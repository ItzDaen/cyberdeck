// ==============================================================================
// MeterRow.qml — Instrument row: label, bar, value.
// Author: Daen
//
// The base row of the whole panel. Three parts with three different
// typographic weights, which is how a reading is communicated to a
// person:
//
//   LABEL       IBM Plex Sans, uppercase, spaced, grey    ->  what we are talking about
//   BAR         segments, 5px                            ->  where we are
//   VALUE       IBM Plex Mono, tabular figures, bright     ->  the exact number
//
// In the v1.0 HUD those three things had the same weight, colour and
// face: everything was equally important, so nothing was.
// ==============================================================================
import QtQuick

Item {
    id: root

    property string label: ""
    property string valueText: ""
    property real value: 0
    property int segments: 16
    property int barHeight: 5
    // Width of the label column. Fixed, so that the bars on different
    // rows stay aligned and the eye can compare them at a glance.
    property int labelWidth: 48
    // Width of the value column, right-aligned.
    property int valueWidth: 128
    property bool ruleVisible: true

    implicitHeight: 19
    implicitWidth: 400

    // ── Label ──────────────────────────────────────────────
    Text {
        id: labelText
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: root.labelWidth - Theme.gap
        elide: Text.ElideRight
        text: root.label
        color: Theme.textSecond
        font.family: Theme.sans
        font.pixelSize: Theme.fsLabel
        font.capitalization: Font.AllUppercase
        font.letterSpacing: 1.0
    }

    // ── Value ─────────────────────────────────────────────────
    Text {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: root.valueWidth
        horizontalAlignment: Text.AlignRight
        elide: Text.ElideRight
        text: root.valueText
        color: Theme.loadAccent(root.value / 100)
        font.family: Theme.mono
        font.pixelSize: Theme.fsValue
        font.features: Theme.numFeatures

        Behavior on color { ColorAnimation { duration: 200 } }
    }

    // ── Bar ──────────────────────────────────────────────────
    SegmentBar {
        anchors.left: parent.left
        anchors.leftMargin: root.labelWidth
        anchors.right: parent.right
        anchors.rightMargin: root.valueWidth + Theme.gap
        anchors.verticalCenter: parent.verticalCenter
        value: root.value
        segments: root.segments
        barHeight: root.barHeight
    }

    // ── Lower rule ──────────────────────────────────────
    // One continuous line behind everything: the reference base the
    // bar rests on, like the surface of a measurement bench.
    Rectangle {
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.leftMargin: root.labelWidth
        anchors.right: parent.right
        anchors.rightMargin: root.valueWidth + Theme.gap
        height: 1
        color: Theme.ruleSoft
        visible: root.ruleVisible
    }
}
