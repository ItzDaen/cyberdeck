#!/usr/bin/env python3
"""
verifica-tema — Checks that the applied theme matches the model.

The kind of check, and why this one and not another
──────────────────────────────────────────────────
The most insidious error of the whole theme build was this: the
`.colors` file was right, `ColorScheme=Meridiano` was set, and
everything looked fine — but `kdeglobals` still held the previous
theme's values, and the windows kept showing those colours. In KDE 6 the
`.colors` file is a model: the values have to be copied into
`~/.config/kdeglobals`, which is the only file applications read.

So this compares the two, which is the only comparison that says
anything true.

A note on what it does NOT measure: the palette cannot be verified with
PySide6. A bare Qt application does not load KDE's platform theme
plugin, so `QApplication::palette()` returns Qt's default palette and
the comparison would give thirteen false negatives. Verification at
application level needs a real KDE application and has to be done by
looking at the screen.

Usage:
    python3 tools/verifica-tema.py
"""

import configparser
import sys
from pathlib import Path

HOME = Path.home()
KDEGLOBALS = HOME / ".config" / "kdeglobals"
MODELLO = (Path(__file__).resolve().parent.parent / "src" / "theme"
           / "color-schemes" / "Meridiano.colors")

# The roles that actually matter: the ones the eyes see.
CRITICI = [
    ("Colors:Window",    "BackgroundNormal",  "14,13,11",    "window background"),
    ("Colors:Window",    "ForegroundNormal",  "232,228,220", "normal text"),
    ("Colors:Window",    "DecorationFocus",   "255,157,46",  "focus border"),
    ("Colors:View",      "BackgroundNormal",  "26,25,23",    "surfaces, fields, lists"),
    ("Colors:View",      "ForegroundNormal",  "232,228,220", "text on surfaces"),
    ("Colors:Button",    "BackgroundNormal",  "34,32,29",    "buttons"),
    ("Colors:Button",    "ForegroundNormal",  "232,228,220", "button text"),
    ("Colors:Header",    "BackgroundNormal",  "20,19,17",    "bars and headings"),
    ("Colors:Selection", "BackgroundNormal",  "255,157,46",  "selection: lit amber"),
    ("Colors:Selection", "ForegroundNormal",  "14,13,11",    "text on selection"),
    ("Colors:Tooltip",   "BackgroundNormal",  "232,228,220", "light tooltip"),
    ("Colors:Tooltip",   "ForegroundNormal",  "14,13,11",    "tooltip text"),
]

G, R, DIM, B, O = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def leggi(path: Path) -> configparser.RawConfigParser:
    cp = configparser.RawConfigParser(strict=False)
    cp.optionxform = str
    cp.read(path, encoding="utf-8")
    return cp


def main() -> None:
    for p, etichetta in ((KDEGLOBALS, "kdeglobals"), (MODELLO, "model")):
        if not p.exists():
            print(f"  {R}✗{O} not found: {etichetta}: {p}")
            sys.exit(1)

    cfg = leggi(KDEGLOBALS)
    mod = leggi(MODELLO)

    print(f"  {DIM}{'role':34} {'value':16} result{O}")
    print("  " + "-" * 60)

    falliti = 0
    for sez, chiave, atteso, descrizione in CRITICI:
        reale = cfg[sez].get(chiave) if cfg.has_section(sez) else None
        modello = mod[sez].get(chiave) if mod.has_section(sez) else None

        if reale == atteso:
            segno = f"{G}✓{O}"
        elif reale == modello and modello != atteso:
            segno = f"{R}✗{O}"
        else:
            segno = f"{R}?{O}"
        if reale != atteso:
            falliti += 1

        etichetta_r = f"{sez[7:]}.{chiave}"
        print(f"  {etichetta_r:34} {str(reale):16} {segno}  {DIM}{descrizione}{O}")

    # ── Overall consistency ──
    print()
    schema = cfg["General"].get("ColorScheme") if cfg.has_section("General") else None
    hash_presente = (cfg["General"].get("ColorSchemeHash") is not None
                     if cfg.has_section("General") else False)

    print(f"  {DIM}declared scheme{O}   {schema}")
    print(f"  {DIM}cached hash{O}       "
          f"{'present — open apps still hold the old palette' if hash_presente else 'absent, correct'}")

    if falliti:
        print(f"\n{R}{B}  ✗ {falliti} roles do not match the theme{O}")
        print("    Probably `meridiano-apply` has not been run.")
    else:
        print(f"\n{G}{B}  ✓ kdeglobals matches the Meridiano theme{O}")
        print(f"    {DIM}Application-level check: open a KDE app{O}")
    sys.exit(1 if falliti else 0)


if __name__ == "__main__":
    main()
