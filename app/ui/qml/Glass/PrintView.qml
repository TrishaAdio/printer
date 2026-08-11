import QtQuick
import QtQuick.Dialogs
import QtQuick.Layouts
import Glass

/*
 * The main screen: drop target and preview on the left, the full option set on
 * the right, and the one action the app exists for across the bottom.
 *
 * The compact queue strip under the drop zone is deliberate. Watching the first
 * few jobs go through is how a user gains confidence that a batch is doing what
 * they asked, and making them switch tabs to see it would undermine that.
 */
Item {
    id: root

    property var backend: null
    property string selectedPath: ""
    property string selectedName: ""

    signal openQueue()

    function previewJob(path, name) {
        root.selectedPath = path
        root.selectedName = name
        drop.previewUrl = ""
        drop.previewError = ""
        drop.previewName = name
        drop.previewBusy = true
        if (backend)
            backend.requestPreview(path)
    }

    Connections {
        target: root.backend
        function onSuggestPreview(path, name) {
            root.previewJob(path, name)
        }
        function onPreviewReady(path, url) {
            if (path !== root.selectedPath)
                return
            drop.previewBusy = false
            drop.previewError = ""
            drop.previewUrl = url
        }
        function onPreviewFailed(path, reason) {
            if (path !== root.selectedPath)
                return
            drop.previewBusy = false
            drop.previewUrl = ""
            drop.previewError = reason
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: Theme.gap(2)

        // ============================================================== left
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredWidth: 3
            spacing: Theme.gap(1.5)

            DropZone {
                id: drop
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 220

                onFilesDropped: function (urls) {
                    if (root.backend)
                        root.backend.addUrls(urls)
                }
                onBrowseFiles: fileDialog.open()
                onBrowseFolder: folderDialog.open()
            }

            // ------------------------------------------------- queue strip
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 172
                radius: Theme.radiusLg
                elevation: 0.7
                sweepOnHover: false
                visible: (root.backend ? (root.backend.counts.total || 0) : 0) > 0

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.gap(1.5)
                    spacing: Theme.gap(1)

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.gap(1)

                        Text {
                            text: "In the queue"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fsSmall
                            font.weight: Font.DemiBold
                            color: Theme.textDim
                        }

                        Chip {
                            text: String(root.backend ? (root.backend.counts.total || 0) : 0)
                            tone: Theme.accent
                            filled: true
                        }

                        Item { Layout.fillWidth: true }

                        GlassButton {
                            text: "See all"
                            subtle: true
                            onClicked: root.openQueue()
                        }
                    }

                    ListView {
                        id: strip
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        model: root.backend ? root.backend.queue : null
                        spacing: Theme.gap(0.5)
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds

                        delegate: JobRow {
                            required property var row

                            width: strip.width
                            compact: true
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
                            selected: root.selectedPath === row.path

                            onActivated: root.previewJob(row.path, row.name)
                            onCancelRequested: root.backend.cancelJob(row.id)
                            onRetryRequested: root.backend.retryJob(row.id)
                            onRemoveRequested: root.backend.removeJob(row.id)
                            onMoveRequested: function (delta) {
                                root.backend.moveJob(row.id, delta)
                            }
                            onRevealRequested: root.backend.openPath(row.path)
                        }
                    }
                }
            }

            // ----------------------------------------------- action bar
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: 78
                radius: Theme.radiusLg
                elevation: 1.0
                sweepOnHover: false

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.gap(2)
                    anchors.rightMargin: Theme.gap(2)
                    spacing: Theme.gap(1.5)

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3

                        Text {
                            text: root.backend ? root.backend.progressText : ""
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fsSmall
                            color: Theme.textDim
                        }

                        ProgressTrack {
                            Layout.fillWidth: true
                            Layout.maximumWidth: 320
                            thickness: 5
                            value: root.backend ? root.backend.overall : 0
                            active: root.backend ? root.backend.running : false
                            visible: (root.backend ? (root.backend.counts.total || 0) : 0) > 0
                        }
                    }

                    GlassButton {
                        visible: (root.backend ? (root.backend.counts.pending || 0) : 0) > 0
                                 || (root.backend ? root.backend.running : false)
                        text: root.backend && root.backend.paused ? "Resume" : "Pause"
                        glyph: root.backend && root.backend.paused
                               ? Theme.icon.play : Theme.icon.pause
                        onClicked: root.backend.togglePause()
                    }

                    GlassButton {
                        text: {
                            const pending = root.backend ? (root.backend.counts.pending || 0) : 0
                            if (!pending)
                                return "Print"
                            return "Print " + pending + (pending === 1 ? " file" : " files")
                        }
                        glyph: Theme.icon.print
                        primary: true
                        horizontalPadding: Theme.gap(3)
                        busy: root.backend ? root.backend.running : false
                        enabled: (root.backend ? (root.backend.counts.pending || 0) : 0) > 0
                        onClicked: {
                            const pending = root.backend.counts.pending || 0
                            const limit = root.backend.getSetting("confirm_over_pages") || 0
                            if (limit > 0 && pending >= limit)
                                bigBatch.open({ payload: pending,
                                                message: "That is " + pending
                                                         + " files in one go. Nothing stops you, "
                                                         + "but it is worth a look at the printer's "
                                                         + "paper tray first." })
                            else
                                root.backend.start()
                        }
                    }
                }
            }
        }

        // ============================================================= right
        GlassCard {
            Layout.preferredWidth: 2
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 320
            Layout.maximumWidth: 460
            radius: Theme.radiusXl
            elevation: 0.9
            sweepOnHover: false

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.gap(2)
                spacing: Theme.gap(1)

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.gap(1)

                    Text {
                        Layout.fillWidth: true
                        text: "Print options"
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsTitle
                        font.weight: Font.DemiBold
                        color: Theme.text
                    }

                    GlassButton {
                        text: "Apply to queue"
                        subtle: true
                        visible: (root.backend ? (root.backend.counts.pending || 0) : 0) > 0
                        onClicked: root.backend.applyOptionsToQueue()
                    }
                }

                OptionsPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    backend: root.backend
                }
            }
        }
    }

    // ------------------------------------------------------------- dialogs
    FileDialog {
        id: fileDialog
        title: "Choose files to print"
        fileMode: FileDialog.OpenFiles
        nameFilters: [
            "Everything printable (*.pdf *.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff "
            + "*.txt *.log *.md *.csv *.json *.xml *.docx *.xlsx *.pptx *.rtf)",
            "Documents (*.pdf *.docx *.xlsx *.pptx *.rtf *.odt)",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff)",
            "Text (*.txt *.log *.md *.csv *.json *.xml)",
            "All files (*)"
        ]
        onAccepted: if (root.backend) root.backend.addUrls(selectedFiles)
    }

    FolderDialog {
        id: folderDialog
        title: "Add every printable file in a folder"
        onAccepted: if (root.backend) root.backend.addUrls([selectedFolder])
    }

    Modal {
        id: bigBatch
        title: "Print a large batch?"
        acceptText: "Print them all"
        rejectText: "Not yet"
        glyph: Theme.icon.warning
        tone: Theme.warn
        onAccepted: root.backend.start()
    }
}
