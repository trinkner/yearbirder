# import the GUI forms that we create with Qt Creator
import form_Preferences

# import the Qt components we'll use
# do this so later we won't have to clutter our code with references to parent Qt classes 
    
from PySide6.QtGui import (
    QFont
    )

from PySide6.QtCore import (
    Signal,
    Qt
    )

from PySide6.QtWidgets import (
    QFileDialog,
    QMdiSubWindow
    )

import os


class Preferences(QMdiSubWindow, form_Preferences.Ui_frmPreferences):

    # create "resized" as a signal that the window can emit
    # we respond to this signal with the form's resizeMe method below
    resized = Signal()   
            
    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose,True)
        self.mdiParent = ""        
        self.resized.connect(self.resizeMe)
        self.buttonBox.accepted.connect(self.savePreferences)
        self.buttonBox.rejected.connect(self.closeMe)
        self.btnSelectStartupFolder.clicked.connect(self.selectStartupFolder)
        self.btnSelectPhotoDataFile.clicked.connect(self.selectPhotoDataFile)
                
    def fillPreferences(self):
        
        self.txtStartupFolder.setText(self.mdiParent.db.getStartupFolder())
        if self.mdiParent.db.getStartupFolder() != "":
            self.chkStartupFolder.setChecked(True)
            
        self.txtPhotoDataFile.setText(self.mdiParent.db.getPhotoDataFile())
        if self.mdiParent.db.getPhotoDataFile() != "":
            self.chkPhotoDataFile.setChecked(True)
        
            
    def resizeEvent(self, event):
        #routine to handle events on objects, like clicks, lost focus, gained forcus, etc.        
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)
        
        
    def resizeMe(self):

        return
    
    
    def closeMe(self):
        self.close()
   
   
    def scaleMe(self):
                       
        fontSize = self.mdiParent.fontSize
        
        #scale the font for all widgets in window
        for w in ([
            self.grpStartupFolder, 
            self.grpPhotoDataFile, 
            self.chkStartupFolder, 
            self.chkPhotoDataFile, 
            self.txtStartupFolder, 
            self.txtPhotoDataFile,
            self.btnSelectStartupFolder,
            self.btnSelectPhotoDataFile
            ]):
            
            try:
                w.setFont(QFont("Helvetica", fontSize))
            except:
                pass 

        self.adjustSize()
        
        
    def savePreferences(self):
        
        if self.chkStartupFolder.isChecked():
            self.mdiParent.db.startupFolder = self.txtStartupFolder.text()
        else:
            self.mdiParent.db.startupFolder = ""
            
        if self.chkPhotoDataFile.isChecked():
            self.mdiParent.db.photoDataFile = self.txtPhotoDataFile.text()
        else:
            self.mdiParent.db.photoDataFile = ""
            
        self.mdiParent.db.writePreferences()
        
        self.close()
        
        
    def selectStartupFolder(self):
        
        folder = str(QFileDialog.getExistingDirectory(self, "Select Startup Folder", self.mdiParent.db.startupFolder))
        
        if folder != "":
            
            self.txtStartupFolder.setText(folder)
            self.chkStartupFolder.setChecked(True)
        
    
    def selectPhotoDataFile(self):
        
        fname = QFileDialog.getOpenFileName(self,"Select Photo Data File", self.mdiParent.db.photoDataFile, "Photo Data Files (*.csv)")
        
        if fname[0] != "":
        
            self.txtPhotoDataFile.setText(fname[0])
            self.chkPhotoDataFile.setChecked(True)

