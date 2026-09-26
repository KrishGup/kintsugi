# Building shapes: profiles, extrusions, rounding, fillets

The fastest route to a strong, printable, *measurable* part is: draw the cross-section or outline in 2D → round it in 2D → extrude or revolve → subtract the mating features with overshooting cutters. Reach for 3D booleans of primitives when the part is a stack of simple blocks; reach for BOSL2 (`scad_guide("bosl2")`) when you need rounded edges on a 3D body or a thread.

## 1. Flat parts: outline → `offset` → `linear_extrude`

```scad
// a 40 × 20 × 4 plate with R3 outside corners, size unchanged by the rounding
linear_extrude(4) offset(r = 3) offset(delta = -3) square([40, 20], center = true);
```

- `offset(r = +R) offset(delta = -R)` rounds **convex** corners with radius R and keeps the size.
- `offset(r = -R) offset(delta = +R)` rounds **concave** (inside) corners — fillets in 2D.
- Both, one after the other, round everything: `offset(r=-2) offset(delta=2) offset(r=3) offset(delta=-3) shape();`
- `offset(delta = d, chamfer = true)` chamfers instead of rounding.
- `offset` also grows a measured outline by a clearance: `offset(delta = 0.15) neck_outline();`.

```scad
// L bracket profile with a 2 mm inside fillet and 3 mm outside rounding, extruded 20 mm wide
module L() polygon([[0, 0], [30, 0], [30, 6], [6, 6], [6, 30], [0, 30]]);
linear_extrude(20) offset(r = 3) offset(delta = -3) offset(r = -2) offset(delta = 2) L();
```

## 2. Round parts: cross-section → `rotate_extrude`

The profile is drawn in XY with X = radius and Y = height, all at x ≥ 0, then revolved around Z.

```scad
// ring: bore 43.25 (43 + 0.25 clearance), OD 54, 6 mm tall, 1 mm entry chamfer on the bore, R1 outer edges
ri = 43.25 / 2; ro = 54 / 2; h = 6;
rotate_extrude($fn = 128)
    offset(r = 1) offset(delta = -1)                       // round the outer corners
    polygon([[ri + 1, 0], [ro, 0], [ro, h], [ri, h], [ri, 1]]);   // chamfer at the bottom of the bore
```

Rules: `$fn` on `rotate_extrude` sets the facets around the axis (the measured bore comes from this); `angle = 300` makes a C-shaped ring; a profile crossing x = 0 is an error ("all points must have the same sign").

## 3. Rounded 3D bodies without minkowski

```scad
// capsule / rounded bar by hull of spheres
hull() { sphere(d = 8, $fn = 32); translate([40, 0, 0]) sphere(d = 8, $fn = 32); }
```

```scad
// rounded plate by hull of four cylinders (fast, exact radii)
hull() for (x = [-17, 17], y = [-7, 7]) translate([x, y, 0]) cylinder(h = 4, r = 3, $fn = 32);
```

```scad
// bridge between a ring and a loop: hull of the two footprints, then cut the holes afterwards
difference() {
    hull() { cylinder(h = 6, d = 54, $fn = 96); translate([70, 0, 0]) cylinder(h = 6, d = 34, $fn = 96); }
    translate([0, 0, -1]) cylinder(h = 8, d = 43.25, $fn = 128);
    translate([70, 0, -1]) cylinder(h = 8, d = 26, $fn = 96);
}
```

`hull()` discards concavities — union several hulls for a concave body. `minkowski() { body; sphere(r); }` rounds every edge but grows the body by r and costs seconds to minutes in CGAL; use it only for small bodies with `$fn ≤ 24` on the sphere.

With BOSL2 the same is one call: `cuboid([40, 20, 4], rounding = 3, edges = "Z")` (vertical edges only), `cuboid(size, rounding = 1)` (all edges), `cyl(h, d, rounding1 = , rounding2 = )`, `rounded_prism()` for a rounded extrusion, `offset_sweep()` for a profile with rounded top/bottom edges.

## 4. Fillets at junctions (where parts snap)

A loop meeting a ring, a tab meeting a plate, a boss meeting a base: the inside corner is the stress riser. Three ways:

```scad
// (a) 2D: fillet the concave corners of the outline before extruding (best for flat parts)
module outline() { circle(d = 54, $fn = 96); translate([40, 0]) square([60, 16], center = true); }
linear_extrude(6) offset(r = -4) offset(delta = 4) outline();
```

```scad
// (b) 3D: a hull "web" that blends a boss into a plate
cube([40, 40, 3]);
hull() { translate([20, 20, 3 - 0.01]) cylinder(h = 0.02, d = 22, $fn = 48); translate([20, 20, 3]) cylinder(h = 10, d = 12, $fn = 48); }
```

```scad
// (c) BOSL2 masks: subtract a rounding mask along an edge, or add a fillet at a joint
include <BOSL2/std.scad>
diff() cuboid([40, 20, 10]) edge_mask(TOP + RIGHT) rounding_edge_mask(l = 21, r = 4);
cuboid([40, 40, 3], anchor = BOT) attach(TOP) cyl(h = 10, d = 12, $fn = 48) attach(BOT) fillet(l = 3, r = 3, $fn = 48);
```

## 5. Chamfers and the bed edge

Chamfer the edge that touches the bed by 0.4–0.6 mm to counter elephant's foot and make the part lift off cleanly:

```scad
// 45° bed chamfer on a cylinder by a truncated cone at the bottom
c = 0.5; h = 6; d = 54;
union() { cylinder(h = c, d1 = d - 2 * c, d2 = d, $fn = 128); translate([0, 0, c - 0.01]) cylinder(h = h - c + 0.01, d = d, $fn = 128); }
```

For a bore entry, a 0.5–1 mm chamfer (a cone on the cutter) makes the part slide on; for a boss, a chamfer on the leading edge does the same.

## 6. Holes that print

- Vertical holes print round. Add 0.1–0.2 mm to the diameter for FDM shrink if the fit is close.
- Horizontal holes sag at the top. Use a **teardrop** (a circle with a 45° point on top) or a small flat at the top so no overhang exceeds 45°:

```scad
// horizontal 6 mm teardrop hole through a 20 mm block, hole axis along Y
module teardrop(d, l) rotate([90, 0, 0]) linear_extrude(l, center = true)
    union() { circle(d = d, $fn = 48); rotate(45) square([d / 2, d / 2]); }
difference() { cube([20, 20, 20], center = true); teardrop(6, 30); }
```

- Countersinks and counterbores are cones/cylinders on the cutter. Hex nut traps: a `cylinder($fn = 6)` with the *circumradius* = across-flats / cos(30) + clearance.

## 7. Twists, tapers and sweeps

- `linear_extrude(h, scale = 0.8)` tapers (plugs, funnels); `twist = 30` twists (knurl-like grips).
- BOSL2 `linear_sweep()` and `path_sweep()` sweep a 2D profile along a path (hooks, handles with a bent bar); `rotate_sweep()`/`rotate_extrude` revolve.
- Lofts between two different outlines: BOSL2 `skin()`; avoid hand-written `polyhedron()`.

## 8. Text

`linear_extrude(1) text("KIN", size = 7, halign = "center")` embosses; subtract it 0.6–1 mm deep to engrave. Keep strokes ≥ 0.8 mm (two extrusion widths). `textmetrics()` does not exist in 2021.01 — leave margin instead of measuring.

## 9. Checklist before `iterate`

- Every cutter overshoots by ≥ 1 mm; unions overlap by ≥ 0.01 mm.
- Measured bores/bosses have `$fn ≥ 96`, set on the primitive (or on `rotate_extrude`).
- The bed is z = 0 and the part's lowest face sits on it; the primary interface axis is at the origin.
- No `%` on anything that must be exported; `%` on every context proxy.
- `echo()` the derived dimensions; `assert()` the hard constraints.
