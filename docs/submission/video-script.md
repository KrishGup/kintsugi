# Demo video — what is in it

`docs/submission/kintsugi-demo.mp4` (2:49, 1280×720, under 10 MB). Recorded on 14 Oct 2026 by `scripts/record_demo.py` from the first real
GPT-6 session (`eval/reports/gpt6-first-run/`) on the private Azure instance: Playwright drives the real app, the narration
is OpenAI text-to-speech (`gpt-4o-mini-tts`), and the words are burned in as captions. The result beats are written from that
session's own numbers (iterations, checks, critic verdict, cost), read from the API at recording time.

What it does not show: a real phone photo going through intake (the home beat shows the photo screen, not a photo run) and a
printed part — neither exists yet.

| at | beat | picture | narration (also the caption) |
|---|---|---|---|
| 0:00.0 | title | card | This is Kintsugi: an agent that turns phone photos of a broken part into a verified, printable replacement. |
| 0:10.6 | problem | card | Things break at the one part that mattered: a handle, a clip, a knob. 3D printing should fix it, but someone has to measure the mating geometry and model a part that actually fits. Ask a language model for the CAD code, and you get a plausible shape that is off where it matters, because the model never sees what it built. |
| 0:34.7 | home | live: home | You start with two or three photos on a printed calibration sheet and one sentence about what broke. Kintsugi works out which features the part must mate with, and asks for the exact photos and ruler readings it still needs. |
| 0:49.7 | spec | live: spec | For this run I start from a typed spec instead: the carry handle of a water bottle. The neck diameter, the ring height and the size limits are the contract the part has to meet. |
| 1:02.6 | run | live: timeline | Then GPT-6 Astra takes over, through the OpenAI Responses API. It reads the OpenSCAD guides, writes the part, and compiles it. Every dimension in the spec is then measured on the exported mesh, never trusted from the code. This real run took 2 iterations. Its first attempt did not even compile; it read the error and fixed the geometry. The last one passes all 15 measured checks. |
| 1:32.8 | sheets | live: sheets | Before each change the model looks at engineering drawings rendered from that mesh. The measurements are drawn as dimension lines, green or red against the tolerance, so it sees exactly what it got wrong. |
| 1:47.3 | checks | live: checks | Pointing at a check shows the section it was measured on. A second model reviews the drawings and the check table without ever seeing the code. The critic agreed. The whole run cost $1.01. |
| 2:04.5 | customize | live: customize | The finished part is not a file but a parametric designer. Every dimension is a slider with a live 3D draft, and every fit dimension shows where its number came from and the tolerance it must stay inside. |
| 2:22.0 | export | live: export | Before the full part, a fit coupon tests the mating feature at three clearances in a few minutes of printing. Then you get the STL, a 3MF, the blueprints and a print card that explains the settings. |
| 2:38.3 | close | card | Off grid, the repair is the supply chain. Kintsugi: photograph what broke, print what fits. The demo and the code are linked below. |
