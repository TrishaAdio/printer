import QtQuick
import QtQuick.Layouts
import Glass

/* Continuous value with a live readout, used for volume and blur strength. */
FieldRow {
    id: root

    stretch: true

    property real value: 0.5
    property real minimum: 0.0
    property real maximum: 1.0
    property int decimals: 0
    property string display: ""      // override the readout text
    property bool percent: true

    signal moved(real value)
    signal released()

    readonly property real fraction: (value - minimum) / Math.max(0.0001, maximum - minimum)

    function setFromX(x) {
        const usable = Math.max(1, track.width)
        const clamped = Math.max(0, Math.min(1, x / usable))
        const next = root.minimum + clamped * (root.maximum - root.minimum)
        root.value = next
        root.moved(next)
    }

    Item {
        Layout.fillWidth: true
        Layout.preferredHeight: Theme.controlHeight

        Item {
            id: track
            anchors.left: parent.left
            anchors.right: readout.left
            anchors.rightMargin: Theme.gap(1.5)
            anchors.verticalCenter: parent.verticalCenter
            height: 20

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width
                height: 5
                radius: 2.5
                color: Theme.glassSunken
                border.width: Theme.hairline
                border.color: Theme.stroke
            }

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: Math.max(5, parent.width * root.fraction)
                height: 5
                radius: 2.5
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Theme.accent }
                    GradientStop { position: 1.0; color: Theme.accent2 }
                }
            }

            Rectangle {
                id: handle
                width: area.pressed ? 16 : 14
                height: width
                radius: width / 2
                x: Math.max(0, Math.min(track.width - width, track.width * root.fraction - width / 2))
                anchors.verticalCenter: parent.verticalCenter
                color: "#FFFFFF"
                border.width: 2
                border.color: Theme.accent

                Behavior on width {
                    NumberAnimation { duration: Theme.ms(Theme.fast) }
                }
            }

            MouseArea {
                id: area
                anchors.fill: parent
                anchors.margins: -Theme.gap(1)
                enabled: root.fieldEnabled
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onPressed: function (mouse) { root.setFromX(mouse.x + Theme.gap(1)) }
                onPositionChanged: function (mouse) {
                    if (pressed)
                        root.setFromX(mouse.x + Theme.gap(1))
                }
                onReleased: {
                    Sfx.play("click")
                    root.released()
                }
            }
        }

        Text {
            id: readout
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: 46
            horizontalAlignment: Text.AlignRight
            text: root.display !== ""
                  ? root.display
                  : (root.percent ? Math.round(root.fraction * 100) + "%"
                                  : root.value.toFixed(root.decimals))
            color: Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fsSmall
        }
    }
}
