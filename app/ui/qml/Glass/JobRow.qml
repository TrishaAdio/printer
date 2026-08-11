import QtQuick
import QtQuick.Layouts
import Glass

/*
 * One row in the queue.
 *
 * Rows have to stay cheap: a batch can be several hundred, and every progress
 * tick repaints the running one. So there are no effects here beyond the shared
 * card, actions appear only on hover, and the progress bar exists only while the
 * row is actually printing.
 */
Item {
    id: root

    property string jobId: ""
    property string name: ""
    property string kind: ""
    property string status: "pending"
    property string statusLabel: ""
    property string detail: ""
    property string sizeText: ""
    property int pages: 0
    property int sheets: 0
    property real progress: 0
    property bool selected: false
    property bool compact: false

    signal activated()
    signal cancelRequested()
    signal retryRequested()
    signal removeRequested()
    signal moveRequested(int delta)
    signal revealRequested()

    readonly property color tone: Theme.jobColor(status)
    readonly property bool busy: status === "running"

    implicitHeight: compact ? 52 : 60

    GlassCard {
        anchors.fill: parent
        radius: Theme.radiusMd
        interactive: true
        hovered: area.containsMouse
        selected: root.selected
        elevation: 0.5
        sweepOnHover: false
        fill: root.busy
              ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.09)
              : Theme.glass
    }

    // Status stripe down the leading edge: readable at a glance while scrolling.
    Rectangle {
        x: 0
        y: Theme.gap(1)
        width: 3
        height: parent.height - Theme.gap(2)
        radius: 1.5
        color: root.tone
        opacity: root.status === "pending" ? 0.35 : 0.95
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.gap(1.75)
        anchors.rightMargin: Theme.gap(1.25)
        spacing: Theme.gap(1.25)

        // File type badge
        Rectangle {
            Layout.preferredWidth: 30
            Layout.preferredHeight: 30
            radius: Theme.radiusSm
            color: Theme.glassSunken
            border.width: Theme.hairline
            border.color: Theme.stroke

            Text {
                anchors.centerIn: parent
                text: root.kind === "image" ? Theme.icon.image
                      : root.kind === "pdf" ? Theme.icon.document
                      : root.kind === "text" ? Theme.icon.text
                      : Theme.icon.page
                font.family: Theme.iconFamily
                font.pixelSize: Theme.fsSmall
                color: Theme.textDim
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.gap(1)

                Text {
                    Layout.fillWidth: true
                    text: root.name
                    elide: Text.ElideMiddle
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fsBody
                    font.weight: root.busy ? Font.DemiBold : Font.Normal
                    color: Theme.text
                }

                Chip {
                    text: root.statusLabel
                    tone: root.tone
                    filled: root.status !== "pending"
                    showDot: root.busy
                    visible: !root.compact || !root.busy
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.gap(0.75)
                visible: !root.busy

                Text {
                    text: {
                        const bits = []
                        if (root.pages > 0)
                            bits.push(root.pages + (root.pages === 1 ? " page" : " pages"))
                        if (root.sheets > 0 && root.sheets !== root.pages)
                            bits.push(root.sheets + (root.sheets === 1 ? " sheet" : " sheets"))
                        if (root.sizeText)
                            bits.push(root.sizeText)
                        return bits.join("  |  ")
                    }
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fsTiny
                    color: Theme.textFaint
                }

                Text {
                    Layout.fillWidth: true
                    visible: root.detail !== ""
                    text: root.detail
                    elide: Text.ElideRight
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fsTiny
                    color: root.status === "failed" ? Theme.bad : Theme.textFaint
                }
            }

            // Only exists while printing, which keeps idle rows cheap.
            Loader {
                Layout.fillWidth: true
                Layout.topMargin: 3
                active: root.busy
                visible: active
                sourceComponent: Component {
                    ColumnLayout {
                        spacing: 2
                        ProgressTrack {
                            Layout.fillWidth: true
                            thickness: 4
                            value: root.progress
                            active: true
                            indeterminate: root.progress <= 0.001
                        }
                        Text {
                            text: root.detail !== "" ? root.detail : "Working"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fsTiny
                            color: Theme.textDim
                        }
                    }
                }
            }
        }

        // Actions: hidden until the row is hovered so the list stays quiet.
        RowLayout {
            spacing: 2
            opacity: area.containsMouse ? 1 : 0
            visible: opacity > 0.01

            Behavior on opacity {
                NumberAnimation { duration: Theme.ms(Theme.fast) }
            }

            IconButton {
                glyph: Theme.icon.up
                tip: "Move up"
                flat: true
                size: 26
                glyphSize: 9
                visible: root.status === "pending"
                onClicked: root.moveRequested(-1)
            }
            IconButton {
                glyph: Theme.icon.down
                tip: "Move down"
                flat: true
                size: 26
                glyphSize: 9
                visible: root.status === "pending"
                onClicked: root.moveRequested(1)
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
                glyph: Theme.icon.refresh
                tip: "Print again"
                flat: true
                size: 26
                glyphSize: 10
                visible: root.status === "done" || root.status === "failed"
                           || root.status === "cancelled"
                onClicked: root.retryRequested()
            }
            IconButton {
                glyph: Theme.icon.stop
                tip: "Cancel"
                flat: true
                danger: true
                size: 26
                glyphSize: 10
                visible: root.busy
                onClicked: root.cancelRequested()
            }
            IconButton {
                glyph: Theme.icon.close
                tip: "Remove from list"
                flat: true
                danger: true
                size: 26
                glyphSize: 9
                visible: !root.busy
                onClicked: root.removeRequested()
            }
        }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        z: -1
        onClicked: root.activated()
    }
}
