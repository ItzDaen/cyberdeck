# The yield contract

The performance mode stops this project's audio spectrum, and when a person
asks for it, also takes an animated wallpaper off the screen. This document
is for anyone writing a wallpaper that wants to take part, and for anyone
who is surprised that a second monitor with a video on it no longer turns
the desktop off by itself.

**Nothing automatic throws this switch.** The detector reads the list and
*reports*; it does not write. YIELD is the user's, for a game or a render.
The section below says exactly what each path does.

## What is published, and what is not

**Published:** a file.

    ~/.cache/cyberdeck/yield

Its **presence** means "stop what you are doing; the GPU is wanted". Its
absence means the desktop is running at full tilt. It is written by the
manual performance mode and by nothing else, so if the file is there it is
there because a person asked.

    ~/.cache/cyberdeck/yield-manual

records that a person chose the current state by hand. It exists so that
nothing automatic can overrule a decision — and now that the automatic pass
is a reporter, its remaining job is to stop the two-second timer from
touching a choice. `cyberhud performance auto` is the way to clear it, and
going to full tilt is what clearing it does.

That is the whole contract. There is no list to be added to, no API to
call, and no version to match.

## How to take part

Watch for the file appearing and disappearing, and reduce your own work
when it is there. Poll it — one existence check a second is nothing, and
on a wallpaper plugin there is usually nothing better available (see
"What this project cannot do" below).

The signal is raised by a person, not by a timer. The detector notices an
animated wallpaper on a screen that is **not** showing ours and reports it,
but it does not raise the signal and it never swaps a wallpaper; the manual
performance mode is what does that, and only while it is switched on.

So being on the list no longer means "the analyser will step aside when I
appear". It means "when someone frees the GPU, the performance mode will
know to put me back". That is the part worth taking part in.

To be acted on, add your plugin id to:

    ~/.config/cyberdeck/animated-wallpapers.list

one per line, `#` for comments. That file is seeded once from the
repository and then never overwritten: it is your statement about your own
desktop. Without it the performance mode cannot know you are there, and
YIELD would stop our spectrum without noticing that your wallpaper needs
putting back.

## The detector reports; the manual mode acts

Two different jobs, and the difference matters to anyone whose wallpaper is
the one being affected.

**The detector writes nothing.** It reads your list, notes which screens are
animating, and that note ends up on the web deck as
`animating_elsewhere`. It used to decide as well — it used to yield — and
that was a mistake worth recording rather than quietly reverting.

The condition was "an animated wallpaper is running on a screen that is not
ours". With a video wallpaper on the second monitor that is true at every
single pass. So the detector yielded at two-second intervals, the spectrum
never came on, and nothing on screen distinguished *stopped on purpose* from
*broken*. The project's own rule is that a person outranks a timer, and a
timer that holds a setting for ever is a timer with no off switch. It now
reports and stops there: there is no code path that writes a screen's
wallpaper except the manual mode below.

**The manual performance mode does take the GPU back.** Set it by hand and
you have said *I need the whole GPU now* — a game, or a render. At that point
an animated wallpaper is the largest thing competing for the GPU, and
stopping an audio spectrum is not what was asked for. So the manual mode:

1. raises the signal, stopping our spectrum;
2. records which plugin was on each screen, in
   `~/.cache/cyberdeck/gpu-free-wallpapers.json`;
3. points those screens at `cyberdeck.instrument.field`, which draws nothing
   while the mode is on.

Turning it off with FULL, or handing it back with AUTO, puts the recorded
plugin back on each screen. Plasma keeps a
`[Containments][N][Wallpaper][<plugin>][General]` group per plugin, so your
video file and playback position are still there and come back with it; only
the plugin id is stored, never a second copy of the settings.

Two consequences worth stating plainly:

- **A wallpaper swap is immediate; the spectrum is not.** The swap goes
  through plasmashell and the plugin is recreated, so it lands at once. The
  signal is a file the wallpaper only reads at start-up, so stopping the
  spectrum still waits for a plasmashell restart. Both facts are on the card
  that shows the state.
- **`cyberhud performance auto` restores your wallpaper and goes to full
  tilt.** It clears the manual marker, hands back what was taken, and stops
  the spectrum from being held. It is not "hand the decision to the detector"
  any more, because there is nothing left to hand it to.

## What this project cannot do, measured

**A Plasma wallpaper cannot observe a configuration change.** This is the
one that shaped the design, and it was worth the measurements:

- `WallpaperItem` exposes no `configurationChanged` signal, and the
  plugin binary carries no such symbol.
- Polling `root.configuration.PerformanceMode` every second returns the
  value captured when the plugin was loaded, forever. Measured: the key
  was written to `true` from outside and the poll kept reporting `false`.
- `Qt.labs.platform` in Qt 6 has no `FileSystemWatcher` and no `File`.
  Loading one fails outright: `Platform.FileSystemWatcher is not a type`,
  and the wallpaper does not load at all.

So the signal is a file because a file is the only thing that can cross
from a process into a QML tree. The file is not readable *by* the
wallpaper — only by whatever you write, which is a limitation, not a
choice.

**Our own wallpaper does not read the file either.** It takes the state
from its configuration key, and that key only reaches the screen when
plasmashell restarts. Reloading the wallpaper through the Plasma script
API re-creates the plugin but does not re-read the config: measured 4
`cava` processes before, 3 while the other wallpaper was showing, 4
after switching back, with the key set to `true` throughout.

That is why `cyberhud performance on` says the value is saved but not on
screen yet. It is the same warning the HUD has always given, for the same
reason, and the reason it is not conditional on the reload attempt is
that the attempt cannot be trusted.

## Writing a wallpaper

A Plasma 6 wallpaper is a `KPackage`: a directory with `metadata.json`
declaring `"KPackageStructure": "Plasma/Wallpaper"`, and a QML tree under
`contents/ui/`. Ours is `src/qml/wallpaper/`; it is the smallest
complete example in the repository, and `tools/genera-aurorae.py` shows
the generation discipline the project expects.

The choice of wallpaper is the user's. Nothing in the Meridiano theme --
the colour scheme, the icon set, the window decoration, the shell theme
-- refers to our wallpaper, and the HUD carries its own surface, so any
wallpaper can be used without the theme falling apart.
