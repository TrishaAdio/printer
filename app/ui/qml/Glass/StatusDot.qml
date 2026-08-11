import QtQuick
import Glass

/* A state dot that breathes when the state is "in progress". */
Item {
    id: root

    property color tone: Theme.good
    property bool pulsing: false
    property int size: 8

    implicitWidth: size
    implicitHeight: size

    Rectangle {
        id: halo
        anchors.centerIn: parent
        width: root.size * 2.2
        height: width
        radius: width / 2
        color: root.tone
        opacity: 0
        visible: root.pulsing && Theme.animationsOn && !Theme.reduceMotion

        SequentialAnimation {
            running: halo.visible
            loops: Animation.Infinite
            ParallelAnimation {
                NumberAnimation {
                    target: halo; property: "opacity"
                    from: 0.32; to: 0; duration: 1500; easing.type: Easing.OutCubic
                }
                NumberAnimation {
                    target: halo; property: "scale"
                    from: 0.5; to: 1.15; duration: 1500; easing.type: Easing.OutCubic
                }
            }
        }
    }

    Rectangle {
        anchors.centerIn: parent
        width: root.size
        height: root.size
        radius: width / 2
        color: root.tone
        Behavior on color {
            ColorAnimation { duration: Theme.ms(Theme.normal) }
        }
    }
}
