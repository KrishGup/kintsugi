"""The OpenSCAD knowledge base: guides whose examples compile, a reference index that finds things, tools wired to the designer."""

from __future__ import annotations

import pytest

from kintsugi.agent import knowledge as K
from kintsugi.scad.compile import compile_scad, openscad_version

needs_openscad = pytest.mark.skipif(openscad_version() is None, reason="openscad not installed")


def test_guides_exist_and_alias():
    topics = [k for k, _ in K.guide_topics()]
    assert topics == list(K.GUIDE_TOPICS)
    assert K.guide("rounding") == K.guide("shapes") and K.guide("customizer") == K.guide("kintsugi") and K.guide("nope") is None
    assert "last assignment" in K.guide("essentials").lower() and "render_target" in K.guide("kintsugi")


def test_reference_index_and_search():
    idx = K.all_entries()
    assert len(K.builtin_index()) >= 60 and len(K.bosl2_index()) >= 800
    names = {e.name for e in idx}
    for n in ("cube", "offset", "linear_extrude", "rotate_extrude", "cuboid", "cyl", "tube", "threaded_rod", "screw_hole", "attach", "diff",
              "rounding_edge_mask", "line_copies", "arc_copies", "skin", "sp_cap"):
        assert n in names, n
    assert K.search("offset", 1)[0].source == "openscad"  # the builtin outranks the BOSL2 function of the same name
    assert K.search("tube wall", 1)[0].name == "tube"
    assert K.search("threaded nut", 3)[0].name in ("nut", "threaded_nut")
    e = K.lookup("cuboid")
    assert e and e.includes.startswith("include <BOSL2/std.scad>") and any("rounding" in a for a in e.arguments) and e.examples
    text = K.docs_answer("", name="tube")
    assert "od=" in text and "wall=" in text
    assert "scad_guide(\"shapes\")" in K.docs_answer("how do I round the corners of a plate")
    assert "Nothing matched" in K.docs_answer("zzqx")
    assert K.bosl_version_str().count(".") == 2


def test_prompt_and_tools_mention_knowledge():
    from kintsugi.agent.designer import designer_prompt
    from kintsugi.agent.tools import make_knowledge_tools
    p = designer_prompt("openai")
    assert "scad_guide" in p and "scad_docs" in p and "$fn" in p
    tools = {t.name: t for t in make_knowledge_tools()}
    assert set(tools) == {"scad_guide", "scad_docs"}
    import asyncio
    r = asyncio.run(tools["scad_guide"].handler({"topic": "list"}))
    assert "patterns" in r.text and not r.is_error
    r = asyncio.run(tools["scad_docs"].handler({"query": "hex nut trap"}))
    assert "nut_trap" in r.text
    r = asyncio.run(tools["scad_guide"].handler({"topic": "nope"}))
    assert r.is_error


@needs_openscad
@pytest.mark.parametrize("topic", list(K.GUIDE_TOPICS))
def test_every_guide_example_compiles(tmp_path, topic):
    """Every ```scad block in every guide compiles on the shipped OpenSCAD + BOSL2 without 'unknown' or manifold warnings."""
    examples = K.guide_examples(topic)
    if topic in ("patterns", "shapes", "bosl2"):
        assert len(examples) >= 8, topic
    for label, src in examples:
        p = tmp_path / (label.replace("#", "_") + ".scad")
        p.write_text(src, encoding="utf-8")
        r = compile_scad(p, p.with_suffix(".stl"), timeout_s=180)
        assert r.ok, f"{label}: {r.errors[:1]}"
        bad = [w for w in (r.warnings or []) if "unknown" in w.lower() or "manifold" in w.lower()]
        assert not bad, f"{label}: {bad[:1]}"
