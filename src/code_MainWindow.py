#! /usr/bin/env python

# import the GUI forms that we create with Qt Creator
import code_DataBase
from code_Stylesheet import YBFont
import code_BigReport
import code_Stats
import code_MediaRefresh
from shiboken6 import isValid
import code_Filter
import code_Find
import code_Explorer
import code_Lists
import code_Individual
import code_Web
import code_Families
import code_Compare
import code_Location
import code_LocationTotals
import code_DateTotals
import code_Graphs
import code_Photos
import code_Recordings
import code_SpeciesGallery
import code_RecordingsSpeciesGallery
import code_ManagePhotos
import code_ManageRecordings
import code_RenameMedia
import code_Preferences
import code_Stylesheet

import form_MDIMain

# import basic Python libraries
import sys
import os
import glob
import re
import queue
import threading
import time
import subprocess
import datetime
import json
import urllib.request
import urllib.error

import code_ThumbnailCache

from math import (
    ceil,
    floor,
    modf
    )

# import the Qt components we'll use
# do this so later we won't have to clutter our code with references to parent Qt classes 

from PySide6.QtGui import (
    QAction,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QFontInfo,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
    QTextDocument,
    QColor
    )
    
from PySide6.QtCore import (
    Qt,
    QDate,
    QMarginsF,
    QSize,
    QTimer,
    QEvent,
    QThread,
    Signal,
    QUrl
    )
    
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QListWidget,
    QMdiArea,
    QMessageBox,
    QMainWindow,
    QFileDialog,
    QSlider,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QCheckBox,
    QMenu,
    QProxyStyle,
    QStyle,
    QStyleOptionToolButton,
    QWidget,
    )

from PySide6.QtPrintSupport import (
    QPrintDialog,
    QPrinter
    )
from PySide6.QtGui import QPageSize, QPageLayout


class _ProgressOverlay(QWidget):
    """Child-widget progress overlay used during data and photo loading.

    Replaces the three frameless QDialog progress dialogs.  Because this is a
    plain child widget rather than a top-level window, Windows DWM never needs
    to re-composite the window stack when loading completes \u2014 eliminating the
    desktop-wallpaper flash that occurred with the old modal/frameless dialogs
    on Windows.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("_ProgressOverlay")
        self.setFixedWidth(380)

        self.setStyleSheet("""
            #_ProgressOverlay {
                background: #1e1f26;
                border: 2px solid #4f8ef7;
                border-radius: 10px;
            }
            QLabel {
                color: #e2e4ec;
                font-size: 13px;
                background: transparent;
            }
            QProgressBar {
                background: #252730;
                border: 1px solid #3a3d4e;
                border-radius: 5px;
                min-height: 20px;
                text-align: center;
                color: #e2e4ec;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background: #4f8ef7;
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        self._label = QLabel("")
        self._label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        layout.addWidget(self._bar)

        # Time-based reveal gate.  When armed, the overlay stays hidden until the
        # work has run longer than a threshold, so fast operations on quick
        # machines never flash a progress bar.  Disarmed (default) = show at once.
        self._gateStart = None
        self._gateMs = 0
        self._revealed = True

        self.hide()

    def _reposition(self):
        mdi = self.parent().mdiArea
        pos = mdi.mapTo(self.parent(), mdi.rect().topLeft())
        x = pos.x() + (mdi.width()  - self.width())  // 2
        y = pos.y() + (mdi.height() - self.height()) // 2
        self.move(x, y)
        self.raise_()

    def armGate(self, threshold_ms=1000, force=True):
        """Arm a time-based reveal: keep the overlay hidden until the work has run
        longer than threshold_ms, so fast operations never flash a progress bar.
        force=False keeps an already-running clock, so the gate can span
        FillPhotos → SortAndDisplayPhotos as a single operation."""
        if not force and self._gateStart is not None:
            return
        self._gateStart = time.monotonic()
        self._gateMs = threshold_ms
        self._revealed = False

    def _gatedShow(self):
        """Reveal the overlay immediately when ungated, or once the gate elapses."""
        if not self._revealed:
            if (self._gateStart is None
                    or (time.monotonic() - self._gateStart) * 1000.0 < self._gateMs):
                return                      # not slow enough yet — stay hidden
            self._revealed = True
        if not self.isVisible():
            self.adjustSize()
            self._reposition()
            self.show()

    def hide(self):
        # Dismissing the overlay also disarms the reveal gate.
        self._gateStart = None
        self._revealed = True
        super().hide()

    def showForDataLoad(self):
        self._label.setText("Loading eBird data\u2026")
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self.adjustSize()
        self._reposition()
        self._gatedShow()

    def showForPhotos(self):
        self._noun = "photos"
        self._label.setText("Preparing photos\u2026")
        self._bar.setRange(0, 0)   # indeterminate until startLoading() is called
        self._bar.setValue(0)
        self.adjustSize()
        self._reposition()
        self._gatedShow()

    def showForRecordings(self):
        self._noun = "recordings"
        self._label.setText("Preparing recordings\u2026")
        self._bar.setRange(0, 0)
        self._bar.setValue(0)
        self.adjustSize()
        self._reposition()
        self._gatedShow()

    def startLoading(self, total):
        """Switch from indeterminate to determinate mode once total is known."""
        noun = getattr(self, "_noun", "photos")
        self._bar.setRange(0, max(total, 1))
        self._bar.setValue(0)
        self._label.setText(f"Loading {noun}\u2026  0 of {total:,}")

    def setValue(self, v):
        self._bar.setValue(v)
        self._gatedShow()

    def setPhotoValue(self, loaded):
        noun = getattr(self, "_noun", "photos")
        self._bar.setValue(loaded)
        self._label.setText(
            f"Loading {noun}\u2026  {loaded:,} of {self._bar.maximum():,}"
        )
        self._gatedShow()

    def showDeterminate(self, message, total):
        """Show the overlay in determinate mode with a custom message and known
        total \u2014 same visual style as photo loading, reused for batch jobs."""
        self._message = message
        self._bar.setRange(0, max(total, 1))
        self._bar.setValue(0)
        self._label.setText(f"{message}  0 of {total:,}")
        self.adjustSize()
        self._reposition()
        self._gatedShow()

    def setProgress(self, value):
        self._bar.setValue(value)
        self._label.setText(
            f"{getattr(self, '_message', 'Working\u2026')}  "
            f"{value:,} of {self._bar.maximum():,}"
        )
        self._gatedShow()


class _WhiteIconToolbarStyle(QProxyStyle):
    """Proxy style that draws white icons on toolbar buttons, leaving menu icons unchanged."""
    def __init__(self, white_icon_map):
        super().__init__()
        self._map = white_icon_map  # {QAction: QIcon}

    def drawControl(self, element, option, painter, widget=None):
        if (element == QStyle.ControlElement.CE_ToolButtonLabel
                and isinstance(option, QStyleOptionToolButton)
                and widget is not None
                and hasattr(widget, 'defaultAction')):
            action = widget.defaultAction()
            if action in self._map:
                opt = QStyleOptionToolButton(option)
                opt.icon = self._map[action]
                super().drawControl(element, opt, painter, widget)
                return
        super().drawControl(element, option, painter, widget)


class _OptimizePhotoSettingsDialog(QDialog):
    """Scans photo settings for missing files and offers to remove them."""

    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.missing = []

        self.setWindowTitle("Compact Catalog and Cache")
        self.setMinimumWidth(520)
        self.setModal(True)

        # Blue circle "?" icon — matches code_Stylesheet.question()
        px = QPixmap(48, 48)
        px.fill(Qt.GlobalColor.transparent)
        painter = QPainter(px)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(code_Stylesheet.CHART_PRIMARY))
        painter.drawEllipse(0, 0, 48, 48)
        font = painter.font()
        font.setPixelSize(30)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "?")
        painter.end()
        _icon = QLabel()
        _icon.setPixmap(px)
        _icon.setFixedWidth(64)

        # Content area — _showResults() appends to this
        self._layout = QVBoxLayout()
        self._layout.setSpacing(12)

        self._statusLabel = QLabel("Checking media files…")
        self._statusLabel.setWordWrap(True)
        self._layout.addWidget(self._statusLabel)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._layout.addWidget(self._progress)

        self._listWidget = QListWidget()
        self._listWidget.setMaximumHeight(200)
        self._listWidget.setVisible(False)
        self._layout.addWidget(self._listWidget)

        self._buttonBox = QDialogButtonBox()
        self._buttonBox.setVisible(False)
        self._layout.addWidget(self._buttonBox)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(_icon, alignment=Qt.AlignmentFlag.AlignTop)
        body.addLayout(self._layout)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.addLayout(body)

        QTimer.singleShot(50, self._scan)

    def _scan(self):
        missing = []
        for i, sighting in enumerate(self.db.sightingList):
            if i % 200 == 0:
                QApplication.processEvents()
            for j, photo in enumerate(sighting.get("photos", [])):
                path = photo.get("fileName", "")
                if path and not os.path.isfile(path):
                    missing.append({
                        "sighting_idx": i,
                        "media_idx": j,
                        "kind": "photo",
                        "path": path,
                        "species": sighting.get("commonName", "Unknown"),
                    })
            for j, rec in enumerate(sighting.get("audio", [])):
                path = rec.get("fileName", "")
                if path and not os.path.isfile(path):
                    missing.append({
                        "sighting_idx": i,
                        "media_idx": j,
                        "kind": "recording",
                        "path": path,
                        "species": sighting.get("commonName", "Unknown"),
                    })
        self.missing = missing
        self._showResults()

    def _showResults(self):
        self._progress.setVisible(False)

        skipped = self.db.jsonlSkippedLines
        skipped_note = (
            f"\n\n{skipped} line{'s' if skipped != 1 else ''} in the media "
            f"catalog could not be read and will be dropped on compaction."
        ) if skipped > 0 else ""

        cache_note = (
            "\n\nUnused cached images (thumbnails and spectrograms not matching "
            "this catalog) will also be cleared from disk."
        )

        if not self.missing:
            self._statusLabel.setText(
                "Good news! Files exist on disk for all media files in the catalog."
                + skipped_note
                + cache_note
                + "\n\nCompact the catalog and cache?\n"
            )
            btn_box = QDialogButtonBox()
            btn_box.addButton("Compact", QDialogButtonBox.ButtonRole.AcceptRole)
            btn_box.addButton(QDialogButtonBox.StandardButton.Cancel)
            btn_box.accepted.connect(self.accept)
            btn_box.rejected.connect(self.reject)
            self._layout.addWidget(btn_box)
            self.adjustSize()
            return

        n_photos = sum(1 for m in self.missing if m["kind"] == "photo")
        n_recordings  = sum(1 for m in self.missing if m["kind"] == "recording")
        species_set = {m["species"] for m in self.missing}
        s_count = len(species_set)

        parts = []
        if n_photos:
            parts.append(f"{n_photos} photo {'file' if n_photos == 1 else 'files'}")
        if n_recordings:
            parts.append(f"{n_recordings} recording {'file' if n_recordings == 1 else 'files'}")
        summary = (
            f"{' and '.join(parts)} could not be found on disk "
            f"({s_count} {'species' if s_count != 1 else 'species'})."
        )

        self._statusLabel.setText(
            summary + skipped_note + "\n\n"
            "These entries will be removed from the media catalog "
            "and the file will be compacted. This cannot be undone."
            + cache_note
        )

        for m in self.missing:
            kind_tag = "[Photo]" if m["kind"] == "photo" else "[Recording]"
            self._listWidget.addItem(
                f"{kind_tag} {os.path.basename(m['path'])}  —  {m['species']}"
            )
        self._listWidget.setVisible(True)

        self._buttonBox.addButton(
            "Optimize", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._buttonBox.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._buttonBox.accepted.connect(self.accept)
        self._buttonBox.rejected.connect(self.reject)
        self._buttonBox.setVisible(True)

        self.adjustSize()


class _UpdateCheckThread(QThread):
    """Fetches the latest release tag from GitHub in a background thread."""
    done = Signal(str)  # emits tag name like "v1.491", or "" on error

    def run(self):
        url = "https://api.github.com/repos/trinkner/yearbirder/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "Yearbirder"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.done.emit(data.get("tag_name", ""))
        except Exception:
            self.done.emit("")


class MainWindow(QMainWindow, form_MDIMain.Ui_MainWindow):

    # initialize main database that will be used throughout program
    db = code_DataBase.DataBase()
    fontSize = 11
    scaleFactor = 1
    rowHeight = 16  # default; recomputed in ScaleDisplay() and __init__
    versionNumber = "2.10"
    versionDate = "August 7, 2026"
    taxonomyYear = ""

    def __init__(self):
        super(self.__class__, self).__init__()

        # macOS: pin the APPLICATION default font's family by name, so widgets
        # that never call setFont are also immune to the session-wide
        # font-registration bug (see YBFont in code_Stylesheet — the empty
        # "system default" family misresolves to the emoji font after Qt
        # rebuilds its font database).  Family only; size/weight stay default.
        if sys.platform == "darwin":
            _appFont = QApplication.font()
            _appFont.setFamily(YBFont)
            QApplication.setFont(_appFont)

        self.setupUi(self)
        self.setCentralWidget(self.mdiArea)
        self.actionAboutYearbirder.setText("About Yearbirder")

        # The form sets scrMediaFilter with AlignTop + stretch=0, which prevents it
        # from expanding to fill the dock and causes a spurious scroll bar.
        self.verticalLayout_4.setAlignment(self.scrMediaFilter, Qt.Alignment())
        self.verticalLayout_4.setStretchFactor(self.scrMediaFilter, 1)
        # Pin the media filter content to the top (mirrors how frmFilter is AlignTop
        # in the standard filter), so items aren't stretched to fill the scroll area.
        self.verticalLayout_5.setAlignment(self.frmMediaFilter, Qt.AlignTop)

        # Black icons for drop-down menus (loaded from Qt resource system)
        _menuIcons = {
            self.actionOpen:           ":/icon_open.png",
            self.actionPrint:          ":/icon_print.png",
            self.actionCreatePDF:      ":/icon_pdf.png",
            self.actionSpecies:        ":/icon_bird.png",
            self.actionLocations:      ":/icon_location.png",
            self.actionChecklists:     ":/icon_checklists.png",
            self.actionMap:            ":/icon_map.png",
            self.actionFamilies:       ":/icon_piechart_white.png",
            self.actionDateTotals:     ":/icon_datetotals.png",
            self.actionLocationTotals: ":/icon_locationtotals.png",
            self.actionCompareLists:   ":/icon_compare.png",
            self.actionBigReport:      ":/icon_tripreport.png",
            self.actionStats:          ":/icon_datetotals.png",
            self.actionPhotos:         ":/icon_camera.png",
            self.actionFind:           ":/icon_find.png",
            self.actionClearAllFilters:":/icon_filter.png",
        }
        for action, path in _menuIcons.items():
            action.setIcon(QIcon(QPixmap(path)))
        # White icons for toolbar buttons via proxy style (menus keep the black icons above)
        _whiteIconMap = {
            self.actionOpen:           QIcon(QPixmap(":/icon_open_white.png")),
            self.actionPrint:          QIcon(QPixmap(":/icon_print_white.png")),
            self.actionCreatePDF:      QIcon(QPixmap(":/icon_pdf_white.png")),
            self.actionSpecies:        QIcon(QPixmap(":/icon_bird_white.png")),
            self.actionLocations:      QIcon(QPixmap(":/icon_location_white.png")),
            self.actionChecklists:     QIcon(QPixmap(":/icon_checklists_white.png")),
            self.actionMap:            QIcon(QPixmap(":/icon_map_white.png")),
            self.actionFamilies:       QIcon(QPixmap(":/icon_piechart_white.png")),
            self.actionDateTotals:     QIcon(QPixmap(":/icon_datetotals_white.png")),
            self.actionLocationTotals: QIcon(QPixmap(":/icon_locationtotals_white.png")),
            self.actionCompareLists:   QIcon(QPixmap(":/icon_compare_white.png")),
            self.actionBigReport:      QIcon(QPixmap(":/icon_tripreport_white.png")),
            self.actionStats:          QIcon(QPixmap(":/icon_datetotals_white.png")),
            self.actionPhotos:         QIcon(QPixmap(":/icon_camera_white.png")),
            self.actionRecordingsToolbar: QIcon(QPixmap(":/icon_microphone_white.png")),
            self.actionFind:           QIcon(QPixmap(":/icon_find_white.png")),
            self.actionClearAllFilters:QIcon(QPixmap(":/icon_filter_white.png")),
        }
        self._toolbarStyle = _WhiteIconToolbarStyle(_whiteIconMap)
        self.toolBar.setStyle(self._toolbarStyle)

        # Remove all separators from the toolbar for uniform spacing
        for action in self.toolBar.actions():
            if action.isSeparator():
                self.toolBar.removeAction(action)

        # Reduce toolbar icon size by 10%
        _sz = self.toolBar.iconSize()
        self.toolBar.setIconSize(QSize(int(_sz.width() * 0.9), int(_sz.height() * 0.9)))

        self.actionOpen.setIconText("Open")

        # Equalise toolbar button widths to the widest label
        fm = self.toolBar.fontMetrics()
        toolbarIconSize = self.toolBar.iconSize()
        maxWidth = max(
            (max(toolbarIconSize.width(), fm.boundingRect(action.iconText()).width())
             for action in self.toolBar.actions()
             if not action.isSeparator()),
            default=24
        )
        buttonWidth = maxWidth + 24  # padding on each side
        for action in self.toolBar.actions():
            btn = self.toolBar.widgetForAction(action)
            if btn is not None:
                btn.setFixedWidth(buttonWidth)

        self.actionOpen.triggered.connect(self.openDataFileClicked)
        self.actionClose.triggered.connect(self.closeDataFile)

        self.actionAboutYearbirder.triggered.connect(self.CreateAboutYearbirder)
        self.actionUserGuide.triggered.connect(self.CreateUserGuide)
        self.actionUserGuide.setShortcut(QKeySequence(QKeySequence.StandardKey.HelpContents))

        # macOS intercepts any QAction named "About …" and moves it to the Application
        # menu, so actionAboutYearbirder never stays in the User Guide dropdown.
        # Create a separate action with NoRole so macOS leaves it in place.
        _aboutAction = QAction("About Yearbirder", self)
        _aboutAction.setMenuRole(QAction.MenuRole.NoRole)
        _aboutAction.triggered.connect(self.CreateAboutYearbirder)
        _checkUpdatesAction = QAction("Check for Updates…", self)
        _checkUpdatesAction.setMenuRole(QAction.MenuRole.NoRole)
        _checkUpdatesAction.triggered.connect(self.CheckForUpdates)
        self.menuHelp.addSeparator()
        self.menuHelp.addAction(_checkUpdatesAction)
        self.menuHelp.addAction(_aboutAction)        
        self.actionPreferences.triggered.connect(self.createPreferences)
        self.actionExit.triggered.connect(self.ExitApp)
        
        self.actionShowStandardFilter.triggered.connect(self.showStandardFilter)
        self.actionHideStandardFilter.triggered.connect(self.hideStandardFilter)
        self.actionShowMediaFilter.triggered.connect(self.showMediaFilter)
        self.actionHideMediaFilter.triggered.connect(self.hideMediaFilter)

        self.actionClearAllFilters.triggered.connect(self.clearAllFilters)
        self.actionClearStandardFilter.triggered.connect(self.clearStandardFilter)
        self.actionClearMediaFilter.triggered.connect(self.clearMediaFilter)
        
        self.actionDateTotals.triggered.connect(self.CreateDateTotals)
        self.actionLocationTotals.triggered.connect(self.CreateLocationTotals)
        self.actionCompareLists.triggered.connect(self.CreateCompareLists)
        self.actionTileWindows.triggered.connect(self.TileWindows)
        self.actionCascade.triggered.connect(self.CascadeWindows)
        self.actionCloseAllWindows.triggered.connect(self.CloseAllWindows)
        self.actionSpecies.triggered.connect(self.CreateSpeciesList)
        self.actionChecklists.triggered.connect(self.CreateChecklistsList)
        self.actionLocations.triggered.connect(self.CreateLocationsList)
        self.actionPrint.triggered.connect(self.printMe)
        self.actionCreatePDF.triggered.connect(self.CreatePDF)
        self.actionFamilies.triggered.connect(self.CreateFamilyPieChart)
        self.actionPhotos.triggered.connect(self.createPhotosReport)
        self.actionRecordingsToolbar.triggered.connect(self.createRecordingsBrowser)
        self.actionPhotosByFilter.triggered.connect(self.createPhotosReport)
        self.actionSpeciesGallery.triggered.connect(self.createSpeciesGallery)
        self.actionPhotosSpeciesGallery.triggered.connect(self.createPhotosBySpeciesBarChart)
        self.actionBigReport.triggered.connect(self.CreateBigReport)
        self.actionStats.triggered.connect(self.CreateStats)
        self.actionLocation.triggered.connect(self.CreateLocationReport)
        self.actionRegionalTaxonomy.triggered.connect(self.CreateRegionalTaxonomy)
        self.actionExplorer.triggered.connect(self.CreateExplorer)
        self.actionNotableSightings.triggered.connect(self.CreateNotableSightings)
        self.actionAllSightings.triggered.connect(self.CreateAllSightings)
        self.actionHotspotMap.triggered.connect(self.CreateHotspotMap)
        self.actionBarGraph.triggered.connect(self.CreateBarGraph)
        self.actionTotalChecklists.triggered.connect(self.CreateTotalChecklistsGraph)
        self.actionTotalLocations.triggered.connect(self.CreateTotalLocationsGraph)
        self.actionCumulativeCurve.triggered.connect(self.CreateCumulativeCurve)
        self.actionCumulativeLocations.triggered.connect(self.CreateCumulativeLocationsCurve)
        self.actionCumulativeFamilies.triggered.connect(self.CreateCumulativeFamiliesCurve)
        self.actionHeatmap.triggered.connect(self.CreateHeatmap)
        self.actionAccumulation.triggered.connect(self.CreateAccumulationChart)
        self.actionTopLocations.triggered.connect(self.CreateTopLocations)
        self.actionYTDReport.triggered.connect(self.CreateYTDReport)
        self.actionYTDLocations.triggered.connect(self.CreateYTDLocations)
        self.actionYTDChecklists.triggered.connect(self.CreateYTDChecklists)
        self.actionScatter.triggered.connect(self.CreateScatterChart)
        self.actionPhenology.triggered.connect(self.CreatePhenologyChart)
        self.actionFOY.triggered.connect(self.CreateFOYChart)
        self.actionLOY.triggered.connect(self.CreateLOYChart)
        self.actionLocationScatter.triggered.connect(self.CreateLocationScatterChart)
        self.actionSpeciesScatter.triggered.connect(self.CreateSpeciesScatterChart)
        self.actionLocationChecklistPie.triggered.connect(self.CreateLocationChecklistPieChart)
        self.actionFamilyPie.triggered.connect(self.CreateFamilyPieChart)
        self.actionIndivPie.triggered.connect(self.CreateIndivPieChart)
        self.actionMap.triggered.connect(self.CreateMap)
        self.actionFind.triggered.connect(self.CreateFind)

        self.actionOpenPhotoSettings.triggered.connect(self.openPhotoSettings)
        self.actionClosePhotoSettings.triggered.connect(self.closePhotoSettings)
        self.actionSavePhotoSettings.triggered.connect(self.savePhotoSettings)
        self.actionAddPhotos.triggered.connect(self.addPhotos)
        self.actionAddRecordings.triggered.connect(self.addAudio)
        self.actionManageRecordings.triggered.connect(self.createManageRecordings)
        self.actionBrowseRecordings.triggered.connect(self.createRecordingsBrowser)
        self.actionEditPhotosByFilter.triggered.connect(self.createEditPhotosByFilter)
        self.actionEditPhotosByFilter.setVisible(False)
        self.actionUpdateEXIFDataForAllPhotos.triggered.connect(self.updateEXIFDataForAllPhotos)
        self.actionUpdateEXIFDataForAllPhotos.setVisible(False)
        self.actionUpdateRecordingData.triggered.connect(self.updateRecordingDataForAll)
        self.actionUpdateRecordingData.setVisible(False)
        self.actionRenameMedia.triggered.connect(self.createRenameMedia)
        self.actionRenameMedia.setVisible(False)

        # Rebuild thumbnail cache — created dynamically (no generated-form edit)
        # and inserted into the File menu's media-wide group, just after Rename
        # Media (i.e. immediately before that group's trailing separator).
        self.actionRebuildThumbnailCache = QAction("Rebuild thumbnail cache…", self)
        self.actionRebuildThumbnailCache.setMenuRole(QAction.MenuRole.NoRole)
        self.actionRebuildThumbnailCache.triggered.connect(self.rebuildThumbnailCache)
        self.menuFile.insertAction(self.menuFileMediaSeparator,
                                   self.actionRebuildThumbnailCache)
        self.actionOptimizePhotoSettings.triggered.connect(self.optimizePhotoSettings)
        self.actionOptimizePhotoSettings.setVisible(False)
        
        self.actionUS_States.triggered.connect(self.createChoroplethUSStates)
        self.actionUS_Counties.triggered.connect(self.createChoroplethUSCounties)
        self.actionCanada_Provinces.triggered.connect(self.createChoroplethCanadaProvinces)
        self.actionIndia_States.triggered.connect(self.createChoroplethIndiaStates)
        self.actionGB_Counties.triggered.connect(self.createChoroplethGBCounties)
        self.actionWorld_Countries.triggered.connect(self.createChoroplethWorldCountries)
        self.actionUS_States_Checklists.triggered.connect(self.createChoroplethUSStatesChecklists)
        self.actionUS_Counties_Checklists.triggered.connect(self.createChoroplethUSCountiesChecklists)
        self.actionCanada_Provinces_Checklists.triggered.connect(self.createChoroplethCanadaProvincesChecklists)
        self.actionIndia_States_Checklists.triggered.connect(self.createChoroplethIndiaStatesChecklists)
        self.actionGB_Counties_Checklists.triggered.connect(self.createChoroplethGBCountiesChecklists)
        self.actionWorld_Countries_Checklists.triggered.connect(self.createChoroplethWorldCountriesChecklists)
        self.actionGeolocatedPhotos.triggered.connect(self.createGeolocatedPhotosMap)
        self.actionAnimatedPhotoSequence.triggered.connect(self.createAnimatedPhotoSequenceMap)
        self.actionSlideshow.triggered.connect(self.createSlideshow)
        self.actionYTDPhotos.triggered.connect(self.CreateYTDPhotos)
        self.actionPhotoPie.triggered.connect(self.CreatePhotoPieChart)
        self.actionPhotoBar.triggered.connect(self.CreatePhotoBarChart)
        self.actionPhotoAccumulation.triggered.connect(self.CreatePhotoAccumulationChart)
        self.actionCumulativePhotos.triggered.connect(self.CreateCumulativePhotosChart)
        self.actionRecordingsGallery.triggered.connect(self.createRecordingsSpeciesGallery)
        self.actionRecordingsSpeciesGallery.triggered.connect(self.createRecordingsBySpeciesBarChart)
        self.actionGeolocatedRecordings.triggered.connect(self.createGeolocatedRecordingsMap)
        self.actionAnimatedRecordingSequenceMap.triggered.connect(self.createAnimatedRecordingSequenceMap)
        self.actionYTDRecordings.triggered.connect(self.CreateYTDRecordings)
        self.actionRecordingsPie.triggered.connect(self.CreateRecordingsPieChart)
        self.actionTotalRecordings.triggered.connect(self.CreateTotalRecordingsChart)
        self.actionRecordingsAccumulation.triggered.connect(self.CreateRecordingsAccumulationChart)
        self.actionCumulativeRecordings.triggered.connect(self.CreateCumulativeRecordingsChart)
        self.actionLifeListMap.triggered.connect(self.createLifeListMap)
        self.actionFirstSightingsMap.triggered.connect(self.createFirstSightingsMap)
        self.actionEffortMap.triggered.connect(self.createEffortMap)
        self.actionEffortMapByChecklists.triggered.connect(self.createEffortMapByChecklists)
        self.actionSpeciesTotalMap.triggered.connect(self.createSpeciesTotalMap)
        self.actionIndividualsTotalMap.triggered.connect(self.createIndividualsTotalMap)
        self.actionNotableMap.triggered.connect(self.createNotableMap)
        
        self.cboStartSeasonalRangeMonth.addItems(["Jan",  "Feb",  "Mar",  "Apr",  "May", "Jun",  "Jul",  "Aug",  "Sep",  "Oct",  "Nov",  "Dec"])
        self.cboEndSeasonalRangeMonth.addItems(["Jan",  "Feb",  "Mar",  "Apr",  "May", "Jun",  "Jul",  "Aug",  "Sep",  "Oct",  "Nov",  "Dec"])
        for d in range(1,  32):
            self.cboStartSeasonalRangeDate.addItem(str(d))
            self.cboEndSeasonalRangeDate.addItem(str(d))
        self.cboDateOptions.addItems(["No Date Filter",  "Use Calendars Below",  "This Year",  "Last Year",  "This Month",  "This Week (M-Su)",  "Today",  "Yesterday", "Last Weekend", "Select Year"])
        self.cboSeasonalRangeOptions.addItems([
            "No Seasonal Range",  
            "Use Range Below",  
            "Spring",  
            "Summer",  
            "Fall",  
            "Winter",  
            "This Month", 
            "Year to Date", 
            "Remainder of Year",
            "January",  
            "February",  
            "March",  
            "April",  
            "May", 
            "June",  
            "July",  
            "August",  
            "September",  
            "October",  
            "November",
            "December"
            ])                    
        self.cboRegions.currentIndexChanged.connect(self.ComboRegionsChanged)
        self.cboCountries.currentIndexChanged.connect(self.ComboCountriesChanged)
        self.cboStates.currentIndexChanged.connect(self.ComboStatesChanged)
        self.cboCounties.currentIndexChanged.connect(self.ComboCountiesChanged)
        self.cboLocations.currentIndexChanged.connect(self.ComboLocationsChanged)
        self.btnMyCounty.clicked.connect(self.applyMyCounty)
        self.btnMyPatch.clicked.connect(self.applyMyPatch)
        self.cboOrders.currentIndexChanged.connect(self.ComboOrdersChanged)
        self.cboFamilies.currentIndexChanged.connect(self.ComboFamiliesChanged)
        self.cboSpecies.currentIndexChanged.connect(self.ComboSpeciesChanged)
        self.txtCommonNameSearch.textChanged.connect(self.textCommonNameSearchChanged)
        self.cboDateOptions.currentIndexChanged.connect(self.ComboDateOptionsChanged)
        self.cboYear.currentIndexChanged.connect(self.ComboYearChanged)
        self.cboSeasonalRangeOptions.currentIndexChanged.connect(self.ComboSeasonalRangeOptionsChanged)
        self.calStartDate.dateChanged.connect(self.CalendarClicked)
        self.calEndDate.dateChanged.connect(self.CalendarClicked)
        self.cboStartSeasonalRangeMonth.currentIndexChanged.connect(self.SeasonalRangeClicked)
        self.cboStartSeasonalRangeDate.currentIndexChanged.connect(self.SeasonalRangeClicked)
        self.cboEndSeasonalRangeMonth.currentIndexChanged.connect(self.SeasonalRangeClicked)
        self.cboEndSeasonalRangeDate.currentIndexChanged.connect(self.SeasonalRangeClicked)
        self.fillingLocationComboBoxesFlag = False
        self.calStartDate.setDate(datetime.datetime.now())
        self.calEndDate.setDate(datetime.datetime.now())

        # ── Standard Filter tooltips ──────────────────────────────────────────
        self.cboRegions.setToolTip(
            "Filter by broad geographic region (e.g., ABA Area, Europe).\n"
            "Narrows the Country, State, County, and Location lists below.")
        self.cboCountries.setToolTip(
            "Filter by country.\n"
            "Narrows the State, County, and Location lists below.")
        self.cboStates.setToolTip(
            "Filter by state or province.\n"
            "Narrows the County and Location lists below.")
        self.cboCounties.setToolTip(
            "Filter by county or equivalent administrative area.\n"
            "Narrows the Location list below.")
        self.cboLocations.setToolTip("Filter by a specific named eBird location.")
        self.cboOrders.setToolTip(
            "Filter by taxonomic order.\n"
            "Narrows the Family and Species lists below.")
        self.cboFamilies.setToolTip(
            "Filter by taxonomic family.\n"
            "Narrows the Species list below.")
        self.cboSpecies.setToolTip("Filter by species.")
        self.txtCommonNameSearch.setToolTip(
            "Filter by a word or phrase in the common name or subspecies name.\n"
            "Use s: prefix to search scientific names instead (e.g., s:Buteo).")
        self.cboDateOptions.setToolTip(
            "Choose how to filter by date: use the calendars below, select a\n"
            "preset (Today, This Year, etc.), or apply no date filter.")
        self.cboYear.setToolTip("Filter to a single year.")
        self.calStartDate.setToolTip("Start of the date range.")
        self.calEndDate.setToolTip("End of the date range.")
        self.cboSeasonalRangeOptions.setToolTip(
            "Filter by season or a recurring month-and-day range, regardless\n"
            "of year. Use this to find all your April sightings, for example.")
        self.cboStartSeasonalRangeMonth.setToolTip("Start month of the seasonal range.")
        self.cboStartSeasonalRangeDate.setToolTip("Start day of the seasonal range.")
        self.cboEndSeasonalRangeMonth.setToolTip("End month of the seasonal range.")
        self.cboEndSeasonalRangeDate.setToolTip("End day of the seasonal range.")

        self.cboStartRatingRange.addItem("All")
        self.cboStartRatingRange.insertSeparator(1)
        self.cboStartRatingRange.addItems(["0", "1", "2", "3", "4", "5"])
        self.cboEndRatingRange.addItem("All")
        self.cboEndRatingRange.insertSeparator(1)
        self.cboEndRatingRange.addItems(["0", "1", "2", "3", "4", "5"])
        self.cboStartRatingRange.currentIndexChanged.connect(self.ComboStartRatingRangeChanged)
        self.cboEndRatingRange.currentIndexChanged.connect(self.ComboEndRatingRangeChanged)
        self.cboSpeciesHasPhoto.addItem("All")
        self.cboSpeciesHasPhoto.insertSeparator(1)
        self.cboSpeciesHasPhoto.addItems(["Photographed", "Not photographed"])
        self.cboSpeciesHasPhoto.currentIndexChanged.connect(self.ComboSpeciesHasPhotosChanged)
        self.cboCamera.currentIndexChanged.connect(self.ComboCameraChanged)
        self.cboLens.currentIndexChanged.connect(self.ComboLensChanged)
        self.cboStartShutterSpeedRange.currentIndexChanged.connect(self.ComboStartShutterSpeedChanged)
        self.cboEndShutterSpeedRange.currentIndexChanged.connect(self.ComboEndShutterSpeedChanged)
        self.cboStartApertureRange.currentIndexChanged.connect(self.ComboStartApertureChanged)
        self.cboEndApertureRange.currentIndexChanged.connect(self.ComboEndApertureChanged)
        self.cboStartFocalLengthRange.currentIndexChanged.connect(self.ComboStartFocalLengthChanged)
        self.cboEndFocalLengthRange.currentIndexChanged.connect(self.ComboEndFocalLengthChanged)
        self.cboStartIsoRange.currentIndexChanged.connect(self.ComboStartIsoChanged)
        self.cboEndIsoRange.currentIndexChanged.connect(self.ComboEndIsoChanged)

        # Static audio filter combos (items don't depend on catalog contents)
        self.cboStartRecordingsRatingRange.addItem("All")
        self.cboStartRecordingsRatingRange.insertSeparator(1)
        self.cboStartRecordingsRatingRange.addItems(["0", "1", "2", "3", "4", "5"])
        self.cboEndRecordingsRatingRange.addItem("All")
        self.cboEndRecordingsRatingRange.insertSeparator(1)
        self.cboEndRecordingsRatingRange.addItems(["0", "1", "2", "3", "4", "5"])
        self.cboSpeciesHasRecording.addItem("All")
        self.cboSpeciesHasRecording.insertSeparator(1)
        self.cboSpeciesHasRecording.addItems(["Recorded", "Not recorded"])
        self.cboChannels.addItem("All")
        self.cboChannels.insertSeparator(1)
        self.cboChannels.addItems(["Mono", "Stereo"])

        self.cboStartRecordingsRatingRange.currentIndexChanged.connect(self.ComboStartRecordingsRatingRangeChanged)
        self.cboEndRecordingsRatingRange.currentIndexChanged.connect(self.ComboEndRecordingsRatingRangeChanged)
        self.cboSpeciesHasRecording.currentIndexChanged.connect(self.ComboSpeciesHasRecordingChanged)
        self.cboChannels.currentIndexChanged.connect(self.ComboChannelsChanged)
        self.cboStartRecordingsDurationRange.currentIndexChanged.connect(self.ComboStartRecordingsDurationChanged)
        self.cboEndRecordingsDurationRange.currentIndexChanged.connect(self.ComboEndRecordingsDurationChanged)
        self.cboStartRecordingsSampleRateRange.currentIndexChanged.connect(self.ComboStartRecordingsSampleRateChanged)
        self.cboEndRecordingsSampleRateRange.currentIndexChanged.connect(self.ComboEndRecordingsSampleRateChanged)
        self.cboRecordingsDevice.currentIndexChanged.connect(self.ComboRecordingsDeviceChanged)
        self._bitDepthChecks = []   # runtime QCheckBoxes, one per catalog bit depth

        # Clicking anywhere on the section header row toggles the section
        self.frmPhotoHeader.mousePressEvent = lambda e: self._togglePhotoSection()
        self.frmRecordingsHeader.mousePressEvent = lambda e: self._toggleRecordingsSection()
        
        self.lblSlider = QLabel(self.statusBar)
        self.lblSlider.setText("Display Size")
        self.lblSlider.setVisible(False)
        self.sldFontSize = QSlider(self.statusBar)
        self.sldFontSize.setSingleStep(10)
        self.sldFontSize.setProperty("value", 50)
        self.sldFontSize.setOrientation(Qt.Horizontal)
        self.sldFontSize.setObjectName("sldFontSize")
        self.sldFontSize.valueChanged.connect(self.ScaleDisplay)
        self.sldFontSize.setVisible(False)
        self.lblStatusBarMessage = QLabel(self.statusBar)
        self.lblStatusBarMessage.setText("")
        self.lblStatusBarMessage.setVisible(False)
        # self.statusBar.addWidget(self.lblSlider)
        # self.statusBar.addWidget(self.sldFontSize)
        self.statusBar.addWidget(self.lblStatusBarMessage, 1)
        self.statusBar.hide()  # status bar unused; kept hidden
        
        self.dckMediaFilter.setMinimumWidth(235)
        self.dckFilter.setMinimumWidth(215)

        self.dckFilter.visibilityChanged.connect(
            lambda v: (self.actionShowStandardFilter.setVisible(not v),
                       self.actionHideStandardFilter.setVisible(v)))
        self.dckMediaFilter.visibilityChanged.connect(
            lambda v: (self.actionShowMediaFilter.setVisible(not v),
                       self.actionHideMediaFilter.setVisible(v)))
        
        self.setWindowTitle("Yearbirder v. " + self.versionNumber)

        self.HideMainWindowOptions()
        
        self.setStyleSheet(code_Stylesheet.stylesheetBase)
        self.mdiArea.setBackground(code_Stylesheet.mdiAreaColor)

        self.ScaleDisplay()

        self.progressOverlay = _ProgressOverlay(self)
        # The window is shown (showMaximized) and the eBird file is loaded
        # (processPreferences) from main() AFTER the event loop starts — not here.
        # Running that heavy synchronous load inside __init__, before app.exec(),
        # made the maximized window briefly drop and re-assert on Windows (a
        # "flash of the desktop").  Deferring it lets the window fully realise
        # under the running event loop first.

        self.subWindowFocusOrder = []
        self._windowBeingClosed = None
        self.mdiArea.subWindowActivated.connect(self.onSubWindowActivated)

        self._initFontCanary()

        QApplication.processEvents()


    # ── Font-engine canary ────────────────────────────────────────────────
    # form_Individual's detail labels intermittently render with inflated
    # advances for digits/hyphen/space ("spread" text) after media windows
    # have been used.  A canary event captured 2026-07-11 shows digits AND the
    # space jumping to a uniform em-width (full-width forms — i.e. served by a
    # CJK-style fallback font) while letters shift by exactly -1px (a slightly
    # different Latin face): the process's FONT RESOLUTION state changed
    # mid-session, and every font engine REBUILT after that resolves wrong.
    # Engines held by live widgets keep their original (correct) resolution;
    # Qt's font cache evicts idle engines on an internal timer, which is why
    # windows break "randomly"/while idle rather than at the corrupting moment.
    # Until the corruptor is identified, this canary:
    #   (a) records each monitored font's per-glyph advances and resolved
    #       family at startup,
    #   (b) polls every second and logs a timestamped per-glyph diff, the
    #       resolved-family change, the font-database family count, and the
    #       open windows to ~/Yearbirder_FontCanary.log the moment anything
    #       changes — correlating the corruption with what the app was doing,
    #   (c) serves substituteFont(): a known-good replacement font (explicit
    #       family pin), which form_Individual uses to self-heal.

    _CANARY_GLYPHS = "0123456789-: ()/.ABLNWabcdeghilmnorstuwy,;"

    def _canaryAdvances(self, font):
        fm = QFontMetrics(font)
        return [fm.horizontalAdvance(ch) for ch in self._CANARY_GLYPHS]

    def _canaryFont(self, pointSizeF, family=None):
        f = QFont(family if family is not None else YBFont)
        f.setPointSizeF(pointSizeF)
        return f

    # Candidate explicit families for pinning/self-heal.  The startup-resolved
    # family is prepended at runtime; these are public, always-present faces.
    _CANARY_PIN_CANDIDATES = ("Helvetica Neue", "Helvetica", "Arial")

    def _initFontCanary(self):
        # The detail-label font (fontSize+1) is the one that visibly breaks;
        # also watch the base UI font, the platform default, and the spectro
        # axis font to learn how widely each corruption event spreads.
        self._canarySizes = sorted({float(self.fontSize),
                                    float(self.fontSize + 1), 13.0, 9.0})
        self._canaryBaseline = {}
        self._canaryFamily = {}
        for s in self._canarySizes:
            f = self._canaryFont(s)
            self._canaryBaseline[s] = self._canaryAdvances(f)
            self._canaryFamily[s] = QFontInfo(f).family()
        # Baselines for the explicit-family pin candidates, captured while the
        # font database is healthy: at each corruption event we re-probe these
        # and log whether explicit-name matching survived the rebuild — the
        # data that decides whether pinning YBFont app-wide is a valid fix.
        self._canaryPinBaseline = {}
        for fam in ((self._canaryFamily[self._canarySizes[0]],)
                    + self._CANARY_PIN_CANDIDATES):
            f = self._canaryFont(9.0, family=fam)
            self._canaryPinBaseline[fam] = (QFontInfo(f).family(),
                                            self._canaryAdvances(f))
        self._canaryFamilyCount = len(QFontDatabase.families())
        self._canaryCorrupt = set()     # sizes currently known corrupted
        self._canarySubstitute = {}     # original size -> verified-clean QFont
        self._canaryTimer = QTimer(self)
        self._canaryTimer.setInterval(1000)
        self._canaryTimer.timeout.connect(self.checkFontCanary)
        self._canaryTimer.start()

    def _canaryLog(self, msg):
        print(msg)
        try:
            with open(os.path.expanduser("~/Yearbirder_FontCanary.log"),
                      "a", encoding="utf-8") as fh:
                fh.write(msg + "\n")
        except OSError:
            pass

    def checkFontCanary(self):
        """Compare current per-glyph advances against the startup baseline and
        log any change (with resolution context).  Returns the corrupted set."""
        for s in self._canarySizes:
            if s in self._canaryCorrupt:
                continue
            f = self._canaryFont(s)
            now = self._canaryAdvances(f)
            base = self._canaryBaseline[s]
            if now != base:
                self._canaryCorrupt.add(s)
                diffs = ["%r %d->%d" % (ch, b, n)
                         for ch, b, n in zip(self._CANARY_GLYPHS, base, now)
                         if b != n]
                stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                famNow = QFontInfo(f).family()
                famCountNow = len(QFontDatabase.families())
                windows = [w.windowTitle() for w in self.mdiArea.subWindowList()]
                # Probe the explicit-family pin candidates under the broken
                # database: whichever still resolves and measures as at
                # startup is a proven-safe family to pin YBFont to.
                pins = []
                for fam, (baseFam, baseAdv) in self._canaryPinBaseline.items():
                    pf = self._canaryFont(9.0, family=fam)
                    ok = (QFontInfo(pf).family() == baseFam
                          and self._canaryAdvances(pf) == baseAdv)
                    pins.append("%r %s" % (fam, "OK" if ok else
                                           "BROKEN(->%r)" % QFontInfo(pf).family()))
                self._canaryLog(
                    "FONT ENGINE CORRUPTED  %s  %gpt\n"
                    "  resolved family: %r -> %r\n"
                    "  font-db families: %d -> %d\n"
                    "  explicit pins: %s\n"
                    "  open windows: %s\n"
                    "  glyphs: %s"
                    % (stamp, s,
                       self._canaryFamily[s], famNow,
                       self._canaryFamilyCount, famCountNow,
                       ", ".join(pins),
                       windows, "; ".join(diffs)))
        return self._canaryCorrupt

    def substituteFont(self, pointSize):
        """Return a QFont for pointSize that measures clean.  If the default
        resolution for this size is corrupted, fall back to pinning an explicit
        known-good family (the family the size resolved to at startup, then
        common system faces), verified against the startup baseline.  A fresh
        default-resolved engine can NOT be trusted here: once the process's
        font-resolution state has broken, rebuilt engines resolve wrong too."""
        pointSize = float(pointSize)
        self.checkFontCanary()
        healthy = self._canaryFont(pointSize)
        if pointSize not in self._canaryCorrupt:
            return QFont(healthy)
        cached = self._canarySubstitute.get(pointSize)
        if cached is not None:
            return QFont(cached)
        base = self._canaryBaseline.get(pointSize)
        candidates = [self._canaryFamily.get(pointSize),
                      "Helvetica Neue", "Helvetica", "Arial"]
        for fam in candidates:
            if not fam:
                continue
            f = self._canaryFont(pointSize, family=fam)
            # ±1px per glyph: family pinning can round advances a hair
            # differently; real corruption is full-width digits, far larger.
            if base is not None and all(
                    abs(n - b) <= 1 for n, b in zip(self._canaryAdvances(f), base)):
                self._canaryLog("font self-heal: %gpt pinned to family %r"
                                % (pointSize, fam))
                self._canarySubstitute[pointSize] = QFont(f)
                return f
        return healthy    # nothing clean found; give up gracefully


    def closeEvent(self, event):
        # Compact/save the media catalog if there are pending changes (matches the
        # File → Exit path), then remove the custom toolbar style before Qt teardown
        # so PySide6's shutdown cannot call back into a half-destroyed proxy style.
        self.checkIfPhotoDataNeedSaving()
        self.toolBar.setStyle(None)
        event.accept()


    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'progressOverlay') and self.progressOverlay.isVisible():
            self.progressOverlay._reposition()

    def eventFilter(self, obj, event):
        # Detect when a tracked subwindow is about to close so we can
        # restore focus to the correct window afterward.
        if event.type() == QEvent.Close and obj in self.subWindowFocusOrder:
            self._windowBeingClosed = obj
            QTimer.singleShot(0, self.restorePreviousFocus)
        return False


    def onSubWindowActivated(self, window):
        # Property-tag the focused child so the stylesheet can draw its border
        # brighter (QSS has no reliable :active state on QMdiSubWindow); the
        # borders make overlapping dark windows visually separable.
        for w in self.mdiArea.subWindowList():
            is_active = (w is window)
            if bool(w.property("activeWin")) != is_active:
                w.setProperty("activeWin", is_active)
                w.style().unpolish(w)
                w.style().polish(w)
                w.update()

        if window is None:
            return
        # Install our event filter the first time each subwindow is activated.
        if not getattr(window, '_focusFilterInstalled', False):
            window.installEventFilter(self)
            window._focusFilterInstalled = True
        # Ignore Qt's automatic re-activation that fires while a close is in progress.
        if self._windowBeingClosed is not None:
            return
        if window in self.subWindowFocusOrder:
            self.subWindowFocusOrder.remove(window)
        self.subWindowFocusOrder.append(window)


    def restorePreviousFocus(self):
        openWindows = set(self.mdiArea.subWindowList())
        self.subWindowFocusOrder = [w for w in self.subWindowFocusOrder
                                    if w in openWindows]
        self._windowBeingClosed = None
        if self.subWindowFocusOrder:
            self.mdiArea.setActiveSubWindow(self.subWindowFocusOrder[-1])


    def processPreferences(self):

        # Read preferences directly on the main thread
        self.db.readPreferences()

        # Install the calibrated per-device output-latency map into the shared
        # player class so every recordings window compensates its cursor.
        import code_Audio
        code_Audio.PcmAudioPlayer.setLatencyMap(self.db.audioLatencyByDevice)

        # If a startup folder is defined and valid, open it
        if self.db.startupFolder and os.path.isdir(self.db.startupFolder):
            self.OpenDataFile(self.db.startupFolder)

            if self.db.eBirdFileOpenFlag:
                self._autoOpenDefaultCatalog()

        # Now that preferences are processed, continue with UI updates
        self.finishedProcessingPreferences()
        

    def _updateMediaMenuVisibility(self):
        """Show the Photos menu only when the open media catalog actually contains
        photos, and the Recordings menu only when it contains recordings.  Both
        hide when no catalog is open.  (File-menu items like Add photos / Add
        recordings stay available whenever an eBird data file is open, so you can
        add the first item of a kind — but Manage recordings needs an existing
        recording to manage, so it tracks the same condition as the Recordings
        menu.)"""
        has_catalog = self.db.photoDataFileOpenFlag
        self.menuPhotos.menuAction().setVisible(has_catalog and self.db.hasPhotos())
        self.menuRecordings.menuAction().setVisible(has_catalog and self.db.hasRecordings())
        self.actionManageRecordings.setVisible(has_catalog and self.db.hasRecordings())
        # Toolbar Recordings button tracks the same condition as the menu.
        self.actionRecordingsToolbar.setVisible(has_catalog and self.db.hasRecordings())

    def finishedProcessingPreferences(self):
        self.updateMyLocationButtons()

        if self.db.eBirdFileOpenFlag == True:
            self.fillingLocationComboBoxesFlag = True
            self.FillMainComboBoxes()
            self.fillingLocationComboBoxesFlag = False
            self.showStandardFilter()
            self.CreateSpeciesList()
            self.actionClose.setVisible(True)
            self.actionOpenPhotoSettings.setVisible(True)
            self.actionAddPhotos.setVisible(True)
            self.actionAddRecordings.setVisible(True)
            self.actionRebuildThumbnailCache.setVisible(True)
            # Photos/Recordings menus appear only if the catalog has that media.
            self._updateMediaMenuVisibility()

            #show photo filter if an ebird file has been read and a photo file has been opened
            if self.db.photoDataFileOpenFlag == True:
                self.fillPhotoComboBoxes()
                self.fillRecordingsComboBoxes()
                self.showMediaFilter()
                self._showPhotoCatalogMenuItems()
                self.actionGeolocatedPhotos.setVisible(True)
                self.actionGeolocatedPhotosSeparator.setVisible(True)
                self.actionAnimatedPhotoSequence.setVisible(True)
                self.actionSlideshow.setVisible(True)
                self.actionYTDPhotos.setVisible(True)
                self.actionPhotoPie.setVisible(True)
                self.actionPhotoBar.setVisible(True)
                self.actionPhotoAccumulation.setVisible(True)
                self.actionCumulativePhotos.setVisible(True)
                self.actionEditPhotosByFilter.setVisible(True)
                self.actionUpdateEXIFDataForAllPhotos.setVisible(True)
                self.actionUpdateRecordingData.setVisible(True)
                self.actionRenameMedia.setVisible(True)
                self.actionOptimizePhotoSettings.setVisible(True)

            self.showFileDataMessage()
            
            
          
    def ScaleDisplay(self):
        
        
        self.scaleFactor = self.sldFontSize.value()/50
        if self.scaleFactor > 1:
            self.scaleFactor = 1 + modf(self.scaleFactor)[0] * 3
        if self.scaleFactor < 1:
            self.scaleFactor = (1 + self.scaleFactor) / 2
        self.fontSize = floor(11 * self.scaleFactor)
        MainWindow.fontSize = self.fontSize
        MainWindow.scaleFactor = self.scaleFactor
        MainWindow.rowHeight = int(QFontMetrics(QFont(YBFont, MainWindow.fontSize)).boundingRect("2222-22-22").height() * 1.1)
        
        self.menuBar.setFont(QFont(YBFont, self.fontSize))
        for _menu in self.menuBar.findChildren(QMenu):
            _menu.setFont(QFont(YBFont, self.fontSize))
                        
        for a in self.toolBar.actions():
            a.setFont(QFont(YBFont, self.fontSize))                    
                
        # scale the standard and photo filter docks

        filterFrameChildren = (
            self.frmFilter.children() +
            self.frmPhotoSection.children() +
            self.frmRecordingsSection.children() +
            self.frmStartSeasonalRange.children() +
            self.frmEndSeasonalRange.children() +
            self.frmShutterSpeedRange.children() +
            self.frmApertureRange.children() +
            self.frmIsoRange.children() +
            self.frmFocalLengthRange.children() +
            self.frmRatingRange.children() +
            self.frmRecordingsRatingRange.children() +
            self.frmRecordingsDurationRange.children() +
            self.frmRecordingsSampleRateRange.children()
            )

        for w in filterFrameChildren:

            if w.objectName()[0:3] == "cbo":
                # Height is deliberately NOT forced: the app stylesheet's
                # QComboBox padding/min-height is the single sizing authority.
                # The old 2×-line-height minimums (a vestige of the abandoned
                # font-size slider) ballooned combos on Windows, where Segoe UI
                # line metrics run much taller than the macOS system font.
                w.setFont(QFont(YBFont, self.fontSize))
                metrics = w.fontMetrics()
                cboText = w.currentText()
                if cboText == "":
                    cboText = "Dummy Text"
                itemTextWidth = metrics.boundingRect(cboText).width()
                w.setMinimumWidth(floor(1.1 * itemTextWidth))

            if w.objectName()[0:3] == "lbl":
                _boldFont = QFont(YBFont, self.fontSize)
                _boldFont.setBold(True)
                w.setFont(_boldFont)
                metrics = w.fontMetrics()
                labelText = w.text()
                itemTextWidth = metrics.boundingRect(labelText).width()
                itemTextHeight = metrics.boundingRect(labelText).height()
                w.setMinimumWidth(floor(itemTextWidth))
                w.setMinimumHeight(floor(itemTextHeight))
                w.setMaximumHeight(floor(itemTextHeight))
                w.resize(itemTextHeight, itemTextWidth)

            if w.objectName()[0:3] == "cal":
                w.setFont(QFont(YBFont, self.fontSize))
                metrics = w.fontMetrics()
                startDate = (
                            str(self.calStartDate.date().year())
                            + "-"
                            + str(self.calStartDate.date().month())
                            + "-"
                            + str(self.calStartDate.date().day()))
                itemTextWidth = metrics.boundingRect(startDate).width()
                itemTextHeight = metrics.boundingRect(startDate).height()
                w.setMinimumWidth(floor(2 * itemTextWidth))
                w.setMinimumHeight(floor(2 * itemTextHeight))
                w.setMaximumHeight(floor(2 * itemTextHeight))
                w.resize(int(2 * itemTextHeight), int(2 * itemTextWidth))

        for w in (
            self.frmStartSeasonalRange,
            self.frmEndSeasonalRange,
            self.frmRatingRange,
            self.frmShutterSpeedRange,
            self.frmApertureRange,
            self.frmIsoRange,
            self.frmFocalLengthRange,
            self.frmRecordingsRatingRange,
            self.frmRecordingsDurationRange,
            self.frmRecordingsSampleRateRange,
            ):
            w.setMinimumWidth(floor(2 * itemTextWidth))


        self.scrMediaFilter.setMinimumHeight(0)
        self.scrMediaFilter.setMinimumWidth(int(2.5 * itemTextWidth))
        self.scrFilter.setMinimumWidth(int(2.5 * itemTextWidth))

        # Scale section header labels (excluded from filterFrameChildren to avoid
        # polluting itemTextWidth; scaled explicitly here instead).
        # Arrow rendered at 2x label size via inline HTML span.
        _sectionFont = QFont(YBFont, self.fontSize)
        _sectionFont.setBold(True)
        _arrowPt = self.fontSize * 2
        self.lblPhotoSection.setFont(_sectionFont)
        self.lblRecordingsSection.setFont(_sectionFont)
        _pArrow = "▸" if self.frmPhotoSection.isHidden() else "▾"
        _aArrow = "▸" if self.frmRecordingsSection.isHidden() else "▾"
        self.lblPhotoSection.setText(
            f"Photos  <span style='font-size:{_arrowPt}pt; vertical-align:middle'>{_pArrow}</span>")
        self.lblRecordingsSection.setText(
            f"Recordings  <span style='font-size:{_arrowPt}pt; vertical-align:middle'>{_aArrow}</span>")

        # scale open children windows
        for w in self.mdiArea.subWindowList():        
            w.scaleMe()
            

    def showFileDataMessage(self):
        self.CreateStatsOnLoad()
        

    def clearAllFilters(self):
        self.clearStandardFilter()
        self.clearMediaFilter()
    
    
    def clearStandardFilter(self):
        self.cboRegions.setCurrentIndex(0)
        self.cboCountries.setCurrentIndex(0)
        self.cboStates.setCurrentIndex(0)
        self.cboCounties.setCurrentIndex(0)
        self.cboLocations.setCurrentIndex(0)
        self.cboOrders.setCurrentIndex(0)
        self.cboFamilies.setCurrentIndex(0)
        self.cboSpecies.setCurrentIndex(0)
        self.calStartDate.setDate(datetime.datetime.now())
        self.calEndDate.setDate(datetime.datetime.now())
        self.cboDateOptions.setCurrentIndex(0)
        self.cboYear.setCurrentIndex(0)
        self.cboYear.setVisible(False)
        self.cboYear.setStyleSheet("")
        self.cboSeasonalRangeOptions.setCurrentIndex(0)
        self.txtCommonNameSearch.setText("")

        # Drop keyboard focus from whichever filter widget the user last touched,
        # so the blue :focus border (e.g. around Date Options) doesn't linger on a
        # now-cleared control.
        for w in (self.cboRegions, self.cboCountries, self.cboStates,
                  self.cboCounties, self.cboLocations, self.cboOrders,
                  self.cboFamilies, self.cboSpecies, self.cboDateOptions,
                  self.cboYear, self.cboSeasonalRangeOptions,
                  self.calStartDate, self.calEndDate, self.txtCommonNameSearch):
            w.clearFocus()


    def clearMediaFilter(self):
        self.cboStartRatingRange.setCurrentIndex(0)
        self.cboEndRatingRange.setCurrentIndex(0)
        self.cboSpeciesHasPhoto.setCurrentIndex(0)
        self.cboCamera.setCurrentIndex(0)
        self.cboLens.setCurrentIndex(0)
        self.cboStartShutterSpeedRange.setCurrentIndex(0)
        self.cboEndShutterSpeedRange.setCurrentIndex(0)
        self.cboStartApertureRange.setCurrentIndex(0)
        self.cboEndApertureRange.setCurrentIndex(0)
        self.cboStartFocalLengthRange.setCurrentIndex(0)
        self.cboEndFocalLengthRange.setCurrentIndex(0)
        self.cboStartIsoRange.setCurrentIndex(0)
        self.cboEndIsoRange.setCurrentIndex(0)
        self.cboStartRecordingsRatingRange.setCurrentIndex(0)
        self.cboEndRecordingsRatingRange.setCurrentIndex(0)
        self.cboSpeciesHasRecording.setCurrentIndex(0)
        self.cboChannels.setCurrentIndex(0)
        self.cboStartRecordingsDurationRange.setCurrentIndex(0)
        self.cboEndRecordingsDurationRange.setCurrentIndex(0)
        self.cboStartRecordingsSampleRateRange.setCurrentIndex(0)
        self.cboEndRecordingsSampleRateRange.setCurrentIndex(0)
        self.cboRecordingsDevice.setCurrentIndex(0)
        for chk in getattr(self, "_bitDepthChecks", []):
            chk.setChecked(False)


    def _warnIfJsonlSkippedLines(self):
        n = self.db.jsonlSkippedLines
        if n > 0:
            QMessageBox.warning(
                self,
                "Media Catalog Warning",
                f"{n} line{'s' if n != 1 else ''} in the media catalog could not "
                f"be read and {'were' if n != 1 else 'was'} skipped.\n\n"
                "The file may be partially corrupted. Consider running "
                "File \u2192 Compact catalog and cache\u2026 to compact and repair it.",
                QMessageBox.StandardButton.Ok,
            )

    def _warnIfCsvSkippedRows(self):
        n = self.db.csvSkippedRows
        if n > 0:
            QMessageBox.warning(
                self,
                "Media Catalog Warning",
                f"{n} row{'s' if n != 1 else ''} in the media catalog could "
                f"not be read due to missing columns and {'were' if n != 1 else 'was'} "
                f"skipped.\n\n"
                "This may indicate an older or incompatible CSV format.",
                QMessageBox.StandardButton.Ok,
            )

    def openPhotoSettings(self, photoDataFile = ""):

        if not self.db.eBirdFileOpenFlag:
            QMessageBox.warning(self, "No eBird Data File Open",
                "Please open an eBird data file first (File → Open), "
                "then open a media catalog.")
            return

        # Block if Manage Photos is open — switching catalogs mid-session would corrupt its state
        for w in self.mdiArea.subWindowList():
            if isinstance(w, code_ManagePhotos.ManagePhotos):
                QMessageBox.warning(self, "Close Manage Photos First",
                    "Please close the Manage Photos window before opening a different media catalog.\n\n"
                    "Having both open at the same time could cause conflicts.")
                return

        # Snapshot the configured default so we can skip the prompt when re-opening it
        prev_default = self.db.photoDataFileDefault

        # If a catalog is already open, confirm the switch
        if self.db.photoDataFileOpenFlag:
            reply = code_Stylesheet.question(self, "Media Catalog Already Open",
                "A media catalog is already open.\n\n"
                "Do you want to close it and open a different one?")
            if reply != QMessageBox.StandardButton.Yes:
                return
            # Compact any pending changes before switching
            self.checkIfPhotoDataNeedSaving()
            self._closePhotoDependentWindows()
            self.db.ClearPhotoSettings()

        # open data file
        initial_dir = os.path.dirname(MainWindow.db.photoDataFile) if MainWindow.db.photoDataFile else ""
        fname = QFileDialog.getOpenFileName(self,"Select Yearbirder Photo Data File", initial_dir,"Yearbirder Photo Data Files (*.jsonl *.csv)")

        # check if user pressed cancel or if we have a file name to open
        if fname[0] == "":
            return

        photoDataFile = fname[0]

        self.db.readPhotoDataFromFile(photoDataFile)
        self._warnIfJsonlSkippedLines()
        self._warnIfCsvSkippedRows()
        self._promptJsonlMigrationIfNeeded()

        # If conversion was declined or the save dialog was cancelled, abort the open
        if self.db.photoDataFile.lower().endswith(".csv"):
            self.db.ClearPhotoSettings()
            QMessageBox.warning(self, "Media Catalog Not Opened",
                "The media catalog was not opened. CSV catalogs must be converted to "
                "Yearbirder's catalog format (.jsonl) before they can be used.\n\n"
                "Open the file again to convert it.")
            return

        # Offer to make this the default catalog if it differs from the previous one.
        # Skip for CSV files — _promptJsonlMigrationIfNeeded already asked.
        if (not photoDataFile.lower().endswith(".csv") and
                os.path.realpath(photoDataFile) != os.path.realpath(prev_default or "")):
            reply = code_Stylesheet.question(self, "Set as Default Catalog?",
                "Would you like Yearbirder to open this media catalog automatically "
                "each time it starts?\n\n" + photoDataFile)
            if reply == QMessageBox.StandardButton.Yes:
                self.db.photoDataFileDefault = photoDataFile
                self.db.writePreferences()

        self.fillPhotoComboBoxes()
        self.fillRecordingsComboBoxes()

        self.showMediaFilter()

        # Photos/Recordings menus appear only if the catalog has that media.
        self._updateMediaMenuVisibility()
        self._showPhotoCatalogMenuItems()
        self.actionGeolocatedPhotos.setVisible(True)
        self.actionGeolocatedPhotosSeparator.setVisible(True)
        self.actionAnimatedPhotoSequence.setVisible(True)
        self.actionSlideshow.setVisible(True)
        self.actionYTDPhotos.setVisible(True)
        self.actionPhotoPie.setVisible(True)
        self.actionPhotoBar.setVisible(True)
        self.actionEditPhotosByFilter.setVisible(True)
        self.actionUpdateEXIFDataForAllPhotos.setVisible(True)
        self.actionUpdateRecordingData.setVisible(True)
        self.actionRenameMedia.setVisible(True)
        self.actionOptimizePhotoSettings.setVisible(True)

        self.CreateStatsOnLoad()


    def _autoOpenDefaultCatalog(self):
        default_catalog = self.db.photoDataFileDefault
        if not default_catalog or not os.path.isfile(default_catalog):
            return

        self.db.readPhotoDataFromFile(default_catalog)
        self._warnIfJsonlSkippedLines()
        self._warnIfCsvSkippedRows()
        self._promptJsonlMigrationIfNeeded()

        if self.db.photoDataFile.lower().endswith(".csv"):
            self.db.ClearPhotoSettings()
            return

        filter = code_Filter.Filter()
        if (self.db.photoRecordsInCatalog > 0
                and not self.db.GetSightingsWithPhotos(filter)):
            QMessageBox.warning(
                self,
                "Media Catalog Mismatch",
                "The photos in the catalog don't match the open eBird data file. "
                "The catalog will be closed.\n\n"
                + default_catalog,
            )
            self.db.ClearPhotoSettings()


    def _showPhotoCatalogMenuItems(self):
        self.actionPhotos.setVisible(True)
        self.actionOpenPhotoSettings.setVisible(True)
        self.actionClosePhotoSettings.setVisible(True)
        self.actionSavePhotoSettings.setVisible(True)
        self.menuFileCatalogSeparator.setVisible(True)
        self.actionEditPhotosByFilter.setVisible(True)
        self.actionUpdateEXIFDataForAllPhotos.setVisible(True)
        self.actionRenameMedia.setVisible(True)
        self.actionOptimizePhotoSettings.setVisible(True)

    def _hidePhotoCatalogMenuItems(self):
        self.actionPhotos.setVisible(False)
        self.actionClosePhotoSettings.setVisible(False)
        self.actionSavePhotoSettings.setVisible(False)
        # menuFileCatalogSeparator stays visible: "Open media catalog..." is
        # always shown, so the separator after it always has something to
        # separate from "Add photos..." below it.
        self.actionEditPhotosByFilter.setVisible(False)
        self.actionUpdateEXIFDataForAllPhotos.setVisible(False)
        self.actionUpdateRecordingData.setVisible(False)
        self.actionRenameMedia.setVisible(False)
        self.actionOptimizePhotoSettings.setVisible(False)

    def closePhotoSettings(self):

        # The media catalog is written to disk continuously, so there is no
        # unsaved state to prompt about — just compact the .jsonl quietly before
        # closing (no "save before closing?" dialog).
        self.checkIfPhotoDataNeedSaving()

        self.clearMediaFilter()
        self.hideMediaFilter()
        self.db.ClearPhotoSettings()

        for w in list(self.mdiArea.subWindowList()):
            if w.objectName() == "frmStats":
                w.close()
        # Catalog is now closed — hide both media menus.
        self._updateMediaMenuVisibility()
        self._hidePhotoCatalogMenuItems()
        self.actionGeolocatedPhotos.setVisible(False)
        self.actionGeolocatedPhotosSeparator.setVisible(False)
        self.actionAnimatedPhotoSequence.setVisible(False)
        self.actionSlideshow.setVisible(False)
        self.actionYTDPhotos.setVisible(False)
        self.actionPhotoPie.setVisible(False)
        self.actionPhotoBar.setVisible(False)
        self.actionPhotoAccumulation.setVisible(False)
        self.actionCumulativePhotos.setVisible(False)


    def addPhotos(self):
        # Abort if no data file is open
        if not MainWindow.db.eBirdFileOpenFlag:
            self.CreateMessageNoFile()
            return

        default_dir = ""
        if MainWindow.db.photoDataFileOpenFlag:
            latest_date = ""
            latest_file = ""
            for s in MainWindow.db.sightingList:
                if "photos" in s and s["date"] >= latest_date:
                    latest_date = s["date"]
                    latest_file = s["photos"][0]["fileName"]
            if latest_file:
                default_dir = os.path.dirname(latest_file)

        photo_paths, _ = QFileDialog.getOpenFileNames(self, 'Select photo files', default_dir, "Jpeg Images (*.jpg *.jpeg)")

        if not photo_paths:
            return

        filter_obj = code_Filter.Filter()
        # realpath normalises both sides so symlinked paths (e.g. ~/Dropbox →
        # ~/Library/CloudStorage/Dropbox on macOS) compare equal regardless of
        # which file-dialog variant produced them.
        photos_already_in_db = {os.path.realpath(p) for p in self.db.GetPhotos(filter_obj)}

        unmatched_photos = [p for p in photo_paths if os.path.realpath(p) not in photos_already_in_db]
        count_photos_not_processed = len(photo_paths) - len(unmatched_photos)

        if count_photos_not_processed > 0:
            new_count = len(unmatched_photos)
            new_str = "1 photo will be added." if new_count == 1 else f"{new_count} photos will be added."
            QMessageBox.information(
                self,
                "Photos",
                f"{count_photos_not_processed} of the selected photos are already in the catalog.\n\n"
                f"{new_str}",
                QMessageBox.StandardButton.Ok
            )

        if unmatched_photos:
            sub = code_ManagePhotos.ManagePhotos()
            sub.mdiParent = self

            sub.scaleMe()
            sub.resizeMe()

            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)

            # Keep the window HIDDEN while its rows build: inserting hundreds
            # of rows into a visible grid forces a relayout+repaint of the
            # whole grid per row (O(N²) for large imports); built hidden it is
            # a single layout pass at reveal.  The main window's gated progress
            # overlay provides feedback whenever the load runs long.
            def _revealManagePhotos():
                sub.show()
                self.mdiArea.setActiveSubWindow(sub)
                sub.raise_()
                sub.setFocus()
            sub.contentReady.connect(_revealManagePhotos)

            QTimer.singleShot(20, lambda: sub.FillPhotosByFiles(unmatched_photos))
        else:
            QMessageBox.information(
                self,
                "Photos",
                "No new photo files were found.",
                QMessageBox.StandardButton.Ok
            )

    def addAudio(self):
        if not MainWindow.db.eBirdFileOpenFlag:
            self.CreateMessageNoFile()
            return

        default_dir = ""
        if MainWindow.db.photoDataFileOpenFlag:
            all_audio = MainWindow.db.GetAudio(code_Filter.Filter())
            if all_audio:
                default_dir = os.path.dirname(all_audio[-1])

        audio_paths, _ = QFileDialog.getOpenFileNames(
            self, 'Select recording files', default_dir, "WAV Audio (*.wav)")

        if not audio_paths:
            return

        already_in_db = {os.path.realpath(a) for a in MainWindow.db.GetAudio(code_Filter.Filter())}
        new_files = [p for p in audio_paths if os.path.realpath(p) not in already_in_db]
        already_count = len(audio_paths) - len(new_files)

        if already_count > 0:
            new_str = "1 file will be added." if len(new_files) == 1 else f"{len(new_files)} files will be added."
            QMessageBox.information(
                self, "Recordings",
                f"{already_count} of the selected files are already in the catalog.\n\n{new_str}",
                QMessageBox.StandardButton.Ok
            )

        if new_files:
            sub = code_ManageRecordings.ManageRecordings()
            sub.mdiParent = self
            sub.scaleMe()
            sub.resizeMe()
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)

            # Keep the window HIDDEN while its rows build (see addPhotos); the
            # gated overlay provides feedback whenever the load runs long.
            def _revealManageRecordings():
                sub.show()
                self.mdiArea.setActiveSubWindow(sub)
                sub.raise_()
                sub.setFocus()
            sub.contentReady.connect(_revealManageRecordings)

            QTimer.singleShot(20, lambda: sub.FillRecordingsByFiles(new_files))
        else:
            QMessageBox.information(
                self, "Recordings",
                "No new recording files were found.",
                QMessageBox.StandardButton.Ok
            )

    def _promptJsonlMigrationIfNeeded(self):
        if self.db.photoDataFile.lower().endswith(".jsonl"):
            return
        if self.db.photoDataFile == "":
            # No catalog at all — plain prompt to create one
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setText(
                "No media catalog is open.\n\n"
                "Please choose a name and location for a media catalog. "
                "Yearbirder will save your photo data there going forward."
            )
            msg.setWindowTitle("Media Catalog")
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()
            self.savePhotoSettings()
        else:
            # CSV file — require explicit conversion; offer a clean cancel path
            msg = QMessageBox(self)
            msg.setWindowTitle("Convert Media Catalog")
            msg.setText(
                "Your media catalog is in the legacy CSV format, which is no longer "
                "supported.\n\n"
                "Choose a location to save the converted catalog (.jsonl). "
                "If you cancel, the catalog will not be opened."
            )
            convert_btn = msg.addButton("Convert…", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("Don't Open",             QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            if msg.clickedButton() is not convert_btn:
                return   # caller must check db.photoDataFile to detect this
            self.savePhotoSettings(is_conversion=True)

        if self.db.photoDataFile.lower().endswith(".jsonl"):
            if code_Stylesheet.question(
                self, "Set as Default?",
                "Would you like to set this as your default media catalog?\n\n"
                + self.db.photoDataFile,
            ) == QMessageBox.StandardButton.Yes:
                self.db.photoDataFileDefault = self.db.photoDataFile
                self.db.writePreferences()


    def savePhotoSettings(self, is_conversion=False):

        photoFileInUse = self.db.photoDataFile
        # suggest .jsonl path even if user currently has a .csv path
        if photoFileInUse.lower().endswith(".csv"):
            photoFileInUse = photoFileInUse[:-4] + ".jsonl"

        if is_conversion:
            dialog_title = "Media Catalog"
            suggested = photoFileInUse
        else:
            datestamp = datetime.datetime.now().strftime("%Y%m%d")
            base, ext = os.path.splitext(photoFileInUse)
            suggested = f"{base}_Backup_{datestamp}{ext}"
            dialog_title = "Backup Media Catalog"

        fname = QFileDialog.getSaveFileName(self, dialog_title, suggested, "Yearbirder Media Catalog (*.jsonl)")

        if fname[0] == "":
            return

        self.db.writePhotoDataToFile(fname[0])
        self.db.photoDataFile = fname[0]
        self.db.photosNeedSaving = False


    def fillPhotoComboBoxes(self):
        
        for w in (
            self.cboCamera, 
            self.cboLens,
            self.cboStartShutterSpeedRange,
            self.cboEndShutterSpeedRange,
            self.cboStartApertureRange,
            self.cboEndApertureRange,
            self.cboStartIsoRange,
            self.cboEndIsoRange,
            self.cboStartFocalLengthRange,
            self.cboEndFocalLengthRange
            ):
            w.clear()
            
            if w == self.cboCamera:
                w.addItem("All Cameras")
                w.insertSeparator(1)
                w.addItems(self.db.cameraList)

            if w == self.cboLens:
                w.addItem("All Lenses")
                w.insertSeparator(1)
                w.addItems(self.db.lensList)

            if w == self.cboStartShutterSpeedRange:
                w.addItem("All")
                w.insertSeparator(1)
                w.addItems(self.db.shutterSpeedList)

            if w == self.cboEndShutterSpeedRange:
                w.addItem("All")
                w.insertSeparator(1)
                w.addItems(self.db.shutterSpeedList)

            if w == self.cboStartApertureRange:
                w.addItem("All")
                w.insertSeparator(1)
                w.addItems(self.db.apertureList)

            if w == self.cboEndApertureRange:
                w.addItem("All")
                w.insertSeparator(1)
                w.addItems(self.db.apertureList)

            if w == self.cboStartIsoRange:
                w.addItem("All")
                w.insertSeparator(1)
                w.addItems(self.db.isoList)

            if w == self.cboEndIsoRange:
                w.addItem("All")
                w.insertSeparator(1)
                w.addItems(self.db.isoList)

            if w == self.cboStartFocalLengthRange:
                w.addItem("All")
                w.insertSeparator(1)
                w.addItems(self.db.focalLengthList)

            if w == self.cboEndFocalLengthRange:
                w.addItem("All")
                w.insertSeparator(1)
                w.addItems(self.db.focalLengthList)
                
            w.setCurrentIndex(0)
        
        self.cboStartRatingRange.setCurrentIndex(0)
        self.cboEndRatingRange.setCurrentIndex(0)


    def fillRecordingsComboBoxes(self):
        # Populate only the catalog-derived comboboxes (duration, sample rate,
        # bit depth); static items (rating, channels, has-recording) are set once
        # in __init__.
        # Block signals while repopulating: clearing a combo drops its index to
        # -1, which would otherwise fire the range-coupling handlers and leave the
        # paired combo blank and falsely highlighted.  Reset to "All" + clear any
        # stale highlight from a prior selection.
        for w in (self.cboStartRecordingsDurationRange, self.cboEndRecordingsDurationRange):
            w.blockSignals(True)
            w.clear()
            w.addItem("All")
            w.insertSeparator(1)
            w.addItems(self.db.durationList)
            w.setCurrentIndex(0)
            w.blockSignals(False)
            self.unhighlightFilterElement(w)

        for w in (self.cboStartRecordingsSampleRateRange, self.cboEndRecordingsSampleRateRange):
            w.blockSignals(True)
            w.clear()
            w.addItem("All")
            w.insertSeparator(1)
            w.addItems(self.db.sampleRateList)
            w.setCurrentIndex(0)
            w.blockSignals(False)
            self.unhighlightFilterElement(w)

        # Bit-depth multi-select: one checkbox per distinct depth in the catalog.
        for chk in getattr(self, "_bitDepthChecks", []):
            self._recordingsBitDepthLayout.removeWidget(chk)
            chk.deleteLater()
        self._bitDepthChecks = []
        chkFont = QFont(YBFont, self.fontSize)
        for depth in self.db.bitDepthList:
            chk = QCheckBox(depth, self.frmRecordingsBitDepth)
            chk.setFont(chkFont)
            chk.toggled.connect(self._onBitDepthToggled)
            self._recordingsBitDepthLayout.addWidget(chk)
            self._bitDepthChecks.append(chk)
        self.frmRecordingsBitDepth.setVisible(bool(self._bitDepthChecks))
        self.lblRecordingsBitDepth.setVisible(bool(self._bitDepthChecks))

        # Recording-device combo: catalog-derived, single-select.
        self.cboRecordingsDevice.blockSignals(True)
        self.cboRecordingsDevice.clear()
        self.cboRecordingsDevice.addItem("All")
        self.cboRecordingsDevice.insertSeparator(1)
        self.cboRecordingsDevice.addItems(self.db.deviceList)
        self.cboRecordingsDevice.setCurrentIndex(0)
        self.cboRecordingsDevice.blockSignals(False)
        self.unhighlightFilterElement(self.cboRecordingsDevice)
        self.cboRecordingsDevice.setVisible(bool(self.db.deviceList))
        self.lblRecordingsDevice.setVisible(bool(self.db.deviceList))


    def _togglePhotoSection(self):
        visible = self.frmPhotoSection.isVisible()
        _arrowPt = self.fontSize * 2
        _arrow = "▸" if visible else "▾"
        self.dckMediaFilter.setUpdatesEnabled(False)
        self.frmPhotoSection.setVisible(not visible)
        self.frmMediaFilter.layout().activate()
        self.lblPhotoSection.setText(
            f"Photos  <span style='font-size:{_arrowPt}pt; vertical-align:middle'>{_arrow}</span>")
        self.dckMediaFilter.setUpdatesEnabled(True)


    def _toggleRecordingsSection(self):
        visible = self.frmRecordingsSection.isVisible()
        _arrowPt = self.fontSize * 2
        _arrow = "▸" if visible else "▾"
        self.dckMediaFilter.setUpdatesEnabled(False)
        self.frmRecordingsSection.setVisible(not visible)
        self.frmMediaFilter.layout().activate()
        self.lblRecordingsSection.setText(
            f"Recordings  <span style='font-size:{_arrowPt}pt; vertical-align:middle'>{_arrow}</span>")
        self.dckMediaFilter.setUpdatesEnabled(True)


    def removeUnfoundPhotos(self):
        
        countRemovedPhotos = self.db.removeUnfoundPhotos()
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("Yearbirder removed " + str(countRemovedPhotos) + " references to unfound photos from its database.\n\nRemember to save your photo settings to a file.\n\n(No files were deleted from your computer.)")
        msg.setWindowTitle("Removed Photo References")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()        
        

    def broadcastMediaRemovals(self, photoFiles=(), audioRemovals=(), exclude=None):
        """Deliver catalog departures to every open window, WITHOUT the report
        refresh — the single delivery path behind notifyPhotoDeletion /
        notifyAudioDeletion and a Manage save, which departs many files at once
        and fires notifyMediaChanged itself, once, at the end.

        audioRemovals items are (filename, species): species None means the file
        is gone for every species; a species means only that assignment went.
        exclude skips one window that has already handled the removal itself —
        an Enlargement in full screen is detached from the MDI area (see
        toggleFullScreen), so it isn't in subWindowList() and must drive its own
        list; passing itself here keeps that from happening twice when it IS
        attached.  The window list is re-read per file because handling one
        removal can close a window."""
        for fn in photoFiles:
            for w in self.mdiArea.subWindowList():
                if w is not exclude and hasattr(w, 'handlePhotoDeletion'):
                    w.handlePhotoDeletion(fn)
        for fn, species in audioRemovals:
            for w in self.mdiArea.subWindowList():
                if w is not exclude and hasattr(w, 'handleAudioDeletion'):
                    w.handleAudioDeletion(fn, species)

    def notifyPhotoDeletion(self, filename, exclude=None):
        """A photo left the catalog — deleted from disk, or removed from the
        catalog only.  Both have the same consequence for every open window, so
        both fire this."""
        self.broadcastMediaRemovals(photoFiles=(filename,), exclude=exclude)
        self.notifyMediaChanged()

    def notifyAudioDeletion(self, filename, species=None, exclude=None):
        """species=None: the file is gone for every species.  With a species,
        only that species' assignment was removed — other cards for the same
        file must survive."""
        self.broadcastMediaRemovals(audioRemovals=((filename, species),),
                                    exclude=exclude)
        self.notifyMediaChanged()

    def notifyMediaChanged(self):
        """Broadcast a media-catalog change to open report windows.  Each report
        decides for itself (cheaply) whether the change touched its scope and
        rebuilds only if so — see code_MediaRefresh.  Fire this once per change
        (a multi-file Manage save fires it once, from closeEvent)."""
        for w in self.mdiArea.subWindowList():
            if hasattr(w, "_mediaRebuildName"):
                code_MediaRefresh.maybeRefresh(w)


    def evictMediaCacheIfUnreferenced(self, fileName):
        """Delete a media file's on-disk cache (thumbnail/spectrograms) once no
        sighting references it any more, so removing media from the catalog
        reclaims its cache.  Must be called while the file still exists on disk —
        the cache key derives from its path+mtime+size — so a permanent delete
        must call this BEFORE unlinking the file."""
        if not self.db.isMediaFileReferenced(fileName):
            code_ThumbnailCache.evict(fileName)


    def _liveCatalogMedia(self):
        """(source_path, kinds) for every distinct media file in the open catalog:
        photos carry the 'photo' cache kind, recordings the three spectro_* kinds.
        Feeds code_ThumbnailCache.prune_to_catalog to sweep orphaned cache files."""
        _REC_KINDS = ["spectro_thumb", "spectro_overview", "spectro_ribbon"]
        media = []
        seen = set()
        for s in self.db.sightingList:
            for p in s.get("photos", []):
                fn = p.get("fileName", "")
                if fn and fn not in seen:
                    seen.add(fn)
                    media.append((fn, ["photo"]))
            for a in s.get("audio", []):
                fn = a.get("fileName", "")
                if fn and fn not in seen:
                    seen.add(fn)
                    media.append((fn, _REC_KINDS))
        return media


    def refreshOpenRecordings(self):
        """After a Manage Recordings save, re-run each open Browse Recordings
        window's filter query so recordings that now match the filter appear
        (and ones an edit pushed out of the filter drop away).  Re-querying the
        updated catalog handles insert, edit, and removal uniformly and keeps
        the current sort.  Single-recording windows (launched from Find) carry
        a synthetic one-file filter and must not be re-broadened, so skip them;
        windows never filled (filter still the empty tuple) are skipped too.

        FillRecordings returns False when the re-query is now empty WITHOUT
        clearing the window's stale content (its early-out on no results), so
        close the window in that case — otherwise an edit that emptied the
        filter (e.g. a recording reassigned to another species) would leave the
        old cards on screen."""
        for w in list(self.mdiArea.subWindowList()):
            if (isinstance(w, code_Recordings.Recordings)
                    and not getattr(w, "_singleMode", False)
                    and w.filter):
                if w.FillRecordings(w.filter) is False:
                    w.close()


    def refreshOpenPhotos(self):
        """Photos counterpart to refreshOpenRecordings, run after a Manage
        Photos save.  See that method for the skip rationale (including closing
        a window whose re-query is now empty)."""
        for w in list(self.mdiArea.subWindowList()):
            if (isinstance(w, code_Photos.Photos)
                    and not getattr(w, "_singleMode", False)
                    and w.filter):
                if w.FillPhotos(w.filter) is False:
                    w.close()


    def createPreferences(self):
        

        
        sub = code_Preferences.Preferences()

        # save the MDI window as the parent for future use in the child        
        sub.mdiParent = self 
        
        sub.fillPreferences()

        # add and center the child in the MDI area
        self.mdiArea.addSubWindow(sub)
        x = max(0, (self.mdiArea.width() - sub.width()) // 2)
        y = max(0, (self.mdiArea.height() - sub.height()) // 2)
        sub.move(x, y)
        sub.show()



    def createPhotosReport(self):
        # if no data file is currently open, abort
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetPhotoFilter()

        # Pre-check before touching the MDI area — PositionChildWindow restores
        # any maximized sibling, so adding then immediately removing a window
        # causes a visible jerk. Bail out here instead.
        if not MainWindow.db.GetSightingsWithPhotos(filter):
            QMessageBox.information(
                self,
                "No Photos",
                "No photos match the current filter.",
                QMessageBox.StandardButton.Ok,
            )
            return

        sub = code_Photos.Photos()
        sub.mdiParent = self

        self.mdiArea.addSubWindow(sub)
        self.PositionChildWindow(sub,  self)

        # Keep the window HIDDEN while the grid builds (see addPhotos): on a
        # visible window every processEvents during the build re-lays-out and
        # repaints the growing grid, and each arriving thumbnail repaints its
        # cell.  The gated overlay provides progress; reveal fully built.
        # (contentReady also fires after re-sorts, hence the isVisible guard.)
        def _revealPhotos():
            if sub.isVisible():
                return
            sub.show()
            self.mdiArea.setActiveSubWindow(sub)
            sub.raise_()
            sub.setFocus()
        sub.contentReady.connect(_revealPhotos)

        if sub.FillPhotos(filter) is False:

            # Fallback: filter passed sightings but no individual photos matched
            sub.close()
            QMessageBox.information(
                self,
                "No Photos",
                "No photos match the current filter.",
                QMessageBox.StandardButton.Ok,
            )


    def createSpeciesGallery(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetPhotoFilter()
        sub = code_SpeciesGallery.SpeciesGallery()
        sub.mdiParent = self
        self.mdiArea.addSubWindow(sub)
        self.PositionChildWindow(sub, self)
        sub.show()

        if sub.FillGallery(filter) is False:
            sub.close()
            self.CreateMessageNoResults()


    def createRecordingsSpeciesGallery(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetRecordingsFilter()
        sub = code_RecordingsSpeciesGallery.RecordingsSpeciesGallery()
        sub.mdiParent = self
        self.mdiArea.addSubWindow(sub)
        self.PositionChildWindow(sub, self)
        sub.show()

        if sub.FillGallery(filter) is False:
            sub.close()
            self.CreateMessageNoResults()


    def setCountryFilter(self, country):
        index = self.cboCountries.findText(country)
        if index >= 0:
             self.cboCountries.setCurrentIndex(index)

             
    def setCountyFilter(self, county):
        self.cboCountries.setCurrentIndex(0)
        self.cboStates.setCurrentIndex(0)
        index = self.cboCounties.findText(county)
        if index >= 0:
             self.cboCounties.setCurrentIndex(index)

             
    def setStateFilter(self, state):
        self.cboCountries.setCurrentIndex(0)
        index = self.cboStates.findText(state)
        if index >= 0:
             self.cboStates.setCurrentIndex(index)


    def setLocationFilter(self, location):
        self.cboCountries.setCurrentIndex(0)
        self.cboStates.setCurrentIndex(0)
        self.cboCounties.setCurrentIndex(0)
        index = self.cboLocations.findText(location)
        if index >= 0:
             self.cboLocations.setCurrentIndex(index)


    def updateMyLocationButtons(self):
        self.btnMyCounty.setVisible(bool(MainWindow.db.myCounty))
        self.btnMyPatch.setVisible(bool(MainWindow.db.myPatch))


    def _resetLocationCombosToFull(self):
        """Silently reset all location combos to their full 'All X' state."""
        self.fillingLocationComboBoxesFlag = True
        self.cboRegions.setCurrentIndex(0)
        self.unhighlightFilterElement(self.cboRegions)
        self.cboCountries.clear()
        self.cboCountries.addItem("All Countries")
        self.cboCountries.insertSeparator(1)
        self.cboCountries.addItems(MainWindow.db.countryList)
        self.cboCountries.setCurrentIndex(0)
        self.unhighlightFilterElement(self.cboCountries)
        self.cboStates.clear()
        self.cboStates.addItem("All States")
        self.cboStates.insertSeparator(1)
        self.cboStates.addItems(MainWindow.db.stateList)
        self.cboStates.setCurrentIndex(0)
        self.unhighlightFilterElement(self.cboStates)
        self.cboCounties.clear()
        self.cboCounties.addItem("All Counties")
        self.cboCounties.insertSeparator(1)
        self.cboCounties.addItems(MainWindow.db.countyList)
        self.cboCounties.setCurrentIndex(0)
        self.unhighlightFilterElement(self.cboCounties)
        self.cboLocations.clear()
        self.cboLocations.addItem("All Locations")
        self.cboLocations.insertSeparator(1)
        self.cboLocations.addItems(MainWindow.db.locationList)
        self.cboLocations.setCurrentIndex(0)
        self.unhighlightFilterElement(self.cboLocations)
        self.fillingLocationComboBoxesFlag = False


    def applyMyCounty(self):
        county = MainWindow.db.myCounty
        if not county:
            return

        # Look up region, country, and state for this county.
        # Use GetCountryName/GetStateName (reliable lookup dicts) rather than
        # reading countryName/stateName directly from the entry — those fields
        # are only populated on the first entry per code due to a break in the
        # population loop, so other entries for the same state may lack them.
        region_name = ""
        country_name = ""
        state_name = ""
        for entry in MainWindow.db.masterLocationList:
            if entry.get("county") == county:
                codes = entry.get("regionCodes", [])
                if codes:
                    try:
                        region_name = MainWindow.db.GetRegionName(codes[0])
                    except Exception:
                        pass
                country_name = MainWindow.db.GetCountryName(entry.get("countryCode", ""))
                state_name = MainWindow.db.GetStateName(entry.get("stateCode", ""))
                break

        # Silently restore all combos to full lists, then cascade downward letting
        # each Combo*Changed signal narrow and highlight the child combos.
        self._resetLocationCombosToFull()

        if region_name:
            idx = self.cboRegions.findText(region_name)
            if idx > 0:
                self.cboRegions.setCurrentIndex(idx)  # → ComboRegionsChanged

        if country_name:
            idx = self.cboCountries.findText(country_name)
            if idx > 0:
                self.cboCountries.setCurrentIndex(idx)  # → ComboCountriesChanged

        if state_name:
            idx = self.cboStates.findText(state_name)
            if idx > 0:
                self.cboStates.setCurrentIndex(idx)  # → ComboStatesChanged

        idx = self.cboCounties.findText(county)
        if idx >= 0:
            self.cboCounties.setCurrentIndex(idx)  # → ComboCountiesChanged

        # ComboCountriesChanged clears the region highlight; re-apply it.
        if region_name and self.cboRegions.currentText() not in ("All Regions", ""):
            self.highlightFilterElement(self.cboRegions)


    def applyMyPatch(self):
        location = MainWindow.db.myPatch
        if not location:
            return

        # Look up full hierarchy for this location (same lookup strategy as applyMyCounty).
        region_name = ""
        country_name = ""
        state_name = ""
        county_name = ""
        for entry in MainWindow.db.masterLocationList:
            if entry.get("location") == location:
                codes = entry.get("regionCodes", [])
                if codes:
                    try:
                        region_name = MainWindow.db.GetRegionName(codes[0])
                    except Exception:
                        pass
                country_name = MainWindow.db.GetCountryName(entry.get("countryCode", ""))
                state_name = MainWindow.db.GetStateName(entry.get("stateCode", ""))
                county_name = entry.get("county", "")
                break

        self._resetLocationCombosToFull()

        if region_name:
            idx = self.cboRegions.findText(region_name)
            if idx > 0:
                self.cboRegions.setCurrentIndex(idx)  # → ComboRegionsChanged

        if country_name:
            idx = self.cboCountries.findText(country_name)
            if idx > 0:
                self.cboCountries.setCurrentIndex(idx)  # → ComboCountriesChanged

        if state_name:
            idx = self.cboStates.findText(state_name)
            if idx > 0:
                self.cboStates.setCurrentIndex(idx)  # → ComboStatesChanged

        if county_name:
            idx = self.cboCounties.findText(county_name)
            if idx > 0:
                self.cboCounties.setCurrentIndex(idx)  # → ComboCountiesChanged

        idx = self.cboLocations.findText(location)
        if idx >= 0:
            self.cboLocations.setCurrentIndex(idx)  # → ComboLocationsChanged

        # ComboCountriesChanged clears the region highlight; re-apply it.
        if region_name and self.cboRegions.currentText() not in ("All Regions", ""):
            self.highlightFilterElement(self.cboRegions)


    def setSpeciesFilter(self, species):
        index = self.cboSpecies.findText(species)
        if index >= 0:
             self.cboSpecies.setCurrentIndex(index)


    def setFamilyFilter(self, family):
        index = self.cboFamilies.findText(family)
        if index >= 0:
             self.cboFamilies.setCurrentIndex(index)
             

    def setDateFilter(self, startDate, endDate = "", setCombo = True):

        # if only one date is specified, use that date for both start and end dates
        if endDate == "":
            endDate = startDate

        startYear = int(startDate[0:4])
        startMonth = int(startDate[5:7])
        startDay = int(startDate[8:])
        myStartDate = QDate()
        myStartDate.setDate(startYear, startMonth, startDay)

        endYear = int(endDate[0:4])
        endMonth = int(endDate[5:7])
        endDay = int(endDate[8:])
        myEndDate = QDate()
        myEndDate.setDate(endYear, endMonth, endDay)

        # External callers (e.g. clicking a year/date in another window) leave the
        # Date Options combo showing "Use Calendars Below".  The combo's own
        # preset handlers pass setCombo=False so the user's specific choice
        # (e.g. "This Year", "Select Year") remains displayed; GetFilter() still
        # recomputes the correct dates from that choice.
        if setCombo:
            self.cboDateOptions.setCurrentIndex(1)  # "Use Calendars Below"

        # Block calendar signals so CalendarClicked doesn't override the combo selection
        self.calStartDate.blockSignals(True)
        self.calEndDate.blockSignals(True)
        self.calStartDate.setDate(myStartDate)
        self.calEndDate.setDate(myEndDate)
        self.calStartDate.blockSignals(False)
        self.calEndDate.blockSignals(False)


    def setPhotoFolder(self):
        
        directory = str(QFileDialog.getExistingDirectory(self, "Select Directory"))

        self.db.attachPhotos(directory)


    def createEditPhotosByFilter(self):

        # if no data file is currently open, abort
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        for w in self.mdiArea.subWindowList():
            if isinstance(w, code_RenameMedia.RenameMedia):
                QMessageBox.warning(
                    self,
                    "Close Rename Media First",
                    "Please close the Rename Media window before editing photos.\n\n"
                    "Having both windows open at the same time could cause conflicts.",
                    QMessageBox.StandardButton.Ok,
                )
                return

        # create new Manage Photos child window
        sub = code_ManagePhotos.ManagePhotos()

        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self

        # call the child's routine to fill it with data
        if sub.FillPhotosByFilter(self.GetPhotoFilter()) is True:

            # add and position the child to our MDI area, but keep it HIDDEN
            # until its rows have built (see addPhotos): the workers load
            # thumbnails in parallel and contentReady fires when done, with
            # the gated progress overlay providing feedback for slow loads.
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)

            def _revealManagePhotos():
                sub.show()
                self.mdiArea.setActiveSubWindow(sub)
                sub.raise_()
                sub.setFocus()
            sub.contentReady.connect(_revealManagePhotos)

        else:

            # abort since filter found no sightings for child
            self.CreateMessageNoResults()
            sub.close()


    def createManageRecordings(self):
        if not MainWindow.db.eBirdFileOpenFlag:
            self.CreateMessageNoFile()
            return

        sub = code_ManageRecordings.ManageRecordings()
        sub.mdiParent = self

        if sub.FillRecordingsByFilter(self.GetRecordingsFilter()) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)

            # Keep the window HIDDEN while its rows build (see addPhotos); the
            # gated overlay provides feedback whenever the load runs long.
            def _revealManageRecordings():
                sub.show()
                self.mdiArea.setActiveSubWindow(sub)
                sub.raise_()
                sub.setFocus()
            sub.contentReady.connect(_revealManageRecordings)

        else:
            self.CreateMessageNoResults()
            sub.close()

    def createRecordingsBrowser(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetRecordingsFilter()

        if not MainWindow.db.GetSightingsWithRecordings(filter):
            QMessageBox.information(
                self,
                "No Recordings",
                "No recordings match the current filter.",
                QMessageBox.StandardButton.Ok,
            )
            return

        sub = code_Recordings.Recordings()
        sub.mdiParent = self

        self.mdiArea.addSubWindow(sub)
        self.PositionChildWindow(sub, self)
        sub.show()

        if sub.FillRecordings(filter) is False:
            sub.close()
            QMessageBox.information(
                self,
                "No Recordings",
                "No recordings match the current filter.",
                QMessageBox.StandardButton.Ok,
            )

    def createRenameMedia(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        for w in self.mdiArea.subWindowList():
            if isinstance(w, (code_ManagePhotos.ManagePhotos,
                               code_ManageRecordings.ManageRecordings)):
                QMessageBox.warning(
                    self,
                    "Close Manage Media First",
                    "Please close any open Manage Photos or Manage Recordings windows "
                    "before renaming media.\n\n"
                    "Having both windows open at the same time could cause conflicts.",
                    QMessageBox.StandardButton.Ok,
                )
                return

        photo_sightings = MainWindow.db.GetSightingsWithPhotos(self.GetFilter())
        recording_file_to_sightings = MainWindow.db.GetSightingsByRecordingFile(
            self.GetFilter())

        if not photo_sightings and not recording_file_to_sightings:
            self.CreateMessageNoResults()
            return

        sub = code_RenameMedia.RenameMedia()
        sub.mdiParent = self

        self.mdiArea.addSubWindow(sub)
        self.PositionChildWindow(sub, self)
        sub.show()
        sub.scaleMe()
        sub.resizeMe()

        sub.FillRenameMedia(photo_sightings, recording_file_to_sightings)


    def rebuildThumbnailCache(self):
        """Clear and regenerate the on-disk thumbnail cache for every photo in
        the media catalog, showing the same progress overlay as photo loading.

        Runs asynchronously: worker threads decode/store off the GUI thread while
        a drain timer updates the overlay, so the app stays responsive (matching
        the Photos browser's loading pattern)."""
        if getattr(self, "_rebuildTimer", None) and self._rebuildTimer.isActive():
            return   # a rebuild is already in progress

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        photo_files = MainWindow.db.GetPhotos(code_Filter.Filter())
        recording_files = MainWindow.db.GetAudio(code_Filter.Filter())
        n_photos = len(photo_files)
        n_recordings = len(recording_files)
        total = n_photos + n_recordings
        if total == 0:
            QMessageBox.information(
                self, "Rebuild Thumbnail Cache",
                "There is no photo or recording media in the catalog to rebuild.",
                QMessageBox.StandardButton.Ok)
            return

        parts = []
        if n_photos:
            parts.append(f"{n_photos} photo{'s' if n_photos != 1 else ''}")
        if n_recordings:
            parts.append(f"{n_recordings} recording{'s' if n_recordings != 1 else ''}")

        # Offer per-kind rebuilds: the photo option only when the catalog has
        # photos, the recording option only when it has recordings, and "all"
        # only when it has both (otherwise the single-kind option *is* "all").
        # Order left-to-right: Cancel, photos, recordings, all.
        labels = ["Cancel"]
        if n_photos:
            labels.append("Rebuild photo thumbnails")
        if n_recordings:
            labels.append("Rebuild recording thumbnails")
        if n_photos and n_recordings:
            labels.append("Rebuild all thumbnails")

        choice = code_Stylesheet.choose(
            self, "Rebuild Thumbnail Cache",
            "Cached thumbnails (photos) and spectrograms (recordings) are "
            "regenerated from the original media files.\n\n"
            f"The catalog has {' and '.join(parts)}.",
            labels)
        if choice in (None, "Cancel"):
            return

        rebuild_all        = choice == "Rebuild all thumbnails"
        rebuild_photos     = rebuild_all or choice == "Rebuild photo thumbnails"
        rebuild_recordings = rebuild_all or choice == "Rebuild recording thumbnails"

        # Import the ribbon renderer on the main thread (matplotlib init isn't
        # thread-safe) before the worker threads use it.
        import code_RecordingEnlargement

        # A full rebuild starts clean so orphaned/stale entries are removed; a
        # single-kind rebuild regenerates just that kind's entries in place,
        # leaving the other kind's cache untouched.
        if rebuild_all:
            code_ThumbnailCache.clear()

        work = queue.Queue()
        if rebuild_photos:
            for f in photo_files:
                work.put(("photo", f))
        if rebuild_recordings:
            for f in recording_files:
                work.put(("recording", f))
        total = (n_photos if rebuild_photos else 0) + (n_recordings if rebuild_recordings else 0)
        self._rebuildDone = queue.Queue()
        self._rebuildTotal = total
        self._rebuildCompleted = 0

        done = self._rebuildDone

        # Arm the GUI-thread axes pump: the workers render spectro thumbs
        # text-free (QFont/drawText is not thread-safe on macOS), and the pump
        # paints the kHz/sec labels and stores the finished PNGs.
        code_ThumbnailCache.ensure_axes_pump()

        # Worker *threads* (not processes): the renderers release the GIL during
        # the heavy work (libsndfile decode, numpy FFT, matplotlib's Agg C++), so
        # threads parallelise it well — and without process-spawn overhead.
        def worker():
            code_ThumbnailCache.builder_started()
            try:
                while True:
                    try:
                        item = work.get_nowait()
                    except queue.Empty:
                        break
                    code_ThumbnailCache.rebuild_one(item)
                    done.put(1)
            finally:
                code_ThumbnailCache.builder_finished()

        thread_count = min(os.cpu_count() or 4, 8)
        self._rebuildWorkers = [threading.Thread(target=worker, daemon=True)
                                for _ in range(thread_count)]
        for t in self._rebuildWorkers:
            t.start()

        self.progressOverlay.showDeterminate("Rebuilding media cache…", total)

        self._rebuildTimer = QTimer(self)
        self._rebuildTimer.timeout.connect(self._drainRebuild)
        self._rebuildTimer.start(50)

    def _drainRebuild(self):
        """Drain completed-thumbnail markers (every 50 ms) and update the overlay."""
        drained = False
        try:
            while True:
                self._rebuildDone.get_nowait()
                self._rebuildCompleted += 1
                drained = True
        except queue.Empty:
            pass
        if drained:
            self.progressOverlay.setProgress(self._rebuildCompleted)
        if self._rebuildCompleted >= self._rebuildTotal:
            self._rebuildTimer.stop()
            self.progressOverlay.hide()
            code_ThumbnailCache.enforce_cap()   # keep the cache bounded


    def optimizePhotoSettings(self):

        if not MainWindow.db.photoDataFileOpenFlag:
            QMessageBox.warning(
                self,
                "No Media Catalog",
                "Please open a media catalog first.",
                QMessageBox.StandardButton.Ok,
            )
            return

        dlg = _OptimizePhotoSettingsDialog(self, MainWindow.db)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        missing = dlg.missing
        from collections import defaultdict
        by_sighting_photo = defaultdict(list)
        by_sighting_audio = defaultdict(list)
        for m in missing:
            if m["kind"] == "photo":
                by_sighting_photo[m["sighting_idx"]].append(m["media_idx"])
            else:
                by_sighting_audio[m["sighting_idx"]].append(m["media_idx"])

        for sighting_idx, indices in by_sighting_photo.items():
            sighting = MainWindow.db.sightingList[sighting_idx]
            for idx in sorted(indices, reverse=True):
                sighting["photos"].pop(idx)
            if not sighting["photos"]:
                del sighting["photos"]

        for sighting_idx, indices in by_sighting_audio.items():
            sighting = MainWindow.db.sightingList[sighting_idx]
            for idx in sorted(indices, reverse=True):
                sighting["audio"].pop(idx)
            if not sighting["audio"]:
                del sighting["audio"]

        MainWindow.db.compactJsonlFile()

        # Sweep the on-disk cache: delete every cached thumbnail/spectrogram that
        # does not correspond to a media file in the now-compacted catalog. This
        # reclaims cache for files removed above and any earlier orphans. The
        # cache is shared across catalogs, so another catalog's media re-caches
        # on next view (no data or files are lost).
        cache_removed = code_ThumbnailCache.prune_to_catalog(self._liveCatalogMedia())

        n_photos = sum(1 for m in missing if m["kind"] == "photo")
        n_recordings  = sum(1 for m in missing if m["kind"] == "recording")
        if not missing:
            msg = "The media catalog has been compacted."
        else:
            parts = []
            if n_photos:
                parts.append(f"{n_photos} missing photo {'entries' if n_photos != 1 else 'entry'}")
            if n_recordings:
                parts.append(f"{n_recordings} missing recordings {'entries' if n_recordings != 1 else 'entry'}")
            msg = f"Removed {' and '.join(parts)} and compacted the media catalog."
        if cache_removed:
            msg += (f"\n\nReclaimed {cache_removed} cached "
                    f"{'image' if cache_removed == 1 else 'images'} from disk.")
        QMessageBox.information(
            self,
            "Compact Complete",
            msg,
            QMessageBox.StandardButton.Ok,
        )



    def setSeasonalRangeFilter(self, month):
        index = self.cboStartSeasonalRangeMonth.findText(month)
        if index >= 0:
            self.cboStartSeasonalRangeMonth.setCurrentIndex(index)
            self.cboEndSeasonalRangeMonth.setCurrentIndex(index)
            self.cboStartSeasonalRangeDate.setCurrentIndex(0)
            self.cboEndSeasonalRangeDate.setCurrentIndex(30)

             
    def showStandardFilter(self):
        self.dckFilter.show()
        self.actionShowStandardFilter.setVisible(False)
        self.actionHideStandardFilter.setVisible(True)

        
    def hideStandardFilter(self):
        self.dckFilter.hide()
        self.actionHideStandardFilter.setVisible(False)
        self.actionShowStandardFilter.setVisible(True)        


    def showMediaFilter(self):
        self.dckMediaFilter.show()
        self.actionShowMediaFilter.setVisible(False)
        self.actionHideMediaFilter.setVisible(True)
        
        
    def hideMediaFilter(self):
        self.dckMediaFilter.hide()
        self.actionHideMediaFilter.setVisible(False)
        self.actionShowMediaFilter.setVisible(True)
        
        
    def keyPressEvent(self, e):
        # open file dialog routine if user presses Crtl-O
        if e.key() == Qt.Key_O and e.modifiers() & Qt.ControlModifier:
            self.openDataFileClicked()

        # open file dialog routine if user presses Crtl-O
        if e.key() == Qt.Key_F and e.modifiers() & Qt.ControlModifier:
            self.CreateFind()

        # toggle Media filter dock with Cmd-M
        if e.key() == Qt.Key_M and e.modifiers() & Qt.ControlModifier:
            if self.dckMediaFilter.isVisible():
                self.hideMediaFilter()
            else:
                self.showMediaFilter()

        # toggle Sighting Filter dock with Cmd-S
        if e.key() == Qt.Key_S and e.modifiers() & Qt.ControlModifier:
            if self.dckFilter.isVisible():
                self.hideStandardFilter()
            else:
                self.showStandardFilter()

        # toggle toolbar with Cmd-T
        if e.key() == Qt.Key_T and e.modifiers() & Qt.ControlModifier:
            self.toolBar.setVisible(not self.toolBar.isVisible())
            
                
    def CalendarClicked(self):
        if MainWindow.db.eBirdFileOpenFlag is True:
            if self.cboDateOptions.currentText() != "Select Year":
                self.cboDateOptions.setCurrentIndex(1)


    def CreateFind(self):
        
        # if no data file is currently open, abort
        if MainWindow.db.eBirdFileOpenFlag is False:
            self.CreateMessageNoFile()   
            return
        
        sub = code_Find.Find()

        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self

        self.mdiArea.addSubWindow(sub)

        # center in the MDI area
        x = (self.mdiArea.width()  - sub.width())  // 2
        y = (self.mdiArea.height() - sub.height()) // 2
        sub.move(max(0, x), max(0, y))

        sub.show()
        
        
    def CreateMessageNoFile(self):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("No ebird data is currently loaded.\n\nPlease open an eBird data file.")
        msg.setWindowTitle("No Data")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()


    def CreateMessageNoResults(self):
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("No sightings match the current filter settings.")
        msg.setWindowTitle("No Sightings")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()
        
        
    def PositionChildWindow(self, child,  creatingWindow):

        # Qt's QMdiArea only allows one maximized subwindow at a time.
        # Capture whether the MDI area is in maximized mode *before* restoring,
        # then restore the sibling so the new child can be freely positioned.
        # After scaleMe has set the restore size, maximize the new child.
        # QTimer(50ms) ensures both synchronous and QTimer(0) scaleMe calls
        # complete before showMaximized fires.
        spawned_from_maximized = any(
            w.isMaximized() for w in self.mdiArea.subWindowList() if w is not child)
        displaced_maximized = None
        if spawned_from_maximized:
            for w in self.mdiArea.subWindowList():
                if w is not child and w.isMaximized():
                    displaced_maximized = w
                    w.showNormal()
                    # Qt's cached pre-maximize geometry can be stale (e.g. it
                    # was captured before the window ever settled into its
                    # content-driven size), which restores it to a startlingly
                    # small size.  Recompute a correct size from its current
                    # content instead of trusting that cache.  Not every
                    # subwindow type implements scaleMe (e.g. RecordingEnlargement,
                    # SpeciesGallery), so guard the call.
                    if hasattr(w, "scaleMe"):
                        w.scaleMe()
                    break

        # if creatingWindow is the maind MDI window, center the new child window
        if creatingWindow.objectName() == "MainWindow":
            childWindowCoordinates = []
            for window in self.mdiArea.subWindowList():
                if window.isVisible() == True:
                    childWindowCoordinates.append([window.x(),  window.y()])
            # try to place child window, but check if that would exactly overlap another window
            x = 10
            y = 10
            # if x, y is already the top left coordinate of a child window, add 20 to x and y and retry
            while [x, y] in childWindowCoordinates:
                x = x + 25
                y = y + 25
            child.setGeometry(x, y, child.width(), child.height())

        # if creatingWindow is a child window, place new child window cascaded down from calling creatingWindow
        else:
            x = creatingWindow.x() + 25
            y = creatingWindow.y() + 25
        child.setGeometry(x, y, child.width(), child.height())

        child.setFocus()

        if spawned_from_maximized:
            QTimer.singleShot(50, child.showMaximized)
            # When the child was maximized in place of a maximized sibling, Qt
            # does NOT reliably re-transfer the maximized state back to that
            # sibling when the child closes — intermittently leaving the sibling
            # at its small showNormal()/scaleMe() size (e.g. a Browse Recordings
            # window shrinking after its Recording Enlargement closes).  Restore
            # it explicitly when the child is destroyed.
            if displaced_maximized is not None:
                child.destroyed.connect(
                    lambda *_a, w=displaced_maximized:
                        self._restoreDisplacedMaximized(w))
            # The deferred showMaximized above is this window's FIRST appearance.
            # Signal the caller not to show() it now: showing it here would flash
            # the window at its small pre-maximize size for one frame before it
            # snaps to maximized.  Callers that honour this return skip show().
            return True

        return False


    def _restoreDisplacedMaximized(self, w):
        """Re-maximize a sibling that was un-maximized to make room for a child
        window, once that child has closed.  Guards against the sibling having
        been deleted or already re-maximized in the meantime."""
        if not isValid(w):
            return
        if w not in self.mdiArea.subWindowList():
            return
        if not w.isMaximized():
            w.showMaximized()


    def closeDataFile(self):
                
        
        self.checkIfPhotoDataNeedSaving()
        self.ResetMainWindow()
        self.db.ClearDatabase()



    def checkIfPhotoDataNeedSaving(self):

        if self.db.photosNeedSaving is True:

            if self.db.photoDataFile and self.db.photoDataFile.lower().endswith(".jsonl"):
                # JSONL file already set — compact silently, no dialog needed
                self.db.compactJsonlFile()

            else:
                # No JSONL file yet (first save or legacy CSV) — use the standard migration prompt
                self._promptJsonlMigrationIfNeeded()

        return(True)
                
                
    def openDataFileClicked(self):

        self.checkIfPhotoDataNeedSaving()
        self.ResetMainWindow()
        self.db.ClearDatabase()
        self.clearStandardFilter()

        self.OpenDataFile()

        if MainWindow.db.eBirdFileOpenFlag is True:
            self.FillMainComboBoxes()
            self.dckFilter.setVisible(True)
            self.CreateSpeciesList()
            self.actionClose.setVisible(True)
            self.actionOpenPhotoSettings.setVisible(True)
            self.actionAddPhotos.setVisible(True)
            self.actionAddRecordings.setVisible(True)
            self.actionRebuildThumbnailCache.setVisible(True)

            self._autoOpenDefaultCatalog()

            if self.db.photoDataFileOpenFlag:
                self.fillPhotoComboBoxes()
                self.fillRecordingsComboBoxes()
                self.showMediaFilter()
                # Photos/Recordings menus appear only if the catalog has that media.
                self._updateMediaMenuVisibility()
                self._showPhotoCatalogMenuItems()
                self.actionGeolocatedPhotos.setVisible(True)
                self.actionGeolocatedPhotosSeparator.setVisible(True)
                self.actionAnimatedPhotoSequence.setVisible(True)
                self.actionSlideshow.setVisible(True)
                self.actionYTDPhotos.setVisible(True)
                self.actionPhotoPie.setVisible(True)
                self.actionPhotoBar.setVisible(True)
                self.actionPhotoAccumulation.setVisible(True)
                self.actionCumulativePhotos.setVisible(True)
                self.actionEditPhotosByFilter.setVisible(True)
                self.actionUpdateEXIFDataForAllPhotos.setVisible(True)
                self.actionUpdateRecordingData.setVisible(True)
                self.actionRenameMedia.setVisible(True)
                self.actionOptimizePhotoSettings.setVisible(True)

            self.CreateStatsOnLoad()

            # Offer to make the opened file's folder the default startup folder,
            # but only if it differs from the folder already set in Preferences.
            opened_dir = os.path.dirname(MainWindow.db.eBirdFilePath)
            if opened_dir and os.path.realpath(opened_dir) != os.path.realpath(MainWindow.db.startupFolder):
                reply = code_Stylesheet.question(
                    self,
                    "Set Default Folder",
                    "Set this as your default eBird folder?\n\n"
                    "On startup, Yearbirder will open the most recent eBird file it finds here.",
                )
                if reply == QMessageBox.StandardButton.Yes:
                    MainWindow.db.setStartupFolder(opened_dir)
                    MainWindow.db.writePreferences()


    def OpenDataFile(self, startupFolder=""):
        # clear and close any data if a file is already open

        self.closeDataFile()
        
        QApplication.processEvents()
                
        if os.path.isdir(startupFolder):
            
            list_of_files = []
            
            for file in os.listdir(startupFolder):
                                
                if file.endswith(".zip") and "ebird" in str(file):
                    
                    list_of_files.append(os.path.join(startupFolder, file))
            
            try:
                #try to get the most recent file from the list of ebird zip files, if any were found
                fname = max(list_of_files, key=os.path.getctime)
            except:
                #none were found, so return an empty string.  Tell ther user.
                fname = ""
                msg = QMessageBox()
                msg.setText("No ebird file was found in the startup folder specified in your preferences.")
                msg.exec()

        else:
            
            #No startup folder was specified, so ask user which ebird file to open.  Take only the first element of the tuple, which is the filename
            fname = QFileDialog.getOpenFileName(self,"QFileDialog.getOpenFileNames()", MainWindow.db.startupFolder,"eBird Data Files (*.csv *.zip)")[0]
                
        if fname != "":

            # --- Load the main eBird CSV with a progress dialog. ---
            # ReadDataFile is CPU-bound Python (CSV + dict work), so it holds
            # the GIL throughout; a background thread can't help here.  Instead
            # run it synchronously and pump the event loop via processEvents()
            # inside the progress callback so the bar repaints as rows are read.
            self.progressOverlay.showForDataLoad()
            QApplication.processEvents()

            def _progress(v):
                self.progressOverlay.setValue(v)
                QApplication.processEvents()

            MainWindow.db.ReadDataFile(fname, progress_callback=_progress)
            self.progressOverlay.hide()

            # If loading failed (e.g. bad zip file), show a message and stop.
            if not MainWindow.db.eBirdFileOpenFlag:
                QMessageBox.warning(
                    self,
                    "File failed to load",
                    "The file failed to load.\n\n"
                    "Please check that it is a valid eBird data file.",
                )
                return

            # Helper files are small and fast; load them synchronously.
            QApplication.processEvents()

            # Taxonomy file: find the most recent eBird_Taxonomy*.csv
            resourceDir = os.path.dirname(code_DataBase.resource_path("eBird_Taxonomy.csv"))
            taxonomyMatches = glob.glob(os.path.join(resourceDir, "eBird_Taxonomy*.csv"))
            taxonomyFile = max(taxonomyMatches) if taxonomyMatches else None
            if taxonomyFile:
                MainWindow.db.ReadTaxonomyDataFile(taxonomyFile)
                yearMatch = re.search(r'(\d{4})', os.path.basename(taxonomyFile))
                MainWindow.taxonomyYear = yearMatch.group(1) if yearMatch else ""

            # Country/state code file
            countryStateCodeFile = code_DataBase.resource_path("ebird_api_ref_location_eBird_list_subnational1.csv")
            if os.path.isfile(countryStateCodeFile):
                MainWindow.db.ReadCountryStateCodeFile(countryStateCodeFile)

            # BBL banding code file
            bblCodeFile = code_DataBase.resource_path("eBird_BBLCodes.csv")
            if os.path.isfile(bblCodeFile):
                MainWindow.db.ReadBBLCodeFile(bblCodeFile)



    def CreateRegionalTaxonomy(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Web.Web()
        sub.mdiParent = self

        if sub.loadRegionalTaxonomy(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()


    def CreateExplorer(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        api_key = MainWindow.db.ebirdApiKey.strip()
        if not api_key:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "eBird API Key Required",
                "No eBird API key is configured.\n\nPlease add your key under Preferences.",
                QMessageBox.StandardButton.Ok,
            )
            return

        sub = code_Explorer.Explorer()
        sub.mdiParent = self
        self.mdiArea.addSubWindow(sub)
        sub.scaleMe()
        mdi_rect = self.mdiArea.rect()
        sub_size = sub.size()
        sub.move(
            max(0, (mdi_rect.width()  - sub_size.width())  // 2),
            max(0, (mdi_rect.height() - sub_size.height()) // 2),
        )
        sub.show()
        sub.load()   # kicks off background country-list fetch after window is visible


    def CreateNotableSightings(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self

        if sub.loadNotableSightings(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()


    def CreateAllSightings(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self

        if sub.loadAllSightings(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()


    def CreateHotspotMap(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self

        if sub.loadHotspotMap(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()


    def CreateBigReport(self):
        # the Create Analysis Report button was clicked
        # spawn a new ChildAnalysis window and fill it

        # if no data file is currently open, abort
        if MainWindow.db.eBirdFileOpenFlag is False:
            self.CreateMessageNoFile()
            return

        # get the current filter settings to validate before proceeding
        filter = self.GetGeneralFilter()
        if filter is None:
            return

        # check if filter is completely empty (no meaningful constraints set)
        filterIsEmpty = (
            filter.getLocationName() == "" and
            filter.getStartDate() == "" and
            filter.getEndDate() == "" and
            filter.getSpeciesName() == "" and
            filter.getSpeciesList() == [] and
            filter.getFamily() == "" and
            filter.getChecklistID() == "" and
            filter.getCommonNameSearch() == "" and
            filter.getStartSeasonalMonth() == ""
        )
        if filterIsEmpty:
            QMessageBox.information(
                self,
                "No Filter Set",
                "Please set a filter before generating a Big Report.\n\n"
                "A Big Report with no filter will query your entire dataset and may take a very long time.",
                QMessageBox.StandardButton.Ok
            )
            return

        # if a date range is set, warn if it spans more than one year
        startDate = filter.getStartDate()
        endDate = filter.getEndDate()
        if startDate != "" and endDate != "":
            d0 = datetime.datetime.strptime(startDate, "%Y-%m-%d")
            d1 = datetime.datetime.strptime(endDate, "%Y-%m-%d")
            if (d1 - d0).days > 365:
                reply = code_Stylesheet.question(
                    self,
                    "Large Date Range",
                    f"The selected date range spans more than one year "
                    f"({startDate} to {endDate}).\n\n"
                    "Generating this report may take a long time. Proceed anyway?",
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

        
        # create new Analysis child window
        sub = code_BigReport.BigReport()
        
        # set the mdiParent variable in the child so it can know the 
        # object that called it (for later use in the child)
        sub.mdiParent = self
        
        # call the child's routine to fill it with data
        if sub.FillAnalysisReport(filter) is False:
            self.CreateMessageNoResults()
            sub.close()
            
        else:
        
            # add child to MDI area and position it
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)



    def CreateStats(self):
        if MainWindow.db.eBirdFileOpenFlag is False:
            self.CreateMessageNoFile()
            return

        sub = code_Stats.Stats()
        sub.mdiParent = self

        if sub.FillStats(code_Filter.Filter()) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateStatsOnLoad(self):
        """Show a Stats window (all data, no filter) after a file load.

        Closes any existing Stats windows first, then creates a fresh one
        centered in the MDI area.
        """
        if not MainWindow.db.eBirdFileOpenFlag:
            return

        # close any existing Stats windows so we don't pile them up
        for w in list(self.mdiArea.subWindowList()):
            if w.objectName() == "frmStats":
                w.close()

        sub = code_Stats.Stats()
        sub.mdiParent = self

        if sub.FillStats(code_Filter.Filter()) is True:
            self.mdiArea.addSubWindow(sub)
            # Size and position while still HIDDEN.
            sub.scaleMe()
            mdi_w = self.mdiArea.width()
            mdi_h = self.mdiArea.height()
            x = max(0, (mdi_w - sub.width()) // 2)
            y = max(0, (mdi_h - sub.height()) // 2)
            sub.move(x, y)

            # Reveal the window ONLY once its QWebEngineView has painted its dark
            # content AND the window has been sized to fit it (contentReady, see
            # Stats._fitToContent).  On Windows a QWebEngineView flashes a white
            # frame while Chromium initialises; keeping the whole window hidden
            # until then means that white init happens off-screen, so the user
            # never sees it.  QTimer fallback in case the load never finishes.
            def _revealStats(*_):
                if sub.isVisible():
                    return
                # re-center: the fit may have changed the height set above
                x = max(0, (self.mdiArea.width() - sub.width()) // 2)
                y = max(0, (self.mdiArea.height() - sub.height()) // 2)
                sub.move(x, y)
                sub.show()
                self.mdiArea.setActiveSubWindow(sub)
                sub.raise_()
                sub.setFocus()
            sub.contentReady.connect(_revealStats)
            # Fallback timer is BOUND TO sub (context-object overload): the
            # window is WA_DeleteOnClose and can be destroyed before the timer
            # fires (e.g. another file load closes existing Stats windows) —
            # an unbound closure would then touch a deleted wrapper and raise.
            QTimer.singleShot(2500, sub, _revealStats)
        else:
            sub.close()


    def CreateChecklistsList(self):
        # Create Filtered List button was clicked
        # create filtered species list child

        # if no data file is currently open, abort
        if MainWindow.db.eBirdFileOpenFlag is False:
            self.CreateMessageNoFile()
            return
            
        
        # get the current filter settings in a list to pass to child
        filter = self.GetGeneralFilter()
        if filter is None:
            return

        # create child window
        sub = code_Lists.Lists()

        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self

        # call the child's fill routine, passing the filter settings list
        if sub.FillChecklists(filter) is True:
            
            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.resize(1000, sub.height())
            sub.show()
            sub.scaleMe()

        else:

            self.CreateMessageNoResults()
            sub.close()

                    
                 
    def CreatePDF(self):

        activeWindow = self.mdiArea.activeSubWindow()

        if activeWindow is None:
            return

        if activeWindow.objectName() in ([
            "frmSpeciesList",
            "frmFamilies",
            "frmCompare",
            "frmDateTotals",
            "frmLocationTotals",
            "frmWeb",
            "frmGraphs",
            "frmPhotos",
            "frmStats",
            "frmIndividual",
            "frmLocation",
            "frmBigReport",
            "frmSpeciesGallery",
            ]):

            # create a QTextDocument in memory to hold and render our content
            document = QTextDocument()

            # create a QPrinter object for the printer the user later selects
            printer = QPrinter()
            
            # set printer to PDF output, Letter size
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
            printer.setPageMargins(QMarginsF(20, 10, 10, 10), QPageLayout.Unit.Millimeter)

            # set the document to the printer's page size
            pageSize = printer.pageLayout().fullRect(QPageLayout.Unit.Point).size()
            document.setPageSize(pageSize)

            if activeWindow.objectName() in ("frmPhotos", "frmSpeciesGallery"):
                n = (len(activeWindow.photoList)
                     if activeWindow.objectName() == "frmPhotos"
                     else len(activeWindow._galleryItems))
                pages = ceil(n / 6)
                reply = code_Stylesheet.question(
                    self,
                    "Confirm PDF",
                    f"This will generate approximately {pages} page{'s' if pages != 1 else ''} "
                    f"({n} photo{'s' if n != 1 else ''}). Continue?",
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            filename = QFileDialog.getSaveFileName(self, "Save PDF File", "", "PDF Files (*.pdf)")
            
            if filename[0] != "":
                
                # set output file name
                printer.setOutputFileName(filename[0])
            
                # get html content from child window
                html = activeWindow.html()

                # load the html into the document
                document.setHtml(html)

                # create the PDF file by printing to the "printer" (which is set to PDF)
                document.print_(printer)  

                if sys.platform == "win32":
                    os.startfile(filename[0])
                else:
                    opener ="open" if sys.platform == "darwin" else "xdg-open"
                    subprocess.call([opener, filename[0]])

        else:
            QMessageBox.information(
                self,
                "PDF Not Available",
                "Saving as PDF is not available for this window.",
                QMessageBox.StandardButton.Ok,
            )


    def CreateSpeciesList(self): 
        # Create Filtered List button was clicked
        # create filtered species list child
        
        # if no data file is currently open, abort
        if MainWindow.db.eBirdFileOpenFlag is False:
            self.CreateMessageNoFile()   
            return
            
        
        # get the current filter settings in a list to pass to child
        filter = self.GetGeneralFilter()
        if filter is None:
            return

        # If a single species is selected in the Sighting Filter, the resulting
        # Species list would show only that one species. Show the more useful
        # Individual window for that species instead.
        if filter.getSpeciesName() != "":
            sub = code_Individual.Individual()
            sub.mdiParent = self
            sub.FillIndividual(filter.getSpeciesName())
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QApplication.processEvents()
            sub.scaleMe()
            sub.resizeMe()
            return

        # create child window
        sub = code_Lists.Lists()

        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self

        # call the child's fill routine, passing the filter settings list
        if sub.FillSpecies(filter) is True:
            
            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()
            sub.scaleMe()

        else:

            self.CreateMessageNoResults()
            sub.close()



    def CreateLocationReport(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return
        if filter.getLocationType() != "Location" or not filter.getLocationName():
            QMessageBox.information(
                self,
                "No Location Selected",
                "Please select a specific location in the Sighting Filter before opening a Location report.",
                QMessageBox.StandardButton.Ok,
            )
            return

        sub = code_Location.Location()
        sub.mdiParent = self
        sub.FillLocation(filter.getLocationName())
        self.mdiArea.addSubWindow(sub)
        self.PositionChildWindow(sub, self)
        sub.show()


    def CreateLocationTotals(self):

        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        # create new Location Totals child window
        sub = code_LocationTotals.LocationTotals()

        # save the MDI window as the parent for future use in the child        
        sub.mdiParent = self        

        # call the child's routine to fill it with data        
        # procede if the child successfully filled with data
        if sub.FillLocationTotals(filter) is True:

            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)

        else:

            # abort if filter found no sightings for child
            self.CreateMessageNoResults()
            sub.close()



    def CreateAboutYearbirder(self):


        sub = code_Web.Web()

        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self

        # call the child's routine to fill it with data
        sub.loadAboutYearbirder()

        # add and position the child to our MDI area
        self.mdiArea.addSubWindow(sub)
        self.PositionChildWindow(sub,  self)
        sub.show()



    def CreateUserGuide(self):


        sub = code_Web.Web()
        sub.mdiParent = self
        sub.loadUserGuide()

        self.mdiArea.addSubWindow(sub)
        self.PositionChildWindow(sub, self)
        sub.show()


    def CheckForUpdates(self):
        self._updateThread = _UpdateCheckThread()
        self._updateThread.done.connect(self._onUpdateCheckDone)
        self._updateThread.start()

    def _onUpdateCheckDone(self, tag_name):
        if not tag_name:
            QMessageBox.warning(
                self, "Check for Updates",
                "Could not reach the update server.\nPlease check your internet connection and try again."
            )
            return

        latest = tag_name.lstrip("v")
        current = self.versionNumber

        if latest <= current:
            QMessageBox.information(
                self, "Check for Updates",
                f"You have the latest version of Yearbirder (v{current})."
            )
        else:
            msg = QMessageBox(self)
            msg.setWindowTitle("Update Available")
            msg.setText(f"Yearbirder v{latest} is available.")
            msg.setInformativeText(f"You are running v{current}. Click Download to open the download page in your browser.")
            download_btn = msg.addButton("Download…", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("Not Now", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            if msg.clickedButton() is download_btn:
                QDesktopServices.openUrl(QUrl("https://github.com/trinkner/yearbirder/releases/latest"))


    def CreateMap(self):   

        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        # create new Location Totals child window
        sub = code_Web.Web()

        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self

        # call the child's routine to fill it with data
        if sub.LoadLocationsMap(filter) is True:
            
            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()

        else:
            # abort if filter found no sightings for map
            self.CreateMessageNoResults()
            sub.close()
            

        
    def CreateDateTotals(self):  

        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        # create new Date Totals child window
        sub = code_DateTotals.DateTotals()

        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self

        # call the child's routine to fill it with data
        if sub.FillDateTotals(filter) is True:

            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)

        else:

            # abort since filter found no sightings for child
            self.CreateMessageNoResults()
            sub.close()



    def CreateBarGraph(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return


        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "bar") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateTotalChecklistsGraph(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "totalchecklists") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateTotalLocationsGraph(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "totallocations") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateCumulativeCurve(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "cumulative") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateCumulativeLocationsCurve(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "cumulativelocations") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateCumulativeFamiliesCurve(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "cumulativefamilies") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateHeatmap(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "heatmap") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateAccumulationChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "accumulation") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()



    def CreateTopLocations(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "locations") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateYTDReport(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "ytdreport") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateYTDLocations(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "ytdlocations") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateYTDChecklists(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "ytdchecklists") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateYTDPhotos(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetPhotoFilter(), "ytdphotos") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreatePhotoPieChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetPhotoFilter(), "photopie") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

    def CreatePhotoBarChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetPhotoFilter(), "totalphotos") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

    def CreatePhotoAccumulationChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetPhotoFilter(), "photoaccumulation") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

    def CreateCumulativePhotosChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(self.GetPhotoFilter(), "cumulativephotos") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

    def createRecordingsBySpeciesBarChart(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetRecordingsFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadAudioSpeciesGallery(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()

    def createPhotosBySpeciesBarChart(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetPhotoFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadPhotoSpeciesGallery(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()

    def createGeolocatedRecordingsMap(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetRecordingsFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadGeolocatedRecordingsMap(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()

    def createAnimatedRecordingSequenceMap(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetRecordingsFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadAnimatedRecordingSequenceMap(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()

    def CreateYTDRecordings(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        sub = code_Graphs.Graphs()
        sub.mdiParent = self
        if sub.FillGraph(self.GetRecordingsFilter(), "ytdrecordings") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

    def CreateRecordingsPieChart(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        sub = code_Graphs.Graphs()
        sub.mdiParent = self
        if sub.FillGraph(self.GetRecordingsFilter(), "recordingspie") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

    def CreateTotalRecordingsChart(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        sub = code_Graphs.Graphs()
        sub.mdiParent = self
        if sub.FillGraph(self.GetRecordingsFilter(), "totalrecordings") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

    def CreateRecordingsAccumulationChart(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        sub = code_Graphs.Graphs()
        sub.mdiParent = self
        if sub.FillGraph(self.GetRecordingsFilter(), "recordingsaccumulation") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

    def CreateCumulativeRecordingsChart(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        sub = code_Graphs.Graphs()
        sub.mdiParent = self
        if sub.FillGraph(self.GetRecordingsFilter(), "cumulativerecordings") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()

    def CreateScatterChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "scatter") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreatePhenologyChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        f = self.GetGeneralFilter()
        if f is None:
            return
        if (f.getSpeciesName() == "" and f.getCommonNameSearch() == ""
                and f.getFamily() == "" and f.getOrder() == ""):
            reply = code_Stylesheet.question(
                self,
                "No Species Filter",
                "No species, family, or order filter is set.\n\n"
                "The Phenology Chart is most useful for a species, family, or order. "
                "Generating it for your entire dataset may be too cluttered "
                "to read clearly.\n\n"
                "Generate it anyway?",
            )
            if reply == QMessageBox.StandardButton.No:
                return


        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(f, "strip") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateFOYChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "foy") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateLOYChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "loy") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateLocationScatterChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "locationscatter") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateSpeciesScatterChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "speciesscatter") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateIndivPieChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "indivpie") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateLocationChecklistPieChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "locationchecklistpie") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateFamilyPieChart(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return

        filter = self.GetGeneralFilter()
        if filter is None:
            return

        sub = code_Graphs.Graphs()
        sub.mdiParent = self

        if sub.FillGraph(filter, "familypie") is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
            QTimer.singleShot(0, sub.scaleMe)
        else:
            self.CreateMessageNoResults()
            sub.close()


    def CreateFamiliesReport(self):

        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        
        # create Families Report child window
        sub = code_Families.Families()
        
        # save the MDI window as the parent for future use in the child        
        sub.mdiParent = self
        
        # get filter
        filter = self.GetGeneralFilter()
        if filter is None:
            return

        # call the child's routine to fill it with data
        # these must be called in this exact order, or else the pic chart won't draw
        # large enough to fill its area.  I don't really know why.
        if sub.FillFamilies(filter) is True:
        
            sub.scaleMe()
            sub.resizeMe()
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)        
            sub.show()
                       
            sub.FillPieChart()

            sub.scaleMe()
            
                        
        else:
            
            # abort if no families matched the filter
            self.CreateMessageNoResults()
            sub.close()
        
           
           
    def CreateCompareLists(self):    

        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        
        # create new Compare child window
        sub = code_Compare.Compare()
        
        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self

        # call the child's routine to fill it with data
        if sub.FillListChoices() is True:

            # add and position the child to our MDI area        
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.scaleMe()
            sub.resizeMe()
            sub.show()

        else:
            
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setText("Fewer than two lists are available to compare. \n\nCreate two or more species lists before trying to compare them.")
            msg.setWindowTitle("No Species Lists")
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()            
            sub.close()



    def CreateLocationsList(self):      
        
        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return

        
        filter = self.GetGeneralFilter()
        if filter is None:
            return

        # create a new list child window
        sub = code_Lists.Lists()
        
        # save the MDI window as the parent for future use in the child            
        sub.mdiParent = self

        # call the child's routine to fill it with data
        if sub.FillLocations(filter) is True:
        
            # add and position the child to our MDI area        
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()
            sub.scaleMe()

        else:

            self.CreateMessageNoResults()
            sub.close()

        
        
    def GetFilter(self):
        startDate = ""
        endDate= ""
        startSeasonalMonth = ""
        startSeasonalDay = ""
        endSeasonalMonth = ""
        endSeasonalDay = ""
        locationType = ""
        locationName = "" 
        speciesName = ""
        family = ""
        order = ""
        commonNameSearch = ""
        startRating = ""
        endRating = ""
        speciesHasPhoto = ""
        validPhotoSpecies = []
        camera = ""
        lens = ""
        startShutterSpeed = ""
        endShutterSpeed = ""
        startAperture = ""
        endAperture = ""
        startFocalLength = ""
        endFocalLength = ""
        startIso = ""
        endIso = ""
        
        # check whether calendar widgets are used
        if self.cboDateOptions.currentText() == "Use Calendars Below":
            
            # get yyyy-mm-dd start date string from widget
            startDate = (
                                   str(self.calStartDate.date().year()) 
                                + "-" 
                                + str(self.calStartDate.date().month()) 
                                + "-" 
                                + str(self.calStartDate.date().day()))
            
            # get yyyy-mm-dd end date string from widget
            endDate = (
                                   str(self.calEndDate.date().year()) 
                                + "-" 
                                + str(self.calEndDate.date().month()) 
                                + "-" 
                                + str(self.calEndDate.date().day())
                                )
                                
        # Check if Today radio button is checked.
        # If so, just create yyyy-mm-dd for today.
        if self.cboDateOptions.currentText() == "Today":

            now = datetime.datetime.now()

            startDate = (
                                      str(now.year) 
                                   + "-" 
                                   + str(now.month) 
                                   + "-" 
                                   + str(now.day)
                                   )
            
            # since this is a single day, startDate and endDate are the same
            endDate = startDate    
            
        if self.cboDateOptions.currentText() == "Yesterday":
            now = datetime.datetime.now()
           
           # subtract a day from today to get yesterday
            yesterday = now + datetime.timedelta(days=-1)
            
            # convert to yyyy-mm-dd string
            startDate = (
                                      str(yesterday.year) 
                                   + "-" 
                                   + str(yesterday.month) 
                                   + "-" 
                                   + str(yesterday.day)
                                   )
            
            # since this is a single day, startDate and endDate are the same
            endDate = startDate

        if self.cboDateOptions.currentText() == "Last Weekend":
            now = datetime.datetime.now()
            
            todayDayOfWeek = now.weekday()
           
           # subtract a day from today to get yesterday
            lastSunday = now + datetime.timedelta(days = 0 - todayDayOfWeek - 1)
            lastSaturday = lastSunday + datetime.timedelta(days = -1)
            
            # convert to yyyy-mm-dd string
            startDate = (
                                      str(lastSaturday.year) 
                                   + "-" 
                                   + str(lastSaturday.month) 
                                   + "-" 
                                   + str(lastSaturday.day)
                                   )

            endDate = (
                                      str(lastSunday.year) 
                                   + "-" 
                                   + str(lastSunday.month) 
                                   + "-" 
                                   + str(lastSunday.day)
                                   )

        # Check if This Year radio button is checked.
        # if so, create yyyy-01-01 and yyyy-12-31 start and end dates
        if self.cboDateOptions.currentText() == "This Year":

            now = datetime.datetime.now()

            # set startDate to January 1 of this year
            startDate = str(now.year) + "-01-01"

            # set endDate to December 31 of this year
            endDate = str(now.year) + "-12-31"

        if self.cboDateOptions.currentText() == "Last Year":

            now = datetime.datetime.now()
            lastYear = str(now.year - 1)
            startDate = lastYear + "-01-01"
            endDate = lastYear + "-12-31"

        if self.cboDateOptions.currentText() == "Select Year":
            year = self.cboYear.currentText()
            if year:
                startDate = year + "-01-01"
                endDate = year + "-12-31"

        # Check if This Month radio button is checked
        # if so, create yyyy-mm-01 and yyyy-mm-31 dates
        # We'll need to get the correct number for the last day of the month
        if self.cboDateOptions.currentText() == "This Month":
            
            now = datetime.datetime.now()

            # startDate should be first day of this month
            # convert to yyyy-mm-dd string
            startDate = (
                                      str(now.year) 
                                   + "-" 
                                   + str(now.month) 
                                   + "-" 
                                   + "01"
                                   )
            
            # lastDate is trickier. Need the last day of month, which varies numerically by month.
            # set day to 28 and then add 4 days. This guarantees finding a date in next month
            dayInNextMonth= now.replace(day=28) + datetime.timedelta(days=4)
            
             # Now set the date to 1 so we're at the first day of next month
            firstOfNextMonth = dayInNextMonth.replace(day=1)
            
            # Now subtract a day from the  first of next month, which back into the last day of this month
            lastDayOfThisMonth = firstOfNextMonth + datetime.timedelta(days = -1)
            # convert to yyyy-mm-dd string
            endDate = (
                                     str(lastDayOfThisMonth.year)
                                  + "-"
                                  + str(lastDayOfThisMonth.month)
                                  + "-"
                                  + str(lastDayOfThisMonth.day)
                                  )

        # This Week runs Monday through Sunday of the week containing today.
        if self.cboDateOptions.currentText() == "This Week (M-Su)":

            now = datetime.datetime.now()

            # weekday() is 0=Monday .. 6=Sunday
            monday = now + datetime.timedelta(days = -now.weekday())
            sunday = monday + datetime.timedelta(days = 6)

            startDate = (
                                      str(monday.year)
                                   + "-"
                                   + str(monday.month)
                                   + "-"
                                   + str(monday.day)
                                   )

            endDate = (
                                      str(sunday.year)
                                   + "-"
                                   + str(sunday.month)
                                   + "-"
                                   + str(sunday.day)
                                   )

        # add leading 0 to date digit strings if less than two digits
        # only take action if startDate has a value
        if not startDate == "":
           
            # get the date digit(s) from the yyyy-mm-d(d) string
            # they might be only 1 digit long, hence the need to pad
            startDateDigits = startDate.split("-")[2]
            endDateDigits = endDate.split("-")[2]
            
            if len(startDateDigits) < 2:
                
                # pad with 0, because date is only one digit
                startDateDigits = "0" + startDateDigits
            
            if len(endDateDigits) < 2:
                
                # pad with 0, because date is only one digit
                endDateDigits = "0" + endDateDigits
                
            # add leading 0 to month digit strings if less than two digits
           
            # get the month digit(s) from the yyyy-m(m)-dd string
            # they might be only 1 digit long, hence the need to pad
            startMonthDigits = startDate.split("-")[1]
            endMonthDigits = endDate.split("-")[1]
            
            if len(startMonthDigits) < 2:

                # pad with 0, because month is only one digit                
                startMonthDigits = "0" + startMonthDigits
            
            if len(endMonthDigits) < 2:
                
                # pad with 0, because month is only one digit                
                endMonthDigits = "0" + endMonthDigits 
                
            # reassemble padded Start and End Dates in yyyy-mm-dd string
            startDate = (
                                     startDate[0:4]   # year digits yyyy
                                     + "-" 
                                     + startMonthDigits 
                                     + "-" 
                                     + startDateDigits
                                    )
            
            endDate = (
                                     endDate[0:4]  # year digits yyyy
                                     + "-" 
                                     + endMonthDigits 
                                     + "-" 
                                     + endDateDigits
                                    )

        if self.cboSeasonalRangeOptions.currentText() == "Use Range Below":
           
            # read date month number from combobox, and add one to convert from
           # zero-based to one-based month 
            startSeasonalMonth = str(self.cboStartSeasonalRangeMonth.currentIndex()+1)
           
            # read startSeasonalDay from combobox
            startSeasonalDay = self.cboStartSeasonalRangeDate.currentText()
            
            # read date month number from combobox, and add one to convert from
            # zero-based to one-based month 
            endSeasonalMonth  = str(self.cboEndSeasonalRangeMonth.currentIndex()+1)
            
            # read endSeasonalDay from combobox
            endSeasonalDay  = self.cboEndSeasonalRangeDate.currentText()      
      
            # add leading 0 to seasonal month and date strings if less than two digits
            if len(startSeasonalMonth) < 2:
                startSeasonalMonth = "0" + startSeasonalMonth
            
            if len(startSeasonalDay) < 2:
                startSeasonalDay = "0" + startSeasonalDay    
            
            if len(endSeasonalMonth) < 2:
                endSeasonalMonth = "0" + endSeasonalMonth
            
            if len(endSeasonalDay) < 2:
                endSeasonalDay = "0" + endSeasonalDay                    

        if self.cboSeasonalRangeOptions.currentText() == "Spring":
            startSeasonalMonth = "03"
            startSeasonalDay = "20"
            endSeasonalMonth = "06"
            endSeasonalDay = "19"

        if self.cboSeasonalRangeOptions.currentText() == "Summer":
            startSeasonalMonth = "06"
            startSeasonalDay = "20"
            endSeasonalMonth = "09"
            endSeasonalDay = "19"

        if self.cboSeasonalRangeOptions.currentText() == "Fall":
            startSeasonalMonth = "09"
            startSeasonalDay = "20"
            endSeasonalMonth = "12"
            endSeasonalDay = "19"

        if self.cboSeasonalRangeOptions.currentText() == "Winter":
            startSeasonalMonth = "12"
            startSeasonalDay = "20"
            endSeasonalMonth = "03"
            endSeasonalDay = "19"
         
        if self.cboSeasonalRangeOptions.currentText() == "This Month":
            now = datetime.datetime.now()
            startSeasonalMonth = str(now.month)
            if len(startSeasonalMonth) == 1:
                startSeasonalMonth = "0" + startSeasonalMonth
            endSeasonalMonth = startSeasonalMonth
            startSeasonalDay = "01"
            endSeasonalDay = MainWindow.db.GetLastDayOfMonth(startSeasonalMonth)

        if self.cboSeasonalRangeOptions.currentText() == "Year to Date":
            now = datetime.datetime.now()
            startSeasonalMonth = "01"
            startSeasonalDay = "01"
            endSeasonalMonth = str(now.month)
            endSeasonalDay = str(now.day)
            # add leading 0 to seasonal month and date strings if less than two digits
            if len(endSeasonalMonth) < 2:
                endSeasonalMonth = "0" + endSeasonalMonth
            
            if len(endSeasonalDay) < 2:
                endSeasonalDay = "0" + endSeasonalDay  

        if self.cboSeasonalRangeOptions.currentText() == "Remainder of Year":
            now = datetime.datetime.now()
            startSeasonalMonth = str(now.month)
            startSeasonalDay = str(now.day)
            endSeasonalMonth = "12"
            endSeasonalDay = "31"
            # add leading 0 to seasonal month and date strings if less than two digits
            if len(startSeasonalMonth) < 2:
                startSeasonalMonth = "0" + startSeasonalMonth
            
            if len(endSeasonalDay) < 2:
                startSeasonalDay = "0" + startSeasonalDay 

        monthList = ([
            "January",  
            "February",  
            "March",  
            "April",  
            "May", 
            "June",  
            "July",  
            "August",  
            "September",  
            "October",  
            "November",
            "December"
            ])
        
        if self.cboSeasonalRangeOptions.currentText() in monthList:
            
            startSeasonalMonth = str(monthList.index(self.cboSeasonalRangeOptions.currentText()) + 1)
            # add leading 0 to seasonal month and date strings if less than two digits
            if len(startSeasonalMonth) < 2:
                startSeasonalMonth = "0" + startSeasonalMonth
            endSeasonalMonth = startSeasonalMonth
            startSeasonalDay = "01"
            endSeasonalDay = "31"
            if startSeasonalMonth in ["03", "04", "06", "09", "11"]:
                endSeasonalDay = "30"
            if startSeasonalMonth == "02":
                endSeasonalDay = "29"
                
        # check location comboboxes to learn location type and name
        # Only get location information if user has selected one
        # we'll cycle through cbo boxes, from most general to specific
        # we'll save the most specific one in the filter

        if self.cboRegions.currentText() != None:
            
            if self.cboRegions.currentText() != "All Regions":
                
                # for region name, get the short code,which the db uses for searches
                locationName = MainWindow.db.GetRegionCode(self.cboRegions.currentText())
                locationType = "Region"
                
        if self.cboCountries.currentText() != None:
            
            if self.cboCountries.currentText() != "All Countries":
                
                # for country name, get the short code,which the db uses for searches
                locationName = MainWindow.db.GetCountryCode(self.cboCountries.currentText())
                locationType = "Country"
       
        if self.cboStates.currentText() != None:
            
            if self.cboStates.currentText() != "All States":
                
                # for state name, get the short code, which the db uses for searches
                locationName = MainWindow.db.GetStateCode(self.cboStates.currentText())
                locationType = "State"
      
        if self.cboCounties.currentText() != None:
            
            if self.cboCounties.currentText() != "All Counties":
                
                locationName = self.cboCounties.currentText()
                locationType = "County"
        
        if self.cboLocations.currentText() != None:
            
            if self.cboLocations.currentText() != "All Locations":
                
                locationName = self.cboLocations.currentText()
                locationType = "Location"

        # check species combobox to learn species name
        if self.cboSpecies.currentText() != None:
            
            if self.cboSpecies.currentText() != "All Species":
                
                speciesName = self.cboSpecies.currentText()

        # check order combobox
        if self.cboOrders.currentText() != None:
            
            if self.cboOrders.currentText() != "All Orders":
                
                order = self.cboOrders.currentText()

        # check family combobox
        if self.cboFamilies.currentText() != None:
            
            if self.cboFamilies.currentText() != "All Families":
                
                family = self.cboFamilies.currentText()


        # check Common Name Search test
        if self.txtCommonNameSearch.text() != "":
                
            commonNameSearch = self.txtCommonNameSearch.text().rstrip()               


        # check sighting combobox
        if self.cboStartRatingRange.currentIndex() != 0:
            startRating = self.cboStartRatingRange.currentText()

        # check sighting combobox
        if self.cboEndRatingRange.currentIndex() != 0:
            endRating = self.cboEndRatingRange.currentText()

        # check sighting combobox
        if self.cboSpeciesHasPhoto.currentIndex() != 0:
            speciesHasPhoto = self.cboSpeciesHasPhoto.currentText()

        # check camera combobox
        if self.cboCamera.currentIndex() != 0:
            camera = self.cboCamera.currentText()

        # check lens combobox
        if self.cboLens.currentIndex() != 0:
            lens = self.cboLens.currentText()

        # check start shutter speed combobox
        if self.cboStartShutterSpeedRange.currentIndex() != 0:
            startShutterSpeed = self.cboStartShutterSpeedRange.currentText()

        # check end shutter speed combobox
        if self.cboEndShutterSpeedRange.currentIndex() != 0:
            endShutterSpeed = self.cboEndShutterSpeedRange.currentText()

        # check end aperture combobox
        if self.cboEndApertureRange.currentIndex() != 0:
            endAperture = self.cboEndApertureRange.currentText()

        # check start aperture combobox
        if self.cboStartApertureRange.currentIndex() != 0:
            startAperture = self.cboStartApertureRange.currentText()

        # check end Iso combobox
        if self.cboEndIsoRange.currentIndex() != 0:
            endIso = self.cboEndIsoRange.currentText()

        # check start Iso combobox
        if self.cboStartIsoRange.currentIndex() != 0:
            startIso = self.cboStartIsoRange.currentText()

        # check end FocalLength combobox
        if self.cboEndFocalLengthRange.currentIndex() != 0:
            endFocalLength = self.cboEndFocalLengthRange.currentText()

        # check start FocalLength combobox
        if self.cboStartFocalLengthRange.currentIndex() != 0:
            startFocalLength = self.cboStartFocalLengthRange.currentText()                


                                
        # package up the filter list and return it
        newFilter = code_Filter.Filter()
        newFilter.setLocationType(locationType)
        newFilter.setLocationName(locationName)
        newFilter.setStartDate(startDate)
        newFilter.setEndDate(endDate)
        newFilter.setStartSeasonalMonth(startSeasonalMonth)
        newFilter.setEndSeasonalMonth(endSeasonalMonth)
        newFilter.setStartSeasonalDay(startSeasonalDay)
        newFilter.setEndSeasonalDay(endSeasonalDay)
        newFilter.setSpeciesName(speciesName)
        newFilter.setFamily(family)
        newFilter.setOrder(order)
        newFilter.setCommonNameSearch(commonNameSearch)
        
        newFilter.setStartRating(startRating)
        newFilter.setEndRating(endRating)
        newFilter.setSpeciesHasPhoto(speciesHasPhoto)        
        newFilter.setCamera(camera)
        newFilter.setLens(lens)
        newFilter.setStartShutterSpeed(startShutterSpeed)
        newFilter.setEndShutterSpeed(endShutterSpeed)
        newFilter.setStartAperture(startAperture)
        newFilter.setEndAperture(endAperture)
        newFilter.setStartIso(startIso)
        newFilter.setEndIso(endIso)
        newFilter.setStartFocalLength(startFocalLength)
        newFilter.setEndFocalLength(endFocalLength)
        
        # use the filter set up so far to get the valid Photo species
        # do this only if the user has set the species photo cbo box
        if self.cboSpeciesHasPhoto.currentText() == "Photographed":
            validPhotoSpecies = self.db.GetSpeciesWithPhotos(newFilter)
            newFilter.setValidPhotoSpecies(validPhotoSpecies)

        if self.cboSpeciesHasPhoto.currentText() == "Not photographed":
            validPhotoSpecies = self.db.GetSpeciesWithoutPhotos(newFilter)
            newFilter.setValidPhotoSpecies(validPhotoSpecies)

        # audio filter fields
        if self.cboStartRecordingsRatingRange.currentIndex() != 0:
            newFilter.setStartRecordingRating(self.cboStartRecordingsRatingRange.currentText())
        if self.cboEndRecordingsRatingRange.currentIndex() != 0:
            newFilter.setEndRecordingRating(self.cboEndRecordingsRatingRange.currentText())
        if self.cboSpeciesHasRecording.currentIndex() != 0:
            newFilter.setSpeciesHasRecording(self.cboSpeciesHasRecording.currentText())
        if self.cboChannels.currentIndex() != 0:
            newFilter.setChannels(self.cboChannels.currentText())
        if self.cboStartRecordingsDurationRange.currentIndex() != 0:
            newFilter.setStartDuration(self.cboStartRecordingsDurationRange.currentText())
        if self.cboEndRecordingsDurationRange.currentIndex() != 0:
            newFilter.setEndDuration(self.cboEndRecordingsDurationRange.currentText())
        if self.cboStartRecordingsSampleRateRange.currentIndex() != 0:
            newFilter.setStartSampleRate(self.cboStartRecordingsSampleRateRange.currentText())
        if self.cboEndRecordingsSampleRateRange.currentIndex() != 0:
            newFilter.setEndSampleRate(self.cboEndRecordingsSampleRateRange.currentText())
        checkedDepths = [chk.text() for chk in getattr(self, "_bitDepthChecks", []) if chk.isChecked()]
        if checkedDepths:
            newFilter.setBitDepths(checkedDepths)
        if self.cboRecordingsDevice.currentIndex() != 0:
            newFilter.setDevice(self.cboRecordingsDevice.currentText())

        if self.cboSpeciesHasRecording.currentText() == "Recorded":
            newFilter.setValidRecordingSpecies(self.db.GetSpeciesWithRecordings(newFilter))
        if self.cboSpeciesHasRecording.currentText() == "Not recorded":
            newFilter.setValidRecordingSpecies(self.db.GetSpeciesWithoutRecordings(newFilter))

        return(newFilter)

    def GetPhotoFilter(self):
        """Filter for Photo-menu queries: recording filter fields are cleared."""
        f = self.GetFilter()
        f.clearRecordingFilter()
        return f

    def GetRecordingsFilter(self):
        """Filter for Recordings-menu queries: photo filter fields are cleared."""
        f = self.GetFilter()
        f.clearPhotoFilter()
        return f

    def GetGeneralFilter(self):
        """Filter for general queries. Shows a conflict dialog if both media sections
        have active settings and lets the user choose which to apply.
        Returns None if the user cancels."""
        f = self.GetFilter()
        if f.hasPhotoFilter() and f.hasRecordingFilter():
            choice = code_Stylesheet.mediaFilterConflict(self)
            if choice == "photos":
                f.clearRecordingFilter()
            elif choice == "recordings":
                f.clearPhotoFilter()
            else:
                return None
        return f
                           
                                      
    def updateEXIFDataForAllPhotos(self):

        # Respect the current Sighting Filter and Photo (Media) Filter so the
        # user can refresh EXIF data for just a subset of photos. The recording
        # side of the media filter is irrelevant here, so clear it to avoid the
        # media-conflict prompt in GetGeneralFilter.
        filter = self.GetFilter()
        filter.clearRecordingFilter()

        # get the filtered sightings with photos
        sightings = self.db.GetSightingsWithPhotos(filter)

        # loop through the filtered photos, and refresh each photo's EXIF data
        updated = 0
        skipped = 0
        for s in sightings:
            for pCount, p in enumerate(s["photos"]):
                # skip files no longer on disk so we don't wipe good EXIF data
                if not os.path.isfile(p["fileName"]):
                    skipped += 1
                    continue
                photoData = self.db.getPhotoData(p["fileName"])
                # preserve the user's rating and notes (getPhotoData blanks them)
                photoData["rating"] = p["rating"]
                photoData["notes"] = p.get("notes", "")
                s["photos"][pCount] = photoData
                updated += 1

        # rebuild the photo (and recording) filter metadata lists from the full
        # catalog so values for photos outside this subset are retained
        self.db.refreshPhotoLists()

        # clear and repopulate photo filter cbo boxes with updated data
        self.fillPhotoComboBoxes()

        # Persist to JSONL: compact rewrites all in-memory photo data.
        # If no JSONL file is open, checkIfPhotoDataNeedSaving prompts the user to create one.
        self.db.photosNeedSaving = True
        self.checkIfPhotoDataNeedSaving()

        msg = (f"EXIF data updated for {updated} attached photo(s)."
               f"\n\nFilter: {filter.describeScope(self.db)}")
        if skipped:
            msg += f"\n\n{skipped} file(s) were not found on disk and were not updated."
        QMessageBox.information(
            self, "Updated EXIF Data", msg, QMessageBox.StandardButton.Ok,
        )
        
        
    def updateRecordingDataForAll(self):
        # Respect the current Sighting Filter and Recording (Media) Filter so the
        # user can refresh just a subset of recordings. The photo side of the
        # media filter is irrelevant here, so clear it to avoid the media-conflict
        # prompt in GetGeneralFilter.
        filter = self.GetFilter()
        filter.clearPhotoFilter()

        sightings = self.db.GetSightingsWithRecordings(filter)

        updated = 0
        skipped = 0
        for s in sightings:
            for i, a in enumerate(s["audio"]):
                fn = a["fileName"]
                if not os.path.isfile(fn):
                    skipped += 1
                    continue
                fresh = self.db.getRecordingData(fn)
                # preserve the user's rating and notes (getRecordingData blanks them)
                fresh["rating"] = a.get("rating", "0")
                fresh["notes"] = a.get("notes", "")
                s["audio"][i] = fresh
                updated += 1

        self.db.refreshRecordingsLists()
        self.fillRecordingsComboBoxes()

        self.db.photosNeedSaving = True
        self.checkIfPhotoDataNeedSaving()
        self.notifyMediaChanged()

        msg = (f"Updated recording data for {updated} recording(s)."
               f"\n\nFilter: {filter.describeScope(self.db)}")
        if skipped:
            msg += f"\n\n{skipped} file(s) were not found on disk and were not updated."
        QMessageBox.information(
            self, "Updated Recording Data", msg, QMessageBox.StandardButton.Ok
        )


    def SeasonalRangeClicked(self):
        self.cboSeasonalRangeOptions.setCurrentIndex(1)
        
        
    def TileWindows(self):
        # Restore any minimized windows first
        for w in self.mdiArea.subWindowList():
            if w.isMinimized():
                w.showNormal()
        self.mdiArea.tileSubWindows()
        
        
    def CascadeWindows(self):
        # Restore any minimized or maximized windows first
        for w in self.mdiArea.subWindowList():
            if w.isMinimized() or w.isMaximized():
                w.showNormal()

        # Get windows in stacking order (back-most first, front-most last)
        visibleWindows = [w for w in self.mdiArea.subWindowList(QMdiArea.WindowOrder.StackingOrder) if w.isVisible()]
        if not visibleWindows:
            return

        # Scale every window to its default size first
        for w in visibleWindows:
            if w.windowTitle() != "Enlargement":
                w.scaleMe()

        # Cascade: position each window offset by title bar height from the previous,
        # and raise_ each in order so z-order matches cascade position
        titleBarHeight = 25
        x, y = 0, 0
        for w in visibleWindows:
            w.move(x, y)
            w.raise_()
            x += titleBarHeight
            y += titleBarHeight
        
    def CloseAllWindows(self):
        self.mdiArea.closeAllSubWindows()


    def _closePhotoDependentWindows(self):
        """Close every child window that displays data from the media catalog."""
        _PHOTO_GRAPH_TYPES = {"totalphotos", "ytdphotos", "photopie",
                              "photoaccumulation", "cumulativephotos"}
        _PHOTO_MAP_TITLES  = {"Geolocated Photos", "Animated Sequence Map"}

        for w in list(self.mdiArea.subWindowList()):
            if isinstance(w, (code_Photos.Photos,
                               code_SpeciesGallery.SpeciesGallery,
                               code_ManagePhotos.ManagePhotos)):
                w.close()
            elif w.objectName() == "frmEnlargement":
                w.close()
            elif (isinstance(w, code_Web.Web) and
                  getattr(w, "title", "") in _PHOTO_MAP_TITLES):
                w.close()
            elif (isinstance(w, code_Graphs.Graphs) and
                  getattr(w, "_chart_type", "") in _PHOTO_GRAPH_TYPES):
                w.close()


    def HideMainWindowOptions(self):
        self.clearStandardFilter()
        self.clearMediaFilter()
        self.dckFilter.setVisible(False)
        self.dckMediaFilter.setVisible(False)
        self.actionClose.setVisible(False)
        self.actionOpenPhotoSettings.setVisible(False)
        self.actionAddPhotos.setVisible(False)
        self.actionAddRecordings.setVisible(False)
        self.actionRebuildThumbnailCache.setVisible(False)
        self.menuPhotos.menuAction().setVisible(False)
        self.menuRecordings.menuAction().setVisible(False)
        self.actionManageRecordings.setVisible(False)
        self.actionRecordingsToolbar.setVisible(False)
        self._hidePhotoCatalogMenuItems()


    def ShowMainWindowOptions(self):
        self.dckFilter.setVisible(True)


    def SetChildDetailsLabels(self,  sub,  filter):
        locationType = filter.getLocationType()                             # str   choices are Country, County, State, Location, or ""
        locationName = filter.getLocationName()                         # str   name of region or location  or ""
        startDate = filter.getStartDate()                                           # str   format yyyy-mm-dd  or ""
        endDate = filter.getEndDate()                                               # str   format yyyy-mm-dd  or ""
        startSeasonalMonth = filter.getStartSeasonalMonth() # str   format mm
        startSeasonalDay = filter.getStartSeasonalDay()            # str   format dd
        endSeasonalMonth  = filter.getEndSeasonalMonth()    # str   format  dd
        endSeasonalDay  = filter.getEndSeasonalDay()               # str   format dd
        checklistID = filter.getChecklistID()                                     # str   checklistID
        speciesName = filter.getSpeciesName()                           # str   speciesName
        family = filter.getFamily()                                                         # str family name
        order = filter.getOrder()
        commonNameSearch = filter.getCommonNameSearch()
        sightingPhotographed = filter.getSightingHasPhoto()
        speciesPhotographed = filter.getSpeciesHasPhoto()
        camera = filter.getCamera()
        lens = filter.getLens()
        startShutterSpeed = filter.getStartShutterSpeed()
        endShutterSpeed = filter.getEndShutterSpeed()
        startAperture = filter.getStartAperture()
        endAperture = filter.getEndAperture()
        startIso = filter.getStartIso()
        endIso = filter.getEndIso()
        startFocalLength = filter.getStartFocalLength()
        endFocalLength = filter.getEndFocalLength()
        speciesRecorded = filter.getSpeciesHasRecording()
        channels = filter.getChannels()
        startRecordingRating = filter.getStartRecordingRating()
        endRecordingRating = filter.getEndRecordingRating()
        startDuration = filter.getStartDuration()
        endDuration = filter.getEndDuration()
        startSampleRate = filter.getStartSampleRate()
        endSampleRate = filter.getEndSampleRate()
        bitDepths = filter.getBitDepths()
        device = filter.getDevice()

        # set main location label, using "All Locations" if none others are selected
        if locationName == "":   
            sub.lblLocation.setText("All Locations")
        else:
            if locationType == "Region":
                sub.lblLocation.setText(MainWindow.db.GetRegionName(locationName))
            elif locationType == "Country":
                sub.lblLocation.setText(MainWindow.db.GetCountryName(locationName))
            elif locationType == "State":
                sub.lblLocation.setText(MainWindow.db.GetStateName(locationName))       
            else:
                sub.lblLocation.setText(locationName)
        
        if speciesName != "":
            sub.lblLocation.setText(speciesName +": " + sub.lblLocation.text())
            
        # set main date range label, using "AllDates" if none others are selected
        detailsText = ""
        dateText = ""
        
        if startDate == "":
            dateText = "; All Dates"
        else:
            dateTitle = startDate + " to " + endDate
            if startDate == endDate:
                dateTitle = startDate
            if checklistID != "":
                dateTitle = dateTitle + ": Checklist #" + checklistID
            dateText = "; " + dateTitle

        # set main seasonal range label, if specified
        if not ((startSeasonalMonth == "") or (endSeasonalMonth == "")):
            monthRange = ["Jan",  "Feb",  "Mar",  "Apr", "May",   "Jun",  "Jul",  "Aug",  "Sep",  "Oct",  "Nov",  "Dec"]
            rangeTitle = monthRange[int(startSeasonalMonth)-1] + "-" + startSeasonalDay + " to " + monthRange[int(endSeasonalMonth)-1] + "-" + endSeasonalDay
            dateText = dateText + "; " + rangeTitle
       
        if checklistID != "":
            detailsText = "; Checklist " + checklistID

        if order != "":
            detailsText = detailsText + "; " + order
        
        if family != "":
            detailsText = detailsText + "; " + family
            
        if commonNameSearch != "":
            if "s:" in commonNameSearch:
                detailsText = detailsText + "; Scientific name includes '" +  commonNameSearch.split("s:",1)[1]  + "'"
            else:
                detailsText = detailsText + "; Common name includes '" +  commonNameSearch + "'"

        if sightingPhotographed == "Has photo":
            detailsText = detailsText + "; " + "Sightings with photos"
        if sightingPhotographed == "No photo":
            detailsText = detailsText + "; " + "Sightings without photos"

        if speciesPhotographed == "Photographed":
            detailsText = detailsText + "; " + "Photographed species"
        if speciesPhotographed == "Not photographed":
            detailsText = detailsText + "; " + "Unphotographed species"
            
        if camera != "":
            detailsText = detailsText + "; " + camera            

        if lens != "":
            detailsText = detailsText + "; " + lens
            
        if startShutterSpeed != "" and endShutterSpeed != "":
            if startShutterSpeed == endShutterSpeed:
                detailsText = detailsText + "; Speed: " + startShutterSpeed
            else:
                detailsText = detailsText + "; Speed: " + startShutterSpeed + " to " + endShutterSpeed 
        if startShutterSpeed != "" and endShutterSpeed == "":
            detailsText = detailsText + "; Speed: from " + startShutterSpeed
        if startShutterSpeed == "" and endShutterSpeed != "":
            detailsText = detailsText + "; Speed: to " + endShutterSpeed

        if startAperture != "" and endAperture != "":
            if startAperture == endAperture:
                detailsText = detailsText + "; Aperture: " + startAperture
            else:
                detailsText = detailsText + "; Aperture: " + startAperture + " to " + endAperture 
        if startAperture != "" and endAperture == "":
            detailsText = detailsText + "; Aperture: from " + startAperture
        if startAperture == "" and endAperture != "":
            detailsText = detailsText + "; Aperture: to " + endAperture
            
        if startFocalLength != "" and endFocalLength != "":
            if startFocalLength == endFocalLength:
                detailsText = detailsText + "; Focal Length: " + startFocalLength
            else:
                detailsText = detailsText + "; Focal Length: " + startFocalLength + " to " + endFocalLength 
        if startFocalLength != "" and endFocalLength == "":
            detailsText = detailsText + "; Focal Length: from " + startFocalLength
        if startFocalLength == "" and endFocalLength != "":
            detailsText = detailsText + "; Focal Length: to " + endFocalLength
            
        if startIso != "" and endIso != "":
            if startIso == endIso:
                detailsText = detailsText + "; ISO: " + startIso
            else:
                detailsText = detailsText + "; ISO: " + startIso + " to " + endIso 
        if startIso != "" and endIso == "":
            detailsText = detailsText + "; ISO: from " + startIso
        if startIso == "" and endIso != "":
            detailsText = detailsText + "; ISO: to " + endIso

        # recording (audio) filter fields
        if speciesRecorded == "Recorded":
            detailsText = detailsText + "; Recorded species"
        if speciesRecorded == "Not recorded":
            detailsText = detailsText + "; Unrecorded species"

        if channels != "":
            detailsText = detailsText + "; " + channels

        if startRecordingRating != "" and endRecordingRating != "":
            if startRecordingRating == endRecordingRating:
                detailsText = detailsText + "; Recording rating: " + startRecordingRating
            else:
                detailsText = detailsText + "; Recording rating: " + startRecordingRating + " to " + endRecordingRating
        if startRecordingRating != "" and endRecordingRating == "":
            detailsText = detailsText + "; Recording rating: from " + startRecordingRating
        if startRecordingRating == "" and endRecordingRating != "":
            detailsText = detailsText + "; Recording rating: to " + endRecordingRating

        if startDuration != "" and endDuration != "":
            if startDuration == endDuration:
                detailsText = detailsText + "; Duration: " + startDuration
            else:
                detailsText = detailsText + "; Duration: " + startDuration + " to " + endDuration
        if startDuration != "" and endDuration == "":
            detailsText = detailsText + "; Duration: from " + startDuration
        if startDuration == "" and endDuration != "":
            detailsText = detailsText + "; Duration: to " + endDuration

        if startSampleRate != "" and endSampleRate != "":
            if startSampleRate == endSampleRate:
                detailsText = detailsText + "; Sample rate: " + startSampleRate
            else:
                detailsText = detailsText + "; Sample rate: " + startSampleRate + " to " + endSampleRate
        if startSampleRate != "" and endSampleRate == "":
            detailsText = detailsText + "; Sample rate: from " + startSampleRate
        if startSampleRate == "" and endSampleRate != "":
            detailsText = detailsText + "; Sample rate: to " + endSampleRate

        if bitDepths:
            detailsText = detailsText + "; " + ", ".join(bitDepths)

        if device != "":
            detailsText = detailsText + "; " + device

        #remove leading "; "
        dateText = dateText[2:]
        detailsText = detailsText[2:]
        
        sub.lblDateRange.setText(dateText)
        if dateText =="":
            sub.lblDateRange.setVisible(False)
        else:
            sub.lblDateRange.setVisible(True)
            
        sub.lblDetails.setText(detailsText)
        if detailsText =="":
            sub.lblDetails.setVisible(False)
        else:
            sub.lblDetails.setVisible(True)
       
    
    def FillMainComboBoxes(self):
        
        # use the master lists in db to populate the 4 location comboboxes
        self.fillingLocationComboBoxesFlag = True

        self.cboRegions.clear()
        self.cboRegions.addItem("All Regions")
        self.cboRegions.insertSeparator(1)
        self.cboRegions.addItems(MainWindow.db.regionList)

        self.cboCountries.clear()
        self.cboCountries.addItem("All Countries")
        self.cboCountries.insertSeparator(1)
        self.cboCountries.addItems(MainWindow.db.countryList)

        self.cboStates.clear()
        self.cboStates.addItem("All States")
        self.cboStates.insertSeparator(1)
        self.cboStates.addItems(MainWindow.db.stateList)

        self.cboCounties.clear()
        self.cboCounties.addItem("All Counties")
        self.cboCounties.insertSeparator(1)
        self.cboCounties.addItems(MainWindow.db.countyList)

        self.cboLocations.clear()
        self.cboLocations.addItem("All Locations")
        self.cboLocations.insertSeparator(1)
        self.cboLocations.addItems(MainWindow.db.locationList)

        self.cboSpecies.clear()
        self.cboSpecies.addItem("All Species")
        self.cboSpecies.insertSeparator(1)
        self.cboSpecies.addItems(sorted(MainWindow.db.speciesDict.keys()))

        self.cboFamilies.clear()
        self.cboFamilies.addItem("All Families")
        self.cboFamilies.insertSeparator(1)
        self.cboFamilies.addItems(MainWindow.db.familyList)

        self.cboOrders.clear()
        self.cboOrders.addItem("All Orders")
        self.cboOrders.insertSeparator(1)
        self.cboOrders.addItems(MainWindow.db.orderList)

        self.cboYear.clear()
        years = sorted({s["date"][0:4] for s in MainWindow.db.sightingList}, reverse=True)
        self.cboYear.addItems(years)

        self.fillingLocationComboBoxesFlag = False
                

    def printMe(self):

        activeWindow = self.mdiArea.activeSubWindow()            

        if activeWindow is None:
            return

        if activeWindow.objectName() in ([
            "frmSpeciesList",
            "frmFamilies",
            "frmCompare",
            "frmDateTotals",
            "frmLocationTotals",
            "frmWeb",
            "frmIndividual",
            "frmLocation",
            "frmBigReport",
            "frmPhotos",
            "frmSpeciesGallery",
            ]):

            if activeWindow.objectName() in ("frmPhotos", "frmSpeciesGallery"):
                n = (len(activeWindow.photoList)
                     if activeWindow.objectName() == "frmPhotos"
                     else len(activeWindow._galleryItems))
                pages = ceil(n / 6)
                reply = code_Stylesheet.question(
                    self,
                    "Confirm Print",
                    f"This will generate approximately {pages} page{'s' if pages != 1 else ''} "
                    f"({n} photo{'s' if n != 1 else ''}). Continue?",
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            # create a QTextDocument in memory to hold and render our content
            document = QTextDocument()

            # create a QPrinter object for the printer the user later selects
            printer = QPrinter()
        
            # get html content from child window
            html = activeWindow.html()

            # load the html into the document
            document.setHtml(html)

            # let user select and configure a printer
            dialog = QPrintDialog(printer, self) 

            # execute the print if the user clicked "Print"
            if dialog.exec():

                # send the html to the physical printer
                document.print_(printer)

        else:
            QMessageBox.information(
                self,
                "Printing Not Available",
                "Printing is not available for this window.",
                QMessageBox.StandardButton.Ok,
            )


    def ResetMainWindow(self):

        self.CloseAllWindows()
        self.clearAllFilters()
        self.hideStandardFilter()
        self.hideMediaFilter()
        self.actionClose.setVisible(False)
        self.actionOpenPhotoSettings.setVisible(False)
        self.actionAddPhotos.setVisible(False)
        self.actionAddRecordings.setVisible(False)
        self.actionRebuildThumbnailCache.setVisible(False)
        self.menuPhotos.menuAction().setVisible(False)
        self.menuRecordings.menuAction().setVisible(False)
        self.actionManageRecordings.setVisible(False)
        self._hidePhotoCatalogMenuItems()
        self.db.ClearDatabase()


    def _refillTaxonomyCombosForFilter(self, f):
        """Repopulate Order/Family/Species combos with only options present in location+date
        filtered sightings. Must be called while fillingLocationComboBoxesFlag is True."""
        f.setOrder("")
        f.setFamily("")
        f.setSpeciesName("")
        f.setSpeciesList([])

        sightings = MainWindow.db.GetSightings(f)

        seen_species = set()
        seen_families = set()
        seen_orders = set()
        for s in sightings:
            seen_species.add(s["commonName"])
            if s["family"]: seen_families.add(s["family"])
            if s["order"]:  seen_orders.add(s["order"])

        filtered_orders   = [o for o in MainWindow.db.orderList  if o in seen_orders]
        filtered_families = [fam for fam in MainWindow.db.familyList if fam in seen_families]
        filtered_species  = sorted(sp for sp in MainWindow.db.speciesDict.keys() if sp in seen_species)

        self.cboOrders.setStyleSheet("")
        self.cboOrders.clearFocus()
        self.cboFamilies.setStyleSheet("")
        self.cboFamilies.clearFocus()
        self.cboSpecies.setStyleSheet("")
        self.cboSpecies.clearFocus()
        self.cboOrders.clear()
        self.cboFamilies.clear()
        self.cboSpecies.clear()

        self.cboOrders.addItem("All Orders")
        self.cboOrders.insertSeparator(1)
        self.cboOrders.addItems(filtered_orders)

        self.cboFamilies.addItem("All Families")
        self.cboFamilies.insertSeparator(1)
        self.cboFamilies.addItems(filtered_families)

        self.cboSpecies.addItem("All Species")
        self.cboSpecies.insertSeparator(1)
        self.cboSpecies.addItems(filtered_species)


    def ComboRegionsChanged(self):

        # Check whether the program is adding locations while reading the data file
        # if so, abort. If not, the user has clicked the combobox and we should proceed
        if self.fillingLocationComboBoxesFlag is False:
                  
            # set the flag to True so the state, county, and location cbos won't trigger
            self.fillingLocationComboBoxesFlag = True    
            
            # clear the color coding for selected filter components
            self.cboRegions.setStyleSheet("")
            self.cboCountries.setStyleSheet("")
            self.cboCountries.clearFocus()
            self.cboStates.setStyleSheet("")
            self.cboStates.clearFocus()
            self.cboCounties.setStyleSheet("")
            self.cboCounties.clearFocus()
            self.cboLocations.setStyleSheet("")
            self.cboLocations.clearFocus()

            # use the selected region to filter the masterLocationList
            # clear the subsidiary comboboxes and populate them anew with filtered locations
            thisRegionName = self.cboRegions.currentText()
            thisRegionCode = MainWindow.db.GetRegionCode(self.cboRegions.currentText())
            self.cboCountries.clear()
            self.cboStates.clear()
            self.cboCounties.clear()
            self.cboLocations.clear()
            
            # if "all regions" is chosen, fill subsidiary cbos with all locations
            # e.g., remove the country filter, if one had existed for the cbos
            if thisRegionName == "All Regions":
                self.cboRegions.setStyleSheet("");
                self.cboCountries.addItem("All Countries")
                self.cboCountries.insertSeparator(1)
                self.cboStates.addItem("All States")
                self.cboStates.insertSeparator(1)
                self.cboCounties.addItem("All Counties")
                self.cboCounties.insertSeparator(1)
                self.cboLocations.addItem("All Locations")
                self.cboLocations.insertSeparator(1)
                self.cboCountries.addItems(MainWindow.db.countryList)
                self.cboStates.addItems(MainWindow.db.stateList)
                self.cboCounties.addItems(MainWindow.db.countyList)
                self.cboLocations.addItems(MainWindow.db.locationList)
            
            else:

                self.cboRegions.setStyleSheet("QComboBox { color: #4f8ef7; }")
                
                # initialize lists to store the subsidiary locations
                thisRegionCountries = set()
                thisRegionStates = set()
                thisRegionCounties = set()
                thisRegionLocations = set()
                
                # loop through masterLocationList to find locations filtered for the chosen region
                for l in MainWindow.db.masterLocationList:
                    
                    if thisRegionCode in l["regionCodes"]:
                                                
                        if "countryName" in l.keys():
                            if l["countryName"] != "": thisRegionCountries.add(l["countryName"])
                        
                        if "stateName" in l.keys():
                            if l["stateName"] != "": thisRegionStates.add(l["stateName"])
                        
                        if "county" in l.keys():
                            if l["county"] != "": thisRegionCounties.add(l["county"])
                            
                        if l["location"] != "": thisRegionLocations.add(l["location"])
                
                # remove duplicates using the set command, then return to list format
                thisRegionCountries = list(thisRegionCountries)
                thisRegionStates = list(thisRegionStates)
                thisRegionCounties = list(thisRegionCounties)
                thisRegionLocations = list(thisRegionLocations)
                
                # sort them
                thisRegionCountries.sort()
                thisRegionStates.sort()
                thisRegionCounties.sort()
                thisRegionLocations.sort()
                
                # add filtered locations to comboboxes
                self.cboCountries.addItem("All Countries")
                self.cboCountries.insertSeparator(1)
                self.cboCountries.addItems(thisRegionCountries)
                self.cboStates.addItem("All States")
                self.cboStates.insertSeparator(1)
                self.cboStates.addItems(thisRegionStates)
                self.cboCounties.addItem("All Counties")
                self.cboCounties.insertSeparator(1)
                self.cboCounties.addItems(thisRegionCounties)
                self.cboLocations.addItem("All Locations")
                self.cboLocations.insertSeparator(1)
                self.cboLocations.addItems(thisRegionLocations)

            self._refillTaxonomyCombosForFilter(self.GetFilter())

            # we're done, so reset flag to false to allow future triggers
            self.fillingLocationComboBoxesFlag = False




    def ComboCountriesChanged(self):
        
        # Check whether the program is adding locations while reading the data file
        # if so, abort. If not, the user has clicked the combobox and we should proceed
        if self.fillingLocationComboBoxesFlag is False:  
                  
            # set the flag to True so the state, county, and location cbos won't trigger
            self.fillingLocationComboBoxesFlag = True    
            
            # clear the color coding for selected filter components
            self.cboRegions.setStyleSheet("")
            self.cboCountries.setStyleSheet("")
            self.cboStates.setStyleSheet("")
            self.cboStates.clearFocus()
            self.cboCounties.setStyleSheet("")
            self.cboCounties.clearFocus()
            self.cboLocations.setStyleSheet("")
            self.cboLocations.clearFocus()

            # use the selected country to filter the masterLocationList
            # clear the subsidiary comboboxes and populate them anew with filtered locations
            thisCountry = self.cboCountries.currentText()
            self.cboStates.clear()
            self.cboCounties.clear()
            self.cboLocations.clear()
            
            # if "all countries" is chosen, fill subsidiary cbos with all locations
            # e.g., remove the country filter, if one had existed for the cbos
            if thisCountry == "All Countries":
                self.cboCountries.setStyleSheet("");
                self.cboStates.addItem("All States")
                self.cboStates.insertSeparator(1)
                self.cboCounties.addItem("All Counties")
                self.cboCounties.insertSeparator(1)
                self.cboLocations.addItem("All Locations")
                self.cboLocations.insertSeparator(1)
                self.cboStates.addItems(MainWindow.db.stateList)
                self.cboCounties.addItems(MainWindow.db.countyList)
                self.cboLocations.addItems(MainWindow.db.locationList)
                self.cboCountries.setStyleSheet("");
            
            else:

                self.cboCountries.setStyleSheet("QComboBox { color: #4f8ef7; }")
                
                # initialize lists to store the subsidiary locations
                thisCountryStates = set()
                thisCountryCounties = set()
                thisCountryLocations = set()

                # loop through masterLocationList to find locations filtered for the chose country
                for l in MainWindow.db.masterLocationList:
                    if "countryName" in l.keys():
                    
                        if l["countryName"] == thisCountry:

                            if "stateName" in l.keys():
                                if l["stateName"] != "": thisCountryStates.add(l["stateName"])

                            if l["county"] != "": thisCountryCounties.add(l["county"])
                            if l["location"] != "": thisCountryLocations.add(l["location"])
                
                # remove duplicates using the set command, then return to list format
                thisCountryStates = list(thisCountryStates)
                thisCountryCounties = list(thisCountryCounties)
                thisCountryLocations = list(thisCountryLocations)
                
                # sort them
                thisCountryStates.sort()
                thisCountryCounties.sort()
                thisCountryLocations.sort()
                
                # add filtered locations to comboboxes
                self.cboStates.addItem("All States")
                self.cboStates.insertSeparator(1)
                self.cboStates.addItems(thisCountryStates)
                self.cboCounties.addItem("All Counties")
                self.cboCounties.insertSeparator(1)
                self.cboCounties.addItems(thisCountryCounties)
                self.cboLocations.addItem("All Locations")
                self.cboLocations.insertSeparator(1)
                self.cboLocations.addItems(thisCountryLocations)

            self._refillTaxonomyCombosForFilter(self.GetFilter())

            # we're done, so reset flag to false to allow future triggers
            self.fillingLocationComboBoxesFlag = False


    def ComboDateOptionsChanged(self):
        
        if self.fillingLocationComboBoxesFlag is False:
            
            thisOption = self.cboDateOptions.currentText()
            
            # Show the year picker only when "Select Year" is selected
            self.cboYear.setVisible(thisOption == "Select Year")
            if thisOption != "Select Year":
                self.unhighlightFilterElement(self.cboYear)

            if thisOption == "No Date Filter":
                self.cboDateOptions.setStyleSheet("");
                self.calStartDate.setStyleSheet("")
                self.calEndDate.setStyleSheet("")

            elif thisOption == "Use Calendars Below":
                self.highlightFilterElement(self.cboDateOptions)
                self.highlightFilterElement(self.calStartDate)
                self.highlightFilterElement(self.calEndDate)

            elif thisOption == "Select Year":
                self.highlightFilterElement(self.cboDateOptions)
                self.highlightFilterElement(self.cboYear)
                self.highlightFilterElement(self.calStartDate)
                self.highlightFilterElement(self.calEndDate)
                year = self.cboYear.currentText()
                if year:
                    self.setDateFilter(year + "-01-01", year + "-12-31", setCombo=False)

            else:
                self.highlightFilterElement(self.cboDateOptions)
                self.highlightFilterElement(self.calStartDate)
                self.highlightFilterElement(self.calEndDate)

                now = datetime.datetime.now()
                if thisOption == "Today":
                    startDate = endDate = now.strftime("%Y-%m-%d")
                elif thisOption == "Yesterday":
                    yesterday = now + datetime.timedelta(days=-1)
                    startDate = endDate = yesterday.strftime("%Y-%m-%d")
                elif thisOption == "Last Weekend":
                    lastSunday = now + datetime.timedelta(days=0 - now.weekday() - 1)
                    lastSaturday = lastSunday + datetime.timedelta(days=-1)
                    startDate = lastSaturday.strftime("%Y-%m-%d")
                    endDate = lastSunday.strftime("%Y-%m-%d")
                elif thisOption == "This Year":
                    startDate = now.strftime("%Y-01-01")
                    endDate = now.strftime("%Y-12-31")
                elif thisOption == "Last Year":
                    lastYear = str(now.year - 1)
                    startDate = lastYear + "-01-01"
                    endDate = lastYear + "-12-31"
                elif thisOption == "This Month":
                    startDate = now.strftime("%Y-%m-01")
                    dayInNextMonth = now.replace(day=28) + datetime.timedelta(days=4)
                    lastDay = dayInNextMonth.replace(day=1) + datetime.timedelta(days=-1)
                    endDate = lastDay.strftime("%Y-%m-%d")
                elif thisOption == "This Week (M-Su)":
                    monday = now + datetime.timedelta(days=-now.weekday())
                    sunday = monday + datetime.timedelta(days=6)
                    startDate = monday.strftime("%Y-%m-%d")
                    endDate = sunday.strftime("%Y-%m-%d")
                self.setDateFilter(startDate, endDate, setCombo=False)


    def ComboYearChanged(self):
        if self.fillingLocationComboBoxesFlag is False:
            year = self.cboYear.currentText()
            if year:
                self.highlightFilterElement(self.cboYear)
                self.setDateFilter(year + "-01-01", year + "-12-31", setCombo=False)


    def ComboFamiliesChanged(self):

        if self.fillingLocationComboBoxesFlag is False:

            self.fillingLocationComboBoxesFlag = True
            thisFamily = self.cboFamilies.currentText()

            if thisFamily == "All Families":
                self.cboFamilies.setStyleSheet("")
            else:
                self.highlightFilterElement(self.cboFamilies)

            # Repopulate Species from location+date+order+family filtered sightings
            f = self.GetFilter()
            f.setSpeciesName("")
            f.setSpeciesList([])
            sightings = MainWindow.db.GetSightings(f)
            seen_species = set(s["commonName"] for s in sightings)
            filtered_species = sorted(sp for sp in MainWindow.db.speciesDict.keys() if sp in seen_species)

            self.cboSpecies.setStyleSheet("")
            self.cboSpecies.clearFocus()
            self.cboSpecies.clear()
            self.cboSpecies.addItem("All Species")
            self.cboSpecies.insertSeparator(1)
            self.cboSpecies.addItems(filtered_species)

            self.fillingLocationComboBoxesFlag = False


    def ComboLocationsChanged(self):
        
        if self.fillingLocationComboBoxesFlag is False:

            self.fillingLocationComboBoxesFlag = True

            thisLocation = self.cboLocations.currentText()

            if thisLocation == "All Locations":
                self.unhighlightFilterElement(self.cboLocations)
            else:
                self.highlightFilterElement(self.cboLocations)

            self._refillTaxonomyCombosForFilter(self.GetFilter())

            self.fillingLocationComboBoxesFlag = False

            self.cboStartSeasonalRangeMonth.adjustSize()


    def ComboOrdersChanged(self):

        if self.fillingLocationComboBoxesFlag is False:

            self.fillingLocationComboBoxesFlag = True
            thisOrder = self.cboOrders.currentText()

            if thisOrder == "All Orders":
                self.cboOrders.setStyleSheet("")
            else:
                self.highlightFilterElement(self.cboOrders)

            # Repopulate Family and Species from location+date+order filtered sightings
            f = self.GetFilter()
            f.setFamily("")
            f.setSpeciesName("")
            f.setSpeciesList([])
            sightings = MainWindow.db.GetSightings(f)
            seen_species = set()
            seen_families = set()
            for s in sightings:
                seen_species.add(s["commonName"])
                if s["family"]: seen_families.add(s["family"])

            filtered_families = [fam for fam in MainWindow.db.familyList if fam in seen_families]
            filtered_species  = sorted(sp for sp in MainWindow.db.speciesDict.keys() if sp in seen_species)

            self.unhighlightFilterElement(self.cboFamilies)
            self.cboFamilies.clearFocus()
            self.unhighlightFilterElement(self.cboSpecies)
            self.cboSpecies.clearFocus()
            self.cboFamilies.clear()
            self.cboSpecies.clear()
            self.cboFamilies.addItem("All Families")
            self.cboFamilies.insertSeparator(1)
            self.cboFamilies.addItems(filtered_families)
            self.cboSpecies.addItem("All Species")
            self.cboSpecies.insertSeparator(1)
            self.cboSpecies.addItems(filtered_species)

            self.fillingLocationComboBoxesFlag = False


    def textCommonNameSearchChanged(self):
        
        if self.txtCommonNameSearch.text().strip() != "":
            self.txtCommonNameSearch.setStyleSheet(f"QLineEdit {{ color: {code_Stylesheet.CHART_PRIMARY}; }}")
        else:
            self.txtCommonNameSearch.setStyleSheet("")
            
        
    def ComboSeasonalRangeOptionsChanged(self):
        if self.fillingLocationComboBoxesFlag is False:

            thisOption = self.cboSeasonalRangeOptions.currentText()

            if thisOption == "No Seasonal Range":
                self.unhighlightFilterElement(self.cboSeasonalRangeOptions)
                self.unhighlightFilterElement(self.cboStartSeasonalRangeMonth)
                self.unhighlightFilterElement(self.cboStartSeasonalRangeDate)
                self.unhighlightFilterElement(self.cboEndSeasonalRangeMonth)
                self.unhighlightFilterElement(self.cboEndSeasonalRangeDate)

            elif thisOption == "Use Range Below":
                self.highlightFilterElement(self.cboSeasonalRangeOptions)
                self.highlightFilterElement(self.cboStartSeasonalRangeMonth)
                self.highlightFilterElement(self.cboStartSeasonalRangeDate)
                self.highlightFilterElement(self.cboEndSeasonalRangeMonth)
                self.highlightFilterElement(self.cboEndSeasonalRangeDate)

            else:
                # Presets (Spring, Summer, This Month, a specific month, etc.)
                # populate the Start/End combos with the active range, so they
                # hold non-default values — highlight them blue to match.
                self.highlightFilterElement(self.cboSeasonalRangeOptions)
                self.highlightFilterElement(self.cboStartSeasonalRangeMonth)
                self.highlightFilterElement(self.cboStartSeasonalRangeDate)
                self.highlightFilterElement(self.cboEndSeasonalRangeMonth)
                self.highlightFilterElement(self.cboEndSeasonalRangeDate)

                # Compute start/end month index (0=Jan) and day index (0=1st)
                # for the preset so the dropdowns reflect the active range.
                start_m = start_d = end_m = end_d = None

                if thisOption == "Spring":
                    start_m, start_d, end_m, end_d = 2, 19, 5, 18   # Mar 20 – Jun 19
                elif thisOption == "Summer":
                    start_m, start_d, end_m, end_d = 5, 19, 8, 18   # Jun 20 – Sep 19
                elif thisOption == "Fall":
                    start_m, start_d, end_m, end_d = 8, 19, 11, 18  # Sep 20 – Dec 19
                elif thisOption == "Winter":
                    start_m, start_d, end_m, end_d = 11, 19, 2, 18  # Dec 20 – Mar 19
                elif thisOption == "This Month":
                    now = datetime.datetime.now()
                    m = now.month - 1
                    last = int(MainWindow.db.GetLastDayOfMonth(str(now.month).zfill(2)))
                    start_m, start_d, end_m, end_d = m, 0, m, last - 1
                elif thisOption == "Year to Date":
                    now = datetime.datetime.now()
                    start_m, start_d = 0, 0
                    end_m, end_d = now.month - 1, now.day - 1
                elif thisOption == "Remainder of Year":
                    now = datetime.datetime.now()
                    start_m, start_d = now.month - 1, now.day - 1
                    end_m, end_d = 11, 30  # Dec 31
                else:
                    monthList = ["January", "February", "March", "April", "May", "June",
                                 "July", "August", "September", "October", "November", "December"]
                    if thisOption in monthList:
                        m = monthList.index(thisOption)
                        last = int(MainWindow.db.GetLastDayOfMonth(str(m + 1).zfill(2)))
                        start_m, start_d, end_m, end_d = m, 0, m, last - 1

                if start_m is not None:
                    for combo, idx in (
                        (self.cboStartSeasonalRangeMonth, start_m),
                        (self.cboStartSeasonalRangeDate,  start_d),
                        (self.cboEndSeasonalRangeMonth,   end_m),
                        (self.cboEndSeasonalRangeDate,    end_d),
                    ):
                        combo.blockSignals(True)
                        combo.setCurrentIndex(idx)
                        combo.blockSignals(False)


    def ComboSpeciesChanged(self):
        if self.fillingLocationComboBoxesFlag is False:
            
            thisSpecies = self.cboSpecies.currentText()
            
            if thisSpecies == "All Species":
                self.unhighlightFilterElement(self.cboSpecies)                
            else:
                self.highlightFilterElement(self.cboSpecies)

                     
    def ComboStatesChanged(self):
        if self.fillingLocationComboBoxesFlag is False:        
            self.fillingLocationComboBoxesFlag = True
            
            # clear any color coding for selected filter components
            self.unhighlightFilterElement(self.cboCounties)
            self.cboCounties.clearFocus()
            self.unhighlightFilterElement(self.cboLocations)
            self.cboLocations.clearFocus()

            thisState = MainWindow.db.GetStateCode(self.cboStates.currentText())
            self.cboCounties.clear()
            self.cboLocations.clear()
            if thisState == "All States":
                self.unhighlightFilterElement(self.cboStates)
                self.cboCounties.addItem("All Counties")
                self.cboCounties.insertSeparator(1)
                self.cboLocations.addItem("All Locations")
                self.cboLocations.insertSeparator(1)
                self.cboCounties.addItems(MainWindow.db.countyList)
                self.cboLocations.addItems(MainWindow.db.locationList)
            else:
                self.highlightFilterElement(self.cboStates)
                thisStateCounties = set()
                thisStateLocations = set()
                for l in MainWindow.db.masterLocationList:
                    if l["stateCode"] == thisState:
                        if l["county"] != "": thisStateCounties.add(l["county"])
                        if l["location"] != "": thisStateLocations.add(l["location"])

                thisStateCounties = sorted(thisStateCounties)
                thisStateLocations = sorted(thisStateLocations)

                self.cboCounties.addItem("All Counties")
                self.cboCounties.insertSeparator(1)
                self.cboCounties.addItems(thisStateCounties)
                self.cboLocations.addItem("All Locations")
                self.cboLocations.insertSeparator(1)
                self.cboLocations.addItems(thisStateLocations)

            self._refillTaxonomyCombosForFilter(self.GetFilter())
            self.fillingLocationComboBoxesFlag = False


    def ComboCountiesChanged(self):
        if self.fillingLocationComboBoxesFlag is False:
            self.fillingLocationComboBoxesFlag = True
            thisCounty = self.cboCounties.currentText()
            
            # clear any color coding for selected filter components
            self.cboLocations.setStyleSheet("")
            self.cboLocations.clearFocus()

            self.cboLocations.clear()
            if thisCounty == "All Counties":
                self.unhighlightFilterElement(self.cboCounties)
                self.cboLocations.addItem("All Locations")
                self.cboLocations.insertSeparator(1)
                self.cboLocations.addItems(MainWindow.db.locationList)
            else:
                self.highlightFilterElement(self.cboCounties)
                thisCountyLocations = set()
                for l in MainWindow.db.masterLocationList:
                    if l["county"] == thisCounty:
                        if l["location"] != "": thisCountyLocations.add(l["location"])
                thisCountyLocations = sorted(thisCountyLocations)
                self.cboLocations.addItem("All Locations")
                self.cboLocations.insertSeparator(1)
                self.cboLocations.addItems(thisCountyLocations)

            self._refillTaxonomyCombosForFilter(self.GetFilter())
            self.fillingLocationComboBoxesFlag = False


    def ComboStartRatingRangeChanged(self):
            
            thisSighting = self.cboStartRatingRange.currentText()
            
            startRating = self.cboStartRatingRange.currentIndex()
            endRating = self.cboEndRatingRange.currentIndex()
            
            if startRating > endRating:
                if endRating == 0:
                    self.cboEndRatingRange.setCurrentIndex(7)
                else:
                    self.cboEndRatingRange.setCurrentIndex(startRating)
            
            if thisSighting == "All":
                self.unhighlightFilterElement(self.cboStartRatingRange)
            else:
                self.highlightMediaFilterElement(self.cboStartRatingRange)


    def ComboEndRatingRangeChanged(self):
            
            thisSighting = self.cboEndRatingRange.currentText()
            
            startRating = self.cboStartRatingRange.currentIndex()
            endRating = self.cboEndRatingRange.currentIndex()
            
            if endRating != 0 and startRating == 0:
                # Upper limit set with no lower limit: default the lower limit to "0"
                self.cboStartRatingRange.setCurrentIndex(2)
            elif startRating > endRating:
                self.cboStartRatingRange.setCurrentIndex(endRating)

            if thisSighting == "All":
                self.unhighlightFilterElement(self.cboEndRatingRange)
            else:
                self.highlightMediaFilterElement(self.cboEndRatingRange)


    def ComboSpeciesHasPhotosChanged(self):
            
            thisSpecies = self.cboSpeciesHasPhoto.currentText()
            
            if thisSpecies == "All":
                self.unhighlightFilterElement(self.cboSpeciesHasPhoto)
            else:
                self.highlightMediaFilterElement(self.cboSpeciesHasPhoto)
                

    def ComboCameraChanged(self):
            
            thisCamera = self.cboCamera.currentText()
            
            if thisCamera == "All Cameras":
                self.unhighlightFilterElement(self.cboCamera)
            else:
                self.highlightMediaFilterElement(self.cboCamera)


    def ComboLensChanged(self):
            
            thisLens = self.cboLens.currentText()
            
            if thisLens== "All Lenses":
                self.unhighlightFilterElement(self.cboLens)
            else:
                self.highlightMediaFilterElement(self.cboLens)


    def ComboStartShutterSpeedChanged(self):
            
            thisShutterSpeed = self.cboStartShutterSpeedRange.currentText()
            
            if thisShutterSpeed == "All":
                self.unhighlightFilterElement(self.cboStartShutterSpeedRange)
            else:
                self.highlightMediaFilterElement(self.cboStartShutterSpeedRange)
                

    def ComboEndShutterSpeedChanged(self):
            
            thisShutterSpeed = self.cboEndShutterSpeedRange.currentText()
            
            if thisShutterSpeed == "All":
                self.unhighlightFilterElement(self.cboEndShutterSpeedRange)
            else:
                self.highlightMediaFilterElement(self.cboEndShutterSpeedRange)


    def ComboStartApertureChanged(self):
            
            thisAperture = self.cboStartApertureRange.currentText()
            
            if thisAperture == "All":
                self.unhighlightFilterElement(self.cboStartApertureRange)
            else:
                self.highlightMediaFilterElement(self.cboStartApertureRange)
                

    def ComboEndApertureChanged(self):
            
            thisAperture = self.cboEndApertureRange.currentText()
            
            if thisAperture == "All":
                self.unhighlightFilterElement(self.cboEndApertureRange)
            else:
                self.highlightMediaFilterElement(self.cboEndApertureRange)
                

    def ComboStartFocalLengthChanged(self):
            
            thisFocalLength = self.cboStartFocalLengthRange.currentText()
            
            if thisFocalLength == "All":
                self.unhighlightFilterElement(self.cboStartFocalLengthRange)
            else:
                self.highlightMediaFilterElement(self.cboStartFocalLengthRange)
                

    def ComboEndFocalLengthChanged(self):
            
            thisFocalLength = self.cboEndFocalLengthRange.currentText()
            
            if thisFocalLength == "All":
                self.unhighlightFilterElement(self.cboEndFocalLengthRange)
            else:
                self.highlightMediaFilterElement(self.cboEndFocalLengthRange)


    def ComboStartIsoChanged(self):
            
            thisIso = self.cboStartIsoRange.currentText()
            
            if thisIso == "All":
                self.unhighlightFilterElement(self.cboStartIsoRange)
            else:
                self.highlightMediaFilterElement(self.cboStartIsoRange)
                

    def ComboEndIsoChanged(self):

            thisIso = self.cboEndIsoRange.currentText()

            if thisIso == "All":
                self.unhighlightFilterElement(self.cboEndIsoRange)
            else:
                self.highlightMediaFilterElement(self.cboEndIsoRange)


    def ComboStartRecordingsRatingRangeChanged(self):
        startRating = self.cboStartRecordingsRatingRange.currentIndex()
        endRating   = self.cboEndRecordingsRatingRange.currentIndex()
        if startRating > endRating:
            if endRating == 0:
                self.cboEndRecordingsRatingRange.setCurrentIndex(7)
            else:
                self.cboEndRecordingsRatingRange.setCurrentIndex(startRating)
        if self.cboStartRecordingsRatingRange.currentText() == "All":
            self.unhighlightFilterElement(self.cboStartRecordingsRatingRange)
        else:
            self.highlightRecordingFilterElement(self.cboStartRecordingsRatingRange)

    def ComboEndRecordingsRatingRangeChanged(self):
        startRating = self.cboStartRecordingsRatingRange.currentIndex()
        endRating   = self.cboEndRecordingsRatingRange.currentIndex()
        if endRating != 0 and startRating == 0:
            # Upper limit set with no lower limit: default the lower limit to "0"
            self.cboStartRecordingsRatingRange.setCurrentIndex(2)
        elif startRating > endRating:
            self.cboStartRecordingsRatingRange.setCurrentIndex(endRating)
        if self.cboEndRecordingsRatingRange.currentText() == "All":
            self.unhighlightFilterElement(self.cboEndRecordingsRatingRange)
        else:
            self.highlightRecordingFilterElement(self.cboEndRecordingsRatingRange)

    def ComboSpeciesHasRecordingChanged(self):
        if self.cboSpeciesHasRecording.currentText() == "All":
            self.unhighlightFilterElement(self.cboSpeciesHasRecording)
        else:
            self.highlightRecordingFilterElement(self.cboSpeciesHasRecording)

    def ComboChannelsChanged(self):
        if self.cboChannels.currentText() == "All":
            self.unhighlightFilterElement(self.cboChannels)
        else:
            self.highlightRecordingFilterElement(self.cboChannels)

    def ComboStartRecordingsDurationChanged(self):
        startIdx = self.cboStartRecordingsDurationRange.currentIndex()
        endIdx   = self.cboEndRecordingsDurationRange.currentIndex()
        if startIdx > endIdx:
            if endIdx == 0:
                self.cboEndRecordingsDurationRange.setCurrentIndex(
                    self.cboEndRecordingsDurationRange.count() - 1)
            else:
                self.cboEndRecordingsDurationRange.setCurrentIndex(startIdx)
        if self.cboStartRecordingsDurationRange.currentText() == "All":
            self.unhighlightFilterElement(self.cboStartRecordingsDurationRange)
        else:
            self.highlightRecordingFilterElement(self.cboStartRecordingsDurationRange)

    def ComboEndRecordingsDurationChanged(self):
        startIdx = self.cboStartRecordingsDurationRange.currentIndex()
        endIdx   = self.cboEndRecordingsDurationRange.currentIndex()
        if startIdx > endIdx:
            self.cboStartRecordingsDurationRange.setCurrentIndex(endIdx)
        if self.cboEndRecordingsDurationRange.currentText() == "All":
            self.unhighlightFilterElement(self.cboEndRecordingsDurationRange)
        else:
            self.highlightRecordingFilterElement(self.cboEndRecordingsDurationRange)

    def ComboStartRecordingsSampleRateChanged(self):
        startIdx = self.cboStartRecordingsSampleRateRange.currentIndex()
        endIdx   = self.cboEndRecordingsSampleRateRange.currentIndex()
        if startIdx > endIdx:
            if endIdx == 0:
                self.cboEndRecordingsSampleRateRange.setCurrentIndex(
                    self.cboEndRecordingsSampleRateRange.count() - 1)
            else:
                self.cboEndRecordingsSampleRateRange.setCurrentIndex(startIdx)
        if self.cboStartRecordingsSampleRateRange.currentText() == "All":
            self.unhighlightFilterElement(self.cboStartRecordingsSampleRateRange)
        else:
            self.highlightRecordingFilterElement(self.cboStartRecordingsSampleRateRange)

    def ComboEndRecordingsSampleRateChanged(self):
        startIdx = self.cboStartRecordingsSampleRateRange.currentIndex()
        endIdx   = self.cboEndRecordingsSampleRateRange.currentIndex()
        if startIdx > endIdx:
            self.cboStartRecordingsSampleRateRange.setCurrentIndex(endIdx)
        if self.cboEndRecordingsSampleRateRange.currentText() == "All":
            self.unhighlightFilterElement(self.cboEndRecordingsSampleRateRange)
        else:
            self.highlightRecordingFilterElement(self.cboEndRecordingsSampleRateRange)

    def _onBitDepthToggled(self):
        color = code_Stylesheet.RECORDINGS_PRIMARY
        for chk in self._bitDepthChecks:
            chk.setStyleSheet(f"color: {color};" if chk.isChecked() else "")

    def ComboRecordingsDeviceChanged(self):
        if self.cboRecordingsDevice.currentText() == "All":
            self.unhighlightFilterElement(self.cboRecordingsDevice)
        else:
            self.highlightRecordingFilterElement(self.cboRecordingsDevice)


    def createChoroplethUSStates(self):
        
        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        # create new Location Totals child window
        sub = code_Web.Web()

        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self

        # call the child's routine to fill it with data
        if sub.loadChoroplethUSStates(filter) is True:
            
            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()

        else:
            # abort if filter found no sightings for map
            self.CreateMessageNoResults()
            sub.close()
            
        

    def createChoroplethGBCounties(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return


        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self

        if sub.loadChoroplethGBCounties(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()



    def createChoroplethIndiaStates(self):

        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return


        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self

        if sub.loadChoroplethIndiaStates(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()



    def createChoroplethCanadaProvinces(self):

        # if no data file is currently open, abort
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return


        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self

        if sub.loadChoroplethCanadaProvinces(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()



    def createChoroplethUSCounties(self):
                
        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        # create new Location Totals child window
        sub = code_Web.Web()

        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self

        # call the child's routine to fill it with data
        if sub.loadChoroplethUSCounties(filter) is True:
            
            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()

        else:
            # abort if filter found no sightings for map
            self.CreateMessageNoResults()
            sub.close()
            
        
    
    def createChoroplethWorldCountries(self):

        # if no data file is currently open, abort        
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()   
            return
        
        
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        # create new Location Totals child window
        sub = code_Web.Web()

        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self

        # call the child's routine to fill it with data
        if sub.loadChoroplethWorldCountries(filter) is True:

            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()

        else:
            # abort if filter found no sightings for map
            self.CreateMessageNoResults()
            sub.close()



    def createChoroplethUSStatesChecklists(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadChoroplethUSStates(filter, mode='checklists') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()


    def createChoroplethUSCountiesChecklists(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadChoroplethUSCounties(filter, mode='checklists') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()


    def createChoroplethCanadaProvincesChecklists(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadChoroplethCanadaProvinces(filter, mode='checklists') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()


    def createChoroplethIndiaStatesChecklists(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadChoroplethIndiaStates(filter, mode='checklists') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()


    def createChoroplethGBCountiesChecklists(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadChoroplethGBCounties(filter, mode='checklists') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()


    def createChoroplethWorldCountriesChecklists(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadChoroplethWorldCountries(filter, mode='checklists') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()


    def createGeolocatedPhotosMap(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetPhotoFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadGeolocatedPhotosMap(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()


    def createAnimatedPhotoSequenceMap(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetPhotoFilter()
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadAnimatedPhotoSequenceMap(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()


    def createSlideshow(self):
        import code_Slideshow
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetPhotoFilter()
        dlg = code_Slideshow.SlideshowDialog(self)
        if dlg.exec() != code_Slideshow.QDialog.DialogCode.Accepted:
            return
        photoList = code_Slideshow.buildPhotoList(
            MainWindow.db, filter, dlg.sortOrder()
        )
        if not photoList:
            self.CreateMessageNoResults()
            return
        self._slideshow = code_Slideshow.SlideshowWindow(
            photoList, dlg.secondsPerPhoto(), dlg.showTitleBar()
        )
        self._slideshow.show()


    def createLifeListMap(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadLifeListMap(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()


    def createFirstSightingsMap(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadFirstSightingsMap(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()


    def createEffortMap(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadEffortMap(filter, mode='time') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()

    def createEffortMapByChecklists(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadEffortMap(filter, mode='checklists') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()


    def createSpeciesTotalMap(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadBubbleMap(filter, mode='species') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()

    def createIndividualsTotalMap(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadBubbleMap(filter, mode='individuals') is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            self.CreateMessageNoResults()
            sub.close()

    def createNotableMap(self):
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        if not MainWindow.db.ebirdApiKey.strip():
            QMessageBox.warning(
                self,
                "eBird API Key Required",
                "No eBird API key is configured.\n\nPlease add your key under Preferences.",
                QMessageBox.StandardButton.Ok,
            )
            return
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        sub = code_Web.Web()
        sub.mdiParent = self
        if sub.loadNotableMap(filter) is True:
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub, self)
            sub.show()
        else:
            sub.close()

    def createChoroplethWorldSubregion1(self):

        # if no data file is currently open, abort
        if MainWindow.db.eBirdFileOpenFlag is not True:
            self.CreateMessageNoFile()
            return
        
        
        filter = self.GetGeneralFilter()
        if filter is None:
            return
        # create new Location Totals child window
        sub = code_Web.Web()

        # save the MDI window as the parent for future use in the child
        sub.mdiParent = self

        # call the child's routine to fill it with data
        if sub.loadChoroplethWorldSubregion1(filter) is True:
            
            # add and position the child to our MDI area
            self.mdiArea.addSubWindow(sub)
            self.PositionChildWindow(sub,  self)
            sub.show()

        else:
            # abort if filter found no sightings for map
            self.CreateMessageNoResults()
            sub.close()
            



    def highlightFilterElement(self, widget, color=None):
        if color is None:
            color = code_Stylesheet.CHART_PRIMARY

        if widget.objectName()[0:3] == "cbo":
            widget.setStyleSheet(f"QComboBox {{ color: {color}; }}")

        if widget.objectName()[0:3] == "cal":
            red = str(code_Stylesheet.mdiAreaColor.red())
            green = str(code_Stylesheet.mdiAreaColor.green())
            blue = str(code_Stylesheet.mdiAreaColor.blue())
            bg = "rgb(" + red + "," + green + "," + blue + ")"
            # The displayed date text lives in QDateTimeEdit's internal QLineEdit
            # (objectName "qt_spinbox_lineedit").  The global "QWidget { color }"
            # rule matches that line edit directly and out-specifies an inherited
            # "QDateTimeEdit { color }", so we must colour the line edit itself.
            widget.setStyleSheet(
                "QDateTimeEdit { background-color: " + bg + "; color: " + color + "; }"
                "QDateTimeEdit QLineEdit { color: " + color + "; background: transparent; }"
            )

    def highlightMediaFilterElement(self, widget):
        self.highlightFilterElement(widget, color=code_Stylesheet.PHOTO_PRIMARY)

    def highlightRecordingFilterElement(self, widget):
        self.highlightFilterElement(widget, color=code_Stylesheet.RECORDINGS_PRIMARY)

    def unhighlightFilterElement(self, widget):
        
        widget.setStyleSheet("")

 
                
    def ExitApp(self):

        self.checkIfPhotoDataNeedSaving()
        self.toolBar.setStyle(None)
        sys.exit()
        
