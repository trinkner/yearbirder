import form_Enlargement
import code_Filter
import code_Stylesheet
import code_NotesDialog
import datetime
import ntpath

import os
from math import floor

import piexif

from PySide6.QtGui import (
    QPixmap,
    QPainter,
    QCursor,
    QIcon
    )

from PySide6.QtCore import (
    Qt,
    Signal,
    QTimer,
    QSize,
    QPropertyAnimation,
    QEasingCurve
    )

from PySide6.QtWidgets import (
    QApplication,
    QMdiSubWindow,
    QGraphicsView,
    QGraphicsScene,
    QMessageBox,
    QMenu,
    QLabel,
    QGroupBox,
    QHBoxLayout,
    QBoxLayout,
    QFrame,
    QVBoxLayout,
    QPushButton,
    QWidget,
    QDialog
    )

BLEND_DURATION = 300   # crossfade duration in ms
BLEND_INTERVAL = 16    # timer tick in ms (~60 fps)
FADE_MS = 220          # Windows full-screen enter/exit opacity fade duration
DETAILS_PANE_WIDTH = 297   # must match detailsPane.setFixedWidth() below
   

class Enlargement(QMdiSubWindow, form_Enlargement.Ui_frmEnlargement):
    
    # create "resized" as a signal that the window can emit
    # we respond to this signal with the form's resizeMe method below
    resized = Signal() 
    
    class _CrossfadeOverlay(QWidget):
        """Snapshot of the outgoing photo that fades to transparent, revealing the
        incoming photo in the QGraphicsView underneath."""

        def __init__(self, parent):
            super().__init__(parent)
            self._pixmap = QPixmap()
            self._alpha  = 0.0
            self.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.hide()

        def paintEvent(self, event):
            if self._pixmap.isNull() or self._alpha <= 0.0:
                return
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.setOpacity(self._alpha)
            p.drawPixmap(self.rect(), self._pixmap)
            p.end()


    class MyGraphicsView(QGraphicsView):
        
        def __init__(self):
            QGraphicsView.__init__(self)
            self.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform)
            self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setFrameShape(QFrame.NoFrame)
            self.mdiParent = ""
            
            
        def wheelEvent(self,event):
            adj = 1 + event.angleDelta().y()/120 * 0.1
            self.scale(adj, adj)


        def mouseDoubleClickEvent(self, event):
            # Double-click undoes wheel zooming, the same as F and the context
            # menu's "Fit to window" — the zoom is right under the mouse, so the
            # way back should be too.
            if event.button() == Qt.LeftButton:
                self.mdiParent.fitEnlargement()
                event.accept()
                return
            super().mouseDoubleClickEvent(event)


        # we need a keepress event handler here in case the user clicks on the photo.
        # when user clicks on the photo, the keypress handler is this GraphicsView, not the Englargement class.
        def keyPressEvent(self, e):

            # Ctrl/Cmd shortcuts belong to the main window (Open, Find, filters,
            # toolbar…) — forward and stop, so this view doesn't swallow them
            # (e.g. Cmd-O to open a data file).  self.mdiParent is the
            # Enlargement; its .mdiParent.mdiParent is the MainWindow.
            if e.modifiers() & Qt.ControlModifier:
                self.mdiParent.mdiParent.mdiParent.keyPressEvent(e)
                return

            # F key is pressed. Re-display the currentEnlargement to fit the screen
            if e.key() == Qt.Key_F:
                self.mdiParent.fitEnlargement()
                
            # Backspace key is pressed, so show previous image as enlargement     
            if e.key() == Qt.Key_Backspace:
                self.mdiParent.showPreviousPhoto()
    
            # Space bar is pressed, so show next image as enlargement     
            if e.key() == Qt.Key_Space:
                self.mdiParent.showNextPhoto()

            # F7 is pressed, so toggle display of cursor
            if e.key() == Qt.Key_F7:
                self.mdiParent.toggleHideCursor()          
    
            # F9 is pressed, so toggle display of camera details 
            if e.key() == Qt.Key_F9:
                self.mdiParent.toggleCameraDetails()
    
            # F10 is pressed, so toggle display of camera details
            if e.key() == Qt.Key_F10:
                QTimer.singleShot(0, self.mdiParent.toggleFullScreen)

            # Esc is pressed, so exit full screen mode, if we're in it
            if e.key() == Qt.Key_Escape and self.mdiParent._fullScreen:
                QTimer.singleShot(0, self.mdiParent.toggleFullScreen)
    
            # 1-5 pressed, so rate the photo 
            if e.key() in [Qt.Key_0, Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4, Qt.Key_5]:
                self.mdiParent.ratePhoto(e.key())
    
            # Right is pressed: show next photo            
            if e.key() == Qt.Key_Right or e.key() == Qt.Key_PageDown:   
                self.mdiParent.showNextPhoto()               
    
            # Left is pressed: show previous photo
            if e.key() == Qt.Key_Left or e.key() == Qt.Key_PageUp:   
                self.mdiParent.showPreviousPhoto()           

            
        def contextMenuEvent(self, event):
    
            QApplication.restoreOverrideCursor()           

            menu = QMenu(self)
            menu.setStyleSheet("color:silver; background-color: #343333;")
            
            actionFitToWindow = menu.addAction("Fit to window (F or double-click)")
            menu.addSeparator()
            actionShowNextPhoto = menu.addAction("Next photo (→)")
            actionShowPreviousPhoto = menu.addAction("Previous photo (←)")
            menu.addSeparator()
            
            if self.mdiParent._fullScreen:
                if self.mdiParent.cursorIsVisible:
                    actionToggleHideCursor = menu.addAction("Hide cursor (F7)")
                else:
                    actionToggleHideCursor = menu.addAction("Show cursor (F7)")

            if self.mdiParent.detailsPane.isVisible():
                actionToggleCameraDetails = menu.addAction("Hide details (F9)")
            else:
                actionToggleCameraDetails = menu.addAction("Show details (F9)")

            if self.mdiParent._fullScreen:
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
            actionSlideshow = menu.addAction("Slideshow")
            menu.addSeparator()
            actionEditAssignment = menu.addAction("Edit species or location assignment…")
            menu.addSeparator()
            actionDetachFile = menu.addAction("Remove photo from catalog…")
            menu.addSeparator()
            actionDeleteFile = menu.addAction("Delete photo from file system…")

            action = menu.exec(self.mapToGlobal(event.pos()))

            if self.mdiParent._fullScreen:
                if action == actionToggleHideCursor:
                    self.parent().toggleHideCursor()

            if action == actionFitToWindow:
                self.parent().fitEnlargement()

            if action == actionShowNextPhoto:
                self.parent().showNextPhoto()

            if action == actionShowPreviousPhoto:
                self.parent().showPreviousPhoto()

            if action == actionToggleCameraDetails:
                self.parent().toggleCameraDetails()

            if action == actionToggleFullScreen:
                QTimer.singleShot(0, self.parent().toggleFullScreen)

            if action == actionRate1:
                self.parent().ratePhoto(Qt.Key_1)
            if action == actionRate2:
                self.parent().ratePhoto(Qt.Key_2)
            if action == actionRate3:
                self.parent().ratePhoto(Qt.Key_3)
            if action == actionRate4:
                self.parent().ratePhoto(Qt.Key_4)
            if action == actionRate5:
                self.parent().ratePhoto(Qt.Key_5)

            if action == actionSlideshow:
                self.parent().launchSlideshow()

            if action == actionEditAssignment:
                # Deferred: opening an MDI child from inside the menu's own
                # event handler fights the popup teardown, and full screen has
                # to unwind first (see editAssignment).
                QTimer.singleShot(0, self.parent().editAssignment)

            if action == actionDeleteFile:
                self.parent().deleteFile()

            if action == actionDetachFile:
                self.parent().detachFile()
                                                 
    
    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose,True)
        self.resized.connect(self.resizeMe)        
        self.mdiParent = ""
        self.photoList = []
        self.currentIndex = 0
        
        self.pixmapEnlargement = QPixmap()
        # Full-screen state.  In full screen this window detaches from the MDI
        # area and shows itself as a top-level window; the main window is left
        # untouched behind it (see toggleFullScreen).  _mdiGeometry restores the
        # MDI-child geometry on the way back.
        self._fullScreen = False
        self._mdiGeometry = None
        self._savedFlags = None
        self._crossfadeOverlay = None
        self._blendTimer = QTimer(self)
        self._blendTimer.timeout.connect(self._blendStep)

        # A rating edit changes what open reports show — the Species Gallery
        # picks the best-rated photo per species, and ratings are part of the
        # media-scope signature — so it has to be broadcast.  Debounced: stepping
        # through stars (or rating a run of photos) would otherwise re-run every
        # open report's signature query on each keystroke.
        self._ratingNotifyTimer = QTimer(self)
        self._ratingNotifyTimer.setSingleShot(True)
        self._ratingNotifyTimer.setInterval(400)
        self._ratingNotifyTimer.timeout.connect(self._notifyRatingChanged)

        self.layout().setDirection(QBoxLayout.Direction.RightToLeft)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)   
        self.setStyleSheet("color:silver; background-color: #343333")
        
        self.detailsPaneLayout = QVBoxLayout()
        self.detailsPaneLayout.setContentsMargins(0, 0, 0, 0)
        self.detailsPaneLayout.setSpacing(0)
        self.detailsPaneLayout.setAlignment(Qt.AlignCenter)
        
        
        self.detailsPane = QFrame()
        self.detailsPane.setFrameShape(QFrame.NoFrame)
        self.detailsPane.setFixedWidth(DETAILS_PANE_WIDTH)
        self.detailsPane.setLayout(self.detailsPaneLayout)
        self.detailsPane.setStyleSheet("color:silver; background-color: #343333; border: none;")
        
        self.layout().addWidget(self.detailsPane)
        
        # create label for species common name
        self.commonName = QLabel()
        self.commonName.setStyleSheet("font:15pt; font-weight:bold; color:silver; background-color: #343333; padding: 3px")                
        self.detailsPaneLayout.addWidget(self.commonName)

        # create label for species scientific name
        self.scientificName = QLabel()
        self.scientificName.setStyleSheet("font:12pt; font-style:italic; color:silver; background-color: #343333; padding: 3px")                
        self.detailsPaneLayout.addWidget(self.scientificName)

        # create label for camera details text
        self.cameraDetails = QLabel()
        self.cameraDetails.setWordWrap(True)
        self.cameraDetails.setStyleSheet("color:silver; background-color: #343333; padding: 3px")
        # Explicit (not auto-detected): the italic "f" in the exposure/aperture
        # line is set via <i>, and Qt's rich-text sniff only looks for a tag
        # before the first line break — which this text never has.
        self.cameraDetails.setTextFormat(Qt.TextFormat.RichText)
        self.detailsPaneLayout.addWidget(self.cameraDetails)

        # Notes — clickable label beneath the filename (in cameraDetails); a
        # click (anywhere, even when empty) opens the same plain-text popup
        # used by Manage Photos' Notes button.
        self.notesLabel = QLabel()
        # Word wrap is off: elideToLines() already hard-breaks the text into
        # exactly the lines that fit, using its own pixel measurement. Leaving
        # Qt's automatic wrap on as well let it re-wrap a borderline line a
        # second time (its internal text-layout width can differ from
        # QFontMetrics.horizontalAdvance() by a few px), stranding the last
        # word of that line alone on an extra line.
        self.notesLabel.setWordWrap(False)
        self.notesLabel.setStyleSheet("color:silver; background-color: #343333; padding: 3px")
        self.notesLabel.setCursor(Qt.PointingHandCursor)
        self.notesLabel.mousePressEvent = lambda event: self._openNotesDialog()
        self.detailsPaneLayout.addWidget(self.notesLabel)
        self.detailsPaneLayout.addSpacing(10)   # line feed after the Notes field

        # setVisible(True) MUST stay after the addWidget above (line ~257) that
        # reparents detailsPane: calling it while the QFrame is still parent=None
        # realizes it as a stray top-level native window (an empty "Yearbirder"
        # window on Windows).  That exact ordering bug caused the Recording
        # Enlargement spectro-click flash — keep the reparent before this line.
        self.detailsPane.setVisible(True)

        # create horizontal layout to show rating stars
        self.horizontalGroupBox = QGroupBox()
        self.horizontalGroupBox.setContentsMargins(0, 0, 0, 0)
        self.horizontalGroupBox.setStyleSheet("QGroupBox { border: none; background-color: #343333; padding: 3px; }")

        self.detailsPaneLayout.addWidget(self.horizontalGroupBox)
        self.detailsPaneLayout.addSpacing(10)   # line feed after the rating stars

        ratingLayout = QHBoxLayout()
        ratingLayout.setContentsMargins(0, 0, 0, 0)
        ratingLayout.setSpacing(0)
         
        self.star1 = QPushButton()
        self.star2 = QPushButton()
        self.star3 = QPushButton()
        self.star4 = QPushButton()
        self.star5 = QPushButton()

        self.star1.setIconSize(QSize(40,40))    
        self.star2.setIconSize(QSize(40,40))    
        self.star3.setIconSize(QSize(40,40))    
        self.star4.setIconSize(QSize(40,40))    
        self.star5.setIconSize(QSize(40,40))    
        
        # Zero the global QPushButton rule's padding/min-width — otherwise
        # each star's true footprint is that 60px floor plus 12px padding
        # per side (~86px), not the 40px icon, and 5 of them overflow the
        # details pane.
        _starStyle = ("QPushButton{ background-color: #343333; border:none; "
                      "padding: 0px; min-width: 0px; }")
        self.star1.setStyleSheet("QPushButton:pressed{ background-color: #343333; }")
        self.star1.setStyleSheet("QPushButton:hover{ background-color: #343333; }")
        self.star1.setStyleSheet("QPushButton:flat{ background-color: #343333; }")
        self.star1.setStyleSheet(_starStyle)
        self.star2.setStyleSheet("QPushButton:pressed{ background-color: #343333; }")
        self.star2.setStyleSheet("QPushButton:hover{ background-color: #343333; }")
        self.star2.setStyleSheet("QPushButton:flat{ background-color: #343333; }")
        self.star2.setStyleSheet(_starStyle)
        self.star3.setStyleSheet("QPushButton:pressed{ background-color: #343333; }")
        self.star3.setStyleSheet("QPushButton:hover{ background-color: #343333; }")
        self.star3.setStyleSheet("QPushButton:flat{ background-color: #343333; }")
        self.star3.setStyleSheet(_starStyle)
        self.star4.setStyleSheet("QPushButton:pressed{ background-color: #343333; }")
        self.star4.setStyleSheet("QPushButton:hover{ background-color: #343333; }")
        self.star4.setStyleSheet("QPushButton:flat{ background-color: #343333; }")
        self.star4.setStyleSheet(_starStyle)
        self.star5.setStyleSheet("QPushButton:pressed{ background-color: #343333; }")
        self.star5.setStyleSheet("QPushButton:hover{ background-color: #343333; }")
        self.star5.setStyleSheet("QPushButton:flat{ background-color: #343333; }")
        self.star5.setStyleSheet(_starStyle)
        
        self.star1.setIcon(QIcon(QPixmap(":/icon_star.png")))
        self.star2.setIcon(QIcon(QPixmap(":/icon_star.png")))
        self.star3.setIcon(QIcon(QPixmap(":/icon_star.png")))
        self.star4.setIcon(QIcon(QPixmap(":/icon_star.png")))
        self.star5.setIcon(QIcon(QPixmap(":/icon_star.png")))

        self.star1.clicked.connect(lambda: self.ratePhoto(Qt.Key_1, "Clicked"))
        self.star2.clicked.connect(lambda: self.ratePhoto(Qt.Key_2))
        self.star3.clicked.connect(lambda: self.ratePhoto(Qt.Key_3))
        self.star4.clicked.connect(lambda: self.ratePhoto(Qt.Key_4))
        self.star5.clicked.connect(lambda: self.ratePhoto(Qt.Key_5))
        
        ratingLayout.addWidget(self.star1)
        ratingLayout.addWidget(self.star2)
        ratingLayout.addWidget(self.star3)
        ratingLayout.addWidget(self.star4)
        ratingLayout.addWidget(self.star5)
        
        self.horizontalGroupBox.setLayout(ratingLayout)

        self.cursorIsVisible = True


    def resizeEvent(self, event):
        #routine to handle window resize event        
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)
        
            
    def resizeMe(self):
        
        QTimer.singleShot(5, self.fitEnlargement)
        
        
    def scaleMe(self):
        
        return
        

    def keyPressEvent(self, e):

        # Any Ctrl/Cmd shortcut (Open, Find, filters, toolbar…) belongs to the
        # main window — forward and stop so the enlargement doesn't swallow it
        # (e.g. Cmd-O to open a data file).  self.mdiParent.mdiParent is the
        # MainWindow.
        if e.modifiers() & Qt.ControlModifier:
            self.mdiParent.mdiParent.keyPressEvent(e)
            return

        # F key is pressed. Re-display the currentEnlargement to fit the screen
        if e.key() == Qt.Key_F:
            self.fitEnlargement()
            
        # Backspace key is pressed, so show previous image as enlargement     
        if e.key() == Qt.Key_Backspace:
            self.showPreviousPhoto()

        # Space bar is pressed, so show next image as enlargement     
        if e.key() == Qt.Key_Space:
            self.showNextPhoto()

        # F7 is pressed, so toggle display of cursor
        if e.key() == Qt.Key_F7:
            self.toggleHideCursor()       

        # F9 is pressed, so toggle display of camera details 
        if e.key() == Qt.Key_F9:
            self.toggleCameraDetails()

        # F10 is pressed, so toggle full screen
        if e.key() == Qt.Key_F10:
            QTimer.singleShot(0, self.toggleFullScreen)

        if e.key() == Qt.Key_Escape and self._fullScreen:
            QTimer.singleShot(0, self.toggleFullScreen)

        # 1-5 pressed, so rate the photo 
        if e.key() in [Qt.Key_0, Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4, Qt.Key_5]:
            self.ratePhoto(e.key())

        # Right is pressed: show next photo            
        if e.key() == Qt.Key_Right or e.key() == Qt.Key_PageDown:   
            self.showNextPhoto()               

        # Left is pressed: show previous photo
        if e.key() == Qt.Key_Left or e.key() == Qt.Key_PageUp:
            self.showPreviousPhoto()


    def ratePhoto(self, ratingKey, actionType=""):
                
        if ratingKey == Qt.Key_0:
            self.photoList[self.currentIndex][0]["rating"] = "0"
        if ratingKey == Qt.Key_1:
            if self.photoList[self.currentIndex][0]["rating"] == "1" and actionType == "Clicked":
                self.photoList[self.currentIndex][0]["rating"] = "0"
            else:
                self.photoList[self.currentIndex][0]["rating"] = "1"
        if ratingKey == Qt.Key_2:
            self.photoList[self.currentIndex][0]["rating"] = "2"
        if ratingKey == Qt.Key_3:
            self.photoList[self.currentIndex][0]["rating"] = "3"
        if ratingKey == Qt.Key_4:
            self.photoList[self.currentIndex][0]["rating"] = "4"
        if ratingKey == Qt.Key_5:
            self.photoList[self.currentIndex][0]["rating"] = "5"
            
        self.setCameraDetails()
        self._setDetailsPaneVisible(True)
        db = self.mdiParent.mdiParent.db
        db.photosNeedSaving = True
        try:
            db.appendPhotoToJsonl(self.photoList[self.currentIndex][1], self.photoList[self.currentIndex][0])
        except IOError as exc:
            QMessageBox.warning(self, "Settings File Error",
                f"Rating saved in memory but could not be written to the media catalog:\n{exc}")
        self._ratingNotifyTimer.start()   # debounced broadcast; see __init__
        self.viewEnlargement.setFocus()


    def _notifyRatingChanged(self):
        mainWindow = getattr(self.mdiParent, "mdiParent", None)
        if mainWindow is not None:
            mainWindow.notifyMediaChanged()


    def closeEvent(self, event):
        # Flush a pending rating broadcast: the debounce timer is parented to
        # this window, so closing within the debounce window would drop it.
        if self._ratingNotifyTimer.isActive():
            self._ratingNotifyTimer.stop()
            self._notifyRatingChanged()
        super().closeEvent(event)


    def _refreshNotesLabel(self):
        notes = self.photoList[self.currentIndex][0].get("notes", "")
        metrics = self.notesLabel.fontMetrics()
        # detailsPaneLayout has zero content margins; clear this label's own
        # 3px left+right CSS padding.
        width = self.detailsPane.width() - 6
        if not notes:
            self.notesLabel.setText('Notes: <i>Click to add notes…</i>')
            return
        self.notesLabel.setText(code_NotesDialog.elideToLines("Notes: " + notes, metrics, width, 4))

    def _openNotesDialog(self):
        photoData = self.photoList[self.currentIndex][0]
        dlg = code_NotesDialog.NotesDialog(photoData.get("notes", ""), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            photoData["notes"] = dlg.result
            db = self.mdiParent.mdiParent.db
            db.photosNeedSaving = True
            try:
                db.appendPhotoToJsonl(self.photoList[self.currentIndex][1], photoData)
            except IOError as exc:
                QMessageBox.warning(self, "Settings File Error",
                    f"Notes saved in memory but could not be written to the media catalog:\n{exc}")
            self._refreshNotesLabel()


    def showPreviousPhoto(self):
        for i in range(self.currentIndex - 1, -1, -1):
            if os.path.isfile(self.photoList[i][0].get("fileName", "")):
                self.currentIndex = i
                self.changeEnlargement()
                return

    def showNextPhoto(self):
        n = len(self.photoList)
        for i in range(self.currentIndex + 1, n):
            if os.path.isfile(self.photoList[i][0].get("fileName", "")):
                self.currentIndex = i
                self.changeEnlargement()
                return
            
                                  
    def fillEnlargement(self):

        # Skip forward (wrapping) to the first photo file that exists on disk.
        n = len(self.photoList)
        for i in range(n):
            idx = (self.currentIndex + i) % n
            if os.path.isfile(self.photoList[idx][0].get("fileName", "")):
                self.currentIndex = idx
                break
        else:
            QMessageBox.warning(
                self,
                "Photos Not Found",
                "None of the photos in this view could be found on disk.\n\n"
                "They may have been moved or deleted outside of Yearbirder.",
                QMessageBox.StandardButton.Ok,
            )
            QTimer.singleShot(0, self.close)
            return

        self.pixmapEnlargement = QPixmap(self.photoList[self.currentIndex][0]["fileName"])

        self.sceneEnlargement= QGraphicsScene()
        if self.pixmapEnlargement.isNull():
            self.itemPixmap = self.sceneEnlargement.addPixmap(QPixmap())
        else:
            self.itemPixmap = self.sceneEnlargement.addPixmap(self.pixmapEnlargement)

        self.viewEnlargement = self.MyGraphicsView() 
        self.viewEnlargement.mdiParent = self               
        self.viewEnlargement.setScene(self.sceneEnlargement)
        self.viewEnlargement.setStyleSheet("QWidget{ background-color: #343333;}")
        
        # add viewEnlargement to the default layout of the form
        self.layout().addWidget(self.viewEnlargement)

        # overlay widget for crossfade transitions (child of view, on top)
        self._crossfadeOverlay = self._CrossfadeOverlay(self.viewEnlargement)

        self.setCameraDetails()

        self.setPhotoTitle()

        # Fit the photo to the view synchronously, BEFORE the window is shown, so
        # it snaps to its final size instead of visibly scaling up after the
        # window appears (very noticeable on a slow machine).  activate() sizes
        # viewEnlargement to its final dimensions while hidden — but a
        # QGraphicsView's *viewport* (which fitInView measures) is not resized to
        # match its view until the view is first shown; while hidden it stays at
        # Qt's default 640x480.  Diagnostics confirmed the hidden fit used
        # viewport=640x480 while the view was already 729x572, so the photo was
        # fitted ~15% too small and then grew after show.  Force the viewport to
        # the view's size so the hidden fit is already the final fit.
        self.layout().activate()
        self.viewEnlargement.viewport().resize(self.viewEnlargement.size())
        self.fitEnlargement()
        # Safety-net refit after show (e.g. spawned into a maximized parent whose
        # deferred maximize changes the final view size).
        QTimer.singleShot(10, self.fitEnlargement)


    def changeEnlargement(self):

        # Capture the outgoing frame as a snapshot for the crossfade overlay
        if self._crossfadeOverlay is not None and not self.pixmapEnlargement.isNull():
            overlay = self._crossfadeOverlay
            overlay.setGeometry(0, 0, self.viewEnlargement.width(), self.viewEnlargement.height())
            overlay._pixmap = self.viewEnlargement.grab()
            overlay._alpha  = 1.0
            overlay.show()
            overlay.raise_()
            self._blendTimer.start(BLEND_INTERVAL)

        self.pixmapEnlargement = QPixmap(self.photoList[self.currentIndex][0]["fileName"])

        if self.pixmapEnlargement.isNull():
            self.sceneEnlargement.clear()
            self.itemPixmap = self.sceneEnlargement.addPixmap(QPixmap())
        else:
            self.itemPixmap.setPixmap(self.pixmapEnlargement)

        self.setCameraDetails()

        self.setPhotoTitle()

        QTimer.singleShot(20, self.fitEnlargement)


    def _blendStep(self):
        self._crossfadeOverlay._alpha -= BLEND_INTERVAL / BLEND_DURATION
        if self._crossfadeOverlay._alpha <= 0.0:
            self._crossfadeOverlay._alpha = 0.0
            self._blendTimer.stop()
            self._crossfadeOverlay.hide()
        self._crossfadeOverlay.update()
                

    def fitEnlargement(self):

        if self.pixmapEnlargement.isNull():
            return
        # scale the view to fit the photo, edge to edge
        self.viewEnlargement.setSceneRect(0, 0, self.pixmapEnlargement.width(), self.pixmapEnlargement.height())
        self.viewEnlargement.fitInView(self.viewEnlargement.sceneRect(), Qt.KeepAspectRatio)
                
        
    def setPhotoTitle(self):
        
        # display the file name in the window title bar
        basename = os.path.basename(self.photoList[self.currentIndex][0]["fileName"])
        self.setWindowTitle(basename) 
        
        
    def toggleCameraDetails(self):

        # toggle visibility of cameraDetails
        self._setDetailsPaneVisible(not self.detailsPane.isVisible())

    def _setDetailsPaneVisible(self, visible):
        """Show/hide detailsPane. When the window isn't maximized, the pane is
        added to (or removed from) the window's width so the photo area keeps
        its own width — rather than the pane eating into the photo's space.
        While maximized there's no extra screen space to grow into, so it
        falls back to resizing the photo area in place, as before."""
        if visible == self.detailsPane.isVisible():
            return

        if self.isMaximized() or self._fullScreen:
            self.detailsPane.setVisible(visible)
        else:
            delta = DETAILS_PANE_WIDTH if visible else -DETAILS_PANE_WIDTH
            self.detailsPane.setVisible(visible)
            self.resize(self.width() + delta, self.height())

        QTimer.singleShot(10, self.fitEnlargement)


    def toggleHideCursor(self):

        # toggle visibility of the cursor — only in full screen
        if not self._fullScreen:
            return()
        
        if self.cursorIsVisible is True:
            QApplication.setOverrideCursor(QCursor(Qt.BlankCursor))
            self.cursorIsVisible = False
        else:
            QApplication.restoreOverrideCursor()
            self.cursorIsVisible = True   
        

    def detachFile(self):
        
        # remove photo from database, but don't delete it from file system
        msgText = "Remove \n\n" + self.photoList[self.currentIndex][0]["fileName"] + "\n\n from the media catalog?"
        msgText = msgText + "\n\n(File will NOT be deleted from file system)"

        buttonClicked = code_Stylesheet.question(self, "Remove photo from catalog?", msgText)

        if buttonClicked == QMessageBox.StandardButton.Yes:
                
            # remove photo from database
            currentPhoto = self.photoList[self.currentIndex][0]["fileName"]
            photoCommonName = self.photoList[self.currentIndex][1]["commonName"]
            photoLocation = self.photoList[self.currentIndex][1]["location"] 
            
            self.mdiParent.mdiParent.db.removePhotoFromDatabase(photoLocation, "", "", photoCommonName, currentPhoto)
            try:
                self.mdiParent.mdiParent.db.appendPhotoDeletionToJsonl(currentPhoto)
            except IOError as exc:
                QMessageBox.warning(self, "Settings File Error",
                    f"Photo removed from memory but could not be recorded in the media catalog:\n{exc}")

            # free the photo's on-disk cache now that it's out of the catalog
            self.mdiParent.mdiParent.evictMediaCacheIfUnreferenced(currentPhoto)

            # set flag for requiring photo file save
            self.mdiParent.mdiParent.db.photosNeedSaving = True

            # Tell every open window the photo left the catalog, then drop it
            # from this window's own list.  Removal from the catalog has exactly
            # the same consequences for open windows as deleting the file, so it
            # takes the same broadcast (see deleteFile) — refreshing only the
            # parent Photos grid left every other window stale, and the grid
            # itself stale whenever the re-query came back empty.  Ordered so
            # this window handles itself last: it may close on the final photo.
            self.mdiParent.mdiParent.notifyPhotoDeletion(currentPhoto, exclude=self)
            self.handlePhotoDeletion(currentPhoto)


    def deleteFile(self):

        msgText = "Permanently delete \n\n" + self.photoList[self.currentIndex][0]["fileName"] + "\n\n from Yearbirder and the file system?"

        if code_Stylesheet.question(self, "Permanently delete photo?", msgText) != QMessageBox.StandardButton.Yes:
            return

        currentPhoto = self.photoList[self.currentIndex][0]["fileName"]
        photoCommonName = self.photoList[self.currentIndex][1]["commonName"]
        photoLocation = self.photoList[self.currentIndex][1]["location"]

        self.mdiParent.mdiParent.db.removePhotoFromDatabase(photoLocation, "", "", photoCommonName, currentPhoto)
        try:
            self.mdiParent.mdiParent.db.appendPhotoDeletionToJsonl(currentPhoto)
        except IOError as exc:
            QMessageBox.warning(self, "Settings File Error",
                f"Photo removed from memory but could not be recorded in the media catalog:\n{exc}")

        self.mdiParent.mdiParent.db.photosNeedSaving = True

        # Evict the on-disk cache while the file still exists (the cache key needs
        # its mtime/size), before unlinking it below.
        self.mdiParent.mdiParent.evictMediaCacheIfUnreferenced(currentPhoto)

        if os.path.isfile(currentPhoto):
            try:
                os.remove(currentPhoto)
            except:
                pass

        # Same two-step as detachFile: broadcast to the others, then handle this
        # window explicitly — in full screen it is detached from the MDI area and
        # the broadcast can't reach it.
        self.mdiParent.mdiParent.notifyPhotoDeletion(currentPhoto, exclude=self)
        self.handlePhotoDeletion(currentPhoto)


    def handlePhotoDeletion(self, filename):
        idx = next((i for i, (p, s) in enumerate(self.photoList) if p["fileName"] == filename), None)
        if idx is None:
            return
        self.photoList.pop(idx)
        if idx == self.currentIndex:
            if not self.photoList:
                self.close()
                return
            if self.currentIndex >= len(self.photoList):
                self.currentIndex -= 1
            self.changeEnlargement()
        elif idx < self.currentIndex:
            self.currentIndex -= 1

            
    def toggleFullScreen(self):
        # Called via QTimer.singleShot(0, ...) from all key/menu handlers so that
        # this runs after the triggering event handler has fully returned.
        # Full-screen state is tracked by self._fullScreen (used for detection
        # everywhere — Esc handling, cursor hide, the context-menu label).
        #
        # DETACH this enlargement from the MDI area and show it as a top-level
        # full-screen window, fading it in/out, leaving the main window untouched
        # behind it.  Used on BOTH platforms: it avoids Windows' desktop-exposing
        # restore / chrome flicker / black-MDI flash AND macOS's native
        # full-screen animation (which moves the app to its own Space, briefly
        # exposing other windows and flickering the menu bar).  The main window's
        # own window state never changes — the transition is a single top-level
        # window fading in/out.
        mainWindow = self.mdiParent.mdiParent
        mdiArea = mainWindow.mdiArea

        if not self._fullScreen:
            # ── Enter full screen ────────────────────────────────────────────
            self._mdiGeometry = self.geometry()
            # Remember the functional MDI-subwindow flags (title bar, system menu,
            # min/max/close buttons) so they can be restored on exit.
            self._savedFlags = self.windowFlags()
            mdiArea.removeSubWindow(self)      # detach: self becomes top-level
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
            self.showFullScreen()
            self.setWindowOpacity(0.0)         # invisible; faded in below
            self._fullScreen = True
            # Register as THE full-screen child: detached and frameless, this
            # window is unreachable from the Windows menu, Cmd-` and App Exposé,
            # so MainWindow has to raise it when the app is re-activated.
            mainWindow._fullScreenChild = self
            # Fit to the now-full-screen view.  A QGraphicsView's viewport isn't
            # resized to match its view until shown, so force it before fitting.
            self.layout().activate()
            self.viewEnlargement.viewport().resize(self.viewEnlargement.size())
            self.fitEnlargement()
            self.activateWindow()
            self.setFocus()
            # The finished full-screen frame is composed (still invisible at
            # opacity 0) — fade it in over the app behind it.
            self._startFade(0.0, 1.0)
        else:
            # ── Exit full screen ─────────────────────────────────────────────
            self._fullScreen = False
            if mainWindow._fullScreenChild is self:
                mainWindow._fullScreenChild = None
            QApplication.restoreOverrideCursor()
            # Fade out, then re-attach to the MDI in the finished callback.
            self._startFade(1.0, 0.0, on_done=self._reattachFromFullScreen)
            return

        QTimer.singleShot(0, self.fitEnlargement)


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
        """Called when the exit fade-out finishes: return this window to the MDI
        area (main window was never touched) and restore it as a normal child."""
        mdiArea = self.mdiParent.mdiParent.mdiArea
        self.showNormal()
        mdiArea.addSubWindow(self)
        # Restore the ORIGINAL subwindow flags — setting only Qt.SubWindow strips
        # the title-bar/system-menu/button hints, leaving a frozen, decoration-
        # less window (the MDI area still tracks it, but it can't be moved/closed).
        if self._savedFlags is not None:
            self.setWindowFlags(self._savedFlags)
        if self._mdiGeometry is not None:
            self.setGeometry(self._mdiGeometry)
        self.setWindowOpacity(1.0)   # undo the fade (harmless on an MDI child)
        # Fit to the restored MDI size BEFORE showing, so the photo reappears
        # already at its final size instead of visibly re-scaling.  (The window
        # is hidden here, so force the QGraphicsView viewport to the view size —
        # while hidden it stays at Qt's default 640x480 and fitInView would
        # otherwise measure the wrong size.)
        self.layout().activate()
        self.viewEnlargement.viewport().resize(self.viewEnlargement.size())
        self.fitEnlargement()
        self.show()
        mdiArea.setActiveSubWindow(self)
        self.activateWindow()
        self.setFocus()
        QTimer.singleShot(0, self.fitEnlargement)


    def editAssignment(self):
        """Open Manage Photos on just the photo being enlarged, so its species
        or location assignment can be changed.

        Full screen has to unwind first: full screen detaches this window from
        the MDI area and shows it top-level (see toggleFullScreen), so a new MDI
        child would be created behind it and never seen.  The window is opened
        from the fade's completion callback, once the re-attach has finished."""
        import code_ManagePhotos
        import code_RenameMedia

        if not self.photoList:
            return

        main_window = self.mdiParent.mdiParent

        # Manage Photos holds unsaved edits, so a second one editing the same
        # catalog can conflict — the app guards this elsewhere the same way.
        for w in main_window.mdiArea.subWindowList():
            if isinstance(w, code_ManagePhotos.ManagePhotos):
                QMessageBox.warning(
                    self, "Manage Photos Already Open",
                    "A Manage Photos window is already open.\n\n"
                    "Please close it before editing this photo's assignment.")
                return
            if isinstance(w, code_RenameMedia.RenameMedia):
                QMessageBox.warning(
                    self, "Close Rename Media First",
                    "Please close the Rename Media window before editing photos.\n\n"
                    "Having both windows open at the same time could cause conflicts.")
                return

        if self._fullScreen:
            self.toggleFullScreen()
            # toggleFullScreen fades out and re-attaches in a callback; queue the
            # open behind that rather than racing it.
            QTimer.singleShot(FADE_MS + 60, self._openManagePhotosForCurrent)
            return

        self._openManagePhotosForCurrent()


    def _openManagePhotosForCurrent(self):
        """Spawn the single-photo Manage Photos window (see editAssignment)."""
        import code_ManagePhotos

        if not self.photoList:
            return

        photoData, sightingData = self.photoList[self.currentIndex]
        main_window = self.mdiParent.mdiParent

        sub = code_ManagePhotos.ManagePhotos()
        sub.mdiParent = main_window

        # Built hidden and revealed on contentReady, as the other Manage Photos
        # entry points do — the row's thumbnail loads on a worker thread.
        main_window.mdiArea.addSubWindow(sub)
        main_window.PositionChildWindow(sub, main_window)

        def _reveal():
            sub.show()
            main_window.mdiArea.setActiveSubWindow(sub)
            sub.raise_()
            sub.setFocus()
        sub.contentReady.connect(_reveal)

        sub.FillSinglePhoto(photoData, sightingData)


    def launchSlideshow(self):
        import code_Slideshow
        import random

        if not self.photoList:
            return

        main_window = self.mdiParent.mdiParent
        dlg = code_Slideshow.SlideshowDialog(main_window)
        if dlg.exec() != code_Slideshow.QDialog.DialogCode.Accepted:
            return

        pairs = list(self.photoList)   # shallow copy — don't mutate the window's list
        sort_order = dlg.sortOrder()

        if sort_order == "alphabetic":
            pairs.sort(key=lambda x: (x[1].get("commonName", "").lower(),
                                      x[1].get("date", "")))
        elif sort_order == "rating":
            def _rating(pair):
                try:
                    return -int(pair[0].get("rating", "0") or "0")
                except ValueError:
                    return 0
            pairs.sort(key=lambda x: (_rating(x),
                                      float(x[1].get("taxonomicOrder", 0))))
        elif sort_order == "chronological":
            pairs.sort(key=lambda x: (x[1].get("date", ""), x[1].get("time", "")))
        elif sort_order == "location":
            pairs.sort(key=lambda x: (x[1].get("location", "").lower(),
                                      x[1].get("date", "")))
        elif sort_order == "random":
            random.shuffle(pairs)
        elif sort_order == "seasonal":
            def _mmdd(pair):
                d = pair[1].get("date", "")
                return d[5:] if len(d) >= 7 else ""
            pairs.sort(key=lambda x: (_mmdd(x), x[1].get("date", "")))
        else:  # taxonomic
            pairs.sort(key=lambda x: (float(x[1].get("taxonomicOrder", 0)),
                                      x[1].get("date", ""),
                                      x[1].get("time", "")))

        main_window._slideshow = code_Slideshow.SlideshowWindow(
            pairs, dlg.secondsPerPhoto(), dlg.showTitleBar()
        )
        main_window._slideshow.show()


    def setCameraDetails(self):
        
        currentPhoto = self.photoList[self.currentIndex][0]["fileName"]
        photoRating = self.photoList[self.currentIndex][0]["rating"]
        
        photoCommonName = self.photoList[self.currentIndex][1]["commonName"]
        photoScientificName = self.photoList[self.currentIndex][1]["scientificName"]
        photoLocation = self.photoList[self.currentIndex][1]["location"]
        
        # get EXIF data
        
        try:
            exif_dict = piexif.load(currentPhoto)
        except:
            exif_dict = ""
        
        # Photo creation date/time from the catalog (cached EXIF); fall back to
        # the checklist date/time when the photo has no stored creation date.
        exif_dt = self.photoList[self.currentIndex][0].get("exifDatetime")
        sighting = self.photoList[self.currentIndex][1]
        if exif_dt and len(exif_dt) >= 10:
            photoExifDate = exif_dt[0:4] + "-" + exif_dt[5:7] + "-" + exif_dt[8:10]
            photoExifTime = exif_dt[11:16] if len(exif_dt) >= 16 else ""
        else:
            photoExifDate = sighting.get("date", "")
            photoExifTime = sighting.get("time", "")
        try:
            photoWeekday = datetime.datetime(
                int(photoExifDate[0:4]), int(photoExifDate[5:7]), int(photoExifDate[8:10])
            ).strftime("%A") + ", "
        except Exception:
            photoWeekday = ""
            
        try:
            photoExifModel = exif_dict["0th"][piexif.ImageIFD.Model].decode("utf-8")
        except:
            photoExifModel = ""
        try:
            photoExifLensModel = exif_dict["Exif"][piexif.ExifIFD.LensModel].decode("utf-8")
        except:
            photoExifLensModel = ""
        
        try:        
            photoExifExposureTime = exif_dict["Exif"][piexif.ExifIFD.ExposureTime]
            photoExifExposureTime = "1/" + str(floor(photoExifExposureTime[1] / photoExifExposureTime[0])) + " sec"
        except:
            photoExifExposureTime = ""

        try:
            photoExifAperture = exif_dict["Exif"][piexif.ExifIFD.FNumber]
            photoExifAperture = round(photoExifAperture[0] / photoExifAperture[1], 1)
        except:
            photoExifAperture = ""
            
        try:
            photoExifISO = exif_dict["Exif"][piexif.ExifIFD.ISOSpeedRatings]
        except:
            photoExifISO = ""
        
        # get pixel dimensions from the already-loaded full-resolution pixmap
        # (setCameraDetails always runs right after pixmapEnlargement is set
        # for this same file — re-decoding the JPEG just for its dimensions
        # doubled the decode cost of every photo navigation)
        if not self.pixmapEnlargement.isNull():
            photoDimensions = (f"{self.pixmapEnlargement.width()} x "
                               f"{self.pixmapEnlargement.height()}")
        else:
            photoDimensions = ""

        
        try:
            photoExifFocalLength = exif_dict["Exif"][piexif.ExifIFD.FocalLength]
            photoExifFocalLength = floor(photoExifFocalLength[0] / photoExifFocalLength[1])
            photoExifFocalLength = str(photoExifFocalLength) + " mm"
            
        except:
            photoExifFocalLength = ""
            
        self.commonName.setText(photoCommonName)
        self.scientificName.setText(photoScientificName)

#         detailsText = photoCommonName + "\n"
#         detailsText = photoScientificName + "\n"
        # Rich text (set explicitly below) so the italic "f" in the
        # exposure/aperture line renders — every line break must therefore be
        # an explicit <br>, not a literal "\n".
        detailsText = "<br><br>" + photoLocation + "<br>"
        detailsText = detailsText + photoWeekday + photoExifDate + " " + photoExifTime + "<br>"
        detailsText = detailsText + "<br>"
        detailsText = detailsText + photoExifModel + "<br>"
        detailsText = detailsText + photoExifLensModel + "<br>"
        detailsText = detailsText + str(photoExifFocalLength) + "<br>"
        detailsText = detailsText + str(photoExifExposureTime) + ", <i>f</i>/" + str(photoExifAperture) + ", ISO " + str(photoExifISO) + "<br>"
        detailsText = detailsText + str(photoDimensions) + "<br>"
        _fname = (ntpath.basename(currentPhoto)
                  .replace('_', '_​')
                  .replace('-', '-​')
                  .replace('.', '.​'))
        detailsText = detailsText + "<br>" + _fname
        detailsText = detailsText + "<br>"  # line feed between the file name and the Notes field

        if photoRating == "0":
            self.star1.setIcon(QIcon(QPixmap(":/icon_star_gray.png")))
            self.star2.setIcon(QIcon(QPixmap(":/icon_star_gray.png")))
            self.star3.setIcon(QIcon(QPixmap(":/icon_star_gray.png")))
            self.star4.setIcon(QIcon(QPixmap(":/icon_star_gray.png")))
            self.star5.setIcon(QIcon(QPixmap(":/icon_star_gray.png")))
        if photoRating == "1":
            self.star1.setIcon(QIcon(QPixmap(":/icon_star.png")))
            self.star2.setIcon(QIcon(QPixmap(":/icon_star_gray.png")))
            self.star3.setIcon(QIcon(QPixmap(":/icon_star_gray.png")))
            self.star4.setIcon(QIcon(QPixmap(":/icon_star_gray.png")))
            self.star5.setIcon(QIcon(QPixmap(":/icon_star_gray.png")))
        if photoRating == "2":
            self.star1.setIcon(QIcon(QPixmap(":/icon_star.png")))
            self.star2.setIcon(QIcon(QPixmap(":/icon_star.png")))
            self.star3.setIcon(QIcon(QPixmap(":/icon_star_gray.png")))
            self.star4.setIcon(QIcon(QPixmap(":/icon_star_gray.png")))
            self.star5.setIcon(QIcon(QPixmap(":/icon_star_gray.png")))
        if photoRating == "3":
            self.star1.setIcon(QIcon(QPixmap(":/icon_star.png")))
            self.star2.setIcon(QIcon(QPixmap(":/icon_star.png")))
            self.star3.setIcon(QIcon(QPixmap(":/icon_star.png")))
            self.star4.setIcon(QIcon(QPixmap(":/icon_star_gray.png")))
            self.star5.setIcon(QIcon(QPixmap(":/icon_star_gray.png")))
        if photoRating == "4":
            self.star1.setIcon(QIcon(QPixmap(":/icon_star.png")))
            self.star2.setIcon(QIcon(QPixmap(":/icon_star.png")))
            self.star3.setIcon(QIcon(QPixmap(":/icon_star.png")))
            self.star4.setIcon(QIcon(QPixmap(":/icon_star.png")))
            self.star5.setIcon(QIcon(QPixmap(":/icon_star_gray.png")))
        if photoRating == "5":
            self.star1.setIcon(QIcon(QPixmap(":/icon_star.png")))
            self.star2.setIcon(QIcon(QPixmap(":/icon_star.png")))
            self.star3.setIcon(QIcon(QPixmap(":/icon_star.png")))
            self.star4.setIcon(QIcon(QPixmap(":/icon_star.png")))
            self.star5.setIcon(QIcon(QPixmap(":/icon_star.png")))            

        self.cameraDetails.setText(detailsText)

        self._refreshNotesLabel()

        