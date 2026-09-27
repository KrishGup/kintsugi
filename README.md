<p align="left"><img src="docs/brand/png/kintsugi-lockup-tag@2x.png" alt="Kintsugi — Photograph what broke. Print what fits." width="420"></p>

# Kintsugi

**Photograph what broke. Print what fits.**

Kintsugi is an agent that turns photos of a broken object into a verified, parametric, 3D‑printable replacement part. It guides the photos, measures the mating geometry, writes a Part Spec, designs the part in OpenSCAD, checks its own drawings and mesh against the spec, has a second, code‑blind model review the drawings, closes the loop with a printed fit coupon, and exports an STL with a print card.

The same machinery is a general OpenSCAD design agent with a real verification loop: give it a spec with dimensions and it designs, measures, and fixes until the numbers and the drawings agree.

Built for OFFGRID (Hack47), September–October 2026.

## Why it works

- **A replacement part is defined by its interfaces.** Measure the few dimensions that mate with the object; design the body freely. That turns "3D‑scan the thing" into "measure a ring and a height".
- **The Part Spec is a contract.** Every dimension carries its evidence (estimates with source and confidence) and a *measure recipe* that tells the checker how to read it off the finished mesh. Verification is executable, not interpretive.
- **The agent checks its work like an engineer.** Blueprint sheets whose dimension lines are computed from the exported mesh, never from the code; numeric checks (walls, overhangs, interference against a proxy of the object); a fresh‑context critic that never sees the CAD code.
- **Output is parametric.** Every user‑facing dimension is a customizer slider. A near miss is a nudge, not a re‑run.

## What is in the box

| piece | what it does |
|---|---|
| `kintsugi/scad` | headless OpenSCAD compile with structured errors/echoes, cancellable for live previews; the customizer model (annotations → sliders with units, kinds, gated toggles, spec bindings, computed values, asserts), the latest‑wins preview engine, OpenSCAD‑compatible parameter‑set presets |
| `kintsugi/checks` | mesh measurements: sections, robust circle fits, hole patterns, notch (clip) fits, wall thickness by ray casting, overhang/bed/orientation scoring, boolean interference against context proxies |
| `kintsugi/render` | software z‑buffer renderer for 7 orthographic/iso views with hidden lines, hatched sections, mesh‑derived dimension lines, composed blueprint sheets |
| `kintsugi/spec` | the Part Spec (pydantic): interfaces, requirements, context proxies, print settings, evidence fusion and confirmation gates; the evidence graph (dimensions ↔ photos ↔ estimates ↔ questions ↔ checks) that decides what is missing and plans the cheapest next round; a knowledge base of standard interfaces (bottle finishes, pipe ODs, shafts, fasteners, batteries, rails…) that seeds estimates from the object's identity |
| `kintsugi/graph` | the graph runtime: typed dataflow graphs whose nodes are algorithms, model calls or people; event‑driven scheduling with parallel branches, guards, ordering dependencies, human nodes that suspend a run, per‑run traces with the critical path; the iteration and export pipelines and the session flow are defined here |
| `kintsugi/agent` | the designer (a GPT‑6 tool loop on the OpenAI Responses API, sandboxed file tools + `iterate`/`finish`/`ask_user` with photo requests), the code‑blind critic, photo intake, the capture loop (automatic sheet measurement, evidence‑driven follow‑up rounds written by a capture agent), iteration policy (budget/oscillation/strategy switch), export bundle; a scripted `fake` provider runs the whole loop without a key |
| `kintsugi/agent/knowledge` | what the designer knows about OpenSCAD: seven curated guides for OpenSCAD 2021.01 as shipped (language essentials, shapes and rounding, the vendored BOSL2, design for FDM, Kintsugi's conventions, compiling patterns for repair parts, errors) — every example is compiled by the test‑suite — plus a searchable reference of all builtins and the 980 BOSL2 modules/functions parsed from the library's own doc comments; exposed to the model as `scad_guide` / `scad_docs`, to people as `kin docs` / `kin guide` and the Code tab's *Reference* search |
| `kintsugi/measure` | printable ArUco calibration sheet, marker detection + homography rectification (homography error under 0.1 mm, diameters within 0.5 mm, on synthetic photos to 35° tilt — real phone photos still to be exercised), circle/outline/rectangle measurement, coin/card reference scale, capture grading, synthetic photo generator |
| `kintsugi/server` + `web/` | FastAPI API with SSE event stream; React + three.js workspace: a six‑stage guide (intake → capture → confirm → design → review → print), chat/timeline, 3D viewer with on‑model dimensions and draft/verified ghosting, blueprint tabs, checks table, the parametric customizer, code pane, spec editor, photos/measure, model settings |
| `templates/` | seven vetted parametric templates (ring‑and‑loop handle, L bracket, snap clip, D‑shaft knob, hook, spacer/gasket, threaded cap), each with a spec it passes |
| `eval/` | benchmark specs and the A/B evaluation against human‑designed OpenSCAD repair parts |

## Quick start

Requirements: Python 3.11+, OpenSCAD (2021.01 works; a Manifold‑enabled nightly is faster), `xvfb-run` on headless Linux (only for OpenSCAD's own PNG renders), Node 22 for the web UI, and an `OPENAI_API_KEY` for the agent (GPT‑6 through the Responses API). Without a key, the `fake` provider runs the whole pipeline with a scripted designer.

```bash
git clone https://github.com/KrishGup/kintsugi && cd kintsugi
pip install -e ".[dev]"
sudo apt-get install -y openscad xvfb          # or your platform's equivalent
cp .env.example .env                          # set OPENAI_API_KEY (or paste it in the web app's Settings)

# 1. the toolchain, no model needed
kin compile templates/ring_loop_handle.scad -o /tmp/handle.stl
kin checks /tmp/handle.stl --spec eval/specs/bottle_handle.yaml
kin blueprint /tmp/handle.stl --spec eval/specs/bottle_handle.yaml -o /tmp/sheets --iteration 1

# 2. the loop, with the model
S=$(kin new --spec eval/specs/bottle_handle.yaml --name bottle_handle)
kin design "$S" --budget 8 --critic-rounds 2  # gpt-6-astra by default; --provider fake needs no key
kin export "$S"                               # STL/3MF/SCAD/blueprint.pdf/print_card.md/coupon.stl/bundle.zip

# 3. the web app
(cd web && npm install && npm run build)
kin serve --port 8000                         # open http://localhost:8000
```

`kin sheet -o calibration_sheet.pdf` prints the ArUco calibration sheet (print at 100%; the 100 mm bar is the check).

On Windows (PowerShell):

```powershell
py -3.11 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
winget install OpenSCAD.OpenSCAD            # or set KIN_OPENSCAD_BIN to your openscad.exe
cd web; npm install; npm run build; cd ..
kin serve                                    # then http://localhost:8000 → Settings → paste the OpenAI key
```

`xvfb` is not needed on Windows or macOS. Git Bash is picked up automatically for the designer's shell tool when present; otherwise it uses the platform shell.

## Deploy it

One container holds the API, the built UI and the OpenSCAD toolchain; everything it writes goes under `/data`.

```bash
docker compose -f deploy/docker-compose.yml up -d --build      # any Docker host; /data on a volume
deploy/azure/deploy.sh -g kintsugi-rg -l eastus2 --auth easyauth --admin you@example.com   # Azure, end to end
```

**Azure** — `docs/DEPLOY-AZURE.md` is the full stack (Container Apps, Azure Files, Container Registry, Key Vault, Log Analytics, Easy Auth) with every environment variable per piece, the Bicep in `deploy/azure/`, a GitHub Actions workflow that ships each push, an App Service budget variant, costs and troubleshooting.

**Sign-in** — `KIN_AUTH=none` (a personal box), `token` (one shared access code, asked once, signed cookie), or `easyauth` (Microsoft / GitHub / Google through the platform; sessions belong to the person who made them, `KIN_ADMIN_USERS` see all). `KIN_SETTINGS_LOCK=1` makes the Settings dialog read-only so a deployment's key never lands in a file.

**Portable state** — every session exports as one `.zip` (Export → *Download session archive*, `GET /api/sessions/{id}/archive`, `kin archive`) with a manifest, and imports on any other Kintsugi (Home → *Import*, `POST /api/sessions/import`, `kin import`). The schemas of the manifest and of `spec.yaml` are in `docs/schemas/` and served at `/api/schemas/{session-archive,part-spec}`.

## The flow

1. **Intake** — photos + one sentence → object, broken part, its interfaces, a draft spec; recognised standard sizes become first estimates.
2. **Capture rounds** — the evidence graph lists what is still a guess; the capture agent writes the round: one photo per mating feature on the calibration sheet, a ruler reading for each height, a coupon when only the fit is in doubt. Uploads are graded and measured automatically; the next round asks only for what is still missing. The designer can ask for a photo the same way mid‑run.
3. **Measurement** — rectify to a metric top‑down image of the sheet plane; fit circles and outlines; attach estimates to spec dimensions with a confidence; independent sources that agree confirm a dimension, sources that disagree trigger a ruler request.
4. **Spec review** — the editable spec card; interface dimensions must be *confirmed* before the export loses its "fit unconfirmed" label.
5. **Design loop** — write `part.scad` → compile → checks → blueprint → (critic) → revise, with an iteration budget, oscillation detection and a strategy switch (CSG → template → profile).
6. **Review** — 3D viewer, sheets, checks, the customizer, code, iteration timeline with branching.
7. **Fit coupon** — the mating feature only, in three clearances; the result locks the clearance.
8. **Export** — oriented STL and 3MF, customizer‑ready `.scad`, blueprint PDF, print card, spec, session log.

## Graph engineering

Every stage runs as a typed dataflow graph (`kintsugi/graph`): a node declares the state keys it needs and the keys it produces, edges follow from that, and the runtime starts a node the moment its inputs exist. Independent nodes run in parallel (blocking algorithms in threads, model calls as coroutines), `after=` gives ordering without data, guards skip nodes, optional nodes may fail without stopping the run, and a **human node** suspends the run with a request — the graph resumes when the answer is in the state. Each run leaves a trace with per‑node timing, the critical path and the serial‑vs‑wall time, which the UI draws live in the *Graph* tab.

- **Iteration**: `params ∥ compile → mesh → checks ∥ views ∥ context → sections ∥ assembly → compose` — the sheets no longer wait for the checks to finish before rendering; ~1.6–1.7× faster per iteration on two cores, more on a desktop.
- **Intake & capture**: `grade ∥ standards → vision → spec → auto‑measure → evidence → follow‑up → capture (you)`, repeated per round.
- **Export**: coupon compile ∥ 3MF ∥ blueprint PDF ∥ print card ∥ session log → zip.
- **Session flow**: the stages as a state graph with guarded transitions (`kintsugi/graph/flow.py`); the stepper and the "open moves" come from it, and the loops (another capture round, a designer's photo request, a coupon result) are explicit edges.

The **evidence graph** (`kintsugi/spec/evidence.py`) is the data structure the capture loop reasons over: dimension nodes with status and confidence, estimate nodes weighted by source trust, photo/question/standard/request nodes that target dimensions, check nodes that verify them on the mesh. `missing()` ranks what still needs evidence; `plan_round()` batches it into the fewest user actions; `readiness()` decides when designing is safe. The *Evidence* tab draws it.

## Customize like a parametric designer

The *Customize* tab is what MakerWorld's parametric model maker or Thingiverse's customizer give a downloaded model — sliders, number boxes with units, switches, option cards, presets, a live 3D preview — with one difference that only a photo‑measured part can offer: **every slider knows where its number came from.**

- **Controls from the code.** The parameter block of `part.scad` (`neck_id = 43.2; // [20:0.1:90]  description`) becomes a slider with a typed box (`45`, `1.75 in`, `1 3/4"` all work), ± steppers and a unit; a boolean becomes a switch whose dependent parameters (`scallops` → `scallop_depth`) fold underneath; a `// [a, b, c]` choice becomes option cards; sections become tabs. A mm/in toggle converts the display; the model stays metric.
- **Measured dimensions carry their evidence.** A slider bound to a spec dimension shows *measured 43.2 ± 0.3 · from caliper +1 · sliding fit, +0.25 clearance*, draws the tolerance band on the rail, and warns when you leave it. Requirement dimensions show their floor or ceiling. Applying a changed fit dimension moves the spec target with it (with a `user_stated` estimate in the evidence graph) so the checks verify the value you chose instead of fighting it.
- **Live draft, verified on apply.** Each change compiles a draft with `-D` overrides (nothing written to `part.scad`); a burst of drags kills the stale compile and keeps only the newest one; the 3D view shows the draft with the verified mesh ghosted behind it, overall dimensions drawn on the model, and the *Computed* panel reads the model's `echo()` values live — `overall_length 118.8 mm ✗ ≤ 110` turns red before anything is applied. Facets adapt: full quality while previews are quick, draft `$fn` once a full preview proves slow; a slow model pauses auto‑preview and offers a button instead. *Apply & verify* rewrites the parameters and runs the real iteration (compile → checks → blueprints).
- **Presets, undo, portability.** Named presets are stored as `part.json` next to `part.scad` in OpenSCAD's own parameter‑set format (the desktop customizer opens them) and ride along in the export bundle; undo/redo (Ctrl+Z) covers every change; the *⋯* menu copies the equivalent `openscad -D …` command line and downloads the draft STL.
- **Assertions are messages.** A top‑level `assert(cond, "scallops too deep for the loop height")` fails a preview with that sentence next to the slider that caused it.

The designer is told to write for this panel (`scad_guide("kintsugi")`): ranges and descriptions on every number, units in parentheses, `[Interface]` first, toggles with prefixed dependents, a `// Spec dims: … <- …` header binding sliders to spec dimensions, echoed derived values named like the spec's, and the iteration policy nags it about numbers without ranges.

## Design

The mark is a ring — the part — cracked on a diagonal and mended with a gold seam; the brand kit (mark, wordmark as outlines, lockups, favicon and app icons, social image, the fonts, `kintsugi-brand.css` and a usage sheet) lives in `docs/brand/` and is regenerated by `scripts/brand_assets.py`.

The interface is a drafting sheet: fine blueprint grid, white panels with navy-tinted rules, one blue for every action, the two lighter blues for tolerance bands and ghosted geometry, measured values in tabular mono, tracked title-block labels. Light by default (a bench in daylight), a dark mode composed from the navy by system setting. `DESIGN.md` records the system with its tokens; `PRODUCT.md` records the product truth it serves. Fonts and icons ship with the app, so it looks the same off-grid. The [Impeccable](https://github.com/pbakaus/impeccable) design skill is vendored under `.agent/` (`/impeccable audit`, `polish`, `critique`, …).

## How the agent runs

The designer is a GPT‑6 tool loop on the OpenAI Responses API (`gpt-6-astra`, reasoning effort `high` by default) whose working directory is the session workspace. It has sandboxed file tools (`read_file`, `write_file`, `edit_file`, `list_files`, `run_command` — confined to the session directory, with the templates and BOSL2 readable) and five in‑process tools: `iterate` (compile + checks + blueprint; returns the check table and the sheets as images the model looks at), `list_templates`, `read_template`, `ask_user`, `finish`. Tool steps are chained server‑side with `previous_response_id`, so each blueprint image is uploaded once; `KIN_OPENAI_STATELESS=1` resends the transcript with encrypted reasoning instead. The designer also has `scad_guide(topic)` and `scad_docs(query)`: curated, compile‑tested guides and the full OpenSCAD + BOSL2 reference (`kintsugi/agent/knowledge`), so it looks up a module's arguments instead of guessing them. The critic is a separate single‑turn call with fresh context that receives the spec, the check table and the sheets — never the code — and returns a JSON verdict. Set `KIN_DESIGNER_MODEL` / `KIN_CRITIC_MODEL` / `KIN_VISION_MODEL` (or use the Settings dialog) to change models; `gpt-6-sol` is the fast, inexpensive option for the critic and intake. A `agent` provider (agent SDK, `pip install ".[agent]"`) and a scripted `fake` provider share the same interface.

Every iteration is a git commit in the session directory. The UI panels are views of the session's files; the event log (`events.jsonl`) drives the timeline.

## Evaluation

- `tests/` — the toolchain against known geometry (circle fits within 0.05 mm, wall thickness, interference volumes within 3 %), measurement against synthetic photos, every template against its spec, the session pipeline and export, the agent runtime with a scripted provider, the OpenAI wire format through the real SDK against a mock transport, the web API end to end, and the deployment surfaces. None of it needs a model key. The test suite is a regression net, not the proof: `docs/REVIEW.md` records the use cases walked through the code and the UI by hand, and `eval/reports/` the blind A/B study.
- `eval/ab_eval.py` — the A/B study: five human‑designed OpenSCAD repair parts from public repositories, a spec written from each one's own mating dimensions, the designer builds from the spec alone, both measured by the same checker and judged blind. Report in `eval/reports/`.

## Repository layout

```
kintsugi/            Python package (scad, checks, render, spec, agent, measure, session, server, cli)
templates/           vetted parametric parts with self‑checks
eval/                specs, references manifest, A/B runner, reports
tests/               pytest suite (no model required)
web/                 React + Vite UI (built into web/dist, served by the API)
vendor/BOSL2/        the BOSL2 library (BSD‑2), on OPENSCADPATH for every compile
deploy/              Dockerfile companions: docker-compose, Azure Bicep + scripts
docs/                design document, DEPLOY-AZURE.md, the JSON Schemas, submission material
```

## Disclosure

Kintsugi uses OpenSCAD (GPL‑2.0, invoked as a separate process), BOSL2 (BSD‑2, vendored), OpenCV, trimesh + manifold3d, shapely, FastAPI, React, three.js, Monaco, and OpenAI GPT‑6 models through the official `openai` Python SDK (Responses API). The A/B references are cloned at evaluation time from their authors' repositories and are not redistributed here.

## License

MIT for this repository's own code. See `vendor/BOSL2/LICENSE` for BOSL2.
