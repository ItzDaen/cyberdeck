#!/usr/bin/env python3
"""
verifica-decorazione.py — Photographs the title bar of a test window and
says whether the buttons are there.

Why it exists
-------------
Until not long ago the check consisted of opening a kdialog, finding
the window in the screenshot by eye, cropping and looking. Two flaws:
the windows stayed open and you had to close them by hand, and the crop
depended on where the window happened to end. I lost a dozen trials to
working out whether I was looking at the right window.

Here the test window has a colour that exists nowhere else on the
desktop (magenta), says where it is and how wide it is, and closes
itself after nine seconds. The screenshot is cropped automatically on
that colour: if the window is not there it says so, instead of leaving
me to interpret the wrong picture.

Usage:
    python3 tools/verifica-decorazione.py [nome-tema]
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import time

from PIL import Image

# Has to match tools/finestra-prova.qml
COLORE = (0xFF, 0x00, 0xFF)
TOLLERANZA = 8
DAL = "/usr/lib/qt6/bin/qml"
PROVA = pathlib.Path(__file__).with_name("finestra-prova.qml")
SCHERMO = pathlib.Path("/tmp/verifica-decorazione.png")
ZOOM = pathlib.Path("/tmp/verifica-decorazione-zoom.png")


def cattura() -> Image.Image:
    ambiente = {
        **dict(__import__("os").environ),
        "WAYLAND_DISPLAY": "wayland-0",
        "XDG_SESSION_TYPE": "wayland",
    }
    SCHERMO.unlink(missing_ok=True)
    subprocess.run(["spectacle", "-b", "-n", "-o", str(SCHERMO)],
                   env=ambiente, capture_output=True, timeout=40)
    return Image.open(SCHERMO).convert("RGB")


def ritrova(px, larghezza: int) -> tuple[int, int, int] | None:
    """The top-left edge of the magenta block: (x, y, xmax)."""
    def magenta(c):
        return all(abs(a - b) <= TOLLERANZA for a, b in zip(c, COLORE))
    for y in range(0, 1080):
        riga = [x for x in range(0, larghezza) if magenta(px[x, y])]
        if len(riga) > 60:            # a full strip, not a single pixel
            return riga[0], y, riga[-1]
    return None


def main() -> int:
    tema = sys.argv[1] if len(sys.argv) > 1 else "(the active one)"
    print(f"  decorazione: {tema}")

    proc = subprocess.Popen([DAL, str(PROVA)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)
    try:
        im = cattura()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    px = im.load()
    trovato = ritrova(px, im.size[0])
    if not trovato:
        print("  ✗ test window not found in the screenshot")
        return 2

    x, y, xmax = trovato
    print(f"  window: x {x}..{xmax}  y {y} (magenta body)")

    # The title bar sits above the body, as tall as TitleHeight plus the
    # borders. I crop a generous strip and look at it.
    alto = 40
    ritaglio = im.crop((x - 16, max(0, y - alto), xmax + 16, y + 2))
    ritaglio = ritaglio.resize((ritaglio.width * 5, ritaglio.height * 5),
                               Image.NEAREST)
    ritaglio.save(ZOOM)
    print(f"  crop: {ZOOM}")

    # The buttons: I look for pixels belonging neither to the bar's
    # background nor to its border, within the right half.
    barra = im.crop((x, max(0, y - alto), xmax, y))
    bp = barra.load()
    larghezza, altezza = barra.size
    marcati = 0
    for yy in range(altezza):
        for xx in range(larghezza // 2, larghezza):
            r, g, b = bp[xx, yy]
            if r > 90 or g > 90 or b > 90:      # above the background threshold
                marcati += 1
    print(f"  non-background pixels in the right half: {marcati}")
    print("  → open /tmp/verifica-decorazione-zoom.png and look")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
