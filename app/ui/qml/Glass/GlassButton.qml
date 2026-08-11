import QtQuick
import QtQuick.Layouts
import Glass

/*
 * Buttons come in three weights. `primary` is the filled accent gradient used for
 * the one action a screen is about; `subtle` is a bare label for tertiary
 * actions; everything else is a glass card.
 */
Item {
    id: root

    property string text: ""
    property string glyph: ""
    property bool primary: false
    property bool subtle: false
    property bool danger: false
    property bool busy: false
    property int horizontalPadding: Theme.gap(2)
    property alias hovered: hover.hovered
    property color accentColor: root.danger ? Theme.bad : Theme.accent

    signal clicked()

    implicitHeight: Theme.controlHeight
    implicitWidth: row.implicitWidth + horizontalPadding * 2
    opacity: enabled ? 1.0 : 0.42

    Behavior on opacity {
        NumberAnimation { duration: Theme.ms(Theme.normal) }
    }

    GlassCard {
        id: cardSurface
        anchors.fill: parent
        radius: Theme.radiusMd
        interactive: root.enabled
        hovered: hover.hovered
        pressed: hover.pressed && root.enabled
        visible: !root.subtle
        elevation: root.primary ? 1.4 : 0.8
        fill: root.primary ? "transparent"
                           : (root.danger && hover.hovered
                              ? Qt.rgba(Theme.bad.r, Theme.bad.g, Theme.bad.b, 0.16)
                              : Theme.glass)
        border: root.primary ? Qt.rgba(1, 1, 1, 0.24)
                             : (root.danger
                                ? Qt.rgba(Theme.bad.r, Theme.bad.g, Theme.bad.b, 0.42)
                                : Theme.stroke)

        // The accent fill sits inside the card so it inherits the same radius,
        // bevel and sweep as every other surface.
        Rectangle {
            parent: cardSurface.contentItem
            anchors.fill: parent
            radius: Theme.radiusMd
            visible: root.primary
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop {
                    position: 0.0
                    color: hover.hovered ? Qt.lighter(root.accentColor, 1.12) : root.accentColor
                }
                GradientStop {
                    position: 1.0
                    color: hover.hovered ? Qt.lighter(Theme.accent2, 1.12) : Theme.accent2
                }
            }
        }
    }

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: Theme.gap(1)

        Text {
            visible: root.glyph !== "" && !root.busy
            text: root.glyph
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fsHeading
            color: root.primary ? "#FFFFFF"
                                : (root.danger ? Theme.bad
                                               : (hover.hovered ? Theme.text : Theme.textDim))
        }

        Item {
            visible: root.busy
            implicitWidth: 14
            implicitHeight: 14
            Rectangle {
                anchors.fill: parent
                radius: width / 2
                color: "transparent"
                border.width: 2
                border.color: Qt.rgba(1, 1, 1, 0.25)
            }
            Rectangle {
                width: 4; height: 4; radius: 2
                color: root.primary ? "#FFFFFF" : Theme.accent
                x: parent.width / 2 - 2
                y: 0
                transformOrigin: Item.Center
                RotationAnimator on rotation {
                    running: root.busy
                    loops: Animation.Infinite
                    from: 0; to: 360; duration: 900
                }
            }
        }

        Text {
            visible: root.text !== ""
            text: root.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fsBody
            font.weight: root.primary ? Font.DemiBold : Font.Medium
            color: root.primary ? "#FFFFFF"
                                : (root.danger ? Theme.bad
                                               : (hover.hovered ? Theme.text : Theme.textDim))
            Behavior on color {
                ColorAnimation { duration: Theme.ms(Theme.fast) }
            }
        }
    }

    // Focus ring, for keyboard users.
    Rectangle {
        anchors.fill: parent
        anchors.margins: -3
        radius: Theme.radiusMd + 3
        color: "transparent"
        border.width: 2
        border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.7)
        visible: root.activeFocus
    }

    MouseArea {
        id: hover
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: root.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        property bool hovered: false
        onEntered: {
            hovered = true
            if (root.enabled)
                Sfx.play("hover")
        }
        onExited: hovered = false
        onClicked: {
            if (!root.enabled)
                return
            Sfx.play("click")
            root.clicked()
        }
    }

    Keys.onReturnPressed: if (root.enabled) root.clicked()
    Keys.onSpacePressed: if (root.enabled) root.clicked()
}
