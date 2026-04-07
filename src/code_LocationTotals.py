# import GUI form for this class
import form_LocationTotals
# import pandas
# import folium
# import json
# from branca.colormap import LinearColormap

# import classes from other project files
import code_Filter
import code_Lists

# import basic Python libraries
from copy import deepcopy
from math import floor

from PySide6.QtGui import (
    QCursor,
    QFont,
    QFontMetrics
    )

from PySide6.QtCore import (
    Qt,
    Signal
    )

from collections import (
    defaultdict
)
from PySide6.QtWidgets import (
    QApplication,
    QTableWidgetItem,
    QHeaderView,
    QMdiSubWindow,
    QWidget,
    )




class LocationTotals(QMdiSubWindow, form_LocationTotals.Ui_frmLocationTotals):

    # create "resized" as a signal that the window can emit
    # we respond to this signal with the form's resizeMe method below
    resized = Signal()       
    
    
    def __init__(self):
        super(self.__class__, self).__init__()
        # setupUi sets QVBoxLayout directly on its argument. QMdiSubWindow already
        # has an internal Qt6 layout, so passing self causes a "already has a layout"
        # warning. Use a container widget instead; all self.xxx UI attributes are still
        # set on self by the Ui mixin regardless of which widget is passed.
        _container = QWidget()
        self.setupUi(_container)
        self.setWidget(_container)
        self.setObjectName("frmLocationTotals")
        self.setAttribute(Qt.WA_DeleteOnClose,True)
        self.mdiParent = ""        
        self.resized.connect(self.resizeMe)                            
        self.tblRegionTotals.itemDoubleClicked.connect(lambda: self.CreateListForLocation("Region"))
        self.tblCountryTotals.itemDoubleClicked.connect(lambda: self.CreateListForLocation("Country"))
        self.tblStateTotals.itemDoubleClicked.connect(lambda: self.CreateListForLocation("State"))
        self.tblCountyTotals.itemDoubleClicked.connect(lambda: self.CreateListForLocation("County"))
        self.tblLocationTotals.itemDoubleClicked.connect(lambda: self.CreateListForLocation("Location"))
        self.filter = code_Filter.Filter()
        self.tabLocationTotals.setCurrentIndex(0)

        self.tblCountryTotals.addAction(self.actionSetCountryFilter)
        self.tblStateTotals.addAction(self.actionSetStateFilter)
        self.tblCountyTotals.addAction(self.actionSetCountyFilter)
        self.tblLocationTotals.addAction(self.actionSetLocationFilter)
        
        self.actionSetCountryFilter.triggered.connect(self.setCountryFilter)
        self.actionSetStateFilter.triggered.connect(self.setStateFilter)
        self.actionSetCountyFilter.triggered.connect(self.setCountyFilter)
        self.actionSetLocationFilter.triggered.connect(self.setLocationFilter)


    def CreateListForLocation(self,  locationType):
        tempFilter = deepcopy(self.filter)

        if locationType == "Region":
            if self.tblRegionTotals.currentRow() == -1:
                return
            locationName = self.mdiParent.db.GetRegionCode(self.tblRegionTotals.item(self.tblRegionTotals.currentRow(),  1).text())
        if locationType == "Country":
            if self.tblCountryTotals.currentRow() == -1:
                return
            locationName = self.mdiParent.db.GetCountryCode(self.tblCountryTotals.item(self.tblCountryTotals.currentRow(),  1).text())
        if locationType == "State":
            if self.tblStateTotals.currentRow() == -1:
                return
            locationName = self.mdiParent.db.GetStateCode(self.tblStateTotals.item(self.tblStateTotals.currentRow(),  1).text())
        if locationType == "County":
            if self.tblCountyTotals.currentRow() == -1:
                return
            locationName = self.tblCountyTotals.item(self.tblCountyTotals.currentRow(),  1).text()
        if locationType == "Location":
            if self.tblLocationTotals.currentRow() == -1:
                return
            locationName = self.tblLocationTotals.item(self.tblLocationTotals.currentRow(),  1).text()
        
        sub = code_Lists.Lists()        
        sub.mdiParent = self.mdiParent
        tempFilter.setLocationType(locationType)
        tempFilter.setLocationName(locationName)
        
        if self.focusWidget().currentColumn() in [0, 1, 2]:
            sub.FillSpecies(tempFilter)

        if self.focusWidget().currentColumn() == 3:
            sub.FillChecklists(tempFilter)

        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow( sub, self)
        sub.show()
        sub.scaleMe()
        QApplication.restoreOverrideCursor()


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
            "Location Totals" + 
            "</H1>"
            )
        
        html = html + (
            "<H2>" + 
            self.lblLocation.text() + 
            "</H2>"
            )        

        html = html + (
            "<H2>" + 
            self.lblDateRange.text() + 
            "</H2>"
            )        

        html = html + (
            "<H2>" + 
            self.lblDetails.text() + 
            "</H2>"
            )        

        html = html + (
            "<H3>" + 
            "Region Totals" + 
            "</H3>"
            )        
            
        html=html + (
            "<font size='2'>" +
            "<table width='100%'>" +
            " <tr>"
            )
                    
        html=html + (    
            "<th>Rank</th>" +
            "<th>Region</th> " +
            "<th>Species</th>" +
            "<th>Checklists</th>" +
            "</tr>"
            )
            
        for r in range(self.tblRegionTotals.rowCount()):
            html = html + (
            "<tr>" +
            "<td>" +
            self.tblRegionTotals.item(r, 0).text() +
            "</td>" +
            "<td>" +
            self.tblRegionTotals.item(r, 1).text() +
            "</td>" +
            "<td>" +
            self.tblRegionTotals.item(r, 2).text() +
            "</td>" +
            "<td>" +
            self.tblRegionTotals.item(r, 3).text() +
            "</td>" +
            "</tr>"
            )
            
        html = html + (
            "</table>"
            "</font size>"
            )


        html = html + (
            "<H3>" + 
            "Country Totals" + 
            "</H3>"
            )        
            
        html=html + (
            "<font size='2'>" +
            "<table width='100%'>" +
            " <tr>"
            )
                    
        html=html + (    
            "<th>Rank</th>" +
            "<th>Country</th> " +
            "<th>Species</th>" +
            "<th>Checklists</th>" +
            "</tr>"
            )
            
        for r in range(self.tblCountryTotals.rowCount()):
            html = html + (
            "<tr>" +
            "<td>" +
            self.tblCountryTotals.item(r, 0).text() +
            "</td>" +
            "<td>" +
            self.tblCountryTotals.item(r, 1).text() +
            "</td>" +
            "<td>" +
            self.tblCountryTotals.item(r, 2).text() +
            "</td>" +
            "<td>" +
            self.tblCountryTotals.item(r, 3).text() +
            "</td>" +
            "</tr>"
            )
            
        html = html + (
            "</table>"
            "</font size>"
            )

        html = html + (
            "<H3>" + 
            "State Totals" + 
            "</H3>"
            )        
            
        html=html + (
            "<font size='2'>" +
            "<table width='100%'>" +
            " <tr>"
            )
                    
        html=html + (    
            "<th>Rank</th>" +
            "<th>State</th> " +
            "<th>Species</th>" +
            "<th>Checklists</th>" +
            "</tr>"
            )
            
        for r in range(self.tblStateTotals.rowCount()):
            html = html + (
            "<tr>" +
            "<td>" +
            self.tblStateTotals.item(r, 0).text() +
            "</td>" +
            "<td>" +
            self.tblStateTotals.item(r, 1).text() +
            "</td>" +
            "<td>" +
            self.tblStateTotals.item(r, 2).text() +
            "</td>" +           
            "<td>" +
            self.tblStateTotals.item(r, 3).text() +
            "</td>" +
            "</tr>"
            )
            
        html = html + (
            "</table>"
            "</font size>"
            )

        html = html + (
            "<H3>" + 
            "County Totals" + 
            "</H3>"
            )        
            
        html=html + (
            "<font size='2'>" +
            "<table width='100%'>" +
            " <tr>"
            )
                    
        html=html + (    
            "<th>Rank</th>" +
            "<th>County</th> " +
            "<th>Species</th>" +
            "<th>Checklists</th>" +
            "</tr>"
            )
            
        for r in range(self.tblCountyTotals.rowCount()):
            html = html + (
            "<tr>" +
            "<td>" +
            self.tblCountyTotals.item(r, 0).text() +
            "</td>" +
            "<td>" +
            self.tblCountyTotals.item(r, 1).text() +
            "</td>" +
            "<td>" +
            self.tblCountyTotals.item(r, 2).text() +
            "</td>" +
            "<td>" +
            self.tblCountyTotals.item(r, 3).text() +
            "</td>" +
            "</tr>"
            )
            
        html = html + (
            "</table>"
            "</font size>"
            )

        html = html + (
            "<H3>" + 
            "Location Totals" + 
            "</H3>"
            )        
            
        html=html + (
            "<font size='2'>" +
            "<table width='100%'>" +
            " <tr>"
            )
                    
        html=html + (    
            "<th>Rank</th>" +
            "<th>Location</th> " +
            "<th>Species</th>" +
            "<th>Checklists</th>" +
            "</tr>"
            )
            
        for r in range(self.tblLocationTotals.rowCount()):
            html = html + (
            "<tr>" +
            "<td>" +
            self.tblLocationTotals.item(r, 0).text() +
            "</td>" +
            "<td>" +
            self.tblLocationTotals.item(r, 1).text() +
            "</td>" +
            "<td>" +
            self.tblLocationTotals.item(r, 2).text() +
            "</td>" +
            "<td>" +
            self.tblLocationTotals.item(r, 3).text() +
            "</td>" +
            "</tr>"
            )
            
        html = html + (
            "</table>"
            "</font size>"
            )
            
        html = html + (
            "</body>" +
            "</html>"
            )
            
        QApplication.restoreOverrideCursor()   
        
        return(html)
        

    def FillLocationTotals(self,  filter):
        self.filter = deepcopy(filter)
        
        # find all years, months, and dates in db
        dbRegions = set()
        dbCountries = set()
        dbStates = set()
        dbCounties = set()
        dbLocations = set()
        regionDict = defaultdict()
        countryDict = defaultdict()
        stateDict = defaultdict()
        countyDict = defaultdict()
        locationDict = defaultdict()
        
        minimalSightingList = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)
        cf = self.mdiParent.db.CompileFilter(filter)

        for s in minimalSightingList:

            # Consider only full species, not slash or spuh or hybrid entries
            commonName = s["commonName"]
            if "/" not in commonName and "sp." not in commonName and " x " not in commonName:

                if self.mdiParent.db.TestSightingCompiled(s, cf) is True:
                    for r in s["regionCodes"]:
                        dbRegions.add(r)  
                    dbCountries.add(s["country"])
                    dbStates.add(s["state"])
                    if s["county"] != "":
                        dbCounties.add(s["county"])
                    dbLocations.add(s["location"])
                    
                    # create dictionaries of region, country, state, county, and location sighting for faster lookup
                    for r in s["regionCodes"]:
                        if r not in regionDict.keys():
                            regionDict[r] = [s]
                        else:
                            regionDict[r].append(s)                

                    if s["country"] not in countryDict.keys():
                        countryDict[s["country"]] = [s]
                    else:
                        countryDict[s["country"]].append(s)                
                    
                    if s["state"] not in stateDict.keys():
                        stateDict[s["state"]] = [s]
                    else:
                        stateDict[s["state"]].append(s)                
                                 
                    if s["county"] != "":
                        if s["county"] not in countyDict.keys():
                            countyDict[s["county"]] = [s]
                        else:
                            countyDict[s["county"]].append(s)       
                                 
                    if s["location"] not in locationDict.keys():
                        locationDict[s["location"]] = [s]
                    else:
                        locationDict[s["location"]].append(s)           
        
        # check if no sightings were found. Return false if none found. Abort and display message.
        if len(regionDict) + len(countryDict) + len(stateDict) + len(countyDict) + len(locationDict) == 0:
            return(False)
        
        # set numbers of rows for each tab's grid (years, months, dates)
        self.tblRegionTotals.setRowCount(len(dbRegions))
        self.tblRegionTotals.setColumnCount(4)
        self.tblCountryTotals.setRowCount(len(dbCountries))
        self.tblCountryTotals.setColumnCount(4)
        self.tblStateTotals.setRowCount(len(dbStates))
        self.tblStateTotals.setColumnCount(4)
        self.tblCountyTotals.setRowCount(len(dbCounties))
        self.tblCountyTotals.setColumnCount(4)
        self.tblLocationTotals.setRowCount(len(dbLocations))
        self.tblLocationTotals.setColumnCount(4)     

        self.tblRegionTotals.setShowGrid(False)                
        self.tblCountryTotals.setShowGrid(False)        
        self.tblStateTotals.setShowGrid(False)        
        self.tblCountyTotals.setShowGrid(False)        
        self.tblLocationTotals.setShowGrid(False)        
     
        regionArray = []
        for region in dbRegions:
            regionSpecies = set()
            regionChecklists = set()
            for s in regionDict[region]:
                regionSpecies.add(s["commonName"])
                regionChecklists.add(s["checklistID"])
            regionArray.append([len(regionSpecies), region, len(regionChecklists)])
        regionArray.sort(reverse=True)
        R = 0
        for region in regionArray:            
            rankItem = QTableWidgetItem()
            rankItem.setData(Qt.DisplayRole, R+1)
            regionItem = QTableWidgetItem()
            regionItem.setText(self.mdiParent.db.GetRegionName(region[1]))
            regionTotalItem = QTableWidgetItem()
            regionTotalItem.setData(Qt.DisplayRole, region[0])
            regionTotalItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)                     
            regionChecklistTotalItem = QTableWidgetItem()
            regionChecklistTotalItem.setData(Qt.DisplayRole, region[2])
            regionChecklistTotalItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)                     
            self.tblRegionTotals.setItem(R, 0, rankItem)    
            self.tblRegionTotals.setItem(R, 1, regionItem)
            self.tblRegionTotals.setItem(R, 2, regionTotalItem)
            self.tblRegionTotals.setItem(R, 3, regionChecklistTotalItem)

            R = R + 1     
     
        
        countryArray = []
        for country in dbCountries:
            countrySpecies = set()
            countryChecklists = set()
            for s in countryDict[country]:
                countrySpecies.add(s["commonName"])
                countryChecklists.add(s["checklistID"])
            countryArray.append([len(countrySpecies),  country, len(countryChecklists)])
        countryArray.sort(reverse=True)
        R = 0
        for country in countryArray:            
            rankItem = QTableWidgetItem()
            rankItem.setData(Qt.DisplayRole, R+1)
            countryItem = QTableWidgetItem()
            countryItem.setText(self.mdiParent.db.GetCountryName(country[1]))
            countryTotalItem = QTableWidgetItem()
            countryTotalItem.setData(Qt.DisplayRole, country[0])
            countryTotalItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)                     
            countryChecklistTotalItem = QTableWidgetItem()
            countryChecklistTotalItem.setData(Qt.DisplayRole, country[2])
            countryChecklistTotalItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)                     
            self.tblCountryTotals.setItem(R, 0, rankItem)    
            self.tblCountryTotals.setItem(R, 1, countryItem)
            self.tblCountryTotals.setItem(R, 2, countryTotalItem)
            self.tblCountryTotals.setItem(R, 3, countryChecklistTotalItem)

            R = R + 1

        stateArray = []
        for state in dbStates:
            stateSpecies = set()
            stateChecklists = set()
            for s in stateDict[state]:
                stateSpecies.add(s["commonName"])
                stateChecklists.add(s["checklistID"])
            stateArray.append([len(stateSpecies),  state, len(stateChecklists)])
        stateArray.sort(reverse=True)
        R = 0
        for state in stateArray:            
            rankItem = QTableWidgetItem()
            rankItem.setData(Qt.DisplayRole, R+1)
            stateItem = QTableWidgetItem()
            stateItem.setText(self.mdiParent.db.GetStateName(state[1]))
            stateTotalItem = QTableWidgetItem()
            stateTotalItem.setData(Qt.DisplayRole, state[0])
            stateTotalItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)                     
            stateChecklistTotalItem = QTableWidgetItem()
            stateChecklistTotalItem.setData(Qt.DisplayRole, state[2])
            stateChecklistTotalItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)                     
            self.tblStateTotals.setItem(R, 0, rankItem)    
            self.tblStateTotals.setItem(R, 1, stateItem)
            self.tblStateTotals.setItem(R, 2, stateTotalItem)
            self.tblStateTotals.setItem(R, 3, stateChecklistTotalItem)
            R = R + 1
            
        countyArray = []
        for county in dbCounties:
            if county != "" and county is not None:
                countySpecies = set()
                countyChecklists = set()
                for s in countyDict[county]:
                    countySpecies.add(s["commonName"])
                    countyChecklists.add(s["checklistID"])
                countyArray.append([len(countySpecies),  county, len(countyChecklists)])
        countyArray.sort(reverse=True)
        R = 0
        for county in countyArray:            
            rankItem = QTableWidgetItem()
            rankItem.setData(Qt.DisplayRole, R+1)
            countyItem = QTableWidgetItem()
            countyItem.setText(county[1])
            countyTotalItem = QTableWidgetItem()
            countyTotalItem.setData(Qt.DisplayRole, county[0])
            countyTotalItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)                                 
            countyChecklistTotalItem = QTableWidgetItem()
            countyChecklistTotalItem.setData(Qt.DisplayRole, county[2])
            countyChecklistTotalItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)                                 
            self.tblCountyTotals.setItem(R, 0, rankItem)    
            self.tblCountyTotals.setItem(R, 1, countyItem)
            self.tblCountyTotals.setItem(R, 2, countyTotalItem)
            self.tblCountyTotals.setItem(R, 3, countyChecklistTotalItem)
            R = R + 1

        locationArray = []
        for location in dbLocations:
            if location != "":
                locationSpecies = set()
                locationChecklists = set()
                for s in locationDict[location]:
                    locationSpecies.add(s["commonName"])
                    locationChecklists.add(s["checklistID"])
                locationArray.append([len(locationSpecies),  location, len(locationChecklists)])
        locationArray.sort(reverse=True)
        rank = 0
        lastLocationTotal = 0
        R = 0
        for location in locationArray:            
            rankItem = QTableWidgetItem()
            if location[0] != lastLocationTotal:
                rank = R+1
            rankItem.setData(Qt.DisplayRole, rank)
            locationItem = QTableWidgetItem()
            locationItem.setText(location[1])
            locationTotalItem = QTableWidgetItem()
            locationTotalItem.setData(Qt.DisplayRole, location[0])
            locationTotalItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)                                             
            locationChecklistTotalItem = QTableWidgetItem()
            locationChecklistTotalItem.setData(Qt.DisplayRole, location[2])
            locationChecklistTotalItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)                                             
            self.tblLocationTotals.setItem(R, 0, rankItem)    
            self.tblLocationTotals.setItem(R, 1, locationItem)
            self.tblLocationTotals.setItem(R, 2, locationTotalItem)
            self.tblLocationTotals.setItem(R, 3, locationChecklistTotalItem)
            lastLocationTotal = location[0]
            R = R + 1

        # set headers and column stretching 
        for t in [self.tblRegionTotals, self.tblCountryTotals, self.tblStateTotals, self.tblCountyTotals, self.tblLocationTotals]:
            t.setSortingEnabled(True)
            t.sortItems(0, Qt.SortOrder.AscendingOrder)
            t.horizontalHeader().setVisible(True)
            # remove first three characters from tbl widget name
            regionType = t.objectName()[3:]
            # remove "Totals" from widget name
            regionType = regionType[:-6]
            t.setHorizontalHeaderLabels(['Rank', regionType, 'Species', 'Checklists'])
            header = t.horizontalHeader()
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        # set location and date range titles
        self.mdiParent.SetChildDetailsLabels(self, self.filter)

        # set window title
        self.setWindowTitle(self.filter.buildWindowTitle("Location Totals", self.mdiParent.db))

        if self.lblDetails.text() != "":
            self.lblDetails.setVisible(True)
        else:
            self.lblDetails.setVisible(False)
        
        self.scaleMe()
        self.resizeMe()

        return(True)


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
        windowWidth =  int(600  * scaleFactor)
        windowHeight = int(580 * scaleFactor)      
        self.resize(windowWidth, windowHeight)
        
        fontSize = self.mdiParent.fontSize
        scaleFactor = self.mdiParent.scaleFactor     
        #scale the font for all widgets in window
        for w in self.scrollAreaWidgetContents.children():
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
        rowHeight = self.mdiParent.rowHeight
        rankTextWidth = int(metrics.boundingRect("Rank").width())

        for t in [self.tblRegionTotals, self.tblCountryTotals, self.tblStateTotals, self.tblCountyTotals, self.tblLocationTotals]:
            header = t.horizontalHeader()
            header.resizeSection(0,  floor(1.7 * rankTextWidth))
            header.resizeSection(2,  floor(2 * rankTextWidth))
            header.resizeSection(3,  floor(2.5 * rankTextWidth))
            t.verticalHeader().setDefaultSectionSize(rowHeight)


    def setCountryFilter(self):
        countryName= self.tblCountryTotals.item(self.tblCountryTotals.currentRow(), 1).text()
        self.mdiParent.setCountryFilter(countryName)

             
    def setStateFilter(self):
        stateName= self.tblStateTotals.item(self.tblStateTotals.currentRow(), 1).text()
        self.mdiParent.setStateFilter(stateName)
            
            
    def setCountyFilter(self):
        countyName= self.tblCountyTotals.item(self.tblCountyTotals.currentRow(), 1).text()
        self.mdiParent.setCountyFilter(countyName)
   
   
    def setLocationFilter(self):
        locationName= self.tblLocationTotals.item(self.tblLocationTotals.currentRow(), 1).text()
        self.mdiParent.setLocationFilter(locationName)
            
