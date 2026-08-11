import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Glass

/*
 * Dropdown built on the Basic style so it can be skinned completely. The stock
 * styles bring their own background and would not match the glass.
 */
FieldRow {
    id: root

    stretch: true

    property var items: []            // list of strings, or of {text, value}
    property int currentIndex: -1
    property bool showEmpty: false
    property string emptyText: "Driver default"

    signal activated(int index)

    readonly property var effectiveItems: {
        const out = []
        if (root.showEmpty)
            out.push({ text: root.emptyText, value: 0 })
        for (let i = 0; i < root.items.length; i++) {
            const entry = root.items[i]
            if (entry === null || entry === undefined)
                continue
            if (typeof entry === "object")
                out.push({ text: entry.text !== undefined ? entry.text : String(entry.name),
                           value: entry.value !== undefined ? entry.value : entry.id })
            else
                out.push({ text: String(entry), value: i })
        }
        return out
    }

    function valueAt(index) {
        const list = root.effectiveItems
        if (index < 0 || index >= list.length)
            return undefined
        return list[index].value
    }

    function indexOfValue(value) {
        const list = root.effectiveItems
        for (let i = 0; i < list.length; i++) {
            if (list[i].value === value)
                return i
        }
        return -1
    }

    ComboBox {
        id: combo
        Layout.fillWidth: true
        Layout.preferredHeight: Theme.controlHeight
        enabled: root.fieldEnabled
        model: root.effectiveItems
        textRole: "text"
        currentIndex: root.currentIndex
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fsBody

        onActivated: function (index) {
            root.currentIndex = index
            Sfx.play("click")
            root.activated(index)
        }
        onPressedChanged: if (pressed) Sfx.play("click")

        background: GlassCard {
            radius: Theme.radiusSm
            interactive: combo.enabled
            hovered: combo.hovered
            pressed: combo.pressed
            elevation: 0.5
            sweepOnHover: false
            fill: combo.popup.visible ? Theme.glassHover : Theme.glass
        }

        contentItem: Text {
            leftPadding: Theme.gap(1.25)
            rightPadding: Theme.gap(3.5)
            text: combo.displayText
            font: combo.font
            color: Theme.text
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        indicator: Text {
            x: combo.width - width - Theme.gap(1.25)
            y: (combo.height - height) / 2
            text: Theme.icon.down
            font.family: Theme.iconFamily
            font.pixelSize: Theme.fsTiny
            color: combo.hovered ? Theme.text : Theme.textFaint
            rotation: combo.popup.visible ? 180 : 0
            Behavior on rotation {
                NumberAnimation { duration: Theme.ms(Theme.normal); easing.type: Theme.easeOut }
            }
        }

        popup: Popup {
            y: combo.height + 4
            width: combo.width
            implicitHeight: Math.min(contentItem.implicitHeight + Theme.gap(1), 300)
            padding: Theme.gap(0.5)
            modal: false

            enter: Transition {
                ParallelAnimation {
                    NumberAnimation {
                        property: "opacity"; from: 0; to: 1
                        duration: Theme.ms(Theme.fast)
                    }
                    NumberAnimation {
                        property: "y"; from: combo.height - 4; to: combo.height + 4
                        duration: Theme.ms(Theme.normal); easing.type: Theme.easeOut
                    }
                }
            }
            exit: Transition {
                NumberAnimation {
                    property: "opacity"; to: 0; duration: Theme.ms(Theme.fast)
                }
            }

            background: Rectangle {
                radius: Theme.radiusMd
                color: Theme.dark ? Qt.rgba(0.055, 0.065, 0.10, 0.985)
                                  : Qt.rgba(1, 1, 1, 0.99)
                border.width: Theme.hairline
                border.color: Theme.strokeStrong
            }

            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: combo.popup.visible ? combo.delegateModel : null
                currentIndex: combo.highlightedIndex
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {
                    active: true
                    contentItem: Rectangle {
                        implicitWidth: 4
                        radius: 2
                        color: Qt.rgba(1, 1, 1, 0.22)
                    }
                    background: Item {}
                }
            }
        }

        delegate: ItemDelegate {
            id: option
            required property var modelData
            required property int index

            width: combo.popup.width - Theme.gap(1)
            height: 32
            highlighted: combo.highlightedIndex === index

            background: Rectangle {
                radius: Theme.radiusSm
                color: option.highlighted
                       ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.20)
                       : "transparent"
            }

            contentItem: RowLayout {
                spacing: Theme.gap(1)
                Text {
                    Layout.fillWidth: true
                    leftPadding: Theme.gap(1)
                    text: option.modelData.text
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fsBody
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }
                Text {
                    visible: combo.currentIndex === option.index
                    rightPadding: Theme.gap(1)
                    text: Theme.icon.check
                    font.family: Theme.iconFamily
                    font.pixelSize: Theme.fsTiny
                    color: Theme.accent
                }
            }
        }
    }
}
