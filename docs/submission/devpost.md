# Devpost submission — draft 2

Everything below maps to the HACK47: OFFGRID submission form (Project Name, Short Description, Problem Statement, Solution, Demo Link, Source Code, Demo Video, Tech Stack, Build Process) plus the standard Devpost story sections. Text in `[brackets]` is a placeholder to fill in before submitting. Numbers marked † were measured on the Agent-provider runs before the switch to OpenAI and must be re-run on GPT-6 (`eval/ab_eval.py`, `eval/critic_probe.py`) before submission; until then the form carries them with the † and the footnote below, or they are dropped.

---

## Project name

**Kintsugi**

## Tagline (Devpost "short description", ≤ 200 chars)

Pick one:

1. **Photograph what broke. Print what fits.** An agent that turns photos of a broken part into a verified, printable replacement — it measures, designs, checks its own drawings, and asks for the photo it still needs.
2. Snap a photo of the broken bit. Kintsugi measures it, designs the replacement in OpenSCAD, proves the fit on its own blueprints, and hands you an STL — with a second model auditing the drawings.
3. A repair agent with an engineer's habits: measure before you draw, check the drawing against the spec, print a fit coupon before the part.

(1 is the recommended one — it is the product's line everywhere else.)

## Problem statement

Things break at the one part that mattered: the handle, the clip, the knob, the cap. The object still works; the part that fits it does not exist any more. Replacement means shipping a whole new thing (or nothing, off-grid), and 3D printing — the obvious answer — stalls at the step nobody enjoys: measuring the mating geometry precisely enough and modelling a part that actually fits. "Ask an LLM for the OpenSCAD" produces plausible code and a part that is a millimetre or two out at the one dimension that has to fit, because the model never sees what it built.

## Solution

Kintsugi is an agent that behaves like a careful mechanical designer:

1. **Intake** — two or three phone photos and one sentence → what the object is, which part broke, which features it mates with, a draft Part Spec, and a capture plan. Standard sizes it recognises (a 63-415 bottle finish, a 3/4" pipe, an M5) become first estimates.
2. **Capture rounds** — an *evidence graph* knows which dimensions are still guesses. The capture agent asks for exactly the photos and ruler readings that resolve them ("press the neck opening-down on the calibration sheet, shoot straight down"). Each upload is graded and measured automatically on a printed ArUco sheet; readings become confirmed dimensions; the next round asks only for what is still missing. The designer can ask for a photo the same way mid-run.
3. **Design loop** — GPT-6 writes the OpenSCAD, compiles it, and every spec dimension is **measured on the exported mesh** — never trusted from the code. Blueprint sheets (views, sections, assembly with the mating object ghosted) carry dimension lines computed from the mesh, with pass/fail colours, and the model looks at them before its next change. Budget, oscillation detection and a strategy switch keep it converging.
4. **Code-blind critic** — a second, fresh-context model reviews the drawings and the check table without ever seeing the code, and sends the designer back when the numbers pass but the part is wrong (a hole through the load path, missing finger scallops).
5. **Customize** — every parameter of the finished part is a slider or a switch with a live 3D draft, like MakerWorld's parametric model maker — except that each fit dimension shows *where its number came from* (the photo, the ruler, the caliper, a recognised standard), draws its tolerance band on the slider, and the computed dimensions turn red against the spec's limits before anything is applied. *Apply & verify* re-runs the real checks.
6. **Fit coupon + export** — the mating feature alone at three clearances to print first; then an oriented STL/3MF, a customizer-ready `.scad` with presets in OpenSCAD's own format, a blueprint PDF and a print card that says *why* the settings are what they are.

**Status at submission (14 Oct 2026), stated plainly.** The GPT-6 path has completed one real run: the bottle handle from a typed spec, 2 iterations (the first did not compile, the second passes every hard check on the exported mesh), critic verdict *pass*, 21 model calls, $1.01 — the files are in `eval/reports/gpt6-first-run/`. The designer adapted the vetted ring-and-loop template for that part. No real phone photo has been through intake yet (the measurement numbers are on synthetic photos), and nothing has been printed yet. The hosted demo runs the scripted provider.

Everything runs as typed dataflow graphs: independent steps in parallel, people as first-class nodes, every run traced with its critical path.

## Demo link

https://kintsugi.orangecliff-df186167.eastus2.azurecontainerapps.io — hosted on Azure Container Apps, running in **demo mode**: a scripted designer with the real OpenSCAD compiles, mesh checks, blueprints and export, so it needs no key and costs nothing to try. Pick the bottle handle, *Create session*, *Design this part*: iteration 1 fails the footprint check, iteration 2 passes. It scales to zero when idle, so the first visit after a quiet spell takes about half a minute to wake; after that it answers at once.

Locally with your own key: `docker compose -f deploy/docker-compose.yml up -d --build` (builds the image locally) or the README's setup; Settings switches between OpenAI and demo mode.

## Source code

`https://github.com/KrishGup/kintsugi` `[create the repo and push before submitting]`

## Demo video

`[YouTube link, ≤ 3 minutes — see docs/submission/video-script.md]`

## Tech stack ("Built with")

OpenAI GPT-6 (gpt-6-astra for design, critic and vision; gpt-6-sol optional) via the **OpenAI Responses API** (function tools with image outputs, `previous_response_id` chaining, reasoning effort, JSON mode) · Python 3.11+ · OpenSCAD 2021 + BOSL2 · trimesh + manifold3d + shapely (mesh measurement) · OpenCV (ArUco calibration sheet, homography rectification, sub-pixel circle fitting) · NumPy software z-buffer renderer (hidden-line views, hatched sections, mesh-derived dimension lines) · FastAPI + SSE · React + Vite + three.js + Monaco · pydantic Part Spec · a home-grown dataflow-graph runtime · a use-case review record (`docs/REVIEW.md`) and a regression net that needs no model · Docker · Azure Container Apps (Bicep; the live demo deploys with one command; Easy Auth reviewed in code, not deployed)

## Build process (short version for the form)

Built solo during the OFFGRID window (local history from 25 September 2026; the repository was published at submission). Order of work: (1) the verification toolchain first — headless OpenSCAD compile, mesh checks, the blueprint renderer, the Part Spec with measurement recipes — all tested on known geometry before any model was involved; (2) the design loop with the code-blind critic and an iteration policy, validated on the bottle-handle benchmark and an A/B study against five human-designed OpenSCAD repair parts; (3) the measurement core (calibration sheet, rectification, circle/outline fitting) validated on synthetic photos with known ground truth; (4) the web workspace; (5) the port to the OpenAI Responses API with a scripted provider so the whole loop is testable without a key; (6) graph engineering: the dataflow runtime, the evidence graph and the capture loop. Every stage has a headless test; the UI was walked end to end in a headless browser after each change.

---

## Devpost story

### Inspiration

The carry handle on my water bottle snapped at the ring. The bottle is fine. The handle is a 6 mm ring and a loop — a five-minute part for anyone who can measure a neck and write OpenSCAD, and an impossible one for everyone else. I wanted the version of "just print a new one" that a person with a phone and a printer could actually do, and I wanted it to be *right*: a part that fits the first time, not a plausible shape.

Kintsugi is the Japanese art of repairing pottery with gold — the repair is visible and it is the point. Off-grid, the repair *is* the supply chain.

### What it does

Photograph the broken object, say one sentence. Kintsugi identifies the part and the features it must mate with, asks for the specific photos and readings that pin those features down, measures them on a printed calibration sheet, designs the replacement in OpenSCAD, verifies every dimension on the exported mesh, draws blueprints and has a second model audit them, then exports a printable STL with a fit coupon and a print card. If it still does not know something, it asks for another picture — not a number.

### How we built it

- **The spec is a contract.** Every dimension carries its evidence (estimates with source and confidence) and a *measure recipe* that tells the checker how to read it off the finished mesh (`circle_fit_inner` at z = 3, `hole_extent` along x, `gap`, `notch_mouth`, …). Verification is executable, not interpretive.
- **The model never grades its own homework.** Dimension lines on the sheets are computed from the mesh; the critic sees drawings and numbers, never code.
- **A measurement core that earns its numbers.** ArUco sheet → homography → metric top-down image at 0.1 mm/px → RANSAC circle candidates refined by radial edge profiles. On synthetic photos with known ground truth: diameters within 0.5 mm to 35° of camera tilt, centres within 0.3 mm.
- **Graph engineering.** Each stage is a typed dataflow graph: nodes declare inputs and outputs, independent nodes run in parallel, humans are nodes that suspend the run, every run is traced with its critical path. The iteration pipeline renders its sheets while the checks run, just by declaring what depends on what, and every run reports how much of it ran in parallel.
- **The evidence graph** decides what to ask for next; a knowledge base of standard interfaces (bottle finishes, pipe ODs, shafts, fasteners, batteries, extrusions, bearings, bike parts) seeds estimates from the object's identity.
- **A customizer that knows its evidence.** The parameter block becomes sliders with units, switches that fold their dependents, option cards, presets and undo; each change compiles a draft with `-D` overrides (a burst of drags kills the stale compile and keeps the newest), the 3D view ghosts the verified mesh behind the draft with the overall dimensions drawn on the model, and a slider bound to a measured spec dimension carries the measurement, its sources and its tolerance band — moving it moves the spec with it, so the checks verify what the person chose.
- **OpenAI Responses API, used the way it wants to be used:** function tools whose outputs are images (the model looks at its own blueprints), `previous_response_id` so each sheet is uploaded once, reasoning effort per role, JSON mode for the critic and intake, vision for the capture agent.

### Challenges we ran into

- Making a model *see* a 0.4 mm error. Numbers in a table are ignored; a dimension line in red on a section view is not. Getting the renderer to draw engineering-drawing conventions (third angle, hatched sections, cutting-plane marks, detail views) was most of the leverage.
- Section recipes that read "no hole found" because the plane was at the wrong height. The intake prompt now writes recipes at heights where the feature exists — and the checker says exactly what it did not find.
- Wall-thickness minima that are convex-corner artifacts of sampling. `p05` is the hard check; the minimum is advisory.
- Oscillation: the designer nudging a dimension across its target four iterations running. Detected from history; the policy freezes the parameter and says so.
- Photos of shiny and transparent objects. The design answer is the neck-on-sheet trick: press the mating feature onto the sheet so its outline lies in the sheet plane. It has not been tried on a real photo yet.
- Streaming a long-running agent to a browser that may be a phone on the same Wi-Fi.

### Accomplishments that we're proud of

- The first real GPT-6 run converged in 2 iterations for $1.01 (`eval/reports/gpt6-first-run/`). Earlier, on the Agent provider, four kept runs on the same part (which has a vetted template the designer used) converged in 1, 1, 1 and 7 iterations; those raw sessions are not in the repository.†
- The A/B study†: five human-designed OpenSCAD repair parts from public repositories, a spec written by us from each one's own mating dimensions, Kintsugi designing from the spec alone; every Kintsugi part passed its hard checks (the hinge run was interrupted after iteration 4 and fails two soft checks), two human parts failed wall or topology checks (thresholds their designers never targeted), and a blind judge — the same model family as the designer, reading the sheets and the check tables — preferred Kintsugi's part in 4 of 5. One run per part; the caveats are in `eval/reports/ab_templates.md`.
- The critic probe†: five defects injected into a passing part. Three are invisible to the numeric checks and the code-blind critic caught 2 of those 3 (it missed the missing fillets); the other two also tripped a footprint check. Control: pass.
- Verified on known geometry before any model was involved: circle fits within 0.05 mm, interference volumes within 3 %, measurement within 0.5 mm on synthetic photos, every template against its spec, every OpenSCAD guide example compiled. The UI was driven end to end in a headless browser after every change, at desktop and phone widths, light and dark; `docs/REVIEW.md` walks the deployment journeys through the code.
- The follow-up loop: the system asks for the *photo* it needs, measures it automatically, and stops asking when it knows enough (exercised on synthetic photos and the scripted provider so far).
- The customizer: the finished part is not a file, it is a parametric designer with the evidence attached — and "overall length 118.8 mm ✗ ≤ 110" shows up before the person applies anything.

† Measured during development with the Agent provider; the GPT-6 re-run is pending.

### What we learned

- Verification is a rendering problem as much as a measurement problem: what the model sees decides what it fixes.
- An agent that can ask a good question is worth more than one that guesses well. The evidence graph made the questions cheap to compute and easy to batch.
- Declaring inputs and outputs (graph engineering) is a better foundation than orchestration code: parallelism, traces, resumable human steps and the critical path all fell out of it.
- Standard sizes are everywhere; a small catalogue plus one confirming photo beats estimating from pixels.

### What's next

- Order the print when you have no printer: Slant 3D "Portals" + Stripe, straight from the export step (scoped, not built).
- Publish the parametric part with its spec to MakerWorld/Printables so the next person with the same bottle gets it in one click.
- Grow the standards knowledge base into a proper interface library (threads, snap profiles, common appliance clips) and let intake match against it with vision.
- Multi-photo reconstruction and a printed measuring jig for the features a flat sheet cannot reach.
- A fleet mode for repair cafés and makerspaces: one server, many phones, a queue of prints.

---

## Disclosure (paste into the form's "third-party technologies" field)

OpenAI GPT-6 models through the official `openai` Python SDK (Responses API). OpenSCAD (GPL-2.0, invoked as a separate process). BOSL2 (BSD-2, vendored). OpenCV, trimesh, manifold3d, shapely, NumPy, Pillow, reportlab, pydantic, FastAPI, sse-starlette, uvicorn, React, Vite, three.js, Monaco. The A/B references are cloned at evaluation time from their authors' public repositories and are not redistributed. All application code, the renderer, the checker, the measurement core, the graph runtime, the prompts and the templates were written for OFFGRID during the hackathon window; AI coding assistants were used throughout, as the rules allow: Agent (the vendor) wrote and reviewed much of the code with me, first in a cloud session and then in the coding assistant locally. During development the A/B study and the critic probe (the numbers marked †) were run through the project's opt-in Agent provider; the product itself runs on the OpenAI API.

## Assets checklist

- [ ] Cover image (1280×720): the hero shot — phone photo of the snapped handle on the calibration sheet next to the printed replacement on the bottle.
- [ ] Gallery: (1) the guide at capture round 1 with a measured photo, (2) the blueprint views sheet with dimension lines, (3) the sections & assembly sheet, (4) the Evidence tab, (5) the Graph tab with the live pipeline, (6) the A/B side-by-side sheets (human vs Kintsugi), (7) the printed part on the object.
- [ ] Demo video ≤ 3 min (script in `video-script.md`).
- [ ] Repo public, README screenshots, `docs/design.html` linked.
- [ ] Re-run `eval/ab_eval.py` and `eval/critic_probe.py` on GPT-6; replace every † number and delete the marker.
- [ ] Hosted demo (or the Docker one-liner in the README) tested from a phone.
