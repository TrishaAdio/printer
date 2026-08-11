import QtQuick
import QtQuick.Layouts
import Glass

/*
 * Transient messages, newest at the top.
 *
 * Capped at four visible: a batch of four hundred files can produce a lot of
 * notes, and a wall of toasts is worse than none. Identical consecutive messages
 * are collapsed into a counter instead of stacking.
 */
Item {
    id: root

    property int maxVisible: 4
    property int lifetime: 4200

    function show(kind, message) {
        if (!message)
            return
        if (model.count > 0) {
            const top = model.get(0)
            if (top.message === message && top.kind === kind) {
                model.setProperty(0, "repeats", top.repeats + 1)
                restartTimer(0)
                return
            }
        }
        model.insert(0, { kind: kind, message: message, repeats: 1,
                          born: Date.now() })
        while (model.count > root.maxVisible)
            model.remove(model.count - 1)
        Sfx.play(kind === "bad" ? "error" : "toast")
    }

    function restartTimer(index) {
        // Re-stamping the birth time is what extends a collapsed toast's life.
        model.setProperty(index, "born", Date.now())
    }

    ListModel { id: model }

    Timer {
        interval: 400
        repeat: true
        running: model.count > 0
        onTriggered: {
            const now = Date.now()
            for (let i = model.count - 1; i >= 0; i--) {
                if (now - model.get(i).born > root.lifetime)
                    model.remove(i)
            }
        }
    }

    ColumnLayout {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        width: Math.min(root.width, 360)
        spacing: Theme.gap(1)

        Repeater {
            model: model

            Item {
                id: toast
                required property string kind
                required property string message
                required property int repeats
                required property int index

                Layout.fillWidth: true
                implicitHeight: Math.max(40, label.implicitHeight + Theme.gap(2))

                readonly property color tone: Theme.statusColor(toast.kind)

                // Slide in from the right while fading up, on one curve.
                opacity: 0
                transform: Translate { id: slide; x: 28 }
                Component.onCompleted: opacity = 1

                Behavior on opacity {
                    NumberAnimation { duration: Theme.ms(Theme.normal) }
                }
                NumberAnimation {
                    target: slide
                    property: "x"
                    from: 28
                    to: 0
                    duration: Theme.ms(320)
                    easing.type: Theme.easeOut
                    running: true
                }

                GlassCard {
                    anchors.fill: parent
                    radius: Theme.radiusMd
                    elevation: 1.6
                    fill: Theme.dark ? Qt.rgba(0.06, 0.07, 0.11, 0.93)
                                     : Qt.rgba(1, 1, 1, 0.96)
                    border: Qt.rgba(toast.tone.r, toast.tone.g, toast.tone.b, 0.45)
                    sweepOnHover: false
                }

                Rectangle {
                    x: 0
                    y: Theme.gap(1)
                    width: 3
                    height: parent.height - Theme.gap(2)
                    radius: 1.5
                    color: toast.tone
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.gap(1.75)
                    anchors.rightMargin: Theme.gap(1.25)
                    spacing: Theme.gap(1)

                    Text {
                        text: toast.kind === "good" ? Theme.icon.check
                              : toast.kind === "bad" ? Theme.icon.error
                              : toast.kind === "warn" ? Theme.icon.warning
                              : Theme.icon.info
                        font.family: Theme.iconFamily
                        font.pixelSize: Theme.fsSmall
                        color: toast.tone
                        Layout.alignment: Qt.AlignTop
                        Layout.topMargin: 2
                    }

                    Text {
                        id: label
                        Layout.fillWidth: true
                        text: toast.repeats > 1
                              ? toast.message + "  (x" + toast.repeats + ")"
                              : toast.message
                        wrapMode: Text.WordWrap
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsSmall
                        color: Theme.text
                    }

                    IconButton {
                        glyph: Theme.icon.close
                        flat: true
                        size: 22
                        glyphSize: 8
                        Layout.alignment: Qt.AlignTop
                        onClicked: model.remove(toast.index)
                    }
                }
            }
        }
    }
}
