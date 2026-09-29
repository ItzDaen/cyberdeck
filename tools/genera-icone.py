#!/usr/bin/env python3
"""
genera-icone.py — Recolours an icon theme into the Meridiano monochrome.

Why recolour instead of drawing
--------------------------------
A system icon set covers thousands of names: applications, actions,
states, mimetypes. That is not work you do by hand. But a monochrome
set is by definition a *transformation* of an already drawn set: same
shapes, one colour. The transformation is mechanical, so it is done once
and made explicit.

The choice of colour
--------------------
One colour for everything: the scheme's warm text colour (#e8e4dc). Not
a ramp of greys, not two tones to tell elements apart. In a set of
instruments colour carries no information; the shape does. Amber stays
reserved for what is data — the telemetry panel, the title bar — and does
not appear in icons. If an icon said "this thing is on" through its
colour, colour would become part of the language and would stop being an
accent.

Which contexts are covered
--------------------------
Applications are deliberately not covered. A theme that supplies app
icons replaces every program's mark with a grey drawing, and the user can
no longer tell Firefox from a text editor. Identity is data, not
decoration. This theme keeps only the interface: actions, status,
devices, places, mimetypes, emblems.

The ColorScheme classes
-----------------------
The sources already use KDE's mechanism: `class="ColorScheme-Text"` with
`fill="currentColor"`. The classes are left in place and only the colour
they declare is changed, so the theme stays readable and the colour for
a single class can be reopened later.

Usage:
    python3 tools/genera-icone.py [--da Fluent] [--a ~/.local/share/icons/Meridiano]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import sys

# The colours of the Meridiano scheme. This theme has only one: the warm
# text colour. Every role becomes that.
# The monochrome ramp.
#
# The first version moved *every* colour to a single value, and the
# result was worse than having colours at all: icons that depend on
# internal contrast to be legible became blank white blobs, and the
# Windows logo stayed blue because its blue lived in a gradient the
# rewrite did not see.
#
# A monochrome set is not flattened. The *value* of each source colour
# is mapped onto a ramp of a single colour. The shape survives because
# every tone stays distinguishable, and the result is what an
# instrument looks like: one colour whose luminosity is all that varies.
#
# On the range: the ramp goes from dim grey to full text. On a
# dark background the high end must be near white and the low end must
# stay legible, so the two extremes are not 0% and 100%.
SPENTO = (0x8a, 0x85, 0x7c)     # #8a857c — the grey of resting glyphs
PIENO = (0xe8, 0xe4, 0xdc)      # #e8e4dc — the scheme's warm text


def luminanza(hexcolore: str) -> float:
    """Perceived luminosity of a hex colour, from 0 to 1."""
    c = hexcolore.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) < 6:
        return 0.5
    try:
        r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return 0.5
    # the canonical weighting: human vision does not perceive green the
    # way it perceives the other two channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def sulla_rampa(esadecimale: str) -> str:
    """Move a colour onto the monochrome ramp, keeping its value."""
    L = luminanza(esadecimale)
    canali = [round(a + (b - a) * L) for a, b in zip(SPENTO, PIENO)]
    return "#%02x%02x%02x" % tuple(canali)


# The places a colour can appear in an SVG: attribute, inline style, and
# stylesheet rule. The first attempt only looked at the first, and
# leaving the others alone left icons in colour.
_COLORI_ATTR = re.compile(
    r'(\b(?:fill|stroke|stop-color|flood-color|lighting-color|color)\s*=\s*")'
    r'(#[0-9a-fA-F]{3,8}|[a-zA-Z]+\([^)]*\)|[a-zA-Z]{3,20})(")')
_COLORI_STILE = re.compile(
    r'((?:^|[;{\s])(?:fill|stroke|stop-color|color)\s*:\s*)'
    r'(#[0-9a-fA-F]{3,8}|[a-zA-Z]+\([^)]*\)|[a-zA-Z]{3,20})')

_DA_TENERE = {
    "none", "transparent", "currentColor", "inherit",
    "context-fill", "context-stroke", "unset",
}

# Named colours. The first attempt ignored them: `fill="gray"` was left
# untouched and produced a grey icon amid a set with no greys in it.
NOMINATI = {
    "black": "#000000", "silver": "#c0c0c0", "gray": "#808080",
    "grey": "#808080", "white": "#ffffff", "maroon": "#800000",
    "red": "#ff0000", "purple": "#800080", "fuchsia": "#ff00ff",
    "magenta": "#ff00ff", "green": "#008000", "lime": "#00ff00",
    "olive": "#808000", "yellow": "#ffff00", "navy": "#000080",
    "blue": "#0000ff", "teal": "#008080", "aqua": "#00ffff",
    "cyan": "#00ffff", "orange": "#ffa500", "darkgray": "#a9a9a9",
    "darkgrey": "#a9a9a9", "lightgray": "#d3d3d3",
    "lightgrey": "#d3d3d3", "dimgray": "#696969", "gainsboro": "#dcdcdc",
}


def _pulito(valore: str) -> bool:
    v = valore.strip()
    return (v in _DA_TENERE or v.startswith("url(")
            or v.startswith("var(") or v.lower() not in NOMINATI
            and not v.startswith("#") and "(" not in v)


# Embedded images.
#
# Many icons are not pure vector: they contain a base64 PNG inside the
# SVG. No attribute touches those, and the result was the Windows logo
# still blue in the middle of a theme with no blue in it. No textual rule
# reaches them: the file has to be opened, the pixels moved onto the
# ramp, and the PNG rebuilt.
_IMMAGINE = re.compile(
    r'(xlink:href|href)="data:image/png;base64,([A-Za-z0-9+/=\s]+)"')


def _rampa_immagine(dati: bytes) -> bytes | None:
    """Move a PNG onto the ramp, channel by channel."""
    try:
        import base64
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(dati)).convert("RGBA")
    except Exception:
        return None
    px = img.load()
    W, H = img.size
    for y in range(H):
        for x in range(W):
            r, g, b, a = px[x, y]
            L = 0.2126 * (r / 255) + 0.7152 * (g / 255) + 0.0722 * (b / 255)
            px[x, y] = tuple(round(u + (v - u) * L) for u, v in zip(SPENTO, PIENO)) + (a,)
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _colore(valore: str) -> str:
    """The hex name of a colour, whether given as a name or as hex."""
    v = valore.strip()
    if v.startswith("#"):
        return v
    return NOMINATI.get(v.lower(), v)


# The plate of a device avatar, and the rule that puts one where it belongs.
#
# Adwaita's `audio-headset` and eight of its siblings are a filled circle
# with a white glyph on it. Flattened onto the ramp, the circle landed at
# #b7b2aa and the glyph at #e8e4dc: a contrast ratio of 1.66. In the popup
# that read as an empty beige disc, because a glyph at 1.66 against its
# own plate is not a glyph.
#
# Darkening the ramp does not fix it, and it is worth writing down why so
# that nobody tries again: sulla_rampa() maps a colour's LUMINANCE, and
# the source plate and the source glyph are 0.35 apart in luminance, so
# the best case over any ramp is 2.33:1. Contrast that is not in the
# source cannot be mapped into existence. It has to be put there.
#
# So the plate is set, not mapped: a lifted dark, dark enough for the
# glyph to read on it and light enough to read as a chip against the
# popup. Against the popup #1b2531 that is 2.4:1, and against the glyph
# 7.5:1. Both are worth having, and the glyph is the one that matters.
PIATTO = (0x4a, 0x46, 0x3f)   # #4a463f


def sistema_piatto(testo: str) -> tuple[str, int]:
    """Give a filled-disc avatar a plate the glyph can sit on.

    Detected, not listed, and the two conditions are both needed. Radius
    alone is not enough: `drive-removable-media` carries a circle at
    cx=47 cy=47 r=16 which is the badge on the stick, not a plate, and
    flattening it to a dark dot took the highlight off the icon. A plate
    is a circle that is big AND centred: r >= 14 within four units of the
    canvas centre on both axes.
    """
    import re as _re

    m = _re.search(r'<circle[^>]*\bcx="([0-9.]+)"[^>]*\bcy="([0-9.]+)"'
                   r'[^>]*\br="([0-9.]+)"[^>]*>', testo)
    if not m:
        return testo, 0
    cx, cy, r = (float(m.group(i)) for i in (1, 2, 3))
    if r < 14 or abs(cx - 32) > 4 or abs(cy - 32) > 4:
        return testo, 0

    nuovo, n = _re.subn(r'(<circle[^>]*>)',
                        lambda mm: _re.sub(r'fill="[^"]*"',
                                            'fill="#%02x%02x%02x"' % PIATTO,
                                            mm.group(1)),
                        testo, count=1)
    return nuovo, n


def appiattisci(testo: str) -> tuple[str, int]:
    """Move every colour onto the ramp. Returns the text and how many changed."""
    import base64
    cambiati = 0

    def attr(m: re.Match) -> str:
        nonlocal cambiati
        grezzo = m.group(2)
        if _pulito(grezzo):
            return m.group(0)
        cambiati += 1
        return m.group(1) + sulla_rampa(_colore(grezzo)) + m.group(3)

    def stile(m: re.Match) -> str:
        nonlocal cambiati
        grezzo = m.group(2)
        if _pulito(grezzo):
            return m.group(0)
        cambiati += 1
        return m.group(1) + sulla_rampa(_colore(grezzo))

    def immagine(m: re.Match) -> str:
        nonlocal cambiati
        try:
            dati = base64.b64decode(re.sub(r"\s", "", m.group(2)))
        except Exception:
            return m.group(0)
        nuovi = _rampa_immagine(dati)
        if nuovi is None:
            return m.group(0)
        cambiati += 1
        testo = base64.b64encode(nuovi).decode("ascii")
        # the re-encoded base64 is longer: the XML accepts it, but only
        # with no spaces, otherwise some parsers notice
        return f'{m.group(1)}="data:image/png;base64,{testo}"'

    testo = _COLORI_ATTR.sub(attr, testo)
    testo = _COLORI_STILE.sub(stile, testo)
    testo = _IMMAGINE.sub(immagine, testo)
    testo, piatti = sistema_piatto(testo)
    cambiati += piatti
    return testo, cambiati


# The per-context sections. `Directories` lists only the directories that
# really exist: declaring a missing one makes the theme malformed and the
# engine refuses to load it. The first version declared `preferences`,
# `other` and `categories`, which the source theme does not have, and
# used lower-case names while the directories are capitalised.
SEZIONI = {
    "Apps":       ("Applications", 48),
    "Actions":    ("Actions", 48),
    "Status":     ("Status", 48),
    "Places":     ("Places", 48),
    "Devices":    ("Devices", 48),
    "Mimetypes":  ("MimeTypes", 48),
    "Emblems":    ("Emblems", 48),
    "Categories": ("Categories", 48),
    "Preferences": ("Preferences", 48),
    "Other":      ("Other", 48),
}


def griglia_tasti() -> str:
    """The start icon: a Braun-style key grid.

    Not a redrawing, a replacement. Every `start-here*` name in the
    source themes is the four-pane Windows flag, and the generator only
    moves colours onto the ramp, so what came through was a recoloured
    Windows logo: four quadrants, unmistakable, in a theme whose whole
    argument is that a desktop is not Windows. Recolouring a foreign
    brand is not the same as not carrying it.

    The mark is a 3x3 grid of rounded keys on a 32 unit canvas, with
    the first key in the theme's amber and the rest in the mid ink. That
    is the Braun reference -- the key arrays on the ET66, the AB and the
    T3 -- and it is the same argument the whole theme makes: an
    instrument panel is a set of keys, not a logo.

    Plain and symbolic are drawn identically, and they were identical
    before this too: the theme is monochrome throughout, so there is no
    second rendering to choose between.
    """
    CHIAVE = 8
    PASSO = 2
    RAGGIO = 1.6
    INCHIOSTRO = "#b6b2a9"
    ACCENTO = "#ff9d2e"

    chiavi = []
    for riga in range(3):
        for colonna in range(3):
            x = 2 + colonna * (CHIAVE + PASSO)
            y = 2 + riga * (CHIAVE + PASSO)
            tinta = ACCENTO if (riga, colonna) == (0, 0) else INCHIOSTRO
            chiavi.append(
                f'    <rect x="{x}" y="{y}" width="{CHIAVE}" '
                f'height="{CHIAVE}" rx="{RAGGIO}" fill="{tinta}"/>'
            )

    corpo = "\n".join(chiavi)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" \
viewBox="0 0 32 32">
  <!--
    Meridiano start icon: a 3x3 key grid. Generated by
    tools/genera-icone.py; every start-here* name is drawn here rather
    than recoloured from the source theme, which carries the Windows
    flag under all of them. Do not edit by hand: re-running the
    generator overwrites this file.
  -->
{corpo}
</svg>
"""


# Which files get drawn rather than inherited.
#
# A pattern, not a list of names. The first version of this listed five
# names and missed `start-here-kde.svg`, which lives in Places rather than
# Status, so the Windows flag survived under one of the two names the
# kickoff actually asks for: read back out of the plugin with
# `strings -e l`, it wants `start-here-kde` and `start-here-kde-symbolic`,
# and only the second one was covered.
#
# Listing names is how that happened, and the list was already wrong the
# first time it ran. A name added upstream later would have failed the
# same way, silently, with nothing to notice it: the icon would simply
# come back as Windows. Matching the family instead means a name this
# file has never heard of is covered the day it appears.
NOMI_START = "start-here*.svg"


def indice(presenti: list[str], nome: str, eredita: str) -> str:
    parti = ["[Icon Theme]",
             f"Name={nome}",
             "Comment=Monochrome Meridiano icon theme",
             f"Inherits={eredita}",
             "Example=folder",
             "",
             "Directories=" + ",".join(f"scalable/{d}" for d in presenti)]
    for d in presenti:
        contesto, dim = SEZIONI.get(d, ("Other", 48))
        parti += ["", f"[scalable/{d}]",
                  f"Size={dim}", "MinSize=16", "MaxSize=512",
                  f"Context={contesto}", "Type=Scalable"]
    return "\n".join(parti) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--da", default="Fluent")
    ap.add_argument("--a", default=None)
    # The order matters: lookup goes left to right, and what comes first
    # is where the application icons come from, which this theme does not
    # provide. hicolor is first because it is what the system ships and
    # has to be respected; Fluent follows because it is the only
    # complete colour set installed, and it is what makes every
    # application show its own mark.
    ap.add_argument("--eredita",
                    default="hicolor,Fluent,breeze-dark,Adwaita")
    ap.add_argument("--limite", type=int, default=0,
                    help="convert at most N icons (for trials)")
    args = ap.parse_args()

    sorgente = pathlib.Path.home() / ".local/share/icons" / args.da
    if not sorgente.is_dir():
        print(f"  ✗ source theme not found: {sorgente}", file=sys.stderr)
        return 2

    destinazione = pathlib.Path(args.a) if args.a else \
        pathlib.Path.home() / ".local/share/icons/Meridiano"
    if destinazione.exists():
        shutil.rmtree(destinazione)

    # The freedesktop contexts. In the sources they sit under
    # `scalable/<context>/`, not at the root: Fluent's root is organised
    # by *size* (16, 22, 24, 32, 256) with the contexts inside, while a
    # freedesktop theme's root wants them the other way round. So
    # `scalable/` is taken and looked into.
    CONTESTI = ["apps", "actions", "status", "places", "preferences",
                "mimetypes", "emblems", "other", "devices", "categories"]
    trovate = 0
    scartate = 0
    # Where the contexts live is not uniform.
    #
    # `apps`, `places` and `devices` sit under `scalable/`, at the theme
    # root. `actions`, `status`, `mimetypes` and `emblems` exist only
    # inside the per-size directories, and they are copies of the same
    # icon: one size is taken, the largest available, because
    # duplicating them adds nothing and multiplies the file count.
    # `preferences` and `other` the source theme does not have: they are
    # inherited.
    #
    # No application icons. A theme that supplies them replaces every
    # program's mark with a monochrome drawing: the user can no longer
    # tell Firefox from a text editor, and in a panel with six windows
    # open has no idea which is which. Identity is data, not decoration,
    # and a theme has no business erasing it.
    #
    # So the `apps` context is not generated: applications inherit their
    # own icon from the theme chain below. Only interface icons live
    # here, and those have no mark to defend.
    for contesto in ("places", "devices", "mimetypes"):
        nome = "MimeTypes" if contesto == "mimetypes" else contesto.capitalize()
        src = sorgente / "scalable" / contesto
        if not src.is_dir():
            continue
        dst = destinazione / "scalable" / nome
        dst.mkdir(parents=True, exist_ok=True)
        for svg in sorted(src.rglob("*.svg")):
            try:
                testo = svg.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            nuovo_t, _ = appiattisci(testo)
            (dst / svg.name).write_text(nuovo_t, encoding="utf-8")
            trovate += 1

    # Per-size contexts.
    #
    # Every size is walked, largest first, and a name already taken is
    # not taken again. The previous version did `break` after the first
    # size that existed, on the reasoning that "duplicating them adds
    # nothing": true of the drawings, and the cause of a silent loss.
    # Fluent does not distribute evenly, so an icon that exists only at
    # 24 was simply never copied. Regenerating the theme dropped
    # `utilities-terminal.svg` and `start-here-kde.svg` this way, and
    # nothing complained: the theme is generated, so a file that goes
    # missing is indistinguishable from one that never existed.
    #
    # `places` is read from `scalable/places` *and* from the per-size
    # directories, for the same reason: some of its icons are in one and
    # some in the other.
    PER_DIMENSIONE = {"actions": ["32", "24", "22", "16"],
                      "status": ["32", "24", "22", "16"],
                      "mimetypes": ["32", "24", "22", "16"],
                      "emblems": ["32", "24", "22", "16"],
                      "places": ["32", "24", "22", "16"]}
    for contesto, dimensioni in PER_DIMENSIONE.items():
        nome = contesto.capitalize() if contesto != "mimetypes" else "MimeTypes"
        dst = destinazione / "scalable" / nome
        presi: set[str] = set()
        sorgenti: list[pathlib.Path] = []
        if contesto == "places":
            # Already copied from scalable/places above; these are the
            # extra sources, largest first, and the set of names taken
            # is seeded from what is already on disk.
            presi = {p.name for p in dst.glob("*.svg")} if dst.is_dir() else set()
            dst.mkdir(parents=True, exist_ok=True)
        for d in dimensioni:
            src = sorgente / d / contesto
            if src.is_dir():
                sorgenti.append(src)
        for src in sorgenti:
            for svg in sorted(src.glob("*.svg")):
                if svg.name in presi:
                    continue
                presi.add(svg.name)
                try:
                    testo = svg.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                nuovo_t, _ = appiattisci(testo)
                dst.mkdir(parents=True, exist_ok=True)
                (dst / svg.name).write_text(nuovo_t, encoding="utf-8")
                trovate += 1

    destinazione.mkdir(parents=True, exist_ok=True)

    # The start icon, drawn rather than inherited.
    #
    # It has to happen here and not as a post-step: the destination is
    # wiped at the top of main, so anything applied afterwards would be
    # gone the next time the generator runs, and the Windows flag would
    # come back.
    #
    # Every context directory is walked, not a chosen three. The same
    # name lives in more than one context -- `start-here-kde.svg` is in
    # Places and `start-here-kde-symbolic.svg` is in Status -- and a
    # name that is left as the source artwork in the context where it
    # happens to sit is still a Windows logo on the panel.
    scalabile = destinazione / "scalable"
    scritte = 0
    if scalabile.is_dir():
        for svg in sorted(scalabile.glob(f"*/{NOMI_START}")):
            svg.write_text(griglia_tasti(), encoding="utf-8")
            scritte += 1
    if scritte:
        print(f"  ✓ start icon drawn: {scritte} files, key grid, "
              f"not the Windows flag")

    presenti = sorted(d.name for d in (destinazione / "scalable").iterdir()
                      if d.is_dir())
    (destinazione / "index.theme").write_text(
        indice(presenti, "Meridiano", args.eredita), encoding="utf-8")
    print(f"  ✓ index.theme declares {len(presenti)} directories: "
          f"{', '.join(presenti)}")

    print(f"  ✓ {destinazione}")
    print(f"  ✓ {trovate} monochrome icons in {len(CONTESTI)} contexts")
    if scartate:
        print(f"    ({scartate} skipped because of --limite)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
