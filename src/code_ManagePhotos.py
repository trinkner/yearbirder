# import project files
import form_ManagePhotos
import code_Filter
import code_Stylesheet
import os

import piexif

# import basic Python libraries
import queue
from functools import partial

from collections import defaultdict

from PySide6.QtGui import (
    QPixmap,
    QFont,
    QIcon,
    QImage,
    QTransform,
    QCursor
    )

from PySide6.QtCore import (
    Signal,
    QSize,
    Qt,
    QThread,
    )

from PySide6.QtWidgets import (
    QMdiSubWindow,
    QPushButton,
    QApplication,
    QWidget,
    QLabel,
    QComboBox,
    QVBoxLayout
    )
    

class threadGetPhotoData(QThread):

    sigProcessedPhoto = Signal(dict)
    sigThreadFinished = Signal()

    def __init__(self):

        QThread.__init__(self)

        self.parent = ""
        self.workQueue = None

    def __del__(self):

        self.wait()


    def run(self):

        while True:

            # pull the next job; exit cleanly when the queue is empty
            try:
                item = self.workQueue.get_nowait()
            except queue.Empty:
                break

            row = item[0]
            file = item[1]

            # read EXIF once and share it across all three functions
            try:
                exif_dict = piexif.load(file)
            except:
                exif_dict = {}

            photoData = self.parent.mdiParent.db.getPhotoData(file, exif_dict)
            photoMatchData = self.parent.mdiParent.db.matchPhoto(file, exif_dict)
            pixMap = self.parent.GetPixmapForThumbnail(file, exif_dict)

            # pre-compute combo box data here in the worker thread so the
            # main thread can populate widgets without querying the database
            comboData = self.parent.mdiParent.db.getComboDataForPhoto(photoMatchData)

            thisPhotoDataEntry = defaultdict()
            thisPhotoDataEntry["row"] = row
            thisPhotoDataEntry["photoData"] = photoData
            thisPhotoDataEntry["photoMatchData"] = photoMatchData
            thisPhotoDataEntry["pixMap"] = pixMap
            thisPhotoDataEntry["comboData"] = comboData

            self.sigProcessedPhoto.emit(thisPhotoDataEntry)
            self.workQueue.task_done()

        self.sigThreadFinished.emit()
        


class ManagePhotos(QMdiSubWindow, form_ManagePhotos.Ui_frmManagePhotos):
    
    # create "resized" as a signal that the window can emit
    # we respond to this signal with the form's resizeMe method below
    resized = Signal()
    
    
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
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.photosAlreadyInDb = True
                
        # dynamic thread pool — sized to CPU count, capped at 8 for disk-bound work
        self.threadCount = min(os.cpu_count() or 4, 8)
        self.workQueue = queue.Queue()
        self.threadsRemaining = 0
        self.threads = []

        for _ in range(self.threadCount):
            t = threadGetPhotoData()
            t.parent = self
            t.workQueue = self.workQueue
            t.sigProcessedPhoto.connect(self.threadProcessedPhoto)
            t.sigThreadFinished.connect(self.threadFinished)
            self.threads.append(t)
        
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_camera_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon) 


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
                w.setFont(QFont("Helvetica", fontSize))
            except:
                pass
                        
        for c in self.layLists.children():
            if "QLabel" in str(c):
                c.setFont(QFont("Helvetica", fontSize))
         
        windowWidth =  int(1200  * scaleFactor)
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
            
            QApplication.processEvents()
                        
            # get file extension to process only jpg and tiff image files
            photoFileExtension = os.path.splitext(fileName)[1]
            
            # only process jpg and tiff files
            if photoFileExtension.lower() in [".jpg", ".jpeg", ".tif", "tiff"]:
                
                allowedPhotoFiles.append([row, fileName])
            
            row += 1
        
        # fill the shared work queue; threads pull jobs from it dynamically
        # so no thread sits idle while others still have work
        for item in allowedPhotoFiles:
            self.workQueue.put(item)

        # start only as many threads as there are photos to process
        threadsToStart = min(self.threadCount, len(allowedPhotoFiles))
        self.threadsRemaining = threadsToStart
        for i in range(threadsToStart):
            self.threads[i].start()
                
    
    def threadProcessedPhoto(self, thisPhotoDataEntry):

        self.insertPhotoIntoTable(
            thisPhotoDataEntry["row"],
            thisPhotoDataEntry["photoData"],
            thisPhotoDataEntry["photoMatchData"],
            thisPhotoDataEntry["pixMap"],
            thisPhotoDataEntry["comboData"],
            )                         
   
   
    def threadFinished(self):

        self.threadsRemaining -= 1
        if self.threadsRemaining == 0:
            self.scrollArea.verticalScrollBar().setValue(0)
            QApplication.restoreOverrideCursor()
              
                                
                                 
    def insertPhotoIntoTable(self, row, photoData, photoMatchData, pixMap, comboData):

        QApplication.processEvents()
                    
        self.fillingCombos = True
                                                                    
        photoLocation = photoMatchData["photoLocation"]
        photoDate = photoMatchData["photoDate"]
        photoTime = photoMatchData["photoTime"]
        photoCommonName = photoMatchData["photoCommonName"]
                            
        # p is a filename. Use it to add the image to the label as a pixmap
        buttonPhoto = QPushButton()
        buttonPhoto.setMinimumHeight(330)
        buttonPhoto.setMinimumWidth(500)
                
        buttonPhoto.setIcon(QIcon(pixMap))
        
        # size to 500x330
        buttonPhoto.setIconSize(QSize(500,330))    
        buttonPhoto.setStyleSheet("QPushButton {background-color: #343333; border: 0px}")

        # display thumbnail to new row in grid
        self.gridPhotos.addWidget(buttonPhoto, row, 0)  
        
        # set up layout in second column of row to house combo boxes
        # give each object a name according to the row so we can access them later
        container = QWidget()
        container.setObjectName("container" + str(row))
        detailsLayout = QVBoxLayout(container)
        detailsLayout.setObjectName("layout" + str(row)) 
        detailsLayout.setAlignment(Qt.AlignTop)

        self.gridPhotos.addWidget(container, row, 1)

        # create combo boxes for details
        # add connection for when user changes a combo box
        cboLocation = QComboBox()
        cboLocation.currentIndexChanged.connect(partial( self.cboLocationChanged, row))
        
        cboDate = QComboBox()
        cboDate.currentIndexChanged.connect(partial( self.cboDateChanged, row))
        
        cboTime = QComboBox()
        cboTime.currentIndexChanged.connect(partial( self.cboTimeChanged, row))
            
        cboCommonName = QComboBox()
        cboCommonName.currentIndexChanged.connect(partial( self.cboCommonNameChanged, row))
        
        cboRating = QComboBox()
        cboRating.addItems(["Not Rated", "1", "2", "3", "4", "5"])
        cboRating.currentIndexChanged.connect(partial( self.cboRatingChanged, row))  
              
        # set stylesheet for cbo boxes
        for c in [cboLocation, cboDate, cboTime, cboCommonName, cboRating]:
            self.removeHighlight(c)   

        # date-first cascade: use data pre-computed by the worker thread
        cboDate.addItems(comboData["allDates"])
        if photoDate != "":
            index = cboDate.findText(photoDate)
            if index >= 0:
                cboDate.setCurrentIndex(index)

        cboLocation.addItems(comboData["locationsByDate"])
        if photoLocation != "":
            index = cboLocation.findText(photoLocation)
            if index >= 0:
                cboLocation.setCurrentIndex(index)

        cboTime.addItems(comboData["timesByDateAndLocation"])
        if photoTime != "":
            index = cboTime.findText(photoTime)
            if index >= 0:
                cboTime.setCurrentIndex(index)

        cboCommonName.addItem("**None Selected**")
        cboCommonName.addItem("**Detach Photo**")
        cboCommonName.addItems(comboData["speciesByChecklist"])
        if photoCommonName != "":
            index = cboCommonName.findText(photoCommonName)
            if index >= 0:
                cboCommonName.setCurrentIndex(index)

        # assign names to combo boxes for future access
        cboLocation.setObjectName("cboLocation" + str(row))
        cboDate.setObjectName("cboDate" + str(row))
        cboTime.setObjectName("cboTime" + str(row))
        cboCommonName.setObjectName("cboCommonName" + str(row))
        cboRating.setObjectName("cboRating" + str(row))

        lblFileName = QLabel()
        lblFileName.setText("File: " + os.path.basename(photoData["fileName"]))

        lblFileDate = QLabel()
        lblFileDate.setText("Date: " + photoData["date"])

        lblFileTime = QLabel()
        lblFileTime.setText("Time: " + photoData["time"])
        
        # add combo boxes to the layout in second column (date-first order)
        detailsLayout.addWidget(lblFileName)
        detailsLayout.addWidget(lblFileDate)
        detailsLayout.addWidget(lblFileTime)
        detailsLayout.addWidget(cboDate)
        detailsLayout.addWidget(cboLocation)
        detailsLayout.addWidget(cboTime)
        detailsLayout.addWidget(cboCommonName)
        detailsLayout.addWidget(cboRating)

        # create and add resent button
        btnReset = QPushButton()
        btnReset.setText("Reset")
        btnReset.clicked.connect(partial( self.btnResetClicked, row))
        detailsLayout.addWidget(btnReset)

        # save meta data for future use when user clicks cbo boxes
        thisPhotoMetaData = {}
        thisPhotoMetaData["photoFileName"] = photoData["fileName"]
        thisPhotoMetaData["location"] = photoLocation
        thisPhotoMetaData["date"] = photoDate
        thisPhotoMetaData["time"] = cboTime.currentText()
        thisPhotoMetaData["commonName"] = photoCommonName
        thisPhotoMetaData["photoData"] = photoData
        thisPhotoMetaData["rating"] = thisPhotoMetaData["photoData"]["rating"]
        thisPhotoMetaData["cascadeMode"] = "date_first"

        self.metaDataByRow[row] = thisPhotoMetaData
        
        # initialize the "new" data so that there are values there, even if they're not really new
        # user can change the cbo boxes later, which will also change the "new" data 
        self.saveNewMetaData(row)
                                                            
        self.fillingCombos = False
                
                                  
    def FillPhotosByFilter(self, filter): 
        
        # it's tempting to think that we could use the insertPhotoIntoTable routine,
        # but we can't here, because if we're filling photos by filter, we already know
        # each photo's meta data.  The insertPhotoIntoTable routine tries to guess the
        # location, time, species, etc. from the photo file's embedded meta data.

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        self.scaleMe()
        self.resizeMe()
        
        self.fillingCombos = True
        
        # save the filter settings passed to this routine to the form itself for future use
        self.filter = filter
        
        photoSightings = self.mdiParent.db.GetSightingsWithPhotos(filter)

        if len(photoSightings) == 0:
            return False
        
        row = 0
        
        # count photos for message display
        photoCount = 0
        for s in photoSightings:
            photoCount = photoCount + len(s["photos"])
        photoCount = str(photoCount)

        for s in photoSightings:
            for p in s["photos"]:
                
                self.mdiParent.lblStatusBarMessage.setVisible(True)
                self.mdiParent.lblStatusBarMessage.setText("Processing photo " + str(row + 1) + " of " + photoCount)
                
                # p is a filename. Use it to add the image to the label as a pixmap
                buttonPhoto = QPushButton()
                buttonPhoto.setMinimumHeight(330)
                buttonPhoto.setMinimumWidth(500)
                
                # get thumbnail from file to display
                pixMap = self.GetPixmapForThumbnail(p["fileName"])
                
                buttonPhoto.setIcon(QIcon(pixMap))
                
                # size to 500x330
                buttonPhoto.setIconSize(QSize(500,330))    
                buttonPhoto.setStyleSheet("QPushButton {background-color: #343333; border: 0px}")

                # display thumbnail to new row in grid
                self.gridPhotos.addWidget(buttonPhoto, row, 0)  
                
                # set up layout in second column of row to house combo boxes
                # give each object a name according to the row so we can access them later
                container = QWidget()
                container.setObjectName("container" + str(row))
                detailsLayout = QVBoxLayout(container)
                detailsLayout.setObjectName("layout" + str(row)) 
                detailsLayout.setAlignment(Qt.AlignTop)
                self.gridPhotos.addWidget(container, row, 1)

                # create combo boxes for details
                # add connection for when user changes a combo box
                cboLocation = QComboBox()
                cboLocation.currentIndexChanged.connect(partial( self.cboLocationChanged, row))
                
                cboDate = QComboBox()
                cboDate.currentIndexChanged.connect(partial( self.cboDateChanged, row))
                
                cboTime = QComboBox()
                cboTime.currentIndexChanged.connect(partial( self.cboTimeChanged, row))
                    
                cboCommonName = QComboBox()
                cboCommonName.currentIndexChanged.connect(partial( self.cboCommonNameChanged, row))
                
                cboRating = QComboBox()
                cboRating.addItems(["Not Rated", "1", "2", "3", "4", "5"])
                cboRating.currentIndexChanged.connect(partial( self.cboRatingChanged, row))                  

                # set stylesheet for cmbo boxes
                for c in [cboLocation, cboDate, cboTime, cboCommonName, cboRating]:
                    self.removeHighlight(c)      

                # fill location combo box with all locations in db
                locations = self.mdiParent.db.locationList
                cboLocation.addItems(locations)
                
                # set location combo box to the photo's location
                index = cboLocation.findText(s["location"])
                if index >= 0:
                    cboLocation.setCurrentIndex(index)
                    
                # fill date combo box with all dates associated with selected location
                filterForThisPhoto = code_Filter.Filter()
                filterForThisPhoto.setLocationName(s["location"])
                filterForThisPhoto.setLocationType("Location")
                dates = self.mdiParent.db.GetDates(filterForThisPhoto)
                cboDate.addItems(dates)
                
                # set date  combo box to the photo's associated date
                index = cboDate.findText(s["date"])
                if index >= 0:
                    cboDate.setCurrentIndex(index)              
                    
                # fill time combo box with all times associated with selected location and date
                filterForThisPhoto.setStartDate(s["date"])
                filterForThisPhoto.setEndDate(s["date"])
                startTimes = self.mdiParent.db.GetStartTimes(filterForThisPhoto)
                cboTime.addItems(startTimes)
                
                # set time combo box to the photo's associated checklist time
                index = cboTime.findText(s["time"])
                if index >= 0:
                    cboTime.setCurrentIndex(index)                              
                                        
                # get common names from checklist associated with photo
                filterForThisPhoto.setChecklistID(s["checklistID"])
                commonNames = self.mdiParent.db.GetSpecies(filterForThisPhoto)
                
                cboCommonName.addItem("**Detach Photo**")
                cboCommonName.addItems(commonNames)  
                
                # set combo box to common name
                index = cboCommonName.findText(s["commonName"])
                if index >= 0:
                    cboCommonName.setCurrentIndex(index)   

                # set combo box to rating value
                index = int(p["rating"])
                cboRating.setCurrentIndex(index)
                    
                # assign names to combo boxes for future access
                cboLocation.setObjectName("cboLocation" + str(row))
                cboDate.setObjectName("cboDate" + str(row))
                cboTime.setObjectName("cboTime" + str(row))
                cboCommonName.setObjectName("cboCommonName" + str(row))
                cboRating.setObjectName("cboRating" + str(row))
                
                # add combo boxes to the layout in second column
                detailsLayout.addWidget(cboLocation)
                detailsLayout.addWidget(cboDate)
                detailsLayout.addWidget(cboTime)
                detailsLayout.addWidget(cboCommonName)
                detailsLayout.addWidget(cboRating)
                
                # create and add resent button
                btnReset = QPushButton()
                btnReset.setText("Reset")
                btnReset.clicked.connect(partial( self.btnResetClicked, row))
                detailsLayout.addWidget(btnReset)
                                
                # save meta data for future use when user clicks cbo boxes
                thisPhotoMetaData = {}
                thisPhotoMetaData["photoFileName"] = p["fileName"]
                thisPhotoMetaData["location"] = s["location"]
                thisPhotoMetaData["date"] = s["date"]
                thisPhotoMetaData["time"] = s["time"]
                thisPhotoMetaData["commonName"] = s["commonName"]
                thisPhotoMetaData["photoData"] = p
                thisPhotoMetaData["rating"] = p["rating"]
                thisPhotoMetaData["cascadeMode"] = "location_first"

                self.metaDataByRow[row] = thisPhotoMetaData

                # initialize the "new" data so that there are values there, even if they're not really new
                # user can change the cbo boxes later, which will also change the "new" data 
                self.saveNewMetaData(row)      
                
                row = row + 1
                
                qApp.processEvents()

        self.mdiParent.lblStatusBarMessage.setText("")
        self.mdiParent.lblStatusBarMessage.setVisible(False)
                                
        QApplication.processEvents()

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_camera_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon) 
        self.setWindowTitle("Manage Photos")
        
        self.fillingCombos = False
        
        QApplication.restoreOverrideCursor()         
                    
        # tell MainWindow that we succeeded filling the list
        return(True)


    def GetPixmapForThumbnail(self, photoFile, exif_dict=None):

        # use provided exif_dict (pre-loaded by caller) or load from file
        if exif_dict is None:
            try:
                exif_dict = piexif.load(photoFile)
            except:
                exif_dict = {}

        try:
            pmOrientation = int(exif_dict["0th"][piexif.ImageIFD.Orientation])
        except:
            pmOrientation = 1

        try:
            thumbimg = exif_dict["thumbnail"]
        except:
            thumbimg = None

        if thumbimg is None:
            qimage = QImage(photoFile)
        else:
            qimage = QImage()
            qimage.loadFromData(thumbimg, format='JPG')
        if pmOrientation == 2: qimage = qimage.mirrored(True,  False)
        if pmOrientation == 3: qimage = qimage.transformed(QTransform().rotate(180))
        if pmOrientation == 4: qimage = qimage.mirrored(False,  True)
        if pmOrientation == 5: 
            qimage = qimage.mirrored(True,  False)
            qimage = qimage.transformed(QTransform().rotate(270))
        if pmOrientation == 6: qimage = qimage.transformed(QTransform().rotate(90))
        if pmOrientation == 7:          
            qimage = qimage.mirrored(True,  False)
            qimage = qimage.transformed(QTransform().rotate(90))
        if pmOrientation == 8: qimage = qimage.transformed(QTransform().rotate(270))
        
        pm = QPixmap()
        pm.convertFromImage(qimage)
            
        if pm.height() > pm.width():
            pm = pm.scaledToHeight(330)
        else:
            pm = pm.scaledToWidth(500)
        return pm


    def cboLocationChanged(self, row):
        
        if self.fillingCombos == False:
            self.fillingCombos = True
    
            # get cboLocationChanged widget from the row that was clicked                
            container = self.gridPhotos.itemAtPosition(row, 1).widget()
            for w in container.children():
                if "cboLocation" in w.objectName():
                    cboLocation = w
                
            originalLocation = self.metaDataByRow[row]["location"]                
            
            if cboLocation.currentText() == originalLocation:
                self.removeHighlight(cboLocation)
            else:
                self.highlightWidget(cboLocation)

            cascadeMode = self.metaDataByRow[row].get("cascadeMode", "location_first")
            if cascadeMode == "location_first":
                self.setCboDate(row)

            self.setCboTime(row)

            self.setCboCommonName(row)
                        
            self.saveNewMetaData(row)

            self.fillingCombos = False


    def cboDateChanged(self, row):
        
        if self.fillingCombos is False:

            self.fillingCombos = True
            
            # get cboLocationChanged widget from the row that was clicked                
            container = self.gridPhotos.itemAtPosition(row, 1).widget()
            for w in container.children():
                if "cboDate" in w.objectName():
                    cboDate = w            
            
            originalDate = self.metaDataByRow[row]["date"]                
            
            if cboDate.currentText() == originalDate:
                self.removeHighlight(cboDate)
            else:
                self.highlightWidget(cboDate)

            cascadeMode = self.metaDataByRow[row].get("cascadeMode", "location_first")
            if cascadeMode == "date_first":
                self.setCboLocationByDate(row)

            self.setCboTime(row)

            self.setCboCommonName(row)
            
            self.saveNewMetaData(row)                         
            
            self.fillingCombos = False


    def cboTimeChanged(self, row):

        if self.fillingCombos is False:
            
            self.fillingCombos = True

            # get cboLocationChanged widget from the row that was clicked                
            container = self.gridPhotos.itemAtPosition(row, 1).widget()
            for w in container.children():
                if "cboTime" in w.objectName():
                    cboTime = w            
            
            originalTime = self.metaDataByRow[row]["time"]                
#             
            if cboTime.currentText() == originalTime:
                self.removeHighlight(cboTime)
            else:
                self.highlightWidget(cboTime) 
                                    
            self.setCboCommonName(row)
            
            self.saveNewMetaData(row)            
            
            self.fillingCombos = False


    def cboCommonNameChanged(self, row):

        if self.fillingCombos is False:
                    
            # get cboCommonName widget from the row that was clicked                
            container = self.gridPhotos.itemAtPosition(row, 1).widget()
            for w in container.children():
                if "cboCommonName" in w.objectName():
                    cboCommonName = w
            
            originalCommonName = self.metaDataByRow[row]["commonName"]
            
            if cboCommonName.currentText() == originalCommonName:
                self.removeHighlight(cboCommonName)
            else:
                self.highlightWidget(cboCommonName)
            
            self.saveNewMetaData(row)


    def cboRatingChanged(self, row):

        if self.fillingCombos is False:
                    
            # get cboCommonName widget from the row that was clicked                
            container = self.gridPhotos.itemAtPosition(row, 1).widget()
            for w in container.children():
                if "cboRating" in w.objectName():
                    cboRating = w
            
            originalRating = self.metaDataByRow[row]["rating"]
            
            if cboRating.currentText() == originalRating:
                self.removeHighlight(cboRating)
            else:
                self.highlightWidget(cboRating)
            
            self.saveNewMetaData(row)
                            

    def setCboDate(self, row):
        
        # get cboLocationChanged widget from the row that was clicked                
        container = self.gridPhotos.itemAtPosition(row, 1).widget()
        for w in container.children():
            if "cboLocation" in w.objectName():
                cboLocation = w
            if "cboDate" in w.objectName():
                cboDate = w
                                
        originalDate = self.metaDataByRow[row]["date"]
        
        currentlyDisplayedDate = cboDate.currentText()
                    
        # fill date combo box with all dates associated with selected location
        filterForThisPhoto = code_Filter.Filter()
        filterForThisPhoto.setLocationName(cboLocation.currentText())
        filterForThisPhoto.setLocationType("Location")
        dates = self.mdiParent.db.GetDates(filterForThisPhoto)
        cboDate.clear()
        cboDate.addItems(dates)
        
        # set date combo box to the photo's associated date
        index = cboDate.findText(currentlyDisplayedDate)
        if index >= 0:
            cboDate.setCurrentIndex(index)

        # if currentlyDisplayedDate didn't match, try the original
        else:
            index = cboDate.findText(originalDate)
            if index >= 0:
                cboDate.setCurrentIndex(index)

        if cboDate.currentText() == originalDate:
            self.removeHighlight(cboDate)
        else:
            self.highlightWidget(cboDate)


    def setCboLocationByDate(self, row):

        container = self.gridPhotos.itemAtPosition(row, 1).widget()
        for w in container.children():
            if "cboDate" in w.objectName():
                cboDate = w
            if "cboLocation" in w.objectName():
                cboLocation = w

        originalLocation = self.metaDataByRow[row]["location"]
        currentlyDisplayedLocation = cboLocation.currentText()

        # get locations visited on the selected date
        filterForThisPhoto = code_Filter.Filter()
        filterForThisPhoto.setStartDate(cboDate.currentText())
        filterForThisPhoto.setEndDate(cboDate.currentText())
        locations = self.mdiParent.db.GetLocations(filterForThisPhoto)
        cboLocation.clear()
        cboLocation.addItems(locations)

        # try to keep the currently displayed location if it's valid for the new date
        index = cboLocation.findText(currentlyDisplayedLocation)
        if index >= 0:
            cboLocation.setCurrentIndex(index)

        if cboLocation.currentText() == originalLocation:
            self.removeHighlight(cboLocation)
        else:
            self.highlightWidget(cboLocation)


    def setCboTime(self, row):
        
        # get cboLocationChanged widget from the row that was clicked                
        container = self.gridPhotos.itemAtPosition(row, 1).widget()
        for w in container.children():
            if "cboLocation" in w.objectName():
                cboLocation = w
            if "cboDate" in w.objectName():
                cboDate = w
            if "cboTime" in w.objectName():
                cboTime = w

        originalTime = self.metaDataByRow[row]["time"]
        
        currentlyDisplayedTime = cboTime.currentText()
                    
        # fill date combo box with all dates associated with selected location
        filterForThisPhoto = code_Filter.Filter()
        filterForThisPhoto.setLocationName(cboLocation.currentText())
        filterForThisPhoto.setLocationType("Location")
        filterForThisPhoto.setStartDate(cboDate.currentText())
        filterForThisPhoto.setEndDate(cboDate.currentText())
        times = self.mdiParent.db.GetStartTimes(filterForThisPhoto)
        cboTime.clear()
        cboTime.addItems(times)
        
        # set date  combo box to the photo's associated date
        index = cboTime.findText(currentlyDisplayedTime)
        if index >= 0:
            cboTime.setCurrentIndex(index)
             
        if cboTime.currentText() == originalTime:
            self.removeHighlight(cboTime)
        else:
            self.highlightWidget(cboTime)         


    def setCboCommonName(self, row):
        
        # get widgets from the row that was clicked                
        container = self.gridPhotos.itemAtPosition(row, 1).widget()
        for w in container.children():
            if "cboLocation" in w.objectName():
                cboLocation = w
            if "cboDate" in w.objectName():
                cboDate = w
            if "cboTime" in w.objectName():
                cboTime = w
            if "cboCommonName" in w.objectName():
                cboCommonName = w
    
        originalCommonName = self.metaDataByRow[row]["commonName"]                  
    
        currentlyDisplayedCommonName = cboCommonName.currentText() 
        
        # fill time combo box with all times associated with selected location and date
        filterForThisPhoto = code_Filter.Filter()
        filterForThisPhoto.setLocationName(cboLocation.currentText())
        filterForThisPhoto.setLocationType("Location")
        filterForThisPhoto.setStartDate(cboDate.currentText())
        filterForThisPhoto.setEndDate(cboDate.currentText())
        filterForThisPhoto.setTime(cboTime.currentText())
        commonNames = self.mdiParent.db.GetSpecies(filterForThisPhoto)
        cboCommonName.clear()
        cboCommonName.addItem("**None Selected**")
        cboCommonName.addItem("**Detach Photo**") 
        cboCommonName.addItems(commonNames)
        
        # try to set combo box to the currentlyDisplayedCommonName
        index = cboCommonName.findText(currentlyDisplayedCommonName)
        if index >= 0:
            cboCommonName.setCurrentIndex(index)

        # if currentlyDisplayedCommonName failed, try
        # looking for the oringalCommonName
        else:
            index = cboCommonName.findText(originalCommonName)
            if index >= 0:
                cboCommonName.setCurrentIndex(index)
                
        # if set to **None Selected**, try to set it to the original
        if cboCommonName.currentText() == "**None Selected**":
            index = cboCommonName.findText(originalCommonName)
            if index >= 0:
                cboCommonName.setCurrentIndex(index)
# 
        # set highlighting if commonName is different from the original
        if cboCommonName.currentText() == originalCommonName:
            self.removeHighlight(cboCommonName)
        else:
            self.highlightWidget(cboCommonName) 
                        
            
    def saveNewMetaData(self, row):
        
        # get metadata from widgets from row in question
        container = self.gridPhotos.itemAtPosition(row, 1).widget()
        for w in container.children():
            if "cboLocation" in w.objectName():
                self.metaDataByRow[row]["newLocation"] = w.currentText()
            if "cboDate" in w.objectName():
                self.metaDataByRow[row]["newDate"] = w.currentText()
            if "cboTime" in w.objectName():
                self.metaDataByRow[row]["newTime"] = w.currentText()
            if "cboCommonName" in w.objectName():
                self.metaDataByRow[row]["newCommonName"] = w.currentText()
            if "cboRating" in w.objectName():
                self.metaDataByRow[row]["newRating"] = str(w.currentIndex())      
                
           
    def btnResetClicked(self, row):
        
        self.fillingCombos = True
        
        # get widgets from the row that was clicked                
        container = self.gridPhotos.itemAtPosition(row, 1).widget()
        for w in container.children():
            if "cboLocation" in w.objectName():
                cboLocation = w
            if "cboDate" in w.objectName():
                cboDate = w
            if "cboTime" in w.objectName():
                cboTime = w
            if "cboCommonName" in w.objectName():
                cboCommonName = w
            if "cboRating" in w.objectName():
                cboRating = w
                
        originalLocation = self.metaDataByRow[row]["location"]
        originalDate = self.metaDataByRow[row]["date"]
        originalTime = self.metaDataByRow[row]["time"]
        originalCommonName = self.metaDataByRow[row]["commonName"] 
        originalRating = self.metaDataByRow[row]["rating"]                 

        # set the locations cbo box to original location
        index = cboLocation.findText(originalLocation)
        cboLocation.setCurrentIndex(index)        
            
        # fill date combo box with all dates associated with selected location
        filterForThisPhoto = code_Filter.Filter()
        filterForThisPhoto.setLocationName(cboLocation.currentText())
        filterForThisPhoto.setLocationType("Location")
        dates = self.mdiParent.db.GetDates(filterForThisPhoto)
        cboDate.clear()
        cboDate.addItems(dates)
        
        # set the date cbo box to original date
        index = cboDate.findText(originalDate)
        cboDate.setCurrentIndex(index)         

        # fill time combo box with all times associated with selected location and date
        filterForThisPhoto = code_Filter.Filter()
        filterForThisPhoto.setLocationName(cboLocation.currentText())
        filterForThisPhoto.setLocationType("Location")
        filterForThisPhoto.setStartDate(originalDate)
        filterForThisPhoto.setEndDate(originalDate)
        times = self.mdiParent.db.GetStartTimes(filterForThisPhoto)
        cboTime.clear()
        cboTime.addItems(times)
        
        # set the time cbo box to original time
        index = cboTime.findText(originalTime)
        cboTime.setCurrentIndex(index)  
        
        # fill commonName combo box with all names associated with selected location, date and time
        filterForThisPhoto = code_Filter.Filter()
        filterForThisPhoto.setLocationName(cboLocation.currentText())
        filterForThisPhoto.setLocationType("Location")
        filterForThisPhoto.setStartDate(originalDate)
        filterForThisPhoto.setEndDate(originalDate)
        filterForThisPhoto.setTime(originalTime)
        commonNames = self.mdiParent.db.GetSpecies(filterForThisPhoto)
        cboCommonName.clear()
        cboCommonName.addItem("**None Selected**")
        cboCommonName.addItem("**Detach Photo**")         
        cboCommonName.addItems(commonNames)
        
        # set the time cbo box to original time
        index = cboCommonName.findText(originalCommonName)
        cboCommonName.setCurrentIndex(index)  
        
        # set the rating cbo to the original rating
        index = int(originalRating)
        cboRating.setCurrentIndex(index)
                   
#         # turn off highlighting for all cbo boxes
        self.removeHighlight(cboLocation)
        self.removeHighlight(cboDate)
        self.removeHighlight(cboTime)
        self.removeHighlight(cboCommonName)
        self.removeHighlight(cboRating)
         
        self.fillingCombos = False


    def savePhotoSettings(self):
                
        # call database function to remove modified photos from db
        for r in range(self.gridPhotos.rowCount()):
            
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
                        
                if metaDataChanged is True:
                    # remove the photo from the database
                    self.mdiParent.db.removePhotoFromDatabase(
                        self.metaDataByRow[r]["location"],
                        self.metaDataByRow[r]["date"],
                        self.metaDataByRow[r]["time"],
                        self.metaDataByRow[r]["commonName"],
                        self.metaDataByRow[r]["photoFileName"])
                
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
                                                    
                    self.mdiParent.db.addPhotoToDatabase(filter, self.metaDataByRow[r]["photoData"])
                    
        
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
                                                                            
                    self.mdiParent.db.addPhotoToDatabase(filter, self.metaDataByRow[r]["photoData"])
                    

        if self.photosAlreadyInDb is False:
            
            # ensure that photo filter is visible, if we've added new photos.
            self.mdiParent.dckPhotoFilter.setVisible(True)

            # update the photo filter's cbo boxes                    
            self.mdiParent.fillPhotoComboBoxes()
        
        # set flag indicating that some photo data isn't yet saved to file
        self.mdiParent.db.photosNeedSaving = True
        
        self.mdiParent.db.refreshPhotoLists()
        
        self.mdiParent.fillPhotoComboBoxes()
    
        # close the window
        self.close()
        
        
    def closeWindow(self):
        
        self.close()
 
 
    def highlightWidget(self, w):
    
        red = str(code_Stylesheet.mdiAreaColor.red())
        blue = str(code_Stylesheet.mdiAreaColor.blue())
        green = str(code_Stylesheet.mdiAreaColor.green())
        w.setStyleSheet("QComboBox { background-color: rgb(" + red + "," + green + "," + blue + ")}")
         
    def removeHighlight(self, w):
        w.setStyleSheet("")

        
        
