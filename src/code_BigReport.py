# import project files
import form_BigReport
import code_Filter
import code_Location
import code_Individual
import code_Lists
import code_Stylesheet

# import basic Python libraries
from copy import deepcopy
from collections import defaultdict
from math import floor
import base64

from PySide6.QtGui import (
    QCursor,
    QFont,
    QFontMetrics,
    )

from PySide6.QtCore import (
    Qt,
    QUrl,
    QFile,
    Signal,
    Slot,
    QObject,
    QIODevice,
    QByteArray,
    QBuffer
    )

from PySide6.QtWebChannel import QWebChannel

from PySide6.QtWidgets import (
    QApplication,
    QTableWidgetItem,
    QHeaderView,
    QMdiSubWindow,
    )

from PySide6.QtWebEngineWidgets import (
    QWebEngineView,
)

from PySide6.QtWebEngineCore import (
    QWebEngineSettings,
    QWebEngineProfile,
)


class BigReportMapBridge(QObject):
    """Qt/JavaScript bridge for the Big Report map tab.

    Registered on the page's QWebChannel as 'bridge'.  Clicking a location
    dot calls locationClicked(name) which opens the Location child window.
    """

    def __init__(self, big_report):
        super().__init__()
        self._br = big_report

    @Slot(str)
    def locationClicked(self, locationName):
        sub = code_Location.Location()
        sub.mdiParent = self._br.mdiParent
        sub.FillLocation(locationName)
        self._br.mdiParent.mdiArea.addSubWindow(sub)
        self._br.mdiParent.PositionChildWindow(sub, self._br)
        sub.show()
        QApplication.processEvents()
        sub.scaleMe()


class BigReport(QMdiSubWindow, form_BigReport.Ui_frmBigReport):

    # create "resized" as a signal that the window can emit
    # we respond to this signal with the form's resizeMe method below
    resized = Signal()  
    
    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        
        self.setAttribute(Qt.WA_DeleteOnClose,True)
        
        self.mdiParent = ""
        self.myHtml = ""
        self.resized.connect(self.resizeMe)                
        self.lstDates.currentRowChanged.connect(self.FillSpeciesForDate)
        self.lstLocations.currentRowChanged.connect(self.FillSpeciesForLocation)
        self.lstLocations.doubleClicked.connect(lambda: self.CreateLocation(self.lstLocations))
        self.tblNewLocationSpecies.itemDoubleClicked.connect(lambda: self.CreateLocation(self.tblNewLocationSpecies))        
        self.lstDates.doubleClicked.connect(lambda: self.CreateSpeciesList(self.lstDates))
        self.lstSpecies.doubleClicked.connect(lambda: self.CreateIndividual(self.lstSpecies))
        self.lstLocationSpecies.doubleClicked.connect(lambda: self.CreateIndividual(self.lstLocationSpecies))
        self.lstLocationUniqueSpecies.doubleClicked.connect(lambda: self.CreateIndividual(self.lstLocationUniqueSpecies))
        self.lstNewLifeSpecies.doubleClicked.connect(lambda: self.CreateIndividual(self.lstNewLifeSpecies))
        self.tblNewYearSpecies.doubleClicked.connect(lambda: self.CreateIndividual(self.tblNewYearSpecies))
        self.tblNewMonthSpecies.doubleClicked.connect(lambda: self.CreateIndividual(self.tblNewMonthSpecies))
        self.tblNewCountrySpecies.doubleClicked.connect(lambda: self.CreateIndividual(self.tblNewCountrySpecies))
        self.tblNewStateSpecies.doubleClicked.connect(lambda: self.CreateIndividual(self.tblNewStateSpecies))
        self.tblNewCountySpecies.doubleClicked.connect(lambda: self.CreateIndividual(self.tblNewCountySpecies))
        self.tblNewLocationSpecies.doubleClicked.connect(lambda: self.CreateIndividual(self.tblNewLocationSpecies))
        self.tblSpecies.doubleClicked.connect(self.TblSpeciesClicked)
        
        # right-click menu actions to widgets as appropriate
        self.tblSpecies.addAction(self.actionSetSpeciesFilter)
        self.tblSpecies.addAction(self.actionSetFirstDateFilter)
        self.tblSpecies.addAction(self.actionSetLastDateFilter)
        self.lstLocations.addAction(self.actionSetLocationFilter)
        self.lstDates.addAction(self.actionSetDateFilter)
        self.lstSpecies.addAction(self.actionSetSpeciesFilter)        
        self.lstLocationSpecies.addAction(self.actionSetSpeciesFilter)
        self.lstLocationUniqueSpecies.addAction(self.actionSetSpeciesFilter)
        self.lstNewLifeSpecies.addAction(self.actionSetSpeciesFilter)
        self.tblNewYearSpecies.addAction(self.actionSetSpeciesFilter)
        self.tblNewYearSpecies.addAction(self.actionSetDateFilterToYear)
        self.tblNewMonthSpecies.addAction(self.actionSetSpeciesFilter)
        self.tblNewMonthSpecies.addAction(self.actionSetDateFilterToMonth)
        self.tblNewCountrySpecies.addAction(self.actionSetSpeciesFilter)
        self.tblNewCountrySpecies.addAction(self.actionSetLocationFilter)
        self.tblNewStateSpecies.addAction(self.actionSetSpeciesFilter)
        self.tblNewStateSpecies.addAction(self.actionSetLocationFilter)
        self.tblNewCountySpecies.addAction(self.actionSetSpeciesFilter)
        self.tblNewCountySpecies.addAction(self.actionSetLocationFilter)
        self.tblNewLocationSpecies.addAction(self.actionSetSpeciesFilter)
        self.tblNewLocationSpecies.addAction(self.actionSetLocationFilter)
        
        # connect right-click actions to methods
        self.actionSetDateFilter.triggered.connect(self.setDateFilter)
        self.actionSetFirstDateFilter.triggered.connect(self.setFirstDateFilter)
        self.actionSetLastDateFilter.triggered.connect(self.setLastDateFilter)
        self.actionSetSpeciesFilter.triggered.connect(self.setSpeciesFilter)
        self.actionSetCountryFilter.triggered.connect(self.setLocationFilter)
        self.actionSetStateFilter.triggered.connect(self.setLocationFilter)
        self.actionSetCountyFilter.triggered.connect(self.setLocationFilter)
        self.actionSetLocationFilter.triggered.connect(self.setLocationFilter)       
        self.actionSetDateFilterToYear.triggered.connect(self.setDateFilter)
        self.actionSetDateFilterToMonth.triggered.connect(self.setDateFilter)

        self.webMap = QWebEngineView(self.tabMap)
        self.webMap.setUrl(QUrl("about:blank"))
        self.webMap.setObjectName("webMap")
        
        self.tabAnalysis.setCurrentIndex(0)
        self.speciesList = []
        self.filter = code_Filter.Filter()
        self.filteredSightingList = []
        self.sightingListForSpeciesSubset = None
        self.newDatesLoaded = False
        self.newRegionsLoaded = False
        self.newLocationsLoaded = False
        self.tabAnalysis.currentChanged.connect(self.onTabChanged)
        
        
    def CreateLocation(self,  callingWidget):
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        if callingWidget.objectName() == "lstLocations":
            locationName = callingWidget.currentItem().text()
        if callingWidget.objectName() == "tblNewLocationSpecies":
            if callingWidget.currentColumn() != 0:
                QApplication.restoreOverrideCursor()
                return
            locationName = callingWidget.item(callingWidget.currentRow(),  0).text()
        sub = code_Location.Location()
        sub.mdiParent = self.mdiParent
        sub.FillLocation(locationName)
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow( sub, self)
        sub.show()
        QApplication.processEvents()
        sub.scaleMe()
        QApplication.restoreOverrideCursor()
    
    
    def CreateIndividual(self,  callingWidget):
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        if callingWidget.objectName() in (["lstSpecies", 
                                                                            "lstLocationSpecies", 
                                                                            "lstLocationUniqueSpecies", 
                                                                            "lstNewLifeSpecies"
                                                                            ]):
            species = callingWidget.currentItem().text()
        if callingWidget.objectName() in (["tblNewYearSpecies", 
                                                                            "tblNewMonthSpecies", 
                                                                            "tblNewCountrySpecies", 
                                                                            "tblNewStateSpecies", 
                                                                            "tblNewCountySpecies", 
                                                                            "tblNewLocationSpecies"
                                                                            ]):
            if callingWidget.currentColumn() != 1:
                QApplication.restoreOverrideCursor()
                return
            species = callingWidget.item(callingWidget.currentRow(),  1).text()
        sub = code_Individual.Individual()
        sub.mdiParent = self.mdiParent
        sub.FillIndividual(species)
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow( sub, self)        
        sub.show() 
        sub.resizeMe()
        QApplication.restoreOverrideCursor()     
    
    
    def CreateSpeciesList(self,  callingWidget):
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        if callingWidget.objectName() == "lstDates":
            date = callingWidget.currentItem().text()
        
        filter = code_Filter.Filter()
        filter.setStartDate(date)
        filter.setEndDate(date)
        
        sub = code_Lists.Lists()
        sub.mdiParent = self.mdiParent
        sub.FillSpecies(filter)
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow( sub, self)
        sub.show()
        sub.scaleMe()
        QApplication.restoreOverrideCursor()


    def FillAnalysisReport(self, filter):
        # save filter for later use
        self.filter = filter
        
        # set up a bold font to use in columns as needed
        font = QFont()
        font.setBold(True)         
        
        # create subset of master sightings list for this filter
        self.filteredSightingList = deepcopy(self.mdiParent.db.GetSightings(filter))
        filteredSightingList = self.filteredSightingList
        
        # ****Setup Species page****
        # get species and first/last date data from db 
        speciesListWithDates = self.mdiParent.db.GetSpeciesWithData(filter,  self.filteredSightingList,  "Subspecies")
       
        # abort if filter produced no sightings
        if len(speciesListWithDates) == 0:
            return(False)
       
        # set up tblSpecies column headers and widths
        self.tblSpecies.setColumnCount(5)
        self.tblSpecies.setRowCount(len(speciesListWithDates))
        self.tblSpecies.horizontalHeader().setVisible(True)
        self.tblSpecies.setHorizontalHeaderLabels(['Tax', 'Species', 'Count', 'First',  'Last'])
        header = self.tblSpecies.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tblSpecies.setShowGrid(False)

        # add species and dates to table row by row        
        R = 0
        for species in speciesListWithDates:    
            taxItem = QTableWidgetItem()
            taxItem.setData(Qt.DisplayRole, R+1)
            speciesItem = QTableWidgetItem()
            speciesItem.setText(species[0])
            speciesItem.setData(Qt.UserRole,  species[4]) 
            countItem = QTableWidgetItem()
            countItem.setData(Qt.DisplayRole, species[7])
            firstDateItem = QTableWidgetItem()
            firstDateItem.setData(Qt.DisplayRole, species[1])
            lastDateItem = QTableWidgetItem()
            lastDateItem.setData(Qt.DisplayRole, species[2])
            self.tblSpecies.setItem(R, 0, taxItem)    
            self.tblSpecies.setItem(R, 1, speciesItem)
            self.tblSpecies.setItem(R, 2, countItem)
            self.tblSpecies.setItem(R, 3, firstDateItem)
            self.tblSpecies.setItem(R, 4, lastDateItem)
            
            # set the species column to bold font (set up above)
            self.tblSpecies.item(R, 1).setFont(font)

            # color code the entry. Stylesheet color for full species, gray if not
            # set the species to gray if it's not a true species
            if " x " in species[0] or "sp." in species[0] or "/" in species[0]:
                self.tblSpecies.item(R, 1).setForeground(Qt.gray)
            else:
                self.tblSpecies.item(R, 1).setForeground(code_Stylesheet.speciesColor)            
            
            self.speciesList.append(species[4])
            
            R = R + 1

        # ****Setup Dates page****
        listDates = self.mdiParent.db.GetDates(filter,  filteredSightingList)
        self.lstDates.addItems(listDates)
        self.lstDates.setSpacing(2)
        if len(listDates) > 0:
            self.lstDates.setCurrentRow(0)
            self.FillSpeciesForDate()
            
        self.lblDatesSeen.setText("Dates: " + str(len(listDates)))

        # ****Setup Locations page****
        listLocations = self.mdiParent.db.GetLocations(filter, "OnlyLocations",   filteredSightingList)
        for l in listLocations:
            self.lstLocations.addItem(l)
        self.lstLocations.setSpacing(2)
        if len(listLocations) > 0:
            self.lstLocations.setCurrentRow(0)
            self.FillSpeciesForLocation()
                                
            self.lblLocations.setText("Locations: " + str(len(listLocations)))
            self.lblLocationsVisited.setText("Locations: " + str(len(listLocations)))

        # ****Setup window's main labels****
        # set main species seen label text
        count = self.mdiParent.db.CountSpecies(self.speciesList)
        nonSpeciesTaxaCount = self.tblSpecies.rowCount() - count
        
        labelText = "Species: " + str(count)
        
        if nonSpeciesTaxaCount > 0:
            labelText = labelText +  " + " + str(nonSpeciesTaxaCount) + " taxa"
        
        self.lblTopSpeciesSeen.setText(labelText)
        
        # set main location label, using "All Locations" if none others are selected
        self.mdiParent.SetChildDetailsLabels(self, filter)

        self.setWindowTitle(self.filter.buildWindowTitle("Big Report", self.mdiParent.db, count=count, countUnit="Species"))

        if self.lblDetails.text() != "":
            self.lblDetails.setVisible(True)
        else:
            self.lblDetails.setVisible(False)

        self.resizeMe()
        self.scaleMe()

        return(True)


    def onTabChanged(self, index):
        tabIndex = self.tabAnalysis.indexOf
        if index == tabIndex(self.tabNewDates) and not self.newDatesLoaded:
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            self._fillNewDates()
            self.newDatesLoaded = True
            QApplication.restoreOverrideCursor()
        elif index == tabIndex(self.tabNewRegions) and not self.newRegionsLoaded:
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            self._fillNewRegions()
            self.newRegionsLoaded = True
            QApplication.restoreOverrideCursor()
        elif index == tabIndex(self.tabNewLocations) and not self.newLocationsLoaded:
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            self._fillNewLocations()
            self.newLocationsLoaded = True
            QApplication.restoreOverrideCursor()


    def _ensureSpeciesSubsetSightings(self):
        if self.sightingListForSpeciesSubset is None:
            speciesListFilter = code_Filter.Filter()
            speciesListFilter.setSpeciesList(self.speciesList)
            self.sightingListForSpeciesSubset = self.mdiParent.db.GetSightings(speciesListFilter)


    def _fillNewDates(self):
        self._ensureSpeciesSubsetSightings()
        font = QFont()
        font.setBold(True)
        filteredSightingList = self.filteredSightingList
        sightingListForSpeciesSubset = self.sightingListForSpeciesSubset

        yearSpecies = self.mdiParent.db.GetNewYearSpecies(self.filter, filteredSightingList, sightingListForSpeciesSubset)
        lifeSpecies = self.mdiParent.db.GetNewLifeSpecies(self.filter, filteredSightingList, sightingListForSpeciesSubset)
        monthSpecies = self.mdiParent.db.GetNewMonthSpecies(self.filter, filteredSightingList, sightingListForSpeciesSubset)

        self.tblNewYearSpecies.setColumnCount(2)
        self.tblNewYearSpecies.setRowCount(len(yearSpecies) + 1)
        self.tblNewYearSpecies.horizontalHeader().setVisible(False)
        self.tblNewYearSpecies.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tblNewYearSpecies.setShowGrid(False)
        count = 0
        nonSpeciesTaxaCount = 0
        for R, ys in enumerate(yearSpecies):
            yearItem = QTableWidgetItem(ys[0])
            newYearSpeciesItem = QTableWidgetItem(ys[1])
            self.tblNewYearSpecies.setItem(R, 0, yearItem)
            self.tblNewYearSpecies.setItem(R, 1, newYearSpeciesItem)
            self.tblNewYearSpecies.item(R, 1).setFont(font)
            if " x " in ys[1] or "sp." in ys[1] or "/" in ys[1]:
                self.tblNewYearSpecies.item(R, 1).setForeground(Qt.gray)
                nonSpeciesTaxaCount += 1
            else:
                self.tblNewYearSpecies.item(R, 1).setForeground(code_Stylesheet.speciesColor)
                count += 1
        labelText = "New year species: " + str(count)
        if nonSpeciesTaxaCount > 0:
            labelText += " + " + str(nonSpeciesTaxaCount) + " other taxa"
        self.lblNewYearSpecies.setText(labelText)

        self.tblNewMonthSpecies.setColumnCount(2)
        self.tblNewMonthSpecies.setRowCount(len(monthSpecies) + 1)
        self.tblNewMonthSpecies.horizontalHeader().setVisible(False)
        self.tblNewMonthSpecies.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tblNewMonthSpecies.setShowGrid(False)
        count = 0
        nonSpeciesTaxaCount = 0
        for R, ms in enumerate(monthSpecies):
            monthItem = QTableWidgetItem(ms[0])
            newMonthSpeciesItem = QTableWidgetItem(ms[1])
            self.tblNewMonthSpecies.setItem(R, 0, monthItem)
            self.tblNewMonthSpecies.setItem(R, 1, newMonthSpeciesItem)
            self.tblNewMonthSpecies.item(R, 1).setFont(font)
            if " x " in ms[1] or "sp." in ms[1] or "/" in ms[1]:
                self.tblNewMonthSpecies.item(R, 1).setForeground(Qt.gray)
                nonSpeciesTaxaCount += 1
            else:
                self.tblNewMonthSpecies.item(R, 1).setForeground(code_Stylesheet.speciesColor)
                count += 1
        labelText = "New month species: " + str(count)
        if nonSpeciesTaxaCount > 0:
            labelText += " + " + str(nonSpeciesTaxaCount) + " other taxa"
        self.lblNewMonthSpecies.setText(labelText)

        for R, ls in enumerate(lifeSpecies):
            self.lstNewLifeSpecies.addItem(ls)
            self.lstNewLifeSpecies.item(R).setFont(font)
            if "/" in ls or "sp." in ls or " x " in ls:
                self.lstNewLifeSpecies.item(R).setForeground(Qt.gray)
            else:
                self.lstNewLifeSpecies.item(R).setForeground(code_Stylesheet.speciesColor)
        if lifeSpecies:
            self.lstNewLifeSpecies.setSpacing(2)
        count = self.mdiParent.db.CountSpecies(lifeSpecies)
        nonSpeciesTaxaCount = len(lifeSpecies) - count
        labelText = "New life species: " + str(count)
        if nonSpeciesTaxaCount > 0:
            labelText += " + " + str(nonSpeciesTaxaCount) + " other taxa"
        self.lblNewLifeSpecies.setText(labelText)


    def _fillNewRegions(self):
        self._ensureSpeciesSubsetSightings()
        font = QFont()
        font.setBold(True)
        filteredSightingList = self.filteredSightingList
        sightingListForSpeciesSubset = self.sightingListForSpeciesSubset

        countrySpecies = self.mdiParent.db.GetNewCountrySpecies(self.filter, filteredSightingList, sightingListForSpeciesSubset, self.speciesList)
        stateSpecies = self.mdiParent.db.GetNewStateSpecies(self.filter, filteredSightingList, sightingListForSpeciesSubset, self.speciesList)
        countySpecies = self.mdiParent.db.GetNewCountySpecies(self.filter, filteredSightingList, sightingListForSpeciesSubset, self.speciesList)

        self.tblNewCountrySpecies.setColumnCount(2)
        self.tblNewCountrySpecies.setRowCount(len(countrySpecies))
        self.tblNewCountrySpecies.horizontalHeader().setVisible(False)
        self.tblNewCountrySpecies.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tblNewCountrySpecies.setShowGrid(False)
        count = 0
        nonSpeciesTaxaCount = 0
        for R, cs in enumerate(countrySpecies):
            countryItem = QTableWidgetItem(self.mdiParent.db.GetCountryName(cs[0]))
            newCountrySpeciesItem = QTableWidgetItem(cs[1])
            self.tblNewCountrySpecies.setItem(R, 0, countryItem)
            self.tblNewCountrySpecies.setItem(R, 1, newCountrySpeciesItem)
            self.tblNewCountrySpecies.item(R, 1).setFont(font)
            if " x " in cs[1] or "sp." in cs[1] or "/" in cs[1]:
                self.tblNewCountrySpecies.item(R, 1).setForeground(Qt.gray)
                nonSpeciesTaxaCount += 1
            else:
                self.tblNewCountrySpecies.item(R, 1).setForeground(code_Stylesheet.speciesColor)
                count += 1
        labelText = "New country species: " + str(count)
        if nonSpeciesTaxaCount > 0:
            labelText += " + " + str(nonSpeciesTaxaCount) + " taxa"
        self.lblNewCountrySpecies.setText(labelText)

        self.tblNewStateSpecies.setColumnCount(2)
        self.tblNewStateSpecies.setRowCount(len(stateSpecies))
        self.tblNewStateSpecies.horizontalHeader().setVisible(False)
        self.tblNewStateSpecies.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tblNewStateSpecies.setShowGrid(False)
        count = 0
        nonSpeciesTaxaCount = 0
        for R, ss in enumerate(stateSpecies):
            stateItem = QTableWidgetItem(self.mdiParent.db.GetStateName(ss[0]))
            newStateSpeciesItem = QTableWidgetItem(ss[1])
            self.tblNewStateSpecies.setItem(R, 0, stateItem)
            self.tblNewStateSpecies.setItem(R, 1, newStateSpeciesItem)
            self.tblNewStateSpecies.item(R, 1).setFont(font)
            if " x " in ss[1] or "sp." in ss[1] or "/" in ss[1]:
                self.tblNewStateSpecies.item(R, 1).setForeground(Qt.gray)
                nonSpeciesTaxaCount += 1
            else:
                self.tblNewStateSpecies.item(R, 1).setForeground(code_Stylesheet.speciesColor)
                count += 1
        labelText = "New state species: " + str(count)
        if nonSpeciesTaxaCount > 0:
            labelText += " + " + str(nonSpeciesTaxaCount) + " taxa"
        self.lblNewStateSpecies.setText(labelText)
        self.tblNewStateSpecies.sortByColumn(0, Qt.AscendingOrder)

        self.tblNewCountySpecies.setColumnCount(2)
        self.tblNewCountySpecies.setRowCount(len(countySpecies))
        self.tblNewCountySpecies.horizontalHeader().setVisible(False)
        self.tblNewCountySpecies.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tblNewCountySpecies.setShowGrid(False)
        count = 0
        nonSpeciesTaxaCount = 0
        for R, cs in enumerate(countySpecies):
            countyItem = QTableWidgetItem(cs[0])
            newCountySpeciesItem = QTableWidgetItem(cs[1])
            self.tblNewCountySpecies.setItem(R, 0, countyItem)
            self.tblNewCountySpecies.setItem(R, 1, newCountySpeciesItem)
            self.tblNewCountySpecies.item(R, 1).setFont(font)
            if " x " in cs[1] or "sp." in cs[1] or "/" in cs[1]:
                self.tblNewCountySpecies.item(R, 1).setForeground(Qt.gray)
                nonSpeciesTaxaCount += 1
            else:
                self.tblNewCountySpecies.item(R, 1).setForeground(code_Stylesheet.speciesColor)
                count += 1
        labelText = "New county species: " + str(count)
        if nonSpeciesTaxaCount > 0:
            labelText += " + " + str(nonSpeciesTaxaCount) + " taxa"
        self.lblNewCountySpecies.setText(labelText)


    def _fillNewLocations(self):
        self._ensureSpeciesSubsetSightings()
        font = QFont()
        font.setBold(True)
        filteredSightingList = self.filteredSightingList
        sightingListForSpeciesSubset = self.sightingListForSpeciesSubset

        locationSpecies = self.mdiParent.db.GetNewLocationSpecies(self.filter, filteredSightingList, sightingListForSpeciesSubset, self.speciesList)

        self.tblNewLocationSpecies.setColumnCount(2)
        self.tblNewLocationSpecies.setRowCount(len(locationSpecies))
        self.tblNewLocationSpecies.horizontalHeader().setVisible(False)
        self.tblNewLocationSpecies.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tblNewLocationSpecies.setShowGrid(False)
        count = 0
        nonSpeciesTaxaCount = 0
        for R, ls in enumerate(locationSpecies):
            locationItem = QTableWidgetItem(ls[0])
            newLocationSpeciesItem = QTableWidgetItem(ls[1])
            self.tblNewLocationSpecies.setItem(R, 0, locationItem)
            self.tblNewLocationSpecies.setItem(R, 1, newLocationSpeciesItem)
            self.tblNewLocationSpecies.item(R, 1).setFont(font)
            if " x " in ls[1] or "sp." in ls[1] or "/" in ls[1]:
                self.tblNewLocationSpecies.item(R, 1).setForeground(Qt.gray)
                nonSpeciesTaxaCount += 1
            else:
                self.tblNewLocationSpecies.item(R, 1).setForeground(code_Stylesheet.speciesColor)
                count += 1
        labelText = "New location species: " + str(count)
        if nonSpeciesTaxaCount > 0:
            labelText += " + " + str(nonSpeciesTaxaCount) + " taxa"
        self.lblNewLocationSpecies.setText(labelText)

        # set location column width (must be done after fill since setColumnCount resets widths)
        fontSize = self.mdiParent.fontSize
        textWidth = int(QFontMetrics(QFont("Helvetica", fontSize)).boundingRect("Dummy Country").width())
        self.tblNewLocationSpecies.horizontalHeader().resizeSection(0, floor(8 * textWidth))


    def FillSpeciesForDate(self):
        # create temporary filter for query with nothing but needed date
        self.lstSpecies.clear()
        date = self.lstDates.currentItem().text()
        
        tempFilter = code_Filter.Filter()
        
        tempFilter.setStartDate(date)
        tempFilter.setEndDate(date)
        
        speciesList = self.mdiParent.db.GetSpecies(tempFilter,  self.filteredSightingList)
        
        self.lstSpecies.addItems(speciesList)
        self.lstSpecies.setSpacing(2)
        
        count = 0
        nonSpeciesTaxaCount = 0
        
        font = QFont()
        font.setBold(True)
        
        for R in range(self.lstSpecies.count()):
            
            self.lstSpecies.item(R).setFont(font)
            
            speciesName = self.lstSpecies.item(R).text()
            
            if " x " in speciesName or "sp." in speciesName or "/" in speciesName:
                self.lstSpecies.item(R).setForeground(Qt.gray)
                nonSpeciesTaxaCount += 1
            
            else:
                self.lstSpecies.item(R).setForeground(code_Stylesheet.speciesColor)
                count += 1                   
            
            R = R + 1
                
        labelText = "Species: " + str(count)
        
        if nonSpeciesTaxaCount > 0:
            labelText = labelText + " + " + str(nonSpeciesTaxaCount) + " taxa"
                
        self.lblSpeciesSeen.setText(labelText) 
    

    def FillMap(self):
        import folium, tempfile, re
        mapWidth = int(self.width() - 20)
        mapHeight = int(self.height() - self.lblLocation.height() - (self.lblDateRange.height() * 7.5))
        self.webMap.setGeometry(5, 5, mapWidth, mapHeight)

        coordinatesDict = defaultdict()
        for l in range(self.lstLocations.count()):
            locationName = self.lstLocations.item(l).text()
            coordinates = self.mdiParent.db.GetLocationCoordinates(locationName)
            coordinatesDict[locationName] = coordinates

        points = []
        for name, coords in coordinatesDict.items():
            points.append([float(coords[0]), float(coords[1])])

        # Compute center and zoom in Python — Leaflet can't fitBounds reliably
        # inside a hidden tab (container size is 0 on first render).
        lats = [p[0] for p in points]
        lons  = [p[1] for p in points]
        center = [(min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2]
        span = max(max(lats) - min(lats), max(lons) - min(lons), 0.01)

        if   span >= 90:  zoom = 2
        elif span >= 45:  zoom = 3
        elif span >= 22:  zoom = 4
        elif span >= 11:  zoom = 5
        elif span >= 5:   zoom = 6
        elif span >= 2.5: zoom = 7
        elif span >= 1.2: zoom = 8
        elif span >= 0.6: zoom = 9
        elif span >= 0.3: zoom = 10
        elif span >= 0.15:zoom = 11
        elif span >= 0.07:zoom = 12
        else:             zoom = 13

        location_map = folium.Map(location=center, zoom_start=zoom,
                                  tiles="CartoDB Positron")
        for name, coords in coordinatesDict.items():
            lat, lon = float(coords[0]), float(coords[1])
            marker = folium.CircleMarker(
                location=[lat, lon],
                radius=6,
                color="#4f8ef7",
                fill=True,
                fill_color="#4f8ef7",
                fill_opacity=0.85,
                tooltip=name,
            )
            marker.options["locationName"] = name
            marker.add_to(location_map)

        # Wire up QWebChannel bridge for click-to-spawn-Location
        self._mapBridge = BigReportMapBridge(self)
        channel = QWebChannel(self.webMap.page())
        channel.registerObject("bridge", self._mapBridge)
        self.webMap.page().setWebChannel(channel)

        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        html = location_map.get_root().render()

        map_var = re.search(r'var\s+(map_[a-zA-Z0-9_]+)\s*=\s*L\.map', html)
        map_var = map_var.group(1) if map_var else "map"

        inject_js = f"""
<script>
{qwc_js}
document.addEventListener("DOMContentLoaded", function() {{
    setTimeout(function() {{ {map_var}.invalidateSize(); }}, 100);
    new QWebChannel(qt.webChannelTransport, function(channel) {{
        window.bridge = channel.objects.bridge;
        {map_var}.eachLayer(function(layer) {{
            if (layer.options && layer.options.locationName) {{
                var name = layer.options.locationName;
                layer.on('click', function(e) {{
                    window.bridge.locationClicked(name);
                }});
            }}
        }});
    }});
}});
</script>
"""
        html = html.replace("</body>", inject_js + "</body>")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False,
                                         encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.webMap.setUrl(QUrl.fromLocalFile(tmp_path))
        

    
    def FillSpeciesForLocation(self):
        # create temporary filter for query with nothing but needed location
        location = self.lstLocations.currentItem().text()
        
        tempFilter = code_Filter.Filter()
        tempFilter.setLocationType("Location")
        tempFilter.setLocationName(location)

        speciesList = self.mdiParent.db.GetSpecies(tempFilter,  self.filteredSightingList)
        
        self.lstLocationSpecies.clear()
        self.lstLocationSpecies.addItems(speciesList)
        self.lstLocationSpecies.setSpacing(2)
        
        uniqueSpecies = self.mdiParent.db.GetUniqueSpeciesForLocation(
            self.filter,
            location,  
            speciesList,  
            self.filteredSightingList
            )
            
        self.lstLocationUniqueSpecies.clear()
        self.lstLocationUniqueSpecies.addItems(uniqueSpecies)
        self.lstLocationUniqueSpecies.setSpacing(2)
        
        count = 0
        nonSpeciesTaxaCount = 0
        
        # set up a bold font 
        font = QFont()
        font.setBold(True)
        
        for R in range(self.lstLocationSpecies.count()):
            
            # set font to bold for all entries
            self.lstLocationSpecies.item(R).setFont(font)
            
            # color code the entry. Stylesheet color  for full species, gray if not
            # set the species to gray if it's not a true species
            if " x " in self.lstLocationSpecies.item(R).text() or "sp." in self.lstLocationSpecies.item(R).text() or "/" in self.lstLocationSpecies.item(R).text():
                self.lstLocationSpecies.item(R).setForeground(Qt.gray)
                nonSpeciesTaxaCount += 1
            else:
                self.lstLocationSpecies.item(R).setForeground(code_Stylesheet.speciesColor)
                count += 1         
        
        labelText = "Species: " + str(count)
        
        if nonSpeciesTaxaCount > 0:
            labelText = labelText + " + " + str(nonSpeciesTaxaCount) + " taxa"
        
        self.lblLocationSpecies.setText(labelText)

        # reset counts
        count = 0
        nonSpeciesTaxaCount = 0
                
        for R in range(self.lstLocationUniqueSpecies.count()):
            
            # set font to bold for all entries
            self.lstLocationUniqueSpecies.item(R).setFont(font)
            
            # color code the entry. Stylesheet color  for full species, gray if not
            # set the species to gray if it's not a true species
            if " x " in self.lstLocationUniqueSpecies.item(R).text() or "sp." in self.lstLocationUniqueSpecies.item(R).text() or "/" in self.lstLocationUniqueSpecies.item(R).text():
                self.lstLocationUniqueSpecies.item(R).setForeground(Qt.gray)
                nonSpeciesTaxaCount += 1
            else:
                self.lstLocationUniqueSpecies.item(R).setForeground(code_Stylesheet.speciesColor)
                count += 1         
        
        labelText = "Observed only at location: " + str(count)
        
        if nonSpeciesTaxaCount > 0:
            labelText = labelText + " + " + str(nonSpeciesTaxaCount) + " taxa"        
        
        self.lblLocationUniqueSpecies.setText(labelText)


    def TblSpeciesClicked(self):
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        currentColumn = self.tblSpecies.currentColumn()
        currentRow = self.tblSpecies.currentRow()
        
        tempFilter = deepcopy(self.filter)
        
        if currentColumn == 0:
            # the taxonomy order column was clicked, so abort. We won't create a report.
            # turn off the hourglass cursor before exiting
            QApplication.restoreOverrideCursor()     
            return
                        
        if currentColumn == 1:
            # species column has been clicked so create individual window for that species
            species = self.tblSpecies.item(currentRow,  1).data(Qt.UserRole)
            sub = code_Individual.Individual()
            sub.mdiParent = self.mdiParent
            sub.FillIndividual(species)        
            self.parent().parent().addSubWindow(sub)
            self.mdiParent.PositionChildWindow(sub, self)        
            sub.show() 
            sub.resizeMe()
        
        if currentColumn > 1:
            # date column has been clicked so create species list frame for that dateArray
            # use same start and end date for new filter to show just the single day
            date = self.tblSpecies.item(currentRow,  currentColumn).text()
            tempFilter.setStartDate(date)
            tempFilter.setEndDate(date)
            
            sub = code_Lists.Lists()
            sub.mdiParent = self.mdiParent
            sub.FillSpecies(tempFilter)
            self.parent().parent().addSubWindow(sub)
            self.mdiParent.PositionChildWindow(sub, self)
            sub.show()
            sub.scaleMe()
            sub.resizeMe()

        QApplication.restoreOverrideCursor()
        

    def html(self):
    
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        # create start to basic html format
        html = """
            <!DOCTYPE html>
            <html>
            <head>
            </head>
            <style>
            * {
                font-size: 75%;
                font-family: "Times New Roman", Times, serif;
                }
            th {
                text-align: left;
            }
            </style>
            <body>
            """
        
        # add title information
        html = html + (
            "<H1>" + 
            self.lblLocation.text() + 
            "</H1>"
            )
        
        html = html + (
            "<H3>" + 
            self.lblDateRange.text() + 
            "</H3>"
            )        

        html = html + (
            "<H3>" + 
            self.lblDetails.text() + 
            "</H3>"
            )               

        html = html + (
            "<H3>" + 
            self.lblLocationsVisited.text() + 
            "</H3>"
            )   

        html = html + (
            "<H3>" + 
            self.lblTopSpeciesSeen.text() + 
            "</H3>"
            )    
            
        # grab the map image from the map tap
        # process it into a byte array and encode it
        # so we can insert it inline into the html
        myPixmap = self.webMap.grab()
        myPixmap = myPixmap.scaledToWidth(600, Qt.SmoothTransformation)

        myByteArray = QByteArray()
        myBuffer = QBuffer(myByteArray)
        myBuffer.open(QIODevice.OpenModeFlag.WriteOnly)
        myPixmap.save(myBuffer, "PNG")

        encodedImage = base64.b64encode(myByteArray)
        
        html = html + ("""
        <img src="data:image/png;base64, 
        """)
        
        html = html + str(encodedImage)[1:]
        
        html = html + ("""        
        "  />
        """)

        html = html + (
            "<H4>" + 
            "Species" +
            "</H4>"
            )    

        html=html + (
            "<font size='2'>" +
            "<table width='100%'>" +
            " <tr>"
            )
                    
        html=html + (    
            "<th>" + 
            "Species" +
            "</th>" +
            "<th>" + 
            "First" + 
            "</th> " +
            "<th></th> " +
            "<th>" +
            "Latest" +
            "</th>" +
            "</tr>"
            )
            
        for r in range(self.tblSpecies.rowCount()):
            html = html + (
            "<tr>" +
            "<td>" +
            self.tblSpecies.item(r, 1).text() +
            "</td>" +
            "<td>" +
            self.tblSpecies.item(r, 2).text() +
            "</td>" +
            "<td>" +
            "  " +
            "</td>" +
            "<td>" +
            self.tblSpecies.item(r, 3).text() +
            "</td>" +
            "</tr>"
            )
        html = html + "</table>"

        html= html + (
            "<H4>" +
            "Dates" +
            "</H4>"
            )

        html=html + (
            "<font size='2'>" +
            "<p>"
            )
       
        # loopthrough the dates listed in lstDates
        # create a filter unique to each date
        # and get species for that date
        for r in range(self.lstDates.count()):
            html= html + (
                "<b>" +
                self.lstDates.item(r).text() +
                "</b>"                
                )
 
            # create filter set to our current location
            filter = deepcopy(self.filter)
            filter.setStartDate(self.lstDates.item(r).text())
            filter.setEndDate(self.lstDates.item(r).text())
            
            species = self.mdiParent.db.GetSpecies(filter)

            html = html + (    
                "<br>" +                   
                "<table width='100%'>" +
                "<tr>"
                )

            # set up counter R to start a new row after listing each 3 species
            R = 1
            for s in species:
                html = html + (
                    "<td>" +
                    s + 
                    "</td>"
                    )
                if R == 3:
                    html = html + (
                        "</tr>" +
                        "<tr>"
                        )
                    R = 0
                R = R + 1

            html= html + (
                "<br>" +
                "<br>" +
                "</table>"
                )

        html= html + (
            "<H4>" +
            "Locations" +
            "</H4>" +
            "<p>" +
            "Asterisks indicate species seen only at listed location."
            )

        # loopthrough the locations listed in lstLocations
        # create a filter unique to each location
        # and get species for that date
        for r in range(self.lstLocations.count()):
            html= html + (
                "<b>" +
                self.lstLocations.item(r).text() +
                "</b>"                
                )
 
            # create filter set to our current location
            filter = deepcopy(self.filter)
            filter.setLocationType("Location")
            filter.setLocationName(self.lstLocations.item(r).text())
                        
            species = self.mdiParent.db.GetSpecies(filter)

            uniqueSpecies = self.mdiParent.db.GetUniqueSpeciesForLocation(
                self.filter,
                self.lstLocations.item(r).text(),  
                species,  
                self.filteredSightingList
                )            

            html = html + (    
                "<br>" +                       
                "<table width='100%'>" +
                "<tr>"
                )

            # set up counter R to start a new row after listing each 3 species
            R = 1
            for s in species:
                
                if s in uniqueSpecies:
                    s = s + "*"
                    
                html = html + (
                    "<td>" +
                    s + 
                    "</td>"
                    )
                if R == 3:
                    html = html + (
                        "</tr>" +
                        "<tr>"
                        )
                    R = 0
                R = R + 1

            html= html + (
                "<br>" +
                "<br>" +
                "</table>"
                )

        html= html + (
            "<p>" +
            "<H4>" +
            "New Life Species" +
            "</H4>" +
            "<p>" +
            "<table width='100%'>"
            "<tr>"
            )

        # set up counter R to start a new row after listing each 3 species
        R = 1

        if self.lstNewLifeSpecies.count() == 0:
            html = html + (
                "<td>" +
                "None" +
                "</td>"
                )
                
        else:
            
            # loopthrough the species listed in lstNewLifeSpecies
            for r in range(self.lstNewLifeSpecies.count()):
                        
                html = html + (
                    "<td>" +
                    self.lstNewLifeSpecies.item(r).text() +
                    "</td>"
                    )
                    
                if R == 3:
                    html = html + (
                        "</tr>" +
                        "<tr>"
                        )
                    R = 0
                    
                R = R + 1

            html= html + (
                "<br>" +
                "<br>" +
                "</table>"
                    )
                
        # set up New Year Species
        html= html + (
            "<p>" +
            "<H4>" +
            "New Year Species" +
            "</H4>" +
            "<p>" +
            "<table width='100%'>" +
            "<tr>"
            )

        # set up counter R to start a new row after listing each 3 species
        R = 1

        if self.tblNewYearSpecies.rowCount() == 0:
            html = html + (
                "<td>" +
                "None" +
                "</td>"
                )
                
        else:
            # loopthrough the species listed in lstNewLifeSpecies
            for r in range(self.tblNewYearSpecies.rowCount()):
            
                html = html + (
                    "<td>" +
                    self.tblNewYearSpecies.item(r, 1).text() +
                    " (" + self.tblNewYearSpecies.item(r, 0).text() + ")" +
                    "</td>"
                    )
                    
                if R == 3:
                    html = html + (
                        "</tr>"
                        "<tr>"
                        )
                    R = 0
                    
                R = R + 1

            html= html + (
                "</tr>" +
                "</table>"
                    )

        # set up New Month Species
        html= html + (
            "<p>" +
            "<H4>" +
            "New Month Species" +
            "</H4>" +
            "<p>" +
            "<table width='100%'>" +
            "<tr>"
            )

        # set up counter R to start a new row after listing each 3 species
        R = 1

        if self.tblNewMonthSpecies.rowCount() == 0:
            html = html + (
                "<td>" +
                "None" +
                "</td>"
                )
                
        else:
        
            # loopthrough the species listed in lstNewLifeSpecies
            for r in range(self.tblNewMonthSpecies.rowCount()):
            
                html = html + (
                    "<td>" +
                    self.tblNewMonthSpecies.item(r, 1).text() +
                    " (" + self.tblNewMonthSpecies.item(r, 0).text() + ")" +
                    "</td>"
                    )
                    
                if R == 3:
                    html = html + (
                        "</tr>"
                        "<tr>"
                        )
                    R = 0
                    
                R = R + 1

            html= html + (
                "</tr>" +
                "</table>"
                    )

        # set up New Country Species
        html= html + (
            "<p>" +
            "<H4>" +
            "New Country Species" +
            "</H4>" +
            "<p>" +
            "<table width='100%'>" +
            "<tr>"
            )

        # set up counter R to start a new row after listing each 3 species
        R = 1
        
        if self.tblNewCountrySpecies.rowCount() == 0:
            html = html + (
                "<td>" +
                "None" +
                "</td>"
                )
                
        else:

            # loopthrough the species listed in lstNewLifeSpecies
            for r in range(self.tblNewCountrySpecies.rowCount()):
            
                html = html + (
                    "<td>" +
                    self.tblNewCountrySpecies.item(r, 1).text() +
                    " (" + self.tblNewCountrySpecies.item(r, 0).text() + ")" +
                    "</td>"
                    )
                    
                if R == 2:
                    html = html + (
                        "</tr>"
                        "<tr>"
                        )
                    R = 0
                    
                R = R + 1

            html= html + (
                "</tr>" +
                "</table>"
                    )
                
        html = html + (
            "<font size>" +            
            "</body>" +
            "</html>"
            )
        
        # set up New State Species
        html= html + (
            "<p>" +
            "<H4>" +
            "New State Species" +
            "</H4>" +
            "<p>" +
            "<table width='100%'>" +
            "<tr>"
            )

        # set up counter R to start a new row after listing each 3 species
        R = 1

        if self.tblNewStateSpecies.rowCount() == 0:
            html = html + (
                "<td>" +
                "None" +
                "</td>"
                )
                
        else:
            
            # loopthrough the species listed in lstNewLifeSpecies
            for r in range(self.tblNewStateSpecies.rowCount()):
            
                html = html + (
                    "<td>" +
                    self.tblNewStateSpecies.item(r, 1).text() +
                    " (" + self.tblNewStateSpecies.item(r, 0).text() + ")" +
                    "</td>"
                    )
                    
                if R == 2:
                    html = html + (
                        "</tr>"
                        "<tr>"
                        )
                    R = 0
                    
                R = R + 1

            html= html + (
                "</tr>" +
                "</table>"
                    )

        # set up New County Species
        html= html + (
            "<p>" +
            "<H4>" +
            "New County Species" +
            "</H4>" +
            "<p>" +
            "<table width='100%'>" +
            "<tr>"
            )

        # set up counter R to start a new row after listing each 3 species
        R = 1

        if self.tblNewCountySpecies.rowCount() == 0:
            html = html + (
                "<td>" +
                "None" +
                "</td>"
                )
                
        else:
            
            # loopthrough the species listed in lstNewLifeSpecies
            for r in range(self.tblNewCountySpecies.rowCount()):
            
                html = html + (
                    "<td>" +
                    self.tblNewCountySpecies.item(r, 1).text() +
                    " (" + self.tblNewCountySpecies.item(r, 0).text() + ")" +
                    "</td>"
                    )
                    
                if R == 2:
                    html = html + (
                        "</tr>"
                        "<tr>"
                        )
                    R = 0
                    
                R = R + 1

            html= html + (
                "</tr>" +
                "</table>"
                    )
     
        # set up New Location Species
        html= html + (
            "<p>" +
            "<H4>" +
            "New Location Species" +
            "</H4>" +
            "<p>" +
            "<table width='100%'>" +
            "<tr>"
            )

        # set up counter R to start a new row after listing each 3 species
        R = 1

        if self.tblNewLocationSpecies.rowCount() == 0:
            html = html + (
                "<td>" +
                "None" +
                "</td>"
                )
                
        else:
            
            # loopthrough the species listed in lstNewLifeSpecies
            for r in range(self.tblNewLocationSpecies.rowCount()):
            
                html = html + (
                    "<td>" +
                    self.tblNewLocationSpecies.item(r, 1).text() +
                    " (" + self.tblNewLocationSpecies.item(r, 0).text() + ")" +
                    "</td>"
                    )
                    
                if R == 2:
                    html = html + (
                        "</tr>"
                        "<tr>"
                        )
                    R = 0
                    
                R = R + 1

            html= html + (
                "</tr>" +
                "</table>"
                )
     
        html = html + (
            "<font size>" +            
            "</body>" +
            "</html>"
            )       
            
        QApplication.restoreOverrideCursor()   
        
        return(html)


    def setDateFilter(self):
        # get location name and type from focus widget. Varies for widgets. 
        if self.focusWidget().objectName() == "lstDates":
            date = self.focusWidget().currentItem().text()
            self.mdiParent.setDateFilter(date)

        if self.focusWidget().objectName() == "tblNewYearSpecies":
            date = self.focusWidget().item(self.focusWidget().currentRow(), 0).text()
            startDate = date + "-01-01"
            endDate = date + "-12-31"
            self.mdiParent.setDateFilter(startDate, endDate)

        if self.focusWidget().objectName() == "tblNewMonthSpecies":
            month = self.focusWidget().item(self.focusWidget().currentRow(), 0).text()
            self.mdiParent.setSeasonalRangeFilter(month)


    def setFirstDateFilter(self):
        # get location name and type from focus widget. Varies for tables. 
        if self.focusWidget().objectName() == "tblSpecies":
            date = self.focusWidget().item(self.focusWidget().currentRow(), 3).text()
            self.mdiParent.setDateFilter(date)


    def setLastDateFilter(self):
        # get location name and type from focus widget. Varies for tables. 
        if self.focusWidget().objectName() == "tblSpecies":
            date = self.focusWidget().item(self.focusWidget().currentRow(), 4).text()
            self.mdiParent.setDateFilter(date)
            
            
    def setLocationFilter(self):

        # get location name and type from focus widget. Varies for tables. 
        if self.focusWidget().objectName() == "tblNewCountrySpecies":
            country = self.focusWidget().item(self.focusWidget().currentRow(), 0).text()
            self.mdiParent.setCountryFilter(country)

        if self.focusWidget().objectName() == "tblNewStateSpecies":
            state = self.focusWidget().item(self.focusWidget().currentRow(), 0).text()
            self.mdiParent.setStateFilter(state)

        if self.focusWidget().objectName() == "tblNewCountySpecies":
            county = self.focusWidget().item(self.focusWidget().currentRow(), 0).text()
            self.mdiParent.setCountyFilter(county)

        if self.focusWidget().objectName() == "tblNewLocationSpecies":
            location = self.focusWidget().item(self.focusWidget().currentRow(), 0).text()
            self.mdiParent.setLocationFilter(location)

        if self.focusWidget().objectName() == "lstLocations":
            location = self.focusWidget().currentItem().text()
            self.mdiParent.setLocationFilter(location)


    def setSpeciesFilter(self):

        # get species name from focus widget. Getting the species name is different for tables than for lists.
        if self.focusWidget().objectName() in ([
            "tblSpecies",
            "tblNewYearSpecies", 
            "tblNewMonthSpecies", 
            "tblNewCountrySpecies", 
            "tblNewStateSpecies", 
            "tblNewCountySpecies", 
            "tblNewLocationSpecies"
            ]):
            species = self.focusWidget().item(self.focusWidget().currentRow(), 1).text()

        if self.focusWidget().objectName() in ([
            "lstSpecies",
            "lstLocationSpecies",
            "lstLocationUniqueSpecies",
            "lstNewLifeSpecies"
            ]):
            species = self.focusWidget().currentItem().text()

        self.mdiParent.setSpeciesFilter(species)


    def resizeEvent(self, event):
        #routine to handle events on objects, like clicks, lost focus, gained forcus, etc.        
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)
        
        
    def resizeMe(self):

        windowWidth =  self.frameGeometry().width()
        windowHeight = self.frameGeometry().height()
        self.scrollArea.setGeometry(5, 27, windowWidth -10 , windowHeight-35)
        self.FillMap()

   
    def scaleMe(self):
               
        scaleFactor = self.mdiParent.scaleFactor
        windowWidth =  int(1100  * scaleFactor)
        windowHeight = int(625 * scaleFactor)            
        self.resize(windowWidth, windowHeight)
        
        fontSize = self.mdiParent.fontSize
        scaleFactor = self.mdiParent.scaleFactor     
        #scale the font for all widgets in window
        for w in self.scrollArea.children():
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

        metrics = QFontMetrics(QFont("Helvetica", fontSize))
        textWidth = int(metrics.boundingRect("Dummy Country").width())

        rowHeight = self.mdiParent.rowHeight

        for t in ([
            self.tblNewYearSpecies,
            self.tblNewMonthSpecies,
            self.tblNewCountrySpecies,
            self.tblNewStateSpecies,
            self.tblNewCountySpecies
            ]):
            header = t.horizontalHeader()
            if t == self.tblNewYearSpecies or t == self.tblNewMonthSpecies:
                header.resizeSection(0,  floor(.6 * textWidth))
            else:
                header.resizeSection(0,  floor(textWidth))
            t.verticalHeader().setDefaultSectionSize(rowHeight)

        # format tblSpecies, which is laid out differently from the other tables
        dateWidth = int(metrics.boundingRect("2222-22-22").width())
        header = self.tblSpecies.horizontalHeader()
        header.resizeSection(2,  floor(1.5* dateWidth))
        header.resizeSection(3,  floor(1.5 * dateWidth))
        self.tblSpecies.verticalHeader().setDefaultSectionSize(rowHeight)

        # format tblNewLocationSpecies, which needs wider location column
        header = self.tblNewLocationSpecies.horizontalHeader()
        header.resizeSection(0,  floor(8 * textWidth))
        self.tblNewLocationSpecies.verticalHeader().setDefaultSectionSize(rowHeight)

