# import GUI form for this class
import form_DateTotals

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
    )


class DateTotals(QMdiSubWindow, form_DateTotals.Ui_frmDateTotals):

    # create "resized" as a signal that the window can emit
    # we respond to this signal with the form's resizeMe method below
    resized = Signal()            
    
    
    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose,True)
        self.mdiParent = ""        
        self.tblYearTotals.itemDoubleClicked.connect(self.YearTableClicked)
        self.tblMonthTotals.itemDoubleClicked.connect(self.MonthTableClicked)
        self.tblDateTotals.itemDoubleClicked.connect(self.DateTableClicked)        
        self.tblYearTotals.setShowGrid(False)
        self.tblDateTotals.setShowGrid(False)
        self.tblMonthTotals.setShowGrid(False)
        self.resized.connect(self.resizeMe) 
        self.tabDateTotals.setCurrentIndex(0)
        self.filter = code_Filter.Filter()

        self.tblDateTotals.addAction(self.actionSetDateFilter)
        self.tblMonthTotals.addAction(self.actionSetDateFilterToMonth)
        self.tblYearTotals.addAction(self.actionSetDateFilterToYear)
        
        self.actionSetDateFilter.triggered.connect(self.setDateFilter)
        self.actionSetDateFilterToMonth.triggered.connect(self.setSeasonalRangeFilterToMonth)
        self.actionSetDateFilterToYear.triggered.connect(self.setDateFilterToYear)


    def DateTableClicked(self):
        sub = code_Lists.Lists()
        sub.mdiParent = self.mdiParent 
        
        date = self.tblDateTotals.item(self.tblDateTotals.currentRow(),  1).text()        
        tempFilter = deepcopy(self.filter)
        tempFilter.setStartDate(date)
        tempFilter.setEndDate(date)

        if self.tblDateTotals.currentColumn() in [0, 1, 2]:
            sub.FillSpecies(tempFilter)

        if self.tblDateTotals.currentColumn() == 3:
            sub.FillChecklists(tempFilter)
            
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)
        sub.show()
        sub.scaleMe()


    def MonthTableClicked(self):
        month = self.tblMonthTotals.item(self.tblMonthTotals.currentRow(),  1).text() 
        monthRange = ["Jan",  "Feb",  "Mar",  "Apr", "May",   "Jun",  "Jul",  "Aug",  "Sep",  "Oct",  "Nov",  "Dec"]
        monthNumberStrings = ["01",  "02",  "03",  "04",  "05",  "06",  "07",  "08",  "09",  "10",  "11",  "12"]
        monthNumber = monthRange.index(month)
        # find last day of the selected month
        if month in ["Apr", "Jun",  "Sep",  "Nov"]: lastDay = "30"
        if month in ["Jan",  "Mar", "May",  "Jul",  "Aug", "Oct",  "Dec"]: lastDay = "31"
        if month == "Feb": lastDay = "29"
        
        sub = code_Lists.Lists()
        sub.mdiParent = self.mdiParent
        
        tempFilter = deepcopy(self.filter)
        tempFilter.setStartSeasonalMonth(monthNumberStrings[monthNumber])
        tempFilter.setStartSeasonalDay("01")
        tempFilter.setEndSeasonalMonth(monthNumberStrings[monthNumber])
        tempFilter.setEndSeasonalDay(lastDay)
        
        if self.tblMonthTotals.currentColumn() in [0, 1, 2]:
            sub.FillSpecies(tempFilter)

        if self.tblMonthTotals.currentColumn() == 3:
            sub.FillChecklists(tempFilter)
    
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)
        sub.show()
        sub.scaleMe()


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
            "Date Totals" + 
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
            "Year Totals" + 
            "</H3>"
            )        
            
        html=html + (
            "<font size='2'>" +
            "<table width='100%'>" +
            " <tr>"
            )
                    
        html=html + (    
            "<th>Rank</th>" +
            "<th>Year</th> " +
            "<th>Species</th>" +
            "<th>Checklists</th>" +
            "</tr>"
            )
            
        for r in range(self.tblYearTotals.rowCount()):
            html = html + (
            "<tr>" +
            "<td>" +
            self.tblYearTotals.item(r, 0).text() +
            "</td>" +
            "<td>" +
            self.tblYearTotals.item(r, 1).text() +
            "</td>" +
            "<td>" +
            self.tblYearTotals.item(r, 2).text() +
            "</td>" +
            "<td>" +
            self.tblYearTotals.item(r, 3).text() +
            "</td>" +
            "</tr>"
            )
            
        html = html + (
            "</table>"
            "</font size>"
            )

        html = html + (
            "<H3>" + 
            "Month Totals" + 
            "</H3>"
            )        
            
        html=html + (
            "<font size='2'>" +
            "<table width='100%'>" +
            " <tr>"
            )
                    
        html=html + (    
            "<th>Rank</th>" +
            "<th>Month</th> " +
            "<th>Species</th>" +
            "<th>Checklists</th>" +
            "</tr>"
            )
            
        for r in range(self.tblMonthTotals.rowCount()):
            html = html + (
            "<tr>" +
            "<td>" +
            self.tblMonthTotals.item(r, 0).text() +
            "</td>" +
            "<td>" +
            self.tblMonthTotals.item(r, 1).text() +
            "</td>" +
            "<td>" +
            self.tblMonthTotals.item(r, 2).text() +
            "</td>" +
            "<td>" +
            self.tblMonthTotals.item(r, 3).text() +
            "</td>" +
            "</tr>"
            )
            
        html = html + (
            "</table>"
            "</font size>"
            )

        html = html + (
            "<H3>" + 
            "Date Totals" + 
            "</H3>"
            )        
            
        html=html + (
            "<font size='2'>" +
            "<table width='100%'>" +
            " <tr>"
            )
                    
        html=html + (    
            "<th>Rank</th>" +
            "<th>Date</th> " +
            "<th>Species</th>" +
            "<th>Checklists</th>" +
            "</tr>"
            )
            
        for r in range(self.tblDateTotals.rowCount()):
            html = html + (
            "<tr>" +
            "<td>" +
            self.tblDateTotals.item(r, 0).text() +
            "</td>" +
            "<td>" +
            self.tblDateTotals.item(r, 1).text() +
            "</td>" +
            "<td>" +
            self.tblDateTotals.item(r, 2).text() +
            "</td>" +
            "<td>" +
            self.tblDateTotals.item(r, 3).text() +
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


    def YearTableClicked(self):

        sub = code_Lists.Lists()
        sub.mdiParent = self.mdiParent

        year = self.tblYearTotals.item(self.tblYearTotals.currentRow(),  1).text()                
        startDate = year + "-01-01"
        endDate = year + "-12-31"
        
        tempFilter = deepcopy(self.filter)
        tempFilter.setStartDate(startDate)
        tempFilter.setEndDate(endDate)
        
        if self.tblYearTotals.currentColumn() in [0, 1, 2]:
            sub.FillSpecies(tempFilter)

        if self.tblYearTotals.currentColumn() == 3:
            sub.FillChecklists(tempFilter)
            
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)
        sub.show()
        sub.scaleMe()


    def FillDateTotals(self,  filter):
        
        self.filter = filter
        
        # find all years, months, and dates in db
        dbYears = set()
        dbMonths = set()
        dbDates = set()   
        dbFilteredSightings = []
        yearDict = defaultdict()
        monthDict = defaultdict()
        dateDict = defaultdict()
        
        minimalSightingList = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)
        cf = self.mdiParent.db.CompileFilter(filter)

        for sighting in minimalSightingList:

            # Consider only full species, not slash or spuh or hybrid entries
            commonName = sighting["commonName"]
            if ("/" not in commonName) and ("sp." not in commonName) and " x " not in commonName:

                if self.mdiParent.db.TestSightingCompiled(sighting, cf) is True:
                    dbYears.add(sighting["date"][0:4])
                    dbMonths.add(sighting["date"][5:7])
                    dbDates.add(sighting["date"])
                    dbFilteredSightings.append(sighting)
                    
                    if sighting["date"][0:4] not in yearDict.keys():
                        yearDict[sighting["date"][0:4]] = [sighting]
                    else:
                        yearDict[sighting["date"][0:4]].append(sighting)
                    
                    if sighting["date"][5:7] not in monthDict.keys():
                        monthDict[sighting["date"][5:7]] = [sighting]
                    else:
                        monthDict[sighting["date"][5:7]].append(sighting)
                    
                    if sighting["date"] not in dateDict.keys():
                        dateDict[sighting["date"]] = [sighting]
                    else:
                        dateDict[sighting["date"]].append(sighting)

        # check that we have at least one sighting to work with
        # otherwise, abort so MainWindow can post message to user
        if len(yearDict) == 0:
            return(False)
        
        # set numbers of rows for each tab's grid (years, months, dates)
        self.tblYearTotals.setRowCount(len(dbYears)+1)
        self.tblYearTotals.setColumnCount(4)
        self.tblMonthTotals.setRowCount(len(dbMonths)+1)
        self.tblMonthTotals.setColumnCount(4)
        self.tblDateTotals.setRowCount(len(dbDates)+1)
        self.tblDateTotals.setColumnCount(4)

        yearArray = []

        for year in dbYears:
            yearSpecies = set()
            yearChecklists = set()
            for s in yearDict[year]:
                yearSpecies.add(s["commonName"])
                yearChecklists.add(s["checklistID"])
            yearArray.append([len(yearSpecies),  year, len(yearChecklists)])
        yearArray.sort(reverse=True)
        R = 0
        for year in yearArray:            
            rankItem = QTableWidgetItem()
            rankItem.setData(Qt.DisplayRole, R+1)
            yearItem = QTableWidgetItem()
            yearItem.setText(year[1])
            yearTotalItem = QTableWidgetItem()
            yearTotalItem.setData(Qt.DisplayRole, year[0])
            yearTotalItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)
            yearChecklistTotalItem = QTableWidgetItem()
            yearChecklistTotalItem.setData(Qt.DisplayRole, year[2])
            yearChecklistTotalItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)
            self.tblYearTotals.setItem(R, 0, rankItem)    
            self.tblYearTotals.setItem(R, 1, yearItem)
            self.tblYearTotals.setItem(R, 2, yearTotalItem)
            self.tblYearTotals.setItem(R, 3, yearChecklistTotalItem)
            R = R + 1

        monthArray = []
        for month in dbMonths:
            monthSpecies = set()
            monthChecklists = set()
            for s in monthDict[month]:
                monthSpecies.add(s["commonName"])
                monthChecklists.add(s["checklistID"])
            monthArray.append([len(monthSpecies),  month, len(monthChecklists)])
        monthArray.sort(reverse=True)
        R = 0
        for month in monthArray:
            if month[1] == "01":
                month[1] = "Jan"
            if month[1] == "02":
                month[1] = "Feb"
            if month[1] == "03":
                month[1] = "Mar"
            if month[1] == "04":
                month[1] = "Apr"
            if month[1] == "05":
                month[1] = "May"
            if month[1] == "06":
                month[1] = "Jun"
            if month[1] == "07":
                month[1] = "Jul"
            if month[1] == "08":
                month[1] = "Aug"
            if month[1] == "09":
                month[1] = "Sep"
            if month[1] == "10":
                month[1] = "Oct"
            if month[1] == "11":
                month[1] = "Nov"
            if month[1] == "12":
                month[1] = "Dec"        
            rankItem = QTableWidgetItem()
            rankItem.setData(Qt.DisplayRole, R+1)
            monthItem= QTableWidgetItem()
            monthItem.setText(month[1])
            monthTotalItem = QTableWidgetItem()
            monthTotalItem.setData(Qt.DisplayRole, month[0])
            monthTotalItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)         
            monthChecklistTotalItem = QTableWidgetItem()
            monthChecklistTotalItem.setData(Qt.DisplayRole, month[2])   
            monthChecklistTotalItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)         
            self.tblMonthTotals.setItem(R, 0, rankItem)    
            self.tblMonthTotals.setItem(R, 1, monthItem)
            self.tblMonthTotals.setItem(R, 2, monthTotalItem)
            self.tblMonthTotals.setItem(R, 3, monthChecklistTotalItem)
            R = R + 1
        R = -1
        
        dateArray = []
                
        for date in dbDates:
            dateSpecies = set()
            dateChecklists = set()
            for s in dateDict[date]:
                dateSpecies.add(s["commonName"])
                dateChecklists.add(s["checklistID"])
            dateArray.append([len(dateSpecies),  date, len(dateChecklists)])
                        
        dateArray.sort(reverse=True)
        R = 0
        rank = 1
        lastDateTotal = 0
        for date in dateArray:            
            dateItem = QTableWidgetItem()
            dateItem.setText(date[1][0:4] + "-" + date[1][5:7] + "-" + date[1][8:])
            dateTotalItem = QTableWidgetItem()
            dateTotalItem.setData(Qt.DisplayRole, date[0])
            dateTotalItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)                     
            if date[0] != lastDateTotal:
                rank = R+1
            rankItem = QTableWidgetItem()
            rankItem.setData(Qt.DisplayRole, rank)
            dateChecklistTotalItem = QTableWidgetItem()
            dateChecklistTotalItem.setData(Qt.DisplayRole, date[2])    
            dateChecklistTotalItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)                     
            self.tblDateTotals.setItem(R, 0, rankItem)    
            self.tblDateTotals.setItem(R, 1, dateItem)
            self.tblDateTotals.setItem(R, 2, dateTotalItem)
            self.tblDateTotals.setItem(R, 3, dateChecklistTotalItem)
            lastDateTotal = date[0]
            
            R = R + 1
    
        self.tblYearTotals.horizontalHeader().setVisible(True)
        self.tblMonthTotals.horizontalHeader().setVisible(True)
        self.tblDateTotals.horizontalHeader().setVisible(True)
        self.tblYearTotals.setHorizontalHeaderLabels(['Rank', 'Year', 'Species', 'Checklists'])
        self.tblYearTotals.setSortingEnabled(True)
        self.tblYearTotals.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.tblMonthTotals.setHorizontalHeaderLabels(['Rank', 'Month', 'Species', 'Checklists'])
        self.tblMonthTotals.setSortingEnabled(True)
        self.tblMonthTotals.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.tblDateTotals.setHorizontalHeaderLabels(['Rank', 'Date', 'Species', 'Checklists'])
        self.tblDateTotals.setSortingEnabled(True)
        self.tblDateTotals.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.tblYearTotals.removeRow(self.tblYearTotals.rowCount()-1)
        self.tblMonthTotals.removeRow(self.tblMonthTotals.rowCount()-1)
        self.tblDateTotals.removeRow(self.tblDateTotals.rowCount()-1)
        header = self.tblYearTotals.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header = self.tblMonthTotals.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header = self.tblDateTotals.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self.mdiParent.SetChildDetailsLabels(self, self.filter)

        self.setWindowTitle(self.filter.buildWindowTitle("Date Totals", self.mdiParent.db, count=self.tblDateTotals.rowCount(), countUnit="Dates"))

        if self.lblDetails.text() != "":
            self.lblDetails.setVisible(True)
        else:
            self.lblDetails.setVisible(False)
        
        self.scaleMe()
        self.resizeMe()
        
        # tell MainWindow that all is OK
        return(True)
        
        
    def resizeEvent(self, event):
        #routine to handle events on objects, like clicks, lost focus, gained forcus, etc.        
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)
        
        
    def resizeMe(self):
        
        windowWidth =  self.frameGeometry().width()
        windowHeight = self.frameGeometry().height()
        self.scrollArea.setGeometry(5, 27, windowWidth -10 , windowHeight-35)
   
   
    def setDateFilter(self):        
        currentRow = self.tblDateTotals.currentRow()
        date = self.tblDateTotals.item(currentRow, 1).text()
        self.mdiParent.setDateFilter(date)


    def setSeasonalRangeFilterToMonth(self):        
        currentRow = self.tblMonthTotals.currentRow()
        month = self.tblMonthTotals.item(currentRow, 1).text()
        self.mdiParent.setSeasonalRangeFilter(month)  # month is in format three-letter English abbreviation


    def setDateFilterToYear(self):        
        currentRow = self.tblYearTotals.currentRow()
        year = self.tblYearTotals.item(currentRow, 1).text()
        startDate = year + "-01-01"
        endDate = year + "-12-31"
        self.mdiParent.setDateFilter(startDate, endDate)
        
         
    def scaleMe(self):
               
        scaleFactor = self.mdiParent.scaleFactor
        windowWidth =  int(600  * scaleFactor)
        windowHeight = int(580 * scaleFactor)
        self.resize(windowWidth, windowHeight)
        
        fontSize = self.mdiParent.fontSize
        scaleFactor = self.mdiParent.scaleFactor     
        #scale the font for all widgets in window
        for w in self.layLists.children():
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

        for t in [self.tblYearTotals, self.tblMonthTotals, self.tblDateTotals]:
            header = t.horizontalHeader()
            header.resizeSection(0,  floor(2 * rankTextWidth))
            header.resizeSection(2,  floor(2.5 * rankTextWidth))
            header.resizeSection(3,  floor(2.5 * rankTextWidth))
            t.verticalHeader().setDefaultSectionSize(rowHeight)
 
