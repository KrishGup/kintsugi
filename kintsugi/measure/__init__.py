"""Photo measurement: the calibration sheet, marker detection and rectification, planar measurements,
reference-object scale, capture grading and synthetic test images.

Typical sheet workflow::

    from kintsugi.measure import detect_markers, sheet_homography, rectify, find_circles, grade_capture

    grade = grade_capture(img)                      # sharp? exposed? tilted? enough markers?
    markers = detect_markers(img)                   # sub-pixel ArUco corners
    H = sheet_homography(markers)                   # photo px -> sheet mm
    rect = rectify(img, H, mm_per_px=0.1)           # metric top-down view
    circles = find_circles(rect, 20, 60, roi_mm=(40, 40, 170, 190))
"""

from kintsugi.measure.aruco import (
    Marker,
    RectifiedImage,
    detect_markers,
    estimate_pose,
    estimate_tilt_deg,
    guess_intrinsics,
    homography_residuals_mm,
    mm_to_px,
    photo_px_per_mm,
    px_to_mm,
    rectify,
    refine_corners,
    sheet_homography,
)
from kintsugi.measure.grade import CaptureGrade, edge_width_px, grade_capture, laplacian_variance
from kintsugi.measure.planar import (
    CircleMeasure,
    RectMeasure,
    find_circles,
    find_outline,
    measure_rect,
    to_openscad_polygon,
)
from kintsugi.measure.reference import (
    REFERENCES,
    ReferenceDetection,
    detect_card,
    detect_coin,
    detect_reference,
    measure_with_reference,
    verify_sheet_scale,
)
from kintsugi.measure.sheet import (
    ARUCO_DICT_ID,
    ARUCO_DICT_NAME,
    PAPER_SIZES_MM,
    SHEET_LAYOUT,
    SheetLayout,
    make_calibration_sheet,
    marker_corners_mm,
    render_sheet_image,
)
from kintsugi.measure.synth import circle, rect, ring, synth_photo

__all__ = [
    # sheet
    "ARUCO_DICT_ID", "ARUCO_DICT_NAME", "PAPER_SIZES_MM", "SHEET_LAYOUT", "SheetLayout", "make_calibration_sheet",
    "marker_corners_mm", "render_sheet_image",
    # aruco
    "Marker", "RectifiedImage", "detect_markers", "estimate_pose", "estimate_tilt_deg", "guess_intrinsics",
    "homography_residuals_mm", "mm_to_px", "photo_px_per_mm", "px_to_mm", "rectify", "refine_corners",
    "sheet_homography",
    # planar
    "CircleMeasure", "RectMeasure", "find_circles", "find_outline", "measure_rect", "to_openscad_polygon",
    # reference
    "REFERENCES", "ReferenceDetection", "detect_card", "detect_coin", "detect_reference", "measure_with_reference",
    "verify_sheet_scale",
    # grade
    "CaptureGrade", "edge_width_px", "grade_capture", "laplacian_variance",
    # synth
    "circle", "rect", "ring", "synth_photo",
]
