# Kintsugi conventions: the customizer, the file layout, the frame, the checker's expectations

The checker, the sheets, the coupon, the sliders in the UI and the export all rely on the shape of `part.scad` described here. A part that follows it gets measured correctly on the first `iterate`.

## The file, top to bottom

```scad
// bottle handle — ring under the cap flange with a two-finger loop.
// Load path: loop -> solid bridge -> ring; print flat so the pull runs along the layers.
// Spec dims: neck_ring.inner_diameter <- neck_id (+ clearance), neck_ring.ring_height <- ring_height, load.loop_inner_width <- loop_inner_w

/* [Interface] */
neck_id = 43;            // [20:0.1:90]  the neck's outer diameter (the OBJECT, measured)
clearance = 0.25;        // [0:0.05:0.8] sliding fit; the coupon sets this
ring_height = 6;         // [3:0.5:20]

/* [Body] */
ring_wall = 4;           // [2:0.5:10]
loop_inner_w = 42;       // [25:1:80]
loop_inner_h = 26;       // [15:1:45]
loop_thick = 6;          // [4:0.5:14]
scallops = true;         // finger scallops on the loop

/* [Render] */
render_target = "part";  // [part, coupon, assembly]

/* [Hidden] */
$fn = 96;
bore = neck_id + clearance;
ring_od = bore + 2 * ring_wall;
loop_cx = ring_od / 2 + loop_inner_w / 2 + loop_thick;

assert(loop_inner_w >= 40, "two fingers need 40 mm");
echo(bore = bore, ring_od = ring_od);

module outline2d() { offset(r = -4) offset(r = 4) union() { circle(d = ring_od); translate([loop_cx, 0]) square([loop_inner_w + 2 * loop_thick, loop_inner_h + 2 * loop_thick], center = true); translate([0, -(loop_inner_h + 2 * loop_thick) / 2]) square([loop_cx, loop_inner_h + 2 * loop_thick]); } }
module openings2d() { circle(d = bore, $fn = 160); translate([loop_cx, 0]) square([loop_inner_w, loop_inner_h], center = true); }

module part() { linear_extrude(ring_height) difference() { outline2d(); openings2d(); } }

module coupon() {   // the mating feature only, three clearances, labelled
    for (i = [-1, 0, 1]) translate([i * (bore + 10), 0, 0]) {
        difference() { cylinder(d = bore + i * 0.2 + 4.8, h = 3, $fn = 96); translate([0, 0, -1]) cylinder(d = bore + i * 0.2, h = 5, $fn = 160); }
        translate([0, (bore + 4.8) / 2 + 3, 0]) linear_extrude(1) text(str(i * 0.2), size = 4, halign = "center");
    }
}

module assembly() {   // the part plus ghosted context proxies (never exported)
    part();
    %translate([0, 0, -3]) cylinder(d = neck_id, h = ring_height + 6, $fn = 96);
    %translate([0, 0, ring_height + 0.3]) cylinder(d = neck_id + 18, h = 3, $fn = 96);
}

if (render_target == "part") part(); else if (render_target == "coupon") coupon(); else assembly();
```

## Customizer rules (what becomes a slider)

- Only **top-level assignments before the first `module`/`function` definition** are parameters. Put every module after the parameter block.
- Number ranges: `// [min:max]` or `// [min:step:max]`; choices: `// [a, b, c]` (strings or numbers), labelled `// [1:one, 2:two]`; booleans need no annotation.
- `/* [Section] */` groups; `/* [Hidden] */` hides everything after it (derived values, `$fn`, constants). A comment line directly above a parameter is its description.
- Derived values (`bore = neck_id + clearance;`) are expressions and are not sliders — keep them under `[Hidden]` so the panel stays clean.
- Do not reassign a parameter later in the file (last assignment wins silently and the slider stops working).
- `render_target = "part"; // [part, coupon, assembly]` is required: Kintsugi compiles with `-D render_target="part"` for the mesh, `"coupon"` for the fit coupon and `"assembly"` for the ghosted views.

## The coordinate frame (the checker's measure recipes are written in it)

- **Z up, bed at z = 0**: the part's lowest face must sit on z = 0 (`print.on_bed` check, ±0.01). No `center = true` on the extrusion height, or translate it up.
- **Origin at the primary interface**: for a bore or ring, the bore axis is the Z axis through the origin; for a boss, the boss axis; for a slot, the slot's centre. The spec's `measure` recipes say `at_z` and `near = [x, y]` in this frame — a feature moved off the origin reads as "no hole found".
- The print orientation *is* the modeled orientation. Rotate the model, not the STL.
- Context proxies (the neck, the cap flange, a wall) are given in the same frame in `spec.context`; `assembly()` ghosts them with `%` so the sheets show the part in place, and the interference check uses them.

## What the checker reads off the mesh

- Interface dims by recipe: `circle_fit_inner`/`circle_fit_outer` fit a circle to the section at `at_z` (facets matter: `$fn ≥ 96`; 160 for press fits); `hole_extent` / `section_extent` measure widths across a section; `extent` measures along an axis (optionally within `region`); `gap` measures free space; `notch_circle`/`notch_mouth` measure clip jaws; `hole_positions` compares hole centres and diameters to `expect`; `wall_min`, `bbox`.
- The expected value already includes the fit clearance: a bore of a 43 mm neck with a 0.25 sliding clearance must measure **43.25 ± tol**. Model it as `neck_id + clearance`. A boss into a 10 mm hole measures `10 − clearance`.
- `walls.p05` (hard, ≥ `print.min_wall`, default 1.6), `walls.min` (soft), `print.overhang` (soft, ≤ 5 % beyond 45°), `print.on_bed`, `mesh.watertight`, `mesh.single_body`, `interference.<proxy>` (≤ 0.05 mm³ unless `allow_contact`).
- Read the check table in the `iterate` result, then look at the sheets: section views carry every measured dimension with pass/fail colour; the assembly views show the ghosted context.

## Iteration etiquette

- One change per iteration when chasing a number; say what and why in the `label`.
- `echo()` the derived dimension you are chasing; compare it with the measured value — if they differ, the geometry is not where you think it is (frame, `$fn`, a stray `center=true`).
- A FAIL on a dimension with the right formula usually means the section plane `at_z` misses the feature (a chamfer at that height, the feature starts higher) — move the feature to cover the plane or say so in the narration.
- When the budget message says the same checks failed three times, switch strategy: start from a template (`list_templates`), or rebuild the failing feature from a 2D profile so one parameter drives it.
- Never edit the spec to make a check pass; ask the user with `ask_user` (and request a photo when the number is a guess).
