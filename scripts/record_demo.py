"""Record the Kintsugi demo video: narration from OpenAI text-to-speech, picture from Playwright driving the real app,
assembled with ffmpeg. Every on-screen result comes from a real session; the narration of the result beats is written
from that session's own numbers (iterations, checks, critic, cost), never typed in.

    python scripts/record_demo.py voice      --base URL --session SID   # narration per beat -> scratch/demo/voice/<id>.mp3
    python scripts/record_demo.py record     --base URL --session SID   # one clip per beat  -> scratch/demo/clips/<id>.webm
    python scripts/record_demo.py assemble                               # -> scratch/demo/kintsugi-demo.mp4 (+ -upload.mp4, < 10 MB)
    python scripts/record_demo.py all        --base URL --session SID

The private instance needs its access code: --code-file (default scratch/tmp/live-access-code.txt). Needs the `tools`
extra (playwright) and imageio-ffmpeg; the narration uses OPENAI_API_KEY from .env (a three-minute script costs cents).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratch" / "demo"
W, H = 1600, 900
FONTS = (ROOT / "docs" / "brand" / "fonts").as_uri()
MARK = (ROOT / "docs" / "brand" / "png" / "mark-512.png").as_uri()
VOICE_MODEL, VOICE = "gpt-4o-mini-tts", "ash"
VOICE_STYLE = "Calm, clear and confident, like a maker explaining a project to a friend. Unhurried, warm, no hype."


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def duration(path: Path) -> float:
    err = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def openai_key() -> str:
    env = (ROOT / ".env").read_text(encoding="utf-8")
    return re.search(r"(?m)^OPENAI_API_KEY=(.+)$", env).group(1).strip()


# ---- the session the result beats describe --------------------------------------------------------------------------

class Site:
    def __init__(self, base: str, code_file: str | None):
        import http.cookiejar
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.code = Path(code_file).read_text().strip() if code_file and Path(code_file).exists() else ""
        if self.code:
            self.api("POST", "/api/auth/login", {"token": self.code})

    def api(self, method: str, path: str, body=None):
        req = urllib.request.Request(self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        with self.op.open(req, timeout=180) as r:
            return json.loads(r.read() or b"null")


def facts(site: Site, sid: str) -> dict:
    d = site.api("GET", f"/api/sessions/{sid}")
    meta = d["meta"]
    iters = d.get("iterations") or []
    checks = d.get("checks") or {}
    items = [i for i in (checks.get("items") or []) if i.get("passed") is not None]
    critic = d.get("critic") or []
    return {"iterations": len(iters), "final_ok": bool(checks.get("all_hard_pass")) and bool(iters and iters[-1].get("ok")),
            "first_failed": bool(iters and not iters[0].get("ok")), "first_compiled": bool(iters and iters[0].get("compile_ok")),
            "verdict": (critic[-1].get("verdict") if critic else None) or "none", "cost": meta.get("cost_usd"), "status": meta.get("status"),
            "model": (d.get("llm") or {}).get("models", {}).get("designer", "gpt-6-astra"),
            "checks_total": len(items), "checks_passed": sum(1 for i in items if i.get("passed"))}


def money(v) -> str:
    return "under a cent" if not v else f"${v:.2f}"


def spoken(model: str) -> str:
    """gpt-6-astra -> GPT-6 Astra, so the voice says a name rather than spelling a slug."""
    m = re.match(r"gpt-(\d+(?:\.\d+)?)-(\w+)", model)
    return f"GPT-{m.group(1)} {m.group(2).capitalize()}" if m else model


def beats(f: dict) -> list[dict]:
    first = (" Its first attempt did not even compile; it read the error and fixed the geometry." if f.get("first_failed") and not f.get("first_compiled")
             else " Its first attempt failed a check; it read the table and fixed it." if f.get("first_failed") else "")
    loop = (f"This real run took {f['iterations']} iteration{'s' if f['iterations'] != 1 else ''}.{first}"
            + (f" The last one passes all {f['checks_passed']} measured checks." if f["final_ok"] else " The last iteration still fails a check, and the guide says which one."))
    critic = {"pass": "The critic agreed.", "revise": "The critic asked for a revision, and the designer answered it."}.get(f["verdict"], "")
    return [
        {"id": "01-title", "card": "title",
         "say": "This is Kintsugi: an agent that turns phone photos of a broken part into a verified, printable replacement."},
        {"id": "02-problem", "card": "problem",
         "say": "Things break at the one part that mattered: a handle, a clip, a knob. 3D printing should fix it, but someone has "
                "to measure the mating geometry and model a part that actually fits. Ask a language model for the CAD code, and you "
                "get a plausible shape that is off where it matters, because the model never sees what it built."},
        {"id": "03-home", "page": "home",
         "say": "You start with two or three photos on a printed calibration sheet and one sentence about what broke. Kintsugi works "
                "out which features the part must mate with, and asks for the exact photos and ruler readings it still needs."},
        {"id": "04-spec", "page": "spec",
         "say": "For this run I start from a typed spec instead: the carry handle of a water bottle. The neck diameter, the ring "
                "height and the size limits are the contract the part has to meet."},
        {"id": "05-run", "page": "timeline",
         "say": f"Then {spoken(f['model'])} takes over, through the OpenAI Responses API. It reads the OpenSCAD guides, writes the part, and "
                f"compiles it. Every dimension in the spec is then measured on the exported mesh, never trusted from the code. {loop}"},
        {"id": "06-sheets", "page": "sheets",
         "say": "Before each change the model looks at engineering drawings rendered from that mesh. The measurements are drawn as "
                "dimension lines, green or red against the tolerance, so it sees exactly what it got wrong."},
        {"id": "07-checks", "page": "checks",
         "say": f"Pointing at a check shows the section it was measured on. A second model reviews the drawings and the check table "
                f"without ever seeing the code. {critic} The whole run cost {money(f['cost'])}."},
        {"id": "08-customize", "page": "customize",
         "say": "The finished part is not a file but a parametric designer. Every dimension is a slider with a live 3D draft, and "
                "every fit dimension shows where its number came from and the tolerance it must stay inside."},
        {"id": "09-export", "page": "export",
         "say": "Before the full part, a fit coupon tests the mating feature at three clearances in a few minutes of printing. Then "
                "you get the STL, a 3MF, the blueprints and a print card that explains the settings."},
        {"id": "10-close", "card": "close",
         "say": "Off grid, the repair is the supply chain. Kintsugi: photograph what broke, print what fits. The demo and the code "
                "are linked below."},
    ]


# ---- narration -------------------------------------------------------------------------------------------------------

def voice(bs: list[dict]) -> None:
    import httpx
    d = OUT / "voice"
    d.mkdir(parents=True, exist_ok=True)
    key = openai_key()
    for b in bs:
        h = hashlib.sha1((VOICE + VOICE_STYLE + b["say"]).encode()).hexdigest()[:10]
        path = d / f"{b['id']}.mp3"
        stamp = d / f"{b['id']}.hash"
        if path.exists() and stamp.exists() and stamp.read_text() == h:
            continue
        r = httpx.post("https://api.openai.com/v1/audio/speech", headers={"Authorization": f"Bearer {key}"}, timeout=120,
                       json={"model": VOICE_MODEL, "voice": VOICE, "input": b["say"], "instructions": VOICE_STYLE, "response_format": "mp3"})
        r.raise_for_status()
        path.write_bytes(r.content)
        stamp.write_text(h)
        print(f"voice {b['id']}: {duration(path):.1f}s")


def voice_len(b: dict) -> float:
    return duration(OUT / "voice" / f"{b['id']}.mp3")


# ---- picture ---------------------------------------------------------------------------------------------------------

CARD_CSS = f"""
@font-face {{ font-family: Barlow; font-weight: 700; src: url({FONTS}/barlow-semi-condensed-latin-700-normal.woff2); }}
@font-face {{ font-family: Plex; font-weight: 400; src: url({FONTS}/ibm-plex-sans-latin-400-normal.woff2); }}
@font-face {{ font-family: PlexMono; font-weight: 400; src: url({FONTS}/ibm-plex-mono-latin-400-normal.woff2); }}
html, body {{ margin: 0; width: {W}px; height: {H}px; background: #05142e; color: #f3f7fe; font-family: Plex, sans-serif; }}
body {{ display: flex; flex-direction: column; justify-content: center; padding: 0 120px; box-sizing: border-box; gap: 34px;
  background-image: linear-gradient(rgba(190,212,249,.06) 1px, transparent 1px), linear-gradient(90deg, rgba(190,212,249,.06) 1px, transparent 1px);
  background-size: 40px 40px; }}
.brand {{ display: flex; align-items: center; gap: 22px; font-family: Barlow; font-size: 40px; letter-spacing: 6px; }}
.brand img {{ width: 88px; height: 88px; }}
h1 {{ font-family: Barlow; font-size: 96px; line-height: 1.02; margin: 0; max-width: 1300px; }}
p {{ font-size: 34px; line-height: 1.4; color: #bed4f9; margin: 0; max-width: 1250px; }}
.dim {{ display: flex; align-items: center; gap: 16px; color: #6c9ef0; font-family: PlexMono; font-size: 26px; max-width: 1250px; }}
.dim i {{ flex: 1; height: 2px; background: #6c9ef0; }} .dim b {{ width: 2px; height: 30px; background: #6c9ef0; }}
.links {{ font-family: PlexMono; font-size: 28px; color: #f3f7fe; line-height: 1.7; }}
"""

CARDS = {
    "title": """<div class="brand"><img src="{mark}">KINTSUGI</div><h1>Photograph what broke. Print what fits.</h1>
<p>An agent that turns phone photos of a broken part into a verified, printable replacement.</p>
<div class="dim"><b></b><i></i>photo → spec → OpenSCAD → measured mesh → print<i></i><b></b></div>""",
    "problem": """<div class="dim">THE PROBLEM</div><h1>It breaks at the one part that mattered.</h1>
<p>Language-model CAD looks right and misses the one dimension that has to fit, because the model never sees what it built.</p>""",
    "close": """<div class="brand"><img src="{mark}">KINTSUGI</div><h1>Off grid, the repair is the supply chain.</h1>
<div class="links">demo&nbsp;&nbsp; kintsugi.orangecliff-df186167.eastus2.azurecontainerapps.io<br>code&nbsp;&nbsp; github.com/KrishGup/kintsugi</div>
<p>Built for HACK47: OFFGRID on the OpenAI Responses API.</p>""",
}

OVERLAY_JS = """
(text) => {
  const old = document.getElementById('__cap'); if (old) old.remove();
  const c = document.createElement('div'); c.id = '__cap'; c.textContent = text;
  Object.assign(c.style, { position: 'fixed', left: '50%', bottom: '22px', transform: 'translateX(-50%)', maxWidth: '1360px',
    background: 'rgba(5,20,46,.86)', color: '#f3f7fe', font: '500 22px/1.4 "IBM Plex Sans", system-ui, sans-serif', padding: '12px 22px',
    borderRadius: '8px', zIndex: '2147483646', textAlign: 'center', boxShadow: '0 8px 24px rgba(5,20,46,.3)', pointerEvents: 'none' });
  document.body.appendChild(c);
  if (!document.getElementById('__cursor')) {
    const k = document.createElement('div'); k.id = '__cursor';
    Object.assign(k.style, { position: 'fixed', left: '-100px', top: '-100px', width: '26px', height: '26px', borderRadius: '50%',
      background: 'rgba(21,93,211,.25)', border: '2.5px solid #155dd3', pointerEvents: 'none', zIndex: '2147483647',
      transform: 'translate(-50%,-50%)', transition: 'transform .09s ease' });
    document.body.appendChild(k);
    window.addEventListener('mousemove', e => { k.style.left = e.clientX + 'px'; k.style.top = e.clientY + 'px'; }, true);
    window.addEventListener('mousedown', () => k.style.transform = 'translate(-50%,-50%) scale(.65)', true);
    window.addEventListener('mouseup', () => k.style.transform = 'translate(-50%,-50%) scale(1)', true);
  }
}
"""


async def glide(pg, locator, click=False, steps=18):
    """Move the visible cursor to an element (and click it); an element that is not on screen is skipped, not waited for."""
    try:
        if not await locator.count():
            return
        box = await locator.bounding_box(timeout=3000)
    except Exception:
        return
    if not box:
        return
    await pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=steps)
    await pg.wait_for_timeout(250)
    if click:
        await locator.click()


async def act(pg, kind: str, base: str, sid: str) -> None:
    async def tab(name):  # a tab in any pane, by its visible name
        t = pg.get_by_role("tab", name=re.compile(rf"^{name}", re.I)).first
        await glide(pg, t, click=True)
        await pg.wait_for_timeout(700)

    if kind == "home":
        await pg.wait_for_timeout(1200)
        await glide(pg, pg.get_by_role("tab", name=re.compile("photograph what broke", re.I)).first)
        await pg.wait_for_timeout(900)
        await glide(pg, pg.locator(".file-drop-main").first)
        await pg.wait_for_timeout(1200)
        await glide(pg, pg.get_by_role("button", name=re.compile("calibration sheet", re.I)).first)
    elif kind == "spec":
        await tab("from a spec")
        await pg.wait_for_timeout(800)
        await glide(pg, pg.locator("select.select").first)
        await pg.wait_for_timeout(1500)
        await glide(pg, pg.locator("textarea").first)
    elif kind == "timeline":
        await tab("timeline")
        await pg.mouse.move(W * 0.15, H * 0.5, steps=12)
        await pg.wait_for_timeout(2500)
        for _ in range(26):
            await pg.mouse.wheel(0, -150)
            await pg.wait_for_timeout(900)
    elif kind == "sheets":
        await tab("views")
        await pg.wait_for_timeout(2500)
        await tab("sections")
        await pg.wait_for_timeout(2500)
    elif kind == "checks":
        await tab("checks")
        rows = pg.locator(".table-checks tbody tr")
        n = await rows.count()
        for i in range(min(n, 4)):
            await glide(pg, rows.nth(i))
            await pg.wait_for_timeout(900)
        await tab("guide")
    elif kind == "customize":
        await tab("customize")
        await pg.wait_for_timeout(1200)
        thumb = pg.locator(".slider-thumb").nth(4)
        box = await thumb.bounding_box()
        if box:
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            await pg.mouse.move(x, y, steps=14)
            await pg.mouse.down()
            await pg.mouse.move(x + 70, y, steps=24)
            await pg.mouse.up()
            await pg.wait_for_timeout(3500)
    elif kind == "export":
        btn = pg.get_by_role("button", name=re.compile("^export", re.I)).first
        await glide(pg, btn, click=True)
        await pg.wait_for_timeout(1200)
        go = pg.get_by_role("button", name=re.compile("export last passing|re-export", re.I)).first
        if await go.count():
            await glide(pg, go, click=True)
            await pg.wait_for_timeout(6000)
        await pg.keyboard.press("Escape")
        await pg.wait_for_timeout(800)
        await glide(pg, pg.get_by_role("button", name=re.compile("^coupon", re.I)).first, click=True)
        await pg.wait_for_timeout(2500)


async def record(base: str, sid: str, code: str, bs: list[dict], only: set[str] | None = None) -> None:
    from playwright.async_api import async_playwright
    cdir, tmp = OUT / "clips", OUT / "clips-raw"
    cdir.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
        for beat in bs:
            if only and not any(beat["id"].startswith(o) for o in only):
                continue
            if "card" in beat:
                ctx = await b.new_context(viewport={"width": W, "height": H})
                pg = await ctx.new_page()
                html = cdir / f"{beat['id']}.html"
                html.write_text(f"<!doctype html><meta charset=utf-8><style>{CARD_CSS}</style>" + CARDS[beat["card"]].replace("{mark}", MARK), encoding="utf-8")
                await pg.goto(html.as_uri(), wait_until="load")
                await pg.evaluate("document.fonts.ready")
                await pg.wait_for_timeout(600)
                await pg.screenshot(path=str(cdir / f"{beat['id']}.png"))
                await ctx.close()
                print("card", beat["id"])
                continue
            ctx = await b.new_context(viewport={"width": W, "height": H}, record_video_dir=str(tmp), record_video_size={"width": W, "height": H})
            if code:
                await ctx.request.post(base + "/api/auth/login", data={"token": code})
            pg = await ctx.new_page()
            t_open = time.time()
            url = base + ("/#/" if beat["page"] in ("home", "spec") else f"/#/s/{sid}")
            await pg.goto(url, wait_until="load")
            await pg.wait_for_selector(".home, .topbar", timeout=60000)
            if beat["page"] not in ("home", "spec"):
                await pg.get_by_role("tab", name=re.compile("^guide", re.I)).first.click()
            await pg.wait_for_timeout(1500)
            await pg.evaluate(OVERLAY_JS, beat["say"])
            t_ready = time.time()
            need = voice_len(beat) + 0.8
            await act(pg, beat["page"], base, sid)
            left = need - (time.time() - t_ready)
            if left > 0:
                await pg.wait_for_timeout(int(left * 1000))
            raw = await pg.video.path()
            await ctx.close()
            dst = cdir / f"{beat['id']}.webm"
            if dst.exists():
                dst.unlink()
            Path(raw).rename(dst)
            (cdir / f"{beat['id']}.trim").write_text(f"{t_ready - t_open:.2f}")
            print(f"clip {beat['id']}: lead {t_ready - t_open:.1f}s, voice {need:.1f}s")
        await b.close()


# ---- assembly --------------------------------------------------------------------------------------------------------

def assemble(bs: list[dict]) -> None:
    ff = ffmpeg()
    seg = OUT / "segments"
    seg.mkdir(parents=True, exist_ok=True)
    parts = []
    for beat in bs:
        v = OUT / "voice" / f"{beat['id']}.mp3"
        dur = voice_len(beat) + 0.8
        out = seg / f"{beat['id']}.mp4"
        if "card" in beat:
            vin = ["-loop", "1", "-t", f"{dur:.2f}", "-i", str(OUT / "clips" / f"{beat['id']}.png")]
        else:
            lead = float((OUT / "clips" / f"{beat['id']}.trim").read_text())
            vin = ["-ss", f"{lead:.2f}", "-t", f"{dur:.2f}", "-i", str(OUT / "clips" / f"{beat['id']}.webm")]
        fade_out = max(dur - 0.35, 0)
        subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", *vin, "-i", str(v),
                        "-filter_complex", f"[0:v]fps=30,scale={W}:{H},format=yuv420p,fade=t=in:st=0:d=0.3,fade=t=out:st={fade_out:.2f}:d=0.35[v];"
                                           f"[1:a]adelay=300|300,apad,atrim=0:{dur:.2f},aresample=48000[a]",
                        "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                        "-c:a", "aac", "-b:a", "160k", "-ac", "2", str(out)], check=True)
        parts.append(out)
    lst = seg / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
    master = OUT / "kintsugi-demo.mp4"
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(master)], check=True)
    total = duration(master)
    # an upload copy under 10 MB (the browser upload tool's limit): 720p, two-pass at the bitrate that fits
    kbps = int((9.4 * 8 * 1024) / total - 64)
    small = OUT / "kintsugi-demo-upload.mp4"
    common = ["-vf", "scale=1280:720:flags=lanczos", "-c:v", "libx264", "-preset", "slow", "-b:v", f"{kbps}k", "-r", "30"]
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", str(master), *common, "-pass", "1", "-passlogfile", str(seg / "x264"), "-an", "-f", "mp4", os.devnull], check=True)
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", str(master), *common, "-pass", "2", "-passlogfile", str(seg / "x264"),
                    "-c:a", "aac", "-b:a", "64k", "-ac", "1", str(small)], check=True)
    print(f"master {master} {total:.1f}s {master.stat().st_size / 1e6:.1f} MB; upload copy {small.stat().st_size / 1e6:.2f} MB at {kbps} kbps")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["voice", "record", "assemble", "all", "script"])
    ap.add_argument("--base", default="https://kintsugi-live.orangecliff-df186167.eastus2.azurecontainerapps.io")
    ap.add_argument("--session", default="")
    ap.add_argument("--code-file", default=str(ROOT / "scratch" / "tmp" / "live-access-code.txt"))
    ap.add_argument("--only", default="", help="comma-separated beat id prefixes to re-record, e.g. 01,02,05")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    fpath = OUT / "facts.json"
    if a.step in ("voice", "record", "all", "script"):
        site = Site(a.base, a.code_file)
        f = facts(site, a.session)
        fpath.write_text(json.dumps(f, indent=1))
    f = json.loads(fpath.read_text())
    bs = beats(f)
    if a.step == "script":
        print(json.dumps(f, indent=1))
        for b in bs:
            print(f"[{b['id']}] {b['say']}\n")
        return 0
    if a.step in ("voice", "all"):
        voice(bs)
    if a.step in ("record", "all"):
        import asyncio
        code = Path(a.code_file).read_text().strip() if Path(a.code_file).exists() else ""
        asyncio.run(record(a.base, a.session, code, bs, {o.strip() for o in a.only.split(",") if o.strip()} or None))
    if a.step in ("assemble", "all"):
        assemble(bs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
