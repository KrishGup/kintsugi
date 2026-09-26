import type { Param } from "../types";

export type UnitSystem = "mm" | "in";

const MM_PER_IN = 25.4;

/** Is this parameter a length the unit toggle should convert? */
export function isLength(p: Param): boolean {
  return p.type === "number" && (p.unit === "mm" || p.kind === "length" || p.kind === "clearance");
}

/** Model value (always mm in OpenSCAD) -> display value in the chosen system. */
export function toDisplay(p: Param, v: number, units: UnitSystem): number {
  if (units === "in" && isLength(p)) return v / MM_PER_IN;
  return v;
}

/** Display value -> model value (mm). */
export function fromDisplay(p: Param, v: number, units: UnitSystem): number {
  if (units === "in" && isLength(p)) return v * MM_PER_IN;
  return v;
}

export function unitLabel(p: Param, units: UnitSystem): string {
  if (isLength(p)) return units === "in" ? "in" : "mm";
  return p.unit || "";
}

/** Decimal places to show: from the step (0.05 -> 2), lengths in inches get 3; a typed value keeps its own decimals. */
export function decimalsFor(p: Param, units: UnitSystem, value?: number): number {
  if (units === "in" && isLength(p)) return 3;
  const st = stepFor(p);
  let d: number;
  if (st >= 1) d = Number.isInteger(p.value) || p.kind === "count" ? 0 : 1;
  else d = Math.min(4, Math.max(0, Math.ceil(-Math.log10(st) - 1e-9)));
  if (typeof value === "number" && Number.isFinite(value)) {
    const own = decimalsOf(value);
    if (own > d) d = Math.min(3, own);
  }
  return d;
}

function decimalsOf(v: number): number {
  const s = String(Number(v.toFixed(4)));
  const i = s.indexOf(".");
  return i < 0 ? 0 : s.length - i - 1;
}

export function stepFor(p: Param): number {
  if (typeof p.step === "number" && p.step > 0) return p.step;
  if (p.kind === "count") return 1;
  if (p.kind === "clearance") return 0.05;
  return Number.isInteger(p.value) ? 1 : 0.1;
}

export function displayStep(p: Param, units: UnitSystem): number {
  const st = stepFor(p);
  if (units === "in" && isLength(p)) {
    // a sensible inch step: 1/64" for fine steps, 1/32" otherwise
    return st <= 0.25 ? 1 / 64 : st <= 1 ? 1 / 32 : 1 / 8;
  }
  return st;
}

export function fmt(v: number, decimals: number): string {
  if (!Number.isFinite(v)) return "—";
  const s = v.toFixed(decimals);
  // trim trailing zeros but keep at least the integer part
  return decimals > 0 ? s.replace(/\.?0+$/, "") || "0" : s;
}

export function fmtValue(p: Param, v: unknown, units: UnitSystem, withUnit = true): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return String(v ?? "");
  const d = decimalsFor(p, units, v);
  const s = fmt(toDisplay(p, v, units), d);
  const u = unitLabel(p, units);
  return withUnit && u ? `${s} ${u}` : s;
}

/** Round to the parameter's step grid (in model units). */
export function snap(p: Param, v: number): number {
  const st = stepFor(p);
  const base = typeof p.min === "number" ? p.min : 0;
  const n = Math.round((v - base) / st);
  const out = base + n * st;
  const decimals = Math.max(0, Math.ceil(-Math.log10(st) - 1e-9)) + 1;
  return Number(out.toFixed(decimals));
}

export function clamp(p: Param, v: number): number {
  let out = v;
  if (typeof p.min === "number") out = Math.max(p.min, out);
  if (typeof p.max === "number") out = Math.min(p.max, out);
  return out;
}

/** Parse what a person typed: "43.2", "1 3/4", "1.5in", "2 in", "45 mm", "1'" -> model mm (or the parameter's own unit). */
export function parseTyped(p: Param, text: string, units: UnitSystem): number | null {
  const t = text.trim().toLowerCase().replace(/,/g, ".");
  if (!t) return null;
  let m = t.match(/^(-?[\d.]+)\s*(mm|cm|m|in|inch|inches|"|'|°|deg)?$/);
  let val: number | null = null;
  let unit: string | null = null;
  if (m) {
    val = Number(m[1]);
    unit = m[2] || null;
  } else {
    // mixed fractions: 1 3/4, 3/4, 1-3/4
    m = t.match(/^(-?\d+)?[\s-]*(\d+)\/(\d+)\s*(mm|cm|m|in|inch|inches|"|')?$/);
    if (m) {
      const whole = m[1] ? Number(m[1]) : 0;
      const frac = Number(m[2]) / Number(m[3]);
      val = whole < 0 ? whole - frac : whole + frac;
      unit = m[4] || null;
    }
  }
  if (val === null || !Number.isFinite(val)) return null;
  if (!isLength(p)) return val;
  if (unit === "in" || unit === "inch" || unit === "inches" || unit === '"') return val * MM_PER_IN;
  if (unit === "'") return val * 12 * MM_PER_IN;
  if (unit === "cm") return val * 10;
  if (unit === "m") return val * 1000;
  if (unit === "mm") return val;
  return fromDisplay(p, val, units);
}

export function same(a: unknown, b: unknown): boolean {
  if (typeof a === "number" && typeof b === "number") return Math.abs(a - b) < 1e-9;
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Copy-friendly OpenSCAD literal. */
export function scadLiteral(v: unknown): string {
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : String(Number(v.toFixed(6)));
  if (typeof v === "string") return JSON.stringify(v);
  if (Array.isArray(v)) return `[${v.map(scadLiteral).join(", ")}]`;
  return String(v);
}

export function sourceLabel(src: string): string {
  const map: Record<string, string> = {
    rectified_sheet: "photo on the calibration sheet",
    reference_object: "photo with a reference object",
    user_caliper: "caliper",
    user_ruler: "ruler",
    user_stated: "typed by you",
    coupon: "fit coupon",
    vision_estimate: "model estimate from the photo",
    template_default: "template default",
    counterpart: "the mating part",
    jig: "printed jig",
    jig_side_view: "jig side view",
    reconstruction: "3D reconstruction",
  };
  if (src.startsWith("standard:")) return `standard ${src.slice(9).replace(/_/g, " ")}`;
  return map[src] || src.replace(/_/g, " ");
}
