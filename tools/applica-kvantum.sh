#!/usr/bin/env bash
# Applies the Kvantum configuration from the single source.
# The theme lives in src/, not in ~/.config: the configuration in
# ~/.config is a copy that gets regenerated, and keeping the original
# outside the repository makes it unversionable.
set -euo pipefail
cd "$(dirname "$0")/.."
DEST="$HOME/.config/Kvantum"
mkdir -p "$DEST"
install -m 644 src/theme/kvantum/Kvantum.kvconfig "$DEST/Kvantum.kvconfig"

python3 - <<'PY'
import pathlib, re
p = pathlib.Path.home() / ".config/kdeglobals"
s = p.read_text()
# `widgetStyle` only says "use the engine". The real style name is in
# Kvantum's own configuration, in [General] theme=.
if re.search(r"^widgetStyle=.*$", s, re.M):
    s = re.sub(r"^widgetStyle=.*$", "widgetStyle=Kvantum", s, flags=re.M)
else:
    s = s.replace("[KDE]\n", "[KDE]\nwidgetStyle=Kvantum\n", 1)
p.write_text(s)
print("  kdeglobals: widgetStyle=Kvantum")
PY
echo "  ✓ $DEST/Kvantum.kvconfig"
