"""Live preview compiles for the customizer: latest-wins, per session, without touching part.scad.

A slider drag produces a burst of requests. Each request gets a generation number; the running compile of an older
generation is killed, queued older requests return `superseded` without compiling, and only the newest one produces
`preview/preview.stl` (renamed into place atomically so the viewer never loads a half-written file).

Values are passed as `-D name=value` overrides, so the preview reads exactly the part.scad on disk plus the user's edits;
draft quality lowers `$fn` for speed (the verified iteration always runs at the model's own facet count).
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

from kintsugi.scad.compile import CompileResult, compile_scad

DRAFT_FN = 32
PREVIEW_TIMEOUT_S = 120.0


class _SessionState:
    def __init__(self) -> None:
        self.lock = threading.Lock()      # one compile at a time per session
        self.gen = 0                      # newest requested generation
        self.cancel: threading.Event | None = None
        self.last: dict[str, Any] | None = None
        self.durations: list[float] = []  # recent successful compile times (for the adaptive auto-preview)


class PreviewEngine:
    def __init__(self) -> None:
        self._states: dict[str, _SessionState] = {}
        self._guard = threading.Lock()

    def _state(self, sid: str) -> _SessionState:
        with self._guard:
            st = self._states.get(sid)
            if st is None:
                st = self._states[sid] = _SessionState()
            return st

    def last(self, sid: str) -> dict[str, Any] | None:
        return self._state(sid).last

    def cancel(self, sid: str) -> None:
        """Kill whatever preview is compiling for this session (an apply or a code edit is about to compile for real)."""
        with self._guard:
            st = self._states.get(sid)
            if st is not None:
                st.gen += 1
                if st.cancel is not None:
                    st.cancel.set()

    def forget(self, sid: str) -> None:
        with self._guard:
            self._states.pop(sid, None)

    def run(self, sid: str, scad_path: Path, out_dir: Path, values: dict[str, Any], *, render_target: str | None = "part",
            quality: str = "draft", has_render_target: bool = True) -> dict[str, Any]:
        st = self._state(sid)
        with self._guard:
            st.gen += 1
            gen = st.gen
            if st.cancel is not None:
                st.cancel.set()               # kill whatever is compiling: it is older than this request
        with st.lock:
            if gen != st.gen:                 # a newer request arrived while we waited
                return {"ok": False, "superseded": True, "gen": gen, "values": values}
            cancel = threading.Event()
            st.cancel = cancel
            defines: dict[str, Any] = dict(values)
            if has_render_target and render_target:
                defines["render_target"] = render_target
            if quality == "draft":
                defines["$fn"] = DRAFT_FN
            out_dir.mkdir(parents=True, exist_ok=True)
            tmp = out_dir / f"preview_{gen}.stl"
            t0 = time.time()
            comp: CompileResult = compile_scad(scad_path, tmp, defines, timeout_s=PREVIEW_TIMEOUT_S, cancel=cancel)
            if st.cancel is cancel:
                st.cancel = None
            result: dict[str, Any] = {
                "ok": comp.ok, "gen": gen, "superseded": gen != st.gen, "cancelled": comp.cancelled, "values": values,
                "render_target": render_target if has_render_target else None, "quality": quality,
                "duration_s": round(time.time() - t0, 3), "echo_values": comp.echo_values, "errors": comp.errors,
                "warnings": comp.warnings[:12], "file": None, "version": gen, "assert_failures": _assert_failures(comp.errors),
            }
            if comp.ok and comp.out_path:
                final = out_dir / "preview.stl"
                os.replace(comp.out_path, final)
                result["file"] = final.relative_to(out_dir.parent).as_posix() if out_dir.parent in final.parents else str(final)
                st.durations = (st.durations + [result["duration_s"]])[-5:]
            else:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
            result["avg_duration_s"] = round(sum(st.durations) / len(st.durations), 3) if st.durations else None
            if not comp.cancelled:
                st.last = result
            return result


def _assert_failures(errors: list[str]) -> list[str]:
    """OpenSCAD reports `Assertion 'cond' failed: "message" in file ..., line N` — keep the human message."""
    out: list[str] = []
    for e in errors:
        if "Assertion" in e and "failed" in e:
            msg = e
            if ":" in e:
                tail = e.split("failed", 1)[1].strip(" :")
                if tail.startswith('"'):
                    end = tail.find('"', 1)
                    msg = tail[1:end] if end > 0 else tail
                else:
                    msg = tail.split(" in file")[0]
            out.append(msg.strip())
    return out


ENGINE = PreviewEngine()
