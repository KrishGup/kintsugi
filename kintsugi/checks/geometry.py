"""Mesh geometry helpers: sections, circle fits, extents, wall thickness, overhangs, interference."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import shapely
import trimesh
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import unary_union

AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def load_mesh(path) -> trimesh.Trimesh:
    m = trimesh.load(str(path), force="mesh", process=True)
    if not isinstance(m, trimesh.Trimesh):
        raise ValueError(f"not a triangle mesh: {path}")
    m.merge_vertices()
    m.remove_unreferenced_vertices()
    return m


# ---- sections --------------------------------------------------------------------------------------

def section_polygons(mesh: trimesh.Trimesh, plane_axis: str = "z", at: float = 0.0) -> list[Polygon]:
    """Cross-section of the mesh by an axis-aligned plane, as shapely polygons (with holes).

    Coordinates are the world coordinates of the two remaining axes, in axis order
    (plane z -> (x, y); plane y -> (x, z); plane x -> (y, z)).
    """
    ai = AXIS_INDEX[plane_axis]
    normal = np.zeros(3)
    normal[ai] = 1.0
    origin = np.zeros(3)
    origin[ai] = at
    sec = mesh.section(plane_origin=origin, plane_normal=normal)
    if sec is None:
        return []
    keep = [i for i in range(3) if i != ai]
    polys: list[Polygon] = []
    # Build closed loops from the section's discrete paths.
    for pts in sec.discrete:
        p2 = np.asarray(pts)[:, keep]
        if len(p2) < 3:
            continue
        ring = Polygon(p2)
        if not ring.is_valid:
            ring = ring.buffer(0)
        if ring.is_empty or ring.area < 1e-9:
            continue
        if isinstance(ring, MultiPolygon):
            polys.extend(g for g in ring.geoms if g.area > 1e-9)
        else:
            polys.append(ring)
    if not polys:
        return []
    # Nest loops: even-odd fill. Sort by area descending; a loop inside another is a hole (or an island inside a hole).
    polys.sort(key=lambda p: p.area, reverse=True)
    result: list[Polygon] = []
    depth = [0] * len(polys)
    parent = [-1] * len(polys)
    for i, p in enumerate(polys):
        for j in range(i - 1, -1, -1):
            if polys[j].contains(p.representative_point()):
                parent[i] = j
                depth[i] = depth[j] + 1
                break
    holes_of: dict[int, list[int]] = {}
    for i in range(len(polys)):
        if depth[i] % 2 == 1:
            holes_of.setdefault(parent[i], []).append(i)
    for i, p in enumerate(polys):
        if depth[i] % 2 == 0:
            shell = list(p.exterior.coords)
            holes = [list(polys[h].exterior.coords) for h in holes_of.get(i, [])]
            poly = Polygon(shell, holes)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if isinstance(poly, MultiPolygon):
                result.extend(list(poly.geoms))
            elif not poly.is_empty:
                result.append(poly)
    return result


def _pick_polygon(polys: list[Polygon], near: list[float] | None) -> Polygon | None:
    if not polys:
        return None
    if near is None:
        return max(polys, key=lambda p: p.area)
    pt = shapely.Point(near[0], near[1])
    return min(polys, key=lambda p: p.distance(pt) if not p.contains(pt) else 0.0)


def _pick_hole(poly: Polygon, near: list[float] | None):
    holes = list(poly.interiors)
    if not holes:
        return None
    if near is None:
        return max(holes, key=lambda h: Polygon(h).area)
    pt = shapely.Point(near[0], near[1])
    return min(holes, key=lambda h: Polygon(h).distance(pt) if not Polygon(h).contains(pt) else 0.0)


# ---- circle fit ------------------------------------------------------------------------------------

@dataclass
class CircleFit:
    cx: float
    cy: float
    r: float
    rms: float  # residual, mm
    n: int
    inlier_fraction: float = 1.0

    @property
    def d(self) -> float:
        return 2 * self.r


def fit_circle(points: np.ndarray) -> CircleFit:
    """Algebraic (Kasa) least-squares circle fit, refined with a few Gauss-Newton steps."""
    pts = np.asarray(points, dtype=float)
    if len(pts) < 3:
        raise ValueError("need at least 3 points")
    x, y = pts[:, 0], pts[:, 1]
    A = np.column_stack([x, y, np.ones_like(x)])
    b = x**2 + y**2
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = sol[0] / 2, sol[1] / 2
    r = math.sqrt(max(sol[2] + cx**2 + cy**2, 0))
    for _ in range(5):
        dx, dy = x - cx, y - cy
        di = np.sqrt(dx**2 + dy**2)
        di[di == 0] = 1e-12
        J = np.column_stack([-dx / di, -dy / di, -np.ones_like(di)])
        res = di - r
        step, *_ = np.linalg.lstsq(J, -res, rcond=None)
        cx, cy, r = cx + step[0], cy + step[1], r + step[2]
        if np.linalg.norm(step) < 1e-9:
            break
    dx, dy = x - cx, y - cy
    rms = float(np.sqrt(np.mean((np.sqrt(dx**2 + dy**2) - r) ** 2)))
    return CircleFit(float(cx), float(cy), float(r), rms, len(pts))


def fit_circle_robust(points: np.ndarray, tol: float = 0.08, iters: int = 300, seed: int = 0) -> CircleFit:
    """RANSAC circle fit: finds the arc most of the boundary agrees on, even when another feature
    merges into the loop (a ring with a handle attached). Falls back to the plain fit when everything is inlier."""
    pts = np.asarray(points, dtype=float)
    n = len(pts)
    plain = fit_circle(pts)
    if n < 12 or plain.rms <= tol:
        return plain
    rng = np.random.default_rng(seed)
    best_inliers = None
    best_count = 0
    for _ in range(iters):
        idx = rng.choice(n, 3, replace=False)
        p = pts[idx]
        # circumscribed circle of 3 points
        ax, ay = p[0]
        bx, by = p[1]
        cx_, cy_ = p[2]
        d = 2 * (ax * (by - cy_) + bx * (cy_ - ay) + cx_ * (ay - by))
        if abs(d) < 1e-9:
            continue
        ux = ((ax**2 + ay**2) * (by - cy_) + (bx**2 + by**2) * (cy_ - ay) + (cx_**2 + cy_**2) * (ay - by)) / d
        uy = ((ax**2 + ay**2) * (cx_ - bx) + (bx**2 + by**2) * (ax - cx_) + (cx_**2 + cy_**2) * (bx - ax)) / d
        r = math.hypot(ax - ux, ay - uy)
        if r < 0.2 or r > 1e4:
            continue
        di = np.hypot(pts[:, 0] - ux, pts[:, 1] - uy)
        inl = np.abs(di - r) <= tol
        c = int(inl.sum())
        if c > best_count:
            best_count, best_inliers = c, inl
            if c > 0.98 * n:
                break
    if best_inliers is None or best_count < max(6, 0.15 * n):
        return plain
    fit = fit_circle(pts[best_inliers])
    fit.inlier_fraction = best_count / n
    return fit


def circle_fit_inner(mesh, at: float, plane_axis: str = "z", near: list[float] | None = None) -> CircleFit | None:
    polys = section_polygons(mesh, plane_axis, at)
    poly = _pick_polygon(polys, near)
    if poly is None:
        return None
    hole = _pick_hole(poly, near)
    if hole is None:
        return None
    return fit_circle_robust(np.asarray(hole.coords)[:-1])


def circle_fit_outer(mesh, at: float, plane_axis: str = "z", near: list[float] | None = None) -> CircleFit | None:
    """Circle through the outer envelope of the section: boundary points that lie on the convex hull, so a ring cut
    by slits (tabs) or joined to another feature still measures its outer arc."""
    polys = section_polygons(mesh, plane_axis, at)
    if not polys:
        return None
    chosen = None
    if near is not None:
        pt = shapely.Point(near[0], near[1])
        inside = [p for p in polys if p.contains(pt)]
        chosen = inside[0] if inside else None
    group = [chosen] if chosen is not None else polys
    hull = unary_union(group).convex_hull
    ring = hull.exterior
    pts = np.vstack([np.asarray(p.exterior.coords)[:-1] for p in group])
    on_hull = np.array([ring.distance(shapely.Point(q)) < 1e-6 for q in pts])
    sel = pts[on_hull] if on_hull.sum() >= 6 else pts
    return fit_circle_robust(sel)


def hole_extent(mesh, at: float, axis: str, plane_axis: str = "z", near: list[float] | None = None) -> float | None:
    polys = section_polygons(mesh, plane_axis, at)
    poly = _pick_polygon(polys, near)
    if poly is None:
        return None
    hole = _pick_hole(poly, near)
    if hole is None:
        return None
    coords = np.asarray(hole.coords)
    keep = [a for a in "xyz" if a != plane_axis]
    col = keep.index(axis)
    return float(coords[:, col].max() - coords[:, col].min())


def section_extent(mesh, at: float, axis: str, plane_axis: str = "z", near: list[float] | None = None) -> float | None:
    polys = section_polygons(mesh, plane_axis, at)
    poly = _pick_polygon(polys, near)
    if poly is None:
        return None
    coords = np.asarray(poly.exterior.coords)
    keep = [a for a in "xyz" if a != plane_axis]
    col = keep.index(axis)
    return float(coords[:, col].max() - coords[:, col].min())


def notch_measure(mesh, at: float, plane_axis: str = "z", near: list[float] | None = None) -> dict | None:
    """A notch (open-sided hole, as in a snap-on clip): the concavity of the section polygon nearest `near`.

    Returns {mouth_width, hull_width, circle: CircleFit | None, depth, area}. `mouth_width` is the narrowest passage
    between the jaws (the gap the object must snap through), `hull_width` the straight-line span at the convex hull,
    `circle` a fit to the seat beyond the widest point of the cavity (a clean arc even for egg-shaped seats).
    """
    polys = section_polygons(mesh, plane_axis, at)
    poly = _pick_polygon(polys, near)
    if poly is None:
        return None
    hull = poly.convex_hull
    diff = hull.difference(poly)
    cands = [g for g in iter_polys(diff) if g.area > 0.05]
    if not cands:
        return None
    if near is not None:
        pt = shapely.Point(near[0], near[1])
        cav = min(cands, key=lambda g: g.distance(pt) if not g.contains(pt) else 0.0)
    else:
        cav = max(cands, key=lambda g: g.area)
    hull_ring = hull.exterior
    pts = np.asarray(cav.exterior.coords)[:-1]
    on_hull = np.array([hull_ring.distance(shapely.Point(p)) < 1e-6 for p in pts])
    mouth_pts = pts[on_hull]
    if len(mouth_pts) < 2:
        return None
    # mouth line a-b (extreme hull points), inward normal n
    d = mouth_pts[:, None, :] - mouth_pts[None, :, :]
    i, j = np.unravel_index(np.argmax((d ** 2).sum(-1)), (len(mouth_pts), len(mouth_pts)))
    a, b = mouth_pts[i], mouth_pts[j]
    ab = b - a
    L = float(np.linalg.norm(ab)) + 1e-12
    u = ab / L
    n = np.array([-u[1], u[0]])
    cen = np.asarray(cav.centroid.coords)[0]
    if (cen - a) @ n < 0:
        n = -n
    depth = float(((pts - a) @ n).max())
    # width profile along the depth
    widths = []
    ts = np.arange(0.0, depth + 1e-9, max(depth / 200.0, 0.02))
    for t in ts:
        p0 = a + n * t - u * L
        p1 = a + n * t + u * L
        chord = cav.intersection(LineString([p0, p1]))
        widths.append(float(chord.length) if not chord.is_empty else 0.0)
    widths = np.asarray(widths)
    k_max = int(np.argmax(widths)) if len(widths) else 0
    throat = float(widths[: k_max + 1].min()) if k_max >= 0 and len(widths) else L
    seat_pts = pts[(~on_hull) & (((pts - a) @ n) > ts[k_max] - 1e-6)] if len(ts) else pts[~on_hull]
    circle = None
    if len(seat_pts) >= 6:
        try:
            circle = fit_circle_robust(seat_pts, tol=0.08)
        except ValueError:
            circle = None
    return {"mouth_width": throat, "hull_width": L, "circle": circle, "depth": depth, "area": float(cav.area),
            "widest_depth": float(ts[k_max]) if len(ts) else 0.0}


def gap_extent(mesh, at: float, axis: str, plane_axis: str = "z", near: list[float] | None = None) -> float | None:
    """Free distance across empty space: the length of the line through `near` along `axis`, in the section plane at
    `at`, between the part's boundaries (clipped to the part's bounding box). Measures a slot width between two jaw
    faces, a bore depth along its axis, a channel opening — anything that is a gap rather than a solid."""
    polys = section_polygons(mesh, plane_axis, at)
    if not polys:
        return None
    keep = [a for a in "xyz" if a != plane_axis]
    col = keep.index(axis)
    lo, hi = mesh.bounds
    lo2 = np.array([lo[AXIS_INDEX[keep[0]]], lo[AXIS_INDEX[keep[1]]]])
    hi2 = np.array([hi[AXIS_INDEX[keep[0]]], hi[AXIS_INDEX[keep[1]]]])
    if near is None:
        near = list((lo2 + hi2) / 2)
    p = np.array(near, float)
    a = p.copy()
    b = p.copy()
    a[col] = lo2[col] - 1e-6
    b[col] = hi2[col] + 1e-6
    line = LineString([a, b])
    solid = unary_union(polys)
    free = line.difference(solid)
    pt = shapely.Point(p)
    pieces = [g for g in (free.geoms if hasattr(free, "geoms") else [free]) if g.geom_type == "LineString" and not g.is_empty]
    for g in pieces:
        if g.distance(pt) < 1e-6:
            return float(g.length)
    return None


def hole_positions(mesh, at: float, plane_axis: str = "z") -> list[dict]:
    out = []
    for poly in section_polygons(mesh, plane_axis, at):
        for hole in poly.interiors:
            pts = np.asarray(hole.coords)[:-1]
            try:
                c = fit_circle(pts)
                out.append({"x": c.cx, "y": c.cy, "d": c.d, "rms": c.rms, "area": Polygon(hole).area})
            except ValueError:
                continue
    return out


def clip_to_region(mesh: trimesh.Trimesh, region: list[list[float]]) -> trimesh.Trimesh | None:
    """The part of the mesh inside an axis-aligned box (surface clipped by the six planes, not a vertex filter)."""
    lo, hi = np.asarray(region[0], float), np.asarray(region[1], float)
    m = mesh
    for i in range(3):
        for sign, bound in ((1.0, lo[i]), (-1.0, hi[i])):
            normal = np.zeros(3)
            normal[i] = sign
            origin = np.zeros(3)
            origin[i] = bound
            try:
                m = trimesh.intersections.slice_mesh_plane(m, plane_normal=normal, plane_origin=origin, cap=False)
            except Exception:
                return None
            if m is None or len(m.vertices) == 0:
                return None
    return m


def extent(mesh, axis: str, region: list[list[float]] | None = None) -> float | None:
    """Size along an axis; with `region`, of the geometry inside that box (clipped, so a feature that crosses the
    box boundary still measures correctly)."""
    v = mesh.vertices
    if region:
        clipped = clip_to_region(mesh, region)
        if clipped is None or len(clipped.vertices) == 0:
            return None
        v = clipped.vertices
    col = AXIS_INDEX[axis]
    return float(v[:, col].max() - v[:, col].min())


# ---- wall thickness --------------------------------------------------------------------------------

@dataclass
class WallStats:
    min: float
    p05: float
    median: float
    n: int
    thin_points: np.ndarray  # points where thickness < threshold (for the sheet)


def wall_thickness(mesh: trimesh.Trimesh, n_samples: int = 1500, threshold: float = 1.6,
                   region: list[list[float]] | None = None, seed: int = 0) -> WallStats | None:
    """Thickness along the inward normal at sampled surface points (ray cast to the far wall)."""
    if len(mesh.faces) == 0:
        return None
    rng = np.random.default_rng(seed)
    pts, fidx = trimesh.sample.sample_surface(mesh, n_samples, seed=int(rng.integers(0, 2**31 - 1)))
    normals = mesh.face_normals[fidx]
    if region:
        lo, hi = np.asarray(region[0], float), np.asarray(region[1], float)
        mask = np.all((pts >= lo) & (pts <= hi), axis=1)
        pts, normals = pts[mask], normals[mask]
        if len(pts) == 0:
            return None
    eps = 1e-3
    origins = pts - normals * eps
    dirs = -normals
    locs, ray_ids, _ = mesh.ray.intersects_location(origins, dirs, multiple_hits=False)
    if len(ray_ids) == 0:
        return None
    dist = np.linalg.norm(locs - origins[ray_ids], axis=1) + eps
    # ignore degenerate self-hits
    keep = dist > 1e-2
    dist, ray_ids = dist[keep], ray_ids[keep]
    if len(dist) == 0:
        return None
    thin = pts[ray_ids[dist < threshold]]
    return WallStats(min=float(dist.min()), p05=float(np.percentile(dist, 5)), median=float(np.median(dist)),
                     n=int(len(dist)), thin_points=thin)


# ---- printability ----------------------------------------------------------------------------------

@dataclass
class OverhangStats:
    overhang_area: float
    total_area: float
    fraction: float
    bed_contact_area: float
    centroid_height: float
    footprint_area: float


def overhang_stats(mesh: trimesh.Trimesh, angle_deg: float = 45.0, bed_eps: float = 0.05) -> OverhangStats:
    n = mesh.face_normals
    areas = mesh.area_faces
    zmin = float(mesh.bounds[0][2])
    fz = mesh.triangles[:, :, 2]
    on_bed = (np.abs(fz - zmin) < bed_eps).all(axis=1) & (n[:, 2] < -0.9)
    down = n[:, 2] < -math.sin(math.radians(angle_deg))
    # a face is an overhang if it faces down past the angle and is not on the bed
    over = down & ~on_bed
    total = float(areas.sum())
    footprint = 0.0
    try:
        footprint = float(unary_union([Polygon(t[:, :2]) for t in mesh.triangles if Polygon(t[:, :2]).area > 1e-9]).area)
    except Exception:
        pass
    return OverhangStats(
        overhang_area=float(areas[over].sum()), total_area=total, fraction=float(areas[over].sum() / total) if total else 0.0,
        bed_contact_area=float(areas[on_bed].sum()), centroid_height=float(mesh.center_mass[2] - zmin),
        footprint_area=footprint,
    )


def orientation_candidates() -> list[tuple[str, np.ndarray]]:
    R = []
    R.append(("as modeled (Z up)", np.eye(4)))
    R.append(("rotated 180° about X (upside down)", trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0])))
    R.append(("rotated +90° about X", trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0])))
    R.append(("rotated -90° about X", trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0])))
    R.append(("rotated +90° about Y", trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0])))
    R.append(("rotated -90° about Y", trimesh.transformations.rotation_matrix(-math.pi / 2, [0, 1, 0])))
    return R


def score_orientations(mesh: trimesh.Trimesh) -> list[dict]:
    out = []
    for name, M in orientation_candidates():
        m = mesh.copy()
        m.apply_transform(M)
        m.apply_translation([0, 0, -m.bounds[0][2]])
        st = overhang_stats(m)
        bbox = m.extents
        # score: lower is better. overhang fraction dominates; low centroid and large bed contact help.
        contact_ratio = st.bed_contact_area / max(st.footprint_area, 1e-6) if st.footprint_area else 0.0
        score = st.fraction * 10.0 + st.centroid_height / max(float(bbox[2]), 1e-6) * 1.0 - min(contact_ratio, 1.0) * 1.5
        out.append({
            "name": name, "score": round(float(score), 4), "overhang_fraction": round(st.fraction, 4),
            "bed_contact_area": round(st.bed_contact_area, 2), "footprint_area": round(st.footprint_area, 2),
            "height": round(float(bbox[2]), 3), "matrix": M.tolist(),
        })
    out.sort(key=lambda d: d["score"])
    return out


# ---- interference ----------------------------------------------------------------------------------

def context_mesh(shape: str, **kw) -> trimesh.Trimesh:
    at = np.asarray(kw.get("at") or [0, 0, 0], float)
    axis = kw.get("axis", "z")
    if shape == "cylinder":
        m = trimesh.creation.cylinder(radius=kw["d"] / 2, height=kw["h"], sections=96)
        m.apply_translation([0, 0, kw["h"] / 2])
    elif shape == "cone":
        m = trimesh.creation.cone(radius=1.0, height=1.0, sections=96)  # placeholder; build a frustum below
        m = _frustum(kw["d1"] / 2, kw["d2"] / 2, kw["h"])
    elif shape == "box":
        size = np.asarray(kw["size"], float)
        m = trimesh.creation.box(extents=size)
        m.apply_translation(size / 2)
    elif shape == "sphere":
        m = trimesh.creation.icosphere(subdivisions=3, radius=kw["d"] / 2)
    elif shape == "tube":
        outer = trimesh.creation.cylinder(radius=kw["d"] / 2, height=kw["h"], sections=96)
        inner = trimesh.creation.cylinder(radius=kw["di"] / 2, height=kw["h"] + 2, sections=96)
        m = trimesh.boolean.difference([outer, inner], engine="manifold")
        m.apply_translation([0, 0, kw["h"] / 2])
    else:
        raise ValueError(shape)
    if axis == "x":
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    elif axis == "y":
        m.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
    m.apply_translation(at)
    return m


def _frustum(r1: float, r2: float, h: float, sections: int = 96) -> trimesh.Trimesh:
    ang = np.linspace(0, 2 * math.pi, sections, endpoint=False)
    bottom = np.column_stack([r1 * np.cos(ang), r1 * np.sin(ang), np.zeros(sections)])
    top = np.column_stack([r2 * np.cos(ang), r2 * np.sin(ang), np.full(sections, h)])
    verts = np.vstack([bottom, top, [[0, 0, 0]], [[0, 0, h]]])
    cb, ct = 2 * sections, 2 * sections + 1
    faces = []
    for i in range(sections):
        j = (i + 1) % sections
        faces.append([i, j, sections + i])
        faces.append([j, sections + j, sections + i])
        faces.append([cb, j, i])
        faces.append([ct, sections + i, sections + j])
    m = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    if m.volume < 0:
        m.invert()
    return m


def interference_volume(part: trimesh.Trimesh, other: trimesh.Trimesh) -> float:
    """Volume of part ∩ other using the manifold engine; 0 if disjoint."""
    if not part.is_watertight or not other.is_watertight:
        # fall back to a bounding test to avoid crashing
        if not trimesh.bounds.contains(part.bounds, other.vertices).any():
            return 0.0
    try:
        inter = trimesh.boolean.intersection([part, other], engine="manifold")
        if inter is None or inter.is_empty:
            return 0.0
        return float(abs(inter.volume))
    except Exception:
        # very conservative fallback: voxel-free proximity test
        try:
            d = trimesh.proximity.signed_distance(other, part.vertices[:: max(1, len(part.vertices) // 2000)])
            return float(max(0.0, d.max())) * 1e-3  # tiny nonzero flag value
        except Exception:
            return 0.0


def bbox_dict(mesh: trimesh.Trimesh) -> dict:
    lo, hi = mesh.bounds
    return {"min": [round(float(v), 3) for v in lo], "max": [round(float(v), 3) for v in hi],
            "size": [round(float(v), 3) for v in (hi - lo)]}


def mesh_stats(mesh: trimesh.Trimesh) -> dict:
    bodies = 1
    try:
        bodies = int(mesh.body_count)
    except Exception:
        pass
    return {
        "triangles": int(len(mesh.faces)), "vertices": int(len(mesh.vertices)),
        "watertight": bool(mesh.is_watertight), "winding_consistent": bool(mesh.is_winding_consistent),
        "bodies": bodies, "volume_mm3": round(float(abs(mesh.volume)), 3) if mesh.is_watertight else None,
        "surface_area_mm2": round(float(mesh.area), 3), "bbox": bbox_dict(mesh),
        "center_mass": [round(float(v), 3) for v in mesh.center_mass] if mesh.is_watertight else None,
    }


def iter_polys(geom) -> Iterable[Polygon]:
    if isinstance(geom, Polygon):
        yield geom
    elif isinstance(geom, MultiPolygon):
        yield from geom.geoms
