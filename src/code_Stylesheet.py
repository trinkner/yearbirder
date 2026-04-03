import sys
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QProxyStyle, QStyle, QMenu
from PySide6.QtCore import Qt, QRect, QEvent


class AppStyle(QProxyStyle):
    """Fusion proxy style — non-bold MDI title bars and opaque dark menus."""

    def polish(self, obj):
        """Install this style as an event filter on every QMenu so we can patch
        its NSWindow before macOS gets a chance to apply vibrancy compositing.

        QPalette overload must return the (possibly modified) palette object.
        """
        from PySide6.QtGui import QPalette
        if isinstance(obj, QPalette):
            return super().polish(obj)
        super().polish(obj)
        if isinstance(obj, QMenu) and sys.platform == "darwin":
            obj.installEventFilter(self)

    def eventFilter(self, obj, event):
        """On Show, patch the NSWindow backing each QMenu to be fully opaque.

        macOS applies its vibrancy/blur compositor effect at the window layer,
        after Qt finishes painting.  The only reliable fix is to reach into the
        NSWindow via Objective-C and call setOpaque:YES before the window appears.
        """
        if isinstance(obj, QMenu) and event.type() == QEvent.Show:
            try:
                import ctypes, ctypes.util
                lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))

                lib.objc_getClass.restype   = ctypes.c_void_p
                lib.objc_getClass.argtypes  = [ctypes.c_char_p]
                lib.sel_registerName.restype  = ctypes.c_void_p
                lib.sel_registerName.argtypes = [ctypes.c_char_p]

                addr     = ctypes.cast(lib.objc_msgSend, ctypes.c_void_p).value
                msg0     = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(addr)
                msg1_id  = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(addr)
                msg_bool = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool)(addr)
                msg_4d   = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                            ctypes.c_double, ctypes.c_double,
                                            ctypes.c_double, ctypes.c_double)(addr)

                # winId() returns an NSView*; get its NSWindow
                ns_view   = int(obj.winId())
                ns_window = msg0(ns_view, lib.sel_registerName(b"window"))
                if ns_window:
                    # Make the window opaque — disables macOS vibrancy compositing
                    msg_bool(ns_window, lib.sel_registerName(b"setOpaque:"), True)

                    # Set the window background to our dark menu colour (#2b2d38)
                    NSColor    = lib.objc_getClass(b"NSColor")
                    dark_color = msg_4d(NSColor,
                                        lib.sel_registerName(b"colorWithRed:green:blue:alpha:"),
                                        43/255.0, 45/255.0, 56/255.0, 1.0)
                    msg1_id(ns_window, lib.sel_registerName(b"setBackgroundColor:"), dark_color)
            except Exception:
                pass
        return False  # never consume the event

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PE_PanelMenu:
            painter.setCompositionMode(QPainter.CompositionMode_Source)
            painter.fillRect(option.rect, QColor("#2b2d38"))
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(QColor("#3a3d4e"))
            painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
            return
        super().drawPrimitive(element, option, painter, widget)

    def drawComplexControl(self, control, option, painter, widget=None):
        # Let Fusion draw the full title bar (background, buttons, bold text)
        super().drawComplexControl(control, option, painter, widget)

        if control == QStyle.CC_TitleBar:
            isActive = bool(option.state & QStyle.State_Active)
            bgColor   = QColor("#636878") if isActive else QColor("#2e3040")

            iconRect = self.subControlRect(control, option, QStyle.SC_TitleBarSysMenu, widget)

            # Find the leftmost of the three window buttons
            leftEdge = option.rect.right()
            for btn in (QStyle.SC_TitleBarMinButton,
                        QStyle.SC_TitleBarMaxButton,
                        QStyle.SC_TitleBarCloseButton):
                r = self.subControlRect(control, option, btn, widget)
                if r.isValid() and r.left() < leftEdge:
                    leftEdge = r.left()

            # Size the icon to fill the title bar height with a small margin,
            # and offset it past the window's rounded corner radius (~8 px) so
            # it isn't clipped.  Fusion's SC_TitleBarSysMenu rect starts at (0,0)
            # which sits inside the clipped corner.
            barH = option.rect.height()
            iconSize = max(barH - 8, 10)   # 4 px top + 4 px bottom padding
            iconX = option.rect.left() + 8  # clear the corner-radius clip zone
            iconY = option.rect.top() + (barH - iconSize) // 2
            columnRight = max(iconRect.right(), iconX + iconSize + 4)

            # Repaint the icon column at full title-bar height
            iconColumnRect = QRect(option.rect.left(), option.rect.top(),
                                   columnRight - option.rect.left() + 1,
                                   option.rect.height())
            painter.fillRect(iconColumnRect, bgColor)
            if not option.icon.isNull():
                px = option.icon.pixmap(iconSize, iconSize)
                painter.drawPixmap(iconX, iconY, px)

            # Repaint the text area to erase Fusion's bold title text
            fillRect = QRect(
                columnRight + 1,
                option.rect.top(),
                leftEdge - columnRight - 2,
                option.rect.height(),
            )
            painter.fillRect(fillRect, bgColor)

            # Redraw the title text without bold
            painter.save()
            font = painter.font()
            font.setBold(False)
            painter.setFont(font)
            textColor = QColor("#e2e4ec") if isActive else QColor("#8b8fa8")
            painter.setPen(textColor)
            painter.drawText(fillRect, Qt.AlignCenter | Qt.TextSingleLine, option.text)
            painter.restore()


baseColor = "#1e1f26"
tableColor = "#252730"
mdiAreaColor = QColor(18, 19, 24)
textColor = "#e2e4ec"
speciesColor = QColor(79, 142, 247)

stylesheetBase = """
    QWidget {
        background: #1e1f26;
        color: #e2e4ec;
    }

    QTabWidget::pane {
        border: 1px solid #3a3d4e;
        border-radius: 6px;
    }
    QTabBar::tab {
        background: #2b2d38;
        padding: 6px 14px;
        border-radius: 4px;
    }
    QTabBar::tab:selected {
        background: #4f8ef7;
        color: white;
    }

    QPushButton {
        background: #2b2d38;
        color: #e2e4ec;
        border: 1px solid #3a3d4e;
        border-radius: 6px;
        padding: 5px 12px;
        min-width: 60px;
    }
    QPushButton:hover { background: #363a4f; }
    QPushButton:pressed { background: #4f8ef7; color: white; }

    QComboBox {
        background: #2b2d38;
        border: 1px solid #3a3d4e;
        border-radius: 5px;
        padding: 3px 8px;
        min-height: 22px;
    }
    QComboBox:hover { border-color: #4f8ef7; }
    QComboBox:focus {
        background: #363a4f;
        border: 1px solid #4f8ef7;
        border-radius: 5px;
    }
    QComboBox:on {
        background: #363a4f;
        border: 1px solid #4f8ef7;
        border-radius: 5px;
    }
    QComboBox QAbstractItemView {
        background: #2b2d38;
        selection-background-color: #4f8ef7;
    }

    QLineEdit, QPlainTextEdit {
        background: #252730;
        border: 1px solid #3a3d4e;
        border-radius: 5px;
        padding: 4px 8px;
    }
    QLineEdit:focus, QPlainTextEdit:focus { border-color: #4f8ef7; }

    QTableWidget {
        background: #252730;
        gridline-color: #2e3040;
        border: 1px solid #3a3d4e;
        border-radius: 4px;
    }
    QTableWidget::item:selected { background: #4f8ef7; color: white; }
    QHeaderView::section {
        background: #2b2d38;
        padding: 5px;
        border: none;
        border-bottom: 1px solid #3a3d4e;
        font-weight: bold;
    }

    QListWidget {
        background: #1e1f26;
        border: none;
    }
    QListWidget::item:selected { background: #4f8ef7; color: white; }
    QListWidget::item:hover { background: #363a4f; }

    QScrollBar:vertical {
        background: #1e1f26;
        width: 8px;
        border-radius: 4px;
    }
    QScrollBar::handle:vertical {
        background: #3a3d4e;
        border-radius: 4px;
        min-height: 20px;
    }
    QScrollBar::handle:vertical:hover { background: #4f8ef7; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

    QScrollBar:horizontal {
        background: #1e1f26;
        height: 8px;
        border-radius: 4px;
    }
    QScrollBar::handle:horizontal {
        background: #3a3d4e;
        border-radius: 4px;
    }
    QScrollBar::handle:horizontal:hover { background: #4f8ef7; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

    QDockWidget::title {
        background: #2b2d38;
        padding: 6px;
        font-weight: bold;
    }

    QToolBar {
        background: #1e1f26;
        border: none;
        spacing: 0px;
    }
    QToolBar::separator {
        width: 0px;
        height: 0px;
    }
    QToolButton {
        background: transparent;
        border: none;
        color: #e2e4ec;
    }
    QToolButton:hover {
        background: #363a4f;
        border-radius: 4px;
    }
    QToolButton:pressed {
        background: #4f8ef7;
        border-radius: 4px;
        color: white;
    }

    QMenuBar { background: #1e1f26; color: #e2e4ec; }
    QMenuBar::item { background: transparent; color: #e2e4ec; padding: 4px 8px; }
    QMenuBar::item:selected { background: #363a4f; border-radius: 4px; }

    QMenu {
        color: #e2e4ec;
    }
    QMenu::item {
        background: transparent;
        color: #e2e4ec;
        padding: 5px 28px 5px 24px;
    }
    QMenu::item:selected {
        background: #4f8ef7;
        color: #ffffff;
        border-radius: 4px;
    }
    QMenu::item:disabled { color: #5a5e73; }
    QMenu::separator {
        height: 1px;
        background: #3a3d4e;
        margin: 4px 8px;
    }

    QRadioButton::indicator {
        border: 2px solid #8b8fa8;
        border-radius: 6px;
        width: 10px;
        height: 10px;
        background: transparent;
    }
    QRadioButton::indicator:checked {
        background: #4f8ef7;
        border-color: #4f8ef7;
    }

    QStatusBar { background: #16171e; color: #8b8fa8; }

    QCalendarWidget QWidget { background: #2b2d38; }
    QCalendarWidget QAbstractItemView {
        background: #252730;
        selection-background-color: #4f8ef7;
    }
"""
