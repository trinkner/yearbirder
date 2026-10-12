# -*- coding: utf-8 -*-
from PySide6 import QtCore, QtGui, QtWidgets


class Ui_frmPhotoStats(object):
    def setupUi(self, frmPhotoStats):
        frmPhotoStats.setObjectName("frmPhotoStats")
        frmPhotoStats.resize(900, 640)
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(frmPhotoStats.sizePolicy().hasHeightForWidth())
        frmPhotoStats.setSizePolicy(sizePolicy)
        frmPhotoStats.setMinimumSize(QtCore.QSize(400, 300))
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icon_camera.png"),
                       QtGui.QIcon.Normal, QtGui.QIcon.Off)
        frmPhotoStats.setWindowIcon(icon)
        self.retranslateUi(frmPhotoStats)
        QtCore.QMetaObject.connectSlotsByName(frmPhotoStats)

    def retranslateUi(self, frmPhotoStats):
        _translate = QtCore.QCoreApplication.translate
        frmPhotoStats.setWindowTitle(_translate("frmPhotoStats", "Photo Statistics"))


import icons_rc
