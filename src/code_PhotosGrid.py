# Browse Grid — the Photos browser laid out as a thumbnail grid.
#
# Same window, same data, same loading machinery as the card view: this is a
# subclass of code_Photos.Photos and reuses its form (header labels, the four
# sort radios, the Slideshow button), its worker pool and disk cache, the drain
# timer and progress overlay, sorting, deletion handling, print/PDF and the
# slideshow.  Only the arrangement of cells differs, so only the layout hooks
# are overridden — see the "Subclass seam" note in code_Photos.
#
# Why a subclass rather than a copy: code_SpeciesGallery and
# code_RecordingsSpeciesGallery are near-identical files, and the same
# ghost-cell and thread-restart bugs had to be fixed twice, once in each.  A fix
# in Photos now reaches both views.
#
# Why rows of cells rather than a QGridLayout: Qt caps a QGridLayout's total
# height at ~524k px (the reason the card view abandoned it), which a grid of
# 200x150 cells would hit around 8,000-12,000 photos depending on the column
# count.  Chunking cells into per-row container widgets inside the inherited
# rowsLayout has no such cap.

import code_Photos
import code_ThumbnailCache

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from functools import partial


CELL_SPACING = 6     # gap between cells, and between rows of cells
CAPTION_H    = 34    # room under the thumbnail for the species name (2 lines)
CELL_PADDING = 12    # card margins around the thumbnail (6 per side)
DEFAULT_COLS = 4     # columns the window opens sized to


class PhotosGrid(code_Photos.Photos):

    # Browse Grid loads its own small cached artifact instead of scaling the
    # card view's 500x330 thumbnail down at paint time: ~104 KB of pixmap
    # memory per photo against ~638 KB, which is what makes a 1,000-photo grid
    # practical.  Manage Photos builds it at add time (prebuild_async); older
    # catalogs derive it from the big thumbnail on first view.
    THUMB_KIND = "photo_grid"
    CELL_SIZE  = code_ThumbnailCache.GRID_THUMB_SIZE

    def __init__(self):
        super().__init__()
        self._numCols   = 4     # recomputed from the viewport before each build
        self._cellWidgets = []  # cell container per photo, in photoList order
        self._rowContainers = []

    # ── Layout ────────────────────────────────────────────────────────────────

    def _calcCols(self):
        """Columns that fit the scroll-area viewport at the current width.

        The initial build runs while the window is still hidden (the browser is
        revealed only once contentReady fires), so the viewport has no real
        geometry yet — fall back to the window's own width, or the first build
        would lay every photo out in a single column and need a full reflow the
        moment it appeared.
        """
        # Measure against the CARD's width (thumbnail + its padding), not the
        # thumbnail alone, or the rightmost column is clipped by the viewport.
        cellW = self.CELL_SIZE.width() + CELL_PADDING + CELL_SPACING
        available = self.scrollArea.viewport().width() - 20   # margins + buffer
        if available < cellW:
            available = self.width() - 60   # hidden build: allow for the scrollbar
        return max(1, available // cellW)

    def _beginLayout(self):
        """Drop every cell and row container from the previous fill.

        removeWidget alone leaves a widget parented and painted, so cells are
        hidden and unparented before deleteLater — otherwise the outgoing fill
        stays on screen behind the new one.
        """
        for w in self._rowContainers:
            self.rowsLayout.removeWidget(w)
            w.hide()
            w.setParent(None)
            w.deleteLater()
        self._rowContainers = []
        self._cellWidgets = []
        self._numCols = self._calcCols()

    def _addCell(self, row, p, s):
        """One thumbnail + species name, appended to the row being filled."""
        imgLabel = QLabel()
        imgLabel.setFixedSize(self.CELL_SIZE)
        imgLabel.setAlignment(Qt.AlignCenter)
        imgLabel.setCursor(Qt.PointingHandCursor)
        imgLabel.mousePressEvent = partial(self._photoClicked, row)

        nameLabel = QLabel(s["commonName"])
        nameLabel.setFixedWidth(self.CELL_SIZE.width())
        nameLabel.setFixedHeight(CAPTION_H)
        nameLabel.setWordWrap(True)
        nameLabel.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        nameLabel.setObjectName("mediaCaption")

        cell = QWidget()
        cell.setObjectName("mediaCard")
        cell.setAttribute(Qt.WA_StyledBackground, True)
        cell.setFixedSize(self.CELL_SIZE.width() + 12,
                          self.CELL_SIZE.height() + CAPTION_H + 12)
        cell.setCursor(Qt.PointingHandCursor)
        # The whole card is clickable, not just the thumbnail, so the caption
        # and the padding around it open the photo too.
        cell.mousePressEvent = partial(self._photoClicked, row)
        # Full detail on hover — the card view's caption in tooltip form.
        cell.setToolTip(
            f'{s["commonName"]}\n{s["scientificName"]}\n'
            f'{s["location"]}\n{self.captureDateLine(p, s)}\n'
            f'Rating: {p["rating"]}'
        )

        lay = QVBoxLayout(cell)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(0)
        lay.addWidget(imgLabel, 0, Qt.AlignHCenter)
        lay.addWidget(nameLabel, 0, Qt.AlignHCenter)

        self._cellWidgets.append(cell)
        self._photoButtons[row] = imgLabel   # the drain fills this
        self._rowWidgets[row] = cell

        # Start a new row container whenever the current one is full.
        if row % self._numCols == 0:
            self._rowContainers.append(self._newRowContainer())
        self._rowContainers[-1].layout().insertWidget(
            self._rowContainers[-1].layout().count() - 1, cell)

    def _endLayout(self):
        pass   # rows are flushed as they fill; nothing to close out

    def _newRowContainer(self):
        """A left-aligned row of cells, appended to the inherited vertical spine."""
        rowWidget = QWidget()
        lay = QHBoxLayout(rowWidget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(CELL_SPACING)
        lay.addStretch(1)          # keeps a short last row left-aligned
        self.rowsLayout.addWidget(rowWidget)
        # Explicit show: adding to a layout reparents the widget, which sets its
        # hidden flag, so a container created during a reflow (window already
        # visible) would never appear — the grid went blank on the first resize.
        # It has a parent by now, so this cannot create a stray native window.
        rowWidget.show()
        return rowWidget

    def _reflowCells(self):
        """Re-chunk the existing cells into rows — after a sort, a column-count
        change, or a deletion.  Never touches thumbnails, so it costs nothing
        beyond re-parenting."""
        # Detach the cells BEFORE discarding the containers: cells are children
        # of their row container, so deleting a container would take its cells
        # with it.  deleteLater defers to the event loop, but re-parenting first
        # means that ordering never has to be relied on.
        for cell in self._cellWidgets:
            cell.setParent(None)
        for w in self._rowContainers:
            self.rowsLayout.removeWidget(w)
            w.hide()
            w.setParent(None)
            w.deleteLater()
        self._rowContainers = []

        for i, cell in enumerate(self._cellWidgets):
            if i % self._numCols == 0:
                self._rowContainers.append(self._newRowContainer())
            lay = self._rowContainers[-1].layout()
            lay.insertWidget(lay.count() - 1, cell)
            cell.show()

    # ── Qt event overrides ────────────────────────────────────────────────────

    def resizeEvent(self, event):
        # Defer until Qt has finished the layout pass, so the viewport reports
        # its final width (same reason as the Species Gallery's reflow).
        QTimer.singleShot(0, self._onResize)
        return super().resizeEvent(event)

    def _onResize(self):
        if self._abort or not self._cellWidgets:
            return
        newCols = self._calcCols()
        if newCols != self._numCols:
            self._numCols = newCols
            self._reflowCells()

    # ── Sorting / deletion ────────────────────────────────────────────────────

    def SortAndDisplayPhotos(self):
        """Radio-button sort: permute the existing cells, no rebuild.

        Mirrors the card view — refused while the initial load is running,
        because in-flight worker results are addressed to the old row numbers.
        """
        if not self.photoList:
            return
        if self._sorting or self._building or self.threadsRemaining > 0:
            return
        if not self._cellWidgets:
            self._buildRows()
            return
        self._sorting = True

        order = self._sortPhotoList()

        self._cellWidgets = [self._cellWidgets[i] for i in order]
        newButtons, newRows = {}, {}
        for new_row, old_row in enumerate(order):
            btn = self._photoButtons.get(old_row)
            cell = self._rowWidgets.get(old_row)
            if btn is not None:
                btn.mousePressEvent = partial(self._photoClicked, new_row)
                newButtons[new_row] = btn
            if cell is not None:
                cell.mousePressEvent = partial(self._photoClicked, new_row)
                newRows[new_row] = cell
        self._photoButtons = newButtons
        self._rowWidgets = newRows

        self._reflowCells()
        self.scrollArea.verticalScrollBar().setValue(0)
        self._sorting = False

    def handlePhotoDeletion(self, filename):
        """A photo left the catalog — drop its cell and re-chunk the rows."""
        self.pixmapCache.pop(filename, None)

        idx = next((i for i, (p, s) in enumerate(self.photoList)
                    if p["fileName"] == filename), None)
        if idx is None:
            return

        cell = self._cellWidgets.pop(idx) if idx < len(self._cellWidgets) else None
        if cell is not None:
            cell.hide()
            cell.setParent(None)
            cell.deleteLater()

        self.photoList.pop(idx)

        if not self.photoList:
            self.close()
            return

        # Re-index the row-keyed maps past the removed cell.
        newButtons, newRows = {}, {}
        for old_row in sorted(self._photoButtons.keys()):
            if old_row == idx:
                continue
            new_row = old_row if old_row < idx else old_row - 1
            btn = self._photoButtons[old_row]
            if new_row != old_row:
                btn.mousePressEvent = partial(self._photoClicked, new_row)
            newButtons[new_row] = btn
            cellW = self._rowWidgets.get(old_row)
            if cellW is not None:
                if new_row != old_row:
                    cellW.mousePressEvent = partial(self._photoClicked, new_row)
                newRows[new_row] = cellW
        self._photoButtons = newButtons
        self._rowWidgets = newRows

        self._reflowCells()
        self._refreshCounts()

    # ── Window geometry ───────────────────────────────────────────────────────

    def _widthForCols(self, cols):
        """Window width that fits exactly `cols` columns with no dead space.

        Derived rather than hardcoded so it stays right if the cell size,
        padding or spacing changes.  Inverts the chain _calcCols reads through:
        window -> scrollArea (resizeMe insets 15) -> viewport (less the
        scrollbar) -> the 20px buffer _calcCols subtracts.
        """
        cellW = self.CELL_SIZE.width() + CELL_PADDING + CELL_SPACING
        scrollbar = self.scrollArea.verticalScrollBar().sizeHint().width()
        return cols * cellW + 20 + scrollbar + 15

    def scaleMe(self):
        """Open exactly DEFAULT_COLS columns wide — cells are a fixed pixel
        size, so the width must not be multiplied by the UI scale factor or the
        last column would no longer fit.  A single-photo window keeps the base
        class's compact size."""
        super().scaleMe()
        if len(self.photoList) == 1:
            return
        self.resize(self._widthForCols(DEFAULT_COLS),
                    int(800 * self.mdiParent.scaleFactor))
