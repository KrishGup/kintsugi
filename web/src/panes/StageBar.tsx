import { useSession } from "../pages/session-context";
import { STAGES, stageIndex } from "./GuidePane";
import type { Stage } from "../types";

/** Slim horizontal stepper under the top bar: intake → capture → spec → design → review → export. */
export default function StageBar() {
  const s = useSession();
  const d = s.detail!;
  const cur: Stage = s.running ? "design" : (d.stage as Stage);
  const idx = stageIndex(cur);
  return (
    <ol className="stagebar" aria-label="Progress">
      {STAGES.map((st, i) => (
        <li key={st.id} className={`stage ${i < idx ? "done" : i === idx ? "current" : "todo"}`} aria-current={i === idx ? "step" : undefined}>
          <span className="stage-n">{i < idx ? "✓" : i + 1}</span>
          <span className="stage-l">{st.short}</span>
        </li>
      ))}
    </ol>
  );
}
