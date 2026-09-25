"""Blueprint orchestration: mesh + spec + checks -> annotated views, sections, assembly, composed sheets."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import trimesh

from kintsugi.checks import geometry as G
from kintsugi.checks.run import CheckReport
from kintsugi.render import raster
from kintsugi.render.raster import VIEW_LABELS, pick_scale, render_view
from kintsugi.render.sheet import Panel, annotate_overall, compose_sheet, draw_axes_and_label, render_section
from kintsugi.spec.model import PartSpec

MAIN_VIEWS = ["top", "iso", "front", "right", "bottom", "left", "back"]


@dataclass
class BlueprintResult:
    sheet_path: Path
    sections_path: Path | None
    view_paths: dict[str, Path] = field(default_factory=dict)
    section_paths: dict[str, Path] = field(default_factory=dict)
    assembly_paths: dict[str, Path] = field(default_factory=dict)
    scale_px_per_mm: float = 0.0

    def to_dict(self) -> dict:
        return {
            "sheet": str(self.sheet_path), "sections": str(self.sections_path) if self.sections_path else None,
            "views": {k: str(v) for k, v in self.view_paths.items()},
            "section_views": {k: str(v) for k, v in self.section_paths.items()},
            "assembly": {k: str(v) for k, v in self.assembly_paths.items()},
            "scale_px_per_mm": self.scale_px_per_mm,
        }


def context_ghost(spec: PartSpec) -> trimesh.Trimesh | None:
    meshes = []
    for c in spec.context:
        try:
            meshes.append(G.context_mesh(c.shape, d=c.d, d1=c.d1, d2=c.d2, di=c.di, h=c.h, size=c.size, at=c.at, axis=c.axis))
        except Exception:
            continue
    if not meshes:
        return None
    return trimesh.util.concatenate(meshes)


def make_blueprint(mesh_path: str | Path, spec: PartSpec, report: CheckReport | None, out_dir: str | Path, iteration: int,
                   *, part_name: str | None = None, target_px: float = 560.0) -> BlueprintResult:
    out_dir = Path(out_dir)
    views_dir = out_dir / "views"
    views_dir.mkdir(parents=True, exist_ok=True)
    mesh = G.load_mesh(mesh_path)
    name = part_name or spec.part.name or "part"
    scale = pick_scale(mesh, target_px)
    ghost = context_ghost(spec)


    # ---- orthographic + iso views
    view_imgs: dict[str, raster.ViewImage] = {}
    for v in MAIN_VIEWS:
        vi = render_view(mesh, v, scale, margin_px=96)
        if v in ("top", "front", "right"):
            annotate_overall(vi, mesh)
        _draw_extent_annotations(vi, mesh, report, v)
        draw_axes_and_label(vi, VIEW_LABELS[v])
        view_imgs[v] = vi
    view_paths = {}
    for v, vi in view_imgs.items():
        p = views_dir / f"iter_{iteration:02d}_{v}.png"
        cv2.imwrite(str(p), vi.img)
        view_paths[v] = p

    # ---- sections
    section_panels: list[Panel] = []
    section_paths: dict[str, Path] = {}
    planes = (report.sections if report else []) or [{"plane_axis": "z", "at": float(np.mean(mesh.bounds[:, 2])), "dims": []}]
    sec_scale = min(10.0, scale * 1.4)
    letters = "ABCDEFGH"
    for i, pl in enumerate(planes):
        ax, at = pl["plane_axis"], float(pl["at"])
        anns = _section_annotations(mesh, report, ax, at)
        vi = render_section(mesh, ax, at, sec_scale, annotations=anns, margin_px=90)
        label = f"SECTION {letters[i % 8]}-{letters[i % 8]}  ({ax} = {at:g} mm, viewed from +{ax.upper()})" if ax != "y" else \
            f"SECTION {letters[i % 8]}-{letters[i % 8]}  (y = {at:g} mm, viewed from −Y)"
        draw_axes_and_label(vi, label)
        _mark_cutting_plane(view_imgs, ax, at, letters[i % 8])
        p = views_dir / f"iter_{iteration:02d}_section_{letters[i % 8]}.png"
        cv2.imwrite(str(p), vi.img)
        section_paths[f"{letters[i % 8]}"] = p
        section_panels.append(Panel(label, vi.img))

    # re-save views after cutting-plane marks
    for v, vi in view_imgs.items():
        cv2.imwrite(str(view_paths[v]), vi.img)

    # ---- assembly (part with ghosted context)
    assembly_paths: dict[str, Path] = {}
    assembly_panels: list[Panel] = []
    if ghost is not None:
        for v in ("top", "front", "iso"):
            vi = render_view(mesh, v, scale, margin_px=60, ghost=ghost)
            draw_axes_and_label(vi, f"ASSEMBLY {VIEW_LABELS[v]} — context ghosted")
            p = views_dir / f"iter_{iteration:02d}_assembly_{v}.png"
            cv2.imwrite(str(p), vi.img)
            assembly_paths[v] = p
            assembly_panels.append(Panel(f"ASSEMBLY — {VIEW_LABELS[v]} (context in light grey)", vi.img))

    # ---- tables
    table, status = _key_dims_table(report)
    notes = _notes(report)
    subtitle = f"{name} · iteration {iteration} · units mm · scale {scale:.2f} px/mm (sections {sec_scale:.2f}) · third-angle · dimensions measured from the exported mesh"

    panels = [Panel(VIEW_LABELS[v], view_imgs[v].img) for v in ("top", "iso", "front", "right", "bottom", "left", "back")]
    sheet = compose_sheet(panels, columns=2, title=f"{name.upper()} — VIEWS", subtitle=subtitle, table=table, table_status=status, notes=notes)
    sheet_path = out_dir / f"iter_{iteration:02d}_sheet.png"
    sheet.save(sheet_path)

    sections_path = None
    if section_panels or assembly_panels:
        sheet2 = compose_sheet(section_panels + assembly_panels, columns=2 if len(section_panels + assembly_panels) > 1 else 1,
                               title=f"{name.upper()} — SECTIONS & ASSEMBLY", subtitle=subtitle, table=table, table_status=status, notes=notes)
        sections_path = out_dir / f"iter_{iteration:02d}_sections.png"
        sheet2.save(sections_path)

    res = BlueprintResult(sheet_path, sections_path, view_paths, section_paths, assembly_paths, scale)
    (out_dir / f"iter_{iteration:02d}_blueprint.json").write_text(json.dumps(res.to_dict(), indent=2))
    return res


# ---- helpers ----------------------------------------------------------------------------------------

def _label_for(item) -> str:
    tgt = item.target
    if isinstance(tgt, (int, float)):
        tol = f" ±{item.tol:g}" if item.tol is not None else ""
        want = f"{tgt:g}{tol}"
    else:
        want = str(tgt) if tgt is not None else ""
    meas = f"{item.measured:.2f}" if isinstance(item.measured, (int, float)) else str(item.measured)
    mark = "✓" if item.passed else ("✗" if item.passed is False else "")
    name = item.id.split(".")[-1]
    return f"{name} {meas} [{want}] {mark}".replace("  ", " ")


def _section_annotations(mesh, report: CheckReport | None, plane_axis: str, at: float) -> list[dict]:
    anns: list[dict] = []
    if not report:
        return anns
    stack_h = 0
    stack_v = 0
    keep = [a for a in "xyz" if a != plane_axis]
    for it in report.items:
        a = it.annotate or {}
        if not a or a.get("plane_axis") != plane_axis or a.get("at") is None or abs(float(a["at"]) - at) > 1e-6:
            continue
        if a["type"] == "circle":
            anns.append({"type": "circle", "cx": a["cx"], "cy": a["cy"], "r": a["r"], "label": "Ø" + _label_for(it), "passed": it.passed,
                         "angle": [150, 210, 30, 330][len([x for x in anns if x["type"] == "circle"]) % 4]})
        elif a["type"] in ("hole_extent", "section_extent"):
            polys = G.section_polygons(mesh, plane_axis, at)
            poly = G._pick_polygon(polys, a.get("near"))
            if poly is None:
                continue
            ring = G._pick_hole(poly, a.get("near")) if a["type"] == "hole_extent" else poly.exterior
            if ring is None:
                continue
            coords = np.asarray(ring.coords)
            col = keep.index(a["axis"])
            other = 1 - col
            lo_i, hi_i = coords[:, col].argmin(), coords[:, col].argmax()
            mid = float(coords[:, other].mean())
            p0 = [0.0, 0.0]
            p1 = [0.0, 0.0]
            p0[col], p1[col] = float(coords[lo_i, col]), float(coords[hi_i, col])
            p0[other] = p1[other] = mid
            horiz = col == 0
            bb = [float(coords[:, 0].min()), float(coords[:, 1].min()), float(coords[:, 0].max()), float(coords[:, 1].max())]
            ob = list(poly.bounds)
            anns.append({"type": a["type"], "p0": p0, "p1": p1, "bbox": bb, "outer_bbox": ob, "axis_is_horizontal": horiz,
                         "label": _label_for(it), "passed": it.passed, "stack": stack_h if horiz else stack_v})
            if horiz:
                stack_h += 1
            else:
                stack_v += 1
        elif a["type"] == "holes":
            anns.append({"type": "holes", "holes": [{"x": h[0], "y": h[1], "d": h[2]} for h in (it.measured or [])], "passed": it.passed})
    return anns


def _draw_extent_annotations(vi: raster.ViewImage, mesh, report: CheckReport | None, view: str) -> None:
    """`extent` recipes: x on the front view (horizontal), y on the top view (vertical), z on the front view (vertical)."""
    if not report:
        return
    from kintsugi.render.sheet import dim_horizontal, dim_vertical
    stack_h, stack_v = 1, 1
    for it in report.items:
        a = it.annotate or {}
        if a.get("type") != "extent":
            continue
        axis = a.get("axis", "z")
        if (axis in ("x", "z") and view != "front") or (axis == "y" and view != "top"):
            continue
        v = mesh.vertices
        if a.get("region"):
            lo, hi = np.asarray(a["region"][0], float), np.asarray(a["region"][1], float)
            mask = np.all((v >= lo - 1e-9) & (v <= hi + 1e-9), axis=1)
            v = v[mask]
            if len(v) == 0:
                continue
        col = G.AXIS_INDEX[axis]
        lo_w, hi_w = v[:, col].min(), v[:, col].max()
        # end points in world: take the other coords from the extreme vertices' centroid for placement
        base = v.mean(axis=0)
        p0w, p1w = base.copy(), base.copy()
        p0w[col], p1w[col] = lo_w, hi_w
        p0, p1 = vi.to_px(np.array([p0w, p1w]))
        color = raster.PASS if it.passed else (raster.FAIL if it.passed is False else raster.DIM)
        label = _label_for(it)
        allv = vi.to_px(mesh.vertices)
        if axis == "x":
            y_obj = allv[:, 1].max()
            dim_horizontal(vi.img, p0[0], p1[0], y_obj, y_obj + 30 + 22 * stack_h, label, color)
            stack_h += 1
        else:
            x_obj = allv[:, 0].max()
            dim_vertical(vi.img, min(p0[1], p1[1]), max(p0[1], p1[1]), x_obj, x_obj + 30 + 22 * stack_v, label, color)
            stack_v += 1


def _mark_cutting_plane(view_imgs: dict[str, raster.ViewImage], plane_axis: str, at: float, letter: str) -> None:
    """Draw the cutting-plane line (dash-dot) with letters on the view where the plane appears edge-on."""
    from kintsugi.render.sheet import _dashed_line_dd, _put_text
    target = {"z": "front", "x": "top", "y": "top"}[plane_axis]
    vi = view_imgs.get(target)
    if vi is None:
        return
    H, W = vi.img.shape[:2]
    m = vi.margin
    x_l, x_r = max(6, m - 40), min(W - 6, W - m + 40)
    y_t, y_b = max(6, m - 40), min(H - 6, H - m + 40)
    if plane_axis == "z":
        y = vi.to_px(np.array([[0, 0, at]]))[0][1]
        _dashed_line_dd(vi.img, (x_l, int(y)), (x_r, int(y)), (40, 32, 24))
        _put_text(vi.img, letter, (x_l, int(y) - 4), 13, (40, 32, 24), bold=True, anchor="lb")
        _put_text(vi.img, letter, (x_r, int(y) - 4), 13, (40, 32, 24), bold=True, anchor="rb")
    elif plane_axis == "x":
        x = vi.to_px(np.array([[at, 0, 0]]))[0][0]
        _dashed_line_dd(vi.img, (int(x), y_t), (int(x), y_b), (40, 32, 24))
        _put_text(vi.img, letter, (int(x) + 4, y_t), 13, (40, 32, 24), bold=True, anchor="lt")
        _put_text(vi.img, letter, (int(x) + 4, y_b), 13, (40, 32, 24), bold=True, anchor="lb")
    else:
        y = vi.to_px(np.array([[0, at, 0]]))[0][1]
        _dashed_line_dd(vi.img, (x_l, int(y)), (x_r, int(y)), (40, 32, 24))
        _put_text(vi.img, letter, (x_l, int(y) - 4), 13, (40, 32, 24), bold=True, anchor="lb")
        _put_text(vi.img, letter, (x_r, int(y) - 4), 13, (40, 32, 24), bold=True, anchor="rb")


def _key_dims_table(report: CheckReport | None):
    if not report:
        return None, None
    rows, status = [], []
    for it in report.items:
        if it.kind == "info" and it.passed is None and not it.id.startswith("print."):
            continue
        tgt = it.target
        if isinstance(tgt, (int, float)):
            tgt_s = f"{tgt:g}"
        else:
            tgt_s = str(tgt) if tgt is not None else "—"
        meas = it.measured
        meas_s = f"{meas:.2f}" if isinstance(meas, (int, float)) and not isinstance(meas, bool) else str(meas)
        tol_s = f"±{it.tol:g}" if it.tol is not None else ""
        st = "PASS" if it.passed else ("FAIL" if it.passed is False else "info")
        rows.append([it.id, tgt_s, meas_s + (f" {it.unit}" if it.unit and it.unit not in ("",) else ""), tol_s, st, it.detail])
        status.append(it.passed)
    return rows, status


def _notes(report: CheckReport | None) -> list[str]:
    if not report:
        return []
    out = []
    s = report.stats
    if s:
        out.append(f"mesh: {s.get('triangles')} triangles, watertight={s.get('watertight')}, bodies={s.get('bodies')}, "
                   f"bbox {s['bbox']['size']} mm, volume {s.get('volume_mm3')} mm³")
    if report.walls:
        w = report.walls
        out.append(f"walls: min {w['min']:.2f} / p05 {w['p05']:.2f} / median {w['median']:.2f} mm (required {w['required']:.2f})")
    if report.printability:
        p = report.printability
        out.append(f"printability as modeled: overhang beyond 45° = {p['overhang_fraction']*100:.1f}% of area, bed contact {p['bed_contact_area']:.0f} mm², height {p['height']:.1f} mm"
                   + (f"; best orientation: {report.orientations[0]['name']}" if report.orientations else ""))
    return out
