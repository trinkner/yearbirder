# -*- coding: utf-8 -*-

from PySide6 import QtCore, QtGui, QtWidgets


class Ui_frmRenameMedia(object):

    def setupUi(self, frmRenameMedia):
        frmRenameMedia.setObjectName("frmRenameMedia")
        frmRenameMedia.resize(960, 720)
        frmRenameMedia.setMinimumSize(QtCore.QSize(600, 400))
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icon_bird_white.png"),
                       QtGui.QIcon.Normal, QtGui.QIcon.Off)
        frmRenameMedia.setWindowIcon(icon)

        # ── Outer container ───────────────────────────────────────────────────
        self.frmContainer = QtWidgets.QWidget(frmRenameMedia)
        self.frmContainer.setObjectName("frmContainer")
        self.mainLayout = QtWidgets.QVBoxLayout(self.frmContainer)
        self.mainLayout.setContentsMargins(8, 8, 8, 8)
        # Spacing is 0; each inter-section gap is set explicitly with addSpacing()
        # so it is an exact pixel value (a non-zero base spacing would otherwise
        # be added on both sides of every inserted spacer).
        self.mainLayout.setSpacing(0)

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 1 — Name Format
        # ══════════════════════════════════════════════════════════════════════
        self.frmFormat = QtWidgets.QFrame(self.frmContainer)
        self.frmFormat.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frmFormat.setObjectName("frmFormat")
        self.frmFormatLayout = QtWidgets.QVBoxLayout(self.frmFormat)
        self.frmFormatLayout.setContentsMargins(0, 0, 0, 0)
        self.frmFormatLayout.setSpacing(0)   # gaps set explicitly via addSpacing()

        # Section title
        self.lblFormatTitle = QtWidgets.QLabel(self.frmFormat)
        self.lblFormatTitle.setObjectName("lblFormatTitle")
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(QtGui.QFont.Weight.Bold)
        self.lblFormatTitle.setFont(font)
        self.frmFormatLayout.addWidget(self.lblFormatTitle)
        self.frmFormatLayout.addSpacing(5)

        # Slot row
        self.frmSlots = QtWidgets.QFrame(self.frmFormat)
        self.frmSlots.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frmSlots.setObjectName("frmSlots")
        self.slotsLayout = QtWidgets.QHBoxLayout(self.frmSlots)
        self.slotsLayout.setContentsMargins(0, 0, 0, 0)
        self.slotsLayout.setSpacing(8)

        for n in range(1, 5):
            # Each slot is a vertical column: label on top, combo below.
            slotCol = QtWidgets.QVBoxLayout()
            slotCol.setContentsMargins(0, 0, 0, 0)
            slotCol.setSpacing(5)
            lbl = QtWidgets.QLabel(self.frmSlots)
            lbl.setObjectName(f"lblSlot{n}")
            slotCol.addWidget(lbl)
            cbo = QtWidgets.QComboBox(self.frmSlots)
            cbo.setObjectName(f"cboSlot{n}")
            cbo.setMinimumWidth(180)   # holds full "Category: Format" strings
            slotCol.addWidget(cbo)
            self.slotsLayout.addLayout(slotCol)
            setattr(self, f"lblSlot{n}", lbl)
            setattr(self, f"cboSlot{n}", cbo)

        self.slotsLayout.addStretch()
        self.frmFormatLayout.addWidget(self.frmSlots)
        self.frmFormatLayout.addSpacing(15)   # combos → Sample

        # Sample filename label
        self.lblSample = QtWidgets.QLabel(self.frmFormat)
        self.lblSample.setObjectName("lblSample")
        self.frmFormatLayout.addWidget(self.lblSample)

        self.mainLayout.addWidget(self.frmFormat)
        self.mainLayout.addSpacing(15)   # Sample → Options

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 2 — Options
        # ══════════════════════════════════════════════════════════════════════
        self.frmOptions = QtWidgets.QFrame(self.frmContainer)
        self.frmOptions.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frmOptions.setObjectName("frmOptions")
        self.frmOptionsLayout = QtWidgets.QVBoxLayout(self.frmOptions)
        self.frmOptionsLayout.setContentsMargins(0, 0, 0, 0)
        self.frmOptionsLayout.setSpacing(4)

        # Section title
        self.lblOptionsTitle = QtWidgets.QLabel(self.frmOptions)
        self.lblOptionsTitle.setObjectName("lblOptionsTitle")
        self.lblOptionsTitle.setFont(font)
        self.frmOptionsLayout.addWidget(self.lblOptionsTitle)

        # Remove spaces checkbox
        self.chkRemoveSpaces = QtWidgets.QCheckBox(self.frmOptions)
        self.chkRemoveSpaces.setObjectName("chkRemoveSpaces")
        self.chkRemoveSpaces.setChecked(True)
        self.frmOptionsLayout.addWidget(self.chkRemoveSpaces)

        # Shorten location names checkbox
        self.chkShortenLocation = QtWidgets.QCheckBox(self.frmOptions)
        self.chkShortenLocation.setObjectName("chkShortenLocation")
        self.frmOptionsLayout.addWidget(self.chkShortenLocation)

        self.mainLayout.addWidget(self.frmOptions)
        self.mainLayout.addSpacing(15)   # Options → table

        # ══════════════════════════════════════════════════════════════════════
        # TABLE
        # ══════════════════════════════════════════════════════════════════════
        self.tblPhotos = QtWidgets.QTableWidget(self.frmContainer)
        self.tblPhotos.setObjectName("tblPhotos")
        self.tblPhotos.setColumnCount(4)
        self.tblPhotos.setRowCount(0)
        self.tblPhotos.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tblPhotos.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.tblPhotos.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tblPhotos.horizontalHeader().setVisible(True)
        self.tblPhotos.horizontalHeader().setHighlightSections(False)
        self.tblPhotos.horizontalHeader().setStretchLastSection(False)
        self.tblPhotos.verticalHeader().setVisible(False)
        self.tblPhotos.setSortingEnabled(True)

        # Column widths: checkbox | current name | proposed name | status
        # Cols 1-3 use Interactive so resizeColumnToContents() can size them
        # to actual content after the table is populated.
        self.tblPhotos.setColumnWidth(0, 30)
        self.tblPhotos.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.tblPhotos.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.tblPhotos.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.tblPhotos.horizontalHeader().setSectionResizeMode(
            3, QtWidgets.QHeaderView.ResizeMode.Interactive)

        self.mainLayout.addWidget(self.tblPhotos, stretch=1)
        self.mainLayout.addSpacing(15)   # table → buttons

        # ══════════════════════════════════════════════════════════════════════
        # FOOTER
        # ══════════════════════════════════════════════════════════════════════
        self.frmFooter = QtWidgets.QFrame(self.frmContainer)
        self.frmFooter.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frmFooter.setObjectName("frmFooter")
        self.footerLayout = QtWidgets.QHBoxLayout(self.frmFooter)
        self.footerLayout.setContentsMargins(0, 0, 0, 0)
        self.footerLayout.setSpacing(8)

        self.btnSelectAll = QtWidgets.QPushButton(self.frmFooter)
        self.btnSelectAll.setObjectName("btnSelectAll")
        self.footerLayout.addWidget(self.btnSelectAll)

        self.btnSelectNone = QtWidgets.QPushButton(self.frmFooter)
        self.btnSelectNone.setObjectName("btnSelectNone")
        self.footerLayout.addWidget(self.btnSelectNone)

        self.btnSelectWav = QtWidgets.QPushButton(self.frmFooter)
        self.btnSelectWav.setObjectName("btnSelectWav")
        self.footerLayout.addWidget(self.btnSelectWav)

        self.btnSelectJpg = QtWidgets.QPushButton(self.frmFooter)
        self.btnSelectJpg.setObjectName("btnSelectJpg")
        self.footerLayout.addWidget(self.btnSelectJpg)

        self.lblCount = QtWidgets.QLabel(self.frmFooter)
        self.lblCount.setObjectName("lblCount")
        self.footerLayout.addWidget(self.lblCount)

        self.footerLayout.addStretch()

        self.btnRename = QtWidgets.QPushButton(self.frmFooter)
        self.btnRename.setObjectName("btnRename")
        self.footerLayout.addWidget(self.btnRename)

        self.btnCancel = QtWidgets.QPushButton(self.frmFooter)
        self.btnCancel.setObjectName("btnCancel")
        self.footerLayout.addWidget(self.btnCancel)

        self.mainLayout.addWidget(self.frmFooter)

        self.retranslateUi(frmRenameMedia)
        QtCore.QMetaObject.connectSlotsByName(frmRenameMedia)

    def retranslateUi(self, frmRenameMedia):
        _t = QtCore.QCoreApplication.translate
        frmRenameMedia.setWindowTitle(_t("frmRenameMedia", "Rename Media"))

        # Section 1
        self.lblFormatTitle.setText(_t("frmRenameMedia", "File Name Format"))
        for n in range(1, 5):
            getattr(self, f"lblSlot{n}").setText(
                _t("frmRenameMedia", f"Part {n}"))
        self.lblSample.setText(_t("frmRenameMedia", "Sample: —"))

        # Section 2
        self.lblOptionsTitle.setText(_t("frmRenameMedia", "Options"))
        self.chkShortenLocation.setText(_t("frmRenameMedia",
            "Shorten location name to the first punctuation mark (, - : @ ( )"))
        self.chkRemoveSpaces.setText(_t("frmRenameMedia", "Remove spaces"))

        # Table headers
        self.tblPhotos.setHorizontalHeaderItem(
            0, QtWidgets.QTableWidgetItem(""))
        self.tblPhotos.setHorizontalHeaderItem(
            1, QtWidgets.QTableWidgetItem(
                _t("frmRenameMedia", "Current File Name")))
        self.tblPhotos.setHorizontalHeaderItem(
            2, QtWidgets.QTableWidgetItem(
                _t("frmRenameMedia", "Proposed File Name")))
        self.tblPhotos.setHorizontalHeaderItem(
            3, QtWidgets.QTableWidgetItem(
                _t("frmRenameMedia", "Status")))

        # Footer
        self.btnSelectAll.setText(_t("frmRenameMedia", "Select All"))
        self.btnSelectNone.setText(_t("frmRenameMedia", "Select None"))
        self.btnSelectWav.setText(_t("frmRenameMedia", "WAV"))
        self.btnSelectJpg.setText(_t("frmRenameMedia", "JPG"))
        self.lblCount.setText(_t("frmRenameMedia", "0 of 0 selected"))
        self.btnRename.setText(_t("frmRenameMedia", "Rename"))
        self.btnCancel.setText(_t("frmRenameMedia", "Cancel"))


import icons_rc
