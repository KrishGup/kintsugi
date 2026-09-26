"""The code-blind critic: a fresh-context model call that sees drawings and numbers, never the CAD code."""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kintsugi import PACKAGE_DIR
from kintsugi.checks.run import CheckReport
from kintsugi.spec.model import PartSpec

CRITIC_PROMPT = (PACKAGE_DIR / "agent" / "prompts" / "critic.md").read_text(encoding="utf-8")


@dataclass
class CriticVerdict:
    verdict: str  # pass | revise | ask_user | error
    summary: str = ""
    discrepancies: list[dict[str, Any]] = field(default_factory=list)
    question_for_user: str | None = None
    raw: str = ""
    model: str | None = None
    duration_s: float = 0.0
    inspection: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"

    def to_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "summary": self.summary, "discrepancies": self.discrepancies,
                "question_for_user": self.question_for_user, "model": self.model, "duration_s": round(self.duration_s, 1),
                "inspection": self.inspection}

    def summary_for_model(self) -> str:
        lines = [f"CRITIC VERDICT: {self.verdict.upper()} — {self.summary}"]
        for d in self.discrepancies:
            lines.append(f"  [{d.get('severity','?')}] {d.get('where','')}: expected {d.get('expected','')}; observed {d.get('observed','')}. "
                         f"Suggestion: {d.get('suggestion','')}")
        if self.question_for_user:
            lines.append(f"  question for user: {self.question_for_user}")
        return "\n".join(lines)


def _image_block(path: Path, max_side: int = 1600) -> dict[str, Any] | None:
    """Agent-SDK-shaped image block (kept for the Agent runtime)."""
    from kintsugi.agent.llm import image_part
    p = image_part(path, max_side=max_side)
    if not p:
        return None
    return {"type": "image", "source": {"type": "base64", "media_type": p["mime"], "data": base64.b64encode(p["data"]).decode()}}


def detail_views(sheets: list[Path]) -> list[Path]:
    """Higher-resolution single views that accompany the composed sheets: the top view and the first section."""
    out: list[Path] = []
    for p in sheets:
        vd = p.parent / "views"
        if not vd.exists():
            continue
        stem = p.stem.rsplit("_", 1)[0]  # iter_04
        for name in (f"{stem}_top_detail.png", f"{stem}_section_A.png", f"{stem}_front_detail.png"):
            q = vd / name
            if q.exists() and q not in out:
                out.append(q)
        break
    return out


def build_critic_parts(spec: PartSpec, report: CheckReport | None, sheets: list[Path], prev_sheets: list[Path] | None = None,
                       photos: list[Path] | None = None, extra_context: str = "") -> list[dict[str, Any]]:
    """Provider-neutral parts: text + images (see kintsugi.agent.llm)."""
    from kintsugi.agent.llm import image_part, text_part

    parts: list[dict[str, Any]] = []
    text = ["PART SPEC:", spec.summary_for_model(), ""]
    if report:
        text += ["CHECK TABLE (measured on the exported mesh; covers only the dimensions listed in the spec):", report.summary_for_model(), ""]
    if extra_context:
        text += [extra_context, ""]
    parts.append(text_part("\n".join(text)))
    for i, p in enumerate(sheets):
        img = image_part(p)
        if img:
            parts.append(text_part(f"CURRENT ITERATION — sheet {i+1}: {p.name}"))
            parts.append(img)
    for p in detail_views(sheets):
        img = image_part(p, max_side=1600)
        if img:
            parts.append(text_part(f"CURRENT ITERATION — detail view at full resolution: {p.name}"))
            parts.append(img)
    for i, p in enumerate(prev_sheets or []):
        img = image_part(p, max_side=1000)
        if img:
            parts.append(text_part(f"PREVIOUS ITERATION — sheet {i+1}: {p.name}"))
            parts.append(img)
    for p in photos or []:
        img = image_part(p, max_side=1200)
        if img:
            parts.append(text_part(f"REFERENCE PHOTO: {p.name}"))
            parts.append(img)
    parts.append(text_part("Review now. Respond with the JSON object only."))
    return parts


def parse_verdict(text: str) -> CriticVerdict:
    raw = text.strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return CriticVerdict("error", summary="critic returned no JSON", raw=raw)
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        # try to trim trailing junk
        try:
            d = json.loads(m.group(0).rsplit("}", 1)[0] + "}")
        except Exception:
            return CriticVerdict("error", summary="critic JSON unparsable", raw=raw)
    v = str(d.get("verdict", "error")).lower()
    if v not in ("pass", "revise", "ask_user"):
        v = "error"
    disc = list(d.get("discrepancies") or [])
    # a medium/high discrepancy means revise, whatever the verdict field says
    if v == "pass" and any(str(x.get("severity", "")).lower() in ("high", "medium") for x in disc):
        v = "revise"
    verdict = CriticVerdict(v, summary=str(d.get("summary", "")), discrepancies=disc,
                            question_for_user=d.get("question_for_user"), raw=raw)
    verdict.inspection = d.get("inspection") or {}
    return verdict


async def critique(spec: PartSpec, report: CheckReport | None, sheets: list[Path], *, prev_sheets: list[Path] | None = None,
                   photos: list[Path] | None = None, model: str | None = None, extra_context: str = "", cwd: Path | None = None,
                   llm=None) -> CriticVerdict:
    """Run the critic: one fresh-context model call with the spec, the check table and the drawings (never the code)."""
    from kintsugi.agent.llm import get_llm

    llm = llm or get_llm()
    model = model or llm.models["critic"]
    parts = build_critic_parts(spec, report, sheets, prev_sheets, photos, extra_context)
    t0 = time.time()
    try:
        text = await llm.complete(system=CRITIC_PROMPT, parts=parts, model=model, json_mode=True, role="critic")
    except Exception as e:
        v = CriticVerdict("error", summary=f"critic call failed: {type(e).__name__}: {str(e)[:200]}")
        v.model = model
        v.duration_s = time.time() - t0
        return v
    v = parse_verdict(text)
    v.model = model
    v.duration_s = time.time() - t0
    return v
