// TEMPLATE: L bracket — a base leg screwed to a shelf/floor and a vertical leg screwed to a wall/panel, two holes per leg (plain or countersunk), inside-corner fillet, optional centre gusset
// Interfaces: base_holes (vertical, through the base leg) and wall_holes (horizontal, through the vertical leg), both screw_d + clearance.
// Origin at the outer corner: the wall face is x = 0, the bed/shelf face is z = 0, the bracket is centred on y. Base leg along +X, vertical leg up +Z.
// Load path: shelf load on the base -> inside fillet (+ gusset) -> vertical leg -> wall screws. Prints base-down, no supports:
// the vertical-leg holes are teardrops (50° roof) so their ceilings need no bridging.

/* [Interface] */
screw_d = 4.0;           // [2:0.1:10]  screw shank diameter (M4 = 4.0)
clearance = 0.5;         // [0:0.05:1]  added to the hole diameter
hole_spacing = 16;       // [6:1:60]  centre distance between the two holes of a leg (across the width)
hole_inset = 12;         // [5:0.5:40]  hole centre from the free end of each leg

/* [Legs] */
leg_a = 50;              // [20:1:120]  base leg length (along X)
leg_b = 50;              // [20:1:120]  vertical leg height (along Z)
width = 30;              // [12:1:80]
thickness = 5;           // [2.4:0.2:12]
inner_fillet = 4;        // [0:0.5:10]  fillet in the inside corner
bed_chamfer = 0.5;       // [0:0.1:1.5]  60° chamfer on the bed-side profile corners

/* [Reinforcement] */
gusset = true;           // triangular centre gusset in the inside corner
gusset_len = 20;         // [5:1:60]  gusset leg length along each leg
gusset_t = 4;            // [2:0.5:10]  gusset thickness (along Y)

/* [Holes] */
countersink = false;     // 90° countersink on the screw-head side (top of the base, inside of the vertical leg)
cs_d = 9;                // [4:0.5:20]  countersink diameter at the surface (when countersink)
teardrop_angle = 50;     // [45:1:70]  roof angle of the horizontal holes, from horizontal (> 45° prints without support)

/* [Render] */
render_target = "part";  // [part, coupon, assembly]

/* [Hidden] */
$fn = 96;
hole = screw_d + clearance;
t = thickness;
base_hole_x = leg_a - hole_inset;
wall_hole_z = leg_b - hole_inset;
cs_depth = (cs_d - hole) / 2;                      // 90° countersink
chamfer_w = bed_chamfer / tan(60);
edge_margin = width / 2 - hole_spacing / 2 - hole / 2;

assert(edge_margin >= 1.6, "holes too close to the side edges (need 1.6 mm)");
assert(hole_inset - hole / 2 >= 1.6, "hole_inset too small for the free end wall");
assert(base_hole_x - hole / 2 > t + inner_fillet + (gusset ? gusset_len : 0), "base holes overlap the corner fillet / gusset");
assert(wall_hole_z - hole / 2 > t + inner_fillet + (gusset ? gusset_len : 0), "wall holes overlap the corner fillet / gusset");
assert(!gusset || hole_spacing / 2 - hole / 2 - gusset_t / 2 >= 1.6, "gusset too close to the holes");
assert(!countersink || cs_depth < t - 1.2, "countersink deeper than the leg allows");
assert(t >= 2.4, "legs thinner than 2.4 mm will not hold screws");
echo(hole = hole, base_holes = [[base_hole_x, -hole_spacing / 2], [base_hole_x, hole_spacing / 2]],
     wall_holes = [[-hole_spacing / 2, wall_hole_z], [hole_spacing / 2, wall_hole_z]], edge_margin = edge_margin);

// L profile in the XZ plane (2D x -> X, 2D y -> Z)
module profile2d() {
    union() {
        polygon([[chamfer_w, 0], [leg_a - chamfer_w, 0], [leg_a, bed_chamfer], [leg_a, t], [t, t], [t, leg_b], [0, leg_b], [0, bed_chamfer]]);
        if (inner_fillet > 0) translate([t, t]) difference() { square([inner_fillet, inner_fillet]); translate([inner_fillet, inner_fillet]) circle(r = inner_fillet); }
    }
}

module teardrop2d(d, ang, n = 56) {
    // circle of diameter d with a pointed roof whose faces are `ang` degrees from horizontal (apex on +Y)
    r = d / 2;
    sweep = 360 - 2 * (90 - ang);
    polygon(concat([for (i = [0 : n]) let(a = ang - i * sweep / n) [r * cos(a), r * sin(a)]], [[0, r / sin(90 - ang)]]));
}

module body() {
    rotate([90, 0, 0]) linear_extrude(height = width, center = true) profile2d();
    if (gusset) rotate([90, 0, 0]) linear_extrude(height = gusset_t, center = true)
        polygon([[t - 0.01, t - 0.01], [t + gusset_len, t - 0.01], [t - 0.01, t + gusset_len]]);
}

module base_holes() {
    for (s = [-1, 1]) translate([base_hole_x, s * hole_spacing / 2, 0]) {
        translate([0, 0, -1]) cylinder(d = hole, h = t + 2, $fn = 64);
        if (countersink) translate([0, 0, t - cs_depth]) cylinder(d1 = hole, d2 = cs_d + 2, h = cs_depth + 1, $fn = 64);
    }
}

module wall_holes() {
    // horizontal along X, teardrop apex up (+Z); countersink on the inside face (x = t)
    for (s = [-1, 1]) translate([0, s * hole_spacing / 2, wall_hole_z]) {
        translate([-1, 0, 0]) rotate([90, 0, 90]) linear_extrude(height = t + 2) teardrop2d(hole, teardrop_angle);
        if (countersink) translate([t - cs_depth, 0, 0]) rotate([0, 90, 0]) cylinder(d1 = hole, d2 = cs_d + 2, h = cs_depth + 1, $fn = 64);
    }
}

module part() { difference() { body(); base_holes(); wall_holes(); } }

module coupon() {
    // hole ladder: a strip with three vertical holes at clearance -0.2 / 0 / +0.2 and three teardrop holes (printed standing) to test the horizontal-hole fit
    difference() {
        union() {
            translate([-25, -8, 0]) cube([50, 16, t]);
            for (i = [-1, 0, 1]) translate([i * 15, 8 - 3, t]) linear_extrude(0.6) text(str(i * 0.2), size = 2.6, halign = "center", $fn = 16);
        }
        for (i = [-1, 0, 1]) translate([i * 15, -2, -1]) cylinder(d = hole + i * 0.2, h = t + 2, $fn = 64);
    }
    translate([-25, -32, 0]) difference() {
        cube([50, t, 14]);
        for (i = [-1, 0, 1]) translate([25 + i * 15, -1, 7]) rotate([-90, 0, 0]) rotate([0, 0, 180]) linear_extrude(height = t + 2) teardrop2d(hole + i * 0.2, teardrop_angle);
    }
    translate([-25, -32 + t - 0.01, 0]) cube([50, 8 - (-32 + t) + 0.02, 1.2]);   // bridge so the coupon is one piece
}

module assembly() {
    part();
    %translate([-6, -width / 2 - 10, -6]) cube([6, width + 20, leg_b + 16]);      // wall
    %translate([-6, -width / 2 - 10, -6]) cube([leg_a + 16, width + 20, 6]);      // shelf / floor
    for (s = [-1, 1]) {
        %translate([base_hole_x, s * hole_spacing / 2, -8]) cylinder(d = screw_d, h = t + 8 + 4);
        %translate([-12, s * hole_spacing / 2, wall_hole_z]) rotate([0, 90, 0]) cylinder(d = screw_d, h = 12 + t + 4);
    }
}

if (render_target == "part") part();
else if (render_target == "coupon") coupon();
else assembly();
