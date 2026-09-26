import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from "react";
import { ApiError, fileUrl, kin } from "../api";
import { useLocal } from "../hooks";
import { useSession } from "../pages/session-context";
import { useToast } from "../toast";
import type { CustomizerModel, IterationRunResult, Param, PreviewResult } from "../types";
import { same, scadLiteral, type UnitSystem } from "./units";

export type Quality = "auto" | "draft" | "full";

/** In auto mode a model whose full-quality preview takes longer than this drops to draft facets. */
export const AUTO_DRAFT_S = 2.5;

export interface PreviewState {
  status: "idle" | "queued" | "running" | "ok" | "error";
  gen: number;
  url: string | null;
  values: Record<string, unknown>;
  renderTarget: string | null;
  quality: Quality;
  durationS: number | null;
  avgS: number | null;
  echo: Record<string, unknown>;
  errors: string[];
  asserts: string[];
  warnings: string[];
  /** the edits moved on since this result was produced */
  stale: boolean;
}

type Edits = Record<string, unknown>;
interface EditState {
  edits: Edits;
  undo: Edits[];
  redo: Edits[];
}
type EditAction =
  | { type: "set"; edits: Edits; snapshot?: Edits }
  | { type: "transient"; edits: Edits }
  | { type: "push"; snapshot: Edits }
  | { type: "undo" }
  | { type: "redo" }
  | { type: "clear" }
  | { type: "prune"; keep: (name: string, v: unknown) => boolean };

function editReducer(st: EditState, a: EditAction): EditState {
  switch (a.type) {
    case "set":
      return { edits: a.edits, undo: a.snapshot ? [...st.undo.slice(-49), a.snapshot] : st.undo, redo: a.snapshot ? [] : st.redo };
    case "transient":
      return { ...st, edits: a.edits };
    case "push":
      return { ...st, undo: [...st.undo.slice(-49), a.snapshot], redo: [] };
    case "undo": {
      if (!st.undo.length) return st;
      const prev = st.undo[st.undo.length - 1];
      return { edits: prev, undo: st.undo.slice(0, -1), redo: [...st.redo, st.edits] };
    }
    case "redo": {
      if (!st.redo.length) return st;
      const next = st.redo[st.redo.length - 1];
      return { edits: next, undo: [...st.undo, st.edits], redo: st.redo.slice(0, -1) };
    }
    case "clear":
      return { edits: {}, undo: [], redo: [] };
    case "prune": {
      const out: Edits = {};
      let changed = false;
      for (const [k, v] of Object.entries(st.edits)) {
        if (a.keep(k, v)) out[k] = v;
        else changed = true;
      }
      return changed ? { ...st, edits: out } : st;
    }
  }
}

const IDLE: PreviewState = {
  status: "idle",
  gen: 0,
  url: null,
  values: {},
  renderTarget: "part",
  quality: "draft",
  durationS: null,
  avgS: null,
  echo: {},
  errors: [],
  asserts: [],
  warnings: [],
  stale: false,
};

/** Above this (seconds per preview) the automatic preview pauses and offers a button instead. */
export const SLOW_PREVIEW_S = 5;
const DEBOUNCE_MS = 260;

export interface CustomizerState {
  model: CustomizerModel | null;
  loading: boolean;
  reload: () => Promise<void>;
  /** parameter -> edited value (only those that differ from the verified part.scad) */
  edits: Record<string, unknown>;
  nChanged: number;
  /** the full current value set (verified values overlaid with the edits) */
  values: Record<string, unknown>;
  verified: Record<string, unknown>;
  valueOf: (p: Param) => unknown;
  isChanged: (name: string) => boolean;
  setValue: (name: string, v: unknown, opts?: { transient?: boolean }) => void;
  dragStart: () => void;
  dragEnd: () => void;
  reset: (name: string) => void;
  resetAll: () => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  units: UnitSystem;
  setUnits: (u: UnitSystem) => void;
  quality: Quality;
  setQuality: (q: Quality) => void;
  /** what the next preview will actually use (auto resolves to draft or full) */
  effectiveQuality: "draft" | "full";
  autoPreview: boolean;
  setAutoPreview: (b: boolean) => void;
  /** the adaptive pause: previews are slow for this model, so they wait for a click */
  paused: boolean;
  renderTarget: string;
  setRenderTarget: (t: string) => void;
  preview: PreviewState;
  previewNow: () => void;
  /** a draft mesh exists and is what the viewer should show */
  hasDraft: boolean;
  viewMode: "draft" | "verified";
  setViewMode: (m: "draft" | "verified") => void;
  applying: boolean;
  apply: (opts?: { updateSpec?: boolean }) => Promise<IterationRunResult | null>;
  /** bound interface (fit) parameters among the edits — applying moves the spec target */
  boundEdits: Param[];
  presets: Record<string, Record<string, unknown>>;
  savePreset: (name: string) => Promise<void>;
  applyPreset: (name: string) => void;
  deletePreset: (name: string) => Promise<void>;
  command: string;
  draftDownloadUrl: string | null;
}

const Ctx = createContext<CustomizerState | null>(null);

export function useCustomizer(): CustomizerState {
  const c = useContext(Ctx);
  if (!c) throw new Error("useCustomizer outside CustomizerProvider");
  return c;
}

export function CustomizerProvider({ children }: { children: ReactNode }) {
  const s = useSession();
  const { toast, error } = useToast();
  const sid = s.sid;
  const scad = s.detail?.scad ?? null;
  const iteration = s.detail?.meta.iteration ?? 0;

  const [model, setModel] = useState<CustomizerModel | null>(null);
  const [loading, setLoading] = useState(false);
  const [es, dispatch] = useReducer(editReducer, { edits: {}, undo: [], redo: [] });
  const edits = es.edits;
  const [units, setUnits] = useLocal<UnitSystem>("kin.cz.units", "mm");
  const [quality, setQuality] = useLocal<Quality>("kin.cz.quality", "auto");
  const [fullS, setFullS] = useState<number | null>(null);
  const [autoPreview, setAutoPreview] = useLocal<boolean>("kin.cz.auto", true);
  const [renderTarget, setRenderTarget] = useState("part");
  const [preview, setPreview] = useState<PreviewState>(IDLE);
  const [viewMode, setViewMode] = useState<"draft" | "verified">("draft");
  const [applying, setApplying] = useState(false);
  const [presets, setPresets] = useState<Record<string, Record<string, unknown>>>({});
  const dragSnapshot = useRef<Record<string, unknown> | null>(null);
  const editsRef = useRef(edits);
  editsRef.current = edits;
  const wantRef = useRef({ renderTarget, quality: "full" as "draft" | "full" });

  // ---- the model ------------------------------------------------------------------------------------------
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const m = await kin.customizer(sid);
      setModel(m);
      setPresets(m.presets || {});
      if (m.render_targets && !m.render_targets.includes(renderTarget)) setRenderTarget(m.render_targets[0] || "part");
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 404)) error(e, "Could not load the customizer");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid, error]);

  useEffect(() => {
    if (!scad) {
      setModel(null);
      return;
    }
    reload();
  }, [sid, scad, iteration, reload]);

  const verified = useMemo(() => model?.verified?.values || {}, [model]);
  const params = model?.params || [];

  // drop edits that no longer apply once the verified values move (designer iteration, apply, branch)
  useEffect(() => {
    if (!model) return;
    const known = new Set(params.map((p) => p.name));
    dispatch({ type: "prune", keep: (k, v) => known.has(k) && !same(v, verified[k]) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model]);

  const values = useMemo(() => ({ ...verified, ...edits }), [verified, edits]);
  const nChanged = Object.keys(edits).length;
  const valueOf = useCallback((p: Param) => (p.name in edits ? edits[p.name] : p.value), [edits]);
  const isChanged = useCallback((name: string) => name in edits, [edits]);

  const setEdits = useCallback((next: Edits, snapshot?: Edits) => dispatch({ type: "set", edits: next, snapshot }), []);

  const setValue = useCallback(
    (name: string, v: unknown, opts?: { transient?: boolean }) => {
      const cur = editsRef.current;
      const next = { ...cur };
      if (same(v, verified[name])) delete next[name];
      else next[name] = v;
      if (opts?.transient) {
        editsRef.current = next; // a drag fires faster than React re-renders; keep the ref current for the next move
        dispatch({ type: "transient", edits: next });
      } else setEdits(next, cur);
    },
    [verified, setEdits],
  );

  const dragStart = useCallback(() => {
    dragSnapshot.current = editsRef.current;
  }, []);
  const dragEnd = useCallback(() => {
    const snap = dragSnapshot.current;
    dragSnapshot.current = null;
    if (snap && JSON.stringify(snap) !== JSON.stringify(editsRef.current)) dispatch({ type: "push", snapshot: snap });
  }, []);

  const reset = useCallback(
    (name: string) => {
      const cur = editsRef.current;
      if (!(name in cur)) return;
      const next = { ...cur };
      delete next[name];
      setEdits(next, cur);
    },
    [setEdits],
  );
  const resetAll = useCallback(() => {
    const cur = editsRef.current;
    if (!Object.keys(cur).length) return;
    setEdits({}, cur);
  }, [setEdits]);

  const undo = useCallback(() => dispatch({ type: "undo" }), []);
  const redo = useCallback(() => dispatch({ type: "redo" }), []);

  // ---- live preview -----------------------------------------------------------------------------------------
  const seq = useRef(0);
  const inflight = useRef<AbortController | null>(null);
  const timer = useRef<number | undefined>(undefined);
  // auto quality: full facets while the model previews quickly, draft facets once a full preview proved slow
  const effectiveQuality: "draft" | "full" = quality === "auto" ? (fullS !== null && fullS > AUTO_DRAFT_S ? "draft" : "full") : quality;
  const wantKey = useMemo(() => JSON.stringify({ edits, renderTarget, effectiveQuality }), [edits, renderTarget, effectiveQuality]);
  wantRef.current = { renderTarget, quality: effectiveQuality };
  const needsPreview = nChanged > 0 || renderTarget !== "part";
  const slow = (preview.avgS ?? 0) > SLOW_PREVIEW_S || (preview.durationS ?? 0) > SLOW_PREVIEW_S * 1.6;
  const paused = autoPreview && slow;

  const runPreview = useCallback(
    (vals: Record<string, unknown>, target: string, q: "draft" | "full") => {
      inflight.current?.abort();
      const ctl = new AbortController();
      inflight.current = ctl;
      const my = ++seq.current;
      setPreview((p) => ({ ...p, status: "running", stale: false }));
      kin
        .preview(sid, vals, target, q, ctl.signal)
        .then((r: PreviewResult) => {
          if (my !== seq.current || r.superseded) return;
          const gen = r.gen;
          if (q === "full" && r.ok && typeof r.duration_s === "number") setFullS(r.duration_s);
          setPreview({
            status: r.ok ? "ok" : "error",
            gen,
            url: r.ok && r.file ? fileUrl(sid, r.file, `${gen}`) : null,
            values: vals,
            renderTarget: target,
            quality: q,
            durationS: r.duration_s ?? null,
            avgS: r.avg_duration_s ?? null,
            echo: r.echo_values || {},
            errors: r.errors || [],
            asserts: r.assert_failures || [],
            warnings: r.warnings || [],
            stale: JSON.stringify(editsRef.current) !== JSON.stringify(vals) || target !== wantRef.current.renderTarget || q !== wantRef.current.quality,
          });
        })
        .catch((e) => {
          if (my !== seq.current || (e instanceof DOMException && e.name === "AbortError") || ctl.signal.aborted) return;
          setPreview((p) => ({ ...p, status: "error", errors: [e instanceof Error ? e.message : String(e)], asserts: [], stale: false }));
        });
    },
    [sid],
  );

  const previewNow = useCallback(() => {
    window.clearTimeout(timer.current);
    runPreview(editsRef.current, renderTarget, effectiveQuality);
  }, [runPreview, renderTarget, effectiveQuality]);

  useEffect(() => {
    window.clearTimeout(timer.current);
    if (!model?.available) return;
    if (!needsPreview) {
      inflight.current?.abort();
      seq.current++;
      setPreview(IDLE);
      return;
    }
    // something changed since the last result
    setPreview((p) => (p.status === "ok" || p.status === "error" ? { ...p, stale: true } : p));
    if (!autoPreview || paused) return;
    timer.current = window.setTimeout(() => runPreview(editsRef.current, renderTarget, effectiveQuality), DEBOUNCE_MS);
    return () => window.clearTimeout(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantKey, model?.available, autoPreview, paused]);

  // a new verified mesh (designer iteration, apply) invalidates the draft
  useEffect(() => {
    inflight.current?.abort();
    seq.current++;
    setPreview(IDLE);
  }, [iteration, scad]);

  const hasDraft = preview.status === "ok" && !!preview.url && needsPreview;

  // ---- apply & verify -----------------------------------------------------------------------------------------
  const boundEdits = useMemo(
    () => params.filter((p) => p.name in edits && p.binding && p.binding.role === "interface" && p.binding.target !== null && ["explicit", "name+value", "name"].includes(p.binding.how)),
    [params, edits],
  );

  const apply = useCallback(
    async (opts?: { updateSpec?: boolean }): Promise<IterationRunResult | null> => {
      const cur = editsRef.current;
      if (!Object.keys(cur).length) return null;
      const vals: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(cur)) {
        const p = params.find((x) => x.name === k);
        if (p?.type === "vector" && typeof v === "string") {
          try {
            vals[k] = JSON.parse(v);
          } catch {
            vals[k] = v;
          }
        } else vals[k] = v;
      }
      setApplying(true);
      let result: IterationRunResult | null = null;
      await s.runBusy("Applying parameters…", async () => {
        try {
          const label = "customizer: " + Object.entries(vals).map(([k, v]) => `${k}=${scadLiteral(v)}`).join(", ");
          const r = await kin.setParams(sid, vals, label, opts?.updateSpec ?? true);
          result = r;
          const { text, tone } = describeIteration(r);
          toast(text, tone);
          if (r.spec_changed?.length) toast(`Spec updated: ${r.spec_changed.map((c) => `${c.dim} ${c.from ?? "?"} → ${c.to}`).join(", ")}`, "info");
          dispatch({ type: "clear" });
          setPreview(IDLE);
          await s.refresh();
          s.setSelected(null);
        } catch (e) {
          error(e, "Could not apply parameters");
        } finally {
          setApplying(false);
        }
      });
      return result;
    },
    [params, s, sid, toast, error],
  );

  // ---- presets ----------------------------------------------------------------------------------------------
  const savePreset = useCallback(
    async (name: string) => {
      try {
        const r = await kin.savePreset(sid, name, { ...verified, ...editsRef.current });
        setPresets(r.presets);
        toast(`Preset “${name}” saved`, "pass");
      } catch (e) {
        error(e, "Could not save the preset");
      }
    },
    [sid, verified, toast, error],
  );
  const applyPreset = useCallback(
    (name: string) => {
      const pv = presets[name];
      if (!pv) return;
      const next: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(pv)) if (k in verified && !same(v, verified[k])) next[k] = v;
      setEdits(next, editsRef.current);
    },
    [presets, verified, setEdits],
  );
  const deletePreset = useCallback(
    async (name: string) => {
      try {
        const r = await kin.deletePreset(sid, name);
        setPresets(r.presets);
      } catch (e) {
        error(e, "Could not delete the preset");
      }
    },
    [sid, error],
  );

  const command = useMemo(() => {
    const defs = Object.entries(edits).map(([k, v]) => `-D ${k}=${quoteShell(scadLiteral(v))}`);
    if (model?.has_render_target) defs.push(`-D render_target=${quoteShell(JSON.stringify(renderTarget))}`);
    return ["openscad", "-o", "part.stl", ...defs, "part.scad"].join(" ");
  }, [edits, renderTarget, model?.has_render_target]);

  const draftDownloadUrl = hasDraft && preview.url ? preview.url : null;

  const value: CustomizerState = useMemo(
    () => ({
      model,
      loading,
      reload,
      edits,
      nChanged,
      values,
      verified,
      valueOf,
      isChanged,
      setValue,
      dragStart,
      dragEnd,
      reset,
      resetAll,
      undo,
      redo,
      canUndo: es.undo.length > 0,
      canRedo: es.redo.length > 0,
      units,
      setUnits,
      quality,
      setQuality,
      effectiveQuality,
      autoPreview,
      setAutoPreview,
      paused,
      renderTarget,
      setRenderTarget,
      preview,
      previewNow,
      hasDraft,
      viewMode,
      setViewMode,
      applying,
      apply,
      boundEdits,
      presets,
      savePreset,
      applyPreset,
      deletePreset,
      command,
      draftDownloadUrl,
    }),
    [
      model, loading, reload, edits, nChanged, values, verified, valueOf, isChanged, setValue, dragStart, dragEnd, reset, resetAll, undo, redo,
      es.undo.length, es.redo.length, units, setUnits, quality, setQuality, effectiveQuality, autoPreview, setAutoPreview, paused, renderTarget, preview,
      previewNow, hasDraft, viewMode, applying, apply, boundEdits, presets, savePreset, applyPreset, deletePreset, command, draftDownloadUrl,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

function quoteShell(s: string): string {
  return /[\s"'$]/.test(s) ? `'${s.replace(/'/g, `'\\''`)}'` : s;
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
