import QtQuick
import QtQuick.Layouts
import Glass

/* A switch. The knob travels with a slight overshoot, which reads as physical. */
FieldRow {
    id: root

    stretch: true

    property bool checked: false
    signal toggled(bool checked)

    function flip() {
        if (!root.fieldEnabled)
            return
        root.checked = !root.checked
        Sfx.play("click")
        root.toggled(root.checked)
    }

    Item {
        Layout.fillWidth: true
        Layout.preferredHeight: Theme.controlHeight

        Rectangle {
            id: track
            width: 42
            height: 22
            radius: height / 2
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            color: root.checked
                   ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.85)
                   : Theme.glassSunken
            border.width: Theme.hairline
            border.color: root.checked
                          ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.95)
                          : Theme.stroke

            Behavior on color {
                ColorAnimation { duration: Theme.ms(Theme.normal) }
            }

            Rectangle {
                id: knob
                width: 16
                height: 16
                radius: 8
                y: 3
                x: root.checked ? track.width - width - 3 : 3
                color: root.checked ? "#FFFFFF" : Theme.textDim
                scale: area.pressed ? 0.9 : 1.0

                Behavior on x {
                    NumberAnimation {
                        duration: Theme.ms(260)
                        easing.type: Theme.animationsOn && !Theme.reduceMotion
                                     ? Easing.OutBack : Easing.Linear
                        easing.overshoot: 1.6
                    }
                }
                Behavior on color {
                    ColorAnimation { duration: Theme.ms(Theme.normal) }
                }
                Behavior on scale {
                    NumberAnimation { duration: Theme.ms(Theme.fast) }
                }
            }
        }

        MouseArea {
            id: area
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: track.width + Theme.gap(1)
            height: parent.height
            hoverEnabled: true
            cursorShape: root.fieldEnabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onEntered: if (root.fieldEnabled) Sfx.play("hover")
            onClicked: root.flip()
        }
    }
}
