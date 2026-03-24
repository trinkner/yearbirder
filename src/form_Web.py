# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'Web.ui'
#
# Created by: PyQt5 UI code generator 5.9.2
#
# WARNING! All changes made in this file will be lost!

from PySide6 import QtCore, QtGui, QtWidgets

class Ui_frmWeb(object):
    def setupUi(self, frmWeb):
        frmWeb.setObjectName("frmWeb")
        frmWeb.resize(777, 503)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(frmWeb.sizePolicy().hasHeightForWidth())
        frmWeb.setSizePolicy(sizePolicy)
        self.scrollArea = QtWidgets.QScrollArea(frmWeb)
        self.scrollArea.setGeometry(QtCore.QRect(9, 9, 16, 16))
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setObjectName("scrollArea")
        self.scrollAreaWidgetContents = QtWidgets.QWidget()
        self.scrollAreaWidgetContents.setGeometry(QtCore.QRect(0, 0, 16, 16))
        self.scrollAreaWidgetContents.setObjectName("scrollAreaWidgetContents")
        self.scrollArea.setWidget(self.scrollAreaWidgetContents)

        self.retranslateUi(frmWeb)
        QtCore.QMetaObject.connectSlotsByName(frmWeb)

    def retranslateUi(self, frmWeb):
        _translate = QtCore.QCoreApplication.translate
        frmWeb.setWindowTitle(_translate("frmWeb", "Species Report"))

