import QtQuick
import QtQuick.Layouts
import Glass

/*
 * The label-plus-control row every option uses.
 *
 * All of the app's alignment consistency comes from here: one fixed label
 * column, one control column that fills the rest, one row height. Because every
 * field is built on this, nothing can drift out of line with its neighbours.
 *
 * Controls are laid out by a RowLayout rather than by anchoring them by hand;
 * a control only has to declare `Layout.fillWidth: true` to occupy the column.
 */
Item {
    id: root

    property string label: ""
    property string hint: ""
    property bool fieldEnabled: true
    property int labelWidth: Theme.labelWidth
    //: Whether the control should occupy the whole column. Text entry, combos and
    //: sliders want that; a two option switch does not. When false the surplus is
    //: absorbed by a trailing spacer so the control sits left instead of drifting
    //: to the middle, which is what the layout engine does with space nothing claims.
    property bool stretch: false
    // Children land in a slot that fills the remaining width. A control that
    // declares Layout.fillWidth stretches across the column; one that does not
    // sits at the left of it. Without this nesting, a non-filling control ends up
    // floating in the middle of the row because the layout has nowhere to put the
    // leftover space.
    default property alias content: slot.data

    implicitHeight: line.implicitHeight + (hintLabel.visible ? hintLabel.implicitHeight + 2 : 0)
    Layout.fillWidth: true
    opacity: fieldEnabled ? 1 : 0.4

    Behavior on opacity {
        NumberAnimation { duration: Theme.ms(Theme.normal) }
    }

    RowLayout {
        id: line
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: Theme.gap(1)

        Text {
            text: root.label
            color: Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fsSmall
            elide: Text.ElideRight
            Layout.preferredWidth: root.labelWidth - line.spacing
            Layout.maximumWidth: root.labelWidth - line.spacing
            Layout.alignment: Qt.AlignVCenter
        }

        RowLayout {
            id: slot
            Layout.fillWidth: root.stretch
            spacing: Theme.gap(1)
        }

        Item {
            Layout.fillWidth: !root.stretch
            Layout.preferredWidth: 0
        }
    }

    Text {
        id: hintLabel
        visible: root.hint !== ""
        anchors.left: parent.left
        anchors.leftMargin: root.labelWidth
        anchors.right: parent.right
        anchors.top: line.bottom
        anchors.topMargin: 2
        text: root.hint
        color: Theme.textFaint
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fsTiny
        wrapMode: Text.WordWrap
    }
}
