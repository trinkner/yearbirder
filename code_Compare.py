# import the GUI forms that we create with Qt Creator
import code_Individual
import form_Compare
import code_Stylesheet

# import the Qt components we'll use
# do this so later we won't have to clutter our code with references to parent Qt classes 

from PyQt5.QtGui import (
    QFont
    )
    
from PyQt5.QtCore import (
    pyqtSignal,
    Qt
)
    
from PyQt5.QtWidgets import (
    QMdiSubWindow
    )
    
from PyQt5.QtWebEngineWidgets import (
    QWebEngineView,
)

from PyQt5.QtPrintSupport import (
    QPrinter
    )

class Compare(QMdiSubWindow, form_Compare.Ui_frmCompare):

    # create "resized" as a signal that the window can emit
    # we respond to this signal with the form's resizeMe method below
    resized = pyqtSignal()

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose,True)
        self.mdiParent = ""
        self.resized.connect(self.resizeMe)                      
        self.btnCompare.clicked.connect(self.CompareLists)
        self.lstLeftOnly.itemDoubleClicked.connect(self.ListLeftClicked)
        self.lstRightOnly.itemDoubleClicked.connect(self.ListRightClicked)
        self.lstBoth.itemDoubleClicked.connect(self.ListBothClicked)
        self.webView = QWebEngineView()
        self.myPrinter = QPrinter(QPrinter.HighResolution)
        
        red = str(code_Stylesheet.speciesColor.red())
        green = str(code_Stylesheet.speciesColor.green())
        blue = str(code_Stylesheet.speciesColor.blue())
        
        self.lstLeftOnly.setStyleSheet("QListWidget {color: rgb(" + red + "," + green + "," + blue + "); font-weight: bold}")
        self.lstRightOnly.setStyleSheet("QListWidget {color: rgb(" + red + "," + green + "," + blue + "); font-weight: bold}")
        self.lstBoth.setStyleSheet("QListWidget {color: rgb(" + red + "," + green + "," + blue + "); font-weight: bold}")

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
                padding: 5px;
            }
            th {
                text-align: left;
            }
            </style>
            <body>
            """
            
        html = html + """
            <H1>  
            List Comparison  
            </H1>
            """
        
        html = html + (
            "<H2>" + 
            "Species only on " + self.cboListsLeft.currentText() + 
            "</H2>"
            )        

        html=html + (
            "<font size='2'>"
            )
        
        for r in range(self.lstLeftOnly.count()):
            html = html + (
                "<br>" +
                self.lstLeftOnly.item(r).text() +
                "</br>"
                )
        
        html=html + (
            "</font size='2'>"
            )
        
        html = html + (
            "<H2>" + 
            "Species only on " + self.cboListsRight.currentText() + 
            "</H2>"
            )        

        html=html + (
            "<font size='2'>"
            )
            
        # add family names and the species under them
        
        for r in range(self.lstRightOnly.count()):
            html = html + (
                "<br>" +
                self.lstRightOnly.item(r).text() +
                "</br>"
                )
        
        html=html + (
            "</font size='2'>"
            )        
        
        html = html + """
            <H2>  
            Species on Both Lists  
            </H2>
            """    

        html=html + (
            "<font size='2'>"
            )
                    
        for r in range(self.lstBoth.count()):
            html = html + (
                "<br>" +                
                self.lstBoth.item(r).text() +
                "</br>"
                )
        
        html=html + (
            "</font size='2'>"
            )        
             
        html = html + """
            <font size>           
            </body>
            </html>
            """
        return(html)


    def ListLeftClicked(self):
        self.CreateNewIndividual(self.lstLeftOnly.currentItem().text())


    def ListRightClicked(self):
        self.CreateNewIndividual(self.lstRightOnly.currentItem().text())


    def ListBothClicked(self):
        self.CreateNewIndividual(self.lstBoth.currentItem().text())        


    def FillListChoices(self): 
        self.lstLeftOnly.clear()
        self.lstRightOnly.clear()
        self.lstBoth.clear()
        self.cboListsLeft.clear()
        self.cboListsRight.clear()
        thisWindowList = []
        for window in self.mdiParent.mdiArea.subWindowList():        
            if window.objectName() == "frmSpeciesList":
                if window.isVisible() == True:
                    thisWindowList.append(window.windowTitle())
        thisWindowList.sort()
        self.cboListsLeft.addItems(thisWindowList)
        self.cboListsRight.addItems(thisWindowList)
        
        if len(thisWindowList) < 2:
            return(False)
        else:
            return(True)
              
        self.scaleMe()
        self.resizeMe()
        
              
    def CompareLists(self):
        self.lstLeftOnly.clear()
        self.lstBoth.clear()
        self.lstRightOnly.clear()
        
        # get left list species
        leftListSpecies = []
        leftTitle = self.cboListsLeft.currentText()
        for window in self.mdiParent.mdiArea.subWindowList():        
            if window.objectName() == "frmSpeciesList":
                if window.windowTitle() == leftTitle:
                    for s in window.currentSpeciesList:
                        if "(" in s:
                            s = s.split(" (")[0]
                        if "/" not in s and " x " not in s and "sp." not in s:
                            leftListSpecies.append(s)
                        
        # get right list species
        rightListSpecies = []
        rightTitle = self.cboListsRight.currentText()
        for window in self.mdiParent.mdiArea.subWindowList():        
            if window.objectName() == "frmSpeciesList":
                if window.windowTitle() == rightTitle:
                    for s in window.currentSpeciesList:
                        if "(" in s:
                            s = s.split(" (")[0]
                        if "/" not in s and " x " not in s and "sp." not in s:
                            rightListSpecies.append(s)
        
        bothLists = []
        leftListOnly = []
        rightListOnly = []
        
        for ls in leftListSpecies:
          
            if ls in rightListSpecies:
                if ls not in bothLists:
                    bothLists.append(ls)
            
            else:
                
                if ls not in leftListOnly:
                    leftListOnly.append(ls)
        
        for rs in rightListSpecies:
          
            if rs in leftListSpecies:
                
                if rs not in bothLists:
                    bothLists.append(rs)
            
            else:
                
                if rs not in rightListOnly:
                    rightListOnly.append(rs)
                    
        self.lstLeftOnly.addItems(leftListOnly)
        self.lstLeftOnly.setSpacing(2)
        self.lstBoth.addItems(bothLists)
        self.lstBoth.setSpacing(2)
        self.lstRightOnly.addItems(rightListOnly)
        self.lstRightOnly.setSpacing(2)        
        self.lblLeftListOnly.setText("Species only on this list: " + str(self.lstLeftOnly.count()))
        self.lblBothLists.setText("Species on both lists: " + str(self.lstBoth.count()))
        self.lblRightListOnly.setText("Species only on this list: " + str(self.lstRightOnly.count()))
        
        
    def CreateNewIndividual(self,  speciesName):      
        sub = code_Individual.Individual()
        sub.mdiParent = self.mdiParent
        sub.FillIndividual(speciesName)
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)        
        sub.show()
        sub.resizeMe()


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
        windowWidth =  int(900  * scaleFactor)
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


