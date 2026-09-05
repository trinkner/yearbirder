# import the GUI forms that we create with Qt Creator
import form_Preferences
from code_Stylesheet import YBFont
import code_Audio

from PySide6.QtGui import QFont

from PySide6.QtCore import Signal, Qt, QTimer

from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMdiSubWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtMultimedia import QMediaPlayer

import math
import os
import struct
import tempfile
import wave

# Calibration test-sound geometry
_TICK_INTERVAL_MS = 600     # one tick / flash every 600 ms
_TICK_WAV_SECONDS = 60      # test sound length; loops while calibrating
_FLASH_MS = 90              # how long the visual flash stays lit


class Preferences(QMdiSubWindow, form_Preferences.Ui_frmPreferences):

    resized = Signal()

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.mdiParent = ""
        self.resized.connect(self.resizeMe)
        self.buttonBox.accepted.connect(self.savePreferences)
        self.buttonBox.rejected.connect(self.closeMe)
        self.btnSelectStartupFolder.clicked.connect(self.selectStartupFolder)
        self.btnSelectPhotoDataFile.clicked.connect(self.selectPhotoDataFile)
        self.btnToggleApiKey.clicked.connect(self.toggleApiKeyVisibility)
        self.tabWidget.currentChanged.connect(self.tabChanged)
        self.btnAddRig.clicked.connect(self._addRig)
        self.btnRemoveRig.clicked.connect(self._removeRig)
        self._buildPlaybackTab()

    def fillPreferences(self):
        self.txtStartupFolder.setText(self.mdiParent.db.getStartupFolder())
        if self.mdiParent.db.getStartupFolder() != "":
            self.chkStartupFolder.setChecked(True)

        self.txtPhotoDataFile.setText(self.mdiParent.db.photoDataFileDefault)
        if self.mdiParent.db.photoDataFileDefault != "":
            self.chkPhotoDataFile.setChecked(True)

        self.txtEbirdApiKey.setEchoMode(QLineEdit.EchoMode.Password)
        self.txtEbirdApiKey.setText(self.mdiParent.db.ebirdApiKey)

        self._fillMyLocationCombos()
        self._refreshRigTable()

    def _refreshRigTable(self):
        """Show the saved rigs.  Cells are edited in place; the table is the
        working copy and savePreferences() harvests it."""
        self.tblRigs.setRowCount(0)
        for rig in self.mdiParent.db.rigs:
            self._appendRigRow(rig.get("name", ""),
                               rig.get("recorder", ""),
                               rig.get("microphone", ""))

    def _appendRigRow(self, name, recorder, microphone):
        r = self.tblRigs.rowCount()
        self.tblRigs.insertRow(r)
        for col, value in enumerate((name, recorder, microphone)):
            self.tblRigs.setItem(r, col, QTableWidgetItem(value))
        return r

    def _addRig(self):
        r = self._appendRigRow("", "", "")
        self.tblRigs.selectRow(r)
        self.tblRigs.editItem(self.tblRigs.item(r, 0))

    def _removeRig(self):
        r = self.tblRigs.currentRow()
        if r >= 0:
            self.tblRigs.removeRow(r)

    def _harvestRigs(self):
        """Read the rig table back into (rigs, problems).

        A rig must carry all three fields: Manage Recordings applies a rig as a
        pair, so a half-filled one would blank a recorder or a microphone rather
        than set it.  Enforcing it here means every use site can trust it.

        A completely blank row is an Add the user thought better of, and is
        dropped in silence.  Anything partly filled — or a duplicate name — is
        reported instead of quietly discarded, so work never disappears without
        explanation."""
        rigs = []
        problems = []
        seen = set()
        for r in range(self.tblRigs.rowCount()):
            def cell(c):
                item = self.tblRigs.item(r, c)
                return item.text().strip() if item else ""
            name, recorder, mic = cell(0), cell(1), cell(2)

            if not any((name, recorder, mic)):
                continue                       # abandoned Add — nothing to keep

            missing = [label for label, value in
                       (("a name", name), ("a recording device", recorder),
                        ("a microphone", mic)) if not value]
            if missing:
                problems.append("Row %d (%s) needs %s."
                                % (r + 1, name or "unnamed", " and ".join(missing)))
                continue

            if name.lower() in seen:
                problems.append('Row %d: there is already a rig named "%s".'
                                % (r + 1, name))
                continue
            seen.add(name.lower())
            rigs.append({"name": name, "recorder": recorder, "microphone": mic})
        return rigs, problems

    def _fillMyLocationCombos(self):
        """Populate the My County and My Patch comboboxes from the open data file."""
        db = self.mdiParent.db

        self.cboMyCounty.clear()
        self.cboMyPatch.clear()

        if not db.eBirdFileOpenFlag:
            self.cboMyCounty.addItem("(open a data file to set)")
            self.cboMyPatch.addItem("(open a data file to set)")
            self.cboMyCounty.setEnabled(False)
            self.cboMyPatch.setEnabled(False)
            return

        self.cboMyCounty.setEnabled(True)
        self.cboMyPatch.setEnabled(True)

        self.cboMyCounty.addItem("")
        for county in sorted(set(db.countyList)):
            self.cboMyCounty.addItem(county)

        self.cboMyPatch.addItem("")
        for location in sorted(set(db.locationList)):
            self.cboMyPatch.addItem(location)

        # Select saved values
        idx = self.cboMyCounty.findText(db.myCounty)
        if idx >= 0:
            self.cboMyCounty.setCurrentIndex(idx)

        idx = self.cboMyPatch.findText(db.myPatch)
        if idx >= 0:
            self.cboMyPatch.setCurrentIndex(idx)

    def showTab(self, title):
        """Select the tab with this title (used when another window sends the
        user straight to a particular tab)."""
        for i in range(self.tabWidget.count()):
            if self.tabWidget.tabText(i) == title:
                self.tabWidget.setCurrentIndex(i)
                return

    def tabChanged(self, index):
        if self.tabWidget.tabText(index) == "My Locations":
            if not self.mdiParent.db.eBirdFileOpenFlag:
                QMessageBox.information(
                    self,
                    "No Data File Open",
                    "Please open an eBird data file before setting My County or My Patch.",
                    QMessageBox.StandardButton.Ok,
                )
        if self.tabWidget.tabText(index) == "Audio Calibration":
            self._refreshCurrentDevice()
            self._refreshDeviceTable()
            self._deviceTimer.start()
        else:
            self._deviceTimer.stop()
            self._stopTick()

    # ── Playback tab: per-device audio/cursor sync calibration ──────────
    #
    # Bluetooth outputs add ~300-500ms of latency downstream of anything Qt
    # can see, so the playback cursor leads the heard audio.  The user aligns
    # a repeating tick (played through the SAME warm-sink pipeline as real
    # playback) with a visual flash driven by the same position() clock the
    # spectrogram cursor uses; the resulting per-device offset is stored in
    # preferences and applied by every recordings window.

    def _buildPlaybackTab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setSpacing(10)

        self.lblCurrentDevice = QLabel("Current audio device:  \u2014")
        lay.addWidget(self.lblCurrentDevice)

        calRow = QHBoxLayout()
        self._flashBox = QFrame()
        self._flashBox.setFixedSize(46, 46)
        calRow.addWidget(self._flashBox)

        self.btnTick = QPushButton("Start Test")
        self.btnTick.clicked.connect(self._toggleTick)
        calRow.addWidget(self.btnTick)

        self.sldLatency = QSlider(Qt.Orientation.Horizontal)
        self.sldLatency.setRange(0, 600)
        self.sldLatency.valueChanged.connect(self._latencySliderChanged)
        calRow.addWidget(self.sldLatency, 1)

        self.spnLatency = QSpinBox()
        self.spnLatency.setRange(0, 600)
        self.spnLatency.setSuffix(" ms")
        self.spnLatency.valueChanged.connect(self._latencySpinChanged)
        calRow.addWidget(self.spnLatency)

        self.btnSaveLatency = QPushButton("Save")
        self.btnSaveLatency.clicked.connect(self._saveLatencyForDevice)
        calRow.addWidget(self.btnSaveLatency)
        lay.addLayout(calRow)

        note = QLabel(
            "To sync the spectrogram cursor to your audio device, start the "
            "test and drag the slider so the sound and flash feel "
            "simultaneous."
        )
        note.setWordWrap(True)
        lay.addWidget(note)

        self.tblDevices = QTableWidget(0, 3)
        self.tblDevices.setHorizontalHeaderLabels(["Device", "Offset", ""])
        deviceHeaderItem = self.tblDevices.horizontalHeaderItem(0)
        deviceHeaderItem.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.tblDevices.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.tblDevices.verticalHeader().setVisible(False)
        self.tblDevices.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tblDevices.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lay.addWidget(self.tblDevices, 1)

        self.tabWidget.addTab(tab, "Audio Calibration")

        self._tickPlayer = None
        self._ticking = False
        self._lastTickIdx = -1
        self._currentKey = None
        self._setFlash(False)
        self._flashTimer = QTimer(self)
        self._flashTimer.setInterval(16)
        self._flashTimer.timeout.connect(self._pollFlash)
        # Re-check the default output once a second while the tab is open, so
        # switching devices in Control Center updates the tab live.
        self._deviceTimer = QTimer(self)
        self._deviceTimer.setInterval(1000)
        self._deviceTimer.timeout.connect(self._refreshCurrentDevice)

    def _latencyMap(self):
        return self.mdiParent.db.audioLatencyByDevice

    def _refreshCurrentDevice(self):
        key, name = code_Audio.current_output_key_and_name()
        if key == self._currentKey:
            return
        self._currentKey = key
        self.lblCurrentDevice.setText("Current audio device:  " + name)
        entry = self._latencyMap().get(key)
        try:
            ms = int(entry.get("ms", 0)) if entry else 0
        except (TypeError, ValueError):
            ms = 0
        for w in (self.sldLatency, self.spnLatency):
            w.blockSignals(True)
            w.setValue(ms)
            w.blockSignals(False)

    def _setFlash(self, on):
        self._flashBox.setStyleSheet(
            "QFrame { background-color: %s; border-radius: 8px; }"
            % ("#4f8ef7" if on else "#252730"))

    def _ensureTickWav(self):
        """Generate (once) a WAV of sharp 1 kHz ticks at the calibration
        interval; played through PcmAudioPlayer so the calibration measures
        the exact same pipeline as real recordings playback."""
        path = os.path.join(tempfile.gettempdir(), "yearbirder_calibration_tick.wav")
        if os.path.isfile(path):
            return path
        fs = 44100
        total = fs * _TICK_WAV_SECONDS
        interval = int(fs * _TICK_INTERVAL_MS / 1000)
        tick_len = int(fs * 0.04)
        samples = bytearray(total * 2)
        for start in range(0, total - tick_len, interval):
            for i in range(tick_len):
                amp = 0.75 * math.exp(-i / (tick_len / 5.0))
                v = int(32767 * amp * math.sin(2 * math.pi * 1000 * i / fs))
                struct.pack_into("<h", samples, (start + i) * 2, v)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(fs)
            w.writeframes(bytes(samples))
        return path

    def _toggleTick(self):
        if self._ticking:
            self._stopTick()
            return
        if self._tickPlayer is None:
            self._tickPlayer = code_Audio.PcmAudioPlayer(self)
            self._tickPlayer.mediaStatusChanged.connect(self._tickStatus)
        try:
            ok = self._tickPlayer.setSourceWav(self._ensureTickWav())
        except OSError:
            ok = False
        if not ok:
            QMessageBox.warning(self, "Calibration",
                                "Could not create the calibration test sound.")
            return
        self._ticking = True
        self._lastTickIdx = -1
        self._tickPlayer.play()
        self._flashTimer.start()
        self.btnTick.setText("Stop Test")

    def _stopTick(self):
        if not getattr(self, "_ticking", False):
            return
        self._ticking = False
        self._flashTimer.stop()
        self._setFlash(False)
        if self._tickPlayer is not None:
            self._tickPlayer.stop()
        self.btnTick.setText("Start Test")

    def _tickStatus(self, status):
        # loop the test sound for as long as the user is calibrating
        if self._ticking and status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._tickPlayer.play()

    def _pollFlash(self):
        """Flash when the COMPENSATED position crosses a tick boundary: when
        the user has the slider right, flash and heard tick coincide."""
        if not self._ticking or self._tickPlayer is None:
            return
        idx = self._tickPlayer.position() // _TICK_INTERVAL_MS
        if idx != self._lastTickIdx:
            self._lastTickIdx = idx
            self._setFlash(True)
            QTimer.singleShot(_FLASH_MS, self._flashBox,
                              lambda: self._setFlash(False))

    def _latencySliderChanged(self, v):
        self.spnLatency.blockSignals(True)
        self.spnLatency.setValue(v)
        self.spnLatency.blockSignals(False)
        self._applyLatencyLive(v)

    def _latencySpinChanged(self, v):
        self.sldLatency.blockSignals(True)
        self.sldLatency.setValue(v)
        self.sldLatency.blockSignals(False)
        self._applyLatencyLive(v)

    def _applyLatencyLive(self, ms):
        key, name = code_Audio.current_output_key_and_name()
        if not key:
            return
        self._latencyMap()[key] = {"ms": int(ms), "name": name}
        code_Audio.PcmAudioPlayer.setLatencyMap(self._latencyMap())

    def _saveLatencyForDevice(self):
        self._applyLatencyLive(self.sldLatency.value())
        self.mdiParent.db.writePreferences()
        self._refreshDeviceTable()

    def _refreshDeviceTable(self):
        m = self._latencyMap()
        self.tblDevices.setRowCount(0)
        for key in sorted(m, key=lambda k: m[k].get("name", "")):
            entry = m[key]
            r = self.tblDevices.rowCount()
            self.tblDevices.insertRow(r)
            item = QTableWidgetItem(entry.get("name", key))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tblDevices.setItem(r, 0, item)
            spin = QSpinBox()
            spin.setRange(0, 600)
            spin.setSuffix(" ms")
            spin.setValue(int(entry.get("ms", 0)))
            spin.valueChanged.connect(lambda v, k=key: self._deviceTableEdited(k, v))
            self.tblDevices.setCellWidget(r, 1, spin)
            btn = QPushButton("Remove")
            btn.clicked.connect(lambda _=False, k=key: self._removeDevice(k))
            self.tblDevices.setCellWidget(r, 2, btn)

    def _deviceTableEdited(self, key, ms):
        m = self._latencyMap()
        if key in m:
            m[key]["ms"] = int(ms)
            code_Audio.PcmAudioPlayer.setLatencyMap(m)
            self.mdiParent.db.writePreferences()
            if key == self._currentKey:
                for w in (self.sldLatency, self.spnLatency):
                    w.blockSignals(True)
                    w.setValue(int(ms))
                    w.blockSignals(False)

    def _removeDevice(self, key):
        self._latencyMap().pop(key, None)
        code_Audio.PcmAudioPlayer.setLatencyMap(self._latencyMap())
        self.mdiParent.db.writePreferences()
        self._refreshDeviceTable()
        if key == self._currentKey:
            self._currentKey = None       # re-sync slider on next refresh
            self._refreshCurrentDevice()

    def closeEvent(self, event):
        self._stopTick()
        self._deviceTimer.stop()
        super(self.__class__, self).closeEvent(event)

    def resizeEvent(self, event):
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)

    def resizeMe(self):
        # Inset like every other child window (Lists, Stats, Graphs all use
        # 5, 27 with matching right/bottom margins).  Flush to x=0 at full
        # width/height, the content covered the native window frame and hid the
        # hairline border AppStyle.drawPrimitive paints there for PE_FrameWindow.
        self.contentWidget.setGeometry(5, 27, self.width() - 10, self.height() - 35)

    def closeMe(self):
        self.close()

    def scaleMe(self):
        fontSize = self.mdiParent.fontSize

        for w in ([
            self.grpStartupFolder,
            self.grpPhotoDataFile,
            self.grpEbirdApiKey,
            self.grpMyCounty,
            self.grpMyPatch,
            self.chkStartupFolder,
            self.chkPhotoDataFile,
            self.txtStartupFolder,
            self.txtPhotoDataFile,
            self.txtEbirdApiKey,
            self.lblEbirdApiKey,
            self.lblMyCountyDesc,
            self.lblMyPatchDesc,
            self.cboMyCounty,
            self.cboMyPatch,
            self.btnSelectStartupFolder,
            self.btnSelectPhotoDataFile,
            self.btnToggleApiKey,
            self.tabWidget,
        ]):
            try:
                w.setFont(QFont(YBFont, fontSize))
            except:
                pass

        self.resizeMe()

    def savePreferences(self):
        if self.chkStartupFolder.isChecked():
            self.mdiParent.db.startupFolder = self.txtStartupFolder.text()
        else:
            self.mdiParent.db.startupFolder = ""

        if self.chkPhotoDataFile.isChecked():
            self.mdiParent.db.photoDataFileDefault = self.txtPhotoDataFile.text()
        else:
            self.mdiParent.db.photoDataFileDefault = ""

        self.mdiParent.db.ebirdApiKey = self.txtEbirdApiKey.text().strip()

        if self.cboMyCounty.isEnabled():
            self.mdiParent.db.myCounty = self.cboMyCounty.currentText()

        if self.cboMyPatch.isEnabled():
            self.mdiParent.db.myPatch = self.cboMyPatch.currentText()

        rigs, rigProblems = self._harvestRigs()
        if rigProblems:
            # Stay open on the Gear tab rather than saving a partial rig or
            # dropping it silently — the user is mid-edit, not done.
            self.showTab("Recording Gear")
            QMessageBox.warning(
                self, "Incomplete Rig",
                "Every rig needs a name, a recording device, and a microphone, "
                "and each name must be unique.\n\n" + "\n".join(rigProblems))
            return
        self.mdiParent.db.rigs = rigs

        self.mdiParent.db.writePreferences()
        self.mdiParent.updateMyLocationButtons()
        # An open Add/Manage Recordings window built its rig pickers from the
        # old list — a user who came here precisely because they had no rigs
        # would otherwise return to an empty combo.
        self.mdiParent.refreshOpenRigPickers()

        self.close()

    def toggleApiKeyVisibility(self):
        if self.txtEbirdApiKey.echoMode() == QLineEdit.EchoMode.Password:
            self.txtEbirdApiKey.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btnToggleApiKey.setText("Hide")
        else:
            self.txtEbirdApiKey.setEchoMode(QLineEdit.EchoMode.Password)
            self.btnToggleApiKey.setText("Show")

    def selectStartupFolder(self):
        folder = str(QFileDialog.getExistingDirectory(
            self, "Select Startup Folder", self.mdiParent.db.startupFolder
        ))
        if folder != "":
            self.txtStartupFolder.setText(folder)
            self.chkStartupFolder.setChecked(True)

    def selectPhotoDataFile(self):
        fname = QFileDialog.getOpenFileName(
            self, "Select Photo Data File",
            self.mdiParent.db.photoDataFile,
            "Photo Data Files (*.jsonl *.csv)"
        )
        if fname[0] != "":
            self.txtPhotoDataFile.setText(fname[0])
            self.chkPhotoDataFile.setChecked(True)
