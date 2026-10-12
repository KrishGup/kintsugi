import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, kin, sheetPdfUrl } from "../api";
import { UserChip, useAuth } from "../auth";
import { Brand } from "../brand";
import { useBusy } from "../hooks";
import { Camera, Check, ChevronDown, ChevronRight, Close, Dot, Download, Gear, Plus, Upload } from "../icons";
import { ProviderPill, providerLabel, useLlm } from "../llm";
import { useToast } from "../toast";
import type { ExampleSpec, IntakeResult, SessionMeta } from "../types";
import { Empty, Pill, Spinner, relTime, statusLabel, statusTone } from "../ui";

type Mode = "spec" | "photos";

const exampleName = (ex: ExampleSpec) => (ex.title || ex.name).replace(/_/g, " ");

export default function Home() {
  const nav = useNavigate();
  const { toast, error } = useToast();
  const llm = useLlm();
  const auth = useAuth();
  const [sessions, setSessions] = useState<SessionMeta[] | null>(null);
  const [examples, setExamples] = useState<ExampleSpec[]>([]);
  const [mode, setMode] = useState<Mode>("photos");

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

  // session archives (.zip) coming back in
  const archiveInput = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);

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
          setName((n) => n || exampleName(ex[0]));
        }
      })
      .catch((e) => error(e, "Could not load example specs"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pickExample = (n: string) => {
    const prev = examples.find((e) => e.name === example);
    setExample(n);
    const ex = examples.find((e) => e.name === n);
    if (ex) {
      setSpecYaml(ex.yaml);
      // the name follows the example until someone types their own
      if (!name || (prev && name === exampleName(prev))) setName(exampleName(ex));
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
    if (!llm.ready) {
      llm.openSettings();
      return;
    }
    let sid = intakeSid;
    try {
      setIntake(null);
      setIntakeStep(1);
      if (!sid) {
        const d = await kin.createSession({ name: name.trim() || undefined, intake: true });
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
      toast(`Intake: ${res.object || "object recognised"} — opening the session`, "pass");
      nav(`/s/${sid}`);
    } catch (e) {
      setIntakeStep(intake ? 4 : 0);
      if (e instanceof ApiError && e.status === 412) {
        toast("Add your OpenAI API key to analyze photos", "warn");
        llm.openSettings();
      } else error(e, "Intake failed");
      if (sid && intakeStep >= 2) loadSessions();
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

  const onImport = async (file: File | null | undefined) => {
    if (!file) return;
    setImporting(true);
    try {
      const d = await kin.importSession(file);
      toast(`Imported “${d.meta.name}”`, "pass");
      nav(`/s/${d.meta.id}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 413) toast("That archive is larger than this server accepts", "fail");
      else if (e instanceof ApiError && e.status === 422) error(e, "Not a Kintsugi session archive");
      else error(e, "Import failed");
    } finally {
      setImporting(false);
    }
  };

  const sorted = useMemo(() => (sessions ? [...sessions].sort((a, b) => (b.updated || b.created || 0) - (a.updated || a.created || 0)) : []), [sessions]);

  return (
    <div className="app">
      <header className="app-header">
        <Link to="/" className="brand">
          <Brand />
        </Link>
        <span className="brand-tag">Photograph what broke. Print what fits.</span>
        <span className="header-spacer" />
        <ProviderPill />
        <a className="btn btn-sm btn-icon-sm" href={sheetPdfUrl} target="_blank" rel="noreferrer" aria-label="Calibration sheet (PDF)">
          <Download size={17} /> <span className="btn-text">Calibration sheet</span>
        </a>
        <button className="btn btn-sm btn-icon-sm" onClick={llm.openSettings} aria-label="Settings">
          <Gear size={17} /> <span className="btn-text">Settings</span>
        </button>
        <UserChip />
      </header>

      <main className="home">
        <div className="hero">
          <h1>Photograph what broke. Print what fits.</h1>
          <p>Two or three phone photos become a verified, printable replacement: every dimension is measured on the designed mesh before you print.</p>
        </div>
        <ol className="path" aria-label="How it works">
          {[
            ["Photograph", "the broken part on the printed calibration sheet"],
            ["Answer", "the one or two photos it still needs"],
            ["Verify", "every dimension measured on the designed mesh"],
            ["Print", "the fit coupon, then the part"],
          ].map(([h, t], i) => (
            <li key={h} className="path-step">
              <span className="path-tick" aria-hidden="true" />
              <span className="path-n num">{i + 1}</span>
              <span className="path-text">
                <b>{h}</b> {t}
              </span>
            </li>
          ))}
        </ol>
        {llm.status && !llm.ready && (
          <div className="banner banner-warn mb">
            {llm.locked ? (
              <span>
                <b>No model configured on this server.</b> Its settings are managed by the deployment — ask whoever runs it to set the OpenAI key
                (or demo mode).
              </span>
            ) : (
              <span>
                <b>No model yet.</b> Add your OpenAI API key to design parts, or switch to demo mode for a scripted walkthrough.
              </span>
            )}
            {!llm.locked && (
              <button className="btn btn-sm btn-primary" onClick={llm.openSettings}>
                Open settings
              </button>
            )}
          </div>
        )}

        <div className="home-grid">
          <section className="panel home-new">
            <div className="panel-head">
              <h2>New part</h2>
              <span className="grow" />
              <div className="mode-switch" role="tablist" aria-label="Start from">
                <button
                  role="tab"
                  aria-selected={mode === "photos"}
                  className={mode === "photos" ? "active" : ""}
                  onClick={() => setMode("photos")}
                >
                  Photograph what broke
                </button>
                <button role="tab" aria-selected={mode === "spec"} className={mode === "spec" ? "active" : ""} onClick={() => setMode("spec")}>
                  From a spec
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
                      <span className="file-drop-main">Drop photos here, or tap to take or choose them</span>
                      <span className="file-drop-sub">JPG, PNG or WebP · two or three shots: the whole object, the break, the mating feature on the sheet</span>
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
                            <button className="toast-x" style={{ padding: 0 }} aria-label={`Remove ${f.name}`} onClick={() => setFiles((fs) => fs.filter((_, j) => j !== i))}>
                              <Close size={14} />
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
                      {intakeStep > 0 && intakeStep < 4 ? <Spinner size={16} /> : <Camera size={17} />}
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
                    <optgroup label="Parts with a vetted template (demo mode designs these)">
                      {examples
                        .filter((ex) => ex.group !== "reference")
                        .map((ex) => (
                          <option key={ex.name} value={ex.name}>
                            {ex.title || ex.name}
                          </option>
                        ))}
                    </optgroup>
                    {examples.some((ex) => ex.group === "reference") && (
                      <optgroup label="A/B reference specs (human-designed parts; need a real model)">
                        {examples
                          .filter((ex) => ex.group === "reference")
                          .map((ex) => (
                            <option key={ex.name} value={ex.name}>
                              {ex.title || ex.name}
                            </option>
                          ))}
                      </optgroup>
                    )}
                  </select>
                  {llm.status?.provider === "fake" && examples.find((ex) => ex.name === example)?.group === "reference" && (
                    <span className="field-hint">
                      Demo mode has no template for this part: the run will show the checks failing, not a finished part. Pick one from the first group, or add an OpenAI key.
                    </span>
                  )}
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


              {mode === "spec" && (
                <>
                  <button className="btn btn-ghost btn-sm" style={{ alignSelf: "flex-start" }} onClick={() => setShowScad((v) => !v)}>
                    {showScad ? <ChevronDown size={16} /> : <ChevronRight size={16} />} Optional starting part.scad
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
                      {creating ? <Spinner size={16} /> : <Plus size={17} />}
                      Create session
                    </button>
                    <span className="field-hint">You can run the designer, edit params or code from the workspace.</span>
                  </div>
                </>
              )}

              {mode === "photos" && intakeSid && intakeStep === 4 && (
                <div className="row">
                  <button className="btn btn-primary" onClick={onOpenIntake}>
                    Open the session →
                  </button>
                </div>
              )}
            </div>
          </section>

          <section className="panel home-sessions">
            <div className="panel-head">
              <h2>Your parts</h2>
              <span className="grow" />
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => archiveInput.current?.click()}
                disabled={importing}
              >
                {importing ? <Spinner size={14} /> : <Upload size={16} />} Import archive
              </button>
              <input
                ref={archiveInput}
                type="file"
                accept=".zip,application/zip"
                hidden
                aria-label="Session archive (.zip)"
                onChange={(e) => {
                  onImport(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
              <button className="btn btn-ghost btn-sm" onClick={loadSessions}>
                Refresh
              </button>
            </div>
            {sessions === null ? (
              <div className="panel-body">
                <Spinner label="Loading sessions…" />
              </div>
            ) : sorted.length === 0 ? (
              <div className="panel-body">
                <Empty title="No parts yet" icon={<Camera size={39} stroke={1.4} />}>
                  Print the{" "}
                  <a href={sheetPdfUrl} target="_blank" rel="noreferrer">
                    calibration sheet
                  </a>
                  , put the broken object on it, take two or three photos and describe what broke. Each part becomes a session with its photos,
                  spec, iterations and exports — or import an archive from another Kintsugi.
                </Empty>
              </div>
            ) : (
              <ul className="session-list">
                {sorted.map((s) => (
                  <li key={s.id} className="session-row" onClick={() => nav(`/s/${s.id}`)}>
                    <div className="session-main">
                      <Link to={`/s/${s.id}`} className="session-name" onClick={(e) => e.stopPropagation()}>
                        {s.name || s.id}
                      </Link>
                      <span className="session-meta">
                        <span className="num">{s.iteration ? `${s.iteration} iteration${s.iteration === 1 ? "" : "s"}` : "no iterations yet"}</span>
                        <span aria-hidden="true">·</span>
                        <span>{relTime(s.updated || s.created)}</span>
                        {s.imported_from && (
                          <>
                            <span aria-hidden="true">·</span>
                            <span>imported{s.imported_from.app_version ? ` from Kintsugi ${s.imported_from.app_version}` : ""}</span>
                          </>
                        )}
                        {auth.info?.mode === "easyauth" && s.owner && s.owner !== auth.info.user?.id && (
                          <>
                            <span aria-hidden="true">·</span>
                            <span>{s.owner_name || s.owner}</span>
                          </>
                        )}
                      </span>
                    </div>
                    <Pill tone={statusTone(s.status)} dot={s.status === "running"}>
                      {statusLabel(s.status)}
                    </Pill>
                    <button
                      className="btn btn-ghost btn-xs btn-quiet-danger session-delete"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDelete(s);
                      }}
                      aria-label={`Delete ${s.name || s.id}`}
                    >
                      Delete
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {llm.version && (
              <div className="health">
                Kintsugi v{llm.version}
                {llm.openscad ? ` · OpenSCAD ${llm.openscad}` : " · OpenSCAD not found"}
                {llm.status ? ` · ${providerLabel(llm.status.provider)}${llm.status.provider !== "fake" && llm.status.models.designer ? " " + llm.status.models.designer : ""}` : ""}
              </div>
            )}
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
      {cur > n ? <Check size={14} /> : cur === n ? <Spinner size={14} /> : <Dot size={14} />}
      <span>{label}</span>
    </div>
  );
}

function IntakeCard({ data }: { data: IntakeResult }) {
  return (
    <div className="intake-card stack">
      <div>
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
