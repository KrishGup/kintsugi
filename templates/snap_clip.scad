// TEMPLATE: cantilever snap-fit edge clip — a U channel that snaps over the edge of a rail / panel of given thickness; rigid jaw, flexing arm with a barb, lead-in chamfers, root fillets, and a mounting ear with a screw hole
// Interfaces: rail_slot (slot width = rail_t + clearance, along Y; the rail edge enters along -X and seats on the floor x = 0) and mount_hole (screw through the ear, along X).
// Origin: slot floor (back plate inner face) at x = 0, slot centred on y = 0, bottom of the extrusion on z = 0.
// The rail seats against the floor between the root fillets (its corners ride ~0.2 mm up them); catch_gap covers that.
// Print orientation: STANDING, the U profile flat on the bed and extruded up Z (the clip's length along the rail). The arm then bends
// within the layer plane, so the flex stress runs along the layers instead of prying them apart. No overhangs: the screw hole is a teardrop.
// Beam rule (straight cantilever, uniform section): deflection y = eps * L^2 / (1.5 * h)  ->  L_min = sqrt(1.5 * h * y / eps).

/* [Interface] */
rail_t = 3.0;            // [1:0.1:12]  rail / panel thickness
clearance = 0.3;         // [0:0.05:0.8]  added to the slot width
rail_w = 12;             // [5:0.5:40]  how far the rail edge goes into the clip (slot depth to the barb)
screw_d = 3.0;           // [2:0.1:6]  mounting screw diameter (M3 = 3.0)
hole_clearance = 0.4;    // [0:0.05:1]

/* [Snap] */
arm_t = 1.8;             // [1.2:0.1:4]  flexing arm thickness (h)
catch = 1.0;             // [0.4:0.1:3]  barb height = arm tip deflection (y)
catch_angle = 90;        // [45:5:90]  retaining face angle; 90 = permanent hook, 45 = releasable
barb_len = 3;            // [1.5:0.25:8]  lead-in ramp length
barb_flat = 0.6;         // [0:0.1:2]
catch_gap = 0.5;         // [0:0.05:1]  gap between the rail edge and the retaining face (the rail corners ride ~0.2 mm up the root fillets)
max_strain = 0.03;       // [0.01:0.005:0.06]  allowable strain (PETG ~0.03, PLA ~0.02, nylon ~0.05)
modulus_mpa = 2000;      // [1000:100:4000]  flexural modulus, for the insertion-force estimate only

/* [Body] */
depth = 12;              // [6:1:40]  clip length along the rail (extrusion, Z)
jaw_t = 3;               // [2:0.25:8]  rigid jaw thickness
base_t = 3;              // [2:0.25:8]  back plate / ear thickness
ear_w = 9;               // [6:0.5:20]  mounting ear width (beyond the rigid jaw)
root_fillet = 0.6;       // [0:0.1:2]  fillets in the slot floor corners (arm root) and at the ear; a sharp-cornered rail seats r*(1-cos45°) off the floor
lead_in = 1;             // [0.4:0.1:2]  chamfer on the rigid jaw's inner tip (guides the rail in)

/* [Render] */
render_target = "part";  // [part, coupon, assembly]

/* [Hidden] */
$fn = 96;
w = rail_t + clearance;                       // slot width
hole = screw_d + hole_clearance;
xb = rail_w + catch_gap;                      // retaining face
tip_x = xb + barb_flat + barb_len + catch / tan(catch_angle);
arm_len = xb;                                 // effective cantilever length (root plane x = 0 to the retaining face)
arm_len_min = sqrt(1.5 * arm_t * catch / max_strain);
insertion_force_n = depth * arm_t * arm_t * modulus_mpa * max_strain / (6 * arm_len);
y_ear = -(w / 2 + jaw_t + ear_w / 2);
opening = w - catch;

assert(arm_len >= arm_len_min, str("arm too short for the catch: rail_w + catch_gap must be >= ", arm_len_min, " mm (or lower catch / thinner arm)"));
assert(opening > 0.5, "barb closes the slot; reduce catch");
assert(arm_t >= 1.2, "arm thinner than 1.2 mm will not print reliably");
assert(ear_w >= hole + 3.2, "ear too narrow for the screw hole with 1.6 mm walls");
assert(depth >= hole / sin(40) + 3.2, "clip too short (Z) for the screw hole");
echo(slot_width = w, opening_at_tips = opening, arm_len = arm_len, arm_len_min = arm_len_min, insertion_force_n = insertion_force_n, hole = hole, ear_centre_y = y_ear);

module teardrop2d(d, ang = 50, n = 56) {
    r = d / 2;
    sweep = 360 - 2 * (90 - ang);
    polygon(concat([for (i = [0 : n]) let(a = ang - i * sweep / n) [r * cos(a), r * sin(a)]], [[0, r / sin(90 - ang)]]));
}

module fillet2d(r) { difference() { square([r, r]); translate([r, r]) circle(r = r, $fn = 32); } }

// U profile in the XY plane
module profile2d() {
    union() {
        translate([-base_t, y_ear - ear_w / 2]) square([base_t, ear_w + jaw_t + w + arm_t]);                // back plate + ear
        translate([-base_t, -w / 2 - jaw_t]) square([tip_x + base_t, jaw_t]);                              // rigid jaw
        translate([-base_t, w / 2]) square([tip_x + base_t, arm_t]);                                       // arm
        // barb on the arm's inner face: retaining face, flat, lead-in ramp
        polygon([[xb, w / 2 + 0.01], [xb + catch / tan(catch_angle), w / 2 - catch], [xb + catch / tan(catch_angle) + barb_flat, w / 2 - catch], [tip_x, w / 2 + 0.01]]);
        if (root_fillet > 0) {
            translate([0, w / 2]) mirror([0, 1]) fillet2d(root_fillet);                                  // arm root
            translate([0, -w / 2]) fillet2d(root_fillet);                                                // rigid jaw root
            translate([0, -w / 2 - jaw_t]) mirror([0, 1]) fillet2d(root_fillet);                         // ear / jaw corner
        }
    }
}

module tip_chamfers2d() {
    // lead-in on the rigid jaw's inner tip; small chamfers on both outer tips
    translate([tip_x, -w / 2]) polygon([[0.01, -lead_in], [0.01, 0.01], [-lead_in, 0.01]]);
    translate([tip_x, -w / 2 - jaw_t]) polygon([[0.01, 0.6], [0.01, -0.01], [-0.6, -0.01]]);
    translate([tip_x, w / 2 + arm_t]) polygon([[0.01, -0.6], [0.01, 0.01], [-0.6, 0.01]]);
}

module mount_hole() {
    translate([-base_t - 1, y_ear, depth / 2]) rotate([90, 0, 90]) linear_extrude(height = base_t + 2) teardrop2d(hole);
}

module part() {
    difference() {
        linear_extrude(height = depth) difference() { profile2d(); tip_chamfers2d(); }
        mount_hole();
    }
}

module coupon() {
    // slot ladder: a comb with three plain slots at clearance -0.2 / 0 / +0.2 (no barb), printed standing like the part
    pitch = w + 6;
    difference() {
        union() {
            translate([-base_t, -pitch * 1.5 - 1, 0]) cube([base_t + 8, 3 * pitch + 2, depth]);
            for (i = [-1, 0, 1]) translate([-base_t, i * pitch, depth - 3]) rotate([90, 0, -90]) linear_extrude(0.6) text(str(i * 0.2), size = 2.2, halign = "center", valign = "center", $fn = 16);
        }
        for (i = [-1, 0, 1]) translate([0, i * pitch - (w + i * 0.2) / 2, -1]) cube([9, w + i * 0.2, depth + 2]);
    }
}

module assembly() {
    part();
    %translate([0, -rail_t / 2, -5]) cube([rail_w, rail_t, depth + 10]);                  // the rail edge, seated
    %translate([-base_t - 4, y_ear - ear_w / 2 - 6, -6]) cube([4, ear_w + 26, depth + 12]); // the wall
    %translate([-base_t - 6, y_ear, depth / 2]) rotate([0, 90, 0]) cylinder(d = screw_d, h = base_t + 8);
}

if (render_target == "part") part();
else if (render_target == "coupon") coupon();
else assembly();
