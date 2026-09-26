"""The parametric customizer: annotation parsing, units, gating, spec bindings, presets, live previews and the apply path."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from kintsugi import TEMPLATES_DIR
from kintsugi.scad.compile import openscad_version
from kintsugi.scad.customizer import (
    bind_params,
    customizer_model,
    humanize,
    parse_asserts,
    parse_customizer,
    parse_derived,
    parse_echo_names,
    parse_header_bindings,
    presets_from_openscad,
    presets_to_openscad,
    set_param_values,
)
from kintsugi.spec.model import PartSpec

SPEC = Path(__file__).parent.parent / "eval" / "specs" / "bottle_handle.yaml"

SRC = '''// knob — Spec dims: shaft.diameter <- shaft_d (+ clearance)
/* [Interface] */
shaft_d = 6.0;           // [3:0.1:15]  shaft diameter (round part)
clearance = 0.2;         // [0:0.05:0.6]
// how deep the shaft goes
bore_depth = 11;         // [4:0.5:30]

/* [Grip] */
grip = "flutes";         // [flutes, ribs, plain]
grip_n = 12;             // [6:1:36]  number of flutes
pointer = true;          // index wedge
pointer_angle = 90;      // [0:15:345]  direction (90 = towards the flat)
tilt = 5;                // tilt of the top (deg)
cs_d = 9;                // [4:0.5:20]  countersink diameter (when pointer)
rated_load_kg = 5;       // [0.5:0.5:30]
safety_factor = 3;       // [1.5:0.5:6]
label = "A";             // [12]
render_target = "part";  // [part, coupon, assembly]

/* [Hidden] */
$fn = 96;
bore = shaft_d + clearance;
assert(bore_depth > 2, "bore too shallow");
echo(bore = bore, overall = bore_depth + 2);

module part() { cylinder(d = bore, h = bore_depth); }
part();
'''


def test_annotations_units_kinds_and_labels():
    ps = {p.name: p for p in parse_customizer(SRC)}
    assert ps["shaft_d"].min == 3 and ps["shaft_d"].step == 0.1 and ps["shaft_d"].max == 15
    assert ps["shaft_d"].description == "shaft diameter (round part)" and ps["shaft_d"].unit == "mm" and ps["shaft_d"].kind == "length"
    assert ps["shaft_d"].label == "Shaft diameter"
    assert ps["clearance"].kind == "clearance" and ps["clearance"].step == 0.05
    assert ps["bore_depth"].description == "how deep the shaft goes"
    assert ps["grip"].kind == "choice" and [o["value"] for o in ps["grip"].options] == ["flutes", "ribs", "plain"]
    assert ps["grip_n"].kind == "count" and ps["grip_n"].unit == "" and ps["grip_n"].step == 1
    assert ps["pointer"].kind == "toggle"
    assert ps["pointer_angle"].kind == "angle" and ps["pointer_angle"].unit == "°" and ps["pointer_angle"].gate == "pointer"
    assert ps["tilt"].unit == "°" and ps["tilt"].description == "tilt of the top (deg)"
    assert ps["cs_d"].gate == "pointer" and ps["cs_d"].description == "countersink diameter"
    assert ps["rated_load_kg"].unit == "kg" and ps["rated_load_kg"].kind == "mass" and ps["rated_load_kg"].label == "Rated load (kg)"
    assert ps["safety_factor"].kind == "ratio"
    assert ps["label"].kind == "text" and ps["label"].options == []
    assert ps["render_target"].options and "$fn" not in ps and "bore" not in ps
    assert humanize("loop_inner_w") == "Loop inner width" and humanize("neck_id") == "Neck ID"


def test_derived_asserts_echo_and_header_bindings():
    d = {x.name: x.expr for x in parse_derived(SRC)}
    assert d == {"bore": "shaft_d + clearance"}
    a = parse_asserts(SRC)
    assert a[0].message == "bore too shallow" and a[0].params == ["bore_depth"]
    assert parse_echo_names(SRC) == ["bore", "overall"]
    assert parse_header_bindings(SRC) == {"shaft_d": "shaft.diameter"}
    m = customizer_model(SRC, None, {"bore": 6.2, "overall": 13})
    names = {x["name"]: x for x in m["derived"]}
    assert names["bore"]["value"] == 6.2 and names["bore"]["echoed"] and names["overall"]["value"] == 13 and names["overall"]["expr"] == ""
    assert m["sections"] == ["Interface", "Grip"] and m["render_targets"] == ["part", "coupon", "assembly"]


def test_every_template_parameter_has_a_range_and_bindings_resolve():
    for t in sorted(TEMPLATES_DIR.glob("*.scad")):
        ps = parse_customizer(t.read_text(encoding="utf-8"))
        assert ps, t.name
        unranged = [p.name for p in ps if p.type == "number" and p.min is None]
        assert not unranged, f"{t.name}: {unranged}"
        for p in ps:
            if p.type == "number":
                assert p.min <= p.value <= p.max, f"{t.name}: {p.name} = {p.value} outside [{p.min}, {p.max}]"
    src = (TEMPLATES_DIR / "ring_loop_handle.scad").read_text(encoding="utf-8")
    spec = PartSpec.load(SPEC)
    ps = parse_customizer(src)
    bind_params(ps, spec, parse_header_bindings(src))
    b = {p.name: p.binding for p in ps if p.binding}
    assert b["neck_id"].dim == "neck_ring.inner_diameter" and b["neck_id"].how == "name+value" and b["neck_id"].target == 43.2
    assert b["neck_id"].clearance == 0.25 and b["neck_id"].fit == "sliding" and b["neck_id"].status == "confirmed"
    assert {s["source"] for s in b["neck_id"].sources} == {"rectified_sheet", "user_caliper"}
    assert b["ring_height"].dim == "neck_ring.ring_height"
    assert b["loop_inner_w"].dim == "load.loop_inner_width" and b["loop_inner_w"].role == "requirement" and b["loop_inner_w"].min == 40
    assert "clearance" not in b and "ring_wall" not in b
    # gating markers in the templates
    lb = {p.name: p for p in parse_customizer((TEMPLATES_DIR / "l_bracket.scad").read_text(encoding="utf-8"))}
    assert lb["cs_d"].gate == "countersink" and lb["gusset_len"].gate == "gusset"


def test_set_param_values_keeps_literals_and_annotations():
    out = set_param_values(SRC, {"bore_depth": 12.0, "shaft_d": 6.35, "grip": "ribs", "pointer": False})
    assert "bore_depth = 12;         // [4:0.5:30]" in out
    assert "shaft_d = 6.35;" in out and "// [3:0.1:15]  shaft diameter (round part)" in out
    assert 'grip = "ribs";' in out and "pointer = false;" in out
    assert parse_customizer(out)[0].value == 6.35


def test_presets_round_trip_in_openscad_format():
    ps = parse_customizer(SRC)
    doc = presets_to_openscad({"big": {"shaft_d": 8, "pointer": False, "grip": "ribs", "grip_n": 20}})
    assert doc["fileFormatVersion"] == "1" and doc["parameterSets"]["big"] == {"shaft_d": "8", "pointer": "false", "grip": "ribs", "grip_n": "20"}
    back = presets_from_openscad(doc, ps)
    assert back == {"big": {"shaft_d": 8.0, "pointer": False, "grip": "ribs", "grip_n": 20}}


@pytest.mark.skipif(openscad_version() is None, reason="openscad not installed")
def test_preview_engine_latest_wins(tmp_path):
    from kintsugi.scad.preview import PreviewEngine

    eng = PreviewEngine()
    scad = TEMPLATES_DIR / "ring_loop_handle.scad"
    r = eng.run("s", scad, tmp_path / "preview", {"neck_id": 50}, render_target="part")
    assert r["ok"] and r["file"] == "preview/preview.stl" and r["echo_values"]["bore"] == 50.25 and (tmp_path / "preview" / "preview.stl").exists()
    r = eng.run("s", scad, tmp_path / "preview", {"scallop_depth": 20}, render_target="part")
    assert not r["ok"] and r["assert_failures"] == ["scallops too deep for the loop height"]
    # a burst: the older request is killed, only the newest compiles
    res: dict[int, dict] = {}

    def go(i: int) -> None:
        res[i] = eng.run("burst", TEMPLATES_DIR / "knob_d_shaft.scad", tmp_path / "burst", {"knob_d": 30 + i}, render_target="part")

    threads = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    threads[0].start()
    time.sleep(0.2)
    threads[1].start()
    for t in threads:
        t.join(120)
    assert res[0]["superseded"] and res[0]["cancelled"] and not res[0]["ok"]
    assert res[1]["ok"] and not res[1]["superseded"] and res[1]["gen"] == 2
    assert eng.last("burst")["gen"] == 2


@pytest.mark.skipif(openscad_version() is None, reason="openscad not installed")
def test_customizer_api(tmp_path, monkeypatch):
    monkeypatch.setenv("KIN_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("KIN_PROVIDER", "fake")
    from fastapi.testclient import TestClient

    import kintsugi.server.app as appmod
    from kintsugi.agent.llm import get_llm

    get_llm(reset=True)
    appmod.SESSIONS_DIR = (tmp_path / "sessions").resolve()
    appmod.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    scad = (TEMPLATES_DIR / "ring_loop_handle.scad").read_text(encoding="utf-8")
    with TestClient(appmod.app) as c:
        s = c.post("/api/sessions", json={"name": "cz", "spec_yaml": SPEC.read_text(), "scad": scad}).json()
        sid = s["meta"]["id"]
        m = c.get(f"/api/sessions/{sid}/customizer").json()
        assert m["available"] and m["sections"] == ["Interface", "Loop", "Render"] and m["has_render_target"]
        p = {x["name"]: x for x in m["params"]}
        assert p["neck_id"]["binding"]["dim"] == "neck_ring.inner_diameter" and p["neck_id"]["unit"] == "mm"
        assert p["bridge_len"]["description"].startswith("straight bridge") and p["bridge_len"]["min"] == 0
        assert p["scallop_depth"]["gate"] == "scallops"
        assert m["verified"]["values"]["neck_id"] == 43.2 and m["presets"] == {}
        # a draft preview does not touch part.scad or the iteration count
        r = c.post(f"/api/sessions/{sid}/preview", json={"values": {"neck_id": 45, "loop_inner_w": 50}, "render_target": "part"}).json()
        assert r["ok"] and r["file"] == "preview/preview.stl" and r["echo_values"]["bore"] == 45.25 and r["quality"] == "draft"
        assert c.get(f"/api/sessions/{sid}/files/preview/preview.stl").status_code == 200
        d = c.get(f"/api/sessions/{sid}").json()
        assert d["meta"].get("iteration", 0) == 0 and "neck_id = 43.2" in d["scad"]
        m = c.get(f"/api/sessions/{sid}/customizer").json()
        assert m["preview"]["gen"] == r["gen"]
        # an assert failure comes back as a human message, not a compile
        r = c.post(f"/api/sessions/{sid}/preview", json={"values": {"scallop_depth": 20}}).json()
        assert not r["ok"] and r["assert_failures"] == ["scallops too deep for the loop height"]
        # presets in OpenSCAD's parameter-sets format, next to part.scad
        r = c.put(f"/api/sessions/{sid}/presets/wide%20loop", json={"values": {"loop_inner_w": 50, "scallops": False, "bogus": 1}}).json()
        assert r["presets"] == {"wide loop": {"loop_inner_w": 50, "scallops": False}}
        doc = json.loads((appmod.SESSIONS_DIR / sid / "part.json").read_text())
        assert doc["parameterSets"]["wide loop"]["loop_inner_w"] == "50"
        assert c.get(f"/api/sessions/{sid}/presets").json()["presets"]["wide loop"]["scallops"] is False
        assert c.delete(f"/api/sessions/{sid}/presets/wide%20loop").json()["presets"] == {}
        assert c.delete(f"/api/sessions/{sid}/presets/nope").status_code == 404
        # apply & verify: a bound fit dimension moves the spec target with it
        r = c.post(f"/api/sessions/{sid}/params", json={"values": {"neck_id": 44.0, "loop_inner_h": 24}}).json()
        assert r["iteration"] == 1 and r["compile"]["ok"] and r["spec_changed"] == [{"dim": "neck_ring.inner_diameter", "param": "neck_id", "from": 43.2, "to": 44.0}]
        d = c.get(f"/api/sessions/{sid}").json()
        dim = d["spec"]["interfaces"][0]["dims"]["inner_diameter"]
        assert dim["target"] == 44.0 and dim["status"] == "confirmed" and dim["estimates"][-1]["source"] == "user_stated"
        assert "neck_id = 44;" in d["scad"] or "neck_id = 44.0;" in d["scad"]
        m = c.get(f"/api/sessions/{sid}/customizer").json()
        assert m["verified"]["iteration"] == 1 and m["verified"]["values"]["neck_id"] == 44 and m["verified"]["values"]["loop_inner_h"] == 24
        derived = {x["name"]: x["value"] for x in m["derived"]}
        assert derived["bore"] == 44.25
        # update_spec=false leaves the spec alone
        r = c.post(f"/api/sessions/{sid}/params", json={"values": {"neck_id": 43.2}, "update_spec": False}).json()
        assert r["spec_changed"] == [] and c.get(f"/api/sessions/{sid}").json()["spec"]["interfaces"][0]["dims"]["inner_diameter"]["target"] == 44.0
