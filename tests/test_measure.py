"""Tests for kintsugi.measure: sheet, markers, rectification, planar measurement, reference scale, grading.

Everything is synthetic (no network, no fixtures on disk); ground truth comes from ``synth_photo``.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kintsugi.measure import (
    REFERENCES,
    SHEET_LAYOUT,
    circle,
    detect_markers,
    detect_reference,
    estimate_tilt_deg,
    find_circles,
    find_outline,
    grade_capture,
    make_calibration_sheet,
    marker_corners_mm,
    measure_rect,
    measure_with_reference,
    px_to_mm,
    rect,
    rectify,
    render_sheet_image,
    ring,
    sheet_homography,
    synth_photo,
    to_openscad_polygon,
    verify_sheet_scale,
)

RING = ring(105.0, 100.0, 51.0, 43.2)
DISC = circle(105.0, 160.0, 30.0)
BAR = rect(60.0, 130.0, 25.0, 12.0, angle_deg=20.0)
SHAPES = [RING, DISC, BAR]
WORK_AREA = SHEET_LAYOUT.work_area()


@pytest.fixture(scope="module")
def photos() -> dict[float, tuple[np.ndarray, dict]]:
    return {tilt: synth_photo(SHAPES, tilt) for tilt in (0.0, 15.0, 25.0, 35.0)}


def _nearest_circle(circles, cx: float, cy: float, d: float):
    """The measured circle closest in diameter among those centred near (cx, cy)."""
    near = [c for c in circles if math.hypot(c.cx - cx, c.cy - cy) < 3.0 and abs(c.d - d) < 5.0]
    assert near, f"no circle near ({cx}, {cy}) with d~{d}; found {[(round(c.cx), round(c.cy), round(c.d, 2)) for c in circles]}"
    return min(near, key=lambda c: abs(c.d - d))


# ---- sheet -----------------------------------------------------------------------------------------------

def test_sheet_markers_detected_and_mapped_at_300dpi():
    img = render_sheet_image(300, "letter")
    assert img.dtype == np.uint8 and img.ndim == 3
    assert img.shape[:2] == (round(279.4 * 300 / 25.4), round(215.9 * 300 / 25.4))
    markers = detect_markers(img)
    assert sorted(m.id for m in markers) == SHEET_LAYOUT.marker_ids
    H = sheet_homography(markers)
    assert H is not None and H.shape == (3, 3)
    worst = 0.0
    for m in markers:
        err = np.linalg.norm(px_to_mm(H, m.corners) - marker_corners_mm(m.id), axis=1)
        worst = max(worst, float(err.max()))
    print(f"\n300 dpi sheet: worst marker corner error {worst:.4f} mm")
    assert worst < 0.3


def test_sheet_layout_is_paper_independent():
    a4 = render_sheet_image(150, "a4")
    ma4 = detect_markers(a4)
    assert sorted(m.id for m in ma4) == SHEET_LAYOUT.marker_ids
    H = sheet_homography(ma4)
    err = max(float(np.linalg.norm(px_to_mm(H, m.corners) - marker_corners_mm(m.id), axis=1).max()) for m in ma4)
    assert err < 0.3
    c = marker_corners_mm(0)
    assert c.shape == (4, 2)
    assert np.allclose(c[1] - c[0], [SHEET_LAYOUT.marker_size, 0])  # TL -> TR is +x
    assert np.allclose(c[3] - c[0], [0, SHEET_LAYOUT.marker_size])  # TL -> BL is +y


def test_calibration_sheet_pdf(tmp_path):
    out = make_calibration_sheet(tmp_path / "sheet.pdf", paper="letter")
    assert out.exists() and out.stat().st_size > 1000
    assert out.read_bytes()[:5] == b"%PDF-"
    out_a4 = make_calibration_sheet(tmp_path / "nested" / "sheet_a4.pdf", paper="a4")
    assert out_a4.exists()
    with pytest.raises(ValueError):
        make_calibration_sheet(tmp_path / "x.pdf", paper="legal")


def test_cli_sheet_command(tmp_path, capsys):
    from kintsugi.cli import main

    out = tmp_path / "cal.pdf"
    assert main(["sheet", "-o", str(out), "--paper", "a4"]) == 0
    assert out.exists()
    assert str(out) in capsys.readouterr().out


# ---- synthetic photos: rectification and circle measurement ---------------------------------------------

@pytest.mark.parametrize("tilt", [0.0, 15.0, 25.0, 35.0])
def test_ring_and_disc_measured_after_rectification(photos, tilt):
    img, truth = photos[tilt]
    markers = detect_markers(img)
    assert len(markers) >= 4, f"only {len(markers)} markers at tilt {tilt}"
    H = sheet_homography(markers)
    assert H is not None
    # the recovered homography agrees with the exact one over the work area
    gx, gy = np.meshgrid(np.linspace(WORK_AREA[0], WORK_AREA[2], 8), np.linspace(WORK_AREA[1], WORK_AREA[3], 8))
    pts_mm = np.column_stack([gx.ravel(), gy.ravel()])
    pts_px = px_to_mm(truth["H_inv"], pts_mm)  # exact mm -> px
    h_err = np.linalg.norm(px_to_mm(H, pts_px) - pts_mm, axis=1).max()
    assert h_err < 0.1, f"homography error {h_err:.3f} mm"

    rectified = rectify(img, H, mm_per_px=0.1)
    circles = find_circles(rectified, 25.0, 60.0, roi_mm=WORK_AREA)
    inner = _nearest_circle(circles, RING["cx"], RING["cy"], RING["d_inner"])
    outer = _nearest_circle(circles, RING["cx"], RING["cy"], RING["d_outer"])
    disc = _nearest_circle(circles, DISC["cx"], DISC["cy"], DISC["d"])
    e_in, e_out, e_disc = inner.d - 43.2, outer.d - 51.0, disc.d - 30.0
    print(f"\ntilt {tilt:4.1f}: homography err {h_err:.4f} mm | ring inner {inner.d:.3f} mm (err {e_in:+.3f}) "
          f"outer {outer.d:.3f} (err {e_out:+.3f}) | disc {disc.d:.3f} (err {e_disc:+.3f}) | "
          f"conf {inner.conf:.2f}/{disc.conf:.2f} method {inner.method}")
    assert abs(e_in) < 0.5, f"inner diameter error {e_in:+.3f} mm at tilt {tilt}"
    assert abs(e_disc) < 0.5, f"30 mm disc error {e_disc:+.3f} mm at tilt {tilt}"
    assert abs(e_out) < 0.5
    assert inner.conf > 0.5 and disc.conf > 0.5
    assert math.hypot(inner.cx - RING["cx"], inner.cy - RING["cy"]) < 0.3
    assert math.hypot(disc.cx - DISC["cx"], disc.cy - DISC["cy"]) < 0.3


@pytest.mark.parametrize("tilt", [0.0, 25.0])
def test_rectangle_and_outline(photos, tilt):
    img, _ = photos[tilt]
    H = sheet_homography(detect_markers(img))
    rectified = rectify(img, H, mm_per_px=0.1)
    rm = measure_rect(rectified, roi_mm=(40.0, 110.0, 80.0, 150.0))
    assert rm is not None
    print(f"\ntilt {tilt:4.1f}: rect {rm.w:.3f} x {rm.h:.3f} mm @ {rm.angle:.2f} deg (truth 25 x 12 @ 20), conf {rm.conf:.2f}")
    assert abs(rm.w - 25.0) < 0.3 and abs(rm.h - 12.0) < 0.3
    assert abs(rm.angle - 20.0) < 1.0
    assert abs(rm.cx - BAR["cx"]) < 0.3 and abs(rm.cy - BAR["cy"]) < 0.3
    assert rm.conf > 0.5

    polys = find_outline(rectified, roi_mm=WORK_AREA)
    assert len(polys) == 3  # ring, disc, bar - largest first
    areas = [abs(_shoelace(p)) for p in polys]
    assert areas == sorted(areas, reverse=True)
    assert abs(areas[0] - math.pi * 25.5**2) / (math.pi * 25.5**2) < 0.02  # ring silhouette (outer disc)
    assert abs(areas[1] - math.pi * 15.0**2) / (math.pi * 15.0**2) < 0.02
    assert abs(areas[2] - 300.0) / 300.0 < 0.03
    for p in polys:
        assert p.ndim == 2 and p.shape[1] == 2 and len(p) >= 3


def _shoelace(p: np.ndarray) -> float:
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def test_tilt_estimate_tracks_truth(photos):
    for tilt, (img, _) in photos.items():
        markers = detect_markers(img)
        est = estimate_tilt_deg(markers, (img.shape[1], img.shape[0]))
        assert est is not None
        print(f"\ntilt truth {tilt:4.1f} -> estimate {est:.1f}")
        assert abs(est - tilt) < 6.0


def test_rotated_sheet_in_frame():
    img, truth = synth_photo([DISC], 20.0, yaw_deg=90.0, roll_deg=5.0)
    markers = detect_markers(img)
    H = sheet_homography(markers)
    assert H is not None and len(markers) == SHEET_LAYOUT.n_markers
    rectified = rectify(img, H, mm_per_px=0.1, region_mm=(80.0, 135.0, 130.0, 185.0))
    circles = find_circles(rectified, 25.0, 35.0)
    disc = _nearest_circle(circles, DISC["cx"], DISC["cy"], DISC["d"])
    assert abs(disc.d - 30.0) < 0.5


# ---- reference object (no sheet) ---------------------------------------------------------------------------

@pytest.mark.parametrize("tilt", [0.0, 10.0])
def test_reference_object_scale(tilt):
    quarter = circle(70.0, 140.0, REFERENCES["us_quarter"], color=(165, 168, 170))
    part = circle(140.0, 140.0, 40.0)
    img, _ = synth_photo([quarter, part], tilt, sheet=False)
    ref = detect_reference(img, "auto")
    assert ref is not None
    assert ref.kind == "us_quarter"
    res = measure_with_reference(img, ref)
    assert res["circle"] is not None
    d = res["circle"]["d"]
    print(f"\nreference path tilt {tilt:4.1f}: {ref.kind} conf {ref.conf:.2f}, mm/px {ref.mm_per_px:.5f}; "
          f"40 mm disc measured {d:.3f} mm ({100 * (d - 40) / 40:+.2f}%)")
    assert abs(d - 40.0) / 40.0 < 0.03
    assert res["outline_mm"] is not None
    # explicit kinds and a wrong name
    assert detect_reference(img, "us_quarter").kind == "us_quarter"
    with pytest.raises(ValueError):
        detect_reference(img, "doubloon")


def test_reference_card():
    card = rect(110.0, 150.0, *REFERENCES["credit_card"], angle_deg=8.0, color=(40, 40, 45))
    img, _ = synth_photo([card], 0.0, sheet=False)
    ref = detect_reference(img, "card")
    assert ref is not None and ref.kind == "credit_card"
    w_px, h_px = ref.size_px
    assert abs(w_px / h_px - 85.60 / 53.98) < 0.03
    assert 0.2 < ref.mm_per_px < 0.5


def test_verify_print_scale_with_real_coin():
    silver = (165, 168, 170)
    # a correctly printed sheet with a quarter inside the grid, then a sheet printed at 97% (the coin then
    # appears 1/0.97 larger relative to the markers)
    for scale_true in (1.0, 0.97):
        img, _ = synth_photo([circle(140.0, 60.0, REFERENCES["us_quarter"] / scale_true, color=silver)], 12.0)
        H = sheet_homography(detect_markers(img))
        rectified = rectify(img, H, mm_per_px=0.1)
        res = verify_sheet_scale(rectified, "us_quarter")
        assert res is not None
        print(f"\nprint scale {scale_true}: coin measured {res['measured_mm']:.3f} mm -> scale {res['scale']:.4f}, ok {res['ok']}")
        assert abs(res["scale"] - 1.0 / scale_true) < 0.005
        assert res["ok"] == (scale_true == 1.0)
    # the sheet's own printed coin outlines are not mistaken for a coin
    img, _ = synth_photo([DISC], 12.0)
    rectified = rectify(img, sheet_homography(detect_markers(img)), mm_per_px=0.1)
    assert verify_sheet_scale(rectified) is None
    assert [round(c.d, 1) for c in find_circles(rectified, 15.0, 60.0)] == [30.0]


# ---- grading ---------------------------------------------------------------------------------------------

def test_grade_capture(photos):
    good, _ = photos[0.0]
    g = grade_capture(good)
    print(f"\ngood: sharpness {g.sharpness:.1f}, edge width {g.edge_width_px:.2f} px, tilt {g.tilt_deg:.1f}, "
          f"markers {g.markers_found}, ok {g.ok}")
    assert g.sharpness_ok and g.exposure_ok and g.tilt_ok and g.markers_found == 8 and g.ok

    blurred, _ = synth_photo(SHAPES, 0.0, blur=6.0)
    gb = grade_capture(blurred)
    print(f"blurred: sharpness {gb.sharpness:.1f}, edge width {gb.edge_width_px:.2f} px, ok {gb.ok}")
    assert not gb.sharpness_ok and not gb.ok
    assert any("blurry" in s.lower() for s in gb.instructions)

    tilted, _ = photos[35.0]
    gt = grade_capture(tilted)
    print(f"tilted: tilt estimate {gt.tilt_deg:.1f}, ok {gt.ok}")
    assert gt.sharpness_ok and not gt.tilt_ok and not gt.ok
    assert any("tilt" in s.lower() for s in gt.instructions)

    dark, _ = synth_photo(SHAPES, 0.0, exposure=0.25)
    gd = grade_capture(dark)
    assert not gd.exposure_ok and any("dark" in s.lower() for s in gd.instructions)

    no_sheet, _ = synth_photo([DISC], 0.0, sheet=False)
    gn = grade_capture(no_sheet, expect_sheet=True)
    assert gn.markers_found == 0 and not gn.ok
    assert grade_capture(no_sheet, expect_sheet=False).ok


# ---- OpenSCAD ---------------------------------------------------------------------------------------------

def test_to_openscad_polygon():
    poly = np.array([[10.0, 20.0], [30.0, 20.0], [30.0, 30.0], [10.0, 30.0]])
    s = to_openscad_polygon(poly)
    assert "polygon(" in s
    assert s.count("[") == 5  # the points list plus 4 points
    # centred and y-flipped by default
    assert "[-10.000, 5.000]" in s and "[10.000, -5.000]" in s
    raw = to_openscad_polygon(poly, flip_y=False, center=False)
    assert "[10.000, 20.000]" in raw
    named = to_openscad_polygon(poly, name="foot")
    assert named.startswith("module foot()") and "polygon(" in named
    with pytest.raises(ValueError):
        to_openscad_polygon(poly[:2])
