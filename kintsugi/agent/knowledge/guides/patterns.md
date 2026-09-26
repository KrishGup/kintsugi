# Patterns: compiling building blocks for repair parts

Each block compiles as-is on OpenSCAD 2021.01 (the test-suite compiles them). Copy the block, rename the parameters to the spec's names, keep the origin at the primary interface and the bottom on z = 0. Full parts that follow every Kintsugi convention live in `templates/` (`list_templates()`): ring-and-loop handle, L bracket, snap clip, D-shaft knob, hook, spacer/gasket, threaded cap.

## Ring around a neck (sliding fit) with a finger loop

```scad
neck_id = 43; clearance = 0.25; wall = 4; h = 6; loop_w = 42; loop_h = 26; loop_t = 6;
bore = neck_id + clearance; od = bore + 2 * wall;
cx = od / 2 + loop_w / 2 + loop_t;                     // loop centre on +X
module stadium(w, hh) hull() for (s = [-1, 1]) translate([s * (w - hh) / 2, 0]) circle(d = hh, $fn = 64);
linear_extrude(h) difference() {
    offset(r = -4) offset(r = 4) union() {             // 4 mm fillets where the bridge meets ring and loop
        circle(d = od, $fn = 96);
        translate([cx, 0]) stadium(loop_w + 2 * loop_t, loop_h + 2 * loop_t);
        translate([0, -(loop_h + 2 * loop_t) / 2]) square([cx, loop_h + 2 * loop_t]);   // solid bridge: no waist in the load path
    }
    circle(d = bore, $fn = 160);                        // the measured bore, fine facets
    translate([cx, 0]) stadium(loop_w, loop_h);
}
```

## Boss into a hole (press fit) with a lead-in chamfer

```scad
hole_d = 10; clearance = 0.10; boss_h = 8; plate = [30, 30, 4];
boss_d = hole_d - clearance;
translate([0, 0, 0]) cube([plate.x, plate.y, plate.z], center = false);
translate([plate.x / 2, plate.y / 2, plate.z - 0.01]) {
    cylinder(h = boss_h - 0.8, d = boss_d, $fn = 128);
    translate([0, 0, boss_h - 0.8]) cylinder(h = 0.8, d1 = boss_d, d2 = boss_d - 1.6, $fn = 128);   // 45° lead-in
}
```

## D-shaft bore (knob, gear, lever)

```scad
shaft_d = 6; flat = 4.5; clearance = 0.15; hub_h = 12; hub_d = 20;   // flat = distance from the flat face to the round side
r = (shaft_d + clearance) / 2;
module d_bore(h) intersection() {
    cylinder(h = h, d = 2 * r, $fn = 128);
    translate([-r, -r, 0]) cube([flat + clearance, 2 * r, h]);      // keeps x from -r to -r + flat + clearance: the flat face
}
difference() { cylinder(h = hub_h, d = hub_d, $fn = 96); translate([0, 0, -1]) d_bore(hub_h + 2); }
```
The `gap` recipe measures across-flat distances; `circle_fit_inner` on the section fits the round part (expect the fit to report a partial arc).

## Slot / fork that straddles a plate (sliding fit)

```scad
plate_t = 3; clearance = 0.3; arm_t = 3; depth = 12; width = 20; h = 10;
slot = plate_t + clearance;
difference() {
    translate([-width / 2, 0, 0]) cube([width, depth, h]);
    translate([-width / 2 - 1, arm_t, -1]) cube([width + 2, slot, h + 2]);   // the slot, measured with `gap` along y at z = h/2
}
```

## Snap clip jaws around a tube (notch fit)

```scad
tube_d = 16; clearance = 0.2; wall = 2.5; h = 10; mouth = 0.82;   // mouth as a fraction of the tube diameter
r = (tube_d + clearance) / 2;
linear_extrude(h) difference() {
    offset(r = 1) offset(delta = -1) union() { circle(r = r + wall, $fn = 96); translate([-(r + wall), -r - wall - 6]) square([2 * (r + wall), r + wall + 6]); }   // body with a stem
    circle(r = r, $fn = 128);                                     // the notch circle (notch_circle recipe)
    translate([-mouth * tube_d / 2, 0]) square([mouth * tube_d, 2 * r]);   // the mouth (notch_mouth recipe): narrower than the tube
    translate([-(r + wall) - 1, -r - wall - 7]) square([2 * (r + wall) + 2, 3]);   // trim: stem end open
}
```

## Hole pattern from a list (hole_positions recipe)

```scad
holes = [[-31.6, 0, 4.5], [31.6, 0, 4.5]];      // [x, y, diameter], matched against spec `expect`
difference() {
    hull() for (p = holes) translate([p[0], p[1], 0]) cylinder(h = 4, d = 12, $fn = 48);   // a bar around the holes
    for (p = holes) translate([p[0], p[1], -1]) cylinder(h = 6, d = p[2], $fn = 48);
}
```

## Countersunk and counterbored screw holes

```scad
module csk_hole(d = 4.5, head_d = 9, depth = 20) {        // 90° countersink for a flat-head screw
    translate([0, 0, -1]) cylinder(h = depth + 2, d = d, $fn = 32);
    translate([0, 0, depth - head_d / 2 + 0.01]) cylinder(h = head_d / 2, d1 = 0, d2 = head_d, $fn = 48);
}
module cbore_hole(d = 4.5, head_d = 8, head_h = 4, depth = 20) {  // counterbore for a socket-head screw
    translate([0, 0, -1]) cylinder(h = depth + 2, d = d, $fn = 32);
    translate([0, 0, depth - head_h]) cylinder(h = head_h + 1, d = head_d, $fn = 48);
}
difference() { cube([40, 20, 8]); translate([10, 10, 0]) csk_hole(depth = 8); translate([30, 10, 0]) cbore_hole(depth = 8); }
```

## Hex nut trap (across-flats to circumradius)

```scad
af = 8; nut_h = 4; clearance = 0.3;      // M5: 8 mm across flats
difference() {
    cylinder(h = 12, d = 20, $fn = 96);
    translate([0, 0, -1]) cylinder(h = 14, d = 5.5, $fn = 32);                          // M5 clearance hole
    translate([0, 0, 12 - nut_h]) cylinder(h = nut_h + 1, d = af / cos(30) + clearance, $fn = 6);   // $fn=6 hexagon, corner diameter
}
```

## Plug / cap for a tube end (with retention ribs)

```scad
tube_id = 25.4; clearance = 0.25; depth = 12; lip = 3; rib = 0.3;
d = tube_id - clearance;
union() {
    cylinder(h = lip, d = tube_id + 6, $fn = 96);                                    // the stop lip on the bed
    translate([0, 0, lip - 0.01]) cylinder(h = depth - 1, d = d, $fn = 128);
    translate([0, 0, lip + depth - 1.01]) cylinder(h = 1, d1 = d, d2 = d - 2, $fn = 128);   // lead-in
    for (z = [lip + 3, lip + 7]) translate([0, 0, z]) cylinder(h = 1, d = d + 2 * rib, $fn = 128);   // crush ribs for retention
}
```

## Flanged bushing / spacer by revolve

```scad
id = 8.2; od = 12; flange_d = 18; flange_t = 2; h = 10;
rotate_extrude($fn = 128) polygon([[id / 2, 0], [flange_d / 2, 0], [flange_d / 2, flange_t], [od / 2, flange_t], [od / 2, h], [id / 2, h]]);
```

## Hook with a rounded profile

```scad
bar = 6; mouth = 20; reach = 30; back = 40;
module bar2d() circle(d = bar, $fn = 32);
// the hook path in the XZ plane, built from hull segments so every corner is round
module seg(a, b) hull() { translate(a) sphere(d = bar, $fn = 24); translate(b) sphere(d = bar, $fn = 24); }
translate([0, 0, bar / 2]) union() {
    seg([0, 0, 0], [0, 0, back]);                       // back plate contact
    seg([0, 0, back], [reach, 0, back]);               // top
    seg([reach, 0, back], [reach, 0, back - mouth]);   // drop
    seg([reach, 0, back - mouth], [reach - 8, 0, back - mouth + 2]);   // lip
}
```

## Cap with an internal thread (BOSL2)

```scad
include <BOSL2/std.scad>
include <BOSL2/threading.scad>
thread_d = 24; pitch = 2; cap_h = 10; wall = 2.5;
diff() cyl(h = cap_h, d = thread_d + 2 * wall + 0.5, chamfer2 = 0.8, anchor = BOT, $fn = 96)
    tag("remove") position(BOT) threaded_rod(d = thread_d + 0.3, l = cap_h - 2, pitch = pitch, anchor = BOT, $fn = 48);   // +0.3 for FDM
```

## A printable horizontal hole (teardrop) through a boss

```scad
module teardrop_y(d, l) rotate([90, 0, 0]) linear_extrude(l, center = true) union() { circle(d = d, $fn = 48); rotate(45) square([d / 2, d / 2]); }
difference() { translate([0, 0, 0]) cube([20, 20, 20]); translate([10, 10, 10]) teardrop_y(6, 30); }
```

## Ghosted context for assembly views (never exported)

```scad
cylinder(h = 6, d = 54, $fn = 96);                       // the part
%translate([0, 0, -3]) cylinder(h = 12, d = 43, $fn = 96);   // the neck, ghosted
%translate([0, 0, 6.3]) cylinder(h = 3, d = 62, $fn = 96);   // the cap flange, ghosted
```
