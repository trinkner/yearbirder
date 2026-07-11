import form_ManageRecordings
from code_Stylesheet import YBFont
import code_Filter
import code_Stylesheet
import code_ThumbnailCache
import code_ChecklistTree
import code_NotesDialog
import os
import queue
import threading
import time
from functools import partial
from collections import defaultdict

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from PySide6.QtGui import QPixmap, QImage, QFont, QIcon, QPainter, QPen, QColor
from PySide6.QtCore import (
    Signal, QObject, QSize, Qt, QThread, QTimer, QIODevice,
)
from PySide6.QtWidgets import (
    QMdiSubWindow, QPushButton, QApplication, QWidget, QLabel,
    QComboBox, QHBoxLayout, QVBoxLayout, QMessageBox, QFileDialog,
    QSlider, QCheckBox, QSizePolicy, QDialog,
)
from PySide6.QtMultimedia import (
    QMediaPlayer, QAudioFormat, QAudioSink, QMediaDevices,
)


# Colours for the assignment labels.  A field's value is shown green only while
# it still equals the value auto-derived from the recording's metadata/filename;
# once the user overrides it via the tree it reverts to the neutral text colour.
_FIELD_NAME_COLOR = "#c1c1c1"          # matches the Browse windows' card text
_MATCH_COLOR      = "#4CAF50"          # green  – value came from metadata/filename
_VALUE_COLOR      = "#c1c1c1"          # neutral – manually chosen / not auto-derived
_SKIPPED_COLOR    = "#6b6e7e"          # muted value when the row is skipped
_NO_SPECIES_COLOR = "#E57373"          # red – flags a row that still needs a species picked


def _wrappable(text):
    """Insert zero-width break opportunities after separator characters.
    Word wrap can only break at whitespace, so an underscore-joined filename
    is one unbreakable word — the label's MINIMUM width becomes the full text
    width, overflowing the window and pushing the controls column past the
    right edge."""
    return "".join(c + "\u200b" if c in "_-." else c for c in text)


# ── Audio decode / spectrogram rendering / playback ──────────────────────────
# These now live in code_Audio (single source of truth for WAV sample-format
# handling, the spectrogram thumbnail render, and the persistent-sink player).
# Re-export under the names other modules already import from here so their
# imports keep working.
from code_Audio import (
    PcmAudioPlayer,
    SPECTRO_AX_BBOX,
    render_spectrogram_qimage as _render_spectrogram_qimage,
    build_spectrogram_pixmap as _build_spectrogram_pixmap,
    paint_spectro_axes as _paint_spectro_axes,
    decode_wav_pcm16 as _decode_wav_pcm16,
)


class SpectrogramLabel(QWidget):
    """Displays a spectrogram pixmap with an optional red playback-position line.

    Scaling is handled in paintEvent so the line tracks correctly when the
    widget is resized, and so no per-frame pixmap copies are needed.

    ax_bbox is a (x0, x1, y0, y1) tuple of the matplotlib axes in
    figure-fraction coordinates (origin = bottom-left).  The line is
    confined to this data rectangle so it doesn't wander into the axis
    labels / margins.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._ax_bbox = (0.0, 1.0, 0.0, 1.0)  # full-area fallback
        self._fraction = None   # 0.0–1.0; None hides the line
        self._error_text = ""
        # Same display geometry as the Manage Photos thumbnails.  FIXED height:
        # the spectrogram is rendered at exactly this size, and without a
        # maximum the widget stretched with spare row height, which let the
        # Play/scrubber strip drift over the spectrogram's white area.
        self.setMinimumWidth(code_ThumbnailCache.THUMB_DISPLAY_SIZE.width())
        self.setFixedHeight(code_ThumbnailCache.THUMB_DISPLAY_SIZE.height())

    def setPixmap(self, pixmap, ax_bbox=None):
        self._pixmap = pixmap
        if ax_bbox is not None:
            self._ax_bbox = ax_bbox
        self._error_text = ""
        self.update()

    def setFraction(self, fraction):
        self._fraction = max(0.0, min(1.0, fraction))
        self.update()

    def clearFraction(self):
        self._fraction = None
        self.update()

    def setErrorText(self, text):
        self._pixmap = None
        self._error_text = text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.white)

        if self._error_text:
            painter.setPen(QColor("#444444"))
            painter.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, self._error_text)
            painter.end()
            return

        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)

            if self._fraction is not None:
                # Convert matplotlib figure-fraction coords (origin=bottom-left)
                # to Qt widget coords within the scaled pixmap.
                ax_x0, ax_x1, ax_y0, ax_y1 = self._ax_bbox
                data_left   = x + ax_x0 * scaled.width()
                data_right  = x + ax_x1 * scaled.width()
                data_top    = y + (1.0 - ax_y1) * scaled.height()
                data_bottom = y + (1.0 - ax_y0) * scaled.height()
                line_x = int(data_left + self._fraction * (data_right - data_left))
                pen = QPen(QColor(220, 0, 0))
                pen.setWidth(1)
                painter.setPen(pen)
                painter.drawLine(line_x, int(data_top), line_x, int(data_bottom))

        painter.end()


class SpeciesTagStrip(QWidget):
    """A vertical stack of pill-shaped chips, one per associated species.

    Each chip shows the species name and an × button to remove it.  The widget
    hides itself when the species list is empty.
    """

    speciesChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._species = []
        self._skipped = False
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 2, 0, 2)
        self._layout.setSpacing(3)
        self.setVisible(False)

    def setSkipped(self, skipped):
        """Grey the chips (instead of the thematic blue) when the recording is
        being removed/skipped, to emphasise it won't be kept."""
        skipped = bool(skipped)
        if skipped != self._skipped:
            self._skipped = skipped
            self._rebuild()

    def addSpecies(self, name):
        if name and name not in self._species:
            self._species.append(name)
            self._rebuild()
            self.speciesChanged.emit()

    def removeSpecies(self, name):
        if name in self._species:
            self._species.remove(name)
            self._rebuild()
            self.speciesChanged.emit()

    def setSpeciesList(self, names):
        self._species = [n for n in names if n]
        self._rebuild()

    def getSpecies(self):
        return list(self._species)

    def _rebuild(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()
        for name in self._species:
            # Trailing stretch keeps each pill at exactly its content width no
            # matter how wide the column is — all leftover width lands in the
            # stretch, outside the blue pill.
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(self._makeChip(name))
            row.addStretch()
            self._layout.addLayout(row)
        self.setVisible(bool(self._species))

    def _makeChip(self, name):
        # All styling comes from the app stylesheet (#speciesChip /
        # #chipRemoveBtn rules, incl. the skipped-grey variant via the
        # "skipped" property and the min-width/padding zeroing that keeps the
        # × button at its true 18px).  Per-widget setStyleSheet calls here
        # cost ~13ms per row — a fresh style object + repolish per piece.
        chip = QWidget()
        chip.setObjectName("speciesChip")
        chip.setAttribute(Qt.WA_StyledBackground, True)
        chip.setProperty("skipped", self._skipped)
        chipLayout = QHBoxLayout(chip)
        chipLayout.setContentsMargins(8, 3, 5, 3)
        chipLayout.setSpacing(8)
        label = QLabel(name)
        removeBtn = QPushButton("×")
        removeBtn.setObjectName("chipRemoveBtn")
        removeBtn.setFixedSize(18, 18)
        removeBtn.setFlat(True)
        removeBtn.clicked.connect(partial(self.removeSpecies, name))
        chipLayout.addWidget(label)
        chipLayout.addWidget(removeBtn)
        # Hug the species name instead of stretching across the whole column
        chip.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        return chip


class threadGetAudioData(QThread):

    sigThreadFinished = Signal()

    def __init__(self):
        QThread.__init__(self)
        self.parent = ""
        self.workQueue = None
        self.resultQueue = None

    def __del__(self):
        try:
            self.wait()
        except RuntimeError:
            pass

    def run(self):
        while True:
            try:
                item = self.workQueue.get_nowait()
            except queue.Empty:
                break

            row = item["row"]
            file = item["file"]
            mode = item.get("mode", "new")

            # Reuse the on-disk spectrogram cache (the same "spectro_thumb"
            # image the Recordings browser caches); render only on a miss, then
            # store, so re-opening this window is fast.
            img = code_ThumbnailCache.load(file, "spectro_thumb",
                                           code_ThumbnailCache.SPECTRO_THUMB_VARIANT)
            if img is not None and not img.isNull():
                # Cached image already has the axes baked in.
                pixmap = QPixmap.fromImage(img)
                ax_bbox = SPECTRO_AX_BBOX
                _dur, _fs, axesPending = 0, 0, False
            else:
                # Render text-free off-thread (QFont/drawText is not thread-safe
                # on macOS); the GUI thread composites the axes and caches below.
                pixmap, _dur, _fs, ax_bbox = _build_spectrogram_pixmap(
                    file, draw_axis_text=False)
                axesPending = pixmap is not None and not pixmap.isNull()
            recordingData = self.parent.mdiParent.db.getRecordingData(file)

            if mode == "new":
                audioMatchData = self.parent.mdiParent.db.matchRecording(file)
                # Recordings from the same checklist share identical combo
                # data — memoize by (date, location, time), and use the
                # caller-precomputed allDates: these pure-Python database
                # scans are serialized by the GIL regardless of thread count.
                key = (audioMatchData.get("recordingDate", ""),
                       audioMatchData.get("recordingLocation", ""),
                       audioMatchData.get("recordingTime", ""))
                with self.parent._comboCacheLock:
                    comboData = self.parent._comboCache.get(key)
                if comboData is None:
                    comboData = self.parent.mdiParent.db.getComboDataForAudio(
                        audioMatchData, allDates=self.parent._allDates)
                    with self.parent._comboCacheLock:
                        self.parent._comboCache[key] = comboData
                cascadeMode = "date_first"
                allSightings = None
            else:
                s = item["sighting"]
                a = item["recordingData"]
                allSightings = item.get("allSightings", [s])
                recordingData["rating"] = a.get("rating", "0")
                recordingData["notes"] = a.get("notes", "")
                audioMatchData = {
                    "recordingDate": s["date"],
                    "recordingTime": s["time"],
                    "recordingLocation": s["location"],
                    "recordingCommonName": s["commonName"],
                    "dateMatchFound": True,
                    "timeMatchFound": True,
                }
                comboData = self.parent.mdiParent.db.getComboDataForAudioExisting(s)
                cascadeMode = "location_first"

            entry = defaultdict()
            entry["row"] = row
            entry["recordingData"] = recordingData
            entry["audioMatchData"] = audioMatchData
            entry["pixmap"] = pixmap
            entry["ax_bbox"] = ax_bbox
            entry["axesPending"] = axesPending
            entry["duration"] = _dur
            entry["sampleRate"] = _fs
            entry["file"] = file
            entry["comboData"] = comboData
            entry["cascadeMode"] = cascadeMode
            entry["allSightings"] = allSightings

            self.resultQueue.put(entry)
            self.workQueue.task_done()

        self.sigThreadFinished.emit()


class ManageRecordings(QMdiSubWindow, form_ManageRecordings.Ui_frmManageRecordings):

    resized = Signal()
    contentReady = Signal()   # all rows built — a hidden window can be revealed

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.mdiParent = ""
        self.resized.connect(self.resizeMe)
        self.filter = ()
        self.fillingCombos = False
        self.btnSaveAudioSettings.clicked.connect(self.saveAudioSettings)
        self.btnCancel.clicked.connect(self.closeWindow)
        self.metaDataByRow = {}
        # Per-row widget references for the label/Select/Skip panel.
        self._rowLabels = {}
        self.audioAlreadyInDb = True
        self._changesSaved = False
        self._skipCloseGuard = False

        # Card gutters: frame the media-card rows with the window background
        # (the other three media views do the same on their rowsLayout).
        self.gridAudio.setContentsMargins(8, 6, 8, 6)
        self.gridAudio.setVerticalSpacing(6)

        self.threadCount = min(os.cpu_count() or 4, 8)
        self.workQueue = queue.Queue()
        self.resultQueue = queue.Queue()
        self.threadsRemaining = 0
        self.threads = []
        self._loadedCount = 0
        self._totalFiles = 0
        self._threadsToStart = 0
        # Shared combo-data memo for the worker threads (see threadGetAudioData.run)
        self._comboCache = {}
        self._comboCacheLock = threading.Lock()
        self._allDates = None

        for _ in range(self.threadCount):
            t = threadGetAudioData()
            t.parent = self
            t.workQueue = self.workQueue
            t.resultQueue = self.resultQueue
            t.sigThreadFinished.connect(self.threadFinished)
            self.threads.append(t)

        self._drainTimer = QTimer(self)
        self._drainTimer.timeout.connect(self._drainResultQueue)

        # One shared player; switches source when a different row's Play is clicked.
        # QAudioSink-based player: plays pre-decoded PCM so the first audio is
        # immediate (no AVFoundation per-source renderer priming delay).
        self._player = PcmAudioPlayer(self)
        self._player.playbackStateChanged.connect(self._onPlaybackStateChanged)
        self._player.mediaStatusChanged.connect(self._onMediaStatusChanged)
        self._activeRow = None
        self._sliders = {}
        self._playBtns = {}
        self._filePaths = {}
        self._durations_ms = {}
        self._spectroLabels = {}

        self._updateTimer = QTimer(self)
        self._updateTimer.timeout.connect(self._updateScrubber)

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_microphone_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        if (not self._skipCloseGuard and
                not self._changesSaved and
                not self.audioAlreadyInDb and
                self.metaDataByRow):
            reply = code_Stylesheet.question(
                self, "Unsaved Recordings",
                "Your recording information has not been saved to a catalog.\n\n"
                "Close anyway and discard your work?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
                yes_text="Close and discard", no_text="Keep working",
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

        self._drainTimer.stop()
        self._updateTimer.stop()
        self._player.stop()
        while not self.workQueue.empty():
            try:
                self.workQueue.get_nowait()
                self.workQueue.task_done()
            except queue.Empty:
                break
        while not self.resultQueue.empty():
            try:
                self.resultQueue.get_nowait()
            except queue.Empty:
                break
        if self._changesSaved:
            self.mdiParent.refreshOpenStats()
        super(self.__class__, self).closeEvent(event)

    def resizeEvent(self, event):
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)

    def resizeMe(self):
        windowWidth = self.width() - 10
        windowHeight = self.height()
        self.scrollArea.setGeometry(5, 27, windowWidth - 5, windowHeight - 105)
        self.layLists.setGeometry(0, 0, windowWidth - 5, windowHeight - 100)
        self.btnCancel.setGeometry(10, windowHeight - 50, 100, 35)
        self.btnSaveAudioSettings.setGeometry(windowWidth - 160, windowHeight - 50, 150, 35)

    def scaleMe(self):
        fontSize = self.mdiParent.fontSize
        scaleFactor = self.mdiParent.scaleFactor
        for w in self.children():
            try:
                w.setFont(QFont(YBFont, fontSize))
            except Exception:
                pass
        for c in self.layLists.children():
            if "QLabel" in str(c):
                c.setFont(QFont(YBFont, fontSize))
        # Same width as Manage Photos: display thumbnail + text column + fixed
        # controls column, plus a little breathing room.
        windowWidth = int(1045 * scaleFactor)
        windowHeight = int(800 * scaleFactor)
        self.resize(windowWidth, windowHeight)

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    def _btnPlayClicked(self, row):
        filePath = self._filePaths.get(row, "")
        if not filePath:
            return

        if self._activeRow == row:
            state = self._player.playbackState()
            if state == QMediaPlayer.PlaybackState.PlayingState:
                self._player.pause()
            else:
                self._player.play()
            return

        # Switch to a different row — clear previous row's state.
        if self._activeRow is not None:
            self._player.stop()
            prevBtn = self._playBtns.get(self._activeRow)
            if prevBtn:
                prevBtn.setText("Play")
            prevSld = self._sliders.get(self._activeRow)
            if prevSld:
                prevSld.setValue(0)
            prevLbl = self._spectroLabels.get(self._activeRow)
            if prevLbl:
                prevLbl.clearFraction()

        self._activeRow = row
        # PCM is decoded synchronously and playback starts immediately.
        if self._player.setSourceWav(filePath):
            # Honor a scrub position set before this row was first played:
            # the slider may have been dragged while the row was inactive.
            sld = self._sliders.get(row)
            if sld and sld.value() > 0 and self._player.duration() > 0:
                self._player.setPosition(
                    int(sld.value() / 1000.0 * self._player.duration()))
            self._player.play()

    def _onSliderMoved(self, row, value):
        """User dragged the scrubber; show the cursor line, and seek if this
        row is the one loaded in the player.  On a not-yet-played row the
        line still tracks the drag, and the position is honored when Play
        first loads the row (_btnPlayClicked)."""
        lbl = self._spectroLabels.get(row)
        if lbl:
            lbl.setFraction(value / 1000.0)
        if self._activeRow == row and self._player.duration() > 0:
            pos_ms = int(value / 1000.0 * self._player.duration())
            self._player.setPosition(pos_ms)

    def _onPlaybackStateChanged(self, state):
        btn = self._playBtns.get(self._activeRow)
        if state == QMediaPlayer.PlaybackState.PlayingState:
            if btn:
                btn.setText("Pause")
            self._updateTimer.start(100)
        else:
            if btn:
                btn.setText("Play")
            self._updateTimer.stop()

    def _onMediaStatusChanged(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            sld = self._sliders.get(self._activeRow)
            if sld:
                sld.setValue(0)
            btn = self._playBtns.get(self._activeRow)
            if btn:
                btn.setText("Play")
            lbl = self._spectroLabels.get(self._activeRow)
            if lbl:
                lbl.clearFraction()
            self._updateTimer.stop()
            self._activeRow = None

    def _updateScrubber(self):
        """Called by timer every 100 ms during playback; updates slider and cursor line."""
        if self._activeRow is None:
            return
        dur = self._player.duration()
        if dur <= 0:
            return
        pos = self._player.position()
        fraction = pos / dur
        sld = self._sliders.get(self._activeRow)
        if sld and not sld.isSliderDown():
            sld.setValue(int(fraction * 1000))
        lbl = self._spectroLabels.get(self._activeRow)
        if lbl:
            lbl.setFraction(fraction)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def FillRecordingsByFiles(self, files):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.audioAlreadyInDb = False

        allowed = []
        row = 0
        for f in files:
            if os.path.splitext(f)[1].lower() == ".wav":
                allowed.append({"row": row, "file": f, "mode": "new"})
                row += 1

        if not allowed:
            QApplication.restoreOverrideCursor()
            return

        # The full date list is identical for every recording; compute it once
        # here instead of once per file inside getComboDataForAudio (a whole-
        # database scan that the GIL serializes across the worker threads).
        self._allDates = self.mdiParent.db.GetDates(code_Filter.Filter())
        self._comboCache.clear()

        for item in allowed:
            self.workQueue.put(item)

        self._totalFiles = len(allowed)
        self._loadedCount = 0
        self._threadsToStart = min(self.threadCount, len(allowed))
        self.threadsRemaining = self._threadsToStart

        # Gated main-window progress overlay, as in Manage Photos: it only
        # becomes visible if the load runs longer than the gate, so small
        # batches never flash a progress bar.
        overlay = self.mdiParent.progressOverlay
        overlay.armGate(1000)
        overlay.showForRecordings()
        overlay.startLoading(self._totalFiles)

        QTimer.singleShot(0, self._startThreads)

    def FillRecordingsByFilter(self, filter):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.scaleMe()
        self.resizeMe()
        self.fillingCombos = True
        self.filter = filter

        fileToSightings = self.mdiParent.db.GetSightingsByRecordingFile(filter)
        if not fileToSightings:
            QApplication.restoreOverrideCursor()
            return False

        row = 0
        for filename, sightings in fileToSightings.items():
            primary_sighting = sightings[0]
            primary_audio = next(
                (a for a in primary_sighting["audio"] if a["fileName"] == filename),
                primary_sighting["audio"][0],
            )
            self.workQueue.put({
                "row": row,
                "file": filename,
                "mode": "existing",
                "sighting": primary_sighting,
                "recordingData": primary_audio,
                "allSightings": sightings,
            })
            row += 1

        self._totalFiles = row
        self._loadedCount = 0
        self._threadsToStart = min(self.threadCount, row)
        self.threadsRemaining = self._threadsToStart

        # Gated overlay, as in Manage Photos (existing recordings need no
        # combo-data precompute — their assignment is already known).
        overlay = self.mdiParent.progressOverlay
        overlay.armGate(1000)
        overlay.showForRecordings()
        overlay.startLoading(self._totalFiles)

        self.audioAlreadyInDb = True
        self.fillingCombos = False
        self.setWindowTitle("Manage Recordings")

        QTimer.singleShot(0, self._startThreads)
        return True

    def _startThreads(self):
        for i in range(self._threadsToStart):
            self.threads[i].start()
        self._drainTimer.start(50)

    def _drainResultQueue(self):
        prevCount = self._loadedCount
        # Time-budgeted drain (see Manage Photos): workers can outpace the
        # main-thread row building, so an unbounded drain would block the
        # event loop until every row was built — beachball, and the progress
        # bar's first paint would be the finished count.  200ms chunks: long
        # enough that the between-chunk event-loop overhead is negligible,
        # short enough that the overlay stays live (~5 updates/s) and the app
        # never looks hung.
        deadline = time.monotonic() + 0.200
        while time.monotonic() < deadline:
            try:
                entry = self.resultQueue.get_nowait()
            except queue.Empty:
                break
            # Composite the kHz/sec axes on the GUI thread (the worker rendered
            # the spectrogram text-free — QFont/drawText is not thread-safe on
            # macOS), then cache the finished image.
            _pm = entry.get("pixmap")
            if entry.get("axesPending") and _pm and not _pm.isNull():
                _paint_spectro_axes(_pm, entry.get("duration", 0),
                                    entry.get("sampleRate", 0))
                code_ThumbnailCache.store(
                    entry.get("file", ""), _pm.toImage(), "spectro_thumb",
                    code_ThumbnailCache.SPECTRO_THUMB_VARIANT)
            self.insertAudioIntoTable(
                entry["row"],
                entry["recordingData"],
                entry["audioMatchData"],
                entry["pixmap"],
                entry["comboData"],
                entry.get("cascadeMode", "date_first"),
                entry.get("ax_bbox"),
                entry.get("allSightings"),
            )
            self._loadedCount += 1

        if self._loadedCount > prevCount:
            self.mdiParent.progressOverlay.setPhotoValue(self._loadedCount)

        if self.threadsRemaining == 0 and self.resultQueue.empty():
            self._drainTimer.stop()
            self._finishLoading()
        elif not self.resultQueue.empty():
            # Results are already waiting: continue on the next event-loop
            # pass (paints still get through) rather than idling until the
            # next 50ms tick — with quick rows that idle time would dominate
            # the load.  The periodic timer stays as the backstop while the
            # workers are still producing.
            QTimer.singleShot(0, self._drainResultQueue)

    def _finishLoading(self):
        # Run once: the periodic timer and the singleShot continuations can
        # both deliver a final "queue empty" drain pass, and contentReady must
        # not re-fire (it re-shows the window — or worse, fires on a deleted
        # one).
        if getattr(self, "_loadFinished", False):
            return
        self._loadFinished = True
        self.scrollArea.verticalScrollBar().setValue(0)
        self.mdiParent.progressOverlay.hide()
        QApplication.restoreOverrideCursor()
        self.contentReady.emit()

    def threadFinished(self):
        self.threadsRemaining -= 1

    # ------------------------------------------------------------------
    # Row insertion
    # ------------------------------------------------------------------

    def insertAudioIntoTable(self, row, recordingData, audioMatchData, pixmap,
                             comboData, cascadeMode="date_first", ax_bbox=None,
                             allSightings=None):
        # No processEvents here: on a visible window it forced a relayout and
        # repaint of the whole growing grid for every row.  The window stays
        # hidden until contentReady, and the time-budgeted drain keeps the
        # event loop responsive between batches.
        self.fillingCombos = True

        recordingLocation = audioMatchData.get("recordingLocation", "")
        recordingDate = audioMatchData.get("recordingDate", "")
        recordingTime = audioMatchData.get("recordingTime", "")
        recordingCommonName = audioMatchData.get("recordingCommonName", "")

        # ---- Column 0: spectrogram + scrubber ----
        visContainer = QWidget()
        visContainer.setObjectName("cardTransparent")
        visLayout = QVBoxLayout(visContainer)
        visLayout.setContentsMargins(0, 0, 0, 0)
        visLayout.setSpacing(2)

        spectroLabel = SpectrogramLabel()
        if pixmap and not pixmap.isNull():
            spectroLabel.setPixmap(pixmap, ax_bbox)
        self._spectroLabels[row] = spectroLabel
        visLayout.addWidget(spectroLabel)

        scrubRow = QWidget()
        scrubRow.setObjectName("cardTransparent")
        scrubLayout = QHBoxLayout(scrubRow)
        scrubLayout.setContentsMargins(2, 0, 2, 0)
        scrubLayout.setSpacing(4)

        playBtn = QPushButton("Play")
        playBtn.setFixedWidth(60)
        playBtn.setFixedHeight(28)
        playBtn.clicked.connect(partial(self._btnPlayClicked, row))
        self._playBtns[row] = playBtn

        scrubber = QSlider(Qt.Orientation.Horizontal)
        scrubber.setRange(0, 1000)
        scrubber.setValue(0)
        scrubber.setFixedHeight(28)
        scrubber.sliderMoved.connect(partial(self._onSliderMoved, row))
        self._sliders[row] = scrubber

        scrubLayout.addWidget(playBtn)
        scrubLayout.addWidget(scrubber)
        visLayout.addWidget(scrubRow)
        visLayout.addStretch(1)   # keep the strip snug under the spectro

        # Pin the spectro/play column to the shared thumbnail width; the
        # details column absorbs all extra width via the row layout below.
        visContainer.setFixedWidth(code_ThumbnailCache.THUMB_DISPLAY_SIZE.width())

        self._filePaths[row] = recordingData["fileName"]
        dur_str = recordingData.get("duration", "")
        if dur_str:
            try:
                parts = dur_str.split(":")
                mins = int(parts[0]) if len(parts) > 1 else 0
                secs = int(parts[-1])
                self._durations_ms[row] = (mins * 60 + secs) * 1000
            except (ValueError, IndexError):
                self._durations_ms[row] = 0
        else:
            self._durations_ms[row] = 0

        # ---- Column 1: metadata and combos ----
        # Built DETACHED and inserted into the live grid only when complete
        # (below): adding the empty container first made every subsequent
        # widget insertion propagate styles/fonts through the live hierarchy,
        # one widget at a time (~7ms per row).
        container = QWidget()
        container.setObjectName("cardTransparent")
        detailsLayout = QVBoxLayout(container)
        detailsLayout.setObjectName("layout" + str(row))
        detailsLayout.setAlignment(Qt.AlignTop)

        # Seed this row's working metadata, then build the colour-coded label /
        # Select / Skip panel.  Date, location and time are shown as labels; the
        # species tag strip (multiple chips) is fed by the checklist tree picker.
        isExisting = self.audioAlreadyInDb
        if allSightings:
            initialSpecies = [s["commonName"] for s in allSightings]
        elif recordingCommonName:
            initialSpecies = [recordingCommonName]
        else:
            initialSpecies = []

        thisAudioMetaData = {}
        thisAudioMetaData["location"] = recordingLocation
        thisAudioMetaData["date"] = recordingDate
        thisAudioMetaData["time"] = recordingTime
        thisAudioMetaData["commonNames"] = list(initialSpecies)
        thisAudioMetaData["origCommonNames"] = list(initialSpecies)
        thisAudioMetaData["allSightings"] = allSightings or []
        thisAudioMetaData["recordingData"] = recordingData
        thisAudioMetaData["rating"] = recordingData.get("rating", "0")
        thisAudioMetaData["notes"] = recordingData.get("notes", "")
        thisAudioMetaData["cascadeMode"] = cascadeMode
        thisAudioMetaData["skip"] = False
        thisAudioMetaData["newLocation"] = recordingLocation
        thisAudioMetaData["newDate"] = recordingDate
        thisAudioMetaData["newTime"] = recordingTime
        thisAudioMetaData["newCommonNames"] = list(initialSpecies)
        thisAudioMetaData["autoDate"] = recordingDate
        thisAudioMetaData["autoLocation"] = recordingLocation
        thisAudioMetaData["autoTime"] = recordingTime
        if isExisting:
            thisAudioMetaData["autoGreen"] = {"date": True, "location": True, "time": True}
        else:
            thisAudioMetaData["autoGreen"] = self._computeAutoGreen(audioMatchData)

        self.metaDataByRow[row] = thisAudioMetaData
        self._buildDetailsPanel(row, detailsLayout, recordingData, isExisting)

        # Panel complete — assemble spectro + details as ONE card row spanning
        # both grid columns (shared media-card background, matching the other
        # media views), inserted in a single style/font propagation pass.
        rowWidget = QWidget()
        rowWidget.setObjectName("mediaCard")
        rowWidget.setAttribute(Qt.WA_StyledBackground, True)
        rowLayout = QHBoxLayout(rowWidget)
        rowLayout.setContentsMargins(6, 6, 6, 6)   # inset content off the rounded corners
        rowLayout.setSpacing(2)
        rowLayout.addWidget(visContainer)
        rowLayout.addWidget(container, 1)   # details absorb the extra width
        self.gridAudio.addWidget(rowWidget, row, 0, 1, 2)

        self.saveNewMetaData(row)
        self.fillingCombos = False

    # ------------------------------------------------------------------
    # Assignment panel + checklist tree
    # ------------------------------------------------------------------

    def _computeAutoGreen(self, md):
        """Which fields were confirmed from the recording's metadata/filename
        (only these may show green): date matched a checklist date, time matched
        exactly, location confirmed only when the exact checklist matched."""
        dmf = md.get("dateMatchFound", False)
        tmf = md.get("timeMatchFound", False)
        return {"date": dmf, "time": tmf, "location": tmf}

    def _fieldGreen(self, md, field):
        """Green only if the field was auto-derived AND still equals that value."""
        if field not in ("date", "location", "time"):
            return False
        if not md.get("autoGreen", {}).get(field, False):
            return False
        current = {"date": md.get("newDate", ""),
                   "location": md.get("newLocation", ""),
                   "time": md.get("newTime", "")}[field]
        auto = {"date": md.get("autoDate", ""),
                "location": md.get("autoLocation", ""),
                "time": md.get("autoTime", "")}[field]
        return current == auto

    def _fieldHtml(self, name, value, green, skipped):
        if skipped:
            valColor = _SKIPPED_COLOR
        elif green:
            valColor = _MATCH_COLOR
        else:
            valColor = _VALUE_COLOR
        return ('<span style="color:%s">%s</span>&nbsp;&nbsp;'
                '<span style="color:%s; font-weight:600">%s</span>'
                % (_FIELD_NAME_COLOR, name, valColor, value))

    def _buildDetailsPanel(self, row, detailsLayout, recordingData, isExisting):
        """Minimalist row panel: filename, colour-coded Date/Location/Time
        labels, the species tag strip, and a right-hand Select / Reset / Rating /
        Skip column.  The checklist tree sets date/location/time and adds chips."""
        lbls = {}
        self._rowLabels[row] = lbls

        bodyRow = QHBoxLayout()
        bodyRow.setSpacing(14)
        # Right inset so the control column clears the vertical scrollbar.
        bodyRow.setContentsMargins(0, 0, 16, 0)

        # Left column: filename + duration above the assignment labels and the
        # species tag strip.
        leftCol = QVBoxLayout()
        leftCol.setSpacing(4)

        lblFileName = QLabel(_wrappable(os.path.basename(recordingData["fileName"])))
        lblFileName.setStyleSheet("color: %s;" % _FIELD_NAME_COLOR)
        # Wrap the (often long) filename so it can't force the whole right-hand
        # section wider than the window and truncate the buttons.
        lblFileName.setWordWrap(True)
        leftCol.addWidget(lblFileName)

        # The recording's own embedded date/time (EXIF / WAV-metadata
        # equivalent), shown so the user can judge how to assign it.
        metaDate = recordingData.get("metaDate", "")
        metaTime = recordingData.get("metaTime", "")
        if metaDate:
            metaStr = "Recorded %s" % metaDate
            if metaTime:
                metaStr += " %s" % metaTime
        else:
            metaStr = "Recording date unknown"
        lblMeta = QLabel(metaStr)
        lblMeta.setStyleSheet("color: %s;" % _FIELD_NAME_COLOR)
        lblMeta.setWordWrap(True)
        leftCol.addWidget(lblMeta)
        leftCol.addSpacing(10)   # line feed after the metadata line

        for key in ("date", "location", "time"):
            lbl = QLabel()
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setWordWrap(True)
            lbls[key] = lbl
            leftCol.addWidget(lbl)

        speciesHeader = QLabel()
        speciesHeader.setTextFormat(Qt.TextFormat.RichText)
        speciesHeader.setWordWrap(True)
        lbls["speciesHeader"] = speciesHeader
        leftCol.addWidget(speciesHeader)


        # Parent the strip at construction: _rebuild() calls setVisible(True),
        # and showing a PARENTLESS widget creates a native top-level window
        # (~8ms) that must then be torn down when the row assembly reparents
        # it (~5ms more) — measured as the bulk of the per-row build cost.
        tagStrip = SpeciesTagStrip(detailsLayout.parentWidget())
        tagStrip.setObjectName("tagStrip" + str(row))
        tagStrip.setSpeciesList(list(self.metaDataByRow[row]["commonNames"]))
        tagStrip.speciesChanged.connect(partial(self._onSpeciesChanged, row))
        lbls["tagStrip"] = tagStrip
        leftCol.addWidget(tagStrip)

        leftCol.addStretch()
        bodyRow.addLayout(leftCol, 1)


        # Right column, top-to-bottom: Select, Reset, Rating combo, Skip/Remove.
        # Held to a fixed, narrow width so the buttons always render in full.
        # Pin every control to one explicit font so the combo text can't end up
        # a different size from the buttons (they otherwise resolve fonts via
        # different inheritance paths).
        _panelFont = QFont(YBFont, getattr(self.mdiParent, "fontSize", 11))
        controlsCol = QVBoxLayout()
        controlsCol.setContentsMargins(0, 0, 0, 0)
        controlsCol.setSpacing(8)

        btnSelect = QPushButton("Select")
        btnSelect.setFont(_panelFont)
        btnSelect.clicked.connect(partial(self._openSelectTree, row))
        controlsCol.addWidget(btnSelect)

        btnReset = QPushButton("Reset")
        btnReset.setFont(_panelFont)
        btnReset.clicked.connect(partial(self.btnResetClicked, row))
        controlsCol.addWidget(btnReset)

        btnNotes = QPushButton("Notes")
        btnNotes.setFont(_panelFont)
        btnNotes.clicked.connect(partial(self._openNotesDialog, row))
        controlsCol.addWidget(btnNotes)

        cboRating = QComboBox()
        cboRating.addItems(["Not Rated", "1", "2", "3", "4", "5"])
        cboRating.setObjectName("cboRating" + str(row))
        cboRating.setFont(_panelFont)
        cboRating.setEditable(True)
        cboRating.lineEdit().setReadOnly(True)
        cboRating.lineEdit().setAlignment(Qt.AlignCenter)
        cboRating.lineEdit().setFocusPolicy(Qt.NoFocus)
        cboRating.lineEdit().setFont(_panelFont)
        # Transparent line edit; the left padding offsets the drop-down arrow on
        # the right so the text sits centred under the full control, not just the
        # area left of the arrow.
        cboRating.lineEdit().setStyleSheet(
            "QLineEdit { background: transparent; border: none; padding-left: 30px; }")
        for _i in range(cboRating.count()):
            cboRating.setItemData(_i, Qt.AlignCenter, Qt.TextAlignmentRole)
        try:
            cboRating.setCurrentIndex(max(0, min(5, int(self.metaDataByRow[row]["rating"]))))
        except (TypeError, ValueError):
            cboRating.setCurrentIndex(0)
        cboRating.currentIndexChanged.connect(partial(self.cboRatingChanged, row))
        lbls["rating"] = cboRating
        controlsCol.addWidget(cboRating)


        chkSkip = QCheckBox("Remove" if isExisting else "Skip")
        chkSkip.setFont(_panelFont)
        chkSkip.toggled.connect(partial(self._toggleSkip, row))
        lbls["skip"] = chkSkip
        controlsCol.addWidget(chkSkip)

        controlsCol.addStretch()
        controlsWidget = QWidget()
        controlsWidget.setObjectName("cardTransparent")
        controlsWidget.setLayout(controlsCol)
        # Wide enough that "Not Rated" plus the dropdown arrow plus the centring
        # padding all fit without clipping the leading letter.
        controlsWidget.setFixedWidth(160)
        bodyRow.addWidget(controlsWidget)

        detailsLayout.addLayout(bodyRow)
        self._refreshRowLabels(row)

    def _refreshRowLabels(self, row):
        md = self.metaDataByRow[row]
        lbls = self._rowLabels.get(row)
        if not lbls:
            return
        skipped = md.get("skip", False)
        date = md.get("newDate") or "\u2014"
        loc  = md.get("newLocation") or "\u2014"
        tm   = md.get("newTime") or "\u2014"
        lbls["date"].setText(self._fieldHtml("Date", date, self._fieldGreen(md, "date"), skipped))
        lbls["location"].setText(self._fieldHtml("Location", loc, self._fieldGreen(md, "location"), skipped))
        lbls["time"].setText(self._fieldHtml("Time", tm, self._fieldGreen(md, "time"), skipped))
        ts = lbls.get("tagStrip")
        if ts is not None:
            ts.setEnabled(not skipped)
            ts.setSkipped(skipped)
        # No standing "Species" header: show the skip note when skipped, a prompt
        # when nothing is selected, and nothing at all once species are chosen.
        hdr = lbls.get("speciesHeader")
        if hdr is not None:
            if skipped:
                note = "Will be removed" if self.audioAlreadyInDb else "Will be skipped"
                hdr.setText('<span style="color:%s">%s</span>' % (_SKIPPED_COLOR, note))
                hdr.setVisible(True)
            elif ts is not None and ts.getSpecies():
                hdr.setText("")
                hdr.setVisible(False)
            else:
                hdr.setText('<span style="color:%s">Click Select to choose a species</span>'
                            % _NO_SPECIES_COLOR)
                hdr.setVisible(True)

    def _openSelectTree(self, row):
        md = self.metaDataByRow[row]
        dlg = code_ChecklistTree.ChecklistTreeDialog(self.mdiParent.db, self)
        dlg.expand_to(md.get("newDate", ""), md.get("newLocation", ""),
                      md.get("newTime", ""), "")
        if dlg.exec() and dlg.result:
            self._applyTreeResult(row, dlg.result)

    def _openNotesDialog(self, row):
        md = self.metaDataByRow[row]
        dlg = code_NotesDialog.NotesDialog(md.get("newNotes", md.get("notes", "")), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            md["newNotes"] = dlg.result
            self.saveNewMetaData(row)

    def _applyTreeResult(self, row, result):
        md = self.metaDataByRow[row]
        ts = self._rowLabels.get(row, {}).get("tagStrip")
        # A recording belongs to one checklist; keep species consistent with it.
        sameChecklist = (result["date"] == md.get("newDate") and
                         result["location"] == md.get("newLocation") and
                         result["time"] == md.get("newTime"))
        md["newDate"] = result["date"]
        md["newLocation"] = result["location"]
        md["newTime"] = result["time"]
        md["skip"] = False
        chk = self._rowLabels.get(row, {}).get("skip")
        if chk is not None:
            chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(False)
        if ts is not None:
            if sameChecklist:
                ts.addSpecies(result["species"])        # same checklist: add a species
            else:
                ts.setSpeciesList([result["species"]])  # new checklist: reset species
        self._refreshRowLabels(row)
        self.saveNewMetaData(row)

    def _onSpeciesChanged(self, row):
        # Covers removing the last species via a pill's "x", which leaves the
        # tag strip empty without going through _applyTreeResult/btnResetClicked
        # (the only other callers that already refresh the "no species" note).
        self._refreshRowLabels(row)
        self.saveNewMetaData(row)

    def _toggleSkip(self, row, checked):
        self.metaDataByRow[row]["skip"] = checked
        self._refreshRowLabels(row)
        self.saveNewMetaData(row)

    def cboRatingChanged(self, row, _index=None):
        if self.fillingCombos:
            return
        self.saveNewMetaData(row)

    def saveNewMetaData(self, row):
        md = self.metaDataByRow.get(row)
        if md is None:
            return
        lbls = self._rowLabels.get(row, {})
        md.setdefault("newLocation", md["location"])
        md.setdefault("newDate", md["date"])
        md.setdefault("newTime", md["time"])
        md.setdefault("newNotes", md.get("notes", ""))
        if md.get("skip"):
            md["newCommonNames"] = []
        else:
            ts = lbls.get("tagStrip")
            if ts is not None:
                md["newCommonNames"] = ts.getSpecies()
            else:
                md.setdefault("newCommonNames", list(md.get("commonNames", [])))
        cbo = lbls.get("rating")
        if cbo is not None:
            md["newRating"] = str(cbo.currentIndex())
        else:
            md.setdefault("newRating", str(md.get("rating", "0")))

    def btnResetClicked(self, row):
        md = self.metaDataByRow[row]
        md["newLocation"] = md["location"]
        md["newDate"] = md["date"]
        md["newTime"] = md["time"]
        md["newNotes"] = md.get("notes", "")
        md["skip"] = False
        lbls = self._rowLabels.get(row, {})
        chk = lbls.get("skip")
        if chk is not None:
            chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(False)
        ts = lbls.get("tagStrip")
        if ts is not None:
            ts.setSpeciesList(list(md.get("origCommonNames", [])))
        cbo = lbls.get("rating")
        if cbo is not None:
            try:
                cbo.setCurrentIndex(max(0, min(5, int(md["rating"]))))
            except (TypeError, ValueError):
                cbo.setCurrentIndex(0)
        self._refreshRowLabels(row)
        self.saveNewMetaData(row)

    def saveAudioSettings(self):
        if not self.audioAlreadyInDb and not self.mdiParent.db.photoDataFileOpenFlag:
            msg = QMessageBox(self)
            msg.setWindowTitle("No Catalog Open")
            msg.setText(
                "You need a photo/recording catalog file for Yearbirder to save "
                "your recording information.\n\n"
                "A catalog is a file that stores the species, checklist, and "
                "rating data for each of your media files. Without one, your "
                "work here cannot be saved to disk.\n\n"
                "Would you like to create a new catalog file now, or go back?"
            )
            create_btn = msg.addButton("Create Catalog…", QMessageBox.ButtonRole.AcceptRole)
            go_back_btn = msg.addButton("Go Back", QMessageBox.ButtonRole.RejectRole)
            discard_btn = msg.addButton("Discard Work", QMessageBox.ButtonRole.DestructiveRole)
            msg.setDefaultButton(create_btn)
            msg.exec()

            clicked = msg.clickedButton()
            if clicked is discard_btn:
                self._skipCloseGuard = True
                self.close()
                return
            elif clicked is not create_btn:
                return

            initial_dir = self.mdiParent.db.startupFolder or os.path.expanduser("~")
            fname, _ = QFileDialog.getSaveFileName(
                self,
                "Create Catalog File",
                os.path.join(initial_dir, "Yearbirder_MediaCatalog.jsonl"),
                "Yearbirder Catalog (*.jsonl)",
            )
            if not fname:
                return
            if not fname.lower().endswith(".jsonl"):
                fname += ".jsonl"
            self.mdiParent.db.photoDataFile = fname
            self.mdiParent.db.photoDataFileOpenFlag = True
            reply = QMessageBox.question(
                self,
                "Set as Default Catalog?",
                f"Would you like Yearbirder to open\n\"{os.path.basename(fname)}\"\n"
                "automatically each time it starts?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.mdiParent.db.photoDataFileDefault = fname
                self.mdiParent.db.writePreferences()
            self.mdiParent._updateMediaMenuVisibility()
            self.mdiParent._showPhotoCatalogMenuItems()
            self.mdiParent.actionGeolocatedPhotos.setVisible(True)
            self.mdiParent.actionGeolocatedPhotosSeparator.setVisible(True)
            self.mdiParent.actionAnimatedPhotoSequence.setVisible(True)
            self.mdiParent.actionSlideshow.setVisible(True)

        # Collect files successfully added so their spectrograms can be cached.
        added_recording_files = set()

        # Iterate the metadata dict directly (not layout row counts)
        for r in sorted(self.metaDataByRow):
            meta = self.metaDataByRow[r]

            if self.audioAlreadyInDb:
                old_species = [s["commonName"] for s in meta.get("allSightings", [])]
                new_species = meta.get("newCommonNames", [])
                changed = (
                    meta["location"] != meta["newLocation"] or
                    meta["date"] != meta["newDate"] or
                    meta["time"] != meta["newTime"] or
                    set(old_species) != set(new_species) or
                    meta["rating"] != meta["newRating"] or
                    meta["notes"] != meta["newNotes"]
                )
                if changed:
                    audio_filename = meta["recordingData"]["fileName"]
                    self.mdiParent.db.removeRecordingFileFromDatabase(audio_filename)
                    try:
                        self.mdiParent.db.appendRecordingDeletionToJsonl(audio_filename)
                    except IOError:
                        pass
                    meta["recordingData"]["rating"] = meta["newRating"]
                    meta["recordingData"]["notes"] = meta["newNotes"]
                    for species_name in new_species:
                        f = code_Filter.Filter()
                        f.setLocationName(meta["newLocation"])
                        f.setLocationType("Location")
                        f.setStartDate(meta["newDate"])
                        f.setEndDate(meta["newDate"])
                        f.setTime(meta["newTime"])
                        f.setSpeciesName(species_name)
                        s = self.mdiParent.db.addRecordingToDatabase(f, meta["recordingData"])
                        if s:
                            added_recording_files.add(meta["recordingData"]["fileName"])
                            try:
                                self.mdiParent.db.appendRecordingToJsonl(s, meta["recordingData"])
                            except IOError as exc:
                                QMessageBox.warning(self, "Catalog File Error",
                                    f"Recording saved in memory but could not be written to catalog:\n{exc}")
            else:
                new_species = meta.get("newCommonNames", [])
                if new_species:
                    meta["recordingData"]["rating"] = meta["newRating"]
                    meta["recordingData"]["notes"] = meta["newNotes"]
                    for species_name in new_species:
                        f = code_Filter.Filter()
                        f.setLocationName(meta["newLocation"])
                        f.setLocationType("Location")
                        f.setStartDate(meta["newDate"])
                        f.setEndDate(meta["newDate"])
                        f.setTime(meta["newTime"])
                        f.setSpeciesName(species_name)
                        s = self.mdiParent.db.addRecordingToDatabase(f, meta["recordingData"])
                        if s:
                            added_recording_files.add(meta["recordingData"]["fileName"])
                            try:
                                self.mdiParent.db.appendRecordingToJsonl(s, meta["recordingData"])
                            except IOError as exc:
                                QMessageBox.warning(self, "Catalog File Error",
                                    f"Recording saved in memory but could not be written to catalog:\n{exc}")

        # Cache the spectrogram thumbnail + enlargement ribbon for the added
        # recordings in the background (skips ones already cached) so every
        # catalogued recording exists in the cache.
        if added_recording_files:
            code_ThumbnailCache.prebuild_async(recording_paths=added_recording_files)

        # Rebuild the Media Filter's recording options so any new sample rate or
        # bit depth introduced by the saved recordings appears immediately (this
        # mirrors what Manage Photos does for the photo filters on save).
        self.mdiParent.db.refreshRecordingsLists()
        self.mdiParent.fillRecordingsComboBoxes()
        # Reveal the Recordings menu if this added the first recording to the catalog.
        self.mdiParent._updateMediaMenuVisibility()
        self.mdiParent.db.photosNeedSaving = True
        self._changesSaved = True
        self.close()

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def closeWindow(self):
        self.close()

    def highlightWidget(self, w):
        red = str(code_Stylesheet.mdiAreaColor.red())
        blue = str(code_Stylesheet.mdiAreaColor.blue())
        green = str(code_Stylesheet.mdiAreaColor.green())
        w.setStyleSheet("QComboBox { background-color: rgb(" + red + "," + green + "," + blue + ")}")

    def removeHighlight(self, w):
        w.setStyleSheet("")
