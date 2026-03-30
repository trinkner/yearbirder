#! /usr/bin/env python

# import the GUI forms that we create with Qt Creator
import code_DataBase
import code_BigReport
import code_Filter
import code_Find 
import code_Lists
import code_Web
import code_Families
import code_Compare
import code_LocationTotals
import code_DateTotals
import code_Graphs
import code_Photos
import code_ManagePhotos
import code_Preferences
import code_Stylesheet

import form_MDIMain

# import basic Python libraries
import sys
import os
import subprocess
import datetime

from math import (
    floor, 
    modf
    )

# import the Qt components we'll use
# do this so later we won't have to clutter our code with references to parent Qt classes 

from PySide6.QtGui import (
    QAction,
    QCursor,
    QFont,
    QFontMetrics,
    QIcon,
    QPixmap,
    QTextDocument,
    QColor
    )
    
from PySide6.QtCore import (
    Qt,
    QDate,
    QSize,
    QThread,
    Signal,
    QTimer,
    QEvent
    )
    
from PySide6.QtWidgets import (
    QApplication,
    QMdiArea,
    QMessageBox,
    QMainWindow,
    QFileDialog,
    QSlider,
    QLabel,
    QProxyStyle,
    QStyle,
    QStyleOptionToolButton
    )

from PySide6.QtPrintSupport import (
    QPrintDialog,
    QPrinter
    )

class _WhiteIconToolbarStyle(QProxyStyle):
    """Proxy style that draws white icons on toolbar buttons, leaving menu icons unchanged."""
    def __init__(self, white_icon_map):
        super().__init__()
        self._map = white_icon_map  # {QAction: QIcon}

    def drawControl(self, element, option, painter, widget=None):
        if (element == QStyle.ControlElement.CE_ToolButtonLabel
                and isinstance(option, QStyleOptionToolButton)
                and widget is not None
                and hasattr(widget, 'defaultAction')):
            action = widget.defaultAction()
            if action in self._map:
                opt = QStyleOptionToolButton(option)
                opt.icon = self._map[action]
                super().drawControl(element, opt, painter, widget)
                return
        super().drawControl(element, option, painter, widget)


class MainWindow(QMainWindow, form_MDIMain.Ui_MainWindow):

    # initialize main database that will be used throughout program
    db = code_DataBase.DataBase()
    fontSize = 11
    scaleFactor = 1
    rowHeight = 16  # default; recomputed in ScaleDisplay() and __init__
    versionNumber = "1.2"
    versionDate = "March 30, 2026"

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setCentralWidget(self.mdiArea)
        self.actionAboutYearbird.setText("About Yearbird")

        # The form sets scrPhotoFilter with AlignTop + stretch=0, which prevents it
        # from expanding to fill the dock and causes a spurious scroll bar.
        self.verticalLayout_4.setAlignment(self.scrPhotoFilter, Qt.Alignment())
        self.verticalLayout_4.setStretchFactor(self.scrPhotoFilter, 1)
        # Pin the photo filter content to the top (mirrors how frmFilter is AlignTop
        # in the standard filter), so items aren't stretched to fill the scroll area.
        self.verticalLayout_5.setAlignment(self.frmPhotoFilter, Qt.AlignTop)

        # Black icons for drop-down menus (loaded from Qt resource system)
        _menuIcons = {
            self.actionOpen:           ":/icon_open.png",
            self.actionPrint:          ":/icon_print.png",
            self.actionCreatePDF:      ":/icon_pdf.png",
            self.actionSpecies:        ":/icon_bird.png",
            self.actionLocations:      ":/icon_location.png",
            self.actionChecklists:     ":/icon_checklists.png",
            self.actionMap:            ":/icon_map.png",
            self.actionFamilies:       ":/icon_families.png",
            self.actionDateTotals:     ":/icon_datetotals.png",
            self.actionLocationTotals: ":/icon_locationtotals.png",
            self.actionCompareLists:   ":/icon_compare.png",
            self.actionBigReport:      ":/icon_tripreport.png",
            self.actionPhotos:         ":/icon_camera.png",
            self.actionFind:           ":/icon_find.png",
            self.actionClearAllFilters:":/icon_filter.png",
        }
        for action, path in _menuIcons.items():
            action.setIcon(QIcon(QPixmap(path)))
        # White icons for toolbar buttons via proxy style (menus keep the black icons above)
        _whiteIconMap = {
            self.actionOpen:           QIcon(QPixmap(":/icon_open_white.png")),
            self.actionPrint:          QIcon(QPixmap(":/icon_print_white.png")),
            self.actionCreatePDF:      QIcon(QPixmap(":/icon_pdf_white.png")),
            self.actionSpecies:        QIcon(QPixmap(":/icon_bird_white.png")),
            self.actionLocations:      QIcon(QPixmap(":/icon_location_white.png")),
            self.actionChecklists:     QIcon(QPixmap(":/icon_checklists_white.png")),
            self.actionMap:            QIcon(QPixmap(":/icon_map_white.png")),
            self.actionFamilies:       QIcon(QPixmap(":/icon_families_white.png")),
            self.actionDateTotals:     QIcon(QPixmap(":/icon_datetotals_white.png")),
            self.actionLocationTotals: QIcon(QPixmap(":/icon_locationtotals_white.png")),
            self.actionCompareLists:   QIcon(QPixmap(":/icon_compare_white.png")),
            self.actionBigReport:      QIcon(QPixmap(":/icon_tripreport_white.png")),
            self.actionPhotos:         QIcon(QPixmap(":/icon_camera_white.png")),
            self.actionFind:           QIcon(QPixmap(":/icon_find_white.png")),
            self.actionClearAllFilters:QIcon(QPixmap(":/icon_filter_white.png")),
        }
        self._toolbarStyle = _WhiteIconToolbarStyle(_whiteIconMap)
        self.toolBar.setStyle(self._toolbarStyle)

        # Remove all separators from the toolbar for uniform spacing
        for action in self.toolBar.actions():
            if action.isSeparator():
                self.toolBar.removeAction(action)

        # Reduce toolbar icon size by 10%
        _sz = self.toolBar.iconSize()
        self.toolBar.setIconSize(QSize(int(_sz.width() * 0.9), int(_sz.height() * 0.9)))

        # Equalise toolbar button widths to the widest label
        fm = self.toolBar.fontMetrics()
        toolbarIconSize = self.toolBar.iconSize()
        maxWidth = max(
            (max(toolbarIconSize.width(), fm.boundingRect(action.text()).width())
             for action in self.toolBar.actions()
             if not action.isSeparator()),
            default=24
        )
        buttonWidth = maxWidth + 24  # padding on each side
        for action in self.toolBar.actions():
            btn = self.toolBar.widgetForAction(action)
            if btn is not None:
                btn.setFixedWidth(buttonWidth)
        
        self.actionOpen.triggered.connect(self.openDataFileClicked)
        self.actionClose.triggered.connect(self.closeDataFile)

        self.actionAboutYearbird.triggered.connect(self.CreateAboutYearbird)
        self.actionUserGuide.triggered.connect(self.CreateUserGuide)

        # macOS intercepts any QAction named "About …" and moves it to the Application
        # menu, so actionAboutYearbird never stays in the User Guide dropdown.
        # Create a separate action with NoRole so macOS leaves it in place.
        _aboutAction = QAction("About Yearbird", self)
        _aboutAction.setMenuRole(QAction.MenuRole.NoRole)
        _aboutAction.triggered.connect(self.CreateAboutYearbird)
        self.menuHelp.addSeparator()
        self.menuHelp.addAction(_aboutAction)        
        self.actionPreferences.triggered.connect(self.createPreferences)
        self.actionExit.triggered.connect(self.ExitApp)
        
        self.actionShowStandardFilter.triggered.connect(self.showStandardFilter)
        self.actionHideStandardFilter.triggered.connect(self.hideStandardFilter)
        self.actionShowPhotoFilter.triggered.connect(self.showPhotoFilter)
        self.actionHidePhotoFilter.triggered.connect(self.hidePhotoFilter)

        self.actionClearAllFilters.triggered.connect(self.clearAllFilters)
        self.actionClearStandardFilter.triggered.connect(self.clearStandardFilter)
        self.actionClearPhotoFilter.triggered.connect(self.clearPhotoFilter)
        
        self.actionDateTotals.triggered.connect(self.CreateDateTotals)
        self.actionLocationTotals.triggered.connect(self.CreateLocationTotals)
        self.actionCompareLists.triggered.connect(self.CreateCompareLists)
        self.actionTileWindows.triggered.connect(self.TileWindows)
        self.actionCascade.triggered.connect(self.CascadeWindows)
        self.actionCloseAllWindows.triggered.connect(self.CloseAllWindows)
        self.actionSpecies.triggered.connect(self.CreateSpeciesList)
        self.actionChecklists.triggered.connect(self.CreateChecklistsList)
        self.actionLocations.triggered.connect(self.CreateLocationsList)
        self.actionPrint.triggered.connect(self.printMe)
        self.actionCreatePDF.triggered.connect(self.CreatePDF)
        self.actionFamilies.triggered.connect(self.CreateIndivPieChart)
        self.actionPhotos.triggered.connect(self.createPhotosReport)
        self.actionBigReport.triggered.connect(self.CreateBigReport)
        self.actionBarGraph.triggered.connect(self.CreateBarGraph)
        self.actionTotalChecklists.triggered.connect(self.CreateTotalChecklistsGraph)
        self.actionTotalLocations.triggered.connect(self.CreateTotalLocationsGraph)
        self.actionCumulativeCurve.triggered.connect(self.CreateCumulativeCurve)
        self.actionCumulativeLocations.triggered.connect(self.CreateCumulativeLocationsCurve)
        self.actionCumulativeFamilies.triggered.connect(self.CreateCumulativeFamiliesCurve)
        self.actionHeatmap.triggered.connect(self.CreateHeatmap)
        self.actionAccumulation.triggered.connect(self.CreateAccumulationChart)
        self.actionTopLocations.triggered.connect(self.CreateTopLocations)
        self.actionScatter.triggered.connect(self.CreateScatterChart)
        self.actionPhenology.triggered.connect(self.CreatePhenologyChart)
        self.actionFOY.triggered.connect(self.CreateFOYChart)
        self.actionLOY.triggered.connect(self.CreateLOYChart)
        self.actionFamilyPie.triggered.connect(self.CreateFamilyPieChart)
        self.actionIndivPie.triggered.connect(self.CreateIndivPieChart)
        self.actionMap.triggered.connect(self.CreateMap)
        self.actionFind.triggered.connect(self.CreateFind)

        self.actionOpenPhotoSettings.triggered.connect(self.openPhotoSettings)
        self.actionClosePhotoSettings.triggered.connect(self.closePhotoSettings)
        self.actionSavePhotoSettings.triggered.connect(self.savePhotoSettings)
        self.actionAddPhotos.triggered.connect(self.addPhotos)
        self.actionEditPhotosByFilter.triggered.connect(self.createEditPhotosByFilter)
        self.actionUpdateEXIFDataForAllPhotos.triggered.connect(self.updateEXIFDataForAllPhotos)
        
        self.actionUS_States.triggered.connect(self.createChoroplethUSStates)
        self.actionUS_Counties.triggered.connect(self.createChoroplethUSCounties)
        self.actionCanada_Provinces.triggered.connect(self.createChoroplethCanadaProvinces)
        self.actionIndia_States.triggered.connect(self.createChoroplethIndiaStates)
        self.actionGB_Counties.triggered.connect(self.createChoroplethGBCounties)
        self.actionWorld_Countries.triggered.connect(self.createChoroplethWorldCountries)
        self.actionUS_States_Checklists.triggered.connect(self.createChoroplethUSStatesChecklists)
        self.actionUS_Counties_Checklists.triggered.connect(self.createChoroplethUSCountiesChecklists)
        self.actionCanada_Provinces_Checklists.triggered.connect(self.createChoroplethCanadaProvincesChecklists)
        self.actionIndia_States_Checklists.triggered.connect(self.createChoroplethIndiaStatesChecklists)
        self.actionGB_Counties_Checklists.triggered.connect(self.createChoroplethGBCountiesChecklists)
        self.actionWorld_Countries_Checklists.triggered.connect(self.createChoroplethWorldCountriesChecklists)
        self.actionGeolocatedPhotos.triggered.connect(self.createGeolocatedPhotosMap)
        self.actionGeolocatedPhotos.setEnabled(False)
        self.actionLifeListMap.triggered.connect(self.createLifeListMap)
        self.actionEffortMap.triggered.connect(self.createEffortMap)
        self.actionEffortMapByChecklists.triggered.connect(self.createEffortMapByChecklists)
        self.actionSpeciesTotalMap.triggered.connect(self.createSpeciesTotalMap)
        self.actionIndividualsTotalMap.triggered.connect(self.createIndividualsTotalMap)
        
        self.cboStartSeasonalRangeMonth.addItems(["Jan",  "Feb",  "Mar",  "Apr",  "May", "Jun",  "Jul",  "Aug",  "Sep",  "Oct",  "Nov",  "Dec"])
        self.cboEndSeasonalRangeMonth.addItems(["Jan",  "Feb",  "Mar",  "Apr",  "May", "Jun",  "Jul",  "Aug",  "Sep",  "Oct",  "Nov",  "Dec"])
        for d in range(1,  32):
            self.cboStartSeasonalRangeDate.addItem(str(d))
            self.cboEndSeasonalRangeDate.addItem(str(d))
        self.cboDateOptions.addItems(["No Date Filter",  "Use Calendars Below",  "This Year",  "This Month",  "Today",  "Yesterday", "Last Weekend"])            
        self.cboSeasonalRangeOptions.addItems([
            "No Seasonal Range",  
            "Use Range Below",  
            "Spring",  
            "Summer",  
            "Fall",  
            "Winter",  
            "This Month", 
            "Year to Date", 
            "Remainder of Year",
            "January",  
            "February",  
            "March",  
            "April",  
            "May", 
            "June",  
            "July",  
            "August",  
            "September",  
            "October",  
            "November",
            "December"
            ])                    
        self.cboRegions.currentIndexChanged.connect(self.ComboRegionsChanged)
        self.cboCountries.currentIndexChanged.connect(self.ComboCountriesChanged)
        self.cboStates.currentIndexChanged.connect(self.ComboStatesChanged)
        self.cboCounties.currentIndexChanged.connect(self.ComboCountiesChanged)
        self.cboLocations.currentIndexChanged.connect(self.ComboLocationsChanged)
        self.cboOrders.currentIndexChanged.connect(self.ComboOrdersChanged)
        self.cboFamilies.currentIndexChanged.connect(self.ComboFamiliesChanged)
        self.cboSpecies.currentIndexChanged.connect(self.ComboSpeciesChanged)
        self.txtCommonNameSearch.textChanged.connect(self.textCommonNameSearchChanged)
        self.cboDateOptions.currentIndexChanged.connect(self.ComboDateOptionsChanged)
        self.cboSeasonalRangeOptions.currentIndexChanged.connect(self.ComboSeasonalRangeOptionsChanged)
        self.calStartDate.dateChanged.connect(self.CalendarClicked)
        self.calEndDate.dateChanged.connect(self.CalendarClicked)
        self.cboStartSeasonalRangeMonth.currentIndexChanged.connect(self.SeasonalRangeClicked)
        self.cboStartSeasonalRangeDate.currentIndexChanged.connect(self.SeasonalRangeClicked)
        self.cboEndSeasonalRangeMonth.currentIndexChanged.connect(self.SeasonalRangeClicked)
        self.cboEndSeasonalRangeDate.currentIndexChanged.connect(self.SeasonalRangeClicked)
        self.fillingLocationComboBoxesFlag = False  
        self.calStartDate.setDate(datetime.datetime.now())
        self.calEndDate.setDate(datetime.datetime.now())

        self.cboStartRatingRange.addItems(["**All**", "0", "1", "2", "3", "4", "5"])
        self.cboEndRatingRange.addItems(["**All**", "0", "1", "2", "3", "4", "5"])                    
        self.cboStartRatingRange.currentIndexChanged.connect(self.ComboStartRatingRangeChanged)
        self.cboEndRatingRange.currentIndexChanged.connect(self.ComboEndRatingRangeChanged)
        self.cboSpeciesHasPhoto.addItems(["**All**", "Photographed", "Not photographed"])                    
        self.cboSpeciesHasPhoto.currentIndexChanged.connect(self.ComboSpeciesHasPhotosChanged)
        self.cboCamera.currentIndexChanged.connect(self.ComboCameraChanged)        
        self.cboLens.currentIndexChanged.connect(self.ComboLensChanged)
        self.cboStartShutterSpeedRange.currentIndexChanged.connect(self.ComboStartShutterSpeedChanged)
        self.cboEndShutterSpeedRange.currentIndexChanged.connect(self.ComboEndShutterSpeedChanged)
        self.cboStartApertureRange.currentIndexChanged.connect(self.ComboStartApertureChanged)
        self.cboEndApertureRange.currentIndexChanged.connect(self.ComboEndApertureChanged)
        self.cboStartFocalLengthRange.currentIndexChanged.connect(self.ComboStartFocalLengthChanged)
        self.cboEndFocalLengthRange.currentIndexChanged.connect(self.ComboEndFocalLengthChanged)
        self.cboStartIsoRange.currentIndexChanged.connect(self.ComboStartIsoChanged)
        self.cboEndIsoRange.currentIndexChanged.connect(self.ComboEndIsoChanged)
        
        self.lblSlider = QLabel(self.statusBar)
        self.lblSlider.setText("Display Size")
        self.lblSlider.setVisible(False)
        self.sldFontSize = QSlider(self.statusBar)
        self.sldFontSize.setSingleStep(10)
        self.sldFontSize.setProperty("value", 50)
        self.sldFontSize.setOrientation(Qt.Horizontal)
        self.sldFontSize.setObjectName("sldFontSize")
        self.sldFontSize.valueChanged.connect(self.ScaleDisplay)
        self.sldFontSize.setVisible(False)
        self.lblStatusBarMessage = QLabel(self.statusBar)
        self.lblStatusBarMessage.setText("")
        self.lblStatusBarMessage.setVisible(False)
        # self.statusBar.addWidget(self.lblSlider)
        # self.statusBar.addWidget(self.sldFontSize)
        self.statusBar.addWidget(self.lblStatusBarMessage, 1)
        
        self.dckPhotoFilter.setMinimumWidth(235)
        self.dckFilter.setMinimumWidth(215)
        
        self.setWindowTitle("Yearbird v. " + self.versionNumber)

        self.HideMainWindowOptions()
        
        self.setStyleSheet(code_Stylesheet.stylesheetBase)
        self.mdiArea.setBackground(code_Stylesheet.mdiAreaColor)

        self.showMaximized()
        self.ScaleDisplay()
        
        self.processPreferences()

        self.subWindowFocusOrder = []
        self._windowBeingClosed = None
        self.mdiArea.subWindowActivated.connect(self.onSubWindowActivated)

        QApplication.processEvents()


    def closeEvent(self, event):

        reply = self.checkIfPhotoDataNeedSaving()

        if reply is True:
            event.accept()


    def eventFilter(self, obj, event):
        # Detect when a tracked subwindow is about to close so we can
        # restore focus to the correct window afterward.
        if event.type() == QEvent.Close and obj in self.subWindowFocusOrder:
            self._windowBeingClosed = obj
            QTimer.singleShot(0, self.restorePreviousFocus)
        return False


    def onSubWindowActivated(self, window):
        if window is None:
            return
        # Install our event filter the first time each subwindow is activated.
        if not getattr(window, '_focusFilterInstalled', False):
            window.installEventFilter(self)
            window._focusFilterInstalled = True
        # Ignore Qt's automatic re-activation that fires while a close is in progress.
        if self._windowBeingClosed is not None:
            return
        if window in self.subWindowFocusOrder:
            self.subWindowFocusOrder.remove(window)
        self.subWindowFocusOrder.append(window)


    def restorePreviousFocus(self):
        openWindows = set(self.mdiArea.subWindowList())
        self.subWindowFocusOrder = [w for w in self.subWindowFocusOrder
                                    if w in openWindows]
        self._windowBeingClosed = None
        if self.subWindowFocusOrder:
            self.mdiArea.setActiveSubWindow(self.subWindowFocusOrder[-1])


    def processPreferences(self):
        
        # Read preferences directly on the main thread 
        self.db.readPreferences()

        # If a startup folder is defined and valid, open it
        if self.db.startupFolder and os.path.isdir(self.db.startupFolder):
            self.OpenDataFile(self.db.startupFolder)             

            # If a photo data file is defined and valid, load it
            if self.db.photoDataFile and os.path.isfile(self.db.photoDataFile):
                self.db.readPhotoDataFromFile(self.db.photoDataFile)

        # Now that preferences are processed, continue with UI updates
        self.finishedProcessingPreferences()
        

    def finishedProcessingPreferences(self):
        
        if self.db.eBirdFileOpenFlag == True:
            self.fillingLocationComboBoxesFlag = True
            self.FillMainComboBoxes()
            self.fillingLocationComboBoxesFlag = False
            self.showStandardFilter()
            self.CreateSpeciesList()
            
            #show photo filter if an ebird file has been read and a photo file has been opened
            if self.db.photoDataFileOpenFlag == True:
                self.fillPhotoComboBoxes()
                self.showPhotoFilter()
                self.actionGeolocatedPhotos.setEnabled(True)
            
            self.showFileDataMessage()
            
            
          
    def ScaleDisplay(self):
        
        
        self.scaleFactor = self.sldFontSize.value()/50
        if self.scaleFactor > 1:
            self.scaleFactor = 1 + modf(self.scaleFactor)[0] * 3
        if self.scaleFactor < 1:
            self.scaleFactor = (1 + self.scaleFactor) / 2
        self.fontSize = floor(11 * self.scaleFactor)
        MainWindow.fontSize = self.fontSize
        MainWindow.scaleFactor = self.scaleFactor
        MainWindow.rowHeight = int(QFontMetrics(QFont("Helvetica", MainWindow.fontSize)).boundingRect("2222-22-22").height() * 1.1)
        
        self.menuBar.setFont(QFont("Helvetica", self.fontSize))     
                        
        for a in self.toolBar.actions():
            a.setFont(QFont("Helvetica", self.fontSize))                    
                
        # scale the standard and photo filter docks
                
        filterFrameChildren = (
            self.frmFilter.children() +
            self.frmPhotoFilter.children() +           
            self.frmStartSeasonalRange.children() +
            self.frmEndSeasonalRange.children()+
            self.frmShutterSpeedRange.children() + 
            self.frmApertureRange.children() + 
            self.frmIsoRange.children() +
            self.frmFocalLengthRange.children() +
            self.frmRatingRange.children()
            )
                
        for w in filterFrameChildren:
                         
            if w.objectName()[0:3] == "cbo":
                w.setFont(QFont("Helvetica", self.fontSize))
                metrics = w.fontMetrics()
                cboText = w.currentText()
                if cboText == "":
                    cboText = "Dummy Text"
                itemTextWidth = metrics.boundingRect(cboText).width()
                itemTextHeight = metrics.height()  # full line height; independent of current text content
                w.setMinimumWidth(floor(1.1 * itemTextWidth))
                w.setMinimumHeight(floor(2 * itemTextHeight))
                w.setMaximumHeight(floor(2 * itemTextHeight))
                w.resize(int(2 * itemTextHeight), int(2 * itemTextWidth))
       
            if w.objectName()[0:3] == "lbl":
                w.setFont(QFont("Helvetica", self.fontSize))    
                metrics = w.fontMetrics()
                labelText = w.text()
                itemTextWidth = metrics.boundingRect(labelText).width()
                itemTextHeight = metrics.boundingRect(labelText).height()
                w.setMinimumWidth(floor(itemTextWidth))
                w.setMinimumHeight(floor(itemTextHeight))
                w.setMaximumHeight(floor(itemTextHeight))
                w.resize(itemTextHeight, itemTextWidth)  
                w.setStyleSheet("QLabel { font: bold }");
                                      
            if w.objectName()[0:3] == "cal":              
                w.setFont(QFont("Helvetica", self.fontSize))    
                metrics = w.fontMetrics()
                startDate = (
                            str(self.calStartDate.date().year()) 
                            + "-" 
                            + str(self.calStartDate.date().month()) 
                            + "-" 
                            + str(self.calStartDate.date().day()))
                itemTextWidth = metrics.boundingRect(startDate).width()
                itemTextHeight = metrics.boundingRect(startDate).height()
                w.setMinimumWidth(floor(2 * itemTextWidth))
                w.setMinimumHeight(floor(2 * itemTextHeight))
                w.setMaximumHeight(floor(2 * itemTextHeight))
                w.resize(int(2 * itemTextHeight), int(2 * itemTextWidth))

        for w in (
            self.frmStartSeasonalRange,
            self.frmEndSeasonalRange,
            self.frmRatingRange,
            self.frmShutterSpeedRange,
            self.frmApertureRange,
            self.frmIsoRange,
            self.frmFocalLengthRange,
            ):
            w.setMinimumWidth(floor(2 * itemTextWidth))
            w.setMinimumHeight(floor(2 * itemTextHeight))
            w.setMaximumHeight(floor(2 * itemTextHeight))
            w.resize(int(2 * itemTextHeight), int(2 * itemTextWidth))
            w.adjustSize()

            
        self.scrPhotoFilter.setMinimumHeight(0)
        self.scrPhotoFilter.setMinimumWidth(int(2.5 * itemTextWidth))
        self.scrFilter.setMinimumWidth(int(2.5 * itemTextWidth))
            
        # scale open children windows
        for w in self.mdiArea.subWindowList():        
            w.scaleMe()
            

    def showFileDataMessage(self):
        
        countSightings = len(self.db.sightingList)
        
        countSpecies = 0
        for s in self.db.allSpeciesList:
            if " x " not in s:
                countSpecies += 1
        
        # create blank filter to get all sightings with photos
        filter = code_Filter.Filter()
        
        photoSightings = self.db.GetSightingsWithPhotos(filter)
        
        countPhotos = 0
        
        for ps in photoSightings:
            countPhotos = countPhotos + len(ps["photos"])
        
        countPhotoSightings = len(self.db.GetSightingsWithPhotos(filter))
    
        msgText = "Yearbird loaded " + format(countSightings, ',') + " sightings, including " + format(countSpecies, ",") + " species.\n\n"
        msgText = msgText + "Yearbird attached " + format(countPhotos, ",") + " photos to " + format(countPhotoSightings, ",") + " sightings."
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(msgText)
        msg.setWindowTitle("eBird Data File")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()        
        

    def clearAllFilters(self):
        self.clearStandardFilter()
        self.clearPhotoFilter()
    
    
    def clearStandardFilter(self):
        self.cboRegions.setCurrentIndex(0)
        self.cboCountries.setCurrentIndex(0)
        self.cboStates.setCurrentIndex(0)
        self.cboCounties.setCurrentIndex(0)
        self.cboLocations.setCurrentIndex(0)
        self.cboOrders.setCurrentIndex(0)
        self.cboFamilies.setCurrentIndex(0)
        self.cboSpecies.setCurrentIndex(0)
        self.calStartDate.setDate(datetime.datetime.now())
        self.calEndDate.setDate(datetime.datetime.now())
        self.cboDateOptions.setCurrentIndex(0)
        self.cboSeasonalRangeOptions.setCurrentIndex(0)
        self.txtCommonNameSearch.setText("")


    def clearPhotoFilter(self):
        self.cboStartRatingRange.setCurrentIndex(0)
        self.cboEndRatingRange.setCurrentIndex(0)
        self.cboSpeciesHasPhoto.setCurrentIndex(0)
        self.cboCamera.setCurrentIndex(0)
        self.cboLens.setCurrentIndex(0)
        self.cboStartShutterSpeedRange.setCurrentIndex(0)
        self.cboEndShutterSpeedRange.setCurrentIndex(0)
        self.cboStartApertureRange.setCurrentIndex(0)
        self.cboEndApertureRange.setCurrentIndex(0)
        self.cboStartFocalLengthRange.setCurrentIndex(0)
        self.cboEndFocalLengthRange.setCurrentIndex(0)
        self.cboStartIsoRange.setCurrentIndex(0)
        self.cboEndIsoRange.setCurrentIndex(0)


    def openPhotoSettings(self, photoDataFile = ""):
                    
        # open data file
        fname = QFileDialog.getOpenFileName(self,"Select Yearbird Photo Data File", "","Yearbird Photo Data File (*.csv)")
        
        # check if user pressed cancel or if we have a file name to open
        if fname[0] == "":
            return
    
        photoDataFile = fname[0]
                            
        self.db.readPhotoDataFromFile(photoDataFile)

        self.fillPhotoComboBoxes()

        self.showPhotoFilter()

        self.actionGeolocatedPhotos.setEnabled(True)


    def closePhotoSettings(self):

        self.clearPhotoFilter()
        self.hidePhotoFilter()
        self.db.ClearPhotoSettings()
        self.actionGeolocatedPhotos.setEnabled(False)
        
        
    def addPhotos(self):
        # Abort if no data file is open
        if not MainWindow.db.eBirdFileOpenFlag:
            self.CreateMessageNoFile()
            return

        photo_paths, _ = QFileDialog.getOpenFileNames(self, 'Select photo files', "", "Jpeg Images (*.jpg *.jpeg)")

        if not photo_paths:
            return

        filter_obj = code_Filter.Filter()
        photos_already_in_db = set(self.db.GetPhotos(filter_obj))  # Use set for fast lookup

        unmatched_photos = [p for p in photo_paths if p not in photos_already_in_db]
        count_photos_not_processed = len(photo_paths) - len(unmatched_photos)

        if count_photos_not_processed > 0:
            QMessageBox.information(
                self,
                "Photos",
                f"{count_photos_not_processed} files were already attached to sightings and are not displayed here.\n\n"
                "To edit their attachments, use Manage Photos By Filter.",
                QMessageBox.StandardButton.Ok
            )

        if unmatched_photos:
            sub = code_ManagePhotos.ManagePhotos()
            sub.mdiParent = self

            sub.scaleMe()
            sub.resizeMe()

            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()

            QApplication.processEvents()
            QTimer.singleShot(20, lambda: sub.FillPhotosByFiles(unmatched_photos))
        else:
            QMessageBox.information(
                self,
                "Photos",
                "No new photo files were found.",
                QMessageBox.StandardButton.Ok
            )
           
    
    def savePhotoSettings(self):
        
        photoFileInUse = self.db.photoDataFile
        
        # open save dialog box to get name of photo settings file
        fname = QFileDialog.getSaveFileName(self, "Save Photo Settings File", photoFileInUse, "Yearbird Photo Settings File (*.csv)")
        
        # check if user pressed cancel or if we have a file name for saving
        if fname[0] == "":
            return
        
        # call database function to write entire db's photo settings to CSV vile
        self.db.writePhotoDataToFile(fname[0])   
        
        self.db.photosNeedSaving = False     


    def fillPhotoComboBoxes(self):
        
        for w in (
            self.cboCamera, 
            self.cboLens,
            self.cboStartShutterSpeedRange,
            self.cboEndShutterSpeedRange,
            self.cboStartApertureRange,
            self.cboEndApertureRange,
            self.cboStartIsoRange,
            self.cboEndIsoRange,
            self.cboStartFocalLengthRange,
            self.cboEndFocalLengthRange
            ):
            w.clear()
            
            if w == self.cboCamera:
                w.addItem("**All Cameras**")
                w.addItems(self.db.cameraList)

            if w == self.cboLens:
                w.addItem("**All Lenses**")
                w.addItems(self.db.lensList)

            if w == self.cboStartShutterSpeedRange:
                w.addItem("**All**")
                w.addItems(self.db.shutterSpeedList)

            if w == self.cboEndShutterSpeedRange:
                w.addItem("**All**")
                w.addItems(self.db.shutterSpeedList)
                
            if w == self.cboStartApertureRange:
                w.addItem("**All**")
                w.addItems(self.db.apertureList)

            if w == self.cboEndApertureRange:
                w.addItem("**All**")
                w.addItems(self.db.apertureList)

            if w == self.cboStartIsoRange:
                w.addItem("**All**")
                w.addItems(self.db.isoList)

            if w == self.cboEndIsoRange:
                w.addItem("**All**")
                w.addItems(self.db.isoList)

            if w == self.cboStartFocalLengthRange:
                w.addItem("**All**")
                w.addItems(self.db.focalLengthList)

            if w == self.cboEndFocalLengthRange:
                w.addItem("**All**")
                w.addItems(self.db.focalLengthList)
                
            w.setCurrentIndex(0)
        
        self.cboStartRatingRange.setCurrentIndex(0)
        self.cboEndRatingRange.setCurrentIndex(0)

        # Adding items via addItem() triggers Qt layout updates that can override
        # the size constraints set by ScaleDisplay().  Re-apply them now so these
        # comboboxes stay the same height as the rest of the filter.
        cboHeight = floor(2 * QFontMetrics(QFont("Helvetica", self.fontSize)).height())

        for w in (
            self.cboCamera,
            self.cboLens,
            self.cboStartShutterSpeedRange,
            self.cboEndShutterSpeedRange,
            self.cboStartApertureRange,
            self.cboEndApertureRange,
            self.cboStartIsoRange,
            self.cboEndIsoRange,
            self.cboStartFocalLengthRange,
            self.cboEndFocalLengthRange,
            ):
            w.setMinimumHeight(cboHeight)
            w.setMaximumHeight(cboHeight)

        for w in (
            self.frmShutterSpeedRange,
            self.frmApertureRange,
            self.frmIsoRange,
            self.frmFocalLengthRange,
            ):
            w.setMinimumHeight(cboHeight)
            w.setMaximumHeight(cboHeight)


    def removeUnfoundPhotos(self):
        
        countRemovedPhotos = self.db.removeUnfoundPhotos()
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("Yearbird removed " + str(countRemovedPhotos) + " references to unfound photos from its database.\n\nRemember to save your photo settings to a file.\n\n(No files were deleted from your computer.)")
        msg.setWindowTitle("Removed Photo References")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()        
        

    def createPreferences(self):
        

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        sub = code_Preferences.Preferences()

        # save the MDI window as the parent for future use in the child        
        sub.mdiParent = self 
        
        sub.fillPreferences()       
        
        # add and position the child to our MDI area
        self.mdiArea.addSubWindow(sub)
        self.PositionChildWindow(sub,  self)
        sub.show()
            
        QApplication.restoreOverrideCursor()         


    def createPhotosReport(self):
        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        filter = self.GetFilter()
        # create new Location Totals child window        
        sub = code_Photos.Photos()

        # save the MDI window as the parent for future use in the child        
        sub.mdiParent = self        
        
        # add and position the child to our MDI area
        self.mdiArea.addSubWindow(sub)
        self.PositionChildWindow(sub,  self)
        sub.show()

        if sub.FillPhotos(filter) is False:

            # abort if filter found no photos
            sub.close()
            self.CreateMessageNoResults()
            
        QApplication.restoreOverrideCursor()         


    def setCountryFilter(self, country):
        index = self.cboCountries.findText(country)
        if index >= 0:
             self.cboCountries.setCurrentIndex(index)

             
    def setCountyFilter(self, county):
        self.cboCountries.setCurrentIndex(0)
        self.cboStates.setCurrentIndex(0)
        index = self.cboCounties.findText(county)
        if index >= 0:
             self.cboCounties.setCurrentIndex(index)

             
    def setStateFilter(self, state):
        self.cboCountries.setCurrentIndex(0)
        index = self.cboStates.findText(state)
        if index >= 0:
             self.cboStates.setCurrentIndex(index)


    def setLocationFilter(self, location):
        self.cboCountries.setCurrentIndex(0)
        self.cboStates.setCurrentIndex(0)
        self.cboCounties.setCurrentIndex(0)
        index = self.cboLocations.findText(location)
        if index >= 0:
             self.cboLocations.setCurrentIndex(index)


    def setSpeciesFilter(self, species):
        index = self.cboSpecies.findText(species)
        if index >= 0:
             self.cboSpecies.setCurrentIndex(index)


    def setFamilyFilter(self, family):
        index = self.cboFamilies.findText(family)
        if index >= 0:
             self.cboFamilies.setCurrentIndex(index)
             

    def setDateFilter(self, startDate, endDate = ""):
        
        # if only one date is specified, use that date for both start and end dates
        if endDate == "":
            endDate = startDate
            
        startYear = int(startDate[0:4])
        startMonth = int(startDate[5:7])
        startDay = int(startDate[8:])
        myStartDate = QDate()
        myStartDate.setDate(startYear, startMonth, startDay)
        
        endYear = int(endDate[0:4])
        endMonth = int(endDate[5:7])
        endDay = int(endDate[8:])
        myEndDate = QDate()
        myEndDate.setDate(endYear, endMonth, endDay)        
        
        self.calStartDate.setDate(myStartDate)
        self.calEndDate.setDate(myEndDate)


    def setPhotoFolder(self):
        
        directory = str(QFileDialog.getExistingDirectory(self, "Select Directory"))

        directory = os.fsencode(directory)
        
        self.db.attachPhotos(directory)


    def createEditPhotosByFilter(self):
        
        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        # create new Date Totals child window        
        sub = code_ManagePhotos.ManagePhotos()

        # save the MDI window as the parent for future use in the child        
        sub.mdiParent = self 
        
        # call the child's routine to fill it with data
        if sub.FillPhotosByFilter(self.GetFilter()) is True:

            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()            
        
        else:
                    
            # abort since filter found no sightings for child
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor() 


    def setSeasonalRangeFilter(self, month):
        index = self.cboStartSeasonalRangeMonth.findText(month)
        if index >= 0:
            self.cboStartSeasonalRangeMonth.setCurrentIndex(index)
            self.cboEndSeasonalRangeMonth.setCurrentIndex(index)
            self.cboStartSeasonalRangeDate.setCurrentIndex(0)
            self.cboEndSeasonalRangeDate.setCurrentIndex(30)

             
    def showStandardFilter(self):
        self.dckFilter.show()
        self.actionShowStandardFilter.setVisible(False)
        self.actionHideStandardFilter.setVisible(True)

        
    def hideStandardFilter(self):
        self.dckFilter.hide()
        self.actionHideStandardFilter.setVisible(False)
        self.actionShowStandardFilter.setVisible(True)        


    def showPhotoFilter(self):
        self.dckPhotoFilter.show()
        self.actionShowPhotoFilter.setVisible(False)
        self.actionHidePhotoFilter.setVisible(True)
        
        
    def hidePhotoFilter(self):
        self.dckPhotoFilter.hide()
        self.actionHidePhotoFilter.setVisible(False)
        self.actionShowPhotoFilter.setVisible(True)
        
        
    def keyPressEvent(self, e):
        # open file dialog routine if user presses Crtl-O
        if e.key() == Qt.Key_O and e.modifiers() & Qt.ControlModifier:
            self.openDataFileClicked()

        # open file dialog routine if user presses Crtl-O
        if e.key() == Qt.Key_F and e.modifiers() & Qt.ControlModifier:
            self.CreateFind()
            
                
    def CalendarClicked(self):
        if MainWindow.db.eBirdFileOpenFlag is True:
            self.cboDateOptions.setCurrentIndex(1)


    def CreateFind(self):
        
        # if no data file is currently open, abort
        if MainWindow.db.eBirdFileOpenFlag is False:
            self.CreateMessageNoFile()   
            return
        
        sub = code_Find.Find()
        
        # save the MDI window as the parent for future use in the child            
        sub.mdiParent = self
        
        # add and position the child to our MDI area        
        self.mdiArea.addSubWindow(sub)
        #sub.setGeometry(self.dckFilter.width() * 2, self.dckFilter.height() * .25, sub.width(), sub.height())
        
        #sub.scaleMe()
        #sub.resizeMe()
        
        sub.show()
        
        
    def CreateMessageNoFile(self):
        QApplication.restoreOverrideCursor() 
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("No ebird data is currently loaded.\n\nPlease open an eBird data file.")
        msg.setWindowTitle("No Data")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()


    def CreateMessageNoResults(self):
        
        QApplication.restoreOverrideCursor() 
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("No sightings match the current filter settings.")
        msg.setWindowTitle("No Sightings")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()
        
        
    def PositionChildWindow(self, child,  creatingWindow):

        # Qt's QMdiArea only allows one maximized subwindow at a time.
        # Capture whether the MDI area is in maximized mode *before* restoring,
        # then restore the sibling so the new child can be freely positioned.
        # After scaleMe has set the restore size, maximize the new child.
        # QTimer(50ms) ensures both synchronous and QTimer(0) scaleMe calls
        # complete before showMaximized fires.
        spawned_from_maximized = any(
            w.isMaximized() for w in self.mdiArea.subWindowList() if w is not child)
        if spawned_from_maximized:
            for w in self.mdiArea.subWindowList():
                if w is not child and w.isMaximized():
                    w.showNormal()
                    break

        # if creatingWindow is the maind MDI window, center the new child window
        if creatingWindow.objectName() == "MainWindow":
            childWindowCoordinates = []
            for window in self.mdiArea.subWindowList():
                if window.isVisible() == True:
                    childWindowCoordinates.append([window.x(),  window.y()])
            # try to place child window, but check if that would exactly overlap another window
            x = 10
            y = 10
            # if x, y is already the top left coordinate of a child window, add 20 to x and y and retry
            while [x, y] in childWindowCoordinates:
                x = x + 25
                y = y + 25
            child.setGeometry(x, y, child.width(), child.height())

        # if creatingWindow is a child window, place new child window cascaded down from calling creatingWindow
        else:
            x = creatingWindow.x() + 25
            y = creatingWindow.y() + 25
        child.setGeometry(x, y, child.width(), child.height())

        child.setFocus()

        if spawned_from_maximized:
            QTimer.singleShot(50, child.showMaximized)


    def closeDataFile(self):
                
        
        self.checkIfPhotoDataNeedSaving()
        self.ResetMainWindow()
        self.db.ClearDatabase()



    def checkIfPhotoDataNeedSaving(self):
        
        # check to see if unsaved photo settings exist
        if self.db.photosNeedSaving is True:
            
            # ask if user wants to save photo settings
            QApplication.restoreOverrideCursor() 
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setText("Some photo attachment settings have not been saved\n\nDo you want to save them?")
            msg.setWindowTitle("Save Photo Settings?")
            msg.setStandardButtons(QMessageBox.StandardButton.No | QMessageBox.StandardButton.Save)
            buttonClicked = msg.exec()
            
            if buttonClicked == QMessageBox.StandardButton.Save:
                
                self.savePhotoSettings()
                
        return(True)
                
                
    def openDataFileClicked(self):

        self.ResetMainWindow()
        self.db.ClearDatabase()
        self.clearStandardFilter()
                
        self.OpenDataFile()

        if MainWindow.db.eBirdFileOpenFlag is True:
            self.FillMainComboBoxes()
            self.dckFilter.setVisible(True)        
            self.CreateSpeciesList()


    def OpenDataFile(self, startupFolder = ""):  
        # clear and close any data if a file is already open

        self.closeDataFile()
        
        QApplication.processEvents()
                
        if os.path.isdir(startupFolder):
            
            list_of_files = []
            
            for file in os.listdir(startupFolder):
                                
                if file.endswith(".zip") and "ebird" in str(file):
                    
                    list_of_files.append(os.path.join(startupFolder, file))
            
            try:
                #try to get the most recent file from the list of ebird zip files, if any were found
                fname = max(list_of_files, key=os.path.getctime)
            except:
                #none were found, so return an empty string.  Tell ther user.
                fname = ""
                msg = QMessageBox()
                msg.setText("No ebird file was found in the startup folder specified in your preferences.")
                msg.exec()

        else:
            
            #No startup folder was specified, so ask user which ebird file to open.  Take only the first element of the tuple, which is the filename
            fname = QFileDialog.getOpenFileName(self,"QFileDialog.getOpenFileNames()", "","eBird Data Files (*.csv *.zip)")[0]   
                
        if fname != "":
            
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
                        
            QApplication.processEvents()

            MainWindow.db.ReadDataFile(fname)            
            
            # Load helper files using resource_path from Code_DataBase

            # Taxonomy file
            taxonomyFile = code_DataBase.resource_path("eBird_Taxonomy.csv")
            if os.path.isfile(taxonomyFile):
                MainWindow.db.ReadTaxonomyDataFile(taxonomyFile)

            # Country/state code file
            countryStateCodeFile = code_DataBase.resource_path("ebird_api_ref_location_eBird_list_subnational1.csv")
            if os.path.isfile(countryStateCodeFile):
                MainWindow.db.ReadCountryStateCodeFile(countryStateCodeFile)

            # BBL banding code file
            bblCodeFile = code_DataBase.resource_path("eBird_BBLCodes.csv")
            if os.path.isfile(bblCodeFile):
                MainWindow.db.ReadBBLCodeFile(bblCodeFile)
                                             
        QApplication.restoreOverrideCursor()


    def CreateBigReport(self): 
        # the Create Analysis Report button was clicked
        # spawn a new ChildAnalysis window and fill it
        
        # if no data file is currently open, abort
        if MainWindow.db.eBirdFileOpenFlag is False:
            self.CreateMessageNoFile()
            return

        # get the current filter settings to validate before proceeding
        filter = self.GetFilter()

        # check if filter is completely empty (no meaningful constraints set)
        filterIsEmpty = (
            filter.getLocationName() == "" and
            filter.getStartDate() == "" and
            filter.getEndDate() == "" and
            filter.getSpeciesName() == "" and
            filter.getSpeciesList() == [] and
            filter.getFamily() == "" and
            filter.getChecklistID() == "" and
            filter.getCommonNameSearch() == "" and
            filter.getStartSeasonalMonth() == ""
        )
        if filterIsEmpty:
            QMessageBox.information(
                self,
                "No Filter Set",
                "Please set a filter before generating a Big Report.\n\n"
                "A Big Report with no filter will query your entire dataset and may take a very long time.",
                QMessageBox.StandardButton.Ok
            )
            return

        # if a date range is set, warn if it spans more than one year
        startDate = filter.getStartDate()
        endDate = filter.getEndDate()
        if startDate != "" and endDate != "":
            d0 = datetime.datetime.strptime(startDate, "%Y-%m-%d")
            d1 = datetime.datetime.strptime(endDate, "%Y-%m-%d")
            if (d1 - d0).days > 365:
                reply = QMessageBox.question(
                    self,
                    "Large Date Range",
                    f"The selected date range spans more than one year "
                    f"({startDate} to {endDate}).\n\n"
                    "Generating this report may take a long time. Proceed anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        # create new Analysis child window
        sub = code_BigReport.BigReport()
        
        # set the mdiParent variable in the child so it can know the 
        # object that called it (for later use in the child)
        sub.mdiParent = self
        
        # call the child's routine to fill it with data
        if sub.FillAnalysisReport(filter) is False:
            self.CreateMessageNoResults()
            sub.close()
            
        else:
        
            # add child to MDI area and position it
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)

        QApplication.restoreOverrideCursor()


    def CreateChecklistsList(self): 
        # Create Filtered List button was clicked
        # create filtered species list child
        
        # if no data file is currently open, abort
        if MainWindow.db.eBirdFileOpenFlag is False:
            self.CreateMessageNoFile()   
            return
            
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))            
        
        # get the current filter settings in a list to pass to child
        filter = self.GetFilter()
        
        # create child window 
        sub = code_Lists.Lists()
        
        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self
        
        # call the child's fill routine, passing the filter settings list
        if sub.FillChecklists(filter) is True:
            
            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.resize(1000, sub.height())
            sub.show()
            sub.scaleMe()

        else:

            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()
                    
                 
    def CreatePDF(self):
        
        activeWindow = self.mdiArea.activeSubWindow()

        if activeWindow is None:
            return

        if activeWindow.objectName() in ([
            "frmSpeciesList", 
            "frmFamilies", 
            "frmCompare", 
            "frmDateTotals", 
            "frmLocationTotals", 
            "frmWeb", 
            "frmIndividual", 
            "frmLocation",
            "frmBigReport"
            ]):

            # create a QTextDocument in memory to hold and render our content
            document = QTextDocument()

            # create a QPrinter object for the printer the user later selects
            printer = QPrinter()
            
            # set printer to PDF output, Letter size
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setPaperSize(QPrinter.Letter);
            printer.setPageMargins(20, 10, 10, 10, QPrinter.Millimeter)

            # set the document to the printer's page size
            pageSize = printer.paperSize(QPrinter.Point)
            document.setPageSize(pageSize)
            
            filename = QFileDialog.getSaveFileName(self, "Save PDF File", "", "PDF Files (*.pdf)")
            
            if filename[0] != "":
                
                # set output file name
                printer.setOutputFileName(filename[0])
            
                # get html content from child window
                html = activeWindow.html()

                # load the html into the document
                document.setHtml(html)

                # create the PDF file by printing to the "printer" (which is set to PDF)
                document.print_(printer)  

                if sys.platform == "win32":
                    os.startfile(filename[0])
                else:
                    opener ="open" if sys.platform == "darwin" else "xdg-open"
                    subprocess.call([opener, filename[0]])
                                
              
    def CreateSpeciesList(self): 
        # Create Filtered List button was clicked
        # create filtered species list child
        
        # if no data file is currently open, abort
        if MainWindow.db.eBirdFileOpenFlag is False:
            self.CreateMessageNoFile()   
            return
            
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))            
        
        # get the current filter settings in a list to pass to child
        filter = self.GetFilter()
        
        # create child window 
        sub = code_Lists.Lists()
        
        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self
        
        # call the child's fill routine, passing the filter settings list
        if sub.FillSpecies(filter) is True:
            
            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()
            sub.scaleMe()

        else:

            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()


    def CreateLocationTotals(self):   

        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        filter = self.GetFilter()
        # create new Location Totals child window        
        sub = code_LocationTotals.LocationTotals()

        # save the MDI window as the parent for future use in the child        
        sub.mdiParent = self        

        # call the child's routine to fill it with data        
        # procede if the child successfully filled with data
        if sub.FillLocationTotals(filter) is True:

            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)

        else:

            # abort if filter found no sightings for child
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()


    def CreateAboutYearbird(self):

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Web.Web()

        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self

        # call the child's routine to fill it with data
        sub.loadAboutYearbird()

        # add and position the child to our MDI area
        self.mdiArea.addSubWindow(sub)
        self.PositionChildWindow(sub,  self)
        sub.show()

        QApplication.restoreOverrideCursor()


    def CreateUserGuide(self):

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Web.Web()
        sub.mdiParent = self
        sub.loadUserGuide()

        self.mdiArea.addSubWindow(sub)
        self.PositionChildWindow(sub, self)
        sub.show()

        QApplication.restoreOverrideCursor()


    def CreateMap(self):   

        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        filter = self.GetFilter()
        # create new Location Totals child window        
        sub = code_Web.Web()

        # save the MDI window as the parent for future use in the child        
        sub.mdiParent = self        

        # call the child's routine to fill it with data        
        if sub.LoadLocationsMap(filter) is True:
            
            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()

        else:
            # abort if filter found no sightings for map
            self.CreateMessageNoResults()
            sub.close()
            
        QApplication.restoreOverrideCursor() 

        
    def CreateDateTotals(self):  

        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        # create new Date Totals child window        
        sub = code_DateTotals.DateTotals()

        # save the MDI window as the parent for future use in the child        
        sub.mdiParent = self 
        
        # call the child's routine to fill it with data
        if sub.FillDateTotals(self.GetFilter()) is True:

            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)

        else:

            # abort since filter found no sightings for child
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()


    def CreateBarGraph(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetFilter(), "bar") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()

    def CreateTotalChecklistsGraph(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetFilter(), "totalchecklists") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()

    def CreateTotalLocationsGraph(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetFilter(), "totallocations") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()

    def CreateCumulativeCurve(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetFilter(), "cumulative") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()

    def CreateCumulativeLocationsCurve(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetFilter(), "cumulativelocations") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()

    def CreateCumulativeFamiliesCurve(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetFilter(), "cumulativefamilies") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()

    def CreateHeatmap(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetFilter(), "heatmap") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()

    def CreateAccumulationChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetFilter(), "accumulation") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()


    def CreateTopLocations(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetFilter(), "locations") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()

    def CreateScatterChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetFilter(), "scatter") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()

    def CreatePhenologyChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        f = self.GetFilter()
        if (f.getSpeciesName() == "" and f.getCommonNameSearch() == ""
                and f.getFamily() == "" and f.getOrder() == ""):
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self,
                "No Species Filter",
                "No species, family, or order filter is set.\n\n"
                "The Phenology Chart is most useful for a species, family, or order. "
                "Generating it for your entire dataset may be too cluttered "
                "to read clearly.\n\n"
                "Generate it anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No)
            if reply == QMessageBox.No:
                return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(f, "strip") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()

    def CreateFOYChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetFilter(), "foy") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()

    def CreateLOYChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetFilter(), "loy") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()

    def CreateIndivPieChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetFilter(), "indivpie") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()

    def CreateFamilyPieChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetFilter(), "familypie") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()

    def CreateFamiliesReport(self):

        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        # create Families Report child window
        sub = code_Families.Families()
        
        # save the MDI window as the parent for future use in the child        
        sub.mdiParent = self
        
        # get filter 
        filter = self.GetFilter()
        
        # call the child's routine to fill it with data
        # these must be called in this exact order, or else the pic chart won't draw 
        # large enough to fill its area.  I don't really know why.
        if sub.FillFamilies(filter) is True:
        
            sub.scaleMe()
            sub.resizeMe()
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)        
            sub.show()
                       
            sub.FillPieChart()

            sub.scaleMe()
            
                        
        else:
            
            # abort if no families matched the filter
            self.CreateMessageNoResults()
            sub.close()
        
        QApplication.restoreOverrideCursor()   
           
           
    def CreateCompareLists(self):    

        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        # create new Compare child window
        sub = code_Compare.Compare()
        
        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self

        # call the child's routine to fill it with data
        if sub.FillListChoices() is True:

            # add and position the child to our MDI area        
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.scaleMe()
            sub.resizeMe()
            sub.show()

        else:
            
            QApplication.restoreOverrideCursor() 
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setText("Fewer than two lists are available to compare. \n\nCreate two or more species lists before trying to compare them.")
            msg.setWindowTitle("No Species Lists")
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()            
            sub.close()

        QApplication.restoreOverrideCursor()   


    def CreateLocationsList(self):      
        
        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        filter = self.GetFilter()
                
        # create a new list child window
        sub = code_Lists.Lists()
        
        # save the MDI window as the parent for future use in the child            
        sub.mdiParent = self

        # call the child's routine to fill it with data
        if sub.FillLocations(filter) is True:
        
            # add and position the child to our MDI area        
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()
            sub.scaleMe()

        else:

            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()
        
        
    def GetFilter(self):
        startDate = ""
        endDate= ""
        startSeasonalMonth = ""
        startSeasonalDay = ""
        endSeasonalMonth = ""
        endSeasonalDay = ""
        locationType = ""
        locationName = "" 
        speciesName = ""
        family = ""
        order = ""
        commonNameSearch = ""
        startRating = ""
        endRating = ""
        speciesHasPhoto = ""
        validPhotoSpecies = []
        camera = ""
        lens = ""
        startShutterSpeed = ""
        endShutterSpeed = ""
        startAperture = ""
        endAperture = ""
        startFocalLength = ""
        endFocalLength = ""
        startIso = ""
        endIso = ""
        
        # check whether calendar widgets are used
        if self.cboDateOptions.currentText() == "Use Calendars Below":
            
            # get yyyy-mm-dd start date string from widget
            startDate = (
                                   str(self.calStartDate.date().year()) 
                                + "-" 
                                + str(self.calStartDate.date().month()) 
                                + "-" 
                                + str(self.calStartDate.date().day()))
            
            # get yyyy-mm-dd end date string from widget
            endDate = (
                                   str(self.calEndDate.date().year()) 
                                + "-" 
                                + str(self.calEndDate.date().month()) 
                                + "-" 
                                + str(self.calEndDate.date().day())
                                )
                                
        # Check if Today radio button is checked.
        # If so, just create yyyy-mm-dd for today.
        if self.cboDateOptions.currentText() == "Today":

            now = datetime.datetime.now()

            startDate = (
                                      str(now.year) 
                                   + "-" 
                                   + str(now.month) 
                                   + "-" 
                                   + str(now.day)
                                   )
            
            # since this is a single day, startDate and endDate are the same
            endDate = startDate    
            
        if self.cboDateOptions.currentText() == "Yesterday":
            now = datetime.datetime.now()
           
           # subtract a day from today to get yesterday
            yesterday = now + datetime.timedelta(days=-1)
            
            # convert to yyyy-mm-dd string
            startDate = (
                                      str(yesterday.year) 
                                   + "-" 
                                   + str(yesterday.month) 
                                   + "-" 
                                   + str(yesterday.day)
                                   )
            
            # since this is a single day, startDate and endDate are the same
            endDate = startDate

        if self.cboDateOptions.currentText() == "Last Weekend":
            now = datetime.datetime.now()
            
            todayDayOfWeek = now.weekday()
           
           # subtract a day from today to get yesterday
            lastSunday = now + datetime.timedelta(days = 0 - todayDayOfWeek - 1)
            lastSaturday = lastSunday + datetime.timedelta(days = -1)
            
            # convert to yyyy-mm-dd string
            startDate = (
                                      str(lastSaturday.year) 
                                   + "-" 
                                   + str(lastSaturday.month) 
                                   + "-" 
                                   + str(lastSaturday.day)
                                   )

            endDate = (
                                      str(lastSunday.year) 
                                   + "-" 
                                   + str(lastSunday.month) 
                                   + "-" 
                                   + str(lastSunday.day)
                                   )

        # Check if This Year radio button is checked.
        # if so, create yyyy-01-01 and yyyy-12-31 start and end dates
        if self.cboDateOptions.currentText() == "This Year":

            now = datetime.datetime.now()
            
            # set startDate to January 1 of this year
            startDate = str(now.year) + "-01-01"
            
            # set endDate to December 31 of this year
            endDate = str(now.year) + "-12-31"

        
        # Check if This Month radio button is checked
        # if so, create yyyy-mm-01 and yyyy-mm-31 dates
        # We'll need to get the correct number for the last day of the month
        if self.cboDateOptions.currentText() == "This Month":
            
            now = datetime.datetime.now()

            # startDate should be first day of this month
            # convert to yyyy-mm-dd string
            startDate = (
                                      str(now.year) 
                                   + "-" 
                                   + str(now.month) 
                                   + "-" 
                                   + "01"
                                   )
            
            # lastDate is trickier. Need the last day of month, which varies numerically by month.
            # set day to 28 and then add 4 days. This guarantees finding a date in next month
            dayInNextMonth= now.replace(day=28) + datetime.timedelta(days=4)
            
             # Now set the date to 1 so we're at the first day of next month
            firstOfNextMonth = dayInNextMonth.replace(day=1)
            
            # Now subtract a day from the  first of next month, which back into the last day of this month
            lastDayOfThisMonth = firstOfNextMonth + datetime.timedelta(days = -1)
            # convert to yyyy-mm-dd string
            endDate = (
                                     str(lastDayOfThisMonth.year) 
                                  + "-" 
                                  + str(lastDayOfThisMonth.month) 
                                  + "-" 
                                  + str(lastDayOfThisMonth.day)
                                  )

        # add leading 0 to date digit strings if less than two digits
        # only take action if startDate has a value
        if not startDate == "":
           
            # get the date digit(s) from the yyyy-mm-d(d) string
            # they might be only 1 digit long, hence the need to pad
            startDateDigits = startDate.split("-")[2]
            endDateDigits = endDate.split("-")[2]
            
            if len(startDateDigits) < 2:
                
                # pad with 0, because date is only one digit
                startDateDigits = "0" + startDateDigits
            
            if len(endDateDigits) < 2:
                
                # pad with 0, because date is only one digit
                endDateDigits = "0" + endDateDigits
                
            # add leading 0 to month digit strings if less than two digits
           
            # get the month digit(s) from the yyyy-m(m)-dd string
            # they might be only 1 digit long, hence the need to pad
            startMonthDigits = startDate.split("-")[1]
            endMonthDigits = endDate.split("-")[1]
            
            if len(startMonthDigits) < 2:

                # pad with 0, because month is only one digit                
                startMonthDigits = "0" + startMonthDigits
            
            if len(endMonthDigits) < 2:
                
                # pad with 0, because month is only one digit                
                endMonthDigits = "0" + endMonthDigits 
                
            # reassemble padded Start and End Dates in yyyy-mm-dd string
            startDate = (
                                     startDate[0:4]   # year digits yyyy
                                     + "-" 
                                     + startMonthDigits 
                                     + "-" 
                                     + startDateDigits
                                    )
            
            endDate = (
                                     endDate[0:4]  # year digits yyyy
                                     + "-" 
                                     + endMonthDigits 
                                     + "-" 
                                     + endDateDigits
                                    )

        if self.cboSeasonalRangeOptions.currentText() == "Use Range Below":
           
            # read date month number from combobox, and add one to convert from
           # zero-based to one-based month 
            startSeasonalMonth = str(self.cboStartSeasonalRangeMonth.currentIndex()+1)
           
            # read startSeasonalDay from combobox
            startSeasonalDay = self.cboStartSeasonalRangeDate.currentText()
            
            # read date month number from combobox, and add one to convert from
            # zero-based to one-based month 
            endSeasonalMonth  = str(self.cboEndSeasonalRangeMonth.currentIndex()+1)
            
            # read endSeasonalDay from combobox
            endSeasonalDay  = self.cboEndSeasonalRangeDate.currentText()      
      
            # add leading 0 to seasonal month and date strings if less than two digits
            if len(startSeasonalMonth) < 2:
                startSeasonalMonth = "0" + startSeasonalMonth
            
            if len(startSeasonalDay) < 2:
                startSeasonalDay = "0" + startSeasonalDay    
            
            if len(endSeasonalMonth) < 2:
                endSeasonalMonth = "0" + endSeasonalMonth
            
            if len(endSeasonalDay) < 2:
                endSeasonalDay = "0" + endSeasonalDay                    

        if self.cboSeasonalRangeOptions.currentText() == "Spring":
            startSeasonalMonth = "03"
            startSeasonalDay = "20"
            endSeasonalMonth = "06"
            endSeasonalDay = "19"

        if self.cboSeasonalRangeOptions.currentText() == "Summer":
            startSeasonalMonth = "06"
            startSeasonalDay = "20"
            endSeasonalMonth = "09"
            endSeasonalDay = "19"

        if self.cboSeasonalRangeOptions.currentText() == "Fall":
            startSeasonalMonth = "09"
            startSeasonalDay = "20"
            endSeasonalMonth = "12"
            endSeasonalDay = "19"

        if self.cboSeasonalRangeOptions.currentText() == "Winter":
            startSeasonalMonth = "12"
            startSeasonalDay = "20"
            endSeasonalMonth = "03"
            endSeasonalDay = "19"
         
        if self.cboSeasonalRangeOptions.currentText() == "This Month":
            now = datetime.datetime.now()
            startSeasonalMonth = str(now.month)
            if len(startSeasonalMonth) == 1:
                startSeasonalMonth = "0" + startSeasonalMonth
            endSeasonalMonth = startSeasonalMonth
            startSeasonalDay = "01"
            endSeasonalDay = MainWindow.db.GetLastDayOfMonth(startSeasonalMonth)

        if self.cboSeasonalRangeOptions.currentText() == "Year to Date":
            now = datetime.datetime.now()
            startSeasonalMonth = "01"
            startSeasonalDay = "01"
            endSeasonalMonth = str(now.month)
            endSeasonalDay = str(now.day)
            # add leading 0 to seasonal month and date strings if less than two digits
            if len(endSeasonalMonth) < 2:
                endSeasonalMonth = "0" + endSeasonalMonth
            
            if len(endSeasonalDay) < 2:
                endSeasonalDay = "0" + endSeasonalDay  

        if self.cboSeasonalRangeOptions.currentText() == "Remainder of Year":
            now = datetime.datetime.now()
            startSeasonalMonth = str(now.month)
            startSeasonalDay = str(now.day)
            endSeasonalMonth = "12"
            endSeasonalDay = "31"
            # add leading 0 to seasonal month and date strings if less than two digits
            if len(startSeasonalMonth) < 2:
                startSeasonalMonth = "0" + startSeasonalMonth
            
            if len(endSeasonalDay) < 2:
                startSeasonalDay = "0" + startSeasonalDay 

        monthList = ([
            "January",  
            "February",  
            "March",  
            "April",  
            "May", 
            "June",  
            "July",  
            "August",  
            "September",  
            "October",  
            "November",
            "December"
            ])
        
        if self.cboSeasonalRangeOptions.currentText() in monthList:
            
            startSeasonalMonth = str(monthList.index(self.cboSeasonalRangeOptions.currentText()) + 1)
            # add leading 0 to seasonal month and date strings if less than two digits
            if len(startSeasonalMonth) < 2:
                startSeasonalMonth = "0" + startSeasonalMonth
            endSeasonalMonth = startSeasonalMonth
            startSeasonalDay = "01"
            endSeasonalDay = "31"
            if startSeasonalMonth in ["03", "04", "06", "09", "11"]:
                endSeasonalDay = "30"
            if startSeasonalMonth == "02":
                endSeasonalDay = "29"
                
        # check location comboboxes to learn location type and name
        # Only get location information if user has selected one
        # we'll cycle through cbo boxes, from most general to specific
        # we'll save the most specific one in the filter

        if self.cboRegions.currentText() != None:
            
            if self.cboRegions.currentText() != "**All Regions**":
                
                # for region name, get the short code,which the db uses for searches
                locationName = MainWindow.db.GetRegionCode(self.cboRegions.currentText())
                locationType = "Region"
                
        if self.cboCountries.currentText() != None:
            
            if self.cboCountries.currentText() != "**All Countries**":
                
                # for country name, get the short code,which the db uses for searches
                locationName = MainWindow.db.GetCountryCode(self.cboCountries.currentText())
                locationType = "Country"
       
        if self.cboStates.currentText() != None:
            
            if self.cboStates.currentText() != "**All States**":
                
                # for state name, get the short code, which the db uses for searches
                locationName = MainWindow.db.GetStateCode(self.cboStates.currentText())
                locationType = "State"
      
        if self.cboCounties.currentText() != None:
            
            if self.cboCounties.currentText() != "**All Counties**":
                
                locationName = self.cboCounties.currentText()
                locationType = "County"
        
        if self.cboLocations.currentText() != None:
            
            if self.cboLocations.currentText() != "**All Locations**":
                
                locationName = self.cboLocations.currentText()
                locationType = "Location"

        # check species combobox to learn species name
        if self.cboSpecies.currentText() != None:
            
            if self.cboSpecies.currentText() != "**All Species**":
                
                speciesName = self.cboSpecies.currentText()

        # check order combobox
        if self.cboOrders.currentText() != None:
            
            if self.cboOrders.currentText() != "**All Orders**":
                
                order = self.cboOrders.currentText()

        # check family combobox
        if self.cboFamilies.currentText() != None:
            
            if self.cboFamilies.currentText() != "**All Families**":
                
                family = self.cboFamilies.currentText()


        # check Common Name Search test
        if self.txtCommonNameSearch.text() != "":
                
            commonNameSearch = self.txtCommonNameSearch.text().rstrip()               


        # check sighting combobox
        if self.cboStartRatingRange.currentText() != None:
            
            if "**" not in self.cboStartRatingRange.currentText():
                
                startRating = self.cboStartRatingRange.currentText()
                
        # check sighting combobox
        if self.cboEndRatingRange.currentText() != None:
            
            if "**" not in self.cboEndRatingRange.currentText():
                
                endRating = self.cboEndRatingRange.currentText()                

        # check sighting combobox
        if self.cboSpeciesHasPhoto.currentText() != None:
            
            if "**" not in self.cboSpeciesHasPhoto.currentText():
                
                speciesHasPhoto = self.cboSpeciesHasPhoto.currentText()

        # check camera combobox
        if self.cboCamera.currentText() != None:
            
            if "**" not in self.cboCamera.currentText():
                
                camera = self.cboCamera.currentText()

        # check lens combobox
        if self.cboLens.currentText() != None:
            
            if "**" not in self.cboLens.currentText():
                
                lens = self.cboLens.currentText()

        # check start shutter speed combobox
        if self.cboStartShutterSpeedRange.currentText() != None:
            
            if "**" not in self.cboStartShutterSpeedRange.currentText():
                
                startShutterSpeed = self.cboStartShutterSpeedRange.currentText()
                
        # check end shutter speed combobox
        if self.cboEndShutterSpeedRange.currentText() != None:
            
            if "**" not in self.cboEndShutterSpeedRange.currentText():
                
                endShutterSpeed = self.cboEndShutterSpeedRange.currentText()

        # check end aperture combobox
        if self.cboEndApertureRange.currentText() != None:
            
            if "**" not in self.cboEndApertureRange.currentText():
                
                endAperture = self.cboEndApertureRange.currentText()

        # check start aperture combobox
        if self.cboStartApertureRange.currentText() != None:
            
            if "**" not in self.cboStartApertureRange.currentText():
                
                startAperture = self.cboStartApertureRange.currentText()

        # check end Iso combobox
        if self.cboEndIsoRange.currentText() != None:
            
            if "**" not in self.cboEndIsoRange.currentText():
                
                endIso = self.cboEndIsoRange.currentText()

        # check start Iso combobox
        if self.cboStartIsoRange.currentText() != None:
            
            if "**" not in self.cboStartIsoRange.currentText():
                
                startIso = self.cboStartIsoRange.currentText()
                
        # check end FocalLength combobox
        if self.cboEndFocalLengthRange.currentText() != None:
            
            if "**" not in self.cboEndFocalLengthRange.currentText():
                
                endFocalLength = self.cboEndFocalLengthRange.currentText()

        # check start FocalLength combobox
        if self.cboStartFocalLengthRange.currentText() != None:
            
            if "**" not in self.cboStartFocalLengthRange.currentText():
                
                startFocalLength = self.cboStartFocalLengthRange.currentText()                


                                
        # package up the filter list and return it
        newFilter = code_Filter.Filter()
        newFilter.setLocationType(locationType)
        newFilter.setLocationName(locationName)
        newFilter.setStartDate(startDate)
        newFilter.setEndDate(endDate)
        newFilter.setStartSeasonalMonth(startSeasonalMonth)
        newFilter.setEndSeasonalMonth(endSeasonalMonth)
        newFilter.setStartSeasonalDay(startSeasonalDay)
        newFilter.setEndSeasonalDay(endSeasonalDay)
        newFilter.setSpeciesName(speciesName)
        newFilter.setFamily(family)
        newFilter.setOrder(order)
        newFilter.setCommonNameSearch(commonNameSearch)
        
        newFilter.setStartRating(startRating)
        newFilter.setEndRating(endRating)
        newFilter.setSpeciesHasPhoto(speciesHasPhoto)        
        newFilter.setCamera(camera)
        newFilter.setLens(lens)
        newFilter.setStartShutterSpeed(startShutterSpeed)
        newFilter.setEndShutterSpeed(endShutterSpeed)
        newFilter.setStartAperture(startAperture)
        newFilter.setEndAperture(endAperture)
        newFilter.setStartIso(startIso)
        newFilter.setEndIso(endIso)
        newFilter.setStartFocalLength(startFocalLength)
        newFilter.setEndFocalLength(endFocalLength)
        
        # use the filter set up so far to get the valid Photo species
        # do this only if the user has set the species photo cbo box
        if self.cboSpeciesHasPhoto.currentText() == "Photographed":
            validPhotoSpecies = self.db.GetSpeciesWithPhotos(newFilter)
            newFilter.setValidPhotoSpecies(validPhotoSpecies)
        
        if self.cboSpeciesHasPhoto.currentText() == "Not photographed":
            validPhotoSpecies = self.db.GetSpeciesWithoutPhotos(newFilter)
            newFilter.setValidPhotoSpecies(validPhotoSpecies)
        
        return(newFilter)
                           
                                      
    def updateEXIFDataForAllPhotos(self):
                
        # get all sightings with photos
        
        filter = code_Filter.Filter()
        sightings = self.db.GetSightingsWithPhotos(filter)
        
        # find total count of photos in db
        photoCount = 0
        for s in sightings:
            for p in s["photos"]:
                photoCount += 1
                
        # clear pdb's photo list metadata
        self.db.cameraList = []
        self.db.lensList = []
        self.db.apertureList = []
        self.db.shutterSpeedList = []
        self.db.isoList = []
        self.db.focalLengthList = []
        
        # loop through photos, and update each photos EXIF data
        # after each photo, update the db's photo list metadata
        for s in sightings:
            pCount = 0
            for p in s["photos"]:
                photoData = self.db.getPhotoData(p["fileName"])
                # save the rating for the photo 
                photoData["rating"] = p["rating"]
                s["photos"][pCount] = photoData
                self.db.addPhotoDataToDb(photoData)
                pCount += 1
        
        # clear and repopulate photo filter cbo boxes with updated data
        self.fillPhotoComboBoxes()                 

        msgText = "Yearbird updated EXIF data for all attached photos.\n\nRemember to save your photo data file to make these updates permanent."
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(msgText)
        msg.setWindowTitle("Updated EXIF Data")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()         
        
        # set flag indicating that some photo data isn't yet saved to file
        self.db.photosNeedSaving = True
        
        
    def SeasonalRangeClicked(self):
        self.cboSeasonalRangeOptions.setCurrentIndex(1)
        
        
    def TileWindows(self):
        # Restore any minimized windows first
        for w in self.mdiArea.subWindowList():
            if w.isMinimized():
                w.showNormal()
        self.mdiArea.tileSubWindows()
        
        
    def CascadeWindows(self):
        # Restore any minimized or maximized windows first
        for w in self.mdiArea.subWindowList():
            if w.isMinimized() or w.isMaximized():
                w.showNormal()

        # Get windows in stacking order (back-most first, front-most last)
        visibleWindows = [w for w in self.mdiArea.subWindowList(QMdiArea.WindowOrder.StackingOrder) if w.isVisible()]
        if not visibleWindows:
            return

        # Scale every window to its default size first
        for w in visibleWindows:
            if w.windowTitle() != "Enlargement":
                w.scaleMe()

        # Cascade: position each window offset by title bar height from the previous,
        # and raise_ each in order so z-order matches cascade position
        titleBarHeight = 25
        x, y = 0, 0
        for w in visibleWindows:
            w.move(x, y)
            w.raise_()
            x += titleBarHeight
            y += titleBarHeight
        
    def CloseAllWindows(self):
        self.mdiArea.closeAllSubWindows()


    def HideMainWindowOptions(self):
        self.clearStandardFilter()
        self.clearPhotoFilter()
        self.dckFilter.setVisible(False)
        self.dckPhotoFilter.setVisible(False)
        

    def ShowMainWindowOptions(self):
        self.dckFilter.setVisible(True)


    def SetChildDetailsLabels(self,  sub,  filter):
        locationType = filter.getLocationType()                             # str   choices are Country, County, State, Location, or ""
        locationName = filter.getLocationName()                         # str   name of region or location  or ""
        startDate = filter.getStartDate()                                           # str   format yyyy-mm-dd  or ""
        endDate = filter.getEndDate()                                               # str   format yyyy-mm-dd  or ""
        startSeasonalMonth = filter.getStartSeasonalMonth() # str   format mm
        startSeasonalDay = filter.getStartSeasonalDay()            # str   format dd
        endSeasonalMonth  = filter.getEndSeasonalMonth()    # str   format  dd
        endSeasonalDay  = filter.getEndSeasonalDay()               # str   format dd
        checklistID = filter.getChecklistID()                                     # str   checklistID
        speciesName = filter.getSpeciesName()                           # str   speciesName
        family = filter.getFamily()                                                         # str family name
        order = filter.getOrder()
        commonNameSearch = filter.getCommonNameSearch()
        sightingPhotographed = filter.getSightingHasPhoto()
        speciesPhotographed = filter.getSpeciesHasPhoto()
        camera = filter.getCamera()
        lens = filter.getLens()
        startShutterSpeed = filter.getStartShutterSpeed()
        endShutterSpeed = filter.getEndShutterSpeed()
        startAperture = filter.getStartAperture()
        endAperture = filter.getEndAperture()
        startIso = filter.getStartIso()
        endIso = filter.getEndIso()
        startFocalLength = filter.getStartFocalLength()
        endFocalLength = filter.getEndFocalLength()
        
        # set main location label, using "All Locations" if none others are selected
        if locationName == "":   
            sub.lblLocation.setText("All Locations")
        else:
            if locationType == "Region":
                sub.lblLocation.setText(MainWindow.db.GetRegionName(locationName))
            elif locationType == "Country":
                sub.lblLocation.setText(MainWindow.db.GetCountryName(locationName))
            elif locationType == "State":
                sub.lblLocation.setText(MainWindow.db.GetStateName(locationName))       
            else:
                sub.lblLocation.setText(locationName)
        
        if speciesName != "":
            sub.lblLocation.setText(speciesName +": " + sub.lblLocation.text())
            
        # set main date range label, using "AllDates" if none others are selected
        detailsText = ""
        dateText = ""
        
        if startDate == "":
            dateText = "; All Dates"
        else:
            dateTitle = startDate + " to " + endDate
            if startDate == endDate:
                dateTitle = startDate
            if checklistID != "":
                dateTitle = dateTitle + ": Checklist #" + checklistID
            dateText = "; " + dateTitle

        # set main seasonal range label, if specified
        if not ((startSeasonalMonth == "") or (endSeasonalMonth == "")):
            monthRange = ["Jan",  "Feb",  "Mar",  "Apr", "May",   "Jun",  "Jul",  "Aug",  "Sep",  "Oct",  "Nov",  "Dec"]
            rangeTitle = monthRange[int(startSeasonalMonth)-1] + "-" + startSeasonalDay + " to " + monthRange[int(endSeasonalMonth)-1] + "-" + endSeasonalDay
            dateText = dateText + "; " + rangeTitle
       
        if checklistID != "":
            detailsText = "; Checklist " + checklistID

        if order != "":
            detailsText = detailsText + "; " + order
        
        if family != "":
            detailsText = detailsText + "; " + family
            
        if commonNameSearch != "":
            if "s:" in commonNameSearch:
                detailsText = detailsText + "; Scientific name includes '" +  commonNameSearch.split("s:",1)[1]  + "'"
            else:
                detailsText = detailsText + "; Common name includes '" +  commonNameSearch + "'"

        if sightingPhotographed == "Has photo":
            detailsText = detailsText + "; " + "Sightings with photos"
        if sightingPhotographed == "No photo":
            detailsText = detailsText + "; " + "Sightings without photos"

        if speciesPhotographed == "Photographed":
            detailsText = detailsText + "; " + "Photographed species"
        if speciesPhotographed == "Not photographed":
            detailsText = detailsText + "; " + "Unphotographed species"
            
        if camera != "":
            detailsText = detailsText + "; " + camera            

        if lens != "":
            detailsText = detailsText + "; " + lens
            
        if startShutterSpeed != "" and endShutterSpeed != "":
            if startShutterSpeed == endShutterSpeed:
                detailsText = detailsText + "; Speed: " + startShutterSpeed
            else:
                detailsText = detailsText + "; Speed: " + startShutterSpeed + " to " + endShutterSpeed 
        if startShutterSpeed != "" and endShutterSpeed == "":
            detailsText = detailsText + "; Speed: from " + startShutterSpeed
        if startShutterSpeed == "" and endShutterSpeed != "":
            detailsText = detailsText + "; Speed: to " + endShutterSpeed

        if startAperture != "" and endAperture != "":
            if startAperture == endAperture:
                detailsText = detailsText + "; Aperture: " + startAperture
            else:
                detailsText = detailsText + "; Aperture: " + startAperture + " to " + endAperture 
        if startAperture != "" and endAperture == "":
            detailsText = detailsText + "; Aperture: from " + startAperture
        if startAperture == "" and endAperture != "":
            detailsText = detailsText + "; Aperture: to " + endAperture
            
        if startFocalLength != "" and endFocalLength != "":
            if startFocalLength == endFocalLength:
                detailsText = detailsText + "; Focal Length: " + startFocalLength
            else:
                detailsText = detailsText + "; Focal Length: " + startFocalLength + " to " + endFocalLength 
        if startFocalLength != "" and endFocalLength == "":
            detailsText = detailsText + "; Focal Length: from " + startFocalLength
        if startFocalLength == "" and endFocalLength != "":
            detailsText = detailsText + "; Focal Length: to " + endFocalLength
            
        if startIso != "" and endIso != "":
            if startIso == endIso:
                detailsText = detailsText + "; ISO: " + startIso
            else:
                detailsText = detailsText + "; ISO: " + startIso + " to " + endIso 
        if startIso != "" and endIso == "":
            detailsText = detailsText + "; ISO: from " + startIso
        if startIso == "" and endIso != "":
            detailsText = detailsText + "; ISO: to " + endIso
                        
        #remove leading "; "
        dateText = dateText[2:]
        detailsText = detailsText[2:]
        
        sub.lblDateRange.setText(dateText)
        if dateText =="":
            sub.lblDateRange.setVisible(False)
        else:
            sub.lblDateRange.setVisible(True)
            
        sub.lblDetails.setText(detailsText)
        if detailsText =="":
            sub.lblDetails.setVisible(False)
        else:
            sub.lblDetails.setVisible(True)
       
    
    def FillMainComboBoxes(self):
        
        # use the master lists in db to populate the 4 location comboboxes
        # for each, first add the "**All...**" item. 
        # It's starred to appear at the top of the sorted comboboxes
        self.fillingLocationComboBoxesFlag = True

        self.cboRegions.clear()
        self.cboRegions.addItem("**All Regions**")
        self.cboRegions.addItems(MainWindow.db.regionList)        
                
        self.cboCountries.clear()
        self.cboCountries.addItem("**All Countries**")
        self.cboCountries.addItems(MainWindow.db.countryList)        
        
        self.cboStates.clear()
        self.cboStates.addItem("**All States**")
        self.cboStates.addItems(MainWindow.db.stateList)        
        
        self.cboCounties.clear()
        self.cboCounties.addItem("**All Counties**")
        self.cboCounties.addItems(MainWindow.db.countyList)
        
        self.cboLocations.clear()
        self.cboLocations.addItem("**All Locations**")
        self.cboLocations.addItems(MainWindow.db.locationList)
        
        self.cboSpecies.clear()
        self.cboSpecies.addItem("**All Species**")
        self.cboSpecies.addItems(MainWindow.db.speciesDict.keys())  
        self.cboSpecies.model().sort(0)
        
        self.cboFamilies.clear()
        self.cboFamilies.addItem("**All Families**")
        self.cboFamilies.addItems(MainWindow.db.familyList)

        self.cboOrders.clear()
        self.cboOrders.addItem("**All Orders**")
        self.cboOrders.addItems(MainWindow.db.orderList)
        
        self.fillingLocationComboBoxesFlag = False
                

    def printMe(self):

        activeWindow = self.mdiArea.activeSubWindow()            

        if activeWindow is None:
            return

        if activeWindow.objectName() in ([
            "frmSpeciesList", 
            "frmFamilies", 
            "frmCompare", 
            "frmDateTotals", 
            "frmLocationTotals", 
            "frmWeb", 
            "frmIndividual", 
            "frmLocation",
            "frmBigReport"
            ]):

            # create a QTextDocument in memory to hold and render our content
            document = QTextDocument()

            # create a QPrinter object for the printer the user later selects
            printer = QPrinter()
        
            # get html content from child window
            html = activeWindow.html()

            # load the html into the document
            document.setHtml(html)

            # let user select and configure a printer
            dialog = QPrintDialog(printer, self) 

            # execute the print if the user clicked "Print"
            if dialog.exec():

                # send the html to the physical printer
                document.print_(printer)            


    def ResetMainWindow(self):
        
        self.CloseAllWindows()
        self.clearAllFilters()
        self.hideStandardFilter()
        self.hidePhotoFilter()
        self.db.ClearDatabase()
        

    def ComboRegionsChanged(self):
        
        # Check whether the program is adding locations while reading the data file
        # if so, abort. If not, the user has clicked the combobox and we should proceed
        if self.fillingLocationComboBoxesFlag is False:  
                  
            # set the flag to True so the state, county, and location cbos won't trigger
            self.fillingLocationComboBoxesFlag = True    
            
            # clear the color coding for selected filter components
            self.cboRegions.setStyleSheet("");                
            self.cboCountries.setStyleSheet("");                
            self.cboStates.setStyleSheet("");                
            self.cboCounties.setStyleSheet("");                
            self.cboLocations.setStyleSheet("");                            
       
            # use the selected region to filter the masterLocationList
            # clear the subsidiary comboboxes and populat them anew with filtered locations
            thisRegionName = self.cboRegions.currentText()
            thisRegionCode = MainWindow.db.GetRegionCode(self.cboRegions.currentText())
            self.cboCountries.clear()
            self.cboStates.clear()
            self.cboCounties.clear()
            self.cboLocations.clear()
            
            # if "all regions" is chosen, fill subsidiary cbos with all locations
            # e.g., remove the country filter, if one had existed for the cbos
            if thisRegionName == "**All Regions**":
                self.cboRegions.setStyleSheet("");                
                self.cboCountries.addItem("**All Countries**")
                self.cboStates.addItem("**All States**")
                self.cboCounties.addItem("**All Counties**")
                self.cboLocations.addItem("**All Locations**")
                self.cboCountries.addItems(MainWindow.db.countryList)
                self.cboStates.addItems(MainWindow.db.stateList)
                self.cboCounties.addItems(MainWindow.db.countyList)
                self.cboLocations.addItems(MainWindow.db.locationList)
            
            else:

                self.cboRegions.setStyleSheet("QComboBox { color: #4f8ef7; }")
                
                # initialize lists to store the subsidiary locations
                thisRegionCountries = set()
                thisRegionStates = set()
                thisRegionCounties = set()
                thisRegionLocations = set()
                
                # loop through masterLocationList to find locations filtered for the chosen region
                for l in MainWindow.db.masterLocationList:
                    
                    if thisRegionCode in l["regionCodes"]:
                                                
                        if "countryName" in l.keys():
                            if l["countryName"] != "": thisRegionCountries.add(l["countryName"])
                        
                        if "stateName" in l.keys():
                            if l["stateName"] != "": thisRegionStates.add(l["stateName"])
                        
                        if "county" in l.keys():
                            if l["county"] != "": thisRegionCounties.add(l["county"])
                            
                        if l["location"] != "": thisRegionLocations.add(l["location"])
                
                # remove duplicates using the set command, then return to list format
                thisRegionCountries = list(thisRegionCountries)
                thisRegionStates = list(thisRegionStates)
                thisRegionCounties = list(thisRegionCounties)
                thisRegionLocations = list(thisRegionLocations)
                
                # sort them
                thisRegionCountries.sort()
                thisRegionStates.sort()
                thisRegionCounties.sort()
                thisRegionLocations.sort()
                
                # add filtered locations to comboboxes
                self.cboCountries.addItem("**All Countries**")
                self.cboCountries.addItems(thisRegionCountries)
                self.cboStates.addItem("**All States**")
                self.cboStates.addItems(thisRegionStates)
                self.cboCounties.addItem("**All Counties**")
                self.cboCounties.addItems(thisRegionCounties)
                self.cboLocations.addItem("**All Locations**")
                self.cboLocations.addItems(thisRegionLocations)
            
            # we're done, so reset flag to false to allow future triggers
            self.fillingLocationComboBoxesFlag = False



        
    def ComboCountriesChanged(self):
        
        # Check whether the program is adding locations while reading the data file
        # if so, abort. If not, the user has clicked the combobox and we should proceed
        if self.fillingLocationComboBoxesFlag is False:  
                  
            # set the flag to True so the state, county, and location cbos won't trigger
            self.fillingLocationComboBoxesFlag = True    
            
            # clear the color coding for selected filter components
            self.cboRegions.setStyleSheet("");                
            self.cboCountries.setStyleSheet("");                
            self.cboStates.setStyleSheet("");                
            self.cboCounties.setStyleSheet("");                
            self.cboLocations.setStyleSheet("");                            
       
            # use the selected country to filter the masterLocationList
            # clear the subsidiary comboboxes and populat them anew with filtered locations
            thisCountry = self.cboCountries.currentText()
            self.cboStates.clear()
            self.cboCounties.clear()
            self.cboLocations.clear()
            
            # if "all countries" is chosen, fill subsidiary cbos with all locations
            # e.g., remove the country filter, if one had existed for the cbos
            if thisCountry == "**All Countries**":
                self.cboCountries.setStyleSheet("");                
                self.cboStates.addItem("**All States**")
                self.cboCounties.addItem("**All Counties**")
                self.cboLocations.addItem("**All Locations**")
                self.cboStates.addItems(MainWindow.db.stateList)
                self.cboCounties.addItems(MainWindow.db.countyList)
                self.cboLocations.addItems(MainWindow.db.locationList)
                self.cboCountries.setStyleSheet("");
            
            else:

                self.cboCountries.setStyleSheet("QComboBox { color: #4f8ef7; }")
                
                # initialize lists to store the subsidiary locations
                thisCountryStates = set()
                thisCountryCounties = set()
                thisCountryLocations = set()

                # loop through masterLocationList to find locations filtered for the chose country
                for l in MainWindow.db.masterLocationList:
                    if "countryName" in l.keys():
                    
                        if l["countryName"] == thisCountry:

                            if "stateName" in l.keys():
                                if l["stateName"] != "": thisCountryStates.add(l["stateName"])

                            if l["county"] != "": thisCountryCounties.add(l["county"])
                            if l["location"] != "": thisCountryLocations.add(l["location"])
                
                # remove duplicates using the set command, then return to list format
                thisCountryStates = list(thisCountryStates)
                thisCountryCounties = list(thisCountryCounties)
                thisCountryLocations = list(thisCountryLocations)
                
                # sort them
                thisCountryStates.sort()
                thisCountryCounties.sort()
                thisCountryLocations.sort()
                
                # add filtered locations to comboboxes
                self.cboStates.addItem("**All States**")
                self.cboStates.addItems(thisCountryStates)
                self.cboCounties.addItem("**All Counties**")
                self.cboCounties.addItems(thisCountryCounties)
                self.cboLocations.addItem("**All Locations**")
                self.cboLocations.addItems(thisCountryLocations)
            
            # we're done, so reset flag to false to allow future triggers
            self.fillingLocationComboBoxesFlag = False


    def ComboDateOptionsChanged(self):
        
        if self.fillingLocationComboBoxesFlag is False:
            
            thisOption = self.cboDateOptions.currentText()
            
            if thisOption == "No Date Filter":
                self.cboDateOptions.setStyleSheet("");  
                self.calStartDate.setStyleSheet("")
                self.calEndDate.setStyleSheet("")

            elif thisOption == "Use Calendars Below":
                self.highlightFilterElement(self.cboDateOptions)
                self.highlightFilterElement(self.calStartDate)
                self.highlightFilterElement(self.calEndDate)
                
            else:
                self.highlightFilterElement(self.cboDateOptions)
                self.unhighlightFilterElement(self.calStartDate)                
                self.unhighlightFilterElement(self.calEndDate)


    def ComboFamiliesChanged(self):
        
        if self.fillingLocationComboBoxesFlag is False:
            
            self.fillingLocationComboBoxesFlag = True
            thisFamily = self.cboFamilies.currentText()
            
            # clear any color coding for selected filter components 
            self.cboSpecies.setStyleSheet("")
            self.cboSpecies.clear()
            
            if thisFamily == "**All Families**":
                self.cboFamilies.setStyleSheet("");                
                self.cboSpecies.addItem("**All Species**")
                if self.cboOrders.currentText() == "**All Orders**":
                    speciesList = MainWindow.db.speciesDict.keys()
                    speciesList = list(speciesList)
                else:
                    speciesList = MainWindow.db.orderSpeciesDict[self.cboOrders.currentText()]
                speciesList.sort()                
                self.cboSpecies.addItems(speciesList)
                
            else:
                self.highlightFilterElement(self.cboFamilies)
                self.cboSpecies.addItem("**All Species**")
                self.cboSpecies.addItems(MainWindow.db.familySpeciesDict[thisFamily])                
            
            self.fillingLocationComboBoxesFlag = False


    def ComboLocationsChanged(self):
        
        if self.fillingLocationComboBoxesFlag is False:
            
            thisLocation = self.cboLocations.currentText()
            
            if thisLocation == "**All Locations**":
                self.unhighlightFilterElement(self.cboLocations)                
            else:
                self.highlightFilterElement(self.cboLocations)
            
            self.cboStartSeasonalRangeMonth.adjustSize()


    def ComboOrdersChanged(self):
        
        if self.fillingLocationComboBoxesFlag is False:
            
            self.fillingLocationComboBoxesFlag = True
            thisOrder = self.cboOrders.currentText()
            
            # clear any color coding for selected filter components 
            self.unhighlightFilterElement(self.cboFamilies)
            self.unhighlightFilterElement(self.cboSpecies)
            self.cboFamilies.clear()
            self.cboSpecies.clear()
            
            if thisOrder == "**All Orders**":
                self.cboOrders.setStyleSheet("");                
                self.cboFamilies.addItem("**All Families**")
                self.cboFamilies.addItems(MainWindow.db.familyList)
                self.cboSpecies.addItem("**All Species**")
                speciesList = MainWindow.db.speciesDict.keys()
                speciesList = list(speciesList)
                speciesList.sort()
                self.cboSpecies.addItems(speciesList)
                
            else:
                thisFamilies = []
                self.highlightFilterElement(self.cboOrders)
                for l in MainWindow.db.masterFamilyOrderList:
                    if l[1] == thisOrder:
                        if l[0] not in thisFamilies:
                            thisFamilies.append(l[0])
                self.cboFamilies.addItem("**All Families**")
                self.cboFamilies.addItems(thisFamilies)
                self.cboSpecies.addItem("**All Species**")
                self.cboSpecies.addItems(MainWindow.db.orderSpeciesDict[thisOrder]) 
                               
            self.fillingLocationComboBoxesFlag = False


    def textCommonNameSearchChanged(self):
        
        if self.txtCommonNameSearch.text().strip() != "":
            
            red = str(code_Stylesheet.mdiAreaColor.red())
            blue = str(code_Stylesheet.mdiAreaColor.blue())
            green = str(code_Stylesheet.mdiAreaColor.green())        
            self.txtCommonNameSearch.setStyleSheet("QLineEdit {color: white; background-color: rgb(" + red + "," + green + "," + blue + ");}")

        else:
            
            self.txtCommonNameSearch.setStyleSheet("")
            
        
    def ComboSeasonalRangeOptionsChanged(self):
        if self.fillingLocationComboBoxesFlag is False:

            thisOption = self.cboSeasonalRangeOptions.currentText()

            if thisOption == "No Seasonal Range":
                self.unhighlightFilterElement(self.cboSeasonalRangeOptions)
                self.unhighlightFilterElement(self.cboStartSeasonalRangeMonth)
                self.unhighlightFilterElement(self.cboStartSeasonalRangeDate)
                self.unhighlightFilterElement(self.cboEndSeasonalRangeMonth)
                self.unhighlightFilterElement(self.cboEndSeasonalRangeDate)

            elif thisOption == "Use Range Below":
                self.highlightFilterElement(self.cboSeasonalRangeOptions)
                self.highlightFilterElement(self.cboStartSeasonalRangeMonth)
                self.highlightFilterElement(self.cboStartSeasonalRangeDate)
                self.highlightFilterElement(self.cboEndSeasonalRangeMonth)
                self.highlightFilterElement(self.cboEndSeasonalRangeDate)

            else:
                self.highlightFilterElement(self.cboSeasonalRangeOptions)
                self.unhighlightFilterElement(self.cboStartSeasonalRangeMonth)
                self.unhighlightFilterElement(self.cboStartSeasonalRangeDate)
                self.unhighlightFilterElement(self.cboEndSeasonalRangeMonth)
                self.unhighlightFilterElement(self.cboEndSeasonalRangeDate)

                # Compute start/end month index (0=Jan) and day index (0=1st)
                # for the preset so the dropdowns reflect the active range.
                start_m = start_d = end_m = end_d = None

                if thisOption == "Spring":
                    start_m, start_d, end_m, end_d = 2, 19, 5, 18   # Mar 20 – Jun 19
                elif thisOption == "Summer":
                    start_m, start_d, end_m, end_d = 5, 19, 8, 18   # Jun 20 – Sep 19
                elif thisOption == "Fall":
                    start_m, start_d, end_m, end_d = 8, 19, 11, 18  # Sep 20 – Dec 19
                elif thisOption == "Winter":
                    start_m, start_d, end_m, end_d = 11, 19, 2, 18  # Dec 20 – Mar 19
                elif thisOption == "This Month":
                    now = datetime.datetime.now()
                    m = now.month - 1
                    last = int(MainWindow.db.GetLastDayOfMonth(str(now.month).zfill(2)))
                    start_m, start_d, end_m, end_d = m, 0, m, last - 1
                elif thisOption == "Year to Date":
                    now = datetime.datetime.now()
                    start_m, start_d = 0, 0
                    end_m, end_d = now.month - 1, now.day - 1
                elif thisOption == "Remainder of Year":
                    now = datetime.datetime.now()
                    start_m, start_d = now.month - 1, now.day - 1
                    end_m, end_d = 11, 30  # Dec 31
                else:
                    monthList = ["January", "February", "March", "April", "May", "June",
                                 "July", "August", "September", "October", "November", "December"]
                    if thisOption in monthList:
                        m = monthList.index(thisOption)
                        last = int(MainWindow.db.GetLastDayOfMonth(str(m + 1).zfill(2)))
                        start_m, start_d, end_m, end_d = m, 0, m, last - 1

                if start_m is not None:
                    for combo, idx in (
                        (self.cboStartSeasonalRangeMonth, start_m),
                        (self.cboStartSeasonalRangeDate,  start_d),
                        (self.cboEndSeasonalRangeMonth,   end_m),
                        (self.cboEndSeasonalRangeDate,    end_d),
                    ):
                        combo.blockSignals(True)
                        combo.setCurrentIndex(idx)
                        combo.blockSignals(False)


    def ComboSpeciesChanged(self):
        if self.fillingLocationComboBoxesFlag is False:
            
            thisSpecies = self.cboSpecies.currentText()
            
            if thisSpecies == "**All Species**":
                self.unhighlightFilterElement(self.cboSpecies)                
            else:
                self.highlightFilterElement(self.cboSpecies)

                     
    def ComboStatesChanged(self):
        if self.fillingLocationComboBoxesFlag is False:        
            self.fillingLocationComboBoxesFlag = True
            
            # clear any color coding for selected filter components
            self.unhighlightFilterElement(self.cboCounties)
            self.unhighlightFilterElement(self.cboLocations)
            
            thisState = MainWindow.db.GetStateCode(self.cboStates.currentText())
            self.cboCounties.clear()
            self.cboLocations.clear()
            if thisState == "**All States**":
                self.unhighlightFilterElement(self.cboStates)
                self.cboCounties.addItem("**All Counties**")
                self.cboLocations.addItem("**All Locations**")
                self.cboCounties.addItems(MainWindow.db.countyList)
                self.cboLocations.addItems(MainWindow.db.locationList)
            else:
                self.highlightFilterElement(self.cboStates)                
                thisStateCounties = set()
                thisStateLocations = set()
                for l in MainWindow.db.masterLocationList:
                    if l["stateCode"] == thisState:
                        if l["county"] != "": thisStateCounties.add(l["county"])
                        if l["location"] != "": thisStateLocations.add(l["location"])
                
                thisStateCounties = list(thisStateCounties)
                thisStateLocations = list(thisStateLocations)
                
                thisStateCounties.sort()
                thisStateLocations.sort()
                
                self.cboCounties.addItem("**All Counties**")
                self.cboCounties.addItems(thisStateCounties)
                self.cboLocations.addItem("**All Locations**")
                self.cboLocations.addItems(thisStateLocations)  
            self.fillingLocationComboBoxesFlag = False
           
            
    def ComboCountiesChanged(self):
        if self.fillingLocationComboBoxesFlag is False:
            self.fillingLocationComboBoxesFlag = True
            thisCounty = self.cboCounties.currentText()
            
            # clear any color coding for selected filter components 
            self.cboLocations.setStyleSheet("");          
            
            self.cboLocations.clear()
            if thisCounty == "**All Counties**":
                self.unhighlightFilterElement(self.cboCounties)     
                self.cboLocations.addItem("**All Locations**")
                self.cboLocations.addItems(MainWindow.db.locationList)
            else:
                self.highlightFilterElement(self.cboCounties)
                thisCountyLocations = set()
                for l in MainWindow.db.masterLocationList:
                    if l["county"] == thisCounty:
                        if l["location"] != "": thisCountyLocations.add(l["location"])
                thisCountyLocations = list(thisCountyLocations)
                thisCountyLocations.sort()
                self.cboLocations.addItem("**All Locations**")
                self.cboLocations.addItems(thisCountyLocations)
            self.fillingLocationComboBoxesFlag = False


    def ComboStartRatingRangeChanged(self):
            
            thisSighting = self.cboStartRatingRange.currentText()
            
            startRating = self.cboStartRatingRange.currentIndex()
            endRating = self.cboEndRatingRange.currentIndex()
            
            if startRating > endRating:
                if endRating == 0:
                    self.cboEndRatingRange.setCurrentIndex(6)
                else:
                    self.cboEndRatingRange.setCurrentIndex(startRating)
            
            if thisSighting == "**All**":
                self.unhighlightFilterElement(self.cboStartRatingRange)                
            else:
                self.highlightFilterElement(self.cboStartRatingRange)


    def ComboEndRatingRangeChanged(self):
            
            thisSighting = self.cboEndRatingRange.currentText()
            
            startRating = self.cboStartRatingRange.currentIndex()
            endRating = self.cboEndRatingRange.currentIndex()
            
            if startRating > endRating:
                self.cboStartRatingRange.setCurrentIndex(endRating)            
            
            if thisSighting == "**All**":
                self.unhighlightFilterElement(self.cboEndRatingRange)                
            else:
                self.highlightFilterElement(self.cboEndRatingRange)


    def ComboSpeciesHasPhotosChanged(self):
            
            thisSpecies = self.cboSpeciesHasPhoto.currentText()
            
            if thisSpecies == "**All**":
                self.unhighlightFilterElement(self.cboSpeciesHasPhoto)                
            else:
                self.highlightFilterElement(self.cboSpeciesHasPhoto)
                

    def ComboCameraChanged(self):
            
            thisCamera = self.cboCamera.currentText()
            
            if thisCamera == "**All Cameras**":
                self.unhighlightFilterElement(self.cboCamera)                
            else:
                self.highlightFilterElement(self.cboCamera)


    def ComboLensChanged(self):
            
            thisLens = self.cboLens.currentText()
            
            if thisLens== "**All Lenses**":
                self.unhighlightFilterElement(self.cboLens)                
            else:
                self.highlightFilterElement(self.cboLens)


    def ComboStartShutterSpeedChanged(self):
            
            thisShutterSpeed = self.cboStartShutterSpeedRange.currentText()
            
            if thisShutterSpeed == "**All**":
                self.unhighlightFilterElement(self.cboStartShutterSpeedRange)                
            else:
                self.highlightFilterElement(self.cboStartShutterSpeedRange)
                

    def ComboEndShutterSpeedChanged(self):
            
            thisShutterSpeed = self.cboEndShutterSpeedRange.currentText()
            
            if thisShutterSpeed == "**All**":
                self.unhighlightFilterElement(self.cboEndShutterSpeedRange)                
            else:
                self.highlightFilterElement(self.cboEndShutterSpeedRange)


    def ComboStartApertureChanged(self):
            
            thisAperture = self.cboStartApertureRange.currentText()
            
            if thisAperture == "**All**":
                self.unhighlightFilterElement(self.cboStartApertureRange)                
            else:
                self.highlightFilterElement(self.cboStartApertureRange)
                

    def ComboEndApertureChanged(self):
            
            thisAperture = self.cboEndApertureRange.currentText()
            
            if thisAperture == "**All**":
                self.unhighlightFilterElement(self.cboEndApertureRange)                
            else:
                self.highlightFilterElement(self.cboEndApertureRange)
                

    def ComboStartFocalLengthChanged(self):
            
            thisFocalLength = self.cboStartFocalLengthRange.currentText()
            
            if thisFocalLength == "**All**":
                self.unhighlightFilterElement(self.cboStartFocalLengthRange)                
            else:
                self.highlightFilterElement(self.cboStartFocalLengthRange)
                

    def ComboEndFocalLengthChanged(self):
            
            thisFocalLength = self.cboEndFocalLengthRange.currentText()
            
            if thisFocalLength == "**All**":
                self.unhighlightFilterElement(self.cboEndFocalLengthRange)                
            else:
                self.highlightFilterElement(self.cboEndFocalLengthRange)


    def ComboStartIsoChanged(self):
            
            thisIso = self.cboStartIsoRange.currentText()
            
            if thisIso == "**All**":
                self.unhighlightFilterElement(self.cboStartIsoRange)                
            else:
                self.highlightFilterElement(self.cboStartIsoRange)
                

    def ComboEndIsoChanged(self):
            
            thisIso = self.cboEndIsoRange.currentText()
            
            if thisIso == "**All**":
                self.unhighlightFilterElement(self.cboEndIsoRange)                
            else:
                self.highlightFilterElement(self.cboEndIsoRange)


    def createChoroplethUSStates(self):
        
        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        filter = self.GetFilter()
        # create new Location Totals child window        
        sub = code_Web.Web()

        # save the MDI window as the parent for future use in the child        
        sub.mdiParent = self        

        # call the child's routine to fill it with data        
        if sub.loadChoroplethUSStates(filter) is True:
            
            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()

        else:
            # abort if filter found no sightings for map
            self.CreateMessageNoResults()
            sub.close()
            
        QApplication.restoreOverrideCursor() 
        

    def createChoroplethGBCounties(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        filter = self.GetFilter()
        sub = code_Web.Web()
        sub.mdiParent = self

        if sub.loadChoroplethGBCounties(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()


    def createChoroplethIndiaStates(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        filter = self.GetFilter()
        sub = code_Web.Web()
        sub.mdiParent = self

        if sub.loadChoroplethIndiaStates(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()


    def createChoroplethCanadaProvinces(self):

        # if no data file is currently open, abort
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        filter = self.GetFilter()
        sub = code_Web.Web()
        sub.mdiParent = self

        if sub.loadChoroplethCanadaProvinces(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()


    def createChoroplethUSCounties(self):
                
        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        filter = self.GetFilter()
        # create new Location Totals child window        
        sub = code_Web.Web()

        # save the MDI window as the parent for future use in the child        
        sub.mdiParent = self        

        # call the child's routine to fill it with data        
        if sub.loadChoroplethUSCounties(filter) is True:
            
            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()

        else:
            # abort if filter found no sightings for map
            self.CreateMessageNoResults()
            sub.close()
            
        QApplication.restoreOverrideCursor()         
        
    
    def createChoroplethWorldCountries(self):

        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        filter = self.GetFilter()
        # create new Location Totals child window        
        sub = code_Web.Web()

        # save the MDI window as the parent for future use in the child        
        sub.mdiParent = self        

        # call the child's routine to fill it with data        
        if sub.loadChoroplethWorldCountries(filter) is True:

            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()

        else:
            # abort if filter found no sightings for map
            self.CreateMessageNoResults()
            sub.close()

        QApplication.restoreOverrideCursor()


    def createChoroplethUSStatesChecklists(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        filter = self.GetFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadChoroplethUSStates(filter, mode='checklists') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()
        QApplication.restoreOverrideCursor()


    def createChoroplethUSCountiesChecklists(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        filter = self.GetFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadChoroplethUSCounties(filter, mode='checklists') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()
        QApplication.restoreOverrideCursor()


    def createChoroplethCanadaProvincesChecklists(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        filter = self.GetFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadChoroplethCanadaProvinces(filter, mode='checklists') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()
        QApplication.restoreOverrideCursor()


    def createChoroplethIndiaStatesChecklists(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        filter = self.GetFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadChoroplethIndiaStates(filter, mode='checklists') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()
        QApplication.restoreOverrideCursor()


    def createChoroplethGBCountiesChecklists(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        filter = self.GetFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadChoroplethGBCounties(filter, mode='checklists') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()
        QApplication.restoreOverrideCursor()


    def createChoroplethWorldCountriesChecklists(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        filter = self.GetFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadChoroplethWorldCountries(filter, mode='checklists') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()
        QApplication.restoreOverrideCursor()


    def createGeolocatedPhotosMap(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        filter = self.GetFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadGeolocatedPhotosMap(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()
        QApplication.restoreOverrideCursor()


    def createLifeListMap(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        filter = self.GetFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadLifeListMap(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()
        QApplication.restoreOverrideCursor()


    def createEffortMap(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        filter = self.GetFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadEffortMap(filter, mode='time') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()
        QApplication.restoreOverrideCursor()

    def createEffortMapByChecklists(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        filter = self.GetFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadEffortMap(filter, mode='checklists') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()
        QApplication.restoreOverrideCursor()


    def createSpeciesTotalMap(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        filter = self.GetFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadBubbleMap(filter, mode='species') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()
        QApplication.restoreOverrideCursor()

    def createIndividualsTotalMap(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        filter = self.GetFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadBubbleMap(filter, mode='individuals') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()
        QApplication.restoreOverrideCursor()

    def createChoroplethWorldSubregion1(self):
        
        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        filter = self.GetFilter()
        # create new Location Totals child window        
        sub = code_Web.Web()

        # save the MDI window as the parent for future use in the child        
        sub.mdiParent = self        

        # call the child's routine to fill it with data        
        if sub.loadChoroplethWorldSubregion1(filter) is True:
            
            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()

        else:
            # abort if filter found no sightings for map
            self.CreateMessageNoResults()
            sub.close()
            
        QApplication.restoreOverrideCursor()         



    def highlightFilterElement(self, widget):

        if widget.objectName()[0:3] == "cbo":
            widget.setStyleSheet("QComboBox { color: #4f8ef7; }")

        if widget.objectName()[0:3] == "cal":
            red = str(code_Stylesheet.mdiAreaColor.red())
            blue = str(code_Stylesheet.mdiAreaColor.blue())
            green = str(code_Stylesheet.mdiAreaColor.green())
            widget.setStyleSheet("QDateTimeEdit { background-color: rgb(" + red + "," + green + "," + blue + ")}")


    def unhighlightFilterElement(self, widget):
        
        widget.setStyleSheet("")

 
                
    def closeEvent(self, event):
        # Remove the custom toolbar style before Qt teardown so PySide6's shutdown
        # sequence cannot call back into a partially-destroyed Python proxy style object.
        self.toolBar.setStyle(None)
        event.accept()

    def ExitApp(self):

        self.checkIfPhotoDataNeedSaving()
        self.toolBar.setStyle(None)
        sys.exit()
        
