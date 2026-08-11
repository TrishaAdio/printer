import QtQuick
import Glass

/*
 * Fine grain over the whole window.
 *
 * This is the detail that stops large translucent panels reading as flat plastic.
 * The texture is a tiled 160 px sprite of white specks with varying alpha, laid
 * on at a few percent, and it is deliberately not animated: moving grain is
 * distracting and, at this scale, looks like video noise.
 */
Item {
    id: root
    property real strength: Theme.grainOpacity

    Image {
        anchors.fill: parent
        source: "../../../assets/images/noise.png"
        fillMode: Image.Tile
        horizontalAlignment: Image.AlignLeft
        verticalAlignment: Image.AlignTop
        opacity: root.strength
        cache: true
        smooth: false
        mipmap: false
        asynchronous: true
    }
}
