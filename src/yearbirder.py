import os
import sys

# Set a persistent MPLCONFIGDIR before matplotlib is imported anywhere.
# PyInstaller's pyi_rth_mplconfig.py hook normally creates a new temp directory
# on every launch, forcing matplotlib to rebuild its font cache from scratch
# (~15 seconds). Pointing MPLCONFIGDIR at a stable location lets the cache
# persist between launches and eliminates that delay.
if sys.platform == "darwin":
    _mpl_cache = os.path.join(
        os.path.expanduser("~"), "Library", "Application Support",
        "Yearbirder", "matplotlib"
    )
else:
    _mpl_cache = os.path.join(
        os.path.expanduser("~"), ".yearbirder", "matplotlib"
    )
os.makedirs(_mpl_cache, exist_ok=True)
os.environ["MPLCONFIGDIR"] = _mpl_cache

# Use the native macOS multimedia backend (AVFoundation / Core Audio) instead of
# Qt's default FFmpeg backend.  The FFmpeg backend's QAudioSink crackles on macOS
# with our continuous pull device and ignores setBufferSize; the native backend
# plays cleanly and is what the persistent-sink player (PcmAudioPlayer) targets.
# Must be set before QtMultimedia is loaded.
if sys.platform == "darwin":
    os.environ.setdefault("QT_MEDIA_BACKEND", "darwin")

# On Windows the embedded Chromium (QWebEngineView) cannot verify tile-server
# SSL certificates inside a PyInstaller bundle, causing map tiles to silently
# fail. This flag must be set before QApplication is created.
if sys.platform != "darwin":
    _webengine_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    if "--ignore-certificate-errors" not in _webengine_flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
            (_webengine_flags + " ").lstrip() + "--ignore-certificate-errors"
        ).strip()

import code_MainWindow
import code_Stylesheet

from PySide6.QtWidgets import (
    QApplication,
    )

from PySide6.QtGui import QFont, QPalette, QColor, QIcon
from PySide6.QtCore import QTimer, Qt


def _force_macos_dark_appearance():
    """Set NSAppearanceName.darkAqua on macOS so native windows (e.g. QMessageBox)
    use a dark title bar instead of the system-default white one."""
    if sys.platform != "darwin":
        return
    try:
        import ctypes, ctypes.util
        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))

        lib.objc_getClass.restype   = ctypes.c_void_p
        lib.objc_getClass.argtypes  = [ctypes.c_char_p]
        lib.sel_registerName.restype  = ctypes.c_void_p
        lib.sel_registerName.argtypes = [ctypes.c_char_p]

        # Build typed wrappers around the variadic objc_msgSend
        addr   = ctypes.cast(lib.objc_msgSend, ctypes.c_void_p).value
        send0  = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(addr)
        send1  = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(addr)
        send1s = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p)(addr)

        NSString      = lib.objc_getClass(b"NSString")
        NSAppearance  = lib.objc_getClass(b"NSAppearance")
        NSApplication = lib.objc_getClass(b"NSApplication")

        sel_utf8   = lib.sel_registerName(b"stringWithUTF8String:")
        sel_named  = lib.sel_registerName(b"appearanceNamed:")
        sel_shared = lib.sel_registerName(b"sharedApplication")
        sel_set    = lib.sel_registerName(b"setAppearance:")

        dark_str = send1s(NSString, sel_utf8, b"NSAppearanceNameDarkAqua")
        dark_app = send1(NSAppearance, sel_named, dark_str)
        ns_app   = send0(NSApplication, sel_shared)
        send1(ns_app, sel_set, dark_app)
    except Exception:
        pass


def _install_webengine_scrollbar_style():
    """Give every web view dark scrollbars matching the app theme (Windows only).

    Chromium draws native scrollbars for page content: auto-hiding dark overlay
    ones on macOS, but classic opaque white ones on Windows — glaring inside the
    dark web-based windows (Statistics, Recordings by Species, maps, ...).  The
    many HTML templates across the app don't each need ::-webkit-scrollbar rules:
    a QWebEngineScript on the default profile injects one <style> into every
    page any view loads.  Kept off macOS so its overlay scrollbars stay native
    (styling ::-webkit-scrollbar would make them permanently visible).
    """
    if sys.platform != "win32":
        return
    try:
        from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineScript
        css = (
            "::-webkit-scrollbar { width:12px; height:12px; background:transparent; }"
            "::-webkit-scrollbar-thumb { background:#4a4e5e; border-radius:6px; }"
            "::-webkit-scrollbar-thumb:hover { background:#636878; }"
            "::-webkit-scrollbar-corner { background:transparent; }"
        )
        js = (
            "(function() {"
            "  var s = document.createElement('style');"
            "  s.textContent = '%s';"
            "  (document.head || document.documentElement).appendChild(s);"
            "})();" % css
        )
        script = QWebEngineScript()
        script.setName("yearbirderScrollbars")
        script.setSourceCode(js)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
        script.setRunsOnSubFrames(True)
        QWebEngineProfile.defaultProfile().scripts().insert(script)
    except Exception:
        pass


def _warm_up_webengine(form):
    """Create the process's first QWebEngineView while the main window is still
    hidden (Windows only).

    Embedding the first web view switches the top-level window from raster to
    GPU composition, and Qt destroys and recreates the native window to make
    that switch.  When it happens while the window is visible — the Stats
    report auto-opening after the data load — the app momentarily vanishes to
    the desktop with a white flash (AA_ShareOpenGLContexts alone did not
    prevent this; the recreation is about the window's surface type, not GL
    context sharing).  A tiny web view parented to the not-yet-shown main
    window forces the one-time switch to happen while nothing is on screen.

    The view must be a CHILD of the main window: an earlier warm-up attempt
    with a top-level web view made things worse (top-level web views flash
    white on Windows even when never shown).  Chromium starting at launch
    costs nothing extra here — the Stats window (a web view) auto-opens right
    after the data load anyway.
    """
    if sys.platform != "win32":
        return
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView
        view = QWebEngineView(form)
        view.setFixedSize(1, 1)
        view.move(-10, -10)   # clipped away inside the parent
        view.setHtml("")      # force page/render-widget creation now
        form._webengineWarmup = view  # keep alive for the app's lifetime
    except Exception:
        pass


def _prepare_windows_first_frame(form):
    """Make the very first frame Windows shows for the main window dark.

    On Windows the native top-level window becomes visible before Qt paints
    into it: the title bar is drawn by DWM in the system (light) theme, and the
    client area is filled with the window class's background brush — which is
    white — producing a brief white flash at launch before the dark palette
    takes over.  Neither is controllable from Qt's paint pipeline, so fix both
    at the Win32 level before the window is shown:

    - DWMWA_USE_IMMERSIVE_DARK_MODE → dark title bar from the first frame
      (attribute 20 on Windows 10 20H1+, 19 on older 1809+ builds).
    - GCLP_HBRBACKGROUND → dark class background brush, so the pre-first-paint
      fill matches the app background (#2b2d38) instead of white.  Qt shares
      one window class across all its top-level windows, so this also covers
      any later native windows in the process.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(form.winId())  # forces native window creation now

        value = ctypes.c_int(1)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd), attr,
                    ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break

        user32 = ctypes.windll.user32
        user32.SetClassLongPtrW.restype = ctypes.c_void_p
        user32.SetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                            ctypes.c_void_p]
        GCLP_HBRBACKGROUND = -10
        # COLORREF is 0x00BBGGRR: #2b2d38 → 0x00382D2B
        brush = ctypes.windll.gdi32.CreateSolidBrush(0x00382D2B)
        user32.SetClassLongPtrW(ctypes.c_void_p(hwnd), GCLP_HBRBACKGROUND,
                                ctypes.c_void_p(brush))
    except Exception:
        pass


def main():
    # QtWebEngine's documented requirement: OpenGL context sharing must be
    # enabled BEFORE the QApplication is created so web views can share GL
    # resources with Qt's rendering.  (Note: this alone does NOT prevent the
    # Windows window-recreation flash when the first web view is embedded —
    # that is handled by _warm_up_webengine below.)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)

    # Stable app name → stable per-platform cache/data locations
    # (QStandardPaths.CacheLocation is used by the thumbnail cache).
    app.setApplicationName("Yearbirder")

    # Default icon for every top-level window.  The Windows taskbar and task
    # switcher read the icon embedded in the .exe, so those were already right,
    # but the title bar draws the WINDOW's QIcon — and nothing ever set one, so
    # the main window showed Qt's generic default.  Setting it here covers the
    # main window and dialogs at once; MDI children keep the per-report icons
    # they set for themselves.
    #
    # Platform-specific artwork, because the same call means different things.
    # macOS has no title-bar icons: this IS the Dock and Cmd-Tab icon, and it
    # takes precedence over the bundle's .icns — and when running from source
    # there is no bundle at all, so it is the only icon there is.  It therefore
    # needs Apple's icon grid (824px body inside a 1024 canvas, squircle
    # corners) or Yearbirder renders larger and squarer than every app beside
    # it.  Windows and Linux want the full-bleed square, which is what a taskbar
    # and a title bar expect.  See icons/make_macos_icon.py.
    if sys.platform == "darwin":
        app.setWindowIcon(QIcon(":/icon_yearbirder_macos.png"))
    else:
        app.setWindowIcon(QIcon(":/icon_yearbirder.ico"))

    app.setStyle(code_Stylesheet.AppStyle("Fusion"))

    font = app.font()
    # 11pt to match MainWindow.fontSize: the app-wide stylesheet disables Qt's
    # parent->child font propagation, so widgets the scaleMe() children loops
    # don't reach directly (nested tables, their headers, QFont()-based bold
    # item fonts) fall back to THIS font.  At 10pt they rendered one point
    # smaller than the explicitly-sized header labels around them.
    font.setPointSize(11)
    # On Windows the stock default family resolves to the legacy "MS Sans Serif"
    # bitmap font, which DirectWrite cannot load — it spams CreateFontFaceFromHDC
    # errors and forces an ugly fallback (and is why QFont("") looked wrong on
    # Windows).  Use the real Windows UI font, and redirect any lingering
    # MS Sans Serif request (e.g. from empty-family QFont("")) to it.
    if sys.platform == "win32":
        font.setFamily("Segoe UI")
        QFont.insertSubstitution("MS Sans Serif", "Segoe UI")
    app.setFont(font)

    palette = app.palette()

    # Base colours — used by Fusion for all palette-driven rendering (menus,
    # buttons, panels, etc.) that Qt stylesheets cannot fully override on macOS.
    palette.setColor(QPalette.Window,          QColor("#2b2d38"))
    palette.setColor(QPalette.WindowText,      QColor("#e2e4ec"))
    palette.setColor(QPalette.Base,            QColor("#252730"))
    palette.setColor(QPalette.AlternateBase,   QColor("#2b2d38"))
    palette.setColor(QPalette.Text,            QColor("#e2e4ec"))
    palette.setColor(QPalette.BrightText,      QColor("#ffffff"))
    palette.setColor(QPalette.Button,          QColor("#2b2d38"))
    palette.setColor(QPalette.ButtonText,      QColor("#e2e4ec"))
    palette.setColor(QPalette.ToolTipBase,     QColor("#2b2d38"))
    palette.setColor(QPalette.ToolTipText,     QColor("#e2e4ec"))
    palette.setColor(QPalette.Link,            QColor("#4f8ef7"))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#5a5e73"))
    palette.setColor(QPalette.Disabled, QPalette.Text,       QColor("#5a5e73"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#5a5e73"))

    # MDI subwindow title bars
    palette.setColor(QPalette.Active,   QPalette.Highlight,       QColor("#636878"))
    palette.setColor(QPalette.Inactive, QPalette.Highlight,       QColor("#2e3040"))
    palette.setColor(QPalette.Active,   QPalette.HighlightedText, QColor("#e2e4ec"))
    palette.setColor(QPalette.Inactive, QPalette.HighlightedText, QColor("#8b8fa8"))

    app.setPalette(palette)
    app.setStyleSheet(code_Stylesheet.stylesheetBase)
    _force_macos_dark_appearance()

    _install_webengine_scrollbar_style()

    form = code_MainWindow.MainWindow()
    _warm_up_webengine(form)          # raster→GPU window switch while hidden
    _prepare_windows_first_frame(form)

    # Show the window exactly once, then load the eBird file only after the event
    # loop is running, so the maximized window is fully realised before the heavy
    # synchronous load.  Doing the load inside __init__ (before app.exec) made
    # the window drop and re-assert on Windows — a desktop flash.  The progress
    # overlay is a child of the now-visible window, so it still shows during the
    # load.
    if sys.platform == "win32":
        # The native window's initial (white) surface reaches the screen before
        # Qt's first paint.  DWM cloaking could not stop it — the cloak sticks to
        # one HWND, and Qt may recreate the native window during show (the
        # raster→GPU switch from the WebEngine warm-up), silently shedding it.
        # Window opacity lives in Qt's own window state and is re-applied to any
        # recreated native window, so it survives that.  Show fully transparent,
        # give the event loop a moment to expose the window, force a paint so
        # the surface provably holds the dark UI, then reveal and start the
        # load.  The reveal is in a finally so the window can never stay
        # invisible.
        form.setWindowOpacity(0.0)
        form.showMaximized()

        def _revealThenLoad():
            try:
                form.repaint()
            finally:
                form.setWindowOpacity(1.0)
            QTimer.singleShot(0, form.processPreferences)

        QTimer.singleShot(50, _revealThenLoad)
    else:
        form.showMaximized()
        QTimer.singleShot(0, form.processPreferences)

    app.exec()


if __name__ == '__main__':
    main()
