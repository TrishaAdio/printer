import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import Glass

/*
 * Custom title bar, because the window is frameless so the glass can run edge to
 * edge. Dragging and the double click to maximise are implemented here, and the
 * system snap gestures still work because the window is moved with
 * startSystemMove rather than by setting x and y.
 */
Item {
    id: root

    property var window: null
    property string title: ""
    property string subtitle: ""

    implicitHeight: Theme.titleBarHeight

    // Drag handling. startSystemMove hands the drag to Windows, which is what
    // keeps Aero Snap, shake to minimise and multi monitor behaviour intact.
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        onPressed: if (root.window) root.window.startSystemMove()
        onDoubleClicked: root.toggleMaximise()
    }

    function toggleMaximise() {
        if (!root.window)
            return
        if (root.window.visibility === Window.Maximized)
            root.window.showNormal()
        else
            root.window.showMaximized()
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.gap(2)
        anchors.rightMargin: Theme.gap(1)
        spacing: Theme.gap(1.5)

        // Mark: a small glass tile with the accent gradient, echoing the icon.
        Rectangle {
            Layout.preferredWidth: 24
            Layout.preferredHeight: 24
            radius: 7
            gradient: Gradient {
                GradientStop { position: 0.0; color: Theme.accent }
                GradientStop { position: 1.0; color: Theme.accent2 }
            }
            Text {
                anchors.centerIn: parent
                text: Theme.icon.print
                font.family: Theme.iconFamily
                font.pixelSize: 11
                color: "#FFFFFF"
            }
        }

        ColumnLayout {
            spacing: 0
            Layout.alignment: Qt.AlignVCenter

            Text {
                text: root.title
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fsBody
                font.weight: Font.DemiBold
                color: Theme.text
            }
            Text {
                visible: root.subtitle !== ""
                text: root.subtitle
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fsTiny
                color: Theme.textFaint
            }
        }

        Item { Layout.fillWidth: true }

        IconButton {
            glyph: Theme.icon.minimise
            tip: "Minimise"
            flat: true
            size: 32
            glyphSize: Theme.fsTiny
            onClicked: if (root.window) root.window.showMinimized()
        }

        IconButton {
            glyph: root.window && root.window.visibility === Window.Maximized
                   ? Theme.icon.restore : Theme.icon.maximise
            tip: root.window && root.window.visibility === Window.Maximized
                 ? "Restore" : "Maximise"
            flat: true
            size: 32
            glyphSize: Theme.fsTiny
            onClicked: root.toggleMaximise()
        }

        IconButton {
            glyph: Theme.icon.close
            tip: "Close"
            flat: true
            danger: true
            size: 32
            glyphSize: Theme.fsTiny
            onClicked: if (root.window) root.window.close()
        }
    }

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: Theme.hairline
        color: Theme.stroke
    }
}
