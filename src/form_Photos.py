# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'form_Photos.ui'
#
# Created by: PyQt5 UI code generator 5.11.2
#
# WARNING! All changes made in this file will be lost!

from PySide6 import QtCore, QtGui, QtWidgets

class Ui_frmPhotos(object):
    def setupUi(self, frmPhotos):
        frmPhotos.setObjectName("frmPhotos")
        frmPhotos.resize(671, 505)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(frmPhotos.sizePolicy().hasHeightForWidth())
        frmPhotos.setSizePolicy(sizePolicy)
        frmPhotos.setMinimumSize(QtCore.QSize(200, 300))
        frmPhotos.setSizeIncrement(QtCore.QSize(0, 0))
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icon_bird_white.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        frmPhotos.setWindowIcon(icon)

        # ── Fixed header (never scrolls) ──────────────────────────────────────
        self.headerFrame = QtWidgets.QFrame(frmPhotos)
        self.headerFrame.setGeometry(QtCore.QRect(0, 0, 671, 130))
        self.headerFrame.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.headerFrame.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.headerFrame.setLineWidth(0)
        self.headerFrame.setObjectName("headerFrame")

        # Top-level horizontal split: labels (left) | button (right)
        self.horizontalLayoutHeader = QtWidgets.QHBoxLayout(self.headerFrame)
        self.horizontalLayoutHeader.setContentsMargins(5, 5, 5, 5)
        self.horizontalLayoutHeader.setSpacing(6)
        self.horizontalLayoutHeader.setObjectName("horizontalLayoutHeader")

        # ── Left subframe: all labels + sort controls ─────────────────────────
        self.frameLabels = QtWidgets.QFrame(self.headerFrame)
        self.frameLabels.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frameLabels.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.frameLabels.setLineWidth(0)
        self.frameLabels.setObjectName("frameLabels")
        self.verticalLayoutLabels = QtWidgets.QVBoxLayout(self.frameLabels)
        self.verticalLayoutLabels.setContentsMargins(0, 0, 0, 0)
        self.verticalLayoutLabels.setSpacing(4)
        self.verticalLayoutLabels.setObjectName("verticalLayoutLabels")

        self.lblLocation = QtWidgets.QLabel(self.frameLabels)
        font = QtGui.QFont()
        font.setPointSize(14)
        font.setBold(True)
        font.setWeight(QtGui.QFont.Weight.Bold)
        self.lblLocation.setFont(font)
        self.lblLocation.setWordWrap(True)
        self.lblLocation.setObjectName("lblLocation")
        self.verticalLayoutLabels.addWidget(self.lblLocation)

        self.lblDateRange = QtWidgets.QLabel(self.frameLabels)
        font = QtGui.QFont()
        font.setPointSize(12)
        font.setBold(False)
        font.setWeight(QtGui.QFont.Weight.Normal)
        self.lblDateRange.setFont(font)
        self.lblDateRange.setLineWidth(0)
        self.lblDateRange.setObjectName("lblDateRange")
        self.verticalLayoutLabels.addWidget(self.lblDateRange)

        self.lblDetails = QtWidgets.QLabel(self.frameLabels)
        font = QtGui.QFont()
        font.setPointSize(12)
        font.setBold(False)
        font.setWeight(QtGui.QFont.Weight.Normal)
        self.lblDetails.setFont(font)
        self.lblDetails.setLineWidth(0)
        self.lblDetails.setObjectName("lblDetails")
        self.verticalLayoutLabels.addWidget(self.lblDetails)

        self.lblSpecies = QtWidgets.QLabel(self.frameLabels)
        font = QtGui.QFont()
        font.setPointSize(10)
        self.lblSpecies.setFont(font)
        self.lblSpecies.setObjectName("lblSpecies")
        self.verticalLayoutLabels.addWidget(self.lblSpecies)

        self.lblSortBy = QtWidgets.QLabel(self.frameLabels)
        self.lblSortBy.setObjectName("lblSortBy")

        self.sortButtonGroup = QtWidgets.QButtonGroup(self.frameLabels)
        self.sortButtonGroup.setObjectName("sortButtonGroup")

        self.rdoSortSpecies = QtWidgets.QRadioButton(self.frameLabels)
        self.rdoSortSpecies.setObjectName("rdoSortSpecies")
        self.sortButtonGroup.addButton(self.rdoSortSpecies, 0)

        self.rdoSortDate = QtWidgets.QRadioButton(self.frameLabels)
        self.rdoSortDate.setObjectName("rdoSortDate")
        self.sortButtonGroup.addButton(self.rdoSortDate, 1)

        self.rdoSortRating = QtWidgets.QRadioButton(self.frameLabels)
        self.rdoSortRating.setObjectName("rdoSortRating")
        self.sortButtonGroup.addButton(self.rdoSortRating, 2)

        self.rdoSortTaxonomy = QtWidgets.QRadioButton(self.frameLabels)
        self.rdoSortTaxonomy.setChecked(True)
        self.rdoSortTaxonomy.setObjectName("rdoSortTaxonomy")
        self.sortButtonGroup.addButton(self.rdoSortTaxonomy, 3)

        self.sortRow = QtWidgets.QHBoxLayout()
        self.sortRow.addWidget(self.lblSortBy)
        self.sortRow.addWidget(self.rdoSortSpecies)
        self.sortRow.addWidget(self.rdoSortDate)
        self.sortRow.addWidget(self.rdoSortRating)
        self.sortRow.addWidget(self.rdoSortTaxonomy)
        self.sortRow.addStretch()
        self.verticalLayoutLabels.addLayout(self.sortRow)

        self.horizontalLayoutHeader.addWidget(self.frameLabels, 1)

        # ── Right subframe: Slideshow button fills full header height ──────────
        self.frameButton = QtWidgets.QFrame(self.headerFrame)
        self.frameButton.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frameButton.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.frameButton.setLineWidth(0)
        self.frameButton.setObjectName("frameButton")
        self.verticalLayoutButton = QtWidgets.QVBoxLayout(self.frameButton)
        self.verticalLayoutButton.setContentsMargins(0, 0, 0, 0)
        self.verticalLayoutButton.setSpacing(0)
        self.verticalLayoutButton.setObjectName("verticalLayoutButton")

        self.buttonSlideshow = QtWidgets.QPushButton(self.frameButton)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                                           QtWidgets.QSizePolicy.Policy.Preferred)
        self.buttonSlideshow.setSizePolicy(sizePolicy)
        self.buttonSlideshow.setObjectName("buttonSlideshow")
        self.verticalLayoutButton.addWidget(self.buttonSlideshow)
        self.verticalLayoutButton.addStretch(1)

        self.horizontalLayoutHeader.addWidget(self.frameButton, 0)

        # ── Scroll area (photo grid only) ─────────────────────────────────────
        self.scrollArea = QtWidgets.QScrollArea(frmPhotos)
        self.scrollArea.setGeometry(QtCore.QRect(0, 130, 671, 350))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.scrollArea.sizePolicy().hasHeightForWidth())
        self.scrollArea.setSizePolicy(sizePolicy)
        self.scrollArea.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scrollArea.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.scrollArea.setLineWidth(0)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setAlignment(QtCore.Qt.AlignLeading|QtCore.Qt.AlignLeft|QtCore.Qt.AlignTop)
        self.scrollArea.setObjectName("scrollArea")

        self.layLists = QtWidgets.QWidget()
        self.layLists.setGeometry(QtCore.QRect(0, 0, 671, 350))
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
        self.gridPhotos.setObjectName("gridPhotos")
        self.verticalLayout_3.addLayout(self.gridPhotos)

        self.scrollArea.setWidget(self.layLists)

        self.actionSetDateFilter = QtGui.QAction(frmPhotos)
        self.actionSetDateFilter.setObjectName("actionSetDateFilter")
        self.actionSetLocationFilter = QtGui.QAction(frmPhotos)
        self.actionSetLocationFilter.setObjectName("actionSetLocationFilter")
        self.actionSetFirstDateFilter = QtGui.QAction(frmPhotos)
        self.actionSetFirstDateFilter.setObjectName("actionSetFirstDateFilter")
        self.actionSetLastDateFilter = QtGui.QAction(frmPhotos)
        self.actionSetLastDateFilter.setObjectName("actionSetLastDateFilter")
        self.actionSetSpeciesFilter = QtGui.QAction(frmPhotos)
        self.actionSetSpeciesFilter.setObjectName("actionSetSpeciesFilter")
        self.actionSetCountryFilter = QtGui.QAction(frmPhotos)
        self.actionSetCountryFilter.setObjectName("actionSetCountryFilter")
        self.actionSetStateFilter = QtGui.QAction(frmPhotos)
        self.actionSetStateFilter.setObjectName("actionSetStateFilter")
        self.actionSetCountyFilter = QtGui.QAction(frmPhotos)
        self.actionSetCountyFilter.setObjectName("actionSetCountyFilter")

        self.retranslateUi(frmPhotos)
        QtCore.QMetaObject.connectSlotsByName(frmPhotos)

    def retranslateUi(self, frmPhotos):
        _translate = QtCore.QCoreApplication.translate
        frmPhotos.setWindowTitle(_translate("frmPhotos", "Species Report"))
        self.lblLocation.setText(_translate("frmPhotos", "Location"))
        self.lblDateRange.setText(_translate("frmPhotos", "Date Range"))
        self.lblDetails.setText(_translate("frmPhotos", "Details Label"))
        self.lblSpecies.setText(_translate("frmPhotos", "Species"))
        self.actionSetDateFilter.setText(_translate("frmPhotos", "Set Filter to Date"))
        self.actionSetLocationFilter.setText(_translate("frmPhotos", "Set Filter to Location"))
        self.actionSetFirstDateFilter.setText(_translate("frmPhotos", "Set Filter to \"First\" Date"))
        self.actionSetLastDateFilter.setText(_translate("frmPhotos", "Set Filter to \"Last\" Date"))
        self.actionSetSpeciesFilter.setText(_translate("frmPhotos", "Set Filter to Species"))
        self.actionSetCountryFilter.setText(_translate("frmPhotos", "Set Filter to Country"))
        self.actionSetStateFilter.setText(_translate("frmPhotos", "Set Filter to State"))
        self.actionSetCountyFilter.setText(_translate("frmPhotos", "Set Filter to County"))
        self.lblSortBy.setText(_translate("frmPhotos", "Sort by:"))
        self.rdoSortSpecies.setText(_translate("frmPhotos", "Alphabetical"))
        self.rdoSortDate.setText(_translate("frmPhotos", "Date"))
        self.rdoSortRating.setText(_translate("frmPhotos", "Rating"))
        self.rdoSortTaxonomy.setText(_translate("frmPhotos", "Taxonomy"))
        self.buttonSlideshow.setText(_translate("frmPhotos", "Slideshow"))

import icons_rc

if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    frmPhotos = QtWidgets.QWidget()
    ui = Ui_frmPhotos()
    ui.setupUi(frmPhotos)
    frmPhotos.show()
    sys.exit(app.exec())
