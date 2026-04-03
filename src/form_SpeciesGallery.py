# -*- coding: utf-8 -*-

from PySide6 import QtCore, QtGui, QtWidgets


class Ui_frmSpeciesGallery(object):
    def setupUi(self, frmSpeciesGallery):
        frmSpeciesGallery.setObjectName("frmSpeciesGallery")
        frmSpeciesGallery.resize(860, 700)
        frmSpeciesGallery.setMinimumSize(QtCore.QSize(300, 300))
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icon_camera_white.png"),
                       QtGui.QIcon.Normal, QtGui.QIcon.Off)
        frmSpeciesGallery.setWindowIcon(icon)

        self.scrollArea = QtWidgets.QScrollArea(frmSpeciesGallery)
        self.scrollArea.setGeometry(QtCore.QRect(0, 0, 860, 700))
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scrollArea.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.scrollArea.setObjectName("scrollArea")

        self.layGallery = QtWidgets.QWidget()
        self.layGallery.setObjectName("layGallery")

        self.verticalLayout = QtWidgets.QVBoxLayout(self.layGallery)
        self.verticalLayout.setContentsMargins(10, 10, 10, 10)
        self.verticalLayout.setSpacing(6)
        self.verticalLayout.setObjectName("verticalLayout")

        self.lblTitle = QtWidgets.QLabel(self.layGallery)
        font = QtGui.QFont()
        font.setPointSize(14)
        font.setBold(True)
        self.lblTitle.setFont(font)
        self.lblTitle.setWordWrap(True)
        self.lblTitle.setObjectName("lblTitle")
        self.verticalLayout.addWidget(self.lblTitle)

        self.lblCount = QtWidgets.QLabel(self.layGallery)
        font2 = QtGui.QFont()
        font2.setPointSize(10)
        self.lblCount.setFont(font2)
        self.lblCount.setObjectName("lblCount")
        self.verticalLayout.addWidget(self.lblCount)

        self.gridPhotos = QtWidgets.QGridLayout()
        self.gridPhotos.setObjectName("gridPhotos")
        self.gridPhotos.setSpacing(6)
        self.verticalLayout.addLayout(self.gridPhotos)
        self.verticalLayout.addStretch(1)

        self.scrollArea.setWidget(self.layGallery)

        self.retranslateUi(frmSpeciesGallery)
        QtCore.QMetaObject.connectSlotsByName(frmSpeciesGallery)

    def retranslateUi(self, frmSpeciesGallery):
        _translate = QtCore.QCoreApplication.translate
        frmSpeciesGallery.setWindowTitle(
            _translate("frmSpeciesGallery", "Species Gallery"))
        self.lblTitle.setText(
            _translate("frmSpeciesGallery", "Species Gallery"))
        self.lblCount.setText(
            _translate("frmSpeciesGallery", ""))


import icons_rc
