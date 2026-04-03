import os
import queue
import copy
from functools import partial

from PySide6.QtGui import (
    QPixmap,
    QIcon,
    QImageReader,
)
from PySide6.QtCore import (
    Signal,   # used by _ThumbnailThread.sigFinished
    QSize,
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
)

import form_SpeciesGallery

# Thumbnail dimensions for gallery cells
THUMB_W = 200
THUMB_H = 150
CELL_SPACING = 6


class _ThumbnailThread(QThread):
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
                idx, photoFile = self.workQueue.get_nowait()
            except queue.Empty:
                break
            reader = QImageReader(photoFile)
            reader.setAutoTransform(True)
            imgSize = reader.size()
            if imgSize.isValid():
                imgSize.scale(QSize(THUMB_W, THUMB_H), Qt.KeepAspectRatio)
                reader.setScaledSize(imgSize)
            qimage = reader.read()
            self.resultQueue.put((idx, photoFile, qimage))
            self.workQueue.task_done()
        self.sigFinished.emit()


class SpeciesGallery(QMdiSubWindow, form_SpeciesGallery.Ui_frmSpeciesGallery):

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.mdiParent = None
        self.filter = None

        # list of (photo_dict, sighting_dict), one per species, taxonomic order
        self._galleryItems = []
        # list of (imgLabel, nameLabel, frame) parallel to _galleryItems
        self._cells = []
        self._pixmapCache = {}
        self._numCols = 4
        self._abort = False
        self.threadsRemaining = 0

        self.threadCount = min(os.cpu_count() or 4, 8)
        self.workQueue = queue.Queue()
        self.resultQueue = queue.Queue()
        self.threads = []
        for _ in range(self.threadCount):
            t = _ThumbnailThread()
            t.workQueue = self.workQueue
            t.resultQueue = self.resultQueue
            t.sigFinished.connect(self._threadFinished)
            self.threads.append(t)

        self._drainTimer = QTimer(self)
        self._drainTimer.timeout.connect(self._drainResultQueue)

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
        self.scrollArea.setGeometry(5, 27, self.width() - 10, self.height() - 35)
        # Defer reflow until the next event-loop iteration so Qt has finished
        # the layout pass and the viewport reports its final size.
        QTimer.singleShot(0, self._onResize)
        return super().resizeEvent(event)

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _calcCols(self):
        """Number of columns that fit in the scroll-area viewport.

        Called only from _onResize which is deferred via singleShot(0), so
        Qt has completed the layout pass and the viewport width is reliable.
        """
        available = self.scrollArea.viewport().width() - 4  # small buffer
        return max(1, available // (THUMB_W + CELL_SPACING))

    def _onResize(self):
        if self._abort:
            return
        newCols = self._calcCols()
        if newCols != self._numCols and self._cells:
            self._numCols = newCols
            self._reflowGrid()

    def _reflowGrid(self):
        """Re-place existing cell widgets under the new column count without
        re-loading any thumbnails."""
        for _, _, frame in self._cells:
            self.gridPhotos.removeWidget(frame)
        for i, (_, _, frame) in enumerate(self._cells):
            row, col = divmod(i, self._numCols)
            self.gridPhotos.addWidget(frame, row, col)

    # ------------------------------------------------------------------
    # Main fill entry point
    # ------------------------------------------------------------------

    def FillGallery(self, filter):
        self.filter = filter
        db = self.mdiParent.db

        sightings = db.GetSightingsWithPhotos(filter)
        if not sightings:
            return False

        # Build species -> (rating, photo_dict, sighting_dict, taxonomic_order)
        best = {}
        for s in sightings:
            taxo = float(s.get("taxonomicOrder", 0))
            name = s["commonName"]
            for p in s["photos"]:
                if db.TestIndividualPhoto(p, filter):
                    try:
                        rating = float(p["rating"]) if p["rating"] else 0.0
                    except (ValueError, TypeError):
                        rating = 0.0
                    if name not in best or rating > best[name][0]:
                        best[name] = (rating, p, s, taxo)

        if not best:
            return False

        # Sort by taxonomic order, then common name as tiebreaker
        self._galleryItems = [
            (entry[1], entry[2])
            for entry in sorted(best.values(), key=lambda x: (x[3], x[2]["commonName"]))
        ]

        speciesCount = len(self._galleryItems)
        self.lblTitle.setText("Species Gallery")
        self.lblCount.setText(f"{speciesCount:,} species with photos")
        self.setWindowTitle(
            filter.buildWindowTitle("Species Gallery", db, count=speciesCount, countUnit="Species"))

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_camera_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        # Resize the subwindow to fit 4 columns with room to breathe
        self.resize(860, 700)
        self.scrollArea.setGeometry(5, 27, 850, 665)
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
        """Create a placeholder cell frame for every gallery item."""
        self._cells = []
        for idx, (p, s) in enumerate(self._galleryItems):
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

            # Apply any already-cached pixmap immediately
            photoFile = p["fileName"]
            if photoFile in self._pixmapCache:
                pm = self._pixmapCache[photoFile]
                imgLbl.setPixmap(pm.scaled(imgLbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _fillGrid(self):
        """Place all cell frames into the grid layout."""
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
            (idx, p["fileName"])
            for idx, (p, _) in enumerate(self._galleryItems)
            if p["fileName"] not in self._pixmapCache
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
                idx, photoFile, qimage = self.resultQueue.get_nowait()
            except queue.Empty:
                break

            if self._abort:
                continue

            pm = QPixmap.fromImage(qimage)
            self._pixmapCache[photoFile] = pm

            if idx < len(self._cells):
                imgLbl = self._cells[idx][0]
                imgLbl.setPixmap(
                    pm.scaled(imgLbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

        if self.threadsRemaining == 0 and self.resultQueue.empty():
            self._drainTimer.stop()

    def _threadFinished(self):
        if not self._abort:
            self.threadsRemaining -= 1

    # ------------------------------------------------------------------
    # Click handler — opens Photos window filtered to the clicked species
    # ------------------------------------------------------------------

    def _cellClicked(self, idx, event):
        import code_Photos

        p, s = self._galleryItems[idx]
        species_name = s["commonName"]

        species_filter = copy.deepcopy(self.filter)
        species_filter.speciesName = species_name
        species_filter.speciesList = []

        sub = code_Photos.Photos()
        sub.mdiParent = self.mdiParent
        self.mdiParent.mdiArea.addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)
        sub.show()
        if sub.FillPhotos(species_filter) is False:
            sub.close()
