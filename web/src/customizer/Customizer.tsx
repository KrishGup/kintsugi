import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import { useDismiss } from "../hooks";
import { Close, Cross, More, Redo, Undo } from "../icons";
import { useSession } from "../pages/session-context";
import { useToast } from "../toast";
import type { Param } from "../types";
import { Empty, Pill, Spinner } from "../ui";
import { SLOW_PREVIEW_S, useCustomizer } from "./context";
import { ChoiceControl, NumberControl, TextControl, ToggleControl } from "./controls";
import { fmt, fmtValue } from "./units";

const HIDDEN_PARAMS = new Set(["render_target"]);

export default function Customizer() {
  const s = useSession();
  const cz = useCustomizer();
  const [section, setSection] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [updateSpec, setUpdateSpec] = useState(true);
  const model = cz.model;

  const params = useMemo(() => (model?.params || []).filter((p) => !HIDDEN_PARAMS.has(p.name)), [model]);
  const sections = useMemo(() => (model?.sections || []).filter((sec) => params.some((p) => p.section === sec)), [model, params]);
  const disabled = cz.applying || s.running || !!s.busy;

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return params.filter((p) => (section === "all" || p.section === section) && (!q || `${p.name} ${p.label || ""} ${p.description || ""} ${p.binding?.dim || ""}`.toLowerCase().includes(q)));
  }, [params, section, query]);

  const groups = useMemo(() => {
    const byName = new Map(visible.map((p) => [p.name, p]));
    const out: Array<{ section: string; items: Array<{ p: Param; children: Param[] }> }> = [];
    for (const sec of sections) {
      const items: Array<{ p: Param; children: Param[] }> = [];
      const consumed = new Set<string>();
      for (const p of visible) {
        if (p.section !== sec || consumed.has(p.name)) continue;
        if (p.gate && byName.has(p.gate)) continue; // rendered under its toggle
        const children = p.type === "bool" ? visible.filter((c) => c.gate === p.name) : [];
        for (const c of children) consumed.add(c.name);
        items.push({ p, children });
      }
      if (items.length) out.push({ section: sec, items });
    }
    return out;
  }, [visible, sections]);

  if (!model || !model.available || !params.length) {
    return (
      <Empty title={cz.loading ? "Loading the customizer…" : "No customizer parameters yet"} icon={<SlidersIcon />}>
        Once part.scad has a parameter block (<code>name = 10; // [min:step:max] description</code>), every parameter gets a slider or a switch here, the 3D
        view previews each change as a draft, and <b>Apply &amp; verify</b> re-runs the checks.
      </Empty>
    );
  }

  const changedIn = (sec: string) => params.filter((p) => p.section === sec && cz.isChanged(p.name)).length;
  const onKeys = (e: React.KeyboardEvent) => {
    const tag = (e.target as HTMLElement).tagName;
    if (tag === "INPUT" || tag === "TEXTAREA") return;
    if ((e.ctrlKey || e.metaKey) && (e.key === "z" || e.key === "Z")) {
      e.preventDefault();
      if (e.shiftKey) cz.redo();
      else cz.undo();
    }
  };

  return (
    <div className="cz" onKeyDown={onKeys}>
      <div className="cz-toolbar">
        <div className="cz-toolbar-row">
          {sections.length > 1 ? (
            <div className="seg cz-sections" role="tablist" aria-label="Parameter sections">
              <button role="tab" aria-selected={section === "all"} className={`seg-btn${section === "all" ? " active" : ""}`} onClick={() => setSection("all")}>
                All
              </button>
              {sections.map((sec) => (
                <button key={sec} role="tab" aria-selected={section === sec} className={`seg-btn${section === sec ? " active" : ""}`} onClick={() => setSection(sec)}>
                  {sec}
                  {changedIn(sec) > 0 && <span className="seg-dot" title={`${changedIn(sec)} changed`} />}
                </button>
              ))}
            </div>
          ) : (
            <span className="label">{sections[0] || "Parameters"}</span>
          )}
          <span className="grow" />
          <button className={`btn btn-xs btn-ghost${searchOpen ? " active" : ""}`} onClick={() => setSearchOpen((v) => !v)} title="Find a parameter" aria-label="search parameters">
            <SearchIcon />
          </button>
        </div>
        <div className="cz-toolbar-row popover-anchor">
          <div className="seg cz-units" title="Display units (the model stays in millimetres)">
            <button className={`seg-btn${cz.units === "mm" ? " active" : ""}`} onClick={() => cz.setUnits("mm")}>
              mm
            </button>
            <button className={`seg-btn${cz.units === "in" ? " active" : ""}`} onClick={() => cz.setUnits("in")}>
              in
            </button>
          </div>
          <button className="btn btn-xs btn-ghost" onClick={cz.undo} disabled={!cz.canUndo} title="Undo the last change (Ctrl+Z)" aria-label="undo">
            <Undo size={13} />
          </button>
          <button className="btn btn-xs btn-ghost" onClick={cz.redo} disabled={!cz.canRedo} title="Redo (Ctrl+Shift+Z)" aria-label="redo">
            <Redo size={13} />
          </button>
          <PresetsMenu />
          <MoreMenu />
          <span className="grow" />
          {cz.nChanged > 0 ? (
            <span className="small" style={{ color: "var(--blue)" }}>
              {cz.nChanged} changed
            </span>
          ) : (
            <span className="small dim">verified · it {model.verified?.iteration ?? 0}</span>
          )}
        </div>
        {searchOpen && (
          <div className="cz-toolbar-row">
            <input className="input" autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find a parameter: name, label, description, spec dimension…" aria-label="search" />
            {query && (
              <button className="btn btn-xs btn-ghost" onClick={() => setQuery("")}>
                clear
              </button>
            )}
          </div>
        )}
        <StatusStrip />
      </div>

      {groups.length === 0 && <div className="small dim" style={{ padding: 12 }}>No parameter matches.</div>}
      {groups.map((g) => (
        <section className="cz-group" key={g.section}>
          {(section === "all" || sections.length === 1) && (
            <div className="cz-group-title">
              <span>{g.section}</span>
              {changedIn(g.section) > 0 && <span className="cz-group-count">{changedIn(g.section)} changed</span>}
            </div>
          )}
          {g.items.map(({ p, children }) => (
            <Control key={p.name} p={p} disabled={disabled}>
              {children.length > 0 && children.map((c) => <Control key={c.name} p={c} disabled={disabled || !cz.valueOf(p)} />)}
            </Control>
          ))}
        </section>
      ))}

      <ComputedPanel />

      <div className="sticky-actions cz-footer">
        {cz.boundEdits.length > 0 && (
          <label className="cz-spec-note" title="These parameters are bound to measured dimensions in the spec. Applying moves the spec target with the parameter so the fit check verifies the value you chose.">
            <input type="checkbox" checked={updateSpec} onChange={(e) => setUpdateSpec(e.target.checked)} />
            <span>
              Fit {cz.boundEdits.length === 1 ? "dimension" : "dimensions"} changed ({cz.boundEdits.map((p) => p.label || p.name).join(", ")}) — also update the spec target
            </span>
          </label>
        )}
        <div className="cz-footer-row">
          <button className="btn btn-primary btn-sm" onClick={() => cz.apply({ updateSpec })} disabled={disabled || !cz.nChanged} title="Rewrite part.scad with these values and run compile → checks → blueprints (a new verified iteration)">
            {cz.applying ? <Spinner size={11} /> : <CheckIcon />} Apply &amp; verify{cz.nChanged ? ` (${cz.nChanged})` : ""}
          </button>
          <button className="btn btn-ghost btn-sm" onClick={cz.resetAll} disabled={!cz.nChanged || cz.applying}>
            Reset
          </button>
          <span className="grow" />
          {cz.applying ? (
            <span className="small muted">compiling, checking, rendering…</span>
          ) : s.running ? (
            <Pill tone="blue" dot>
              designer running
            </Pill>
          ) : cz.draftDownloadUrl ? (
            <a className="btn btn-xs" href={cz.draftDownloadUrl} download={`${(model.part_name || "part").replace(/[^\w.-]+/g, "_")}-draft.stl`} title="The draft mesh as shown (lower facet count, not verified). Apply & verify for the checked STL.">
              <DownloadIcon /> draft STL
            </a>
          ) : (
            <span className="small muted" title="Drag a slider: the 3D view shows a draft; Apply & verify runs the checks">
              {cz.nChanged ? "draft only — not verified yet" : `verified · it ${model.verified?.iteration ?? 0}`}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function Control({ p, disabled, children }: { p: Param; disabled: boolean; children?: ReactNode }) {
  if (p.options && p.options.length > 0) return <ChoiceControl p={p} disabled={disabled} />;
  if (p.type === "bool")
    return (
      <ToggleControl p={p} disabled={disabled}>
        {children}
      </ToggleControl>
    );
  if (p.type === "number") return <NumberControl p={p} disabled={disabled} />;
  return <TextControl p={p} disabled={disabled} />;
}

// ---- status strip ------------------------------------------------------------------------------------------------

function StatusStrip() {
  const cz = useCustomizer();
  const pv = cz.preview;
  const fn = cz.model?.draft_fn ?? 32;
  if (pv.status === "running" || pv.status === "queued")
    return (
      <div className="cz-status">
        <Spinner size={11} /> <span>compiling the draft preview…</span>
      </div>
    );
  if (pv.status === "error")
    return (
      <div className="cz-status tone-fail">
        <span className="cz-status-dot" />
        <div className="stack-tight">
          {pv.asserts.length ? pv.asserts.map((m, i) => <div key={i}>{m}</div>) : <div>{pv.errors[0] || "preview failed"}</div>}
          {pv.stale && <div className="dim small">changed since — {cz.autoPreview && !cz.paused ? "recompiling" : <button className="link" onClick={cz.previewNow}>preview again</button>}</div>}
        </div>
      </div>
    );
  if (cz.paused && cz.nChanged > 0)
    return (
      <div className="cz-status tone-warn">
        <span className="cz-status-dot" />
        <span>
          previews take ~{fmt(pv.avgS ?? pv.durationS ?? SLOW_PREVIEW_S, 0)} s for this model, so they wait for you
        </span>
        <span className="grow" />
        <button className="btn btn-xs" onClick={cz.previewNow}>
          Preview now
        </button>
      </div>
    );
  if (pv.status === "ok")
    return (
      <div className={`cz-status ${pv.stale ? "tone-warn" : "tone-pass"}`}>
        <span className="cz-status-dot" />
        <span>
          draft preview · {fmt(pv.durationS ?? 0, pv.durationS && pv.durationS < 1 ? 2 : 1)} s{pv.quality === "draft" ? ` · $fn ${fn}` : " · full facets"}
          {pv.stale && (cz.autoPreview ? " · updating…" : " · out of date")}
        </span>
        <span className="grow" />
        {!cz.autoPreview && pv.stale && (
          <button className="btn btn-xs" onClick={cz.previewNow}>
            Preview
          </button>
        )}
        {cz.viewMode === "verified" && cz.hasDraft && (
          <button className="link" onClick={() => cz.setViewMode("draft")}>
            show in 3D
          </button>
        )}
      </div>
    );
  if (!cz.autoPreview && cz.nChanged > 0)
    return (
      <div className="cz-status">
        <span>auto-preview is off</span>
        <span className="grow" />
        <button className="btn btn-xs" onClick={cz.previewNow}>
          Preview
        </button>
      </div>
    );
  return (
    <div className="cz-status dim">
      <span>Drag a slider or type a value — the 3D view shows a draft at once. Apply &amp; verify re-runs the checks and the drawings.</span>
    </div>
  );
}

// ---- computed values -------------------------------------------------------------------------------------------------

function ComputedPanel() {
  const cz = useCustomizer();
  const model = cz.model!;
  const live = cz.preview.status === "ok" && cz.hasDraft;
  const echo = live ? cz.preview.echo : {};
  const rows = model.derived.filter((d) => d.echoed);
  if (!rows.length) return null;
  const lengthLike = (name: string) => !/(_n|_count|angle|_deg|factor|ratio|_kg|_mpa)$/i.test(name);
  return (
    <section className="cz-group cz-computed">
      <div className="cz-group-title">
        <span>Computed</span>
        <span className="cz-group-count">{live ? "from the draft" : `verified it ${model.verified?.iteration ?? 0}`}</span>
      </div>
      <div className="cz-derived">
        {rows.map((d) => {
          const v = d.name in echo ? echo[d.name] : d.value;
          const num = typeof v === "number";
          const len = lengthLike(d.name);
          const show = (x: number) => (len && cz.units === "in" ? `${fmt(x / 25.4, 3)} in` : `${fmt(x, 2)}${len ? " mm" : ""}`);
          const shown = num ? show(v as number) : v == null ? "—" : JSON.stringify(v);
          const b = d.binding;
          const lim: string[] = [];
          let bad = false;
          if (b) {
            if (typeof b.min === "number") {
              lim.push(`≥ ${show(b.min)}`);
              if (num && (v as number) < b.min - 1e-9) bad = true;
            }
            if (typeof b.max === "number") {
              lim.push(`≤ ${show(b.max)}`);
              if (num && (v as number) > b.max + 1e-9) bad = true;
            }
          }
          const title = [d.expr ? `${d.name} = ${d.expr}` : d.name, b ? `spec ${b.dim}${lim.length ? ` (${lim.join(", ")})` : ""}` : "", bad ? "outside the spec's limit — the check will fail" : ""].filter(Boolean).join("\n");
          return (
            <div className={`cz-derived-row${bad ? " bad" : ""}`} key={d.name} title={title}>
              <span className="mono">{d.name}</span>
              {d.expr && <span className="cz-formula mono dim">= {d.expr}</span>}
              {lim.length > 0 && (
                <span className="cz-derived-lim num">
                  {bad && <Cross size={10} />} {lim.join(" ")}
                </span>
              )}
              <span className="num cz-derived-val">{shown}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ---- presets -----------------------------------------------------------------------------------------------------------

function PresetsMenu() {
  const cz = useCustomizer();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const box = useRef<HTMLDivElement>(null);
  useDismiss(open, useCallback(() => setOpen(false), []), box);
  const names = Object.keys(cz.presets).sort((a, b) => a.localeCompare(b));
  const save = async () => {
    const n = name.trim();
    if (!n) return;
    await cz.savePreset(n);
    setName("");
  };
  return (
    <div className="cz-menu" ref={box}>
      <button className={`btn btn-xs btn-ghost${open ? " active" : ""}`} onClick={() => setOpen((v) => !v)} title="Presets — named parameter sets (also readable by OpenSCAD's own customizer)" aria-label="presets" aria-expanded={open}>
        <StarIcon /> {names.length ? names.length : ""}
      </button>
      {open && (
        <div className="popover cz-presets">
          <h3>Presets</h3>
          <div className="cz-preset-list">
            <button className="cz-preset" onClick={() => { cz.resetAll(); setOpen(false); }} disabled={!cz.nChanged}>
              <span>Verified values (it {cz.model?.verified?.iteration ?? 0})</span>
              <span className="dim small">reset</span>
            </button>
            {names.map((n) => {
              const pv = cz.presets[n];
              const diff = Object.entries(pv).filter(([k, v]) => k in cz.verified && JSON.stringify(v) !== JSON.stringify(cz.verified[k])).length;
              return (
                <div className="cz-preset-row" key={n}>
                  <button className="cz-preset" onClick={() => { cz.applyPreset(n); setOpen(false); }} title={Object.entries(pv).map(([k, v]) => `${k} = ${JSON.stringify(v)}`).join("\n")}>
                    <span>{n}</span>
                    <span className="dim small">{diff ? `${diff} differ` : "same as verified"}</span>
                  </button>
                  <button className="btn btn-xs btn-quiet-danger" onClick={() => cz.deletePreset(n)} title={`Delete preset “${n}”`} aria-label={`delete preset ${n}`}>
                    <Close size={12} />
                  </button>
                </div>
              );
            })}
            {!names.length && <div className="small dim">No presets yet. Save the current values under a name — they are stored next to part.scad in OpenSCAD's parameter-set format, so the desktop customizer sees them too.</div>}
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Save current values as…" onKeyDown={(e) => e.key === "Enter" && save()} aria-label="preset name" />
            <button className="btn btn-sm" onClick={save} disabled={!name.trim()}>
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---- more menu ---------------------------------------------------------------------------------------------------------------

function MoreMenu() {
  const cz = useCustomizer();
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useDismiss(open, useCallback(() => setOpen(false), []), box);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(cz.command);
      toast("OpenSCAD command copied", "pass");
    } catch {
      toast(cz.command, "info");
    }
  };
  const model = cz.model!;
  const summary = useMemo(() => {
    const out: string[] = [];
    for (const p of model.params) {
      if (!cz.isChanged(p.name)) continue;
      const v = cz.valueOf(p);
      out.push(`${p.label || p.name}: ${fmtValue(p, cz.verified[p.name], cz.units)} → ${typeof v === "number" ? fmtValue(p, v, cz.units) : String(v)}`);
    }
    return out;
  }, [model, cz]);
  return (
    <div className="cz-menu" ref={box}>
      <button className={`btn btn-xs btn-ghost${open ? " active" : ""}`} onClick={() => setOpen((v) => !v)} title="Preview options, export" aria-label="more" aria-expanded={open}>
        <More size={14} />
      </button>
      {open && (
        <div className="popover cz-more">
          <h3>Preview</h3>
          <label className="cz-more-row">
            <span>Auto-preview while editing</span>
            <button type="button" role="switch" aria-checked={cz.autoPreview} className={`switch${cz.autoPreview ? " on" : ""}`} onClick={() => cz.setAutoPreview(!cz.autoPreview)}>
              <span className="switch-knob" />
            </button>
          </label>
          <div className="cz-more-row">
            <span>Facets</span>
            <div className="seg">
              <button className={`seg-btn${cz.quality === "auto" ? " active" : ""}`} onClick={() => cz.setQuality("auto")} title="full facets while previews are quick; coarse facets once a full preview took more than a couple of seconds">
                auto
              </button>
              <button className={`seg-btn${cz.quality === "draft" ? " active" : ""}`} onClick={() => cz.setQuality("draft")} title={`$fn ${model.draft_fn}: fast, coarse facets`}>
                draft
              </button>
              <button className={`seg-btn${cz.quality === "full" ? " active" : ""}`} onClick={() => cz.setQuality("full")} title="the model's own facet count (slower)">
                full
              </button>
            </div>
          </div>
          <div className="small dim">
            next preview: {cz.effectiveQuality === "draft" ? `draft ($fn ${model.draft_fn})` : "full facets"}
            {cz.preview.avgS != null ? ` · average ${fmt(cz.preview.avgS, 1)} s` : ""}
          </div>
          <h3 style={{ marginTop: 10 }}>Changes</h3>
          {summary.length ? (
            <ul className="cz-changes">
              {summary.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          ) : (
            <div className="small dim">none — every value is the verified one</div>
          )}
          <h3 style={{ marginTop: 10 }}>Take it elsewhere</h3>
          <div className="stack-tight">
            <button className="btn btn-sm" onClick={copy} title={cz.command}>
              Copy the OpenSCAD command line
            </button>
            {cz.draftDownloadUrl && (
              <a className="btn btn-sm" href={cz.draftDownloadUrl} download={`${(model.part_name || "part").replace(/[^\w.-]+/g, "_")}-draft.stl`}>
                Download the draft STL
              </a>
            )}
            <div className="small dim">Presets are written to <code>part.json</code> next to <code>part.scad</code> — OpenSCAD's desktop customizer opens them as parameter sets.</div>
          </div>
          {cz.units === "in" && <div className="small dim" style={{ marginTop: 6 }}>Showing inches; the model itself stays in millimetres (1 in = 25.4 mm).</div>}
        </div>
      )}
    </div>
  );
}

// ---- icons ---------------------------------------------------------------------------------------------------------------------

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
function SearchIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}
function StarIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
      <path d="m12 3 2.8 5.9 6.4.8-4.7 4.4 1.2 6.4L12 17.4 6.3 20.5l1.2-6.4L2.8 9.7l6.4-.8L12 3z" />
    </svg>
  );
}
function CheckIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="m4 12.5 5 5L20 6.5" />
    </svg>
  );
}
function DownloadIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 4v11m0 0 4-4m-4 4-4-4M4 19h16" />
    </svg>
  );
}
