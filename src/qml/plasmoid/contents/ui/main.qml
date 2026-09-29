// ==============================================================================
// main.qml — Plasmoid CyberDeck Telemetry
// Author: Daen
// Platform: CachyOS Linux | KDE Plasma 6 (Wayland)
//
// The PlasmoidItem does nothing more than give TelemetryHUD a container
// of the right size and forward the synchronisation requests. All the
// logic and all the design live in TelemetryHUD.qml.
//
// On positioning: nothing is saved here. An applet's position belongs
// to Plasma, which already records it per screen in the
// ItemGeometries-* keys. If the QML saved it too, two instances on two
// monitors would share the same position and overlap. The size and the
// collapsed state, on the other hand, are shared across all the
// instances and are useful here.
// ==============================================================================
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore

PlasmoidItem {
    id: plasmoidRoot
    preferredRepresentation: fullRepresentation
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground

    property var hudInstance: null

    readonly property int collapsedH: 34
    readonly property int defaultW: 460
    readonly property int defaultH: 440

    width: hudInstance ? hudInstance.width : defaultW
    height: hudInstance ? hudInstance.height : defaultH
    implicitWidth: width
    implicitHeight: height
    Layout.preferredWidth: width
    Layout.preferredHeight: height
    Layout.minimumWidth: hudInstance && hudInstance.isCollapsed ? 220 : 300
    Layout.minimumHeight: hudInstance && hudInstance.isCollapsed ? collapsedH : 200
    Layout.maximumWidth: 1600
    Layout.maximumHeight: 1200

    // Aligns the container to the HUD's instance.
    // w/h not passed = use the HUD's current dimensions.
    function syncContainerSize(w, h, finished) {
        var hInst = plasmoidRoot.hudInstance;
        var cont = hInst ? hInst.getAppletContainer() : plasmoidRoot.parent;
        if (!cont || !hInst) return;

        var targetW = (w !== undefined && w > 0)
            ? w : (hInst.isCollapsed ? hInst.collapsedWidth : hInst.customWidth);
        var targetH = (h !== undefined && h > 0)
            ? h : (hInst.isCollapsed ? plasmoidRoot.collapsedH : hInst.customHeight);

        cont.width  = targetW;
        cont.height = targetH;
        plasmoidRoot.width  = targetW;
        plasmoidRoot.height = targetH;

        if (finished && cont.layout) {
            if (cont.layout.positionItem) cont.layout.positionItem(cont);
            if (cont.layout.save)         cont.layout.save();
        }
    }

    onParentChanged: {
        if (parent) syncTimer.restart();
    }

    // The Plasma container is not ready in Component.onCompleted:
    // without this deferred step the dimensions stay at the defaults
    // and the applet starts crooked.
    Timer {
        id: syncTimer
        interval: 100
        repeat: false
        onTriggered: plasmoidRoot.syncContainerSize(undefined, undefined, true)
    }

    fullRepresentation: Item {
        id: fullRepItem
        width: hud.width
        height: hud.height
        implicitWidth: hud.width
        implicitHeight: hud.height
        Layout.minimumWidth: hud ? (hud.isCollapsed ? 220 : 300) : 300
        Layout.minimumHeight: plasmoidRoot.collapsedH
        Layout.maximumWidth: 1600
        Layout.maximumHeight: 1200
        Layout.preferredWidth: hud.width
        Layout.preferredHeight: hud.height
        clip: true

        TelemetryHUD {
            id: hud
            anchors.top: parent.top
            anchors.left: parent.left
            appletRoot: plasmoidRoot
            Component.onCompleted: {
                plasmoidRoot.hudInstance = this;
                plasmoidRoot.syncContainerSize(undefined, undefined, true);
            }
        }

        Connections {
            target: hud
            function onIsCollapsedChanged() {
                plasmoidRoot.syncContainerSize(undefined, undefined, true);
            }
        }
    }

    // Compact representation: shown when Plasma decides the space is
    // not enough. Same language as the panel, not a random icon.
    compactRepresentation: Rectangle {
        color: Theme.surface
        radius: Theme.radius
        border.width: 1
        border.color: Theme.edge
        implicitWidth: 132
        implicitHeight: 26

        Row {
            anchors.centerIn: parent
            spacing: 7

            Rectangle {
                width: 5; height: 5
                anchors.verticalCenter: parent.verticalCenter
                color: Theme.idle
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "Telemetry"
                color: Theme.text
                font.family: Theme.sans
                font.pixelSize: Theme.fsLabel
                font.capitalization: Font.AllUppercase
                font.letterSpacing: 1.2
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                visible: hudInstance !== null
                text: hudInstance ? hudInstance.cpuUsage + "%" : "—"
                color: Theme.textSecond
                font.family: Theme.mono
                font.pixelSize: Theme.fsLabel
                font.features: Theme.numFeatures
            }
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: plasmoidRoot.expanded = !plasmoidRoot.expanded
        }
    }
}
