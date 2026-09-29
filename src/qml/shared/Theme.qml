pragma Singleton

// ==============================================================================
// Theme.qml — Design system tokens for the "analog instrument" system.
// Author: Daen
//
// Single source of truth for colour, typography and measurements. It
// replaces the ~40 loose #RRGGBB constants in the QML and the green/cyan
// Matrix palette.
//
// It is a singleton declared in qmldir: you use it as `Theme.field`,
// without instantiating it, and the type checker knows its members at
// compile time.
//
// Golden rule: the amber #ff9d2e is the ONLY colour allowed to "move".
// Everything else is warm grey. That is what holds the identity
// together.
// ==============================================================================
import QtQuick

QtObject {
    id: theme

    // ─────────────────────────────────────────────────────────────
    // Superfici — nero caldo, mai blu-informatico
    // ─────────────────────────────────────────────────────────────
    readonly property color field:      "#0e0d0b"   // fondo dello schermo
    readonly property color fieldLight: "#16140f"   // luce dall'alto, +2%
    readonly property color surface:    "#1a1917"   // pannello
    readonly property color surfaceHigh:"#22201d"   // pannello sollevato
    readonly property color inset:      "#090908"   // incavo, traccia canale

    // ─────────────────────────────────────────────────────────────
    // Bordi — 1px, mai 2px. Le ombre non fanno struttura.
    // ─────────────────────────────────────────────────────────────
    readonly property color rule:       "#2a2825"   // separatore strutturale
    readonly property color ruleSoft:   "#1f1d1a"   // separatore interno
    readonly property color edge:       Qt.rgba(1, 1, 1, 0.08)
    readonly property color edgeStrong: Qt.rgba(1, 1, 1, 0.14)

    // ─────────────────────────────────────────────────────────────
    // Text — warm white. Pure #ffffff tires the eye and falsifies the contrast.
    // ─────────────────────────────────────────────────────────────
    readonly property color text:       "#e8e4dc"
    readonly property color textSecond: "#8a857c"
    readonly property color textFaint:  "#565250"
    readonly property color textGhost:  "#35332f"

    // ─────────────────────────────────────────────────────────────
    // Accent — amber, used sparingly
    // ─────────────────────────────────────────────────────────────
    readonly property color accent:     "#ff9d2e"
    readonly property color accentDim:  "#8a5420"
    readonly property color accentWash: Qt.rgba(1.0, 0.616, 0.180, 0.14)

    // Allarme: rosso mattone, non rosso neon.
    readonly property color alarm:      "#d8492f"
    readonly property color alarmDim:   "#7a2a1a"

    // Inactive channel: dim grey-green. It takes the place of the old
    // Matrix green, but an order of magnitude below it.
    readonly property color idle:       "#6b7a6f"
    readonly property color idleDim:    "#3a423b"

    // ─────────────────────────────────────────────────────────────
    // Tipografia
    // Sans for labels, Mono ONLY for the numbers, tabular figures.
    // Monospace on a long string is noise, not information.
    // ─────────────────────────────────────────────────────────────
    readonly property string sans: "IBM Plex Sans"
    readonly property string mono: "IBM Plex Mono"

    readonly property var numFeatures: ({ "tnum": 1, "lnum": 1 })

    // Scala: salto grosso tra etichette e titoli, mai tutto bold.
    readonly property int fsMicro:  9
    readonly property int fsLabel: 10
    readonly property int fsValue: 13
    readonly property int fsReadout: 26
    readonly property int fsHero:  34

    // ─────────────────────────────────────────────────────────────
    // Misure
    // ─────────────────────────────────────────────────────────────
    readonly property int gap:      8
    readonly property int gapWide: 14
    readonly property int pad:     16
    readonly property int radius:   2   // quasi dritto, ma non spigoloso
    readonly property int hairline:  1

    // ─────────────────────────────────────────────────────────────
    // Soglie dell'accento
    //
    // Deliberately below 90%. Any normalisation (cava runs with
    // autosens) keeps the peak steady between 60% and 80% even with
    // full-scale audio: a threshold at 90% would never trigger and the
    // amber would stay a dead colour.
    // ─────────────────────────────────────────────────────────────
    readonly property real hotLevel: 0.65
    readonly property real overloadLevel: 0.88

    // ─────────────────────────────────────────────────────────────
    // Helper functions
    // ─────────────────────────────────────────────────────────────

    // Measurement for a 0..100 value against a given height.
    function meter(value, max, extent) {
        if (!max) return 0;
        return Math.max(0, Math.min(1, value / max)) * extent;
    }

    // Colour of a reading as a function of its load.
    //
    // To be used on the CURSORS and the DIGITS, never on the whole bar:
    // if the whole reading takes the colour, the accent stops being an
    // accent and becomes the background.
    function loadAccent(frac) {
        if (frac >= overloadLevel) return Theme.alarm;
        if (frac >= hotLevel)       return Theme.accent;
        return Theme.textSecond;
    }
}
