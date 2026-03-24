# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'form_ManagePhotos.ui'
#
# Created by: PyQt5 UI code generator 5.11.2
#
# WARNING! All changes made in this file will be lost!

from PySide6 import QtCore, QtGui, QtWidgets

class Ui_frmManagePhotos(object):
    def setupUi(self, frmManagePhotos):
        frmManagePhotos.setObjectName("frmManagePhotos")
        frmManagePhotos.resize(897, 680)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(frmManagePhotos.sizePolicy().hasHeightForWidth())
        frmManagePhotos.setSizePolicy(sizePolicy)
        frmManagePhotos.setMinimumSize(QtCore.QSize(200, 300))
        frmManagePhotos.setSizeIncrement(QtCore.QSize(0, 0))
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icon_bird_white.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        frmManagePhotos.setWindowIcon(icon)
        self.scrollArea = QtWidgets.QScrollArea(frmManagePhotos)
        self.scrollArea.setGeometry(QtCore.QRect(0, 10, 891, 601))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.scrollArea.sizePolicy().hasHeightForWidth())
        self.scrollArea.setSizePolicy(sizePolicy)
        self.scrollArea.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scrollArea.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.scrollArea.setLineWidth(0)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setObjectName("scrollArea")
        self.layLists = QtWidgets.QWidget()
        self.layLists.setGeometry(QtCore.QRect(0, 0, 891, 601))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.layLists.sizePolicy().hasHeightForWidth())
        self.layLists.setSizePolicy(sizePolicy)
        self.layLists.setObjectName("layLists")
        self.verticalLayout_3 = QtWidgets.QVBoxLayout(self.layLists)
        self.verticalLayout_3.setContentsMargins(5, 5, 5, 5)
        self.verticalLayout_3.setSpacing(4)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.gridPhotos = QtWidgets.QGridLayout()
        self.gridPhotos.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        self.gridPhotos.setObjectName("gridPhotos")
        self.verticalLayout_3.addLayout(self.gridPhotos)
        self.scrollArea.setWidget(self.layLists)
        self.btnSavePhotoSettings = QtWidgets.QPushButton(frmManagePhotos)
        self.btnSavePhotoSettings.setGeometry(QtCore.QRect(700, 630, 181, 28))
        self.btnSavePhotoSettings.setObjectName("btnSavePhotoSettings")
        self.btnCancel = QtWidgets.QPushButton(frmManagePhotos)
        self.btnCancel.setGeometry(QtCore.QRect(510, 630, 181, 28))
        self.btnCancel.setObjectName("btnCancel")
        self.actionSetDateFilter = QtGui.QAction(frmManagePhotos)
        self.actionSetDateFilter.setObjectName("actionSetDateFilter")
        self.actionSetLocationFilter = QtGui.QAction(frmManagePhotos)
        self.actionSetLocationFilter.setObjectName("actionSetLocationFilter")
        self.actionSetFirstDateFilter = QtGui.QAction(frmManagePhotos)
        self.actionSetFirstDateFilter.setObjectName("actionSetFirstDateFilter")
        self.actionSetLastDateFilter = QtGui.QAction(frmManagePhotos)
        self.actionSetLastDateFilter.setObjectName("actionSetLastDateFilter")
        self.actionSetSpeciesFilter = QtGui.QAction(frmManagePhotos)
        self.actionSetSpeciesFilter.setObjectName("actionSetSpeciesFilter")
        self.actionSetCountryFilter = QtGui.QAction(frmManagePhotos)
        self.actionSetCountryFilter.setObjectName("actionSetCountryFilter")
        self.actionSetStateFilter = QtGui.QAction(frmManagePhotos)
        self.actionSetStateFilter.setObjectName("actionSetStateFilter")
        self.actionSetCountyFilter = QtGui.QAction(frmManagePhotos)
        self.actionSetCountyFilter.setObjectName("actionSetCountyFilter")

        self.retranslateUi(frmManagePhotos)
        QtCore.QMetaObject.connectSlotsByName(frmManagePhotos)

    def retranslateUi(self, frmManagePhotos):
        _translate = QtCore.QCoreApplication.translate
        frmManagePhotos.setWindowTitle(_translate("frmManagePhotos", "Species Report"))
        self.btnSavePhotoSettings.setText(_translate("frmManagePhotos", "OK"))
        self.btnCancel.setText(_translate("frmManagePhotos", "Cancel"))
        self.actionSetDateFilter.setText(_translate("frmManagePhotos", "Set Filter to Date"))
        self.actionSetLocationFilter.setText(_translate("frmManagePhotos", "Set Filter to Location"))
        self.actionSetFirstDateFilter.setText(_translate("frmManagePhotos", "Set Filter to \"First\" Date"))
        self.actionSetLastDateFilter.setText(_translate("frmManagePhotos", "Set Filter to \"Last\" Date"))
        self.actionSetSpeciesFilter.setText(_translate("frmManagePhotos", "Set Filter to Species"))
        self.actionSetCountryFilter.setText(_translate("frmManagePhotos", "Set Filter to Country"))
        self.actionSetStateFilter.setText(_translate("frmManagePhotos", "Set Filter to State"))
        self.actionSetCountyFilter.setText(_translate("frmManagePhotos", "Set Filter to County"))

import icons_rc

if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    frmManagePhotos = QtWidgets.QWidget()
    ui = Ui_frmManagePhotos()
    ui.setupUi(frmManagePhotos)
    frmManagePhotos.show()
    sys.exit(app.exec())

