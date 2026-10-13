#!/usr/bin/env python3
"""
genera-assets-plasma.py — Generates the SVG asset set of the Meridiano
Plasma theme.

Why a generator and not twenty files by hand
--------------------------------------------
Plasma's components are not overridable QML: they are compiled into the
binary (see docs/SCOPERTA-tema-plasma6.md). The real lever is the SVGs,
and they are twenty sets with a very regular contract: nine elements per
prefix, plus rectangles that declare where to cut. Written by hand they
would be twenty almost identical files, and the day the radius went from
2 to 3px I would have twenty files to edit and no error to trace.

Here the twenty sets derive from a readable table of parameters: for
each element you can see radius, border, fill. It is the same choice as
make-textures.py makes for the background.

The contract, in brief
----------------------
Each set is an SVG with these elements, for each state prefix:

    {prefix}-topleft  {prefix}-top  {prefix}-topright
    {prefix}-left     {prefix}-center  {prefix}-right
    {prefix}-bottomleft {prefix}-bottom {prefix}-bottomright

and these invisible rectangles, which tell KSvg where to cut:

    focus-hint-top-margin    focus-hint-bottom-margin
    focus-hint-left-margin   focus-hint-right-margin

Plasma asks for states with formulas, not with fixed names: the button
asks for `["toolbutton-hover", "normal"]`, meaning "if the
toolbutton-hover family exists use that, otherwise normal". A set that
exposes only `normal`, `hover`, `pressed` and `focus` is therefore
still valid.

The colours
-----------
No colour is written as hex. Every element carries a `ColorScheme-*`
class that Plasma substitutes at runtime with the active scheme. The
theme is written once and follows the scheme forever: that is why SVGs
are preferable to any colour override.

Usage:
    python3 tools/genera-assets-plasma.py [--out DIR] [--check]
"""

from __future__ import annotations

import argparse
import configparser
import functools
import pathlib
import re

# ── Theme geometry ─────────────────────────────────────────────────────
# The same numbers as the QML core I wrote and then threw away: they
# survive here, where they are actually needed.

RAGGIO = 2.0      # px — enough not to look sharp
BORDO = 1.0       # px — a single thickness across the whole theme
LATO = 16         # px — side of the sets' square canvas
MARGINE = 4       # px — width of the peripheral slices

# The margin rectangles have to stay in the document but must not be
# drawn: KSvg only measures them.
NASCOSTO = 'fill="none" stroke="none"'

# Centre of the corner arc: half the radius plus half the border.
_C = RAGGIO + BORDO / 2.0


def _n(v: float) -> str:
    """Compact number: 2.0 -> '2', 0.5 -> '0.5'."""
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:g}"


# ── Primitives ──────────────────────────────────────────────────────────

def _rect(x, y, w, h, *, fill="none", classe=None, rx=None,
          stroke=None, spessore=0.0, opacita=None) -> str:
    a = [f'x="{_n(x)}"', f'y="{_n(y)}"', f'width="{_n(w)}"', f'height="{_n(h)}"']
    if rx is not None:
        a += [f'rx="{_n(rx)}"', f'ry="{_n(rx)}"']
    if classe:
        a.insert(0, f'class="{classe}"')
    a.append(f'fill="{fill}"')
    if spessore:
        a.append(f'stroke="{stroke}"')
        a.append(f'stroke-width="{_n(spessore)}"')
    if opacita is not None:
        a.append(f'opacity="{_n(opacita)}"')
    return "<rect " + " ".join(a) + "/>"


def _path(d, *, fill="none", classe=None, stroke=None, spessore=0.0) -> str:
    a = [f'd="{d}"']
    if classe:
        a.insert(0, f'class="{classe}"')
    a.append(f'fill="{fill}"')
    if spessore:
        a += [f'stroke="{stroke}"', f'stroke-width="{_n(spessore)}"',
              'stroke-linecap="round"', 'stroke-linejoin="round"']
    return "<path " + " ".join(a) + "/>"


def _gruppo(id_: str, dentro: str) -> str:
    return f'<g id="{id_}">{dentro}</g>' if dentro else ""


# ── The nine-slice ──────────────────────────────────────────────────────

def _angolo(qx: int, qy: int, riempimento, bordo, raggio: float = RAGGIO) -> str:
    """One of the four corners, in absolute coordinates.

    The corner piece contains the fillet arc and the filled square out
    to the edge of the slice. The curve starts at (radius+0.5, 0.5) and
    ends at (0.5, radius+0.5): those are the points where the arc
    touches the straight sides, and they have to match the ends of the
    strips, otherwise a seam appears on wide surfaces.

    `qx`/`qy` say which corner we are at: 0,0 is top left.
    """
    L, k = LATO, MARGINE
    c = _C + (raggio - RAGGIO) / 2.0
    if qx == 0:
        sx = 1.0
    else:
        sx = -1.0
    if qy == 0:
        sy = 1.0
    else:
        sy = -1.0
    # The "inward" side of the corner square.
    x0, y0 = (0.0, 0.0) if (qx, qy) == (0, 0) else \
             (L - k, 0.0) if (qx, qy) == (1, 0) else \
             (0.0, L - k) if (qx, qy) == (0, 1) else (L - k, L - k)
    # Fill: full square with the arc cut out of it.
    riemp = _path(
        f"M {_n(c)},{_n(y0)} H {_n(x0 + k)} V {_n(y0 + k)} H {_n(x0)} "
        f"V {_n(c)} A {_n(RAGGIO)},{_n(RAGGIO)} 0 0 {'1' if sx * sy > 0 else '0'} "
        f"{_n(c)},{_n(y0)} Z",
        fill=riempimento or "none", classe=riempimento)
    # Border: only the arc. The strips draw the straight parts.
    if bordo:
        a0 = f"M {_n(c)},{_n(y0 + BORDO / 2)} A {_n(RAGGIO)},{_n(RAGGIO)} 0 0 " \
             f"{'1' if sx * sy > 0 else '0'} {_n(x0 + BORDO / 2)},{_n(c)}"
        bor = _path(a0, classe=bordo, stroke="currentColor", spessore=BORDO)
    else:
        bor = ""
    return riemp + bor


def nove_slice(prefisso: str, *, riempimento=None, bordo=None,
               raggio: float = RAGGIO, lato: int = LATO,
               margine: int = MARGINE) -> str:
    """A rounded rectangle split into the nine slices.

    `raggio` serves the switches and the knobs, which are round. The
    fillet is computed on the corner: the corners have to match the
    strips, otherwise a seam appears on wide surfaces, and a seam is
    the defect that makes a theme built this way look cheap.
    """
    L, k = lato, margine
    interno = L - 2 * k
    b = BORDO / 2.0

    # The four straight strips: full fill, border only on the outer
    # side.
    top = _rect(k, 0, interno, k, fill=riempimento or "none", classe=riempimento) + (
        _path(f"M {k},{_n(b)} H {L - k}", classe=bordo, stroke="currentColor",
              spessore=BORDO) if bordo else "")
    bot = _rect(k, L - k, interno, k, fill=riempimento or "none", classe=riempimento) + (
        _path(f"M {k},{_n(L - b)} H {L - k}", classe=bordo, stroke="currentColor",
              spessore=BORDO) if bordo else "")
    sx = _rect(0, k, k, interno, fill=riempimento or "none", classe=riempimento) + (
        _path(f"M {_n(b)},{k} V {L - k}", classe=bordo, stroke="currentColor",
              spessore=BORDO) if bordo else "")
    dx = _rect(L - k, k, k, interno, fill=riempimento or "none", classe=riempimento) + (
        _path(f"M {_n(L - b)},{k} V {L - k}", classe=bordo, stroke="currentColor",
              spessore=BORDO) if bordo else "")

    centro = _rect(k, k, interno, interno,
                   fill=riempimento or "none", classe=riempimento)

    return "\n".join(x for x in [
        _gruppo(f"{prefisso}-topleft",     _angolo(0, 0, riempimento, bordo, raggio)),
        _gruppo(f"{prefisso}-top",         top),
        _gruppo(f"{prefisso}-topright",    _angolo(1, 0, riempimento, bordo, raggio)),
        _gruppo(f"{prefisso}-left",        sx),
        _gruppo(f"{prefisso}-center",      centro),
        _gruppo(f"{prefisso}-right",       dx),
        _gruppo(f"{prefisso}-bottomleft",  _angolo(0, 1, riempimento, bordo, raggio)),
        _gruppo(f"{prefisso}-bottom",      bot),
        _gruppo(f"{prefisso}-bottomright", _angolo(1, 1, riempimento, bordo, raggio)),
    ] if x)


SCHEMA = "Meridiano"

# What class each role comes from. The six names are the only ones
# libKF6Svg knows; the left-hand side is the name in the file, the
# right-hand side is the group and role in the colour scheme.
RUOLI = (
    ("Text", "View", "ForegroundNormal"),
    ("Background", "View", "BackgroundNormal"),
    ("Highlight", "Button", "DecorationFocus"),
    ("ButtonBackground", "Button", "BackgroundNormal"),
    ("ButtonText", "Button", "ForegroundNormal"),
    ("Frame", "View", "BackgroundAlternate"),
)


@functools.lru_cache(maxsize=1)
def blocco_stile(schemi: str = SCHEMA) -> str:
    """The `<style id="current-color-scheme">` block, without which nothing
    in these files is coloured.

    libKF6Svg contains the literal string `current-color-scheme`: it parses
    that block to learn WHICH classes exist in this file and what each one
    means. A `class="ColorScheme-Text"` written on a path is not a colour
    and not a reference to one -- on its own it is an unknown selector, the
    stylesheet default applies, and the element is painted black.

    Which is what happened, and for a long time: all twenty sets carried
    valid class names and none of them carried the block, so every widget
    Plasma drew from this theme came out black. The geometry work on the
    switch was correct and irrelevant until this was added; the red 40x24
    test rectangle only showed up because it used a literal `fill`.

    The values written here are the active scheme's own, read from
    src/theme/color-schemes/, so the file is also correct when rendered
    outside Plasma -- and Plasma overwrites them at load time with the
    scheme that is active then, which is how one file serves both
    Meridiano, which is the only scheme there is.
    """
    f = pathlib.Path(__file__).resolve().parent.parent / "src/theme/color-schemes" / f"{schemi}.colors"
    valori = {}
    if f.is_file():
        cp = configparser.RawConfigParser(strict=False, comment_prefixes=("#",))
        cp.optionxform = str
        cp.read_string(f.read_text(encoding="utf-8"))
        for nome, gruppo, ruolo in RUOLI:
            try:
                r, g, b = (int(x) for x in cp[f"Colors:{gruppo}"][ruolo].split(","))
                valori[nome] = f"#{r:02x}{g:02x}{b:02x}"
            except (KeyError, ValueError):
                pass
    righe = []
    for nome, gruppo, ruolo in RUOLI:
        v = valori.get(nome, "#808080")
        righe.append(f"        .ColorScheme-{nome} {{ color: {v}; stop-color: {v}; }}")
    return ('\n    <style id="current-color-scheme" type="text/css">\n'
            + "\n".join(righe) + "\n      </style>")


def guscio(contenuto: str, *, lato: int = LATO, margine: int = MARGINE,
           extra_defs: str = "", attributi: str = "") -> str:
    """An SVG document with the margin rectangles and the content.

    The margins are declared once, under the `focus-hint-*` name Plasma
    looks for. They have neither fill nor border: they exist to be
    measured, and their position is irrelevant.
    """
    d = f"""\n    <!-- The slice margins. Plasma only measures them: no fill, no
         border, and their position does not matter. -->
    <rect id="focus-hint-top-margin"    x="0" y="0"              width="{lato}" height="{margine}" {NASCOSTO}/>
    <rect id="focus-hint-bottom-margin" x="0" y="{lato - margine}" width="{lato}" height="{margine}" {NASCOSTO}/>
    <rect id="focus-hint-left-margin"   x="0" y="0"              width="{margine}" height="{lato}" {NASCOSTO}/>
    <rect id="focus-hint-right-margin"  x="{lato - margine}" y="0" width="{margine}" height="{lato}" {NASCOSTO}/>{extra_defs}"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="{lato}" height="{lato}" viewBox="0 0 {lato} {lato}"{attributi}>
  <defs>{d}
{blocco_stile()}
  </defs>
{contenuto}
</svg>
"""


# ── The colours, as classes and not as hex values ───────────────────────
# Plasma substitutes these classes with the active scheme, so the assets
# follow the scheme without being rewritten. The theme is written once.
#
# The vocabulary is exactly six names, and it is not a matter of taste:
# libKF6Svg holds those six role names as plain strings and builds the
# `ColorScheme-` prefix itself at load time. Any other class name has no
# rule to match, the stylesheet default applies, and the element is drawn
# BLACK. That is not a cosmetic mistake -- an unresolved class does not
# skip the element, it paints it, and black on a dark popup is what a
# broken switch looks like.
#
# Read out of /usr/lib/libKF6Svg.so.6.30.0, not guessed:
#
#   strings libKF6Svg.so.6.30.0 | grep -xE 'Text|Background|...'
#   Background  ButtonBackground  ButtonText  Frame  Highlight  Text
#
# Names that do not exist, and were used here anyway until this was
# measured: ViewBackground, HighlightedText, DisabledText, NegativeText,
# Border.
TESTO = "ColorScheme-Text"
FONDO = "ColorScheme-Background"
ALTO = "ColorScheme-Background"
ACCENTO = "ColorScheme-Highlight"
SPENTO = "ColorScheme-Text"

# The six names. This set is what main() checks every generated file
# against, and a class outside it makes the run fail with a non-zero exit
# rather than writing twenty files full of black. It is a set, not a
# function: an earlier version of this comment referred to a
# `verifica_vocabolario` that was never written.
VOCABOLARIO = {
    "ColorScheme-Text",
    "ColorScheme-Background",
    "ColorScheme-Highlight",
    "ColorScheme-ButtonBackground",
    "ColorScheme-ButtonText",
    "ColorScheme-Frame",
}


# ── The sets ───────────────────────────────────────────────────────────
# For each set: the state families Plasma asks for, and the drawing of
# each. The `prefix`es are the ones extraction from Plasma's code
# found: they are not fixed names, they are formulas over the states,
# and the renderer falls into them with the first family it finds.
#
# A set that exposes only the right families is still valid: that way
# you never end up drawing states the theme does not use.


def set_pulsante() -> str:
    """widgets/button — the button.

    Plasma asks for: normal, pressed, hover, focus, and the variants
    toolbutton-hover / toolbutton-pressed / toolbutton-focus. The
    renderer tries the specific family and falls back to the generic
    one. For a theme with no effects on mouse-over, the generic family
    is enough, plus the three toolbutton ones the toolbar needs.
    """
    parti = []
    for famiglia, riemp, bordo in (
        ("normal",        ALTO,    "ColorScheme-Text"),
        ("pressed",       FONDO,   ACCENTO),
        ("hover",         ALTO,    ACCENTO),
        ("focus",         ALTO,    ACCENTO),
        ("toolbutton-normal",  FONDO, SPENTO),
        ("toolbutton-hover",   ALTO,   ACCENTO),
        ("toolbutton-pressed", FONDO,  ACCENTO),
        ("toolbutton-focus",   ALTO,   ACCENTO),
    ):
        parti.append(_famiglia(famiglia, riempimento=riemp, bordo=bordo))
    parti.append(_famiglia("shadow", riempimento="none", bordo="none",
                           solo_ombra=True))
    return guscio("\n".join(parti))


def _famiglia(prefisso: str, *, riempimento, bordo, raggio=RAGGIO,
              solo_ombra=False) -> str:
    """A rounded rectangle in the nine slices, under a prefix."""
    if solo_ombra:
        return nove_slice(prefisso, riempimento=None, bordo=None)
    return nove_slice(prefisso, riempimento=riempimento, bordo=bordo,
                      raggio=raggio)


def set_linea() -> str:
    """widgets/line — the separators.

    A 1px line. Plasma asks for it horizontally and vertically with the
    same `elementId`, so the same drawing rotates.
    """
    return guscio(
        f'<g id="horizontal-line"><rect x="0" y="{LATO // 2}" width="{LATO}" '
        f'height="1" class="{TESTO}" opacity="0.20" fill="currentColor"/></g>\n'
        f'<g id="vertical-line"><rect x="{LATO // 2}" y="0" width="1" '
        f'height="{LATO}" class="{TESTO}" opacity="0.20" fill="currentColor"/></g>',
        extra_defs=f'\n    <rect id="hint-line-size" x="0" y="0" width="1" '
                   f'height="1" {NASCOSTO}/>')


def set_barra() -> str:
    """widgets/scrollbar — the scrollbar.

    Plasma asks for `background-vertical` and `background-horizontal`,
    and for the handle the plain prefixes `slider` and
    `mouseover-slider` -- not oriented names. A set with only
    `slider-horizontal` families paints the groove and no thumb: the
    handle request matches nothing and the thumb is invisible, the
    same defect as the missing viewitem selection. The oriented
    families stay as inert extras; the hint is renamed to the name
    ScrollBar.qml actually measures (`hint-scrollbar-size`).
    A 3px track with no arrows and no nubbins, as in the
    panel theme: a scrollbar is not content, it is chrome.
    """
    parti = [
        _fascia("background-vertical", LATO, 3),
        _fascia("background-horizontal", LATO, 3),
        _famiglia("slider", riempimento=ALTO, bordo=None, raggio=1),
        _famiglia("mouseover-slider", riempimento=ACCENTO, bordo=None,
                  raggio=1),
        _fascia("slider-vertical", 3, LATO, colore=ALTO, raggio=1),
        _fascia("slider-horizontal", LATO, 3, colore=ALTO, raggio=1),
        _fascia("slider-vertical-hover", 3, LATO, colore=ACCENTO, raggio=1),
        _fascia("slider-horizontal-hover", LATO, 3, colore=ACCENTO, raggio=1),
    ]
    return guscio("\n".join(parti),
                  extra_defs=f'\n    <rect id="hint-scrollbar-size" x="0" y="0" '
                             f'width="3" height="3" {NASCOSTO}/>\n'
                             f'\n    <rect id="hint-slider-size" x="0" y="0" '
                             f'width="3" height="3" {NASCOSTO}/>\n'
                             f'    <g id="arrow-up"><rect x="0" y="0" width="1" '
                             f'height="1" {NASCOSTO}/></g>')


def _fascia(prefisso: str, w: int, h: int, *, colore=None, raggio=0.0) -> str:
    """A thin strip: used for the tracks and the handles."""
    r = ""
    if colore:
        r = f' rx="{_n(raggio)}" ry="{_n(raggio)}"' if raggio else ""
        fill = f'class="{colore}" fill="currentColor"'
    else:
        fill = f'class="{TESTO}" fill="currentColor" opacity="0.14"'
    return (f'<g id="{prefisso}"><rect x="0" y="0" width="{w}" height="{h}"'
            f'{r} {fill}/></g>')


def set_sfondo() -> str:
    """widgets/background — the background of panels and boxes.

    A full rectangle. The name Plasma looks for is `blurred-mask`, and
    for the panel it is better as an opaque surface than as a mask: on a
    dark background a transparent surface makes the text readable
    against the wallpaper, and legible text is the one thing that
    cannot be sacrificed.
    """
    return guscio(
        f'<g id="blurred-mask"><rect x="0" y="0" width="{LATO}" height="{LATO}" '
        f'class="{FONDO}" fill="currentColor"/></g>')


def set_quadro() -> str:
    """widgets/frame — the boxes.

    Plasma asks for the `plain` prefix. A box with barely a thread of
    live colour inside it, like the graticule of a measurement panel.
    """
    return guscio("\n".join([
        _famiglia("plain", riempimento=ALTO, bordo="ColorScheme-Text"),
    ]))


def set_campo() -> str:
    """widgets/lineedit — the text fields.

    Sunken, with the border lighting up only on focus. Plasma asks for
    `base`, `hover` and `focus`, and looks for `focusframe-center` to
    decide whether the theme has a dedicated focus border: this set
    declares it, so `focus` is not treated as a plain hover.
    """
    return guscio("\n".join([
        _famiglia("base", riempimento=FONDO, bordo=SPENTO),
        _famiglia("hover", riempimento=FONDO, bordo="ColorScheme-Text"),
        _famiglia("focus", riempimento=FONDO, bordo=ACCENTO),
        f'<g id="focusframe-center"><rect x="0" y="0" width="1" height="1" '
        f'{NASCOSTO}/></g>',
    ]))


def set_spunte() -> str:
    """widgets/checkmarks — the box and the knob.

    Two symbols in the same file, chosen by Plasma with `elementId`.
    Drawn in QML? No: here in SVG, and without a font glyph, because
    glyphs change shape from one theme to the next.
    """
    return guscio(
        f'<g id="checkbox"><path d="M 4,8.5 L 7,11.5 L 12,5" fill="none" '
        f'stroke="currentColor" stroke-width="2" class="{ACCENTO}" '
        f'stroke-linecap="round" stroke-linejoin="round"/></g>\n'
        f'<g id="radiobutton"><circle cx="8" cy="8" r="4" fill="currentColor" '
        f'class="{ACCENTO}"/></g>')


def _letterale(id_: str, *, riempimento, bordo=None, raggio=RAGGIO) -> str:
    """A single element with an exact id, for the sets Plasma asks for by
    elementId.

    Two different ways of asking for the same thing, and both are needed:
    `widgets/button` asks for a prefix *family* and KSvg cuts the box
    into nine, while `widgets/actionbutton` asks for the whole `normal`
    element. If the shape the set asks for is missing, Plasma draws
    nothing and does not report it.
    """
    return (f'<g id="{id_}"><rect x="0" y="0" width="{LATO}" height="{LATO}"'
            f' rx="{_n(raggio)}" ry="{_n(raggio)}" class="{riempimento}"'
            f' fill="currentColor"/></g>')


def set_azioni() -> str:
    """widgets/actionbutton — the action button and the dial's square.

    Here Plasma asks for the elements by name: `normal`, `pressed`,
    `hover`, `shadow`. Not families. See _letterale.
    """
    parti = [
        _letterale("normal", riempimento=FONDO),
        _letterale("hover", riempimento=ALTO),
        _letterale("pressed", riempimento=FONDO),
        _letterale("radiobutton", riempimento=ALTO),
        # the shadow: the same shape as the button, with no fill. The
        # renderer uses it for the halo, which on a dark background is
        # invisible and when visible looks like dirt: better that it be
        # there and be harmless.
        f'<g id="shadow" opacity="0"><rect x="0" y="0" width="{LATO}" '
        f'height="{LATO}" fill="none"/></g>',
    ]
    return guscio("\n".join(parti))


def set_radio() -> str:
    """widgets/radiobutton — the selector's ring and dot.

    Plasma asks for `symbol` (the dot) and `hover`, by name.
    """
    parti = [
        _letterale("normal", riempimento=FONDO, raggio=LATO / 2),
        _letterale("hover", riempimento=ALTO, raggio=LATO / 2),
        _letterale("checked", riempimento=ALTO, raggio=LATO / 2),
        _letterale("focus", riempimento=ALTO, raggio=LATO / 2),
        # the dot: a full disc in the centre. The shape already says
        # how it differs from the box, colour need not say it twice.
        f'<g id="symbol"><circle cx="{LATO / 2}" cy="{LATO / 2}" r="3.5" '
        f'class="{ACCENTO}" fill="currentColor"/></g>',
        f'<g id="shadow" opacity="0"><rect x="0" y="0" width="{LATO}" '
        f'height="{LATO}" fill="none"/></g>',
    ]
    return guscio("\n".join(parti))


def set_voce() -> str:
    """widgets/listitem — the list entry.

    Plasma calls `normal`, `hover` and, for section headings, a prefix
    that starts with `section`. Selection is a full background: in a
    scrolling list a border follows the mouse and makes the list look
    like a run of boxes.

    `pressed` is the same bug viewitem had: DefaultListItemBackground
    asks for it whenever the entry is highlighted or down
    (`control.highlighted || control.down ? "pressed" : "normal"`),
    with no fallback array. Without the family a highlighted row loses
    its background the same way a clicked desktop icon lost its
    highlight.
    """
    return guscio("\n".join([
        _famiglia("normal", riempimento=FONDO, bordo=None),
        _famiglia("hover", riempimento=ALTO, bordo=None),
        _famiglia("pressed", riempimento=ACCENTO, bordo=None),
        _famiglia("section", riempimento=FONDO, bordo=None),
        _famiglia("separator", riempimento=None, bordo=None),
        f'<g id="separator"><rect x="0" y="{LATO // 2}" width="{LATO}" '
        f'height="1" class="{TESTO}" fill="currentColor" opacity="0.20"/></g>',
    ]))


def set_scheda() -> str:
    """widgets/tabbar — the tab bar.

    Plasma calls `north-active-tab` or `south-active-tab` depending on
    the position. The active tab is told apart by a lit line, not by a
    fill: in a bar with many tabs it is the only way to know which one
    is open without reading them all.
    """
    parti = [
        _famiglia("north-active-tab", riempimento=FONDO, bordo=ACCENTO),
        _famiglia("south-active-tab", riempimento=FONDO, bordo=ACCENTO),
    ]
    return guscio("\n".join(parti))


def set_strumento() -> str:
    """widgets/toolbar — the toolbar."""
    return guscio(
        f'<g id="separator"><rect x="0" y="{LATO // 2}" width="{LATO}" '
        f'height="1" class="{TESTO}" fill="currentColor" opacity="0.20"/></g>')


def set_riquadro_voce() -> str:
    """widgets/viewitem — an entry in a view.

    PlasmaExtras.Highlight asks for four families, and the two that
    matter only exist while something is chosen: `normal`, `hover`,
    `selected` and `selected+hover`. A set with only the first two
    renders the highlight fine until the click, and then nothing at
    all -- the selection looks as if it was never inserted, which is
    exactly how a missing family presents. Selected is the model's
    own selection colour, full amber: that is what Selection means
    everywhere else in this theme.
    """
    return guscio("\n".join([
        _famiglia("normal", riempimento=FONDO, bordo=None),
        _famiglia("hover", riempimento=ALTO, bordo=ACCENTO),
        _famiglia("selected", riempimento=ACCENTO, bordo=None),
        _famiglia("selected+hover", riempimento=ACCENTO, bordo=TESTO),
    ]))


def set_testo() -> str:
    """widgets/plasmoidheading — a plasmoid's heading."""
    return guscio("\n".join([
        _famiglia("header", riempimento=FONDO, bordo=None),
        _famiglia("footer", riempimento=ALTO, bordo=None),
    ]))


def set_occupato() -> str:
    """widgets/busywidget — the busy indicator.

    A ring that turns, in the dim channel. The missing quadrant is the
    information: a whole ring that turns looks like an ornament.
    """
    return guscio(
        f'<g id="busywidget">'
        f'<circle cx="8" cy="8" r="6" fill="none" class="{SPENTO}" '
        f'stroke="currentColor" stroke-width="2" opacity="0.5"/>'
        f'<path d="M 8,2 A 6,6 0 0 1 14,8" fill="none" class="{ACCENTO}" '
        f'stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
        f'</g>')


def set_misura() -> str:
    """widgets/bar_meter_horizontal — the meter bar.

    Like the panel's progress bar: dim track, lit charge, and the same
    thresholds.

    Both families have to be nine-slice sets, not single groups: the
    only consumer, PlasmaComponents3.ProgressBar (which is also what
    the volume/brightness OSD draws), reads them through
    KSvg.FrameSvgItem with the prefixes `bar-active` and
    `bar-inactive`. Single `<g id="bar-active">` elements are not
    frames, so the meter painted nothing at all -- the OSD showed the
    icon and the percentage with no bar between them, the same defect
    as the missing viewitem selection. The track is the background
    colour itself, so it reads as a groove cut into the popup rather
    than as a second bar competing with the charge.
    """
    return guscio("\n".join([
        _famiglia("bar-inactive", riempimento=FONDO, bordo=None, raggio=1),
        _famiglia("bar-active", riempimento=ACCENTO, bordo=None, raggio=1),
    ]),
        extra_defs=f'\n    <rect id="hint-bar-size" x="0" y="0" width="16" '
                   f'height="3" {NASCOSTO}/>')


def set_frecce() -> str:
    """widgets/arrows — the menu arrows."""
    return guscio(
        f'<g id="down-arrow"><path d="M 4,6 L 8,10 L 12,6 Z" fill="currentColor" '
        f'class="{TESTO}"/></g>')


# Not generated here: widgets/switch and widgets/slider.
#
# Same reasoning, and it is worth stating once for both. Plasma falls back
# to desktoptheme/default/widgets/ for any set the active theme does not
# ship, and Breeze's are hand-tuned nine-patches with a
# `<style id="current-color-scheme">` block: switch.svgz is 2.3 kB with
# gradients, a real drop shadow and four handle states, slider.svgz 2.8 kB.
#
# I wrote both anyway. The switch took four rounds to stop being a black
# dot -- square geometry instead of a pill, `hint-bar-size` at 2 x 2, the
# resting `handle` missing, and not one of the twenty sets carrying the
# style block that tells Plasma which classes exist. It was still an ugly
# crescent by the time it was finally coloured. The slider I never even
# saw: it had two elements, `groove` and `groove-highlight`, and nothing
# in the file could tell me whether that was the contract.
#
# The identity of Meridiano lives in its colour scheme, its textures and
# its icons. It does not live in redrawing widgets that KDE already draws
# well, and every one of them follows the active scheme for free because
# Breeze's files ship the same six classes and Plasma rewrites them from
# the active scheme.
SET = {
    "widgets/button": set_pulsante,
    "widgets/frame": set_quadro,
    "widgets/background": set_sfondo,
    "widgets/lineedit": set_campo,
    "widgets/scrollbar": set_barra,
    "widgets/line": set_linea,
    "widgets/checkmarks": set_spunte,
    "widgets/actionbutton": set_azioni,
    "widgets/radiobutton": set_radio,
    "widgets/listitem": set_voce,
    "widgets/tabbar": set_scheda,
    "widgets/toolbar": set_strumento,
    "widgets/viewitem": set_riquadro_voce,
    "widgets/plasmoidheading": set_testo,
    "widgets/busywidget": set_occupato,
    "widgets/bar_meter_horizontal": set_misura,
    "widgets/arrows": set_frecce,
    "solid/widgets/tooltip": set_campo,
}


COLORS = "colors"
PLASMARRC = "plasmarc"
METADATA = """{
    "KPackageStructure": "Plasma/Theme",
    "KPlugin": {
        "Id": "Meridiano",
        "Name": "Meridiano",
        "Description": "Warm surfaces, 1px edges, a single amber accent. The colours follow the active scheme.",
        "Author": "Daen",
        "License": "GPL-3.0",
        "Version": "1.0"
    }
}
"""

# The Plasma theme's colour effects. Copied from the default theme: they
# add nothing to a dark scheme, and the panel applies them over the
# backgrounds, so they can only dirty things.
COLORS_FILE = """[ColorEffects:Disabled]
Color=0,0,0
ColorAmount=0
ColorEffect=0
ContrastAmount=0.65
ContrastEffect=1
IntensityAmount=0
IntensityEffect=0

[ColorEffects:Inactive]
ChangeSelectionColor=true
ColorAmount=0.0125
ColorEffect=2
ContrastAmount=0.10
ContrastEffect=2
Enable=false
IntensityAmount=0
IntensityEffect=0
"""

# The settings the theme carries with it. The skin is the entry that
# matters: with `Next` Plasma draws the panels on its own initiative, and
# the result is no longer the one the theme draws.
PLASMAR_FILE = """[Theme]
name=Meridiano

[AdaptiveTransparency]
enabled=false
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = pathlib.Path(args.out)

    scritti = 0
    mancanti = []
    fuori_vocabolario: set[str] = set()
    for nome, costruttore in sorted(SET.items()):
        # Plasma declares `imagePath: "widgets/button"` and KSvg resolves
        # it to `button.svg`: without the extension the file is there but
        # is not found, and the theme falls back to Breeze without
        # saying anything.
        dest = out / (nome + ".svg")
        dest.parent.mkdir(parents=True, exist_ok=True)
        svg = costruttore()
        if "<g " not in svg:
            mancanti.append(nome)
        # A class outside the six names libKF6Svg knows is not a warning,
        # it is black paint. Five of them were used here for a long time
        # and nothing failed: the files were valid SVGs, they were just
        # wrong, and the only symptom was on screen.
        fuori_vocabolario |= {c for c in re.findall(r"ColorScheme-[A-Za-z]+", svg)
                              if c not in VOCABOLARIO}
        dest.write_text(svg, encoding="utf-8")
        scritti += 1

    out.mkdir(parents=True, exist_ok=True)
    (out / "metadata.json").write_text(METADATA, encoding="utf-8")
    (out / COLORS).write_text(COLORS_FILE, encoding="utf-8")
    (out / PLASMARRC).write_text(PLASMAR_FILE, encoding="utf-8")

    print(f"  ✓ {out}")
    print(f"  ✓ {scritti} SVG sets, plus colors, plasmarc and metadata.json")
    if mancanti:
        print(f"  ✗ sets with no groups: {', '.join(mancanti)}")
        return 1
    if fuori_vocabolario:
        print("  ✗ classi che Plasma non sa risolvere, verrebbero dipinte "
              "di nero:")
        for c in sorted(fuori_vocabolario):
            print(f"      {c}")
        print("      i sei nomi validi sono in libKF6Svg: "
              + ", ".join(sorted(n.split('-', 1)[1] for n in VOCABOLARIO)))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
