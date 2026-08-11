import QtQuick
import QtQuick.Layouts
import Glass

/* Shown wherever a list has nothing in it yet. */
Item {
    id: root

    property string glyph: Theme.icon.info
    property string title: ""
    property string body: ""
    property string actionText: ""

    signal actionTriggered()

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width - Theme.gap(6), 340)
        spacing: Theme.gap(1.25)

        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            width: 46
            height: 46
            radius: Theme.radiusMd
            color: Theme.glassSunken
            border.width: Theme.hairline
            border.color: Theme.stroke
            Text {
                anchors.centerIn: parent
                text: root.glyph
                font.family: Theme.iconFamily
                font.pixelSize: Theme.fsTitle
                color: Theme.textFaint
            }
        }

        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: root.title
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fsHeading
            font.weight: Font.DemiBold
            color: Theme.textDim
        }

        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            visible: root.body !== ""
            text: root.body
            wrapMode: Text.WordWrap
            lineHeight: 1.35
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fsSmall
            color: Theme.textFaint
        }

        GlassButton {
            Layout.alignment: Qt.AlignHCenter
            visible: root.actionText !== ""
            text: root.actionText
            onClicked: root.actionTriggered()
        }
    }
}
