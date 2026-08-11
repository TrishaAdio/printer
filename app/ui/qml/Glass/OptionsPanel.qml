import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Glass

/*
 * Every print option the driver admits to supporting.
 *
 * Controls are driven by the capability report, not by a fixed list: a tray, a
 * media type or a resolution appears only if the printer actually offers it, and
 * options the device cannot do are disabled with the reason shown rather than
 * silently ignored. Anything not modelled here is still reachable through the
 * driver's own property sheet at the bottom.
 */
Item {
    id: root

    property var backend: null
    readonly property var opts: backend ? backend.options : ({})
    readonly property var caps: backend ? backend.caps : ({})

    function set(key, value) {
        if (backend)
            backend.setOption(key, value)
    }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        ColumnLayout {
            width: root.width - Theme.gap(2)
            spacing: Theme.gap(0.75)

            // ------------------------------------------------------- output
            SectionTitle { text: "Output"; glyph: Theme.icon.printer; first: true }

            SpinField {
                label: "Copies"
                value: root.opts.copies !== undefined ? root.opts.copies : 1
                minimum: 1
                maximum: 999
                hint: root.caps.max_copies !== undefined && root.opts.copies > root.caps.max_copies
                      ? "Above the driver's limit of " + root.caps.max_copies
                        + ", so the extras are printed as repeat passes"
                      : ""
                onEdited: function (v) { root.set("copies", v) }
            }

            ToggleField {
                label: "Collate"
                checked: root.opts.collate === true
                fieldEnabled: (root.opts.copies || 1) > 1
                hint: (root.opts.copies || 1) > 1 ? "" : "Only matters with more than one copy"
                onToggled: function (v) { root.set("collate", v) }
            }

            ToggleField {
                label: "Colour"
                checked: root.opts.color === true
                fieldEnabled: root.caps.color === true
                hint: root.caps.color === true ? "" : "This printer is monochrome"
                onToggled: function (v) { root.set("color", v) }
            }

            FieldRow {
                stretch: true
                label: "Quality"
                hint: {
                    const dpi = root.backend ? root.backend.effectiveDpi : 0
                    const max = root.caps.max_dpi !== undefined ? root.caps.max_dpi : 0
                    let text = "Rendering at " + dpi + " dpi"
                    if (max && dpi >= max)
                        text += ", the highest this printer reports"
                    return text
                }
                SegmentedControl {
                    Layout.fillWidth: true
                    options: [
                        { text: "Draft", value: "draft" },
                        { text: "Normal", value: "normal" },
                        { text: "High", value: "high" },
                        { text: "HD", value: "hd" },
                        { text: "Photo", value: "photo" }
                    ]
                    value: root.opts.quality !== undefined ? root.opts.quality : "normal"
                    onPicked: function (v) {
                        root.set("render_dpi", 0)
                        root.set("quality", v)
                    }
                }
            }

            ComboField {
                label: "Resolution"
                showEmpty: true
                emptyText: "Follow quality preset"
                items: {
                    const list = []
                    const res = root.caps.resolutions || []
                    for (let i = 0; i < res.length; i++)
                        list.push({ text: res[i].label, value: res[i].x })
                    return list
                }
                currentIndex: indexOfValue(root.opts.render_dpi || 0)
                onActivated: function (index) { root.set("render_dpi", valueAt(index)) }
            }

            FieldRow {
                stretch: true
                label: "Two sided"
                fieldEnabled: root.caps.duplex === true
                hint: root.caps.duplex === true
                      ? "" : "No automatic duplex on this printer, use the manual option below"
                SegmentedControl {
                    Layout.fillWidth: true
                    options: [
                        { text: "Off", value: "simplex" },
                        { text: "Long edge", value: "vertical" },
                        { text: "Short edge", value: "horizontal" }
                    ]
                    value: root.opts.duplex !== undefined ? root.opts.duplex : "simplex"
                    onPicked: function (v) { root.set("duplex", v) }
                }
            }

            ToggleField {
                label: "Manual duplex"
                checked: root.opts.manual_duplex === true
                hint: "Prints one side, waits for you to flip the stack, then prints the rest"
                onToggled: function (v) { root.set("manual_duplex", v) }
            }

            // -------------------------------------------------------- paper
            SectionTitle { text: "Paper"; glyph: Theme.icon.page }

            ComboField {
                label: "Size"
                showEmpty: true
                items: {
                    const list = []
                    const papers = root.caps.papers || []
                    for (let i = 0; i < papers.length; i++) {
                        const paper = papers[i]
                        let text = paper.name
                        if (paper.width_mm > 0)
                            text += "  (" + Math.round(paper.width_mm) + " x "
                                    + Math.round(paper.height_mm) + " mm)"
                        list.push({ text: text, value: paper.id })
                    }
                    return list
                }
                currentIndex: indexOfValue(root.opts.paper_size || 0)
                onActivated: function (index) { root.set("paper_size", valueAt(index)) }
            }

            ComboField {
                label: "Tray"
                showEmpty: true
                items: root.caps.bins || []
                currentIndex: indexOfValue(root.opts.paper_source || 0)
                onActivated: function (index) { root.set("paper_source", valueAt(index)) }
            }

            ComboField {
                label: "Media type"
                showEmpty: true
                items: root.caps.media_types || []
                currentIndex: indexOfValue(root.opts.media_type || 0)
                hint: root.opts.quality === "photo"
                      ? "Photo mode works best with a glossy or photo media type" : ""
                onActivated: function (index) { root.set("media_type", valueAt(index)) }
            }

            FieldRow {
                stretch: true
                label: "Orientation"
                SegmentedControl {
                    Layout.fillWidth: true
                    options: [
                        { text: "Auto", value: "auto" },
                        { text: "Portrait", value: "portrait" },
                        { text: "Landscape", value: "landscape" }
                    ]
                    value: root.opts.orientation !== undefined ? root.opts.orientation : "auto"
                    onPicked: function (v) { root.set("orientation", v) }
                }
            }

            ToggleField {
                label: "Full bleed"
                checked: root.opts.borderless === true
                hint: "Prints to the sheet edge. Needs borderless enabled in the driver, "
                      + "otherwise the driver crops the overflow"
                onToggled: function (v) { root.set("borderless", v) }
            }

            SliderField {
                label: "Extra margin"
                value: root.opts.extra_margin_mm !== undefined ? root.opts.extra_margin_mm : 0
                minimum: 0
                maximum: 25
                percent: false
                decimals: 1
                display: (root.opts.extra_margin_mm || 0).toFixed(1) + " mm"
                onMoved: function (v) { root.set("extra_margin_mm", v) }
            }

            // ------------------------------------------------------- layout
            SectionTitle { text: "Layout"; glyph: Theme.icon.tune }

            FieldRow {
                stretch: true
                label: "Scaling"
                hint: root.opts.scale_mode === "fill"
                      ? "Fills the page and crops what does not fit"
                      : (root.opts.scale_mode === "actual"
                         ? "Keeps the document's real size, whatever the paper" : "")
                SegmentedControl {
                    Layout.fillWidth: true
                    options: [
                        { text: "Fit", value: "fit" },
                        { text: "Fill", value: "fill" },
                        { text: "Actual", value: "actual" },
                        { text: "Custom", value: "custom" }
                    ]
                    value: root.opts.scale_mode !== undefined ? root.opts.scale_mode : "fit"
                    onPicked: function (v) { root.set("scale_mode", v) }
                }
            }

            SpinField {
                label: "Scale"
                visible: root.opts.scale_mode === "custom"
                value: root.opts.scale_percent !== undefined ? root.opts.scale_percent : 100
                minimum: 10
                maximum: 400
                step: 5
                suffix: "%"
                onEdited: function (v) { root.set("scale_percent", v) }
            }

            ComboField {
                label: "Pages per sheet"
                items: {
                    const list = []
                    const choices = root.backend ? root.backend.nupChoices : [1, 2, 4, 9]
                    for (let i = 0; i < choices.length; i++) {
                        list.push({ text: choices[i] === 1 ? "1  (normal)" : String(choices[i]),
                                    value: choices[i] })
                    }
                    return list
                }
                currentIndex: indexOfValue(root.opts.nup || 1)
                onActivated: function (index) { root.set("nup", valueAt(index)) }
            }

            ToggleField {
                label: "Auto rotate"
                checked: root.opts.auto_rotate === true
                hint: "Turns landscape pages to match the sheet"
                onToggled: function (v) { root.set("auto_rotate", v) }
            }

            ToggleField {
                label: "Sharpen"
                checked: root.opts.sharpen === true
                hint: "Helps low resolution scans and photos that have been enlarged"
                onToggled: function (v) { root.set("sharpen", v) }
            }

            ToggleField {
                label: "Render as grey"
                checked: root.opts.force_grayscale_render === true
                hint: "Converts before sending, rather than leaving it to the driver"
                onToggled: function (v) { root.set("force_grayscale_render", v) }
            }

            // -------------------------------------------------------- pages
            SectionTitle { text: "Pages"; glyph: Theme.icon.document }

            TextField {
                id: rangeField
                label: "Range"
                text: root.opts.page_range !== undefined ? root.opts.page_range : ""
                placeholder: "all pages"
                monospace: true
                hint: "Examples: 1-5   2,4,9   7-  (to the end)"
                onEdited: function (v) { root.set("page_range", v) }
            }

            FieldRow {
                stretch: true
                label: "Only"
                SegmentedControl {
                    Layout.fillWidth: true
                    options: [
                        { text: "All pages", value: "all" },
                        { text: "Odd", value: "odd" },
                        { text: "Even", value: "even" }
                    ]
                    value: root.opts.page_subset !== undefined ? root.opts.page_subset : "all"
                    onPicked: function (v) { root.set("page_subset", v) }
                }
            }

            ToggleField {
                label: "Reverse order"
                checked: root.opts.reverse === true
                onToggled: function (v) { root.set("reverse", v) }
            }

            // --------------------------------------------------- text files
            SectionTitle { text: "Text files"; glyph: Theme.icon.text }

            ComboField {
                label: "Font"
                items: ["Consolas", "Courier New", "Cascadia Mono", "Segoe UI", "Arial",
                        "Times New Roman"]
                currentIndex: {
                    const names = ["Consolas", "Courier New", "Cascadia Mono", "Segoe UI",
                                   "Arial", "Times New Roman"]
                    const current = root.opts.text_font
                    const found = names.indexOf(current)
                    return found >= 0 ? found : 0
                }
                onActivated: function (index) {
                    const names = ["Consolas", "Courier New", "Cascadia Mono", "Segoe UI",
                                   "Arial", "Times New Roman"]
                    root.set("text_font", names[index])
                }
            }

            SpinField {
                label: "Size"
                value: Math.round(root.opts.text_point_size !== undefined
                                  ? root.opts.text_point_size : 10)
                minimum: 5
                maximum: 48
                suffix: "pt"
                onEdited: function (v) { root.set("text_point_size", v) }
            }

            ToggleField {
                label: "Header"
                checked: root.opts.text_header === true
                hint: "File name and page numbers at the top of each page"
                onToggled: function (v) { root.set("text_header", v) }
            }

            ToggleField {
                label: "Wrap lines"
                checked: root.opts.text_wrap === true
                hint: "Off means long lines are clipped at the margin"
                onToggled: function (v) { root.set("text_wrap", v) }
            }

            // ----------------------------------------------------- advanced
            SectionTitle { text: "Advanced"; glyph: Theme.icon.settings }

            ToggleField {
                label: "Dry run"
                checked: root.opts.dry_run === true
                hint: "Renders everything and reports timings without using paper"
                onToggled: function (v) { root.set("dry_run", v) }
            }

            Item {
                Layout.fillWidth: true
                Layout.topMargin: Theme.gap(0.5)
                implicitHeight: driverRow.implicitHeight

                ColumnLayout {
                    id: driverRow
                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: Theme.gap(1)

                    Text {
                        Layout.fillWidth: true
                        text: "Anything this panel does not cover lives in the printer's own "
                              + "settings. Changes made there apply to jobs from GlassPrint."
                        wrapMode: Text.WordWrap
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsTiny
                        color: Theme.textFaint
                        lineHeight: 1.35
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.gap(1)

                        GlassButton {
                            text: "Printer settings"
                            glyph: Theme.icon.settings
                            enabled: root.backend && !root.backend.simulated
                            onClicked: root.backend.openDriverProperties()
                        }
                        GlassButton {
                            text: "Reset"
                            subtle: true
                            onClicked: root.backend.resetOptions()
                        }
                        Item { Layout.fillWidth: true }
                    }
                }
            }

            Item { Layout.preferredHeight: Theme.gap(2) }
        }
    }
}
