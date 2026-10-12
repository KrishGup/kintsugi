"""Export bundle: oriented STL/3MF, customizer-ready .scad, blueprint PDF, print card, spec, session log, zip."""

from __future__ import annotations

import json
import math
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image

from kintsugi.checks import geometry as G
from kintsugi.scad.compile import compile_scad
from kintsugi.session.workspace import Session
from kintsugi.spec.model import PartSpec


def last_passing_iteration(session: Session) -> int | None:
    hist = session.dir / "history.json"
    if hist.exists():
        try:
            h = json.loads(hist.read_text(encoding="utf-8"))
            oks = [e["iteration"] for e in h if e.get("ok")]
            if oks:
                return oks[-1]
        except json.JSONDecodeError:
            pass
    n = int(session.meta.get("iteration", 0))
    return n or None


def print_card(spec: PartSpec, checks: dict[str, Any] | None, coupon_available: bool, params: list[dict[str, Any]] | None = None,
               presets: dict[str, dict[str, Any]] | None = None) -> str:
    p = spec.print
    walls = max(2, math.ceil(p.min_wall / p.nozzle))
    load_bearing = any("load" in r.id.lower() or "carry" in r.text.lower() or "kg" in r.text.lower() for r in spec.requirements)
    infill = "30% gyroid" if load_bearing else "20% gyroid"
    if load_bearing:
        walls = max(walls, 4)
    lines = [f"# Print card — {spec.part.name}", ""]
    lines += [f"- **Material**: {p.material}", f"- **Nozzle / layer**: {p.nozzle:g} mm / {p.layer_height:g} mm",
              f"- **Walls**: {walls} perimeters ({walls * p.nozzle:.1f} mm)", f"- **Infill**: {infill}",
              f"- **Orientation**: {p.orientation_hint or 'as exported (Z up, bed at z = 0)'}"]
    supports = "no"
    if checks and checks.get("printability"):
        pr = checks["printability"]
        frac = pr.get("overhang_fraction", 0.0)
        supports = "no" if frac <= 0.05 else f"yes — {frac*100:.0f}% of the surface overhangs beyond 45° (or reorient)"
        if checks.get("orientations"):
            best = checks["orientations"][0]
            if best.get("name") != "as modeled (Z up)" and best.get("overhang_fraction", 1) < frac - 0.02:
                lines.append(f"- **Better orientation found**: {best['name']} (overhang {best['overhang_fraction']*100:.0f}% vs {frac*100:.0f}%)")
    lines.append(f"- **Supports**: {supports}")
    if load_bearing:
        lines.append("- **Why these settings**: the part carries load; extra perimeters do more for strength than infill, and the modeled "
                     "orientation keeps the load along the layers rather than across them.")
    unconfirmed = spec.unconfirmed_interface_dims()
    lines.append("")
    if unconfirmed:
        lines.append(f"> **Fit unconfirmed**: {', '.join(unconfirmed)} were never confirmed by a measurement or a coupon. "
                     "Print `coupon.stl` first and check which ring fits before printing the full part.")
    else:
        lines.append("> All interface dimensions are confirmed.")
    if coupon_available:
        lines += ["", "## Fit coupon", "`coupon.stl` holds the mating feature only, in three clearances (−0.2 / 0 / +0.2 mm). "
                  "Print it flat, try each on the object, and set `clearance` to the one that slides on without force."]
    lines += ["", "## Customizer", "Open `part.scad` in OpenSCAD (Window → Customizer) to adjust any dimension; every user-facing "
              "parameter has a slider. Re-export STL after changes."]
    shown = [q for q in (params or []) if q.get("name") != "render_target"]
    if shown:
        lines += ["", "### Parameters as printed", "", "| parameter | value | spec |", "|---|---|---|"]
        for q in shown:
            v = q.get("value")
            unit = q.get("unit") or ""
            val = f"{v:g} {unit}".strip() if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v).lower() if isinstance(v, bool) else str(v)
            b = q.get("binding") or {}
            spec_col = ""
            if b:
                if b.get("target") is not None:
                    spec_col = f"{b['dim']} = {b['target']:g} ± {b.get('tol') or 0:g} ({b.get('status', 'unknown')})"
                else:
                    lim = " ".join(x for x in (f"≥ {b['min']:g}" if b.get("min") is not None else "", f"≤ {b['max']:g}" if b.get("max") is not None else "") if x)
                    spec_col = f"{b['dim']} {lim}".strip()
            label = q.get("label") or q["name"]
            lines.append(f"| {label} (`{q['name']}`) | {val} | {spec_col} |")
    if presets:
        lines += ["", f"Presets in `part.json` (OpenSCAD's parameter sets): {', '.join(sorted(presets))}."]
    return "\n".join(lines) + "\n"


# ---- export pieces (each is a node of the export graph) ------------------------------------------------

def copy_sources(session: Session, n: int, out: Path) -> dict[str, str]:
    it = session.iteration_dir(n)
    files: dict[str, str] = {}
    shutil.copy(it / "part.scad", out / "part.scad")
    files["scad"] = str(out / "part.scad")
    if (it / "part.stl").exists():
        shutil.copy(it / "part.stl", out / "part.stl")
        files["stl"] = str(out / "part.stl")
    if (it / "checks.json").exists():
        shutil.copy(it / "checks.json", out / "checks.json")
        files["checks"] = str(out / "checks.json")
    session.spec().save(out / "spec.yaml")
    files["spec"] = str(out / "spec.yaml")
    presets = session.dir / "part.json"          # the customizer's presets, in OpenSCAD's parameter-sets format
    if presets.exists():
        shutil.copy(presets, out / "part.json")
        files["presets"] = str(out / "part.json")
    return files


def write_3mf(stl_path: str | Path, dest: Path, spec: PartSpec | None = None) -> str | None:
    m = G.load_mesh(stl_path)
    m.export(dest)
    return str(dest)


def compile_coupon(session: Session, out: Path, n: int | None = None) -> str | None:
    it = session.iteration_dir(n or int(session.meta.get("exported_iteration") or session.meta.get("iteration", 0)))
    src = (it / "part.scad").read_text(encoding="utf-8")
    if "render_target" not in src or "module coupon" not in src:
        return None
    r = compile_scad(it / "part.scad", out / "coupon.stl", {"render_target": "coupon"}, timeout_s=180)
    return str(out / "coupon.stl") if r.ok else None


def blueprint_pdf(session: Session, n: int, dest: Path) -> str | None:
    it = session.iteration_dir(n)
    sheets = [p for p in sorted((it / "sheets").glob(f"iter_{n:02d}_*.png")) if p.name.endswith(("_sheet.png", "_sections.png"))]
    if not sheets:
        return None
    Image.init()  # register the JPEG plugin the PDF writer needs
    ims = [Image.open(p).convert("RGB") for p in sheets]
    ims[0].save(dest, save_all=True, append_images=ims[1:], resolution=150.0)
    shutil.copy(sheets[0], dest.parent / "blueprint_views.png")
    return str(dest)


def write_print_card(session: Session, spec: PartSpec, n: int, dest: Path) -> str:
    it = session.iteration_dir(n)
    checks = json.loads((it / "checks.json").read_text(encoding="utf-8")) if (it / "checks.json").exists() else None
    src = (it / "part.scad").read_text(encoding="utf-8")
    coupon_possible = "render_target" in src and "module coupon" in src
    from kintsugi.scad.customizer import customizer_model, presets_from_openscad
    try:
        params = customizer_model(src, spec)["params"]
    except Exception:  # noqa: BLE001 — the card must never fail on a parsing corner case
        params = []
    presets: dict[str, dict[str, Any]] = {}
    pj = session.dir / "part.json"
    if pj.exists():
        try:
            presets = presets_from_openscad(json.loads(pj.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, AttributeError):
            presets = {}
    dest.write_text(print_card(spec, checks, coupon_possible, params, presets), encoding="utf-8")
    return str(dest)


def write_session_log(session: Session, dest: Path) -> str:
    dest.write_text(session_log(session), encoding="utf-8")
    return str(dest)


def zip_bundle(out: Path, part_name: str | None = None) -> str:
    z = out / "bundle.zip"
    name = part_name or "part"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(out.iterdir()):
            if f.is_file() and f.name not in ("bundle.zip", "export_graph.json"):
                zf.write(f, arcname=f"{name}/{f.name}")
    return str(z)


def export_bundle(session: Session, iteration: int | None = None) -> dict[str, Any]:
    """Export the last passing iteration through the export graph (the independent pieces run in parallel)."""
    from kintsugi.graph.core import run_sync
    from kintsugi.graph.pipelines import export_graph

    spec = session.spec()
    n = iteration or last_passing_iteration(session)
    if not n:
        raise RuntimeError("no iteration to export")
    it = session.iteration_dir(n)
    out = session.dir / "export"
    out.mkdir(exist_ok=True)
    for f in out.iterdir():
        if f.is_file():
            f.unlink()
    state: dict[str, Any] = {"session": session, "spec": spec, "iteration": n, "out_dir": str(out), "scad_path": str(it / "part.scad")}
    if (it / "part.stl").exists():
        state["stl_path"] = str(it / "part.stl")
    g = export_graph()
    # the zip must contain everything, so name it with the part name
    g.nodes["bundle"].fn = lambda s: {"bundle": zip_bundle(Path(s["out_dir"]), spec.part.name)}
    trace = run_sync(g, state, emit=lambda kind, **d: session.emit(kind, **d))
    (out / "export_graph.json").write_text(json.dumps(trace.to_dict(), indent=2), encoding="utf-8")
    files: dict[str, str] = dict(state.get("copies") or {})
    for key, sk in (("3mf", "mf3"), ("coupon", "coupon"), ("blueprint", "pdf"), ("print_card", "card"), ("session_log", "log"), ("bundle", "bundle")):
        if state.get(sk):
            files[key] = state[sk]
    session.update_meta(exported_iteration=n, exported_at=time.time())
    session.emit("export", iteration=n, files=sorted(f.name for f in out.iterdir() if f.name != "export_graph.json"),
                 graph={"wall_s": round(trace.wall_s, 2), "serial_s": round(trace.serial_s, 2), "critical_path": trace.critical_path})
    return {"iteration": n, "files": files, "unconfirmed": spec.unconfirmed_interface_dims(), "graph": trace.to_dict()}


def session_log(session: Session) -> str:
    meta = session.meta
    lines = [f"# Session log — {meta.get('name')}", "", f"- id: {meta.get('id')}", f"- status: {meta.get('status')}",
             f"- model: {meta.get('model', '?')}", ""]
    hist = session.dir / "history.json"
    if hist.exists():
        lines.append("## Iterations")
        for e in json.loads(hist.read_text(encoding="utf-8")):
            lines.append(f"- {e['iteration']:02d}: {'pass' if e.get('ok') else ('compile error' if not e.get('compile_ok') else 'fail: ' + ', '.join(e.get('failures', [])))}"
                         + (f" — {e['label']}" if e.get("label") else ""))
    crit = sorted((session.dir / "critic").glob("*.json"))
    if crit:
        lines += ["", "## Critic"]
        for c in crit:
            d = json.loads(c.read_text(encoding="utf-8"))
            lines.append(f"- {c.stem}: {d.get('verdict')} — {d.get('summary')}")
            for disc in d.get("discrepancies", []):
                lines.append(f"  - [{disc.get('severity')}] {disc.get('where')}: {disc.get('suggestion')}")
    if meta.get("narration"):
        lines += ["", "## Designer's note", meta["narration"]]
    return "\n".join(lines) + "\n"
