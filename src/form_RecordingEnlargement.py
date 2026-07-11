# -*- coding: utf-8 -*-

from PySide6 import QtCore, QtGui, QtWidgets


class Ui_frmRecordingEnlargement(object):
    def setupUi(self, frmRecordingEnlargement):
        frmRecordingEnlargement.setObjectName("frmRecordingEnlargement")
        # Base (spectrogram-viewing-area) width is 910 * 1.2 * 0.75 * 0.9 = 737; the
        # details pane (297px, shown by default) is added on top, giving 1034 total.
        frmRecordingEnlargement.resize(1034, 600)
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
