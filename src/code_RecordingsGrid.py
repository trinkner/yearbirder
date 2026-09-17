# Browse Grid for recordings — the Recordings browser laid out as a grid.
#
# The counterpart of code_PhotosGrid: a subclass of code_Recordings.Recordings
# reusing its form (header labels, the four sort radios), its worker pool and
# spectrogram cache, the drain timer and progress overlay, sorting, deletion
# handling, and the Recording Enlargement launch.  Only the arrangement of cells
# is overridden — see the "Subclass seam" note in code_Recordings.
#
# Each cell keeps the Play/Pause button and the scrubber, so a recording can be
# auditioned without leaving the grid.  Playback itself needs no changes: the
# window has one shared player keyed by _activeRow, which is layout-agnostic.
#
# Cells display the EXISTING 333x220 spectrogram artifact scaled down rather
# than a separately rendered small one.  SpectrogramLabel scales in paintEvent
# and maps the cursor line through the same axes bbox, so this costs nothing and
# needs no new cache kind; the trade is that the baked-in kHz/sec axis labels
# shrink with it and read as texture rather than as numbers.  If they are ever
# wanted legible at this size, the fix is a separately rendered axis-free
# artifact selected through SPECTRO_SIZE and a new cache kind — the layout code
# below would not change.

import code_Recordings
import code_ThumbnailCache

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from functools import partial


# Wider than the photo grid's 200px cell: the Play button is a fixed 60px and
# the scrubber needs usable travel beside it.
CELL_W       = 260
CELL_SPACING = 6
# Species name: TWO lines.  Plain common names fit one 15px line at this width,
# but hybrid and subspecies forms do not — "Greater White-fronted x Canada Goose
# (hybrid)" and "Yellow-rumped Warbler (Myrtle x Audubon's)" both wrap.  Sizing
# to one line reclaims ~13px per cell and truncates those names, so the second
# line stays.
# One measured line for the species name — see code_PhotosGrid for why, and
# for what happens to the rare name too wide to fit.
DATE_H       = 16    # one line under the name for the recording date
CELL_PADDING = 12    # card margins around the contents (6 per side)
PLAY_STRIP_H = 28    # Play button / scrubber height
STRIP_GAP    = 7     # gap between spectrogram and the play strip
DEFAULT_COLS = 3     # columns the window opens sized to


class RecordingsGrid(code_Recordings.Recordings):

    # 333x220 scaled to the cell width, keeping the spectrogram's aspect so the
    # cursor line stays aligned with the audio.
    SPECTRO_SIZE = QSize(
        CELL_W,
        round(CELL_W * code_ThumbnailCache.THUMB_DISPLAY_SIZE.height()
              / code_ThumbnailCache.THUMB_DISPLAY_SIZE.width()),
    )
    # A few recordings sit on the opening row (DEFAULT_COLS wide), so the
    # window can fit its height to that one row instead of opening tall.
    FIT_TO_CONTENT_MAX = 3

    def __init__(self):
        super().__init__()
        self._numCols = DEFAULT_COLS
        self._captionH = None   # measured on first use (see _captionHeight)
        self._cellWidgets = []      # cell container per recording, in audioList order
        self._rowContainers = []

    # ── Layout ────────────────────────────────────────────────────────────────

    def _captionHeight(self):
        """One line of the caption font plus the stylesheet's 3px padding."""
        if self._captionH is None:
            probe = QLabel()
            probe.setObjectName("mediaCaption")
            self._captionH = QFontMetrics(probe.font()).height() + 6
        return self._captionH

    def _calcCols(self):
        """Columns that fit the scroll-area viewport at the current width."""
        cellW = CELL_W + CELL_PADDING + CELL_SPACING
        available = self.scrollArea.viewport().width() - 20
        if available < cellW:
            available = self.width() - 60   # not laid out yet; allow for the scrollbar
        return max(1, available // cellW)

    def _widthForCols(self, cols):
        """Window width fitting exactly `cols` columns, with no dead space."""
        cellW = CELL_W + CELL_PADDING + CELL_SPACING
        scrollbar = self.scrollArea.verticalScrollBar().sizeHint().width()
        return cols * cellW + 20 + scrollbar + 15

    def _beginLayout(self):
        for w in self._rowContainers:
            self.rowsLayout.removeWidget(w)
            w.hide()
            w.setParent(None)
            w.deleteLater()
        self._rowContainers = []
        self._cellWidgets = []
        self._numCols = self._calcCols()

    def _addCell(self, row, a, s):
        """Spectrogram + Play/scrubber strip + species name, as one card."""
        fileName = a.get("fileName", "")

        spectroLabel = code_Recordings.SpectrogramLabel()
        spectroLabel.setFixedSize(self.SPECTRO_SIZE)
        spectroLabel.setCursor(Qt.PointingHandCursor)
        spectroLabel.mousePressEvent = partial(self._spectroClicked, row)

        playBtn = QPushButton("Play")
        playBtn.setFixedWidth(60)
        playBtn.setFixedHeight(PLAY_STRIP_H)
        playBtn.clicked.connect(partial(self._btnPlayClicked, row))

        scrubber = QSlider(Qt.Orientation.Horizontal)
        scrubber.setRange(0, 1000)
        scrubber.setValue(0)
        scrubber.setFixedHeight(PLAY_STRIP_H)
        scrubber.sliderMoved.connect(partial(self._onSliderMoved, row))

        scrubRow = QWidget()
        scrubRow.setObjectName("cardTransparent")
        scrubLayout = QHBoxLayout(scrubRow)
        scrubLayout.setContentsMargins(2, 0, 2, 0)
        scrubLayout.setSpacing(4)
        scrubLayout.addWidget(playBtn)
        scrubLayout.addWidget(scrubber)

        captionH = self._captionHeight()
        nameLabel = QLabel()
        nameLabel.setFixedWidth(CELL_W)
        nameLabel.setFixedHeight(captionH)
        nameLabel.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        nameLabel.setObjectName("mediaCaption")
        nameLabel.setText(QFontMetrics(nameLabel.font()).elidedText(
            s["commonName"], Qt.ElideRight, CELL_W - 6))

        dateLabel = QLabel(self.captureDate(a, s))
        dateLabel.setFixedWidth(CELL_W)
        dateLabel.setFixedHeight(DATE_H)
        dateLabel.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        dateLabel.setObjectName("mediaCaptionDate")

        cell = QWidget()
        cell.setObjectName("mediaCard")
        cell.setAttribute(Qt.WA_StyledBackground, True)
        cell.setFixedSize(
            CELL_W + CELL_PADDING,
            self.SPECTRO_SIZE.height() + STRIP_GAP + PLAY_STRIP_H
            + captionH + DATE_H + CELL_PADDING,
        )
        # Full detail on hover — the card view's caption in tooltip form.  The
        # card itself is NOT click-to-open: the Play button and scrubber live
        # inside it, so opening the Enlargement stays on the spectrogram.
        cell.setToolTip(
            f'{s["commonName"]}\n{s["scientificName"]}\n'
            f'{s["location"]}\n{self.captureDateLine(a, s)}\n'
            f'Rating: {a.get("rating", "0")}'
        )

        lay = QVBoxLayout(cell)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(0)
        lay.addWidget(spectroLabel, 0, Qt.AlignHCenter)
        lay.addSpacing(STRIP_GAP)
        lay.addWidget(scrubRow)
        lay.addWidget(nameLabel, 0, Qt.AlignHCenter)
        lay.addWidget(dateLabel, 0, Qt.AlignHCenter)

        self._cellWidgets.append(cell)
        self._spectroLabels[row] = spectroLabel
        self._playBtns[row] = playBtn
        self._sliders[row] = scrubber
        self._filePaths[row] = fileName
        self._rowWidgets[row] = cell

        if row % self._numCols == 0:
            self._rowContainers.append(self._newRowContainer())
        lay_row = self._rowContainers[-1].layout()
        lay_row.insertWidget(lay_row.count() - 1, cell)

    def _endLayout(self):
        pass

    def _newRowContainer(self):
        rowWidget = QWidget()
        lay = QHBoxLayout(rowWidget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(CELL_SPACING)
        lay.addStretch(1)          # keeps a short last row left-aligned
        self.rowsLayout.addWidget(rowWidget)
        # Explicit show: adding to a layout reparents the widget, which sets its
        # hidden flag, so a container created during a reflow would never appear.
        rowWidget.show()
        return rowWidget

    def _reflowCells(self):
        """Re-chunk the existing cells into rows — after a sort, a column-count
        change, or a deletion.  Detach the cells before discarding the old
        containers: cells are children of their container."""
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

    def SortAndDisplayRecordings(self):
        """Radio-button sort: permute the existing cells, no rebuild.

        Playback stops first, as the card view does, so scrubber state can't be
        left attached to a row number that has moved.
        """
        if not self.audioList:
            return
        if self._sorting or self.threadsRemaining > 0:
            return
        if not self._cellWidgets:
            self._buildRows()
            return
        self._sorting = True

        from PySide6.QtMultimedia import QMediaPlayer
        if self._player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
            self._player.stop()
        self._activeRow = None

        order = self._sortAudioList()

        self._cellWidgets = [self._cellWidgets[i] for i in order]
        newRows, newSpectros, newBtns, newSliders, newPaths = {}, {}, {}, {}, {}
        for new_row, old_row in enumerate(order):
            cell = self._rowWidgets.get(old_row)
            if cell is not None:
                newRows[new_row] = cell
            lbl = self._spectroLabels.get(old_row)
            if lbl is not None:
                lbl.mousePressEvent = partial(self._spectroClicked, new_row)
                newSpectros[new_row] = lbl
            btn = self._playBtns.get(old_row)
            if btn is not None:
                btn.clicked.disconnect()
                btn.clicked.connect(partial(self._btnPlayClicked, new_row))
                newBtns[new_row] = btn
            sld = self._sliders.get(old_row)
            if sld is not None:
                sld.sliderMoved.disconnect()
                sld.sliderMoved.connect(partial(self._onSliderMoved, new_row))
                newSliders[new_row] = sld
            if old_row in self._filePaths:
                newPaths[new_row] = self._filePaths[old_row]
        self._rowWidgets = newRows
        self._spectroLabels = newSpectros
        self._playBtns = newBtns
        self._sliders = newSliders
        self._filePaths = newPaths

        self._reflowCells()
        self.scrollArea.verticalScrollBar().setValue(0)
        self._sorting = False

    def handleAudioDeletion(self, filename, species=None):
        """A recording left the catalog — drop its cell and re-chunk the rows."""
        orig_len = len(self.audioList)
        keep = [i for i, (a, s) in enumerate(self.audioList)
                if not (a.get("fileName") == filename
                        and (species is None
                             or s.get("commonName") == species))]
        if len(keep) == orig_len:
            return

        # Stop playback if the card that was playing is one of the departing ones.
        if self._activeRow is not None and self._activeRow not in keep:
            self._player.stop()
            self._activeRow = None

        for i in range(orig_len):
            if i in keep:
                continue
            cell = self._rowWidgets.get(i)
            if cell is not None:
                cell.hide()
                cell.setParent(None)
                cell.deleteLater()

        self.audioList = [self.audioList[i] for i in keep]
        self._cellWidgets = [self._cellWidgets[i] for i in keep
                             if i < len(self._cellWidgets)]

        if not any(a.get("fileName") == filename for (a, s) in self.audioList):
            self.spectroCache.pop(filename, None)

        if not self.audioList:
            self.close()
            return

        # Re-index the row-keyed maps and rebind the baked-in row numbers.
        newRows, newSpectros, newBtns, newSliders, newPaths = {}, {}, {}, {}, {}
        for new_row, old_row in enumerate(keep):
            cell = self._rowWidgets.get(old_row)
            if cell is not None:
                newRows[new_row] = cell
            lbl = self._spectroLabels.get(old_row)
            if lbl is not None:
                lbl.mousePressEvent = partial(self._spectroClicked, new_row)
                newSpectros[new_row] = lbl
            btn = self._playBtns.get(old_row)
            if btn is not None:
                btn.clicked.disconnect()
                btn.clicked.connect(partial(self._btnPlayClicked, new_row))
                newBtns[new_row] = btn
            sld = self._sliders.get(old_row)
            if sld is not None:
                sld.sliderMoved.disconnect()
                sld.sliderMoved.connect(partial(self._onSliderMoved, new_row))
                newSliders[new_row] = sld
            if old_row in self._filePaths:
                newPaths[new_row] = self._filePaths[old_row]
            if self._activeRow == old_row:
                self._activeRow = new_row
        self._rowWidgets = newRows
        self._spectroLabels = newSpectros
        self._playBtns = newBtns
        self._sliders = newSliders
        self._filePaths = newPaths

        self._reflowCells()
        self._refreshCounts()

    # ── Window geometry ───────────────────────────────────────────────────────

    def scaleMe(self):
        """Open exactly DEFAULT_COLS columns wide.  Cells are a fixed pixel size,
        so the width must not be multiplied by the UI scale factor.
        FIT_TO_CONTENT_MAX recordings or fewer open only as tall as their row."""
        super().scaleMe()
        width = self._widthForCols(DEFAULT_COLS)
        if 0 < len(self.audioList) <= self.FIT_TO_CONTENT_MAX:
            height = self._fittedHeight(width)
        else:
            height = int(800 * self.mdiParent.scaleFactor)
        self.resize(width, height)
