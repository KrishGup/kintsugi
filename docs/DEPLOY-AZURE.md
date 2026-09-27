# Deploying Kintsugi on Azure

One container, one always-on replica, everything it writes on an Azure Files share, the OpenAI key in Key Vault, sign-in
handled by the platform. `deploy/azure/deploy.sh` stands the whole thing up from a laptop with the `az` CLI; the same
Bicep is re-runnable, and a GitHub Actions workflow ships every push to `main`.

What you get at the end:

- `https://kintsugi.<random>.<region>.azurecontainerapps.io` — the full app: photo intake, capture loop, designer,
  critic, customizer, blueprint sheets, exports. Phones on any network can use it.
- **Sign-in** (choose one): Microsoft / GitHub / Google accounts via Azure Easy Auth with sessions **per user**; or one
  shared access code; or nothing (a private demo box).
- **Portable state**: every session exports as a `.zip` with a manifest and published JSON Schemas, and imports on any
  other Kintsugi (Azure, a laptop, a NAS). That is also the backup story.
- Settings (provider, key, models) come from the deployment and the UI shows them read-only — nobody pastes a key into a
  browser on a shared server.

> Two things are **not** in scope: horizontal scaling (runs and live previews live inside the one process, see
> [Why one replica](#why-one-replica)) and a database (the file share *is* the store; sessions are folders).

---

## 1. The stack

```
                     ┌──────────────────────────────────────────────────────────────────┐
   phone / browser ──▶  Container Apps ingress (HTTPS, managed cert)                    │
                     │   └─ Easy Auth  (Entra ID · GitHub · Google)  ──▶ X-MS-CLIENT-PRINCIPAL-* headers
                     │        └─ Container App  kintsugi  (1 replica · 2 vCPU · 4 GiB)  │
                     │             ├─ kin serve  (FastAPI + uvicorn, :8000)             │
                     │             ├─ OpenSCAD 2021.01 + BOSL2, xvfb                    │
                     │             ├─ /data  ◀── Azure Files share  kintsugi-data       │
                     │             ├─ OPENAI_API_KEY ◀── Key Vault (managed identity)   │
                     │             └─ stdout/stderr ──▶ Log Analytics                   │
                     │   Container Registry ──▶ image  (az acr build · GitHub Actions)  │
                     └──────────────────────────────────────────────────────────────────┘
                                                      │
                                                      ▼  api.openai.com  (or OPENAI_BASE_URL)
```

| # | Service | SKU / size | Why it is there | ≈ cost / month |
|---|---------|-----------|-----------------|----------------|
| 1 | **Azure Container Apps** environment + app | Consumption profile, min = max = 1 replica, 2 vCPU / 4 GiB | Runs the container with HTTPS ingress, a managed certificate, health probes, log shipping and built-in authentication. Single revision mode. | ≈ $50 mostly idle (idle rate) → ≈ $155 if busy 24 h/day |
| 2 | **Azure Files** (Storage account, Standard LRS) | one SMB share `kintsugi-data`, 100 GiB quota | `/data` in the container: `sessions/` (photos, spec, every iteration, sheets, exports, git history) and the settings file `.env`. Survives restarts, image rolls and region evacuation of the replica. 14-day soft delete on the share. | ≈ $1–6 (used GiB + transactions) |
| 3 | **Azure Container Registry** | Basic | The image, built *in Azure* by `az acr build` (no Docker on your machine). Pulled with the managed identity — no admin password. | ≈ $5 |
| 4 | **Key Vault** | Standard, RBAC | `openai-api-key`. The app's identity has *Key Vault Secrets User*; the Container App secret is a Key Vault reference, so rotation = update the secret + restart. | ≈ $0 |
| 5 | **User-assigned managed identity** | — | The app's identity: AcrPull on the registry, secrets-user on the vault. Nothing has a password. | free |
| 6 | **Log Analytics** workspace | PerGB2018, 30-day retention | `kin serve` logs (uvicorn access log, run narration, OpenSCAD errors). Required by the Container Apps environment. | ≈ $0–3 |
| 7 | **Easy Auth** (Container Apps authentication) + **Entra app registration** | — | The platform signs people in *before* the request reaches the container and forwards the identity. GitHub or Google can be added the same way. | free |
| 8 | *(optional)* **Azure OpenAI** | your deployment | If your OpenAI usage has to stay inside Azure, point `OPENAI_BASE_URL` at the resource's OpenAI-compatible endpoint. Not needed: the default is api.openai.com with your key. | your usage |
| 9 | *(optional)* **GitHub Actions** | — | `.github/workflows/azure.yml`: build in ACR + roll the app on every push to `main`, via a federated (OIDC) credential. | free |

Budget alternative: **App Service B2** (Linux container) instead of Container Apps — same image, same share, same auth
headers, ≈ $55/month always-on. See [App Service instead](#9-app-service-instead-budget).

---

## 2. Environment variables, per piece

Kintsugi reads everything from the environment (and, for anything not set there, from `KIN_ENV_FILE`). The container
app carries the variables below; the deployment scripts set every one of them. `.env.example` at the repo root is the
same list for local runs.

### 2.1 The Container App (runtime environment)

| Variable | Value in Azure | Source | What it does |
|----------|----------------|--------|--------------|
| `OPENAI_API_KEY` | *(secret)* | Container App secret `openai-api-key` → **Key Vault** reference | The designer, code-blind critic and photo intake run on the OpenAI Responses API. |
| `OPENAI_BASE_URL` | *(empty)* or `https://<res>.openai.azure.com/openai/v1/` | plain | Optional. Azure OpenAI's OpenAI-compatible endpoint or a gateway; the model names must then be your deployment names. |
| `KIN_PROVIDER` | `openai` | plain | `openai` or `fake` (scripted demo, no key, no cost — fine for a judging box). |
| `KIN_DESIGNER_MODEL` | `gpt-6-astra` | plain | Model for the designer loop. |
| `KIN_CRITIC_MODEL` | `gpt-6-astra` | plain | Model for the code-blind critic (`gpt-6-sol` is ~5× cheaper and fine here). |
| `KIN_VISION_MODEL` | `gpt-6-astra` | plain | Model for photo intake / capture grading. |
| `KIN_REASONING_EFFORT` | `high` | plain | `low` · `medium` · `high` · `max`. |
| `KIN_OPENAI_TIMEOUT_S` | `900` | plain | Per-request timeout; long design steps with images need it. |
| `KIN_OPENAI_RETRIES` | `6` | plain | Client retries on 429/5xx. |
| `KIN_OPENAI_STATELESS` | *(unset = 0)* | plain | `1` resends the whole transcript with `store=false` (zero-retention orgs). |
| `KIN_SETTINGS_LOCK` | `1` | plain | The Settings dialog becomes read-only; `POST /api/settings` answers 403. The key never lands in a file on the share. |
| `KIN_DATA_DIR` | `/data` | plain | Root of everything the app writes. |
| `KIN_SESSIONS_DIR` | `/data/sessions` | plain | Session folders. |
| `KIN_ENV_FILE` | `/data/.env` | plain | Where the UI would persist settings (unused while locked). |
| `KIN_SESSION_GIT` | `1` | plain | Per-iteration git history inside each session. Works on Azure Files with the `nobrl` mount; set `0` if runs feel slow — `history.json` still records every iteration. |
| `KIN_MAX_IMPORT_MB` | `500` | plain | Largest archive the import endpoint accepts. |
| `KIN_MAX_COST_USD` | `5` | plain | The most one design run may spend on model calls (the client's own token accounting); `0` = no cap. Set it on anything shared — the iteration budget bounds work, this bounds money. |
| `KIN_RATE_PER_MIN` | `30` (public) · `0` (private) | plain | Heavy calls (run, iterate, coupon, export, params, code, photos, intake, import) per client per minute; `0` = off. |
| `KIN_MAX_COMPILES` | `4` | plain | OpenSCAD processes at once across all sessions; previews queue and cancel each other. |
| `KIN_AUTH` | `easyauth` · `token` · `none` | plain | Who may use it — [section 5](#5-sign-in-the-three-modes). |
| `KIN_ADMIN_USERS` | `you@example.com,teammate@example.com` | plain | *easyauth*: lower-case ids (email for Microsoft/Google, login for GitHub) who see every session and may change settings. |
| `KIN_EASYAUTH_PROVIDER` | `aad` · `github` · `google` | plain | *easyauth*: which `/.auth/login/<provider>` the sign-in gate links to. |
| `KIN_ACCESS_TOKEN` | *(secret)* | Container App secret `access-token` | *token*: the shared access code. |
| `KIN_SECRET_KEY` | *(secret, optional)* | Container App secret `secret-key` | *token*: cookie signing key; defaults to the access code. Set separately to invalidate cookies without changing the code. |
| `KIN_COOKIE_SECURE` | `1` | plain | Auth cookie gets the `Secure` flag (also automatic behind `X-Forwarded-Proto: https`). |
| `KIN_PROXY_HEADERS` | `1` | plain | Trust `X-Forwarded-For/Proto` from the ingress (client IPs in logs, https detection). |
| `KIN_HOST` / `KIN_PORT` | `0.0.0.0` / `8000` | plain | Bind address; the ingress targets 8000. |
| `KIN_KEEPALIVE_S` | *(unset = 75)* | plain | HTTP keep-alive idle timeout, above the ingress's. |
| `KIN_OPENSCAD_BIN` | *(unset = `openscad`)* | plain | The image installs OpenSCAD 2021.01 on PATH. |
| `PYTHONUNBUFFERED` | `1` | plain | Logs arrive in Log Analytics as they happen. |

### 2.2 Key Vault

| Secret | Value | Consumer |
|--------|-------|----------|
| `openai-api-key` | your OpenAI key | Container App secret `openai-api-key` (Key Vault reference, versionless URL — rotate by setting a new version and restarting the revision: `az containerapp revision restart`). |

The identity `kintsugi-id` holds **Key Vault Secrets User** on the vault (RBAC mode; no access policies).

### 2.3 Container App secrets

| Secret name | Filled from | Used by |
|-------------|-------------|---------|
| `openai-api-key` | Key Vault reference (above) | env `OPENAI_API_KEY` |
| `access-token` | bicep param `accessToken` (token mode) | env `KIN_ACCESS_TOKEN` |
| `secret-key` | bicep param `secretKey` (optional) | env `KIN_SECRET_KEY` |
| `entra-client-secret` | the Entra app registration's client secret | Easy Auth (`clientSecretSettingName`) |
| `github-client-secret` / `google-client-secret` | the OAuth app's secret | Easy Auth |

### 2.4 Storage (Azure Files)

| Setting | Value |
|---------|-------|
| Share | `kintsugi-data`, SMB, 100 GiB quota (parameter `shareQuotaGb`), TransactionOptimized tier, 14-day soft delete |
| Environment storage link | `kintsugi-data` (account name + key, ReadWrite) |
| Mount in the app | volume `data` → `/data`, options `dir_mode=0777,file_mode=0777,uid=0,gid=0,mfsymlinks,nobrl,cache=strict,actimeo=1` |

`nobrl` turns off byte-range locking (git and atomic renames on SMB); `mfsymlinks` lets git write symlinks; `actimeo=1`
keeps attribute caching short so a restarted replica sees the truth. Sessions weigh 20–80 MB each with photos and
sheets; 100 GiB is hundreds of parts.

### 2.5 Easy Auth — the Entra app registration

| Setting | Value |
|---------|-------|
| Display name | `Kintsugi (<name>)` |
| Sign-in audience | `AzureADMyOrg` (your tenant) — or `AzureADandPersonalMicrosoftAccount` with `--entra-audience any` |
| Web redirect URI | `https://<fqdn>/.auth/login/aad/callback` |
| ID tokens | enabled (implicit grant for id_token — Easy Auth needs it) |
| Client secret | 2 years, stored as Container App secret `entra-client-secret` |
| Auth config (`authConfigs/current`) | `unauthenticatedClientAction: AllowAnonymous`, `redirectToProvider: azureActiveDirectory`, `requireHttps`, `preserveUrlFragmentsForLogins: true` (the SPA uses `#/` routes), cookie 8 h |

`AllowAnonymous` is deliberate: the platform *authenticates* but does not *block*, so the app shell always loads and the
app itself answers `401` (JSON) on `/api/*` without a principal — that is what draws the sign-in gate with the
`/.auth/login/aad` link. The identity arrives in `X-MS-CLIENT-PRINCIPAL-NAME` / `-ID` / `-IDP` and the base64
`X-MS-CLIENT-PRINCIPAL` claims document; the app uses `preferred_username`/email (lower-case) as the user id and the
`name` claim for display.

**GitHub** instead of / as well as Microsoft: create an OAuth App at github.com → Settings → Developer settings with
callback `https://<fqdn>/.auth/login/github/callback`, then pass `githubClientId` / `githubClientSecret` (and
`easyauthProvider=github`, `KIN_ADMIN_USERS` = GitHub logins). **Google**: an OAuth client in Google Cloud Console with
redirect `https://<fqdn>/.auth/login/google/callback`, parameters `googleClientId` / `googleClientSecret`.

### 2.6 GitHub Actions (`.github/workflows/azure.yml`)

| Kind | Name | Value |
|------|------|-------|
| secret | `AZURE_CLIENT_ID` | app registration (client) id of the deployer identity |
| secret | `AZURE_TENANT_ID` | your tenant id |
| secret | `AZURE_SUBSCRIPTION_ID` | the subscription |
| variable | `AZURE_RESOURCE_GROUP` | e.g. `kintsugi-rg` |
| variable | `AZURE_ACR_NAME` | registry name from `deploy.sh` output (e.g. `kintsugiacrx7k…`) |
| variable | `AZURE_APP_NAME` | `kintsugi` |

The deployer is an Entra app registration with a **federated credential** whose subject is
`repo:<owner>/<repo>:ref:refs/heads/main` (the workflow runs on pushes to `main`; a manual run from another branch needs
its own subject), holding *Contributor* on the resource group. *Contributor* covers `az acr build` and the app update; no
secret is stored in GitHub.

### 2.7 Local development (`.env`)

Copy `.env.example` → `.env`, set `OPENAI_API_KEY`, run `kin serve`. `KIN_AUTH=none` on a laptop; `KIN_AUTH=token`
with `KIN_ACCESS_TOKEN` for anything you expose with a tunnel. `deploy/docker-compose.yml` runs the production image
locally with `/data` on a volume.

---

## 3. Deploy in one command

Prerequisites: an Azure subscription where you can create resource groups **and** app registrations (the Entra step
needs *Application Developer* or better — or hand `--entra-client-id/--entra-client-secret` to the script), the
[`az` CLI](https://aka.ms/azcli) ≥ 2.60 signed in (`az login`), Python 3 on PATH, `openssl` for generated codes. No Docker.

```bash
git clone https://github.com/KrishGup/kintsugi && cd kintsugi
export OPENAI_API_KEY=sk-...                      # or leave it in ./.env; the script reads that too
deploy/azure/deploy.sh -g kintsugi-rg -l eastus2 --auth easyauth --admin you@example.com
```

Ten to fifteen minutes later it prints the URL. The script runs these phases, each idempotent (re-run after any failure):

1. `az group create`
2. **infrastructure** — `main.bicep` with `deployApp=false`: Log Analytics, storage + share, registry, identity, Key
   Vault (+ the `openai-api-key` secret), the Container Apps environment with the share attached, the role assignments
3. **image** — `az acr build --platform linux/amd64 -f Dockerfile .` (node build + OpenSCAD apt install, ≈ 5 min)
4. **app** — `main.bicep` with `deployApp=true image=<registry>/kintsugi:<tag>`: the Container App, `/data` mounted,
   secrets, probes, ingress → prints the FQDN
5. **sign-in** (`--auth easyauth`) — creates the Entra app registration `Kintsugi (kintsugi)` with the real callback
   URL, mints a client secret, and runs step 4 once more with `entraClientId`/`entraClientSecret` so the auth config
   is written

Then:

- Open the URL, sign in. The **first** admin is whoever you passed with `--admin` (or set `KIN_ADMIN_USERS` later with
  `az containerapp update --set-env-vars`).
- Restrict *who* may sign in: Entra admin center → Enterprise applications → `Kintsugi (kintsugi)` → Properties →
  **Assignment required = Yes**, then assign users/groups. Without it, anyone in the tenant can sign in (they only ever
  see their own sessions).
- Custom domain: `az containerapp hostname add -g kintsugi-rg -n kintsugi --hostname parts.example.com` +
  `az containerapp hostname bind … --environment kintsugi-env --validation-method CNAME` (managed certificate, free). Then
  add `https://parts.example.com/.auth/login/aad/callback` to the app registration's redirect URIs.

Other shapes:

```bash
deploy/azure/deploy.sh -g kintsugi-rg --auth token                 # one shared access code, printed once
deploy/azure/deploy.sh -g kintsugi-rg --auth none --provider fake  # a public scripted demo, no key, no sign-in
deploy/azure/deploy.sh -g kintsugi-rg --no-infra --tag v7          # build + roll a new image only
deploy/azure/deploy.sh -g kintsugi-rg --cpu 4.0 --memory 8Gi       # bigger replica (faster OpenSCAD on complex parts)
deploy/azure/deploy.sh -g kintsugi-rg --openai-base-url https://myres.openai.azure.com/openai/v1/
```

### By hand (the same thing without the script)

```bash
RG=kintsugi-rg; LOC=eastus2
az group create -n $RG -l $LOC
az deployment group create -g $RG -f deploy/azure/main.bicep -p name=kintsugi deployApp=false
ACR=$(az acr list -g $RG --query '[0].name' -o tsv); LOGIN=$(az acr show -n $ACR --query loginServer -o tsv)
az acr build -r $ACR -t kintsugi:v1 --platform linux/amd64 -f Dockerfile .
az deployment group create -g $RG -f deploy/azure/main.bicep \
   -p name=kintsugi deployApp=true image=$LOGIN/kintsugi:v1 authMode=easyauth adminUsers=you@example.com \
      openaiApiKey="$OPENAI_API_KEY"
FQDN=$(az containerapp show -g $RG -n kintsugi --query properties.configuration.ingress.fqdn -o tsv)
APPID=$(az ad app create --display-name "Kintsugi (kintsugi)" --sign-in-audience AzureADMyOrg \
          --web-redirect-uris https://$FQDN/.auth/login/aad/callback --enable-id-token-issuance true --query appId -o tsv)
az ad sp create --id $APPID
SECRET=$(az ad app credential reset --id $APPID --years 2 --query password -o tsv)
az deployment group create -g $RG -f deploy/azure/main.bicep \
   -p name=kintsugi deployApp=true image=$LOGIN/kintsugi:v1 authMode=easyauth adminUsers=you@example.com \
      openaiApiKey="$OPENAI_API_KEY" entraClientId=$APPID entraClientSecret="$SECRET"
```

`deploy/azure/main.bicepparam` is the same parameter set as a file, reading secrets from the environment.

---

## 4. Continuous deployment

One-time: create the deployer identity and the federated credential, then the GitHub secrets/variables from §2.6.

```bash
SUB=$(az account show --query id -o tsv); RG=kintsugi-rg
DEPLOYER=$(az ad app create --display-name "kintsugi-deployer" --query appId -o tsv)
az ad sp create --id $DEPLOYER
az role assignment create --assignee $DEPLOYER --role Contributor --scope /subscriptions/$SUB/resourceGroups/$RG
az ad app federated-credential create --id $DEPLOYER --parameters '{
  "name": "github-main", "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:KrishGup/kintsugi:ref:refs/heads/main", "audiences": ["api://AzureADTokenExchange"] }'
```

Every push to `main` (docs excluded) then builds `kintsugi:<sha>` in ACR, rolls the app to it, and waits for
`/api/health` to answer. Rollback = `az containerapp revision list` + `az containerapp update --image …:<older sha>`.

---

## 5. Sign-in: the three modes

| `KIN_AUTH` | Who gets in | Sessions | Settings | When |
|------------|-------------|----------|----------|------|
| `none` | anyone who reaches the URL | shared | anyone (unless `KIN_SETTINGS_LOCK`) | a laptop, a LAN, a judging box with `provider=fake` |
| `token` | whoever has the access code (asked once, 30-day signed cookie; scripts send `Authorization: Bearer <code>`) | shared by all holders | any holder | a small trusted group; the cheapest real protection |
| `easyauth` | accounts the platform accepts (Entra tenant / GitHub / Google) | **per user** — you see only sessions you created or imported; `KIN_ADMIN_USERS` see all | admins only | anything on the public internet with more than one person |

Mechanics worth knowing:

- The gate is the app's own page: in `token` mode it asks for the code and calls `POST /api/auth/login`, which sets an
  HttpOnly, SameSite=Lax, Secure cookie holding an HMAC of a fixed message under `KIN_SECRET_KEY` (default: the code
  itself) — the code is never stored in the browser. `POST /api/auth/logout` clears it.
- In `easyauth` mode the gate links to `/.auth/login/<provider>?post_login_redirect_uri=/`; sign-out goes to
  `/.auth/logout`. `GET /api/auth/me` tells the UI which mode and who.
- **Only enable `easyauth` behind Azure's authentication.** The app trusts the `X-MS-CLIENT-PRINCIPAL-*` headers
  because the platform sets (and strips) them; exposed directly, anyone could forge them. The bicep never produces that
  combination.
- Ownership is stamped on the session (`owner`, `owner_name` in `session.json`) at creation and on import. Switching a
  server from `easyauth` back to `token`/`none` makes every session visible to everyone again — by design, the stamps
  stay for when you switch back.
- The health endpoint, the auth endpoints and the schemas are public; every other `/api/*` path needs a user.

---

## 6. Portable state: session archives

Every session can leave and re-enter as one file, so people can move parts between servers, keep their own backups, and
you can rebuild a deployment from nothing.

- **Web**: session → Export → *Download session archive*; Home → *Import* (a `.zip`). While a run is in progress the
  archive is refused (409) — a run cannot travel.
- **API**: `GET /api/sessions/{id}/archive` (`application/zip`), `POST /api/sessions/import` (multipart `file`,
  `201` with the session detail; `413` over `KIN_MAX_IMPORT_MB`, `422` when it is not a valid archive).
- **CLI**: `kin archive <session dir> [-o file.zip]`, `kin import file.zip [--sessions DIR] [--new-id]`.

The zip holds `manifest.json` plus every file of the session except derived/heavy ones (`.git/`, `preview/`,
`export/bundle.zip`): `session.json`, `spec.yaml`, `part.scad`, `part.json` (presets), `params.json`, `checks.json`,
`history.json`, `intake.json`, `events.jsonl`, and the `photos/ measure/ iterations/ sheets/ critic/ export/` folders.
The manifest lists each file with size and sha256, the app version, and the session's meta (minus the owner).

Schemas — served by the app and committed in the repo:

| Schema | URL on the server | In the repo |
|--------|-------------------|-------------|
| archive manifest | `/api/schemas/session-archive` | `docs/schemas/session-archive.schema.json` |
| Part Spec (`spec.yaml`) | `/api/schemas/part-spec` | `docs/schemas/part-spec.schema.json` |

Import rules: the manifest must say `kind: kintsugi-session` with a supported `schema_version`; every path is checked
against traversal (`..`, absolute, drive letters); the expanded size is capped; the original id is kept when it is
free on the target, otherwise a fresh one is minted; the session becomes the importer's; a `running` status becomes
`stopped`; a new git history is initialised; an `imported` event is appended. Nothing is executed on import.

**Backups.** Two layers: (1) Azure Files share snapshots — `az storage share snapshot --name kintsugi-data
--account-name <acct>` on a schedule (Azure Backup for Files does this with retention); (2) archives, which are
what you would hand to a person. To rebuild a deployment: run `deploy.sh` into a new group, then either restore the
share from a snapshot or `kin import` the archives.

---

## 7. Operating it

**Logs**: `az containerapp logs show -g kintsugi-rg -n kintsugi --follow` (console) or in Log Analytics,
`ContainerAppConsoleLogs_CL | where ContainerAppName_s == "kintsugi" | order by TimeGenerated desc`. The run narration,
tool calls, OpenSCAD errors and uvicorn access lines all go to stdout.

**Health**: `GET /api/health` → `{ok, version, openscad, llm: {provider, ready, reason, models}, auth, settings_locked}`.
The startup, liveness and readiness probes hit it.

**Update the code**: push to `main` (workflow) or `deploy/azure/deploy.sh -g kintsugi-rg --no-infra`. A roll takes
about a minute: the new revision must pass its startup probe before traffic moves and the old one is stopped, so a run
that is in progress at that moment ends with `stopped` — roll when nobody is designing.

**Change settings**: `az containerapp update -g kintsugi-rg -n kintsugi --set-env-vars KIN_CRITIC_MODEL=gpt-6-sol
KIN_ADMIN_USERS=a@x.com,b@x.com`. Rotate the OpenAI key: `az keyvault secret set --vault-name <kv> -n openai-api-key
--value sk-new` then `az containerapp revision restart -g kintsugi-rg -n kintsugi --revision $(az containerapp revision
list -g kintsugi-rg -n kintsugi --query '[0].name' -o tsv)`.

**Sizing**: OpenSCAD 2021.01 is single-threaded per compile; the designer, the customizer preview engine and a critic
render can overlap, so 2 vCPU is the comfortable floor and 4 vCPU noticeably shortens complex parts. Memory sits under
1 GiB in normal use; big meshes (checks + blueprint sheets) spike to 2–3 GiB — hence 4 GiB.

<a id="why-one-replica"></a>**Why one replica.** A design run is an asyncio task inside the process, the customizer's
preview engine keeps per-session compile state in memory, and the event stream tails a file — all of that assumes one
process per sessions directory. `minReplicas = maxReplicas = 1` and single-revision mode make Container Apps behave like
one always-on server with a managed front door. Scaling out would need a queue and a shared preview store; it is not
what this deployment is for. (It is also why `KIN_WORKERS` stays at 1.)

**Long connections**: the UI follows a run over Server-Sent Events. The server sends a `ping` every 15 s so nothing
idles out, and if the ingress ever closes a stream (it caps single HTTP requests at 240 s in some configurations) the
client reconnects with `since=<last id>` and misses nothing. Runs themselves are started with `POST …/run` (returns
`202` at once) and finish in the background, so no request outlives the ingress limit; exports and archives stream.

**Costs, roughly** (East US 2, pay-as-you-go, September 2026 list prices; check the calculator):

| Item | Idle month | Busy month |
|------|-----------|------------|
| Container App 2 vCPU / 4 GiB, 1 replica | ≈ $47 (idle rate) | ≈ $155 (active rate, 24×7) |
| Storage (Files, ~10 GiB used) | ≈ $2 | ≈ $6 |
| Container Registry Basic | $5 | $5 |
| Log Analytics | ≈ $0 (5 GiB free) | ≈ $3 |
| Key Vault, identity, Easy Auth | ≈ $0 | ≈ $0 |
| **Platform total** | **≈ $55** | **≈ $170** |
| OpenAI usage | a typical part: $0.50–3 with `gpt-6-astra` at `high`; the critic on `gpt-6-sol` cuts ~30 % | |

To pause everything: `az containerapp update -g kintsugi-rg -n kintsugi --min-replicas 0 --max-replicas 0` (the share and
everything on it stay; ≈ $8/month). To delete: `az group delete -n kintsugi-rg` (Key Vault soft-deletes for 30 days).

---

## 8. Troubleshooting

| Symptom | Cause → fix |
|---------|-------------|
| Deployment fails at the app with *"unable to fetch secret from Key Vault"* / *"identity does not have access"* | RBAC propagation lag on a brand-new identity. Re-run the same command (the deployment is idempotent). |
| Container starts, probes fail, revision *Degraded* | `az containerapp logs show … --tail 200`. Usually the share: check the storage link exists in the environment (`az containerapp env storage list`) and the account key was not rotated. |
| `/api/health` says `openscad: null` | The image did not install OpenSCAD — `az acr build` output shows the apt step; rebuild. |
| Sign-in loops or "AADSTS50011: redirect URI mismatch" | The app registration's redirect URI must equal `https://<fqdn>/.auth/login/aad/callback` exactly (custom domain → add it). |
| Signed in but the gate still shows "Sign in" | The auth config was not written (only when `entraClientId` is set) — `az containerapp auth show -g … -n kintsugi`. Or `KIN_AUTH` is `easyauth` while the platform auth is off: the app then sees no principal. |
| Everyone sees everyone's sessions | `KIN_AUTH` is `token` or `none`. Per-user scoping needs `easyauth`. |
| Settings dialog is read-only and you want to change models | That is `KIN_SETTINGS_LOCK=1`. Change the env vars (§7) — or set the lock to `0` and the UI writes `/data/.env`. |
| Runs are slow to start; every iteration pauses ~1 s | git on SMB. `KIN_SESSION_GIT=0` (history.json keeps the iterations). |
| The event stream shows *offline* now and then | The ingress closed a long SSE response; the client reconnects with `since`. Nothing is lost. |
| Import answers 413 | Over `KIN_MAX_IMPORT_MB` (default 500). Raise it, or `kin import` on the share directly. |
| Import answers 422 *"unsafe path"* | The zip was hand-made with `../` or absolute paths; archives from Kintsugi never contain them. |
| `az acr build` fails at `npm ci` | Network hiccup inside ACR Tasks; re-run. |

---

<a id="9-app-service-instead-budget"></a>
## 9. App Service instead (budget)

`deploy/azure/appservice.sh` puts the same image on an **App Service plan B2 (Linux, 2 cores, 3.5 GB)** — ≈ $55/month
always-on, everything else identical: `/data` on the Azure Files share (`az webapp config storage-account add`), the
same environment variables as **App settings**, Easy Auth via `az webapp auth`. Differences to know:

- Cold start is slower (first image pull ≈ 2 min; `WEBSITES_CONTAINER_START_TIME_LIMIT=600` covers it) and B-tier CPU
  is shared; OpenSCAD on a complex part takes 1.5–2× longer than on 2 dedicated vCPU.
- Idle request timeout is 230 s — same SSE reconnect story.
- `WEBSITES_PORT=8000`, `WEBSITES_ENABLE_APP_SERVICE_STORAGE=false` (we mount our own share), `always-on` true.
- Easy Auth headers are the same, so `KIN_AUTH=easyauth` works unchanged.
- Secrets: App settings are encrypted at rest; use `@Microsoft.KeyVault(SecretUri=…)` references with the web app's
  system identity if you want the key in Key Vault there too.

```bash
deploy/azure/deploy.sh -g kintsugi-rg --no-infra --no-build   # (infra phase already done) or run main.bicep with deployApp=false
deploy/azure/appservice.sh -g kintsugi-rg --sku B2 --auth easyauth --admin you@example.com
```

---

## 10. Azure OpenAI instead of api.openai.com (optional)

Kintsugi speaks the **OpenAI Responses API**. Azure OpenAI exposes it on the OpenAI-compatible v1 endpoint of a resource;
point the client there and use your *deployment names* as the model ids:

```
OPENAI_BASE_URL=https://<resource>.openai.azure.com/openai/v1/
OPENAI_API_KEY=<the resource's key>          # or an Entra token via your gateway
KIN_DESIGNER_MODEL=<deployment name>  KIN_CRITIC_MODEL=…  KIN_VISION_MODEL=…
```

Keep `KIN_OPENAI_STATELESS=0` only if the endpoint supports `previous_response_id` (stored responses); set it to `1`
otherwise. Images (blueprint sheets, photos) go in as `input_image` items, so the deployment must be a vision-capable
model. This path is documented, not exercised by the test suite.

---

## 11. Security notes

- The OpenAI key lives in Key Vault and reaches the process as an environment variable; it is never written to the
  share while `KIN_SETTINGS_LOCK=1`. The UI shows only a masked form (`sk-…abcd`).
- TLS terminates at the Container Apps ingress with a managed certificate; `allowInsecure=false` redirects http.
- Container App secrets (access code, client secrets) are encrypted at rest and never returned by the API.
- The image runs as root inside a rootless-by-default sandbox (Container Apps); the share is mounted `0777` because
  SMB has no POSIX owners. If you need a non-root process, add a user in the Dockerfile and `uid=`/`gid=` in the mount.
- Session ids are validated (`[A-Za-z0-9._-]{1,120}`), file paths are resolved inside the session folder, archives are
  path-checked and size-capped before extraction, uploads are typed.
- Log Analytics receives the run narration; do not photograph secrets.

---

## 12. Checklist

- [ ] `az login`, subscription selected, permission to create app registrations (or an admin hands you the client id/secret)
- [ ] `OPENAI_API_KEY` exported (or in `./.env`)
- [ ] `deploy/azure/deploy.sh -g <rg> -l <region> --auth easyauth --admin <you>`
- [ ] Open the URL, sign in, check `/api/health` shows `llm.ready: true`, `auth: easyauth`, `settings_locked: true`
- [ ] Entra → Enterprise app → *Assignment required* (if the tenant is bigger than your team)
- [ ] Custom domain (optional) + add its callback to the app registration
- [ ] GitHub: deployer identity, federated credential, secrets/variables → push to `main`
- [ ] A share snapshot schedule, and `kin archive` of anything you would hate to lose
