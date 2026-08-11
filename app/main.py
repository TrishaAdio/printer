"""Entry point.

Builds the Qt application, exposes the backend to QML as ``App``, loads the
window and applies the Windows compositor effects once it exists.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `python app/main.py` work as well as `python -m app.main`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import APP_NAME, APP_ORG, APP_VERSION  # noqa: E402
from app.core import env  # noqa: E402
from app.core.logging_setup import setup as setup_logging  # noqa: E402
from app.core.settings import settings  # noqa: E402


def _configure_environment() -> None:
    """Qt hints that have to be set before the application object exists."""
    # Windows 10 with a translucent frameless window: the D3D11 backend handles
    # this correctly, and asking for it explicitly avoids falling back to
    # software rendering on machines with an unhelpful OpenGL driver.
    os.environ.setdefault("QSG_RHI_BACKEND", "d3d11" if env.IS_WINDOWS else "opengl")
    # Per monitor DPI awareness, so the glass stays crisp on a scaled display.
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    # Self test: load everything, confirm the interface built, then exit. The
    # packaged exe runs this in CI, which is what proves the bundle actually
    # contains the QML module and the assets rather than merely building.
    selftest = "--selftest" in argv
    if selftest:
        argv = [a for a in argv if a != "--selftest"]
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ["GLASSPRINT_SIMULATE"] = "1"

    _configure_environment()
    log = setup_logging()

    from PySide6.QtCore import QCoreApplication, QTimer
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine

    QCoreApplication.setApplicationName(APP_NAME)
    QCoreApplication.setOrganizationName(APP_ORG)
    QCoreApplication.setApplicationVersion(APP_VERSION)

    app = QGuiApplication(argv)
    icon_path = env.assets_dir() / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    from app.bridge import Backend
    from app.core.sounds import sounds

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(env.qml_dir()))

    backend = Backend()
    engine.rootContext().setContextProperty("App", backend)

    qml_main = env.qml_dir() / "Main.qml"
    if not qml_main.exists():
        log.error("cannot find %s", qml_main)
        return 2

    def on_warnings(warnings) -> None:
        for warning in warnings:
            log.warning("qml: %s", warning.toString())

    engine.warnings.connect(on_warnings)
    engine.load(str(qml_main))

    roots = engine.rootObjects()
    if not roots:
        log.error("the interface failed to load; see the warnings above")
        return 3

    window = roots[0]
    # The backend needs the window for the driver dialog's owner handle and for
    # the compositor effects, and it cannot exist before the window does.
    backend.setParent(window)

    def after_show() -> None:
        backend.applyWindowEffects()
        sounds.preload()
        if settings.get("restore_queue", True):
            restored = backend.runner.restore()
            if restored:
                backend.toast.emit(
                    "info",
                    f"{restored} unfinished job{'s' if restored != 1 else ''} "
                    "restored from last time",
                )
        if backend.simulated:
            backend.toast.emit(
                "warn",
                "No Windows printing available, running in simulation mode",
            )

    # One tick after the window is up: winId only exists once it has been shown.
    QTimer.singleShot(60, after_show)

    app.aboutToQuit.connect(backend.shutdown)
    log.info("%s %s started", APP_NAME, APP_VERSION)

    if selftest:
        checks: list[tuple[str, bool, str]] = []

        def report() -> None:
            from app.core import printers
            from app.core.printing import engine  # noqa: F401  (import must work)

            assets = env.assets_dir()
            checks.append(("window created", window is not None, type(window).__name__))
            checks.append(("qml module found", (env.qml_dir() / "Glass" / "qmldir").exists(),
                           str(env.qml_dir())))
            checks.append(("icon bundled", (assets / "icon.ico").exists(), str(assets)))
            checks.append(("grain bundled", (assets / "images" / "noise.png").exists(), ""))
            sound_count = len(list((assets / "sounds").glob("*.wav"))) if (
                assets / "sounds").is_dir() else 0
            checks.append((f"sounds bundled ({sound_count})", sound_count >= 8, ""))
            checks.append(("printer backend answered",
                           isinstance(printers.snapshot().get("printers"), list),
                           "simulated" if printers.IS_SIMULATED else "windows"))
            try:
                from PySide6.QtPdf import QPdfDocument  # noqa: F401

                pdf_ok = True
            except Exception as exc:  # pragma: no cover
                pdf_ok = False
                log.error("QtPdf missing from the bundle: %s", exc)
            checks.append(("QtPdf available", pdf_ok, ""))

            # Render and lay out a real document, without spooling anything. This
            # is the check that matters: it drives QtPdf, Pillow, the placement
            # maths and the engine through the packaged bundle rather than merely
            # confirming that imports resolve.
            try:
                from app.core import testpage
                from app.core.options import PrintOptions
                from app.core.printing import engine as print_engine

                probe = testpage.write_probe_pdf(str(env.cache_dir() / "selftest.pdf"))
                printer_name = printers.pick_printer()
                options = PrintOptions(printer=printer_name, dry_run=True, quality="high")
                outcome = print_engine.print_file(probe, options)
                checks.append((
                    "pdf rendered and laid out",
                    outcome.ok and outcome.sheets == 1,
                    f"{outcome.status}, {outcome.sheets} sheet at {outcome.dpi} dpi"
                    + (f", {outcome.error}" if outcome.error else ""),
                ))

                thumb = str(env.cache_dir() / "selftest.png")
                checks.append((
                    "preview thumbnail rendered",
                    print_engine.make_thumbnail(probe, thumb, 240)
                    and Path(thumb).exists(),
                    "",
                ))
            except Exception as exc:
                log.exception("self test rendering failed")
                checks.append(("pdf rendered and laid out", False, str(exc)))

            app.quit()

        QTimer.singleShot(1200, report)
        app.exec()

        print("\nGlassPrint self test")
        failed = 0
        for label, ok, detail in checks:
            print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
            failed += 0 if ok else 1
        print("self test passed" if not failed else f"{failed} check(s) failed")

        # Leave immediately rather than returning and unwinding.
        #
        # The packaged build reported every check as passing and then still exited
        # non-zero, because tearing down Qt after the event loop has already
        # finished can fault on Windows. That turned a successful verification into
        # a failed build. Everything worth checking has been checked by this point,
        # so the diagnostic path skips teardown entirely and reports its own
        # verdict. The normal path below still shuts down properly.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0 if not failed else 4)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
