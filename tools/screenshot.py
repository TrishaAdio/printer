"""Render the interface offscreen and save frames as PNG.

Development aid for checking layout and composition without a Windows machine.
Note that Segoe UI and Segoe MDL2 Assets do not exist off Windows, so text falls
back to another family and icon glyphs come out as empty boxes. Spacing, colour,
glass and alignment are all still meaningful.

Run: python tools/screenshot.py [outdir] [--tab N] [--no-intro] [--queue]
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
os.environ.setdefault("QSG_RHI_BACKEND", "opengl")


def main() -> int:
    args = list(sys.argv[1:])
    outdir = ROOT / ".verify" / "shots"
    positional = [a for a in args if not a.startswith("--")]
    if positional:
        outdir = Path(positional[0])
    outdir.mkdir(parents=True, exist_ok=True)

    want_intro = "--no-intro" not in args
    want_queue = "--queue" in args
    tab = 0
    for arg in args:
        if arg.startswith("--tab"):
            tab = int(arg.split("=")[-1]) if "=" in arg else 0

    from PySide6.QtCore import QCoreApplication, QTimer
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine

    from app import APP_NAME, APP_ORG, APP_VERSION
    from app.core import env
    from app.core.settings import settings

    settings.set("intro_enabled", want_intro)
    settings.set("sound_enabled", False)

    QCoreApplication.setApplicationName(APP_NAME)
    QCoreApplication.setOrganizationName(APP_ORG)
    QCoreApplication.setApplicationVersion(APP_VERSION)
    app = QGuiApplication(sys.argv[:1])
    icon = env.assets_dir() / "icon.ico"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    from app.bridge import Backend

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(env.qml_dir()))
    backend = Backend()
    engine.rootContext().setContextProperty("App", backend)
    engine.warnings.connect(
        lambda warnings: [print("QML:", w.toString()) for w in warnings]
    )
    engine.load(str(env.qml_dir() / "Main.qml"))
    roots = engine.rootObjects()
    if not roots:
        print("interface failed to load")
        return 1
    window = roots[0]
    backend.setParent(window)
    window.resize(1280, 820)

    shots: list[tuple[int, str]] = []
    if want_intro:
        shots += [(330, "intro_1_sweep"), (760, "intro_2_reveal"),
                  (1700, "intro_3_settled"), (2250, "intro_4_before_exit")]
    base = 3000 if want_intro else 500
    shots.append((base, f"tab{tab}_initial"))

    # The capture is started from QML: PySide cannot pass a QQuickItem into
    # Python, so Main.qml exposes grabFrame() for exactly this.
    def grab(name: str) -> None:
        path = outdir / f"{name}.png"
        try:
            if window.grabFrame(str(path)):
                print(f"  requested {path.name}")
            else:
                print(f"  {name}: grab refused")
        except Exception as exc:
            print("grab failed:", exc)

    for delay, name in shots:
        QTimer.singleShot(delay, lambda n=name: grab(n))

    if want_queue:
        import make_test_pdf


        files = []
        tmp = ROOT / ".verify"
        tmp.mkdir(exist_ok=True)
        for index in range(5):
            path = str(tmp / f"shot_{index}.pdf")
            make_test_pdf.build(path, 3)
            files.append(path)

        def queue_up() -> None:
            backend.runner.pause()
            backend.addPaths(files)
            backend.requestPreview(files[0])

        QTimer.singleShot(base + 200, queue_up)
        QTimer.singleShot(base + 2000, lambda: grab("tab0_with_queue"))
        QTimer.singleShot(base + 3000, lambda: window.setProperty("currentTab", 1))
        QTimer.singleShot(base + 4200, lambda: grab("tab1_queue"))
        QTimer.singleShot(base + 5200, lambda: window.setProperty("currentTab", 2))
        QTimer.singleShot(base + 6400, lambda: grab("tab2_history"))
        QTimer.singleShot(base + 7400, lambda: window.setProperty("currentTab", 3))
        QTimer.singleShot(base + 8600, lambda: grab("tab3_settings"))
        QTimer.singleShot(base + 9600, app.quit)
    else:
        if tab:
            QTimer.singleShot(base - 200, lambda: window.setProperty("currentTab", tab))
        QTimer.singleShot(base + 600, app.quit)

    print(f"writing frames to {outdir}")
    code = app.exec()
    backend.shutdown()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
