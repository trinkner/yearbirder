# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'form_Enlargement.ui'
#
# Created by: PyQt5 UI code generator 5.11.2
#
# WARNING! All changes made in this file will be lost!

from PySide6 import QtCore, QtGui, QtWidgets

class Ui_frmEnlargement(object):
    def setupUi(self, frmEnlargement):
        frmEnlargement.setObjectName("frmEnlargement")
        frmEnlargement.resize(671, 505)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(frmEnlargement.sizePolicy().hasHeightForWidth())
        frmEnlargement.setSizePolicy(sizePolicy)
        frmEnlargement.setMinimumSize(QtCore.QSize(200, 300))
        frmEnlargement.setSizeIncrement(QtCore.QSize(0, 0))
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icon_camera.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        frmEnlargement.setWindowIcon(icon)

        self.retranslateUi(frmEnlargement)
        QtCore.QMetaObject.connectSlotsByName(frmEnlargement)

    def retranslateUi(self, frmEnlargement):
        _translate = QtCore.QCoreApplication.translate
        frmEnlargement.setWindowTitle(_translate("frmEnlargement", "Enlargement"))

import icons_rc

if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    frmEnlargement = QtWidgets.QWidget()
    ui = Ui_frmEnlargement()
    ui.setupUi(frmEnlargement)
    frmEnlargement.show()
    sys.exit(app.exec())

