import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Kirigami.FormLayout {
    id: root

    property alias cfg_ShowHud: showHudCheck.checked
    property alias cfg_HudPosition: positionCombo.currentValue
    property alias cfg_HudCustomX: customXSpin.value
    property alias cfg_HudCustomY: customYSpin.value
    property alias cfg_HudWidth: widthSpin.value
    property alias cfg_HudHeight: heightSpin.value
    property alias cfg_SpectrumBottomInset: spectrumInsetSpin.value

    QQC2.CheckBox {
        id: showHudCheck
        Kirigami.FormData.label: "HUD:"
        text: "Show the telemetry panel on the background"
    }

    QQC2.ComboBox {
        id: positionCombo
        Kirigami.FormData.label: "HUD position:"
        textRole: "text"
        valueRole: "value"
        model: [
            { text: "Top Right", value: "top-right" },
            { text: "Top Left", value: "top-left" },
            { text: "Top Center", value: "top-center" },
            { text: "Bottom Right", value: "bottom-right" },
            { text: "Bottom Left", value: "bottom-left" },
            { text: "Centre", value: "center" },
            { text: "Custom (free coordinates)", value: "custom" }
        ]
    }

    QQC2.SpinBox {
        id: customXSpin
        Kirigami.FormData.label: "X coordinate (px):"
        from: 0
        to: 3840
        stepSize: 10
        visible: positionCombo.currentValue === "custom"
    }

    QQC2.SpinBox {
        id: customYSpin
        Kirigami.FormData.label: "Y coordinate (px):"
        from: 0
        to: 2160
        stepSize: 10
        visible: positionCombo.currentValue === "custom"
    }

    QQC2.SpinBox {
        id: widthSpin
        Kirigami.FormData.label: "HUD width (px):"
        from: 360
        to: 800
        stepSize: 10
    }

    QQC2.SpinBox {
        id: heightSpin
        Kirigami.FormData.label: "HUD height (px):"
        from: 260
        to: 750
        stepSize: 10
    }

    QQC2.SpinBox {
        id: spectrumInsetSpin
        Kirigami.FormData.label: "Audio spectrum — distance from the panel (px):"
        from: 0
        to: 200
        stepSize: 2
    }
}
