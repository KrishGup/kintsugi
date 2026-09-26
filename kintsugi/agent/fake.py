"""A scripted stand-in for the OpenAI Responses client so the whole design loop runs without a key.

`FakeResponsesClient` mimics `client.responses.create(...)`: each call returns the next scripted turn as SDK-shaped
objects (function_call items, message items, usage). The default script designs the bottle handle from the template
and finishes; `fake_complete` answers the one-turn prompts (intake, critic, judge) with canned JSON.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from kintsugi import TEMPLATES_DIR

Turn = list[dict[str, Any]]  # [{"text": "..."} | {"call": name, "args": {...} | callable(ctx) -> args}]


def default_design_script(template: str = "ring_loop_handle") -> list[Turn]:
    def write_args(ctx: dict[str, Any]) -> dict[str, Any]:
        src = (TEMPLATES_DIR / f"{template}.scad").read_text(encoding="utf-8")
        return {"path": "part.scad", "content": src}

    return [
        [{"call": "read_file", "args": {"path": "spec.yaml"}}],
        [{"call": "list_templates", "args": {}}],
        [{"call": "read_template", "args": {"name": template}}],
        [{"text": "The template matches the part class; adapting it."}, {"call": "write_file", "args": write_args}],
        [{"call": "iterate", "args": {"label": f"initial design from the {template} template"}}],
        [{"text": "All hard checks pass and the drawings match the spec."},
         {"call": "finish", "args": {"narration": "Designed from the vetted template; every interface dimension measured within tolerance on the exported mesh. Print flat as modeled."}}],
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
        # a new run starts when the input is a single user message (no transcript yet)
        if len(inputs) == 1 and isinstance(inputs[0], dict) and inputs[0].get("role") == "user":
            self._runs += 1
            self._pos = 0
            self._active = self._turns if self._runs == 1 else self._followup
        turns = getattr(self, "_active", self._turns)
        if self._pos >= len(turns):
            turn: Turn = [{"text": "Done."}]
        else:
            turn = turns[self._pos]
            self._pos += 1
        ctx = {"kwargs": kwargs, "inputs": inputs}
        output = []
        for item in turn:
            if "text" in item:
                output.append(SimpleNamespace(type="message", id=f"msg_{next(self._ids)}", role="assistant",
                                              content=[SimpleNamespace(type="output_text", text=item["text"], annotations=[])]))
            else:
                args = item["args"](ctx) if callable(item["args"]) else item["args"]
                output.append(SimpleNamespace(type="function_call", id=f"fc_{next(self._ids)}", call_id=f"call_{next(self._ids)}",
                                              name=item["call"], arguments=json.dumps(args)))
        text = "\n".join(c.text for o in output if o.type == "message" for c in o.content)
        usage = SimpleNamespace(input_tokens=1000, output_tokens=200, input_tokens_details=SimpleNamespace(cached_tokens=0))
        return SimpleNamespace(id=f"resp_{next(self._ids)}", output=output, output_text=text, usage=usage)


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


__all__ = ["FakeResponsesClient", "default_design_script", "revise_script", "fake_complete", "make_fake_llm", "Path", "Callable"]
