import { useEffect, useMemo, useState } from "react";
import { kin } from "../api";
import FlowView, { type FlowGraph } from "../components/FlowView";
import GraphView from "../components/GraphView";
import { useSession } from "../pages/session-context";
import type { GraphShape, GraphTrace } from "../types";
import { Pill } from "../ui";

/** The graph runs behind the session: the live/last iteration pipeline, the intake graph, the export graph. */
export default function PipelineTab() {
  const s = useSession();
  const d = s.detail!;
  const [data, setData] = useState<{ intake?: GraphTrace; iteration?: GraphTrace; export?: GraphTrace; shapes: Record<string, GraphShape>; flow?: FlowGraph } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const iterN = d.meta.iteration ?? 0;
  const exportedAt = d.meta.exported_at ?? 0;

  useEffect(() => {
    let alive = true;
    kin
      .graphs(s.sid)
      .then((g) => alive && setData(g))
      .catch((e) => alive && setErr((e as Error).message));
    return () => {
      alive = false;
    };
  }, [s.sid, iterN, exportedAt, d.intake?.rounds?.length, d.stage, d.meta.status]);

  // a live view of the iteration graph while it runs: overlay graph_node events on the static shape
  const live = useMemo(() => {
    if (!data?.shapes?.iteration) return null;
    let startIdx = -1;
    for (let i = s.events.length - 1; i >= 0; i--) {
      const ev = s.events[i];
      if (ev.kind === "graph_run" && ev.graph === "iteration") return null; // finished: the fetched trace is authoritative
      if (ev.kind === "graph_node" && ev.graph === "iteration") startIdx = i;
      if (ev.kind === "iteration") break;
    }
    if (startIdx < 0) return null;
    const shape = data.shapes.iteration;
    const nodes = shape.nodes.map((n) => ({ name: n.name, kind: n.kind, label: n.label, status: "pending", wave: null as number | null, duration_s: null as number | null, est_s: n.est_s }));
    for (let i = startIdx; i < s.events.length; i++) {
      const ev = s.events[i];
      if (ev.kind !== "graph_node" || ev.graph !== "iteration") continue;
      const n = nodes.find((x) => x.name === ev.node);
      if (!n) continue;
      n.status = String(ev.status);
      n.wave = typeof ev.wave === "number" ? ev.wave : n.wave;
      if (typeof ev.duration_s === "number") n.duration_s = ev.duration_s;
    }
    const trace: GraphTrace = { graph: "iteration", status: "running", nodes, edges: shape.edges, critical_path: shape.critical_path, critical_s: shape.critical_s, wall_s: 0, serial_s: 0 };
    return trace;
  }, [s.events, data]);

  if (err) return <div className="banner banner-fail">{err}</div>;
  if (!data) return <div className="small dim">Loading graph traces…</div>;
  const it = live || data.iteration;
  return (
    <div className="stack">
      <div className="small dim">
        Every stage of Kintsugi is a typed dataflow graph: nodes declare their inputs and outputs, independent nodes run in parallel, people are
        nodes too. Rounded nodes are model calls, pills are you; the blue path is the critical path.
      </div>
      {data.flow && (
        <section>
          <div className="row-wrap mb">
            <span className="label">Session flow</span>
            <Pill tone="blue">{String(d.stage)}</Pill>
            <span className="small dim">open moves: {(d.flow?.transitions || []).filter((t) => t.enabled).map((t) => t.label).join(" · ") || "—"}</span>
          </div>
          <FlowView flow={{ ...data.flow, stage: d.stage }} />
        </section>
      )}
      <section>
        <div className="row-wrap mb">
          <span className="label">Iteration pipeline</span>
          {it ? <Pill tone={it.status === "done" ? "pass" : it.status === "failed" ? "fail" : "blue"} dot={it.status === "running"}>{live ? "running" : `iteration ${data.iteration?.iteration ?? iterN} · ${it.status}`}</Pill> : <Pill tone="neutral">not run yet</Pill>}
        </div>
        {it ? <GraphView trace={live ? { ...it, wall_s: 0, serial_s: 0 } : it} compact /> : <GraphView shape={data.shapes.iteration} compact />}
      </section>
      {data.intake && (
        <section>
          <div className="row-wrap mb">
            <span className="label">Intake &amp; capture</span>
            <Pill tone={data.intake.status === "waiting" ? "warn" : data.intake.status === "done" ? "pass" : "neutral"}>{data.intake.status === "waiting" ? `waiting: ${data.intake.waiting_on}` : data.intake.status}</Pill>
          </div>
          <GraphView trace={data.intake} compact />
        </section>
      )}
      {data.export && (
        <section>
          <div className="row-wrap mb">
            <span className="label">Export bundle</span>
            <Pill tone={data.export.status === "done" ? "pass" : "warn"}>{data.export.status}</Pill>
          </div>
          <GraphView trace={data.export} compact />
        </section>
      )}
      {!data.export && (
        <section>
          <div className="row-wrap mb">
            <span className="label">Export bundle</span>
            <Pill tone="neutral">shape</Pill>
          </div>
          <GraphView shape={data.shapes.export} compact />
        </section>
      )}
    </div>
  );
}
