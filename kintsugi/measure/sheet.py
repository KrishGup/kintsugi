"""The printable calibration sheet.

The sheet is the metric anchor of every photo measurement: eight 20 mm ArUco markers (DICT_4X4_50, ids 0..7)
around the border and mid-edges give the plane homography, a light 10 mm grid helps the user place the object,
a 100 mm bar lets them verify the printer did not rescale, and printed coin outlines are a scale sanity check.

Coordinate conventions (used by every module in ``kintsugi.measure``):

* Sheet coordinates are millimetres with the origin at the paper's top-left corner, +x right, +y down.
* The layout is identical on Letter and A4: everything lives inside the common 210 x 279.4 mm area anchored at
  the top-left, so a homography recovered from the markers is paper-independent.
* ``render_sheet_image(dpi)`` rasterises the layout so that pixel index ``(i, j)`` (OpenCV pixel-centre
  convention) sits at sheet coordinate ``(i, j) * 25.4 / dpi``. Edges are rendered with exact area coverage,
  so a marker edge at 10 mm really is at ``10 * dpi / 25.4`` pixels, not rounded to the grid.
* Marker corners are listed in the order OpenCV's detector returns them for an unrotated marker:
  top-left, top-right, bottom-right, bottom-left.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

PAPER_SIZES_MM: dict[str, tuple[float, float]] = {"letter": (215.9, 279.4), "a4": (210.0, 297.0)}
ARUCO_DICT_ID: int = cv2.aruco.DICT_4X4_50
ARUCO_DICT_NAME = "DICT_4X4_50"

# Coin diameters (mm) printed as outlines for a scale sanity check.
US_QUARTER_MM = 24.26
US_PENNY_MM = 19.05


@dataclass(frozen=True)
class SheetLayout:
    """Everything on the sheet, in millimetres (origin top-left, +x right, +y down).

    ``markers`` maps marker id -> (x, y) of the marker's top-left corner. Marker ids run clockwise from the
    top-left corner: 0 TL, 1 top-centre, 2 TR, 3 right-middle, 4 BR, 5 bottom-centre, 6 BL, 7 left-middle, so
    at least four stay visible when an object covers the middle of the sheet.
    """

    common_area: tuple[float, float] = (210.0, 279.4)  # the layout fits on both Letter and A4
    marker_size: float = 20.0
    marker_border_bits: int = 1  # ArUco quiet-zone-free border cells inside the 20 mm (6x6 cells for 4x4 bits)
    margin: float = 10.0  # paper edge -> marker outer edge
    markers: dict[int, tuple[float, float]] = field(default_factory=dict)
    grid_pitch: float = 10.0
    grid_region: tuple[float, float, float, float] = (40.0, 40.0, 170.0, 190.0)  # x0, y0, x1, y1 of grid lines
    grid_line_width: float = 0.2
    grid_gray: float = 0.78  # 0 = black, 1 = white
    bar_length: float = 100.0
    bar_start: tuple[float, float] = (55.0, 208.0)  # left end of the verification bar (x, y)
    bar_width: float = 0.5
    bar_tick: float = 4.0
    coins: dict[str, tuple[float, float, float]] = field(default_factory=dict)  # name -> (cx, cy, diameter)
    coin_line_width: float = 0.25
    title: str = "Kintsugi calibration sheet"
    instructions: tuple[str, ...] = (
        "Print at 100% / actual size (never 'fit to page').",
        "Check that the bar below measures exactly 100 mm.",
        "Put the part inside the grid; keep all 8 markers visible.",
        "Photograph from directly above, in even light, no shadows.",
    )
    font_size_mm: float = 2.8

    def __post_init__(self) -> None:
        w, h = self.common_area
        s, m = self.marker_size, self.margin
        if not self.markers:
            xm, ym = (w - s) / 2, (h - s) / 2
            object.__setattr__(self, "markers", {
                0: (m, m), 1: (xm, m), 2: (w - m - s, m), 3: (w - m - s, ym),
                4: (w - m - s, h - m - s), 5: (xm, h - m - s), 6: (m, h - m - s), 7: (m, ym),
            })
        if not self.coins:
            object.__setattr__(self, "coins", {
                "us_quarter": (55.0, 230.0, US_QUARTER_MM),
                "us_penny": (85.0, 230.0, US_PENNY_MM),
            })

    # ---- derived geometry -------------------------------------------------------------------------
    @property
    def marker_ids(self) -> list[int]:
        return sorted(self.markers)

    @property
    def n_markers(self) -> int:
        return len(self.markers)

    @property
    def cell_size(self) -> float:
        """Side of one marker cell (4 data bits + 2 border cells across the 20 mm)."""
        return self.marker_size / (4 + 2 * self.marker_border_bits)

    def marker_corners_mm(self, marker_id: int) -> np.ndarray:
        """(4, 2) corners of a marker in sheet mm: top-left, top-right, bottom-right, bottom-left."""
        if marker_id not in self.markers:
            raise KeyError(f"marker id {marker_id} is not on the sheet (ids {self.marker_ids})")
        x0, y0 = self.markers[marker_id]
        s = self.marker_size
        return np.array([[x0, y0], [x0 + s, y0], [x0 + s, y0 + s], [x0, y0 + s]], dtype=np.float64)

    def marker_center_mm(self, marker_id: int) -> tuple[float, float]:
        x0, y0 = self.markers[marker_id]
        return (x0 + self.marker_size / 2, y0 + self.marker_size / 2)

    def grid_lines(self) -> tuple[list[float], list[float]]:
        """(x positions of vertical lines, y positions of horizontal lines) in mm."""
        x0, y0, x1, y1 = self.grid_region
        p = self.grid_pitch
        xs = [x for x in np.arange(np.ceil(x0 / p) * p, x1 + 1e-6, p)]
        ys = [y for y in np.arange(np.ceil(y0 / p) * p, y1 + 1e-6, p)]
        return [float(v) for v in xs], [float(v) for v in ys]

    def bar_end(self) -> tuple[float, float]:
        x, y = self.bar_start
        return (x + self.bar_length, y)

    def work_area(self) -> tuple[float, float, float, float]:
        """The region where the object should sit (the gridded area), x0, y0, x1, y1 in mm."""
        return self.grid_region


SHEET_LAYOUT = SheetLayout()


def marker_corners_mm(marker_id: int, layout: SheetLayout = SHEET_LAYOUT) -> np.ndarray:
    """Four corners of marker ``marker_id`` in sheet millimetres, ordered TL, TR, BR, BL (OpenCV order)."""
    return layout.marker_corners_mm(marker_id)


def aruco_dictionary() -> cv2.aruco.Dictionary:
    return cv2.aruco.getPredefinedDictionary(ARUCO_DICT_ID)


def marker_bits(marker_id: int, border_bits: int = 1) -> np.ndarray:
    """Boolean (6, 6) cell matrix of a marker, True where the cell is black (includes the black border)."""
    side = 4 + 2 * border_bits
    img = cv2.aruco.generateImageMarker(aruco_dictionary(), int(marker_id), side, borderBits=border_bits)
    return img == 0


# ---- PDF ---------------------------------------------------------------------------------------------

def make_calibration_sheet(out_path: str | Path, paper: str = "letter", layout: SheetLayout = SHEET_LAYOUT) -> Path:
    """Write the calibration sheet as a PDF at exact physical size. Returns the output path."""
    from reportlab.lib.units import mm as MM
    from reportlab.pdfgen import canvas as rl_canvas

    paper = paper.lower()
    if paper not in PAPER_SIZES_MM:
        raise ValueError(f"paper must be one of {sorted(PAPER_SIZES_MM)}, got {paper!r}")
    W, H = PAPER_SIZES_MM[paper]
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    c = rl_canvas.Canvas(str(out), pagesize=(W * MM, H * MM))
    c.setTitle(layout.title)
    c.setAuthor("kintsugi")

    def Y(y_mm: float) -> float:  # sheet y (down) -> PDF y (up), in points
        return (H - y_mm) * MM

    # markers: black cells only (paper is the white)
    c.setFillGray(0.0)
    cell = layout.cell_size
    for mid, (x0, y0) in layout.markers.items():
        bits = marker_bits(mid, layout.marker_border_bits)
        for r in range(bits.shape[0]):
            for q in range(bits.shape[1]):
                if bits[r, q]:
                    c.rect((x0 + q * cell) * MM, Y(y0 + (r + 1) * cell), cell * MM, cell * MM, stroke=0, fill=1)

    # light grid
    xs, ys = layout.grid_lines()
    gx0, gy0, gx1, gy1 = layout.grid_region
    c.setStrokeGray(layout.grid_gray)
    c.setLineWidth(layout.grid_line_width * MM)
    for x in xs:
        c.line(x * MM, Y(gy0), x * MM, Y(gy1))
    for y in ys:
        c.line(gx0 * MM, Y(y), gx1 * MM, Y(y))

    # verification bar with end ticks
    (bx0, by), (bx1, _) = layout.bar_start, layout.bar_end()
    c.setStrokeGray(0.0)
    c.setLineWidth(layout.bar_width * MM)
    c.line(bx0 * MM, Y(by), bx1 * MM, Y(by))
    t = layout.bar_tick / 2
    c.line(bx0 * MM, Y(by - t), bx0 * MM, Y(by + t))
    c.line(bx1 * MM, Y(by - t), bx1 * MM, Y(by + t))
    c.setFont("Helvetica", 7)
    c.setFillGray(0.0)
    c.drawString(bx0 * MM, Y(by + 5.5), f"{layout.bar_length:g} mm - measure this bar with a ruler to verify the print scale")

    # coin outlines
    c.setLineWidth(layout.coin_line_width * MM)
    for name, (cx, cy, d) in layout.coins.items():
        c.circle(cx * MM, Y(cy), d / 2 * MM, stroke=1, fill=0)
        label = name.replace("_", " ").upper() + f" {d:g} mm"
        c.setFont("Helvetica", 6)
        c.drawCentredString(cx * MM, Y(cy + d / 2 + 3.5), label)

    # title and instructions
    c.setFont("Helvetica-Bold", 9)
    c.drawString(gx0 * MM, Y(38.0), layout.title)
    c.setFont("Helvetica", 7)
    ix, iy = 105.0, 222.0
    for i, line in enumerate(layout.instructions):
        c.drawString(ix * MM, Y(iy + i * 4.2), f"{i + 1}. {line}")
    c.setFont("Helvetica", 5.5)
    c.setFillGray(0.35)
    c.drawString(gx0 * MM, Y(H - 6.0), f"{paper.upper()} - markers {ARUCO_DICT_NAME} ids 0-{layout.n_markers - 1}, "
                                          f"{layout.marker_size:g} mm - grid {layout.grid_pitch:g} mm")
    c.showPage()
    c.save()
    return out


# ---- raster --------------------------------------------------------------------------------------------

def _interval_coverage(lo: float, hi: float, n: int) -> tuple[int, int, np.ndarray]:
    """Fraction of each pixel [i-0.5, i+0.5] covered by the interval [lo, hi] (pixel-centre coordinates).

    Returns (first index, last index + 1, coverage array for that index range).
    """
    i0 = max(int(np.floor(lo - 0.5)), 0)
    i1 = min(int(np.ceil(hi + 0.5)) + 1, n)
    if i1 <= i0:
        return 0, 0, np.zeros(0)
    idx = np.arange(i0, i1, dtype=np.float64)
    cov = np.clip(np.minimum(idx + 0.5, hi) - np.maximum(idx - 0.5, lo), 0.0, 1.0)
    return i0, i1, cov


def _composite(img: np.ndarray, y0: int, y1: int, x0: int, x1: int, alpha: np.ndarray, color: tuple[float, ...]) -> None:
    """Blend ``color`` into img[y0:y1, x0:x1] with per-pixel alpha (exact area coverage)."""
    if y1 <= y0 or x1 <= x0:
        return
    roi = img[y0:y1, x0:x1].astype(np.float64)
    a = alpha[..., None]
    col = np.asarray(color, dtype=np.float64).reshape(1, 1, -1)
    img[y0:y1, x0:x1] = np.clip(roi * (1.0 - a) + col * a, 0, 255).astype(np.uint8)


def _fill_rect_mm(img: np.ndarray, s: float, x0: float, y0: float, x1: float, y1: float, color: tuple[float, ...]) -> None:
    h, w = img.shape[:2]
    cx0, cx1, covx = _interval_coverage(x0 * s, x1 * s, w)
    cy0, cy1, covy = _interval_coverage(y0 * s, y1 * s, h)
    if cx1 <= cx0 or cy1 <= cy0:
        return
    _composite(img, cy0, cy1, cx0, cx1, np.outer(covy, covx), color)


def _draw_marker_exact(img: np.ndarray, s: float, x0: float, y0: float, size: float, bits: np.ndarray) -> None:
    """Render a marker whose top-left is at (x0, y0) mm with exact per-pixel coverage of its black cells."""
    h, w = img.shape[:2]
    n = bits.shape[0]
    cell = size / n
    px0, px1 = x0 * s, (x0 + size) * s
    py0, py1 = y0 * s, (y0 + size) * s
    ix0, ix1, _ = _interval_coverage(px0, px1, w)
    iy0, iy1, _ = _interval_coverage(py0, py1, h)
    if ix1 <= ix0 or iy1 <= iy0:
        return
    xs = np.arange(ix0, ix1, dtype=np.float64)
    ys = np.arange(iy0, iy1, dtype=np.float64)
    covx = np.zeros((n, len(xs)))
    covy = np.zeros((n, len(ys)))
    for k in range(n):
        lo, hi = px0 + k * cell * s, px0 + (k + 1) * cell * s
        covx[k] = np.clip(np.minimum(xs + 0.5, hi) - np.maximum(xs - 0.5, lo), 0.0, 1.0)
        lo, hi = py0 + k * cell * s, py0 + (k + 1) * cell * s
        covy[k] = np.clip(np.minimum(ys + 0.5, hi) - np.maximum(ys - 0.5, lo), 0.0, 1.0)
    darkness = covy.T @ bits.astype(np.float64) @ covx  # (rows, cols) in [0, 1]
    _composite(img, iy0, iy1, ix0, ix1, darkness, (0, 0, 0))


def _put_text(img: np.ndarray, text: str, x_mm: float, y_mm: float, s: float, size_mm: float,
              gray: int = 0, bold: bool = False, center: bool = False) -> None:
    """Draw text with its baseline at (x_mm, y_mm); ``size_mm`` is the cap height."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = (size_mm * s) / 22.0  # Hershey simplex cap height is ~22 px at scale 1
    thick = max(1, int(round(scale * (2.2 if bold else 1.4))))
    (tw, th), _ = cv2.getTextSize(text, font, scale, thick)
    x = int(round(x_mm * s - (tw / 2 if center else 0)))
    y = int(round(y_mm * s))
    cv2.putText(img, text, (x, y), font, scale, (gray, gray, gray), thick, cv2.LINE_AA)


def render_sheet_image(dpi: float = 300.0, paper: str = "letter", layout: SheetLayout = SHEET_LAYOUT) -> np.ndarray:
    """Rasterise the sheet exactly as printed: uint8 BGR, ``round(paper_mm * dpi / 25.4)`` pixels per side.

    Pixel ``(i, j)`` (column, row) is centred on sheet coordinate ``(i, j) * 25.4 / dpi`` mm. Marker, grid and bar
    edges are rendered with exact area coverage (anti-aliased), so their sub-pixel positions match the layout.
    """
    paper = paper.lower()
    if paper not in PAPER_SIZES_MM:
        raise ValueError(f"paper must be one of {sorted(PAPER_SIZES_MM)}, got {paper!r}")
    W, H = PAPER_SIZES_MM[paper]
    s = dpi / 25.4
    w, h = int(round(W * s)), int(round(H * s))
    img = np.full((h, w, 3), 255, np.uint8)

    # grid (light) first so markers/bar overprint it
    xs, ys = layout.grid_lines()
    gx0, gy0, gx1, gy1 = layout.grid_region
    g = int(round(layout.grid_gray * 255))
    lw = layout.grid_line_width
    for x in xs:
        _fill_rect_mm(img, s, x - lw / 2, gy0, x + lw / 2, gy1, (g, g, g))
    for y in ys:
        _fill_rect_mm(img, s, gx0, y - lw / 2, gx1, y + lw / 2, (g, g, g))

    for mid, (x0, y0) in layout.markers.items():
        _draw_marker_exact(img, s, x0, y0, layout.marker_size, marker_bits(mid, layout.marker_border_bits))

    (bx0, by), (bx1, _) = layout.bar_start, layout.bar_end()
    bw, t = layout.bar_width, layout.bar_tick / 2
    _fill_rect_mm(img, s, bx0, by - bw / 2, bx1, by + bw / 2, (0, 0, 0))
    _fill_rect_mm(img, s, bx0 - bw / 2, by - t, bx0 + bw / 2, by + t, (0, 0, 0))
    _fill_rect_mm(img, s, bx1 - bw / 2, by - t, bx1 + bw / 2, by + t, (0, 0, 0))
    _put_text(img, f"{layout.bar_length:g} mm - measure this bar with a ruler to verify the print scale",
              bx0, by + 5.5, s, 1.8)

    shift = 4
    for name, (cx, cy, d) in layout.coins.items():
        center = (int(round(cx * s * (1 << shift))), int(round(cy * s * (1 << shift))))
        radius = int(round(d / 2 * s * (1 << shift)))
        thick = max(1, int(round(layout.coin_line_width * s)))
        cv2.circle(img, center, radius, (0, 0, 0), thick, cv2.LINE_AA, shift)
        _put_text(img, name.replace("_", " ").upper() + f" {d:g} mm", cx, cy + d / 2 + 3.5, s, 1.5, center=True)

    _put_text(img, layout.title, gx0, 38.0, s, 2.4, bold=True)
    ix, iy = 105.0, 222.0
    for i, line in enumerate(layout.instructions):
        _put_text(img, f"{i + 1}. {line}", ix, iy + i * 4.2, s, 1.7)
    _put_text(img, f"{paper.upper()} - markers {ARUCO_DICT_NAME} ids 0-{layout.n_markers - 1}, "
                   f"{layout.marker_size:g} mm - grid {layout.grid_pitch:g} mm", gx0, H - 6.0, s, 1.3, gray=90)
    return img


__all__ = [
    "ARUCO_DICT_ID", "ARUCO_DICT_NAME", "PAPER_SIZES_MM", "SHEET_LAYOUT", "SheetLayout", "US_PENNY_MM",
    "US_QUARTER_MM", "aruco_dictionary", "make_calibration_sheet", "marker_bits", "marker_corners_mm",
    "render_sheet_image",
]
