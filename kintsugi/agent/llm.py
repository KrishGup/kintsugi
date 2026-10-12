"""Model provider facade: OpenAI (default, Responses API) or Agent (Agent SDK), behind one small interface.

Two operations cover everything Kintsugi needs from a model:
  complete()   one turn, text + images in, text (usually JSON) out            -> intake, critic, judge
  run_tools()  an agentic loop over our own tools (files, shell, iterate ...) -> the designer

The OpenAI path talks to the Responses API directly with function tools; tool results may carry images (the
blueprint sheets) so the designer looks at its drawings after every iteration. The Agent path keeps the Agent SDK.
A `fake` provider replays scripted responses so the whole loop can be tested without a key.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from PIL import Image, ImageOps

# ---- pricing (USD per 1M tokens), used for the cost readout only ------------------------------------
PRICES: dict[str, tuple[float, float, float]] = {  # input, cached input, output
    "gpt-6-astra": (10.0, 1.0, 50.0),
    "gpt-6-sol": (2.0, 0.5, 10.0),
    "gpt-6-luna": (0.4, 0.1, 1.6),
}

DEFAULT_MODELS = {
    "openai": {"designer": "gpt-6-astra", "critic": "gpt-6-astra", "vision": "gpt-6-astra", "fast": "gpt-6-sol"},
    "agent": {"designer": "opus", "critic": "opus", "vision": "opus", "fast": "sonnet"},
    "fake": {"designer": "fake", "critic": "fake", "vision": "fake", "fast": "fake"},
}


@dataclass
class ToolResult:
    text: str
    images: list[tuple[bytes, str]] = field(default_factory=list)  # (bytes, mime)
    is_error: bool = False


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], Awaitable[ToolResult]]

    def openai_schema(self) -> dict[str, Any]:
        params = dict(self.parameters)
        params.setdefault("type", "object")
        params.setdefault("additionalProperties", False)
        return {"type": "function", "name": self.name, "description": self.description, "parameters": params, "strict": False}


@dataclass
class Usage:
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0

    def add(self, model: str, inp: int, cached: int, out: int) -> None:
        self.input_tokens += inp
        self.cached_tokens += cached
        self.output_tokens += out
        self.calls += 1
        p = PRICES.get(model.split(":")[0])
        if p:
            self.cost_usd += (max(inp - cached, 0) * p[0] + cached * p[1] + out * p[2]) / 1e6

    def to_dict(self) -> dict[str, Any]:
        return {"input_tokens": self.input_tokens, "cached_tokens": self.cached_tokens, "output_tokens": self.output_tokens,
                "cost_usd": round(self.cost_usd, 4), "calls": self.calls}


@dataclass
class ToolLoopResult:
    texts: list[str]
    steps: int
    stopped_by: str | None  # tool name that ended the loop, or None
    usage: Usage
    error: str | None = None


def image_part(path: Path, max_side: int = 1600, quality: int = 80) -> dict[str, Any] | None:
    """A provider-neutral image part: {"type": "image", "data": bytes, "mime": "image/jpeg"}."""
    try:
        Image.init()
        im = Image.open(path)
        try:
            im = ImageOps.exif_transpose(im)  # phone photos carry their rotation in EXIF
        except Exception:
            pass
        im = im.convert("RGB")
    except Exception:
        return None
    w, h = im.size
    if max(w, h) > max_side:
        r = max_side / max(w, h)
        im = im.resize((int(w * r), int(h * r)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True)
    return {"type": "image", "data": buf.getvalue(), "mime": "image/jpeg"}


def text_part(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def detect_provider() -> str:
    """KIN_PROVIDER if set, else OpenAI (the default; the app asks for a key when none is configured).

    The Agent and fake providers are opt-in only, so a stray Agent login on the machine never changes what runs."""
    p = os.environ.get("KIN_PROVIDER", "").lower().strip()
    if p in ("openai", "agent", "fake"):
        return p
    return "openai"


class LLM:
    def __init__(self, provider: str | None = None, client: Any = None):
        self.provider = provider or detect_provider()
        self._client = client
        env = os.environ
        d = DEFAULT_MODELS[self.provider]
        fast = env.get("KIN_FAST", "").lower() in ("1", "true", "yes")
        # The KIN_*_MODEL settings name real models. Demo mode ignores them: otherwise the scripted run is labelled
        # gpt-6-astra and its placeholder token counts are priced as if a model had been paid for.
        pick = (lambda key: None) if self.provider == "fake" else env.get
        self.models = {
            "designer": pick("KIN_DESIGNER_MODEL") or (d["fast"] if fast else d["designer"]),
            "critic": pick("KIN_CRITIC_MODEL") or (d["fast"] if fast else d["critic"]),
            "vision": pick("KIN_VISION_MODEL") or (d["fast"] if fast else d["vision"]),
        }
        self.effort = env.get("KIN_REASONING_EFFORT", "high")
        self.usage = Usage()

    # ---- status ------------------------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        ok, why = self.available()
        return {"provider": self.provider, "models": self.models, "effort": self.effort, "ready": ok, "reason": why}

    def available(self) -> tuple[bool, str]:
        if self.provider == "openai":
            if not os.environ.get("OPENAI_API_KEY") and self._client is None:
                return False, "OPENAI_API_KEY is not set"
            return True, "OpenAI Responses API"
        if self.provider == "agent":
            if os.environ.get("AGENT_API_KEY") or shutil.which("agent"):
                return True, "agent SDK"
            return False, "no AGENT_API_KEY and no agent CLI"
        return True, "demo mode: a scripted designer, no key needed"

    # ---- clients -----------------------------------------------------------------------------------
    def openai_client(self):
        if self._client is not None:
            return self._client
        if self.provider == "fake":
            from kintsugi.agent.fake import FakeResponsesClient
            self._client = FakeResponsesClient()
            return self._client
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(max_retries=int(os.environ.get("KIN_OPENAI_RETRIES", "6")),
                                   timeout=float(os.environ.get("KIN_OPENAI_TIMEOUT_S", "900")))
        return self._client

    # ---- one-turn completion -----------------------------------------------------------------------
    async def complete(self, *, system: str, parts: list[dict[str, Any]], model: str | None = None, json_mode: bool = True,
                       effort: str | None = None, max_output_tokens: int = 24000, role: str = "vision") -> str:
        model = model or self.models[role]
        if self.provider == "openai":
            return await self._openai_complete(system, parts, model, json_mode, effort or self.effort, max_output_tokens)
        if self.provider == "agent":
            return await self._agent_complete(system, parts, model, json_mode)
        return await self._fake_complete(system, parts)

    async def _openai_complete(self, system, parts, model, json_mode, effort, max_output_tokens) -> str:
        client = self.openai_client()
        content = [_oa_part(p) for p in parts]
        kwargs: dict[str, Any] = {
            "model": model, "instructions": system, "input": [{"role": "user", "content": content}],
            "max_output_tokens": max_output_tokens, "store": False,
        }
        if _is_reasoning_model(model):
            kwargs["reasoning"] = {"effort": _clamp_effort(effort, model)}
        if json_mode:
            kwargs["text"] = {"format": {"type": "json_object"}}
        resp = await client.responses.create(**kwargs)
        self._account(model, resp)
        text = _oa_output_text(resp)
        if getattr(resp, "status", "") == "incomplete" and not text.strip():
            # reasoning ate the output budget: once more with room to answer and a lighter effort
            kwargs["max_output_tokens"] = max_output_tokens * 2
            if "reasoning" in kwargs:
                kwargs["reasoning"] = {"effort": "medium" if kwargs["reasoning"]["effort"] in ("high", "xhigh", "max") else kwargs["reasoning"]["effort"]}
            resp = await client.responses.create(**kwargs)
            self._account(model, resp)
            text = _oa_output_text(resp)
        return text

    async def _agent_complete(self, system, parts, model, json_mode) -> str:
        from agent_sdk import AssistantMessage, AgentOptions, SDKClient, TextBlock

        content = []
        for p in parts:
            if p["type"] == "text":
                content.append({"type": "text", "text": p["text"]})
            else:
                content.append({"type": "image", "source": {"type": "base64", "media_type": p["mime"], "data": base64.b64encode(p["data"]).decode()}})
        if json_mode:
            content.append({"type": "text", "text": "Respond with the JSON object only."})
        options = AgentOptions(system_prompt=system, model=model, allowed_tools=[], max_turns=1, setting_sources=[],
                                     disallowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch", "Task", "TodoWrite"],
                                     permission_mode="dontAsk")
        out: list[str] = []

        async def gen():
            yield {"type": "user", "message": {"role": "user", "content": content}, "parent_tool_use_id": None, "session_id": "one"}

        async with SDKClient(options) as client:
            await client.query(gen(), session_id="one")
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for b in msg.content:
                        if isinstance(b, TextBlock):
                            out.append(b.text)
                elif type(msg).__name__ == "ResultMessage":
                    self.usage.calls += 1
                    self.usage.cost_usd += float(getattr(msg, "total_cost_usd", 0.0) or 0.0)
        return "\n".join(out)

    async def _fake_complete(self, system, parts) -> str:
        from kintsugi.agent.fake import fake_complete
        return fake_complete(system, parts)

    # ---- agentic tool loop -------------------------------------------------------------------------
    async def run_tools(self, *, system: str, parts: list[dict[str, Any]], tools: list[ToolDef], model: str | None = None,
                        effort: str | None = None, max_steps: int = 60, stop_tools: tuple[str, ...] = ("finish", "ask_user"),
                        on_text: Callable[[str], None] | None = None, on_tool: Callable[[str, dict[str, Any]], None] | None = None,
                        on_step: Callable[[int], None] | None = None, followups: list[str] | None = None,
                        role: str = "designer", cost_limit_usd: float | None = None) -> ToolLoopResult:
        """Run the model against `tools` until it stops calling them, calls a stop tool, hits max_steps, or — when
        `cost_limit_usd` is set — has spent that much (by the client's own token accounting) in this loop."""
        model = model or self.models[role]
        if self.provider == "openai":
            return await self._openai_loop(system, parts, tools, model, effort or self.effort, max_steps, stop_tools, on_text, on_tool, on_step, cost_limit_usd)
        if self.provider == "fake":
            return await self._openai_loop(system, parts, tools, model, "none", max_steps, stop_tools, on_text, on_tool, on_step, cost_limit_usd)
        raise NotImplementedError("the Agent designer runs through the Agent SDK path in designer.py")

    async def _openai_loop(self, system, parts, tools, model, effort, max_steps, stop_tools, on_text, on_tool, on_step,
                           cost_limit_usd: float | None = None) -> ToolLoopResult:
        """The Responses-API tool loop.

        Stateful mode (default): the conversation lives on OpenAI's side and each step sends only the new tool outputs with
        `previous_response_id`, so the growing pile of blueprint images is not re-uploaded on every step. Stateless mode
        (`KIN_OPENAI_STATELESS=1`, or automatically after a stateful request is rejected): the full transcript is resent
        with `store=False`, carrying the reasoning items' encrypted content so reasoning survives across tool calls.
        """
        client = self.openai_client()
        by_name = {t.name: t for t in tools}
        schemas = [t.openai_schema() for t in tools]
        stateless = self.provider == "fake" or os.environ.get("KIN_OPENAI_STATELESS", "").lower() in ("1", "true", "yes")
        first_user: dict[str, Any] = {"role": "user", "content": [_oa_part(p) for p in parts]}
        transcript: list[dict[str, Any]] = [first_user]  # complete client-side copy (stateless mode sends all of it)
        pending: list[dict[str, Any]] = [first_user]     # stateful mode sends only what is new since the last response
        prev_id: str | None = None
        texts: list[str] = []
        stopped_by = None
        steps = 0
        error = None
        truncations = 0
        images_split = os.environ.get("KIN_OPENAI_IMAGES_AS_MESSAGE", "").lower() in ("1", "true", "yes")
        max_out = int(os.environ.get("KIN_MAX_OUTPUT_TOKENS", "32000"))
        cost_start = self.usage.cost_usd
        step = 0
        while step < max_steps:
            if cost_limit_usd is not None and self.usage.cost_usd - cost_start >= cost_limit_usd:
                error = f"spend cap reached: ${self.usage.cost_usd - cost_start:.2f} of ${cost_limit_usd:.2f} for this run"
                stopped_by = "cost_cap"
                break
            step += 1
            steps = step
            if on_step:
                on_step(step)
            kwargs: dict[str, Any] = {
                "model": model, "instructions": system, "tools": schemas, "max_output_tokens": max_out, "parallel_tool_calls": False,
            }
            if stateless:
                kwargs.update({"input": transcript, "store": False})
                if _is_reasoning_model(model):
                    kwargs["include"] = ["reasoning.encrypted_content"]
            else:
                kwargs.update({"input": pending, "store": True})
                if prev_id:
                    kwargs["previous_response_id"] = prev_id
            if _is_reasoning_model(model):
                kwargs["reasoning"] = {"effort": _clamp_effort(effort, model)}
            try:
                resp = await client.responses.create(**kwargs)
            except Exception as e:  # after the SDK's own retries
                msg = str(e)
                if not stateless and prev_id is None and _looks_like_store_rejection(msg):
                    # the org cannot store responses: switch to the stateless transcript and retry this step
                    stateless = True
                    step -= 1
                    continue
                if not images_split and getattr(e, "status_code", None) == 400 and any(_has_image_output(i) for i in pending):
                    # the API rejected images inside function_call_output: send them as a user message instead
                    images_split = True
                    pending = _split_images(pending)
                    transcript = _split_images(transcript)
                    step -= 1
                    continue
                error = f"{type(e).__name__}: {msg[:300]}"
                break
            self._account(model, resp)
            prev_id = getattr(resp, "id", None) or prev_id
            pending = []
            outputs = list(resp.output or [])
            transcript.extend(x for x in (_oa_item_to_input(o, stateless) for o in outputs) if x is not None)
            calls = [o for o in outputs if getattr(o, "type", "") == "function_call"]
            for o in outputs:
                if getattr(o, "type", "") == "message":
                    for c in getattr(o, "content", []) or []:
                        if getattr(c, "type", "") == "output_text" and c.text.strip():
                            texts.append(c.text)
                            if on_text:
                                on_text(c.text)
            if not calls:
                if getattr(resp, "status", "") == "incomplete" and truncations < 2:
                    # the reasoning/output hit max_output_tokens before a tool call: ask for the next step in smaller pieces
                    truncations += 1
                    nudge = {"role": "user", "content": [{"type": "input_text", "text": "Your last response was cut off by the output limit. "
                                                                                          "Continue from where you were; make smaller edits and call tools one at a time."}]}
                    transcript.append(nudge)
                    pending.append(nudge)
                    continue
                break
            stop = False
            for call in calls:
                name = call.name
                try:
                    args = json.loads(call.arguments or "{}")
                except json.JSONDecodeError:
                    args = {"_raw": call.arguments}
                if on_tool:
                    on_tool(name, args)
                tool = by_name.get(name)
                if tool is None:
                    result = ToolResult(f"unknown tool {name}", is_error=True)
                else:
                    try:
                        result = await tool.handler(args)
                    except Exception as e:
                        result = ToolResult(f"{name} failed: {type(e).__name__}: {e}", is_error=True)
                items = [_oa_call_output(call.call_id, result)]
                if images_split:
                    items = _split_images(items)
                transcript.extend(items)
                pending.extend(items)
                if name in stop_tools and not result.is_error:
                    stopped_by = name
                    stop = True
            if stop:
                break
        return ToolLoopResult(texts, steps, stopped_by, self.usage, error)

    def _account(self, model: str, resp: Any) -> None:
        u = getattr(resp, "usage", None)
        if not u:
            return
        cached = 0
        det = getattr(u, "input_tokens_details", None)
        if det is not None:
            cached = int(getattr(det, "cached_tokens", 0) or 0)
        self.usage.add(model, int(getattr(u, "input_tokens", 0) or 0), cached, int(getattr(u, "output_tokens", 0) or 0))


# ---- OpenAI payload helpers -------------------------------------------------------------------------

def _is_reasoning_model(model: str) -> bool:
    m = model.lower()
    return m.startswith(("gpt-6", "gpt-5", "o1", "o3", "o4")) and not m.startswith(("gpt-5-chat",))


def _clamp_effort(effort: str, model: str) -> str:
    e = (effort or "medium").lower()
    allowed = ("none", "low", "medium", "high", "xhigh", "max")
    if e not in allowed:
        e = "medium"
    if e == "none" and "astra" in model:  # astra has no 'none'
        e = "low"
    return e


def _data_url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def _oa_part(p: dict[str, Any]) -> dict[str, Any]:
    if p["type"] == "text":
        return {"type": "input_text", "text": p["text"]}
    return {"type": "input_image", "image_url": _data_url(p["data"], p["mime"]), "detail": p.get("detail", "high")}


def _oa_call_output(call_id: str, result: ToolResult) -> dict[str, Any]:
    if result.images:
        out: list[dict[str, Any]] = [{"type": "input_text", "text": result.text}]
        for data, mime in result.images:
            out.append({"type": "input_image", "image_url": _data_url(data, mime), "detail": "high"})
        return {"type": "function_call_output", "call_id": call_id, "output": out}
    return {"type": "function_call_output", "call_id": call_id, "output": result.text}


def _looks_like_store_rejection(msg: str) -> bool:
    m = msg.lower()
    return ("store" in m or "previous_response_id" in m or "retention" in m) and ("not" in m or "unsupported" in m or "invalid" in m)


def _has_image_output(item: dict[str, Any]) -> bool:
    return item.get("type") == "function_call_output" and isinstance(item.get("output"), list)


def _split_images(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rewrite function_call_output items that carry images into a text output plus a user message with the images."""
    out: list[dict[str, Any]] = []
    for it in items:
        if _has_image_output(it):
            texts = [c["text"] for c in it["output"] if c.get("type") == "input_text"]
            images = [c for c in it["output"] if c.get("type") == "input_image"]
            out.append({**it, "output": "\n".join(texts) or "(see the attached images)"})
            if images:
                out.append({"role": "user", "content": [{"type": "input_text", "text": "Images returned by the tool call above:"}, *images]})
        else:
            out.append(it)
    return out


def _oa_item_to_input(o: Any, stateless: bool = True) -> dict[str, Any] | None:
    """Convert a response output item back into an input item (so the transcript stays complete)."""
    t = getattr(o, "type", None)
    if t == "reasoning":
        d = o.model_dump(exclude_none=True) if hasattr(o, "model_dump") else dict(o)
        keep = {k: v for k, v in d.items() if k in ("id", "type", "summary", "encrypted_content")}
        if stateless and not keep.get("encrypted_content"):
            # without the encrypted payload a stored-less reasoning item cannot be replayed; the following
            # function_call still replays fine on its own
            return None
        keep.setdefault("summary", [])
        return keep
    if t == "message":
        return {"type": "message", "role": "assistant", "id": getattr(o, "id", None), "status": "completed",
                "content": [{"type": "output_text", "text": c.text, "annotations": []} for c in (o.content or []) if getattr(c, "type", "") == "output_text"]}
    if t == "function_call":
        return {"type": "function_call", "id": getattr(o, "id", None), "call_id": o.call_id, "name": o.name, "arguments": o.arguments or "{}"}
    return None


def _oa_output_text(resp: Any) -> str:
    txt = getattr(resp, "output_text", None)
    if txt:
        return txt
    parts = []
    for o in getattr(resp, "output", []) or []:
        if getattr(o, "type", "") == "message":
            for c in getattr(o, "content", []) or []:
                if getattr(c, "type", "") == "output_text":
                    parts.append(c.text)
    return "\n".join(parts)


# ---- module-level singleton ---------------------------------------------------------------------------
_LLM: LLM | None = None


def get_llm(reset: bool = False) -> LLM:
    global _LLM
    if _LLM is None or reset:
        _LLM = LLM()
    return _LLM


def set_llm(llm: LLM) -> None:
    global _LLM
    _LLM = llm


async def with_timeout(coro, seconds: float, what: str = "model call"):
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError as e:
        raise TimeoutError(f"{what} exceeded {seconds:.0f}s") from e


__all__ = ["LLM", "ToolDef", "ToolResult", "ToolLoopResult", "Usage", "get_llm", "set_llm", "image_part", "text_part",
           "detect_provider", "PRICES", "DEFAULT_MODELS", "with_timeout", "time"]
