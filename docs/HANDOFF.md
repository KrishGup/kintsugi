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
6. **Step 5 — Review**: pass/fail per check, the critic's verdict, the designer's narration; ask for a change in plain words, or **Looks right — export**.
7. **Step 6 — Print**: STL / 3MF / bundle downloads and the print card. If a fit dimension was never confirmed the guide says to print `coupon.stl` first.

The Timeline tab (left pane) is the full event log; the right pane keeps the engineer's view (checks, params, code, spec, photos).

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

- The designer's shell is confined to its session directory and a blocklist (no package installs, no network tools), but it is still a shell; keep sessions on a machine you trust and do not expose the server (no authentication).
- OpenSCAD 2021.01 is slow on BOSL2-heavy models (CGAL). A Manifold-enabled nightly (`KIN_OPENSCAD_BIN`) is 10–50× faster; the templates avoid post-2021 syntax.
- Section recipes need a height where the feature exists (`at_z`); a spec written at the wrong height reads "no hole found". The intake prompt knows this but check the draft.
- The intake prompt has only been exercised on rendered scenes and the scripted provider here (no real photos in the build environment). Shiny or transparent objects will need the neck-on-sheet trick and a manual confirmation; expect to correct a number or two in step 3.
- The critic occasionally asks for changes the spec does not justify; the designer is told it may push back in its narration.
- Reconstruction from many photos and the printed 3D jig (approaches C/D in the design doc) are not built; the sheet + reference-object paths are.

## Where things are

- Session workspaces: `sessions/<id>/` (spec.yaml, part.scad, intake.json, iterations/, sheets/, checks.json, critic/, export/, events.jsonl, history.json, a git repo).
- Prompts: `kintsugi/agent/prompts/{designer,critic,intake}.md`. Provider facade: `kintsugi/agent/llm.py`; tools: `kintsugi/agent/tools.py`; scripted provider: `kintsugi/agent/fake.py`.
- Recipes the checker understands: `kintsugi/spec/model.py` (MeasureRecipe docstring).
- Templates: `templates/*.scad`, their specs `eval/specs/*.yaml`.
- A/B evaluation: `eval/ab_eval.py`, report `eval/reports/ab_templates.md`.
- Web UI: `web/src` (guide: `panes/GuidePane.tsx`, settings: `llm.tsx`); `npm run build` writes `web/dist`, which the API serves.
