import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, fileUrl, kin, sheetPdfUrl } from "../api";
import { useLlm } from "../llm";
import { useSession } from "../pages/session-context";
import { fmtElapsed, useRunProgress } from "../progress";
import { useToast } from "../toast";
import type { AnswerBody, CaptureShot, Dim, IntakeQuestion, Photo, Stage } from "../types";
import { Markdown, Pill, Spinner, fmtNum, type Tone } from "../ui";

export const STAGES: Array<{ id: Stage; label: string; short: string }> = [
  { id: "intake", label: "What broke", short: "Intake" },
  { id: "capture", label: "Photos & answers", short: "Capture" },
  { id: "spec", label: "Confirm the fit", short: "Spec" },
  { id: "design", label: "Design & verify", short: "Design" },
  { id: "review", label: "Review", short: "Review" },
  { id: "export", label: "Print it", short: "Print" },
];

export function stageIndex(stage: string | undefined): number {
  const i = STAGES.findIndex((s) => s.id === stage);
  return i < 0 ? 2 : i;
}

function dimStatus(d: Dim): { tone: Tone; label: string } {
  switch (d.status) {
    case "confirmed":
      return { tone: "pass", label: "confirmed" };
    case "estimated":
      return { tone: "warn", label: "estimated" };
    default:
      return { tone: "fail", label: "unknown" };
  }
}

function dimText(d: Dim): string {
  if (typeof d.target === "number") return `${fmtNum(d.target)} ±${fmtNum(d.tol ?? 0.3)} mm`;
  const parts: string[] = [];
  if (typeof d.min === "number") parts.push(`≥ ${fmtNum(d.min)}`);
  if (typeof d.max === "number") parts.push(`≤ ${fmtNum(d.max)}`);
  return parts.length ? `${parts.join(" ")} mm` : "unspecified";
}

/** Stage-aware walkthrough: one card per stage, the current one expanded, each with the single next action. */
export default function GuidePane() {
  const s = useSession();
  const d = s.detail!;
  const cur = s.running ? "design" : (d.stage as Stage);
  const curIdx = stageIndex(cur);
  const [openStage, setOpenStage] = useState<Stage | null>(null);
  const shown = openStage ?? cur;

  useEffect(() => {
    setOpenStage(null); // follow the session when the stage advances
  }, [cur]);

  return (
    <div className="guide">
      {STAGES.map((st, i) => {
        const state = i < curIdx ? "done" : i === curIdx ? "current" : "todo";
        const open = shown === st.id;
        return (
          <section key={st.id} className={`gstep gstep-${state}${open ? " open" : ""}`}>
            <button className="gstep-head" onClick={() => setOpenStage(open && st.id !== cur ? null : st.id)} aria-expanded={open}>
              <span className="gstep-n">{state === "done" ? "✓" : i + 1}</span>
              <span className="gstep-title">{st.label}</span>
              <span className="grow" />
              <StageSummary stage={st.id} />
            </button>
            {open && (
              <div className="gstep-body">
                {st.id === "intake" && <IntakeStage />}
                {st.id === "capture" && <CaptureStage />}
                {st.id === "spec" && <SpecStage />}
                {st.id === "design" && <DesignStage />}
                {st.id === "review" && <ReviewStage />}
                {st.id === "export" && <ExportStage />}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

function StageSummary({ stage }: { stage: Stage }) {
  const s = useSession();
  const d = s.detail!;
  const it = s.latestIter;
  switch (stage) {
    case "intake":
      return d.intake ? <span className="gstep-sum">{d.intake.object || "analyzed"}</span> : <span className="gstep-sum dim">photos + one sentence</span>;
    case "capture": {
      const n = d.photos.length;
      const q = d.intake?.questions?.length || 0;
      return <span className="gstep-sum">{n ? `${n} photo${n === 1 ? "" : "s"}` : "no photos"}{q ? ` · ${q} question${q === 1 ? "" : "s"}` : ""}</span>;
    }
    case "spec":
      return d.unconfirmed.length ? (
        <Pill tone="warn">{d.unconfirmed.length} to confirm</Pill>
      ) : (
        <Pill tone="pass">fit confirmed</Pill>
      );
    case "design":
      if (s.running) return <Pill tone="blue" dot>running</Pill>;
      if (d.meta.status === "waiting_user") return <Pill tone="warn">question for you</Pill>;
      return it ? <span className="gstep-sum">{d.iterations.length} iteration{d.iterations.length === 1 ? "" : "s"}</span> : <span className="gstep-sum dim">not started</span>;
    case "review":
      return it ? <Pill tone={it.ok ? "pass" : "fail"}>{it.ok ? "all checks pass" : `${it.failures.length} failing`}</Pill> : <span className="gstep-sum dim">—</span>;
    case "export":
      return d.export.includes("bundle.zip") ? <Pill tone="pass">bundle ready</Pill> : <span className="gstep-sum dim">—</span>;
    default:
      return null;
  }
}

function NotReady({ what }: { what: string }) {
  const llm = useLlm();
  return (
    <div className="banner banner-warn">
      <span>
        <b>Add your OpenAI API key</b> to {what}. {llm.status?.reason ? `(${llm.status.reason})` : ""}
      </span>
      <button className="btn btn-sm btn-primary" onClick={llm.openSettings}>
        Open settings
      </button>
    </div>
  );
}

// ---- 1. intake ------------------------------------------------------------------------------------

function IntakeStage() {
  const s = useSession();
  const llm = useLlm();
  const { toast, error } = useToast();
  const d = s.detail!;
  const [files, setFiles] = useState<File[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<"" | "upload" | "analyze">("");
  const input = useRef<HTMLInputElement>(null);
  const intake = d.intake;

  const analyze = async () => {
    if (!llm.ready) {
      llm.openSettings();
      return;
    }
    try {
      if (files.length) {
        setBusy("upload");
        await kin.uploadPhotos(s.sid, files, true);
        setFiles([]);
      } else if (!d.photos.length) {
        toast("Add at least one photo of the broken object", "warn");
        return;
      }
      setBusy("analyze");
      const r = await kin.intake(s.sid, text.trim());
      toast(`Intake: ${r.object || "object recognised"} · ${r.questions?.length || 0} question${r.questions?.length === 1 ? "" : "s"}`, "pass");
      await s.refresh();
    } catch (e) {
      if (e instanceof ApiError && e.status === 412) llm.openSettings();
      error(e, "Intake failed");
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="stack">
      {intake && (
        <div className="gcard">
          <div className="row-wrap">
            <b>{intake.object || "Object"}</b>
            {typeof intake.confidence === "number" && (
              <Pill tone={intake.confidence >= 0.7 ? "pass" : intake.confidence >= 0.4 ? "warn" : "fail"}>confidence {Math.round(intake.confidence * 100)}%</Pill>
            )}
          </div>
          {intake.part_role && <div className="small">{intake.part_role}</div>}
          {intake.damage && (
            <div className="small dim">
              <b>Damage:</b> {intake.damage}
            </div>
          )}
          {intake.interfaces_reasoning && <div className="small dim mt">{intake.interfaces_reasoning}</div>}
          {intake.spec_error && <div className="banner banner-fail mt">Draft spec had a problem: {intake.spec_error}</div>}
        </div>
      )}
      {!llm.ready && <NotReady what="analyze the photos" />}
      <div className="field">
        <span className="field-label">{intake ? "More photos (optional)" : "Photos of the broken object"}</span>
        <div className="row-wrap">
          <button className="btn btn-sm" onClick={() => input.current?.click()}>
            <CameraIcon /> {files.length ? `${files.length} chosen` : "Choose photos"}
          </button>
          <input
            ref={input}
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={(e) => {
              const list = Array.from(e.target.files || []).filter((f) => /^image\//.test(f.type) || /\.(jpe?g|png|webp)$/i.test(f.name));
              if (list.length) setFiles((fs) => [...fs, ...list]);
              e.target.value = "";
            }}
          />
          {d.photos.length > 0 && <Pill tone="pass">{d.photos.length} uploaded</Pill>}
          {files.length > 0 && (
            <button className="btn btn-ghost btn-xs" onClick={() => setFiles([])}>
              clear
            </button>
          )}
        </div>
        <span className="field-hint">
          Two or three shots: the whole object, the broken part close up, and the mating feature (the neck, the shaft, the slot) on the{" "}
          <a href={sheetPdfUrl} target="_blank" rel="noreferrer">
            calibration sheet
          </a>
          .
        </span>
      </div>
      <label className="field">
        <span className="field-label">What broke?</span>
        <textarea
          className="textarea"
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="One sentence: the carry handle of this 1 L water bottle snapped at the ring…"
        />
      </label>
      <div className="row">
        <button className="btn btn-primary" onClick={analyze} disabled={busy !== ""}>
          {busy ? <Spinner size={12} /> : <CameraIcon />} {busy === "upload" ? "Uploading…" : busy === "analyze" ? "Analyzing with GPT-6…" : intake ? "Analyze again" : "Analyze photos"}
        </button>
        {intake && (
          <button className="btn btn-ghost btn-sm" onClick={() => kin.setStage(s.sid, "capture").then(() => s.refresh())}>
            Continue →
          </button>
        )}
      </div>
    </div>
  );
}

// ---- 2. capture + questions -----------------------------------------------------------------------

function CaptureStage() {
  const s = useSession();
  const { toast, error } = useToast();
  const d = s.detail!;
  const plan = d.intake?.capture_plan || [];
  const questions = d.intake?.questions || [];
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const answered = questions.filter((q) => (answers[q.id || q.text || ""] || "").trim() !== "").length;

  const submit = async () => {
    const body: AnswerBody[] = [];
    for (const q of questions) {
      const key = q.id || q.text || "";
      const v = (answers[key] || "").trim();
      if (!v) continue;
      const kind = (q.kind === "number" || q.kind === "choice" ? q.kind : "text") as AnswerBody["kind"];
      body.push({ id: q.id, dim: q.dim, kind, value: kind === "number" ? Number(v) : v, question: q.text });
    }
    setSaving(true);
    try {
      if (body.length) {
        const r = await kin.answers(s.sid, body);
        toast(`${r.applied.length} answer${r.applied.length === 1 ? "" : "s"} applied to the spec`, "pass");
      } else await kin.setStage(s.sid, "spec");
      await s.refresh();
    } catch (e) {
      error(e, "Could not save answers");
    } finally {
      setSaving(false);
    }
  };

  if (!d.intake) {
    return (
      <div className="stack">
        <div className="small dim">Intake has not run for this session. Upload photos in the Photos tab, or go straight to the spec.</div>
        <button className="btn btn-sm" onClick={() => kin.setStage(s.sid, "spec").then(() => s.refresh())}>
          Skip to the spec →
        </button>
      </div>
    );
  }

  return (
    <div className="stack">
      {plan.length > 0 && (
        <div>
          <div className="label">Capture plan</div>
          <div className="small dim mb">Each shot pins down one dimension. Shoot straight down on the calibration sheet; blurry or tilted shots are flagged on upload.</div>
          <div className="stack">
            {plan.map((c, i) => (
              <ShotSlot key={i} shot={c} index={i} photos={d.photos} />
            ))}
          </div>
        </div>
      )}
      {questions.length > 0 && (
        <div>
          <div className="label">Questions for you</div>
          <div className="small dim mb">Numbers become confirmed dimensions; choices become design intent. Skip what you don't know.</div>
          <div className="stack">
            {questions.map((q, i) => (
              <QuestionField key={q.id || i} q={q} value={answers[q.id || q.text || ""] || ""} onChange={(v) => setAnswers((a) => ({ ...a, [q.id || q.text || ""]: v }))} />
            ))}
          </div>
        </div>
      )}
      {plan.length === 0 && questions.length === 0 && <div className="small dim">Intake had no further questions.</div>}
      <div className="row">
        <button className="btn btn-primary" onClick={submit} disabled={saving}>
          {saving ? <Spinner size={12} /> : null} {answered ? `Save ${answered} answer${answered === 1 ? "" : "s"} & continue` : "Continue"} →
        </button>
        <span className="small dim">Next: confirm the fit dimensions.</span>
      </div>
    </div>
  );
}

function ShotSlot({ shot, index, photos }: { shot: CaptureShot; index: number; photos: Photo[] }) {
  const s = useSession();
  const { toast, error } = useToast();
  const n = shot.n ?? index + 1;
  const label = `shot${n}`;
  const mine = photos.filter((p) => p.file.replace(/^photos\//, "").startsWith(label + "_"));
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const upload = async (list: FileList | null) => {
    if (!list || !list.length) return;
    setBusy(true);
    try {
      const res = await kin.uploadPhotos(s.sid, Array.from(list), true, label);
      const g = res[0]?.grade;
      toast(g?.ok ? `Shot ${n}: good capture` : `Shot ${n}: ${g?.instructions?.[0] || "check the grade and retake if needed"}`, g?.ok ? "pass" : "warn");
      await s.refresh();
    } catch (e) {
      error(e, "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const best = mine.find((p) => p.grade?.ok) || mine[mine.length - 1];
  return (
    <div className={`shot${best ? (best.grade?.ok ? " shot-ok" : " shot-retake") : ""}`}>
      <div className="shot-n">{n}</div>
      <div className="shot-body">
        <div className="row-wrap">
          <b>{shot.name || `Shot ${n}`}</b>
          {best ? <Pill tone={best.grade?.ok ? "pass" : "warn"}>{best.grade?.ok ? "good capture" : "retake suggested"}</Pill> : <Pill tone="neutral">not yet</Pill>}
        </div>
        {shot.purpose && <div className="small dim">{shot.purpose}</div>}
        {shot.how && <div className="small">{shot.how}</div>}
        {shot.measures && shot.measures.length > 0 && (
          <div className="row-wrap" style={{ marginTop: 4 }}>
            {shot.measures.map((m) => (
              <Pill key={m} tone="blue">
                {m}
              </Pill>
            ))}
          </div>
        )}
        {best && best.grade && !best.grade.ok && best.grade.instructions && best.grade.instructions.length > 0 && (
          <ul className="photo-instr">
            {best.grade.instructions.slice(0, 2).map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        )}
        <div className="row-wrap" style={{ marginTop: 6 }}>
          <button className="btn btn-xs" onClick={() => input.current?.click()} disabled={busy}>
            {busy ? <Spinner size={10} /> : <CameraIcon />} {best ? "Retake" : "Take / upload"}
          </button>
          <input
            ref={input}
            type="file"
            accept="image/*"
            capture="environment"
            hidden
            onChange={(e) => {
              upload(e.target.files);
              e.target.value = "";
            }}
          />
          {best && (
            <a className="small" href={fileUrl(s.sid, best.file)} target="_blank" rel="noreferrer">
              view
            </a>
          )}
          {best && shot.measures && shot.measures.length > 0 && <span className="small dim">measure it in the Photos tab →</span>}
        </div>
      </div>
      {best && <img className="shot-thumb" src={fileUrl(s.sid, best.file)} alt="" loading="lazy" />}
    </div>
  );
}

function QuestionField({ q, value, onChange }: { q: IntakeQuestion; value: string; onChange: (v: string) => void }) {
  const kind = q.kind || "text";
  return (
    <div className="qfield">
      <div className="small">
        {q.text}
        {q.dim && (
          <>
            {" "}
            <Pill tone="neutral">{q.dim}</Pill>
          </>
        )}
      </div>
      {kind === "number" ? (
        <div className="row">
          <input className="input input-num input-mono" type="number" step="0.1" inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value)} placeholder="—" />
          <span className="small dim">mm</span>
        </div>
      ) : kind === "choice" && q.options && q.options.length ? (
        <div className="choices">
          {q.options.map((o) => (
            <button key={o} className={`btn btn-sm btn-choice${value === o ? " btn-primary" : ""}`} onClick={() => onChange(value === o ? "" : o)}>
              {o}
            </button>
          ))}
        </div>
      ) : (
        <input className="input" value={value} onChange={(e) => onChange(e.target.value)} placeholder="Your answer (optional)" />
      )}
    </div>
  );
}

// ---- 3. spec / confirm --------------------------------------------------------------------------------

function SpecStage() {
  const s = useSession();
  const llm = useLlm();
  const d = s.detail!;
  const [budget, setBudget] = useState(8);
  const [starting, setStarting] = useState(false);

  const dims = useMemo(() => {
    const out: Array<{ key: string; itf: string; name: string; dim: Dim; mates?: string; fit?: string }> = [];
    for (const itf of d.spec.interfaces || [])
      for (const [k, dim] of Object.entries(itf.dims || {})) out.push({ key: `${itf.id}.${k}`, itf: itf.id, name: k, dim, mates: itf.mates_with, fit: itf.fit });
    return out;
  }, [d.spec]);

  const start = async () => {
    if (!llm.ready) {
      llm.openSettings();
      return;
    }
    setStarting(true);
    try {
      await s.startRun({ budget, critic_rounds: 2 });
    } finally {
      setStarting(false);
    }
  };

  const hasRun = d.iterations.length > 0;
  return (
    <div className="stack">
      <div className="small dim">
        These are the dimensions the part must match on the real object. Confirmed ones drive the design; estimated ones are the model's guess from the
        photos — type the measured value to lock them.
      </div>
      {dims.length === 0 ? (
        <div className="banner banner-warn">
          <span>The spec has no interface dimensions yet. Edit it in the Spec tab (or run intake) before designing.</span>
        </div>
      ) : (
        <div className="dims">
          {dims.map((x) => (
            <DimRow key={x.key} itf={x.itf} name={x.name} dim={x.dim} mates={x.mates} fit={x.fit} />
          ))}
        </div>
      )}
      {d.unconfirmed.length > 0 && (
        <div className="small dim">
          {d.unconfirmed.length} dimension{d.unconfirmed.length === 1 ? "" : "s"} still unconfirmed — you can design now and print the fit coupon afterwards.
        </div>
      )}
      {!llm.ready && <NotReady what="run the designer" />}
      <div className="gcard stack">
        <div className="row-wrap">
          <span className="label">Design effort</span>
          <div className="seg" role="radiogroup">
            {[
              [4, "Quick"],
              [8, "Standard"],
              [14, "Thorough"],
            ].map(([n, l]) => (
              <button key={n} role="radio" aria-checked={budget === n} className={`seg-btn${budget === n ? " active" : ""}`} onClick={() => setBudget(Number(n))}>
                {l}
              </button>
            ))}
          </div>
          <span className="small dim">{budget} iterations max · 2 critic rounds</span>
        </div>
        <button className="btn btn-primary btn-lg" onClick={start} disabled={starting || s.running || dims.length === 0}>
          {starting ? <Spinner size={13} /> : <PlayIcon />} {hasRun ? "Design again" : "Design this part"}
        </button>
        <span className="small dim">
          {llm.status?.provider === "fake" ? "Demo mode: a scripted designer builds from the closest template." : `${llm.status?.models.designer || "GPT-6"} writes the OpenSCAD, compiles it, measures the mesh against every dimension above and fixes what fails — then a second model reviews the drawings.`}
        </span>
      </div>
    </div>
  );
}

function DimRow({ itf, name, dim, mates, fit }: { itf: string; name: string; dim: Dim; mates?: string; fit?: string }) {
  const s = useSession();
  const { toast, error } = useToast();
  const [v, setV] = useState("");
  const [busy, setBusy] = useState(false);
  const st = dimStatus(dim);
  const full = `${itf}.${name}`;
  const confirm = async () => {
    const val = Number(v);
    if (!Number.isFinite(val)) return;
    setBusy(true);
    try {
      await kin.confirm(s.sid, full, val, "user_ruler");
      toast(`${full} confirmed at ${val} mm`, "pass");
      setV("");
      await s.refresh();
    } catch (e) {
      error(e, "Could not confirm");
    } finally {
      setBusy(false);
    }
  };
  const best = dim.estimates && dim.estimates.length ? dim.estimates[dim.estimates.length - 1] : null;
  return (
    <div className="dimrow">
      <div className="dimrow-main">
        <div className="row-wrap">
          <span className="dim-name">
            <span className="itf">{itf}.</span>
            {name}
          </span>
          <Pill tone={st.tone}>{st.label}</Pill>
        </div>
        <div className="small dim">
          {dimText(dim)}
          {mates ? ` · mates with ${mates}` : ""}
          {fit ? ` · ${fit} fit` : ""}
          {best && dim.status !== "confirmed" ? ` · last estimate ${fmtNum(best.value)} mm (${best.source})` : ""}
        </div>
      </div>
      {dim.status !== "confirmed" && (
        <div className="row">
          <input
            className="input input-num input-mono"
            type="number"
            step="0.1"
            inputMode="decimal"
            value={v}
            onChange={(e) => setV(e.target.value)}
            placeholder={typeof dim.target === "number" ? fmtNum(dim.target) : "mm"}
            onKeyDown={(e) => {
              if (e.key === "Enter") confirm();
            }}
            aria-label={`measured ${full} in mm`}
          />
          <button className="btn btn-xs btn-primary" onClick={confirm} disabled={busy || !v.trim()}>
            {busy ? <Spinner size={10} /> : "Confirm"}
          </button>
        </div>
      )}
    </div>
  );
}

// ---- 4. design (live) -----------------------------------------------------------------------------------

function DesignStage() {
  const s = useSession();
  const d = s.detail!;
  const p = useRunProgress(s.events, s.running);
  const waiting = d.meta.status === "waiting_user" && !s.running;
  const q = d.meta.question;
  const [answer, setAnswer] = useState("");
  const [sending, setSending] = useState(false);

  const reply = async (text: string) => {
    if (!text.trim()) return;
    setSending(true);
    try {
      await s.startRun({ answer: text.trim() });
      setAnswer("");
    } finally {
      setSending(false);
    }
  };

  if (s.running) {
    const pct = p.budget ? Math.min(100, Math.round((p.iterations / p.budget) * 100)) : 0;
    const phase = p.phase === "critic" ? "critic is inspecting the drawings" : p.phase === "revising" ? "revising after the critic's review" : p.iterations ? "designing" : "reading the spec";
    return (
      <div className="stack">
        <div className="gcard stack">
          <div className="row-wrap">
            <Spinner size={13} />
            <b>{phase}</b>
            <span className="grow" />
            <span className="num small">{fmtElapsed(p.elapsed)}</span>
          </div>
          <div className="progress" title={p.budget ? `${p.iterations} of ${p.budget} iterations` : ""}>
            <div className="progress-bar" style={{ width: `${Math.max(3, pct)}%` }} />
          </div>
          <div className="row-wrap small dim">
            <span>
              iteration <b className="num">{p.iterations}</b>
              {p.budget ? ` / ${p.budget}` : ""}
            </span>
            <span>·</span>
            <span>
              step <span className="num">{p.step}</span>
            </span>
            {p.model && (
              <>
                <span>·</span>
                <span className="mono">{p.model}</span>
              </>
            )}
          </div>
          {p.tool && (
            <div className="card-tool">
              <span>⚙</span>
              <span className="tool-name">{p.tool.name}</span>
              {p.tool.arg && <span className="tool-arg">{p.tool.arg}</span>}
            </div>
          )}
          {p.note && <div className="small">{p.note}</div>}
          {p.lastIterOk !== null && (
            <div className="row-wrap">
              <Pill tone={p.lastIterOk ? "pass" : "fail"}>{p.lastIterOk ? "last iteration passed" : "last iteration failed"}</Pill>
              {p.failures.slice(0, 4).map((f) => (
                <Pill key={f} tone="fail">
                  {f}
                </Pill>
              ))}
            </div>
          )}
          <button className="btn btn-sm" onClick={s.stopRun}>
            Stop
          </button>
        </div>
        <div className="small dim">Watch the drawings update in the middle pane after every iteration; the timeline tab has every step.</div>
      </div>
    );
  }

  if (waiting && q) {
    return (
      <div className="stack">
        <div className="gcard card-question stack">
          <div className="row-wrap">
            <Pill tone="blue" dot>
              the designer has a question
            </Pill>
          </div>
          <Markdown text={q.question} />
          {q.options && q.options.length > 0 && (
            <div className="choices">
              {q.options.map((o) => (
                <button key={o} className="btn btn-sm btn-choice" onClick={() => reply(o)} disabled={sending}>
                  {o}
                </button>
              ))}
            </div>
          )}
          <div className="chat-input">
            <input
              className="input grow"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Or type an answer…"
              onKeyDown={(e) => {
                if (e.key === "Enter") reply(answer);
              }}
            />
            <button className="btn btn-sm btn-primary" onClick={() => reply(answer)} disabled={sending || !answer.trim()}>
              {sending ? <Spinner size={10} /> : "Reply"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  const st = d.meta.status;
  const last = s.latestIter;
  return (
    <div className="stack">
      {st === "error" && (
        <div className="banner banner-fail">
          <span>The last run hit an error — see the timeline for details. Fix the cause (usually the API key or a spec typo) and run again.</span>
        </div>
      )}
      {st === "stopped" && <div className="small dim">The run was stopped. The last compiled iteration is kept; run again to continue.</div>}
      {st === "budget_exhausted" && (
        <div className="banner banner-warn">
          <span>The designer used its iteration budget without passing every check. Review what's failing, then run again with a note or a bigger budget.</span>
        </div>
      )}
      {last ? (
        <div className="row-wrap">
          <Pill tone={last.ok ? "pass" : "fail"}>
            iteration {last.iteration} {last.ok ? "passes" : "fails"}
          </Pill>
          {last.failures.slice(0, 4).map((f) => (
            <Pill key={f} tone="fail">
              {f}
            </Pill>
          ))}
        </div>
      ) : (
        <div className="small dim">No iterations yet.</div>
      )}
      <RunAgain label={last ? "Run again" : "Design this part"} />
    </div>
  );
}

function RunAgain({ label }: { label: string }) {
  const s = useSession();
  const llm = useLlm();
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async () => {
    if (!llm.ready) {
      llm.openSettings();
      return;
    }
    setBusy(true);
    try {
      await s.startRun({ message: msg.trim() || undefined, budget: 8, critic_rounds: 2 });
      setMsg("");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="stack">
      {!llm.ready && <NotReady what="run the designer" />}
      <textarea className="textarea" rows={2} value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="Optional note for the designer, e.g. make the loop wider for gloved fingers…" />
      <button className="btn btn-primary" onClick={go} disabled={busy || s.running}>
        {busy ? <Spinner size={12} /> : <PlayIcon />} {label}
      </button>
    </div>
  );
}

// ---- 5. review -------------------------------------------------------------------------------------------

function ReviewStage() {
  const s = useSession();
  const llm = useLlm();
  const { toast, error } = useToast();
  const d = s.detail!;
  const last = s.latestIter;
  const critic = d.critic.length ? d.critic[d.critic.length - 1] : null;
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState<"" | "change" | "export">("");

  const change = async () => {
    if (!msg.trim()) return;
    if (!llm.ready) {
      llm.openSettings();
      return;
    }
    setBusy("change");
    try {
      const ok = await s.startRun({ message: msg.trim(), budget: 6, critic_rounds: 1 });
      if (ok) setMsg("");
    } finally {
      setBusy("");
    }
  };

  const doExport = async () => {
    setBusy("export");
    try {
      const r = await kin.export(s.sid);
      toast(`Exported iteration ${r.iteration} — ${Object.keys(r.files).length} files`, "pass");
      await s.refresh();
    } catch (e) {
      error(e, "Export failed");
    } finally {
      setBusy("");
    }
  };

  if (!last) return <div className="small dim">Nothing to review yet — design the part first.</div>;
  const checks = d.checks;
  const hard = checks ? checks.items.filter((i) => i.kind === "hard") : [];
  const hardFail = hard.filter((i) => i.passed === false);
  const soft = checks ? checks.items.filter((i) => i.kind === "soft" && i.passed === false) : [];
  return (
    <div className="stack">
      <div className="gcard stack">
        <div className="row-wrap">
          <Pill tone={last.ok ? "pass" : "fail"}>{last.ok ? "every hard check passes" : `${hardFail.length} hard check${hardFail.length === 1 ? "" : "s"} failing`}</Pill>
          {soft.length > 0 && <Pill tone="warn">{soft.length} soft warning{soft.length === 1 ? "" : "s"}</Pill>}
          {critic && <Pill tone={critic.verdict === "pass" ? "pass" : critic.verdict === "revise" ? "warn" : "neutral"}>critic: {critic.verdict.replace("_", " ")}</Pill>}
        </div>
        {d.meta.narration && <Markdown text={d.meta.narration} />}
        {critic && critic.summary && <div className="small dim">{critic.summary}</div>}
        {checks && (
          <ul className="review-list">
            {hard.slice(0, 8).map((i) => (
              <li key={i.id} className={i.passed === false ? "bad" : ""}>
                <span className="review-mark">{i.passed === false ? "✗" : "✓"}</span>
                <span className="review-lab">{i.label}</span>
                <span className="review-val num">
                  {typeof i.measured === "number" ? fmtNum(i.measured) : ""}
                  {typeof i.target === "number" ? ` / ${fmtNum(i.target)}` : ""}
                  {i.unit && (typeof i.measured === "number" || typeof i.target === "number") ? ` ${i.unit}` : ""}
                </span>
              </li>
            ))}
            {hard.length > 8 && <li className="dim small">…and {hard.length - 8} more in the Checks tab</li>}
          </ul>
        )}
      </div>
      {d.unconfirmed.length > 0 && (
        <div className="banner banner-warn">
          <span>
            <b>Fit not yet confirmed:</b> {d.unconfirmed.join(", ")}. Print the <b>fit coupon</b> (top bar) — three clearances in one small print — and tell Kintsugi
            which slid on, or confirm the measurement in step 3.
          </span>
        </div>
      )}
      <div className="stack">
        <div className="label">Want a change?</div>
        <textarea className="textarea" rows={2} value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="e.g. add a second finger loop, thicken the ring to 4 mm, round the outer edge…" />
        <div className="row-wrap">
          <button className="btn" onClick={change} disabled={busy !== "" || s.running || !msg.trim()}>
            {busy === "change" ? <Spinner size={11} /> : null} Ask the designer
          </button>
          <span className="grow" />
          <button className="btn btn-primary" onClick={doExport} disabled={busy !== "" || s.running || !d.iterations.some((i) => i.compile_ok)}>
            {busy === "export" ? <Spinner size={11} /> : <DownloadIcon />} Looks right — export
          </button>
        </div>
        <span className="small dim">Tweak numbers yourself in the Params tab; every change re-runs the checks.</span>
      </div>
    </div>
  );
}

// ---- 6. export -------------------------------------------------------------------------------------------

function ExportStage() {
  const s = useSession();
  const d = s.detail!;
  const [card, setCard] = useState<string | null>(null);
  const has = (f: string) => d.export.includes(f);
  const v = d.meta.exported_at ?? Date.now();

  useEffect(() => {
    if (!has("print_card.md")) return;
    fetch(fileUrl(s.sid, "export/print_card.md", v))
      .then((r) => (r.ok ? r.text() : ""))
      .then((t) => setCard(t || null))
      .catch(() => setCard(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.sid, v, d.export.join("|")]);

  if (!d.export.length) return <div className="small dim">Nothing exported yet — finish the review step.</div>;
  return (
    <div className="stack">
      <div className="row-wrap">
        {has("part.stl") && (
          <a className="btn btn-primary" href={fileUrl(s.sid, "export/part.stl", v)} download>
            <DownloadIcon /> part.stl
          </a>
        )}
        {has("part.3mf") && (
          <a className="btn" href={fileUrl(s.sid, "export/part.3mf", v)} download>
            part.3mf
          </a>
        )}
        {has("bundle.zip") && (
          <a className="btn" href={fileUrl(s.sid, "export/bundle.zip", v)} download>
            everything (.zip)
          </a>
        )}
      </div>
      <div className="row-wrap small">
        {["part.scad", "blueprint.pdf", "coupon.stl", "print_card.md", "spec.yaml", "session_log.md"].filter(has).map((f) => (
          <a key={f} href={fileUrl(s.sid, `export/${f}`, v)} download>
            {f}
          </a>
        ))}
      </div>
      {typeof d.meta.exported_iteration === "number" && (
        <div className="small dim">
          iteration {d.meta.exported_iteration}
          {d.meta.exported_at ? ` · ${new Date(d.meta.exported_at * 1000).toLocaleString()}` : ""}
        </div>
      )}
      {card && (
        <div className="gcard">
          <div className="label">Print card</div>
          <Markdown text={card} />
        </div>
      )}
      {d.unconfirmed.length > 0 && (
        <div className="banner banner-warn">
          <span>Print <b>coupon.stl</b> first — it has the mating feature at three clearances. Then export again once the fit is confirmed.</span>
        </div>
      )}
    </div>
  );
}

// ---- icons ----------------------------------------------------------------------------------------------------

function CameraIcon(): ReactNode {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
      <path d="M4 8h3l2-3h6l2 3h3v11H4z" />
      <circle cx="12" cy="13" r="3.2" />
    </svg>
  );
}
function PlayIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
      <path d="M6 4l14 8-14 8z" />
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
