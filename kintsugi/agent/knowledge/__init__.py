"""OpenSCAD knowledge for the designer: curated guides, a reference of the language builtins, and an index of the
vendored BOSL2 library parsed from its own doc comments. Exposed to the model as the `scad_guide` and `scad_docs`
tools and to people as `kin guide` / `kin docs`.

Everything here is checked against what actually ships: OpenSCAD 2021.01 and the vendored BOSL2 (`BOSL_VERSION`);
every ```scad example in the guides is compiled by the test-suite.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from kintsugi import VENDOR_DIR

KNOWLEDGE_DIR = Path(__file__).resolve().parent
GUIDES_DIR = KNOWLEDGE_DIR / "guides"
BUILTINS_PATH = KNOWLEDGE_DIR / "openscad_builtins.json"

GUIDE_TOPICS: dict[str, str] = {
    "essentials": "OpenSCAD 2021.01 language essentials, scope rules, $fn, precision, what is and is not available",
    "shapes": "building shapes: 2D profiles → 3D, offset/hull/minkowski rounding, chamfers, fillets, teardrops, extrusions",
    "bosl2": "the vendored BOSL2 library: includes, anchors and attachments, rounded primitives, masks, threads, screws, joiners",
    "fdm": "design for FDM printing: walls, clearances by fit and material, overhangs, bridges, holes, orientation, snap fits",
    "kintsugi": "Kintsugi conventions: customizer syntax, render_target/part/coupon/assembly, the coordinate frame, clearance, measure recipes",
    "patterns": "worked, compiling snippets for common repair parts: rings and loops, clips, D-shaft bores, hole patterns, nut traps, plugs, caps",
    "errors": "compile errors and warnings you will meet, what they mean, and the fix",
}


# ---- guides -------------------------------------------------------------------------------------------

def guide_topics() -> list[tuple[str, str]]:
    return [(k, v) for k, v in GUIDE_TOPICS.items() if (GUIDES_DIR / f"{k}.md").exists()]


def guide(topic: str) -> str | None:
    t = (topic or "").strip().lower().replace(" ", "-")
    aliases = {"language": "essentials", "basics": "essentials", "syntax": "essentials", "rounding": "shapes", "fillets": "shapes",
               "2d": "shapes", "extrude": "shapes", "printing": "fdm", "print": "fdm", "tolerances": "fdm", "clearance": "fdm",
               "customizer": "kintsugi", "conventions": "kintsugi", "idioms": "patterns", "examples": "patterns", "snippets": "patterns",
               "warnings": "errors", "troubleshooting": "errors", "bosl": "bosl2", "attachments": "bosl2", "threads": "bosl2"}
    t = aliases.get(t, t)
    p = GUIDES_DIR / f"{t}.md"
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def guide_examples(topic: str) -> list[tuple[str, str]]:
    """(label, source) for every ```scad block in a guide — the tests compile all of them."""
    text = guide(topic) or ""
    out = []
    for i, m in enumerate(re.finditer(r"```scad([^\n]*)\n(.*?)```", text, re.S)):
        out.append((f"{topic}#{i + 1}{m.group(1).strip()}", m.group(2)))
    return out


# ---- reference entries --------------------------------------------------------------------------------

@dataclass
class Entry:
    name: str
    kind: str  # module | function | function&module | constant | statement | variable
    source: str  # "openscad" | a BOSL2 file name
    synopsis: str = ""
    usage: list[str] = field(default_factory=list)
    description: str = ""
    arguments: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    see_also: list[str] = field(default_factory=list)
    includes: str = ""
    notes: str = ""

    def render(self, full: bool = False, max_chars: int = 2200) -> str:
        head = f"{self.name}  [{self.kind}, {self.source}]"
        lines = [head]
        if self.synopsis:
            lines.append(f"  {self.synopsis}")
        if self.includes:
            lines.append(f"  include: {self.includes}")
        for u in self.usage[: (8 if full else 3)]:
            lines.append(f"  usage: {u}")
        if self.description:
            desc = self.description if full else self.description[:500] + ("…" if len(self.description) > 500 else "")
            lines.append("  " + desc.replace("\n", "\n  "))
        args = self.arguments if full else self.arguments[:10]
        for a in args:
            lines.append(f"    - {a}")
        if len(self.arguments) > len(args):
            lines.append(f"    - … {len(self.arguments) - len(args)} more arguments (ask with full=true)")
        if self.notes:
            lines.append("  note: " + self.notes)
        for ex in self.examples[: (3 if full else 1)]:
            lines.append("  example:\n    " + ex.strip().replace("\n", "\n    "))
        if self.see_also:
            lines.append("  see also: " + ", ".join(self.see_also[:8]))
        text = "\n".join(lines)
        return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


@lru_cache(maxsize=1)
def builtin_index() -> list[Entry]:
    data = json.loads(BUILTINS_PATH.read_text(encoding="utf-8"))
    out = []
    for d in data:
        out.append(Entry(name=d["name"], kind=d.get("kind", "module"), source="openscad", synopsis=d.get("synopsis", ""),
                         usage=list(d.get("usage", [])), description=d.get("description", ""), arguments=list(d.get("arguments", [])),
                         examples=list(d.get("examples", [])), topics=list(d.get("topics", [])), see_also=list(d.get("see_also", [])),
                         notes=d.get("notes", "")))
    return out


_HEADER = re.compile(r"^// (Module|Function|Function&Module|Constant|Module&Function): ([^\n]+)$")
_KEY = re.compile(r"^// ([A-Za-z ]+?)(?:\(([^)]*)\))?: ?(.*)$")


@lru_cache(maxsize=1)
def bosl2_index() -> list[Entry]:
    """Parse the vendored BOSL2 sources' structured doc comments into entries."""
    root = VENDOR_DIR / "BOSL2"
    out: list[Entry] = []
    if not root.exists():
        return out
    for path in sorted(root.glob("*.scad")):
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        includes = ""
        m_inc = re.search(r"^// Includes:\n((?://   .*\n)+)", text, re.M)
        if m_inc:
            includes = " + ".join(x.strip("/ ").strip() for x in m_inc.group(1).splitlines())
        i = 0
        while i < len(lines):
            m = _HEADER.match(lines[i])
            if not m:
                i += 1
                continue
            kind = m.group(1).lower()
            name = m.group(2).strip().rstrip("()")
            e = Entry(name=name, kind=kind, source=path.name, includes=includes)
            i += 1
            key = None
            buf: list[str] = []

            def flush():
                nonlocal buf, key
                if key is None:
                    return
                body = "\n".join(buf).strip()
                if key == "synopsis":
                    e.synopsis = body
                elif key == "usage":
                    e.usage.extend([b.strip() for b in body.splitlines() if b.strip()])
                elif key == "description":
                    body = "\n".join("" if ln.strip() == "." else ln for ln in body.splitlines())
                    e.description = (e.description + "\n" + body).strip()
                elif key == "arguments":
                    e.arguments.extend([b.strip() for b in body.splitlines() if b.strip() and b.strip() != "---"])
                elif key.startswith("example"):
                    if body:
                        e.examples.append(body)
                elif key == "topics":
                    e.topics = [t.strip() for t in body.split(",") if t.strip()]
                elif key == "see also":
                    e.see_also = [t.strip() for t in body.split(",") if t.strip()]
                buf = []
                key = None

            while i < len(lines) and lines[i].startswith("//"):
                line = lines[i]
                if _HEADER.match(line) or line.startswith("// Section:") or line.startswith("// Subsection:"):
                    break
                km = _KEY.match(line)
                if km and not line.startswith("//   ") and km.group(1).strip().lower() in (
                    "synopsis", "usage", "description", "arguments", "example", "examples", "topics", "see also", "syntags",
                    "figure", "continues", "side effects", "anchor types", "named anchors", "extra anchors", "context variables"):
                    flush()
                    k = km.group(1).strip().lower()
                    if k in ("example", "examples", "figure"):
                        key = "example"
                        # an example's title text after the colon is not code
                        buf = []
                    else:
                        key = k
                        rest = km.group(3).strip()
                        buf = [rest] if rest and k != "usage" else []  # a "Usage: <title>" line is a heading, not code
                elif line.startswith("//   ") and key is not None:
                    buf.append(line[5:])
                elif line.strip() == "//" and key is not None:
                    buf.append("")
                i += 1
            flush()
            if not e.synopsis and e.description:
                e.synopsis = e.description.split("\n")[0][:160]
            out.append(e)
    return out


@lru_cache(maxsize=1)
def all_entries() -> list[Entry]:
    return builtin_index() + bosl2_index()


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9_]+", s.lower()) if t]


def search(query: str, limit: int = 5, source: str | None = None) -> list[Entry]:
    """Rank reference entries for a query: exact name, name containment, then token overlap with synopsis/topics/description."""
    q = (query or "").strip()
    if not q:
        return []
    qname = q.lower().rstrip("()")
    toks = _tokens(q)
    scored: list[tuple[float, Entry]] = []
    for e in all_entries():
        if source and not (e.source == source or (source == "bosl2" and e.source.endswith(".scad")) or (source == "openscad" and e.source == "openscad")):
            continue
        n = e.name.lower()
        score = 0.0
        if n == qname:
            score += 100 + (25 if e.source == "openscad" else 0)  # the builtin outranks a same-named library function
        elif n.startswith(qname) or qname.startswith(n) and len(n) > 3:
            score += 40
        elif qname in n:
            score += 25
        hay_syn = e.synopsis.lower()
        hay_top = " ".join(e.topics).lower()
        hay_desc = e.description.lower()[:1200]
        hay_args = " ".join(e.arguments).lower()
        for t in toks:
            if t == n:
                score += 30
            elif t in n:
                score += 8
            if t in hay_syn:
                score += 6
            if t in hay_top:
                score += 4
            if t in hay_args:
                score += 2
            if t in hay_desc:
                score += 1.5
        if score > 0:
            if e.source == "openscad":
                score += 3  # builtins first on ties
            scored.append((score, e))
    scored.sort(key=lambda x: (-x[0], x[1].name))
    return [e for _, e in scored[:limit]]


GUIDE_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("round", "rounding", "fillet", "chamfer", "corner", "edge", "hull", "minkowski", "extrude", "revolve", "profile", "teardrop", "taper"), "shapes"),
    (("clearance", "tolerance", "fit", "wall", "overhang", "bridge", "orientation", "snap", "flex", "insert", "print", "layer", "petg", "pla", "strength"), "fdm"),
    (("customizer", "slider", "render_target", "coupon", "assembly", "frame", "origin", "recipe", "at_z", "check", "measure"), "kintsugi"),
    (("pattern", "holes", "hole pattern", "clip", "ring", "loop", "knob", "cap", "plug", "hook", "bracket", "nut trap", "countersink", "spacer", "bushing"), "patterns"),
    (("error", "warning", "manifold", "empty", "assertion", "unknown", "syntax", "recursion", "timeout"), "errors"),
    (("attach", "anchor", "bosl", "tag", "diff", "mask", "thread", "screw", "gear", "hinge", "sweep", "position"), "bosl2"),
    (("variable", "scope", "let", "list", "comprehension", "function", "module", "range", "$fn", "facet", "syntax"), "essentials"),
]


def guide_hint(query: str) -> str | None:
    q = " " + (query or "").lower() + " "
    for words, topic in GUIDE_HINTS:
        if any(" " + w + " " in q or q.strip().startswith(w) for w in words):
            return topic
    return None


def lookup(name: str) -> Entry | None:
    n = (name or "").strip().lower().rstrip("()")
    for e in all_entries():
        if e.name.lower() == n:
            return e
    return None


def docs_answer(query: str, *, name: str | None = None, full: bool = False, limit: int = 5) -> str:
    """The `scad_docs` tool body: an exact entry (name) or the best matches for a query."""
    if name:
        e = lookup(name)
        if e is None:
            hits = search(name, limit=limit)
            if not hits:
                return f"No entry named {name!r}. Try a shorter word, or scad_guide('bosl2') / scad_guide('essentials')."
            return f"No exact entry named {name!r}; closest:\n\n" + "\n\n".join(h.render(full=False) for h in hits)
        return e.render(full=True)
    hits = search(query, limit=limit)
    hint = guide_hint(query)
    if not hits:
        return (f"Nothing matched {query!r} in the reference." + (f" The `{hint}` guide covers this: scad_guide(\"{hint}\")." if hint else
                " The guides cover the language, shapes, BOSL2, FDM and patterns: scad_guide(topic)."))
    head = f"{len(hits)} match(es) for {query!r} (OpenSCAD 2021.01 + BOSL2 {bosl_version_str()}):"
    if hint and len(_tokens(query)) >= 2:
        head += f"\n(for the technique rather than a single call, scad_guide(\"{hint}\") has worked examples)"
    return head + "\n\n" + "\n\n".join(h.render(full=full and len(hits) == 1) for h in hits)


@lru_cache(maxsize=1)
def bosl_version_str() -> str:
    p = VENDOR_DIR / "BOSL2" / "version.scad"
    try:
        m = re.search(r"BOSL_VERSION\s*=\s*\[(\d+),\s*(\d+),\s*(\d+)\]", p.read_text(encoding="utf-8"))
        return ".".join(m.groups()) if m else "?"
    except OSError:
        return "?"


def summary_for_prompt() -> str:
    """A short block for the designer's system prompt: what the knowledge tools offer."""
    topics = ", ".join(f"`{k}`" for k, _ in guide_topics())
    return (f"- `scad_guide(topic)` — curated guides for OpenSCAD 2021.01 and the vendored BOSL2 ({bosl_version_str()}); topics: {topics}. "
            f"Read `patterns` before modelling a part class you have not built before, `shapes` for rounding/fillets, `fdm` for clearances.\n"
            f"- `scad_docs(query)` — the reference: every OpenSCAD builtin and every BOSL2 module/function with usage, arguments and an example, "
            f"searched by name or words (`scad_docs(name=\"cuboid\")` for the full entry). Use it before calling any BOSL2 module you are not certain about.")


def to_json(entries: list[Entry]) -> list[dict[str, Any]]:
    return [e.__dict__ for e in entries]
