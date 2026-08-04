import form_RecordingEnlargement
from code_ManageRecordings import SpectrogramLabel   # UI widget stays in its module
from code_Audio import PcmAudioPlayer
import code_Audio
import code_Stylesheet
import code_ThumbnailCache
import code_NotesDialog

_DETAILS_PANE_WIDTH = 297   # must match _detailsPane.setFixedWidth() below
FADE_MS = 220               # Windows full-screen enter/exit opacity fade duration

# The compact overview and the wide ribbon both render label-less (data fills
# the whole figure), so their data rect is the full area — a constant, so the
# cached images need no per-file bbox metadata.
_OVERVIEW_AX_BBOX = (0.0, 1.0, 0.0, 1.0)
_RIBBON_AX_BBOX   = (0.0, 1.0, 0.0, 1.0)

# Cacheable open-state ribbons always render at the max-density cap width, so the
# cache key (variant) is deterministic without a live widget — the rebuild and a
# later window open always agree.  This is >= any dynamic _ribbonWidthPx(), so
# the cached ribbon is never blurrier than a live render.
_RIBBON_CACHE_WIDTH = 16000

# The cached ribbon is rendered at contrast 0 (widest dynamic range); the live
# Contrast slider applies a grayscale levels remap on top.  The "_c0" suffix in
# the variant invalidates older contrast-50 ribbons without a full cache bump.
_RIBBON_VARIANT = "{}_c0".format(_RIBBON_CACHE_WIDTH)

# Per-file auto-contrast: pick the initial Contrast so each file's noise floor
# clips to white regardless of its absolute level (some files render overly
# white, others overly gray at a fixed default).  The base grayscale maps noise
# floor -> white, signal -> black; setting the white point at the INK percentile
# keeps the darkest ~15% (signal) as ink and clips the brighter floor to white.
# Band-limited to the bird-relevant range so wind / handling rumble in the lowest
# octaves doesn't bias the floor estimate.
_AUTO_CONTRAST_BAND_LO_HZ = 500.0
_AUTO_CONTRAST_BAND_HI_HZ = 10000.0
_AUTO_CONTRAST_INK_PCTILE = 15
_AUTO_CONTRAST_SCALE = 0.75  # dial the full-strength default back 25% (less white)
_AUTO_CONTRAST_MIN = 18      # clamp so the auto value never goes flat or extreme
_AUTO_CONTRAST_MAX = 70
_AUTO_CONTRAST_DEFAULT_OFFSET = 10  # nudge the default slider position left (less contrast)


def build_ribbon_cache(wav_path):
    """Render and persist the deterministic ribbon base (grayscale PNG).

    Off-GUI-thread safe (QImage only) — used by the cache-rebuild workers.
    Renders the full clip at contrast 0 (widest range) and full frequency range;
    the enlargement applies the live contrast remap on display.  True on success.
    """
    data, fs, n_frames = _load_audio_data(wav_path)
    if data is None or not fs:
        return False
    # Lightweight numpy renderer (no matplotlib Figure/Axes/Agg) — the ribbon is
    # axis-less, so this is ~4x faster than the Agg path and visually identical.
    img = code_Audio.render_ribbon_qimage(
        data, fs, n_frames, _RIBBON_CACHE_WIDTH, 700, contrast_pct=0)
    if img is None or img.isNull():
        return False
    gray = img.convertToFormat(QImage.Format_Grayscale8)
    code_ThumbnailCache.store(wav_path, gray, "spectro_ribbon",
                              variant=_RIBBON_VARIANT)
    return True


def build_overview_cache(wav_path):
    """Render and persist the compact full-file overview strip (spectro_overview).

    Off-GUI-thread safe (QImage only) — mirrors build_ribbon_cache but for the
    small, label-less overview panel the enlargement shows above the ribbon.
    Renders the full clip at the full frequency range with the same parameters
    as the live _renderOverview path, so a later open is an exact cache hit.
    True on success.
    """
    data, fs, n_frames = _load_audio_data(wav_path)
    if data is None or not fs:
        return False
    duration = n_frames / fs if fs else 0.0
    img, _bbox = _render_slice_qimage(
        data, fs, 0.0, duration, compact=True, freq_max=fs // 2)
    if img is None or img.isNull():
        return False
    code_ThumbnailCache.store(wav_path, img, "spectro_overview")
    return True

import datetime
import gc
import math
import os
import time

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from PySide6.QtGui import QPixmap, QImage, QIcon, QPainter, QPen, QColor
from PySide6.QtCore import (Signal, Qt, QThread, QTimer, QUrl, QSize, QRect, QRectF,
                            QEvent, QPropertyAnimation, QEasingCurve)
from PySide6.QtWidgets import (
    QMdiSubWindow, QWidget, QLabel, QHBoxLayout, QVBoxLayout,
    QPushButton, QSlider, QApplication, QSizePolicy,
    QMenu, QFrame, QGroupBox, QMessageBox, QDialog,
)
from PySide6.QtMultimedia import QMediaPlayer  # enum constants reused by PcmAudioPlayer
from functools import partial


# Minimum visible window when zoomed all the way in (seconds).
_ZOOM_MIN_WINDOW = 1.0

# Zoom slider resolution: many fine steps mapped geometrically onto the zoom
# range so the slider feels continuous (like the Hz slider) rather than stepping
# through discrete power-of-two zoom levels.
_ZOOM_SLIDER_STEPS = 1000

# During the right-of-center catch-up phase, the viewport scrolls this many
# times faster than real-time so the cursor drifts left toward centre.
_CENTERING_OVERSPEED = 1.5


# ---------------------------------------------------------------------------
# Audio loading
# ---------------------------------------------------------------------------

def _load_audio_data(wav_path):
    """Read a WAV file into a float32 mono numpy array.

    Returns (data, sample_rate, n_frames) or (None, 0, 0) on error.  Delegates to
    code_Audio so WAV sample-format handling lives in exactly one place.
    """
    return code_Audio.decode_wav_float_mono(wav_path)


# ---------------------------------------------------------------------------
# Spectrogram slice renderer (thread-safe, Agg backend only)
# ---------------------------------------------------------------------------

def _render_slice_qimage(audio_data, fs, t_start, t_end,
                         freq_min=0, freq_max=None, compact=False, contrast_pct=20,
                         ribbon=False, fig_px_wide=1600):
    """Render the audio between t_start and t_end seconds as a spectrogram QImage.

    Returns (QImage, ax_bbox) or (None, None).  Uses only the Agg backend and
    QImage (no QPixmap), so it is safe to call off the GUI thread (e.g. the
    cache-rebuild workers).

    freq_min / freq_max: Hz range for the y-axis (None = use Nyquist cap).
    contrast_pct: lower percentile cutoff for colormap (0 = no clipping,
        higher = more aggressive noise-floor suppression).
    compact=True renders a short figure with no axis labels, suitable for
    the small overview panel.
    ribbon=True renders a wide no-label figure at fig_px_wide pixels wide
    covering the full file; the caller crops a viewport from this ribbon.
    Returns (QPixmap, ax_bbox) or (None, None).
    """
    if freq_max is None:
        freq_max = fs // 2

    s0 = max(0, int(t_start * fs))
    s1 = min(len(audio_data), int(t_end * fs))
    data = audio_data[s0:s1]

    if len(data) < 64:
        return None, None

    # NFFT: ribbon renders balance time vs frequency resolution.
    # Bird calls are 50–500 ms long, so time bins up to ~10 ms are fine.
    # Prioritise frequency resolution (larger NFFT) to reduce graininess.
    slice_dur = (s1 - s0) / max(fs, 1)
    if compact:
        nfft = 512
    elif ribbon:
        px_per_sec = fig_px_wide / max(slice_dur, 0.001)
        if px_per_sec > 600:
            nfft = 2048
        elif px_per_sec > 200:
            nfft = 4096
        else:
            nfft = 8192
    elif slice_dur < 2.0:
        nfft = 128
    elif slice_dur < 5.0:
        nfft = 256
    else:
        nfft = 512
    noverlap = nfft * 3 // 4

    if ribbon:
        figsize = (fig_px_wide / 100.0, 7.0)
    elif compact:
        figsize = (8.0, 1.0)
    else:
        figsize = (8.0, 3.5)
    fig = Figure(figsize=figsize, dpi=100)
    fig.patch.set_facecolor('white')
    ax = fig.add_subplot(111)

    try:
        with np.errstate(divide='ignore', invalid='ignore'):
            spectrum, _freqs, _bins, im = ax.specgram(
                data, Fs=fs, NFFT=nfft, noverlap=noverlap, cmap='gray_r', scale='dB')
    except Exception:
        return None, None

    # Fixed dynamic range: anchor vmax at the 99.5th-percentile dB value and
    # place vmin 80 dB below it.  A fixed 80 dB window means weak midrange
    # content (e.g. 2k-4kHz harmonics) is always visible rather than being
    # crushed by dominant low-frequency energy when global percentiles are used.
    # The contrast slider raises vmin by up to 64 dB to suppress the noise floor.
    db    = 10.0 * np.log10(np.maximum(spectrum, 1e-12))
    db_hi = float(np.percentile(db, 99.5))
    db_range = 80.0
    frac  = 0.0 if compact else contrast_pct / 100.0
    im.set_clim(db_hi - db_range * (1.0 - frac), db_hi)

    ax.set_ylim(freq_min, min(freq_max, fs // 2))
    ax.set_facecolor('white')

    if compact or ribbon:
        ax.tick_params(left=False, bottom=False,
                       labelleft=False, labelbottom=False)
        for sp in ax.spines.values():
            sp.set_visible(False)
        fig.tight_layout(pad=0.0)
    else:
        ax.tick_params(colors='#444444', labelsize=7)
        ax.set_ylabel('Hz', color='#444444', fontsize=7)
        ax.set_xlabel('sec', color='#444444', fontsize=7)
        for sp in ax.spines.values():
            sp.set_edgecolor('#aaaaaa')
        fig.tight_layout(pad=0.4)

    canvas = FigureCanvasAgg(fig)
    canvas.draw()

    pos = ax.get_position()
    ax_bbox = (pos.x0, pos.x1, pos.y0, pos.y1)

    # Build the QImage straight from the Agg RGBA buffer — avoids a PNG
    # encode/decode round-trip that dominated render time on the large ribbon
    # (~1.3-1.7 s for a 16000x700 image).  copy() is required: the buffer is
    # released when the figure/canvas is garbage-collected.
    w_px, h_px = canvas.get_width_height()
    img = QImage(canvas.buffer_rgba(), w_px, h_px, QImage.Format_RGBA8888)
    return img.copy(), ax_bbox


# ---------------------------------------------------------------------------
# Background render thread
# ---------------------------------------------------------------------------

class _RenderThread(QThread):
    """Renders one spectrogram slice in a background thread.

    The caller supplies a cancel token: a one-element list [False].
    Setting token[0] = True before the render completes discards the result.

    Emits a QImage, never a QPixmap: QPixmap creation/destruction is a
    GUI-thread-only operation (off-thread use corrupts macOS's shared native
    graphics state — app-wide stretched text, same failure mode as off-thread
    QFont/drawText).  The sigDone slot converts on the GUI thread if needed.
    """

    sigDone = Signal(object, object)    # QImage, ax_bbox (tuple or None)

    def __init__(self, audio_data, fs, t_start, t_end, token,
                 compact=False, freq_min=0, freq_max=None, contrast_pct=20,
                 ribbon=False, fig_px_wide=1600, parent=None):
        super().__init__(parent)
        self._audio_data = audio_data
        self._fs = fs
        self._t_start = t_start
        self._t_end = t_end
        self._token = token
        self._compact = compact
        self._freq_min = freq_min
        self._freq_max = freq_max
        self._contrast_pct = contrast_pct
        self._ribbon = ribbon
        self._fig_px_wide = fig_px_wide

    def __del__(self):
        try:
            self.wait()
        except RuntimeError:
            pass

    def run(self):
        if self._token[0]:
            return
        img, bbox = _render_slice_qimage(
            self._audio_data, self._fs,
            self._t_start, self._t_end,
            freq_min=self._freq_min,
            freq_max=self._freq_max,
            compact=self._compact,
            contrast_pct=self._contrast_pct,
            ribbon=self._ribbon,
            fig_px_wide=self._fig_px_wide,
        )
        if not self._token[0]:
            self.sigDone.emit(img, bbox)


# ---------------------------------------------------------------------------
# Zoomed detail panel
# ---------------------------------------------------------------------------

class ZoomedSpectroWidget(QWidget):
    """Large top panel — shows the zoomed time window with a red cursor line.

    The pixmap is scaled to fill the full widget (IgnoreAspectRatio) so the
    axis-fraction coordinates from matplotlib map simply to widget pixels.
    Clicking seeks to the clicked position within the zoom window.

    Live y-frequency crop (setFreqViewFracs) crops the pixmap in pixel space
    for instant visual feedback while sliders are being dragged.  The proper
    re-render (clearFreqCrop + setPixmap) replaces it once the render finishes.
    """

    seekRequested = Signal(float)   # fraction within the zoom window (0.0–1.0)
    panRequested  = Signal(float)   # delta fraction of zoom window (negative = left)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None         # full-file ribbon pixmap
        self._ax_bbox = (0.0, 1.0, 0.0, 1.0)
        self._viewLeft  = 0.0       # fraction of full file shown at left edge
        self._viewRight = 1.0       # fraction of full file shown at right edge
        self._fraction = None       # cursor position within the current viewport (0–1)
        self._freqBottomFrac = 0.0  # live crop: bottom of visible band as fraction
        self._freqTopFrac = 1.0     # live crop: top of visible band as fraction
        self._liveFreqCrop = False
        self._pressX = None
        self._lastPanX = None
        self._panning = False
        self._labelStartSec = 0.0
        self._labelEndSec   = 0.0
        self._labelHzMin    = 0.0
        self._labelHzMax    = 10000.0
        self._hoverPos = None       # last mouse pos over the panel, or None
        self.setMinimumHeight(200)
        self.setCursor(Qt.CrossCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)  # receive move events without a button held
        self.mdiParent = None

    def setPixmap(self, pixmap, ax_bbox=None):
        """Store the ribbon pixmap (covers the full recording file)."""
        self._pixmap = pixmap
        if ax_bbox is not None:
            self._ax_bbox = ax_bbox
        self.update()

    def setViewFracs(self, left, right):
        """Set which fraction of the full ribbon is currently visible."""
        self._viewLeft  = max(0.0, min(1.0, left))
        self._viewRight = max(0.0, min(1.0, right))
        self.update()

    def setLabelInfo(self, start_sec, end_sec, hz_min, hz_max):
        """Update the time and frequency values used to draw axis labels."""
        self._labelStartSec = start_sec
        self._labelEndSec   = end_sec
        self._labelHzMin    = hz_min
        self._labelHzMax    = hz_max
        self.update()

    def setViewState(self, left, right, start_sec, end_sec, hz_min, hz_max):
        """Set viewport fracs and label info in one call, firing update() once."""
        self._viewLeft      = max(0.0, min(1.0, left))
        self._viewRight     = max(0.0, min(1.0, right))
        self._labelStartSec = start_sec
        self._labelEndSec   = end_sec
        self._labelHzMin    = hz_min
        self._labelHzMax    = hz_max
        self.update()

    def setFraction(self, fraction):
        self._fraction = max(0.0, min(1.0, fraction))
        self.update()

    def clearFraction(self):
        self._fraction = None
        self.update()

    def setFreqViewFracs(self, bottom_frac, top_frac):
        """Apply immediate pixel-crop while freq sliders are being dragged."""
        self._freqBottomFrac = max(0.0, min(1.0, bottom_frac))
        self._freqTopFrac = max(0.0, min(1.0, top_frac))
        self._liveFreqCrop = (self._freqBottomFrac > 0.001 or self._freqTopFrac < 0.999)
        self.update()

    def clearFreqCrop(self):
        """Remove live crop — called when a fresh properly-ylim'd render arrives."""
        self._liveFreqCrop = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)

        if not (self._pixmap and not self._pixmap.isNull()):
            painter.end()
            return

        ax_x0, ax_x1, ax_y0, ax_y1 = self._ax_bbox
        rw, rh = self._pixmap.width(), self._pixmap.height()
        w, h   = self.width(), self.height()

        # Horizontal viewport crop (time axis).
        # Keep as float throughout so SmoothPixmapTransform can interpolate
        # sub-pixel positions — integer truncation causes staircase jitter.
        data_x0_px = ax_x0 * rw
        data_x1_px = ax_x1 * rw
        data_w_px  = data_x1_px - data_x0_px

        crop_x  = data_x0_px + self._viewLeft  * data_w_px
        crop_x2 = data_x0_px + self._viewRight * data_w_px
        crop_w  = max(1.0, crop_x2 - crop_x)

        # Build source rect in pixmap coordinates — combine horizontal and
        # optional vertical (freq) crop so painter does one GPU-accelerated
        # blit instead of the previous copy→scale→copy→scale chain.
        if self._liveFreqCrop and self._freqTopFrac > self._freqBottomFrac:
            data_y_bot_src = (1.0 - ax_y0) * rh
            data_y_top_src = (1.0 - ax_y1) * rh
            data_h_src     = data_y_bot_src - data_y_top_src
            src_y0 = data_y_bot_src - self._freqTopFrac    * data_h_src
            src_y1 = data_y_bot_src - self._freqBottomFrac * data_h_src
            src_h  = max(1.0, src_y1 - src_y0)
            cursor_top, cursor_bot = 0, h
        else:
            src_y0, src_h  = 0.0, float(rh)
            cursor_top = int((1.0 - ax_y1) * h)
            cursor_bot = int((1.0 - ax_y0) * h)

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(QRectF(0, 0, w, h), self._pixmap,
                           QRectF(crop_x, src_y0, crop_w, src_h))

        # Red cursor line — fraction within viewport maps directly to widget x.
        if self._fraction is not None:
            pen = QPen(QColor(220, 0, 0))
            pen.setWidth(2)
            painter.setPen(pen)
            # Clamp so the 2 px line stays fully on-screen at the extreme ends
            # (fraction 0 → left edge, fraction 1 → right edge) instead of being
            # half-clipped off the left or drawn past the right edge.
            lx = max(1, min(int(round(self._fraction * w)), w - 1))
            painter.drawLine(lx, cursor_top, lx, cursor_bot)

        self._drawAxisLabels(painter, w, h)
        self._drawHoverReadout(painter, w, h)
        painter.end()

    def _drawAxisLabels(self, painter, w, h):
        """Draw Hz and time tick labels overlaid on the spectrogram edges."""
        sec_range = self._labelEndSec  - self._labelStartSec
        hz_range  = self._labelHzMax   - self._labelHzMin
        if sec_range <= 0 or hz_range <= 0:
            return

        font = painter.font()
        font.setPointSize(11)
        painter.setFont(font)
        fm   = painter.fontMetrics()
        tick = QColor(68, 68, 68)
        bg   = QColor(255, 255, 255, 190)

        # ── Y-axis (Hz) — left strip ────────────────────────────────────
        interval = self._niceInterval(hz_range, 6)
        first_hz = np.ceil(self._labelHzMin / interval) * interval
        hz = float(first_hz)
        while hz <= self._labelHzMax + interval * 0.01:
            y_frac = 1.0 - (hz - self._labelHzMin) / hz_range
            y = int(y_frac * h)
            if 0 <= y <= h:
                painter.setPen(tick)
                painter.drawLine(0, y, 4, y)
                lbl = (f"{int(hz // 1000)}k" if hz >= 1000 and hz % 1000 == 0
                       else f"{int(hz)}" if hz < 1000 else f"{hz / 1000:.1f}k")
                lw = fm.horizontalAdvance(lbl)
                lh = fm.height()
                painter.fillRect(5, y - lh // 2, lw + 2, lh, bg)
                painter.setPen(tick)
                painter.drawText(5, y - lh // 2, lw + 2, lh,
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, lbl)
            hz += interval

        # "Hz" rotated label
        painter.save()
        painter.translate(fm.height(), h // 2)
        painter.rotate(-90)
        lbl = "Hz"
        lw = fm.horizontalAdvance(lbl)
        painter.fillRect(-lw // 2 - 1, -fm.height(), lw + 2, fm.height(), bg)
        painter.setPen(tick)
        painter.drawText(-lw // 2, 0, lbl)
        painter.restore()

        # ── X-axis (sec) — bottom strip ─────────────────────────────────
        interval = self._niceSecInterval(sec_range, 7)
        first_t  = np.ceil(self._labelStartSec / interval) * interval
        t = float(first_t)
        while t <= self._labelEndSec + interval * 0.01:
            x_frac = (t - self._labelStartSec) / sec_range
            x = int(x_frac * w)
            if 0 <= x <= w:
                painter.setPen(tick)
                painter.drawLine(x, h - 4, x, h)
                lbl = f"{t:.1f}s" if interval < 1.0 else f"{int(t)}s"
                lw = fm.horizontalAdvance(lbl)
                lh = fm.height()
                bx = max(0, min(w - lw - 2, x - lw // 2 - 1))
                painter.fillRect(bx, h - lh - 5, lw + 2, lh, bg)
                painter.setPen(tick)
                painter.drawText(bx, h - lh - 5, lw + 2, lh,
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, lbl)
            t += interval

        # "sec" axis label — bottom-right corner
        lbl = "sec"
        lw = fm.horizontalAdvance(lbl)
        lh = fm.height()
        painter.fillRect(w - lw - 6, h - lh - 5, lw + 4, lh, bg)
        painter.setPen(tick)
        painter.drawText(w - lw - 5, h - lh - 5, lw + 4, lh,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, lbl)

    @staticmethod
    def _niceInterval(value_range, target_ticks=6):
        raw = value_range / max(target_ticks, 1)
        mag = 10 ** int(np.log10(max(raw, 1.0)))
        for mult in [1, 2, 5, 10]:
            if mag * mult >= raw:
                return float(mag * mult)
        return float(mag * 10)

    @staticmethod
    def _niceSecInterval(value_range, target_ticks=7):
        raw = value_range / max(target_ticks, 1)
        for nice in [0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0, 120.0, 300.0]:
            if nice >= raw:
                return nice
        return 600.0

    def _drawHoverReadout(self, painter, w, h):
        """Floating box showing the time / kHz under the mouse pointer.

        Computed here (not on mouse-move) from the live label ranges, so the
        read-out stays correct as the viewport scrolls under a stationary
        pointer during playback."""
        if self._hoverPos is None or not (self._pixmap and not self._pixmap.isNull()):
            return
        sec_range = self._labelEndSec - self._labelStartSec
        hz_range  = self._labelHzMax - self._labelHzMin
        if sec_range <= 0 or hz_range <= 0 or w <= 0 or h <= 0:
            return

        mx, my = self._hoverPos.x(), self._hoverPos.y()
        if mx < 0 or mx > w or my < 0 or my > h:
            return

        # Time: mirror the click-seek mapping (ax_bbox data rect).
        ax_x0, ax_x1, _, _ = self._ax_bbox
        dl = ax_x0 * w
        dw = (ax_x1 - ax_x0) * w
        frac = max(0.0, min(1.0, (mx - dl) / dw)) if dw > 0 else 0.0
        t = self._labelStartSec + frac * sec_range

        # Hz: mirror the axis-label mapping (full widget height, top = high).
        hz = self._labelHzMin + (1.0 - my / h) * hz_range
        hz = max(self._labelHzMin, min(self._labelHzMax, hz))

        text = f"{t:.2f} s  ·  {hz / 1000.0:.2f} kHz"

        font = painter.font()
        font.setPointSize(11)
        painter.setFont(font)
        fm = painter.fontMetrics()
        pad_x, pad_y = 7, 4
        bw = fm.horizontalAdvance(text) + pad_x * 2
        bh = fm.height() + pad_y * 2

        # Offset up-right of the pointer; flip / clamp to stay fully on-screen.
        bx = mx + 14
        by = my - bh - 8
        if bx + bw > w:
            bx = mx - 14 - bw
        bx = max(0.0, min(bx, w - bw))
        if by < 0:
            by = my + 16
        by = max(0.0, min(by, h - bh))

        rect = QRectF(bx, by, bw, bh)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 185))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.setBrush(Qt.NoBrush)

    def contextMenuEvent(self, event):
        if self.mdiParent:
            self.mdiParent._showContextMenu(self.mapToGlobal(event.pos()))

    def keyPressEvent(self, e):
        if self.mdiParent:
            self.mdiParent.keyPressEvent(e)
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, event):
        self.setFocus()
        self._pressX  = event.position().x()
        self._lastPanX = self._pressX
        self._panning = False
        self.setCursor(Qt.ClosedHandCursor)   # hand from the moment the button goes down

    def mouseMoveEvent(self, event):
        x = event.position().x()
        self._hoverPos = event.position()
        if self._pressX is None:
            self.update()           # refresh the hover read-out
            return
        if not self._panning and abs(x - self._pressX) > 4:
            self._panning = True
        if self._panning:
            self.setCursor(Qt.ClosedHandCursor)   # hand while dragging the view
            ax_x0, ax_x1, _, _ = self._ax_bbox
            dw = (ax_x1 - ax_x0) * self.width()
            if dw > 0:
                delta = -(x - self._lastPanX) / dw
                self.panRequested.emit(delta)
            self._lastPanX = x
        self.update()

    def leaveEvent(self, event):
        self._hoverPos = None
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if not self._panning:
            ax_x0, ax_x1, _, _ = self._ax_bbox
            w = self.width()
            dl = ax_x0 * w
            dw = (ax_x1 - ax_x0) * w
            if dw > 0:
                frac = (event.position().x() - dl) / dw
                self.seekRequested.emit(max(0.0, min(1.0, frac)))
        self._pressX  = None
        self._lastPanX = None
        self._panning = False
        self.setCursor(Qt.CrossCursor)


# ---------------------------------------------------------------------------
# Overview / minimap panel
# ---------------------------------------------------------------------------

class OverviewSpectroWidget(QWidget):
    """Small bottom panel — full-file spectrogram, viewport rect, and cursor.

    Clicking outside the viewport emits seekRequested(fraction).
    Dragging the viewport rect emits viewportMoved(center_fraction).
    """

    seekRequested = Signal(float)       # file fraction 0.0–1.0 (click outside viewport)
    viewportMoved = Signal(float)       # new viewport center fraction (drag)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._ax_bbox = (0.0, 1.0, 0.0, 1.0)
        self._fraction = None       # playback cursor as fraction of full file
        self._viewport = None       # (left_frac, right_frac) of zoomed window
        self._dragging = False
        self._dragOffsetFrac = 0.0  # offset from click point to viewport centre
        self._duration = 0.0
        self.setFixedHeight(80)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

    def setDuration(self, duration):
        self._duration = duration
        self.update()

    def setPixmap(self, pixmap, ax_bbox=None):
        self._pixmap = pixmap
        if ax_bbox is not None:
            self._ax_bbox = ax_bbox
        self.update()

    def setFraction(self, fraction):
        self._fraction = max(0.0, min(1.0, fraction))
        self.update()

    def clearFraction(self):
        self._fraction = None
        self.update()

    def setViewport(self, left_frac, right_frac):
        self._viewport = (left_frac, right_frac)
        self.update()

    def _dataRect(self):
        """Data-area bounds in widget pixels (using IgnoreAspectRatio scaling)."""
        ax_x0, ax_x1, ax_y0, ax_y1 = self._ax_bbox
        w, h = self.width(), self.height()
        return ax_x0 * w, ax_x1 * w, (1.0 - ax_y1) * h, (1.0 - ax_y0) * h

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.white)

        if self._pixmap and not self._pixmap.isNull():
            rw, rh = self._pixmap.width(), self._pixmap.height()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(QRect(0, 0, self.width(), self.height()),
                               self._pixmap, QRect(0, 0, rw, rh))

            dl, dr, dt, db = self._dataRect()
            dw = dr - dl
            h  = self.height()

            # Zoom-window viewport rectangle.
            if self._viewport and dw > 0:
                vl, vr = self._viewport
                vx0 = int(dl + vl * dw)
                vx1 = int(dl + vr * dw)
                painter.fillRect(vx0, int(dt), vx1 - vx0, int(db - dt),
                                 QColor(100, 150, 255, 50))
                vpen = QPen(QColor(80, 120, 220, 200))
                vpen.setWidth(1)
                painter.setPen(vpen)
                painter.drawRect(vx0, int(dt), vx1 - vx0, int(db - dt) - 1)

            # Playback cursor — clamp inside the data rect so it stays visible
            # at the absolute start and end of the file.
            if self._fraction is not None and dw > 0:
                lx = int(round(dl + self._fraction * dw))
                lx = max(int(dl), min(lx, int(dr) - 1))
                cpen = QPen(QColor(220, 0, 0))
                cpen.setWidth(1)
                painter.setPen(cpen)
                painter.drawLine(lx, int(dt), lx, int(db))

            # Time axis labels.
            if self._duration > 0 and dw > 0:
                self._drawTimeLabels(painter, dl, dw, h)

        painter.end()

    def _drawTimeLabels(self, painter, data_left, data_width, h):
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        fm   = painter.fontMetrics()
        tick = QColor(68, 68, 68)
        bg   = QColor(255, 255, 255, 190)

        # Choose a nice tick interval that fits without crowding.
        target_ticks = max(3, int(data_width / 60))
        raw = self._duration / target_ticks
        interval = next((n for n in
                         [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600]
                         if n >= raw), 600)

        t = 0.0
        lh = fm.height()
        while t <= self._duration + interval * 0.01:
            x = int(data_left + (t / self._duration) * data_width)
            painter.setPen(tick)
            painter.drawLine(x, h - 4, x, h)
            lbl = f"{int(t)}s" if t == int(t) else f"{t:.1f}s"
            lw = fm.horizontalAdvance(lbl)
            bx = max(int(data_left), min(int(data_left + data_width) - lw - 2, x - lw // 2 - 1))
            painter.fillRect(bx, h - lh - 5, lw + 2, lh, bg)
            painter.setPen(tick)
            painter.drawText(bx, h - lh - 5, lw + 2, lh,
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, lbl)
            t += interval

    def _clickFrac(self, event):
        dl, dr, _, _ = self._dataRect()
        dw = dr - dl
        if dw <= 0:
            return None
        return (event.position().x() - dl) / dw

    def _isOverViewport(self, frac):
        if not self._viewport or frac is None:
            return False
        vl, vr = self._viewport
        return vl <= frac <= vr

    def mousePressEvent(self, event):
        frac = self._clickFrac(event)
        if frac is None:
            return
        # Check before seeking so we know the user's intent.
        was_over_viewport = self._isOverViewport(frac)
        # Always seek — moves the cursor and re-centers the viewport.
        self.seekRequested.emit(max(0.0, min(1.0, frac)))
        # If the click was inside the viewport, also arm dragging so the user
        # can continue sliding without releasing.  The viewport is now centred
        # on the click point, so the drag offset is zero.
        if was_over_viewport:
            self._dragging = True
            self._dragOffsetFrac = 0.0
            self.setCursor(Qt.SizeHorCursor)

    def mouseMoveEvent(self, event):
        frac = self._clickFrac(event)
        if self._dragging:
            if frac is not None:
                center = max(0.0, min(1.0, frac - self._dragOffsetFrac))
                self.viewportMoved.emit(center)
        else:
            if self._isOverViewport(frac):
                self.setCursor(Qt.SizeHorCursor)
            else:
                self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        frac = self._clickFrac(event)
        if self._isOverViewport(frac):
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.PointingHandCursor)


# ---------------------------------------------------------------------------
# Dual-handle Hz range slider
# ---------------------------------------------------------------------------

class HzRangeSlider(QWidget):
    """Vertical dual-handle slider for the visible frequency band.

    Top handle = ceiling (freq_high); bottom handle = floor (freq_low).
    The blue bar fills between the two handles.
    Emits rangeChanged(floor_hz, ceiling_hz) on every drag step.
    """

    rangeChanged = Signal(float, float)   # floor_hz, ceiling_hz

    _R  = 7   # handle radius, px
    _GW = 4   # groove width, px

    def __init__(self, parent=None):
        super().__init__(parent)
        self._maxFreq  = 10000.0
        self._floor    = 0.0
        self._ceiling  = 10000.0
        self._dragging = None   # 'ceiling' | 'floor' | None
        self.setFixedWidth(20)
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    # ── public API ───────────────────────────────────────────────────────

    def setMaxFreq(self, max_hz):
        self._maxFreq = float(max(1.0, max_hz))
        self._floor   = 0.0
        self._ceiling = self._maxFreq
        self.update()

    def setValues(self, floor_hz, ceiling_hz):
        """Programmatic update — does NOT emit rangeChanged."""
        self._floor   = max(0.0, float(floor_hz))
        self._ceiling = min(self._maxFreq, float(ceiling_hz))
        self.update()

    # ── coordinate helpers ───────────────────────────────────────────────

    def _hzToY(self, hz):
        """Hz → widget y-pixel.  Top = maxFreq, bottom = 0 Hz."""
        track = max(1, self.height() - 2 * self._R)
        return int(self._R + (1.0 - hz / self._maxFreq) * track)

    def _yToHz(self, y):
        track = max(1, self.height() - 2 * self._R)
        return max(0.0, min(self._maxFreq,
                            (1.0 - (y - self._R) / track) * self._maxFreq))

    def _hitHandle(self, y):
        """Return 'ceiling', 'floor', or None."""
        cy, fy = self._hzToY(self._ceiling), self._hzToY(self._floor)
        dc, df = abs(y - cy), abs(y - fy)
        hit = self._R + 3
        if dc <= hit and dc <= df:
            return 'ceiling'
        if df <= hit:
            return 'floor'
        return None

    # ── painting ─────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p  = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() // 2
        r, gw = self._R, self._GW
        gx = cx - gw // 2
        cy = self._hzToY(self._ceiling)
        fy = self._hzToY(self._floor)

        # Groove
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2b2d38"))
        p.drawRoundedRect(gx, r, gw, self.height() - 2 * r, 2, 2)

        # Blue fill between handles
        p.setBrush(QColor("#4f8ef7"))
        p.drawRect(gx, cy, gw, fy - cy)

        # Handles — ceiling on top, floor on bottom
        for y in (cy, fy):
            p.drawEllipse(cx - r, y - r, 2 * r, 2 * r)

        p.end()

    # ── mouse events ─────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = self._hitHandle(int(event.position().y()))
            if self._dragging:
                self.setCursor(Qt.CursorShape.SizeVerCursor)

    def mouseMoveEvent(self, event):
        y  = int(event.position().y())
        hz = self._yToHz(y)
        if self._dragging:
            min_gap = max(50.0, self._maxFreq * 0.01)
            if self._dragging == 'ceiling':
                self._ceiling = max(self._floor + min_gap,
                                    min(self._maxFreq, hz))
            else:
                self._floor = min(self._ceiling - min_gap,
                                  max(0.0, hz))
            self.update()
            self.rangeChanged.emit(self._floor, self._ceiling)
        else:
            hit = self._hitHandle(y)
            self.setCursor(Qt.CursorShape.SizeVerCursor if hit
                           else Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = None
            hit = self._hitHandle(int(event.position().y()))
            self.setCursor(Qt.CursorShape.SizeVerCursor if hit
                           else Qt.CursorShape.PointingHandCursor)


# ---------------------------------------------------------------------------
# Main AudioEnlargement window
# ---------------------------------------------------------------------------

class RecordingEnlargement(QMdiSubWindow, form_RecordingEnlargement.Ui_frmRecordingEnlargement):

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.mdiParent = ""

        # Full-screen state.  On Windows this window detaches from the MDI area
        # and shows itself as a top-level window (main window untouched); on macOS
        # the main window itself goes full screen (see toggleFullScreen).
        self._fullScreen = False
        self._mdiGeometry = None
        self._savedFlags = None

        # Audio state
        self._recordingData = None
        self._fs = 0
        self._duration = 0.0
        self._wavPath = ""
        self._sighting = {}
        self._audioRecord = None   # audio data dict for this file within _sighting

        # Navigation state (set by the Audio browser when launching)
        self._audioList = []       # [(recordingData, sighting), ...] from Audio browser
        self._currentIdx = 0
        self._spectroCache = {}    # filename -> (QPixmap, ax_bbox)

        # Time-axis zoom state.  Continuous: visible window = duration / zoomFactor,
        # zoomFactor in [1.0 (full clip), _maxZoom].  The ribbon is rendered at
        # _maxZoom pixel density, so any zoom level is a pure crop of it.
        self._zoomFactor = 1.0
        self._maxZoom = 1.0         # computed per clip in fillEnlargement
        self._windowStart = 0.0     # seconds
        self._windowEnd = 0.0       # seconds

        # Frequency-axis state
        self._maxFreq = 10000.0     # upper Hz limit of the recording
        self._freqViewBottom = 0.0  # currently displayed Hz range (bottom)
        self._freqViewTop = 10000.0 # currently displayed Hz range (top)

        # Contrast state: fraction (×100) of dB range clipped from the low end, 0–80
        self._contrastPct = 50
        self._autoContrastPct = 50  # per-file suggestion, computed once the base loads

        # Fit Hz toggle state
        self._fitHzActive = False

        # Render management — cancel tokens are [False]; set to [True] to abort
        self._zoomToken = None
        self._zoomThread = None
        self._overviewToken = None
        self._overviewThread = None
        self._ribbonRenderWidth = 0          # width of the in-flight ribbon render
        self._ribbonRenderCacheable = False  # True when that render is the cacheable open-state
        # Frequency range the currently-displayed ribbon pixmap actually covers.
        # Live Hz-slider crops are computed against THIS range (not _maxFreq), so a
        # second drag after a re-render zooms correctly within the cropped pixmap
        # instead of over-zooming and snapping back on release.
        self._ribbonFreqBottom = 0.0
        self._ribbonFreqTop = 10000.0
        self._ribbonRenderFreqBottom = 0.0   # captured at render start, committed on done
        self._ribbonRenderFreqTop = 10000.0
        # Grayscale ribbon base (rendered at contrast 0).  The Contrast slider
        # applies a live levels remap to this, so contrast never re-renders.
        self._ribbonBaseImage = None

        # Playback centering state machine
        self._centering = False       # True while cursor is working toward centre
        self._centeringDir = None     # 'left' or 'right'
        self._lastCursorPosSec = 0.0  # pos_sec at the previous _updateCursor tick
        self._pendingCenteringInit = False  # consumed in _onPlaybackStateChanged
        self._pendingPlay = False           # deferred play until media is loaded

        # ── Build layout ────────────────────────────────────────────────────
        central = QWidget()
        self.setWidget(central)
        outerHBox = QHBoxLayout(central)
        outerHBox.setContentsMargins(0, 0, 0, 0)
        outerHBox.setSpacing(0)

        contentWidget = QWidget()
        main = QVBoxLayout(contentWidget)
        main.setContentsMargins(4, 4, 4, 4)
        main.setSpacing(3)
        outerHBox.addWidget(contentWidget, 1)

        # ── Zoomed panel row: [Hz range slider | spectrogram] ──────────────
        zoomedRow = QHBoxLayout()
        zoomedRow.setSpacing(2)

        self._hzRangeSlider = HzRangeSlider()
        self._hzRangeSlider.setToolTip(
            "Drag top handle to set frequency ceiling, bottom handle to set floor")
        self._hzRangeSlider.rangeChanged.connect(self._onHzRangeChanged)
        zoomedRow.addWidget(self._hzRangeSlider)

        self._zoomedWidget = ZoomedSpectroWidget()
        self._zoomedWidget.mdiParent = self
        self._zoomedWidget.seekRequested.connect(self._onZoomedSeek)
        self._zoomedWidget.panRequested.connect(self._onZoomedPan)
        zoomedRow.addWidget(self._zoomedWidget, 1)

        main.addLayout(zoomedRow, 1)   # stretch: takes most of the height

        # Overview / minimap panel — left-aligned with the zoomed spectrogram
        # (offset by the hz-range slider width + row spacing).
        overviewRow = QHBoxLayout()
        overviewRow.setSpacing(0)
        _overviewSpacer = QWidget()
        _overviewSpacer.setFixedWidth(
            self._hzRangeSlider.width() + zoomedRow.spacing())
        overviewRow.addWidget(_overviewSpacer)
        self._overviewWidget = OverviewSpectroWidget()
        self._overviewWidget.seekRequested.connect(self._onOverviewSeek)
        self._overviewWidget.viewportMoved.connect(self._onViewportDragged)
        overviewRow.addWidget(self._overviewWidget, 1)
        main.addLayout(overviewRow)

        # Left offset for controls row — matches hz-range slider + gap.
        _leftOffset = self._hzRangeSlider.width() + zoomedRow.spacing()

        # Controls row: [Hz Auto] [--stretch--] [Play] [time] [--stretch--] [Zoom: ...]
        ctrl = QHBoxLayout()
        ctrl.setSpacing(6)
        ctrl.setContentsMargins(_leftOffset, 0, 0, 0)

        # The global QPushButton rule pads 12px each side, which is generous
        # enough to leave little slack once the details pane (F9) eats 297px
        # of window width — each of these three overrides its own padding
        # tighter so the fixed width can shrink without clipping the widest
        # label it ever shows ("Restore" / "Pause").
        self._autoRangeBtn = QPushButton("Fit Hz")
        self._autoRangeBtn.setFixedHeight(24)
        self._autoRangeBtn.setToolTip("Fit the frequency view to the active signal range")
        self._autoRangeBtn.setStyleSheet(
            "QPushButton { color: #4f8ef7; padding: 5px 8px; min-width: 45px; }"
            "QPushButton:pressed { color: white; }")
        self._autoRangeBtn.clicked.connect(self._onAutoRange)
        ctrl.addWidget(self._autoRangeBtn)

        ctrl.addStretch()

        # U+FE0E (text/monochrome variation selector) stops Windows from drawing
        # ⏮ as a colour-emoji tile (a blue square) — we want a plain white glyph
        # on the blue pill, matching the Play button beside it.
        self._backToStartBtn = QPushButton("⏮︎")
        self._backToStartBtn.setFixedSize(34, 30)
        self._backToStartBtn.setToolTip("Back to start")
        self._backToStartBtn.setStyleSheet(
            "QPushButton { background: #4f8ef7; color: white; border: none;"
            " border-radius: 6px; font-size: 14px; padding: 1px 3px; }"
            "QPushButton:hover { background: #6ba0f9; }"
            "QPushButton:pressed { background: #3f78d8; }")
        self._backToStartBtn.clicked.connect(self._onBackToStart)
        ctrl.addWidget(self._backToStartBtn)

        self._playBtn = QPushButton("Play")
        self._playBtn.setFixedWidth(50)
        self._playBtn.setFixedHeight(30)
        self._playBtn.setStyleSheet(
            "QPushButton { background: #4f8ef7; color: white; border: none;"
            " border-radius: 6px; padding: 4px 6px; }"
            "QPushButton:hover { background: #6ba0f9; }"
            "QPushButton:pressed { background: #3f78d8; }")
        self._playBtn.clicked.connect(self._onPlayClicked)
        ctrl.addWidget(self._playBtn)

        self._timeLabel = QLabel("0:00 / 0:00")
        ctrl.addWidget(self._timeLabel)

        ctrl.addStretch()

        ctrl.addWidget(QLabel("Contrast:"))
        self._contrastSlider = QSlider(Qt.Orientation.Horizontal)
        self._contrastSlider.setRange(0, 100)
        self._contrastSlider.setValue(50)
        self._contrastSlider.setFixedWidth(110)
        self._contrastSlider.setFixedHeight(24)
        self._contrastSlider.setToolTip(
            "Noise-floor suppression: drag right to make calls stand out more")
        self._contrastSlider.valueChanged.connect(self._onContrastChanged)
        ctrl.addWidget(self._contrastSlider)

        ctrl.addWidget(QLabel("Zoom:"))

        self._zoomSlider = QSlider(Qt.Orientation.Horizontal)
        self._zoomSlider.setRange(0, 0)   # range updated per clip in fillEnlargement
        self._zoomSlider.setValue(0)
        self._zoomSlider.setPageStep(1)
        self._zoomSlider.setFixedWidth(110)
        self._zoomSlider.setFixedHeight(24)
        self._zoomSlider.valueChanged.connect(self._onZoomSliderChanged)
        ctrl.addWidget(self._zoomSlider)

        main.addLayout(ctrl)

        # ── Details pane (F9 side panel) ────────────────────────────────────
        self._detailsPane = QFrame()
        self._detailsPane.setFrameShape(QFrame.Shape.NoFrame)
        self._detailsPane.setFixedWidth(_DETAILS_PANE_WIDTH)
        self._detailsPane.setStyleSheet(
            "color: silver; background-color: #343333; border: none;")

        _dpLayout = QVBoxLayout(self._detailsPane)
        _dpLayout.setContentsMargins(8, 8, 8, 8)
        _dpLayout.setSpacing(4)
        _dpLayout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._detailsCommonName = QLabel()
        self._detailsCommonName.setWordWrap(True)
        self._detailsCommonName.setStyleSheet(
            "font: 15pt; font-weight: bold; color: silver; "
            "background-color: #343333; padding: 3px;")
        _dpLayout.addWidget(self._detailsCommonName)

        self._detailsScientificName = QLabel()
        self._detailsScientificName.setWordWrap(True)
        self._detailsScientificName.setStyleSheet(
            "font: 12pt; font-style: italic; color: silver; "
            "background-color: #343333; padding: 3px;")
        _dpLayout.addWidget(self._detailsScientificName)

        self._detailsInfo = QLabel()
        self._detailsInfo.setWordWrap(True)
        self._detailsInfo.setStyleSheet(
            "color: silver; background-color: #343333; padding: 3px;")
        _dpLayout.addWidget(self._detailsInfo)

        # Notes — clickable label beneath the filename (in _detailsInfo); a
        # click (anywhere, even when empty) opens the same plain-text popup
        # used by Manage Recordings' Notes button.
        self._detailsNotes = QLabel()
        # Word wrap is off: elideToLines() already hard-breaks the text into
        # exactly the lines that fit, using its own pixel measurement. Leaving
        # Qt's automatic wrap on as well let it re-wrap a borderline line a
        # second time (its internal text-layout width can differ from
        # QFontMetrics.horizontalAdvance() by a few px), stranding the last
        # word of that line alone on an extra line.
        self._detailsNotes.setWordWrap(False)
        self._detailsNotes.setStyleSheet(
            "color: silver; background-color: #343333; padding: 3px;")
        self._detailsNotes.setCursor(Qt.CursorShape.PointingHandCursor)
        self._detailsNotes.mousePressEvent = lambda event: self._openNotesDialog()
        _dpLayout.addWidget(self._detailsNotes)
        _dpLayout.addSpacing(10)   # line feed after the Notes field

        _starsGroup = QGroupBox()
        _starsGroup.setContentsMargins(0, 0, 0, 0)
        _starsGroup.setStyleSheet(
            "QGroupBox { border: none; background-color: #343333; padding: 3px; }")
        _starsLayout = QHBoxLayout(_starsGroup)
        _starsLayout.setContentsMargins(0, 0, 0, 0)
        _starsLayout.setSpacing(0)
        _dpLayout.addWidget(_starsGroup)

        self._starBtns = []
        for _i in range(1, 6):
            _btn = QPushButton()
            _btn.setIconSize(QSize(40, 40))
            _btn.setIcon(QIcon(QPixmap(":/icon_star_gray.png")))
            # Zero the global QPushButton rule's padding/min-width — otherwise
            # each star's true footprint is that 60px floor plus 12px padding
            # per side (~86px), not the 40px icon, and 5 of them overflow the
            # details pane.
            _btn.setStyleSheet(
                "QPushButton { background-color: #343333; border: none; "
                "padding: 0px; min-width: 0px; }")
            _btn.clicked.connect(partial(self._starClicked, _i))
            _starsLayout.addWidget(_btn)
            self._starBtns.append(_btn)

        _dpLayout.addSpacing(10)   # line feed after the rating stars
        _dpLayout.addStretch()
        # Add to the layout (which reparents it) BEFORE making it visible.
        # setVisible(True) on the still-parentless QFrame realizes it as a
        # top-level native window — on Windows that appears as a small empty
        # "Yearbirder" window that lingers on screen for the whole (event-loop-
        # blocking) fillEnlargement decode: the reported spectrogram-click flash.
        outerHBox.addWidget(self._detailsPane)
        self._detailsPane.setVisible(True)

        # ── Player ──────────────────────────────────────────────────────────
        # QAudioSink-based player: plays pre-decoded PCM from memory so the first
        # audio is immediate (no AVFoundation per-source renderer priming delay).
        self._player = PcmAudioPlayer(self)
        self._player.playbackStateChanged.connect(self._onPlaybackStateChanged)
        self._player.mediaStatusChanged.connect(self._onMediaStatusChanged)

        # 100ms timer drives the centering state machine during playback.
        self._updateTimer = QTimer(self)
        self._updateTimer.timeout.connect(self._updatePlayback)

        # 16ms (~60fps) timer interpolates cursor position between real polls
        # so the red line and viewport scroll smoothly rather than in 100ms jumps.
        # PreciseTimer stops macOS from coalescing/delaying it for power saving —
        # coarse-timer jitter presents frames at uneven intervals, which reads as
        # a faint scroll stutter when zoomed in.
        self._cursorTimer = QTimer(self)
        self._cursorTimer.setTimerType(Qt.TimerType.PreciseTimer)
        self._cursorTimer.setInterval(16)
        self._cursorTimer.timeout.connect(self._updateCursor)
        self._lastRealPosSec = 0.0  # player position at last 100ms poll
        self._lastPollTime   = None  # time.perf_counter() at last poll
        self._gcWasEnabled   = None  # GC state saved while playback pauses it

        # Single-shot debounce for slider drags (avoids rendering on every step).
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._triggerRibbonRender)

        # A rating edit changes what open reports show — the Recordings Species
        # Gallery picks the best-rated recording per species, and ratings are part
        # of the media-scope signature — so it has to be broadcast.  Debounced:
        # stepping through stars would otherwise re-run every open report's
        # signature query on each keystroke.
        self._ratingNotifyTimer = QTimer(self)
        self._ratingNotifyTimer.setSingleShot(True)
        self._ratingNotifyTimer.setInterval(400)
        self._ratingNotifyTimer.timeout.connect(self._notifyRatingChanged)

        # Intercept arrow/page keys before any child widget (slider, button, etc.)
        # can consume them, so Left/Right/PageUp/PageDown always navigate recordings.
        _cw = self.widget()
        _cw.installEventFilter(self)
        for _w in _cw.findChildren(QWidget):
            _w.installEventFilter(self)

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        # Flush a pending rating broadcast: the debounce timer is parented to
        # this window, so closing within the debounce window would drop it.
        if self._ratingNotifyTimer.isActive():
            self._ratingNotifyTimer.stop()
            self._notifyRatingChanged()
        self._updateTimer.stop()
        self._cursorTimer.stop()
        self._debounce.stop()
        self._pausePlaybackGC(False)   # restore GC if closed mid-playback
        self._player.stop()
        if self._zoomToken:
            self._zoomToken[0] = True
        if self._overviewToken:
            self._overviewToken[0] = True
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)

    # ------------------------------------------------------------------
    # Fill
    # ------------------------------------------------------------------

    def fillEnlargement(self, wav_path, sighting, overview_cache=None):
        """Open this enlargement for the given WAV file.

        overview_cache: optional (QPixmap, ax_bbox) tuple from the Audio
        browser's spectroCache, used for instant overview display while the
        compact re-render runs in the background.
        """
        self._wavPath = wav_path
        self._sighting = sighting
        self._audioRecord = next(
            (a for a in sighting.get("audio", []) if a["fileName"] == wav_path),
            None,
        )

        data, fs, n_frames = _load_audio_data(wav_path)
        if data is None:
            return

        self._recordingData = data
        self._fs = fs
        self._duration = n_frames / fs if fs else 0.0

        self._maxFreq = float(fs // 2)
        self._freqViewBottom = 0.0
        self._freqViewTop = self._maxFreq
        # The initial ribbon covers the full frequency range.
        self._ribbonFreqBottom = 0.0
        self._ribbonFreqTop = self._maxFreq

        # Reset Hz range slider and contrast without triggering callbacks
        self._hzRangeSlider.setMaxFreq(self._maxFreq)   # resets floor=0, ceil=maxFreq
        self._contrastPct = 50
        self._fitHzActive = False
        self._autoRangeBtn.setText("Fit Hz")
        self._contrastSlider.blockSignals(True)
        self._contrastSlider.setValue(50)
        self._contrastSlider.blockSignals(False)

        # Max zoom: smallest window is _ZOOM_MIN_WINDOW seconds.  The ribbon is
        # rendered at this density so the deepest zoom is still a crop, not an
        # upscale.  Zoom is continuous between 1.0 (full clip) and _maxZoom.
        self._maxZoom = max(1.0, self._duration / _ZOOM_MIN_WINDOW)
        self._zoomFactor = 1.0
        self._zoomSlider.blockSignals(True)
        self._zoomSlider.setRange(0, _ZOOM_SLIDER_STEPS)
        self._zoomSlider.setValue(0)
        self._zoomSlider.blockSignals(False)
        self._setZoomWindow(0.0)   # derive window from zoom level, anchored at start
        self._overviewWidget.setDuration(self._duration)

        self._pendingPlay = False
        self._player.setSourceWav(wav_path)
        self._updateTimeLabel(0)
        # Show the cursor parked at the start so it's visible before playback,
        # matching the visible cursor left at the end when playback finishes.
        self._overviewWidget.setFraction(0.0)
        self._zoomedWidget.setFraction(0.0)

        species = sighting.get("commonName", "")
        basename = os.path.basename(wav_path)
        self.setWindowTitle(f"Recording: {species} — {basename}")

        self._setRecordingDetails()

        # Overview: prefer the persisted compact overview (instant, exact match);
        # otherwise show the browser thumbnail for immediate feedback and render
        # the compact overview in the background (which then caches it).
        cached_ov = code_ThumbnailCache.load(wav_path, "spectro_overview")
        if cached_ov is not None and not cached_ov.isNull():
            self._overviewWidget.setPixmap(QPixmap.fromImage(cached_ov), _OVERVIEW_AX_BBOX)
        else:
            if overview_cache:
                pm, bbox = overview_cache
                self._overviewWidget.setPixmap(pm, bbox)
            self._renderOverview()

        self._updateViewport()
        self._triggerRibbonRender()

    # ------------------------------------------------------------------
    # Render management
    # ------------------------------------------------------------------

    def _ribbonWidthPx(self):
        """Pixel width for the ribbon rendered at max-zoom density, capped at 16000.

        Always render at the max-zoom pixel density so that any zoom level is a
        crop of the ribbon rather than a blurry upscale.
        """
        widget_w = max(1200, self._zoomedWidget.width())
        return min(16000, int(widget_w * self._maxZoom))

    def _ribbonIsCacheable(self):
        """Always True: the ribbon base is rendered at the full frequency range
        and contrast 0, so it's fully deterministic regardless of the live Hz /
        contrast sliders (which only crop / remap the result)."""
        return True

    def _triggerRibbonRender(self):
        """Render (or load from cache) the deterministic ribbon BASE — full file,
        full frequency range, contrast 0.  The Hz and Contrast sliders are applied
        live to this base, so this runs only on open, never on a slider change."""
        if self._recordingData is None:
            return
        if self._zoomToken is not None:
            self._zoomToken[0] = True

        width = _RIBBON_CACHE_WIDTH
        self._ribbonRenderWidth = width
        self._ribbonRenderFreqBottom = 0.0
        self._ribbonRenderFreqTop = self._maxFreq

        # Cache hit: adopt the persisted base, then apply the live contrast remap
        # and Hz crop on top of it.
        img = code_ThumbnailCache.load(
            self._wavPath, "spectro_ribbon", variant=_RIBBON_VARIANT)
        if img is not None and not img.isNull():
            self._ribbonBaseImage = img.convertToFormat(QImage.Format_Grayscale8)
            self._ribbonFreqBottom = self._ribbonRenderFreqBottom
            self._ribbonFreqTop = self._ribbonRenderFreqTop
            self._seedAutoContrast()
            self._applyContrast()
            self._applyYFreqCrop()
            self._updateViewport()
            self._updateZoomCursor()
            return

        self._zoomToken = [False]
        t = _RenderThread(
            self._recordingData, self._fs,
            0.0, self._duration,        # always the full file
            self._zoomToken,
            ribbon=True,
            fig_px_wide=width,
            freq_min=0,                 # always full range; Hz slider crops the result
            freq_max=self._maxFreq,
            contrast_pct=0,             # base = widest range; contrast applied live
            parent=self,
        )
        t.sigDone.connect(self._onRibbonRenderDone)
        t.start()
        self._zoomThread = t

    def _renderOverview(self):
        """Render the full-file compact overview (full freq range) in a background thread."""
        if self._overviewToken is not None:
            self._overviewToken[0] = True

        self._overviewToken = [False]
        t = _RenderThread(
            self._recordingData, self._fs,
            0.0, self._duration,
            self._overviewToken, compact=True,
            freq_max=self._maxFreq, parent=self,
        )
        t.sigDone.connect(self._onOverviewRenderDone)
        t.start()
        self._overviewThread = t

    def _onRibbonRenderDone(self, image, ax_bbox):
        if image is not None and not image.isNull():
            # The render is the contrast-0 base; keep it grayscale and apply the
            # live contrast remap + Hz crop on top.
            self._ribbonBaseImage = image.convertToFormat(QImage.Format_Grayscale8)
            self._ribbonFreqBottom = self._ribbonRenderFreqBottom
            self._ribbonFreqTop = self._ribbonRenderFreqTop
            self._seedAutoContrast()
            self._applyContrast()
            self._applyYFreqCrop()
            self._updateViewport()               # push current viewport fracs
            self._updateZoomCursor()
            # Persist the contrast-0 base (grayscale) so the next open is instant.
            # Only the latest render reaches here (cancelled ones don't emit).
            code_ThumbnailCache.store(self._wavPath, self._ribbonBaseImage,
                                      "spectro_ribbon", variant=_RIBBON_VARIANT)

    def _onOverviewRenderDone(self, image, ax_bbox):
        if image is not None and not image.isNull():
            self._overviewWidget.setPixmap(QPixmap.fromImage(image), ax_bbox)
            # Persist the compact overview so the next open is instant.
            code_ThumbnailCache.store(self._wavPath, image, "spectro_overview")

    def _updateZoomCursor(self):
        """Set the zoomed-panel cursor fraction from the current player position."""
        window_dur = self._windowEnd - self._windowStart
        if window_dur <= 0 or self._duration <= 0:
            return
        pos_sec = self._player.position() / 1000.0
        frac = (pos_sec - self._windowStart) / window_dur
        self._zoomedWidget.setFraction(frac)

    # ------------------------------------------------------------------
    # Time-axis zoom controls
    # ------------------------------------------------------------------

    def _zoomFactorToSlider(self, factor):
        """Continuous zoom factor → slider value (geometric / log scale)."""
        if self._maxZoom <= 1.0:
            return 0
        frac = math.log(max(1.0, factor)) / math.log(self._maxZoom)
        return int(round(max(0.0, min(1.0, frac)) * _ZOOM_SLIDER_STEPS))

    def _sliderToZoomFactor(self, value):
        """Slider value → continuous zoom factor (geometric / log scale)."""
        if self._maxZoom <= 1.0:
            return 1.0
        return self._maxZoom ** (value / _ZOOM_SLIDER_STEPS)

    def _setZoomFactor(self, factor):
        """Clamp and apply a zoom factor, syncing the slider."""
        self._zoomFactor = max(1.0, min(self._maxZoom, factor))
        self._zoomSlider.blockSignals(True)
        self._zoomSlider.setValue(self._zoomFactorToSlider(self._zoomFactor))
        self._zoomSlider.blockSignals(False)
        self._applyZoom()

    def _zoomIn(self):
        # One "octave" per click (halve the visible window).
        self._setZoomFactor(self._zoomFactor * 2.0)

    def _zoomOut(self):
        self._setZoomFactor(self._zoomFactor / 2.0)

    def _onZoomSliderChanged(self, value):
        self._zoomFactor = self._sliderToZoomFactor(value)
        self._applyZoom()

    def _applyZoom(self):
        """Apply the current zoom as a pure viewport crop of the full-density
        ribbon — no re-render, so sliding is continuous and instant (like Hz)."""
        pos_sec = self._player.position() / 1000.0 if self._duration > 0 else 0.0
        self._setZoomWindow(pos_sec)
        self._updateViewport()

    def _setZoomWindow(self, center_sec):
        """Set _windowStart/_windowEnd centred on center_sec at the current zoom."""
        visible = max(_ZOOM_MIN_WINDOW, self._duration / self._zoomFactor)
        half = visible / 2.0
        start = max(0.0, center_sec - half)
        end = start + visible
        if end > self._duration:
            end = self._duration
            start = max(0.0, end - visible)
        self._windowStart = start
        self._windowEnd = end

    def _scrollToIfNeeded(self, pos_sec):
        """Scroll the zoom window only if pos_sec falls outside the current window.
        When inside, the cursor simply moves without disturbing the view."""
        if pos_sec < self._windowStart or pos_sec > self._windowEnd:
            self._setZoomWindow(pos_sec)
            self._updateViewport()

    def _updateViewport(self):
        """Update the viewport rectangle on the overview and the ribbon crop on the zoomed panel."""
        if self._duration <= 0:
            return
        left  = self._windowStart / self._duration
        right = self._windowEnd   / self._duration
        self._overviewWidget.setViewport(left, right)
        self._zoomedWidget.setViewState(
            left, right,
            self._windowStart, self._windowEnd,
            self._freqViewBottom, self._freqViewTop,
        )

    # ------------------------------------------------------------------
    # Frequency-axis controls
    # ------------------------------------------------------------------

    def _onHzRangeChanged(self, floor_hz, ceiling_hz):
        """Hz range slider moved — pure viewport crop, no re-render.

        The ribbon is always rendered at the full frequency range, and the
        spectrogram pixel data is identical regardless of the displayed Hz range
        (specgram computes the full spectrum; freq range only sets ax ylim).  So
        the Hz slider just crops the full-range pixmap — which works smoothly in
        both directions (shrink AND expand) with no re-render and no snap-back."""
        self._freqViewBottom = floor_hz
        self._freqViewTop    = ceiling_hz
        self._applyYFreqCrop()
        self._zoomedWidget.setLabelInfo(
            self._windowStart, self._windowEnd, floor_hz, ceiling_hz)

    def _applyYFreqCrop(self):
        """Push live pixel-crop fractions to the zoomed widget for instant feedback.

        Fractions are relative to the frequency range the *displayed* ribbon
        pixmap actually covers (_ribbonFreq*), not the full Nyquist range — so a
        second Hz-slider drag after a re-render zooms correctly within the
        already-cropped pixmap instead of over-zooming and snapping back."""
        span = self._ribbonFreqTop - self._ribbonFreqBottom
        if span <= 0:
            return
        self._zoomedWidget.setFreqViewFracs(
            (self._freqViewBottom - self._ribbonFreqBottom) / span,
            (self._freqViewTop - self._ribbonFreqBottom) / span,
        )

    def _computeAutoContrast(self):
        """Suggest an initial Contrast (0-100) from the base ribbon's grayscale.

        The base maps noise floor -> white, signal -> black.  We put the white
        point at the INK percentile of the band-limited grayscale, so the
        darkest ~15% (the signal) stays as ink and the brighter floor clips to
        white.  Because c = 100*(1 - I_white/255) and I_white adapts per file,
        quiet clean files get gentle contrast while files with a high/loud floor
        get more — self-normalizing the "overly white vs overly gray" look.
        Returns an int, or None if the base isn't available yet."""
        base = self._ribbonBaseImage
        if base is None or base.isNull():
            return None
        w, h, bpl = base.width(), base.height(), base.bytesPerLine()
        if w <= 0 or h <= 0:
            return None
        arr = np.frombuffer(base.constBits(), np.uint8).reshape(h, bpl)[:, :w]

        # Restrict to the bird-relevant band (top row = Nyquist, bottom = 0 Hz)
        # so low-frequency wind / handling rumble doesn't bias the floor estimate.
        nyq = float(self._maxFreq) if self._maxFreq else (
            self._fs / 2.0 if self._fs else 0.0)
        band = arr
        if nyq > _AUTO_CONTRAST_BAND_LO_HZ:
            hi = min(_AUTO_CONTRAST_BAND_HI_HZ, nyq)
            lo = min(_AUTO_CONTRAST_BAND_LO_HZ, hi)
            r_top = max(0, min(h - 1, int(round(h * (1.0 - hi / nyq)))))
            r_bot = max(r_top + 1, min(h, int(round(h * (1.0 - lo / nyq)))))
            sub = arr[r_top:r_bot, ::4]     # column-subsample for speed
            if sub.size:
                band = sub

        i_white = float(np.percentile(band, _AUTO_CONTRAST_INK_PCTILE))
        # Full-strength value (capped), then dialed back for a less-white default.
        c = min(_AUTO_CONTRAST_MAX, 100.0 * (1.0 - i_white / 255.0))
        c *= _AUTO_CONTRAST_SCALE
        c = int(round(max(_AUTO_CONTRAST_MIN, min(_AUTO_CONTRAST_MAX, c))))
        # Nudge the default a further 10% left (less contrast), keeping it on-slider.
        return max(0, c - _AUTO_CONTRAST_DEFAULT_OFFSET)

    def _seedAutoContrast(self):
        """Set this file's initial contrast from the base ribbon (once, at open).
        Stored in _autoContrastPct so future resets can return to it."""
        c = self._computeAutoContrast()
        if c is None:
            return
        self._autoContrastPct = c
        self._contrastPct = c
        self._contrastSlider.blockSignals(True)
        self._contrastSlider.setValue(c)
        self._contrastSlider.blockSignals(False)

    def _applyContrast(self):
        """Apply the current contrast as a live grayscale levels remap of the
        contrast-0 ribbon base — no re-render, so the slider is continuous.

        The base encodes the full 80 dB range; raising contrast by c% pulls the
        white point up: I' = clamp(I / (1 - c/100), 0, 255).  Because the base is
        the minimum contrast, every slider position is a 'raise' (no data lost)."""
        base = self._ribbonBaseImage
        if base is None or base.isNull():
            return
        denom = 1.0 - self._contrastPct / 100.0
        if denom <= 1e-6:
            lut = np.full(256, 255, dtype=np.uint8)
        else:
            lut = np.clip(np.arange(256) / denom, 0, 255).astype(np.uint8)
        w, h, bpl = base.width(), base.height(), base.bytesPerLine()
        arr = np.frombuffer(base.constBits(), np.uint8).reshape(h, bpl)[:, :w]
        out = np.ascontiguousarray(lut[arr])
        outQ = QImage(out.data, w, h, w, QImage.Format_Grayscale8).copy()
        self._zoomedWidget.setPixmap(QPixmap.fromImage(outQ), _RIBBON_AX_BBOX)

    def _onAutoRange(self):
        """Toggle between fitting the freq view to the active signal band and full spectrum."""
        if self._recordingData is None or self._fs == 0 or self._maxFreq <= 0:
            return

        if self._fitHzActive:
            # Restore full spectrum.
            self._freqViewBottom = 0.0
            self._freqViewTop    = self._maxFreq
            self._hzRangeSlider.setValues(0.0, self._maxFreq)
            self._fitHzActive = False
            self._autoRangeBtn.setText("Fit Hz")
            self._applyYFreqCrop()
            self._zoomedWidget.setLabelInfo(
                self._windowStart, self._windowEnd,
                self._freqViewBottom, self._freqViewTop)
            return

        # Fit to active band.
        nfft = 2048
        hop = nfft // 2
        n = len(self._recordingData)
        window = np.hanning(nfft)

        freq_bins = np.fft.rfftfreq(nfft, 1.0 / self._fs)
        mask = freq_bins <= self._maxFreq
        freq_bins = freq_bins[mask]

        # Peak power per bin (max over all frames): sensitive to brief signals
        # that would be drowned out by averaging.
        peak_power = np.zeros(int(mask.sum()), dtype=np.float64)
        count = 0
        for start in range(0, n - nfft, hop):
            segment = self._recordingData[start:start + nfft]
            power = np.abs(np.fft.rfft(segment * window)[:int(mask.sum())]) ** 2
            np.maximum(peak_power, power, out=peak_power)
            count += 1

        if count == 0:
            return

        # Skip very low bins (< 100 Hz) — usually handling/wind noise.
        skip = int(np.searchsorted(freq_bins, 100))
        search = peak_power[skip:]
        peak = float(np.max(search))
        if peak <= 0:
            return

        # Include all bins whose peak power is within 40 dB of the overall peak.
        threshold = peak * (10.0 ** (-40.0 / 10.0))
        active = np.where(search >= threshold)[0]
        if len(active) == 0:
            return

        freq_low  = max(0.0, freq_bins[skip + int(active[0])]  - 300.0)
        freq_high = min(self._maxFreq, freq_bins[skip + int(active[-1])] + 500.0)

        if freq_high <= freq_low:
            return

        self._freqViewBottom = freq_low
        self._freqViewTop    = freq_high
        self._hzRangeSlider.setValues(freq_low, freq_high)
        self._fitHzActive = True
        self._autoRangeBtn.setText("Restore")

        self._applyYFreqCrop()
        self._zoomedWidget.setLabelInfo(
            self._windowStart, self._windowEnd,
            self._freqViewBottom, self._freqViewTop)

    def _onContrastChanged(self, value):
        """Contrast slider moved — live grayscale levels remap of the ribbon base,
        no re-render (continuous, like the Hz and Zoom sliders)."""
        self._contrastPct = value
        self._applyContrast()

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    def _initCentering(self):
        """Determine the starting centering direction based on cursor vs viewport centre."""
        if self._duration <= 0 or self._zoomFactor <= 1.0:
            self._centering = False
            self._centeringDir = None
            return
        pos_sec = self._player.position() / 1000.0
        window_center = (self._windowStart + self._windowEnd) / 2.0
        lead = pos_sec - window_center
        if lead < -0.01:
            self._centering = True
            self._centeringDir = 'left'
        elif lead > 0.01:
            self._centering = True
            self._centeringDir = 'right'
        else:
            self._centering = False
            self._centeringDir = None
        self._lastCursorPosSec = pos_sec

    def _onPlayClicked(self):
        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._pendingCenteringInit = True
            _ready = (QMediaPlayer.MediaStatus.LoadedMedia,
                      QMediaPlayer.MediaStatus.BufferedMedia)
            if self._player.mediaStatus() in _ready:
                self._player.play()
            else:
                self._pendingPlay = True

    def _onBackToStart(self):
        self._player.stop()
        self._player.setPosition(0)
        self._setZoomWindow(0.0)
        self._updateViewport()
        # Park the cursor at the start (fraction 0) so it stays visible at the
        # left edge — symmetric with leaving it visible at the end of playback.
        self._overviewWidget.setFraction(0.0)
        self._zoomedWidget.setFraction(0.0)
        self._updateTimeLabel(0)

    def _anchorPlayback(self, pos_sec, resetGate=True):
        """Reset the wall-clock interpolation anchor to pos_sec (seconds).

        Cursor/viewport animation free-runs on the wall clock between anchors.
        The backend position() advances in coarse ~90 ms buffer steps, so we
        anchor only at play and on seeks — never re-snap to that staircase each
        poll, which made the zoomed viewport scroll in visible jerks."""
        self._lastRealPosSec   = pos_sec
        self._lastCursorPosSec = pos_sec
        self._lastPollTime     = time.perf_counter()
        # resetGate=True (play/seek): schedule a HOLD for the calibrated
        # output latency — the player floors position at the seek point until
        # the sound reaches the ears, so the interpolated cursor waits exactly
        # that long before gliding (zero wait on a zero-latency device).
        if resetGate:
            self._holdUntilTime = (time.perf_counter()
                                   + self._player.outputLatencyMs() / 1000.0)

    def _interpPosSec(self):
        """Wall-clock interpolated position, honoring the post-play/seek hold."""
        base = max(self._lastPollTime, getattr(self, "_holdUntilTime", 0.0))
        return self._lastRealPosSec + max(0.0, time.perf_counter() - base)

    def _pausePlaybackGC(self, pause):
        """Pause the cyclic GC while the spectrogram is scrolling.

        Playback allocates steadily (per-frame paint objects + the audio-feed
        byte slices), so the collector's gen-2 scan fires every few seconds and
        stalls the main thread for a few ms — one dropped frame, seen as an
        intermittent scroll hitch. Ordinary non-cyclic garbage is still freed
        immediately by refcounting, so memory doesn't grow over a clip. Re-enable
        (and sweep once) when scrolling stops."""
        if pause:
            if self._gcWasEnabled is None:
                self._gcWasEnabled = gc.isenabled()
                gc.disable()
        elif self._gcWasEnabled is not None:
            if self._gcWasEnabled:
                gc.enable()
            self._gcWasEnabled = None
            gc.collect()

    def _onPlaybackStateChanged(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._playBtn.setText("Pause")
            if self._pendingCenteringInit:
                self._pendingCenteringInit = False
                self._initCentering()
            self._anchorPlayback(self._player.position() / 1000.0)
            self._updateTimer.start(100)
            self._cursorTimer.start()
            self._pausePlaybackGC(True)
        else:
            self._playBtn.setText("Play")
            self._updateTimer.stop()
            self._cursorTimer.stop()
            self._pausePlaybackGC(False)

    def _onMediaStatusChanged(self, status):
        _ready = (QMediaPlayer.MediaStatus.LoadedMedia,
                  QMediaPlayer.MediaStatus.BufferedMedia)
        if status in _ready:
            if self._pendingPlay:
                self._pendingPlay = False
                self._player.play()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._pendingPlay = False
            self._playBtn.setText("Play")
            self._updateTimer.stop()
            self._cursorTimer.stop()
            self._pausePlaybackGC(False)
            self._centering = False
            self._centeringDir = None
            # Leave the cursor and viewport at the end of the recording rather
            # than rewinding — less jolting, and lets the user inspect the final
            # seconds.  The Back-to-Start button rewinds when they want it.
            self._setZoomWindow(self._duration)
            self._updateViewport()
            self._overviewWidget.setFraction(1.0)
            self._zoomedWidget.setFraction(1.0)
            self._updateTimeLabel(int(self._duration * 1000))

    def _updatePlayback(self):
        """Called every 100 ms during playback.  Updates the time label and only
        re-anchors the wall-clock interpolation on a *gross* divergence.

        The backend position() advances in coarse ~90 ms buffer steps, so it
        oscillates ±90 ms around the smooth interpolated value.  Re-snapping to
        that staircase every poll (the old behaviour) jerked the zoomed viewport.
        Normal anchoring happens at play and on seeks; here we leave the wall
        clock free-running and correct only if something has desynced badly.
        """
        dur_ms = self._player.duration()
        if dur_ms <= 0:
            return

        pos_ms  = self._player.position()
        pos_sec = pos_ms / 1000.0

        if self._lastPollTime is None:
            self._anchorPlayback(pos_sec, resetGate=False)
        elif abs(pos_sec - self._interpPosSec()) > 0.25:
            self._anchorPlayback(pos_sec, resetGate=False)

        self._updateTimeLabel(pos_ms)

    def _updateCursor(self):
        """Called every ~16 ms (60 fps).  Owns all cursor and viewport animation:

        • Centering-left  → viewport stays fixed; detects when interpolated
          cursor reaches centre and hands off to locked-centre immediately.
        • Centering-right → advances the viewport at _CENTERING_OVERSPEED×
          using the per-frame audio delta so scrolling is smooth at 60 fps.
        • Locked-centre   → keeps viewport centred on the interpolated position.
        """
        if self._duration <= 0 or self._lastPollTime is None:
            return

        pos_sec = min(self._interpPosSec(), self._duration)
        # Prevent backward jumps: macOS AVFoundation sometimes returns a cached
        # backend position slightly behind the interpolated value; anchoring on
        # that stale value makes the viewport scroll backward on every 100ms poll,
        # magnified by the zoom factor.  Clamping here ensures monotonic forward motion.
        pos_sec = max(pos_sec, self._lastCursorPosSec)
        frac_total = pos_sec / self._duration

        self._overviewWidget.setFraction(frac_total)

        if self._zoomFactor > 1.0:
            if self._centering:
                window_center = (self._windowStart + self._windowEnd) / 2.0
                if self._centeringDir == 'left':
                    # Viewport fixed; wait until interpolated cursor crosses centre.
                    if pos_sec >= window_center:
                        self._centering = False
                        self._centeringDir = None
                        self._setZoomWindow(pos_sec)
                        self._updateViewport()
                    # else: no viewport change this frame
                else:  # 'right'
                    # Advance viewport at overspeed using the per-frame audio delta.
                    frame_delta = max(0.0, pos_sec - self._lastCursorPosSec)
                    new_center = window_center + frame_delta * _CENTERING_OVERSPEED
                    if pos_sec <= new_center:
                        # Cursor reached centre — hand off to locked-centre.
                        self._centering = False
                        self._centeringDir = None
                        self._setZoomWindow(pos_sec)
                    else:
                        self._setZoomWindow(new_center)
                    self._updateViewport()
            else:
                # Locked-centre: keep viewport centred on the interpolated position.
                self._setZoomWindow(pos_sec)
                self._updateViewport()

        self._lastCursorPosSec = pos_sec

        window_dur = self._windowEnd - self._windowStart
        if window_dur > 0:
            frac_in_window = (pos_sec - self._windowStart) / window_dur
            self._zoomedWidget.setFraction(max(0.0, min(1.0, frac_in_window)))

    # ------------------------------------------------------------------
    # Seeking
    # ------------------------------------------------------------------

    def _onOverviewSeek(self, frac):
        if self._duration <= 0:
            return
        pos_ms = int(frac * self._duration * 1000)
        self._player.setPosition(pos_ms)
        pos_sec = frac * self._duration
        self._anchorPlayback(pos_sec)

        self._overviewWidget.setFraction(frac)
        self._updateTimeLabel(pos_ms)

        self._scrollToIfNeeded(pos_sec)
        self._updateZoomCursor()
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._initCentering()

    def _onViewportDragged(self, center_frac):
        """User is dragging the viewport rectangle; scroll zoom window without seeking."""
        if self._duration <= 0:
            return
        self._setZoomWindow(center_frac * self._duration)
        self._updateViewport()
        self._updateZoomCursor()

    def _onZoomedSeek(self, frac_in_window):
        """User clicked the zoomed panel; seek to that point within the zoom window."""
        if self._duration <= 0:
            return
        window_dur = self._windowEnd - self._windowStart
        pos_sec = max(0.0, min(self._duration,
                               self._windowStart + frac_in_window * window_dur))
        pos_ms = int(pos_sec * 1000)
        frac_total = pos_sec / self._duration

        self._player.setPosition(pos_ms)
        self._anchorPlayback(pos_sec)
        self._overviewWidget.setFraction(frac_total)
        self._zoomedWidget.setFraction(frac_in_window)
        self._updateTimeLabel(pos_ms)
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._initCentering()

    def _onZoomedPan(self, delta_frac):
        """User dragged the zoomed panel; shift the view window by delta_frac of its span."""
        if self._duration <= 0:
            return
        window_dur = self._windowEnd - self._windowStart
        delta_sec = delta_frac * window_dur
        new_start = self._windowStart + delta_sec
        new_end   = self._windowEnd   + delta_sec
        if new_start < 0:
            new_end  -= new_start
            new_start = 0.0
        if new_end > self._duration:
            new_start -= (new_end - self._duration)
            new_end    = self._duration
        self._windowStart = max(0.0, new_start)
        self._windowEnd   = min(self._duration, new_end)
        # Ribbon covers the full file — updating the viewport instantly repaints.
        self._updateViewport()

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _updateTimeLabel(self, pos_ms):
        def fmt(s):
            s = max(0, int(s))
            return f"{s // 60}:{s % 60:02d}"
        self._timeLabel.setText(fmt(pos_ms / 1000) + " / " + fmt(self._duration))

    # ------------------------------------------------------------------
    # Details pane (F9)
    # ------------------------------------------------------------------

    def _setRecordingDetails(self):
        s = self._sighting
        common = s.get("commonName", "")
        scientific = s.get("scientificName", "")
        location = s.get("location", "")

        rec = self._audioRecord or {}
        # Prefer the recording's true (embedded) creation date/time; fall back to
        # the checklist date/time when the file carries no metadata.
        if rec.get("metaDate"):
            date, time_str = rec["metaDate"], rec.get("metaTime", "")
        else:
            date, time_str = s.get("date", ""), s.get("time", "")

        try:
            weekday = datetime.datetime(
                int(date[0:4]), int(date[5:7]), int(date[8:10])
            ).strftime("%A") + ", "
        except Exception:
            weekday = ""

        duration = rec.get("duration", "")
        sample_rate = rec.get("sampleRate", "")
        bit_depth = rec.get("bitDepth", "")
        rating = rec.get("rating", "0")
        filename = (os.path.basename(self._wavPath)
                    .replace('_', '_​')
                    .replace('-', '-​')
                    .replace('.', '.​'))

        # Channels from the catalog (already "Mono"/"Stereo"); the stdlib wave
        # module can't read 32-bit-float or FLAC files, so reading the file here
        # would show nothing for exactly the high-res recordings we care about.
        channels_str = rec.get("channels", "")
        device = rec.get("device", "")

        info = f"\n\n{location}\n{weekday}{date} {time_str}\n"
        if duration:
            info += f"\nDuration: {duration}"
        if sample_rate:
            info += f"\n{sample_rate}"
        if bit_depth:
            info += f"\n{bit_depth}"
        if channels_str:
            info += f"\n{channels_str}"
        if device:
            info += f"\n{device}"
        info += f"\n\n{filename}\n"   # line feed between the file name and the Notes field

        self._detailsCommonName.setText("\n" + common)
        self._detailsScientificName.setText(scientific)
        self._detailsInfo.setText(info)
        self._refreshNotesLabel()

        try:
            r = int(rating)
        except (ValueError, TypeError):
            r = 0
        for i, btn in enumerate(self._starBtns):
            icon_name = ":/icon_star.png" if i < r else ":/icon_star_gray.png"
            btn.setIcon(QIcon(QPixmap(icon_name)))

    def toggleDetails(self):
        self._setDetailsPaneVisible(not self._detailsPane.isVisible())

    def _setDetailsPaneVisible(self, visible):
        """Show/hide _detailsPane. When the window isn't maximized, the pane
        is added to (or removed from) the window's width so the spectrogram
        area keeps its own width — rather than the pane eating into its
        space. While maximized there's no extra screen space to grow into,
        so it falls back to resizing the spectrogram area in place, as
        before."""
        if visible == self._detailsPane.isVisible():
            return

        if self.isMaximized():
            self._detailsPane.setVisible(visible)
        else:
            delta = _DETAILS_PANE_WIDTH if visible else -_DETAILS_PANE_WIDTH
            self._detailsPane.setVisible(visible)
            self.resize(self.width() + delta, self.height())

    def showNextRecording(self):
        n = len(self._audioList)
        for i in range(self._currentIdx + 1, n):
            a, s = self._audioList[i]
            if os.path.isfile(a.get("fileName", "")):
                self._currentIdx = i
                cached = self._spectroCache.get(a["fileName"])
                self.fillEnlargement(a["fileName"], s, overview_cache=cached)
                return

    def showPreviousRecording(self):
        for i in range(self._currentIdx - 1, -1, -1):
            a, s = self._audioList[i]
            if os.path.isfile(a.get("fileName", "")):
                self._currentIdx = i
                cached = self._spectroCache.get(a["fileName"])
                self.fillEnlargement(a["fileName"], s, overview_cache=cached)
                return

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Right, Qt.Key.Key_PageDown):
                self.showNextRecording()
                return True
            if key in (Qt.Key.Key_Left, Qt.Key.Key_PageUp):
                self.showPreviousRecording()
                return True
            # Space always toggles play/pause, intercepted here (this filter is on
            # every child widget) so a focused button/slider/combo can't consume it
            # first.  The Notes popup is a separate modal dialog, not a child of the
            # central widget, so it never reaches this filter.
            if key == Qt.Key.Key_Space:
                self._onPlayClicked()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, e):
        # Any Ctrl/Cmd shortcut (Open, Find, Media/Sighting filters, Toolbar…)
        # belongs to the main window — forward it and stop, so these work even
        # when this enlargement or its spectrogram has keyboard focus.  Without
        # this the enlargement's keyPressEvent swallows the event before it can
        # bubble up (e.g. Cmd-O to open a data file did nothing).  self.mdiParent
        # is the MainWindow.
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.mdiParent.keyPressEvent(e)
            return
        if e.key() == Qt.Key.Key_F9:
            self.toggleDetails()
        if e.key() == Qt.Key.Key_F10:
            # Defer so this runs after the event handler returns (matches the
            # photo Enlargement; avoids conflicts with native window ops).
            QTimer.singleShot(0, self.toggleFullScreen)
        if e.key() == Qt.Key.Key_Escape and self._fullScreen:
            # Esc exits full screen (only when currently in full screen).
            QTimer.singleShot(0, self.toggleFullScreen)
        if e.key() == Qt.Key.Key_Space:
            # Space toggles play/pause whenever the window itself holds focus
            # (child-widget focus is handled by eventFilter).
            self._onPlayClicked()
        if e.key() in (Qt.Key.Key_0, Qt.Key.Key_1, Qt.Key.Key_2,
                       Qt.Key.Key_3, Qt.Key.Key_4, Qt.Key.Key_5):
            rating_map = {
                Qt.Key.Key_0: 0, Qt.Key.Key_1: 1, Qt.Key.Key_2: 2,
                Qt.Key.Key_3: 3, Qt.Key.Key_4: 4, Qt.Key.Key_5: 5,
            }
            self.rateAudio(rating_map[e.key()])
        if e.key() in (Qt.Key.Key_Right, Qt.Key.Key_PageDown):
            self.showNextRecording()
        if e.key() in (Qt.Key.Key_Left, Qt.Key.Key_PageUp):
            self.showPreviousRecording()

    def toggleFullScreen(self):
        # Mirrors the photo Enlargement.  Called via QTimer.singleShot(0, ...) so
        # it runs after the triggering handler returns.  This enlargement's
        # mdiParent IS the MainWindow.  Full-screen state is tracked by
        # self._fullScreen.  The spectrogram widgets re-scale on resize, so unlike
        # photos there's no explicit re-fit.
        #
        # DETACH this enlargement from the MDI area and show it as a top-level
        # full-screen window, fading it in/out, leaving the main window untouched.
        # Used on BOTH platforms: it avoids Windows' desktop-exposing restore /
        # chrome flicker AND macOS's native full-screen animation (which moves the
        # app to its own Space, briefly exposing other windows and the menu bar).
        mainWindow = self.mdiParent
        mdiArea = mainWindow.mdiArea

        if not self._fullScreen:
            # ── Enter full screen ────────────────────────────────────────────
            self._mdiGeometry = self.geometry()
            self._savedFlags = self.windowFlags()
            mdiArea.removeSubWindow(self)      # detach: self becomes top-level
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
            self.showFullScreen()
            self.setWindowOpacity(0.0)         # invisible; faded in below
            self._fullScreen = True
            self.activateWindow()
            self.setFocus()
            self._startFade(0.0, 1.0)          # fade the full-screen image in
        else:
            # ── Exit full screen ─────────────────────────────────────────────
            self._fullScreen = False
            # Fade out, then re-attach to the MDI in the finished callback.
            self._startFade(1.0, 0.0, on_done=self._reattachFromFullScreen)

    def _startFade(self, start, end, on_done=None):
        """Animate this window's opacity (full-screen enter/exit fade).  Keeps a
        reference on self so the animation isn't garbage-collected."""
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(FADE_MS)
        anim.setStartValue(start)
        anim.setEndValue(end)
        # Rise fast on fade-in / drop slow on fade-out, so the window spends as
        # little time as possible semi-transparent — on macOS the menu bar can
        # peek through a partly-transparent full-screen window.
        anim.setEasingCurve(QEasingCurve.OutCubic if end > start else QEasingCurve.InCubic)
        if on_done is not None:
            anim.finished.connect(on_done)
        anim.start()
        self._fadeAnim = anim

    def _reattachFromFullScreen(self):
        """Exit fade-out finished: return this window to the MDI area (main window
        was never touched) and restore it as a normal, fully-interactive child.
        Restore the ORIGINAL subwindow flags — setting only Qt.SubWindow strips
        the title-bar/system-menu/button hints, leaving a frozen window."""
        mdiArea = self.mdiParent.mdiArea
        self.showNormal()
        mdiArea.addSubWindow(self)
        if self._savedFlags is not None:
            self.setWindowFlags(self._savedFlags)
        if self._mdiGeometry is not None:
            self.setGeometry(self._mdiGeometry)
        self.setWindowOpacity(1.0)   # undo the fade (harmless on an MDI child)
        self.show()
        mdiArea.setActiveSubWindow(self)
        self.activateWindow()
        self.setFocus()

    # ------------------------------------------------------------------
    # Rating
    # ------------------------------------------------------------------

    def _starClicked(self, star_idx):
        self.rateAudio(star_idx)

    def rateAudio(self, rating_int):
        if self._audioRecord is None:
            return
        self._audioRecord["rating"] = str(rating_int)
        self._setRecordingDetails()
        self._setDetailsPaneVisible(True)
        db = self.mdiParent.db
        db.photosNeedSaving = True
        try:
            db.appendRecordingToJsonl(self._sighting, self._audioRecord)
        except IOError as exc:
            QMessageBox.warning(self, "Settings File Error",
                f"Rating saved in memory but could not be written to the media catalog:\n{exc}")
        self._ratingNotifyTimer.start()   # debounced broadcast; see __init__

    def _notifyRatingChanged(self):
        # mdiParent is "" until the window is filled (and is the MainWindow, not
        # a browse window, for this enlargement — see Recordings.showEnlargement).
        if hasattr(self.mdiParent, "notifyMediaChanged"):
            self.mdiParent.notifyMediaChanged()

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------

    def _refreshNotesLabel(self):
        notes = self._audioRecord.get("notes", "") if self._audioRecord else ""
        metrics = self._detailsNotes.fontMetrics()
        # Clear _dpLayout's 8px left+right content margins and this label's
        # own 3px left+right CSS padding.
        width = self._detailsPane.width() - 16 - 6
        if not notes:
            self._detailsNotes.setText('Notes: <i>Click to add notes…</i>')
            return
        self._detailsNotes.setText(code_NotesDialog.elideToLines("Notes: " + notes, metrics, width, 4))

    def _openNotesDialog(self):
        if self._audioRecord is None:
            return
        dlg = code_NotesDialog.NotesDialog(self._audioRecord.get("notes", ""), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._audioRecord["notes"] = dlg.result
            db = self.mdiParent.db
            db.photosNeedSaving = True
            try:
                db.appendRecordingToJsonl(self._sighting, self._audioRecord)
            except IOError as exc:
                QMessageBox.warning(self, "Settings File Error",
                    f"Notes saved in memory but could not be written to the media catalog:\n{exc}")
            self._refreshNotesLabel()

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _showContextMenu(self, global_pos):
        menu = QMenu(self)
        menu.setStyleSheet("color: silver; background-color: #343333;")

        actionShowNextRecording = menu.addAction("Next recording (→)")
        actionShowPreviousRecording = menu.addAction("Previous recording (←)")
        menu.addSeparator()

        if self._detailsPane.isVisible():
            actionToggleDetails = menu.addAction("Hide details (F9)")
        else:
            actionToggleDetails = menu.addAction("Show details (F9)")

        if self._fullScreen:
            actionToggleFullScreen = menu.addAction("Exit full screen (F10)")
        else:
            actionToggleFullScreen = menu.addAction("Full screen (F10)")
        menu.addSeparator()

        actionRate1 = menu.addAction("Rate 1 star (1)")
        actionRate2 = menu.addAction("Rate 2 stars (2)")
        actionRate3 = menu.addAction("Rate 3 stars (3)")
        actionRate4 = menu.addAction("Rate 4 stars (4)")
        actionRate5 = menu.addAction("Rate 5 stars (5)")
        menu.addSeparator()

        actionDetach = menu.addAction("Remove recording from catalog…")
        menu.addSeparator()
        actionDelete = menu.addAction("Delete recording from file system…")

        action = menu.exec(global_pos)

        if action == actionShowNextRecording:
            self.showNextRecording()
        elif action == actionShowPreviousRecording:
            self.showPreviousRecording()
        elif action == actionToggleDetails:
            self.toggleDetails()
        elif action == actionToggleFullScreen:
            QTimer.singleShot(0, self.toggleFullScreen)
        elif action == actionRate1:
            self.rateAudio(1)
        elif action == actionRate2:
            self.rateAudio(2)
        elif action == actionRate3:
            self.rateAudio(3)
        elif action == actionRate4:
            self.rateAudio(4)
        elif action == actionRate5:
            self.rateAudio(5)
        elif action == actionDetach:
            self.detachFile()
        elif action == actionDelete:
            self.deleteFile()

    def handleAudioDeletion(self, filename, species=None):
        """A recording left the catalog — deleted from disk, or removed from the
        catalog for one species (species set) or all of them (species None).

        Without this the window kept showing a card that is no longer in the
        catalog: a WAV tagged to several species can be open in one enlargement
        per species, and rating the survivor re-appends the record that the other
        window just removed.  Prev/next was stale for the same reason — it skips
        entries whose file is missing from disk, which a catalog removal (file
        left in place) never triggers."""
        def removed(fileName, sighting):
            return (fileName == filename
                    and (species is None
                         or sighting.get("commonName", "") == species))

        # The card on display is gone — close, exactly as a removal started from
        # this window does (see detachFile / deleteFile).
        if removed(self._wavPath, self._sighting or {}):
            self.close()
            return

        kept = []
        for i, (a, s) in enumerate(self._audioList):
            if removed(a.get("fileName", ""), s):
                if i < self._currentIdx:
                    self._currentIdx -= 1   # keep the cursor on the same card
            else:
                kept.append((a, s))
        self._audioList = kept

    def handleRecordingRename(self, old_path, new_path):
        """Track a Rename Media move of the displayed recording.  The already
        decoded player buffer keeps playing, but _wavPath drives Remove/Delete,
        spectrogram (re)caching and the filename label, so re-point it (and the
        path-keyed caches) or those operations would act on a vanished file."""
        if self._wavPath == old_path:
            self._wavPath = new_path
            if getattr(self._player, "_currentPath", None) == old_path:
                self._player._currentPath = new_path
        if old_path in self._spectroCache:
            self._spectroCache[new_path] = self._spectroCache.pop(old_path)

    # ------------------------------------------------------------------
    # Remove / delete
    # ------------------------------------------------------------------

    def detachFile(self):
        db = self.mdiParent.db
        allSpecies  = db.getSpeciesForRecordingFile(self._wavPath)
        thisSpecies = self._sighting.get("commonName", "")

        if len(allSpecies) > 1:
            # Shared recording: removing it for every species is a bigger act
            # than the card the user is looking at, so offer the choice.
            speciesLines = "\n".join("    " + s for s in allSpecies)
            msgText = (
                f"Remove\n\n{self._wavPath}\n\n"
                "from the media catalog?\n\n"
                f"This recording is assigned to {len(allSpecies)} species:\n"
                f"{speciesLines}\n\n"
                f"Remove it for {thisSpecies} only, or for all of these species?\n\n"
                "(File will NOT be deleted from the file system)"
            )
            onlyLabel = f"Only {thisSpecies}"
            chosen = code_Stylesheet.choose(
                self, "Remove recording from catalog?", msgText,
                [onlyLabel, "All Species", "Cancel"])
            if chosen is None or chosen == "Cancel":
                return
            removeSpecies = thisSpecies if chosen == onlyLabel else None
        else:
            msgText = (
                f"Remove\n\n{self._wavPath}\n\n"
                "from the media catalog?\n\n"
                "(File will NOT be deleted from the file system)"
            )
            if (code_Stylesheet.question(self, "Remove recording from catalog?", msgText)
                    != QMessageBox.StandardButton.Yes):
                return
            removeSpecies = None

        db.removeRecordingFileFromDatabase(self._wavPath, removeSpecies)
        try:
            db.appendRecordingDeletionToJsonl(self._wavPath, removeSpecies)
        except IOError as exc:
            QMessageBox.warning(self, "Settings File Error",
                f"Recording removed from memory but could not be recorded in the catalog:\n{exc}")

        # Free the on-disk cache if the file is no longer assigned to any species.
        self.mdiParent.evictMediaCacheIfUnreferenced(self._wavPath)

        db.photosNeedSaving = True
        self._audioRecord = None
        # exclude=self: this window closes itself below, and in full screen it is
        # detached from the MDI area so the broadcast couldn't reach it anyway.
        self.mdiParent.notifyAudioDeletion(self._wavPath, removeSpecies, exclude=self)
        self.close()

    def deleteFile(self):
        allSpecies = self.mdiParent.db.getSpeciesForRecordingFile(self._wavPath)
        msgText = (
            f"Permanently delete\n\n{self._wavPath}\n\n"
            "from Yearbirder and the file system?"
        )
        if len(allSpecies) > 1:
            speciesLines = "\n".join("    " + s for s in allSpecies)
            msgText += (
                f"\n\nThis recording is assigned to {len(allSpecies)} species, "
                "and will be deleted for all of them:\n"
                f"{speciesLines}"
            )
        if (code_Stylesheet.question(self, "Permanently delete recording?", msgText)
                != QMessageBox.StandardButton.Yes):
            return

        db = self.mdiParent.db
        db.removeRecordingFileFromDatabase(self._wavPath)
        try:
            db.appendRecordingDeletionToJsonl(self._wavPath)
        except IOError as exc:
            QMessageBox.warning(self, "Settings File Error",
                f"Recording removed from memory but could not be recorded in the catalog:\n{exc}")

        db.photosNeedSaving = True

        # Evict the on-disk cache while the file still exists (the cache key needs
        # its mtime/size), before unlinking it below.
        self.mdiParent.evictMediaCacheIfUnreferenced(self._wavPath)

        if os.path.isfile(self._wavPath):
            try:
                os.remove(self._wavPath)
            except Exception:
                pass

        self._audioRecord = None
        self.mdiParent.notifyAudioDeletion(self._wavPath, exclude=self)
        self.close()
