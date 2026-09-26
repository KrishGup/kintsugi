#!/usr/bin/env bash
# The budget alternative: Kintsugi on Azure App Service (Linux, container) instead of Container Apps.
# Same image, same /data share, same Easy Auth headers — about a third of the always-on cost, a slower cold start,
# and the OpenSCAD compiles share the plan's vCPU. Use Container Apps (deploy.sh) when you can.
#
#   deploy/azure/appservice.sh -g kintsugi-rg -l eastus2 --sku B2 --auth token
#
# Needs: an image already in a registry (run deploy.sh with --infra-only first, or any registry you like).
set -euo pipefail

RG=""; LOCATION="eastus2"; NAME="kintsugi"; SKU="B2"; AUTH="${KIN_AUTH:-token}"; TOKEN="${KIN_ACCESS_TOKEN:-}"
ADMINS="${KIN_ADMIN_USERS:-}"; IMAGE=""; ACR=""; STORAGE=""; SHARE="kintsugi-data"
while [[ $# -gt 0 ]]; do
  case "$1" in
    -g|--group) RG="$2"; shift 2 ;;
    -l|--location) LOCATION="$2"; shift 2 ;;
    -n|--name) NAME="$2"; shift 2 ;;
    --sku) SKU="$2"; shift 2 ;;
    --auth) AUTH="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --admin) ADMINS="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --acr) ACR="$2"; shift 2 ;;
    --storage) STORAGE="$2"; shift 2 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$RG" ]] || { echo "-g RG required" >&2; exit 2; }
az config set extension.use_dynamic_install=yes_without_prompt -o none 2>/dev/null || true   # `az webapp auth` lives in the authV2 extension

if [[ -z "$ACR" ]]; then ACR="$(az acr list -g "$RG" --query '[0].name' -o tsv)"; fi
if [[ -z "$STORAGE" ]]; then STORAGE="$(az storage account list -g "$RG" --query '[0].name' -o tsv)"; fi
[[ -n "$ACR" && -n "$STORAGE" ]] || { echo "need a registry and a storage account (run deploy.sh --infra-only first, or pass --acr/--storage)" >&2; exit 2; }
LOGIN="$(az acr show -n "$ACR" --query loginServer -o tsv)"
[[ -n "$IMAGE" ]] || IMAGE="$LOGIN/kintsugi:latest"
if [[ "$AUTH" == "token" && -z "$TOKEN" ]]; then TOKEN="$(openssl rand -hex 24)"; echo "generated access code: $TOKEN" >&2; fi

PLAN="$NAME-plan"
APP="$NAME-$(az account show --query id -o tsv | cut -c1-8)"

az appservice plan create -g "$RG" -n "$PLAN" -l "$LOCATION" --is-linux --sku "$SKU" -o none
echo "✓ plan $PLAN ($SKU)" >&2

# the web app pulls from ACR with its system identity (no admin user on the registry)
az webapp create -g "$RG" -p "$PLAN" -n "$APP" --container-image-name "$IMAGE" --assign-identity '[system]' -o none
PRINCIPAL="$(az webapp identity show -g "$RG" -n "$APP" --query principalId -o tsv)"
ACR_ID="$(az acr show -n "$ACR" --query id -o tsv)"
az role assignment create --assignee-object-id "$PRINCIPAL" --assignee-principal-type ServicePrincipal --role AcrPull --scope "$ACR_ID" -o none 2>/dev/null || true
az webapp config set -g "$RG" -n "$APP" --generic-configurations '{"acrUseManagedIdentityCreds": true}' -o none
echo "✓ web app $APP" >&2

# /data on the Azure Files share
KEY="$(az storage account keys list -n "$STORAGE" --query '[0].value' -o tsv)"
az storage share-rm create --storage-account "$STORAGE" --name "$SHARE" --quota 100 -o none 2>/dev/null || true
az webapp config storage-account add -g "$RG" -n "$APP" --custom-id data --storage-type AzureFiles \
  --account-name "$STORAGE" --share-name "$SHARE" --access-key "$KEY" --mount-path /data -o none
echo "✓ /data ← $STORAGE/$SHARE" >&2

# settings = the same environment variables as the container app (docs/DEPLOY-AZURE.md)
SETTINGS=(
  WEBSITES_PORT=8000
  WEBSITES_CONTAINER_START_TIME_LIMIT=600
  WEBSITES_ENABLE_APP_SERVICE_STORAGE=false
  KIN_DATA_DIR=/data KIN_SESSIONS_DIR=/data/sessions KIN_ENV_FILE=/data/.env
  KIN_PROXY_HEADERS=1 KIN_COOKIE_SECURE=1 KIN_SETTINGS_LOCK=1
  KIN_PROVIDER="${KIN_PROVIDER:-openai}" KIN_DESIGNER_MODEL="${KIN_DESIGNER_MODEL:-gpt-6-astra}"
  KIN_CRITIC_MODEL="${KIN_CRITIC_MODEL:-gpt-6-astra}" KIN_VISION_MODEL="${KIN_VISION_MODEL:-gpt-6-astra}"
  KIN_REASONING_EFFORT="${KIN_REASONING_EFFORT:-high}" KIN_SESSION_GIT="${KIN_SESSION_GIT:-1}"
  KIN_AUTH="$AUTH" KIN_ADMIN_USERS="$ADMINS" KIN_EASYAUTH_PROVIDER=aad
)
[[ -n "${OPENAI_API_KEY:-}" ]] && SETTINGS+=(OPENAI_API_KEY="$OPENAI_API_KEY")
[[ -n "${OPENAI_BASE_URL:-}" ]] && SETTINGS+=(OPENAI_BASE_URL="$OPENAI_BASE_URL")
[[ "$AUTH" == "token" ]] && SETTINGS+=(KIN_ACCESS_TOKEN="$TOKEN")
az webapp config appsettings set -g "$RG" -n "$APP" --settings "${SETTINGS[@]}" -o none
az webapp config set -g "$RG" -n "$APP" --always-on true --http20-enabled true -o none
az webapp log config -g "$RG" -n "$APP" --docker-container-logging filesystem -o none
echo "✓ settings" >&2

FQDN="$(az webapp show -g "$RG" -n "$APP" --query defaultHostName -o tsv)"
if [[ "$AUTH" == "easyauth" ]]; then
  REDIRECT="https://$FQDN/.auth/login/aad/callback"
  CID="$(az ad app create --display-name "Kintsugi ($APP)" --sign-in-audience AzureADMyOrg --web-redirect-uris "$REDIRECT" --enable-id-token-issuance true --query appId -o tsv)"
  az ad sp create --id "$CID" -o none 2>/dev/null || true
  CSEC="$(az ad app credential reset --id "$CID" --display-name easyauth --years 2 --query password -o tsv)"
  TENANT="$(az account show --query tenantId -o tsv)"
  az webapp auth microsoft update -g "$RG" -n "$APP" --client-id "$CID" --client-secret "$CSEC" --tenant-id "$TENANT" --yes -o none
  az webapp auth update -g "$RG" -n "$APP" --enabled true --unauthenticated-client-action AllowAnonymous --redirect-provider azureactivedirectory -o none
  echo "✓ Easy Auth (Entra app $CID)" >&2
fi

echo >&2
echo "Kintsugi is up: https://$FQDN   (first start pulls the image: give it a minute)" >&2
[[ "$AUTH" == "token" ]] && echo "access code: $TOKEN" >&2
echo "logs: az webapp log tail -g $RG -n $APP" >&2
