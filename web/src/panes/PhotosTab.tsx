import { useEffect, useMemo, useRef, useState } from "react";
import { fileUrl, kin, sheetPdfUrl } from "../api";
import { useSession } from "../pages/session-context";
import { useToast } from "../toast";
import type { MeasureResult, Photo } from "../types";
import { Empty, Pill, Spinner, fmtNum } from "../ui";

export default function PhotosTab() {
  const s = useSession();
  const { toast, error } = useToast();
  const d = s.detail!;
  const [expectSheet, setExpectSheet] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [lightbox, setLightbox] = useState<string | null>(null);
  const [measuring, setMeasuring] = useState<string | null>(null); // photo file with the open measure form
  const input = useRef<HTMLInputElement>(null);

  const dims = useMemo(() => {
    const out: string[] = [];
    for (const itf of d.spec.interfaces || []) for (const k of Object.keys(itf.dims || {})) out.push(`${itf.id}.${k}`);
    for (const r of d.spec.requirements || []) for (const k of Object.keys(r.derived || {})) out.push(`${r.id}.${k}`);
    return out;
  }, [d.spec]);

  const upload = async (files: FileList | null) => {
    if (!files || !files.length) return;
    setUploading(true);
    try {
      const res = await kin.uploadPhotos(s.sid, Array.from(files), expectSheet);
      const good = res.filter((p) => p.grade?.ok).length;
      toast(`${res.length} photo${res.length === 1 ? "" : "s"} uploaded · ${good} good capture${good === 1 ? "" : "s"}`, good === res.length ? "pass" : "warn");
      await s.refresh();
    } catch (e) {
      error(e, "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div>
      <div className="row-wrap mb">
        <button className="btn btn-primary btn-sm" onClick={() => input.current?.click()} disabled={uploading}>
          {uploading ? <Spinner size={11} /> : null} Upload photos
        </button>
        <input
          ref={input}
          type="file"
          accept="image/*"
          multiple
          hidden
          onChange={(e) => {
            upload(e.target.files);
            e.target.value = "";
          }}
        />
        <label className="check small">
          <input type="checkbox" checked={expectSheet} onChange={(e) => setExpectSheet(e.target.checked)} />
          <span>on calibration sheet</span>
        </label>
        <a className="small" href={sheetPdfUrl} target="_blank" rel="noreferrer">
          sheet PDF ↗
        </a>
      </div>

      {d.photos.length === 0 ? (
        <Empty title="No photos yet" icon={<CameraIcon />}>
          Photos are graded on upload (sharpness, exposure, tilt, markers). Shots taken straight down on the calibration sheet can be measured
          to attach estimates to spec dimensions.
        </Empty>
      ) : (
        <div className="photo-grid">
          {d.photos.map((p) => (
            <PhotoCard
              key={p.file}
              photo={p}
              selected={measuring === p.file}
              onOpen={() => setLightbox(fileUrl(s.sid, p.file))}
              onMeasure={() => setMeasuring(measuring === p.file ? null : p.file)}
            />
          ))}
        </div>
      )}

      {measuring && d.photos.some((p) => p.file === measuring) && <MeasurePanel photo={measuring} dims={dims} onClose={() => setMeasuring(null)} />}

      {lightbox && (
        <div className="lightbox" onClick={() => setLightbox(null)} role="dialog" aria-label="Photo">
          <img src={lightbox} alt="Photo" />
        </div>
      )}
    </div>
  );
}

function PhotoCard({ photo, selected, onOpen, onMeasure }: { photo: Photo; selected: boolean; onOpen: () => void; onMeasure: () => void }) {
  const s = useSession();
  const g = photo.grade;
  const name = photo.file.replace(/^photos\//, "");
  return (
    <div className={`photo-card${selected ? " selected" : ""}`}>
      <img className="photo-thumb" src={fileUrl(s.sid, photo.file)} alt={name} loading="lazy" onClick={onOpen} />
      <div className="photo-meta">
        <div className="photo-name" title={name}>
          {name}
        </div>
        {g ? (
          g.error ? (
            <>
              <Pill tone="fail">grade failed</Pill>
              <div className="small dim">{g.error}</div>
            </>
          ) : (
            <div className="photo-pills hover-anchor">
              <span className="hover-card below" role="tooltip">
                sharpness <b className="num">{fmtNum(g.sharpness, 1)}</b>
                {g.edge_width_px ? (
                  <>
                    {" "}
                    · edge <b className="num">{fmtNum(g.edge_width_px, 1)} px</b>
                  </>
                ) : null}{" "}
                · brightness <b className="num">{fmtNum(g.mean_brightness, 0)}</b>
              </span>
              <Pill tone={g.ok ? "pass" : "fail"}>{g.ok ? "good capture" : "retake"}</Pill>
              <Pill tone={g.sharpness_ok ? "pass" : "fail"}>{g.sharpness_ok ? "sharp" : "blurry"}</Pill>
              <Pill tone={g.exposure_ok ? "pass" : "warn"}>{g.exposure_ok ? "exposed" : "exposure"}</Pill>
              <Pill tone={typeof g.tilt_deg === "number" ? (g.tilt_ok ? "pass" : "fail") : "neutral"}>
                tilt {typeof g.tilt_deg === "number" ? `${fmtNum(g.tilt_deg, 0)}°` : "—"}
              </Pill>
              <Pill tone={(g.markers_found ?? 0) >= 4 ? "pass" : (g.markers_found ?? 0) > 0 ? "warn" : "neutral"}>
                {g.markers_found ?? 0} marker{g.markers_found === 1 ? "" : "s"}
              </Pill>
            </div>
          )
        ) : (
          <Pill tone="neutral">not graded</Pill>
        )}
        {g && g.instructions && g.instructions.length > 0 && (
          <ul className="photo-instr">
            {g.instructions.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        )}
        <button className={`btn btn-xs${selected ? " btn-primary" : ""}`} onClick={onMeasure}>
          {selected ? "Measuring…" : "Measure"}
        </button>
      </div>
    </div>
  );
}

function MeasurePanel({ photo, dims, onClose }: { photo: string; dims: string[]; onClose: () => void }) {
  const s = useSession();
  const { toast, error } = useToast();
  const [mode, setMode] = useState<"sheet" | "reference">("sheet");
  const [dim, setDim] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<MeasureResult | null>(null);
  const [showPoly, setShowPoly] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    box.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [photo, res]);

  const go = async () => {
    setBusy(true);
    setRes(null);
    try {
      const r = await kin.measure(s.sid, { photo, mode, dim: dim || null });
      setRes(r);
      const c = r.circles && r.circles[0];
      toast(
        c ? `Largest circle ⌀ ${fmtNum(c.d)} mm${r.attached_to ? ` → attached to ${r.attached_to}` : ""}` : "No circles found in this photo",
        c ? "pass" : "warn",
      );
      if (r.attached_to) await s.refresh();
    } catch (e) {
      error(e, "Measurement failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="measure-result" ref={box}>
      <div className="row-wrap">
        <span className="label">Measure</span>
        <span className="mono small">{photo.replace(/^photos\//, "")}</span>
        <span className="grow" />
        <button className="btn btn-ghost btn-xs" onClick={onClose}>
          Close
        </button>
      </div>
      <div className="row-wrap mt">
        <label className="field">
          <span className="field-label">Mode</span>
          <select className="select" value={mode} onChange={(e) => setMode(e.target.value as "sheet" | "reference")} style={{ width: 150 }}>
            <option value="sheet">calibration sheet</option>
            <option value="reference">reference object</option>
          </select>
        </label>
        <label className="field grow">
          <span className="field-label">Attach to dimension</span>
          <select className="select" value={dim} onChange={(e) => setDim(e.target.value)}>
            <option value="">(just measure)</option>
            {dims.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
        </label>
        <button className="btn btn-primary btn-sm" onClick={go} disabled={busy} style={{ alignSelf: "flex-end" }}>
          {busy ? <Spinner size={11} /> : null} Measure
        </button>
      </div>
      <div className="field-hint mt">
        {mode === "sheet"
          ? "Rectifies the photo from the ArUco markers (needs ≥ 2) and fits circles in the sheet plane at 0.1 mm/px."
          : "Scales from a known reference object (coin, card) detected in the photo; lower confidence, no perspective correction."}
      </div>
      {res && (
        <div className="mt">
          <div className="row-wrap">
            {typeof res.markers === "number" && <Pill tone={res.markers >= 4 ? "pass" : "warn"}>{res.markers} markers</Pill>}
            {typeof res.tilt_deg === "number" && <Pill tone={res.tilt_deg <= 20 ? "pass" : "warn"}>tilt {fmtNum(res.tilt_deg, 1)}°</Pill>}
            {res.reference && (
              <Pill tone="blue">
                {res.reference.kind} · {fmtNum(res.reference.mm_per_px, 4)} mm/px
              </Pill>
            )}
            {typeof res.outline_points === "number" && res.outline_points > 0 && <Pill tone="neutral">outline {res.outline_points} pts</Pill>}
            {res.attached_to && <Pill tone="pass">estimate → {res.attached_to}</Pill>}
          </div>
          {res.circles && res.circles.length > 0 ? (
            <table className="table mt">
              <thead>
                <tr>
                  <th>#</th>
                  <th className="num">⌀ mm</th>
                  <th className="num">cx</th>
                  <th className="num">cy</th>
                  <th className="num">conf</th>
                  <th>method</th>
                </tr>
              </thead>
              <tbody>
                {res.circles.map((c, i) => (
                  <tr key={i}>
                    <td className="num">{i + 1}</td>
                    <td className="num">
                      <b>{fmtNum(c.d)}</b>
                    </td>
                    <td className="num">{fmtNum(c.cx, 1)}</td>
                    <td className="num">{fmtNum(c.cy, 1)}</td>
                    <td className="num">{typeof c.conf === "number" ? fmtNum(c.conf) : "—"}</td>
                    <td className="mono small">{c.method || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="small muted mt">No circles found.</div>
          )}
          {res.rectified && (
            <div className="mt">
              <div className="label">Rectified (0.1 mm / px)</div>
              <a href={fileUrl(s.sid, res.rectified, Date.now())} target="_blank" rel="noreferrer">
                <img src={fileUrl(s.sid, res.rectified, Date.now())} alt="Rectified photo" />
              </a>
            </div>
          )}
          {res.openscad_polygon && (
            <div className="mt">
              <button className="btn btn-ghost btn-xs" onClick={() => setShowPoly((v) => !v)}>
                {showPoly ? "Hide" : "Show"} OpenSCAD outline polygon
              </button>
              {showPoly && <pre className="md-code">{res.openscad_polygon}</pre>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CameraIcon() {
  return (
    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round">
      <path d="M4 8h3l2-3h6l2 3h3v11H4z" />
      <circle cx="12" cy="13" r="3.2" />
    </svg>
  );
}
