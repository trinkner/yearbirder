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

        # Exposure-mode row: which setting the distribution shows (Exposure
        # Settings chart only)
        self.frmExposureMode = QtWidgets.QFrame(self.layGraphs)
        self.frmExposureMode.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frmExposureMode.setObjectName("frmExposureMode")
        self.hLayoutExposureMode = QtWidgets.QHBoxLayout(self.frmExposureMode)
        self.hLayoutExposureMode.setContentsMargins(0, 0, 0, 0)
        self.hLayoutExposureMode.setSpacing(16)
        self.hLayoutExposureMode.setObjectName("hLayoutExposureMode")

        self.rdoExpIso = QtWidgets.QRadioButton(self.frmExposureMode)
        self.rdoExpIso.setChecked(True)
        self.rdoExpIso.setObjectName("rdoExpIso")
        self.hLayoutExposureMode.addWidget(self.rdoExpIso)

        self.rdoExpAperture = QtWidgets.QRadioButton(self.frmExposureMode)
        self.rdoExpAperture.setObjectName("rdoExpAperture")
        self.hLayoutExposureMode.addWidget(self.rdoExpAperture)

        self.rdoExpShutter = QtWidgets.QRadioButton(self.frmExposureMode)
        self.rdoExpShutter.setObjectName("rdoExpShutter")
        self.hLayoutExposureMode.addWidget(self.rdoExpShutter)

        self.rdoExpFocal = QtWidgets.QRadioButton(self.frmExposureMode)
        self.rdoExpFocal.setObjectName("rdoExpFocal")
        self.hLayoutExposureMode.addWidget(self.rdoExpFocal)

        self.hLayoutExposureMode.addStretch(1)

        # What the bars measure, right-justified on the same row.
        self.rdoExpCount = QtWidgets.QRadioButton(self.frmExposureMode)
        self.rdoExpCount.setChecked(True)
        self.rdoExpCount.setObjectName("rdoExpCount")
        self.hLayoutExposureMode.addWidget(self.rdoExpCount)

        self.rdoExpRating = QtWidgets.QRadioButton(self.frmExposureMode)
        self.rdoExpRating.setObjectName("rdoExpRating")
        self.hLayoutExposureMode.addWidget(self.rdoExpRating)

        # Two independent choices on one row: radio buttons sharing a parent
        # are auto-exclusive, so without a group of its own, picking Average
        # Rating would clear whichever setting was selected to its left.
        self.grpExposureField = QtWidgets.QButtonGroup(self.frmExposureMode)
        for _b in (self.rdoExpIso, self.rdoExpAperture,
                   self.rdoExpShutter, self.rdoExpFocal):
            self.grpExposureField.addButton(_b)
        self.grpExposureMetric = QtWidgets.QButtonGroup(self.frmExposureMode)
        for _b in (self.rdoExpCount, self.rdoExpRating):
            self.grpExposureMetric.addButton(_b)

        self.frmExposureMode.setVisible(False)
        self.verticalLayout.addWidget(self.frmExposureMode)

        # Compare Settings: one variable per axis, a row each so it is always
        # clear which choice goes where.
        self.frmCompareMode = QtWidgets.QFrame(self.layGraphs)
        self.frmCompareMode.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frmCompareMode.setObjectName("frmCompareMode")
        self.vLayoutCompareMode = QtWidgets.QVBoxLayout(self.frmCompareMode)
        self.vLayoutCompareMode.setContentsMargins(0, 0, 0, 0)
        self.vLayoutCompareMode.setSpacing(2)
        self.vLayoutCompareMode.setObjectName("vLayoutCompareMode")

        self.lblCompareX = QtWidgets.QLabel(self.frmCompareMode)
        self.lblCompareX.setObjectName("lblCompareX")
        self.lblCompareY = QtWidgets.QLabel(self.frmCompareMode)
        self.lblCompareY.setObjectName("lblCompareY")

        self.grpCompareX = QtWidgets.QButtonGroup(self.frmCompareMode)
        self.grpCompareY = QtWidgets.QButtonGroup(self.frmCompareMode)
        self.rdoCmpX = {}
        self.rdoCmpY = {}

        for axis, label, group, store in (
                ("X", self.lblCompareX, self.grpCompareX, self.rdoCmpX),
                ("Y", self.lblCompareY, self.grpCompareY, self.rdoCmpY)):
            row = QtWidgets.QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(16)
            label.setMinimumWidth(80)
            row.addWidget(label)
            for field in ("iso", "aperture", "shutter", "focal"):
                rdo = QtWidgets.QRadioButton(self.frmCompareMode)
                rdo.setObjectName(f"rdoCmp{axis}{field.capitalize()}")
                group.addButton(rdo)
                store[field] = rdo
                row.addWidget(rdo)
            row.addStretch(1)
            self.vLayoutCompareMode.addLayout(row)

        self.frmCompareMode.setVisible(False)
        self.verticalLayout.addWidget(self.frmCompareMode)

        # Time-of-day row: what the bars measure (that chart's x-axis is the
        # hour, so there is no variable to choose on the left).
        self.frmHourMode = QtWidgets.QFrame(self.layGraphs)
        self.frmHourMode.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frmHourMode.setObjectName("frmHourMode")
        self.hLayoutHourMode = QtWidgets.QHBoxLayout(self.frmHourMode)
        self.hLayoutHourMode.setContentsMargins(0, 0, 0, 0)
        self.hLayoutHourMode.setSpacing(16)
        self.hLayoutHourMode.setObjectName("hLayoutHourMode")

        self.rdoHourCount = QtWidgets.QRadioButton(self.frmHourMode)
        self.rdoHourCount.setChecked(True)
        self.rdoHourCount.setObjectName("rdoHourCount")
        self.hLayoutHourMode.addWidget(self.rdoHourCount)

        self.rdoHourRating = QtWidgets.QRadioButton(self.frmHourMode)
        self.rdoHourRating.setObjectName("rdoHourRating")
        self.hLayoutHourMode.addWidget(self.rdoHourRating)

        self.grpHourMetric = QtWidgets.QButtonGroup(self.frmHourMode)
        for _b in (self.rdoHourCount, self.rdoHourRating):
            self.grpHourMetric.addButton(_b)

        self.hLayoutHourMode.addStretch(1)

        self.frmHourMode.setVisible(False)
        self.verticalLayout.addWidget(self.frmHourMode)

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
        self.rdoExpIso.setText(_translate("frmGraphs", "ISO"))
        self.rdoExpAperture.setText(_translate("frmGraphs", "Aperture"))
        self.rdoExpShutter.setText(_translate("frmGraphs", "Shutter Speed"))
        self.rdoExpFocal.setText(_translate("frmGraphs", "Focal Length"))
        self.rdoExpCount.setText(_translate("frmGraphs", "Photographs"))
        self.rdoExpRating.setText(_translate("frmGraphs", "Average Rating"))
        self.rdoHourCount.setText(_translate("frmGraphs", "Photographs"))
        self.rdoHourRating.setText(_translate("frmGraphs", "Average Rating"))
        self.lblCompareX.setText(_translate("frmGraphs", "Horizontal:"))
        self.lblCompareY.setText(_translate("frmGraphs", "Vertical:"))
        for _store in (self.rdoCmpX, self.rdoCmpY):
            _store["iso"].setText(_translate("frmGraphs", "ISO"))
            _store["aperture"].setText(_translate("frmGraphs", "Aperture"))
            _store["shutter"].setText(_translate("frmGraphs", "Shutter Speed"))
            _store["focal"].setText(_translate("frmGraphs", "Focal Length"))


import icons_rc
