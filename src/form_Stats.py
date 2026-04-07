# -*- coding: utf-8 -*-
from PySide6 import QtCore, QtGui, QtWidgets


class Ui_frmStats(object):
    def setupUi(self, frmStats):
        frmStats.setObjectName("frmStats")
        frmStats.resize(960, 640)
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(frmStats.sizePolicy().hasHeightForWidth())
        frmStats.setSizePolicy(sizePolicy)
        frmStats.setMinimumSize(QtCore.QSize(400, 300))
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icon_datetotals.png"),
                       QtGui.QIcon.Normal, QtGui.QIcon.Off)
        frmStats.setWindowIcon(icon)
        self.scrollArea = QtWidgets.QScrollArea(frmStats)
        self.scrollArea.setGeometry(QtCore.QRect(0, 23, 956, 607))
        self.scrollArea.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scrollArea.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.scrollArea.setLineWidth(0)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setObjectName("scrollArea")
        self.retranslateUi(frmStats)
        QtCore.QMetaObject.connectSlotsByName(frmStats)

    def retranslateUi(self, frmStats):
        _translate = QtCore.QCoreApplication.translate
        frmStats.setWindowTitle(_translate("frmStats", "Statistics"))


import icons_rc
