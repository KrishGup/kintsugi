"""Intake: photos + a sentence -> what broke, a draft Part Spec, a capture plan and batched questions."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from kintsugi import PACKAGE_DIR
from kintsugi.agent.critic import _image_block
from kintsugi.session.workspace import Session
from kintsugi.spec.model import PartSpec

INTAKE_PROMPT = (PACKAGE_DIR / "agent" / "prompts" / "intake.md").read_text(encoding="utf-8")


def parse_intake(text: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", text.strip(), re.S)
    if not m:
        raise ValueError("intake returned no JSON")
    return json.loads(m.group(0))


async def run_intake(session: Session, text: str, photos: list[Path], model: str | None = None) -> dict[str, Any]:
    from agent_sdk import AssistantMessage, AgentOptions, SDKClient, TextBlock

    model = model or os.environ.get("KIN_VISION_MODEL", "opus")
    content: list[dict[str, Any]] = [{"type": "text", "text": f"USER SAYS: {text or '(no description)'}\n\nPHOTOS FOLLOW."}]
    for p in photos[:6]:
        blk = _image_block(p, max_side=1400)
        if blk:
            content.append({"type": "text", "text": f"photo: {p.name}"})
            content.append(blk)
    content.append({"type": "text", "text": "Produce the JSON now."})
    options = AgentOptions(system_prompt=INTAKE_PROMPT, model=model, allowed_tools=[], max_turns=1, setting_sources=[],
                                 disallowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch", "Task", "TodoWrite"],
                                 permission_mode="dontAsk", cwd=str(session.dir))
    out: list[str] = []
    t0 = time.time()

    async def gen():
        yield {"type": "user", "message": {"role": "user", "content": content}, "parent_tool_use_id": None, "session_id": "intake"}

    async with SDKClient(options) as client:
        await client.query(gen(), session_id="intake")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for b in msg.content:
                    if isinstance(b, TextBlock):
                        out.append(b.text)
    data = parse_intake("\n".join(out))
    # validate the spec part
    spec_data = data.get("spec") or {}
    try:
        spec = PartSpec.model_validate(spec_data)
    except Exception as e:
        data["spec_error"] = str(e)
        spec = PartSpec()
    if not spec.part.name or spec.part.name == "part":
        spec.part.name = re.sub(r"[^a-z0-9]+", "_", (data.get("part_role") or session.meta.get("name") or "part").lower()).strip("_")[:40] or "part"
    spec.save(session.spec_path)
    (session.dir / "intake.json").write_text(json.dumps(data, indent=2))
    session.update_meta(status="intake_done", name=spec.part.name)
    session.commit("intake: draft spec")
    session.emit("intake", object=data.get("object"), part_role=data.get("part_role"), questions=data.get("questions", []),
                 capture_plan=data.get("capture_plan", []), duration_s=round(time.time() - t0, 1))
    data["spec_yaml"] = spec.to_yaml()
    return data
