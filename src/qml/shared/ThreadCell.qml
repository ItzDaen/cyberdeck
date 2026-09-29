// ==============================================================================
// ThreadCell.qml — A cell of the CPU thread matrix.
// Author: Daen
//
// In v1.0 every cell held "T01:34%": five characters to say that
// thread 1 was at 34%. The number stays, but in Plex Mono at 9px and
// without the "T" label: the position in the grid already says which
// thread it is.
// ==============================================================================
import QtQuick

Rectangle {
    id: root

    property real load: 0
    property int threadNumber: 1
    // Background: dark when the thread is idle, with just a trace of
    // load. Not a different colour for each level: it is a scale, not a
    // traffic light.
    readonly property color base:
        load <= 0.5 ? Theme.inset
                    : Qt.rgba(Theme.idle.r, Theme.idle.g, Theme.idle.b,
                              0.10 + 0.22 * (load / 100))

    color: base
    radius: Theme.radius
    border.width: 1
    border.color: load >= Theme.overloadLevel * 100 ? Theme.alarm
                     : load >= Theme.hotLevel * 100     ? Theme.accentDim
                                                        : Theme.edge

    Behavior on color { ColorAnimation { duration: 200 } }

    // Fill: a load bar from the bottom, with no border.
    Rectangle {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        width: Math.max(0, parent.width * root.load / 100)
        height: parent.height
        radius: Theme.radius
        color: Theme.loadAccent(root.load / 100)
        opacity: 0.30
    }

    Text {
        anchors.centerIn: parent
        text: root.threadNumber
        color: root.load >= Theme.hotLevel * 100 ? Theme.accent
              : root.load > 0.5                   ? Theme.textSecond
                                                  : Theme.textGhost
        font.family: Theme.mono
        font.pixelSize: Theme.fsMicro
        font.features: Theme.numFeatures
    }
}
