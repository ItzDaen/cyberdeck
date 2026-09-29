// ==============================================================================
// preview.qml — test bench for the wallpaper components.
//
// Why it exists: main.qml derives from WallpaperItem, so it can only run
// inside plasmashell. A QML error in there freezes the whole desktop.
// Questo harness carica gli stessi componenti in una finestra normale, li
// renders to PNG, and the result can be inspected without risking anything.
//
// Uso:
//   QT_QPA_PLATFORM=offscreen qml tools/preview.qml --w 1920 --h 1080 --out /tmp/f.png
// ==============================================================================
import QtQuick
import QtQuick.Window

Window {
    id: win
    visible: true
    width: 1920
    height: 1080
    color: Theme.field
    title: "CyberDeck preview"

    // ── Dati audio simulati, se richiesti ─────────────────────────
    property bool simulateAudio: false
    property int seed: 1

    // ── Contenuto: replica esatta della disposizione di main.qml ──
    InstrumentField {
        anchors.fill: parent
    }

    AudioSpectrum {
        id: viz
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 50
        anchors.horizontalCenter: parent.horizontalCenter
        width: Math.min(parent.width - 48, 560)
    }

    // HUD di prova: TelemetryHUD non è ancora ridisegnato, ma qui basta
    // un segnaposto per verificare la posizione calcolata.
    Rectangle {
        visible: false
        x: win.width - 460 - 42
        y: 42
        width: 460; height: 392
        color: Theme.surface
        border.color: Theme.edge
        radius: Theme.radius
    }

    Timer {
        interval: 1200
        running: true
        repeat: false
        onTriggered: {
            if (win.simulateAudio) injectAudio();
            win.grabToImage(function (result) {
                result.saveToFile(win.outPath);
                Qt.callLater(Qt.quit);
            });
        }
    }

    // Genera uno spettro plausibile: si sommano tre armoniche con inviluppo
    // different, the result resembles real audio far more than noise
    // does, which makes the design.
    function injectAudio() {
        var vals = [], peaks = [];
        for (var i = 0; i < viz.barCount; i++) {
            var x = i / viz.barCount;
            var env = Math.exp(-x * 2.2);                 // calo sulle alte frequenze
            var wobble = 0.5 + 0.5 * Math.sin(x * 9.0 + win.seed);
            var v = env * (0.35 + 0.65 * wobble) * 100;
            v = Math.max(0, Math.min(100, v + (Math.sin(i * 12.9898 + win.seed) * 8)));
            vals.push(v);
            peaks.push(Math.max(0, v - 6 - i * 0.4));
        }
        viz.barValues = vals;
        viz.peakValues = peaks;
        viz.isIdle = false;
    }

    property string outPath: "/tmp/cyberdeck-preview.png"

    // Argomenti da riga di comando
    Component.onCompleted: {
        var a = Qt.application.arguments;
        for (var i = 0; i < a.length; i++) {
            if (a[i] === "--out" && i + 1 < a.length) outPath = a[i + 1];
            if (a[i] === "--w" && i + 1 < a.length) width = parseInt(a[i + 1]);
            if (a[i] === "--h" && i + 1 < a.length) height = parseInt(a[i + 1]);
            if (a[i] === "--audio") simulateAudio = true;
        }
    }
}
