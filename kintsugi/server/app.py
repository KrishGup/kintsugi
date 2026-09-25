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
    return {"ok": True, "version": __version__, "openscad": openscad_version(), "sessions_dir": str(SESSIONS_DIR)}


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
    photos = []
    for p in sorted((s.dir / "photos").iterdir()) if (s.dir / "photos").exists() else []:
        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") and not p.name.endswith(".grade.json"):
            g = p.with_suffix(p.suffix + ".grade.json")
            photos.append({"file": f"photos/{p.name}", "grade": json.loads(g.read_text()) if g.exists() else None})
    return {
        "meta": meta, "spec": spec.model_dump(mode="json", exclude_none=True), "spec_yaml": spec.to_yaml(),
        "params": params, "checks": checks, "iterations": iterations, "critic": critic, "photos": photos,
        "scad": s.scad_path.read_text(encoding="utf-8") if s.scad_path.exists() else None,
        "stl": "part.stl" if s.stl_path.exists() else None, "running": sid in RUNS and not RUNS[sid].done(),
        "export": sorted(p.name for p in (s.dir / "export").iterdir()) if (s.dir / "export").exists() else [],
        "unconfirmed": spec.unconfirmed_interface_dims(),
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
async def upload_photos(sid: str, files: list[UploadFile] = File(...), expect_sheet: bool = Form(True)):
    s = _session(sid)
    from kintsugi.measure.grade import grade_capture
    import cv2
    import numpy as np
    out = []
    for f in files:
        data = await f.read()
        name = Path(f.filename or "photo.jpg").name
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
        out.append({"file": f"photos/{dest.name}", "grade": grade})
        s.emit("photo", file=f"photos/{dest.name}", ok=bool(grade and grade.get("ok")))
    s.commit("photos uploaded")
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
    from kintsugi.agent.intake import run_intake
    photos = [_safe_path(s, p) for p in body.photos] if body.photos else sorted(p for p in (s.dir / "photos").glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    res = await run_intake(s, body.text, photos)
    return res


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
    from kintsugi.agent.designer import run_designer
    resume = None
    if body.answer:
        q = s.meta.get("question")
        resume = f"The user answered your question{(' (' + q['question'] + ')') if q else ''}: {body.answer}\nContinue the design accordingly."
        s.update_meta(question=None)
        s.emit("answer", text=body.answer)
    photos = sorted(p for p in (s.dir / "photos").glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))

    async def _run():
        try:
            await run_designer(s, model=body.model, budget=body.budget, critic_rounds=body.critic_rounds, user_message=body.message,
                               strategy=body.strategy, resume_message=resume, photos=photos[:4])
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
async def events(sid: str, request: Request, since: int = 0):
    s = _session(sid)

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
        return export_bundle(s)
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
