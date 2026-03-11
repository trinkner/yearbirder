import code_MainWindow
import code_Stylesheet
import sys

from PyQt5.QtWidgets import (
    QApplication,
    )

from PyQt5.QtGui import QFont, QPalette, QColor


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


def main():
    app = QApplication(sys.argv)

    app.setStyle(code_Stylesheet.AppStyle("Fusion"))

    font = app.font()
    font.setPointSize(10)
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

    form = code_MainWindow.MainWindow()
    form.show()

    # form.processPreferences()
            
    app.exec_()
 

if __name__ == '__main__':              
    main()                              
