# Hand-off notes — what to try, what to expect, what is rough

## Try this first

0. **Windows setup** (PowerShell, from the repo folder): `py -3.11 -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -e ".[dev]"`, install OpenSCAD (`winget install OpenSCAD.OpenSCAD`; the default install folder is found automatically, or set `KIN_OPENSCAD_BIN`), then `cd web; npm install; npm run build; cd ..`.
1. **Run the tests** (no model needed): `pip install -e ".[dev]" && pytest -q`. About four minutes; all green means OpenSCAD, the geometry stack, the measurement core, the agent runtime (scripted provider) and the web API work on your machine.
2. **Start the app**: `(cd web && npm install && npm run build)` once, then `kin serve` and open http://localhost:8000. The header pill says which model provider is active. Click **Settings**, paste your OpenAI API key, tick "remember on this server" — it is written to `.env`, never leaves the machine except to OpenAI.
3. **Walk the demo without a key**: Settings → *Demo mode*. The scripted designer builds the bottle handle from the template so every screen (guide, 3D, sheets, checks, sliders, export) can be seen in a minute.
4. **The loop from a typed spec**, on the CLI:
   ```bash
   S=$(kin new --spec eval/specs/bottle_handle.yaml --name bottle_handle)
   kin design "$S"                 # gpt-6-astra, effort high, budget 8, 2 critic rounds
   kin export "$S"
   ```
   `kin design "$S" --provider fake` runs the same thing with the scripted designer.

## The photo flow with a real object (the hero demo)

1. Print the calibration sheet (header button, or `kin sheet -o sheet.pdf`) at 100%; the 100 mm bar is the check.
2. Home → **Photograph what broke**: two or three photos (whole object, the break close up, the mating feature pressed onto the sheet and shot straight down), one sentence, **Analyze photos**. The session opens on its guide.
3. **Step 2 — Photos & answers**: the capture plan lists one shot per dimension with a *Take / upload* slot (on a phone this opens the camera); each upload is graded and a bad one says why. Answer the numeric questions with a ruler; numbers become confirmed dimensions.
4. **Step 3 — Confirm the fit**: every interface dimension with its status. Type a measured value to lock it, or leave it estimated and print the coupon later. Choose Quick / Standard / Thorough and **Design this part**.
5. **Step 4 — Design & verify**: live progress (iteration k / budget, step, elapsed, the tool the model is using, the last failing checks); the 3D view and sheets refresh after every iteration; a question from the designer appears right here with its options.
6. **Step 5 — Review**: pass/fail per check, the critic's verdict, the designer's narration; ask for a change in plain words, or **Looks right — export**. Or open **Customize** (right pane): sliders for every parameter with the measured value and tolerance band, a live draft in the 3D view, presets, undo; **Apply & verify** re-runs the checks.
7. **Step 6 — Print**: STL / 3MF / bundle downloads and the print card. If a fit dimension was never confirmed the guide says to print `coupon.stl` first.

The Timeline tab (left pane) is the full event log; the right pane keeps the engineer's view (checks, params, code, spec, photos).

## The capture loop and the graphs (new)

- After intake the guide shows **Round 1**: photo requests (each with a camera slot; the upload is measured on the calibration sheet and the value attached to the dimension), ruler readings, and choices. "Check what's still missing" saves the readings and asks the capture agent for the next round; when every fit dimension is known well enough the session moves to *Confirm the fit* by itself. "Design anyway" skips ahead (the coupon still confirms the fit later).
- Mid-design, the designer's `ask_user` can carry `photos` — the question card then has camera slots; the photos are measured and the resume message tells the model the new values.
- The right pane's **Graph** tab shows the session flow, the live iteration pipeline (nodes light up as they run; the blue path is the critical path; the footer says how much ran in parallel), the intake/capture graph and the export graph. The centre pane's **Evidence** tab draws where every dimension's value comes from.
- Standards: `kintsugi/spec/standards.py` is a small knowledge base (bottle neck finishes, pipe ODs, shafts, metric fasteners, batteries, extrusions, bearings, bike parts…). Keywords in the sentence or in intake's object description attach a `standard:<id>` estimate (confidence 0.4–0.85, always below a real measurement). Extend it freely; entries are plain data.
- The runtime is `kintsugi/graph/core.py` (about 300 lines): `Node(name, fn, inputs, outputs, kind, when, optional, after, est_s, ask)`, `Graph(name, nodes).run(state)` → `RunTrace`. Pipelines are in `kintsugi/graph/pipelines.py`, the session flow in `kintsugi/graph/flow.py`. Tests: `tests/test_graph.py`, `tests/test_capture_loop.py`.

## The design system (and the `/impeccable` skill)

- `DESIGN.md` (root) is the recorded visual system — the palette (navy #05142E ink, #155DD3 the one action colour, #6C9EF0 dimension blue, #BED4F9 tolerance tint), both themes, the type ramp, spacing, components, do's and don'ts — with the machine-readable tokens in its frontmatter and `.impeccable/design.json`. `PRODUCT.md` holds the product truth the design serves. Tokens live in `web/src/styles.css` (`:root` and the dark block); every component reads them, including the 3D viewer.
- Fonts are bundled (`@fontsource/*`, latin subsets) so the app renders the same with no internet. Icons are one SVG family in `web/src/icons.tsx`.
- On a phone the session shows one pane at a time, switched from the bar at the bottom (Guide · 3D & sheets · Details); the stage bar scrolls.
- [Impeccable](https://github.com/pbakaus/impeccable) is vendored as a project skill (`.agent/skills/impeccable`, agents in `.agent/agents`, the design-detector hook in `.agent/settings.json`). In the coding assistant: `/impeccable audit web`, `/impeccable polish the settings modal`, `/impeccable critique home`. The launcher downloads its engine binary once on first run (Windows: `scripts/impeccable.cmd`). The mechanical detector is clean on `web/src` except one advisory for the blueprint grid, which is the drafting-sheet ground and deliberate.

## The customizer (Customize tab)

- Backend: `kintsugi/scad/customizer.py` (`customizer_model()` — parameters with units/kinds/labels/gating, spec bindings from the `// Spec dims:` header or name+value matching, derived values with formulas, top-level asserts), `kintsugi/scad/preview.py` (`PreviewEngine`: one compile per session, the newest request kills and supersedes older ones, `preview/preview.stl` replaced atomically, draft `$fn` 32), `compile_scad(..., cancel=Event)`.
- API: `GET /customizer` (the model + presets + verified values + last preview), `POST /preview {values, render_target, quality}` (never touches part.scad), `GET/PUT/DELETE /presets[/name]` (stored as `part.json` in OpenSCAD's parameter-set format), `POST /params {values, update_spec}` (Apply & verify; a bound interface dimension moves the spec target and adds a `user_stated` estimate).
- Web: `web/src/customizer/` — `context.tsx` (edits/undo/redo reducer, debounced latest-wins previews, adaptive facets and pause, apply, presets), `Slider.tsx` (custom rail with tolerance band and marks), `controls.tsx`, `Customizer.tsx`; the 3D view (`components/StlViewer.tsx`) draws the draft, ghosts the verified mesh, and labels the overall dimensions on the model.
- Tests: `tests/test_customizer.py` (parser, bindings, presets, the preview engine's supersession, the API round trip including the spec update). Playwright walkthrough of the tab lives in the session notes, not the repo.
- Rough edges: previews of BOSL2-heavy parts (threads, fluted knobs) take 5–10 s on OpenSCAD 2021.01 — the panel pauses auto-preview above 5 s and offers a button; a Manifold-enabled nightly makes them instant. Dimension lines are the bounding box only (no per-feature callouts).

## What the designer knows about OpenSCAD

- `kintsugi/agent/knowledge/guides/*.md` — seven guides written for the shipped toolchain (OpenSCAD 2021.01 + BOSL2 2.0.759): every ```scad block is compiled by `tests/test_scad_knowledge.py`, so a guide cannot drift from what actually runs. Edit them freely; a broken example fails the suite.
- `openscad_builtins.json` — the language reference (74 entries: every builtin, the statements, special variables, what is *not* in 2021.01); `bosl2_index()` parses the vendored library's doc comments (980 entries) at first use.
- The model sees a compact "OpenSCAD essentials" block in its system prompt and has the `scad_guide` / `scad_docs` tools; the prompt tells it to read `patterns` before a new part class and to look up any BOSL2 call before using it. People get the same through `kin docs …`, `kin guide …`, `/api/docs?q=…` and the *Reference* button in the Code tab.

## Model provider

- Default: OpenAI Responses API, `gpt-6-astra` for the designer, critic and intake, reasoning effort `high`. `gpt-6-sol` for the critic/intake is ~5× cheaper and fine on simple parts; set it in Settings → *Models & reasoning effort*.
- Each tool step is chained with `previous_response_id` (`store=true`), so a run uploads every blueprint sheet once. `KIN_OPENAI_STATELESS=1` resends the whole transcript with `store=false` and encrypted reasoning (for zero-retention orgs); the loop also falls back to it automatically if the API rejects storing.
- Cost is accounted per run from the usage numbers (`usage` event, session meta `cost_usd`); prices are in `kintsugi/agent/llm.py:PRICES` — check them against the current price list.
- The live OpenAI path was verified through the official SDK against a mock transport (request shape, chaining, image tool outputs, JSON mode, truncation nudge) — a real end-to-end run with a key is the first thing to do on your machine. The Agent provider (`pip install ".[agent]"`, `KIN_PROVIDER=agent`) is the path the A/B study in `eval/reports` was run on.

## What the numbers mean

- `checks.json` / the Checks tab: every hard check is numeric and measured on the exported mesh. Interface dims show `expected = target ± clearance`.
- Wall thickness is sampled by ray casting (1500 points): `p05` is the hard check; `min` is a soft check and is often a convex-corner artifact.
- Interference is a boolean intersection with the crude context proxies you wrote in the spec; 0.05 mm³ is the pass limit unless `allow_contact` is set.

## Known rough edges

- The designer's shell is confined to its session directory and a blocklist (no package installs, no network tools), but it is still a shell; keep sessions on a machine you trust. Anything reachable from the internet should run with `KIN_AUTH=token` or `easyauth` (see *Deploying* below) — `none` is for a laptop or a LAN.
- OpenSCAD 2021.01 is slow on BOSL2-heavy models (CGAL). A Manifold-enabled nightly (`KIN_OPENSCAD_BIN`) is 10–50× faster; the templates avoid post-2021 syntax.
- Section recipes need a height where the feature exists (`at_z`); a spec written at the wrong height reads "no hole found". The intake prompt knows this but check the draft.
- The intake prompt has only been exercised on rendered scenes and the scripted provider here (no real photos in the build environment). Shiny or transparent objects will need the neck-on-sheet trick and a manual confirmation; expect to correct a number or two in step 3.
- The critic occasionally asks for changes the spec does not justify; the designer is told it may push back in its narration.
- Reconstruction from many photos and the printed 3D jig (approaches C/D in the design doc) are not built; the sheet + reference-object paths are.

## Deploying (Azure, Docker)

- `docs/DEPLOY-AZURE.md` is the whole story: the service stack (Container Apps · Azure Files · Container Registry · Key Vault · Log Analytics · Easy Auth), every environment variable per piece, costs, operations, troubleshooting. `deploy/azure/deploy.sh -g <rg> --auth easyauth --admin <you>` does it end to end from a laptop with `az`; `deploy/azure/main.bicep` + `app.bicep` are the declarative form; `.github/workflows/azure.yml` ships every push to `main`; `deploy/azure/appservice.sh` is the ≈ $55/month App Service variant; `deploy/docker-compose.yml` runs the same image anywhere.
- Auth (`kintsugi/server/auth.py`): `KIN_AUTH=none|token|easyauth`. Token mode = `KIN_ACCESS_TOKEN` + an HMAC cookie; easyauth reads the `X-MS-CLIENT-PRINCIPAL-*` headers Azure sets and scopes sessions to their `owner` (`KIN_ADMIN_USERS` see all). `KIN_SETTINGS_LOCK=1` makes `/api/settings` read-only. The UI gate lives in `web/src/auth.tsx`.
- Data: `KIN_DATA_DIR` (container: `/data`) holds `sessions/` and the settings `.env`; `KIN_SESSION_GIT=0` drops the per-session git history for slow shares.
- Archives (`kintsugi/session/archive.py`): `GET /api/sessions/{id}/archive` ↔ `POST /api/sessions/import`, `kin archive` / `kin import`, manifest + file hashes, zip-slip and size checks; schemas in `docs/schemas/` (regenerate with `kin schema … -o`), served at `/api/schemas/…`. This is also the backup/migration path.
- Not done here: a real deployment (no Azure subscription in the build environment). The Bicep compiles cleanly with the Bicep CLI and the scripts are syntax-checked; the first `deploy.sh` run is the test.
- `docs/REVIEW.md` is the review record: the deployment journeys walked through the code (what each turned up and what was fixed — scoping on `/stop`, import off the event loop, unicode archive names, non-ASCII codes, login throttling, SSE back-off and auth probe, stale-run reconciliation at startup, the hash route through platform sign-in).

## The workspace (resizable panes, hover linking, no tooltips)

- Desktop: the guide and details columns resize from the gutter between panes (`web/src/panes/Resizer.tsx`); the pill on the line folds a pane away; double-click resets; widths persist per browser.
- Pointing at a check (Checks tab), a fit row (guide), a bound slider (Customize) or a capture chip names its dimension (`web/src/hover.ts`); the 3D view draws the section plane it was measured on and matching rows light up elsewhere.
- The interface has no `title=` tooltips: labels say what controls do, disabled controls carry a dim line saying why, and compact elements (iteration chips, presets, binding lines, photo grades, tool calls) open a hover card. `DESIGN.md` records the patterns.

## Brand

- `docs/brand/` — the mark (a ring cracked on a diagonal, mended with a gold seam), the wordmark as outlines, lockups, the icon set the app serves from `web/public/` (favicon, PWA icons + manifest, Open Graph image), the fonts and `kintsugi-brand.css`, plus `index.html` (the usage sheet). All generated by `scripts/brand_assets.py` (fontTools + Playwright). The deck uses the mark on the title and closing slides and the brand palette throughout (`docs/submission/pitch-deck-build.js`, rebuilt).

## Where things are

- Session workspaces: `<KIN_DATA_DIR>/sessions/<id>/` (spec.yaml, part.scad, part.json, intake.json, iterations/, sheets/, checks.json, critic/, export/, events.jsonl, history.json, a git repo).
- Prompts: `kintsugi/agent/prompts/{designer,critic,intake}.md`. Provider facade: `kintsugi/agent/llm.py`; tools: `kintsugi/agent/tools.py`; scripted provider: `kintsugi/agent/fake.py`.
- Recipes the checker understands: `kintsugi/spec/model.py` (MeasureRecipe docstring).
- Templates: `templates/*.scad`, their specs `eval/specs/*.yaml`.
- A/B evaluation: `eval/ab_eval.py`, report `eval/reports/ab_templates.md`.
- Web UI: `web/src` (guide: `panes/GuidePane.tsx`, settings: `llm.tsx`, sign-in gate: `auth.tsx`); `npm run build` writes `web/dist`, which the API serves.
- Deployment: `deploy/azure/` (bicep, scripts), `docs/DEPLOY-AZURE.md`, `.github/workflows/azure.yml`, `Dockerfile`, `.env.example` (every variable).
