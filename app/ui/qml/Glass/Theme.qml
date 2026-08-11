pragma Singleton
import QtQuick

/*
 * The whole design system in one place: palette, spacing scale, radii, type,
 * motion. Nothing in the interface should hard code a colour or a duration.
 *
 * Two rules keep the layout honest:
 *   - every gap is a multiple of `unit` (8), so nothing is ever "almost" aligned
 *   - every border and hairline is snapped with Math.round, because a half pixel
 *     border is what makes glass look blurry rather than crisp
 */
QtObject {
    id: theme

    // ------------------------------------------------------------ preferences
    property bool dark: true
    property string accentHex: "#5B8CFF"
    property string accent2Hex: "#B06BFF"
    property real blurStrength: 0.85
    property real grainOpacity: 0.045
    property bool animationsOn: true
    property bool reduceMotion: false

    // ----------------------------------------------------------------- colours
    readonly property color accent: accentHex
    readonly property color accent2: accent2Hex

    readonly property color bg: dark ? "#0B0D14" : "#EEF1F8"
    readonly property color bgDeep: dark ? "#070910" : "#E2E7F2"
    readonly property color text: dark ? "#EEF1F8" : "#151824"
    readonly property color textDim: dark ? "#9AA3B8" : "#5B6478"
    readonly property color textFaint: dark ? "#6B7488" : "#8A93A8"

    // Glass surfaces are white at low alpha over the blurred backdrop. Raising
    // alpha rather than lightening the colour keeps the backdrop showing through.
    readonly property color glass: dark ? Qt.rgba(1, 1, 1, 0.055) : Qt.rgba(1, 1, 1, 0.62)
    readonly property color glassHover: dark ? Qt.rgba(1, 1, 1, 0.085) : Qt.rgba(1, 1, 1, 0.78)
    readonly property color glassSunken: dark ? Qt.rgba(0, 0, 0, 0.22) : Qt.rgba(1, 1, 1, 0.45)
    readonly property color stroke: dark ? Qt.rgba(1, 1, 1, 0.13) : Qt.rgba(255, 255, 255, 0.9)
    readonly property color strokeStrong: dark ? Qt.rgba(1, 1, 1, 0.22) : Qt.rgba(0, 0, 0, 0.10)
    // The lit top edge that reads as a bevel on a pane of glass.
    readonly property color highlight: dark ? Qt.rgba(1, 1, 1, 0.28) : Qt.rgba(1, 1, 1, 1.0)

    readonly property color good: "#3DD68C"
    readonly property color warn: "#FFB454"
    readonly property color bad: "#FF6B7A"
    readonly property color info: accent

    function statusColor(kind) {
        switch (kind) {
        case "ready": return good
        case "busy": return accent
        case "warning": case "warn": return warn
        case "paused": return warn
        case "error": case "bad": return bad
        case "offline": return textFaint
        case "good": return good
        default: return textDim
        }
    }

    function jobColor(status) {
        switch (status) {
        case "done": return good
        case "failed": return bad
        case "running": return accent
        case "cancelled": case "skipped": return textFaint
        default: return textDim
        }
    }

    // ------------------------------------------------------------- dimensions
    readonly property int unit: 8
    function gap(n) { return unit * n }

    readonly property int radiusSm: 8
    readonly property int radiusMd: 12
    readonly property int radiusLg: 18
    readonly property int radiusXl: 24
    readonly property int windowRadius: 14

    readonly property int rowHeight: 38
    readonly property int labelWidth: 112
    readonly property int controlHeight: 34
    readonly property int titleBarHeight: 46
    readonly property int hairline: 1

    // ------------------------------------------------------------------- type
    readonly property string fontFamily: "Segoe UI"
    readonly property string monoFamily: "Consolas"
    readonly property int fsDisplay: 30
    readonly property int fsTitle: 19
    readonly property int fsHeading: 15
    readonly property int fsBody: 13
    readonly property int fsSmall: 12
    readonly property int fsTiny: 11

    // ----------------------------------------------------------------- motion
    readonly property int fast: 120
    readonly property int normal: 200
    readonly property int slow: 340
    readonly property int lazy: 640

    // Single gate for every animation, so the accessibility switch is honoured
    // everywhere without each component remembering to check it.
    function ms(duration) {
        if (!animationsOn || reduceMotion)
            return 0
        return duration
    }

    readonly property int easeOut: Easing.OutCubic
    readonly property int easeInOut: Easing.InOutQuad
    readonly property int easeBack: Easing.OutBack

    // ------------------------------------------------------------------ icons
    // Segoe MDL2 Assets ships with Windows 10, which is the target, so the icon
    // set costs nothing to bundle and matches the rest of the system. On other
    // platforms these fall back to empty boxes, which only affects development.
    readonly property string iconFamily: "Segoe MDL2 Assets"
    readonly property var icon: ({
        "print":     "\uE749",
        "add":       "\uE710",
        "folder":    "\uE8B7",
        "openFolder":"\uE838",
        "refresh":   "\uE72C",
        "settings":  "\uE713",
        "history":   "\uE81C",
        "delete":    "\uE74D",
        "close":     "\uE711",
        "minimise":  "\uE921",
        "maximise":  "\uE922",
        "restore":   "\uE923",
        "play":      "\uE768",
        "pause":     "\uE769",
        "stop":      "\uE71A",
        "up":        "\uE70E",
        "down":      "\uE70D",
        "check":     "\uE73E",
        "warning":   "\uE7BA",
        "error":     "\uEA39",
        "info":      "\uE946",
        "document":  "\uE8A5",
        "image":     "\uEB9F",
        "text":      "\uE8A5",
        "queue":     "\uE71D",
        "printer":   "\uE749",
        "view":      "\uE890",
        "more":      "\uE712",
        "tune":      "\uE9E9",
        "page":      "\uE7C3",
        "colour":    "\uE790",
        "sound":     "\uE767",
        "sparkle":   "\uE945"
    })

    function snap(value) { return Math.round(value) }

    function elide(value, limit) {
        if (!value)
            return ""
        return value.length > limit ? value.substring(0, limit - 1) + "\u2026" : value
    }
}
