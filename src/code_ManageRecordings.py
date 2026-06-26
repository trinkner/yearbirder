import form_ManageRecordings
import code_Filter
import code_Stylesheet
import code_ThumbnailCache
import os
import queue
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
    QSlider,
)
from PySide6.QtMultimedia import (
    QMediaPlayer, QAudioFormat, QAudioSink, QMediaDevices,
)


def _decode_wav_pcm16(wav_path, normalize=True, target_fs=None, target_channels=None):
    """Decode a WAV file to interleaved little-endian 16-bit PCM bytes.

    Returns ``(bytes, sample_rate, channels, duration_ms)`` or ``None`` on
    failure.  When ``target_fs`` / ``target_channels`` are given the audio is
    resampled (linear interpolation) and re-channelled to that fixed output
    format — this lets a single QAudioSink be reused across files of differing
    native formats, avoiding a costly per-file sink re-create.  ``duration_ms``
    is always the true wall-clock length, independent of resampling.  When
    ``normalize`` is true, quiet recordings (peak < 0.1 full-scale) are boosted
    in memory — replacing the old temp-file normalisation with a zero-I/O
    equivalent.
    """
    import wave as _wave
    try:
        with _wave.open(wav_path, 'r') as wf:
            n_ch     = wf.getnchannels()
            fs       = wf.getframerate()
            n_frames = wf.getnframes()
            sw       = wf.getsampwidth()
            raw      = wf.readframes(n_frames)
    except Exception:
        return None

    if sw == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sw == 2:
        data = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
    elif sw == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        a = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        a = np.where(a >= 0x800000, a - 0x1000000, a)
        data = a.astype(np.float32) / 8388608.0
    elif sw == 4:
        data = np.frombuffer(raw, dtype='<i4').astype(np.float32) / 2147483648.0
    else:
        return None

    dur_ms = int(round(n_frames / fs * 1000)) if fs else 0

    out_ch = target_channels if target_channels else n_ch
    out_fs = target_fs if target_fs else fs

    # De-interleave to (frames, channels) for re-channelling / resampling.
    frames = data.reshape(-1, n_ch) if n_ch > 1 else data.reshape(-1, 1)

    if out_ch != n_ch:
        if out_ch == 1:
            frames = frames.mean(axis=1, keepdims=True)
        else:                                   # up/replicate to out_ch
            cols = [frames[:, min(c, n_ch - 1)] for c in range(out_ch)]
            frames = np.column_stack(cols)

    if out_fs != fs and frames.shape[0] > 1:
        n_old = frames.shape[0]
        n_new = max(1, int(round(n_old * out_fs / fs)))
        old_x = np.arange(n_old, dtype=np.float64)
        new_x = np.linspace(0.0, n_old - 1, n_new)
        frames = np.column_stack(
            [np.interp(new_x, old_x, frames[:, c]) for c in range(frames.shape[1])])

    data = frames.reshape(-1)

    if normalize and len(data) > 0:
        peak = float(np.max(np.abs(data)))
        if 0.0 < peak < 0.1:
            data = data * (0.9 / peak)

    pcm = np.clip(data, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype('<i2')
    return pcm.tobytes(), out_fs, out_ch, dur_ms


class _PcmStreamDevice(QIODevice):
    """Endless pull source for a continuously-running QAudioSink.

    Returns real PCM (advancing an internal byte cursor) while ``_playing`` is
    set, and silence otherwise — so the sink is never starved and the audio
    output device stays running.  Keeping the device running is what avoids the
    per-start mute/spin-up latency that a stop/start (or suspend/resume) of the
    sink incurs on macOS Core Audio.
    """

    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data       = b''
        self._cursor     = 0       # byte offset of next real sample to emit
        self._frame      = 2       # bytes per audio frame (channels * 2)
        self._playing    = False
        self._emittedEnd = False

    def loadData(self, data, frame_bytes):
        self._data       = data
        self._frame      = max(1, int(frame_bytes))
        self._cursor     = 0
        self._emittedEnd = False

    def lengthBytes(self):
        return len(self._data)

    def cursorBytes(self):
        return self._cursor

    def setPlaying(self, playing):
        self._playing = bool(playing)

    def seekBytes(self, off):
        off = max(0, min(int(off), len(self._data)))
        off -= off % self._frame
        self._cursor = off
        self._emittedEnd = False

    # QIODevice overrides ------------------------------------------------
    def isSequential(self):
        return True

    def bytesAvailable(self):
        # Endless source: always advertise a healthy chunk so the sink pulls.
        return (1 << 20) + super().bytesAvailable()

    def readData(self, maxlen):
        n = int(maxlen)
        n -= n % self._frame
        if n <= 0:
            n = self._frame
        if self._playing and self._cursor < len(self._data):
            end   = min(self._cursor + n, len(self._data))
            chunk = self._data[self._cursor:end]
            self._cursor = end
            if self._cursor >= len(self._data) and not self._emittedEnd:
                self._emittedEnd = True
                self.finished.emit()
            if len(chunk) < n:                 # pad final partial frame run
                chunk = chunk + b'\x00' * (n - len(chunk))
            return bytes(chunk)
        # Paused, stopped, or past end → silence keeps the device warm.
        return b'\x00' * n

    def writeData(self, data):
        return 0


class PcmAudioPlayer(QObject):
    """Low-latency WAV player built on a continuously-running QAudioSink.

    QMediaPlayer's macOS/AVFoundation backend re-primes its audio renderer on
    every ``setSource()`` (0-7 s of silent-but-advancing output).  Creating a
    fresh QAudioSink per play has the same problem: starting a Core Audio output
    unit incurs a variable 0-7 s spin-up/mute the *first* time it runs.

    This player therefore creates **one** QAudioSink **once, at construction**,
    and never re-creates it — so the audio device is warmed as soon as the owning
    window opens, long before the user presses Play.  It is fed by an endless
    :class:`_PcmStreamDevice` that emits silence when not playing, so the unit
    never stops either.  Loading a new file just swaps the device's PCM data;
    play/pause/seek only flip a flag or move a byte cursor.  Because the sink is
    fixed-format, every file is decoded/resampled to that one output format
    (:data:`_OUT_FS` / :data:`_OUT_CH`).

    The public API mirrors the subset of QMediaPlayer used by the Recordings
    browser and Enlargement window, reusing QMediaPlayer's own enum values so
    the callers' comparisons and signal handlers are unchanged.
    """

    playbackStateChanged = Signal(object)
    mediaStatusChanged   = Signal(object)

    # Sink buffer: small enough that the leading silence drains quickly when
    # play() flips the device to real audio (this sets the residual latency),
    # large enough to avoid underruns from the Python pull callback.
    _BUFFER_SECONDS = 0.05
    _OUT_CH = 2                       # fixed output channel count

    def __init__(self, parent=None):
        super().__init__(parent)
        self._durationMs = 0
        self._hasMedia   = False
        self._state      = QMediaPlayer.PlaybackState.StoppedState

        # Fixed output format — chosen from the device's preferred rate so the
        # single persistent sink is always supported; all files are resampled
        # to it.  Int16 stereo is universally accepted.
        pref = QMediaDevices.defaultAudioOutput().preferredFormat()
        self._outFs = pref.sampleRate() if pref.sampleRate() > 0 else 48000
        self._bytesPerFrame = 2 * self._OUT_CH

        fmt = QAudioFormat()
        fmt.setSampleRate(self._outFs)
        fmt.setChannelCount(self._OUT_CH)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)

        self._device = _PcmStreamDevice(self)
        self._device.loadData(b'', self._bytesPerFrame)
        self._device.finished.connect(self._onFinished)
        self._device.open(QIODevice.OpenModeFlag.ReadOnly)

        self._sink = QAudioSink(QMediaDevices.defaultAudioOutput(), fmt, self)
        buf = int(self._outFs * self._bytesPerFrame * self._BUFFER_SECONDS)
        if buf > 0:
            self._sink.setBufferSize(buf)
        # Starts now (silent) so Core Audio is warm before the first Play click.
        self._sink.start(self._device)

    # ── source ──────────────────────────────────────────────────────────
    def setSourceWav(self, wav_path):
        decoded = _decode_wav_pcm16(
            wav_path, target_fs=self._outFs, target_channels=self._OUT_CH)
        if not decoded:
            self._hasMedia = False
            self._durationMs = 0
            self.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.InvalidMedia)
            return False
        pcm, _fs, _ch, dur_ms = decoded
        self._durationMs = dur_ms
        self._hasMedia   = True
        # Swap data in the already-running device; the sink is untouched.
        self._device.setPlaying(False)
        self._device.loadData(pcm, self._bytesPerFrame)
        self._setState(QMediaPlayer.PlaybackState.StoppedState)
        self.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.LoadedMedia)
        return True

    def mediaStatus(self):
        return (QMediaPlayer.MediaStatus.LoadedMedia
                if self._hasMedia
                else QMediaPlayer.MediaStatus.NoMedia)

    # ── transport ───────────────────────────────────────────────────────
    def play(self):
        if not self._hasMedia:
            return
        if self._device.cursorBytes() >= self._device.lengthBytes():
            self._device.seekBytes(0)          # at end → restart from start
        self._device.setPlaying(True)
        self._setState(QMediaPlayer.PlaybackState.PlayingState)

    def pause(self):
        if self._state == QMediaPlayer.PlaybackState.PlayingState:
            self._device.setPlaying(False)
            self._setState(QMediaPlayer.PlaybackState.PausedState)

    def stop(self):
        self._device.setPlaying(False)
        self._device.seekBytes(0)
        self._setState(QMediaPlayer.PlaybackState.StoppedState)

    def setPosition(self, ms):
        ms = max(0, min(int(ms), self._durationMs))
        self._device.seekBytes(int(ms * self._outFs / 1000) * self._bytesPerFrame)

    # ── queries ─────────────────────────────────────────────────────────
    def position(self):
        ms = int(self._device.cursorBytes() / self._bytesPerFrame / self._outFs * 1000)
        return min(ms, self._durationMs)

    def duration(self):
        return self._durationMs

    def playbackState(self):
        return self._state

    # ── internals ───────────────────────────────────────────────────────
    def _setState(self, state):
        if state != self._state:
            self._state = state
            self.playbackStateChanged.emit(state)

    def _onFinished(self):
        # Reached the end of the clip while playing (queued from the pull thread).
        self._device.setPlaying(False)
        self._device.seekBytes(0)
        self._setState(QMediaPlayer.PlaybackState.StoppedState)
        self.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.EndOfMedia)


# Fixed axes rectangle (x0, x1, y0, y1, figure-fraction, origin bottom-left)
# produced by the subplots_adjust() margins below.  Because it's constant, a
# cached spectrogram image can be reused without storing per-file bbox metadata.
SPECTRO_AX_BBOX = (0.13, 0.98, 0.15, 0.95)


def _render_spectrogram_qimage(wav_path, max_freq=10000):
    """Render a spectrogram for wav_path, returning a QImage.

    Returns (QImage, duration_secs, sample_rate, ax_bbox) where ax_bbox is the
    constant SPECTRO_AX_BBOX.  Returns (None, 0, 0, None) on error.  Uses only the
    Agg backend and QImage (no QPixmap), so it is safe to call off the GUI thread.
    """
    import wave as _wave
    try:
        with _wave.open(wav_path, 'r') as wf:
            n_ch = wf.getnchannels()
            fs = wf.getframerate()
            n_frames = wf.getnframes()
            sw = wf.getsampwidth()
            raw = wf.readframes(n_frames)
    except Exception:
        return None, 0, 0, None

    duration = n_frames / fs if fs else 0

    if sw == 1:
        data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        data = (data - 128.0) / 128.0
    elif sw == 4:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    if n_ch > 1:
        data = data[::n_ch]

    if len(data) < 64:
        return None, duration, fs, None

    # Adaptive overlap: keep 75 % overlap (noverlap=384) for short clips, but
    # widen the hop on long recordings so the STFT produces only ~900 columns
    # instead of many thousands.  The thumbnail is ~500 px wide, so the extra
    # columns are invisible work; the max(128, …) floor preserves quality on
    # short clips and noverlap stays in [0, NFFT) so windows remain contiguous.
    NFFT = 512
    hop = max(128, (len(data) - NFFT) // 900)
    noverlap = max(0, min(NFFT - hop, NFFT - 1))

    fig = Figure(figsize=(5.0, 2.9), dpi=100)
    fig.patch.set_facecolor('white')
    ax = fig.add_subplot(111)
    try:
        with np.errstate(divide='ignore', invalid='ignore'):
            spectrum, _freqs, _bins, im = ax.specgram(
                data, Fs=fs, NFFT=NFFT, noverlap=noverlap, cmap='gray_r', scale='dB')
        db = 10.0 * np.log10(np.maximum(spectrum, 1e-12))
        db_hi = float(np.percentile(db, 99.5))
        im.set_clim(db_hi - 80.0 * 0.50, db_hi)   # 50 % contrast, matches AudioEnlargement default
    except Exception:
        return None, duration, fs, None

    ax.set_ylim(0, min(max_freq, fs // 2))
    ax.set_facecolor('white')
    ax.tick_params(colors='#444444', labelsize=7)
    ax.set_ylabel('Hz', color='#444444', fontsize=7)
    ax.set_xlabel('sec', color='#444444', fontsize=7)
    for sp in ax.spines.values():
        sp.set_edgecolor('#aaaaaa')
    # Fixed margins (not tight_layout) so the data rect is a known constant
    # (SPECTRO_AX_BBOX) — the cached image needs no per-file bbox metadata.
    fig.subplots_adjust(left=0.13, right=0.98, bottom=0.15, top=0.95)

    canvas = FigureCanvasAgg(fig)
    canvas.draw()

    ax_bbox = SPECTRO_AX_BBOX

    # Build the QPixmap straight from the Agg RGBA buffer — avoids a PNG
    # encode/decode round-trip that dominated render time.  copy() is required:
    # the buffer is released when the figure/canvas is garbage-collected.
    w_px, h_px = canvas.get_width_height()
    img = QImage(canvas.buffer_rgba(), w_px, h_px, QImage.Format_RGBA8888)
    return img.copy(), duration, fs, ax_bbox


def _build_spectrogram_pixmap(wav_path, max_freq=10000):
    """QPixmap wrapper around _render_spectrogram_qimage for GUI-thread/QThread
    callers that display the result.  Returns (QPixmap, dur, fs, ax_bbox)."""
    img, duration, fs, ax_bbox = _render_spectrogram_qimage(wav_path, max_freq)
    if img is None or img.isNull():
        return None, duration, fs, ax_bbox
    return QPixmap.fromImage(img), duration, fs, ax_bbox


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
        self.setMinimumWidth(500)
        self.setMinimumHeight(290)

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
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 2, 0, 2)
        self._layout.setSpacing(3)
        self.setVisible(False)

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
        for name in self._species:
            self._layout.addWidget(self._makeChip(name))
        self.setVisible(bool(self._species))

    def _makeChip(self, name):
        chip = QWidget()
        chipLayout = QHBoxLayout(chip)
        chipLayout.setContentsMargins(8, 3, 4, 3)
        chipLayout.setSpacing(4)
        label = QLabel(name)
        label.setStyleSheet("color: white; background: transparent; border: none;")
        removeBtn = QPushButton("×")
        removeBtn.setFixedSize(18, 18)
        removeBtn.setFlat(True)
        removeBtn.setStyleSheet(
            "QPushButton { color: white; font-weight: bold; "
            "background: transparent; border: none; }"
            "QPushButton:hover { background: rgba(255,255,255,40); border-radius: 9px; }"
        )
        removeBtn.clicked.connect(partial(self.removeSpecies, name))
        chipLayout.addWidget(label)
        chipLayout.addStretch()
        chipLayout.addWidget(removeBtn)
        chip.setStyleSheet("QWidget { background-color: #4a86c8; border-radius: 8px; }")
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

            pixmap, _dur, _fs, ax_bbox = _build_spectrogram_pixmap(file)
            recordingData = self.parent.mdiParent.db.getRecordingData(file)

            if mode == "new":
                audioMatchData = self.parent.mdiParent.db.matchRecording(file)
                comboData = self.parent.mdiParent.db.getComboDataForAudio(audioMatchData)
                cascadeMode = "date_first"
                allSightings = None
            else:
                s = item["sighting"]
                a = item["recordingData"]
                allSightings = item.get("allSightings", [s])
                recordingData["rating"] = a.get("rating", "0")
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
            entry["comboData"] = comboData
            entry["cascadeMode"] = cascadeMode
            entry["allSightings"] = allSightings

            self.resultQueue.put(entry)
            self.workQueue.task_done()

        self.sigThreadFinished.emit()


class ManageRecordings(QMdiSubWindow, form_ManageRecordings.Ui_frmManageRecordings):

    resized = Signal()

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
        self.audioAlreadyInDb = True
        self._changesSaved = False
        self._skipCloseGuard = False

        self.threadCount = min(os.cpu_count() or 4, 8)
        self.workQueue = queue.Queue()
        self.resultQueue = queue.Queue()
        self.threadsRemaining = 0
        self.threads = []
        self._loadedCount = 0
        self._totalFiles = 0
        self._threadsToStart = 0

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
        icon.addPixmap(QPixmap(":/icon_bird_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        if (not self._skipCloseGuard and
                not self._changesSaved and
                not self.audioAlreadyInDb and
                self.metaDataByRow):
            reply = QMessageBox.question(
                self, "Unsaved Recordings",
                "Your recording information has not been saved to a catalog.\n\n"
                "Close anyway and discard your work?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
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
                w.setFont(QFont("", fontSize))
            except Exception:
                pass
        for c in self.layLists.children():
            if "QLabel" in str(c):
                c.setFont(QFont("", fontSize))
        windowWidth = int(1200 * scaleFactor)
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
            self._player.play()

    def _onSliderMoved(self, row, value):
        """User dragged the scrubber; seek player and update the cursor line."""
        if self._activeRow == row and self._player.duration() > 0:
            pos_ms = int(value / 1000.0 * self._player.duration())
            self._player.setPosition(pos_ms)
        if self._activeRow == row:
            lbl = self._spectroLabels.get(row)
            if lbl:
                lbl.setFraction(value / 1000.0)

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
            QApplication.processEvents()
            if os.path.splitext(f)[1].lower() == ".wav":
                allowed.append({"row": row, "file": f, "mode": "new"})
                row += 1

        if not allowed:
            QApplication.restoreOverrideCursor()
            return

        for item in allowed:
            self.workQueue.put(item)

        self._totalFiles = len(allowed)
        self._loadedCount = 0
        self._threadsToStart = min(self.threadCount, len(allowed))
        self.threadsRemaining = self._threadsToStart

        self.mdiParent.lblStatusBarMessage.setVisible(True)
        self.mdiParent.lblStatusBarMessage.setText("Loading recording files...")
        QApplication.processEvents()

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

        self.mdiParent.lblStatusBarMessage.setVisible(True)
        self.mdiParent.lblStatusBarMessage.setText("Loading recording files...")
        QApplication.processEvents()

        self.audioAlreadyInDb = True
        self.fillingCombos = False
        self.setWindowTitle("Manage Recordings")

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_bird_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        QTimer.singleShot(0, self._startThreads)
        return True

    def _startThreads(self):
        for i in range(self._threadsToStart):
            self.threads[i].start()
        self._drainTimer.start(50)

    def _drainResultQueue(self):
        prevCount = self._loadedCount
        while True:
            try:
                entry = self.resultQueue.get_nowait()
            except queue.Empty:
                break
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

        if self._loadedCount > 0 and (
                self._loadedCount // 5 > prevCount // 5 or prevCount == 0):
            self.mdiParent.lblStatusBarMessage.setText(
                f"Loading recordings: {self._loadedCount} of {self._totalFiles}...")

        if self.threadsRemaining == 0 and self.resultQueue.empty():
            self._drainTimer.stop()
            self._finishLoading()

    def _finishLoading(self):
        self.scrollArea.verticalScrollBar().setValue(0)
        self.mdiParent.lblStatusBarMessage.setText("")
        self.mdiParent.lblStatusBarMessage.setVisible(False)
        QApplication.restoreOverrideCursor()

    def threadFinished(self):
        self.threadsRemaining -= 1

    # ------------------------------------------------------------------
    # Row insertion
    # ------------------------------------------------------------------

    def insertAudioIntoTable(self, row, recordingData, audioMatchData, pixmap,
                             comboData, cascadeMode="date_first", ax_bbox=None,
                             allSightings=None):
        QApplication.processEvents()
        self.fillingCombos = True

        recordingLocation = audioMatchData.get("recordingLocation", "")
        recordingDate = audioMatchData.get("recordingDate", "")
        recordingTime = audioMatchData.get("recordingTime", "")
        recordingCommonName = audioMatchData.get("recordingCommonName", "")

        # ---- Column 0: spectrogram + scrubber ----
        visContainer = QWidget()
        visLayout = QVBoxLayout(visContainer)
        visLayout.setContentsMargins(0, 0, 0, 0)
        visLayout.setSpacing(2)

        spectroLabel = SpectrogramLabel()
        if pixmap and not pixmap.isNull():
            spectroLabel.setPixmap(pixmap, ax_bbox)
        self._spectroLabels[row] = spectroLabel
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

        self.gridAudio.addWidget(visContainer, row, 0)

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
        container = QWidget()
        container.setObjectName("container" + str(row))
        detailsLayout = QVBoxLayout(container)
        detailsLayout.setObjectName("layout" + str(row))
        detailsLayout.setAlignment(Qt.AlignTop)
        self.gridAudio.addWidget(container, row, 1)

        cboLocation = QComboBox()
        cboLocation.currentIndexChanged.connect(partial(self.cboLocationChanged, row))
        cboDate = QComboBox()
        cboDate.currentIndexChanged.connect(partial(self.cboDateChanged, row))
        cboTime = QComboBox()
        cboTime.currentIndexChanged.connect(partial(self.cboTimeChanged, row))
        cboCommonName = QComboBox()
        cboCommonName.currentIndexChanged.connect(partial(self.cboCommonNameChanged, row))
        cboRating = QComboBox()
        cboRating.addItems(["Not Rated", "1", "2", "3", "4", "5"])
        cboRating.currentIndexChanged.connect(partial(self.cboRatingChanged, row))

        for c in [cboLocation, cboDate, cboTime, cboCommonName, cboRating]:
            self.removeHighlight(c)

        if cascadeMode == "date_first":
            cboDate.addItems(comboData.get("allDates", []))
            if recordingDate:
                idx = cboDate.findText(recordingDate)
                if idx >= 0:
                    cboDate.setCurrentIndex(idx)

            cboLocation.addItems(comboData.get("locationsByDate", []))
            if recordingLocation:
                idx = cboLocation.findText(recordingLocation)
                if idx >= 0:
                    cboLocation.setCurrentIndex(idx)

            cboTime.addItems(comboData.get("timesByDateAndLocation", []))
            if recordingTime:
                idx = cboTime.findText(recordingTime)
                if idx >= 0:
                    cboTime.setCurrentIndex(idx)

            cboCommonName.addItem("-- Add a species --")
            cboCommonName.addItems(comboData.get("speciesByChecklist", []))
            cboCommonName.setCurrentIndex(0)

            if (not self.audioAlreadyInDb and
                    audioMatchData.get("dateMatchFound", False) and
                    audioMatchData.get("timeMatchFound", False) and
                    recordingLocation):
                for combo, match_text in (
                    (cboDate, recordingDate),
                    (cboLocation, recordingLocation),
                    (cboTime, recordingTime),
                ):
                    combo.setStyleSheet("QComboBox { color: #4CAF50; }")
        else:
            cboLocation.addItems(comboData.get("allLocations", []))
            if recordingLocation:
                idx = cboLocation.findText(recordingLocation)
                if idx >= 0:
                    cboLocation.setCurrentIndex(idx)

            cboDate.addItems(comboData.get("datesByLocation", []))
            if recordingDate:
                idx = cboDate.findText(recordingDate)
                if idx >= 0:
                    cboDate.setCurrentIndex(idx)

            cboTime.addItems(comboData.get("timesByLocationAndDate", []))
            if recordingTime:
                idx = cboTime.findText(recordingTime)
                if idx >= 0:
                    cboTime.setCurrentIndex(idx)

            cboCommonName.addItem("-- Add a species --")
            cboCommonName.addItems(comboData.get("speciesByChecklist", []))
            cboCommonName.setCurrentIndex(0)

            try:
                rating_idx = max(0, min(5, int(recordingData.get("rating", "0"))))
            except (ValueError, TypeError):
                rating_idx = 0
            cboRating.setCurrentIndex(rating_idx)

        cboLocation.setObjectName("cboLocation" + str(row))
        cboDate.setObjectName("cboDate" + str(row))
        cboTime.setObjectName("cboTime" + str(row))
        cboCommonName.setObjectName("cboCommonName" + str(row))
        cboRating.setObjectName("cboRating" + str(row))

        tagStrip = SpeciesTagStrip()
        tagStrip.setObjectName("tagStrip" + str(row))
        if allSightings:
            tagStrip.setSpeciesList([s["commonName"] for s in allSightings])
        elif recordingCommonName:
            tagStrip.setSpeciesList([recordingCommonName])
        tagStrip.speciesChanged.connect(partial(self.saveNewMetaData, row))

        # Header info labels
        lblFileName = QLabel("File: " + os.path.basename(recordingData["fileName"]))

        lblParsedDate = QLabel()
        parsedDate = recordingData.get("date", "")
        dateSource = recordingData.get("dateSource", "filename")
        if parsedDate and parsedDate != "Date unknown":
            if dateSource == "metadata":
                lblParsedDate.setText("Recording date (metadata): " + parsedDate)
            else:
                lblParsedDate.setText("Filename date: " + parsedDate)
        else:
            lblParsedDate.setText("No date found in filename or metadata.")
            lblParsedDate.setStyleSheet("color: orange;")

        lblMtime = QLabel()
        mtime = recordingData.get("mtime", "")
        if mtime:
            lblMtime.setText("File saved: " + mtime)

        lblDur = QLabel()
        dur = recordingData.get("duration", "")
        if dur:
            sr = recordingData.get("sampleRate", "")
            lblDur.setText(f"Duration: {dur}" + (f"  |  {sr}" if sr else ""))

        detailsLayout.addWidget(lblFileName)
        detailsLayout.addWidget(lblParsedDate)
        if mtime:
            detailsLayout.addWidget(lblMtime)
        if dur:
            detailsLayout.addWidget(lblDur)

        lblCboDate = QLabel("Date")
        _f = QFont(); _f.setBold(True); lblCboDate.setFont(_f)
        detailsLayout.addWidget(lblCboDate)
        detailsLayout.addWidget(cboDate)

        lblCboLocation = QLabel("Location")
        _f = QFont(); _f.setBold(True); lblCboLocation.setFont(_f)
        detailsLayout.addWidget(lblCboLocation)
        detailsLayout.addWidget(cboLocation)

        lblCboTime = QLabel("Time")
        _f = QFont(); _f.setBold(True); lblCboTime.setFont(_f)
        detailsLayout.addWidget(lblCboTime)
        detailsLayout.addWidget(cboTime)

        lblCboSpecies = QLabel("Species")
        _f = QFont(); _f.setBold(True); lblCboSpecies.setFont(_f)
        detailsLayout.addWidget(lblCboSpecies)
        detailsLayout.addWidget(cboCommonName)
        detailsLayout.addWidget(tagStrip)

        lblCboRating = QLabel("Rating")
        _f = QFont(); _f.setBold(True); lblCboRating.setFont(_f)
        detailsLayout.addWidget(lblCboRating)
        detailsLayout.addWidget(cboRating)

        btnReset = QPushButton("Reset")
        btnReset.clicked.connect(partial(self.btnResetClicked, row))
        detailsLayout.addWidget(btnReset)

        thisAudioMetaData = {}
        thisAudioMetaData["location"] = recordingLocation
        thisAudioMetaData["date"] = recordingDate
        thisAudioMetaData["time"] = cboTime.currentText()
        thisAudioMetaData["commonNames"] = tagStrip.getSpecies()
        thisAudioMetaData["origCommonNames"] = tagStrip.getSpecies()
        thisAudioMetaData["allSightings"] = allSightings or []
        thisAudioMetaData["recordingData"] = recordingData
        thisAudioMetaData["rating"] = recordingData.get("rating", "0")
        thisAudioMetaData["cascadeMode"] = cascadeMode

        self.metaDataByRow[row] = thisAudioMetaData
        self.saveNewMetaData(row)
        self.fillingCombos = False

    # ------------------------------------------------------------------
    # Combo cascade helpers  (mirror ManagePhotos pattern)
    # ------------------------------------------------------------------

    def _getRowWidgets(self, row):
        container = self.gridAudio.itemAtPosition(row, 1).widget()
        widgets = {}
        for w in container.children():
            name = w.objectName()
            if name.startswith("cboLocation"):
                widgets["location"] = w
            elif name.startswith("cboDate"):
                widgets["date"] = w
            elif name.startswith("cboTime"):
                widgets["time"] = w
            elif name.startswith("cboCommonName"):
                widgets["species"] = w
            elif name.startswith("cboRating"):
                widgets["rating"] = w
            elif name.startswith("tagStrip"):
                widgets["tagStrip"] = w
        return widgets

    def cboLocationChanged(self, row, _index=None):
        if self.fillingCombos:
            return
        self.fillingCombos = True
        w = self._getRowWidgets(row)
        cboLocation = w.get("location")
        if cboLocation:
            orig = self.metaDataByRow[row]["location"]
            if cboLocation.currentText() == orig:
                self.removeHighlight(cboLocation)
            else:
                self.highlightWidget(cboLocation)
        if self.metaDataByRow[row].get("cascadeMode") == "location_first":
            self._setCboDate(row)
        self._setCboTime(row)
        self._setCboCommonName(row)
        self.saveNewMetaData(row)
        self.fillingCombos = False

    def cboDateChanged(self, row, _index=None):
        if self.fillingCombos:
            return
        self.fillingCombos = True
        w = self._getRowWidgets(row)
        cboDate = w.get("date")
        if cboDate:
            orig = self.metaDataByRow[row]["date"]
            if cboDate.currentText() == orig:
                self.removeHighlight(cboDate)
            else:
                self.highlightWidget(cboDate)
        if self.metaDataByRow[row].get("cascadeMode") == "date_first":
            self._setCboLocationByDate(row)
        self._setCboTime(row)
        self._setCboCommonName(row)
        self.saveNewMetaData(row)
        self.fillingCombos = False

    def cboTimeChanged(self, row, _index=None):
        if self.fillingCombos:
            return
        self.fillingCombos = True
        w = self._getRowWidgets(row)
        cboTime = w.get("time")
        if cboTime:
            orig = self.metaDataByRow[row]["time"]
            if cboTime.currentText() == orig:
                self.removeHighlight(cboTime)
            else:
                self.highlightWidget(cboTime)
        self._setCboCommonName(row)
        self.saveNewMetaData(row)
        self.fillingCombos = False

    def cboCommonNameChanged(self, row, _index=None):
        if self.fillingCombos:
            return
        w = self._getRowWidgets(row)
        cbo = w.get("species")
        tagStrip = w.get("tagStrip")
        if cbo and tagStrip:
            selected = cbo.currentText()
            if selected and selected != "-- Add a species --":
                tagStrip.addSpecies(selected)
                self.fillingCombos = True
                cbo.setCurrentIndex(0)
                self.fillingCombos = False
        self.saveNewMetaData(row)

    def cboRatingChanged(self, row, _index=None):
        if self.fillingCombos:
            return
        w = self._getRowWidgets(row)
        cbo = w.get("rating")
        if cbo:
            orig = self.metaDataByRow[row]["rating"]
            if cbo.currentText() == orig:
                self.removeHighlight(cbo)
            else:
                self.highlightWidget(cbo)
        self.saveNewMetaData(row)

    def _setCboDate(self, row):
        w = self._getRowWidgets(row)
        cboLocation = w.get("location")
        cboDate = w.get("date")
        if not cboDate or not cboLocation:
            return
        orig = self.metaDataByRow[row]["date"]
        current = cboDate.currentText()
        f = code_Filter.Filter()
        f.setLocationName(cboLocation.currentText())
        f.setLocationType("Location")
        dates = self.mdiParent.db.GetDates(f)
        cboDate.clear()
        cboDate.addItems(dates)
        idx = cboDate.findText(current)
        if idx >= 0:
            cboDate.setCurrentIndex(idx)
        else:
            idx = cboDate.findText(orig)
            if idx >= 0:
                cboDate.setCurrentIndex(idx)
        if cboDate.currentText() == orig:
            self.removeHighlight(cboDate)
        else:
            self.highlightWidget(cboDate)

    def _setCboLocationByDate(self, row):
        w = self._getRowWidgets(row)
        cboDate = w.get("date")
        cboLocation = w.get("location")
        if not cboDate or not cboLocation:
            return
        orig = self.metaDataByRow[row]["location"]
        current = cboLocation.currentText()
        f = code_Filter.Filter()
        f.setStartDate(cboDate.currentText())
        f.setEndDate(cboDate.currentText())
        locations = self.mdiParent.db.GetLocations(f)
        cboLocation.clear()
        cboLocation.addItems(locations)
        idx = cboLocation.findText(current)
        if idx >= 0:
            cboLocation.setCurrentIndex(idx)
        if cboLocation.currentText() == orig:
            self.removeHighlight(cboLocation)
        else:
            self.highlightWidget(cboLocation)

    def _setCboTime(self, row):
        w = self._getRowWidgets(row)
        cboLocation = w.get("location")
        cboDate = w.get("date")
        cboTime = w.get("time")
        if not all([cboLocation, cboDate, cboTime]):
            return
        orig = self.metaDataByRow[row]["time"]
        current = cboTime.currentText()
        f = code_Filter.Filter()
        f.setLocationName(cboLocation.currentText())
        f.setLocationType("Location")
        f.setStartDate(cboDate.currentText())
        f.setEndDate(cboDate.currentText())
        times = self.mdiParent.db.GetStartTimes(f)
        cboTime.clear()
        cboTime.addItems(times)
        idx = cboTime.findText(current)
        if idx >= 0:
            cboTime.setCurrentIndex(idx)
        if cboTime.currentText() == orig:
            self.removeHighlight(cboTime)
        else:
            self.highlightWidget(cboTime)

    def _setCboCommonName(self, row):
        w = self._getRowWidgets(row)
        cboLocation = w.get("location")
        cboDate = w.get("date")
        cboTime = w.get("time")
        cboCommonName = w.get("species")
        if not all([cboLocation, cboDate, cboTime, cboCommonName]):
            return
        f = code_Filter.Filter()
        f.setLocationName(cboLocation.currentText())
        f.setLocationType("Location")
        f.setStartDate(cboDate.currentText())
        f.setEndDate(cboDate.currentText())
        f.setTime(cboTime.currentText())
        names = self.mdiParent.db.GetSpecies(f)
        cboCommonName.clear()
        cboCommonName.addItem("-- Add a species --")
        cboCommonName.addItems(names)
        cboCommonName.setCurrentIndex(0)

    def saveNewMetaData(self, row):
        w = self._getRowWidgets(row)
        if "location" in w:
            self.metaDataByRow[row]["newLocation"] = w["location"].currentText()
        if "date" in w:
            self.metaDataByRow[row]["newDate"] = w["date"].currentText()
        if "time" in w:
            self.metaDataByRow[row]["newTime"] = w["time"].currentText()
        if "tagStrip" in w:
            self.metaDataByRow[row]["newCommonNames"] = w["tagStrip"].getSpecies()
        if "rating" in w:
            self.metaDataByRow[row]["newRating"] = str(w["rating"].currentIndex())

    def btnResetClicked(self, row):
        self.fillingCombos = True
        w = self._getRowWidgets(row)
        meta = self.metaDataByRow[row]

        origLocation = meta["location"]
        origDate = meta["date"]
        origTime = meta["time"]
        origCommonNames = meta["origCommonNames"]
        origRating = meta["rating"]

        cboLocation = w.get("location")
        cboDate = w.get("date")
        cboTime = w.get("time")
        cboCommonName = w.get("species")
        cboRating = w.get("rating")
        tagStrip = w.get("tagStrip")

        if cboLocation:
            idx = cboLocation.findText(origLocation)
            if idx >= 0:
                cboLocation.setCurrentIndex(idx)

        if cboDate:
            f = code_Filter.Filter()
            f.setLocationName(origLocation)
            f.setLocationType("Location")
            dates = self.mdiParent.db.GetDates(f)
            cboDate.clear()
            cboDate.addItems(dates)
            idx = cboDate.findText(origDate)
            if idx >= 0:
                cboDate.setCurrentIndex(idx)

        if cboTime:
            f = code_Filter.Filter()
            f.setLocationName(origLocation)
            f.setLocationType("Location")
            f.setStartDate(origDate)
            f.setEndDate(origDate)
            times = self.mdiParent.db.GetStartTimes(f)
            cboTime.clear()
            cboTime.addItems(times)
            idx = cboTime.findText(origTime)
            if idx >= 0:
                cboTime.setCurrentIndex(idx)

        if cboCommonName:
            f = code_Filter.Filter()
            f.setLocationName(origLocation)
            f.setLocationType("Location")
            f.setStartDate(origDate)
            f.setEndDate(origDate)
            f.setTime(origTime)
            names = self.mdiParent.db.GetSpecies(f)
            cboCommonName.clear()
            cboCommonName.addItem("-- Add a species --")
            cboCommonName.addItems(names)
            cboCommonName.setCurrentIndex(0)

        if tagStrip:
            tagStrip.setSpeciesList(origCommonNames)

        if cboRating:
            try:
                cboRating.setCurrentIndex(int(origRating))
            except (ValueError, TypeError):
                cboRating.setCurrentIndex(0)

        for cbo in [cboLocation, cboDate, cboTime, cboRating]:
            if cbo:
                self.removeHighlight(cbo)

        self.fillingCombos = False

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

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

        for r in range(self.gridAudio.rowCount()):
            if r not in self.metaDataByRow:
                continue
            meta = self.metaDataByRow[r]

            if self.audioAlreadyInDb:
                old_species = [s["commonName"] for s in meta.get("allSightings", [])]
                new_species = meta.get("newCommonNames", [])
                changed = (
                    meta["location"] != meta["newLocation"] or
                    meta["date"] != meta["newDate"] or
                    meta["time"] != meta["newTime"] or
                    set(old_species) != set(new_species) or
                    meta["rating"] != meta["newRating"]
                )
                if changed:
                    audio_filename = meta["recordingData"]["fileName"]
                    self.mdiParent.db.removeRecordingFileFromDatabase(audio_filename)
                    try:
                        self.mdiParent.db.appendRecordingDeletionToJsonl(audio_filename)
                    except IOError:
                        pass
                    meta["recordingData"]["rating"] = meta["newRating"]
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
