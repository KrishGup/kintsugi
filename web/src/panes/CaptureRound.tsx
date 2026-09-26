import { useRef, useState } from "react";
import { fileUrl, kin } from "../api";
import { useSession } from "../pages/session-context";
import { useToast } from "../toast";
import type { CaptureRequest, Photo, Readiness } from "../types";
import { Pill, Spinner, fmtNum } from "../ui";

/** Which uploaded photos belong to a request label (`r1_photo1_IMG.jpg`). */
export function photosFor(label: string | null | undefined, photos: Photo[]): Photo[] {
  if (!label) return [];
  return photos.filter((p) => {
    const name = p.file.replace(/^photos\//, "");
    return name === label || name.startsWith(label + "_");
  });
}

export function ReadinessBar({ r }: { r: Readiness }) {
  const pct = Math.round((r.score || 0) * 100);
  return (
    <div className="ready">
      <div className="row-wrap">
        <Pill tone={r.ready ? "pass" : "warn"} dot={!r.ready}>
          {r.ready ? "ready to design" : "not ready"}
        </Pill>
        <span className="small">
          <b className="num">{r.confirmed}</b> of <b className="num">{r.interface_dims}</b> fit dimension{r.interface_dims === 1 ? "" : "s"} confirmed
        </span>
      </div>
      <div className="progress" title={`${pct}%`}>
        <div className="progress-bar" style={{ width: "100%", transform: `scaleX(${Math.max(0.03, pct / 100)})`, background: r.ready ? "var(--pass)" : undefined }} />
      </div>
      <div className="small dim">{r.advice}</div>
    </div>
  );
}

/** One request card: a camera slot, a ruler reading, a choice, or the coupon note. */
export function RequestCard({ req, value, onChange }: { req: CaptureRequest; value: string; onChange: (v: string) => void }) {
  const s = useSession();
  const { toast, error } = useToast();
  const d = s.detail!;
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const mine = photosFor(req.label || req.id, d.photos);
  const best = mine.find((p) => p.grade?.ok) || mine[mine.length - 1];
  const measured = mine.flatMap((p) => p.estimates || []);
  const dimNodes = req.dims.map((dim) => ({ dim, spec: dimStatus(d, dim) }));
  const allConfirmed = dimNodes.length > 0 && dimNodes.every((x) => x.spec === "confirmed");
  const pri = req.priority ?? 1;

  const upload = async (list: FileList | null) => {
    if (!list || !list.length) return;
    setBusy(true);
    try {
      const res = await kin.uploadPhotos(s.sid, Array.from(list), true, req.label || req.id);
      const g = res[0]?.grade;
      const est = res[0]?.estimates || [];
      if (est.length) toast(`Measured ${est.map((e) => `${e.dim.split(".").pop()} ${fmtNum(e.value)} mm`).join(", ")}`, "pass");
      else toast(g?.ok ? "Good capture — but no circle could be measured; check the framing" : `Retake: ${g?.instructions?.[0] || "poor capture"}`, "warn");
      await s.refresh();
    } catch (e) {
      error(e, "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`req req-${req.kind}${allConfirmed ? " req-done" : best ? (best.grade?.ok ? " req-ok" : " req-retake") : ""}`}>
      <div className="req-head">
        <span className={`req-pri pri-${pri}`} title={pri === 0 ? "needed for the fit" : pri === 1 ? "should have" : "nice to have"}>
          {req.kind === "photo" ? <CameraIcon /> : req.kind === "measure" ? <RulerIcon /> : req.kind === "coupon" ? <CouponIcon /> : "?"}
        </span>
        <b>{req.title}</b>
        <span className="grow" />
        {allConfirmed ? <Pill tone="pass">confirmed</Pill> : req.kind === "photo" && best ? <Pill tone={best.grade?.ok ? "pass" : "warn"}>{best.grade?.ok ? "captured" : "retake"}</Pill> : pri === 0 ? <Pill tone="fail">needed</Pill> : null}
      </div>
      <div className="small">{req.instructions}</div>
      {req.why && <div className="small dim">— {req.why}</div>}
      <div className="row-wrap" style={{ marginTop: 4 }}>
        {dimNodes.map((x) => (
          <Pill key={x.dim} tone={x.spec === "confirmed" ? "pass" : x.spec === "estimated" ? "warn" : "neutral"} title={`status: ${x.spec}`}>
            {x.dim}
          </Pill>
        ))}
      </div>
      {req.kind === "photo" && (
        <div className="req-body">
          <div className="row-wrap">
            <button className="btn btn-sm btn-primary" onClick={() => input.current?.click()} disabled={busy}>
              {busy ? <Spinner size={11} /> : <CameraIcon />} {best ? "Retake" : "Take / upload photo"}
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
            {measured.length > 0 && (
              <span className="small">
                measured: {measured.map((e) => `${e.dim.split(".").pop()} ${fmtNum(e.value)} mm (${Math.round(e.conf * 100)}%)`).join(" · ")}
              </span>
            )}
          </div>
          {best && best.grade && !best.grade.ok && best.grade.instructions && best.grade.instructions.length > 0 && (
            <ul className="photo-instr">
              {best.grade.instructions.slice(0, 2).map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          )}
          {best && <img className="req-thumb" src={fileUrl(s.sid, best.file)} alt="" loading="lazy" />}
        </div>
      )}
      {req.kind === "measure" && (
        <div className="row" style={{ marginTop: 6 }}>
          <input className="input input-num input-mono" type="number" step="0.1" inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value)} placeholder="—" aria-label={`${req.title} in mm`} />
          <span className="small dim">mm</span>
        </div>
      )}
      {req.kind === "text" && (
        <input className="input" value={value} onChange={(e) => onChange(e.target.value)} placeholder="Your answer (optional)" style={{ marginTop: 6 }} />
      )}
      {req.kind === "choice" && req.options && req.options.length > 0 && (
        <div className="choices">
          {req.options.map((o) => (
            <button key={o} className={`btn btn-sm btn-choice${value === o ? " btn-primary" : ""}`} onClick={() => onChange(value === o ? "" : o)}>
              {o}
            </button>
          ))}
        </div>
      )}
      {req.kind === "coupon" && <div className="small dim">Available from the <b>Coupon</b> button once the part is designed.</div>}
    </div>
  );
}

function dimStatus(d: { spec: { interfaces?: Array<{ id: string; dims?: Record<string, { status?: string }> }>; requirements?: Array<{ id: string; derived?: Record<string, { status?: string }> }> } }, dim: string): string {
  const [head, name] = dim.split(".");
  const itf = d.spec.interfaces?.find((i) => i.id === head);
  if (itf?.dims?.[name]) return itf.dims[name].status || "unknown";
  const req = d.spec.requirements?.find((r) => r.id === head);
  if (req?.derived?.[name]) return req.derived[name].status || "unknown";
  return "unknown";
}

export function CameraIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
      <path d="M4 8h3l2-3h6l2 3h3v11H4z" />
      <circle cx="12" cy="13" r="3.2" />
    </svg>
  );
}
export function RulerIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
      <rect x="3" y="8" width="18" height="8" rx="1" />
      <path d="M7 8v3M11 8v4M15 8v3M19 8v4" />
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
