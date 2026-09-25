import { Component, lazy, Suspense, useState, type ReactNode } from "react";
import { Spinner } from "../ui";
import type { MonacoProps } from "./MonacoEditor";

// Monaco is loaded lazily (its own chunk); if the chunk or package is unavailable we fall back to a textarea.
const Monaco = lazy(() => import("./MonacoEditor"));

class Boundary extends Component<{ fallback: ReactNode; onError: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onError();
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export default function CodeEditor(props: MonacoProps) {
  const [failed, setFailed] = useState(false);
  const fallback = (
    <textarea
      className="editor-fallback textarea-mono"
      value={props.value}
      readOnly={props.readOnly}
      spellCheck={false}
      onChange={(e) => props.onChange(e.target.value)}
      aria-label={`${props.language} source`}
    />
  );
  if (failed) return fallback;
  return (
    <Boundary fallback={fallback} onError={() => setFailed(true)}>
      <Suspense
        fallback={
          <div className="viewer-overlay">
            <Spinner label="Loading editor…" />
          </div>
        }
      >
        <Monaco {...props} />
      </Suspense>
    </Boundary>
  );
}
