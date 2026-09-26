# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- Primary: makers fixing their own broken things at home — a bench or a kitchen table, in daylight, phone in hand, an FDM printer nearby. They can take a photo and press print; they do not model in CAD. (confirmed)
- Second audience, first in priority until 15 Oct 2026: the Hack47 OFFGRID judges and demo audience, who meet the product through the demo path home → capture → review → customize, on a laptop and on a phone. (confirmed)
- Not a target: professional engineers who would rather open CAD. (inferred from the brief)

## Product Purpose

Kintsugi turns photos of a broken object into a verified, printable replacement part. The person photographs what broke on a printed calibration sheet and says one sentence; the agent works out which features the part must mate with, asks for the specific photos and readings that pin those features down, measures them, designs the part in OpenSCAD, verifies every dimension on the exported mesh, draws blueprints, has a second model review them, and exports an STL with a fit coupon and a print card. Success is a part that fits on the first or second print, reached without the person typing a number they did not measure.

## Positioning

The model never grades its own homework: dimensions are measured on the exported mesh, the blueprint's dimension lines are computed from that mesh, and the critic reviews the drawings without seeing the code. Every dimension carries its evidence (which photo, ruler, caliper, or recognised standard produced it, and with what confidence), and the finished part stays parametric — the customizer's sliders know where their numbers came from. Kintsugi asks for a *photo*, not a number.

## Operating Context

- Runs locally (FastAPI + a React workspace) on the maker's own computer; the phone joins over the same Wi-Fi to take photos into the session. Off-grid is the hackathon's theme: the app must work with no internet except the model API, so nothing in the UI may depend on a CDN.
- Materials in the loop: the printed ArUco calibration sheet (100 mm bar as the print-scale check), a ruler or caliper, the fit coupon (three clearances printed before the part), the print card that explains slicer settings.
- Tools around it: OpenSCAD 2021.01 + BOSL2 (the modeling engine), the slicer the maker already uses, OpenSCAD's desktop customizer (reads the presets Kintsugi writes).
- Demo mode: a scripted designer builds the bottle handle from a template so every screen can be shown in a minute without an API key.

## Capabilities and Constraints

- Six stages: intake → capture rounds → confirm the fit → design & verify → review → print/export; a three-pane workspace (guide/timeline · 3D and blueprint sheets · checks/customizer/code/spec/photos/graphs).
- Model provider: OpenAI GPT-6 via the Responses API is the default and the sponsor's platform; a Agent provider exists but is opt-in and never the pitch.
- Iterations are budgeted (8 by default), with oscillation detection and a strategy switch; a run can pause on a question to the person (text, a choice, or a photo request).
- Terminology: *spec* (the Part Spec contract), *interface* (a mating feature), *dimension* with *estimates* and *status* (unknown / estimated / confirmed), *check* (hard or soft), *iteration*, *critic*, *coupon*, *blueprint sheets* (views, sections, assembly), *customizer* / *draft* / *verified*.
- Undecided: whether the demo video is recorded on the phone-first or the laptop-first path; the numbers marked † in the submission drafts must be re-run on GPT-6.

## Brand Commitments

- Name: Kintsugi. Tagline: "Photograph what broke. Print what fits."
- Palette (binding, from the brief): navy #05142E, blue #155DD3, mid blue #6C9EF0, pale blue #BED4F9. Light workspace by default, a dark mode composed from the navy by system setting.
- The drafting-sheet look (blueprint sheets, dimension lines, tracked title-block labels) is the incumbent identity the deck and the docs already use; refine it, do not replace it.
- Sponsors to keep in mind on public surfaces: OpenAI (the platform) and Red Bull (the hackathon); no sponsor logos in the product UI.

## Evidence on Hand

- Real: the templates and their specs (`templates/`, `eval/specs/`), the A/B study against human-designed repair parts (`eval/reports/ab_templates.md`), the critic probe, 96 tests, the blueprint sheets and screenshots in `docs/submission/img/`, the pitch deck and Devpost draft in `docs/submission/`.
- Absent, never to be fabricated: customer quotes, install counts, the GPT-6 re-run numbers (marked †), a recorded demo video, the photo of the real snapped handle (placeholder in the deck).

## Product Principles

1. Ask for a photo, not a number — the person measures by pointing a camera, the system does the arithmetic.
2. Verified beats plausible: nothing is shown as fitting until a check measured it on the mesh; drafts are labelled drafts.
3. The guide never shows a blank screen — every stage has its one next action, and the engineer's view stays one tab away.
4. Phone and laptop are one session: capture happens where the object is, review where the screen is big.
5. Works off-grid: no CDN, no cloud storage, only the model API leaves the machine.

## Accessibility & Inclusion

- Keyboard-operable throughout (sliders, tabs, menus), visible focus, WCAG AA contrast in both themes; measurement states never rely on colour alone (text and icons carry pass/fail).
