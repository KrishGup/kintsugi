"""The session flow as an explicit state graph: stages, guarded transitions, and what each stage waits on.

Nodes are stages; each has the inputs it consumes (photos, answers, a confirmed spec, a finished run…) and the outputs it
produces. Transitions carry a guard evaluated on the session's state, so the UI can show which moves are open right now
and the API can refuse the rest. The critical path is the straight line intake → capture → spec → design → review →
print; the loops (another capture round, a designer question, a coupon result that retunes the clearance) are the
other paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

STAGES = ["intake", "capture", "spec", "design", "review", "export"]


@dataclass
class Transition:
    src: str
    dst: str
    label: str
    guard: str  # a named predicate over the session state (see `guards`)


FLOW_NODES: dict[str, dict[str, Any]] = {
    "intake": {"label": "What broke", "kind": "agent", "inputs": ["photos", "sentence"], "outputs": ["draft spec", "capture plan"], "human": "photos + one sentence"},
    "capture": {"label": "Photos & answers", "kind": "human", "inputs": ["capture round"], "outputs": ["measurements", "readings"], "human": "take the requested photos, read the ruler"},
    "spec": {"label": "Confirm the fit", "kind": "human", "inputs": ["evidence graph"], "outputs": ["confirmed spec"], "human": "confirm or accept the fit dimensions"},
    "design": {"label": "Design & verify", "kind": "agent", "inputs": ["confirmed spec"], "outputs": ["part.scad", "checks", "blueprint"], "human": "answer the designer's questions"},
    "review": {"label": "Review", "kind": "human", "inputs": ["checks", "critic verdict"], "outputs": ["approval", "change request"], "human": "look at the drawings, ask for changes"},
    "export": {"label": "Print", "kind": "algorithm", "inputs": ["approved iteration"], "outputs": ["STL / 3MF / bundle", "coupon"], "human": "print the coupon, then the part"},
}

TRANSITIONS: list[Transition] = [
    Transition("intake", "capture", "intake done", "has_intake"),
    Transition("intake", "spec", "spec typed by hand", "has_spec"),
    Transition("capture", "capture", "another round", "not_ready"),
    Transition("capture", "spec", "fit dimensions ready", "ready"),
    Transition("capture", "spec", "design anyway", "always"),
    Transition("spec", "design", "run the designer", "has_spec"),
    Transition("spec", "capture", "more photos", "has_intake"),
    Transition("design", "review", "designer finished", "run_done"),
    Transition("design", "capture", "designer asked for a photo", "question_has_photos"),
    Transition("design", "design", "answer / revise", "waiting_user"),
    Transition("review", "export", "looks right", "has_passing_iteration"),
    Transition("review", "design", "ask for a change", "always"),
    Transition("review", "capture", "fit is off — measure again", "has_intake"),
    Transition("export", "design", "coupon result retunes the clearance", "always"),
    Transition("export", "review", "back to review", "always"),
]

CRITICAL_PATH = ["intake", "capture", "spec", "design", "review", "export"]


def guards(state: dict[str, Any]) -> dict[str, bool]:
    meta = state.get("meta") or {}
    q = meta.get("question") or {}
    return {
        "always": True,
        "has_intake": bool(state.get("has_intake")),
        "has_spec": bool(state.get("has_spec")),
        "ready": bool(state.get("ready")),
        "not_ready": not bool(state.get("ready")),
        "run_done": meta.get("status") == "done",
        "waiting_user": meta.get("status") == "waiting_user",
        "question_has_photos": bool(q.get("photos")),
        "has_passing_iteration": bool(state.get("has_passing_iteration")),
    }


def derive_stage(state: dict[str, Any]) -> str:
    """The stage a session is in, from its state (an explicit `meta.stage` wins when it is consistent)."""
    meta = state.get("meta") or {}
    explicit = meta.get("stage")
    if state.get("running"):
        return "design"
    if explicit in STAGES:
        return explicit
    if not state.get("has_spec"):
        return "intake"
    if meta.get("exported_iteration"):
        return "export"
    if meta.get("status") == "done":
        return "review"
    if state.get("iterations"):
        return "design"
    if state.get("has_intake") and not state.get("ready"):
        return "capture"
    return "spec"


def open_transitions(stage: str, state: dict[str, Any]) -> list[dict[str, Any]]:
    g = guards(state)
    out = []
    for t in TRANSITIONS:
        if t.src != stage:
            continue
        out.append({"to": t.dst, "label": t.label, "enabled": bool(g.get(t.guard)), "guard": t.guard})
    return out


def describe(stage: str | None = None, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """The flow graph for the UI: nodes with their inputs/outputs, edges with guards, the current stage and open moves."""
    st = state or {}
    g = guards(st)
    return {
        "graph": "session",
        "nodes": [{"name": k, **v, "current": k == stage} for k, v in FLOW_NODES.items()],
        "edges": [{"from": t.src, "to": t.dst, "label": t.label, "guard": t.guard, "enabled": bool(g.get(t.guard)) and (stage is None or t.src == stage)}
                  for t in TRANSITIONS],
        "critical_path": CRITICAL_PATH,
        "stage": stage,
    }
