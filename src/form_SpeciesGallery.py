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

        # ── Fixed header (never scrolls) ──────────────────────────────────────
        self.headerFrame = QtWidgets.QFrame(frmSpeciesGallery)
        self.headerFrame.setGeometry(QtCore.QRect(5, 27, 850, 65))
        self.headerFrame.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.headerFrame.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.headerFrame.setLineWidth(0)
        self.headerFrame.setObjectName("headerFrame")

        self.horizontalLayoutHeader = QtWidgets.QHBoxLayout(self.headerFrame)
        self.horizontalLayoutHeader.setContentsMargins(5, 5, 5, 5)
        self.horizontalLayoutHeader.setSpacing(6)
        self.horizontalLayoutHeader.setObjectName("horizontalLayoutHeader")

        # Left: title + count labels
        self.frameLabels = QtWidgets.QFrame(self.headerFrame)
        self.frameLabels.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frameLabels.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.frameLabels.setLineWidth(0)
        self.frameLabels.setObjectName("frameLabels")
        self.verticalLayoutLabels = QtWidgets.QVBoxLayout(self.frameLabels)
        self.verticalLayoutLabels.setContentsMargins(0, 0, 0, 0)
        self.verticalLayoutLabels.setSpacing(4)
        self.verticalLayoutLabels.setObjectName("verticalLayoutLabels")

        self.lblTitle = QtWidgets.QLabel(self.frameLabels)
        font = QtGui.QFont()
        font.setPointSize(14)
        font.setBold(True)
        self.lblTitle.setFont(font)
        self.lblTitle.setWordWrap(True)
        self.lblTitle.setObjectName("lblTitle")
        self.verticalLayoutLabels.addWidget(self.lblTitle)

        self.lblCount = QtWidgets.QLabel(self.frameLabels)
        font2 = QtGui.QFont()
        font2.setPointSize(10)
        self.lblCount.setFont(font2)
        self.lblCount.setObjectName("lblCount")
        self.verticalLayoutLabels.addWidget(self.lblCount)

        self.horizontalLayoutHeader.addWidget(self.frameLabels, 1)

        # Right: Slideshow button
        self.frameButton = QtWidgets.QFrame(self.headerFrame)
        self.frameButton.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frameButton.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.frameButton.setLineWidth(0)
        self.frameButton.setObjectName("frameButton")
        self.verticalLayoutButton = QtWidgets.QVBoxLayout(self.frameButton)
        self.verticalLayoutButton.setContentsMargins(0, 0, 0, 0)
        self.verticalLayoutButton.setSpacing(6)
        self.verticalLayoutButton.setObjectName("verticalLayoutButton")

        self.buttonSlideshow = QtWidgets.QPushButton(self.frameButton)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                                           QtWidgets.QSizePolicy.Policy.Preferred)
        self.buttonSlideshow.setSizePolicy(sizePolicy)
        self.buttonSlideshow.setObjectName("buttonSlideshow")
        self.verticalLayoutButton.addWidget(self.buttonSlideshow)

        self.buttonShowAll = QtWidgets.QPushButton(self.frameButton)
        sizePolicy2 = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                                            QtWidgets.QSizePolicy.Policy.Preferred)
        self.buttonShowAll.setSizePolicy(sizePolicy2)
        self.buttonShowAll.setObjectName("buttonShowAll")
        self.verticalLayoutButton.addWidget(self.buttonShowAll)
        self.verticalLayoutButton.addStretch(1)

        self.horizontalLayoutHeader.addWidget(self.frameButton, 0)

        # ── Scroll area (photo grid only) ─────────────────────────────────────
        self.scrollArea = QtWidgets.QScrollArea(frmSpeciesGallery)
        self.scrollArea.setGeometry(QtCore.QRect(5, 92, 850, 603))
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
        self.buttonSlideshow.setText(
            _translate("frmSpeciesGallery", "Slideshow"))
        self.buttonShowAll.setText(
            _translate("frmSpeciesGallery", "Show All"))


import icons_rc
