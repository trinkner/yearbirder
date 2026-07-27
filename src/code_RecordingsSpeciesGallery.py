"""Recordings Species Gallery — a native thumbnail grid of the best (highest-
rated) recording per species, shown as spectrogram thumbnails.  Cloned from the
photo Species Gallery (code_SpeciesGallery); the only real differences are the
data source (GetSightingsWithRecordings), the thumbnail (a spectrogram loaded
from / rendered into the shared on-disk cache, same as Browse Recordings), and
the click target (Browse Recordings)."""

import base64
import datetime
import os
import queue
import copy
from functools import partial

from PySide6.QtGui import QPixmap, QIcon, QImage
from PySide6.QtCore import (
    Signal,
    QByteArray,
    QBuffer,
    QIODevice,
    Qt,
    QThread,
    QTimer,
)
from PySide6.QtWidgets import (
    QMdiSubWindow,
    QLabel,
    QFrame,
    QVBoxLayout,
    QApplication,
    QMessageBox,
)

import form_SpeciesGallery
import code_MediaRefresh
import code_ThumbnailCache
from code_Audio import (
    render_spectrogram_qimage as _render_spectrogram_qimage,
    paint_spectro_axes as _paint_spectro_axes,
)

# Thumbnail dimensions for gallery cells — same size as the photo gallery.
THUMB_W = 200
THUMB_H = 150
CELL_SPACING = 6


class _SpectroThumbThread(QThread):
    """Worker: produce a spectrogram QImage for one WAV file, from the on-disk
    cache when present, otherwise rendered WITHOUT axis text (drawing text off
    the GUI thread corrupts macOS glyph metrics — the GUI thread paints the axes
    in _drainResultQueue).  Mirrors threadLoadSpectrogram in code_Recordings."""
    sigFinished = Signal()

    def __init__(self):
        super().__init__()
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
                idx, wavFile = self.workQueue.get_nowait()
            except queue.Empty:
                break
            img = code_ThumbnailCache.load(wavFile, "spectro_thumb",
                                           code_ThumbnailCache.SPECTRO_THUMB_VARIANT)
            if img is not None and not img.isNull():
                duration, sr, axesPending = 0, 0, False
            else:
                img, duration, sr, _bbox = _render_spectrogram_qimage(
                    wavFile, draw_axis_text=False)
                axesPending = img is not None and not img.isNull()
            self.resultQueue.put((idx, wavFile, img, duration, sr, axesPending))
            self.workQueue.task_done()
        self.sigFinished.emit()


class RecordingsSpeciesGallery(QMdiSubWindow, form_SpeciesGallery.Ui_frmSpeciesGallery):

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.mdiParent = None
        self.filter = None

        # list of (audio_dict, sighting_dict), one per species, taxonomic order
        self._galleryItems = []
        # list of (imgLabel, nameLabel, frame) parallel to _galleryItems
        self._cells = []
        self._pixmapCache = {}   # wav path -> QPixmap (full spectro thumb)
        self._numCols = 4
        self._abort = False
        self.threadsRemaining = 0

        self.threadCount = min(os.cpu_count() or 4, 8)
        self.workQueue = queue.Queue()
        self.resultQueue = queue.Queue()
        self.threads = []
        for _ in range(self.threadCount):
            t = _SpectroThumbThread()
            t.workQueue = self.workQueue
            t.resultQueue = self.resultQueue
            t.sigFinished.connect(self._threadFinished)
            self.threads.append(t)

        self._drainTimer = QTimer(self)
        self._drainTimer.timeout.connect(self._drainResultQueue)

        # Recordings have no slideshow; repurpose the second button to open the
        # full Browse Recordings for the current filter, and hide Slideshow.
        self.buttonSlideshow.setVisible(False)
        self.buttonShowAll.setText("Show All Recordings")
        self.buttonShowAll.clicked.connect(self.showAllRecordings)

    # ------------------------------------------------------------------
    # Qt event overrides
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._abort = True
        self._drainTimer.stop()
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
        super().closeEvent(event)

    def resizeEvent(self, event):
        header_h = max(self.headerFrame.sizeHint().height(), 50) + 10
        self.headerFrame.setGeometry(5, 27, self.width() - 10, header_h)
        self.scrollArea.setGeometry(5, 27 + header_h, self.width() - 10,
                                    self.height() - 35 - header_h)
        QTimer.singleShot(0, self._onResize)
        return super().resizeEvent(event)

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _calcCols(self):
        available = self.scrollArea.viewport().width() - 4
        return max(1, available // (THUMB_W + CELL_SPACING))

    def _onResize(self):
        if self._abort:
            return
        newCols = self._calcCols()
        if newCols != self._numCols and self._cells:
            self._numCols = newCols
            self._reflowGrid()

    def _reflowGrid(self):
        for _, _, frame in self._cells:
            self.gridPhotos.removeWidget(frame)
        for i, (_, _, frame) in enumerate(self._cells):
            row, col = divmod(i, self._numCols)
            self.gridPhotos.addWidget(frame, row, col)

    # ------------------------------------------------------------------
    # Print / PDF support
    # ------------------------------------------------------------------

    def _spectroImageForPrint(self, wavFile):
        """A finished (axes-baked) spectrogram QImage for one WAV, cache-first."""
        img = code_ThumbnailCache.load(wavFile, "spectro_thumb",
                                       code_ThumbnailCache.SPECTRO_THUMB_VARIANT)
        if img is not None and not img.isNull():
            return img
        img, duration, sr, _bbox = _render_spectrogram_qimage(
            wavFile, draw_axis_text=False)
        if img is not None and not img.isNull():
            _paint_spectro_axes(img, duration, sr)
            code_ThumbnailCache.store(wavFile, img, "spectro_thumb",
                                      code_ThumbnailCache.SPECTRO_THUMB_VARIANT)
        return img

    def html(self):
        title = self.windowTitle()
        if ': ' in title:
            type_part, filter_part = title.split(': ', 1)
            heading = '<h1>' + type_part + '</h1><h2>' + filter_part + '</h2>'
        else:
            heading = '<h1>' + title + '</h1>'

        html = """<!DOCTYPE html>
<html><head></head>
<style>
* { font-family: "Times New Roman", Times, serif; }
h1 { font-size: 16pt; margin-bottom: 2px; }
h2 { font-size: 11pt; font-weight: normal; margin-top: 0; margin-bottom: 8px; }
table { width: 100%; border-collapse: collapse; }
td { width: 50%; vertical-align: top; padding: 6px; text-align: center; }
.caption { font-size: 8pt; margin-top: 4px; text-align: left; }
</style>
<body>
"""
        html += heading

        cells = []
        for a, s in self._galleryItems:
            img = self._spectroImageForPrint(a["fileName"])
            if img is None or img.isNull():
                continue
            pixmap = QPixmap.fromImage(img).scaled(
                540, 360, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            byte_array = QByteArray()
            buf = QBuffer(byte_array)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            pixmap.save(buf, "PNG")
            encoded = base64.b64encode(bytes(byte_array)).decode('ascii')
            img_tag = '<img src="data:image/png;base64,' + encoded + '" width="270">'

            try:
                weekday = datetime.datetime(
                    int(s["date"][0:4]), int(s["date"][5:7]), int(s["date"][8:10])
                ).strftime("%A")
            except Exception:
                weekday = ""

            caption = (
                '<b>' + s["commonName"] + '</b><br>'
                '<i>' + s["scientificName"] + '</i><br>'
                + s["location"] + '<br>'
                + weekday + ', ' + s["date"]
            )

            cells.append('<td>' + img_tag + '<div class="caption">' + caption + '</div></td>')

        for i in range(0, len(cells), 6):
            page_cells = cells[i:i+6]
            if len(page_cells) % 2 != 0:
                page_cells.append('<td></td>')
            html += '<table>'
            for j in range(0, len(page_cells), 2):
                html += '<tr>' + page_cells[j] + page_cells[j + 1] + '</tr>'
            html += '</table>'
            if i + 6 < len(cells):
                html += '<div style="page-break-after: always;"></div>'

        html += '</body></html>'
        return html

    # ------------------------------------------------------------------
    # Main fill entry point
    # ------------------------------------------------------------------

    @code_MediaRefresh.media_report(is_content=True)   # rebuild on media changes
    def FillGallery(self, filter):
        self.filter = filter
        db = self.mdiParent.db

        sightings = db.GetSightingsWithRecordings(filter)
        if not sightings:
            return False

        # Best (highest-rated) recording per species.  GetSightingsWithRecordings
        # already applied the filter at the sighting level (as Browse Recordings
        # does), so take every audio entry in the returned sightings.
        best = {}
        for s in sightings:
            taxo = float(s.get("taxonomicOrder", 0))
            name = s["commonName"]
            for a in s.get("audio", []):
                try:
                    rating = float(a["rating"]) if a.get("rating") else 0.0
                except (ValueError, TypeError):
                    rating = 0.0
                if name not in best or rating > best[name][0]:
                    best[name] = (rating, a, s, taxo)

        if not best:
            return False

        self._galleryItems = [
            (entry[1], entry[2])
            for entry in sorted(best.values(), key=lambda x: (x[3], x[2]["commonName"]))
        ]

        speciesCount = len(self._galleryItems)
        self.lblTitle.setText("Species Gallery")
        self.lblCount.setText(f"{speciesCount:,} species with recordings")
        self.setWindowTitle(
            filter.buildWindowTitle("Recordings Species Gallery", db,
                                    count=speciesCount, countUnit="Species"))

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_microphone_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        self.resize(860, 700)
        QApplication.processEvents()

        self._numCols = self._calcCols()
        self._buildCells()
        self._fillGrid()
        self._startLoading()
        return True

    # ------------------------------------------------------------------
    # Cell construction and grid layout
    # ------------------------------------------------------------------

    def _buildCells(self):
        self._cells = []
        for idx, (a, s) in enumerate(self._galleryItems):
            frame = QFrame()
            frame.setFixedSize(THUMB_W, THUMB_H + 36)
            frame.setStyleSheet(
                "QFrame { background: #2a2b35; border-radius: 4px; }"
                "QFrame:hover { background: #363848; }"
            )
            frame.setCursor(Qt.PointingHandCursor)
            frame.mousePressEvent = partial(self._cellClicked, idx)

            vlay = QVBoxLayout(frame)
            vlay.setContentsMargins(0, 0, 0, 4)
            vlay.setSpacing(2)

            imgLbl = QLabel()
            imgLbl.setFixedSize(THUMB_W, THUMB_H)
            imgLbl.setAlignment(Qt.AlignCenter)
            imgLbl.setStyleSheet("background: transparent; border-radius: 4px 4px 0 0;")
            vlay.addWidget(imgLbl)

            nameLbl = QLabel(s["commonName"])
            nameLbl.setFixedWidth(THUMB_W)
            nameLbl.setWordWrap(True)
            nameLbl.setAlignment(Qt.AlignCenter)
            nameLbl.setStyleSheet(
                "color: #c8ccdf; font-size: 10px; background: transparent; padding: 0 2px;"
            )
            vlay.addWidget(nameLbl)

            self._cells.append((imgLbl, nameLbl, frame))

            wavFile = a["fileName"]
            if wavFile in self._pixmapCache:
                pm = self._pixmapCache[wavFile]
                imgLbl.setPixmap(pm.scaled(imgLbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _fillGrid(self):
        for _, _, frame in self._cells:
            self.gridPhotos.removeWidget(frame)
        for i, (_, _, frame) in enumerate(self._cells):
            row, col = divmod(i, self._numCols)
            self.gridPhotos.addWidget(frame, row, col)
        QApplication.processEvents()

    # ------------------------------------------------------------------
    # Thumbnail loading
    # ------------------------------------------------------------------

    def _startLoading(self):
        uncached = [
            (idx, a["fileName"])
            for idx, (a, _) in enumerate(self._galleryItems)
            if a["fileName"] not in self._pixmapCache
        ]
        if not uncached:
            return

        for item in uncached:
            self.workQueue.put(item)

        threadsToStart = min(self.threadCount, len(uncached))
        self.threadsRemaining = threadsToStart
        for i in range(threadsToStart):
            self.threads[i].start()
        self._drainTimer.start(50)

    def _drainResultQueue(self):
        while True:
            try:
                idx, wavFile, img, duration, sr, axesPending = self.resultQueue.get_nowait()
            except queue.Empty:
                break

            if self._abort:
                continue
            if img is None or img.isNull():
                continue

            # Composite the kHz/sec axes on the GUI thread (worker rendered the
            # spectrogram text-free), then cache the finished image.  QImage ->
            # QPixmap conversion is also GUI-thread-only.
            if axesPending:
                _paint_spectro_axes(img, duration, sr)
                code_ThumbnailCache.store(wavFile, img, "spectro_thumb",
                                          code_ThumbnailCache.SPECTRO_THUMB_VARIANT)
            pm = QPixmap.fromImage(img)
            self._pixmapCache[wavFile] = pm

            if idx < len(self._cells):
                imgLbl = self._cells[idx][0]
                imgLbl.setPixmap(
                    pm.scaled(imgLbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

        if self.threadsRemaining == 0 and self.resultQueue.empty():
            self._drainTimer.stop()
            code_ThumbnailCache.enforce_cap()   # keep the on-disk cache bounded

    def _threadFinished(self):
        if not self._abort:
            self.threadsRemaining -= 1

    # ------------------------------------------------------------------
    # Click handler — opens Browse Recordings filtered to the clicked species
    # ------------------------------------------------------------------

    def _cellClicked(self, idx, event):
        import code_Recordings

        a, s = self._galleryItems[idx]
        species_name = s["commonName"]

        species_filter = copy.deepcopy(self.filter)
        species_filter.speciesName = species_name
        species_filter.speciesList = []

        sub = code_Recordings.Recordings()
        sub.mdiParent = self.mdiParent
        self.mdiParent.mdiArea.addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)
        sub.show()
        if sub.FillRecordings(species_filter) is False:
            sub.close()

    def showAllRecordings(self):
        import code_Recordings
        sub = code_Recordings.Recordings()
        sub.mdiParent = self.mdiParent
        self.mdiParent.mdiArea.addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)
        sub.show()
        if sub.FillRecordings(self.filter) is False:
            self.mdiParent.CreateMessageNoResults()
            sub.close()
