# Demo video — script and shot list (draft 1)

Target: **2:30–2:50**, 1080p, captions burned in (judges watch muted). Voice-over is you, plain and unhurried. Every claim on screen has a number or a file behind it. Nothing is faked: the sheets, checks and timings are from a real GPT-6 session on the actual bottle handle (keep that session folder; the video is shot from it).

## Structure

| t | section | what's on screen | voice-over |
|---|---|---|---|
| 0:00–0:08 | **Cold open** | Hands. The snapped handle. The bottle on the table. Then the printed replacement clicking onto the neck. No title. | "This handle snapped last month. This is the one Kintsugi designed from three phone photos." |
| 0:08–0:18 | **Title** | KINTSUGI — *Photograph what broke. Print what fits.* (2 s) → the guide's home page on a phone | "Kintsugi is an agent that turns photos of a broken part into a verified, printable replacement — and it checks its own work like an engineer." |
| 0:18–0:40 | **Intake + capture round** | Phone: three photos, one sentence, *Analyze*. Cut to the guide: intake card ("1 L wide-mouth bottle · carry handle · snapped at the ring"), the recognised standard chip, then **Round 1**: "bottle neck on the calibration sheet" with a camera slot, "measure the ring height" with a ruler. Upload the neck-on-sheet photo → "measured: inner_diameter 43.1 mm". | "It works out which features the part has to mate with, then asks for the photos that pin them down — one shot per feature on a printed calibration sheet. Each upload is measured automatically. When it knows enough, it stops asking." |
| 0:40–0:50 | **Evidence** | Evidence tab: photos → estimates → dimensions → checks; readiness bar turning green. | "Every dimension carries its evidence. Nothing is designed against a guess without saying so." |
| 0:50–1:35 | **Design loop** | *Design this part.* Timeline: the designer reads the spec, picks the ring-and-loop template, writes part.scad, `iterate`. The **sections sheet** with a **red** dimension line (43.45 vs 43.25). The designer's note. Next iteration: the line turns **green**. The 3D view rotating. Graph tab for 4 s: nodes lighting up in parallel, critical path in blue. | "GPT-6 writes the OpenSCAD and compiles it. Then the part is measured — on the exported mesh, never trusted from the code. The blueprint carries those measurements as dimension lines the model has to look at before it changes anything. Every step runs as a dataflow graph, so checks and drawings render in parallel." |
| 1:35–1:55 | **Critic** | The critic card: verdict *revise*, "unexplained through-hole in the bridge on the load path" (use the probe's `hole_in_bridge` variant if the real session had no revise). Designer fixes; critic *pass*. | "A second model reviews the drawings with fresh eyes and never sees the code. It catches what the numbers can't: a hole through the load path, missing finger scallops. In our probe it caught four of five injected defects." |
| 1:55–2:07 | **Customize** | The Customize tab: drag *Loop inner width* — the 3D draft follows the slider, the verified mesh ghosted behind; *Neck ID* shows "measured 43.2 ± 0.3 · from caliper" with the band on the rail; *Computed* flips "overall_length 118.8 mm ✗ ≤ 110" red; flip *Scallops* off; *Apply & verify*. | "The finished part is a parametric designer, not a file: every dimension a slider with a live draft — and every fit dimension shows where its number came from and warns before the checks would fail." |
| 2:07–2:17 | **Coupon + export** | Coupon popover; the printed three-ring coupon on the neck; "0.00 slid on" → clearance confirmed. Print step: STL, 3MF, blueprint PDF, print card. | "Before the full part, a fit coupon: the mating feature at three clearances. Pick the one that slid on and the clearance locks. Then the export, with a print card that says why." |
| 2:17–2:35 | **Proof** | Split screen: five A/B pairs (human sheet vs Kintsugi sheet) — quick; the table row "5/5 pass, 4/5 preferred". Then the printed handle on the bottle, lifted. | "Against five human-designed repair parts from public repos, built from the same mating dimensions, every Kintsugi part passed every check and a blind judge preferred it four times out of five. And the handle holds." |
| 2:35–2:48 | **Close** | Logo line + repo URL + "Built for HACK47: OFFGRID on the OpenAI Responses API". One beat on the open question. | "Off-grid, the repair is the supply chain. Kintsugi. Photograph what broke, print what fits." |

## Filming checklist

- [ ] Object: the bottle, the snapped handle, the printed handle, the printed coupon, the calibration sheet (printed at 100 %, check the 100 mm bar), a ruler/caliper.
- [ ] Phone footage: natural light, the sheet flat on a table; shoot the three intake photos *for real* on camera (screen recording of the phone browser via QuickTime/scrcpy or just film the phone).
- [ ] Screen recordings at 1440×900 (the layout in the screenshots): home → session guide; keep the mouse slow; hide bookmarks bar.
- [ ] Capture the timeline during a real run: the `iterate` calls, a failing check turning green, the critic verdict. If the real run passes first try, use the eval session `eval/reports/critic_probe/hole_in_bridge` for the critic scene and say so in the caption ("from our critic probe").
- [ ] Graph tab during the run (4 s).
- [ ] A/B sheets: `eval/reports/templates/<part>/ref/iter_00_sheet.png` vs `…/kin/iter_0N_sheet.png` (re-generated on GPT-6).
- [ ] Captions file; export with captions burned in; upload unlisted to YouTube; paste the link into Devpost.

## On-screen text (captions that carry the numbers)

- "measured on the mesh — never trusted from the code"
- "diameters within 0.5 mm on synthetic photos, to 35° of tilt"
- "critic caught 4 of 5 injected defects (control: pass)"
- "A/B vs five human designs: 5/5 pass · 4/5 preferred by a blind judge" (re-run on GPT-6 first)
- "verified on known geometry before any model was involved"
- "OpenAI Responses API: image tool outputs · previous_response_id · reasoning effort"
