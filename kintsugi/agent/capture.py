"""The capture loop: measure what the photos can show, work out what is still missing, ask for the next round.

    photos + spec ──auto_measure──▶ estimates ──evidence──▶ missing / ready
                                                      │
                               ready ◀────────────────┴──not ready──▶ plan_round ──followup agent──▶ round N requests ──▶ (user) ──▶ photos …

`auto_measure` runs the calibration-sheet measurement on every usable photo and attaches circle diameters to the
dimensions a request or capture-plan shot targeted (a labelled upload), or to any unconfirmed planar dimension whose
current estimate the measured circle agrees with. `run_capture_round` builds the evidence graph and, when the spec
is not ready, writes the next round of requests — algorithmically, then refined by the follow-up agent when a model
is available — and records it in `intake.json`.
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from kintsugi import PACKAGE_DIR
from kintsugi.session.workspace import Session
from kintsugi.spec import evidence as E
from kintsugi.spec.model import Estimate, PartSpec

FOLLOWUP_PROMPT = (PACKAGE_DIR / "agent" / "prompts" / "followup.md").read_text(encoding="utf-8")
MAX_ROUNDS = 4
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")


# ---- session photo bookkeeping -----------------------------------------------------------------------------

def session_photos(session: Session) -> list[dict[str, Any]]:
    out = []
    pdir = session.dir / "photos"
    if not pdir.exists():
        return out
    for p in sorted(pdir.iterdir()):
        if p.suffix.lower() in IMAGE_EXT:
            g = p.with_suffix(p.suffix + ".grade.json")
            try:
                grade = json.loads(g.read_text()) if g.exists() else None
            except json.JSONDecodeError:
                grade = None
            out.append({"file": f"photos/{p.name}", "grade": grade, "path": p})
    return out


def load_intake(session: Session) -> dict[str, Any]:
    p = session.dir / "intake.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}


def save_intake(session: Session, data: dict[str, Any]) -> None:
    (session.dir / "intake.json").write_text(json.dumps(data, indent=2, default=str))


def _label_of(name: str, intake: dict[str, Any] | None = None) -> str:
    return E.label_of(name, E.known_labels(intake or {}))


def targets_by_label(intake: dict[str, Any]) -> dict[str, list[str]]:
    """Upload label (`shot2`, `r2_photo1`, `q_neck_id`) -> the dimensions that upload was meant to measure."""
    out: dict[str, list[str]] = {}
    for c in intake.get("capture_plan") or []:
        n = c.get("n")
        if n is not None and c.get("measures"):
            out[f"shot{int(n)}"] = [str(m) for m in c["measures"]]
    for rnd in intake.get("rounds") or []:
        for r in rnd.get("requests") or []:
            if r.get("kind") == "photo" and r.get("dims"):
                out[str(r.get("label") or r.get("id"))] = [str(d) for d in r["dims"]]
    for pr in (intake.get("designer_requests") or []):
        if pr.get("dims"):
            out[str(pr.get("label"))] = [str(d) for d in pr["dims"]]
    return out


# ---- automatic measurement ----------------------------------------------------------------------------------

_MEASURE_LOCKS: dict[str, threading.Lock] = {}
_MEASURE_LOCKS_GUARD = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _MEASURE_LOCKS_GUARD:
        return _MEASURE_LOCKS.setdefault(key, threading.Lock())


def diameter_range(spec: PartSpec) -> tuple[float, float]:
    """A search window for circle finding from the spec's planar targets (much faster than the full 4–140 mm sweep)."""
    vals = [d.target for _, d, _ in spec.all_dims() if d.measure and d.measure.recipe in E.PLANAR_RECIPES and isinstance(d.target, (int, float))]
    if not vals:
        return 4.0, 140.0
    return max(3.0, min(vals) * 0.6), min(200.0, max(vals) * 1.5)


def measure_photo_circles(session: Session, photo: Path, min_d: float = 4.0, max_d: float = 140.0) -> dict[str, Any]:
    """Sheet measurement of one photo (cached in measure/<name>.auto.json; concurrent callers wait for the first)."""
    cache = session.dir / "measure" / (photo.stem + ".auto.json")
    with _lock_for(str(cache)):
        if cache.exists():
            try:
                cached = json.loads(cache.read_text())
                lo, hi = cached.get("range", [4.0, 140.0])
                if lo <= min_d + 1e-9 and hi >= max_d - 1e-9:
                    return cached
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        return _measure_photo_circles(session, photo, cache, min_d, max_d)


def _measure_photo_circles(session: Session, photo: Path, cache: Path, min_d: float, max_d: float) -> dict[str, Any]:
    import cv2

    from kintsugi.measure import aruco, planar

    res: dict[str, Any] = {"photo": f"photos/{photo.name}", "markers": 0, "circles": [], "range": [min_d, max_d]}
    img = cv2.imread(str(photo))
    if img is None:
        res["error"] = "unreadable image"
    else:
        markers = aruco.detect_markers(img)
        res["markers"] = len(markers)
        H = aruco.sheet_homography(markers) if len(markers) >= 2 else None
        if H is not None:
            rect = aruco.rectify(img, H, mm_per_px=0.1)
            circles = planar.find_circles(rect, min_d, max_d)
            res["circles"] = [c.to_dict() for c in circles[:8]]
            try:
                res["tilt_deg"] = aruco.estimate_tilt_deg(markers, (img.shape[1], img.shape[0]))
            except Exception:
                pass
            rect_path = session.dir / "measure" / (photo.stem + "_rectified.png")
            cv2.imwrite(str(rect_path), rect.img)
            res["rectified"] = f"measure/{rect_path.name}"
    cache.parent.mkdir(exist_ok=True)
    cache.write_text(json.dumps(res, indent=2))
    return res


def auto_measure(session: Session, spec: PartSpec | None = None, only: list[Path] | None = None, emit: bool = True) -> list[dict[str, Any]]:
    """Attach sheet-measured circle diameters to the spec's planar dimensions. Returns the estimates applied."""
    spec = spec or session.spec()
    intake = load_intake(session)
    targets = targets_by_label(intake)
    photos = session_photos(session)
    if only is not None:
        names = {p.name for p in only}
        photos = [p for p in photos if p["path"].name in names]
    applied: list[dict[str, Any]] = []
    planar_dims = [(q, d) for q, d, i in spec.all_dims() if d.measure and d.measure.recipe in E.PLANAR_RECIPES and d.status != "confirmed"]
    if not planar_dims:
        return applied
    already = {(e.photo, q) for q, d, _ in spec.all_dims() for e in d.estimates if e.photo}
    lo, hi = diameter_range(spec)
    for p in photos:
        grade = p.get("grade") or {}
        if grade and grade.get("markers_found", 0) < 2 and grade.get("markers_found") is not None:
            continue
        res = measure_photo_circles(session, p["path"], lo, hi)
        circles = res.get("circles") or []
        if not circles:
            continue
        label = _label_of(p["path"].name, intake)
        wanted = targets.get(label, [])
        for q, d in planar_dims:
            if (p["file"], q) in already:
                continue
            circle = None
            if q in wanted:
                # the shot was taken for this dimension: the circle nearest the current estimate, else the most confident
                if d.target is not None:
                    circle = min(circles, key=lambda c: abs(c["d"] - d.target) / max(d.target, 1.0))
                    if abs(circle["d"] - d.target) / max(d.target, 1.0) > 0.35:
                        circle = max(circles, key=lambda c: c["conf"])
                else:
                    circle = max(circles, key=lambda c: c["conf"])
            elif d.target is not None:
                # an unlabelled photo: only an unambiguous match (exactly one circle within 15 % of the estimate)
                close = [c for c in circles if abs(c["d"] - d.target) / max(d.target, 1.0) <= 0.15]
                if len(close) == 1:
                    circle = close[0]
            if circle is None:
                continue
            # one sheet photo is strong evidence but not a confirmation: a second source (ruler, coupon, another shot) lifts it
            conf = round(min(0.88, 0.5 + 0.4 * float(circle.get("conf", 0.5))), 3)
            est = Estimate(value=round(float(circle["d"]), 2), source="rectified_sheet", conf=conf, photo=p["file"],
                           note=f"auto: {circle.get('method', '')}, {circle.get('n_points', 0)} edge points")
            spec.add_estimate(q, est)
            already.add((p["file"], q))
            applied.append({"dim": q, "value": est.value, "conf": conf, "photo": p["file"], "status": spec.get_dim(q).status})
            if emit:
                session.emit("estimate", dim=q, value=est.value, source="rectified_sheet", conf=conf, photo=p["file"], auto=True)
    if applied:
        spec.save(session.spec_path)
        session.commit("auto-measured " + ", ".join(sorted({a["dim"] for a in applied})))
    return applied


# ---- rounds ---------------------------------------------------------------------------------------------------

def evidence_snapshot(session: Session, spec: PartSpec | None = None) -> dict[str, Any]:
    spec = spec or session.spec()
    intake = load_intake(session)
    checks = None
    cp = session.dir / "checks.json"
    if cp.exists():
        try:
            checks = json.loads(cp.read_text())
        except json.JSONDecodeError:
            checks = None
    photos = [{"file": p["file"], "grade": p["grade"]} for p in session_photos(session)]
    g = E.build(spec, photos=photos, intake=intake, checks=checks, standards=intake.get("standards") or [])
    return g.to_dict()


def _photo_notes(session: Session, intake: dict[str, Any]) -> list[str]:
    notes = []
    targets = targets_by_label(intake)
    for p in session_photos(session):
        g = p.get("grade") or {}
        lab = _label_of(p["path"].name, intake)
        what = f"taken for {', '.join(targets[lab])}" if lab in targets else "context photo"
        state = "usable" if g.get("ok") else ("unusable: " + "; ".join((g.get("instructions") or ["poor capture"])[:2]) if g else "ungraded")
        notes.append(f"- {p['path'].name}: {what}; {state}; {g.get('markers_found', 0)} markers")
    return notes


async def refine_round_with_model(session: Session, spec: PartSpec, intake: dict[str, Any], plan: list[E.Request],
                                  missing: list[E.MissingDim], round_no: int, llm=None) -> tuple[list[E.Request], str]:
    """Ask the follow-up agent to rewrite the algorithmic plan for this object. Falls back to the plan on any problem."""
    from kintsugi.agent.llm import get_llm, image_part, text_part

    llm = llm or get_llm()
    ok, _ = llm.available()
    if not ok or llm.provider == "fake":
        return plan, ""
    dims_lines = []
    for q, d, is_itf in spec.all_dims():
        conf = E._conf_of(d)
        dims_lines.append(f"- {q} ({'interface' if is_itf else 'requirement'}): {d.describe()} status={d.status} conf={conf:.2f}"
                          + (f" recipe={d.measure.recipe}" if d.measure else "") + (f" feature={d.measure.feature}" if d.measure and d.measure.feature else ""))
    parts: list[dict[str, Any]] = [text_part(
        f"OBJECT: {intake.get('object') or spec.part.object or '?'}\nPART: {intake.get('part_role') or spec.part.role}\nDAMAGE: {intake.get('damage') or '?'}\n\n"
        f"ROUND {round_no} of at most {MAX_ROUNDS}.\n\nPHOTOS SO FAR:\n" + "\n".join(_photo_notes(session, intake) or ["- none"]) + "\n\nDIMENSIONS:\n" + "\n".join(dims_lines)
        + "\n\nMISSING:\n" + "\n".join(f"- {m.dim}: {m.reason} (conf {m.conf:.2f}, {m.importance})" for m in missing)
        + "\n\nALGORITHMIC PLAN:\n" + json.dumps([r.to_dict() for r in plan], indent=1) + "\n\nPHOTOS FOLLOW (most recent last).")]
    for p in session_photos(session)[-4:]:
        img = image_part(p["path"], max_side=1000, quality=72)
        if img:
            parts.append(text_part(f"photo: {p['path'].name}"))
            parts.append(img)
    parts.append(text_part("Produce the JSON now."))
    try:
        raw = await llm.complete(system=FOLLOWUP_PROMPT, parts=parts, json_mode=True, role="vision")
        data = json.loads(_json_only(raw))
    except Exception as e:  # noqa: BLE001
        session.emit("error", message=f"follow-up agent failed ({type(e).__name__}); using the algorithmic plan")
        return plan, ""
    reqs: list[E.Request] = []
    valid_dims = {q for q, _, _ in spec.all_dims()}
    for i, r in enumerate(data.get("requests") or []):
        if not isinstance(r, dict):
            continue
        kind = str(r.get("kind") or "photo")
        if kind not in ("photo", "measure", "choice", "coupon"):
            kind = "photo"
        dims = [str(d) for d in (r.get("dims") or []) if str(d) in valid_dims]
        if not dims and kind != "choice":
            continue
        rid = re.sub(r"[^a-zA-Z0-9_]+", "_", str(r.get("id") or f"r{round_no}_{i + 1}"))[:40] or f"r{round_no}_{i + 1}"
        try:
            pri = int(r.get("priority", 1))
        except (TypeError, ValueError):
            pri = 1
        req = E.Request(rid, kind, dims, str(r.get("title") or rid), str(r.get("instructions") or ""), str(r.get("why") or ""),
                        max(0, min(2, pri)), label=rid if kind == "photo" else None)
        if kind == "choice":
            req.__dict__["options"] = [str(o) for o in (r.get("options") or [])]
        reqs.append(req)
    if not reqs:
        return plan, str(data.get("note") or "")
    reqs.sort(key=lambda r: (r.priority, r.kind != "photo"))
    return reqs, str(data.get("note") or "")


def _json_only(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    i, j = raw.find("{"), raw.rfind("}")
    return raw[i:j + 1] if i >= 0 and j > i else raw


async def run_capture_round(session: Session, llm=None, *, measure: bool = True) -> dict[str, Any]:
    """Measure, build the evidence graph, and when the spec is not ready write the next round of requests."""
    t0 = time.time()
    spec = session.spec()
    intake = load_intake(session)
    applied = auto_measure(session, spec) if measure else []
    snap = evidence_snapshot(session, spec)
    rounds = intake.get("rounds") or []
    round_no = len(rounds) + 1
    result: dict[str, Any] = {"evidence": snap, "applied": applied, "round": None, "ready": snap["ready"], "readiness": snap["readiness"]}
    if snap["ready"] or round_no > MAX_ROUNDS:
        if not snap["ready"]:
            result["note"] = "No more capture rounds; design with the estimates and confirm the fit with the coupon."
        intake["capture_done"] = True
        save_intake(session, intake)
        session.update_meta(stage="spec")
        session.emit("capture_ready", ready=snap["ready"], readiness=snap["readiness"], rounds=len(rounds))
        return result
    missing = E.missing(spec)
    plan = E.plan_round(spec, missing, round_no=round_no)
    if round_no == 1:
        plan += intake_questions_as_requests(intake, plan)
    reqs, note = await refine_round_with_model(session, spec, intake, plan, missing, round_no, llm)
    if round_no == 1:
        # the agent may drop design-intent questions; keep the ones it did not carry over
        have = {r.id for r in reqs}
        reqs += [r for r in intake_questions_as_requests(intake, plan) if r.id not in have and r.kind in ("choice", "text")]
    rnd = {"n": round_no, "t": time.time(), "requests": [r.to_dict() for r in reqs], "note": note,
           "missing": [m.to_dict() for m in missing], "duration_s": round(time.time() - t0, 1)}
    rounds.append(rnd)
    intake["rounds"] = rounds
    save_intake(session, intake)
    session.update_meta(stage="capture")
    session.commit(f"capture round {round_no}")
    session.emit("capture_round", n=round_no, requests=rnd["requests"], note=note, missing=[m.dim for m in missing])
    result["round"] = rnd
    return result


def intake_questions_as_requests(intake: dict[str, Any], plan: list[E.Request]) -> list[E.Request]:
    """Intake's own questions that the algorithmic plan does not already cover (design-intent choices, free text)."""
    covered = {d for r in plan for d in r.dims}
    out: list[E.Request] = []
    for i, q in enumerate(intake.get("questions") or []):
        if not isinstance(q, dict) or not q.get("text"):
            continue
        kind = str(q.get("kind") or "text")
        dim = q.get("dim")
        if dim and dim in covered:
            continue  # a photo or ruler request already targets it
        rid = re.sub(r"[^a-zA-Z0-9_]+", "_", str(q.get("id") or f"q{i + 1}"))
        if kind == "number" and dim:
            out.append(E.Request(rid, "measure", [str(dim)], str(q["text"]), "Read it with a ruler or caliper, in mm.", "the intake engineer asked for it", 1))
        elif kind == "choice":
            r = E.Request(rid, "choice", [str(dim)] if dim else [], str(q["text"]), "", "shapes the design", 1)
            r.__dict__["options"] = [str(o) for o in (q.get("options") or [])]
            out.append(r)
        else:
            out.append(E.Request(rid, "text", [str(dim)] if dim else [], str(q["text"]), "", "shapes the design", 2))
    return out


def apply_measure_answers(session: Session, spec: PartSpec, answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ruler readings from a capture round: numbers confirm dimensions."""
    applied = []
    for a in answers:
        dim = a.get("dim")
        val = a.get("value")
        if not dim or val in (None, ""):
            continue
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        if spec.get_dim(dim) is None:
            continue
        spec.confirm(dim, v, source=str(a.get("source") or "user_ruler"))
        applied.append({"dim": dim, "value": v})
        session.emit("dim_confirmed", dim=dim, value=v, source=str(a.get("source") or "user_ruler"))
    if applied:
        spec.save(session.spec_path)
        session.commit("ruler readings: " + ", ".join(a["dim"] for a in applied))
    return applied
