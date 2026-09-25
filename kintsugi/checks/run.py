"""Run every check the spec asks for against a mesh and produce checks.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from kintsugi.checks import geometry as G
from kintsugi.spec.model import Dim, PartSpec


@dataclass
class CheckItem:
    id: str
    label: str
    kind: str  # hard | soft | info
    passed: bool | None
    measured: Any = None
    target: Any = None
    tol: float | None = None
    unit: str = "mm"
    detail: str = ""
    annotate: dict | None = None  # hints for the blueprint: {"view": "section_z_3.0", "type": "circle", ...}

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CheckReport:
    iteration: int
    mesh_path: str
    items: list[CheckItem] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    orientations: list[dict] = field(default_factory=list)
    walls: dict | None = None
    printability: dict | None = None
    sections: list[dict] = field(default_factory=list)  # planes the sheet should draw
    interference: list[dict] = field(default_factory=list)

    @property
    def hard_failures(self) -> list[CheckItem]:
        return [i for i in self.items if i.kind == "hard" and i.passed is False]

    @property
    def all_hard_pass(self) -> bool:
        return not self.hard_failures and all(i.passed is not None for i in self.items if i.kind == "hard")

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration, "mesh_path": self.mesh_path,
            "all_hard_pass": self.all_hard_pass,
            "items": [i.to_dict() for i in self.items], "stats": self.stats, "walls": self.walls,
            "printability": self.printability, "orientations": self.orientations[:3], "sections": self.sections,
            "interference": self.interference,
        }

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def summary_for_model(self) -> str:
        lines = [f"CHECKS iteration {self.iteration}: {'ALL HARD CHECKS PASS' if self.all_hard_pass else 'FAILURES PRESENT'}"]
        for it in self.items:
            mark = "PASS" if it.passed else ("FAIL" if it.passed is False else "n/a ")
            meas = _fmt(it.measured)
            tgt = _fmt(it.target)
            tol = f" ±{it.tol:g}" if it.tol is not None and it.target is not None and not isinstance(it.target, str) else ""
            lines.append(f"  [{mark}] {it.id}: measured {meas} vs {tgt}{tol} {it.unit if it.unit else ''}".rstrip()
                         + (f" — {it.detail}" if it.detail else ""))
        if self.walls:
            lines.append(f"  walls: min {self.walls['min']:.2f} p05 {self.walls['p05']:.2f} median {self.walls['median']:.2f} (required min {self.walls['required']:.2f})")
        if self.printability:
            p = self.printability
            lines.append(f"  printability (as modeled): overhang {p['overhang_fraction']*100:.1f}% of area beyond 45°, bed contact {p['bed_contact_area']:.0f} mm², height {p['height']:.1f} mm")
            if self.orientations:
                best = self.orientations[0]
                lines.append(f"  best orientation: {best['name']} (overhang {best['overhang_fraction']*100:.1f}%)")
        s = self.stats
        if s:
            lines.append(f"  mesh: {s.get('triangles')} tris, watertight={s.get('watertight')}, bodies={s.get('bodies')}, "
                         f"bbox {s['bbox']['size']} mm, volume {s.get('volume_mm3')} mm³")
        return "\n".join(lines)


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.2f}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    return str(v)


def run_checks(mesh_path: str | Path, spec: PartSpec, iteration: int = 0, *, wall_samples: int = 1500) -> CheckReport:
    mesh = G.load_mesh(mesh_path)
    rep = CheckReport(iteration=iteration, mesh_path=str(mesh_path))
    rep.stats = G.mesh_stats(mesh)

    # --- topology (hard)
    rep.items.append(CheckItem("mesh.watertight", "Mesh is watertight", "hard", bool(mesh.is_watertight),
                               measured="yes" if mesh.is_watertight else "no", target="yes", unit=""))
    bodies = rep.stats.get("bodies", 1)
    rep.items.append(CheckItem("mesh.single_body", "Single body", "hard", bodies == 1, measured=bodies, target=1, unit="bodies",
                               detail="" if bodies == 1 else "separate pieces will print as loose parts; union them or intend it"))

    # --- spec dimensions
    planes: dict[tuple[str, float], list[str]] = {}
    offsets = clearance_offsets(spec)
    for qname, dim, is_itf in spec.all_dims():
        item = _measure_dim(mesh, qname, dim, is_itf, offsets.get(qname, 0.0))
        if item is not None:
            rep.items.append(item)
            r = dim.measure
            if r and r.at_z is not None and r.recipe in ("circle_fit_inner", "circle_fit_outer", "hole_extent", "section_extent", "hole_positions"):
                planes.setdefault((r.plane_axis, float(r.at_z)), []).append(qname)
    rep.sections = [{"plane_axis": ax, "at": at, "dims": names} for (ax, at), names in planes.items()]
    if not rep.sections:
        # default: one section through the middle height
        zc = float((mesh.bounds[0][2] + mesh.bounds[1][2]) / 2)
        rep.sections = [{"plane_axis": "z", "at": round(zc, 3), "dims": []}]

    # --- walls (hard on p05, soft on min)
    ws = G.wall_thickness(mesh, n_samples=wall_samples, threshold=spec.print.min_wall)
    if ws is not None:
        rep.walls = {"min": ws.min, "p05": ws.p05, "median": ws.median, "n": ws.n, "required": spec.print.min_wall,
                     "thin_points": ws.thin_points[:200].round(2).tolist()}
        rep.items.append(CheckItem("walls.p05", "Wall thickness (5th percentile)", "hard", ws.p05 >= spec.print.min_wall - 1e-6,
                                   measured=round(ws.p05, 3), target=spec.print.min_wall, unit="mm",
                                   detail="≥ two perimeters" if ws.p05 >= spec.print.min_wall else
                                   f"{len(ws.thin_points)} sampled points thinner than {spec.print.min_wall:g} mm"))
        rep.items.append(CheckItem("walls.min", "Wall thickness (minimum sampled)", "soft", ws.min >= 0.75 * spec.print.min_wall,
                                   measured=round(ws.min, 3), target=round(0.75 * spec.print.min_wall, 3), unit="mm"))

    # --- printability (info + soft)
    st = G.overhang_stats(mesh)
    rep.printability = {"overhang_fraction": st.fraction, "overhang_area": st.overhang_area, "bed_contact_area": st.bed_contact_area,
                        "centroid_height": st.centroid_height, "height": float(mesh.extents[2]), "footprint_area": st.footprint_area}
    rep.items.append(CheckItem("print.overhang", "Overhang area beyond 45° (as modeled)", "soft",
                               st.fraction <= 0.05 or spec.print.supports_ok, measured=round(st.fraction * 100, 2), target=5.0, unit="%",
                               detail="" if st.fraction <= 0.05 else "consider chamfers, teardrops, or a different orientation"))
    rep.items.append(CheckItem("print.bed_contact", "Bed contact area (as modeled)", "info", None,
                               measured=round(st.bed_contact_area, 1), unit="mm²"))
    zmin = float(mesh.bounds[0][2])
    rep.items.append(CheckItem("print.on_bed", "Model sits on the bed (min z = 0)", "soft", abs(zmin) < 0.01,
                               measured=round(zmin, 3), target=0.0, tol=0.01, unit="mm",
                               detail="" if abs(zmin) < 0.01 else "translate so the bottom face is at z = 0"))
    try:
        rep.orientations = G.score_orientations(mesh)
    except Exception as e:  # pragma: no cover
        rep.orientations = [{"name": "as modeled", "error": str(e)}]

    # --- interference with context (hard unless allow_contact)
    for c in spec.context:
        try:
            other = G.context_mesh(c.shape, d=c.d, d1=c.d1, d2=c.d2, h=c.h, size=c.size, at=c.at, axis=c.axis)
            vol = G.interference_volume(mesh, other)
        except Exception as e:
            rep.items.append(CheckItem(f"interference.{c.id}", f"Interference with {c.id}", "info", None, detail=f"could not evaluate: {e}"))
            continue
        limit = 2.0 if c.allow_contact else 0.05
        rep.interference.append({"id": c.id, "volume_mm3": vol, "allow_contact": c.allow_contact})
        rep.items.append(CheckItem(f"interference.{c.id}", f"Interference volume with {c.id}", "hard", vol <= limit,
                                   measured=round(vol, 3), target=0.0, tol=limit, unit="mm³",
                                   detail="" if vol <= limit else f"the part penetrates the {c.id} proxy; enlarge the clearance or move the feature"))
    return rep


def clearance_offsets(spec: PartSpec) -> dict[str, float]:
    """Which spec dimensions get the fit clearance applied, and with what sign.

    Interface dims describe the mating object. A bore that receives a boss is made larger by the clearance;
    a boss that enters a hole is made smaller. Anything else is checked as-is.
    """
    out: dict[str, float] = {}
    female_names = ("inner_diameter", "bore", "id", "hole_diameter", "width", "slot_width")
    male_names = ("outer_diameter", "od", "boss_diameter", "pin_diameter")
    for itf in spec.interfaces:
        if itf.fit == "none":
            continue
        c = spec.clearance_for(itf)
        side = itf.side
        if side is None:
            side = "female" if itf.type in ("cylindrical_bore", "slot", "hole_pattern") else ("male" if itf.type in ("cylindrical_boss", "snap") else None)
        for key in itf.dims:
            k = key.lower()
            receives = k in female_names or k.endswith("_bore") or k.endswith("_id")
            enters = k in male_names or k.endswith("_od")
            if side == "female" and (receives or (itf.type == "thread" and enters)):
                # the part is the receiving side: its opening is the mate's size plus clearance
                out[f"{itf.id}.{key}"] = +c
            elif side == "male" and (enters or (itf.type == "thread" and receives)):
                out[f"{itf.id}.{key}"] = -c
            elif side is None:
                if receives:
                    out[f"{itf.id}.{key}"] = +c
                elif enters:
                    out[f"{itf.id}.{key}"] = -c
    return out


def _measure_dim(mesh: trimesh.Trimesh, qname: str, dim: Dim, is_itf: bool, offset: float = 0.0) -> CheckItem | None:
    r = dim.measure
    if r is None or r.recipe == "none":
        return None
    kind = "hard" if (is_itf or dim.target is not None or dim.min is not None or dim.max is not None) else "info"
    label = r.feature or qname
    unit = dim.unit
    try:
        if r.recipe in ("circle_fit_inner", "circle_fit_outer"):
            if r.at_z is None:
                return CheckItem(qname, label, kind, None, detail="recipe needs at_z")
            fn = G.circle_fit_inner if r.recipe == "circle_fit_inner" else G.circle_fit_outer
            c = fn(mesh, r.at_z, r.plane_axis, r.near)
            if c is None:
                return CheckItem(qname, label, kind, False, measured=None, target=dim.target, tol=dim.tol, unit=unit,
                                 detail=f"no {'hole' if r.recipe.endswith('inner') else 'section'} found at {r.plane_axis}={r.at_z:g}")
            detail = f"center ({c.cx:.2f}, {c.cy:.2f}), fit rms {c.rms:.3f}"
            passed = dim.passes(c.d - offset) if offset else dim.passes(c.d)
            if c.inlier_fraction < 0.999:
                detail += f", circular arc covers {c.inlier_fraction*100:.0f}% of the boundary"
                if r.recipe == "circle_fit_inner" and c.inlier_fraction < 0.9:
                    passed = False
                    detail += " — the bore is not a complete circle: another cutout breaks into it"
                else:
                    detail += " (another feature merges into it)"
            if c.rms > 0.15:
                detail += " — not round (rms > 0.15): the feature is not a circle at this height"
            if offset:
                detail += f"; expected {dim.target:g} {'+' if offset > 0 else '-'} clearance {abs(offset):g} = {dim.target + offset:g}"
            return CheckItem(qname, label, kind, passed, measured=round(c.d, 3),
                             target=(round(dim.target + offset, 3) if dim.target is not None else _bounds(dim)),
                             tol=dim.tol if dim.target is not None else None, unit=unit, detail=detail,
                             annotate={"type": "circle", "plane_axis": r.plane_axis, "at": r.at_z, "cx": c.cx, "cy": c.cy, "r": c.r})
        if r.recipe == "extent":
            v = G.extent(mesh, r.axis, r.region)
            if v is None:
                return CheckItem(qname, label, kind, False, target=dim.target, tol=dim.tol, unit=unit, detail="no vertices in region")
            return CheckItem(qname, label, kind, dim.passes(v - offset), measured=round(v, 3),
                             target=(round(dim.target + offset, 3) if dim.target is not None else _bounds(dim)),
                             tol=dim.tol if dim.target is not None else None, unit=unit,
                             detail=(f"expected {dim.target:g} {'+' if offset > 0 else '-'} clearance {abs(offset):g}" if offset and dim.target is not None else ""),
                             annotate={"type": "extent", "axis": r.axis, "region": r.region})
        if r.recipe in ("hole_extent", "section_extent"):
            if r.at_z is None:
                return CheckItem(qname, label, kind, None, detail="recipe needs at_z")
            fn = G.hole_extent if r.recipe == "hole_extent" else G.section_extent
            v = fn(mesh, r.at_z, r.axis, r.plane_axis, r.near)
            if v is None:
                return CheckItem(qname, label, kind, False, target=dim.target, tol=dim.tol, unit=unit,
                                 detail=f"no {'hole' if r.recipe == 'hole_extent' else 'section'} at {r.plane_axis}={r.at_z:g}")
            return CheckItem(qname, label, kind, dim.passes(v - offset), measured=round(v, 3),
                             target=(round(dim.target + offset, 3) if dim.target is not None else _bounds(dim)),
                             tol=dim.tol if dim.target is not None else None, unit=unit,
                             detail=(f"expected {dim.target:g} {'+' if offset > 0 else '-'} clearance {abs(offset):g}" if offset and dim.target is not None else ""),
                             annotate={"type": r.recipe, "plane_axis": r.plane_axis, "at": r.at_z, "axis": r.axis, "near": r.near})
        if r.recipe == "hole_positions":
            if r.at_z is None:
                return CheckItem(qname, label, kind, None, detail="recipe needs at_z")
            holes = G.hole_positions(mesh, r.at_z, r.plane_axis)
            found = [[round(h["x"], 2), round(h["y"], 2), round(h["d"], 2)] for h in holes]
            if not r.expect:
                return CheckItem(qname, label, "info", None, measured=found, unit="", detail=f"{len(holes)} holes")
            ok, worst = True, 0.0
            for ex in r.expect:
                best = min((np.hypot(h["x"] - ex[0], h["y"] - ex[1]) + abs(h["d"] - ex[2]) for h in holes), default=1e9)
                worst = max(worst, best)
                if best > dim.tol:
                    ok = False
            return CheckItem(qname, label, kind, ok, measured=found, target=r.expect, tol=dim.tol, unit="",
                             detail=f"worst match {worst:.2f} mm" if holes else "no holes found",
                             annotate={"type": "holes", "plane_axis": r.plane_axis, "at": r.at_z})
        if r.recipe == "wall_min":
            ws = G.wall_thickness(mesh, 800, threshold=dim.min or 1.6, region=r.region)
            if ws is None:
                return CheckItem(qname, label, kind, None, detail="no samples")
            return CheckItem(qname, label, kind, dim.passes(ws.p05), measured=round(ws.p05, 3), target=_bounds(dim), unit=unit,
                             detail=f"min {ws.min:.2f}")
        if r.recipe == "bbox":
            size = [float(x) for x in mesh.extents]
            ok = None
            if dim.target is not None:
                ok = abs(max(size) - dim.target) <= dim.tol
            return CheckItem(qname, label, "info" if ok is None else kind, ok, measured=[round(s, 2) for s in size], target=dim.target,
                             tol=dim.tol, unit=unit)
    except Exception as e:
        return CheckItem(qname, label, kind, False, detail=f"measurement error: {e}")
    return None


def _bounds(dim: Dim) -> str:
    parts = []
    if dim.min is not None:
        parts.append(f"≥{dim.min:g}")
    if dim.max is not None:
        parts.append(f"≤{dim.max:g}")
    return " ".join(parts) if parts else "—"
