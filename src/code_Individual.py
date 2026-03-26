# import the GUI forms that we create with Qt Creator
import form_Individual
import code_Filter 
import code_Lists 
import code_Location 
import code_Web
import code_Photos
import code_Stylesheet

# import the Qt components we'll use
# do this so later we won't have to clutter our code with references to parent Qt classes 

from PySide6.QtGui import (
    QCursor,
    QFont,
    QFontMetrics
    )

from PySide6.QtCore import (
    Qt,
    QSize,
    Signal,
    )

from PySide6.QtWidgets import (
    QApplication,
    QTableWidgetItem,
    QHeaderView,
    QMdiSubWindow,
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
        self.buttonMap.clicked.connect(self.CreateMap)
        self.buttonChecklists.clicked.connect(self.CreateChecklists)
        self.tabIndividual.setCurrentIndex(0)

 
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
            
        # add a photo button if the db holds photos of this species
        filter = code_Filter.Filter()
        filter.setSpeciesName(Species) 
        
        photoSightings = self.mdiParent.db.GetSightingsWithPhotos(filter)
        
        if len(photoSightings) > 0:
            btnPhotos = QPushButton()
            btnPhotos.setText("Photos")
            btnPhotos.clicked.connect(self.createPhotos)
            self.verticalLayout_10.addWidget(btnPhotos)

        self.scaleMe()
        self.resizeMe()            

        
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
        
        
    def resizeMe(self):

        windowWidth =  self.frameGeometry().width()
        windowHeight = self.frameGeometry().height()
        self.scrollArea.setGeometry(5, 27, windowWidth -10 , windowHeight-35)


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
                w.setFont(QFont("Helvetica", fontSize))
            except:
                pass 
        
        baseFont = QFont(QFont("Helvetica", fontSize))
        commonFont = QFont(QFont("Helvetica", floor(fontSize * 1.4)))
        commonFont.setBold(True)
        scientificFont=  QFont(QFont("Helvetica", floor(fontSize * 1.2)))
        scientificFont.setItalic(True)
        self.lblCommonName.setFont(commonFont)
        self.lblScientificName.setFont(scientificFont)
        self.lblOrderName.setFont(baseFont)

        metrics = self.trDates.fontMetrics()
        textHeight = int(metrics.boundingRect("2222-22-22").height())
        textWidth= int(metrics.boundingRect("2222-22-22").width())
        myQSize = QSize(int(textWidth * 1.1), int(textHeight * 1.75))

        self.buttonWikipedia.resize(self.buttonWikipedia.x(), textHeight)
        self.buttonAudubon.resize(self.buttonWikipedia.x(), textHeight)
        self.buttonAllAboutBirds.resize(self.buttonWikipedia.x(), textHeight)
        self.buttonChecklists.resize(self.buttonWikipedia.x(), textHeight)
        self.buttonMap.resize(self.buttonWikipedia.x(), textHeight)

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



