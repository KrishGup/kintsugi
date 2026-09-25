"""The Part Spec: the contract between measurement, modeling and verification.

Every dimension keeps its evidence (estimates with source and confidence). Interface dimensions carry a
`measure` recipe that tells the checker how to measure them on the exported mesh, so verification is
executable rather than interpretive.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

Status = Literal["unknown", "estimated", "confirmed"]
Fit = Literal["press", "sliding", "loose", "snap", "none"]
Source = str  # rectified_sheet | reference_object | user_caliper | user_ruler | user_stated | reconstruction |
#               vision_estimate | template_default | counterpart | coupon | jig_side_view

# Trust order for fusion (higher wins). Two agreeing rectified-sheet shots outrank one; handled in fuse().
SOURCE_TRUST: dict[str, int] = {
    "coupon": 100,
    "user_caliper": 95,
    "user_ruler": 85,
    "user_stated": 80,
    "counterpart": 70,
    "rectified_sheet": 60,
    "jig": 55,
    "jig_side_view": 55,
    "reference_object": 40,
    "reconstruction": 30,
    "vision_estimate": 15,
    "template_default": 5,
}

# Default clearances by fit and material family (mm on diameter for bores; per-side for slots is half).
DEFAULT_CLEARANCE: dict[str, dict[str, float]] = {
    "PLA": {"press": 0.10, "sliding": 0.25, "loose": 0.40, "snap": 0.15, "none": 0.0},
    "PETG": {"press": 0.10, "sliding": 0.30, "loose": 0.45, "snap": 0.20, "none": 0.0},
    "ABS": {"press": 0.10, "sliding": 0.30, "loose": 0.45, "snap": 0.20, "none": 0.0},
    "ASA": {"press": 0.10, "sliding": 0.30, "loose": 0.45, "snap": 0.20, "none": 0.0},
    "TPU": {"press": 0.00, "sliding": 0.30, "loose": 0.60, "snap": 0.10, "none": 0.0},
    "Nylon": {"press": 0.10, "sliding": 0.35, "loose": 0.50, "snap": 0.20, "none": 0.0},
}

INTERFACE_CONF_THRESHOLD = 0.9
BODY_CONF_THRESHOLD = 0.6


class Estimate(BaseModel):
    value: float
    source: Source
    conf: float = 0.5
    photo: str | None = None
    note: str | None = None


class MeasureRecipe(BaseModel):
    """How the checker measures a dimension on the mesh.

    recipe:
      circle_fit_inner   least-squares circle on the hole of the section at `at_z` (nearest `near` if several)
      circle_fit_outer   least-squares circle on the outer boundary of the section at `at_z`
      extent             max - min of mesh vertices along `axis`, optionally within `region` [[x0,y0,z0],[x1,y1,z1]]
      hole_extent        width of the (largest / nearest) hole of the section at `at_z` along `axis`
      section_extent     width of the section polygon at `at_z` along `axis`
      hole_positions     centroids + diameters of every hole in the section at `at_z`; compared to `expect`
      wall_min           minimum wall thickness within `region` (falls back to global)
      bbox               overall extents [x, y, z]
    """

    recipe: Literal[
        "circle_fit_inner", "circle_fit_outer", "extent", "hole_extent", "section_extent",
        "hole_positions", "wall_min", "bbox", "none",
    ] = "none"
    at_z: float | None = None
    axis: Literal["x", "y", "z"] = "z"
    plane_axis: Literal["x", "y", "z"] = "z"  # which axis the section plane is normal to
    near: list[float] | None = None  # [x, y] in the section plane to disambiguate
    region: list[list[float]] | None = None  # [[x0,y0,z0],[x1,y1,z1]]
    expect: list[list[float]] | None = None  # for hole_positions: [[x, y, d], ...]
    feature: str | None = None  # free-text name for the sheet


class Dim(BaseModel):
    target: float | None = None
    tol: float = 0.3
    min: float | None = None
    max: float | None = None
    status: Status = "unknown"
    estimates: list[Estimate] = Field(default_factory=list)
    measure: MeasureRecipe | None = None
    unit: str = "mm"
    note: str | None = None

    @model_validator(mode="after")
    def _derive(self) -> "Dim":
        if self.target is None and self.estimates and self.status == "unknown":
            fused = fuse_estimates(self.estimates)
            if fused is not None:
                self.target, _, _ = fused
                self.status = "estimated"
        return self

    def describe(self) -> str:
        if self.target is not None:
            return f"{self.target:g} ±{self.tol:g} {self.unit}"
        parts = []
        if self.min is not None:
            parts.append(f"≥ {self.min:g}")
        if self.max is not None:
            parts.append(f"≤ {self.max:g}")
        return " ".join(parts) + f" {self.unit}" if parts else "unspecified"

    def passes(self, measured: float) -> bool | None:
        if measured is None:
            return None
        if self.target is not None:
            return abs(measured - self.target) <= self.tol + 1e-9
        ok = True
        if self.min is not None:
            ok = ok and measured >= self.min - 1e-9
        if self.max is not None:
            ok = ok and measured <= self.max + 1e-9
        return ok


class Interface(BaseModel):
    id: str
    type: str = "custom"  # cylindrical_bore | cylindrical_boss | slot | plate | hole_pattern | snap | thread | custom
    mates_with: str = ""
    fit: Fit = "sliding"
    clearance: float | None = None  # on diameter; None means use material default
    dims: dict[str, Dim] = Field(default_factory=dict)
    note: str | None = None


class Requirement(BaseModel):
    id: str
    text: str
    derived: dict[str, Dim] = Field(default_factory=dict)


class ContextShape(BaseModel):
    """Crude proxy of the object the part mates with. Used for interference checks and assembly views."""

    id: str
    shape: Literal["cylinder", "cone", "box", "sphere"] = "cylinder"
    d: float | None = None
    d1: float | None = None
    d2: float | None = None
    h: float | None = None
    size: list[float] | None = None  # box
    at: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])  # base center (cylinder/cone) or box min corner
    axis: Literal["x", "y", "z"] = "z"
    allow_contact: bool = False  # True: small overlap tolerated (declared contact face)


class PrintSettings(BaseModel):
    material: str = "PETG"
    nozzle: float = 0.4
    layer_height: float = 0.2
    min_wall: float = 1.6
    orientation_hint: str | None = None
    supports_ok: bool = False


class PartInfo(BaseModel):
    name: str = "part"
    role: str = ""
    object: str = ""
    design_intent: str = ""
    notes: str = ""


class PartSpec(BaseModel):
    part: PartInfo = Field(default_factory=PartInfo)
    interfaces: list[Interface] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    context: list[ContextShape] = Field(default_factory=list)
    print: PrintSettings = Field(default_factory=PrintSettings)
    open_questions: list[str] = Field(default_factory=list)

    # ---- I/O -------------------------------------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> "PartSpec":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)

    @classmethod
    def from_yaml(cls, text: str) -> "PartSpec":
        return cls.model_validate(yaml.safe_load(text) or {})

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json", exclude_none=True), sort_keys=False, allow_unicode=True)

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(self.to_yaml(), encoding="utf-8")

    # ---- queries ---------------------------------------------------------------------------------
    def all_dims(self) -> list[tuple[str, Dim, bool]]:
        """(qualified name, dim, is_interface) for every dimension in the spec."""
        out: list[tuple[str, Dim, bool]] = []
        for itf in self.interfaces:
            for k, d in itf.dims.items():
                out.append((f"{itf.id}.{k}", d, True))
        for req in self.requirements:
            for k, d in req.derived.items():
                out.append((f"{req.id}.{k}", d, False))
        return out

    def measured_dims(self) -> list[tuple[str, Dim, bool]]:
        return [(n, d, i) for n, d, i in self.all_dims() if d.measure and d.measure.recipe != "none"]

    def unconfirmed_interface_dims(self) -> list[str]:
        return [n for n, d, i in self.all_dims() if i and d.status != "confirmed"]

    def clearance_for(self, itf: Interface) -> float:
        if itf.clearance is not None:
            return itf.clearance
        table = DEFAULT_CLEARANCE.get(self.print.material, DEFAULT_CLEARANCE["PLA"])
        return table.get(itf.fit, 0.25)

    def get_dim(self, qualified: str) -> Dim | None:
        for n, d, _ in self.all_dims():
            if n == qualified:
                return d
        return None

    def add_estimate(self, qualified: str, est: Estimate) -> Dim:
        dim = self.get_dim(qualified)
        if dim is None:
            raise KeyError(qualified)
        dim.estimates.append(est)
        refresh_dim(dim)
        return dim

    def confirm(self, qualified: str, value: float, source: str = "user_stated", conf: float = 0.97) -> Dim:
        dim = self.get_dim(qualified)
        if dim is None:
            raise KeyError(qualified)
        dim.estimates.append(Estimate(value=value, source=source, conf=conf))
        dim.target = value
        dim.status = "confirmed"
        return dim

    def summary_for_model(self) -> str:
        """Compact text the designer and critic both read."""
        lines = [f"PART {self.part.name}: {self.part.role}".strip()]
        if self.part.object:
            lines.append(f"  object: {self.part.object}")
        if self.part.design_intent:
            lines.append(f"  design intent: {self.part.design_intent}")
        for itf in self.interfaces:
            lines.append(f"INTERFACE {itf.id} ({itf.type}, fit={itf.fit}, clearance={self.clearance_for(itf):g}) mates with {itf.mates_with}")
            for k, d in itf.dims.items():
                rec = f" [measured by {d.measure.recipe}" + (f" at z={d.measure.at_z:g}" if d.measure and d.measure.at_z is not None else "") + "]" if d.measure else ""
                lines.append(f"  {k}: {d.describe()} status={d.status}{rec}")
        for req in self.requirements:
            lines.append(f"REQUIREMENT {req.id}: {req.text}")
            for k, d in req.derived.items():
                rec = f" [measured by {d.measure.recipe}]" if d.measure else ""
                lines.append(f"  {k}: {d.describe()}{rec}")
        if self.context:
            lines.append("CONTEXT (proxy of the mating object; the part must not intersect these unless allow_contact):")
            for c in self.context:
                geo = {k: v for k, v in c.model_dump(exclude_none=True).items() if k not in ("id",)}
                lines.append(f"  {c.id}: {geo}")
        p = self.print
        lines.append(f"PRINT: {p.material}, nozzle {p.nozzle:g}, layer {p.layer_height:g}, min wall {p.min_wall:g}"
                     + (f", orientation: {p.orientation_hint}" if p.orientation_hint else "")
                     + (", supports ok" if p.supports_ok else ", avoid supports"))
        if self.open_questions:
            lines.append("OPEN QUESTIONS: " + "; ".join(self.open_questions))
        return "\n".join(lines)


# ---- fusion ----------------------------------------------------------------------------------------

def fuse_estimates(estimates: list[Estimate]) -> tuple[float, float, str] | None:
    """Pick a value from the evidence.

    Rule: highest-trust source wins. Two rectified-sheet estimates that agree within 1% are promoted above a
    single user_stated value's trust? No: user-confirmed always wins. Agreement between two independent
    sources raises confidence. Returns (value, confidence, reason) or None.
    """
    if not estimates:
        return None
    ranked = sorted(estimates, key=lambda e: (SOURCE_TRUST.get(e.source, 10), e.conf), reverse=True)
    best = ranked[0]
    value, conf = best.value, best.conf
    reason = f"from {best.source}"
    # Independent agreement boosts confidence
    others = [e for e in ranked[1:] if e.source != best.source]
    agree = [e for e in others if abs(e.value - value) <= max(0.3, 0.01 * abs(value))]
    if agree:
        conf = min(0.99, max(conf, 1 - (1 - conf) * 0.5))
        reason += f", corroborated by {', '.join(sorted({e.source for e in agree}))}"
    # Same-source repeat agreement (two rectified shots) also helps
    same = [e for e in ranked[1:] if e.source == best.source and abs(e.value - value) <= max(0.3, 0.01 * abs(value))]
    if same and not agree:
        conf = min(0.95, max(conf, 1 - (1 - conf) * 0.6))
        reason += f", repeated {best.source} agrees"
    return value, conf, reason


def disagreement(estimates: list[Estimate], tol: float) -> list[tuple[Estimate, Estimate]] | None:
    """Pairs of high-trust estimates that disagree beyond tolerance (these become measurement request cards)."""
    strong = [e for e in estimates if SOURCE_TRUST.get(e.source, 10) >= 40]
    bad = []
    for i in range(len(strong)):
        for j in range(i + 1, len(strong)):
            if abs(strong[i].value - strong[j].value) > tol:
                bad.append((strong[i], strong[j]))
    return bad or None


def refresh_dim(dim: Dim) -> None:
    """Recompute target/status from evidence unless confirmed by the user."""
    if dim.status == "confirmed":
        return
    fused = fuse_estimates(dim.estimates)
    if fused is None:
        return
    value, conf, _ = fused
    dim.target = value
    dim.status = "confirmed" if conf >= INTERFACE_CONF_THRESHOLD else "estimated"


def spec_to_json(spec: PartSpec) -> dict[str, Any]:
    return spec.model_dump(mode="json", exclude_none=True)
