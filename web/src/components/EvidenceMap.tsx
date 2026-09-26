import { useMemo } from "react";
import type { EvidenceGraph, EvidenceNode } from "../types";

/** Three-column evidence map: sources (photos, questions, standards, requests) → estimates → dimensions → checks. */
export default function EvidenceMap({ graph, compact }: { graph: EvidenceGraph; compact?: boolean }) {
  const m = useMemo(() => layout(graph), [graph]);
  if (!m.dims.length) return <div className="small dim">No dimensions in the spec yet.</div>;
  const { cols, pos, width, height, edges } = m;
  const w = compact ? 120 : 140;
  const h = 26;
  return (
    <svg className="em-svg" viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label="evidence map">
      {edges.map((e, i) => {
        const a = pos[e.from];
        const b = pos[e.to];
        if (!a || !b) return null;
        const x1 = a.x + w / 2;
        const x2 = b.x - w / 2;
        const dx = Math.max(24, (x2 - x1) / 2);
        const weight = typeof e.weight === "number" ? e.weight : 40;
        const stroke = e.rel === "verifies" ? (e.passed === false ? "var(--fail)" : "var(--pass)") : weight >= 80 ? "var(--pass)" : weight >= 40 ? "var(--blue)" : "var(--warn)";
        return (
          <path
            key={i}
            d={`M${x1},${a.y} C${x1 + dx},${a.y} ${x2 - dx},${b.y} ${x2},${b.y}`}
            fill="none"
            stroke={stroke}
            strokeWidth={e.rel === "supports" ? 1 + Math.min(2.5, weight / 40) : 1.2}
            strokeDasharray={e.rel === "targets" ? "3 3" : undefined}
            opacity={0.85}
          >
            <title>{`${e.from} —${e.rel}→ ${e.to}`}</title>
          </path>
        );
      })}
      {cols.flat().map((n) => {
        const p = pos[n.id];
        return (
          <g key={n.id} className={`em-node em-${n.type} ${nodeState(n)}`} transform={`translate(${p.x - w / 2},${p.y - h / 2})`}>
            <title>{tooltip(n)}</title>
            <rect width={w} height={h} rx={n.type === "dim" ? 3 : 13} />
            <text x={n.type === "dim" ? 8 : w / 2} y={17} textAnchor={n.type === "dim" ? "start" : "middle"} className="em-label">
              {truncate(labelOf(n), compact ? 17 : 20)}
            </text>
            {n.type === "dim" && (
              <circle cx={w - 10} cy={h / 2} r={4} className="em-dot" />
            )}
          </g>
        );
      })}
    </svg>
  );
}

function nodeState(n: EvidenceNode): string {
  if (n.type === "dim") {
    if (n.status === "confirmed") return "ok";
    if (n.status === "estimated") return (n.conf || 0) >= 0.6 ? "mid" : "low";
    return n.bounded ? "bound" : "bad"; // a stated bound is a design constraint, not missing evidence
  }
  if (n.type === "photo") return n.ok ? "ok" : "low";
  if (n.type === "check") return n.passed === false ? "bad" : n.passed ? "ok" : "mid";
  if (n.type === "estimate") return (n.trust || 0) >= 80 ? "ok" : (n.trust || 0) >= 40 ? "mid" : "low";
  return "";
}

function labelOf(n: EvidenceNode): string {
  switch (n.type) {
    case "dim":
      return String(n.label || n.id).replace(/^dim:/, "");
    case "estimate":
      return `${typeof n.value === "number" ? n.value : "?"} mm · ${String(n.source || "").replace("standard:", "std ").replace("rectified_sheet", "sheet").replace("vision_estimate", "vision").replace("user_", "")}`;
    case "photo":
      return `📷 ${String(n.label || "")}`;
    case "question":
      return `? ${String(n.label || "")}`;
    case "standard":
      return `📖 ${String(n.label || "")}`;
    case "shot":
    case "request":
      return `→ ${String(n.label || "")}`;
    case "check":
      return `${n.passed === false ? "✗" : "✓"} check${typeof n.measured === "number" ? ` ${Math.round((n.measured as number) * 100) / 100}` : ""}`;
    default:
      return String(n.label || n.id);
  }
}

function tooltip(n: EvidenceNode): string {
  if (n.type === "dim") return `${n.id.replace(/^dim:/, "")}\nstatus ${n.status} · confidence ${Math.round((n.conf || 0) * 100)}%${typeof n.target === "number" ? ` · ${n.target} mm` : ""}`;
  if (n.type === "estimate") return `${n.value} mm from ${n.source} (conf ${n.conf})`;
  return String(n.label || n.id);
}

function truncate(s: string, k: number): string {
  return s.length > k ? s.slice(0, k - 1) + "…" : s;
}

function layout(g: EvidenceGraph) {
  const sources = g.nodes.filter((n) => ["photo", "question", "standard", "shot", "request"].includes(n.type));
  const ests = g.nodes.filter((n) => n.type === "estimate");
  const dims = g.nodes.filter((n) => n.type === "dim");
  const checks = g.nodes.filter((n) => n.type === "check");
  const cols: EvidenceNode[][] = [sources, ests, dims, checks].filter((c) => c.length > 0);
  // keep the estimate column ordered by the dim it supports so edges stay short
  const order: Record<string, number> = {};
  dims.forEach((d, i) => (order[d.id] = i));
  ests.sort((a, b) => {
    const ea = g.edges.find((e) => e.from === a.id && e.rel === "supports");
    const eb = g.edges.find((e) => e.from === b.id && e.rel === "supports");
    return (order[ea?.to || ""] ?? 99) - (order[eb?.to || ""] ?? 99);
  });
  const colW = 176;
  const rowH = 34;
  const maxRows = Math.max(...cols.map((c) => c.length), 1);
  const height = maxRows * rowH + 12;
  const width = cols.length * colW + 10;
  const pos: Record<string, { x: number; y: number; col: number }> = {};
  cols.forEach((col, ci) => {
    const total = col.length * rowH;
    const y0 = (height - total) / 2 + rowH / 2;
    col.forEach((n, i) => (pos[n.id] = { x: 5 + ci * colW + colW / 2, y: y0 + i * rowH, col: ci }));
  });
  const edges = g.edges
    .filter((e) => pos[e.from] && pos[e.to] && pos[e.from].col < pos[e.to].col)
    .map((e) => {
      const from = g.nodes.find((n) => n.id === e.from);
      return { ...e, passed: from?.type === "check" ? (from.passed as boolean | null | undefined) : undefined };
    });
  // edges from a photo to an estimate span one column; shots/questions/standards target dims directly (dashed)
  return { cols, pos, width, height, edges, dims };
}
