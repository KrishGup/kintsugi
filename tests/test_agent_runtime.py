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
