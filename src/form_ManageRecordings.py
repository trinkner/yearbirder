# -*- coding: utf-8 -*-
from PySide6 import QtCore, QtGui, QtWidgets


class Ui_frmManageRecordings(object):
    def setupUi(self, frmManageRecordings):
        frmManageRecordings.setObjectName("frmManageRecordings")
        frmManageRecordings.resize(897, 680)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(frmManageRecordings.sizePolicy().hasHeightForWidth())
        frmManageRecordings.setSizePolicy(sizePolicy)
        frmManageRecordings.setMinimumSize(QtCore.QSize(200, 300))
        frmManageRecordings.setSizeIncrement(QtCore.QSize(0, 0))
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icon_bird_white.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        frmManageRecordings.setWindowIcon(icon)
        # ── Bulk gear banner ─────────────────────────────────────────────────
        # Sits above the card list; assigns one rig to every loaded card at
        # once, which is the usual case since a batch is normally one outing
        # with one rig.  Hidden entirely when no rigs are defined.
        self.frmGearBanner = QtWidgets.QFrame(frmManageRecordings)
        self.frmGearBanner.setObjectName("frmGearBanner")
        self.frmGearBanner.setGeometry(QtCore.QRect(5, 27, 891, 40))
        # Pinned so resizeMe's height arithmetic can't drift with the layout's
        # size hint (_GEAR_BANNER_H in code_ManageRecordings must match).
        self.frmGearBanner.setFixedHeight(40)
        _bannerLayout = QtWidgets.QHBoxLayout(self.frmGearBanner)
        # 13 = layLists' 5px inset + gridAudio's 8px, so the banner's contents
        # line up with the card edges.  resizeMe widens the right margin further
        # when a vertical scrollbar is showing (see _alignBannerToCards).
        _bannerLayout.setContentsMargins(13, 4, 13, 4)
        _bannerLayout.setSpacing(8)
        # Layout: [balance spacer] [stretch] label combo Apply [stretch] [toggle]
        #
        # The toggle sits hard right, level with the cards' right edge (both
        # inset 8px).  The spacer mirrors its width on the left so the two ends
        # weigh the same and the middle group centres on the STRIP, not on the
        # space left over beside the button.  _applyBatchOptionsState keeps the
        # spacer in step, since the button's width changes with its caption.
        self.spcGearBannerBalance = QtWidgets.QSpacerItem(
            0, 0, QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Minimum)
        _bannerLayout.addItem(self.spcGearBannerBalance)
        _bannerLayout.addStretch(1)
        self.lblGearBanner = QtWidgets.QLabel(self.frmGearBanner)
        self.lblGearBanner.setObjectName("lblGearBanner")
        _bannerLayout.addWidget(self.lblGearBanner)
        self.cboGearBannerRig = QtWidgets.QComboBox(self.frmGearBanner)
        self.cboGearBannerRig.setObjectName("cboGearBannerRig")
        self.cboGearBannerRig.setMinimumWidth(200)
        _bannerLayout.addWidget(self.cboGearBannerRig)
        self.btnApplyGearBanner = QtWidgets.QPushButton(self.frmGearBanner)
        self.btnApplyGearBanner.setObjectName("btnApplyGearBanner")
        _bannerLayout.addWidget(self.btnApplyGearBanner)
        _bannerLayout.addStretch(1)
        # Hard right: collapsed, this button is the whole banner.  The strip
        # keeps its height either way, so toggling never reflows the cards.
        self.btnToggleBatch = QtWidgets.QPushButton(self.frmGearBanner)
        self.btnToggleBatch.setObjectName("btnToggleBatch")
        _bannerLayout.addWidget(self.btnToggleBatch)

        self.scrollArea = QtWidgets.QScrollArea(frmManageRecordings)
        self.scrollArea.setGeometry(QtCore.QRect(0, 10, 891, 601))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.scrollArea.sizePolicy().hasHeightForWidth())
        self.scrollArea.setSizePolicy(sizePolicy)
        self.scrollArea.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scrollArea.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        self.scrollArea.setLineWidth(0)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setObjectName("scrollArea")
        self.layLists = QtWidgets.QWidget()
        self.layLists.setGeometry(QtCore.QRect(0, 0, 891, 601))
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
        self.gridAudio = QtWidgets.QGridLayout()
        self.gridAudio.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        self.gridAudio.setObjectName("gridAudio")
        self.verticalLayout_3.addLayout(self.gridAudio)
        self.scrollArea.setWidget(self.layLists)
        self.btnSaveAudioSettings = QtWidgets.QPushButton(frmManageRecordings)
        self.btnSaveAudioSettings.setGeometry(QtCore.QRect(700, 630, 181, 28))
        self.btnSaveAudioSettings.setObjectName("btnSaveAudioSettings")
        self.btnCancel = QtWidgets.QPushButton(frmManageRecordings)
        self.btnCancel.setGeometry(QtCore.QRect(510, 630, 181, 28))
        self.btnCancel.setObjectName("btnCancel")

        self.retranslateUi(frmManageRecordings)
        QtCore.QMetaObject.connectSlotsByName(frmManageRecordings)

    def retranslateUi(self, frmManageRecordings):
        _translate = QtCore.QCoreApplication.translate
        frmManageRecordings.setWindowTitle(_translate("frmManageRecordings", "Add Recordings"))
        self.btnSaveAudioSettings.setText(_translate("frmManageRecordings", "Save"))
        self.btnCancel.setText(_translate("frmManageRecordings", "Cancel"))
        self.lblGearBanner.setText(_translate("frmManageRecordings", "Set gear for all:"))
        self.btnToggleBatch.setText(_translate("frmManageRecordings", "Show batch options"))
        self.btnApplyGearBanner.setToolTip(_translate("frmManageRecordings", "Assign the chosen rig's recorder and microphone to every card below. Yearbirder never writes to your audio files — only to its own catalog — and \"Use each file's original metadata\" puts them back."))
        self.btnApplyGearBanner.setText(_translate("frmManageRecordings", "Apply"))
        self.cboGearBannerRig.setToolTip(_translate("frmManageRecordings", "Rigs are defined in Preferences → Recording Gear."))


import icons_rc

if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    frmManageRecordings = QtWidgets.QWidget()
    ui = Ui_frmManageRecordings()
    ui.setupUi(frmManageRecordings)
    frmManageRecordings.show()
    sys.exit(app.exec())
