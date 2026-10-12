import { useEffect, useState, type ReactNode } from "react";
import { Reset } from "../icons";
import type { Param, ParamBinding } from "../types";
import { useCustomizer } from "./context";
import Slider, { type SliderBand, type SliderMark } from "./Slider";
import { clamp, decimalsFor, displayStep, fmt, fmtValue, fromDisplay, parseTyped, same, snap, sourceLabel, toDisplay, unitLabel } from "./units";
import { hoverProps, useHoveredDim } from "../hover";

// ---- shared bits -----------------------------------------------------------------------------------------------

function Head({ p, right, children }: { p: Param; right?: ReactNode; children?: ReactNode }) {
  const cz = useCustomizer();
  const changed = cz.isChanged(p.name);
  return (
    <div className="cz-head">
      <div className="cz-title">
        <span className={`cz-label${changed ? " changed" : ""}`}>{p.label || p.name}</span>
        <span className="cz-name mono">{p.name}</span>
        {changed && (
          <span className="hover-anchor">
            <button className="cz-reset" onClick={() => cz.reset(p.name)} aria-label={`Reset ${p.name} to the verified value`}>
              <Reset size={16} />
            </button>
            <span className="hover-card below" role="tooltip">
              back to <b className="num">{fmtValue(p, cz.verified[p.name], cz.units)}</b> (verified)
            </span>
          </span>
        )}
        {children}
      </div>
      {right}
    </div>
  );
}

function statusOf(b: ParamBinding): { text: string; tone: "pass" | "warn" | "fail" | "blue" } {
  if (b.role === "requirement") return { text: "requirement", tone: "blue" };
  if (b.status === "confirmed") return { text: "measured", tone: "pass" };
  if (b.status === "estimated") return { text: "estimated", tone: "warn" };
  return { text: "unknown", tone: "fail" };
}

export function BindingBadge({ p }: { p: Param }) {
  const cz = useCustomizer();
  const b = p.binding;
  if (!b) return null;
  const st = statusOf(b);
  const parts: string[] = [];
  if (b.role === "interface") {
    if (typeof b.target === "number") parts.push(`${fmtValue(p, b.target, cz.units)}${typeof b.tol === "number" ? ` ± ${fmt(toDisplay(p, b.tol, cz.units), decimalsFor(p, cz.units) + 1)}` : ""}`);
    if (b.sources.length) {
      const best = [...b.sources].sort((x, y) => (y.conf ?? 0) - (x.conf ?? 0))[0];
      parts.push(`from ${sourceLabel(best.source)}${b.sources.length > 1 ? ` +${b.sources.length - 1}` : ""}`);
    }
    if (typeof b.clearance === "number" && b.fit) parts.push(`${b.fit} fit, +${fmt(b.clearance, 2)} clearance`);
  } else {
    const lim: string[] = [];
    if (typeof b.min === "number") lim.push(`≥ ${fmtValue(p, b.min, cz.units)}`);
    if (typeof b.max === "number") lim.push(`≤ ${fmtValue(p, b.max, cz.units)}`);
    if (typeof b.target === "number") lim.push(`= ${fmtValue(p, b.target, cz.units)}`);
    parts.push(lim.join(", "));
  }
  const sorted = [...b.sources].sort((x, y) => (y.conf ?? 0) - (x.conf ?? 0));
  return (
    <div className={`cz-bind tone-${st.tone} hover-anchor`} tabIndex={sorted.length ? 0 : undefined}>
      <span className="cz-bind-dot" />
      <b>{st.text}</b>
      <span className="mono">{b.dim}</span>
      {parts.filter(Boolean).length > 0 && <span className="dim">· {parts.filter(Boolean).join(" · ")}</span>}
      {sorted.length > 0 && (
        <span className="hover-card below cz-evidence-card" role="tooltip">
          <b>
            {b.dim}
            {b.feature ? ` — ${b.feature}` : ""}
          </b>
          {sorted.map((src, i) => (
            <span key={i} className="cz-evidence-line">
              <span className="num">{fmtValue(p, src.value, cz.units)}</span> from {sourceLabel(src.source)}
              <span className="dim"> · {((src.conf ?? 0) * 100).toFixed(0)}% confidence</span>
            </span>
          ))}
        </span>
      )}
    </div>
  );
}

// ---- number -------------------------------------------------------------------------------------------------------

export function NumberControl({ p, disabled }: { p: Param; disabled: boolean }) {
  const hovered = useHoveredDim();
  const cz = useCustomizer();
  const raw = cz.valueOf(p);
  const value = typeof raw === "number" ? raw : Number(raw);
  const units = cz.units;
  const hasRange = typeof p.min === "number" && typeof p.max === "number";
  const dec = decimalsFor(p, units, value);
  const [text, setText] = useState(fmt(toDisplay(p, value, units), dec));
  const [focus, setFocus] = useState(false);
  const [bad, setBad] = useState(false);

  useEffect(() => {
    if (!focus) {
      setText(fmt(toDisplay(p, value, units), dec));
      setBad(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, units, focus]);

  const commitText = () => {
    const v = parseTyped(p, text, units);
    if (v === null || !Number.isFinite(v)) {
      setBad(true);
      return;
    }
    setBad(false);
    const nv = p.kind === "count" ? Math.round(v) : Number(v.toFixed(4));
    cz.setValue(p.name, nv);
    setText(fmt(toDisplay(p, nv, units), decimalsFor(p, units, nv)));
  };

  const bump = (dir: 1 | -1) => {
    const st = displayStep(p, units);
    const nv = fromDisplay(p, toDisplay(p, value, units) + dir * st, units);
    const fixed = hasRange ? snap(p, clamp(p, nv)) : Number(nv.toFixed(4));
    cz.setValue(p.name, fixed);
  };

  const b = p.binding;
  let band: SliderBand | null = null;
  const marks: SliderMark[] = [];
  const verifiedV = cz.verified[p.name];
  if (typeof verifiedV === "number" && cz.isChanged(p.name)) marks.push({ at: verifiedV, label: `verified: ${fmtValue(p, verifiedV, units)}`, tone: "neutral" });
  let warn: string | null = null;
  if (b && hasRange) {
    if (b.role === "interface" && typeof b.target === "number") {
      const tol = typeof b.tol === "number" ? b.tol : 0.3;
      band = { lo: b.target - tol, hi: b.target + tol, tone: b.status === "confirmed" ? "pass" : "warn", title: `measured ${b.target} ± ${tol}` };
      marks.push({ at: b.target, label: `measured ${fmtValue(p, b.target, units)}`, tone: b.status === "confirmed" ? "pass" : "warn" });
      if (Math.abs(value - b.target) > tol + 1e-9)
        warn =
          b.status === "confirmed"
            ? `Outside the measured ${fmtValue(p, b.target, units)} ± ${fmt(toDisplay(p, tol, units), dec + 1)} — applying moves the spec to your value and re-checks the fit.`
            : `Away from the estimate ${fmtValue(p, b.target, units)} — measure it or print the coupon to be sure.`;
    } else if (b.role === "requirement") {
      const lo = typeof b.min === "number" ? b.min : p.min!;
      const hi = typeof b.max === "number" ? b.max : p.max!;
      band = { lo, hi, tone: "blue", title: `requirement ${b.dim}` };
      if (typeof b.min === "number") marks.push({ at: b.min, label: `min ${fmtValue(p, b.min, units)}`, tone: "blue" });
      if (typeof b.max === "number") marks.push({ at: b.max, label: `max ${fmtValue(p, b.max, units)}`, tone: "blue" });
      if ((typeof b.min === "number" && value < b.min - 1e-9) || (typeof b.max === "number" && value > b.max + 1e-9))
        warn = `Outside the requirement ${b.dim} (${typeof b.min === "number" ? `≥ ${fmtValue(p, b.min, units)}` : ""}${typeof b.max === "number" ? ` ≤ ${fmtValue(p, b.max, units)}` : ""}) — the check will fail.`;
    }
  }
  const outOfRange = hasRange && (value < p.min! - 1e-9 || value > p.max! + 1e-9);
  const assertHit = cz.preview.status === "error" && cz.model?.asserts.some((a) => a.params.includes(p.name) && cz.preview.asserts.some((m) => m === a.message));

  return (
    <div className={`cz-param cz-number${disabled ? " disabled" : ""}${assertHit ? " assert-hit" : ""}${hovered && hovered === p.binding?.dim ? " is-hovered" : ""}`} {...hoverProps(p.binding?.dim)}>
      <Head
        p={p}
        right={
          <div className={`cz-numbox${bad ? " bad" : ""}`}>
            <button className="cz-step" onClick={() => bump(-1)} disabled={disabled} aria-label={`decrease ${p.name}`} tabIndex={-1}>
              −
            </button>
            <input
              className="cz-input num"
              value={text}
              inputMode="decimal"
              onChange={(e) => setText(e.target.value)}
              onFocus={() => setFocus(true)}
              onBlur={() => {
                setFocus(false);
                commitText();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                if (e.key === "Escape") {
                  setText(fmt(toDisplay(p, value, units), dec));
                  (e.target as HTMLInputElement).blur();
                }
                if (e.key === "ArrowUp") {
                  e.preventDefault();
                  bump(1);
                }
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  bump(-1);
                }
              }}
              disabled={disabled}
              aria-label={p.name}
              aria-description="Units are understood: 45, 1.75 in, 1 3/4 inch, 2 cm"
            />
            <button className="cz-step" onClick={() => bump(1)} disabled={disabled} aria-label={`increase ${p.name}`} tabIndex={-1}>
              +
            </button>
            <span className="cz-unit">{unitLabel(p, units) || (p.kind === "count" ? "×" : "")}</span>
          </div>
        }
      />
      {p.description && <div className="cz-desc">{p.description}</div>}
      {hasRange && (
        <Slider
          min={p.min!}
          max={p.max!}
          step={p.step && p.step > 0 ? p.step : displayStep(p, "mm")}
          value={value}
          onChange={(v, transient) => cz.setValue(p.name, v, { transient })}
          onDragStart={cz.dragStart}
          onDragEnd={cz.dragEnd}
          band={band}
          marks={marks}
          disabled={disabled}
          ariaLabel={`${p.label || p.name} slider`}
          format={(v) => fmtValue(p, v, units)}
          minLabel={fmtValue(p, p.min!, units, false)}
          maxLabel={fmtValue(p, p.max!, units, false)}
        />
      )}
      <BindingBadge p={p} />
      {outOfRange && <div className="cz-warn">Outside the designer's range {fmtValue(p, p.min!, units, false)}–{fmtValue(p, p.max!, units)} — the preview will still try it.</div>}
      {warn && <div className="cz-warn">{warn}</div>}
    </div>
  );
}

// ---- toggle ---------------------------------------------------------------------------------------------------------

export function ToggleControl({ p, disabled, children }: { p: Param; disabled: boolean; children?: ReactNode }) {
  const cz = useCustomizer();
  const on = !!cz.valueOf(p);
  return (
    <div className={`cz-param cz-toggle${disabled ? " disabled" : ""}`}>
      <Head
        p={p}
        right={
          <button
            type="button"
            role="switch"
            aria-checked={on}
            aria-label={p.name}
            className={`switch${on ? " on" : ""}`}
            onClick={() => cz.setValue(p.name, !on)}
            disabled={disabled}
          >
            <span className="switch-knob" />
          </button>
        }
      />
      {p.description && <div className="cz-desc">{p.description}</div>}
      {children && <div className={`cz-gated${on ? "" : " off"}`}>{children}</div>}
    </div>
  );
}

// ---- choice -----------------------------------------------------------------------------------------------------------

export function ChoiceControl({ p, disabled }: { p: Param; disabled: boolean }) {
  const cz = useCustomizer();
  const value = cz.valueOf(p);
  const idx = p.options.findIndex((o) => same(o.value, value));
  const cards = p.options.length <= 6;
  return (
    <div className={`cz-param cz-choice${disabled ? " disabled" : ""}`}>
      <Head p={p} />
      {p.description && <div className="cz-desc">{p.description}</div>}
      {cards ? (
        <div className="optcards" role="radiogroup" aria-label={p.name}>
          {p.options.map((o, i) => (
            <button
              key={i}
              type="button"
              role="radio"
              aria-checked={i === idx}
              className={`optcard${i === idx ? " active" : ""}`}
              onClick={() => cz.setValue(p.name, o.value)}
              disabled={disabled}
            >
              {o.label}
            </button>
          ))}
          {idx < 0 && <span className="small dim">current: {String(value)}</span>}
        </div>
      ) : (
        <select className="select" value={idx >= 0 ? String(idx) : ""} onChange={(e) => cz.setValue(p.name, p.options[Number(e.target.value)].value)} disabled={disabled} aria-label={p.name}>
          {idx < 0 && <option value="">{String(value)}</option>}
          {p.options.map((o, i) => (
            <option key={i} value={String(i)}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

// ---- text / vector --------------------------------------------------------------------------------------------------------

export function TextControl({ p, disabled }: { p: Param; disabled: boolean }) {
  const cz = useCustomizer();
  const value = cz.valueOf(p);
  const isVec = p.type === "vector";
  const text = isVec ? (typeof value === "string" ? value : JSON.stringify(value)) : String(value ?? "");
  const [local, setLocal] = useState(text);
  const [focus, setFocus] = useState(false);
  useEffect(() => {
    if (!focus) setLocal(text);
  }, [text, focus]);
  const commit = () => {
    if (isVec) {
      try {
        const v = JSON.parse(local);
        if (Array.isArray(v)) cz.setValue(p.name, v);
        else cz.setValue(p.name, local);
      } catch {
        cz.setValue(p.name, local);
      }
    } else cz.setValue(p.name, local);
  };
  return (
    <div className={`cz-param cz-text${disabled ? " disabled" : ""}`}>
      <Head p={p} />
      {p.description && <div className="cz-desc">{p.description}</div>}
      <input
        className="input input-mono"
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        onFocus={() => setFocus(true)}
        onBlur={() => {
          setFocus(false);
          commit();
        }}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
        disabled={disabled}
        aria-label={p.name}
        placeholder={isVec ? "[x, y, z]" : ""}
      />
    </div>
  );
}
