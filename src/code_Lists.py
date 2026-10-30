# import project files
import form_Lists
from code_Stylesheet import YBFont
import code_Filter
import code_SeasonalSort
import code_MediaRefresh
import code_Location
import code_Individual
import code_DataBase
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


class _ConservationPillDelegate(QStyledItemDelegate):
    """Paints the Status column's conservation pill, centered in the cell, at
    the size the Individual window uses."""

    def __init__(self, diameter, parent=None):
        super().__init__(parent)
        self.diameter = diameter

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget else QApplication.style()

        # Draw background (selection, hover, etc.) without any text
        opt.text = ""
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        code = index.data(Qt.ItemDataRole.DisplayRole) or "NA"
        rect = option.rect
        code_Individual.paintConservationPill(
            painter,
            rect.x() + (rect.width() - self.diameter) / 2,
            rect.y() + (rect.height() - self.diameter) / 2,
            self.diameter, code)


class _StatusItem(QTableWidgetItem):
    """Status cell that sorts by severity (Extinct first), then taxonomic
    order, instead of alphabetically by code."""

    def __lt__(self, other):
        return ((self.data(Qt.ItemDataRole.UserRole), self.data(Qt.ItemDataRole.UserRole + 1))
                < (other.data(Qt.ItemDataRole.UserRole), other.data(Qt.ItemDataRole.UserRole + 1)))


class _SortKeyItem(QTableWidgetItem):
    """Cell whose text is for display and whose UserRole value is what it
    sorts by."""

    def __lt__(self, other):
        return self.data(Qt.ItemDataRole.UserRole) < other.data(Qt.ItemDataRole.UserRole)


# Severity rank of each IUCN base category for sorting the Status column.
_STATUS_RANK = {code: rank for rank, code in enumerate(code_DataBase.IUCN_COLORS)}


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

        # A single checklist's Photos and Recordings buttons, under Location;
        # shown only when the checklist has media (see _updateMediaButtons).
        self.btnPhotos = QPushButton("Photos", self.frmButtons)
        self.btnPhotos.clicked.connect(self.CreatePhotos)
        self.verticalLayout_3.addWidget(self.btnPhotos)
        self.btnRecordings = QPushButton("Recordings", self.frmButtons)
        self.btnRecordings.clicked.connect(self.CreateRecordings)
        self.verticalLayout_3.addWidget(self.btnRecordings)

        self.btnShowLocation.setVisible(False)
        self.btnEbird.setVisible(False)
        self.btnPhotos.setVisible(False)
        self.btnRecordings.setVisible(False)
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
        
        if self.listType in ["Checklists", "Locations"]:
            if self.listType == "Checklists":
                countyName= self.tblList.item(self.tblList.currentRow(), 2).text()
            if self.listType == "Locations":
                countyName= self.tblList.item(self.tblList.currentRow(), 6).text()
            # nor a county, nor does a location eBird files under no county
            if countyName:
                self.mdiParent.setCountyFilter(countyName)
   
   
    def setCountryFilter(self):
        
        if self.listType in ["Checklists", "Locations"]:
            if self.listType == "Checklists":
                countryName= self.tblList.item(self.tblList.currentRow(), 0).text()
            if self.listType == "Locations":
                countryName= self.tblList.item(self.tblList.currentRow(), 4).text()
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
        
        if self.listType in ["Checklists", "Locations"]:
            if self.listType == "Checklists":
                stateName= self.tblList.item(self.tblList.currentRow(), 1).text()
            if self.listType == "Locations":
                stateName= self.tblList.item(self.tblList.currentRow(), 5).text()
            # a location that is a whole country has no state to filter on
            if stateName:
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
          
        # fix the Find text box to a reasonable width; its height comes from the
        # stylesheet's padding, so descenders are not clipped.  Let the Location
        # button size itself.
        metrics = self.btnShowLocation.fontMetrics()
        fieldWidth = int(metrics.boundingRect("Sample find text").width())
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
            # First, Last, Photos and Recordings: the wider of their data plus
            # a little cell padding and the header's own size hint, which
            # covers the bold title, the stylesheet padding and the sort arrow.
            cellPadding = int(16 * scaleFactor)
            w2 = max(firstDateTextWidth + cellPadding, header.sectionSizeHint(2))
            w3 = max(lastDateTextWidth + cellPadding, header.sectionSizeHint(3))
            w4 = max(floor(1.3 * dateTextWidth), metrics.horizontalAdvance("Checklists") + arrowAllowance)
            w5 = max(floor(1.8 * dateTextWidth), metrics.horizontalAdvance("% of Checklists") + arrowAllowance)

            w6 = max(code_Individual.conservationPillDiameter(QFont(YBFont, fontSize + 1)) * 2,
                     metrics.horizontalAdvance("Status") + arrowAllowance)

            # give species name column the remaining width
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

            # apply fixed widths to all columns except species name (must come after setSectionResizeMode)
            header.resizeSection(0, w0)
            header.resizeSection(2, w2)
            header.resizeSection(3, w3)
            header.resizeSection(4, w4)
            header.resizeSection(5, w5)
            header.resizeSection(6, w6)
            mediaDataWidth = metrics.horizontalAdvance("9999") + cellPadding
            header.resizeSection(7, max(mediaDataWidth, header.sectionSizeHint(7)))
            header.resizeSection(8, max(mediaDataWidth, header.sectionSizeHint(8)))

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
            # First and Last fit the widest possible timestamp — written with
            # the font's widest digit, as digit widths can differ — plus a
            # little cell padding, or the header with its sort arrow if wider.
            widestDigit = max("0123456789", key=metrics.horizontalAdvance)
            timestamp = "{0}{0}{0}{0}-{0}{0}-{0}{0} {0}{0}:{0}{0}".format(widestDigit)
            dateTextWidth = metrics.horizontalAdvance(timestamp) + int(16 * scaleFactor)
            header.resizeSection(1, max(dateTextWidth, header.sectionSizeHint(1)))
            header.resizeSection(2, max(dateTextWidth, header.sectionSizeHint(2)))
            # Country, State and County at the Checklists list's width; Photos
            # and Recordings as in the Species list.
            placeWidth = floor(1.5 * int(metrics.boundingRect("Sample Names").width()))
            for column in (4, 5, 6):
                header.resizeSection(column, placeWidth)
            mediaDataWidth = metrics.horizontalAdvance("9999") + int(16 * scaleFactor)
            header.resizeSection(7, max(mediaDataWidth, header.sectionSizeHint(7)))
            header.resizeSection(8, max(mediaDataWidth, header.sectionSizeHint(8)))
            # Reserve room for the sort-indicator arrow plus cell padding so the
            # Checklists title and arrow never overlap, while still fitting the data.
            arrowAllowance = int(28 * scaleFactor) + int(20 * scaleFactor)
            checklistsDataWidth = metrics.horizontalAdvance("99999")
            header.resizeSection(3, max(checklistsDataWidth, metrics.horizontalAdvance("Checklists") + arrowAllowance))

        if self.listType == "Checklists":

            # Country, State and County share one width.
            thisColumnWidth = int(metrics.boundingRect("Sample Names").width())
            header.resizeSection(0,  floor(1.5 * thisColumnWidth))                
            header.resizeSection(1,  floor(1.5 * thisColumnWidth))                
            header.resizeSection(2,  floor(1.5 * thisColumnWidth))                
            
            # Don't set Location width. It stretches to fill remaining vacant width

            # Date, Time, Species and Tallies share one width: Tallies' title
            # with room for the sort-indicator arrow and cell padding ("Tallies"
            # is wider than its alternative, "Media"), widened only if a date
            # would not fit.
            arrowAllowance = int(28 * scaleFactor) + int(20 * scaleFactor)
            dateTextWidth = int(metrics.boundingRect("2222-22-22").width())
            tallyDataWidth = metrics.horizontalAdvance("99999+")
            sharedWidth = max(tallyDataWidth,
                              metrics.horizontalAdvance("Tallies") + arrowAllowance,
                              dateTextWidth + int(16 * scaleFactor))
            for column in (4, 5, 6, 7):
                header.resizeSection(column, sharedWidth)
            header.resizeSection(8, 66)

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
        self.btnPhotos.setFont(QFont(YBFont, fontSize))
        self.btnRecordings.setFont(QFont(YBFont, fontSize))
        charFmt = QTextCharFormat()
        charFmt.setFontPointSize(float(fontSize * 1.25))
        charFmt.setFontWeight(QFont.Weight.Normal)
        cur = self.txtChecklistComments.textCursor()
        cur.select(QTextCursor.SelectionType.Document)
        cur.mergeCharFormat(charFmt)
        cur.clearSelection()
        self.txtChecklistComments.setTextCursor(cur)
         
        windowWidth = int(1050 * scaleFactor) if self.listType == "Checklists" else int(800 * scaleFactor)
        # The Species list is wider by its Status column and any media
        # columns, and the Checklists list by its Tallies column, so the other
        # columns keep their widths.
        if self.listType == "Species":
            windowWidth += header.sectionSize(6)
            for column in (7, 8):
                if not self.tblList.isColumnHidden(column):
                    windowWidth += header.sectionSize(column)
        if self.listType == "Checklists":
            windowWidth += header.sectionSize(7)
        # The Locations list is wider by its place and any media columns, then
        # 15% narrower overall; the stretching Location column gives it up.
        if self.listType == "Locations":
            for column in (4, 5, 6, 7, 8):
                if not self.tblList.isColumnHidden(column):
                    windowWidth += header.sectionSize(column)
            windowWidth = int(windowWidth * 0.85)
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


    def _checklistMediaFilter(self):
        """The single checklist's filter without its Media Filter settings, so
        the Photos and Recordings buttons cover all of its listed species'
        media."""
        f = deepcopy(self.filter)
        f.clearPhotoFilter()
        f.clearRecordingFilter()
        return f


    def _updateMediaButtons(self):
        if self.listType != "Single Checklist":
            return
        f = self._checklistMediaFilter()
        db = self.mdiParent.db
        self.btnPhotos.setVisible(len(db.GetSightingsWithPhotos(f)) > 0)
        self.btnRecordings.setVisible(len(db.GetSightingsWithRecordings(f)) > 0)


    def refreshMedia(self):
        """Show or hide the Photos and Recordings buttons after a catalog
        change — called by MainWindow.notifyMediaChanged."""
        self._updateMediaButtons()


    def CreatePhotos(self):
        import code_Photos
        sub = code_Photos.Photos()
        sub.mdiParent = self.mdiParent
        sub.FillPhotos(self._checklistMediaFilter())
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)
        sub.show()


    def CreateRecordings(self):
        import code_Recordings
        sub = code_Recordings.Recordings()
        sub.mdiParent = self.mdiParent
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)
        sub.FillRecordings(self._checklistMediaFilter())   # fill hidden, then show: see MainWindow._createRecordingsWindow
        sub.show()


    def CreateSpeciesMedia(self, speciesName, kind):
        """Browse Grid of one species' photos or recordings under the list's
        filter."""
        filter = deepcopy(self.filter)
        filter.setSpeciesName(speciesName)
        self._openMediaGrid(filter, kind)


    def _openMediaGrid(self, filter, kind):
        """Browse Grid of the photos ("photos") or recordings ("audio") that
        match filter."""
        if kind == "photos":
            self.mdiParent.createPhotosGridForFilter(filter)
        else:
            self.mdiParent.createRecordingsGridForFilter(filter)


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
                "<th>Country</th>" +
                "<th>State</th>" +
                "<th>County</th>" +
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
                "".join("<td>" + self.tblList.item(r, c).text() + "</td>" for c in (4, 5, 6)) +
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
                "<th>Location</th>" +
                "<th>Country</th>" +
                "<th>State</th> " +
                "<th>County</th>" +
                "<th>Date</th>" +
                "<th>Time</th>" +
                "<th>Species</th>" +
                "<th>" + self.tblList.horizontalHeaderItem(7).text() + "</th>" +
                "</tr>"
                )
                
            for r in range(self.tblList.rowCount()):
                html = html + (
                "<tr>" +
                "<td>" +
                self.tblList.item(r, 3).text() +
                "</td>" +
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
                self.tblList.item(r, 4).text() +
                "</td>" +
                "<td>" +
                self.tblList.item(r, 5).text() +
                "</td>" +
                "<td>" +
                self.tblList.item(r, 6).text() +
                "</td>" +
                "<td>" +
                self.tblList.item(r, 7).text() +
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
        

    # A Species list's Photos and Recordings columns are about media, so it
    # rebuilds when the catalog changes — even with the columns hidden, so
    # they come back when a catalog is opened.
    @code_MediaRefresh.media_report(is_content=lambda w: w.listType == "Species")
    def FillSpecies(self, filter):
        
        self.filter = filter
        self.listType = "Species"
        checklistDetails = ""

        # No sorting while rows are filled: a media-change rebuild refills a
        # table that may already be sorted, and each setItem would re-sort it
        # mid-fill.  Re-enabled at the end, which sorts by the indicator.
        self.tblList.setSortingEnabled(False)

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
                        
            thisWindowList = self.mdiParent.db.GetSpeciesWithData(filter,  [], "Subspecies", mediaCounts=True)

            if len(thisWindowList) == 0:
                return(False)

            self.tblList.setRowCount(len(thisWindowList))
            self.tblList.setColumnCount(9)
            self.tblList.setHorizontalHeaderLabels(['Tax', 'Species', 'First',  'Last', 'Checklists', '% of Checklists', 'Status',
                                                    'Photos', 'Recordings'])
            # Status, Photos and Recordings are the last logical columns, so
            # the other columns keep the indexes the click handlers and filters
            # use; they are only SHOWN elsewhere: Status right after Species,
            # Photos and Recordings just before Checklists.  The pill matches
            # the Individual window's, whose status label uses the font one
            # point larger.
            # A media-change rebuild replays this fill, so move only columns
            # not already in place.
            header.moveSection(header.visualIndex(6), 2)
            for column in (7, 8):
                if header.visualIndex(column) > header.visualIndex(4):
                    header.moveSection(header.visualIndex(column), header.visualIndex(4))
            # Each media column appears only if the catalog has that kind of media.
            self.tblList.setColumnHidden(7, not self.mdiParent.db.hasPhotos())
            self.tblList.setColumnHidden(8, not self.mdiParent.db.hasRecordings())
            self.tblList.setItemDelegateForColumn(6, _ConservationPillDelegate(
                code_Individual.conservationPillDiameter(QFont(YBFont, self.mdiParent.fontSize + 1)),
                self.tblList))
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

                # The code is the cell's text, so the Find box matches it.
                statusCode, statusName = self.mdiParent.db.GetConservationStatus(species[0])
                statusCode = statusCode.split()[0]
                statusItem = _StatusItem()
                statusItem.setText(statusCode)
                statusItem.setToolTip(statusName)
                statusItem.setData(Qt.ItemDataRole.UserRole, _STATUS_RANK[statusCode])
                statusItem.setData(Qt.ItemDataRole.UserRole + 1, R)
                self.tblList.setItem(R, 6, statusItem)

                # Media counts; a species with none shows a blank cell.
                for column, mediaCount in ((7, species[8]), (8, species[9])):
                    mediaItem = _SortKeyItem()
                    mediaItem.setText(str(mediaCount) if mediaCount else "")
                    mediaItem.setData(Qt.UserRole, mediaCount)
                    mediaItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)
                    self.tblList.setItem(R, column, mediaItem)
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

            self._updateMediaButtons()
                            
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
        self.tblList.setSortingEnabled(True)

        # tell MainWindow that we succeeded filling the list
        return(True)


    @code_MediaRefresh.media_report()
    def FillChecklists(self, filter):

        self.filter = filter
        self.listType = "Checklists"

        # A media-change rebuild (see code_MediaRefresh) replays this fill on
        # a window already on screen: keep the user's width, and fill with
        # sorting off so each setItem does not re-sort a sorted table.
        isRebuild = hasattr(self, "_mediaRebuildName")
        self.tblList.setSortingEnabled(False)
        
        # get species data from db 
        # Species and Tallies count only the sightings that match the filter.
        # A Media Filter matches photo and recording files, which do not
        # correspond one to one with tallies, so the column then counts the
        # matching media files instead.
        checklists = self.mdiParent.db.GetChecklists(filter, filteredCounts=True)
        showMedia = filter.hasPositiveMediaFilter()
        
        # abort if no checklists matched filter
        if len(checklists) == 0:
            return(False)
       
       # set up tblList column headers and widths
        self.tblList.setColumnCount(9)
        self.tblList.setRowCount(len(checklists))
        self.tblList.horizontalHeader().setVisible(True)
        self.tblList.setHorizontalHeaderLabels(['Country', 'State', 'County', 'Location', 'Date', 'Time', 'Species',
                                                'Media' if showMedia else 'Tallies', ''])
        header = self.tblList.horizontalHeader()
        # Shown Location, Country, State, County.  Only the display order
        # changes: the logical indexes, which the click handlers, filter
        # actions and widths use, stay Country 0 to Location 3.  Moving by
        # target position makes this safe to replay on a rebuild.
        for visual, logical in enumerate((3, 0, 1, 2)):
            header.moveSection(header.visualIndex(logical), visual)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        self.tblList.setColumnWidth(8, 66)
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
            speciesCountItem.setData(Qt.DisplayRole, c[8])  
            speciesCountItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)

            # Individuals counted on the matching sightings.  A species
            # counted as X adds an unknown number, so the tally reads "12+",
            # or just "X" when nothing was counted.
            tally, hasX = c[9], c[10]
            tallyItem = _SortKeyItem()
            if showMedia:
                tallyItem.setText(str(c[11]))
                tallyItem.setData(Qt.UserRole, c[11])
            else:
                tallyItem.setText(("X" if tally == 0 else str(tally) + "+") if hasX else str(tally))
                tallyItem.setData(Qt.UserRole, tally)
                if hasX:
                    tallyItem.setToolTip("Includes species counted as X (present, not counted)")
            tallyItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)
            
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
            self.tblList.setItem(R, 7, tallyItem)
            self.tblList.setCellWidget(R, 8, ebirdBtn)
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

        if not isRebuild:
            self.resize(1050 + self.tblList.horizontalHeader().sectionSize(7), self.height())

        code_SeasonalSort.install(self.tblList, (4,))     # Date
        self.showDefaultSortIndicator()
        self.tblList.setSortingEnabled(True)

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


    # The Photos and Recordings columns are about media, so the list rebuilds
    # when the catalog changes, as the Species list does.
    @code_MediaRefresh.media_report(is_content=lambda w: w.listType == "Locations")
    def FillLocations(self, filter):
        
        self.filter = filter
        self.listType = "Locations"

        # No sorting while rows are filled: a media-change rebuild refills a
        # table that may already be sorted.  Re-enabled at the end.
        self.tblList.setSortingEnabled(False)
       
        self.btnShowLocation.setVisible(False)
        self.lblDetails.setVisible(False)
                  
       # set up tblList column headers and widths
        self.tblList.setShowGrid(False)        
        header = self.tblList.horizontalHeader()
        header.setVisible(True)   
        
        thisWindowList = self.mdiParent.db.GetLocations(filter,  "Dates")
        
        if len(thisWindowList) == 0:
            return(False)

        # set columns and header titles.  Country, State, County, Photos and
        # Recordings are the last logical columns, so First, Last and
        # Checklists keep the indexes the click handlers and filter actions
        # use; they are only SHOWN in the order Location, Country, State,
        # County, First, Last, Photos, Recordings, Checklists.  Moving by
        # target position makes this safe to replay on a rebuild.
        self.tblList.setRowCount(len(thisWindowList))
        self.tblList.setColumnCount(9)
        self.tblList.setHorizontalHeaderLabels(['Location', 'First', 'Last', 'Checklists',
                                                'Country', 'State', 'County', 'Photos', 'Recordings'])
        for visual, logical in enumerate((0, 4, 5, 6, 1, 2, 7, 8, 3)):
            header.moveSection(header.visualIndex(logical), visual)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        # Each media column appears only if the catalog has that kind of media.
        self.tblList.setColumnHidden(7, not self.mdiParent.db.hasPhotos())
        self.tblList.setColumnHidden(8, not self.mdiParent.db.hasRecordings())

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

            countryItem = QTableWidgetItem(self.mdiParent.db.GetCountryName(loc[4][0:2]))
            stateItem = QTableWidgetItem(self.mdiParent.db.GetStateName(loc[4]))
            countyItem = QTableWidgetItem(loc[5])
            self.tblList.setItem(R, 4, countryItem)
            self.tblList.setItem(R, 5, stateItem)
            self.tblList.setItem(R, 6, countyItem)

            # Media counts; a location with none shows a blank cell.
            for column, mediaCount in ((7, loc[6]), (8, loc[7])):
                mediaItem = _SortKeyItem()
                mediaItem.setText(str(mediaCount) if mediaCount else "")
                mediaItem.setData(Qt.UserRole, mediaCount)
                mediaItem.setTextAlignment(Qt.AlignCenter|Qt.AlignVCenter)
                self.tblList.setItem(R, column, mediaItem)
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
        self.tblList.addAction(self.actionSetCountryFilter)
        self.tblList.addAction(self.actionSetStateFilter)
        self.tblList.addAction(self.actionSetCountyFilter)
        self.tblList.addAction(self.actionSetFirstDateFilter)
        self.tblList.addAction(self.actionSetLastDateFilter)

        code_SeasonalSort.install(self.tblList, (1, 2))   # First, Last
        self.showDefaultSortIndicator()
        self.tblList.setSortingEnabled(True)

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
                
            if self.listType == "Species" and currentColumn in [7, 8]:
                # a media count was clicked, so open that species' photos or
                # recordings under the list's filter, if it has any
                QApplication.restoreOverrideCursor()
                if self.tblList.item(currentRow, currentColumn).data(Qt.UserRole):
                    self.CreateSpeciesMedia(self.tblList.item(currentRow, 1).text(),
                                            "photos" if currentColumn == 7 else "audio")
                return

            if currentColumn in [1, 6]:
                # species or status column has been clicked so create individual window for that species
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

            if currentColumn in [7, 8]:
                # a media count was clicked, so open that location's photos or
                # recordings under the list's filter, if it has any
                QApplication.restoreOverrideCursor()
                if self.tblList.item(currentRow, currentColumn).data(Qt.UserRole):
                    filter = deepcopy(self.filter)
                    filter.setLocationName(self.tblList.item(currentRow, 0).text())
                    filter.setLocationType("Location")
                    self._openMediaGrid(filter, "photos" if currentColumn == 7 else "audio")
                return

            if currentColumn not in [0, 1, 2]:
                # Checklists and the place columns open nothing
                QApplication.restoreOverrideCursor()
                return
                
            if currentColumn == 0:
                # species column has been clicked so create individual window for that species
                locationName = self.tblList.item(currentRow,  0).text()
                
                sub = code_Location.Location()
                sub.mdiParent = self.mdiParent
                sub.FillLocation(locationName)
                
            if currentColumn in [1, 2]:

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
        

