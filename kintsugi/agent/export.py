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
            h = json.loads(hist.read_text())
            oks = [e["iteration"] for e in h if e.get("ok")]
            if oks:
                return oks[-1]
        except json.JSONDecodeError:
            pass
    n = int(session.meta.get("iteration", 0))
    return n or None


def print_card(spec: PartSpec, checks: dict[str, Any] | None, coupon_available: bool) -> str:
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
    return "\n".join(lines) + "\n"


def export_bundle(session: Session, iteration: int | None = None) -> dict[str, Any]:
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
    files: dict[str, Path] = {}
    # part files
    shutil.copy(it / "part.scad", out / "part.scad")
    files["scad"] = out / "part.scad"
    if (it / "part.stl").exists():
        shutil.copy(it / "part.stl", out / "part.stl")
        files["stl"] = out / "part.stl"
        try:
            m = G.load_mesh(it / "part.stl")
            m.export(out / "part.3mf")
            files["3mf"] = out / "part.3mf"
        except Exception:
            pass
    # coupon
    coupon_ok = False
    try:
        if "render_target" in (it / "part.scad").read_text(encoding="utf-8") and "module coupon" in (it / "part.scad").read_text(encoding="utf-8"):
            r = compile_scad(it / "part.scad", out / "coupon.stl", {"render_target": "coupon"}, timeout_s=180)
            coupon_ok = r.ok
            if r.ok:
                files["coupon"] = out / "coupon.stl"
    except Exception:
        pass
    # blueprint pdf
    sheets = [p for p in sorted((it / "sheets").glob(f"iter_{n:02d}_*.png")) if p.name.endswith(("_sheet.png", "_sections.png"))]
    if sheets:
        Image.init()  # register the JPEG plugin the PDF writer needs
        ims = [Image.open(p).convert("RGB") for p in sheets]
        ims[0].save(out / "blueprint.pdf", save_all=True, append_images=ims[1:], resolution=150.0)
        files["blueprint"] = out / "blueprint.pdf"
        shutil.copy(sheets[0], out / "blueprint_views.png")
    # checks + spec + card + log
    checks = None
    if (it / "checks.json").exists():
        shutil.copy(it / "checks.json", out / "checks.json")
        checks = json.loads((it / "checks.json").read_text())
    spec.save(out / "spec.yaml")
    (out / "print_card.md").write_text(print_card(spec, checks, coupon_ok), encoding="utf-8")
    files["print_card"] = out / "print_card.md"
    (out / "session_log.md").write_text(session_log(session), encoding="utf-8")
    # zip
    z = out / "bundle.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(out.iterdir()):
            if f.is_file() and f.name != "bundle.zip":
                zf.write(f, arcname=f"{spec.part.name}/{f.name}")
    files["bundle"] = z
    session.update_meta(exported_iteration=n, exported_at=time.time())
    session.emit("export", iteration=n, files=sorted(f.name for f in out.iterdir()))
    return {"iteration": n, "files": {k: str(v) for k, v in files.items()}, "unconfirmed": spec.unconfirmed_interface_dims()}


def session_log(session: Session) -> str:
    meta = session.meta
    lines = [f"# Session log — {meta.get('name')}", "", f"- id: {meta.get('id')}", f"- status: {meta.get('status')}",
             f"- model: {meta.get('model', '?')}", ""]
    hist = session.dir / "history.json"
    if hist.exists():
        lines.append("## Iterations")
        for e in json.loads(hist.read_text()):
            lines.append(f"- {e['iteration']:02d}: {'pass' if e.get('ok') else ('compile error' if not e.get('compile_ok') else 'fail: ' + ', '.join(e.get('failures', [])))}"
                         + (f" — {e['label']}" if e.get("label") else ""))
    crit = sorted((session.dir / "critic").glob("*.json"))
    if crit:
        lines += ["", "## Critic"]
        for c in crit:
            d = json.loads(c.read_text())
            lines.append(f"- {c.stem}: {d.get('verdict')} — {d.get('summary')}")
            for disc in d.get("discrepancies", []):
                lines.append(f"  - [{disc.get('severity')}] {disc.get('where')}: {disc.get('suggestion')}")
    if meta.get("narration"):
        lines += ["", "## Designer's note", meta["narration"]]
    return "\n".join(lines) + "\n"
