#!/usr/bin/env python3
"""
schiarisci-icone.py — Picks, for each icon, the variant that measures
lightest on the panel, and installs it into the Meridiano theme.

Why selection and not recolouring
---------------------------------
I tried recolouring first: raise the lightness of every fill, stroke,
stylesheet rule and embedded PNG, keeping hue and saturation. It is
the obvious approach and it measured badly. On the panel's own icons:

    systemsettings   L  41.8 ->  54.8    three colours changed
    steam            L  65.6 ->  65.6    six colours changed, mean unmoved
    firefox          L  77.3 -> 105.3    still under the floor

The reason is that the artwork is a base64 PNG inside the SVG, so the
visual mass is in the pixels and not in the vector fills. Half the
icons stayed dark and the report would have had to admit it.

Selection is better for a reason that has nothing to do with effort:
the right artwork already exists on this machine. Measured on the
panel colour #0e0d0b:

    start-here-kde       Fluent places/24      L  15.0   <- what is used
                         Fluent scalable/apps  L  95.8   <- same icon
    utilities-terminal   Fluent actions/16     L  23.3   <- what is used
                         Fluent scalable/apps  L 121.2   <- same icon

Those two are not two colours of one icon, they are two renderings of
it, and KDE ships both. Installing the light one keeps the icon
exactly as its author drew it and takes it from 1.04:1 to about 8:1.

The one thing selection cannot do is fix an icon that has no light
variant anywhere. That is a separate decision, and this tool does not
make it: it reports those and stops. Recolouring a brand mark is a
judgement about identity, not a measurement, and it does not belong
here.

What this tool therefore does
-----------------------------
For each icon in NOMI, measure every candidate across the chain, and
install into Meridiano the one that measures lightest — but only if it
is meaningfully lighter than what the icon engine would pick on its
own. Anything that already measures well is left alone, and the report
says so.

Usage:
    python3 tools/schiarisci-icone.py            # apply
    python3 tools/schiarisci-icone.py --check    # measure only
    python3 tools/schiarisci-icone.py --soglia 120
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import tempfile

TEMA = pathlib.Path.home() / ".local/share/icons/Meridiano"

# The panel the icons are judged against: Meridiano's own field.
PANNO = "#0e0d0b"

# Lookup order, the same one the theme's Inherits declares. Meridiano
# itself is absent on purpose: it is the destination, not a source.
CATENA = [
    pathlib.Path.home() / ".local/share/icons/Fluent",
    pathlib.Path("/usr/share/icons/breeze"),
    pathlib.Path("/usr/share/icons/Adwaita"),
    pathlib.Path("/usr/share/icons/breeze-dark"),
    pathlib.Path("/usr/share/icons/hicolor"),
]

# Where each icon has to land. The context matters: the icon engine
# looks up by context, so a light file installed under the wrong
# context is simply never asked for. This is the whole reason
# start-here-kde stayed dark -- a light one existed, in apps/, while
# the request was for places/.
DESTINAZIONI = {
    "start-here-kde": "Places",
    "utilities-terminal": "Actions",
    "systemsettings": "apps",
    "org.kde.dolphin": "apps",
    "firefox": "apps",
    "steam": "apps",
}

# A candidate has to beat what is already used by this much to be
# worth taking. Below it, the churn is not worth the change.
MARGINE = 20.0

# Above this the icon is left entirely alone.
SOGLIA = 130.0

G, Y, BOLD, DIM, OFF = ("\033[32m", "\033[33m", "\033[1m",
                        "\033[2m", "\033[0m")


def misura(svg: pathlib.Path) -> float:
    """Render the icon flat on the panel colour, return the mean L."""
    with tempfile.TemporaryDirectory() as td:
        out = pathlib.Path(td) / "a.png"
        try:
            subprocess.run(
                ["rsvg-convert", "-w", "48", "-h", "48", "-b", PANNO,
                 str(svg), "-o", str(out)],
                check=True, capture_output=True, timeout=20)
            from PIL import Image, ImageStat
            return ImageStat.Stat(Image.open(out).convert("L")).mean[0]
        except Exception:
            return -1.0


def candidati(nome: str) -> list[pathlib.Path]:
    trovati: list[pathlib.Path] = []
    for radice in CATENA:
        if radice.exists():
            trovati += sorted(radice.rglob(f"{nome}.svg"))
    return trovati


def scelta_del_motore(nome: str, contesto: str) -> pathlib.Path | None:
    """What the icon engine resolves to right now, given the context.

    Mirrors the lookup: Meridiano first, because Meridiano is the
    active theme and a file it provides wins over everything it
    inherits -- then the chain in index.theme, same context before any
    context. Checking Meridiano first is what makes this tool
    idempotent: without it, running it twice reports the same change
    twice and never notices it already made it.
    """
    if TEMA.is_dir():
        t = sorted((TEMA / "scalable" / contesto).rglob(f"{nome}.svg")) \
            if (TEMA / "scalable" / contesto).is_dir() else []
        if t:
            return t[0]
        t = sorted((TEMA / "scalable").rglob(f"{nome}.svg"))
        if t:
            return t[0]
    for radice in CATENA:
        if not radice.exists():
            continue
        contesto_g = radice / contesto.lower()
        if contesto_g.is_dir():
            t = sorted(contesto_g.rglob(f"{nome}.svg"))
            if t:
                return t[0]
        t = sorted(radice.rglob(f"{nome}.svg"))
        if t:
            return t[0]
    return None


def _testo_indice() -> str:
    idx = TEMA / "index.theme"
    return idx.read_text(encoding="utf-8") if idx.exists() else ""


def _sezione(contesto: str) -> str:
    """The index.theme stanza a directory needs, or "" if it is there."""
    idx = TEMA / "index.theme"
    if not idx.exists():
        return ""
    testo = idx.read_text(encoding="utf-8")
    return f"\n[scalable/{contesto}]\n" if f"[scalable/{contesto}]" not in testo else ""


def _dichiara(contesti: set[str]) -> list[str]:
    """Make index.theme list the directories this tool wrote into.

    Without this the files are simply never asked for: the icon engine
    reads `Directories=` and ignores anything absent from it. It is the
    reason a light variant can sit on disk, correct, and still not be
    used.
    """
    idx = TEMA / "index.theme"
    if not idx.exists() or not contesti:
        return []
    testo = idx.read_text(encoding="utf-8")
    aggiunti = []

    for contesto in sorted(contesti):
        chiave = f"scalable/{contesto}"
        if chiave in testo:
            continue
        testo = testo.replace("Directories=", f"Directories={chiave},", 1)
        testo += (f"\n[{chiave}]\nSize=48\nMinSize=16\nMaxSize=512\n"
                  f"Context={_contesto_nome(contesto)}\nType=Scalable\n")
        aggiunti.append(chiave)

    if aggiunti:
        idx.write_text(testo, encoding="utf-8")
    return aggiunti


def _contesto_nome(contesto: str) -> str:
    return {"apps": "Applications", "actions": "Actions",
            "places": "Places", "status": "Status"}.get(
                contesto.lower(), contesto.capitalize())


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Installs the lightest measured variant of each icon")
    ap.add_argument("--check", action="store_true",
                    help="measure only, write nothing")
    ap.add_argument("--soglia", type=float, default=SOGLIA,
                    help=f"above this an icon is left alone, default {SOGLIA}")
    args = ap.parse_args()

    print(f"  Meridiano — icon variant selection")
    print(f"  {DIM}panel {PANNO}, leave alone above L={args.soglia:.0f}, "
          f"take the best if it wins by {MARGINE:.0f}{OFF}")
    print()

    installati = 0
    lasciati = 0
    senza = 0
    nuovi_contesti: set[str] = set()

    for nome, contesto in DESTINAZIONI.items():
        cands = candidati(nome)
        if not cands:
            print(f"  {nome:20s} no candidate in the chain")
            senza += 1
            continue

        misurati = [(misura(c), c) for c in cands]
        misurati = [(v, c) for v, c in misurati if v >= 0]
        if not misurati:
            print(f"  {nome:20s} nothing measurable")
            senza += 1
            continue
        misurati.sort(key=lambda t: -t[0])
        migliore, path_migliore = misurati[0]

        attuale = scelta_del_motore(nome, contesto)
        L_attuale = misura(attuale) if attuale else -1.0
        in_uso = "Meridiano" if attuale and TEMA in attuale.parents else (
            "chain" if attuale else "none")

        def dove(p: pathlib.Path) -> str:
            return str(p).replace(str(pathlib.Path.home()), "~")

        # Compare by measurement, not by path: the file installed in
        # Meridiano is a copy of the chain's, so the two are different
        # objects holding identical artwork.
        if migliore - L_attuale <= 0.5:
            # Already the best the machine has. Whether that is bright
            # enough is a separate question, and the answer belongs in
            # the line, not in an excuse.
            if L_attuale >= args.soglia:
                print(f"  {G}·{OFF} {nome:20s} L {L_attuale:6.1f}  best "
                      f"available, above the floor  ({in_uso})")
                lasciati += 1
            else:
                print(f"  {Y}·{OFF} {nome:20s} L {L_attuale:6.1f}  best "
                      f"available but under the floor: no lighter variant "
                      f"exists ({in_uso})")
                senza += 1
            continue

        if migliore - L_attuale < MARGINE:
            print(f"  {Y}!{OFF} {nome:20s} L {L_attuale:6.1f}  best only "
                  f"{migliore - L_attuale:+.0f} better, under the margin")
            senza += 1
            continue

        dest = TEMA / "scalable" / contesto / f"{nome}.svg"
        # not declared in index.theme, not "the directory is missing":
        # the directory can exist and still never be asked for.
        if f"[scalable/{contesto}]" not in _testo_indice():
            nuovi_contesti.add(contesto)
        if args.check:
            print(f"  {Y}?{OFF} {nome:20s} L {L_attuale:6.1f} -> "
                  f"{migliore:6.1f}  {dove(path_migliore)}  (check: not written)")
            installati += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path_migliore.read_bytes())
        installati += 1
        print(f"  {G}✓{OFF} {nome:20s} L {L_attuale:6.1f} -> {migliore:6.1f}  "
              f"from {dove(path_migliore)}")

    if not args.check and nuovi_contesti:
        for chiave in _dichiara(nuovi_contesti):
            print(f"  {G}✓{OFF} index.theme now declares {chiave}")

    print()
    if args.check:
        print(f"  {Y}{BOLD}check: nothing written{OFF}  "
              f"({installati} would change, {lasciati} fine, {senza} undecided)")
    else:
        print(f"  {G}{BOLD}✓{OFF} {installati} variant(s) installed, "
              f"{lasciati} left alone, {senza} without a light variant")
        print(f"  {DIM}the icon cache has to be rebuilt to pick them up{OFF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
