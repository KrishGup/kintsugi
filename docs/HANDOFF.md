# Hand-off notes — what to try, what to expect, what is rough

## Try this first (30 minutes)

1. **Run the tests** (no model needed): `pip install -e ".[dev]" && pytest -q`. ~4 minutes, all green means OpenSCAD, the geometry stack and the measurement core work on your machine.
2. **The loop from a typed spec** (needs `AGENT_API_KEY` in `.env` or a logged-in `agent` CLI):
   ```bash
   S=$(kin new --spec eval/specs/bottle_handle.yaml --name bottle_handle)
   kin design "$S" --model opus
   kin export "$S"
   ```
   Watch `$S/events.jsonl` or open the web app. The bottle handle converges in 1–3 iterations, ~10 minutes, ~$3 on Opus (Sonnet is ~4x cheaper and does the simple parts fine: `--model sonnet`).
3. **The web app**: `kin serve` then http://localhost:8000. Open the session above, drag the parameter sliders (each Apply re-runs compile + checks + blueprint in a few seconds), read the checks table, look at the Sections tab.
4. **Print the coupon** from the Coupon button, then the part from the Export bundle. The print card says why the settings are what they are.

## The photo flow with a real object

1. Print `kin sheet -o sheet.pdf` at 100% (check the 100 mm bar with a ruler).
2. Home → Photo intake: upload 2–4 photos of the broken object (one context shot, one of the mating feature pressed onto the sheet, shot straight down), type one sentence, Analyze.
3. Intake returns the object, the broken part, a draft spec, a capture plan and up to four questions. Edit the spec YAML if it guessed wrong; answer the numeric questions with a ruler (Spec tab → Confirm).
4. Photos tab → Measure on the sheet photo with the interface dimension selected: the rectified image and the fitted circle are shown, and the estimate is attached to the spec with its confidence.
5. Run designer. Confirm the interface dimensions before Export or the bundle carries a "fit unconfirmed" label.

The intake prompt has only been exercised on rendered scenes here (no real photos were available in the build environment). Real photos of shiny or transparent objects will need the neck-on-sheet trick and a manual confirmation; expect to edit the draft spec.

## What the numbers mean

- `checks.json` / the Checks tab: every hard check is numeric and measured on the exported mesh. Interface dims show `expected = target ± clearance`.
- Wall thickness is sampled by ray casting (1500 points): `p05` is the hard check; `min` is a soft check and is often a convex-corner artifact.
- Interference is a boolean intersection with the crude context proxies you wrote in the spec; 0.05 mm³ is the pass limit unless `allow_contact` is set.

## Known rough edges

- The designer is confined to its session directory by a hook; it still has a shell, so keep sessions on a machine you trust.
- OpenSCAD 2021.01 is slow on BOSL2-heavy models (CGAL). A Manifold-enabled nightly (`KIN_OPENSCAD_BIN`) is 10–50x faster; the templates avoid post-2021 syntax.
- Section recipes need a height where the feature exists (`at_z`); a spec written at the wrong height reads "no hole found". The intake prompt knows this but check the draft.
- The critic occasionally asks for changes the spec does not justify; the designer is told it may push back in its narration.
- Server has no authentication. It is a local tool / demo, not a public service.
- Reconstruction from many photos (approach D in the scope) and the printed 3D jig (approach C) are not built; the sheet + reference-object paths are.

## Where things are

- Session workspaces: `sessions/<id>/` (spec.yaml, part.scad, iterations/, sheets/, checks.json, critic/, export/, events.jsonl, history.json, a git repo).
- Prompts: `kintsugi/agent/prompts/{designer,critic,intake}.md`.
- Recipes the checker understands: `kintsugi/spec/model.py` (MeasureRecipe docstring).
- Templates: `templates/*.scad`, their specs `eval/specs/*.yaml`.
- A/B evaluation: `eval/ab_eval.py`, report `eval/reports/ab_templates.md`.
