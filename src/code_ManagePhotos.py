# import project files
import form_ManagePhotos
from code_Stylesheet import YBFont
import code_Filter
import code_Stylesheet
import code_ThumbnailCache
import code_ChecklistTree
import code_NotesDialog
import os

import piexif

# import basic Python libraries
import bisect
import queue
import threading
import time
from functools import partial

from collections import defaultdict

from PySide6.QtGui import (
    QPixmap,
    QFont,
    QIcon,
    QCursor,
    QPalette,
    QColor,
    )

from PySide6.QtCore import (
    Signal,
    QSize,
    Qt,
    QThread,
    QTimer,
    )

from PySide6.QtWidgets import (
    QMdiSubWindow,
    QPushButton,
    QApplication,
    QWidget,
    QLabel,
    QComboBox,
    QHBoxLayout,
    QVBoxLayout,
    QMessageBox,
    QProgressBar,
    QFileDialog,
    QStyledItemDelegate,
    QCheckBox,
    QDialog,
    )


# Colours for the assignment labels.  A field's value is shown green only while
# it still equals the value auto-derived from the photo's metadata / filename;
# once the user overrides it via the tree (or it was never auto-derived) it is
# shown in the neutral text colour.
_FIELD_NAME_COLOR = "#c1c1c1"          # matches the Browse windows' card text
_MATCH_COLOR      = "#4CAF50"          # green  – value came from metadata/filename
_VALUE_COLOR      = "#c1c1c1"          # neutral – manually chosen / not auto-derived
_SKIPPED_COLOR    = "#6b6e7e"          # muted value when the row is skipped
_NO_SPECIES_COLOR = "#E57373"          # red – flags a row that still needs a species picked
# Species sentinel that savePhotoSettings treats as "do not attach" ("**").
_SKIP_SENTINEL = "** (skipped) **"


def _wrappable(text):
    """Insert zero-width break opportunities after separator characters.
    Word wrap can only break at whitespace, so an underscore-joined filename
    is one unbreakable word — the label's MINIMUM width becomes the full text
    width, overflowing the window and pushing the controls column past the
    right edge."""
    return "".join(c + "\u200b" if c in "_-." else c for c in text)

# Displayed thumbnail size, shared with the Photos browser: the cached image is
# 500x330 (code_ThumbnailCache.THUMB_SIZE); both views show it smaller so more
# rows fit vertically.
_THUMB_DISPLAY_W = code_ThumbnailCache.THUMB_DISPLAY_SIZE.width()
_THUMB_DISPLAY_H = code_ThumbnailCache.THUMB_DISPLAY_SIZE.height()


class GreenMatchDelegate(QStyledItemDelegate):
    """Paints a single popup item green to signal that the EXIF timestamp matched a checklist."""

    def __init__(self, match_text, parent=None):
        super().__init__(parent)
        self._match_text = match_text

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.data(Qt.ItemDataRole.DisplayRole) == self._match_text:
            option.palette.setColor(QPalette.ColorRole.Text, QColor("#4CAF50"))
            option.palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#4CAF50"))


class threadGetPhotoData(QThread):

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

            # pull the next job; exit cleanly when the queue is empty
            try:
                item = self.workQueue.get_nowait()
            except queue.Empty:
                break

            row = item[0]
            file = item[1]

            # read EXIF once and share it across the metadata functions
            try:
                exif_dict = piexif.load(file)
            except:
                exif_dict = {}

            photoData = self.parent.mdiParent.db.getPhotoData(file, exif_dict)

            if self.parent.photosAlreadyInDb:
                # Catalog photos already carry their assignment (the stored
                # sighting, stashed in the parent's _rowContext), so no
                # matchPhoto / combo-data work — just the EXIF display data
                # and the thumbnail.
                thisPhotoDataEntry = defaultdict()
                thisPhotoDataEntry["row"] = row
                thisPhotoDataEntry["photoData"] = photoData
                thisPhotoDataEntry["image"] = self.parent.GetImageForThumbnail(file)
                self.resultQueue.put(thisPhotoDataEntry)
                self.workQueue.task_done()
                continue

            photoMatchData = self.parent.mdiParent.db.matchPhoto(file, exif_dict)
            # QImage only in worker threads — QPixmap is a GUI-thread-only
            # class; the main thread converts when it builds the row.
            image = self.parent.GetImageForThumbnail(file)

            # Pre-compute combo box data in the worker thread so the main
            # thread can populate widgets without querying the database.
            # Photos from the same checklist share identical combo data, so
            # memoize by (date, location, time) — a typical bulk import spans
            # hundreds of photos but only a handful of checklists, and these
            # pure-Python database scans are serialized by the GIL regardless
            # of the thread count.
            key = (photoMatchData["photoDate"],
                   photoMatchData["photoLocation"],
                   photoMatchData["photoTime"])
            with self.parent._comboCacheLock:
                comboData = self.parent._comboCache.get(key)
            if comboData is None:
                comboData = self.parent.mdiParent.db.getComboDataForPhoto(
                    photoMatchData, allDates=self.parent._allDates)
                with self.parent._comboCacheLock:
                    self.parent._comboCache[key] = comboData

            thisPhotoDataEntry = defaultdict()
            thisPhotoDataEntry["row"] = row
            thisPhotoDataEntry["photoData"] = photoData
            thisPhotoDataEntry["photoMatchData"] = photoMatchData
            thisPhotoDataEntry["image"] = image
            thisPhotoDataEntry["comboData"] = comboData

            self.resultQueue.put(thisPhotoDataEntry)
            self.workQueue.task_done()

        self.sigThreadFinished.emit()
        


class ManagePhotos(QMdiSubWindow, form_ManagePhotos.Ui_frmManagePhotos):
    
    # create "resized" as a signal that the window can emit
    # we respond to this signal with the form's resizeMe method below
    resized = Signal()
    contentReady = Signal()   # all rows built — a hidden window can be revealed


    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose,True)
        self.mdiParent = ""
        self.resized.connect(self.resizeMe)        
        self.filter = ()
        self.fillingCombos = False
        self.btnSavePhotoSettings.clicked.connect(self.savePhotoSettings)
        self.btnCancel.clicked.connect(self.closeWindow)
        self.metaDataByRow = {}
        # Per-row widget references for the label/Select/Skip panel.
        self._rowLabels = {}
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.photosAlreadyInDb = True
        self._changesSaved = False
        self._skipCloseGuard = False
        # Files this save dropped from the catalog, broadcast from closeEvent
        self._departedPhotoFiles = set()
                
        # dynamic thread pool — sized to CPU count, capped at 8 for disk-bound work
        self.threadCount = min(os.cpu_count() or 4, 8)
        self.workQueue = queue.Queue()
        self.resultQueue = queue.Queue()
        self.threadsRemaining = 0
        self.threads = []
        self._loadedCount = 0
        self._totalFiles = 0
        self._threadsToStart = 0
        # Shared combo-data memo for the worker threads (see threadGetPhotoData.run)
        self._comboCache = {}
        self._comboCacheLock = threading.Lock()
        self._allDates = None
        # row -> (sighting, photo dict) for the catalog (by-filter) path
        self._rowContext = {}

        # One container widget per row in a QVBoxLayout — same fix as the
        # Photos browser: QGridLayout tops out around ~524k px of total
        # height, so past ~1,500 rows it silently compresses them (squished
        # thumbnails).  The Designer grid (gridPhotos) is left unused.
        self.rowsLayout = QVBoxLayout()
        self.rowsLayout.setContentsMargins(8, 6, 8, 6)   # gutters frame the cards
        self.rowsLayout.setSpacing(6)
        self.verticalLayout_3.addLayout(self.rowsLayout)
        self._rowWidgets = {}
        self._rowOrder = []   # sorted row numbers currently in rowsLayout

        for _ in range(self.threadCount):
            t = threadGetPhotoData()
            t.parent = self
            t.workQueue = self.workQueue
            t.resultQueue = self.resultQueue
            t.sigThreadFinished.connect(self.threadFinished)
            self.threads.append(t)

        # Timer drains resultQueue in the main thread at regular intervals,
        # keeping the event loop free so Cocoa can flush the display normally.
        self._drainTimer = QTimer(self)
        self._drainTimer.timeout.connect(self._drainResultQueue)
        
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_camera_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon) 


    def closeEvent(self, event):
        if (not self._skipCloseGuard and
                not self._changesSaved and
                not self.photosAlreadyInDb and
                self.metaDataByRow):
            reply = code_Stylesheet.question(
                self, "Unsaved Photos",
                "Your photo information has not been saved to a catalog.\n\n"
                "Close anyway and discard your work?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
                yes_text="Close and discard", no_text="Keep working",
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

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
        if self._changesSaved:
            # Departures first, so windows drop (and close on) photos that have
            # left the catalog; then re-query the browse grids for everything
            # else the save changed; then let the reports refresh once.
            # exclude=self: this window is mid-close and still in subWindowList().
            self.mdiParent.broadcastMediaRemovals(
                photoFiles=self._departedPhotoFiles, exclude=self)
            self.mdiParent.refreshOpenPhotos()
            self.mdiParent.notifyMediaChanged()
        super(self.__class__, self).closeEvent(event)

    def resizeEvent(self, event):
        # routine to handle resize event
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)
        
            
    def resizeMe(self):

        windowWidth = self.width()-10
        windowHeight = self.height()     
        self.scrollArea.setGeometry(5, 27, windowWidth-5, windowHeight-105)
        self.layLists.setGeometry(0, 0, windowWidth-5, windowHeight-100)
        self.btnCancel.setGeometry(10, windowHeight - 50, 100, 35)
        self.btnSavePhotoSettings.setGeometry(windowWidth - 160, windowHeight - 50, 150, 35)
   
   
    def scaleMe(self):
       
        fontSize = self.mdiParent.fontSize
        scaleFactor = self.mdiParent.scaleFactor
             
        #scale the font for all widgets in window
        for w in self.children():
            try:
                w.setFont(QFont(YBFont, fontSize))
            except:
                pass
                        
        for c in self.layLists.children():
            if "QLabel" in str(c):
                c.setFont(QFont(YBFont, fontSize))
         
        # Thumbnail (333) + text column + fixed controls column (160), plus a
        # little breathing room: wide enough that filenames rarely wrap,
        # without a band of blank space between the file info and the buttons.
        windowWidth =  int(1045  * scaleFactor)
        windowHeight = int(800 * scaleFactor)
        self.resize(windowWidth, windowHeight)


    def FillPhotosByFiles(self, files): 
        
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        # set flag so other routines will know that we're adding new files to db
        self.photosAlreadyInDb = False
        
        # create list to hold names of allowable files, including jpgs and tiffs
        # we'll be adding these files to the db once the user provides the meta data for them
        allowedPhotoFiles = []
        
        # remove non-image files from the list
        row = 0
        for fileName in files:

            # get file extension to process only jpg and tiff image files
            photoFileExtension = os.path.splitext(fileName)[1]

            # only process jpg and tiff files
            if photoFileExtension.lower() in [".jpg", ".jpeg", ".tif", "tiff"]:

                allowedPhotoFiles.append([row, fileName])

            row += 1

        # The full date list is identical for every photo; compute it once here
        # instead of once per photo inside getComboDataForPhoto (a whole-database
        # scan that the GIL serializes across the worker threads).
        self._allDates = self.mdiParent.db.GetDates(code_Filter.Filter())
        self._comboCache.clear()

        # fill the shared work queue; threads pull jobs from it dynamically
        # so no thread sits idle while others still have work
        for item in allowedPhotoFiles:
            self.workQueue.put(item)

        self._totalFiles = len(allowedPhotoFiles)
        self._loadedCount = 0
        self._threadsToStart = min(self.threadCount, len(allowedPhotoFiles))
        self.threadsRemaining = self._threadsToStart

        # Gated main-window progress overlay, as in the Photos browser: it only
        # becomes visible if the load runs longer than the gate, so small
        # batches never flash a progress bar.
        overlay = self.mdiParent.progressOverlay
        overlay.armGate(1000)
        overlay.showForPhotos()
        overlay.startLoading(self._totalFiles)

        # Defer thread start until the event loop regains control so the UI
        # is fully laid out before loading begins.
        QTimer.singleShot(0, self._startThreads)
                
    
    def _startThreads(self):
        for i in range(self._threadsToStart):
            self.threads[i].start()
        self._drainTimer.start(50)

    def _drainResultQueue(self):
        prevCount = self._loadedCount

        # Time-budgeted drain: with warm caches the workers produce results
        # faster than the main thread can build rows, so an unbounded drain
        # never sees an empty queue — this one callback would then block the
        # event loop until EVERY row was built (beachball; the progress bar's
        # first paint would be the finished count).  200ms chunks: long
        # enough that the between-chunk event-loop overhead is negligible,
        # short enough that the overlay stays live (~5 updates/s) and the app
        # never looks hung.
        deadline = time.monotonic() + 0.200
        while time.monotonic() < deadline:
            try:
                entry = self.resultQueue.get_nowait()
            except queue.Empty:
                break

            if self.photosAlreadyInDb:
                self.insertExistingPhotoIntoTable(
                    entry["row"],
                    entry["photoData"],
                    QPixmap.fromImage(entry["image"]),
                )
            else:
                self.insertPhotoIntoTable(
                    entry["row"],
                    entry["photoData"],
                    entry["photoMatchData"],
                    QPixmap.fromImage(entry["image"]),
                    entry["comboData"],
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
            # next 50ms tick — that idle time otherwise dominates the load.
            # The periodic timer stays as the backstop while the workers are
            # still producing.
            QTimer.singleShot(0, self._drainResultQueue)

    def _finishLoading(self):
        # Run once: the periodic timer and the singleShot continuations can
        # both deliver a final "queue empty" drain pass, and contentReady must
        # not re-fire (it re-shows the window — or worse, fires on a deleted
        # one).
        if getattr(self, "_loadFinished", False):
            return
        self._loadFinished = True
        # The reveal (contentReady → show) blocks for a few seconds on large
        # sets while Qt lays out and polishes the whole never-shown widget
        # tree.  A "Building the display…" overlay phase was tried here and
        # removed: the block freezes all painting (including the overlay's
        # busy animation), so it read as a hang — a short gap after the
        # progress bar completes is the better experience.
        self.scrollArea.verticalScrollBar().setValue(0)
        self.mdiParent.progressOverlay.hide()
        QApplication.restoreOverrideCursor()
        self.contentReady.emit()

    def threadFinished(self):
        self.threadsRemaining -= 1
              
                                
                                 
    def _addRowWidget(self, row, buttonPhoto, container):
        """Wrap one photo row (thumbnail + details) in a container widget and
        insert it into rowsLayout at its ordered position.  Worker results
        arrive out of order, and a QVBoxLayout (unlike the old grid) has no
        row indices of its own, so the position is found by bisecting the
        sorted list of rows already present."""
        rowWidget = QWidget()
        # Shared media-card background (see code_Stylesheet), matching the
        # Browse views; children are transparent over it.
        rowWidget.setObjectName("mediaCard")
        rowWidget.setAttribute(Qt.WA_StyledBackground, True)
        rowWidget.setMinimumHeight(_THUMB_DISPLAY_H)
        rowLayout = QHBoxLayout(rowWidget)
        rowLayout.setContentsMargins(6, 6, 6, 6)   # inset content off the rounded corners
        rowLayout.setSpacing(2)
        rowLayout.addWidget(buttonPhoto)
        rowLayout.addWidget(container, 1)   # details absorb the extra width

        pos = bisect.bisect_left(self._rowOrder, row)
        self._rowOrder.insert(pos, row)
        self.rowsLayout.insertWidget(pos, rowWidget)
        self._rowWidgets[row] = rowWidget


    def insertPhotoIntoTable(self, row, photoData, photoMatchData, pixMap, comboData):

        # No processEvents here: on a visible window it forced a full relayout
        # and repaint of the whole growing grid for EVERY row (O(N²) for large
        # imports).  The window stays hidden until contentReady, and the 50ms
        # drain timer keeps the event loop responsive between batches.
        self.fillingCombos = True
                                                                    
        photoLocation = photoMatchData["photoLocation"]
        photoDate = photoMatchData["photoDate"]
        photoTime = photoMatchData["photoTime"]
        photoCommonName = photoMatchData["photoCommonName"]
                            
        # p is a filename. Use it to add the image to the label as a pixmap
        buttonPhoto = QPushButton()
        buttonPhoto.setMinimumHeight(_THUMB_DISPLAY_H)
        # Fixed (not minimum) width pins the thumbnail column: any extra
        # window width goes to the details column, as in Manage Recordings.
        buttonPhoto.setFixedWidth(_THUMB_DISPLAY_W)

        buttonPhoto.setIcon(QIcon(pixMap))

        buttonPhoto.setIconSize(QSize(_THUMB_DISPLAY_W, _THUMB_DISPLAY_H))
        buttonPhoto.setObjectName("mediaThumbBtn")   # styled via the app sheet

        # set up layout in second column of row to house combo boxes
        # give each object a name according to the row so we can access them later
        # (built DETACHED; inserted into the live layout only when complete —
        # inserting first makes every subsequent widget insertion propagate
        # styles/fonts through the live hierarchy one widget at a time)
        container = QWidget()
        container.setObjectName("cardTransparent")
        detailsLayout = QVBoxLayout(container)
        detailsLayout.setObjectName("layout" + str(row))
        detailsLayout.setAlignment(Qt.AlignTop)

        # Seed this row's working metadata, then build the colour-coded label /
        # Select / Skip panel from it.  Date, location, time and species are now
        # shown as labels and edited via the checklist tree picker.
        thisPhotoMetaData = {}
        thisPhotoMetaData["location"] = photoLocation
        thisPhotoMetaData["date"] = photoDate
        thisPhotoMetaData["time"] = photoTime
        thisPhotoMetaData["commonName"] = photoCommonName
        thisPhotoMetaData["photoData"] = photoData
        thisPhotoMetaData["rating"] = photoData["rating"]
        thisPhotoMetaData["notes"] = photoData.get("notes", "")
        thisPhotoMetaData["cascadeMode"] = "date_first"
        thisPhotoMetaData["selectedCommonName"] = photoCommonName
        thisPhotoMetaData["skip"] = False
        thisPhotoMetaData["newLocation"] = photoLocation
        thisPhotoMetaData["newDate"] = photoDate
        thisPhotoMetaData["newTime"] = photoTime
        thisPhotoMetaData["newCommonName"] = photoCommonName
        # Auto-derived baseline: a field shows green only while it still equals
        # this metadata/filename-derived value.
        thisPhotoMetaData["autoDate"] = photoDate
        thisPhotoMetaData["autoLocation"] = photoLocation
        thisPhotoMetaData["autoTime"] = photoTime
        thisPhotoMetaData["autoSpecies"] = photoCommonName
        thisPhotoMetaData["autoGreen"] = self._computeAutoGreen(photoMatchData)
        self.metaDataByRow[row] = thisPhotoMetaData

        self._buildDetailsPanel(row, detailsLayout, photoData, isExisting=False)
        # panel complete — insert thumbnail + details as one ordered row
        self._addRowWidget(row, buttonPhoto, container)
        self.saveNewMetaData(row)

        self.fillingCombos = False


    def FillPhotosByFilter(self, filter):

        # These photos already carry a confirmed assignment (their stored
        # sighting), so the workers skip matchPhoto and combo data (see
        # threadGetPhotoData.run); the sighting context for each row is
        # stashed in _rowContext for the drain to use when building the row.
        # Rows build asynchronously into the (still hidden) window;
        # contentReady fires when it can be revealed.

        self.scaleMe()
        self.resizeMe()

        # save the filter settings passed to this routine to the form itself for future use
        self.filter = filter

        photoSightings = self.mdiParent.db.GetSightingsWithPhotos(filter)

        if len(photoSightings) == 0:
            return False

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        self.setWindowTitle("Manage Photos")

        # one job per photo; workers pull from the shared queue dynamically
        row = 0
        for s in photoSightings:
            for p in s["photos"]:
                self._rowContext[row] = (s, p)
                self.workQueue.put([row, p["fileName"]])
                row += 1

        self._totalFiles = row
        self._loadedCount = 0
        self._threadsToStart = min(self.threadCount, self._totalFiles)
        self.threadsRemaining = self._threadsToStart

        # Gated main-window progress overlay, as in the Photos browser: it only
        # becomes visible if the load runs longer than the gate, so small
        # sets never flash a progress bar.
        overlay = self.mdiParent.progressOverlay
        overlay.armGate(1000)
        overlay.showForPhotos()
        overlay.startLoading(self._totalFiles)

        QTimer.singleShot(0, self._startThreads)

        # tell MainWindow that we succeeded filling the list
        return(True)


    def FillSinglePhoto(self, photoData, sightingData):
        """Show exactly one known photo, bypassing the filter-driven query —
        used by the Enlargement window's "Edit species or location
        assignment…", where only the photo on screen should be editable.

        Takes the same path as FillPhotosByFilter (the photo already carries a
        confirmed assignment, so _rowContext supplies the sighting and the
        worker skips matchPhoto), just with one job on the queue instead of
        one per photo in a filter."""
        self.scaleMe()
        self.resizeMe()

        # A real Filter, not the built-in filter(): other methods call
        # self.filter's accessors, and the window title is built from it.
        self.filter = code_Filter.Filter()
        self.filter.setSpeciesName(sightingData["commonName"])
        self.filter.setLocationName(sightingData["location"])
        self.filter.setLocationType("Location")
        self.filter.setStartDate(sightingData["date"])
        self.filter.setEndDate(sightingData["date"])

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        self.setWindowTitle("Manage Photos")

        self._rowContext[0] = (sightingData, photoData)
        self.workQueue.put([0, photoData["fileName"]])

        self._totalFiles = 1
        self._loadedCount = 0
        self._threadsToStart = 1
        self.threadsRemaining = 1

        overlay = self.mdiParent.progressOverlay
        overlay.armGate(1000)
        overlay.showForPhotos()
        overlay.startLoading(self._totalFiles)

        QTimer.singleShot(0, self._startThreads)

        return True


    def insertExistingPhotoIntoTable(self, row, photoData, pixMap):
        """Build one row for a photo already in the catalog.  Its assignment is
        known from the stored sighting (stashed in _rowContext), so every field
        is a direct match — no guessing and no combo data."""

        self.fillingCombos = True

        s, p = self._rowContext[row]

        buttonPhoto = QPushButton()
        buttonPhoto.setMinimumHeight(_THUMB_DISPLAY_H)
        # Fixed width pins the thumbnail column (see insertPhotoIntoTable)
        buttonPhoto.setFixedWidth(_THUMB_DISPLAY_W)
        buttonPhoto.setIcon(QIcon(pixMap))
        buttonPhoto.setIconSize(QSize(_THUMB_DISPLAY_W, _THUMB_DISPLAY_H))
        buttonPhoto.setObjectName("mediaThumbBtn")   # styled via the app sheet

        # set up layout in second column of row to house combo boxes
        # give each object a name according to the row so we can access them later
        container = QWidget()
        container.setObjectName("cardTransparent")
        detailsLayout = QVBoxLayout(container)
        detailsLayout.setObjectName("layout" + str(row))
        detailsLayout.setAlignment(Qt.AlignTop)

        # Existing-photo rows already hold a confirmed assignment, so
        # every field is a direct match.  Seed metadata and build the
        # colour-coded label / Select / Skip panel.
        thisPhotoMetaData = {}
        thisPhotoMetaData["location"] = s["location"]
        thisPhotoMetaData["date"] = s["date"]
        thisPhotoMetaData["time"] = s["time"]
        thisPhotoMetaData["commonName"] = s["commonName"]
        thisPhotoMetaData["photoData"] = p
        thisPhotoMetaData["rating"] = p["rating"]
        thisPhotoMetaData["notes"] = p.get("notes", "")
        thisPhotoMetaData["cascadeMode"] = "location_first"
        thisPhotoMetaData["selectedCommonName"] = s["commonName"]
        thisPhotoMetaData["skip"] = False
        thisPhotoMetaData["newLocation"] = s["location"]
        thisPhotoMetaData["newDate"] = s["date"]
        thisPhotoMetaData["newTime"] = s["time"]
        thisPhotoMetaData["newCommonName"] = s["commonName"]
        # The stored assignment is the auto-derived baseline; every
        # field is green until the user overrides it via the tree.
        thisPhotoMetaData["autoDate"] = s["date"]
        thisPhotoMetaData["autoLocation"] = s["location"]
        thisPhotoMetaData["autoTime"] = s["time"]
        thisPhotoMetaData["autoSpecies"] = s["commonName"]
        thisPhotoMetaData["autoGreen"] = {"date": True, "location": True,
                                          "time": True, "species": True}
        self.metaDataByRow[row] = thisPhotoMetaData

        # Pass the EXIF photoData (not the catalog dict p) so the
        # "Photographed" line can show the capture date/time.
        self._buildDetailsPanel(row, detailsLayout, photoData, isExisting=True)
        # panel complete — insert thumbnail + details as one ordered row
        self._addRowWidget(row, buttonPhoto, container)
        self.saveNewMetaData(row)

        self.fillingCombos = False


    def GetImageForThumbnail(self, photoFile):
        """Return a 500x330-bounded, EXIF-oriented QImage thumbnail.

        Thread-safe (QImage only — QPixmap must stay on the GUI thread).
        Fast path is the on-disk thumbnail cache shared with the Photos
        browser; on a miss, decode through the cache module's scaled decode
        (large JPEGs are never fully decoded) and store the result, priming
        the browser's cache for later.  The old code preferred the tiny EXIF
        embedded thumbnail here and upscaled it to 500px — fast, but blurry,
        and it poisoned the shared cache with that blurry image.
        """
        cached = code_ThumbnailCache.load(photoFile)
        if cached is not None and not cached.isNull():
            return cached

        image = code_ThumbnailCache.decode_thumbnail(photoFile)
        if not image.isNull():
            code_ThumbnailCache.store(photoFile, image)
        return image


    def _computeAutoGreen(self, md):
        """Which fields were confirmed directly from the photo's metadata /
        filename.  Only these are eligible to show green (and only while the
        user hasn't overridden them).  A best-guess fallback is not "gleaned"
        and stays neutral.

        date     – the EXIF date matched a checklist date
        time     – the EXIF time matched a checklist time exactly
        location – confirmed only when the exact checklist (date+time) matched
        species  – a species was recognised in the filename
        """
        dmf = md.get("dateMatchFound", False)
        tmf = md.get("timeMatchFound", False)
        return {
            "date":     dmf,
            "time":     tmf,
            "location": tmf,
            "species":  bool(md.get("photoCommonName", "")),
        }

    def _fieldGreen(self, md, field):
        """A field shows green only if it was auto-derived AND its current value
        still equals that auto-derived value (i.e. the user hasn't changed it)."""
        if not md.get("autoGreen", {}).get(field, False):
            return False
        current = {
            "date":     md.get("newDate", ""),
            "location": md.get("newLocation", ""),
            "time":     md.get("newTime", ""),
            "species":  md.get("selectedCommonName", ""),
        }[field]
        auto = {
            "date":     md.get("autoDate", ""),
            "location": md.get("autoLocation", ""),
            "time":     md.get("autoTime", ""),
            "species":  md.get("autoSpecies", ""),
        }[field]
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

    def _buildDetailsPanel(self, row, detailsLayout, photoData, isExisting):
        """Minimalist row panel: filename, four colour-coded assignment labels,
        and a right-hand Select / Skip / Rating / Reset column.  Date, location,
        time and species are chosen via the checklist tree picker."""
        lbls = {}
        self._rowLabels[row] = lbls

        bodyRow = QHBoxLayout()
        bodyRow.setSpacing(14)

        # Left column: filename on top (level with the Select button), then the
        # four colour-coded assignment labels.
        leftCol = QVBoxLayout()
        leftCol.setSpacing(4)
        lblFileName = QLabel(_wrappable(os.path.basename(photoData["fileName"])))
        lblFileName.setStyleSheet("color: %s;" % _FIELD_NAME_COLOR)
        lblFileName.setWordWrap(True)
        leftCol.addWidget(lblFileName)

        # The photo's own EXIF capture date/time, shown so the user can judge how
        # to assign it.
        exifDate = photoData.get("date", "")
        exifTime = photoData.get("time", "")
        if exifDate and exifDate != "Date unknown":
            metaStr = "Photographed %s" % exifDate
            if exifTime and exifTime != "Time unknown":
                metaStr += " %s" % exifTime
        else:
            metaStr = "Photo date unknown"
        lblMeta = QLabel(metaStr)
        lblMeta.setStyleSheet("color: %s;" % _FIELD_NAME_COLOR)
        lblMeta.setWordWrap(True)
        leftCol.addWidget(lblMeta)
        leftCol.addSpacing(10)   # line feed after the metadata line

        for key in ("date", "location", "time", "species"):
            lbl = QLabel()
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setWordWrap(True)
            lbls[key] = lbl
            leftCol.addWidget(lbl)
        leftCol.addStretch()
        bodyRow.addLayout(leftCol, 1)

        # Right column, top-to-bottom: Select (aligned with the filename),
        # Reset, the Rating label/combo, then the Remove/Skip checkbox — with a
        # few pixels of breathing room between each control.
        controlsCol = QVBoxLayout()
        controlsCol.setSpacing(8)

        # Pin every control to one explicit font so the combo text can't end up a
        # different size from the buttons (they otherwise resolve fonts via
        # different inheritance paths).
        _panelFont = QFont(YBFont, getattr(self.mdiParent, "fontSize", 11))

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
        # Centre the displayed text: a non-editable combo's closed text is drawn
        # left-aligned by the style, so use a read-only, centred line edit for the
        # display and centre the popup items too.
        cboRating.setEditable(True)
        cboRating.lineEdit().setReadOnly(True)
        cboRating.lineEdit().setAlignment(Qt.AlignCenter)
        cboRating.lineEdit().setFocusPolicy(Qt.NoFocus)
        cboRating.lineEdit().setFont(_panelFont)
        # Left padding offsets the dropdown arrow on the right so the text sits
        # centred under the full control rather than the area left of the arrow.
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
        # Added directly to the column so it spans the full button width.
        controlsCol.addWidget(cboRating)

        chkSkip = QCheckBox("Remove" if isExisting else "Skip")
        chkSkip.setFont(_panelFont)
        chkSkip.toggled.connect(partial(self._toggleSkip, row))
        lbls["skip"] = chkSkip
        controlsCol.addWidget(chkSkip)

        controlsCol.addStretch()
        # Hold the control column to a fixed width wide enough that "Not Rated"
        # plus the dropdown arrow and centring padding fit without clipping.
        controlsWidget = QWidget()
        controlsWidget.setObjectName("cardTransparent")
        controlsWidget.setLayout(controlsCol)
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
        if skipped:
            note = "Will be removed" if self.photosAlreadyInDb else "Will be skipped"
            lbls["species"].setText(self._fieldHtml("Species", note, False, True))
        elif md.get("selectedCommonName"):
            lbls["species"].setText(self._fieldHtml(
                "Species", md["selectedCommonName"], self._fieldGreen(md, "species"), False))
        else:
            lbls["species"].setText(
                '<span style="color:%s">Click Select to choose a species</span>'
                % _NO_SPECIES_COLOR)

    def _openSelectTree(self, row):
        md = self.metaDataByRow[row]
        dlg = code_ChecklistTree.ChecklistTreeDialog(self.mdiParent.db, self)
        dlg.expand_to(md.get("newDate", ""), md.get("newLocation", ""),
                      md.get("newTime", ""), md.get("selectedCommonName", ""))
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
        md["newDate"] = result["date"]
        md["newLocation"] = result["location"]
        md["newTime"] = result["time"]
        md["selectedCommonName"] = result["species"]
        md["newCommonName"] = result["species"]
        md["skip"] = False
        # Greenness is derived by comparing each field to its auto baseline, so
        # any field the tree changed automatically drops to the neutral colour.
        chk = self._rowLabels.get(row, {}).get("skip")
        if chk is not None:
            chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(False)
        self._refreshRowLabels(row)
        self.saveNewMetaData(row)

    def _toggleSkip(self, row, checked):
        md = self.metaDataByRow[row]
        md["skip"] = checked
        if checked:
            md["newCommonName"] = _SKIP_SENTINEL
        else:
            md["newCommonName"] = md.get("selectedCommonName", "")
        self._refreshRowLabels(row)
        self.saveNewMetaData(row)

    def cboRatingChanged(self, row, _index=None):
        if self.fillingCombos:
            return
        self.saveNewMetaData(row)

    def saveNewMetaData(self, row):
        md = self.metaDataByRow[row]
        md.setdefault("newLocation", md["location"])
        md.setdefault("newDate", md["date"])
        md.setdefault("newTime", md["time"])
        md.setdefault("newCommonName", md["commonName"])
        md.setdefault("newNotes", md.get("notes", ""))
        cbo = self._rowLabels.get(row, {}).get("rating")
        if cbo is not None:
            md["newRating"] = str(cbo.currentIndex())
        else:
            md.setdefault("newRating", str(md.get("rating", "0")))

    def btnResetClicked(self, row):
        md = self.metaDataByRow[row]
        md["newLocation"] = md["location"]
        md["newDate"] = md["date"]
        md["newTime"] = md["time"]
        md["selectedCommonName"] = md["commonName"]
        md["newCommonName"] = md["commonName"]
        md["newNotes"] = md.get("notes", "")
        md["skip"] = False
        lbls = self._rowLabels.get(row, {})
        chk = lbls.get("skip")
        if chk is not None:
            chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(False)
        cbo = lbls.get("rating")
        if cbo is not None:
            try:
                cbo.setCurrentIndex(max(0, min(5, int(md["rating"]))))
            except (TypeError, ValueError):
                cbo.setCurrentIndex(0)
        self._refreshRowLabels(row)
        self.saveNewMetaData(row)


    def savePhotoSettings(self):

        if not self.photosAlreadyInDb and not self.mdiParent.db.photoDataFileOpenFlag:
            msg = QMessageBox(self)
            msg.setWindowTitle("No Media Catalog Open")
            msg.setText(
                "You need to create a media catalog file for Yearbirder to save "
                "your photo information.\n\n"
                "A media catalog is a file that stores the species, checklist, and "
                "rating data for each of your bird photos. Without one, your work "
                "here cannot be saved to disk.\n\n"
                "Would you like to create a new catalog file now, or go back and "
                "continue working?"
            )
            create_btn  = msg.addButton("Create Catalog…", QMessageBox.ButtonRole.AcceptRole)
            go_back_btn = msg.addButton("Go Back",             QMessageBox.ButtonRole.RejectRole)
            discard_btn = msg.addButton("Discard Work",        QMessageBox.ButtonRole.DestructiveRole)
            msg.setDefaultButton(create_btn)
            msg.exec()

            clicked = msg.clickedButton()
            if clicked is discard_btn:
                self._skipCloseGuard = True
                self.close()
                return
            elif clicked is not create_btn:
                return  # Go Back — window stays open

            # Create Catalog path
            initial_dir = self.mdiParent.db.startupFolder or os.path.expanduser("~")
            fname, _ = QFileDialog.getSaveFileName(
                self,
                "Create Media Catalog File",
                os.path.join(initial_dir, "Yearbirder_MediaCatalog.jsonl"),
                "Yearbirder Media Catalog (*.jsonl)",
            )
            if not fname:
                return  # user cancelled the save dialog — stay open
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

        # Collect files successfully added so their thumbnails can be cached.
        added_photo_files = set()
        # Photos stripped from the catalog this save; those not re-added get their
        # on-disk cache evicted below.
        removed_photo_files = set()

        # call database function to remove modified photos from db.
        # Iterate the metadata dict (not layout row counts): rows deleted via
        # handlePhotoDeletion leave gaps in the numbering.
        for r in sorted(self.metaDataByRow):

            # check if we're processing photos new to the db or ones already in the db
            if self.photosAlreadyInDb is True:
                
                # since photos are already in db, we remove them before adding them back with new meta data
                # only remove ones whose data has changed
                metaDataChanged = False
                if self.metaDataByRow[r]["location"] != self.metaDataByRow[r]["newLocation"]:
                    metaDataChanged = True
                if self.metaDataByRow[r]["date"] != self.metaDataByRow[r]["newDate"]:
                    metaDataChanged = True
                if self.metaDataByRow[r]["time"] != self.metaDataByRow[r]["newTime"]:
                    metaDataChanged = True
                if self.metaDataByRow[r]["commonName"] != self.metaDataByRow[r]["newCommonName"]:
                    metaDataChanged = True  
                if self.metaDataByRow[r]["rating"] != self.metaDataByRow[r]["newRating"]:
                    metaDataChanged = True
                if self.metaDataByRow[r]["notes"] != self.metaDataByRow[r]["newNotes"]:
                    metaDataChanged = True

                if metaDataChanged is True:
                    # remove the photo from the database
                    self.mdiParent.db.removePhotoFromDatabase(
                        self.metaDataByRow[r]["location"],
                        self.metaDataByRow[r]["date"],
                        self.metaDataByRow[r]["time"],
                        self.metaDataByRow[r]["commonName"],
                        self.metaDataByRow[r]["photoData"]["fileName"])
                    removed_photo_files.add(self.metaDataByRow[r]["photoData"]["fileName"])
                
                # check whether we're not removing this photo from db
                # set flag to True, and then set it to False if non-write conditions exist
                attachPhoto = True
                
                if self.metaDataByRow[r]["commonName"] != self.metaDataByRow[r]["newCommonName"]:
                    if "**" in self.metaDataByRow[r]["newCommonName"]:
                        attachPhoto = False
                    
                if attachPhoto is True:
                    # Add the photo to the database using its new settings
                    filter = code_Filter.Filter()
                                        
                    # use the new values for the filter to save the photo
                    filter.setLocationName(self.metaDataByRow[r]["newLocation"])
                    filter.setLocationType("Location")                    
                    filter.setStartDate(self.metaDataByRow[r]["newDate"])
                    filter.setEndDate(self.metaDataByRow[r]["newDate"])
                    filter.setTime(self.metaDataByRow[r]["newTime"])
                    filter.setSpeciesName(self.metaDataByRow[r]["newCommonName"])
                    
                    self.metaDataByRow[r]["photoData"]["rating"] = self.metaDataByRow[r]["newRating"]
                    self.metaDataByRow[r]["photoData"]["notes"] = self.metaDataByRow[r]["newNotes"]

                    s = self.mdiParent.db.addPhotoToDatabase(filter, self.metaDataByRow[r]["photoData"])
                    if s:
                        added_photo_files.add(self.metaDataByRow[r]["photoData"]["fileName"])
                        try:
                            self.mdiParent.db.appendPhotoToJsonl(s, self.metaDataByRow[r]["photoData"])
                        except IOError as exc:
                            QMessageBox.warning(self, "Settings File Error",
                                f"Photo saved in memory but could not be written to the media catalog:\n{exc}")

            if self.photosAlreadyInDb is False:
            
                # we're processing photo files that aren't yet in the db, so add them
                # Add the photo to the database using its new settings
                                
                # set flag to True, and then set it to False if non-write conditions exist
                attachPhoto = True

                if "**" in self.metaDataByRow[r]["newCommonName"]:
                    attachPhoto = False
                         
                if self.metaDataByRow[r]["newCommonName"] == "":
                    attachPhoto = False
                            
                if attachPhoto is True:
                    
                    filter = code_Filter.Filter()
                                                            
                    # use the new values for the filter to save the photo
                    filter.setLocationName(self.metaDataByRow[r]["newLocation"])
                    filter.setLocationType("Location")                    
                    filter.setStartDate(self.metaDataByRow[r]["newDate"])
                    filter.setEndDate(self.metaDataByRow[r]["newDate"])
                    filter.setTime(self.metaDataByRow[r]["newTime"])
                    filter.setSpeciesName(self.metaDataByRow[r]["newCommonName"])
                    
                    self.metaDataByRow[r]["photoData"]["rating"] = self.metaDataByRow[r]["newRating"]
                    self.metaDataByRow[r]["photoData"]["notes"] = self.metaDataByRow[r]["newNotes"]

                    s = self.mdiParent.db.addPhotoToDatabase(filter, self.metaDataByRow[r]["photoData"])
                    if s:
                        added_photo_files.add(self.metaDataByRow[r]["photoData"]["fileName"])
                        try:
                            self.mdiParent.db.appendPhotoToJsonl(s, self.metaDataByRow[r]["photoData"])
                        except IOError as exc:
                            QMessageBox.warning(self, "Settings File Error",
                                f"Photo saved in memory but could not be written to the media catalog:\n{exc}")

        # Cache thumbnails for the added photos in the background so every
        # catalogued photo exists in the cache (skips ones already cached).
        if added_photo_files:
            code_ThumbnailCache.prebuild_async(photo_paths=added_photo_files)

        # Photos that left the catalog for good this save — removed and not
        # re-added (an edit removes then re-adds, so a rating or species change
        # is not a departure).  Their on-disk cache goes now, and closeEvent
        # tells the open windows: a Manage save is the same mutation as a
        # one-off removal, just in bulk, so it goes through the same handlers.
        self._departedPhotoFiles = {
            fn for fn in removed_photo_files
            if not self.mdiParent.db.isMediaFileReferenced(fn)
        }
        for fn in self._departedPhotoFiles:
            code_ThumbnailCache.evict(fn)

        if self.photosAlreadyInDb is False:

            # ensure that photo filter is visible, if we've added new photos.
            self.mdiParent.dckMediaFilter.setVisible(True)

            # update the photo filter's cbo boxes
            self.mdiParent.fillPhotoComboBoxes()

        # set flag indicating that some photo data isn't yet saved to file
        self.mdiParent.db.photosNeedSaving = True
        self.mdiParent._promptJsonlMigrationIfNeeded()
        
        self.mdiParent.db.refreshPhotoLists()

        self.mdiParent.fillPhotoComboBoxes()
        # Reveal the Photos menu if this added the first photo to the catalog.
        self.mdiParent._updateMediaMenuVisibility()
        self._changesSaved = True

        # close the window (closeEvent will refresh any open Stats windows)
        self.close()
        
        
    def handlePhotoDeletion(self, filename):
        """A photo left the catalog (or the file system) while this window was
        open — retire its row, so a save can't write back settings for media
        that is gone."""
        row = next((r for r, meta in self.metaDataByRow.items()
                    if meta["photoData"]["fileName"] == filename), None)
        if row is None:
            return
        rowWidget = self._rowWidgets.pop(row, None)
        if rowWidget is not None:
            self._rowOrder.remove(row)
            self.rowsLayout.removeWidget(rowWidget)
            rowWidget.hide()          # removeWidget leaves it parented and visible
            rowWidget.setParent(None)
            rowWidget.deleteLater()
        del self.metaDataByRow[row]
        self._rowLabels.pop(row, None)
        self._rowContext.pop(row, None)


    def closeWindow(self):

        self.close()


    def highlightWidget(self, w):
    
        red = str(code_Stylesheet.mdiAreaColor.red())
        blue = str(code_Stylesheet.mdiAreaColor.blue())
        green = str(code_Stylesheet.mdiAreaColor.green())
        w.setStyleSheet("QComboBox { background-color: rgb(" + red + "," + green + "," + blue + ")}")
         
    def removeHighlight(self, w):
        w.setStyleSheet("")

        
        
