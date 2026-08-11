import QtQuick
import QtQuick.Layouts
import Glass

/* One past job. The point of this list is reprinting, so that action is primary. */
Item {
    id: root

    property string entryId: ""
    property string name: ""
    property string printer: ""
    property string status: ""
    property string whenText: ""
    property string detail: ""
    property string kind: ""

    signal reprintRequested()
    signal removeRequested()
    signal revealRequested()

    readonly property color tone: Theme.jobColor(status)

    implicitHeight: 56

    GlassCard {
        anchors.fill: parent
        radius: Theme.radiusMd
        interactive: true
        hovered: area.containsMouse
        elevation: 0.4
        sweepOnHover: false
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.gap(1.5)
        anchors.rightMargin: Theme.gap(1.25)
        spacing: Theme.gap(1.25)

        StatusDot {
            tone: root.tone
            size: 7
            Layout.alignment: Qt.AlignVCenter
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            Text {
                Layout.fillWidth: true
                text: root.name
                elide: Text.ElideMiddle
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fsBody
                color: Theme.text
            }

            Text {
                Layout.fillWidth: true
                text: root.detail
                elide: Text.ElideRight
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fsTiny
                color: root.status === "failed" ? Theme.bad : Theme.textFaint
            }
        }

        ColumnLayout {
            spacing: 2
            Layout.alignment: Qt.AlignVCenter

            Text {
                Layout.alignment: Qt.AlignRight
                text: root.whenText
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fsTiny
                color: Theme.textDim
            }
            Text {
                Layout.alignment: Qt.AlignRight
                text: Theme.elide(root.printer, 26)
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fsTiny
                color: Theme.textFaint
            }
        }

        RowLayout {
            spacing: 2
            opacity: area.containsMouse ? 1 : 0.0
            visible: opacity > 0.01
            Behavior on opacity {
                NumberAnimation { duration: Theme.ms(Theme.fast) }
            }

            IconButton {
                glyph: Theme.icon.openFolder
                tip: "Show in Explorer"
                flat: true
                size: 26
                glyphSize: 10
                onClicked: root.revealRequested()
            }
            IconButton {
                glyph: Theme.icon.delete
                tip: "Forget this entry"
                flat: true
                danger: true
                size: 26
                glyphSize: 10
                onClicked: root.removeRequested()
            }
        }

        GlassButton {
            text: "Print again"
            glyph: Theme.icon.refresh
            horizontalPadding: Theme.gap(1.25)
            onClicked: root.reprintRequested()
        }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
        z: -1
    }
}
