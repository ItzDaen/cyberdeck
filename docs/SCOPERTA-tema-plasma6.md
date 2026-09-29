# Plasma 6: themes cannot override components in QML

Date: 2026-09-28 · Theme: MERIDIANO, phase 6

## What was wanted

A Plasma theme that would override `org.kde.plasma.core.DefaultToolTip`
and about fifty controls of `org.kde.plasma.components` (Button, MenuItem,
Slider, ScrollBar, Switch, CheckBox, and the rest) with QML
implementations in the Meridiano style. Twenty-two files were written;
all of them passed `qmllint`, and they were verified in a runtime
harness: they load, and every token the singleton returns has a value.

**Plasma 6 does not load them. The mechanism does not exist.**

## Three independent proofs

1. **No code adds the path.** Neither `libPlasma.so.6.7.5` nor
   `plasmashell` contains the strings `ui` or `contents/ui`. If nothing
   adds that directory to the QML engine's import path, no type can be
   resolved from there.

2. **Breeze itself has no `contents/`.** The system's `Plasma/Theme`
   package is `/usr/share/plasma/desktoptheme/breeze-dark`, and it
   contains exactly three files: `colors`, `metadata.json`, `plasmarc`.
   The package is **flat**: there is no `contents/` subdirectory.

3. **Fault injection.** A `readonly property` reading a non-existent
   `Kirigami.Theme` member inside `Meridiano.qml` causes a fatal
   `Property not found`. Restarting plasmashell produced nothing in the
   journal — neither with the files under `contents/ui`, nor at the root
   of the package. The theme *is* found: with a bogus name Plasma prints
   `Could not locate plasma theme "NonEsisteMai"`, with `Meridiano` it
   stays silent. It simply does not read the QML.

The components are also compiled in as a Qt resource: the
`org.kde.plasma.components` qmldir declares
`prefer :/qt/qml/org/kde/plasma/components/`, and in error traces the
files arrive as `qrc:/qt/qml/...`.

## What is actually needed

SVGs. From the KDE documentation:

> Plasma::Theme provides access to a common and standardized set of
> graphic elements stored in SVG format. This allows artists to create
> single packages of SVGs that will affect the look and feel of all
> workspace components.

A package under `plasma/desktoptheme/<name>/` with the twenty required
sets. The contract is precise and extractable: each `KSvg.Svg` declares
an `imagePath` and pulls elements by `elementId`; each
`KSvg.FrameSvgItem` picks its artwork with a `prefix` that is often a
formula over the states.

The advantages are not small: the `ColorScheme-Text`,
`ColorScheme-Background` and `ColorScheme-Highlight` class
substitutions make the SVGs follow the active colour scheme. The assets
are written once and change colour with the scheme.

## What is left of the work that was done

Nothing, and that is the correct outcome. The twenty-two QML files were
removed: keeping them in the repository would have declared a working
theme that Plasma does not load. The design decisions they contained —
1px borders, 2px radius, a spacing scale in 2px steps, amber as the only
living colour, the 0.65 / 0.88 thresholds — survive in
`src/qml/shared/Theme.qml` and in `Meridiano.colors`, which are the real
sources.

## A note on the previous CyberBlue theme

`~/.local/share/plasma/desktoptheme/CyberBlue` contains only `colors`
and `metadata.json`: no SVG at all. So that theme did not draw the shell
either; it only supplied colour effects. The "Cyber" appearance came
from the colour scheme, the panel applets and the wallpaper. That is
one more reason not to read a theme's name as a hint about what governs
what.
