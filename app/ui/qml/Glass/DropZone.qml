import QtQuick
import QtQuick.Layouts
import Glass

/*
 * The drop target, and the main thing the app is about.
 *
 * It doubles as the preview surface: once something is queued it shows the first
 * page of the selected job rather than sitting there as an empty box, so the area
 * is never wasted. Drag feedback is deliberately loud, because the worst outcome
 * is a user not being sure whether a drop registered.
 */
Item {
    id: root

    property bool dragging: false
    property string previewUrl: ""
    property string previewName: ""
    property string previewInfo: ""
    property bool previewBusy: false
    property string previewError: ""

    signal filesDropped(var urls)
    signal browseFiles()
    signal browseFolder()

    GlassCard {
        id: card
        anchors.fill: parent
        radius: Theme.radiusXl
        elevation: 1.2
        interactive: true
        hovered: hoverArea.containsMouse || root.dragging
        selected: root.dragging
        sweepOnHover: !root.dragging

        // Inner outline. Solid rather than dashed: at a hairline weight a dashed
        // ring reads as noise against the grain, and the accent glow on drag is
        // already unambiguous feedback.
        Item {
            parent: card.contentItem
            anchors.fill: parent
            anchors.margins: Theme.gap(1.5)
            opacity: root.previewUrl === "" ? 1 : 0

            Behavior on opacity {
                NumberAnimation { duration: Theme.ms(Theme.slow) }
            }

            Rectangle {
                anchors.fill: parent
                radius: Theme.radiusLg
                color: root.dragging
                       ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.10)
                       : "transparent"
                border.width: root.dragging ? 2 : Theme.hairline
                border.color: root.dragging
                              ? Theme.accent
                              : Qt.rgba(1, 1, 1, Theme.dark ? 0.14 : 0.5)

                Behavior on color {
                    ColorAnimation { duration: Theme.ms(Theme.normal) }
                }
                Behavior on border.color {
                    ColorAnimation { duration: Theme.ms(Theme.normal) }
                }
            }
        }
    }

    // Scale nudge on drag enter. Small, because a big jump feels unstable.
    scale: root.dragging ? 1.012 : 1.0
    Behavior on scale {
        NumberAnimation { duration: Theme.ms(260); easing.type: Theme.easeOut }
    }

    // ------------------------------------------------------------ empty state
    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width - Theme.gap(8), 420)
        spacing: Theme.gap(1.5)
        visible: root.previewUrl === "" && !root.previewBusy
        opacity: visible ? 1 : 0

        Item {
            Layout.alignment: Qt.AlignHCenter
            implicitWidth: 76
            implicitHeight: 76

            // Halo behind the glyph, brighter while dragging.
            Rectangle {
                anchors.centerIn: parent
                width: parent.width * (root.dragging ? 1.25 : 1.0)
                height: width
                radius: width / 2
                color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b,
                               root.dragging ? 0.22 : 0.10)
                Behavior on width {
                    NumberAnimation { duration: Theme.ms(300); easing.type: Theme.easeOut }
                }
                Behavior on color {
                    ColorAnimation { duration: Theme.ms(Theme.normal) }
                }
            }

            Rectangle {
                anchors.centerIn: parent
                width: 54
                height: 54
                radius: Theme.radiusLg
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.12) }
                    GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.04) }
                }
                border.width: Theme.hairline
                border.color: Theme.stroke

                Text {
                    anchors.centerIn: parent
                    text: root.dragging ? Theme.icon.add : Theme.icon.document
                    font.family: Theme.iconFamily
                    font.pixelSize: 22
                    color: root.dragging ? Theme.accent : Theme.textDim
                }
            }

            // A gentle float, so the empty state is not completely static.
            SequentialAnimation on y {
                running: Theme.animationsOn && !Theme.reduceMotion && !root.dragging
                loops: Animation.Infinite
                NumberAnimation { to: -4; duration: 2200; easing.type: Easing.InOutSine }
                NumberAnimation { to: 0; duration: 2200; easing.type: Easing.InOutSine }
            }
        }

        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: root.dragging ? "Release to add" : "Drop files or folders here"
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fsTitle
            font.weight: Font.DemiBold
            color: Theme.text
        }

        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            text: "PDF, photos, scans and text. Whole folders are expanded, "
                  + "and hundreds of files at once are fine."
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fsSmall
            color: Theme.textDim
            lineHeight: 1.35
        }

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: Theme.gap(1)
            visible: !root.dragging

            GlassButton {
                text: "Choose files"
                glyph: Theme.icon.add
                onClicked: root.browseFiles()
            }
            GlassButton {
                text: "Add a folder"
                glyph: Theme.icon.folder
                onClicked: root.browseFolder()
            }
        }
    }

    // --------------------------------------------------------------- preview
    Item {
        anchors.fill: parent
        anchors.margins: Theme.gap(2.5)
        visible: root.previewUrl !== "" || root.previewBusy

        ColumnLayout {
            anchors.fill: parent
            spacing: Theme.gap(1.25)

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                // The sheet: white paper with a soft shadow, so a page reads as a
                // page rather than as a floating bitmap.
                Rectangle {
                    id: sheet
                    anchors.centerIn: parent
                    width: Math.min(parent.width, page.implicitWidth > 0
                                    ? parent.height * (page.implicitWidth / Math.max(1, page.implicitHeight))
                                    : parent.width * 0.72)
                    height: Math.min(parent.height, page.implicitHeight > 0
                                     ? width * (page.implicitHeight / Math.max(1, page.implicitWidth))
                                     : parent.height)
                    color: "#FFFFFF"
                    radius: 3
                    visible: root.previewUrl !== ""

                    Rectangle {
                        anchors.fill: parent
                        anchors.topMargin: 6
                        anchors.bottomMargin: -8
                        radius: 6
                        color: Qt.rgba(0, 0, 0, 0.30)
                        z: -1
                    }

                    Image {
                        id: page
                        anchors.fill: parent
                        source: root.previewUrl
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        cache: false
                        smooth: true
                        opacity: status === Image.Ready ? 1 : 0
                        Behavior on opacity {
                            NumberAnimation { duration: Theme.ms(Theme.slow) }
                        }
                    }
                }

                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: Theme.gap(1)
                    visible: root.previewBusy || root.previewError !== ""

                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: root.previewError !== "" ? Theme.icon.warning : Theme.icon.view
                        font.family: Theme.iconFamily
                        font.pixelSize: 20
                        color: root.previewError !== "" ? Theme.warn : Theme.textFaint
                    }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: root.previewError !== "" ? root.previewError : "Rendering preview"
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsSmall
                        color: Theme.textDim
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.gap(1)

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1
                    Text {
                        Layout.fillWidth: true
                        text: root.previewName
                        elide: Text.ElideMiddle
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsBody
                        font.weight: Font.DemiBold
                        color: Theme.text
                    }
                    Text {
                        Layout.fillWidth: true
                        text: root.previewInfo
                        elide: Text.ElideRight
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsTiny
                        color: Theme.textDim
                    }
                }

                GlassButton {
                    text: "Add more"
                    glyph: Theme.icon.add
                    onClicked: root.browseFiles()
                }
            }
        }
    }

    // ------------------------------------------------------------------ input
    MouseArea {
        id: hoverArea
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        cursorShape: root.previewUrl === "" ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (root.previewUrl === "") root.browseFiles()
    }

    DropArea {
        anchors.fill: parent
        onEntered: function (drag) {
            if (drag.hasUrls) {
                root.dragging = true
                Sfx.play("hover")
            }
        }
        onExited: root.dragging = false
        onDropped: function (drop) {
            root.dragging = false
            if (drop.hasUrls) {
                root.filesDropped(drop.urls)
                drop.acceptProposedAction()
            }
        }
    }
}
