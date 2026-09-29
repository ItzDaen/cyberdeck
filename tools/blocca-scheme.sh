#!/usr/bin/env bash
# ==============================================================================
# blocca-scheme.sh — Make the dark colour scheme the only one that sticks.
#
# What this is for
# ----------------
# There was a MeridianoLight. It was legible — 13.75:1 on the panel against a
# WCAG AA requirement of 4.5 — and it was removed anyway, along with its
# generator, so there is nothing of ours to switch to. `Breeze Light` and the
# other fourteen system schemes are still selectable from System Settings,
# though, and picking one used to take the whole identity with it:
#
#   - selecting a colour scheme runs kcminit
#   - kcminit rewrites ~/.config/kdeglobals from ~/.config/kdedefaults/
#   - kdedefaults/ was Breeze Dark's file with one line edited by hand
#   - so the icons went back to `breeze` and every surface went pale
#
# That chain is fixed at its source too: applying the Meridiano Global Theme
# writes kdedefaults/ from our own package, so a reset now lands back on the
# dark scheme instead of on Breeze. This script is the belt to that braces:
# with kdeglobals immutable, KConfig cannot write it at all, and a scheme
# change is refused rather than half-applied.
#
# The cost, stated plainly
# -----------------------
# Making the file immutable refuses EVERY write to it, not just the colour
# scheme. In practice that means:
#
#   - System Settings cannot save anything that lives in kdeglobals
#     (icon theme, contrast, animation factor)
#   - applying a Global Theme cannot persist its values
#   - kcminit fails at boot and prints a warning
#
# Measured after locking: Plasma logged no errors, the panel rendered, and
# `plasma-apply-colorscheme BreezeDark` reported success while leaving
# ColorScheme=Meridiano in place. Nothing has complained.
#
# If you ever need to change something in kdeglobals again:
#
#     tools/sblocca-scheme.sh        # unlock
#     <make the change>
#     tools/blocca-scheme.sh         # lock again
#
# Requires root: the immutable flag is a filesystem attribute.
# ==============================================================================
set -euo pipefail

KDEGLOBALS="$HOME/.config/kdeglobals"

if [[ ! -f "$KDEGLOBALS" ]]; then
    echo "blocca-scheme: $KDEGLOBALS does not exist" >&2
    exit 1
fi

# What is being locked, before it is locked.
SCHEME="$(kreadconfig6 --file "$KDEGLOBALS" --group General --key ColorScheme || true)"
ICONS="$(kreadconfig6 --file "$KDEGLOBALS" --group Icons --key Theme || true)"

sudo chattr +i "$KDEGLOBALS"

# Verified by attempting the write it is supposed to refuse, because a flag
# that was not set looks exactly like a flag that was set.
if kwriteconfig6 --file "$KDEGLOBALS" General cyberdeck_lock_probe 1 2>/dev/null; then
    sudo chattr -i "$KDEGLOBALS"
    kwriteconfig6 --file "$KDEGLOBALS" General cyberdeck_lock_probe 2>/dev/null || true
    echo "blocca-scheme: the write went through, the lock did not take" >&2
    exit 1
fi

printf 'blocca-scheme: %s is immutable.\n' "$KDEGLOBALS"
printf '  colour scheme : %s\n' "${SCHEME:-none}"
printf '  icon theme    : %s\n' "${ICONS:-none}"
printf '  a scheme change is refused rather than half-applied.\n'
printf '  unlock with tools/sblocca-scheme.sh\n'
