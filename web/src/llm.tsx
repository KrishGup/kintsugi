import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { kin } from "./api";
import { useDismiss } from "./hooks";
import { ChevronDown, ChevronRight, Close } from "./icons";
import { useToast } from "./toast";
import type { LlmStatus, SettingsInfo } from "./types";
import { Pill, Spinner } from "./ui";

interface LlmApi {
  status: LlmStatus | null;
  version: string | null;
  openscad: string | null | undefined;
  ready: boolean;
  /** the deployment sets provider, key and models; the Settings dialog is read-only */
  locked: boolean;
  refresh: () => Promise<void>;
  openSettings: () => void;
}

const Ctx = createContext<LlmApi>({ status: null, version: null, openscad: undefined, ready: false, locked: false, refresh: async () => {}, openSettings: () => {} });

export function useLlm(): LlmApi {
  return useContext(Ctx);
}

/** Fetches /api/health once, exposes the model-provider status and owns the Settings modal. */
export function LlmProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<LlmStatus | null>(null);
  const [version, setVersion] = useState<string | null>(null);
  const [openscad, setOpenscad] = useState<string | null | undefined>(undefined);
  const [locked, setLocked] = useState(false);
  const [open, setOpen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const h = await kin.health();
      setStatus(h.llm || null);
      setVersion(h.version);
      setOpenscad(h.openscad);
      setLocked(!!h.settings_locked);
    } catch {
      /* the header shows "server unreachable" through a null status */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const value = useMemo<LlmApi>(
    () => ({ status, version, openscad, locked, ready: !!status?.ready, refresh, openSettings: () => setOpen(true) }),
    [status, version, openscad, locked, refresh],
  );

  return (
    <Ctx.Provider value={value}>
      {children}
      {open && <SettingsModal onClose={() => setOpen(false)} />}
    </Ctx.Provider>
  );
}

export function providerLabel(p: string | undefined): string {
  switch (p) {
    case "openai":
      return "OpenAI";
    case "fake":
      return "Demo mode";
    default:
      return p || "—";
  }
}

/** Header pill: "OpenAI · gpt-6-astra", "Demo mode", or "Add API key" when the provider is not ready. Click opens Settings. */
export function ProviderPill() {
  const llm = useLlm();
  const s = llm.status;
  if (!s)
    return (
      <button className="pill pill-neutral pill-btn" onClick={llm.openSettings} aria-label="Model settings">
        provider…
      </button>
    );
  const tone = !s.ready ? "warn" : s.provider === "fake" ? "neutral" : "pass";
  const text = !s.ready ? (llm.locked ? "No model configured" : "Add OpenAI API key") : s.provider === "fake" ? "Demo mode" : `${providerLabel(s.provider)} · ${s.models.designer || ""}`;
  const short = !s.ready ? (llm.locked ? "No model" : "No key") : s.provider === "fake" ? "Demo" : providerLabel(s.provider);
  return (
    <button className={`pill pill-${tone} pill-btn`} onClick={llm.openSettings} aria-label={`Model settings — ${s.reason}`}>
      <span className="pill-dot" />
      <span className="pill-long">{text}</span>
      <span className="pill-short">{short}</span>
    </button>
  );
}

const OPENAI_MODELS = ["gpt-6-astra", "gpt-6-sol", "gpt-6-luna"];
const EFFORTS = ["low", "medium", "high", "max"];

const MODEL_NOTES: Record<string, string> = {
  "gpt-6-astra": "flagship reasoning — best design quality (default)",
  "gpt-6-sol": "fast & inexpensive — fine for the critic and vision passes",
  "gpt-6-luna": "balanced",
};

export function SettingsModal({ onClose }: { onClose: () => void }) {
  const llm = useLlm();
  const { toast, error } = useToast();
  const box = useRef<HTMLDivElement>(null);
  useDismiss(true, onClose, box);
  const [info, setInfo] = useState<SettingsInfo | null>(null);
  const [saving, setSaving] = useState(false);
  const [key, setKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [provider, setProvider] = useState("openai");
  const [designer, setDesigner] = useState("gpt-6-astra");
  const [critic, setCritic] = useState("gpt-6-astra");
  const [vision, setVision] = useState("gpt-6-astra");
  const [effort, setEffort] = useState("high");
  const [persist, setPersist] = useState(true);
  const [advanced, setAdvanced] = useState(false);

  useEffect(() => {
    kin
      .settings()
      .then((i) => {
        setInfo(i);
        setProvider(i.llm.provider);
        setDesigner(i.llm.models.designer || "gpt-6-astra");
        setCritic(i.llm.models.critic || "gpt-6-astra");
        setVision(i.llm.models.vision || "gpt-6-astra");
        setEffort(i.llm.effort || "high");
      })
      .catch((e) => error(e, "Could not load settings"));
  }, [error]);

  const save = async () => {
    setSaving(true);
    try {
      const body = {
        openai_api_key: key.trim() || undefined,
        provider,
        designer_model: provider === "openai" ? designer : undefined,
        critic_model: provider === "openai" ? critic : undefined,
        vision_model: provider === "openai" ? vision : undefined,
        effort: provider === "openai" ? effort : undefined,
        persist,
      };
      const r = await kin.setSettings(body);
      await llm.refresh();
      setKey("");
      if (r.probe && r.probe.checked && r.probe.ok === false) {
        toast(r.probe.message || "OpenAI rejected the settings", "fail");
        setInfo(await kin.settings());
        return;
      }
      if (r.llm.ready) {
        const verified = r.probe && r.probe.ok === true ? " · key verified" : r.probe && r.probe.ok === null ? ` · ${r.probe.message}` : "";
        toast(`Ready — ${providerLabel(r.llm.provider)}${r.llm.models.designer ? ` · ${r.llm.models.designer}` : ""}${verified}`, r.probe && r.probe.ok === null ? "warn" : "pass");
        onClose();
      } else {
        toast(`Saved, but the provider is not ready: ${r.llm.reason}`, "warn");
        setInfo(await kin.settings());
      }
    } catch (e) {
      error(e, "Could not save settings");
    } finally {
      setSaving(false);
    }
  };

  const hasKey = !!info?.openai_key_masked;
  const openaiReady = provider !== "openai" || hasKey || key.trim().length > 0;
  const locked = !!info?.locked;

  return (
    <div className="modal-back" role="presentation">
      <div className="modal" role="dialog" aria-modal="true" aria-label="Model settings" ref={box}>
        <div className="modal-head">
          <h2>Model settings</h2>
          <span className="grow" />
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            <Close size={18} />
          </button>
        </div>
        {!info ? (
          <div className="modal-body">
            <Spinner label="Loading…" />
          </div>
        ) : (
          <div className="modal-body stack">
            <div className="row-wrap">
              <span className="label">Status</span>
              <Pill tone={info.llm.ready ? "pass" : "warn"} dot>
                {info.llm.ready ? "ready" : "not ready"}
              </Pill>
              <span className="small dim">{info.llm.reason}</span>
            </div>

            {locked && (
              <div className="banner banner-blue">
                <span>
                  <b>Managed by the server.</b> The provider, key and models are set in the deployment's configuration
                  {info.llm.provider === "openai" && info.llm.models.designer ? (
                    <>
                      {" "}
                      (<span className="num">{info.llm.models.designer}</span>)
                    </>
                  ) : null}
                  ; nothing here can be changed from the browser.
                </span>
              </div>
            )}

            <div className="field">
              <span className="field-label">Provider</span>
              <div className="seg" role="radiogroup" aria-label="Provider">
                {[
                  ["openai", "OpenAI (GPT-6)"],
                  ["fake", "Demo mode"],
                ].map(([v, l]) => (
                  <button
                    key={v}
                    role="radio"
                    aria-checked={provider === v}
                    className={`seg-btn${provider === v ? " active" : ""}`}
                    onClick={() => setProvider(v)}
                    disabled={locked}
                  >
                    {l}
                  </button>
                ))}
              </div>
              <span className="field-hint">
                {provider === "openai"
                  ? "The designer, critic and intake run on the OpenAI Responses API with your key."
                  : "A scripted designer that builds from the templates — no key, no cost. Good for a UI walkthrough."}
              </span>
            </div>

            {provider === "openai" && !locked && (
              <>
                <label className="field">
                  <span className="field-label">
                    OpenAI API key{" "}
                    {hasKey && <Pill tone="pass">on the server: {info.openai_key_masked}</Pill>}
                  </span>
                  <div className="row">
                    <input
                      className="input input-mono grow"
                      type={showKey ? "text" : "password"}
                      value={key}
                      onChange={(e) => setKey(e.target.value)}
                      placeholder={hasKey ? "Paste a new key to replace the configured one" : "sk-…"}
                      autoComplete="off"
                      spellCheck={false}
                      autoFocus={!hasKey}
                    />
                    <button className="btn btn-sm" onClick={() => setShowKey((v) => !v)} type="button">
                      {showKey ? "Hide" : "Show"}
                    </button>
                  </div>
                  <span className="field-hint">
                    The key stays on this server (in memory, and in <code>.env</code> if you tick “remember”). It is never sent anywhere but OpenAI.
                  </span>
                </label>

                <button className="btn btn-ghost btn-sm" style={{ alignSelf: "flex-start" }} onClick={() => setAdvanced((v) => !v)}>
                  {advanced ? <ChevronDown size={16} /> : <ChevronRight size={16} />} Models &amp; reasoning effort
                </button>
                {advanced && (
                  <div className="stack settings-adv">
                    <ModelSelect label="Designer" value={designer} onChange={setDesigner} />
                    <ModelSelect label="Critic" value={critic} onChange={setCritic} />
                    <ModelSelect label="Intake / vision" value={vision} onChange={setVision} />
                    <label className="field">
                      <span className="field-label">Reasoning effort</span>
                      <select className="select" value={effort} onChange={(e) => setEffort(e.target.value)}>
                        {EFFORTS.map((e) => (
                          <option key={e} value={e}>
                            {e}
                          </option>
                        ))}
                      </select>
                      <span className="field-hint">“high” is the sweet spot for the design loop; “max” thinks longer on every step.</span>
                    </label>
                  </div>
                )}
              </>
            )}

            {provider === "openai" && locked && (
              <div className="row-wrap">
                <span className="label">Key</span>
                <Pill tone={hasKey ? "pass" : "fail"}>{hasKey ? info.openai_key_masked : "none configured"}</Pill>
                <span className="label">Models</span>
                <span className="small num">
                  {info.llm.models.designer} · {info.llm.models.critic} · {info.llm.models.vision}
                </span>
                {info.llm.effort && <Pill tone="neutral">effort {info.llm.effort}</Pill>}
              </div>
            )}

            {!locked && (
              <label className="check">
                <input type="checkbox" checked={persist} onChange={(e) => setPersist(e.target.checked)} />
                <span>
                  Remember on this server (<code>.env</code>)
                </span>
              </label>
            )}

            <div className="row">
              {locked ? (
                <button className="btn btn-primary" onClick={onClose}>
                  Close
                </button>
              ) : (
                <>
                  <button className="btn btn-primary" onClick={save} disabled={saving || !openaiReady}>
                    {saving ? <Spinner size={16} /> : null} Save
                  </button>
                  <button className="btn btn-ghost" onClick={onClose}>
                    Cancel
                  </button>
                  {!openaiReady && <span className="small dim">Paste your OpenAI API key to continue.</span>}
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ModelSelect({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const custom = !OPENAI_MODELS.includes(value);
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <select className="select" value={custom ? "__custom" : value} onChange={(e) => onChange(e.target.value === "__custom" ? "" : e.target.value)}>
        {OPENAI_MODELS.map((m) => (
          <option key={m} value={m}>
            {m} — {MODEL_NOTES[m]}
          </option>
        ))}
        <option value="__custom">custom…</option>
      </select>
      {custom && <input className="input input-mono" value={value} onChange={(e) => onChange(e.target.value)} placeholder="model id" />}
    </label>
  );
}
