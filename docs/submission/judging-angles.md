# Judging angles — what we know, how we win it (draft 1)

## What the hackathon actually is

- **HACK47: OFFGRID**, Sept 15 – Oct 15 2026, deadline Oct 15 12:00 am EDT. One prize: **$10,000 in OpenAI credits + a guaranteed seat in the next Hack47 cohort + a month of Red Bull supply** and "additional credits, tools, perks and resources from Hack47's sponsor network".
- Hack47 is **a 30-day builder residency in a Delhi villa** — 16 people per batch, "a house for builders who would rather ship than sleep", "build in the open" (daily logs visible to all), "the table is the seminar", "no friction budget". Founders: Rishul Chanana and Pratyush Pandey (Delhi). They select people who "arrive with something already running — a repo, a prototype, a user or two". Partner network on their site: OpenAI, the vendor, Google Gemini, Meta AI, NVIDIA, Hugging Face, Vercel, Stripe, GitHub.
- Devpost page philosophy: **"Don't build what you're supposed to build. Build what you want to exist."** Rules add: **"You don't need the most complicated project to win."** Required fields: Project Name, Short Description, Problem Statement, Solution, Demo Link, Source Code, Demo Video, Tech Stack, Build Process. Demo videos "strongly recommended"; a working prototype "whenever reasonably possible"; **disclose third-party tech**; explain what you added if building on open source.
- Criteria, verbatim: **Originality** ("genuinely interesting or unconventional?"), **Impact** ("solve a meaningful problem?"), **Execution** ("how well does the project work?"), **Product Thinking** ("would someone actually want to use it?"), **Technical Depth** ("was technology used thoughtfully?"), **Potential** ("could this become something bigger after OFFGRID?").
- **Judges are not announced** ("Looking for judges — hello@hack47.org"). Expect: the two founders, an OpenAI-side reviewer (developer relations / startup team), sponsor-network people, possibly alumni. Plan for a panel that reads fast, values shipped software over slides, and includes at least one person who will open the repo.

Sources: [Devpost page](https://hack47-offgrid.devpost.com/), [rules](https://hack47-offgrid.devpost.com/rules), [hack47.org](https://hack47.org/).

## What this panel is likely to reward

1. **It runs.** A hacker-house crowd will click the demo link before reading the story. The 60-second path must work on a phone and need no key (Demo mode). Everything else is secondary.
2. **Evidence over adjectives.** They said "you don't need the most complicated project". We win Execution and Technical Depth with *measured* claims: check tables, the A/B against human designs, the critic probe, the measurement accuracy. Every number in the submission should have a file behind it in the repo.
3. **Build in the open.** The repo already reads like a daily log: 36 commits, a design document (rev B), a hand-off doc, eval reports with caveats. Say so; link the commit history in the build-process field.
4. **"Build what you want to exist."** Lead with the personal story (the handle snapped) and the OFFGRID reading: a phone and a printer instead of a supply chain.
5. **Sponsor fit without pandering.** See below.

## Criterion → evidence map (use this in the video and the form)

| criterion | the one thing to show | where it lives |
|---|---|---|
| Originality | the model verifies against blueprints it cannot fake: dimension lines computed from the mesh, a code-blind critic, a printed fit coupon; the system asks for a *photo*, not a number | sheets in any session; `kintsugi/render`; critic probe report |
| Impact | repair instead of replace; works with a phone and a printer, off-grid; the part is parametric so the next person needs zero effort | inspiration; what's next; export bundle |
| Execution | bottle handle converges; A/B 5/5 pass and 4/5 preferred; critic 4/5; the toolchain verified on known geometry; the hand-driven browser walkthrough (`docs/REVIEW.md`) | `eval/reports/`, `tests/`, screenshots |
| Product thinking | six-step guide; capture rounds that stop when they know enough; phone camera slots; the customizer (sliders with the measurement behind them, live draft, presets, undo, mm/in) so the part is finished *for the person*, not for the model; coupon before the part; print card that explains itself | the UI, `docs/HANDOFF.md`, README "Customize like a parametric designer" |
| Technical depth | Part Spec with measure recipes; z-buffer engineering-drawing renderer; ArUco metrology; dataflow-graph runtime with human nodes and critical path; evidence graph; Responses API used natively | README "Graph engineering", `kintsugi/graph`, `kintsugi/spec/evidence.py` |
| Potential | Portals/Stripe ordering; MakerWorld publishing; standards library; repair-café fleet mode; the same loop is a general "verified CAD agent" | what's next |

## Sponsor angles

### OpenAI (the technical sponsor; the prize is their credits)

- The agent is **native to the Responses API** and uses the parts most projects skip: function tools whose *outputs are images* (the model looks at its own drawings), `previous_response_id` so a growing pile of blueprints is uploaded once, `reasoning.effort` per role (high for design, lower for the critic), JSON mode for the structured passes, vision in intake and the capture agent. Say this plainly in the build process and in one slide — it shows the technology was "used thoughtfully".
- **Two models, two jobs**: designer and code-blind critic with fresh context is a clean story about *why* a second model call is worth the tokens.
- **Credits would be spent well**: the A/B harness, the critic probe and the bottle-handle repeat runs are ready-made ways to burn $10k productively (bigger benchmark, more objects, more runs per part). Put a "what we'd do with the credits" line in Potential.
- Model naming: say GPT-6 (gpt-6-astra / gpt-6-sol) exactly as configured; never claim results from a model that did not produce them (re-run the † numbers on GPT-6 first).

### Red Bull

- Red Bull's brand is *doing hard things at the edge* — athletes, mechanics, expeditions — and its hackathon presence is the "gives you wings / keeps you shipping" supply. Two honest tie-ins, no logo abuse:
  1. **The off-grid repair story**: a bottle handle 40 km from a shop; a bike part on a trail. Our standards knowledge base already knows seatposts, handlebar clamps and **bottle-cage bosses (two M5 bolts, 64 mm apart)** — a broken bike bottle cage mount is a Red Bull-adjacent second demo object that we can measure and design today.
  2. **The energy joke, once, lightly**: a can holder / cooler clip as a fun demo object if one is at hand. Don't overdo it; the judges are engineers.
- Do **not** put Red Bull branding on the part or the UI; mention the sponsor in the thanks slide and in the story where the off-grid framing is natural.

### Hack47 itself

- The prize is a **seat in the house**. The founders select builders with "something already running". The submission should read like a person they want at the table: shipped, measured, honest about the rough edges, curious. Keep the "known rough edges" section — it is a feature to this audience.
- "The table is the seminar": end the video with the open question we'd bring to the house (how far can a phone + printer replace a supply chain?).

## Stand-out tactics (cheap, high leverage)

1. **Cold open with the real thing** (first 8 seconds of the video): the snapped handle, the phone, the printed replacement clicking onto the bottle. No logo, no title card first.
2. **Show the receipts on screen**: a section view with a red dimension line becoming green on the next iteration; the critic's "hole in the load path" catch; the A/B sheet pair.
3. **Let the judge run it in a minute**: Demo mode needs no key; the README's first block is `docker run … -e OPENAI_API_KEY=…` and the demo-mode toggle. Test that path from a phone.
4. **One number per claim**, each with a file behind it. Judges who open the repo find `eval/reports/*.md` with the same numbers.
5. **Name the limits**: no reconstruction from many photos; shiny objects need the neck-on-sheet trick; the critic misses missing fillets; specs need the right section heights. Credibility is the moat in a room full of demos that "work".
6. **Kintsugi as a name and a frame**: the repair is visible and it is the point. One sentence, once.
7. **Graph tab in the video for four seconds**: the live pipeline lighting up in parallel with the critical path in blue is the most "engineered" image we have.
8. **The gallery order matters**: cover = physical result; image 2 = blueprint with dimension lines; image 3 = the guide asking for a photo; then the rest.

## Judge experience — the three paths

- **30 seconds** (skimmer): cover image + tagline + the first paragraph of the solution + the video's first 20 s. Must land: "photos → verified printable part; it checks its own drawings".
- **3 minutes** (watcher): the video. Story → capture round → design loop with blueprints → critic catch → coupon → printed part. Numbers on screen, not spoken only.
- **10 minutes** (opener): README → Demo mode in the browser → `eval/reports/ab_templates.md` → `tests/` → `docs/design.html`. Every link must resolve; the repo must be public before the deadline.

## Risks and how we handle them

| risk | handling |
|---|---|
| numbers were produced on a different model family (†) | re-run A/B + critic probe on gpt-6-astra before submission; if a run cannot be repeated, drop the number rather than keep it |
| "students only" eligibility wording on Devpost | already discussed with the organiser context in mind; keep the team page accurate |
| live model call fails during a judge's demo | Demo mode; the capture agent and the finish nudge fall back gracefully; the guide shows errors as toasts, never blank screens |
| judges have no printer | the value is visible on screen (sheets, checks, coupon); the video shows the physical fit |
| the evidence/graph machinery reads as complexity for its own sake | frame it as *why it converges*: fewer wasted photos, parallel pipeline, resumable human steps; keep the tab optional |
| repo not public / demo link dead at deadline | checklist in `devpost.md`; do it a day early |

## Likely questions from the panel (and the answers)

- *Why OpenSCAD and not a mesh/CSG library?* Parametric text is what a customizer slider and a diff need; the model reasons about it well; the STL is verified independently anyway.
- *How accurate is the photo measurement?* Within 0.5 mm on synthetic ground truth to 35° tilt; on real photos the calibration sheet and the neck-on-sheet trick keep it in the same range, and a ruler or the coupon confirms before printing.
- *What happens when the model is wrong?* The checker fails the iteration with the number; the critic sends it back with a location on the drawing; after the budget it asks the user a specific question or for a specific photo. It cannot pass without measuring.
- *Why a second model as critic?* The designer grades itself generously; a fresh context that never sees the code catches intent and load-path problems the numbers cannot (2 of the 3 drawing-only defects in the probe; it missed the missing fillets).
- *Cost per part?* $0.35–$1.30 per design run in the A/B†; the coupon and the print are the expensive part.
- *What would you do with $10k of credits?* Scale the benchmark to 50 real broken objects, run each 5×, measure convergence and cost per model/effort, and publish the results with the parts.
- *Is this just for bottles?* The templates cover ring/loop handles, brackets, snap clips, D-shaft knobs, hooks, spacers and threaded caps; the spec language covers bores, bosses, slots, hole patterns, snaps and threads; the standards base covers pipes, shafts, fasteners, batteries, rails and bike parts.

## Before-submission TODO (owner: Krish)

- [ ] Real photos of the bottle handle through the full flow on GPT-6; keep the session folder as the demo session.
- [ ] Re-run `eval/ab_eval.py` (5 parts) and `eval/critic_probe.py` on gpt-6-astra; regenerate reports; update every † number in `devpost.md` and the deck.
- [ ] Print the coupon and the handle; film the fit (this is the cover image and the cold open).
- [ ] Second object if time: a bike bottle-cage adapter or a broken clip from around the house.
- [ ] Create the GitHub repo, push, make it public; add screenshots to the README.
- [ ] Host a demo (any small VM with Docker) or document the one-liner; test from a phone.
- [ ] Record the video from `video-script.md`; ≤ 3 minutes; captions on.
- [ ] Fill the Devpost form from `devpost.md`; upload the gallery in the order above.
