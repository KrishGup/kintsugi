# A/B report — Kintsugi designer vs human-designed OpenSCAD parts (templates mode)

Each reference is a human-designed replacement part from a public OpenSCAD repository. A Part Spec was written from the reference's own mating dimensions (its interfaces), the designer built a part from the spec alone (it never saw the reference), and both were measured by the same checker and judged blind by the critic (A/B order randomized).

| part | kin checks | human checks | iterations | cost | silhouette IoU | Chamfer (mm) | volume kin/human | blind judge |
|---|---|---|---|---|---|---|---|---|
| rack_spacer | pass | pass | 2 | $0.498 | 0.89 | 0.31 | 0.83 | human (kin 8 / human 9) |
| cabinet_plug | pass | fail: walls.p05, walls.min | 1 | $0.3514 | 0.92 | 1.22 | 7.78 | kintsugi (kin 9 / human 6) |
| ikea_dombas_handle | pass | pass | 1 | $0.8903 | 0.96 | 0.54 | 1.33 | kintsugi (kin 9 / human 5) |

## Interface dimensions (measured on the meshes)

### rack_spacer — Rack spacer (xenomachina/3d-models)

| dimension | target | human | kintsugi |
|---|---|---|---|
| screw.inner_diameter | 5.2 ±0.2 | 5.19 ✓ | 5.199 ✓ |
| stack.height | 11.0 ±0.15 | 11.0 ✓ | 11.0 ✓ |
| footprint.width_x | ≥14 ≤16.5 | 16.0 ✓ | 15.0 ✓ |
| footprint.width_y | ≥10 ≤12.5 | 12.0 ✓ | 11.0 ✓ |

**Blind judge** preferred **human**. Both parts pass all measured checks: bore ~5.2 mm (loose fit on 4.7 mm shank), 11 mm stack height, footprint within limits, flat-on-bed orientation, no overhangs, and no interference with the screw. A uses a 16×12 mm footprint giving 3.4+ mm of surrounding wall (well above the 1.6 mm minimum) and 170 mm² bed contact, providing better clamping-load resistance around the bore. B is slightly more compact at 15×11 mm with ~2.9 mm walls — still compliant but with less material margin around the bore and less bed adhesion. Both honor the rounded-rectangle design intent, but A's extra wall thickness better satisfies the explicit 'no thin walls / no crushing' strength requirement while remaining within footprint bounds. I would print A.

Sheets: human `eval/reports/templates/rack_spacer/ref/iter_00_sheet.png` · kintsugi `eval/reports/templates/rack_spacer/kin/iter_02_sheet.png`

### cabinet_plug — Cabinet plug (xenomachina/3d-models)

| dimension | target | human | kintsugi |
|---|---|---|---|
| opening.width_x | 37.26 ±0.3 | 37.26 ✓ | 37.26 ✓ |
| opening.depth_y | 60.39 ±0.3 | 60.39 ✓ | 60.39 ✓ |
| tube.inner_diameter | 5.55 ±0.2 | 5.539 ✓ | 5.55 ✓ |
| flange.flange_x | ≥38.2 ≤41 | 38.26 ✓ | 39.26 ✓ |
| flange.flange_y | ≥61.3 ≤64 | 61.39 ✓ | 62.39 ✓ |
| height.height | ≥10 ≤12 | 10.0 ✓ | 11.0 ✓ |

**Blind judge** preferred **kintsugi**. Both candidates hit the opening (37.26 x 60.39) and tube bore (~5.55 with clearance) targets and satisfy the flange overlap and skirt height requirements. Candidate A passes all wall-thickness checks (min 1.65 mm, p05 11.0 mm) well above the 1.2 mm minimum, giving a robust skirt and flange suitable for PLA at 0.4 nozzle. Candidate B fails walls.p05 and walls.min at 0.50 mm — 1421 sampled points thinner than 1.2 mm — which means single-perimeter, fragile walls that will likely delaminate or crack when press-fit into the panel. Both print flange-down with no overhang issues, but B's paper-thin skirt undermines strength and printability despite its smaller, lighter volume. A is the clear choice to print.

Sheets: human `eval/reports/templates/cabinet_plug/ref/iter_00_sheet.png` · kintsugi `eval/reports/templates/cabinet_plug/kin/iter_01_sheet.png`

### ikea_dombas_handle — IKEA DOMBAS wardrobe handle (frdmn/openscad-ikea-handle-replacement)

| dimension | target | human | kintsugi |
|---|---|---|---|
| screws.positions | [[-63.2, 0.0, 3.0], [63.2, 0.0, 3.0]] | [[63.2, -0.0, 3.0], [-63.2, -0.0, 3.0]] ✓ | [[-63.2, 0.0, 3.0], [63.2, -0.0, 3.0]] ✓ |
| screws.standoff | 24.0 ±0.5 | 24.0 ✓ | 24.0 ✓ |
| length.overall_length | ≥130 ≤140 | 136.4 ✓ | 136.4 ✓ |
| bar_width.bar_width | ≥8 ≤14 | 10.0 ✓ | 10.0 ✓ |

**Blind judge** preferred **kintsugi**. Both candidates hit the interface targets: 136.4 mm length, 24 mm standoff, 10 mm bar width, and screw positions at ±63.2 mm all pass. The decisive difference is wall thickness and geometry. Candidate A uses a rectangular bar/pillar cross-section giving a min wall of 1.82 mm and p05 of 3.94 mm — comfortably above the 1.6 mm minimum with two solid perimeters. Candidate B uses cylindrical pillars around 3 mm screw holes, producing a min wall of 0.09 mm (FAIL) and a thin knife-edge tangent between the round pillar and the flat bar, which will not print reliably in PETG at 0.4 nozzle and will snap under pull-out load. A also has a larger, cleaner bed-contact footprint and a more elegant, uniform slim-bar aesthetic that matches the design intent. I would print A.

Sheets: human `eval/reports/templates/ikea_dombas_handle/ref/iter_00_sheet.png` · kintsugi `eval/reports/templates/ikea_dombas_handle/kin/iter_01_sheet.png`


## Reading the numbers

- *checks*: every hard check in the spec (interface dimensions with clearance, interference against the context proxies, walls, topology).
- *silhouette IoU*: overlap of top/front/right silhouettes at the same scale and frame; low values mean a different body shape, which is allowed (only interfaces are specified).
- *Chamfer*: mean surface-to-surface distance (mm) between the two meshes; a shape-difference measure, not a quality measure.
- *blind judge*: the critic model scoring both sheets without knowing which is human-designed.
