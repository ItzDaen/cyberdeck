// finestra-prova.qml — verification window that closes itself.
//
// Opened from here rather than left on the user's screen as a dialog to
// dismiss on every run: the window stays for 9 seconds and then tears
// itself down. The position and the size are fixed, so the crop out of
// the screenshot is deterministic and does not have to be hunted for by
// eye.
//
// Draws nothing: its only purpose is to give a decorated window to look
// at.
//
// Usage:  qml finestra-prova.qml
import QtQuick
import QtQuick.Window

Window {
    // Absolute coordinates on the main monitor (1920x1080). The window
    // is deliberately wide: with a narrow one the side regions of the
    // nine-slice do not stretch and the seams do not show, and the seams
    // are the actual defect of the decoration.
    x: 500
    y: 300
    width: 900
    height: 480
    visible: true
    title: "Meridiano"
    // Solid magenta: a colour that exists nowhere else on the desktop.
    // It is what makes the screenshot crop automatic and error-free:
    // with "normal" colours the crop also caught the terminal's
    // background and it was not clear which window was being looked at.
    color: "#ff00ff"

    Timer {
        interval: 9000
        running: true
        onTriggered: Qt.quit()
    }
}
