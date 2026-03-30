# -*- coding: utf-8 -*-

from PySide6 import QtCore, QtGui, QtWidgets


class Ui_frmGraphs(object):
    def setupUi(self, frmGraphs):
        frmGraphs.setObjectName("frmGraphs")
        frmGraphs.resize(700, 520)
        frmGraphs.setMinimumSize(QtCore.QSize(300, 250))

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icon_bird_white.png"),
                       QtGui.QIcon.Normal, QtGui.QIcon.Off)
        frmGraphs.setWindowIcon(icon)

        # Scroll area sits directly on the form (same pattern as form_Lists.py)
        self.scrollArea = QtWidgets.QScrollArea(frmGraphs)
        self.scrollArea.setGeometry(QtCore.QRect(0, 23, 695, 497))
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding)
        self.scrollArea.setSizePolicy(sizePolicy)
        self.scrollArea.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scrollArea.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.scrollArea.setLineWidth(0)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setObjectName("scrollArea")

        # Inner widget with a vertical layout
        self.layGraphs = QtWidgets.QWidget()
        sizePolicy2 = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding)
        self.layGraphs.setSizePolicy(sizePolicy2)
        self.layGraphs.setObjectName("layGraphs")

        self.verticalLayout = QtWidgets.QVBoxLayout(self.layGraphs)
        self.verticalLayout.setContentsMargins(5, 5, 5, 5)
        self.verticalLayout.setSpacing(4)
        self.verticalLayout.setObjectName("verticalLayout")

        # Location label — large, bold
        self.lblLocation = QtWidgets.QLabel(self.layGraphs)
        font = QtGui.QFont()
        font.setPointSize(14)
        font.setBold(True)
        font.setWeight(QtGui.QFont.Weight.Bold)
        self.lblLocation.setFont(font)
        self.lblLocation.setWordWrap(True)
        self.lblLocation.setObjectName("lblLocation")
        self.verticalLayout.addWidget(self.lblLocation)

        # Date range label
        self.lblDateRange = QtWidgets.QLabel(self.layGraphs)
        font2 = QtGui.QFont()
        font2.setPointSize(12)
        self.lblDateRange.setFont(font2)
        self.lblDateRange.setObjectName("lblDateRange")
        self.verticalLayout.addWidget(self.lblDateRange)

        # Details label (taxonomy / misc filter info)
        self.lblDetails = QtWidgets.QLabel(self.layGraphs)
        font3 = QtGui.QFont()
        font3.setPointSize(12)
        self.lblDetails.setFont(font3)
        self.lblDetails.setObjectName("lblDetails")
        self.verticalLayout.addWidget(self.lblDetails)

        # Granularity row: radio buttons + warning label
        self.frmGranularity = QtWidgets.QFrame(self.layGraphs)
        self.frmGranularity.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frmGranularity.setObjectName("frmGranularity")
        self.hLayoutGranularity = QtWidgets.QHBoxLayout(self.frmGranularity)
        self.hLayoutGranularity.setContentsMargins(0, 0, 0, 0)
        self.hLayoutGranularity.setSpacing(16)
        self.hLayoutGranularity.setObjectName("hLayoutGranularity")

        self.rdoYear = QtWidgets.QRadioButton(self.frmGranularity)
        self.rdoYear.setChecked(True)
        self.rdoYear.setObjectName("rdoYear")
        self.hLayoutGranularity.addWidget(self.rdoYear)

        self.rdoMonth = QtWidgets.QRadioButton(self.frmGranularity)
        self.rdoMonth.setObjectName("rdoMonth")
        self.hLayoutGranularity.addWidget(self.rdoMonth)

        self.rdoMonthYear = QtWidgets.QRadioButton(self.frmGranularity)
        self.rdoMonthYear.setObjectName("rdoMonthYear")
        self.hLayoutGranularity.addWidget(self.rdoMonthYear)

        self.rdoDay = QtWidgets.QRadioButton(self.frmGranularity)
        self.rdoDay.setObjectName("rdoDay")
        self.hLayoutGranularity.addWidget(self.rdoDay)

        self.lblWarning = QtWidgets.QLabel(self.frmGranularity)
        self.lblWarning.setObjectName("lblWarning")
        self.lblWarning.setVisible(False)
        self.hLayoutGranularity.addWidget(self.lblWarning)

        # Push everything to the left
        self.hLayoutGranularity.addStretch(1)

        self.verticalLayout.addWidget(self.frmGranularity)

        # Pie-mode row: Families / Orders toggle (shown only for pie chart)
        self.frmPieMode = QtWidgets.QFrame(self.layGraphs)
        self.frmPieMode.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frmPieMode.setObjectName("frmPieMode")
        self.hLayoutPieMode = QtWidgets.QHBoxLayout(self.frmPieMode)
        self.hLayoutPieMode.setContentsMargins(0, 0, 0, 0)
        self.hLayoutPieMode.setSpacing(16)
        self.hLayoutPieMode.setObjectName("hLayoutPieMode")

        self.rdoPieFamily = QtWidgets.QRadioButton(self.frmPieMode)
        self.rdoPieFamily.setChecked(True)
        self.rdoPieFamily.setObjectName("rdoPieFamily")
        self.hLayoutPieMode.addWidget(self.rdoPieFamily)

        self.rdoPieOrder = QtWidgets.QRadioButton(self.frmPieMode)
        self.rdoPieOrder.setObjectName("rdoPieOrder")
        self.hLayoutPieMode.addWidget(self.rdoPieOrder)

        self.hLayoutPieMode.addStretch(1)

        self.frmPieMode.setVisible(False)
        self.verticalLayout.addWidget(self.frmPieMode)

        # Chart widget — expands to fill all remaining vertical space
        self.chartWidget = QtWidgets.QWidget(self.layGraphs)
        sizePolicy3 = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding)
        self.chartWidget.setSizePolicy(sizePolicy3)
        self.chartWidget.setObjectName("chartWidget")
        self.verticalLayout.addWidget(self.chartWidget, stretch=1)

        self.scrollArea.setWidget(self.layGraphs)

        self.retranslateUi(frmGraphs)
        QtCore.QMetaObject.connectSlotsByName(frmGraphs)

    def retranslateUi(self, frmGraphs):
        _translate = QtCore.QCoreApplication.translate
        frmGraphs.setWindowTitle(_translate("frmGraphs", "Bar Graph"))
        self.lblLocation.setText(_translate("frmGraphs", "Location"))
        self.lblDateRange.setText(_translate("frmGraphs", "Date Range"))
        self.lblDetails.setText(_translate("frmGraphs", ""))
        self.rdoYear.setText(_translate("frmGraphs", "By Year"))
        self.rdoMonth.setText(_translate("frmGraphs", "By Month"))
        self.rdoMonthYear.setText(_translate("frmGraphs", "By Month-Year"))
        self.rdoDay.setText(_translate("frmGraphs", "By Day"))
        self.lblWarning.setText(_translate("frmGraphs",
            "⚠  Too many days to display clearly — narrow the date filter."))
        self.rdoPieFamily.setText(_translate("frmGraphs", "Families"))
        self.rdoPieOrder.setText(_translate("frmGraphs", "Orders"))


import icons_rc
