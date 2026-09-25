"""Synthetic photos of the calibration sheet with exact ground truth.

``synth_photo`` renders the sheet, draws objects on it (dark discs, rings, rectangles at known mm positions),
and photographs the result with a pinhole camera tilted by ``tilt_deg``: the sheet plane is rotated, projected
with a focal length that makes it fill ~80% of the frame, then blurred and noised. The returned truth carries
the shapes in mm and the exact homography (photo px -> sheet mm), so every stage of the measurement pipeline can
be scored against it.

Camera model (OpenCV conventions, pixel-centre coordinates):

* world frame = sheet frame (mm, +x right, +y down, +z into the table), origin at the paper centre;
* ``R = Rz(roll) . Rx(tilt) . Rz(yaw)``: ``yaw`` spins the sheet in the image, ``tilt`` leans the camera so the
  sheet's +y side recedes, ``roll`` turns the camera about its optical axis;
* the camera sits ``distance_mm`` from the sheet centre along its optical axis and is shifted sideways so the
  sheet's projection is centred in the frame.
"""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np

from kintsugi.measure.sheet import PAPER_SIZES_MM, SHEET_LAYOUT, SheetLayout, render_sheet_image

DEFAULT_OBJECT_COLOR = (45, 45, 45)  # BGR: dark plastic
TABLE_COLOR = (118, 126, 134)  # BGR: what shows around the sheet
PLAIN_BACKGROUND = (238, 238, 238)  # BGR: a light desk when no sheet is used

Shape = dict[str, Any]


def circle(cx: float, cy: float, d: float, color: tuple[int, int, int] = DEFAULT_OBJECT_COLOR) -> Shape:
    """A filled disc: centre (cx, cy) mm, diameter d mm."""
    return {"type": "circle", "cx": float(cx), "cy": float(cy), "d": float(d), "color": tuple(color)}


def ring(cx: float, cy: float, d_outer: float, d_inner: float,
         color: tuple[int, int, int] = DEFAULT_OBJECT_COLOR) -> Shape:
    """A filled annulus (a washer / bearing seen from above): the sheet shows through the hole."""
    return {"type": "ring", "cx": float(cx), "cy": float(cy), "d_outer": float(d_outer), "d_inner": float(d_inner),
            "color": tuple(color)}


def rect(cx: float, cy: float, w: float, h: float, angle_deg: float = 0.0,
         color: tuple[int, int, int] = DEFAULT_OBJECT_COLOR) -> Shape:
    """A filled rectangle w x h mm centred at (cx, cy), rotated by angle_deg (counter-clockwise on paper)."""
    return {"type": "rect", "cx": float(cx), "cy": float(cy), "w": float(w), "h": float(h),
            "angle_deg": float(angle_deg), "color": tuple(color)}


# ---- drawing (exact-ish anti-aliasing from signed distance) ------------------------------------------

def _blend(img: np.ndarray, y0: int, y1: int, x0: int, x1: int, cov: np.ndarray, color: tuple[int, ...]) -> None:
    roi = img[y0:y1, x0:x1].astype(np.float64)
    a = cov[..., None]
    col = np.asarray(color, dtype=np.float64).reshape(1, 1, -1)
    img[y0:y1, x0:x1] = np.clip(roi * (1 - a) + col * a, 0, 255).astype(np.uint8)


def _disc_coverage(xx: np.ndarray, yy: np.ndarray, cx: float, cy: float, r: float) -> np.ndarray:
    return np.clip(r - np.hypot(xx - cx, yy - cy) + 0.5, 0.0, 1.0)


def draw_shape(img: np.ndarray, shape: Shape, px_per_mm: float) -> None:
    """Draw one shape (mm units) onto a raster whose pixel (i, j) sits at (i, j) / px_per_mm mm."""
    h, w = img.shape[:2]
    s = px_per_mm
    kind = shape["type"]
    color = tuple(shape.get("color", DEFAULT_OBJECT_COLOR))
    cx, cy = shape["cx"] * s, shape["cy"] * s
    if kind in ("circle", "ring"):
        r_out = (shape["d"] if kind == "circle" else shape["d_outer"]) / 2 * s
        r_in = shape["d_inner"] / 2 * s if kind == "ring" else 0.0
        x0, x1 = max(int(cx - r_out - 2), 0), min(int(cx + r_out + 3), w)
        y0, y1 = max(int(cy - r_out - 2), 0), min(int(cy + r_out + 3), h)
        if x1 <= x0 or y1 <= y0:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float64)
        cov = _disc_coverage(xx, yy, cx, cy, r_out)
        if r_in > 0:
            cov = np.clip(cov - _disc_coverage(xx, yy, cx, cy, r_in), 0.0, 1.0)
        _blend(img, y0, y1, x0, x1, cov, color)
    elif kind == "rect":
        hw, hh = shape["w"] / 2 * s, shape["h"] / 2 * s
        ang = math.radians(shape.get("angle_deg", 0.0))
        c, sn = math.cos(ang), math.sin(ang)
        ext = math.hypot(hw, hh) + 2
        x0, x1 = max(int(cx - ext), 0), min(int(cx + ext + 1), w)
        y0, y1 = max(int(cy - ext), 0), min(int(cy + ext + 1), h)
        if x1 <= x0 or y1 <= y0:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float64)
        dx, dy = xx - cx, yy - cy
        # rotate into the rectangle frame (image y is down, so a CCW-on-paper rotation is a CW rotation here)
        u = c * dx - sn * dy
        v = sn * dx + c * dy
        sdf = np.maximum(np.abs(u) - hw, np.abs(v) - hh)
        cov = np.clip(0.5 - sdf, 0.0, 1.0)
        _blend(img, y0, y1, x0, x1, cov, color)
    else:
        raise ValueError(f"unknown shape type {kind!r}")


# ---- camera --------------------------------------------------------------------------------------------

def _rot_x(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float64)


def _rot_z(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)


def camera_for_sheet(paper_mm: tuple[float, float], tilt_deg: float, yaw_deg: float, roll_deg: float,
                     out_size: tuple[int, int], distance_mm: float, fill: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pinhole camera (K, R, t) looking at a sheet of ``paper_mm`` centred at the world origin.

    The focal length is chosen so the sheet's projected bounding box spans ``fill`` of the limiting frame
    dimension; the camera is then shifted sideways (in its own x/y) to centre that box in the frame.
    """
    W, H = paper_mm
    w, h = out_size
    R = _rot_z(math.radians(roll_deg)) @ _rot_x(math.radians(tilt_deg)) @ _rot_z(math.radians(yaw_deg))
    corners = np.array([[-W / 2, -H / 2, 0], [W / 2, -H / 2, 0], [W / 2, H / 2, 0], [-W / 2, H / 2, 0]], dtype=np.float64)
    t = np.array([0.0, 0.0, distance_mm])
    f = 1.0
    for _ in range(4):
        pc = corners @ R.T + t
        xn, yn = pc[:, 0] / pc[:, 2], pc[:, 1] / pc[:, 2]
        ext_x, ext_y = xn.max() - xn.min(), yn.max() - yn.min()
        f = fill * min(w / ext_x, h / ext_y)
        # shift the camera so the box centre lands on the principal point (depth-averaged, iterated)
        zc = float(pc[:, 2].mean())
        t = t - np.array([(xn.max() + xn.min()) / 2 * zc, (yn.max() + yn.min()) / 2 * zc, 0.0])
    K = np.array([[f, 0, (w - 1) / 2], [0, f, (h - 1) / 2], [0, 0, 1]], dtype=np.float64)
    return K, R, t


def sheet_to_image_homography(K: np.ndarray, R: np.ndarray, t: np.ndarray, paper_mm: tuple[float, float]) -> np.ndarray:
    """3x3 map from sheet mm (origin top-left) to image px for the camera (K, R, t) (world origin = sheet centre)."""
    W, H = paper_mm
    T = np.array([[1, 0, -W / 2], [0, 1, -H / 2], [0, 0, 1]], dtype=np.float64)
    P = np.column_stack([R[:, 0], R[:, 1], t])
    return K @ P @ T


# ---- the photo --------------------------------------------------------------------------------------------

def synth_photo(shapes: list[Shape], tilt_deg: float, yaw_deg: float = 0.0, roll_deg: float = 0.0,
                dpi: float = 200.0, out_size: tuple[int, int] = (1600, 1200), blur: float = 1.0, noise: float = 3.0,
                seed: int = 0, *, paper: str = "letter", sheet: bool = True, distance_mm: float = 350.0,
                fill: float = 0.8, exposure: float = 0.92, vignette: float = 0.15,
                background: tuple[int, int, int] | None = None,
                layout: SheetLayout = SHEET_LAYOUT) -> tuple[np.ndarray, dict[str, Any]]:
    """Photograph ``shapes`` lying on the calibration sheet with a tilted pinhole camera.

    Args:
        shapes: list of shape dicts from :func:`circle`, :func:`ring`, :func:`rect` (mm, sheet coordinates).
        tilt_deg: camera lean away from the sheet normal (0 = straight down).
        yaw_deg: rotation of the sheet about its normal (90 turns a portrait sheet landscape in the frame).
        roll_deg: camera rotation about its optical axis.
        dpi: resolution of the intermediate sheet raster (the "print"); the photo is resampled from it.
        out_size: (width, height) of the photo in pixels.
        blur: Gaussian blur sigma in photo pixels (0 disables).
        noise: Gaussian noise sigma in grey levels (0 disables).
        seed: RNG seed for the noise.
        paper: "letter" or "a4".
        sheet: False replaces the printed sheet by a plain light surface (for reference-object tests).
        distance_mm: camera distance from the sheet centre along the optical axis.
        fill: fraction of the limiting frame dimension the sheet's projection spans.
        exposure: multiplicative exposure (paper white 255 -> 255 * exposure) so highlights do not clip.
        vignette: relative darkening at the frame corners.
        background: BGR colour outside the sheet (defaults to a grey table, or the plain surface when sheet=False).

    Returns:
        (img_bgr, truth) where truth has ``shapes`` (mm), ``H`` (3x3 photo px -> sheet mm), ``H_inv``
        (sheet mm -> photo px), the camera ``K``, ``R``, ``t``, ``focal_px``, and the parameters used.
    """
    paper = paper.lower()
    W, H = PAPER_SIZES_MM[paper]
    s = dpi / 25.4
    if sheet:
        canvas = render_sheet_image(dpi, paper, layout)
        bg = TABLE_COLOR if background is None else tuple(background)
    else:
        plain = PLAIN_BACKGROUND if background is None else tuple(background)
        canvas = np.empty((int(round(H * s)), int(round(W * s)), 3), np.uint8)
        canvas[:] = np.asarray(plain, np.uint8)
        bg = plain
    for sh in shapes:
        draw_shape(canvas, sh, s)

    w, h = int(out_size[0]), int(out_size[1])
    K, R, t = camera_for_sheet((W, H), tilt_deg, yaw_deg, roll_deg, (w, h), distance_mm, fill)
    H_mm2px = sheet_to_image_homography(K, R, t, (W, H))

    # render at 2x and area-average down: proper anti-aliasing where the far side of the sheet is minified
    K2 = K.copy()
    K2[0, 0] *= 2
    K2[1, 1] *= 2
    K2[0, 2] = 2 * K[0, 2] + 0.5
    K2[1, 2] = 2 * K[1, 2] + 0.5
    H2 = sheet_to_image_homography(K2, R, t, (W, H))
    M = H2 @ np.diag([1.0 / s, 1.0 / s, 1.0])  # sheet raster px -> 2x photo px
    big = cv2.warpPerspective(canvas, M, (2 * w, 2 * h), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=tuple(int(v) for v in bg))

    # photometrics: exposure and vignetting
    yy, xx = np.mgrid[0:2 * h, 0:2 * w].astype(np.float32)
    rr = np.hypot((xx - (2 * w - 1) / 2) / w, (yy - (2 * h - 1) / 2) / h) / math.sqrt(2.0)
    gain = (exposure * (1.0 - vignette * rr ** 2)).astype(np.float32)
    big = big.astype(np.float32) * gain[..., None]
    img = cv2.resize(big, (w, h), interpolation=cv2.INTER_AREA)
    if blur and blur > 0:
        img = cv2.GaussianBlur(img, (0, 0), float(blur))
    if noise and noise > 0:
        rng = np.random.default_rng(seed)
        img = img + rng.normal(0.0, float(noise), img.shape).astype(np.float32)
    img = np.clip(img, 0, 255).astype(np.uint8)

    H_px2mm = np.linalg.inv(H_mm2px)
    H_px2mm /= H_px2mm[2, 2]
    truth: dict[str, Any] = {
        "shapes": [dict(sh) for sh in shapes],
        "H": H_px2mm, "H_inv": H_mm2px / H_mm2px[2, 2],
        "K": K, "R": R, "t": t, "focal_px": float(K[0, 0]),
        "tilt_deg": float(tilt_deg), "yaw_deg": float(yaw_deg), "roll_deg": float(roll_deg),
        "distance_mm": float(distance_mm), "paper": paper, "paper_mm": (W, H), "dpi": float(dpi),
        "out_size": (w, h), "blur": float(blur), "noise": float(noise), "sheet": bool(sheet),
    }
    return img, truth


__all__ = ["DEFAULT_OBJECT_COLOR", "PLAIN_BACKGROUND", "TABLE_COLOR", "Shape", "camera_for_sheet", "circle",
           "draw_shape", "rect", "ring", "sheet_to_image_homography", "synth_photo"]
