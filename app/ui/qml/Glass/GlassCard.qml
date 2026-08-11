import QtQuick
import Glass

/*
 * The single surface primitive. Every panel, row and button in the app is one of
 * these, which is what keeps the look consistent.
 *
 * The recipe, in layers from back to front:
 *   1. a low alpha white fill, so the blurred backdrop reads through it
 *   2. a hairline border at slightly higher alpha
 *   3. a brighter one pixel line along the top edge only, which the eye reads as
 *      a lit bevel and is the difference between "translucent" and "glass"
 *   4. an optional specular sweep on hover
 */
Item {
    id: root

    property real radius: Theme.radiusLg
    property color fill: Theme.glass
    property color fillHover: Theme.glassHover
    property color border: Theme.stroke
    property bool interactive: false
    property bool hovered: false
    property bool pressed: false
    property bool selected: false
    property bool showHighlight: true
    property bool sweepOnHover: true
    property real elevation: 1.0
    property alias contentItem: content

    // Lift and brighten together; either alone looks like a bug rather than a
    // response. The animations live on the transforms themselves so no
    // intermediate property is needed.
    transform: [
        Translate {
            y: root.interactive && root.hovered && !root.pressed ? -2 : 0
            Behavior on y {
                NumberAnimation { duration: Theme.ms(Theme.normal); easing.type: Theme.easeOut }
            }
        },
        Scale {
            origin.x: root.width / 2
            origin.y: root.height / 2
            xScale: root.pressed ? 0.985 : 1.0
            yScale: xScale
            Behavior on xScale {
                NumberAnimation { duration: Theme.ms(Theme.fast); easing.type: Theme.easeOut }
            }
        }
    ]

    // Shadow: two stacked soft rectangles rather than a blur pass, which is far
    // cheaper and good enough behind an opaque-ish card.
    Rectangle {
        anchors.fill: parent
        anchors.margins: -1
        anchors.topMargin: Math.round(3 * root.elevation)
        anchors.bottomMargin: Math.round(-5 * root.elevation)
        radius: root.radius + 2
        color: Qt.rgba(0, 0, 0, Theme.dark ? 0.22 * root.elevation : 0.07 * root.elevation)
        visible: root.elevation > 0
        z: -2
    }

    Rectangle {
        id: surface
        anchors.fill: parent
        radius: root.radius
        color: root.selected ? Qt.lighter(root.fillHover, 1.05)
                             : (root.interactive && root.hovered ? root.fillHover : root.fill)
        border.width: Theme.hairline
        border.color: root.selected ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.55)
                                    : root.border
        antialiasing: true

        Behavior on color {
            ColorAnimation { duration: Theme.ms(Theme.normal) }
        }
        Behavior on border.color {
            ColorAnimation { duration: Theme.ms(Theme.normal) }
        }

        // Lit top bevel. Inset by the border so it sits inside the frame.
        Rectangle {
            visible: root.showHighlight
            x: root.radius * 0.6
            y: Theme.hairline
            width: parent.width - root.radius * 1.2
            height: Theme.hairline
            color: Theme.highlight
            opacity: root.hovered ? 0.9 : 0.55
            Behavior on opacity {
                NumberAnimation { duration: Theme.ms(Theme.normal) }
            }
        }

        // Specular sweep: a soft diagonal band that travels across on hover.
        Item {
            anchors.fill: parent
            clip: true
            visible: root.sweepOnHover && root.interactive
            Rectangle {
                id: sweep
                width: parent.width * 0.42
                height: parent.height * 2.2
                y: -parent.height * 0.6
                x: root.hovered ? parent.width * 1.1 : -width * 1.2
                rotation: 18
                opacity: root.hovered ? 1 : 0
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, Theme.dark ? 0.055 : 0.5) }
                    GradientStop { position: 1.0; color: "transparent" }
                }
                Behavior on x {
                    NumberAnimation { duration: Theme.ms(620); easing.type: Easing.OutCubic }
                }
                Behavior on opacity {
                    NumberAnimation { duration: Theme.ms(Theme.fast) }
                }
            }
        }
    }

    Item {
        id: content
        anchors.fill: parent
    }
}
