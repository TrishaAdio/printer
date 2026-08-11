import QtQuick
import Glass

/*
 * The opening title sequence.
 *
 * An original piece in the spirit of the streaming service openers: black, a
 * light sweep that reveals the wordmark, a low sting on the reveal, then the
 * whole thing pulls apart to hand over to the app. Nothing is copied from anyone
 * else's identity; the sound is synthesised in tools/gen_assets.py.
 *
 * Timeline, in milliseconds from start:
 *     0    black, the mark begins to scale in from slightly large
 *   180    vertical light bars sweep in from both edges
 *   420    bars collide at the centre, sting fires, wordmark revealed by a mask
 *   900    letters settle, subtitle fades up, ambience continues
 *  1900    bloom flash, everything scales up and fades out
 *  2400    finished, `done` is emitted
 *
 * It can be skipped with any click or key press, and turned off in settings; both
 * paths go through `finish()` so it can never leave the app hidden behind it.
 */
Item {
    id: root

    property string appName: "GlassPrint"
    property string tagline: "Precision printing"
    property bool soundEnabled: true

    signal done()

    property bool finished: false
    property real timeline: 0        // 0..1 across the whole sequence
    readonly property int duration: 2400

    function start() {
        runner.restart()
        if (root.soundEnabled)
            Sfx.play("intro")
    }

    function finish() {
        if (root.finished)
            return
        root.finished = true
        runner.stop()
        exitAnim.start()
    }

    anchors.fill: parent
    focus: true

    // ------------------------------------------------------------- background
    Rectangle {
        anchors.fill: parent
        color: "#04050A"
    }

    // A slow radial glow that grows through the whole sequence, so the frame is
    // never completely flat even before the reveal.
    // The glow behind the mark, built from stacked low alpha discs for the same
    // reason as the window background: no shader, nothing to fail silently.
    Item {
        anchors.fill: parent
        opacity: Math.min(1, root.timeline * 2.2)

        Repeater {
            model: 14

            Rectangle {
                required property int index
                readonly property real step: (index + 1) / 14

                anchors.centerIn: parent
                width: (parent.width * 0.78) * (1.0 - index / 15)
                       * (0.55 + root.timeline * 0.95)
                height: width
                radius: width / 2
                color: index % 2 === 0 ? Theme.accent : Theme.accent2
                opacity: 0.012 + 0.055 * Math.pow(step, 2.0)
                antialiasing: true
            }
        }
    }

    // ------------------------------------------------------------------- mark
    Item {
        id: stage
        anchors.centerIn: parent
        width: Math.min(parent.width * 0.8, 560)
        height: 150

        // Overall breathing scale: starts slightly large, settles, then pushes
        // past on the way out. Reads as a camera move rather than a fade.
        scale: exitAnim.running ? 1.0 : (1.06 - 0.06 * Math.min(1, root.timeline * 3.2))

        Column {
            anchors.centerIn: parent
            spacing: Theme.gap(1.5)

            // The wordmark, revealed by a window that widens from the centre.
            //
            // A clip rather than a shader mask: clipping is exact, needs no
            // texture provider and no offscreen pass, and behaves identically on
            // every driver. The letters are positioned against the stage, so as
            // the clip grows they are uncovered in place instead of sliding.
            Item {
                id: wordmarkHolder
                width: stage.width
                height: 62

                Item {
                    id: revealWindow
                    anchors.centerIn: parent
                    width: parent.width * root.revealFraction
                    height: parent.height
                    clip: true

                    // Chromatic fringes: the same letters in accent colours,
                    // offset a couple of pixels, fading out as things settle.
                    Text {
                        x: wordmarkHolder.width / 2 - revealWindow.width / 2
                           - implicitWidth / 2 + wordmarkHolder.width / 2 - 2
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.appName.toUpperCase()
                        font: mainWord.font
                        color: Theme.accent
                        opacity: 0.6 * (1.0 - root.settleFraction)
                    }

                    Text {
                        x: wordmarkHolder.width / 2 - revealWindow.width / 2
                           - implicitWidth / 2 + wordmarkHolder.width / 2 + 2
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.appName.toUpperCase()
                        font: mainWord.font
                        color: Theme.accent2
                        opacity: 0.6 * (1.0 - root.settleFraction)
                    }

                    Text {
                        id: mainWord
                        // Keep the glyphs pinned to the holder's centre while the
                        // clip window grows around them.
                        x: wordmarkHolder.width / 2 - revealWindow.width / 2
                           - implicitWidth / 2 + wordmarkHolder.width / 2
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.appName.toUpperCase()
                        font.family: Theme.fontFamily
                        font.pixelSize: 52
                        font.weight: Font.Black
                        font.letterSpacing: 6
                        color: "#FFFFFF"
                    }
                }
            }

            // Subtitle fades up once the letters have settled.
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.tagline
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fsBody
                font.letterSpacing: 5
                font.weight: Font.Medium
                color: Theme.textDim
                opacity: root.settleFraction
                // A transform, not `y`: assigning y inside a Column overrides the
                // positioner and the subtitle lands on top of the wordmark.
                transform: Translate { y: 6 * (1 - root.settleFraction) }
            }
        }

        // The two light bars that sweep in and collide at the centre.
        Repeater {
            model: 2
            Rectangle {
                required property int index
                readonly property real direction: index === 0 ? -1 : 1

                width: 2
                height: stage.height * 0.62
                anchors.verticalCenter: stage.verticalCenter
                x: stage.width / 2 - width / 2
                   + direction * (stage.width / 2) * (1.0 - root.barFraction)
                opacity: root.barOpacity
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.5; color: index === 0 ? Theme.accent : Theme.accent2 }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }
        }

        // Impact flash at the collision.
        Rectangle {
            anchors.centerIn: stage
            width: stage.width * (0.2 + root.flash * 1.1)
            height: 3 + root.flash * 5
            radius: height / 2
            opacity: root.flash
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 0.5; color: "#FFFFFF" }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }
    }

    // Grain over the top, tying the intro to the rest of the app's look.
    GrainOverlay {
        anchors.fill: parent
        strength: 0.055
    }

    // --------------------------------------------------------------- timeline
    property real revealFraction: 0
    property real barFraction: 0
    property real barOpacity: 0
    property real settleFraction: 0
    property real flash: 0

    SequentialAnimation {
        id: runner

        ParallelAnimation {
            NumberAnimation {
                target: root; property: "timeline"
                from: 0; to: 1; duration: root.duration
                easing.type: Easing.InOutQuad
            }

            SequentialAnimation {
                PauseAnimation { duration: 180 }
                ParallelAnimation {
                    NumberAnimation {
                        target: root; property: "barFraction"
                        from: 0; to: 1; duration: 260; easing.type: Easing.InQuad
                    }
                    NumberAnimation {
                        target: root; property: "barOpacity"
                        from: 0; to: 1; duration: 140
                    }
                }
                // Collision.
                ParallelAnimation {
                    NumberAnimation {
                        target: root; property: "flash"
                        from: 0; to: 1; duration: 90
                    }
                    NumberAnimation {
                        target: root; property: "barOpacity"
                        from: 1; to: 0; duration: 220
                    }
                }
                ParallelAnimation {
                    NumberAnimation {
                        target: root; property: "revealFraction"
                        from: 0; to: 1.05; duration: 520; easing.type: Easing.OutCubic
                    }
                    NumberAnimation {
                        target: root; property: "flash"
                        from: 1; to: 0; duration: 420; easing.type: Easing.OutCubic
                    }
                }
                NumberAnimation {
                    target: root; property: "settleFraction"
                    from: 0; to: 1; duration: 460; easing.type: Easing.OutCubic
                }
                PauseAnimation { duration: 620 }
            }
        }

        ScriptAction { script: root.finish() }
    }

    // Exit: a short push and fade, which hands over to the window underneath.
    ParallelAnimation {
        id: exitAnim
        NumberAnimation {
            target: root; property: "opacity"
            to: 0; duration: Theme.ms(420); easing.type: Easing.InQuad
        }
        NumberAnimation {
            target: stage; property: "scale"
            to: 1.08; duration: Theme.ms(460); easing.type: Easing.InQuad
        }
        onFinished: root.done()
    }

    // ------------------------------------------------------------------- skip
    MouseArea {
        anchors.fill: parent
        onClicked: root.finish()
    }
    Keys.onPressed: function (event) {
        root.finish()
        event.accepted = true
    }

    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.gap(4)
        text: "click to skip"
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fsTiny
        font.letterSpacing: 2
        color: Theme.textFaint
        opacity: root.settleFraction * 0.7
    }
}
