"""Headless OpenSCAD compilation with structured error, warning and echo capture.

The agent, the tests and a human all compile through this one function so behaviour is identical.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kintsugi import VENDOR_DIR

_ERROR_RE = re.compile(r"^ERROR:\s*(.*)$")
_WARNING_RE = re.compile(r"^WARNING:\s*(.*)$")
_ECHO_RE = re.compile(r"^ECHO:\s*(.*)$")
_ECHO_KV_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$')
_DEPRECATED_RE = re.compile(r"^DEPRECATED:\s*(.*)$")
_NOISE_PREFIXES = (
    "Geometry cache", "CGAL cache", "CGAL Polyhedrons", "Total rendering time", "Top level object",
    "Simple:", "Vertices:", "Halfedges:", "Edges:", "Halffacets:", "Facets:", "Volumes:", "Marked",
    "Valid:", "Compiling design", "Rendering Polygon Mesh", "Parsing design", "Saved backup",
    "Loaded design", "Fontconfig", "Using default", "Compiling library",
)


@dataclass
class CompileResult:
    ok: bool
    out_path: Path | None
    format: str
    duration_s: float
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    echoes: list[str] = field(default_factory=list)
    echo_values: dict[str, Any] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    command: list[str] = field(default_factory=list)
    top_level_kind: str | None = None  # "3D" | "2D" | None
    returncode: int | None = None
    cancelled: bool = False

    def summary(self) -> str:
        """A compact, model-readable summary."""
        lines = [f"compile: {'ok' if self.ok else 'FAILED'} ({self.format}, {self.duration_s:.1f}s)"]
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        for w in self.warnings[:20]:
            lines.append(f"  WARNING: {w}")
        if len(self.warnings) > 20:
            lines.append(f"  ... {len(self.warnings) - 20} more warnings")
        for k, v in self.echo_values.items():
            lines.append(f"  echo {k} = {v}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "out_path": str(self.out_path) if self.out_path else None,
            "format": self.format,
            "duration_s": round(self.duration_s, 3),
            "errors": self.errors,
            "warnings": self.warnings,
            "echo_values": self.echo_values,
            "top_level_kind": self.top_level_kind,
            "returncode": self.returncode,
            "cancelled": self.cancelled,
        }


_WINDOWS_OPENSCAD = (r"C:\Program Files\OpenSCAD\openscad.exe", r"C:\Program Files\OpenSCAD (Nightly)\openscad.exe",
                     r"C:\Program Files (x86)\OpenSCAD\openscad.exe")
_MAC_OPENSCAD = ("/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",)


def openscad_binary() -> str:
    """KIN_OPENSCAD_BIN, else `openscad` on PATH, else the usual install locations on Windows/macOS."""
    if os.environ.get("KIN_OPENSCAD_BIN"):
        return os.environ["KIN_OPENSCAD_BIN"]
    found = shutil.which("openscad")
    if found:
        return found
    for cand in _WINDOWS_OPENSCAD + _MAC_OPENSCAD:
        if os.path.exists(cand):
            return cand
    return "openscad"


def openscad_version() -> str | None:
    try:
        out = subprocess.run([openscad_binary(), "--version"], capture_output=True, text=True, timeout=30)
        text = (out.stdout + out.stderr).strip()
        m = re.search(r"version\s+([\w.\-]+)", text)
        return m.group(1) if m else text
    except Exception:
        return None


def format_define(value: Any) -> str:
    """Render a Python value as an OpenSCAD literal for -D."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        # Allow raw OpenSCAD expressions when explicitly wrapped as raw:...
        if value.startswith("raw:"):
            return value[4:]
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(format_define(v) for v in value) + "]"
    raise TypeError(f"cannot render {type(value).__name__} as an OpenSCAD literal")


def _parse_echo_value(raw: str) -> Any:
    raw = raw.strip()
    if raw in ("true", "false"):
        return raw == "true"
    if raw == "undef":
        return None
    try:
        if re.fullmatch(r"-?\d+", raw):
            return int(raw)
        if re.fullmatch(r"-?\d*\.\d+(e-?\d+)?|-?\d+e-?\d+", raw):
            return float(raw)
    except ValueError:
        pass
    if raw.startswith("[") and raw.endswith("]"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    return raw


def parse_openscad_log(text: str) -> tuple[list[str], list[str], list[str], dict[str, Any], str | None]:
    errors, warnings, echoes = [], [], []
    echo_values: dict[str, Any] = {}
    kind = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(_NOISE_PREFIXES):
            if line.startswith("Top level object is a 3D object"):
                kind = "3D"
            elif line.startswith("Top level object is a 2D object"):
                kind = "2D"
            continue
        m = _ERROR_RE.match(line)
        if m:
            errors.append(m.group(1))
            continue
        m = _WARNING_RE.match(line)
        if m:
            warnings.append(m.group(1))
            continue
        m = _DEPRECATED_RE.match(line)
        if m:
            warnings.append("DEPRECATED: " + m.group(1))
            continue
        m = _ECHO_RE.match(line)
        if m:
            body = m.group(1)
            echoes.append(body)
            # ECHO: name = value   or   ECHO: name = value, other = value
            for part in _split_echo_parts(body):
                kv = _ECHO_KV_RE.match(part.strip())
                if kv:
                    echo_values[kv.group(1)] = _parse_echo_value(kv.group(2))
            continue
    return errors, warnings, echoes, echo_values, kind


def _split_echo_parts(body: str) -> list[str]:
    """Split 'a = 1, b = [1, 2]' on top-level commas."""
    parts, depth, cur, in_str = [], 0, [], False
    for ch in body:
        if ch == '"':
            in_str = not in_str
        if not in_str:
            if ch in "[(":
                depth += 1
            elif ch in "])":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(cur))
                cur = []
                continue
        cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return parts


def compile_scad(
    scad_path: str | Path,
    out_path: str | Path,
    defines: dict[str, Any] | None = None,
    *,
    fmt: str | None = None,
    timeout_s: float = 300.0,
    extra_args: list[str] | None = None,
    include_dirs: list[str | Path] | None = None,
    use_xvfb: bool | None = None,
    cancel: threading.Event | None = None,
) -> CompileResult:
    """Compile a .scad file to STL/OFF/3MF/PNG/SVG/etc.

    `defines` become -D overrides (strings are quoted, numbers left as-is, "raw:expr" passes through).
    PNG output is routed through xvfb-run automatically when no display is available.
    `cancel` (a threading.Event) kills the OpenSCAD process when set — the live preview uses it so a slider drag
    never queues stale compiles; the result then has `cancelled=True`.
    """
    scad_path = Path(scad_path).resolve()
    out_path = Path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = fmt or out_path.suffix.lstrip(".").lower()

    cmd = [openscad_binary(), "-o", str(out_path)]
    for k, v in (defines or {}).items():
        cmd += ["-D", f"{k}={format_define(v)}"]
    if extra_args:
        cmd += list(extra_args)
    cmd.append(str(scad_path))

    needs_display = fmt in ("png",)
    if use_xvfb is None:
        use_xvfb = needs_display and not os.environ.get("DISPLAY") and shutil.which("xvfb-run") is not None
    if use_xvfb:
        cmd = ["xvfb-run", "-a", "-s", "-screen 0 1600x1600x24"] + cmd

    env = dict(os.environ)
    paths = [str(VENDOR_DIR)] + [str(p) for p in (include_dirs or [])]
    if env.get("OPENSCADPATH"):
        paths.append(env["OPENSCADPATH"])
    env["OPENSCADPATH"] = os.pathsep.join(paths)

    t0 = time.time()
    cancelled = False
    if cancel is None:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, env=env, cwd=str(scad_path.parent))
            rc = proc.returncode
            stdout, stderr = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as e:
            rc = -1
            stdout = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr = ((e.stderr or b"").decode() if isinstance(e.stderr, bytes) else (e.stderr or "")) + \
                f"\nERROR: OpenSCAD timed out after {timeout_s:.0f}s (reduce $fn or simplify booleans)"
    else:
        rc, stdout, stderr, cancelled = _run_cancellable(cmd, env, str(scad_path.parent), timeout_s, cancel)
    duration = time.time() - t0

    errors, warnings, echoes, echo_values, kind = parse_openscad_log(stderr + "\n" + stdout)
    if cancelled:
        errors.append("cancelled (superseded by a newer preview)")
    produced = out_path.exists() and out_path.stat().st_size > 0
    if rc != 0 and not errors:
        tail = [ln for ln in (stderr + "\n" + stdout).splitlines() if ln.strip() and not ln.startswith(_NOISE_PREFIXES)]
        errors.append(f"openscad exited {rc}: " + (" | ".join(tail[-5:]) if tail else "no message"))
    ok = rc == 0 and not errors and produced
    if rc == 0 and not produced and not errors:
        errors.append("OpenSCAD exited 0 but produced no output (empty geometry? check that something is rendered)")
        ok = False
    if kind == "2D" and fmt in ("stl", "off", "3mf", "amf"):
        errors.append("Top-level object is 2D; a 3D export needs a 3D object (extrude it)")
        ok = False
    return CompileResult(
        ok=ok, out_path=out_path if produced else None, format=fmt, duration_s=duration,
        errors=errors, warnings=warnings, echoes=echoes, echo_values=echo_values,
        stdout=stdout, stderr=stderr, command=cmd, top_level_kind=kind, returncode=rc, cancelled=cancelled,
    )


def _run_cancellable(cmd: list[str], env: dict[str, str], cwd: str, timeout_s: float, cancel: threading.Event) -> tuple[int, str, str, bool]:
    """Run OpenSCAD in a subprocess that dies as soon as `cancel` is set (or the timeout passes)."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=cwd)
    chunks: dict[str, str] = {"out": "", "err": ""}

    def pump(stream, key):
        try:
            chunks[key] = stream.read()
        except Exception:
            pass

    t_out = threading.Thread(target=pump, args=(proc.stdout, "out"), daemon=True)
    t_err = threading.Thread(target=pump, args=(proc.stderr, "err"), daemon=True)
    t_out.start()
    t_err.start()
    deadline = time.time() + timeout_s
    cancelled = False
    timed_out = False
    while proc.poll() is None:
        if cancel.is_set():
            cancelled = True
            break
        if time.time() > deadline:
            timed_out = True
            break
        time.sleep(0.03)
    if proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass
        proc.wait()
    t_out.join(timeout=2)
    t_err.join(timeout=2)
    stderr = chunks["err"]
    if timed_out:
        stderr += f"\nERROR: OpenSCAD timed out after {timeout_s:.0f}s (reduce $fn or simplify booleans)"
    return (proc.returncode if proc.returncode is not None else -1), chunks["out"], stderr, cancelled


def render_png(
    scad_path: str | Path, out_path: str | Path, *, camera: str | None = None, projection: str = "o",
    imgsize: tuple[int, int] = (1200, 1200), defines: dict[str, Any] | None = None, colorscheme: str = "Tomorrow",
    viewall: bool = True, autocenter: bool = True, timeout_s: float = 300.0,
) -> CompileResult:
    """OpenSCAD's own renderer (for the drawing-style experiment and quick previews)."""
    args = [f"--projection={projection}", f"--imgsize={imgsize[0]},{imgsize[1]}", f"--colorscheme={colorscheme}"]
    if camera:
        args.append(f"--camera={camera}")
    if viewall:
        args.append("--viewall")
    if autocenter:
        args.append("--autocenter")
    return compile_scad(scad_path, out_path, defines, fmt="png", extra_args=args, timeout_s=timeout_s)
