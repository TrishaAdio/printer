import QtQuick
import QtQuick.Layouts
import Glass

/* A small heading with a trailing hairline, for grouping options. */
Item {
    id: root

    property string text: ""
    property string glyph: ""
    property bool first: false

    Layout.fillWidth: true
    implicitHeight: Theme.gap(first ? 2.5 : 4)

    RowLayout {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.gap(0.5)
        spacing: Theme.gap(1)

        Text {
            visible: root.glyph !== ""
            text: root.glyph
            font.family: Theme.iconFamily
            font.pixelSize: Theme.fsSmall
            color: Theme.accent
        }

        Text {
            text: root.text.toUpperCase()
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fsTiny
            font.weight: Font.DemiBold
            font.letterSpacing: 1.1
            color: Theme.textFaint
        }

        Rectangle {
            Layout.fillWidth: true
            height: Theme.hairline
            color: Theme.stroke
        }
    }
}
