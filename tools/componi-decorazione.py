#!/usr/bin/env python3
"""
componi-decorazione.py — Composes decoration.svg the way Aurorae does,
without opening a single window.

Why it exists
-------------
KWin's frame is a nine-slice: the corners and the strips do not
stretch, the centre stretches out to the window. Seams are only
visible in that composition, and measuring them required windows on
the desktop — that is, windows popping up over whatever the user was
doing.

This does the same composition on an image and saves it. No KWin, no
windows, no interruptions: you look at a PNG.

Usage:
    python3 tools/componi-decorazione.py [LATO_X LATO_Y] [out.png]
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

from PIL import Image

# The slice margins, in coordinates of the 84x84 source. They have to
# match the clipPaths in decoration.svg.
M = 17           # thickness of the peripheral strips
LATO = 84        # side of the source

REGIONI = {
    "topleft":     (0, 0, M, M),
    "top":         (M, 0, LATO - 2 * M, M),
    "topright":    (LATO - M, 0, M, M),
    "left":        (0, M, M, LATO - 2 * M),
    "center":      (M, M, LATO - 2 * M, LATO - 2 * M),
    "right":       (LATO - M, M, M, LATO - 2 * M),
    "bottomleft":  (0, LATO - M, M, M),
    "bottom":      (M, LATO - M, LATO - 2 * M, M),
    "bottomright": (LATO - M, LATO - M, M, M),
}


def regioni(svg: pathlib.Path, td: pathlib.Path) -> dict:
    """Rasterise the source once and cut out its nine regions."""
    solo = td / "a.svg"
    solo.write_text(svg.read_text(encoding="utf-8"), encoding="utf-8")
    png = td / "a.png"
    subprocess.run(["rsvg-convert", "-w", str(LATO), "-h", str(LATO),
                    str(solo), "-o", str(png)],
                   check=True, capture_output=True, timeout=30)
    intero = Image.open(png).convert("RGB")
    return {nome: intero.crop((x, y, x + w, y + h))
            for nome, (x, y, w, h) in REGIONI.items()}


def componi(reg: dict[str, Image.Image], larghezza: int, altezza: int) -> Image.Image:
    """Composes the way Aurorae does, and not the way one assumes.

    The model I used first stretched the side regions vertically. That
    is not what Aurorae does: the side regions are drawn at their
    natural size and whatever space is left over takes the centre's
    colour. The difference is not academic — with the stretching a 1px
    line inside the region smears into a band, and with the right
    model it stays a 1px fragment. It is the difference between "a
    broken line" and "an erased line".

    Horizontally the top and bottom regions really do stretch: that is
    where the title bar's colour lives, and the amber notch has to
    cross the whole width while staying 1px tall.
    """
    out = Image.new("RGB", (larghezza, altezza),
                    reg["center"].getpixel((M, M)))
    cx, cy = larghezza - 2 * M, altezza - 2 * M

    out.paste(reg["center"].resize((cx, cy), Image.NEAREST), (M, M))
    out.paste(reg["top"].resize((cx, M), Image.NEAREST), (M, 0))
    out.paste(reg["bottom"].resize((cx, M), Image.NEAREST), (M, altezza - M))
    # the sides do NOT stretch: they are drawn where they are
    out.paste(reg["left"], (0, M))
    out.paste(reg["right"], (larghezza - M, M))
    for nome, (x, y) in (("topleft", (0, 0)),
                         ("topright", (larghezza - M, 0)),
                         ("bottomleft", (0, altezza - M)),
                         ("bottomright", (larghezza - M, altezza - M))):
        out.paste(reg[nome], (x, y))
    return out


def cuciture(imm: Image.Image) -> list[str]:
    """The broken lines, ignoring the borders.

    The defect I had: a 1px line inside the side region, which Aurorae
    draws at its natural size. The result was two fragments at the
    sides and a clean middle — a line that should run from side to
    side and instead starts over.

    The check only looks at the interior, discarding the outer left
    and right columns: there the border's tint appears twice per line
    even when everything is correct, and it would report a defect on
    every window in the world.

    In the interior a tint must never reappear in a second stretch:
    that means the line is broken.
    """
    px = imm.load()
    W, H = imm.size
    out: list[str] = []
    for y in range(H):
        tratti: dict[tuple, int] = {}
        inizio = 1                      # skip the border column
        prec = px[1, y]
        for x in range(2, W - 1):
            c = px[x, y]
            if c != prec:
                tratti[prec] = tratti.get(prec, 0) + 1
                inizio, prec = x, c
        tratti[prec] = tratti.get(prec, 0) + 1
        for tinta, n in tratti.items():
            if n > 1:
                out.append(f"y={y}: tint {tinta} split into {n} runs")
                break
    return out[:10]


def main() -> int:
    arg = sys.argv[1:]
    larghezza = int(arg[0]) if len(arg) > 0 else 900
    altezza = int(arg[1]) if len(arg) > 1 else 480
    uscita = pathlib.Path(arg[2]) if len(arg) > 2 else pathlib.Path(
        "/tmp/decorazione-composita.png")

    tema = pathlib.Path.home() / ".local/share/aurorae/themes/Meridiano"
    svg = tema / "decoration.svg"
    if not svg.exists():
        print(f"  ✗ not found: {svg}")
        return 2

    with tempfile.TemporaryDirectory() as td:
        reg = regioni(svg, pathlib.Path(td))

    imm = componi(reg, larghezza, altezza)
    # the "outer border" is the window's background: this way you can
    # see where the decoration ends
    sfondo = Image.new("RGB", (larghezza, altezza), (60, 20, 90))
    sfondo.paste(imm, (0, 0))
    uscita.parent.mkdir(parents=True, exist_ok=True)
    sfondo.save(uscita)
    print(f"  composed {larghezza}x{altezza} -> {uscita}")

    difetti = cuciture(imm)
    if difetti:
        print(f"  ✗ {len(difetti)} interior discontinuities:")
        for d in difetti:
            print(f"      {d}")
    else:
        print("  ✓ no seams: the strips are uniform")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
