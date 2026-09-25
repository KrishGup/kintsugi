"""The designer agent: agent SDK session in the workspace with the kin tools, plus the critic loop."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from kintsugi import PACKAGE_DIR, TEMPLATES_DIR, VENDOR_DIR
from kintsugi.agent.critic import CriticVerdict, critique
from kintsugi.agent.pipeline import ITERATION_BUDGET, IterationResult, run_iteration
from kintsugi.session.workspace import Session
from kintsugi.spec.model import PartSpec

DESIGNER_PROMPT = (PACKAGE_DIR / "agent" / "prompts" / "designer.md").read_text(encoding="utf-8")


@dataclass
class RunState:
    finished: bool = False
    narration: str = ""
    question: dict[str, Any] | None = None
    last_result: IterationResult | None = None
    iterations: list[IterationResult] = field(default_factory=list)
    critic_verdicts: list[CriticVerdict] = field(default_factory=list)
    cost_usd: float = 0.0
    turns: int = 0
    error: str | None = None


@dataclass
class RunOutcome:
    status: str  # done | waiting_user | budget_exhausted | error
    state: RunState
    session: Session
    duration_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "duration_s": round(self.duration_s, 1), "iterations": len(self.state.iterations),
            "final_ok": bool(self.state.last_result and self.state.last_result.ok), "narration": self.state.narration,
            "question": self.state.question, "critic": [v.to_dict() for v in self.state.critic_verdicts],
            "cost_usd": round(self.state.cost_usd, 4), "turns": self.state.turns, "error": self.state.error,
        }


def _img_content(path: Path, max_side: int = 1400, quality: int = 82) -> dict[str, Any] | None:
    """Sheet image for a tool result: JPEG keeps the SDK message small (the sheets are line drawings on white)."""
    try:
        Image.init()
        im = Image.open(path).convert("RGB")
    except Exception:
        return None
    w, h = im.size
    if max(w, h) > max_side:
        r = max_side / max(w, h)
        im = im.resize((int(w * r), int(h * r)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True)
    return {"type": "image", "data": base64.b64encode(buf.getvalue()).decode(), "mimeType": "image/jpeg"}


def make_tools(session: Session, state: RunState, spec: PartSpec, budget: int, emit: Callable[[str, dict], None]):
    from agent_sdk import tool

    @tool("iterate", "Compile part.scad, run all spec checks on the exported mesh, render blueprint sheets. Returns the check table and the sheets as images. Call after every change to part.scad.",
          {"label": str})
    async def iterate_tool(args: dict[str, Any]) -> dict[str, Any]:
        label = str(args.get("label", ""))[:200]
        loop = asyncio.get_running_loop()
        try:
            res = await loop.run_in_executor(None, lambda: run_iteration(session, spec=spec, budget=budget, label=label))
        except Exception as e:
            return {"content": [{"type": "text", "text": f"iterate failed: {e}"}], "is_error": True}
        state.last_result = res
        state.iterations.append(res)
        content: list[dict[str, Any]] = [{"type": "text", "text": res.summary_for_model()}]
        if res.blueprint:
            for p, title in ((res.blueprint.sheet_path, "VIEWS SHEET"), (res.blueprint.sections_path, "SECTIONS & ASSEMBLY SHEET")):
                if p:
                    blk = _img_content(p)
                    if blk:
                        content.append({"type": "text", "text": f"[{title}: {p}]"})
                        content.append(blk)
        return {"content": content}

    @tool("list_templates", "List the vetted parametric templates (name and one-line description).", {})
    async def list_templates_tool(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": templates_index()}]}

    @tool("read_template", "Read the full source of a template by name (without .scad).", {"name": str})
    async def read_template_tool(args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("name", "")).replace(".scad", "")
        p = TEMPLATES_DIR / f"{name}.scad"
        if not p.exists():
            return {"content": [{"type": "text", "text": f"no template named {name}. Available:\n{templates_index()}"}], "is_error": True}
        return {"content": [{"type": "text", "text": p.read_text(encoding="utf-8")}]}

    @tool("ask_user", "Pause the run and ask the user a decision you cannot make. Batch all questions into one call.",
          {"question": str, "options": list})
    async def ask_user_tool(args: dict[str, Any]) -> dict[str, Any]:
        state.question = {"question": str(args.get("question", "")), "options": list(args.get("options") or [])}
        session.update_meta(status="waiting_user", question=state.question)
        emit("question", **state.question)
        return {"content": [{"type": "text", "text": "Question recorded. Stop now; the run will resume when the user answers."}]}

    @tool("finish", "Declare the part done: all hard checks pass and the drawings look right. Provide the narration for the user.",
          {"narration": str})
    async def finish_tool(args: dict[str, Any]) -> dict[str, Any]:
        if not (state.last_result and state.last_result.ok):
            return {"content": [{"type": "text", "text": "Refused: the last iteration does not pass all hard checks. Fix them and iterate, or ask_user."}],
                    "is_error": True}
        state.finished = True
        state.narration = str(args.get("narration", ""))
        emit("narration", text=state.narration)
        return {"content": [{"type": "text", "text": "Recorded. The critic will now review the drawings; stop and wait."}]}

    return [iterate_tool, list_templates_tool, read_template_tool, ask_user_tool, finish_tool]


def make_sandbox_hook(session_dir: Path):
    """PreToolUse hook: the designer may only write inside its session directory and may not run commands that reach
    outside it (the first live run patched the package source to add debug logging; this stops that)."""
    root = session_dir.resolve()
    allowed_read_roots = [root, TEMPLATES_DIR.resolve(), VENDOR_DIR.resolve()]

    def inside(p: str) -> bool:
        try:
            rp = (root / p).resolve() if not os.path.isabs(p) else Path(p).resolve()
        except Exception:
            return False
        return rp == root or root in rp.parents

    def readable(p: str) -> bool:
        try:
            rp = (root / p).resolve() if not os.path.isabs(p) else Path(p).resolve()
        except Exception:
            return False
        return any(rp == r or r in rp.parents for r in allowed_read_roots)

    async def hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        tool = input_data.get("tool_name", "")
        ti = input_data.get("tool_input") or {}
        deny = None
        if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            fp = str(ti.get("file_path") or ti.get("notebook_path") or "")
            if not inside(fp):
                deny = f"writes are limited to the session directory {root}; write to part.scad there"
        elif tool == "Read":
            fp = str(ti.get("file_path") or "")
            if fp and not readable(fp):
                deny = "reading is limited to the session directory, templates and the BOSL2 library"
        elif tool == "Bash":
            cmd = str(ti.get("command") or "")
            bad = [t for t in ("pip ", "pip3 ", "apt", "git push", "sudo", "kin new", "kin design", "kin serve", "kin critique", "curl ", "wget ", "chmod", "rm -rf /")
                   if t in cmd]
            import re as _re
            abs_paths = _re.findall(r"(?<![\w/.-])(/[\w./-]+)", cmd)
            outside = [a for a in abs_paths if not readable(a) and not a.startswith(("/usr/bin", "/bin", "/tmp", "/dev/null", "/usr/lib", "/opt"))]
            if bad:
                deny = f"command not allowed in the design sandbox: {bad[0].strip()}"
            elif outside:
                deny = f"commands may only touch the session directory (got {outside[0]})"
            elif ".." in cmd:
                deny = "no parent-directory access from the session directory"
        if deny:
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": deny}}
        return {}

    return hook


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


def initial_prompt(spec: PartSpec, user_message: str | None, strategy: str | None) -> str:
    parts = ["Design the part described by spec.yaml in this directory.", "", "SPEC SUMMARY:", spec.summary_for_model(), ""]
    if strategy:
        parts += [f"STRATEGY: {strategy}", ""]
    if user_message:
        parts += ["USER NOTES:", user_message, ""]
    parts.append("Start by reading spec.yaml and list_templates(). Then write part.scad and call iterate.")
    return "\n".join(parts)


async def run_designer(session: Session, *, spec: PartSpec | None = None, model: str | None = None, budget: int = ITERATION_BUDGET,
                       critic_rounds: int = 2, user_message: str | None = None, strategy: str | None = None,
                       resume_message: str | None = None, max_turns: int = 150, critic_model: str | None = None,
                       run_critic: bool = True, photos: list[Path] | None = None) -> RunOutcome:
    from agent_sdk import (
        AgentOptions, SDKClient, create_sdk_mcp_server,
    )

    t0 = time.time()
    spec = spec or session.spec()
    model = model or os.environ.get("KIN_DESIGNER_MODEL", "opus")
    state = RunState()

    def emit(kind: str, **data):
        session.emit(kind, **data)

    from agent_sdk import HookMatcher

    tools = make_tools(session, state, spec, budget, emit)
    server = create_sdk_mcp_server("kin", tools=tools)
    env = {"OPENSCADPATH": str(VENDOR_DIR)}
    options = AgentOptions(
        cwd=str(session.dir), model=model, system_prompt=DESIGNER_PROMPT, permission_mode="bypassPermissions",
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash", "mcp__kin__iterate", "mcp__kin__list_templates",
                       "mcp__kin__read_template", "mcp__kin__ask_user", "mcp__kin__finish"],
        disallowed_tools=["WebSearch", "WebFetch", "Task", "TodoWrite", "NotebookEdit", "ToolSearch"],
        mcp_servers={"kin": server}, max_turns=max_turns, setting_sources=[], env=env, add_dirs=[str(TEMPLATES_DIR)],
        max_buffer_size=64 * 1024 * 1024,
        hooks={"PreToolUse": [HookMatcher(matcher="Write|Edit|MultiEdit|NotebookEdit|Bash|Read", hooks=[make_sandbox_hook(session.dir)])]},
    )
    session.update_meta(status="running", model=model)
    emit("run_start", model=model, budget=budget)
    status = "error"
    try:
        async with SDKClient(options) as client:
            prompt = resume_message or initial_prompt(spec, user_message, strategy)
            await client.query(prompt)
            await _drain(client, state, emit)
            rounds = 0
            while not state.question and state.finished and run_critic and rounds < critic_rounds:
                rounds += 1
                verdict = await _run_critic(session, spec, state, critic_model, photos, emit)
                state.critic_verdicts.append(verdict)
                if verdict.verdict in ("pass", "error"):
                    break
                if verdict.verdict == "ask_user":
                    state.question = {"question": verdict.question_for_user or verdict.summary, "options": []}
                    session.update_meta(status="waiting_user", question=state.question)
                    emit("question", **state.question)
                    break
                # revise: send the discrepancies back to the same designer session
                state.finished = False
                followup = ("A code-blind critic reviewed the drawings of your last iteration and asks for changes:\n"
                            + verdict.summary_for_model()
                            + "\n\nAddress every high and medium item (or explain in the finish narration why a request is wrong per the spec), "
                              "iterate until checks pass, then call finish again.")
                emit("critic_followup", round=rounds)
                await client.query(followup)
                await _drain(client, state, emit)
            if state.question:
                status = "waiting_user"
            elif state.finished:
                status = "done"
            elif state.error:
                status = "error"
            elif state.last_result and state.last_result.budget_left == 0:
                status = "budget_exhausted"
            else:
                status = "stopped"
    except Exception as e:  # pragma: no cover
        state.error = f"{type(e).__name__}: {e}"
        status = "error"
        emit("error", message=state.error)
    session.update_meta(status=status, narration=state.narration, cost_usd=round(state.cost_usd, 4))
    emit("run_end", status=status, iterations=len(state.iterations), cost_usd=round(state.cost_usd, 4))
    return RunOutcome(status, state, session, time.time() - t0)


STALL_TIMEOUT_S = float(os.environ.get("KIN_STALL_TIMEOUT_S", "900"))


class StalledError(RuntimeError):
    pass


async def _drain(client, state: RunState, emit) -> None:
    """Consume the designer's messages; raise StalledError when nothing arrives for STALL_TIMEOUT_S."""
    from agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

    it = client.receive_response().__aiter__()
    while True:
        try:
            msg = await asyncio.wait_for(it.__anext__(), timeout=STALL_TIMEOUT_S)
        except StopAsyncIteration:
            break
        except asyncio.TimeoutError:
            emit("error", message=f"no message from the model for {STALL_TIMEOUT_S:.0f}s; run aborted as stalled")
            raise StalledError("designer stalled")
        if isinstance(msg, AssistantMessage):
            for b in msg.content:
                if isinstance(b, TextBlock) and b.text.strip():
                    emit("assistant", text=b.text.strip()[:4000])
                elif isinstance(b, ToolUseBlock):
                    brief = {k: (str(v)[:160]) for k, v in (b.input or {}).items() if k in ("label", "name", "file_path", "command", "question", "pattern")}
                    emit("tool_use", tool=b.name, input=brief)
        elif isinstance(msg, ResultMessage):
            state.cost_usd += float(msg.total_cost_usd or 0.0)
            state.turns += int(msg.num_turns or 0)
            if msg.is_error or (msg.subtype and msg.subtype != "success"):
                state.error = f"{msg.subtype}: {(msg.result or '')[:400]} {' | '.join(msg.errors or [])}".strip()
                emit("error", message=state.error, stop_reason=msg.stop_reason)
            elif msg.stop_reason:
                emit("result", stop_reason=msg.stop_reason, turns=msg.num_turns)


async def _run_critic(session: Session, spec: PartSpec, state: RunState, critic_model, photos, emit) -> CriticVerdict:
    res = state.last_result
    sheets: list[Path] = []
    prev: list[Path] = []
    if res and res.blueprint:
        sheets = [p for p in (res.blueprint.sheet_path, res.blueprint.sections_path) if p]
    if len(state.iterations) >= 2:
        pr = state.iterations[-2]
        if pr.blueprint:
            prev = [p for p in (pr.blueprint.sheet_path,) if p]
    emit("critic_start", iteration=res.iteration if res else None)
    verdict = await critique(spec, res.checks if res else None, sheets, prev_sheets=prev, photos=photos, model=critic_model, cwd=session.dir)
    n = res.iteration if res else 0
    (session.dir / "critic" / f"iter_{n:02d}.json").write_text(json.dumps(verdict.to_dict(), indent=2))
    session.update_meta(critic_rounds=int(session.meta.get("critic_rounds", 0)) + 1)
    session.commit(f"critic review of iteration {n}: {verdict.verdict}")
    emit("critic", iteration=n, verdict=verdict.verdict, summary=verdict.summary, discrepancies=verdict.discrepancies)
    return verdict
