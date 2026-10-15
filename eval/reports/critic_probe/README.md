# Critic probe — does the code-blind critic catch what the numbers miss?

Each variant injects one defect into the passing bottle-handle template. Three of the five variants keep every hard check green, so on those the critic can only catch the defect from the drawings; two (`thin_bridge`, `loop_too_thick_walls_ok`) also trip `footprint.overall_length`, so the numeric checks would have flagged them too — and on those the critic's finding cites the length overrun rather than the injected defect.

| variant | injected defect | hard checks | verdict | caught |
|---|---|---|---|---|
| control | (none: control) | pass | pass | — |
| no_scallops | design intent asks for finger scallops; they are missing | pass | revise | yes |
| hole_in_bridge | a 4 mm hole drilled through the bridge, the tension load path between ring and loop | pass | revise | yes |
| no_fillets | sharp inside corners where the bridge meets the ring and the loop (stress concentration) | pass | pass | no |
| thin_bridge | the bridge between ring and loop is a 6 mm wide neck, far narrower than the loop it carries (thin neck in the load path) | FAIL: footprint.overall_length | revise | yes |
| loop_too_thick_walls_ok | a 14 mm thick loop wall: heavy, over-built, wastes material and makes the grip bulky | FAIL: footprint.overall_length | revise | yes |

**Catch rate: 4/5 overall; 2/3 on the three defects the numbers cannot see** (missed `no_fillets`); control verdict: pass. Runs on an earlier model provider (since removed from the code); to be repeated on GPT-6.

### control

All spec dimensions pass, every design-intent feature (reinforced loop, finger scallops, flat ring, XY loop) is present, the load path from loop to ring is unbroken, and the part assembles cleanly with the neck while clearing the cap flange. Prints as oriented with no supports.

- [low] OPEN QUESTION in spec: 0.25 mm diametral clearance yields a sliding/snug fit — likely fine but unresolved in spec → Note the current fit as sliding-snug; no change required unless the user wants free rotation, in which case bump clearance to ~0.5 mm.

### no_scallops

All hard checks pass and the geometry is clean, but the design_intent 'finger scallops' on the loop are missing — the loop is a plain oblong with no indentations for finger placement.

- [medium] TOP view / detail — loop opening: Plain oblong hole with uniform straight sides; no scallops or finger-locating features → Add two shallow concave scallops (~R10–12 mm, ~1.5–2 mm deep) on the inner long edges of the loop opening, symmetric about the loop center, so each finger has a defined seat. Keep loop_inner_width ≥ 40 mm at the narrowest point between the scallops.

### hole_in_bridge

Dimensions, fit, and printability all pass and the intent features (scallops, reinforced loop, flat ring) are present, but the drawings show an unexplained small through-hole in the bridge between the ring and the loop — directly on the load path — that the spec does not call for.

- [medium] TOP / BOTTOM / SECTION A-A views, connecting bridge between neck ring and finger loop (~midway along the spine): A small circular through-hole pierces the bridge on the load path (visible in TOP detail, BOTTOM view, and SECTION A-A). → Remove the through-hole in the bridge. If a lanyard hole is actually desired, move it to a non-load-bearing location (e.g. the far end of the loop, opposite the bridge) and add it explicitly to design_intent.

### no_fillets

Meets every spec dimension, implements the reinforced-loop-with-finger-scallops intent, has a clean solid load path from loop to ring with tangent junctions, and prints flat with zero overhang in the specified orientation.

- [low] OPEN QUESTION in spec (ring rotate vs snug): current 0.25 mm clearance gives a sliding fit — snug but rotatable; not a defect, just an unresolved spec question the user may want to confirm → Confirm 0.25 mm sliding clearance is the intended behavior; if a looser rotating fit is wanted, bump clearance to ~0.4–0.5 mm.

### thin_bridge

Geometry, load path, intent features and assembly are all clean, but the overall length of 117.45 mm exceeds the 110 mm footprint cap called out in the spec. Shrink the loop (and/or shorten the connecting web) to bring the bbox within 110 mm.

- [high] TOP / FRONT views, overall_length dimension: 117.45 mm (X extent of bbox) → Reduce the loop's outer X extent by ~8 mm — e.g. shorten the loop inner width from 42 to ~36 mm (still ≥ two-finger 40 mm? no — keep ≥40; instead trim the connecting web length by ~4 mm and shave ~4 mm from the loop's far end, keeping loop_inner_width ≥40 and loop_inner_height ≥22). Target overall_length ≈ 108 mm to leave margin.

### loop_too_thick_walls_ok

Geometry, interfaces, intent features and printability are all clean, but the part is 123.45 mm long against a ≤110 mm hard cap in the spec. Shorten the spine between the ring and the finger loop.

- [high] TOP / FRONT views, footprint.overall_length: 123.45 mm — 13.45 mm over the cap → Pull the finger loop toward the ring by ~15 mm: reduce the straight spine between the ring OD and the near edge of the loop opening. loop_inner_width is already at its 40 mm floor and ring OD is mid-range (54 vs 50–58 allowed), so also consider dropping ring OD to ~51–52 mm to buy a couple more mm of margin while keeping ≥3.5 mm of ring wall.
