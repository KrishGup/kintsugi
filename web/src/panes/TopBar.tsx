import { useCallback, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { fileUrl, kin } from "../api";
import { useDismiss } from "../hooks";
import { ProviderPill, useLlm } from "../llm";
import { Mark } from "../pages/Home";
import { useSession } from "../pages/session-context";
import { fmtElapsed, useRunProgress } from "../progress";
import { useToast } from "../toast";
import { Pill, Spinner, statusLabel, statusTone } from "../ui";

type Pop = "run" | "coupon" | "export" | null;

export default function TopBar() {
  const s = useSession();
  const { toast, error } = useToast();
  const d = s.detail!;
  const [pop, setPop] = useState<Pop>(null);
  const ref = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setPop(null), []);
  useDismiss(pop !== null, close, ref);

  // run popover
  const [message, setMessage] = useState("");
  const [strategy, setStrategy] = useState("");
  const [budget, setBudget] = useState(8);
  const [rounds, setRounds] = useState(2);

  const status = s.running ? "running" : d.meta.status;
  const waiting = d.meta.status === "waiting_user" && !s.running;
  const llm = useLlm();
  const p = useRunProgress(s.events, s.running);

  const onRun = async () => {
    if (!llm.ready) {
      llm.openSettings();
      return;
    }
    const ok = await s.startRun({
      message: message.trim() || undefined,
      strategy: strategy.trim() || undefined,
      budget: Math.max(1, Math.min(30, budget || 8)),
      critic_rounds: Math.max(0, Math.min(6, rounds ?? 2)),
    });
    if (ok) {
      setMessage("");
      setPop(null);
    }
  };

  const onExport = async () => {
    const r = await s.runBusy("Exporting bundle…", async () => {
      try {
        const res = await kin.export(s.sid);
        toast(`Exported iteration ${res.iteration}`, "pass");
        await s.refresh();
        return res;
      } catch (e) {
        error(e, "Export failed");
        return undefined;
      }
    });
    return r;
  };

  return (
    <div className="topbar" ref={ref}>
      <Link to="/" className="brand" title="All sessions">
        <span className="brand-mark">
          <Mark />
        </span>
        <span className="brand-name">Kintsugi</span>
      </Link>
      <span className="topbar-sep" />
      <div className="topbar-title">
        <h1 title={d.meta.id}>{d.meta.name}</h1>
        <span className="topbar-iter">
          iteration <b>{d.meta.iteration ?? 0}</b>
          {d.meta.critic_rounds ? (
            <>
              {" "}
              · critic <b>{d.meta.critic_rounds}</b>
            </>
          ) : null}
          {typeof d.meta.cost_usd === "number" && d.meta.cost_usd > 0 ? (
            <>
              {" "}
              · <b title="model spend so far, from the API's token counts">${d.meta.cost_usd.toFixed(2)}</b>
            </>
          ) : null}
        </span>
        <Pill tone={statusTone(status, s.running)} dot={s.running} title={`status: ${d.meta.status}`}>
          {statusLabel(status, s.running)}
        </Pill>
        {s.running && (
          <span className="topbar-progress num" title="iterations used / budget · model steps · elapsed">
            it {p.iterations}
            {p.budget ? `/${p.budget}` : ""} · step {p.step} · {fmtElapsed(p.elapsed)}
          </span>
        )}
        {!s.connected && (
          <Pill tone="warn" title="Event stream disconnected; reconnecting">
            offline
          </Pill>
        )}
        {s.busy && <Spinner size={12} label={s.busy} />}
      </div>

      <div className="topbar-provider">
        <ProviderPill />
      </div>

      <div className="topbar-actions">
        <div className="popover-anchor">
          <button
            className="btn btn-primary btn-sm"
            onClick={() => setPop(pop === "run" ? null : "run")}
            disabled={s.running}
            aria-expanded={pop === "run"}
            title={s.running ? "A run is in progress" : "Start the designer agent"}
          >
            <PlayIcon /> Run designer
          </button>
          {pop === "run" && (
            <div className="popover" role="dialog" aria-label="Run designer">
              <h3>Run designer</h3>
              {waiting && (
                <div className="banner banner-warn mb">The designer is waiting for your answer — reply in the chat to resume. Starting here begins a fresh run.</div>
              )}
              <div className="stack">
                <label className="field">
                  <span className="field-label">Message (optional)</span>
                  <textarea
                    className="textarea"
                    rows={3}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder="Notes for the designer, e.g. keep the loop in the XY plane…"
                    autoFocus
                  />
                </label>
                <label className="field">
                  <span className="field-label">Strategy (optional)</span>
                  <input className="input" value={strategy} onChange={(e) => setStrategy(e.target.value)} placeholder="e.g. start from the ring_loop_handle template" />
                </label>
                <div className="row">
                  <label className="field grow">
                    <span className="field-label">Iteration budget</span>
                    <input className="input input-mono" type="number" min={1} max={30} value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
                  </label>
                  <label className="field grow">
                    <span className="field-label">Critic rounds</span>
                    <input className="input input-mono" type="number" min={0} max={6} value={rounds} onChange={(e) => setRounds(Number(e.target.value))} />
                  </label>
                </div>
                <div className="row">
                  <button className="btn btn-primary" onClick={onRun}>
                    Start
                  </button>
                  <button className="btn btn-ghost" onClick={() => setPop(null)}>
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
        <button className="btn btn-sm" onClick={s.stopRun} disabled={!s.running} title="Cancel the running designer">
          <StopIcon /> Stop
        </button>
        <span className="topbar-sep" />
        <div className="popover-anchor">
          <button className="btn btn-sm" onClick={() => setPop(pop === "coupon" ? null : "coupon")} aria-expanded={pop === "coupon"} disabled={!d.scad}>
            <CouponIcon /> Coupon
          </button>
          {pop === "coupon" && <CouponPopover onClose={close} />}
        </div>
        <div className="popover-anchor">
          <button className="btn btn-sm" onClick={() => setPop(pop === "export" ? null : "export")} aria-expanded={pop === "export"}>
            <ExportIcon /> Export
          </button>
          {pop === "export" && <ExportPopover onExport={onExport} />}
        </div>
      </div>
    </div>
  );
}

function CouponPopover({ onClose }: { onClose: () => void }) {
  const s = useSession();
  const { toast, error } = useToast();
  const d = s.detail!;
  const [file, setFile] = useState<string | null>(d.export.includes("coupon.stl") ? "export/coupon.stl" : null);
  const [compiling, setCompiling] = useState(false);
  const [applying, setApplying] = useState<number | null>(null);

  const p = d.params.find((x) => x.name === "clearance");
  const fromSpec = d.spec.interfaces?.find((i) => typeof i.clearance === "number")?.clearance;
  const current = typeof p?.value === "number" ? p.value : typeof fromSpec === "number" ? fromSpec : 0.25;
  const choices = [-0.2, 0, 0.2].map((delta) => Math.round((current + delta) * 100) / 100);

  const compile = async () => {
    setCompiling(true);
    try {
      const r = await kin.coupon(s.sid);
      setFile(r.file);
      toast("Coupon compiled", "pass");
      s.refresh();
    } catch (e) {
      error(e, "Coupon failed");
    } finally {
      setCompiling(false);
    }
  };

  const pick = async (clearance: number) => {
    setApplying(clearance);
    await s.runBusy(`Applying clearance ${clearance} mm…`, async () => {
      try {
        const r = await kin.couponResult(s.sid, clearance);
        const it = r.iteration;
        toast(
          `Clearance set to ${clearance} mm` +
            (r.confirmed.length ? ` — confirmed ${r.confirmed.join(", ")}` : "") +
            (it ? ` · iteration ${it.iteration} ${it.ok ? "passes" : "fails"}` : ""),
          it && !it.ok ? "warn" : "pass",
        );
        await s.refresh();
        onClose();
      } catch (e) {
        error(e, "Could not record the coupon result");
      } finally {
        setApplying(null);
      }
    });
  };

  return (
    <div className="popover" role="dialog" aria-label="Fit coupon">
      <h3>Fit coupon</h3>
      <p className="small dim" style={{ margin: "0 0 8px" }}>
        The coupon holds only the mating feature in three clearances (−0.2 / 0 / +0.2 mm). Print it flat, try each on the object, then tell
        Kintsugi which one slid on without force.
      </p>
      <div className="row mb">
        <button className="btn btn-sm" onClick={compile} disabled={compiling}>
          {compiling ? <Spinner size={11} /> : null} {file ? "Recompile" : "Compile coupon"}
        </button>
        {file && (
          <a className="btn btn-sm btn-primary" href={fileUrl(s.sid, file, Date.now())} download>
            Download coupon.stl
          </a>
        )}
      </div>
      <div className="label">Which one fit?</div>
      <div className="small dim">
        current clearance <span className="num">{current} mm</span>
      </div>
      <div className="coupon-choices">
        {choices.map((c, i) => (
          <button key={c} className={`btn${i === 1 ? " btn-primary" : ""}`} onClick={() => pick(c)} disabled={applying !== null}>
            {applying === c ? <Spinner size={11} /> : <span className="num">{c.toFixed(2)}</span>}
            <small>{i === 0 ? "tighter (−0.2)" : i === 1 ? "as designed" : "looser (+0.2)"}</small>
          </button>
        ))}
      </div>
      <div className="field-hint mt">Recording a result marks the interface dims confirmed and re-runs an iteration with the chosen clearance.</div>
    </div>
  );
}

function ExportPopover({ onExport }: { onExport: () => Promise<unknown> }) {
  const s = useSession();
  const d = s.detail!;
  const [working, setWorking] = useState(false);
  const canExport = d.iterations.some((i) => i.compile_ok);

  const go = async () => {
    setWorking(true);
    try {
      await onExport();
    } finally {
      setWorking(false);
    }
  };

  const order = ["bundle.zip", "part.stl", "part.3mf", "part.scad", "coupon.stl", "blueprint.pdf", "print_card.md", "spec.yaml", "checks.json", "session_log.md"];
  const files = [...d.export].sort((a, b) => {
    const ia = order.indexOf(a);
    const ib = order.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
  });

  return (
    <div className="popover" role="dialog" aria-label="Export">
      <h3>Export bundle</h3>
      {d.unconfirmed.length > 0 && (
        <div className="banner banner-warn mb">
          <span>
            <b>Fit unconfirmed:</b> {d.unconfirmed.join(", ")} {d.unconfirmed.length === 1 ? "was" : "were"} never confirmed by a measurement or
            a coupon. Print the coupon first, or confirm the dimension in the Spec tab.
          </span>
        </div>
      )}
      <div className="row mb">
        <button className="btn btn-primary btn-sm" onClick={go} disabled={working || !canExport} title={canExport ? "" : "Nothing compiled yet"}>
          {working ? <Spinner size={11} /> : <ExportIcon />} {d.export.length ? "Re-export" : "Export"} last passing iteration
        </button>
      </div>
      {typeof d.meta.exported_iteration === "number" && (
        <div className="small dim mb">
          Exported iteration <span className="num">{d.meta.exported_iteration}</span>
          {d.meta.exported_at ? ` · ${new Date(d.meta.exported_at * 1000).toLocaleString()}` : ""}
        </div>
      )}
      {files.length ? (
        <ul className="export-list">
          {files.map((f) => (
            <li key={f}>
              <a href={fileUrl(s.sid, `export/${f}`, d.meta.exported_at ?? Date.now())} download>
                {f}
              </a>
              {f === "bundle.zip" && <Pill tone="blue">everything</Pill>}
            </li>
          ))}
        </ul>
      ) : (
        <div className="small dim">STL / 3MF, customizer-ready .scad, blueprint PDF, print card, spec and session log — zipped.</div>
      )}
    </div>
  );
}

function PlayIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
      <path d="M6 4l14 8-14 8z" />
    </svg>
  );
}
function StopIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
      <rect x="5" y="5" width="14" height="14" rx="1" />
    </svg>
  );
}
function CouponIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="7" cy="12" r="3.5" />
      <circle cx="17" cy="12" r="3.5" />
    </svg>
  );
}
function ExportIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 16V4m0 0-4 4m4-4 4 4M4 15v4h16v-4" />
    </svg>
  );
}
