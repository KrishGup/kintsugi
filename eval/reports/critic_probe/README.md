# Critic probe — does the code-blind critic catch what the numbers miss?

Each variant injects one defect into the passing bottle-handle template. Every variant except one keeps all hard checks green, so the critic can only catch the defect from the drawings.

| variant | injected defect | hard checks | verdict | caught |
|---|---|---|---|---|
| control | (none: control) | pass | pass | — |
| no_scallops | design intent asks for finger scallops; they are missing | pass | revise | yes |
| hole_in_bridge | a 4 mm hole drilled through the bridge, the tension load path between ring and loop | pass | revise | yes |
| no_fillets | sharp inside corners where the bridge meets the ring and the loop (stress concentration) | pass | pass | no |
| thin_bridge | the bridges between ring and loop are only 2 mm wide (thin neck in the load path) | pass | pass | no |
| loop_too_thick_walls_ok | a 14 mm thick loop wall: heavy, over-built, wastes material and makes the grip bulky | FAIL: footprint.overall_length | revise | yes |

**Catch rate: 3/5**; control verdict: pass.

### control

Meets every spec dimension, has all intent features (closed ring, reinforced loop, finger scallops), a clean solid load path from loop to ring, no unexplained features, and prints flat with zero overhang. Ready to print.

- [low] OPEN QUESTION in spec: sliding clearance of 0.25 mm (ID 43.45 vs neck 43.2) gives a slip fit that will rotate freely — consistent with the sliding fit already declared, so likely fine → no change required; the current clearance already satisfies a sliding fit, but confirm with the user if a snug/anti-rotation fit is preferred

### no_scallops

Dimensions, fit, clearance and printability all pass, but the design_intent 'reinforced loop with finger scallops' is not delivered: the loop is a plain racetrack with the same 4 mm wall as the ring — no scallops on the finger-facing edge and no local thickening.

- [medium] TOP view / detail — loop inner and outer edges: Loop is a plain oval/racetrack; inner edge is a smooth constant-radius curve with no scalloping. → Add two shallow concave scallops (~R12–15, ~2–3 mm deep) on the outer top edge of the loop (or on the inner long edges) spaced ~18–20 mm apart so each finger has a seat. Keep the remaining wall ≥ 2.5 mm.
- [medium] SECTION A-A / TOP detail — loop wall thickness: Loop wall is ~4.0 mm, identical to the ring wall and the bridge wall — no reinforcement is visible. → Thicken the loop rim to ~5–6 mm (in-plane), or increase the loop's Z-height locally (e.g. an 8–10 mm tall boss around the loop) so the finger-bearing member is stiffer and more comfortable than a thin flat strap.

### hole_in_bridge

All spec dimensions pass and the assembly clears the neck, cap flange and shoulder, but there is an unexplained small through-hole in the connecting web directly on the load path between the ring and the finger loop. The spec does not call for it, so it should be removed (or justified and dimensioned) before sign-off.

- [medium] TOP view / SECTION A-A / top detail — connecting web between neck ring and finger loop: A small circular through-hole in the middle of the connecting web, in the direct tension/bending path between the loop and the ring. → Remove the small hole in the connecting web so the load path is a continuous solid section. If it is intended as a lanyard hole, add it to the Part Spec (with diameter, position and an edge-distance requirement) and move it off the primary tension path.

### no_fillets

All spec dimensions pass and the qualitative review is clean: closed ring, tangent bridge to a scalloped finger loop, uniform ~4 mm walls, no unexplained holes or notches in the load path, and a support-free flat-on-bed print with load along the layers.

- [low] Spec open question: Chosen fit is sliding with 0.25 mm diametral clearance (snug but not free-spinning). → Confirm with the user; if free rotation is wanted, bump clearance to ~0.4–0.5 mm.

### thin_bridge

Part meets every spec dimension, has all stated intent features (reinforced loop, finger scallops, coplanar ring+loop, ring flat on bed), a clean uninterrupted load path from loop to ring, no unexplained features, and prints cleanly with 0% overhang and solid 4 mm walls. Assembly views confirm proper capture of the neck below the cap flange with correct clearance.

- [low] spec open question: 0.25 mm sliding clearance implemented, which is snug-sliding rather than free-rotating → Confirm with user that snug sliding fit is acceptable; if free rotation is required, increase clearance to ~0.4–0.6 mm.

### loop_too_thick_walls_ok

Geometry, load path, ring fit, scalloped loop, and printability are all sound, but the part is 123.45 mm long against a hard ≤110 mm footprint requirement — a spec failure that must be fixed.

- [high] TOP view / footprint.overall_length: 123.45 mm along X (ring center at X=0, loop center at X≈70.7, ring OD ≈54, loop hole ≈40 wide, plus wall) → Shorten the X extent by ~14 mm. Options: (a) reduce loop_inner_width from 40 to ~30 mm — still meets ≥40? No, must stay ≥40; instead (b) move the loop closer to the ring (reduce center-to-center from 70.7 to ~64 mm) and/or reduce the loop's outer wall from its current ~7 mm per side down to ~3–4 mm per side, keeping loop_inner_width at 40 and loop_inner_height at ≥22. Target overall length ≤108 mm to leave margin.
- [low] TOP detail view, outer boundary near ring/slab tangent (top and bottom edges): Small step/notch features where the arc meets the straight edges → Ensure the outer profile is a true tangent union (fillet or tangent arc) so no sharp micro-notches remain on the outer edge — cosmetic but easy to clean up when the length is being reworked.
