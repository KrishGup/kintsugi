import { useMemo, useState } from "react";
import { kin } from "../api";
import { useSession } from "../pages/session-context";
import { useToast } from "../toast";
import type { IterationRunResult, Param } from "../types";
import { Empty, Pill, Spinner } from "../ui";

function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function stepFor(p: Param): number {
  if (typeof p.step === "number" && p.step > 0) return p.step;
  return Number.isInteger(p.value) ? 1 : 0.1;
}

export function describeIteration(r: IterationRunResult): { text: string; tone: "pass" | "fail" | "warn" } {
  if (!r.compile?.ok) {
    const err = (r.compile?.errors || [])[0];
    return { text: `Iteration ${r.iteration}: compile error${err ? ` — ${err}` : ""}`, tone: "fail" };
  }
  if (r.ok) return { text: `Iteration ${r.iteration}: all hard checks pass (${r.duration_s.toFixed(1)} s)`, tone: "pass" };
  const fails = (r.checks?.items || []).filter((i) => i.kind === "hard" && i.passed === false).map((i) => i.id);
  return { text: `Iteration ${r.iteration}: failing ${fails.join(", ") || "checks"}`, tone: "warn" };
}

export default function ParamsTab() {
  const s = useSession();
  const { toast, error } = useToast();
  const d = s.detail!;
  const [edits, setEdits] = useState<Record<string, unknown>>({});
  const [applying, setApplying] = useState(false);

  const groups = useMemo(() => {
    const m = new Map<string, Param[]>();
    for (const p of d.params) {
      const k = p.section || "Parameters";
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(p);
    }
    return [...m.entries()];
  }, [d.params]);

  const changed = useMemo(() => {
    const out: Record<string, unknown> = {};
    for (const p of d.params) {
      if (p.name in edits && !same(edits[p.name], p.value)) out[p.name] = edits[p.name];
    }
    return out;
  }, [edits, d.params]);
  const nChanged = Object.keys(changed).length;

  const set = (name: string, v: unknown) => setEdits((e) => ({ ...e, [name]: v }));
  const valueOf = (p: Param) => (p.name in edits ? edits[p.name] : p.value);

  const apply = async () => {
    if (!nChanged) return;
    const values: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(changed)) {
      const p = d.params.find((x) => x.name === k);
      if (p?.type === "vector" && typeof v === "string") {
        try {
          values[k] = JSON.parse(v);
        } catch {
          values[k] = v;
        }
      } else values[k] = v;
    }
    setApplying(true);
    await s.runBusy("Applying parameters…", async () => {
      try {
        const r = await kin.setParams(s.sid, values);
        const { text, tone } = describeIteration(r);
        toast(text, tone);
        setEdits({});
        await s.refresh();
        s.setSelected(null);
      } catch (e) {
        error(e, "Could not apply parameters");
      } finally {
        setApplying(false);
      }
    });
  };

  if (!d.params.length) {
    return (
      <Empty title="No customizer parameters yet" icon={<SlidersIcon />}>
        Once part.scad has a parameter block (<code>name = 10; // [min:step:max]</code>), each parameter gets a control here. Apply changes to
        re-run compile, checks and blueprints.
      </Empty>
    );
  }

  const disabled = applying || s.running || !!s.busy;

  return (
    <div>
      {groups.map(([section, ps]) => (
        <div className="params-group" key={section}>
          <div className="section-title">{section}</div>
          {ps.map((p) => {
            const v = valueOf(p);
            const isChanged = p.name in changed;
            return (
              <div className="param-row" key={p.name}>
                <span className={`param-name${isChanged ? " changed" : ""}`} title={p.name}>
                  {p.name}
                </span>
                <span className="param-range-lbl">
                  {p.type === "number" && p.min !== null && p.max !== null ? `${p.min} – ${p.max}` : p.type}
                </span>
                {p.description && <div className="param-desc">{p.description}</div>}
                <div className="param-ctl">
                  <ParamControl p={p} value={v} onChange={(nv) => set(p.name, nv)} disabled={disabled} />
                </div>
              </div>
            );
          })}
        </div>
      ))}
      <div className="sticky-actions">
        <button className="btn btn-primary btn-sm" onClick={apply} disabled={disabled || !nChanged}>
          {applying ? <Spinner size={11} /> : null} Apply{nChanged ? ` (${nChanged})` : ""}
        </button>
        <button className="btn btn-ghost btn-sm" onClick={() => setEdits({})} disabled={!nChanged || applying}>
          Reset
        </button>
        <span className="grow" />
        {applying ? (
          <span className="small muted">compiling, checking, rendering…</span>
        ) : s.running ? (
          <Pill tone="blue" dot>
            designer running
          </Pill>
        ) : (
          <span className="small muted">runs one iteration</span>
        )}
      </div>
    </div>
  );
}

function ParamControl({ p, value, onChange, disabled }: { p: Param; value: unknown; onChange: (v: unknown) => void; disabled: boolean }) {
  if (p.options && p.options.length > 0) {
    const idx = p.options.findIndex((o) => same(o.value, value));
    return (
      <select
        className="select"
        value={idx >= 0 ? String(idx) : ""}
        onChange={(e) => onChange(p.options[Number(e.target.value)].value)}
        disabled={disabled}
        aria-label={p.name}
      >
        {idx < 0 && <option value="">{String(value)}</option>}
        {p.options.map((o, i) => (
          <option key={i} value={String(i)}>
            {o.label}
          </option>
        ))}
      </select>
    );
  }
  if (p.type === "bool") {
    return (
      <label className="check">
        <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} disabled={disabled} aria-label={p.name} />
        <span className="small dim">{value ? "true" : "false"}</span>
      </label>
    );
  }
  if (p.type === "number") {
    const step = stepFor(p);
    const num = typeof value === "number" ? value : Number(value);
    const hasRange = p.min !== null && p.max !== null;
    return (
      <>
        {hasRange && (
          <input
            type="range"
            className="range"
            min={p.min!}
            max={p.max!}
            step={step}
            value={Number.isFinite(num) ? num : p.min!}
            onChange={(e) => onChange(Number(e.target.value))}
            disabled={disabled}
            aria-label={`${p.name} slider`}
          />
        )}
        <input
          type="number"
          className="input input-num"
          value={Number.isFinite(num) ? num : ""}
          step={step}
          min={p.min ?? undefined}
          max={p.max ?? undefined}
          onChange={(e) => {
            const nv = e.target.value === "" ? "" : Number(e.target.value);
            onChange(nv === "" ? value : nv);
          }}
          disabled={disabled}
          aria-label={p.name}
        />
      </>
    );
  }
  if (p.type === "vector") {
    const text = typeof value === "string" ? value : JSON.stringify(value);
    return <input className="input input-mono" value={text} onChange={(e) => onChange(e.target.value)} disabled={disabled} aria-label={p.name} />;
  }
  return <input className="input input-mono" value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} disabled={disabled} aria-label={p.name} />;
}

function SlidersIcon() {
  return (
    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
      <path d="M4 7h16M4 12h16M4 17h16" />
      <circle cx="9" cy="7" r="1.8" fill="currentColor" />
      <circle cx="15" cy="12" r="1.8" fill="currentColor" />
      <circle cx="7" cy="17" r="1.8" fill="currentColor" />
    </svg>
  );
}
