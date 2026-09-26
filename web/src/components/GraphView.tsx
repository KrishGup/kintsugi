import { useMemo } from "react";
import type { GraphNodeRun, GraphShape, GraphTrace } from "../types";

/** Layered DAG drawing of a graph run (or its static shape): nodes by depth, edges as curves, critical path emphasised. */
export default function GraphView({ trace, shape, title, compact, direction }: { trace?: GraphTrace | null; shape?: GraphShape | null; title?: string; compact?: boolean; direction?: "lr" | "tb" | "auto" }) {
  const model = useMemo(() => layout(trace, shape, direction || "auto"), [trace, shape, direction]);
  if (!model) return null;
  const { nodes, edges, width, height, critical, tb } = model;
  const nw = compact ? 118 : 138;
  const nh = compact ? 34 : 40;
  return (
    <div className="gv">
      {title && <div className="gv-title">{title}</div>}
      <svg className="gv-svg" viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label={title || "pipeline graph"}>
        <defs>
          <marker id="gv-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" fill="var(--rule)" />
          </marker>
          <marker id="gv-arrow-crit" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" fill="var(--blue)" />
          </marker>
        </defs>
        {edges.map((e, i) => {
          const a = nodes.find((n) => n.name === e.from)!;
          const b = nodes.find((n) => n.name === e.to)!;
          const crit = critical.has(`${e.from}>${e.to}`);
          let d: string;
          if (tb) {
            const x1 = a.x;
            const y1 = a.y + nh / 2;
            const x2 = b.x;
            const y2 = b.y - nh / 2;
            const dy = Math.max(16, (y2 - y1) / 2);
            d = `M${x1},${y1} C${x1},${y1 + dy} ${x2},${y2 - dy} ${x2},${y2}`;
          } else {
            const x1 = a.x + nw / 2;
            const y1 = a.y;
            const x2 = b.x - nw / 2;
            const y2 = b.y;
            const dx = Math.max(30, (x2 - x1) / 2);
            d = `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`;
          }
          return (
            <path
              key={i}
              d={d}
              fill="none"
              stroke={crit ? "var(--blue)" : "var(--rule)"}
              strokeWidth={crit ? 2.2 : 1.2}
              strokeDasharray={e.key === "after" ? "4 3" : undefined}
              markerEnd={crit ? "url(#gv-arrow-crit)" : "url(#gv-arrow)"}
              opacity={crit ? 1 : 0.9}
            >
              <title>{e.key === "after" ? `${e.to} waits for ${e.from}` : `${e.from} → ${e.to}: ${e.key}`}</title>
            </path>
          );
        })}
        {nodes.map((n) => {
          const st = n.run?.status || "pending";
          const cls = `gv-node gv-${st} gv-kind-${n.kind}${critical.has(n.name) ? " gv-crit" : ""}`;
          const dur = n.run?.duration_s;
          return (
            <g key={n.name} className={cls} transform={`translate(${n.x - nw / 2},${n.y - nh / 2})`}>
              <title>
                {n.label} — {st}
                {dur != null ? ` · ${dur.toFixed(2)} s` : ` · est ${n.est_s}s`}
                {n.run?.error ? `\n${n.run.error}` : ""}
              </title>
              <rect width={nw} height={nh} rx={n.kind === "human" ? nh / 2 : n.kind === "agent" ? 8 : 3} />
              <text x={nw / 2} y={compact ? 14 : 16} textAnchor="middle" className="gv-label">
                {truncate(n.label, compact ? 17 : 20)}
              </text>
              <text x={nw / 2} y={compact ? 26 : 30} textAnchor="middle" className="gv-sub">
                {st === "running" ? "running…" : dur != null ? `${dur.toFixed(dur < 10 ? 2 : 1)} s` : st === "waiting" ? "waiting for you" : st === "skipped" ? "skipped" : st === "failed" ? "failed" : n.kind}
              </text>
            </g>
          );
        })}
      </svg>
      {trace && (
        <div className="gv-foot small dim">
          <span>
            <b className="num">{trace.wall_s.toFixed(1)} s</b> wall · <span className="num">{trace.serial_s.toFixed(1)} s</span> of work
            {trace.speedup && trace.speedup > 1.05 ? (
              <>
                {" "}
                · <b className="num">{trace.speedup.toFixed(1)}×</b> parallel
              </>
            ) : null}
          </span>
          <span className="grow" />
          <span>
            critical path: <span className="mono">{trace.critical_path.join(" → ")}</span>
          </span>
        </div>
      )}
    </div>
  );
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

interface LNode {
  name: string;
  label: string;
  kind: string;
  est_s: number;
  x: number;
  y: number;
  run?: GraphNodeRun;
}

function layout(trace?: GraphTrace | null, shape?: GraphShape | null, direction: "lr" | "tb" | "auto" = "auto") {
  const names: string[] = [];
  const meta: Record<string, { label: string; kind: string; est_s: number }> = {};
  const edges: Array<{ from: string; to: string; key: string }> = [];
  if (trace) {
    for (const n of trace.nodes) {
      names.push(n.name);
      meta[n.name] = { label: n.label, kind: n.kind, est_s: n.est_s };
    }
    edges.push(...trace.edges);
  } else if (shape) {
    for (const n of shape.nodes) {
      names.push(n.name);
      meta[n.name] = { label: n.label, kind: n.kind, est_s: n.est_s };
    }
    edges.push(...shape.edges);
  } else return null;
  if (!names.length) return null;
  // depth = longest path from a source (layers)
  const preds: Record<string, string[]> = {};
  for (const n of names) preds[n] = [];
  for (const e of edges) if (preds[e.to] && names.includes(e.from)) preds[e.to].push(e.from);
  const depth: Record<string, number> = {};
  const visit = (n: string, seen: Set<string>): number => {
    if (depth[n] !== undefined) return depth[n];
    if (seen.has(n)) return 0;
    seen.add(n);
    const d = preds[n].length ? Math.max(...preds[n].map((p) => visit(p, seen))) + 1 : 0;
    depth[n] = d;
    return d;
  };
  for (const n of names) visit(n, new Set());
  const layers: Record<number, string[]> = {};
  for (const n of names) (layers[depth[n]] ||= []).push(n);
  const nLayers = Math.max(...Object.values(depth)) + 1;
  const maxRows = Math.max(...Object.values(layers).map((l) => l.length));
  // long chains with little parallelism read better top-to-bottom in a narrow pane
  const tb = direction === "tb" || (direction === "auto" && nLayers >= 6 && maxRows <= 3);
  const nodes: LNode[] = [];
  let width: number;
  let height: number;
  if (tb) {
    const colW = 150;
    const rowH = 58;
    width = Math.max(1, maxRows) * colW + 20;
    height = nLayers * rowH + 12;
    for (let d = 0; d < nLayers; d++) {
      const row = layers[d] || [];
      const total = row.length * colW;
      const x0 = (width - total) / 2 + colW / 2;
      row.forEach((n, i) => nodes.push({ name: n, ...meta[n], x: x0 + i * colW, y: 6 + d * rowH + rowH / 2, run: trace?.nodes.find((r) => r.name === n) }));
    }
  } else {
    const colW = 170;
    const rowH = 54;
    height = Math.max(1, maxRows) * rowH + 20;
    width = nLayers * colW + 20;
    for (let d = 0; d < nLayers; d++) {
      const col = layers[d] || [];
      const total = col.length * rowH;
      const y0 = (height - total) / 2 + rowH / 2;
      col.forEach((n, i) => nodes.push({ name: n, ...meta[n], x: 10 + d * colW + 80, y: y0 + i * rowH, run: trace?.nodes.find((r) => r.name === n) }));
    }
  }
  const cp = trace?.critical_path || shape?.critical_path || [];
  const critical = new Set<string>(cp);
  for (let i = 0; i + 1 < cp.length; i++) critical.add(`${cp[i]}>${cp[i + 1]}`);
  return { nodes, edges, width, height, critical, tb };
}
