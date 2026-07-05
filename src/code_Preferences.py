# import the GUI forms that we create with Qt Creator
import form_Preferences
from code_Stylesheet import YBFont

from PySide6.QtGui import QFont

from PySide6.QtCore import Signal, Qt

from PySide6.QtWidgets import (
    QFileDialog,
    QLineEdit,
    QMdiSubWindow,
    QMessageBox,
)

import os


class Preferences(QMdiSubWindow, form_Preferences.Ui_frmPreferences):

    resized = Signal()

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.mdiParent = ""
        self.resized.connect(self.resizeMe)
        self.buttonBox.accepted.connect(self.savePreferences)
        self.buttonBox.rejected.connect(self.closeMe)
        self.btnSelectStartupFolder.clicked.connect(self.selectStartupFolder)
        self.btnSelectPhotoDataFile.clicked.connect(self.selectPhotoDataFile)
        self.btnToggleApiKey.clicked.connect(self.toggleApiKeyVisibility)
        self.tabWidget.currentChanged.connect(self.tabChanged)

    def fillPreferences(self):
        self.txtStartupFolder.setText(self.mdiParent.db.getStartupFolder())
        if self.mdiParent.db.getStartupFolder() != "":
            self.chkStartupFolder.setChecked(True)

        self.txtPhotoDataFile.setText(self.mdiParent.db.photoDataFileDefault)
        if self.mdiParent.db.photoDataFileDefault != "":
            self.chkPhotoDataFile.setChecked(True)

        self.txtEbirdApiKey.setEchoMode(QLineEdit.EchoMode.Password)
        self.txtEbirdApiKey.setText(self.mdiParent.db.ebirdApiKey)

        self._fillMyLocationCombos()

    def _fillMyLocationCombos(self):
        """Populate the My County and My Patch comboboxes from the open data file."""
        db = self.mdiParent.db

        self.cboMyCounty.clear()
        self.cboMyPatch.clear()

        if not db.eBirdFileOpenFlag:
            self.cboMyCounty.addItem("(open a data file to set)")
            self.cboMyPatch.addItem("(open a data file to set)")
            self.cboMyCounty.setEnabled(False)
            self.cboMyPatch.setEnabled(False)
            return

        self.cboMyCounty.setEnabled(True)
        self.cboMyPatch.setEnabled(True)

        self.cboMyCounty.addItem("")
        for county in sorted(set(db.countyList)):
            self.cboMyCounty.addItem(county)

        self.cboMyPatch.addItem("")
        for location in sorted(set(db.locationList)):
            self.cboMyPatch.addItem(location)

        # Select saved values
        idx = self.cboMyCounty.findText(db.myCounty)
        if idx >= 0:
            self.cboMyCounty.setCurrentIndex(idx)

        idx = self.cboMyPatch.findText(db.myPatch)
        if idx >= 0:
            self.cboMyPatch.setCurrentIndex(idx)

    def tabChanged(self, index):
        if self.tabWidget.tabText(index) == "My Locations":
            if not self.mdiParent.db.eBirdFileOpenFlag:
                QMessageBox.information(
                    self,
                    "No Data File Open",
                    "Please open an eBird data file before setting My County or My Patch.",
                    QMessageBox.StandardButton.Ok,
                )

    def resizeEvent(self, event):
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)

    def resizeMe(self):
        self.contentWidget.setGeometry(0, 23, self.width(), self.height() - 23)

    def closeMe(self):
        self.close()

    def scaleMe(self):
        fontSize = self.mdiParent.fontSize

        for w in ([
            self.grpStartupFolder,
            self.grpPhotoDataFile,
            self.grpEbirdApiKey,
            self.grpMyCounty,
            self.grpMyPatch,
            self.chkStartupFolder,
            self.chkPhotoDataFile,
            self.txtStartupFolder,
            self.txtPhotoDataFile,
            self.txtEbirdApiKey,
            self.lblEbirdApiKey,
            self.lblMyCountyDesc,
            self.lblMyPatchDesc,
            self.cboMyCounty,
            self.cboMyPatch,
            self.btnSelectStartupFolder,
            self.btnSelectPhotoDataFile,
            self.btnToggleApiKey,
            self.tabWidget,
        ]):
            try:
                w.setFont(QFont(YBFont, fontSize))
            except:
                pass

        self.resizeMe()

    def savePreferences(self):
        if self.chkStartupFolder.isChecked():
            self.mdiParent.db.startupFolder = self.txtStartupFolder.text()
        else:
            self.mdiParent.db.startupFolder = ""

        if self.chkPhotoDataFile.isChecked():
            self.mdiParent.db.photoDataFileDefault = self.txtPhotoDataFile.text()
        else:
            self.mdiParent.db.photoDataFileDefault = ""

        self.mdiParent.db.ebirdApiKey = self.txtEbirdApiKey.text().strip()

        if self.cboMyCounty.isEnabled():
            self.mdiParent.db.myCounty = self.cboMyCounty.currentText()

        if self.cboMyPatch.isEnabled():
            self.mdiParent.db.myPatch = self.cboMyPatch.currentText()

        self.mdiParent.db.writePreferences()
        self.mdiParent.updateMyLocationButtons()

        self.close()

    def toggleApiKeyVisibility(self):
        if self.txtEbirdApiKey.echoMode() == QLineEdit.EchoMode.Password:
            self.txtEbirdApiKey.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btnToggleApiKey.setText("Hide")
        else:
            self.txtEbirdApiKey.setEchoMode(QLineEdit.EchoMode.Password)
            self.btnToggleApiKey.setText("Show")

    def selectStartupFolder(self):
        folder = str(QFileDialog.getExistingDirectory(
            self, "Select Startup Folder", self.mdiParent.db.startupFolder
        ))
        if folder != "":
            self.txtStartupFolder.setText(folder)
            self.chkStartupFolder.setChecked(True)

    def selectPhotoDataFile(self):
        fname = QFileDialog.getOpenFileName(
            self, "Select Photo Data File",
            self.mdiParent.db.photoDataFile,
            "Photo Data Files (*.jsonl *.csv)"
        )
        if fname[0] != "":
            self.txtPhotoDataFile.setText(fname[0])
            self.chkPhotoDataFile.setChecked(True)
