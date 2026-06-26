# import the GUI forms that we create with Qt Creator
import code_Individual
import code_Stylesheet

# import the Qt components we'll use
from PySide6.QtGui import (
    QFont,
    QColor,
    QPainter,
    QPen,
)

from PySide6.QtCore import (
    Signal,
    Qt,
    QEvent,
    QTimer,
)

from PySide6.QtWidgets import (
    QMdiSubWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QScrollArea,
    QFrame,
    QLabel,
    QListWidget,
    QSizePolicy,
)

from PySide6.QtWebEngineWidgets import (
    QWebEngineView,
)

from PySide6.QtPrintSupport import (
    QPrinter,
)

# ── Card colors ────────────────────────────────────────────────────────────────
_COLOR_A        = "#4f8ef7"   # blue  – slot A
_COLOR_B        = "#d98c5a"   # orange – slot B (toned-down, less saturated)
_COLOR_IDLE     = "#3a3c4a"   # unselected card background
_COLOR_IDLE_HV  = "#4a4d5e"   # unselected card hover
_COLOR_BORDER   = "#5a5e73"   # idle border
_CARD_W         = 160         # px
_CARD_H         = 64          # px (20% shorter than the original 80)


class _ListCard(QFrame):
    """A clickable card that represents one species-list window."""

    clicked = Signal(object)   # emits self

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title        = title   # full window title — used for list lookup
        self._display     = title.removeprefix("Species: ")
        self.slot    = None          # None | "A" | "B"
        self._hovered = False

        # Named so the border stylesheet can target only this frame.  Without
        # an objectName a bare "QFrame { border }" rule also matches the child
        # QLabels (QLabel subclasses QFrame), drawing a stray inner border.
        self.setObjectName("listCard")
        self.setMinimumHeight(_CARD_H)
        self.setMinimumWidth(_CARD_W)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 6, 7, 6)
        layout.setSpacing(3)

        self._badge = QLabel("", self)
        self._badge.setAlignment(Qt.AlignCenter)
        self._badge.setFixedSize(20, 20)
        badge_font = QFont("", 9, QFont.Bold)
        self._badge.setFont(badge_font)

        self._title_lbl = QLabel(self._display, self)
        self._title_lbl.setAlignment(Qt.AlignCenter)
        self._title_lbl.setWordWrap(True)
        self._title_lbl.setStyleSheet("color: #e2e4ec; background: transparent;")

        badge_row = QHBoxLayout()
        badge_row.addStretch()
        badge_row.addWidget(self._badge)
        layout.addLayout(badge_row)
        layout.addWidget(self._title_lbl)

        self._refresh_style()

    # ── Public ─────────────────────────────────────────────────────────────────

    def set_slot(self, slot):
        """Set slot to "A", "B", or None."""
        self.slot = slot
        self._refresh_style()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _slot_color(self):
        if self.slot == "A":
            return _COLOR_A
        if self.slot == "B":
            return _COLOR_B
        return _COLOR_IDLE_HV if self._hovered else _COLOR_IDLE

    def _refresh_style(self):
        color = self._slot_color()
        border = _COLOR_A if self.slot == "A" else (_COLOR_B if self.slot == "B" else _COLOR_BORDER)
        self.setStyleSheet(
            f"QFrame#listCard {{ background: {color}; border: 2px solid {border}; border-radius: 6px; }}"
        )
        if self.slot:
            self._badge.setText(self.slot)
            self._badge.setStyleSheet(
                "color: white; background: rgba(0,0,0,40%); border-radius: 10px;"
            )
        else:
            self._badge.setText("")
            self._badge.setStyleSheet("background: transparent;")

    def enterEvent(self, event):
        self._hovered = True
        self._refresh_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._refresh_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self)
        super().mousePressEvent(event)


# ══════════════════════════════════════════════════════════════════════════════

class Compare(QMdiSubWindow):

    resized = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("frmCompare")
        self.setWindowTitle("Compare Lists")
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.mdiParent = ""

        from PySide6.QtGui import QIcon, QPixmap
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_compare_white.png"))
        self.setWindowIcon(icon)

        self._card_a = None   # _ListCard currently in slot A
        self._card_b = None   # _ListCard currently in slot B
        self._cards  = []     # all _ListCard widgets

        self._build_ui()

        self.resized.connect(self.resizeMe)
        self.lstLeftOnly.itemClicked.connect(self.ListLeftClicked)
        self.lstRightOnly.itemClicked.connect(self.ListRightClicked)
        self.lstBoth.itemClicked.connect(self.ListBothClicked)

        self.webView   = QWebEngineView()
        self.myPrinter = QPrinter(QPrinter.HighResolution)

        red   = str(code_Stylesheet.speciesColor.red())
        green = str(code_Stylesheet.speciesColor.green())
        blue  = str(code_Stylesheet.speciesColor.blue())
        species_style = (
            f"QListWidget {{color: rgb({red},{green},{blue}); font-weight: bold; "
            f"background: #252730}}"
        )
        self.lstLeftOnly.setStyleSheet(species_style)
        self.lstRightOnly.setStyleSheet(species_style)
        self.lstBoth.setStyleSheet(species_style)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        """Build the entire UI programmatically."""
        container = QWidget()
        self.setWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # ── Card gallery row ──────────────────────────────────────────────────
        gallery_scroll = QScrollArea()
        gallery_scroll.setFrameShape(QFrame.Shape.NoFrame)
        gallery_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        gallery_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        gallery_scroll.setMinimumHeight(_CARD_H + 20)
        gallery_scroll.setMaximumHeight(_CARD_H * 2)
        gallery_scroll.setWidgetResizable(True)

        gallery_widget = QWidget()
        self._gallery_layout = QHBoxLayout(gallery_widget)
        self._gallery_layout.setContentsMargins(4, 4, 4, 4)
        self._gallery_layout.setSpacing(8)
        self._gallery_layout.addStretch()

        gallery_scroll.setWidget(gallery_widget)
        root.addWidget(gallery_scroll)

        # ── Instruction label ─────────────────────────────────────────────────
        self._lbl_instruction = QLabel(
            "Click a card to select List A, then click another to select List B and compare."
        )
        self._lbl_instruction.setAlignment(Qt.AlignCenter)
        self._lbl_instruction.setStyleSheet("color: #8b8fa8; font-style: italic;")
        root.addWidget(self._lbl_instruction)

        # ── Results scroll area ───────────────────────────────────────────────
        self.scrollArea = QScrollArea()
        self.scrollArea.setFrameShape(QFrame.Shape.NoFrame)
        self.scrollArea.setWidgetResizable(True)
        root.addWidget(self.scrollArea)

        results_widget = QWidget()
        # A 3x3 grid (row 0 = list titles, row 1 = "only on this list" counts,
        # row 2 = the species lists).  Because every grid row shares a single
        # height across all columns, the three list widgets (row 2) always start
        # at the same y — even when a title wraps to two lines and the centre
        # column has no title.  Equal column stretch keeps the widths matched.
        results_layout = QGridLayout(results_widget)
        results_layout.setContentsMargins(5, 5, 5, 5)
        results_layout.setHorizontalSpacing(2)
        results_layout.setVerticalSpacing(5)
        self.scrollArea.setWidget(results_widget)

        # Row 0 — list titles (centre column has no title)
        self._lbl_a_name = QLabel("")
        self._lbl_a_name.setWordWrap(True)
        self._lbl_a_name.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._lbl_a_name.setStyleSheet(f"color: {_COLOR_A}; font-weight: bold;")
        results_layout.addWidget(self._lbl_a_name, 0, 0)

        self._lbl_b_name = QLabel("")
        self._lbl_b_name.setWordWrap(True)
        self._lbl_b_name.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._lbl_b_name.setStyleSheet(f"color: {_COLOR_B}; font-weight: bold;")
        results_layout.addWidget(self._lbl_b_name, 0, 2)

        # Row 1 — per-column counts (centre cell stays empty so its list still
        # lines up with the side lists)
        self.lblLeftListOnly = QLabel("This List Only")
        self.lblLeftListOnly.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        results_layout.addWidget(self.lblLeftListOnly, 1, 0)

        self.lblBothLists = QLabel("Species on Both Lists")
        self.lblBothLists.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        results_layout.addWidget(self.lblBothLists, 1, 1)

        self.lblRightListOnly = QLabel("This List Only")
        self.lblRightListOnly.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        results_layout.addWidget(self.lblRightListOnly, 1, 2)

        # Row 2 — the species lists
        self.lstLeftOnly = QListWidget()
        results_layout.addWidget(self.lstLeftOnly, 2, 0)

        self.lstBoth = QListWidget()
        results_layout.addWidget(self.lstBoth, 2, 1)

        self.lstRightOnly = QListWidget()
        results_layout.addWidget(self.lstRightOnly, 2, 2)

        # Equal column widths; only the list row grows vertically.
        for col in range(3):
            results_layout.setColumnStretch(col, 1)
        results_layout.setRowStretch(2, 1)

    # ── Card interaction ───────────────────────────────────────────────────────

    def _on_card_clicked(self, card: _ListCard):
        if card.slot == "A":
            # Deselect A; promote B to A if present
            card.set_slot(None)
            self._card_a = None
            if self._card_b is not None:
                self._card_b.set_slot("A")
                self._card_a = self._card_b
                self._card_b = None
            self._clear_results()

        elif card.slot == "B":
            # Deselect B
            card.set_slot(None)
            self._card_b = None
            self._clear_results()

        else:
            # Unselected card
            if self._card_a is None:
                card.set_slot("A")
                self._card_a = card
                self._clear_results()
            else:
                # A is already set — replace B (deselect old B first) and compare
                if self._card_b is not None:
                    self._card_b.set_slot(None)
                card.set_slot("B")
                self._card_b = card
                self.CompareLists()

    # ── List population ────────────────────────────────────────────────────────

    def FillListChoices(self):
        self._cards.clear()
        # Remove old cards (leave the trailing stretch)
        while self._gallery_layout.count() > 1:
            item = self._gallery_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._card_a = None
        self._card_b = None
        self._clear_results()

        titles = []
        for window in self.mdiParent.mdiArea.subWindowList():
            if window.objectName() == "frmSpeciesList":
                titles.append(window.windowTitle())
        titles.sort()

        for title in titles:
            card = _ListCard(title)
            card.clicked.connect(self._on_card_clicked)
            self._gallery_layout.insertWidget(self._gallery_layout.count() - 1, card)
            self._cards.append(card)

        # Watch the MDI viewport for windows being added or removed.
        # QMdiArea is a QAbstractScrollArea; subwindows are children of its
        # viewport, so ChildAdded/ChildRemoved events go there, not to mdiArea.
        self.mdiParent.mdiArea.viewport().installEventFilter(self)

        if len(titles) < 2:
            return False

        # If exactly two lists are available, there's only one possible
        # comparison — pre-assign them to A and B and show it immediately.
        if len(self._cards) == 2:
            self._cards[0].set_slot("A")
            self._card_a = self._cards[0]
            self._cards[1].set_slot("B")
            self._card_b = self._cards[1]
            self.CompareLists()

        self.scaleMe()
        self.resizeMe()
        return True

    # ── Comparison logic ───────────────────────────────────────────────────────

    def CompareLists(self):
        self.lstLeftOnly.clear()
        self.lstBoth.clear()
        self.lstRightOnly.clear()

        if self._card_a is None or self._card_b is None:
            return

        left_title  = self._card_a.title
        right_title = self._card_b.title

        def _fetch(title):
            species = []
            for window in self.mdiParent.mdiArea.subWindowList():
                if window.objectName() == "frmSpeciesList" and window.windowTitle() == title:
                    for s in window.currentSpeciesList:
                        if "(" in s:
                            s = s.split(" (")[0]
                        if "/" not in s and " x " not in s and "sp." not in s:
                            species.append(s)
            return species

        left_species  = _fetch(left_title)
        right_species = _fetch(right_title)

        both_lists   = []
        left_only    = []
        right_only   = []

        for s in left_species:
            if s in right_species:
                if s not in both_lists:
                    both_lists.append(s)
            else:
                if s not in left_only:
                    left_only.append(s)

        for s in right_species:
            if s in left_species:
                if s not in both_lists:
                    both_lists.append(s)
            else:
                if s not in right_only:
                    right_only.append(s)

        self.lstLeftOnly.addItems(left_only)
        self.lstLeftOnly.setSpacing(2)
        self.lstBoth.addItems(both_lists)
        self.lstBoth.setSpacing(2)
        self.lstRightOnly.addItems(right_only)
        self.lstRightOnly.setSpacing(2)

        self.lblLeftListOnly.setText(f"Species only on this list: {self.lstLeftOnly.count()}")
        self.lblBothLists.setText(f"Species on both lists: {self.lstBoth.count()}")
        self.lblRightListOnly.setText(f"Species only on this list: {self.lstRightOnly.count()}")

        # Drop the redundant "Species: " prefix in the top column labels — the
        # comparison is plainly about species and the white sub-titles say so.
        self._lbl_a_name.setText(left_title.removeprefix("Species: "))
        self._lbl_b_name.setText(right_title.removeprefix("Species: "))
        self._lbl_instruction.hide()

    def _clear_results(self):
        self.lstLeftOnly.clear()
        self.lstBoth.clear()
        self.lstRightOnly.clear()
        self.lblLeftListOnly.setText("This List Only")
        self.lblBothLists.setText("Species on Both Lists")
        self.lblRightListOnly.setText("This List Only")
        self._lbl_a_name.setText("")
        self._lbl_b_name.setText("")
        self._lbl_instruction.show()

    # ── HTML export ────────────────────────────────────────────────────────────

    def html(self):
        left_title  = self._card_a.title if self._card_a else ""
        right_title = self._card_b.title if self._card_b else ""

        html = """
            <!DOCTYPE html>
            <html>
            <head>
            </head>
            <style>
            * {
                font-size: 75%;
                font-family: "Times New Roman", Times, serif;
                }
            table, th, td {
                border-collapse: collapse;
            }
            th, td {
                padding: 5px;
            }
            th {
                text-align: left;
            }
            </style>
            <body>
            """

        html += "<H1>List Comparison</H1>"

        html += f"<H2>Species only on {left_title}</H2><font size='2'>"
        for r in range(self.lstLeftOnly.count()):
            html += f"<br>{self.lstLeftOnly.item(r).text()}</br>"
        html += "</font>"

        html += f"<H2>Species only on {right_title}</H2><font size='2'>"
        for r in range(self.lstRightOnly.count()):
            html += f"<br>{self.lstRightOnly.item(r).text()}</br>"
        html += "</font>"

        html += "<H2>Species on Both Lists</H2><font size='2'>"
        for r in range(self.lstBoth.count()):
            html += f"<br>{self.lstBoth.item(r).text()}</br>"
        html += "</font>"

        html += "<font size></body></html>"
        return html

    # ── Species-detail drill-down ──────────────────────────────────────────────

    def ListLeftClicked(self):
        self.CreateNewIndividual(self.lstLeftOnly.currentItem().text())

    def ListRightClicked(self):
        self.CreateNewIndividual(self.lstRightOnly.currentItem().text())

    def ListBothClicked(self):
        self.CreateNewIndividual(self.lstBoth.currentItem().text())

    def CreateNewIndividual(self, speciesName):
        sub = code_Individual.Individual()
        sub.mdiParent = self.mdiParent
        sub.FillIndividual(speciesName)
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)
        sub.show()
        sub.resizeMe()

    # ── MDI area tracking ──────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        # mdiParent starts as "" until assigned; ignore until it's the real window
        if not isinstance(self.mdiParent, str):
            if obj is self.mdiParent.mdiArea.viewport():
                if event.type() in (QEvent.Type.ChildAdded, QEvent.Type.ChildRemoved):
                    QTimer.singleShot(0, self._sync_cards)
        return super().eventFilter(obj, event)

    def _sync_cards(self):
        """Reconcile the card gallery with the currently open frmSpeciesList windows."""
        # Build the authoritative set of titles from the MDI area
        current_titles = set()
        for window in self.mdiParent.mdiArea.subWindowList():
            if window.objectName() == "frmSpeciesList":
                current_titles.add(window.windowTitle())

        existing_titles = {card.title for card in self._cards}

        # Remove cards for windows that are no longer open
        slot_cleared = False
        for card in list(self._cards):
            if card.title not in current_titles:
                if card is self._card_a:
                    self._card_a = None
                    slot_cleared = True
                if card is self._card_b:
                    self._card_b = None
                    slot_cleared = True
                self._gallery_layout.removeWidget(card)
                card.deleteLater()
                self._cards.remove(card)

        if slot_cleared:
            self._clear_results()

        # Add cards for newly opened windows, inserting in sorted order
        for title in sorted(current_titles - existing_titles):
            card = _ListCard(title)
            card.clicked.connect(self._on_card_clicked)
            # Insert before the trailing stretch (last item)
            self._gallery_layout.insertWidget(self._gallery_layout.count() - 1, card)
            self._cards.append(card)

    def closeEvent(self, event):
        if not isinstance(self.mdiParent, str) and hasattr(self.mdiParent, 'mdiArea'):
            self.mdiParent.mdiArea.viewport().removeEventFilter(self)
        super().closeEvent(event)

    # ── Resize handling ────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        self.resized.emit()
        return super().resizeEvent(event)

    def resizeMe(self):
        pass  # QMdiSubWindow manages the inner widget's geometry automatically

    def scaleMe(self):
        scaleFactor = self.mdiParent.scaleFactor
        windowWidth  = int(900 * scaleFactor)
        windowHeight = int(550 * scaleFactor)
        self.resize(windowWidth, windowHeight)

        fontSize    = self.mdiParent.fontSize
        for w in self.findChildren(QWidget):
            try:
                w.setFont(QFont("", fontSize))
            except Exception:
                pass

        # Species columns use QFont() (app-default size) to match the font size
        # that code_Lists.py uses for its species table items.
        _list_font = QFont()
        for lst in (self.lstLeftOnly, self.lstBoth, self.lstRightOnly):
            lst.setFont(_list_font)
