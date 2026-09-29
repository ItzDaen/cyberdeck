pragma ComponentBehavior: Bound

// ==============================================================================
// TelemetryHUD.qml — Telemetry panel.
// Author: Daen
// Platform: CachyOS Linux | KDE Plasma 6 (Wayland) | KSysGuard
//
// ── What changes with respect to v1.0 ────────────────────────────────────────
//
// 1. Hierarchy. v1.0 showed ~20 numbers all with the same weight, colour
//    and face: nothing was important. Here three readings dominate the
//    panel (CPU, GPU, MEM) and everything else drops a step.
//
// 2. Typography. The labels are in IBM Plex Sans, the numbers in IBM Plex
//    Mono with tabular figures. Before: everything generic "monospace",
//    and on systems without those fonts (see docs/STATO-v1.0.md) it
//    landed on DejaVu.
//
// 3. Language. Gone: the "[ CPU // ... ]" headers, the pipes, the square
//    brackets and the "•" separator. That was terminal noise, not
//    instrument.
//
// 4. Colour. Gone: the green #00ff66. The amber #ff9d2e is the only
//    accent and appears only past the threshold, on the cursors and on
//    the micro bars.
//
// 5. Deduplication. The 16-segment bar appeared five times, identical
//    apart from the colours and the thresholds. Now it is a component,
//    SegmentBar.qml. Together with MeterRow, Readout and ThreadCell the
//    file goes from 1219 lines to a few hundred: less code, fewer places
//    to get it wrong.
//
// 6. Persistence. In v1.0 the position lived both in LocalStorage and
//    in the INI written by the cyberhud script: two sources of truth
//    that could disagree. Now the position is owned by Plasma (which
//    already saves it per screen in ItemGeometries) and this file saves
//    only the size and the collapsed state, shared between the
//    instances.
//
// 7. Performance Mode: removed. It existed only to switch off the
//    shader, which is no longer there.
// ==============================================================================
import QtQuick
import QtQuick.Layouts
import QtQuick.LocalStorage
import org.kde.ksysguard.sensors 1.0 as Sensors
import com.github.luisbocanegra.audiovisualizer.process 1.0  // for the type `Process`

Item {
    id: root

    // Dimensions
    property real collapsedWidth: 380
    property real customWidth: 460
    // Tall enough for the whole column, spectrum included. It was 440,
    // which is what the panel had before the analyser moved into it, and
    // at 440 the last section falls below the fold: the panel looked the
    // same as it always had and the spectrum was simply not on it.
    //
    // The body is a Flickable and it still scrolls, so nothing is lost if
    // the panel is dragged shorter -- the resize handles at the bottom
    // right change this, and the minimum is 220. This is only the size a
    // panel starts at.
    property real customHeight: 640
    property bool isCollapsed: false
    property bool isResizing: false
    property bool hasUserMoved: false
    property int updateInterval: 1000

    // Reference to the PlasmoidItem when we are inside an applet; null
    // when we are inside the wallpaper.
    property var appletRoot: null

    // Are we inside an applet? Then Plasma owns our position and we
    // must not save it: two instances on two monitors would otherwise
    // share the same position and overlap.
    readonly property bool inApplet: appletRoot !== null

    // ── The yield signal ──────────────────────────────────────────────
    //
    // ~/.cache/cyberdeck/yield, the file the contract publishes. The
    // spectrum stops when it is there and starts when it goes.
    //
    // Watched by a shell loop rather than read: on Qt 6 QML has no file
    // API to read with. Qt.labs.platform ships neither `File` nor
    // `FileSystemWatcher`, and naming a type that does not exist fails the
    // whole component at load rather than degrading, so the loop is the
    // honest mechanism. It prints on a change and repeats every five
    // seconds, because a signal that can be missed once cannot be trusted
    // on the transition that matters.
    readonly property string yieldPath: "~/.cache/cyberdeck/yield"
    property bool yielding: false

    Process {
        id: yieldWatcher
        command: [
            "sh", "-c",
            "prev=unk; n=0; while :; do " +
            "  if [ -f " + yieldPath + " ]; then cur=1; else cur=0; fi; " +
            "  n=$((n+1)); " +
            "  if [ \"$cur\" != \"$prev\" ] || [ $((n % 5)) -eq 0 ]; then " +
            "    echo \"$cur\"; prev=$cur; " +
            "  fi; " +
            "  sleep 1; " +
            "done"
        ]
        onStdoutChanged: {
            const out = (yieldWatcher.stdout || "").trim();
            if (out.length > 0) {
                const last = out[out.length - 1];
                if (last === "0" || last === "1") yielding = (last === "1");
            }
        }
    }

    width:  isCollapsed ? collapsedWidth : customWidth
    height: isCollapsed ? 34 : customHeight

    // ── Resize state ──────────────────────────────
    property real startGlobalX: 0
    property real startGlobalY: 0
    property real startContX: 0
    property real startContY: 0
    property real startW: 0
    property real startH: 0
    property real startCW: 0
    property var activeResizeCont: null

    // ═══════════════════════════════════════════════════════════
    //  RESIZING
    // ═══════════════════════════════════════════════════════════
    function getAppletContainer() {
        var start = root.appletRoot ? root.appletRoot : root;
        var p = start;
        while (p) {
            if (p.layout !== undefined
                && (p.layout.positionItem !== undefined || p.userDrag !== undefined)) {
                return p;
            }
            p = p.parent;
        }
        return (start && start.parent) ? start.parent : null;
    }

    function startResize(area, mouse, handleType) {
        root.isResizing = true;
        activeResizeCont = root.getAppletContainer();
        if (activeResizeCont && activeResizeCont.layout
            && activeResizeCont.layout.releaseSpace) {
            activeResizeCont.layout.releaseSpace(activeResizeCont);
        }
        var p = area.mapToItem(null, mouse.x, mouse.y);
        startGlobalX = p.x;
        startGlobalY = p.y;
        startContX = activeResizeCont ? activeResizeCont.x : 0;
        startContY = activeResizeCont ? activeResizeCont.y : 0;
        startW  = root.customWidth;
        startH  = root.customHeight;
        startCW = root.collapsedWidth;
    }

    function updateResize(area, mouse, handleType) {
        if (!root.isResizing) return;
        var p = area.mapToItem(null, mouse.x, mouse.y);
        var dx = p.x - startGlobalX;
        var dy = p.y - startGlobalY;
        var cont = activeResizeCont;

        if (root.isCollapsed) {
            // Collapsed: only the width is adjustable.
            if (handleType === "e" || handleType === "se" || handleType === "ne") {
                root.collapsedWidth = Math.max(220, Math.min(1200, startCW + dx));
                if (cont) cont.width = root.collapsedWidth;
            } else if (handleType === "w" || handleType === "sw" || handleType === "nw") {
                var newCW = Math.max(220, Math.min(1200, startCW - dx));
                var actualDx = startCW - newCW;
                root.collapsedWidth = newCW;
                if (cont) {
                    cont.x = Math.max(0, startContX + actualDx);
                    cont.width = newCW;
                }
            }
            if (root.appletRoot && root.appletRoot.syncContainerSize) {
                root.appletRoot.syncContainerSize(root.collapsedWidth, 34, false);
            }
            return;
        }

        // ── Horizontal ──
        if (handleType === "se" || handleType === "ne" || handleType === "e") {
            root.customWidth = Math.max(320, Math.min(1400, startW + dx));
            if (cont) cont.width = root.customWidth;
        } else if (handleType === "sw" || handleType === "nw" || handleType === "w") {
            var nw = Math.max(320, Math.min(1400, startW - dx));
            var adx = startW - nw;
            root.customWidth = nw;
            if (cont) {
                cont.x = Math.max(0, startContX + adx);
                cont.width = nw;
            }
        }

        // ── Vertical ──
        if (handleType === "se" || handleType === "sw" || handleType === "s") {
            root.customHeight = Math.max(220, Math.min(1100, startH + dy));
            if (cont) cont.height = root.customHeight;
        } else if (handleType === "ne" || handleType === "nw") {
            var nh = Math.max(220, Math.min(1100, startH - dy));
            var ady = startH - nh;
            root.customHeight = nh;
            if (cont) {
                cont.y = Math.max(0, startContY + ady);
                cont.height = nh;
            }
        }

        if (root.appletRoot && root.appletRoot.syncContainerSize) {
            root.appletRoot.syncContainerSize(root.customWidth, root.customHeight, false);
        }
    }

    function finishResize(handleType) {
        root.isResizing = false;
        var cont = activeResizeCont;
        root.saveState();

        var targetW = root.isCollapsed ? root.collapsedWidth : root.customWidth;
        var targetH = root.isCollapsed ? 34 : root.customHeight;

        if (cont) {
            cont.width  = targetW;
            cont.height = targetH;
            if (cont.layout) {
                if (cont.layout.hidePlaceHolder) cont.layout.hidePlaceHolder();
                if (cont.layout.positionItem)  cont.layout.positionItem(cont);
                if (cont.layout.save)          cont.layout.save();
            }
        }
        if (root.appletRoot && root.appletRoot.syncContainerSize) {
            root.appletRoot.syncContainerSize(targetW, targetH, true);
        }
        activeResizeCont = null;
    }

    // ═══════════════════════════════════════════════════════════
    //  PERSISTENCE
    //
    //  We save the size, the collapsed width and the collapsed state:
    //  they are shareable between the instances and do not conflict.
    //  x/y are saved ONLY in the wallpaper: in the applet the position
    //  belongs to Plasma.
    // ═══════════════════════════════════════════════════════════
    function getDb() {
        // The name includes the layout version. The default size went
        // from 392 to 440 because the content did not fit: without
        // changing the database, LocalStorage would go on returning
        // 392 and the panel would stay clipped.
        return LocalStorage.openDatabaseSync("CyberDeckHudV2", "1.0",
                                            "CyberDeck HUD Storage", 100000);
    }

    function saveState() {
        try {
            var db = getDb();
            db.transaction(function (tx) {
                tx.executeSql('CREATE TABLE IF NOT EXISTS State(key TEXT UNIQUE, val TEXT)');
                tx.executeSql('INSERT OR REPLACE INTO State VALUES("w", ?)',  [String(root.customWidth)]);
                tx.executeSql('INSERT OR REPLACE INTO State VALUES("h", ?)',  [String(root.customHeight)]);
                tx.executeSql('INSERT OR REPLACE INTO State VALUES("c", ?)',  [root.isCollapsed ? "1" : "0"]);
                tx.executeSql('INSERT OR REPLACE INTO State VALUES("cw", ?)', [String(root.collapsedWidth)]);
                if (!root.inApplet) {
                    tx.executeSql('INSERT OR REPLACE INTO State VALUES("x", ?)', [String(Math.round(root.x))]);
                    tx.executeSql('INSERT OR REPLACE INTO State VALUES("y", ?)', [String(Math.round(root.y))]);
                }
            });
        } catch (e) { console.warn("[HUD] saving state:", e); }
    }

    function loadState() {
        try {
            var db = getDb();
            db.transaction(function (tx) {
                tx.executeSql('CREATE TABLE IF NOT EXISTS State(key TEXT UNIQUE, val TEXT)');
                var rs = tx.executeSql('SELECT key, val FROM State');
                for (var i = 0; i < rs.rows.length; i++) {
                    var it = rs.rows.item(i);
                    if (it.key === "w")  root.customWidth  = Math.max(320, Math.min(1400, parseFloat(it.val)));
                    else if (it.key === "h")  root.customHeight = Math.max(220, Math.min(1100, parseFloat(it.val)));
                    else if (it.key === "c")  root.isCollapsed  = (it.val === "1");
                    else if (it.key === "cw") root.collapsedWidth = Math.max(220, Math.min(1200, parseFloat(it.val)));
                    else if (it.key === "x" && !root.inApplet) { root.x = parseFloat(it.val); root.hasUserMoved = true; }
                    else if (it.key === "y" && !root.inApplet) { root.y = parseFloat(it.val); root.hasUserMoved = true; }
                }
            });
        } catch (e) { console.warn("[HUD] loading state:", e); }

        // In the wallpaper, with no saved position, it goes to the top
        // right with a margin proportional to the resolution.
        if (!root.inApplet && !root.hasUserMoved && root.parent && root.parent.width > 0) {
            var cw = root.isCollapsed ? root.collapsedWidth : root.customWidth;
            var m = Math.round(Math.min(root.parent.width, root.parent.height) * 0.022);
            root.x = Math.max(m, root.parent.width - cw - m);
            root.y = m;
        }
        if (root.appletRoot && root.appletRoot.syncContainerSize) {
            root.appletRoot.syncContainerSize(root.width, root.height);
        }
    }

    Component.onCompleted: loadState()

    // ═══════════════════════════════════════════════════════════
    //  SENSORS
    // ═══════════════════════════════════════════════════════════
    Sensors.Sensor { id: cpuUsageSensor;  sensorId: "cpu/all/usage";              updateRateLimit: root.updateInterval }
    Sensors.Sensor { id: cpuFreqSensor;   sensorId: "cpu/all/averageFrequency";    updateRateLimit: root.updateInterval }
    Sensors.Sensor { id: cpuTempSensor;   sensorId: "cpu/all/averageTemperature";  updateRateLimit: root.updateInterval }
    Sensors.Sensor { id: load1Sensor;     sensorId: "cpu/loadaverages/loadaverage1"; updateRateLimit: 2000 }
    Sensors.Sensor { id: load5Sensor;     sensorId: "cpu/loadaverages/loadaverage5"; updateRateLimit: 2000 }

    Sensors.Sensor { id: ramUsedSensor;   sensorId: "memory/physical/used";         updateRateLimit: root.updateInterval }
    Sensors.Sensor { id: ramTotalSensor;  sensorId: "memory/physical/total";        updateRateLimit: 5000 }
    Sensors.Sensor { id: swapUsedSensor;  sensorId: "memory/swap/used";             updateRateLimit: root.updateInterval }
    Sensors.Sensor { id: swapTotalSensor; sensorId: "memory/swap/total";            updateRateLimit: 5000 }

    Sensors.Sensor { id: gpuUsageSensor;  sensorId: "gpu/gpu0/usage";               updateRateLimit: root.updateInterval }
    Sensors.Sensor { id: gpuTempSensor;   sensorId: "gpu/gpu0/temperature";         updateRateLimit: root.updateInterval }
    Sensors.Sensor { id: gpuTemp2Sensor;  sensorId: "gpu/gpu0/temp2";              updateRateLimit: root.updateInterval }
    Sensors.Sensor { id: gpuVramSensor;   sensorId: "gpu/gpu0/usedVram";           updateRateLimit: root.updateInterval }
    Sensors.Sensor { id: gpuTotalVramSensor; sensorId: "gpu/gpu0/totalVram";       updateRateLimit: 5000 }
    Sensors.Sensor { id: gpuPowerSensor;  sensorId: "gpu/gpu0/power1";              updateRateLimit: root.updateInterval }
    Sensors.Sensor { id: gpuCoreClockSensor; sensorId: "gpu/gpu0/coreFrequency";    updateRateLimit: root.updateInterval }
    Sensors.Sensor { id: gpuMemClockSensor;  sensorId: "gpu/gpu0/memoryFrequency";  updateRateLimit: root.updateInterval }
    Sensors.Sensor { id: gpuFanSensor;    sensorId: "gpu/gpu0/fan1";                updateRateLimit: root.updateInterval }

    Sensors.Sensor { id: diskReadSensor;  sensorId: "disk/all/read";               updateRateLimit: root.updateInterval }
    Sensors.Sensor { id: diskWriteSensor; sensorId: "disk/all/write";              updateRateLimit: root.updateInterval }
    Sensors.Sensor { id: diskUsedPctSensor; sensorId: "disk/all/usedPercent";     updateRateLimit: 5000 }
    Sensors.Sensor { id: diskTotalSensor; sensorId: "disk/all/total";              updateRateLimit: 5000 }

    Sensors.Sensor { id: cpuFanSensor;    sensorId: "lmsensors/nct6797-isa-0a20/fan2"; updateRateLimit: root.updateInterval }
    Sensors.Sensor { id: chassisFanSensor; sensorId: "lmsensors/nct6797-isa-0a20/fan5"; updateRateLimit: root.updateInterval }
    Sensors.Sensor { id: uptimeSensor;   sensorId: "os/system/uptime";             updateRateLimit: 5000 }
    Sensors.Sensor { id: kernelSensor;   sensorId: "os/kernel/version";            updateRateLimit: 60000 }
    Sensors.Sensor { id: hostSensor;     sensorId: "os/system/hostname";           updateRateLimit: 60000 }

    // ═══════════════════════════════════════════════════════════
    //  DERIVED VALUES
    // ═══════════════════════════════════════════════════════════
    function num(v, fallback) {
        return (v !== undefined && !isNaN(v)) ? v : fallback;
    }

    readonly property real cpuUsage: Math.round(num(cpuUsageSensor.value, 0))
    readonly property string cpuFreq: {
        if (!cpuFreqSensor.value) return "—";
        var mhz = cpuFreqSensor.value;
        return (mhz >= 1000) ? (mhz / 1000).toFixed(2) + " GHz" : Math.round(mhz) + " MHz";
    }
    readonly property real cpuTemp: Math.round(num(cpuTempSensor.value, 0))
    readonly property string loadAvgStr: {
        var l1 = (load1Sensor.value !== undefined && !isNaN(load1Sensor.value)) ? load1Sensor.value.toFixed(2) : "—";
        var l5 = (load5Sensor.value !== undefined && !isNaN(load5Sensor.value)) ? load5Sensor.value.toFixed(2) : "—";
        return l1 + " / " + l5;
    }

    readonly property real ramUsedGB:  (ramUsedSensor.value  > 0) ? ramUsedSensor.value  / 1073741824 : 0
    readonly property real ramTotalGB: (ramTotalSensor.value > 0) ? ramTotalSensor.value / 1073741824 : 32
    readonly property real ramPercent: (ramTotalGB > 0) ? Math.round((ramUsedGB / ramTotalGB) * 100) : 0

    readonly property real swapUsedGB:  (swapUsedSensor.value  > 0) ? swapUsedSensor.value  / 1073741824 : 0
    readonly property real swapTotalGB: (swapTotalSensor.value > 0) ? swapTotalSensor.value / 1073741824 : 32
    readonly property real swapPercent: (swapTotalGB > 0) ? Math.round((swapUsedGB / swapTotalGB) * 100) : 0

    readonly property real gpuUsage: Math.round(num(gpuUsageSensor.value, 0))
    readonly property real gpuTemp: Math.round(num(gpuTempSensor.value, 0))
    readonly property real gpuTempJunc: Math.round(num(gpuTemp2Sensor.value, gpuTemp))
    readonly property real gpuVramGB: (gpuVramSensor.value > 0) ? gpuVramSensor.value / 1073741824 : 0
    readonly property real gpuTotalVramGB: (gpuTotalVramSensor.value > 0) ? gpuTotalVramSensor.value / 1073741824 : 8
    readonly property real gpuVramPercent: (gpuTotalVramGB > 0) ? Math.round((gpuVramGB / gpuTotalVramGB) * 100) : 0
    readonly property real gpuPowerW: Math.round(num(gpuPowerSensor.value, 0))
    readonly property int gpuClockMHz: Math.round(num(gpuCoreClockSensor.value, 0))
    readonly property int gpuMemClockMHz: Math.round(num(gpuMemClockSensor.value, 0))
    readonly property int gpuFanRPM: (gpuFanSensor.value > 0) ? Math.round(gpuFanSensor.value) : 0

    readonly property real diskUsedPct: Math.round(num(diskUsedPctSensor.value, 0))
    readonly property real diskTotalTB: (diskTotalSensor.value > 0) ? diskTotalSensor.value / 1099511627776 : 0
    readonly property int cpuFanRPM: (cpuFanSensor.value > 0) ? Math.round(cpuFanSensor.value) : 0
    readonly property int chassisFanRPM: (chassisFanSensor.value > 0) ? Math.round(chassisFanSensor.value) : 0

    readonly property string diskReadStr:  formatRate(diskReadSensor.value)
    readonly property string diskWriteStr: formatRate(diskWriteSensor.value)

    function formatRate(b) {
        if (!b || isNaN(b) || b < 0) return "0 B/s";
        if (b < 1024) return Math.round(b) + " B/s";
        if (b < 1048576) return (b / 1024).toFixed(1) + " KB/s";
        return (b / 1048576).toFixed(1) + " MB/s";
    }

    readonly property string uptimeStr: {
        if (!uptimeSensor.value) return "—";
        var s = uptimeSensor.value;
        var h = Math.floor(s / 3600);
        var m = Math.floor((s % 3600) / 60);
        return h + "h " + (m < 10 ? "0" : "") + m + "m";
    }
    readonly property string kernelStr: (kernelSensor.value) ? kernelSensor.value : "linux"
    readonly property string hostStr:   (hostSensor.value)   ? hostSensor.value   : "—"

    // Thermal load: the maximum of the two packages, so you can tell at
    // a glance whether the system is warm without reading two numbers.
    readonly property real maxTemp: Math.max(cpuTemp, gpuTemp)
    readonly property bool isHot: maxTemp >= 75

    Behavior on width  { enabled: !root.isResizing; NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
    Behavior on height { enabled: !root.isResizing; NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

    // ═══════════════════════════════════════════════════════════
    //  PANEL BODY
    // ═══════════════════════════════════════════════════════════
    Rectangle {
        id: panel
        anchors.fill: parent
        color: Theme.surface
        radius: Theme.radius
        clip: true
        opacity: 0.94

        // 1px border. In v1.0 it was 1.5px and shifted from cyan to green
        // on hover: a border that changes colour is an effect, not a
        // border.
        border.width: 1
        border.color: root.isResizing ? Theme.accent : Theme.edge

        Behavior on border.color { ColorAnimation { duration: 160 } }

        // ─────────────────────────────────────────────────────
        //  Header: identity and controls
        // ─────────────────────────────────────────────────────
        Item {
            id: header
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: root.isCollapsed ? parent.height : 32

            // Lower rule: separates the header from the body without
            // needing a border everywhere.
            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 1
                color: Theme.rule
                visible: !root.isCollapsed
            }

            MouseArea {
                id: headerMouse
                anchors.fill: parent
                anchors.leftMargin: root.isCollapsed ? 10 : 34
                anchors.rightMargin: 38
                hoverEnabled: true
                acceptedButtons: Qt.LeftButton
                cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor

                property var cont: null
                property real startMouseX: 0
                property real startMouseY: 0
                property real startContX: 0
                property real startContY: 0

                onPressed: (mouse) => {
                    cont = root.getAppletContainer();
                    if (cont) {
                        var p = mapToItem(null, mouse.x, mouse.y);
                        startMouseX = p.x;  startMouseY = p.y;
                        startContX = cont.x; startContY = cont.y;
                        if (cont.layout && cont.layout.releaseSpace) {
                            cont.layout.releaseSpace(cont);
                        }
                    }
                }

                onPositionChanged: (mouse) => {
                    if (pressed && cont) {
                        var p = mapToItem(null, mouse.x, mouse.y);
                        cont.x = Math.max(0, startContX + (p.x - startMouseX));
                        cont.y = Math.max(0, startContY + (p.y - startMouseY));
                    }
                }

                onReleased: {
                    if (cont) {
                        if (cont.layout) {
                            if (cont.layout.hidePlaceHolder) cont.layout.hidePlaceHolder();
                            if (cont.layout.positionItem)  cont.layout.positionItem(cont);
                            if (cont.layout.save)          cont.layout.save();
                        }
                        cont = null;
                    }
                    root.hasUserMoved = true;
                    root.saveState();
                    if (root.appletRoot && root.appletRoot.syncContainerSize) {
                        root.appletRoot.syncContainerSize(root.width, root.height, true);
                    }
                }

                onDoubleClicked: root.toggleCollapsed()
            }

            // ── Mark ──
            // One filled square and the name. No square brackets: they
            // are the terminal's signature, not an instrument's.
            Row {
                id: mark
                anchors.left: parent.left
                anchors.leftMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                spacing: 7

                Rectangle {
                    width: 6; height: 6
                    anchors.verticalCenter: parent.verticalCenter
                    color: root.isHot ? Theme.alarm
                         : headerMouse.containsMouse ? Theme.accent
                                                    : Theme.idle
                    Behavior on color { ColorAnimation { duration: 200 } }
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Telemetry"
                    color: Theme.text
                    font.family: Theme.sans
                    font.pixelSize: Theme.fsValue
                    font.capitalization: Font.AllUppercase
                    font.letterSpacing: 1.6
                }
            }

            // ── Quick readings, only when collapsed ──
            // Expanded, the header stays clean: the numbers are all in
            // the body already, repeating them here would be noise.
            Row {
                id: strip
                anchors.right: collapseButton.left
                anchors.rightMargin: Theme.gapWide
                anchors.verticalCenter: parent.verticalCenter
                spacing: 16
                visible: root.isCollapsed
                clip: true

                Repeater {
                    id: stripRepeater
                    model: [
                        { l: "CPU", v: root.cpuUsage, t: root.cpuTemp },
                        { l: "GPU", v: root.gpuUsage, t: root.gpuTemp },
                        { l: "MEM", v: root.ramPercent, t: 0 }
                    ]
                    Row {
                        id: stripItem
                        required property var modelData
                        spacing: 5

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: stripItem.modelData.l
                            color: Theme.textFaint
                            font.family: Theme.sans
                            font.pixelSize: Theme.fsMicro
                            font.capitalization: Font.AllUppercase
                            font.letterSpacing: 1.0
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: stripItem.modelData.v + "%"
                            color: Theme.text
                            font.family: Theme.mono
                            font.pixelSize: Theme.fsValue
                            font.features: Theme.numFeatures
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: stripItem.modelData.t > 0
                            text: stripItem.modelData.t + "°"
                            color: Theme.loadAccent(stripItem.modelData.t / 100)
                            font.family: Theme.mono
                            font.pixelSize: Theme.fsMicro
                            font.features: Theme.numFeatures
                        }
                    }
                }
            }

            // ── Machine identity, only when expanded ──
            Text {
                anchors.right: collapseButton.left
                anchors.rightMargin: Theme.gapWide
                anchors.verticalCenter: parent.verticalCenter
                visible: !root.isCollapsed
                text: root.hostStr + " · " + root.kernelStr
                color: Theme.textFaint
                font.family: Theme.mono
                font.pixelSize: Theme.fsMicro
                font.features: Theme.numFeatures
                elide: Text.ElideRight
                width: Math.min(implicitWidth, Math.max(0, panel.width - 200))
            }

            // ── Collapse/expand button ──
            Item {
                id: collapseButton
                anchors.right: parent.right
                anchors.rightMargin: 6
                anchors.verticalCenter: parent.verticalCenter
                width: 22; height: 22
                visible: headerMouse.hoverEnabled

                Rectangle {
                    anchors.fill: parent
                    radius: Theme.radius
                    color: collapseMouse.containsMouse ? Theme.surfaceHigh : "transparent"
                }

                // Chevron: two segments drawing an arrow. A ▼/▲ glyph in
                // a monospace font was wrong in height and weight.
                Canvas {
                    id: chevron
                    anchors.centerIn: parent
                    width: 9; height: 9

                    property color stroke: collapseMouse.containsMouse
                        ? Theme.accent : Theme.textSecond

                    onStrokeChanged: requestPaint()
                    Component.onCompleted: requestPaint()

                    onPaint: {
                        var ctx = getContext("2d");
                        ctx.reset();
                        ctx.strokeStyle = stroke;
                        ctx.lineWidth = 1.4;
                        ctx.lineCap = "round";
                        ctx.lineJoin = "round";
                        var d = root.isCollapsed ? 2.5 : -0.5;   // ▼ piegato, ▲ espanso
                        ctx.beginPath();
                        ctx.moveTo(1, 3 + d);
                        ctx.lineTo(4.5, 6.5 + d);
                        ctx.lineTo(8, 3 + d);
                        ctx.stroke();
                    }
                }

                MouseArea {
                    id: collapseMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.toggleCollapsed()
                }
            }
        }

        // ─────────────────────────────────────────────────────
        //  Body
        // ─────────────────────────────────────────────────────
        Flickable {
            id: body
            anchors.top: header.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: Theme.pad
            anchors.topMargin: Theme.pad
            anchors.bottomMargin: Theme.pad - 2
            clip: true
            visible: !root.isCollapsed
            contentWidth: width
            contentHeight: content.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            // No scrollbar: in a 460px panel it is noise. It scrolls with
            // the wheel and with touch like any other surface.
            flickableDirection: Flickable.VerticalFlick

            Column {
                id: content
                width: body.width
                spacing: Theme.gapWide - 2

                // ── Primary readings ──────────────────────────
                // The hierarchy that was missing: three large numbers at
                // the top, everything else below and smaller.
                Row {
                    width: parent.width
                    spacing: Theme.gap

                    Readout {
                        width: (parent.width - Theme.gap * 2) / 3
                        label: "CPU"
                        value: String(root.cpuUsage)
                        sub: root.cpuTemp + " °C"
                        load: root.cpuUsage
                    }
                    Readout {
                        width: (parent.width - Theme.gap * 2) / 3
                        label: "GPU"
                        value: String(root.gpuUsage)
                        sub: root.gpuTemp + " °C"
                        load: root.gpuUsage
                    }
                    Readout {
                        width: (parent.width - Theme.gap * 2) / 3
                        label: "Memory"
                        value: String(root.ramPercent)
                        sub: root.ramUsedGB.toFixed(1) + " / " + root.ramTotalGB.toFixed(0) + " GB"
                        load: root.ramPercent
                    }
                }

                // ── Subsystems ─────────────────────────────
                Column {
                    width: parent.width
                    spacing: Theme.gap

                    MeterRow {
                        width: parent.width
                        label: "CPU"
                        valueText: root.cpuUsage + "% · " + root.cpuFreq
                        value: root.cpuUsage
                    }
                    MeterRow {
                        width: parent.width
                        label: "GPU"
                        valueText: root.gpuUsage + "% · " + root.gpuPowerW + " W"
                        value: root.gpuUsage
                    }
                    MeterRow {
                        width: parent.width
                        label: "VRAM"
                        valueText: root.gpuVramGB.toFixed(1) + " / " + root.gpuTotalVramGB.toFixed(0) + " GB"
                        value: root.gpuVramPercent
                    }
                    MeterRow {
                        width: parent.width
                        label: "Swap"
                        valueText: root.swapUsedGB.toFixed(1) + " / " + root.swapTotalGB.toFixed(0) + " GB"
                        value: root.swapPercent
                    }
                    MeterRow {
                        width: parent.width
                        label: "Disk"
                        valueText: root.diskTotalTB.toFixed(1) + " TB"
                        value: root.diskUsedPct
                        ruleVisible: false
                    }
                }

                // ── Thread matrix ───────────────────────
                Column {
                    id: threadGroup
                    width: parent.width
                    spacing: 5

                    Text {
                        text: "Thread"
                        color: Theme.textSecond
                        font.family: Theme.sans
                        font.pixelSize: Theme.fsLabel
                        font.capitalization: Font.AllUppercase
                        font.letterSpacing: 1.0
                    }

                    Grid {
                        id: threadGrid
                        width: parent.width
                        columns: 8
                        spacing: 3

                        Repeater {
                            model: 16

                            ThreadCell {
                                id: cell
                                required property int index
                                threadNumber: cell.index + 1

                                // The cell has no size of its own: without
                                // these two lines it is 0x0 and the grid
                                // comes out empty. 8 columns across the
                                // available width, minus the 7 gaps.
                                width: Math.max(12, Math.floor(
                                    (threadGrid.width - 3 * 7) / 8))
                                height: 18

                                Sensors.Sensor {
                                    id: coreSensor
                                    sensorId: "cpu/cpu" + cell.index + "/usage"
                                    updateRateLimit: root.updateInterval
                                }

                                load: (coreSensor.value !== undefined && !isNaN(coreSensor.value))
                                      ? Math.round(coreSensor.value) : 0
                            }
                        }
                    }
                }

                // ── Frequencies, cooling, disk ───────────
                // Two sections in one. Frequencies and I/O were
                // separate blocks identical in shape (a title plus a
                // 4-column row): merging them saves a title and a
                // section's spacing, and that is what was making the
                // panel exceed its height.
                Column {
                    width: parent.width
                    spacing: 5

                    Text {
                        text: "Frequencies & storage"
                        color: Theme.textSecond
                        font.family: Theme.sans
                        font.pixelSize: Theme.fsLabel
                        font.capitalization: Font.AllUppercase
                        font.letterSpacing: 1.0
                    }

                    Grid {
                        width: parent.width
                        columns: 4
                        rowSpacing: 6
                        columnSpacing: Theme.gap

                        // Row 1: clock and fans
                        Repeater {
                            model: [
                                { l: "Core",    v: root.gpuClockMHz + " MHz" },
                                { l: "Memory",  v: root.gpuMemClockMHz + " MHz" },
                                { l: "CPU fan", v: root.cpuFanRPM + " rpm" },
                                { l: "GPU fan", v: root.gpuFanRPM + " rpm" }
                            ]
                            Column {
                                id: clockItem
                                required property var modelData
                                width: (threadGroup.width - Theme.gap * 3) / 4
                                spacing: 1

                                Text {
                                    text: clockItem.modelData.l
                                    color: Theme.textFaint
                                    font.family: Theme.sans
                                    font.pixelSize: Theme.fsMicro
                                    font.capitalization: Font.AllUppercase
                                    font.letterSpacing: 0.8
                                    elide: Text.ElideRight
                                    width: parent.width
                                }
                                Text {
                                    text: clockItem.modelData.v
                                    color: Theme.text
                                    font.family: Theme.mono
                                    font.pixelSize: Theme.fsLabel
                                    font.features: Theme.numFeatures
                                    elide: Text.ElideRight
                                    width: parent.width
                                }
                            }
                        }

                        // Row 2: I/O, uptime, load
                        Repeater {
                            model: [
                                { l: "Read",      v: root.diskReadStr },
                                { l: "Write",     v: root.diskWriteStr },
                                { l: "Uptime",   v: root.uptimeStr },
                                { l: "Load",     v: root.loadAvgStr }
                            ]
                            Column {
                                id: ioItem
                                required property var modelData
                                width: (threadGroup.width - Theme.gap * 3) / 4
                                spacing: 1

                                Text {
                                    text: ioItem.modelData.l
                                    color: Theme.textFaint
                                    font.family: Theme.sans
                                    font.pixelSize: Theme.fsMicro
                                    font.capitalization: Font.AllUppercase
                                    font.letterSpacing: 0.8
                                    elide: Text.ElideRight
                                    width: parent.width
                                }
                                Text {
                                    text: ioItem.modelData.v
                                    color: Theme.text
                                    font.family: Theme.mono
                                    font.pixelSize: Theme.fsLabel
                                    font.features: Theme.numFeatures
                                    elide: Text.ElideRight
                                    width: parent.width
                                }
                            }
                        }
                    }
                }

                // ─────────────────────────────────────────────────
                //  Audio spectrum
                // ─────────────────────────────────────────────────
                //
                // It lives here, at the bottom of the same column as every
                // other section, and that is the whole point of the move.
                //
                // It was a desktop widget of its own, which bought three
                // things and cost three more. It bought surviving a change
                // of wallpaper, and it cost: a second analyser on every
                // screen, a second window to place, and a second thing that
                // refuses to be moved -- `immutability` came back on it
                // after every plasmashell restart while the panel beside it
                // behaved, and there was no way to tell from inside which
                // of the two was at fault.
                //
                // Here it needs none of that. The panel is already
                // movable, already resizable, already on both screens, and
                // already obeys the yield signal because it is one object
                // with one lifetime. A section of a panel is not a window
                // and inherits nothing from one.
                AudioSpectrum {
                    id: spectrum
                    // Explicit width and height, not `Layout.*`.
                    //
                    // The container is a plain `Column`, which is a
                    // positioner: it arranges its children itself and
                    // knows nothing about the attached `Layout` properties,
                    // so `Layout.fillWidth` and `Layout.preferredHeight`
                    // were silently discarded. AudioSpectrum is an `Item`
                    // with a height and no width, so it came out 0 wide --
                    // present, running its own cava, and drawing nothing at
                    // all. Which is why it could not be found: not hidden
                    // below the fold, not failing, simply zero pixels wide.
                    width: content.width
                    height: 96
                    // Always running, including while yielding.
                    //
                    // This used to be `!yielding`, on the reasoning that
                    // yielding means giving the machine away. Measured, that
                    // was the wrong thing to give away: the analyser costs
                    // about 2.4% of a core and the video wallpaper it was
                    // standing aside for was measured at 3-19% of the GPU.
                    // The performance mode exists for a game and for a
                    // render, and the wallpaper is the large item, not this.
                    //
                    // So the signal no longer stops the analyser. It is
                    // still read, and it is still shown below, because
                    // knowing the mode is on is worth more than having the
                    // bars disappear to say so.
                    active: true
                }

                // The mode, said rather than acted on. Without this the
                // panel would look identical in FULL and in YIELD, and a
                // silent difference is how a stopped thing and a working
                // thing get confused for each other.
                Item {
                    width: content.width
                    height: visible ? 18 : 0
                    visible: root.yielding

                    Rectangle {
                        id: yieldDot
                        width: 6; height: 6; radius: 1
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.accent
                    }

                    Text {
                        anchors.left: yieldDot.right
                        anchors.leftMargin: 7
                        anchors.verticalCenter: parent.verticalCenter
                        text: "YIELDING — GPU to a game or a render. The wallpaper is stopped; this analyser is not."
                        color: Theme.textFaint
                        font.family: Theme.sans
                        font.pixelSize: Theme.fsMicro
                        font.capitalization: Font.AllUppercase
                        font.letterSpacing: 0.8
                        elide: Text.ElideRight
                        width: parent.width - yieldDot.width - 7
                    }
                }
            }
        }

        // ─────────────────────────────────────────────────────
        //  Resize handles
        //
        //  Eight identical handles, generated from a table. In v1.0 they
        //  were eight nearly equal blocks with eight Canvas items
        //  redrawn by hand: 400 lines to draw eight arrows.
        //
        //  The anchoring uses only left/right/top/bottom: mixing
        //  horizontalCenter with left or right is a conflict and QML
        //  rejects it. Whoever wants the full length declares the two
        //  opposite sides and leaves w/h at 0.
        // ─────────────────────────────────────────────────────
        Repeater {
            model: [
                //      h    al ar at ab   w   hh  ml mt mr mb  vis
                { k: "se", al: 0, ar: 1, at: 0, ab: 1, w: 26, hh: 26, ml: 0,  mt: 0,  mr: 0, mb: 0, vis: !root.isCollapsed },
                { k: "sw", al: 1, ar: 0, at: 0, ab: 1, w: 26, hh: 26, ml: 0,  mt: 0,  mr: 0, mb: 0, vis: !root.isCollapsed },
                { k: "ne", al: 0, ar: 1, at: 1, ab: 0, w: 22, hh: 22, ml: 0,  mt: 0,  mr: 0, mb: 0, vis: !root.isCollapsed },
                { k: "nw", al: 1, ar: 0, at: 1, ab: 0, w: 22, hh: 22, ml: 0,  mt: 0,  mr: 0, mb: 0, vis: !root.isCollapsed },
                { k: "e",  al: 0, ar: 1, at: 1, ab: 1, w: 7,  hh: 0,  ml: 0,  mt: 22, mr: 0, mb: 22, vis: true },
                { k: "s",  al: 1, ar: 1, at: 0, ab: 1, w: 0,  hh: 7,  ml: 22, mt: 0,  mr: 22, mb: 0, vis: !root.isCollapsed },
                { k: "w",  al: 1, ar: 0, at: 1, ab: 1, w: 7,  hh: 0,  ml: 0,  mt: 22, mr: 0, mb: 22, vis: true }
            ]

            Item {
                id: handle
                required property var modelData

                visible: modelData.vis
                z: 1000

                // w = 0 / hh = 0 mean "the whole side": the two
                // opposite sides are already anchored, the height
                // follows on its own.
                width:  modelData.w  > 0 ? modelData.w  : parent.width  - modelData.ml - modelData.mr
                height: modelData.hh > 0 ? modelData.hh : parent.height - modelData.mt - modelData.mb

                anchors.left:   modelData.al ? parent.left   : undefined
                anchors.right:  modelData.ar ? parent.right  : undefined
                anchors.top:    modelData.at ? parent.top    : undefined
                anchors.bottom: modelData.ab ? parent.bottom : undefined

                anchors.leftMargin:   modelData.ml
                anchors.rightMargin:  modelData.mr
                anchors.topMargin:    modelData.mt
                anchors.bottomMargin: modelData.mb

                MouseArea {
                    id: handleMouse
                    anchors.fill: parent
                    hoverEnabled: true

                    cursorShape: {
                        var k = handle.modelData.k;
                        if (k === "se") return Qt.SizeFDiagCursor;
                        if (k === "sw" || k === "ne") return Qt.SizeBDiagCursor;
                        if (k === "e" || k === "w") return Qt.SizeHorCursor;
                        return Qt.SizeVerCursor;
                    }

                    onPressed:  (mouse) => root.startResize(this, mouse, handle.modelData.k)
                    onPositionChanged: (mouse) => root.updateResize(this, mouse, handle.modelData.k)
                    onReleased: root.finishResize(handle.modelData.k)
                }

                // A 1px rule that appears only under the pointer: it
                // says "you resize here" without always drawing the
                // arrow.
                Rectangle {
                    visible: handleMouse.containsMouse
                             || (root.isResizing && handleMouse.pressed)
                    color: Theme.accent

                    anchors.left:   handle.modelData.al ? parent.left   : undefined
                    anchors.right:  handle.modelData.ar ? parent.right  : undefined
                    anchors.top:    handle.modelData.at ? parent.top    : undefined
                    anchors.bottom: handle.modelData.ab ? parent.bottom : undefined

                    width:  handle.modelData.w  > 0 ? 1 : undefined
                    height: handle.modelData.hh > 0 ? 1 : undefined
                }
            }
        }
    }

    // ═══════════════════════════════════════════════════════════
    //  Actions
    // ═══════════════════════════════════════════════════════════
    function toggleCollapsed() {
        root.isCollapsed = !root.isCollapsed;
        root.saveState();
        if (root.appletRoot && root.appletRoot.syncContainerSize) {
            root.appletRoot.syncContainerSize(undefined, undefined, true);
        }
    }
}
