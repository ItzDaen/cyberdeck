# State at the end of the refactoring

Date: 2026-09-28. Latest tag: `v1.4-dashboard` (plus `v1.5-hygiene`).

The starting document is `STATO-v1.0.md`, which lists what was broken
before. This one is about what is still open, which is the honest part.

---

## Done

| Phase | Outcome | Tag |
|---|---|---|
| 0 — foundations | single monorepo, safety tarball, legacy history imported | `v1.0-matrix-freeze` |
| 1 — wallpaper | GLSL shader removed, flat surface + grain + vignette | `v1.1-wallpaper`, `v1.1.1` |
| 2 — HUD | 1219 → ~930 lines, 4 components extracted | `v1.2-hud`, `v1.2.1` |
| 3 — CLI | bash 234 lines → Python, hardwired Plasma IDs gone | `v1.3-cli` |
| 4 — dashboard | CSS rewritten, 50 Matrix colours in the JS → 4 | `v1.4-dashboard` |
| 5 — hygiene | Performance Mode removed everywhere, system font, panel palette | `v1.5-hygiene` |
| 6 — theme | colour scheme, Aurorae decoration, 20 Plasma SVG sets, icon set, Kvantum, Konsole | `v1.6-colors` … `v1.10.0-shell` |
| 7 — translation | every comment, document and commit message in the repository, plus the strings a screenshot can only find | — |

By the numbers:

- total QML lines: from 3115 to 2745, with 4 new components replacing
  repeated code
- hardcoded colours in the dashboard's JS: from 50 to 4 (the token
  fallbacks)
- `qmllint`: 0 warnings across all QML files
- hardwired containment IDs: from 4 (22, 23, 808, 810) to 0

---

## Open problems, in order of severity

This list was last rewritten on 2026-09-29. Four of the six entries
that used to be here are no longer true; they are kept below under
*Closed since*, because a defect that was real and got fixed is
evidence about the process, and erasing it would make the next
occurrence look like a surprise.

### 1. Resolved: there is no duplication, and the old entry was wrong

**There is no leak. Four `cava` processes is the correct count on this
session, and every earlier reading of it was wrong.**

The count only ever made sense against an expectation of 2, and that
expectation was the error: it counted the two wallpapers and ignored
everything else on the desktop. Where the four come from:

| source | instances | `cava` |
|---|---|---|
| this repo's wallpaper, one `AudioSpectrum` per containment | 2 | 2 |
| `luisbocanegra.audio.visualizer` applets, third party, each with its own `Cava.qml` | 2 | 2 |

The second row is why the doubling looked like a fault. The two
processes from the third-party applets start about 3s after the
wallpaper's, which reads as a leak at the process level and is not one.

How that was established, since the first three attempts were not:

- The `Process` type from `com.github.luisbocanegra.audiovisualizer`
  is a C++ plugin, not QML, and its string table lists exactly four
  members: the properties `command`, `running`, `stdout`, `stderr` and
  the methods `stop()` and `restart()`. **There is no `start()`.** An
  intermediate version of `AudioSpectrum.qml` called one, on the theory
  that a guard around `restart()` would stop the doubling; it was a
  call into nothing, and the doubling it claimed to fix was never ours.
  The file is back to its original lifecycle with that fact written down.
- Counting `console.warn` lines from `Component.onCompleted` gives 2
  `AudioSpectrum` instances, and giving each one a unique marker in its
  `argv[0]` shows exactly one `cava` per instance. The first two
  processes are ours and are marked; the other two are not, and they
  come from `Cava.qml` in the third-party plasmoid.
- The applet config carries `plugin=luisbocanegra.audio.visualizer`
  twice.

Two earlier claims in this document were also wrong, both from looking
at the wrong layer:

- **The 8 `cava:input_*` are not dead orphans.** They are the input
  ports of the 4 live processes, 2 each, and all 8 are connected:
  32 links currently run into them. The node *names* are just `cava`;
  `cava:input_FL` and `cava:input_FR` are the *port* names, which is
  the level `pw-link -I` reports. Checking `pw-cli ls Node` for
  `cava:input` finds nothing and looks like a dead end, because the
  names are one level down.
- **`cybercava-router` is working, and it is load-bearing.** It reads
  ports with `pw-link -I -i`, matches `cava:input_FL` / `cava:input_FR`,
  and links every monitor channel into them. The old entry here
  proposed dropping it in favour of `visualizer.py` as a single
  producer; that would have taken the spectrum with it, since the
  wallpaper's `cava -p /dev/stdin` reads from those ports.

One observation survives, and it is a design choice rather than a bug:
the router connects `Discord.monitor`, `Browser.monitor` and
`Main.monitor` into **every** analyser, so each `cava` sums all three
rather than reading one. The wallpaper's own config says
`source=Main.monitor`, so on paper it is narrower than what it is fed.
Worth a decision, not worth a change nobody has asked for.

### 2. The applet's geometry has two owners

Unchanged, and still the most likely reason the panel would look wrong
one day. `ItemGeometries-*` in Plasma's config and the size in
LocalStorage compete over the panel's size, and during the refactoring
the saved geometry won over the value just set more than once. The
LocalStorage database was renamed (`CyberDeckHud` → `CyberDeckHudV2`)
to break that tie once.

It is not fixed. If the panel ever comes back clipped, the first thing
to check is whether `Applet-808` in the config states a different size
from the one on screen.

### 3. The applets ask for icon names the theme does not have

Not one name but a category of them, and the same shape has now
appeared three times: the artwork exists, bright, under a name nobody
requests, while a hardcoded near-black copy from another theme gets
used instead. The kickoff button was the first, the launcher icons the
second, and this is the third.

`tools/ponte-icone.py` bridges the names the applets ask for, writing
them with the Plasma colour contract (`class="ColorScheme-Text"` and
`fill="currentColor"`) so they follow the active scheme. What is
*not* solved is the general case: the theme is generated from whatever
names the source themes carry, and that set is not the set the applets
request. Every new applet is another possible gap, and the symptom is
always the same -- an icon that is invisible rather than missing.

**The fourth time, and the one where I got the name wrong twice.** The
power profile selector showed all three profiles with the same icon and
I bridged `power-profile-*-symbolic`, a prefix I had guessed. Those
names exist in Fluent and Adwaita and the applet never asks for any of
them, so nothing changed, and I reported it as fixed. The prefix is
`battery-profile-`, and it is not a guess this time: the applet's own
binary carries the AOT-compiled `PowerProfileItem.qml`, and reading its
string table in 16-bit little endian (`strings` with the default
single-byte scan misses them entirely) yields
`battery-profile-performance-symbolic`,
`battery-profile-powersave-symbolic` and `powerProfileIconName`
directly. breeze uses the same vocabulary, and it is the only installed
theme that carries the set at all, so the two sources agree. The three
are supplied and rendered side by side to confirm they are distinct and
not merely present: a gauge with a needle, a bolt, a leaf, at 9.35, 9.22
and 7.80 to 1 against the panel.

The lesson generalises: the answer was on disk the whole time, in the
binary and in the one theme that had the artwork. Guessing a name and
then measuring the file I had just written is how two rounds of
"verified" fixes shipped in a row.

### 4. Thirty-two inline styles with v1.0 variable names

`index.html` has 32 `style="..."` using `--font-mono`, `--text-dim`,
`--matrix-green`, `--cyber-cyan`, `--tactical-red`. They are mapped to
the new tokens in `:root` by the compatibility bridge, so they do not
break, but they are debt and they should go together with the inline
styles that use them.

They were not removed because rewriting thirty inline styles blind can
break the layout, and the layout is worth more than the tidiness. That
reasoning still holds.

---

## Closed since this list was written

### The performance mode could not be set from the web deck

Every press of `[FULL]` or `[YIELD]` failed, and the page showed nothing.
It looked like a dead button.

**The cause was the server's PATH, not the code.** The web deck runs as a
systemd user service, and `cyberdeck.service` sets only
`PYTHONUNBUFFERED`, so the child inherits whatever the user manager had
in its environment when it started. After a reboot that was
`/usr/local/bin:/usr/bin` — and `cyberhud` is installed to `~/.local/bin`.
Every action therefore produced the same line in the journal and nothing
on the page:

    Command execution error for cyberhud performance off -q:
    [Errno 2] No such file or directory: 'cyberhud'

Measured, not assumed: the same request against a server whose PATH did
include `~/.local/bin` worked, and the failing one did not. The PATH is now
not consulted at all — `system_control.cyberhud()` resolves the CLI to an
absolute path, with an environment override and a deliberate fall back to
the bare name so a missing install reports `ENOENT` instead of going quiet.

Two things had been hiding this. The failure returned `success: false` in a
reply the browser never reads, because actions go out over the WebSocket
and only the state comes back; and the state was unchanged, so a failed
press looked exactly like an ignored one. The error now travels in the
state, which is broadcast every second, and the card shows it.

**Also fixed while in there:** the card's own comment claimed a third state
("the detector decides") that no control set, so a manual choice was a
one-way door from inside the deck. `cyberhud performance auto` existed on
the command line the whole time and is now reachable from both the card
and the header. The mode is also reachable from the header, one tap, on
any tab — it is a switch you use from a phone, and a switch you have to
find is a switch you do not reach for.

### The spectrum was permanently off, and nothing said why

The first monitor showed the static background and the spectrum never
came back, with no error anywhere.

**The automatic yield was the cause, and the desktop's shape is the
reason.** The rule was "yield when an animated wallpaper is running on a
screen that is not ours". The video wallpaper lives on the second monitor
and stays there, so the condition was true on every one of the two-second
passes. The spectrum was therefore off always, and `cava` was still
running: it was a stopped spectrum, not a broken one, and the page drew no
difference between the two. The only thing keeping it on was the manual
marker written by hand — which is the definition of a setting with no off
switch.

It was changed because the mode was asked for a purpose, and that purpose
is gaming and rendering. Yielding a 2%-of-a-core audio spectrum is not
freeing a GPU, and a background process that turns off the user's desktop
for ever is a nuisance rather than a courtesy. So the automatic pass now
**reports** and writes nothing: `animated_elsewhere` on the web deck, and
`on another screen` in `cyberhud performance status`. `--auto` means full
tilt, and it means that unconditionally.

Verified by leaving the timer to run: after `auto`, six passes over twelve
seconds, the yield file was still absent and the state still `full`.

Two things this made false and that had to change with it, or the code
would have gone on saying things that were not true:

- `cyberhud performance auto` used to be "hand the decision to the
  detector". There was no longer a decision to hand to. It clears the
  marker, restores any wallpaper that was taken, and goes to full tilt.
- The card's `DECIDED BY / detector` line was the UI version of the same
  claim. It reads `IN CHARGE / hands off` or `you`.

**One message was wrong in both directions.** `avvisa_se_non_preso()` said
"the spectrum stops on the next plasmashell restart" and was called for
FULL too, where the spectrum was starting. It now names the direction from
the file it is about to be honest about.

### The performance mode did not do what it was for

The mode exists for when the whole GPU is wanted: a game, or a render.
Yielding an audio spectrum is not that, because a video wallpaper is the
largest continuous GPU consumer on the desktop and it belongs to somebody
else. So the manual mode now also swaps an animated wallpaper out, records
which plugin was where in `~/.cache/cyberdeck/gpu-free-wallpapers.json`,
and puts it back on FULL or AUTO. Verified by file descriptor, not by
appearance: the process holding `cyberpunk_gloomy_rain.mp4` drops from one
holder to none while the mode is on, and back to one when it is off.

**The automatic detector still never touches anyone's wallpaper.** That is
the line the two behaviours are drawn on, and `docs/CONTRATTO-resa.md` now
says so explicitly instead of implying it.

Two bugs were found by writing this and are worth recording because both
were silent:

- `plasma_wallpapers()` parsed one screen per line, but `evaluateScript`
  returns several `print` calls **concatenated with no newline**. The
  result was a single key holding both screens glued together, so no screen
  ever matched the animated plugin and the mode reported success while
  swapping nothing.
- `enabled_screens()` matched `Geometry:` in `kscreen-doctor` output that
  is wrapped in ANSI colour codes, so it matched nothing and always fell
  back to a one-screen list built from *this* wallpaper's containments. On
  a two-monitor desktop `--screen 1` had never worked.

### Was the desktop colour scheme still blue?

False now, and it was false for a second, unrelated reason that the
first investigation did not reach.

**The earlier "twelve checked roles" was too small a sample.** Comparing
`Meridiano.colors` against `kdeglobals` over *every* `Colors:` role
rather than a chosen twelve: **45 of 96 disagreed**, in every section,
not just the three that had been noticed. The blue was not Breeze's.
It was `Cyberpunk-Blue.colors`, the scheme this one replaced:
`0,170,255` for the focus border, hover, active and link roles,
`7,126,185` for the selection background, `10,128,187` for the button
alternate. Left over from before, and nothing had ever corrected them.

Two causes, both in `tools/meridiano-apply`:

1. **A regex that could not see a section with a bracket in its name.**
   The writer walked `kdeglobals` with `^\[([^\]]+)\]\s*$`, which stops
   at the first `]`. `[Colors:Header][Inactive]` — a legitimate KDE
   construct — therefore was not recognised as a section at all, fell
   through as ordinary text with its keys under it, and kept the
   previous values forever. The name now runs greedily to the last `]`.
   Sections written per run: 10 → 11.
2. **Plasma 6's accent override was outside the tool's reach.**
   `AccentColor` lives in `[General]`, which the tool deliberately
   preserves, and it *wins* over the colour scheme: it is what the shell
   paints with, independently of `DecorationFocus`. A value left by
   Cyberpunk-Blue survived every run, so the desktop would have shown a
   cyan accent with every other colour correct — the worst way for a
   theme to be wrong. The tool now derives the accent from the model's
   own `DecorationFocus` and writes it, so the two places holding it
   cannot drift.

Final state: 96 of 96 roles agree, no occurrence of the old blue
anywhere in `kdeglobals`, and `AccentColor=255,157,46`. Confirmed live
by measurement, not by eye: `rgb(255,157,46)` appears in the taskbar
where the active window is highlighted.

The earlier cause, still true: the tool looked for the Aurorae theme in
`aurorae/themes/Meridiano` while the installed theme was `Meridiano-3`,
printed "decoration not found" and carried on, so the colour step was
never re-run after the rename. It now resolves the theme name from disk
and prefers the canonical one.

The general lesson, which is the fourth time it applies in this project:
a check over a hand-picked sample is not a check. Twelve roles agreed
and forty-five did not, and the twelve were the ones already looked at.

### Was the Plasma theme never touched?

False now. Twenty SVG sets are generated from a parameter table and
verified against Plasma's own code: `verifica-assets-plasma.py` reads
the installed QML, extracts the `imagePath`, `elementId` and `prefix`
expressions, and compares. It reads the source rather than a private
list on purpose, so a change in Plasma shows up as a failure.

`docs/SCOPERTA-tema-plasma6.md` records why the QML component theme
does not work at all: Plasma 6 has no mechanism for it, proven three
independent ways.

### Were the system icons still coloured?

False now, and the decision behind it is the opposite of what this
entry used to imply. The icon theme supplies **no application icons at
all**: 3080 monochrome icons across six contexts, chrome only
(actions, status, devices, places, mimetypes, emblems). Applications
inherit their own mark from the chain, and 213 of 213 application
icons resolve.

The reasoning: replacing every program's mark with a grey drawing means
the user can no longer tell Firefox from a text editor. Identity is
data, not decoration.

The corollary, which is not a defect: three of the panel's icons still
measure under 3:1 against the panel. `systemsettings` (L 42) and `steam`
(L 66) have no lighter variant in any installed theme, and recolouring
a brand mark is a decision, not a measurement. The three that were
genuinely bad were fixed by *selecting* a variant that already exists
— the kickoff button was not a dark icon, it was the dark rendering of
an icon that also exists light, and the context decided which.


---

## Things I decided differently from how they were described

Noted because they are decisions, not outcomes, and each one is
reversible.

**Accent threshold.** Amber was set at 80% of the load. With `autosens`
the peak sits between 60% and 80% even at full-scale audio, so it never
triggered: a dead colour. Raised to 0.65, and moved off the lit segments
onto the peak cursors and the summary figure. The bar stays neutral
because it is the measurement; the colour only says whether the
threshold was crossed.

**Thermal spectrum.** Six interpolated steps (cyan, green, amber,
orange, red, deep red) reduced to three. With thirty sensors it was a
rainbow of dots, and moving between two values changed hue rather than
intensity.

**Zero-RPM fans.** They were cyan, as if it were good news. A fan
stopped with the package above 75 °C is a red alarm, because it is an
alarm.

**Default panel height.** From 392 to 440 px: the content did not fit
and was being clipped.

## What automatic checking did not find, and looking at the screen did

Worth recording, because it is the lesson of this work, and it has now
been paid three times in three different ways.

`qmllint` and `node --check` were clean while the page was illegible.
Five defects emerged only from rendering:

1. A confirmation modal open on load (its background darkened the whole
   page: it looked like a colour problem, it was a state problem)
2. Four tabs overlapping in the same spot
3. Section titles in the wrong order
4. `CYBERAUDIO` — a global replacement that had also hit the brand
5. Status bars clipped on the left

And five in the QML HUD, two of them treacherous: `anchors.baseline`
inside a `Row` (which is a positioner: conflict) and cells without
`width`/`height`, which look empty while the sensors work — so the
symptom pointed at the data instead of at the layout.

**The second time**, the same lesson in a different shape: the overflow
check said the commands tab was clean, and it was clean, because the
deep link that selects the tab had never worked. The check was right
about the tab it measured and silent about the one nobody measured.
A check that only ever looks at one instance of a thing is not a check
on the thing.

**The third time**, the panel's icon report. Two icons on the panel
measured 1.04:1 and 1.2:1 against the panel background, and the report
that would have caught it had never been run against the panel — it had
been run against a synthetic render, where the numbers for a
bright-logo icon like Firefox came out at 77 while the real panel
showed 8.9:1. The metric was not wrong, it was measuring a different
thing than the one the user looks at.

**Operational conclusion:** for QML and for CSS, the linter is a
first-level filter, not an acceptance criterion. You have to look at
the result, and you have to look at *each* thing, on the surface it
actually appears on.

Qt 6's `qml` runtime does not work in this environment (it fails even on
an empty `Item`), so for QML the path was `qmllint` plus `journalctl`
after restarting plasmashell. For the web, headless Chromium worked and
rendered the screenshots.

## Commands

```bash
tools/sync-packages.sh            # propagates src/ to the real locations
tools/sync-packages.sh --check    # verifies drift, writes nothing
tools/sync-packages.sh --prune    # plus removing obsolete files
tools/install.sh --prune          # deploy + reload services
tools/install.sh --prune --restart-plasma

tools/verifica-tema.py            # kdeglobals against the colour model
tools/verifica-assets-plasma.py   # the SVG sets against Plasma's own code
tools/genera-aurorae.py --out DIR # the window decoration
tools/schiarisci-icone.py --check # icon variants, measured, writes nothing
tools/ponte-icone.py --check    # the icon names the applets ask for
tools/meridiano-apply --dry-run   # colours + decoration, writes nothing

cyberhud status                   # panel state
cyberhud screens                  # monitors and containments
cyberhud move top-left            # position (also 900 60)
cyberhud size 600 440
cyberhud toggle

cyberhud wallpaper list                      # what is on each screen
cyberhud wallpaper set 1 <plugin-id>         # by screen number
cyberhud wallpaper set 23 <plugin-id>        # or by containment id

cyberhud performance status                  # the yield state and who set it
cyberhud performance on                      # manual: stop the spectrum, swap
cyberhud performance off                     #          animated wallpapers out
cyberhud performance auto                    # back to the detector, wallpaper back

cyberdeck-overhead      # VRAM, GPU, and how many audio analyses run in parallel
cyberdeck-overhead -w   # the same, continuously
```

Rolling back a single phase: `git checkout <tag> -- src/` then
`tools/install.sh --prune`.
