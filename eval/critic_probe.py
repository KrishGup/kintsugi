"""Critic probe: can the code-blind critic catch defects the numeric checks do not?

Takes the passing bottle-handle template, injects one defect per variant that leaves every hard check green
(or nearly), renders the sheets, and asks the critic. A catch is a verdict of "revise" whose discrepancies name
the injected defect.

    python eval/critic_probe.py            # runs all variants (one critic call each)
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kintsugi import TEMPLATES_DIR  # noqa: E402
from kintsugi.agent.critic import critique  # noqa: E402
from kintsugi.checks.run import run_checks  # noqa: E402
from kintsugi.render.blueprint import make_blueprint  # noqa: E402
from kintsugi.scad.compile import compile_scad  # noqa: E402
from kintsugi.spec.model import PartSpec  # noqa: E402

OUT = ROOT / "eval" / "reports" / "critic_probe"
BASE = (TEMPLATES_DIR / "ring_loop_handle.scad").read_text()

VARIANTS = {
    "control": {"scad": BASE, "defect": None, "keywords": []},
    "no_scallops": {
        "scad": BASE.replace("scallops = true;", "scallops = false;"),
        "defect": "design intent asks for finger scallops; they are missing",
        "keywords": ["scallop"],
    },
    "hole_in_bridge": {
        "scad": BASE.replace("module part() {\n    linear_extrude(height = ring_height) difference() { outline2d(); openings2d(); }\n}",
                             "module part() {\n    difference() { linear_extrude(height = ring_height) difference() { outline2d(); openings2d(); }\n"
                             "        translate([ring_od / 2 + bridge_len / 2 + 1, 0, -1]) cylinder(d = 4, h = ring_height + 2); }\n}"),
        "defect": "a 4 mm hole drilled through the bridge, the tension load path between ring and loop",
        "keywords": ["hole", "bridge", "load path", "through"],
    },
    "no_fillets": {
        "scad": BASE.replace("fillet_r = 4;", "fillet_r = 0;"),
        "defect": "sharp inside corners where the bridge meets the ring and the loop (stress concentration)",
        "keywords": ["fillet", "sharp", "corner", "stress"],
    },
    "thin_bridge": {
        "scad": BASE.replace("translate([0, -loop_oh / 2]) square([loop_cx, loop_oh]);", "translate([0, -3]) square([loop_cx, 6]);")
        .replace("bridge_len = 4;", "bridge_len = 12;"),
        "defect": "the bridge between ring and loop is a 6 mm wide neck, far narrower than the loop it carries (thin neck in the load path)",
        "keywords": ["thin", "narrow", "bridge", "neck", "waist", "6 mm", "6.0"],
    },
    "loop_too_thick_walls_ok": {
        "scad": BASE.replace("loop_thick = 6;", "loop_thick = 14;").replace("loop_inner_w = 42;", "loop_inner_w = 40;"),
        "defect": "a 14 mm thick loop wall: heavy, over-built, wastes material and makes the grip bulky",
        "keywords": ["thick", "bulky", "heavy", "over", "material"],
    },
}


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    spec = PartSpec.load(ROOT / "eval" / "specs" / "bottle_handle.yaml")
    results = []
    for name, v in VARIANTS.items():
        d = OUT / name
        d.mkdir(exist_ok=True)
        (d / "part.scad").write_text(v["scad"])
        comp = compile_scad(d / "part.scad", d / "part.stl", {"render_target": "part"})
        if not comp.ok:
            results.append({"variant": name, "error": comp.errors})
            print(name, "compile failed", comp.errors)
            continue
        rep = run_checks(d / "part.stl", spec, iteration=1)
        bp = make_blueprint(d / "part.stl", spec, rep, d / "sheets", 1)
        verdict = await critique(spec, rep, [p for p in (bp.sheet_path, bp.sections_path) if p], model="opus", cwd=d)
        text = json.dumps(verdict.to_dict()).lower()
        caught = None
        if v["defect"] is not None:
            named = any(k.lower() in text for k in v["keywords"])
            caught = verdict.verdict == "revise" and named
        entry = {"variant": name, "defect": v["defect"], "hard_checks_pass": rep.all_hard_pass,
                 "hard_failures": [i.id for i in rep.hard_failures], "verdict": verdict.verdict, "summary": verdict.summary,
                 "discrepancies": verdict.discrepancies, "caught": caught}
        (d / "critic.json").write_text(json.dumps(entry, indent=2))
        results.append(entry)
        print(f"{name}: checks_pass={rep.all_hard_pass} verdict={verdict.verdict} caught={caught} — {verdict.summary[:120]}")
    defects = [r for r in results if r.get("defect")]
    caught = [r for r in defects if r.get("caught")]
    control = [r for r in results if r["variant"] == "control"]
    summary = {"variants": results, "defects": len(defects), "caught": len(caught),
               "catch_rate": round(len(caught) / len(defects), 2) if defects else None,
               "control_verdict": control[0]["verdict"] if control else None}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    lines = ["# Critic probe — does the code-blind critic catch what the numbers miss?", "",
             "Each variant injects one defect into the passing bottle-handle template. Every variant except one keeps all hard checks green, "
             "so the critic can only catch the defect from the drawings.", "",
             "| variant | injected defect | hard checks | verdict | caught |", "|---|---|---|---|---|"]
    for r in results:
        if "error" in r:
            continue
        lines.append(f"| {r['variant']} | {r['defect'] or '(none: control)'} | {'pass' if r['hard_checks_pass'] else 'FAIL: ' + ', '.join(r['hard_failures'])} | "
                     f"{r['verdict']} | {'yes' if r['caught'] else ('no' if r['caught'] is False else '—')} |")
    lines += ["", f"**Catch rate: {len(caught)}/{len(defects)}**; control verdict: {summary['control_verdict']}.", ""]
    for r in results:
        if "error" in r:
            continue
        lines += [f"### {r['variant']}", "", r["summary"], ""]
        for disc in r["discrepancies"]:
            lines.append(f"- [{disc.get('severity')}] {disc.get('where')}: {disc.get('observed')} → {disc.get('suggestion')}")
        lines.append("")
    (OUT / "README.md").write_text("\n".join(lines))
    print(json.dumps({k: v for k, v in summary.items() if k != "variants"}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
