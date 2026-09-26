"""The designer's tools for the OpenAI runtime: files and a shell confined to the session directory, plus the
Kintsugi tools (iterate, templates, ask_user, finish). The Agent path gets the same Kintsugi tools through the Agent
SDK and uses the SDK's own file tools."""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable

from kintsugi import TEMPLATES_DIR, VENDOR_DIR
from kintsugi.agent.llm import ToolDef, ToolResult, image_part
from kintsugi.agent.pipeline import IterationResult, run_iteration
from kintsugi.session.workspace import Session
from kintsugi.spec.model import PartSpec

BLOCKED_COMMANDS = ("pip ", "pip3 ", "apt", "git push", "sudo", "kin new", "kin design", "kin serve", "kin critique", "curl ", "wget ",
                    "chmod", "rm -rf /", "ssh ", "scp ", "nc ", "python -m http", "mkfs", "dd ")


class Sandbox:
    """Path and command rules: the designer may only touch its session directory (plus read templates and BOSL2)."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.read_roots = [self.root, TEMPLATES_DIR.resolve(), VENDOR_DIR.resolve()]

    def resolve(self, p: str) -> Path:
        q = Path(p)
        return (self.root / q).resolve() if not q.is_absolute() else q.resolve()

    def inside(self, p: str) -> bool:
        rp = self.resolve(p)
        return rp == self.root or self.root in rp.parents

    def readable(self, p: str) -> bool:
        rp = self.resolve(p)
        return any(rp == r or r in rp.parents for r in self.read_roots)

    def command_ok(self, cmd: str) -> str | None:
        for b in BLOCKED_COMMANDS:
            if b in cmd:
                return f"command not allowed in the design sandbox: {b.strip()}"
        for a in re.findall(r"(?<![\w/.-])(/[\w./-]+)", cmd):
            if not self.readable(a) and not a.startswith(("/usr/bin", "/bin", "/tmp", "/dev/null", "/usr/lib", "/opt", "/usr/local/bin")):
                return f"commands may only touch the session directory (got {a})"
        if ".." in cmd:
            return "no parent-directory access from the session directory"
        return None


def _text_file(p: Path, offset: int = 0, limit: int = 400) -> str:
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    total = len(lines)
    chunk = lines[offset: offset + limit]
    body = "\n".join(f"{i + offset + 1:5d}| {ln}" for i, ln in enumerate(chunk))
    more = f"\n... ({total - offset - len(chunk)} more lines; call read_file with offset={offset + len(chunk)})" if offset + len(chunk) < total else ""
    return body + more


def make_file_tools(sandbox: Sandbox) -> list[ToolDef]:
    root = sandbox.root

    async def read_file(args: dict[str, Any]) -> ToolResult:
        p = str(args.get("path", ""))
        if not sandbox.readable(p):
            return ToolResult("reading is limited to the session directory, templates/ and the BOSL2 library", is_error=True)
        rp = sandbox.resolve(p)
        if not rp.exists():
            return ToolResult(f"no such file: {p}", is_error=True)
        if rp.suffix.lower() in (".png", ".jpg", ".jpeg"):
            img = image_part(rp, max_side=1600)
            if not img:
                return ToolResult("unreadable image", is_error=True)
            return ToolResult(f"image {p} ({rp.stat().st_size // 1024} KB)", images=[(img["data"], img["mime"])])
        try:
            return ToolResult(_text_file(rp, int(args.get("offset", 0) or 0), int(args.get("limit", 400) or 400)))
        except Exception as e:
            return ToolResult(f"cannot read {p}: {e}", is_error=True)

    async def write_file(args: dict[str, Any]) -> ToolResult:
        p = str(args.get("path", ""))
        if not sandbox.inside(p):
            return ToolResult(f"writes are limited to the session directory {root}; write part.scad there", is_error=True)
        rp = sandbox.resolve(p)
        rp.parent.mkdir(parents=True, exist_ok=True)
        content = str(args.get("content", ""))
        rp.write_text(content, encoding="utf-8")
        return ToolResult(f"wrote {p} ({len(content.splitlines())} lines)")

    async def edit_file(args: dict[str, Any]) -> ToolResult:
        p = str(args.get("path", ""))
        if not sandbox.inside(p):
            return ToolResult("edits are limited to the session directory", is_error=True)
        rp = sandbox.resolve(p)
        if not rp.exists():
            return ToolResult(f"no such file: {p}", is_error=True)
        old, new = str(args.get("old_string", "")), str(args.get("new_string", ""))
        src = rp.read_text(encoding="utf-8")
        n = src.count(old)
        if not old or n == 0:
            return ToolResult("old_string not found in the file (it must match exactly, including whitespace)", is_error=True)
        if n > 1 and not args.get("replace_all"):
            return ToolResult(f"old_string matches {n} places; include more context or set replace_all=true", is_error=True)
        rp.write_text(src.replace(old, new) if args.get("replace_all") else src.replace(old, new, 1), encoding="utf-8")
        return ToolResult(f"edited {p}")

    async def list_files(args: dict[str, Any]) -> ToolResult:
        p = str(args.get("path", ".") or ".")
        if not sandbox.readable(p):
            return ToolResult("listing is limited to the session directory", is_error=True)
        rp = sandbox.resolve(p)
        if not rp.is_dir():
            return ToolResult(f"not a directory: {p}", is_error=True)
        entries = []
        for q in sorted(rp.iterdir()):
            if q.name.startswith(".git"):
                continue
            entries.append(f"{q.name}/" if q.is_dir() else f"{q.name} ({q.stat().st_size} B)")
        return ToolResult("\n".join(entries) or "(empty)")

    async def run_command(args: dict[str, Any]) -> ToolResult:
        cmd = str(args.get("command", ""))
        why = sandbox.command_ok(cmd)
        if why:
            return ToolResult(why, is_error=True)
        timeout = min(float(args.get("timeout_s", 120) or 120), 300)
        env = dict(os.environ)
        env["OPENSCADPATH"] = str(VENDOR_DIR)
        loop = asyncio.get_running_loop()

        def _run():
            return subprocess.run(["bash", "-lc", cmd], cwd=str(root), capture_output=True, text=True, timeout=timeout, env=env)

        try:
            proc = await loop.run_in_executor(None, _run)
        except subprocess.TimeoutExpired:
            return ToolResult(f"command timed out after {timeout:.0f}s", is_error=True)
        out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
        if len(out) > 8000:
            out = out[:4000] + "\n... (truncated) ...\n" + out[-3500:]
        return ToolResult(f"exit {proc.returncode}\n{out}".strip(), is_error=proc.returncode != 0)

    return [
        ToolDef("read_file", "Read a text file (numbered lines) or an image (PNG/JPG, returned as a picture) from the session directory, templates/ or the BOSL2 library.",
                {"type": "object", "properties": {"path": {"type": "string"}, "offset": {"type": "integer", "description": "first line (0-based)"},
                                                  "limit": {"type": "integer", "description": "max lines (default 400)"}}, "required": ["path"]}, read_file),
        ToolDef("write_file", "Create or overwrite a file in the session directory (use for part.scad).",
                {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}, write_file),
        ToolDef("edit_file", "Replace one exact occurrence of old_string with new_string in a session file.",
                {"type": "object", "properties": {"path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"},
                                                  "replace_all": {"type": "boolean"}}, "required": ["path", "old_string", "new_string"]}, edit_file),
        ToolDef("list_files", "List a directory in the session (default: the session root).",
                {"type": "object", "properties": {"path": {"type": "string"}}}, list_files),
        ToolDef("run_command", "Run a shell command in the session directory (openscad, python3 with numpy/trimesh/opencv, ls, grep...). No network, no package installs, no paths outside the session.",
                {"type": "object", "properties": {"command": {"type": "string"}, "timeout_s": {"type": "number"}}, "required": ["command"]}, run_command),
    ]


def templates_index() -> str:
    lines = []
    if not TEMPLATES_DIR.exists():
        return "(no templates)"
    for p in sorted(TEMPLATES_DIR.glob("*.scad")):
        desc = ""
        try:
            for line in p.read_text(encoding="utf-8").splitlines()[:6]:
                if line.startswith("//") and "TEMPLATE:" in line:
                    desc = line.split("TEMPLATE:", 1)[1].strip()
                    break
        except Exception:
            pass
        lines.append(f"- {p.stem}: {desc}")
    return "\n".join(lines) or "(no templates)"


def make_kin_tools(session: Session, state: Any, spec: PartSpec, budget: int, emit: Callable[..., Any], *,
                   sheet_images: bool = True, hide_templates: bool = False) -> list[ToolDef]:
    """iterate / list_templates / read_template / ask_user / finish, shared by both runtimes."""

    async def iterate(args: dict[str, Any]) -> ToolResult:
        label = str(args.get("label", ""))[:200]
        loop = asyncio.get_running_loop()
        try:
            res: IterationResult = await loop.run_in_executor(None, lambda: run_iteration(session, spec=spec, budget=budget, label=label))
        except Exception as e:
            return ToolResult(f"iterate failed: {e}", is_error=True)
        state.last_result = res
        state.iterations.append(res)
        images: list[tuple[bytes, str]] = []
        text = res.summary_for_model()
        if sheet_images and res.blueprint:
            for p, title in ((res.blueprint.sheet_path, "VIEWS SHEET"), (res.blueprint.sections_path, "SECTIONS & ASSEMBLY SHEET")):
                if p:
                    img = image_part(p, max_side=1400, quality=78)
                    if img:
                        images.append((img["data"], img["mime"]))
                        text += f"\n[{title}: {p.name} — attached as an image]"
        return ToolResult(text, images=images)

    async def list_templates(args: dict[str, Any]) -> ToolResult:
        if hide_templates:
            return ToolResult("(templates are disabled for this run; design from primitives)")
        return ToolResult(templates_index())

    async def read_template(args: dict[str, Any]) -> ToolResult:
        if hide_templates:
            return ToolResult("templates are disabled for this run", is_error=True)
        name = str(args.get("name", "")).replace(".scad", "")
        p = TEMPLATES_DIR / f"{name}.scad"
        if not p.exists():
            return ToolResult(f"no template named {name}. Available:\n{templates_index()}", is_error=True)
        return ToolResult(p.read_text(encoding="utf-8"))

    async def ask_user(args: dict[str, Any]) -> ToolResult:
        q = {"question": str(args.get("question", "")), "options": [str(o) for o in (args.get("options") or [])]}
        state.question = q
        session.update_meta(status="waiting_user", question=q)
        emit("question", **q)
        return ToolResult("Question recorded. Stop now; the run resumes when the user answers.")

    async def finish(args: dict[str, Any]) -> ToolResult:
        if not (state.last_result and state.last_result.ok):
            return ToolResult("Refused: the last iteration does not pass all hard checks. Fix them and iterate, or ask_user.", is_error=True)
        state.finished = True
        state.narration = str(args.get("narration", ""))
        emit("narration", text=state.narration)
        return ToolResult("Recorded. The critic will now review the drawings; stop and wait.")

    return [
        ToolDef("iterate", "Compile part.scad, run every spec check on the exported mesh, render the blueprint sheets, and return the check table with the sheets as images. Call after every change to part.scad.",
                {"type": "object", "properties": {"label": {"type": "string", "description": "one line: what changed and why"}}, "required": ["label"]}, iterate),
        ToolDef("list_templates", "List the vetted parametric templates (name and one-line description).", {"type": "object", "properties": {}}, list_templates),
        ToolDef("read_template", "Read the full source of a template by name (without .scad).",
                {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}, read_template),
        ToolDef("ask_user", "Pause and ask the user one batched question you cannot decide (an open interface dimension, an ambiguity about function).",
                {"type": "object", "properties": {"question": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}}}, "required": ["question"]}, ask_user),
        ToolDef("finish", "Declare the part done: all hard checks pass and the drawings look right. Give the user a 3-8 line narration.",
                {"type": "object", "properties": {"narration": {"type": "string"}}, "required": ["narration"]}, finish),
    ]


def shell_quote(s: str) -> str:
    return shlex.quote(s)
