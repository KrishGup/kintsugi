import { useEffect } from "react";
import { useCustomizer } from "../customizer/context";
import { useLocal } from "../hooks";
import { Check } from "../icons";
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
  const cz = useCustomizer();
  const d = s.detail!;
  const [tab, setTab] = useLocal<Tab>("kin.right.tab", "checks");

  // other panes (the guide's "Customize" card, the 3D view's draft pill) can open a tab here
  useEffect(() => {
    const onOpen = (e: Event) => {
      const t = (e as CustomEvent<Tab>).detail;
      if (t) setTab(t);
      document.querySelector(".ws-right")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    };
    window.addEventListener("kin:right-tab", onOpen);
    return () => window.removeEventListener("kin:right-tab", onOpen);
  }, [setTab]);

  const hardFails = d.checks ? d.checks.items.filter((i) => i.kind === "hard" && i.passed === false).length : 0;
  const tabs: Array<{ id: Tab; label: string; count?: React.ReactNode; tone?: "pass" | "fail"; title?: string }> = [
    {
      id: "checks",
      label: "Checks",
      count: d.checks ? (hardFails ? hardFails : <Check size={10} />) : undefined,
      tone: d.checks ? (hardFails ? "fail" : "pass") : undefined,
      title: d.checks ? (hardFails ? `${hardFails} hard checks failing` : "all hard checks pass") : "no checks yet",
    },
    { id: "params", label: "Customize", count: cz.nChanged || undefined, title: cz.nChanged ? `${cz.nChanged} parameter${cz.nChanged === 1 ? "" : "s"} changed (draft)` : "sliders, switches and presets for every parameter" },
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
            <button key={t.id} role="tab" aria-selected={tab === t.id} className={`tab${tab === t.id ? " active" : ""}`} onClick={() => setTab(t.id)} aria-label={t.title ? `${t.label}: ${t.title}` : undefined}>
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
