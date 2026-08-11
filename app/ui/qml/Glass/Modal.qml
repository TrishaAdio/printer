import QtQuick
import QtQuick.Layouts
import Glass

/*
 * A blocking dialog. Used for the manual two sided paper swap and for
 * confirmations that would otherwise destroy work.
 *
 * The scrim darkens rather than blurs the window behind it: blurring a layer that
 * is already blurred glass turns into mush, and it costs a full frame buffer.
 */
Item {
    id: root

    property string title: ""
    property string message: ""
    property string acceptText: "Continue"
    property string rejectText: "Cancel"
    property string glyph: Theme.icon.info
    property color tone: Theme.accent
    property bool showReject: true
    property var payload: undefined

    signal accepted(var payload)
    signal rejected(var payload)

    visible: false
    anchors.fill: parent
    z: 900

    function open(options) {
        if (options) {
            title = options.title !== undefined ? options.title : title
            message = options.message !== undefined ? options.message : message
            acceptText = options.acceptText !== undefined ? options.acceptText : "Continue"
            rejectText = options.rejectText !== undefined ? options.rejectText : "Cancel"
            glyph = options.glyph !== undefined ? options.glyph : Theme.icon.info
            tone = options.tone !== undefined ? options.tone : Theme.accent
            showReject = options.showReject !== undefined ? options.showReject : true
            payload = options.payload
        }
        visible = true
        card.appear = true
        Sfx.play("toast")
    }

    function accept() {
        card.appear = false
        visible = false
        accepted(payload)
    }

    function reject() {
        card.appear = false
        visible = false
        rejected(payload)
    }

    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, Theme.dark ? 0.58 : 0.32)
        opacity: card.appear ? 1 : 0
        Behavior on opacity {
            NumberAnimation { duration: Theme.ms(Theme.normal) }
        }
        MouseArea {
            anchors.fill: parent
            onClicked: if (root.showReject) root.reject()
        }
    }

    Item {
        id: card
        property bool appear: false

        anchors.centerIn: parent
        width: Math.min(parent.width - Theme.gap(8), 460)
        height: layout.implicitHeight + Theme.gap(4)

        opacity: appear ? 1 : 0
        scale: appear ? 1 : 0.96
        Behavior on opacity {
            NumberAnimation { duration: Theme.ms(Theme.normal) }
        }
        Behavior on scale {
            NumberAnimation { duration: Theme.ms(260); easing.type: Theme.easeOut }
        }

        GlassCard {
            anchors.fill: parent
            radius: Theme.radiusXl
            elevation: 2.2
            fill: Theme.dark ? Qt.rgba(0.07, 0.08, 0.12, 0.97) : Qt.rgba(1, 1, 1, 0.98)
            border: Theme.strokeStrong
            sweepOnHover: false
        }

        ColumnLayout {
            id: layout
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Theme.gap(2.5)
            spacing: Theme.gap(1.5)

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.gap(1.5)

                Rectangle {
                    Layout.preferredWidth: 38
                    Layout.preferredHeight: 38
                    radius: Theme.radiusMd
                    color: Qt.rgba(root.tone.r, root.tone.g, root.tone.b, 0.16)
                    border.width: Theme.hairline
                    border.color: Qt.rgba(root.tone.r, root.tone.g, root.tone.b, 0.4)
                    Text {
                        anchors.centerIn: parent
                        text: root.glyph
                        font.family: Theme.iconFamily
                        font.pixelSize: Theme.fsHeading
                        color: root.tone
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: root.title
                    wrapMode: Text.WordWrap
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fsTitle
                    font.weight: Font.DemiBold
                    color: Theme.text
                }
            }

            Text {
                Layout.fillWidth: true
                text: root.message
                wrapMode: Text.WordWrap
                lineHeight: 1.4
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fsBody
                color: Theme.textDim
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: Theme.gap(0.5)
                spacing: Theme.gap(1)

                Item { Layout.fillWidth: true }

                GlassButton {
                    visible: root.showReject
                    text: root.rejectText
                    onClicked: root.reject()
                }

                GlassButton {
                    text: root.acceptText
                    primary: true
                    horizontalPadding: Theme.gap(2.5)
                    onClicked: root.accept()
                }
            }
        }
    }

    Keys.onEscapePressed: if (root.showReject) root.reject()
    Keys.onReturnPressed: root.accept()
}
