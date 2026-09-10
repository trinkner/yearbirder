# import project files
import form_BigReport
from code_Stylesheet import YBFont
import code_Filter
import code_Basemap
import code_MediaRefresh
import code_Location
import code_Individual
import code_Lists
import code_Stylesheet
from code_Web import satellite_toggle_js

# import basic Python libraries
from copy import deepcopy
from collections import defaultdict
from datetime import datetime
from html import escape
from math import floor
import base64

from PySide6.QtGui import (
    QColor,
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
    QBuffer,
    QEventLoop,
    QTimer
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


# ---- PDF palette ---------------------------------------------------------
# The printed report is rendered by QTextDocument, which understands only Qt's
# rich-text subset of CSS — no flexbox, no columns, no borders on ordinary
# blocks.  Everything structural below is therefore built from tables and cell
# background colours, which that subset does support reliably.  The palette is
# print-friendly: charcoal bands, light zebra rows, the app blue as the single
# accent.
_PDF_INK     = "#1f2430"   # body text
_PDF_MUTED   = "#5a6070"   # subtitles, notes, secondary numbers
_PDF_BAND    = "#2f3542"   # section header band
_PDF_BAND_FG = "#ffffff"   # section header text
_PDF_BAND_NOTE = "#c9ccd6"  # section header's right-hand count
_PDF_SUBBAND = "#e8eaee"   # per-date / per-location header, table headers
_PDF_ZEBRA   = "#f5f6f8"   # alternating row fill
_PDF_WHITE   = "#ffffff"


def _taxOrder(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _fmtItineraryDate(dateString):
    """'2025-05-09' -> 'Friday, May 9, 2025' (no %-d: Windows has no such flag)."""
    try:
        d = datetime.strptime(dateString, "%Y-%m-%d")
    except (ValueError, TypeError):
        return dateString
    return f"{d.strftime('%A, %B')} {d.day}, {d.year}"


def _fmtReportDate(d):
    """'September 8, 2026' — spelled out, and no %-d (Windows has no such flag)."""
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _fmtItineraryTime(timeString):
    """'17:24' -> '5:24 PM'.  Times are stored 24-hour by the CSV importer."""
    if not timeString:
        return ""
    try:
        hour = int(timeString[0:2])
        minute = timeString[3:5]
    except (ValueError, IndexError):
        return timeString
    suffix = "AM" if hour < 12 else "PM"
    displayHour = hour % 12
    if displayHour == 0:
        displayHour = 12
    return f"{displayHour}:{minute} {suffix}"


def _fmtItineraryDuration(minutes):
    if not minutes:
        return ""
    try:
        total = int(round(float(minutes)))
    except (ValueError, TypeError):
        return ""
    if total <= 0:
        return ""
    hours, mins = divmod(total, 60)
    if hours == 0:
        return f"{mins} min"
    return f"{hours}h {mins}m" if mins else f"{hours}h"


def _fmtItineraryDistance(km):
    # eBird records distance in kilometers; the app reports both units
    if not km:
        return ""
    try:
        value = float(km)
    except (ValueError, TypeError):
        return ""
    if value <= 0:
        return ""
    return f"{value:.2f} km ({value * 0.621371:.2f} mi)"


def _itineraryDaySummary(dayStops):
    """"3 checklists · 2 locations · 47 species" for one day's stops."""
    locations = len(set(c["location"] for c in dayStops))
    species = set()
    for c in dayStops:
        for entry in c["species"]:
            if entry["isSpecies"]:
                species.add(entry["commonName"])
    return " · ".join([
        f"{len(dayStops)} checklist{'' if len(dayStops) == 1 else 's'}",
        f"{locations} location{'' if locations == 1 else 's'}",
        f"{len(species)} species",
        ])


def _itineraryStopMeta(stop):
    """One stop's protocol / duration / distance / species count, as plain text."""
    meta = [stop[key] for key in ("protocol", "duration", "distance") if stop[key]]
    meta.append(f"{len(stop['species'])} species")
    return meta


def _itinerarySpeciesCount(entry):
    """The count to show beside a species — a number, eBird's "X", or nothing."""
    if entry["count"] > 0:
        return str(entry["count"])
    return "X" if entry["uncounted"] else ""


def _fmtItineraryProtocol(protocol):
    """Name the checklist type the way Statistics and the eBird app do.

    The CSV spells these "eBird - Traveling Count", "eBird - Casual
    Observation", and so on; the same substring tests Statistics uses (see
    code_Stats._computeStats) map them onto the four familiar names.  Anything
    else — Area, Banding, a pelagic count — keeps its own name rather than
    being flattened to Statistics' catch-all "Other", which would tell the
    reader nothing about the stop.
    """
    protocol = (protocol or "").strip()
    for name in ("Traveling", "Stationary", "Historical"):
        if name in protocol:
            return name
    if "Casual" in protocol:
        return "Incidental"
    if protocol.startswith("eBird - "):
        protocol = protocol[len("eBird - "):]
    return protocol


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


class BigReportItineraryBridge(QObject):
    """Qt/JavaScript bridge for the Big Report Itinerary tab.

    Registered on the page's QWebChannel as 'bridge'.  Clicking a stop's
    location name opens the Location child window, clicking a species opens
    the Individual child window, and clicking the eBird link opens the
    checklist in the system browser.
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

    @Slot(str)
    def speciesClicked(self, speciesName):
        # spuh/slash taxa are not filed in speciesDict, so there is no
        # Individual window to build for them
        if speciesName not in self._br.mdiParent.db.speciesDict:
            return
        sub = code_Individual.Individual()
        sub.mdiParent = self._br.mdiParent
        sub.FillIndividual(speciesName)
        self._br.mdiParent.mdiArea.addSubWindow(sub)
        self._br.mdiParent.PositionChildWindow(sub, self._br)
        sub.show()
        sub.resizeMe()

    @Slot(str)
    def checklistClicked(self, checklistID):
        from PySide6.QtGui import QDesktopServices
        if checklistID:
            QDesktopServices.openUrl(QUrl(f"https://ebird.org/checklist/{checklistID}"))


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
        # Match the lighter-gray table background (#252730) on the Dates,
        # Locations, and "New for Dates" tabs (default QListWidget bg is darker).
        for lst in (self.lstNewLifeSpecies, self.lstDates, self.lstSpecies,
                    self.lstLocations, self.lstLocationSpecies, self.lstLocationUniqueSpecies):
            lst.setStyleSheet("QListWidget { background: #252730; }")
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

        # The Itinerary view lives in the tab's layout so it tracks the window
        # size; its HTML is built lazily, once the tab is first shown, so the
        # renderer has a real viewport to lay the report out in.
        self.webItinerary = QWebEngineView(self.tabItinerary)
        self.webItinerary.setObjectName("webItinerary")
        # Chromium paints an unloaded page white, which flashes when the tab is
        # first revealed — match the report's own background (as Stats and the
        # Web reports do) so the reveal is seamless.
        self.webItinerary.page().setBackgroundColor(QColor("#1e1f26"))
        self.verticalLayout_Itinerary.addWidget(self.webItinerary)

        self.tabAnalysis.setCurrentIndex(0)
        self.speciesList = []
        self.filter = code_Filter.Filter()
        self.filteredSightingList = []
        self.sightingListForSpeciesSubset = None
        self.newDatesLoaded = False
        self.newRegionsLoaded = False
        self.newLocationsLoaded = False
        self.itineraryLoaded = False
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


    @code_MediaRefresh.media_report()
    def FillAnalysisReport(self, filter):
        # save filter for later use
        self.filter = filter
        
        # set up a bold font to use in columns as needed
        font = QFont()
        font.setBold(True)         
        
        # create subset of master sightings list for this filter
        self.filteredSightingList = deepcopy(self.mdiParent.db.GetSightings(filter))
        filteredSightingList = self.filteredSightingList

        # a media refresh replays this method, so the itinerary built from the
        # previous sighting list is now stale
        self.itineraryLoaded = False
        
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
            countItem.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
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

        # onTabChanged only fires on a change, so rebuild the itinerary here if
        # its tab is already the one on screen
        if self.tabAnalysis.currentIndex() == self.tabAnalysis.indexOf(self.tabItinerary):
            self.FillItinerary()
            self.itineraryLoaded = True

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
        elif index == tabIndex(self.tabItinerary) and not self.itineraryLoaded:
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            self.FillItinerary()
            self.itineraryLoaded = True
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
        textWidth = int(QFontMetrics(QFont(YBFont, fontSize)).boundingRect("Dummy Country").width())
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
    

    def _locationSequence(self):
        """Number each location by when the filtered set first reaches it.

        The map draws one dot per location, so a location revisited later in
        the trip keeps the number of its first visit — the dots then read as
        the route travelled, in step with the Itinerary tab's ordering.
        """
        firstVisit = {}
        for s in self.filteredSightingList:
            location = s.get("location", "")
            when = (s.get("date", ""), s.get("time", "") or "")
            if location not in firstVisit or when < firstVisit[location]:
                firstVisit[location] = when
        ordered = sorted(firstVisit.items(), key=lambda kv: (kv[1], kv[0]))
        return {location: n for n, (location, _) in enumerate(ordered, start=1)}


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
                                  tiles=code_Basemap.streetTiles())

        # Numbered dots, in visit order.  A DivIcon replaces the plain
        # CircleMarker because only real markup can carry a label; every dot
        # gets the same diameter, sized to the widest number so the map keeps
        # one consistent dot size.
        sequence = self._locationSequence()
        digits = len(str(max(sequence.values()))) if sequence else 1
        diameter = {1: 20, 2: 22, 3: 26}.get(digits, 30)
        fontSize = {1: 11, 2: 11, 3: 10}.get(digits, 9)

        for name, coords in coordinatesDict.items():
            lat, lon = float(coords[0]), float(coords[1])
            number = sequence.get(name, 0)
            icon = folium.DivIcon(
                icon_size=(diameter, diameter),
                icon_anchor=(diameter // 2, diameter // 2),
                html=(
                    f'<div style="width:{diameter}px;height:{diameter}px;'
                    'border-radius:50%;background:#4f8ef7;opacity:0.9;'
                    'border:1px solid #1e1f26;box-sizing:border-box;'
                    'display:flex;align-items:center;justify-content:center;'
                    f'color:#ffffff;font-family:sans-serif;font-size:{fontSize}px;'
                    f'font-weight:700;line-height:1;">{number}</div>'
                ),
            )
            marker = folium.Marker(
                location=[lat, lon],
                icon=icon,
                tooltip=f"{number}. {name}",
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
        html = html.replace("</body>", inject_js + satellite_toggle_js() + "</body>")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False,
                                         encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.webMap.setUrl(QUrl.fromLocalFile(tmp_path))
        

    
    def _regionText(self, sighting):
        # county arrives as "Boulder (US-CO)"; the state code is spelled out
        # separately, so strip the parenthetical before joining the parts
        db = self.mdiParent.db
        parts = []
        county = (sighting.get("county") or "").split(" (")[0]
        if county:
            parts.append(county)
        state = sighting.get("state", "")
        if state:
            stateName = db.GetStateName(state)
            if stateName and stateName not in parts:
                parts.append(stateName)
        country = sighting.get("country", "")
        if country:
            countryName = db.GetCountryName(country)
            if countryName and countryName not in parts:
                parts.append(countryName)
        return ", ".join(parts)


    def _buildItineraryStops(self):
        """Group the filtered sightings into checklists, in chronological order.

        Every stop carries only the species the report's filter let through, so
        a species-filtered Big Report yields an itinerary of just those birds.
        """
        stops = {}
        seen = set()

        for s in self.filteredSightingList:
            # speciesDict files each sighting under both its common and its
            # subspecies name, so a species-filtered list holds the same object
            # twice whenever those names coincide — dedupe on identity
            if id(s) in seen:
                continue
            seen.add(id(s))

            checklistID = s.get("checklistID", "")
            stop = stops.get(checklistID)
            if stop is None:
                stop = stops[checklistID] = {
                    "checklistID": checklistID,
                    "date":        s.get("date", ""),
                    "time":        s.get("time", ""),
                    "location":    s.get("location", ""),
                    "region":      self._regionText(s),
                    "protocol":    _fmtItineraryProtocol(s.get("protocol", "")),
                    "duration":    _fmtItineraryDuration(s.get("duration", "")),
                    "distance":    _fmtItineraryDistance(s.get("distance", "")),
                    "comments":    (s.get("checklistComments") or "").strip(),
                    "species":     {},
                }

            # show the full name the checklist used (subspecies included), but
            # keep the top-level common name for the click-through to Individual
            commonName = s.get("commonName", "")
            name = s.get("subspeciesName") or commonName
            entry = stop["species"].get(name)
            if entry is None:
                entry = stop["species"][name] = {
                    "name":       name,
                    "commonName": commonName,
                    "tax":        _taxOrder(s.get("taxonomicOrder", 0)),
                    "count":      0,
                    "uncounted":  False,
                    "isSpecies":  (" x " not in commonName and
                                   "sp."  not in commonName and
                                   "/"    not in commonName),
                }
            count = (s.get("count") or "").strip()
            if count.isdigit():
                entry["count"] += int(count)
            else:
                # eBird's "X" — present, but not counted
                entry["uncounted"] = True

        ordered = sorted(stops.values(),
                         key=lambda c: (c["date"], c["time"] or "", c["checklistID"]))
        for stop in ordered:
            stop["species"] = sorted(stop["species"].values(), key=lambda e: e["tax"])

        return ordered


    def _itineraryHtml(self, stops):
        primary = code_Stylesheet.CHART_PRIMARY

        # Blue means "clickable" here — the location, the species, and the eBird
        # link.  Everything else on a card is plain text.
        css = """
  body { margin:0; padding:0; background:#1e1f26; color:#e2e4ec;
         font-family:sans-serif; font-size:13px; }
  #report { padding:0 16px 24px; }
  .day-head { position:sticky; top:0; background:#1e1f26; padding:12px 0 6px;
              border-bottom:1px solid #2a2b35; margin-bottom:10px; z-index:2; }
  .day-date { font-size:14px; font-weight:600; }
  .day-sub { font-size:11px; color:#8b8fa8; margin-left:10px; }
  .stop { background:CARD_BG; border-radius:5px; padding:10px 14px;
          margin-bottom:10px; }
  .stop-head { display:flex; flex-wrap:wrap; align-items:baseline; gap:10px; }
  .stop-time { font-size:12px; font-variant-numeric:tabular-nums;
               white-space:nowrap; }
  .stop-loc { color:COLOR_PRIMARY; font-weight:600; font-size:14px; cursor:pointer; }
  .stop-loc:hover { text-decoration:underline; }
  .stop-region { font-size:12px; }
  .meta { margin-top:6px; font-size:12px; }
  .meta span { white-space:nowrap; }
  .meta .sep { color:#8b8fa8; margin:0 7px; }
  .ebird { color:COLOR_PRIMARY; cursor:pointer; }
  .ebird:hover { text-decoration:underline; }
  .comments { margin-top:8px; font-size:12px; line-height:1.45;
              white-space:pre-wrap; }
  .species { margin-top:9px; columns:210px; column-gap:20px; }
  .sp { display:block; break-inside:avoid; padding:1px 0; font-size:12px;
        color:COLOR_PRIMARY; cursor:pointer; }
  .sp:hover { text-decoration:underline; }
  .sp.taxon { color:#8b8fa8; cursor:default; }
  .sp.taxon:hover { text-decoration:none; }
  .sp .ct { color:#e2e4ec; margin-left:5px; font-variant-numeric:tabular-nums; }
  .none { color:#8b8fa8; padding:20px 0; }
""".replace("COLOR_PRIMARY", primary).replace("CARD_BG", code_Stylesheet.mediaCardColor)

        # No banner here — the window's own banner already carries the report's
        # location, date range, and totals.
        parts = ["<div id='report'>"]

        if not stops:
            parts.append("<div class='none'>No checklists match this filter.</div>")

        stopsByDate = defaultdict(list)
        for stop in stops:
            stopsByDate[stop["date"]].append(stop)

        # ---- one section per date, one card per checklist ----
        currentDate = None
        for stop in stops:
            if stop["date"] != currentDate:
                if currentDate is not None:
                    parts.append("</div>")
                currentDate = stop["date"]
                daySub = _itineraryDaySummary(stopsByDate[currentDate])
                parts.append(
                    "<div class='day'><div class='day-head'>"
                    f"<span class='day-date'>{escape(_fmtItineraryDate(currentDate))}</span>"
                    f"<span class='day-sub'>{escape(daySub)}</span>"
                    "</div>"
                    )

            parts.append("<div class='stop'><div class='stop-head'>")
            parts.append(
                f"<span class='stop-loc' data-loc=\"{escape(stop['location'])}\">"
                f"{escape(stop['location'])}</span>"
                )
            time = _fmtItineraryTime(stop["time"])
            if time:
                parts.append(f"<span class='stop-time'>{escape(time)}</span>")
            if stop["region"]:
                parts.append(f"<span class='stop-region'>{escape(stop['region'])}</span>")
            parts.append("</div>")

            meta = [escape(m) for m in _itineraryStopMeta(stop)]
            if stop["checklistID"]:
                meta.append(
                    f"<span class='ebird' data-cid=\"{escape(stop['checklistID'])}\">"
                    f"{escape(stop['checklistID'])} &#8599;</span>"
                    )
            parts.append(
                "<div class='meta'>" +
                "<span class='sep'>·</span>".join(f"<span>{m}</span>" for m in meta) +
                "</div>"
                )

            if stop["comments"]:
                parts.append(f"<div class='comments'>{escape(stop['comments'])}</div>")

            parts.append("<div class='species'>")
            for entry in stop["species"]:
                countText = _itinerarySpeciesCount(entry)
                countHtml = f"<span class='ct'>{countText}</span>" if countText else ""
                if entry["isSpecies"]:
                    parts.append(
                        f"<span class='sp' data-sp=\"{escape(entry['commonName'])}\">"
                        f"{escape(entry['name'])}{countHtml}</span>"
                        )
                else:
                    parts.append(
                        f"<span class='sp taxon'>{escape(entry['name'])}{countHtml}</span>"
                        )
            parts.append("</div></div>")

        if currentDate is not None:
            parts.append("</div>")
        parts.append("</div>")

        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        script = """
%s
new QWebChannel(qt.webChannelTransport, function(channel) {
    window.bridge = channel.objects.bridge;
});
document.addEventListener('click', function(e) {
    if (!window.bridge || !e.target.closest) { return; }
    var el = e.target.closest('[data-loc]');
    if (el) { window.bridge.locationClicked(el.getAttribute('data-loc')); return; }
    el = e.target.closest('[data-sp]');
    if (el) { window.bridge.speciesClicked(el.getAttribute('data-sp')); return; }
    el = e.target.closest('[data-cid]');
    if (el) { window.bridge.checklistClicked(el.getAttribute('data-cid')); }
});
""" % qwc_js

        return ("<!DOCTYPE html>\n<html><head><meta charset='utf-8'>\n<style>" +
                css + "</style></head><body>\n" + "\n".join(parts) +
                "\n<script>" + script + "</script>\n</body></html>")


    def FillItinerary(self):
        import tempfile

        stops = self._buildItineraryStops()
        html = self._itineraryHtml(stops)

        # Wire up the QWebChannel bridge for click-through to Location,
        # Individual, and the checklist on eBird
        self._itineraryBridge = BigReportItineraryBridge(self)
        channel = QWebChannel(self.webItinerary.page())
        channel.registerObject("bridge", self._itineraryBridge)
        self.webItinerary.page().setWebChannel(channel)

        # a long itinerary easily exceeds setHtml's 2MB limit, so load from disk
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False,
                                         encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        self.webItinerary.setUrl(QUrl.fromLocalFile(tmp_path))


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
        

    def pdfFooter(self):
        """Left-hand footer text stamped on every printed page.

        MainWindow's print/PDF routines look for this method; a window that
        defines it gets page furniture, one that doesn't prints as before.
        """
        return (f"Yearbirder {self.mdiParent.versionNumber}"
                f"  ·  Big Report generated "
                f"{_fmtReportDate(datetime.now())}")


    def _pdfBand(self, title, note="", pageBreak=False):
        """A full-width section header: dark band, title left, count right."""
        html = ""
        if pageBreak:
            # Qt honours page-break-before on a block; putting it on an empty
            # paragraph ahead of the band is the reliable placement.
            html += "<p style='page-break-before:always'></p>"
        return html + (
            f"<table width='100%' cellspacing='0' cellpadding='5' bgcolor='{_PDF_BAND}'>"
            f"<tr><td><span class='band'>{escape(title)}</span></td>"
            f"<td align='right'><span class='bandnote'>{escape(note)}</span></td>"
            "</tr></table><p></p>"
            )


    def _pdfSubBand(self, title, note=""):
        """A lighter band, for one date or one location inside a section."""
        return (
            f"<table width='100%' cellspacing='0' cellpadding='3' bgcolor='{_PDF_SUBBAND}'>"
            f"<tr><td><span class='sub'>{escape(title)}</span></td>"
            f"<td align='right'><span class='note'>{escape(note)}</span></td>"
            "</tr></table>"
            )


    def _pdfGrid(self, entries, columns=3):
        """Lay a list of names out in a striped, multi-column table."""
        if not entries:
            return "<p class='none'>None</p>"
        width = int(100 / columns)
        rows = []
        for start in range(0, len(entries), columns):
            chunk = entries[start:start + columns]
            fill = _PDF_ZEBRA if (start // columns) % 2 else _PDF_WHITE
            cells = "".join(
                f"<td width='{width}%' bgcolor='{fill}'>{escape(e)}</td>" for e in chunk)
            cells += f"<td bgcolor='{fill}'></td>" * (columns - len(chunk))
            rows.append(f"<tr>{cells}</tr>")
        return ("<table width='100%' cellspacing='0' cellpadding='4'>" +
                "".join(rows) + "</table>")


    def _pdfCountGrid(self, entries, columns=3):
        """Species and their counts, in striped columns — name left, count right.

        Each column is really a name/count pair of cells so the numbers line up
        down the page instead of trailing their names.
        """
        if not entries:
            return "<p class='none'>None</p>"
        nameWidth = int(88 / columns)
        countWidth = int(12 / columns)
        rows = []
        for start in range(0, len(entries), columns):
            chunk = entries[start:start + columns]
            fill = _PDF_ZEBRA if (start // columns) % 2 else _PDF_WHITE
            cells = "".join(
                f"<td width='{nameWidth}%' bgcolor='{fill}'>{escape(name)}</td>"
                f"<td width='{countWidth}%' bgcolor='{fill}' align='right'>{escape(count)}</td>"
                for name, count in chunk
                )
            cells += f"<td bgcolor='{fill}'></td><td bgcolor='{fill}'></td>" * (
                columns - len(chunk))
            rows.append(f"<tr>{cells}</tr>")
        return ("<table width='100%' cellspacing='0' cellpadding='4'>" +
                "".join(rows) + "</table>")


    def _pdfItinerary(self, stops):
        """The Itinerary tab's content, rendered for print."""
        if not stops:
            return "<p class='none'>No checklists match this filter.</p>"

        stopsByDate = defaultdict(list)
        for stop in stops:
            stopsByDate[stop["date"]].append(stop)

        html = []
        currentDate = None
        for stop in stops:
            if stop["date"] != currentDate:
                currentDate = stop["date"]
                html.append("<p></p>")
                html.append(self._pdfSubBand(
                    _fmtItineraryDate(currentDate),
                    _itineraryDaySummary(stopsByDate[currentDate])))
            else:
                # separate consecutive stops; the day band already does this
                # for the first stop under it
                html.append("<p></p>")

            heading = stop["location"]
            time = _fmtItineraryTime(stop["time"])
            if time:
                heading += "  ·  " + time
            if stop["region"]:
                heading += "  ·  " + stop["region"]

            meta = _itineraryStopMeta(stop)
            if stop["checklistID"]:
                meta.append(stop["checklistID"])

            html.append(
                "<table width='100%' cellspacing='0' cellpadding='2'>"
                f"<tr><td><span class='stop'>{escape(heading)}</span></td></tr>"
                f"<tr><td><span class='note'>{escape('  ·  '.join(meta))}</span></td></tr>"
                + (f"<tr><td><span class='comment'>{escape(stop['comments'])}"
                   "</span></td></tr>" if stop["comments"] else "")
                + "</table>"
                )
            html.append(self._pdfCountGrid(
                [(e["name"], _itinerarySpeciesCount(e)) for e in stop["species"]]))

        return "".join(html)


    def _pdfPairTable(self, pairs, secondHeader):
        """Two columns — species and the year/region/location it was new for."""
        if not pairs:
            return "<p class='none'>None</p>"
        rows = [
            f"<tr bgcolor='{_PDF_SUBBAND}'>"
            "<th align='left' width='55%'>Species</th>"
            f"<th align='left'>{escape(secondHeader)}</th></tr>"
            ]
        for n, (species, other) in enumerate(pairs):
            fill = _PDF_ZEBRA if n % 2 else _PDF_WHITE
            rows.append(
                f"<tr><td bgcolor='{fill}'>{escape(species)}</td>"
                f"<td bgcolor='{fill}'>{escape(other)}</td></tr>"
                )
        return ("<table width='100%' cellspacing='0' cellpadding='4'>" +
                "".join(rows) + "</table>")


    def _pdfPairsFromTable(self, table):
        """Read a "new for ..." table widget into (species, context) pairs."""
        pairs = []
        for r in range(table.rowCount()):
            if table.item(r, 1) is None or table.item(r, 0) is None:
                continue
            pairs.append((table.item(r, 1).text(), table.item(r, 0).text()))
        return pairs


    def _waitMs(self, milliseconds):
        """Let the event loop run for a while — the compositor needs real time."""
        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()


    def _runMapJs(self, script, timeoutMs=2000):
        """Run script in the map page and return its result synchronously."""
        result = []
        loop = QEventLoop()

        def done(value):
            result.append(value)
            loop.quit()

        self.webMap.page().runJavaScript(script, done)
        QTimer.singleShot(timeoutMs, loop.quit)
        loop.exec()
        return result[0] if result else None


    def _waitForTiles(self, timeoutMs=8000):
        """Block until every visible map tile has loaded, or we give up.

        Leaflet tags each tile 'leaflet-tile-loaded' as it arrives, so the two
        counts converging means the map is whole.  Returns False on timeout —
        the caller still grabs, since a partly drawn map beats no map at all.
        """
        waited = 0
        while waited < timeoutMs:
            loaded = self._runMapJs(
                "(function(){"
                "  var all = document.querySelectorAll('.leaflet-tile').length;"
                "  var done = document.querySelectorAll('.leaflet-tile-loaded').length;"
                "  return all > 0 && all === done;"
                "})()")
            if loaded:
                return True
            self._waitMs(150)
            waited += 150
        return False


    def _pdfMapImage(self):
        """Grab the Map tab and return it as an inline <img>, or "" on failure."""
        # Switch to the map tab so the renderer has a real viewport, then wait
        # for the tiles: grabbing on a fixed short delay caught them mid-load
        # and printed a patchwork of blank squares.
        previousTab = self.tabAnalysis.currentIndex()
        self.tabAnalysis.setCurrentIndex(self.tabAnalysis.indexOf(self.tabMap))
        self._waitMs(300)
        self._waitForTiles()

        # Leaflet's zoom control and the Satellite / Reset / Full Screen
        # buttons are page furniture, not data — hide them for the grab.  The
        # attribution stays: the tile provider requires it.
        self._runMapJs(
            "document.querySelectorAll('.leaflet-control').forEach(function(el){"
            "  if (!el.classList.contains('leaflet-control-attribution'))"
            "    el.style.visibility = 'hidden';"
            "});")

        # even with every tile loaded, Leaflet fades them in and the GPU
        # compositor is async, so let the view settle before grabbing
        self._waitMs(500)
        myPixmap = self.webMap.grab()

        self._runMapJs(
            "document.querySelectorAll('.leaflet-control').forEach(function(el){"
            "  el.style.visibility = '';"
            "});")
        self.tabAnalysis.setCurrentIndex(previousTab)
        if myPixmap.isNull():
            return ""

        myPixmap = myPixmap.scaledToWidth(600, Qt.SmoothTransformation)
        myByteArray = QByteArray()
        myBuffer = QBuffer(myByteArray)
        myBuffer.open(QIODevice.OpenModeFlag.WriteOnly)
        myPixmap.save(myBuffer, "PNG")
        encoded = base64.b64encode(bytes(myByteArray)).decode("ascii")

        return (
            # image and caption share one cell so they centre on the same axis
            "<table width='100%' cellspacing='0' cellpadding='0'>"
            "<tr><td align='center'>"
            f"<img src='data:image/png;base64,{encoded}' width='600' /><br />"
            "<span class='note'>"
            "Locations visited, numbered in the order they were first birded"
            # the in-map attribution does not survive the widget grab, and the
            # tile provider's credit has to appear somewhere on the page
            f"  ·  {escape(code_Basemap.TILE_ATTR)}"
            "</span></td></tr></table>"
            )


    def html(self):

        # Ensure all lazy-loaded tabs are populated before generating the PDF.
        if not self.newDatesLoaded:
            self._fillNewDates()
            self.newDatesLoaded = True
        if not self.newRegionsLoaded:
            self._fillNewRegions()
            self.newRegionsLoaded = True
        if not self.newLocationsLoaded:
            self._fillNewLocations()
            self.newLocationsLoaded = True

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        db = self.mdiParent.db
        speciesCount   = db.CountSpecies(self.speciesList)
        taxaCount      = self.tblSpecies.rowCount() - speciesCount
        locationCount  = self.lstLocations.count()
        dateCount      = self.lstDates.count()
        checklistCount = len({s["checklistID"] for s in self.filteredSightingList})

        html = f"""<!DOCTYPE html>
<html>
<head>
<style>
body {{ font-family: Helvetica, Arial, sans-serif; font-size: 9pt; color: {_PDF_INK}; }}
p, td, th, li {{ font-family: Helvetica, Arial, sans-serif; font-size: 9pt; color: {_PDF_INK}; }}
th {{ text-align: left; font-weight: bold; }}
.title {{ font-size: 20pt; font-weight: bold; color: {_PDF_INK}; }}
.subtitle {{ font-size: 11pt; color: {_PDF_MUTED}; }}
.band {{ font-size: 12pt; font-weight: bold; color: {_PDF_BAND_FG}; }}
.bandnote {{ font-size: 9pt; color: {_PDF_BAND_NOTE}; }}
.sub {{ font-size: 10pt; font-weight: bold; color: {_PDF_INK}; }}
.stop {{ font-size: 9.5pt; font-weight: bold; color: {_PDF_INK}; }}
.comment {{ font-size: 8.5pt; font-style: italic; color: {_PDF_INK}; }}
.note {{ font-size: 8pt; color: {_PDF_MUTED}; }}
.stat {{ font-size: 17pt; font-weight: bold; color: {_PDF_BAND}; }}
.statlabel {{ font-size: 8pt; color: {_PDF_MUTED}; }}
.none {{ font-size: 9pt; color: {_PDF_MUTED}; }}
</style>
</head>
<body>
"""

        # ---- title block ----
        html += f"<p class='title'>{escape(self.lblLocation.text())}</p>"
        if self.lblDateRange.text():
            html += f"<p class='subtitle'>{escape(self.lblDateRange.text())}</p>"
        if self.lblDetails.text():
            html += f"<p class='subtitle'>{escape(self.lblDetails.text())}</p>"

        # A coloured rule: QTextDocument gives <hr> no colour, but a one-cell
        # table filled with the accent does the same job.
        html += ("<p></p>"
                 f"<table width='100%' cellspacing='0' cellpadding='0' "
                 f"bgcolor='{code_Stylesheet.CHART_PRIMARY}'>"
                 "<tr><td style='font-size:2pt'>&nbsp;</td></tr></table>")

        # ---- summary strip ----
        stats = [(f"{speciesCount:,}", "Species")]
        if taxaCount > 0:
            stats.append((f"{taxaCount:,}", "Other Taxa"))
        stats.extend([
            (f"{checklistCount:,}", "Checklists"),
            (f"{locationCount:,}",  "Locations"),
            (f"{dateCount:,}",      "Dates"),
            ])
        cells = "".join(
            f"<td width='{int(100 / len(stats))}%' align='center' bgcolor='{_PDF_SUBBAND}'>"
            f"<span class='stat'>{value}</span><br />"
            f"<span class='statlabel'>{label}</span></td>"
            for value, label in stats
            )
        html += ("<p></p><table width='100%' cellspacing='4' cellpadding='8'>"
                 f"<tr>{cells}</tr></table><p></p>")

        # ---- map ----
        html += self._pdfMapImage()

        # ---- itinerary ----
        # First section after the map: the trip in order, before the analysis
        # sections slice the same sightings by species, date, and location.
        stops = self._buildItineraryStops()
        html += self._pdfBand(
            "Itinerary",
            f"{len(stops):,} checklist{'' if len(stops) == 1 else 's'}",
            pageBreak=True)
        html += self._pdfItinerary(stops)

        # ---- species ----
        note = f"{speciesCount:,} species"
        if taxaCount > 0:
            note += f" + {taxaCount:,} other taxa"
        html += self._pdfBand("Species", note, pageBreak=True)
        html += (f"<table width='100%' cellspacing='0' cellpadding='4'>"
                 f"<tr bgcolor='{_PDF_SUBBAND}'>"
                 "<th align='right' width='6%'>#</th>"
                 "<th width='46%'>Species</th>"
                 "<th align='right' width='12%'>Count</th>"
                 "<th width='18%'>First</th>"
                 "<th width='18%'>Last</th></tr>")
        def cell(row, column, fill, align="left"):
            item = self.tblSpecies.item(row, column)
            text = escape(item.text()) if item is not None else ""
            return f"<td bgcolor='{fill}' align='{align}'>{text}</td>"

        for r in range(self.tblSpecies.rowCount()):
            fill = _PDF_ZEBRA if r % 2 else _PDF_WHITE
            html += ("<tr>" +
                     cell(r, 0, fill, "right") +
                     cell(r, 1, fill) +
                     cell(r, 2, fill, "right") +
                     cell(r, 3, fill) +
                     cell(r, 4, fill) +
                     "</tr>")
        html += "</table>"

        # ---- dates ----
        html += self._pdfBand(
            "Dates", f"{dateCount:,} date{'' if dateCount == 1 else 's'}", pageBreak=True)
        for r in range(self.lstDates.count()):
            date = self.lstDates.item(r).text()

            # create filter set to our current date
            filter = deepcopy(self.filter)
            filter.setStartDate(date)
            filter.setEndDate(date)
            species = db.GetSpecies(filter)

            html += self._pdfSubBand(
                _fmtItineraryDate(date),
                f"{len(species)} species")
            html += self._pdfGrid(species)
            html += "<p></p>"

        # ---- locations ----
        html += self._pdfBand(
            "Locations",
            f"{locationCount:,} location{'' if locationCount == 1 else 's'}",
            pageBreak=True)
        html += ("<p class='note'>An asterisk marks a species seen only at "
                 "that location.</p><p></p>")
        for r in range(self.lstLocations.count()):
            location = self.lstLocations.item(r).text()

            # create filter set to our current location
            filter = deepcopy(self.filter)
            filter.setLocationType("Location")
            filter.setLocationName(location)
            species = db.GetSpecies(filter)

            uniqueSpecies = db.GetUniqueSpeciesForLocation(
                self.filter,
                location,
                species,
                self.filteredSightingList
                )

            html += self._pdfSubBand(location, f"{len(species)} species")
            html += self._pdfGrid(
                [s + "*" if s in uniqueSpecies else s for s in species])
            html += "<p></p>"

        # ---- firsts ----
        newLife = [self.lstNewLifeSpecies.item(r).text()
                   for r in range(self.lstNewLifeSpecies.count())]
        html += self._pdfBand(
            "New Life Species",
            f"{len(newLife):,} species" if newLife else "none",
            pageBreak=True)
        html += self._pdfGrid(newLife)

        for title, table, column in (
                ("New Year Species",     self.tblNewYearSpecies,     "Year"),
                ("New Month Species",    self.tblNewMonthSpecies,    "Month"),
                ("New Country Species",  self.tblNewCountrySpecies,  "Country"),
                ("New State Species",    self.tblNewStateSpecies,    "State"),
                ("New County Species",   self.tblNewCountySpecies,   "County"),
                ("New Location Species", self.tblNewLocationSpecies, "Location"),
                ):
            pairs = self._pdfPairsFromTable(table)
            html += "<p></p>" + self._pdfBand(
                title, f"{len(pairs):,} species" if pairs else "none")
            html += self._pdfPairTable(pairs, column)

        html += "</body></html>"

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
                w.setFont(QFont(YBFont, fontSize))
            except:
                pass 

        self.lblLocation.setFont(QFont(YBFont, floor(fontSize * 1.4 )))
        self.lblLocation.setStyleSheet("QLabel { font: bold }");
        self.lblDateRange.setFont(QFont(YBFont, floor(fontSize * 1.2 )))
        self.lblDateRange.setStyleSheet("QLabel { font: bold }");
        self.lblDetails.setFont(QFont(YBFont, floor(fontSize * 1.2 )))
        self.lblDetails.setStyleSheet("QLabel { font: bold }");

        metrics = QFontMetrics(QFont(YBFont, fontSize))
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
        #find the width of the widest integer in the Tax column, but use a minimum if needed        
        taxText = str(self.tblSpecies.rowCount())
        taxTextWidth = int(metrics.boundingRect(taxText).width())
        if taxTextWidth < int(metrics.boundingRect("Tax").width()) * 1.5:
            taxTextWidth = int(metrics.boundingRect("Tax").width()) * 1.5
        dateWidth = int(metrics.boundingRect("2222-22-22").width())
        header = self.tblSpecies.horizontalHeader()
        header.resizeSection(0,  floor(2.5* taxTextWidth))
        header.resizeSection(2,  floor(1.5* dateWidth))
        header.resizeSection(3,  floor(1.5 * dateWidth))
        self.tblSpecies.verticalHeader().setDefaultSectionSize(rowHeight)

        # format tblNewLocationSpecies, which needs wider location column
        header = self.tblNewLocationSpecies.horizontalHeader()
        header.resizeSection(0,  floor(8 * textWidth))
        self.tblNewLocationSpecies.verticalHeader().setDefaultSectionSize(rowHeight)



