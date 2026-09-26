// TEMPLATE: flat spacer / gasket ring — a bore that slides over a bolt or shaft, an outer diameter, a thickness; optional parallel flats (wrench/keying) and a keying notch on the OD
// Interfaces: bolt_d (the bolt's outer diameter) + clearance -> bore. Origin on the bore axis, bottom face on z = 0.
// Print flat (a pure extrusion, no overhangs); the bed-side outer edge gets a light 60° chamfer so the first layer lifts off cleanly.

/* [Interface] */
bolt_d = 8.0;            // [3:0.1:40]  diameter of the bolt / shaft that passes through
clearance = 0.3;         // [0:0.05:0.8]  added to the bore diameter
outer_d = 20;            // [8:0.5:80]
thickness = 3;           // [0.8:0.1:20]

/* [Options] */
flats = false;           // two parallel flats on the outer diameter (for a wrench, or to key against a wall)
across_flats = 17;       // [6:0.5:80]  distance between the flats (when flats)
notch = true;            // radial keying notch in the outer edge
notch_w = 2;             // [1:0.25:8]
notch_depth = 1.5;       // [0.5:0.25:8]
bed_chamfer = 0.5;       // [0:0.1:1.5]  height of the 60° chamfer on the bottom outer edge

/* [Render] */
render_target = "part";  // [part, coupon, assembly]

/* [Hidden] */
$fn = 96;
bore = bolt_d + clearance;
wall = (outer_d - bore) / 2;
flat_wall = (across_flats - bore) / 2;
chamfer_w = bed_chamfer / tan(60);                 // radial width of the 60° bed chamfer
chamfer_scale = (outer_d / 2 - chamfer_w) / (outer_d / 2);

assert(outer_d > bore + 3.2, "outer_d leaves less than a 1.6 mm wall around the bore");
assert(!flats || across_flats > bore + 3.2, "across_flats leaves less than a 1.6 mm wall around the bore");
assert(!flats || across_flats < outer_d, "across_flats must be smaller than outer_d");
assert(!notch || wall - notch_depth >= 1.6, "the notch cuts the wall below 1.6 mm");
assert(thickness > 2 * bed_chamfer, "thickness must exceed twice the bed chamfer");
echo(bore = bore, wall = wall, min_wall = notch ? wall - notch_depth : (flats ? flat_wall : wall));

module body2d() {
    // outer outline without the bore: circle, optionally clipped by two flats, optionally notched
    difference() {
        intersection() {
            circle(d = outer_d);
            if (flats) square([outer_d + 2, across_flats], center = true);
        }
        if (notch) translate([outer_d / 2 - notch_depth, -notch_w / 2]) square([notch_depth + 1, notch_w]);
    }
}

module ring(bore_d, t) {
    difference() {
        union() {
            // chamfered bottom band (scaled about the axis), then the straight body
            linear_extrude(height = bed_chamfer + 0.01, scale = 1 / chamfer_scale) scale(chamfer_scale) body2d();
            translate([0, 0, bed_chamfer]) linear_extrude(height = t - bed_chamfer) body2d();
        }
        translate([0, 0, -1]) cylinder(d = bore_d, h = t + 2, $fn = 128);
    }
}

module part() { ring(bore, thickness); }

module coupon() {
    // fit ladder: one plate carrying three bosses with the bore at clearance -0.2 / 0 / +0.2, labels embossed on the plate
    pitch = bore + 8;
    plate = [3 * pitch + 4, bore + 13, 1.2];
    difference() {
        union() {
            translate([-plate[0] / 2, -plate[1] / 2, 0]) cube(plate);
            for (i = [-1, 0, 1]) translate([i * pitch, 0, 0]) cylinder(d = bore + 5, h = plate[2] + thickness);
            for (i = [-1, 0, 1]) translate([i * pitch, plate[1] / 2 - 3.2, plate[2]])
                linear_extrude(0.6) text(str(i * 0.2), size = 2.6, halign = "center", $fn = 16);
        }
        for (i = [-1, 0, 1]) translate([i * pitch, 0, -1]) cylinder(d = bore + i * 0.2, h = plate[2] + thickness + 2, $fn = 128);
    }
}

module assembly() {
    part();
    %translate([0, 0, -8]) cylinder(d = bolt_d, h = thickness + 16);                       // the bolt
    %translate([0, 0, -3]) cylinder(d = outer_d + 6, h = 3);                              // the surface it sits on
    %translate([0, 0, thickness + 0.3]) cylinder(d = bolt_d * 1.8, h = 0.8 * bolt_d, $fn = 6); // the nut
}

if (render_target == "part") part();
else if (render_target == "coupon") coupon();
else assembly();
