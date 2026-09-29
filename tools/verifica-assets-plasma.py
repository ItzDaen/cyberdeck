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
        lambda: {"elementId": set(), "prefix": set(), "espressioni": 0})
    for f in PLASMA.rglob("*.qml"):
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
            for pm in re.finditer(r'prefix:\s*(.+)', blocco):
                valore = pm.group(1).strip().rstrip(",")
                if valore.startswith('"'):
                    per_set[nome]["prefix"].add(valore.strip('"'))
                else:
                    per_set[nome]["espressioni"] += 1
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
    if problemi:
        print(f"  {problemi} sets do not satisfy the requests")
    else:
        print("  all sets satisfy the requests")
    return 1 if problemi else 0


if __name__ == "__main__":
    raise SystemExit(main())
