import { useEffect, useMemo, useState } from "react";
import type { KinEvent } from "./types";

export interface RunProgress {
  /** t (epoch seconds) of the last run_start, or null */
  startedAt: number | null;
  /** seconds since run_start while running (ticks once a second) */
  elapsed: number;
  budget: number | null;
  model: string | null;
  /** iterations recorded since run_start */
  iterations: number;
  /** last model step number since run_start */
  step: number;
  /** last tool call since run_start */
  tool: { name: string; arg: string } | null;
  /** last designer text since run_start (first line) */
  note: string | null;
  /** failures of the last iteration since run_start */
  failures: string[];
  lastIterOk: boolean | null;
  /** "critic" while the critic is reviewing, "revising" after a revise verdict */
  phase: "designing" | "critic" | "revising" | "idle";
  costUsd: number | null;
}

function fmtTool(ev: KinEvent): { name: string; arg: string } {
  const input = (ev.input || {}) as Record<string, unknown>;
  const name = String(ev.tool || "").replace(/^mcp__kin__/, "").replace(/^mcp__/, "");
  const arg = String(input.label || input.name || input.path || input.file_path || input.command || input.question || "");
  return { name, arg: arg.length > 60 ? arg.slice(0, 57) + "…" : arg };
}

/** Derives live run progress from the event log; `running` keeps the elapsed clock ticking. */
export function useRunProgress(events: KinEvent[], running: boolean): RunProgress {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(t);
  }, [running]);

  const base = useMemo(() => {
    let start = -1;
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].kind === "run_start") {
        start = i;
        break;
      }
    }
    const p: Omit<RunProgress, "elapsed"> = {
      startedAt: null,
      budget: null,
      model: null,
      iterations: 0,
      step: 0,
      tool: null,
      note: null,
      failures: [],
      lastIterOk: null,
      phase: "idle",
      costUsd: null,
    };
    if (start < 0) return p;
    const rs = events[start];
    p.startedAt = rs.t;
    p.budget = typeof rs.budget === "number" ? rs.budget : null;
    p.model = rs.model ? String(rs.model) : null;
    p.phase = "designing";
    for (let i = start + 1; i < events.length; i++) {
      const ev = events[i];
      switch (ev.kind) {
        case "iteration":
          p.iterations += 1;
          p.failures = (ev.failures as string[]) || [];
          p.lastIterOk = !!ev.ok;
          break;
        case "step":
          p.step = Number(ev.n) || p.step;
          break;
        case "tool_use":
          p.tool = fmtTool(ev);
          break;
        case "assistant":
          p.note = String(ev.text || "").split(/\r?\n/)[0].slice(0, 160) || p.note;
          break;
        case "critic_start":
          p.phase = "critic";
          break;
        case "critic":
          p.phase = String(ev.verdict) === "pass" ? "designing" : "revising";
          break;
        case "critic_followup":
          p.phase = "revising";
          break;
        case "usage":
          p.costUsd = typeof ev.cost_usd === "number" ? ev.cost_usd : p.costUsd;
          break;
        case "run_end":
          p.phase = "idle";
          p.costUsd = typeof ev.cost_usd === "number" ? ev.cost_usd : p.costUsd;
          break;
        default:
          break;
      }
    }
    return p;
  }, [events]);

  const elapsed = base.startedAt ? Math.max(0, (running ? now : lastEndT(events, base.startedAt)) - base.startedAt) : 0;
  return { ...base, elapsed };
}

function lastEndT(events: KinEvent[], startedAt: number): number {
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].kind === "run_end" && events[i].t >= startedAt) return events[i].t;
  }
  return events.length ? events[events.length - 1].t : startedAt;
}

export function fmtElapsed(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return m ? `${m}:${String(sec).padStart(2, "0")}` : `${sec}s`;
}
