#!/usr/bin/env bash
# ==============================================================================
# install.sh — Full deploy: src/ -> real locations + service reload.
#
#   tools/install.sh              full deploy
#   tools/install.sh --no-restart deploy without touching the services
#   tools/install.sh --prune      deploy + removal of obsolete files
#   tools/install.sh --restart-plasma  deploy + plasmashell restart
# ==============================================================================
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESTART_SERVICES=1
RESTART_PLASMA=0
PRUNE=0

for arg in "$@"; do
    case "$arg" in
        --no-restart)     RESTART_SERVICES=0 ;;
        --restart-plasma) RESTART_PLASMA=1 ;;
        --prune)          PRUNE=1 ;;
    esac
done

GREEN=$'\e[32m'; RED=$'\e[31m'; BOLD=$'\e[1m'; DIM=$'\e[2m'; OFF=$'\e[0m'

printf "${BOLD}CyberDeck deploy${OFF}  ${DIM}%s${OFF}\n" "$REPO"

# ── 1. Snapshot the desktop before touching anything ──────────
# Writing to the appletsrc can break the whole desktop: always copy first.
SNAP="$HOME/.cache/cyberdeck-deploy"
mkdir -p "$SNAP"
cp -f "$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc" \
      "$SNAP/desktop-appletsrc.$(date +%Y%m%d-%H%M%S).bak" 2>/dev/null \
   && printf "  ${DIM}snapshot desktop: $SNAP${OFF}\n"

# ── 2. Propagate the sources ─────────────────────────────────────
if [[ $PRUNE -eq 1 ]]; then
    "$REPO/tools/sync-packages.sh" --prune || {
        printf "\n${RED}${BOLD}✗ deploy abortito: sync fallito.${OFF}\n"; exit 1
    }
else
    "$REPO/tools/sync-packages.sh" || {
        printf "\n${RED}${BOLD}✗ deploy abortito: sync fallito.${OFF}\n"; exit 1
    }
fi

# ── 3. Executable permissions ────────────────────────────────────
chmod +x "$HOME/.local/bin/cyberdeck" \
         "$HOME/.local/bin/cyberhud" \
         "$HOME/.local/bin/cybercava-router.py" \
         "$HOME/.local/bin/cybercava-watchdog.sh" \
         "$HOME/.local/bin/cyberdeck-overhead" 2>/dev/null

# ── 4. Reload services ──────────────────────────────────────────
if [[ $RESTART_SERVICES -eq 1 ]]; then
    printf "\n${BOLD}Reload servizi${OFF}\n"
    if systemctl --user cat cyberdeck.service >/dev/null 2>&1; then
        systemctl --user daemon-reload
        systemctl --user restart cyberdeck.service
        printf "  ${GREEN}✓${OFF} cyberdeck.service\n"
    fi
    for u in cybercava-router.service cybercava-watchdog.timer; do
        if systemctl --user cat "$u" >/dev/null 2>&1; then
            systemctl --user restart "$u" 2>/dev/null \
                && printf "  ${GREEN}✓${OFF} %s\n" "$u"
        fi
    done
fi

# ── 5. Plasma ──────────────────────────────────────────────────
if [[ $RESTART_PLASMA -eq 1 ]]; then
    printf "\n${BOLD}Riavvio plasmashell${OFF}\n"
    systemctl --user restart plasma-plasmashell.service
    printf "  ${GREEN}✓${OFF} plasma-plasmashell.service\n"
fi

printf "\n${GREEN}${BOLD}✓ deploy completato${OFF}\n"
