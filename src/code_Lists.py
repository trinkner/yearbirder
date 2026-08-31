# import project files
import form_Lists
from code_Stylesheet import YBFont
import code_Filter
import code_SeasonalSort
import code_MediaRefresh
import code_Location
import code_Individual
import code_FloatDelegate
import code_Stylesheet

# import basic Python libraries
from copy import deepcopy
from math import floor

from PySide6.QtGui import (
    QColor,
    QCursor,
    QIcon,
    QPalette,
    QPixmap,
    QFont,
    QFontMetrics,
    QTextCharFormat,
    QTextCursor
    )

from PySide6.QtCore import (
    Qt,
    QUrl,
    Signal
    )

from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QHeaderView,
    QMdiSubWindow,
    QItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate
    )

from PySide6.QtGui import QDesktopServices


def _find_snippet(text, search_term):
    """Return up to five words centered on the word containing search_term.
    Adds leading/trailing ellipsis when surrounding words are omitted."""
    words = text.split()
    if not words:
        return text

    search_lower = search_term.lower()

    # Find the first word that contains the search term
    match_idx = next((i for i, w in enumerate(words) if search_lower in w.lower()), None)

    # If the term spans a word boundary, locate it by character position instead
    if match_idx is None:
        pos = text.lower().find(search_lower)
        if pos >= 0:
            match_idx = max(0, len(text[:pos].split()) - 1)

    if match_idx is None:
        match_idx = 0

    start = max(0, match_idx - 2)
    end   = min(len(words), match_idx + 3)

    snippet = " ".join(words[start:end])
    if start > 0:
        snippet = "…" + snippet
    if end < len(words):
        snippet = snippet + "…"

    return snippet


class _FoundHighlightDelegate(QStyledItemDelegate):
    """Paints the Found column with the matched substring in red."""

    MATCH_COLOR = QColor(code_Stylesheet.CHART_PRIMARY)

    def __init__(self, search_term, parent=None):
        super().__init__(parent)
        self._search = search_term

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        style = opt.widget.style() if opt.widget else QApplication.style()

        # Draw background (selection, hover, etc.) without any text
        opt.text = ""
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if not text:
            return

        text_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)

        search_lower = self._search.lower()
        pos = text.lower().find(search_lower) if self._search else -1

        painter.save()
        painter.setFont(opt.font)

        is_selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        color_group = QPalette.ColorGroup.Active if is_selected else QPalette.ColorGroup.Normal
        color_role  = QPalette.ColorRole.HighlightedText if is_selected else QPalette.ColorRole.Text
        normal_color = opt.palette.color(color_group, color_role)

        if pos < 0:
            painter.setPen(normal_color)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, text)
        else:
            fm = QFontMetrics(opt.font)
            x = text_rect.x()
            segments = [
                (text[:pos],                          normal_color),
                (text[pos:pos + len(self._search)],   self.MATCH_COLOR),
                (text[pos + len(self._search):],      normal_color),
            ]
            for segment, color in segments:
                if segment:
                    painter.setPen(color)
                    w = fm.horizontalAdvance(segment)
                    painter.drawText(x, text_rect.y(), w, text_rect.height(),
                                     Qt.AlignmentFlag.AlignVCenter, segment)
                    x += w

        painter.restore()


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
        self.btnEbird.clicked.connect(self.openEBirdSingleChecklist)
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
        self.btnEbird.setVisible(False)
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

        windowWidth = self.width()-20
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
                w.setFont(QFont(YBFont, fontSize))
            except:
                pass
          
        # fix the Find text box to a reasonable width; let the Location button size itself
        metrics = self.btnShowLocation.fontMetrics()
        fieldHeight = int(metrics.boundingRect("Ag").height() * 1.4)
        fieldWidth = int(metrics.boundingRect("Sample find text").width())
        self.txtFind.setFixedHeight(fieldHeight)
        self.txtFind.setFixedWidth(fieldWidth)

        # scale the main window table
        header = self.tblList.horizontalHeader()
        metrics = QFontMetrics(QFont(YBFont, fontSize))

        self.tblList.verticalHeader().setDefaultSectionSize(self.mdiParent.rowHeight)

        if self.listType == "Species":
            dateTextWidth = int(metrics.boundingRect("2222-22-22").width())

            #find the width of the widest integer in the Tax column, but use a minimum if needed
            taxTextWidth = int(metrics.boundingRect(str(self.tblList.rowCount())).width())
            if taxTextWidth < int(metrics.boundingRect("Tax").width()) * 1.5:
                taxTextWidth = int(metrics.boundingRect("Tax").width()) * 1.5 
            
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
            # Reserve room for the sort-indicator arrow plus cell padding so the
            # Checklists / % of Checklists titles and arrows never overlap, while
            # keeping the data-based width as a floor.
            arrowAllowance = int(28 * scaleFactor) + int(20 * scaleFactor)
            w0 = floor(2.5 * taxTextWidth)
            w2 = floor(1.75 * firstDateTextWidth)
            w3 = floor(1.75 * lastDateTextWidth)
            w4 = max(floor(1.3 * dateTextWidth), metrics.horizontalAdvance("Checklists") + arrowAllowance)
            w5 = max(floor(1.8 * dateTextWidth), metrics.horizontalAdvance("% of Checklists") + arrowAllowance)

            # give species name column the remaining width
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

            # apply fixed widths to all columns except species name (must come after setSectionResizeMode)
            header.resizeSection(0, w0)
            header.resizeSection(2, w2)
            header.resizeSection(3, w3)
            header.resizeSection(4, w4)
            header.resizeSection(5, w5)

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
            header.resizeSection(1, floor(1.75 * dateTextWidth))
            header.resizeSection(2, floor(1.75 * dateTextWidth))
            # Reserve room for the sort-indicator arrow plus cell padding so the
            # Checklists title and arrow never overlap, while still fitting the data.
            arrowAllowance = int(28 * scaleFactor) + int(20 * scaleFactor)
            checklistsDataWidth = metrics.horizontalAdvance("99999")
            header.resizeSection(3, max(checklistsDataWidth, metrics.horizontalAdvance("Checklists") + arrowAllowance))

        if self.listType == "Checklists":

            thisColumnWidth = int(metrics.boundingRect("Sample Names").width())
            header.resizeSection(0,  floor(1.5 * thisColumnWidth))                
            header.resizeSection(1,  floor(1.75 * thisColumnWidth))                
            header.resizeSection(2,  floor(1.75 * thisColumnWidth))                
            
            # Don't set Location width. It stretches to fill remaining vacant width

            dateTextWidth = int(metrics.boundingRect("2222-22-22").width())
            header.resizeSection(4,  floor(1.75 * dateTextWidth))

            # Reserve room for the sort-indicator arrow plus cell padding so the
            # header title and arrow never overlap, while still fitting the data.
            arrowAllowance = int(28 * scaleFactor) + int(20 * scaleFactor)
            timeDataWidth = metrics.horizontalAdvance("22:22")
            header.resizeSection(5, max(timeDataWidth, metrics.horizontalAdvance("Time") + arrowAllowance))

            speciesDataWidth = metrics.horizontalAdvance("9999")
            header.resizeSection(6, max(speciesDataWidth, metrics.horizontalAdvance("Species") + arrowAllowance))
            header.resizeSection(7, 66)

        if self.listType == "Find Results":

            thisColumnWidth = int(metrics.boundingRect("Checklist Comments").width())
            header.resizeSection(0,  floor(1.5 * thisColumnWidth))                

            thisColumnWidth = int(metrics.boundingRect("Some Location's Long Name").width())
            header.resizeSection(1,  floor(1.75 * thisColumnWidth))               

            dateTextWidth = int(metrics.boundingRect("2222-22-22").width())
            header.resizeSection(2,  floor(1.75 * dateTextWidth))

            # Don't set Comments width. It stretches to fill remaining vacant width

        self.lblLocation.setFont(QFont(YBFont, floor(fontSize * 1.4 )))
        self.lblLocation.setStyleSheet("QLabel { font: bold }");
        self.lblDateRange.setFont(QFont(YBFont, floor(fontSize * 1.2 )))
        self.lblDateRange.setStyleSheet("QLabel { font: bold }");
        self.lblDetails.setFont(QFont(YBFont, floor(fontSize * 1.2 )))
        self.lblDetails.setStyleSheet("QLabel { font: bold }");
        self.lblSpecies.setFont(QFont(YBFont, fontSize))
        self.lblFind.setFont(QFont(YBFont, fontSize))
        self.btnShowLocation.setFont(QFont(YBFont, fontSize))
        self.btnShowLocation.setStyleSheet("QLabel { font: bold }")
        charFmt = QTextCharFormat()
        charFmt.setFontPointSize(float(fontSize * 1.25))
        charFmt.setFontWeight(QFont.Weight.Normal)
        cur = self.txtChecklistComments.textCursor()
        cur.select(QTextCursor.SelectionType.Document)
        cur.mergeCharFormat(charFmt)
        cur.clearSelection()
        self.txtChecklistComments.setTextCursor(cur)
         
        windowWidth = int(1050 * scaleFactor) if self.listType == "Checklists" else int(800 * scaleFactor)
        windowHeight = int(580 * scaleFactor)
        self.resize(windowWidth, windowHeight)


    def afterSort(self, column, order):
        self.tblList.verticalHeader().setDefaultSectionSize(self.mdiParent.rowHeight)


    def showDefaultSortIndicator(self):
        """Point the header's sort arrow at the column the rows already arrive
        sorted by — the leftmost visible one — so the window opens advertising
        that the headers are clickable.

        The arrow is set with the header's signals blocked ON PURPOSE.  The
        table has sorting enabled, so QTableView listens to sortIndicatorChanged
        and would re-sort the rows; every Fill* method inserts its rows in the
        order the database already returned them, and re-sorting on the column's
        DISPLAY text would not always reproduce that (checklists, for instance,
        are ordered by country code, not by the country name shown).  Blocking
        the signal shows the arrow and leaves the rows exactly as built.

        A side benefit: with the indicator already on that column, the user's
        first click on it flips to descending — a visible change — instead of
        re-applying the ascending sort that is already in effect and appearing
        to do nothing."""
        header = self.tblList.horizontalHeader()
        for column in range(self.tblList.columnCount()):
            if not self.tblList.isColumnHidden(column):
                header.blockSignals(True)
                header.setSortIndicator(column, Qt.SortOrder.AscendingOrder)
                header.blockSignals(False)
                header.setSortIndicatorShown(True)
                return
           
        
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
        QApplication.processEvents()
        sub.scaleMe()


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
                "<th>First</th>" +
                "<th>Latest</th>" +
                "<th>Checklists</th>" +
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
        

    @code_MediaRefresh.media_report()
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
                firstItem = code_SeasonalSort.dateItem(species[1])
                lastItem = code_SeasonalSort.dateItem(species[2])
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

            self.btnEbird.setVisible(True)
            self.btnEbird.setStyleSheet(
                "QPushButton { background-color: #2d7a2d; color: white; "
                "border-radius: 3px; padding: 2px 6px; font-size: 11px; }"
            )

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
        icon.addPixmap(QPixmap(":/icon_bird_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        # Only the species list has date columns; the single-checklist variant
        # this method also builds is Tax/Species/Count/Comment.
        if self.listType == "Species":
            code_SeasonalSort.install(self.tblList, (2, 3))   # First, Last
        self.showDefaultSortIndicator()

        # tell MainWindow that we succeeded filling the list
        return(True)


    @code_MediaRefresh.media_report()
    def FillChecklists(self, filter):

        self.filter = filter
        self.listType = "Checklists"
        
        # get species data from db 
        checklists = self.mdiParent.db.GetChecklists(filter)
        
        # abort if no checklists matched filter
        if len(checklists) == 0:
            return(False)
       
       # set up tblList column headers and widths
        self.tblList.setColumnCount(8)
        self.tblList.setRowCount(len(checklists))
        self.tblList.horizontalHeader().setVisible(True)
        self.tblList.setHorizontalHeaderLabels(['Country', 'State', 'County', 'Location', 'Date', 'Time', 'Species', ''])
        header = self.tblList.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        self.tblList.setColumnWidth(7, 66)
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
            
            dateItem = code_SeasonalSort.dateItem(c[4])

            timeItem = QTableWidgetItem()
            timeItem.setText(c[5])
            
            speciesCountItem = QTableWidgetItem()
            speciesCountItem.setData(Qt.DisplayRole, c[6])  
            speciesCountItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)
            
            ebirdBtn = QPushButton("eBird")
            ebirdBtn.setStyleSheet(
                "QPushButton { background-color: #2d7a2d; color: white; border-radius: 3px;"
                "              padding: 2px 6px; font-size: 11px; }"
                "QPushButton:hover { background-color: #3a9e3a; }"
                "QPushButton:pressed { background-color: #1f5c1f; }"
            )
            checklistId = c[0]
            ebirdBtn.clicked.connect(lambda checked=False, cid=checklistId: self.openEBirdChecklist(cid))

            self.tblList.setItem(R, 0, countryItem)
            self.tblList.setItem(R, 1, stateItem)
            self.tblList.setItem(R, 2, countyItem)
            self.tblList.setItem(R, 3, locationItem)
            self.tblList.setItem(R, 4, dateItem)
            self.tblList.setItem(R, 5, timeItem)
            self.tblList.setItem(R, 6, speciesCountItem)
            self.tblList.setCellWidget(R, 7, ebirdBtn)
            R = R + 1
        
        self.lblSpecies.setText("Checklists: " + str(self.tblList.rowCount()))

        self.mdiParent.SetChildDetailsLabels(self, filter)

        self.setWindowTitle(filter.buildWindowTitle("Checklists", self.mdiParent.db, count=self.tblList.rowCount(), countUnit="Checklists"))

        self.txtChecklistComments.setVisible(False)

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_checklists_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)  
        
        self.tblList.addAction(self.actionSetDateFilter)
        self.tblList.addAction(self.actionSetCountryFilter)
        self.tblList.addAction(self.actionSetStateFilter)
        self.tblList.addAction(self.actionSetCountyFilter)
        self.tblList.addAction(self.actionSetLocationFilter)

        self.resize(1050, self.height())

        code_SeasonalSort.install(self.tblList, (4,))     # Date
        self.showDefaultSortIndicator()

        # alert MainWindow that we finished fill data successfully
        return(True)


    def openEBirdChecklist(self, checklistId):
        if not self.mdiParent.db.ebirdApiKey.strip():
            QMessageBox.warning(
                self,
                "eBird API Key Required",
                "No eBird API key is configured.\n\nPlease add your key under Preferences.",
                QMessageBox.StandardButton.Ok,
            )
            return
        QDesktopServices.openUrl(QUrl(f"https://ebird.org/checklist/{checklistId}"))


    def openEBirdSingleChecklist(self):
        if not self.mdiParent.db.ebirdApiKey.strip():
            QMessageBox.warning(
                self,
                "eBird API Key Required",
                "No eBird API key is configured.\n\nPlease add your key under Preferences.",
                QMessageBox.StandardButton.Ok,
            )
            return
        QDesktopServices.openUrl(QUrl(f"https://ebird.org/checklist/{self.filter.getChecklistID()}"))


    def FillFindChecklists(self, foundList, searchString=""):

        # Find has no sighting filter; use an empty one so self.filter is a real
        # Filter object (this was mistakenly assigned the built-in filter()).
        self.filter = code_Filter.Filter()
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

        if searchString:
            self.tblList.setItemDelegateForColumn(3, _FoundHighlightDelegate(searchString, self.tblList))

        # add checklists and found term to table row by row

        R = 0
        for c in foundList:  
            typeItem = QTableWidgetItem()
            typeItem.setData(Qt.UserRole, c[1])  #store checklistID for future retreaval
            typeItem.setData(Qt.UserRole + 1, c[5])  # media fileName (Photo/Recording Notes hits only)
            typeItem.setText(c[0])
            
            locationItem = QTableWidgetItem()
            locationItem.setText(c[2])
            
            dateItem = code_SeasonalSort.dateItem(c[3])

            foundTextItem = QTableWidgetItem()
            foundText = _find_snippet(c[4], searchString) if searchString else c[4]
            foundTextItem.setText(foundText)
            foundTextItem.setToolTip(c[4])

            self.tblList.setItem(R, 0, typeItem)                
            self.tblList.setItem(R, 1, locationItem)
            self.tblList.setItem(R, 2, dateItem)
            self.tblList.setItem(R, 3, foundTextItem)
            R = R + 1
        
        self.setWindowTitle("Find Results")
        self.lblLocation.setVisible(False)
        self.lblDateRange.setVisible(False)

        # Header reflects the search terms (was a vestigial "Details Label"
        # placeholder from Qt Designer, since this label was never set here).
        if searchString:
            self.lblDetails.setText('Find results for "' + searchString + '"')
            self.lblDetails.setVisible(True)
        else:
            self.lblDetails.setText("")
            self.lblDetails.setVisible(False)
            
        self.lblSpecies.setText("Checklists: " + str(self.tblList.rowCount()))
        self.txtChecklistComments.setVisible(False)

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_find_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        code_SeasonalSort.install(self.tblList, (2,))     # Date
        self.showDefaultSortIndicator()


    @code_MediaRefresh.media_report()
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

        # set 4 columns and header titles
        self.tblList.setRowCount(len(thisWindowList))
        self.tblList.setColumnCount(4)
        self.tblList.setHorizontalHeaderLabels(['Location', 'First', 'Last', 'Checklists'])
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        # add locations and dates to table row by row
        R = 0
        for loc in thisWindowList:
            locationItem = QTableWidgetItem()
            locationItem.setText(loc[0])
            firstItem = code_SeasonalSort.dateItem(loc[1])
            lastItem = code_SeasonalSort.dateItem(loc[2])
            checklistCountItem = QTableWidgetItem()
            checklistCountItem.setData(Qt.DisplayRole, loc[3])
            checklistCountItem.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.tblList.setItem(R, 0, locationItem)
            self.tblList.setItem(R, 1, firstItem)
            self.tblList.setItem(R, 2, lastItem)
            self.tblList.setItem(R, 3, checklistCountItem)
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
        icon.addPixmap(QPixmap(":/icon_location_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)  

        self.tblList.addAction(self.actionSetLocationFilter)
        self.tblList.addAction(self.actionSetFirstDateFilter)
        self.tblList.addAction(self.actionSetLastDateFilter)

        code_SeasonalSort.install(self.tblList, (1, 2))   # First, Last
        self.showDefaultSortIndicator()

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

        if self.listType == "Find Results":
            category = self.tblList.item(currentRow, 0).text()
            if category in ("Photo Notes", "Recording Notes"):
                fileName = self.tblList.item(currentRow, 0).data(Qt.UserRole + 1)

                if category == "Photo Notes":
                    photoData, sightingData = self.mdiParent.db.GetPhotoAndSightingByFileName(fileName)
                    if photoData is not None:
                        import code_Photos
                        sub = code_Photos.Photos()
                        sub.mdiParent = self.mdiParent
                        sub.FillSinglePhoto(photoData, sightingData)
                        self.parent().parent().addSubWindow(sub)
                        self.mdiParent.PositionChildWindow(sub, self)
                        sub.show()
                else:
                    audioData, sightingData = self.mdiParent.db.GetAudioAndSightingByFileName(fileName)
                    if audioData is not None:
                        import code_Recordings
                        sub = code_Recordings.Recordings()
                        sub.mdiParent = self.mdiParent
                        sub.FillSingleRecording(audioData, sightingData)
                        self.parent().parent().addSubWindow(sub)
                        self.mdiParent.PositionChildWindow(sub, self)
                        sub.show()

                QApplication.restoreOverrideCursor()
                return

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
        QApplication.processEvents()
        sub.scaleMe()
        sub.resizeMe()
        QApplication.restoreOverrideCursor()
        

