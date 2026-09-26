"""Session workspace: all state as files, one git commit per iteration, an event log the UI tails."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kintsugi import DATA_DIR
from kintsugi.spec.model import PartSpec

DEFAULT_SESSIONS_DIR = Path(os.environ.get("KIN_SESSIONS_DIR") or (DATA_DIR / "sessions")).resolve()


def git_enabled() -> bool:
    """Per-iteration git history is on by default; KIN_SESSION_GIT=0 turns it off (slow network volumes)."""
    return os.environ.get("KIN_SESSION_GIT", "1").lower() not in ("0", "false", "no") and shutil.which("git") is not None


@dataclass
class Session:
    dir: Path

    # ---- creation --------------------------------------------------------------------------------
    @classmethod
    def create(cls, name: str, spec: PartSpec | None = None, sessions_dir: Path | None = None, session_id: str | None = None) -> "Session":
        root = Path(sessions_dir or DEFAULT_SESSIONS_DIR).resolve()
        sid = session_id or (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
        d = root / sid
        for sub in ("photos", "iterations", "sheets", "export", "critic", "measure"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        meta = {"id": sid, "name": name, "created": time.time(), "status": "new", "iteration": 0, "critic_rounds": 0}
        (d / "session.json").write_text(json.dumps(meta, indent=2))
        s = cls(d)
        if spec is not None:
            spec.save(d / "spec.yaml")
        if git_enabled():
            s._git(["init", "-q"])
            s._git(["config", "user.email", "kintsugi@local"])
            s._git(["config", "user.name", "kintsugi"])
        (d / ".gitignore").write_text("*.stl\n*.3mf\n__pycache__/\n")
        s.commit("session created")
        return s

    @classmethod
    def open(cls, path: str | Path) -> "Session":
        d = Path(path).resolve()
        if not (d / "session.json").exists():
            raise FileNotFoundError(f"not a session: {d}")
        return cls(d)

    # ---- meta ------------------------------------------------------------------------------------
    @property
    def id(self) -> str:
        return self.meta["id"]

    @property
    def meta(self) -> dict[str, Any]:
        return json.loads((self.dir / "session.json").read_text())

    def update_meta(self, **kw) -> dict[str, Any]:
        m = self.meta
        m.update(kw)
        m["updated"] = time.time()
        (self.dir / "session.json").write_text(json.dumps(m, indent=2))
        return m

    @property
    def spec_path(self) -> Path:
        return self.dir / "spec.yaml"

    def spec(self) -> PartSpec:
        return PartSpec.load(self.spec_path)

    @property
    def scad_path(self) -> Path:
        return self.dir / "part.scad"

    @property
    def stl_path(self) -> Path:
        return self.dir / "part.stl"

    def iteration_dir(self, n: int) -> Path:
        d = self.dir / "iterations" / f"iter_{n:02d}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ---- events ----------------------------------------------------------------------------------
    def emit(self, kind: str, **data: Any) -> dict[str, Any]:
        ev = {"t": time.time(), "kind": kind, **data}
        with open(self.dir / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, default=str) + "\n")
        return ev

    def events(self, since: int = 0) -> list[dict[str, Any]]:
        p = self.dir / "events.jsonl"
        if not p.exists():
            return []
        out = []
        with open(p, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i < since:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    # ---- git -------------------------------------------------------------------------------------
    def _git(self, args: list[str]) -> subprocess.CompletedProcess:
        # safe.directory: a session on a mounted volume is often owned by another uid; git would refuse it otherwise
        return subprocess.run(["git", "-c", "safe.directory=*", "-C", str(self.dir)] + args, capture_output=True, text=True)

    def commit(self, message: str) -> str | None:
        if not git_enabled() or not (self.dir / ".git").exists():
            return None
        self._git(["add", "-A"])
        r = self._git(["commit", "-q", "-m", message, "--allow-empty"])
        if r.returncode != 0:
            return None
        h = self._git(["rev-parse", "--short", "HEAD"])
        return h.stdout.strip() or None

    def history(self) -> list[dict[str, str]]:
        if not git_enabled() or not (self.dir / ".git").exists():
            return []
        r = self._git(["log", "--pretty=format:%h|%s|%ct"])
        out = []
        for line in r.stdout.splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                out.append({"hash": parts[0], "message": parts[1], "time": parts[2]})
        return out

    def checkout_iteration(self, n: int) -> None:
        """Restore part.scad from an earlier iteration (branch from it)."""
        src = self.iteration_dir(n) / "part.scad"
        if src.exists():
            shutil.copy(src, self.scad_path)
            self.commit(f"branch from iteration {n}")
            self.emit("branch", iteration=n)

    # ---- listing ---------------------------------------------------------------------------------
    @staticmethod
    def list_all(sessions_dir: Path | None = None) -> list[dict[str, Any]]:
        root = Path(sessions_dir or DEFAULT_SESSIONS_DIR)
        if not root.exists():
            return []
        out = []
        for d in sorted(root.iterdir(), reverse=True):
            p = d / "session.json"
            if p.exists():
                try:
                    out.append(json.loads(p.read_text()))
                except json.JSONDecodeError:
                    continue
        return out
