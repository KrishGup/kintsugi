"""Record the Kintsugi demo video: Krish's voice-over (or OpenAI text-to-speech as a stand-in), picture from Playwright
driving the real app and a few drafting-sheet cards, captions burned in from the transcript, assembled with ffmpeg.
Every on-screen result comes from a real session (the first real GPT-6 run); the script's numbers were read off that
session (`facts`, printed by the `script` step) and the script step warns if the session disagrees with them.

    python scripts/record_demo.py voice  --take take.m4a --session SID   # one recorded take -> scratch/demo/voice/<id>.mp3 + captions
    python scripts/record_demo.py record --session SID                   # one clip or card per shot -> scratch/demo/clips/
    python scripts/record_demo.py assemble                               # -> scratch/demo/kintsugi-demo.mp4 (+ -upload.mp4, < 10 MB)
    python scripts/record_demo.py script --take take.m4a --session SID   # the facts, and how the take was cut (no rendering)

The take is one file with every section in order; a line or a section said again replaces the earlier take, and a
section heading read aloud is dropped. Without --take the voice step speaks the script with text-to-speech.
The private instance needs its access code: --code-file (default scratch/tmp/live-access-code.txt). Needs the `tools`
extra (playwright) and imageio-ffmpeg; transcription and text-to-speech use OPENAI_API_KEY from .env (cents).
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratch" / "demo"
W, H = 1600, 900
LEAD, TAIL = 0.3, 0.6  # seconds of picture before and after each section's voice
FONTS = (ROOT / "docs" / "brand" / "fonts").as_uri()
MARK = (ROOT / "docs" / "brand" / "png" / "mark-512.png").as_uri()
VOICE_MODEL, VOICE = "gpt-4o-mini-tts", "ash"
VOICE_STYLE = "Calm, clear and confident, like a maker explaining a project to a friend. Unhurried, warm, no hype."


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ff(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", *args], check=True, cwd=cwd,
                          capture_output=True, text=True).stderr


def duration(path: Path) -> float:
    err = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def openai_key() -> str:
    env = (ROOT / ".env").read_text(encoding="utf-8")
    return re.search(r"(?m)^OPENAI_API_KEY=(.+)$", env).group(1).strip()


def words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower().replace("-", ""))


def contained(part: list[str], whole: list[str]) -> float:
    """How much of `part` appears, in order, in `whole` (1.0 = all of it)."""
    if not part:
        return 0.0
    sm = difflib.SequenceMatcher(None, part, whole, autojunk=False)
    return sum(b.size for b in sm.get_matching_blocks()) / len(part)


# ---- the session the result sections describe -----------------------------------------------------------------------

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


# what the script says about the run; `script` warns when the session's own numbers disagree
SCRIPT_CLAIMS = {"iterations": 2, "first_compiled": False, "final_ok": True, "checks_passed": 15, "verdict": "pass"}


# ---- the script: twelve sections, each a run of shots (a card or a live page, cut in at a spoken line) ---------------

def beats(f: dict) -> list[dict]:
    def card(name, at=None):
        return {"card": name, "at": at}

    def page(kind, at=None):
        return {"page": kind, "at": at}

    return [
        {"id": "01-opener", "shots": [card("title"), page("overview", "So I built Kintsugi")],
         "say": "Hi, I'm Krish, and this is my hackathon project, Kintsugi. Kintsugi is the Japanese art of taking something that's "
                "broken and making it whole again. In today's world, we're too quick to throw things into landfills that could easily "
                "be repaired. For this hackathon, that's the exact problem I wanted to solve. So I built Kintsugi, a web app built on "
                "top of OpenSCAD. It uses a node-based graph workflow to turn a few photos, or a simple spec, into a 3D-printable repair."},
        {"id": "02-why", "shots": [card("why-1"), card("why-2", "Modern CAD software"), card("why-3", "AI 3D generation"),
                                   card("why-4", "OpenSCAD builds parts out of code")],
         "say": "3D printing has come a long way. It's a lot cheaper now, and the printers are way better today than they were even "
                "three years ago. But while the hardware has made huge advancements, the software hasn't really gotten any better. "
                "Modern CAD software is often bloated and very difficult to learn, and the open-source alternatives lack general "
                "adoption and frankly aren't any easier. And most AI 3D generation today just spits out a mesh. It might look right, "
                "but it isn't built to exact measurements, and for a repair, the measurements are everything. OpenSCAD builds parts "
                "out of code, with exact numbers. That's hard for a person to write, but it's perfect for an AI. So that's what "
                "Kintsugi builds on."},
        {"id": "03-example", "shots": [card("example"), page("home", "print out a reference sheet")],
         "say": "Let's say the handle on your water bottle snapped. The bottle's fine, but that one small piece of plastic is broken. "
                "That's no reason to go buy a new water bottle. But how do you actually repair the handle? In the age of AI, this "
                "shouldn't be a difficult task. With Kintsugi, you print out a reference sheet, put the broken part on it, take a few "
                "pictures from a couple of different angles, and upload them, along with a quick sentence about what broke."},
        {"id": "04-how", "shots": [card("how-1"), card("how-2", "It measures what it can"), card("how-3", "still missing something"),
                                   card("how-4", "All of that turns into a spec"), card("how-5", "designs the part")],
         "say": "From there, Kintsugi figures out what the part is, and what it needs to fit onto. In this case, the neck of the bottle. "
                "It measures what it can straight from the photos, using the markers on the reference sheet. If it's still missing "
                "something, it asks you. But only for the exact photo or measurement it needs, so it's not wasting your time. All of "
                "that turns into a spec: every measurement the part has to hit, and how much room for error each one gets. Then GPT-6 "
                "designs the part in OpenSCAD, measures it, and checks its own work before you ever print anything."},
        {"id": "05-graph", "shots": [page("graph")],
         "say": "Under the hood, all of this runs on a node-based graph. Every step is a node, and each node says what it needs and "
                "what it produces. Compiling needs the code. The checks need the 3D model. So anything that doesn't depend on "
                "something else runs at the same time. The measurements and the drawings get built in parallel. And you're a node "
                "too. When it needs a photo or a measurement from you, the graph just pauses there and picks back up when you "
                "answer. You can watch the whole thing run live in the Graph tab."},
        {"id": "06-demo", "shots": [page("spec")],
         "say": "For this demo, I'm starting from a spec instead of photos. If you already know your measurements, say you measured "
                "with calipers, you can skip the photos and just type them in. The public demo runs a scripted version, because I "
                "didn't want to leave my OpenAI key live on the internet. But the run you're about to see is a real one."},
        {"id": "07-run", "shots": [page("timeline")],
         "say": "GPT-6 is the orchestrator behind this entire thing. We feed it OpenSCAD's documentation directly, and it writes the "
                "part and runs the compile itself. Then every dimension gets measured on the actual 3D mesh, not taken from its own "
                "code. On this run, the first try didn't compile. GPT-6 read the error, fixed it, and tried again, and the second try "
                "passed all fifteen checks. OpenSCAD is basically a niche programming language, and I doubt there's much training data "
                "out there for it. So for a part like this, I think it did a really good job."},
        {"id": "08-blueprints", "shots": [page("sheets")],
         "say": "This is one of my favorite parts: the blueprints. After every try, Kintsugi draws a full set of engineering drawings "
                "of what was actually built. Top, front, side, and cross-sections, with the real measurements on them. Green means "
                "it's in tolerance, red means it's off. Those drawings are the model's reference. It can keep iterating without "
                "rescanning the photos or re-explaining everything to itself. It just looks at where it's at."},
        {"id": "09-checks", "shots": [page("checks")],
         "say": "Every check here is a real measurement. Hover over one, and it shows you exactly where on the part it was measured. "
                "Then a second GPT-6 reviews the drawings without ever seeing the code. Kind of like getting a second opinion from a "
                "coworker. On this run, it signed off. And this entire run, on a live endpoint, cost about a dollar."},
        {"id": "10-customize", "shots": [page("customize")],
         "say": "The best thing about the result is that it's not a dead file. Every dimension has its own slider with a live 3D "
                "preview, and the ones that have to fit show where their number came from. So if you print it and it's slightly off, "
                "you just adjust it and reprint."},
        {"id": "11-print", "shots": [page("export")],
         "say": "Standard procedure for repairs like this is to print what's called a fit coupon first. It's just the part that has "
                "to fit, at three slightly different sizes. It prints in a few minutes. You see which one fits, and then you print "
                "the real part. You get the STL, plus a print card with the settings."},
        {"id": "12-close", "shots": [card("close")],
         "say": "Kintsugi. Photograph what broke, print what fits. The demo and code are linked below, and everything else can be "
                "found in the GitHub repository. Thank you!"},
    ]


# ---- narration: text-to-speech stand-in ------------------------------------------------------------------------------

def voice(bs: list[dict]) -> None:
    import httpx
    d = OUT / "voice"
    d.mkdir(parents=True, exist_ok=True)
    key = openai_key()
    for b in bs:
        h = hashlib.sha1((VOICE + VOICE_STYLE + b["say"]).encode()).hexdigest()[:10]
        path = d / f"{b['id']}.mp3"
        stamp = d / f"{b['id']}.hash"
        if path.exists() and stamp.exists() and stamp.read_text() in (h, "human"):
            continue
        r = httpx.post("https://api.openai.com/v1/audio/speech", headers={"Authorization": f"Bearer {key}"}, timeout=120,
                       json={"model": VOICE_MODEL, "voice": VOICE, "input": b["say"], "instructions": VOICE_STYLE, "response_format": "mp3"})
        r.raise_for_status()
        path.write_bytes(r.content)
        stamp.write_text(h)
        (d / f"{b['id']}.cues.json").unlink(missing_ok=True)
        print(f"voice {b['id']}: {duration(path):.1f}s")


def voice_len(b: dict) -> float:
    return duration(OUT / "voice" / f"{b['id']}.mp3")


# ---- a human voice-over: one take, cut into sections ----------------------------------------------------------------

# one chain for the whole take so every section sits at the same loudness: rumble off, a light FFT denoise at the
# measured room floor (about -60 dB; stronger settings made the voice gritty), then an EQ read off the take's own
# third-octave spectrum: the 315-500 Hz bump (+3 dB over the speech trend, the boxy/nasal honk) cut, the 5-6.3 kHz grit
# peak (+4 dB) notched, presence at 3 kHz and air above 9 kHz lifted for crispness; de-essing after the boosts, light
# compression; loudness is then normalised in two passes
CLEAN = ("highpass=f=80,afftdn=nr=8:nf=-60:tn=1,"
         "equalizer=f=420:t=q:w=1.1:g=-3.5,equalizer=f=6200:t=q:w=2:g=-3.5,"
         "equalizer=f=3000:t=q:w=0.8:g=2,highshelf=f=9000:g=3,deesser=i=0.4,"
         "acompressor=threshold=-24dB:ratio=2.5:attack=6:release=120:makeup=2")
LOUD = "loudnorm=I=-16:TP=-1.5:LRA=9"
GATE = "agate=threshold=0.005:ratio=2:range=0.2:attack=10:release=250:knee=2.8"  # room noise between words down ~14 dB
# what the speech recogniser hears wrong in this project's vocabulary; captions are otherwise the words as said
ASR_FIXES = [(r"\bKitsugi\b", "Kintsugi"), (r"\bintolerant\b", "in tolerance"), (r"\band opens CAD\b", "in OpenSCAD"),
             (r"\bopens CAD\b", "OpenSCAD"), (r"\bgraphic workflow\b", "graph workflow"), (r"\b15\b", "fifteen")]
LABEL_GAP = 0.8   # a lone word with this much silence around it is a section heading read aloud
JOIN_GAP = 0.9    # pauses up to this long are kept as said; longer ones are shortened to KEEP_PAUSE
KEEP_PAUSE = 0.6


def transcribe_words(path: Path, out: Path) -> dict:
    import httpx
    mp3 = out.with_suffix(".asr.mp3")
    run_ff("-i", str(path), "-ac", "1", "-ar", "16000", "-b:a", "64k", str(mp3))
    with open(mp3, "rb") as fh:
        r = httpx.post("https://api.openai.com/v1/audio/transcriptions", headers={"Authorization": f"Bearer {openai_key()}"}, timeout=600,
                       data={"model": "whisper-1", "response_format": "verbose_json", "timestamp_granularities[]": ["word", "segment"],
                             "prompt": "Kintsugi, OpenSCAD, GPT-6, STL, fit coupon."},
                       files={"file": (mp3.name, fh, "audio/mpeg")})
    r.raise_for_status()
    out.write_text(json.dumps(r.json(), indent=1), encoding="utf-8")
    return r.json()


def clean_take(src: Path, dst: Path) -> None:
    err = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(src), "-af", f"{CLEAN},{LOUD}:print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = json.loads(err[err.rindex("{"):err.rindex("}") + 1])
    second = (f"{LOUD}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
              f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    run_ff("-i", str(src), "-af", f"{CLEAN},{second},{GATE},aresample=48000", "-ac", "1", str(dst))


def silences(path: Path) -> list[tuple[float, float]]:
    err = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path), "-af", "silencedetect=noise=-42dB:d=0.18", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    return list(zip(starts, ends + [duration(path)] * (len(starts) - len(ends))))


def speech_span(s: float, e: float, sil: list[tuple[float, float]]) -> tuple[float, float]:
    """A transcript segment's edges moved to where the voice actually starts and stops."""
    onset = next((b for a, b in sil if a - 0.05 <= s <= b + 0.05), None)  # starts inside a silence: speech begins at its end
    if onset is None:
        before = [b for a, b in sil if b <= s and s - b <= 0.7]
        onset = before[-1] if before else s - 0.12
    offset = next((a for a, b in sil if a - 0.05 <= e <= b + 0.05), None)
    if offset is None:
        after = [a for a, b in sil if a >= e and a - e <= 0.7]
        offset = after[0] if after else e + 0.15
    return max(onset, 0.0), max(offset, onset + 0.2)


def assign(bs: list[dict], segs: list[dict]) -> None:
    """Give each transcript segment the section whose script it belongs to (or None: a heading, a remark, an aside)."""
    texts = {b["id"]: words(b["say"]) for b in bs}
    prev = None
    for i, sg in enumerate(segs):
        ws = words(sg["text"])
        gap_before = sg["start"] - segs[i - 1]["end"] if i else 9.0
        gap_after = segs[i + 1]["start"] - sg["end"] if i + 1 < len(segs) else 9.0
        if len(ws) <= 1 and gap_before >= LABEL_GAP and gap_after >= LABEL_GAP:
            sg["sec"], sg["why"] = None, "heading"
            continue
        if i and prev and segs[i - 1]["sec"] and not re.search(r"[.?!]$", segs[i - 1]["text"]) and gap_before < 0.6:
            sg["sec"], sg["score"], sg["why"] = segs[i - 1]["sec"], 1.0, ""  # the rest of a sentence the last segment began
            continue
        scores = {k: contained(ws, t) for k, t in texts.items()}
        best = max(scores, key=scores.get)
        if prev and scores[prev] >= scores[best] - 0.15:
            best = prev  # a short line that fits two sections stays with the one being spoken
        sg["sec"], sg["score"] = (best, scores[best]) if scores[best] >= 0.5 else (None, scores[best])
        sg["why"] = "" if sg["sec"] else "not in the script"
        prev = sg["sec"] or prev
    # a section said twice: an earlier run whose words the later run repeats is a fluffed take
    runs: list[list[dict]] = []
    for sg in segs:  # anything outside the script (a remark, "redoing this section") ends a run
        if sg["sec"] and runs and runs[-1] and runs[-1][0]["sec"] == sg["sec"]:
            runs[-1].append(sg)
        else:
            runs.append([sg] if sg["sec"] else [])
    runs = [r for r in runs if r]
    for i, r in enumerate(runs):
        later = [w for r2 in runs[i + 1:] if r2[0]["sec"] == r[0]["sec"] for sg in r2 for w in words(sg["text"])]
        if later and contained([w for sg in r for w in words(sg["text"])], later) >= 0.5:
            for sg in r:
                sg["sec"], sg["why"] = None, "redone later"
    # a single line said again inside a section: keep the last one
    for i, sg in enumerate(segs):
        if not sg["sec"] or len(words(sg["text"])) < 4:
            continue
        for sg2 in segs[i + 1:]:
            if sg2["sec"] == sg["sec"] and difflib.SequenceMatcher(None, words(sg["text"]), words(sg2["text"])).ratio() >= 0.7:
                sg["sec"], sg["why"] = None, "line redone"
                break


def caption_cues(kept: list[dict], remap) -> list[dict]:
    text = lambda s: " ".join(s.split())  # noqa: E731
    cues: list[dict] = []
    for sg in kept:
        t = sg["text"].strip()
        for pat, rep in ASR_FIXES:
            t = re.sub(pat, rep, t)
        a, b = remap(sg["span"][0]), remap(sg["span"][1])
        if cues and ((not re.search(r"[.?!]$", cues[-1]["text"]) and a - cues[-1]["end"] < 0.6) or a < cues[-1]["end"] - 0.05):
            cues[-1]["text"] = text(cues[-1]["text"] + " " + t)
            cues[-1]["end"] = b
        else:
            cues.append({"start": a, "end": b, "text": text(t)})
    out = []
    for c in cues:  # long lines become two captions, split near the middle (at a comma when there is one)
        if len(c["text"]) <= 92:
            out.append(c)
            continue
        mid = len(c["text"]) // 2
        cuts = [m.end() for m in re.finditer(r"[,;:] ", c["text"])] or [m.end() for m in re.finditer(r" ", c["text"])]
        k = min(cuts, key=lambda x: abs(x - mid))
        frac = k / len(c["text"])
        t_mid = c["start"] + (c["end"] - c["start"]) * frac
        out += [{"start": c["start"], "end": t_mid, "text": c["text"][:k].strip()}, {"start": t_mid, "end": c["end"], "text": c["text"][k:].strip()}]
    return out


def cut_take(bs: list[dict], take: Path, render: bool = True) -> None:
    """One recorded take -> scratch/demo/voice/<id>.mp3 (cleaned, the last take of every line, long pauses shortened)
    and <id>.cues.json (captions timed to the words as said); the cut list goes to voice-work/cut.txt."""
    work, d = OUT / "voice-work", OUT / "voice"
    work.mkdir(parents=True, exist_ok=True)
    d.mkdir(parents=True, exist_ok=True)
    tj = work / f"{take.stem}.transcript.json"
    tr = json.loads(tj.read_text(encoding="utf-8")) if tj.exists() else transcribe_words(take, tj)
    clean = work / f"{take.stem}.clean.wav"
    if not clean.exists() or clean.stat().st_mtime < take.stat().st_mtime:
        clean_take(take, clean)
    sil = silences(clean)
    segs = [{"start": s["start"], "end": s["end"], "text": s["text"].strip()} for s in tr["segments"]]
    assign(bs, segs)
    log = []
    for sg in segs:
        sg["span"] = speech_span(sg["start"], sg["end"], sil)
        log.append(f"{sg['span'][0]:7.2f}-{sg['span'][1]:7.2f}  {sg['sec'] or '-- ' + sg['why']:<16} {sg['text']}")
    (work / "cut.txt").write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))
    if not render:
        return
    for b in bs:
        kept = [sg for sg in segs if sg["sec"] == b["id"]]
        if not kept:
            print(f"MISSING take for {b['id']}: keeping what is in voice/")
            continue
        spans: list[list[float]] = []
        for sg in kept:
            a, e = sg["span"]
            if spans and a - spans[-1][1] <= JOIN_GAP:
                spans[-1][1] = e
            else:
                spans.append([a, e])
        # pad: a breath before the first word, a tail after the last, half the kept pause on each side of a cut
        iv = []
        for i, (a, e) in enumerate(spans):
            pre = 0.2 if i == 0 else KEEP_PAUSE / 2
            post = 0.35 if i == len(spans) - 1 else KEEP_PAUSE / 2
            iv.append((max(a - pre, iv[-1][1] if iv else 0.0), e + post))

        def remap(t: float, iv=iv) -> float:
            off = 0.0
            for a, e in iv:
                if t <= e:
                    return off + max(0.0, t - a)
                off += e - a
            return off

        chains = [f"[0:a]atrim={a:.3f}:{e:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.012,afade=t=out:st={e - a - 0.012:.3f}:d=0.012[a{i}]"
                  for i, (a, e) in enumerate(iv)]
        graph = ";".join(chains) + ";" + "".join(f"[a{i}]" for i in range(len(iv))) + f"concat=n={len(iv)}:v=0:a=1[out]"
        out = d / f"{b['id']}.mp3"
        run_ff("-i", str(clean), "-filter_complex", graph, "-map", "[out]", "-ac", "1", "-ar", "48000", "-c:a", "libmp3lame", "-q:a", "2", str(out))
        (d / f"{b['id']}.hash").write_text("human")
        cues = caption_cues(kept, remap)
        (d / f"{b['id']}.cues.json").write_text(json.dumps(cues, indent=1), encoding="utf-8")
        print(f"voice {b['id']}: {duration(out):5.1f}s from {len(kept)} lines, {len(iv)} cuts")


def load_cues(b: dict) -> list[dict]:
    p = OUT / "voice" / f"{b['id']}.cues.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    # text-to-speech: sentences timed by their length
    sents = re.split(r"(?<=[.?!])\s+", b["say"])
    total, n = voice_len(b), sum(len(s) for s in sents)
    cues, t = [], 0.0
    for s in sents:
        dt = total * len(s) / n
        cues.append({"start": t, "end": t + dt, "text": s})
        t += dt
    return cues


def shot_plan(b: dict) -> list[tuple[dict, float, float]]:
    """Each shot's start and end on the section's own clock (the voice starts at LEAD)."""
    total = voice_len(b) + LEAD + TAIL
    cues = load_cues(b)
    starts = [0.0]
    for s in b["shots"][1:]:
        c = next((c for c in cues if contained(words(s["at"]), words(c["text"])) >= 0.75), None)
        if not c:
            print(f"  {b['id']}: no caption says '{s['at']}', the shot starts after the previous one")
        starts.append(max(starts[-1] + 1.5, c["start"] + LEAD - 0.15 if c else starts[-1] + 4.0))
    return list(zip(b["shots"], starts, starts[1:] + [total]))


# ---- picture ---------------------------------------------------------------------------------------------------------

CARD_CSS = f"""
@font-face {{ font-family: Barlow; font-weight: 700; src: url({FONTS}/barlow-semi-condensed-latin-700-normal.woff2); }}
@font-face {{ font-family: Plex; font-weight: 400; src: url({FONTS}/ibm-plex-sans-latin-400-normal.woff2); }}
@font-face {{ font-family: Plex; font-weight: 600; src: url({FONTS}/ibm-plex-sans-latin-600-normal.woff2); }}
@font-face {{ font-family: PlexMono; font-weight: 400; src: url({FONTS}/ibm-plex-mono-latin-400-normal.woff2); }}
html, body {{ margin: 0; width: {W}px; height: {H}px; background: #05142e; color: #f3f7fe; font-family: Plex, sans-serif; }}
body {{ display: flex; flex-direction: column; justify-content: center; padding: 0 120px 110px; box-sizing: border-box; gap: 30px;
  background-image: linear-gradient(rgba(190,212,249,.06) 1px, transparent 1px), linear-gradient(90deg, rgba(190,212,249,.06) 1px, transparent 1px);
  background-size: 40px 40px; }}
.brand {{ display: flex; align-items: center; gap: 22px; font-family: Barlow; font-size: 40px; letter-spacing: 6px; }}
.brand img {{ width: 88px; height: 88px; }}
h1 {{ font-family: Barlow; font-size: 92px; line-height: 1.02; margin: 0; max-width: 1300px; }}
p {{ font-size: 34px; line-height: 1.4; color: #bed4f9; margin: 0; max-width: 1250px; }}
.dim {{ display: flex; align-items: center; gap: 16px; color: #6c9ef0; font-family: PlexMono; font-size: 26px; max-width: 1360px; letter-spacing: 2px; }}
.dim i {{ flex: 1; height: 2px; background: #6c9ef0; }} .dim b {{ width: 2px; height: 30px; background: #6c9ef0; }}
.links {{ font-family: PlexMono; font-size: 28px; color: #f3f7fe; line-height: 1.7; }}
.links span {{ color: #6c9ef0; display: inline-block; width: 150px; }}
.cols {{ display: flex; gap: 48px; align-items: flex-start; }}
.list {{ display: flex; flex-direction: column; gap: 24px; width: 640px; flex: none; }}
.item h2 {{ font-family: Barlow; font-size: 46px; line-height: 1.05; margin: 0 0 6px; color: #f3f7fe; }}
.item div {{ font-size: 25px; line-height: 1.35; color: #bed4f9; }}
.item.past h2 {{ color: #6c9ef0; }} .item.past div {{ color: #4f6f9f; }}
.code {{ flex: 1; border: 2px solid #155dd3; background: rgba(21,93,211,.12); padding: 22px 24px; font-family: PlexMono; font-size: 17px;
  line-height: 1.75; color: #f3f7fe; white-space: pre; }}
.code em {{ font-style: normal; color: #6c9ef0; }} .code small {{ display: block; margin-top: 12px; font-size: 18px; color: #6c9ef0; }}
.steps {{ display: flex; flex-direction: column; gap: 14px; }}
.step {{ display: flex; gap: 28px; align-items: center; border: 2px solid rgba(108,158,240,.25); padding: 14px 26px; }}
.step .n {{ font-family: PlexMono; font-size: 26px; color: #6c9ef0; width: 40px; }}
.step h2 {{ font-family: Barlow; font-size: 40px; margin: 0; width: 640px; color: #6c9ef0; }}
.step div {{ font-size: 25px; color: #4f6f9f; }}
.step.done h2 {{ color: #bed4f9; }} .step.done div {{ color: #6c9ef0; }} .step.done .n::after {{ content: " ✓"; }}
.step.on {{ border-color: #f3f7fe; background: rgba(21,93,211,.28); }} .step.on h2 {{ color: #f3f7fe; }} .step.on div {{ color: #bed4f9; }}
"""

WHY = [("Printers got cheaper, and better.", "Better hardware than three years ago, for less money."),
       ("The software didn't.", "CAD is bloated and hard to learn; the open-source tools aren't easier."),
       ("AI 3D models are meshes.", "They look right, but they aren't built to exact measurements. For a repair, the measurements are everything."),
       ("OpenSCAD: the part is code.", "Exact numbers. Hard for a person to write, a good fit for a model.")]
SCAD = """<em>/* [Interface] */</em>
neck_id = 43.2;    <em>// Measured bottle neck diameter</em>
clearance = 0.25;  <em>// Diametral sliding-fit clearance</em>
ring_height = 6;   <em>// Thickness of the neck ring and loop</em>
<em>/* [Body] */</em>
ring_od = 54;      <em>// Neck ring outside diameter</em>
loop_inner_w = 42; <em>// Finger opening extent along X</em>
<small>from the real GPT-6 run · iter_02_part.scad</small>"""
HOW = [("Identify the part", "and what it fits onto: here, the neck of the bottle"),
       ("Measure from the photos", "the markers on the reference sheet give the scale"),
       ("Ask only for what's missing", "the exact photo or measurement, nothing else"),
       ("Write the spec", "every measurement the part has to hit, and its tolerance"),
       ("Design, measure, check", "GPT-6 writes OpenSCAD; every dimension is measured on the mesh")]


def card_html(name: str) -> str:
    if name.startswith("why-"):
        k = int(name[4:])
        items = "".join(f'<div class="item{" past" if i < k - 1 else ""}"><h2>{h}</h2><div>{s}</div></div>' for i, (h, s) in enumerate(WHY[:k]))
        code = f'<div class="code">{SCAD}</div>' if k == 4 else ""
        return f'<div class="dim">WHY OPENSCAD</div><div class="cols"><div class="list">{items}</div>{code}</div>'
    if name.startswith("how-"):
        k = int(name[4:])
        rows = "".join(f'<div class="step{" on" if i == k - 1 else " done" if i < k - 1 else ""}"><span class="n">{i + 1}</span>'
                       f'<div><h2>{h}</h2><div>{s}</div></div></div>' for i, (h, s) in enumerate(HOW))
        return f'<div class="dim">HOW IT WORKS</div><div class="steps">{rows}</div>'
    return {
        "title": """<div class="brand"><img src="{mark}">KINTSUGI</div><h1>Photograph what broke.<br>Print what fits.</h1>
<p>A web app on top of OpenSCAD that turns a few photos, or a simple spec, into a 3D-printable repair.</p>
<div class="dim"><b></b><i></i>HACK47: OFFGRID · Krish<i></i><b></b></div>""",
        "example": """<div class="dim">EXAMPLE</div><h1>The handle on your water bottle snapped.</h1>
<p>The bottle is fine. One small piece of plastic isn't, and that's no reason to buy a new bottle.</p>""",
        "close": """<div class="brand"><img src="{mark}">KINTSUGI</div><h1>Photograph what broke.<br>Print what fits.</h1>
<div class="links"><span>demo</span>kintsugi.orangecliff-df186167.eastus2.azurecontainerapps.io<br><span>code</span>github.com/KrishGup/kintsugi<br>
<span>the run</span>eval/reports/gpt6-first-run</div>
<p>Built for HACK47: OFFGRID on the OpenAI Responses API.</p>""",
    }[name]


CURSOR_JS = """
() => {
  if (document.getElementById('__cursor')) return;
  const k = document.createElement('div'); k.id = '__cursor';
  Object.assign(k.style, { position: 'fixed', left: '-100px', top: '-100px', width: '26px', height: '26px', borderRadius: '50%',
    background: 'rgba(21,93,211,.25)', border: '2.5px solid #155dd3', pointerEvents: 'none', zIndex: '2147483647',
    transform: 'translate(-50%,-50%)', transition: 'transform .09s ease' });
  document.body.appendChild(k);
  window.addEventListener('mousemove', e => { k.style.left = e.clientX + 'px'; k.style.top = e.clientY + 'px'; }, true);
  window.addEventListener('mousedown', () => k.style.transform = 'translate(-50%,-50%) scale(.65)', true);
  window.addEventListener('mouseup', () => k.style.transform = 'translate(-50%,-50%) scale(1)', true);
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


async def drag(pg, x, y, dx, dy, steps=30):
    await pg.mouse.move(x, y, steps=12)
    await pg.mouse.down()
    await pg.mouse.move(x + dx, y + dy, steps=steps)
    await pg.mouse.up()


async def act(pg, kind: str, need: float) -> None:
    async def tab(name):  # a tab in any pane, by its visible name
        t = pg.get_by_role("tab", name=re.compile(rf"^{name}", re.I)).first
        await glide(pg, t, click=True)
        await pg.wait_for_timeout(700)

    if kind == "overview":
        await pg.wait_for_timeout(1500)
        canvas = pg.locator("canvas").first
        box = await canvas.bounding_box() if await canvas.count() else None
        if box:
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            await drag(pg, cx - 120, cy, 240, 30, steps=60)
            await pg.wait_for_timeout(1500)
            await drag(pg, cx + 100, cy + 20, -160, -40, steps=50)
    elif kind == "home":
        await pg.wait_for_timeout(1000)
        await glide(pg, pg.get_by_role("tab", name=re.compile("photograph what broke", re.I)).first)
        await pg.wait_for_timeout(1500)
        await glide(pg, pg.get_by_role("button", name=re.compile("calibration sheet", re.I)).first)
        await pg.wait_for_timeout(2500)
        await glide(pg, pg.locator(".file-drop-main").first)
        await pg.wait_for_timeout(2500)
        await glide(pg, pg.locator("textarea").first)
    elif kind == "graph":
        await tab("graph")
        await pg.wait_for_timeout(1500)
        svgs = pg.locator(".gv-svg")
        for k in range(min(await svgs.count(), 2)):
            nodes = svgs.nth(k).locator("g[transform]")
            for i in range(min(await nodes.count(), 6)):
                await glide(pg, nodes.nth(i), steps=14)
                await pg.wait_for_timeout(1100)
        body = pg.locator(".pane-body").last
        bb = await body.bounding_box() if await body.count() else None
        if bb:
            await pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2, steps=10)
            for _ in range(8):
                await pg.mouse.wheel(0, 160)
                await pg.wait_for_timeout(700)
    elif kind == "spec":
        await tab("from a spec")
        await pg.wait_for_timeout(1000)
        await glide(pg, pg.locator("select.select").first)
        await pg.wait_for_timeout(2000)
        await glide(pg, pg.locator("textarea").first)
        await pg.wait_for_timeout(2000)
        await pg.mouse.wheel(0, 300)
    elif kind == "timeline":
        await tab("timeline")
        await pg.mouse.move(W * 0.15, H * 0.5, steps=12)
        await pg.wait_for_timeout(2500)
        n = max(int((need - 6) / 1.1), 10)
        for _ in range(n):
            await pg.mouse.wheel(0, -130)
            await pg.wait_for_timeout(1000)
    elif kind == "sheets":
        await tab("views")
        await pg.wait_for_timeout(int(need * 0.45 * 1000))
        await tab("sections")
    elif kind == "checks":
        await tab("checks")
        rows = pg.locator(".table-checks tbody tr")
        for i in range(min(await rows.count(), 6)):
            await glide(pg, rows.nth(i))
            await pg.wait_for_timeout(1300)
        await tab("guide")
    elif kind == "customize":
        await tab("customize")
        await pg.wait_for_timeout(1500)
        thumb = pg.locator(".slider-thumb").nth(4)
        box = await thumb.bounding_box() if await thumb.count() else None
        if box:
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            await drag(pg, x, y, 70, 0, steps=24)
            await pg.wait_for_timeout(4000)
            await drag(pg, x + 70, y, -70, 0, steps=24)
    elif kind == "export":
        await pg.wait_for_timeout(800)
        await glide(pg, pg.get_by_role("button", name=re.compile("^coupon", re.I)).first, click=True)
        await pg.wait_for_timeout(int(max(need * 0.45, 5) * 1000))
        btn = pg.get_by_role("button", name=re.compile("^export", re.I)).first
        await glide(pg, btn, click=True)
        await pg.wait_for_timeout(1200)
        go = pg.get_by_role("button", name=re.compile("export last passing|re-export", re.I)).first
        if await go.count():
            await glide(pg, go, click=True)


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
            for k, (shot, t0, t1) in enumerate(shot_plan(beat)):
                name = f"{beat['id']}-{k}"
                if "card" in shot:
                    ctx = await b.new_context(viewport={"width": W, "height": H})
                    pg = await ctx.new_page()
                    html = cdir / f"{name}.html"
                    html.write_text(f"<!doctype html><meta charset=utf-8><style>{CARD_CSS}</style>" + card_html(shot["card"]).replace("{mark}", MARK),
                                    encoding="utf-8")
                    await pg.goto(html.as_uri(), wait_until="load")
                    await pg.evaluate("document.fonts.ready")
                    await pg.wait_for_timeout(500)
                    await pg.screenshot(path=str(cdir / f"{name}.png"))
                    await ctx.close()
                    print(f"card {name} ({t1 - t0:.1f}s)")
                    continue
                ctx = await b.new_context(viewport={"width": W, "height": H}, record_video_dir=str(tmp), record_video_size={"width": W, "height": H})
                if code:
                    await ctx.request.post(base + "/api/auth/login", data={"token": code})
                pg = await ctx.new_page()
                t_open = time.time()
                url = base + ("/#/" if shot["page"] in ("home", "spec") else f"/#/s/{sid}")
                await pg.goto(url, wait_until="load")
                await pg.wait_for_selector(".home, .topbar", timeout=90000)
                if shot["page"] not in ("home", "spec"):
                    await pg.get_by_role("tab", name=re.compile("^guide", re.I)).first.click()
                await pg.wait_for_timeout(1500)
                await pg.evaluate(CURSOR_JS)
                t_ready = time.time()
                need = t1 - t0
                await act(pg, shot["page"], need)
                left = need + 0.5 - (time.time() - t_ready)
                if left > 0:
                    await pg.wait_for_timeout(int(left * 1000))
                raw = await pg.video.path()
                await ctx.close()
                dst = cdir / f"{name}.webm"
                dst.unlink(missing_ok=True)
                Path(raw).rename(dst)
                (cdir / f"{name}.trim").write_text(f"{t_ready - t_open:.2f}")
                print(f"clip {name}: lead {t_ready - t_open:.1f}s, {need:.1f}s")
        await b.close()


# ---- assembly --------------------------------------------------------------------------------------------------------

def caption_filters(b: dict, cap: Path) -> list[str]:
    cues = load_cues(b)
    out = []
    for i, c in enumerate(cues):
        nxt = cues[i + 1]["start"] if i + 1 < len(cues) else None
        end = nxt if nxt is not None and nxt - c["end"] < 0.8 else c["end"] + 0.3
        tf = cap / f"{b['id']}-{i:02d}.txt"
        tf.write_text("\n".join(textwrap.wrap(c["text"], 72)), encoding="utf-8")
        out.append(f"drawtext=fontfile=cap.ttf:textfile={tf.name}:expansion=none:fontsize=30:fontcolor=0xF3F7FE:line_spacing=4:text_align=C"
                   f":box=1:boxcolor=0x05142E@0.88:boxborderw=16|28:x=(w-text_w)/2:y=h-text_h-46"
                   f":enable='between(t,{c['start'] + LEAD:.2f},{end + LEAD:.2f})'")
    return out


def assemble(bs: list[dict]) -> None:
    seg, cap = OUT / "segments", OUT / "captions"
    seg.mkdir(parents=True, exist_ok=True)
    cap.mkdir(parents=True, exist_ok=True)
    # drawtext needs a TrueType/OpenType file (the brand fonts ship as web fonts only): Segoe UI Semibold on Windows
    font = next((f for f in (Path("C:/Windows/Fonts/seguisb.ttf"), Path("C:/Windows/Fonts/segoeui.ttf"),
                             Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")) if f.exists()), None)
    if not font:
        raise SystemExit("no TrueType font for the captions")
    shutil.copy(font, cap / "cap.ttf")
    parts = []
    for beat in bs:
        total = voice_len(beat) + LEAD + TAIL
        plan = shot_plan(beat)
        ins, chains = [], []
        for k, (shot, t0, t1) in enumerate(plan):
            name, dur = f"{beat['id']}-{k}", t1 - t0
            if "card" in shot:
                ins += ["-loop", "1", "-t", f"{dur + 0.5:.2f}", "-i", str(OUT / "clips" / f"{name}.png")]
            else:
                lead = float((OUT / "clips" / f"{name}.trim").read_text())
                ins += ["-ss", f"{lead:.2f}", "-t", f"{dur + 0.5:.2f}", "-i", str(OUT / "clips" / f"{name}.webm")]
            chains.append(f"[{k}:v]fps=30,scale={W}:{H},setsar=1,format=yuv420p,tpad=stop_mode=clone:stop_duration=10,"
                          f"trim=duration={dur:.3f},setpts=PTS-STARTPTS[v{k}]")
        n = len(plan)
        ins += ["-i", str(OUT / "voice" / f"{beat['id']}.mp3")]
        caps = ",".join(caption_filters(beat, cap))
        graph = (";".join(chains) + ";" + "".join(f"[v{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0[vc];"
                 + f"[vc]{caps + ',' if caps else ''}fade=t=in:st=0:d=0.3,fade=t=out:st={total - 0.35:.2f}:d=0.35[v];"
                 + f"[{n}:a]aresample=48000,adelay={int(LEAD * 1000)}:all=1,apad,atrim=0:{total:.3f}[a]")
        out = seg / f"{beat['id']}.mp4"
        run_ff(*ins, "-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium",
               "-crf", "18", "-c:a", "aac", "-b:a", "160k", "-ac", "2", str(out), cwd=cap)
        print(f"segment {beat['id']}: {total:.1f}s, {n} shot{'s' if n > 1 else ''}")
        parts.append(out)
    lst = seg / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
    master = OUT / "kintsugi-demo.mp4"
    run_ff("-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(master))
    upload_copy(master)


def upload_copy(master: Path) -> None:
    """A copy under 10 MB for the repository and the browser upload tool: 720p at 24 fps (more bits per frame for the
    captions and the UI text), two-pass at the bitrate that fits. Mono AAC at 64k behind a limiter: at 48k the encoder's
    own ringing pushed the voice's true peak above 0 dBFS."""
    seg = OUT / "segments"
    total = duration(master)
    kbps = int((9.5 * 8 * 1024) / total - 72)
    small = OUT / "kintsugi-demo-upload.mp4"
    common = ["-vf", "scale=1280:720:flags=lanczos", "-c:v", "libx264", "-preset", "slow", "-tune", "animation", "-b:v", f"{kbps}k", "-r", "24"]
    run_ff("-i", str(master), *common, "-pass", "1", "-passlogfile", str(seg / "x264"), "-an", "-f", "mp4", os.devnull)
    run_ff("-i", str(master), *common, "-pass", "2", "-passlogfile", str(seg / "x264"), "-af", "alimiter=limit=0.7:level=false",
           "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-movflags", "+faststart", str(small))
    print(f"master {master} {total:.1f}s {master.stat().st_size / 1e6:.1f} MB; upload copy {small.stat().st_size / 1e6:.2f} MB at {kbps} kbps")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["voice", "record", "assemble", "all", "script"])
    ap.add_argument("--base", default="https://kintsugi-live.orangecliff-df186167.eastus2.azurecontainerapps.io")
    ap.add_argument("--session", default="")
    ap.add_argument("--code-file", default=str(ROOT / "scratch" / "tmp" / "live-access-code.txt"))
    ap.add_argument("--only", default="", help="comma-separated section id prefixes to re-record, e.g. 01,05")
    ap.add_argument("--take", default="", help="voice step: Krish's recorded take (one file, every section in order)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    fpath = OUT / "facts.json"
    if a.session and a.step in ("voice", "record", "all", "script"):
        fpath.write_text(json.dumps(facts(Site(a.base, a.code_file), a.session), indent=1))
    f = json.loads(fpath.read_text())
    bs = beats(f)
    if a.step == "script":
        print(json.dumps(f, indent=1))
        for k, v in SCRIPT_CLAIMS.items():
            if f.get(k) != v:
                print(f"WARNING: the script says {k} = {v}, the session says {f.get(k)}")
        if a.take:
            cut_take(bs, Path(a.take), render=False)
        return 0
    if a.step in ("voice", "all"):
        if a.take:
            cut_take(bs, Path(a.take))
        else:
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
