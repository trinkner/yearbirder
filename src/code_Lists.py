# import project files
import form_Lists
import code_Filter
import code_Location
import code_Individual
import code_FloatDelegate
import code_Stylesheet

# import basic Python libraries
from copy import deepcopy
from math import floor

from PySide6.QtGui import (
    QCursor,
    QIcon,
    QPixmap,
    QFont
    )

from PySide6.QtCore import (
    Qt,
    Signal
    )

from PySide6.QtWidgets import (
    QApplication,
    QTableWidgetItem,
    QHeaderView,
    QMdiSubWindow,
    QItemDelegate
    )


class Lists(QMdiSubWindow, form_Lists.Ui_frmSpeciesList):

    # create "resized" as a signal that the window can emit
    # we respond to this signal with the form's resizeMe method below
    resized = Signal()
    
    
    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        
        self.setAttribute(Qt.WA_DeleteOnClose,True)
        
        self.tblList.doubleClicked.connect(self.tblListClicked)
        self.btnShowLocation.clicked.connect(self.CreateLocation)
        self.txtFind.textChanged.connect(self.ChangedFindText)
        self.actionSetDateFilter.triggered.connect(self.setDateFilter)
        self.actionSetFirstDateFilter.triggered.connect(self.setFirstDateFilter)
        self.actionSetLastDateFilter.triggered.connect(self.setLastDateFilter)
        self.actionSetSpeciesFilter.triggered.connect(self.setSpeciesFilter)
        self.actionSetCountryFilter.triggered.connect(self.setCountryFilter)
        self.actionSetStateFilter.triggered.connect(self.setStateFilter)
        self.actionSetCountyFilter.triggered.connect(self.setCountyFilter)
        self.actionSetLocationFilter.triggered.connect(self.setLocationFilter)
        self.tblList.horizontalHeader().sortIndicatorChanged.connect(self.afterSort)
        self.resized.connect(self.resizeMe)    
        
        self.btnShowLocation.setVisible(False)
        self.lblDetails.setVisible(False)

        self.mdiParent = ""
        self.currentSpeciesList = []
        self.filter = ()
        self.listType = ""


    def resizeEvent(self, event):
        #routine to handle events on objects, like clicks, lost focus, gained forcus, etc.        
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)
        
            
    def resizeMe(self):

        windowWidth = self.width()-10
        windowHeight = self.height()     
        self.scrollArea.setGeometry(5, 27, windowWidth-5, windowHeight-35)
        self.layLists.setGeometry(0, 0, windowWidth-5, windowHeight-40)
        self.txtChecklistComments.setMaximumHeight(floor(.15 * windowHeight))  
    
   
    def setCountyFilter(self):
        
        if self.listType in ["Checklists"]:
            if self.listType == "Checklists":
                countyName= self.tblList.item(self.tblList.currentRow(), 2).text()
            self.mdiParent.setCountyFilter(countyName)
   
   
    def setCountryFilter(self):
        
        if self.listType in ["Checklists"]:
            if self.listType == "Checklists":
                countryName= self.tblList.item(self.tblList.currentRow(), 0).text()
                self.mdiParent.setCountryFilter(countryName)


    def setDateFilter(self):   
             
        if self.listType in ["Checklists", "Single Checklist"]:
            if self.listType == "Checklists":
                date = self.tblList.item(self.tblList.currentRow(), 4).text()
            if self.listType == "Single Checklist":
                date = self.filter.getStartDate()
            self.mdiParent.setDateFilter(date)
   
   
    def setFirstDateFilter(self):
        
        if self.listType in ["Species", "Locations"]:
            if self.listType == "Species":
                date = self.tblList.item(self.tblList.currentRow(), 2).text()
            if self.listType == "Locations":
                date = self.tblList.item(self.tblList.currentRow(), 1).text()                
            self.mdiParent.setDateFilter(date)


    def setLastDateFilter(self):
        
        if self.listType in ["Species", "Locations"]:
            if self.listType == "Species":
                date = self.tblList.item(self.tblList.currentRow(), 3).text()
            if self.listType == "Locations":
                date = self.tblList.item(self.tblList.currentRow(), 2).text()    
            self.mdiParent.setDateFilter(date)


    def setLocationFilter(self):
        
        if self.listType in ["Locations", "Single Checklist", "Checklists"]:
            if self.listType == "Locations":
                locationName= self.tblList.item(self.tblList.currentRow(), 0).text()
            if self.listType == "Single Checklist":
                locationName= self.lblLocation.text()
            if self.listType == "Checklists":
                locationName= self.tblList.item(self.tblList.currentRow(), 3).text()
            self.mdiParent.setLocationFilter(locationName)
                 
   
    def setSpeciesFilter(self):
        
        if self.listType in ["Species", "Single Checklist"]:
            speciesName = self.tblList.item(self.tblList.currentRow(), 1).text()
            self.mdiParent.setSpeciesFilter(speciesName)
            
   
    def setStateFilter(self):
        
        if self.listType in ["Checklists"]:
            if self.listType == "Checklists":
                stateName= self.tblList.item(self.tblList.currentRow(), 1).text()
            self.mdiParent.setStateFilter(stateName)
            
   
    def scaleMe(self):
       
        fontSize = self.mdiParent.fontSize
        scaleFactor = self.mdiParent.scaleFactor     
        #scale the font for all widgets in window
        for w in self.children():
            try:
                w.setFont(QFont("Helvetica", fontSize))
            except:
                pass
          
        # scale the find text box and show location button
        metrics = self.btnShowLocation.fontMetrics()
        buttonWidth = int(metrics.boundingRect(self.btnShowLocation.text()).width() * 1.25)
        buttonHeight = int(metrics.boundingRect(self.btnShowLocation.text()).height() * 1.25)
        self.btnShowLocation.setMinimumWidth(buttonWidth)
        self.btnShowLocation.setMaximumWidth(buttonWidth)
        self.btnShowLocation.setMinimumHeight(buttonHeight)
        self.btnShowLocation.setMaximumHeight(buttonHeight)
        self.txtFind.setMinimumWidth(buttonWidth)
        self.txtFind.setMaximumWidth(buttonWidth)
        self.txtFind.setMinimumHeight(buttonHeight)
        self.txtFind.setMaximumHeight(buttonHeight)        
        
        # scale the main window table   
        header = self.tblList.horizontalHeader()
        metrics = self.tblList.fontMetrics()

        if self.listType == "Species":
            dateTextWidth = int(metrics.boundingRect("2222-22-22").width())
            dateTextHeight = int(metrics.boundingRect("2222-22-22").height())
            
            #find the width of the widest integer in the Tax column
            maxWidth = 0
            for R in range(self.tblList.rowCount()):
                item = self.tblList.item(R, 0)
                if item is not None:
                    text = item.text()
                    w = metrics.boundingRect(text).width()
                    if w > maxWidth:
                        maxWidth = w
            taxTextWidth = maxWidth
            
            #find the width of the widest date in the First Date column
            maxWidth = 0
            for R in range(self.tblList.rowCount()):
                item = self.tblList.item(R, 2)
                if item is not None:
                    text = item.text()
                    w = metrics.boundingRect(text).width()
                    if w > maxWidth:
                        maxWidth = w
            firstDateTextWidth = maxWidth
            
            #find the width of the widest date in the Last Date column
            maxWidth = 0
            for R in range(self.tblList.rowCount()):
                item = self.tblList.item(R, 3)
                if item is not None:
                    text = item.text()
                    w = metrics.boundingRect(text).width()
                    if w > maxWidth:
                        maxWidth = w
            lastDateTextWidth = maxWidth
            
            # --- compute fixed widths ---
            w0 = floor(1.75 * taxTextWidth)
            w2 = floor(1.75 * firstDateTextWidth)
            w3 = floor(1.75 * lastDateTextWidth)
            w4 = floor(1.3 * dateTextWidth)
            w5 = floor(1.7 * dateTextWidth)

            # apply fixed widths to all columns except species name
            header.resizeSection(0, w0)
            header.resizeSection(2, w2)
            header.resizeSection(3, w3)
            header.resizeSection(4, w4)
            header.resizeSection(5, w5)
            
            # give species name column the remaining width
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch) 
                      
            for R in range(self.tblList.rowCount()):
                self.tblList.setRowHeight(R, int(dateTextHeight * 1.1))
        
        if self.listType == "Single Checklist":
            taxTextWidth = int(metrics.boundingRect("Tax").width())
            header.resizeSection(0,  floor(1.75 * taxTextWidth))
            countWidth = int(metrics.boundingRect("Count").width())
            header.resizeSection(2,  floor(1.6 * countWidth))
            commentWidth = int(metrics.boundingRect("Suitble comments column").width())
            header.resizeSection(3,  floor(1.15 * commentWidth))
            # only limit row height if there aren't comments. If there are comments, we want word wrap
            # to have unlimited height
            thisRowHeight= int(metrics.boundingRect("222").height())
            for R in range(self.tblList.rowCount()):
                if self.tblList.item(R,3).data(Qt.DisplayRole) == "":
                    self.tblList.setRowHeight(R, int(thisRowHeight * 1.1)) 
            self.tblList.resizeRowsToContents()
        
        if self.listType == "Locations":
            dateTextWidth = int(metrics.boundingRect("2222-22-22 22:22").width())
            dateTextHeight = int(metrics.boundingRect("2222-22-22 22:22").height())
            header.resizeSection(1,  floor(1.75 * dateTextWidth))
            header.resizeSection(2,  floor(1.75 * dateTextWidth))                
            for R in range(self.tblList.rowCount()):
                self.tblList.setRowHeight(R, int(dateTextHeight * 1.1))

        if self.listType == "Checklists":

            thisColumnWidth = int(metrics.boundingRect("Sample Names").width())
            header.resizeSection(0,  floor(1.5 * thisColumnWidth))                
            header.resizeSection(1,  floor(1.75 * thisColumnWidth))                
            header.resizeSection(2,  floor(1.75 * thisColumnWidth))                
            
            # Don't set Location width. It stretches to fill remaining vacant width

            dateTextWidth = int(metrics.boundingRect("2222-22-22").width())
            header.resizeSection(4,  floor(1.75 * dateTextWidth))

            timeTextWidth = int(metrics.boundingRect("22:22").width())
            header.resizeSection(5,  floor(1.75 * timeTextWidth))
            
            speciesColumnWidth = int(metrics.boundingRect("Species").width())
            header.resizeSection(6,  floor(1.45 * speciesColumnWidth))                
            
            textHeight= int(metrics.boundingRect("2222").height())
            for R in range(self.tblList.rowCount()):
                self.tblList.setRowHeight(R, int(textHeight * 1.1))  
        
        if self.listType == "Find Results":

            thisColumnWidth = int(metrics.boundingRect("Checklist Comments").width())
            header.resizeSection(0,  floor(1.5 * thisColumnWidth))                

            thisColumnWidth = int(metrics.boundingRect("Some Location's Long Name").width())
            header.resizeSection(1,  floor(1.75 * thisColumnWidth))               

            dateTextWidth = int(metrics.boundingRect("2222-22-22").width())
            header.resizeSection(2,  floor(1.75 * dateTextWidth))

            # Don't set Comments width. It stretches to fill remaining vacant width
            textHeight= int(metrics.boundingRect("2222").height())
            for R in range(self.tblList.rowCount()):
                self.tblList.setRowHeight(R, int(textHeight * 1.1))
        
        self.lblLocation.setFont(QFont("Helvetica", floor(fontSize * 1.4 )))
        self.lblLocation.setStyleSheet("QLabel { font: bold }");
        self.lblDateRange.setFont(QFont("Helvetica", floor(fontSize * 1.2 )))
        self.lblDateRange.setStyleSheet("QLabel { font: bold }");
        self.lblDetails.setFont(QFont("Helvetica", floor(fontSize * 1.2 )))
        self.lblDetails.setStyleSheet("QLabel { font: bold }");
        self.lblSpecies.setFont(QFont("Helvetica", fontSize))
        self.lblFind.setFont(QFont("Helvetica", fontSize))
        self.btnShowLocation.setFont(QFont("Helvetica", fontSize))
        self.btnShowLocation.setStyleSheet("QLabel { font: bold }");
         
        windowWidth =  int(800  * scaleFactor)
        windowHeight = int(580 * scaleFactor)
        self.resize(windowWidth, windowHeight)
           
           
    def afterSort(self, column, order):
        metrics = self.tblList.fontMetrics()
        textHeight = int(metrics.boundingRect("2222").height())

        for R in range(self.tblList.rowCount()):
            self.tblList.setRowHeight(R, int(textHeight * 1.1))       
           
        
    def ChangedFindText(self):
        searchString = self.txtFind.text().lower()
        rowCount = self.tblList.rowCount()
        columnCount = self.tblList.columnCount()
        
        for r in range(rowCount):
            wholeRowText = ""
            
            for c in range(columnCount):

                wholeRowText = wholeRowText + self.tblList.item(r,  c).text().lower() + " "
            
            if searchString in wholeRowText:
                self.tblList.setRowHidden(r,  False)
            
            else:
                self.tblList.setRowHidden(r,  True)


    def CreateLocation(self):
        location = self.lblLocation.text()
        sub = code_Location.Location()
        sub.mdiParent = self.mdiParent
        sub.FillLocation(location)  
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)        
        sub.show()        


    def html(self):
    
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
                padding: 1px;
            }
            th {
                text-align: left;
            }
            </style>
            <body>
            """
            
        html = html + (
            "<H1>" + 
            self.lblLocation.text() + 
            "</H1>"
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
            self.lblSpecies.text() + 
            "</H3>"
            )        
        
        html=html + (
            "<font size='2'>" +
            "<table width='100%'>" +
            " <tr>"
            )
            
        # add table content depending on type of list we're displaying
        
        if self.listType == "Species":
            html=html + (    
                "<th>Species</th>" +
                "<th>First</th> " +
                "<th>       </th> " +
                "<th>Latest</th>" +
                "<th>Checklists</th>" +
                "</tr>"
                )
                
            for r in range(self.tblList.rowCount()):
                html = html + (
                "<tr>" +
                "<td>" +
                self.tblList.item(r, 1).text() +
                "</td>" +
                "<td>" +
                self.tblList.item(r, 2).text() +
                "</td>" +
                "<td>" +
                "  " +
                "</td>" +
                "<td>" +
                self.tblList.item(r, 3).text() +
                "</td>" +
                "<td>" +
                self.tblList.item(r, 4).text() +
                "</td>" +
                "</tr>"
                )
            html = html + "</table>"

        if self.listType == "Locations":
            html=html + (    
                "<th>Location</th>" +
                "<th>First</th> " +
                "<th>Latest</th>" +
                "</tr>"
                )
                
            for r in range(self.tblList.rowCount()):
                html = html + (
                "<tr>" +
                "<td>" +
                self.tblList.item(r, 0).text() +
                "</td>" +
                "<td>" +
                self.tblList.item(r, 1).text() +
                "</td>" +
                "<td>" +
                self.tblList.item(r, 2).text() +
                "</td>" +
                "</tr>"
                )
            html = html + "</table>"

        if self.listType == "Single Checklist":
            html=html + (    
                "<th>Taxa</th>" +
                "<th>Count</th> " +
                "<th>Comments</th>" +
                "</tr>"
                )
                
            for r in range(self.tblList.rowCount()):
                html = html + (
                "<tr>" +
                "<td>" +
                self.tblList.item(r, 1).text() +
                "</td>" +
                "<td>" +
                self.tblList.item(r, 2).text() +
                "</td>" +
                "<td>" +
                self.tblList.item(r, 3).text() +
                "</td>" +
                "</tr>"
                )
            html = html + (
                "</table>" +
                "<h2>" +
                self.txtChecklistComments.toPlainText() +
                "</h2>"
            )

        if self.listType == "Checklists":
            html=html + (    
                "<th>Country</th>" +
                "<th>State</th> " +
                "<th>County</th>" +
                "<th>Location</th>" +
                "<th>Date</th>" +
                "<th>Time</th>" +
                "<th>Species</th>" +
                "</tr>"
                )
                
            for r in range(self.tblList.rowCount()):
                html = html + (
                "<tr>" +
                "<td>" +
                self.tblList.item(r, 0).text() +
                "</td>" +
                "<td>" +
                self.tblList.item(r, 1).text() +
                "</td>" +
                "<td>" +
                self.tblList.item(r, 2).text() +
                "</td>" +
                "<td>" +
                self.tblList.item(r, 3).text() +
                "</td>" +
                "<td>" +            
                self.tblList.item(r, 4).text() +
                "</td>" +
                "<td>" +
                self.tblList.item(r, 5).text() +
                "</td>" +
                "<td>" +
                self.tblList.item(r, 6).text() +
                "</td>" +
                "</tr>"
                )
            html = html + "</table>"                

        html = html + (
            "<font size>" +            
            "</body>" +
            "</html>"
            )
            
        return(html)
        

    def FillSpecies(self, filter): 
        
        self.filter = filter
        self.listType = "Species"
        checklistDetails = ""

        # set up a bold font to use in columns as needed
        font = QFont()
        font.setBold(True)        
       
        if filter.getLocationType() == "Location":
            self.btnShowLocation.setVisible(True)
                  
        # set up tblList column headers and widths
        self.tblList.setShowGrid(False)        
        header = self.tblList.horizontalHeader()
        header.setVisible(True)   
        
        # if this is a species list (not a single checklist), get data and set 4 columns
        if filter.getChecklistID() == "":
                        
            thisWindowList = self.mdiParent.db.GetSpeciesWithData(filter,  [], "Subspecies")
                    
            if len(thisWindowList) == 0:
                return(False)                    
                    
            self.tblList.setRowCount(len(thisWindowList))
            self.tblList.setColumnCount(6)
            self.tblList.setHorizontalHeaderLabels(['Tax', 'Species', 'First',  'Last', 'Checklists', '% of Checklists'])
            #header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch) 
            # header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            self.tblList.setItemDelegateForColumn(5, code_FloatDelegate.FloatDelegate(2))

            # add species and dates to table row by row        
            R = 0
            for species in thisWindowList:   
                taxItem = QTableWidgetItem()
                taxItem.setData(Qt.DisplayRole, R+1)
                speciesItem = QTableWidgetItem()
                speciesItem.setText(species[0])
                speciesItem.setData(Qt.UserRole,  species[4])                
                firstItem = QTableWidgetItem()
                firstItem.setData(Qt.DisplayRole, species[1])
                lastItem = QTableWidgetItem()
                lastItem.setData(Qt.DisplayRole, species[2])
                self.tblList.setItem(R, 0, taxItem)    
                checklistCountItem = QTableWidgetItem()
                checklistCountItem.setData(Qt.DisplayRole, species[5])
                checklistCountItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)
                
                percentageItem = QTableWidgetItem()
                percentageItem.setData(Qt.DisplayRole, species[6])
                
                self.tblList.setItem(R, 1, speciesItem)
                self.tblList.item(R, 1).setFont(font)
                
                # set the species to gray if it's not a true species
                if " x " in species[0] or "sp." in species[0] or "/" in species[0]:
                    self.tblList.item(R, 1).setForeground(Qt.gray)
                else:
                    self.tblList.item(R, 1).setForeground(code_Stylesheet.speciesColor)

                self.tblList.setItem(R, 2, firstItem)
                self.tblList.setItem(R, 3, lastItem)
                self.tblList.setItem(R, 4, checklistCountItem)
                self.tblList.setItem(R, 5, percentageItem)
                self.currentSpeciesList.append(species[0])
                R = R + 1    
                
            # hide the checklist comments box, since  we're not showing a single checklist
            self.txtChecklistComments.setVisible(False)
                            
            self.tblList.addAction(self.actionSetFirstDateFilter)
            self.tblList.addAction(self.actionSetLastDateFilter)
            self.tblList.addAction(self.actionSetSpeciesFilter)
                
        # if this is limited to a checklist, set 3 columns
        else:
            
            self.listType = "Single Checklist"

            thisWindowList = self.mdiParent.db.GetSightings(filter)  
            self.tblList.setRowCount(len(thisWindowList))            
            self.tblList.setColumnCount(4)
            self.tblList.setHorizontalHeaderLabels(['Tax', 'Species', 'Count',  "Comment"])    
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            self.tblList.setWordWrap(True)
            
            # add species and dates to table row by row        
            R = 0
            for s in thisWindowList:    
                
                taxItem = QTableWidgetItem()
                taxItem.setData(Qt.DisplayRole, R+1)
                
                speciesItem = QTableWidgetItem()
                speciesItem.setText(s["commonName"])
                speciesItem.setData(Qt.UserRole,  s["commonName"])
                
                countItem = QTableWidgetItem()
                count = s["count"]
                if count != "X":
                    count = int(count)
                countItem.setData(Qt.DisplayRole, count)
                countItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)

                commentItem = QTableWidgetItem()
                commentItem.setText(s["speciesComments"])                
                
                self.tblList.setItem(R, 0, taxItem)    
                self.tblList.setItem(R, 1, speciesItem)
                self.tblList.item(R, 1).setFont(font)
                self.tblList.setItem(R, 2, countItem)
                self.tblList.setItem(R,  3,  commentItem)
                
                # set the species to gray if it's not a true species
                if " x " in s["commonName"] or "sp." in s["commonName"] or "/" in s["commonName"]:
                    self.tblList.item(R, 1).setForeground(Qt.gray)
                else:
                    self.tblList.item(R, 1).setForeground(code_Stylesheet.speciesColor)                
        
                self.currentSpeciesList.append(s["commonName"])
                
                R = R + 1     
            
            # resize all rows as necessary to show full comments
            # without this call, Qt sometimes truncates the comments
             
            # shorten  the height of tblList to create room for checklist comments box
            self.txtChecklistComments.setVisible(True)
            
            # fill checklist comments text
            checklistComments = thisWindowList[0]["checklistComments"]
            if checklistComments == "":
                checklistComments = "No checklist comments."
            self.txtChecklistComments.appendPlainText(checklistComments)
            
            #fill checklist details of time, distance, and checklist protoccol
            time = thisWindowList[0]["time"]        
            protocol = thisWindowList[0]["protocol"]
            duration = thisWindowList[0]["duration"]
            distance = thisWindowList[0]["distance"]
            observerCount = thisWindowList[0]["observers"]
            
            if time != ""and time is not None:
                time = time + ",  "
                
            if duration != "0" and duration is not None:
                duration = duration + " min,  "
            else:
                duration = ""
                
            if distance != "" and distance is not None:
                distance = distance + " km,  "
                
            if observerCount != "" and observerCount is not None:
                observerCount = observerCount + " obs,  "
            
            if "Traveling" in protocol:
                protocol ="Traveling"
            if "Stationary" in protocol:
                protocol ="Stationary"
            if "Casual" in protocol:
                protocol ="Casual"
                
            checklistDetails = (
                time + 
                duration +
                distance +
                observerCount  +
                protocol
                )
                
            self.tblList.addAction(self.actionSetDateFilter)
            self.tblList.addAction(self.actionSetSpeciesFilter)
            self.tblList.addAction(self.actionSetLocationFilter)
                            
        speciesCount = self.mdiParent.db.CountSpecies(self.currentSpeciesList)
        
        self.lblSpecies.setText("Species: " + str(speciesCount))
        
        if speciesCount != self.tblList.rowCount():
            self.lblSpecies.setText(
                "Species: " + 
                str(speciesCount) + 
                " + " + 
                str(self.tblList.rowCount() - speciesCount) + 
                " taxa"
                )

        self.mdiParent.SetChildDetailsLabels(self, filter)
        
        if checklistDetails != "":
            self.lblDetails.setText(checklistDetails)        

        self.setWindowTitle(filter.buildWindowTitle("Species", self.mdiParent.db, count=self.tblList.rowCount(), countUnit="Species"))
        
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_bird.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)      
        
        self.scaleMe()
        self.resizeMe()
        
        # tell MainWindow that we succeeded filling the list
        return(True)


    def FillChecklists(self, filter): 

        self.filter = filter
        self.listType = "Checklists"
        
        # get species data from db 
        checklists = self.mdiParent.db.GetChecklists(filter)
        
        # abort if no checklists matched filter
        if len(checklists) == 0:
            return(False)
       
       # set up tblList column headers and widths
        self.tblList.setColumnCount(7)
        self.tblList.setRowCount(len(checklists))
        self.tblList.horizontalHeader().setVisible(True)
        self.tblList.setHorizontalHeaderLabels(['Country', 'State', 'County',  'Location', 'Date', 'Time',  'Species'])
        header = self.tblList.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)        
        self.tblList.setShowGrid(False)

        # add species and dates to table row by row        
        R = 0
        for c in checklists:    
            countryItem = QTableWidgetItem()
            countryItem.setData(Qt.UserRole, c[0])  #store checklistID for future retreaval                     
            countryName = self.mdiParent.db.GetCountryName(c[1][0:2])
            countryItem.setText(countryName)            
            
            stateItem = QTableWidgetItem()
            stateName = self.mdiParent.db.GetStateName(c[1])
            stateItem.setText(stateName)
            
            countyItem = QTableWidgetItem()
            countyItem.setText(c[2])
            
            locationItem = QTableWidgetItem()
            locationItem.setText(c[3])
            
            dateItem = QTableWidgetItem()
            dateItem.setText(c[4])

            timeItem = QTableWidgetItem()
            timeItem.setText(c[5])
            
            speciesCountItem = QTableWidgetItem()
            speciesCountItem.setData(Qt.DisplayRole, c[6])  
            speciesCountItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)
            
            self.tblList.setItem(R, 0, countryItem)    
            self.tblList.setItem(R, 1, stateItem)
            self.tblList.setItem(R, 2, countyItem)
            self.tblList.setItem(R, 3, locationItem)
            self.tblList.setItem(R, 4, dateItem)
            self.tblList.setItem(R, 5, timeItem)
            self.tblList.setItem(R, 6, speciesCountItem)
            R = R + 1
        
        self.lblSpecies.setText("Checklists: " + str(self.tblList.rowCount()))

        self.mdiParent.SetChildDetailsLabels(self, filter)

        self.setWindowTitle(filter.buildWindowTitle("Checklists", self.mdiParent.db, count=self.tblList.rowCount(), countUnit="Checklists"))

        self.txtChecklistComments.setVisible(False)

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_checklists.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)  
        
        self.tblList.addAction(self.actionSetDateFilter)
        self.tblList.addAction(self.actionSetCountryFilter)
        self.tblList.addAction(self.actionSetStateFilter)
        self.tblList.addAction(self.actionSetCountyFilter)
        self.tblList.addAction(self.actionSetLocationFilter)

        self.scaleMe()
        self.resizeMe()
        
        # alert MainWindow that we finished fill data successfully
        return(True)


    def FillFindChecklists(self,  foundList):
        
        self.filter = filter
        self.listType = "Find Results"        
                      
       # set up tblList column headers and widths
        self.tblList.setColumnCount(4)
        self.tblList.setRowCount(len(foundList))
        self.tblList.horizontalHeader().setVisible(True)
        self.tblList.setHorizontalHeaderLabels(['Type', 'Location', 'Date', 'Found'])
        header = self.tblList.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)        

        self.tblList.setShowGrid(False)
        self.tblList.setWordWrap(True)

        # add checklists and fount term to table row by row        
        R = 0
        for c in foundList:  
            typeItem = QTableWidgetItem()
            typeItem.setData(Qt.UserRole, c[1])  #store checklistID for future retreaval                     
            typeItem.setText(c[0])
            
            locationItem = QTableWidgetItem()
            locationItem.setText(c[2])
            
            dateItem = QTableWidgetItem()
            dateItem.setText(c[3])

            foundTextItem = QTableWidgetItem()
            foundTextItem.setText(c[4])

            self.tblList.setItem(R, 0, typeItem)                
            self.tblList.setItem(R, 1, locationItem)
            self.tblList.setItem(R, 2, dateItem)
            self.tblList.setItem(R, 3, foundTextItem)
            R = R + 1
        
        self.setWindowTitle("Find Results")        
        self.lblLocation.setVisible(False)
        self.lblDateRange.setVisible(False)
        
        if self.lblDetails.text() != "":
            self.lblDetails.setVisible(True)
        else:
            self.lblDetails.setVisible(False)
            
        self.lblSpecies.setText("Checklists: " + str(self.tblList.rowCount()))
        self.txtChecklistComments.setVisible(False)
        
        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_find.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)          

        self.scaleMe()
        self.resizeMe()


    def FillLocations(self, filter): 
        
        self.filter = filter
        self.listType = "Locations"
       
        self.btnShowLocation.setVisible(False)
        self.lblDetails.setVisible(False)
                  
       # set up tblList column headers and widths
        self.tblList.setShowGrid(False)        
        header = self.tblList.horizontalHeader()
        header.setVisible(True)   
        
        thisWindowList = self.mdiParent.db.GetLocations(filter,  "Dates")
        
        if len(thisWindowList) == 0:
            return(False)

        # set 3 columns and header titles
        self.tblList.setRowCount(len(thisWindowList))
        self.tblList.setColumnCount(3)
        self.tblList.setHorizontalHeaderLabels(['Location', 'First',  'Last'])
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)        

        # add locations and dates to table row by row        
        R = 0
        for loc in thisWindowList:    
            locationItem = QTableWidgetItem()
            locationItem.setText(loc[0])
            firstItem = QTableWidgetItem()
            firstItem.setData(Qt.DisplayRole, loc[1])
            lastItem = QTableWidgetItem()
            lastItem.setData(Qt.DisplayRole, loc[2])
            self.tblList.setItem(R, 0, locationItem)
            self.tblList.setItem(R, 1, firstItem)
            self.tblList.setItem(R, 2, lastItem)
            R = R + 1    
            
            # hide the checklist comments box, since  we're not showing a single checklist
            self.txtChecklistComments.setVisible(False)
            
            # hide the checklist details label, since  we're not showing a single checklist                
            self.lblDetails.setText("")
            
        locationCount = self.tblList.rowCount()
        
        self.lblSpecies.setText("Locations: " + str(locationCount))
        
        self.mdiParent.SetChildDetailsLabels(self, filter)

        self.setWindowTitle(filter.buildWindowTitle("Locations", self.mdiParent.db, count=locationCount, countUnit="Locations"))

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_location.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)  

        self.tblList.addAction(self.actionSetLocationFilter)
        self.tblList.addAction(self.actionSetFirstDateFilter)
        self.tblList.addAction(self.actionSetLastDateFilter)
        
        self.scaleMe()
        self.resizeMe()
        
        return(True)


    def tblListClicked(self):
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        currentRow = self.tblList.currentRow()
        currentColumn = self.tblList.currentColumn()
        
        if self.listType in ["Species", "Single Checklist"]:
            if currentColumn in [0, 5]:
                # the taxonomy order or percentage column was clicked, so abort. We won't create a report.
                # turn off the hourglass cursor before exiting
                QApplication.restoreOverrideCursor()     
                return
                
            if currentColumn== 1:
                # species column has been clicked so create individual window for that species
                speciesName = self.tblList.item(currentRow,  1).text()
                
                # abort if a spuh or slash species was clicked (we can't show an individual for this)
                # if "sp." in speciesName or "/" in speciesName:
                    # QApplication.restoreOverrideCursor()
                    # return
                
                sub = code_Individual.Individual()
                sub.mdiParent = self.mdiParent
                sub.FillIndividual(speciesName)
                
            if currentColumn in [2, 3]:
                # If list is already a checklist, we abort
                if self.filter.getChecklistID() != "":
                    QApplication.restoreOverrideCursor()  
                    return
                    
                # date column has been clicked so create species list frame for that dateArray
                date = self.tblList.item(currentRow,  self.tblList.currentColumn()).text()
                speciesName = self.tblList.item(currentRow,  1).data(Qt.UserRole)

                filter = code_Filter.Filter()
                filter.setSpeciesName(speciesName)
                filter.setStartDate(date)
                filter.setEndDate(date)
                
                # get all checklists that have this date and species
                checklists = self.mdiParent.db.GetChecklists(filter)
                
                # see if only one checklist meets filter
                # create a SpeciesList window to display a checklist if only one is found
                # create a checklists list window if more than one if found
                if len(checklists) == 1:
                    filter.setSpeciesName("")
                    filter.setChecklistID(checklists[0][0])
                    filter.setLocationType("Location")
                    filter.setLocationName(checklists[0][3])
                    sub = Lists()
                    sub.mdiParent = self.mdiParent
                    sub.FillSpecies(filter) 
                if len(checklists) > 1:
                    sub = Lists()
                    sub.mdiParent = self.mdiParent
                    sub.FillChecklists(filter)

            if currentColumn == 4:
                # If list is already a checklist, we abort
                if self.filter.getChecklistID() != "":
                    QApplication.restoreOverrideCursor()  
                    return
                    
                # checklist count column has been clicked so create checklist list for widget's filter and species
                speciesName = self.tblList.item(currentRow,  1).text()

                filter = deepcopy(self.filter)
                filter.setSpeciesName(speciesName)
                
                # get all checklists that have this date and species
                checklists = self.mdiParent.db.GetChecklists(filter)
                
                if len(checklists) > 0:
                    sub = Lists()
                    sub.mdiParent = self.mdiParent
                    sub.FillChecklists(filter)

        if self.listType == "Locations":
                
            if currentColumn == 0:
                # species column has been clicked so create individual window for that species
                locationName = self.tblList.item(currentRow,  0).text()
                
                sub = code_Location.Location()
                sub.mdiParent = self.mdiParent
                sub.FillLocation(locationName)
                
            if currentColumn > 0:

                # date column has been clicked so create species list frame for that dateArray
                clickedText = self.tblList.item(currentRow,  self.tblList.currentColumn()).text()
                date = clickedText.split(" ")[0]
                time = clickedText.split(" ")[1]
                locationName = self.tblList.item(currentRow,  0).text()

                filter = code_Filter.Filter()
                filter.setLocationName(locationName)
                filter.setLocationType("Location")
                filter.setStartDate(date)
                filter.setEndDate(date)
                filter.setTime(time)
                
                # get all checklists that have this date and location
                checklists = self.mdiParent.db.GetChecklists(filter)
                
                # see if only one checklist meets filter
                # create a SpeciesList window to display a checklist if only one is found
                # create a checklists list window if more than one if found
                if len(checklists) == 1:
                    filter.setSpeciesName("")
                    filter.setChecklistID(checklists[0][0])
                    filter.setLocationType("Location")
                    filter.setLocationName(checklists[0][3])
                    sub = Lists()
                    sub.mdiParent = self.mdiParent
                    sub.FillSpecies(filter) 
                if len(checklists) > 1:
                    sub = Lists()
                    sub.mdiParent = self.mdiParent
                    sub.FillChecklists(filter)

        if self.listType in ["Checklists", "Find Results"]:

            checklistID = self.tblList.item(currentRow, 0).data(Qt.UserRole)
            
            filter = code_Filter.Filter()
            filter.setChecklistID(checklistID)
            
            location = self.mdiParent.db.GetLocations(filter)[0]
            date = self.mdiParent.db.GetDates(filter)[0]

            filter = code_Filter.Filter()
            filter.setChecklistID(checklistID)
            filter.setLocationName(location)
            filter.setLocationType("Location")
            filter.setStartDate(date)
            filter.setEndDate(date)

            sub = Lists()
            sub.mdiParent = self.mdiParent
            sub.FillSpecies(filter)
            
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)        
        sub.show() 
        sub.resizeMe()
        QApplication.restoreOverrideCursor()  
        

