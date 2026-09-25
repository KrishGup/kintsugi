"""Toolchain tests: compile, checks on known geometry, blueprint rendering, customizer parsing, spec fusion, session pipeline.
No model required."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from kintsugi import TEMPLATES_DIR
from kintsugi.checks import geometry as G
from kintsugi.checks import run_checks
from kintsugi.render import make_blueprint
from kintsugi.scad.compile import compile_scad, openscad_version
from kintsugi.scad.customizer import parse_customizer, set_param_values
from kintsugi.spec.model import Dim, Estimate, PartSpec, fuse_estimates, refresh_dim

pytestmark = pytest.mark.skipif(openscad_version() is None, reason="openscad not installed")

TUBE = """$fn = 160;
difference() { cylinder(d = 50, h = 6); translate([0, 0, -1]) cylinder(d = 43.2, h = 8); }
"""

STEP_BLOCK = """// stepped gauge block 40 x 30 x 20 with a 10 mm step and two 5 mm holes
difference() {
  union() { cube([40, 30, 10]); cube([20, 30, 20]); }
  for (x = [30]) for (y = [8, 22]) translate([x, y, -1]) cylinder(d = 5, h = 30, $fn = 64);
}
"""

T_SHAPE = """// overhanging T: 40% of the surface faces down
translate([0,0,10]) cube([40, 40, 4], center=false);
translate([15, 15, 0]) cube([10, 10, 10]);
"""


@pytest.fixture(scope="module")
def tmp(tmp_path_factory):
    return tmp_path_factory.mktemp("kin")


def _compile(tmp: Path, name: str, src: str) -> Path:
    scad = tmp / f"{name}.scad"
    scad.write_text(src)
    r = compile_scad(scad, tmp / f"{name}.stl")
    assert r.ok, r.summary()
    return tmp / f"{name}.stl"


def test_compile_reports_errors(tmp):
    scad = tmp / "bad.scad"
    scad.write_text("cube([10,10,10]\n")  # missing paren
    r = compile_scad(scad, tmp / "bad.stl")
    assert not r.ok and r.errors


def test_compile_relative_path(tmp, monkeypatch):
    scad = tmp / "rel.scad"
    scad.write_text("cube(5);")
    monkeypatch.chdir(tmp)
    r = compile_scad("rel.scad", "rel.stl")
    assert r.ok


def test_compile_assert_and_echo(tmp):
    scad = tmp / "ae.scad"
    scad.write_text('x = 4; echo(x = x, name = "a"); assert(x > 2); cube(x);')
    r = compile_scad(scad, tmp / "ae.stl")
    assert r.ok and r.echo_values.get("x") == 4 and r.echo_values.get("name") == "a"
    scad.write_text("x = 1; assert(x > 2, \"x too small\"); cube(x);")
    r = compile_scad(scad, tmp / "ae2.stl")
    assert not r.ok and any("x too small" in e or "Assertion" in e for e in r.errors)


def test_tube_measurements(tmp):
    stl = _compile(tmp, "tube", TUBE)
    m = G.load_mesh(stl)
    c = G.circle_fit_inner(m, 3.0)
    assert abs(c.d - 43.2) < 0.05, c
    assert c.rms < 0.02
    o = G.circle_fit_outer(m, 3.0)
    assert abs(o.d - 50.0) < 0.05
    assert abs(G.extent(m, "z") - 6.0) < 1e-6
    assert abs(G.hole_extent(m, 3.0, "x") - 43.2) < 0.02
    w = G.wall_thickness(m, 1200)
    assert abs(w.min - 3.4) < 0.1 and abs(w.p05 - 3.4) < 0.1  # (50 - 43.2) / 2
    st = G.overhang_stats(m)
    assert st.fraction == 0.0
    assert abs(st.bed_contact_area - (np.pi * (25**2 - 21.6**2))) < 5


def test_robust_circle_with_attached_feature(tmp):
    stl = _compile(tmp, "tube_bar", TUBE + "translate([22, -5, 0]) cube([40, 10, 6]);")
    m = G.load_mesh(stl)
    c = G.circle_fit_inner(m, 3.0)
    assert abs(c.d - 43.2) < 0.05 and c.inlier_fraction > 0.99
    o = G.circle_fit_outer(m, 3.0)  # outer boundary is a union outline; RANSAC still finds the ring arc
    assert abs(o.d - 50.0) < 0.1 and o.inlier_fraction < 0.99


def test_interference_and_context(tmp):
    stl = _compile(tmp, "tube2", TUBE)
    m = G.load_mesh(stl)
    small = G.context_mesh("cylinder", d=43.0, h=12, at=[0, 0, -3])
    big = G.context_mesh("cylinder", d=44.0, h=12, at=[0, 0, -3])
    assert G.interference_volume(m, small) < 1e-6
    v = G.interference_volume(m, big)
    expected = np.pi * (22.0**2 - 21.6**2) * 6  # ring of material inside the 44 mm cylinder
    assert abs(v - expected) / expected < 0.03
    cone = G.context_mesh("cone", d1=85, d2=43.2, h=10, at=[0, 0, -13])
    assert cone.is_watertight and cone.volume > 0


def test_step_block_holes_and_walls(tmp):
    stl = _compile(tmp, "block", STEP_BLOCK)
    m = G.load_mesh(stl)
    holes = G.hole_positions(m, 5.0)
    assert len(holes) == 2
    for h in holes:
        assert abs(h["d"] - 5.0) < 0.05 and abs(h["x"] - 30) < 0.05
    assert sorted(round(h["y"]) for h in holes) == [8, 22]
    assert abs(G.extent(m, "z", region=[[0, 0, 0], [20, 30, 30]]) - 20) < 1e-6
    assert abs(G.extent(m, "z", region=[[21, 0, 0], [40, 30, 30]]) - 10) < 1e-6


def test_overhang_and_orientation(tmp):
    stl = _compile(tmp, "t", T_SHAPE)
    m = G.load_mesh(stl)
    st = G.overhang_stats(m)
    assert st.fraction > 0.2  # the underside of the plate overhangs
    ranked = G.score_orientations(m)
    assert ranked[0]["name"] != "as modeled (Z up)"  # upside down or on its side is better
    assert ranked[0]["overhang_fraction"] < st.fraction


def test_run_checks_with_spec(tmp):
    spec = PartSpec.load(Path(__file__).parent.parent / "eval" / "specs" / "bottle_handle.yaml")
    stl = _compile(tmp, "tmpl", (TEMPLATES_DIR / "ring_loop_handle.scad").read_text())
    rep = run_checks(stl, spec, iteration=1)
    ids = {i.id: i for i in rep.items}
    assert ids["neck_ring.inner_diameter"].passed and abs(ids["neck_ring.inner_diameter"].measured - 43.45) < 0.05
    assert ids["neck_ring.inner_diameter"].target == 43.45  # target + clearance
    assert ids["interference.neck"].passed and ids["interference.cap_flange"].passed
    assert ids["load.loop_inner_width"].passed and ids["load.loop_inner_height"].passed
    assert rep.all_hard_pass, [i.id for i in rep.hard_failures]
    # a defect: bore too small -> fails and interferes
    stl2 = _compile(tmp, "tmpl_bad", (TEMPLATES_DIR / "ring_loop_handle.scad").read_text().replace("neck_id = 43.2;", "neck_id = 42.0;"))
    rep2 = run_checks(stl2, spec, iteration=2)
    ids2 = {i.id: i for i in rep2.items}
    assert ids2["neck_ring.inner_diameter"].passed is False
    assert ids2["interference.neck"].passed is False and ids2["interference.neck"].measured > 100


def test_blueprint_renders(tmp):
    spec = PartSpec.load(Path(__file__).parent.parent / "eval" / "specs" / "bottle_handle.yaml")
    stl = _compile(tmp, "bp", (TEMPLATES_DIR / "ring_loop_handle.scad").read_text())
    rep = run_checks(stl, spec, iteration=3)
    res = make_blueprint(stl, spec, rep, tmp / "sheets", 3)
    assert res.sheet_path.exists() and res.sections_path and res.sections_path.exists()
    assert set(res.view_paths) == {"top", "iso", "front", "right", "bottom", "left", "back"}
    assert "A" in res.section_paths and "top" in res.assembly_paths
    from PIL import Image
    im = Image.open(res.sheet_path)
    assert im.width <= 2200 and im.height > 800


def test_customizer_roundtrip():
    src = (TEMPLATES_DIR / "ring_loop_handle.scad").read_text()
    params = {p.name: p for p in parse_customizer(src)}
    assert params["neck_id"].min == 20 and params["neck_id"].step == 0.1 and params["neck_id"].max == 90
    assert params["scallops"].type == "bool"
    assert [o["value"] for o in params["render_target"].options] == ["part", "coupon", "assembly"]
    assert "bore" not in params  # hidden section
    new = set_param_values(src, {"neck_id": 38.0, "scallops": False, "render_target": "coupon"})
    p2 = {p.name: p for p in parse_customizer(new)}
    assert p2["neck_id"].value == 38.0 and p2["scallops"].value is False and p2["render_target"].value == "coupon"
    assert "// [20:0.1:90]" in new  # annotation preserved


def test_spec_fusion_and_gates():
    d = Dim(tol=0.3, estimates=[Estimate(value=43.4, source="rectified_sheet", conf=0.75)])
    assert d.status == "estimated" and d.target == 43.4
    d.estimates.append(Estimate(value=43.2, source="user_caliper", conf=0.95))
    refresh_dim(d)
    assert d.target == 43.2 and d.status == "confirmed"
    v, conf, why = fuse_estimates([Estimate(value=20.1, source="rectified_sheet", conf=0.7), Estimate(value=20.0, source="reference_object", conf=0.5)])
    assert v == 20.1 and conf > 0.7 and "corroborated" in why
    spec = PartSpec.load(Path(__file__).parent.parent / "eval" / "specs" / "bottle_handle.yaml")
    assert spec.unconfirmed_interface_dims() == ["neck_ring.ring_outer_diameter"]
    assert spec.clearance_for(spec.interfaces[0]) == 0.25
    assert "INTERFACE neck_ring" in spec.summary_for_model()


def test_session_pipeline_and_export(tmp):
    from kintsugi.agent.export import export_bundle
    from kintsugi.agent.pipeline import run_iteration
    from kintsugi.session.workspace import Session

    spec = PartSpec.load(Path(__file__).parent.parent / "eval" / "specs" / "bottle_handle.yaml")
    s = Session.create("test_handle", spec, sessions_dir=tmp / "sessions")
    shutil.copy(TEMPLATES_DIR / "ring_loop_handle.scad", s.scad_path)
    res = run_iteration(s, label="template as-is")
    assert res.ok, res.summary_for_model()
    assert (s.dir / "iterations" / "iter_01" / "checks.json").exists()
    assert (s.dir / "params.json").exists() and json.loads((s.dir / "params.json").read_text())
    evs = s.events()
    assert any(e["kind"] == "iteration" for e in evs)
    # a failing edit and the policy history
    src = s.scad_path.read_text().replace("neck_id = 43.2;", "neck_id = 41.0;")
    res2 = run_iteration(s, scad_text=src, label="bore too small on purpose")
    assert not res2.ok and "neck_ring.inner_diameter" in [i.id for i in res2.checks.hard_failures]
    # branch back to iteration 1 and export
    s.checkout_iteration(1)
    res3 = run_iteration(s, label="back to iteration 1")
    assert res3.ok
    out = export_bundle(s)
    files = out["files"]
    for k in ("stl", "scad", "blueprint", "print_card", "bundle", "coupon"):
        assert k in files and Path(files[k]).exists(), k
    card = Path(files["print_card"]).read_text()
    assert "Print card" in card and "coupon" in card.lower()
    assert len(s.history()) >= 4
