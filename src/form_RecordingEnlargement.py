# -*- coding: utf-8 -*-

from PySide6 import QtCore, QtGui, QtWidgets


class Ui_frmRecordingEnlargement(object):
    def setupUi(self, frmRecordingEnlargement):
        frmRecordingEnlargement.setObjectName("frmRecordingEnlargement")
        frmRecordingEnlargement.resize(900, 600)
        frmRecordingEnlargement.setMinimumSize(QtCore.QSize(500, 350))
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icon_bird_white.png"),
                       QtGui.QIcon.Normal, QtGui.QIcon.Off)
        frmRecordingEnlargement.setWindowIcon(icon)
        self.retranslateUi(frmRecordingEnlargement)

    def retranslateUi(self, frmRecordingEnlargement):
        frmRecordingEnlargement.setWindowTitle(
            QtCore.QCoreApplication.translate("frmRecordingEnlargement", "Recordings"))


import icons_rc

if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = QtWidgets.QWidget()
    ui = Ui_frmRecordingEnlargement()
    ui.setupUi(w)
    w.show()
    sys.exit(app.exec())
