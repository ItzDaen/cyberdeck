#!/usr/bin/env python3
"""
applica-konsole.py — Puts the Meridiano palette into Konsole.

Why a script and not two files by hand
--------------------------------------
Konsole holds three things in three places: the profile that names the
scheme, the scheme with the colours, and the style sheet for the tabs.
Change one and forget the other and Konsole starts with a mix of two
themes, with no error at all — just a half-themed terminal.

The colours here are in hex and not in `ColorScheme-*` classes, which
do not exist in Qt: the tabs are drawn by Qt, not by KSVGFrenchy. So
the values are written down and have to be kept aligned by hand, and
keeping two places aligned is exactly the job a script does better.
"""

from __future__ import annotations

import configparser
import pathlib
import shutil
import sys

UTENTE = pathlib.Path.home() / ".local"
KONSOLE = UTENTE / "share/konsole"
SORGENTE = pathlib.Path(__file__).resolve().parent.parent / "src/theme/konsole"

PROFILO = "Meridiano"
SCHEMA = "Meridiano.colorscheme"
FOGLIO = "meridiano.qss"


def scrivi_profilo(percorso: pathlib.Path) -> None:
    """The profile: names the scheme and the style sheet.

    If the profile does not exist it is created with the bare minimum.
    Konsole expects a profile with certain keys: without them it does
    not start.
    """
    nuovo = not percorso.exists()
    cp = configparser.RawConfigParser()
    cp.optionxform = str
    if not nuovo:
        cp.read(percorso, encoding="utf-8")
    if not cp.has_section("General"):
        cp.add_section("General")
    cp.set("General", "Name", PROFILO)
    cp.set("General", "ColorScheme", SCHEMA.replace(".colorscheme", ""))
    cp.set("General", "Font", "IBM Plex Mono,11,-1,5,50,0,0,0,0,0")
    cp.set("General", "TerminalColumns", "120")
    cp.set("General", "TerminalRows", "30")
    cp.set("General", "TerminalColor", "1")          # custom colours
    cp.set("General", "TerminalOpacity", "100")
    # The background colour comes from the scheme; with TerminalColor=1
    # Konsole asks for a background colour of its own and otherwise puts
    # a random one over the scheme's.
    with percorso.open("w", encoding="utf-8") as f:
        cp.write(f, space_around_delimiters=False)
    return


def main() -> int:
    for nome in (SCHEMA, FOGLIO):
        if not (SORGENTE / nome).exists():
            print(f"  ✗ missing {SORGENTE / nome}", file=sys.stderr)
            return 2
    KONSOLE.mkdir(parents=True, exist_ok=True)

    for nome in (SCHEMA, FOGLIO):
        shutil.copy2(SORGENTE / nome, KONSOLE / nome)
        print(f"  ✓ {KONSOLE / nome}")

    scrivi_profilo(KONSOLE / f"{PROFILO}.profile")

    # The default profile: this is the step that gets forgotten, and
    # without it Konsole keeps using the old theme without saying
    # anything.
    k = pathlib.Path.home() / ".config/konsolerc"
    cp = configparser.RawConfigParser()
    cp.optionxform = str
    if k.exists():
        cp.read(k, encoding="utf-8")
    if not cp.has_section("Desktop Entry"):
        cp.add_section("Desktop Entry")
    cp.set("Desktop Entry", "DefaultProfile", f"{PROFILO}.profile")
    if not cp.has_section("TabBar"):
        cp.add_section("TabBar")
    cp.set("TabBar", "TabBarUserStyleSheetFile", f"file://{KONSOLE / FOGLIO}")
    with k.open("w", encoding="utf-8") as f:
        cp.write(f, space_around_delimiters=False)
    print(f"  ✓ {k}: DefaultProfile={PROFILO}, sheet={FOGLIO}")
    print()
    print("  Konsole has to be restarted: it holds the scheme in memory,")
    print("  the way Aurorae holds the buttons. You can do that from the")
    print("  window you have open.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
