import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Glass

/*
 * Appearance, sound, behaviour and the printer level actions that belong to the
 * device rather than to a job.
 */
Item {
    id: root

    property var backend: null

    function get(key, fallback) {
        if (!backend)
            return fallback
        const value = backend.getSetting(key)
        return value === undefined || value === null ? fallback : value
    }

    function set(key, value) {
        if (backend)
            backend.setSetting(key, value)
    }

    property int revision: 0
    Connections {
        target: root.backend
        function onSettingsChanged() { root.revision++ }
    }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            width: root.width - Theme.gap(2)
            spacing: Theme.gap(1.5)

            // =========================================================== look
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: appearance.implicitHeight + Theme.gap(4)
                radius: Theme.radiusXl
                elevation: 0.8
                sweepOnHover: false

                ColumnLayout {
                    id: appearance
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: Theme.gap(2)
                    spacing: Theme.gap(0.75)

                    SectionTitle { text: "Appearance"; glyph: Theme.icon.colour; first: true }

                    FieldRow {
                        stretch: true
                        label: "Accent"
                        hint: "Drives the glow behind the glass and every highlight"
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.gap(1)

                            Repeater {
                                model: [
                                    { a: "#5B8CFF", b: "#B06BFF", name: "Indigo" },
                                    { a: "#33C4FF", b: "#3DE0C0", name: "Lagoon" },
                                    { a: "#FF7A59", b: "#FFB454", name: "Ember" },
                                    { a: "#FF5C8A", b: "#B06BFF", name: "Orchid" },
                                    { a: "#4ADE80", b: "#33C4FF", name: "Mint" },
                                    { a: "#94A3B8", b: "#CBD5E1", name: "Graphite" }
                                ]

                                Item {
                                    id: swatch
                                    required property var modelData
                                    implicitWidth: 34
                                    implicitHeight: 26

                                    readonly property bool current:
                                        root.get("accent", "#5B8CFF") === modelData.a

                                    Rectangle {
                                        anchors.fill: parent
                                        radius: Theme.radiusSm
                                        gradient: Gradient {
                                            orientation: Gradient.Horizontal
                                            GradientStop { position: 0.0; color: swatch.modelData.a }
                                            GradientStop { position: 1.0; color: swatch.modelData.b }
                                        }
                                        border.width: swatch.current ? 2 : Theme.hairline
                                        border.color: swatch.current
                                                      ? "#FFFFFF" : Qt.rgba(1, 1, 1, 0.25)
                                        scale: swatchArea.containsMouse ? 1.08 : 1.0
                                        Behavior on scale {
                                            NumberAnimation { duration: Theme.ms(Theme.fast) }
                                        }
                                    }

                                    MouseArea {
                                        id: swatchArea
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onEntered: Sfx.play("hover")
                                        onClicked: {
                                            Sfx.play("click")
                                            root.set("accent", swatch.modelData.a)
                                            root.set("accent2", swatch.modelData.b)
                                            Theme.accentHex = swatch.modelData.a
                                            Theme.accent2Hex = swatch.modelData.b
                                        }
                                    }
                                }
                            }

                            Item { Layout.fillWidth: true }
                        }
                    }

                    FieldRow {
                        label: "Theme"
                        SegmentedControl {
                            options: [
                                { text: "Dark", value: "dark" },
                                { text: "Light", value: "light" }
                            ]
                            value: root.get("theme", "dark")
                            onPicked: function (v) {
                                root.set("theme", v)
                                Theme.dark = (v === "dark")
                            }
                        }
                    }

                    ToggleField {
                        label: "Blur the desktop"
                        checked: root.get("desktop_blur", true) === true
                        hint: root.backend
                              ? "Windows is currently applying: " + root.backend.windowEffect
                              : ""
                        onToggled: function (v) { root.set("desktop_blur", v) }
                    }

                    FieldRow {
                        label: "Blur style"
                        fieldEnabled: root.get("desktop_blur", true) === true
                        hint: "Acrylic is richer but can stutter while dragging on Windows 10"
                        SegmentedControl {
                            options: [
                                { text: "Smooth", value: "blur" },
                                { text: "Acrylic", value: "acrylic" }
                            ]
                            value: root.get("acrylic_mode", "blur")
                            onPicked: function (v) { root.set("acrylic_mode", v) }
                        }
                    }

                    SliderField {
                        label: "Glow strength"
                        value: root.get("blur_strength", 0.85)
                        minimum: 0.15
                        maximum: 1.0
                        onMoved: function (v) {
                            Theme.blurStrength = v
                        }
                        onReleased: root.set("blur_strength", Theme.blurStrength)
                    }

                    SliderField {
                        label: "Grain"
                        value: root.get("grain_opacity", 0.045)
                        minimum: 0.0
                        maximum: 0.12
                        display: Math.round((root.get("grain_opacity", 0.045) / 0.12) * 100) + "%"
                        onMoved: function (v) { Theme.grainOpacity = v }
                        onReleased: root.set("grain_opacity", Theme.grainOpacity)
                    }

                    ToggleField {
                        label: "Animations"
                        checked: root.get("animations", true) === true
                        onToggled: function (v) {
                            root.set("animations", v)
                            Theme.animationsOn = v
                        }
                    }

                    ToggleField {
                        label: "Reduce motion"
                        checked: root.get("reduce_motion", false) === true
                        hint: "Keeps state changes instant, for motion sensitivity"
                        onToggled: function (v) {
                            root.set("reduce_motion", v)
                            Theme.reduceMotion = v
                        }
                    }

                    ToggleField {
                        label: "Opening titles"
                        checked: root.get("intro_enabled", true) === true
                        hint: "The animation when the app starts"
                        onToggled: function (v) { root.set("intro_enabled", v) }
                    }
                }
            }

            // ========================================================== sound
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: audio.implicitHeight + Theme.gap(4)
                radius: Theme.radiusXl
                elevation: 0.8
                sweepOnHover: false

                ColumnLayout {
                    id: audio
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: Theme.gap(2)
                    spacing: Theme.gap(0.75)

                    SectionTitle { text: "Sound"; glyph: Theme.icon.sound; first: true }

                    ToggleField {
                        label: "Sound effects"
                        checked: root.get("sound_enabled", true) === true
                        onToggled: function (v) {
                            root.set("sound_enabled", v)
                            Sfx.muted = !v
                            if (v)
                                Sfx.play("click")
                        }
                    }

                    ToggleField {
                        label: "Opening sting"
                        checked: root.get("intro_sound", true) === true
                        fieldEnabled: root.get("sound_enabled", true) === true
                        onToggled: function (v) { root.set("intro_sound", v) }
                    }

                    SliderField {
                        label: "Volume"
                        fieldEnabled: root.get("sound_enabled", true) === true
                        value: root.get("sound_volume", 0.55)
                        minimum: 0
                        maximum: 1
                        onMoved: function (v) { root.set("sound_volume", v) }
                        onReleased: Sfx.play("toast")
                    }

                    FieldRow {
                        stretch: true
                        label: "Try them"
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.gap(0.75)
                            Repeater {
                                model: ["intro", "click", "drop", "start", "complete", "error"]
                                GlassButton {
                                    required property string modelData
                                    text: modelData
                                    horizontalPadding: Theme.gap(1.25)
                                    onClicked: root.backend.playSound(modelData)
                                }
                            }
                            Item { Layout.fillWidth: true }
                        }
                    }
                }
            }

            // ====================================================== behaviour
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: behaviour.implicitHeight + Theme.gap(4)
                radius: Theme.radiusXl
                elevation: 0.8
                sweepOnHover: false

                ColumnLayout {
                    id: behaviour
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: Theme.gap(2)
                    spacing: Theme.gap(0.75)

                    SectionTitle { text: "Behaviour"; glyph: Theme.icon.tune; first: true }

                    ToggleField {
                        label: "Walk folders"
                        checked: root.get("recursive_folders", true) === true
                        hint: "Dropping a folder also picks up everything in its subfolders"
                        onToggled: function (v) { root.set("recursive_folders", v) }
                    }

                    ToggleField {
                        label: "Restore the queue"
                        checked: root.get("restore_queue", true) === true
                        hint: "Unfinished jobs come back after a restart or a crash"
                        onToggled: function (v) { root.set("restore_queue", v) }
                    }

                    SpinField {
                        label: "Warn above"
                        value: root.get("confirm_over_pages", 50)
                        minimum: 0
                        maximum: 5000
                        step: 10
                        suffix: "files"
                        hint: "Asks before starting a batch this large. Zero never asks"
                        onEdited: function (v) { root.set("confirm_over_pages", v) }
                    }

                    SpinField {
                        label: "Keep history"
                        value: root.get("history_days", 90)
                        minimum: 0
                        maximum: 3650
                        step: 30
                        suffix: "days"
                        hint: "Older entries are pruned at startup. Zero keeps everything"
                        onEdited: function (v) { root.set("history_days", v) }
                    }
                }
            }

            // ======================================================== printer
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: device.implicitHeight + Theme.gap(4)
                radius: Theme.radiusXl
                elevation: 0.8
                sweepOnHover: false

                ColumnLayout {
                    id: device
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: Theme.gap(2)
                    spacing: Theme.gap(1)

                    SectionTitle { text: "Printer"; glyph: Theme.icon.printer; first: true }

                    Text {
                        Layout.fillWidth: true
                        text: {
                            if (!root.backend)
                                return ""
                            const caps = root.backend.caps
                            const bits = []
                            if (caps.driver)
                                bits.push(caps.driver)
                            if (caps.port)
                                bits.push("on " + caps.port)
                            if (caps.max_dpi)
                                bits.push("up to " + caps.max_dpi + " dpi")
                            bits.push(caps.color ? "colour" : "monochrome")
                            bits.push(caps.duplex ? "auto duplex" : "single sided")
                            if (caps.print_rate_ppm)
                                bits.push(caps.print_rate_ppm + " ppm")
                            return bits.join("  |  ")
                        }
                        wrapMode: Text.WordWrap
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsSmall
                        color: Theme.textDim
                    }

                    Text {
                        Layout.fillWidth: true
                        visible: text !== ""
                        text: {
                            if (!root.backend)
                                return ""
                            const notes = root.backend.caps.notes || []
                            return notes.join("\n")
                        }
                        wrapMode: Text.WordWrap
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsTiny
                        color: Theme.warn
                    }

                    Flow {
                        Layout.fillWidth: true
                        spacing: Theme.gap(1)

                        GlassButton {
                            text: "Print a test page"
                            glyph: Theme.icon.print
                            onClicked: root.backend.printTestPage()
                        }
                        GlassButton {
                            text: "Printer settings"
                            glyph: Theme.icon.settings
                            enabled: root.backend && !root.backend.simulated
                            onClicked: root.backend.openDriverProperties()
                        }
                        GlassButton {
                            text: "Make default"
                            onClicked: root.backend.makeDefaultPrinter()
                        }
                        GlassButton {
                            text: "Windows queue"
                            glyph: Theme.icon.queue
                            enabled: root.backend && !root.backend.simulated
                            onClicked: root.backend.openWindowsQueue()
                        }
                        GlassButton {
                            text: "Pause device"
                            onClicked: root.backend.pausePrinter()
                        }
                        GlassButton {
                            text: "Resume device"
                            onClicked: root.backend.resumePrinter()
                        }
                        GlassButton {
                            text: "Purge device queue"
                            danger: true
                            onClicked: root.backend.purgePrinter()
                        }
                    }
                }
            }

            // ========================================================== about
            GlassCard {
                Layout.fillWidth: true
                Layout.preferredHeight: about.implicitHeight + Theme.gap(4)
                radius: Theme.radiusXl
                elevation: 0.8
                sweepOnHover: false

                ColumnLayout {
                    id: about
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: Theme.gap(2)
                    spacing: Theme.gap(1)

                    SectionTitle { text: "About"; glyph: Theme.icon.info; first: true }

                    Text {
                        Layout.fillWidth: true
                        text: root.backend
                              ? root.backend.appName + " " + root.backend.version + "\n"
                                + root.backend.platformNote
                              : ""
                        wrapMode: Text.WordWrap
                        lineHeight: 1.4
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsSmall
                        color: Theme.textDim
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.gap(1)

                        GlassButton {
                            text: "Open log folder"
                            glyph: Theme.icon.openFolder
                            onClicked: root.backend.openLogFolder()
                        }
                        GlassButton {
                            text: "Reset all settings"
                            danger: true
                            onClicked: resetConfirm.open()
                        }
                        Item { Layout.fillWidth: true }
                    }
                }
            }

            Item { Layout.preferredHeight: Theme.gap(2) }
        }
    }

    Modal {
        id: resetConfirm
        title: "Reset every setting?"
        message: "Appearance, sound and print defaults all go back to how they shipped. "
                 + "Your history and anything queued are left alone."
        acceptText: "Reset"
        glyph: Theme.icon.warning
        tone: Theme.warn
        onAccepted: root.backend.resetSettings()
    }
}
