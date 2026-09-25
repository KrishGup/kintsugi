"""Parse OpenSCAD customizer annotations into a parameter list the UI can render as sliders.

Supported forms (same rules as OpenSCAD's customizer):
    /* [Section name] */
    // description on the line before
    name = 10;            // [0:0.5:50]      slider with step
    name = 10;            // [0:50]          slider, integer step
    name = "a";           // [a, b, c]       dropdown
    name = "a";           // [a:Alpha, b:Beta]  dropdown with labels
    name = true;          //                 checkbox
    name = [1, 2, 3];     //                 vector
Parsing stops at the first module/function definition or a /* [Hidden] */ section.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

_SECTION_RE = re.compile(r"^\s*/\*\s*\[(.*?)\]\s*\*/\s*$")
_DESC_RE = re.compile(r"^\s*//\s*(.*)$")
_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_$]*)\s*=\s*(.*?);\s*(?://\s*(.*))?$")
_STOP_RE = re.compile(r"^\s*(module|function)\s+[A-Za-z_]")
_RANGE_RE = re.compile(r"^\[\s*(-?[\d.]+)\s*:\s*(-?[\d.]+)\s*(?::\s*(-?[\d.]+)\s*)?\]$")
_LIST_RE = re.compile(r"^\[(.*)\]$")


@dataclass
class Param:
    name: str
    value: Any
    type: str  # number | string | bool | vector
    section: str = "Parameters"
    description: str = ""
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[dict[str, Any]] = field(default_factory=list)  # [{value, label}]
    raw_value: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_value(raw: str) -> tuple[Any, str]:
    raw = raw.strip()
    if raw in ("true", "false"):
        return raw == "true", "bool"
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1], "string"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw), "number"
    if re.fullmatch(r"-?(\d+\.\d*|\.\d+|\d+)([eE]-?\d+)?", raw):
        return float(raw), "number"
    if raw.startswith("[") and raw.endswith("]"):
        try:
            return json.loads(raw), "vector"
        except json.JSONDecodeError:
            return raw, "vector"
    return raw, "expression"


def _parse_annotation(ann: str, p: Param) -> None:
    ann = ann.strip()
    m = _RANGE_RE.match(ann)
    if m and p.type == "number":
        a, b, c = m.group(1), m.group(2), m.group(3)
        if c is None:
            p.min, p.max = float(a), float(b)
            p.step = 1.0 if isinstance(p.value, int) else 0.1
        else:
            p.min, p.step, p.max = float(a), float(b), float(c)
        return
    m = _LIST_RE.match(ann)
    if m:
        items = [s.strip() for s in m.group(1).split(",") if s.strip()]
        opts = []
        for it in items:
            if ":" in it and p.type in ("string", "number"):
                v, label = it.split(":", 1)
                v = v.strip().strip('"')
                opts.append({"value": _coerce_like(v, p.value), "label": label.strip()})
            else:
                v = it.strip().strip('"')
                opts.append({"value": _coerce_like(v, p.value), "label": v})
        if opts:
            p.options = opts
        return
    if re.fullmatch(r"\d+", ann) and p.type == "string":
        # max length hint; ignore
        return


def _coerce_like(v: str, like: Any) -> Any:
    if isinstance(like, bool):
        return v == "true"
    if isinstance(like, int):
        try:
            return int(v)
        except ValueError:
            return v
    if isinstance(like, float):
        try:
            return float(v)
        except ValueError:
            return v
    return v


def parse_customizer(source: str) -> list[Param]:
    params: list[Param] = []
    section = "Parameters"
    pending_desc: list[str] = []
    hidden = False
    for line in source.splitlines():
        if _STOP_RE.match(line):
            break
        m = _SECTION_RE.match(line)
        if m:
            section = m.group(1).strip()
            hidden = section.lower() == "hidden"
            pending_desc = []
            continue
        m = _ASSIGN_RE.match(line)
        if m:
            name, raw, ann = m.group(1), m.group(2), m.group(3)
            if hidden or name.startswith("$"):
                pending_desc = []
                continue
            value, vtype = _parse_value(raw)
            if vtype == "expression":
                pending_desc = []
                continue  # derived value, not a customizer input
            p = Param(name=name, value=value, type=vtype, section=section,
                      description=" ".join(pending_desc).strip(), raw_value=raw.strip())
            if ann:
                _parse_annotation(ann, p)
            params.append(p)
            pending_desc = []
            continue
        m = _DESC_RE.match(line)
        if m:
            text = m.group(1).strip()
            if text and not text.startswith("["):
                pending_desc.append(text)
            continue
        if line.strip() == "":
            pending_desc = []
    return params


def set_param_values(source: str, values: dict[str, Any]) -> str:
    """Rewrite top-level parameter assignments in the parameter block with new values.

    Keeps annotations and comments intact. Only rewrites names present in `values`.
    """
    from kintsugi.scad.compile import format_define

    out = []
    stopped = False
    for line in source.splitlines():
        if not stopped and _STOP_RE.match(line):
            stopped = True
        if not stopped:
            m = _ASSIGN_RE.match(line)
            if m and m.group(1) in values:
                name, ann = m.group(1), m.group(3)
                new = f"{name} = {format_define(values[name])};"
                if ann is not None:
                    # preserve original spacing before the comment where possible
                    idx = line.find("//")
                    pad = max(1, idx - len(new)) if idx > 0 else 1
                    new = new + " " * pad + "// " + ann
                indent = line[: len(line) - len(line.lstrip())]
                out.append(indent + new)
                continue
        out.append(line)
    return "\n".join(out) + ("\n" if source.endswith("\n") else "")
