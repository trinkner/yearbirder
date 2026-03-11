# import project files
import form_Find
import code_Lists

from PyQt5.QtGui import (
    QCursor,
    QFont
    )
    
from PyQt5.QtCore import (
    Qt,
    pyqtSignal
    )
    
from PyQt5.QtWidgets import (
    QApplication, 
    QMdiSubWindow,
    )


class Find(QMdiSubWindow, form_Find.Ui_frmFind):
    
    resized = pyqtSignal()

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose,True)
        self.mdiParent = ""
        self.resized.connect(self.resizeMe)    
        self.btnFind.clicked.connect(self.CreateFindResults)
        self.btnCancel.clicked.connect(self.Cancel)      
        self.txtFind.setFocus()


    def CreateFindResults(self):

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        
        #The user has accepted the has clicked OK
        searchString = self.txtFind.text()
        
        # get names of which checkboxes are checked
        checkedBoxes = []
        for c in ([
            self.chkCommonName, 
            self.chkScientificName,
            self.chkCountryName,
            self.chkStateName,
            self.chkCountyName,
            self.chkLocationName,
            self.chkSpeciesComments,
            self.chkChecklistComments
            ]):
            if c.isChecked() is True:
                checkedBoxes.append(c.objectName())
                
        # get search results
        found = self.mdiParent.db.GetFindResults(searchString, checkedBoxes)
    
        # create child window 
        sub = code_Lists.Lists()
        
        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self.mdiParent
        
        # call the child's fill routine, passing the filter settings list
        sub.FillFindChecklists(found)
        
        self.parent().parent().addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self)        
        sub.show()  

        QApplication.restoreOverrideCursor()   
        
        # close the Find child
        self.close()


    def Cancel(self):
        
        self.close()


    def resizeEvent(self, event):
        #routine to handle events on objects, like clicks, lost focus, gained forcus, etc.        
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)
        
            
    def resizeMe(self):

        windowWidth =  self.frameGeometry().width()
        windowHeight = self.frameGeometry().height()
        self.scrollArea.setGeometry(5, 27, windowWidth - 10, windowHeight - 32)

   
    def scaleMe(self):
       
        metrics = self.txtFind.fontMetrics()
        textHeight = int(metrics.boundingRect("ABCD").height())
        
        self.txtFind.resize(self.txtFind.x(), textHeight)
        self.lblFind.resize(self.txtFind.x(), textHeight)
       
        fontSize = self.mdiParent.fontSize
        for c in ([
            self.chkCommonName, 
            self.chkScientificName,
            self.chkCountryName,
            self.chkStateName,
            self.chkCountyName,
            self.chkLocationName,
            self.chkSpeciesComments,
            self.chkChecklistComments
            ]):
            c.setFont(QFont("Helvetica", fontSize))  
            c.resize(c.x(), textHeight * 1.1)

        scaleFactor = self.mdiParent.scaleFactor
        windowWidth =  400 * scaleFactor
        windowHeight = 300 * scaleFactor            
        self.resize(windowWidth, windowHeight)

        baseFont = QFont(QFont("Helvetica", fontSize))
        self.lblFind.setFont(baseFont)
        self.lblWhatToSearch.setFont(baseFont)
        self.txtFind.setFont(baseFont)

        metrics = self.txtFind.fontMetrics()
        textHeight = int(metrics.boundingRect("2222-22-22").height())          
        
        self.txtFind.resize(self.txtFind.x(), textHeight)
        self.lblFind.resize(self.txtFind.x(), textHeight)
        
