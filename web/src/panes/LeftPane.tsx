import { useEffect } from "react";
import { useLocal } from "../hooks";
import { useSession } from "../pages/session-context";
import ChatPane from "./ChatPane";
import GuidePane from "./GuidePane";

type Tab = "guide" | "timeline";

/** Left column: the guided walkthrough, or the full chat & timeline. */
export default function LeftPane() {
  const s = useSession();
  const d = s.detail!;
  const [tab, setTab] = useLocal<Tab>("kin.left.tab", "guide");
  const waiting = d.meta.status === "waiting_user" && !s.running;

  // a question from the designer is answered from the guide; make sure it is visible
  useEffect(() => {
    if (waiting) setTab("guide");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waiting]);

  if (tab === "timeline")
    return (
      <ChatPane
        header={
          <LeftTabs tab={tab} setTab={setTab} events={s.events.length} />
        }
      />
    );
  return (
    <div className="pane">
      <div className="pane-head" style={{ padding: "0 4px" }}>
        <LeftTabs tab={tab} setTab={setTab} events={s.events.length} />
      </div>
      <div className="pane-body">
        <GuidePane />
      </div>
    </div>
  );
}

export function LeftTabs({ tab, setTab, events }: { tab: Tab; setTab: (t: Tab) => void; events: number }) {
  return (
    <div className="tabs" role="tablist" aria-label="Left pane">
      <button role="tab" aria-selected={tab === "guide"} className={`tab${tab === "guide" ? " active" : ""}`} onClick={() => setTab("guide")}>
        Guide
      </button>
      <button role="tab" aria-selected={tab === "timeline"} className={`tab${tab === "timeline" ? " active" : ""}`} onClick={() => setTab("timeline")}>
        Timeline
        {events > 0 && <span className="tab-count">{events}</span>}
      </button>
    </div>
  );
}
