# -*- coding: utf-8 -*-

from PySide6 import QtCore, QtGui, QtWidgets


class Ui_frmRenamePhotos(object):

    def setupUi(self, frmRenamePhotos):
        frmRenamePhotos.setObjectName("frmRenamePhotos")
        frmRenamePhotos.resize(960, 720)
        frmRenamePhotos.setMinimumSize(QtCore.QSize(600, 400))
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(":/icon_bird_white.png"),
                       QtGui.QIcon.Normal, QtGui.QIcon.Off)
        frmRenamePhotos.setWindowIcon(icon)

        # ── Outer container ───────────────────────────────────────────────────
        self.frmContainer = QtWidgets.QWidget(frmRenamePhotos)
        self.frmContainer.setObjectName("frmContainer")
        self.mainLayout = QtWidgets.QVBoxLayout(self.frmContainer)
        self.mainLayout.setContentsMargins(8, 8, 8, 8)
        self.mainLayout.setSpacing(6)

        # ══════════════════════════════════════════════════════════════════════
        # SECTION 1 — Name Format
        # ══════════════════════════════════════════════════════════════════════
        self.frmFormat = QtWidgets.QFrame(self.frmContainer)
        self.frmFormat.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frmFormat.setObjectName("frmFormat")
        self.frmFormatLayout = QtWidgets.QVBoxLayout(self.frmFormat)
        self.frmFormatLayout.setContentsMargins(0, 0, 0, 0)
        self.frmFormatLayout.setSpacing(4)

        # Section title
        self.lblFormatTitle = QtWidgets.QLabel(self.frmFormat)
        self.lblFormatTitle.setObjectName("lblFormatTitle")
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(QtGui.QFont.Weight.Bold)
        self.lblFormatTitle.setFont(font)
        self.frmFormatLayout.addWidget(self.lblFormatTitle)

        # Slot row
        self.frmSlots = QtWidgets.QFrame(self.frmFormat)
        self.frmSlots.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frmSlots.setObjectName("frmSlots")
        self.slotsLayout = QtWidgets.QHBoxLayout(self.frmSlots)
        self.slotsLayout.setContentsMargins(0, 0, 0, 0)
        self.slotsLayout.setSpacing(8)

        for n in range(1, 5):
            lbl = QtWidgets.QLabel(self.frmSlots)
            lbl.setObjectName(f"lblSlot{n}")
            self.slotsLayout.addWidget(lbl)
            cbo = QtWidgets.QComboBox(self.frmSlots)
            cbo.setObjectName(f"cboSlot{n}")
            cbo.setMinimumWidth(110)
            self.slotsLayout.addWidget(cbo)
            setattr(self, f"lblSlot{n}", lbl)
            setattr(self, f"cboSlot{n}", cbo)

        self.slotsLayout.addStretch()
        self.frmFormatLayout.addWidget(self.frmSlots)

        # Date/time format row
        self.frmFormats = QtWidgets.QFrame(self.frmFormat)
        self.frmFormats.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.frmFormats.setObjectName("frmFormats")
        self.formatsLayout = QtWidgets.QHBoxLayout(self.frmFormats)
        self.formatsLayout.setContentsMargins(0, 0, 0, 0)
        self.formatsLayout.setSpacing(8)

        self.lblDateFormat = QtWidgets.QLabel(self.frmFormats)
        self.lblDateFormat.setObjectName("lblDateFormat")
        self.formatsLayout.addWidget(self.lblDateFormat)
        self.cboDateFormat = QtWidgets.QComboBox(self.frmFormats)
        self.cboDateFormat.setObjectName("cboDateFormat")
        self.cboDateFormat.setMinimumWidth(130)
        self.formatsLayout.addWidget(self.cboDateFormat)

        self.formatsLayout.addSpacing(16)

        self.lblTimeFormat = QtWidgets.QLabel(self.frmFormats)
        self.lblTimeFormat.setObjectName("lblTimeFormat")
        self.formatsLayout.addWidget(self.lblTimeFormat)
        self.cboTimeFormat = QtWidgets.QComboBox(self.frmFormats)
        self.cboTimeFormat.setObjectName("cboTimeFormat")
        self.cboTimeFormat.setMinimumWidth(130)
        self.formatsLayout.addWidget(self.cboTimeFormat)

        self.formatsLayout.addSpacing(16)

        self.lblNameFormat = QtWidgets.QLabel(self.frmFormats)
        self.lblNameFormat.setObjectName("lblNameFormat")
        self.formatsLayout.addWidget(self.lblNameFormat)
        self.cboNameFormat = QtWidgets.QComboBox(self.frmFormats)
        self.cboNameFormat.setObjectName("cboNameFormat")
        self.cboNameFormat.setMinimumWidth(150)
        self.formatsLayout.addWidget(self.cboNameFormat)

        self.formatsLayout.addStretch()
        self.frmFormatLayout.addWidget(self.frmFormats)

        # Sample filename label
        self.lblSample = QtWidgets.QLabel(self.frmFormat)
        self.lblSample.setObjectName("lblSample")
        self.frmFormatLayout.addWidget(self.lblSample)

        self.mainLayout.addWidget(self.frmFormat)

        # Separator 1
        self.lineSep1 = QtWidgets.QFrame(self.frmContainer)
        self.lineSep1.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self.lineSep1.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        self.lineSep1.setObjectName("lineSep1")
        self.mainLayout.addWidget(self.lineSep1)

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

        # Checklist time fallback checkbox
        self.chkUseChecklistTime = QtWidgets.QCheckBox(self.frmOptions)
        self.chkUseChecklistTime.setObjectName("chkUseChecklistTime")
        self.chkUseChecklistTime.setChecked(True)
        self.frmOptionsLayout.addWidget(self.chkUseChecklistTime)

        # Shorten location names checkbox
        self.chkShortenLocation = QtWidgets.QCheckBox(self.frmOptions)
        self.chkShortenLocation.setObjectName("chkShortenLocation")
        self.frmOptionsLayout.addWidget(self.chkShortenLocation)

        # Add tenths checkbox
        self.chkAddTenths = QtWidgets.QCheckBox(self.frmOptions)
        self.chkAddTenths.setObjectName("chkAddTenths")
        self.frmOptionsLayout.addWidget(self.chkAddTenths)

        self.frmOptionsLayout.addSpacing(8)

        # Duplicate-suffix note
        self.lblDuplicateNote = QtWidgets.QLabel(self.frmOptions)
        self.lblDuplicateNote.setObjectName("lblDuplicateNote")
        self.frmOptionsLayout.addWidget(self.lblDuplicateNote)

        # Backup warning
        self.lblWarning = QtWidgets.QLabel(self.frmOptions)
        self.lblWarning.setObjectName("lblWarning")
        self.frmOptionsLayout.addWidget(self.lblWarning)

        self.mainLayout.addWidget(self.frmOptions)

        # Separator 2
        self.lineSep2 = QtWidgets.QFrame(self.frmContainer)
        self.lineSep2.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self.lineSep2.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        self.lineSep2.setObjectName("lineSep2")
        self.mainLayout.addWidget(self.lineSep2)

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
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
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

        # Separator 3
        self.lineSep3 = QtWidgets.QFrame(self.frmContainer)
        self.lineSep3.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self.lineSep3.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        self.lineSep3.setObjectName("lineSep3")
        self.mainLayout.addWidget(self.lineSep3)

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

        self.retranslateUi(frmRenamePhotos)
        QtCore.QMetaObject.connectSlotsByName(frmRenamePhotos)

    def retranslateUi(self, frmRenamePhotos):
        _t = QtCore.QCoreApplication.translate
        frmRenamePhotos.setWindowTitle(_t("frmRenamePhotos", "Rename Photos"))

        # Section 1
        self.lblFormatTitle.setText(_t("frmRenamePhotos", "Name Format"))
        for n in range(1, 5):
            getattr(self, f"lblSlot{n}").setText(
                _t("frmRenamePhotos", f"Slot {n}:"))
        self.lblDateFormat.setText(_t("frmRenamePhotos", "Date Format:"))
        self.lblTimeFormat.setText(_t("frmRenamePhotos", "Time Format:"))
        self.lblNameFormat.setText(_t("frmRenamePhotos", "Species Name Format:"))
        self.lblSample.setText(_t("frmRenamePhotos", "Sample: —"))

        # Section 2
        self.lblOptionsTitle.setText(_t("frmRenamePhotos", "Options"))
        self.chkUseChecklistTime.setText(_t("frmRenamePhotos",
            "Use checklist time for photos without a time"))
        self.chkShortenLocation.setText(_t("frmRenamePhotos",
            "Shorten location name to the first punctuation mark (, - : @ ( )"))
        self.chkAddTenths.setText(_t("frmRenamePhotos",
            "If photos have the same HH-MM-SS, add tenths (if available)"))
        self.chkRemoveSpaces.setText(_t("frmRenamePhotos", "Remove spaces"))
        self.lblDuplicateNote.setText(_t("frmRenamePhotos",
            "When files would share the same proposed name, Yearbirder will add _1, _2, etc."))
        self.lblWarning.setText(_t("frmRenamePhotos",
            "⚠  Renaming is permanent and cannot be undone. "
            "Backup your photos before proceeding."))

        # Table headers
        self.tblPhotos.setHorizontalHeaderItem(
            0, QtWidgets.QTableWidgetItem(""))
        self.tblPhotos.setHorizontalHeaderItem(
            1, QtWidgets.QTableWidgetItem(
                _t("frmRenamePhotos", "Current Filename")))
        self.tblPhotos.setHorizontalHeaderItem(
            2, QtWidgets.QTableWidgetItem(
                _t("frmRenamePhotos", "Proposed Filename")))
        self.tblPhotos.setHorizontalHeaderItem(
            3, QtWidgets.QTableWidgetItem(
                _t("frmRenamePhotos", "Status")))

        # Footer
        self.btnSelectAll.setText(_t("frmRenamePhotos", "Select All"))
        self.btnSelectNone.setText(_t("frmRenamePhotos", "Select None"))
        self.lblCount.setText(_t("frmRenamePhotos", "0 of 0 selected"))
        self.btnRename.setText(_t("frmRenamePhotos", "Rename"))
        self.btnCancel.setText(_t("frmRenamePhotos", "Cancel"))


import icons_rc
