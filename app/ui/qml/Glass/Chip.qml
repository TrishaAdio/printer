import QtQuick
import QtQuick.Layouts
import Glass

/* A small labelled pill. Used for status, counts and metadata. */
Item {
    id: root

    property string text: ""
    property string glyph: ""
    property color tone: Theme.textDim
    property bool filled: false
    property bool showDot: false

    implicitHeight: 24
    implicitWidth: row.implicitWidth + Theme.gap(1.75)

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: root.filled ? Qt.rgba(root.tone.r, root.tone.g, root.tone.b, 0.18)
                           : Theme.glassSunken
        border.width: Theme.hairline
        border.color: root.filled
                      ? Qt.rgba(root.tone.r, root.tone.g, root.tone.b, 0.42)
                      : Theme.stroke
    }

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: Theme.gap(0.625)

        StatusDot {
            visible: root.showDot
            tone: root.tone
            Layout.alignment: Qt.AlignVCenter
        }

        Text {
            visible: root.glyph !== ""
            text: root.glyph
            font.family: Theme.iconFamily
            font.pixelSize: Theme.fsTiny
            color: root.tone
        }

        Text {
            text: root.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fsTiny
            font.weight: Font.Medium
            color: root.filled ? root.tone : Theme.textDim
        }
    }
}
