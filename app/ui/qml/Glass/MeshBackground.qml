import QtQuick
import Glass

/*
 * The thing that makes glass look like glass.
 *
 * Translucent panels over a flat colour just look grey. They need something with
 * structure behind them to catch, so this drifts a handful of large soft colour
 * fields across the window. Panel edges pick the colour up as it passes, which is
 * what produces the shifting sheen.
 *
 * The softness is built from stacked low alpha discs rather than from a blur
 * shader. A `MultiEffect` blur was tried first and produced nothing at all when
 * rendered offscreen, and a background that silently disappears on some driver is
 * not worth the risk for an effect that geometry can express exactly. Alpha
 * accumulates across the rings, giving a smooth falloff with no shader, no
 * offscreen pass and no dependency on QtQuick.Effects.
 */
Item {
    id: root

    property real intensity: Theme.blurStrength
    property bool animate: Theme.animationsOn && !Theme.reduceMotion

    //: How many discs make up one field. Twelve still showed faint concentric
    //: banding in the larger fields, so twenty with correspondingly lower alpha.
    readonly property int rings: 20

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.dark ? "#0A0C14" : "#F4F6FC" }
            GradientStop { position: 0.55; color: Theme.dark ? "#0D1020" : "#EAEFFA" }
            GradientStop { position: 1.0; color: Theme.dark ? "#070910" : "#E4EAF6" }
        }
    }

    Item {
        anchors.fill: parent
        opacity: root.intensity * (Theme.dark ? 1.0 : 0.55)

        Repeater {
            model: [
                { c: Theme.accent,  s: 1.05, x0: 0.10, y0: 0.08, dx: 0.16, dy: 0.13, p: 27000 },
                { c: Theme.accent2, s: 1.25, x0: 0.74, y0: 0.04, dx: -0.19, dy: 0.20, p: 34000 },
                { c: "#2BD9C8",     s: 0.80, x0: 0.62, y0: 0.78, dx: -0.14, dy: -0.17, p: 41000 },
                { c: Theme.accent,  s: 0.68, x0: 0.16, y0: 0.86, dx: 0.22, dy: -0.12, p: 23000 }
            ]

            Item {
                id: field
                required property var modelData

                readonly property color fieldColor: modelData.c

                width: root.width * modelData.s
                height: width
                x: root.width * modelData.x0 - width / 2 + root.width * modelData.dx * phase
                y: root.height * modelData.y0 - height / 2 + root.height * modelData.dy * phase

                property real phase: 0
                SequentialAnimation on phase {
                    running: root.animate
                    loops: Animation.Infinite
                    NumberAnimation {
                        to: 1; duration: field.modelData.p; easing.type: Easing.InOutSine
                    }
                    NumberAnimation {
                        to: 0; duration: field.modelData.p; easing.type: Easing.InOutSine
                    }
                }

                Repeater {
                    model: root.rings

                    Rectangle {
                        required property int index

                        // Innermost ring last, so the centre accumulates the most.
                        readonly property real step: (index + 1) / root.rings

                        anchors.centerIn: parent
                        width: field.width * (1.0 - index / (root.rings + 1))
                        height: width
                        radius: width / 2
                        color: field.fieldColor
                        // Weighted so the outer rings are barely there and the
                        // build up is gradual rather than a visible cone.
                        opacity: 0.008 + 0.028 * Math.pow(step, 2.0)
                        antialiasing: true
                    }
                }
            }
        }
    }

    // A soft vignette so the corners settle and the centre stays the focus.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0.0; color: Qt.rgba(0, 0, 0, Theme.dark ? 0.20 : 0.0) }
            GradientStop { position: 0.45; color: "transparent" }
            GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, Theme.dark ? 0.32 : 0.05) }
        }
    }
}
