import { useSession } from "../pages/session-context";
import type { CheckItem } from "../types";
import { Empty, Pill, fmtNum } from "../ui";

function targetText(it: CheckItem): string {
  if (it.target === null || it.target === undefined) return "—";
  const t = fmtNum(it.target);
  if (typeof it.target === "number" && typeof it.tol === "number") return `${t} ±${fmtNum(it.tol)}`;
  return t;
}

export default function ChecksTab() {
  const s = useSession();
  const d = s.detail!;
  const c = d.checks;
  if (!c) {
    return (
      <Empty title="No checks yet" icon={<RulerIcon />}>
        After the first iteration compiles, every spec dimension is measured on the exported mesh and listed here with pass / fail against its
        tolerance, plus wall thickness, printability and interference checks.
      </Empty>
    );
  }
  const hard = c.items.filter((i) => i.kind === "hard");
  const hardFail = hard.filter((i) => i.passed === false).length;
  const st = c.stats;
  const best = c.orientations && c.orientations[0];
  const latestN = s.latestIter?.iteration;

  return (
    <div>
      <div className="row-wrap mb">
        <Pill tone={c.all_hard_pass ? "pass" : "fail"}>{c.all_hard_pass ? "all hard checks pass" : `${hardFail} hard check${hardFail === 1 ? "" : "s"} failing`}</Pill>
        <span className="small muted num">
          iteration {c.iteration}
          {latestN !== undefined && c.iteration !== latestN ? ` (latest ${latestN})` : ""}
        </span>
      </div>
      <div className="summary-line">
        {st && st.bbox && (
          <span>
            bbox <b>{st.bbox.size.map((x) => fmtNum(x, 1)).join(" × ")}</b> mm
          </span>
        )}
        {st && typeof st.volume_mm3 === "number" && (
          <span>
            volume <b>{fmtNum(st.volume_mm3 / 1000, 1)}</b> cm³
          </span>
        )}
        {st && (
          <span>
            <b>{st.triangles?.toLocaleString()}</b> tris · {st.watertight ? "watertight" : "not watertight"} · {st.bodies ?? 1} bod{(st.bodies ?? 1) === 1 ? "y" : "ies"}
          </span>
        )}
        {c.walls && (
          <span>
            walls p05 <b>{fmtNum(c.walls.p05)}</b> / min <b>{fmtNum(c.walls.min)}</b> / req <b>{fmtNum(c.walls.required)}</b> mm
          </span>
        )}
        {c.printability && (
          <span>
            overhang <b>{fmtNum(c.printability.overhang_fraction * 100, 1)}%</b> · bed contact <b>{fmtNum(c.printability.bed_contact_area, 0)}</b> mm² · height{" "}
            <b>{fmtNum(c.printability.height, 1)}</b> mm
          </span>
        )}
        {best && best.name && (
          <span>
            best orientation <b>{best.name}</b>
            {typeof best.overhang_fraction === "number" ? ` (${fmtNum(best.overhang_fraction * 100, 1)}%)` : ""}
          </span>
        )}
      </div>
      <table className="table table-flush table-checks">
        <colgroup>
          <col className="c-check" />
          <col className="c-val" />
          <col className="c-st" />
        </colgroup>
        <thead>
          <tr>
            <th>Check</th>
            <th title="measured on the mesh → target from the spec">Measured</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {c.items.map((it) => (
            <tr key={it.id}>
              <td>
                <div className="check-id">{it.id}</div>
                <div className="small dim">{it.label}</div>
                {it.detail && <div className="check-detail">{it.detail}</div>}
              </td>
              <td>
                <div className="val-meas" title="measured on the exported mesh">
                  {fmtNum(it.measured)}
                  {it.unit ? <span className="muted"> {it.unit}</span> : null}
                </div>
                {it.target !== null && it.target !== undefined && (
                  <div className="val-target" title="target from the spec">
                    {targetText(it)}
                  </div>
                )}
              </td>
              <td>
                <Pill tone={it.passed === true ? "pass" : it.passed === false ? (it.kind === "hard" ? "fail" : "warn") : "neutral"} title={`${it.kind} check`}>
                  {it.passed === true ? "pass" : it.passed === false ? (it.kind === "hard" ? "fail" : "soft") : "info"}
                </Pill>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {c.sections && c.sections.length > 0 && (
        <div className="small muted mt">
          Sections: {c.sections.map((x) => `${x.plane_axis} = ${fmtNum(x.at, 1)}${x.dims.length ? ` (${x.dims.join(", ")})` : ""}`).join(" · ")}
        </div>
      )}
    </div>
  );
}

function RulerIcon() {
  return (
    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round">
      <rect x="2" y="8" width="20" height="8" rx="1" />
      <path d="M6 8v3M10 8v4M14 8v3M18 8v4" />
    </svg>
  );
}
