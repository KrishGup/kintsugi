# A/B report — Kintsugi designer vs human-designed OpenSCAD parts (templates mode)

Each reference is a human-designed replacement part from a public OpenSCAD repository. A Part Spec was written from the reference's own mating dimensions (its interfaces), the designer built a part from the spec alone (it never saw the reference), and both were measured by the same checker and judged blind by the critic (A/B order randomized).

| part | kin checks | human checks | iterations | cost | silhouette IoU | Chamfer (mm) | volume kin/human | blind judge |
|---|---|---|---|---|---|---|---|---|
| rack_spacer | pass | pass | 2 | $0.498 | 0.89 | 0.31 | 0.83 | human (kin 8 / human 9) |
| cabinet_plug | pass | fail: walls.p05, walls.min | 1 | $0.3514 | 0.92 | 1.22 | 7.78 | kintsugi (kin 9 / human 6) |
| ikea_dombas_handle | pass | pass | 1 | $0.8903 | 0.96 | 0.54 | 1.33 | kintsugi (kin 9 / human 5) |
| trailer_jack_cap | pass | pass | 2 | $1.2642 | 0.99 | 0.17 | 0.95 | kintsugi (kin 9 / human 7) |

## Interface dimensions (measured on the meshes)

### rack_spacer — Rack spacer (xenomachina/3d-models)

| dimension | target | human | kintsugi |
|---|---|---|---|
| screw.inner_diameter | 5.2 ±0.2 | 5.19 ✓ | 5.199 ✓ |
| stack.height | 11.0 ±0.15 | 11.0 ✓ | 11.0 ✓ |
| footprint.width_x | ≥14 ≤16.5 | 16.0 ✓ | 15.0 ✓ |
| footprint.width_y | ≥10 ≤12.5 | 12.0 ✓ | 11.0 ✓ |

**Blind judge** preferred **human**. Both candidates pass all measured checks: bore ~5.2 mm with proper loose clearance around the 4.7 mm shank, 11 mm stack height, watertight single body, and flat-on-bed orientation with 0% overhangs. A uses the full 16×12 mm footprint giving 3.4+ mm walls around the bore (well above the 1.6 mm minimum), maximizing crush resistance under screw clamping load — the stated strength requirement. B is trimmed to 15×11 mm with ~2.9 mm walls; still passes but leaves less material around the bore for the clamping load, and its more rounded corners slightly reduce side-by-side packing density on the rail. Both are equally printable (170 vs 140 mm² bed contact, no supports), but A better honors the 'solid body, no thin walls' strength intent and sits closer to the nominal 16×12 footprint called out in the spec. I'd print A.

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

**Blind judge** preferred **kintsugi**. Both candidates meet the interface dimensions (opening 37.26×60.39, tube bore ~5.55 with clearance) and flange overlap targets. Candidate A passes all wall-thickness checks with p05 = 11.0 mm and min 1.65 mm, giving a robust skirt that will survive insertion/removal and print reliably in PLA at 0.4 nozzle. Candidate B fails walls.p05 and walls.min at 0.50 mm — below the 1.2 mm minimum and even below a single 0.4 mm perimeter pair — meaning the skirt is a thin shell that will be fragile, may not slice as solid walls, and risks splitting. A's height (11 mm) also sits more centrally in the 10–12 mm band than B's 10.0 mm floor. Both print flange-down with 0% overhang, but A's substantially greater material and wall integrity make it the clear choice.

Sheets: human `eval/reports/templates/cabinet_plug/ref/iter_00_sheet.png` · kintsugi `eval/reports/templates/cabinet_plug/kin/iter_01_sheet.png`

### ikea_dombas_handle — IKEA DOMBAS wardrobe handle (frdmn/openscad-ikea-handle-replacement)

| dimension | target | human | kintsugi |
|---|---|---|---|
| screws.positions | [[-63.2, 0.0, 3.0], [63.2, 0.0, 3.0]] | [[63.2, -0.0, 3.0], [-63.2, -0.0, 3.0]] ✓ | [[-63.2, 0.0, 3.0], [63.2, -0.0, 3.0]] ✓ |
| screws.standoff | 24.0 ±0.5 | 24.0 ✓ | 24.0 ✓ |
| length.overall_length | ≥130 ≤140 | 136.4 ✓ | 136.4 ✓ |
| bar_width.bar_width | ≥8 ≤14 | 10.0 ✓ | 10.0 ✓ |

**Blind judge** preferred **kintsugi**. Both parts hit the interface targets: 136.4 mm overall, 24 mm standoff, 10 mm bar width, and screw bosses at ±63.2 mm. However, Candidate B fails walls.min at 0.09 mm — the round pillars leave a razor-thin sliver of material around the 3 mm screw pocket inside a 10 mm boss, which will not print reliably in PETG at 0.4 nozzle and will shear under pull-out load. Candidate A uses a rectangular section with a min wall of 1.82 mm and p05 of 3.94 mm, giving a solid, printable, and stronger boss while still passing every spec check. A's flat-bottomed U-profile also seats cleanly on the bed with 1332 mm² contact and near-zero overhang. A is the one I would print.

Sheets: human `eval/reports/templates/ikea_dombas_handle/ref/iter_00_sheet.png` · kintsugi `eval/reports/templates/ikea_dombas_handle/kin/iter_01_sheet.png`

### trailer_jack_cap — Trailer jack stand cap (chrishad95/3dPrintingProjects)

| dimension | target | human | kintsugi |
|---|---|---|---|
| pipe_bore.outer_diameter | 45.79 ±0.25 | 45.78 ✓ | 45.785 ✓ |
| pipe_bore.plug_depth | ≥8 ≤14 | 9.99 ✓ | 9.99 ✓ |
| rim.flange_diameter | 50.8 ±0.5 | 50.791 ✓ | 50.792 ✓ |
| height.height | 25.0 ±1.0 | 25.0 ✓ | 25.0 ✓ |

**Blind judge** preferred **kintsugi**. Both candidates hit the key interface dimensions: plug OD 45.78 mm (within the 46.04 ±0.25 sliding-fit window with ~0.25 mm clearance), flange 50.79 mm, height 25 mm, and plug depth ~9.99 mm within the 8–14 mm band. Both show retention features (small tabs/ribs on the plug wall) consistent with the spec. The decisive difference is wall thickness: A reports walls.min 2.65 mm (p05 3.00 mm) and PASSES the min-wall check, while B reports walls.min 1.41 mm (p05 3.50 mm) and FAILS the 2.25 mm minimum — its retention tab roots are too thin for durable PETG outdoor service and risk splitting on insertion. A is also cleaner geometrically with more bed contact (1947 vs 2026 mm² comparable) and no overhang issues. I would print A.

Sheets: human `eval/reports/templates/trailer_jack_cap/ref/iter_00_sheet.png` · kintsugi `eval/reports/templates/trailer_jack_cap/kin/iter_02_sheet.png`


## Reading the numbers

- *checks*: every hard check in the spec (interface dimensions with clearance, interference against the context proxies, walls, topology).
- *silhouette IoU*: overlap of top/front/right silhouettes at the same scale and frame; low values mean a different body shape, which is allowed (only interfaces are specified).
- *Chamfer*: mean surface-to-surface distance (mm) between the two meshes; a shape-difference measure, not a quality measure.
- *blind judge*: the critic model scoring both sheets without knowing which is human-designed.
