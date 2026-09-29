pragma ComponentBehavior: Bound

// ==============================================================================
// SegmentBar.qml — Barra a segmenti.
// Author: Daen
//
// Born to end the most obvious duplication in the old HUD: the same
// Repeater of 16 rectangles, with three colours and three different
// thresholds, appeared five times identical in the file. Five copies,
// five places to
// cui sbagliare.
//
// One lit segment = 100/segments. The colour follows Theme.loadAccent,
// but only on the last lit segment: the rest of the lit run stays
// neutral. This is a meter's bar, not an alarm bar.
// ==============================================================================
import QtQuick

Item {
    id: root

    // Valore corrente, 0..100.
    property real value: 0
    property int segments: 16
    property int gap: 3
    property int barHeight: 5

    // How many segments are lit at this value.
    readonly property int lit: Math.max(0, Math.min(segments,
        Math.ceil((Math.max(0, Math.min(100, value)) / 100) * segments)))

    implicitWidth: 200
    implicitHeight: barHeight

    readonly property real segW:
        Math.max(1, (width - gap * (segments - 1)) / segments)

    Repeater {
        model: root.segments

        Rectangle {
            id: seg
            required property int index

            // Repeater non posiziona i delegati: x va assegnata a mano.
            x: index * (root.segW + root.gap)
            y: 0
            width: root.segW
            height: root.barHeight

            readonly property bool on_: index < root.lit
            // Solo l'ultimo segmento acceso porta l'accento.
            readonly property bool isEdge: index === root.lit - 1

            color: !on_ ? Theme.ruleSoft
                        : (isEdge ? Theme.loadAccent(root.value / 100)
                                  : Theme.idle)

            Behavior on color { ColorAnimation { duration: 160 } }
        }
    }
}
