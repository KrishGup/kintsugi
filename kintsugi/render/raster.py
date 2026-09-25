"""Software orthographic renderer for engineering views.

Painter's-algorithm fill through OpenCV with a per-triangle depth buffer, Lambert shading, and drafting-style
edges: visible silhouettes and creases solid, hidden creases dashed. Exact mm-per-pixel mapping so the sheet can
carry true dimension lines.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np
import trimesh

# View rotations: rows are camera axes (right, up, toward-viewer) expressed in world coordinates.
VIEWS: dict[str, np.ndarray] = {
    "front": np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float),   # from -Y: x right, z up
    "back": np.array([[-1, 0, 0], [0, 0, 1], [0, 1, 0]], float),    # from +Y
    "right": np.array([[0, 1, 0], [0, 0, 1], [1, 0, 0]], float),    # from +X: y right, z up
    "left": np.array([[0, -1, 0], [0, 0, 1], [-1, 0, 0]], float),   # from -X
    "top": np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], float),      # from +Z: x right, y up
    "bottom": np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1]], float), # from -Z
}


def _iso_matrix() -> np.ndarray:
    # Viewer at (1, -1, 1) direction (front-right-top), z up on screen.
    toward = np.array([1.0, -1.0, 1.0])
    toward /= np.linalg.norm(toward)
    up_hint = np.array([0.0, 0.0, 1.0])
    right = np.cross(up_hint, toward)
    right /= np.linalg.norm(right)
    up = np.cross(toward, right)
    return np.vstack([right, up, toward])


VIEWS["iso"] = _iso_matrix()
VIEW_LABELS = {"front": "FRONT (from −Y)", "back": "BACK (from +Y)", "right": "RIGHT (from +X)", "left": "LEFT (from −X)",
               "top": "TOP (from +Z)", "bottom": "BOTTOM (from −Z)", "iso": "ISOMETRIC (front-right-top)"}
VIEW_AXES = {"front": ("X", "Z"), "back": ("−X", "Z"), "right": ("Y", "Z"), "left": ("−Y", "Z"), "top": ("X", "Y"),
             "bottom": ("X", "−Y"), "iso": ("", "")}

# Palette (BGR for OpenCV)
BG = (252, 251, 250)
FACE = (205, 200, 192)
FACE_TINT = (228, 214, 198)  # slightly blue tint in BGR -> warm? keep neutral-blue
EDGE = (40, 32, 24)
HIDDEN = (120, 110, 100)
GRID = (236, 233, 229)
GRID_MAJOR = (222, 218, 212)
DIM = (168, 79, 31)  # blueprint blue in BGR
PASS = (70, 122, 31)
FAIL = (42, 50, 184)
GHOST = (215, 205, 196)


@dataclass
class ViewImage:
    name: str
    img: np.ndarray  # BGR uint8
    depth: np.ndarray  # float32, +inf where empty; larger = closer to viewer
    scale: float  # px per mm
    origin: tuple[float, float]  # camera-space (x_min, y_max) mapped to pixel (margin, margin)
    margin: int
    R: np.ndarray  # 3x3 world->camera
    bounds_cam: np.ndarray  # [[xmin,ymin],[xmax,ymax]] in camera space (mm)
    extras: dict = field(default_factory=dict)

    def to_px(self, pts_world: np.ndarray) -> np.ndarray:
        """World points (N,3) -> pixel coords (N,2) as floats."""
        cam = np.asarray(pts_world, float) @ self.R.T
        return self.cam_to_px(cam[:, :2])

    def cam_to_px(self, cam_xy: np.ndarray) -> np.ndarray:
        cam_xy = np.asarray(cam_xy, float)
        x0, y1 = self.origin
        px = (cam_xy[:, 0] - x0) * self.scale + self.margin
        py = (y1 - cam_xy[:, 1]) * self.scale + self.margin
        return np.column_stack([px, py])

    @property
    def size(self) -> tuple[int, int]:
        return self.img.shape[1], self.img.shape[0]


def _edge_classification(mesh: trimesh.Trimesh, R: np.ndarray, crease_deg: float = 30.0):
    """Return (silhouette_edges, crease_edges, boundary_edges) as (E,2) vertex index arrays."""
    normals_cam = mesh.face_normals @ R.T
    front = normals_cam[:, 2] > 0
    fa = mesh.face_adjacency  # (E,2) faces
    if len(fa) == 0:
        return np.zeros((0, 2), int), np.zeros((0, 2), int), np.zeros((0, 2), int)
    edges = mesh.face_adjacency_edges  # (E,2) vertex indices
    angles = mesh.face_adjacency_angles
    f0, f1 = fa[:, 0], fa[:, 1]
    sil = front[f0] != front[f1]
    crease = (~sil) & (angles > math.radians(crease_deg)) & (front[f0] | front[f1])
    crease_hidden = (~sil) & (angles > math.radians(crease_deg)) & ~(front[f0] | front[f1])
    # boundary edges (open meshes)
    boundary = np.zeros((0, 2), int)
    try:
        ue = mesh.edges_unique
        counts = np.bincount(mesh.edges_unique_inverse, minlength=len(ue))
        boundary = ue[counts == 1]
    except Exception:
        pass
    return edges[sil], np.vstack([edges[crease], edges[crease_hidden]]), boundary


def render_view(
    mesh: trimesh.Trimesh, view: str, px_per_mm: float = 6.0, margin_px: int = 60, *,
    bounds_cam: np.ndarray | None = None, crease_deg: float = 30.0, hidden_lines: bool = True,
    shade: bool = True, ghost: trimesh.Trimesh | None = None, grid_mm: float = 10.0, edge_px: int = 2,
) -> ViewImage:
    R = VIEWS[view]
    V = mesh.vertices @ R.T  # camera coords
    if bounds_cam is None:
        lo, hi = V[:, :2].min(axis=0), V[:, :2].max(axis=0)
        if ghost is not None:
            gv = ghost.vertices @ R.T
            lo = np.minimum(lo, gv[:, :2].min(axis=0))
            hi = np.maximum(hi, gv[:, :2].max(axis=0))
        bounds_cam = np.array([lo, hi])
    lo, hi = bounds_cam
    W = int(math.ceil((hi[0] - lo[0]) * px_per_mm)) + 2 * margin_px
    H = int(math.ceil((hi[1] - lo[1]) * px_per_mm)) + 2 * margin_px
    W, H = max(W, 64), max(H, 64)
    img = np.full((H, W, 3), BG, np.uint8)
    depth = np.full((H, W), -np.inf, np.float32)
    vi = ViewImage(view, img, depth, px_per_mm, (float(lo[0]), float(hi[1])), margin_px, R, bounds_cam)

    _draw_grid(vi, grid_mm)

    if ghost is not None:
        _fill_mesh(vi, ghost, R, color=GHOST, shade=False, write_depth=False, alpha=0.5)

    _fill_mesh(vi, mesh, R, color=FACE, shade=shade, write_depth=True)
    _draw_edges(vi, mesh, R, crease_deg=crease_deg, hidden_lines=hidden_lines, edge_px=edge_px)
    return vi


def _draw_grid(vi: ViewImage, grid_mm: float) -> None:
    if grid_mm <= 0:
        return
    H, W = vi.img.shape[:2]
    lo = vi.bounds_cam[0]
    hi = vi.bounds_cam[1]
    x = math.floor(lo[0] / grid_mm) * grid_mm
    while x <= hi[0] + grid_mm:
        px = int(round((x - vi.origin[0]) * vi.scale + vi.margin))
        if 0 <= px < W:
            cv2.line(vi.img, (px, 0), (px, H - 1), GRID_MAJOR if abs(x % (grid_mm * 5)) < 1e-6 else GRID, 1)
        x += grid_mm
    y = math.floor(lo[1] / grid_mm) * grid_mm
    while y <= hi[1] + grid_mm:
        py = int(round((vi.origin[1] - y) * vi.scale + vi.margin))
        if 0 <= py < H:
            cv2.line(vi.img, (0, py), (W - 1, py), GRID_MAJOR if abs(y % (grid_mm * 5)) < 1e-6 else GRID, 1)
        y += grid_mm


def _fill_mesh(vi: ViewImage, mesh: trimesh.Trimesh, R: np.ndarray, *, color, shade: bool, write_depth: bool,
               alpha: float = 1.0, chunk_px: int = 3_000_000) -> None:
    """Vectorized z-buffer rasterizer: exact per-pixel depth, flat Lambert shading per face."""
    V = mesh.vertices @ R.T
    P = vi.cam_to_px(V[:, :2])
    H, W = vi.depth.shape
    faces = mesh.faces
    normals_cam = mesh.face_normals @ R.T
    front = normals_cam[:, 2] > 1e-9
    faces = faces[front]
    normals_cam = normals_cam[front]
    if len(faces) == 0:
        return
    tri = P[faces]  # (F,3,2)
    triz = V[faces][:, :, 2]  # (F,3)
    light = np.array([-0.35, 0.55, 1.0])
    light /= np.linalg.norm(light)
    base = np.array(color, float)
    if shade:
        lam = np.clip(normals_cam @ light, 0, 1)
        k = 0.45 + 0.55 * lam
        cols = np.clip(base[None, :] * k[:, None] + 18, 0, 255).astype(np.uint8)
    else:
        cols = np.tile(base.astype(np.uint8), (len(faces), 1))

    x0 = np.clip(np.floor(tri[:, :, 0].min(axis=1)).astype(int), 0, W - 1)
    x1 = np.clip(np.ceil(tri[:, :, 0].max(axis=1)).astype(int), 0, W - 1)
    y0 = np.clip(np.floor(tri[:, :, 1].min(axis=1)).astype(int), 0, H - 1)
    y1 = np.clip(np.ceil(tri[:, :, 1].max(axis=1)).astype(int), 0, H - 1)
    bw = x1 - x0 + 1
    bh = y1 - y0 + 1
    area = bw * bh
    ok = area > 0
    idx_all = np.nonzero(ok)[0]
    if len(idx_all) == 0:
        return
    # order triangles so chunk boundaries do not matter (z-buffer is order independent)
    csum = np.cumsum(area[idx_all])
    start = 0
    overlay = vi.img.copy() if alpha < 1.0 else vi.img
    depth_scratch = vi.depth if write_depth else np.full_like(vi.depth, -np.inf)
    while start < len(idx_all):
        end = int(np.searchsorted(csum, csum[start - 1] + chunk_px if start > 0 else chunk_px, side="right"))
        end = max(end, start + 1)
        idx = idx_all[start:end]
        _raster_chunk(overlay, depth_scratch, tri[idx], triz[idx], cols[idx], x0[idx], y0[idx], bw[idx], area[idx], write_depth)
        start = end
    if alpha < 1.0:
        cv2.addWeighted(overlay, alpha, vi.img, 1 - alpha, 0, dst=vi.img)


def _raster_chunk(img, depth, tri, triz, cols, x0, y0, bw, area, write_depth: bool) -> None:
    n = len(tri)
    total = int(area.sum())
    rep = np.repeat(np.arange(n), area)
    offsets = np.cumsum(area) - area
    k = np.arange(total) - np.repeat(offsets, area)
    px = x0[rep] + (k % bw[rep])
    py = y0[rep] + (k // bw[rep])
    cx = px + 0.5
    cy = py + 0.5
    A, B, C = tri[rep, 0], tri[rep, 1], tri[rep, 2]
    # edge functions
    w0 = (B[:, 0] - A[:, 0]) * (cy - A[:, 1]) - (B[:, 1] - A[:, 1]) * (cx - A[:, 0])  # AB vs P
    w1 = (C[:, 0] - B[:, 0]) * (cy - B[:, 1]) - (C[:, 1] - B[:, 1]) * (cx - B[:, 0])  # BC vs P
    w2 = (A[:, 0] - C[:, 0]) * (cy - C[:, 1]) - (A[:, 1] - C[:, 1]) * (cx - C[:, 0])  # CA vs P
    areaT = (B[:, 0] - A[:, 0]) * (C[:, 1] - A[:, 1]) - (B[:, 1] - A[:, 1]) * (C[:, 0] - A[:, 0])
    eps = 1e-9
    pos = areaT > 0
    inside = np.where(pos, (w0 >= -eps) & (w1 >= -eps) & (w2 >= -eps), (w0 <= eps) & (w1 <= eps) & (w2 <= eps))
    inside &= np.abs(areaT) > 1e-12
    if not inside.any():
        return
    sel = np.nonzero(inside)[0]
    rep, px, py = rep[sel], px[sel], py[sel]
    # barycentric weights: w1 ~ A, w2 ~ B, w0 ~ C
    aT = areaT[sel]
    la = w1[sel] / aT
    lb = w2[sel] / aT
    lc = w0[sel] / aT
    z = la * triz[rep, 0] + lb * triz[rep, 1] + lc * triz[rep, 2]
    np.maximum.at(depth, (py, px), z.astype(np.float32))
    win = depth[py, px] <= z.astype(np.float32) + 1e-6
    img[py[win], px[win]] = cols[rep[win]]


def _draw_edges(vi: ViewImage, mesh: trimesh.Trimesh, R: np.ndarray, *, crease_deg: float, hidden_lines: bool,
                edge_px: int) -> None:
    sil, crease, boundary = _edge_classification(mesh, R, crease_deg)
    V = mesh.vertices @ R.T
    P = vi.cam_to_px(V[:, :2])
    H, W = vi.depth.shape

    def draw_set(edges: np.ndarray, color, dashed_hidden: bool):
        if len(edges) == 0:
            return
        for a, b in edges:
            p0, p1 = P[a], P[b]
            z0, z1 = V[a, 2], V[b, 2]
            length = float(np.hypot(*(p1 - p0)))
            n = max(2, int(length / 3.0) + 1)
            t = np.linspace(0, 1, n)
            xs = p0[0] + (p1[0] - p0[0]) * t
            ys = p0[1] + (p1[1] - p0[1]) * t
            zs = z0 + (z1 - z0) * t
            xi = np.clip(np.round(xs).astype(int), 0, W - 1)
            yi = np.clip(np.round(ys).astype(int), 0, H - 1)
            dbuf = vi.depth[yi, xi]
            bias = 0.35 + 0.02 * abs(z1 - z0)
            visible = zs >= dbuf - bias
            # runs
            runs = _runs(visible)
            for vis, i0, i1 in runs:
                q0 = (int(round(xs[i0])), int(round(ys[i0])))
                q1 = (int(round(xs[i1])), int(round(ys[i1])))
                if vis:
                    cv2.line(vi.img, q0, q1, color, edge_px, cv2.LINE_AA)
                elif dashed_hidden and hidden_lines:
                    _dashed_line(vi.img, q0, q1, HIDDEN, 1, dash=6, gap=4)

    draw_set(crease, EDGE, dashed_hidden=True)
    draw_set(sil, EDGE, dashed_hidden=False)
    draw_set(boundary, EDGE, dashed_hidden=False)


def _runs(mask: np.ndarray):
    out = []
    if len(mask) == 0:
        return out
    start = 0
    cur = bool(mask[0])
    for i in range(1, len(mask)):
        if bool(mask[i]) != cur:
            out.append((cur, start, i))
            start = i
            cur = bool(mask[i])
    out.append((cur, start, len(mask) - 1))
    return out


def _dashed_line(img, p0, p1, color, thickness=1, dash=6, gap=4):
    x0, y0 = p0
    x1, y1 = p1
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 1:
        return
    dx, dy = (x1 - x0) / length, (y1 - y0) / length
    s = 0.0
    while s < length:
        e = min(s + dash, length)
        cv2.line(img, (int(round(x0 + dx * s)), int(round(y0 + dy * s))), (int(round(x0 + dx * e)), int(round(y0 + dy * e))),
                 color, thickness, cv2.LINE_AA)
        s = e + gap


def shared_bounds(mesh: trimesh.Trimesh, views: list[str], ghost: trimesh.Trimesh | None = None) -> dict[str, np.ndarray]:
    """Per-view camera-space bounds; all orthographic views share the same scale so sizes are comparable."""
    out = {}
    for v in views:
        R = VIEWS[v]
        V = mesh.vertices @ R.T
        lo, hi = V[:, :2].min(axis=0), V[:, :2].max(axis=0)
        if ghost is not None:
            gv = ghost.vertices @ R.T
            lo = np.minimum(lo, gv[:, :2].min(axis=0))
            hi = np.maximum(hi, gv[:, :2].max(axis=0))
        out[v] = np.array([lo, hi])
    return out


def pick_scale(mesh: trimesh.Trimesh, target_px: float = 640.0, max_px_per_mm: float = 10.0) -> float:
    ext = float(max(mesh.extents.max(), 1e-6))
    return float(min(max_px_per_mm, target_px / ext))
