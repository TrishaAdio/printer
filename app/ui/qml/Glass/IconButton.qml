import QtQuick
import Glass

/* Square icon-only button. Used in the title bar and on row actions. */
Item {
    id: root

    property string glyph: ""
    property string tip: ""
    property bool danger: false
    property bool flat: false
    property bool active: false
    property int size: 30
    property real glyphSize: Theme.fsBody

    signal clicked()

    implicitWidth: size
    implicitHeight: size
    opacity: enabled ? 1 : 0.35

    Behavior on opacity {
        NumberAnimation { duration: Theme.ms(Theme.normal) }
    }

    GlassCard {
        anchors.fill: parent
        radius: Theme.radiusSm
        interactive: root.enabled
        hovered: area.containsMouse
        pressed: area.pressed && root.enabled
        selected: root.active
        elevation: root.flat ? 0 : 0.6
        sweepOnHover: false
        showHighlight: !root.flat
        fill: root.flat && !area.containsMouse
              ? "transparent"
              : (root.danger && area.containsMouse
                 ? Qt.rgba(Theme.bad.r, Theme.bad.g, Theme.bad.b, 0.18)
                 : Theme.glass)
        border: root.flat && !area.containsMouse ? "transparent" : Theme.stroke
    }

    Text {
        anchors.centerIn: parent
        text: root.glyph
        font.family: Theme.iconFamily
        font.pixelSize: root.glyphSize
        color: root.danger
               ? (area.containsMouse ? Theme.bad : Theme.textDim)
               : (root.active ? Theme.accent
                              : (area.containsMouse ? Theme.text : Theme.textDim))
        Behavior on color {
            ColorAnimation { duration: Theme.ms(Theme.fast) }
        }
    }

    MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: root.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onEntered: if (root.enabled) Sfx.play("hover")
        onClicked: {
            if (!root.enabled)
                return
            Sfx.play("click")
            root.clicked()
        }
    }

    // Tooltip, drawn rather than using the Controls one so it matches the glass.
    Loader {
        active: root.tip !== "" && area.containsMouse
        z: 999
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.bottom
        anchors.topMargin: Theme.gap(0.75)
        sourceComponent: Component {
            Item {
                implicitWidth: label.implicitWidth + Theme.gap(2)
                implicitHeight: label.implicitHeight + Theme.gap(1.25)
                opacity: 0
                Component.onCompleted: opacity = 1
                Behavior on opacity {
                    NumberAnimation { duration: Theme.ms(Theme.normal) }
                }
                Rectangle {
                    anchors.fill: parent
                    radius: Theme.radiusSm
                    color: Theme.dark ? Qt.rgba(0.05, 0.06, 0.09, 0.94)
                                      : Qt.rgba(1, 1, 1, 0.97)
                    border.width: 1
                    border.color: Theme.stroke
                }
                Text {
                    id: label
                    anchors.centerIn: parent
                    text: root.tip
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fsTiny
                }
            }
        }
    }
}
