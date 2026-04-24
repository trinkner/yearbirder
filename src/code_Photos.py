# import project files
import form_Photos
import code_Enlargement

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
    QImageReader,
    )

from PySide6.QtCore import (
    Signal,
    QSize,
    Qt,
    QThread,
    QTimer,
    QByteArray,
    QBuffer,
    QIODevice,
    )

import base64

from PySide6.QtWidgets import (
    QDialog,
    QMdiSubWindow,
    QLabel,
    QMessageBox,
    QProgressBar,
    QVBoxLayout,
    QApplication,
    )


class _PhotoProgressDialog(QDialog):
    """Frameless progress dialog shown while the Photos window prepares and loads thumbnails.

    Starts in indeterminate mode ("Preparing photos…") so it can appear
    immediately before the database query runs.  Call startLoading(total) to
    switch to a determinate bar once the thumbnail-loading phase begins.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(False)   # non-blocking so the drain timer can fire
        self.setFixedWidth(380)

        self.setStyleSheet("""
            QDialog {
                background: #1e1f26;
                border: 2px solid #4f8ef7;
                border-radius: 10px;
            }
            QLabel {
                color: #e2e4ec;
                font-size: 13px;
                background: transparent;
            }
            QProgressBar {
                background: #252730;
                border: 1px solid #3a3d4e;
                border-radius: 5px;
                min-height: 20px;
                text-align: center;
                color: #e2e4ec;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background: #4f8ef7;
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        self._label = QLabel("Preparing photos\u2026")
        self._label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        layout.addWidget(self._bar)

    def startLoading(self, total):
        """Switch from indeterminate to determinate mode when thumbnail loading begins."""
        self._bar.setRange(0, max(total, 1))
        self._bar.setValue(0)
        self._label.setText(f"Loading photos\u2026  0 of {total:,}")

    def setValue(self, loaded):
        self._bar.setValue(loaded)
        self._label.setText(
            f"Loading photos\u2026  {loaded:,} of {self._bar.maximum():,}"
        )

    def closeEvent(self, event):
        event.ignore()   # user cannot dismiss; call accept() to close programmatically


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

            try:
                row, photoFile = self.workQueue.get_nowait()
            except queue.Empty:
                break

            reader = QImageReader(photoFile)
            reader.setAutoTransform(True)
            imgSize = reader.size()
            if imgSize.isValid():
                imgSize.scale(QSize(500, 330), Qt.KeepAspectRatio)
                reader.setScaledSize(imgSize)
            qimage = reader.read()

            self.resultQueue.put((row, photoFile, qimage))
            self.workQueue.task_done()

        self.sigThreadFinished.emit()


class Photos(QMdiSubWindow, form_Photos.Ui_frmPhotos):

    # create "resized" as a signal that the window can emit
    # we respond to this signal with the form's resizeMe method below
    resized = Signal()

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
        self.gridPhotos.setContentsMargins(2,2,2,2)
        self.gridPhotos.setSpacing(2)
        self.verticalLayout_3.addStretch(1)
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
        self._progressDlg = None

        # Timer drains resultQueue in the main thread at regular intervals.
        # Because no Qt signals are fired from worker threads, the event loop
        # stays idle between ticks and Cocoa can flush the display normally.
        self._drainTimer = QTimer(self)
        self._drainTimer.timeout.connect(self._drainResultQueue)


    def closeEvent(self, event):
        self._abort = True
        self._drainTimer.stop()
        # drain the work queue so worker threads exit their loops promptly
        while not self.workQueue.empty():
            try:
                self.workQueue.get_nowait()
                self.workQueue.task_done()
            except queue.Empty:
                break
        # drain the result queue so nothing lingers
        while not self.resultQueue.empty():
            try:
                self.resultQueue.get_nowait()
            except queue.Empty:
                break
        self.mdiParent.db.compactJsonlFile()
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

        self.lblLocation.setFont(QFont("Helvetica", fontSize))
        metrics = self.lblLocation.fontMetrics()
        cboText = self.lblLocation.text()
        if cboText == "":
            cboText = "Dummy Text"
        itemTextWidth = int(metrics.boundingRect(cboText).width())
        itemTextHeight = int(metrics.boundingRect(cboText).height())
        #scale the font for all widgets in window
        for w in self.children():
            try:
                w.setFont(QFont("Helvetica", fontSize))
            except:
                pass

        self.lblLocation.setFont(QFont("Helvetica", floor(fontSize * 1.4 )))
        self.lblLocation.setStyleSheet("QLabel { font: bold }");
        self.lblDateRange.setFont(QFont("Helvetica", floor(fontSize * 1.2 )))
        self.lblDateRange.setStyleSheet("QLabel { font: bold }");
        self.lblDetails.setFont(QFont("Helvetica", floor(fontSize * 1.2 )))
        self.lblDetails.setStyleSheet("QLabel { font: bold }");
        self.lblSpecies.setFont(QFont("Helvetica", fontSize))
        self.lblSortBy.setFont(QFont("Helvetica", fontSize))
        self.rdoSortSpecies.setFont(QFont("Helvetica", fontSize))
        self.rdoSortDate.setFont(QFont("Helvetica", fontSize))
        self.rdoSortRating.setFont(QFont("Helvetica", fontSize))
        self.rdoSortTaxonomy.setFont(QFont("Helvetica", fontSize))

        for c in self.layLists.children():
            if "QLabel" in str(c):
                c.setFont(QFont("Helvetica", fontSize))

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

        # Lay out 4 photos per page: 2 columns × 2 rows.
        for i in range(0, len(cells), 4):
            page_cells = cells[i:i+4]
            if len(page_cells) % 2 != 0:
                page_cells.append('<td></td>')
            html += '<table>'
            for j in range(0, len(page_cells), 2):
                html += '<tr>' + page_cells[j] + page_cells[j + 1] + '</tr>'
            html += '</table>'
            if i + 4 < len(cells):
                html += '<div style="page-break-after: always;"></div>'

        html += '</body></html>'
        return html


    def FillPhotos(self, filter):

        self.scaleMe()
        self.resizeMe()
        self._missingPhotoSpecies = set()

        # save the filter settings passed to this routine to the form for future use
        self.filter = filter

        # Show progress dialog immediately (indeterminate) before any DB work starts.
        self._progressDlg = _PhotoProgressDialog(parent=self.mdiParent)
        self._progressDlg.adjustSize()
        mw = self.mdiParent.geometry()
        self._progressDlg.move(
            mw.center().x() - self._progressDlg.width() // 2,
            mw.center().y() - self._progressDlg.height() // 2,
        )
        self._progressDlg.show()
        QApplication.processEvents()

        photoSightings = self.mdiParent.db.GetSightingsWithPhotos(filter)

        if len(photoSightings) == 0:
            self._progressDlg.accept()
            self._progressDlg = None
            return False

        # count photos and species for the header label
        species = set()
        photoCount = 0
        for s in photoSightings:
            for p in s["photos"]:
                if self.mdiParent.db.TestIndividualPhoto(p, filter):
                    photoCount += 1
                    species.add(s["commonName"])
        photoCountStr = str(photoCount)
        speciesCount = len(species)

        self.lblSpecies.setText("Species: " + str(speciesCount) + ". Photos: " + photoCountStr)
        self.mdiParent.SetChildDetailsLabels(self, filter)
        self.setWindowTitle(filter.buildWindowTitle("Photos", self.mdiParent.db, count=photoCount, countUnit="Photos"))

        # Build photoList by iterating all valid photos
        self.photoList = []
        for s in photoSightings:
            for p in s["photos"]:
                if self.mdiParent.db.TestIndividualPhoto(p, filter):
                    self.photoList.append([p, s])
                    if self._abort:
                        self._progressDlg.accept()
                        self._progressDlg = None
                        return False

        # Sort and populate the grid
        self.SortAndDisplayPhotos()

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_camera_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        # don't show if we don't have any photos to show
        if len(self.photoList) == 0:
            if self._progressDlg is not None:
                self._progressDlg.accept()
                self._progressDlg = None
            self.close()

        # resize to a smaller window if we only have one photo to show
        if len(self.photoList) == 1:
            self.scaleMe()

        # tell MainWindow that we succeeded filling the list
        return(True)


    def SortAndDisplayPhotos(self):

        if not self.photoList:
            return

        # guard against re-entrant calls while threads are still running
        if self._sorting:
            return
        self._sorting = True

        QApplication.processEvents()

        # sort based on the selected radio button
        if self.rdoSortSpecies.isChecked():
            self.photoList.sort(key=lambda x: x[1]["commonName"])
        elif self.rdoSortDate.isChecked():
            self.photoList.sort(key=lambda x: x[1]["date"] + x[1]["time"])
        elif self.rdoSortRating.isChecked():
            try:
                self.photoList.sort(key=lambda x: float(x[0]["rating"]) if x[0]["rating"] else 0, reverse=True)
            except (ValueError, TypeError):
                self.photoList.sort(key=lambda x: x[0]["rating"], reverse=True)
        elif self.rdoSortTaxonomy.isChecked():
            self.photoList.sort(key=lambda x: (float(x[1]["taxonomicOrder"]), x[1]["commonName"]))

        # clear the grid
        for i in reversed(range(self.gridPhotos.count())):
            self.gridPhotos.itemAt(i).widget().setParent(None)

        # create placeholder buttons and captions for every row immediately so the
        # layout is fully established before any thumbnails arrive from threads
        self._photoButtons = {}
        uncached = []

        # Drive column and row sizes directly on the grid layout so the constraints
        # propagate to the scroll-area content widget regardless of label size policy.
        self.gridPhotos.setColumnMinimumWidth(0, 500)
        self.gridPhotos.setColumnStretch(1, 1)   # caption column absorbs extra width

        for row, (p, s) in enumerate(self.photoList):

            buttonPhoto = QLabel()
            buttonPhoto.setAlignment(Qt.AlignCenter)
            buttonPhoto.setStyleSheet("QLabel{ background-color: #343333; }")
            buttonPhoto.setCursor(Qt.PointingHandCursor)
            buttonPhoto.mousePressEvent = partial(self._photoClicked, row)

            photoWeekday = datetime.datetime(int(s["date"][0:4]), int(s["date"][5:7]), int(s["date"][8:10]))
            photoWeekday = photoWeekday.strftime("%A")

            labelCaption = QLabel()
            labelCaption.setTextFormat(Qt.RichText)
            labelCaption.setText(
                s["commonName"] + "<br>"
                "<i>" + s["scientificName"] + "</i><br><br>" +
                s["location"] + "<br>" +
                photoWeekday + ", " + s["date"] + " " + s["time"] + "<br><br>" +
                "Rating: " + p["rating"]
            )
            labelCaption.setStyleSheet("QLabel { background-color: #343333; color: silver; padding: 3px; }")

            self.gridPhotos.addWidget(buttonPhoto, row, 0)
            self.gridPhotos.addWidget(labelCaption, row, 1)
            self.gridPhotos.setRowMinimumHeight(row, 330)
            self._photoButtons[row] = buttonPhoto

            # Cached photos are applied after processEvents() below so the label
            # has its actual rendered height before we scale the pixmap to fit.
            if p["fileName"] not in self.pixmapCache:
                uncached.append((row, p["fileName"]))

        # Let the layout engine run so every label has its real geometry.  Then
        # apply cached pixmaps scaled to each label's actual size — this ensures
        # photos fill their row correctly whether rows are 330 px (small list) or
        # compressed shorter (Qt's QLAYOUTSIZE_MAX cap on very large lists).
        QApplication.processEvents()
        for row, (p, s) in enumerate(self.photoList):
            if p["fileName"] in self.pixmapCache:
                btn = self._photoButtons.get(row)
                if btn and btn.height() > 0:
                    pm = self.pixmapCache[p["fileName"]]
                    if not pm.isNull():
                        btn.setPixmap(pm.scaled(btn.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

        self.scrollArea.verticalScrollBar().setValue(0)

        if uncached:
            for item in uncached:
                self.workQueue.put(item)
            threadsToStart = min(self.threadCount, len(uncached))
            self.threadsRemaining = threadsToStart
            self._loadedCount = 0
            self._totalUncached = len(uncached)
            self._threadsToStart = threadsToStart

            # Switch the already-visible dialog from indeterminate to determinate mode.
            if self._progressDlg is not None:
                self._progressDlg.startLoading(len(uncached))

            # Defer thread start until the event loop regains control.
            # Threads started here would run while FillPhotos() finishes and
            # the click handler unwinds — loading ~1400 photos before the
            # drain timer ever gets a chance to fire.
            QTimer.singleShot(0, self._startThreads)
        else:
            # everything was in the cache — finish synchronously
            self._finishLoading()


    def _startThreads(self):
        """Starts worker threads and the drain timer.  Called via singleShot(0)
        so it runs on the first event-loop iteration after the click handler
        that triggered loading has fully returned."""
        if self._abort:
            return
        for i in range(self._threadsToStart):
            self.threads[i].start()
        self._drainTimer.start(50)


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
                    btn.setStyleSheet(
                        "QPushButton { background-color: #343333; border: 0px; "
                        "color: #e2e4ec; font-size: 10pt; }")
            else:
                self.pixmapCache[photoFile] = pm
                btn = self._photoButtons.get(row)
                if btn and btn.height() > 0:
                    btn.setPixmap(pm.scaled(btn.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

            self._loadedCount += 1

        # Update the progress dialog on every drain tick that delivered photos.
        if self._progressDlg is not None and not self._abort and self._loadedCount > prevCount:
            self._progressDlg.setValue(self._loadedCount)

        # finish once all threads are done and the queue is fully drained
        if self.threadsRemaining == 0 and self.resultQueue.empty():
            self._drainTimer.stop()
            self._finishLoading()


    def thumbnailThreadFinished(self):

        if self._abort:
            return

        self.threadsRemaining -= 1


    def _finishLoading(self):

        if self._progressDlg is not None:
            self._progressDlg.accept()   # accept() bypasses closeEvent's ignore()
            self._progressDlg = None
        self.scrollArea.verticalScrollBar().setValue(0)
        self._sorting = False

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


    def GetPixmapForThumbnail(self, photoFile):
        """Synchronous fallback — returns a pixmap from cache or reads from disk.
        Used by code_Enlargement and any other callers that need a pixmap on demand."""

        if photoFile in self.pixmapCache:
            return self.pixmapCache[photoFile]

        reader = QImageReader(photoFile)
        reader.setAutoTransform(True)
        imgSize = reader.size()
        if imgSize.isValid():
            imgSize.scale(QSize(500, 330), Qt.KeepAspectRatio)
            reader.setScaledSize(imgSize)
        pm = QPixmap.fromImage(reader.read())
        if not pm.isNull():
            self.pixmapCache[photoFile] = pm
        return pm


    def _photoClicked(self, row, event):
        self.showEnlargement(row)


    def handlePhotoDeletion(self, filename):
        self.pixmapCache.pop(filename, None)

        idx = next((i for i, (p, s) in enumerate(self.photoList) if p["fileName"] == filename), None)
        if idx is None:
            return

        for col in (0, 1):
            item = self.gridPhotos.itemAtPosition(idx, col)
            if item and item.widget():
                item.widget().setParent(None)
        self.gridPhotos.setRowMinimumHeight(idx, 0)

        self.photoList.pop(idx)

        if not self.photoList:
            self.close()
            return

        new_buttons = {}
        for old_row, btn in self._photoButtons.items():
            if old_row == idx:
                continue
            new_row = old_row if old_row < idx else old_row - 1
            if new_row != old_row:
                btn.mousePressEvent = partial(self._photoClicked, new_row)
            new_buttons[new_row] = btn
        self._photoButtons = new_buttons


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
