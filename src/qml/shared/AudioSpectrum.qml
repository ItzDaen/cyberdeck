pragma ComponentBehavior: Bound

// ==============================================================================
// AudioSpectrum.qml — Spectrum analyser.
// Author: Daen
//
// PAY ATTENTION to the import below: it is NOT an unused import.
//
// In Plasma 6 / Qt 6.11 the QML type `Process` does not exist in QtQuick
// nor in QtQml: it is registered by the third-party module
// `com.github.luisbocanegra.audiovisualizer.process`. Remove that import
// and the whole file stops loading, and with it the whole wallpaper.
//
// qmllint, run outside the Plasma environment, reports this import as
// "Unused import" and reports `Process` as "not a type": both false
// positives. Take them at face value and the wallpaper breaks.
//
// The CAVA logic is unchanged with respect to v1.0 (decision: "leave it,
// only redesign"). The appearance changes completely.
//
// Before: 14px sticks with a green-to-cyan gradient, a "wet asphalt"
// reflection below, a blinking status square, a header
// "[ AUDIO MONITOR // SYSTEM WIDE ACTIVE ]".
//
// Now: a meter. A thin needle, a recessed background lane, a signal
// that lights up only above 80% and that shifts to brick red at 95%. The
// amber is information, not decoration.
// ==============================================================================
import QtQuick
import com.github.luisbocanegra.audiovisualizer.process 1.0  // fornisce il tipo `Process`

Item {
    id: root
    height: 104

    property int barCount: 32
    property var barValues: []
    property var peakValues: []
    property bool isIdle: true
    property bool active: true
    visible: root.active

    // The accent thresholds and the rule that applies them live in
    // Theme (Theme.hotLevel / Theme.loadAccent): that is a design
    // system decision, not a component one. No copy here.

    // Absolute peak across all the bands, in percent. It is the number
    // a real analyser shows: the figure, not just the shape.
    readonly property int peakLevel: {
        var m = 0;
        for (var i = 0; i < barCount; i++) {
            var p = (peakValues && peakValues[i] !== undefined) ? peakValues[i] : 0;
            if (p > m) m = p;
        }
        return m;
    }
    readonly property string peakLevelText: peakLevel + "%"

    // ── Init ───────────────────────────────────────────────────────
    Component.onCompleted: {
        var vals = [], peaks = [];
        for (var i = 0; i < barCount; i++) { vals.push(0); peaks.push(0); }
        barValues = vals;
        peakValues = peaks;
    }

    onActiveChanged: {
        if (active) cavaProcess.restart();
        else cavaProcess.stop();
    }

    // One timer, both directions.
    //
    // It used to only ever restart, and that was enough while `active`
    // was always true. The performance mode made it false, and then the
    // ordering bit: the Process type starts itself when it is created,
    // so with `active` false from the beginning `onActiveChanged` fires
    // before any process exists, `stop()` finds nothing, and the
    // analyser starts anyway. Measured, in this order:
    //
    //     onCompleted   active=false  running=false
    //     onRunningChanged running=true  active=false
    //
    // A guard in Component.onCompleted does not help, because running is
    // false there too -- the process has not spawned yet. The state
    // worth catching is the second line: the process is up and we do
    // not want it. So the trigger is the disagreement between the two,
    // and the handler settles it either way.
    Timer {
        id: cavaRestartTimer
        interval: 1000
        repeat: false
        onTriggered: {
            if (root.active && !cavaProcess.running) {
                cavaProcess.restart();
            } else if (!root.active && cavaProcess.running) {
                cavaProcess.stop();
            }
        }
    }

    // ── CAVA stream ─────────────────────────────────────────────────
    //
    // The Process type from com.github.luisbocanegra.audiovisualizer is
    // a C++ plugin, and its string table lists exactly four members: the
    // properties `command`, `running`, `stdout`, `stderr`, and the
    // methods `stop()` and `restart()`. There is no `start()`. Worth
    // writing down, because reaching for one is the obvious thing to try
    // and it is a call into nothing.
    //
    // One process per instance, and that is the whole count. The two
    // other `cava` processes on a two-desktop session do not come from
    // here: they belong to the third-party applets
    // `luisbocanegra.audio.visualizer`, which run their own analyser
    // with their own `Cava.qml`. See docs/STATO-v1.5.md.
    Process {
        id: cavaProcess
        onRunningChanged: {
            if (cavaProcess.running !== root.active) {
                cavaRestartTimer.restart();
            }
        }
        command: [
            "sh", "-c",
            "exec cava -p /dev/stdin <<-EOF\n" +
            "[general]\n" +
            "framerate=60\n" +
            "bars=32\n" +
            "autosens=1\n" +
            "lower_cutoff_freq=50\n" +
            "higher_cutoff_freq=12000\n" +
            "sleep_timer=0\n" +
            "[input]\n" +
            "method=pulse\n" +
            "source=Main.monitor\n" +
            "[output]\n" +
            "channels=mono\n" +
            "mono_option=average\n" +
            "method=raw\n" +
            "raw_target=/dev/stdout\n" +
            "data_format=ascii\n" +
            "ascii_max_range=100\n" +
            "[smoothing]\n" +
            "monstercat=1\n" +
            "waves=1\n" +
            "gravity=100\n" +
            "noise_reduction=45\n" +
            "EOF\n"
        ]

        onStdoutChanged: {
            var raw = cavaProcess.stdout.trim();
            if (!raw) return;
            var lines = raw.split('\n');
            var lastLine = "";
            for (var l = lines.length - 1; l >= 0; l--) {
                var t = lines[l].trim();
                if (t.length >= 10) { lastLine = t; break; }
            }
            if (!lastLine) return;
            if (lastLine.endsWith(';')) lastLine = lastLine.slice(0, -1);
            var parts = lastLine.split(';');
            if (parts.length >= root.barCount) {
                var newVals = [];
                var maxVal = 0;
                var currentPeaks = (root.peakValues && root.peakValues.length === root.barCount)
                    ? root.peakValues.slice() : [];

                for (var i = 0; i < root.barCount; i++) {
                    var v = parseInt(parts[i], 10) || 0;
                    if (v <= 3) v = 0;              // gate: sotto il 3% è silenzio
                    if (v > maxVal) maxVal = v;
                    newVals.push(v);

                    var p = currentPeaks[i] || 0;
                    if (v >= p) currentPeaks[i] = v;
                    else currentPeaks[i] = Math.max(0, p - 3.0);  // peak-hold scende
                }

                root.barValues = newVals;
                root.peakValues = currentPeaks;

                if (maxVal > 0) { root.isIdle = false; idleTimer.restart(); }
            }
        }
    }

    Timer {
        id: idleTimer
        interval: 1000
        repeat: false
        onTriggered: {
            root.isIdle = true;
            var vals = [];
            for (var i = 0; i < root.barCount; i++) vals.push(0);
            root.barValues = vals;
        }
    }

    // ─────────────────────────────────────────────────────────────
    // Header
    // ─────────────────────────────────────────────────────────────
    Item {
        id: header
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 14

        // Status indicator: a square LED. It does not blink -- an
        // analog object does not blink, it lights up.
        Rectangle {
            id: statusLed
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: 5; height: 5; radius: 1
            color: root.isIdle ? Theme.idleDim : Theme.accent
            opacity: root.isIdle ? 0.7 : 1.0
            Behavior on opacity { NumberAnimation { duration: 220 } }
        }

        Text {
            anchors.left: statusLed.right
            anchors.leftMargin: 7
            anchors.verticalCenter: parent.verticalCenter
            text: "Audio"
            color: Theme.textSecond
            font.family: Theme.sans
            font.pixelSize: Theme.fsLabel
            font.capitalization: Font.AllUppercase
            font.letterSpacing: 1.4
        }

        // Summary figure: the absolute peak. It is the number a real
        // analyser shows, and the only large-size accent on the
        // screen -- so it has to be on-demand, not permanent.
        Text {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: root.isIdle ? "—" : root.peakLevelText
            color: root.isIdle ? Theme.textGhost : Theme.loadAccent(root.peakLevel / 100)
            font.family: Theme.mono
            font.pixelSize: Theme.fsValue
            font.features: Theme.numFeatures

            Behavior on color { ColorAnimation { duration: 250 } }
        }
    }

    // ─────────────────────────────────────────────────────────────
    // Lanes
    // ─────────────────────────────────────────────────────────────
    Item {
        id: plot
        anchors.top: header.bottom
        anchors.topMargin: 10
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: axis.top
        anchors.bottomMargin: 5

        Repeater {
            model: root.barCount

            Item {
                id: slot
                // Qt6 wants `index` declared explicitly: the implicit
                // injection works but it is not bound to the model.
                required property int index

                // The Repeater does NOT position the delegates: it
                // creates them as siblings and leaves them all at
                // (0,0). You have to assign x by hand. Without this the
                // 32 bars end up stacked on the first one.
                readonly property real cell: plot.width / root.barCount
                x: index * cell
                width: cell
                height: plot.height

                // Each slot takes one cell of the width: the lane always
                // fills the whole available area, whatever that is.
                readonly property real frac:
                    (root.barValues && root.barValues[index] !== undefined)
                        ? Math.max(0, Math.min(1, root.barValues[index] / 100)) : 0
                readonly property real peakFrac:
                    (root.peakValues && root.peakValues[index] !== undefined)
                        ? Math.max(0, Math.min(1, root.peakValues[index] / 100)) : 0

                // Background lane: recessed, the instrument's
                // "graticule". It has to be LIGHTER than the field in
                // order to exist: with Theme.inset (#090908) on a
                // #0e0d0b field it was invisible, there was no graticule.
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: Math.max(2, Math.round(slot.width * 0.42))
                    height: parent.height
                    color: Theme.ruleSoft
                }

                // The signal. Always neutral: the bar is the
                // measurement, not the alarm. The peak cursor is what
                // carries the accent.
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: Math.max(2, Math.round(slot.width * 0.42))
                    height: Math.max(1, slot.frac * parent.height)
                    color: root.isIdle ? Theme.idleDim : Theme.idle
                    Behavior on height {
                        NumberAnimation { duration: 45; easing.type: Easing.OutQuad }
                    }
                }

                // Peak-hold: the falling line is what distinguishes a
                // meter from a bar chart. Same width as the signal plus
                // 2px, otherwise it becomes a floating dash wider than
                // the bar and reads as a rendering error rather than as
                // a cursor.
                Rectangle {
                    visible: !root.isIdle
                             && slot.peakFrac > 0.04
                             // Do not draw it if it coincides with the
                             // top of the signal: that would be a border,
                             // not a cursor.
                             && slot.peakFrac - slot.frac > 0.02
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: Math.min(
                        parent.height - 1, slot.peakFrac * parent.height)
                    width: Math.max(4, Math.round(slot.width * 0.42)) + 2
                    height: 1
                    color: Theme.loadAccent(slot.peakFrac)
                    opacity: root.isIdle ? 0.4 : 0.95
                }
            }
        }
    }

    // ─────────────────────────────────────────────────────────────
    // Axis: a reference line plus a few ticks, not 32 labels
    // ─────────────────────────────────────────────────────────────
    Item {
        id: axis
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        height: 12

        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: 1
            color: Theme.rule
        }

        // An Item, not a Row.
        //
        // A Row is a positioner: it lays its children out itself and
        // overwrites their x. So the explicit `x` below was ignored and
        // the five labels were packed shoulder to shoulder at the left
        // edge, reading "602501k 6k 12k" instead of spreading along the
        // axis. Nothing about the arithmetic was wrong; the container was
        // rearranging the answer.
        Item {
            anchors.top: parent.top
            anchors.topMargin: 3
            anchors.left: parent.left
            anchors.right: parent.right
            height: 10

            Repeater {
                model: [
                    { t: "60", a: 0.0 },
                    { t: "250", a: 0.18 },
                    { t: "1k", a: 0.42 },
                    { t: "6k", a: 0.70 },
                    { t: "12k", a: 1.0 }
                ]
                Text {
                    required property var modelData
                    text: modelData.t
                    // textSecond, not textGhost. The ghost tone (#35332f)
                    // is right on the field and unreadable over the
                    // wallpaper showing through the panel, and the axis
                    // is what tells you what the bars are: a spectrum
                    // with no scale is decoration.
                    color: Theme.textSecond
                    font.family: Theme.mono
                    font.pixelSize: Theme.fsMicro
                    font.features: Theme.numFeatures
                    // Against `axis`, the item these live in, not `plot`:
                    // a sibling that may be a different width.
                    x: Math.round(axis.width * modelData.a)
                       - (modelData.a === 1.0 ? width : 0)
                }
            }
        }
    }
}
