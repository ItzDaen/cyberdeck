// ==============================================================================
// Readout.qml — Primary reading: one large number, its label, its
//                unit, and a secondary condition.
// Author: Daen
//
// This is the component the v1.0 HUD did not have. It had ~20 numbers
// all of the same size and colour, so there was no visual hierarchy:
// you could not tell which reading was the important one. Here three
// readings dominate the panel and everything else drops a step.
//
//   31        <- IBM Plex Mono, tabular figures, the reading
//   %         <- unit, small and unlit
//   CPU       <- IBM Plex Sans, uppercase and spaced
//   56 °C     <- secondary condition, bottom right
// ==============================================================================
import QtQuick
import QtQuick.Layouts

Item {
    id: root

    property string label: ""
    property string value: "0"
    property string unit: "%"
    property string sub: ""          // condizione secondaria (temperatura, carico)
    property real load: 0            // 0..100, comanda il colore e la barra
    property bool showBar: true

    implicitWidth: 96
    implicitHeight: 66

    // ── Value ─────────────────────────────────────────────────
    //
    // Digit and unit are in a Layout's Row, not in a plain Row.
    // `Row` is a positioner: it stacks the children vertically, and an
    // `anchors.baseline` on the child conflicts with that positioning
    // (QML reports it and the result is the digit clipped at the top).
    // `Layout.alignment: Qt.AlignBaseline` is the API made for this,
    // and it really does align the two baselines.
    RowLayout {
        id: valueRow
        // Centred, not left. The three cells across the top are equal
        // width, so anchoring to the left left each reading hard against
        // its own edge with an empty column beside it -- visible on a
        // careful look as the numbers not sitting over their own boxes.
        // Everything in this component is centred the same way, because
        // one alignment that disagrees with the rest reads as a mistake
        // rather than as a choice.
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        spacing: 1

        Text {
            id: valueText
            Layout.alignment: Qt.AlignBaseline
            text: root.value
            // Always bright: the digit is the measurement, not the
            // alarm. The accent is carried by the micro bar and the
            // secondary condition, not by the large number -- if the
            // hero number takes the colour, the amber becomes the
            // background instead of the exception.
            color: Theme.text
            font.family: Theme.mono
            font.pixelSize: Theme.fsReadout
            font.features: Theme.numFeatures
        }

        Text {
            id: unitText
            Layout.alignment: Qt.AlignBaseline
            text: root.unit
            color: Theme.textFaint
            font.family: Theme.sans
            font.pixelSize: Theme.fsValue
        }
    }

    // ── Label ──────────────────────────────────────────────
    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: valueRow.bottom
        anchors.topMargin: 1
        text: root.label
        color: Theme.textSecond
        font.family: Theme.sans
        font.pixelSize: Theme.fsLabel
        font.capitalization: Font.AllUppercase
        font.letterSpacing: 1.4
    }

    // ── Secondary condition ──────────────────────────────────
    Text {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.bottom
        anchors.topMargin: -14
        text: root.sub
        color: Theme.textFaint
        font.family: Theme.mono
        font.pixelSize: Theme.fsMicro
        font.features: Theme.numFeatures
        elide: Text.ElideRight
        horizontalAlignment: Text.AlignHCenter
    }

    // ── Micro bar under the condition ─────────────────────────
    // One bar for the primary reading, to give weight to the eye
    // without adding numbers.
    SegmentBar {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        visible: root.showBar
        value: root.load
        segments: 8
        barHeight: 3
    }
}
