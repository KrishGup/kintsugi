"""Walk the product the way a first-time user (or a judge) would, in a real browser, and look at what they would see.

    python scripts/walk.py                 # demo mode, its own server on a free port, screenshots → scratch/walk/
    python scripts/walk.py --base http://localhost:8000   # against a server you are already running
    python scripts/walk.py --keep          # leave the server and the data directory up afterwards

Journeys: the home page (desktop light + dark, phone) · "From a spec" with the default example → Design this part →
the failing iteration turning green → Checks hover (section plane) → Export → the print card → a bad Customize apply
dropping the stage back → click-to-pin · a reference spec (honest stop in demo mode) · the phone session.
It prints what it observed against what is expected and exits 1 when something expected is missing — but the
screenshots in scratch/walk/ are the point: open them. Needs the `tools` extra (playwright + chromium).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratch" / "walk"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def shot(pg, path: Path) -> None:
    """A page screenshot, retried once: a freshly launched Chromium sometimes refuses its very first capture
    ("Unable to capture screenshot") and then works; a second failure is real and raises."""
    for attempt in range(2):
        try:
            await pg.screenshot(path=str(path))
            return
        except Exception:
            if attempt:
                raise
            await pg.wait_for_timeout(1000)


def rmtree(path: Path) -> None:
    """rmtree that copes with the read-only files git leaves in session folders on Windows."""
    def on_error(fn, p, exc):
        os.chmod(p, 0o700)
        try:
            fn(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=on_error)


def start_server(port: int, data_dir: Path) -> subprocess.Popen:
    env = {**os.environ, "KIN_PROVIDER": "fake", "KIN_DATA_DIR": str(data_dir), "KIN_AUTH": "none", "KIN_SETTINGS_LOCK": "0"}
    log = open(OUT / "server.log", "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "kintsugi.cli", "serve", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as r:
                if r.status == 200:
                    return proc
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    raise SystemExit("the server did not come up; see scratch/walk/server.log")


class Walk:
    def __init__(self, base: str):
        self.base = base
        self.problems: list[str] = []
        self.notes: list[str] = []

    def expect(self, cond: bool, what: str) -> None:
        (self.notes if cond else self.problems).append(("  ok   " if cond else "  MISS ") + what)

    async def run(self) -> None:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            b = await p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
            ctx = await b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
            pg = await ctx.new_page()
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))

            # ---- home --------------------------------------------------------------------------------------------
            await pg.goto(self.base + "/#/", wait_until="load")
            await pg.wait_for_selector(".home", timeout=20000)
            await pg.wait_for_timeout(400)
            await shot(pg, OUT / "01-home.png")
            await pg.emulate_media(color_scheme="dark")
            await pg.wait_for_timeout(300)
            await shot(pg, OUT / "02-home-dark.png")
            await pg.emulate_media(color_scheme="light")
            self.expect(not await pg.locator("[title]").count(), "no title= tooltips on the home page")

            # ---- from a spec, the default example ---------------------------------------------------------------------
            await pg.get_by_role("tab", name="From a spec").click()
            await pg.wait_for_timeout(200)
            default = await pg.locator("select.select").input_value()
            self.expect(default == "bottle_handle", f"default example is the bottle handle (got {default})")
            await pg.get_by_role("button", name="Create session").click()
            await pg.wait_for_url("**/#/s/**", timeout=30000)
            await pg.wait_for_selector(".topbar", timeout=20000)
            await pg.get_by_role("button", name="Design this part").click()
            status = await self.wait_run(pg)
            chips = await self.chips(pg)
            self.expect(status == "done", f"demo design finishes (status {status})")
            self.expect(chips == [("it 1", "fail"), ("it 2", "pass")], f"iteration 1 fails, iteration 2 passes (got {chips})")
            bar = await pg.locator(".topbar").inner_text()
            self.expect("spent" not in bar and "astra" not in bar, "demo mode claims no spend and no model in the top bar")
            await shot(pg, OUT / "03-designed.png")
            await pg.get_by_role("tab", name="Timeline").click()
            await pg.wait_for_timeout(400)
            await pg.locator(".ws-left").screenshot(path=str(OUT / "04-timeline.png"))
            text = await pg.locator(".ws-left").inner_text()
            self.expect("footprint.overall_length" in text, "the timeline names the check that caught the first attempt")

            # ---- checks hover → the section plane ----------------------------------------------------------------------
            await pg.get_by_role("tab", name="Checks").click()
            await pg.wait_for_timeout(300)
            rows = pg.locator(".table-checks tr.is-linked")
            n = await rows.count()
            self.expect(n >= 3, f"checks rows are linked to sections ({n})")
            if n:
                await rows.nth(1).hover()
                await pg.wait_for_timeout(500)
                self.expect(await pg.locator(".dim-focus").count() == 1, "hovering a check draws its section plane on the model")
                await shot(pg, OUT / "05-check-hover.png")
                await rows.nth(1).click()
                await pg.mouse.move(5, 5)
                await pg.wait_for_timeout(400)
                self.expect(await pg.locator(".dim-focus").count() == 1, "clicking a check pins the plane")
                await rows.nth(1).click()

            # ---- export → the print card ------------------------------------------------------------------------------
            await pg.locator(".topbar-actions button", has_text="Export").click()
            await pg.wait_for_selector(".popover")
            await pg.locator(".popover button", has_text="last passing iteration").click()
            for _ in range(120):
                if await pg.locator(".export-list li").count():
                    break
                await pg.wait_for_timeout(500)
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(500)
            await pg.get_by_role("tab", name="Guide").click()
            await pg.wait_for_timeout(500)
            self.expect((await self.stage(pg)).endswith("Print"), "the stage is Print after an export")
            self.expect(await pg.locator(".md-table").count() == 1, "the print card's parameter table renders as a table")
            await pg.locator(".ws-left").screenshot(path=str(OUT / "06-print-card.png"))

            # ---- a bad apply from the customizer -----------------------------------------------------------------------
            await pg.get_by_role("tab", name="Customize").click()
            await pg.wait_for_timeout(600)
            box = pg.locator(".cz-number input").first
            await box.fill("60")
            await box.press("Enter")
            await pg.wait_for_timeout(1500)
            await pg.locator(".cz-footer button", has_text="Apply").click()
            for _ in range(90):
                if len(await self.chips(pg)) >= 3:
                    break
                await pg.wait_for_timeout(700)
            await pg.wait_for_timeout(1500)
            self.expect((await self.stage(pg)).endswith("Design"), "a failing apply after an export drops the stage back to Design")
            await shot(pg, OUT / "07-after-bad-apply.png")
            session_url = pg.url

            # ---- a reference spec in demo mode -------------------------------------------------------------------------
            await pg.goto(self.base + "/#/", wait_until="load")
            await pg.wait_for_selector(".home", timeout=20000)
            await pg.get_by_role("tab", name="From a spec").click()
            await pg.select_option("select.select", "ab_cabinet_plug")
            await pg.wait_for_timeout(200)
            picked = await pg.locator(".home input.input").first.input_value()
            self.expect(picked != "bottle handle", f"picking another example renames the part (got {picked!r})")
            self.expect(await pg.locator(".field-hint", has_text="no template").count() == 1, "demo mode warns before a reference spec")
            await pg.get_by_role("button", name="Create session").click()
            await pg.wait_for_url("**/#/s/**", timeout=30000)
            await pg.wait_for_selector(".topbar", timeout=20000)
            await pg.get_by_role("button", name="Design this part").click()
            status = await self.wait_run(pg)
            await pg.get_by_role("tab", name="Guide").click()
            await pg.wait_for_timeout(400)
            guide = await pg.locator(".ws-left").inner_text()
            self.expect(status == "stopped" and "Demo mode ended without a finished part" in guide, "a reference spec stops honestly in demo mode")
            await shot(pg, OUT / "08-reference-spec.png")
            await ctx.close()

            # ---- phone -------------------------------------------------------------------------------------------------
            ctx = await b.new_context(viewport={"width": 390, "height": 780}, device_scale_factor=2, is_mobile=True, has_touch=True)
            pg = await ctx.new_page()
            await pg.goto(self.base + "/#/", wait_until="load")
            await pg.wait_for_selector(".home", timeout=20000)
            await pg.wait_for_timeout(300)
            await shot(pg, OUT / "09-phone-home.png")
            wide = await pg.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
            self.expect(not wide, "no horizontal scroll on a phone")
            await pg.goto(session_url, wait_until="load")
            await pg.wait_for_selector(".topbar", timeout=20000)
            await pg.wait_for_timeout(500)
            await shot(pg, OUT / "10-phone-session.png")
            self.expect(not await pg.evaluate("[...document.querySelectorAll('.ws-handle')].some(e => getComputedStyle(e).display !== 'none')"), "no resize handles on a phone")
            await b.close()
            self.expect(not errors, f"no page errors ({errors[:2]})")

    async def wait_run(self, pg, limit: float = 150) -> str:
        t0 = time.time()
        while time.time() - t0 < limit:
            st = await pg.locator(".topbar .pill").first.inner_text()
            if st in ("done", "stopped", "error", "spend cap reached", "budget exhausted") and not await pg.locator(".topbar-progress").count():
                await pg.wait_for_timeout(1500)
                return st
            await pg.wait_for_timeout(700)
        return "timeout"

    async def chips(self, pg) -> list[tuple[str, str]]:
        texts = await pg.locator(".chips .chip").all_inner_texts()
        out = []
        for i, t in enumerate(texts):
            cls = await pg.locator(".chips .chip").nth(i).get_attribute("class") or ""
            out.append((t, "fail" if "fail" in cls else "pass"))
        return out

    async def stage(self, pg) -> str:
        return (await pg.locator(".stagebar .stage.current").inner_text()).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="a running server (default: start one in demo mode)")
    ap.add_argument("--keep", action="store_true", help="leave the server and scratch/walk/data in place")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    proc = None
    base = args.base
    data = OUT / "data"
    if not base:
        if data.exists() and not args.keep:
            rmtree(data)
        port = free_port()
        proc = start_server(port, data)
        base = f"http://127.0.0.1:{port}"
    w = Walk(base)
    try:
        asyncio.run(w.run())
    finally:
        if proc and not args.keep:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
    print("\n".join(w.notes + w.problems))
    print(f"\nscreenshots: {OUT}")
    return 1 if w.problems else 0


if __name__ == "__main__":
    sys.exit(main())
