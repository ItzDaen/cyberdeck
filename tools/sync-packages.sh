#!/usr/bin/env bash
# ==============================================================================
# sync-packages.sh — Propagates src/ into the real installed locations.
#
# src/ is the single source of truth. This script copies into
# ~/.local/share/ and verifies the SHA256 after every copy, so a
# duplicate can no longer drift apart silently (which is exactly what
# happened with TelemetryHUD.qml: two byte-identical copies that nobody
# kept in step).
#
# Usage:
#   tools/sync-packages.sh            propagate everything
#   tools/sync-packages.sh --check    verify drift, write nothing
#   tools/sync-packages.sh --qml      propagate only the QML packages
#   tools/sync-packages.sh --web      propagate only the web dashboard
#   tools/sync-packages.sh --prune    remove from the destination the files
#                                     that no longer exist in src/ (opt-in:
#                                     it is the only destructive step here)
# ==============================================================================
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_SHARE="$HOME/.local/share"
DEST_BIN="$HOME/.local/bin"
DEST_SYSTEMD="$HOME/.config/systemd/user"
DEST_ZELLIJ="$HOME/.config/zellij/layouts"

MODE="sync"
SCOPE="all"
PRUNE=0
for arg in "$@"; do
    case "$arg" in
        --check) MODE="check" ;;
        --qml)   SCOPE="qml" ;;
        --web)   SCOPE="web" ;;
        --prune) PRUNE=1 ;;
    esac
done

GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RED=$'\e[31m'; DIM=$'\e[2m'; BOLD=$'\e[1m'; OFF=$'\e[0m'

FAILED=0
SYNCED=0
DRIFT=0
PRUNED=0

# ---------------------------------------------------------------------------
# sync_file <src> <dst>
# Copies (in sync mode) and always verifies the SHA256.
# ---------------------------------------------------------------------------
sync_file() {
    local src="$1" dst="$2"
    [[ -f "$src" ]] || { printf "  ${RED}✗ source missing:${OFF} %s\n" "$src"; FAILED=1; return; }

    local dst_dir; dst_dir="$(dirname "$dst")"
    [[ -d "$dst_dir" ]] || mkdir -p "$dst_dir"

    local want have
    want="$(sha256sum "$src" | cut -d' ' -f1)"

    if [[ -f "$dst" ]]; then
        have="$(sha256sum "$dst" | cut -d' ' -f1)"
        if [[ "$want" == "$have" ]]; then
            printf "  ${DIM}=${OFF} %s\n" "${dst/#$HOME/\~}"
            return
        fi
    fi

    if [[ "$MODE" == "check" ]]; then
        printf "  ${YELLOW}! drift${OFF} %s\n" "${dst/#$HOME/\~}"
        DRIFT=$((DRIFT+1))
        return
    fi

    # Atomic copy: tmp + mv, so an interruption never leaves a half
    # written file.
    cp -f "$src" "$dst.tmp$$" && mv -f "$dst.tmp$$" "$dst"
    have="$(sha256sum "$dst" | cut -d' ' -f1)"

    if [[ "$want" == "$have" ]]; then
        printf "  ${GREEN}✓${OFF} %s\n" "${dst/#$HOME/\~}"
        SYNCED=$((SYNCED+1))
    else
        printf "  ${RED}✗ post-copy checksum failed${OFF} %s\n" "${dst/#$HOME/\~}"
        FAILED=1
    fi
}

# ---------------------------------------------------------------------------
# sync_tree <src_dir> <dst_dir>
# Synchronises recursively, but NEVER deletes anything at the
# destination (safe: an extra file in ~/.local/share is not removed, only
# reported).
# ---------------------------------------------------------------------------
sync_tree() {
    local src_dir="$1" dst_dir="$2"
    [[ -d "$src_dir" ]] || return
    local rel f
    while IFS= read -r f; do
        rel="${f#"$src_dir"/}"
        sync_file "$f" "$dst_dir/$rel"
    done < <(find "$src_dir" -type f \
        ! -name '*.pyc' ! -path '*/__pycache__/*' \
        ! -name '.gitignore' ! -path '*/.git/*' | sort)
}

# ---------------------------------------------------------------------------
# prune_multi <dst_dir> <src_dir> [src_dir...]
# Removes from the destination the files that no longer have a
# counterpart in any of the given sources.
#
# Several sources because the Plasma packages are made of two trees: the
# package's own part plus src/qml/shared/ (Theme, TelemetryHUD, textures),
# which is copied into both. Pruning against a single tree would delete
# the shared files that were just synced.
#
# It is destructive, so only with an explicit --prune, and only inside
# directories the repo owns. Every removal is listed.
# ---------------------------------------------------------------------------
prune_multi() {
    local dst_dir="$1"; shift
    [[ -d "$dst_dir" ]] || return
    local f rel s inner alive
    while IFS= read -r f; do
        rel="${f#"$dst_dir"/}"
        inner="${rel#contents/ui/}"          # per i pacchetti Plasma
        alive=0
        for s in "$@"; do
            # A source can be either a package tree (full path) or the
            # shared tree (which is deposited inside contents/ui/, so the
            # path has to be straightened).
            if [[ -e "$s/$rel" ]] || { [[ "$rel" == contents/ui/* ]] && [[ -e "$s/$inner" ]]; }; then
                alive=1; break
            fi
        done
        [[ $alive -eq 1 ]] && continue

        if [[ "$MODE" == "check" ]]; then
            printf "  ${YELLOW}! obsolete${OFF} %s\n" "${f/#$HOME/\~}"
            DRIFT=$((DRIFT+1))
        else
            rm -f "$f"
            printf "  ${RED}− removed${OFF} %s\n" "${f/#$HOME/\~}"
            PRUNED=$((PRUNED+1))
        fi
    done < <(find "$dst_dir" -type f \
        ! -name '*.pyc' ! -path '*/__pycache__/*' \
        ! -name 'auth.token' ! -name '.gitignore' ! -path '*/.git/*' | sort)

    # Empty directories left by the prune (e.g. contents/ui/shaders/)
    find "$dst_dir" -type d -empty -delete 2>/dev/null || true
}

# ---------------------------------------------------------------------------
section() { printf "\n${BOLD}%s${OFF}\n" "$1"; }

# ═══════════════════════════════════════════════════════════════
if [[ "$SCOPE" == "all" || "$SCOPE" == "qml" ]]; then
    section "Plasma packages (QML)"

    # ── Shared component: one source, two destinations ──
    if [[ -d "$REPO/src/qml/shared" ]]; then
        # Two destinations. AudioSpectrum.qml used to live in the wallpaper
        # only, which is the same coupling that made the analyser vanish
        # with the wallpaper: it was part of a picture. It is in shared/ so
        # the wallpaper and the HUD can both reach it.
        #
        # There was a third, a `cyberdeck.spectrum` plasmoid, and it is
        # gone. A desktop widget of its own bought survival across a
        # wallpaper change and cost a second analyser per screen, a second
        # window to place, and a second thing that refused to move. The
        # spectrum is a section of the HUD panel instead: one object, one
        # lifetime, already movable, already on both screens.
        while IFS= read -r f; do
            rel="${f#"$REPO/src/qml/shared/"}"
            sync_file "$f" "$DEST_SHARE/plasma/plasmoids/cyberdeck.hud/contents/ui/$rel"
            sync_file "$f" "$DEST_SHARE/plasma/wallpapers/cyberdeck.instrument.field/contents/ui/$rel"
        done < <(find "$REPO/src/qml/shared" -type f | sort)
    fi

    # ── Plasmoid package (without shared/, already handled above) ──
    while IFS= read -r f; do
        rel="${f#"$REPO/src/qml/plasmoid/"}"
        [[ "$rel" == contents/ui/TelemetryHUD.qml ]] && continue   # vive in shared/
        sync_file "$f" "$DEST_SHARE/plasma/plasmoids/cyberdeck.hud/$rel"
    done < <(find "$REPO/src/qml/plasmoid" -type f ! -name '.gitignore' | sort)

    # ── Wallpaper package (same) ──
    while IFS= read -r f; do
        rel="${f#"$REPO/src/qml/wallpaper/"}"
        [[ "$rel" == contents/ui/TelemetryHUD.qml ]] && continue   # vive in shared/
        sync_file "$f" "$DEST_SHARE/plasma/wallpapers/cyberdeck.instrument.field/$rel"
    done < <(find "$REPO/src/qml/wallpaper" -type f ! -name '.gitignore' | sort)

    if [[ $PRUNE -eq 1 ]]; then
        prune_multi "$DEST_SHARE/plasma/plasmoids/cyberdeck.hud" \
                    "$REPO/src/qml/plasmoid" "$REPO/src/qml/shared"
        prune_multi "$DEST_SHARE/plasma/wallpapers/cyberdeck.instrument.field" \
                    "$REPO/src/qml/wallpaper" "$REPO/src/qml/shared"
    fi
fi

# ═══════════════════════════════════════════════════════════════
if [[ "$SCOPE" == "all" || "$SCOPE" == "web" ]]; then
    section "CyberDeck web (server + PWA)"
    sync_tree "$REPO/src/web" "$DEST_SHARE/cyberdeck"
fi

# ═══════════════════════════════════════════════════════════════
if [[ "$SCOPE" == "all" ]]; then
    section "CLI (bin)"
    # game-performance is in the list because it is a wrapper that calls
    # cyberhud, and a wrapper outside the repository does not get updated when
    # cyberhud's interface changes. It did, for months: the wrapper was
    # still passing `--auto` to a command where that flag now means "turn
    # performance mode off".
    for f in cyberdeck cyberhud cybercava-router.py cybercava-watchdog.sh cyberdeck-overhead game-performance; do
        [[ -f "$REPO/src/bin/$f" ]] && sync_file "$REPO/src/bin/$f" "$DEST_BIN/$f"
    done

    section "systemd (user units)"
    for f in "$REPO"/src/systemd/*.service "$REPO"/src/systemd/*.timer; do
        [[ -f "$f" ]] && sync_file "$f" "$DEST_SYSTEMD/$(basename "$f")"
    done

    section "zellij layout"
    [[ -f "$REPO/src/cyberdeck.kdl" ]] && sync_file "$REPO/src/cyberdeck.kdl" "$DEST_ZELLIJ/cyberdeck.kdl"

    # config.yaml yes: it is versioned now, so it is a source of truth
    # like the rest of src/. BUT this directory is never pruned: it also
    # holds auth.token, a secret generated on first start. It must not
    # enter the repo (it is in .gitignore) nor be touched from here.
    section "Meridiano theme"
    sync_tree "$REPO/src/theme" "$HOME/.local/share/meridiano-src"
    # The mirror is a copy of src/theme, so it has to lose what src/theme
    # loses. It did not: `switch.svg` and `slider.svg` left the source and
    # stayed in the mirror for the rest of time, which is how a file that
    # nothing reads any more keeps looking like part of the theme.
    if [[ $PRUNE -eq 1 ]]; then
        prune_multi "$HOME/.local/share/meridiano-src" "$REPO/src/theme"
    fi
    # Only the dark scheme. There was a MeridianoLight, generated by
    # tools/genera-scheme-light.py by preserving each role's contrast
    # ratio; it measured 13.75:1 on the panel and was legible. It was
    # removed on purpose, along with its generator, so there is
    # nothing to switch to.
    for f in color-schemes/Meridiano.colors; do
        sync_file "$REPO/src/theme/$f" "$HOME/.local/share/color-schemes/$(basename $f)"
    done
    # The Plasma style, and it has to be installed, not just carried.
    #
    # 17 widget SVGs plus solid/widgets/tooltip.svg, drawn for this theme
    # by tools/genera-assets-plasma.py. It was in the repository the whole
    # time and sync-packages.sh never copied it anywhere, so
    # `plasmarc [Theme] name=Meridiano` named a package that was not
    # installed. Plasma does not complain about that: it falls back to its
    # built-in defaults for every widget the style was supposed to draw.
    #
    # `switch.svg` and `slider.svg` used to be in this list. They are not,
    # and the comment that said they were is gone with them: Plasma falls
    # back to desktoptheme/default/widgets/ for any set a theme does not
    # ship, and Breeze's are better than the ones written here.
    #
    # It is installed TWICE, into two directories with the same name, and
    # that is not redundancy: `plasmarc [Theme] name` resolves to
    # plasma/desktoptheme/<name>/ for the nine-patch lookups, which is
    # where SwitchIndicator.qml's `imagePath: "widgets/switch"` lands.
    # Measured, not reasoned: a red 40x24 rectangle with a cyan handle was
    # written into each of the two in turn, plasmashell was restarted, and
    # the switch on screen turned red from plasma/desktoptheme/ and stayed
    # unchanged from plasma/themes/. Every symptom that survived the
    # switch fix -- the black dot, the black band on the selected tab, the
    # black box around a clicked panel item -- is this: the assets were
    # correct and were being read from a directory Plasma does not consult.
    # Both destinations are written from the same source and the checksum
    # is verified on each, so the two cannot drift apart again.
    if [[ -d "$REPO/src/theme/plasma-style/Meridiano" ]]; then
        for dest in "$HOME/.local/share/plasma/themes/Meridiano" \
                    "$HOME/.local/share/plasma/desktoptheme/Meridiano"; do
            sync_tree "$REPO/src/theme/plasma-style/Meridiano" "$dest"
            # sync_tree never deletes, which is right for everything else
            # here and wrong for this: a set we stop generating stays in
            # the theme and keeps being loaded, which is exactly how a
            # switch we had removed went on drawing for a month. The
            # theme trees are entirely ours, so obsolete files in them go
            # with --prune and only with it.
            if [[ $PRUNE -eq 1 ]]; then
                prune_multi "$dest" "$REPO/src/theme/plasma-style/Meridiano"
            fi
        done
    fi
    # The font choice reaches the desktop outside Plasma, through
    # fontconfig, so it has to be installed like everything else. The file
    # was in src/desktop/ from the start and nothing ever copied it: the
    # theme named IBM Plex as the system font and the desktop kept
    # whatever fontconfig resolved first.
    if [[ -d "$REPO/src/desktop" ]]; then
        for f in "$REPO"/src/desktop/*.conf; do
            [[ -f "$f" ]] && sync_file "$f" "$HOME/.config/fontconfig/$(basename "$f")"
        done
        fc-cache -f >/dev/null 2>&1
    fi

    # The window decoration, applied.
    #
    # The Aurorae theme is installed and had never been applied: kwinrc had
    # no [org.kde.kdecoration2] section at all, so KWin fell back to
    # kdedefaults and every window on this desktop was Breeze's. A theme
    # that ships a decoration and does not apply it is not a theme, it is a
    # folder.
    #
    # It is written here rather than left to the Global Theme because
    # `plasma-apply-lookandfeel` does not keep it: applying Meridiano
    # rewrote kwinrc and dropped the section, even though the package's
    # contents/defaults declares it with the same spelling Breeze's does.
    # Two keys, idempotent, printed so it is never a surprise.
    if [[ -f "$HOME/.local/share/aurorae/themes/Meridiano/Meridianorc" ]]; then
        python3 - "$HOME/.config/kwinrc" <<'APPLICA'
import pathlib, re, sys
p = pathlib.Path(sys.argv[1])
blocco = ("[org.kde.kdecoration2]\n"
          "library=org.kde.kwin.aurorae.v2\n"
          "theme=__aurorae__svg__Meridiano\n")
try:
    t = p.read_text(encoding="utf-8")
except OSError:
    t = ""
t = re.sub(r"\[org\.kde\.kdecoration2\].*?(?=\n\[|\Z)", "", t, flags=re.S)
t = t.rstrip("\n") + "\n\n" + blocco
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(t, encoding="utf-8")
print("    window decoration -> Aurorae / Meridiano")
APPLICA
    fi

    # The Aurorae decoration has to be regenerated: it is a product of
    # tools/genera-aurorae.py, not a hand-written file.
    if [ -x "$REPO/tools/genera-aurorae.py" ] || [ -f "$REPO/tools/genera-aurorae.py" ]; then
        python3 "$REPO/tools/genera-aurorae.py" \
            --out "$HOME/.local/share/aurorae/themes/Meridiano" | sed 's/^/    /'
    fi
    # The Global Theme, so the whole identity is one selectable entry instead
    # of four settings in four files. It is a KPackage, so it goes to
    # look-and-feel/ -- which is where Plasma's own Global Themes live on this
    # system (org.kde.breeze.desktop and friends), and not to a globals/
    # directory that does not exist here.
    sync_tree "$REPO/src/theme/look-and-feel/Meridiano" \
              "$HOME/.local/share/plasma/look-and-feel/Meridiano"

    # Report, never act. The dark scheme is enforced by making
    # ~/.config/kdeglobals immutable, which needs root and therefore cannot
    # happen as a side effect of a deploy -- see tools/blocca-scheme.sh for
    # what it costs and tools/sblocca-scheme.sh to undo it. This only says
    # whether the guarantee is still in place, because a lock that silently
    # disappeared would leave the identity one colour-scheme click from gone.
    if [[ -f "$HOME/.config/kdeglobals" ]]; then
        if kwriteconfig6 --file "$HOME/.config/kdeglobals" General cyberdeck_lock_probe 1 2>/dev/null; then
            kwriteconfig6 --file "$HOME/.config/kdeglobals" General cyberdeck_lock_probe 2 2>/dev/null || true
            printf "    ${YELLOW}!${OFF} kdeglobals is writable: the colour scheme can be switched\n"
            printf "      ${DIM}tools/blocca-scheme.sh to lock it again${OFF}\n"
        else
            printf "    ${DIM}kdeglobals immutable: the colour scheme cannot be switched${OFF}\n"
        fi
    fi

    section "Configuration"
    sync_file "$REPO/src/config/config.yaml" "$HOME/.config/cyberdeck/config.yaml"
    # The animated-wallpaper list is seeded, not synchronised. It is the
    # user's own statement about which of their wallpapers animate, so
    # overwriting it on every deploy would throw away the lines they
    # added. Written once, then left alone; the repository keeps the
    # documented default for a fresh install.
    LIST="$HOME/.config/cyberdeck/animated-wallpapers.list"
    if [[ -f "$REPO/src/config/animated-wallpapers.list" && ! -f "$LIST" ]]; then
        cp "$REPO/src/config/animated-wallpapers.list" "$LIST"
        printf "    ${GREEN}seeded${OFF}  %s\n" "$LIST"
    elif [[ -f "$LIST" ]]; then
        printf "    ${DIM}kept${OFF}      %s (yours, never overwritten)\n" "$LIST"
    fi
fi

# ═══════════════════════════════════════════════════════════════
printf "\n"
if [[ $FAILED -gt 0 ]]; then
    printf "${RED}${BOLD}✗ sync failed${OFF} — no deploy considered valid.\n"; exit 1
fi
if [[ "$MODE" == "check" ]]; then
    if [[ $DRIFT -gt 0 ]]; then
        printf "${YELLOW}${BOLD}! %d files in drift${OFF} between src/ and ~/.local/share/\n" "$DRIFT"; exit 2
    fi
    printf "${GREEN}${BOLD}✓ no drift${OFF} — ~/.local/share/ matches src/\n"
else
    printf "${GREEN}${BOLD}✓ %d files synced${OFF}" "$SYNCED"
    [[ $PRUNED -gt 0 ]] && printf ", ${RED}%d obsolete removed${OFF}" "$PRUNED"
    printf "\n"
fi
