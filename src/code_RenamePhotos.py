# import project files
import form_RenamePhotos
import code_Filter
import code_Stylesheet

import errno as _errno_mod
import os
import re
import unicodedata
import uuid
import piexif

from collections import Counter

from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QPen,
    QPixmap,
)

import base64

from PySide6.QtCore import (
    Signal,
    Qt,
    QEvent,
    QPoint,
)

from PySide6.QtWidgets import (
    QMdiSubWindow,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidgetItem,
    QCheckBox,
    QWidget,
    QHBoxLayout,
    QMessageBox,
    QToolTip,
)


# ── Slot option labels ─────────────────────────────────────────────────────────
_SLOT_OPTIONS  = ["(omit)", "Species Name", "Location", "Date", "Time"]
_DATE_FORMATS  = ["YYYY-MM-DD", "YYYYMMDD", "(omit)"]
_TIME_FORMATS  = ["HH-MM-SS", "HHMMSS", "HH-MM-SSt", "HHMMSSt", "(omit)"]
_NAME_FORMATS  = ["Common Name", "Scientific Name", "eBird Species Code"]

# ── Column indices ─────────────────────────────────────────────────────────────
_COL_CHECK    = 0
_COL_CURRENT  = 1
_COL_PROPOSED = 2
_COL_STATUS   = 3

# Red used for error messages in the Status column.
_ERROR_RED = QColor("#e05c5c")

# Human-readable messages for the most common OS rename failures.
_OSERROR_MESSAGES = {
    _errno_mod.ENOENT: "File not found",
    _errno_mod.EACCES: "Permission denied",
    _errno_mod.EPERM:  "Permission denied",
    _errno_mod.EEXIST: "Name already in use",
    _errno_mod.ENOSPC: "Disk full",
}

# Windows reserved device names — forbidden as a bare basename on any drive.
_WINDOWS_RESERVED = frozenset([
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
])


class _HoverRowDelegate(QStyledItemDelegate):
    """Draws a white border around every cell in the hovered row."""

    def __init__(self, table):
        super().__init__(table)
        self._table = table
        self._hover_row = -1

    def setHoverRow(self, row):
        if row != self._hover_row:
            self._hover_row = row
            self._table.viewport().update()

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.row() == self._hover_row:
            painter.save()
            pen = QPen(QColor("#e2e4ec"), 1)
            painter.setPen(pen)
            painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
            painter.restore()


class RenamePhotos(QMdiSubWindow, form_RenamePhotos.Ui_frmRenamePhotos):

    resized = Signal()

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.mdiParent = ""
        self.resized.connect(self.resizeMe)

        # Each entry: {"sighting": s, "photo": p,
        #              "exifDatetime": str|None, "exifSubsec": str|None}
        self._rows = []

        # Paths that have been through the rename loop (success or failure) and
        # must not have their Status/Proposed columns overwritten by subsequent
        # _updateProposedNames() calls.
        self._frozen_paths = set()

        # Populate slot combos
        for n in range(1, 5):
            cbo = getattr(self, f"cboSlot{n}")
            cbo.addItems(_SLOT_OPTIONS)

        # Defaults: Date | Time | Species Name | Location
        self.cboSlot1.setCurrentIndex(_SLOT_OPTIONS.index("Date"))
        self.cboSlot2.setCurrentIndex(_SLOT_OPTIONS.index("Time"))
        self.cboSlot3.setCurrentIndex(_SLOT_OPTIONS.index("Species Name"))
        self.cboSlot4.setCurrentIndex(_SLOT_OPTIONS.index("Location"))

        self.cboDateFormat.addItems(_DATE_FORMATS)
        self.cboTimeFormat.addItems(_TIME_FORMATS)
        self.cboNameFormat.addItems(_NAME_FORMATS)   # default = "Common Name"

        # Wire signals
        for n in range(1, 5):
            getattr(self, f"cboSlot{n}").currentIndexChanged.connect(
                self._updateProposedNames)
        self.cboDateFormat.currentIndexChanged.connect(self._updateProposedNames)
        self.cboTimeFormat.currentIndexChanged.connect(self._updateProposedNames)
        self.cboNameFormat.currentIndexChanged.connect(self._updateProposedNames)
        self.chkUseChecklistTime.stateChanged.connect(self._updateProposedNames)
        self.chkShortenLocation.stateChanged.connect(self._updateProposedNames)
        self.chkAddTenths.stateChanged.connect(self._updateProposedNames)
        self.chkRemoveSpaces.stateChanged.connect(self._updateProposedNames)
        self.btnSelectAll.clicked.connect(self._selectAll)
        self.btnSelectNone.clicked.connect(self._selectNone)
        self.btnRename.clicked.connect(self._rename)
        self.btnCancel.clicked.connect(self.close)

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_camera_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        self._hoverDelegate = _HoverRowDelegate(self.tblPhotos)
        self.tblPhotos.setItemDelegate(self._hoverDelegate)
        self.tblPhotos.viewport().installEventFilter(self)
        self.tblPhotos.setMouseTracking(True)


    def closeEvent(self, event):
        self.mdiParent.db.compactJsonlFile()
        super(self.__class__, self).closeEvent(event)


    def eventFilter(self, obj, event):
        if obj is self.tblPhotos.viewport():
            if event.type() == QEvent.Type.MouseMove:
                self._hoverDelegate.setHoverRow(
                    self.tblPhotos.rowAt(event.pos().y()))
            elif event.type() == QEvent.Type.Leave:
                self._hoverDelegate.setHoverRow(-1)

        if obj is self.tblPhotos.viewport() and event.type() == QEvent.Type.ToolTip:
            pos = event.pos()
            row = self.tblPhotos.rowAt(pos.y())
            if row >= 0:
                item = self.tblPhotos.item(row, _COL_CURRENT)
                if item:
                    path = item.data(Qt.UserRole)
                    if path and os.path.isfile(path):
                        px = QPixmap(path)
                        if not px.isNull():
                            px = px.scaled(200, 200,
                                           Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
                            buf = px.toImage()
                            from PySide6.QtCore import QBuffer, QByteArray, QIODevice
                            ba = QByteArray()
                            qbuf = QBuffer(ba)
                            qbuf.open(QIODevice.OpenModeFlag.WriteOnly)
                            buf.save(qbuf, "JPEG", 85)
                            qbuf.close()
                            b64 = base64.b64encode(bytes(ba)).decode("ascii")
                            html = f'<img src="data:image/jpeg;base64,{b64}">'
                            QToolTip.showText(event.globalPos(), html, self.tblPhotos.viewport())
                            return True
            QToolTip.hideText()
            return True
        return super().eventFilter(obj, event)


    # ── Public ─────────────────────────────────────────────────────────────────

    def FillRenamePhotos(self, sightings):
        """Populate the table from a list of sightings-with-photos.

        Each sighting may carry multiple photos; each photo becomes one row.
        """
        self._rows = []
        self._frozen_paths = set()
        self.tblPhotos.setRowCount(0)
        self.tblPhotos.setSortingEnabled(False)

        row_index = 0
        for s in sightings:
            for p in s.get("photos", []):
                exif_dt, exif_sub, exif_bad = self._readExifDatetime(p["fileName"])
                self._rows.append({
                    "sighting": s,
                    "photo": p,
                    "exifDatetime": exif_dt,
                    "exifSubsec": exif_sub,
                    "exifDateInvalid": exif_bad,
                })

                self.tblPhotos.insertRow(row_index)

                # Col 0 — centred checkbox widget
                chk_widget = QWidget()
                chk = QCheckBox()
                chk.setChecked(True)
                chk.stateChanged.connect(self._updateCount)
                lay = QHBoxLayout(chk_widget)
                lay.addWidget(chk)
                lay.setAlignment(Qt.AlignCenter)
                lay.setContentsMargins(0, 0, 0, 0)
                self.tblPhotos.setCellWidget(row_index, _COL_CHECK, chk_widget)

                # Col 1 — current filename; UserRole holds full path for lookup,
                # tooltip shows the full basename so truncated names are readable
                basename = os.path.basename(p["fileName"])
                item_cur = QTableWidgetItem(basename)
                item_cur.setData(Qt.UserRole, p["fileName"])
                item_cur.setToolTip(basename)
                self.tblPhotos.setItem(row_index, _COL_CURRENT, item_cur)

                # Col 2 — proposed (computed below)
                self.tblPhotos.setItem(row_index, _COL_PROPOSED, QTableWidgetItem(""))

                # Col 3 — status
                self.tblPhotos.setItem(row_index, _COL_STATUS, QTableWidgetItem(""))

                row_index += 1

        self.tblPhotos.setSortingEnabled(True)
        self._updateProposedNames()
        self._updateCount()
        self._resizeContentColumns()


    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _readExifDatetime(filepath):
        """Return (datetime_str, subsec_str, bad_flag) from EXIF.

        datetime_str is 'YYYY:MM:DD HH:MM:SS' when present and valid.
        subsec_str is the raw SubSecTimeOriginal value (e.g. '7', '123').
        bad_flag is True when EXIF data was found but contained an invalid date.
        Returns (None, None, False) when EXIF is absent or unreadable.
        """
        try:
            exif = piexif.load(filepath)
        except Exception:
            return None, None, False

        dt_raw = exif.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
        if dt_raw is None:
            return None, None, False
        try:
            dt_str = dt_raw.decode("utf-8")
        except Exception:
            return None, None, True

        # Validate: expected format is 'YYYY:MM:DD HH:MM:SS' (19 chars)
        try:
            if len(dt_str) < 19:
                raise ValueError
            year  = int(dt_str[0:4])
            month = int(dt_str[5:7])
            day   = int(dt_str[8:10])
            hour  = int(dt_str[11:13])
            minute = int(dt_str[14:16])
            if not (1 <= month <= 12 and 1 <= day <= 31
                    and 0 <= hour <= 23 and 0 <= minute <= 59
                    and year > 0):
                raise ValueError
        except (ValueError, IndexError):
            return None, None, True

        sub_raw = exif.get("Exif", {}).get(piexif.ExifIFD.SubSecTimeOriginal)
        sub_str = None
        if sub_raw is not None:
            try:
                sub_str = sub_raw.decode("utf-8").strip("\x00").strip()
            except Exception:
                pass

        return dt_str, sub_str, False


    @staticmethod
    def _sanitizeForFilename(text):
        """Sanitize a species or location name for use as a filename component.

        Steps applied in order:
        1. Strip parenthetical suffixes, e.g. "Joe's Harbor (Colorado)" → "Joe's Harbor"
        2. Remove apostrophes (delete, not replace)
        3. Replace remaining filesystem-illegal characters with a dash
        4. Remove all spaces
        5. Strip leading/trailing dashes left over from step 3
        """
        # 1. Remove parenthetical expressions (and any preceding whitespace)
        text = re.sub(r'\s*\(.*?\)', '', text)
        # 2. Remove apostrophes
        text = text.replace("'", "")
        # 3. Strip control characters (forbidden on Windows; unusual in metadata)
        text = re.sub(r'[\x00-\x1f\x7f]', '', text)
        # 4. Replace filesystem-illegal characters with a dash
        for ch in r'\/:*?"<>|':
            text = text.replace(ch, "-")
        # 5. Tidy leading/trailing dashes, dots, and spaces.
        #    Windows rejects filenames ending in '.' or ' '; stripping here keeps
        #    components clean on all platforms.
        #    Space removal is NOT done here — callers apply it based on the checkbox.
        text = text.strip("-. ")
        return text


    @staticmethod
    def _sanitizeSpeciesName(text, scientific=False):
        """Sanitize a species name, promoting any parenthetical to an
        underscore-separated suffix instead of dropping it.

        'Dark-eyed Junco (Slate-colored)' → 'Dark-eyed Junco_Slate-colored'
        'Junco hyemalis (hyemalis)' (scientific) → 'Junco hyemalis_hyemalis'

        Spaces are preserved here; callers apply space/underscore substitution
        based on the "Remove spaces" checkbox.
        """
        # Split out parenthetical content before sanitizing
        match = re.search(r'\(([^)]+)\)', text)
        if match:
            parens_content = match.group(1).strip()
            base = re.sub(r'\s*\([^)]+\)', '', text).strip()
        else:
            parens_content = None
            base = text

        sanitized_base = RenamePhotos._sanitizeForFilename(base)

        if parens_content:
            sanitized_parens = RenamePhotos._sanitizeForFilename(parens_content)
            if sanitized_base and sanitized_parens:
                return f"{sanitized_base}_{sanitized_parens}"
            return sanitized_base or sanitized_parens

        return sanitized_base


    def _buildComponent(self, slot_label, row_data, force_tenths=False):
        """Return the string for one name-format slot.

        Returns '' for '(omit)' or when data is unavailable.
        force_tenths: when True and the Time slot is active with a seconds-only
        format (HH-MM-SS / HHMMSS), append the tenths digit to differentiate
        same-second filenames.
        """
        s        = row_data["sighting"]
        exif_dt  = row_data["exifDatetime"]
        exif_sub = row_data["exifSubsec"]

        if slot_label == "(omit)":
            return ""

        if slot_label == "Species Name":
            name_fmt = self.cboNameFormat.currentText()
            if name_fmt == "eBird Species Code":
                return self._sanitizeForFilename(s.get("quickEntryCode", ""))
            use_scientific = name_fmt == "Scientific Name"
            raw = s.get("scientificName" if use_scientific else "commonName", "")
            result = self._sanitizeSpeciesName(raw, scientific=use_scientific)
            if self.chkRemoveSpaces.isChecked():
                result = result.replace(" ", "_" if use_scientific else "")
            return result

        if slot_label == "Location":
            loc = s.get("location", "")
            if self.chkShortenLocation.isChecked():
                m = re.search(r'[,\-:@(]', loc)
                if m:
                    loc = loc[:m.start()].strip()
            result = self._sanitizeForFilename(loc)
            if self.chkRemoveSpaces.isChecked():
                result = result.replace(" ", "")
            return result

        if slot_label == "Date":
            fmt = self.cboDateFormat.currentText()
            if fmt == "(omit)":
                return ""
            if exif_dt and len(exif_dt) >= 10:
                # EXIF: 'YYYY:MM:DD HH:MM:SS'
                y, m, d = exif_dt[0:4], exif_dt[5:7], exif_dt[8:10]
            else:
                date_str = s.get("date", "")
                if len(date_str) >= 10:
                    y, m, d = date_str[0:4], date_str[5:7], date_str[8:10]
                else:
                    return ""
            if fmt == "YYYY-MM-DD":
                return f"{y}-{m}-{d}"
            if fmt == "YYYYMMDD":
                return f"{y}{m}{d}"
            if fmt == "YYYY":
                return y
            return ""

        if slot_label == "Time":
            fmt = self.cboTimeFormat.currentText()
            if fmt == "(omit)":
                return ""
            use_fallback = self.chkUseChecklistTime.isChecked()
            if exif_dt and len(exif_dt) >= 19:
                # EXIF: 'YYYY:MM:DD HH:MM:SS'
                hh, mm, ss = exif_dt[11:13], exif_dt[14:16], exif_dt[17:19]
                tenth = exif_sub[0] if exif_sub else "0"
                if fmt == "HH-MM-SSt":
                    return f"{hh}-{mm}-{ss}{tenth}"
                if fmt == "HHMMSSt":
                    return f"{hh}{mm}{ss}{tenth}"
                if fmt == "HH-MM-SS":
                    return (f"{hh}-{mm}-{ss}{tenth}"
                            if force_tenths else f"{hh}-{mm}-{ss}")
                if fmt == "HHMMSS":
                    return (f"{hh}{mm}{ss}{tenth}"
                            if force_tenths else f"{hh}{mm}{ss}")
            elif use_fallback:
                # Checklist time is 'HH:MM' — seconds default to 00;
                # no subsecond data is available so force_tenths is a no-op here
                t = s.get("time", "")
                if len(t) >= 5:
                    hh, mm = t[0:2], t[3:5]
                    if fmt in ("HH-MM-SS", "HH-MM-SSt"):
                        return f"{hh}-{mm}-00"
                    if fmt in ("HHMMSS", "HHMMSSt"):
                        return f"{hh}{mm}00"
            return ""

        return ""


    def _buildProposedBasename(self, row_data, force_tenths=False):
        """Return the proposed base name (no extension) for one photo row."""
        parts = []
        for n in range(1, 5):
            label = getattr(self, f"cboSlot{n}").currentText()
            comp = self._buildComponent(label, row_data, force_tenths=force_tenths)
            if comp:
                parts.append(comp)
        base = "_".join(parts) if parts else ""
        # Guard against Windows reserved device names (CON, NUL, COM1, etc.).
        if base.upper() in _WINDOWS_RESERVED:
            base = base + "_photo"
        return base


    def _updateProposedNames(self):
        """Recompute all proposed names and update the Status column."""
        if not self._rows:
            return

        # Disable sorting for the duration of this update.
        # With sorting active, any setText() call on a sorted column triggers an
        # immediate re-sort, scrambling the row↔resolved[] mapping mid-Pass-3.
        self.tblPhotos.setSortingEnabled(False)
        try:
            self._doUpdateProposedNames()
        finally:
            self.tblPhotos.setSortingEnabled(True)


    def _doUpdateProposedNames(self):
        """Inner implementation called by _updateProposedNames."""
        row_count = self.tblPhotos.rowCount()

        # ── Pre-pass: find rows that need tenths added to Time slot ───────────
        # Only runs when chkAddTenths is checked, a Time slot is active, and the
        # current time format does not already include tenths (HH-MM-SS.t).
        # Rows that share the same proposed basename (ignoring tenths) are both
        # promoted to the .t / t variant.  Checklist-fallback rows are skipped
        # because they have no subsecond EXIF data.
        tenths_paths = set()   # set of original_path strings needing force_tenths
        if self.chkAddTenths.isChecked():
            time_slot_active = any(
                getattr(self, f"cboSlot{n}").currentText() == "Time"
                for n in range(1, 5)
            )
            if time_slot_active and self.cboTimeFormat.currentText() not in (
                    "(omit)", "HH-MM-SSt", "HHMMSSt"):
                pre = {}   # original_path -> (base, ext)
                for ri in range(row_count):
                    chk = self._getCheckboxForRow(ri)
                    if chk is None or not chk.isChecked():
                        continue
                    cur_item = self.tblPhotos.item(ri, _COL_CURRENT)
                    if cur_item is None:
                        continue
                    opath = cur_item.data(Qt.UserRole)
                    if not opath:
                        continue
                    rd = self._rowDataForTableRow(ri)
                    if rd is None or rd["exifDatetime"] is None:
                        continue
                    b = self._buildProposedBasename(rd, force_tenths=False)
                    e = os.path.splitext(opath)[1].lower()
                    pre[opath] = (b, e)
                key_counts = Counter(v for v in pre.values() if v[0])
                tenths_paths = {p for p, ke in pre.items()
                                if key_counts[ke] > 1}

        # ── Pass 1: collect one record per checked row ────────────────────────
        # Each record is (base, ext, original_dir, original_path).
        # Keyed on original_path so Pass 2 and Pass 3 can look up by path
        # rather than by row index, making them immune to any row reordering.
        checked_rows = {}   # original_path -> (base, ext, original_dir)
        for row_index in range(row_count):
            chk = self._getCheckboxForRow(row_index)
            if chk is None or not chk.isChecked():
                continue
            cur_item = self.tblPhotos.item(row_index, _COL_CURRENT)
            if cur_item is None:
                continue
            original_path = cur_item.data(Qt.UserRole)
            if not original_path:
                continue
            rd = self._rowDataForTableRow(row_index)
            if rd is None:
                continue
            original_dir = unicodedata.normalize(
                "NFC", os.path.dirname(original_path))
            ext  = os.path.splitext(original_path)[1].lower()
            base = self._buildProposedBasename(
                rd, force_tenths=(original_path in tenths_paths))
            checked_rows[original_path] = (base, ext, original_dir)

        # ── Pass 2: detect duplicates and assign zero-padded suffixes ─────────
        # Group by (base, ext) globally — files in different subdirectories that
        # share a proposed basename are both disambiguated.
        # Padding width comes from the group size.
        # After assigning an internal suffix we check the filesystem to skip any
        # slot already occupied by an external file; the "own-file exemption"
        # lets us reclaim the slot the renamed file is moving away from.
        group_count = Counter(
            (base, ext)
            for base, ext, _ in checked_rows.values()
            if base
        )
        group_seen = Counter()   # tracks next suffix index per group key

        # resolved_map: original_path -> (proposed_basename, flag, suffix_str)
        resolved_map = {}
        for original_path, (base, ext, original_dir) in checked_rows.items():
            if not base:
                resolved_map[original_path] = ("", "no-name", "")
                continue
            group_key = (base, ext)
            if group_count[group_key] > 1:
                pad = len(str(group_count[group_key]))
                n = group_seen[group_key] + 1
                while True:
                    suffix = f"{n:0{pad}d}"
                    candidate = os.path.join(
                        original_dir, f"{base}_{suffix}{ext}")
                    # Available when no file exists at that path, or the only
                    # occupant is the file we are renaming away from it.
                    if (not os.path.exists(candidate)
                            or os.path.normcase(candidate)
                               == os.path.normcase(original_path)):
                        break
                    n += 1
                group_seen[group_key] = n
                resolved_map[original_path] = (
                    f"{base}_{suffix}{ext}", "dup", suffix)
            else:
                resolved_map[original_path] = (base + ext, "ok", "")

        # ── Pass 3: write proposed names and statuses to every table row ──────
        # Looked up by original_path (from UserRole), NOT by row index, so
        # the result is correct regardless of how the table is currently sorted.
        for row_index in range(row_count):
            cur_item      = self.tblPhotos.item(row_index, _COL_CURRENT)
            proposed_item = self.tblPhotos.item(row_index, _COL_PROPOSED)
            status_item   = self.tblPhotos.item(row_index, _COL_STATUS)
            if None in (cur_item, proposed_item, status_item):
                continue

            original_path = cur_item.data(Qt.UserRole)
            if not original_path:
                continue

            # Skip rows already processed by the rename loop — their Status and
            # Current Filename columns must not be overwritten.
            if original_path in self._frozen_paths:
                continue

            if original_path not in resolved_map:
                # Row is unchecked — clear it
                proposed_item.setText("")
                proposed_item.setToolTip("")
                status_item.setText("")
                continue

            proposed_basename, flag, suffix = resolved_map[original_path]

            if not proposed_basename:
                proposed_item.setText("")
                proposed_item.setToolTip("")
                status_item.setText("No name")
                continue

            proposed_item.setText(proposed_basename)
            proposed_item.setToolTip(proposed_basename)

            original_basename = os.path.basename(original_path)

            # NFC normalise before comparing so macOS NFD filenames equal their
            # NFC counterparts from the eBird CSV.
            if (unicodedata.normalize("NFC", proposed_basename) ==
                    unicodedata.normalize("NFC", original_basename)):
                status_item.setText("No Change")
                continue

            # Check whether the proposed path conflicts with an existing file
            # that is not the file being renamed.
            proposed_path = os.path.join(
                os.path.dirname(original_path), proposed_basename)
            if (os.path.exists(proposed_path)
                    and os.path.normcase(proposed_path)
                       != os.path.normcase(original_path)):
                status_item.setText("Name in use")
            elif flag == "dup":
                status_item.setText(f"Duplicate: Append _{suffix}")
            else:
                status_item.setText("Ready")

            rd = self._rowDataForTableRow(row_index)
            if rd and rd.get("exifDateInvalid"):
                status_item.setToolTip(
                    "EXIF date/time unreadable; using checklist time instead.")
            else:
                status_item.setToolTip("")

        self._updateSample()


    def _updateSample(self):
        """Update the Sample label using the first row in _rows."""
        if not self._rows:
            self.lblSample.setText("Sample: —")
            return
        rd = self._rows[0]
        ext = os.path.splitext(rd["photo"]["fileName"])[1]
        base = self._buildProposedBasename(rd)
        sample = (base + ext) if base else "—"
        self.lblSample.setText(f"Sample: {sample}")


    def _rowDataForTableRow(self, table_row):
        """Map a (possibly sorted) table row back to its _rows entry.

        Compares NFC-normalised paths so that macOS NFD filesystem strings
        and NFC database strings for the same file always match.
        """
        cur_item = self.tblPhotos.item(table_row, _COL_CURRENT)
        if cur_item is None:
            return None
        original_path = unicodedata.normalize(
            "NFC", cur_item.data(Qt.UserRole) or "")
        for rd in self._rows:
            fn = rd["photo"].get("fileName", "") or ""
            if unicodedata.normalize("NFC", fn) == original_path:
                return rd
        return None


    def _getCheckboxForRow(self, table_row):
        """Return the QCheckBox widget embedded in the given row, or None."""
        widget = self.tblPhotos.cellWidget(table_row, _COL_CHECK)
        if widget is None:
            return None
        for child in widget.children():
            if isinstance(child, QCheckBox):
                return child
        return None


    def _resizeContentColumns(self):
        """Size cols 1-3 to content, then ensure the Status column is always
        visible by capping cols 1 and 2 to share the remaining viewport width.

        Long filenames are still fully readable via horizontal scrolling and
        the per-cell tooltips set earlier.
        """
        # Size all three to their natural content width first
        for col in (_COL_CURRENT, _COL_PROPOSED, _COL_STATUS):
            self.tblPhotos.resizeColumnToContents(col)

        # Reserve space: checkbox col + status col + vertical-scrollbar allowance
        vbar_w = self.tblPhotos.verticalScrollBar().sizeHint().width()
        reserved = (self.tblPhotos.columnWidth(_COL_CHECK)
                    + self.tblPhotos.columnWidth(_COL_STATUS)
                    + vbar_w + 4)          # 4 px for borders
        available = self.tblPhotos.viewport().width() - reserved

        col1_natural = self.tblPhotos.columnWidth(_COL_CURRENT)
        col2_natural = self.tblPhotos.columnWidth(_COL_PROPOSED)

        if col1_natural + col2_natural > available:
            # Split available space proportionally to natural widths,
            # with a 120 px floor so neither column collapses entirely.
            total = col1_natural + col2_natural
            if total > 0:
                col1_w = max(120, int(available * col1_natural / total))
                col2_w = max(120, available - col1_w)
            else:
                col1_w = col2_w = max(120, available // 2)
            self.tblPhotos.setColumnWidth(_COL_CURRENT,  col1_w)
            self.tblPhotos.setColumnWidth(_COL_PROPOSED, col2_w)


    def _selectAll(self):
        for row in range(self.tblPhotos.rowCount()):
            chk = self._getCheckboxForRow(row)
            if chk:
                chk.blockSignals(True)
                chk.setChecked(True)
                chk.blockSignals(False)
        self._updateCount()


    def _selectNone(self):
        for row in range(self.tblPhotos.rowCount()):
            chk = self._getCheckboxForRow(row)
            if chk:
                chk.blockSignals(True)
                chk.setChecked(False)
                chk.blockSignals(False)
        self._updateCount()


    def _updateCount(self):
        total    = self.tblPhotos.rowCount()
        selected = sum(
            1 for row in range(total)
            if (chk := self._getCheckboxForRow(row)) and chk.isChecked()
        )
        self.lblCount.setText(f"{selected} of {total} selected")
        self._updateProposedNames()


    def _rename(self):
        """Rename files per their proposed names, update the in-memory db, and
        write incremental JSONL tombstone+append pairs for each rename.
        A full compact runs once at the end.
        The window stays open so the user can rename further batches.
        """
        db = self.mdiParent.db
        self.btnRename.setEnabled(False)
        try:
            self._doRename(db)
        finally:
            self.btnRename.setEnabled(True)


    def _doRename(self, db):
        # ── Step 1: collect rename candidates ─────────────────────────────────
        rename_list = []   # (table_row, rd, old_path, proposed_basename)
        for row in range(self.tblPhotos.rowCount()):
            chk = self._getCheckboxForRow(row)
            if chk is None or not chk.isChecked():
                continue
            status_item = self.tblPhotos.item(row, _COL_STATUS)
            if status_item is None:
                continue
            status = status_item.text()
            if status != "Ready" and not status.startswith("Duplicate:"):
                continue
            cur_item      = self.tblPhotos.item(row, _COL_CURRENT)
            proposed_item = self.tblPhotos.item(row, _COL_PROPOSED)
            if cur_item is None or proposed_item is None:
                continue
            old_path         = cur_item.data(Qt.UserRole)
            proposed_basename = proposed_item.text()
            if not old_path or not proposed_basename:
                continue
            rd = self._rowDataForTableRow(row)
            if rd is None:
                continue
            rename_list.append((row, rd, old_path, proposed_basename))

        if not rename_list:
            QMessageBox.information(
                self, "Nothing to Rename",
                "No files are ready to rename.\n\n"
                "Select files whose status is 'Ready' or 'Duplicate: Append _X'.",
                QMessageBox.StandardButton.Ok,
            )
            return

        # ── Step 2: ensure a JSONL file is open ──────────────────────────────
        if not db.photoDataFile or not db.photoDataFile.lower().endswith(".jsonl"):
            self.mdiParent._promptJsonlMigrationIfNeeded()
            if not db.photoDataFile or not db.photoDataFile.lower().endswith(".jsonl"):
                QMessageBox.warning(
                    self, "No Photo Catalog",
                    "A photo settings (.jsonl) file must be open before renaming.\n\n"
                    "Please open or create one and try again.",
                    QMessageBox.StandardButton.Ok,
                )
                return

        # ── Step 3: compact any pending session changes ───────────────────────
        self.mdiParent.checkIfPhotoDataNeedSaving()

        # ── Step 4: confirm ───────────────────────────────────────────────────
        n = len(rename_list)
        confirm = code_Stylesheet.question(
            self, "Confirm Rename",
            f"Rename {n} file{'s' if n != 1 else ''}?\n\nThis cannot be undone.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        # ── Step 5: rename loop ───────────────────────────────────────────────
        unique_token  = uuid.uuid4().hex[:8]
        succeeded     = 0
        failed        = 0

        self.tblPhotos.setSortingEnabled(False)

        for (row, rd, old_path, proposed_basename) in rename_list:
            new_path = os.path.join(os.path.dirname(old_path), proposed_basename)
            tmp_path = old_path + f".ybtmp.{unique_token}"

            try:
                # Phase 1: current → temp (breaks rename chains / cycles)
                os.rename(old_path, tmp_path)
                # Phase 2: temp → final.  os.replace is used (not os.rename) so
                # the move succeeds on Windows even if a destination file appeared
                # in the window between the pre-flight check and here.
                os.replace(tmp_path, new_path)
            except OSError as exc:
                # Attempt to restore if stuck in the temp state
                if os.path.exists(tmp_path) and not os.path.exists(old_path):
                    try:
                        os.rename(tmp_path, old_path)
                    except OSError:
                        pass
                msg = _OSERROR_MESSAGES.get(exc.errno, exc.strerror or str(exc))
                status_item = self.tblPhotos.item(row, _COL_STATUS)
                if status_item:
                    status_item.setText(msg)
                    status_item.setForeground(_ERROR_RED)
                self._frozen_paths.add(old_path)
                failed += 1
                continue

            # Update live db dict in-place — rd["photo"] IS the dict in the db
            rd["photo"]["fileName"] = new_path

            # Write incremental JSONL: new record first, tombstone second.
            # Writing in this order means a failure on the tombstone write leaves
            # a harmless duplicate (old name still in JSONL alongside new name)
            # rather than a tombstone with no replacement, which would cause the
            # photo to vanish on the next compaction.
            try:
                db.appendPhotoToJsonl(rd["sighting"], rd["photo"])
            except IOError:
                rd["photo"]["fileName"] = old_path   # undo db update
                try:
                    os.rename(new_path, old_path)    # undo filesystem rename
                except OSError:
                    pass
                status_item = self.tblPhotos.item(row, _COL_STATUS)
                if status_item:
                    status_item.setText("Settings save failed")
                    status_item.setForeground(_ERROR_RED)
                self._frozen_paths.add(old_path)
                failed += 1
                continue

            # Tombstone the old path only after the new record is safely written.
            # A failure here leaves a harmless duplicate; Optimize will clean it.
            try:
                db.appendPhotoDeletionToJsonl(old_path)
            except IOError:
                pass

            # Update table row so subsequent operations use the new path
            cur_item = self.tblPhotos.item(row, _COL_CURRENT)
            if cur_item:
                new_basename = os.path.basename(new_path)
                cur_item.setText(new_basename)
                cur_item.setToolTip(new_basename)
                cur_item.setData(Qt.UserRole, new_path)

            proposed_item = self.tblPhotos.item(row, _COL_PROPOSED)
            if proposed_item:
                proposed_item.setText("")
                proposed_item.setToolTip("")

            status_item = self.tblPhotos.item(row, _COL_STATUS)
            if status_item:
                status_item.setText("Done")

            # Update any open Photos window's pixmap cache so it doesn't
            # serve the old path's cached pixmap under the new filename.
            for w in self.mdiParent.mdiArea.subWindowList():
                cache = getattr(w, "pixmapCache", None)
                if cache and old_path in cache:
                    cache[new_path] = cache.pop(old_path)

            self._frozen_paths.add(new_path)
            succeeded += 1

        # ── Final compact ─────────────────────────────────────────────────────
        if succeeded > 0:
            db.compactJsonlFile()

        # ── Refresh proposed names for any remaining unprocessed rows ─────────
        # _updateProposedNames() re-enables sorting via its own finally block,
        # so we leave it disabled here to close the race window between the
        # rename loop ending and _updateProposedNames() disabling it again.
        self._updateProposedNames()
        self._resizeContentColumns()

        # ── Summary ──────────────────────────────────────────────────────────
        s_word = lambda n: f"{n} file{'s' if n != 1 else ''}"
        if failed == 0:
            self.lblCount.setText(f"{s_word(succeeded)} renamed")
        else:
            self.lblCount.setText(
                f"{s_word(succeeded)} renamed, {s_word(failed)} failed")
            QMessageBox.warning(
                self, "Rename Completed with Errors",
                f"{s_word(succeeded)} renamed successfully.\n"
                f"{s_word(failed)} failed.\n\n"
                "See the Status column for details.",
                QMessageBox.StandardButton.Ok,
            )


    # ── Qt overrides ───────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)


    def handlePhotoDeletion(self, filename):
        for r in range(self.tblPhotos.rowCount()):
            item = self.tblPhotos.item(r, _COL_CURRENT)
            if item and item.data(Qt.UserRole) == filename:
                self.tblPhotos.removeRow(r)
                self._rows = [row for row in self._rows if row["photo"]["fileName"] != filename]
                break


    def resizeMe(self):
        windowWidth  = self.width() - 10
        windowHeight = self.height()
        self.frmContainer.setGeometry(5, 27, windowWidth, windowHeight - 32)


    def scaleMe(self):
        fontSize    = self.mdiParent.fontSize
        scaleFactor = self.mdiParent.scaleFactor

        for w in self.children():
            try:
                w.setFont(QFont("Helvetica", fontSize))
            except Exception:
                pass

        windowWidth  = int(960 * scaleFactor)
        windowHeight = int(720 * scaleFactor)
        self.resize(windowWidth, windowHeight)
