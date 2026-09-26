"""A small knowledge graph of standard interfaces: named things whose mating dimensions are known before any photo.

When intake recognises the object ("wide-mouth Nalgene", "3/4 inch PVC", "M5 bolt", "18650 cell"), the matching
standard becomes an evidence node: a medium-confidence estimate (`source = "standard:<id>"`) for the dimensions it
fixes, plus a capture step to confirm it. Numbers are nominal catalogue values in millimetres; every entry carries
the confidence the estimate should get and a note on what varies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Standard:
    id: str
    family: str
    name: str
    keywords: tuple[str, ...]
    dims: dict[str, float]  # dimension role -> nominal mm
    note: str = ""
    conf: float = 0.55
    roles: dict[str, str] = field(default_factory=dict)  # dimension role -> which spec dim name it usually maps to

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "family": self.family, "name": self.name, "dims": self.dims, "note": self.note, "conf": self.conf,
                "roles": self.roles, "keywords": list(self.keywords)}


def _neck(id_, t, e, i, keywords, note="", conf=0.55):
    return Standard(id_, "bottle_neck", f"{id_.replace('neck_', '').replace('_', '-')} bottle neck finish", keywords,
                    {"thread_od": t, "root_od": e, "inner_diameter": i}, note or "SPI/GPI finish; T = thread OD, E = root OD, I = opening",
                    conf, {"thread_od": "outer_diameter", "inner_diameter": "inner_diameter"})


STANDARDS: list[Standard] = [
    # ---- bottle necks (SPI/GPI finishes; T/E/I nominal, ±0.4 mm across makers)
    _neck("neck_18_400", 17.9, 16.4, 12.0, ("18-400", "18mm neck", "dropper bottle")),
    _neck("neck_20_410", 19.7, 18.2, 14.0, ("20-410", "20mm neck")),
    _neck("neck_24_410", 23.5, 22.0, 17.0, ("24-410", "24mm neck", "lotion pump", "squeeze bottle")),
    _neck("neck_28_400", 27.5, 25.8, 20.0, ("28-400", "28mm neck", "soda bottle", "water bottle cap 28", "pet bottle")),
    _neck("neck_28_410", 27.5, 25.8, 20.0, ("28-410", "shampoo bottle")),
    _neck("neck_38_400", 37.6, 35.5, 30.0, ("38-400", "38mm neck", "narrow mouth nalgene", "narrow-mouth")),
    _neck("neck_38_430", 37.9, 35.9, 30.5, ("38-430", "nalgene narrow", "narrow mouth 1 l")),
    _neck("neck_43_400", 42.5, 40.4, 35.0, ("43-400", "43mm neck", "wide neck 43")),
    _neck("neck_53_400", 52.6, 50.5, 44.0, ("53-400", "53mm neck", "peanut butter jar")),
    _neck("neck_63_400", 62.6, 60.5, 54.0, ("63-400", "63mm neck")),
    _neck("neck_63_415", 62.6, 60.5, 54.0, ("63-415", "wide mouth nalgene", "wide-mouth nalgene", "nalgene wide", "wide mouth 1 l", "wide mouth 32 oz")),
    _neck("neck_70_400", 69.6, 67.5, 60.0, ("70-400", "70mm neck", "mason jar regular")),
    _neck("neck_89_400", 88.9, 86.6, 78.0, ("89-400", "89mm neck", "wide mouth mason", "wide-mouth mason")),
    # ---- pipes and tubes (outside diameters)
    Standard("pvc_sch40_1_2", "pipe", "1/2\" PVC schedule 40", ("1/2 inch pvc", "half inch pvc", "1/2\" pvc", "1/2 in pvc"),
             {"outer_diameter": 21.3, "inner_diameter": 15.8}, "NPS 1/2 OD is 0.840\"; sch 40 wall 2.8 mm", 0.7, {"outer_diameter": "outer_diameter"}),
    Standard("pvc_sch40_3_4", "pipe", "3/4\" PVC schedule 40", ("3/4 inch pvc", "3/4\" pvc", "three quarter pvc", "3/4 in pvc"),
             {"outer_diameter": 26.7, "inner_diameter": 20.9}, "NPS 3/4 OD is 1.050\"", 0.7, {"outer_diameter": "outer_diameter"}),
    Standard("pvc_sch40_1", "pipe", "1\" PVC schedule 40", ("1 inch pvc", "1\" pvc", "one inch pvc"),
             {"outer_diameter": 33.4, "inner_diameter": 26.6}, "NPS 1 OD is 1.315\"", 0.7, {"outer_diameter": "outer_diameter"}),
    Standard("pvc_sch40_1_1_4", "pipe", "1-1/4\" PVC schedule 40", ("1 1/4 inch pvc", "1-1/4\" pvc", "1.25 inch pvc"),
             {"outer_diameter": 42.2, "inner_diameter": 35.1}, "NPS 1-1/4 OD is 1.660\"", 0.7, {"outer_diameter": "outer_diameter"}),
    Standard("pvc_sch40_1_1_2", "pipe", "1-1/2\" PVC schedule 40", ("1 1/2 inch pvc", "1-1/2\" pvc", "1.5 inch pvc"),
             {"outer_diameter": 48.3, "inner_diameter": 40.9}, "NPS 1-1/2 OD is 1.900\"", 0.7, {"outer_diameter": "outer_diameter"}),
    Standard("pvc_sch40_2", "pipe", "2\" PVC schedule 40", ("2 inch pvc", "2\" pvc", "two inch pvc"),
             {"outer_diameter": 60.3, "inner_diameter": 52.5}, "NPS 2 OD is 2.375\"", 0.7, {"outer_diameter": "outer_diameter"}),
    Standard("copper_1_2", "pipe", "1/2\" copper tube (type L/M)", ("1/2 inch copper", "1/2\" copper", "half inch copper"),
             {"outer_diameter": 15.9}, "nominal 1/2\" copper is 5/8\" OD", 0.7, {"outer_diameter": "outer_diameter"}),
    Standard("copper_3_4", "pipe", "3/4\" copper tube (type L/M)", ("3/4 inch copper", "3/4\" copper"),
             {"outer_diameter": 22.2}, "nominal 3/4\" copper is 7/8\" OD", 0.7, {"outer_diameter": "outer_diameter"}),
    Standard("emt_1_2", "pipe", "1/2\" EMT conduit", ("1/2 emt", "half inch emt", "1/2 inch conduit"),
             {"outer_diameter": 17.9}, "EMT 1/2 OD 0.706\"", 0.65, {"outer_diameter": "outer_diameter"}),
    Standard("emt_3_4", "pipe", "3/4\" EMT conduit", ("3/4 emt", "3/4 inch conduit"),
             {"outer_diameter": 23.4}, "EMT 3/4 OD 0.922\"", 0.65, {"outer_diameter": "outer_diameter"}),
    Standard("garden_hose_ght", "thread", "garden hose thread (3/4-11.5 NH)", ("garden hose", "hose thread", "ght", "hose bib", "spigot"),
             {"outer_diameter": 26.9, "pitch": 2.209}, "male thread OD 1.0625\"; 11.5 threads per inch", 0.6, {"outer_diameter": "outer_diameter"}),
    # ---- shafts
    Standard("shaft_5_d_nema17", "shaft", "NEMA 17 stepper shaft (5 mm D)", ("nema 17", "nema17", "stepper motor shaft", "5mm d shaft", "5 mm d-shaft"),
             {"outer_diameter": 5.0, "flat_depth": 0.5, "across_flat": 4.5}, "D-cut shaft, flat 0.5 mm deep", 0.65, {"outer_diameter": "outer_diameter"}),
    Standard("shaft_6_d_pot", "shaft", "6 mm D-shaft (potentiometer / encoder)", ("potentiometer", "rotary encoder", "6mm d shaft", "6 mm d-shaft", "knob shaft", "volume knob"),
             {"outer_diameter": 6.0, "across_flat": 4.5}, "the flat depth varies (4.5 mm across the flat is common for pots; motors often 5.5)", 0.5,
             {"outer_diameter": "outer_diameter"}),
    Standard("shaft_6_35_quarter", "shaft", "1/4\" round shaft", ("1/4 inch shaft", "quarter inch shaft", "1/4\" shaft", "1/4 shaft"),
             {"outer_diameter": 6.35}, "", 0.7, {"outer_diameter": "outer_diameter"}),
    Standard("shaft_8_round", "shaft", "8 mm round shaft (3D printer smooth rod)", ("8mm rod", "8 mm rod", "8mm smooth rod", "lm8uu"),
             {"outer_diameter": 8.0}, "", 0.7, {"outer_diameter": "outer_diameter"}),
    # ---- fasteners (ISO metric)
    Standard("m3", "fastener", "M3 screw", ("m3",), {"major_diameter": 3.0, "clearance_hole": 3.4, "nut_across_flats": 5.5, "nut_height": 2.4, "sh_cap_head_d": 5.5},
             "clearance hole medium fit; DIN 934 nut", 0.75, {"major_diameter": "outer_diameter"}),
    Standard("m4", "fastener", "M4 screw", ("m4",), {"major_diameter": 4.0, "clearance_hole": 4.5, "nut_across_flats": 7.0, "nut_height": 3.2, "sh_cap_head_d": 7.0}, "", 0.75,
             {"major_diameter": "outer_diameter"}),
    Standard("m5", "fastener", "M5 screw", ("m5",), {"major_diameter": 5.0, "clearance_hole": 5.5, "nut_across_flats": 8.0, "nut_height": 4.0, "sh_cap_head_d": 8.5}, "", 0.75,
             {"major_diameter": "outer_diameter"}),
    Standard("m6", "fastener", "M6 screw", ("m6",), {"major_diameter": 6.0, "clearance_hole": 6.6, "nut_across_flats": 10.0, "nut_height": 5.0, "sh_cap_head_d": 10.0}, "", 0.75,
             {"major_diameter": "outer_diameter"}),
    Standard("m8", "fastener", "M8 screw", ("m8",), {"major_diameter": 8.0, "clearance_hole": 9.0, "nut_across_flats": 13.0, "nut_height": 6.5, "sh_cap_head_d": 13.0}, "", 0.75,
             {"major_diameter": "outer_diameter"}),
    Standard("m10", "fastener", "M10 screw", ("m10",), {"major_diameter": 10.0, "clearance_hole": 11.0, "nut_across_flats": 17.0, "nut_height": 8.0, "sh_cap_head_d": 16.0},
             "ISO 4032 nut is 16 mm AF; DIN 934 is 17 mm", 0.7, {"major_diameter": "outer_diameter"}),
    Standard("quarter_20", "fastener", "1/4-20 UNC (tripod / camera thread)", ("1/4-20", "1/4 20", "tripod thread", "tripod screw", "camera mount screw"),
             {"major_diameter": 6.35, "clearance_hole": 6.8, "pitch": 1.27}, "", 0.75, {"major_diameter": "outer_diameter"}),
    Standard("three_eighths_16", "fastener", "3/8-16 UNC (tripod head thread)", ("3/8-16", "3/8 16", "tripod head"),
             {"major_diameter": 9.525, "pitch": 1.588}, "", 0.75, {"major_diameter": "outer_diameter"}),
    # ---- batteries
    Standard("battery_aa", "battery", "AA cell", ("aa battery", "aa cell", "double a"), {"outer_diameter": 14.5, "length": 50.5}, "IEC R6", 0.8),
    Standard("battery_aaa", "battery", "AAA cell", ("aaa battery", "aaa cell", "triple a"), {"outer_diameter": 10.5, "length": 44.5}, "IEC R03", 0.8),
    Standard("battery_18650", "battery", "18650 li-ion cell", ("18650",), {"outer_diameter": 18.6, "length": 65.2}, "unprotected cell; protected cells are up to 70 mm", 0.75),
    Standard("battery_21700", "battery", "21700 li-ion cell", ("21700",), {"outer_diameter": 21.2, "length": 70.2}, "", 0.75),
    Standard("battery_cr2032", "battery", "CR2032 coin cell", ("cr2032", "coin cell"), {"outer_diameter": 20.0, "thickness": 3.2}, "", 0.8),
    Standard("battery_9v", "battery", "9 V (PP3)", ("9v battery", "9 volt", "pp3"), {"width": 26.5, "depth": 17.5, "height": 48.5}, "", 0.7),
    # ---- profiles, rails, hardware
    Standard("extrusion_2020", "profile", "2020 aluminium extrusion", ("2020 extrusion", "20x20 extrusion", "2020 aluminum", "t-slot 20"),
             {"width": 20.0, "slot_width": 6.0, "slot_depth": 6.0}, "6 mm T-slot; V-slot variants have a 45° chamfered slot", 0.7),
    Standard("extrusion_3030", "profile", "3030 aluminium extrusion", ("3030 extrusion", "30x30 extrusion"), {"width": 30.0, "slot_width": 8.0}, "", 0.7),
    Standard("extrusion_4040", "profile", "4040 aluminium extrusion", ("4040 extrusion", "40x40 extrusion"), {"width": 40.0, "slot_width": 8.0}, "", 0.7),
    Standard("pegboard_1_4", "panel", "1/4\" pegboard", ("pegboard",), {"hole_diameter": 7.1, "pitch": 25.4, "thickness": 6.0}, "holes 9/32\" on 1\" centres", 0.65),
    Standard("din_rail_35", "rail", "35 mm DIN rail", ("din rail",), {"width": 35.0, "depth": 7.5}, "TS35 / EN 60715", 0.75),
    Standard("gopro_mount", "mount", "GoPro two/three-finger mount", ("gopro", "go pro mount", "action camera mount"),
             {"finger_thickness": 3.0, "finger_gap": 3.35, "bolt": 5.0}, "M5 thumb-screw through 3 mm fingers", 0.55),
    Standard("picatinny", "rail", "Picatinny rail (MIL-STD-1913)", ("picatinny",), {"top_width": 21.2, "slot_width": 5.23, "slot_pitch": 10.01}, "", 0.7),
    Standard("skate_bearing_608", "bearing", "608 bearing", ("608 bearing", "skateboard bearing", "608zz", "fidget spinner bearing"),
             {"outer_diameter": 22.0, "inner_diameter": 8.0, "width": 7.0}, "", 0.85),
    Standard("bearing_625", "bearing", "625 bearing", ("625 bearing", "625zz"), {"outer_diameter": 16.0, "inner_diameter": 5.0, "width": 5.0}, "", 0.85),
    Standard("bearing_6001", "bearing", "6001 bearing", ("6001 bearing",), {"outer_diameter": 28.0, "inner_diameter": 12.0, "width": 8.0}, "", 0.85),
    # ---- bicycle
    Standard("seatpost_27_2", "bicycle", "27.2 mm seatpost", ("27.2 seatpost", "seatpost 27.2"), {"outer_diameter": 27.2}, "", 0.8, {"outer_diameter": "outer_diameter"}),
    Standard("seatpost_31_6", "bicycle", "31.6 mm seatpost", ("31.6 seatpost", "seatpost 31.6"), {"outer_diameter": 31.6}, "", 0.8, {"outer_diameter": "outer_diameter"}),
    Standard("handlebar_31_8", "bicycle", "31.8 mm handlebar clamp", ("31.8 handlebar", "oversize handlebar", "handlebar clamp"), {"outer_diameter": 31.8}, "", 0.7,
             {"outer_diameter": "outer_diameter"}),
    Standard("handlebar_22_2", "bicycle", "22.2 mm handlebar grip area", ("bike grip", "handlebar grip", "22.2 bar", "bar end"), {"outer_diameter": 22.2}, "MTB/flat bars; road bars are 23.8", 0.6,
             {"outer_diameter": "outer_diameter"}),
    Standard("steerer_1_1_8", "bicycle", "1-1/8\" steerer tube", ("1 1/8 steerer", "steerer tube", "headset spacer"), {"outer_diameter": 28.6}, "", 0.75, {"outer_diameter": "outer_diameter"}),
    Standard("bottle_cage_bolts", "bicycle", "bottle cage bosses", ("bottle cage", "water bottle cage"), {"bolt": 5.0, "pitch": 64.0}, "two M5 bolts 64 mm apart", 0.8),
    # ---- household
    Standard("broom_handle_1_1_8", "handle", "1-1/8\" broom / tool handle", ("broom handle", "mop handle", "tool handle", "rake handle"),
             {"outer_diameter": 28.6}, "handles run 15/16\" to 1-1/8\"; measure", 0.4, {"outer_diameter": "outer_diameter"}),
    Standard("shower_rod_1", "handle", "1\" shower / closet rod", ("shower rod", "closet rod", "curtain rod"), {"outer_diameter": 25.4}, "", 0.45, {"outer_diameter": "outer_diameter"}),
    Standard("wine_cork", "household", "wine bottle neck", ("wine bottle", "wine cork"), {"inner_diameter": 18.5, "outer_diameter": 29.5}, "cork-finish bore ~18.5 mm at the mouth", 0.55),
    Standard("mason_regular", "household", "regular-mouth mason jar", ("mason jar", "ball jar", "canning jar"), {"outer_diameter": 70.0}, "regular mouth ≈ 70 mm, wide mouth ≈ 86 mm", 0.5),
    Standard("usb_a_plug", "electronics", "USB-A plug shell", ("usb a", "usb-a", "usb stick", "flash drive"), {"width": 12.0, "height": 4.5}, "", 0.75),
    Standard("usb_c_plug", "electronics", "USB-C plug shell", ("usb c", "usb-c"), {"width": 8.34, "height": 2.56}, "", 0.75),
    Standard("hdmi_plug", "electronics", "HDMI type A plug", ("hdmi",), {"width": 13.9, "height": 4.45}, "", 0.7),
    Standard("rj45", "electronics", "RJ45 plug", ("rj45", "ethernet plug", "ethernet jack"), {"width": 11.7, "height": 8.0}, "without the latch", 0.7),
    Standard("audio_3_5", "electronics", "3.5 mm audio plug", ("3.5mm jack", "headphone jack", "aux plug"), {"outer_diameter": 3.5}, "", 0.85),
    Standard("led_5mm", "electronics", "5 mm LED", ("5mm led",), {"outer_diameter": 5.0, "flange": 5.8}, "", 0.85),
    Standard("led_3mm", "electronics", "3 mm LED", ("3mm led",), {"outer_diameter": 3.0, "flange": 3.8}, "", 0.85),
    Standard("wall_plate_us", "electrical", "US single-gang wall plate", ("light switch plate", "wall plate", "outlet cover", "single gang"),
             {"width": 70.0, "height": 114.3, "screw_pitch": 83.3}, "standard size 2.75\" × 4.5\"", 0.7),
]

_BY_ID = {s.id: s for s in STANDARDS}


def get_standard(id_: str) -> Standard | None:
    return _BY_ID.get(id_)


def _norm(text: str) -> str:
    t = text.lower().replace("’", "'").replace("″", "\"").replace("”", "\"")
    t = re.sub(r"\s+", " ", t)
    return t


def match_standards(text: str, limit: int = 6) -> list[Standard]:
    """Keyword match against the object description; longer keyword matches rank first."""
    t = _norm(text or "")
    if not t:
        return []
    hits: list[tuple[int, Standard]] = []
    for s in STANDARDS:
        best = 0
        for k in s.keywords:
            kk = _norm(k)
            # word-ish boundary: avoid "m3" matching inside "m30" or "aa" inside "aaa"
            if re.search(r"(?<![a-z0-9])" + re.escape(kk) + r"(?![a-z0-9])", t):
                best = max(best, len(kk))
        if best:
            hits.append((best, s))
    hits.sort(key=lambda x: (-x[0], x[1].id))
    return [s for _, s in hits[:limit]]


def hints_for_model(matches: list[Standard]) -> str:
    """A text block for the intake prompt."""
    if not matches:
        return ""
    lines = ["KNOWN STANDARDS that may apply (nominal mm). If the object is one of these, use its numbers as estimates with "
             "source \"standard:<id>\" and the given confidence, and add a capture step to confirm the mating dimension:"]
    for s in matches:
        dims = ", ".join(f"{k} {v:g}" for k, v in s.dims.items())
        lines.append(f"- {s.id}: {s.name} — {dims}" + (f" ({s.note})" if s.note else "") + f" [conf {s.conf:g}]")
    return "\n".join(lines)


def trust_for_source(source: str) -> int | None:
    """Standards are cited as `standard:<id>`; they sit between a vision guess and a reference-object measurement."""
    if source.startswith("standard:"):
        return 25
    return None
