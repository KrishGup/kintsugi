"""Parse OpenSCAD customizer annotations into a parameter model the UI renders as a parametric designer.

Supported forms (a superset of OpenSCAD's customizer rules):
    /* [Section name] */
    // description on the line before
    name = 10;            // [0:0.5:50]  description after the range     slider with step
    name = 10;            // [0:50]                                       slider, integer step
    name = "a";           // [a, b, c]                                    choice
    name = "a";           // [a:Alpha, b:Beta]                            choice with labels
    name = true;          // description                                  toggle
    name = [1, 2, 3];     //                                              vector
Parsing stops at the first module/function definition; a /* [Hidden] */ section hides what follows.

On top of OpenSCAD's rules the model carries what a parametric designer needs:
  * a unit and a kind per parameter (length in mm, angle, count, ratio, clearance…), from the name or a "(unit)" in the description
  * a human label ("loop_inner_w" -> "Loop inner width")
  * gating: `feature = true;` followed by `feature_*` parameters (or "(when feature)" in a description) nests them under the toggle
  * bindings to the spec: a `// Spec dims: neck_ring.inner_diameter <- neck_id` header, else name/value matching
  * derived values (`bore = neck_id + clearance;`) with their formulas, top-level asserts with their messages, echoed names
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
_BRACKET_RE = re.compile(r"\[[^\[\]]*\]")
_UNIT_IN_DESC_RE = re.compile(r"\((mm|cm|m|in|inch|inches|deg|degrees|°|kg|g|N|MPa|GPa|%|percent|count|x|×|s|ms|mm/s)\)", re.I)
_WHEN_RE = re.compile(r"\(\s*(?:when|if|with|requires)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\)", re.I)
_SPEC_DIMS_RE = re.compile(r"^\s*//.*?\bSpec dims?\s*:\s*(.*)$", re.I)
_BINDING_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\s*<-\s*([A-Za-z_][A-Za-z0-9_]*)")
_ASSERT_RE = re.compile(r"^\s*assert\s*\((.*)\)\s*;\s*$")
_ECHO_RE = re.compile(r"^\s*echo\s*\((.*)\)\s*;\s*$")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

UNIT_WORDS = {
    "mm": "mm", "cm": "cm", "m": "m", "in": "in", "inch": "in", "inches": "in",
    "deg": "°", "degrees": "°", "°": "°", "kg": "kg", "g": "g", "n": "N", "mpa": "MPa", "gpa": "GPa",
    "%": "%", "percent": "%", "count": "", "x": "×", "×": "×", "s": "s", "ms": "ms", "mm/s": "mm/s",
}
# name fragments -> (unit, kind); checked in order, first match wins
_NAME_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"(^|_)(mpa)$"), "MPa", "stress"),
    (re.compile(r"(^|_)(gpa)$"), "GPa", "stress"),
    (re.compile(r"(^|_)(kg)$"), "kg", "mass"),
    (re.compile(r"(^|_)(deg|angle|ang|tilt|taper|rot|rotation|twist|draft)($|_)"), "°", "angle"),
    (re.compile(r"(^|_)(pct|percent)$"), "%", "ratio"),
    (re.compile(r"(^|_)(n|num|count|qty|teeth|segs|segments|sides|flutes|ribs|holes|slots|fingers|turns|starts|copies)$|^(n|num)_"), "", "count"),
    (re.compile(r"(^|_)(factor|ratio|strain|scale|fraction|gain)($|_)"), "×", "ratio"),
    (re.compile(r"clearance|slop|gap|tolerance|tol$|play"), "mm", "clearance"),
    (re.compile(r"(^|_)(fn|fs|fa)$"), "", "facets"),
]
_ABBREV = {
    "w": "width", "h": "height", "t": "thickness", "d": "diameter", "r": "radius", "l": "length", "len": "length",
    "id": "ID", "od": "OD", "n": "count", "num": "count", "z": "Z", "x": "X", "y": "Y", "cx": "centre X", "cy": "centre Y",
    "mpa": "(MPa)", "kg": "(kg)", "pct": "%", "deg": "°", "min": "min", "max": "max", "dia": "diameter", "thk": "thickness",
    "cs": "countersink", "cb": "counterbore", "fn": "facets", "ang": "angle", "rad": "radius", "tol": "tolerance", "pos": "position",
    "fillet": "fillet", "chamfer": "chamfer", "thick": "thickness", "spc": "spacing", "ht": "height", "wd": "width",
}
_MATING_KEYS = ("inner_diameter", "outer_diameter", "bore", "width", "height", "diameter", "thickness", "length", "spacing",
                "across_flats", "pitch", "depth", "od", "id")


@dataclass
class Binding:
    """A parameter's link to a dimension in the spec."""
    dim: str                       # e.g. neck_ring.inner_diameter
    how: str                       # explicit | name | value | name+value
    role: str = "interface"        # interface | requirement
    target: float | None = None
    tol: float | None = None
    min: float | None = None
    max: float | None = None
    status: str = "unknown"
    clearance: float | None = None  # the interface's fit clearance (interface dims only)
    fit: str | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)   # the estimates behind the value
    feature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    unit: str = ""
    kind: str = "number"           # length | angle | count | ratio | clearance | stress | mass | facets | toggle | choice | text | vector | number
    label: str = ""
    gate: str | None = None        # name of the boolean parameter this one depends on
    binding: Binding | None = None
    order: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["binding"] = self.binding.to_dict() if self.binding else None
        return d


@dataclass
class Derived:
    name: str
    expr: str
    value: Any = None
    echoed: bool = False
    binding: dict[str, Any] | None = None   # {dim, role, min, max, target, tol} when the name matches a spec dimension

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Assertion:
    cond: str
    message: str
    params: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------------------------------------------------
# parsing

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


def _split_annotation(ann: str) -> tuple[str | None, str]:
    """'[0:0.5:20]  straight bridge' -> ('[0:0.5:20]', 'straight bridge'); 'text [a, b]' -> ('[a, b]', 'text')."""
    ann = ann.strip()
    m = _BRACKET_RE.search(ann)
    if not m:
        return None, ann
    bracket = m.group(0)
    rest = (ann[: m.start()] + " " + ann[m.end():]).strip()
    rest = re.sub(r"\s{2,}", " ", rest).strip(" -–—:")
    return bracket, rest


def _parse_bracket(bracket: str, p: Param) -> bool:
    m = _RANGE_RE.match(bracket)
    if m and p.type == "number":
        a, b, c = m.group(1), m.group(2), m.group(3)
        if c is None:
            p.min, p.max = float(a), float(b)
            p.step = 1.0 if isinstance(p.value, int) else 0.1
        else:
            p.min, p.step, p.max = float(a), float(b), float(c)
        if p.min is not None and p.max is not None and p.min > p.max:
            p.min, p.max = p.max, p.min
        return True
    if re.fullmatch(r"\[\s*\d+\s*\]", bracket) and p.type == "string":
        return True  # max length hint; ignore
    m = _LIST_RE.match(bracket)
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
            return True
    return False


def _coerce_like(v: str, like: Any) -> Any:
    if isinstance(like, bool):
        return v == "true"
    if isinstance(like, int):
        try:
            return int(v)
        except ValueError:
            try:
                return float(v)
            except ValueError:
                return v
    if isinstance(like, float):
        try:
            return float(v)
        except ValueError:
            return v
    return v


def humanize(name: str) -> str:
    """loop_inner_w -> 'Loop inner width'; neck_id -> 'Neck ID'; rated_load_kg -> 'Rated load (kg)'."""
    parts = [x for x in name.strip("$").split("_") if x]
    words = [_ABBREV.get(x.lower(), x) for x in parts]
    if not words:
        return name
    out = " ".join(words)
    return out[0].upper() + out[1:]


def _units_for(p: Param) -> tuple[str, str]:
    """(unit, kind) for a numeric parameter from its description or name."""
    m = _UNIT_IN_DESC_RE.search(p.description or "")
    if m:
        u = UNIT_WORDS.get(m.group(1).lower(), m.group(1))
        kind = {"°": "angle", "%": "ratio", "×": "ratio", "kg": "mass", "g": "mass", "MPa": "stress", "GPa": "stress", "N": "force"}.get(u, "length" if u in ("mm", "cm", "m", "in") else ("count" if u == "" else "number"))
        return u, kind
    name = p.name.lower()
    for rx, unit, kind in _NAME_RULES:
        if rx.search(name):
            return unit, kind
    return "mm", "length"


def _finish_param(p: Param) -> None:
    p.label = humanize(p.name)
    if p.options:
        p.kind = "choice"
        p.unit = ""
    elif p.type == "bool":
        p.kind = "toggle"
        p.unit = ""
    elif p.type == "number":
        p.unit, p.kind = _units_for(p)
        if p.kind == "count":
            p.step = 1.0
            if isinstance(p.value, float) and p.value.is_integer():
                p.value = int(p.value)
        elif p.step is None:
            p.step = 1.0 if isinstance(p.value, int) and p.kind not in ("clearance", "ratio") else (0.05 if p.kind == "clearance" else 0.1)
    elif p.type == "vector":
        p.kind = "vector"
    else:
        p.kind = "text"
    m = _WHEN_RE.search(p.description or "")
    if m:
        p.gate = m.group(1)
        p.description = _WHEN_RE.sub("", p.description).strip()
        p.description = re.sub(r"\s{2,}", " ", p.description)


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
                      description=" ".join(pending_desc).strip(), raw_value=raw.strip(), order=len(params))
            if ann:
                bracket, rest = _split_annotation(ann)
                if bracket and not _parse_bracket(bracket, p):
                    rest = (rest + " " + bracket).strip() if rest else bracket   # not an annotation after all: keep it as text
                if rest:
                    p.description = (p.description + " " + rest).strip() if p.description else rest
            _finish_param(p)
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
    _apply_gating(params)
    return params


def _apply_gating(params: list[Param]) -> None:
    toggles = [p for p in params if p.type == "bool"]
    names = {p.name for p in params}
    for p in params:
        if p.gate and p.gate not in names:
            p.gate = None
        if p.gate or p.type == "bool":
            continue
        # the longest toggle whose name prefixes this one, in the same section
        best = None
        for t in toggles:
            stems = {t.name}
            if t.name.endswith("s") and len(t.name) > 3:
                stems.add(t.name[:-1])       # scallops -> scallop_depth, flats -> flat_width
            if t.section == p.section and any(p.name.startswith(st + "_") for st in stems) and (best is None or len(t.name) > len(best.name)):
                best = t
        if best:
            p.gate = best.name


# ---------------------------------------------------------------------------------------------------------------------
# the rest of the parameter block: derived values, asserts, echoes, explicit spec bindings

def parse_header_bindings(source: str) -> dict[str, str]:
    """`// Spec dims: neck_ring.inner_diameter <- neck_id (+ clearance), load.loop_inner_width <- loop_inner_w` -> {param: dim}."""
    out: dict[str, str] = {}
    for line in source.splitlines()[:60]:
        m = _SPEC_DIMS_RE.match(line)
        if not m:
            continue
        for dim, param in _BINDING_RE.findall(m.group(1)):
            out.setdefault(param, dim)
    return out


def parse_derived(source: str) -> list[Derived]:
    """Top-level expression assignments (before the first module), with their formulas."""
    out: list[Derived] = []
    for line in source.splitlines():
        if _STOP_RE.match(line):
            break
        m = _ASSIGN_RE.match(line)
        if not m or m.group(1).startswith("$"):
            continue
        value, vtype = _parse_value(m.group(2))
        if vtype == "expression":
            out.append(Derived(name=m.group(1), expr=m.group(2).strip()))
    return out


def parse_asserts(source: str) -> list[Assertion]:
    out: list[Assertion] = []
    for line in source.splitlines():
        if _STOP_RE.match(line):
            break
        m = _ASSERT_RE.match(line)
        if not m:
            continue
        body = m.group(1)
        msg = ""
        cond = body
        mm = re.search(r',\s*"((?:[^"\\]|\\.)*)"\s*$', body)
        if mm:
            msg = mm.group(1)
            cond = body[: mm.start()].strip()
        out.append(Assertion(cond=cond.strip(), message=msg, params=sorted(set(_IDENT_RE.findall(cond)))))
    return out


def parse_echo_names(source: str) -> list[str]:
    names: list[str] = []
    for line in source.splitlines():
        if _STOP_RE.match(line):
            break
        m = _ECHO_RE.match(line)
        if not m:
            continue
        for part in m.group(1).split(","):
            kv = part.split("=", 1)
            if len(kv) == 2 and _IDENT_RE.fullmatch(kv[0].strip()):
                names.append(kv[0].strip())
    return names


def render_targets(params: list[Param]) -> list[str] | None:
    for p in params:
        if p.name == "render_target" and p.options:
            return [str(o["value"]) for o in p.options]
    return None


# ---------------------------------------------------------------------------------------------------------------------
# spec bindings

def _expand_tokens(name: str) -> set[str]:
    words = {"w": "width", "h": "height", "t": "thickness", "d": "diameter", "r": "radius", "len": "length", "l": "length",
             "dia": "diameter", "thk": "thickness", "id": "inner_diameter", "od": "outer_diameter", "sp": "spacing"}
    toks: set[str] = set()
    for x in name.lower().split("_"):
        if not x:
            continue
        toks.update(words.get(x, x).split("_"))
    return toks


def _spec_dims(spec: Any) -> list[dict[str, Any]]:
    """Flatten a PartSpec (or a dict of it) into [{id, key, role, dim, interface}]."""
    out: list[dict[str, Any]] = []
    interfaces = getattr(spec, "interfaces", None)
    if interfaces is None and isinstance(spec, dict):
        interfaces = spec.get("interfaces", [])
    for itf in interfaces or []:
        g = (lambda k, d=None: getattr(itf, k, d)) if not isinstance(itf, dict) else (lambda k, d=None: itf.get(k, d))
        dims = g("dims", {}) or {}
        for key, dim in dims.items():
            out.append({"id": f"{g('id')}.{key}", "key": key, "role": "interface", "dim": dim, "owner": itf, "owner_id": g("id")})
    reqs = getattr(spec, "requirements", None)
    if reqs is None and isinstance(spec, dict):
        reqs = spec.get("requirements", [])
    for req in reqs or []:
        g = (lambda k, d=None: getattr(req, k, d)) if not isinstance(req, dict) else (lambda k, d=None: req.get(k, d))
        for key, dim in (g("derived", {}) or {}).items():
            out.append({"id": f"{g('id')}.{key}", "key": key, "role": "requirement", "dim": dim, "owner": req, "owner_id": g("id")})
    return out


def _dim_attr(dim: Any, k: str, default: Any = None) -> Any:
    if isinstance(dim, dict):
        return dim.get(k, default)
    return getattr(dim, k, default)


def _binding_from(entry: dict[str, Any], how: str, spec: Any) -> Binding:
    dim = entry["dim"]
    b = Binding(dim=entry["id"], how=how, role=entry["role"], target=_dim_attr(dim, "target"), tol=_dim_attr(dim, "tol"),
                min=_dim_attr(dim, "min"), max=_dim_attr(dim, "max"), status=str(_dim_attr(dim, "status", "unknown")))
    meas = _dim_attr(dim, "measure")
    if meas is not None:
        b.feature = _dim_attr(meas, "feature")
    ests = _dim_attr(dim, "estimates", []) or []
    for e in ests:
        b.sources.append({"value": _dim_attr(e, "value"), "source": str(_dim_attr(e, "source", "")), "conf": _dim_attr(e, "conf"),
                          "photo": _dim_attr(e, "photo")})
    if entry["role"] == "interface":
        owner = entry["owner"]
        b.fit = str(_dim_attr(owner, "fit", "sliding"))
        cl = _dim_attr(owner, "clearance")
        if cl is None and hasattr(spec, "clearance_for"):
            try:
                cl = spec.clearance_for(owner)
            except Exception:
                cl = None
        b.clearance = cl
    return b


def bind_params(params: list[Param], spec: Any, explicit: dict[str, str] | None = None) -> None:
    """Attach a Binding to every numeric parameter that corresponds to a spec dimension.

    Order of trust: an explicit header binding, then a name match (tokens of the expanded parameter name cover the dimension
    key, or the interface id + key), then a value match (the parameter equals a dimension's target). A name match that also
    matches the value is reported as name+value.
    """
    if spec is None:
        return
    entries = _spec_dims(spec)
    if not entries:
        return
    by_id = {e["id"]: e for e in entries}
    explicit = explicit or {}
    taken: set[str] = set()
    for p in params:
        if p.type != "number":
            continue
        dim_id = explicit.get(p.name)
        if dim_id and dim_id in by_id:
            p.binding = _binding_from(by_id[dim_id], "explicit", spec)
            taken.add(dim_id)
    for p in params:
        if p.type != "number" or p.binding is not None or p.kind in ("clearance", "facets", "count", "ratio", "angle"):
            continue
        ptoks = _expand_tokens(p.name)
        best: tuple[int, dict[str, Any] | None] = (0, None)
        for e in entries:
            if e["id"] in taken:
                continue
            ktoks = _expand_tokens(e["key"])
            otoks = _expand_tokens(str(e["owner_id"])) | ktoks
            score = 0
            if ptoks == ktoks or ptoks == otoks:
                score = 3
            elif ktoks <= ptoks and ptoks <= otoks:
                score = 2
            elif e["key"] in _MATING_KEYS and ktoks <= ptoks and len(ptoks - otoks) <= 1:
                score = 1
            target = _dim_attr(e["dim"], "target")
            value_match = isinstance(p.value, (int, float)) and isinstance(target, (int, float)) and abs(float(p.value) - float(target)) < 1e-6
            if value_match:
                score += 2 if score else 1
            if score > best[0]:
                best = (score, e)
        score, e = best
        if e is None or score < 2:
            continue
        target = _dim_attr(e["dim"], "target")
        value_match = isinstance(p.value, (int, float)) and isinstance(target, (int, float)) and abs(float(p.value) - float(target)) < 1e-6
        how = "name+value" if (score >= 3 and value_match) else ("value" if score == 2 and value_match and not (_expand_tokens(e["key"]) <= ptoks) else "name")
        p.binding = _binding_from(e, how, spec)
        taken.add(e["id"])


def bind_derived(derived: list[Derived], spec: Any, taken: set[str] | None = None) -> None:
    """Computed values (echoed derived dims) that carry a spec dimension's name get its bounds, so the panel can say
    'overall_length 118.8 mm — over the 110 mm footprint limit' before anything is applied."""
    if spec is None:
        return
    entries = [e for e in _spec_dims(spec) if e["id"] not in (taken or set())]
    for d in derived:
        dtoks = _expand_tokens(d.name)
        for e in entries:
            ktoks = _expand_tokens(e["key"])
            if dtoks == ktoks or dtoks == (_expand_tokens(str(e["owner_id"])) | ktoks):
                dim = e["dim"]
                d.binding = {"dim": e["id"], "role": e["role"], "min": _dim_attr(dim, "min"), "max": _dim_attr(dim, "max"),
                             "target": _dim_attr(dim, "target"), "tol": _dim_attr(dim, "tol")}
                break


# ---------------------------------------------------------------------------------------------------------------------
# the whole model

def customizer_model(source: str, spec: Any = None, echo_values: dict[str, Any] | None = None) -> dict[str, Any]:
    params = parse_customizer(source)
    bind_params(params, spec, parse_header_bindings(source))
    derived = parse_derived(source)
    echoed = set(parse_echo_names(source))
    ev = echo_values or {}
    known = {d.name for d in derived}
    for d in derived:
        d.echoed = d.name in echoed
        if d.name in ev:
            d.value = ev[d.name]
    for name in echoed:                      # echoed values without a top-level formula (e.g. echo(overall_length = ...))
        if name not in known:
            derived.append(Derived(name=name, expr="", value=ev.get(name), echoed=True))
    bind_derived(derived, spec, {p.binding.dim for p in params if p.binding})
    sections: list[str] = []
    for p in params:
        if p.section not in sections:
            sections.append(p.section)
    return {
        "params": [p.to_dict() for p in params],
        "sections": sections,
        "render_targets": render_targets(params),
        "derived": [d.to_dict() for d in derived],
        "asserts": [a.to_dict() for a in parse_asserts(source)],
        "bindings": {p.name: p.binding.dim for p in params if p.binding},
    }


def current_values(params: list[Param] | list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for p in params:
        if isinstance(p, Param):
            out[p.name] = p.value
        else:
            out[p["name"]] = p["value"]
    return out


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
                v = values[name]
                if isinstance(v, float) and v.is_integer() and re.fullmatch(r"-?\d+", m.group(2).strip() or "x"):
                    v = int(v)   # keep integer literals integer
                new = f"{name} = {format_define(v)};"
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


# ---------------------------------------------------------------------------------------------------------------------
# OpenSCAD parameter sets (the desktop customizer's presets file: <part>.json next to <part>.scad)

def presets_to_openscad(presets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """OpenSCAD stores every value as a string in {"parameterSets": {...}, "fileFormatVersion": "1"}."""
    from kintsugi.scad.compile import format_define

    sets: dict[str, dict[str, str]] = {}
    for name, values in presets.items():
        sets[name] = {}
        for k, v in values.items():
            if isinstance(v, bool):
                sets[name][k] = "true" if v else "false"
            elif isinstance(v, (int, float)):
                sets[name][k] = repr(v)
            elif isinstance(v, str):
                sets[name][k] = v
            else:
                sets[name][k] = format_define(v)
    return {"parameterSets": sets, "fileFormatVersion": "1"}


def presets_from_openscad(doc: dict[str, Any], params: list[Param] | None = None) -> dict[str, dict[str, Any]]:
    """The inverse: coerce OpenSCAD's string values back to typed values using the parameter list when given."""
    like = {p.name: p.value for p in (params or [])}
    out: dict[str, dict[str, Any]] = {}
    for name, values in (doc.get("parameterSets") or {}).items():
        out[name] = {}
        for k, v in (values or {}).items():
            if isinstance(v, str):
                parsed, _ = _parse_value(v if (v in ("true", "false") or re.fullmatch(r"-?[\d.eE+-]+", v) or v.startswith("[")) else json.dumps(v))
                if k in like and isinstance(like[k], (int, float)) and not isinstance(like[k], bool):
                    try:
                        parsed = float(v)
                        if isinstance(like[k], int) and parsed.is_integer():
                            parsed = int(parsed)
                    except ValueError:
                        pass
                out[name][k] = parsed
            else:
                out[name][k] = v
    return out
