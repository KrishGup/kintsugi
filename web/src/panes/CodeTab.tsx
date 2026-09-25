import { useEffect, useRef, useState } from "react";
import { fileUrl, kin } from "../api";
import CodeEditor from "../components/CodeEditor";
import { useSession } from "../pages/session-context";
import { useToast } from "../toast";
import { Pill, Spinner } from "../ui";
import { describeIteration } from "./ParamsTab";

export default function CodeTab() {
  const s = useSession();
  const { toast, error } = useToast();
  const d = s.detail!;
  const remote = d.scad ?? "";
  const [text, setText] = useState(remote);
  const [dirty, setDirty] = useState(false);
  const [running, setRunning] = useState(false);
  const [label, setLabel] = useState("");
  const lastRemote = useRef(remote);
  const [stale, setStale] = useState(false);

  // follow the file on disk unless the user has local edits
  useEffect(() => {
    if (remote === lastRemote.current) return;
    lastRemote.current = remote;
    if (!dirty) {
      setText(remote);
      setStale(false);
    } else setStale(true);
  }, [remote, dirty]);

  const onChange = (v: string) => {
    setText(v);
    setDirty(v !== lastRemote.current);
  };

  const reload = () => {
    setText(remote);
    setDirty(false);
    setStale(false);
  };

  const run = async () => {
    if (!text.trim()) {
      toast("part.scad is empty", "warn");
      return;
    }
    setRunning(true);
    await s.runBusy("Compiling part.scad…", async () => {
      try {
        const r = await kin.iterate(s.sid, text, label.trim() || undefined);
        const { text: msg, tone } = describeIteration(r);
        toast(msg, tone);
        setDirty(false);
        setStale(false);
        lastRemote.current = text;
        setLabel("");
        await s.refresh();
        s.setSelected(null);
      } catch (e) {
        error(e, "Iteration failed");
      } finally {
        setRunning(false);
      }
    });
  };

  const disabled = running || s.running || !!s.busy;

  return (
    <div className="editor-wrap">
      <div className="editor-bar">
        <span className="mono small">part.scad</span>
        {dirty && <Pill tone="warn">modified</Pill>}
        <span className="grow" />
        {d.scad && (
          <a className="btn btn-ghost btn-xs" href={fileUrl(s.sid, "part.scad", s.stlVersion)} download="part.scad" title="Download part.scad">
            Download
          </a>
        )}
        <button className="btn btn-ghost btn-xs" onClick={reload} disabled={!dirty || running} title="Discard local edits">
          Revert
        </button>
        <button className="btn btn-primary btn-sm" onClick={run} disabled={disabled} title="Save part.scad and run compile + checks + blueprints (Ctrl/⌘+Enter)">
          {running ? <Spinner size={11} /> : <PlayIcon />} Run
        </button>
        <input
          className="input label-input"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Label for this iteration (optional)"
          aria-label="Iteration label"
          onKeyDown={(e) => {
            if (e.key === "Enter") run();
          }}
        />
      </div>
      {!d.scad && !text && (
        <div className="editor-note" style={{ background: "var(--blue-soft)" }}>
          <span>
            No part.scad yet — the designer writes it on the first run. You can also paste OpenSCAD here and press <b>Run</b> to compile and
            verify it against the spec.
          </span>
        </div>
      )}
      {stale && (
        <div className="editor-note">
          <span>part.scad changed on disk (iteration {d.meta.iteration}) while you were editing.</span>
          <button className="btn btn-xs" onClick={reload}>
            Reload
          </button>
        </div>
      )}
      <div
        className="editor-body"
        onKeyDown={(e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
            e.preventDefault();
            if (!disabled) run();
          }
        }}
      >
        <CodeEditor value={text} onChange={onChange} language="openscad" readOnly={running} />
      </div>
    </div>
  );
}

function PlayIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
      <path d="M6 4l14 8-14 8z" />
    </svg>
  );
}
