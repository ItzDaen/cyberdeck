# State at the v1.0 freeze (before the refactoring)

Date: 2026-09-28. Tag: `v1.0-matrix-freeze`

## Problems found during the analysis

1. **Duplicate `TelemetryHUD.qml`** — two byte-identical copies (md5
   `9ce7f62a…`) in `plasmoids/cyberpunk.hud` and in
   `wallpapers/cyberpunk.solitude.hud`. Every change had to be
   replicated by hand. Resolved: it now lives in `src/qml/shared/`.

2. **No version control on the QML** — the pre-existing git repository
   covered only `~/.local/share/cyberdeck` (Python) and was local, with
   no remote. The 1219 lines of TelemetryHUD and the entire wallpaper
   had no backup.

3. **Drawn fonts that do not exist** — `app.css` declared
   `JetBrains Mono → Fira Code → Share Tech Mono`; none of the three is
   installed. The dashboard always fell back to **DejaVu Sans Mono**.
   The QML said only `"monospace"`. Decision: IBM Plex Sans + IBM Plex
   Mono (`ttf-ibm-plex`).

4. **Overlapping, incoherent palettes** — HUD green `#00ff66` (29
   occurrences), Plasma colour scheme `Cyberpunk-Blue` (azure), QML
   comments saying "Pure Blue Cyberpunk Matrix", zellij with no theme.
   Three or four identities in competition.

5. **Three audio systems in parallel** — the wallpaper does NOT use
   CyberCAVA: it reads from
   `com.github.luisbocanegra.audiovisualizer`. CyberCAVA feeds the
   panel. `visualizer.py` starts a third cava for web clients. At
   snapshot time there were **4 cava processes** and **2 identical
   `while true` loops** (PIDs 3518, 3083495).

6. **Two sources of truth about state** — the same position/size lives
   in LocalStorage SQLite (inside the QML) **and** in
   `plasma-org.kde.plasma.desktop-appletsrc` (written by the bash
   `cyberhud` with `kwriteconfig6`).

7. **Hardwired Plasma IDs** — the bash assumes containment `22`/`23` and
   applet `808`/`810`. Changing the desktop layout breaks the
   positioning.

## Decisions taken for the refactoring

| Aspect | Decision |
|---|---|
| Aesthetic | Analog instrument (Braun / NASA / Teenage Engineering) |
| Scope | deck + HUD + wallpaper + CAVA + desktop |
| Version control | local git + tar, no cloud |
| Prototypes | none, proceed directly |
| Wallpaper | flat colour + grain + vignette, **zero shader** |
| Font | IBM Plex Sans + IBM Plex Mono |
| Naming | unchanged, decided after the refactoring |
| CAVA | functionally unchanged |
| Performance Mode | **removed entirely** |
| Dual monitor | HUD on both, calculated positions |
| Plasma | IBM Plex as the system font only |
| Release | incremental, component by component |
| sudoers | left active |

## Target palette

```
background        #0e0d0b      warm black, off
surface           #1a1917      dark anodised aluminium
raised surface    #22201d
border            rgba(255,255,255,.08)   1px
text              #e8e4dc      warm white, never pure #ffffff
text 2            #8a857c
dim text          #565250
ACCENT            #ff9d2e      amber — the only "living" colour
alarm             #d8492f      brick red
idle channel      #6b7a6f      dim grey-green
```

`#00ff66` disappears from every file.

## What is NOT touched

- Plasma colour scheme stays `Cyberpunk-Blue`
- plasma theme, KWin, zellij layout: unchanged
- CyberCAVA: unchanged
- The dashboard's API contract and authentication: unchanged
- No new shader
- No renaming

## Backup

`~/backups/cyber-refactor-20260928-1728.tar.gz`
SHA256 `acf19e07f734553292732bda55b2adc28701842b619b939c8f404492dc3ab5c0`
