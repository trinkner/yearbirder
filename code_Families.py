# import the GUI forms that we create with Qt Creator
import form_Families

import code_Filter
import code_Lists
import code_Individual

# import basic Python libraries
import random

from copy import deepcopy

from math import floor

# import the Qt components we'll use
# do this so later we won't have to clutter our code with references to parent Qt classes 

from PyQt5.QtGui import (
    QCursor,
    QColor,
    QFont,
    QPen
    )
    
from PyQt5.QtCore import (
    Qt,
    pyqtSignal,
    QTimer
    )
    
from PyQt5.QtWidgets import (
    QApplication,  
    QTableWidgetItem, 
    QHeaderView,
    QMdiSubWindow,
    QGraphicsScene,
    QGraphicsEllipseItem, 
    QMenu
    )


class Families(QMdiSubWindow, form_Families.Ui_frmFamilies):

    # create "resized" as a signal that the window can emit
    # we respond to this signal with the form's resizeMe method below
    resized = pyqtSignal()   
    
    class MyEllipse(QGraphicsEllipseItem):
        
        family = ""
        parent= ""
    
        def mouseDoubleClickEvent(self, event):
            # Do your stuff here.
            self.parent.CreateFamilyList(self.family)
            
        def contextMenuEvent(self, event):
    
            menu = QMenu()
            menu.setStyleSheet("color:black; background-color: white;")
            
            actionSetFilterToFamily = menu.addAction("Set filter to " + self.family)
            
            action = menu.exec(event.screenPos())
            
            if action == actionSetFilterToFamily:
                self.parent.setFamilyFilter(self.family)
    
            
    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose,True)
        self.mdiParent = ""        

        self.resized.connect(self.resizeMe)  

        self.lstFamilies.currentRowChanged.connect(self.FillSpecies)
        self.lstFamilies.itemDoubleClicked.connect(self.ClickedLstFamilies)  
        self.lstSpecies.itemDoubleClicked.connect(self.ClickedLstSpecies)
        self.tblPieChartLegend.doubleClicked.connect(self.clickedPieChartLegend) 
        
        self.lstFamilies.addAction(self.actionSetFilterToFamily)
        self.actionSetFilterToFamily.triggered.connect(self.lstFamiliesSetFilterToFamily)  

        self.lstSpecies.addAction(self.actionSetFilterToSpecies)
        self.actionSetFilterToSpecies.triggered.connect(self.lstSpeciesSetFilterToSpecies)  

        self.tblPieChartLegend.addAction(self.actionSetFamilyFilterToPieChartLegendFamily)
        self.actionSetFamilyFilterToPieChartLegendFamily.triggered.connect(self.tblPieChartLegendSetFilterToFamily)  
                     
        self.lstFamilies.setSpacing(2)
        self.lstSpecies.setSpacing(2)
                
        self.tabFamilies.setCurrentIndex(1)
                
        self.filter = code_Filter.Filter()
        self.filteredSpeciesList = []
        self.filteredSpeciesListWithFamilies = []
        self.familiesList = []


    def lstFamiliesSetFilterToFamily(self):
        
        family = self.lstFamilies.currentItem().text()
        self.setFamilyFilter(family)        
        

    def tblPieChartLegendSetFilterToFamily(self):        
        
        currentRow = self.tblPieChartLegend.currentRow()
        family = self.tblPieChartLegend.item(currentRow, 1).text()
        self.setFamilyFilter(family)


    def lstSpeciesSetFilterToSpecies(self):
        
        commonName = self.lstSpecies.currentItem().text()
        self.mdiParent.setSpeciesFilter(commonName)
                

    def setFamilyFilter(self, family):
                        
        self.mdiParent.setFamilyFilter(family)
            
            
    def clickedPieChartLegend(self):
        
        currentRow = self.tblPieChartLegend.currentRow()
        
        family = self.tblPieChartLegend.item(currentRow, 1).text()
        self.CreateFamilyList(family)   
        
    
    def ClickedLstSpecies(self):
        species = self.lstSpecies.currentItem().text()
        self.CreateIndividual(species)    


    def ClickedLstFamilies(self):
        family = self.lstFamilies.currentItem().text()
        self.CreateFamilyList(family)
        

    def CreateFamilyList(self,  family):
        
        tempFilter = deepcopy(self.filter)
        tempFilter.setFamily(family)
        
        sub = code_Lists.Lists()
        sub.mdiParent = self.mdiParent        
        
        sub.FillSpecies(tempFilter)        
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)        
        sub.show()

    
    def CreateIndividual(self,  species):
        sub = code_Individual.Individual()
        sub.mdiParent = self.mdiParent
        sub.FillIndividual(species)
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)        
        sub.show()
        sub.resizeMe()


    def FillSpecies(self):
        self.lstSpecies.clear()
        if self.lstFamilies.currentIndex() is not None:
            selectedFamily = self.lstFamilies.currentItem().text()
            familySpecies = []
            # check if we've already added each species' family to list
            if len(self.filteredSpeciesListWithFamilies) == 0:
                # need to add species' families to list               
                for s in self.filteredSpeciesList:
                    thisFamily = self.mdiParent.db.GetFamilyName(s)
                    self.filteredSpeciesListWithFamilies.append([s,  thisFamily])
            for sf in self.filteredSpeciesListWithFamilies:               
                if sf[1]== selectedFamily:
                    familySpecies.append(sf[0])
            self.lstSpecies.addItems(familySpecies)
            self.lstSpecies.setSpacing(2)
            
            count = self.mdiParent.db.CountSpecies(familySpecies)
            self.lblSpecies.setText("Species for selected family: " + str(count))
            
        
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
        
        html=html + (
            "<font size='2'>"
            )
            
        # add family names and the species under them
        
        for r in range(self.lstFamilies.count()):
            html = html + (
                "<h3>" +
                self.lstFamilies.item(r).text() +
                "</h3>"
                )
            self.filter.setFamily(self.lstFamilies.item(r).text())
            for s in self.mdiParent.db.GetSpecies(self.filter):
                html = html + (
                    s +
                    "<br>"
                    )                

        html = html + (
            "<font size>" +            
            "</body>" +
            "</html>"
            )
            
        QApplication.restoreOverrideCursor()   
        
        return(html)
        
    
    def FillFamilies(self, filter):
        
        self.filter = deepcopy(filter)
        
        self.familiesList = self.mdiParent.db.GetFamilies(self.filter)
        self.filteredSpeciesList = self.mdiParent.db.GetSpecies(self.filter)
        cleanedFilteredSpeciesList = []
        for s in self.filteredSpeciesList:
            if "sp." not in s and "/" not in s and " x " not in s:
                cleanedFilteredSpeciesList.append(s)
        self.filteredSpeciesList = cleanedFilteredSpeciesList
        
        self.lblFamilies.setText("Families: " + str(len(self.familiesList )))
        self.lstFamilies.addItems(self.familiesList )
        if len(self.familiesList ) > 0:
            self.lstFamilies.setCurrentRow(0)
            self.FillSpecies()
            self.lstFamilies.setSpacing(2)
        
        else:
            # no families were found matching filter, so report failure back to MainWindow
            return(False)
            
        self.mdiParent.SetChildDetailsLabels(self, self.filter)

        self.setWindowTitle(self.filter.buildWindowTitle("Families", self.mdiParent.db, count=len(self.familiesList), countUnit="Families"))
        
        QApplication.processEvents()
        
        # report success back to MainWindow
        return(True)
        

    def FillPieChart(self):
        
        self.tblPieChartLegend.clear()
        
        QApplication.processEvents()
        
        self.tblPieChartLegend.setColumnCount(3)       
        self.tblPieChartLegend.setRowCount(len(self.familiesList))        
        
        self.tblPieChartLegend.horizontalHeader().setVisible(False)
        header = self.tblPieChartLegend.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)     
        self.tblPieChartLegend.setShowGrid(False)
        
        colors = []
        familiesCount = []
        set_angle = 0
        R = 0
        
        for f in self.familiesList:
            familiesCount.append(sum(x.count(str(f)) for x in self.filteredSpeciesListWithFamilies))
        total = sum(familiesCount)
        
        for fl in range(len(self.familiesList)):
            number = []
            # randomly create three color values (rgb)
            for rgb in range(3):
                number.append(random.randrange(0, 255))
            colors.append(QColor(number[0],number[1],number[2]))

        scene = QGraphicsScene()
                
        for family in familiesCount:  
            # create the angle of each wedge according to its perecent of 360
            angle = round(family/total*16*360)
            # set size of circle and create wedge
            ellipse = self.MyEllipse(0, 0, 100, 100)
            # set the tooltip for the ellipse wedge
            ellipse.setToolTip(self.familiesList[R] + ": " + str(family))                        
            # set center of circle, like an axle
            ellipse.setPos(0,0)
            # rotate through the wedge
            ellipse.setStartAngle(set_angle)
            ellipse.setSpanAngle(angle)
            # assign color
            ellipse.setBrush(colors[R])
            # turn off pen so we won't have ellipse borders
            
            pen = QPen()
            pen.setWidthF(.1)
            ellipse.setPen(pen)
            
            # create set_angle for next time around
            set_angle = angle + set_angle
            # add the actual wedge to the scene object
            scene.addItem(ellipse) 
            
            # save meta data to ellipse for future use (e.g., clicks)
            ellipse.family = self.familiesList[R]
            ellipse.parent = self
            
            # add entry to legend table and set proper color
            colorItem = QTableWidgetItem()
            colorItem.setBackground(QColor(colors[R]))
            
            familyNameItem = QTableWidgetItem()
            familyNameItem.setData(Qt.DisplayRole, self.familiesList[R])
            
            familyCountItem = QTableWidgetItem()
            familyCountItem.setData(Qt.DisplayRole, family)            
            
            self.tblPieChartLegend.setItem(R, 0, colorItem) 
            self.tblPieChartLegend.setItem(R, 1, familyNameItem)
            self.tblPieChartLegend.setItem(R, 2, familyCountItem)
            
            R = R + 1 
        
        self.gvPieChart.setScene(scene)

        self.fitPieChart()
                       
        return(True)


    def fitPieChart(self):
        
        self.gvPieChart.setSceneRect(0, 0, 100, 100)
        self.gvPieChart.fitInView(self.gvPieChart.sceneRect(), Qt.KeepAspectRatio)
                

    def resizeEvent(self, event):
        #routine to handle events on objects, like clicks, lost focus, gained focus, etc.        
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)
        
        
    def resizeMe(self):

        windowWidth =  self.frameGeometry().width()
        windowHeight = self.frameGeometry().height()
        self.scrollArea.setGeometry(5, 27, windowWidth -10 , windowHeight-35)
        self.fitPieChart()
   
   
    def scaleMe(self):
               
        scaleFactor = self.mdiParent.scaleFactor
        windowWidth =  int(780  * scaleFactor)
        windowHeight = int(500 * scaleFactor)            
        self.resize(windowWidth, windowHeight)
        
        fontSize = self.mdiParent.fontSize
        scaleFactor = self.mdiParent.scaleFactor     
        #scale the font for all widgets in window
        for w in self.children():
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

        metrics = self.tblPieChartLegend.fontMetrics()
        textHeight = int(metrics.boundingRect("A").height())
        textWidth = int(metrics.boundingRect("Rank").width())
        
        for t in [self.tblPieChartLegend]:
            header = t.horizontalHeader()
            header.resizeSection(0,  floor(.75 * textWidth))
            header.resizeSection(2,  floor(.75 * textWidth))
            for r in range(t.rowCount()):
                t.setRowHeight(r, int(textHeight * 1.1)) 
    
