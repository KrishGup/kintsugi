import { useEffect, useRef, useState } from "react";
import { kin } from "../api";
import { hoverProps } from "../hover";
import CodeEditor from "../components/CodeEditor";
import { useSession } from "../pages/session-context";
import { useToast } from "../toast";
import type { Dim } from "../types";
import { Pill, Spinner, fmtNum, type Tone } from "../ui";

function dimText(d: Dim): string {
  if (typeof d.target === "number") return `${fmtNum(d.target)} ±${fmtNum(d.tol ?? 0.3)} ${d.unit || "mm"}`;
  const parts: string[] = [];
  if (typeof d.min === "number") parts.push(`≥ ${fmtNum(d.min)}`);
  if (typeof d.max === "number") parts.push(`≤ ${fmtNum(d.max)}`);
  return parts.length ? `${parts.join(" ")} ${d.unit || "mm"}` : "unspecified";
}

function statusOf(d: Dim): { tone: Tone; label: string } {
  switch (d.status) {
    case "confirmed":
      return { tone: "pass", label: "confirmed" };
    case "estimated":
      return { tone: "warn", label: "estimated" };
    default:
      return { tone: "fail", label: "unknown" };
  }
}

export default function SpecTab() {
  const s = useSession();
  const { toast, error } = useToast();
  const d = s.detail!;
  const remote = d.spec_yaml || "";
  const [text, setText] = useState(remote);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [stale, setStale] = useState(false);
  const lastRemote = useRef(remote);

  useEffect(() => {
    if (remote === lastRemote.current) return;
    lastRemote.current = remote;
    if (!dirty) {
      setText(remote);
      setStale(false);
    } else setStale(true);
  }, [remote, dirty]);

  const save = async () => {
    setSaving(true);
    try {
      await kin.updateSpec(s.sid, text);
      toast("Spec saved", "pass");
      setDirty(false);
      setStale(false);
      lastRemote.current = text;
      await s.refresh();
    } catch (e) {
      error(e, "Spec rejected");
    } finally {
      setSaving(false);
    }
  };

  const interfaces = d.spec.interfaces || [];
  const reqs = d.spec.requirements || [];

  return (
    <div className="spec-split">
      <div className="editor-wrap spec-editor">
        <div className="editor-bar">
          <span className="mono small">spec.yaml</span>
          {dirty && <Pill tone="warn">modified</Pill>}
          {d.unconfirmed.length > 0 ? (
            <span className="hover-anchor">
              <Pill tone="fail">{d.unconfirmed.length} unconfirmed</Pill>
              <span className="hover-card below" role="tooltip">
                {d.unconfirmed.map((u) => (
                  <span key={u} className="mono">
                    {u}
                  </span>
                ))}
              </span>
            </span>
          ) : (
            <Pill tone="pass">fit confirmed</Pill>
          )}
          <span className="grow" />
          <button
            className="btn btn-ghost btn-xs"
            onClick={() => {
              setText(remote);
              setDirty(false);
              setStale(false);
            }}
            disabled={!dirty}
          >
            Revert
          </button>
          <button className="btn btn-primary btn-sm" onClick={save} disabled={saving || !dirty}>
            {saving ? <Spinner size={14} /> : null} Save
          </button>
        </div>
        {stale && (
          <div className="editor-note">
            <span>spec.yaml changed on the server while you were editing.</span>
            <button
              className="btn btn-xs"
              onClick={() => {
                setText(remote);
                setDirty(false);
                setStale(false);
              }}
            >
              Reload
            </button>
          </div>
        )}
        <div className="editor-body">
          <CodeEditor
            value={text}
            onChange={(v) => {
              setText(v);
              setDirty(v !== lastRemote.current);
            }}
            language="yaml"
          />
        </div>
      </div>

      <div className="spec-dims">
        <div className="section-title">Interface dimensions</div>
        {interfaces.length === 0 ? (
          <div className="small muted">No interfaces in the spec yet. Interfaces describe the geometry the part must mate with (a bore, a boss, a slot…).</div>
        ) : (
          <div className="dim-list">
            {interfaces.flatMap((itf) =>
              Object.entries(itf.dims || {}).map(([k, dim]) => {
                const st = statusOf(dim);
                const q = `${itf.id}.${k}`;
                const ests = dim.estimates || [];
                const best = ests.length ? ests[ests.length - 1] : null;
                return (
                  <div className="dim-item" key={q}>
                    <div className="dim-head">
                      <span className="dim-name" {...hoverProps(q)}>
                        <span className="itf">{itf.id}.</span>
                        {k}
                      </span>
                      <Pill tone={st.tone}>{st.label}</Pill>
                    </div>
                    <div className="small dim">
                      <span className="dim-spec">{dimText(dim)}</span> · {itf.type || "custom"} · {itf.fit || "sliding"} fit
                      {typeof itf.clearance === "number" ? ` · clearance ${itf.clearance}` : ""}
                      {dim.measure?.recipe && dim.measure.recipe !== "none" ? ` · ${dim.measure.recipe}` : ""}
                      {ests.length > 0 && best
                        ? ` · ${ests.length} estimate${ests.length === 1 ? "" : "s"}, latest ${fmtNum(best.value)} from ${best.source}${typeof best.conf === "number" ? ` (${Math.round(best.conf * 100)}%)` : ""}`
                        : " · no estimates yet"}
                    </div>
                    <ConfirmForm dim={q} initial={typeof dim.target === "number" ? dim.target : typeof dim.min === "number" ? dim.min : undefined} />
                  </div>
                );
              }),
            )}
          </div>
        )}
        {reqs.some((r) => r.derived && Object.keys(r.derived).length) && (
          <>
            <div className="section-title">Requirement-derived dimensions</div>
            <table className="table table-flush">
              <thead>
                <tr>
                  <th>Dimension</th>
                  <th className="num">Spec</th>
                  <th>Recipe</th>
                </tr>
              </thead>
              <tbody>
                {reqs.flatMap((r) =>
                  Object.entries(r.derived || {}).map(([k, dim]) => (
                    <tr key={`${r.id}.${k}`}>
                      <td>
                        <div className="dim-name">
                          <span className="itf">{r.id}.</span>
                          {k}
                        </div>
                        <div className="small dim">{r.text}</div>
                      </td>
                      <td className="num">{dimText(dim)}</td>
                      <td className="mono small">{dim.measure?.recipe || "—"}</td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          </>
        )}
        {d.spec.open_questions && d.spec.open_questions.length > 0 && (
          <>
            <div className="section-title">Open questions</div>
            <ul className="small" style={{ margin: 0, paddingLeft: 23 }}>
              {d.spec.open_questions.map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}

function ConfirmForm({ dim, initial }: { dim: string; initial?: number }) {
  const s = useSession();
  const { toast, error } = useToast();
  const [value, setValue] = useState<string>(initial !== undefined ? String(initial) : "");
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState("user_caliper");

  useEffect(() => {
    if (initial !== undefined) setValue(String(initial));
  }, [initial]);

  const go = async () => {
    const v = Number(value);
    if (!Number.isFinite(v)) {
      toast("Enter a number", "warn");
      return;
    }
    setBusy(true);
    try {
      const r = await kin.confirm(s.sid, dim, v, source);
      toast(`${dim} confirmed at ${v} mm${r.unconfirmed.length ? ` · ${r.unconfirmed.length} still unconfirmed` : " · all interface dims confirmed"}`, "pass");
      await s.refresh();
    } catch (e) {
      error(e, "Could not confirm");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="confirm-form">
      <input
        type="number"
        className="input input-num"
        step={0.01}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") go();
        }}
        aria-label={`Confirmed value for ${dim}`}
        placeholder="mm"
      />
      <select className="select" value={source} onChange={(e) => setSource(e.target.value)} aria-label="Measurement source" style={{ width: 120, padding: "4px 26px 4px 8px", fontSize: 14.5 }}>
        <option value="user_caliper">caliper</option>
        <option value="user_ruler">ruler</option>
        <option value="user_stated">stated</option>
      </select>
      <button className="btn btn-xs" onClick={go} disabled={busy || !value}>
        {busy ? <Spinner size={13} /> : "Confirm"}
      </button>
    </div>
  );
}
