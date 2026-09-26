# Design for FDM printing (the numbers Kintsugi's checker enforces, and the ones it does not)

Assume a 0.4 mm nozzle, 0.2 mm layers, PLA/PETG unless the spec's `print` block says otherwise. The checker measures walls, overhang, bed contact, interference and every interface dimension; it cannot measure strength, so the rules below are yours to apply.

## Walls and features

| feature | minimum | why |
|---|---|---|
| wall (structural) | 2 perimeters = **1.6 mm** at 0.4 nozzle (`print.min_wall`; the hard check is the 5th-percentile wall) | one perimeter splits |
| wall (cosmetic skirt) | 1.2 mm | `walls.min` soft check at 0.75 × min_wall |
| post / pin | ≥ 3 mm diameter, add a fillet at the root | bending snaps posts at the root |
| embossed text / rib | ≥ 0.8 mm wide, 0.4–1 mm tall | one extrusion width is fragile |
| hole (vertical) | ≥ 1.5 mm; add 0.1–0.2 mm to the diameter for close fits | perimeters shrink holes |
| slot | ≥ 1.0 mm wide | narrower fuses |
| gap between parts printed together | ≥ 0.3 mm (0.4 for TPU) | otherwise they weld |

Thicker is not free: a solid 14 mm loop wall prints slowly, warps and looks over-built — the critic flags it. Two to four perimeters plus infill is the strength sweet spot; put material where the load path is (see below), not everywhere.

## Fit clearances (mm on the diameter, applied by the checker to the mating dimension)

| fit | PLA | PETG / ABS / ASA | Nylon | TPU | use |
|---|---|---|---|---|---|
| press | 0.10 | 0.10 | 0.10 | 0.00 | pushed on once, stays |
| snap | 0.15 | 0.20 | 0.20 | 0.10 | clips over a lip |
| sliding | 0.25 | 0.30 | 0.35 | 0.30 | slides on, does not rattle (a ring under a cap flange) |
| loose | 0.40 | 0.45 | 0.50 | 0.60 | free rotation, easy assembly |

Rules the checker assumes: a **bore** that receives the object is modeled at `target + clearance`; a **boss** that enters the object at `target − clearance`; a **slot** width at `target + clearance`. Keep `clearance` as its own parameter (the coupon changes it). Horizontal holes (axis parallel to the bed) need +0.2 mm on the vertical axis because the top sags. When a fit is press or snap and the dimension is only estimated, the coupon decides — design for the middle value.

## Overhangs and bridges

- Overhangs up to **45°** print clean; the checker reports `print.overhang` as the surface fraction beyond 45° (5 % is the soft limit). Chamfer the underside of anything that sticks out (`cylinder(d1 = , d2 = )` cones, 45° `offset(delta, chamfer = true)` profiles) instead of a square shelf.
- Bridges up to ~20 mm are fine flat; a hole through a horizontal boss needs a teardrop or a 0.2 mm sacrificial layer.
- Horizontal holes: teardrop (45° roof) or a flat top; see `scad_guide("shapes")` §6.
- The first layer spreads (elephant's foot): chamfer the bed edge 0.4–0.6 mm, or the checker's `print.on_bed` face is right but the real part is 0.2 mm wider at the base.

## Orientation and the load path

FDM parts are strong along layers and weak across them (the layer bond is ~50–70 % of the material's strength in PLA, worse in PETG for peeling). So:

- Print the part in the orientation it is modeled — `print.on_bed` requires the lowest face on z = 0 — and choose that orientation so the **tension runs along the layers**: a carry handle flat on the bed (the loop's pull is in-plane), a hook with its hook profile in the XY plane, a clip's flexing cantilever parallel to the bed.
- Cantilevers and snap arms that flex must lie *in* the layer plane; a snap arm printed standing up delaminates on the second flex.
- Where a thin section meets a thick one (loop → ring, tab → plate), fillet the inside corner (r ≥ 2 mm) — the checker cannot see stress, the critic will look for it.
- Round or chamfer outside edges lightly (0.5–1 mm): fewer stress risers, nicer in the hand.

## Snap fits and flexures (quick sizing)

For a cantilever snap arm of length L, thickness t, deflection y at the catch: the strain at the root is ε ≈ 1.5·y·t / L². Keep ε below **1 %** for PLA, **2 %** for PETG/ABS, **5 %** for nylon. Example: L = 15, t = 1.6, y = 1.0 → ε = 1.5·1.0·1.6/225 = 1.07 % — marginal in PLA, fine in PETG. Longer arms or thinner sections reduce strain; taper the arm (thicker at the root) to spread it. Lead-in ramp 30–45°, retention face 60–90°.

Living hinges only survive in PP/nylon/TPU; in PLA/PETG use a pin hinge (BOSL2 `knuckle_hinge`) or a separate part.

## Threads, inserts, screws

- Printed threads: pitch ≥ 1.25 mm (M8 coarse or coarser), or trapezoidal/buttress threads — BOSL2 `threaded_rod` / `threaded_nut` / `trapezoidal_threaded_rod`; add 0.2–0.3 mm on the diameter of the internal thread for FDM.
- For real screws into plastic: a plain hole at the screw's *minor* diameter (M3 → 2.5, M4 → 3.3, M5 → 4.2) for thread-forming, or a heat-set insert pocket (M3 → 4.0 × 5.7 deep, M4 → 5.6 × 8.1, M5 → 6.4 × 9.5 — check the insert's datasheet).
- Clearance holes (medium fit): M3 3.4, M4 4.5, M5 5.5, M6 6.6, M8 9.0 — `screw_hole("M4")` in BOSL2 knows these.
- Nut traps: hex across-flats (M3 5.5, M4 7, M5 8, M6 10, M8 13) + 0.2–0.3 mm; model the hexagon with `cylinder($fn = 6, d = AF / cos(30) + 0.3)` (that `d` is the corner-to-corner diameter).

## Materials in one line each

PLA: stiff, precise, brittle in impact, creeps warm — handles and brackets indoors. PETG: tougher, a little stringy, slightly flexible — outdoor and load-bearing; over-extrudes 0.1 mm on fits. ABS/ASA: heat and UV — cars, sun. TPU: flexible; clearances go up, features go bigger, press fits become interference. Nylon: strongest, slippery, absorbs water; fits loosen 0.1 mm as it hydrates.

## What the checker will say

`walls.p05` FAIL → somewhere a wall is under `min_wall`: look at the section sheet for the thin skirt, boss or bridge. `print.overhang` warn → the underside of a feature; chamfer it. `interference.<context>` FAIL → the part occupies the object's space: check the origin/frame and the clearance sign. `print.on_bed` FAIL → the part floats or sinks: translate it so the lowest face is z = 0.
