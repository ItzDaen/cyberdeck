#!/usr/bin/env bash
# ==============================================================================
# sblocca-scheme.sh — Release the immutable flag on kdeglobals.
#
# The counterpart of tools/blocca-scheme.sh, and the only thing that needs
# running when a setting in kdeglobals has to change again: the icon theme,
# the contrast, the animation factor, or the colour scheme itself.
#
# After changing what you went in for:
#
#     tools/blocca-scheme.sh
#
# Leaving it unlocked is a choice with a consequence, not a neutral state:
# a colour scheme change runs kcminit, kcminit rewrites kdeglobals from
# kdedefaults/, and if that defaults file is not ours the whole identity
# goes with it. See tools/blocca-scheme.sh for the chain.
# ==============================================================================
set -euo pipefail

KDEGLOBALS="$HOME/.config/kdeglobals"

if [[ ! -f "$KDEGLOBALS" ]]; then
    echo "sblocca-scheme: $KDEGLOBALS does not exist" >&2
    exit 1
fi

sudo chattr -i "$KDEGLOBALS"

# Verified the same way the lock is: attempt the write it should now allow.
if kwriteconfig6 --file "$KDEGLOBALS" General cyberdeck_lock_probe 2 2>/dev/null; then
    printf 'sblocca-scheme: %s is writable again.\n' "$KDEGLOBALS"
    printf '  colour scheme : %s\n' \
        "$(kreadconfig6 --file "$KDEGLOBALS" --group General --key ColorScheme || echo none)"
    printf '  remember tools/blocca-scheme.sh when you are done.\n'
else
    printf 'sblocca-scheme: still not writable, something else is holding it\n' >&2
    exit 1
fi
