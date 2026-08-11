"""Load the interface headlessly and fail on any QML problem.

QML is resolved at runtime, so a typo in a binding or a missing property is not a
build error, it is a warning printed at load and a piece of the interface silently
missing. This turns all of that into a non-zero exit code, and drives the app
through every tab and a real queue so the bindings that only run in those states
are exercised too.

Run: python tools/verify_ui.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

os.environ.setdefault("GLASSPRINT_SIMULATE", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> int:
    import make_test_pdf
    from PySide6.QtCore import QCoreApplication, QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    from app import APP_NAME, APP_ORG, APP_VERSION
    from app.core import env
    from app.core.settings import settings

    problems: list[str] = []
    # Binding loops and type errors are reported through the message handler
    # rather than the warnings signal, so both are collected.
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    def message_handler(mode, context, message) -> None:
        text = str(message)
        if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            # Environment noise rather than defects in this application. Each of
            # these is a property of the machine the check runs on, not of the
            # interface, and none of them is actionable from here:
            #
            #  - propertyCache fires for any QML type that redeclares an inherited
            #    name on purpose
            #  - the font directory warning only appears under the offscreen
            #    platform, which has no system fonts to fall back on; a real
            #    desktop session takes them from the OS
            #  - style and OpenGL notices come from headless CI graphics stacks
            ignorable = (
                "propertyCache.append",
                "Cannot find style",
                "QFontDatabase",
                "Qt no longer ships fonts",
                "Failed to create OpenGL context",
                "libpng warning",
            )
            if not any(hint in text for hint in ignorable):
                problems.append(text)
        print(text, file=sys.stderr)

    qInstallMessageHandler(message_handler)

    settings.set("intro_enabled", False)
    settings.set("sound_enabled", False)
    settings.set("restore_queue", False)

    QCoreApplication.setApplicationName(APP_NAME)
    QCoreApplication.setOrganizationName(APP_ORG)
    QCoreApplication.setApplicationVersion(APP_VERSION)
    app = QGuiApplication(sys.argv[:1])

    from app.bridge import Backend

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(env.qml_dir()))
    backend = Backend()
    engine.rootContext().setContextProperty("App", backend)
    engine.warnings.connect(
        lambda warnings: problems.extend(w.toString() for w in warnings)
    )
    engine.load(str(env.qml_dir() / "Main.qml"))

    roots = engine.rootObjects()
    if not roots:
        print("\nthe interface did not load at all")
        for problem in problems:
            print("  ", problem)
        return 1

    window = roots[0]
    window.resize(1280, 820)
    backend.setParent(window)

    tmp = ROOT / ".verify"
    tmp.mkdir(exist_ok=True)
    files = []
    for index in range(3):
        path = str(tmp / f"ui_{index}.pdf")
        make_test_pdf.build(path, 2)
        files.append(path)

    steps: list[tuple[int, str, object]] = []

    def add(delay: int, label: str, action) -> None:
        steps.append((delay, label, action))

    visited: list[str] = []

    def visit(tab: int, name: str):
        def run() -> None:
            window.setProperty("currentTab", tab)
            visited.append(name)

        return run

    # Queue some work first, so the states that only exist with jobs present are
    # built: progress bars, row actions, chips, the compact strip.
    add(200, "pause the runner", lambda: backend.runner.pause())
    add(300, "add files", lambda: backend.addPaths(files))
    add(900, "preview the first file", lambda: backend.requestPreview(files[0]))
    add(1500, "open the queue tab", visit(1, "queue"))
    add(2100, "open the history tab", visit(2, "history"))
    add(2700, "open the settings tab", visit(3, "settings"))
    add(3600, "back to the print tab", visit(0, "print"))
    add(4000, "toggle every quality preset", lambda: [
        backend.setOption("quality", value)
        for value in ("draft", "normal", "high", "hd", "photo")
    ])
    add(4200, "exercise the layout options", lambda: [
        backend.setOption("scale_mode", "custom"),
        backend.setOption("nup", 4),
        backend.setOption("borderless", True),
        backend.setOption("manual_duplex", True),
        backend.setOption("page_range", "1-2"),
        backend.setOption("page_subset", "odd"),
    ])
    add(4400, "switch printer", lambda: backend.selectPrinter(
        "Office Laser Duplex (Simulated)"))
    add(4700, "raise a toast", lambda: backend.toast.emit("good", "verification toast"))
    add(4900, "raise the flip dialog", lambda: backend.flipRequested.emit(
        "x", "Flip the paper", "This is the two sided prompt."))
    add(5300, "clear the queue", lambda: backend.clearQueue())
    add(5600, "reset the options", lambda: backend.resetOptions())

    for delay, label, action in steps:
        def wrapper(label=label, action=action):
            try:
                action()
            except Exception as exc:
                problems.append(f"step '{label}' raised: {exc}")

        QTimer.singleShot(delay, wrapper)

    QTimer.singleShot(6200, app.quit)
    app.exec()
    backend.shutdown()

    print("\nInterface verification")
    print(f"  tabs visited: {', '.join(visited) or 'none'}")
    print(f"  steps run: {len(steps)}")

    # De-duplicate: a binding warning inside a delegate repeats per row.
    unique: list[str] = []
    for problem in problems:
        if problem not in unique:
            unique.append(problem)

    if unique:
        print(f"\n{len(unique)} distinct QML problem(s):")
        for problem in unique:
            print("  -", problem)
        return 1

    print("\nno QML warnings, errors or binding loops")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
