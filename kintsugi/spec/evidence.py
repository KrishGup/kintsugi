"""The evidence graph: what the spec needs to know, what we know it from, and the cheapest way to learn the rest.

Nodes: every spec dimension, every estimate behind it, the photos those estimates came from, the capture-plan shots and
questions that target a dimension, the standards that supplied a catalogue value, and (once a design exists) the
checks that verify each dimension on the mesh. Edges say which supports which.

Two algorithms run on it:
  missing()     the dimensions that still need evidence, ranked by how much a wrong value costs
                (an interface dim decides the fit; a requirement dim only the shape) and by how weak the evidence is
  plan_round()  the next batch of things to ask the user for: one photo request per mating feature (a photo on the
                calibration sheet measures every planar dimension of that feature at once), a ruler question for the
                dimensions a photo cannot pin down, a coupon when only the fit is still in doubt

The follow-up agent turns that plan into instructions written for the specific object in the photos; without a model
the algorithmic plan is shown as is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from kintsugi.spec.model import Dim, PartSpec, disagreement, fuse_estimates, source_trust

# recipes whose feature is a planar outline in a section: a top-down photo on the calibration sheet measures them
PLANAR_RECIPES = {"circle_fit_inner", "circle_fit_outer", "hole_extent", "section_extent", "hole_positions", "notch_circle", "notch_mouth", "gap"}
# recipes that measure a height/length: a ruler (or a side photo with a reference) is the honest way
LINEAR_RECIPES = {"extent", "bbox", "wall_min"}

READY_CONF = 0.6  # an estimated interface dim at this confidence may be designed against (with a coupon afterwards)
# dimension names that describe the mating object itself (the fit clearance applies to exactly these)
MATING_NAMES = {"inner_diameter", "outer_diameter", "width", "positions", "thread_od", "major_diameter", "bore_diameter", "shaft_diameter"}


@dataclass
class MissingDim:
    dim: str
    importance: str  # interface | requirement
    status: str
    conf: float
    reason: str  # unknown | low_confidence | conflict | estimated
    recipe: str | None
    feature: str | None
    interface: str | None
    mates_with: str | None
    fit: str | None
    target: float | None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class Request:
    id: str
    kind: str  # photo | measure | choice | coupon
    dims: list[str]
    title: str
    instructions: str
    why: str
    priority: int = 1  # 0 = must, 1 = should, 2 = nice
    feature: str | None = None
    label: str | None = None  # upload label (prefix) for photo requests

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class EvidenceGraph:
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    missing: list[MissingDim] = field(default_factory=list)
    ready: bool = False
    readiness: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": self.nodes, "edges": self.edges, "missing": [m.to_dict() for m in self.missing], "ready": self.ready,
                "readiness": self.readiness}


def _conf_of(dim: Dim) -> float:
    if dim.status == "confirmed":
        return max(0.97, max((e.conf for e in dim.estimates), default=0.97))
    fused = fuse_estimates(dim.estimates)
    return fused[1] if fused else 0.0


def _shot_label(n: int) -> str:
    return f"shot{n}"


def label_of(name: str, known: set[str] | None = None) -> str:
    """The upload label a photo name starts with: the longest known label, else `shotN` / `rN_...` / `qN_N` patterns."""
    stem = name.rsplit(".", 1)[0]
    if known:
        for lab in sorted(known, key=len, reverse=True):
            if stem == lab or stem.startswith(lab + "_"):
                return lab
    m = re.match(r"^(shot\d+|r\d+_[a-z]+\d*|q\d+_\d+)(?:_|$)", stem)
    return m.group(1) if m else ""


def known_labels(intake: dict[str, Any]) -> set[str]:
    labs: set[str] = set()
    for c in intake.get("capture_plan") or []:
        if c.get("n") is not None:
            labs.add(_shot_label(int(c["n"])))
    for rnd in intake.get("rounds") or []:
        for r in rnd.get("requests") or []:
            if r.get("label"):
                labs.add(str(r["label"]))
            elif r.get("id"):
                labs.add(str(r["id"]))
    for pr in intake.get("designer_requests") or []:
        if pr.get("label"):
            labs.add(str(pr["label"]))
    return labs


def is_design_freedom(qual: str, dim: Dim) -> bool:
    """An interface dimension that only bounds the part's own size (no target, no evidence, not a mating name)."""
    name = qual.split(".")[-1]
    return dim.target is None and not dim.estimates and (dim.min is not None or dim.max is not None) and name not in MATING_NAMES


def build(spec: PartSpec, photos: list[dict[str, Any]] | None = None, intake: dict[str, Any] | None = None,
          checks: dict[str, Any] | None = None, standards: list[dict[str, Any]] | None = None) -> EvidenceGraph:
    """Assemble the graph from the spec's evidence, the session photos (with grades), intake's plan and questions, checks."""
    g = EvidenceGraph()
    photos = photos or []
    intake = intake or {}
    seen: set[str] = set()

    def node(nid: str, **attrs):
        if nid in seen:
            return
        seen.add(nid)
        g.nodes.append({"id": nid, **attrs})

    def edge(a: str, b: str, rel: str, **attrs):
        g.edges.append({"from": a, "to": b, "rel": rel, **attrs})

    # photos and their grades
    by_label: dict[str, list[str]] = {}
    labs = known_labels(intake)
    for p in photos:
        f = str(p.get("file", ""))
        name = f.split("/")[-1]
        grade = p.get("grade") or {}
        node(f"photo:{name}", type="photo", label=name, ok=bool(grade.get("ok")), markers=int(grade.get("markers_found") or 0), file=f)
        lab = label_of(name, labs)
        if lab:
            by_label.setdefault(lab, []).append(name)

    # capture-plan shots and questions
    for c in intake.get("capture_plan") or []:
        n = int(c.get("n") or 0) or (len([x for x in g.nodes if x["type"] == "shot"]) + 1)
        sid = f"shot:{n}"
        node(sid, type="shot", label=c.get("name") or f"shot {n}", purpose=c.get("purpose"), n=n)
        for m in c.get("measures") or []:
            edge(sid, f"dim:{m}", "targets")
        for name in by_label.get(_shot_label(n), []):
            edge(f"photo:{name}", sid, "fulfils")
    for rnd_i, rnd in enumerate(intake.get("rounds") or []):
        for r in rnd.get("requests") or []:
            rid = f"req:{r.get('id') or rnd_i}"
            node(rid, type="request", label=r.get("title") or r.get("id"), kind=r.get("kind"), round=rnd_i + 1)
            for m in r.get("dims") or []:
                edge(rid, f"dim:{m}", "targets")
            lab = r.get("label")
            for name in by_label.get(lab or "", []):
                edge(f"photo:{name}", rid, "fulfils")
    for q in intake.get("questions") or []:
        if q.get("dim"):
            qid = f"q:{q.get('id') or q.get('dim')}"
            node(qid, type="question", label=q.get("text"), kind=q.get("kind"))
            edge(qid, f"dim:{q['dim']}", "targets")

    # dimensions and their evidence
    itf_by_id = {i.id: i for i in spec.interfaces}
    for qual, dim, is_itf in spec.all_dims():
        itf = itf_by_id.get(qual.split(".")[0]) if is_itf else None
        conf = _conf_of(dim)
        node(f"dim:{qual}", type="dim", label=qual, status=dim.status, conf=round(conf, 2), target=dim.target, tol=dim.tol,
             bounded=dim.min is not None or dim.max is not None, freedom=is_itf and is_design_freedom(qual, dim),
             importance="interface" if is_itf else "requirement", recipe=dim.measure.recipe if dim.measure else None,
             feature=(dim.measure.feature if dim.measure else None) or (itf.mates_with if itf else None),
             fit=itf.fit if itf else None, interface=itf.id if itf else None)
        for k, e in enumerate(dim.estimates):
            eid = f"est:{qual}:{k}"
            node(eid, type="estimate", label=f"{e.value:g} mm", value=e.value, source=e.source, conf=e.conf, trust=source_trust(e.source), photo=e.photo)
            edge(eid, f"dim:{qual}", "supports", weight=source_trust(e.source))
            if e.photo:
                pname = str(e.photo).split("/")[-1]
                node(f"photo:{pname}", type="photo", label=pname, file=e.photo)
                edge(f"photo:{pname}", eid, "measured_in")
            if e.source.startswith("standard:"):
                sid = f"std:{e.source.split(':', 1)[1]}"
                node(sid, type="standard", label=e.source.split(":", 1)[1])
                edge(sid, eid, "catalogue")
    for s in standards or []:
        node(f"std:{s['id']}", type="standard", label=s.get("name") or s["id"], dims=s.get("dims"), conf=s.get("conf"))

    # checks (the design side of the graph)
    for item in (checks or {}).get("items") or []:
        cid = str(item.get("id"))
        if any(n["id"] == f"dim:{cid}" for n in g.nodes):
            node(f"check:{cid}", type="check", label=cid, passed=item.get("passed"), measured=item.get("measured"))
            edge(f"check:{cid}", f"dim:{cid}", "verifies")

    g.missing = missing(spec)
    g.readiness = readiness(spec, g.missing)
    g.ready = bool(g.readiness["ready"])
    return g


def missing(spec: PartSpec) -> list[MissingDim]:
    out: list[MissingDim] = []
    itf_by_id = {i.id: i for i in spec.interfaces}
    for qual, dim, is_itf in spec.all_dims():
        if dim.status == "confirmed":
            continue
        itf = itf_by_id.get(qual.split(".")[0]) if is_itf else None
        conf = _conf_of(dim)
        if is_itf and is_design_freedom(qual, dim):
            continue  # the part's own size with a stated bound: the designer's freedom, not a measurement of the object
        if dim.target is None and dim.min is None and dim.max is None:
            reason = "unknown"
        elif disagreement(dim.estimates, dim.tol):
            reason = "conflict"
        elif not dim.estimates:
            reason = "unknown" if is_itf else "estimated"
        elif conf < READY_CONF:
            reason = "low_confidence"
        else:
            reason = "estimated"
        if not is_itf and reason == "estimated" and (dim.min is not None or dim.max is not None or dim.target is not None):
            continue  # a requirement dimension with a stated bound needs no further evidence
        out.append(MissingDim(qual, "interface" if is_itf else "requirement", dim.status, round(conf, 2), reason,
                              dim.measure.recipe if dim.measure else None, (dim.measure.feature if dim.measure else None) or (itf.mates_with if itf else None),
                              itf.id if itf else None, itf.mates_with if itf else None, itf.fit if itf else None, dim.target))
    order = {"conflict": 0, "unknown": 1, "low_confidence": 2, "estimated": 3}
    out.sort(key=lambda m: (0 if m.importance == "interface" else 1, order.get(m.reason, 9), m.conf))
    return out


def readiness(spec: PartSpec, miss: list[MissingDim] | None = None) -> dict[str, Any]:
    miss = missing(spec) if miss is None else miss
    blocking = [m for m in miss if m.importance == "interface" and m.reason in ("unknown", "conflict", "low_confidence")]
    soft = [m for m in miss if m.importance == "interface" and m.reason == "estimated"]
    relevant = [(q, d) for q, d, i in spec.all_dims() if i and not is_design_freedom(q, d)]
    total = len(relevant) or 1
    confirmed = len([1 for _, d in relevant if d.status == "confirmed"])
    return {"ready": not blocking, "blocking": [m.dim for m in blocking], "unconfirmed": [m.dim for m in soft],
            "confirmed": confirmed, "interface_dims": total, "score": round(confirmed / total, 2),
            "advice": ("Every interface dimension is confirmed." if confirmed == total else
                       "The fit dimensions are known well enough to design; print the coupon to lock the clearance." if not blocking else
                       "Some fit dimensions are still guesses — a photo on the sheet or a ruler reading is needed before the part can fit.")}


def plan_round(spec: PartSpec, miss: list[MissingDim] | None = None, photos: list[dict[str, Any]] | None = None,
               round_no: int = 1) -> list[Request]:
    """Batch the missing dimensions into the fewest user actions."""
    miss = missing(spec) if miss is None else miss
    reqs: list[Request] = []
    # 1. one sheet photo per mating feature covers all its planar dims
    by_feature: dict[str, list[MissingDim]] = {}
    for m in miss:
        if m.recipe in PLANAR_RECIPES and m.importance == "interface":
            by_feature.setdefault(m.interface or m.feature or m.dim, []).append(m)
    k = 0
    for feat, ms in by_feature.items():
        k += 1
        itf = next((i for i in spec.interfaces if i.id == feat), None)
        what = (itf.mates_with if itf else None) or ms[0].feature or feat
        rid = f"r{round_no}_photo{k}"
        conflict = any(m.reason == "conflict" for m in ms)
        reqs.append(Request(rid, "photo", [m.dim for m in ms], f"{what} on the calibration sheet",
                            f"Press the {what} flat onto the printed calibration sheet (the mating face down, the opening or outline "
                            f"touching the paper) and photograph it straight from above with at least two markers in frame. "
                            + ("Two independent readings disagree, so this shot decides." if conflict else "This one photo measures every dimension of that feature."),
                            "the checker needs the true " + ", ".join(m.dim.split(".")[-1].replace("_", " ") for m in ms) + " to size the fit",
                            0 if any(m.reason in ("unknown", "conflict", "low_confidence") for m in ms) else 1, feature=what, label=rid))
    # 2. ruler readings for linear dims and anything not planar
    for m in miss:
        if m.recipe in PLANAR_RECIPES and m.importance == "interface":
            continue
        name = m.dim.split(".")[-1].replace("_", " ")
        pri = 0 if (m.importance == "interface" and m.reason in ("unknown", "conflict", "low_confidence")) else (1 if m.importance == "interface" else 2)
        hint = f" The photos suggest about {m.target:g} mm." if m.target is not None else ""
        reqs.append(Request(f"r{round_no}_measure_{m.dim.replace('.', '_')}", "measure", [m.dim], f"Measure the {name}",
                            f"With a ruler or caliper, read the {name}" + (f" of the {m.feature}" if m.feature else "") + f" in mm.{hint}",
                            "a height or length cannot be read from a top-down photo", pri, feature=m.feature))
    # 3. a coupon when the only doubt left is the fit itself
    soft = [m for m in miss if m.importance == "interface" and m.reason == "estimated" and m.fit in ("press", "snap", "sliding")]
    if soft and not any(r.priority == 0 for r in reqs):
        reqs.append(Request(f"r{round_no}_coupon", "coupon", [m.dim for m in soft], "Print the fit coupon",
                            "The mating feature alone, at three clearances. Print it flat, try each on the object, and tell Kintsugi which one slid on.",
                            "the surest way to set a press or snap fit is to try it", 1))
    reqs.sort(key=lambda r: (r.priority, r.kind != "photo", r.id))
    return reqs
