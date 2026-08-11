import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Glass

/*
 * The queue, with the controls a large batch actually needs: pause between jobs,
 * cancel everything, retry the ones that failed, and clear the finished rows out
 * of the way. Reordering is per row, in JobRow.
 */
Item {
    id: root

    property var backend: null
    property string selectedId: ""

    signal jobSelected(string jobId, string path, string name)

    readonly property var counts: backend ? backend.counts : ({})

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.gap(1.5)

        // ------------------------------------------------------------ toolbar
        GlassCard {
            Layout.fillWidth: true
            Layout.preferredHeight: 60
            radius: Theme.radiusLg
            elevation: 0.6
            sweepOnHover: false

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.gap(2)
                anchors.rightMargin: Theme.gap(1.5)
                spacing: Theme.gap(1.25)

                ColumnLayout {
                    spacing: 2
                    Layout.fillWidth: true

                    Text {
                        text: {
                            const total = root.counts.total || 0
                            if (!total)
                                return "Queue is empty"
                            return total + (total === 1 ? " job" : " jobs")
                        }
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsHeading
                        font.weight: Font.DemiBold
                        color: Theme.text
                    }
                    Text {
                        text: root.backend ? root.backend.queueSummary : ""
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsTiny
                        color: Theme.textFaint
                    }
                }

                GlassButton {
                    text: root.backend && root.backend.paused ? "Resume" : "Pause"
                    glyph: root.backend && root.backend.paused ? Theme.icon.play : Theme.icon.pause
                    enabled: (root.counts.pending || 0) > 0 || (root.counts.running || 0) > 0
                    onClicked: root.backend.togglePause()
                }

                GlassButton {
                    text: "Retry failed"
                    glyph: Theme.icon.refresh
                    visible: (root.counts.failed || 0) > 0
                    onClicked: root.backend.retryFailed()
                }

                GlassButton {
                    text: "Clear finished"
                    subtle: true
                    visible: (root.counts.done || 0) + (root.counts.failed || 0)
                             + (root.counts.cancelled || 0) > 0
                    onClicked: root.backend.clearFinished()
                }

                GlassButton {
                    text: "Cancel all"
                    danger: true
                    glyph: Theme.icon.stop
                    enabled: (root.counts.pending || 0) > 0 || (root.counts.running || 0) > 0
                    onClicked: cancelConfirm.open()
                }
            }
        }

        // ------------------------------------------------------------ progress
        GlassCard {
            Layout.fillWidth: true
            Layout.preferredHeight: 62
            radius: Theme.radiusLg
            elevation: 0.6
            sweepOnHover: false
            visible: (root.counts.total || 0) > 0

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.gap(1.75)
                spacing: Theme.gap(1)

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: root.backend ? root.backend.progressText : ""
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsSmall
                        color: Theme.textDim
                    }
                    Text {
                        text: root.backend
                              ? Math.round(root.backend.overall * 100) + "%" : "0%"
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsSmall
                        font.weight: Font.DemiBold
                        color: Theme.text
                    }
                }

                ProgressTrack {
                    Layout.fillWidth: true
                    thickness: 7
                    value: root.backend ? root.backend.overall : 0
                    active: root.backend ? root.backend.running : false
                }
            }
        }

        // ---------------------------------------------------------------- list
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: list
                anchors.fill: parent
                model: root.backend ? root.backend.queue : null
                spacing: Theme.gap(0.75)
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                cacheBuffer: 400
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

                // Rows fade and slide in, staggered by nothing more than their own
                // arrival, which keeps a large batch from flashing all at once.
                add: Transition {
                    ParallelAnimation {
                        NumberAnimation {
                            property: "opacity"; from: 0; to: 1
                            duration: Theme.ms(Theme.normal)
                        }
                        NumberAnimation {
                            property: "y"; from: 12
                            duration: Theme.ms(Theme.slow); easing.type: Theme.easeOut
                        }
                    }
                }
                displaced: Transition {
                    NumberAnimation {
                        properties: "y"
                        duration: Theme.ms(Theme.normal)
                        easing.type: Theme.easeOut
                    }
                }
                remove: Transition {
                    NumberAnimation {
                        property: "opacity"; to: 0; duration: Theme.ms(Theme.fast)
                    }
                }

                delegate: JobRow {
                    // One `row` role rather than a required property per field:
                    // redeclaring `name`, `status` and friends here would shadow
                    // JobRow's own properties of the same name.
                    required property var row

                    width: list.width - Theme.gap(1)
                    jobId: row.id
                    name: row.name
                    kind: row.kind
                    status: row.status
                    statusLabel: row.statusLabel
                    detail: row.detail
                    progress: row.progress
                    pages: row.pages
                    sheets: row.sheets
                    sizeText: row.size_text
                    selected: root.selectedId === row.id

                    onActivated: {
                        root.selectedId = row.id
                        root.jobSelected(row.id, row.path, row.name)
                    }
                    onCancelRequested: root.backend.cancelJob(row.id)
                    onRetryRequested: root.backend.retryJob(row.id)
                    onRemoveRequested: root.backend.removeJob(row.id)
                    onMoveRequested: function (delta) { root.backend.moveJob(row.id, delta) }
                    onRevealRequested: root.backend.openPath(row.path)
                }
            }

            EmptyState {
                anchors.fill: parent
                visible: list.count === 0
                glyph: Theme.icon.queue
                title: "Nothing queued"
                body: "Drop files on the Print tab and they will line up here, "
                      + "one job at a time, in order."
            }
        }
    }

    Modal {
        id: cancelConfirm
        title: "Cancel the whole queue?"
        message: "Everything still waiting will be cancelled, and the job on the "
                 + "printer now will be stopped. Sheets already printed stay printed."
        acceptText: "Cancel everything"
        rejectText: "Keep printing"
        glyph: Theme.icon.warning
        tone: Theme.bad
        onAccepted: root.backend.cancelAll()
    }
}
