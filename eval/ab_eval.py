"""A/B evaluation: Kintsugi's designer vs human-designed OpenSCAD repair parts, on the same Part Spec.

    python eval/ab_eval.py fetch                      # clone the reference repos, compile them into the spec frame
    python eval/ab_eval.py design --mode templates    # run the designer on every AB spec (sequential; costs model time)
    python eval/ab_eval.py design --mode primitives   # same, with the template catalog hidden from the designer
    python eval/ab_eval.py compare --mode templates   # geometry metrics + blind critic preference -> eval/reports/

The references are never committed; only the specs, the run summaries and the report are.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import trimesh
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kintsugi.checks import geometry as G  # noqa: E402
from kintsugi.checks.run import run_checks  # noqa: E402
from kintsugi.render.raster import VIEWS  # noqa: E402
from kintsugi.spec.model import PartSpec  # noqa: E402

EVAL = ROOT / "eval"
SRC = EVAL / "references" / "src"
REFS = EVAL / "references"
RUNS = EVAL / "runs"
REPORTS = EVAL / "reports"


def manifest() -> list[dict]:
    return yaml.safe_load((EVAL / "references.yaml").read_text())["references"]


# ---- fetch -----------------------------------------------------------------------------------------

def fetch(names: list[str] | None = None) -> None:
    from kintsugi.scad.compile import compile_scad

    SRC.mkdir(parents=True, exist_ok=True)
    for ref in manifest():
        if names and ref["name"] not in names:
            continue
        repo_dir = SRC / ref["repo"].rstrip("/").split("/")[-1]
        if not repo_dir.exists():
            print(f"cloning {ref['repo']}")
            subprocess.run(["git", "clone", "-q", "--depth", "1", ref["repo"], str(repo_dir)], check=True)
        scad = repo_dir / ref["path"]
        raw = REFS / f"{ref['name']}_raw.stl"
        r = compile_scad(scad, raw, timeout_s=300)
        if not r.ok:
            print(f"  {ref['name']}: compile failed: {r.errors}")
            continue
        m = G.load_mesh(raw)
        tr = ref.get("transform", {})
        for ax, ang in zip("xyz", tr.get("rotate", [0, 0, 0])):
            if ang:
                m.apply_transform(trimesh.transformations.rotation_matrix(np.radians(ang), {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}[ax]))
        m.apply_translation(tr.get("translate", [0, 0, 0]))
        if m.bounds[0][2] < -1e-6:  # put the reference on the bed if the author did not
            m.apply_translation([0, 0, -m.bounds[0][2]])
        out = REFS / f"{ref['name']}_ref.stl"
        m.export(out)
        raw.unlink(missing_ok=True)
        spec = PartSpec.load(ROOT / ref["spec"])
        rep = run_checks(out, spec)
        fails = [i.id for i in rep.items if i.passed is False]
        print(f"  {ref['name']}: {len(m.faces)} tris, watertight={m.is_watertight}, hard_pass={rep.all_hard_pass}, fails={fails}")


# ---- design ----------------------------------------------------------------------------------------

async def design(names: list[str] | None, mode: str, model: str | None, budget: int, critic_rounds: int) -> None:
    from kintsugi.agent.designer import run_designer
    from kintsugi.session.workspace import Session

    for ref in manifest():
        if names and ref["name"] not in names:
            continue
        run_dir = RUNS / mode
        run_dir.mkdir(parents=True, exist_ok=True)
        summary = run_dir / f"{ref['name']}.json"
        if summary.exists() and json.loads(summary.read_text()).get("status") == "done":
            print(f"skip {ref['name']} (done)")
            continue
        spec = PartSpec.load(ROOT / ref["spec"])
        sess_dir = run_dir / ref["name"]
        if sess_dir.exists():
            shutil.rmtree(sess_dir)
        s = Session.create(ref["name"], spec, sessions_dir=run_dir, session_id=ref["name"])
        strategy = None
        if mode == "primitives":
            strategy = ("Do NOT use the template catalog for this run (do not call read_template; ignore list_templates). "
                        "Design from primitives and BOSL2 only.")
        print(f"designing {ref['name']} ({mode}) ...", flush=True)
        t0 = time.time()
        out = await run_designer(s, spec=spec, model=model, budget=budget, critic_rounds=critic_rounds, strategy=strategy)
        if out.status == "error" and "stalled" in (out.state.error or ""):
            print("  stalled; retrying once", flush=True)
            shutil.rmtree(sess_dir)
            s = Session.create(ref["name"], spec, sessions_dir=run_dir, session_id=ref["name"])
            out = await run_designer(s, spec=spec, model=model, budget=budget, critic_rounds=critic_rounds, strategy=strategy)
        d = out.to_dict()
        d["duration_s"] = round(time.time() - t0, 1)
        d["session"] = str(sess_dir)
        summary.write_text(json.dumps(d, indent=2))
        print(f"  -> {d['status']} in {d['duration_s']}s, {d['iterations']} iterations, ${d['cost_usd']}", flush=True)


# ---- compare ---------------------------------------------------------------------------------------

def _silhouette(mesh: trimesh.Trimesh, view: str, bounds: np.ndarray, scale: float) -> np.ndarray:
    from kintsugi.render.raster import render_view
    vi = render_view(mesh, view, scale, margin_px=10, bounds_cam=bounds, hidden_lines=False, shade=False, grid_mm=0)
    return np.isfinite(vi.depth) & (vi.depth > -1e30)


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    a, b = a[:h, :w], b[:h, :w]
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter / union) if union else 0.0


def _chamfer(a: trimesh.Trimesh, b: trimesh.Trimesh, n: int = 4000) -> dict:
    pa, _ = trimesh.sample.sample_surface(a, n, seed=0)
    pb, _ = trimesh.sample.sample_surface(b, n, seed=1)
    da = trimesh.proximity.closest_point(b, pa)[1]
    db = trimesh.proximity.closest_point(a, pb)[1]
    return {"mean_a_to_b": float(da.mean()), "mean_b_to_a": float(db.mean()), "p95_a_to_b": float(np.percentile(da, 95)),
            "p95_b_to_a": float(np.percentile(db, 95)), "chamfer": float((da.mean() + db.mean()) / 2)}


def geometry_metrics(ref: trimesh.Trimesh, kin: trimesh.Trimesh) -> dict:
    out: dict = {}
    views = ["top", "front", "right"]
    lo = np.minimum(ref.bounds[0], kin.bounds[0])
    hi = np.maximum(ref.bounds[1], kin.bounds[1])
    allv = np.vstack([ref.vertices, kin.vertices])
    ext = float(max((allv.max(axis=0) - allv.min(axis=0)).max(), 1e-6))
    scale = float(min(10.0, 400.0 / ext))
    ious = {}
    for v in views:
        R = VIEWS[v]
        V = np.vstack([ref.vertices, kin.vertices]) @ R.T
        b = np.array([V[:, :2].min(axis=0) - 1, V[:, :2].max(axis=0) + 1])
        ious[v] = _iou(_silhouette(ref, v, b, scale), _silhouette(kin, v, b, scale))
    out["silhouette_iou"] = ious
    out["silhouette_iou_mean"] = float(np.mean(list(ious.values())))
    out["volume_ref_mm3"] = float(abs(ref.volume)) if ref.is_watertight else None
    out["volume_kin_mm3"] = float(abs(kin.volume)) if kin.is_watertight else None
    out["bbox_ref"] = [round(float(x), 2) for x in ref.extents]
    out["bbox_kin"] = [round(float(x), 2) for x in kin.extents]
    out["surface_ref_mm2"] = float(ref.area)
    out["surface_kin_mm2"] = float(kin.area)
    out["chamfer_mm"] = _chamfer(ref, kin)
    del lo, hi
    return out


def _check_table(rep) -> dict:
    return {i.id: {"passed": i.passed, "measured": i.measured, "target": i.target, "tol": i.tol, "kind": i.kind} for i in rep.items}


async def blind_preference(spec: PartSpec, sheets_a: list[Path], sheets_b: list[Path], model: str | None) -> dict:
    """Ask the critic to compare two candidates (order randomized by the caller) without knowing which is human."""
    from agent_sdk import AssistantMessage, AgentOptions, SDKClient, TextBlock

    from kintsugi.agent.critic import _image_block

    prompt = (
        "You are a senior mechanical engineer judging two candidate replacement parts, A and B, designed to the same Part Spec. "
        "You see their blueprint sheets (orthographic views, sections with measured dimensions, assembly views). "
        "Score each on fit (does it meet the interface dimensions and clearances), printability, strength for the stated use, "
        "and design intent (does it do what the spec asks, elegantly), 1-10 each, and pick the one you would print. "
        "Respond with ONLY JSON: {\"preferred\": \"A\"|\"B\"|\"tie\", \"scores\": {\"A\": {\"fit\":n,\"printability\":n,\"strength\":n,\"intent\":n,\"overall\":n}, "
        "\"B\": {...}}, \"reasoning\": \"3-6 sentences\"}"
    )
    content = [{"type": "text", "text": "PART SPEC:\n" + spec.summary_for_model()}]
    for label, sheets in (("A", sheets_a), ("B", sheets_b)):
        for p in sheets:
            blk = _image_block(p, max_side=1400)
            if blk:
                content.append({"type": "text", "text": f"CANDIDATE {label} — {p.name}"})
                content.append(blk)
    content.append({"type": "text", "text": "Judge now. JSON only."})
    options = AgentOptions(system_prompt=prompt, model=model or "opus", allowed_tools=[], max_turns=1, setting_sources=[],
                                 disallowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch", "Task"],
                                 permission_mode="dontAsk", cwd=str(ROOT))
    out = []

    async def gen():
        yield {"type": "user", "message": {"role": "user", "content": content}, "parent_tool_use_id": None, "session_id": "judge"}

    async with SDKClient(options) as client:
        await client.query(gen(), session_id="judge")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for b in msg.content:
                    if isinstance(b, TextBlock):
                        out.append(b.text)
    text = "\n".join(out)
    import re
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else {"error": "no json", "raw": text[:500]}
    except json.JSONDecodeError:
        return {"error": "bad json", "raw": text[:500]}


async def compare(names: list[str] | None, mode: str, judge_model: str | None, with_judge: bool = True) -> None:
    from kintsugi.render.blueprint import make_blueprint

    REPORTS.mkdir(parents=True, exist_ok=True)
    results = []
    for ref in manifest():
        if names and ref["name"] not in names:
            continue
        name = ref["name"]
        spec = PartSpec.load(ROOT / ref["spec"])
        ref_stl = REFS / f"{name}_ref.stl"
        summary_p = RUNS / mode / f"{name}.json"
        if not ref_stl.exists() or not summary_p.exists():
            print(f"skip {name}: missing reference or run")
            continue
        summary = json.loads(summary_p.read_text())
        sess = Path(summary["session"])
        hist = json.loads((sess / "history.json").read_text()) if (sess / "history.json").exists() else []
        oks = [h["iteration"] for h in hist if h.get("ok")]
        last = oks[-1] if oks else (hist[-1]["iteration"] if hist else None)
        if last is None:
            print(f"skip {name}: no iteration")
            continue
        kin_stl = sess / "iterations" / f"iter_{last:02d}" / "part.stl"
        if not kin_stl.exists():
            print(f"skip {name}: no stl")
            continue
        ref_mesh = G.load_mesh(ref_stl)
        kin_mesh = G.load_mesh(kin_stl)
        rep_ref = run_checks(ref_stl, spec, iteration=0)
        rep_kin = run_checks(kin_stl, spec, iteration=last)
        out_dir = REPORTS / mode / name
        out_dir.mkdir(parents=True, exist_ok=True)
        bp_ref = make_blueprint(ref_stl, spec, rep_ref, out_dir / "ref", 0, part_name=f"{name} (human)")
        bp_kin = make_blueprint(kin_stl, spec, rep_kin, out_dir / "kin", last, part_name=f"{name} (kintsugi)")
        metrics = geometry_metrics(ref_mesh, kin_mesh)
        entry = {
            "name": name, "title": ref["title"], "mode": mode, "kintsugi_status": summary.get("status"),
            "kintsugi_iterations": summary.get("iterations"), "kintsugi_cost_usd": summary.get("cost_usd"),
            "kintsugi_duration_s": summary.get("duration_s"), "final_iteration": last,
            "ref_hard_pass": rep_ref.all_hard_pass, "kin_hard_pass": rep_kin.all_hard_pass,
            "ref_fails": [i.id for i in rep_ref.items if i.passed is False], "kin_fails": [i.id for i in rep_kin.items if i.passed is False],
            "interface_dims": {}, "metrics": metrics,
            "sheets": {"ref": str(bp_ref.sheet_path.relative_to(ROOT)), "kin": str(bp_kin.sheet_path.relative_to(ROOT)),
                       "ref_sections": str(bp_ref.sections_path.relative_to(ROOT)) if bp_ref.sections_path else None,
                       "kin_sections": str(bp_kin.sections_path.relative_to(ROOT)) if bp_kin.sections_path else None},
            "critic": summary.get("critic", []), "narration": summary.get("narration", ""),
        }
        tr, tk = _check_table(rep_ref), _check_table(rep_kin)
        for qname, dim, is_itf in spec.all_dims():
            if qname in tr and qname in tk:
                entry["interface_dims"][qname] = {"target": tr[qname]["target"], "tol": tr[qname]["tol"], "ref": tr[qname]["measured"],
                                                  "kin": tk[qname]["measured"], "ref_pass": tr[qname]["passed"], "kin_pass": tk[qname]["passed"],
                                                  "interface": is_itf}
        if with_judge:
            flip = random.Random(hash(name) & 0xFFFF).random() < 0.5
            a = [p for p in (bp_kin.sheet_path, bp_kin.sections_path) if p] if flip else [p for p in (bp_ref.sheet_path, bp_ref.sections_path) if p]
            b = [p for p in (bp_ref.sheet_path, bp_ref.sections_path) if p] if flip else [p for p in (bp_kin.sheet_path, bp_kin.sections_path) if p]
            j = await blind_preference(spec, a, b, judge_model)
            pref = j.get("preferred")
            who = {"A": "kintsugi" if flip else "human", "B": "human" if flip else "kintsugi"}.get(pref, pref)
            entry["judge"] = {"raw": j, "A_is": "kintsugi" if flip else "human", "preferred": who,
                              "scores": {("kintsugi" if (k == "A") == flip else "human"): v for k, v in (j.get("scores") or {}).items()}}
        results.append(entry)
        print(f"{name}: kin pass={rep_kin.all_hard_pass} ref pass={rep_ref.all_hard_pass} IoU={metrics['silhouette_iou_mean']:.2f} "
              f"chamfer={metrics['chamfer_mm']['chamfer']:.2f} judge={entry.get('judge', {}).get('preferred')}")
    (REPORTS / f"ab_{mode}.json").write_text(json.dumps(results, indent=2, default=str))
    write_report(results, mode)


def write_report(results: list[dict], mode: str) -> None:
    lines = [f"# A/B report — Kintsugi designer vs human-designed OpenSCAD parts ({mode} mode)", "",
             "Each reference is a human-designed replacement part from a public OpenSCAD repository. A Part Spec was written from the "
             "reference's own mating dimensions (its interfaces), the designer built a part from the spec alone (it never saw the reference), "
             "and both were measured by the same checker and judged blind by the critic (A/B order randomized).", "",
             "| part | kin checks | human checks | iterations | cost | silhouette IoU | Chamfer (mm) | volume kin/human | blind judge |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        m = r["metrics"]
        vr = (m["volume_kin_mm3"] / m["volume_ref_mm3"]) if m.get("volume_kin_mm3") and m.get("volume_ref_mm3") else None
        judge = r.get("judge", {}).get("preferred", "—")
        sc = r.get("judge", {}).get("scores", {})
        js = f"{judge}" + (f" (kin {sc.get('kintsugi', {}).get('overall', '?')} / human {sc.get('human', {}).get('overall', '?')})" if sc else "")
        lines.append(f"| {r['name']} | {'pass' if r['kin_hard_pass'] else 'FAIL: ' + ', '.join(r['kin_fails'])} | "
                     f"{'pass' if r['ref_hard_pass'] else 'fail: ' + ', '.join(r['ref_fails'])} | {r['kintsugi_iterations']} | ${r['kintsugi_cost_usd']} | "
                     f"{m['silhouette_iou_mean']:.2f} | {m['chamfer_mm']['chamfer']:.2f} | {vr:.2f} | {js} |" if vr else
                     f"| {r['name']} | {'pass' if r['kin_hard_pass'] else 'FAIL'} | {'pass' if r['ref_hard_pass'] else 'fail'} | {r['kintsugi_iterations']} | "
                     f"${r['kintsugi_cost_usd']} | {m['silhouette_iou_mean']:.2f} | {m['chamfer_mm']['chamfer']:.2f} | — | {js} |")
    lines += ["", "## Interface dimensions (measured on the meshes)", ""]
    for r in results:
        lines += [f"### {r['name']} — {r['title']}", "", "| dimension | target | human | kintsugi |", "|---|---|---|---|"]
        for k, v in r["interface_dims"].items():
            tgt = v["target"]
            tgt_s = f"{tgt}" + (f" ±{v['tol']}" if v["tol"] is not None and isinstance(tgt, (int, float)) else "")
            lines.append(f"| {k} | {tgt_s} | {v['ref']} {'✓' if v['ref_pass'] else ('✗' if v['ref_pass'] is False else '')} | "
                         f"{v['kin']} {'✓' if v['kin_pass'] else ('✗' if v['kin_pass'] is False else '')} |")
        if r.get("judge"):
            raw = r["judge"]["raw"]
            lines += ["", f"**Blind judge** preferred **{r['judge']['preferred']}**. {raw.get('reasoning', '')}"]
        lines += ["", f"Sheets: human `{r['sheets']['ref']}` · kintsugi `{r['sheets']['kin']}`", ""]
    lines += ["", "## Reading the numbers", "",
              "- *checks*: every hard check in the spec (interface dimensions with clearance, interference against the context proxies, walls, topology).",
              "- *silhouette IoU*: overlap of top/front/right silhouettes at the same scale and frame; low values mean a different body shape, which is allowed (only interfaces are specified).",
              "- *Chamfer*: mean surface-to-surface distance (mm) between the two meshes; a shape-difference measure, not a quality measure.",
              "- *blind judge*: the critic model scoring both sheets without knowing which is human-designed."]
    (REPORTS / f"ab_{mode}.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {REPORTS / f'ab_{mode}.md'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fetch")
    p.add_argument("--parts", nargs="*")
    p = sub.add_parser("design")
    p.add_argument("--parts", nargs="*")
    p.add_argument("--mode", default="templates", choices=["templates", "primitives"])
    p.add_argument("--model")
    p.add_argument("--budget", type=int, default=8)
    p.add_argument("--critic-rounds", type=int, default=2)
    p = sub.add_parser("compare")
    p.add_argument("--parts", nargs="*")
    p.add_argument("--mode", default="templates")
    p.add_argument("--judge-model")
    p.add_argument("--no-judge", action="store_true")
    a = ap.parse_args()
    if a.cmd == "fetch":
        fetch(a.parts)
    elif a.cmd == "design":
        asyncio.run(design(a.parts, a.mode, a.model, a.budget, a.critic_rounds))
    elif a.cmd == "compare":
        asyncio.run(compare(a.parts, a.mode, a.judge_model, not a.no_judge))


if __name__ == "__main__":
    main()
