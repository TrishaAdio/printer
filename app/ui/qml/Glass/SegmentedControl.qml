import QtQuick
import QtQuick.Layouts
import Glass

/*
 * A row of exclusive choices with a single indicator that slides between them.
 * Sliding one indicator rather than fading each segment makes the relationship
 * between the options obvious and costs one animation instead of N.
 */
Item {
    id: root

    property var options: []          // [{ text, value, glyph }] or plain strings
    property var value: undefined
    property bool useFieldRow: false
    property int itemHeight: 30

    signal picked(var value)

    readonly property var normalised: {
        const out = []
        for (let i = 0; i < options.length; i++) {
            const entry = options[i]
            if (typeof entry === "object")
                out.push({ text: entry.text, value: entry.value !== undefined ? entry.value : entry.text,
                           glyph: entry.glyph !== undefined ? entry.glyph : "" })
            else
                out.push({ text: String(entry), value: entry, glyph: "" })
        }
        return out
    }

    readonly property int currentIndex: {
        for (let i = 0; i < normalised.length; i++) {
            if (normalised[i].value === root.value)
                return i
        }
        return -1
    }

    implicitHeight: itemHeight + Theme.gap(0.5)
    implicitWidth: row.implicitWidth + Theme.gap(0.5)

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusMd
        color: Theme.glassSunken
        border.width: Theme.hairline
        border.color: Theme.stroke
    }

    // The sliding indicator, positioned from the current segment's geometry so it
    // stays correct whatever the segment widths turn out to be.
    Rectangle {
        id: indicator
        visible: root.currentIndex >= 0
        y: Theme.gap(0.25)
        height: root.itemHeight
        radius: Theme.radiusSm
        x: {
            const item = segments.itemAt(root.currentIndex)
            return item ? item.x + row.x : Theme.gap(0.25)
        }
        width: {
            const item = segments.itemAt(root.currentIndex)
            return item ? item.width : 0
        }
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop {
                position: 0.0
                color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.34)
            }
            GradientStop {
                position: 1.0
                color: Qt.rgba(Theme.accent2.r, Theme.accent2.g, Theme.accent2.b, 0.30)
            }
        }
        border.width: Theme.hairline
        border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.5)

        Behavior on x {
            NumberAnimation { duration: Theme.ms(280); easing.type: Theme.easeOut }
        }
        Behavior on width {
            NumberAnimation { duration: Theme.ms(280); easing.type: Theme.easeOut }
        }
    }

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: Theme.gap(0.25)
        spacing: 0

        Repeater {
            id: segments
            model: root.normalised

            Item {
                id: segment
                required property var modelData
                required property int index

                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: segContent.implicitWidth + Theme.gap(2.5)
                // A preferred width as well as a minimum, so the control has a
                // meaningful implicitWidth and can size to its content instead of
                // only ever stretching to whatever it is put inside.
                Layout.preferredWidth: segContent.implicitWidth + Theme.gap(3.5)

                readonly property bool current: root.currentIndex === segment.index

                RowLayout {
                    id: segContent
                    anchors.centerIn: parent
                    spacing: Theme.gap(0.75)

                    Text {
                        visible: segment.modelData.glyph !== ""
                        text: segment.modelData.glyph
                        font.family: Theme.iconFamily
                        font.pixelSize: Theme.fsSmall
                        color: segment.current ? Theme.text
                                               : (hover.containsMouse ? Theme.text : Theme.textDim)
                    }

                    Text {
                        id: label
                        text: segment.modelData.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsSmall
                        font.weight: segment.current ? Font.DemiBold : Font.Medium
                        color: segment.current ? Theme.text
                                               : (hover.containsMouse ? Theme.text : Theme.textDim)
                        Behavior on color {
                            ColorAnimation { duration: Theme.ms(Theme.fast) }
                        }
                    }
                }

                MouseArea {
                    id: hover
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onEntered: Sfx.play("hover")
                    onClicked: {
                        if (segment.current)
                            return
                        Sfx.play("click")
                        root.value = segment.modelData.value
                        root.picked(segment.modelData.value)
                    }
                }
            }
        }
    }
}
