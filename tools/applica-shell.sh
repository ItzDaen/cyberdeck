#!/usr/bin/env bash
# Installs the Plasma shell theme from the single source.
set -euo pipefail
cd "$(dirname "$0")/.."
SRC="src/theme/plasma-style/Meridiano"
DEST="$HOME/.local/share/plasma/desktoptheme/Meridiano"
[ -d "$SRC" ] || { echo "  ✗ missing: $SRC"; exit 1; }
rm -rf "$DEST"
cp -r "$SRC" "$DEST"

python3 tools/verifica-assets-plasma.py "$DEST" >/dev/null

python3 - <<'PY'
import pathlib, re
p = pathlib.Path.home() / ".config/plasmarc"
s = p.read_text() if p.exists() else ""
if re.search(r"^name=.*$", s, re.M):
    s = re.sub(r"^name=.*$", "name=Meridiano", s, flags=re.M)
else:
    s = "[Theme]\nname=Meridiano\n"
p.write_text(s)
PY
echo "  ✓ $DEST"
echo "  plasmarc: name=Meridiano"
