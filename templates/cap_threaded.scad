// TEMPLATE: threaded cap — an internally threaded closed cap for a bolt end, threaded neck or pipe (ISO 60° profile via BOSL2), ribbed grip, plain rim, closed top
// Interfaces: neck_thread (thread nominal diameter + pitch of the mating external thread) + clearance -> internal thread. Origin on the thread axis.
// Print orientation: CLOSED TOP ON THE BED, mouth up (z = 0 is the outside of the top). The mouth has a plain lead-in counterbore at
// nominal + clearance (this is what the checker measures as the thread's diameter), the thread runs out through a 60° cone into a plain
// relief at the floor, the floor/wall corner is filleted, the mouth edge rounded, the bed edge chamfered 60°. The thread flanks (30° ISO)
// are the usual short overhangs every printed cap has; nothing else overhangs.
// Load path: hand torque -> ribs -> wall -> thread flanks -> neck. The wall is measured from the thread root (major diameter).

/* [Interface] */
thread_d = 28;           // [6:0.5:80]  nominal (major) diameter of the mating external thread
pitch = 2.5;             // [0.5:0.25:6]
clearance = 0.25;        // [0:0.05:1]  added to the thread's major diameter (per diameter)
thread_len = 10;         // [3:0.5:40]  engaged thread length

/* [Cap] */
wall = 4;                // [2:0.25:10]  wall from the thread root (major diameter) to the outside
top_t = 3;               // [1.6:0.2:8]
relief_h = 2;            // [1:0.25:6]  plain relief above the floor so the neck never bottoms on a half thread
lead_in = 2;             // [1:0.25:6]  plain counterbore at the mouth
floor_fillet = 1.5;      // [0:0.25:4]
mouth_round = 1.5;       // [0:0.25:4]  round on the outer edge of the mouth
bed_chamfer = 0.5;       // [0:0.1:1.5]

/* [Grip] */
grip = "ribs";           // [ribs, flutes, plain]
grip_n = 24;             // [8:1:60]
rib_r = 1.2;             // [0.6:0.1:3]  rib (or flute) radius
rib_depth = 0.8;         // [0.3:0.1:2]  how far a rib stands out (or a flute cuts in)
rim_h = 2;               // [1:0.5:6]  plain band at the mouth (measured for the outer diameter)

/* [Render] */
render_target = "part";  // [part, coupon, assembly]

/* [Hidden] */
$fn = 96;
include <BOSL2/std.scad>
include <BOSL2/threading.scad>
thread_fn = 48;
major = thread_d + clearance;                          // internal thread major diameter (root of the cap's thread)
depth = 0.541 * pitch;                                 // ISO thread depth (5/8 H)
minor = major - 2 * depth;                             // crests of the cap's thread
cone_h = depth * tan(60);                              // 60° run-out cone from the relief to the thread crests
cap_od = major + 2 * wall;
R = cap_od / 2;
R_env = R + (grip == "ribs" ? rib_depth : 0);
z_floor = top_t;
z_thread0 = top_t + relief_h;
z_mouth = z_thread0 + thread_len;
cap_h = z_mouth + lead_in;
chamfer_w = bed_chamfer / tan(60);

assert(wall >= 1.6 + (grip == "flutes" ? rib_depth : 0), "wall too thin at the flutes / thread root");
assert(thread_len >= 2 * pitch + cone_h, "thread_len must give at least two full turns beyond the run-out cone");
assert(top_t >= 1.6, "top thinner than two perimeters");
assert(floor_fillet < relief_h + cone_h, "floor fillet taller than the relief");
echo(major = major, minor = minor, cap_od = cap_od, cap_h = cap_h, turns = (thread_len - cone_h) / pitch, mouth_counterbore_z = [z_mouth, cap_h]);

module outline2d() {
    // outer outline: circle plus ribs or minus flutes
    if (grip == "ribs") union() {
        circle(r = R);
        for (i = [0 : grip_n - 1]) rotate(i * 360 / grip_n) translate([R - rib_r + rib_depth, 0]) circle(r = rib_r, $fn = 24);
    } else if (grip == "flutes") difference() {
        circle(r = R);
        for (i = [0 : grip_n - 1]) rotate(i * 360 / grip_n) translate([R + rib_r - rib_depth, 0]) circle(r = rib_r, $fn = 24);
    } else circle(r = R);
}

module envelope() {
    // body of revolution that trims the extruded outline: 60° bed chamfer at the top plate, rounded mouth edge
    rotate_extrude() polygon(concat(
        [[0, 0], [R_env - chamfer_w, 0], [R_env, bed_chamfer], [R_env, cap_h - mouth_round]],
        [for (i = [0 : 12]) let(a = i * 90 / 12) [R_env - mouth_round + mouth_round * cos(a), cap_h - mouth_round + mouth_round * sin(a)]],
        [[0, cap_h]]));
}

module body() {
    intersection() {
        union() {
            linear_extrude(height = cap_h - rim_h) outline2d();           // gripped zone
            cylinder(r = R, h = cap_h);                                    // plain rim at the mouth
        }
        envelope();
    }
}

module internal_thread(d, l) {
    // BOSL2 mask for an internal ISO thread, bottom at z = 0
    threaded_rod(d = d, l = l, pitch = pitch, internal = true, anchor = BOTTOM, $fn = thread_fn);
}

module cavity(maj, min_d) {
    union() {
        translate([0, 0, z_floor]) cylinder(d = maj, h = relief_h + 0.01, $fn = 128);                       // relief at the floor
        translate([0, 0, z_thread0]) cylinder(d1 = maj, d2 = min_d, h = cone_h, $fn = 128);                  // 60° run-out cone
        translate([0, 0, z_thread0]) internal_thread(maj, thread_len);                                       // the thread
        translate([0, 0, z_mouth - 0.01]) cylinder(d = maj, h = lead_in + 1.01, $fn = 128);                  // lead-in counterbore
    }
}

module floor_fillet_ring(maj) {
    if (floor_fillet > 0) rotate_extrude() translate([maj / 2 - floor_fillet, z_floor]) difference() {
        square([floor_fillet + 0.01, floor_fillet]);
        translate([0, floor_fillet]) circle(r = floor_fillet, $fn = 32);
    }
}

module part() {
    union() {
        difference() { body(); cavity(major, minor); }
        floor_fillet_ring(major);
    }
}

module coupon() {
    // thread ladder: three short threaded rings at clearance -0.2 / 0 / +0.2 on one plate (mouth up, like the part), labels embossed
    ring_h = 2 * pitch + 1;
    pitch_x = major + 9;
    plate = [3 * pitch_x + 4, major + 14, 1.2];
    difference() {
        union() {
            translate([-plate[0] / 2, -plate[1] / 2, 0]) cube(plate);
            for (i = [-1, 0, 1]) translate([i * pitch_x, 0, 0]) cylinder(d = major + 6, h = plate[2] + ring_h);
            for (i = [-1, 0, 1]) translate([i * pitch_x, plate[1] / 2 - 3.4, plate[2]])
                linear_extrude(0.6) text(str(i * 0.2), size = 2.6, halign = "center", $fn = 16);
        }
        for (i = [-1, 0, 1]) translate([i * pitch_x, 0, -1]) internal_thread(major + i * 0.2, plate[2] + ring_h + 2);
    }
}

module assembly() {
    part();
    %translate([0, 0, z_thread0 + 1]) threaded_rod(d = thread_d, l = thread_len + 12, pitch = pitch, anchor = BOTTOM, $fn = thread_fn);  // the neck
    %translate([0, 0, cap_h + 0.5]) cylinder(d = cap_od + 6, h = 4);                                                               // shoulder / flange above the mouth
}

if (render_target == "part") part();
else if (render_target == "coupon") coupon();
else assembly();
