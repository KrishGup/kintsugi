# Review record — use cases walked through the code

The deployment surfaces (sign-in modes, per-user sessions, archives, the Azure stack) were reviewed by reading the
code against the situations a real deployment meets, not by counting tests. Each journey below names the code that
carries it and what the walk turned up. Fixes are in the same commit as this file.

## 1. First admin deploys with Microsoft sign-in

`deploy/azure/deploy.sh --auth easyauth --admin you@…` → `main.bicep` (infra) → `az acr build` → `app.bicep` →
Entra app registration with the real callback → auth config.

- **Found:** the Entra callback URL only exists after the app exists → the two-phase deploy is deliberate and the
  script is idempotent; documented in `DEPLOY-AZURE.md §3`.
- **Found:** the app registration's `sub` for a GitHub Actions deployer differs when a job uses a GitHub *environment*
  (`repo:…:environment:azure`) → the workflow no longer declares one; the doc gives the exact subject.
- **Found:** RBAC on a brand-new identity can lag the first Key Vault reference → re-run; documented as the first
  troubleshooting row.
- Signs in → `/.auth/login/aad` → back to the SPA. `auth.py:_easyauth_user` takes `preferred_username`/email
  lower-cased as the id; `KIN_ADMIN_USERS` is compared lower-cased. Sessions are stamped `owner` at creation
  (`create_session`) and on import.

## 2. Second person signs in, sees nothing, imports an archive

`list_sessions` filters by `auth.can_see`; `_session()` answers 404 (not 403) for someone else's session so ids
leak nothing. Import stamps the importer as owner and mints a fresh id if the original is taken.

- **Found:** `POST /sessions/{sid}/stop` checked `RUNS` *before* scoping — a signed-in stranger who knew an id could
  cancel another person's run. → scope first.
- **Found:** `import_archive` ran on the event loop; a 300 MB zip would stall every event stream for seconds.
  → `asyncio.to_thread`, and the upload is read in 1 MB chunks and refused the moment it passes `KIN_MAX_IMPORT_MB`
  instead of being buffered whole first.
- **Found:** archive path safety was ASCII-only, so a photo named `Foto ñ (1).jpg` (phones do this) would make its
  own archive un-importable. → any unicode name is accepted; control characters, separators, Windows-illegal
  characters, `.`/`..`, trailing dots/spaces and >200-char segments are refused. Upload names are now normalised
  to `[A-Za-z0-9._-]` at upload time as well, so file URLs never need escaping.
- The schemas moved to the public path list (`/api/schemas/`) — they are documentation, and the doc links them.

## 3. A phone on the road, token mode

Gate → `POST /api/auth/login` → HttpOnly/SameSite=Lax/Secure cookie (Secure follows `X-Forwarded-Proto`, which
`kin serve` now trusts with `--proxy-headers`).

- **Found:** `hmac.compare_digest` on `str` raises on non-ASCII — a code (or a forged cookie) with an accent was a
  500 on every request. → bytes comparison, and `resolve()` failures are "not signed in", never an error page.
- **Found:** nothing slowed a guess loop against the shared code. → 8 wrong codes per client per 10 min, then a
  60 s cool-off (429 with `Retry-After`), a flat 400 ms on every miss; the gate explains the 429.
- The EventSource cannot see status codes: a lapsed cookie made it retry every 2 s forever, silently.
  → exponential back-off (2 → 30 s) and, after the second failure, a probe of `/api/auth/me` that opens the gate.
- Photos upload as multipart through the ingress; ACA has no small body cap; heartbeats every 15 s keep the stream
  under any idle timeout; `POST …/run` returns 202 so no request outlives the 240 s ingress limit.

## 4. Sign-in lapses mid-session (Easy Auth's 8 h cookie)

`AllowAnonymous` at the platform means the shell still loads; the app answers 401 JSON; `api.ts` fires
`kin:unauthorized`; the gate shows the platform link.

- **Found:** the gate sent people back to `/` after sign-in, losing the `#/s/<id>` route. → `loginHere()` puts the
  current path+hash into `post_login_redirect_uri` (Easy Auth keeps fragments: `preserveUrlFragmentsForLogins`).

## 5. The server restarts during a run (image roll, crash, scale event)

A run is an `asyncio.Task`; its session was left saying `running` with nothing behind it — the top bar showed a
run nobody could stop, and the archive endpoint refused (409) forever.

- → a lifespan hook marks every `running` session `stopped` with a `run_end` event (`reason: the server restarted
  during the run`); `/stop` also repairs a stale `running` on demand; shutdown cancels live tasks.

## 6. Key rotation and locked settings

`KIN_SETTINGS_LOCK=1` → `/api/settings` POST is 403, the dialog is read-only with the configured models shown, the
provider pill and the home banner say "No model configured" instead of asking for a key. Rotation is a Key Vault
version + revision restart; the key never reaches `/data/.env`.

## 7. Archive round trip

`export_archive` skips `.git`, `preview/`, `bundle.zip`; the manifest hashes every file; import validates before
extracting, extracts into a temp dir, renames atomically, rewrites `session.json`, re-inits git (or not, under
`KIN_SESSION_GIT=0`), appends `imported`. A `running` status becomes `stopped` — a run cannot travel.

## 8. The workspace itself (hand-driven in a browser, desktop and phone, light and dark)

- Resizable panes: drag, keyboard, fold/unfold, double-click reset, persisted widths; phones keep the one-pane
  layout. **Found during the walk:** a folded (`display: none`) pane shifted its neighbours into the wrong grid
  tracks — every item now has an explicit `grid-column`; and the fold button was swallowing drags that started on it
  — the strip owns the whole gesture (press-and-move resizes, press-and-release on the button folds).
- Hover linking: pointing at a check draws its section plane on the model; the guide's fit rows, the customizer's
  bound sliders and the capture chips all point at the same dimension. **Found:** the plane's label sat off the
  right edge of the viewer for wide parts — it now sits on the plane's front edge.
- Tooltips: 112 `title=` attributes reduced to 5 (ellipsised text and an error detail). Everything else is a label,
  an inline hint or a hover card.

## Not exercised here

No Azure subscription and no Docker daemon exist in the build environment: the Bicep compiles cleanly with the
Bicep CLI, the scripts are syntax-checked and their parameter generation was run, the container's runtime layout
(`/data`, proxy headers, health path) is the one the app was run with locally — the first `deploy.sh` run is the
real test of the platform plumbing.
