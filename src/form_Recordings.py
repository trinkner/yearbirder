# -*- coding: utf-8 -*-

from PySide6 import QtCore, QtGui, QtWidgets


class Ui_frmRecordings(object):
    def setupUi(self, frmRecordings):
        frmRecordings.setObjectName("frmRecordings")
        frmRecordings.resize(671, 505)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                                           QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(frmRecordings.sizePolicy().hasHeightForWidth())
        frmRecordings.setSizePolicy(sizePolicy)
        frmRecordings.setMinimumSize(QtCore.QSize(200, 300))
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icon_bird_white.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        frmRecordings.setWindowIcon(icon)

        # ── Fixed header (never scrolls) ──────────────────────────────────────
        self.headerFrame = QtWidgets.QFrame(frmRecordings)
        self.headerFrame.setGeometry(QtCore.QRect(0, 0, 671, 110))
        self.headerFrame.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.headerFrame.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.headerFrame.setLineWidth(0)
        self.headerFrame.setObjectName("headerFrame")

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
        font.setPointSize(11)
        font.setBold(True)
        font.setWeight(QtGui.QFont.Weight.Bold)
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

        # ── Scroll area (audio grid only) ─────────────────────────────────────
        self.scrollArea = QtWidgets.QScrollArea(frmRecordings)
        self.scrollArea.setGeometry(QtCore.QRect(0, 110, 671, 370))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                           QtWidgets.QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.scrollArea.sizePolicy().hasHeightForWidth())
        self.scrollArea.setSizePolicy(sizePolicy)
        self.scrollArea.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scrollArea.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.scrollArea.setLineWidth(0)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setAlignment(QtCore.Qt.AlignLeading | QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.scrollArea.setObjectName("scrollArea")

        self.layLists = QtWidgets.QWidget()
        self.layLists.setGeometry(QtCore.QRect(0, 0, 671, 370))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                           QtWidgets.QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.layLists.sizePolicy().hasHeightForWidth())
        self.layLists.setSizePolicy(sizePolicy)
        self.layLists.setObjectName("layLists")

        self.verticalLayout_3 = QtWidgets.QVBoxLayout(self.layLists)
        self.verticalLayout_3.setContentsMargins(5, 5, 5, 5)
        self.verticalLayout_3.setSpacing(4)
        self.verticalLayout_3.setObjectName("verticalLayout_3")

        self.gridAudio = QtWidgets.QGridLayout()
        self.gridAudio.setObjectName("gridAudio")
        self.verticalLayout_3.addLayout(self.gridAudio)

        self.scrollArea.setWidget(self.layLists)

        # Context menu actions
        self.actionSetDateFilter = QtGui.QAction(frmRecordings)
        self.actionSetDateFilter.setObjectName("actionSetDateFilter")
        self.actionSetLocationFilter = QtGui.QAction(frmRecordings)
        self.actionSetLocationFilter.setObjectName("actionSetLocationFilter")
        self.actionSetFirstDateFilter = QtGui.QAction(frmRecordings)
        self.actionSetFirstDateFilter.setObjectName("actionSetFirstDateFilter")
        self.actionSetLastDateFilter = QtGui.QAction(frmRecordings)
        self.actionSetLastDateFilter.setObjectName("actionSetLastDateFilter")
        self.actionSetSpeciesFilter = QtGui.QAction(frmRecordings)
        self.actionSetSpeciesFilter.setObjectName("actionSetSpeciesFilter")
        self.actionSetCountryFilter = QtGui.QAction(frmRecordings)
        self.actionSetCountryFilter.setObjectName("actionSetCountryFilter")
        self.actionSetStateFilter = QtGui.QAction(frmRecordings)
        self.actionSetStateFilter.setObjectName("actionSetStateFilter")
        self.actionSetCountyFilter = QtGui.QAction(frmRecordings)
        self.actionSetCountyFilter.setObjectName("actionSetCountyFilter")

        self.retranslateUi(frmRecordings)
        QtCore.QMetaObject.connectSlotsByName(frmRecordings)

    def retranslateUi(self, frmRecordings):
        _translate = QtCore.QCoreApplication.translate
        frmRecordings.setWindowTitle(_translate("frmRecordings", "Recordings"))
        self.lblLocation.setText(_translate("frmRecordings", "Location"))
        self.lblDateRange.setText(_translate("frmRecordings", "Date Range"))
        self.lblDetails.setText(_translate("frmRecordings", "Details Label"))
        self.lblSpecies.setText(_translate("frmRecordings", "Species"))
        self.actionSetDateFilter.setText(_translate("frmRecordings", "Set Filter to Date"))
        self.actionSetLocationFilter.setText(_translate("frmRecordings", "Set Filter to Location"))
        self.actionSetFirstDateFilter.setText(_translate("frmRecordings", "Set Filter to \"First\" Date"))
        self.actionSetLastDateFilter.setText(_translate("frmRecordings", "Set Filter to \"Last\" Date"))
        self.actionSetSpeciesFilter.setText(_translate("frmRecordings", "Set Filter to Species"))
        self.actionSetCountryFilter.setText(_translate("frmRecordings", "Set Filter to Country"))
        self.actionSetStateFilter.setText(_translate("frmRecordings", "Set Filter to State"))
        self.actionSetCountyFilter.setText(_translate("frmRecordings", "Set Filter to County"))
        self.lblSortBy.setText(_translate("frmRecordings", "Sort by:"))
        self.rdoSortSpecies.setText(_translate("frmRecordings", "Alphabetical"))
        self.rdoSortDate.setText(_translate("frmRecordings", "Date"))
        self.rdoSortRating.setText(_translate("frmRecordings", "Rating"))
        self.rdoSortTaxonomy.setText(_translate("frmRecordings", "Taxonomy"))


import icons_rc

if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    frmRecordings = QtWidgets.QWidget()
    ui = Ui_frmRecordings()
    ui.setupUi(frmRecordings)
    frmRecordings.show()
    sys.exit(app.exec())
