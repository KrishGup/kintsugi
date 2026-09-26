"""Agent runtime tests without a model key: the OpenAI-style tool loop with a scripted client, and the web API end to end."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from kintsugi.agent.fake import FakeResponsesClient, default_design_script, revise_script
from kintsugi.agent.llm import LLM, ToolDef, ToolResult
from kintsugi.scad.compile import openscad_version

pytestmark = pytest.mark.skipif(openscad_version() is None, reason="openscad not installed")

SPEC = Path(__file__).parent.parent / "eval" / "specs" / "bottle_handle.yaml"


def test_tool_loop_with_images_and_stop():
    """The Responses-style loop: function calls are executed, image results are attached, stop tools end the loop."""
    seen: list[str] = []

    async def echo(args):
        seen.append(args.get("x", ""))
        return ToolResult("ok " + str(args.get("x")), images=[(b"\x89PNG\r\n", "image/png")])

    async def finish(args):
        return ToolResult("done")

    tools = [ToolDef("echo", "echo", {"type": "object", "properties": {"x": {"type": "string"}}}, echo),
             ToolDef("finish", "finish", {"type": "object", "properties": {}}, finish)]
    client = FakeResponsesClient(script=[[{"call": "echo", "args": {"x": "a"}}], [{"text": "thinking"}, {"call": "echo", "args": {"x": "b"}}],
                                         [{"call": "finish", "args": {}}], [{"call": "echo", "args": {"x": "never"}}]])
    llm = LLM(provider="fake", client=client)
    res = asyncio.run(llm.run_tools(system="s", parts=[{"type": "text", "text": "go"}], tools=tools, max_steps=10))
    assert seen == ["a", "b"] and res.stopped_by == "finish" and res.steps == 3
    # the transcript carried the image back as an input_image item
    last_call = client.calls[-1]
    outs = [i for i in last_call["input"] if isinstance(i, dict) and i.get("type") == "function_call_output"]
    assert any(isinstance(o["output"], list) and o["output"][1]["type"] == "input_image" for o in outs)
    assert res.texts == ["thinking"]


def test_designer_fake_provider(tmp_path):
    from kintsugi.agent.designer import run_designer
    from kintsugi.session.workspace import Session
    from kintsugi.spec.model import PartSpec

    spec = PartSpec.load(SPEC)
    s = Session.create("fake", spec, sessions_dir=tmp_path)
    llm = LLM(provider="fake", client=FakeResponsesClient(default_design_script(), revise_script()))
    out = asyncio.run(run_designer(s, spec=spec, llm=llm, critic_rounds=1))
    assert out.status == "done" and out.state.last_result and out.state.last_result.ok
    kinds = [json.loads(line)["kind"] for line in (s.dir / "events.jsonl").read_text().splitlines()]
    for k in ("run_start", "tool_use", "iteration", "narration", "critic", "run_end"):
        assert k in kinds, k
    assert (s.dir / "iterations" / "iter_01" / "sheets" / "iter_01_sheet.png").exists()
    assert s.meta["status"] == "done"


def test_sandbox_rules(tmp_path):
    from kintsugi.agent.tools import Sandbox, make_file_tools

    sb = Sandbox(tmp_path)
    assert sb.inside("part.scad") and not sb.inside("/etc/passwd") and not sb.inside("../x")
    assert sb.command_ok("openscad -o part.stl part.scad") is None
    assert sb.command_ok("pip install foo") and sb.command_ok("cat /etc/passwd") and sb.command_ok("cd .. && ls")
    tools = {t.name: t for t in make_file_tools(sb)}
    r = asyncio.run(tools["write_file"].handler({"path": "a.txt", "content": "hello\nworld\n"}))
    assert not r.is_error
    r = asyncio.run(tools["read_file"].handler({"path": "a.txt"}))
    assert "1| hello" in r.text
    r = asyncio.run(tools["edit_file"].handler({"path": "a.txt", "old_string": "world", "new_string": "there"}))
    assert not r.is_error and (tmp_path / "a.txt").read_text() == "hello\nthere\n"
    r = asyncio.run(tools["write_file"].handler({"path": "/tmp/evil.txt", "content": "x"}))
    assert r.is_error
    r = asyncio.run(tools["run_command"].handler({"command": "echo hi && ls"}))
    assert "hi" in r.text and "a.txt" in r.text and not r.is_error


def test_web_api_end_to_end(tmp_path, monkeypatch):
    """Create a session, run the fake designer through the API, follow the events, apply params, export."""
    monkeypatch.setenv("KIN_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("KIN_PROVIDER", "fake")
    from fastapi.testclient import TestClient

    import kintsugi.server.app as appmod
    from kintsugi.agent.llm import get_llm

    get_llm(reset=True)
    appmod.SESSIONS_DIR = (tmp_path / "sessions").resolve()
    appmod.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    with TestClient(appmod.app) as c:
        h = c.get("/api/health").json()
        assert h["ok"] and h["llm"]["provider"] == "fake" and h["llm"]["ready"]
        s = c.post("/api/sessions", json={"name": "api", "spec_yaml": SPEC.read_text()}).json()
        sid = s["meta"]["id"]
        assert s["stage"] == "spec"
        r = c.post(f"/api/sessions/{sid}/run", json={"budget": 4, "critic_rounds": 1})
        assert r.status_code == 202
        # poll the detail until the run ends
        for _ in range(120):
            d = c.get(f"/api/sessions/{sid}").json()
            if d["meta"].get("status") in ("done", "error", "stopped") and not d["running"]:
                break
            time.sleep(0.5)
        assert d["meta"]["status"] == "done", d["meta"]
        assert d["stage"] == "review" and d["iterations"] and d["iterations"][-1]["ok"]
        evs = c.get(f"/api/sessions/{sid}/events", params={"since": 0, "once": "true"}).json()
        kinds = [e["kind"] for e in evs["events"]]
        assert kinds[0] == "run_start" and "run_end" in kinds and evs["next"] == len(kinds)
        r = c.post(f"/api/sessions/{sid}/params", json={"values": {"loop_inner_h": 24}}).json()
        assert r["ok"]
        r = c.post(f"/api/sessions/{sid}/export").json()
        assert "bundle" in r["files"]
        d = c.get(f"/api/sessions/{sid}").json()
        assert d["stage"] == "export" and "bundle.zip" in d["export"]
        f = c.get(f"/api/sessions/{sid}/files/export/print_card.md")
        assert f.status_code == 200 and "Print card" in f.text
        # answers endpoint confirms a dimension
        r = c.post(f"/api/sessions/{sid}/answers", json={"answers": [{"id": "q1", "dim": "neck_ring.ring_outer_diameter", "kind": "number", "value": 52}]}).json()
        assert r["ok"] and "neck_ring.ring_outer_diameter" not in r["unconfirmed"]
        st = c.post("/api/settings", json={"effort": "medium"}).json()
        assert st["ok"] and st["llm"]["effort"] == "medium"


def test_sse_stream_live_server(tmp_path, monkeypatch):
    """The SSE endpoint streams the log from a real server (the TestClient cannot close a streaming response early)."""
    import socket
    import threading
    import urllib.request

    import uvicorn

    monkeypatch.setenv("KIN_PROVIDER", "fake")
    import kintsugi.server.app as appmod
    from kintsugi.session.workspace import Session
    from kintsugi.spec.model import PartSpec

    appmod.SESSIONS_DIR = (tmp_path / "sessions").resolve()
    appmod.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    s = Session.create("sse", PartSpec.load(SPEC), sessions_dir=appmod.SESSIONS_DIR)
    s.emit("run_start", model="fake")
    s.emit("narration", text="hello")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    config = uvicorn.Config(appmod.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/sessions/{s.id}/events?since=0")
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.headers["content-type"].startswith("text/event-stream")
            got = b""
            while b'"text": "hello"' not in got:
                chunk = resp.readline()
                assert chunk, "stream ended early"
                got += chunk
            assert b"event: run_start" in got and b"event: narration" in got
    finally:
        server.should_exit = True
        th.join(timeout=10)


def _mock_openai(script):
    """A real AsyncOpenAI client whose HTTP layer answers /responses from `script` (list of output-item lists)."""
    import httpx
    from openai import AsyncOpenAI

    requests: list[dict] = []
    n = {"i": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content or b"{}")
        requests.append(body)
        i = min(n["i"], len(script) - 1)
        n["i"] += 1
        out = script[i]
        payload = {
            "id": f"resp_{i + 1}", "object": "response", "created_at": 1700000000, "model": body.get("model", "gpt-6-astra"), "status": "completed",
            "output": out, "parallel_tool_calls": False, "tool_choice": "auto", "tools": body.get("tools", []), "error": None, "incomplete_details": None,
            "usage": {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500, "input_tokens_details": {"cached_tokens": 1000},
                      "output_tokens_details": {"reasoning_tokens": 100}},
        }
        return httpx.Response(200, json=payload, headers={"content-type": "application/json"})

    client = AsyncOpenAI(api_key="sk-test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), max_retries=0)
    return client, requests


def _fc(i, name, args):
    return {"type": "function_call", "id": f"fc_{i}", "call_id": f"call_{i}", "name": name, "arguments": json.dumps(args), "status": "completed"}


def _msg(i, text):
    return {"type": "message", "id": f"msg_{i}", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": text, "annotations": []}]}


def _rs(i):
    return {"type": "reasoning", "id": f"rs_{i}", "summary": [], "encrypted_content": f"enc_{i}"}


def test_openai_wire_format_stateful(monkeypatch):
    """Through the real SDK: tools, reasoning effort, previous_response_id chaining, image tool outputs, usage accounting."""
    monkeypatch.delenv("KIN_OPENAI_STATELESS", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    script = [[_rs(1), _fc(1, "echo", {"x": "a"})], [_rs(2), _msg(2, "now finishing"), _fc(2, "finish", {})]]
    client, requests = _mock_openai(script)
    seen = []

    async def echo(args):
        seen.append(args["x"])
        return ToolResult("ok", images=[(b"\xff\xd8\xff", "image/jpeg")])

    async def finish(args):
        return ToolResult("done")

    tools = [ToolDef("echo", "echo", {"type": "object", "properties": {"x": {"type": "string"}}}, echo), ToolDef("finish", "finish", {"type": "object", "properties": {}}, finish)]
    llm = LLM(provider="openai", client=client)
    res = asyncio.run(llm.run_tools(system="sys", parts=[{"type": "text", "text": "go"}, {"type": "image", "data": b"\x89PNG", "mime": "image/png"}], tools=tools, model="gpt-6-astra", effort="high"))
    assert res.stopped_by == "finish" and res.error is None and seen == ["a"] and res.texts == ["now finishing"]
    r1, r2 = requests
    assert r1["model"] == "gpt-6-astra" and r1["instructions"] == "sys" and r1["store"] is True and r1["reasoning"] == {"effort": "high"}
    assert r1["parallel_tool_calls"] is False and [t["name"] for t in r1["tools"]] == ["echo", "finish"] and r1["tools"][0]["type"] == "function"
    assert r1["input"][0]["role"] == "user" and r1["input"][0]["content"][1]["type"] == "input_image" and r1["input"][0]["content"][1]["image_url"].startswith("data:image/png;base64,")
    assert "previous_response_id" not in r1
    # step 2 sends only the new tool output, chained to the first response
    assert r2["previous_response_id"] == "resp_1" and len(r2["input"]) == 1
    fo = r2["input"][0]
    assert fo["type"] == "function_call_output" and fo["call_id"] == "call_1" and fo["output"][1]["type"] == "input_image"
    assert fo["output"][1]["image_url"].startswith("data:image/jpeg;base64,")
    u = llm.usage.to_dict()
    assert u["calls"] == 2 and u["input_tokens"] == 2400 and u["cached_tokens"] == 2000 and u["cost_usd"] > 0


def test_openai_wire_format_stateless(monkeypatch):
    """Stateless mode resends the transcript with store=false, encrypted reasoning included and replayed."""
    monkeypatch.setenv("KIN_OPENAI_STATELESS", "1")
    script = [[_rs(1), _fc(1, "echo", {"x": "a"})], [_msg(2, "bye")]]
    client, requests = _mock_openai(script)

    async def echo(args):
        return ToolResult("ok")

    tools = [ToolDef("echo", "echo", {"type": "object", "properties": {"x": {"type": "string"}}}, echo)]
    llm = LLM(provider="openai", client=client)
    res = asyncio.run(llm.run_tools(system="sys", parts=[{"type": "text", "text": "go"}], tools=tools, model="gpt-6-sol", effort="medium"))
    assert res.stopped_by is None and res.texts == ["bye"] and res.steps == 2
    r1, r2 = requests
    assert r1["store"] is False and r1["include"] == ["reasoning.encrypted_content"] and "previous_response_id" not in r1
    types = [i.get("type") or i.get("role") for i in r2["input"]]
    assert types == ["user", "reasoning", "function_call", "function_call_output"], types
    assert r2["input"][1]["encrypted_content"] == "enc_1" and r2["input"][2]["call_id"] == "call_1" and r2["input"][3]["output"] == "ok"


def test_openai_complete_json_mode(monkeypatch):
    """One-turn completion (critic / intake): instructions, json_object format, reasoning effort clamp for astra."""
    monkeypatch.delenv("KIN_OPENAI_STATELESS", raising=False)
    client, requests = _mock_openai([[_msg(1, '{"verdict": "pass"}')]])
    llm = LLM(provider="openai", client=client)
    out = asyncio.run(llm.complete(system="You are the critic", parts=[{"type": "text", "text": "look"}], model="gpt-6-astra", effort="none", role="critic"))
    assert json.loads(out)["verdict"] == "pass"
    r = requests[0]
    assert r["text"] == {"format": {"type": "json_object"}} and r["reasoning"] == {"effort": "low"} and r["store"] is False and r["instructions"] == "You are the critic"


def test_openai_truncation_nudge(monkeypatch):
    """An incomplete response without a tool call gets one nudge instead of ending the run."""
    import httpx
    from openai import AsyncOpenAI

    monkeypatch.delenv("KIN_OPENAI_STATELESS", raising=False)
    requests: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content or b"{}")
        requests.append(body)
        first = len(requests) == 1
        payload = {"id": f"resp_{len(requests)}", "object": "response", "created_at": 1, "model": "gpt-6-astra",
                   "status": "incomplete" if first else "completed", "incomplete_details": {"reason": "max_output_tokens"} if first else None,
                   "output": [_rs(1)] if first else [_fc(2, "finish", {})], "parallel_tool_calls": False, "tool_choice": "auto", "tools": [], "error": None,
                   "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2, "input_tokens_details": {"cached_tokens": 0}}}
        return httpx.Response(200, json=payload)

    client = AsyncOpenAI(api_key="sk-test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), max_retries=0)

    async def finish(args):
        return ToolResult("done")

    llm = LLM(provider="openai", client=client)
    res = asyncio.run(llm.run_tools(system="s", parts=[{"type": "text", "text": "go"}], tools=[ToolDef("finish", "f", {"type": "object", "properties": {}}, finish)], model="gpt-6-astra"))
    assert res.stopped_by == "finish" and res.steps == 2
    assert requests[1]["previous_response_id"] == "resp_1" and "cut off" in requests[1]["input"][0]["content"][0]["text"]


def test_openai_image_output_fallback(monkeypatch):
    """If the API rejects images inside function_call_output, they are resent as a user message and the loop continues."""
    import httpx
    from openai import AsyncOpenAI

    monkeypatch.delenv("KIN_OPENAI_STATELESS", raising=False)
    requests: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content or b"{}")
        requests.append(body)
        if any(isinstance(i.get("output"), list) for i in body["input"] if isinstance(i, dict)):
            return httpx.Response(400, json={"error": {"message": "Invalid type for 'input[0].output': expected a string", "type": "invalid_request_error"}})
        n = len(requests)
        out = [_fc(1, "echo", {"x": "a"})] if n == 1 else [_fc(9, "finish", {})]
        payload = {"id": f"resp_{n}", "object": "response", "created_at": 1, "model": "gpt-6-astra", "status": "completed", "output": out,
                   "parallel_tool_calls": False, "tool_choice": "auto", "tools": [], "error": None, "incomplete_details": None,
                   "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2, "input_tokens_details": {"cached_tokens": 0}}}
        return httpx.Response(200, json=payload)

    client = AsyncOpenAI(api_key="sk-test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), max_retries=0)

    async def echo(args):
        return ToolResult("table", images=[(b"\xff\xd8", "image/jpeg")])

    async def finish(args):
        return ToolResult("done")

    tools = [ToolDef("echo", "e", {"type": "object", "properties": {"x": {"type": "string"}}}, echo), ToolDef("finish", "f", {"type": "object", "properties": {}}, finish)]
    llm = LLM(provider="openai", client=client)
    res = asyncio.run(llm.run_tools(system="s", parts=[{"type": "text", "text": "go"}], tools=tools, model="gpt-6-astra"))
    assert res.stopped_by == "finish" and res.error is None
    # request 2 was rejected (list output); request 3 carries the text output + a user message with the image
    assert len(requests) == 3
    r3 = requests[2]
    assert r3["previous_response_id"] == "resp_1"
    assert r3["input"][0]["type"] == "function_call_output" and r3["input"][0]["output"] == "table"
    assert r3["input"][1]["role"] == "user" and r3["input"][1]["content"][1]["type"] == "input_image"


def test_designer_critic_revise_round(tmp_path, monkeypatch):
    """Critic says 'revise' once: the designer gets a follow-up loop, iterates again, finishes, and the second review passes."""
    import kintsugi.agent.fake as fake
    from kintsugi.agent.designer import run_designer
    from kintsugi.session.workspace import Session
    from kintsugi.spec.model import PartSpec

    verdicts = iter(["revise", "pass"])
    orig = fake.fake_complete

    def scripted(system, parts):
        if "critic" in system[:200].lower():
            v = next(verdicts, "pass")
            return json.dumps({"inspection": {}, "verdict": v, "summary": f"scripted {v}",
                               "discrepancies": [{"where": "loop", "expected": "fillet", "observed": "sharp", "severity": "medium", "suggestion": "add a fillet"}] if v == "revise" else []})
        return orig(system, parts)

    monkeypatch.setattr(fake, "fake_complete", scripted)
    spec = PartSpec.load(SPEC)
    s = Session.create("revise", spec, sessions_dir=tmp_path)
    llm = LLM(provider="fake", client=FakeResponsesClient(default_design_script(), revise_script()))
    out = asyncio.run(run_designer(s, spec=spec, llm=llm, critic_rounds=2))
    assert out.status == "done", out.to_dict()
    evs = [json.loads(line) for line in (s.dir / "events.jsonl").read_text().splitlines()]
    kinds = [e["kind"] for e in evs]
    assert kinds.count("critic") == 2 and "critic_followup" in kinds and kinds.count("iteration") == 2
    assert [e["verdict"] for e in evs if e["kind"] == "critic"] == ["revise", "pass"]
    assert kinds.index("critic_followup") < kinds.index("run_end") and s.meta["critic_rounds"] == 2


def test_ask_user_then_resume_via_api(tmp_path, monkeypatch):
    """The designer asks a question (run pauses as waiting_user); answering through the API resumes and finishes."""
    monkeypatch.setenv("KIN_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("KIN_PROVIDER", "fake")
    from fastapi.testclient import TestClient

    import kintsugi.server.app as appmod
    from kintsugi.agent import llm as llmmod

    ask_script = [[{"call": "read_file", "args": {"path": "spec.yaml"}}],
                  [{"text": "The spec leaves the loop width open."},
                   {"call": "ask_user", "args": {"question": "How wide should the finger loop be?", "options": ["40 mm", "48 mm"]}}]]
    resume_script = [[{"call": "list_templates", "args": {}}], [{"call": "read_template", "args": {"name": "ring_loop_handle"}}],
                     [{"call": "write_file", "args": lambda ctx: {"path": "part.scad", "content": (Path("templates") / "ring_loop_handle.scad").read_text()}}],
                     [{"call": "iterate", "args": {"label": "48 mm loop as the user asked"}}],
                     [{"call": "finish", "args": {"narration": "Loop at 48 mm per your answer."}}]]
    client = FakeResponsesClient(ask_script, resume_script)
    llmmod.set_llm(LLM(provider="fake", client=client))
    appmod.SESSIONS_DIR = (tmp_path / "sessions").resolve()
    appmod.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    with TestClient(appmod.app) as c:
        sid = c.post("/api/sessions", json={"name": "ask", "spec_yaml": SPEC.read_text()}).json()["meta"]["id"]
        assert c.post(f"/api/sessions/{sid}/run", json={"budget": 4, "critic_rounds": 0}).status_code == 202
        for _ in range(60):
            d = c.get(f"/api/sessions/{sid}").json()
            if not d["running"]:
                break
            time.sleep(0.5)
        assert d["meta"]["status"] == "waiting_user" and d["meta"]["question"]["options"] == ["40 mm", "48 mm"]
        assert c.post(f"/api/sessions/{sid}/run", json={"answer": "48 mm", "critic_rounds": 0}).status_code == 202
        for _ in range(120):
            d = c.get(f"/api/sessions/{sid}").json()
            if not d["running"]:
                break
            time.sleep(0.5)
        assert d["meta"]["status"] == "done" and d["meta"]["question"] is None and d["stage"] == "review", d["meta"]
        kinds = [e["kind"] for e in c.get(f"/api/sessions/{sid}/events", params={"once": "true"}).json()["events"]]
        assert kinds.count("run_start") == 2 and "question" in kinds and "answer" in kinds and kinds.count("run_end") == 2
        # the resume prompt carried the answer to the model
        resume_call = [k for k in client.calls if len(k["input"]) == 1 and k["input"][0].get("role") == "user"][1]
        assert "48 mm" in json.dumps(resume_call["input"][0]["content"])
    llmmod.get_llm(reset=True)
