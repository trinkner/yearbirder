# -*- coding: utf-8 -*-

from PySide6 import QtCore, QtGui, QtWidgets

class Ui_frmPreferences(object):
    def setupUi(self, frmPreferences):
        frmPreferences.setObjectName("frmPreferences")
        frmPreferences.resize(840, 480)
        frmPreferences.setMinimumSize(QtCore.QSize(500, 360))
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icon_Yearbirder_small.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        frmPreferences.setWindowIcon(icon)

        # Container widget
        self.contentWidget = QtWidgets.QWidget(frmPreferences)
        self.contentWidget.setObjectName("contentWidget")
        # Inset to leave the native window frame visible (see resizeMe, which
        # keeps these margins on every resize).
        self.contentWidget.setGeometry(5, 27, 830, 445)

        self.mainLayout = QtWidgets.QVBoxLayout(self.contentWidget)
        self.mainLayout.setContentsMargins(10, 10, 10, 10)
        self.mainLayout.setSpacing(10)
        self.mainLayout.setObjectName("mainLayout")

        # ── Tab widget ───────────────────────────────────────────────────────
        self.tabWidget = QtWidgets.QTabWidget(self.contentWidget)
        self.tabWidget.setObjectName("tabWidget")
        self.mainLayout.addWidget(self.tabWidget)

        # ── Tab 1: Default Files ─────────────────────────────────────────────
        self.tabDefaultFiles = QtWidgets.QWidget()
        self.tabDefaultFiles.setObjectName("tabDefaultFiles")
        self.tabLayout = QtWidgets.QVBoxLayout(self.tabDefaultFiles)
        self.tabLayout.setContentsMargins(10, 14, 10, 10)
        self.tabLayout.setSpacing(10)

        # Startup Folder group
        self.grpStartupFolder = QtWidgets.QGroupBox(self.tabDefaultFiles)
        self.grpStartupFolder.setObjectName("grpStartupFolder")
        self.grpStartupFolder.setStyleSheet(
            "QGroupBox { font-size: 14px; font-weight: bold; } "
            "QGroupBox QWidget { font-size: 13px; font-weight: normal; }"
        )
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.grpStartupFolder)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.chkStartupFolder = QtWidgets.QCheckBox(self.grpStartupFolder)
        self.chkStartupFolder.setObjectName("chkStartupFolder")
        self.verticalLayout_2.addWidget(self.chkStartupFolder)
        self.hboxStartup = QtWidgets.QHBoxLayout()
        self.hboxStartup.setObjectName("hboxStartup")
        self.txtStartupFolder = QtWidgets.QLineEdit(self.grpStartupFolder)
        self.txtStartupFolder.setObjectName("txtStartupFolder")
        self.hboxStartup.addWidget(self.txtStartupFolder)
        self.btnSelectStartupFolder = QtWidgets.QPushButton(self.grpStartupFolder)
        self.btnSelectStartupFolder.setObjectName("btnSelectStartupFolder")
        self.hboxStartup.addWidget(self.btnSelectStartupFolder)
        self.verticalLayout_2.addLayout(self.hboxStartup)
        self.tabLayout.addWidget(self.grpStartupFolder)

        # Media Catalog File group
        self.grpPhotoDataFile = QtWidgets.QGroupBox(self.tabDefaultFiles)
        self.grpPhotoDataFile.setObjectName("grpPhotoDataFile")
        self.grpPhotoDataFile.setStyleSheet(
            "QGroupBox { font-size: 14px; font-weight: bold; } "
            "QGroupBox QWidget { font-size: 13px; font-weight: normal; }"
        )
        self.verticalLayout = QtWidgets.QVBoxLayout(self.grpPhotoDataFile)
        self.verticalLayout.setObjectName("verticalLayout")
        self.chkPhotoDataFile = QtWidgets.QCheckBox(self.grpPhotoDataFile)
        self.chkPhotoDataFile.setObjectName("chkPhotoDataFile")
        self.verticalLayout.addWidget(self.chkPhotoDataFile)
        self.hboxPhoto = QtWidgets.QHBoxLayout()
        self.hboxPhoto.setObjectName("hboxPhoto")
        self.txtPhotoDataFile = QtWidgets.QLineEdit(self.grpPhotoDataFile)
        self.txtPhotoDataFile.setObjectName("txtPhotoDataFile")
        self.hboxPhoto.addWidget(self.txtPhotoDataFile)
        self.btnSelectPhotoDataFile = QtWidgets.QPushButton(self.grpPhotoDataFile)
        self.btnSelectPhotoDataFile.setObjectName("btnSelectPhotoDataFile")
        self.hboxPhoto.addWidget(self.btnSelectPhotoDataFile)
        self.verticalLayout.addLayout(self.hboxPhoto)
        self.tabLayout.addWidget(self.grpPhotoDataFile)

        self.tabLayout.addStretch(1)
        self.tabWidget.addTab(self.tabDefaultFiles, "Default Files")

        # ── Tab 2: My Locations ──────────────────────────────────────────────
        self.tabMyLocations = QtWidgets.QWidget()
        self.tabMyLocations.setObjectName("tabMyLocations")
        self.tabMyLocLayout = QtWidgets.QVBoxLayout(self.tabMyLocations)
        self.tabMyLocLayout.setContentsMargins(10, 14, 10, 10)
        self.tabMyLocLayout.setSpacing(14)

        # My County group
        self.grpMyCounty = QtWidgets.QGroupBox(self.tabMyLocations)
        self.grpMyCounty.setObjectName("grpMyCounty")
        self.grpMyCounty.setStyleSheet(
            "QGroupBox { font-size: 14px; font-weight: bold; } "
            "QGroupBox QWidget { font-size: 13px; font-weight: normal; }"
        )
        self.vboxMyCounty = QtWidgets.QVBoxLayout(self.grpMyCounty)
        self.vboxMyCounty.setObjectName("vboxMyCounty")
        self.lblMyCountyDesc = QtWidgets.QLabel(self.grpMyCounty)
        self.lblMyCountyDesc.setObjectName("lblMyCountyDesc")
        self.lblMyCountyDesc.setWordWrap(True)
        self.vboxMyCounty.addWidget(self.lblMyCountyDesc)
        self.cboMyCounty = QtWidgets.QComboBox(self.grpMyCounty)
        self.cboMyCounty.setObjectName("cboMyCounty")
        self.vboxMyCounty.addWidget(self.cboMyCounty)
        self.tabMyLocLayout.addWidget(self.grpMyCounty)

        # My Patch group
        self.grpMyPatch = QtWidgets.QGroupBox(self.tabMyLocations)
        self.grpMyPatch.setObjectName("grpMyPatch")
        self.grpMyPatch.setStyleSheet(
            "QGroupBox { font-size: 14px; font-weight: bold; } "
            "QGroupBox QWidget { font-size: 13px; font-weight: normal; }"
        )
        self.vboxMyPatch = QtWidgets.QVBoxLayout(self.grpMyPatch)
        self.vboxMyPatch.setObjectName("vboxMyPatch")
        self.lblMyPatchDesc = QtWidgets.QLabel(self.grpMyPatch)
        self.lblMyPatchDesc.setObjectName("lblMyPatchDesc")
        self.lblMyPatchDesc.setWordWrap(True)
        self.vboxMyPatch.addWidget(self.lblMyPatchDesc)
        self.cboMyPatch = QtWidgets.QComboBox(self.grpMyPatch)
        self.cboMyPatch.setObjectName("cboMyPatch")
        self.vboxMyPatch.addWidget(self.cboMyPatch)
        self.tabMyLocLayout.addWidget(self.grpMyPatch)

        self.tabMyLocLayout.addStretch(1)
        self.tabWidget.addTab(self.tabMyLocations, "My Locations")

        # ── Tab 3: eBird ─────────────────────────────────────────────────────
        self.tabEbird = QtWidgets.QWidget()
        self.tabEbird.setObjectName("tabEbird")
        self.tabEbirdLayout = QtWidgets.QVBoxLayout(self.tabEbird)
        self.tabEbirdLayout.setContentsMargins(10, 14, 10, 10)
        self.tabEbirdLayout.setSpacing(10)

        self.grpEbirdApiKey = QtWidgets.QGroupBox(self.tabEbird)
        self.grpEbirdApiKey.setObjectName("grpEbirdApiKey")
        self.grpEbirdApiKey.setStyleSheet(
            "QGroupBox { font-size: 14px; font-weight: bold; } "
            "QGroupBox QWidget { font-size: 13px; font-weight: normal; }"
        )
        self.verticalLayout_3 = QtWidgets.QVBoxLayout(self.grpEbirdApiKey)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.lblEbirdApiKey = QtWidgets.QLabel(self.grpEbirdApiKey)
        self.lblEbirdApiKey.setObjectName("lblEbirdApiKey")
        self.lblEbirdApiKey.setWordWrap(True)
        self.lblEbirdApiKey.setOpenExternalLinks(True)
        self.verticalLayout_3.addWidget(self.lblEbirdApiKey)
        self.hboxApiKey = QtWidgets.QHBoxLayout()
        self.hboxApiKey.setObjectName("hboxApiKey")
        self.txtEbirdApiKey = QtWidgets.QLineEdit(self.grpEbirdApiKey)
        self.txtEbirdApiKey.setObjectName("txtEbirdApiKey")
        self.hboxApiKey.addWidget(self.txtEbirdApiKey)
        self.btnToggleApiKey = QtWidgets.QPushButton(self.grpEbirdApiKey)
        self.btnToggleApiKey.setObjectName("btnToggleApiKey")
        self.hboxApiKey.addWidget(self.btnToggleApiKey)
        self.verticalLayout_3.addLayout(self.hboxApiKey)
        self.tabEbirdLayout.addWidget(self.grpEbirdApiKey)

        self.tabEbirdLayout.addStretch(1)
        self.tabWidget.addTab(self.tabEbird, "eBird")

        # ── Cancel / OK ──────────────────────────────────────────────────────
        self.buttonBox = QtWidgets.QDialogButtonBox(self.contentWidget)
        self.buttonBox.setStandardButtons(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel |
            QtWidgets.QDialogButtonBox.StandardButton.Ok
        )
        self.buttonBox.setObjectName("buttonBox")
        self.mainLayout.addWidget(self.buttonBox)

        # Actions (unchanged)
        self.actionSetDateFilter = QtGui.QAction(frmPreferences)
        self.actionSetDateFilter.setObjectName("actionSetDateFilter")
        self.actionSetLocationFilter = QtGui.QAction(frmPreferences)
        self.actionSetLocationFilter.setObjectName("actionSetLocationFilter")
        self.actionSetFirstDateFilter = QtGui.QAction(frmPreferences)
        self.actionSetFirstDateFilter.setObjectName("actionSetFirstDateFilter")
        self.actionSetLastDateFilter = QtGui.QAction(frmPreferences)
        self.actionSetLastDateFilter.setObjectName("actionSetLastDateFilter")
        self.actionSetSpeciesFilter = QtGui.QAction(frmPreferences)
        self.actionSetSpeciesFilter.setObjectName("actionSetSpeciesFilter")
        self.actionSetCountryFilter = QtGui.QAction(frmPreferences)
        self.actionSetCountryFilter.setObjectName("actionSetCountryFilter")
        self.actionSetStateFilter = QtGui.QAction(frmPreferences)
        self.actionSetStateFilter.setObjectName("actionSetStateFilter")
        self.actionSetCountyFilter = QtGui.QAction(frmPreferences)
        self.actionSetCountyFilter.setObjectName("actionSetCountyFilter")

        self.retranslateUi(frmPreferences)
        QtCore.QMetaObject.connectSlotsByName(frmPreferences)

    def retranslateUi(self, frmPreferences):
        _translate = QtCore.QCoreApplication.translate
        frmPreferences.setWindowTitle(_translate("frmPreferences", "Preferences"))

        self.grpStartupFolder.setTitle(_translate("frmPreferences", "Startup Folder"))
        self.chkStartupFolder.setText(_translate("frmPreferences", "Set eBird data folder. At startup, Yearbirder will open the most recent eBird file in the folder (e.g., your download folder)."))
        self.btnSelectStartupFolder.setText(_translate("frmPreferences", "Select"))

        self.grpPhotoDataFile.setTitle(_translate("frmPreferences", "Media Catalog File"))
        self.chkPhotoDataFile.setText(_translate("frmPreferences", "Load media catalog file at startup. (Only helpful if you have photos.)"))
        self.btnSelectPhotoDataFile.setText(_translate("frmPreferences", "Select"))

        self.grpMyCounty.setTitle(_translate("frmPreferences", "My County"))
        self.lblMyCountyDesc.setText(_translate("frmPreferences", "Select your home county. A \"My County\" button will appear at the top of the Sighting Filter to set the filter to this county with one click."))
        self.grpMyPatch.setTitle(_translate("frmPreferences", "My Patch"))
        self.lblMyPatchDesc.setText(_translate("frmPreferences", "Select your regular birding location (\"patch\"). A \"My Patch\" button will appear at the top of the Sighting Filter to set the filter to this location with one click."))

        self.grpEbirdApiKey.setTitle(_translate("frmPreferences", "eBird API Key"))
        self.lblEbirdApiKey.setText(_translate("frmPreferences", "Optional. Required for reports and maps that use eBird server data. Get a free key at <a href=\"https://ebird.org/api/keygen\">ebird.org/api/keygen</a>."))
        self.btnToggleApiKey.setText(_translate("frmPreferences", "Show"))

        self.actionSetDateFilter.setText(_translate("frmPreferences", "Set Filter to Date"))
        self.actionSetLocationFilter.setText(_translate("frmPreferences", "Set Filter to Location"))
        self.actionSetFirstDateFilter.setText(_translate("frmPreferences", "Set Filter to \"First\" Date"))
        self.actionSetLastDateFilter.setText(_translate("frmPreferences", "Set Filter to \"Last\" Date"))
        self.actionSetSpeciesFilter.setText(_translate("frmPreferences", "Set Filter to Species"))
        self.actionSetCountryFilter.setText(_translate("frmPreferences", "Set Filter to Country"))
        self.actionSetStateFilter.setText(_translate("frmPreferences", "Set Filter to State"))
        self.actionSetCountyFilter.setText(_translate("frmPreferences", "Set Filter to County"))

import icons_rc

if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    frmPreferences = QtWidgets.QWidget()
    ui = Ui_frmPreferences()
    ui.setupUi(frmPreferences)
    frmPreferences.show()
    sys.exit(app.exec())
