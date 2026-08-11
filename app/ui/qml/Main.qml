import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import Glass

/*
 * The window.
 *
 * Frameless and translucent so the glass can run to the edge and so Windows can
 * blur what is behind it. That means three things are ours to implement rather
 * than the system's: the rounded shape, the title bar, and resizing from the
 * edges. Windows 10 has no system rounded corners, which is the main reason the
 * shape is drawn here.
 */
Window {
    id: win

    width: Math.max(1060, App.getSetting("window_width") || 1180)
    height: Math.max(680, App.getSetting("window_height") || 760)
    minimumWidth: 1000
    minimumHeight: 660
    visible: true
    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint
    title: App.appName

    property int currentTab: 0
    readonly property bool maximised: win.visibility === Window.Maximized
    // Squared off when maximised: a rounded window against the screen edge shows
    // slivers of desktop in the corners.
    readonly property int shellRadius: maximised ? 0 : Theme.windowRadius

    // Development helper used by tools/screenshot.py to capture frames offscreen.
    // Harmless in a release build and the only way in, since PySide cannot pass a
    // QQuickItem back to Python.
    function grabFrame(path) {
        // contentItem rather than `shell`: the intro and the overlays are
        // siblings of the shell, so grabbing the shell alone would miss them.
        return contentItem.grabToImage(function (result) { result.saveToFile(path) })
    }

    // ---------------------------------------------------------------- shell
    Rectangle {
        id: shell
        anchors.fill: parent
        radius: win.shellRadius
        // Not fully opaque: this is the tint that sits over the blurred desktop.
        color: Theme.dark ? Qt.rgba(0.043, 0.051, 0.078, 0.86)
                          : Qt.rgba(0.94, 0.96, 0.99, 0.86)
        border.width: win.maximised ? 0 : Theme.hairline
        border.color: Theme.dark ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(0, 0, 0, 0.10)
        antialiasing: true

        Behavior on radius {
            NumberAnimation { duration: Theme.ms(Theme.fast) }
        }

        // Everything inside is clipped to the rounded shape.
        Item {
            id: clipper
            anchors.fill: parent
            anchors.margins: Theme.hairline
            layer.enabled: !win.maximised
            layer.smooth: true

            MeshBackground {
                anchors.fill: parent
            }

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                TitleBar {
                    Layout.fillWidth: true
                    window: win
                    title: App.appName
                    subtitle: App.simulated ? "Simulation mode" : App.printerStatusText
                }

                // ------------------------------------------------- nav strip
                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: Theme.gap(2.5)
                    Layout.rightMargin: Theme.gap(2.5)
                    Layout.topMargin: Theme.gap(1.75)
                    spacing: Theme.gap(1.5)

                    SegmentedControl {
                        id: tabs
                        itemHeight: 32
                        options: [
                            { text: "Print", value: 0, glyph: Theme.icon.print },
                            { text: "Queue", value: 1, glyph: Theme.icon.queue },
                            { text: "History", value: 2, glyph: Theme.icon.history },
                            { text: "Settings", value: 3, glyph: Theme.icon.settings }
                        ]
                        value: win.currentTab
                        onPicked: function (v) { win.currentTab = v }
                    }

                    Item { Layout.fillWidth: true }

                    // Printer picker. Sits in the chrome rather than in the
                    // options panel because it is the one setting that changes
                    // what every other option can even be.
                    Item {
                        id: printerPicker
                        Layout.preferredWidth: 300
                        Layout.preferredHeight: 40

                        GlassCard {
                            anchors.fill: parent
                            radius: Theme.radiusMd
                            interactive: true
                            hovered: pickerArea.containsMouse
                            pressed: pickerArea.pressed
                            elevation: 0.6
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: Theme.gap(1.5)
                            anchors.rightMargin: Theme.gap(1.25)
                            spacing: Theme.gap(1)

                            StatusDot {
                                tone: Theme.statusColor(App.printerStatus)
                                pulsing: App.printerStatus === "busy"
                                Layout.alignment: Qt.AlignVCenter
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0

                                Text {
                                    Layout.fillWidth: true
                                    text: App.printer !== "" ? App.printer : "No printer found"
                                    elide: Text.ElideRight
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fsSmall
                                    font.weight: Font.DemiBold
                                    color: Theme.text
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: App.printerStatusText
                                    elide: Text.ElideRight
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fsTiny
                                    color: Theme.statusColor(App.printerStatus)
                                }
                            }

                            Text {
                                text: Theme.icon.down
                                font.family: Theme.iconFamily
                                font.pixelSize: 9
                                color: Theme.textFaint
                                rotation: printerMenu.visible ? 180 : 0
                                Behavior on rotation {
                                    NumberAnimation { duration: Theme.ms(Theme.normal) }
                                }
                            }
                        }

                        MouseArea {
                            id: pickerArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onEntered: Sfx.play("hover")
                            onClicked: {
                                Sfx.play("click")
                                printerMenu.visible = !printerMenu.visible
                            }
                        }
                    }

                    IconButton {
                        glyph: Theme.icon.refresh
                        tip: "Look for printers again"
                        onClicked: App.refreshPrinters()
                    }
                }

                // ------------------------------------------------ tab content
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.margins: Theme.gap(2.5)
                    Layout.topMargin: Theme.gap(2)

                    // Views are kept alive rather than reloaded, so switching tabs
                    // does not lose scroll position or restart a preview render.
                    PrintView {
                        id: printView
                        anchors.fill: parent
                        backend: App
                        opacity: win.currentTab === 0 ? 1 : 0
                        visible: opacity > 0.01
                        enabled: win.currentTab === 0
                        transform: Translate { y: win.currentTab === 0 ? 0 : 10 }
                        Behavior on opacity {
                            NumberAnimation { duration: Theme.ms(Theme.normal) }
                        }
                        onOpenQueue: win.currentTab = 1
                    }

                    QueueView {
                        id: queueView
                        anchors.fill: parent
                        backend: App
                        opacity: win.currentTab === 1 ? 1 : 0
                        visible: opacity > 0.01
                        enabled: win.currentTab === 1
                        Behavior on opacity {
                            NumberAnimation { duration: Theme.ms(Theme.normal) }
                        }
                        onJobSelected: function (jobId, path, name) {
                            printView.previewJob(path, name)
                        }
                    }

                    HistoryView {
                        id: historyView
                        anchors.fill: parent
                        backend: App
                        opacity: win.currentTab === 2 ? 1 : 0
                        visible: opacity > 0.01
                        enabled: win.currentTab === 2
                        Behavior on opacity {
                            NumberAnimation { duration: Theme.ms(Theme.normal) }
                        }
                    }

                    SettingsView {
                        id: settingsView
                        anchors.fill: parent
                        backend: App
                        opacity: win.currentTab === 3 ? 1 : 0
                        visible: opacity > 0.01
                        enabled: win.currentTab === 3
                        Behavior on opacity {
                            NumberAnimation { duration: Theme.ms(Theme.normal) }
                        }
                    }
                }

                // ------------------------------------------------ status bar
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 30

                    Rectangle {
                        anchors.top: parent.top
                        width: parent.width
                        height: Theme.hairline
                        color: Theme.stroke
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.gap(2.5)
                        anchors.rightMargin: Theme.gap(2.5)
                        spacing: Theme.gap(1.5)

                        Text {
                            text: App.simulated
                                  ? "Simulation mode, no paper will move"
                                  : App.printerStatusText
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fsTiny
                            color: App.simulated ? Theme.warn : Theme.textFaint
                        }

                        Rectangle {
                            width: Theme.hairline
                            height: 12
                            color: Theme.stroke
                        }

                        Text {
                            text: App.effectiveDpi + " dpi"
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fsTiny
                            color: Theme.textFaint
                        }

                        Item { Layout.fillWidth: true }

                        Text {
                            text: App.queueSummary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fsTiny
                            color: Theme.textFaint
                        }

                        Rectangle {
                            width: Theme.hairline
                            height: 12
                            color: Theme.stroke
                        }

                        Text {
                            text: App.appName + " " + App.version
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fsTiny
                            color: Theme.textFaint
                        }
                    }
                }
            }

            GrainOverlay {
                anchors.fill: parent
            }
        }
    }

    // ------------------------------------------------------- printer dropdown
    Item {
        id: printerMenu
        visible: false
        anchors.fill: parent
        z: 800

        MouseArea {
            anchors.fill: parent
            onClicked: printerMenu.visible = false
        }

        GlassCard {
            id: menuCard
            x: printerPicker.mapToItem(win.contentItem, 0, 0).x
            y: printerPicker.mapToItem(win.contentItem, 0, 0).y + printerPicker.height + 6
            width: Math.max(340, printerPicker.width)
            height: Math.min(menuColumn.implicitHeight + Theme.gap(2), 400)
            radius: Theme.radiusLg
            elevation: 2.0
            sweepOnHover: false
            fill: Theme.dark ? Qt.rgba(0.055, 0.065, 0.10, 0.985) : Qt.rgba(1, 1, 1, 0.99)
            border: Theme.strokeStrong

            ColumnLayout {
                id: menuColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: Theme.gap(1)
                spacing: 2

                Repeater {
                    model: App.printerList

                    Item {
                        id: entry
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: 46

                        readonly property bool current: modelData.name === App.printer

                        Rectangle {
                            anchors.fill: parent
                            radius: Theme.radiusSm
                            color: entry.current
                                   ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.18)
                                   : (entryArea.containsMouse ? Qt.rgba(1, 1, 1, 0.07)
                                                              : "transparent")
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: Theme.gap(1.25)
                            anchors.rightMargin: Theme.gap(1.25)
                            spacing: Theme.gap(1)

                            StatusDot {
                                tone: Theme.statusColor(entry.modelData.status)
                                size: 7
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Text {
                                    Layout.fillWidth: true
                                    text: entry.modelData.name
                                    elide: Text.ElideRight
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fsSmall
                                    font.weight: entry.current ? Font.DemiBold : Font.Normal
                                    color: Theme.text
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: {
                                        const bits = [entry.modelData.status_text]
                                        if (entry.modelData.is_default)
                                            bits.push("Windows default")
                                        if (entry.modelData.port)
                                            bits.push(entry.modelData.port)
                                        return bits.join("  |  ")
                                    }
                                    elide: Text.ElideRight
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fsTiny
                                    color: Theme.textFaint
                                }
                            }

                            Text {
                                visible: entry.current
                                text: Theme.icon.check
                                font.family: Theme.iconFamily
                                font.pixelSize: Theme.fsTiny
                                color: Theme.accent
                            }
                        }

                        MouseArea {
                            id: entryArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onEntered: Sfx.play("hover")
                            onClicked: {
                                Sfx.play("click")
                                App.selectPrinter(entry.modelData.name)
                                printerMenu.visible = false
                            }
                        }
                    }
                }
            }
        }
    }

    // ------------------------------------------------------------ resize grips
    // Frameless windows lose the system resize border, so eight grips are added
    // back. startSystemResize keeps the behaviour native, including the cursor
    // and the snap that follows a double click on an edge.
    Repeater {
        model: [
            { e: Qt.LeftEdge,                  cx: 0,  cy: 0.5, w: 6,  h: -1 },
            { e: Qt.RightEdge,                 cx: 1,  cy: 0.5, w: 6,  h: -1 },
            { e: Qt.TopEdge,                   cx: 0.5, cy: 0,  w: -1, h: 6 },
            { e: Qt.BottomEdge,                cx: 0.5, cy: 1,  w: -1, h: 6 },
            { e: Qt.LeftEdge | Qt.TopEdge,     cx: 0,  cy: 0,   w: 12, h: 12 },
            { e: Qt.RightEdge | Qt.TopEdge,    cx: 1,  cy: 0,   w: 12, h: 12 },
            { e: Qt.LeftEdge | Qt.BottomEdge,  cx: 0,  cy: 1,   w: 12, h: 12 },
            { e: Qt.RightEdge | Qt.BottomEdge, cx: 1,  cy: 1,   w: 12, h: 12 }
        ]

        MouseArea {
            required property var modelData

            width: modelData.w > 0 ? modelData.w : win.width
            height: modelData.h > 0 ? modelData.h : win.height
            x: (win.width - width) * modelData.cx
            y: (win.height - height) * modelData.cy
            z: 950
            visible: !win.maximised
            acceptedButtons: Qt.LeftButton
            hoverEnabled: true
            cursorShape: {
                const edge = modelData.e
                if (edge === Qt.LeftEdge || edge === Qt.RightEdge)
                    return Qt.SizeHorCursor
                if (edge === Qt.TopEdge || edge === Qt.BottomEdge)
                    return Qt.SizeVerCursor
                if (edge === (Qt.LeftEdge | Qt.TopEdge)
                        || edge === (Qt.RightEdge | Qt.BottomEdge))
                    return Qt.SizeFDiagCursor
                return Qt.SizeBDiagCursor
            }
            onPressed: win.startSystemResize(modelData.e)
        }
    }

    // ------------------------------------------------------------------ overlay
    ToastStack {
        id: toasts
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.gap(5.5)
        anchors.rightMargin: Theme.gap(2.5)
        width: 380
        height: Math.min(parent.height * 0.6, 320)
        z: 880
    }

    Modal {
        id: flipDialog
        title: "Flip the paper"
        acceptText: "Carry on"
        rejectText: "Stop here"
        glyph: Theme.icon.page
        tone: Theme.accent
        onAccepted: function (payload) { App.answerFlip(payload, true) }
        onRejected: function (payload) { App.answerFlip(payload, false) }
    }

    // --------------------------------------------------------------- intro
    Loader {
        id: introLoader
        anchors.fill: parent
        z: 1000
        active: App.getSetting("intro_enabled") !== false
        sourceComponent: Component {
            IntroSplash {
                appName: App.appName
                tagline: "Precision printing"
                soundEnabled: App.getSetting("sound_enabled") !== false
                             && App.getSetting("intro_sound") !== false
                Component.onCompleted: start()
                onDone: introLoader.active = false
            }
        }
    }

    // ------------------------------------------------------------ connections
    Connections {
        target: App
        function onToast(kind, message) { toasts.show(kind, message) }
        function onFlipRequested(jobId, title, message) {
            flipDialog.open({ title: title, message: message, payload: jobId,
                              glyph: Theme.icon.page, tone: Theme.accent })
        }
        function onBatchDone(done, failed, cancelled) {
            if (done > 0 && failed === 0 && win.currentTab === 0)
                return
        }
    }

    // Keyboard: the handful of shortcuts worth having.
    Item {
        anchors.fill: parent
        focus: true
        Keys.onPressed: function (event) {
            if (event.modifiers & Qt.ControlModifier) {
                switch (event.key) {
                case Qt.Key_P: App.start(); event.accepted = true; break
                case Qt.Key_O: printView.forceActiveFocus(); win.currentTab = 0
                               event.accepted = true; break
                case Qt.Key_L: win.currentTab = 1; event.accepted = true; break
                case Qt.Key_H: win.currentTab = 2; event.accepted = true; break
                case Qt.Key_Comma: win.currentTab = 3; event.accepted = true; break
                }
            } else if (event.key === Qt.Key_Space) {
                App.togglePause()
                event.accepted = true
            }
        }
    }

    // Window level drop target, so a drop anywhere counts, not only on the zone.
    DropArea {
        anchors.fill: parent
        z: 700
        onDropped: function (drop) {
            if (drop.hasUrls) {
                App.addUrls(drop.urls)
                drop.acceptProposedAction()
            }
        }
    }

    // ------------------------------------------------------------- lifecycle
    Component.onCompleted: {
        Sfx.backend = App
        Theme.dark = App.getSetting("theme") !== "light"
        Theme.accentHex = App.getSetting("accent") || "#5B8CFF"
        Theme.accent2Hex = App.getSetting("accent2") || "#B06BFF"
        Theme.blurStrength = App.getSetting("blur_strength")
        Theme.grainOpacity = App.getSetting("grain_opacity")
        Theme.animationsOn = App.getSetting("animations") !== false
        Theme.reduceMotion = App.getSetting("reduce_motion") === true
        Sfx.muted = App.getSetting("sound_enabled") === false
        App.applyWindowEffects()
    }

    onClosing: function (close) {
        App.setSetting("window_width", win.width)
        App.setSetting("window_height", win.height)
        App.shutdown()
    }
}
