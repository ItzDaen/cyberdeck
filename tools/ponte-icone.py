#!/usr/bin/env python3
"""
ponte-icone.py — Gives Plasma's applets the icon names they ask for.

Why this exists
---------------
The icon theme is generated from whatever names the source themes
happen to carry, and that is not the same set as the names the applets
request. Three concrete cases, all measured against the panel colour
#0e0d0b:

    bluetooth                       present, L  95  but it is called
                                    `bluetooth`, in Devices/; the applet
                                    asks for `bluetooth-symbolic`, in
                                    Status/, so it is never looked up
    bluetooth-*-symbolic            falls through to Fluent, which
                                    hardcodes fill="#363636" -> L 20,
                                    1.14:1, invisible
    power-profile-*-symbolic        the same: Fluent hardcodes #363636,
                                    L 21, and `power-profile-powersave-
                                    symbolic` is in no theme at all

That is the third time the same shape of problem has appeared here: the
artwork was there and bright, under a name nobody asked for, while a
hardcoded near-black copy from another theme got used instead. The
kickoff button was the first (`start-here-kde` existed light in apps/
and dark in places/); the launcher icons were the second.

What it does
------------
For each name an applet is known to ask for, take the source artwork
and write it into the theme with the Plasma colour contract:

    class="ColorScheme-Text" fill="currentColor"

so the icon follows the active colour scheme instead of carrying a
baked-in grey. A symbolic icon that hardcodes its colour cannot follow
a dark scheme, which is the whole reason the theme has classes at all.

The three power profiles keep their three distinct shapes; only the
colour is replaced. They are not made to look alike, and they are not
made to look different by recolouring: the shapes were already
different, they were just all invisible.

Usage:
    python3 tools/ponte-icone.py --check     # measure, write nothing
    python3 tools/ponte-icone.py
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import tempfile

TEMA = pathlib.Path.home() / ".local/share/icons/Meridiano"
PANNO = "#0e0d0b"

FLUENT = pathlib.Path.home() / ".local/share/icons/Fluent"
ALTRI = [
    pathlib.Path("/usr/share/icons/breeze-dark"),
    pathlib.Path("/usr/share/icons/Adwaita"),
    pathlib.Path("/usr/share/icons/breeze"),
]

# name -> (context to write it into, where to take the artwork from)
PONTE: dict[str, tuple[str, str | None]] = {
    # The bluetooth applet.
    #
    # The names it asks for were read out of its own plugin with
    # `strings -e l`, and they are not the ones this file was bridging:
    #
    #   bluetooth-symbolic
    #   bluetooth-activated-symbolic
    #   bluetooth-inactive-symbolic
    #   bluetooth-activated
    #
    # The earlier version bridged `bluetooth-active-symbolic`,
    # `bluetooth-connected-symbolic` and `bluetooth-disabled-symbolic`,
    # which the applet never asks for, and left the two it does ask for
    # unbridged. So the connected state and the idle state both fell
    # through the chain to whatever was there, which is why "a device is
    # paired" and "nothing is paired" looked identical: the two names that
    # would have told them apart were never written at all.
    #
    # The three states are told apart by shape, not by tone, because a
    # shape survives being recoloured onto the ramp and a 15% difference in
    # lightness does not read at 22px on a panel:
    #
    #   idle        the plain rune
    #   activated   the plain rune, lit          <- a device is connected
    #   inactive    the rune with a circled cross
    "bluetooth-symbolic":                 ("Status", "bluetooth-symbolic"),
    "bluetooth-activated-symbolic":       ("Status", "bluetooth-active-symbolic"),
    "bluetooth-activated":                ("Status", "bluetooth-active-symbolic"),
    "bluetooth-inactive-symbolic":        ("Status", "bluetooth-disconnected-symbolic"),
    # Kept, because System Settings and the KCM do ask for some of these.
    "bluetooth-active-symbolic":          ("Status", "bluetooth-active-symbolic"),
    "bluetooth-disconnected-symbolic":    ("Status", "bluetooth-disconnected-symbolic"),
    "bluetooth-connected-symbolic":       ("Status", "bluetooth-active-symbolic"),
    "bluetooth-disabled-symbolic":        ("Status", "bluetooth-disabled-symbolic"),
    # The same applet, and the names it actually asks for. This is the
    # second time this file got the vocabulary wrong, and both times the
    # symptom was identical: the state that mattered was simply absent.
    #
    # Read out of org.kde.plasma.bluetooth.so, the full list is
    #
    #   network-bluetooth-symbolic
    #   network-bluetooth-activated-symbolic
    #   network-bluetooth-inactive-symbolic
    #   network-bluetooth-activated
    #   network-bluetooth
    #   powered
    #   switch
    #
    # The `network-` prefix, not `bluetooth-`. So the four bridged above
    # are names the applet never asks for, while the four it does ask
    # for were all missing from the theme and fell through the chain --
    # which is why "connected" and "nothing connected" looked the same no
    # matter what was done to the `bluetooth-` set.
    #
    # `switch` and `powered` are asked for too, and neither exists in any
    # source theme, so they are drawn rather than bridged: a switch is the
    # control the user is talking about, and it cannot be left to a guest
    # theme that has never heard of it.
    #
    # Correction, measured 2026-10-03: only `powered` is an icon request
    # (`strings -e l org.kde.plasma.bluetooth.so` lists it alongside the
    # network-bluetooth names). `switch` appears in the binary only as QML
    # internals -- switchHeight, switchWidth, onSwitch,
    # PlasmaComponents3.Switch -- never as an icon name, so there is
    # nothing to draw for it and no PONTE entry.
    "powered":                             ("Status", None),
    "network-bluetooth-symbolic":          ("Status", "network-bluetooth-symbolic"),
    "network-bluetooth-activated-symbolic": ("Status", "network-bluetooth-activated-symbolic"),
    "network-bluetooth-inactive-symbolic":  ("Status", "network-bluetooth-inactive-symbolic"),
    "network-bluetooth-activated":         ("Status", "network-bluetooth-activated-symbolic"),
    "network-bluetooth":                    ("Status", "network-bluetooth-symbolic"),
    # The audio applet, and the same fault with a different face.
    #
    # It asks for the *symbolic* names -- read out of its own plugin with
    # `strings -e l`, so not a guess: audio-volume, audio-volume-high,
    # audio-volume-muted, audio-input-microphone and their -symbolic forms.
    # The theme carried the plain names only, so every symbolic request fell
    # through the chain and landed on Fluent-light: a dark drawing made for
    # a light background, sitting on a dark panel. That is the headphone
    # with no contrast, and it was never this theme's icon at all.
    #
    # Bridged from the theme's own plain names, which are already on our
    # ramp, so what reaches the panel is the identity rather than a guest.
    "audio-volume-symbolic":              ("Status", "audio-volume"),
    "audio-volume-high-symbolic":         ("Status", "audio-volume-high"),
    "audio-volume-medium-symbolic":       ("Status", "audio-volume-medium"),
    "audio-volume-low-symbolic":          ("Status", "audio-volume-low"),
    "audio-volume-muted-symbolic":        ("Status", "audio-volume-muted"),
    "audio-headset-symbolic":             ("Status", "audio-volume-high"),
    "audio-headphones-symbolic":          ("Status", "audio-volume-high"),
    # The microphone, same reason: the plain name is in the theme and the
    # symbolic one the applet asks for is not, so the tray drew whatever
    # the chain had -- and the chain's answer was a few pixels across,
    # which is the speck sitting in the tray next to the bluetooth.
    "audio-input-microphone-symbolic":    ("Status", "audio-input-microphone"),
    "audio-input-microphone-muted-symbolic": ("Status", "audio-volume-muted"),
    "microphone-sensitivity-muted-symbolic": ("Status", "audio-volume-muted"),
    # The powerdevil profile selector.
    #
    # The prefix is `battery-profile-`, and that is not a guess: it is
    # the vocabulary breeze uses, and breeze is the only installed
    # theme that carries the set at all. An earlier version of this
    # file bridged `power-profile-*-symbolic` instead -- names that
    # exist in Fluent and Adwaita but that nothing in the applet asks
    # for, so the three profiles still looked the same. Reading the
    # vocabulary off the theme that actually has it is the lesson.
    "battery-profile-balanced":             ("Status", "battery-profile-balanced"),
    "battery-profile-balanced-symbolic":    ("Status", "battery-profile-balanced"),
    "battery-profile-performance":          ("Status", "battery-profile-performance"),
    "battery-profile-performance-symbolic": ("Status", "battery-profile-performance"),
    "battery-profile-powersave":            ("Status", "battery-profile-powersave"),
    "battery-profile-powersave-symbolic":  ("Status", None),
}

# The colour Plasma substitutes for ColorScheme-Text with the active
# scheme's foreground. Read from kdeglobals so it is not a guess.
def _primo_piano() -> str:
    try:
        import configparser
        cp = configparser.RawConfigParser(strict=False)
        cp.optionxform = str
        cp.read(pathlib.Path.home() / ".config/kdeglobals", encoding="utf-8")
        v = cp["Colors:Window"]["ForegroundNormal"].split(",")
        return "#" + "".join(f"{int(x):02x}" for x in v[:3])
    except Exception:
        return "#e8e4dc"


PRIMO_PIANO = _primo_piano()

def lum(c: tuple[int, int, int]) -> float:
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrasto(l: float) -> float:
    def f(v: float) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    fb = 0.0448 * 255
    return (max(f(l), f(fb)) + 0.05) / (min(f(l), f(fb)) + 0.05)


def misura(svg: pathlib.Path, testo: str | None = None) -> float:
    """Render the way Plasma will, not the way rsvg does.

    `currentColor` with no CSS in scope resolves to black, so measuring
    the file as written reports a black icon and looks like a
    regression. Plasma substitutes `ColorScheme-Text` with the scheme's
    foreground before the icon is ever rasterised, so that is what the
    measurement has to do: replace the class with the real colour and
    render that. The number is then the one the panel will show.
    """
    testo = (testo if testo is not None
             else svg.read_text(encoding="utf-8", errors="replace"))
    testo = testo.replace("currentColor", PRIMO_PIANO)
    with tempfile.TemporaryDirectory() as td:
        src = pathlib.Path(td) / "a.svg"
        out = pathlib.Path(td) / "a.png"
        src.write_text(testo, encoding="utf-8")
        try:
            subprocess.run(["rsvg-convert", "-w", "48", "-h", "48", "-b", PANNO,
                            str(src), "-o", str(out)],
                           check=True, capture_output=True, timeout=20)
            from PIL import Image
            im = Image.open(out).convert("RGB")
            # Mean over the *drawn* pixels, not over the canvas.
            #
            # A thin outline glyph on a 48px square is mostly background,
            # so averaging the canvas reports the background and every
            # icon looks like it is in the dark. Firefox measured 77
            # this way and 8.9:1 on the real panel, for exactly that
            # reason. The colour the eye sees as the icon is the mean
            # of the pixels the icon actually covers.
            fondo = im.getpixel((0, 0))
            px = im.load()
            disegnati = [px[x, y] for y in range(im.size[1])
                          for x in range(im.size[0])
                          if max(abs(px[x, y][i] - fondo[i]) for i in range(3)) > 12]
            if not disegnati:
                return -1.0
            return sum(lum(c) for c in disegnati) / len(disegnati)
        except Exception:
            return -1.0


def foglia() -> str:
    """A leaf, for power saving. Drawn here because no theme has it.

    `power-profile-powersave-symbolic` exists in no installed theme --
    not in Fluent, not in breeze-dark, not in Adwaita -- so the
    applet falls back to whatever generic icon it can find and all
    three profiles end up looking the same. A leaf is the convention
    everyone already reads for "saving power", and the other two
    profiles keep their own shapes, so the three stay distinct.
    """
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path class="ColorScheme-Text" fill="currentColor" d="
    M 13.5 2.5 C 8.5 2.2 4.2 4.0 3.0 8.0 C 2.3 10.5 3.4 12.6 5.6 13.2
    C 5.0 11.0 5.6 8.4 7.4 6.4 C 6.2 9.0 5.8 11.0 6.4 13.5
    C 9.6 13.0 12.2 10.4 12.9 6.6 C 13.2 5.1 13.4 3.7 13.5 2.5 Z
    M 13.5 2.5 C 13.3 5.4 12.6 8.0 11.4 10.2 C 12.1 8.2 12.5 5.6 12.4 2.9 Z"/>
</svg>
"""


def potenza() -> str:
    """The power symbol, for the bluetooth applet's `powered` state. Drawn
    here because no installed theme has it -- not Fluent, not breeze-dark,
    not Adwaita -- and the applet asks for the bare name `powered`
    (verified with `strings -e l` on its own plugin).

    The IEC 5009 standby glyph: a broken circle with the line through the
    gap. Stroke-based so it follows ColorScheme-Text like the rest.
    """
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <path class="ColorScheme-Text" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" d="
    M 8.0 2.0 V 8.0
    M 4.6 4.2 A 5.2 5.2 0 1 0 11.4 4.2"/>
</svg>
"""


def trova(nome: str) -> pathlib.Path | None:
    for radice in [FLUENT] + ALTRI + [TEMA]:
        t = sorted(radice.rglob(f"{nome}.svg"))
        if t:
            return t[0]
    return None


def colora(testo: str) -> str:
    """Swap every baked-in fill for the Plasma colour contract.

    A symbolic icon that hardcodes `#363636` cannot follow a dark
    scheme. The shape is left exactly as drawn.
    """
    # fill="..." on any element, including inside style=""
    testo = re.sub(r'fill="(#[0-9A-Fa-f]{3,8}|[A-Za-z]+)"',
                   'fill="currentColor"', testo)
    testo = re.sub(r'fill:\s*(#[0-9A-Fa-f]{3,8}|[A-Za-z]+)\s*;',
                   'fill:currentColor;', testo)
    testo = re.sub(r'fill:\s*(#[0-9A-Fa-f]{3,8}|[A-Za-z]+)',
                   'fill:currentColor', testo)
    # apply the class to the first path so Plasma substitutes the colour
    if "<path" in testo and "ColorScheme-Text" not in testo:
        testo = testo.replace("<path", f'<path class="ColorScheme-Text"', 1)
    return testo


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Provides the icon names Plasma's applets request")
    ap.add_argument("--check", action="store_true", help="measure only")
    args = ap.parse_args()

    print(f"  Meridiano — icon name bridge")
    print(f"  {DIM}panel {PANNO}; ColorScheme-Text resolves to {PRIMO_PIANO} "
          f"in this scheme{OFF}")
    print()

    scritti = 0
    salti = 0
    for nome, (contesto, alias) in sorted(PONTE.items()):
        sorgente = trova(alias) if alias else trova(nome)
        if sorgente is None and nome.endswith("powersave-symbolic"):
            testo = foglia()
        elif sorgente is None and nome == "powered":
            testo = potenza()
        elif sorgente is None:
            print(f"  {Y}!{OFF} {nome:38s} no artwork anywhere")
            salti += 1
            continue
        else:
            testo = sorgente.read_text(encoding="utf-8", errors="replace")
        nuovo = colora(testo)
        prima = misura(sorgente, testo)
        dopo = misura(sorgente, nuovo)
        dest = TEMA / "scalable" / contesto / f"{nome}.svg"
        if args.check:
            print(f"  {Y}?{OFF} {nome:38s} L {prima:6.1f} -> {dopo:6.1f} "
                  f"({contrasto(dopo):.2f}:1)  (check: not written)")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(nuovo, encoding="utf-8")
        scritti += 1
        print(f"  {G}✓{OFF} {nome:38s} L {prima:6.1f} -> {dopo:6.1f} "
              f"({contrasto(dopo):.2f}:1)")

    print()
    if args.check:
        print(f"  {Y}{BOLD}check: nothing written{OFF}")
    else:
        print(f"  {G}{BOLD}✓{OFF} {scritti} icon name(s) written"
              + (f", {salti} without artwork" if salti else ""))
        print(f"  {DIM}the panel has to reload to pick them up{OFF}")
    return 0


G, Y, BOLD, DIM, OFF = ("\033[32m", "\033[33m", "\033[1m", "\033[2m", "\033[0m")

if __name__ == "__main__":
    raise SystemExit(main())
