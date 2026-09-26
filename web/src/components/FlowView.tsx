/** The session flow as a state diagram: stages on the critical path left to right, loops as arcs below, the current stage highlighted. */
export interface FlowGraph {
  graph: string;
  nodes: Array<{ name: string; label: string; kind: string; inputs: string[]; outputs: string[]; human?: string; current?: boolean }>;
  edges: Array<{ from: string; to: string; label: string; guard: string; enabled: boolean }>;
  critical_path: string[];
  stage?: string | null;
}

export default function FlowView({ flow }: { flow: FlowGraph }) {
  const order = flow.critical_path.length ? flow.critical_path : flow.nodes.map((n) => n.name);
  const idx: Record<string, number> = {};
  order.forEach((n, i) => (idx[n] = i));
  const colW = 118;
  const nw = 96;
  const nh = 34;
  const y = 70;
  const width = order.length * colW + 10;
  const height = 150;
  const cx = (n: string) => 5 + idx[n] * colW + colW / 2;
  const loops = flow.edges.filter((e) => idx[e.to] <= idx[e.from]);
  const forwards = flow.edges.filter((e) => idx[e.to] > idx[e.from]);
  return (
    <div className="gv">
      <svg className="gv-svg" viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label="session flow">
        <defs>
          <marker id="fv-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" fill="var(--ink-3)" />
          </marker>
          <marker id="fv-arrow-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" fill="var(--blue)" />
          </marker>
        </defs>
        {forwards.map((e, i) => {
          const skip = idx[e.to] - idx[e.from] > 1;
          const x1 = cx(e.from) + nw / 2;
          const x2 = cx(e.to) - nw / 2;
          const on = e.enabled;
          if (!skip)
            return (
              <line key={i} x1={x1} y1={y} x2={x2} y2={y} stroke={on ? "var(--blue)" : "var(--rule)"} strokeWidth={on ? 2 : 1.2} markerEnd={on ? "url(#fv-arrow-on)" : "url(#fv-arrow)"}>
                <title>{e.label}</title>
              </line>
            );
          const top = y - 34;
          return (
            <path key={i} d={`M${x1},${y - 6} C${x1 + 20},${top} ${x2 - 20},${top} ${x2},${y - 6}`} fill="none" stroke={on ? "var(--blue)" : "var(--rule)"} strokeWidth={on ? 2 : 1} strokeDasharray="4 3" markerEnd={on ? "url(#fv-arrow-on)" : "url(#fv-arrow)"}>
              <title>{e.label}</title>
            </path>
          );
        })}
        {loops.map((e, i) => {
          const self = e.from === e.to;
          const x1 = cx(e.from);
          const x2 = cx(e.to);
          const depth = y + nh / 2 + 18 + (i % 3) * 14;
          const on = e.enabled;
          const d = self
            ? `M${x1 + 14},${y + nh / 2} C${x1 + 34},${depth} ${x1 - 34},${depth} ${x1 - 14},${y + nh / 2}`
            : `M${x1},${y + nh / 2} C${x1},${depth} ${x2},${depth} ${x2},${y + nh / 2}`;
          return (
            <path key={`l${i}`} d={d} fill="none" stroke={on ? "var(--blue)" : "var(--rule)"} strokeWidth={on ? 2 : 1} strokeDasharray={on ? undefined : "3 3"} markerEnd={on ? "url(#fv-arrow-on)" : "url(#fv-arrow)"} opacity={on ? 1 : 0.7}>
              <title>{e.label}</title>
            </path>
          );
        })}
        {flow.nodes.map((n) => {
          const x = cx(n.name) - nw / 2;
          const cur = n.current || n.name === flow.stage;
          return (
            <g key={n.name} className={`gv-node gv-kind-${n.kind} ${cur ? "gv-running gv-crit" : "gv-done"}`} transform={`translate(${x},${y - nh / 2})`}>
              <title>
                {n.label}
                {"\n"}in: {n.inputs.join(", ")}
                {"\n"}out: {n.outputs.join(", ")}
                {n.human ? `\nyou: ${n.human}` : ""}
              </title>
              <rect width={nw} height={nh} rx={n.kind === "human" ? nh / 2 : n.kind === "agent" ? 8 : 3} />
              <text x={nw / 2} y={14} textAnchor="middle" className="gv-label">
                {n.label.length > 15 ? n.label.slice(0, 14) + "…" : n.label}
              </text>
              <text x={nw / 2} y={26} textAnchor="middle" className="gv-sub">
                {n.kind}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
