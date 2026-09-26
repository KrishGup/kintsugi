"""A small typed dataflow-graph runtime.

Nodes declare the state keys they need (`inputs`) and the keys they produce (`outputs`); the edges follow from that.
A run is a sequence of *waves*: every node whose inputs are present runs, independent nodes run concurrently
(blocking algorithms in worker threads, agents as coroutines), and the wave repeats until nothing more can run.
`human` nodes never run by themselves — when a human node is the only thing left that could make progress the run
stops in the `waiting` state with the node's request, and a later run with the answer in the state continues from
there. Every run leaves a trace: per-node status and timing, the critical path (longest path by measured or
estimated duration), and the serial-vs-wall time, so the UI can show what ran in parallel and what the bottleneck was.

This is the mechanism behind the iteration pipeline (compile → checks ∥ renders → sheets), the intake pipeline
(grade ∥ standards ∥ vision → measure → evidence → follow-up round → capture (human)), and the export bundle.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Callable

State = dict[str, Any]
Emit = Callable[..., None]

KINDS = ("algorithm", "agent", "human", "io")


@dataclass
class Node:
    name: str
    fn: Callable[[State], Any] | None = None
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    kind: str = "algorithm"
    label: str = ""
    when: Callable[[State], bool] | None = None
    optional: bool = False
    est_s: float = 1.0
    blocking: bool = True
    ask: Callable[[State], dict[str, Any]] | None = None
    after: tuple[str, ...] = ()  # ordering-only dependencies: wait for these nodes to finish (done, failed or skipped)

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"node {self.name}: unknown kind {self.kind}")
        if self.kind != "human" and self.fn is None:
            raise ValueError(f"node {self.name}: fn required")
        self.label = self.label or self.name.replace("_", " ")


@dataclass
class NodeRun:
    name: str
    kind: str
    label: str
    status: str = "pending"  # pending | running | done | failed | skipped | waiting
    started: float | None = None
    ended: float | None = None
    error: str | None = None
    wave: int | None = None
    est_s: float = 1.0
    note: str = ""

    @property
    def duration(self) -> float | None:
        if self.started is None or self.ended is None:
            return None
        return self.ended - self.started

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind, "label": self.label, "status": self.status, "wave": self.wave,
                "duration_s": round(self.duration, 3) if self.duration is not None else None, "est_s": self.est_s,
                "error": self.error, "note": self.note}


@dataclass
class RunTrace:
    graph: str
    nodes: dict[str, NodeRun]
    edges: list[tuple[str, str, str]]
    status: str = "pending"  # done | failed | waiting | partial
    waiting_on: str | None = None
    request: dict[str, Any] | None = None
    critical_path: list[str] = field(default_factory=list)
    critical_s: float = 0.0
    wall_s: float = 0.0
    serial_s: float = 0.0
    waves: int = 0
    started: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"graph": self.graph, "status": self.status, "waiting_on": self.waiting_on, "request": self.request,
                "nodes": [n.to_dict() for n in self.nodes.values()],
                "edges": [{"from": a, "to": b, "key": k} for a, b, k in self.edges],
                "critical_path": self.critical_path, "critical_s": round(self.critical_s, 3),
                "wall_s": round(self.wall_s, 3), "serial_s": round(self.serial_s, 3),
                "speedup": round(self.serial_s / self.wall_s, 2) if self.wall_s > 0 else None, "waves": self.waves,
                "started": self.started}


class GraphError(RuntimeError):
    pass


class Graph:
    """A dataflow DAG. Edges are derived from input/output keys; cycles are rejected."""

    def __init__(self, name: str, nodes: list[Node], *, max_parallel: int = 4):
        self.name = name
        self.nodes: dict[str, Node] = {}
        for n in nodes:
            if n.name in self.nodes:
                raise GraphError(f"duplicate node {n.name}")
            self.nodes[n.name] = n
        self.max_parallel = max_parallel
        self.edges = self._edges()
        self._check_acyclic()

    # ---- structure ---------------------------------------------------------------------------------
    def _edges(self) -> list[tuple[str, str, str]]:
        producers: dict[str, list[str]] = {}
        for n in self.nodes.values():
            for k in n.outputs:
                producers.setdefault(k, []).append(n.name)
        edges = []
        for n in self.nodes.values():
            for k in n.inputs:
                for p in producers.get(k, []):
                    if p != n.name:
                        edges.append((p, n.name, k))
            for p in n.after:
                if p not in self.nodes:
                    raise GraphError(f"node {n.name}: after={p!r} is not a node")
                edges.append((p, n.name, "after"))
        return edges

    def _check_acyclic(self) -> None:
        order = self.topological_order()
        if len(order) != len(self.nodes):
            raise GraphError(f"graph {self.name} has a cycle")

    def predecessors(self, name: str) -> list[str]:
        return sorted({a for a, b, _ in self.edges if b == name})

    def successors(self, name: str) -> list[str]:
        return sorted({b for a, b, _ in self.edges if a == name})

    def topological_order(self) -> list[str]:
        preds = {n: set(self.predecessors(n)) for n in self.nodes}
        indeg = {n: len(ps) for n, ps in preds.items()}
        ready = sorted(n for n, d in indeg.items() if d == 0)
        out: list[str] = []
        while ready:
            n = ready.pop(0)
            out.append(n)
            for s in self.successors(n):
                indeg[s] -= 1
                if indeg[s] == 0:
                    ready.append(s)
                    ready.sort()
        return out

    def critical_path(self, durations: dict[str, float]) -> tuple[list[str], float]:
        """Longest path through the DAG by node duration (measured where available, else the node's estimate)."""
        best: dict[str, tuple[float, str | None]] = {}
        for n in self.topological_order():
            d = durations.get(n, self.nodes[n].est_s)
            preds = self.predecessors(n)
            if preds:
                p = max(preds, key=lambda x: best[x][0])
                best[n] = (best[p][0] + d, p)
            else:
                best[n] = (d, None)
        if not best:
            return [], 0.0
        end = max(best, key=lambda x: best[x][0])
        path = []
        cur: str | None = end
        while cur is not None:
            path.append(cur)
            cur = best[cur][1]
        return list(reversed(path)), best[end][0]

    def describe(self) -> dict[str, Any]:
        cp, total = self.critical_path({})
        return {"graph": self.name, "nodes": [{"name": n.name, "kind": n.kind, "label": n.label, "inputs": list(n.inputs),
                                              "outputs": list(n.outputs), "est_s": n.est_s, "optional": n.optional} for n in self.nodes.values()],
                "edges": [{"from": a, "to": b, "key": k} for a, b, k in self.edges], "critical_path": cp, "critical_s": total}

    # ---- execution ---------------------------------------------------------------------------------
    async def run(self, state: State, *, emit: Emit | None = None, until: set[str] | None = None) -> RunTrace:
        """Run every node whose inputs can be satisfied. `until` limits the run to those nodes and their ancestors.

        Scheduling is event-driven: a node starts the moment its inputs exist and its `after` nodes have finished,
        without waiting for unrelated nodes (no wave barriers). `wave` in the trace is the start generation, for display.
        """
        wanted = set(self.nodes) if until is None else self._ancestors(until) | set(until)
        runs = {n.name: NodeRun(n.name, n.kind, n.label, est_s=n.est_s) for n in self.nodes.values()}
        trace = RunTrace(self.name, runs, list(self.edges), started=time.time())
        for n in self.nodes.values():  # a resumed run: outputs already present count as done
            if n.outputs and all(k in state for k in n.outputs):
                runs[n.name].status = "done"
                runs[n.name].note = "already in state"
        sem = asyncio.Semaphore(self.max_parallel)
        finished = ("done", "failed", "skipped")
        generation = 0
        failed_required = False
        t_start = time.time()
        running: dict[asyncio.Task, Node] = {}
        while True:
            pending = [n for n in self.nodes.values() if n.name in wanted and runs[n.name].status == "pending"]
            ready = [n for n in pending if all(k in state for k in n.inputs) and all(runs[p].status in finished for p in n.after)]
            runnable = []
            skipped_now = 0
            for n in ready:
                if n.when is not None and not n.when(state):
                    runs[n.name].status = "skipped"
                    runs[n.name].wave = generation
                    skipped_now += 1
                    if emit:
                        emit("graph_node", graph=self.name, node=n.name, status="skipped", wave=generation)
                else:
                    runnable.append(n)
            if skipped_now and not runnable and not running:
                continue
            machines = [n for n in runnable if n.kind != "human"]
            humans = [n for n in runnable if n.kind == "human"]
            if machines:
                generation += 1
                for n in machines:
                    task = asyncio.create_task(self._run_node(n, state, runs, generation, sem, emit))
                    running[task] = n
            if not running:
                if humans and not failed_required:
                    h = humans[0]
                    runs[h.name].status = "waiting"
                    runs[h.name].wave = generation
                    trace.status = "waiting"
                    trace.waiting_on = h.name
                    trace.request = h.ask(state) if h.ask else {}
                    if emit:
                        emit("graph_node", graph=self.name, node=h.name, status="waiting", wave=generation)
                break
            done_tasks, _ = await asyncio.wait(set(running), return_when=asyncio.FIRST_COMPLETED)
            for t in done_tasks:
                n = running.pop(t)
                if runs[n.name].status == "failed" and not n.optional:
                    failed_required = True
            if failed_required and not running:
                break
            if failed_required:
                continue  # let the nodes already running finish, start nothing new
        if running:
            await asyncio.gather(*running, return_exceptions=True)
        trace.waves = generation
        trace.wall_s = time.time() - t_start
        durations = {k: (r.duration or 0.0) for k, r in runs.items() if r.status == "done" and r.duration is not None}
        trace.serial_s = sum(durations.values())
        for k, r in runs.items():
            if r.status == "skipped":
                durations[k] = 0.0
        trace.critical_path, trace.critical_s = self.critical_path(durations)
        if failed_required:
            trace.status = "failed"
        elif trace.status != "waiting":
            left = [n for n in self.nodes.values() if n.name in wanted and runs[n.name].status == "pending"]
            trace.status = "partial" if left else "done"
        if emit:
            emit("graph_run", graph=self.name, status=trace.status, wall_s=round(trace.wall_s, 2), serial_s=round(trace.serial_s, 2),
                 critical_path=trace.critical_path, waiting_on=trace.waiting_on)
        return trace

    async def _run_node(self, n: Node, state: State, runs: dict[str, NodeRun], wave: int, sem: asyncio.Semaphore, emit: Emit | None) -> None:
        r = runs[n.name]
        async with sem:
            r.status = "running"
            r.wave = wave
            r.started = time.time()
            if emit:
                emit("graph_node", graph=self.name, node=n.name, status="running", wave=wave)
            try:
                assert n.fn is not None
                if inspect.iscoroutinefunction(n.fn):
                    out = await n.fn(state)
                elif n.blocking:
                    out = await asyncio.to_thread(n.fn, state)
                else:
                    out = n.fn(state)
                if inspect.isawaitable(out):
                    out = await out
                if out:
                    if not isinstance(out, dict):
                        raise GraphError(f"node {n.name} must return a dict of outputs")
                    state.update(out)
                    missing = [k for k in n.outputs if k not in state]
                    if missing:
                        r.note = f"did not produce {', '.join(missing)}"
                r.status = "done"
            except Exception as e:  # noqa: BLE001 - node failures are recorded, not raised
                r.status = "failed"
                r.error = f"{type(e).__name__}: {e}"[:400]
            r.ended = time.time()
            if emit:
                emit("graph_node", graph=self.name, node=n.name, status=r.status, wave=wave, duration_s=round(r.duration or 0.0, 3), error=r.error)

    def _ancestors(self, names: set[str]) -> set[str]:
        out: set[str] = set()
        stack = list(names)
        while stack:
            n = stack.pop()
            for p in self.predecessors(n):
                if p not in out:
                    out.add(p)
                    stack.append(p)
        return out


def run_sync(graph: Graph, state: State, **kw) -> RunTrace:
    """Run a graph from synchronous code (a new event loop when none is running)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(graph.run(state, **kw))
    # called from inside a running loop (e.g. an executor thread of the server): use a private loop in this thread
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(graph.run(state, **kw))
    finally:
        loop.close()
