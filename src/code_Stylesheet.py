import sys
import os
import tempfile
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QProxyStyle, QStyle, QMenu, QMessageBox, QMdiSubWindow,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PySide6.QtCore import Qt, QRect, QEvent


class AppStyle(QProxyStyle):
    """Fusion proxy style — non-bold MDI title bars and opaque dark menus."""

    def polish(self, obj):
        """Install this style as an event filter on every QMenu so we can patch
        its NSWindow before macOS gets a chance to apply vibrancy compositing.

        Qt may call polish() with a QWidgetItem (a layout wrapper) which is not
        one of the three supported overloads; guard with explicit isinstance
        checks so unrecognised types are silently ignored.
        """
        from PySide6.QtGui import QPalette
        from PySide6.QtWidgets import QApplication, QWidget
        if isinstance(obj, QPalette):
            return super().polish(obj)
        if isinstance(obj, (QApplication, QWidget)):
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

        # Hairline frame on top of Fusion's native MDI frame (not a QSS
        # border — see comment above QMdiSubWindow's stylesheet block for
        # why) so overlapping dark child windows read as separate surfaces;
        # the focused window's border is clearly lighter (driven by the
        # activeWin property set in onSubWindowActivated).  option.rect here
        # is the frame's true outer edge, matching where Fusion just painted,
        # so the line traces the window with no gap at the corners.
        if element == QStyle.PE_FrameWindow and isinstance(widget, QMdiSubWindow):
            isActive = bool(widget.property("activeWin"))
            painter.save()
            painter.setPen(QColor("#5a5f75") if isActive else QColor("#3f4254"))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
            painter.restore()

    def standardPixmap(self, standardPixmap, option=None, widget=None):
        if standardPixmap in (
            QStyle.StandardPixmap.SP_MessageBoxInformation,
            QStyle.StandardPixmap.SP_MessageBoxWarning,
            QStyle.StandardPixmap.SP_MessageBoxCritical,
        ):
            px = QPixmap(48, 48)
            px.fill(Qt.GlobalColor.transparent)
            painter = QPainter(px)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(CHART_PRIMARY))
            painter.drawEllipse(0, 0, 48, 48)
            font = painter.font()
            font.setPixelSize(30)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "!")
            painter.end()
            return px
        return super().standardPixmap(standardPixmap, option, widget)

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


# UI font family — single source of truth for every QFont() in the app.
# Empty string means "let Qt pick the system default", which is correct on macOS
# (San Francisco) and Linux.  On Windows an empty family resolves to the legacy
# bitmap font "MS Sans Serif", which DirectWrite cannot load (it spams
# CreateFontFaceFromHDC errors and renders an ugly fallback), so we name the real
# Windows UI font explicitly.  Use as QFont(YBFont, pointSize).
YBFont = "Segoe UI" if sys.platform == "win32" else ""

# Chart colour palette — single source of truth for code_Graphs.py and code_Web.py
CHART_PRIMARY   = "#4f8ef7"   # thematic blue — standard-filter charts
CHART_SECONDARY = "#28384c"   # dark muted blue — repeat / extension bars
PHOTO_PRIMARY   = "#f7d94f"   # bright golden yellow — photo-filter charts
PHOTO_SECONDARY = "#594d26"   # dark muted amber — repeat / extension bars
RECORDINGS_PRIMARY   = "#52c878"   # bright green — recording-filter charts
RECORDINGS_SECONDARY = "#1e5430"   # dark forest green — repeat / extension bars

baseColor = "#1e1f26"
tableColor = "#252730"
mdiAreaColor = QColor(39, 39, 43)
textColor = "#e2e4ec"
speciesColor = QColor(79, 142, 247)

stylesheetBase = """
    QWidget {
        background: #1e1f26;
        color: #e2e4ec;
    }

    /* Deliberately no QSS "border" on QMdiSubWindow: it makes
       QStyleSheetStyle substitute its own box-model frame for Fusion's
       native PE_FrameWindow, which leaves the title bar inset ~4px from
       that border (an invisible native resize margin Fusion always
       reserves) — an unpainted gap at the top corners.  The hairline is
       instead painted by AppStyle.drawPrimitive over the untouched native
       frame, at the frame's true outer edge, so there's no mismatch. */

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

    /* Shared media-card background for the four media views (Browse + Manage,
       Photos + Recordings).  A NEUTRAL gray, deliberately outside the blue
       ramp, so photo colour judgement isn't skewed by a tinted surround; the
       same gray the Enlargement windows already use.  Styled here via object
       names — per-widget setStyleSheet in row builders costs milliseconds
       per row. */
    QWidget#mediaCard { background-color: #343333; border-radius: 6px; }
    /* The global "QWidget { background: #1e1f26 }" rule above makes every
       plain child paint an opaque background ON TOP of the card, hiding it.
       Scoped transparency lets the card show through: labels, checkboxes and
       sliders inside a card, plain container widgets tagged #cardTransparent,
       and the species tag strip.  Real controls (buttons, combos) keep their
       own styled backgrounds. */
    QWidget#mediaCard QLabel { background: transparent; color: #c1c1c1; }
    QWidget#mediaCard QCheckBox { background: transparent; color: #c1c1c1; }
    QWidget#mediaCard QSlider { background: transparent; }
    QWidget#cardTransparent { background: transparent; }
    SpeciesTagStrip { background: transparent; }
    QLabel#mediaCaption { background: transparent; color: silver; padding: 3px; }

    /* Controls sitting ON a card must be lighter than the card to read as
       raised — the global button fill (#2b2d38) is darker than the card, which
       inverted the elevation and made buttons look recessed.  These ID-scoped
       rules outrank the global :hover/:pressed/:focus states, so those are
       restated here; the chip × and the photo-thumbnail button must stay
       transparent and are exempted at higher specificity. */
    QWidget#mediaCard QPushButton {
        background: #42454f;
        border: 1px solid #565a6a;
    }
    QWidget#mediaCard QPushButton:hover { background: #4d5160; }
    QWidget#mediaCard QPushButton:pressed { background: #4f8ef7; color: white; }
    QWidget#mediaCard QComboBox {
        background: #42454f;
        border: 1px solid #565a6a;
    }
    QWidget#mediaCard QComboBox:hover { border-color: #4f8ef7; }
    QWidget#mediaCard QComboBox:focus,
    QWidget#mediaCard QComboBox:on {
        background: #4d5160;
        border: 1px solid #4f8ef7;
    }
    QWidget#mediaCard QPushButton#chipRemoveBtn {
        background: transparent; border: none;
    }
    QWidget#mediaCard QPushButton#chipRemoveBtn:hover {
        background: rgba(255,255,255,40); border-radius: 9px;
    }
    QWidget#mediaCard QPushButton#mediaThumbBtn {
        background: transparent; border: none;
    }
    QPushButton#mediaThumbBtn {
        background-color: transparent; border: none;
        padding: 0px; min-width: 0px;
    }

    /* Species chip pills (SpeciesTagStrip in Manage Recordings).  Styled here
       rather than with per-widget setStyleSheet: per-widget sheets force a
       fresh style object + repolish per chip piece (~13ms per row). */
    QWidget#speciesChip { background-color: #4a86c8; border-radius: 8px; }
    QWidget#speciesChip[skipped="true"] { background-color: #6b6e7e; }
    QWidget#speciesChip QLabel { color: white; background: transparent; border: none; }
    QPushButton#chipRemoveBtn {
        color: white; font-weight: bold;
        min-width: 0px; padding: 0px;
        background: transparent; border: none;
    }
    QPushButton#chipRemoveBtn:hover {
        background: rgba(255,255,255,40); border-radius: 9px;
    }

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
        border-right: 1px solid #3a3d4e;
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
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: #1e1f26; }

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
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: #1e1f26; }

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

    QSlider::groove:horizontal {
        background: #2b2d38;
        height: 4px;
        border-radius: 2px;
    }
    QSlider::sub-page:horizontal {
        background: #4f8ef7;
        border-radius: 2px;
    }
    QSlider::add-page:horizontal {
        background: #2b2d38;
        border-radius: 2px;
    }
    QSlider::handle:horizontal {
        background: #4f8ef7;
        border: none;
        width: 14px;
        height: 14px;
        margin: -5px 0;
        border-radius: 7px;
    }
    QSlider::handle:horizontal:hover { background: #7aaeff; }

    QSlider::groove:vertical {
        background: #2b2d38;
        width: 4px;
        border-radius: 2px;
    }
    QSlider::sub-page:vertical {
        background: #4f8ef7;
        border-radius: 2px;
    }
    QSlider::add-page:vertical {
        background: #2b2d38;
        border-radius: 2px;
    }
    QSlider::handle:vertical {
        background: #4f8ef7;
        border: none;
        width: 14px;
        height: 14px;
        margin: 0 -5px;
        border-radius: 7px;
    }
    QSlider::handle:vertical:hover { background: #7aaeff; }

    QStatusBar { background: #16171e; color: #8b8fa8; }

    QCalendarWidget QWidget { background: #2b2d38; }
    QCalendarWidget QAbstractItemView {
        background: #252730;
        selection-background-color: #4f8ef7;
    }
"""

# Write a tiny SVG checkmark to the temp directory so the QSS image: property
# can reference it by path.  The stroke colour comes from CHART_PRIMARY so
# there is a single source of truth — no hardcoded hex value here.
_checkmark_svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 14 14">
  <polyline points="2,7 5.5,10.5 12,3.5"
            stroke="{CHART_PRIMARY}" stroke-width="2.2"
            fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""

_checkmark_path = os.path.join(tempfile.gettempdir(),
                               "yearbirder_checkmark.svg").replace("\\", "/")
with open(_checkmark_path, "w", encoding="utf-8") as _f:
    _f.write(_checkmark_svg)

stylesheetBase += f"""
    QCheckBox::indicator {{
        border: 2px solid #8b8fa8;
        border-radius: 3px;
        width: 12px;
        height: 12px;
        background: transparent;
    }}
    QCheckBox::indicator:checked {{
        border-color: {CHART_PRIMARY};
        image: url({_checkmark_path});
    }}
"""


def mediaFilterConflict(parent):
    """Show conflict dialog when both photo and recording filters are active for a general query.
    Returns 'photos', 'recordings', or 'cancel'."""
    px = QPixmap(48, 48)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(CHART_PRIMARY))
    painter.drawEllipse(0, 0, 48, 48)
    font = painter.font()
    font.setPixelSize(30)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "?")
    painter.end()

    msg = QMessageBox(parent)
    msg.setWindowTitle("Media Filter Conflict")
    msg.setText(
        "The Photos and Recordings sections of the Media Filter both have active settings.\n\n"
        "Which filter should be applied to this query?"
    )
    msg.setIconPixmap(px)
    btnPhotos = msg.addButton("Photos Only", QMessageBox.ButtonRole.AcceptRole)
    btnAudio  = msg.addButton("Recordings Only", QMessageBox.ButtonRole.AcceptRole)
    btnCancel = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    msg.setDefaultButton(btnCancel)
    msg.exec()
    clicked = msg.clickedButton()
    if clicked == btnPhotos:
        return "photos"
    if clicked == btnAudio:
        return "recordings"
    return "cancel"


def _blue_question_pixmap():
    """The app's blue circle "?" dialog icon (shared by question/choose)."""
    px = QPixmap(48, 48)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(CHART_PRIMARY))
    painter.drawEllipse(0, 0, 48, 48)
    font = painter.font()
    font.setPixelSize(30)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "?")
    painter.end()
    return px


def choose(parent, title, text, labels):
    """Blue question-mark dialog with arbitrary buttons shown in exactly the
    given left-to-right order.

    Implemented as a custom QDialog because QMessageBox reorders its buttons by
    role on macOS.  Each button is sized to fit its full caption (no truncation).
    Esc / window-close returns None; otherwise the clicked caption is returned."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    result = {"value": None}

    outer = QVBoxLayout(dlg)
    outer.setContentsMargins(24, 20, 24, 16)
    outer.setSpacing(18)

    # Icon + message
    top = QHBoxLayout()
    top.setSpacing(16)
    icon = QLabel()
    icon.setPixmap(_blue_question_pixmap())
    top.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
    msg = QLabel(text)
    msg.setWordWrap(True)
    top.addWidget(msg, 1)
    outer.addLayout(top)

    # Buttons in the exact order supplied, right-aligned as a group.
    btnRow = QHBoxLayout()
    btnRow.setSpacing(10)
    btnRow.addStretch()
    for lbl in labels:
        b = QPushButton(lbl)
        b.setMinimumWidth(b.fontMetrics().horizontalAdvance(lbl) + 40)
        b.clicked.connect(
            lambda _checked=False, _lbl=lbl: (result.update(value=_lbl), dlg.accept()))
        btnRow.addWidget(b)
    outer.addLayout(btnRow)

    dlg.exec()
    return result["value"]


def question(parent, title, text,
             buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
             default=QMessageBox.StandardButton.No,
             yes_text=None, no_text=None):
    """QMessageBox.question replacement with a blue question-mark icon.

    ``yes_text`` / ``no_text`` relabel the Yes / No buttons while keeping their
    standard-button return values, so callers still compare against
    QMessageBox.StandardButton.Yes / .No."""
    msg = QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setIconPixmap(_blue_question_pixmap())
    msg.setStandardButtons(buttons)
    msg.setDefaultButton(default)
    if yes_text is not None:
        b = msg.button(QMessageBox.StandardButton.Yes)
        if b is not None:
            b.setText(yes_text)
    if no_text is not None:
        b = msg.button(QMessageBox.StandardButton.No)
        if b is not None:
            b.setText(no_text)
    return msg.exec()
