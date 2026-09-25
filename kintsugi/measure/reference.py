"""Scale from a reference object (coin or credit card) when no calibration sheet is in the photo.

Without the sheet there is no plane homography, so measurements assume a roughly top-down photo: the scale
(mm per pixel) is taken from the reference object's apparent size and applied to objects lying in the same
plane at about the same distance. Tilt makes objects far from the reference read wrong (see the module's
limitations in :func:`measure_with_reference`); the sheet path should be preferred for anything critical.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from kintsugi.checks.geometry import fit_circle_robust
from kintsugi.measure.aruco import RectifiedImage
from kintsugi.measure.planar import (
    CircleMeasure,
    _angular_coverage,
    _canny_thresholds,
    _hough_candidates,
    _refine_circle,
    find_circles,
    find_outline,
    measure_rect,
)

# Reference sizes in mm: coins by diameter, cards as (width, height). ISO/IEC 7810 ID-1 is 85.60 x 53.98.
REFERENCES: dict[str, float | tuple[float, float]] = {
    "us_quarter": 24.26,
    "us_penny": 19.05,
    "us_nickel": 21.21,
    "us_dime": 17.91,
    "credit_card": (85.60, 53.98),
    "euro_1": 23.25,
    "euro_2": 25.75,
}
CARD_ASPECT = 85.60 / 53.98  # 1.586
COIN_KINDS = tuple(k for k, v in REFERENCES.items() if not isinstance(v, tuple))
CARD_KINDS = tuple(k for k, v in REFERENCES.items() if isinstance(v, tuple))
COPPER_COINS = ("us_penny",)


@dataclass
class ReferenceDetection:
    """A reference object found in the photo. ``size_px`` is the coin diameter or the card (w, h) in pixels;
    ``center_px`` is (x, y); ``conf`` in [0, 1]."""

    kind: str
    mm_per_px: float
    center_px: tuple[float, float]
    size_px: float | tuple[float, float]
    conf: float
    corners_px: np.ndarray | None = field(default=None, repr=False)  # card only, (4, 2)
    notes: list[str] = field(default_factory=list)

    @property
    def size_mm(self) -> float | tuple[float, float]:
        return REFERENCES[self.kind]

    @property
    def radius_px(self) -> float:
        """Circumscribed radius in px (half the diameter for coins, half the diagonal for cards)."""
        if isinstance(self.size_px, tuple):
            return 0.5 * math.hypot(*self.size_px)
        return 0.5 * float(self.size_px)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "mm_per_px": round(self.mm_per_px, 6),
                "center_px": [round(v, 2) for v in self.center_px],
                "size_px": [round(v, 2) for v in self.size_px] if isinstance(self.size_px, tuple) else round(self.size_px, 2),
                "conf": round(self.conf, 3), "notes": list(self.notes)}


# ---- coins ------------------------------------------------------------------------------------------------

def _is_copper(img_bgr: np.ndarray, cx: float, cy: float, r: float) -> bool:
    """Penny heuristic: the coin's interior is distinctly red/orange (R > G > B with a warm hue)."""
    if img_bgr.ndim != 3:
        return False
    h, w = img_bgr.shape[:2]
    rr = max(int(r * 0.6), 2)
    x0, x1 = max(int(cx) - rr, 0), min(int(cx) + rr + 1, w)
    y0, y1 = max(int(cy) - rr, 0), min(int(cy) + rr + 1, h)
    patch = img_bgr[y0:y1, x0:x1].reshape(-1, 3).astype(np.float64)
    if len(patch) == 0:
        return False
    b, g, r_ = patch.mean(axis=0)
    return bool(r_ > g * 1.12 and g > b * 1.05 and (r_ - b) > 25)


def _coin_score(g8: np.ndarray, cx: float, cy: float, r: float, cov: float, systematic: float,
                near_px: tuple[float, float] | None) -> tuple[float, dict[str, float]]:
    """Coin plausibility from circle quality (coverage, systematic deviation from a circle in px), edge
    contrast and a mid-tone (metallic) interior."""
    h, w = g8.shape[:2]
    yy, xx = np.ogrid[0:h, 0:w]
    d2 = (xx - cx) ** 2 + (yy - cy) ** 2
    inner = g8[d2 <= (0.75 * r) ** 2]
    ring = g8[(d2 >= (1.15 * r) ** 2) & (d2 <= (1.5 * r) ** 2)]
    if len(inner) < 10 or len(ring) < 10:
        return 0.0, {}
    tone = float(np.median(inner))
    bg = float(np.median(ring))
    contrast = abs(tone - bg)
    w_shape = float(np.clip((cov - 0.5) / 0.45, 0, 1)) * float(np.clip(1.0 - systematic / max(0.02 * r, 1.0), 0.2, 1.0))
    w_contrast = float(np.clip(contrast / 40.0, 0.0, 1.0))
    # coins are metallic mid-tones; very dark or paper-white discs are more likely the part being measured
    w_tone = 1.0 if 60.0 <= tone <= 215.0 else 0.45
    score = w_shape * w_contrast * w_tone
    if near_px is not None:
        dist = math.hypot(cx - near_px[0], cy - near_px[1])
        score *= float(np.clip(1.0 - dist / (6.0 * r), 0.1, 1.0))
    return float(score), {"tone": tone, "background": bg, "contrast": contrast}


def detect_coin(img_bgr: np.ndarray, kind: str = "us_quarter", *, near_px: tuple[float, float] | None = None,
                min_frac: float = 0.02, max_frac: float = 0.45) -> ReferenceDetection | None:
    """Find the most coin-like circle: HoughCircles candidates plus circular contours, both refined by radial
    edge profiles. ``kind`` names the coin assumed for the scale; a penny is recognised by its copper colour
    when the image is in colour. ``near_px`` (a user tap) favours circles close to that point."""
    g8 = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
    h, w = g8.shape[:2]
    short = min(h, w)
    min_r, max_r = 0.5 * min_frac * short, 0.5 * max_frac * short
    gs = cv2.GaussianBlur(g8.astype(np.float32), (0, 0), 1.0)
    g_blur = cv2.GaussianBlur(g8, (0, 0), 1.2)
    low, high = _canny_thresholds(g_blur)

    cands: list[tuple[float, float, float]] = []
    cands += _hough_candidates(g8, min_r, max_r, high)
    edges = cv2.Canny(g_blur, low, high, L2gradient=True)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    for c in contours:
        pts = c.reshape(-1, 2).astype(np.float64)
        if len(pts) < max(16, int(math.pi * min_r)):
            continue
        ext = pts.max(axis=0) - pts.min(axis=0)
        if ext.max() < 1.2 * min_r or ext.max() > 2.4 * max_r:
            continue
        try:
            fit = fit_circle_robust(pts, tol=1.5)
        except (ValueError, np.linalg.LinAlgError):
            continue
        if not np.isfinite([fit.cx, fit.cy, fit.r]).all() or fit.r < min_r or fit.r > max_r:
            continue
        d = np.abs(np.hypot(pts[:, 0] - fit.cx, pts[:, 1] - fit.cy) - fit.r)
        inl = d <= max(1.5, 0.01 * fit.r)
        if inl.mean() >= 0.5 and _angular_coverage(pts[inl], fit.cx, fit.cy) >= 0.6:
            cands.append((fit.cx, fit.cy, fit.r))

    best: ReferenceDetection | None = None
    best_score = 0.0
    seen: list[tuple[float, float, float]] = []
    for cx, cy, r in cands:
        if any(math.hypot(cx - s[0], cy - s[1]) < max(3.0, 0.05 * s[2]) and abs(r - s[2]) < max(3.0, 0.05 * s[2]) for s in seen):
            continue
        ref = _refine_circle(gs, cx, cy, r)
        if ref is None:
            continue
        fit, cov, systematic = ref.fit, ref.coverage, ref.systematic
        if fit.r < min_r or fit.r > max_r or cov < 0.6 or ref.consistency < 0.6 or ref.contrast < 10.0:
            continue
        seen.append((fit.cx, fit.cy, fit.r))
        score, info = _coin_score(g8, fit.cx, fit.cy, fit.r, cov, systematic, near_px)
        if score > best_score:
            coin = kind
            notes = []
            if coin not in COIN_KINDS:
                coin = "us_quarter"
            if _is_copper(img_bgr, fit.cx, fit.cy, fit.r):
                if coin not in COPPER_COINS:
                    notes.append(f"copper-coloured coin: assumed us_penny instead of {coin}")
                    coin = "us_penny"
            d_mm = float(REFERENCES[coin])
            best_score = score
            best = ReferenceDetection(coin, d_mm / (2 * fit.r), (float(fit.cx), float(fit.cy)), float(2 * fit.r),
                                      float(np.clip(score, 0, 1)), notes=notes + [f"interior tone {info.get('tone', 0):.0f}"])
    return best


# ---- cards ------------------------------------------------------------------------------------------------

def _order_quad(q: np.ndarray) -> np.ndarray:
    """Order 4 points TL, TR, BR, BL."""
    s = q.sum(axis=1)
    d = q[:, 0] - q[:, 1]
    return np.array([q[np.argmin(s)], q[np.argmax(d)], q[np.argmax(s)], q[np.argmin(d)]], dtype=np.float64)


def detect_card(img_bgr: np.ndarray, *, near_px: tuple[float, float] | None = None,
                aspect_tol: float = 0.12, min_area_frac: float = 0.01) -> ReferenceDetection | None:
    """Find an ID-1 card (85.60 x 53.98 mm) as a convex quadrilateral contour with the right aspect ratio.

    Both an Otsu segmentation and Canny edges are tried; the quadrilateral whose aspect ratio is closest to
    1.586 wins. The scale is the mean of the width and height scales, which partly cancels a small tilt."""
    g8 = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
    h, w = g8.shape[:2]
    area_img = float(h * w)
    g_blur = cv2.GaussianBlur(g8, (0, 0), 1.5)
    low, high = _canny_thresholds(g_blur)
    masks: list[np.ndarray] = []
    for flag in (cv2.THRESH_BINARY, cv2.THRESH_BINARY_INV):
        _, m = cv2.threshold(g_blur, 0, 255, flag + cv2.THRESH_OTSU)
        masks.append(m)
    edges = cv2.Canny(g_blur, low, high, L2gradient=True)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    masks.append(edges)

    best: ReferenceDetection | None = None
    best_err = float("inf")
    for m in masks:
        contours, _ = cv2.findContours(m, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area_frac * area_img or area > 0.9 * area_img:
                continue
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) != 4 or not cv2.isContourConvex(approx):
                continue
            q = _order_quad(approx.reshape(4, 2).astype(np.float64))
            top, bottom = np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[3])
            left, right = np.linalg.norm(q[3] - q[0]), np.linalg.norm(q[2] - q[1])
            a, b = (top + bottom) / 2, (left + right) / 2
            long_px, short_px = max(a, b), min(a, b)
            if short_px < 8:
                continue
            aspect = long_px / short_px
            err = abs(aspect - CARD_ASPECT) / CARD_ASPECT
            if err > aspect_tol:
                continue
            # a real card's sides are parallel and its quad fills its bounding rectangle
            par = abs(top - bottom) / max(top, bottom) + abs(left - right) / max(left, right)
            fill = area / max(cv2.contourArea(cv2.convexHull(c)), 1e-9)
            score = err + 0.5 * par + 0.5 * (1.0 - fill)
            if near_px is not None:
                ctr = q.mean(axis=0)
                score += 0.2 * math.hypot(ctr[0] - near_px[0], ctr[1] - near_px[1]) / long_px
            if score < best_err:
                best_err = score
                wmm, hmm = REFERENCES["credit_card"]  # type: ignore[misc]
                mm_per_px = 0.5 * (wmm / long_px + hmm / short_px)
                conf = float(np.clip(1.0 - err / aspect_tol, 0, 1) * np.clip(1.0 - par, 0.2, 1) * fill)
                ctr = q.mean(axis=0)
                best = ReferenceDetection("credit_card", float(mm_per_px), (float(ctr[0]), float(ctr[1])),
                                          (float(long_px), float(short_px)), conf, corners_px=q)
    return best


# ---- public API -------------------------------------------------------------------------------------------

def detect_reference(img_bgr: np.ndarray, kind: str = "auto", *,
                     near_px: tuple[float, float] | None = None) -> ReferenceDetection | None:
    """Find the reference object and return its scale.

    ``kind`` is a key of :data:`REFERENCES`, ``"coin"`` (a US quarter unless the coin looks copper), ``"card"``,
    or ``"auto"`` (tries a card and a coin and keeps the more confident one). Coins cannot be told apart by
    size alone, so name the coin when you know it; ``near_px`` disambiguates when several round objects are
    in the picture. Returns None when nothing plausible is found.
    """
    kind = kind.lower()
    if kind in CARD_KINDS or kind == "card":
        return detect_card(img_bgr, near_px=near_px)
    if kind in COIN_KINDS:
        return detect_coin(img_bgr, kind, near_px=near_px)
    if kind == "coin":
        return detect_coin(img_bgr, "us_quarter", near_px=near_px)
    if kind != "auto":
        raise ValueError(f"unknown reference kind {kind!r}; use one of {sorted(REFERENCES)}, 'coin', 'card' or 'auto'")
    card = detect_card(img_bgr, near_px=near_px)
    coin = detect_coin(img_bgr, "us_quarter", near_px=near_px)
    if card is None:
        return coin
    if coin is None:
        return card
    # a card's aspect-ratio match is a strong cue; a coin needs a clear margin to win
    return coin if coin.conf > card.conf + 0.15 else card


def measure_with_reference(img_bgr: np.ndarray, ref: ReferenceDetection,
                           roi_px: tuple[float, float, float, float] | None = None, *,
                           min_d_mm: float = 3.0, max_d_mm: float | None = None,
                           simplify_mm: float = 0.2) -> dict[str, Any]:
    """Measure the largest circle and outline in ``roi_px`` (x0, y0, x1, y1) using the reference scale.

    The reference object itself is excluded from the results. Everything is returned in mm, in a photo-aligned
    frame whose origin is the photo's top-left pixel (``mm_per_px`` scales pixel coordinates). Limitations:
    no perspective correction (a tilt of t degrees compresses one axis by ~cos t, and objects at a different
    distance than the reference scale by the depth ratio), and circle sizes of a tilted disc are the mean of
    the ellipse axes.
    """
    h, w = img_bgr.shape[:2]
    rect = RectifiedImage(img_bgr, ref.mm_per_px, (0.0, 0.0))
    if roi_px is None:
        roi_mm = None
    else:
        x0, y0, x1, y1 = roi_px
        roi_mm = tuple(float(v) * ref.mm_per_px for v in (x0, y0, x1, y1))
    if max_d_mm is None:
        max_d_mm = 0.95 * min(w, h) * ref.mm_per_px
    ref_c = np.asarray(ref.center_px, dtype=np.float64) * ref.mm_per_px
    ref_r_mm = ref.radius_px * ref.mm_per_px

    def is_reference(cx: float, cy: float, d: float) -> bool:
        near = math.hypot(cx - ref_c[0], cy - ref_c[1]) < 0.6 * max(ref_r_mm, d / 2)
        return near and abs(d / 2 - ref_r_mm) < 0.35 * ref_r_mm

    circles = [c for c in find_circles(rect, min_d_mm, max_d_mm, roi_mm) if not is_reference(c.cx, c.cy, c.d)]
    circles.sort(key=lambda c: (-c.d, -c.conf))
    outlines = []
    for p in find_outline(rect, roi_mm, simplify_mm):
        ctr = p.mean(axis=0)
        ext = float(np.hypot(*(p.max(axis=0) - p.min(axis=0))))
        if not is_reference(float(ctr[0]), float(ctr[1]), ext):
            outlines.append(p)
    rect_m = None
    if outlines:
        # rectangle of the largest non-reference outline
        p = outlines[0]
        pad = 2.0
        sub_roi = (float(p[:, 0].min() - pad), float(p[:, 1].min() - pad), float(p[:, 0].max() + pad), float(p[:, 1].max() + pad))
        try:
            rect_m = measure_rect(rect, sub_roi)
        except ValueError:
            rect_m = None
    largest: CircleMeasure | None = circles[0] if circles else None
    return {
        "reference": ref.to_dict(),
        "mm_per_px": ref.mm_per_px,
        "circle": largest.to_dict() if largest else None,
        "circles": [c.to_dict() for c in circles],
        "outline_mm": outlines[0].round(3).tolist() if outlines else None,
        "outlines_mm": [o.round(3).tolist() for o in outlines],
        "rect": rect_m.to_dict() if rect_m else None,
        "notes": ["no perspective correction: objects should lie in the reference's plane, close to it"],
    }


def verify_sheet_scale(rect: RectifiedImage, kind: str = "us_quarter",
                       near_mm: tuple[float, float] | None = None, tol: float = 0.08) -> dict[str, Any] | None:
    """Measure a real coin lying on the (rectified) sheet to verify the print scale.

    A sheet printed at "fit to page" scales its markers too, so the homography alone cannot notice it; a coin
    of known diameter can. Put the coin inside the grid (not on its printed outline, which peeks out from under
    the coin and is excluded by :func:`find_circles`). Looks for a circle within ``tol`` (relative) of the
    coin's nominal diameter, closest to ``near_mm`` if given, and returns ``{"kind", "measured_mm",
    "nominal_mm", "scale", "ok", "circle"}`` where ``scale`` = measured / nominal and ``ok`` means the print is
    within 1%. Returns None if no such circle is found.
    """
    if kind not in COIN_KINDS:
        raise ValueError(f"kind must be a coin: {COIN_KINDS}")
    nominal = float(REFERENCES[kind])
    # "dark" polarity: a solid coin is darker than the paper, while the printed outline (a thin line that
    # always reads nominal, whatever the print scale) is removed by the line suppression
    circles = find_circles(rect, nominal * (1 - tol), nominal * (1 + tol), polarity="dark")
    if not circles:
        return None
    if near_mm is not None:
        circles.sort(key=lambda c: math.hypot(c.cx - near_mm[0], c.cy - near_mm[1]))
    c = circles[0]
    scale = c.d / nominal
    return {"kind": kind, "measured_mm": c.d, "nominal_mm": nominal, "scale": scale,
            "ok": abs(scale - 1.0) <= 0.01, "circle": c.to_dict()}


__all__ = ["CARD_ASPECT", "CARD_KINDS", "COIN_KINDS", "REFERENCES", "ReferenceDetection", "detect_card", "detect_coin",
           "detect_reference", "measure_with_reference", "verify_sheet_scale"]
