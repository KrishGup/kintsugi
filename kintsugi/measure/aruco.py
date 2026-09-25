"""ArUco marker detection, the sheet homography, rectification and a rough camera tilt.

All pixel coordinates use OpenCV's convention (pixel ``(i, j)`` is centred at ``(i, j)``). Sheet coordinates are
millimetres with the origin at the paper's top-left corner (see :mod:`kintsugi.measure.sheet`). A homography
``H`` returned here always maps *photo pixels -> sheet millimetres*.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from kintsugi.measure.sheet import SHEET_LAYOUT, SheetLayout, aruco_dictionary

# Parameter sets tried in turn until every layout marker is found. Blurred, strongly foreshortened markers
# sometimes survive only a larger adaptive-threshold window or the ArUco3 pipeline.
_DETECTOR_PASSES: tuple[dict[str, object], ...] = (
    {},
    {"adaptiveThreshWinSizeMax": 53},
    {"useAruco3Detection": True},
)


@dataclass
class Marker:
    """One detected marker: ``corners`` are (4, 2) pixel coordinates ordered TL, TR, BR, BL in the marker's
    own (canonical) frame, exactly as ``cv2.aruco`` reports them."""

    id: int
    corners: np.ndarray
    refined: bool = False

    @property
    def center(self) -> np.ndarray:
        return self.corners.mean(axis=0)

    @property
    def side_px(self) -> float:
        """Mean edge length in pixels."""
        c = self.corners
        return float(np.mean([np.linalg.norm(c[(k + 1) % 4] - c[k]) for k in range(4)]))

    def to_dict(self) -> dict:
        return {"id": self.id, "corners": self.corners.round(3).tolist(), "side_px": round(self.side_px, 2)}


@dataclass
class RectifiedImage:
    """A metric, top-down view of the sheet plane.

    Pixel ``(i, j)`` of ``img`` is centred at sheet coordinate ``origin_mm + (i, j) * mm_per_px``.
    """

    img: np.ndarray
    mm_per_px: float
    origin_mm: tuple[float, float]
    H: np.ndarray | None = field(default=None, repr=False)  # the photo px -> mm homography used, if any

    @property
    def shape(self) -> tuple[int, int]:
        return self.img.shape[:2]

    @property
    def size_mm(self) -> tuple[float, float]:
        h, w = self.img.shape[:2]
        return (w * self.mm_per_px, h * self.mm_per_px)

    @property
    def gray(self) -> np.ndarray:
        return cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY) if self.img.ndim == 3 else self.img

    def px_to_mm(self, pts: np.ndarray) -> np.ndarray:
        p = np.asarray(pts, dtype=np.float64)
        return p * self.mm_per_px + np.asarray(self.origin_mm, dtype=np.float64)

    def mm_to_px(self, pts: np.ndarray) -> np.ndarray:
        p = np.asarray(pts, dtype=np.float64)
        return (p - np.asarray(self.origin_mm, dtype=np.float64)) / self.mm_per_px

    def crop_mm(self, roi_mm: tuple[float, float, float, float] | None) -> "RectifiedImage":
        """Sub-image covering ``roi_mm = (x0, y0, x1, y1)`` (clipped to the image); None returns self."""
        if roi_mm is None:
            return self
        h, w = self.img.shape[:2]
        x0, y0, x1, y1 = roi_mm
        (px0, py0), (px1, py1) = self.mm_to_px([[min(x0, x1), min(y0, y1)], [max(x0, x1), max(y0, y1)]])
        ix0, iy0 = max(int(math.floor(px0)), 0), max(int(math.floor(py0)), 0)
        ix1, iy1 = min(int(math.ceil(px1)) + 1, w), min(int(math.ceil(py1)) + 1, h)
        if ix1 <= ix0 or iy1 <= iy0:
            raise ValueError(f"roi {roi_mm} lies outside the rectified image ({self.size_mm} mm)")
        return RectifiedImage(self.img[iy0:iy1, ix0:ix1], self.mm_per_px,
                              tuple(self.px_to_mm([ix0, iy0]).tolist()), self.H)


# ---- detection ---------------------------------------------------------------------------------------------

def _to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    if img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def refine_corners(gray: np.ndarray, corners: np.ndarray, side_px: float) -> np.ndarray:
    """Sub-pixel corner refinement (``cv2.cornerSubPix``) with a window scaled to the marker's cell size.

    The window half-size is ~60% of a cell so the marker's inner bit edges never enter it. A corner that moves
    more than half a cell is considered a failed refinement and is left where the detector put it.
    """
    cell = side_px / 6.0
    win = int(np.clip(round(cell * 0.6), 2, 12))
    pts = np.ascontiguousarray(corners, dtype=np.float32).reshape(-1, 1, 2)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.01)
    try:
        ref = cv2.cornerSubPix(gray, pts.copy(), (win, win), (-1, -1), crit).reshape(-1, 2)
    except cv2.error:
        return np.asarray(corners, dtype=np.float64)
    out = np.asarray(corners, dtype=np.float64).copy()
    moved = np.linalg.norm(ref - out, axis=1)
    ok = np.isfinite(ref).all(axis=1) & (moved <= max(0.5 * cell, 1.0))
    out[ok] = ref[ok]
    return out


def detect_markers(img_bgr: np.ndarray, refine: bool = True, layout: SheetLayout | None = SHEET_LAYOUT,
                   dictionary: cv2.aruco.Dictionary | None = None) -> list[Marker]:
    """Detect DICT_4X4_50 markers, returning them sorted by id with sub-pixel refined corners.

    Several detector parameter sets are tried and merged until all markers of ``layout`` are found (pass
    ``layout=None`` to accept any id from the dictionary and run every pass).
    """
    gray = _to_gray(img_bgr)
    dictionary = dictionary or aruco_dictionary()
    wanted = set(layout.marker_ids) if layout is not None else None
    found: dict[int, np.ndarray] = {}
    for overrides in _DETECTOR_PASSES:
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_NONE  # we refine ourselves, per marker size
        for k, v in overrides.items():
            setattr(params, k, v)
        detector = cv2.aruco.ArucoDetector(dictionary, params)
        corners, ids, _ = detector.detectMarkers(gray)
        if ids is not None:
            for c, i in zip(corners, ids.ravel()):
                i = int(i)
                if (wanted is not None and i not in wanted) or i in found:
                    continue
                found[i] = np.asarray(c, dtype=np.float64).reshape(4, 2)
        if wanted is not None and wanted <= set(found):
            break
    markers: list[Marker] = []
    for i in sorted(found):
        c = found[i]
        side = float(np.mean([np.linalg.norm(c[(k + 1) % 4] - c[k]) for k in range(4)]))
        if refine:
            c = refine_corners(gray, c, side)
        markers.append(Marker(i, c, refined=refine))
    return markers


# ---- homography -------------------------------------------------------------------------------------------

def _correspondences(markers: list[Marker], layout: SheetLayout) -> tuple[np.ndarray, np.ndarray]:
    src, dst = [], []
    for m in markers:
        if m.id in layout.markers:
            src.append(m.corners)
            dst.append(layout.marker_corners_mm(m.id))
    if not src:
        return np.zeros((0, 2)), np.zeros((0, 2))
    return np.concatenate(src).astype(np.float64), np.concatenate(dst).astype(np.float64)


def sheet_homography(markers: list[Marker], layout: SheetLayout = SHEET_LAYOUT,
                     reproj_thresh_mm: float = 1.0, min_markers: int = 2) -> np.ndarray | None:
    """3x3 homography from photo pixels to sheet millimetres, fitted with RANSAC on all marker corners.

    Returns None with fewer than ``min_markers`` known markers or when the fit is degenerate.
    """
    known = [m for m in markers if m.id in layout.markers]
    if len(known) < max(min_markers, 1) or len(known) * 4 < 4:
        return None
    src, dst = _correspondences(known, layout)
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, reproj_thresh_mm)
    if H is None or not np.all(np.isfinite(H)) or abs(H[2, 2]) < 1e-12:
        return None
    if mask is not None and int(mask.sum()) < 4:
        return None
    H = H / H[2, 2]
    # sanity: the mapped image must not be folded (positive Jacobian determinant at the marker centres)
    for m in known:
        if _jacobian_det(H, m.center) <= 0:
            return None
    return H


def homography_residuals_mm(H: np.ndarray, markers: list[Marker], layout: SheetLayout = SHEET_LAYOUT) -> np.ndarray:
    """Per-corner reprojection error (mm) of the markers under H; useful as a self-check."""
    src, dst = _correspondences(markers, layout)
    if len(src) == 0:
        return np.zeros(0)
    return np.linalg.norm(px_to_mm(H, src) - dst, axis=1)


def px_to_mm(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Apply the photo->sheet homography to (N, 2) (or (2,)) pixel points."""
    p = np.asarray(pts, dtype=np.float64)
    single = p.ndim == 1
    out = cv2.perspectiveTransform(p.reshape(-1, 1, 2), np.asarray(H, dtype=np.float64)).reshape(-1, 2)
    return out[0] if single else out


def mm_to_px(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Apply the inverse of the photo->sheet homography to (N, 2) (or (2,)) millimetre points."""
    return px_to_mm(np.linalg.inv(np.asarray(H, dtype=np.float64)), pts)


def _jacobian_det(H: np.ndarray, p: np.ndarray) -> float:
    """Determinant of the local px->mm Jacobian at pixel p (mm^2 per px^2)."""
    x, y = float(p[0]), float(p[1])
    h = H
    d = h[2, 0] * x + h[2, 1] * y + h[2, 2]
    u = h[0, 0] * x + h[0, 1] * y + h[0, 2]
    v = h[1, 0] * x + h[1, 1] * y + h[1, 2]
    dudx = (h[0, 0] * d - u * h[2, 0]) / d**2
    dudy = (h[0, 1] * d - u * h[2, 1]) / d**2
    dvdx = (h[1, 0] * d - v * h[2, 0]) / d**2
    dvdy = (h[1, 1] * d - v * h[2, 1]) / d**2
    return float(dudx * dvdy - dudy * dvdx)


def photo_px_per_mm(H: np.ndarray, at_mm: tuple[float, float]) -> float:
    """Local photo resolution (px/mm) at a sheet position, from the homography's Jacobian."""
    p = mm_to_px(H, np.asarray(at_mm, dtype=np.float64))
    det = _jacobian_det(H, p)
    return float(1.0 / math.sqrt(det)) if det > 0 else float("nan")


# ---- rectification ------------------------------------------------------------------------------------------

def rectify(img_bgr: np.ndarray, H: np.ndarray, mm_per_px: float = 0.1,
            region_mm: tuple[float, float, float, float] | None = None,
            layout: SheetLayout = SHEET_LAYOUT, interpolation: int = cv2.INTER_CUBIC) -> RectifiedImage:
    """Warp the photo into a true top-down metric image of the sheet plane.

    Args:
        img_bgr: the photo.
        H: photo px -> sheet mm homography (from :func:`sheet_homography`).
        mm_per_px: output resolution.
        region_mm: (x0, y0, x1, y1) in sheet mm; default is the whole common layout area.
        interpolation: OpenCV interpolation flag for the warp. When the photo has noticeably more pixels per mm
            than the output, it is pre-blurred so minification does not alias.
    """
    if region_mm is None:
        region_mm = (0.0, 0.0, layout.common_area[0], layout.common_area[1])
    x0, y0, x1, y1 = region_mm
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    w = int(math.ceil((x1 - x0) / mm_per_px)) + 1
    h = int(math.ceil((y1 - y0) / mm_per_px)) + 1
    S = np.array([[mm_per_px, 0.0, x0], [0.0, mm_per_px, y0], [0.0, 0.0, 1.0]])
    M = np.linalg.inv(np.asarray(H, dtype=np.float64)) @ S  # rectified px -> photo px

    src = img_bgr
    ratio = photo_px_per_mm(H, ((x0 + x1) / 2, (y0 + y1) / 2)) * mm_per_px  # photo px per output px
    if np.isfinite(ratio) and ratio > 1.25:
        sigma = 0.6 * math.sqrt(ratio * ratio - 1.0)
        src = cv2.GaussianBlur(img_bgr, (0, 0), sigma)
    out = cv2.warpPerspective(src, M, (w, h), flags=interpolation | cv2.WARP_INVERSE_MAP,
                              borderMode=cv2.BORDER_REPLICATE)
    return RectifiedImage(out, float(mm_per_px), (float(x0), float(y0)), np.asarray(H, dtype=np.float64))


# ---- tilt -------------------------------------------------------------------------------------------------

def guess_intrinsics(image_size: tuple[int, int], focal_factor: float = 1.2) -> np.ndarray:
    """A plausible phone-camera matrix: fx = fy = focal_factor * max(w, h), principal point at the centre."""
    w, h = int(image_size[0]), int(image_size[1])
    f = focal_factor * max(w, h)
    return np.array([[f, 0.0, (w - 1) / 2.0], [0.0, f, (h - 1) / 2.0], [0.0, 0.0, 1.0]])


def estimate_pose(markers: list[Marker], image_size: tuple[int, int], layout: SheetLayout = SHEET_LAYOUT,
                  focal_factor: float = 1.2) -> tuple[np.ndarray, np.ndarray] | None:
    """(R, t) of the sheet in the camera frame (mm), from a planar PnP with guessed intrinsics."""
    known = [m for m in markers if m.id in layout.markers]
    if len(known) < 2:
        return None
    src, dst = _correspondences(known, layout)
    obj = np.column_stack([dst, np.zeros(len(dst))]).astype(np.float64)
    K = guess_intrinsics(image_size, focal_factor)
    try:
        ok, rvec, tvec = cv2.solvePnP(obj, src.astype(np.float64), K, None, flags=cv2.SOLVEPNP_IPPE)
    except cv2.error:
        ok = False
    if not ok:
        return None
    R, _ = cv2.Rodrigues(rvec)
    return R, tvec.reshape(3)


def estimate_tilt_deg(markers: list[Marker], image_size: tuple[int, int], layout: SheetLayout = SHEET_LAYOUT,
                      focal_factor: float = 1.2) -> float | None:
    """Approximate angle (degrees) between the camera's optical axis and the sheet normal.

    Uses a planar PnP with a guessed focal length (``focal_factor * max(w, h)``), so it is only indicative:
    a lens wider than the guess makes the estimate read low, a narrower one high. Falls back to decomposing the
    homography when PnP fails. Returns None with fewer than two markers.
    """
    pose = estimate_pose(markers, image_size, layout, focal_factor)
    if pose is not None:
        R, _ = pose
        return float(math.degrees(math.acos(float(np.clip(abs(R[2, 2]), 0.0, 1.0)))))
    H = sheet_homography(markers, layout)
    if H is None:
        return None
    K = guess_intrinsics(image_size, focal_factor)
    A = np.linalg.inv(K) @ np.linalg.inv(H)  # mm -> normalised camera coords: [r1 r2 t] up to scale
    n1, n2 = np.linalg.norm(A[:, 0]), np.linalg.norm(A[:, 1])
    if n1 < 1e-12 or n2 < 1e-12:
        return None
    r1, r2 = A[:, 0] / n1, A[:, 1] / n2
    r3 = np.cross(r1, r2)
    r3 /= max(np.linalg.norm(r3), 1e-12)
    return float(math.degrees(math.acos(float(np.clip(abs(r3[2]), 0.0, 1.0)))))


__all__ = [
    "Marker", "RectifiedImage", "detect_markers", "estimate_pose", "estimate_tilt_deg", "guess_intrinsics",
    "homography_residuals_mm", "mm_to_px", "photo_px_per_mm", "px_to_mm", "rectify", "refine_corners",
    "sheet_homography",
]
