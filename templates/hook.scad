// TEMPLATE: wall / rail J-hook — a mounting plate with two screw holes and a J-shaped hook with a rated load; filleted root, rounded tip
// Interfaces: mount_holes (two horizontal holes through the plate, screw_d + clearance). The plate's back face is the wall: x = 0.
// Origin at the wall face, midway between the screws (y = 0); the hook curls out along +X; the part is extruded along Z (its width).
// Print orientation: ON ITS SIDE — the J profile lies flat on the bed (z = 0 is one side face) so the layers run along the shank and
// curl; the bending load then runs along the layers, not across them. In use, +Y points up: the shank is at the plate's lower end.
// Load path: hung load -> curl -> shank (cantilever, sized by the bending rule below) -> root fillet -> plate -> upper screw in tension.

/* [Interface] */
screw_d = 4.0;           // [2:0.1:8]  screw shank diameter (M4 = 4.0)
clearance = 0.5;         // [0:0.05:1]  added to the hole diameter
hole_spacing = 30;       // [12:1:100]  centre distance between the two screws (along the plate)

/* [Plate] */
plate_t = 4;             // [2.4:0.2:10]
plate_len = 50;          // [20:1:150]
width = 20;              // [8:1:60]  hook width (extrusion along Z)

/* [Hook] */
reach = 30;              // [12:1:80]  from the wall face to the outside of the tip
throat_r = 8;            // [3:0.5:30]  inside radius of the curl (half the rod / strap thickness it accepts)
arm_t = 6;               // [3:0.5:15]  shank and curl thickness
tip_len = 10;            // [0:1:40]  straight tip rising from the curl
root_fillet = 4;         // [0:0.5:12]  fillet where the shank meets the plate

/* [Rating] */
rated_load_kg = 5;       // [0.5:0.5:30]
safety_factor = 3;       // [1.5:0.5:6]
strength_mpa = 30;       // [10:1:80]  tensile strength of the printed material along the layers (PETG ~ 30, PLA ~ 45)

/* [Render] */
render_target = "part";  // [part, coupon, assembly]

/* [Hidden] */
$fn = 96;
hole = screw_d + clearance;
teardrop_angle = 50;                                   // roof angle of the horizontal holes
y0 = -plate_len / 2;                                   // plate lower end (the shank's underside is flush with it)
x_c = reach - throat_r - arm_t;                        // curl centre x
y_c = y0 + arm_t + throat_r;                           // curl centre y
shank_len = x_c - plate_t;
load_n = rated_load_kg * 9.81;
moment_nmm = load_n * (x_c - plate_t);                 // load hangs at the curl centre line
stress_mpa = 6 * moment_nmm / (width * arm_t * arm_t);
allowable_mpa = strength_mpa / safety_factor;
arm_t_needed = sqrt(6 * moment_nmm / (width * allowable_mpa));
upper_screw_pull_n = load_n * x_c / hole_spacing;

assert(shank_len >= root_fillet + 2, "reach too short for the curl, the shank and the root fillet");
assert(stress_mpa <= allowable_mpa, str("shank overstressed: needs arm_t >= ", arm_t_needed, " mm for ", rated_load_kg, " kg"));
assert(hole_spacing / 2 + hole / 2 + 1.6 <= plate_len / 2 - 0, "screw holes too close to the plate ends");
assert(width - hole >= 3.2, "plate too narrow for the holes");
echo(hole = hole, shank_len = shank_len, curl_centre = [x_c, y_c], stress_mpa = stress_mpa, allowable_mpa = allowable_mpa,
     arm_t_needed = arm_t_needed, upper_screw_pull_n = upper_screw_pull_n);

module teardrop2d(d, ang, n = 56) {
    r = d / 2;
    sweep = 360 - 2 * (90 - ang);
    polygon(concat([for (i = [0 : n]) let(a = ang - i * sweep / n) [r * cos(a), r * sin(a)]], [[0, r / sin(90 - ang)]]));
}

// J profile in the XY plane
module profile2d() {
    union() {
        translate([0, y0]) square([plate_t, plate_len]);                                      // plate
        translate([plate_t - 0.01, y0]) square([shank_len + 0.02, arm_t]);                   // shank
        translate([x_c, y_c]) intersection() {                                                // quarter curl
            difference() { circle(r = throat_r + arm_t); circle(r = throat_r); }
            translate([0, -throat_r - arm_t - 1]) square([throat_r + arm_t + 1, throat_r + arm_t + 1]);
        }
        translate([x_c + throat_r, y_c - 0.01]) square([arm_t, tip_len + 0.01]);              // tip
        translate([x_c + throat_r + arm_t / 2, y_c + tip_len]) circle(d = arm_t);            // rounded tip end
        if (root_fillet > 0) translate([plate_t, y0 + arm_t]) difference() {                 // root fillet
            square([root_fillet, root_fillet]);
            translate([root_fillet, root_fillet]) circle(r = root_fillet);
        }
    }
}

module holes() {
    for (s = [-1, 1]) translate([-1, s * hole_spacing / 2, width / 2]) rotate([90, 0, 90])
        linear_extrude(height = plate_t + 2) teardrop2d(hole, teardrop_angle);
}

module part() { difference() { linear_extrude(height = width) profile2d(); holes(); } }

module coupon() {
    // hole ladder: a strip of the plate with three teardrop holes at clearance -0.2 / 0 / +0.2, printed like the part (on its side)
    difference() {
        union() {
            translate([0, -24, 0]) cube([plate_t, 48, 14]);
            for (i = [-1, 0, 1]) translate([plate_t, i * 16, 11]) rotate([90, 0, 90]) linear_extrude(0.6) text(str(i * 0.2), size = 2.4, halign = "center", $fn = 16);
        }
        for (i = [-1, 0, 1]) translate([-1, i * 16, 5.5]) rotate([90, 0, 90]) linear_extrude(height = plate_t + 2) teardrop2d(hole + i * 0.2, teardrop_angle);
    }
}

module assembly() {
    part();
    %translate([-6, y0 - 10, -10]) cube([6, plate_len + 20, width + 20]);                          // wall
    for (s = [-1, 1]) %translate([-12, s * hole_spacing / 2, width / 2]) rotate([0, 90, 0]) cylinder(d = screw_d, h = 12 + plate_t + 4);
    %translate([x_c, y_c - 1.7, -5]) cylinder(d = 2 * throat_r - 4, h = width + 10);               // the hung rod
}

if (render_target == "part") part();
else if (render_target == "coupon") coupon();
else assembly();
