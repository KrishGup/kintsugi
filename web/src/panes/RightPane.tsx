import { useLocal } from "../hooks";
import { useSession } from "../pages/session-context";
import ChecksTab from "./ChecksTab";
import CodeTab from "./CodeTab";
import ParamsTab from "./ParamsTab";
import PhotosTab from "./PhotosTab";
import PipelineTab from "./PipelineTab";
import SpecTab from "./SpecTab";

type Tab = "checks" | "params" | "code" | "spec" | "photos" | "graph";

export default function RightPane() {
  const s = useSession();
  const d = s.detail!;
  const [tab, setTab] = useLocal<Tab>("kin.right.tab", "checks");

  const hardFails = d.checks ? d.checks.items.filter((i) => i.kind === "hard" && i.passed === false).length : 0;
  const tabs: Array<{ id: Tab; label: string; count?: string | number; tone?: "pass" | "fail"; title?: string }> = [
    {
      id: "checks",
      label: "Checks",
      count: d.checks ? (hardFails ? hardFails : "✓") : undefined,
      tone: d.checks ? (hardFails ? "fail" : "pass") : undefined,
      title: d.checks ? (hardFails ? `${hardFails} hard checks failing` : "all hard checks pass") : "no checks yet",
    },
    { id: "params", label: "Params" },
    { id: "code", label: "Code" },
    { id: "spec", label: "Spec", count: d.unconfirmed.length || undefined, tone: d.unconfirmed.length ? "fail" : undefined, title: d.unconfirmed.length ? `${d.unconfirmed.length} interface dims unconfirmed` : undefined },
    { id: "photos", label: "Photos", count: d.photos.length || undefined },
    { id: "graph", label: "Graph", title: "the dataflow graphs behind the session" },
  ];

  return (
    <div className="pane">
      <div className="pane-head" style={{ padding: "0 4px" }}>
        <div className="tabs" role="tablist" aria-label="Details">
          {tabs.map((t) => (
            <button key={t.id} role="tab" aria-selected={tab === t.id} className={`tab${tab === t.id ? " active" : ""}`} onClick={() => setTab(t.id)} title={t.title}>
              {t.label}
              {t.count !== undefined && (
                <span className="tab-count" style={t.tone ? { color: `var(--${t.tone})`, background: `var(--${t.tone}-soft)` } : undefined}>
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>
      {tab === "checks" && (
        <div className="pane-body">
          <ChecksTab />
        </div>
      )}
      {tab === "params" && (
        <div className="pane-body">
          <ParamsTab />
        </div>
      )}
      {tab === "code" && (
        <div className="pane-body pane-body-flush">
          <CodeTab />
        </div>
      )}
      {tab === "spec" && (
        <div className="pane-body pane-body-flush">
          <SpecTab />
        </div>
      )}
      {tab === "photos" && (
        <div className="pane-body">
          <PhotosTab />
        </div>
      )}
      {tab === "graph" && (
        <div className="pane-body">
          <PipelineTab />
        </div>
      )}
    </div>
  );
}
