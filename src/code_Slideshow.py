import os

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QRadioButton, QLabel, QSpinBox, QDialogButtonBox, QCheckBox,
    QApplication,
)
from PySide6.QtCore import Qt, QTimer, QPoint, QRect
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QCursor


BAR_H            = 72     # title bar height in pixels
BAR_COLOR        = QColor("#2b2d38")
BLEND_DURATION   = 500    # crossfade length in ms
BLEND_INTERVAL   = 16     # timer tick in ms (~60 fps)


class SlideshowDialog(QDialog):
    """Pre-slideshow options dialog: sort order, speed, title-bar toggle."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Slideshow Options")
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # ── Sort order ────────────────────────────────────────────────────────
        sortGroup = QGroupBox("Sort Order")
        sortLayout = QVBoxLayout(sortGroup)
        sortLayout.setContentsMargins(16, 12, 16, 12)
        sortLayout.setSpacing(8)

        self.radioRandom      = QRadioButton("Random")
        self.radioTaxonomic   = QRadioButton("Taxonomic")
        self.radioAlphabetic  = QRadioButton("Alphabetic")
        self.radioRating      = QRadioButton("By rating (highest first)")
        self.radioChronologic = QRadioButton("Chronological")
        self.radioLocation    = QRadioButton("By location")
        self.radioSeasonal    = QRadioButton("By seasonal date (month / day)")

        self.radioRandom.setChecked(True)

        for rb in (self.radioRandom, self.radioTaxonomic, self.radioAlphabetic,
                   self.radioRating, self.radioChronologic, self.radioLocation,
                   self.radioSeasonal):
            sortLayout.addWidget(rb)

        layout.addWidget(sortGroup)

        # ── Speed ─────────────────────────────────────────────────────────────
        speedRow = QHBoxLayout()
        speedRow.setSpacing(10)
        speedLabel = QLabel("Seconds per photo:")
        speedLabel.setStyleSheet("font-size: 14pt;")
        speedRow.addWidget(speedLabel)
        self.spinSpeed = QSpinBox()
        self.spinSpeed.setRange(1, 60)
        self.spinSpeed.setValue(5)
        self.spinSpeed.setStyleSheet("font-size: 14pt;")
        speedRow.addWidget(self.spinSpeed)
        speedRow.addStretch()
        layout.addLayout(speedRow)

        # ── Title bar toggle ──────────────────────────────────────────────────
        self.chkTitleBar = QCheckBox("Show title bar (species, date, location)")
        self.chkTitleBar.setChecked(True)
        layout.addWidget(self.chkTitleBar)

        layout.addSpacing(4)

        # ── Buttons ───────────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def sortOrder(self):
        if self.radioAlphabetic.isChecked():  return "alphabetic"
        if self.radioRating.isChecked():      return "rating"
        if self.radioChronologic.isChecked(): return "chronological"
        if self.radioLocation.isChecked():    return "location"
        if self.radioSeasonal.isChecked():    return "seasonal"
        if self.radioRandom.isChecked():      return "random"
        return "taxonomic"

    def secondsPerPhoto(self):
        return self.spinSpeed.value()

    def showTitleBar(self):
        return self.chkTitleBar.isChecked()


class SlideshowWindow(QWidget):
    """Full-screen photo slideshow with crossfade transitions.

    The screen is divided into a photo area (top) and an optional solid title
    bar (bottom).  Photos are scaled to fit the photo area with aspect ratio
    preserved and centred on the dark-gray background.

    Exits immediately on any key press or deliberate mouse movement.
    The cursor is hidden for the duration of the slideshow.
    """

    def __init__(self, photoList, secondsPerPhoto=5, showTitleBar=True):
        super().__init__()
        self.photoList      = photoList
        self.currentIndex   = 0
        self._showTitleBar  = showTitleBar
        self._pixmap        = QPixmap()   # current (incoming) photo
        self._prevPixmap    = QPixmap()   # outgoing photo during blend
        self._blendAlpha    = 0.0         # start at 0 so first photo fades in
        self._firstPhoto    = True        # use 2× duration for the opening fade
        self._trackMouse    = False
        self._lastMousePos  = QPoint()

        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setMouseTracking(True)

        # Hide the cursor for the duration of the slideshow
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.BlankCursor))

        self._loadCurrentPhoto()
        self.showFullScreen()

        # Slide-advance timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(secondsPerPhoto * 1000)

        # Crossfade timer — runs during transitions and the initial fade-in
        self._blendTimer = QTimer(self)
        self._blendTimer.timeout.connect(self._blendStep)
        self._blendTimer.start(BLEND_INTERVAL)   # fade first photo in from black

        # Arm mouse-move exit only after the window has fully settled
        QTimer.singleShot(800, self._enableMouseTracking)

    # ── private ───────────────────────────────────────────────────────────────

    def _enableMouseTracking(self):
        self._trackMouse   = True
        self._lastMousePos = self.mapFromGlobal(self.cursor().pos())

    def _loadCurrentPhoto(self):
        if not self.photoList:
            return
        fileName = self.photoList[self.currentIndex][0].get("fileName", "")
        self._pixmap = QPixmap(fileName) if (fileName and os.path.isfile(fileName)) else QPixmap()
        self.update()

    def _advance(self):
        if not self.photoList:
            return
        # Capture outgoing frame before loading the new one
        self._prevPixmap = QPixmap(self._pixmap)
        self._blendAlpha = 0.0
        self.currentIndex = (self.currentIndex + 1) % len(self.photoList)
        self._loadCurrentPhoto()
        self._blendTimer.start(BLEND_INTERVAL)

    def _blendStep(self):
        duration = BLEND_DURATION * 4 if self._firstPhoto else BLEND_DURATION
        self._blendAlpha += BLEND_INTERVAL / duration
        if self._blendAlpha >= 1.0:
            self._blendAlpha = 1.0
            self._firstPhoto = False
            self._blendTimer.stop()
            self._prevPixmap = QPixmap()   # release memory
        self.update()

    def _exit(self):
        self._timer.stop()
        self._blendTimer.stop()
        QApplication.restoreOverrideCursor()
        self.close()

    # ── Qt event overrides ────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        self._exit()

    def mouseMoveEvent(self, event):
        if self._trackMouse and event.pos() != self._lastMousePos:
            self._exit()
            return
        self._lastMousePos = event.pos()

    def closeEvent(self, event):
        # Guarantee cursor is restored even if the window is closed externally
        self._timer.stop()
        self._blendTimer.stop()
        QApplication.restoreOverrideCursor()
        super().closeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()

        # ── Title bar ─────────────────────────────────────────────────────────
        if self._showTitleBar and self.photoList:
            photo_area_h = h - BAR_H
            painter.fillRect(0, photo_area_h, w, BAR_H, BAR_COLOR)

            sight    = self.photoList[self.currentIndex][1]
            species  = sight.get("commonName", "")
            date     = sight.get("date", "")
            location = sight.get("location", "")
            counter  = f"{self.currentIndex + 1} / {len(self.photoList)}"

            half = BAR_H // 2

            f1 = QFont("Helvetica", 20, QFont.Weight.Bold)
            painter.setFont(f1)
            painter.setPen(QColor("white"))
            painter.drawText(QRect(0, photo_area_h, w, half),
                             Qt.AlignmentFlag.AlignCenter, species)

            f2 = QFont("Helvetica", 13)
            painter.setFont(f2)
            painter.setPen(QColor(190, 190, 190))
            parts  = [p for p in (date, location, counter) if p]
            detail = "  ·  ".join(parts)
            painter.drawText(QRect(0, photo_area_h + half, w, half),
                             Qt.AlignmentFlag.AlignCenter, detail)
        else:
            photo_area_h = h

        # ── Photo area background ─────────────────────────────────────────────
        painter.setOpacity(1.0)
        painter.fillRect(0, 0, w, photo_area_h, BAR_COLOR)

        # ── Helper: draw a pixmap letterboxed into the photo area ─────────────
        def draw_photo(px, opacity):
            if px.isNull():
                return
            scaled = px.scaled(w, photo_area_h,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            x = (w - scaled.width())  // 2
            y = (photo_area_h - scaled.height()) // 2
            painter.setOpacity(opacity)
            painter.drawPixmap(x, y, scaled)

        # ── Crossfade or plain draw ───────────────────────────────────────────
        if self._blendAlpha < 1.0:
            if not self._prevPixmap.isNull():          # normal crossfade
                draw_photo(self._prevPixmap, 1.0 - self._blendAlpha)
            draw_photo(self._pixmap, self._blendAlpha) # fade-in (from black if no prev)
        else:
            draw_photo(self._pixmap, 1.0)

        painter.setOpacity(1.0)
        painter.end()


# ── Sort helper ───────────────────────────────────────────────────────────────

def buildPhotoList(db, filter, sortOrder):
    """Return a sorted list of [photo_dict, sighting_dict] pairs."""

    sightings = db.GetSightingsWithPhotos(filter)

    pairs = []
    for s in sightings:
        for p in s.get("photos", []):
            if db.TestIndividualPhoto(p, filter):
                if p.get("fileName", ""):
                    pairs.append([p, s])

    if sortOrder == "alphabetic":
        pairs.sort(key=lambda x: (x[1].get("commonName", "").lower(),
                                  x[1].get("date", "")))

    elif sortOrder == "rating":
        def _rating(pair):
            try:
                return -int(pair[0].get("rating", "0") or "0")
            except ValueError:
                return 0
        pairs.sort(key=lambda x: (_rating(x),
                                  float(x[1].get("taxonomicOrder", 0))))

    elif sortOrder == "chronological":
        pairs.sort(key=lambda x: (x[1].get("date", ""), x[1].get("time", "")))

    elif sortOrder == "location":
        pairs.sort(key=lambda x: (x[1].get("location", "").lower(),
                                  x[1].get("date", "")))

    elif sortOrder == "random":
        import random
        random.shuffle(pairs)

    elif sortOrder == "seasonal":
        def _mmdd(pair):
            d = pair[1].get("date", "")
            return d[5:] if len(d) >= 7 else ""
        pairs.sort(key=lambda x: (_mmdd(x), x[1].get("date", "")))

    else:  # taxonomic (default)
        pairs.sort(key=lambda x: (
            float(x[1].get("taxonomicOrder", 0)),
            x[1].get("date", ""),
            x[1].get("time", ""),
        ))

    return pairs
