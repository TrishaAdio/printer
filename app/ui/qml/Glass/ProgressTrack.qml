import QtQuick
import Glass

/*
 * Progress bar with a travelling shimmer.
 *
 * The shimmer only runs while the value is actually advancing, so a stalled job
 * looks stalled instead of looking busy. Indeterminate mode is a separate,
 * obviously different animation for when there is nothing to measure yet.
 */
Item {
    id: root

    property real value: 0.0            // 0..1
    property bool indeterminate: false
    property bool active: false         // drives the shimmer
    property int thickness: 6
    property color tone: Theme.accent
    property color tone2: Theme.accent2
    property bool rounded: true

    implicitHeight: thickness

    Rectangle {
        anchors.fill: parent
        radius: root.rounded ? height / 2 : 0
        color: Theme.glassSunken
        border.width: Theme.hairline
        border.color: Theme.stroke
    }

    Item {
        anchors.fill: parent
        clip: true

        Rectangle {
            id: fill
            height: parent.height
            radius: root.rounded ? height / 2 : 0
            width: root.indeterminate ? parent.width * 0.32
                                      : Math.max(0, Math.min(1, root.value)) * parent.width
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: root.tone }
                GradientStop { position: 1.0; color: root.tone2 }
            }

            Behavior on width {
                enabled: !root.indeterminate
                NumberAnimation { duration: Theme.ms(280); easing.type: Theme.easeOut }
            }

            SequentialAnimation on x {
                running: root.indeterminate && Theme.animationsOn
                loops: Animation.Infinite
                NumberAnimation {
                    from: -fill.width; to: root.width
                    duration: 1150; easing.type: Easing.InOutQuad
                }
            }
        }

        // Shimmer sweep across the filled portion.
        Rectangle {
            id: shimmer
            visible: root.active && !root.indeterminate
                     && Theme.animationsOn && !Theme.reduceMotion && fill.width > 12
            width: 68
            height: parent.height
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.38) }
                GradientStop { position: 1.0; color: "transparent" }
            }
            SequentialAnimation on x {
                running: shimmer.visible
                loops: Animation.Infinite
                NumberAnimation {
                    from: -shimmer.width; to: Math.max(shimmer.width, fill.width)
                    duration: 1400; easing.type: Easing.InOutSine
                }
                PauseAnimation { duration: 320 }
            }
        }
    }
}
