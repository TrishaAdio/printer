# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for GlassPrint.

Builds a directory distribution by default, or a single file when
GLASSPRINT_ONEFILE=1. The directory build is what the installer ships because it
starts immediately; the single file build is the portable copy, which has to
unpack itself into a temp folder on every launch and is noticeably slower.

Run from the repository root:

    pyinstaller build/glassprint.spec --noconfirm
    set GLASSPRINT_ONEFILE=1 && pyinstaller build/glassprint.spec --noconfirm
"""

import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
ONEFILE = os.environ.get("GLASSPRINT_ONEFILE", "") not in ("", "0", "false", "False")
NAME = "GlassPrint"

sys.path.insert(0, str(ROOT))

# Assets and QML are loaded at runtime by path, so they travel as data with the
# same layout the source tree has. app.core.env resolves them relative to
# sys._MEIPASS/app, which holds for both onedir and onefile.
datas = [
    (str(ROOT / "app" / "assets"), "app/assets"),
    (str(ROOT / "app" / "ui" / "qml"), "app/ui/qml"),
]

hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickControls2",
    "PySide6.QtPdf",
    "PySide6.QtMultimedia",
    "PySide6.QtNetwork",
]

if sys.platform.startswith("win"):
    # Imported lazily inside the printing backend, so PyInstaller cannot see them
    # by following imports. Only listed on Windows; elsewhere they do not exist and
    # would just fill the build log with errors.
    hiddenimports += [
        "win32print", "win32ui", "win32gui", "win32api", "win32con",
        "pythoncom", "pywintypes",
    ]

# Trimming the parts of Qt this app never touches. Without this the bundle
# carries WebEngine, 3D, charts and the rest, which triples the download for no
# benefit. QtQuick, QtPdf and QtMultimedia are deliberately absent from the list.
excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtWebView",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtGraphsWidgets", "PySide6.QtQuick3D", "PySide6.QtQuick3DHelpers",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSerialPort", "PySide6.QtSerialBus",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSensors",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtStateMachine",
    "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools",
    "PySide6.QtHttpServer", "PySide6.QtNetworkAuth", "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech", "PySide6.QtSql", "PySide6.QtDBus",
    "PySide6.QtOpenGLWidgets", "PySide6.QtSvgWidgets",
    "PySide6.QtPrintSupport", "PySide6.QtQuickWidgets",
    "PySide6.QtConcurrent", "PySide6.QtXml",
    # Deliberately NOT excluded, even though this app never imports them:
    # PySide6.QtQuick's binding links against QtOpenGL, and QtQuickControls2
    # against QtWidgets. Excluding either breaks `import PySide6.QtQuick` inside
    # the frozen build with a libshiboken import error, which is not obvious from
    # the build log and only shows up when the exe is run.
    # Not a Qt app for these:
    "tkinter", "unittest", "pydoc", "doctest", "pdb", "lib2to3", "distutils",
    "numpy", "scipy", "pandas", "matplotlib", "setuptools", "pip",
]

block_cipher = None

analysis = Analysis(
    [str(ROOT / "app" / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# --------------------------------------------------------------------------- #
# Pruning.
#
# Excluding a Python module does not stop PyInstaller's PySide6 hook collecting
# the matching Qt libraries, plugins and QML modules: it sweeps the whole Qt
# tree. Left alone that produces a bundle of roughly 690 MB, most of it a 194 MB
# WebEngine that this app never loads. So the collected lists are filtered by
# hand afterwards.
#
# The rule is conservative on purpose. Anything Qt Quick, Qt Qml, Qt Pdf or the
# Windows multimedia backend might reach for is kept, and the self test in CI
# runs the packaged exe, so a prune that removes something needed fails the build
# instead of shipping.
# --------------------------------------------------------------------------- #

#: Whole Qt features that are not part of this app. Matched against the file name,
#: case insensitively, so it covers Qt6WebEngineCore.dll and libQt6WebEngineCore.so
#: alike.
DROP_TOKENS = (
    "webengine", "webchannel", "websockets", "webview",
    "quick3d", "qt63dcore", "qt63drender", "qt63dinput", "qt63dlogic",
    "qt63danimation", "qt63dextras", "qt63dquick",
    "charts", "datavisualization", "qt6graphs",
    "location", "positioning", "sensors", "nfc", "bluetooth",
    "serialport", "serialbus", "remoteobjects", "scxml", "statemachine",
    "qt6test", "designer", "qt6help", "uitools", "httpserver", "networkauth",
    "spatialaudio", "texttospeech", "virtualkeyboard", "wayland",
    "qt6quickwidgets", "qt6multimediawidgets", "qt6pdfwidgets",
    "qt5compat", "quickeffectmaker", "qt6quicktimeline",
    # The ffmpeg media backend is about 40 MB and is only one of the two
    # multimedia backends. Windows has its own, which is what QSoundEffect uses,
    # and main.py asks for it explicitly.
    "avcodec", "avformat", "avutil", "swresample", "swscale", "ffmpeg",
)

#: Directories under Qt's qml tree to drop wholesale.
DROP_QML_DIRS = (
    "QtQuick3D", "Qt3D", "QtCharts", "QtDataVisualization", "QtGraphs",
    "QtWebEngine", "QtWebView", "QtWebChannel", "QtWebSockets",
    "QtLocation", "QtPositioning", "QtSensors", "QtNfc", "QtBluetooth",
    "QtRemoteObjects", "QtScxml", "QtStateMachine", "QtTest", "QtWayland",
    "Qt5Compat", "QtTextToSpeech", "QtSpatialAudio", "QtMultimedia",
    "QtQuick/VirtualKeyboard", "QtQuick/Scene2D", "QtQuick/Scene3D",
    "QtQuick/Particles", "QtQuick/LocalStorage", "QtQuick/Timeline",
    "QtQuick/Pdf", "QtCore", "QtQuick/tooling",
)


def _drops(dest: str) -> bool:
    unified = dest.replace("\\", "/")
    lowered = unified.lower()
    name = os.path.basename(lowered)

    if any(token in name for token in DROP_TOKENS):
        return True

    # QML modules live under .../qml/<Module>/...
    marker = "/qml/"
    if marker in unified:
        tail = unified.split(marker, 1)[1]
        for folder in DROP_QML_DIRS:
            if tail == folder or tail.startswith(folder + "/"):
                return True

    # Translations for languages the app does not ship in.
    if "/translations/" in lowered and lowered.endswith(".qm"):
        return True
    return False


def prune(entries, label):
    kept = [entry for entry in entries if not _drops(entry[0])]
    removed = len(entries) - len(kept)
    print(f"[glassprint] pruned {removed} of {len(entries)} {label} entries")
    return kept


analysis.binaries = prune(analysis.binaries, "binary")
analysis.datas = prune(analysis.datas, "data")

pyz = PYZ(analysis.pure, analysis.zipped_data, cipher=block_cipher)

icon_path = str(ROOT / "app" / "assets" / "icon.ico")
version_file = str(ROOT / "build" / "version_info.txt")

if ONEFILE:
    exe = EXE(
        pyz,
        analysis.scripts,
        analysis.binaries,
        analysis.zipfiles,
        analysis.datas,
        [],
        name=f"{NAME}-portable",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        # UPX is off on purpose: it saves a few megabytes and in exchange gets the
        # exe flagged by more than one antivirus engine, which is a bad trade for
        # something a user has to be talked into running past SmartScreen already.
        upx=False,
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_path,
        version=version_file,
    )
else:
    exe = EXE(
        pyz,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name=NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_path,
        version=version_file,
    )

    collected = COLLECT(
        exe,
        analysis.binaries,
        analysis.zipfiles,
        analysis.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=NAME,
    )
