# Pitch deck — outline (draft 1)

File: `docs/submission/kintsugi-offgrid-pitch.pptx` (12 slides, 16:9, speaker notes on every slide). Rebuild from
`pitch-deck-build.js` (`node pitch-deck-build.js`, needs `pptxgenjs`, `react-icons`, `sharp`; images in `img/`).
Visual system: the app's drafting-sheet look — paper, ink, blueprint blue, pass green; the recurring motif is a
dimension line with the measured number in the middle.

| # | slide | the one thing it says | visual |
|---|---|---|---|
| 1 | Title | Kintsugi — photograph what broke, print what fits; built on the OpenAI Responses API | assembly view from a real sheet |
| 2 | Problem | it breaks at the one part that mattered; replacement is the wrong size; LLM CAD is plausible and 1.5 mm out | **[replace the placeholder with the photo of the snapped handle]** |
| 3 | What it does | six steps: intake → capture rounds → design loop → code-blind critic → fit coupon → export | six cards |
| 4 | Key idea | the model never grades its own homework: measured on the mesh, drawn from the measurement, reviewed without the code | Section A-A with the green dimension line |
| 5 | Capture loop | it asks for the photo it needs, not a number; evidence graph; ≤ 0.5 mm; one round for the handle | guide column + evidence map |
| 6 | Graph engineering (dark) | every stage is a typed dataflow graph; people are nodes; critical path; 1.6–1.7× | live pipeline graph |
| 7 | Built on OpenAI | two models, two jobs; Responses API features used natively | designer → checker → critic diagram + feature chips |
| 8 | Proof | measured, not claimed: A/B table, critic probe, 79 tests, convergence († = re-run on GPT-6 pending) | A/B sheet pair |
| 9 | Product | a guide, not a console; phone capture; coupon; print card; demo mode | review screenshot |
| 10 | After OFFGRID (dark) | ordering, publishing, interface library, fleet; what $10k of credits buys | 2×2 cards |
| 11 | Built in the open | six phases; 36 commits · 18k lines · 79 tests · 3 docs; disclosure; thanks to sponsors | timeline + dimension stats |
| 12 | Close (dark) | off-grid, the repair is the supply chain; links | — |

## Talk track (3 minutes, if the deck is presented rather than the video)

1. (0:00) Object in hand. "This snapped; this came from three photos."
2. (0:20) Slide 2 — the problem, and the specific failure of naive LLM CAD.
3. (0:45) Slide 4 — the idea: measured on the mesh, drawn from the measurement, reviewed blind.
4. (1:15) Slide 5 — the capture loop: it asks for the photo, measures it, stops when it knows enough.
5. (1:45) Slide 8 — proof: A/B, critic probe, tests.
6. (2:15) Slide 6/7 — one breath each on the graphs and the API.
7. (2:40) Slide 10 — what's next; what the credits buy.
8. (2:55) Close.

## Iteration notes for draft 2

- Swap the slide 2 placeholder for the real photo; add a second real photo (printed handle on the bottle) to the close slide.
- Re-run the evals on GPT-6 and drop the † markers; if convergence differs, update slide 8 and the video.
- If a second object (bike bottle-cage adapter) gets built, add it to slide 9 as a second screenshot.
- Consider a 30-second "how the graph runs" clip embedded on slide 6 for the video cut.
