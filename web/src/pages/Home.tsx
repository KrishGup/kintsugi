import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { kin, sheetPdfUrl } from "../api";
import { useBusy } from "../hooks";
import { useToast } from "../toast";
import type { ExampleSpec, IntakeResult, SessionMeta } from "../types";
import { Empty, Pill, Spinner, relTime, statusLabel, statusTone } from "../ui";

type Mode = "spec" | "photos";

export default function Home() {
  const nav = useNavigate();
  const { toast, error } = useToast();
  const [sessions, setSessions] = useState<SessionMeta[] | null>(null);
  const [examples, setExamples] = useState<ExampleSpec[]>([]);
  const [health, setHealth] = useState<{ version: string; openscad?: string | null } | null>(null);
  const [mode, setMode] = useState<Mode>("spec");

  // new-part form
  const [name, setName] = useState("");
  const [example, setExample] = useState("");
  const [specYaml, setSpecYaml] = useState("");
  const [scad, setScad] = useState("");
  const [showScad, setShowScad] = useState(false);
  const [creating, create] = useBusy();

  // photo intake
  const [files, setFiles] = useState<File[]>([]);
  const [expectSheet, setExpectSheet] = useState(true);
  const [sentence, setSentence] = useState("");
  const [intakeStep, setIntakeStep] = useState<0 | 1 | 2 | 3 | 4>(0); // 0 idle, 1 creating, 2 uploading, 3 analyzing, 4 done
  const [intake, setIntake] = useState<IntakeResult | null>(null);
  const [intakeSid, setIntakeSid] = useState<string | null>(null);
  const [intakeSpecSaved, setIntakeSpecSaved] = useState("");
  const [intakeYaml, setIntakeYaml] = useState("");
  const [over, setOver] = useState(false);
  const [uploadedCount, setUploadedCount] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);

  const loadSessions = useCallback(async () => {
    try {
      setSessions(await kin.sessions());
    } catch (e) {
      error(e, "Could not list sessions");
      setSessions([]);
    }
  }, [error]);

  useEffect(() => {
    loadSessions();
    kin
      .examples()
      .then((ex) => {
        setExamples(ex);
        if (ex.length && !specYaml) {
          setExample(ex[0].name);
          setSpecYaml(ex[0].yaml);
        }
      })
      .catch((e) => error(e, "Could not load example specs"));
    kin.health().then(setHealth).catch(() => setHealth(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pickExample = (n: string) => {
    setExample(n);
    const ex = examples.find((e) => e.name === n);
    if (ex) {
      setSpecYaml(ex.yaml);
      if (!name) setName(ex.name.replace(/_/g, " "));
    }
  };

  const onCreate = async () => {
    const res = await create(async () => {
      try {
        const d = await kin.createSession({ name: name.trim() || undefined, spec_yaml: specYaml.trim() || undefined, scad: scad.trim() || undefined });
        toast(`Session “${d.meta.name}” created`, "pass");
        return d;
      } catch (e) {
        error(e, "Could not create session");
        return undefined;
      }
    });
    if (res) nav(`/s/${res.meta.id}`);
  };

  const addFiles = (list: FileList | File[] | null) => {
    if (!list) return;
    const imgs = Array.from(list).filter((f) => /^image\//.test(f.type) || /\.(jpe?g|png|webp)$/i.test(f.name));
    if (imgs.length) setFiles((fs) => [...fs, ...imgs]);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setOver(false);
    addFiles(e.dataTransfer.files);
  };

  const onAnalyze = async () => {
    if (!files.length) {
      toast("Add at least one photo first", "warn");
      return;
    }
    try {
      setIntake(null);
      setIntakeStep(1);
      let sid = intakeSid;
      if (!sid) {
        const d = await kin.createSession({ name: name.trim() || undefined });
        sid = d.meta.id;
        setIntakeSid(sid);
      }
      setIntakeStep(2);
      const up = await kin.uploadPhotos(sid, files, expectSheet);
      setUploadedCount((n) => n + up.length);
      setFiles([]);
      setIntakeStep(3);
      const res = await kin.intake(sid, sentence.trim());
      setIntake(res);
      if (res.spec_yaml) {
        setIntakeYaml(res.spec_yaml);
        setIntakeSpecSaved(res.spec_yaml);
      }
      setIntakeStep(4);
      toast("Intake complete — review the draft spec", "pass");
      loadSessions();
    } catch (e) {
      setIntakeStep(intake ? 4 : 0);
      error(e, "Intake failed");
    }
  };

  const onOpenIntake = async () => {
    if (!intakeSid) return;
    try {
      if (intakeYaml.trim() && intakeYaml !== intakeSpecSaved) {
        await kin.updateSpec(intakeSid, intakeYaml);
        toast("Spec saved", "pass");
      }
      nav(`/s/${intakeSid}`);
    } catch (e) {
      error(e, "Could not save spec");
    }
  };

  const onDelete = async (s: SessionMeta) => {
    if (!window.confirm(`Delete session “${s.name}” (${s.id})? This cannot be undone.`)) return;
    try {
      await kin.deleteSession(s.id);
      toast("Session deleted");
      loadSessions();
    } catch (e) {
      error(e, "Could not delete");
    }
  };

  const sorted = useMemo(() => (sessions ? [...sessions].sort((a, b) => (b.updated || b.created || 0) - (a.updated || a.created || 0)) : []), [sessions]);

  return (
    <div className="app">
      <header className="app-header">
        <Link to="/" className="brand">
          <span className="brand-mark">
            <Mark />
          </span>
          <span className="brand-name">Kintsugi</span>
        </Link>
        <span className="brand-tag">Photograph what broke. Print what fits.</span>
        <span className="header-spacer" />
        <a className="btn btn-sm" href={sheetPdfUrl} target="_blank" rel="noreferrer" title="Printable ArUco calibration sheet (letter)">
          <DownloadIcon /> Calibration sheet
        </a>
      </header>

      <main className="home">
        <div className="hero">
          <h1>Sessions</h1>
          <p>
            Each session turns a Part Spec into a verified, parametric OpenSCAD part. Start from an example spec, or photograph the broken
            object and let intake draft the spec for you.
          </p>
        </div>

        <div className="home-grid">
          <section className="panel">
            <div className="panel-head">
              <h2>Recent sessions</h2>
              <span className="grow" />
              <button className="btn btn-ghost btn-sm" onClick={loadSessions} title="Refresh">
                Refresh
              </button>
            </div>
            {sessions === null ? (
              <div className="panel-body">
                <Spinner label="Loading sessions…" />
              </div>
            ) : sorted.length === 0 ? (
              <div className="sessions-empty">
                <Empty title="No sessions yet">Create your first part on the right. Sessions are stored as folders on the server.</Empty>
              </div>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Status</th>
                    <th className="num">Iter.</th>
                    <th>Updated</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((s) => (
                    <tr key={s.id} className="table-row-link" onClick={() => nav(`/s/${s.id}`)}>
                      <td>
                        <Link to={`/s/${s.id}`} onClick={(e) => e.stopPropagation()}>
                          {s.name || s.id}
                        </Link>
                        <span className="sub mono">{s.id}</span>
                      </td>
                      <td>
                        <Pill tone={statusTone(s.status)} dot={s.status === "running"}>
                          {statusLabel(s.status)}
                        </Pill>
                      </td>
                      <td className="num">{s.iteration ?? 0}</td>
                      <td className="nowrap dim">{relTime(s.updated || s.created)}</td>
                      <td className="right">
                        <button
                          className="btn btn-ghost btn-xs btn-quiet-danger"
                          onClick={(e) => {
                            e.stopPropagation();
                            onDelete(s);
                          }}
                          title="Delete session"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {health && (
              <div className="panel-body health">
                kintsugi v{health.version}
                {health.openscad ? ` · openscad ${health.openscad}` : " · openscad not found"}
              </div>
            )}
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>New part</h2>
              <span className="grow" />
              <div className="mode-switch" role="tablist" aria-label="Start from">
                <button role="tab" aria-selected={mode === "spec"} className={mode === "spec" ? "active" : ""} onClick={() => setMode("spec")}>
                  From spec
                </button>
                <button
                  role="tab"
                  aria-selected={mode === "photos"}
                  className={mode === "photos" ? "active" : ""}
                  onClick={() => setMode("photos")}
                >
                  Photo intake
                </button>
              </div>
            </div>
            <div className="panel-body stack">
              <label className="field">
                <span className="field-label">Name</span>
                <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. bottle handle" />
              </label>

              {mode === "photos" && (
                <>
                  <div className="field">
                    <span className="field-label">Photos of the broken object</span>
                    <div
                      className={`file-drop${over ? " over" : ""}`}
                      onClick={() => fileInput.current?.click()}
                      onDragOver={(e) => {
                        e.preventDefault();
                        setOver(true);
                      }}
                      onDragLeave={() => setOver(false)}
                      onDrop={onDrop}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") fileInput.current?.click();
                      }}
                    >
                      Drop photos here or click to choose (JPG / PNG / WebP)
                      <input
                        ref={fileInput}
                        type="file"
                        accept="image/*"
                        multiple
                        hidden
                        onChange={(e) => {
                          addFiles(e.target.files);
                          e.target.value = "";
                        }}
                      />
                    </div>
                    {files.length > 0 && (
                      <div className="file-list">
                        {files.map((f, i) => (
                          <span key={`${f.name}-${i}`} className="pill pill-neutral" title={f.name}>
                            <span>{f.name}</span>
                            <button
                              className="toast-x"
                              style={{ fontSize: 12, padding: 0 }}
                              aria-label={`Remove ${f.name}`}
                              onClick={() => setFiles((fs) => fs.filter((_, j) => j !== i))}
                            >
                              ×
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                    {uploadedCount > 0 && (
                      <span className="field-hint">
                        <Pill tone="pass">{uploadedCount} uploaded</Pill> Add more photos and analyze again if intake asks for another shot.
                      </span>
                    )}
                    <span className="field-hint">
                      Put the object on the printed{" "}
                      <a href={sheetPdfUrl} target="_blank" rel="noreferrer">
                        calibration sheet
                      </a>{" "}
                      and shoot straight down for measurable photos.
                    </span>
                  </div>
                  <label className="check">
                    <input type="checkbox" checked={expectSheet} onChange={(e) => setExpectSheet(e.target.checked)} />
                    <span>Photos include the calibration sheet</span>
                  </label>
                  <label className="field">
                    <span className="field-label">What broke?</span>
                    <textarea
                      className="textarea"
                      rows={2}
                      value={sentence}
                      onChange={(e) => setSentence(e.target.value)}
                      placeholder="One sentence: the carry handle of this 1 L water bottle snapped at the ring…"
                    />
                  </label>
                  <div className="row">
                    <button className="btn btn-primary" onClick={onAnalyze} disabled={intakeStep > 0 && intakeStep < 4}>
                      {intakeStep > 0 && intakeStep < 4 ? <Spinner size={12} /> : <CameraIcon />}
                      Analyze photos
                    </button>
                    {intakeStep > 0 && (
                      <div className="steps">
                        <Step n={1} cur={intakeStep} label="Create session" />
                        <Step n={2} cur={intakeStep} label="Upload & grade photos" />
                        <Step n={3} cur={intakeStep} label="Analyze with vision model" />
                      </div>
                    )}
                  </div>
                  {intake && <IntakeCard data={intake} />}
                </>
              )}

              {mode === "spec" && (
                <label className="field">
                  <span className="field-label">Example spec</span>
                  <select className="select" value={example} onChange={(e) => pickExample(e.target.value)}>
                    {examples.length === 0 && <option value="">(no examples found)</option>}
                    {examples.map((ex) => (
                      <option key={ex.name} value={ex.name}>
                        {ex.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              {mode === "spec" && (
                <label className="field">
                  <span className="field-label">Part Spec (YAML)</span>
                  <textarea
                    className="textarea textarea-mono"
                    rows={16}
                    value={specYaml}
                    onChange={(e) => setSpecYaml(e.target.value)}
                    spellCheck={false}
                    placeholder={"part:\n  name: …"}
                  />
                </label>
              )}
              {mode === "photos" && intakeStep === 4 && (
                <label className="field">
                  <span className="field-label">Draft Part Spec (YAML) — edit before opening</span>
                  <textarea
                    className="textarea textarea-mono"
                    rows={14}
                    value={intakeYaml}
                    onChange={(e) => setIntakeYaml(e.target.value)}
                    spellCheck={false}
                    placeholder="Filled in by intake; edit before opening the session."
                  />
                </label>
              )}

              {mode === "spec" && (
                <>
                  <button className="btn btn-ghost btn-sm" style={{ alignSelf: "flex-start" }} onClick={() => setShowScad((v) => !v)}>
                    {showScad ? "▾" : "▸"} Optional starting part.scad
                  </button>
                  {showScad && (
                    <textarea
                      className="textarea textarea-mono"
                      rows={8}
                      value={scad}
                      onChange={(e) => setScad(e.target.value)}
                      spellCheck={false}
                      placeholder="// Paste an OpenSCAD file to start from; leave empty to let the designer write it."
                    />
                  )}
                  <div className="row">
                    <button className="btn btn-primary" onClick={onCreate} disabled={creating}>
                      {creating ? <Spinner size={12} /> : <PlusIcon />}
                      Create session
                    </button>
                    <span className="field-hint">You can run the designer, edit params or code from the workspace.</span>
                  </div>
                </>
              )}

              {mode === "photos" && intakeSid && intakeStep === 4 && (
                <div className="row">
                  <button className="btn btn-primary" onClick={onOpenIntake}>
                    Save spec &amp; open session
                  </button>
                  <Link to={`/s/${intakeSid}`} className="btn btn-sm">
                    Open without saving
                  </Link>
                </div>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

function Step({ n, cur, label }: { n: number; cur: number; label: string }) {
  const cls = cur > n ? "done" : cur === n ? "active" : "";
  return (
    <div className={`step ${cls}`}>
      {cur > n ? <span>✓</span> : cur === n ? <Spinner size={11} /> : <span>·</span>}
      <span>{label}</span>
    </div>
  );
}

function IntakeCard({ data }: { data: IntakeResult }) {
  return (
    <div className="intake-card stack">
      <div>
        <div className="label">Intake</div>
        <h3>{data.object || "Unknown object"}</h3>
        {data.part_role && <div>{data.part_role}</div>}
        {data.damage && (
          <div className="dim small">
            <b>Damage:</b> {data.damage}
          </div>
        )}
        {typeof data.confidence === "number" && (
          <div className="mt">
            <Pill tone={data.confidence >= 0.7 ? "pass" : data.confidence >= 0.4 ? "warn" : "fail"}>confidence {Math.round(data.confidence * 100)}%</Pill>
          </div>
        )}
        {data.spec_error && <div className="banner banner-fail mt">Spec validation: {data.spec_error}</div>}
      </div>
      {data.interfaces_reasoning && (
        <div>
          <div className="label">Interfaces</div>
          <div className="small">{data.interfaces_reasoning}</div>
        </div>
      )}
      {data.capture_plan && data.capture_plan.length > 0 && (
        <div>
          <div className="label">Capture plan</div>
          <ol>
            {data.capture_plan.map((c, i) => (
              <li key={i}>
                <b>{c.name || `Shot ${c.n ?? i + 1}`}</b>
                {c.purpose && <span className="dim"> — {c.purpose}</span>}
                {c.how && <div className="small dim">{c.how}</div>}
                {c.measures && c.measures.length > 0 && (
                  <div className="row-wrap" style={{ marginTop: 3 }}>
                    {c.measures.map((m) => (
                      <Pill key={m} tone="blue">
                        {m}
                      </Pill>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
      {data.questions && data.questions.length > 0 && (
        <div>
          <div className="label">Questions for you</div>
          <ol>
            {data.questions.map((q, i) => (
              <li key={q.id || i}>
                {q.text}
                {q.options && q.options.length > 0 && <div className="small dim">Options: {q.options.join(" · ")}</div>}
                {q.dim && (
                  <div className="small">
                    <Pill tone="neutral">{q.dim}</Pill>
                  </div>
                )}
              </li>
            ))}
          </ol>
          <div className="field-hint mt">Answer them by editing the spec below, or confirm dimensions in the workspace's Spec tab.</div>
        </div>
      )}
    </div>
  );
}

export function Mark() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#FAFBFC" strokeWidth="2.6" strokeLinejoin="round" strokeLinecap="round">
      <path d="M4 19 10 5l4 8 6-9" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v12m0 0 4-4m-4 4-4-4M4 17v3h16v-3" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function CameraIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
      <path d="M4 8h3l2-3h6l2 3h3v11H4z" />
      <circle cx="12" cy="13" r="3.2" />
    </svg>
  );
}
