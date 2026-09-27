"""A scripted stand-in for the OpenAI Responses client so the whole design loop runs without a key.

`FakeResponsesClient` mimics `client.responses.create(...)`: each call returns the next scripted turn as SDK-shaped
objects (function_call items, message items, usage). The default script designs the bottle handle from the template
and finishes; `fake_complete` answers the one-turn prompts (intake, critic, judge) with canned JSON.
"""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from kintsugi import TEMPLATES_DIR

Turn = list[dict[str, Any]]  # [{"text": "..."} | {"call": name, "args": {...} | callable(ctx) -> args}]


# which vetted template answers which part class (the spec's part.name); the reference template's spec predates the
# <template>.yaml naming rule
TEMPLATE_FOR = {
    "bottle_handle": "ring_loop_handle", "ring_loop_handle": "ring_loop_handle",
    "cap_threaded": "cap_threaded", "hook": "hook", "knob_d_shaft": "knob_d_shaft", "l_bracket": "l_bracket",
    "snap_clip": "snap_clip", "spacer_gasket": "spacer_gasket",
}


def template_for(part_name: str | None) -> str | None:
    """The template whose spec this part class is, or None when demo mode has nothing vetted for it."""
    if not part_name:
        return None
    key = part_name.strip().lower().replace(" ", "_").replace("-", "_")
    if key in TEMPLATE_FOR:
        return TEMPLATE_FOR[key]
    for k, v in TEMPLATE_FOR.items():          # "bottle handle v2", "my_hook"
        if k in key:
            return v
    return None


def _spec_part_name(inputs: list[Any]) -> str | None:
    """The part.name from the spec.yaml the designer read, found in the transcript's tool outputs."""
    for item in inputs:
        if not isinstance(item, dict) or item.get("type") != "function_call_output":
            continue
        out = item.get("output")
        text = out if isinstance(out, str) else "\n".join(str(c.get("text", "")) for c in (out or []) if isinstance(c, dict))
        # read_file prefixes line numbers ("    2|   name: bottle_handle"); strip them before looking
        plain = "\n".join(re.sub(r"^\s*\d+\|\s?", "", ln) for ln in text.splitlines())
        m = re.search(r"^part:\s*\n(?:[ \t]+\w+:.*\n)*?[ \t]+name:[ \t]*['\"]?([\w .-]+)", plain, re.M)
        if m:
            return m.group(1).strip()
    return None


def _last_iterate_ok(inputs: list[Any]) -> bool | None:
    """Did the most recent iterate in the transcript pass every hard check? (None when no iterate has run yet.)"""
    ok: bool | None = None
    for item in inputs:
        if not isinstance(item, dict) or item.get("type") != "function_call_output":
            continue
        out = item.get("output")
        text = out if isinstance(out, str) else "\n".join(str(c.get("text", "")) for c in (out or []) if isinstance(c, dict))
        if "=== ITERATION" in text:
            ok = "STATUS: all hard checks pass" in text or "ALL HARD CHECKS PASS" in text
    return ok


def _failing_lines(inputs: list[Any]) -> list[str]:
    for item in reversed(inputs):
        if not isinstance(item, dict) or item.get("type") != "function_call_output":
            continue
        out = item.get("output")
        text = out if isinstance(out, str) else "\n".join(str(c.get("text", "")) for c in (out or []) if isinstance(c, dict))
        if "=== ITERATION" in text:
            return [ln.strip()[7:] for ln in text.splitlines() if ln.strip().startswith("[FAIL]")][:4]
    return []


def default_design_script(template: str | None = None) -> list[Turn]:
    """The scripted designer. It reads the spec, picks the vetted template for that part class, and — for the bottle
    handle, the hero — first writes a plausible-but-wrong version (a loop too wide for the spec's 110 mm envelope),
    reads the check table that catches it, fixes it, and finishes: the verify-and-revise loop, in demo mode, in
    twenty seconds. Other part classes go straight to their template. A spec with no template gets an honest
    message, the nearest template so the checks show the gap, and no false finish."""

    def chosen(ctx: dict[str, Any]) -> str | None:
        return template or template_for(_spec_part_name(ctx["inputs"]))

    def read_template_args(ctx):
        return {"name": chosen(ctx) or "ring_loop_handle"}

    def first_write_args(ctx):
        t = chosen(ctx) or "ring_loop_handle"
        src = (TEMPLATES_DIR / f"{t}.scad").read_text(encoding="utf-8")
        if t == "ring_loop_handle" and template_for(_spec_part_name(ctx["inputs"])) == "ring_loop_handle":
            # the deliberate first attempt: a wider loop for a gloved hand — 127 mm overall against the 110 mm envelope
            src = src.replace("loop_inner_w = 42;", "loop_inner_w = 60;", 1)
        return {"path": "part.scad", "content": src}

    def first_text(ctx):
        t = chosen(ctx)
        name = _spec_part_name(ctx["inputs"]) or "this part"
        if t is None:
            return (f"Demo mode designs from the vetted template catalog, and none of them is a {name}. Switching the provider to "
                    "OpenAI in Settings designs it from the spec; here I will write the nearest template so the checks show the gap.")
        if t == "ring_loop_handle":
            return "The ring-and-loop template matches the part class. Adapting it: a wider finger loop for a gloved hand."
        return f"The {t} template matches the part class; adapting it to the spec's dimensions."

    def after_first_iterate(ctx):
        ok = _last_iterate_ok(ctx["inputs"])
        t = chosen(ctx)
        if ok:
            return [{"text": "Every hard check passes and the drawings match the spec."},
                    {"call": "finish", "args": {"narration": f"Designed from the vetted {t} template; every interface dimension measured within tolerance on the exported mesh. Print flat as modeled."}}]
        if t == "ring_loop_handle":
            fails = _failing_lines(ctx["inputs"])
            why = fails[0] if fails else "footprint.overall_length is over the 110 mm limit"
            src = (TEMPLATES_DIR / "ring_loop_handle.scad").read_text(encoding="utf-8")
            return [{"text": f"The check table catches it: {why}. The wider loop pushes the part past the spec's envelope — narrowing the loop back to 42 mm keeps two fingers' room and the footprint inside 110 mm."},
                    {"call": "write_file", "args": {"path": "part.scad", "content": src}}]
        fails = _failing_lines(ctx["inputs"])
        return [{"text": "The checks show what a real run would have to fix: " + ("; ".join(fails) if fails else "the interface dimensions do not match this part class")
                         + ". Demo mode stops here — with an OpenAI key the designer iterates on the code until they pass."}]

    def after_second_iterate(ctx):
        ok = _last_iterate_ok(ctx["inputs"])
        if ok:
            return [{"text": "Overall length is back inside the envelope and every other check still passes."},
                    {"call": "finish", "args": {"narration": "Started from the vetted ring-and-loop template with a wider loop; the footprint check caught the 127 mm overall length against the 110 mm limit, so the loop went back to 42 mm. Every interface dimension is measured within tolerance on the exported mesh. Print flat as modeled."}}]
        return [{"text": "A check still fails after the revision; stopping so the numbers stay honest."}]

    return [
        [{"call": "read_file", "args": {"path": "spec.yaml"}}],
        [{"call": "list_templates", "args": {}}],
        [{"call": "read_template", "args": read_template_args}],
        [{"text": first_text}, {"call": "write_file", "args": first_write_args}],
        [{"call": "iterate", "args": lambda ctx: {"label": ("first attempt: wider loop" if chosen(ctx) == "ring_loop_handle" and template_for(_spec_part_name(ctx["inputs"])) == "ring_loop_handle"
                                                              else f"initial design from the {chosen(ctx) or 'nearest'} template")}}],
        {"dynamic": after_first_iterate},
        [{"call": "iterate", "args": {"label": "loop narrowed to 42 mm — footprint inside 110 mm"}}],
        {"dynamic": after_second_iterate},
    ]


def revise_script() -> list[Turn]:
    """After a critic 'revise', the designer re-runs iterate and finishes."""
    return [
        [{"call": "read_file", "args": {"path": "part.scad", "limit": 40}}],
        [{"call": "iterate", "args": {"label": "re-verified after critic review"}}],
        [{"call": "finish", "args": {"narration": "Re-verified after the critic's review; all checks still pass."}}],
    ]


class FakeResponsesClient:
    """Duck-types the async OpenAI client: `await client.responses.create(**kwargs)`."""

    def __init__(self, script: list[Turn] | None = None, followup_script: list[Turn] | None = None):
        self._turns = list(script or default_design_script())
        self._followup = list(followup_script or revise_script())
        self._ids = itertools.count(1)
        self.calls: list[dict[str, Any]] = []
        self._runs = 0
        self.responses = SimpleNamespace(create=self.create)

    async def create(self, **kwargs) -> Any:
        inputs = kwargs.get("input") or []
        self.calls.append({**kwargs, "input": list(inputs)})  # snapshot: the loop mutates its transcript list
        # a new run starts when the input is a single user message (no transcript yet); a session that already holds a
        # part (a change request, a resume after ask_user) gets the follow-up script, a fresh one the design script
        if len(inputs) == 1 and isinstance(inputs[0], dict) and inputs[0].get("role") == "user":
            self._runs += 1
            self._pos = 0
            text = _user_text(inputs[0])
            existing = ("already has a part.scad" in text or "session continues" in text
                        or "code-blind critic reviewed" in text or "Read part.scad first" in text)
            self._active = self._followup if existing else self._turns
        turns = getattr(self, "_active", self._turns)
        ctx = {"kwargs": kwargs, "inputs": inputs}
        if self._pos >= len(turns):
            turn: Turn = [{"text": "Done."}]
        else:
            turn = turns[self._pos]
            self._pos += 1
            if isinstance(turn, dict) and "dynamic" in turn:      # a turn decided from the transcript (a check outcome)
                turn = turn["dynamic"](ctx)
                if not any("call" in it for it in turn):
                    self._pos = len(turns)                         # a text-only dynamic turn ends the run
        output = []
        for item in turn:
            if "text" in item:
                text_v = item["text"](ctx) if callable(item["text"]) else item["text"]
                output.append(SimpleNamespace(type="message", id=f"msg_{next(self._ids)}", role="assistant",
                                              content=[SimpleNamespace(type="output_text", text=text_v, annotations=[])]))
            else:
                args = item["args"](ctx) if callable(item["args"]) else item["args"]
                output.append(SimpleNamespace(type="function_call", id=f"fc_{next(self._ids)}", call_id=f"call_{next(self._ids)}",
                                              name=item["call"], arguments=json.dumps(args)))
        text = "\n".join(c.text for o in output if o.type == "message" for c in o.content)
        usage = SimpleNamespace(input_tokens=1000, output_tokens=200, input_tokens_details=SimpleNamespace(cached_tokens=0))
        return SimpleNamespace(id=f"resp_{next(self._ids)}", output=output, output_text=text, usage=usage)


def _user_text(item: dict[str, Any]) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content
    out = []
    for c in content or []:
        if isinstance(c, dict) and c.get("type") in ("input_text", "text"):
            out.append(str(c.get("text", "")))
    return "\n".join(out)


def fake_complete(system: str, parts: list[dict[str, Any]]) -> str:
    """Canned one-turn answers keyed on the prompt's role."""
    head = system[:200].lower()
    if "critic" in head:
        return json.dumps({
            "inspection": {"load_path": "continuous", "intent_features": [], "unexplained_features": [], "thinnest_section": "n/a",
                           "junctions": "filleted", "assembly": "no interference", "printability": "flat on the bed"},
            "verdict": "pass", "summary": "Scripted critic: the drawings match the spec.", "discrepancies": []})
    if "intake" in head:
        return json.dumps({
            "object": "1 L wide-mouth water bottle", "part_role": "carry handle: a ring under the cap with a finger loop",
            "damage": "the loop snapped off at the ring", "interfaces_reasoning": "the ring must fit the neck under the cap flange",
            "spec": {
                "part": {"name": "bottle_handle", "role": "carry handle; ring under the cap flange with a two-finger loop",
                         "object": "1 L wide-mouth plastic bottle", "design_intent": "reinforced loop with finger scallops"},
                "interfaces": [{"id": "neck_ring", "type": "cylindrical_bore", "mates_with": "bottle neck under the cap flange", "fit": "sliding",
                                "clearance": 0.25,
                                "dims": {"inner_diameter": {"target": 43.0, "tol": 0.3, "status": "estimated",
                                                            "estimates": [{"value": 43.0, "source": "vision_estimate", "conf": 0.3}],
                                                            "measure": {"recipe": "circle_fit_inner", "at_z": 3.0, "near": [0, 0], "feature": "ring bore"}},
                                         "ring_height": {"target": 6.0, "tol": 0.5, "status": "estimated",
                                                         "estimates": [{"value": 6.0, "source": "vision_estimate", "conf": 0.3}],
                                                         "measure": {"recipe": "extent", "axis": "z", "feature": "ring height"}}}}],
                "requirements": [{"id": "load", "text": "carry a full 1 L bottle by two fingers",
                                  "derived": {"loop_inner_width": {"min": 40, "measure": {"recipe": "hole_extent", "at_z": 3.0, "axis": "x", "near": [60, 0]}}}}],
                "context": [{"id": "neck", "shape": "cylinder", "d": 43.0, "h": 12, "at": [0, 0, -3]},
                            {"id": "cap_flange", "shape": "cylinder", "d": 62, "h": 3, "at": [0, 0, 6.3]}],
                "print": {"material": "PETG", "nozzle": 0.4, "layer_height": 0.2, "min_wall": 1.6, "orientation_hint": "ring flat on the bed"},
                "open_questions": []},
            "capture_plan": [{"n": 1, "name": "neck on the sheet", "purpose": "neck diameter", "how": "invert the bottle, press the neck onto the calibration sheet, shoot straight down", "measures": ["neck_ring.inner_diameter"]}],
            "questions": [{"id": "q1", "text": "Measure the neck's outer diameter with a ruler (mm)", "kind": "number", "options": [], "dim": "neck_ring.inner_diameter"}],
            "confidence": 0.5})
    if "judging two candidate" in head or "judge" in head:
        return json.dumps({"preferred": "tie", "scores": {"A": {"fit": 8, "printability": 8, "strength": 8, "intent": 8, "overall": 8},
                                                             "B": {"fit": 8, "printability": 8, "strength": 8, "intent": 8, "overall": 8}},
                           "reasoning": "Scripted judge."})
    return json.dumps({"ok": True})


def make_fake_llm(script: list[Turn] | None = None, followup: list[Turn] | None = None):
    from kintsugi.agent.llm import LLM
    return LLM(provider="fake", client=FakeResponsesClient(script, followup))


__all__ = ["FakeResponsesClient", "default_design_script", "revise_script", "fake_complete", "make_fake_llm", "template_for", "Path", "Callable"]
