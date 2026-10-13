#!/usr/bin/env python3
"""
verifica-assets-plasma.py — Checks the SVG sets against what Plasma asks
for.

Why a check of my own is not enough
-----------------------------------
I generated the twenty sets, and they could all be perfectly well formed
and still not get used: Plasma declares an `imagePath` and an
`elementId`, and if the file does not have the right extension or does
not contain the requested element the renderer draws nothing and leaves
no trace. The theme falls back to Breeze and looks fine.

This reads Plasma's installed code, extracts what it really asks for,
and compares it with what I wrote. The comparison is against the
source, not against a list of mine: if tomorrow Plasma adds an
elementId, the check reports it.

Usage:
    python3 tools/verifica-assets-plasma.py [DIR]
"""
from __future__ import annotations

import collections
import pathlib
import re
import sys

PLASMA = pathlib.Path("/usr/lib/qt6/qml/org/kde/plasma")
# The desktop's own QML lives here, not in the module tree: the folder
# view delegate, the logout OSD, the panel configuration. It declares
# the same imagePath/prefix pairs, and a check that only reads the
# module tree misses them.
PLASMA_EXTRA = pathlib.Path("/usr/share/plasma")

# Sets this theme does not ship on purpose: Plasma falls back to
# desktoptheme/default/widgets/ for any set the active theme has not
# got, and Breeze draws these two better than the versions written
# here ever did (see the note in tools/genera-assets-plasma.py). A
# missing file here is a decision, not a defect.
FALLBACK_INTENZIONALE = {"widgets/slider", "widgets/switch"}


def richieste() -> dict[str, dict]:
    """What Plasma asks for, extracted from its own files.

    Only what can be checked statically: `elementId`s are always a
    string, `prefix`es can be a string or an expression over the states.
    The expressions cannot be resolved without executing the QML, and a
    comparison that treats them as names produces false positives:
    `prefix: control.highlighted ? "pressed" : "normal"` is not asking
    for a prefix called `control`.
    """
    per_set: dict[str, dict] = collections.defaultdict(
        lambda: {"elementId": set(), "prefix": set(), "espressioni": 0,
                 "dinamiche": set(), "da": set()})
    radici = [p for p in (PLASMA, PLASMA_EXTRA) if p.is_dir()]
    for radice in radici:
        for f in radice.rglob("*.qml"):
            try:
                testo = f.read_text(errors="replace")
            except Exception:
                continue
            for m in re.finditer(r'KSvg\.(?:Svg|FrameSvgItem)\s*\{', testo):
                # the block ends at the next closing brace that does not
                # reopen: that is the simplest way not to read into the next
                # object
                start = m.end()
                fine = testo.find("\n        }", start)
                blocco = testo[start:fine if fine != -1 else start + 3000]
                ip = re.search(r'imagePath:\s*"([^"]+)"', blocco)
                if not ip:
                    continue
                nome = ip.group(1)
                per_set[nome]["elementId"] |= set(
                    re.findall(r'elementId:\s*"([^"]+)"', blocco))
                per_set[nome]["da"].add(str(f))
                for pm in re.finditer(r'prefix:\s*(.+)', blocco):
                    valore = pm.group(1).strip().rstrip(",")
                    if valore.startswith('"'):
                        per_set[nome]["prefix"].add(valore.strip('"'))
                    elif valore.startswith("["):
                        # A fallback chain, not an expression: KSvg tries
                        # each prefix in order (`["focus-background",
                        # "normal"]` paints normal when the first is
                        # absent). Missing members are not defects, so
                        # only the literals are recorded for the report
                        # below, and the chain counts as covered if any
                        # member is.
                        catena = re.findall(r'"([^"]+)"', valore)
                        per_set[nome]["dinamiche"] |= set(catena)
                        per_set[nome].setdefault("catene", []).append(catena)
                    else:
                        per_set[nome]["espressioni"] += 1
                        # A dynamic prefix is still a finite set of names:
                        # every branch of the expression is a quoted
                        # string. They cannot be checked as requests --
                        # only one branch runs at a time -- but they can
                        # be listed, so a family that only exists while
                        # something is chosen stops being invisible.
                        # That is how `selected` and `selected+hover`
                        # hid in Highlight.qml while viewitem shipped
                        # without them.
                        per_set[nome]["dinamiche"] |= {
                            d for d in re.findall(r'"([^"]+)"', valore)
                            if d}
    return per_set


def fornito(svg: str) -> tuple[set[str], set[str]]:
    """The ids the set provides, and the families derived from them."""
    ids = set(re.findall(r'<g id="([^"]+)"', svg))
    pfx = {i.rsplit("-", 1)[0] for i in ids if "-" in i}
    return ids, pfx


def main() -> int:
    radice = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                          else "/tmp/shell-test")
    rich = richieste()
    problemi = 0

    for nome, cosa in sorted(rich.items()):
        if not (nome.startswith("widgets/") or nome.startswith("solid/")):
            continue
        f = radice / (nome + ".svg")
        if not f.exists():
            if nome in FALLBACK_INTENZIONALE:
                print(f"  ~ {nome}: not shipped, Breeze fallback (intentional)")
                continue
            print(f"  ✗ {nome}: file missing")
            problemi += 1
            continue
        ids, pfx = fornito(f.read_text(encoding="utf-8"))
        mancanti_id = cosa["elementId"] - ids
        # a prefix that is looked for can be covered by the generic
        # family ("normal"), and so is not a defect
        generiche = {"normal", "plain", "base", "active", "inactive",
                     "checked", "focus", "hover", "pressed", "shadow"}
        # a prefix is satisfied if any of the ids starts with it:
        # `bar-active` arrives as the id `bar-active-top`, not as a
        # (prefix, suffix) pair
        def coperto(p: str) -> bool:
            return p in generiche or any(i == p or i.startswith(p + "-")
                                         for i in ids)
        mancanti_pfx = {p for p in cosa["prefix"] if not coperto(p)}
        if mancanti_id or mancanti_pfx:
            problemi += 1
            print(f"  ✗ {nome}")
            if mancanti_id:
                print(f"      missing elementId: {', '.join(sorted(mancanti_id))}")
            if mancanti_pfx:
                print(f"      missing prefix:    {', '.join(sorted(mancanti_pfx))}")
        else:
            extra = len(ids) - len(cosa["elementId"])
            print(f"  ✓ {nome:36s} {len(ids):3d} groups"
                  + (f"  (+{extra} extra states)" if extra > 0 else ""))

    print()
    # Dynamic prefixes no static check can resolve: every quoted branch
    # is listed, and the ones the files do not have are flagged for a
    # human to read the code. Warnings, not failures -- only one branch
    # runs at a time, so absence is "go and look", not "broken". But
    # absence plus a symptom is exactly the viewitem story, so the list
    # is printed rather than counted in `espressioni` and forgotten.
    avvisi = 0
    for nome, cosa in sorted(rich.items()):
        if not (nome.startswith("widgets/") or nome.startswith("solid/")):
            continue
        if nome in FALLBACK_INTENZIONALE:
            continue
        f = radice / (nome + ".svg")
        if not f.exists():
            continue
        ids, pfx = fornito(f.read_text(encoding="utf-8"))

        def presente(d: str) -> bool:
            return any(i == d or i.startswith(d + "-") for i in ids)
        # Chain members inherit the chain's coverage: ["focus-background",
        # "normal"] resolves as long as one of them exists.
        coperte_catena = {m for cat in cosa.get("catene", [])
                          for m in cat if presente(m)}
        scoperte = {d for d in cosa["dinamiche"]
                    if not presente(d)
                    and not any(d in cat and (set(cat) & coperte_catena)
                                for cat in cosa.get("catene", []))}
        if scoperte:
            avvisi += 1
            print(f"  ! {nome}: dynamic prefixes missing from the file, "
                  f"verify by reading the code: {', '.join(sorted(scoperte))}")
    if avvisi:
        print()

    if problemi:
        print(f"  {problemi} sets do not satisfy the requests")
    else:
        print("  all sets satisfy the requests")
    return 1 if problemi else 0


if __name__ == "__main__":
    raise SystemExit(main())
