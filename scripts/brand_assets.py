"""Generate the Kintsugi brand kit from one source of truth.

    python scripts/brand_assets.py            # writes docs/brand/*, web/public/* (icons, manifest, og image)

The mark: a ring — the part, the neck ring of the hero demo — cracked on a diagonal and mended with a gold seam.
Everything else derives from it: the wordmark (Barlow Semi Condensed 700, real glyph outlines, no font needed to
view the SVG), the lockups, the favicon set, the app icons, the social image, and the brand sheet.

Needs: fontTools (outlines), Pillow (ico), playwright + chromium (SVG → PNG). Deterministic; commit the outputs.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "brand"
PUB = ROOT / "web" / "public"
FONTS = ROOT / "web" / "node_modules" / "@fontsource"

# ---- palette ---------------------------------------------------------------------------------------------------------
NAVY = "#05142E"
BLUE = "#155DD3"
MID = "#6C9EF0"
PALE = "#BED4F9"
PAPER = "#F3F7FE"
INK2 = "#3C485C"
INK3 = "#5B6982"
GOLD = "#F2C14E"          # the seam — the one colour outside the interface palette, used only by the mark
GOLD_DEEP = "#D9A62B"     # the seam on white

# ---- the mark --------------------------------------------------------------------------------------------------------
SEAM = "M17 15 L31 29 L26 37 L47 49"


def mark_svg(*, bg: str | None, ring: str, seam: str, heavy: bool = False, size: int | None = None, radius: float = 15,
             inset: float = 0.0) -> str:
    """The mark on a 64-unit grid. `bg=None` draws no square (the gap then shows whatever is behind, so pass a
    background colour through `seam_gap` semantics: ring and seam only). `heavy` thickens strokes for tiny sizes.
    `inset` scales the drawing towards the centre (maskable icons keep the safe zone)."""
    rw, gap, sw, r = (8.0, 9.8, 4.4, 15.2) if heavy else (6.6, 8.6, 3.4, 16)
    k = 1 - inset
    t = f'transform="translate({32 * inset:.2f} {32 * inset:.2f}) scale({k:.4f})"' if inset else ""
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"' + (f' width="{size}" height="{size}"' if size else "") + ">"]
    if bg:
        parts.append(f'<rect width="64" height="64" rx="{radius}" fill="{bg}"/>')
    parts.append(f"<g {t}>")
    parts.append(f'<circle cx="32" cy="32" r="{r}" fill="none" stroke="{ring}" stroke-width="{rw}"/>')
    gapc = bg or "#000"
    if bg:
        parts.append(f'<path d="{SEAM}" fill="none" stroke="{gapc}" stroke-width="{gap}" stroke-linejoin="round" stroke-linecap="round"/>')
    else:
        # without a square the crack is a real hole: mask the ring where the seam passes
        parts[-1] = ""
        parts.append(
            '<mask id="crack" maskUnits="userSpaceOnUse" x="0" y="0" width="64" height="64">'
            '<rect width="64" height="64" fill="#fff"/>'
            f'<path d="{SEAM}" fill="none" stroke="#000" stroke-width="{gap}" stroke-linejoin="round" stroke-linecap="round"/>'
            "</mask>"
            f'<circle cx="32" cy="32" r="{r}" fill="none" stroke="{ring}" stroke-width="{rw}" mask="url(#crack)"/>'
        )
    parts.append(f'<path d="{SEAM}" fill="none" stroke="{seam}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"/>')
    parts.append("</g></svg>")
    return "".join(p for p in parts if p)


# ---- the wordmark (glyph outlines) -----------------------------------------------------------------------------------

def glyph_paths(font_path: Path, text: str, size: float, tracking_em: float = 0.04) -> tuple[str, float]:
    """SVG path data for `text` set in the font at `size` px, letter-spaced by `tracking_em` (like the UI's
    letter-spacing: 0.04em). Returns (path d, advance width)."""
    f = TTFont(str(font_path))
    upem = f["head"].unitsPerEm
    cmap = f.getBestCmap()
    glyphs = f.getGlyphSet()
    hmtx = f["hmtx"]
    scale = size / upem
    x = 0.0
    d = []
    for ch in text:
        gname = cmap.get(ord(ch))
        if gname is None:
            x += size * 0.3
            continue
        pen = SVGPathPen(glyphs)
        # font units are y-up; SVG is y-down: flip and shift by the cap height baseline (we place baseline at y=size)
        tp = TransformPen(pen, (scale, 0, 0, -scale, x, size * 0.78))
        glyphs[gname].draw(tp)
        d.append(pen.getCommands())
        x += hmtx[gname][0] * scale + tracking_em * size
    return " ".join(d), x - tracking_em * size


def wordmark_svg(color: str, size: float = 64, tagline: str | None = None, tag_color: str = INK3) -> tuple[str, float, float]:
    barlow = FONTS / "barlow-semi-condensed" / "files" / "barlow-semi-condensed-latin-700-normal.woff"
    d, w = glyph_paths(barlow, "KINTSUGI", size)
    h = size * 0.86
    body = f'<path d="{d}" fill="{color}"/>'
    if tagline:
        plex = FONTS / "ibm-plex-sans" / "files" / "ibm-plex-sans-latin-500-normal.woff"
        td, tw = glyph_paths(plex, tagline, size * 0.31, tracking_em=0.0)
        body += f'<g transform="translate(1 {size * 0.98:.1f})"><path d="{td}" fill="{tag_color}"/></g>'
        h = size * 0.98 + size * 0.31 * 0.9
        w = max(w, tw)
    return body, w, h


def svg_doc(inner: str, w: float, h: float, *, bg: str | None = None, pad: float = 0) -> str:
    W, H = w + 2 * pad, h + 2 * pad
    rect = f'<rect width="{W:.1f}" height="{H:.1f}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.1f} {H:.1f}" width="{W:.0f}" height="{H:.0f}">'
            f'{rect}<g transform="translate({pad} {pad})">{inner}</g></svg>')


def lockup_svg(*, horizontal: bool, ink: str, bg: str | None, square: str, ring: str, seam: str, tagline: bool, tag_color: str) -> str:
    size = 64
    wm, ww, wh = wordmark_svg(ink, size, "Photograph what broke. Print what fits." if tagline else None, tag_color)
    mk = mark_svg(bg=square, ring=ring, seam=seam)
    mk_inner = mk[mk.index(">") + 1 : -len("</svg>")]
    if horizontal:
        m = 60
        gap = 18
        y_word = (m - size * 0.62) / 2 - size * 0.16 if not tagline else 0
        inner = (f'<g transform="translate(0 {(wh - m) / 2 if tagline else 0:.1f}) scale({m / 64:.4f})">{mk_inner}</g>'
                 f'<g transform="translate({m + gap} {y_word:.1f})">{wm}</g>')
        return svg_doc(inner, m + gap + ww, max(m, wh), bg=bg, pad=24)
    m = 96
    inner = (f'<g transform="translate({(ww - m) / 2:.1f} 0) scale({m / 64:.4f})">{mk_inner}</g>'
             f'<g transform="translate(0 {m + 22})">{wm}</g>')
    return svg_doc(inner, ww, m + 22 + wh, bg=bg, pad=28)


# ---- raster ----------------------------------------------------------------------------------------------------------

async def rasterize(jobs: list[tuple[str, Path, int, int]]) -> None:
    """[(svg_text, out_png, width, height)] through Chromium, pixel-exact."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        b = await p.chromium.launch()
        for svg, out, w, h in jobs:
            pg = await b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            await pg.set_content(f'<html><body style="margin:0;background:transparent">{svg}</body></html>')
            await pg.wait_for_timeout(50)
            await pg.screenshot(path=str(out), omit_background=True, clip={"x": 0, "y": 0, "width": w, "height": h})
            await pg.close()
        await b.close()


def og_svg() -> str:
    """1200×630: navy, the drafting grid, the lockup and the promise."""
    wm, ww, wh = wordmark_svg(PAPER, 118)
    mk = mark_svg(bg=BLUE, ring=PAPER, seam=GOLD)
    mk_inner = mk[mk.index(">") + 1 : -len("</svg>")]
    plex = FONTS / "ibm-plex-sans" / "files" / "ibm-plex-sans-latin-400-normal.woff"
    t1, _ = glyph_paths(plex, "Photograph what broke. Print what fits.", 46, 0)
    t2, _ = glyph_paths(plex, "Phone photos in. A verified, printable replacement part out — every dimension measured on the mesh.", 22, 0)
    mono = FONTS / "ibm-plex-mono" / "files" / "ibm-plex-mono-latin-500-normal.woff"
    t3, _ = glyph_paths(mono, "kintsugi · OpenSCAD + BOSL2 · OpenAI Responses API · Hack47 OFFGRID", 20, 0)
    ta, taw = glyph_paths(mono, "3 photos", 24, 0)
    tb, tbw = glyph_paths(mono, "1 STL", 24, 0)
    arrow_w = 30
    tvw = taw + 14 + arrow_w + 14 + tbw
    grid = ('<defs><pattern id="g" width="30" height="30" patternUnits="userSpaceOnUse">'
            f'<path d="M30 0H0V30" fill="none" stroke="{PALE}" stroke-opacity="0.09" stroke-width="1"/></pattern></defs>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">{grid}'
            f'<rect width="1200" height="630" fill="{NAVY}"/><rect width="1200" height="630" fill="url(#g)"/>'
            f'<g transform="translate(96 116) scale(2.25)">{mk_inner}</g>'
            f'<g transform="translate(272 128)">{wm}</g>'
            f'<g transform="translate(96 300)"><path d="{t1}" fill="{PALE}"/></g>'
            f'<g transform="translate(96 372)"><path d="{t2}" fill="{MID}"/></g>'
            f'<line x1="96" y1="470" x2="1104" y2="470" stroke="{BLUE}" stroke-width="2"/>'
            f'<line x1="96" y1="458" x2="96" y2="482" stroke="{BLUE}" stroke-width="2"/>'
            f'<line x1="1104" y1="458" x2="1104" y2="482" stroke="{BLUE}" stroke-width="2"/>'
            f'<rect x="{600 - tvw / 2 - 14:.0f}" y="448" width="{tvw + 28:.0f}" height="44" fill="{NAVY}"/>'
            f'<g transform="translate({600 - tvw / 2:.0f} 458)"><path d="{ta}" fill="{MID}"/>'
            f'<path d="M{taw + 14:.0f} 11.5 h{arrow_w - 6} m-6 -5 l6 5 -6 5" fill="none" stroke="{MID}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<g transform="translate({taw + 14 + arrow_w + 14:.0f} 0)"><path d="{tb}" fill="{MID}"/></g></g>'
            f'<g transform="translate(96 536)"><path d="{t3}" fill="{INK3}"/></g>'
            "</svg>")


# ---- the brand sheet -------------------------------------------------------------------------------------------------

def brand_sheet(marks: dict[str, str]) -> str:
    css = (OUT / "kintsugi-brand.css").read_text(encoding="utf-8")
    swatches = [("Navy", NAVY, "ink, dark surfaces"), ("Blue", BLUE, "the one action colour; the mark's square"),
                ("Mid blue", MID, "dimensions, ghosted geometry, dark-mode action"), ("Pale blue", PALE, "tolerance bands, tints"),
                ("Paper", PAPER, "the workspace ground"), ("Seam gold", GOLD, "the mark's seam only")]
    sw = "".join(f'<div class="sw"><div class="chip" style="background:{h}"></div><b>{n}</b><code>{h}</code><span>{u}</span></div>' for n, h, u in swatches)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kintsugi brand</title>
<style>{css}
body{{margin:0;background:var(--paper);color:var(--navy);font-family:var(--font-body);line-height:1.5}}
main{{max-width:1080px;margin:0 auto;padding:40px 24px 80px}}
h1,h2,h3{{font-family:var(--font-head);font-weight:700;letter-spacing:.02em;margin:0}}
h1{{font-size:40px;text-transform:uppercase;letter-spacing:.04em}}
h2{{font-size:22px;margin-top:48px;padding-top:18px;border-top:1px solid #c9d6ec;text-transform:uppercase;letter-spacing:.06em}}
p{{max-width:64ch;color:#3c485c}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:18px;margin-top:18px}}
.card{{background:#fff;border:1px solid #c9d6ec;border-radius:6px;padding:18px;display:flex;flex-direction:column;gap:10px;align-items:flex-start}}
.card.dark{{background:var(--navy);color:var(--pale)}}
.card.blue{{background:var(--blue);color:var(--paper)}}
.card small{{font-family:var(--font-mono);font-size:11px;opacity:.75}}
.card>svg{{max-width:100%;height:auto}}
.sizes{{display:flex;gap:22px;align-items:flex-end}}
.sizes div{{display:flex;flex-direction:column;align-items:center;gap:6px;font-family:var(--font-mono);font-size:11px;color:#5b6982}}
.sw{{display:flex;flex-direction:column;gap:4px;font-size:13px}}
.sw .chip{{height:64px;border-radius:6px;border:1px solid rgba(5,20,46,.12)}}
.sw code{{font-family:var(--font-mono);font-size:12px}}
.type .sample{{margin:10px 0 2px}}
.type .h{{font-family:var(--font-head);font-weight:700;font-size:34px;letter-spacing:.02em}}
.type .b{{font-family:var(--font-body);font-size:16px}}
.type .m{{font-family:var(--font-mono);font-size:14px;font-variant-numeric:tabular-nums}}
.rule{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
.do,.dont{{padding:14px 16px;border-radius:6px;font-size:14px}}
.do{{background:#e8f4ec;color:#1c5a34}} .dont{{background:#fbe9e7;color:#8a2a22}}
ul{{margin:6px 0 0 18px;padding:0}}
.clear{{position:relative;display:inline-block;padding:32px;border:1px dashed #6c9ef0;border-radius:4px}}
.clear:after{{content:"clear space = the ring's width on every side";position:absolute;left:0;bottom:-22px;font:11px var(--font-mono);color:#5b6982;white-space:nowrap}}
</style></head><body><main>
<div style="display:flex;align-items:center;gap:18px;margin-bottom:8px"><div style="width:64px;height:64px">{marks['mark']}</div><h1>Kintsugi</h1></div>
<p><b>Photograph what broke. Print what fits.</b> The name is the Japanese craft of mending broken ceramics with gold: the break is not hidden, it becomes the strongest, most visible part. The mark says exactly that — a ring (the part; the neck ring of the hero demo), cracked on a diagonal, mended with a gold seam.</p>

<h2>The mark</h2>
<div class="grid">
  <div class="card blue"><div style="width:96px;height:96px">{marks['mark_bare']}</div><small>on blue · pale ring · gold seam (primary)</small></div>
  <div class="card dark"><div style="width:96px;height:96px">{marks['mark_navy_bare']}</div><small>on navy · pale ring · gold seam</small></div>
  <div class="card"><div style="width:96px;height:96px">{marks['mark_white_bg']}</div><small>on white · navy ring · deep gold</small></div>
  <div class="card"><div style="width:96px;height:96px">{marks['mark_mono']}</div><small>one colour (print, engraving, embossing)</small></div>
</div>
<p style="margin-top:18px">At 24 px and below the icon build is used: the same drawing with heavier strokes, so the seam still reads as a seam in a browser tab.</p>
<div class="sizes">{''.join(f'<div><div style="width:{s}px;height:{s}px">{marks["mark_heavy" if s <= 24 else "mark"]}</div>{s}</div>' for s in (16, 20, 24, 32, 48, 64, 96, 128))}</div>
<div style="margin-top:28px"><div class="clear"><div style="width:64px;height:64px">{marks['mark']}</div></div></div>

<h2>Lockups</h2>
<div class="grid">
  <div class="card" style="grid-column:span 2">{marks['lockup_h']}<small>horizontal — the default (README, headers, the deck)</small></div>
  <div class="card dark" style="grid-column:span 2">{marks['lockup_h_dark']}<small>horizontal on dark</small></div>
  <div class="card">{marks['lockup_stacked']}<small>stacked — square placements, the title slide</small></div>
  <div class="card" style="grid-column:span 2">{marks['lockup_tag']}<small>with the tagline — one line under the wordmark, IBM Plex Sans 500</small></div>
</div>
<p style="margin-top:14px">The wordmark is <b>Barlow Semi Condensed 700</b>, all caps, tracked +4 %. It is shipped as outlines in the SVGs, so nothing needs the font installed. Never retype it in another face, never set it in mixed case, never squeeze it.</p>

<h2>Colour</h2>
<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">{sw}</div>
<p style="margin-top:14px">The interface palette is the four blues; navy is the ink, blue is the single action colour, the two lighter blues are tints for tolerance bands and ghosted geometry. Gold exists only inside the mark (and, deliberately, as the tint of the <em>real object</em> ghosted in the 3D view — the thing the part is mended to).</p>

<h2>Type</h2>
<div class="type">
  <div class="sample h">Photograph what broke. Print what fits.</div><small style="font-family:var(--font-mono);color:#5b6982">Barlow Semi Condensed 600/700 — headings, stage names, the wordmark. Tracked, often uppercase.</small>
  <div class="sample b">Two or three phone photos become a verified, printable replacement: every dimension is measured on the designed mesh before you print.</div><small style="font-family:var(--font-mono);color:#5b6982">IBM Plex Sans 400/500/600 — everything people read.</small>
  <div class="sample m">neck_ring.inner_diameter 43.45 mm → 43.45 ±0.30 · pass</div><small style="font-family:var(--font-mono);color:#5b6982">IBM Plex Mono 400/500 — measured values, identifiers, code. Always tabular numerals.</small>
</div>
<p style="margin-top:14px">All three are open (SIL OFL) and ship with the app (<code>web/src/main.tsx</code> imports the latin subsets) and with this kit (<code>fonts/</code>). <code>kintsugi-brand.css</code> declares them plus the colour tokens for any HTML document.</p>

<h2>Use</h2>
<div class="rule">
  <div class="do"><b>Do</b><ul><li>use the blue square version on light and dark backgrounds alike; the square is part of the mark</li><li>keep clear space of one ring-width around it</li><li>use the icon build under 24 px</li><li>pair it with the horizontal lockup; stacked when the space is square</li><li>write the name as <b>Kintsugi</b> in text, KINTSUGI only in the wordmark</li></ul></div>
  <div class="dont"><b>Don't</b><ul><li>recolour the seam (it is gold or it is nothing — use the mono build)</li><li>rotate the seam, straighten it, or add a second crack</li><li>put the bare ring on a busy photo; use the square</li><li>stretch the wordmark or set it in another typeface</li><li>add a gradient, a shadow or an outline to the square</li></ul></div>
</div>

<h2>Files</h2>
<p><code>docs/brand/</code> holds the SVG sources (mark, wordmark, lockups in every colourway), PNG exports at 16–1024 px, the social image, the fonts and <code>kintsugi-brand.css</code>; <code>web/public/</code> holds what the app serves (favicon, PWA icons, manifest, Open Graph image). Everything is generated by <code>scripts/brand_assets.py</code> — change the drawing there, run it, commit.</p>
</main></body></html>"""


def brand_css() -> str:
    faces = []
    for fam, file, weight in [("Barlow Semi Condensed", "barlow-semi-condensed-latin-600-normal", 600),
                              ("Barlow Semi Condensed", "barlow-semi-condensed-latin-700-normal", 700),
                              ("IBM Plex Sans", "ibm-plex-sans-latin-400-normal", 400), ("IBM Plex Sans", "ibm-plex-sans-latin-500-normal", 500),
                              ("IBM Plex Sans", "ibm-plex-sans-latin-600-normal", 600),
                              ("IBM Plex Mono", "ibm-plex-mono-latin-400-normal", 400), ("IBM Plex Mono", "ibm-plex-mono-latin-500-normal", 500)]:
        faces.append(f"@font-face{{font-family:\"{fam}\";font-style:normal;font-weight:{weight};font-display:swap;"
                     f"src:url(fonts/{file}.woff2) format(\"woff2\"),url(fonts/{file}.woff) format(\"woff\")}}")
    return ("/* Kintsugi brand — fonts and colour tokens for any HTML document. Generated by scripts/brand_assets.py. */\n"
            + "\n".join(faces) + "\n"
            f":root{{--navy:{NAVY};--blue:{BLUE};--mid:{MID};--pale:{PALE};--paper:{PAPER};--seam:{GOLD};"
            "--font-head:\"Barlow Semi Condensed\",\"Arial Narrow\",sans-serif;--font-body:\"IBM Plex Sans\",system-ui,sans-serif;"
            "--font-mono:\"IBM Plex Mono\",ui-monospace,monospace}\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "png").mkdir(exist_ok=True)
    (OUT / "fonts").mkdir(exist_ok=True)
    PUB.mkdir(parents=True, exist_ok=True)

    # fonts + licences
    for fam, files in [("barlow-semi-condensed", ["barlow-semi-condensed-latin-600-normal", "barlow-semi-condensed-latin-700-normal"]),
                       ("ibm-plex-sans", ["ibm-plex-sans-latin-400-normal", "ibm-plex-sans-latin-500-normal", "ibm-plex-sans-latin-600-normal"]),
                       ("ibm-plex-mono", ["ibm-plex-mono-latin-400-normal", "ibm-plex-mono-latin-500-normal"])]:
        for f in files:
            for ext in ("woff2", "woff"):
                shutil.copy(FONTS / fam / "files" / f"{f}.{ext}", OUT / "fonts" / f"{f}.{ext}")
        lic = FONTS / fam / "LICENSE"
        if lic.exists():
            shutil.copy(lic, OUT / "fonts" / f"LICENSE-{fam}.txt")
    (OUT / "kintsugi-brand.css").write_text(brand_css(), encoding="utf-8")

    # marks
    marks = {
        "mark": mark_svg(bg=BLUE, ring=PAPER, seam=GOLD),
        "mark_heavy": mark_svg(bg=BLUE, ring=PAPER, seam=GOLD, heavy=True),
        "mark_navy": mark_svg(bg=NAVY, ring=PALE, seam=GOLD),
        "mark_white_bg": mark_svg(bg="#FFFFFF", ring=NAVY, seam=GOLD_DEEP),
        "mark_mono": mark_svg(bg=None, ring=NAVY, seam=NAVY),
        "mark_mono_white": mark_svg(bg=None, ring=PAPER, seam=PAPER),
        "mark_bare": mark_svg(bg=None, ring=PAPER, seam=GOLD),        # for use on the brand blue itself
        "mark_navy_bare": mark_svg(bg=None, ring=PALE, seam=GOLD),
        "mark_maskable": mark_svg(bg=BLUE, ring=PAPER, seam=GOLD, radius=0, inset=0.12),
    }
    for name, svg in marks.items():
        (OUT / f"kintsugi-{name.replace('_', '-')}.svg").write_text(svg, encoding="utf-8")

    # lockups
    lock = {
        "lockup_h": lockup_svg(horizontal=True, ink=NAVY, bg=None, square=BLUE, ring=PAPER, seam=GOLD, tagline=False, tag_color=INK3),
        "lockup_h_dark": lockup_svg(horizontal=True, ink=PAPER, bg=None, square=BLUE, ring=PAPER, seam=GOLD, tagline=False, tag_color=PALE),
        "lockup_tag": lockup_svg(horizontal=True, ink=NAVY, bg=None, square=BLUE, ring=PAPER, seam=GOLD, tagline=True, tag_color=INK2),
        "lockup_tag_dark": lockup_svg(horizontal=True, ink=PAPER, bg=None, square=BLUE, ring=PAPER, seam=GOLD, tagline=True, tag_color=PALE),
        "lockup_stacked": lockup_svg(horizontal=False, ink=NAVY, bg=None, square=BLUE, ring=PAPER, seam=GOLD, tagline=False, tag_color=INK3),
        "lockup_stacked_dark": lockup_svg(horizontal=False, ink=PAPER, bg=None, square=BLUE, ring=PAPER, seam=GOLD, tagline=False, tag_color=PALE),
    }
    for name, svg in lock.items():
        (OUT / f"kintsugi-{name.replace('_', '-')}.svg").write_text(svg, encoding="utf-8")
    wm, ww, wh = wordmark_svg(NAVY)
    (OUT / "kintsugi-wordmark.svg").write_text(svg_doc(wm, ww, wh, pad=8), encoding="utf-8")
    wm2, _, _ = wordmark_svg(PAPER)
    (OUT / "kintsugi-wordmark-white.svg").write_text(svg_doc(wm2, ww, wh, pad=8), encoding="utf-8")

    og = og_svg()
    (OUT / "kintsugi-og.svg").write_text(og, encoding="utf-8")

    # what the app serves
    (PUB / "favicon.svg").write_text(marks["mark_heavy"], encoding="utf-8")
    (PUB / "manifest.webmanifest").write_text(json.dumps({
        "name": "Kintsugi", "short_name": "Kintsugi", "description": "Photograph what broke. Print what fits.",
        "start_url": "/", "display": "standalone", "background_color": PAPER, "theme_color": NAVY,
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }, indent=2) + "\n", encoding="utf-8")

    # raster exports
    jobs: list[tuple[str, Path, int, int]] = []
    for s in (16, 32, 48):
        jobs.append((mark_svg(bg=BLUE, ring=PAPER, seam=GOLD, heavy=True, size=s), OUT / "png" / f"icon-{s}.png", s, s))
    for s in (64, 128, 256, 512, 1024):
        jobs.append((mark_svg(bg=BLUE, ring=PAPER, seam=GOLD, size=s), OUT / "png" / f"mark-{s}.png", s, s))
        jobs.append((mark_svg(bg=NAVY, ring=PALE, seam=GOLD, size=s), OUT / "png" / f"mark-navy-{s}.png", s, s))
    jobs.append((mark_svg(bg=BLUE, ring=PAPER, seam=GOLD, size=180), PUB / "apple-touch-icon.png", 180, 180))
    jobs.append((mark_svg(bg=BLUE, ring=PAPER, seam=GOLD, size=192), PUB / "icon-192.png", 192, 192))
    jobs.append((mark_svg(bg=BLUE, ring=PAPER, seam=GOLD, size=512), PUB / "icon-512.png", 512, 512))
    jobs.append((mark_svg(bg=BLUE, ring=PAPER, seam=GOLD, radius=0, inset=0.12, size=512), PUB / "icon-maskable-512.png", 512, 512))
    jobs.append((og, PUB / "og.png", 1200, 630))
    jobs.append((og, OUT / "png" / "kintsugi-og.png", 1200, 630))
    for name, svg in lock.items():
        w = float(svg.split('width="')[1].split('"')[0])
        h = float(svg.split('height="')[1].split('"')[0])
        scaled = svg.replace(f'width="{w:.0f}" height="{h:.0f}"', f'width="{w * 2:.0f}" height="{h * 2:.0f}"', 1)
        jobs.append((scaled, OUT / "png" / f"kintsugi-{name.replace('_', '-')}@2x.png", int(w * 2), int(h * 2)))
    asyncio.run(rasterize(jobs))

    # favicon.ico from the icon builds
    frames = [Image.open(OUT / "png" / f"icon-{s}.png").convert("RGBA") for s in (16, 32, 48)]
    frames[0].save(PUB / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)], append_images=frames[1:])
    shutil.copy(PUB / "favicon.ico", OUT / "png" / "favicon.ico")

    # the sheet
    (OUT / "index.html").write_text(brand_sheet({**marks, **lock}), encoding="utf-8")
    print(f"brand kit → {OUT.relative_to(ROOT)}  ·  app icons → {PUB.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
