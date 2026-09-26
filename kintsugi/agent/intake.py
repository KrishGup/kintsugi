"""Intake: photos + a sentence -> what broke, a draft Part Spec, a capture plan and batched questions."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from kintsugi import PACKAGE_DIR
from kintsugi.session.workspace import Session
from kintsugi.spec.model import PartSpec

INTAKE_PROMPT = (PACKAGE_DIR / "agent" / "prompts" / "intake.md").read_text(encoding="utf-8")


def parse_intake(text: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", text.strip(), re.S)
    if not m:
        raise ValueError("intake returned no JSON")
    return json.loads(m.group(0))


_FITS = ("press", "sliding", "loose", "snap", "none")
_TYPES = ("cylindrical_bore", "cylindrical_boss", "slot", "plate", "hole_pattern", "snap", "thread", "custom")
_RECIPES = ("circle_fit_inner", "circle_fit_outer", "extent", "hole_extent", "section_extent", "hole_positions", "wall_min",
            "bbox", "notch_circle", "notch_mouth", "gap", "none")


def _coerce_fit(v: Any) -> tuple[str, str | None]:
    s = str(v or "").lower()
    if s in _FITS:
        return s, None
    for key, fit in (("press", "press"), ("interference", "press"), ("snap", "snap"), ("loose", "loose"), ("slip", "loose"),
                     ("free", "loose"), ("slid", "sliding"), ("clearance", "sliding"), ("none", "none"), ("no fit", "none")):
        if key in s:
            return fit, str(v)
    return "sliding", str(v) if v else None


def _sanitize_measure(m: Any) -> Any:
    if not isinstance(m, dict):
        return None
    m = dict(m)
    if m.get("recipe") not in _RECIPES:
        r = str(m.get("recipe", "")).lower()
        m["recipe"] = next((x for x in _RECIPES if x in r), "none")
    if "region" in m and not (isinstance(m["region"], list) and len(m["region"]) == 2 and all(isinstance(c, list) and len(c) == 3 for c in m["region"])):
        m["feature"] = (str(m.get("feature") or "") + f" (region {m['region']})").strip()
        m.pop("region")
    if "near" in m and not (isinstance(m["near"], list) and len(m["near"]) == 2):
        m.pop("near")
    if "expect" in m and not isinstance(m["expect"], list):
        m.pop("expect")
    for k in ("at_z",):
        if k in m and m[k] is not None:
            try:
                m[k] = float(m[k])
            except (TypeError, ValueError):
                m.pop(k)
    return m


def _sanitize_dim(d: Any) -> Any:
    if not isinstance(d, dict):
        return {"note": str(d)}
    d = dict(d)
    for k in ("target", "tol", "min", "max"):
        if k in d and d[k] is not None:
            try:
                d[k] = float(d[k])
            except (TypeError, ValueError):
                d[k] = None
    if d.get("status") not in ("unknown", "estimated", "confirmed"):
        d["status"] = "estimated" if d.get("target") is not None else "unknown"
    if "measure" in d:
        d["measure"] = _sanitize_measure(d["measure"])
        if d["measure"] is None:
            d.pop("measure")
    ests = []
    for e in d.get("estimates") or []:
        if isinstance(e, dict) and "value" in e:
            try:
                ests.append({"value": float(e["value"]), "source": str(e.get("source") or "vision_estimate"),
                             "conf": float(e.get("conf", 0.3)), "note": e.get("note")})
            except (TypeError, ValueError):
                continue
    d["estimates"] = ests
    return d


def sanitize_spec_data(data: dict[str, Any]) -> dict[str, Any]:
    """Coerce a model-written spec into the strict schema (free-text enums, named regions, stray fields)."""
    out = dict(data or {})
    part = dict(out.get("part") or {})
    name = re.sub(r"[^a-z0-9]+", "_", str(part.get("name") or "part").lower()).strip("_")[:40] or "part"
    part["name"] = name
    out["part"] = {k: v for k, v in part.items() if k in ("name", "role", "object", "design_intent", "notes")}
    itfs = []
    for itf in out.get("interfaces") or []:
        if not isinstance(itf, dict):
            continue
        itf = dict(itf)
        fit, note = _coerce_fit(itf.get("fit"))
        itf["fit"] = fit
        if note:
            itf["note"] = ((itf.get("note") or "") + " fit: " + note).strip()
        if itf.get("type") not in _TYPES:
            t = str(itf.get("type", "")).lower()
            itf["type"] = next((x for x in _TYPES if x in t), "custom")
        if itf.get("side") not in ("male", "female", None):
            itf.pop("side")
        if itf.get("clearance") is not None:
            try:
                itf["clearance"] = float(itf["clearance"])
            except (TypeError, ValueError):
                itf["clearance"] = None
        itf["dims"] = {str(k): _sanitize_dim(v) for k, v in (itf.get("dims") or {}).items()}
        itf["id"] = re.sub(r"[^a-z0-9_]+", "_", str(itf.get("id") or f"interface_{len(itfs)+1}").lower())
        itfs.append(itf)
    out["interfaces"] = itfs
    reqs = []
    for r in out.get("requirements") or []:
        if not isinstance(r, dict):
            continue
        r = dict(r)
        r["id"] = re.sub(r"[^a-z0-9_]+", "_", str(r.get("id") or f"req_{len(reqs)+1}").lower())
        r["text"] = str(r.get("text") or "")
        r["derived"] = {str(k): _sanitize_dim(v) for k, v in (r.get("derived") or {}).items()}
        reqs.append(r)
    out["requirements"] = reqs
    ctx = []
    for c in out.get("context") or []:
        if not isinstance(c, dict) or c.get("shape") not in ("cylinder", "cone", "box", "sphere", "tube"):
            continue
        c = dict(c)
        c["id"] = re.sub(r"[^a-z0-9_]+", "_", str(c.get("id") or f"ctx_{len(ctx)+1}").lower())
        at = c.get("at")
        if not (isinstance(at, list) and len(at) == 3):
            c["at"] = [0.0, 0.0, 0.0]
        ctx.append(c)
    out["context"] = ctx
    if not isinstance(out.get("print"), dict):
        out["print"] = {}
    oq = out.get("open_questions") or []
    out["open_questions"] = [str(q) for q in oq if q]
    return out


async def intake_call(llm, text: str, photos: list[Path], hints: str = "", model: str | None = None) -> dict[str, Any]:
    """The one vision call: photos + sentence (+ known-standard hints) -> intake JSON (parsed, spec sanitized, not saved)."""
    from kintsugi.agent.llm import image_part, text_part

    model = model or llm.models["vision"]
    head = f"USER SAYS: {text or '(no description)'}"
    if hints:
        head += "\n\n" + hints
    parts: list[dict[str, Any]] = [text_part(head + "\n\nPHOTOS FOLLOW.")]
    for p in photos[:6]:
        img = image_part(p, max_side=1400)
        if img:
            parts.append(text_part(f"photo: {p.name}"))
            parts.append(img)
    parts.append(text_part("Produce the JSON now."))
    raw = await llm.complete(system=INTAKE_PROMPT, parts=parts, model=model, json_mode=True, role="vision")
    data = parse_intake(raw)
    data["spec_data"] = sanitize_spec_data(data.get("spec") or {})
    return data


def spec_from_intake(data: dict[str, Any], fallback_name: str = "part") -> PartSpec:
    spec_data = data.get("spec_data") or sanitize_spec_data(data.get("spec") or {})
    try:
        spec = PartSpec.model_validate(spec_data)
    except Exception as e:
        data["spec_error"] = str(e)
        try:
            spec = PartSpec.model_validate({"part": spec_data.get("part", {}), "print": spec_data.get("print", {})})
        except Exception:
            spec = PartSpec()
    if not spec.part.name or spec.part.name == "part":
        words = re.sub(r"[^a-z0-9 ]+", " ", str(data.get("object") or fallback_name or "part").lower()).split()
        spec.part.name = "_".join(words[:3]) or "part"
    return spec


def attach_standard_estimates(spec: PartSpec, standards: list[Any]) -> list[dict[str, Any]]:
    """Catalogue values for recognised standards become medium-confidence estimates on the matching mating dimensions."""
    from kintsugi.spec.model import Estimate

    applied = []
    for std in standards:
        for role, value in std.dims.items():
            spec_name = std.roles.get(role)
            if not spec_name:
                continue
            for q, d, is_itf in spec.all_dims():
                if not is_itf or q.split(".")[-1] != spec_name or d.status == "confirmed":
                    continue
                if any(e.source == f"standard:{std.id}" for e in d.estimates):
                    continue
                if d.target is not None and abs(d.target - value) / max(abs(value), 1.0) > 0.15:
                    continue  # the photos say something quite different; do not muddy the evidence
                spec.add_estimate(q, Estimate(value=float(value), source=f"standard:{std.id}", conf=std.conf, note=std.name))
                applied.append({"dim": q, "value": float(value), "standard": std.id})
    return applied


async def run_intake(session: Session, text: str, photos: list[Path], model: str | None = None, llm=None) -> dict[str, Any]:
    """Photos + a sentence -> draft spec, capture plan, questions; then measure, evidence, and the first capture round.

    Runs as the intake graph: grade ∥ standards → vision → standards on the object → auto-measure → evidence → follow-up → capture.
    """
    from kintsugi.agent import capture as C
    from kintsugi.agent.llm import get_llm
    from kintsugi.graph.core import Graph, Node
    from kintsugi.spec.standards import hints_for_model, match_standards

    llm = llm or get_llm()
    model = model or llm.models["vision"]
    t0 = time.time()

    def n_grade(s):
        from kintsugi.measure.grade import grade_capture
        import cv2
        import numpy as np
        graded = 0
        for p in s["photos"]:
            g = p.with_suffix(p.suffix + ".grade.json")
            if g.exists():
                continue
            img = cv2.imread(str(p))
            if img is None:
                continue
            try:
                gr = grade_capture(img, expect_sheet=True)
                d = {k: (float(v) if isinstance(v, np.floating) else v) for k, v in gr.__dict__.items() if not k.startswith("_")}
                g.write_text(json.dumps(d, default=lambda o: float(o) if hasattr(o, "__float__") else str(o)))
                graded += 1
            except Exception:
                continue
        return {"graded": graded}

    def n_standards_pre(s):
        matches = match_standards(s["text"] + " " + str(session.meta.get("name") or ""))
        return {"hints": hints_for_model(matches), "standards_pre": matches}

    async def n_vision(s):
        data = await intake_call(llm, s["text"], s["photos"], s.get("hints", ""), model)
        return {"intake": data}

    def n_spec(s):
        data = s["intake"]
        spec = spec_from_intake(data, str(session.meta.get("name") or "part"))
        matches = list(s.get("standards_pre") or [])
        for m in match_standards(" ".join(str(data.get(k) or "") for k in ("object", "part_role", "interfaces_reasoning"))):
            if m.id not in {x.id for x in matches}:
                matches.append(m)
        std_applied = attach_standard_estimates(spec, matches)
        spec.save(session.spec_path)
        data["standards"] = [m.to_dict() for m in matches]
        data["standard_estimates"] = std_applied
        data.pop("spec_data", None)
        C.save_intake(session, data)
        cur = str(session.meta.get("name") or "")
        new_name = cur if cur and cur not in ("part", "session") and not cur.startswith("part_") else spec.part.name
        session.update_meta(status="intake_done", name=new_name, stage="capture")
        session.commit("intake: draft spec")
        session.emit("intake", object=data.get("object"), part_role=data.get("part_role"), damage=data.get("damage"),
                     questions=data.get("questions", []), capture_plan=data.get("capture_plan", []),
                     standards=[m.id for m in matches], duration_s=round(time.time() - t0, 1))
        return {"spec": spec, "standards": matches}

    def n_measure(s):
        return {"measured": C.auto_measure(session, s["spec"])}

    def n_evidence(s):
        snap = C.evidence_snapshot(session, s["spec"])
        return {"evidence": snap, "ready": snap["ready"]}

    async def n_followup(s):
        res = await C.run_capture_round(session, llm, measure=False)
        return {"round": res.get("round") or {}, "capture": res}

    def ask(s):
        rnd = s.get("round") or {}
        return {"requests": rnd.get("requests", []), "note": rnd.get("note", ""), "round": rnd.get("n")}

    g = Graph("intake", [
        Node("grade", n_grade, ("photos",), ("graded",), label="grade photos", est_s=1.0, optional=True),
        Node("standards", n_standards_pre, ("text",), ("hints", "standards_pre"), label="known standards", est_s=0.01, optional=True),
        Node("vision", n_vision, ("text", "photos"), ("intake",), kind="agent", label="intake (vision model)", est_s=40.0, blocking=False, after=("standards", "grade")),
        Node("spec", n_spec, ("intake",), ("spec", "standards"), label="draft spec + standards", est_s=0.2),
        Node("measure", n_measure, ("spec",), ("measured",), label="auto-measure sheet photos", est_s=2.0, optional=True),
        Node("evidence", n_evidence, ("spec",), ("evidence", "ready"), label="evidence graph", est_s=0.05, after=("measure",)),
        Node("followup", n_followup, ("evidence",), ("round",), kind="agent", label="follow-up round", est_s=20.0, blocking=False,
             when=lambda s: not s.get("ready")),
        Node("capture", None, ("round",), ("captured",), kind="human", label="user takes photos / reads ruler", ask=ask),
    ])
    state: dict[str, Any] = {"text": text, "photos": list(photos)}
    trace = await g.run(state, emit=lambda kind, **d: session.emit(kind, **d))
    (session.dir / "intake_graph.json").write_text(json.dumps(trace.to_dict(), indent=2))
    if "intake" not in state:
        err = trace.nodes["vision"].error or "intake failed"
        raise RuntimeError(err)
    data = dict(state["intake"])
    spec = state["spec"]
    if state.get("ready"):
        session.update_meta(stage="spec")
    data["spec_yaml"] = spec.to_yaml()
    data["spec"] = spec.model_dump(mode="json", exclude_none=True)
    data["evidence"] = state.get("evidence")
    data["round"] = state.get("round")
    data["measured"] = state.get("measured", [])
    data["graph"] = trace.to_dict()
    return data
