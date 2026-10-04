#!/bin/bash
# Author: Daen
# CyberCAVA watchdog v1.0 - ensures dock CAVA never stops definitively
# Checks: router alive, >=2 cava processes (2 panels), backend reachable
LOG_TAG="cybercava-watchdog"
fail=0
if ! systemctl --user is-active --quiet cybercava-router.service; then
  echo "[$LOG_TAG] router down, restarting" | systemd-cat -t "$LOG_TAG" -p warning
  systemctl --user restart cybercava-router.service
  fail=1
fi
CAVA_COUNT=$(pgrep -c -f "cava -p /dev/stdin" 2>/dev/null || true)
[ -z "$CAVA_COUNT" ] && CAVA_COUNT=0
CAVA_COUNT=$(printf '%s' "$CAVA_COUNT" | tr -cd '0-9')
[ -z "$CAVA_COUNT" ] && CAVA_COUNT=0
# 4 expected (2 panels + 2 wallpapers), minimum 2 (panels)
if [ "$CAVA_COUNT" -lt 2 ]; then
  echo "[$LOG_TAG] only $CAVA_COUNT cava processes, restarting plasmashell applets" | systemd-cat -t "$LOG_TAG" -p warning
  systemctl --user restart plasma-plasmashell.service 2>/dev/null || qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "lockCorona(false)" >/dev/null 2>&1
  fail=1
fi
if ! systemctl --user is-active --quiet cyberdeck.service; then
  echo "[$LOG_TAG] cyberdeck down, restarting" | systemd-cat -t "$LOG_TAG" -p warning
  systemctl --user restart cyberdeck.service
  fail=1
fi
# link check: at least one monitor linked to cava
if command -v pw-link >/dev/null 2>&1; then
  LINKS=$(pw-link -l 2>/dev/null | grep -c "cava" || true)
  if [ "$LINKS" -eq 0 ] && [ "$CAVA_COUNT" -ge 2 ]; then
    echo "[$LOG_TAG] zero cava links, router will reconnect on next heartbeat" | systemd-cat -t "$LOG_TAG" -p notice
  fi
fi

# Deck topology v2.0 checks (appended 2026-09-26)
for node in Discord Browser Main Virtual_Mic; do
  if ! pactl list sinks short 2>/dev/null | grep -q "^[0-9]*	$node	" && \
     ! pactl list sources short 2>/dev/null | grep -q "^[0-9]*	$node	"; then
    echo "[deck-topology] missing node $node" | systemd-cat -t cybercava-watchdog -p err
  fi
done
for stream in Discord_Stream Browser_Stream Main_Stream; do
  if ! pw-link -l 2>/dev/null | grep -A2 "^$stream:output_FL" | grep -q "|->"; then
    echo "[deck-topology] $stream has no hardware link" | systemd-cat -t cybercava-watchdog -p warning
  fi
done

# Deck v2.0: feedback-loop guard (appended 2026-09-26)
# If system default source ever becomes easyeffects_source while EE follows
# the default input, EE would capture its own output. Flag it, don't auto-fix.
if pgrep -x easyeffects >/dev/null 2>&1; then
  defsrc=$(pactl get-default-source 2>/dev/null)
  if [ "$defsrc" = "easyeffects_source" ]; then
    echo "[deck-topology] WARNING: default source is easyeffects_source (EE self-capture loop risk)" | systemd-cat -t cybercava-watchdog -p warning
  fi
fi

exit $fail
