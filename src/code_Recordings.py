import form_Recordings
from code_ManageRecordings import _build_spectrogram_pixmap, SpectrogramLabel, PcmAudioPlayer, SPECTRO_AX_BBOX
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
            img = code_ThumbnailCache.load(audioFile, "spectro_thumb")
            if img is not None and not img.isNull():
                pixmap = QPixmap.fromImage(img)
                ax_bbox = SPECTRO_AX_BBOX
            else:
                # Tier 3: render the spectrogram, then cache it.
                pixmap, _duration, _sr, ax_bbox = _build_spectrogram_pixmap(audioFile)
                if pixmap is not None and not pixmap.isNull():
                    code_ThumbnailCache.store(audioFile, pixmap.toImage(), "spectro_thumb")

            self.resultQueue.put((row, audioFile, pixmap, ax_bbox))
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
        self.spectroCache = {}   # filename -> (QPixmap, ax_bbox)
        # Qt caps a QGridLayout's total height at ~524k px, which squashes the
        # rows once there are more than ~1,600 recordings.  Use a QVBoxLayout of
        # per-row widgets instead (no such cap until ~50k); the form's gridAudio
        # is left unused.
        self.gridAudio.setContentsMargins(0, 0, 0, 0)
        self.rowsLayout = QVBoxLayout()
        self.rowsLayout.setContentsMargins(0, 0, 0, 0)
        self.rowsLayout.setSpacing(2)
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

    def handleAudioDeletion(self, filename):
        orig_len = len(self.audioList)
        self.audioList = [(a, s) for (a, s) in self.audioList if a.get("fileName") != filename]
        if len(self.audioList) == orig_len:
            return
        self.spectroCache.pop(filename, None)
        if not self.audioList:
            self.close()
            return
        self.SortAndDisplayRecordings()

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
                w.setFont(QFont("", fontSize))
            except Exception:
                pass
        self.lblLocation.setFont(QFont("", floor(fontSize * 1.4)))
        self.lblLocation.setStyleSheet("QLabel { font: bold }")
        self.lblDateRange.setFont(QFont("", floor(fontSize * 1.2)))
        self.lblDateRange.setStyleSheet("QLabel { font: bold }")
        self.lblDetails.setFont(QFont("", floor(fontSize * 1.2)))
        self.lblDetails.setStyleSheet("QLabel { font: bold }")
        self.lblSpecies.setFont(QFont("", fontSize))
        self.lblSortBy.setFont(QFont("", fontSize))
        self.rdoSortSpecies.setFont(QFont("", fontSize))
        self.rdoSortDate.setFont(QFont("", fontSize))
        self.rdoSortRating.setFont(QFont("", fontSize))
        self.rdoSortTaxonomy.setFont(QFont("", fontSize))
        for c in self.layLists.findChildren(QLabel):
            c.setFont(QFont("", fontSize))
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

    def _anchorPlayback(self, pos_sec):
        """Reset the wall-clock interpolation anchor (seconds).

        The backend position() advances in coarse ~90 ms buffer steps; anchoring
        only at play and on seeks — rather than re-snapping to that staircase
        every 100 ms poll — keeps the red cursor line sliding smoothly."""
        self._lastRealPosSec = pos_sec
        self._lastPollTime   = time.perf_counter()

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

        if self._lastPollTime is not None:
            interp = self._lastRealPosSec + (time.perf_counter() - self._lastPollTime)
            if abs(pos_sec - interp) > 0.25:
                self._anchorPlayback(pos_sec)
        else:
            self._anchorPlayback(pos_sec)

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
        pos_sec  = min(self._lastRealPosSec + (time.perf_counter() - self._lastPollTime), dur)
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

        species = set()
        audioCount = 0
        for s in recordingSightings:
            for a in s.get("audio", []):
                audioCount += 1
                species.add(s["commonName"])

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

        self.SortAndDisplayRecordings()

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_bird_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        if not self.audioList:
            self.mdiParent.progressOverlay.hide()
            self.close()

        return True

    def SortAndDisplayRecordings(self):
        if not self.audioList:
            return
        if self._sorting:
            return
        self._sorting = True

        # Stop playback when re-sorting so scrubber state stays consistent.
        if self._player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
            self._player.stop()
        self._activeRow = None

        QApplication.processEvents()

        if self.rdoSortSpecies.isChecked():
            self.audioList.sort(key=lambda x: x[1]["commonName"])
        elif self.rdoSortDate.isChecked():
            self.audioList.sort(key=lambda x: x[1]["date"] + x[1]["time"])
        elif self.rdoSortRating.isChecked():
            try:
                self.audioList.sort(
                    key=lambda x: float(x[0].get("rating") or 0), reverse=True)
            except (ValueError, TypeError):
                self.audioList.sort(key=lambda x: x[0].get("rating", ""), reverse=True)
        elif self.rdoSortTaxonomy.isChecked():
            self.audioList.sort(
                key=lambda x: (float(x[1]["taxonomicOrder"]), x[1]["commonName"]))

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
            visContainer = QWidget()
            visContainer.setFixedWidth(500)
            visLayout = QVBoxLayout(visContainer)
            visLayout.setContentsMargins(0, 0, 0, 0)
            visLayout.setSpacing(2)

            spectroLabel = SpectrogramLabel()
            spectroLabel.setCursor(Qt.PointingHandCursor)
            spectroLabel.mousePressEvent = partial(self._spectroClicked, row)
            visLayout.addWidget(spectroLabel)

            scrubRow = QWidget()
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

            self._spectroLabels[row] = spectroLabel
            self._filePaths[row] = fileName

            # ── Col 1: caption ─────────────────────────────────────────────────
            try:
                weekday = datetime.datetime(
                    int(s["date"][0:4]), int(s["date"][5:7]), int(s["date"][8:10])
                ).strftime("%A")
            except Exception:
                weekday = ""

            duration = a.get("duration", "")
            rating = a.get("rating", "0")

            captionText = (
                "<br><br>"
                '<span style="font-size: 1.1em; font-weight: bold;">' + s["commonName"] + "</span><br>"
                "<i>" + s["scientificName"] + "</i><br><br>"
                + s["location"] + "<br>"
                + weekday + ", " + s["date"] + " " + s["time"]
                + ("<br>Duration: " + duration if duration else "")
                + "<br>Rating: " + rating
            )

            labelCaption = QLabel()
            labelCaption.setTextFormat(Qt.RichText)
            labelCaption.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            labelCaption.setText(captionText)
            labelCaption.setStyleSheet(
                "QLabel { background-color: #343333; color: silver; padding: 3px; }")

            # One container widget per row in a QVBoxLayout (avoids the grid's
            # ~524k-px height cap that squashed rows past ~1,600 recordings).
            rowWidget = QWidget()
            rowWidget.setMinimumHeight(330)
            rowLayout = QHBoxLayout(rowWidget)
            rowLayout.setContentsMargins(0, 0, 0, 0)
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
                row, audioFile, pixmap, ax_bbox = self.resultQueue.get_nowait()
            except queue.Empty:
                break

            if self._abort:
                continue

            if pixmap and not pixmap.isNull():
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
        a, s = self.audioList[row]
        fileName = a.get("fileName", "")
        cached = self.spectroCache.get(fileName)   # (QPixmap, ax_bbox) or None
        sub = code_RecordingEnlargement.RecordingEnlargement()
        sub.mdiParent = self.mdiParent
        sub._audioList = self.audioList
        sub._currentIdx = row
        sub._spectroCache = self.spectroCache
        self.mdiParent.mdiArea.addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self.mdiParent)
        sub.show()
        sub.fillEnlargement(fileName, s, overview_cache=cached)
