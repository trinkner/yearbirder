# import project files
import form_Photos
from code_Stylesheet import YBFont
import code_Enlargement
import code_ThumbnailCache

import datetime
import os
import queue

# import basic Python libraries
from math import floor

from functools import partial

from PySide6.QtGui import (
    QPixmap,
    QFont,
    QIcon,
    )

from PySide6.QtCore import (
    Signal,
    Qt,
    QThread,
    QTimer,
    QByteArray,
    QBuffer,
    QIODevice,
    )

import base64

from PySide6.QtWidgets import (
    QMdiSubWindow,
    QLabel,
    QMessageBox,
    QProgressBar,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QApplication,
    )



class threadLoadThumbnail(QThread):
    """Worker thread that loads a scaled-down thumbnail for a single photo.

    Results are placed directly into a shared Python queue rather than emitted
    as Qt signals — this prevents the main thread's event queue from being
    flooded, which was starving the Cocoa display cycle and preventing the
    status bar from updating visually.
    """

    sigThreadFinished = Signal()

    def __init__(self):
        QThread.__init__(self)
        self.workQueue = None
        self.resultQueue = None   # Python queue shared with Photos

    def __del__(self):
        try:
            self.wait()
        except RuntimeError:
            pass

    def run(self):

        while True:

            # Block until work arrives, so the pool can be started up-front and
            # decode thumbnails in parallel while the grid is still being built.
            item = self.workQueue.get()
            if item is None:        # sentinel → no more work, exit cleanly
                break
            row, photoFile = item

            # Tier 2: on-disk thumbnail cache (tier 1 is the in-memory
            # pixmapCache, checked before a file is ever queued here).
            qimage = code_ThumbnailCache.load(photoFile)
            if qimage is None:
                # Tier 3: decode the source at reduced scale, then cache it.
                qimage = code_ThumbnailCache.decode_thumbnail(photoFile)
                if not qimage.isNull():
                    code_ThumbnailCache.store(photoFile, qimage)

            self.resultQueue.put((row, photoFile, qimage))

        self.sigThreadFinished.emit()


class Photos(QMdiSubWindow, form_Photos.Ui_frmPhotos):

    # create "resized" as a signal that the window can emit
    # we respond to this signal with the form's resizeMe method below
    resized = Signal()
    contentReady = Signal()   # grid built and thumbnails applied — reveal OK

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose,True)
        self.mdiParent = ""
        self.resized.connect(self.resizeMe)
        self.currentSpeciesList = []
        self.lblDetails.setVisible(False)
        self.filter = ()
        self.photoList = []
        self.pixmapCache = {}
        self._missingPhotoSpecies = set()
        # Qt caps a QGridLayout's total height at ~524k px, which squashes the
        # photo rows once there are more than ~1,600 photos.  Use a QVBoxLayout of
        # per-row widgets instead (no such cap until ~50k photos); the form's
        # gridPhotos is left unused.
        self.gridPhotos.setContentsMargins(0, 0, 0, 0)
        self.rowsLayout = QVBoxLayout()
        self.rowsLayout.setContentsMargins(8, 6, 8, 6)   # gutters frame the cards
        self.rowsLayout.setSpacing(6)
        self.verticalLayout_3.addLayout(self.rowsLayout)
        self.verticalLayout_3.addStretch(1)
        self._rowWidgets = {}
        self._abort = False
        self._sorting = False
        self._photoButtons = {}
        self.rdoSortSpecies.toggled.connect(lambda checked: self.SortAndDisplayPhotos() if checked else None)
        self.rdoSortDate.toggled.connect(lambda checked: self.SortAndDisplayPhotos() if checked else None)
        self.rdoSortRating.toggled.connect(lambda checked: self.SortAndDisplayPhotos() if checked else None)
        self.rdoSortTaxonomy.toggled.connect(lambda checked: self.SortAndDisplayPhotos() if checked else None)
        self.buttonSlideshow.clicked.connect(self.launchSlideshow)

        # dynamic thread pool sized to CPU count, capped at 8 for disk-bound work
        self.threadCount = min(os.cpu_count() or 4, 8)
        self.workQueue = queue.Queue()
        self.resultQueue = queue.Queue()
        self.threadsRemaining = 0
        self.threads = []

        for _ in range(self.threadCount):
            t = threadLoadThumbnail()
            t.workQueue = self.workQueue
            t.resultQueue = self.resultQueue
            t.sigThreadFinished.connect(self.thumbnailThreadFinished)
            self.threads.append(t)

        self._loadedCount = 0
        self._totalUncached = 0
        self._building = False   # True while the grid is being built (drain owns no overlay text then)

        # Timer drains resultQueue in the main thread at regular intervals.
        # Because no Qt signals are fired from worker threads, the event loop
        # stays idle between ticks and Cocoa can flush the display normally.
        self._drainTimer = QTimer(self)
        self._drainTimer.timeout.connect(self._drainResultQueue)


    def closeEvent(self, event):
        self._abort = True
        self._building = False
        self._drainTimer.stop()
        # Discard pending work, then sentinel each (blocking) worker so it exits
        # promptly after its current decode.
        try:
            while True:
                self.workQueue.get_nowait()
        except queue.Empty:
            pass
        for _ in range(self.threadCount):
            self.workQueue.put(None)
        # drain the result queue so nothing lingers
        while not self.resultQueue.empty():
            try:
                self.resultQueue.get_nowait()
            except queue.Empty:
                break
        self.mdiParent.progressOverlay.hide()
        self.mdiParent.db.compactJsonlFile()
        # Keep the on-disk thumbnail cache bounded (off the load path).
        code_ThumbnailCache.enforce_cap()
        super(self.__class__, self).closeEvent(event)


    def resizeEvent(self, event):
        #routine to handle events on objects, like clicks, lost focus, gained forcus, etc.
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)


    def resizeMe(self):

        windowWidth  = self.width() - 10
        windowHeight = self.height()
        headerHeight = max(self.headerFrame.sizeHint().height(), 60) + 16
        self.headerFrame.setGeometry(5, 27, windowWidth - 5, headerHeight)
        self.scrollArea.setGeometry(5, 27 + headerHeight, windowWidth - 5,
                                    windowHeight - 35 - headerHeight)


    def scaleMe(self):

        fontSize = self.mdiParent.fontSize
        scaleFactor = self.mdiParent.scaleFactor

        self.lblLocation.setFont(QFont(YBFont, fontSize))
        metrics = self.lblLocation.fontMetrics()
        cboText = self.lblLocation.text()
        if cboText == "":
            cboText = "Dummy Text"
        itemTextWidth = int(metrics.boundingRect(cboText).width())
        itemTextHeight = int(metrics.boundingRect(cboText).height())
        #scale the font for all widgets in window
        for w in self.children():
            try:
                w.setFont(QFont(YBFont, fontSize))
            except:
                pass

        self.lblLocation.setFont(QFont(YBFont, floor(fontSize * 1.4 )))
        self.lblLocation.setStyleSheet("QLabel { font: bold }");
        self.lblDateRange.setFont(QFont(YBFont, floor(fontSize * 1.2 )))
        self.lblDateRange.setStyleSheet("QLabel { font: bold }");
        self.lblDetails.setFont(QFont(YBFont, floor(fontSize * 1.2 )))
        self.lblDetails.setStyleSheet("QLabel { font: bold }");
        self.lblSpecies.setFont(QFont(YBFont, fontSize))
        self.lblSortBy.setFont(QFont(YBFont, fontSize))
        self.rdoSortSpecies.setFont(QFont(YBFont, fontSize))
        self.rdoSortDate.setFont(QFont(YBFont, fontSize))
        self.rdoSortRating.setFont(QFont(YBFont, fontSize))
        self.rdoSortTaxonomy.setFont(QFont(YBFont, fontSize))

        for c in self.layLists.findChildren(QLabel):
            c.setFont(QFont(YBFont, fontSize))

        windowWidth =  int(800  * scaleFactor)
        if len(self.photoList) == 1:
            windowHeight = int(400 * scaleFactor)
        else:
            windowHeight = int(800 * scaleFactor)

        self.resize(windowWidth, windowHeight)


    def html(self):
        # Heading from window title ("Photos: <filter details>")
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

        # Build one cell per photo with an embedded base64 image and caption.
        cells = []
        for p, s in self.photoList:
            if p["fileName"] in self.pixmapCache:
                pixmap = self.pixmapCache[p["fileName"]]
            else:
                pixmap = QPixmap(p["fileName"])

            if pixmap.isNull():
                self._missingPhotoSpecies.add(s["commonName"])
                continue

            pixmap = pixmap.scaled(540, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)

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

        # Lay out 6 photos per page: 2 columns × 3 rows.
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


    def FillPhotos(self, filter):

        self.scaleMe()
        self.resizeMe()
        self._missingPhotoSpecies = set()

        # save the filter settings passed to this routine to the form for future use
        self.filter = filter

        # Arm the time-based reveal gate, then prime the overlay.  It only becomes
        # visible if the whole operation runs longer than the threshold, so small
        # photo sets (instant on any machine) never flash a progress bar.
        overlay = self.mdiParent.progressOverlay
        overlay.armGate(1000)
        overlay.showForPhotos()
        QApplication.processEvents()

        # Phase 1 — query the catalog with a genuinely progressing bar so a large
        # unfiltered query no longer looks hung behind a static "Preparing" message.
        _dbShown = {"done": False}
        def _dbProgress(done, total):
            if not _dbShown["done"]:
                overlay.showDeterminate("Reading catalog…", total)
                _dbShown["done"] = True
            overlay.setProgress(done)
            QApplication.processEvents()

        photoSightings = self.mdiParent.db.GetSightingsWithPhotos(
            filter, progress_callback=_dbProgress)

        if len(photoSightings) == 0:
            overlay.hide()
            return False

        # Phase 2 — single pass over the matched photos: count species/photos for
        # the header AND build photoList (previously two passes over every photo).
        species = set()
        photoCount = 0
        self.photoList = []
        for i, s in enumerate(photoSightings):
            for p in s["photos"]:
                if self.mdiParent.db.TestIndividualPhoto(p, filter):
                    photoCount += 1
                    species.add(s["commonName"])
                    self.photoList.append([p, s])
            if self._abort:
                overlay.hide()
                return False
            if i % 200 == 0:
                QApplication.processEvents()

        self.lblSpecies.setText("Species: " + str(len(species)) + ". Photos: " + str(photoCount))
        self.mdiParent.SetChildDetailsLabels(self, filter)
        self.setWindowTitle(filter.buildWindowTitle("Photos", self.mdiParent.db, count=photoCount, countUnit="Photos"))

        # Sort and populate the grid (shows its own "Preparing photos…" progress)
        self._buildRows()

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_camera_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        # don't show if we don't have any photos to show
        if len(self.photoList) == 0:
            self.mdiParent.progressOverlay.hide()
            self.close()

        # resize to a smaller window if we only have one photo to show
        if len(self.photoList) == 1:
            self.scaleMe()

        # tell MainWindow that we succeeded filling the list
        return(True)


    def _sortPhotoList(self):
        """Sort photoList by the checked radio; returns the permutation
        (new position -> old index) so row widgets and bookkeeping can
        follow the data."""
        idx = range(len(self.photoList))
        if self.rdoSortSpecies.isChecked():
            order = sorted(idx, key=lambda i: self.photoList[i][1]["commonName"])
        elif self.rdoSortDate.isChecked():
            # Sort by the photo's own capture datetime (what the caption
            # shows), not the checklist's start time — photos on the same
            # checklist would otherwise all share one key and lose their
            # within-checklist time order.  Normalised to "YYYY-MM-DD HH:MM"
            # so EXIF-derived and checklist-fallback keys compare cleanly.
            def _capture_dt(i):
                p, s = self.photoList[i]
                dt = p.get("exifDatetime") or ""
                if len(dt) >= 16:
                    return (dt[0:4] + "-" + dt[5:7] + "-" + dt[8:10]
                            + " " + dt[11:16])
                return s.get("date", "") + " " + s.get("time", "")
            order = sorted(idx, key=_capture_dt)
        elif self.rdoSortRating.isChecked():
            def _rating(i):
                try:
                    return float(self.photoList[i][0]["rating"] or 0)
                except (ValueError, TypeError):
                    return 0.0
            order = sorted(idx, key=_rating, reverse=True)
        elif self.rdoSortTaxonomy.isChecked():
            order = sorted(idx, key=lambda i: (float(self.photoList[i][1]["taxonomicOrder"]),
                                               self.photoList[i][1]["commonName"]))
        else:
            order = list(idx)
        self.photoList = [self.photoList[i] for i in order]
        return order

    def SortAndDisplayPhotos(self):
        """Radio-button sort: reorder the EXISTING row widgets in place.

        Every row already holds its data and thumbnail, so a sort is just a
        permutation — no rebuild, no thumbnail reloads, no overlay.  Refused
        while the initial load is running (in-flight worker results are
        addressed to the old row numbers); falls back to a full build if the
        rows don't exist yet."""
        if not self.photoList:
            return
        if self._sorting or self._building or self.threadsRemaining > 0:
            return
        if not self._rowWidgets:
            self._buildRows()
            return
        self._sorting = True

        order = self._sortPhotoList()

        # Detach every row item from the layout (the widgets survive), then
        # re-insert them in the new order and remap the row-indexed
        # bookkeeping.  The click handlers carry baked-in row numbers, so
        # they are rebound to the rows' new positions.
        while self.rowsLayout.count():
            self.rowsLayout.takeAt(0)
        newButtons, newRows = {}, {}
        for new_row, old_row in enumerate(order):
            w = self._rowWidgets.get(old_row)
            if w is None:
                continue
            self.rowsLayout.addWidget(w)
            newRows[new_row] = w
            btn = self._photoButtons.get(old_row)
            if btn is not None:
                btn.mousePressEvent = partial(self._photoClicked, new_row)
                newButtons[new_row] = btn
        self._rowWidgets = newRows
        self._photoButtons = newButtons
        self.scrollArea.verticalScrollBar().setValue(0)
        self._sorting = False

    def _buildRows(self):
        """Full grid build (initial fill): sort, then create every row and
        stream the thumbnails in from the worker pool."""
        if not self.photoList:
            return

        # guard against re-entrant calls while threads are still running
        if self._sorting:
            return
        self._sorting = True

        QApplication.processEvents()

        self._sortPhotoList()

        # clear the existing rows
        for i in reversed(range(self.rowsLayout.count())):
            w = self.rowsLayout.itemAt(i).widget()
            if w:
                w.setParent(None)

        # create placeholder rows for every photo immediately so the layout is
        # fully established before any thumbnails arrive from threads
        self._photoButtons = {}
        self._rowWidgets = {}

        # Start the worker pool and the result drain BEFORE building the grid, so
        # thumbnails decode in parallel and pop into their cells as the grid is
        # built — rather than the grid appearing empty and filling all at once at
        # the end.  Workers block on the queue and exit on a None sentinel.
        overlay = self.mdiParent.progressOverlay
        overlay.armGate(1000, force=False)   # arm for direct re-sorts; keep FillPhotos' clock otherwise
        overlay.showDeterminate("Loading photos…", len(self.photoList))

        self._loadedCount = 0
        self._totalUncached = 0
        self._building = True
        nThreads = min(self.threadCount, max(1, len(self.photoList)))
        self.threadsRemaining = nThreads
        for i in range(nThreads):
            self.threads[i].start()
        self._drainTimer.start(50)

        for row, (p, s) in enumerate(self.photoList):

            if row % 50 == 0:
                overlay.setProgress(row)
                QApplication.processEvents()   # lay out new cells + let the drain fill them

            buttonPhoto = QLabel()
            buttonPhoto.setFixedWidth(code_ThumbnailCache.THUMB_DISPLAY_SIZE.width())
            buttonPhoto.setMinimumHeight(code_ThumbnailCache.THUMB_DISPLAY_SIZE.height())
            buttonPhoto.setAlignment(Qt.AlignCenter)
            buttonPhoto.setCursor(Qt.PointingHandCursor)
            buttonPhoto.mousePressEvent = partial(self._photoClicked, row)

            # Prefer the photo's true (EXIF) creation date/time from the catalog;
            # fall back to the checklist date/time when none is stored.
            exif_dt = p.get("exifDatetime")
            if exif_dt and len(exif_dt) >= 10:
                dispDate = exif_dt[0:4] + "-" + exif_dt[5:7] + "-" + exif_dt[8:10]
                dispTime = exif_dt[11:16] if len(exif_dt) >= 16 else ""
            else:
                dispDate, dispTime = s.get("date", ""), s.get("time", "")
            try:
                photoWeekday = datetime.datetime(
                    int(dispDate[0:4]), int(dispDate[5:7]), int(dispDate[8:10])
                ).strftime("%A")
            except Exception:
                photoWeekday = ""
            dateLine = dispDate + ((" " + dispTime) if dispTime else "")
            if photoWeekday:
                dateLine = photoWeekday + ", " + dateLine

            labelCaption = QLabel()
            labelCaption.setTextFormat(Qt.RichText)
            labelCaption.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            labelCaption.setText(
                "<br><br>"
                '<span style="font-size: 1.1em; font-weight: bold;">' + s["commonName"] + "</span><br>"
                "<i>" + s["scientificName"] + "</i><br><br>" +
                s["location"] + "<br>" +
                dateLine + "<br><br>" +
                "Rating: " + p["rating"]
            )
            labelCaption.setObjectName("mediaCaption")

            # One container widget per row in a QVBoxLayout (avoids the grid's
            # ~524k-px height cap that squashed rows past ~1,600 photos).
            # The row carries the shared media-card background; children are
            # transparent over it.
            rowWidget = QWidget()
            rowWidget.setObjectName("mediaCard")
            rowWidget.setAttribute(Qt.WA_StyledBackground, True)
            rowWidget.setMinimumHeight(code_ThumbnailCache.THUMB_DISPLAY_SIZE.height())
            rowLayout = QHBoxLayout(rowWidget)
            rowLayout.setContentsMargins(6, 6, 6, 6)   # inset content off the rounded corners
            rowLayout.setSpacing(2)
            rowLayout.addWidget(buttonPhoto)
            rowLayout.addWidget(labelCaption, 1)   # caption absorbs the extra width

            self.rowsLayout.addWidget(rowWidget)
            self._photoButtons[row] = buttonPhoto
            self._rowWidgets[row] = rowWidget

            # Queue uncached thumbnails for the (already-running) workers as each
            # row is created, so decoding overlaps grid construction.
            if p["fileName"] not in self.pixmapCache:
                self._totalUncached += 1
                self.workQueue.put((row, p["fileName"]))

        # Grid built: sentinel the workers so each exits once it drains the queue.
        # Keep _building True through the rest of this method: the drain fires
        # during the processEvents below and should keep filling cells, but must
        # NOT update the overlay text or declare completion until we've handed it
        # the loading tail — otherwise a fast drain could finish and hide the
        # overlay, which we'd then re-show in a stuck state.
        for _ in range(nThreads):
            self.workQueue.put(None)

        # Apply any cached thumbnails not yet shown.  Scale to the fixed
        # display size, NOT btn.size(): the window is hidden and unlaid-out
        # during the build, so cell geometry is not valid yet.
        for row, (p, s) in enumerate(self.photoList):
            if p["fileName"] in self.pixmapCache:
                btn = self._photoButtons.get(row)
                if btn:
                    cur = btn.pixmap()
                    if cur is None or cur.isNull():   # skip cells the drain already filled
                        pm = self.pixmapCache[p["fileName"]]
                        if not pm.isNull():
                            btn.setPixmap(pm.scaled(
                                code_ThumbnailCache.THUMB_DISPLAY_SIZE,
                                Qt.KeepAspectRatio, Qt.SmoothTransformation))

        self.scrollArea.verticalScrollBar().setValue(0)

        if self._totalUncached > 0:
            # Loading tail: switch the bar to "Loading photos" for whatever the
            # workers haven't caught up on yet (mainly the cold-cache case).
            overlay.startLoading(self._totalUncached)
            overlay.setPhotoValue(self._loadedCount)

        # Hand the overlay to the drain timer; it now owns the "Loading photos"
        # tail and will finish (hide + reset) once the workers have all exited.
        self._building = False


    def _drainResultQueue(self):
        """Called by QTimer every 50 ms. Drains all results the worker threads
        have produced since the last tick, then updates the status label.
        Because worker threads put results into a plain Python queue instead of
        emitting Qt signals, the event loop is idle between ticks and the Cocoa
        display system can flush the screen normally."""

        prevCount = self._loadedCount

        while True:
            try:
                row, photoFile, qimage = self.resultQueue.get_nowait()
            except queue.Empty:
                break

            if self._abort:
                continue

            pm = QPixmap.fromImage(qimage)
            if pm.isNull():
                try:
                    self._missingPhotoSpecies.add(self.photoList[row][1]["commonName"])
                except (IndexError, KeyError):
                    pass
                btn = self._photoButtons.get(row)
                if btn:
                    btn.setText(
                        f"File not found:\n{os.path.basename(photoFile)}")
                    # note: btn is a QLabel; the card provides the background
                    btn.setStyleSheet(
                        "QLabel { color: #e2e4ec; font-size: 10pt; }")
            else:
                self.pixmapCache[photoFile] = pm
                btn = self._photoButtons.get(row)
                if btn:
                    btn.setPixmap(pm.scaled(
                        code_ThumbnailCache.THUMB_DISPLAY_SIZE,
                        Qt.KeepAspectRatio, Qt.SmoothTransformation))

            self._loadedCount += 1

        # Update the "Loading photos" bar — but only after the build loop has
        # released the overlay (during the build it shows "Preparing grid").
        if (not self._abort and not self._building
                and self._loadedCount > prevCount):
            self.mdiParent.progressOverlay.setPhotoValue(self._loadedCount)

        # Finish once the build is done, all workers have exited, and the queue
        # is fully drained.
        if (not self._building and self.threadsRemaining == 0
                and self.resultQueue.empty()):
            self._drainTimer.stop()
            self._finishLoading()


    def thumbnailThreadFinished(self):

        if self._abort:
            return

        self.threadsRemaining -= 1


    def _finishLoading(self):

        self.mdiParent.progressOverlay.hide()
        self.scrollArea.verticalScrollBar().setValue(0)
        self._sorting = False
        self.contentReady.emit()

        if self._missingPhotoSpecies:
            n = len(self._missingPhotoSpecies)
            if n <= 5:
                species_list = "\n".join(
                    f"  \u2022 {name}" for name in sorted(self._missingPhotoSpecies))
                detail = f"Photos could not be found for:\n\n{species_list}"
            else:
                detail = "Photos could not be found for more than 5 species."
            QMessageBox.warning(
                self.mdiParent,
                "Missing Photos",
                f"{detail}\n\n"
                "These files may have been moved or deleted outside of Yearbirder.",
                QMessageBox.StandardButton.Ok,
            )


    def _photoClicked(self, row, event):
        self.showEnlargement(row)


    def handlePhotoDeletion(self, filename):
        self.pixmapCache.pop(filename, None)

        idx = next((i for i, (p, s) in enumerate(self.photoList) if p["fileName"] == filename), None)
        if idx is None:
            return

        rw = self._rowWidgets.get(idx)
        if rw:
            rw.setParent(None)

        self.photoList.pop(idx)

        if not self.photoList:
            self.close()
            return

        # Re-index the remaining rows (keys shift down past the deleted one).
        new_buttons = {}
        new_rows = {}
        for old_row in sorted(self._photoButtons.keys()):
            if old_row == idx:
                continue
            new_row = old_row if old_row < idx else old_row - 1
            btn = self._photoButtons[old_row]
            if new_row != old_row:
                btn.mousePressEvent = partial(self._photoClicked, new_row)
            new_buttons[new_row] = btn
            if old_row in self._rowWidgets:
                new_rows[new_row] = self._rowWidgets[old_row]
        self._photoButtons = new_buttons
        self._rowWidgets = new_rows


    def showEnlargement(self, row):

        sub = code_Enlargement.Enlargement()

        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self
        sub.photoList = list(self.photoList)
        sub.currentIndex = row

        # add and position the child to our MDI area
        self.mdiParent.mdiArea.addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self.mdiParent)
        sub.show()

        # call the child's routine to fill it with data
        sub.fillEnlargement()


    def launchSlideshow(self):
        import code_Slideshow
        dlg = code_Slideshow.SlideshowDialog(self.mdiParent)
        if dlg.exec() != code_Slideshow.QDialog.DialogCode.Accepted:
            return
        photoList = code_Slideshow.buildPhotoList(
            self.mdiParent.db, self.filter, dlg.sortOrder()
        )
        if not photoList:
            QMessageBox.information(self.mdiParent, "No Results",
                                    "No photos found for the current filter.")
            return
        self.mdiParent._slideshow = code_Slideshow.SlideshowWindow(
            photoList, dlg.secondsPerPhoto(), dlg.showTitleBar()
        )
        self.mdiParent._slideshow.show()
