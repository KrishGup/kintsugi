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
| `kintsugi/scad` | headless OpenSCAD compile with structured errors/echoes; customizer annotation parser (sliders) |
| `kintsugi/checks` | mesh measurements: sections, robust circle fits, hole patterns, notch (clip) fits, wall thickness by ray casting, overhang/bed/orientation scoring, boolean interference against context proxies |
| `kintsugi/render` | software z‑buffer renderer for 7 orthographic/iso views with hidden lines, hatched sections, mesh‑derived dimension lines, composed blueprint sheets |
| `kintsugi/spec` | the Part Spec (pydantic): interfaces, requirements, context proxies, print settings, evidence fusion and confirmation gates |
| `kintsugi/agent` | the designer (agent SDK session in the workspace with `iterate`/`finish`/`ask_user` tools), the code‑blind critic, photo intake, iteration pipeline with budget/oscillation/strategy‑switch policy, export bundle |
| `kintsugi/measure` | printable ArUco calibration sheet, marker detection + homography rectification (sub‑0.1 mm on synthetic photos to 35° tilt), circle/outline/rectangle measurement, coin/card reference scale, capture grading, synthetic photo generator |
| `kintsugi/server` + `web/` | FastAPI API with SSE event stream; React + three.js workspace: chat/timeline, 3D viewer, blueprint tabs, checks table, parameter sliders, code pane, spec editor, photos/measure |
| `templates/` | seven vetted parametric templates (ring‑and‑loop handle, L bracket, snap clip, D‑shaft knob, hook, spacer/gasket, threaded cap), each with a spec it passes |
| `eval/` | benchmark specs and the A/B evaluation against human‑designed OpenSCAD repair parts |

## Quick start

Requirements: Python 3.11+, OpenSCAD (2021.01 works; a Manifold‑enabled nightly is faster), `xvfb-run` on headless Linux (only for OpenSCAD's own PNG renders), Node 22 for the web UI, and a Agent model for the agent (an `AGENT_API_KEY`, or a logged‑in `agent` CLI, which the Agent SDK also accepts).

```bash
git clone https://github.com/KrishGup/kintsugi && cd kintsugi
pip install -e ".[dev]"
sudo apt-get install -y openscad xvfb          # or your platform's equivalent
cp .env.example .env                          # set AGENT_API_KEY (or rely on the agent CLI login)

# 1. the toolchain, no model needed
kin compile templates/ring_loop_handle.scad -o /tmp/handle.stl
kin checks /tmp/handle.stl --spec eval/specs/bottle_handle.yaml
kin blueprint /tmp/handle.stl --spec eval/specs/bottle_handle.yaml -o /tmp/sheets --iteration 1

# 2. the loop, with the model
S=$(kin new --spec eval/specs/bottle_handle.yaml --name bottle_handle)
kin design "$S" --model opus --budget 8 --critic-rounds 2
kin export "$S"                               # STL/3MF/SCAD/blueprint.pdf/print_card.md/coupon.stl/bundle.zip

# 3. the web app
(cd web && npm install && npm run build)
kin serve --port 8000                         # open http://localhost:8000
```

`kin sheet -o calibration_sheet.pdf` prints the ArUco calibration sheet (print at 100%; the 100 mm bar is the check).

## The flow

1. **Intake** — photos + one sentence → object, broken part, its interfaces, a draft spec, a capture plan, batched questions.
2. **Guided capture** — a shot list; each upload is graded (sharpness, exposure, markers, tilt) with a specific retake instruction.
3. **Measurement** — rectify to a metric top‑down image of the sheet plane; fit circles and outlines; attach estimates to spec dimensions; ask for a ruler/caliper confirmation when confidence is low or sources disagree.
4. **Spec review** — the editable spec card; interface dimensions must be *confirmed* before the export loses its "fit unconfirmed" label.
5. **Design loop** — write `part.scad` → compile → checks → blueprint → (critic) → revise, with an iteration budget, oscillation detection and a strategy switch (CSG → template → profile).
6. **Review** — 3D viewer, sheets, checks, sliders, code, iteration timeline with branching.
7. **Fit coupon** — the mating feature only, in three clearances; the result locks the clearance.
8. **Export** — oriented STL and 3MF, customizer‑ready `.scad`, blueprint PDF, print card, spec, session log.

## How the agent runs

The designer is a agent SDK session (the same agent loop as the coding assistant) whose working directory is the session workspace. It has file tools, a shell confined to that directory, and five in‑process tools: `iterate` (compile + checks + blueprint; returns the check table and the sheets as images), `list_templates`, `read_template`, `ask_user`, `finish`. The critic is a separate single‑turn call with fresh context that receives the spec, the check table and the sheets — never the code — and returns a JSON verdict. Both default to Opus; set `KIN_DESIGNER_MODEL` / `KIN_CRITIC_MODEL` to change.

Every iteration is a git commit in the session directory. The UI panels are views of the session's files; the event log (`events.jsonl`) drives the timeline.

## Evaluation

- `tests/` — 50+ tests that need no model: toolchain accuracy on known geometry (circle fits within 0.05 mm, wall thickness, interference volumes within 3%), measurement accuracy on synthetic photos, every template against its spec, the session pipeline and export.
- `eval/ab_eval.py` — the A/B study: five human‑designed OpenSCAD repair parts from public repositories, a spec written from each one's own mating dimensions, the designer builds from the spec alone, both measured by the same checker and judged blind. Report in `eval/reports/`.

## Repository layout

```
kintsugi/            Python package (scad, checks, render, spec, agent, measure, session, server, cli)
templates/           vetted parametric parts with self‑checks
eval/                specs, references manifest, A/B runner, reports
tests/               pytest suite (no model required)
web/                 React + Vite UI (built into web/dist, served by the API)
vendor/BOSL2/        the BOSL2 library (BSD‑2), on OPENSCADPATH for every compile
docs/                design document
```

## Disclosure

Kintsugi uses OpenSCAD (GPL‑2.0, invoked as a separate process), BOSL2 (BSD‑2, vendored), OpenCV, trimesh + manifold3d, shapely, FastAPI, React, three.js, Monaco, and Agent models through the agent SDK. The A/B references are cloned at evaluation time from their authors' repositories and are not redistributed here.

## License

MIT for this repository's own code. See `vendor/BOSL2/LICENSE` for BOSL2.
