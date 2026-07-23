import form_Recordings
from code_Stylesheet import YBFont
from code_ManageRecordings import SpectrogramLabel   # UI widget stays in its module
import code_Filter
from code_Audio import (
    render_spectrogram_qimage as _render_spectrogram_qimage,
    paint_spectro_axes as _paint_spectro_axes,
    PcmAudioPlayer,
    SPECTRO_AX_BBOX,
)
import code_ThumbnailCache

import datetime
import os
import queue
import time
from math import floor
from functools import partial

from PySide6.QtGui import QPixmap, QFont, QIcon
from PySide6.QtCore import Signal, Qt, QThread, QTimer, QUrl
from PySide6.QtWidgets import (
    QMdiSubWindow, QLabel, QApplication,
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider,
)
from PySide6.QtMultimedia import QMediaPlayer  # enum constants reused by PcmAudioPlayer


class threadLoadSpectrogram(QThread):
    """Worker thread that builds a spectrogram pixmap for a single WAV file.

    Results are placed into a shared Python queue to avoid flooding the Qt
    event queue (same pattern as threadLoadThumbnail in code_Photos.py).
    """

    sigThreadFinished = Signal()

    def __init__(self):
        QThread.__init__(self)
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
                row, audioFile = self.workQueue.get_nowait()
            except queue.Empty:
                break

            # Tier 2: on-disk spectrogram cache (tier 1 is the in-memory
            # spectroCache, checked before a file is queued here).
            # QImage ONLY in this thread — QPixmap creation (and destruction)
            # is a GUI-thread-only operation, even for a cached image; the
            # GUI thread converts in _drainResultQueue.
            img = code_ThumbnailCache.load(audioFile, "spectro_thumb",
                                           code_ThumbnailCache.SPECTRO_THUMB_VARIANT)
            if img is not None and not img.isNull():
                # Cached image already has the axes baked in.
                ax_bbox = SPECTRO_AX_BBOX
                duration, sr, axesPending = 0, 0, False
            else:
                # Tier 3: render the spectrogram WITHOUT axis text off-thread —
                # QFont/drawText is not thread-safe on macOS (it corrupts glyph
                # metrics app-wide). The GUI thread composites the kHz/sec axes
                # and caches the result in _drainResultQueue.
                img, duration, sr, ax_bbox = _render_spectrogram_qimage(
                    audioFile, draw_axis_text=False)
                axesPending = img is not None and not img.isNull()

            self.resultQueue.put(
                (row, audioFile, img, ax_bbox, duration, sr, axesPending))
            self.workQueue.task_done()

        self.sigThreadFinished.emit()


class Recordings(QMdiSubWindow, form_Recordings.Ui_frmRecordings):

    resized = Signal()

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.mdiParent = ""
        self.resized.connect(self.resizeMe)
        self.lblDetails.setVisible(False)
        self.filter = ()
        self.audioList = []
        self._singleMode = False   # True only for FillSingleRecording windows
        self.spectroCache = {}   # filename -> (QPixmap, ax_bbox)
        # Qt caps a QGridLayout's total height at ~524k px, which squashes the
        # rows once there are more than ~1,600 recordings.  Use a QVBoxLayout of
        # per-row widgets instead (no such cap until ~50k); the form's gridAudio
        # is left unused.
        self.gridAudio.setContentsMargins(0, 0, 0, 0)
        self.rowsLayout = QVBoxLayout()
        self.rowsLayout.setContentsMargins(8, 6, 8, 6)   # gutters frame the cards
        self.rowsLayout.setSpacing(6)
        self.verticalLayout_3.addLayout(self.rowsLayout)
        self.verticalLayout_3.addStretch(1)
        self._abort = False
        self._sorting = False
        self._spectroLabels = {}
        self._rowWidgets = {}

        self.rdoSortSpecies.toggled.connect(lambda checked: self.SortAndDisplayRecordings() if checked else None)
        self.rdoSortDate.toggled.connect(lambda checked: self.SortAndDisplayRecordings() if checked else None)
        self.rdoSortRating.toggled.connect(lambda checked: self.SortAndDisplayRecordings() if checked else None)
        self.rdoSortTaxonomy.toggled.connect(lambda checked: self.SortAndDisplayRecordings() if checked else None)

        self.threadCount = min(os.cpu_count() or 4, 8)
        self.workQueue = queue.Queue()
        self.resultQueue = queue.Queue()
        self.threadsRemaining = 0
        self.threads = []
        self._loadedCount = 0
        self._totalUncached = 0
        self._threadsToStart = 0

        for _ in range(self.threadCount):
            t = threadLoadSpectrogram()
            t.workQueue = self.workQueue
            t.resultQueue = self.resultQueue
            t.sigThreadFinished.connect(self.spectroThreadFinished)
            self.threads.append(t)

        self._drainTimer = QTimer(self)
        self._drainTimer.timeout.connect(self._drainResultQueue)

        # One shared player; switches source when a different row's Play is clicked.
        # QAudioSink-based player: plays pre-decoded PCM from memory so the first
        # audio is immediate (no AVFoundation per-source renderer priming delay).
        self._player = PcmAudioPlayer(self)
        self._player.playbackStateChanged.connect(self._onPlaybackStateChanged)
        self._player.mediaStatusChanged.connect(self._onMediaStatusChanged)
        self._activeRow = None
        self._sliders = {}
        self._playBtns = {}
        self._filePaths = {}
        self._pendingPlay = False

        self._updateTimer = QTimer(self)
        self._updateTimer.timeout.connect(self._updateScrubber)

        # 16 ms (~60 fps) timer interpolates cursor between 100 ms polls so
        # the red line moves smoothly instead of jumping every 100 ms.
        self._cursorTimer = QTimer(self)
        self._cursorTimer.setInterval(16)
        self._cursorTimer.timeout.connect(self._updateCursor)
        self._lastRealPosSec = 0.0
        self._lastPollTime   = None
        self._activeDuration = 0.0

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._abort = True
        self._drainTimer.stop()
        self._updateTimer.stop()
        self._cursorTimer.stop()
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
        self.mdiParent.progressOverlay.hide()
        self.mdiParent.db.compactJsonlFile()
        code_ThumbnailCache.enforce_cap()   # keep the on-disk cache bounded
        super(self.__class__, self).closeEvent(event)

    def resizeEvent(self, event):
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)

    def handleAudioDeletion(self, filename, species=None):
        orig_len = len(self.audioList)
        self.audioList = [(a, s) for (a, s) in self.audioList
                          if not (a.get("fileName") == filename
                                  and (species is None
                                       or s.get("commonName") == species))]
        if len(self.audioList) == orig_len:
            return
        # A species-scoped removal can leave the file on other species' cards;
        # only evict the cached spectrogram when no card still shows it.
        if not any(a.get("fileName") == filename for (a, s) in self.audioList):
            self.spectroCache.pop(filename, None)
        if not self.audioList:
            self.close()
            return
        self._buildRows()

    def handleRecordingRename(self, old_path, new_path):
        """A Rename Media operation moved a recording on disk.  The audio dicts
        in audioList are the live db objects, so their fileName self-heals, but
        the per-row playback map (_filePaths) holds captured path strings and
        the spectrogram cache is keyed by path — both would keep pointing at the
        vanished file, so Play would silently decode nothing.  Re-point them."""
        touched = False
        for row, path in list(self._filePaths.items()):
            if path == old_path:
                self._filePaths[row] = new_path
                touched = True
        if old_path in self.spectroCache:
            self.spectroCache[new_path] = self.spectroCache.pop(old_path)
            touched = True
        # If the renamed file is the one currently loaded in the player, keep the
        # already-decoded buffer (it plays fine) but track the new path so a
        # later re-select re-decodes from the right place.
        if touched and getattr(self._player, "_currentPath", None) == old_path:
            self._player._currentPath = new_path

    def resizeMe(self):
        windowWidth = self.width() - 10
        windowHeight = self.height()
        headerHeight = max(self.headerFrame.sizeHint().height(), 60) + 16
        self.headerFrame.setGeometry(5, 27, windowWidth - 5, headerHeight)
        self.scrollArea.setGeometry(5, 27 + headerHeight, windowWidth - 5,
                                    windowHeight - 35 - headerHeight)

    def scaleMe(self):
        fontSize = self.mdiParent.fontSize
        scaleFactor = self.mdiParent.scaleFactor
        for w in self.children():
            try:
                w.setFont(QFont(YBFont, fontSize))
            except Exception:
                pass
        self.lblLocation.setFont(QFont(YBFont, floor(fontSize * 1.4)))
        self.lblLocation.setStyleSheet("QLabel { font: bold }")
        self.lblDateRange.setFont(QFont(YBFont, floor(fontSize * 1.2)))
        self.lblDateRange.setStyleSheet("QLabel { font: bold }")
        self.lblDetails.setFont(QFont(YBFont, floor(fontSize * 1.2)))
        self.lblDetails.setStyleSheet("QLabel { font: bold }")
        self.lblSpecies.setFont(QFont(YBFont, fontSize))
        self.lblSortBy.setFont(QFont(YBFont, fontSize))
        self.rdoSortSpecies.setFont(QFont(YBFont, fontSize))
        self.rdoSortDate.setFont(QFont(YBFont, fontSize))
        self.rdoSortRating.setFont(QFont(YBFont, fontSize))
        self.rdoSortTaxonomy.setFont(QFont(YBFont, fontSize))
        for c in self.layLists.findChildren(QLabel):
            c.setFont(QFont(YBFont, fontSize))
        windowWidth = int(800 * scaleFactor)
        if len(self.audioList) == 1:
            windowHeight = int(400 * scaleFactor)
        else:
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
        self._pendingPlay = False
        # PCM is decoded synchronously and playback starts immediately.
        if self._player.setSourceWav(filePath):
            # Honor a scrubber the user pre-positioned before pressing Play, so
            # playback starts at the red cursor rather than from the beginning.
            sld = self._sliders.get(row)
            if sld and sld.value() > 0 and self._player.duration() > 0:
                pos_ms = int(sld.value() / 1000.0 * self._player.duration())
                self._player.setPosition(pos_ms)
                self._anchorPlayback(pos_ms / 1000.0)
            self._player.play()

    def _onSliderMoved(self, row, value):
        """User dragged the scrubber; move this row's cursor line — whether or not
        the row is playing — and seek the player when this row is the loaded one."""
        lbl = self._spectroLabels.get(row)
        if lbl:
            lbl.setFraction(value / 1000.0)
        if self._activeRow == row and self._player.duration() > 0:
            pos_ms = int(value / 1000.0 * self._player.duration())
            self._player.setPosition(pos_ms)
            self._anchorPlayback(pos_ms / 1000.0)

    def _anchorPlayback(self, pos_sec, resetGate=True):
        """Reset the wall-clock interpolation anchor (seconds).

        The backend position() advances in coarse ~90 ms buffer steps; anchoring
        only at play and on seeks — rather than re-snapping to that staircase
        every 100 ms poll — keeps the red cursor line sliding smoothly.

        resetGate=True (play/seek callers) schedules a HOLD: the player floors
        position at the seek point until the sound actually reaches the ears
        (the calibrated output latency), so the interpolated cursor must wait
        exactly that long before gliding — no drift-and-snap-back, and zero
        wait on a zero-latency device."""
        self._lastRealPosSec = pos_sec
        self._lastPollTime   = time.perf_counter()
        if resetGate:
            self._holdUntilTime = (time.perf_counter()
                                   + self._player.outputLatencyMs() / 1000.0)

    def _interpPosSec(self):
        """Wall-clock interpolated position, honoring the post-play/seek hold."""
        base = max(self._lastPollTime, getattr(self, "_holdUntilTime", 0.0))
        return self._lastRealPosSec + max(0.0, time.perf_counter() - base)

    def _onPlaybackStateChanged(self, state):
        btn = self._playBtns.get(self._activeRow)
        if state == QMediaPlayer.PlaybackState.PlayingState:
            if btn:
                btn.setText("Pause")
            self._activeDuration = self._player.duration() / 1000.0
            self._anchorPlayback(self._player.position() / 1000.0)
            self._updateTimer.start(100)
            self._cursorTimer.start()
        else:
            if btn:
                btn.setText("Play")
            self._updateTimer.stop()
            self._cursorTimer.stop()

    def _onMediaStatusChanged(self, status):
        _ready = (QMediaPlayer.MediaStatus.LoadedMedia,
                  QMediaPlayer.MediaStatus.BufferedMedia)
        if status in _ready:
            if self._pendingPlay:
                self._pendingPlay = False
                self._player.play()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._pendingPlay = False
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
            self._cursorTimer.stop()
            self._activeRow = None

    def _updateScrubber(self):
        """Called every 100 ms: updates the slider and, only on a gross
        divergence, re-anchors the interpolation.  The backend position()
        advances in coarse ~90 ms buffer steps, so re-snapping to it every poll
        would stutter the cursor; normal anchoring happens at play and on seeks.
        Smooth cursor painting is handled by _updateCursor."""
        if self._activeRow is None:
            return
        dur = self._player.duration()
        if dur <= 0:
            return
        pos_ms  = self._player.position()
        pos_sec = pos_ms / 1000.0

        if self._lastPollTime is None:
            self._anchorPlayback(pos_sec, resetGate=False)
        elif abs(pos_sec - self._interpPosSec()) > 0.25:
            self._anchorPlayback(pos_sec, resetGate=False)

        sld = self._sliders.get(self._activeRow)
        if sld and not sld.isSliderDown():
            sld.setValue(int((pos_ms / dur) * 1000))

    def _updateCursor(self):
        """Called every ~16 ms: interpolates playback position between 100 ms
        polls so the red cursor line moves smoothly at ~60 fps."""
        if self._activeRow is None or self._lastPollTime is None:
            return
        dur = self._activeDuration
        if dur <= 0:
            return
        pos_sec = min(self._interpPosSec(), dur)
        lbl = self._spectroLabels.get(self._activeRow)
        if lbl:
            lbl.setFraction(pos_sec / dur)

    # ------------------------------------------------------------------
    # Fill
    # ------------------------------------------------------------------

    def FillRecordings(self, filter):
        self.scaleMe()
        self.resizeMe()

        self.filter = filter
        self._singleMode = False

        # Arm the time-based reveal gate, then prime the overlay.  It only becomes
        # visible if loading runs longer than the threshold, so small recording
        # sets (fast on any machine) never flash a progress bar — same as Photos.
        overlay = self.mdiParent.progressOverlay
        overlay.armGate(1000)
        overlay.showForRecordings()
        QApplication.processEvents()

        recordingSightings = self.mdiParent.db.GetSightingsWithRecordings(filter)

        if not recordingSightings:
            self.mdiParent.progressOverlay.hide()
            return False

        # Count unique files, not cards: a recording assigned to several species
        # appears under each of those sightings, so tallying (sighting, audio)
        # pairs would overcount the actual recordings.
        species = set()
        audioFiles = set()
        for s in recordingSightings:
            for a in s.get("audio", []):
                audioFiles.add(a["fileName"])
                species.add(s["commonName"])
        audioCount = len(audioFiles)

        self.lblSpecies.setText(
            "Species: " + str(len(species)) + ".  Recordings: " + str(audioCount))
        self.mdiParent.SetChildDetailsLabels(self, filter)
        self.setWindowTitle(filter.buildWindowTitle(
            "Recordings", self.mdiParent.db, count=audioCount, countUnit="Recordings"))

        self.audioList = []
        for s in recordingSightings:
            for a in s.get("audio", []):
                self.audioList.append([a, s])
                if self._abort:
                    self.mdiParent.progressOverlay.hide()
                    return False

        self._buildRows()

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_microphone_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        if not self.audioList:
            self.mdiParent.progressOverlay.hide()
            self.close()

        return True

    def FillSingleRecording(self, audioData, sightingData):
        """Show exactly one known recording, bypassing the normal
        filter-driven query — used when launched from a Find Results hit on
        that recording's Notes, where only the specific matched file (not its
        whole checklist) should be shown."""
        self.scaleMe()
        self.resizeMe()

        filter = code_Filter.Filter()
        filter.setSpeciesName(sightingData["commonName"])
        filter.setLocationName(sightingData["location"])
        filter.setLocationType("Location")
        filter.setStartDate(sightingData["date"])
        filter.setEndDate(sightingData["date"])
        self.filter = filter
        self._singleMode = True

        self.lblSpecies.setText("Species: 1.  Recordings: 1")
        self.mdiParent.SetChildDetailsLabels(self, filter)
        self.setWindowTitle(filter.buildWindowTitle(
            "Recordings", self.mdiParent.db, count=1, countUnit="Recordings"))

        self.audioList = [[audioData, sightingData]]

        self._buildRows()

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_microphone_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        return True

    def _sortAudioList(self):
        """Sort audioList by the checked radio; returns the permutation
        (new position -> old index) so row widgets and bookkeeping can
        follow the data."""
        idx = range(len(self.audioList))
        if self.rdoSortSpecies.isChecked():
            order = sorted(idx, key=lambda i: self.audioList[i][1]["commonName"])
        elif self.rdoSortDate.isChecked():
            # Sort by the recording's own embedded datetime (what the caption
            # shows), falling back to the checklist's date/time (see the
            # Photos browser's _capture_dt for the rationale).
            def _capture_dt(i):
                a, s = self.audioList[i]
                if a.get("metaDate"):
                    return a["metaDate"] + " " + a.get("metaTime", "")
                return s.get("date", "") + " " + s.get("time", "")
            order = sorted(idx, key=_capture_dt)
        elif self.rdoSortRating.isChecked():
            def _rating(i):
                try:
                    return float(self.audioList[i][0].get("rating") or 0)
                except (ValueError, TypeError):
                    return 0.0
            order = sorted(idx, key=_rating, reverse=True)
        elif self.rdoSortTaxonomy.isChecked():
            order = sorted(idx, key=lambda i: (float(self.audioList[i][1]["taxonomicOrder"]),
                                               self.audioList[i][1]["commonName"]))
        else:
            order = list(idx)
        self.audioList = [self.audioList[i] for i in order]
        return order

    def SortAndDisplayRecordings(self):
        """Radio-button sort: reorder the EXISTING row widgets in place —
        no rebuild, no spectrogram reloads (see SortAndDisplayPhotos)."""
        if not self.audioList:
            return
        if self._sorting or self.threadsRemaining > 0:
            return
        if not self._rowWidgets:
            self._buildRows()
            return
        self._sorting = True

        # Stop playback when re-sorting so scrubber state stays consistent.
        if self._player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
            self._player.stop()
        self._activeRow = None

        order = self._sortAudioList()

        # Detach every row item from the layout (the widgets survive), then
        # re-insert them in the new order and remap the row-indexed
        # bookkeeping.  Handlers carry baked-in row numbers: the spectro
        # click is a plain attribute (reassigned); Play/scrubber are signal
        # connections (disconnected and reconnected at the new index).
        while self.rowsLayout.count():
            self.rowsLayout.takeAt(0)
        newRows, newSpectros, newBtns, newSliders, newPaths = {}, {}, {}, {}, {}
        for new_row, old_row in enumerate(order):
            w = self._rowWidgets.get(old_row)
            if w is None:
                continue
            self.rowsLayout.addWidget(w)
            newRows[new_row] = w
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
        self.scrollArea.verticalScrollBar().setValue(0)
        self._sorting = False

    def _buildRows(self):
        """Full grid build (initial fill / after a deletion): sort, then
        create every row and stream the spectrograms in from the workers."""
        if not self.audioList:
            return
        if self._sorting:
            return
        self._sorting = True

        # Stop playback when rebuilding so scrubber state stays consistent.
        if self._player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
            self._player.stop()
        self._activeRow = None

        QApplication.processEvents()

        self._sortAudioList()

        # Clear the existing rows
        for i in reversed(range(self.rowsLayout.count())):
            w = self.rowsLayout.itemAt(i).widget()
            if w:
                w.setParent(None)

        self._spectroLabels = {}
        self._playBtns = {}
        self._sliders = {}
        self._filePaths = {}
        self._rowWidgets = {}
        uncached = []

        for row, (a, s) in enumerate(self.audioList):
            fileName = a.get("fileName", "")

            # ── Col 0: spectrogram + scrubber ──────────────────────────────────
            # Same display geometry as the Photos browser thumbnails.
            visContainer = QWidget()
            visContainer.setObjectName("cardTransparent")
            visContainer.setFixedWidth(code_ThumbnailCache.THUMB_DISPLAY_SIZE.width())
            visLayout = QVBoxLayout(visContainer)
            visLayout.setContentsMargins(0, 0, 0, 0)
            visLayout.setSpacing(7)   # breathing room between spectro and Play strip

            spectroLabel = SpectrogramLabel()
            spectroLabel.setCursor(Qt.PointingHandCursor)
            spectroLabel.mousePressEvent = partial(self._spectroClicked, row)
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

            self._spectroLabels[row] = spectroLabel
            self._filePaths[row] = fileName

            # ── Col 1: caption ─────────────────────────────────────────────────
            # Prefer the recording's true (embedded) creation date/time; fall
            # back to the checklist date/time when the file carries no metadata.
            if a.get("metaDate"):
                dispDate, dispTime = a["metaDate"], a.get("metaTime", "")
            else:
                dispDate, dispTime = s.get("date", ""), s.get("time", "")
            try:
                weekday = datetime.datetime(
                    int(dispDate[0:4]), int(dispDate[5:7]), int(dispDate[8:10])
                ).strftime("%A")
            except Exception:
                weekday = ""
            dateLine = dispDate + ((" " + dispTime) if dispTime else "")
            if weekday:
                dateLine = weekday + ", " + dateLine

            rating = a.get("rating", "0")

            # No Duration line — the duration is visible on the spectrogram's
            # time axis; the blank line matches the Photos browser caption.
            captionText = (
                "<br><br>"
                '<span style="font-size: 1.1em; font-weight: bold;">' + s["commonName"] + "</span><br>"
                "<i>" + s["scientificName"] + "</i><br><br>"
                + s["location"] + "<br>"
                + dateLine + "<br><br>"
                + "Rating: " + rating
            )

            labelCaption = QLabel()
            labelCaption.setTextFormat(Qt.RichText)
            labelCaption.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            labelCaption.setText(captionText)
            labelCaption.setObjectName("mediaCaption")

            # One container widget per row in a QVBoxLayout (avoids the grid's
            # ~524k-px height cap that squashed rows past ~1,600 recordings).
            # Row height = photo-thumbnail height + the Play/scrubber strip
            # (28px + 7px spacing) + the card's 12px internal padding.  The
            # row carries the shared media-card background; children are
            # transparent.
            rowWidget = QWidget()
            rowWidget.setObjectName("mediaCard")
            rowWidget.setAttribute(Qt.WA_StyledBackground, True)
            rowWidget.setMinimumHeight(
                code_ThumbnailCache.THUMB_DISPLAY_SIZE.height() + 47)
            rowLayout = QHBoxLayout(rowWidget)
            rowLayout.setContentsMargins(6, 6, 6, 6)   # inset content off the rounded corners
            rowLayout.setSpacing(2)
            rowLayout.addWidget(visContainer)
            rowLayout.addWidget(labelCaption, 1)   # caption absorbs the extra width

            self.rowsLayout.addWidget(rowWidget)
            self._rowWidgets[row] = rowWidget

            if fileName not in self.spectroCache:
                uncached.append((row, fileName))

        # Apply cached spectrograms once layout has settled.
        QApplication.processEvents()
        for row, (a, _s) in enumerate(self.audioList):
            fileName = a.get("fileName", "")
            if fileName in self.spectroCache:
                lbl = self._spectroLabels.get(row)
                if lbl:
                    pm, bbox = self.spectroCache[fileName]
                    lbl.setPixmap(pm, bbox)

        self.scrollArea.verticalScrollBar().setValue(0)

        if uncached:
            for item in uncached:
                self.workQueue.put(item)
            threadsToStart = min(self.threadCount, len(uncached))
            self.threadsRemaining = threadsToStart
            self._loadedCount = 0
            self._totalUncached = len(uncached)
            self._threadsToStart = threadsToStart
            self.mdiParent.progressOverlay.startLoading(len(uncached))
            QTimer.singleShot(0, self._startThreads)
        else:
            self._finishLoading()

    def _startThreads(self):
        if self._abort:
            return
        for i in range(self._threadsToStart):
            self.threads[i].start()
        self._drainTimer.start(50)

    def _drainResultQueue(self):
        prevCount = self._loadedCount

        while True:
            try:
                (row, audioFile, img, ax_bbox,
                 duration, sr, axesPending) = self.resultQueue.get_nowait()
            except queue.Empty:
                break

            if self._abort:
                continue

            if img is not None and not img.isNull():
                # Composite the kHz/sec axes here on the GUI thread (the worker
                # rendered the spectrogram text-free), then cache the finished
                # image.  The QImage→QPixmap conversion also happens here: the
                # workers pass QImage only, because QPixmap is GUI-thread-only.
                if axesPending:
                    _paint_spectro_axes(img, duration, sr)
                    code_ThumbnailCache.store(
                        audioFile, img, "spectro_thumb",
                        code_ThumbnailCache.SPECTRO_THUMB_VARIANT)
                pixmap = QPixmap.fromImage(img)
                self.spectroCache[audioFile] = (pixmap, ax_bbox)
                lbl = self._spectroLabels.get(row)
                if lbl:
                    lbl.setPixmap(pixmap, ax_bbox)
            else:
                lbl = self._spectroLabels.get(row)
                if lbl:
                    lbl.setErrorText("Cannot load:\n" + os.path.basename(audioFile))

            self._loadedCount += 1

        if not self._abort and self._loadedCount > prevCount:
            self.mdiParent.progressOverlay.setPhotoValue(self._loadedCount)

        if self.threadsRemaining == 0 and self.resultQueue.empty():
            self._drainTimer.stop()
            self._finishLoading()

    def spectroThreadFinished(self):
        if self._abort:
            return
        self.threadsRemaining -= 1

    def _finishLoading(self):
        self.mdiParent.progressOverlay.hide()
        self.scrollArea.verticalScrollBar().setValue(0)
        self._sorting = False

    # ------------------------------------------------------------------
    # Enlargement
    # ------------------------------------------------------------------

    def _spectroClicked(self, row, event):
        import code_RecordingEnlargement
        if row >= len(self.audioList):
            return
        # Stop Browse Recordings playback before spawning the enlargement so the
        # two windows don't play over each other.
        self._player.stop()
        a, s = self.audioList[row]
        fileName = a.get("fileName", "")
        cached = self.spectroCache.get(fileName)   # (QPixmap, ax_bbox) or None
        sub = code_RecordingEnlargement.RecordingEnlargement()
        sub.mdiParent = self.mdiParent
        sub._audioList = self.audioList
        sub._currentIdx = row
        sub._spectroCache = self.spectroCache
        self.mdiParent.mdiArea.addSubWindow(sub)
        willMaximize = self.mdiParent.PositionChildWindow(sub, self.mdiParent)
        # Fill before showing so the window appears complete rather than empty
        # then filling in (fillEnlargement decodes the WAV and renders the
        # overview synchronously).  When spawned from a maximized parent,
        # PositionChildWindow has scheduled a deferred showMaximized as the first
        # appearance, so skip the show() here to avoid a small-size flash.
        sub.fillEnlargement(fileName, s, overview_cache=cached)
        if not willMaximize:
            sub.show()
