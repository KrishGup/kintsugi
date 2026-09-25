"""Intake: photos + a sentence -> what broke, a draft Part Spec, a capture plan and batched questions."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from kintsugi import PACKAGE_DIR
from kintsugi.agent.critic import _image_block
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


async def run_intake(session: Session, text: str, photos: list[Path], model: str | None = None) -> dict[str, Any]:
    from agent_sdk import AssistantMessage, AgentOptions, SDKClient, TextBlock

    model = model or os.environ.get("KIN_VISION_MODEL", "opus")
    content: list[dict[str, Any]] = [{"type": "text", "text": f"USER SAYS: {text or '(no description)'}\n\nPHOTOS FOLLOW."}]
    for p in photos[:6]:
        blk = _image_block(p, max_side=1400)
        if blk:
            content.append({"type": "text", "text": f"photo: {p.name}"})
            content.append(blk)
    content.append({"type": "text", "text": "Produce the JSON now."})
    options = AgentOptions(system_prompt=INTAKE_PROMPT, model=model, allowed_tools=[], max_turns=1, setting_sources=[],
                                 disallowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch", "Task", "TodoWrite"],
                                 permission_mode="dontAsk", cwd=str(session.dir))
    out: list[str] = []
    t0 = time.time()

    async def gen():
        yield {"type": "user", "message": {"role": "user", "content": content}, "parent_tool_use_id": None, "session_id": "intake"}

    async with SDKClient(options) as client:
        await client.query(gen(), session_id="intake")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for b in msg.content:
                    if isinstance(b, TextBlock):
                        out.append(b.text)
    data = parse_intake("\n".join(out))
    # validate the spec part
    spec_data = sanitize_spec_data(data.get("spec") or {})
    try:
        spec = PartSpec.model_validate(spec_data)
    except Exception as e:
        data["spec_error"] = str(e)
        try:
            spec = PartSpec.model_validate({"part": spec_data.get("part", {}), "print": spec_data.get("print", {})})
        except Exception:
            spec = PartSpec()
    if not spec.part.name or spec.part.name == "part":
        words = re.sub(r"[^a-z0-9 ]+", " ", str(data.get("object") or session.meta.get("name") or "part").lower()).split()
        spec.part.name = "_".join(words[:3]) or "part"
    spec.save(session.spec_path)
    (session.dir / "intake.json").write_text(json.dumps(data, indent=2))
    session.update_meta(status="intake_done", name=spec.part.name)
    session.commit("intake: draft spec")
    session.emit("intake", object=data.get("object"), part_role=data.get("part_role"), questions=data.get("questions", []),
                 capture_plan=data.get("capture_plan", []), duration_s=round(time.time() - t0, 1))
    data["spec_yaml"] = spec.to_yaml()
    return data
