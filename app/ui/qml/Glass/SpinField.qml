import QtQuick
import QtQuick.Layouts
import Glass

/*
 * Numeric field with steppers. Editing is validated on the way out rather than
 * per keystroke, so typing "12" in a field that clamps to 1..99 does not fight
 * you after the first character.
 */
FieldRow {
    id: root

    stretch: true

    property int value: 1
    property int minimum: 1
    property int maximum: 999
    property int step: 1
    property string suffix: ""

    signal edited(int value)

    function commit(candidate) {
        const clamped = Math.max(root.minimum, Math.min(root.maximum, candidate))
        if (clamped !== root.value) {
            root.value = clamped
            root.edited(clamped)
        }
        input.text = String(root.value)
    }

    Item {
        Layout.fillWidth: true
        Layout.preferredHeight: Theme.controlHeight

        GlassCard {
            anchors.fill: parent
            radius: Theme.radiusSm
            interactive: root.fieldEnabled
            hovered: area.containsMouse || input.activeFocus
            elevation: 0.5
            sweepOnHover: false
            selected: input.activeFocus
        }

        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.NoButton
            onWheel: function (wheel) {
                if (!root.fieldEnabled)
                    return
                root.commit(root.value + (wheel.angleDelta.y > 0 ? root.step : -root.step))
            }
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Theme.gap(1.25)
            anchors.rightMargin: Theme.gap(0.5)
            spacing: 0

            TextInput {
                id: input
                Layout.fillWidth: true
                enabled: root.fieldEnabled
                text: String(root.value)
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fsBody
                verticalAlignment: TextInput.AlignVCenter
                selectByMouse: true
                selectionColor: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.45)
                validator: IntValidator { bottom: root.minimum; top: root.maximum }
                onEditingFinished: root.commit(parseInt(text) || root.minimum)
                onActiveFocusChanged: if (!activeFocus) root.commit(parseInt(text) || root.minimum)
                Keys.onUpPressed: root.commit(root.value + root.step)
                Keys.onDownPressed: root.commit(root.value - root.step)

                // Keep the field in step when the value is changed elsewhere,
                // but never while the user is mid-edit.
                Connections {
                    target: root
                    function onValueChanged() {
                        if (!input.activeFocus)
                            input.text = String(root.value)
                    }
                }
            }

            Text {
                visible: root.suffix !== ""
                text: root.suffix
                color: Theme.textFaint
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fsSmall
                rightPadding: Theme.gap(0.75)
            }

            ColumnLayout {
                Layout.preferredWidth: 20
                Layout.fillHeight: true
                spacing: 0

                Repeater {
                    model: [
                        { glyph: Theme.icon.up, delta: 1 },
                        { glyph: Theme.icon.down, delta: -1 }
                    ]
                    Item {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: 1
                            radius: 3
                            color: stepArea.containsMouse
                                   ? Qt.rgba(1, 1, 1, 0.10) : "transparent"
                        }
                        Text {
                            anchors.centerIn: parent
                            text: modelData.glyph
                            font.family: Theme.iconFamily
                            font.pixelSize: 8
                            color: stepArea.containsMouse ? Theme.text : Theme.textFaint
                        }
                        MouseArea {
                            id: stepArea
                            anchors.fill: parent
                            hoverEnabled: true
                            enabled: root.fieldEnabled
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                Sfx.play("hover")
                                root.commit(root.value + root.step * modelData.delta)
                            }
                            onPressAndHold: repeat.start()
                            onReleased: repeat.stop()
                            onExited: repeat.stop()
                            Timer {
                                id: repeat
                                interval: 70
                                repeat: true
                                onTriggered: root.commit(root.value + root.step * modelData.delta)
                            }
                        }
                    }
                }
            }
        }
    }
}
