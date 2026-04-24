import form_Enlargement
import code_Filter
import code_Stylesheet
import datetime
import ntpath

from shiboken6 import isValid

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
    QSize
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
    QWidget
    )

BLEND_DURATION = 300   # crossfade duration in ms
BLEND_INTERVAL = 16    # timer tick in ms (~60 fps)
   

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
            self.mdiParent = "" 
            
            
        def wheelEvent(self,event):        
            adj = 1 + event.angleDelta().y()/120 * 0.1
            self.scale(adj, adj)


        # we need a keepress event handler here in case the user clicks on the photo.
        # when user clicks on the photo, the keypress handler is this GraphicsView, not the Englargement class.
        def keyPressEvent(self, e):
                        
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
            if e.key() == Qt.Key_Escape and self.mdiParent.mdiParent.mdiParent.statusBar.isVisible() is False:
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
            
            actionFitToWindow = menu.addAction("Fit to window (F)")
            menu.addSeparator()
            actionShowNextPhoto = menu.addAction("Next photo (Right arrow)")
            actionShowPreviousPhoto = menu.addAction("Previous photo (Left arrow)")
            menu.addSeparator()
            
            if self.mdiParent.isMaximized() is True:
                if self.mdiParent.cursorIsVisible:
                    actionToggleHideCursor = menu.addAction("Hide cursor (F7)")
                else:
                    actionToggleHideCursor = menu.addAction("Show cursor (F7)")

            if self.mdiParent.detailsPane.isVisible():
                actionToggleCameraDetails = menu.addAction("Hide details (F9)")
            else:
                actionToggleCameraDetails = menu.addAction("Show details (F9)")

            if self.mdiParent.isMaximized() and self.mdiParent.mdiParent.mdiParent.isFullScreen():
                actionToggleFullScreen = menu.addAction("Exit full screen (F10)")
            else:
                actionToggleFullScreen = menu.addAction("Full screen (F10)")
                
            menu.addSeparator()
            actionSlideshow = menu.addAction("Slideshow")
            menu.addSeparator()
            actionDetachFile = menu.addAction("Detach photo from Yearbirder")
            menu.addSeparator()
            actionDeleteFile = menu.addAction("Delete photo from file system")

            action = menu.exec(self.mapToGlobal(event.pos()))

            if self.mdiParent.isMaximized() is True:
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
            
            if action == actionSlideshow:
                self.parent().launchSlideshow()

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
        self._crossfadeOverlay = None
        self._blendTimer = QTimer(self)
        self._blendTimer.timeout.connect(self._blendStep)

        self.layout().setDirection(QBoxLayout.Direction.RightToLeft)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)   
        self.setStyleSheet("color:silver; background-color: #343333")
        
        self.detailsPaneLayout = QVBoxLayout()
        self.detailsPaneLayout.setContentsMargins(0, 0, 0, 0)
        self.detailsPaneLayout.setSpacing(0)
        self.detailsPaneLayout.setAlignment(Qt.AlignCenter)
        
        
        self.detailsPane = QFrame()
        self.detailsPane.setLayout(self.detailsPaneLayout)
        self.detailsPane.setStyleSheet("color:silver; background-color: #343333")
        
        self.layout().addWidget(self.detailsPane)
        
        # create label for species common name
        self.commonName = QLabel()
        self.commonName.setStyleSheet("font:12pt; font-weight:bold; color:silver; background-color: #343333; padding: 3px")                
        self.detailsPaneLayout.addWidget(self.commonName)

        # create label for species scientific name
        self.scientificName = QLabel()
        self.scientificName.setStyleSheet("font:12pt; font-style:italic; color:silver; background-color: #343333; padding: 3px")                
        self.detailsPaneLayout.addWidget(self.scientificName)

        # create label for camera details text
        self.cameraDetails = QLabel()
        self.cameraDetails.setStyleSheet("color:silver; background-color: #343333; padding: 3px")                
        self.detailsPane.setVisible(False)
        self.detailsPaneLayout.addWidget(self.cameraDetails)
                
        # create horizontal layout to show rating stars
        self.horizontalGroupBox = QGroupBox()
        self.horizontalGroupBox.setContentsMargins(0, 0, 0, 0)
        self.horizontalGroupBox.setStyleSheet("background-color: #343333; padding: 3px")
                
        self.detailsPaneLayout.addWidget(self.horizontalGroupBox)
        
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
        
        self.star1.setStyleSheet("QPushButton:pressed{ background-color: #343333; }")
        self.star1.setStyleSheet("QPushButton:hover{ background-color: #343333; }")
        self.star1.setStyleSheet("QPushButton:flat{ background-color: #343333; }")
        self.star1.setStyleSheet("QPushButton{ background-color: #343333; border:none }")        
        self.star2.setStyleSheet("QPushButton:pressed{ background-color: #343333; }")
        self.star2.setStyleSheet("QPushButton:hover{ background-color: #343333; }")
        self.star2.setStyleSheet("QPushButton:flat{ background-color: #343333; }")
        self.star2.setStyleSheet("QPushButton{ background-color: #343333; border:none }")        
        self.star3.setStyleSheet("QPushButton:pressed{ background-color: #343333; }")
        self.star3.setStyleSheet("QPushButton:hover{ background-color: #343333; }")
        self.star3.setStyleSheet("QPushButton:flat{ background-color: #343333; }")
        self.star3.setStyleSheet("QPushButton{ background-color: #343333; border:none }")        
        self.star4.setStyleSheet("QPushButton:pressed{ background-color: #343333; }")
        self.star4.setStyleSheet("QPushButton:hover{ background-color: #343333; }")
        self.star4.setStyleSheet("QPushButton:flat{ background-color: #343333; }")
        self.star4.setStyleSheet("QPushButton{ background-color: #343333; border:none }")        
        self.star5.setStyleSheet("QPushButton:pressed{ background-color: #343333; }")
        self.star5.setStyleSheet("QPushButton:hover{ background-color: #343333; }")
        self.star5.setStyleSheet("QPushButton:flat{ background-color: #343333; }")
        self.star5.setStyleSheet("QPushButton{ background-color: #343333; border:none }")        
        
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

        if e.key() == Qt.Key_Escape and not self.mdiParent.mdiParent.statusBar.isVisible():
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
        self.detailsPane.setVisible(True)
        db = self.mdiParent.mdiParent.db
        db.photosNeedSaving = True
        try:
            db.appendPhotoToJsonl(self.photoList[self.currentIndex][1], self.photoList[self.currentIndex][0])
        except IOError as exc:
            QMessageBox.warning(self, "Settings File Error",
                f"Rating saved in memory but could not be written to the photo catalog:\n{exc}")
        self.viewEnlargement.setFocus()
                                                

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
        if self.detailsPane.isVisible():
            self.detailsPane.setVisible(False)
        else:
            self.detailsPane.setVisible(True)
            
        QTimer.singleShot(10, self.fitEnlargement)   


    def toggleHideCursor(self):

        # toggle visibility of the cursor
        if not self.isMaximized():
            return()

        if not self.mdiParent.mdiParent.isFullScreen():
            return()
        
        if self.cursorIsVisible is True:
            QApplication.setOverrideCursor(QCursor(Qt.BlankCursor))
            self.cursorIsVisible = False
        else:
            QApplication.restoreOverrideCursor()
            self.cursorIsVisible = True   
        

    def detachFile(self):
        
        # remove photo from database, but don't delete it from file system
        msgText = "Detach \n\n" + self.photoList[self.currentIndex][0]["fileName"] + "\n\n from Yearbirder?"
        msgText = msgText + "\n\n(File will NOT be deleted from file system)"
        
        buttonClicked = code_Stylesheet.question(self, "Detach photo?", msgText)

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
                    f"Photo removed from memory but could not be recorded in the photo catalog:\n{exc}")

            # remove photo from current window's photo list
            self.photoList.remove(self.photoList[self.currentIndex])

            # refresh display of parent photo list
            if isValid(self.mdiParent):
                self.mdiParent.FillPhotos(self.mdiParent.filter)

            # advance display to next photo
            if len(self.photoList) == 0:
                self.close()
                return

            if self.currentIndex < len(self.photoList):
                self.changeEnlargement()

            else:
                self.currentIndex -= 1
                self.changeEnlargement()

            # set flag for requiring photo file save
            self.mdiParent.mdiParent.db.photosNeedSaving = True


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
                f"Photo removed from memory but could not be recorded in the photo catalog:\n{exc}")

        self.mdiParent.mdiParent.db.photosNeedSaving = True

        if os.path.isfile(currentPhoto):
            try:
                os.remove(currentPhoto)
            except:
                pass

        self.mdiParent.mdiParent.notifyPhotoDeletion(currentPhoto)


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
        # Note: setUpdatesEnabled(False) cannot be used here — on macOS's Cocoa
        # backend it conflicts with native window operations (showFullScreen,
        # setWindowFlags) and causes a fatal crash via sendPostedEvents.
        #
        # Operation order is chosen to minimise visible intermediate states:
        # entering — child maximises first (image already fills MDI area), then
        # chrome hides and the main window expands to screen.
        # exiting  — chrome restores first, then main window shrinks, then child
        # returns to normal so the image never appears to "float" frameless.

        mainWindow = self.mdiParent.mdiParent

        if not mainWindow.isFullScreen():
            self.showMaximized()
            self.setWindowFlags(Qt.FramelessWindowHint)
            mainWindow.dckFilter.setVisible(False)
            mainWindow.dckPhotoFilter.setVisible(False)
            mainWindow.menuBar.setVisible(False)
            mainWindow.toolBar.setVisible(False)
            mainWindow.statusBar.setVisible(False)
            mainWindow.showFullScreen()

        else:
            mainWindow.dckFilter.setVisible(True)
            mainWindow.dckPhotoFilter.setVisible(True)
            mainWindow.menuBar.setVisible(True)
            mainWindow.toolBar.setVisible(True)
            mainWindow.statusBar.setVisible(True)
            self.setWindowFlags(Qt.SubWindow)
            mainWindow.showMaximized()
            self.showNormal()
            QApplication.restoreOverrideCursor()

        QTimer.singleShot(0, self.fitEnlargement)
                    
            
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
        
        # get photo date from EXIF
        try:
            photoDateTime = exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal].decode("utf-8")
            
            #parse EXIF data for date/time components
            photoExifDate = photoDateTime[0:4] + "-" + photoDateTime[5:7] + "-" + photoDateTime[8:10]
            photoExifTime = photoDateTime[11:13] + ":" + photoDateTime[14:16]
            
            photoWeekday = datetime.datetime(int(photoDateTime[0:4]), int(photoDateTime[5:7]), int(photoDateTime[8:10]))
            photoWeekday = photoWeekday.strftime("%A") + ", "
            
        except:
            photoExifDate = "Date unknown"
            photoExifTime = "Time unknown"
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
        
        # get pixel dimensions

        from PySide6.QtGui import QImage
        qimg = QImage(currentPhoto)
        if not qimg.isNull():
            photoDimensions = f"{qimg.width()} x {qimg.height()}"
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
        detailsText = "\n\n" + photoLocation + "\n"
        detailsText = detailsText + photoWeekday + photoExifDate + "\n"
        detailsText = detailsText + photoExifTime + "\n"
        detailsText = detailsText + "\n"
        detailsText = detailsText + photoExifModel + "\n"
        detailsText = detailsText + photoExifLensModel + "\n"
        detailsText = detailsText + "Focal Length: " + str(photoExifFocalLength) + "\n"
        detailsText = detailsText + str(photoExifExposureTime) + "\n"
        detailsText = detailsText + "Aperture: " + str(photoExifAperture) + "\n"
        detailsText = detailsText + "ISO: " + str(photoExifISO) + "\n"
        detailsText = detailsText + "Dimensions: " + str(photoDimensions) + " pixels\n"
        detailsText = detailsText + "\n\n" + ntpath.basename(currentPhoto)
        detailsText = detailsText + "\n\n\n"  #add space to separate rating stars from text
        
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
        
        