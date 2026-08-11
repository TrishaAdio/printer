import QtQuick
import QtQuick.Layouts
import Glass

/* Single line text entry, with optional inline validation styling. */
FieldRow {
    id: root

    stretch: true

    property string text: ""
    property string placeholder: ""
    property bool invalid: false
    property bool monospace: false

    signal edited(string text)
    signal accepted(string text)

    Item {
        Layout.fillWidth: true
        Layout.preferredHeight: Theme.controlHeight

        GlassCard {
            anchors.fill: parent
            radius: Theme.radiusSm
            interactive: root.fieldEnabled
            hovered: hoverArea.containsMouse || input.activeFocus
            elevation: 0.5
            sweepOnHover: false
            selected: input.activeFocus && !root.invalid
            border: root.invalid
                    ? Qt.rgba(Theme.bad.r, Theme.bad.g, Theme.bad.b, 0.65)
                    : Theme.stroke
        }

        MouseArea {
            id: hoverArea
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.NoButton
        }

        TextInput {
            id: input
            anchors.fill: parent
            anchors.leftMargin: Theme.gap(1.25)
            anchors.rightMargin: Theme.gap(1.25)
            enabled: root.fieldEnabled
            text: root.text
            color: root.invalid ? Theme.bad : Theme.text
            font.family: root.monospace ? Theme.monoFamily : Theme.fontFamily
            font.pixelSize: Theme.fsBody
            verticalAlignment: TextInput.AlignVCenter
            selectByMouse: true
            clip: true
            selectionColor: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.45)

            onTextEdited: {
                root.text = text
                root.edited(text)
            }
            onAccepted: root.accepted(text)

            Connections {
                target: root
                function onTextChanged() {
                    if (!input.activeFocus && input.text !== root.text)
                        input.text = root.text
                }
            }
        }

        Text {
            anchors.left: parent.left
            anchors.leftMargin: Theme.gap(1.25)
            anchors.verticalCenter: parent.verticalCenter
            visible: input.text === ""
            text: root.placeholder
            color: Theme.textFaint
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fsBody
        }
    }
}
