"""One iteration of the verification loop: compile -> checks -> blueprint -> record -> policy signals."""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kintsugi.checks.run import CheckReport, run_checks
from kintsugi.render.blueprint import BlueprintResult, make_blueprint
from kintsugi.scad.compile import CompileResult, compile_scad
from kintsugi.scad.customizer import parse_customizer
from kintsugi.session.workspace import Session
from kintsugi.spec.model import PartSpec

ITERATION_BUDGET = 8


@dataclass
class IterationResult:
    iteration: int
    compile: CompileResult
    checks: CheckReport | None
    blueprint: BlueprintResult | None
    dir: Path
    duration_s: float
    signals: list[str] = field(default_factory=list)  # policy messages for the designer
    budget_left: int = 0

    @property
    def ok(self) -> bool:
        return self.compile.ok and self.checks is not None and self.checks.all_hard_pass

    def summary_for_model(self) -> str:
        lines = [f"=== ITERATION {self.iteration} ({self.duration_s:.1f}s) ==="]
        lines.append(self.compile.summary())
        if self.checks:
            lines.append(self.checks.summary_for_model())
        if self.blueprint:
            lines.append("BLUEPRINT SHEETS (look at them with the Read tool before deciding the next change):")
            lines.append(f"  views:    {self.blueprint.sheet_path}")
            if self.blueprint.sections_path:
                lines.append(f"  sections: {self.blueprint.sections_path}")
            for k, p in self.blueprint.section_paths.items():
                lines.append(f"  section {k}: {p}")
            for k, p in self.blueprint.assembly_paths.items():
                lines.append(f"  assembly {k}: {p}")
        for s in self.signals:
            lines.append(f"POLICY: {s}")
        lines.append(f"Iterations left in budget: {self.budget_left}")
        if self.ok:
            lines.append("STATUS: all hard checks pass. Review the sheets once for shape/intent problems the numbers cannot see, "
                         "then call finish (or fix and iterate again if the drawing shows a problem).")
        else:
            lines.append("STATUS: not passing yet. Fix the failing items and iterate again.")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration, "ok": self.ok, "compile": self.compile.to_dict(),
            "checks": self.checks.to_dict() if self.checks else None,
            "blueprint": self.blueprint.to_dict() if self.blueprint else None,
            "dir": str(self.dir), "duration_s": round(self.duration_s, 2), "signals": self.signals, "budget_left": self.budget_left,
        }


def run_iteration(session: Session, *, scad_text: str | None = None, spec: PartSpec | None = None, budget: int = ITERATION_BUDGET,
                  wall_samples: int = 1500, label: str = "") -> IterationResult:
    t0 = time.time()
    spec = spec or session.spec()
    if scad_text is not None:
        session.scad_path.write_text(scad_text, encoding="utf-8")
    if not session.scad_path.exists():
        raise FileNotFoundError("part.scad missing in session")
    meta = session.meta
    n = int(meta.get("iteration", 0)) + 1
    it_dir = session.iteration_dir(n)
    shutil.copy(session.scad_path, it_dir / "part.scad")

    # compile
    comp = compile_scad(session.scad_path, it_dir / "part.stl", {"render_target": "part"} if _has_render_target(session.scad_path) else None,
                        timeout_s=240)
    (it_dir / "compile.json").write_text(json.dumps(comp.to_dict(), indent=2))
    checks = None
    bp = None
    signals: list[str] = []
    if comp.ok:
        shutil.copy(it_dir / "part.stl", session.stl_path)
        try:
            checks = run_checks(it_dir / "part.stl", spec, iteration=n, wall_samples=wall_samples)
            checks.save(it_dir / "checks.json")
            shutil.copy(it_dir / "checks.json", session.dir / "checks.json")
        except Exception as e:
            signals.append(f"checks failed to run: {e}")
        try:
            bp = make_blueprint(it_dir / "part.stl", spec, checks, it_dir / "sheets", n)
            for src in (bp.sheet_path, bp.sections_path):
                if src:
                    shutil.copy(src, session.dir / "sheets" / src.name)
        except Exception as e:
            signals.append(f"blueprint failed to render: {e}")
        try:
            params = [p.to_dict() for p in parse_customizer(session.scad_path.read_text())]
            (it_dir / "params.json").write_text(json.dumps(params, indent=2))
            (session.dir / "params.json").write_text(json.dumps(params, indent=2))
            if not params:
                signals.append("no customizer parameters found: put user-facing dimensions in a parameter block with // [min:step:max] annotations")
        except Exception:
            pass
    # policy: history-based signals
    hist = _load_history(session)
    entry = {"iteration": n, "ok": bool(comp.ok and checks and checks.all_hard_pass), "compile_ok": comp.ok,
             "failures": [i.id for i in (checks.hard_failures if checks else [])],
             "measured": {i.id: i.measured for i in (checks.items if checks else []) if isinstance(i.measured, (int, float))},
             "targets": {i.id: i.target for i in (checks.items if checks else []) if isinstance(i.target, (int, float))},
             "label": label}
    hist.append(entry)
    _save_history(session, hist)
    signals += _policy_signals(hist)
    budget_left = max(0, budget - len([h for h in hist if h["compile_ok"]]))
    if budget_left == 0 and not entry["ok"]:
        signals.append("ITERATION BUDGET EXHAUSTED. Stop iterating: summarize what remains unresolved and call ask_user with the "
                       "specific decision you need, or finish with the best passing iteration if one exists.")

    status = meta.get("status", "new")
    new_status = "iterating" if status in ("new", "intake_done", "iterating", "running") else status
    session.update_meta(iteration=n, status=new_status, last_ok=entry["ok"])
    res = IterationResult(n, comp, checks, bp, it_dir, time.time() - t0, signals, budget_left)
    (it_dir / "iteration.json").write_text(json.dumps(res.to_dict(), indent=2, default=str))
    (it_dir / "summary.txt").write_text(res.summary_for_model())
    session.commit(f"iteration {n}: {'pass' if res.ok else 'fail'}" + (f" — {label}" if label else ""))
    session.emit("iteration", iteration=n, ok=res.ok, compile_ok=comp.ok, failures=entry["failures"], label=label,
                 sheet=str(bp.sheet_path) if bp else None, sections=str(bp.sections_path) if bp and bp.sections_path else None,
                 duration_s=round(res.duration_s, 1))
    return res


def _has_render_target(scad_path: Path) -> bool:
    try:
        return "render_target" in scad_path.read_text(encoding="utf-8")
    except Exception:
        return False


def _load_history(session: Session) -> list[dict]:
    p = session.dir / "history.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            return []
    return []


def _save_history(session: Session, hist: list[dict]) -> None:
    (session.dir / "history.json").write_text(json.dumps(hist, indent=2, default=str))


def _policy_signals(hist: list[dict]) -> list[str]:
    """Oscillation and repeated-failure detection across iterations."""
    out: list[str] = []
    if len(hist) < 3:
        return out
    # oscillation: a measured dimension crossing its target twice in the last 4 iterations
    recent = hist[-4:]
    dims = set()
    for h in recent:
        dims |= set(h["measured"].keys())
    for d in dims:
        series = [(h["measured"].get(d), h["targets"].get(d)) for h in recent if h["measured"].get(d) is not None and h["targets"].get(d) is not None]
        if len(series) < 3:
            continue
        signs = [1 if m > t else (-1 if m < t else 0) for m, t in series]
        flips = sum(1 for a, b in zip(signs, signs[1:]) if a and b and a != b)
        if flips >= 2:
            out.append(f"{d} is oscillating around its target ({', '.join(f'{m:.2f}' for m, _ in series)}). Freeze the parameter that drives it "
                       f"at the value that measured closest, change only one thing at a time, and if it still fails call ask_user.")
    # same failure set three times in a row -> switch strategy
    last = hist[-3:]
    if all(h["compile_ok"] and not h["ok"] for h in last) and last[0]["failures"] and last[0]["failures"] == last[1]["failures"] == last[2]["failures"]:
        out.append(f"The same checks failed three iterations in a row ({', '.join(last[0]['failures'])}). Switch modeling strategy: "
                   "if you built with free CSG, start from a template (see templates/); if the geometry is a flat outline, use a 2D "
                   "polygon with linear_extrude; simplify until the failing dimension is controlled by a single parameter.")
    if all(not h["compile_ok"] for h in hist[-3:]):
        out.append("Three compile failures in a row. Simplify: comment out the newest feature, get a compiling part, then add features back one at a time.")
    return out
