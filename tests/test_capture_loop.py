"""The capture loop: standards, the evidence graph, automatic sheet measurement, follow-up rounds through the API."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import pytest

from kintsugi.measure.synth import ring, synth_photo
from kintsugi.scad.compile import openscad_version
from kintsugi.spec import evidence as E
from kintsugi.spec.model import Estimate, PartSpec
from kintsugi.spec.standards import match_standards

SPEC = Path(__file__).parent.parent / "eval" / "specs" / "bottle_handle.yaml"


def fresh_intake_spec() -> tuple[PartSpec, dict]:
    from kintsugi.agent.fake import fake_complete
    from kintsugi.agent.intake import sanitize_spec_data
    data = json.loads(fake_complete("You are the intake engineer", []))
    spec = PartSpec.model_validate(sanitize_spec_data(data["spec"]))
    return spec, data


def test_standards_match_and_hints():
    from kintsugi.spec.standards import hints_for_model
    ids = [s.id for s in match_standards("the carry handle of this wide-mouth Nalgene snapped; the cap is 63-415")]
    assert "neck_63_415" in ids
    assert [s.id for s in match_standards("m30 bolt")] == [] and [s.id for s in match_standards("an M5 bolt through 3/4 inch PVC")][:2]
    txt = hints_for_model(match_standards("18650 holder"))
    assert "18650" in txt and "standard:<id>" in txt


def test_evidence_graph_missing_and_plan():
    spec, data = fresh_intake_spec()
    g = E.build(spec, intake=data)
    assert not g.ready and set(g.readiness["blocking"]) == {"neck_ring.inner_diameter", "neck_ring.ring_height"}
    kinds = {n["type"] for n in g.nodes}
    assert {"dim", "estimate", "shot", "question"} <= kinds
    reqs = E.plan_round(spec, g.missing)
    assert reqs[0].kind == "photo" and reqs[0].dims == ["neck_ring.inner_diameter"] and reqs[0].priority == 0
    assert any(r.kind == "measure" and r.dims == ["neck_ring.ring_height"] for r in reqs)
    # a ruler reading confirms the height; a sheet estimate that agrees lifts the diameter
    spec.confirm("neck_ring.ring_height", 6.2, source="user_ruler")
    spec.add_estimate("neck_ring.inner_diameter", Estimate(value=43.1, source="rectified_sheet", conf=0.85, photo="photos/r1_photo1_a.jpg"))
    g2 = E.build(spec, photos=[{"file": "photos/r1_photo1_a.jpg", "grade": {"ok": True, "markers_found": 4}}],
                 intake={**data, "rounds": [{"n": 1, "requests": [r.to_dict() for r in reqs]}]})
    assert g2.ready and g2.readiness["blocking"] == [] and g2.readiness["confirmed"] >= 1
    assert any(e["rel"] == "fulfils" for e in g2.edges) and any(e["rel"] == "measured_in" for e in g2.edges)
    # a confirmed spec has nothing missing and plans nothing
    full = PartSpec.load(SPEC)
    assert E.build(full).ready and E.plan_round(full) == []
    # a standard value counts as evidence below a real measurement
    spec2, _ = fresh_intake_spec()
    spec2.add_estimate("neck_ring.inner_diameter", Estimate(value=42.5, source="standard:neck_43_400", conf=0.55))
    d = spec2.get_dim("neck_ring.inner_diameter")
    assert d.status == "estimated" and abs(d.target - 42.5) < 1e-6
    assert [m.reason for m in E.missing(spec2) if m.dim == "neck_ring.inner_diameter"] == ["low_confidence"]


@pytest.fixture(scope="module")
def sheet_photo(tmp_path_factory):
    # a 43 mm bore seen as a ring lying on the sheet: outer 62, inner 43 (the bottle neck opening-down)
    img, truth = synth_photo([ring(105.0, 140.0, 62.0, 43.0)], tilt_deg=8.0, seed=3)
    p = tmp_path_factory.mktemp("photo") / "r1_photo1_neck.jpg"
    cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return p


@pytest.mark.skipif(openscad_version() is None, reason="openscad not installed")
def test_auto_measure_attaches_estimate(tmp_path, sheet_photo):
    from kintsugi.agent import capture as C
    from kintsugi.session.workspace import Session

    spec, data = fresh_intake_spec()
    s = Session.create("cap", spec, sessions_dir=tmp_path)
    data["rounds"] = [{"n": 1, "requests": [{"id": "r1_photo1", "kind": "photo", "dims": ["neck_ring.inner_diameter"], "label": "r1_photo1"}]}]
    C.save_intake(s, data)
    import shutil
    dest = s.dir / "photos" / sheet_photo.name
    shutil.copy(sheet_photo, dest)
    applied = C.auto_measure(s, spec)
    assert applied and applied[0]["dim"] == "neck_ring.inner_diameter"
    assert abs(applied[0]["value"] - 43.0) < 0.4, applied
    d = s.spec().get_dim("neck_ring.inner_diameter")
    assert any(e.source == "rectified_sheet" for e in d.estimates) and abs(d.target - 43.0) < 0.4
    # idempotent: the same photo is not attached twice
    assert C.auto_measure(s, s.spec()) == []
    snap = C.evidence_snapshot(s)
    assert any(n["type"] == "estimate" and n["source"] == "rectified_sheet" for n in snap["nodes"])


@pytest.mark.skipif(openscad_version() is None, reason="openscad not installed")
def test_intake_graph_and_followup_rounds_via_api(tmp_path, monkeypatch, sheet_photo):
    """Intake (fake vision) -> round 1 requests -> photo upload is auto-measured -> ruler answer -> follow-up declares ready."""
    monkeypatch.setenv("KIN_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("KIN_PROVIDER", "fake")
    from fastapi.testclient import TestClient

    import kintsugi.server.app as appmod
    from kintsugi.agent.llm import get_llm

    get_llm(reset=True)
    appmod.SESSIONS_DIR = (tmp_path / "sessions").resolve()
    appmod.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    with TestClient(appmod.app) as c:
        sid = c.post("/api/sessions", json={"name": "bottle handle", "intake": True}).json()["meta"]["id"]
        # a context photo without the sheet
        blank = tmp_path / "ctx.jpg"
        import numpy as np
        cv2.imwrite(str(blank), np.full((480, 640, 3), 180, np.uint8))
        with open(blank, "rb") as f:
            c.post(f"/api/sessions/{sid}/photos", files=[("files", ("ctx.jpg", f, "image/jpeg"))], data={"expect_sheet": "false"})
        r = c.post(f"/api/sessions/{sid}/intake", json={"text": "the carry handle of this wide mouth nalgene snapped at the ring"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["object"] and data["round"] and data["round"]["n"] == 1 and not data["evidence"]["ready"]
        reqs = data["round"]["requests"]
        photo_req = next(x for x in reqs if x["kind"] == "photo")
        assert "neck_ring.inner_diameter" in photo_req["dims"] and photo_req["label"]
        assert any(x["kind"] == "measure" and x["dims"] == ["neck_ring.ring_height"] for x in reqs)
        assert "neck_63_415" in [s["id"] for s in data.get("standards", [])]  # recognised from the sentence
        g = data["graph"]
        assert g["status"] == "waiting" and g["waiting_on"] == "capture" and g["request"]["requests"]
        d = c.get(f"/api/sessions/{sid}").json()
        assert d["stage"] == "capture" and d["intake"]["rounds"][0]["n"] == 1 and d["readiness"]["ready"] is False
        # upload the requested sheet photo under the request's label -> measured automatically
        with open(sheet_photo, "rb") as f:
            up = c.post(f"/api/sessions/{sid}/photos", files=[("files", ("neck.jpg", f, "image/jpeg"))],
                        data={"expect_sheet": "true", "label": photo_req["label"]}).json()
        assert up[0]["file"].startswith(f"photos/{photo_req['label']}_") and up[0]["estimates"], up
        assert abs(up[0]["estimates"][0]["value"] - 43.0) < 0.4
        # the ruler reading for the height
        a = c.post(f"/api/sessions/{sid}/answers", json={"answers": [{"id": "m1", "dim": "neck_ring.ring_height", "kind": "measure", "value": 6.4}], "advance": False}).json()
        assert a["ok"] and "neck_ring.ring_height" not in a["unconfirmed"]
        # follow-up: everything is now known well enough -> ready, stage advances
        fu = c.post(f"/api/sessions/{sid}/followup").json()
        assert fu["ready"] is True and fu["round"] is None, fu["readiness"]
        d = c.get(f"/api/sessions/{sid}").json()
        assert d["stage"] == "spec" and d["readiness"]["ready"]
        ev = c.get(f"/api/sessions/{sid}/evidence").json()
        assert ev["ready"] and any(n["type"] == "standard" for n in ev["nodes"])
        kinds = [e["kind"] for e in c.get(f"/api/sessions/{sid}/events", params={"once": "true"}).json()["events"]]
        assert "capture_round" in kinds and "capture_ready" in kinds and "graph_run" in kinds and "estimate" in kinds
        gr = c.get(f"/api/sessions/{sid}/graphs").json()
        assert gr["intake"]["status"] == "waiting" and gr["shapes"]["iteration"]["critical_path"]
