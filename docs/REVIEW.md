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

## After the judge (2026-09-27)

An impartial judge agent graded the repo as a hackathon entry (43/60, top 5–8 of ~40 as it stood). What it found
that could be fixed from here was fixed in the same day; what needs the owner is listed in `HANDOFF.md`.

- **Demo mode now shows the loop and tells the truth.** The scripted designer reads the spec, picks the vetted
  template for that part class, and — for the bottle handle — first writes a plausible-but-wrong version (a 60 mm
  loop, 127 mm overall against the 110 mm envelope), reads the check table that catches it, narrows the loop and
  passes: iteration 1 red, iteration 2 green, in ~10 s. Other template parts go straight through. A spec with no
  template (the A/B references) gets an honest message, the nearest template so the checks show the gap, and no
  false "all hard checks pass" — the guide explains why the run ended. The example picker leads with the bottle
  handle and groups the A/B references separately with a hint in demo mode.
- **The stage bar follows the newest iteration**: a failing apply after an export drops the session back to Design
  instead of leaving "Print — bundle ready" up.
- **Rough edges**: the print card's parameter table renders as a table; the mating-object proxy no longer floats over
  the empty viewer; "read the ring height of the ring height" is gone; a typed reading that is more than 2× off what
  the spec expects (or looks like inches) asks before it becomes "confirmed"; clicking a check pins its section plane
  (touch users get it too).
- **Guardrails for a shared box**: `KIN_MAX_COST_USD` caps what one run may spend (status `cost_capped`, a timeline
  event and a guide banner), `KIN_RATE_PER_MIN` limits heavy calls per client, `KIN_MAX_COMPILES` bounds OpenSCAD
  processes across all sessions (previews queue and cancel each other). All three are in the Bicep and `.env.example`.
- **Claims match the files**: the critic probe is stated as 2 of the 3 drawing-only defects (two variants also
  tripped a footprint check); the convergence claim is the four runs on disk (1, 1, 1, 7); the A/B caveats sit next to
  the headline; the measurement wording says homography < 0.1 mm and diameters within 0.5 mm, on synthetic photos.

## First run on the Windows dev box (2026-10-11)

The hand-off's step 1, walked on the owner's machine (Windows 11, Python 3.13 from the `py` launcher, Node 24, a fresh
portable OpenSCAD 2021.01 under `X:\Tools\OpenSCAD`): `scripts/bootstrap.ps1` → `kin serve` → `scripts/walk.py`,
reading every screenshot. Everything the cloud sandbox (Linux, UTF-8 locale) could not show turned up here.

- **Found: bootstrap said "Ready." with nothing installed.** PowerShell names are case-insensitive, so the flag
  `$py = [bool]$Py` overwrote the Python command with `True`; `venv` then failed as "the term 'True' is not
  recognized", which `Run` did not notice because it only looked at native exit codes. → the flag is `$havePy`, `Run`
  fails on any PowerShell error that is not native stderr, and the final import check throws instead of printing an
  empty "ok".
- **Found: a copied `.env` switched off OpenSCAD discovery and session isolation.** `.env.example` carried
  `KIN_OPENSCAD_BIN=openscad`, `KIN_DATA_DIR=.` and `KIN_SESSIONS_DIR=./sessions` as live values; the env var beats
  every other lookup, so the portable build beside the checkout was never found (and the toolchain tests skipped as
  "openscad not installed"), and `walk.py`'s throwaway data directory still wrote its sessions into the repo's
  `sessions/` — the home page of the next walk listed the previous walk's parts. → those three are commented out
  (they restate the defaults); the walk's home page now shows "No parts yet".
- **Found: on Windows the designer never saw its own check table.** Path `read_text`/`write_text` and text-mode
  subprocesses used the locale code page (cp1252). `iterations/iter_NN/summary.txt` contains `≥`, so writing it raised
  `UnicodeEncodeError` inside the `iterate` tool: the model got an error instead of the check results. In demo mode
  this showed as iteration 2 green in the check table while the scripted designer said "a check still fails" and the
  run ended `stopped`; with GPT-6 every iteration would have been blind. Customize → *Apply & verify* was a 500 for the
  same reason. → every such call (66, in `kintsugi/`, `eval/`) names `encoding="utf-8"`; subprocess output (Git Bash,
  OpenSCAD) decodes as UTF-8 with `errors="replace"`. The prompts and knowledge base were already read as UTF-8.
- **Found: the live preview URL had a backslash** (`files/preview%5Cpreview.stl`) — `preview.py` built it with
  `str(relative_path)`. → `.as_posix()`. Archives already did.
- **Found: demo mode claimed money and a model.** `KIN_DESIGNER_MODEL=gpt-6-astra` from `.env` overrode the fake
  provider's own label, so the scripted run said "run started · gpt-6-astra", "8 model calls · $0.16" and
  "$0.16 spent" in the top bar — the placeholder token counts priced at GPT-6 rates. → the fake provider ignores the
  `KIN_*_MODEL` settings; the timeline says "run started · scripted demo" and "8 scripted steps · no model, no cost";
  the top bar shows no spend.
- **Found: choosing another example kept the first example's name** — the A/B cabinet plug became a session called
  "bottle handle". → the name follows the picked example until someone types their own.
- Environment, not code: Playwright's downloader stalls on this network (30 s socket timeouts on every attempt while
  curl pulls the same file at 12 MB/s; IPv6 is broken here, but preferring IPv4 did not cure it). The four archives it
  lists in `playwright install --dry-run chromium` were fetched with curl into `.cache\ms-playwright` with their
  `INSTALLATION_COMPLETE` markers. Python reaches `api.openai.com` over IPv4 directly, so the OpenAI path is not
  affected. Ruff 0.17 widened its default rules; `pyproject.toml` now pins the four families the code was written
  against. A test that spawned the CLI with only `PATH` failed on Windows (no `SYSTEMROOT` → Winsock cannot start);
  it now passes `SYSTEMROOT` too.

`walk.py` now also expects that demo mode shows no spend or model in the top bar and that picking an example renames
the part; every expectation holds, the server log has no errors, and the screenshots read as the journey should:
it 1 red → it 2 green with the footprint check named, the section plane on hover, the print card, the stage dropping
back after a bad apply, the honest stop on a reference spec, the phone layout.

## The first real GPT-6 attempt and the first Azure deploy (2026-10-12)

**The real run** (`kin new --spec eval/specs/bottle_handle.yaml`, `kin design … --budget 8 --critic-rounds 2` on
gpt-6-astra) never reached the model: the account has no prepaid balance, and the first `responses.create` came back
`429 insufficient_quota` ("You have no credits remaining"). Cost $0.00, 0 iterations. The Responses wire format (image
tool outputs, `previous_response_id`, reasoning effort, JSON mode) is still verified only against the mock transport;
it is the first thing to run once credits are added. The attempt still found three things:

- **Found: 28 s of silence before the error.** The SDK retries every 429 with back-off unless the server says not to;
  an empty balance never succeeds on retry. → an httpx response hook marks `insufficient_quota` responses
  `x-should-retry: false`; the same failure now surfaces in about 4 s.
- **Found: the guide hid it.** A run that dies before its first iteration leaves the stage at the spec, so the guide
  opened on *Confirm the fit* and the error banner (inside *Design & verify*) was never on screen; when it was, it said
  "see the timeline". → a failed run opens the design step, and the banner says what happened in the person's words
  for the errors people will actually meet (no credits, a rejected key, a model the account cannot use, rate limits),
  falling back to the first 160 characters of the message.
- **Found: a redeploy could leave a blank page.** `index.html` was served without `Cache-Control`, so browsers kept a
  stale shell pointing at hashed bundles the new image no longer has (seen locally: the old bundle survived a rebuild).
  → the shell is `no-cache`; `assets/*` are `immutable` (Starlette hands Windows paths with `\` to the check).

**The first deploy** (`deploy/azure/deploy.sh`, from Git Bash on Windows, budget shape: scale to zero, 1 vCPU / 2 GiB,
demo provider, no sign-in, per-run cap and rate limit) — every step of it had only ever been syntax-checked:

- `python3` is the Microsoft Store stub on Windows → the script picks the first of `python3`/`python`/`py` that runs.
- `--parameters "@/tmp/…"`: Git Bash converts arguments that *start* with `/`, not ones behind `@` → `cygpath -m`.
  The parameters file (it carries the key) is written under `TMPDIR` on the project drive and removed on exit.
- The Windows `az` runs its Python isolated, prints through cp1252 and crashed on `≈`/`→` in Bicep descriptions and on
  Vite's `✓` in the streamed build log (the build itself carried on and succeeded in Azure) → the Bicep files are
  ASCII; on Windows the image build is awaited with `--no-logs` and its status checked.
- `minReplicas: 1` was hard-coded (≈ $50/month idle at the default size) → `--min-replicas 0|1`, plus `--max-cost`,
  `--rate`, `--no-session-git` flags; the cost table and §3 *On a small budget* say what each costs.
- Container Apps rejected the SMB mount option `actimeo` (preflight validation) → removed.
- ACR Tasks timed out reaching Docker Hub once (transient; re-run). The Container Apps environment took about 55
  minutes to provision in a fresh subscription.
- `.dockerignore` now keeps `.env`, `.venv`, `.cache` and `scratch` out of the upload; the context sent was 8 MiB.

`scripts/walk.py --base https://kintsugi.orangecliff-df186167.eastus2.azurecontainerapps.io` holds every expectation on
the deployed app (desktop and phone, the honest stop, no page errors); the two sessions it made were deleted so the
shared list starts empty. `/api/health` reports OpenSCAD 2021.01, the demo provider and locked settings. A cold start
after scale-to-zero measured 33.8 s for the first page, 0.2 s after; the Devpost text and the deck say "about half a
minute" instead of "a moment".

**Claims checked against the files while writing the submission:** the video script said the critic "caught four of
five" — the report's headline is 2 of the 3 defects the numbers cannot see (the other two also trip a check), now said
that way; the README's "~1.6–1.7× faster per iteration" had no measurement behind it in the repo and was dropped; "every
Kintsugi part passed every check" became "passed its checks" (the A/B table records hard checks).
