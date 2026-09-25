// TEMPLATE: control knob for a D-shaft (potentiometer / encoder / valve stem) — D-profile blind bore, fluted or ribbed grip, rounded top, optional pointer and set screw
// Interfaces: shaft_d (round diameter) and shaft_flat (dimension across the flat) + clearance -> D bore. Origin on the shaft axis;
// the bore opens downward (mouth on z = 0, knob top up), so the bore section exists at low z and the part prints as it sits on the shaft.
// Printability: the blind bore ends in a 50° cone (no flat ceiling to bridge), the mouth has a 60° lead-in chamfer, the set-screw hole is a teardrop.
// Load path: finger torque -> grip -> body -> flat of the D (and the set screw, if fitted) -> shaft.

/* [Interface] */
shaft_d = 6.0;           // [3:0.1:15]  shaft diameter (round part)
shaft_flat = 5.5;        // [2.5:0.1:15]  dimension across the flat (shaft_d minus the flat depth)
clearance = 0.2;         // [0:0.05:0.6]  added to the bore diameter (half per side)
bore_depth = 11;         // [4:0.5:30]

/* [Body] */
knob_d = 30;             // [12:1:60]
knob_h = 18;             // [8:0.5:40]
top_round = 2;           // [0:0.5:5]  round on the top edge
skirt_h = 3;             // [1:0.5:10]  plain band above the bed (measured for the outer diameter)
bed_chamfer = 0.5;       // [0:0.1:1.5]

/* [Grip] */
grip = "flutes";         // [flutes, ribs, plain]
grip_n = 12;             // [6:1:36]  number of flutes / ribs
flute_r = 2.5;           // [1:0.25:6]  flute (or rib) radius
flute_depth = 1.5;       // [0.5:0.25:4]  how deep a flute cuts in (or a rib stands out)

/* [Options] */
pointer = true;          // index wedge on the skirt
pointer_len = 5;         // [2:0.5:15]
pointer_angle = 90;      // [0:15:345]  direction of the pointer (90 = towards the flat)
set_screw = true;        // radial set-screw hole onto the flat
set_screw_d = 3.0;       // [2:0.5:6]  set screw thread diameter (M3 = 3.0)
set_screw_z = 7;         // [2:0.5:25]  height of the set-screw axis

/* [Render] */
render_target = "part";  // [part, coupon, assembly]

/* [Hidden] */
$fn = 96;
bore = shaft_d + clearance;
flat_y = shaft_flat - shaft_d / 2 + clearance / 2;      // the flat's plane (y = flat_y), bore spans y in [-bore/2, flat_y]
cone_h = (bore / 2) * tan(50);                           // 50° cone closing the blind bore
tap_hole = set_screw_d - 0.5;                            // thread-forming pilot for the set screw
grip_wall = (knob_d / 2 - flute_depth) - bore / 2;
chamfer_w = bed_chamfer / tan(60);
R = knob_d / 2;

assert(shaft_flat < shaft_d && shaft_flat > shaft_d / 2, "shaft_flat must be between shaft_d/2 and shaft_d");
assert(bore_depth + cone_h + 1.6 <= knob_h, "knob too short for the bore, its closing cone and a 1.6 mm top");
assert(grip_wall >= 1.6, "flutes cut the wall around the bore below 1.6 mm");
assert(!set_screw || (set_screw_z - tap_hole / 2 >= 1.0 && set_screw_z + tap_hole <= bore_depth), "set screw hole must lie within the bore depth");
echo(bore = bore, flat_y = flat_y, across_flat = shaft_flat + clearance, cone_apex_z = bore_depth + cone_h, grip_wall = grip_wall, tap_hole = tap_hole);

module teardrop2d(d, ang = 50, n = 56) {
    r = d / 2;
    sweep = 360 - 2 * (90 - ang);
    polygon(concat([for (i = [0 : n]) let(a = ang - i * sweep / n) [r * cos(a), r * sin(a)]], [[0, r / sin(90 - ang)]]));
}

module envelope() {
    // body of revolution: bed chamfer, straight side, rounded top edge
    rotate_extrude() polygon(concat(
        [[0, 0], [R - chamfer_w, 0], [R, bed_chamfer], [R, knob_h - top_round]],
        [for (i = [0 : 12]) let(a = i * 90 / 12) [R - top_round + top_round * cos(a), knob_h - top_round + top_round * sin(a)]],
        [[0, knob_h]]));
}

module d_bore(d, fy, depth) {
    // D-profile blind bore with a 50° closing cone and a 60° lead-in chamfer at the mouth
    ch = 0.5;
    intersection() {
        union() {
            translate([0, 0, -1]) cylinder(d = d, h = depth + 1, $fn = 128);
            translate([0, 0, depth - 0.01]) cylinder(d1 = d, d2 = 0.01, h = (d / 2) * tan(50), $fn = 128);
            translate([0, 0, -0.01]) cylinder(d1 = d + 2 * ch, d2 = d, h = ch * tan(60), $fn = 128);
        }
        translate([-d, -d, -2]) cube([2 * d, d + fy, depth + d + 2]);
    }
}

module grip_cutters() {
    // pattern phased half a pitch so a crest (not a flute) sits under the pointer and the set screw
    if (grip == "flutes") for (i = [0 : grip_n - 1]) rotate([0, 0, pointer_angle + (i + 0.5) * 360 / grip_n])
        translate([R + flute_r - flute_depth, 0, skirt_h]) cylinder(r = flute_r, h = knob_h, $fn = 48);
}

module ribs() {
    if (grip == "ribs") for (i = [0 : grip_n - 1]) rotate([0, 0, pointer_angle + (i + 0.5) * 360 / grip_n])
        translate([R - flute_r + flute_depth, 0, 0]) cylinder(r = flute_r, h = knob_h - top_round, $fn = 48);
}

module pointer_wedge() {
    if (pointer) rotate([0, 0, pointer_angle]) linear_extrude(height = skirt_h + 3)
        hull() { translate([R - 2, -3]) square([0.01, 6]); translate([R + pointer_len - 1, 0]) circle(r = 1, $fn = 24); }
}

module set_screw_hole() {
    if (set_screw) translate([0, R + 1, set_screw_z]) rotate([90, 0, 0]) linear_extrude(height = R) teardrop2d(tap_hole);
}

module part() {
    difference() {
        union() {
            difference() { envelope(); grip_cutters(); }   // flutes first, so the pointer is not cut by them
            ribs();
            pointer_wedge();
        }
        d_bore(bore, flat_y, bore_depth);
        set_screw_hole();
    }
}

module coupon() {
    // fit ladder: three D-bore bosses at clearance -0.2 / 0 / +0.2 on one plate, labels embossed
    pitch = bore + 9;
    plate = [3 * pitch + 4, bore + 14, 1.2];
    difference() {
        union() {
            translate([-plate[0] / 2, -plate[1] / 2, 0]) cube(plate);
            for (i = [-1, 0, 1]) translate([i * pitch, 0, 0]) cylinder(d = bore + 6, h = 8);
            for (i = [-1, 0, 1]) translate([i * pitch, plate[1] / 2 - 3.4, plate[2]])
                linear_extrude(0.6) text(str(i * 0.2), size = 2.6, halign = "center", $fn = 16);
        }
        for (i = [-1, 0, 1]) translate([i * pitch, 0, 0]) d_bore(bore + i * 0.2, flat_y + i * 0.1, 12);
    }
}

module assembly() {
    part();
    %translate([0, 0, -6]) intersection() {                                   // the D shaft
        cylinder(d = shaft_d, h = bore_depth + 5);
        translate([-shaft_d, -shaft_d, -1]) cube([2 * shaft_d, shaft_d + shaft_flat - shaft_d / 2, bore_depth + 7]);
    }
    %translate([0, 0, -4]) cylinder(d = knob_d + 10, h = 3);                   // the panel
    if (set_screw) %translate([0, flat_y + 0.2, set_screw_z]) rotate([-90, 0, 0]) cylinder(d = set_screw_d, h = R - flat_y - 2);
}

if (render_target == "part") part();
else if (render_target == "coupon") coupon();
else assembly();
