import { useEffect, useMemo, useState } from "react";
import { fileUrl, kin } from "../api";

const S = (sid: string) => `/api/sessions/${encodeURIComponent(sid)}`;
import EvidenceMap from "../components/EvidenceMap";
import ImageZoom from "../components/ImageZoom";
import StlViewer from "../components/StlViewer";
import { useCustomizer } from "../customizer/context";
import { Sliders } from "../icons";
import { useLocal } from "../hooks";
import { iterPath, useSession } from "../pages/session-context";
import { useToast } from "../toast";
import type { EvidenceGraph } from "../types";
import { Pill, Spinner } from "../ui";

type Tab = "3d" | "views" | "sections" | "view" | "evidence";

export default function CenterPane() {
  const s = useSession();
  const cz = useCustomizer();
  const { toast, error } = useToast();
  const d = s.detail!;
  const [tab, setTab] = useLocal<Tab>("kin.center.tab", "3d");
  const [view, setView] = useState<string>("");
  const [branching, setBranching] = useState(false);
  const [ev, setEv] = useState<EvidenceGraph | null>(null);
  const evKey = `${d.spec_yaml.length}:${d.photos.length}:${d.meta.iteration}`;
  useEffect(() => {
    if (tab !== "evidence") return;
    let alive = true;
    kin
      .evidence(s.sid)
      .then((g) => alive && setEv(g))
      .catch(() => alive && setEv(null));
    return () => {
      alive = false;
    };
  }, [tab, s.sid, evKey]);

  const it = s.selectedIter;
  const isLatest = !it || !s.latestIter || it.iteration === s.latestIter.iteration;
  const n = it?.iteration;

  // STL: the selected iteration's own mesh, else (latest) the session's part.stl (last successful compile)
  const stlUrl = useMemo(() => {
    if (it && it.stl) return fileUrl(s.sid, it.stl, it.iteration);
    if (isLatest && d.stl) return fileUrl(s.sid, d.stl, s.stlVersion);
    return null;
  }, [it, isLatest, d.stl, s.sid, s.stlVersion]);
  const stlNote = it && !it.stl && isLatest && d.stl ? `iteration ${it.iteration} did not compile — showing the last compiled mesh` : null;

  // the customizer's draft mesh replaces the verified one while there are unapplied edits (only on the latest iteration)
  const draftShown = isLatest && cz.hasDraft && cz.viewMode === "draft" && !!cz.preview.url;
  const shownUrl = draftShown ? cz.preview.url : stlUrl;
  const ghostUrl = draftShown && stlUrl && cz.renderTarget === "part" ? stlUrl : null;
  const contextUrl = (d.spec.context?.length || 0) > 0 && (cz.renderTarget !== "coupon" || !draftShown) ? `${S(s.sid)}/context.stl?v=${d.spec_yaml.length}` : null;
  const openCustomizer = () => window.dispatchEvent(new CustomEvent("kin:right-tab", { detail: "params" }));
  const targets = cz.model?.render_targets || null;
  const pv = cz.preview;
  const draftOverlay =
    isLatest && cz.model?.available ? (
      <div className="viewer-pills">
        {draftShown && (
          <span className="pill pill-blue" title="A quick compile of the current slider values — the checks have not run on it. Apply & verify for a checked iteration.">
            <span className="pill-dot" /> draft · {cz.nChanged ? `${cz.nChanged} change${cz.nChanged === 1 ? "" : "s"}` : cz.renderTarget} · {(pv.durationS ?? 0).toFixed(pv.durationS && pv.durationS < 1 ? 2 : 1)} s
            {pv.stale ? " · updating…" : ""}
          </span>
        )}
        {(pv.status === "running" || pv.status === "queued") && (
          <span className="pill pill-neutral">
            <Spinner size={10} /> compiling preview…
          </span>
        )}
        {pv.status === "error" && (
          <span className="pill pill-fail" title={(pv.asserts.length ? pv.asserts : pv.errors).join("\n")}>
            preview failed: {(pv.asserts[0] || pv.errors[0] || "").slice(0, 80)}
          </span>
        )}
        {cz.hasDraft && (
          <div className="seg seg-xs" role="tablist" aria-label="Mesh shown">
            <button role="tab" aria-selected={cz.viewMode === "verified"} className={`seg-btn${cz.viewMode === "verified" ? " active" : ""}`} onClick={() => cz.setViewMode("verified")} title="The last verified iteration">
              verified
            </button>
            <button role="tab" aria-selected={cz.viewMode === "draft"} className={`seg-btn${cz.viewMode === "draft" ? " active" : ""}`} onClick={() => cz.setViewMode("draft")} title="The current slider values (not checked yet)">
              draft
            </button>
          </div>
        )}
        {draftShown && cz.nChanged > 0 && (
          <button className="btn btn-xs btn-primary" onClick={() => cz.apply()} disabled={cz.applying || s.running || !!s.busy} title="Rewrite part.scad with these values and run the checks">
            {cz.applying ? <Spinner size={10} /> : null} Apply &amp; verify
          </button>
        )}
        {!draftShown && cz.nChanged === 0 && d.stl && (
          <button className="btn btn-xs" onClick={openCustomizer} title="Sliders and switches for every parameter">
            <Sliders size={12} /> Customize
          </button>
        )}
      </div>
    ) : null;

  const sheetUrl = it?.sheet ? fileUrl(s.sid, it.sheet, it.iteration) : null;
  const sectionsUrl = it?.sections ? fileUrl(s.sid, it.sections, it.iteration) : null;
  const views = it?.views || [];
  const viewUrl = it && view && views.includes(view) ? fileUrl(s.sid, iterPath(it.iteration, `sheets/views/${view}`), it.iteration) : null;

  useEffect(() => {
    // keep the picked view valid when the iteration changes
    if (view && !views.includes(view)) {
      const same = views.find((v) => v.replace(/^iter_\d+_/, "") === view.replace(/^iter_\d+_/, ""));
      setView(same || "");
      if (!same && tab === "view") setTab("views");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [views.join("|")]);

  const branch = async () => {
    if (!it) return;
    if (!window.confirm(`Restore part.scad from iteration ${it.iteration}? The current code is kept in the history.`)) return;
    setBranching(true);
    try {
      await kin.branch(s.sid, it.iteration);
      toast(`Branched from iteration ${it.iteration} — part.scad restored`, "pass");
      await s.refresh();
      s.setSelected(null);
    } catch (e) {
      error(e, "Branch failed");
    } finally {
      setBranching(false);
    }
  };

  const viewLabel = (name: string) => name.replace(/^iter_\d+_/, "").replace(/\.png$/, "").replace(/_/g, " ");

  return (
    <div className="pane">
      <div className="center-head">
        <div className="tabs" role="tablist" aria-label="Viewer">
          <button role="tab" aria-selected={tab === "3d"} className={`tab${tab === "3d" ? " active" : ""}`} onClick={() => setTab("3d")}>
            3D
          </button>
          <button role="tab" aria-selected={tab === "views"} className={`tab${tab === "views" ? " active" : ""}`} onClick={() => setTab("views")}>
            Views
          </button>
          <button
            role="tab"
            aria-selected={tab === "sections"}
            className={`tab${tab === "sections" ? " active" : ""}`}
            onClick={() => setTab("sections")}
          >
            Sections
          </button>
          <button role="tab" aria-selected={tab === "evidence"} className={`tab${tab === "evidence" ? " active" : ""}`} onClick={() => setTab("evidence")} title="what each dimension is known from">
            Evidence
          </button>
        </div>
        <div className="view-picker">
          {tab === "3d" && targets && targets.length > 1 && isLatest && (
            <div className="seg seg-xs" role="tablist" aria-label="Render target" title="Which top-level object to preview: the part, the fit coupon or the assembly with its context">
              {targets.map((t) => (
                <button key={t} role="tab" aria-selected={cz.renderTarget === t} className={`seg-btn${cz.renderTarget === t ? " active" : ""}`} onClick={() => cz.setRenderTarget(t)}>
                  {t}
                </button>
              ))}
            </div>
          )}
          {n !== undefined && (
            <span className="small muted num nowrap">
              it {n}
              {isLatest ? "" : " (past)"}
            </span>
          )}
          <select
            className="select"
            value={tab === "view" ? view : ""}
            onChange={(e) => {
              const v = e.target.value;
              setView(v);
              setTab(v ? "view" : "views");
            }}
            disabled={views.length === 0}
            aria-label="Single view"
            title="Open one rendered view"
          >
            <option value="">{views.length ? "Single view…" : "No views yet"}</option>
            {views.map((v) => (
              <option key={v} value={v}>
                {viewLabel(v)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="center-body">
        {tab === "3d" && (
          <>
            <StlViewer
              url={shownUrl}
              ghostUrl={ghostUrl}
              ghostLabel="Ghost the verified mesh behind the draft"
              contextUrl={contextUrl}
              contextOn={draftShown && cz.renderTarget === "assembly"}
              overlay={draftOverlay}
              units={cz.units}
              placeholder="The 3D model appears here after the first iteration compiles. Run the designer, apply params or run code to create one."
            />
            {stlNote && (
              <div style={{ position: "absolute", left: 10, top: 8 }}>
                <Pill tone="warn">{stlNote}</Pill>
              </div>
            )}
          </>
        )}
        {tab === "views" && <ImageZoom src={sheetUrl} alt={`Views sheet, iteration ${n ?? ""}`} placeholder="The annotated views sheet (top, iso, front, right…) is rendered after each iteration compiles." />}
        {tab === "sections" && (
          <ImageZoom src={sectionsUrl} alt={`Sections sheet, iteration ${n ?? ""}`} placeholder="Sections through each measured plane, with the assembly ghost, appear here after the first iteration." />
        )}
        {tab === "view" && <ImageZoom src={viewUrl} alt={`View ${view}`} placeholder="Pick a single view from the menu above." />}
        {tab === "evidence" && (
          <div className="evidence-full">
            {ev ? (
              <>
                <EvidenceMap graph={ev} />
                <div className="small dim" style={{ padding: "6px 10px" }}>
                  Sources on the left (photos, ruler readings, recognised standards, open requests) → the estimates they produced → the spec's
                  dimensions → the checks that verify them on the designed mesh. Green = confirmed / passing, amber = estimated, red = unknown or
                  failing; thicker lines are more trusted sources, dashed lines are requests still open.
                </div>
              </>
            ) : (
              <div className="small dim" style={{ padding: 20 }}>Loading the evidence graph…</div>
            )}
          </div>
        )}
      </div>

      <div className="center-foot">
        <span className="label">Iterations</span>
        {d.iterations.length === 0 ? (
          <span className="small muted">none yet</span>
        ) : (
          <div className="chips" role="tablist" aria-label="Iterations">
            {d.iterations.map((x) => (
              <button
                key={x.iteration}
                role="tab"
                aria-selected={x.iteration === n}
                className={`chip ${x.ok ? "pass" : "fail"}${x.iteration === n ? " active" : ""}`}
                onClick={() => s.setSelected(x.iteration === s.latestIter?.iteration ? null : x.iteration)}
                title={`${x.label || "iteration " + x.iteration}${x.failures.length ? "\nfailing: " + x.failures.join(", ") : ""}${x.compile_ok ? "" : "\ncompile error"}`}
              >
                it {x.iteration}
              </button>
            ))}
          </div>
        )}
        {it && it.label ? (
          <span className="small dim" style={{ flex: "1 1 0px", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textAlign: "right" }} title={it.label}>
            {it.label}
          </span>
        ) : (
          <span className="grow" />
        )}
        {!isLatest && (
          <>
            <button className="btn btn-xs" onClick={() => s.setSelected(null)}>
              Latest
            </button>
            <button className="btn btn-xs btn-primary" onClick={branch} disabled={branching || s.running || !!s.busy} title="Restore this iteration's part.scad as the working copy">
              {branching ? <Spinner size={10} /> : null} Branch from here
            </button>
          </>
        )}
      </div>
    </div>
  );
}
