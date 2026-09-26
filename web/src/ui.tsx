import type { ReactNode } from "react";

export type Tone = "pass" | "fail" | "warn" | "blue" | "neutral";

export function Pill({
  tone = "neutral",
  children,
  title,
  dot,
  className,
  ...rest
}: { tone?: Tone; children: ReactNode; title?: string; dot?: boolean; className?: string } & React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span className={`pill pill-${tone}${className ? ` ${className}` : ""}`} title={title} {...rest}>
      {dot && <span className="pill-dot" />}
      {children}
    </span>
  );
}

export function Spinner({ size = 14, label }: { size?: number; label?: string }) {
  return (
    <span className="spinner-wrap" role="status" aria-live="polite">
      <span className="spinner" style={{ width: size, height: size }} />
      {label && <span className="spinner-label">{label}</span>}
    </span>
  );
}

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="empty">
      {icon && <div className="empty-icon">{icon}</div>}
      <div className="empty-title">{title}</div>
      {children && <div className="empty-body">{children}</div>}
    </div>
  );
}

/** Status tone for a session meta status. */
export function statusTone(status: string | undefined, running?: boolean): Tone {
  if (running || status === "running") return "blue";
  switch (status) {
    case "done":
      return "pass";
    case "waiting_user":
    case "budget_exhausted":
      return "warn";
    case "error":
      return "fail";
    default:
      return "neutral";
  }
}

export function statusLabel(status: string | undefined, running?: boolean): string {
  if (running) return "running";
  switch (status) {
    case "waiting_user":
      return "waiting for you";
    case "budget_exhausted":
      return "budget exhausted";
    case "intake_done":
      return "intake done";
    case undefined:
    case "":
    case "new":
      return "idle";
    default:
      return status;
  }
}

export function relTime(ts: number | undefined): string {
  if (!ts) return "—";
  const ms = ts > 1e12 ? ts : ts * 1000;
  const diff = Date.now() - ms;
  const s = Math.round(diff / 1000);
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  if (d < 30) return `${d} d ago`;
  return new Date(ms).toLocaleDateString();
}

export function fmtNum(v: unknown, digits = 2): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(digits);
  if (Array.isArray(v)) return `[${v.map((x) => fmtNum(x, digits)).join(", ")}]`;
  if (typeof v === "boolean") return v ? "yes" : "no";
  return String(v);
}

export function severityTone(sev: string | undefined): Tone {
  switch ((sev || "").toLowerCase()) {
    case "high":
      return "fail";
    case "medium":
      return "warn";
    case "low":
      return "neutral";
    default:
      return "neutral";
  }
}

export function verdictTone(v: string | undefined): Tone {
  switch (v) {
    case "pass":
      return "pass";
    case "revise":
      return "warn";
    case "ask_user":
      return "blue";
    case "error":
      return "fail";
    default:
      return "neutral";
  }
}

/** Markdown-lite: paragraphs, bullet and numbered lines, **bold**, `code`, fenced code. */
export function Markdown({ text }: { text: string }) {
  const blocks = splitBlocks(text || "");
  return (
    <div className="md">
      {blocks.map((b, i) => {
        if (b.type === "code") return <pre key={i} className="md-code">{b.lines.join("\n")}</pre>;
        if (b.type === "ul")
          return (
            <ul key={i}>
              {b.lines.map((l, j) => (
                <li key={j}>{inline(l)}</li>
              ))}
            </ul>
          );
        if (b.type === "ol")
          return (
            <ol key={i}>
              {b.lines.map((l, j) => (
                <li key={j}>{inline(l)}</li>
              ))}
            </ol>
          );
        if (b.type === "h") return <div key={i} className="md-h">{inline(b.lines.join(" "))}</div>;
        return <p key={i}>{inline(b.lines.join(" "))}</p>;
      })}
    </div>
  );
}

type Block = { type: "p" | "ul" | "ol" | "code" | "h"; lines: string[] };

function splitBlocks(text: string): Block[] {
  const out: Block[] = [];
  let cur: Block | null = null;
  let inCode = false;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.replace(/\s+$/, "");
    if (line.trim().startsWith("```")) {
      if (inCode) {
        inCode = false;
        cur = null;
      } else {
        inCode = true;
        cur = { type: "code", lines: [] };
        out.push(cur);
      }
      continue;
    }
    if (inCode) {
      cur!.lines.push(raw);
      continue;
    }
    if (!line.trim()) {
      cur = null;
      continue;
    }
    const ul = /^\s*[-*•]\s+(.*)$/.exec(line);
    const ol = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    const h = /^\s*#{1,4}\s+(.*)$/.exec(line);
    if (ul) {
      if (!cur || cur.type !== "ul") {
        cur = { type: "ul", lines: [] };
        out.push(cur);
      }
      cur.lines.push(ul[1]);
    } else if (ol) {
      if (!cur || cur.type !== "ol") {
        cur = { type: "ol", lines: [] };
        out.push(cur);
      }
      cur.lines.push(ol[1]);
    } else if (h) {
      cur = { type: "h", lines: [h[1]] };
      out.push(cur);
      cur = null;
    } else {
      if (!cur || cur.type !== "p") {
        cur = { type: "p", lines: [] };
        out.push(cur);
      }
      cur.lines.push(line.trim());
    }
  }
  return out;
}

function inline(s: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(s))) {
    if (m.index > last) parts.push(s.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) parts.push(<strong key={k++}>{tok.slice(2, -2)}</strong>);
    else parts.push(<code key={k++}>{tok.slice(1, -1)}</code>);
    last = m.index + tok.length;
  }
  if (last < s.length) parts.push(s.slice(last));
  return parts;
}
