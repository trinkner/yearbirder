# import the GUI forms that we create with Qt Creator
import form_Location

# import classes from other project files
import code_Filter
import code_Lists
import code_MapHtml
import code_Individual
import code_Stylesheet
from collections import defaultdict

# import the Qt components we'll use
# do this so later we won't have to clutter our code with references to parent Qt classes 

from PySide6.QtGui import (
    QCursor,
    QFont
    )

from PySide6.QtCore import (
    Qt,
    Signal,
    QIODevice,
    QByteArray,
    QBuffer,
    )

from PySide6.QtWidgets import (
    QApplication,
    QTableWidgetItem,
    QHeaderView,
    QMdiSubWindow
    )

from math import (
    floor
)

from PySide6.QtWebEngineWidgets import (
    QWebEngineView,
)

from base64 import (
    b64encode
    )
import code_Stylesheet


class Location(QMdiSubWindow, form_Location.Ui_frmLocation):

    resized = Signal()    
    
    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose,True)
        self.mdiParent = ""        
        self.resized.connect(self.resizeMe)                      
        self.tblDates.currentItemChanged.connect(self.FillSpeciesForDate)
        self.lstSpecies.doubleClicked.connect(self.ClickedLstSpecies)       
        self.tblDates.doubleClicked.connect(self.ClickedTblDates)               
        self.tblSpecies.doubleClicked.connect(self.ClickedTblSpecies)               
        self.tblDates.setShowGrid(False)
        
        self.horizontalLayout_2.setContentsMargins(5, 5, 5, 5)
        self.horizontalLayout_2.setSpacing(4)
        self.webMap = QWebEngineView(self.tabMap)
        self.webMap.setObjectName("webMap")
        self.horizontalLayout_2.addWidget(self.webMap)  
        self.tabLocation.setCurrentIndex(0)


    def ClickedLstSpecies(self):
        species = self.lstSpecies.currentItem().text()
        self.CreateIndividual(species)


    def ClickedTblDates(self):
        thisDate = self.tblDates.item(self.tblDates.currentRow(),  1).text()
        thisLocation = self.lblLocation.text()
        
        tempFilter = code_Filter.Filter()
        
        tempFilter.setLocationType("Location")
        tempFilter.setLocationName(thisLocation)
        tempFilter.setStartDate(thisDate)
        tempFilter.setEndDate(thisDate)
        
        self.CreateSpeciesList(tempFilter)


    def ClickedTblSpecies(self):

        selectedRow = self.tblSpecies.currentRow()
        selectedColumn = self.tblSpecies.currentColumn()        

        if selectedColumn > 1:
            thisDate = self.tblSpecies.item(selectedRow, selectedColumn).text()
            thisLocation = self.lblLocation.text()
            
            tempFilter = code_Filter.Filter()

            tempFilter.setLocationType("Location")
            tempFilter.setLocationName(thisLocation)
            tempFilter.setStartDate(thisDate)
            tempFilter.setEndDate(thisDate)

            self.CreateSpeciesList(tempFilter)
        
        else:
            thisSpecies = self.tblSpecies.item(selectedRow,  1).text()
            self.CreateIndividual(thisSpecies)


    def CreateIndividual(self,  species):
        sub = code_Individual.Individual()
        sub.mdiParent = self.mdiParent
        sub.FillIndividual(species)
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)        
        sub.show()
        sub.resizeMe()


    def CreateSpeciesList(self,  filter):
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        sub = code_Lists.Lists()
        sub.mdiParent = self.mdiParent
        sub.FillSpecies(filter)
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow( sub, self)        
        sub.show() 
        
        QApplication.restoreOverrideCursor()  


    def FillLocation(self, location):
        self.location = location
        thisLocationDates= []
        
        filter = code_Filter.Filter()
        filter.setLocationType("Location")
        filter.setLocationName(location)
        
        thisLocationDates = self.mdiParent.db.GetDates(filter)
        thisLocationDates.sort()
        
        self.tblDates.setColumnCount(4)       
        self.tblDates.setRowCount(len(thisLocationDates))        
        self.tblDates.horizontalHeader().setVisible(True)
        self.tblDates.setHorizontalHeaderLabels(['Rank', 'Date', 'Species', 'Checklists'])
        header = self.tblDates.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        
        self.lblLocation.setText(location)
        self.lblFirstVisited.setText("First visited: " + thisLocationDates[0])
        self.lblMostRecentlyVisited.setText("Most recently visited: " + thisLocationDates[len(thisLocationDates)-1])
        
        dateArray = []
        for d in thisLocationDates:
            if d != "":
                dSpecies = set()
                checklistCount = set()
                for sighting in self.mdiParent.db.locationDict[location]:
                    if d == sighting["date"]:
                        dSpecies.add(sighting["commonName"])
                        checklistCount.add(sighting["checklistID"])
                dateArray.append([len(dSpecies),  d, len(checklistCount)])
        dateArray.sort(reverse=True)
        
        rank = 0
        lastDateTotal = 0
        R = 0
        for date in dateArray:            
            rankItem = QTableWidgetItem()
            if date[0] != lastDateTotal:
                rank = R + 1
            rankItem.setData(Qt.DisplayRole, rank)
            dateItem = QTableWidgetItem()
            dateItem.setText(date[1])
            totalSpeciesItem = QTableWidgetItem()
            totalSpeciesItem.setData(Qt.DisplayRole, date[0])
            totalSpeciesItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)
            totalChecklistsItem = QTableWidgetItem()
            totalChecklistsItem.setData(Qt.DisplayRole, date[2])
            totalChecklistsItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)
            
            self.tblDates.setItem(R, 0, rankItem)  
            self.tblDates.setItem(R, 1, dateItem)
            self.tblDates.setItem(R, 2, totalSpeciesItem)
            self.tblDates.setItem(R, 3, totalChecklistsItem)
            lastDateTotal = date[0]
            R = R + 1
        
        self.tblDates.selectRow(0)
        
        if self.tblDates.rowCount() == 1:
            self.lblDatesSeen.setText("Date (1)")
        else:
            self.lblDatesSeen.setText("Dates (" + str(self.tblDates.rowCount()) + ")")
        # display all dates for the selected location
        self.tblDates.setSortingEnabled(True)
        self.tblDates.sortItems(0,0)
        self.tblDates.setCurrentCell(0, 1)
            
        self.coordinates = self.mdiParent.db.GetLocationCoordinates(location)

        # display the species in the species for date list
        self.FillSpeciesForDate()
        # display the main all-species list
        self.FillSpecies()
                
        self.scaleMe()
        self.resizeMe()


    def FillMap(self):

        coordinatesDict = defaultdict()
        coordinatesDict[self.location] = self.coordinates

        mapWidth = self.width() - 40
        mapHeight= self.height() - 170

        thisMap = code_MapHtml.MapHtml()
        thisMap.mapHeight = mapHeight
        thisMap.mapWidth = mapWidth
        thisMap.coordinatesDict = coordinatesDict
        
        html = thisMap.html()        
        self.webMap.setHtml(html)


    def FillSpecies(self): 
        location = self.lblLocation.text()
        tempFilter = code_Filter.Filter()
        tempFilter.setLocationType("Location")
        tempFilter.setLocationName(location)
       
        # get species data from db 
        thisWindowList = self.mdiParent.db.GetSpeciesWithData(tempFilter)
       
        # set up tblSpecies column headers and widths
        self.tblSpecies.setColumnCount(6)
        self.tblSpecies.setRowCount(len(thisWindowList)+1)
        self.tblSpecies.horizontalHeader().setVisible(True)
        self.tblSpecies.setHorizontalHeaderLabels(['Tax', 'Species', 'First',  'Last', 'Checklists', '% of Chlists'])
        header = self.tblSpecies.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tblSpecies.setShowGrid(False)
        
        font = QFont()
        font.setBold(True)
        count = 0
        nonSpeciesTaxaCount = 0

        # add species and dates to table row by row        
        R = 0
        for species in thisWindowList:    
            taxItem = QTableWidgetItem()
            taxItem.setData(Qt.DisplayRole, R)
            speciesItem = QTableWidgetItem()
            speciesItem.setText(species[0])
            firstItem = QTableWidgetItem()
            firstItem.setData(Qt.DisplayRole, species[1])
            lastItem = QTableWidgetItem()
            lastItem.setData(Qt.DisplayRole, species[2])
            checklistsItem = QTableWidgetItem()
            checklistsItem.setData(Qt.DisplayRole, species[5])
            checklistsItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)
            percentageItem = QTableWidgetItem()
            percentageItem.setData(Qt.DisplayRole, species[6])
            percentageItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)
            
            self.tblSpecies.setItem(R, 0, taxItem)    
            self.tblSpecies.setItem(R, 1, speciesItem)
            self.tblSpecies.setItem(R, 2, firstItem)
            self.tblSpecies.setItem(R, 3, lastItem)
            self.tblSpecies.setItem(R, 4, checklistsItem)
            self.tblSpecies.setItem(R, 5, percentageItem)
            
            self.tblSpecies.item(R, 1).setFont(font)
            
            # set the species to gray if it's not a true species
            if " x " in species[0] or "sp." in species[0] or "/" in species[0]:
                self.tblSpecies.item(R, 1).setForeground(Qt.gray)
                nonSpeciesTaxaCount += 1
            else:
                self.tblSpecies.item(R, 1).setForeground(code_Stylesheet.speciesColor)
                count += 1             
                        
            R += 1

        labelText = "Species: " + str(count)
        if nonSpeciesTaxaCount > 0:
            labelText = labelText + " + " + str(nonSpeciesTaxaCount) + " taxa"
                            
        self.lblSpecies.setText(labelText)
        

    def SetDate(self,  date):
        if self.tblDates.rowCount() > 0:
            for d in range(self.tblDates.rowCount()):
                if self.tblDates.item(d,  1).text() == date:
                    self.tblDates.setCurrentCell(d,  1)
                    self.FillSpeciesForDate()
                    self.tabLocation.setCurrentIndex(1)
                    break


    def FillSpeciesForDate(self):
        self.lstSpecies.clear()
        location = self.lblLocation.text()
        if self.tblDates.item(self.tblDates.currentRow(),  1) is not None:
            
            date = self.tblDates.item(self.tblDates.currentRow(),  1).text()      

            tempFilter = code_Filter.Filter()
            tempFilter.setStartDate(date)
            tempFilter.setEndDate(date)
            tempFilter.setLocationName(location)
            tempFilter.setLocationType("Location")

            species = self.mdiParent.db.GetSpecies(tempFilter)

            font = QFont()
            font.setBold(True)
            
            count = 0
            nonSpeciesTaxaCount = 0 
            
            R = 0
            for s in species:
                
                self.lstSpecies.addItem(s)
                self.lstSpecies.item(R).setFont(font)
                # set the species to gray if it's not a true species
                if " x " in s or "sp." in s or "/" in s:
                    self.lstSpecies.item(R).setForeground(Qt.gray)
                    nonSpeciesTaxaCount += 1
                else:
                    self.lstSpecies.item(R).setForeground(code_Stylesheet.speciesColor)
                    count += 1             
                
                R += 1
            
            labelText = "Species: " + str(count)
            if nonSpeciesTaxaCount > 0:
                labelText = labelText + " + " + str(nonSpeciesTaxaCount) + " taxa"                
                
            self.lstSpecies.setCurrentRow(0)
            self.lstSpecies.setSpacing(2)
                        
            self.lblSpeciesSeen.setText(labelText)


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
            self.lblFirstVisited.text() + 
            "</H3>"
            )        

        html = html + (
            "<H3>" + 
            self.lblMostRecentlyVisited.text() + 
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

        encodedImage = b64encode(myByteArray)
        
        html = html + ("""
        <img src="data:image/png;base64, 
        """)
        
        html = html + str(encodedImage)[1:]
        
        html = html + ("""        
        "  />
        """)

        html = html + (
            "<H4>" + 
            "Species"
            "</H4>"
            )    

        html=html + (
            "<font size='2'>" +
            "<p>"
            )
       
        # loopthrough the species listed in tblSpecies
        for r in range(self.tblSpecies.rowCount()):
            html= html + (
                self.tblSpecies.item(r, 1).text()
                + "<br>"
                )

        html= html + (
            "<H4>" +
            "Dates" +
            "</H4>"
            )
 
        # create filter set to our current location
        filter = code_Filter.Filter()
        filter.setLocationType = "Location"
        filter.setLocationName =  self.lblLocation.text()

        # for each date in tblDates, find the species and display them in a table
        for r in range(self.tblDates.rowCount()):

            html= html + (
                "<b>" +
                self.tblDates.item(r, 1).text() +
                "</b>"
                )    

            filter.setStartDate(self.tblDates.item(r, 1).text())
            filter.setEndDate(self.tblDates.item(r, 1).text())
            species = self.mdiParent.db.GetSpecies(filter)

            html = html + (    
                "<br>"                        
                "<table width='100%'>"
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
        self.FillMap()


    def scaleMe(self):
               
        scaleFactor = self.mdiParent.scaleFactor
        windowWidth =  int(800  * scaleFactor)
        windowHeight = int(600 * scaleFactor)      
        self.resize(windowWidth, windowHeight)
        
        fontSize = self.mdiParent.fontSize
        scaleFactor = self.mdiParent.scaleFactor     
        #scale the font for all widgets in window
        for w in self.children():
            try:
                w.setFont(QFont("Helvetica", fontSize))
            except:
                pass 
        
        baseFont = QFont(QFont("Helvetica", floor(fontSize * 1.2)))
        locationFont = QFont(QFont("Helvetica", floor(fontSize * 1.4)))
        locationFont.setBold(True)
        self.lblLocation.setFont(locationFont)
        self.lblFirstVisited.setFont(baseFont)
        self.lblMostRecentlyVisited.setFont(baseFont)

        header = self.tblSpecies.horizontalHeader()
        metrics = self.tblSpecies.fontMetrics()

        dateTextWidth = int(metrics.boundingRect("2222-22-22").width())
        dateTextHeight = int(metrics.boundingRect("2222-22-22").height())
        
        taxText = str(self.tblSpecies.rowCount())
        taxTextWidth = int(metrics.boundingRect(taxText).width())
        header.resizeSection(0,  floor(2 * taxTextWidth))
        header.resizeSection(2,  floor(1.5 * dateTextWidth))
        header.resizeSection(3,  floor(1.5 * dateTextWidth))                
        for R in range(self.tblSpecies.rowCount()):
            self.tblSpecies.setRowHeight(R, int(dateTextHeight * 1.75))

        header = self.tblDates.horizontalHeader()         
        textWidth = int(metrics.boundingRect("Rank").width())
        header.resizeSection(0,  floor(1.75 * textWidth))
        header.resizeSection(1,  floor(1.5 * dateTextWidth))
        for R in range(self.tblDates.rowCount()):
            self.tblDates.setRowHeight(R, int(dateTextHeight * 1.75))
        
        self.FillMap()
