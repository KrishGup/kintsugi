"""Blueprint sheets: orthographic views, sections with hatching, mesh-derived dimension lines, title block."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

import cv2
import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import LineString, MultiLineString, Polygon

from kintsugi.checks import geometry as G
from kintsugi.render import raster
from kintsugi.render.raster import VIEWS, ViewImage, render_view

# ---- fonts -----------------------------------------------------------------------------------------

def _font_path(bold: bool = False, mono: bool = False) -> str | None:
    try:
        import matplotlib
        d = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")
        name = ("DejaVuSansMono" if mono else "DejaVuSans") + ("-Bold" if bold else "") + ".ttf"
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    except Exception:
        pass
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
        if os.path.exists(p):
            return p
    return None


def font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    p = _font_path(bold, mono)
    if p:
        return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# ---- drawing primitives on cv2 images ---------------------------------------------------------------

def _put_text(img: np.ndarray, text: str, xy: tuple[int, int], size: int = 14, color=(40, 32, 24), bold=False, mono=True,
              anchor: str = "la", bg: bool = True) -> tuple[int, int, int, int]:
    """Draw text with PIL onto a BGR cv2 image. Returns the text bbox (x0,y0,x1,y1)."""
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    f = font(size, bold, mono)
    bbox = d.textbbox(xy, text, font=f, anchor=anchor)
    # keep the label inside the image
    W, H = pil.size
    dx = dy = 0
    if bbox[0] < 3:
        dx = 3 - bbox[0]
    elif bbox[2] > W - 3:
        dx = W - 3 - bbox[2]
    if bbox[1] < 3:
        dy = 3 - bbox[1]
    elif bbox[3] > H - 3:
        dy = H - 3 - bbox[3]
    if dx or dy:
        xy = (xy[0] + dx, xy[1] + dy)
        bbox = d.textbbox(xy, text, font=f, anchor=anchor)
    if bg:
        d.rectangle((bbox[0] - 2, bbox[1] - 1, bbox[2] + 2, bbox[3] + 1), fill=(252, 251, 250))
    d.text(xy, text, font=f, fill=(color[2], color[1], color[0]), anchor=anchor)
    img[:, :, :] = cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)
    return bbox


def _arrow(img, p0, p1, color, thickness=1):
    p0 = (int(round(p0[0])), int(round(p0[1])))
    p1 = (int(round(p1[0])), int(round(p1[1])))
    length = max(1.0, math.hypot(p1[0] - p0[0], p1[1] - p0[1]))
    tip = min(0.45, 9.0 / length)
    cv2.arrowedLine(img, p0, p1, color, thickness, cv2.LINE_AA, tipLength=tip)
    cv2.arrowedLine(img, p1, p0, color, thickness, cv2.LINE_AA, tipLength=tip)


def dim_horizontal(img, x0: float, x1: float, y_obj: float, y_line: float, label: str, color, *, ext: bool = True):
    """Horizontal dimension between x0..x1 (px), object edge at y_obj, dimension line at y_line."""
    if ext:
        for x in (x0, x1):
            cv2.line(img, (int(x), int(y_obj)), (int(x), int(y_line + (6 if y_line > y_obj else -6))), color, 1, cv2.LINE_AA)
    _arrow(img, (x0, y_line), (x1, y_line), color)
    _put_text(img, label, (int((x0 + x1) / 2), int(y_line - 4 if y_line >= y_obj else y_line + 4)), 13, color,
              anchor="mb" if y_line >= y_obj else "mt")


def dim_vertical(img, y0: float, y1: float, x_obj: float, x_line: float, label: str, color, *, ext: bool = True,
                 text: str = "side"):
    if ext:
        for y in (y0, y1):
            cv2.line(img, (int(x_obj), int(y)), (int(x_line + (6 if x_line > x_obj else -6)), int(y)), color, 1, cv2.LINE_AA)
    _arrow(img, (x_line, y0), (x_line, y1), color)
    W = img.shape[1]
    est_w = 7.5 * len(label)
    if text == "above" or x_line + 6 + est_w > W - 4:
        _put_text(img, label, (int(x_line), int(min(y0, y1) - 6)), 13, color, anchor="mb")
    else:
        _put_text(img, label, (int(x_line + 5 if x_line >= x_obj else x_line - 5), int((y0 + y1) / 2)), 13, color,
                  anchor="lm" if x_line >= x_obj else "rm")


# ---- views with overall dimensions ------------------------------------------------------------------

def annotate_overall(vi: ViewImage, mesh: trimesh.Trimesh) -> None:
    """Overall extents of the mesh in this view, drawn as dimension lines in the margin."""
    if vi.name == "iso":
        return
    V = mesh.vertices @ vi.R.T
    lo, hi = V[:, :2].min(axis=0), V[:, :2].max(axis=0)
    p_lo = vi.cam_to_px(np.array([[lo[0], lo[1]]]))[0]
    p_hi = vi.cam_to_px(np.array([[hi[0], hi[1]]]))[0]
    x0, x1 = p_lo[0], p_hi[0]
    ytop, ybot = p_hi[1], p_lo[1]
    ax_h, ax_v = raster.VIEW_AXES[vi.name]
    dim_horizontal(vi.img, x0, x1, ybot, ybot + 30, f"{hi[0]-lo[0]:.2f} ({ax_h})", raster.DIM)
    dim_vertical(vi.img, ytop, ybot, x1, x1 + 30, f"{hi[1]-lo[1]:.2f} ({ax_v})", raster.DIM)


def draw_axes_and_label(vi: ViewImage, label: str) -> None:
    H, W = vi.img.shape[:2]
    _put_text(vi.img, label, (8, 6), 15, (40, 32, 24), bold=True, mono=False)
    ax_h, ax_v = raster.VIEW_AXES.get(vi.name, ("", ""))
    if ax_h:
        ox, oy = 14, H - 14
        cv2.arrowedLine(vi.img, (ox, oy), (ox + 26, oy), (90, 80, 70), 1, cv2.LINE_AA, tipLength=0.3)
        cv2.arrowedLine(vi.img, (ox, oy), (ox, oy - 26), (90, 80, 70), 1, cv2.LINE_AA, tipLength=0.3)
        _put_text(vi.img, ax_h, (ox + 30, oy), 11, (90, 80, 70), anchor="lm", bg=False)
        _put_text(vi.img, ax_v, (ox, oy - 30), 11, (90, 80, 70), anchor="mb", bg=False)
    # scale bar 10 mm
    bx = W - 14 - int(10 * vi.scale)
    by = H - 12
    cv2.line(vi.img, (bx, by), (bx + int(10 * vi.scale), by), (40, 32, 24), 2)
    _put_text(vi.img, "10 mm", (bx + int(5 * vi.scale), by - 4), 11, (40, 32, 24), anchor="mb", bg=False)


# ---- sections ---------------------------------------------------------------------------------------

SECTION_VIEW = {"z": "top", "x": "right", "y": "front"}


def render_section(mesh: trimesh.Trimesh, plane_axis: str, at: float, px_per_mm: float, *, annotations: list[dict] | None = None,
                   margin_px: int = 70, bounds_cam: np.ndarray | None = None, ghost: trimesh.Trimesh | None = None) -> ViewImage:
    """Section view: the half of the part beyond the cutting plane, cut faces hatched, recipe dimensions drawn."""
    ai = G.AXIS_INDEX[plane_axis]
    normal = np.zeros(3)
    normal[ai] = 1.0
    origin = np.zeros(3)
    origin[ai] = at
    view = SECTION_VIEW[plane_axis]
    # keep the half away from the viewer: for z (viewer at +z) keep z <= at -> normal -z
    keep_normal = -normal if plane_axis in ("z", "x") else normal
    try:
        half = trimesh.intersections.slice_mesh_plane(mesh, plane_normal=keep_normal, plane_origin=origin, cap=True)
    except Exception:
        half = mesh
    if half is None or len(half.faces) == 0:
        half = mesh
    vi = render_view(half, view, px_per_mm, margin_px, bounds_cam=bounds_cam if bounds_cam is not None else _bounds_for(mesh, view, ghost),
                     hidden_lines=False, ghost=ghost)
    vi.name = f"section_{plane_axis}_{at:g}"
    vi.extras["view"] = view
    # hatch the cut face
    polys = G.section_polygons(mesh, plane_axis, at)
    for poly in polys:
        _hatch_polygon(vi, poly, plane_axis, at)
        _outline_polygon(vi, poly, plane_axis, at, (40, 32, 24), 2)
    for ann in annotations or []:
        _draw_annotation(vi, ann, plane_axis, at)
    return vi


def _bounds_for(mesh, view, ghost=None):
    R = VIEWS[view]
    V = mesh.vertices @ R.T
    lo, hi = V[:, :2].min(axis=0), V[:, :2].max(axis=0)
    if ghost is not None:
        gv = ghost.vertices @ R.T
        lo = np.minimum(lo, gv[:, :2].min(axis=0))
        hi = np.maximum(hi, gv[:, :2].max(axis=0))
    return np.array([lo, hi])


def _plane_to_world(pts2: np.ndarray, plane_axis: str, at: float) -> np.ndarray:
    pts2 = np.asarray(pts2, float)
    out = np.zeros((len(pts2), 3))
    keep = [a for a in "xyz" if a != plane_axis]
    out[:, G.AXIS_INDEX[keep[0]]] = pts2[:, 0]
    out[:, G.AXIS_INDEX[keep[1]]] = pts2[:, 1]
    out[:, G.AXIS_INDEX[plane_axis]] = at
    return out


def _hatch_polygon(vi: ViewImage, poly: Polygon, plane_axis: str, at: float, spacing_mm: float = 2.0) -> None:
    minx, miny, maxx, maxy = poly.bounds
    h = maxy - miny
    lines = []
    c = minx - h - spacing_mm
    while c < maxx + spacing_mm:
        lines.append(LineString([(c, miny - 1), (c + h + 2, maxy + 1)]))  # true 45° lines
        c += spacing_mm
    clipped = poly.intersection(MultiLineString(lines))
    segs = []
    if clipped.geom_type == "LineString":
        segs = [clipped]
    elif clipped.geom_type in ("MultiLineString", "GeometryCollection"):
        segs = [g for g in clipped.geoms if g.geom_type == "LineString"]
    for s in segs:
        pts = vi.to_px(_plane_to_world(np.asarray(s.coords), plane_axis, at))
        cv2.polylines(vi.img, [np.round(pts).astype(np.int32)], False, (120, 100, 80), 1, cv2.LINE_AA)


def _outline_polygon(vi: ViewImage, poly: Polygon, plane_axis: str, at: float, color, thickness: int) -> None:
    rings = [poly.exterior] + list(poly.interiors)
    for r in rings:
        pts = vi.to_px(_plane_to_world(np.asarray(r.coords), plane_axis, at))
        cv2.polylines(vi.img, [np.round(pts).astype(np.int32)], True, color, thickness, cv2.LINE_AA)


def _draw_annotation(vi: ViewImage, ann: dict, plane_axis: str, at: float) -> None:
    """ann: {type, label, passed, cx, cy, r, ...} from a check item's annotate + label/passed fields."""
    color = raster.PASS if ann.get("passed") else (raster.FAIL if ann.get("passed") is False else raster.DIM)
    label = ann.get("label", "")
    t = ann.get("type")
    if t == "circle" and ann.get("r"):
        c2 = np.array([[ann["cx"], ann["cy"]]])
        cpx = vi.to_px(_plane_to_world(c2, plane_axis, at))[0]
        rpx = ann["r"] * vi.scale
        cv2.circle(vi.img, (int(round(cpx[0])), int(round(cpx[1]))), int(round(rpx)), color, 1, cv2.LINE_AA)
        ang = math.radians(ann.get("angle", 30))
        p0 = (cpx[0] - rpx * math.cos(ang), cpx[1] + rpx * math.sin(ang))
        p1 = (cpx[0] + rpx * math.cos(ang), cpx[1] - rpx * math.sin(ang))
        _arrow(vi.img, p0, p1, color)
        # leader out past the circle, text outside the geometry
        lead = 16
        q = (p1[0] + lead * math.cos(ang), p1[1] - lead * math.sin(ang))
        cv2.line(vi.img, (int(p1[0]), int(p1[1])), (int(q[0]), int(q[1])), color, 1, cv2.LINE_AA)
        left = math.cos(ang) < 0
        _put_text(vi.img, label, (int(q[0] + (-4 if left else 4)), int(q[1])), 13, color, anchor="rm" if left else "lm")
        cv2.drawMarker(vi.img, (int(round(cpx[0])), int(round(cpx[1]))), color, cv2.MARKER_CROSS, 10, 1)
    elif t in ("hole_extent", "section_extent", "extent"):
        # the caller supplies the two end points and the feature's bbox in plane coordinates
        if "p0" in ann and "p1" in ann:
            p0 = vi.to_px(_plane_to_world(np.array([ann["p0"]]), plane_axis, at))[0]
            p1 = vi.to_px(_plane_to_world(np.array([ann["p1"]]), plane_axis, at))[0]
            bb = ann.get("outer_bbox") or ann.get("bbox")  # [minx, miny, maxx, maxy] in plane coords
            if ann.get("axis_is_horizontal", True):
                y_obj = vi.to_px(_plane_to_world(np.array([[bb[0], bb[3]]]), plane_axis, at))[0][1] if bb else min(p0[1], p1[1])
                y = y_obj - 22 - 20 * ann.get("stack", 0)
                dim_horizontal(vi.img, p0[0], p1[0], y_obj, y, label, color)
            else:
                x_obj = vi.to_px(_plane_to_world(np.array([[bb[2], bb[1]]]), plane_axis, at))[0][0] if bb else max(p0[0], p1[0])
                x = x_obj + 22 + 20 * ann.get("stack", 0)
                dim_vertical(vi.img, min(p0[1], p1[1]), max(p0[1], p1[1]), x_obj, x, label, color, text="above")
    elif t == "holes":
        for h in ann.get("holes", []):
            c = vi.to_px(_plane_to_world(np.array([[h["x"], h["y"]]]), plane_axis, at))[0]
            cv2.drawMarker(vi.img, (int(round(c[0])), int(round(c[1]))), color, cv2.MARKER_CROSS, 12, 1)
            _put_text(vi.img, f"Ø{h['d']:.2f} @({h['x']:.1f},{h['y']:.1f})", (int(c[0]) + 8, int(c[1]) + 8), 11, color)


# ---- composition ------------------------------------------------------------------------------------

@dataclass
class Panel:
    title: str
    img: np.ndarray  # BGR


def compose_sheet(panels: list[Panel], *, columns: int, title: str, subtitle: str, table: list[list[str]] | None,
                  table_status: list[bool | None] | None = None, notes: list[str] | None = None, max_width: int = 2200) -> Image.Image:
    """Grid of panels with captions, a title block and a key-dimensions table. Returns a PIL RGB image."""
    pad = 18
    cap_h = 26
    cols = max(1, columns)
    # size cells by max panel size per column/row
    rows = [panels[i:i + cols] for i in range(0, len(panels), cols)]
    col_w = [0] * cols
    row_h = []
    for r in rows:
        h = 0
        for j, p in enumerate(r):
            col_w[j] = max(col_w[j], p.img.shape[1])
            h = max(h, p.img.shape[0])
        row_h.append(h + cap_h)
    width = sum(col_w) + pad * (cols + 1)
    header_h = 64
    table_h = 0
    if table:
        table_h = 28 * (len(table) + 1) + 24
    notes_h = 0
    if notes:
        notes_h = 20 * len(notes) + 16
    height = header_h + sum(row_h) + pad * (len(rows) + 1) + table_h + notes_h + 24
    sheet = Image.new("RGB", (width, height), (252, 251, 250))
    d = ImageDraw.Draw(sheet)
    # header / title block
    d.rectangle((pad // 2, pad // 2, width - pad // 2, header_h - 4), outline=(40, 32, 24), width=2)
    d.text((pad + 6, pad // 2 + 8), title, font=font(22, bold=True), fill=(24, 33, 44))
    d.text((pad + 6, pad // 2 + 36), subtitle, font=font(13, mono=True), fill=(74, 85, 99))
    y = header_h + pad
    for r, rh in zip(rows, row_h):
        x = pad
        for j, p in enumerate(r):
            cell_w = col_w[j]
            # panel frame
            d.rectangle((x - 1, y - 1, x + cell_w + 1, y + rh - cap_h + 1), outline=(201, 208, 218), width=1)
            pil = Image.fromarray(cv2.cvtColor(p.img, cv2.COLOR_BGR2RGB))
            sheet.paste(pil, (x, y))
            d.text((x + 4, y + rh - cap_h + 5), p.title, font=font(14, bold=True), fill=(24, 33, 44))
            x += cell_w + pad
        y += rh + pad
    if table:
        _draw_table(d, table, table_status or [None] * len(table), pad, y, width - 2 * pad)
        y += table_h
    if notes:
        for n in notes:
            d.text((pad, y), n, font=font(13, mono=True), fill=(74, 85, 99))
            y += 20
    if sheet.width > max_width:
        ratio = max_width / sheet.width
        sheet = sheet.resize((max_width, int(sheet.height * ratio)), Image.LANCZOS)
    return sheet


def _draw_table(d: ImageDraw.ImageDraw, rows: list[list[str]], status: list[bool | None], x: int, y: int, w: int) -> None:
    head = ["dimension", "target", "measured", "tol", "status", "detail"]
    colw = [int(w * f) for f in (0.22, 0.12, 0.12, 0.08, 0.09, 0.37)]
    fh = font(13, bold=True)
    fm = font(13, mono=True)
    d.rectangle((x, y, x + w, y + 26), fill=(233, 237, 242), outline=(201, 208, 218))
    cx = x + 6
    for h, cw in zip(head, colw):
        d.text((cx, y + 5), h, font=fh, fill=(24, 33, 44))
        cx += cw
    y += 28
    for row, st in zip(rows, status):
        color = (31, 122, 70) if st else ((184, 50, 42) if st is False else (74, 85, 99))
        cx = x + 6
        for i, (cell, cw) in enumerate(zip(row, colw)):
            txt = str(cell)
            # truncate to fit
            while d.textlength(txt, font=fm) > cw - 10 and len(txt) > 3:
                txt = txt[:-2]
            d.text((cx, y + 5), txt, font=fm, fill=color if i in (2, 4) else (24, 33, 44))
            cx += cw
        d.line((x, y + 26, x + w, y + 26), fill=(225, 230, 236))
        y += 28


def _dashed_line_dd(img, p0, p1, color, thickness=1):
    """Dash-dot cutting-plane line."""
    x0, y0 = p0
    x1, y1 = p1
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 1:
        return
    dx, dy = (x1 - x0) / length, (y1 - y0) / length
    s = 0.0
    pattern = [(14, True), (5, False), (3, True), (5, False)]
    i = 0
    while s < length:
        seg, on = pattern[i % len(pattern)]
        e = min(s + seg, length)
        if on:
            cv2.line(img, (int(round(x0 + dx * s)), int(round(y0 + dy * s))), (int(round(x0 + dx * e)), int(round(y0 + dy * e))),
                     color, thickness, cv2.LINE_AA)
        s = e
        i += 1
