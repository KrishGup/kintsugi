# BOSL2 (vendored 2.0.759, verified on OpenSCAD 2021.01)

BOSL2 is on the include path of every Kintsugi compile. Every snippet below was compiled here. For any module not on this page, call `scad_docs(name="…")` — the reference holds all 980 BOSL2 modules/functions with their arguments.

```text
include <BOSL2/std.scad>              // always this one (variables + core)
include <BOSL2/threading.scad>        // threads:   threaded_rod, threaded_nut, trapezoidal_threaded_rod, …
include <BOSL2/screws.scad>           // screws:    screw, nut, screw_hole, nut_trap_inline, nut_trap_side
include <BOSL2/joiners.scad>          // snap pins, rabbit clips, dovetails
include <BOSL2/hinges.scad>           // knuckle_hinge, living_hinge_mask
include <BOSL2/gears.scad>            // spur_gear, rack, bevel gears
include <BOSL2/bottlecaps.scad>       // sp_neck / sp_cap (SPI 400/410/415 finishes), pco1810_neck / pco1810_cap
include <BOSL2/nema_steppers.scad>    // nema_mount_mask
```

Use `include`, not `use` (BOSL2 needs its constants). Never include the same file twice. `std.scad` already covers shapes, transforms, attachments, rounding, masks, sweeps, distributors, paths.

## Anchors, attachments, tags — the core idea

Every BOSL2 shape is *attachable*: it knows its faces, edges and corners, so children can be placed on them without arithmetic.

```scad
include <BOSL2/std.scad>
cuboid([40, 20, 6], anchor = BOT)                 // anchor = which point of the shape sits at the origin
    attach(TOP) cyl(h = 10, d = 8, $fn = 48);   // child's BOTTOM lands on the parent's TOP, oriented outward
```

- **Anchors**: `CENTER`, `TOP`/`BOT`, `LEFT`/`RIGHT`, `FWD`/`BACK`, and sums like `TOP+RIGHT`, `BOT+FWD+LEFT`. `anchor = BOT` puts the bottom face on z = 0 — exactly Kintsugi's bed convention.
- `attach(FACE) child` orients the child so its bottom sits on that face; `position(ANCHOR) child` only moves the child's *own* anchor to that point (keeps orientation).
- **Tagged booleans**: `diff() parent tag("remove") cutters` subtracts the tagged children from the rest; `tag("keep")` protects a child from being cut. This replaces nested `difference()` and keeps the attachment chain intact.

```scad
include <BOSL2/std.scad>
diff()
cuboid([30, 30, 10], anchor = BOT)
    tag("remove") position(TOP) cyl(h = 30, d = 6, $fn = 32);      // a through hole, overshoots both faces
```

- Transforms with names: `up(z) down(z) left(x) right(x) fwd(y) back(y)`, `xrot(a) yrot(a) zrot(a)`, `mirror_copy([1,0,0]) child` (keeps both halves).
- `$fn` still rules facets; BOSL2 shapes also honour `$fa/$fs`. Set `$fn` on the call for measured features.

## Rounded primitives (instead of minkowski)

```scad
include <BOSL2/std.scad>
cuboid([40, 20, 6], rounding = 3, edges = "Z", anchor = BOT);   // round only vertical edges (a plate outline)
```
```scad
include <BOSL2/std.scad>
cuboid([40, 20, 6], rounding = 1, anchor = BOT);                 // every edge
```
```scad
include <BOSL2/std.scad>
cyl(h = 10, d = 20, rounding1 = 2, chamfer2 = 1, anchor = BOT, $fn = 64);   // bottom edge rounded, top edge chamfered
```
```scad
include <BOSL2/std.scad>
tube(h = 6, od = 54, wall = 5.4, anchor = BOT, $fn = 128);      // ring: od/id/wall in any pair; `ifn` for the inner facets
```
```scad
include <BOSL2/std.scad>
rect_tube(size = [30, 20], wall = 2, h = 10, rounding = 3, anchor = BOT, $fn = 32);   // rounded rectangular sleeve
```
```scad
include <BOSL2/std.scad>
prismoid(size1 = [30, 20], size2 = [20, 10], h = 10, rounding = 2, anchor = BOT, $fn = 32);   // tapered block (a plug, a foot)
```
```scad
include <BOSL2/std.scad>
linear_extrude(4) rect([40, 20], rounding = [3, 3, 0, 0], $fn = 32);   // 2D: rect with per-corner rounding
```

Edge selectors: `edges = "Z"` (vertical), `edges = TOP`, `edges = [TOP+LEFT, BOT+RIGHT]`, `except = BOT` (keep the bed edge sharp for a chamfer instead). `teardrop = true` on `cuboid` keeps bottom roundings printable.

## Masks: round or chamfer an edge or a hole after the fact

```scad
include <BOSL2/std.scad>
diff() cuboid([40, 20, 10], anchor = BOT) edge_mask(TOP + RIGHT) rounding_edge_mask(l = 21, r = 4);   // one rounded edge
```
```scad
include <BOSL2/std.scad>
diff() cuboid([30, 30, 10], anchor = BOT) tag("remove") {
    cyl(h = 30, d = 8, $fn = 32);                                       // the hole
    position(TOP) rounding_hole_mask(d = 8, rounding = 1.5, $fn = 32);  // rounded entry
}
```
```scad
include <BOSL2/std.scad>
diff() cuboid([30, 30, 10], anchor = BOT) tag("remove") {
    cyl(h = 30, d = 8, $fn = 32);
    position(TOP) chamfer_cylinder_mask(d = 8, chamfer = 1, $fn = 32);  // chamfered entry
}
```
`corner_mask`, `face_mask`, `rounding_cylinder_mask`, `chamfer_edge_mask` follow the same pattern (`scad_docs(name="…")`). There is no `chamfer_hole_mask` in this version — use `chamfer_cylinder_mask`.

## Fillets at joints and rounded extrusions

```scad
include <BOSL2/std.scad>
cuboid([40, 40, 3], anchor = BOT)
    attach(TOP) cyl(h = 10, d = 12, $fn = 48)
        attach(BOT) fillet(l = 3, r = 3, $fn = 48);        // concave fillet where the boss meets the plate
```
```scad
include <BOSL2/std.scad>
// rounded top/bottom edges on an extruded outline (a region with holes is allowed; slower)
offset_sweep(rect(30, rounding = 4), height = 8, top = os_circle(r = 2), bottom = os_chamfer(1), $fn = 32);
```
```scad
include <BOSL2/std.scad>
// rounded_prism rounds the vertical edges (joint_sides) and the top/bottom edges itself: give it a PLAIN polygon
rounded_prism(rect([40, 20]), height = 6, joint_top = 1, joint_bot = 1, joint_sides = 3, $fn = 32);
```
Giving `rounded_prism` an already-rounded outline fails with "joint lengths too large" — that is the polygon's short segments, not a bug in your sizes.

## Threads and screws

```scad
include <BOSL2/std.scad>
include <BOSL2/threading.scad>
threaded_rod(d = 10, l = 15, pitch = 1.5, anchor = BOT, $fn = 48);                 // external ISO thread (M10×1.5)
```
```scad
include <BOSL2/std.scad>
include <BOSL2/threading.scad>
threaded_nut(nutwidth = 16, id = 10, h = 8, pitch = 1.5, anchor = BOT, $fn = 48);   // internal thread in a hex body
```
```scad
include <BOSL2/std.scad>
include <BOSL2/threading.scad>
trapezoidal_threaded_rod(d = 12, l = 15, pitch = 2, thread_angle = 15, anchor = BOT, $fn = 32);   // coarse, printable
```
```scad
include <BOSL2/std.scad>
include <BOSL2/screws.scad>
diff() cuboid([20, 20, 10], anchor = BOT)
    tag("remove") position(TOP) screw_hole("M4", l = 12, head = "socket", counterbore = 4, anchor = TOP, $fn = 32);
```
```scad
include <BOSL2/std.scad>
include <BOSL2/screws.scad>
diff() cuboid([20, 20, 12], anchor = BOT) tag("remove") position(TOP) nut_trap_inline(10, "M4", anchor = TOP, $fn = 32);
```
`screw("M4,10", head = "socket")` and `nut("M5")` model the fasteners themselves (for assembly views). Printed threads: pitch ≥ 1.25 mm, `$slop` (BOSL2's clearance variable, default 0) around 0.1–0.2 for FDM, or add 0.2–0.3 mm to `id` on nuts; trapezoidal threads print far better than fine ISO threads.

## Bottle necks and caps (SPI finishes)

```scad
include <BOSL2/std.scad>
include <BOSL2/bottlecaps.scad>
sp_cap(63, 400, 10, $fn = 48);       // a cap for a 63-400 finish; sp_neck(63, 400, 10) is the matching neck (type is a NUMBER)
```
Use these when the object *is* a standard SPI finish and the part must thread onto it; for a ring that slides under the cap flange, a plain `tube()` at the measured diameter is the right model.

## Joiners, hinges, gears, motors

```scad
include <BOSL2/std.scad>
include <BOSL2/joiners.scad>
snap_pin("small", $fn = 32);                  // printed snap pin; snap_pin_socket("small") is the mating socket
```
```scad
include <BOSL2/std.scad>
include <BOSL2/joiners.scad>
rabbit_clip(type = "pin", length = 12, width = 8, snap = 1, thickness = 1.2, depth = 6, $fn = 32);   // one-way snap clip
```
```scad
include <BOSL2/std.scad>
include <BOSL2/hinges.scad>
knuckle_hinge(length = 40, offset = 6, segs = 5, $fn = 32);   // print-in-place style knuckle hinge (one leaf; mirror for the other)
```
```scad
include <BOSL2/std.scad>
include <BOSL2/gears.scad>
spur_gear(circ_pitch = 5, teeth = 20, thickness = 6, $fn = 32);
```
```scad
include <BOSL2/std.scad>
include <BOSL2/nema_steppers.scad>
nema_mount_mask(17, depth = 5, l = 6, $fn = 32);   // subtract from a bracket for a NEMA 17 mount (holes + pilot)
```

## Copies and patterns

```scad
include <BOSL2/std.scad>
diff() cuboid([80, 40, 4], anchor = BOT)
    tag("remove") grid_copies(spacing = [60, 30], n = [2, 2]) cyl(h = 10, d = 4.5, $fn = 24);   // 2×2 hole pattern
```
```scad
include <BOSL2/std.scad>
zrot_copies(n = 6, r = 20) cyl(h = 4, d = 3, anchor = BOT, $fn = 16);   // bolt circle
```
`xcopies(spacing, n)`, `ycopies`, `line_copies`, `arc_copies`, `mirror_copy` are the others.

## Sweeps and lofts

```scad
include <BOSL2/std.scad>
path_sweep(circle(d = 4, $fn = 16), arc(r = 20, angle = 120, n = 24));   // a bent round bar (hook, handle)
```
```scad
include <BOSL2/std.scad>
linear_sweep(rect(20, rounding = 3), height = 10, twist = 30, $fn = 32);   // twisted extrusion
```
`skin([profile_a, profile_b], z = [...])` lofts between outlines; `top_half()` / `bottom_half()` clip a body at z (a domed cap from a sphere); `text3d("KIN", h = 1, size = 7)` is attachable 3D text.

## Things that are NOT in this version

`knurled_cylinder`, `chamfer_hole_mask`, `interior_fillet` — use `scad_docs` to find the current name before guessing. A BOSL2 call that raises `Assertion failed` is a wrong argument (read the message: it names the parameter); a WARNING "Ignoring unknown module" means the name does not exist in 2.0.759.
