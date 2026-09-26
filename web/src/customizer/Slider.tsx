import { useCallback, useEffect, useRef, useState } from "react";

export interface SliderMark {
  at: number;
  label?: string;
  tone?: "blue" | "pass" | "warn" | "fail" | "neutral";
}

export interface SliderBand {
  lo: number;
  hi: number;
  tone: "pass" | "warn" | "blue";
  title?: string;
}

interface Props {
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (v: number, transient: boolean) => void;
  onDragStart?: () => void;
  onDragEnd?: () => void;
  band?: SliderBand | null;
  marks?: SliderMark[];
  disabled?: boolean;
  ariaLabel: string;
  format: (v: number) => string;
  /** ends labels */
  minLabel?: string;
  maxLabel?: string;
}

function snapTo(v: number, min: number, max: number, step: number): number {
  const n = Math.round((v - min) / step);
  const decimals = Math.max(0, Math.ceil(-Math.log10(step) - 1e-9)) + 1;
  const out = Number((min + n * step).toFixed(decimals));
  return Math.min(max, Math.max(min, out));
}

/** A drafting-style slider: a thin rule, a tolerance band, ticks for the measured / verified values, a round thumb. */
export default function Slider({ min, max, step, value, onChange, onDragStart, onDragEnd, band, marks, disabled, ariaLabel, format, minLabel, maxLabel }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);
  const span = max - min || 1;
  const pct = (v: number) => `${Math.min(100, Math.max(0, ((v - min) / span) * 100))}%`;
  const shown = Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : min;

  const valueAt = useCallback(
    (clientX: number) => {
      const el = host.current;
      if (!el) return shown;
      const r = el.getBoundingClientRect();
      const t = r.width > 0 ? (clientX - r.left) / r.width : 0;
      return snapTo(min + Math.min(1, Math.max(0, t)) * span, min, max, step);
    },
    [min, max, step, span, shown],
  );

  const onPointerDown = (e: React.PointerEvent) => {
    if (disabled || e.button !== 0) return;
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setDragging(true);
    onDragStart?.();
    onChange(valueAt(e.clientX), true);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging) return;
    onChange(valueAt(e.clientX), true);
  };
  const finish = (e: React.PointerEvent) => {
    if (!dragging) return;
    setDragging(false);
    // the last move is applied as part of the drag; onDragEnd records the whole drag as one undo step
    onChange(valueAt(e.clientX), true);
    onDragEnd?.();
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (disabled) return;
    const big = e.shiftKey ? 10 : 1;
    let next: number | null = null;
    if (e.key === "ArrowRight" || e.key === "ArrowUp") next = shown + step * big;
    else if (e.key === "ArrowLeft" || e.key === "ArrowDown") next = shown - step * big;
    else if (e.key === "PageUp") next = shown + step * 10;
    else if (e.key === "PageDown") next = shown - step * 10;
    else if (e.key === "Home") next = min;
    else if (e.key === "End") next = max;
    if (next === null) return;
    e.preventDefault();
    onChange(snapTo(next, min, max, step), false);
  };

  useEffect(() => {
    if (!dragging) return;
    const up = () => setDragging(false);
    window.addEventListener("pointercancel", up);
    return () => window.removeEventListener("pointercancel", up);
  }, [dragging]);

  return (
    <div className={`slider${disabled ? " disabled" : ""}${dragging ? " dragging" : ""}`}>
      <div className="slider-rail" ref={host} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={finish} onPointerCancel={finish}>
        <div className="slider-track" />
        {band && band.hi > band.lo && (
          <div className={`slider-band band-${band.tone}`} style={{ left: pct(band.lo), width: `calc(${pct(band.hi)} - ${pct(band.lo)})` }} aria-hidden="true" />
        )}
        <div className="slider-fill" style={{ width: pct(shown) }} />
        {(marks || []).map((m, i) => (
          <div key={i} className={`slider-mark mark-${m.tone || "neutral"}`} style={{ left: pct(m.at) }} aria-hidden="true" />
        ))}
        <div
          className="slider-thumb"
          style={{ left: pct(shown) }}
          role="slider"
          tabIndex={disabled ? -1 : 0}
          aria-label={ariaLabel}
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={shown}
          aria-valuetext={format(shown)}
          aria-disabled={disabled || undefined}
          onKeyDown={onKey}
        >
          {dragging && <div className="slider-bubble num">{format(shown)}</div>}
        </div>
      </div>
      <div className="slider-ends num">
        <span>{minLabel ?? format(min)}</span>
        <span>{maxLabel ?? format(max)}</span>
      </div>
    </div>
  );
}
