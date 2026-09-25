# Photo-to-Part — Project Scope (Core Loop)

Working scope for the OFFGRID build. Covers the product, the end-to-end flow, the measurement / modeling / verification approaches worth trying, the agent's tools and policies, the UI, outputs, evaluation, and build order. Ordering and fulfillment (Slant 3D, Stripe) are out of scope here.

---

## 1. What it is

An agent that turns photos of a broken object into a verified, parametric, printable replacement part. The user photographs the damage, the agent guides capture, measures, writes a Part Spec, designs the part in OpenSCAD, checks its own work against engineering drawings and mesh measurements, optionally closes the loop with a physical fit test, and exports an STL plus a print card.

Second face of the same product: a general OpenSCAD design agent with a real verification loop. Photo-to-part is the hero flow; "design me a bracket with these dimensions" uses the same machinery.

**Running example:** a water bottle carry handle that snapped. It is a ring that sits around the neck under the cap, with a loop. Interfaces: ring inner diameter, available ring height between cap flange and shoulder, and no interference with the cap threads.

---

## 2. Principles

1. **A replacement part is defined by its interfaces.** Measure the mating geometry precisely; design the body freely (often stronger and more printable than the original). This replaces "3D-scan the object" (hard, imprecise) with "measure a few critical dimensions and design around them" (tractable, precise). It is also how a human engineer does it.
2. **Everything the agent believes is written down.** The Part Spec holds every dimension with its source and confidence. Interface dimensions must be confirmed before the final export.
3. **The agent checks its work like an engineer, not like a programmer.** Drawings, mesh measurements, an assembly interference check, and a printed fit coupon. A separate critic reviews the drawings and never sees the code.
4. **Output is parametric.** A near miss is a slider nudge, not a re-run.

---

## 3. End-to-end flow

### Stage 1 — Intake
- User uploads one or more photos and says what happened.
- Agent identifies the object, the broken part, and its function (vision pass with structured output: object class, part role, likely interfaces, load direction, materials).
- Agent asks a short batch of questions in one card, not a drip: what does the part attach to; do you have the broken piece, an intact counterpart, or the original part; what printer and material; do you have a ruler or calipers.
- Output: `intake.json` and a first draft of the Part Spec with everything marked `unknown` or `estimated`.

### Stage 2 — Guided capture
- Agent produces a capture plan: an ordered list of shots, each with purpose, camera position, what must be in frame, dos and don'ts, and a ghost overlay in the camera view.
- Two calibration options: (a) a common reference object (coin, credit card), or (b) a printable calibration sheet (Section 5B). The app recommends (b) whenever a printer is within reach.
- Optional one-time phone calibration: photograph the sheet a few times from different angles to get camera intrinsics and distortion. Improves every later measurement and the pose-matched overlay.
- Every photo is auto-graded on upload: sharpness (Laplacian variance), exposure, reference detected, viewing angle from marker pose (near-perpendicular for planar measurement), feature occluded or not (vision check). Failed shots get a specific retake instruction.
- Standard shot set for the example:
  1. Context — whole bottle, cap on, handle area visible.
  2. Broken pieces on the calibration sheet, top-down.
  3. Neck lip pressed onto the sheet, bottle inverted, top-down. The neck outline is now in the sheet plane, so its diameter is directly measurable.
  4. Side view of the neck region with the sheet or jig behind it, cap on, for the height the ring must fit in.
  5. Intact counterpart, if one exists.

### Stage 3 — Measurement
- Agent runs the measurement tools per shot (Section 5) and logs every estimate with source and confidence into the spec.
- Anything critical with low confidence or disagreeing sources becomes a **measurement request card**: the photo annotated with exactly which distance to measure and with what, plus a field for the number.
- The fusion rule (Section 5H) decides the target value per dimension.

### Stage 4 — Part Spec review
- The spec is shown as a card: interfaces with target / tolerance / source / status, functional requirements, print constraints, design intent, open questions.
- User confirms or edits. Editing a number in the card updates the spec file; the agent re-plans if an interface changed.
- Interface dims must be `confirmed` (user-confirmed, or two independent high-confidence sources agreeing within tolerance) before final export. Otherwise export is allowed but labeled "fit unconfirmed — print a coupon first."

### Stage 5 — Concepts
- Agent proposes two or three design concepts as quick low-res renders (A: loop like the original; B: reinforced loop with finger scallops; C: strap style with lanyard hole), each with one line on strength and printability.
- User picks; the choice is recorded as `design_intent`. Skippable ("just match the original").

### Stage 6 — Modeling loop
- The agent writes `part.scad`, compiles, renders the blueprint sheet, runs mesh checks against the spec, runs the interference check against the context proxy, submits to the critic, and revises. Section 7 is the detailed loop.
- The UI streams every iteration: code diff, blueprint sheet, checks table, critic verdict, and a one-line narration ("Iteration 4: ring ID measured 42.9 vs 43.2 target — increased by 0.3; added 1 mm fillet at loop root").

### Stage 7 — Review and refinement
- Live 3D viewer, blueprint tabs, parameter sliders generated from the customizer annotations, code pane.
- Chat edits ("thicker grip", "add a lanyard hole") go through the same loop. Every iteration is a commit; the user can branch from any earlier iteration.

### Stage 8 — Fit test (recommended)
- Agent generates a coupon: only the mating features, small enough to print quickly, with embossed labels. Usually a tolerance ladder (three neck rings at −0.2 / 0 / +0.2 mm clearance).
- User prints, reports which one fits (or photographs it on the object), and the agent locks the clearance and updates spec and model.

### Stage 9 — Export
- STL and 3MF in the recommended print orientation, `part.scad` with customizer parameters, blueprint PDF, print card (material, orientation, walls, infill, supports, and why), spec, and the session log.

---

## 4. The Part Spec

The spec is the contract between measurement, modeling, and verification. It is a YAML file in the session workspace; the spec card in the UI is a view of it.

```yaml
part:
  name: bottle_handle
  role: carry handle; ring sits around the neck under the cap flange
  object: 1 L wide-mouth plastic bottle
  design_intent: reinforced loop, finger scallops (concept B)

interfaces:
  - id: neck_ring
    type: cylindrical_bore
    mates_with: bottle neck between cap flange and shoulder
    fit: sliding            # press | sliding | loose | snap
    clearance: 0.25         # mm; material default, overridden by coupon result
    dims:
      inner_diameter:
        target: 43.2
        tol: 0.3
        status: confirmed   # unknown | estimated | confirmed
        estimates:
          - {value: 43.4, source: rectified_sheet, photo: shot3.jpg, conf: 0.75}
          - {value: 43.2, source: user_caliper, conf: 0.95}
        measure: {recipe: circle_fit_inner, at_z: 3.0}   # how the checker measures the mesh
      height_available:
        target: 6.0
        tol: 0.5
        status: estimated
        estimates:
          - {value: 6.2, source: jig_side_view, conf: 0.6}
        measure: {recipe: extent_z, feature: ring}

requirements:
  - id: load
    text: carry a 1.5 kg full bottle by two fingers, with margin
    derived:
      loop_inner_width: {min: 40}
      loop_inner_height: {min: 25}
      min_cross_section: {min: [6, 4]}
  - id: cap_clearance
    text: cap must thread on and off with the ring in place

context:                  # proxy geometry for interference checks and assembly views
  - {id: neck, shape: cylinder, d: 43.2, h: 12, at: [0, 0, 0]}
  - {id: cap_flange, shape: cylinder, d: 62, h: 3, at: [0, 0, 6]}
  - {id: shoulder, shape: cone, d1: 43.2, d2: 85, h: 10, at: [0, 0, -10]}

print:
  material: PETG
  nozzle: 0.4
  min_wall: 1.6
  orientation_hint: ring flat on bed, loop in the XY plane

open_questions:
  - does the ring need to rotate freely, or is snug fine?
```

Rules:
- Every dimension carries its estimates. The agent never overwrites evidence; it adds to it.
- Each interface dim has a `measure` recipe, so verification is executable rather than interpretive.
- `context` is deliberately crude. It exists so the checker can compute interference volume and the blueprint can show the part on a ghost of the object.

---

## 5. Measurement approaches

The agent selects and combines these. Build A, B, E, F, and G first; C and D are the high-ceiling options to trial.

### A. Reference object in frame (coin, card)
- Detect the reference (circle detection with a color check for coins; rectangle detection for cards), compute mm per pixel in the reference plane, segment the feature, and fit (circle for holes and necks, min-area rectangle for lengths).
- Accuracy: roughly ±2–5 % when the reference is coplanar with the feature and the camera is near-perpendicular; degrades fast off-axis.
- Use: zero-setup first draft, body dimensions, anything the sheet can't reach.

### B. Printable calibration sheet (ArUco / ChArUco)
- A PDF with markers at known spacing, a 10 mm grid, a 100 mm verification bar, and outlines for a coin sanity check. The app asks "does the bar measure 100 mm?" to catch fit-to-page scaling.
- Markers give scale and plane pose. Compute a homography, rectify the photo to a true top-down, mm-scaled image, then measure in it. Expected accuracy: sub-millimeter on flat features with a phone camera and reasonable lighting.
- Use: outlines, hole spacing, any face that can lie on or be pressed against the sheet. The neck-on-sheet trick in Stage 2 belongs here.

### C. Printed 3D calibration jig
- A small corner jig with markers on three orthogonal faces (or a cube). Two or more photos give a 3D reference frame; the agent triangulates feature points to measure heights and depths the flat sheet can't.
- Use: the ring's available height between cap flange and shoulder, step depths, anything along the camera axis.
- Doubles as a printer-scale check.

### D. Few-shot 3D reconstruction plus primitive fitting
- From five to twenty photos, build a point cloud: COLMAP as the reliable classical route; few-image feed-forward models (the DUSt3R / MASt3R family — check the current state) as the fast route. Scale it with markers.
- Then fit primitives to the region of interest with RANSAC. A cylinder fit on the neck yields a diameter and axis from noisy points. Optionally mesh the mating region and `import()` it into OpenSCAD to design against.
- Highest ceiling and most fragile. Frame it as "scan the mating feature", never "scan the object".

### E. Guided manual measurement
- Measurement request cards: annotated photo, plain instruction ("outer diameter of the neck lip at the widest point"), tool suggestion, input field.
- Most reliable source. Mandatory for any interface dim below the confidence threshold.

### F. Silhouette and profile tracing
- Part on the sheet, top-down, rectified, segmented to a polygon, simplified (Douglas–Peucker with a tolerance below the nozzle width), exported as a `polygon()`.
- Flat parts: `linear_extrude(height)`. Axisymmetric parts: side profile → half-profile → `rotate_extrude()`.
- Verification is trivial: overlay the polygon on the rectified photo.
- Use: gaskets, plates, brackets, clips, knobs, caps, the ring of a handle.

### G. Counterpart capture
- If an intact twin exists (other handle, mirrored part, the old part), photograph it on the sheet from three orthographic angles. That is ground truth for the body; A–F still confirm the mating dims. Mirroring is a one-liner.

### H. Fusion
- Per dimension, order of trust: user-confirmed manual > two rectified-sheet shots agreeing > one rectified shot > reference-object > reconstruction-derived, unless reconstruction corroborates a higher source.
- Disagreement beyond tolerance → measurement request card, never a silent average.
- Confidence thresholds: interface dims need ≥ 0.9 or user confirmation; body dims ≥ 0.6.

### Selection matrix

| Part geometry | Primary | Secondary | Confirm with |
|---|---|---|---|
| Round bore or boss (neck ring, cap, bushing) | B (feature on sheet) or F | D (cylinder fit) | E |
| Flat plate, bracket, gasket | F | B | E for hole spacing |
| Loop, hook, handle body | G if a twin exists, else A | B | load rules only |
| Height or depth along the camera axis | C | D | E |
| Organic mating surface | D (import) | — | coupon |

---

## 6. Modeling approaches

### 1. Spec-driven CSG (default)
The agent writes OpenSCAD from the spec using primitives plus BOSL2 (rounding, attachments, threading, bottle-neck and cap modules, joiners). Handles, brackets, hooks, knobs, caps.

### 2. Profile-based
`polygon()` from approach F with `linear_extrude` or `rotate_extrude`. Exact outlines with almost no modeling risk.

### 3. Template catalog
A curated set of vetted parametric templates, each with named parameters, a docstring, default print settings, and its own self-check module: ring-and-loop handle, snap-fit clip, threaded cap, D-shaft knob, L-bracket, hook, hinge pin, spacer / gasket, battery door, buckle. The agent instantiates a template, then customizes in code. Highest success rate; the demo's safety net.

### 4. Scan-import hybrid
`import()` a scaled mesh of the mating region and use it as a negative (`difference()`) or a positive to hull around. For surfaces that resist primitives.

### 5. Parallel attempts (tournament)
For the first modeling pass, run two or three strategies at once (CSG, template, profile) and let the checks plus critic pick the survivor. Worth it when the part class is ambiguous.

### Code conventions the agent must follow
- Parameter block at the top with customizer annotations (`// [0:0.1:10]`, dropdowns, `/* [Section] */`) so the UI can build sliders.
- One file, one `render_target` parameter selecting `part()`, `coupon()`, or `assembly()` (part plus ghosted context).
- Print orientation is model orientation: Z up, bed at Z = 0, origin at the primary interface center.
- Named modules per feature; `assert()`s on spec constraints; `echo()` of derived dims.
- Moderate `$fn` during iteration, high `$fn` at export.

### Design-for-print rules baked into prompts and checks
- Minimum wall = two perimeters (1.6 mm for a 0.4 nozzle); fillets at every stress concentration; chamfer or fillet the bed-side edge.
- Default clearances by fit and material (PLA / PETG): press ~0.1, sliding ~0.2–0.3, loose ~0.4. Coupons override.
- Orientation vs load: layer adhesion is the weak direction; a handle loop prints flat so the load runs along layers, not across them.
- Overhangs beyond ~45° are redesigned (chamfers, teardrops on horizontal holes) or get supports called out on the print card.
- Simple strength rules for the loop cross-section from load, material, and a large safety factor. No FEA in scope.

---

## 7. The verification loop

One iteration:

1. **Compile.** `openscad` exports the STL; syntax errors, failed `assert()`s, and manifold warnings go straight back to the agent.
2. **Blueprint sheet.** Render orthographic front, back, left, right, top, bottom, one isometric, and one to three cross-sections at spec-relevant heights. Draw dimension lines computed **from the mesh, not from the code**: overall extents plus every spec dimension via its `measure` recipe, labeled target vs measured, green inside tolerance and red outside. Add a 10 mm grid, a scale bar, and a title block (part, iteration, key-dims table). Compose into one image so the model reads a single coherent drawing.
   - Two ways to render, both worth trying: OpenSCAD's own `--projection=o` renders (pretty, less controllable) and rendering the STL in Python (exact mm-per-pixel, easy annotation). Cross-sections come from slicing the mesh at a plane, or from `projection(cut=true)`.
3. **Mesh checks → `checks.json`.** Watertight, single body, volume, bounding box vs spec, each interface recipe (slice at height → circle fit → diameter; plane-to-plane distances; hole positions from section components), wall thickness (inward ray casting from sampled surface points; min and low percentile), overhang area fraction, bed contact area, center-of-mass height. Every item is pass/fail with numbers.
4. **Interference check.** Boolean-intersect the part with the `context` proxy; intersection volume must be ~0 except at intended contact faces. The assembly view on the sheet shows the part around the ghosted neck and cap.
5. **Pose-matched overlay (when markers exist).** Recover the camera pose from the markers in a user photo, render the model from that pose, overlay its contour on the photo, and compute silhouette IoU against the segmented original where applicable. This is the "does it look like the photo" check.
6. **Critic.** A separate model call with fresh context receives the spec, the current and previous blueprint sheets, `checks.json`, overlay images, and reference photos. It never sees the code. It returns `{verdict: pass | revise | ask_user, discrepancies: [{where, expected, observed, severity, suggestion}]}`. Fresh context stops the critic agreeing with the author out of shared history.
7. **Decide.** All hard checks pass and the critic passes → done. Otherwise revise with the discrepancy list as input.

Convergence policy:
- Iteration budget per phase (six is a sensible start).
- Oscillation detection: a dimension flipping across the target twice freezes that parameter and asks the user.
- Same failure twice in a row → switch modeling approach (CSG → template, or profile) before asking.
- Ask the user only for: interface dims below threshold, source disagreement beyond tolerance, ambiguous function, or final export with unconfirmed dims. Batch the questions.

Printability pass at export: test the six axis-aligned orientations plus a few rotations, score by overhang area, bed contact, and load direction, recommend one, and write the print card. Optionally dry-run a slicer CLI (PrusaSlicer / OrcaSlicer) for filament and duration figures on the card.

---

## 8. Physical fit loop

- Coupons render from the same file (`render_target = "coupon"`): only the mating features, minimal height, embossed labels.
- Ladders: three to five variants stepping the clearance; sizes marked on each.
- Go / no-go gauges for holes and pins.
- Result capture: a card ("which one fits snug without forcing?") or a photo of the coupon on the object for a vision check.
- The result updates `clearance` and the relevant `status` to `confirmed`, and the loop re-runs the checks. This is also how the app learns a user's printer offsets across sessions.

---

## 9. Agent design

### Tools
- Perception: `analyze_photo`, `grade_capture`, `detect_reference`, `rectify`, `segment`, `measure_planar`, `reconstruct`, `fit_primitive`.
- Spec: `write_spec`, `update_spec`, `request_measurement`, `request_photo`.
- Modeling: `scad_compile`, `render_blueprint`, `mesh_checks`, `interference_check`, `overlay_compare`, `printability`, `generate_coupon`, `critique`.
- Delivery: `export_bundle`.
- Escape hatch: a Python shell in the sandbox with OpenCV, trimesh, numpy, and matplotlib available for the cases the tools don't cover. The tools are the reliable path; the shell is how the agent improvises.

### Workspace as memory
- The session directory is the agent's state: `intake.json`, `photos/` with per-photo metadata and grades, `spec.yaml`, `measurements.json`, `context.scad`, `part.scad`, `views/`, `sheets/`, `checks.json`, `critic/`, `export/`.
- Every iteration is a git commit. The UI panels are views of these files, and the chat transcript is summarized with the spec card pinned in context.

### Control policy
- Plan first: the agent writes a short strategy card (which measurement approaches, which modeling approach, which checks matter) before processing photos. Shown to the user, editable.
- Then stages 2–9, autonomously except at the ask points above.
- Model choice: the strongest available vision-capable model for intake, spec, critic, and coding alike, with separate roles as separate calls. The model layer stays swappable and is disclosed in the submission.

---

## 10. UI features

- **Chat** with rich cards: capture card (shot list with ghost previews and grades), measurement request card, editable spec card, concept picker, iteration card, coupon card, export card.
- **Capture view:** browser camera with a ghost overlay for the current shot, instant grade, retake guidance.
- **Model view:** 3D viewer; blueprint tabs (views, sections, overlay, assembly); checks table with pass/fail and numbers; parameter sliders from the customizer annotations with live re-render; code pane; iteration timeline with diff and before/after sheets; branch from any iteration.
- **Phone-to-desktop handoff:** capture on the phone, review on a laptop, one session link or QR.
- **Export view:** bundle download, print card, "fit unconfirmed" warning if applicable.

---

## 11. Outputs

`part.stl`, `part.3mf` (oriented), `part.scad` (customizer-ready), `blueprint.pdf`, `print_card.md`, `spec.yaml`, `coupon.stl`, and the session log with the iteration narration.

---

## 12. Evaluation harness

- **Benchmark set:** the bottle handle (ground truth: your own replacement model), plus five to eight household parts with caliper-measured interfaces: a bottle cap, a knob, a drawer pull, a phone-stand clip, a battery cover, a hook, a spacer.
- **Metrics:** interface dimension error (mm, per part), fit success rate with at most one coupon, iterations to converge, capture retakes needed, critic agreement with a human reviewer, run duration.
- **Measurement unit tests:** known objects (coins, cards, a printed gauge block with 20 / 30 / 40 mm steps) photographed across angles and lighting; assert error bounds per approach.
- **Regression:** rerun the benchmark whenever prompts, tools, or the critic change. Report the numbers in the demo.

---

## 13. Experiments to run

| Question | Compare | Metric |
|---|---|---|
| Which calibration is worth the setup? | A vs B vs C | dimension error, retakes |
| Can reconstruction beat planar measurement on the neck? | D cylinder fit vs B | error vs calipers |
| Which drawings does the model read best? | OpenSCAD renders vs Python renders; with / without dimension lines | iterations to converge, critic accuracy |
| Does the overlay help? | loop with / without pose-matched overlay | shape errors caught |
| Does a code-blind critic help? | fresh-context critic vs same-context self-review | false passes |
| Template-first or free CSG? | approach 3 vs 1 as first attempt | fit success, originality (judged) |
| Is the tournament worth it? | 1 attempt vs 3 parallel | success rate, iterations |
| Confirmation threshold | ask at conf < 0.8 vs < 0.9 | questions asked vs fit failures |
| Engineer persona and drawing conventions in prompts | with vs without | convergence, drawing quality |

---

## 14. Risks and mitigations

- **Perspective error in photos** → sheet plus rectification; near-perpendicular grading; confirm interface dims.
- **Transparent or shiny objects** (many bottles) → paper behind the feature, feature-on-sheet trick, measure the counterpart instead, manual card as fallback.
- **Wrong print scale** → the 100 mm bar on the sheet; the jig; the gauge block.
- **Slow renders with BOSL2 rounding** → Manifold backend in a recent OpenSCAD snapshot; moderate `$fn` during iteration.
- **Non-converging loop** → budgets, oscillation freeze, approach switch, ask.
- **Agent improvisation going sideways** → tools cover the reliable path; the shell is the exception.
- **No printer for coupons** → conservative clearances, sliders, "fit unconfirmed" label.
- **Reconstruction flakiness** → optional path only; never on the critical path for the demo.

---

## 15. Demo script

1. Drop the bottle. Handle breaks.
2. Photo of the damage, one sentence in chat.
3. Capture card appears; print the calibration sheet; take the four shots; watch grades go green.
4. One measurement card: confirm the neck diameter with a ruler.
5. Spec card; confirm. Concept picker; choose B.
6. Time-lapse of the loop: the blueprint sheet evolving, dimensions turning green, the critic's notes, the assembly view around the ghost neck.
7. Coupon ladder prints; the middle ring fits; the agent locks the clearance.
8. Final print; snap it on; carry the bottle.
9. Close on the benchmark numbers and the parametric sliders.

---

## 16. Build order

1. Blueprint sheet and mesh-check toolchain that works on any `.scad`. Test it on your existing handle model first.
2. Spec format plus the modeling loop from typed dimensions, no photos. This isolates the loop and gets the handle converging from a spec.
3. Measurement core: sheet PDF, marker detection, rectification, planar measurement, gauge-block unit tests.
4. Photo intake, capture plan, capture grading, spec generation.
5. Critic, pose-matched overlay, context proxy and interference check.
6. Coupons.
7. UI: cards, 3D viewer, blueprint pane, sliders, iteration timeline, phone handoff.
8. Benchmark set, experiments from Section 13, tuning; tournament mode.
9. Reconstruction path (D) and jig (C) as far as the benchmark justifies.
10. Demo video and submission write-up.

---

## Appendix — OpenSCAD tooling notes

- Use a recent development snapshot with the Manifold backend (flag names vary by snapshot; check `openscad --help`). Render speed matters because the loop renders every iteration.
- Export: `openscad -o part.stl -D 'render_target="part"' part.scad`; 3MF via `--export-format`.
- Orthographic views from OpenSCAD: `--projection=o --camera=<eye>,<center> --viewall --autocenter --imgsize=1600,1600`, one call per view. For annotated sheets, rendering the STL yourself gives exact mm-per-pixel.
- Cross-sections: slice the mesh at a plane in Python, or `projection(cut=true)` after translating the model.
- Libraries to ship in the sandbox with their docs indexed: BOSL2 (rounding, attachments, threading, bottle necks and caps, joiners) plus the template catalog.
- Customizer annotations drive the UI sliders; the agent must emit them for every user-facing parameter.
- In-browser preview: an OpenSCAD WASM build for slider-driven re-render. OpenSCAD is GPL, so disclose it and comply if you ship a build.
