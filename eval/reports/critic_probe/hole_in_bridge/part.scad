// TEMPLATE: ring-and-loop carry handle — a ring that sits around a neck (bottle, jar, cable) with a finger loop; optional finger scallops
// Interfaces: neck_id (the neck's outer diameter) + clearance -> bore. Origin at the bore axis, ring bottom on z = 0.
// Load path: loop -> tangent bridges -> ring. Print flat (ring on bed) so the carry load runs along the layers.

/* [Interface] */
neck_id = 43.2;          // [20:0.1:90]
clearance = 0.25;        // [0:0.05:0.8]
ring_height = 6;         // [3:0.5:20]
ring_wall = 4;           // [2:0.5:10]

/* [Loop] */
loop_inner_w = 42;       // [25:1:80]
loop_inner_h = 26;       // [15:1:45]
loop_thick = 6;          // [4:0.5:14]
bridge_len = 4;          // [0:0.5:20]  straight bridge between ring and loop (keeps the bore closed)
fillet_r = 4;            // [0:0.5:10]  fillet where bridges meet ring and loop
scallops = true;         // finger scallops on the inside long edges
scallop_depth = 1.5;     // [0:0.25:4]

/* [Render] */
render_target = "part";  // [part, coupon, assembly]

/* [Hidden] */
$fn = 96;
bore = neck_id + clearance;
ring_od = bore + 2 * ring_wall;
loop_cx = ring_od / 2 + bridge_len + loop_inner_w / 2 + loop_thick;   // loop center on +X
loop_ow = loop_inner_w + 2 * loop_thick;
loop_oh = loop_inner_h + 2 * loop_thick;

assert(bridge_len >= 0, "bridge_len must be >= 0");
assert(loop_inner_h > 2 * scallop_depth + 10, "scallops too deep for the loop height");
echo(bore = bore, ring_od = ring_od, overall_length = ring_od + bridge_len + loop_ow);

module stadium2d(w, h) { hull() { translate([-(w - h) / 2, 0]) circle(d = h); translate([(w - h) / 2, 0]) circle(d = h); } }

module outline2d() {
    // ring + bridges + loop as a 2D union, with fillets by offset trick
    offset(r = -fillet_r) offset(r = fillet_r) union() {
        circle(d = ring_od);
        translate([loop_cx, 0]) stadium2d(loop_ow, loop_oh);
        // solid bridge from the ring to the loop, as tall as the loop, so the load path has no waist or notch
        translate([0, -loop_oh / 2]) square([loop_cx, loop_oh]);
    }
}

module openings2d() {
    circle(d = bore, $fn = 160);
    translate([loop_cx, 0]) difference() {
        stadium2d(loop_inner_w, loop_inner_h);
        if (scallops) for (s = [-1, 1]) for (i = [-1, 1])
            translate([i * loop_inner_w / 4, s * (loop_inner_h / 2 + loop_inner_w / 4 - scallop_depth)]) circle(r = loop_inner_w / 4);
    }
}

module part() {
    difference() { linear_extrude(height = ring_height) difference() { outline2d(); openings2d(); }
        translate([ring_od / 2 + bridge_len / 2 + 1, 0, -1]) cylinder(d = 4, h = ring_height + 2); }
}

module coupon() {
    // three rings, mating feature only: clearance -0.2 / 0 / +0.2, embossed labels
    for (i = [-1, 0, 1]) translate([i * (bore + 10), 0, 0]) {
        difference() { cylinder(d = bore + i * 0.2 + 2 * 2.4, h = 3); translate([0, 0, -1]) cylinder(d = bore + i * 0.2, h = 5, $fn = 160); }
        translate([0, (bore + 2 * 2.4) / 2 + 3, 0]) linear_extrude(1) text(str(i * 0.2), size = 4, halign = "center");
    }
}

module assembly() {
    part();
    %translate([0, 0, -3]) cylinder(d = neck_id, h = ring_height + 6);
    %translate([0, 0, ring_height + 0.3]) cylinder(d = neck_id + 18, h = 3);
}

if (render_target == "part") part();
else if (render_target == "coupon") coupon();
else assembly();
