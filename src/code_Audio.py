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
from code_Stylesheet import YBFont

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
from PySide6.QtCore import Signal, QObject, QIODevice, QTimer, Qt, QRectF
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
# Rendered thumbnail size — kept equal to code_ThumbnailCache.THUMB_DISPLAY_SIZE
# (the on-screen size in the recordings views) so the cached image is shown 1:1
# with no scaling at paint time.  This is a leaf module, so the value is
# duplicated here rather than imported from the cache; change both together
# (and bump code_ThumbnailCache.SPECTRO_THUMB_VARIANT).
SPECTRO_THUMB_W, SPECTRO_THUMB_H = 333, 220

# Margins sized for the axis labels at the size above.
SPECTRO_AX_BBOX = (0.13, 0.98, 0.14, 0.95)
_AXIS_FONT_PT = 9    # readable at the 333x220 display size without dominating it

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


def render_spectrogram_qimage(wav_path, max_freq=10000, draw_axis_text=True):
    """Render the browser/manage thumbnail spectrogram for wav_path.

    Returns (QImage, duration_secs, sample_rate, ax_bbox) where ax_bbox is the
    constant SPECTRO_AX_BBOX.  Returns (None, 0, 0, None) on error.  The
    spectrogram itself is produced by the lightweight numpy renderer and composed
    into a SPECTRO_THUMB_W x SPECTRO_THUMB_H image (the exact display size).

    draw_axis_text: when True the kHz/sec tick marks and labels are drawn here.
    The label drawing uses QFont/drawText, which touches macOS's CoreText font
    engine — NOT safe to do off the GUI thread (concurrent use corrupts glyph
    metrics app-wide, producing "stretched" text in windows opened afterwards).
    Off-thread callers (the browser/manage worker threads) MUST pass False and
    call paint_spectro_axes() on the result from the GUI thread instead.  The
    spectrogram + spine drawn here use no fonts, so they are safe off-thread.
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

    W, H = SPECTRO_THUMB_W, SPECTRO_THUMB_H
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

    if draw_axis_text:
        _draw_spectro_axes(p, L, R, T, B, fmax, duration)
    p.end()

    return img, duration, fs, SPECTRO_AX_BBOX


def _draw_spectro_axes(p, L, R, T, B, fmax, duration):
    """Draw the kHz/sec tick marks and labels onto an open QPainter.

    Uses QFont/drawText — GUI-thread only (see render_spectrogram_qimage).
    Label boxes and tick density derive from the font metrics, so the axis
    font size can change without re-tuning pixel offsets."""
    p.setFont(QFont(YBFont, _AXIS_FONT_PT))
    fm = p.fontMetrics()
    lh = fm.height()                              # one label line
    xw = fm.horizontalAdvance("00.0") + 10        # generous x-label box
    tick_pen = QPen(QColor(_AXIS_COLOR), 1)
    aR = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    aHT = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
    aC = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter

    # Tick density scales with the label size so labels never collide.
    ty = max(2, round((B - T) / (lh * 2.0)))
    tx = max(2, round((R - L) / (xw * 1.6)))

    # Y axis — kHz (ticks computed in Hz, labelled in kHz)
    for hz in _nice_ticks(0, fmax, ty):
        if hz > fmax:
            continue
        y = B - (hz / fmax) * (B - T) if fmax else B
        p.setPen(tick_pen)
        p.drawLine(int(L - 3), int(y), int(L), int(y))
        p.drawText(QRectF(0, y - lh / 2.0, L - 5, lh), aR, _fmt_tick(hz / 1000.0))

    # X axis — sec
    for s in _nice_ticks(0, duration, tx):
        if s > duration:
            continue
        x = L + (s / duration) * (R - L) if duration else L
        p.setPen(tick_pen)
        p.drawLine(int(x), int(B), int(x), int(B + 3))
        p.drawText(QRectF(x - xw / 2.0, B + 4, xw, lh), aHT, _fmt_tick(s))

    # Axis titles
    p.setPen(tick_pen)
    p.drawText(QRectF(L, B + 4 + lh, R - L, lh), aHT, "sec")
    p.save()
    p.translate(lh * 0.75, (T + B) / 2.0)
    p.rotate(-90)
    p.drawText(QRectF(-40, -lh / 2.0, 80, lh), aC, "kHz")
    p.restore()


def paint_spectro_axes(paint_device, duration, fs, max_freq=10000):
    """GUI-thread composite: draw the kHz/sec axes onto an already-rendered
    thumbnail spectrogram (QPixmap or QImage) that was produced off-thread with
    draw_axis_text=False.  MUST run on the GUI thread — see render_spectrogram_qimage.
    """
    W, H = paint_device.width(), paint_device.height()
    x0, x1, y0f, y1f = SPECTRO_AX_BBOX
    L, R = x0 * W, x1 * W
    T, B = (1.0 - y1f) * H, (1.0 - y0f) * H
    fmax = min(max_freq, fs // 2) if fs else 0
    p = QPainter(paint_device)
    _draw_spectro_axes(p, L, R, T, B, fmax, duration)
    p.end()


# NOTE: there is deliberately NO QPixmap wrapper around render_spectrogram_qimage.
# QPixmap creation/destruction is a GUI-thread-only operation (concurrent use
# corrupts macOS's shared native graphics state the same way off-thread
# QFont/drawText does — app-wide stretched text).  Worker threads must handle
# QImage only; the GUI-thread consumer converts with QPixmap.fromImage().


# ---------------------------------------------------------------------------
# Playback engine
# ---------------------------------------------------------------------------

def current_output_key_and_name():
    """(hex key, human name) of the system's current default audio output —
    the identity used by the per-device latency map."""
    dev = QMediaDevices.defaultAudioOutput()
    try:
        key = bytes(dev.id()).hex()
    except Exception:
        key = ""
    return key, dev.description()


class PcmAudioPlayer(QObject):
    """WAV player built on a push-mode QAudioSink kept continuously warm.

    Two things must both hold to play cleanly on macOS (incl. Bluetooth):

    * **No Python in the real-time path.**  A Python QIODevice ``readData`` used
      to *pull*-feed the sink takes the GIL on every fill and crackles under any
      GUI/thread contention.  Here the sink is opened in *push* mode: it reads
      its own buffer natively; we only *write* into it, decoupled from the
      real-time callback by the buffer.

    * **The device never idles.**  Starting an idle Core Audio / Bluetooth output
      unit costs ~1 s.  So the sink is started once and a small timer keeps it
      fed forever — real audio while playing, silence otherwise — so Play is
      instant (no per-play spin-up).

    The whole file is decoded (and resampled to the device's preferred format)
    up front into ``_pcm``.  The public API mirrors the subset of QMediaPlayer
    used by the Recordings browser and Enlargement window.
    """

    playbackStateChanged = Signal(object)
    mediaStatusChanged   = Signal(object)

    # Per-device output-latency compensation in ms, keyed by the hex of
    # QAudioDevice.id().  Bluetooth outputs add ~300-500ms downstream of
    # anything Qt can see; subtracting a calibrated per-device offset keeps
    # the displayed cursor aligned with what the user actually HEARS.
    # Class-level so every player instance (browser, manage, enlargement,
    # preferences calibration) shares one map; MainWindow loads it from the
    # preferences file at startup and the Preferences Playback tab edits it.
    _latencyByDevice = {}

    @classmethod
    def setLatencyMap(cls, mapping):
        cls._latencyByDevice = dict(mapping or {})

    def currentDeviceKey(self):
        try:
            return bytes(self._deviceId).hex()
        except Exception:
            return ""

    def outputLatencyMs(self):
        entry = self._latencyByDevice.get(self.currentDeviceKey())
        try:
            return int(entry.get("ms", 0)) if entry else 0
        except (TypeError, ValueError, AttributeError):
            return 0

    _OUT_CH = 2                       # fixed output channel count
    # Sink buffer / write-ahead runway.  Small enough that the leading latency
    # (buffered silence draining before the first real sample) is negligible,
    # large enough that the feed timer can miss a tick without starving.
    _BUFFER_SECONDS = 0.1
    _FEED_MS = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self._durationMs  = 0
        self._hasMedia    = False
        self._state       = QMediaPlayer.PlaybackState.StoppedState
        self._currentPath = None
        self._pcm         = b''       # decoded interleaved PCM for the current file
        self._posBytes    = 0         # next real-audio byte to write to the sink
        self._floorBytes  = 0         # reported position never dips below the last
                                      # play/seek point (avoids a backward hop while
                                      # the pre-buffered silence drains)
        self._playing     = False     # feeding real audio (vs keep-alive silence)
        self._io          = None      # the sink's push endpoint
        self._silence     = b'\x00' * 8192

        self._buildSink()

        # Keep the sink fed forever so the output device never idles.
        self._feedTimer = QTimer(self)
        self._feedTimer.setInterval(self._FEED_MS)
        self._feedTimer.timeout.connect(self._feed)
        self._feedTimer.start()

        self._mediaDevices = QMediaDevices(self)
        self._mediaDevices.audioOutputsChanged.connect(self._onDeviceChanged)

    def _buildSink(self):
        """Create and start (push mode) the QAudioSink for the default output.
        32-bit float at the device's preferred sample rate; Int16 fallback."""
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

        self._sink = QAudioSink(dev, fmt, self)
        buf = int(self._outFs * self._bytesPerFrame * self._BUFFER_SECONDS)
        if buf > 0:
            self._sink.setBufferSize(buf)
        self._io = self._sink.start()           # push mode: device stays active

    def _feed(self):
        """Top up the sink's buffer: real audio while playing, else silence."""
        io = self._io
        if io is None or self._bytesPerFrame <= 0:
            return
        free = self._sink.bytesFree()
        free -= free % self._bytesPerFrame
        while free > 0:
            if self._playing and self._posBytes >= len(self._pcm):
                self._finishPlayback()          # all audio written → stop feeding it
            if self._playing:
                chunk = self._pcm[self._posBytes:self._posBytes + free]
                self._posBytes += len(chunk)
            else:
                chunk = self._silence[:min(free, len(self._silence))]
            if not chunk:
                break
            io.write(chunk)
            free -= len(chunk)

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
        self._playing    = False            # sink keeps running silence; no restart
        self._pcm        = pcm
        self._durationMs = dur_ms
        self._hasMedia   = True
        self._posBytes   = 0
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
        if self._posBytes >= len(self._pcm):
            self._posBytes = 0                  # at end → from the start
        self._floorBytes = self._posBytes       # start exactly where the cursor is
        self._playing = True
        self._setState(QMediaPlayer.PlaybackState.PlayingState)

    def pause(self):
        if self._state == QMediaPlayer.PlaybackState.PlayingState:
            self._posBytes = self._playedBytes()   # resume from what's been heard
            self._playing = False
            self._setState(QMediaPlayer.PlaybackState.PausedState)

    def stop(self):
        self._playing = False
        self._posBytes = 0
        self._setState(QMediaPlayer.PlaybackState.StoppedState)

    def setPosition(self, ms):
        ms = max(0, min(int(ms), self._durationMs))
        self._posBytes = self._bytesForMs(ms)   # feed continues from here
        self._floorBytes = self._posBytes       # cursor holds here until sound catches up

    # ── queries ─────────────────────────────────────────────────────────
    def position(self):
        if self._state == QMediaPlayer.PlaybackState.PlayingState:
            pb = max(self._floorBytes, self._playedBytes())   # never hop backward
        else:
            pb = self._posBytes
        ms = int(pb / self._bytesPerFrame / self._outFs * 1000) \
            if self._bytesPerFrame and self._outFs else 0
        return max(0, min(ms, self._durationMs))

    def duration(self):
        return self._durationMs

    def playbackState(self):
        return self._state

    # ── internals ───────────────────────────────────────────────────────
    def _bytesForMs(self, ms):
        b = int(ms * self._outFs / 1000) * self._bytesPerFrame
        n = len(self._pcm)
        return max(0, min(b, n - (n % self._bytesPerFrame) if self._bytesPerFrame else n))

    def _playedBytes(self):
        """Real-audio bytes actually HEARD = written, minus what's still queued
        in the sink's buffer (which, during playback, is all real audio), minus
        the calibrated per-device output latency (Bluetooth transit that Qt
        cannot see).  Position, pause-resume and the cursor all derive from
        this, so compensation applies everywhere at once."""
        try:
            queued = max(0, self._sink.bufferSize() - self._sink.bytesFree())
        except Exception:
            queued = 0
        latBytes = int(self._outFs * self.outputLatencyMs() / 1000) * self._bytesPerFrame
        return max(0, min(self._posBytes - queued - latBytes, len(self._pcm)))

    def _finishPlayback(self):
        self._playing = False
        self._posBytes = 0
        self._setState(QMediaPlayer.PlaybackState.StoppedState)
        self.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.EndOfMedia)

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

        self._io = None
        self._playing = False
        try:
            self._sink.stop()
        except Exception:
            pass
        self._sink.deleteLater()

        self._buildSink()                   # new sink + push endpoint
        if path:
            if self.setSourceWav(path):     # re-decodes to the new output format
                self.setPosition(pos)
                if wasPlaying:
                    self.play()
