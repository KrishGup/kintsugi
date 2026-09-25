"""Measurements on a rectified (metric, top-down) image. All results are in sheet millimetres.

Circle measurement is two-stage: candidate circles come from edge contours (Canny) and from dark/light blob
contours, each fitted with a RANSAC circle; every candidate is then refined by sampling radial intensity
profiles across its edge and locating the gradient peak to sub-pixel accuracy, followed by a final robust fit.
A HoughCircles pass cross-checks each result and rescues circles the contours missed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import cv2
import numpy as np
from shapely.geometry import Polygon

from kintsugi.checks.geometry import CircleFit, fit_circle, fit_circle_robust
from kintsugi.measure.aruco import RectifiedImage
from kintsugi.measure.sheet import SHEET_LAYOUT, SheetLayout

Polarity = Literal["dark", "light", "any"]


@dataclass
class CircleMeasure:
    """A measured circle in sheet mm. ``method`` records how it was found: ``contour``, ``contour+hough``,
    ``blob``, ``blob+hough``, or ``hough`` (found only by the Hough pass)."""

    cx: float
    cy: float
    d: float
    conf: float
    method: str
    rms_mm: float = 0.0  # scatter of the edge points about the fitted circle (noise + shape deviation)
    n_points: int = 0
    coverage: float = 0.0  # fraction of the circumference supported by edge points
    inlier_fraction: float = 1.0
    systematic_mm: float = 0.0  # the part of the scatter that is not noise: deviation from a true circle
    sigma_d_mm: float = 0.0  # standard error of the diameter (from the point scatter and count)

    @property
    def r(self) -> float:
        return self.d / 2

    def to_dict(self) -> dict:
        return {"cx": round(self.cx, 3), "cy": round(self.cy, 3), "d": round(self.d, 3), "conf": round(self.conf, 3),
                "method": self.method, "rms_mm": round(self.rms_mm, 4), "n_points": self.n_points,
                "coverage": round(self.coverage, 3), "systematic_mm": round(self.systematic_mm, 4),
                "sigma_d_mm": round(self.sigma_d_mm, 4)}


@dataclass
class RectMeasure:
    """Minimum-area rectangle of the dominant outline: ``w`` >= ``h`` in mm, ``angle`` is the direction of the
    ``w`` side in degrees (counter-clockwise on paper, i.e. as seen in the photo), ``conf`` is how rectangular
    the outline is (fill ratio of the outline inside its bounding rectangle, rescaled)."""

    w: float
    h: float
    angle: float
    conf: float
    cx: float = 0.0
    cy: float = 0.0
    corners_mm: np.ndarray = field(default_factory=lambda: np.zeros((4, 2)))

    def to_dict(self) -> dict:
        return {"w": round(self.w, 3), "h": round(self.h, 3), "angle": round(self.angle, 2), "conf": round(self.conf, 3),
                "cx": round(self.cx, 3), "cy": round(self.cy, 3), "corners_mm": self.corners_mm.round(3).tolist()}


# ---- helpers ----------------------------------------------------------------------------------------------

def _prep(rect: RectifiedImage, roi_mm: tuple[float, float, float, float] | None) -> tuple[RectifiedImage, np.ndarray, np.ndarray]:
    """Crop to the ROI and return (crop, gray float32 lightly smoothed, gray uint8)."""
    crop = rect.crop_mm(roi_mm)
    g8 = crop.gray
    gs = cv2.GaussianBlur(g8.astype(np.float32), (0, 0), 0.8)
    return crop, gs, g8


def _suppress_lines(g8: np.ndarray, mm_per_px: float, polarity: Polarity) -> np.ndarray:
    """Remove the sheet's thin printed lines (grid, coin outlines) so they do not seed candidates.

    A grey-scale closing removes dark features thinner than ~0.5 mm (an opening removes light ones); real
    objects are far wider and keep their edges in place (closing/opening displace straight edges by nothing).
    """
    if polarity == "any":
        return g8
    k = int(round(0.5 / mm_per_px)) | 1
    k = max(3, min(k, 15))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    op = cv2.MORPH_CLOSE if polarity == "dark" else cv2.MORPH_OPEN
    return cv2.morphologyEx(g8, op, kernel)


def _canny_thresholds(g8: np.ndarray) -> tuple[float, float]:
    """Hysteresis thresholds from the image contrast: Otsu splits fore/background, the high threshold is a
    fraction of the Sobel response a blurred edge of that contrast would give."""
    thr, _ = cv2.threshold(g8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    lo_mean = float(g8[g8 < thr].mean()) if np.any(g8 < thr) else 0.0
    hi_mean = float(g8[g8 >= thr].mean()) if np.any(g8 >= thr) else 255.0
    contrast = max(hi_mean - lo_mean, 20.0)
    high = float(np.clip(0.45 * contrast, 30.0, 220.0))
    return high * 0.4, high


def _profile_gradient(prof: np.ndarray, step: float, sigma_px: float = 1.0) -> np.ndarray:
    """d(intensity)/dt along axis 1 of a (rays, samples) profile array, after a 1-D Gaussian smoothing of
    ``sigma_px`` (in px, i.e. ``sigma_px / step`` samples) so noisy profiles still give a clean peak."""
    smoothed = cv2.GaussianBlur(prof, (0, 0), sigmaX=max(sigma_px / step, 0.1), sigmaY=1e-3)
    return np.gradient(smoothed, step, axis=1)


def _robust_tol(residuals: np.ndarray, lo: float = 0.75, hi: float = 4.0) -> float:
    """Inlier tolerance from the residual spread: 3 robust sigmas (1.4826 MAD), clamped to [lo, hi] px."""
    if len(residuals) == 0:
        return lo
    mad = float(np.median(np.abs(residuals - np.median(residuals))))
    return float(np.clip(3.0 * 1.4826 * mad, lo, hi))


def _noise_sigma(gs: np.ndarray) -> float:
    """Robust pixel-noise estimate (grey levels) from horizontal differences of the smoothed image."""
    d = np.diff(gs, axis=1).ravel()
    if len(d) == 0:
        return 0.0
    return 1.4826 * float(np.median(np.abs(d - np.median(d)))) / math.sqrt(2.0)


def _angular_coverage(pts: np.ndarray, cx: float, cy: float, bins: int = 36) -> float:
    if len(pts) == 0:
        return 0.0
    ang = np.arctan2(pts[:, 1] - cy, pts[:, 0] - cx)
    hist, _ = np.histogram(ang, bins=bins, range=(-math.pi, math.pi))
    return float(np.count_nonzero(hist) / bins)


def _sample_profiles(gs: np.ndarray, cx: float, cy: float, r: float, half_width: float, n_rays: int,
                     step: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Intensity along ``n_rays`` radial rays, at radii r + t for t in [-half_width, half_width]."""
    ang = np.linspace(0.0, 2 * math.pi, n_rays, endpoint=False)
    ts = np.arange(-half_width, half_width + step / 2, step)
    rr = r + ts[None, :]
    xs = (cx + rr * np.cos(ang)[:, None]).astype(np.float32)
    ys = (cy + rr * np.sin(ang)[:, None]).astype(np.float32)
    prof = cv2.remap(gs, xs, ys, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return ang, ts, prof


def _radial_edge_points(gs: np.ndarray, cx: float, cy: float, r: float, half_width: float,
                        polarity: int = 0, step: float = 0.25) -> tuple[np.ndarray, np.ndarray, int, np.ndarray]:
    """Sub-pixel edge points around a circle from the gradient peak of each radial profile.

    ``polarity`` +1 expects intensity rising outward (dark object on light paper), -1 falling outward (a hole),
    0 picks the majority. Returns (points (N, 2) px, strengths, polarity used, jumps), where ``jumps`` is the
    signed intensity step across each edge point (outside minus inside, times polarity: positive for a real
    edge of the expected polarity). Rays whose peak sits at the end of the profile are dropped.
    """
    n_rays = int(np.clip(round(2 * math.pi * r / 2.5), 48, 720))
    ang, ts, prof = _sample_profiles(gs, cx, cy, r, half_width, n_rays, step)
    g = _profile_gradient(prof, step)
    h, w = gs.shape[:2]
    if polarity == 0:
        peak = g[np.arange(n_rays), np.abs(g).argmax(axis=1)]
        polarity = 1 if np.median(peak) >= 0 else -1
    gs_signed = g * polarity
    k = gs_signed.argmax(axis=1)
    n_t = len(ts)
    valid = (k > 0) & (k < n_t - 1)
    rows = np.arange(n_rays)
    strength = gs_signed[rows, k]
    # parabolic sub-sample interpolation of the peak
    km = np.clip(k - 1, 0, n_t - 1)
    kp = np.clip(k + 1, 0, n_t - 1)
    ym, y0, yp = gs_signed[rows, km], strength, gs_signed[rows, kp]
    denom = ym - 2 * y0 + yp
    off = np.where(np.abs(denom) > 1e-9, 0.5 * (ym - yp) / np.where(np.abs(denom) > 1e-9, denom, 1.0), 0.0)
    off = np.clip(off, -1.0, 1.0)
    t_edge = ts[k] + off * step
    rr = r + t_edge
    pts = np.column_stack([cx + rr * np.cos(ang), cy + rr * np.sin(ang)])
    inside = (pts[:, 0] >= 0) & (pts[:, 0] <= w - 1) & (pts[:, 1] >= 0) & (pts[:, 1] <= h - 1)
    valid &= inside & (strength > 0)
    # intensity step across the edge: mean of the profile 2.5-3.5 px outside minus 2.5-3.5 px inside
    lo, hi = int(round(2.5 / step)), int(round(3.5 / step))
    idx = np.arange(n_t)[None, :]
    band_out = (idx >= k[:, None] + lo) & (idx <= k[:, None] + hi)
    band_in = (idx <= k[:, None] - lo) & (idx >= k[:, None] - hi)
    n_out, n_in = band_out.sum(axis=1), band_in.sum(axis=1)
    mean_out = (prof * band_out).sum(axis=1) / np.maximum(n_out, 1)
    mean_in = (prof * band_in).sum(axis=1) / np.maximum(n_in, 1)
    jumps = polarity * (mean_out - mean_in)
    valid &= (n_out > 0) & (n_in > 0)
    if valid.sum() >= 8:
        med = float(np.median(strength[valid]))
        valid &= strength >= 0.25 * med
    return pts[valid], strength[valid], polarity, jumps[valid]


def _split_residuals(res: np.ndarray, ang: np.ndarray, harmonics: int = 8) -> tuple[float, float]:
    """(noise, systematic) components of circle-fit residuals, in px.

    A real departure from a circle (an ellipse, a flat, a chip) is smooth around the circumference, so it lives
    in the low harmonics of residual-vs-angle; noise (even when blur correlates it over a few pixels) does
    not. Harmonics 2..``harmonics`` are fitted by least squares (0 and 1 are absorbed by the circle fit); the
    expected noise leakage into that fit is subtracted.
    """
    n = len(res)
    if n < 4 * harmonics:
        return float(np.std(res)) if n else 0.0, 0.0
    ks = np.arange(2, harmonics + 1)
    A = np.column_stack([np.cos(np.outer(ang, ks)), np.sin(np.outer(ang, ks))])
    coef, *_ = np.linalg.lstsq(A, res, rcond=None)
    smooth = A @ coef
    noise_var = float(np.mean((res - smooth) ** 2)) * n / max(n - A.shape[1], 1)
    sys_var = float(np.mean(smooth**2)) - noise_var * A.shape[1] / n
    return math.sqrt(max(noise_var, 0.0)), math.sqrt(max(sys_var, 0.0))


@dataclass
class _Refined:
    fit: CircleFit
    coverage: float
    polarity: int
    systematic: float  # px, deviation from a true circle
    contrast: float  # median intensity step across the edge (grey levels)
    consistency: float  # fraction of rays whose step has the expected sign and size


def _refine_circle(gs: np.ndarray, cx: float, cy: float, r: float, polarity: int = 0,
                   passes: int = 2) -> _Refined | None:
    """Radial-profile refinement of a candidate circle (see :class:`_Refined`), or None."""
    fit: CircleFit | None = None
    for p in range(passes):
        # pass 2 needs >= 3.5 px beyond the edge on both sides for the contrast bands, plus the point scatter
        half = float(np.clip(0.12 * r, 5.0, 12.0)) if p == 0 else float(np.clip(0.05 * r, 5.0, 8.0))
        pts, strength, polarity, jumps = _radial_edge_points(gs, cx, cy, r, half, polarity)
        if len(pts) < 12:
            return None
        tol = float(np.clip(0.005 * r, 0.75, 2.0))
        fit = fit_circle_robust(pts, tol=tol)
        if not np.isfinite([fit.cx, fit.cy, fit.r]).all() or fit.r <= 1:
            return None
        # widen the tolerance to the actual noise of the edge points (soft, noisy edges scatter more)
        res = np.hypot(pts[:, 0] - fit.cx, pts[:, 1] - fit.cy) - fit.r
        tol2 = _robust_tol(res, lo=tol)
        if tol2 > tol:
            fit = fit_circle_robust(pts, tol=tol2)
            if not np.isfinite([fit.cx, fit.cy, fit.r]).all() or fit.r <= 1:
                return None
        cx, cy, r = fit.cx, fit.cy, fit.r
    assert fit is not None
    # final statistics on the last point set
    d = np.hypot(pts[:, 0] - fit.cx, pts[:, 1] - fit.cy) - fit.r
    tol = _robust_tol(d, lo=float(np.clip(0.005 * fit.r, 0.75, 2.0)))
    inl = np.abs(d) <= tol
    final = fit_circle(pts[inl]) if inl.sum() >= 6 else fit
    final.inlier_fraction = float(inl.mean())
    cov = _angular_coverage(pts[inl], final.cx, final.cy)
    res = np.hypot(pts[inl, 0] - final.cx, pts[inl, 1] - final.cy) - final.r
    ang = np.arctan2(pts[inl, 1] - final.cy, pts[inl, 0] - final.cx)
    _noise, systematic = _split_residuals(res, ang)
    j = jumps[inl]
    contrast = float(np.median(j)) if len(j) else 0.0
    consistency = float(np.mean(j > 0.3 * max(contrast, 1e-6))) if len(j) else 0.0
    return _Refined(final, cov, polarity, systematic, contrast, consistency)


def _hough_agrees(g8: np.ndarray, cx: float, cy: float, r: float, canny_high: float) -> bool:
    """Run HoughCircles in a window around the candidate; True if a circle of about the same size is found."""
    h, w = g8.shape[:2]
    pad = int(r * 1.3) + 4
    x0, y0 = max(int(cx) - pad, 0), max(int(cy) - pad, 0)
    x1, y1 = min(int(cx) + pad + 1, w), min(int(cy) + pad + 1, h)
    win = g8[y0:y1, x0:x1]
    if min(win.shape) < 8:
        return False
    scale = 1.0
    if max(win.shape) > 700:  # keep the accumulator small
        scale = 700.0 / max(win.shape)
        win = cv2.resize(win, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    rs = r * scale
    win = cv2.GaussianBlur(win, (0, 0), 1.2)
    circles = cv2.HoughCircles(win, cv2.HOUGH_GRADIENT, dp=1.0, minDist=max(rs * 0.5, 4.0),
                               param1=float(max(canny_high, 30.0)), param2=18.0,
                               minRadius=max(int(rs * 0.9) - 2, 1), maxRadius=int(rs * 1.1) + 2)
    if circles is None:
        return False
    tol = max(3.0, 0.04 * rs)
    for x, y, rr in circles[0]:
        if math.hypot(x - (cx - x0) * scale, y - (cy - y0) * scale) <= tol and abs(rr - rs) <= tol:
            return True
    return False


def _hough_candidates(g8: np.ndarray, min_r: float, max_r: float, canny_high: float,
                      max_candidates: int = 24) -> list[tuple[float, float, float]]:
    """A global HoughCircles pass (on a down-scaled image when large), returning (cx, cy, r) in px."""
    scale = 1.0
    src = g8
    if max(g8.shape) > 1200:
        scale = 1200.0 / max(g8.shape)
        src = cv2.resize(g8, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    src = cv2.GaussianBlur(src, (0, 0), 1.2)
    mn, mx = max(int(min_r * scale) - 1, 2), int(max_r * scale) + 2
    if mx <= mn:
        return []
    circles = cv2.HoughCircles(src, cv2.HOUGH_GRADIENT, dp=1.2, minDist=max(min_r * scale, 5.0),
                               param1=float(max(canny_high, 30.0)), param2=30.0, minRadius=mn, maxRadius=mx)
    if circles is None:
        return []
    # HoughCircles returns circles in decreasing accumulator order: keep the best-supported ones only
    return [(float(x / scale), float(y / scale), float(r / scale)) for x, y, r in circles[0][:max_candidates]]


def _contour_candidates(contours: list[np.ndarray], min_r: float, max_r: float,
                        min_cov: float = 0.45) -> list[tuple[float, float, float, int]]:
    """RANSAC circle fits of contours whose size is plausible: (cx, cy, r, n_inliers) in px."""
    out: list[tuple[float, float, float, int]] = []
    for c in contours:
        pts = c.reshape(-1, 2).astype(np.float64)
        if len(pts) < max(16, int(0.5 * math.pi * min_r)):
            continue
        ext = pts.max(axis=0) - pts.min(axis=0)
        diag = float(np.hypot(*ext))
        if diag < 1.2 * min_r or diag > 3.2 * max_r:
            continue
        try:
            fit = fit_circle_robust(pts, tol=1.5)
        except (ValueError, np.linalg.LinAlgError):
            continue
        if not np.isfinite([fit.cx, fit.cy, fit.r]).all():
            continue
        if fit.r < 0.85 * min_r or fit.r > 1.15 * max_r:
            continue
        d = np.abs(np.hypot(pts[:, 0] - fit.cx, pts[:, 1] - fit.cy) - fit.r)
        inl = d <= max(1.5, 0.01 * fit.r)
        if inl.mean() < 0.5 or _angular_coverage(pts[inl], fit.cx, fit.cy) < min_cov:
            continue
        out.append((fit.cx, fit.cy, fit.r, int(inl.sum())))
    return out


def _merge_candidates(cands: list[tuple[float, float, float, int, str]]) -> list[tuple[float, float, float, int, str]]:
    """Cluster near-identical circles, keeping the best-supported one of each cluster."""
    cands = sorted(cands, key=lambda c: -c[3])
    kept: list[tuple[float, float, float, int, str]] = []
    for c in cands:
        dup = False
        for k in kept:
            tol = max(3.0, 0.04 * k[2])
            if math.hypot(c[0] - k[0], c[1] - k[1]) <= tol and abs(c[2] - k[2]) <= tol:
                dup = True
                break
        if not dup:
            kept.append(c)
    return kept


def _confidence(cov: float, systematic_px: float, sigma_r_px: float, inlier_fraction: float, hough: bool) -> float:
    """Confidence in [0, 1] from angular coverage, systematic deviation from a circle, the radius standard
    error (point scatter / sqrt(n)), the inlier fraction and the Hough cross-check."""
    w_cov = float(np.clip((cov - 0.4) / 0.5, 0.0, 1.0))
    w_shape = float(np.clip(1.0 - systematic_px / 1.5, 0.1, 1.0))
    w_prec = float(np.clip(1.0 - sigma_r_px / 0.5, 0.1, 1.0))
    w_inl = float(np.clip((inlier_fraction - 0.3) / 0.6, 0.0, 1.0))
    return float(np.clip(w_cov * w_shape * w_prec * w_inl * (1.0 if hough else 0.85), 0.0, 1.0))


# ---- circles ----------------------------------------------------------------------------------------------

def find_circles(rect: RectifiedImage, min_d_mm: float, max_d_mm: float,
                 roi_mm: tuple[float, float, float, float] | None = None, *, polarity: Polarity = "dark",
                 hough_check: bool = True, min_conf: float = 0.15, min_coverage: float = 0.4,
                 exclude_printed: bool = True, layout: SheetLayout = SHEET_LAYOUT) -> list[CircleMeasure]:
    """Find and measure circles (discs, holes, bosses) with diameters in ``[min_d_mm, max_d_mm]``.

    Args:
        rect: rectified image (from :func:`kintsugi.measure.aruco.rectify`).
        min_d_mm, max_d_mm: diameter range of interest.
        roi_mm: optional (x0, y0, x1, y1) region in sheet mm.
        polarity: "dark" objects on the light sheet (default), "light" objects, or "any" (no line suppression,
            printed grid lines may then seed spurious candidates).
        hough_check: cross-check each circle with HoughCircles and add circles only Hough finds.
        min_conf: drop results below this confidence.
        min_coverage: minimum fraction of the circumference that must have edge support.
        exclude_printed: when the image is a rectified sheet (``rect.H`` is set), drop circles that coincide
            with the sheet's printed coin outlines (they read their nominal size whatever the print scale).

    Returns circles sorted by confidence (then diameter), in sheet mm.
    """
    crop, gs, g8 = _prep(rect, roi_mm)
    mpp = crop.mm_per_px
    min_r, max_r = min_d_mm / 2 / mpp, max_d_mm / 2 / mpp
    if max_r <= 2 or min_r > max(g8.shape):
        return []
    gc = _suppress_lines(g8, mpp, polarity)
    gc_s = cv2.GaussianBlur(gc, (0, 0), 1.0)
    low, high = _canny_thresholds(gc_s)
    noise_sigma = _noise_sigma(gs)

    cands: list[tuple[float, float, float, int, str]] = []
    # 1) edge contours
    edges = cv2.Canny(gc_s, low, high, L2gradient=True)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    cands += [(cx, cy, r, n, "contour") for cx, cy, r, n in _contour_candidates(list(contours), min_r, max_r)]
    # 2) blob contours (outer boundaries and holes)
    if polarity != "any":
        flag = cv2.THRESH_BINARY_INV if polarity == "dark" else cv2.THRESH_BINARY
        _, mask = cv2.threshold(gc_s, 0, 255, flag + cv2.THRESH_OTSU)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        bcont, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        cands += [(cx, cy, r, n, "blob") for cx, cy, r, n in _contour_candidates(list(bcont), min_r, max_r)]
    # 3) circles only Hough sees
    if hough_check:
        merged_so_far = _merge_candidates(cands)
        for cx, cy, r in _hough_candidates(gc, min_r, max_r, high):
            if any(math.hypot(cx - k[0], cy - k[1]) <= max(3.0, 0.05 * k[2]) and abs(r - k[2]) <= max(3.0, 0.05 * k[2])
                   for k in merged_so_far):
                continue
            cands.append((cx, cy, r, 0, "hough"))
    cands = _merge_candidates(cands)

    results: list[CircleMeasure] = []
    for cx, cy, r, _n, method in cands:
        ref = _refine_circle(gs, cx, cy, r)
        if ref is None:
            continue
        fit, cov, systematic = ref.fit, ref.coverage, ref.systematic
        d_mm = 2 * fit.r * mpp
        if d_mm < min_d_mm or d_mm > max_d_mm or cov < min_coverage or fit.rms > 4.0:
            continue
        # a real edge steps consistently (same sign, similar size) all around; circles assembled from grid
        # crossings or noise do not
        if ref.contrast < max(10.0, 4.0 * noise_sigma) or ref.consistency < 0.6:
            continue
        hough = _hough_agrees(gc, fit.cx, fit.cy, fit.r, high) if hough_check and method != "hough" else method == "hough"
        sigma_r = fit.rms / math.sqrt(max(fit.n, 1))
        conf = _confidence(cov, systematic, sigma_r, fit.inlier_fraction, hough)
        conf *= float(np.clip((ref.consistency - 0.5) / 0.4, 0.0, 1.0))
        if conf < min_conf:
            continue
        cmm = crop.px_to_mm([fit.cx, fit.cy])
        results.append(CircleMeasure(float(cmm[0]), float(cmm[1]), float(d_mm), conf,
                                     method if method == "hough" else (method + "+hough" if hough else method),
                                     rms_mm=float(fit.rms * mpp), n_points=int(fit.n), coverage=cov,
                                     inlier_fraction=float(fit.inlier_fraction), systematic_mm=float(systematic * mpp),
                                     sigma_d_mm=float(2 * sigma_r * mpp)))
    # refinement may make several candidates converge on the same circle (HoughCircles in particular reports
    # smaller, offset circles inside a filled disc): keep the contour/blob result and count a converging Hough
    # candidate as agreement
    results.sort(key=lambda c: (c.method == "hough", -c.conf, -c.d))
    final: list[CircleMeasure] = []
    for c in results:
        dup = next((k for k in final if math.hypot(c.cx - k.cx, c.cy - k.cy) <= max(0.3, 0.03 * k.d)
                    and abs(c.d - k.d) <= max(0.3, 0.03 * k.d)), None)
        if dup is None:
            final.append(c)
        elif c.method == "hough" and "hough" not in dup.method:
            dup.method += "+hough"
            dup.conf = _confidence(dup.coverage, dup.systematic_mm / mpp, dup.sigma_d_mm / (2 * mpp),
                                   dup.inlier_fraction, True)
    final.sort(key=lambda c: (-c.conf, -c.d))
    if exclude_printed and rect.H is not None:
        final = [c for c in final if not _is_printed_outline(c, layout)]
    return final


def _is_printed_outline(c: CircleMeasure, layout: SheetLayout) -> bool:
    for _name, (cx, cy, d) in layout.coins.items():
        if math.hypot(c.cx - cx, c.cy - cy) <= 1.5 and abs(c.d - d) <= 1.5:
            return True
    return False


# ---- outlines -----------------------------------------------------------------------------------------------

def _object_mask(g8: np.ndarray, mm_per_px: float, polarity: Polarity, threshold: float | None) -> np.ndarray:
    gc = _suppress_lines(g8, mm_per_px, polarity if polarity != "any" else "dark")
    gc = cv2.GaussianBlur(gc, (0, 0), 0.8)
    inv = polarity != "light"
    flag = cv2.THRESH_BINARY_INV if inv else cv2.THRESH_BINARY
    if threshold is None:
        _, mask = cv2.threshold(gc, 0, 255, flag + cv2.THRESH_OTSU)
    else:
        _, mask = cv2.threshold(gc, float(threshold), 255, flag)
    # No binary open/close here: they fill or shave the staircase of rotated edges and bias sizes by ~1 px.
    # Specks are removed by the contour area filter instead.
    return mask


def _object_contours(crop: RectifiedImage, polarity: Polarity, threshold: float | None,
                     min_area_mm2: float) -> list[np.ndarray]:
    """External contours (px, largest first) of objects in the crop; contours touching the border are kept."""
    g8 = crop.gray
    mask = _object_mask(g8, crop.mm_per_px, polarity, threshold)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    min_area_px = min_area_mm2 / crop.mm_per_px ** 2
    keep = [c for c in contours if len(c) >= 8 and cv2.contourArea(c) >= min_area_px]
    keep.sort(key=cv2.contourArea, reverse=True)
    return keep


def _refine_contour_normals(gs: np.ndarray, mask: np.ndarray, pts: np.ndarray, polarity: int,
                            half_width: float = 3.5, step: float = 0.25) -> np.ndarray | None:
    """Move every contour point onto the gradient peak of the intensity profile along its local normal.

    ``pts`` are ordered boundary points (px). The normal direction is oriented outward using the mask; offsets
    are median-filtered along the contour so an isolated bad profile (a grid line crossing, a touching object)
    cannot spike the outline. Returns the refined (N, 2) points, or None if too few profiles are usable.
    """
    n = len(pts)
    if n < 8:
        return None
    h_img, w_img = gs.shape[:2]
    # smoothed tangent from neighbours +-3 along the closed contour
    k = 3
    tang = np.roll(pts, -k, axis=0) - np.roll(pts, k, axis=0)
    norms = np.linalg.norm(tang, axis=1)
    norms[norms < 1e-9] = 1.0
    tang /= norms[:, None]
    normal = np.column_stack([-tang[:, 1], tang[:, 0]])
    # orient outward: the mask should be empty 2 px outside and set 2 px inside for most points
    probe_out = np.round(pts + 2.0 * normal).astype(int)
    probe_in = np.round(pts - 2.0 * normal).astype(int)
    ok = ((probe_out[:, 0] >= 0) & (probe_out[:, 0] < w_img) & (probe_out[:, 1] >= 0) & (probe_out[:, 1] < h_img)
          & (probe_in[:, 0] >= 0) & (probe_in[:, 0] < w_img) & (probe_in[:, 1] >= 0) & (probe_in[:, 1] < h_img))
    if ok.sum() < 8:
        return None
    m_out = mask[probe_out[ok, 1], probe_out[ok, 0]] > 0
    m_in = mask[probe_in[ok, 1], probe_in[ok, 0]] > 0
    votes = int((m_in & ~m_out).sum()) - int((m_out & ~m_in).sum())
    if votes < 0:
        normal = -normal
    ts = np.arange(-half_width, half_width + step / 2, step)
    xs = (pts[:, 0:1] + ts[None, :] * normal[:, 0:1]).astype(np.float32)
    ys = (pts[:, 1:2] + ts[None, :] * normal[:, 1:2]).astype(np.float32)
    prof = cv2.remap(gs, xs, ys, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    g = _profile_gradient(prof, step)
    if polarity == 0:
        peak = g[np.arange(n), np.abs(g).argmax(axis=1)]
        polarity = 1 if np.median(peak) >= 0 else -1
    gsg = g * polarity
    idx = gsg.argmax(axis=1)
    rows = np.arange(n)
    strength = gsg[rows, idx]
    valid = (idx > 0) & (idx < len(ts) - 1) & (strength > 0)
    if valid.sum() >= 8:
        valid &= strength >= 0.25 * float(np.median(strength[valid]))
    # at corners the normal is ill-defined and the profile straddles two edges: interpolate those offsets
    t_prev = pts - np.roll(pts, k, axis=0)
    t_next = np.roll(pts, -k, axis=0) - pts
    cosang = (t_prev * t_next).sum(axis=1) / np.maximum(np.linalg.norm(t_prev, axis=1) * np.linalg.norm(t_next, axis=1), 1e-9)
    corner = cosang < math.cos(math.radians(25.0))
    corner = np.convolve(np.concatenate([corner[-k:], corner, corner[:k]]).astype(float), np.ones(2 * k + 1), "valid") > 0
    valid &= ~corner
    if valid.sum() < max(8, 0.35 * n):
        return None
    km, kp = np.clip(idx - 1, 0, len(ts) - 1), np.clip(idx + 1, 0, len(ts) - 1)
    ym, y0, yp = gsg[rows, km], strength, gsg[rows, kp]
    den = ym - 2 * y0 + yp
    off = np.where(np.abs(den) > 1e-9, 0.5 * (ym - yp) / np.where(np.abs(den) > 1e-9, den, 1.0), 0.0)
    t_edge = ts[idx] + np.clip(off, -1, 1) * step
    # fill invalid profiles from their neighbours, then smooth heavily along the contour: the goal is to
    # correct the slowly varying threshold bias (lighting, vignetting), not to add per-point noise
    t_edge = np.where(valid, t_edge, np.nan)
    if np.isnan(t_edge).any():
        good = np.where(valid)[0]
        t_edge = np.interp(np.arange(n), good, t_edge[good], period=n)
    win = 5
    padded = np.concatenate([t_edge[-(win // 2):], t_edge, t_edge[: win // 2]])
    t_med = np.array([np.median(padded[i:i + win]) for i in range(n)])
    win = max(9, n // 12) | 1
    padded = np.concatenate([t_med[-(win // 2):], t_med, t_med[: win // 2]])
    t_smooth = np.convolve(padded, np.ones(win) / win, mode="valid")
    return pts + t_smooth[:, None] * normal


def find_outline(rect: RectifiedImage, roi_mm: tuple[float, float, float, float] | None = None,
                 simplify_mm: float = 0.2, *, min_area_mm2: float = 4.0, polarity: Polarity = "dark",
                 threshold: float | None = None, refine: bool = True) -> list[np.ndarray]:
    """Object silhouettes as (N, 2) polygons in sheet mm, largest first.

    Objects are segmented by an Otsu threshold (or ``threshold`` on the 0-255 grey scale) after suppressing the
    printed grid and traced with ``findContours``. With ``refine=True`` every boundary point is moved onto the
    gradient peak across the edge (sub-pixel, independent of the threshold); otherwise the contour is offset
    outward by half a pixel (contours run through boundary pixel centres). The result is simplified with
    Douglas-Peucker at ``simplify_mm``. Polygons are not closed (the last vertex is not repeated).
    """
    crop = rect.crop_mm(roi_mm)
    mpp = crop.mm_per_px
    eps_px = max(simplify_mm / mpp, 0.0)
    g8 = crop.gray
    mask = _object_mask(g8, mpp, polarity, threshold)
    gs = cv2.GaussianBlur(g8.astype(np.float32), (0, 0), 0.8) if refine else None
    pol = 0 if polarity == "any" else (1 if polarity == "dark" else -1)
    polys: list[np.ndarray] = []
    for c in _object_contours(crop, polarity, threshold, min_area_mm2):
        pts = c.reshape(-1, 2).astype(np.float64)
        refined = _refine_contour_normals(gs, mask, pts, pol) if refine else None
        try:
            if refined is not None:
                poly = Polygon(refined)
                if not poly.is_valid:
                    poly = poly.buffer(0)
            else:
                poly = Polygon(pts)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                poly = poly.buffer(0.5, join_style="mitre", mitre_limit=3.0)
            if poly.geom_type == "MultiPolygon":
                poly = max(poly.geoms, key=lambda p: p.area)
            if eps_px > 0:
                poly = poly.simplify(eps_px, preserve_topology=True)
            ring = np.asarray(poly.exterior.coords)[:-1]
        except Exception:  # degenerate geometry: fall back to the raw simplified contour
            approx = cv2.approxPolyDP(c, eps_px, True) if eps_px > 0 else c
            ring = approx.reshape(-1, 2).astype(np.float64)
        if len(ring) >= 3:
            polys.append(crop.px_to_mm(ring))
    return polys


def _fit_line_robust(pts: np.ndarray, tol: float = 1.5) -> tuple[np.ndarray, np.ndarray, float, float] | None:
    """Total-least-squares line through (N, 2) points with one outlier-rejection pass.

    Returns (point on line, unit direction, rms residual, inlier fraction) or None.
    """
    if len(pts) < 4:
        return None
    keep = np.ones(len(pts), dtype=bool)
    for _ in range(3):
        p = pts[keep]
        if len(p) < 4:
            return None
        c = p.mean(axis=0)
        _, _, vt = np.linalg.svd(p - c, full_matrices=False)
        d = vt[0]
        n = np.array([-d[1], d[0]])
        res = (pts - c) @ n
        new_keep = np.abs(res) <= tol
        if new_keep.sum() < 4 or np.array_equal(new_keep, keep):
            keep = new_keep if new_keep.sum() >= 4 else keep
            break
        keep = new_keep
    p = pts[keep]
    c = p.mean(axis=0)
    _, _, vt = np.linalg.svd(p - c, full_matrices=False)
    d = vt[0]
    n = np.array([-d[1], d[0]])
    rms = float(np.sqrt(np.mean(((p - c) @ n) ** 2)))
    return c, d, rms, float(keep.mean())


def _intersect(c1: np.ndarray, d1: np.ndarray, c2: np.ndarray, d2: np.ndarray) -> np.ndarray | None:
    A = np.column_stack([d1, -d2])
    if abs(np.linalg.det(A)) < 1e-9:
        return None
    s, _ = np.linalg.solve(A, c2 - c1)
    return c1 + s * d1


def _refine_rect_edges(gs: np.ndarray, box: np.ndarray, polarity: int = 0) -> tuple[np.ndarray, float, float] | None:
    """Refine a rectangle's four edges from gradient peaks of profiles taken across each side.

    ``box`` is the (4, 2) corner array of the initial rectangle (px). Returns (refined corners (4, 2), mean line
    rms in px, fraction of usable profiles) or None if a side cannot be fitted.
    """
    h_img, w_img = gs.shape[:2]
    ctr = box.mean(axis=0)
    step = 0.25
    corners_lines: list[tuple[np.ndarray, np.ndarray]] = []
    rms_all: list[float] = []
    frac_all: list[float] = []
    side_len = [float(np.linalg.norm(box[(k + 1) % 4] - box[k])) for k in range(4)]
    hw = float(np.clip(0.15 * min(side_len), 3.0, 10.0))
    ts = np.arange(-hw, hw + step / 2, step)
    for k in range(4):
        a, b = box[k], box[(k + 1) % 4]
        L = side_len[k]
        if L < 4:
            return None
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        mid = (a + b) / 2
        if np.dot(n, mid - ctr) < 0:  # make the normal point outward
            n = -n
        n_s = int(np.clip(round(L / 2.0), 8, 120))
        ss = np.linspace(-0.42 * L, 0.42 * L, n_s)  # stay clear of the corners
        base = mid[None, :] + ss[:, None] * u[None, :]
        xs = (base[:, 0:1] + ts[None, :] * n[0]).astype(np.float32)
        ys = (base[:, 1:2] + ts[None, :] * n[1]).astype(np.float32)
        prof = cv2.remap(gs, xs, ys, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        g = _profile_gradient(prof, step)
        if polarity == 0:
            peak = g[np.arange(n_s), np.abs(g).argmax(axis=1)]
            polarity = 1 if np.median(peak) >= 0 else -1
        gsg = g * polarity
        idx = gsg.argmax(axis=1)
        rows = np.arange(n_s)
        valid = (idx > 0) & (idx < len(ts) - 1)
        strength = gsg[rows, idx]
        km, kp = np.clip(idx - 1, 0, len(ts) - 1), np.clip(idx + 1, 0, len(ts) - 1)
        ym, y0, yp = gsg[rows, km], strength, gsg[rows, kp]
        den = ym - 2 * y0 + yp
        off = np.where(np.abs(den) > 1e-9, 0.5 * (ym - yp) / np.where(np.abs(den) > 1e-9, den, 1.0), 0.0)
        t_edge = ts[idx] + np.clip(off, -1, 1) * step
        pts = base + t_edge[:, None] * n[None, :]
        inside = (pts[:, 0] >= 0) & (pts[:, 0] <= w_img - 1) & (pts[:, 1] >= 0) & (pts[:, 1] <= h_img - 1)
        valid &= inside & (strength > 0)
        if valid.sum() >= 6:
            valid &= strength >= 0.25 * float(np.median(strength[valid]))
        if valid.sum() < 4:
            return None
        fit = _fit_line_robust(pts[valid], tol=1.5)
        if fit is None:
            return None
        c, d, rms, frac = fit
        if rms > 0.5:  # noisy edge: refit with a tolerance matched to the scatter
            nrm = np.array([-d[1], d[0]])
            fit = _fit_line_robust(pts[valid], tol=_robust_tol((pts[valid] - c) @ nrm, lo=1.5)) or fit
            c, d, rms, frac = fit
        corners_lines.append((c, d))
        rms_all.append(rms)
        frac_all.append(frac * float(valid.mean()))
    corners = []
    for k in range(4):
        c1, d1 = corners_lines[(k - 1) % 4]
        c2, d2 = corners_lines[k]
        p = _intersect(c1, d1, c2, d2)
        if p is None:
            return None
        corners.append(p)
    return np.asarray(corners), float(np.mean(rms_all)), float(np.mean(frac_all))


def measure_rect(rect: RectifiedImage, roi_mm: tuple[float, float, float, float] | None = None, *,
                 polarity: Polarity = "dark", threshold: float | None = None,
                 min_area_mm2: float = 4.0, refine: bool = True) -> RectMeasure | None:
    """Minimum-area rectangle of the dominant (largest) outline in the ROI, in mm. None if nothing is found.

    The rectangle from the thresholded outline is refined (``refine=True``) by fitting each side to the
    gradient peaks of intensity profiles taken across it, so the result does not depend on the threshold.
    """
    crop = rect.crop_mm(roi_mm)
    contours = _object_contours(crop, polarity, threshold, min_area_mm2)
    if not contours:
        return None
    c = contours[0]
    (cx, cy), (w, h), ang = cv2.minAreaRect(c.astype(np.float32))
    w, h = w + 1.0, h + 1.0  # contour runs through boundary pixel centres: half a pixel inside on every side
    box = np.asarray(cv2.boxPoints(((cx, cy), (w, h), ang)), dtype=np.float64)
    area = cv2.contourArea(c) + 0.5 * cv2.arcLength(c, True)  # area of the half-pixel-offset outline
    fill = float(area / max(w * h, 1e-9))
    conf = float(np.clip(1.0 - 3.0 * (1.0 - min(fill, 1.0)), 0.0, 1.0))

    if refine:
        gs = cv2.GaussianBlur(crop.gray.astype(np.float32), (0, 0), 0.8)
        pol = 0 if polarity == "any" else (1 if polarity == "dark" else -1)
        ref = _refine_rect_edges(gs, box, pol)
        if ref is not None:
            corners, rms, frac = ref
            # accept only if the refined corners stayed close to the initial box
            if np.linalg.norm(corners - box, axis=1).max() <= max(4.0, 0.05 * max(w, h)):
                box = corners
                conf = float(np.clip(conf * np.clip(1.0 - rms / 2.0, 0.2, 1.0) * np.clip(frac / 0.8, 0.0, 1.0), 0.0, 1.0))
    # sizes and orientation from the (possibly refined) corners
    s01 = np.linalg.norm(box[1] - box[0])
    s12 = np.linalg.norm(box[2] - box[1])
    s23 = np.linalg.norm(box[3] - box[2])
    s30 = np.linalg.norm(box[0] - box[3])
    len_a, len_b = (s01 + s23) / 2, (s12 + s30) / 2
    if len_a >= len_b:
        w, h = len_a, len_b
        d = ((box[1] - box[0]) - (box[3] - box[2])) / 2
    else:
        w, h = len_b, len_a
        d = ((box[2] - box[1]) - (box[0] - box[3])) / 2
    # image y points down: negate to report counter-clockwise-on-paper angles
    angle = -math.degrees(math.atan2(d[1], d[0]))
    while angle <= -90.0:
        angle += 180.0
    while angle > 90.0:
        angle -= 180.0
    mpp = crop.mm_per_px
    ctr = box.mean(axis=0)
    cmm = crop.px_to_mm(ctr)
    return RectMeasure(float(w * mpp), float(h * mpp), float(angle), conf, float(cmm[0]), float(cmm[1]),
                       crop.px_to_mm(box))


# ---- OpenSCAD ----------------------------------------------------------------------------------------------

def to_openscad_polygon(poly_mm: np.ndarray, *, flip_y: bool = True, center: bool = True, decimals: int = 3,
                        name: str | None = None) -> str:
    """Render a polygon (N, 2) in mm as an OpenSCAD ``polygon([...])`` statement.

    Sheet coordinates have +y down while OpenSCAD has +y up, so ``flip_y`` mirrors y to reproduce the shape as
    seen in the photo. ``center`` translates the bounding-box centre to the origin. ``name`` wraps the polygon
    in a module of that name.
    """
    pts = np.asarray(poly_mm, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 3:
        raise ValueError("a polygon needs at least 3 points")
    if len(pts) > 3 and np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    if flip_y:
        pts = pts * np.array([1.0, -1.0])
    if center:
        pts = pts - (pts.min(axis=0) + pts.max(axis=0)) / 2
    fmt = f"{{:.{decimals}f}}"
    coords = ", ".join(f"[{fmt.format(x)}, {fmt.format(y)}]" for x, y in pts)
    body = f"polygon(points=[{coords}]);"
    if name:
        return f"module {name}() {{\n    {body}\n}}\n"
    return body


__all__ = ["CircleMeasure", "Polarity", "RectMeasure", "find_circles", "find_outline", "measure_rect",
           "to_openscad_polygon"]
