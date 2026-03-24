# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'Checklists.ui'
#
# Created by: PyQt5 UI code generator 5.10
#
# WARNING! All changes made in this file will be lost!

from PySide6 import QtCore, QtGui, QtWidgets

class Ui_frmChecklists(object):
    def setupUi(self, frmChecklists):
        frmChecklists.setObjectName("frmChecklists")
        frmChecklists.resize(800, 590)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(frmChecklists.sizePolicy().hasHeightForWidth())
        frmChecklists.setSizePolicy(sizePolicy)
        frmChecklists.setMinimumSize(QtCore.QSize(800, 590))
        frmChecklists.setMaximumSize(QtCore.QSize(800, 590))
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icon_checklists_white.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        frmChecklists.setWindowIcon(icon)
        self.txtFind = QtWidgets.QLineEdit(frmChecklists)
        self.txtFind.setGeometry(QtCore.QRect(570, 115, 221, 22))
        self.txtFind.setObjectName("txtFind")
        self.lblChecklists = QtWidgets.QLabel(frmChecklists)
        self.lblChecklists.setGeometry(QtCore.QRect(10, 120, 221, 16))
        self.lblChecklists.setObjectName("lblChecklists")
        self.tblChecklists = QtWidgets.QTableWidget(frmChecklists)
        self.tblChecklists.setGeometry(QtCore.QRect(10, 140, 781, 441))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.tblChecklists.sizePolicy().hasHeightForWidth())
        self.tblChecklists.setSizePolicy(sizePolicy)
        self.tblChecklists.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.tblChecklists.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.tblChecklists.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tblChecklists.setObjectName("tblChecklists")
        self.tblChecklists.setColumnCount(0)
        self.tblChecklists.setRowCount(0)
        self.tblChecklists.horizontalHeader().setVisible(False)
        self.tblChecklists.horizontalHeader().setHighlightSections(False)
        self.tblChecklists.verticalHeader().setVisible(False)
        self.tblChecklists.verticalHeader().setHighlightSections(False)
        self.label = QtWidgets.QLabel(frmChecklists)
        self.label.setGeometry(QtCore.QRect(500, 120, 59, 14))
        self.label.setLayoutDirection(QtCore.Qt.LeftToRight)
        self.label.setAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignTrailing|QtCore.Qt.AlignVCenter)
        self.label.setObjectName("label")
        self.lblDateRange = QtWidgets.QLabel(frmChecklists)
        self.lblDateRange.setGeometry(QtCore.QRect(10, 65, 551, 21))
        font = QtGui.QFont()
        font.setPointSize(12)
        font.setBold(False)
        font.setWeight(QtGui.QFont.Weight.Normal)
        self.lblDateRange.setFont(font)
        self.lblDateRange.setObjectName("lblDateRange")
        self.lblLocation = QtWidgets.QLabel(frmChecklists)
        self.lblLocation.setGeometry(QtCore.QRect(10, 30, 771, 35))
        font = QtGui.QFont()
        font.setPointSize(14)
        font.setBold(True)
        font.setWeight(QtGui.QFont.Weight.Bold)
        self.lblLocation.setFont(font)
        self.lblLocation.setObjectName("lblLocation")
        self.lblDetails = QtWidgets.QLabel(frmChecklists)
        self.lblDetails.setGeometry(QtCore.QRect(10, 90, 551, 21))
        font = QtGui.QFont()
        font.setPointSize(12)
        font.setBold(False)
        font.setWeight(QtGui.QFont.Weight.Normal)
        self.lblDetails.setFont(font)
        self.lblDetails.setObjectName("lblDetails")

        self.retranslateUi(frmChecklists)
        QtCore.QMetaObject.connectSlotsByName(frmChecklists)

    def retranslateUi(self, frmChecklists):
        _translate = QtCore.QCoreApplication.translate
        frmChecklists.setWindowTitle(_translate("frmChecklists", "Species Report"))
        self.lblChecklists.setText(_translate("frmChecklists", "Checklists"))
        self.tblChecklists.setSortingEnabled(True)
        self.label.setText(_translate("frmChecklists", "Search:"))
        self.lblDateRange.setText(_translate("frmChecklists", "Date Range"))
        self.lblLocation.setText(_translate("frmChecklists", "Location"))
        self.lblDetails.setText(_translate("frmChecklists", "Details Label"))

import icons_rc
