"""Capture grading: is this photo good enough to measure from, and if not, what should the user change?

Sharpness is the variance of the Laplacian computed at a canonical scale (the image is resized so its long
side is ~1000 px before a light denoising blur), which makes the threshold independent of the camera's
resolution. It is backed by an edge-width estimate (local contrast / gradient magnitude on strong edges, a
direct read-out of the blur in pixels) so a sparse or noisy scene does not fool it. Exposure looks at mean
brightness and clipped pixels; when a sheet is expected the marker count, marker size and camera tilt are
checked too.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from kintsugi.measure.aruco import Marker, detect_markers, estimate_tilt_deg
from kintsugi.measure.sheet import SHEET_LAYOUT, SheetLayout

CANONICAL_LONG_SIDE = 1000
# Laplacian variance at the canonical scale. A sheet photo is mostly white paper, so even a sharp one only
# reaches ~20-30 (a blur of 2 px on a 1600 px frame gives ~9, 3 px gives ~4).
SHARPNESS_MIN = 8.0
# Edge transition width in canonical px (long side 1000): a sharp photo reads ~3.1, a 1600 px photo blurred by
# a Gaussian of sigma 2 px ~4.0, sigma 3 ~5.1, sigma 6 ~7.
EDGE_WIDTH_MAX_PX = 5.0
TILT_MAX_DEG = 20.0
MIN_MARKERS = 4
MIN_MARKER_PX = 30.0
BRIGHTNESS_MIN = 70.0
BRIGHTNESS_MAX = 245.0
CLIP_HIGH_MAX = 0.15  # fraction of pixels at >= 253
CLIP_LOW_MAX = 0.35  # fraction of pixels at <= 3


@dataclass
class CaptureGrade:
    sharpness: float
    sharpness_ok: bool
    exposure_ok: bool
    mean_brightness: float
    markers_found: int
    tilt_deg: float | None
    tilt_ok: bool
    ok: bool
    instructions: list[str] = field(default_factory=list)
    edge_width_px: float | None = None  # estimated blur (edge transition width) at the canonical scale
    marker_px: float | None = None  # mean marker side in photo pixels
    clipped_high: float = 0.0
    clipped_low: float = 0.0
    markers: list[Marker] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        return {
            "sharpness": round(self.sharpness, 2), "sharpness_ok": self.sharpness_ok,
            "exposure_ok": self.exposure_ok, "mean_brightness": round(self.mean_brightness, 1),
            "markers_found": self.markers_found, "tilt_deg": None if self.tilt_deg is None else round(self.tilt_deg, 1),
            "tilt_ok": self.tilt_ok, "ok": self.ok, "instructions": list(self.instructions),
            "edge_width_px": None if self.edge_width_px is None else round(self.edge_width_px, 2),
            "marker_px": None if self.marker_px is None else round(self.marker_px, 1),
            "clipped_high": round(self.clipped_high, 4), "clipped_low": round(self.clipped_low, 4),
        }


def _canonical_gray(img_bgr: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
    long_side = max(g.shape[:2])
    if long_side > CANONICAL_LONG_SIDE:
        s = CANONICAL_LONG_SIDE / long_side
        g = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return g


def laplacian_variance(img_bgr: np.ndarray) -> float:
    """Variance of the Laplacian at the canonical scale after a sigma-1 denoising blur."""
    g = _canonical_gray(img_bgr).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), 1.0)
    return float(cv2.Laplacian(g, cv2.CV_32F).var())


def edge_width_px(img_bgr: np.ndarray, min_contrast: float = 40.0, min_edge_px: int = 150) -> float | None:
    """Median transition width (px, canonical scale) of real edges: local contrast / gradient at the edge ridge.

    Ridge pixels come from Canny's non-maximum suppression with low thresholds, gated by a local contrast of at
    least ``min_contrast`` grey levels so noise never qualifies. A sharp photo reads about 3 px; the value grows
    with the blur (see ``EDGE_WIDTH_MAX_PX``). Returns None when fewer than ``min_edge_px`` edge pixels exist
    (a featureless frame), in which case the Laplacian variance decides.
    """
    g = _canonical_gray(img_bgr).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), 0.7)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3) / 8.0  # per-pixel gradient
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    mag = np.hypot(gx, gy)
    k = np.ones((9, 9), np.uint8)
    contrast = cv2.dilate(g, k) - cv2.erode(g, k)
    ridge = cv2.Canny(np.clip(g, 0, 255).astype(np.uint8), 10, 30, L2gradient=True) > 0
    strong = ridge & (contrast >= min_contrast)
    if strong.sum() < min_edge_px:
        return None
    width = contrast[strong] / np.maximum(mag[strong], 1e-3)
    return float(np.median(width))


def grade_capture(img_bgr: np.ndarray, expect_sheet: bool = True, layout: SheetLayout = SHEET_LAYOUT,
                  markers: list[Marker] | None = None) -> CaptureGrade:
    """Grade a photo and produce specific retake instructions.

    ``ok`` requires a sharp, well-exposed image and, when ``expect_sheet``, at least 4 markers that are large
    enough and a camera tilt of at most 20 degrees. Pass ``markers`` to reuse an earlier detection.
    """
    h, w = img_bgr.shape[:2]
    instructions: list[str] = []

    # sharpness
    lap = laplacian_variance(img_bgr)
    ew = edge_width_px(img_bgr)
    sharp_by_lap = lap >= SHARPNESS_MIN
    sharp_by_edges = ew is not None and ew <= EDGE_WIDTH_MAX_PX
    very_blurry = ew is not None and ew > 1.6 * EDGE_WIDTH_MAX_PX
    sharpness_ok = (sharp_by_lap or sharp_by_edges) and not very_blurry
    if not sharpness_ok:
        detail = f" (edge width {ew:.1f} px)" if ew is not None else f" (sharpness {lap:.0f})"
        instructions.append("Image is blurry" + detail + ": hold still, tap the sheet to focus, and use more light.")

    # exposure
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
    mean_b = float(g.mean())
    clipped_high = float((g >= 253).mean())
    clipped_low = float((g <= 3).mean())
    exposure_ok = True
    if mean_b < BRIGHTNESS_MIN or clipped_low > CLIP_LOW_MAX:
        exposure_ok = False
        instructions.append(f"Too dark (mean brightness {mean_b:.0f}): add light or increase exposure.")
    elif mean_b > BRIGHTNESS_MAX or clipped_high > CLIP_HIGH_MAX:
        exposure_ok = False
        instructions.append(f"Too bright ({100 * clipped_high:.0f}% of pixels clipped): reduce exposure or avoid direct light.")

    # sheet
    markers_found = 0
    tilt: float | None = None
    tilt_ok = True
    marker_px: float | None = None
    if expect_sheet:
        if markers is None:
            markers = detect_markers(img_bgr, layout=layout)
        known = [m for m in markers if m.id in layout.markers]
        markers_found = len(known)
        if known:
            marker_px = float(np.mean([m.side_px for m in known]))
        if markers_found < MIN_MARKERS:
            need = layout.n_markers
            if markers_found == 0:
                instructions.append("No calibration markers found: put the object on the printed sheet and keep the "
                                    "whole sheet in the frame.")
            else:
                instructions.append(f"Only {markers_found} of {need} markers found (need at least {MIN_MARKERS}): keep the "
                                    "sheet's corners in the frame and uncovered, and avoid glare on the markers.")
        if marker_px is not None and marker_px < MIN_MARKER_PX:
            instructions.append(f"Move closer: markers are only {marker_px:.0f} px across (need at least {MIN_MARKER_PX:.0f}).")
        if markers_found >= 2:
            tilt = estimate_tilt_deg(known, (w, h), layout)
            if tilt is not None and tilt > TILT_MAX_DEG:
                tilt_ok = False
                instructions.append(f"Hold the phone directly above the sheet, parallel to it: tilt is {tilt:.0f} degrees "
                                    f"(keep it under {TILT_MAX_DEG:.0f}).")
    else:
        markers = markers or []

    ok = sharpness_ok and exposure_ok
    if expect_sheet:
        ok = ok and markers_found >= MIN_MARKERS and tilt_ok and (marker_px is None or marker_px >= MIN_MARKER_PX)
    if ok and not instructions:
        instructions.append("Good capture.")
    return CaptureGrade(lap, sharpness_ok, exposure_ok, mean_b, markers_found, tilt, tilt_ok, ok, instructions,
                        edge_width_px=ew, marker_px=marker_px, clipped_high=clipped_high, clipped_low=clipped_low,
                        markers=list(markers))


__all__ = ["CaptureGrade", "EDGE_WIDTH_MAX_PX", "MIN_MARKERS", "MIN_MARKER_PX", "SHARPNESS_MIN", "TILT_MAX_DEG",
           "edge_width_px", "grade_capture", "laplacian_variance"]
