"""The graph runtime: waves, parallelism, guards, optional failures, human nodes, resume, critical path."""

from __future__ import annotations

import asyncio
import time

import pytest

from kintsugi.graph import Graph, GraphError, Node, run_sync


def _sleep_node(name, inputs, outputs, dt=0.2, fail=False, optional=False, est=None):
    def fn(state):
        time.sleep(dt)
        if fail:
            raise RuntimeError("boom")
        return {o: f"{name}:{o}" for o in outputs}

    return Node(name, fn, tuple(inputs), tuple(outputs), optional=optional, est_s=est if est is not None else dt)


def test_parallel_waves_and_critical_path():
    g = Graph("t", [
        _sleep_node("a", [], ["x"], 0.2),
        _sleep_node("b", ["x"], ["y"], 0.3),
        _sleep_node("c", ["x"], ["z"], 0.3),
        _sleep_node("d", ["y", "z"], ["w"], 0.1),
    ])
    assert g.topological_order() == ["a", "b", "c", "d"]
    assert {(a, b) for a, b, _ in g.edges} == {("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")}
    events = []
    tr = run_sync(g, {}, emit=lambda kind, **d: events.append((kind, d)))
    assert tr.status == "done" and tr.waves == 3
    assert tr.nodes["b"].wave == tr.nodes["c"].wave == 2
    assert tr.wall_s < 0.75 and tr.serial_s >= 0.85  # b and c overlapped
    assert tr.critical_path in (["a", "b", "d"], ["a", "c", "d"]) and 0.55 < tr.critical_s < 0.9
    kinds = [k for k, _ in events]
    assert kinds.count("graph_node") == 8 and kinds[-1] == "graph_run"
    d = tr.to_dict()
    assert d["speedup"] and d["speedup"] > 1.1


def test_cycle_rejected():
    with pytest.raises(GraphError):
        Graph("bad", [_sleep_node("a", ["y"], ["x"], 0), _sleep_node("b", ["x"], ["y"], 0)])


def test_guard_optional_failure_and_partial():
    g = Graph("t", [
        _sleep_node("src", [], ["x"], 0.01),
        Node("skipme", lambda s: {"q": 1}, ("x",), ("q",), when=lambda s: False),
        _sleep_node("flaky", ["x"], ["f"], 0.01, fail=True, optional=True),
        _sleep_node("needs_f", ["f"], ["g"], 0.01),
        _sleep_node("fine", ["x"], ["h"], 0.01),
    ])
    tr = run_sync(g, {})
    assert tr.nodes["skipme"].status == "skipped" and tr.nodes["flaky"].status == "failed" and "boom" in tr.nodes["flaky"].error
    assert tr.nodes["needs_f"].status == "pending" and tr.nodes["fine"].status == "done"
    assert tr.status == "partial"


def test_required_failure_stops():
    g = Graph("t", [_sleep_node("a", [], ["x"], 0.01, fail=True), _sleep_node("b", ["x"], ["y"], 0.01)])
    tr = run_sync(g, {})
    assert tr.status == "failed" and tr.nodes["b"].status == "pending"


def test_human_node_waits_then_resumes():
    asked = []

    def ask(state):
        asked.append(True)
        return {"question": f"measure {state['dim']}"}

    g = Graph("t", [
        Node("prep", lambda s: {"dim": "neck"}, (), ("dim",)),
        Node("ask_user", None, ("dim",), ("answer",), kind="human", ask=ask),
        Node("use", lambda s: {"result": s["answer"] * 2}, ("answer",), ("result",)),
    ])
    st = {}
    tr = run_sync(g, st)
    assert tr.status == "waiting" and tr.waiting_on == "ask_user" and tr.request == {"question": "measure neck"}
    assert tr.nodes["use"].status == "pending" and asked == [True]
    st["answer"] = 21
    tr2 = run_sync(g, st)
    assert tr2.status == "done" and st["result"] == 42 and tr2.nodes["prep"].note == "already in state"


def test_async_and_until():
    async def agent(state):
        await asyncio.sleep(0.01)
        return {"a": 1}

    g = Graph("t", [Node("agent", agent, (), ("a",), kind="agent", blocking=False),
                    Node("b", lambda s: {"b": s["a"] + 1}, ("a",), ("b",)),
                    Node("c", lambda s: {"c": 0}, ("a",), ("c",))])
    tr = run_sync(g, {}, until={"b"})
    assert tr.nodes["b"].status == "done" and tr.nodes["c"].status == "pending" and tr.status == "done"
    assert g.describe()["critical_path"]


def test_after_ordering_dependency():
    order = []

    def mk(name, dt, fail=False):
        def fn(s):
            time.sleep(dt)
            order.append(name)
            if fail:
                raise RuntimeError("x")
            return {name: 1}
        return fn

    g = Graph("t", [Node("a", mk("a", 0.05), (), ("a",)), Node("slow", mk("slow", 0.3, fail=True), ("a",), ("slow",), optional=True),
                    Node("b", mk("b", 0.01), ("a",), ("b",), after=("slow",))])
    tr = run_sync(g, {})
    assert order == ["a", "slow", "b"] and tr.nodes["slow"].status == "failed" and tr.nodes["b"].status == "done" and tr.status == "done"
    assert ("slow", "b", "after") in g.edges
    with pytest.raises(GraphError):
        Graph("bad", [Node("x", lambda s: {}, (), (), after=("nope",))])


def test_event_driven_no_wave_barrier():
    """d (after c) must start while the slow b is still running, so the wall time is max(b, c + d), not b + d."""
    g = Graph("t", [
        _sleep_node("a", [], ["x"], 0.05),
        _sleep_node("b", ["x"], ["y"], 0.4),
        _sleep_node("c", ["x"], ["z"], 0.05),
        _sleep_node("d", ["z"], ["w"], 0.3),
    ])
    tr = run_sync(g, {})
    assert tr.status == "done" and tr.wall_s < 0.62, tr.wall_s
    assert tr.nodes["d"].started < tr.nodes["b"].ended
    assert tr.critical_path == ["a", "b"] or tr.critical_path == ["a", "c", "d"]


def test_session_flow_graph():
    from kintsugi.graph.flow import CRITICAL_PATH, derive_stage, describe, open_transitions

    fresh = {"meta": {"status": "new"}, "has_spec": False}
    assert derive_stage(fresh) == "intake"
    cap = {"meta": {"status": "intake_done"}, "has_spec": True, "has_intake": True, "ready": False}
    assert derive_stage(cap) == "capture"
    assert [t["to"] for t in open_transitions("capture", cap) if t["enabled"]] == ["capture", "spec"]
    ready = {**cap, "ready": True}
    assert derive_stage(ready) == "spec"
    labels = [t["label"] for t in open_transitions("capture", ready) if t["enabled"]]
    assert "fit dimensions ready" in labels and "another round" not in labels
    running = {**ready, "running": True, "meta": {"status": "running", "stage": "review"}}
    assert derive_stage(running) == "design"
    done = {**ready, "meta": {"status": "done"}, "iterations": True, "has_passing_iteration": True}
    assert derive_stage(done) == "review" and any(t["to"] == "export" and t["enabled"] for t in open_transitions("review", done))
    asked = {**ready, "meta": {"status": "waiting_user", "question": {"question": "?", "photos": [{"label": "q1_1", "dims": ["a.b"]}]}}}
    assert any(t["to"] == "capture" and t["enabled"] for t in open_transitions("design", asked))
    d = describe("spec", ready)
    assert d["critical_path"] == CRITICAL_PATH and any(n["current"] for n in d["nodes"]) and all("guard" in e for e in d["edges"])
