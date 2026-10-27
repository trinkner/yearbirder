# import the GUI forms that we create with Qt Creator
import form_Individual
from code_Stylesheet import YBFont
import code_Filter 
import code_Lists 
import code_Location 
import code_Web
import code_Photos
import code_Recordings
import code_Stylesheet
import code_DataBase

# import the Qt components we'll use
# do this so later we won't have to clutter our code with references to parent Qt classes 

from PySide6.QtGui import (
    QAction,
    QCursor,
    QFont,
    QFontMetrics,
    QImageReader,
    QPixmap,
    )

from PySide6.QtCore import (
    Qt,
    QSize,
    QTimer,
    Signal,
    QUrl,
    )

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QTableWidgetItem,
    QHeaderView,
    QMdiSubWindow,
    QMenu,
    QTreeWidgetItem,
    QPushButton,
    QMessageBox
    )

from math import floor


class Individual(QMdiSubWindow, form_Individual.Ui_frmIndividual):

    # create "resized" as a signal that the window can emit
    # we respond to this signal with the form's resizeMe method below
    resized = Signal()
   
   
    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose,True)
        self.mdiParent = ""
        self._photoPixmap = None
        self._species = ""
        self._btnPhotos = None
        self._btnRecordings = None
        self._mediaState = None
        self.resized.connect(self.resizeMe)                    
        self.trLocations.currentItemChanged.connect(self.FillDates)
        self.trLocations.itemDoubleClicked.connect(self.CreateLocation)
        self.trDates.currentItemChanged.connect(lambda: self.FillLocations(self.trDates))
        self.trDates.itemDoubleClicked.connect(lambda: self.FillLocations(self.trDates))   
        self.trMonthDates.currentItemChanged.connect(lambda: self.FillLocations(self.trMonthDates))           
        self.lstDates.itemDoubleClicked.connect(lambda: self.CreateSpeciesList(self.lstDates))   
        self.tblYearLocations.itemDoubleClicked.connect(lambda: self.CreateSpeciesList(self.tblYearLocations))
        self.tblMonthLocations.itemDoubleClicked.connect(lambda: self.CreateSpeciesList(self.tblMonthLocations))
        self.buttonWikipedia.clicked.connect(self.CreateWebPageForWikipedia)
        self.buttonAllAboutBirds.clicked.connect(self.CreateWebPageForAllAboutBirds)
        self.buttonAudubon.clicked.connect(self.CreateWebPageForAudubon)

        # Birds of the World sits under All About Birds, its Cornell sibling.
        self.buttonBirdsOfTheWorld = QPushButton("Birds of the World", self.frameButtons)
        self.buttonBirdsOfTheWorld.setSizePolicy(self.buttonAllAboutBirds.sizePolicy())
        self.buttonBirdsOfTheWorld.setObjectName("buttonBirdsOfTheWorld")
        self.buttonBirdsOfTheWorld.clicked.connect(self.CreateWebPageForBirdsOfTheWorld)
        self.verticalLayout_10.insertWidget(
            self.verticalLayout_10.indexOf(self.buttonAllAboutBirds) + 1,
            self.buttonBirdsOfTheWorld)

        # IUCN Red List under it: the authority behind the status badge, and
        # the only answer for species AviList gives no status (Not Available).
        self.buttonIUCN = QPushButton("IUCN Red List", self.frameButtons)
        self.buttonIUCN.setSizePolicy(self.buttonAllAboutBirds.sizePolicy())
        self.buttonIUCN.setObjectName("buttonIUCN")
        self.buttonIUCN.clicked.connect(self.CreateWebPageForIUCN)
        self.verticalLayout_10.insertWidget(
            self.verticalLayout_10.indexOf(self.buttonBirdsOfTheWorld) + 1,
            self.buttonIUCN)

        # IUCN conservation status (AviList), under the order and family.
        self.lblConservationStatus = QLabel(self.frameNames)
        self.verticalLayout_3.insertWidget(
            self.verticalLayout_3.indexOf(self.lblOrderName) + 1,
            self.lblConservationStatus)
        self.buttonMap.clicked.connect(self.CreateMap)
        self.buttonChecklists.clicked.connect(self.CreateChecklists)

        # Right-click a date in the By Location dates list to set the main
        # filter to it, as the dates lists in Date Totals and Trip Report do.
        # A right-click makes the clicked row current before the menu opens,
        # so the action reads currentItem().
        self.actionSetDateFilter = QAction("Set Filter to Date", self)
        self.actionSetDateFilter.triggered.connect(self.setDateFilter)
        self.lstDates.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.lstDates.addAction(self.actionSetDateFilter)

        # Right-click any level of the By Location tree — country, state,
        # county or location — to set the main filter to it.  Built per click
        # because the entry's wording depends on the level clicked.
        self.trLocations.setContextMenuPolicy(Qt.CustomContextMenu)
        self.trLocations.customContextMenuRequested.connect(
            self._showLocationTreeMenu)
        self.tabIndividual.setCurrentIndex(0)

        # Match every data pane in the three tabs to the app's table surface
        # (code_Stylesheet.tableColor).  The global stylesheet only covers
        # QTableWidget, so the By Year/By Month Locations tables already look
        # right; the tree views (no global rule → base window color) and the
        # dates QListWidget (global rule uses the base color) are overridden
        # here, scoped to this window so the ChecklistTree dialog's tree keeps
        # its current look.
        def _paneSheet(widgetSelector):
            return (
                "%(w)s { background: %(bg)s; border: 1px solid #3a3d4e;"
                " border-radius: 4px; }"
                " %(w)s::item:selected { background: #4f8ef7; color: white; }"
                " %(w)s::item:hover { background: #363a4f; }"
                % {"w": widgetSelector, "bg": code_Stylesheet.tableColor})
        for _tree in (self.trLocations, self.trDates, self.trMonthDates):
            _tree.setStyleSheet(_paneSheet("QTreeWidget"))
        self.lstDates.setStyleSheet(_paneSheet("QListWidget"))

 
    def FillIndividual(self, Species): 
        
        self.setWindowTitle(Species)
        self.lblCommonName.setText(Species)
        
        red = code_Stylesheet.speciesColor.red()
        green = code_Stylesheet.speciesColor.green()
        blue = code_Stylesheet.speciesColor.blue()
        self.lblCommonName.setStyleSheet('QLabel {font-weight: bold; color: rgb(' + str(red) + ',' + str(green) + ',' + str(blue) + ');}')
        self.lblScientificName.setText(self.mdiParent.db.GetScientificName(Species))
        orderAndFamilyText = self.mdiParent.db.GetOrderName(Species)
        
        # check if taxonomy data has been loaded. If so, add a semi-colon and the family name
        if orderAndFamilyText != "":
            orderAndFamilyText = orderAndFamilyText + "; " + self.mdiParent.db.GetFamilyName(Species)
        self.lblOrderName.setText(orderAndFamilyText)

        statusCode, statusName = self.mdiParent.db.GetConservationStatus(Species)
        self.lblConservationStatus.setText(
            "Conservation Status (AviList " + code_DataBase.AVILIST_YEAR + "): " + statusName)
        
        # if available, add BBL banding code
        bblCode = self.mdiParent.db.GetBBLCode(Species)
        if bblCode != "":
            self.lblSpeciesCode.setText("IBP Banding Code: " + bblCode)
        else:
            # add species Quick Entry Code code used by eBird
            self.lblSpeciesCode.setText("eBird Entry Code: " + self.mdiParent.db.GetQuickEntryCode(Species).upper())

        # hide nonapplicable web buttons and info for spuh, hybrid and uncertain sightings
        if "sp." in Species or "/" in Species or " x " in Species:
            self.buttonWikipedia.hide()
            self.buttonAllAboutBirds.hide()
            self.buttonAudubon.hide()
            self.buttonBirdsOfTheWorld.hide()
            self.buttonIUCN.hide()
            self.lblScientificName.hide()
            self.lblSpeciesCode.hide()

                
        # find list of dates for species, to find oldest and newest
        filter = code_Filter.Filter()
        filter.setSpeciesName(Species)
        dbDates = self.mdiParent.db.GetDates(filter)
        firstDate = dbDates[0]
        lastDate = dbDates[len(dbDates)-1]
        
        # create filter to find the first location seen
        filter = code_Filter.Filter()
        filter.setStartDate(firstDate)
        filter.setEndDate(firstDate)
        filter.setSpeciesName(Species)
        firstDateLocations = self.mdiParent.db.GetLocations(filter, "Checklist")
        firstDateLocations =  sorted(firstDateLocations, key=lambda x: (x[3]))
        firstLocation = firstDateLocations[0][0]
        
        # create filter to find the last location seen
        filter = code_Filter.Filter()
        filter.setStartDate(lastDate)
        filter.setEndDate(lastDate)
        filter.setSpeciesName(Species)
        lastDateLocations = self.mdiParent.db.GetLocations(filter, "Checklist")
        lastDateLocations =  sorted(lastDateLocations, key=lambda x: (x[3]))
        lastLocation = lastDateLocations[len(lastDateLocations) - 1][0]
        
        self.lblFirstSeen.setText(
            "First seen: " 
            + dbDates[0] 
            + " at " 
            + firstLocation
            )
                                                       
        self.lblMostRecentlySeen.setText(
            "Last seen: " 
            + dbDates[len(dbDates ) - 1] 
            + " at " 
            + lastLocation
            )
            
        # display all locations for the species
        filter = code_Filter.Filter()
        filter.setSpeciesName(Species)
        locationList = self.mdiParent.db.GetLocations(filter,  "LocationHierarchy")
        dateList = self.mdiParent.db.GetDates(filter)

        # fill treeview Locations widget
        self.trLocations.setColumnCount(1)
        theseCountries = set()
        
        sortedLocationList = sorted(locationList, key=lambda x: (x[0], x[1], x[2]))
        
        # add the top-level country tree items
        for l in sortedLocationList:
            theseCountries.add(l[0][0:2])
        
        locationCount = 0
        theseCountries = list(theseCountries)
        theseCountries.sort()
        
        for c in theseCountries:
            thisCountryItem = QTreeWidgetItem()
            thisCountry = self.mdiParent.db.GetCountryName(c)
            thisCountryItem.setText(0,  thisCountry)   
            self.trLocations.addTopLevelItem(thisCountryItem)
            thisCountryItem.setSizeHint(0,  QSize(20,  20))
            
            theseStates = set()
            for l in sortedLocationList:
                if l[0][0:2] == c:
                    theseStates.add(l[0])
            theseStates = list(theseStates)
            theseStates.sort()
            
            for s in theseStates:
                thisState = self.mdiParent.db.GetStateName(s)
                stateTreeItem = QTreeWidgetItem()
                stateTreeItem.setText(0, thisState)
                thisCountryItem.addChild(stateTreeItem)
                stateTreeItem.setSizeHint(0, QSize(20,  20))

                theseCounties = set()
                for l in sortedLocationList:
                    if l[0] == s:
                        theseCounties.add(l[1])
                theseCounties = list(theseCounties)
                theseCounties.sort()
                
                for co in theseCounties:
                    countyTreeItem= QTreeWidgetItem()                    
                    if co == "":
                        countyTreeItem.setText(0, "No County Name")
                    else:
                        countyTreeItem.setText(0, co)                    
                    stateTreeItem.addChild(countyTreeItem)
                    countyTreeItem.setSizeHint(0, QSize(20,  20))
        
                    theseLocations= []
                    for l in sortedLocationList:
                        if l[0] == s and l[1] == co:
                            theseLocations.append(l[2])
                    theseLocations.sort()
                    
                    for lo in theseLocations:
                        locationTreeItem = QTreeWidgetItem()
                        locationTreeItem.setText(0, lo)
                        countyTreeItem.addChild(locationTreeItem)
                        locationTreeItem.setSizeHint(0, QSize(20,  20))                        
                        
                    locationCount = locationCount + len(theseLocations)
        
        # Fill Year Tree widget        
        theseYears = set()
        for d in dateList:
            theseYears.add(d[0:4])
        
        theseYears = list(theseYears)
        theseYears.sort()
        # Counted here rather than at the label: theseYears is reused as a
        # working set inside the By Month loop below, so by then it no longer
        # holds this species' years.
        yearCount = len(theseYears)
        
        dateCount = 0
        for y in theseYears:
            thisYearItem = QTreeWidgetItem()
            thisYearItem.setText(0, str(y))   
            self.trDates.addTopLevelItem(thisYearItem)
            thisYearItem.setSizeHint(0, QSize(20,  20))
            
            theseMonths = set()
            for d in dateList:
                if y == d[0:4]:
                    theseMonths.add(d[5:7])
            
            theseMonths = list(theseMonths)
            theseMonths.sort()
            
            for m in theseMonths:
                monthName = self.mdiParent.db.GetMonthName(m)
                monthTreeItem = QTreeWidgetItem()
                monthTreeItem.setText(0, str(monthName))
                thisYearItem.addChild(monthTreeItem)
                monthTreeItem.setSizeHint(0, QSize(20,  20))

                theseDates = set()
                for da in dateList:
                    if da[0:4] == y:
                        if da[5:7] == m:
                            theseDates.add(da)
                                
                theseDates = list(theseDates)
                theseDates.sort()
                
                for td in theseDates:
                    dateTreeItem= QTreeWidgetItem()                    
                    dateTreeItem.setText(0, str(td))                    
                    monthTreeItem.addChild(dateTreeItem)
                    dateTreeItem.setSizeHint(0, QSize(20,  20))                       

                dateCount = dateCount + len(theseDates)

        # Fill Month Tree widget
        theseMonths = []
        
        theseMonths = set()
        for d in dateList:
            theseMonths.add(d[5:7])
        
        theseMonths = list(theseMonths)
        theseMonths.sort()
        monthCount = len(theseMonths)
        
        dateCount = 0
        for m in theseMonths:
            monthName = self.mdiParent.db.GetMonthName(m)
            thisMonthItem = QTreeWidgetItem()
            thisMonthItem.setText(0, monthName)   
            self.trMonthDates.addTopLevelItem(thisMonthItem)
            thisMonthItem.setSizeHint(0, QSize(20,  20))
            
            theseYears = set()
            for d in dateList:
                if m == d[5:7]:
                    theseYears.add(d[0:4])
            
            theseYears = list(theseYears)
            theseYears.sort()
            
            for y in theseYears:
                yearTreeItem = QTreeWidgetItem()
                yearTreeItem.setText(0, y)
                thisMonthItem.addChild(yearTreeItem)
                yearTreeItem.setSizeHint(0, QSize(20,  20))

                theseDates = set()
                for da in dateList:
                    if da[0:4] == y:
                        if da[5:7] == m:
                            theseDates.add(da)
                                
                theseDates = list(theseDates)
                theseDates.sort()
                
                for td in theseDates:
                    dateTreeItem= QTreeWidgetItem()                    
                    dateTreeItem.setText(0, str(td))                    
                    yearTreeItem.addChild(dateTreeItem)
                    dateTreeItem.setSizeHint(0, QSize(20,  20))                       

                dateCount = dateCount + len(theseDates)

        self.lblLocations.setText("Locations: " + str(locationCount))
        self.lblDates.setText("Years: " + str(yearCount))
        self.lblMonthDates.setText("Months: " + str(monthCount))
            
        self._species = Species
        self._fillMedia()

        self.scaleMe()
        self.resizeMe()
        # Defer one tick so Qt has completed the first layout pass before scaling
        QTimer.singleShot(0, self._updatePhotoThumb)            

        
    def _mediaFor(self):
        """(best photo file or None, has photos, has recordings) for this
        species — everything the header's media pane and buttons depend on."""
        filter = code_Filter.Filter()
        filter.setSpeciesName(self._species)
        photoSightings = self.mdiParent.db.GetSightingsWithPhotos(filter)
        # Find the highest-rated photo across all sightings
        best_rating = -1.0
        best_file = None
        for s in photoSightings:
            for p in s["photos"]:
                try:
                    rating = float(p["rating"]) if p["rating"] else 0.0
                except (ValueError, TypeError):
                    rating = 0.0
                if rating > best_rating:
                    best_rating = rating
                    best_file = p["fileName"]
        has_recordings = bool(self.mdiParent.db.GetSightingsWithRecordings(filter))
        return (best_file, bool(photoSightings), has_recordings)

    def _fillMedia(self):
        """Load the best-rated photo into the center pane and add the Photos
        and Recordings buttons this species has media for."""
        state = self._mediaFor()
        self._mediaState = state
        best_file, has_photos, has_recordings = state

        if best_file:
            reader = QImageReader(best_file)
            reader.setAutoTransform(True)
            imgSize = reader.size()
            if imgSize.isValid():
                # Load at a generous cap — _updatePhotoThumb scales to fit the pane
                imgSize.scale(QSize(800, 600), Qt.KeepAspectRatio)
                reader.setScaledSize(imgSize)
            pm = QPixmap.fromImage(reader.read())
            if not pm.isNull():
                self._photoPixmap = pm
                self.framePhoto.setVisible(True)
                self.lblPhotoThumb.setCursor(Qt.PointingHandCursor)
                self.lblPhotoThumb.mousePressEvent = lambda _e: self.createPhotos()

        if has_photos:
            self._btnPhotos = QPushButton()
            self._btnPhotos.setText("Photos")
            self._btnPhotos.clicked.connect(self.createPhotos)
            self.verticalLayout_10.addWidget(self._btnPhotos)

        if has_recordings:
            self._btnRecordings = QPushButton()
            self._btnRecordings.setText("Recordings")
            self._btnRecordings.clicked.connect(self.createRecordings)
            self.verticalLayout_10.addWidget(self._btnRecordings)

    def refreshMedia(self):
        """Bring the photo pane and media buttons up to date after a catalog
        change — called by MainWindow.notifyMediaChanged.

        FillIndividual builds them once, so a window opened before the
        species had any photos never showed one after photos were added (and
        kept showing a photo, or a Photos button, after the last was removed).
        Only the media part is rebuilt: re-running FillIndividual would add
        duplicate buttons and snap the window back to its default size.
        """
        if not self._species:
            return
        if self._mediaFor() == self._mediaState:
            return

        for btn in (self._btnPhotos, self._btnRecordings):
            if btn is not None:
                self.verticalLayout_10.removeWidget(btn)
                btn.deleteLater()
        self._btnPhotos = None
        self._btnRecordings = None
        self._photoPixmap = None
        self.lblPhotoThumb.clear()
        self.lblPhotoThumb.unsetCursor()
        self.lblPhotoThumb.mousePressEvent = lambda _e: None
        self.framePhoto.setVisible(False)

        self._fillMedia()
        fontSize = self.mdiParent.fontSize
        for btn in (self._btnPhotos, self._btnRecordings):
            if btn is not None:
                btn.setFont(QFont(YBFont, fontSize))
        self._sizeButtonStack()
        QTimer.singleShot(0, self._updatePhotoThumb)

    def FillDates(self):

        currentItem = self.trLocations.currentItem()        
        species = self.lblCommonName.text()
        location = currentItem.text(0)
        self.lstDates.clear()
        
        filter = code_Filter.Filter()
        filter.setSpeciesName(species)
        
        # check if top-level country is currentItem
        if currentItem.parent() is None:
            filter.setLocationType("Country")
            filter.setLocationName(self.mdiParent.db.GetCountryCode(location))

        # check if second-level state is currentItem        
        elif currentItem.parent().parent() is None:
            filter.setLocationType("State")
            filter.setLocationName(self.mdiParent.db.GetStateCode(location))            
            
        # check if third-level county is currentItem
        elif currentItem.parent().parent().parent() is None:
            filter.setLocationType("County") 
            filter.setLocationName(location)            
        
        # check if fourth-level location is currentItem
        else:
            filter.setLocationType("Location")
            filter.setLocationName(location)            
            
        dates = self.mdiParent.db.GetDates(filter)
        
        self.lstDates.addItems(dates)
        self.lstDates.setCurrentRow(0)
        self.lstDates.setSpacing(2)
        self.lblDatesForLocation.setText("Dates for selected location: " + str(self.lstDates.count()))


    def FillLocations(self,  callingWidget):
        
        currentItem = callingWidget.currentItem()
        if currentItem is None:
            return
        
        species = self.lblCommonName.text()
        
        filter = code_Filter.Filter()
        filter.setSpeciesName(species)
        
        if callingWidget.objectName() == "trDates":
            locationWidget = self.tblYearLocations
            
            parent = currentItem.parent()
            
            # check if currentItem is a year
            if parent is None:
                filter.setStartDate(currentItem.text(0) + "-01-01")
                filter.setEndDate(currentItem.text(0) + "-12-31")

            # check if currentItem is a month
            else:
                grandparent = parent.parent()
                if grandparent is None:
                    month = currentItem.text(0)
                    monthNumberString = self.mdiParent.db.monthNumberDict[month]
                    lastDayOfThisMonth = self.mdiParent.db.GetLastDayOfMonth(monthNumberString)
                    year = parent.text(0)
                    filter.setStartDate(year + "-" + monthNumberString + "-01")
                    filter.setEndDate(year + "-" + monthNumberString + "-" + lastDayOfThisMonth)
                
                #currentItem is a date
                else:
                    filter.setStartDate(currentItem.text(0))
                    filter.setEndDate(currentItem.text(0))             

        if callingWidget.objectName() == "trMonthDates":

            locationWidget = self.tblMonthLocations
                        
            # check if currentItem is a month
            if currentItem.parent() is None:
                monthNumberString = self.mdiParent.db.monthNumberDict[currentItem.text(0)]
                lastDayOfThisMonth = self.mdiParent.db.GetLastDayOfMonth(monthNumberString)
                filter.setStartSeasonalMonth(monthNumberString)
                filter.setStartSeasonalDay("01")
                filter.setEndSeasonalMonth(monthNumberString)
                filter.setEndSeasonalDay(lastDayOfThisMonth)
           
            # check if currentItem is a year
            elif currentItem.parent().parent() is None:
                year = currentItem.text(0)
                monthString = currentItem.parent().text(0)
                monthNumberString = self.mdiParent.db.monthNumberDict[monthString]
                filter.setStartDate(year + "-" + monthNumberString + "-01")
                filter.setEndDate(year + "-" + monthNumberString + "-31")
            
            # item is a just a single date
            else:
                filter.setStartDate(currentItem.text(0))
                filter.setEndDate(currentItem.text(0))    
        
        locations = self.mdiParent.db.GetLocations(filter, "Checklist")     
        
        locationWidget.clear()        
        locationWidget.setColumnCount(2)       
        locationWidget.setRowCount(len(locations))        
        locationWidget.horizontalHeader().setVisible(False)
        locationWidget.verticalHeader().setVisible(False)
        header = locationWidget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        locationWidget.setShowGrid(False)

        R = 0
        for l in locations:

            locationItem = QTableWidgetItem()
            locationItem.setText(l[0])

            # store checklist ID in hidden data component of item
            locationItem.setData(Qt.UserRole,  l[2])
            speciesCountItem = QTableWidgetItem()
            speciesCountItem.setData(Qt.DisplayRole, l[1])
            locationWidget.setItem(R, 0, locationItem)
            locationWidget.setItem(R, 1, speciesCountItem)
            R = R + 1
        
        self.lblLocationsForDate.setText("Checklists: " + str(locationWidget.rowCount()))


    @staticmethod
    def _locationLevel(item):
        """"Country", "State", "County" or "Location" for a By Location tree
        item, from its depth (the tree is always built four levels deep)."""
        depth = 0
        parent = item.parent()
        while parent is not None:
            depth += 1
            parent = parent.parent()
        return ("Country", "State", "County", "Location")[min(depth, 3)]

    def _showLocationTreeMenu(self, pos):
        item = self.trLocations.itemAt(pos)
        if item is None:
            return
        self.trLocations.setCurrentItem(item)
        level = self._locationLevel(item)
        name = item.text(0)
        menu = QMenu(self)
        action = menu.addAction(f"Set Filter to {level}")
        # Two tree labels name nothing the filter can select: "No County Name"
        # groups locations without a county, and a bare code such as "GR-" is
        # the "state" eBird gives a checklist entered at country level only.
        if ((level == "County" and name == "No County Name")
                or (level == "State" and name.endswith("-"))):
            action.setEnabled(False)
        chosen = menu.exec(self.trLocations.viewport().mapToGlobal(pos))
        if chosen is not action:
            return
        setter = {
            "Country":  self.mdiParent.setCountryFilter,
            "State":    self.mdiParent.setStateFilter,
            "County":   self.mdiParent.setCountyFilter,
            "Location": self.mdiParent.setLocationFilter,
        }[level]
        setter(name)

    def setDateFilter(self):
        item = self.lstDates.currentItem()
        if item is None:
            return
        self.mdiParent.setDateFilter(item.text())


    def CreateChecklists(self):
        species = self.lblCommonName.text()
        
        filter = code_Filter.Filter()
        filter.setSpeciesName(species)
        
        sub = code_Lists.Lists()
        sub.mdiParent = self.mdiParent
        sub.FillChecklists(filter)  
        sub.lblLocation.setText("Checklists: " + species)
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)
        sub.show()
        sub.scaleMe()


    def CreateLocation(self):
        if self.trLocations.currentItem().childCount() == 0:
            location = self.trLocations.currentItem().text(0)
            sub = code_Location.Location()
            sub.mdiParent = self.mdiParent
            sub.FillLocation(location)
            self.parent().parent().addSubWindow(sub)
            self.mdiParent.PositionChildWindow(sub, self)
            sub.show()
            QApplication.processEvents()
            sub.scaleMe()


    def CreateLocationAndSetDate(self):
        location = self.trLocations.currentItem().text(0)
        date = self.lstDates.currentItem().text()
        sub = code_Location.Location()
        sub.mdiParent = self.mdiParent
        sub.FillLocation(location)
        sub.SetDate(date)
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)
        sub.show()
        QApplication.processEvents()
        sub.scaleMe()
        
        
    def CreateMap(self):
        species = self.lblCommonName.text()
        
        filter = code_Filter.Filter()
        filter.setSpeciesName(species)
        
        sub = code_Web.Web()
        sub.mdiParent = self.mdiParent
        
        sub.LoadLocationsMap(filter)  
        
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)        
        sub.show()   
        

    def CreateSpeciesList(self, callingWidget):

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        filter = code_Filter.Filter()
        filter.setSpeciesName(self.lblCommonName.text())
        
        # Get checklistID(s) and location, depending on the calling widget
        if callingWidget.objectName() in ["tblYearLocations",  "tblMonthLocations"]:
            currentRow = callingWidget.currentRow()
            checklistID = callingWidget.item(currentRow,  0).data(Qt.UserRole)
            filter.setChecklistID(checklistID)
            filter.setLocationType ("Location")
            filter.setLocationName(callingWidget.item(currentRow,  0).text())
            date = self.mdiParent.db.GetDates(filter)[0]
            # even though there is only one checklist here, we need a list to we can
            # loop it later
            checklists = [[checklistID]]

        if callingWidget.objectName() in ["lstDates"]:
            date = str(callingWidget.currentItem().text())
            currentItem = self.trLocations.currentItem()
            locationName = currentItem.text(0)
            #need to get the location type based on the tree hierarchy
            if currentItem.parent() is None:
                filter.setLocationType("Country")
                locationName = self.mdiParent.db.GetCountryCode(locationName)
            elif currentItem.parent().parent() is None:
                filter.setLocationType("State")
                locationName = self.mdiParent.db.GetStateCode(locationName)                
            elif currentItem.parent().parent().parent() is None:
                filter.setLocationType("County")
            else:
                filter.setLocationType("Location")
            
            filter.setLocationName(locationName)
            filter.setStartDate(date)
            filter.setEndDate(date)
                        
            checklists= self.mdiParent.db.GetChecklists(filter)
                    
        for c in checklists:
            cFilter = code_Filter.Filter()
            cFilter.setChecklistID(c[0])
            cLocation = self.mdiParent.db.GetLocations(cFilter,  "OnlyLocations")[0]          
            cFilter.setStartDate(date)
            cFilter.setEndDate(date)
            cFilter.setLocationType("Location")
            cFilter.setLocationName(cLocation)

            sub = code_Lists.Lists()
            sub.mdiParent = self.mdiParent
            sub.FillSpecies(cFilter)
            self.parent().parent().addSubWindow(sub)
            self.mdiParent.PositionChildWindow(sub, self)
            sub.show()
            sub.scaleMe()

        QApplication.restoreOverrideCursor()   


    def CreateWebPageForAllAboutBirds(self):
        
        speciesCommonName = self.lblCommonName.text()

        if "(" in speciesCommonName:
            speciesCommonName = speciesCommonName.split(" (")[0]
            
        speciesCommonName = speciesCommonName.replace(" ",  "_")
        speciesCommonName = speciesCommonName.replace("'",  "")
        
        sub = code_Web.Web()
        sub.mdiParent = self.mdiParent
        sub.title = "All About Birds: " + speciesCommonName        
        url = ("https://www.allaboutbirds.org/guide/"
                  + speciesCommonName
                  + "/id"
                  )
        sub.LoadWebPage(url)        
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)        
        sub.show()   


    def CreateWebPageForAudubon(self):
        speciesCommonName = self.lblCommonName.text()
        
        if "(" in speciesCommonName:
            speciesCommonName = speciesCommonName.split(" (")[0]
            
        speciesCommonName = speciesCommonName.replace(" ",  "-")
        speciesCommonName = speciesCommonName.replace("'",  "")
        
        sub = code_Web.Web()
        sub.mdiParent = self.mdiParent
        sub.title = "Audubon: " + speciesCommonName        
        url = ("http://www.audubon.org/field-guide/bird/"
                  + speciesCommonName                
                  )
        sub.LoadWebPage(url)        
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)        
        sub.show()       


    def CreateWebPageForBirdsOfTheWorld(self):

        speciesCommonName = self.lblCommonName.text()
        url = self.mdiParent.db.GetBirdsOfTheWorldURL(speciesCommonName)
        if not url:
            return

        sub = code_Web.Web()
        sub.mdiParent = self.mdiParent
        sub.title = "Birds of the World: " + speciesCommonName
        sub.LoadWebPage(url)
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)
        sub.show()


    def CreateWebPageForIUCN(self):

        # The species' own Red List page when AviList supplies its IUCN id.
        # Without one (the Not Available species) fall back to IUCN's search
        # on the scientific name, which IUCN shows only to signed-in users;
        # the persistent web profile keeps that sign-in.  The taxonomy's
        # scientific name, not the label's: a species' first sighting can
        # carry a subspecies scientific name.
        speciesCommonName = self.lblCommonName.text()
        taxonID = self.mdiParent.db.GetIUCNTaxonID(speciesCommonName)
        if taxonID:
            url = "https://www.iucnredlist.org/species/" + taxonID
        else:
            sciName = (self.mdiParent.db.sciNameByCommonName.get(speciesCommonName)
                       or self.lblScientificName.text())
            url = ("https://www.iucnredlist.org/search?query="
                   + QUrl.toPercentEncoding(sciName).data().decode()
                   + "&searchType=species")

        sub = code_Web.Web()
        sub.mdiParent = self.mdiParent
        sub.title = "IUCN Red List: " + speciesCommonName
        sub.LoadWebPage(url)
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)
        sub.show()


    def createPhotos(self):

        speciesCommonName = self.lblCommonName.text()

        sub = code_Photos.Photos()
        sub.mdiParent = self.mdiParent

        filter = code_Filter.Filter()
        filter.setSpeciesName(speciesCommonName)
        sub.FillPhotos(filter)

        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)

        sub.show()


    def createRecordings(self):

        speciesCommonName = self.lblCommonName.text()

        sub = code_Recordings.Recordings()
        sub.mdiParent = self.mdiParent

        filter = code_Filter.Filter()
        filter.setSpeciesName(speciesCommonName)

        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)
        sub.FillRecordings(filter)   # fill hidden, then show: see MainWindow._createRecordingsWindow
        sub.show()


    def CreateWebPageForWikipedia(self):
        
        speciesScientificName = self.lblScientificName.text()
        speciesCommonName = self.lblCommonName.text()

        if "(" in speciesCommonName:
            speciesCommonName = speciesCommonName.split(" (")[0]        

        sub = code_Web.Web()
        sub.mdiParent = self.mdiParent
        sub.title = "Wikipedia: " + speciesCommonName        
        url = ("https://en.wikipedia.org/wiki/"
                 + speciesScientificName.split(" ")[0] 
                 +"_" 
                 + speciesScientificName.split(" ")[1]
                 )
        sub.LoadWebPage(url)        
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)        
        sub.show() 


    def html(self):
    
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

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
            table, th, td {
                border-collapse: collapse;
            }
            th, td {
                padding: 5px;
            }
            th {
                text-align: left;
            }
            </style>
            <body>
            """
            
        html = html + (
            "<H1>" + 
            self.lblCommonName.text() + 
            "</H1>"
            )
        
        html = html + (
            "<H2>" + 
            self.lblScientificName.text() + 
            "</H2>"
            )        

        html = html + (
            "<H4>" + 
            self.lblOrderName.text() + 
            "</H4>"
            )               

        html = html + (
            "<H4>" +
            self.lblConservationStatus.text() +
            "</H4>"
            )

        html = html + (
            "<H4>" + 
            self.lblFirstSeen.text() + 
            "</H4>"
            )    
    
        html = html + (
            "<H4>" + 
            self.lblMostRecentlySeen.text() + 
            "</H4>"
            )    
            
        html = html + (
            "<br>" +
            "<H4>" + 
            "Locations"
            "</H4>"
            )    

        html=html + (
            "<font size='2'>"
            )
            
        root = self.trLocations.invisibleRootItem()
        for i in range(root.childCount()):
            for ii in range(root.child(i).childCount()):
                for iii in range(root.child(i).child(ii).childCount()):
                    for iv in range(root.child(i).child(ii).child(iii).childCount()):
                        html = html + (
                            "<b>" + 
                            root.child(i).text(0) + ", " + 
                            root.child(i).child(ii).text(0) + ", " + 
                            root.child(i).child(ii).child(iii).text(0) + ", " + 
                            root.child(i).child(ii).child(iii).child(iv).text(0)
                            )
                            
                        filter = code_Filter.Filter()
                        filter.setSpeciesName = self.lblCommonName.text()
                        filter.setLocationType("Location")
                        filter.setLocationName(root.child(i).child(ii).child(iii).child(iv).text(0))            
            
                        dates = self.mdiParent.db.GetDates(filter)
                        
                        html= html + (
                            " (" + str(len(dates))
                            )
                        
                        if len(dates) > 1:
                            html = html + " dates)"
                        else:
                            html = html + " date)"
                            
                        html = html + (    
                            "</b>"
                            "<br>"                        
                            "<table width='100%'>"
                            "<tr>"
                            )
                            
                        R = 1
                        for d in dates:
                            html = html + (
                                "<td>" +
                                d + 
                                "</td>"
                                )
                            if R == 5:
                                html = html + (
                                    "</tr>"
                                    "<tr>"
                                    )
                                R = 0
                            R = R + 1

                        html= html + (
                            "<br>" +
                            "<br>" +
                            "<br>" +
                            "</table>"
                            )

        html = html + (

            "<font size>" +            
            "</body>" +
            "</html>"
            )
            

        QApplication.restoreOverrideCursor()   
        
        return(html)


    def resizeEvent(self, event):
        #routine to handle events on objects, like clicks, lost focus, gained forcus, etc.        
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)
        
        
    def _updatePhotoThumb(self):
        """Scale the stored pixmap to fill the center pane, preserving aspect ratio."""
        if self._photoPixmap is None or self._photoPixmap.isNull():
            return
        lbl = self.lblPhotoThumb
        if lbl.width() > 0 and lbl.height() > 0:
            lbl.setPixmap(
                self._photoPixmap.scaled(lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

    def resizeMe(self):

        windowWidth =  self.frameGeometry().width()
        windowHeight = self.frameGeometry().height()
        self.scrollArea.setGeometry(5, 27, windowWidth -10 , windowHeight-35)
        self._updatePhotoThumb()


    def _sizeButtonStack(self):
        """Give every header button the same height, and cap the photo pane and
        the header to the height of the button stack, which keeps the header
        compact regardless of font size or window size."""
        metrics = self.trDates.fontMetrics()
        textHeight = int(metrics.boundingRect("2222-22-22").height())
        # Fixed height for all buttons: text height + comfortable padding, all uniform
        btnHeight = textHeight + 12
        for i in range(self.verticalLayout_10.count()):
            item = self.verticalLayout_10.itemAt(i)
            if item and item.widget():
                item.widget().setFixedHeight(btnHeight)

        numBtns = self.verticalLayout_10.count()
        stackHeight = (numBtns * btnHeight
                       + max(0, numBtns - 1) * self.verticalLayout_10.spacing())
        self.framePhoto.setMaximumHeight(stackHeight)
        self.frameTop.setMaximumHeight(stackHeight)

    def scaleMe(self):
               
        scaleFactor = self.mdiParent.scaleFactor
        windowWidth =  int(800  * scaleFactor)
        windowHeight = int(580 * scaleFactor)            
        self.resize(windowWidth, windowHeight)
        
        fontSize = self.mdiParent.fontSize
        scaleFactor = self.mdiParent.scaleFactor     
        #scale the font for all widgets in window
        for w in self.children():
            try:
                w.setFont(QFont(YBFont, fontSize))
            except:
                pass 
        
        baseFont = QFont(QFont(YBFont, fontSize))
        commonFont = QFont(QFont(YBFont, floor(fontSize * 1.4)))
        commonFont.setBold(True)
        scientificFont=  QFont(QFont(YBFont, floor(fontSize * 1.2)))
        scientificFont.setItalic(True)
        # Self-heal for the "spread text" bug: if MainWindow's font canary has
        # detected that this size's font resolution is corrupted (full-width
        # fallback digits), use a verified-clean font pinned to an explicit
        # family instead.  See _initFontCanary in code_MainWindow.
        if hasattr(self.mdiParent, "substituteFont"):
            detailFont = self.mdiParent.substituteFont(fontSize + 1)
        else:
            detailFont = QFont(YBFont, fontSize + 1)
        self.lblCommonName.setFont(commonFont)
        self.lblScientificName.setFont(scientificFont)
        self.lblOrderName.setFont(detailFont)
        self.lblSpeciesCode.setFont(detailFont)
        self.lblConservationStatus.setFont(detailFont)
        self.lblFirstSeen.setFont(detailFont)
        self.lblMostRecentlySeen.setFont(detailFont)

        # macOS bug guard: these word-wrapped header labels can fall into a
        # justified / letter-spread paint path (the rich-text QTextDocument
        # route) after another window — notably Rename Media — has been shown.
        # Pin them to plain text with explicit left alignment on every (re)layout
        # so they always take the simple, non-justifying paint path.
        for _lbl in (self.lblCommonName, self.lblScientificName, self.lblOrderName,
                     self.lblSpeciesCode, self.lblFirstSeen, self.lblMostRecentlySeen,
                     self.lblConservationStatus):
            _lbl.setTextFormat(Qt.TextFormat.PlainText)
            _lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        metrics = self.trDates.fontMetrics()
        textHeight = int(metrics.boundingRect("2222-22-22").height())
        textWidth= int(metrics.boundingRect("2222-22-22").width())
        myQSize = QSize(int(textWidth * 1.1), int(textHeight * 1.75))

        self._sizeButtonStack()

        root = self.trLocations.invisibleRootItem()
        for i in range(root.childCount()):
            root.child(i).setSizeHint(0, myQSize)
            for ii in range(root.child(i).childCount()):
                root.child(i).child(ii).setSizeHint(0, myQSize)
                for iii in range(root.child(i).child(ii).childCount()):
                    root.child(i).child(ii).child(iii).setSizeHint(0, myQSize) 
                    for iv in range(root.child(i).child(ii).child(iii).childCount()):
                        root.child(i).child(ii).child(iii).child(iv).setSizeHint(0, myQSize) 
        
        root = self.trDates.invisibleRootItem()
        for i in range(root.childCount()):
            root.child(i).setSizeHint(0, myQSize)
            for ii in range(root.child(i).childCount()):
                root.child(i).child(ii).setSizeHint(0, myQSize)
                for iii in range(root.child(i).child(ii).childCount()):
                    root.child(i).child(ii).child(iii).setSizeHint(0, myQSize) 
 
        root = self.trMonthDates.invisibleRootItem()
        for i in range(root.childCount()):
            root.child(i).setSizeHint(0, myQSize)
            for ii in range(root.child(i).childCount()):
                root.child(i).child(ii).setSizeHint(0, myQSize)
                for iii in range(root.child(i).child(ii).childCount()):
                    root.child(i).child(ii).child(iii).setSizeHint(0, myQSize)

        rowHeight = self.mdiParent.rowHeight
        self.tblYearLocations.verticalHeader().setDefaultSectionSize(rowHeight)
        self.tblMonthLocations.verticalHeader().setDefaultSectionSize(rowHeight)



