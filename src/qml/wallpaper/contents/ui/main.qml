pragma ComponentBehavior: Bound

// ==============================================================================
// main.qml — CyberDeck Wallpaper
// Author: Daen
// Platform: CachyOS Linux | KDE Plasma 6 (Wayland)
//
// What changed with respect to the v1.0 "Code Reign":
//   - CyberMatrixBackground.qml (GLSL shader, code rain, 60-144 FPS)
//   - the 4 overlapping vignette gradients
//   - the branding block "[ CYBER MATRIX // CODE REIGN - GPU ENGINE v1.0 ]"
//   - the Process that spied on the file ~/.cache/cyberhud_perf_mode
//   - the PerformanceMode entry from the configuration schema
//
// What is in their place: InstrumentField (surface + grain + vignette,
// zero shaders). The audio spectrum is the only animated element, and it
// moves little: it is an instrument, not a show.
// ==============================================================================
import QtQuick
import org.kde.plasma.plasmoid

WallpaperItem {
    id: root
    anchors.fill: parent

    // ── Configuration ─────────────────────────────────────────────
    readonly property bool showHud: (root.configuration && root.configuration.ShowHud !== undefined)
        ? (root.configuration.ShowHud === true || root.configuration.ShowHud === "true") : false
    readonly property string hudPos: (root.configuration && root.configuration.HudPosition)
        ? root.configuration.HudPosition : "top-right"
    readonly property int cfgWidth: (root.configuration && parseInt(root.configuration.HudWidth) > 0)
        ? parseInt(root.configuration.HudWidth) : 460
    readonly property int cfgHeight: (root.configuration && parseInt(root.configuration.HudHeight) > 0)
        ? parseInt(root.configuration.HudHeight) : 392
    readonly property int hudCustomX: (root.configuration && root.configuration.HudCustomX !== undefined)
        ? parseInt(root.configuration.HudCustomX) : 0
    readonly property int hudCustomY: (root.configuration && root.configuration.HudCustomY !== undefined)
        ? parseInt(root.configuration.HudCustomY) : 0

    // Offset of the spectrum from the bottom edge. It has to clear the
    // height of the Plasma panel, otherwise the axis's base and ticks
    // end up underneath.
    //
    // It is not computable from the wallpaper: the panel is a
    // "floating" containment with no ItemGeometries key, so its height
    // cannot be read from the configuration. That is why it is a
    // literal value and not a discovery.
    //
    // Kept although nothing reads it now that the analyser has moved to
    // the widget, so that a configuration written by an older version
    // still loads. The key is ignored, not the file: removing the
    // property would make an existing setting a load-time error.
    readonly property int spectrumInset: (root.configuration
        && parseInt(root.configuration.SpectrumBottomInset) >= 0)
        ? parseInt(root.configuration.SpectrumBottomInset) : 56

    // Yielding to something else that animates.
    //
    // This is not the v1.0 performance mode. That one existed to switch
    // off our own Matrix rain shader, which is gone, so it had nothing
    // left to suppress. This one is the opposite: our animation is cheap
    // (~2% of a core, GPU busy 1-3%) and somebody else's is not, so when
    // the desktop runs an animated wallpaper on another screen we stop
    // the spectrum and give the room over.
    //
    // The state arrives as a configuration key rather than through a
    // watched file on purpose. Plasma pushes a configuration change into
    // the plugin by itself, so this is reactive with no polling and no
    // filesystem access from QML. The published signal for third-party
    // wallpapers is a file, and that is a separate contract: see
    // docs/CONTRATTO-resa.md.
    readonly property bool performanceMode: (root.configuration
        && root.configuration.PerformanceMode !== undefined)
        ? (root.configuration.PerformanceMode === true
           || root.configuration.PerformanceMode === "true") : false

    // Edge margin: it adapts to the resolution instead of being the
    // old fixed 24px, which on 768p was 3% and on 4K 1%. The
    // proportion is what keeps the visual frame constant.
    readonly property int margin: Math.round(Math.min(root.width, root.height) * 0.022)
    readonly property int hudMargin: margin

    // ── HUD positioning ────────────────────────────────────
    // Computed on this screen's REAL geometry. Every monitor has its
    // own instance of the wallpaper, so every monitor works out the
    // right position on its own: no containment ID to remember.
    readonly property int hudX: {
        if (hudPos === "custom")   return Math.max(0, Math.min(root.width  - cfgWidth,  hudCustomX));
        if (hudPos === "top-left" || hudPos === "bottom-left") return hudMargin;
        if (hudPos === "center" || hudPos === "top-center")
            return Math.max(0, Math.round((root.width - cfgWidth) / 2));
        return Math.max(0, root.width - cfgWidth - hudMargin);   // top-right / bottom-right
    }

    readonly property int hudY: {
        if (hudPos === "custom") return Math.max(0, Math.min(root.height - cfgHeight, hudCustomY));
        if (hudPos === "bottom-right" || hudPos === "bottom-left")
            return Math.max(0, root.height - cfgHeight - hudMargin);
        if (hudPos === "center")
            return Math.max(0, Math.round((root.height - cfgHeight) / 2));
        return hudMargin;                                       // top-left / top-center / top-right
    }

    // ── 1. The background ────────────────────────────────────────
    InstrumentField {
        anchors.fill: parent
    }

    // ── 2. Telemetry HUD over the background ──────────────
    // Loaded only if requested: two TelemetryHUD instances on two
    // monitors would quadruple the system probes for nothing.
    Loader {
        id: telemetryHudLoader
        active: root.showHud
        visible: root.showHud
        x: root.hudX
        y: root.hudY
        sourceComponent: Component {
            TelemetryHUD {
                customWidth: root.cfgWidth
                customHeight: root.cfgHeight
            }
        }
    }

    // ── 3. Audio analyser ──────────────────────────────────────
    //
    // Not here any more. It was, anchored to the bottom of this item,
    // which meant the analyser existed only while this wallpaper was the
    // one on that screen: put a video on it and the spectrum went with it,
    // because a wallpaper replaces rather than layers.
    //
    // It is `cyberdeck.spectrum`, a desktop widget, and a widget layers
    // over whatever the wallpaper is. Two of them on one screen is the
    // other half of the same mistake — this copy and the widget's, both
    // drawing, so the spectrum appeared twice.
    //
    // The widget reads ~/.cache/cyberdeck/yield itself, the file the
    // contract publishes, so it honours a yield without this wallpaper
    // having to translate one into the other.
}
