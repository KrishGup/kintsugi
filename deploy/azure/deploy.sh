#!/usr/bin/env bash
# Kintsugi → Azure Container Apps, end to end, re-runnable.
#
#   deploy/azure/deploy.sh -g kintsugi-rg -l eastus2 --auth easyauth --admin you@example.com
#   deploy/azure/deploy.sh -g kintsugi-rg --auth token                       # shared access code (printed once)
#   deploy/azure/deploy.sh -g kintsugi-rg --tag v3 --no-infra                # just build + roll a new image
#
# What it does (each step is idempotent, so re-run after a failure):
#   1. resource group
#   2. bicep, infrastructure only  (logs, storage + file share, registry, identity, key vault, environment)
#   3. az acr build                (the Dockerfile, in Azure — no local docker needed)
#   4. bicep with the app          (container app, /data mounted, secrets, probes)
#   5. easyauth: Entra app registration with the real redirect URI, then bicep once more with the client id/secret
#
# Inputs (flags or environment):
#   -g/--group RG          resource group                     [required]
#   -l/--location LOC      region                             [eastus2]
#   -n/--name NAME         base name (app FQDN starts with it) [kintsugi]
#   --auth MODE            none | token | easyauth            [easyauth]
#   --admin a@b,c@d        KIN_ADMIN_USERS for easyauth        [$KIN_ADMIN_USERS]
#   --token CODE           KIN_ACCESS_TOKEN for token mode     [$KIN_ACCESS_TOKEN or generated]
#   --provider fake        run the scripted demo, no key       [openai]
#   --entra-audience any   allow any Microsoft account (default: this tenant only)
#   --entra-client-id ID   reuse an existing app registration (with --entra-client-secret)
#   --cpu 2.0 --memory 4Gi replica size
#   --min-replicas 0       scale to zero when idle (cold start on the first request)  [1 = always on]
#   --max-cost USD         most one design run may spend, KIN_MAX_COST_USD            [5]
#   --rate N               heavy calls per client per minute, KIN_RATE_PER_MIN         [0 = off]
#   --no-session-git       no per-session git history (faster on the Azure Files share)
#   --tag TAG              image tag                           [UTC timestamp]
#   --no-build             skip az acr build (reuse --tag)
#   --no-infra             skip the infrastructure phase
#   --openai-base-url URL  OPENAI_BASE_URL (Azure OpenAI etc.)
#   OPENAI_API_KEY         from the environment or ./.env      (empty → settings unlocked, paste it in the UI)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

RG="${AZURE_RESOURCE_GROUP:-}"
LOCATION="${AZURE_LOCATION:-eastus2}"
NAME="${KIN_APP_NAME:-kintsugi}"
AUTH="${KIN_AUTH:-easyauth}"
ADMINS="${KIN_ADMIN_USERS:-}"
TOKEN="${KIN_ACCESS_TOKEN:-}"
PROVIDER="${KIN_PROVIDER:-openai}"
ENTRA_AUDIENCE="org"
ENTRA_CLIENT_ID="${ENTRA_CLIENT_ID:-}"
ENTRA_CLIENT_SECRET="${ENTRA_CLIENT_SECRET:-}"
CPU="2.0"
MEMORY="4Gi"
MIN_REPLICAS=1
MAX_COST="5"
RATE=0
SESSION_GIT=1
TAG="$(date -u +%Y%m%d-%H%M%S)"
BUILD=1
INFRA=1
BASE_URL="${OPENAI_BASE_URL:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -g|--group) RG="$2"; shift 2 ;;
    -l|--location) LOCATION="$2"; shift 2 ;;
    -n|--name) NAME="$2"; shift 2 ;;
    --auth) AUTH="$2"; shift 2 ;;
    --admin) ADMINS="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --provider) PROVIDER="$2"; shift 2 ;;
    --entra-audience) ENTRA_AUDIENCE="$2"; shift 2 ;;
    --entra-client-id) ENTRA_CLIENT_ID="$2"; shift 2 ;;
    --entra-client-secret) ENTRA_CLIENT_SECRET="$2"; shift 2 ;;
    --cpu) CPU="$2"; shift 2 ;;
    --memory) MEMORY="$2"; shift 2 ;;
    --min-replicas) MIN_REPLICAS="$2"; shift 2 ;;
    --max-cost) MAX_COST="$2"; shift 2 ;;
    --rate) RATE="$2"; shift 2 ;;
    --no-session-git) SESSION_GIT=0; shift ;;
    --tag) TAG="$2"; shift 2 ;;
    --no-build) BUILD=0; shift ;;
    --no-infra) INFRA=0; shift ;;
    --openai-base-url) BASE_URL="$2"; shift 2 ;;
    -h|--help) sed -n '2,36p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$RG" ]] || { echo "resource group required (-g)" >&2; exit 2; }
command -v az >/dev/null || { echo "az CLI not found: https://aka.ms/azcli" >&2; exit 2; }
az account show >/dev/null 2>&1 || { echo "not signed in: run 'az login'" >&2; exit 2; }
az config set extension.use_dynamic_install=yes_without_prompt -o none 2>/dev/null || true
case "$AUTH" in none|token|easyauth) ;; *) echo "--auth must be none, token or easyauth" >&2; exit 2 ;; esac
# a Python that runs: on Windows `python3` is often the Microsoft Store stub
PY=""
for c in python3 python py; do if "$c" -c "import json" >/dev/null 2>&1; then PY="$c"; break; fi; done
[[ -n "$PY" ]] || { echo "Python 3 not found (python3, python or py)" >&2; exit 2; }

# the key: environment, else ./.env (the file the local UI writes)
if [[ -z "${OPENAI_API_KEY:-}" && -f "$ROOT/.env" ]]; then
  OPENAI_API_KEY="$(grep -E '^OPENAI_API_KEY=' "$ROOT/.env" | tail -1 | cut -d= -f2- | tr -d '"' || true)"
fi
OPENAI_API_KEY="${OPENAI_API_KEY:-}"
if [[ "$PROVIDER" == "openai" && -z "$OPENAI_API_KEY" ]]; then
  echo "note: no OPENAI_API_KEY — deploying with Settings unlocked so you can paste it in the UI (it will live in /data/.env on the share)." >&2
fi
if [[ "$AUTH" == "token" && -z "$TOKEN" ]]; then
  TOKEN="$(openssl rand -hex 24)"
  echo "generated access code: $TOKEN   (keep it; the deployment stores it as a container secret)" >&2
fi

SUB="$(az account show --query id -o tsv)"
TENANT="$(az account show --query tenantId -o tsv)"
echo "▸ subscription $SUB · tenant $TENANT · group $RG · $LOCATION · name $NAME · auth $AUTH" >&2

# ---- 1. resource group ---------------------------------------------------------------------------------------------
az group create -n "$RG" -l "$LOCATION" -o none
echo "✓ resource group" >&2

# parameters go through a 0600 file, never the command line
PARAMS="$(mktemp)"; chmod 600 "$PARAMS"; trap 'rm -f "$PARAMS"' EXIT
# a Windows az (Git Bash) cannot open an MSYS path like /tmp/tmp.x behind '@': hand it the native path
PARAMS_REF="$PARAMS"; command -v cygpath >/dev/null 2>&1 && PARAMS_REF="$(cygpath -m "$PARAMS")"
write_params() {  # $1 = deployApp, $2 = image, $3 = entra client id, $4 = entra client secret
  "$PY" - "$1" "$2" "$3" "$4" > "$PARAMS" <<'PY'
import json, os, sys
deploy, image, cid, csec = sys.argv[1] == "1", sys.argv[2], sys.argv[3], sys.argv[4]
env = os.environ
p = {
  "name": env["NAME"], "location": env["LOCATION"], "deployApp": deploy, "image": image,
  "cpu": env["CPU"], "memory": env["MEMORY"], "minReplicas": int(env["MIN_REPLICAS"]),
  "maxCostUsd": env["MAX_COST"], "ratePerMin": int(env["RATE"]), "sessionGit": env["SESSION_GIT"] == "1",
  "openaiApiKey": env.get("OPENAI_API_KEY", ""), "openaiBaseUrl": env.get("BASE_URL", ""),
  "provider": env["PROVIDER"], "settingsLock": True,
  "authMode": env["AUTH"], "accessToken": env.get("TOKEN", ""), "adminUsers": env.get("ADMINS", ""),
  "easyauthProvider": "aad", "entraClientId": cid, "entraClientSecret": csec,
  "entraTenantId": "common" if env.get("ENTRA_AUDIENCE") == "any" else env["TENANT"],
}
print(json.dumps({"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
                  "contentVersion": "1.0.0.0", "parameters": {k: {"value": v} for k, v in p.items()}}))
PY
}
export NAME LOCATION CPU MEMORY MIN_REPLICAS MAX_COST RATE SESSION_GIT OPENAI_API_KEY BASE_URL PROVIDER AUTH TOKEN ADMINS ENTRA_AUDIENCE TENANT

deploy() {  # runs main.bicep with the current $PARAMS; prints outputs as JSON
  az deployment group create -g "$RG" -n "kintsugi-$(date -u +%Y%m%d%H%M%S)" \
    --template-file "$HERE/main.bicep" --parameters "@$PARAMS_REF" --query properties.outputs -o json
}

# ---- 2. infrastructure ---------------------------------------------------------------------------------------------
if [[ "$INFRA" == "1" ]]; then
  write_params 0 "" "$ENTRA_CLIENT_ID" "$ENTRA_CLIENT_SECRET"
  OUT="$(deploy)"
  echo "✓ infrastructure" >&2
else
  OUT="$(az deployment group list -g "$RG" -o json \
        --query "sort_by([?starts_with(name,'kintsugi-') && properties.provisioningState=='Succeeded'], &properties.timestamp)[-1].properties.outputs")"
  [[ -n "$OUT" && "$OUT" != "null" ]] || { echo "no successful kintsugi deployment in $RG yet; run without --no-infra" >&2; exit 2; }
fi
ACR="$(echo "$OUT" | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["registryName"]["value"])')"
LOGIN="$(echo "$OUT" | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["registryLoginServer"]["value"])')"
IMAGE="$LOGIN/kintsugi:$TAG"

# ---- 3. build the image in Azure -----------------------------------------------------------------------------------
if [[ "$BUILD" == "1" ]]; then
  echo "▸ az acr build $IMAGE (this takes a few minutes: node build + OpenSCAD apt install)" >&2
  if [[ "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* || "$(uname -s)" == CYGWIN* ]]; then
    # the Windows az streams the build log through a cp1252 console and dies on the first non-ASCII character (Vite's
    # check mark) while the build carries on in Azure: wait for the run instead of streaming it
    RUN="$(az acr build --registry "$ACR" --image "kintsugi:$TAG" --image "kintsugi:latest" --platform linux/amd64           --file "$ROOT/Dockerfile" "$ROOT" --no-logs --query "[runId, status]" -o tsv 2>/dev/null | tr -s '\t\r\n' ' ')"
    read -r RUN_ID RUN_STATUS <<< "$RUN"
    if [[ "$RUN_STATUS" != "Succeeded" ]]; then
      echo "image build ${RUN_STATUS:-did not start} (run ${RUN_ID:-?}): az acr task logs -r $ACR --run-id ${RUN_ID:-<id>}" >&2; exit 1
    fi
  else
    az acr build --registry "$ACR" --image "kintsugi:$TAG" --image "kintsugi:latest" --platform linux/amd64 --file "$ROOT/Dockerfile" "$ROOT" -o none
  fi
  echo "✓ image $IMAGE" >&2
fi

# ---- 4. the app ----------------------------------------------------------------------------------------------------
write_params 1 "$IMAGE" "$ENTRA_CLIENT_ID" "$ENTRA_CLIENT_SECRET"
OUT="$(deploy)"
FQDN="$(echo "$OUT" | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["fqdn"]["value"])')"
echo "✓ app https://$FQDN" >&2

# ---- 5. Easy Auth: the app registration needs the real redirect URI, which only exists now -------------------------
if [[ "$AUTH" == "easyauth" && -z "$ENTRA_CLIENT_ID" ]]; then
  REDIRECT="https://$FQDN/.auth/login/aad/callback"
  AUD="AzureADMyOrg"; [[ "$ENTRA_AUDIENCE" == "any" ]] && AUD="AzureADandPersonalMicrosoftAccount"
  EXISTING="$(az ad app list --display-name "Kintsugi ($NAME)" --query '[0].appId' -o tsv 2>/dev/null || true)"
  if [[ -n "$EXISTING" ]]; then
    ENTRA_CLIENT_ID="$EXISTING"
    az ad app update --id "$ENTRA_CLIENT_ID" --web-redirect-uris "$REDIRECT" --enable-id-token-issuance true --sign-in-audience "$AUD" -o none
  else
    ENTRA_CLIENT_ID="$(az ad app create --display-name "Kintsugi ($NAME)" --sign-in-audience "$AUD" \
      --web-redirect-uris "$REDIRECT" --enable-id-token-issuance true --query appId -o tsv)"
    az ad sp create --id "$ENTRA_CLIENT_ID" -o none 2>/dev/null || true
  fi
  ENTRA_CLIENT_SECRET="$(az ad app credential reset --id "$ENTRA_CLIENT_ID" --display-name "easyauth $(date -u +%Y-%m-%d)" --years 2 --query password -o tsv)"
  echo "✓ Entra app registration $ENTRA_CLIENT_ID (redirect $REDIRECT)" >&2
  write_params 1 "$IMAGE" "$ENTRA_CLIENT_ID" "$ENTRA_CLIENT_SECRET"
  deploy >/dev/null
  echo "✓ Easy Auth wired (Microsoft sign-in; admins: ${ADMINS:-none})" >&2
fi

cat >&2 <<EOF

Kintsugi is up:  https://$FQDN
  health         https://$FQDN/api/health
  logs           az containerapp logs show -g $RG -n $NAME --follow
  new image      $0 -g $RG --no-infra            (or push to main with the GitHub workflow)
  data           Azure Files share 'kintsugi-data' in the storage account (sessions/, .env)
EOF
if [[ "$AUTH" == "token" ]]; then echo "  access code    $TOKEN" >&2; fi
if [[ "$AUTH" == "easyauth" ]]; then
  echo "  restrict who may sign in: Entra → Enterprise applications → 'Kintsugi ($NAME)' → Properties → Assignment required" >&2
fi
