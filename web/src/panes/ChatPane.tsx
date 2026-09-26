import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Gear } from "../icons";
import { fileUrl } from "../api";
import { useSession } from "../pages/session-context";
import type { Discrepancy, KinEvent } from "../types";
import { Markdown, Pill, Spinner, fmtNum, severityTone, verdictTone } from "../ui";

function clock(t: number): string {
  const d = new Date(t * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function toolName(t: string): string {
  return t.replace(/^mcp__kin__/, "kin.").replace(/^mcp__/, "");
}

export default function ChatPane({ header }: { header?: ReactNode }) {
  const s = useSession();
  const d = s.detail!;
  const body = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const [showNew, setShowNew] = useState(false);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);

  // index of the last question event and whether it was answered
  const lastQuestionId = useMemo(() => {
    let q: number | null = null;
    for (const ev of s.events) {
      if (ev.kind === "question") q = ev.id;
      if (ev.kind === "answer" || ev.kind === "run_start") q = null;
    }
    return q;
  }, [s.events]);
  const waiting = d.meta.status === "waiting_user" && !s.running;
  const activeQuestion = waiting ? lastQuestionId : null;

  const onScroll = () => {
    const el = body.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    stick.current = atBottom;
    if (atBottom) setShowNew(false);
  };

  const scrollToEnd = (smooth = false) => {
    const el = body.current;
    if (!el) return;
    if (smooth && "scrollTo" in el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    else el.scrollTop = el.scrollHeight;
  };

  useEffect(() => {
    if (stick.current) scrollToEnd();
    else setShowNew(true);
  }, [s.events.length, s.running]);

  useEffect(() => {
    scrollToEnd();
  }, []);

  const send = async (answer?: string) => {
    const msg = (answer ?? text).trim();
    if (!msg) return;
    setSending(true);
    try {
      const ok = await s.startRun(waiting ? { answer: msg } : { message: msg });
      if (ok) setText("");
    } finally {
      setSending(false);
    }
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const disabled = s.running || sending;

  return (
    <div className="pane" style={{ position: "relative" }}>
      <div className="pane-head" style={header ? { padding: "0 4px" } : undefined}>
        {header || <h2>Chat &amp; timeline</h2>}
        <span className="grow" />
        {!header && <span className="small muted num">{s.events.length} events</span>}
      </div>
      <div className="pane-body pane-body-flush" ref={body} onScroll={onScroll}>
        <div className="timeline">
          {s.events.length === 0 && (
            <div className="empty" style={{ minHeight: 160 }}>
              <div className="empty-title">Nothing has happened yet</div>
              <div className="empty-body">
                Press <b>Run designer</b> to let the agent write and verify the part, or ask for a change below. Every step lands here: designer
                notes, iterations with their checks, the critic's review and questions for you.
              </div>
            </div>
          )}
          {s.events.map((ev) => (
            <EventCard key={ev.id} ev={ev} active={ev.id === activeQuestion} onAnswer={(a) => send(a)} />
          ))}
          {s.running && (
            <div className="card-sys">
              <Spinner size={11} label="designer working…" />
            </div>
          )}
          <div ref={endRef} className="timeline-end" />
        </div>
      </div>
      {showNew && (
        <button
          className="btn btn-sm btn-primary scroll-pill"
          onClick={() => {
            stick.current = true;
            scrollToEnd(true);
            setShowNew(false);
          }}
        >
          ↓ New events
        </button>
      )}
      <div className="pane-foot">
        <div className="chat-input">
          <textarea
            className="textarea grow"
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKey}
            placeholder={s.running ? "Designer is running…" : waiting ? "Answer the designer…" : "Ask for a change…"}
            disabled={s.running}
            aria-label={waiting ? "Answer" : "Ask for a change"}
          />
          <button className="btn btn-primary" onClick={() => send()} disabled={disabled || !text.trim()}>
            {sending ? <Spinner size={11} /> : waiting ? "Answer" : "Send"}
          </button>
        </div>
        {text.includes("\n") || text.length > 60 ? <div className="chat-hint">Enter sends · Shift+Enter for a new line</div> : null}
      </div>
    </div>
  );
}

function EventCard({ ev, active, onAnswer }: { ev: KinEvent; active: boolean; onAnswer: (a: string) => void }) {
  const s = useSession();
  const t = clock(ev.t);
  switch (ev.kind) {
    case "run_start":
      return (
        <div className="card-sys">
          <span>
            run started · {String(ev.model || "")} · budget {String(ev.budget ?? "")} · {t}
          </span>
        </div>
      );
    case "assistant":
      return (
        <div className="card card-assistant">
          <div className="card-head">
            <span>Designer</span>
            <span className="t">{t}</span>
          </div>
          <Markdown text={String(ev.text || "")} />
        </div>
      );
    case "tool_use": {
      const input = (ev.input || {}) as Record<string, string>;
      const arg = input.label || input.name || input.file_path || input.command || input.question || input.pattern || "";
      return (
        <div className="card-tool hover-anchor">
          <Gear size={11} />
          <span className="tool-name">{toolName(String(ev.tool || ""))}</span>
          {arg && <span className="tool-arg">{arg}</span>}
          {Object.keys(input).length > 0 && (
            <span className="hover-card below tool-card" role="tooltip">
              {Object.entries(input)
                .slice(0, 8)
                .map(([k, v]) => (
                  <span key={k} className="mono">
                    {k}: {String(v).slice(0, 160)}
                  </span>
                ))}
            </span>
          )}
        </div>
      );
    }
    case "iteration": {
      const ok = !!ev.ok;
      const compileOk = ev.compile_ok !== false;
      const failures = (ev.failures as string[]) || [];
      const n = Number(ev.iteration);
      return (
        <div className={`card card-iter ${ok ? "pass" : "fail"}`}>
          <div className="card-head">
            <span>Iteration {n}</span>
            <Pill tone={ok ? "pass" : "fail"}>{ok ? "pass" : compileOk ? "fail" : "compile error"}</Pill>
            <span className="t">{t}</span>
          </div>
          {ev.label ? <div className="card-iter-label">{String(ev.label)}</div> : null}
          {failures.length > 0 && (
            <div className="fail-ids">
              {failures.map((f) => (
                <Pill key={f} tone="fail">
                  {f}
                </Pill>
              ))}
            </div>
          )}
          <div className="row mt" style={{ marginTop: 6 }}>
            <span className="small muted num">{ev.duration_s !== undefined ? `${fmtNum(ev.duration_s, 1)} s` : ""}</span>
            <span className="grow" />
            <button
              className="btn btn-ghost btn-xs"
              onClick={() => s.setSelected(n === s.latestIter?.iteration ? null : n)}
            >
              View it {n}
            </button>
          </div>
        </div>
      );
    }
    case "critic_start":
      return (
        <div className="card-sys">
          <span>critic reviewing iteration {String(ev.iteration ?? "")}</span>
        </div>
      );
    case "critic": {
      const disc = (ev.discrepancies as Discrepancy[]) || [];
      const v = String(ev.verdict || "");
      return (
        <div className={`card card-critic ${v === "pass" ? "pass" : ""}`}>
          <div className="card-head">
            <span>Critic · iteration {String(ev.iteration ?? "")}</span>
            <Pill tone={verdictTone(v)}>{v.replace("_", " ")}</Pill>
            <span className="t">{t}</span>
          </div>
          <div>{String(ev.summary || "")}</div>
          {disc.map((x, i) => (
            <div className="disc" key={i}>
              <div className="row-wrap">
                <Pill tone={severityTone(x.severity)}>{x.severity || "note"}</Pill>
                <span className="disc-where">{x.where}</span>
              </div>
              {x.observed && (
                <div className="small dim">
                  <b>Observed:</b> {x.observed}
                </div>
              )}
              {x.suggestion && (
                <div className="small disc-sugg">
                  <b>→</b> {x.suggestion}
                </div>
              )}
            </div>
          ))}
        </div>
      );
    }
    case "critic_followup":
      return (
        <div className="card-sys">
          <span>critic round {String(ev.round ?? "")} → designer revising</span>
        </div>
      );
    case "narration":
      return (
        <div className="card card-narration">
          <div className="card-head">
            <span>Designer's note</span>
            <span className="t">{t}</span>
          </div>
          <Markdown text={String(ev.text || "")} />
        </div>
      );
    case "question":
      return <QuestionCard ev={ev} active={active} onAnswer={onAnswer} />;
    case "answer":
      return (
        <div className="card">
          <div className="card-head">
            <span>You</span>
            <span className="t">{t}</span>
          </div>
          <div>{String(ev.text || "")}</div>
        </div>
      );
    case "run_end": {
      const st = String(ev.status || "");
      const cost = typeof ev.cost_usd === "number" ? ev.cost_usd : undefined;
      return (
        <div className="card-sys">
          <span>
            run ended · {st.replace("_", " ")}
            {typeof ev.iterations === "number" ? ` · ${ev.iterations} it.` : ""}
            {cost ? ` · $${cost.toFixed(2)}` : ""} · {t}
          </span>
        </div>
      );
    }
    case "error":
      return (
        <div className="card card-error">
          <div className="card-head">
            <span>Error</span>
            <span className="t">{t}</span>
          </div>
          <div className="mono small">{String(ev.message || "")}</div>
        </div>
      );
    case "photo":
      return (
        <div className="card-sys">
          <span>
            photo {String(ev.file || "").replace(/^photos\//, "")} · {ev.ok ? "good capture" : "needs retake"}
          </span>
        </div>
      );
    case "estimate":
      return (
        <div className="card-sys">
          <span>
            {ev.auto ? "measured" : "estimate"} {String(ev.dim)} = {fmtNum(ev.value)} mm ({String(ev.source).replace("rectified_sheet", "calibration sheet")}, conf {fmtNum(ev.conf)})
          </span>
        </div>
      );
    case "dim_confirmed":
      return (
        <div className="card-sys">
          <span>
            confirmed {String(ev.dim)} = {fmtNum(ev.value)} mm ({String(ev.source || "user")})
          </span>
        </div>
      );
    case "spec_updated": {
      const changed = Array.isArray(ev.changed) ? (ev.changed as Array<{ dim: string; from: number | null; to: number }>) : [];
      return (
        <div className="card-sys">
          <span>
            spec updated{ev.source === "customizer" ? " from the customizer" : ""}
            {changed.length ? ": " + changed.map((c) => `${c.dim} ${c.from ?? "?"} → ${c.to}`).join(", ") : ""} · {t}
          </span>
        </div>
      );
    }
    case "preset":
      return (
        <div className="card-sys">
          <span>
            preset “{String(ev.name)}” {String(ev.action)} · {t}
          </span>
        </div>
      );
    case "coupon":
      return (
        <div className="card-sys">
          <span>
            coupon compiled ·{" "}
            <a href={fileUrl(s.sid, String(ev.file || "export/coupon.stl"), ev.t)} download>
              coupon.stl
            </a>
          </span>
        </div>
      );
    case "coupon_result":
      return (
        <div className="card-sys">
          <span>
            coupon result: clearance {fmtNum(ev.clearance)} mm
            {Array.isArray(ev.confirmed) && ev.confirmed.length ? ` · confirmed ${(ev.confirmed as string[]).join(", ")}` : ""}
          </span>
        </div>
      );
    case "export":
      return (
        <div className="card-sys">
          <span>
            exported iteration {String(ev.iteration ?? "")}
            {Array.isArray(ev.files) ? ` · ${(ev.files as string[]).length} files` : ""}
          </span>
        </div>
      );
    case "intake": {
      const qs = (ev.questions as unknown[]) || [];
      const plan = (ev.capture_plan as unknown[]) || [];
      return (
        <div className="card">
          <div className="card-head">
            <span>Intake</span>
            <span className="t">{t}</span>
          </div>
          <div>
            <b>{String(ev.object || "object")}</b>
            {ev.part_role ? ` — ${String(ev.part_role)}` : ""}
          </div>
          <div className="small dim">
            {plan.length} capture shot{plan.length === 1 ? "" : "s"} planned · {qs.length} question{qs.length === 1 ? "" : "s"}
          </div>
        </div>
      );
    }
    case "branch":
      return (
        <div className="card-sys">
          <span>branched from iteration {String(ev.iteration ?? "")}</span>
        </div>
      );
    case "step":
    case "graph_node":
      return null;
    case "graph_run": {
      const cp = Array.isArray(ev.critical_path) ? (ev.critical_path as string[]).join(" → ") : "";
      const wall = typeof ev.wall_s === "number" ? ev.wall_s : 0;
      const serial = typeof ev.serial_s === "number" ? ev.serial_s : 0;
      return (
        <div className="card-sys">
          <span className={cp ? "hover-anchor" : undefined}>
            {String(ev.graph)} graph {String(ev.status)}
            {wall ? ` · ${wall.toFixed(1)} s wall` : ""}
            {serial > wall * 1.05 ? ` (${(serial / wall).toFixed(1)}× parallel)` : ""}
            {ev.waiting_on ? ` · waiting on ${String(ev.waiting_on)}` : ""}
            {cp && (
              <span className="hover-card below" role="tooltip">
                critical path: <span className="mono">{cp}</span>
              </span>
            )}
          </span>
        </div>
      );
    }
    case "capture_round": {
      const reqs = (ev.requests as Array<{ kind: string; title: string }>) || [];
      return (
        <div className="card">
          <div className="card-head">
            <span>Capture round {String(ev.n ?? "")}</span>
            <span className="t">{t}</span>
          </div>
          {ev.note ? <div className="small">{String(ev.note)}</div> : null}
          <ul className="md">
            {reqs.map((r, i) => (
              <li key={i}>
                <span className="mono small">{r.kind}</span> {r.title}
              </li>
            ))}
          </ul>
        </div>
      );
    }
    case "capture_ready": {
      const rd = (ev.readiness as { confirmed?: number; interface_dims?: number; advice?: string }) || {};
      return (
        <div className="card-sys">
          <span>
            {ev.ready ? "fit dimensions ready" : "capture rounds exhausted"} · {rd.confirmed ?? "?"}/{rd.interface_dims ?? "?"} confirmed
            {typeof ev.rounds === "number" ? ` · ${ev.rounds} round${ev.rounds === 1 ? "" : "s"}` : ""}
          </span>
        </div>
      );
    }
    case "usage": {
      const cost = typeof ev.cost_usd === "number" ? ev.cost_usd : 0;
      return (
        <div className="card-sys">
          <span>
            {String(ev.calls ?? "")} model calls · ${cost.toFixed(2)}
            {ev.model ? ` · ${String(ev.model)}` : ""}
          </span>
        </div>
      );
    }
    case "stage":
      return (
        <div className="card-sys">
          <span>stage → {String(ev.stage || "")}</span>
        </div>
      );
    case "answers": {
      const applied = (ev.applied as Array<Record<string, unknown>>) || [];
      return (
        <div className="card">
          <div className="card-head">
            <span>Your answers</span>
            <span className="t">{t}</span>
          </div>
          <ul className="md">
            {applied.map((a, i) => (
              <li key={i}>{a.dim ? `${String(a.dim)} = ${fmtNum(a.value)} mm (confirmed)` : String(a.note || "")}</li>
            ))}
          </ul>
        </div>
      );
    }
    default:
      return (
        <div className="card-sys">
          <span>
            {ev.kind} · {t}
          </span>
        </div>
      );
  }
}

function QuestionCard({ ev, active, onAnswer }: { ev: KinEvent; active: boolean; onAnswer: (a: string) => void }) {
  const [text, setText] = useState("");
  const options = (ev.options as string[]) || [];
  return (
    <div className={`card card-question${active ? "" : " answered"}`}>
      <div className="card-head">
        <span className="nowrap">Question</span>
        {active ? <Pill tone="blue" dot>waiting for you</Pill> : <Pill tone="neutral">answered</Pill>}
        <span className="t">{clock(ev.t)}</span>
      </div>
      <Markdown text={String(ev.question || "")} />
      {active && (
        <>
          {options.length > 0 && (
            <div className="choices">
              {options.map((o, i) => (
                <button key={i} className="btn btn-sm btn-choice" onClick={() => onAnswer(String(o))}>
                  {String(o)}
                </button>
              ))}
            </div>
          )}
          <div className="chat-input">
            <input
              className="input grow"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Or type an answer…"
              onKeyDown={(e) => {
                if (e.key === "Enter" && text.trim()) {
                  onAnswer(text.trim());
                  setText("");
                }
              }}
            />
            <button
              className="btn btn-sm btn-primary"
              disabled={!text.trim()}
              onClick={() => {
                onAnswer(text.trim());
                setText("");
              }}
            >
              Reply
            </button>
          </div>
        </>
      )}
    </div>
  );
}
