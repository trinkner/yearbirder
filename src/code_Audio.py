# Centralised audio logic for Yearbirder's recording features.
#
# This is a leaf module: it imports only numpy / wave / matplotlib(Agg) / Qt and
# never imports the windows or the cache, so the dependency graph points the
# right way (ManageRecordings, RecordingEnlargement, Recordings and the thumbnail
# cache all import *from here*).
#
# It owns three concerns that previously lived — and drifted — across several
# modules:
#   1. WAV decoding (float-mono for rendering; PCM16 for playback).  A single
#      source of truth here is what prevents bugs like the 24-bit spectrograms
#      that rendered as noise because two of three copies lacked a 24-bit branch.
#   2. Spectrogram thumbnail rendering (decoded audio -> QImage).
#   3. The low-latency playback engine (PcmAudioPlayer over a persistent
#      QAudioSink).
#
# WAV *metadata* (date/time) reading deliberately stays in code_DataBase: it is
# pure-python, used by the data layer, and keeping it out of here avoids dragging
# QtMultimedia into the database module.

import math

import numpy as np
import soundfile as sf
import matplotlib.mlab as mlab

# High-quality sample-rate conversion (libsoxr).  Guarded so a missing wheel can
# never break playback — the decoder falls back to linear interpolation.
try:
    import soxr
    _HAVE_SOXR = True
except Exception:
    _HAVE_SOXR = False

from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont
from PySide6.QtCore import Signal, QObject, QIODevice, Qt, QRectF
from PySide6.QtMultimedia import (
    QMediaPlayer, QAudioFormat, QAudioSink, QMediaDevices,
)


# ---------------------------------------------------------------------------
# WAV decoding  (the single source of truth for sample-format handling)
# ---------------------------------------------------------------------------

def decode_wav_float_mono(wav_path):
    """Read an audio file into a float32 mono numpy array.

    Uses libsndfile (via ``soundfile``), so it handles WAV PCM 8/16/24/32-bit,
    32-/64-bit float and WAVE_FORMAT_EXTENSIBLE, plus FLAC / AIFF / OGG and
    RF64/BWF — well beyond Python's built-in ``wave`` module.  Multi-channel
    files are downmixed by taking the first channel (matches prior behaviour, so
    cached spectrograms stay consistent).  Note: 32-bit-float files may legally
    carry sample values above 1.0; that's fine for the spectrogram, which works
    in relative dB.

    Returns ``(data, sample_rate, n_frames)`` or ``(None, 0, 0)`` on error.
    """
    try:
        frames, fs = sf.read(wav_path, dtype="float32", always_2d=True)
    except Exception:
        return None, 0, 0
    if frames.shape[0] == 0:
        return None, fs, 0
    data = np.ascontiguousarray(frames[:, 0])   # first channel
    return data, fs, frames.shape[0]


def decode_wav_pcm(wav_path, out_fmt="int16", normalize=True,
                   target_fs=None, target_channels=None):
    """Decode an audio file to interleaved little-endian PCM bytes.

    ``out_fmt`` selects the sample format of the returned bytes:
        ``"int16"``   – signed 16-bit            (2 bytes/sample)
        ``"float32"`` – 32-bit IEEE float [-1,1]  (4 bytes/sample)

    Returns ``(bytes, sample_rate, channels, duration_ms)`` or ``None`` on
    failure.  When ``target_fs`` / ``target_channels`` are given the audio is
    resampled (libsoxr — high quality — if available, else linear interpolation)
    and re-channelled to that fixed output format, so a single QAudioSink can be
    reused across files of differing native formats (no costly per-file sink
    re-create).  ``duration_ms`` is always the true wall-clock length,
    independent of resampling.

    Uses libsndfile (via ``soundfile``), so it supports the same broad set of
    formats as :func:`decode_wav_float_mono` (incl. 32-bit float, FLAC, AIFF).
    The peak>1.0 scale-down is always applied (float output also clips at the
    DAC, and a resampler can overshoot ±1.0); the quiet-boost is gated behind
    ``normalize``.
    """
    try:
        # soundfile returns float samples in (frames, channels) order.
        frames, fs = sf.read(wav_path, dtype="float32", always_2d=True)
    except Exception:
        return None

    n_frames, n_ch = frames.shape
    dur_ms = int(round(n_frames / fs * 1000)) if fs else 0

    out_ch = target_channels if target_channels else n_ch
    out_fs = target_fs if target_fs else fs

    if out_ch != n_ch:
        if out_ch == 1:
            frames = frames.mean(axis=1, keepdims=True)
        else:                                   # up/replicate to out_ch
            cols = [frames[:, min(c, n_ch - 1)] for c in range(out_ch)]
            frames = np.column_stack(cols)

    if out_fs != fs and frames.shape[0] > 1:
        if _HAVE_SOXR:
            # Single high-quality hop straight to the output rate.
            frames = soxr.resample(frames, fs, out_fs, quality="HQ")
        else:
            n_old = frames.shape[0]
            n_new = max(1, int(round(n_old * out_fs / fs)))
            old_x = np.arange(n_old, dtype=np.float64)
            new_x = np.linspace(0.0, n_old - 1, n_new)
            frames = np.column_stack(
                [np.interp(new_x, old_x, frames[:, c]) for c in range(frames.shape[1])])

    data = np.ascontiguousarray(frames).reshape(-1)

    if len(data) > 0:
        peak = float(np.max(np.abs(data)))
        if peak > 1.0:                      # headroom / resampler overshoot → avoid clipping
            data = data / peak
        elif normalize and 0.0 < peak < 0.1:   # very quiet → boost
            data = data * (0.9 / peak)

    data = np.clip(data, -1.0, 1.0)
    if out_fmt == "float32":
        pcm = data.astype('<f4')
    else:
        pcm = (data * 32767.0).astype('<i2')
    return pcm.tobytes(), out_fs, out_ch, dur_ms


def decode_wav_pcm16(wav_path, normalize=True, target_fs=None, target_channels=None):
    """Back-compat wrapper: decode to interleaved little-endian 16-bit PCM bytes."""
    return decode_wav_pcm(wav_path, "int16", normalize=normalize,
                          target_fs=target_fs, target_channels=target_channels)


# ---------------------------------------------------------------------------
# Spectrogram thumbnail rendering
# ---------------------------------------------------------------------------

# Fixed data rectangle (x0, x1, y0, y1, figure-fraction, origin bottom-left) for
# the thumbnail — the spectrogram is drawn into this rect, with axes around it.
# Constant, so the cached image needs no per-file bbox metadata.
SPECTRO_AX_BBOX = (0.13, 0.98, 0.15, 0.95)

_AXIS_COLOR  = "#444444"
_SPINE_COLOR = "#aaaaaa"


def _nice_ticks(lo, hi, target=6):
    """Pleasant 1/2/2.5/5/10 tick positions across [lo, hi] (≈ matplotlib's)."""
    if hi <= lo:
        return [lo]
    raw = (hi - lo) / max(1, target)
    mag = 10.0 ** math.floor(math.log10(raw))
    step = 10 * mag
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            step = m * mag
            break
    ticks, v = [], math.ceil(lo / step) * step
    while v <= hi + step * 1e-6:
        ticks.append(round(v, 6))
        v += step
    return ticks


def _fmt_tick(v):
    if abs(v - round(v)) < 1e-6:
        return str(int(round(v)))
    return ("%.1f" % v).rstrip("0").rstrip(".")


def _spectrogram_grayscale_image(data, fs, nfft, noverlap,
                                 freq_min, freq_max, contrast_pct):
    """Grayscale (Format_Grayscale8) spectrogram QImage at the STFT's native
    resolution, frequency-cropped to [freq_min, freq_max] and oriented for
    display (high frequency at the top).

    Uses matplotlib.mlab.specgram so the spectrogram *content* is byte-identical
    to the old ax.specgram path; the dB scaling, fixed-80 dB contrast window and
    gray_r colour mapping are reproduced exactly.  No Figure/Axes/Agg pipeline,
    so it is far cheaper than rendering a large matplotlib image.

    Returns a QImage, or None on error / too-short input.
    """
    if data is None or len(data) < nfft:
        return None
    try:
        with np.errstate(divide='ignore', invalid='ignore'):
            spec, freqs, _t = mlab.specgram(data, NFFT=nfft, Fs=fs, noverlap=noverlap)
    except Exception:
        return None
    with np.errstate(divide='ignore', invalid='ignore'):
        db = 10.0 * np.log10(np.maximum(spec, 1e-12))
    # db_hi anchors the contrast window; compute it over the FULL spectrum (as the
    # old ax.specgram path did) — frequency cropping is a view operation only, so
    # cropping first would change the percentile and shift the brightness.
    db_hi = float(np.percentile(db, 99.5))
    vmin  = db_hi - 80.0 * (1.0 - contrast_pct / 100.0)
    rng   = db_hi - vmin if db_hi > vmin else 1.0
    fmax = min(freq_max if freq_max else fs // 2, fs // 2)
    mask = (freqs >= freq_min) & (freqs <= fmax)
    db = db[mask, :]
    if db.size == 0:
        return None
    norm  = np.clip((db - vmin) / rng, 0.0, 1.0)
    gray  = (255.0 * (1.0 - norm)).astype(np.uint8)   # gray_r: signal dark on white
    gray  = np.ascontiguousarray(gray[::-1])           # flip: high frequency at top
    h, w = gray.shape
    return QImage(gray.data, w, h, w, QImage.Format_Grayscale8).copy()


def render_ribbon_qimage(data, fs, n_frames, width, height, contrast_pct=0):
    """Render the wide enlargement 'ribbon' spectrogram as a grayscale QImage of
    exactly (width x height).  The ribbon is axis-less (data fills the image), so
    there is nothing matplotlib gives us here — this skips the Figure/Axes/Agg
    pipeline entirely and is ~4x faster while producing a visually identical
    result.  NFFT is chosen by pixels-per-second to match the previous renderer.
    Returns a QImage or None.
    """
    if data is None or not fs or len(data) < 64:
        return None
    duration = n_frames / fs if fs else 0
    px_per_sec = width / max(duration, 0.001)
    if px_per_sec > 600:
        nfft = 2048
    elif px_per_sec > 200:
        nfft = 4096
    else:
        nfft = 8192
    noverlap = nfft * 3 // 4
    img = _spectrogram_grayscale_image(
        data, fs, nfft, noverlap, freq_min=0, freq_max=fs // 2, contrast_pct=contrast_pct)
    if img is None:
        return None
    return img.scaled(width, height,
                      Qt.AspectRatioMode.IgnoreAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)


def render_spectrogram_qimage(wav_path, max_freq=10000):
    """Render the browser/manage thumbnail spectrogram for wav_path.

    Returns (QImage, duration_secs, sample_rate, ax_bbox) where ax_bbox is the
    constant SPECTRO_AX_BBOX.  Returns (None, 0, 0, None) on error.  The
    spectrogram itself is produced by the lightweight numpy renderer and composed
    into a 500x290 image with light Hz/sec axes; QImage-only, so it is safe to
    call off the GUI thread.
    """
    data, fs, n_frames = decode_wav_float_mono(wav_path)
    if data is None:
        return None, 0, 0, None
    duration = n_frames / fs if fs else 0
    if len(data) < 64:
        return None, duration, fs, None

    # Match the previous thumbnail's STFT density: NFFT 512 with a hop widened on
    # long clips so the STFT yields ~900 columns (the thumbnail is ~500 px wide).
    NFFT = 512
    hop = max(128, (len(data) - NFFT) // 900)
    noverlap = max(0, min(NFFT - hop, NFFT - 1))
    fmax = min(max_freq, fs // 2)

    # 50 % contrast — matches the old im.set_clim(db_hi - 80*0.50, db_hi).
    spec_img = _spectrogram_grayscale_image(
        data, fs, NFFT, noverlap, freq_min=0, freq_max=fmax, contrast_pct=50)
    if spec_img is None:
        return None, duration, fs, None

    W, H = 500, 290
    x0, x1, y0f, y1f = SPECTRO_AX_BBOX                 # figure-fraction, bottom-origin
    L, R = x0 * W, x1 * W
    T, B = (1.0 - y1f) * H, (1.0 - y0f) * H            # top-origin pixels
    rect = QRectF(L, T, R - L, B - T)

    img = QImage(W, H, QImage.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.drawImage(rect, spec_img.scaled(
        max(1, int(rect.width())), max(1, int(rect.height())),
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation))

    p.setPen(QPen(QColor(_SPINE_COLOR), 1))
    p.drawRect(rect)

    p.setFont(QFont("", 7))
    tick_pen = QPen(QColor(_AXIS_COLOR), 1)
    aR = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    aHT = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
    aC = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter

    # ~1 tick per 45 px on each axis, matching matplotlib's auto density.
    ty = max(3, round((B - T) / 45.0))
    tx = max(3, round((R - L) / 45.0))

    # Y axis — Hz
    for hz in _nice_ticks(0, fmax, ty):
        if hz > fmax:
            continue
        y = B - (hz / fmax) * (B - T) if fmax else B
        p.setPen(tick_pen)
        p.drawLine(int(L - 3), int(y), int(L), int(y))
        p.drawText(QRectF(0, y - 7, L - 5, 14), aR, _fmt_tick(hz))

    # X axis — sec
    for s in _nice_ticks(0, duration, tx):
        if s > duration:
            continue
        x = L + (s / duration) * (R - L) if duration else L
        p.setPen(tick_pen)
        p.drawLine(int(x), int(B), int(x), int(B + 3))
        p.drawText(QRectF(x - 20, B + 4, 40, 12), aHT, _fmt_tick(s))

    # Axis titles
    p.setPen(tick_pen)
    p.drawText(QRectF(L, B + 15, R - L, 12), aHT, "sec")
    p.save()
    p.translate(9, (T + B) / 2.0)
    p.rotate(-90)
    p.drawText(QRectF(-30, -8, 60, 14), aC, "Hz")
    p.restore()
    p.end()

    return img, duration, fs, SPECTRO_AX_BBOX


def build_spectrogram_pixmap(wav_path, max_freq=10000):
    """QPixmap wrapper around render_spectrogram_qimage for GUI-thread/QThread
    callers that display the result.  Returns (QPixmap, dur, fs, ax_bbox)."""
    img, duration, fs, ax_bbox = render_spectrogram_qimage(wav_path, max_freq)
    if img is None or img.isNull():
        return None, duration, fs, ax_bbox
    return QPixmap.fromImage(img), duration, fs, ax_bbox


# ---------------------------------------------------------------------------
# Playback engine
# ---------------------------------------------------------------------------

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
    fixed-format, every file is decoded/resampled to that one output format.

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
        self._durationMs  = 0
        self._hasMedia    = False
        self._state       = QMediaPlayer.PlaybackState.StoppedState
        self._currentPath = None

        self._buildSink()

        # Rebuild the sink only when the output device itself changes (rare and
        # user-initiated — switching headphones, changing the device's rate).
        # A one-off spin-up there is acceptable; file-to-file switches never
        # rebuild, preserving the zero-latency guarantee.
        self._mediaDevices = QMediaDevices(self)
        self._mediaDevices.audioOutputsChanged.connect(self._onDeviceChanged)

    def _buildSink(self):
        """Create the persistent device + QAudioSink for the current default
        output.  Output format is 32-bit float at the device's preferred sample
        rate (so the OS does no further rate conversion); falls back to Int16 if
        the device doesn't support float.  Starts the sink silent so Core Audio
        is warm before the first Play."""
        dev  = QMediaDevices.defaultAudioOutput()
        self._deviceId = dev.id()
        pref = dev.preferredFormat()
        self._outFs = pref.sampleRate() if pref.sampleRate() > 0 else 48000

        fmt = QAudioFormat()
        fmt.setSampleRate(self._outFs)
        fmt.setChannelCount(self._OUT_CH)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
        if dev.isFormatSupported(fmt):
            self._sampleFmt, self._bytesPerSample = "float32", 4
        else:                                   # universally-accepted fallback
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            self._sampleFmt, self._bytesPerSample = "int16", 2
        self._bytesPerFrame = self._bytesPerSample * self._OUT_CH

        self._device = _PcmStreamDevice(self)
        self._device.loadData(b'', self._bytesPerFrame)
        self._device.finished.connect(self._onFinished)
        self._device.open(QIODevice.OpenModeFlag.ReadOnly)

        self._sink = QAudioSink(dev, fmt, self)
        buf = int(self._outFs * self._bytesPerFrame * self._BUFFER_SECONDS)
        if buf > 0:
            self._sink.setBufferSize(buf)
        self._sink.start(self._device)

    # ── source ──────────────────────────────────────────────────────────
    def setSourceWav(self, wav_path):
        self._currentPath = wav_path
        decoded = decode_wav_pcm(
            wav_path, out_fmt=self._sampleFmt,
            target_fs=self._outFs, target_channels=self._OUT_CH)
        if not decoded:
            self._currentPath = None
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

    def _onDeviceChanged(self):
        """Default output device (or its preferred rate) changed: rebuild the
        sink for the new device and reload the current clip in the new format,
        preserving playback position and state."""
        dev  = QMediaDevices.defaultAudioOutput()
        pref = dev.preferredFormat()
        new_fs = pref.sampleRate() if pref.sampleRate() > 0 else 48000
        if dev.id() == self._deviceId and new_fs == self._outFs:
            return                          # default output effectively unchanged

        pos        = self.position()
        wasPlaying = (self._state == QMediaPlayer.PlaybackState.PlayingState)
        path       = self._currentPath

        try:
            self._sink.stop()
        except Exception:
            pass
        self._sink.deleteLater()
        self._device.deleteLater()

        self._buildSink()
        if path:
            if self.setSourceWav(path):     # re-decodes to the new output format
                self.setPosition(pos)
                if wasPlaying:
                    self.play()

    def _onFinished(self):
        # Reached the end of the clip while playing (queued from the pull thread).
        self._device.setPlaying(False)
        self._device.seekBytes(0)
        self._setState(QMediaPlayer.PlaybackState.StoppedState)
        self.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.EndOfMedia)
