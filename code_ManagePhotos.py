# import project files
import form_ManagePhotos
import code_Filter
import code_Stylesheet
import os

import piexif

# import basic Python libraries
from functools import partial

from collections import defaultdict

from PyQt5.QtGui import (
    QPixmap,
    QFont,
    QIcon,
    QImage,
    QTransform,
    QCursor   
    )
    
from PyQt5.QtCore import (
    pyqtSignal,
    QSize,
    Qt,
    QThread,
    )
    
from PyQt5.QtWidgets import (
    QMdiSubWindow,
    QPushButton, 
    QApplication,
    qApp,
    QWidget,
    QLabel
    )

from PyQt5.Qt import (
    QComboBox, 
    QVBoxLayout
    )
    

class threadGetPhotoData(QThread):

    sigProcessedPhoto = pyqtSignal([dict])
    sigThreadFinished = pyqtSignal()

    def __init__(self):
        
        QThread.__init__(self)
        
        self.parent = ""      
        self.fileNames = []
        self.threadNumber = 0
    
    def __del__(self):
        
        self.wait()
                      
                        
    def run(self):

        for p in self.fileNames:
            
            row = p[0]
            file = p[1]
            
            photoData = self.parent.mdiParent.db.getPhotoData(file)
            photoMatchData = self.parent.mdiParent.db.matchPhoto(file)
            pixMap = self.parent.GetPixmapForThumbnail(file)
            
            thisPhotoDataEntry = defaultdict()
            thisPhotoDataEntry["row"] = row
            thisPhotoDataEntry["photoData"] = photoData
            thisPhotoDataEntry["photoMatchData"] = photoMatchData
            thisPhotoDataEntry["pixMap"] = pixMap
            
            # now that we've created the pixmap etc., send it back to the main routine 
            # to insert into the form's grid
            self.sigProcessedPhoto.emit(thisPhotoDataEntry)
        
        #we're done, so wrap up and let the main thread know we're done
        if self.threadNumber == 1:
            self.parent.thread1Finished = True
        if self.threadNumber == 2:
            self.parent.thread2Finished = True
        if self.threadNumber == 3:
            self.parent.thread3Finished = True
        if self.threadNumber == 4:
            self.parent.thread4Finished = True
        
        # tell the main routine that our thread has processed all it's photos
        self.sigThreadFinished.emit()
        


class ManagePhotos(QMdiSubWindow, form_ManagePhotos.Ui_frmManagePhotos):
    
    # create "resized" as a signal that the window can emit
    # we respond to this signal with the form's resizeMe method below
    resized = pyqtSignal()
    
    
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
                
        # set up four threads to be used to get photo data from files        
        self.thread1 = threadGetPhotoData()
        self.thread2 = threadGetPhotoData()
        self.thread3 = threadGetPhotoData()
        self.thread4 = threadGetPhotoData()
        
        self.thread1Finished = False
        self.thread2Finished = False
        self.thread3Finished = False
        self.thread4Finished = False
         
        self.thread1.sigProcessedPhoto.connect(self.threadProcessedPhoto)
        self.thread2.sigProcessedPhoto.connect(self.threadProcessedPhoto)
        self.thread3.sigProcessedPhoto.connect(self.threadProcessedPhoto)
        self.thread4.sigProcessedPhoto.connect(self.threadProcessedPhoto)

        self.thread1.sigThreadFinished.connect(self.threadFinished)
        self.thread2.sigThreadFinished.connect(self.threadFinished)
        self.thread3.sigThreadFinished.connect(self.threadFinished)
        self.thread4.sigThreadFinished.connect(self.threadFinished)
        
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_camera.png"), QIcon.Normal, QIcon.Off)
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
        
        # divide files into four groups, one for each thread
        # we're using threads to divide up the work of creating pixmaps for each image
        
        if len(allowedPhotoFiles) > 3:
            
            filesPerThread = divmod(len(allowedPhotoFiles), 4)[0]
        
            thread1Files = allowedPhotoFiles[0 : filesPerThread]
            thread2Files = allowedPhotoFiles[filesPerThread : 2 * filesPerThread]
            thread3Files = allowedPhotoFiles[2 * filesPerThread : 3 * filesPerThread]
            thread4Files = allowedPhotoFiles[3 * filesPerThread :]        
            
        else:
            
            # fewer than four files were selected, so let's not use more than one thread
            thread1Files = allowedPhotoFiles
            thread2Files = []
            thread3Files = []
            thread4Files = []
            
        # provide threads with starting data and run the threads
        if len(thread1Files) > 0:
            self.thread1.parent = self
            self.thread1.threadNumber = 1
            self.thread1.fileNames = thread1Files
            self.thread1.start()
        else:
            self.thread1Finished = True

        if len(thread2Files) > 0:
            self.thread2.parent = self
            self.thread2.threadNumber = 2
            self.thread2.fileNames = thread2Files
            self.thread2.start()
        else:
            self.thread2Finished = True
        
        if len(thread3Files) > 0:        
            self.thread3.parent = self
            self.thread3.threadNumber = 3
            self.thread3.fileNames = thread3Files
            self.thread3.start()
        else:
            self.thread3Finished = True

        if len(thread4Files) > 0:         
            self.thread4.parent = self
            self.thread4.threadNumber = 4
            self.thread4.fileNames = thread4Files
            self.thread4.start()
        else:
            self.thread4Finished = True
                
    
    def threadProcessedPhoto(self, thisPhotoDataEntry):                                

        QApplication.processEvents()
        
        # call the routine to put the photo into the grid
            
        self.insertPhotoIntoTable(
            thisPhotoDataEntry["row"], 
            thisPhotoDataEntry["photoData"], 
            thisPhotoDataEntry["photoMatchData"], 
            thisPhotoDataEntry["pixMap"]
            )                         
   
   
    def threadFinished(self):

        QApplication.processEvents()
        
        # if all threads are finished, set the scroll bar to the top and show the correct cursor
        if self.thread1Finished == True:
            if self.thread2Finished == True:
                if self.thread3Finished == True:
                    if self.thread4Finished == True:
                        self.scrollArea.verticalScrollBar().setValue(0)
        
        QApplication.restoreOverrideCursor()   
        
        # reset flags for future use
        self.thread1Finished = False
        self.thread2Finished = False
        self.thread3Finished = False
        self.thread4Finished = False
              
                                
                                 
    def insertPhotoIntoTable(self, row, photoData, photoMatchData, pixMap):

        QApplication.processEvents()
                    
        self.fillingCombos = True
                                                                    
        photoLocation = photoMatchData["photoLocation"]
        photoDate = photoMatchData["photoDate"]
        photoTime = photoMatchData["photoTime"]
        photoCommonName = photoMatchData["photoCommonName"]
                            
        # p is a filename. Use it to add the image to the label as a pixmap
        buttonPhoto = QPushButton()
        buttonPhoto.setMinimumHeight(281)
        buttonPhoto.setMinimumWidth(500)
                
        buttonPhoto.setIcon(QIcon(pixMap))
        
        # size to 500x281
        buttonPhoto.setIconSize(QSize(500,281))    
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

        # fill location combo box with all locations in db
        locations = self.mdiParent.db.locationList
        cboLocation.addItems(locations)
        
        # set location combo box to the photo's location
        if photoLocation != "":
            index = cboLocation.findText(photoLocation)
            if index >= 0:
                cboLocation.setCurrentIndex(index)
            
                # fill date combo box with all dates associated with selected location
                filterForThisPhoto = code_Filter.Filter()
                filterForThisPhoto.setLocationName(photoLocation)
                filterForThisPhoto.setLocationType("Location")
                dates = self.mdiParent.db.GetDates(filterForThisPhoto)
                cboDate.addItems(dates)
                
                # set date  combo box to the photo's associated date
                index = cboDate.findText(photoDate)
                if index >= 0:
                    cboDate.setCurrentIndex(index)              
                    
                # fill time combo box with all times associated with selected location and date
                filterForThisPhoto.setStartDate(photoDate)
                filterForThisPhoto.setEndDate(photoDate)
                startTimes = self.mdiParent.db.GetStartTimes(filterForThisPhoto)
                cboTime.addItems(startTimes)
                
                # set time combo box to the photo's associated checklist time
                index = cboTime.findText(photoTime)
                if index >= 0:
                    cboTime.setCurrentIndex(index)                              
                                        
                # get common names from checklist associated with photo
                filterForThisPhoto.setTime(photoTime)
                commonNames = self.mdiParent.db.GetSpecies(filterForThisPhoto)
                
                cboCommonName.addItem("**Detach Photo**")
                cboCommonName.addItems(commonNames)  
                
                # set combo box to common name
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
        
        # add combo boxes to the layout in second column
        detailsLayout.addWidget(lblFileName)
        detailsLayout.addWidget(lblFileDate)
        detailsLayout.addWidget(lblFileTime)
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
        thisPhotoMetaData["photoFileName"] = photoData["fileName"]
        thisPhotoMetaData["location"] = photoLocation
        thisPhotoMetaData["date"] = photoDate
        thisPhotoMetaData["time"] = cboTime.currentText()
        thisPhotoMetaData["commonName"] = photoCommonName
        thisPhotoMetaData["photoData"] = photoData
        thisPhotoMetaData["rating"] = thisPhotoMetaData["photoData"]["rating"] 

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
                buttonPhoto.setMinimumHeight(281)
                buttonPhoto.setMinimumWidth(500)
                
                # get thumbnail from file to display
                pixMap = self.GetPixmapForThumbnail(p["fileName"])
                
                buttonPhoto.setIcon(QIcon(pixMap))
                
                # size to 500x281
                buttonPhoto.setIconSize(QSize(500,281))    
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
        icon.addPixmap(QPixmap(":/icon_camera.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon) 
        self.setWindowTitle("Manage Photos")
        
        self.fillingCombos = False
        
        QApplication.restoreOverrideCursor()         
                    
        # tell MainWindow that we succeeded filling the list
        return(True)


    def GetPixmapForThumbnail(self, photoFile):
                
        photoExif = piexif.load(photoFile)
        
        try:
            pmOrientation = int(photoExif["0th"][piexif.ImageIFD.Orientation] )
        except:
            pmOrientation = 1
            
        try:
            thumbimg = photoExif["thumbnail"]
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
            pm = pm.scaledToHeight(281)
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
#                         
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

        
        
