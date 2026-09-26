import { useEffect, useRef } from "react";
import { useSession } from "../pages/session-context";
import { STAGES, stageIndex } from "./GuidePane";
import type { Stage } from "../types";

/** Slim horizontal stepper under the top bar: intake → capture → spec → design → review → export. */
export default function StageBar() {
  const s = useSession();
  const d = s.detail!;
  const cur: Stage = s.running ? "design" : (d.stage as Stage);
  const idx = stageIndex(cur);
  const ref = useRef<HTMLOListElement>(null);
  useEffect(() => {
    // on a phone the bar scrolls; keep the current stage in view
    const el = ref.current?.querySelector<HTMLElement>(".stage.current");
    if (el && ref.current && ref.current.scrollWidth > ref.current.clientWidth) el.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
  }, [idx]);
  return (
    <ol className="stagebar" aria-label="Progress" ref={ref}>
      {STAGES.map((st, i) => (
        <li key={st.id} className={`stage ${i < idx ? "done" : i === idx ? "current" : "todo"}`} aria-current={i === idx ? "step" : undefined}>
          <span className="stage-n" aria-hidden="true">
            {i < idx ? <CheckMark /> : i + 1}
          </span>
          <span className="stage-l">{st.short}</span>
        </li>
      ))}
    </ol>
  );
}

function CheckMark() {
  return (
    <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m4 12.5 5 5L20 6.5" />
    </svg>
  );
}
