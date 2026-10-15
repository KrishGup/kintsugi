/*
Bottle carry handle, adapted from the ring_loop_handle template.
A closed neck ring feeds a broad, R4-blended web into a 6 mm-wide loop.
Two shallow finger scallops have smooth tangencies; all rim edges have
45-degree chamfers. Print flat: the in-plane loop load flows into both
sides of the neck ring. Geometry is sized for the specified 1.5 kg use;
printed strength depends on material, slicing and layer adhesion.
The specified sliding fit is used (free rotation is not guaranteed).
Spec dims: neck_ring.inner_diameter <- neck_id (+ clearance),
 neck_ring.ring_height <- ring_height,
 neck_ring.ring_outer_diameter <- ring_od,
 load.loop_inner_width <- loop_inner_w,
 load.loop_inner_height <- loop_inner_h,
 footprint.overall_length <- ring_od + bridge_len + loop_inner_w + 2*loop_thick.
Coupon: left to right, nominal clearance -0.2 / nominal / +0.2 mm.
*/
include <BOSL2/std.scad>

/* [Interface] */
neck_id = 43.2; // [40:0.1:46] Measured bottle neck diameter
clearance = 0.25; // [0.05:0.05:0.65] Diametral sliding-fit clearance
ring_height = 6; // [5.5:0.1:6.5] Thickness of the neck ring and loop

/* [Body] */
ring_od = 54; // [50:0.1:58] Neck ring outside diameter
loop_inner_w = 42; // [40:0.5:50] Finger opening extent along X
loop_inner_h = 26; // [22:0.5:32] Finger opening extent along Y
loop_thick = 6; // [4:0.5:8] Minimum in-plane loop rail width
bridge_len = 1; // [0:0.5:8] Separation between ring OD and loop envelope
fillet_r = 4; // [2:0.5:6] Concave blend radius at ring-to-loop roots
edge_chamfer = 0.5; // [0.3:0.1:0.8] Top and bed-side edge relief

/* [Options] */
scallops = true; // Add two-finger seating with a gently raised central divider
scallops_depth = 1.5; // [0.5:0.25:2] Central divider depth on each long inner edge

/* [Render] */
render_target = "part"; // [part, coupon, assembly]

/* [Hidden] */
$fn = 96;
bore = neck_id + clearance;
ring_wall = (ring_od-bore)/2;
loop_ow = loop_inner_w + 2*loop_thick;
loop_oh = loop_inner_h + 2*loop_thick;
loop_cx = ring_od/2 + bridge_len + loop_ow/2;
overall_length = ring_od + bridge_len + loop_ow;
R = ring_od/2;
r = loop_oh/2;
// Tangent R-fillet between the ring circle and the horizontal loop rail.
blend_y = r + fillet_r;
blend_x = sqrt((R+fillet_r)*(R+fillet_r)-blend_y*blend_y);
blend_angle = asin(blend_y/(R+fillet_r));
end_x = loop_cx + (loop_ow-loop_oh)/2;
inner_r = loop_inner_h/2;
inner_a = (loop_inner_w-loop_inner_h)/2;
scallop_d = scallops ? scallops_depth : 0;

assert(ring_od >= 50 && ring_od <= 58, "Ring OD must be 50 to 58 mm");
assert(ring_height >= 5.5 && ring_height <= 6.5, "Ring thickness must be 6 +/-0.5 mm");
assert(ring_height <= 6.0, "Keep at least 0.3 mm beneath the fixed cap-flange proxy");
assert(loop_inner_w >= 40 && loop_inner_h >= 22, "Two fingers need at least a 40 x 22 mm opening");
assert(loop_inner_h-2*scallop_d >= 22, "Keep the central finger gap at least 22 mm");
assert(loop_inner_w > loop_inner_h, "Finger opening width must exceed its height");
assert(overall_length <= 110, "Overall length must not exceed 110 mm");
assert(ring_wall >= 4 && loop_thick >= 4, "Keep reinforced ring and loop walls at least 4 mm");
assert(min(ring_wall,loop_thick)-2*edge_chamfer >= 1.6, "Chamfered edges must retain the minimum wall");
assert(r < R && blend_x < end_x, "Ring must be taller than the loop envelope for tangent root blends");
assert(loop_cx-loop_inner_w/2 > bore/2+4, "Keep the neck bore and finger opening separated by a strong web");
assert(bridge_len >= 0 && edge_chamfer*2 < ring_height, "Invalid bridge or edge chamfer");
echo(neck_ring_inner_diameter=bore, neck_ring_ring_height=ring_height,
     neck_ring_ring_outer_diameter=ring_od, load_loop_inner_width=loop_inner_w,
     load_loop_inner_height=loop_inner_h, footprint_overall_length=overall_length,
     ring_radial_wall=ring_wall, central_finger_gap=loop_inner_h-2*scallop_d);

function arcpts(c, rad, a0, a1, n) =
    [for(i=[0:n]) let(a=a0+(a1-a0)*i/n) c + rad*[cos(a),sin(a)]];
// CCW perimeter: rounded loop end, top root fillet, ring, bottom fillet.
outer_path = concat(
    arcpts([end_x,0],r,-90,90,48),
    arcpts([blend_x,blend_y],fillet_r,270,180+blend_angle,16),
    // Omit ring endpoints: each is already supplied by its tangent fillet.
    [for(i=[1:127]) let(a=blend_angle+(360-2*blend_angle)*i/128)
        R*[cos(a),sin(a)]],
    arcpts([blend_x,-blend_y],fillet_r,180-blend_angle,90,16)
);
inner_local = concat(
    arcpts([inner_a,0],inner_r,-90,90,48),
    [for(i=[1:31]) let(x=inner_a-2*inner_a*i/32)
        [x,inner_r-scallop_d*pow(cos(90*x/inner_a),2)]],
    arcpts([-inner_a,0],inner_r,90,270,48),
    [for(i=[1:31]) let(x=-inner_a+2*inner_a*i/32)
        [x,-inner_r+scallop_d*pow(cos(90*x/inner_a),2)]]
);
loop_path = [for(p=inner_local) p+[loop_cx,0]];
bore_path = [for(i=[0:159]) bore/2*[cos(i*360/160),sin(i*360/160)]];

module part() {
    // offset_sweep accepts a region (outer contour plus the two holes),
    // and preserves the center sections while beveling every exposed rim.
    offset_sweep([outer_path, bore_path, loop_path], height=ring_height,
                 bottom=os_chamfer(edge_chamfer), top=os_chamfer(edge_chamfer));
}

module coupon_ring(d) {
    difference() {
        union() {
            cylinder(h=0.4,d1=d+5.2,d2=d+6,$fn=128);
            translate([0,0,0.39]) cylinder(h=2.61,d=d+6,$fn=128);
        }
        translate([0,0,-1]) cylinder(h=5,d=d,$fn=160);
        translate([0,0,-0.01]) cylinder(h=0.51,d1=d+1.02,d2=d,$fn=160);
        translate([0,0,2.5]) cylinder(h=1.5,d1=d,d2=d+3,$fn=160);
    }
}
module coupon() {
    for(i=[-1,0,1]) translate([i*(bore+9),0,0]) coupon_ring(bore+i*0.2);
}
module assembly() {
    part();
    %translate([0,0,-3]) cylinder(d=neck_id,h=12,$fn=128);
    %translate([0,0,6.3]) cylinder(d=62,h=3,$fn=128);
    %translate([0,0,-13]) cylinder(d1=85,d2=neck_id,h=10,$fn=128);
}

if(render_target == "part") part();
else if(render_target == "coupon") coupon();
else assembly();
