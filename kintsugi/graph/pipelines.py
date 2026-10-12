"""The graphs Kintsugi runs: one iteration of the verification loop, and the export bundle.

Iteration:  params ∥ compile → [checks ∥ base views ∥ context ghost] → sheets
            (checks and the geometry-only renders are independent once the STL exists; the sheets need both)
Export:     coupon compile ∥ 3MF ∥ blueprint PDF ∥ print card ∥ session log → zip
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kintsugi.checks import geometry as G
from kintsugi.checks.run import run_checks
from kintsugi.graph.core import Graph, Node
from kintsugi.render.blueprint import compose_blueprint, context_ghost, render_assembly, render_base_views, render_sections
from kintsugi.scad.compile import compile_scad
from kintsugi.scad.customizer import parse_customizer
from kintsugi.spec.model import PartSpec


def iteration_graph(*, wall_samples: int = 1500) -> Graph:
    """State in: scad_path, it_dir, iteration, spec, render_target (bool). Out: compile, stl_path, params, checks, blueprint."""

    def n_params(s: dict[str, Any]) -> dict[str, Any]:
        params = [p.to_dict() for p in parse_customizer(Path(s["scad_path"]).read_text(encoding="utf-8"))]
        return {"params": params}

    def n_compile(s: dict[str, Any]) -> dict[str, Any]:
        it_dir = Path(s["it_dir"])
        comp = compile_scad(Path(s["scad_path"]), it_dir / "part.stl", {"render_target": "part"} if s.get("render_target") else None, timeout_s=240)
        (it_dir / "compile.json").write_text(json.dumps(comp.to_dict(), indent=2), encoding="utf-8")
        out: dict[str, Any] = {"compile": comp}
        if comp.ok:
            out["stl_path"] = str(it_dir / "part.stl")
        return out

    def n_mesh(s: dict[str, Any]) -> dict[str, Any]:
        return {"mesh": G.load_mesh(s["stl_path"])}

    def n_checks(s: dict[str, Any]) -> dict[str, Any]:
        spec: PartSpec = s["spec"]
        rep = run_checks(s["stl_path"], spec, iteration=int(s["iteration"]), wall_samples=wall_samples)
        rep.save(Path(s["it_dir"]) / "checks.json")
        return {"checks": rep}

    def n_views(s: dict[str, Any]) -> dict[str, Any]:
        base = render_base_views(s["stl_path"], Path(s["it_dir"]) / "sheets", int(s["iteration"]), mesh=s["mesh"])
        return {"base_views": base}

    def n_ghost(s: dict[str, Any]) -> dict[str, Any]:
        return {"ghost": context_ghost(s["spec"])}

    def n_sections(s: dict[str, Any]) -> dict[str, Any]:
        return {"sections": render_sections(s["stl_path"], s.get("checks"), s["base_views"], Path(s["it_dir"]) / "sheets", int(s["iteration"]), mesh=s["mesh"])}

    def n_assembly(s: dict[str, Any]) -> dict[str, Any]:
        return {"assembly": render_assembly(s["stl_path"], s.get("ghost"), s["base_views"], Path(s["it_dir"]) / "sheets", int(s["iteration"]), mesh=s["mesh"])}

    def n_compose(s: dict[str, Any]) -> dict[str, Any]:
        bp = compose_blueprint(s["stl_path"], s["spec"], s.get("checks"), s["base_views"], s.get("sections") or {}, s.get("assembly") or {},
                               Path(s["it_dir"]) / "sheets", int(s["iteration"]), mesh=s["mesh"])
        return {"blueprint": bp}

    return Graph("iteration", [
        Node("params", n_params, ("scad_path",), ("params",), label="customizer params", est_s=0.05, optional=True),
        Node("compile", n_compile, ("scad_path", "it_dir"), ("compile",), label="OpenSCAD compile", est_s=6.0),
        Node("mesh", n_mesh, ("stl_path",), ("mesh",), label="load mesh", est_s=0.2),
        Node("checks", n_checks, ("stl_path", "spec", "iteration"), ("checks",), label="spec checks on the mesh", est_s=3.0, optional=True),
        Node("views", n_views, ("mesh", "it_dir", "iteration"), ("base_views",), label="render views", est_s=1.5),
        Node("ghost", n_ghost, ("spec",), ("ghost",), label="context proxies", est_s=0.1, optional=True),
        # sections need the checks (planes + measured dims) and must still render when that optional node failed;
        # the assembly needs the ghost; the composition needs everything
        Node("sections", n_sections, ("base_views", "mesh"), ("sections",), label="section views", est_s=1.2, after=("checks",), optional=True),
        Node("assembly", n_assembly, ("base_views", "mesh"), ("assembly",), label="assembly views", est_s=0.8, after=("ghost",), optional=True),
        Node("compose", n_compose, ("base_views", "mesh", "spec"), ("blueprint",), label="dimension views + compose sheets", est_s=1.0,
             after=("checks", "sections", "assembly")),
    ], max_parallel=4)


def export_graph() -> Graph:
    """State in: session, spec, iteration, out_dir, stl_path, scad_path. Out: files (dict name -> path)."""
    from kintsugi.agent import export as X

    def n_coupon(s):
        return {"coupon": X.compile_coupon(s["session"], Path(s["out_dir"]), s["iteration"])}

    def n_3mf(s):
        return {"mf3": X.write_3mf(s["stl_path"], Path(s["out_dir"]) / "part.3mf", s["spec"])}

    def n_pdf(s):
        return {"pdf": X.blueprint_pdf(s["session"], s["iteration"], Path(s["out_dir"]) / "blueprint.pdf")}

    def n_card(s):
        return {"card": X.write_print_card(s["session"], s["spec"], s["iteration"], Path(s["out_dir"]) / "print_card.md")}

    def n_log(s):
        return {"log": X.write_session_log(s["session"], Path(s["out_dir"]) / "session_log.md")}

    def n_copy(s):
        return {"copies": X.copy_sources(s["session"], s["iteration"], Path(s["out_dir"]))}

    def n_zip(s):
        return {"bundle": X.zip_bundle(Path(s["out_dir"]))}

    return Graph("export", [
        Node("copy_sources", n_copy, ("session", "iteration", "out_dir"), ("copies",), label="STL / SCAD / spec / checks", est_s=0.1),
        Node("coupon", n_coupon, ("session", "out_dir"), ("coupon",), label="compile fit coupon", est_s=5.0, optional=True),
        Node("threemf", n_3mf, ("stl_path", "out_dir", "spec"), ("mf3",), label="3MF", est_s=0.5, optional=True),
        Node("blueprint_pdf", n_pdf, ("session", "iteration", "out_dir"), ("pdf",), label="blueprint PDF", est_s=1.0, optional=True),
        Node("print_card", n_card, ("session", "spec", "iteration", "out_dir"), ("card",), label="print card", est_s=0.1),
        Node("session_log", n_log, ("session", "out_dir"), ("log",), label="session log", est_s=0.1, optional=True),
        Node("bundle", n_zip, ("copies", "card"), ("bundle",), label="zip", est_s=0.3,
             after=("coupon", "threemf", "blueprint_pdf", "session_log")),
    ], max_parallel=5)
