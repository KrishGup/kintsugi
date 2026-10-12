"""The designer agent: an agentic loop in the session workspace with the Kintsugi tools, followed by the critic.

Two runtimes share the tools and the policy:
  openai  — the Responses API tool loop in kintsugi.agent.llm with our own file/shell tools (default)
  agent  — the agent SDK session (kept for environments with a Agent login)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from kintsugi import PACKAGE_DIR, TEMPLATES_DIR, VENDOR_DIR
from kintsugi.agent.critic import CriticVerdict, critique
from kintsugi.agent.llm import LLM, get_llm, text_part
from kintsugi.agent.pipeline import ITERATION_BUDGET, IterationResult
from kintsugi.agent.tools import Sandbox, make_file_tools, make_kin_tools, templates_index
from kintsugi.session.workspace import Session
from kintsugi.spec.model import PartSpec

_PROMPT_TEMPLATE = (PACKAGE_DIR / "agent" / "prompts" / "designer.md").read_text(encoding="utf-8")

FILE_TOOLS_OPENAI = (
    "- File and shell tools: `read_file(path)` (text files come back with line numbers; PNG/JPG paths come back as images, so "
    "read a view from `iterations/iter_NN/sheets/views/` to look closer), `write_file(path, content)`, "
    "`edit_file(path, old_string, new_string)`, `list_files(path)`, `run_command(command)` (openscad, python with numpy/"
    "trimesh/opencv, no network; runs in bash when the host has it, otherwise the host's own shell — prefer the file tools "
    "and `iterate` over shell commands). Everything is confined to the session directory."
)
FILE_TOOLS_AGENT = (
    "- Standard file tools (Read, Write, Edit, Glob, Grep, Bash). Use Read on the PNG paths returned by `iterate` to look "
    "closer at any view."
)


def designer_prompt(provider: str) -> str:
    from kintsugi.agent.knowledge import summary_for_prompt

    return (_PROMPT_TEMPLATE.replace("{FILE_TOOLS}", FILE_TOOLS_OPENAI if provider != "agent" else FILE_TOOLS_AGENT)
            .replace("{KNOWLEDGE_TOOLS}", summary_for_prompt()))


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
    cost_capped: bool = False


@dataclass
class RunOutcome:
    status: str  # done | waiting_user | budget_exhausted | cost_capped | stopped | error
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


def initial_prompt(spec: PartSpec, user_message: str | None, strategy: str | None) -> str:
    parts = ["Design the part described by spec.yaml in this directory.", "", "SPEC SUMMARY:", spec.summary_for_model(), ""]
    if strategy:
        parts += [f"STRATEGY: {strategy}", ""]
    if user_message:
        parts += ["USER NOTES:", user_message, ""]
    parts.append("Start by reading spec.yaml and list_templates(). Then write part.scad and call iterate.")
    return "\n".join(parts)


def existing_part_note(session: Session) -> str:
    """Appended to a fresh prompt when the session already holds a part: a change request must build on it."""
    n = int(session.meta.get("iteration", 0))
    return (f"\n\nThe session already has a part.scad ({n} iteration{'s' if n != 1 else ''} so far, the current values are the user's). "
            "Read part.scad and the latest iterations/iter_NN/summary.txt first, then make the change requested above and iterate; "
            "do not start over from a template unless the change needs a different part class.")


CRITIC_FOLLOWUP = ("A code-blind critic reviewed the drawings of your last iteration and asks for changes:\n{verdict}\n\n"
                   "Address every high and medium item (or explain in the finish narration why a request is wrong per the spec), "
                   "iterate until checks pass, then call finish again.")


async def run_designer(session: Session, *, spec: PartSpec | None = None, model: str | None = None, budget: int = ITERATION_BUDGET,
                       critic_rounds: int = 2, user_message: str | None = None, strategy: str | None = None,
                       resume_message: str | None = None, max_turns: int = 150, critic_model: str | None = None,
                       run_critic: bool = True, photos: list[Path] | None = None, llm: LLM | None = None,
                       hide_templates: bool = False) -> RunOutcome:
    """Design the part in the session, then review it with the critic (up to `critic_rounds` revise cycles)."""
    llm = llm or get_llm()
    t0 = time.time()
    spec = spec or session.spec()
    state = RunState()

    def emit(kind: str, **data):
        session.emit(kind, **data)

    model = model or llm.models["designer"]
    session.update_meta(status="running", model=model, provider=llm.provider)
    emit("run_start", model=model, provider=llm.provider, budget=budget)
    if hide_templates and not strategy:
        strategy = "Do NOT use the template catalog for this run; design from primitives and BOSL2."
    try:
        if llm.provider == "agent":
            status = await _run_agent(session, spec, state, model, budget, critic_rounds, user_message, strategy, resume_message,
                                       max_turns, critic_model, run_critic, photos, emit, llm, hide_templates)
        else:
            status = await _run_openai(session, spec, state, model, budget, critic_rounds, user_message, strategy, resume_message,
                                       max_turns, critic_model, run_critic, photos, emit, llm, hide_templates)
    except Exception as e:  # pragma: no cover
        state.error = f"{type(e).__name__}: {e}"
        status = "error"
        emit("error", message=state.error)
    session.update_meta(status=status, narration=state.narration, cost_usd=round(state.cost_usd, 4), question=state.question)
    emit("run_end", status=status, iterations=len(state.iterations), cost_usd=round(state.cost_usd, 4),
         duration_s=round(time.time() - t0, 1))
    return RunOutcome(status, state, session, time.time() - t0)


def _status(state: RunState) -> str:
    if state.question:
        return "waiting_user"
    if state.finished:
        return "done"
    if state.error:
        return "error"
    if state.cost_capped:
        return "cost_capped"
    if state.last_result and state.last_result.budget_left == 0:
        return "budget_exhausted"
    return "stopped"


def spend_cap_usd() -> float | None:
    """KIN_MAX_COST_USD: the most one run may spend on model calls (the client's own token accounting); unset or 0 = no cap.
    A shared or public deployment should set it — the iteration budget bounds work, this bounds money."""
    raw = os.environ.get("KIN_MAX_COST_USD", "").strip()
    try:
        v = float(raw) if raw else 0.0
    except ValueError:
        v = 0.0
    return v if v > 0 else None


# ---- OpenAI runtime ------------------------------------------------------------------------------------

async def _run_openai(session, spec, state, model, budget, critic_rounds, user_message, strategy, resume_message, max_turns,
                      critic_model, run_critic, photos, emit, llm: LLM, hide_templates: bool) -> str:
    sandbox = Sandbox(session.dir)
    tools = make_file_tools(sandbox) + make_kin_tools(session, state, spec, budget, emit, hide_templates=hide_templates)
    system = designer_prompt(llm.provider)
    prompt = resume_message or initial_prompt(spec, user_message, strategy)
    if resume_message:
        prompt += "\n\n(Context: the design session continues; read part.scad and the latest iterations/iter_NN/summary.txt first.)"
    elif session.scad_path.exists():
        prompt += existing_part_note(session)
    parts = [text_part(prompt)]
    cost0 = llm.usage.cost_usd
    calls0 = llm.usage.calls
    cap = spend_cap_usd()

    def left() -> float | None:
        """what this run may still spend (KIN_MAX_COST_USD is per run; a resumed run counts from its own start)"""
        return None if cap is None else max(0.0, cap - (llm.usage.cost_usd - cost0))

    def on_text(t: str):
        emit("assistant", text=t.strip()[:4000])

    def on_tool(name: str, args: dict[str, Any]):
        brief = {k: (str(v)[:160]) for k, v in args.items() if k in ("label", "name", "path", "command", "question")}
        emit("tool_use", tool=name, input=brief)

    def on_step(n: int):
        emit("step", n=n)

    res = await llm.run_tools(system=system, parts=parts, tools=tools, model=model, max_steps=max_turns, on_text=on_text,
                              on_tool=on_tool, on_step=on_step, cost_limit_usd=left())
    state.turns += res.steps
    if res.stopped_by == "cost_cap":
        state.cost_capped = True
        emit("cost_cap", message=res.error or "spend cap reached", cap_usd=cap)
    elif res.error:
        state.error = res.error
        emit("error", message=res.error)
    if not state.finished and not state.question and not res.error and res.stopped_by is None and state.last_result and state.last_result.ok:
        # the model stopped talking instead of calling finish although the last iteration passed: one nudge
        emit("assistant", text="(designer stopped without calling finish; asking it to wrap up)")
        nudge = [text_part("You stopped without calling finish, but your last iteration passed every check. Read part.scad and the latest "
                           "iterations/iter_NN/summary.txt; if the design is complete call finish(narration=...), otherwise continue iterating.")]
        res = await llm.run_tools(system=system, parts=nudge, tools=tools, model=model, max_steps=max(10, max_turns // 5),
                                  on_text=on_text, on_tool=on_tool, on_step=on_step, cost_limit_usd=left())
        state.turns += res.steps
        if res.stopped_by == "cost_cap":
            state.cost_capped = True
            emit("cost_cap", message=res.error or "spend cap reached", cap_usd=cap)
        elif res.error:
            state.error = res.error
            emit("error", message=res.error)
    rounds = 0
    followup_parts: list[dict[str, Any]] | None = None
    # the critic loop: the designer continues in a fresh tool loop that carries the critic's verdict
    while not state.question and state.finished and run_critic and rounds < critic_rounds and not state.error and not state.cost_capped:
        rounds += 1
        verdict = await _run_critic(session, spec, state, critic_model, photos, emit, llm)
        state.critic_verdicts.append(verdict)
        if verdict.verdict in ("pass", "error"):
            break
        if verdict.verdict == "ask_user":
            state.question = {"question": verdict.question_for_user or verdict.summary, "options": []}
            session.update_meta(status="waiting_user", question=state.question)
            emit("question", **state.question)
            break
        state.finished = False
        emit("critic_followup", round=rounds)
        followup_parts = [text_part(CRITIC_FOLLOWUP.format(verdict=verdict.summary_for_model())
                                    + "\n\nRead part.scad first (it is the current design), then make the changes.")]
        res = await llm.run_tools(system=system, parts=followup_parts, tools=tools, model=model, max_steps=max_turns,
                                  on_text=on_text, on_tool=on_tool, on_step=on_step, cost_limit_usd=left())
        state.turns += res.steps
        if res.stopped_by == "cost_cap":
            state.cost_capped = True
            emit("cost_cap", message=res.error or "spend cap reached", cap_usd=cap)
        elif res.error:
            state.error = res.error
            emit("error", message=res.error)
    state.cost_usd += llm.usage.cost_usd - cost0
    emit("usage", calls=llm.usage.calls - calls0, cost_usd=round(llm.usage.cost_usd - cost0, 4), model=model)
    return _status(state)


# ---- Agent runtime (Agent SDK) -------------------------------------------------------------------------

STALL_TIMEOUT_S = float(os.environ.get("KIN_STALL_TIMEOUT_S", "900"))


class StalledError(RuntimeError):
    pass


def make_sandbox_hook(session_dir: Path):
    """PreToolUse hook for the SDK path: the designer may only write inside its session directory."""
    sb = Sandbox(session_dir)

    async def hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
        tool = input_data.get("tool_name", "")
        ti = input_data.get("tool_input") or {}
        deny = None
        if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            fp = str(ti.get("file_path") or ti.get("notebook_path") or "")
            if not sb.inside(fp):
                deny = f"writes are limited to the session directory {sb.root}; write to part.scad there"
        elif tool == "Read":
            fp = str(ti.get("file_path") or "")
            if fp and not sb.readable(fp):
                deny = "reading is limited to the session directory, templates and the BOSL2 library"
        elif tool == "Bash":
            deny = sb.command_ok(str(ti.get("command") or ""))
        if deny:
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": deny}}
        return {}

    return hook


def _sdk_tools(session: Session, state: RunState, spec: PartSpec, budget: int, emit, hide_templates: bool):
    """Wrap the shared kin tools as SDK MCP tools."""
    from agent_sdk import tool

    kin = make_kin_tools(session, state, spec, budget, emit, hide_templates=hide_templates)
    wrapped = []
    for td in kin:
        def make(td):
            @tool(td.name, td.description, td.parameters)
            async def fn(args: dict[str, Any]) -> dict[str, Any]:
                r = await td.handler(args)
                content: list[dict[str, Any]] = [{"type": "text", "text": r.text}]
                for data, mime in r.images:
                    import base64 as _b64
                    content.append({"type": "image", "data": _b64.b64encode(data).decode(), "mimeType": mime})
                out: dict[str, Any] = {"content": content}
                if r.is_error:
                    out["is_error"] = True
                return out
            return fn
        wrapped.append(make(td))
    return wrapped


async def _run_agent(session, spec, state, model, budget, critic_rounds, user_message, strategy, resume_message, max_turns,
                      critic_model, run_critic, photos, emit, llm: LLM, hide_templates: bool) -> str:
    from agent_sdk import AgentOptions, SDKClient, HookMatcher, create_sdk_mcp_server

    server = create_sdk_mcp_server("kin", tools=_sdk_tools(session, state, spec, budget, emit, hide_templates))
    options = AgentOptions(
        cwd=str(session.dir), model=model, system_prompt=designer_prompt("agent"), permission_mode="bypassPermissions",
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash", "mcp__kin__iterate", "mcp__kin__list_templates",
                       "mcp__kin__read_template", "mcp__kin__ask_user", "mcp__kin__finish"],
        disallowed_tools=["WebSearch", "WebFetch", "Task", "TodoWrite", "NotebookEdit", "ToolSearch"],
        mcp_servers={"kin": server}, max_turns=max_turns, setting_sources=[], env={"OPENSCADPATH": str(VENDOR_DIR)},
        add_dirs=[str(TEMPLATES_DIR)], max_buffer_size=64 * 1024 * 1024,
        max_thinking_tokens=int(os.environ.get("KIN_THINKING_TOKENS", "12000")),
        hooks={"PreToolUse": [HookMatcher(matcher="Write|Edit|MultiEdit|NotebookEdit|Bash|Read", hooks=[make_sandbox_hook(session.dir)])]},
    )
    async with SDKClient(options) as client:
        first = resume_message or initial_prompt(spec, user_message, strategy)
        if not resume_message and session.scad_path.exists():
            first += existing_part_note(session)
        await client.query(first)
        await _drain(client, state, emit)
        rounds = 0
        while not state.question and state.finished and run_critic and rounds < critic_rounds:
            rounds += 1
            verdict = await _run_critic(session, spec, state, critic_model, photos, emit, llm)
            state.critic_verdicts.append(verdict)
            if verdict.verdict in ("pass", "error"):
                break
            if verdict.verdict == "ask_user":
                state.question = {"question": verdict.question_for_user or verdict.summary, "options": []}
                session.update_meta(status="waiting_user", question=state.question)
                emit("question", **state.question)
                break
            state.finished = False
            emit("critic_followup", round=rounds)
            await client.query(CRITIC_FOLLOWUP.format(verdict=verdict.summary_for_model()))
            await _drain(client, state, emit)
    return _status(state)


async def _drain(client, state: RunState, emit) -> None:
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
        if type(msg).__name__ in ("SystemMessage", "RateLimitEvent"):
            emit("sdk", type=type(msg).__name__, subtype=str(getattr(msg, "subtype", ""))[:60])
        if isinstance(msg, AssistantMessage):
            for b in msg.content:
                if isinstance(b, TextBlock) and b.text.strip():
                    emit("assistant", text=b.text.strip()[:4000])
                elif isinstance(b, ToolUseBlock):
                    brief = {k: (str(v)[:160]) for k, v in (b.input or {}).items() if k in ("label", "name", "file_path", "command", "question", "pattern")}
                    emit("tool_use", tool=b.name.replace("mcp__kin__", ""), input=brief)
        elif isinstance(msg, ResultMessage):
            state.cost_usd += float(msg.total_cost_usd or 0.0)
            state.turns += int(msg.num_turns or 0)
            if msg.is_error or (msg.subtype and msg.subtype != "success"):
                state.error = f"{msg.subtype}: {(msg.result or '')[:400]} {' | '.join(msg.errors or [])}".strip()
                emit("error", message=state.error, stop_reason=msg.stop_reason)


# ---- critic step (shared) --------------------------------------------------------------------------------

async def _run_critic(session: Session, spec: PartSpec, state: RunState, critic_model, photos, emit, llm: LLM) -> CriticVerdict:
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
    verdict = await critique(spec, res.checks if res else None, sheets, prev_sheets=prev, photos=photos, model=critic_model, llm=llm)
    n = res.iteration if res else 0
    (session.dir / "critic" / f"iter_{n:02d}.json").write_text(json.dumps(verdict.to_dict(), indent=2), encoding="utf-8")
    session.update_meta(critic_rounds=int(session.meta.get("critic_rounds", 0)) + 1)
    session.commit(f"critic review of iteration {n}: {verdict.verdict}")
    emit("critic", iteration=n, verdict=verdict.verdict, summary=verdict.summary, discrepancies=verdict.discrepancies)
    return verdict


__all__ = ["run_designer", "RunOutcome", "RunState", "designer_prompt", "templates_index", "initial_prompt", "Callable"]
