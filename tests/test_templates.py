"""Template tests: every templates/*.scad that has a Part Spec in eval/specs/<name>.yaml must, as-is,
compile (part, coupon and assembly targets), pass every hard check of its spec, and expose a customizer
block with a render_target dropdown. No model required; only OpenSCAD."""

from __future__ import annotations

from pathlib import Path

import pytest

from kintsugi import REPO_DIR, TEMPLATES_DIR
from kintsugi.checks import geometry as G
from kintsugi.checks import run_checks
from kintsugi.scad.compile import compile_scad, openscad_version
from kintsugi.scad.customizer import parse_customizer
from kintsugi.spec import PartSpec

SPECS_DIR = REPO_DIR / "eval" / "specs"
SPEC_ALIASES = {"ring_loop_handle": "bottle_handle"}  # the reference template's spec predates the <template>.yaml naming rule


def spec_path(scad: Path) -> Path | None:
    p = SPECS_DIR / f"{SPEC_ALIASES.get(scad.stem, scad.stem)}.yaml"
    return p if p.exists() else None


TEMPLATES = sorted(p for p in TEMPLATES_DIR.glob("*.scad") if spec_path(p))
IDS = [p.stem for p in TEMPLATES]

pytestmark = pytest.mark.skipif(openscad_version() is None, reason="openscad not installed")


@pytest.fixture(scope="module")
def tmp(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("templates")


def test_every_template_has_a_spec():
    missing = [p.stem for p in TEMPLATES_DIR.glob("*.scad") if spec_path(p) is None]
    assert not missing, f"templates without a spec in eval/specs: {missing}"
    assert len(TEMPLATES) >= 7


@pytest.mark.parametrize("scad", TEMPLATES, ids=IDS)
def test_template_header_and_customizer(scad: Path):
    src = scad.read_text()
    assert src.splitlines()[0].startswith("// TEMPLATE:"), "first line must be '// TEMPLATE: <one-line description>'"
    params = {p.name: p for p in parse_customizer(src)}
    assert len(params) >= 4, f"only {len(params)} customizer params: {sorted(params)}"
    assert "render_target" in params
    rt = params["render_target"]
    assert rt.type == "string" and rt.value == "part"
    assert [o["value"] for o in rt.options] == ["part", "coupon", "assembly"]
    assert "clearance" in params or any(n.endswith("clearance") for n in params), "clearance must be a parameter"
    assert "/* [Hidden] */" in src
    for name in ("module part()", "module coupon()", "module assembly()"):
        assert name in src, f"{scad.name} lacks {name}"


@pytest.mark.parametrize("scad", TEMPLATES, ids=IDS)
def test_template_passes_its_spec(scad: Path, tmp: Path):
    spec = PartSpec.load(spec_path(scad))
    r = compile_scad(scad, tmp / f"{scad.stem}.stl", timeout_s=120)
    assert r.ok, r.summary()
    assert r.top_level_kind == "3D"
    assert not [w for w in r.warnings if "undefined" in w.lower() or "unknown" in w.lower()], r.warnings
    rep = run_checks(r.out_path, spec, iteration=1)
    assert rep.all_hard_pass, rep.summary_for_model()
    measured = {i.id for i in rep.items}
    for qname, dim, _ in spec.measured_dims():
        assert qname in measured, f"{qname} has a recipe but produced no check item"
    hard = [i for i in rep.items if i.kind == "hard"]
    assert len(hard) >= 6, "a template spec should exercise several hard checks"
    assert rep.stats["bodies"] == 1 and rep.stats["watertight"]
    assert abs(float(rep.stats["bbox"]["min"][2])) < 0.01, "part must sit on the bed"


@pytest.mark.parametrize("scad", TEMPLATES, ids=IDS)
def test_template_coupon_and_assembly_render(scad: Path, tmp: Path):
    rc = compile_scad(scad, tmp / f"{scad.stem}_coupon.stl", {"render_target": "coupon"}, timeout_s=120)
    assert rc.ok, rc.summary()
    coupon = G.load_mesh(rc.out_path)
    assert coupon.is_watertight and len(coupon.faces) > 0
    ra = compile_scad(scad, tmp / f"{scad.stem}_assembly.stl", {"render_target": "assembly"}, timeout_s=120)
    assert ra.ok, ra.summary()
    # the assembly exports the part only (% context is preview-only), so it must match the part's volume
    part = G.load_mesh(tmp / f"{scad.stem}.stl") if (tmp / f"{scad.stem}.stl").exists() else None
    if part is not None:
        asm = G.load_mesh(ra.out_path)
        assert abs(asm.volume - part.volume) < 1e-3 * max(part.volume, 1.0)
