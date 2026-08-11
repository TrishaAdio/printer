import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Glass

/*
 * Everything printed before, searchable, with one click to print it again using
 * the settings it was printed with the first time. That last part is the whole
 * reason this screen exists.
 */
Item {
    id: root

    property var backend: null
    property string search: ""
    property string filter: "all"

    function reload() {
        if (backend)
            backend.refreshHistory(root.search, root.filter)
    }

    Component.onCompleted: reload()

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.gap(1.5)

        GlassCard {
            Layout.fillWidth: true
            Layout.preferredHeight: 62
            radius: Theme.radiusLg
            elevation: 0.6
            sweepOnHover: false

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.gap(2)
                anchors.rightMargin: Theme.gap(1.5)
                spacing: Theme.gap(1.5)

                Item {
                    Layout.preferredWidth: 220
                    Layout.preferredHeight: Theme.controlHeight

                    GlassCard {
                        anchors.fill: parent
                        radius: Theme.radiusSm
                        elevation: 0.4
                        sweepOnHover: false
                        hovered: searchInput.activeFocus
                        selected: searchInput.activeFocus
                    }

                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: Theme.gap(1.25)
                        anchors.verticalCenter: parent.verticalCenter
                        text: Theme.icon.view
                        font.family: Theme.iconFamily
                        font.pixelSize: Theme.fsSmall
                        color: Theme.textFaint
                    }

                    TextInput {
                        id: searchInput
                        anchors.fill: parent
                        anchors.leftMargin: Theme.gap(4)
                        anchors.rightMargin: Theme.gap(1.25)
                        verticalAlignment: TextInput.AlignVCenter
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsBody
                        selectByMouse: true
                        selectionColor: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.45)
                        onTextEdited: {
                            root.search = text
                            debounce.restart()
                        }
                    }

                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: Theme.gap(4)
                        anchors.verticalCenter: parent.verticalCenter
                        visible: searchInput.text === ""
                        text: "Search by name or printer"
                        color: Theme.textFaint
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsBody
                    }

                    Timer {
                        id: debounce
                        interval: 220
                        onTriggered: root.reload()
                    }
                }

                SegmentedControl {
                    options: [
                        { text: "All", value: "all" },
                        { text: "Printed", value: "done" },
                        { text: "Failed", value: "failed" }
                    ]
                    value: root.filter
                    onPicked: function (v) {
                        root.filter = v
                        root.reload()
                    }
                }

                Item { Layout.fillWidth: true }

                Text {
                    visible: root.backend !== null
                    text: {
                        const stats = root.backend ? root.backend.historyStats : ({})
                        const jobs = stats.jobs || 0
                        const sheets = stats.sheets || 0
                        if (!jobs)
                            return ""
                        return jobs + (jobs === 1 ? " job" : " jobs") + "  |  "
                               + sheets + (sheets === 1 ? " sheet" : " sheets") + " all time"
                    }
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fsTiny
                    color: Theme.textFaint
                }

                GlassButton {
                    text: "Clear history"
                    danger: true
                    glyph: Theme.icon.delete
                    onClicked: clearConfirm.open()
                }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: list
                anchors.fill: parent
                model: root.backend ? root.backend.history : null
                spacing: Theme.gap(0.75)
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                visible: count > 0

                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                    contentItem: Rectangle {
                        implicitWidth: 4
                        radius: 2
                        color: Qt.rgba(1, 1, 1, 0.20)
                    }
                    background: Item {}
                }

                delegate: HistoryRow {
                    required property var row

                    width: list.width - Theme.gap(1)
                    entryId: row.id
                    name: row.name
                    printer: row.printer
                    status: row.status
                    whenText: row.whenText
                    detail: row.detail
                    kind: row.kind

                    onReprintRequested: root.backend.reprint(row.id)
                    onRemoveRequested: root.backend.deleteHistory(row.id)
                    onRevealRequested: root.backend.openPath(row.path)
                }
            }

            EmptyState {
                anchors.fill: parent
                visible: list.count === 0
                glyph: Theme.icon.history
                title: root.search !== "" ? "Nothing matches that" : "No history yet"
                body: root.search !== ""
                      ? "Try a shorter search, or switch the filter back to All."
                      : "Once you print something it appears here, and one click puts it "
                        + "back on the printer with the same settings."
            }
        }
    }

    Modal {
        id: clearConfirm
        title: "Clear the print history?"
        message: "Every past job is forgotten, including the settings they used. "
                 + "Nothing currently queued is affected."
        acceptText: "Clear it"
        glyph: Theme.icon.delete
        tone: Theme.bad
        onAccepted: {
            root.backend.clearHistory()
            root.reload()
        }
    }
}
