# CyberDeck

One monorepo for the whole Cyber* stack: Plasma applet, wallpaper, web
dashboard, CLI scripts and user systemd units.

The rule underneath all of it: **`src/` is the single source of truth.**
No hand-maintained duplicates, no `kwriteconfig6` writing a secret into
a `.desktop-appletsrc` while another module reads it back out of an
SQLite file.

## What it is

A workstation control deck for a Linux desktop running Plasma 6 on
Wayland. It shows what the machine is doing — CPU, GPU, board, storage,
network, fans, voltages — and lets the same readings be read from a
phone over the network. The visual language is an analog instrument
panel rather than a desktop theme: a warm near-black field, a single
amber accent, tabular figures, and colour used only where it carries
meaning.

The Plasma side is a theme called **Meridiano** (colour scheme, window
decoration, twenty generated SVG sets, a monochrome icon set, a Kvantum
theme, a Konsole palette). The web side is a PWA that talks to a small
asyncio server over a WebSocket, authenticated with a token.

## Layout

```
src/
  qml/
    shared/       shared components, one copy (TelemetryHUD)
    plasmoid/     Plasma/Applet package      -> cyberdeck.hud
    wallpaper/    Plasma/Wallpaper package  -> cyberdeck.instrument.field
  web/            Python server + PWA (the CyberDeck dashboard)
  bin/            CLI scripts (cyberhud, cyberdeck, cybercava-*)
  systemd/        user units
  cyberdeck.kdl   zellij layout
  theme/          the Meridiano source: colour scheme, Aurorae, assets
  config/         config.yaml, the versioned defaults
tools/
  sync-packages.sh   src/ -> ~/.local/share/...  (with checksums)
  install.sh         full deploy
  genera-*.py        generators for the theme assets
  verifica-*.py      verifiers, they read Plasma's own sources
  ponte-icone.py     bridges the icon names applets ask for
docs/              what is true, and what is not
packages/          installed mirror of src/, generated, gitignored
```

## Commands

```bash
tools/install.sh                # sync, then reload the services
tools/sync-packages.sh          # propagate src/ to the real locations
tools/sync-packages.sh --check  # report drift, write nothing
```

Every generator and verifier prints what it measured before and after,
so a claim can be checked rather than believed.

## Configuration, in two layers

`~/.config/cyberdeck/config.yaml` is versioned here and deployed from
`src/config/config.yaml`, so the project stays the source of truth.

`~/.config/cyberdeck/config.local.yaml` is **not** in this repository.
The server merges it over `config.yaml`, and `sync-packages.sh` never
touches it. That is where what is true of one machine goes — the name
you reach the deck on, a port you had to move — so it neither has to be
committed nor is clobbered by a deploy.

## The shared QML rule

`TelemetryHUD.qml` used to exist in two byte-identical copies. It now
lives once, in `src/qml/shared/`, and `sync-packages.sh` copies it into
both packages and verifies the checksum afterwards. There is no manual
copy step, and the checksum is what catches it if one is ever added.

## Secrets

The dashboard's auth token is generated on first start, lives in
`~/.config/cyberdeck/auth.token`, and is gitignored. It must never be
committed. The server prints `<redacted>` and points at the file instead
of logging the value.
