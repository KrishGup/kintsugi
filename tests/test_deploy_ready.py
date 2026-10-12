"""What a deployment relies on: the three auth modes, per-user session scoping, the settings lock, portable session archives
(export → import round trip, zip-slip refusal, schema), the CLI around them, and the data-dir/dotenv plumbing.
None of this needs OpenSCAD or a model key."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kintsugi.session.archive import ArchiveError, export_archive, import_archive, inspect_archive, manifest_schema, part_spec_schema
from kintsugi.session.workspace import Session
from kintsugi.spec.model import PartSpec

SPEC = Path(__file__).parent.parent / "eval" / "specs" / "bottle_handle.yaml"


@pytest.fixture
def api(tmp_path, monkeypatch):
    """A TestClient over a fresh sessions dir; auth mode is whatever the test sets before the first request."""
    monkeypatch.setenv("KIN_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("KIN_PROVIDER", "fake")
    for k in ("KIN_AUTH", "KIN_ACCESS_TOKEN", "KIN_SECRET_KEY", "KIN_ADMIN_USERS", "KIN_SETTINGS_LOCK", "KIN_COOKIE_SECURE"):
        monkeypatch.delenv(k, raising=False)
    import kintsugi.server.app as appmod
    from kintsugi.agent.llm import get_llm

    get_llm(reset=True)
    appmod.SESSIONS_DIR = (tmp_path / "sessions").resolve()
    appmod.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    with TestClient(appmod.app) as c:
        yield c


def _principal(name: str, display: str | None = None, idp: str = "aad") -> dict[str, str]:
    """The headers Azure Easy Auth adds to a signed-in request."""
    doc = {"auth_typ": idp, "name_typ": "name", "role_typ": "roles",
           "claims": [{"typ": "name", "val": display or name}, {"typ": "preferred_username", "val": name}]}
    return {"x-ms-client-principal-name": name, "x-ms-client-principal-id": hashlib.md5(name.encode()).hexdigest(),
            "x-ms-client-principal-idp": idp, "x-ms-client-principal": base64.b64encode(json.dumps(doc).encode()).decode()}


# ---- auth modes ----------------------------------------------------------------------------------------------------

def test_auth_none_is_open(api):
    me = api.get("/api/auth/me").json()
    assert me["mode"] == "none" and me["user"]["id"] == "local" and me["user"]["admin"]
    assert api.get("/api/sessions").status_code == 200
    assert api.get("/api/health").json()["auth"] == "none"


def test_auth_token_mode(api, monkeypatch):
    monkeypatch.setenv("KIN_AUTH", "token")
    monkeypatch.setenv("KIN_ACCESS_TOKEN", "correct-horse-battery")
    # locked out: API 401 with the gate description; health and /auth stay public
    r = api.get("/api/sessions")
    assert r.status_code == 401 and r.json()["auth"]["mode"] == "token" and r.json()["auth"]["login_url"] == "/api/auth/login"
    assert api.get("/api/health").status_code == 200
    assert api.get("/api/auth/me").json()["user"] is None
    # wrong code, right code
    assert api.post("/api/auth/login", json={"token": "nope"}).status_code == 401
    r = api.post("/api/auth/login", json={"token": " correct-horse-battery "})
    assert r.status_code == 200 and "kin_auth" in r.cookies
    cookie = r.cookies["kin_auth"]
    assert "correct-horse-battery" not in cookie and len(cookie) == 64   # a signature, never the code
    assert api.get("/api/sessions").status_code == 200
    assert api.get("/api/auth/me").json()["user"]["id"] == "shared"
    # a bearer header works for scripts; a forged cookie does not
    api.cookies.clear()
    assert api.get("/api/sessions").status_code == 401
    assert api.get("/api/sessions", headers={"Authorization": "Bearer correct-horse-battery"}).status_code == 200
    assert api.get("/api/sessions", cookies={"kin_auth": "0" * 64}).status_code == 401
    # logout clears the cookie
    api.post("/api/auth/login", json={"token": "correct-horse-battery"})
    assert api.get("/api/sessions").status_code == 200
    api.post("/api/auth/logout")
    assert api.get("/api/sessions").status_code == 401
    # the login endpoint is only for token mode
    monkeypatch.setenv("KIN_AUTH", "easyauth")
    assert api.post("/api/auth/login", json={"token": "correct-horse-battery"}).status_code == 400


def test_auth_easyauth_scopes_sessions_per_user(api, monkeypatch):
    monkeypatch.setenv("KIN_AUTH", "easyauth")
    monkeypatch.setenv("KIN_ADMIN_USERS", "Boss@Example.com")
    alice, bob, boss = _principal("alice@example.com", "Alice A"), _principal("bob@example.com"), _principal("boss@example.com")
    # no principal → 401 with the platform's login link
    r = api.get("/api/sessions")
    assert r.status_code == 401 and r.json()["auth"]["login_url"].startswith("/.auth/login/aad")
    me = api.get("/api/auth/me", headers=alice).json()
    assert me["user"] == {"id": "alice@example.com", "name": "Alice A", "provider": "aad", "admin": False}
    assert me["logout_url"].startswith("/.auth/logout")
    # each person's sessions are stamped and only theirs come back
    a = api.post("/api/sessions", json={"name": "alice part", "spec_yaml": SPEC.read_text()}, headers=alice).json()
    b = api.post("/api/sessions", json={"name": "bob part", "spec_yaml": SPEC.read_text()}, headers=bob).json()
    assert a["meta"]["owner"] == "alice@example.com" and a["meta"]["owner_name"] == "Alice A"
    assert [s["id"] for s in api.get("/api/sessions", headers=alice).json()] == [a["meta"]["id"]]
    assert [s["id"] for s in api.get("/api/sessions", headers=bob).json()] == [b["meta"]["id"]]
    assert api.get(f"/api/sessions/{a['meta']['id']}", headers=bob).status_code == 404
    assert api.get(f"/api/sessions/{a['meta']['id']}", headers=alice).status_code == 200
    # admins see everything; the setting is case-insensitive
    assert api.get("/api/auth/me", headers=boss).json()["user"]["admin"]
    assert {s["id"] for s in api.get("/api/sessions", headers=boss).json()} == {a["meta"]["id"], b["meta"]["id"]}
    assert api.get(f"/api/sessions/{a['meta']['id']}", headers=boss).status_code == 200
    # settings: only admins may change them in easyauth mode
    assert api.post("/api/settings", json={"effort": "medium"}, headers=alice).status_code == 403
    assert api.post("/api/settings", json={"effort": "medium"}, headers=boss).status_code == 200
    # GitHub sign-in: the login is the id, no principal document needed
    gh = {"x-ms-client-principal-name": "octocat", "x-ms-client-principal-id": "583231", "x-ms-client-principal-idp": "github"}
    assert api.get("/api/auth/me", headers=gh).json()["user"] == {"id": "octocat", "name": "octocat", "provider": "github", "admin": False}


def test_settings_lock(api, monkeypatch):
    assert api.get("/api/settings").json()["locked"] is False
    monkeypatch.setenv("KIN_SETTINGS_LOCK", "1")
    assert api.get("/api/settings").json()["locked"] is True
    assert api.get("/api/health").json()["settings_locked"] is True
    r = api.post("/api/settings", json={"effort": "low"})
    assert r.status_code == 403 and "managed" in r.json()["detail"].lower()


def test_session_id_validation(api):
    for bad in ("..", "..%2F..%2Fetc", ".hidden", "a b", "x" * 121):
        assert api.get(f"/api/sessions/{bad}").status_code == 404, bad


# ---- archives ------------------------------------------------------------------------------------------------------

def _populate(s: Session) -> None:
    """A session with the kinds of files a real one carries, without running anything."""
    s.scad_path.write_text("// Spec dims: neck_ring.ring_outer_diameter <- ring_d\nring_d = 52; // [40:80]\ncylinder(d=ring_d, h=4);\n")
    (s.dir / "photos").mkdir(exist_ok=True)
    (s.dir / "photos" / "shot_01.jpg").write_bytes(b"\xff\xd8\xff\xe0" + bytes(range(256)) * 40)
    it = s.dir / "iterations" / "iter_01"
    (it / "sheets").mkdir(parents=True)
    (it / "part.scad").write_text("cylinder(d=52, h=4);\n")
    (it / "checks.json").write_text(json.dumps({"ok": True, "checks": []}))
    (it / "sheets" / "iter_01_sheet.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 512)
    (s.dir / "preview").mkdir(exist_ok=True)
    (s.dir / "preview" / "preview.stl").write_bytes(b"solid derived\nendsolid\n")     # derived: must not travel
    (s.dir / "export").mkdir(exist_ok=True)
    (s.dir / "export" / "bundle.zip").write_bytes(b"PK\x05\x06" + b"\x00" * 18)       # heavy: must not travel
    (s.dir / "export" / "print_card.md").write_text("# Print card\n")
    s.update_meta(status="running", iteration=1, owner="alice@example.com", owner_name="Alice")
    s.emit("iteration", n=1)
    s.commit("iteration 1")


def test_archive_round_trip(tmp_path):
    src_dir = tmp_path / "a"
    s = Session.create("bottle handle", PartSpec.load(SPEC), sessions_dir=src_dir)
    _populate(s)
    zpath = export_archive(s, tmp_path / "out.zip")
    with zipfile.ZipFile(zpath) as z:
        names = set(z.namelist())
        manifest = json.loads(z.read("manifest.json"))
    assert {"manifest.json", "session.json", "spec.yaml", "part.scad", "events.jsonl", "photos/shot_01.jpg",
            "iterations/iter_01/sheets/iter_01_sheet.png", "export/print_card.md"} <= names
    assert not any(n.startswith((".git/", "preview/")) for n in names) and "export/bundle.zip" not in names
    assert manifest["kind"] == "kintsugi-session" and manifest["schema_version"] == 1
    assert "owner" not in manifest["session"] and manifest["session"]["name"] == "bottle handle"
    listed = {f["path"]: f for f in manifest["files"]}
    assert set(listed) == names - {"manifest.json"}
    assert listed["photos/shot_01.jpg"]["sha256"] == hashlib.sha256((s.dir / "photos" / "shot_01.jpg").read_bytes()).hexdigest()
    assert manifest["total_bytes"] == sum(f["bytes"] for f in manifest["files"])
    # the manifest obeys its published schema
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(manifest, manifest_schema())
    assert jsonschema.Draft202012Validator.check_schema(part_spec_schema()) is None

    # import into another server: the original id is kept when free, every file matches, derived state is reset
    dst_dir = tmp_path / "b"
    s2 = import_archive(zpath.read_bytes(), dst_dir, owner={"owner": "bob@example.com", "owner_name": "Bob"})
    assert s2.id == s.id and s2.dir.parent == dst_dir.resolve()
    for rel, info in listed.items():
        if rel in ("session.json", "events.jsonl"):
            continue      # rewritten on import (new meta) / appended to (the `imported` event)
        assert hashlib.sha256((s2.dir / rel).read_bytes()).hexdigest() == info["sha256"], rel
    assert (s2.dir / "events.jsonl").read_bytes().startswith((s.dir / "events.jsonl").read_bytes())
    assert not (s2.dir / "preview" / "preview.stl").exists() and not (s2.dir / "export" / "bundle.zip").exists()
    m = s2.meta
    assert m["status"] == "stopped" and m["iteration"] == 1 and m["owner"] == "bob@example.com"
    assert m["imported_from"]["id"] == s.id and m["imported_at"] > 0
    assert s2.events()[-1]["kind"] == "imported"
    assert (s2.dir / ".git").exists() and s2.history()          # a fresh git history, first commit present
    # a second import of the same archive gets a fresh id (the original is taken)
    s3 = import_archive(zpath.read_bytes(), dst_dir)
    assert s3.id != s.id and (dst_dir / s3.id / "spec.yaml").exists()
    s4 = import_archive(zpath.read_bytes(), tmp_path / "c", keep_id=False)
    assert s4.id != s.id


def test_archive_refuses_bad_zips(tmp_path):
    def zipped(entries: dict[str, bytes]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for k, v in entries.items():
                z.writestr(k, v)
        return buf.getvalue()

    good_manifest = json.dumps({"kind": "kintsugi-session", "schema_version": 1, "session": {"id": "x"}, "files": []})
    meta = json.dumps({"id": "x", "name": "x", "created": 1})
    with pytest.raises(ArchiveError, match="manifest"):
        inspect_archive(zipped({"session.json": meta}))
    with pytest.raises(ArchiveError, match="session.json"):
        inspect_archive(zipped({"manifest.json": good_manifest}))
    with pytest.raises(ArchiveError, match="not a kintsugi-session"):
        inspect_archive(zipped({"manifest.json": json.dumps({"kind": "other"}), "session.json": meta}))
    with pytest.raises(ArchiveError, match="schema version 9"):
        inspect_archive(zipped({"manifest.json": json.dumps({"kind": "kintsugi-session", "schema_version": 9}), "session.json": meta}))
    for evil in ("../evil.txt", "/etc/passwd", "C:\\boot.ini", "photos/../../x", "..\\evil.txt", "photos/./x"):
        with pytest.raises(ArchiveError, match="unsafe path"):
            inspect_archive(zipped({"manifest.json": good_manifest, "session.json": meta, evil: b"x"}))
    # the size guard counts the expanded size, not the zip
    with pytest.raises(ArchiveError, match="above the"):
        import_archive(zipped({"manifest.json": good_manifest, "session.json": meta, "big.bin": b"\x00" * (2 << 20)}), tmp_path, max_bytes=1 << 20)
    assert not list(tmp_path.glob(".import-*"))       # no temp dirs left behind


def test_archive_api_round_trip(api, monkeypatch):
    import kintsugi.server.app as appmod

    monkeypatch.setenv("KIN_AUTH", "easyauth")
    alice, bob = _principal("alice@example.com"), _principal("bob@example.com")
    d = api.post("/api/sessions", json={"name": "api part", "spec_yaml": SPEC.read_text()}, headers=alice).json()
    sid = d["meta"]["id"]
    _populate(Session.open(appmod.SESSIONS_DIR / sid))
    Session.open(appmod.SESSIONS_DIR / sid).update_meta(status="done")
    # download: only the owner (or an admin) can
    assert api.get(f"/api/sessions/{sid}/archive", headers=bob).status_code == 404
    r = api.get(f"/api/sessions/{sid}/archive", headers=alice)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert f"kintsugi-session-{sid}.zip" in r.headers["content-disposition"]
    blob = r.content
    manifest = inspect_archive(blob)
    assert manifest["session"]["id"] == sid and "owner" not in manifest["session"]
    # the temp file behind the download is gone
    assert not [p for p in Path(__import__("tempfile").gettempdir()).glob(f"kintsugi-session-{sid}-*.zip")]
    # bob imports alice's archive: it becomes his, under a fresh id because the original still exists here
    r = api.post("/api/sessions/import", files={"file": ("x.zip", blob, "application/zip")}, headers=bob)
    assert r.status_code == 201, r.text
    imp = r.json()
    assert imp["meta"]["id"] != sid and imp["meta"]["owner"] == "bob@example.com" and imp["meta"]["imported_from"]["id"] == sid
    assert imp["meta"]["status"] == "done" and imp["scad"].startswith("// Spec dims")
    assert api.get(f"/api/sessions/{imp['meta']['id']}", headers=alice).status_code == 404
    assert [s["id"] for s in api.get("/api/sessions", headers=bob).json()] == [imp["meta"]["id"]]
    # garbage in
    r = api.post("/api/sessions/import", files={"file": ("x.zip", b"not a zip", "application/zip")}, headers=bob)
    assert r.status_code == 422
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps({"kind": "kintsugi-session", "schema_version": 1, "session": {}}))
        z.writestr("session.json", "{}")
        z.writestr("../../escape.txt", "x")
    r = api.post("/api/sessions/import", files={"file": ("x.zip", buf.getvalue(), "application/zip")}, headers=bob)
    assert r.status_code == 422 and "unsafe path" in r.json()["detail"]
    # too big
    monkeypatch.setattr(appmod, "MAX_IMPORT_MB", 0)
    r = api.post("/api/sessions/import", files={"file": ("x.zip", blob, "application/zip")}, headers=bob)
    assert r.status_code == 413
    # the schemas are served
    assert api.get("/api/schemas/session-archive").json()["title"].startswith("Kintsugi session archive")
    assert "interfaces" in api.get("/api/schemas/part-spec.schema.json").json()["properties"]
    assert api.get("/api/schemas/nope").status_code == 404


def test_archive_blocked_while_running(api, monkeypatch):
    import asyncio

    import kintsugi.server.app as appmod

    d = api.post("/api/sessions", json={"name": "busy", "spec_yaml": SPEC.read_text()}).json()
    sid = d["meta"]["id"]

    async def forever():
        await asyncio.sleep(3600)

    loop = asyncio.new_event_loop()
    task = loop.create_task(forever())
    monkeypatch.setitem(appmod.RUNS, sid, task)
    try:
        assert api.get(f"/api/sessions/{sid}/archive").status_code == 409
    finally:
        task.cancel()
        loop.close()


# ---- the CLI and the plumbing --------------------------------------------------------------------------------------

def _bare_env() -> dict[str, str]:
    """A child environment without the developer's KIN_* settings. Windows needs SYSTEMROOT as well as PATH: without
    it the child cannot initialise Winsock and `import asyncio` fails (WinError 10106)."""
    import os
    return {k: os.environ[k] for k in ("PATH", "SYSTEMROOT") if k in os.environ}


def test_cli_archive_import_schema(tmp_path):
    s = Session.create("cli part", PartSpec.load(SPEC), sessions_dir=tmp_path / "s")
    _populate(s)
    env = {**_bare_env(), "KIN_SESSIONS_DIR": str(tmp_path / "s2")}
    out = subprocess.run([sys.executable, "-m", "kintsugi.cli", "archive", str(s.dir), "-o", str(tmp_path / "a.zip")], capture_output=True, text=True, env=env)
    assert out.returncode == 0 and (tmp_path / "a.zip").exists(), out.stderr
    out = subprocess.run([sys.executable, "-m", "kintsugi.cli", "import", str(tmp_path / "a.zip")], capture_output=True, text=True, env=env)
    assert out.returncode == 0, out.stderr
    new_dir = Path(out.stdout.strip())
    assert new_dir.parent == (tmp_path / "s2").resolve() and (new_dir / "spec.yaml").exists()
    out = subprocess.run([sys.executable, "-m", "kintsugi.cli", "import", str(tmp_path / "a.zip"), "--new-id"], capture_output=True, text=True, env=env)
    assert out.returncode == 0 and Path(out.stdout.strip()).name != s.id
    out = subprocess.run([sys.executable, "-m", "kintsugi.cli", "import", str(SPEC)], capture_output=True, text=True, env=env)
    assert out.returncode == 2 and "cannot import" in out.stderr
    out = subprocess.run([sys.executable, "-m", "kintsugi.cli", "schema", "session-archive"], capture_output=True, text=True, env=env)
    assert out.returncode == 0 and json.loads(out.stdout)["properties"]["kind"]["const"] == "kintsugi-session"
    # the committed copies in docs/schemas are current
    docs = Path(__file__).parent.parent / "docs" / "schemas"
    assert json.loads((docs / "session-archive.schema.json").read_text()) == manifest_schema()
    assert json.loads((docs / "part-spec.schema.json").read_text()) == part_spec_schema()


def test_data_dir_and_env_file(tmp_path, monkeypatch):
    """KIN_DATA_DIR decides where sessions and the settings file live; the settings file is loaded on start."""
    env_file = tmp_path / "data" / ".env"
    env_file.parent.mkdir()
    env_file.write_text("KIN_TEST_MARKER=from-data-dir\nOPENAI_API_KEY=sk-should-not-override\n# comment\nexport KIN_TEST_EXPORTED=yes\n")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real")
    monkeypatch.delenv("KIN_TEST_MARKER", raising=False)
    monkeypatch.delenv("KIN_TEST_EXPORTED", raising=False)
    from kintsugi import load_dotenv
    loaded = load_dotenv(paths=(env_file,))
    import os
    assert "KIN_TEST_MARKER" in loaded and os.environ["KIN_TEST_MARKER"] == "from-data-dir"
    assert os.environ["OPENAI_API_KEY"] == "sk-real"            # the process environment wins over the file
    assert os.environ.get("KIN_TEST_EXPORTED") == "yes"
    code = ("import os, sys\n"
            "os.environ['KIN_DATA_DIR'] = sys.argv[1]\n"
            "import kintsugi, kintsugi.session.workspace as w\n"
            "print(kintsugi.DATA_DIR); print(kintsugi.ENV_FILE); print(w.DEFAULT_SESSIONS_DIR)")
    out = subprocess.run([sys.executable, "-c", code, str(tmp_path / "data")], capture_output=True, text=True,
                         env=_bare_env())
    lines = out.stdout.strip().splitlines()
    assert lines == [str((tmp_path / "data").resolve()), str((tmp_path / "data" / ".env").resolve()), str((tmp_path / "data" / "sessions").resolve())], out.stderr


def test_session_without_git(tmp_path, monkeypatch):
    """KIN_SESSION_GIT=0 (slow network shares): sessions still work, history is just empty."""
    monkeypatch.setenv("KIN_SESSION_GIT", "0")
    s = Session.create("nogit", PartSpec.load(SPEC), sessions_dir=tmp_path)
    assert not (s.dir / ".git").exists()
    s.scad_path.write_text("cube(1);\n")
    assert s.commit("edit") is None and s.history() == []
    z = export_archive(s, tmp_path / "z.zip")
    s2 = import_archive(z.read_bytes(), tmp_path / "in")
    assert not (s2.dir / ".git").exists() and s2.scad_path.read_text() == "cube(1);\n"
