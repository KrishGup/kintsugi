"""Portable session state: one .zip that carries everything a session is, and the manifest that describes it.

`export_archive(session)` writes `kintsugi-session-<id>.zip`:
    manifest.json      schema, app version, when, the session's meta, every file with size and sha256
    session.json       the meta (status, stage, iteration, name…)
    spec.yaml          the Part Spec (schema: docs/schemas/part-spec.schema.json)
    part.scad          the current part, part.json (presets), params.json, checks.json, history.json, intake.json
    events.jsonl       the timeline
    photos/ measure/ iterations/ sheets/ critic/ export/   as on disk (bundle.zip, previews and the git repo are left out)

`import_archive(zip, sessions_dir)` recreates the session under a fresh id (or the original one when it is free),
validating the manifest, refusing paths that escape the session folder, and re-initialising the git history.
The same file round-trips through the CLI (`kin archive`, `kin import`) and the web UI (Export → archive, Home → import).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, BinaryIO

from kintsugi import __version__
from kintsugi.session.workspace import Session

SCHEMA_VERSION = 1
SCHEMA_ID = "https://kintsugi.dev/schemas/session-archive.schema.json"

# what travels; everything else in the folder is derived or heavy
SKIP_DIRS = {".git", "preview", "__pycache__"}
SKIP_FILES = {"bundle.zip"}
MAX_FILES = 20000


def _iter_files(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts) or rel.name in SKIP_FILES:
            continue
        yield rel, p


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(session: Session) -> dict[str, Any]:
    meta = dict(session.meta)
    files = []
    total = 0
    for rel, p in _iter_files(session.dir):
        size = p.stat().st_size
        total += size
        files.append({"path": rel.as_posix(), "bytes": size, "sha256": _sha256(p)})
    return {
        "$schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "kind": "kintsugi-session",
        "app_version": __version__,
        "exported_at": time.time(),
        "session": {k: v for k, v in meta.items() if k not in ("owner", "owner_name")},
        "files": files,
        "total_bytes": total,
    }


def export_archive(session: Session, out: str | Path | None = None) -> Path:
    """Write the archive next to nothing in particular (a temp file by default) and return its path."""
    manifest = build_manifest(session)
    if out is None:
        fd, tmp = tempfile.mkstemp(prefix=f"kintsugi-session-{session.id}-", suffix=".zip")
        os.close(fd)
        out = Path(tmp)
    out = Path(out)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))
        for rel, p in _iter_files(session.dir):
            z.write(p, rel.as_posix())
    return out


class ArchiveError(ValueError):
    pass


# a segment may be any unicode name that no filesystem we write to would refuse: no control characters, no separators,
# none of the characters Windows forbids, and never a bare "." / ".." (traversal) or a trailing dot/space
_SAFE_SEG = re.compile(r'^[^\x00-\x1f\x7f/\\:*?"<>|]+$')


def _safe_rel(name: str) -> Path:
    """Refuse absolute paths, drive letters, parent traversal, and segments no filesystem should get (zip-slip)."""
    if not name or name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name):
        raise ArchiveError(f"unsafe path in archive: {name!r}")
    parts = [p for p in re.split(r"[\\/]+", name) if p]
    if not parts or any(p in ("..", ".") or p.endswith((" ", ".")) or not _SAFE_SEG.match(p) or len(p) > 200 for p in parts):
        raise ArchiveError(f"unsafe path in archive: {name!r}")
    return Path(*parts)


def inspect_archive(data: bytes | BinaryIO) -> dict[str, Any]:
    """Read and validate the manifest without extracting anything."""
    z = zipfile.ZipFile(io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data)
    names = z.namelist()
    if "manifest.json" not in names:
        raise ArchiveError("not a Kintsugi session archive (no manifest.json)")
    if "session.json" not in names:
        raise ArchiveError("not a Kintsugi session archive (no session.json)")
    if len(names) > MAX_FILES:
        raise ArchiveError(f"archive has too many files ({len(names)})")
    try:
        manifest = json.loads(z.read("manifest.json").decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ArchiveError(f"manifest.json is not valid JSON: {e}") from e
    if manifest.get("kind") != "kintsugi-session":
        raise ArchiveError("manifest.json is not a kintsugi-session manifest")
    v = int(manifest.get("schema_version", 0) or 0)
    if v < 1 or v > SCHEMA_VERSION:
        raise ArchiveError(f"archive schema version {v} is not supported by this version (supports 1..{SCHEMA_VERSION})")
    for n in names:
        if n.endswith("/"):
            continue
        _safe_rel(n)
    return manifest


def import_archive(data: bytes | BinaryIO, sessions_dir: Path, *, max_bytes: int = 500 << 20, owner: dict[str, Any] | None = None,
                   keep_id: bool = True) -> Session:
    """Recreate the session from the archive. Returns the new Session (a fresh git history, `imported_from` in meta)."""
    manifest = inspect_archive(data)
    z = zipfile.ZipFile(io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data)
    total = sum(i.file_size for i in z.infolist())
    if total > max_bytes:
        raise ArchiveError(f"archive expands to {total / 1e6:.0f} MB, above the {max_bytes / 1e6:.0f} MB limit")
    old_meta = manifest.get("session") or {}
    old_id = str(old_meta.get("id") or "")
    sessions_dir = Path(sessions_dir).resolve()
    sessions_dir.mkdir(parents=True, exist_ok=True)
    sid = old_id if keep_id and old_id and re.fullmatch(r"[A-Za-z0-9._-]{4,80}", old_id) and not (sessions_dir / old_id).exists() else None
    if sid is None:
        sid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    dest = sessions_dir / sid
    tmp = sessions_dir / f".import-{uuid.uuid4().hex[:8]}"
    tmp.mkdir(parents=True)
    try:
        for info in z.infolist():
            if info.is_dir():
                continue
            rel = _safe_rel(info.filename)
            if rel.name == "manifest.json" and len(rel.parts) == 1:
                continue
            target = tmp / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
        for sub in ("photos", "iterations", "sheets", "export", "critic", "measure"):
            (tmp / sub).mkdir(exist_ok=True)
        meta_path = tmp / "session.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["id"] = sid
        meta["imported_from"] = {"id": old_id or None, "exported_at": manifest.get("exported_at"), "app_version": manifest.get("app_version")}
        meta["imported_at"] = time.time()
        meta.pop("owner", None)
        meta.pop("owner_name", None)
        if owner:
            meta.update(owner)
        if meta.get("status") in ("running",):
            meta["status"] = "stopped"          # a run cannot travel
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        tmp.rename(dest)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    s = Session(dest)
    if os.environ.get("KIN_SESSION_GIT", "1").lower() not in ("0", "false", "no") and shutil.which("git"):
        s._git(["init", "-q"])
        s._git(["config", "user.email", "kintsugi@local"])
        s._git(["config", "user.name", "kintsugi"])
        if not (dest / ".gitignore").exists():
            (dest / ".gitignore").write_text("*.stl\n*.3mf\n__pycache__/\n", encoding="utf-8")
        s.commit(f"imported from archive ({old_id or 'unknown'})")
    s.emit("imported", from_id=old_id or None, files=len(manifest.get("files", [])))
    return s


# ---- schemas ------------------------------------------------------------------------------------------------------

def manifest_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "Kintsugi session archive manifest",
        "description": "manifest.json at the root of a kintsugi-session-<id>.zip. The zip also holds session.json, spec.yaml, "
                       "part.scad and the session's folders; every file is listed here with its size and sha256.",
        "type": "object",
        "required": ["schema_version", "kind", "app_version", "exported_at", "session", "files"],
        "properties": {
            "$schema": {"type": "string"},
            "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
            "kind": {"type": "string", "const": "kintsugi-session"},
            "app_version": {"type": "string", "description": "the Kintsugi version that wrote the archive"},
            "exported_at": {"type": "number", "description": "unix seconds"},
            "session": {
                "type": "object",
                "description": "session.json at export time, minus the owner",
                "required": ["id", "name", "created"],
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "created": {"type": "number"},
                    "updated": {"type": "number"},
                    "status": {"type": "string", "enum": ["new", "intake_done", "iterating", "running", "waiting_user", "done", "stopped", "error"]},
                    "stage": {"type": "string", "enum": ["intake", "capture", "spec", "design", "review", "export"]},
                    "iteration": {"type": "integer", "minimum": 0},
                    "critic_rounds": {"type": "integer", "minimum": 0},
                    "model": {"type": "string"},
                    "provider": {"type": "string"},
                    "cost_usd": {"type": "number"},
                    "narration": {"type": "string"},
                    "exported_iteration": {"type": "integer"},
                    "exported_at": {"type": "number"},
                },
                "additionalProperties": True,
            },
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["path", "bytes", "sha256"],
                    "properties": {
                        "path": {"type": "string", "description": "relative, forward slashes, no '..'"},
                        "bytes": {"type": "integer", "minimum": 0},
                        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    },
                },
            },
            "total_bytes": {"type": "integer", "minimum": 0},
        },
    }


def part_spec_schema() -> dict[str, Any]:
    from kintsugi.spec.model import PartSpec
    schema = PartSpec.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://kintsugi.dev/schemas/part-spec.schema.json"
    schema["title"] = "Kintsugi Part Spec (spec.yaml)"
    schema["description"] = ("The contract between the person, the designer and the checker: the part, its interfaces (mating "
                             "features with dimensions, estimates and measure recipes), requirements, context proxies, print settings.")
    return schema
