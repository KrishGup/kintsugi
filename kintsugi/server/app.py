"""FastAPI server: sessions, uploads, runs, SSE event stream, file serving, export."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from kintsugi import REPO_DIR, TEMPLATES_DIR, __version__
from kintsugi.agent.export import export_bundle
from kintsugi.agent.llm import DEFAULT_MODELS, get_llm
from kintsugi.agent.pipeline import run_iteration
from kintsugi.scad.compile import compile_scad, openscad_version
from kintsugi.scad.customizer import parse_customizer, set_param_values
from kintsugi.session.workspace import DEFAULT_SESSIONS_DIR, Session
from kintsugi.spec.model import Estimate, PartSpec

app = FastAPI(title="Kintsugi", version=__version__)
SESSIONS_DIR = Path(os.environ.get("KIN_SESSIONS_DIR", DEFAULT_SESSIONS_DIR)).resolve()
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
RUNS: dict[str, asyncio.Task] = {}


def _session(sid: str) -> Session:
    d = SESSIONS_DIR / sid
    if not (d / "session.json").exists():
        raise HTTPException(404, f"session {sid} not found")
    return Session.open(d)


def _readiness(spec: PartSpec) -> dict[str, Any]:
    try:
        from kintsugi.spec.evidence import missing, readiness
        rd = readiness(spec)
        rd["missing"] = [m.to_dict() for m in missing(spec)]
        return rd
    except Exception as e:  # noqa: BLE001
        return {"ready": True, "error": str(e)}


def _safe_path(session: Session, rel: str) -> Path:
    p = (session.dir / rel).resolve()
    if session.dir.resolve() not in p.parents and p != session.dir.resolve():
        raise HTTPException(400, "bad path")
    if not p.exists() or not p.is_file():
        raise HTTPException(404, rel)
    return p


# ---- meta -------------------------------------------------------------------------------------------

@app.get("/api/health")
def health():
    llm = get_llm()
    return {"ok": True, "version": __version__, "openscad": openscad_version(), "sessions_dir": str(SESSIONS_DIR), "llm": llm.status()}


class Settings(BaseModel):
    openai_api_key: str | None = None
    provider: str | None = None  # openai | agent | fake
    designer_model: str | None = None
    critic_model: str | None = None
    vision_model: str | None = None
    effort: str | None = None
    persist: bool = False  # also write to .env next to the working directory


@app.get("/api/settings")
def get_settings():
    llm = get_llm()
    key = os.environ.get("OPENAI_API_KEY", "")
    return {"llm": llm.status(), "openai_key_masked": (key[:7] + "…" + key[-4:]) if len(key) > 12 else ("set" if key else ""),
            "defaults": DEFAULT_MODELS, "providers": ["openai", "agent", "fake"]}


async def _probe_openai(model: str) -> dict[str, Any]:
    """A free call to OpenAI to validate the key and the model id (models.retrieve)."""
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(timeout=20, max_retries=1)
        m = await client.models.retrieve(model)
        return {"checked": True, "ok": True, "model": getattr(m, "id", model)}
    except Exception as e:  # noqa: BLE001
        name = type(e).__name__
        status = getattr(e, "status_code", None)
        if status == 401 or "Authentication" in name:
            return {"checked": True, "ok": False, "message": "OpenAI rejected the API key (401)."}
        if status == 404 or "NotFound" in name:
            return {"checked": True, "ok": False, "message": f"The model '{model}' is not available to this key."}
        return {"checked": False, "ok": None, "message": f"Could not reach OpenAI to verify the key ({name}); it is saved anyway."}


@app.post("/api/settings/test")
async def test_settings():
    llm = get_llm()
    if llm.provider != "openai":
        return {"checked": False, "ok": True, "message": f"{llm.provider} provider needs no key check"}
    if not os.environ.get("OPENAI_API_KEY"):
        return {"checked": True, "ok": False, "message": "OPENAI_API_KEY is not set"}
    return await _probe_openai(llm.models["designer"])


@app.post("/api/settings")
async def set_settings(body: Settings):
    changed = {}
    if body.openai_api_key is not None and body.openai_api_key.strip():
        os.environ["OPENAI_API_KEY"] = body.openai_api_key.strip()
        changed["OPENAI_API_KEY"] = "set"
    if body.provider:
        if body.provider not in ("openai", "agent", "fake"):
            raise HTTPException(400, "provider must be openai, agent or fake")
        os.environ["KIN_PROVIDER"] = body.provider
        changed["KIN_PROVIDER"] = body.provider
    for k, v in (("KIN_DESIGNER_MODEL", body.designer_model), ("KIN_CRITIC_MODEL", body.critic_model), ("KIN_VISION_MODEL", body.vision_model),
                 ("KIN_REASONING_EFFORT", body.effort)):
        if v:
            os.environ[k] = v
            changed[k] = v
    if body.persist and changed:
        env_path = Path(".env")
        lines = env_path.read_text().splitlines() if env_path.exists() else []
        for k, v in changed.items():
            val = os.environ[k]
            lines = [ln for ln in lines if not ln.startswith(k + "=")]
            lines.append(f"{k}={val}")
        env_path.write_text("\n".join(lines) + "\n")
    llm = get_llm(reset=True)
    probe = None
    if llm.provider == "openai" and os.environ.get("OPENAI_API_KEY") and (body.openai_api_key or body.designer_model or body.provider):
        probe = await _probe_openai(llm.models["designer"])
    return {"ok": True, "changed": list(changed), "llm": llm.status(), "probe": probe}


@app.get("/api/templates")
def templates():
    out = []
    for p in sorted(TEMPLATES_DIR.glob("*.scad")):
        desc = ""
        for line in p.read_text(encoding="utf-8").splitlines()[:6]:
            if "TEMPLATE:" in line:
                desc = line.split("TEMPLATE:", 1)[1].strip()
                break
        out.append({"name": p.stem, "description": desc, "params": [q.to_dict() for q in parse_customizer(p.read_text(encoding="utf-8"))]})
    return out


@app.get("/api/templates/{name}")
def template_source(name: str):
    p = TEMPLATES_DIR / f"{name}.scad"
    if not p.exists():
        raise HTTPException(404)
    return PlainTextResponse(p.read_text(encoding="utf-8"))


@app.get("/api/specs/examples")
def example_specs():
    out = []
    for p in sorted((REPO_DIR / "eval" / "specs").glob("*.yaml")):
        out.append({"name": p.stem, "yaml": p.read_text(encoding="utf-8")})
    return out


@app.get("/api/sheet.pdf")
def calibration_sheet(paper: str = "letter"):
    from kintsugi.measure.sheet import make_calibration_sheet
    out = SESSIONS_DIR / f"calibration_sheet_{paper}.pdf"
    if not out.exists():
        make_calibration_sheet(out, paper=paper)
    return FileResponse(out, media_type="application/pdf", filename="kintsugi_calibration_sheet.pdf")


# ---- sessions ---------------------------------------------------------------------------------------

class NewSession(BaseModel):
    name: str | None = None
    spec_yaml: str | None = None
    scad: str | None = None
    intake: bool = False  # photo-first session: starts at the intake stage


class StageReq(BaseModel):
    stage: str


@app.post("/api/sessions/{sid}/stage")
def set_stage(sid: str, body: StageReq):
    if body.stage not in ("intake", "capture", "spec", "design", "review", "export"):
        raise HTTPException(400, "unknown stage")
    s = _session(sid)
    s.update_meta(stage=body.stage)
    s.emit("stage", stage=body.stage)
    return {"ok": True, "stage": body.stage}


class Answer(BaseModel):
    id: str | None = None
    dim: str | None = None
    kind: str = "text"  # number | choice | text
    value: str | float | None = None
    question: str | None = None


class AnswersReq(BaseModel):
    answers: list[Answer]
    advance: bool = True  # move to the spec stage after applying (false while a capture round is still open)


@app.post("/api/sessions/{sid}/answers")
def answer_questions(sid: str, body: AnswersReq):
    """Apply the user's answers to the intake questions: numbers confirm spec dimensions, choices become design notes."""
    s = _session(sid)
    spec = s.spec()
    applied = []
    for a in body.answers:
        if a.value is None or a.value == "":
            continue
        if a.kind in ("number", "measure") and a.dim:
            try:
                v = float(a.value)
            except (TypeError, ValueError):
                continue
            if spec.get_dim(a.dim) is not None:
                spec.confirm(a.dim, v, source="user_ruler")
                applied.append({"dim": a.dim, "value": v})
                continue
        note = f"{a.question or a.id or 'answer'}: {a.value}"
        spec.part.notes = (spec.part.notes + "\n" + note).strip() if spec.part.notes else note
        if a.kind == "choice" and a.value:
            spec.part.design_intent = (spec.part.design_intent + f"; {a.value}").strip("; ") if spec.part.design_intent else str(a.value)
        applied.append({"note": note})
    spec.save(s.spec_path)
    s.commit("answers applied to spec")
    s.emit("answers", applied=applied)
    from kintsugi.spec.evidence import readiness
    rd = readiness(spec)
    if body.advance or rd["ready"]:
        s.update_meta(stage="spec")
    return {"ok": True, "applied": applied, "unconfirmed": spec.unconfirmed_interface_dims(), "spec_yaml": spec.to_yaml(), "readiness": rd}


@app.get("/api/sessions")
def list_sessions():
    return Session.list_all(SESSIONS_DIR)


@app.post("/api/sessions")
def create_session(body: NewSession):
    spec = PartSpec.from_yaml(body.spec_yaml) if body.spec_yaml else PartSpec()
    name = body.name or spec.part.name or "part"
    if not spec.part.name or spec.part.name == "part":
        spec.part.name = name.replace(" ", "_")
    s = Session.create(name, spec, sessions_dir=SESSIONS_DIR)
    s.update_meta(stage="intake" if body.intake else "spec")
    if body.scad:
        s.scad_path.write_text(body.scad, encoding="utf-8")
        s.commit("initial part.scad")
    return session_detail(s.id)


@app.get("/api/sessions/{sid}")
def session_detail(sid: str):
    s = _session(sid)
    meta = s.meta
    spec = s.spec() if s.spec_path.exists() else PartSpec()
    params = json.loads((s.dir / "params.json").read_text()) if (s.dir / "params.json").exists() else []
    checks = json.loads((s.dir / "checks.json").read_text()) if (s.dir / "checks.json").exists() else None
    hist = json.loads((s.dir / "history.json").read_text()) if (s.dir / "history.json").exists() else []
    iterations = []
    for e in hist:
        n = e["iteration"]
        d = s.dir / "iterations" / f"iter_{n:02d}"
        iterations.append({**e, "sheet": f"iterations/iter_{n:02d}/sheets/iter_{n:02d}_sheet.png" if (d / "sheets" / f"iter_{n:02d}_sheet.png").exists() else None,
                           "sections": f"iterations/iter_{n:02d}/sheets/iter_{n:02d}_sections.png" if (d / "sheets" / f"iter_{n:02d}_sections.png").exists() else None,
                           "stl": f"iterations/iter_{n:02d}/part.stl" if (d / "part.stl").exists() else None,
                           "views": sorted(p.name for p in (d / "sheets" / "views").glob("*.png")) if (d / "sheets" / "views").exists() else []})
    critic = []
    for p in sorted((s.dir / "critic").glob("*.json")):
        try:
            critic.append({"file": p.stem, **json.loads(p.read_text())})
        except json.JSONDecodeError:
            pass
    intake_data = json.loads((s.dir / "intake.json").read_text()) if (s.dir / "intake.json").exists() else None
    rd = _readiness(spec)
    from kintsugi.graph.flow import derive_stage, open_transitions
    flow_state = {"meta": meta, "running": sid in RUNS and not RUNS[sid].done(), "has_intake": intake_data is not None,
                  "has_spec": bool(spec.interfaces or spec.requirements), "ready": bool(rd.get("ready")), "iterations": bool(hist),
                  "has_passing_iteration": any(e.get("ok") for e in hist)}
    stage = derive_stage(flow_state)
    photos = []
    by_photo: dict[str, list[dict[str, Any]]] = {}
    for qual, dim, _ in spec.all_dims():
        for e in dim.estimates:
            if e.photo:
                by_photo.setdefault(str(e.photo), []).append({"dim": qual, "value": e.value, "conf": e.conf, "photo": e.photo, "status": dim.status})
    for p in sorted((s.dir / "photos").iterdir()) if (s.dir / "photos").exists() else []:
        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") and not p.name.endswith(".grade.json"):
            g = p.with_suffix(p.suffix + ".grade.json")
            photos.append({"file": f"photos/{p.name}", "grade": json.loads(g.read_text()) if g.exists() else None,
                           "estimates": by_photo.get(f"photos/{p.name}", [])})
    return {
        "meta": meta, "spec": spec.model_dump(mode="json", exclude_none=True), "spec_yaml": spec.to_yaml(),
        "params": params, "checks": checks, "iterations": iterations, "critic": critic, "photos": photos,
        "scad": s.scad_path.read_text(encoding="utf-8") if s.scad_path.exists() else None,
        "stl": "part.stl" if s.stl_path.exists() else None, "running": sid in RUNS and not RUNS[sid].done(),
        "export": sorted(p.name for p in (s.dir / "export").iterdir()) if (s.dir / "export").exists() else [],
        "unconfirmed": spec.unconfirmed_interface_dims(),
        "intake": intake_data,
        "readiness": rd,
        "stage": stage,
        "flow": {"stage": stage, "transitions": open_transitions(stage, flow_state)},
        "llm": get_llm().status(),
    }


class SpecUpdate(BaseModel):
    spec_yaml: str


@app.put("/api/sessions/{sid}/spec")
def update_spec(sid: str, body: SpecUpdate):
    s = _session(sid)
    spec = PartSpec.from_yaml(body.spec_yaml)
    spec.save(s.spec_path)
    s.commit("spec updated by user")
    s.emit("spec_updated")
    return {"ok": True, "spec": spec.model_dump(mode="json", exclude_none=True)}


class ConfirmDim(BaseModel):
    dim: str
    value: float
    source: str = "user_stated"


@app.post("/api/sessions/{sid}/confirm")
def confirm_dim(sid: str, body: ConfirmDim):
    s = _session(sid)
    spec = s.spec()
    spec.confirm(body.dim, body.value, source=body.source)
    spec.save(s.spec_path)
    s.commit(f"confirmed {body.dim} = {body.value}")
    s.emit("dim_confirmed", dim=body.dim, value=body.value, source=body.source)
    return {"ok": True, "unconfirmed": spec.unconfirmed_interface_dims()}


# ---- photos -----------------------------------------------------------------------------------------

@app.post("/api/sessions/{sid}/photos")
async def upload_photos(sid: str, files: list[UploadFile] = File(...), expect_sheet: bool = Form(True), label: str | None = Form(None)):
    """Store and grade photos. `label` (e.g. `shot2`) prefixes the file name so the UI can match a capture-plan slot."""
    s = _session(sid)
    from kintsugi.measure.grade import grade_capture
    import cv2
    import numpy as np
    out = []
    prefix = "".join(ch for ch in (label or "") if ch.isalnum() or ch in "-_")[:32]
    for f in files:
        data = await f.read()
        name = Path(f.filename or "photo.jpg").name
        if prefix:
            name = f"{prefix}_{name}"
        dest = s.dir / "photos" / name
        i = 1
        while dest.exists():
            dest = s.dir / "photos" / f"{Path(name).stem}_{i}{Path(name).suffix}"
            i += 1
        dest.write_bytes(data)
        grade = None
        try:
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            g = grade_capture(img, expect_sheet=expect_sheet)
            grade = g.__dict__ if hasattr(g, "__dict__") else dict(g)
            grade = {k: (float(v) if isinstance(v, (np.floating,)) else v) for k, v in grade.items() if not k.startswith("_")}
            dest.with_suffix(dest.suffix + ".grade.json").write_text(json.dumps(grade, default=lambda o: float(o) if hasattr(o, "__float__") else str(o)))
        except Exception as e:
            grade = {"error": str(e)}
        out.append({"file": f"photos/{dest.name}", "grade": grade, "path": dest})
        s.emit("photo", file=f"photos/{dest.name}", ok=bool(grade and grade.get("ok")))
    s.commit("photos uploaded")
    # measure what the new photos can show (sheet photos -> circle diameters on the spec's planar dimensions)
    estimates: list[dict[str, Any]] = []
    try:
        from kintsugi.agent.capture import auto_measure
        loop = asyncio.get_running_loop()
        estimates = await loop.run_in_executor(None, lambda: auto_measure(s, None, [o["path"] for o in out]))
    except Exception as e:  # noqa: BLE001
        s.emit("error", message=f"auto-measure failed: {type(e).__name__}: {e}")
    for o in out:
        o.pop("path", None)
        o["estimates"] = [x for x in estimates if x.get("photo") == o["file"]]
    return out


class MeasureReq(BaseModel):
    photo: str
    mode: str = "sheet"  # sheet | reference
    reference: str = "auto"
    min_d: float = 5.0
    max_d: float = 120.0
    roi_mm: list[float] | None = None
    dim: str | None = None  # spec dimension to attach the estimate to


@app.post("/api/sessions/{sid}/measure")
def measure(sid: str, body: MeasureReq):
    s = _session(sid)
    import cv2
    from kintsugi.measure import aruco, planar, reference
    p = _safe_path(s, body.photo)
    img = cv2.imread(str(p))
    if img is None:
        raise HTTPException(400, "unreadable image")
    result: dict[str, Any] = {"photo": body.photo, "mode": body.mode}
    if body.mode == "sheet":
        markers = aruco.detect_markers(img)
        H = aruco.sheet_homography(markers)
        if H is None:
            raise HTTPException(422, f"need at least 2 markers, found {len(markers)}")
        rect = aruco.rectify(img, H, mm_per_px=0.1)
        circles = planar.find_circles(rect, body.min_d, body.max_d, roi_mm=tuple(body.roi_mm) if body.roi_mm else None)
        result["markers"] = len(markers)
        result["tilt_deg"] = aruco.estimate_tilt_deg(markers, (img.shape[1], img.shape[0]))
        result["circles"] = [{"cx": c.cx, "cy": c.cy, "d": c.d, "conf": c.conf, "method": c.method} for c in circles[:6]]
        try:
            outlines = planar.find_outline(rect, roi_mm=tuple(body.roi_mm) if body.roi_mm else None)
            result["outline_points"] = int(len(outlines[0])) if outlines else 0
            if outlines:
                result["openscad_polygon"] = planar.to_openscad_polygon(outlines[0])
        except Exception:
            pass
        rect_path = s.dir / "measure" / (p.stem + "_rectified.png")
        cv2.imwrite(str(rect_path), rect.img)
        result["rectified"] = f"measure/{rect_path.name}"
        source, conf_scale = "rectified_sheet", 1.0
    else:
        ref = reference.detect_reference(img, kind=body.reference)
        if ref is None:
            raise HTTPException(422, "no reference object found")
        m = reference.measure_with_reference(img, ref)
        result["reference"] = {"kind": ref.kind, "mm_per_px": ref.mm_per_px, "conf": ref.conf}
        result.update({k: v for k, v in m.items() if k != "outline"})
        circles = m.get("circles") or []
        result["circles"] = circles[:6] if isinstance(circles, list) else []
        source, conf_scale = "reference_object", 0.7
    if body.dim and result.get("circles"):
        spec = s.spec()
        c = result["circles"][0]
        d_val = c["d"] if isinstance(c, dict) else c.d
        conf = min(0.95, (c.get("conf", 0.6) if isinstance(c, dict) else 0.6) * conf_scale)
        spec.add_estimate(body.dim, Estimate(value=round(float(d_val), 2), source=source, conf=conf, photo=body.photo))
        spec.save(s.spec_path)
        s.commit(f"estimate {body.dim} from {body.photo}")
        s.emit("estimate", dim=body.dim, value=round(float(d_val), 2), source=source, conf=conf)
        result["attached_to"] = body.dim
    return result


# ---- intake -----------------------------------------------------------------------------------------

class IntakeReq(BaseModel):
    text: str = ""
    photos: list[str] = []


@app.post("/api/sessions/{sid}/intake")
async def intake(sid: str, body: IntakeReq):
    s = _session(sid)
    ok, why = get_llm().available()
    if not ok:
        raise HTTPException(412, f"model provider not ready: {why}. Add your OpenAI API key in Settings.")
    from kintsugi.agent.intake import run_intake
    photos = [_safe_path(s, p) for p in body.photos] if body.photos else sorted(p for p in (s.dir / "photos").glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    res = await run_intake(s, body.text, photos)
    return res


@app.post("/api/sessions/{sid}/followup")
async def followup(sid: str):
    """Measure the photos, rebuild the evidence graph, and write the next capture round (or declare the spec ready)."""
    s = _session(sid)
    from kintsugi.agent.capture import run_capture_round
    return await run_capture_round(s)


@app.get("/api/sessions/{sid}/evidence")
def evidence(sid: str):
    s = _session(sid)
    from kintsugi.agent.capture import evidence_snapshot
    return evidence_snapshot(s)


@app.get("/api/sessions/{sid}/graphs")
def graphs(sid: str, iteration: int | None = None):
    """Graph traces: the intake run, the latest (or given) iteration, the export."""
    s = _session(sid)
    out: dict[str, Any] = {}
    p = s.dir / "intake_graph.json"
    if p.exists():
        out["intake"] = json.loads(p.read_text())
    n = iteration or int(s.meta.get("iteration", 0))
    if n:
        q = s.dir / "iterations" / f"iter_{n:02d}" / "graph.json"
        if q.exists():
            out["iteration"] = {"iteration": n, **json.loads(q.read_text())}
    e = s.dir / "export" / "export_graph.json"
    if e.exists():
        out["export"] = json.loads(e.read_text())
    from kintsugi.graph.flow import describe as flow_describe
    from kintsugi.graph.pipelines import export_graph, iteration_graph
    out["shapes"] = {"iteration": iteration_graph().describe(), "export": export_graph().describe()}
    out["flow"] = flow_describe(session_detail(sid)["stage"])
    return out


# ---- runs -------------------------------------------------------------------------------------------

class RunReq(BaseModel):
    message: str | None = None
    strategy: str | None = None
    budget: int = 8
    critic_rounds: int = 2
    model: str | None = None
    answer: str | None = None  # resumes a waiting session


@app.post("/api/sessions/{sid}/run", status_code=202)
async def start_run(sid: str, body: RunReq):
    s = _session(sid)
    if sid in RUNS and not RUNS[sid].done():
        raise HTTPException(409, "run already in progress")
    ok, why = get_llm().available()
    if not ok:
        raise HTTPException(412, f"model provider not ready: {why}. Add your OpenAI API key in Settings.")
    from kintsugi.agent.designer import run_designer
    s.update_meta(stage="design")
    resume = None
    if body.answer:
        q = s.meta.get("question") or {}
        resume = f"The user answered your question{(' (' + q['question'] + ')') if q.get('question') else ''}: {body.answer}\n"
        if q.get("photos"):
            spec_now = s.spec()
            lines = []
            for pr in q["photos"]:
                for dname in pr.get("dims") or []:
                    d = spec_now.get_dim(dname)
                    if d is not None:
                        lines.append(f"- {dname}: now {d.describe()} (status {d.status}; latest evidence: "
                                     + (", ".join(f"{e.value:g} mm from {e.source}" for e in d.estimates[-2:]) or "none") + ")")
            if lines:
                resume += "The photos you asked for were taken and measured; the spec now says:\n" + "\n".join(lines) + "\n"
        resume += "Continue the design accordingly."
        s.update_meta(question=None)
        s.emit("answer", text=body.answer)
    photos = sorted(p for p in (s.dir / "photos").glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))

    async def _run():
        try:
            out = await run_designer(s, model=body.model, budget=body.budget, critic_rounds=body.critic_rounds, user_message=body.message,
                                     strategy=body.strategy, resume_message=resume, photos=photos[:4])
            if out.status == "done":
                s.update_meta(stage="review")
        except Exception as e:  # pragma: no cover
            s.emit("error", message=f"{type(e).__name__}: {e}")
            s.update_meta(status="error")

    RUNS[sid] = asyncio.create_task(_run())
    return {"ok": True, "status": "started"}


@app.post("/api/sessions/{sid}/stop")
async def stop_run(sid: str):
    t = RUNS.get(sid)
    if t and not t.done():
        t.cancel()
        s = _session(sid)
        s.update_meta(status="stopped")
        s.emit("run_end", status="stopped")
        return {"ok": True, "stopped": True}
    return {"ok": True, "stopped": False}


@app.get("/api/sessions/{sid}/events")
async def events(sid: str, request: Request, since: int = 0, once: bool = False):
    """Server-sent events from the session log. `once=true` returns the events since `since` as JSON and closes."""
    s = _session(sid)
    if once:
        evs = s.events(since=since)
        return {"since": since, "next": since + len(evs), "events": evs}

    async def gen():
        idx = since
        heartbeat = time.time()
        while True:
            if await request.is_disconnected():
                break
            evs = s.events(since=idx)
            for ev in evs:
                idx += 1
                yield {"event": ev.get("kind", "event"), "id": str(idx), "data": json.dumps(ev, default=str)}
            if not evs:
                if time.time() - heartbeat > 15:
                    heartbeat = time.time()
                    yield {"event": "ping", "data": "{}"}
                await asyncio.sleep(0.5)

    return EventSourceResponse(gen())


# ---- editing: params, code, branch -------------------------------------------------------------------

class ParamsReq(BaseModel):
    values: dict[str, Any]
    label: str | None = None


@app.post("/api/sessions/{sid}/params")
def set_params(sid: str, body: ParamsReq):
    s = _session(sid)
    if not s.scad_path.exists():
        raise HTTPException(400, "no part.scad yet")
    src = s.scad_path.read_text(encoding="utf-8")
    s.scad_path.write_text(set_param_values(src, body.values), encoding="utf-8")
    res = run_iteration(s, label=body.label or ("parameters: " + ", ".join(f"{k}={v}" for k, v in body.values.items())))
    return res.to_dict()


class CodeReq(BaseModel):
    scad: str
    label: str | None = None


@app.post("/api/sessions/{sid}/iterate")
def iterate_code(sid: str, body: CodeReq):
    s = _session(sid)
    s.scad_path.write_text(body.scad, encoding="utf-8")
    res = run_iteration(s, label=body.label or "manual edit")
    return res.to_dict()


class BranchReq(BaseModel):
    iteration: int


@app.post("/api/sessions/{sid}/branch")
def branch(sid: str, body: BranchReq):
    s = _session(sid)
    s.checkout_iteration(body.iteration)
    return {"ok": True, "scad": s.scad_path.read_text(encoding="utf-8")}


@app.post("/api/sessions/{sid}/coupon")
def coupon(sid: str):
    s = _session(sid)
    if not s.scad_path.exists():
        raise HTTPException(400, "no part.scad")
    out = s.dir / "export" / "coupon.stl"
    r = compile_scad(s.scad_path, out, {"render_target": "coupon"}, timeout_s=180)
    if not r.ok:
        raise HTTPException(422, "; ".join(r.errors) or "coupon compile failed")
    s.emit("coupon", file="export/coupon.stl")
    return {"ok": True, "file": "export/coupon.stl"}


class CouponResult(BaseModel):
    clearance: float
    dim: str | None = None


@app.post("/api/sessions/{sid}/coupon/result")
def coupon_result(sid: str, body: CouponResult):
    s = _session(sid)
    spec = s.spec()
    changed = []
    for itf in spec.interfaces:
        if itf.fit != "none":
            itf.clearance = body.clearance
            for k, d in itf.dims.items():
                if k in ("inner_diameter", "bore", "outer_diameter", "od", "width"):
                    d.status = "confirmed"
                    d.estimates.append(Estimate(value=d.target if d.target is not None else 0.0, source="coupon", conf=0.99))
                    changed.append(f"{itf.id}.{k}")
    spec.save(s.spec_path)
    s.commit(f"coupon result: clearance {body.clearance}")
    s.emit("coupon_result", clearance=body.clearance, confirmed=changed)
    res = None
    if s.scad_path.exists() and "clearance" in s.scad_path.read_text(encoding="utf-8"):
        src = s.scad_path.read_text(encoding="utf-8")
        s.scad_path.write_text(set_param_values(src, {"clearance": body.clearance}), encoding="utf-8")
        res = run_iteration(s, label=f"coupon result: clearance {body.clearance}").to_dict()
    return {"ok": True, "confirmed": changed, "iteration": res}


# ---- export + files ---------------------------------------------------------------------------------

@app.post("/api/sessions/{sid}/export")
def do_export(sid: str):
    s = _session(sid)
    try:
        out = export_bundle(s)
        s.update_meta(stage="export")
        return out
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.get("/api/sessions/{sid}/files/{rel:path}")
def get_file(sid: str, rel: str):
    s = _session(sid)
    p = _safe_path(s, rel)
    media = {".stl": "model/stl", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".json": "application/json",
             ".scad": "text/plain", ".yaml": "text/plain", ".md": "text/markdown", ".zip": "application/zip", ".pdf": "application/pdf",
             ".3mf": "model/3mf"}.get(p.suffix.lower(), "application/octet-stream")
    return FileResponse(p, media_type=media, filename=p.name if p.suffix.lower() in (".zip", ".stl", ".3mf", ".pdf") else None)


@app.delete("/api/sessions/{sid}")
def delete_session(sid: str):
    s = _session(sid)
    t = RUNS.get(sid)
    if t and not t.done():
        raise HTTPException(409, "run in progress")
    shutil.rmtree(s.dir)
    return {"ok": True}


# ---- static UI --------------------------------------------------------------------------------------

_dist = REPO_DIR / "web" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="ui")
else:
    @app.get("/")
    def index():
        return JSONResponse({"kintsugi": __version__, "ui": "not built (cd web && npm install && npm run build)", "api": "/docs"})
