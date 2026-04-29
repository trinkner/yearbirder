import base64
import copy
import calendar
import colorsys
import datetime
import os

import numpy as np

import form_Graphs
import code_Lists
import code_Photos
import code_SpeciesGallery

from collections import defaultdict
from math import floor
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch, Rectangle

from PySide6.QtGui import QCursor, QFont, QIcon, QPixmap
from PySide6.QtCore import Qt, Signal, QByteArray, QBuffer, QIODevice
from PySide6.QtWidgets import QApplication, QMdiSubWindow, QToolTip, QVBoxLayout, QMessageBox

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

# App colour palette (matches code_Stylesheet.py)
from code_Stylesheet import (CHART_PRIMARY, CHART_SECONDARY,
                             PHOTO_PRIMARY, PHOTO_SECONDARY)
_BG_COLOR     = "#1e1f26"
_AXES_COLOR   = "#252730"
_TEXT_COLOR   = "#e2e4ec"
_GRID_COLOR   = "#2e3040"
_GREY_COLOR   = "#5a5e73"   # disabled-looking text

_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_DAY_LIMIT   = 1000
_TOP_N_LOCS  = 20

_SEASON_COLORS = {
    "Winter": "#7ab8d4",   # Dec 20–Mar 19  steel blue
    "Spring": "#5cd68a",   # Mar 20–Jun 19  green
    "Summer": "#f5c842",   # Jun 20–Sep 19  golden
    "Fall":   "#e8783a",   # Sep 20–Dec 19  orange
}


def _period_key(date, granularity):
    """Return the bucket key for a date string at the given granularity."""
    if granularity == "year":      return date[0:4]
    if granularity == "month":     return date[5:7]
    if granularity == "monthyear": return date[0:7]
    return date  # day


def _period_labels(keys, granularity):
    """Convert sorted bucket keys to human-readable bar labels."""
    if granularity == "month":
        return [_MONTH_NAMES[int(k) - 1] for k in keys]
    if granularity == "monthyear":
        return [_MONTH_NAMES[int(k[5:7]) - 1] + "-" + k[0:4] for k in keys]
    return list(keys)  # year or day: keys are already display-ready


def _get_season(month, day):
    """Return the astronomical season name for a given month and day.

    Winter: Dec 20 – Mar 19
    Spring: Mar 20 – Jun 19
    Summer: Jun 20 – Sep 19
    Fall:   Sep 20 – Dec 19
    """
    if (month == 12 and day >= 20) or month in (1, 2) or (month == 3 and day <= 19):
        return "Winter"
    if (month == 3 and day >= 20) or month in (4, 5) or (month == 6 and day <= 19):
        return "Spring"
    if (month == 6 and day >= 20) or month in (7, 8) or (month == 9 and day <= 19):
        return "Summer"
    return "Fall"  # Sep 20 – Dec 19


class Graphs(QMdiSubWindow, form_Graphs.Ui_frmGraphs):

    resized = Signal()

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.mdiParent = ""
        self.filter = None
        self._canvas = None
        self._fig = None
        self._ax = None
        self._labels = []
        self._counts = []
        self._cumulative_new_species = []
        self._cumulative_new_items   = []
        self._cumulative_highlight   = None
        self._new_counts    = []
        self._repeat_counts = []
        self._new_species   = []
        self._accumulation_highlight = None
        self._life_counts   = []
        self._location_species_lists = []
        self._scatter_x    = np.array([])
        self._scatter_y    = np.array([])
        self._scatter_ids  = []
        self._scatter_locs = []
        self._scatter_dates = []
        self._scatter_durs = []
        self._scatter_species = []
        self._scatter_highlight = None
        self._named_scatter_x       = np.array([])
        self._named_scatter_y       = np.array([])
        self._named_scatter_names   = []
        self._named_scatter_species = []
        self._named_scatter_highlight = None
        self._strip_doys    = np.array([])
        self._strip_years   = np.array([])
        self._strip_dates   = []
        self._strip_locs    = []
        self._strip_species = []
        self._strip_highlight = None
        self._foy_doys      = np.array([])
        self._foy_years     = np.array([])
        self._foy_dates     = []
        self._foy_locs      = []
        self._foy_species   = []
        self._foy_highlight = None
        self._loy_doys      = np.array([])
        self._loy_years     = np.array([])
        self._loy_dates     = []
        self._loy_locs      = []
        self._loy_species   = []
        self._loy_highlight = None
        self._pie_families    = []   # family/order name per wedge
        self._pie_species     = []   # species list per wedge (for tooltip)
        self._pie_species_tallies = []  # per-species individual counts (indivpie only)
        self._pie_counts      = []   # display total per wedge (species count or individual tally)
        self._pie_label_suffix = "species"  # "species" or "individuals"
        self._pie_wedges      = []   # matplotlib Wedge artists
        self._pie_hover_idx   = -1
        self._chart_type = "bar"
        self._hover_annot = None
        self._hover_idx   = -1
        self._bar_species    = []
        self._bar_highlight  = None
        self._bar_item_label = "species"
        self._bar_species_tallies = []
        self._bar_color    = CHART_PRIMARY
        self._repeat_color = CHART_SECONDARY
        self._heatmap_years = []
        self._heatmap_grid         = None
        self._heatmap_species_grid = None
        self._heatmap_highlight    = None
        self._too_many_days = False
        self._day_count = 0
        self._current_granularity = "year"   # "year" | "month" | "monthyear" | "day"

        self.resized.connect(self.resizeMe)
        self.rdoYear.toggled.connect(self._on_granularity_changed)
        self.rdoMonth.toggled.connect(self._on_granularity_changed)
        self.rdoMonthYear.toggled.connect(self._on_granularity_changed)
        self.rdoDay.toggled.connect(self._on_granularity_changed)

    # ------------------------------------------------------------------
    # Qt resize plumbing
    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)

    def resizeMe(self):
        windowWidth  = self.width() - 10
        windowHeight = self.height()
        self.scrollArea.setGeometry(5, 27, windowWidth - 5, windowHeight - 35)
        self.layGraphs.setGeometry(0, 0, windowWidth - 5, windowHeight - 40)

    def scaleMe(self):
        fontSize    = self.mdiParent.fontSize
        scaleFactor = self.mdiParent.scaleFactor

        for w in self.children():
            try:
                w.setFont(QFont("Helvetica", fontSize))
            except Exception:
                pass

        self.lblLocation.setFont(QFont("Helvetica", floor(fontSize * 1.4)))
        self.lblLocation.setStyleSheet("QLabel { font: bold }")
        self.lblDateRange.setFont(QFont("Helvetica", floor(fontSize * 1.2)))
        self.lblDateRange.setStyleSheet("QLabel { font: bold }")
        self.lblDetails.setFont(QFont("Helvetica", floor(fontSize * 1.2)))
        self.lblDetails.setStyleSheet("QLabel { font: bold }")

        windowWidth  = int(800 * scaleFactor)
        windowHeight = int(580 * scaleFactor)
        self.resize(windowWidth, windowHeight)

    def html(self):
        title = self.windowTitle()
        if ': ' in title:
            type_part, filter_part = title.split(': ', 1)
            heading = '<h1>' + type_part + '</h1><h2>' + filter_part + '</h2>'
        else:
            heading = '<h1>' + title + '</h1>'

        myPixmap = self.chartWidget.grab()
        myPixmap = myPixmap.scaledToWidth(600, Qt.SmoothTransformation)

        myByteArray = QByteArray()
        myBuffer = QBuffer(myByteArray)
        myBuffer.open(QIODevice.OpenModeFlag.WriteOnly)
        myPixmap.save(myBuffer, "PNG")

        encodedImage = base64.b64encode(myByteArray)

        html = """
            <!DOCTYPE html>
            <html>
            <head>
            </head>
            <style>
            * {
                font-family: "Times New Roman", Times, serif;
            }
            h1 { font-size: 18pt; margin-bottom: 4px; }
            h2 { font-size: 13pt; font-weight: normal; margin-top: 0; }
            </style>
            <body>
            """

        html = html + heading

        html = html + ("""
        <img src="data:image/png;base64,
        """)

        html = html + str(encodedImage)[1:]

        html = html + ("""
            <font size>
            </body>
            </html>
            """)

        return html

    # ------------------------------------------------------------------
    # Colour palette selection
    # ------------------------------------------------------------------

    def _setup_colors(self):
        """Switch to yellow palette when the graph involves the photo filter."""
        photo_chart_types = {"totalphotos", "ytdphotos", "photopie",
                             "photoaccumulation", "cumulativephotos"}
        is_photo = self._chart_type in photo_chart_types
        if not is_photo and self.filter is not None:
            f = self.filter
            is_photo = bool(
                f.sightingHasPhoto or f.speciesHasPhoto or f.validPhotoSpecies
                or f.camera or f.lens
                or f.startShutterSpeed or f.endShutterSpeed
                or f.startAperture    or f.endAperture
                or f.startFocalLength or f.endFocalLength
                or f.startIso         or f.endIso
                or f.startRating      or f.endRating
            )
        if is_photo:
            self._bar_color    = PHOTO_PRIMARY
            self._repeat_color = PHOTO_SECONDARY
        else:
            self._bar_color    = CHART_PRIMARY
            self._repeat_color = CHART_SECONDARY

        rdo_style = self._rdo_checked_style()
        for btn in (self.rdoYear, self.rdoMonth, self.rdoMonthYear, self.rdoDay,
                    self.rdoPieFamily, self.rdoPieOrder):
            btn.setStyleSheet(rdo_style)

    # ------------------------------------------------------------------
    # Radio button handler
    # ------------------------------------------------------------------

    def _on_granularity_changed(self):
        if self.filter is None:
            return
        if not self.sender().isChecked():
            return

        # If the user clicks By Day when it's over the limit, show a message
        # and silently revert to the previous valid selection.
        if self.rdoDay.isChecked() and self._too_many_days:
            for btn in (self.rdoYear, self.rdoMonth, self.rdoMonthYear, self.rdoDay):
                btn.blockSignals(True)
            if self._current_granularity == "month":
                self.rdoMonth.setChecked(True)
            elif self._current_granularity == "monthyear":
                self.rdoMonthYear.setChecked(True)
            else:
                self.rdoYear.setChecked(True)
            for btn in (self.rdoYear, self.rdoMonth, self.rdoMonthYear, self.rdoDay):
                btn.blockSignals(False)
            QMessageBox.information(
                self,
                "Too Many Days",
                f"The current filter returned {self._day_count} days, "
                f"which is more than the {_DAY_LIMIT:,}-day limit for By Day view.\n\n"
                "Narrow your date filter and try again.")
            return

        if self.rdoYear.isChecked():
            self._current_granularity = "year"
        elif self.rdoMonth.isChecked():
            self._current_granularity = "month"
        elif self.rdoMonthYear.isChecked():
            self._current_granularity = "monthyear"
        else:
            self._current_granularity = "day"

        labels, counts, item_lists, y_label = self._get_current_data()
        self._draw_chart(labels, counts, item_lists, y_label, self._bar_item_label)

    # ------------------------------------------------------------------
    # Day-button visual state
    # ------------------------------------------------------------------

    def _rdo_checked_style(self):
        """Return the QSS snippet that colours checked indicators with the current palette."""
        c = self._bar_color
        return f"QRadioButton::indicator:checked {{ background: {c}; border-color: {c}; }}"

    def _update_month_year_button_style(self):
        self.rdoMonthYear.setStyleSheet(self._rdo_checked_style())

    def _update_day_button_style(self):
        base = self._rdo_checked_style()
        if self._too_many_days:
            self.rdoDay.setStyleSheet(
                f"QRadioButton {{ color: {_GREY_COLOR}; }} {base}")
        else:
            self.rdoDay.setStyleSheet(base)

    # ------------------------------------------------------------------
    # Data builders
    # ------------------------------------------------------------------

    def _filtered_sightings(self):
        """Minimal filtered list, excluding slash / spuh / hybrid entries."""
        minimal = self.mdiParent.db.GetMinimalFilteredSightingsList(self.filter)
        cf = self.mdiParent.db.CompileFilter(self.filter)
        result = []
        for s in minimal:
            name = s["commonName"]
            if "/" in name or "sp." in name or " x " in name:
                continue
            if self.mdiParent.db.TestSightingCompiled(s, cf):
                result.append(s)
        return result

    def _build_year_data(self, sightings):
        bucket = defaultdict(set)
        for s in sightings:
            bucket[s["date"][0:4]].add(s["commonName"])
        labels = sorted(bucket.keys())
        counts = [len(bucket[k]) for k in labels]
        species_lists = [self._taxo_sort(bucket[k], sightings) for k in labels]
        return labels, counts, species_lists, "Species per Year"

    def _build_ytd_data(self, sightings):
        """For each year, count species seen up to today's month/day (YTD) and for
        the full calendar year.

        Returns (years, ytd_counts, full_counts, ytd_recent_items, today) where
        years is sorted most-recent-first and ytd_recent_items[i] lists species
        sorted by their first-seen date within that year's YTD window, most-recent first.
        """
        today = datetime.date.today()
        ytd_cutoff = f"{today.month:02d}-{today.day:02d}"  # "MM-DD"

        year_all = defaultdict(set)
        year_ytd = defaultdict(set)
        year_ytd_first: dict[str, dict[str, str]] = defaultdict(dict)

        for s in sightings:
            year = s["date"][0:4]
            name = s["commonName"]
            date = s["date"]
            year_all[year].add(name)
            if date[5:10] <= ytd_cutoff:
                year_ytd[year].add(name)
                prev = year_ytd_first[year].get(name)
                if prev is None or date < prev:
                    year_ytd_first[year][name] = date

        if not year_all:
            return [], [], [], [], today

        years = sorted(year_all.keys(), reverse=True)
        ytd_counts = [len(year_ytd[y]) for y in years]
        full_counts = [len(year_all[y]) for y in years]

        ytd_recent_items = []
        for y in years:
            first_seen = year_ytd_first[y]
            ytd_recent_items.append(
                sorted(first_seen, key=lambda sp: first_seen[sp], reverse=True))

        return years, ytd_counts, full_counts, ytd_recent_items, today

    def _build_ytd_locations_data(self, sightings):
        """For each year, count distinct locations visited up to today's month/day
        (YTD) and for the full calendar year.

        Returns (years, ytd_counts, full_counts, ytd_recent_items, today) where
        years is sorted most-recent-first and ytd_recent_items[i] lists locations
        sorted by their first-visit date within that year's YTD window, most-recent first.
        """
        today = datetime.date.today()
        ytd_cutoff = f"{today.month:02d}-{today.day:02d}"  # "MM-DD"

        year_all = defaultdict(set)
        year_ytd = defaultdict(set)
        year_ytd_first: dict[str, dict[str, str]] = defaultdict(dict)

        for s in sightings:
            year = s["date"][0:4]
            loc  = s["location"]
            date = s["date"]
            year_all[year].add(loc)
            if date[5:10] <= ytd_cutoff:
                year_ytd[year].add(loc)
                prev = year_ytd_first[year].get(loc)
                if prev is None or date < prev:
                    year_ytd_first[year][loc] = date

        if not year_all:
            return [], [], [], [], today

        years = sorted(year_all.keys(), reverse=True)
        ytd_counts = [len(year_ytd[y]) for y in years]
        full_counts = [len(year_all[y]) for y in years]

        ytd_recent_items = []
        for y in years:
            first_seen = year_ytd_first[y]
            ytd_recent_items.append(
                sorted(first_seen, key=lambda loc: first_seen[loc], reverse=True))

        return years, ytd_counts, full_counts, ytd_recent_items, today

    def _build_ytd_checklists_data(self, sightings):
        """For each year, count distinct checklists submitted up to today's
        month/day (YTD) and for the full calendar year.

        Returns (years, ytd_counts, full_counts, ytd_recent_items, today) where
        ytd_recent_items[i] lists 'YYYY-MM-DD  Location' strings for the most
        recently submitted checklists within that year's YTD window.
        """
        today = datetime.date.today()
        ytd_cutoff = f"{today.month:02d}-{today.day:02d}"  # "MM-DD"

        year_all = defaultdict(set)   # year → set of checklistIDs
        year_ytd = defaultdict(set)   # year → set of checklistIDs (YTD only)
        cl_info  = {}                 # checklistID → (date, location)

        for s in sightings:
            year = s["date"][0:4]
            cid  = s["checklistID"]
            year_all[year].add(cid)
            cl_info[cid] = (s["date"], s["location"])
            if s["date"][5:10] <= ytd_cutoff:
                year_ytd[year].add(cid)

        if not year_all:
            return [], [], [], [], today

        years      = sorted(year_all.keys(), reverse=True)
        ytd_counts = [len(year_ytd[y]) for y in years]
        full_counts = [len(year_all[y]) for y in years]

        # Most-recently-submitted first: sort by checklist date descending
        ytd_recent_items = []
        for y in years:
            sorted_cls = sorted(
                year_ytd[y],
                key=lambda cid: cl_info[cid][0],
                reverse=True)
            ytd_recent_items.append(
                [f"{cl_info[cid][0]}  {cl_info[cid][1]}" for cid in sorted_cls])

        return years, ytd_counts, full_counts, ytd_recent_items, today

    def _build_ytd_photos_data(self, sightings):
        """For each year, count photos taken up to today's month/day (YTD) and
        for the full calendar year.

        Returns (years, ytd_counts, full_counts, ytd_recent_items, today) where
        ytd_recent_items[i] lists 'YYYY-MM-DD  Species' strings for the most
        recently photographed species within that year's YTD window.
        """
        today = datetime.date.today()
        ytd_cutoff = f"{today.month:02d}-{today.day:02d}"  # "MM-DD"

        year_all = defaultdict(int)   # year → total photo count
        year_ytd = defaultdict(int)   # year → YTD photo count
        # year → {species: most-recent sighting date within YTD}
        year_ytd_sp_date: dict[str, dict[str, str]] = defaultdict(dict)

        for s in sightings:
            photos = s.get("photos", [])
            if not photos:
                continue
            year    = s["date"][0:4]
            n       = len(photos)
            year_all[year] += n
            if s["date"][5:10] <= ytd_cutoff:
                year_ytd[year] += n
                species = s["commonName"]
                date    = s["date"]
                prev = year_ytd_sp_date[year].get(species)
                if prev is None or date > prev:
                    year_ytd_sp_date[year][species] = date

        if not year_all:
            return [], [], [], [], today

        years      = sorted(year_all.keys(), reverse=True)
        ytd_counts = [year_ytd[y] for y in years]
        full_counts = [year_all[y] for y in years]

        ytd_recent_items = []
        for y in years:
            sp_date = year_ytd_sp_date[y]
            sorted_pairs = sorted(sp_date.items(), key=lambda x: x[1], reverse=True)
            ytd_recent_items.append(
                [f"{date}  {sp}" for sp, date in sorted_pairs])

        return years, ytd_counts, full_counts, ytd_recent_items, today

    def _build_month_data(self, sightings):
        bucket = defaultdict(set)
        for s in sightings:
            bucket[s["date"][5:7]].add(s["commonName"])
        month_nums = sorted(bucket.keys())
        labels = [_MONTH_NAMES[int(m) - 1] for m in month_nums]
        counts = [len(bucket[m]) for m in month_nums]
        species_lists = [self._taxo_sort(bucket[m], sightings) for m in month_nums]
        return labels, counts, species_lists, "Species per Month"

    def _build_month_year_data(self, sightings):
        """One bar per YYYY-MM, sorted chronologically, labelled 'Jan-2020' etc."""
        bucket = defaultdict(set)
        for s in sightings:
            bucket[s["date"][0:7]].add(s["commonName"])   # key = "YYYY-MM"
        keys   = sorted(bucket.keys())
        labels = [_MONTH_NAMES[int(k[5:7]) - 1] + "-" + k[0:4] for k in keys]
        counts = [len(bucket[k]) for k in keys]
        species_lists = [self._taxo_sort(bucket[k], sightings) for k in keys]
        return labels, counts, species_lists, "Species per Month"

    def _build_day_data(self, sightings):
        bucket = defaultdict(set)
        for s in sightings:
            bucket[s["date"]].add(s["commonName"])
        labels = sorted(bucket.keys())
        counts = [len(bucket[k]) for k in labels]
        species_lists = [self._taxo_sort(bucket[k], sightings) for k in labels]
        return labels, counts, species_lists, "Species per Day"

    def _build_checklist_count_data(self, sightings, granularity):
        """Return (labels, counts, checklist_lists, y_label) for any granularity.

        checklist_lists[i] is a list of 'YYYY-MM-DD  Location' strings sorted by date.
        """
        bucket  = defaultdict(set)    # period_key → set of checklistIDs
        cl_info = {}                  # checklistID → (date, location)
        for s in sightings:
            key = _period_key(s["date"], granularity)
            bucket[key].add(s["checklistID"])
            cl_info[s["checklistID"]] = (s["date"], s["location"])

        keys   = sorted(bucket.keys())
        labels = _period_labels(keys, granularity)
        counts = [len(bucket[k]) for k in keys]
        checklist_lists = [
            sorted(f"{cl_info[cid][0]}  {cl_info[cid][1]}" for cid in bucket[k])
            for k in keys
        ]
        suffix = {"year": "per Year", "month": "per Month",
                  "monthyear": "per Month", "day": "per Day"}[granularity]
        return labels, counts, checklist_lists, f"Checklists {suffix}"

    def _build_location_count_data(self, sightings, granularity):
        """Return (labels, counts, location_lists, y_label) for any granularity.

        location_lists[i] is a sorted list of distinct location name strings.
        """
        bucket = defaultdict(set)    # period_key → set of locations
        for s in sightings:
            bucket[_period_key(s["date"], granularity)].add(s["location"])

        keys   = sorted(bucket.keys())
        labels = _period_labels(keys, granularity)
        counts = [len(bucket[k]) for k in keys]
        location_lists = [sorted(bucket[k]) for k in keys]
        suffix = {"year": "per Year", "month": "per Month",
                  "monthyear": "per Month", "day": "per Day"}[granularity]
        return labels, counts, location_lists, f"Locations {suffix}"

    def _build_photo_count_data(self, sightings, granularity):
        """Return (labels, counts, species_lists, species_tallies, y_label).

        counts[i] = total photos in period
        species_lists[i] = species names sorted by photo count descending
        species_tallies[i] = parallel photo counts for each species
        """
        bucket = defaultdict(lambda: defaultdict(int))  # period_key → species → photo_count
        for s in sightings:
            photos = s.get("photos", [])
            if not photos:
                continue
            key = _period_key(s["date"], granularity)
            bucket[key][s["commonName"]] += len(photos)

        keys   = sorted(bucket.keys())
        labels = _period_labels(keys, granularity)
        counts = [sum(bucket[k].values()) for k in keys]

        species_lists   = []
        species_tallies = []
        for k in keys:
            sorted_species = sorted(bucket[k].items(), key=lambda x: x[1], reverse=True)
            species_lists.append([sp for sp, _ in sorted_species])
            species_tallies.append([cnt for _, cnt in sorted_species])

        suffix = {"year": "per Year", "month": "per Month",
                  "monthyear": "per Month", "day": "per Day"}[granularity]
        return labels, counts, species_lists, species_tallies, f"Photographs {suffix}"

    def _build_cumulative_data(self, sightings):
        daily = defaultdict(set)
        for s in sightings:
            daily[s["date"]].add(s["commonName"])

        # Build taxonomic index once — _taxo_sort would rebuild it on every call,
        # which is O(|sightings|) × |dates| and very slow on large unfiltered datasets.
        taxo_index = {}
        for i, s in enumerate(sightings):
            name = s["commonName"]
            if name not in taxo_index:
                taxo_index[name] = i

        dates = sorted(daily.keys())
        seen = set()
        counts = []
        new_species = []
        for d in dates:
            new_sp = daily[d] - seen
            new_species.append(sorted(new_sp, key=lambda sp: taxo_index.get(sp, 999999)))
            seen |= daily[d]
            counts.append(len(seen))
        return dates, counts, new_species, "Cumulative Species"

    def _build_cumulative_photos_data(self, sightings):
        """Return (dates, counts, new_species, y_label, date_best_photo).

        Each date is the first day a photo was taken of each species.
        date_best_photo: {date_str: {species: path}} — best photo for each
        species on the date it was first photographed.
        """
        species_first_photo = {}   # sp -> earliest date with a photo
        # best photo per (date, species) across all sightings
        date_sp_best = {}          # (date, sp) -> (rating, path)

        for s in sightings:
            photos = s.get("photos")
            if not photos:
                continue
            sp   = s["commonName"]
            date = s["date"]
            if sp not in species_first_photo or date < species_first_photo[sp]:
                species_first_photo[sp] = date
            for p in photos:
                path = p.get("fileName", "")
                if not path:
                    continue
                try:
                    rating = int(p.get("rating") or 0)
                except (ValueError, TypeError):
                    rating = 0
                key = (date, sp)
                if key not in date_sp_best or rating > date_sp_best[key][0]:
                    date_sp_best[key] = (rating, path)

        if not species_first_photo:
            return [], [], [], "", {}

        # For each species pick the best photo taken on its first-photo date
        date_best_photo = defaultdict(dict)
        for sp, first_date in species_first_photo.items():
            entry = date_sp_best.get((first_date, sp))
            if entry:
                date_best_photo[first_date][sp] = entry[1]

        daily = defaultdict(set)
        for sp, date in species_first_photo.items():
            daily[date].add(sp)

        taxo_index = {}
        for i, s in enumerate(sightings):
            name = s["commonName"]
            if name not in taxo_index:
                taxo_index[name] = i

        dates = sorted(daily.keys())
        seen  = set()
        counts      = []
        new_species = []
        for d in dates:
            new_species.append(sorted(daily[d], key=lambda sp: taxo_index.get(sp, 999999)))
            seen  |= daily[d]
            counts.append(len(seen))
        return dates, counts, new_species, "Cumulative Species Photographed", dict(date_best_photo)

    def _build_cumulative_locations_data(self, sightings):
        """Return (dates, counts, new_locations, y_label).

        new_locations[i] is a sorted list of location names first seen on dates[i].
        """
        daily = defaultdict(set)
        for s in sightings:
            daily[s["date"]].add(s["location"])
        dates = sorted(daily.keys())
        seen = set()
        counts = []
        new_locations = []
        for d in dates:
            new_locs = sorted(daily[d] - seen)
            seen |= daily[d]
            counts.append(len(seen))
            new_locations.append(new_locs)
        return dates, counts, new_locations, "Cumulative Locations"

    def _build_cumulative_families_data(self, sightings):
        """Return (dates, counts, new_families, y_label).

        new_families[i] is a list of (family_name, species_list) tuples for each
        family first encountered on dates[i].  species_list holds the taxo-sorted
        species from that family seen on that introduction day.
        """
        by_date = defaultdict(lambda: defaultdict(set))
        for s in sightings:
            fam = s.get("family", "") or "Unknown"
            by_date[s["date"]][fam].add(s["commonName"])
        dates = sorted(by_date.keys())
        seen_fams = set()
        counts = []
        new_families = []
        for d in dates:
            day_fams = by_date[d]
            new_fam_entries = []
            for fam in sorted(day_fams.keys() - seen_fams):
                sp = self._taxo_sort(day_fams[fam], sightings)
                new_fam_entries.append((fam, sp))
            seen_fams |= set(day_fams.keys())
            counts.append(len(seen_fams))
            new_families.append(new_fam_entries)
        return dates, counts, new_families, "Cumulative Families"

    def _build_heatmap_data(self, sightings):
        """Return (grid, years, species_grid).

        grid[i][j] = species count for year i, month j.
        species_grid[i][j] = sorted list of species names for that cell.
        """
        bucket = defaultdict(set)
        for s in sightings:
            key = (int(s["date"][0:4]), int(s["date"][5:7]))
            bucket[key].add(s["commonName"])
        years = sorted(set(k[0] for k in bucket), reverse=True)
        grid         = np.zeros((len(years), 12), dtype=int)
        species_grid = [[[] for _ in range(12)] for _ in range(len(years))]
        for i, year in enumerate(years):
            for j in range(12):
                sp = self._taxo_sort(bucket.get((year, j + 1), set()), sightings)
                grid[i, j]         = len(sp)
                species_grid[i][j] = sp
        return grid, years, species_grid

    def _build_accumulation_data(self, sightings):
        """Return (years, new_counts, repeat_counts, new_species) for stacked accumulation chart."""
        by_year = defaultdict(set)
        for s in sightings:
            by_year[s["date"][0:4]].add(s["commonName"])
        years = sorted(by_year.keys())
        seen_before = set()
        new_counts    = []
        repeat_counts = []
        new_species   = []
        for year in years:
            year_species = by_year[year]
            new_sp = self._taxo_sort(year_species - seen_before, sightings)
            new_counts.append(len(new_sp))
            repeat_counts.append(len(year_species & seen_before))
            new_species.append(new_sp)
            seen_before |= year_species
        return years, new_counts, repeat_counts, new_species

    def _build_photo_accumulation_data(self, sightings):
        """Return (years, new_counts, repeat_counts, new_species) for photo accumulation chart.

        new_species[i] is a list of (common_name, first_photo_date, location) tuples —
        one entry per species first photographed in year i, in taxonomic order.
        """
        # Find earliest photo date and location per species across the filtered sightings
        species_first = {}   # species -> (date, location)
        by_year_any  = defaultdict(set)   # year -> species with ANY photo that year

        for s in sightings:
            if not s.get("photos"):
                continue
            sp   = s["commonName"]
            date = s["date"]
            year = date[:4]
            by_year_any[year].add(sp)
            if sp not in species_first or date < species_first[sp][0]:
                species_first[sp] = (date, s.get("location", ""))

        if not species_first:
            return [], [], [], []

        years = sorted(by_year_any.keys())
        seen_before   = set()
        new_counts    = []
        repeat_counts = []
        new_species   = []

        for year in years:
            year_species = by_year_any[year]
            new_sp_set   = year_species - seen_before
            repeat_count = len(year_species & seen_before)

            sorted_names = self._taxo_sort(list(new_sp_set), sightings)
            new_species.append([
                (name, species_first[name][0], species_first[name][1])
                for name in sorted_names
            ])
            new_counts.append(len(sorted_names))
            repeat_counts.append(repeat_count)
            seen_before |= new_sp_set

        return years, new_counts, repeat_counts, new_species

    def _build_top_locations_data(self, sightings):
        """Return (locations, counts, life_counts) sorted descending, capped at _TOP_N_LOCS.

        life_counts[i] = number of species at locations[i] that were first seen
        globally (across the entire database) at that location.
        """
        # Filtered species per location
        bucket = defaultdict(set)
        for s in sightings:
            bucket[s["location"]].add(s["commonName"])

        ranked = sorted(bucket.items(), key=lambda x: len(x[1]), reverse=True)
        ranked = ranked[:_TOP_N_LOCS]
        ranked.reverse()   # highest at top of horizontal chart

        locations = [r[0] for r in ranked]
        counts    = [len(r[1]) for r in ranked]

        # Compute life birds: for each species, find the globally earliest date
        # across ALL sightings, then see which location(s) had it on that date.
        species_first_date = {}
        for s in self.mdiParent.db.sightingList:
            sp = s["commonName"]
            dt = s["date"]
            if sp not in species_first_date or dt < species_first_date[sp]:
                species_first_date[sp] = dt

        # Map location → set of species first seen there (globally)
        life_at_location = defaultdict(set)
        for s in self.mdiParent.db.sightingList:
            if s["date"] == species_first_date.get(s["commonName"]):
                life_at_location[s["location"]].add(s["commonName"])

        # Intersect with the filtered species at each location
        life_counts = [len(bucket[loc] & life_at_location[loc])
                       for loc in locations]

        species_lists = [self._taxo_sort(list(bucket[loc]), sightings) for loc in locations]

        return locations, counts, life_counts, species_lists

    def _build_scatter_data(self, checklists, sightings):
        """Split checklists into scatter data and incidental (0-duration) count.

        Species count per checklist is derived from the already-filtered
        sightings list so that family/order/species filters are respected.
        """
        # Count only the filtered species per checklist
        checklist_species = defaultdict(set)
        for s in sightings:
            checklist_species[s["checklistID"]].add(s["commonName"])

        x, y, colors, ids, locs, dates, durs, species_lists = [], [], [], [], [], [], [], []
        incidental_count = 0
        for c in checklists:
            dur_str = c[7]
            try:
                dur = int(dur_str) if dur_str else 0
            except (ValueError, TypeError):
                dur = 0
            if dur <= 0:
                incidental_count += 1
                continue
            sp_set = checklist_species.get(c[0], set())
            if not sp_set:
                continue
            month = int(c[4][5:7])
            day   = int(c[4][8:10])
            season = _get_season(month, day)
            x.append(dur)
            y.append(len(sp_set))
            colors.append(_SEASON_COLORS[season])
            ids.append(c[0])
            locs.append(c[3])
            dates.append(c[4])
            durs.append(dur)
            species_lists.append(self._taxo_sort(sp_set, sightings))
        return x, y, colors, ids, locs, dates, durs, species_lists, incidental_count

    def _build_location_scatter_data(self, sightings):
        """One dot per location: X = checklist count, Y = species count.

        Returns (x_vals, y_vals, names, species_lists).
        """
        loc_species   = defaultdict(set)
        loc_checklists = defaultdict(set)
        for s in sightings:
            loc_species[s["location"]].add(s["commonName"])
            loc_checklists[s["location"]].add(s["checklistID"])
        names         = sorted(loc_species.keys())
        x_vals        = [len(loc_checklists[loc]) for loc in names]
        y_vals        = [len(loc_species[loc])    for loc in names]
        species_lists = [self._taxo_sort(loc_species[loc], sightings) for loc in names]
        return x_vals, y_vals, names, species_lists

    def _build_species_scatter_data(self, sightings):
        """One dot per species: X = distinct location count, Y = individual count.

        Returns (x_vals, y_vals, names).
        """
        sp_locations = defaultdict(set)
        sp_indiv     = defaultdict(int)
        for s in sightings:
            sp_locations[s["commonName"]].add(s["location"])
            sp_indiv[s["commonName"]] += self._parse_indiv_count(s.get("count", 0))
        names  = self._taxo_sort(sp_locations.keys(), sightings)
        x_vals = [len(sp_locations[sp]) for sp in names]
        y_vals = [sp_indiv[sp]          for sp in names]
        return x_vals, y_vals, names

    def _build_strip_data(self, sightings):
        """One dot per unique date the species was seen.

        Returns (doys, years, dates, loc_lists, species_lists, colors) sorted
        chronologically.  loc_lists[i] and species_lists[i] are sorted lists of
        the locations / filter-matching species seen on dates[i].
        """
        date_locs    = defaultdict(set)
        date_species = defaultdict(set)
        for s in sightings:
            date_locs[s["date"]].add(s["location"])
            date_species[s["date"]].add(s["commonName"])

        doys, years, dates_out, loc_lists, species_lists, colors = [], [], [], [], [], []

        for d in sorted(date_locs.keys()):
            year  = int(d[0:4])
            month = int(d[5:7])
            day   = int(d[8:10])
            doy   = (datetime.date(year, month, day) -
                     datetime.date(year, 1, 1)).days + 1

            season = _get_season(month, day)

            doys.append(doy)
            years.append(year)
            dates_out.append(d)
            loc_lists.append(sorted(date_locs[d]))
            species_lists.append(sorted(date_species[d]))
            colors.append(_SEASON_COLORS[season])

        return doys, years, dates_out, loc_lists, species_lists, colors

    def _draw_strip_chart(self, doys, years, dates, loc_lists, species_lists, colors):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        self._strip_doys    = np.array(doys,  dtype=float)
        self._strip_years   = np.array(years, dtype=float)
        self._strip_dates   = dates
        self._strip_locs    = loc_lists
        self._strip_species = species_lists

        fig = Figure(facecolor=_BG_COLOR)
        ax  = fig.add_subplot(111, facecolor=_AXES_COLOR)

        ax.scatter(doys, years, c=colors, s=20, alpha=1.0, zorder=2, linewidths=0)

        # X-axis: month name labels at each month's start day
        _MONTH_STARTS = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
        ax.set_xticks(_MONTH_STARTS)
        ax.set_xticklabels(_MONTH_NAMES, color=_TEXT_COLOR, fontsize=8)
        ax.set_xlim(1, 366)

        # Y-axis: one tick per year that has data
        unique_years = sorted(set(years))
        ax.set_yticks(unique_years)
        ax.set_yticklabels([str(y) for y in unique_years],
                           color=_TEXT_COLOR, fontsize=8)
        ax.tick_params(colors=_TEXT_COLOR, which="both")

        for spine in ax.spines.values():
            spine.set_edgecolor(_GRID_COLOR)

        # Vertical grid lines at month boundaries
        ax.set_xticks(_MONTH_STARTS, minor=False)
        ax.xaxis.grid(True, color=_GRID_COLOR, linewidth=0.5, zorder=1)
        ax.yaxis.grid(True, color=_GRID_COLOR, linewidth=0.5, zorder=1)
        ax.set_axisbelow(True)

        # Season legend
        legend_handles = [
            Patch(facecolor=_SEASON_COLORS[s], label=f"{s} ({lbl})", alpha=0.8)
            for s, lbl in (("Winter", "Dec 20–Mar 19"), ("Spring", "Mar 20–Jun 19"),
                           ("Summer", "Jun 20–Sep 19"), ("Fall",   "Sep 20–Dec 19"))
        ]
        fig.tight_layout()
        legend = fig.legend(handles=legend_handles, loc="lower center",
                            bbox_to_anchor=(0.5, 0.01), ncol=4,
                            facecolor=_AXES_COLOR, edgecolor=_GRID_COLOR, fontsize=8)
        for text in legend.get_texts():
            text.set_color(_TEXT_COLOR)

        canvas = FigureCanvasQTAgg(fig)
        layout = self.chartWidget.layout()
        if layout is None:
            layout = QVBoxLayout(self.chartWidget)
            layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(canvas)

        self._fig    = fig
        self._canvas = canvas
        self._ax     = ax
        self._hover_idx = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=self._bar_color, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5)

        self._strip_highlight = ax.scatter(
            [], [], s=55, zorder=4,
            facecolors='none', edgecolors=_TEXT_COLOR, linewidths=1.5)

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event', self._on_strip_click)

    def _build_foy_data(self, sightings):
        """One dot per unique first-of-year date, aggregating all species
        whose first sighting in that year falls on that date.

        Returns (doys, years, dates, loc_lists, species_lists, colors) where
        loc_lists[i] is a sorted list of locations for the FOY sightings on
        that date, and species_lists[i] is a sorted list of species names.
        """
        # (species, year) → earliest date string and its location
        foy     = {}
        foy_loc = {}
        for s in sightings:
            key = (s["commonName"], s["date"][0:4])
            if key not in foy or s["date"] < foy[key]:
                foy[key]     = s["date"]
                foy_loc[key] = s["location"]

        # Aggregate by date
        date_species = defaultdict(list)
        date_locs    = defaultdict(set)
        for (species, year_str), date in foy.items():
            date_species[date].append(species)
            date_locs[date].add(foy_loc[(species, year_str)])

        doys, years, dates_out, loc_lists, species_lists, colors = [], [], [], [], [], []
        for date, sp_list in date_species.items():
            year  = int(date[0:4])
            month = int(date[5:7])
            day   = int(date[8:10])
            doy   = (datetime.date(year, month, day) -
                     datetime.date(year, 1, 1)).days + 1

            season = _get_season(month, day)

            doys.append(doy)
            years.append(year)
            dates_out.append(date)
            loc_lists.append(sorted(date_locs[date]))
            species_lists.append(self._taxo_sort(sp_list, sightings))
            colors.append(_SEASON_COLORS[season])

        return doys, years, dates_out, loc_lists, species_lists, colors

    def _draw_foy_chart(self, doys, years, dates, loc_lists, species, colors):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        self._foy_doys    = np.array(doys,  dtype=float)
        self._foy_years   = np.array(years, dtype=float)
        self._foy_dates   = dates
        self._foy_locs    = loc_lists
        self._foy_species = species

        fig = Figure(facecolor=_BG_COLOR)
        ax  = fig.add_subplot(111, facecolor=_AXES_COLOR)

        # Invert y-axis so most recent year is at the top
        ax.scatter(doys, years, c=colors, s=15, alpha=1.0, zorder=2, linewidths=0)

        # X-axis: month name labels at each month's start day
        _MONTH_STARTS = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
        ax.set_xticks(_MONTH_STARTS)
        ax.set_xticklabels(_MONTH_NAMES, color=_TEXT_COLOR, fontsize=8)
        ax.set_xlim(1, 366)

        # Y-axis: one tick per year that has data
        unique_years = sorted(set(years))
        ax.set_yticks(unique_years)
        ax.set_yticklabels([str(y) for y in unique_years],
                           color=_TEXT_COLOR, fontsize=8)
        ax.tick_params(colors=_TEXT_COLOR, which="both")

        for spine in ax.spines.values():
            spine.set_edgecolor(_GRID_COLOR)

        ax.xaxis.grid(True, color=_GRID_COLOR, linewidth=0.5, zorder=1)
        ax.yaxis.grid(True, color=_GRID_COLOR, linewidth=0.5, zorder=1)
        ax.set_axisbelow(True)

        # Season legend
        legend_handles = [
            Patch(facecolor=_SEASON_COLORS[s], label=f"{s} ({lbl})", alpha=0.8)
            for s, lbl in (("Winter", "Dec 20–Mar 19"), ("Spring", "Mar 20–Jun 19"),
                           ("Summer", "Jun 20–Sep 19"), ("Fall",   "Sep 20–Dec 19"))
        ]
        fig.tight_layout()
        legend = fig.legend(handles=legend_handles, loc="lower center",
                            bbox_to_anchor=(0.5, 0.01), ncol=4,
                            facecolor=_AXES_COLOR, edgecolor=_GRID_COLOR, fontsize=8)
        for text in legend.get_texts():
            text.set_color(_TEXT_COLOR)

        canvas = FigureCanvasQTAgg(fig)
        layout = self.chartWidget.layout()
        if layout is None:
            layout = QVBoxLayout(self.chartWidget)
            layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(canvas)

        self._fig    = fig
        self._canvas = canvas
        self._ax     = ax
        self._hover_idx = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=self._bar_color, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5)

        self._foy_highlight = ax.scatter(
            [], [], s=55, zorder=4,
            facecolors='none', edgecolors=_TEXT_COLOR, linewidths=1.5)

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event', self._on_foy_click)

    def _build_loy_data(self, sightings):
        """One dot per unique last-of-year date, aggregating all species
        whose last sighting in that year falls on that date.

        Returns (doys, years, dates, loc_lists, species_lists, colors) where
        loc_lists[i] is a sorted list of locations for the LOY sightings on
        that date, and species_lists[i] is a sorted list of species names.
        """
        # (species, year) → latest date string and its location
        loy     = {}
        loy_loc = {}
        for s in sightings:
            key = (s["commonName"], s["date"][0:4])
            if key not in loy or s["date"] > loy[key]:
                loy[key]     = s["date"]
                loy_loc[key] = s["location"]

        # Aggregate by date
        date_species = defaultdict(list)
        date_locs    = defaultdict(set)
        for (species, year_str), date in loy.items():
            date_species[date].append(species)
            date_locs[date].add(loy_loc[(species, year_str)])

        doys, years, dates_out, loc_lists, species_lists, colors = [], [], [], [], [], []
        for date, sp_list in date_species.items():
            year  = int(date[0:4])
            month = int(date[5:7])
            day   = int(date[8:10])
            doy   = (datetime.date(year, month, day) -
                     datetime.date(year, 1, 1)).days + 1

            season = _get_season(month, day)

            doys.append(doy)
            years.append(year)
            dates_out.append(date)
            loc_lists.append(sorted(date_locs[date]))
            species_lists.append(self._taxo_sort(sp_list, sightings))
            colors.append(_SEASON_COLORS[season])

        return doys, years, dates_out, loc_lists, species_lists, colors

    def _draw_loy_chart(self, doys, years, dates, loc_lists, species, colors):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        self._loy_doys    = np.array(doys,  dtype=float)
        self._loy_years   = np.array(years, dtype=float)
        self._loy_dates   = dates
        self._loy_locs    = loc_lists
        self._loy_species = species

        fig = Figure(facecolor=_BG_COLOR)
        ax  = fig.add_subplot(111, facecolor=_AXES_COLOR)

        ax.scatter(doys, years, c=colors, s=15, alpha=1.0, zorder=2, linewidths=0)

        _MONTH_STARTS = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
        ax.set_xticks(_MONTH_STARTS)
        ax.set_xticklabels(_MONTH_NAMES, color=_TEXT_COLOR, fontsize=8)
        ax.set_xlim(1, 366)

        unique_years = sorted(set(years))
        ax.set_yticks(unique_years)
        ax.set_yticklabels([str(y) for y in unique_years],
                           color=_TEXT_COLOR, fontsize=8)
        ax.tick_params(colors=_TEXT_COLOR, which="both")

        for spine in ax.spines.values():
            spine.set_edgecolor(_GRID_COLOR)

        ax.xaxis.grid(True, color=_GRID_COLOR, linewidth=0.5, zorder=1)
        ax.yaxis.grid(True, color=_GRID_COLOR, linewidth=0.5, zorder=1)
        ax.set_axisbelow(True)

        legend_handles = [
            Patch(facecolor=_SEASON_COLORS[s], label=f"{s} ({lbl})", alpha=0.8)
            for s, lbl in (("Winter", "Dec 20–Mar 19"), ("Spring", "Mar 20–Jun 19"),
                           ("Summer", "Jun 20–Sep 19"), ("Fall",   "Sep 20–Dec 19"))
        ]
        fig.tight_layout()
        legend = fig.legend(handles=legend_handles, loc="lower center",
                            bbox_to_anchor=(0.5, 0.01), ncol=4,
                            facecolor=_AXES_COLOR, edgecolor=_GRID_COLOR, fontsize=8)
        for text in legend.get_texts():
            text.set_color(_TEXT_COLOR)

        canvas = FigureCanvasQTAgg(fig)
        layout = self.chartWidget.layout()
        if layout is None:
            layout = QVBoxLayout(self.chartWidget)
            layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(canvas)

        self._fig    = fig
        self._canvas = canvas
        self._ax     = ax
        self._hover_idx = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=self._bar_color, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5)

        self._loy_highlight = ax.scatter(
            [], [], s=55, zorder=4,
            facecolors='none', edgecolors=_TEXT_COLOR, linewidths=1.5)

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event', self._on_loy_click)

    def _draw_scatter_chart(self, x, y, colors, ids, locs, dates, durs,
                            species_lists, incidental_count):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        self._scatter_x    = np.array(x, dtype=float)
        self._scatter_y    = np.array(y, dtype=float)
        self._scatter_ids  = ids
        self._scatter_locs = locs
        self._scatter_dates = dates
        self._scatter_durs  = durs
        self._scatter_species = species_lists

        fig = Figure(facecolor=_BG_COLOR)
        ax  = fig.add_subplot(111, facecolor=_AXES_COLOR)

        ax.scatter(x, y, c=colors, alpha=1.0, s=18, zorder=2, linewidths=0)

        ax.set_xlabel("Duration (minutes)", color=_TEXT_COLOR, fontsize=9)
        ax.set_ylabel("Species",            color=_TEXT_COLOR, fontsize=9)
        ax.tick_params(colors=_TEXT_COLOR, which="both", labelcolor=_TEXT_COLOR)

        for spine in ax.spines.values():
            spine.set_edgecolor(_GRID_COLOR)
        ax.xaxis.grid(True, color=_GRID_COLOR, linewidth=0.5, zorder=1)
        ax.yaxis.grid(True, color=_GRID_COLOR, linewidth=0.5, zorder=1)
        ax.set_axisbelow(True)

        # Season legend
        legend_handles = [
            Patch(facecolor=_SEASON_COLORS[s], label=f"{s} ({lbl})", alpha=0.8)
            for s, lbl in (("Winter", "Dec 20–Mar 19"), ("Spring", "Mar 20–Jun 19"),
                           ("Summer", "Jun 20–Sep 19"), ("Fall",   "Sep 20–Dec 19"))
        ]
        legend = ax.legend(handles=legend_handles, loc="upper center",
                           bbox_to_anchor=(0.5, -0.08), ncol=4,
                           facecolor=_AXES_COLOR, edgecolor=_GRID_COLOR, fontsize=8)
        for text in legend.get_texts():
            text.set_color(_TEXT_COLOR)

        # Incidental note
        if incidental_count:
            s = "s" if incidental_count != 1 else ""
            ax.text(0.99, 0.01,
                    f"{incidental_count} incidental observation{s} (no duration) not shown",
                    transform=ax.transAxes, ha="right", va="bottom",
                    color=_GREY_COLOR, fontsize=7)

        fig.tight_layout()

        canvas = FigureCanvasQTAgg(fig)
        layout = self.chartWidget.layout()
        if layout is None:
            layout = QVBoxLayout(self.chartWidget)
            layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(canvas)

        self._fig    = fig
        self._canvas = canvas
        self._ax     = ax
        self._hover_idx = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=self._bar_color, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5)

        self._scatter_highlight = ax.scatter(
            [], [], s=55, zorder=4,
            facecolors='none', edgecolors=_TEXT_COLOR, linewidths=1.5)

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event', self._on_scatter_click)

    def _draw_named_scatter(self, x, y, names, x_label, y_label, species_lists=None):
        """Scatter where each dot is a named entity (location or species).

        No season colouring — uses self._bar_color throughout.
        """
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        self._named_scatter_x       = np.array(x, dtype=float)
        self._named_scatter_y       = np.array(y, dtype=float)
        self._named_scatter_names   = names
        self._named_scatter_species = species_lists or []

        fig = Figure(facecolor=_BG_COLOR)
        ax  = fig.add_subplot(111, facecolor=_AXES_COLOR)

        ax.scatter(x, y, c=self._bar_color, alpha=1.0, s=18, zorder=2, linewidths=0)

        ax.set_xlabel(x_label, color=_TEXT_COLOR, fontsize=9)
        ax.set_ylabel(y_label, color=_TEXT_COLOR, fontsize=9)
        ax.tick_params(colors=_TEXT_COLOR, which="both", labelcolor=_TEXT_COLOR)

        for spine in ax.spines.values():
            spine.set_edgecolor(_GRID_COLOR)
        ax.xaxis.grid(True, color=_GRID_COLOR, linewidth=0.5, zorder=1)
        ax.yaxis.grid(True, color=_GRID_COLOR, linewidth=0.5, zorder=1)
        ax.set_axisbelow(True)

        fig.tight_layout()

        canvas = FigureCanvasQTAgg(fig)
        layout = self.chartWidget.layout()
        if layout is None:
            layout = QVBoxLayout(self.chartWidget)
            layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(canvas)

        self._fig    = fig
        self._canvas = canvas
        self._ax     = ax
        self._hover_idx = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=self._bar_color, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5)

        self._named_scatter_highlight = ax.scatter(
            [], [], s=55, zorder=4,
            facecolors='none', edgecolors=_TEXT_COLOR, linewidths=1.5)

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event', self._on_named_scatter_click)

    def _get_current_data(self):
        sightings = self._filtered_sightings()
        if self._chart_type == "totalchecklists":
            return self._build_checklist_count_data(sightings, self._current_granularity)
        if self._chart_type == "totallocations":
            return self._build_location_count_data(sightings, self._current_granularity)
        if self._chart_type == "totalphotos":
            labels, counts, sp_lists, sp_tallies, y_label = self._build_photo_count_data(sightings, self._current_granularity)
            self._bar_species_tallies = sp_tallies
            return labels, counts, sp_lists, y_label
        # Default: species bar chart
        if self._current_granularity == "month":
            return self._build_month_data(sightings)
        if self._current_granularity == "monthyear":
            return self._build_month_year_data(sightings)
        if self._current_granularity == "day":
            return self._build_day_data(sightings)
        return self._build_year_data(sightings)

    # ------------------------------------------------------------------
    # Chart renderer
    # ------------------------------------------------------------------

    def _draw_chart(self, labels, counts, species_lists, y_label, item_label="species"):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        fig = Figure(facecolor=_BG_COLOR)
        ax  = fig.add_subplot(111, facecolor=_AXES_COLOR)

        n     = len(labels)
        x_pos = range(n)
        bars  = ax.bar(x_pos, counts, color=self._bar_color, width=0.6, zorder=2)

        many = n > 10
        if n <= 50:
            ax.bar_label(bars, padding=3, color=_TEXT_COLOR,
                         fontsize=7 if many else 9)

        # Limit x-axis labels to ~50 via dynamic stride when there are many bars
        stride      = max(1, n // 50) if n > 50 else 1
        tick_idx    = list(range(0, n, stride))
        tick_labels = [labels[i] for i in tick_idx]

        ax.set_xticks(tick_idx)
        if many:
            ax.set_xticklabels(tick_labels, rotation=45, ha="right",
                               color=_TEXT_COLOR, fontsize=7)
        else:
            ax.set_xticklabels(tick_labels, color=_TEXT_COLOR, fontsize=9)

        ax.set_ylabel(y_label, color=_TEXT_COLOR, fontsize=9)
        ax.tick_params(colors=_TEXT_COLOR, which="both", labelcolor=_TEXT_COLOR)

        for spine in ax.spines.values():
            spine.set_edgecolor(_GRID_COLOR)

        ax.yaxis.grid(True, color=_GRID_COLOR, linewidth=0.5, zorder=1)
        ax.set_axisbelow(True)

        fig.tight_layout()

        canvas = FigureCanvasQTAgg(fig)

        layout = self.chartWidget.layout()
        if layout is None:
            layout = QVBoxLayout(self.chartWidget)
            layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(canvas)

        self._fig    = fig
        self._canvas = canvas
        self._ax     = ax
        self._labels = labels
        self._counts         = counts
        self._bar_species    = species_lists
        self._bar_item_label = item_label
        self._hover_idx      = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=self._bar_color, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5)

        bar_rect = Rectangle((0, 0), 0.6, 1,
                              linewidth=1.5, edgecolor=_TEXT_COLOR,
                              facecolor='none', visible=False, zorder=4)
        ax.add_patch(bar_rect)
        self._bar_highlight = bar_rect

        canvas.mpl_connect('button_press_event', self._on_bar_click)
        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)

    def _draw_line_chart(self, labels, counts, new_species, y_label, new_items=None):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        fig = Figure(facecolor=_BG_COLOR)
        ax  = fig.add_subplot(111, facecolor=_AXES_COLOR)

        x_pos = list(range(len(labels)))
        ax.plot(x_pos, counts, color=self._bar_color, linewidth=1.5, zorder=2)
        ax.fill_between(x_pos, counts, alpha=0.15, color=self._bar_color, zorder=1)

        # Annotate final value
        ax.annotate(str(counts[-1]),
                    xy=(x_pos[-1], counts[-1]),
                    xytext=(-5, 6), textcoords="offset points",
                    color=_TEXT_COLOR, fontsize=9, ha="right")

        # Thin x-axis ticks to ~12 if many data points
        n = len(labels)
        if n > 24:
            step = max(1, n // 12)
            tick_idx    = list(range(0, n, step))
            tick_labels = [labels[i] for i in tick_idx]
        else:
            tick_idx    = x_pos
            tick_labels = labels

        ax.set_xticks(tick_idx)
        if len(tick_idx) > 10:
            ax.set_xticklabels(tick_labels, rotation=45, ha="right",
                               color=_TEXT_COLOR, fontsize=7)
        else:
            ax.set_xticklabels(tick_labels, color=_TEXT_COLOR, fontsize=9)

        ax.set_ylabel(y_label, color=_TEXT_COLOR, fontsize=9)
        ax.tick_params(colors=_TEXT_COLOR, which="both", labelcolor=_TEXT_COLOR)

        for spine in ax.spines.values():
            spine.set_edgecolor(_GRID_COLOR)

        ax.yaxis.grid(True, color=_GRID_COLOR, linewidth=0.5, zorder=0)
        ax.set_axisbelow(True)

        fig.tight_layout()

        canvas = FigureCanvasQTAgg(fig)

        layout = self.chartWidget.layout()
        if layout is None:
            layout = QVBoxLayout(self.chartWidget)
            layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(canvas)

        self._fig    = fig
        self._canvas = canvas
        self._ax     = ax
        self._labels = labels
        self._counts = counts
        self._cumulative_new_species = new_species
        self._cumulative_new_items   = new_items if new_items is not None else []
        self._hover_idx = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=self._bar_color, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5)

        self._cumulative_highlight = ax.scatter(
            [], [], s=55, zorder=4,
            facecolors='none', edgecolors=_TEXT_COLOR, linewidths=1.5)

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event', self._on_line_click)

    def _draw_heatmap(self, grid, years, species_grid):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        self._heatmap_years        = years
        self._heatmap_grid         = grid
        self._heatmap_species_grid = species_grid

        fig = Figure(facecolor=_BG_COLOR)
        ax  = fig.add_subplot(111, facecolor=_AXES_COLOR)

        # Custom colormap: near-black for low counts → app blue for high counts
        cmap = LinearSegmentedColormap.from_list(
            'yearbirder_heat', ['#a0c4ff', self._bar_color, '#1e4a8a', '#1a2a45'])
        cmap.set_bad(color=_GRID_COLOR)   # no-data cells

        masked = np.ma.masked_where(grid == 0, grid)
        im = ax.imshow(masked, cmap=cmap, aspect='auto',
                       vmin=1, vmax=max(grid.max(), 1))

        # Month labels on x-axis, year labels on y-axis
        ax.set_xticks(range(12))
        ax.set_xticklabels(_MONTH_NAMES, color=_TEXT_COLOR, fontsize=8)
        ax.set_yticks(range(len(years)))
        ax.set_yticklabels([str(y) for y in years], color=_TEXT_COLOR, fontsize=8)
        ax.tick_params(colors=_TEXT_COLOR, which="both")

        for spine in ax.spines.values():
            spine.set_edgecolor(_GRID_COLOR)

        # Annotate every non-empty cell with its species count;
        # scale font size down gracefully as the number of years grows
        cell_fontsize = max(6, 14 - len(years) // 5)
        for i in range(len(years)):
            for j in range(12):
                val = int(grid[i, j])
                if val > 0:
                    ax.text(j, i, str(val), ha='center', va='center',
                            color=_TEXT_COLOR, fontsize=cell_fontsize)

        # Colorbar
        cbar = fig.colorbar(im, ax=ax, pad=0.02)
        cbar.set_label("Species", color=_TEXT_COLOR, fontsize=8)
        cbar.ax.yaxis.set_tick_params(color=_TEXT_COLOR, labelcolor=_TEXT_COLOR)

        fig.tight_layout()

        canvas = FigureCanvasQTAgg(fig)

        layout = self.chartWidget.layout()
        if layout is None:
            layout = QVBoxLayout(self.chartWidget)
            layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(canvas)

        self._fig    = fig
        self._canvas = canvas
        self._ax     = ax
        self._hover_idx = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=self._bar_color, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5)

        # White outline that tracks the hovered cell
        rect = Rectangle((0, 0), 1, 1,
                          linewidth=1.5, edgecolor=_TEXT_COLOR,
                          facecolor='none', visible=False, zorder=4)
        ax.add_patch(rect)
        self._heatmap_highlight = rect

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event', self._on_heatmap_click)

    def _draw_stacked_bar_chart(self, labels, new_counts, repeat_counts, new_species,
                                click_handler=None):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        self._new_counts    = new_counts
        self._repeat_counts = repeat_counts
        self._new_species   = new_species

        fig = Figure(facecolor=_BG_COLOR)
        ax  = fig.add_subplot(111, facecolor=_AXES_COLOR)

        x_pos = list(range(len(labels)))
        ax.bar(x_pos, repeat_counts, color=self._repeat_color, width=0.6,
               label="Seen Before", zorder=2)
        ax.bar(x_pos, new_counts, bottom=repeat_counts, color=self._bar_color,
               width=0.6, label="New", zorder=2)

        many     = len(labels) > 10
        fontsize = 7 if many else 9

        # Label each bar with the new-species count above it
        for i, (new, rep) in enumerate(zip(new_counts, repeat_counts)):
            if new > 0:
                ax.text(i, rep + new, f"+{new}",
                        ha="center", va="bottom",
                        color=_TEXT_COLOR, fontsize=fontsize)

        ax.set_xticks(x_pos)
        if many:
            ax.set_xticklabels(labels, rotation=45, ha="right",
                               color=_TEXT_COLOR, fontsize=7)
        else:
            ax.set_xticklabels(labels, color=_TEXT_COLOR, fontsize=fontsize)

        ax.set_ylabel("Species", color=_TEXT_COLOR, fontsize=9)
        ax.tick_params(colors=_TEXT_COLOR, which="both", labelcolor=_TEXT_COLOR)

        for spine in ax.spines.values():
            spine.set_edgecolor(_GRID_COLOR)

        ax.yaxis.grid(True, color=_GRID_COLOR, linewidth=0.5, zorder=1)
        ax.set_axisbelow(True)

        legend = ax.legend(loc="upper left", facecolor=_AXES_COLOR,
                           edgecolor=_GRID_COLOR, fontsize=8)
        for text in legend.get_texts():
            text.set_color(_TEXT_COLOR)

        fig.tight_layout()

        canvas = FigureCanvasQTAgg(fig)
        layout = self.chartWidget.layout()
        if layout is None:
            layout = QVBoxLayout(self.chartWidget)
            layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(canvas)

        self._fig    = fig
        self._canvas = canvas
        self._ax     = ax
        self._labels = labels
        self._hover_idx = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=self._bar_color, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5)

        # White outline that tracks the hovered bar
        bar_rect = Rectangle((0, 0), 0.6, 1,
                              linewidth=1.5, edgecolor=_TEXT_COLOR,
                              facecolor='none', visible=False, zorder=4)
        ax.add_patch(bar_rect)
        self._accumulation_highlight = bar_rect

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event',
                           click_handler if click_handler is not None
                           else self._on_accumulation_click)

    def _draw_horizontal_bar_chart(self, locations, counts, life_counts, species_lists=None):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        self._life_counts = life_counts
        self._location_species_lists = species_lists if species_lists is not None else [[] for _ in locations]
        non_life_counts   = [t - l for t, l in zip(counts, life_counts)]

        fig = Figure(facecolor=_BG_COLOR)
        ax  = fig.add_subplot(111, facecolor=_AXES_COLOR)

        y_pos = list(range(len(locations)))

        # Non-life-bird segment (left portion)
        ax.barh(y_pos, non_life_counts, color=self._repeat_color, height=0.6,
                label="Previously seen", zorder=2)

        # Life-bird segment (right portion, bright blue)
        life_bars = ax.barh(y_pos, life_counts, left=non_life_counts,
                            color=self._bar_color, height=0.6,
                            label="Life birds", zorder=2)

        # Total count label at the end of each full bar
        for i, total in enumerate(counts):
            ax.text(total, i, f" {total}", va="center",
                    color=_TEXT_COLOR, fontsize=8)

        # Truncate long location names for y-axis readability
        max_chars = 40
        y_labels  = [loc if len(loc) <= max_chars else loc[:max_chars - 1] + "…"
                     for loc in locations]
        ax.set_yticks(y_pos)
        ax.set_yticklabels(y_labels, color=_TEXT_COLOR, fontsize=8)

        ax.set_xlabel("Species", color=_TEXT_COLOR, fontsize=9)
        ax.tick_params(colors=_TEXT_COLOR, which="both", labelcolor=_TEXT_COLOR)

        for spine in ax.spines.values():
            spine.set_edgecolor(_GRID_COLOR)

        ax.xaxis.grid(True, color=_GRID_COLOR, linewidth=0.5, zorder=1)
        ax.set_axisbelow(True)

        # Extend x-axis so total labels don't clip
        ax.set_xlim(right=ax.get_xlim()[1] * 1.1)

        legend = ax.legend(loc="lower right", facecolor=_AXES_COLOR,
                           edgecolor=_GRID_COLOR, fontsize=8)
        for text in legend.get_texts():
            text.set_color(_TEXT_COLOR)

        fig.tight_layout()

        canvas = FigureCanvasQTAgg(fig)
        layout = self.chartWidget.layout()
        if layout is None:
            layout = QVBoxLayout(self.chartWidget)
            layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(canvas)

        self._fig    = fig
        self._canvas = canvas
        self._ax     = ax
        self._labels = locations   # full (untruncated) names for click/hover
        self._counts = counts
        self._hover_idx = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=self._bar_color, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5)

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event', self._on_location_click)

    def _draw_ytd_chart(self, years, ytd_counts, full_counts, ytd_recent_items,
                        item_label, today):
        """Draw a horizontal YTD bar chart for either species or locations.

        item_label  "species" or "locations" — used in tooltip text.
        """
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        self._ytd_years        = years
        self._ytd_ytd_counts   = ytd_counts
        self._ytd_full_counts  = full_counts
        self._ytd_recent_items = ytd_recent_items
        self._ytd_item_label   = item_label

        n = len(years)
        current_year = str(today.year)
        today_label = f"{today.day} {today.strftime('%b')}"  # e.g. "10 Apr"

        y_pos = list(range(n))
        max_val = max(full_counts) if full_counts else 1

        fig = Figure(facecolor=_BG_COLOR)
        ax = fig.add_subplot(111, facecolor=_BG_COLOR)

        # Gray extension bars (full_count − ytd_count) for past years
        for i, year in enumerate(years):
            if year != current_year:
                extra = full_counts[i] - ytd_counts[i]
                if extra > 0:
                    ax.barh(i, extra, left=ytd_counts[i], color=self._repeat_color,
                            height=0.5, zorder=2)

        # Blue YTD bars
        ax.barh(y_pos, ytd_counts, color=self._bar_color, height=0.5, zorder=3)

        # Label layout: reserve left margin for year + YTD count text
        left_margin = max_val * 0.20

        for i, year in enumerate(years):
            is_current = (year == current_year)
            weight = "bold" if is_current else "normal"

            # Year label
            ax.text(-left_margin, i, year,
                    ha="left", va="center",
                    color=_TEXT_COLOR, fontsize=10, fontweight=weight)

            # YTD species count in green, right-aligned just before bar start
            ax.text(-left_margin * 0.15, i, str(ytd_counts[i]),
                    ha="right", va="center",
                    color=self._bar_color, fontsize=10, fontweight="bold")

            # Full year total at right end of gray bar (past years only)
            if year != current_year and full_counts[i] > 0:
                ax.text(full_counts[i] + max_val * 0.025, i, str(full_counts[i]),
                        ha="left", va="center",
                        color=_TEXT_COLOR, fontsize=10)

        # Column header labels above the top bar
        header_y = -0.8
        ax.text(0, header_y, today_label, ha="left", va="center",
                color=_GREY_COLOR, fontsize=8)
        ax.text(max_val, header_y, "31 Dec", ha="right", va="center",
                color=_GREY_COLOR, fontsize=8)

        # Clean axes
        ax.set_yticks([])
        ax.set_xticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)

        ax.set_xlim(-left_margin * 1.1, max_val * 1.15)
        # Set ylim before inverting: -1.2 will become the visual top (header row),
        # n - 0.5 will become the visual bottom.
        ax.set_ylim(-1.2, n - 0.5)
        ax.invert_yaxis()

        fig.tight_layout()

        canvas = FigureCanvasQTAgg(fig)
        layout = self.chartWidget.layout()
        if layout is None:
            layout = QVBoxLayout(self.chartWidget)
            layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(canvas)

        self._fig = fig
        self._canvas = canvas
        self._ax = ax
        self._hover_idx = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=self._bar_color, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5)

        # Horizontal highlight outline (width updated on each hover event)
        highlight_rect = Rectangle((0, -0.25), 1, 0.5,
                                   linewidth=1.5, edgecolor=_TEXT_COLOR,
                                   facecolor="none", visible=False, zorder=4)
        ax.add_patch(highlight_rect)
        self._bar_highlight = highlight_rect

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event', self._on_ytd_click)

    # ------------------------------------------------------------------
    # Bar click → spawn species list
    # ------------------------------------------------------------------

    # Max days per month for seasonal filter (use 29 for Feb to cover leap years)
    _MONTH_DAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    def _on_mouse_move(self, event):
        if self._chart_type in ("ytdreport", "ytdlocations", "ytdchecklists", "ytdphotos"):
            self._update_ytd_hover(event)
        elif self._chart_type == "cumulative":
            self._update_hover_annotation(event)
        elif self._chart_type == "cumulativephotos":
            self._update_cumulative_photos_hover(event)
        elif self._chart_type == "cumulativelocations":
            self._update_cumulative_locations_hover(event)
        elif self._chart_type == "cumulativefamilies":
            self._update_cumulative_families_hover(event)
        elif self._chart_type == "heatmap":
            self._update_heatmap_hover(event)
        elif self._chart_type == "accumulation":
            self._update_accumulation_hover(event)
        elif self._chart_type == "photoaccumulation":
            self._update_photo_accumulation_hover(event)
        elif self._chart_type == "locations":
            self._update_location_hover(event)
        elif self._chart_type == "scatter":
            self._update_scatter_hover(event)
        elif self._chart_type in ("locationscatter", "speciesscatter"):
            self._update_named_scatter_hover(event)
        elif self._chart_type == "strip":
            self._update_strip_hover(event)
        elif self._chart_type == "foy":
            self._update_foy_hover(event)
        elif self._chart_type == "loy":
            self._update_loy_hover(event)
        elif self._chart_type in ("familypie", "indivpie", "locationchecklistpie", "photopie"):
            self._update_family_pie_hover(event)
        else:
            self._update_bar_hover(event)

    def _update_hover_annotation(self, event):
        if self._hover_annot is None:
            return
        if event.inaxes is not self._ax or event.xdata is None:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                if self._cumulative_highlight is not None:
                    self._cumulative_highlight.set_offsets(np.empty((0, 2)))
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        idx = int(round(event.xdata))
        if not (0 <= idx < len(self._labels)):
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                if self._cumulative_highlight is not None:
                    self._cumulative_highlight.set_offsets(np.empty((0, 2)))
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)

        if idx == self._hover_idx:
            return  # already showing this point — no redraw needed

        self._hover_idx = idx
        x, y = idx, self._counts[idx]
        sp_list = (self._cumulative_new_species[idx]
                   if idx < len(self._cumulative_new_species) else [])
        n_new = len(sp_list)
        limit = self._tooltip_species_limit(anchor_data_xy=(x, y))

        tip = f"{self._labels[idx]}\n{y} species total  +{n_new} new"
        for name in sp_list[:limit]:
            tip += f"\n  {name}"
        if n_new > limit:
            tip += f"\n  (+{n_new - limit} more)"
        n_lines = 2 + min(n_new, limit) + (1 if n_new > limit else 0)

        self._hover_annot.xy = (x, y)
        self._hover_annot.set_text(tip)
        self._position_tooltip(event, n_lines, (x, y))
        self._hover_annot.set_visible(True)
        if self._cumulative_highlight is not None:
            self._cumulative_highlight.set_offsets([[x, y]])
        self._canvas.draw_idle()

    _THUMB_PX   = 150   # thumbnail long-edge size in pixels
    _MAX_THUMBS = 6     # maximum species shown with thumbnails

    def _update_cumulative_photos_hover(self, event):
        """Hover for cumulativephotos: Qt thumbnail tooltip + scatter dot."""
        hide_all = event.inaxes is not self._ax or event.xdata is None
        if not hide_all:
            idx = int(round(event.xdata))
            hide_all = not (0 <= idx < len(self._labels))

        if hide_all:
            if self._cumulative_highlight is not None:
                self._cumulative_highlight.set_offsets(np.empty((0, 2)))
            if self._hover_idx != -1:
                self._hover_idx = -1
                self._canvas.draw_idle()
            QToolTip.hideText()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)
        if idx == self._hover_idx:
            return
        self._hover_idx = idx

        x, y = idx, self._counts[idx]
        if self._cumulative_highlight is not None:
            self._cumulative_highlight.set_offsets([[x, y]])
        self._canvas.draw_idle()

        sp_list = (self._cumulative_new_species[idx]
                   if idx < len(self._cumulative_new_species) else [])
        n_new = len(sp_list)

        date_str   = self._labels[idx]
        best_photo = getattr(self, '_date_species_best', {}).get(date_str, {})
        cache      = getattr(self, '_photo_thumb_cache', {})

        parts = [
            f"<b>{self._labels[idx]}</b><br>"
            f"{y} species photographed &nbsp; +{n_new} new<br>"
        ]

        for sp in sp_list[:self._MAX_THUMBS]:
            path = best_photo.get(sp, "")
            if path and os.path.isfile(path):
                if path not in cache:
                    px = QPixmap(path)
                    if not px.isNull():
                        px = px.scaled(
                            self._THUMB_PX, self._THUMB_PX,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
                        ba = QByteArray()
                        buf = QBuffer(ba)
                        buf.open(QIODevice.OpenModeFlag.WriteOnly)
                        px.toImage().save(buf, "JPEG", 85)
                        buf.close()
                        cache[path] = base64.b64encode(bytes(ba)).decode("ascii")
                b64 = cache.get(path)
                if b64:
                    parts.append(
                        f'<img src="data:image/jpeg;base64,{b64}"><br>'
                        f'<small>{sp}</small><br>'
                    )
                    continue
            # Fallback: no image available
            parts.append(f'<small>{sp}</small><br>')

        if n_new > self._MAX_THUMBS:
            parts.append(f'<small>+{n_new - self._MAX_THUMBS} more</small>')

        QToolTip.showText(QCursor.pos(), "".join(parts), self._canvas)

    def _update_cumulative_locations_hover(self, event):
        if self._hover_annot is None:
            return
        if event.inaxes is not self._ax or event.xdata is None:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                if self._cumulative_highlight is not None:
                    self._cumulative_highlight.set_offsets(np.empty((0, 2)))
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        idx = int(round(event.xdata))
        if not (0 <= idx < len(self._labels)):
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                if self._cumulative_highlight is not None:
                    self._cumulative_highlight.set_offsets(np.empty((0, 2)))
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)
        if idx == self._hover_idx:
            return

        self._hover_idx = idx
        x, y   = idx, self._counts[idx]
        new_locs = self._cumulative_new_items[idx] if idx < len(self._cumulative_new_items) else []
        n_new    = len(new_locs)
        limit    = self._tooltip_species_limit(anchor_data_xy=(x, y))

        tip = f"{self._labels[idx]}\n{y} locations total  +{n_new} new"
        for loc in new_locs[:limit]:
            tip += f"\n  {loc}"
        if n_new > limit:
            tip += f"\n  (+{n_new - limit} more)"
        n_lines = 2 + min(n_new, limit) + (1 if n_new > limit else 0)

        self._hover_annot.xy = (x, y)
        self._hover_annot.set_text(tip)
        self._position_tooltip(event, n_lines, (x, y))
        self._hover_annot.set_visible(True)
        if self._cumulative_highlight is not None:
            self._cumulative_highlight.set_offsets([[x, y]])
        self._canvas.draw_idle()

    def _update_cumulative_families_hover(self, event):
        if self._hover_annot is None:
            return
        if event.inaxes is not self._ax or event.xdata is None:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                if self._cumulative_highlight is not None:
                    self._cumulative_highlight.set_offsets(np.empty((0, 2)))
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        idx = int(round(event.xdata))
        if not (0 <= idx < len(self._labels)):
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                if self._cumulative_highlight is not None:
                    self._cumulative_highlight.set_offsets(np.empty((0, 2)))
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)
        if idx == self._hover_idx:
            return

        self._hover_idx  = idx
        x, y     = idx, self._counts[idx]
        new_fams = self._cumulative_new_items[idx] if idx < len(self._cumulative_new_items) else []
        n_new    = len(new_fams)
        limit    = self._tooltip_species_limit(anchor_data_xy=(x, y))

        tip = f"{self._labels[idx]}\n{y} families total  +{n_new} new"
        shown = 0
        for fam, sp_list in new_fams:
            if shown >= limit:
                remaining = n_new - shown
                tip += f"\n  (+{remaining} more)"
                break
            tip += f"\n  {fam}"
            for sp in sp_list:
                tip += f"\n    {sp}"
            shown += 1
        n_lines = 2 + sum(1 + len(sp) for fam, sp in new_fams[:min(n_new, limit)]) + (1 if n_new > limit else 0)

        self._hover_annot.xy = (x, y)
        self._hover_annot.set_text(tip)
        self._position_tooltip(event, n_lines, (x, y))
        self._hover_annot.set_visible(True)
        if self._cumulative_highlight is not None:
            self._cumulative_highlight.set_offsets([[x, y]])
        self._canvas.draw_idle()

    def _on_bar_click(self, event):
        if event.inaxes is not self._ax or event.xdata is None:
            return
        bar_idx = int(round(event.xdata))
        if not (0 <= bar_idx < len(self._labels)):
            return

        label = self._labels[bar_idx]
        new_filter = copy.deepcopy(self.filter)

        if self._current_granularity == "year":
            new_filter.setStartDate(label + "-01-01")
            new_filter.setEndDate(label + "-12-31")

        elif self._current_granularity == "month":
            month_num = _MONTH_NAMES.index(label) + 1
            last_day  = self._MONTH_DAYS[month_num - 1]
            new_filter.setStartSeasonalMonth(str(month_num).zfill(2))
            new_filter.setStartSeasonalDay("01")
            new_filter.setEndSeasonalMonth(str(month_num).zfill(2))
            new_filter.setEndSeasonalDay(str(last_day).zfill(2))

        elif self._current_granularity == "monthyear":
            month_name = label[0:3]
            year       = int(label[4:])
            month_num  = _MONTH_NAMES.index(month_name) + 1
            last_day   = calendar.monthrange(year, month_num)[1]
            new_filter.setStartDate(f"{year}-{month_num:02d}-01")
            new_filter.setEndDate(f"{year}-{month_num:02d}-{last_day:02d}")

        else:  # day
            new_filter.setStartDate(label)
            new_filter.setEndDate(label)

        if self._chart_type == "totallocations":
            self._spawn_locations_list(new_filter)
        elif self._chart_type == "totalphotos":
            self._spawn_photos_window(new_filter)
        else:
            self._spawn_species_list(new_filter)

    def _on_ytd_click(self, event):
        """Click on a YTD bar opens the appropriate child window for that year (YTD only)."""
        if event.inaxes is not self._ax or event.ydata is None:
            return
        # y-axis is inverted: index 0 = top row (most recent year)
        bar_idx = int(round(event.ydata))
        if not (0 <= bar_idx < len(self._ytd_years)):
            return

        year = self._ytd_years[bar_idx]
        today = datetime.date.today()
        new_filter = copy.deepcopy(self.filter)
        new_filter.setStartDate(f"{year}-01-01")
        new_filter.setEndDate(f"{year}-{today.month:02d}-{today.day:02d}")

        if self._chart_type == "ytdphotos":
            self._spawn_photos_window(new_filter)
        else:
            self._spawn_species_list(new_filter)

    def _update_bar_hover(self, event):
        if self._hover_annot is None:
            return
        if event.inaxes is not self._ax or event.xdata is None:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                if self._bar_highlight is not None:
                    self._bar_highlight.set_visible(False)
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        idx = int(round(event.xdata))
        if not (0 <= idx < len(self._labels)):
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                if self._bar_highlight is not None:
                    self._bar_highlight.set_visible(False)
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)
        if idx == self._hover_idx:
            return

        self._hover_idx = idx
        count   = self._counts[idx]
        sp_list = self._bar_species[idx] if idx < len(self._bar_species) else []
        limit   = self._tooltip_species_limit(anchor_data_xy=(idx, count))

        tip = f"{self._labels[idx]}: {count} {self._bar_item_label}"
        if self._chart_type == "totalphotos" and idx < len(self._bar_species_tallies):
            tallies = self._bar_species_tallies[idx]
            num_sp  = len(sp_list)
            for i, name in enumerate(sp_list[:limit]):
                tally = tallies[i] if i < len(tallies) else ""
                tip += f"\n  {name} ({tally})"
            if num_sp > limit:
                tip += f"\n  (+{num_sp - limit} more)"
            n_lines = 1 + min(num_sp, limit) + (1 if num_sp > limit else 0)
        else:
            for name in sp_list[:limit]:
                tip += f"\n  {name}"
            if count > limit:
                tip += f"\n  (+{count - limit} more)"
            n_lines = 1 + min(count, limit) + (1 if count > limit else 0)

        self._hover_annot.xy = (idx, count)
        self._hover_annot.set_text(tip)
        self._position_tooltip(event, n_lines, (idx, count))
        self._hover_annot.set_visible(True)
        if self._bar_highlight is not None:
            self._bar_highlight.set_xy((idx - 0.3, 0))
            self._bar_highlight.set_height(count)
            self._bar_highlight.set_visible(True)
        self._canvas.draw_idle()

    def _update_heatmap_hover(self, event):
        if self._hover_annot is None:
            return
        if (event.inaxes is not self._ax or event.xdata is None
                or event.ydata is None):
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                if self._heatmap_highlight is not None:
                    self._heatmap_highlight.set_visible(False)
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        col = int(round(event.xdata))   # month index 0-11
        row = int(round(event.ydata))   # year index
        if not (0 <= col < 12 and 0 <= row < len(self._heatmap_years)):
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                if self._heatmap_highlight is not None:
                    self._heatmap_highlight.set_visible(False)
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        cell_key = row * 12 + col
        if cell_key == self._hover_idx:
            return

        self._hover_idx = cell_key
        species = int(self._heatmap_grid[row, col])
        year    = self._heatmap_years[row]
        label   = f"{_MONTH_NAMES[col]} {year}"

        limit = self._tooltip_species_limit(anchor_data_xy=(col, row))
        self._hover_annot.xy = (col, row)
        if species > 0:
            sp_list = (self._heatmap_species_grid[row][col]
                       if self._heatmap_species_grid else [])
            tip = f"{label}  ·  {species} species"
            for name in sp_list[:limit]:
                tip += f"\n  {name}"
            if species > limit:
                tip += f"\n  (+{species - limit} more)"
            n_lines = 1 + min(species, limit) + (1 if species > limit else 0)
            self._canvas.setCursor(Qt.PointingHandCursor)
        else:
            tip = f"{label}\nNo data"
            n_lines = 2
            self._canvas.setCursor(Qt.ArrowCursor)
        self._hover_annot.set_text(tip)
        self._position_tooltip(event, n_lines, (col, row))
        self._hover_annot.set_visible(True)
        if self._heatmap_highlight is not None:
            self._heatmap_highlight.set_xy((col - 0.5, row - 0.5))
            self._heatmap_highlight.set_visible(True)
        self._canvas.draw_idle()

    def _update_location_hover(self, event):
        if self._hover_annot is None:
            return
        if event.inaxes is not self._ax or event.ydata is None:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        idx = int(round(event.ydata))
        if not (0 <= idx < len(self._labels)):
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)
        if idx == self._hover_idx:
            return

        self._hover_idx = idx
        count = self._counts[idx]
        life  = self._life_counts[idx] if self._life_counts else 0
        tip   = f"{self._labels[idx]}\n{count} species"
        if life:
            tip += f"  ·  {life} life birds"
        sp_list = self._location_species_lists[idx] if self._location_species_lists else []
        if sp_list:
            limit = self._tooltip_species_limit(anchor_data_xy=(count, idx))
            for sp in sp_list[:limit]:
                tip += f"\n  {sp}"
            if len(sp_list) > limit:
                tip += f"\n  (+{len(sp_list) - limit} more)"

        self._hover_annot.xy = (count, idx)
        self._hover_annot.set_text(tip)
        self._position_tooltip(event, 2, (count, idx))
        self._hover_annot.set_visible(True)
        self._canvas.draw_idle()

    def _update_ytd_hover(self, event):
        if self._hover_annot is None:
            return
        if event.inaxes is not self._ax or event.ydata is None:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                if self._bar_highlight is not None:
                    self._bar_highlight.set_visible(False)
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        idx = int(round(event.ydata))
        if not (0 <= idx < len(self._ytd_years)):
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                if self._bar_highlight is not None:
                    self._bar_highlight.set_visible(False)
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)
        if idx == self._hover_idx:
            return

        self._hover_idx = idx
        year       = self._ytd_years[idx]
        ytd_count  = self._ytd_ytd_counts[idx]
        full_count = self._ytd_full_counts[idx]
        item_list  = self._ytd_recent_items[idx] if self._ytd_recent_items else []
        item_label = getattr(self, "_ytd_item_label", "species")

        # _tooltip_species_limit budgets for 2 overhead lines (header + "more").
        # YTD has 4: header, blank line, heading row, and "more" — subtract 2 more.
        limit = max(3, self._tooltip_species_limit(anchor_data_xy=(ytd_count, idx)) - 2)

        if item_label == "checklists":
            recent_label = "Most recent:"
        elif item_label == "photos":
            recent_label = "Most recently photographed:"
        else:
            recent_label = "Most recently added:"
        tip = f"{year}: {ytd_count} {item_label} YTD"
        if year != str(datetime.date.today().year):
            tip += f"  /  {full_count} full year"
        tip += f"\n\n{recent_label}"
        for item in item_list[:limit]:
            tip += f"\n  {item}"
        if len(item_list) > limit:
            tip += f"\n  (+{len(item_list) - limit} more)"
        n_lines = 3 + min(len(item_list), limit) + (1 if len(item_list) > limit else 0)

        bar_width = full_count if year != str(datetime.date.today().year) else ytd_count
        self._hover_annot.xy = (ytd_count, idx)
        self._hover_annot.set_text(tip)
        self._position_tooltip(event, n_lines, (ytd_count, idx))
        self._hover_annot.set_visible(True)
        if self._bar_highlight is not None:
            self._bar_highlight.set_xy((0, idx - 0.25))
            self._bar_highlight.set_width(bar_width)
            self._bar_highlight.set_visible(True)
        self._canvas.draw_idle()

    def _on_location_click(self, event):
        if event.inaxes is not self._ax or event.ydata is None:
            return
        idx = int(round(event.ydata))
        if not (0 <= idx < len(self._labels)):
            return
        new_filter = copy.deepcopy(self.filter)
        new_filter.setLocationType("Location")
        new_filter.setLocationName(self._labels[idx])
        self._spawn_species_list(new_filter)

    def _update_strip_hover(self, event):
        if self._hover_annot is None or len(self._strip_doys) == 0:
            return
        if event.inaxes is not self._ax or event.xdata is None or event.ydata is None:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                self._hover_idx = -1
                if self._strip_highlight is not None:
                    self._strip_highlight.set_offsets(np.empty((0, 2)))
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        xlim   = self._ax.get_xlim()
        ylim   = self._ax.get_ylim()
        xrange = xlim[1] - xlim[0] if xlim[1] != xlim[0] else 1.0
        yrange = ylim[1] - ylim[0] if ylim[1] != ylim[0] else 1.0

        dx   = (self._strip_doys  - event.xdata) / xrange
        dy   = (self._strip_years - event.ydata) / yrange
        dist = np.sqrt(dx * dx + dy * dy)
        idx  = int(np.argmin(dist))

        if dist[idx] > 0.03:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                self._hover_idx = -1
                if self._strip_highlight is not None:
                    self._strip_highlight.set_offsets(np.empty((0, 2)))
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)
        if idx == self._hover_idx:
            return

        self._hover_idx = idx
        px = float(self._strip_doys[idx])
        py = float(self._strip_years[idx])

        date    = self._strip_dates[idx]
        locs    = self._strip_locs[idx]
        sp_list = self._strip_species[idx] if idx < len(self._strip_species) else []
        limit   = self._tooltip_species_limit(anchor_data_xy=(px, py))

        loc_text = locs[0] if len(locs) == 1 else f"{locs[0]} + {len(locs)-1} more"
        tip = f"{date}\n{loc_text}"

        n_sp = len(sp_list)
        for name in sp_list[:limit]:
            tip += f"\n  {name}"
        if n_sp > limit:
            tip += f"\n  (+{n_sp - limit} more)"
        n_lines = 2 + min(n_sp, limit) + (1 if n_sp > limit else 0)

        self._hover_annot.xy = (px, py)
        self._hover_annot.set_text(tip)
        self._position_tooltip(event, n_lines, (px, py))
        self._hover_annot.set_visible(True)
        if self._strip_highlight is not None:
            self._strip_highlight.set_offsets([[px, py]])
        self._canvas.draw_idle()

    def _on_strip_click(self, event):
        if event.inaxes is not self._ax or event.xdata is None or event.ydata is None:
            return
        if len(self._strip_doys) == 0:
            return

        xlim   = self._ax.get_xlim()
        ylim   = self._ax.get_ylim()
        xrange = xlim[1] - xlim[0] if xlim[1] != xlim[0] else 1.0
        yrange = ylim[1] - ylim[0] if ylim[1] != ylim[0] else 1.0

        dx   = (self._strip_doys  - event.xdata) / xrange
        dy   = (self._strip_years - event.ydata) / yrange
        dist = np.sqrt(dx * dx + dy * dy)
        idx  = int(np.argmin(dist))

        if dist[idx] > 0.03:
            return

        new_filter = copy.deepcopy(self.filter)
        d = self._strip_dates[idx]
        new_filter.setStartDate(d)
        new_filter.setEndDate(d)
        self._spawn_species_list(new_filter)

    def _update_foy_hover(self, event):
        if self._hover_annot is None or len(self._foy_doys) == 0:
            return
        if event.inaxes is not self._ax or event.xdata is None or event.ydata is None:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                self._hover_idx = -1
                if self._foy_highlight is not None:
                    self._foy_highlight.set_offsets(np.empty((0, 2)))
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        xlim   = self._ax.get_xlim()
        ylim   = self._ax.get_ylim()
        xrange = xlim[1] - xlim[0] if xlim[1] != xlim[0] else 1.0
        yrange = ylim[1] - ylim[0] if ylim[1] != ylim[0] else 1.0

        dx   = (self._foy_doys  - event.xdata) / xrange
        dy   = (self._foy_years - event.ydata) / yrange
        dist = np.sqrt(dx * dx + dy * dy)
        idx  = int(np.argmin(dist))

        if dist[idx] > 0.03:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                self._hover_idx = -1
                if self._foy_highlight is not None:
                    self._foy_highlight.set_offsets(np.empty((0, 2)))
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)
        if idx == self._hover_idx:
            return

        self._hover_idx = idx
        px = float(self._foy_doys[idx])
        py = float(self._foy_years[idx])

        date     = self._foy_dates[idx]
        locs     = self._foy_locs[idx] if idx < len(self._foy_locs) else []
        sp_list  = self._foy_species[idx]
        n        = len(sp_list)
        limit    = self._tooltip_species_limit(anchor_data_xy=(px, py))

        loc_text = locs[0] if len(locs) == 1 else f"{locs[0]} + {len(locs)-1} more"
        tip      = f"{date}  ·  {n} FOY species\n{loc_text}"
        for name in sp_list[:limit]:
            tip += f"\n  {name}"
        if n > limit:
            tip += f"\n  (+{n - limit} more)"
        n_lines = 2 + min(n, limit) + (1 if n > limit else 0)

        self._hover_annot.xy = (px, py)
        self._hover_annot.set_text(tip)
        self._position_tooltip(event, n_lines, (px, py))
        self._hover_annot.set_visible(True)
        if self._foy_highlight is not None:
            self._foy_highlight.set_offsets([[px, py]])
        self._canvas.draw_idle()

    def _on_foy_click(self, event):
        if event.inaxes is not self._ax or event.xdata is None or event.ydata is None:
            return
        if len(self._foy_doys) == 0:
            return

        xlim   = self._ax.get_xlim()
        ylim   = self._ax.get_ylim()
        xrange = xlim[1] - xlim[0] if xlim[1] != xlim[0] else 1.0
        yrange = ylim[1] - ylim[0] if ylim[1] != ylim[0] else 1.0

        dx   = (self._foy_doys  - event.xdata) / xrange
        dy   = (self._foy_years - event.ydata) / yrange
        dist = np.sqrt(dx * dx + dy * dy)
        idx  = int(np.argmin(dist))

        if dist[idx] > 0.03:
            return

        new_filter = copy.deepcopy(self.filter)
        d = self._foy_dates[idx]
        new_filter.setStartDate(d)
        new_filter.setEndDate(d)
        self._spawn_species_list(new_filter)

    def _update_loy_hover(self, event):
        if self._hover_annot is None or len(self._loy_doys) == 0:
            return
        if event.inaxes is not self._ax or event.xdata is None or event.ydata is None:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                self._hover_idx = -1
                if self._loy_highlight is not None:
                    self._loy_highlight.set_offsets(np.empty((0, 2)))
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        xlim   = self._ax.get_xlim()
        ylim   = self._ax.get_ylim()
        xrange = xlim[1] - xlim[0] if xlim[1] != xlim[0] else 1.0
        yrange = ylim[1] - ylim[0] if ylim[1] != ylim[0] else 1.0

        dx   = (self._loy_doys  - event.xdata) / xrange
        dy   = (self._loy_years - event.ydata) / yrange
        dist = np.sqrt(dx * dx + dy * dy)
        idx  = int(np.argmin(dist))

        if dist[idx] > 0.03:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                self._hover_idx = -1
                if self._loy_highlight is not None:
                    self._loy_highlight.set_offsets(np.empty((0, 2)))
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)
        if idx == self._hover_idx:
            return

        self._hover_idx = idx
        px = float(self._loy_doys[idx])
        py = float(self._loy_years[idx])

        date     = self._loy_dates[idx]
        locs     = self._loy_locs[idx] if idx < len(self._loy_locs) else []
        sp_list  = self._loy_species[idx]
        n        = len(sp_list)
        limit    = self._tooltip_species_limit(anchor_data_xy=(px, py))

        loc_text = locs[0] if len(locs) == 1 else f"{locs[0]} + {len(locs)-1} more"
        tip      = f"{date}  ·  {n} LOY species\n{loc_text}"
        for name in sp_list[:limit]:
            tip += f"\n  {name}"
        if n > limit:
            tip += f"\n  (+{n - limit} more)"
        n_lines = 2 + min(n, limit) + (1 if n > limit else 0)

        self._hover_annot.xy = (px, py)
        self._hover_annot.set_text(tip)
        self._position_tooltip(event, n_lines, (px, py))
        self._hover_annot.set_visible(True)
        if self._loy_highlight is not None:
            self._loy_highlight.set_offsets([[px, py]])
        self._canvas.draw_idle()

    def _on_loy_click(self, event):
        if event.inaxes is not self._ax or event.xdata is None or event.ydata is None:
            return
        if len(self._loy_doys) == 0:
            return

        xlim   = self._ax.get_xlim()
        ylim   = self._ax.get_ylim()
        xrange = xlim[1] - xlim[0] if xlim[1] != xlim[0] else 1.0
        yrange = ylim[1] - ylim[0] if ylim[1] != ylim[0] else 1.0

        dx   = (self._loy_doys  - event.xdata) / xrange
        dy   = (self._loy_years - event.ydata) / yrange
        dist = np.sqrt(dx * dx + dy * dy)
        idx  = int(np.argmin(dist))

        if dist[idx] > 0.03:
            return

        new_filter = copy.deepcopy(self.filter)
        d = self._loy_dates[idx]
        new_filter.setStartDate(d)
        new_filter.setEndDate(d)
        self._spawn_species_list(new_filter)

    def _update_scatter_hover(self, event):
        if self._hover_annot is None or len(self._scatter_x) == 0:
            return
        if event.inaxes is not self._ax or event.xdata is None or event.ydata is None:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                self._hover_idx = -1
                if self._scatter_highlight is not None:
                    self._scatter_highlight.set_offsets(np.empty((0, 2)))
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        # Normalise distances to axis ranges so x and y are weighted equally
        xlim = self._ax.get_xlim()
        ylim = self._ax.get_ylim()
        xrange = xlim[1] - xlim[0] if xlim[1] != xlim[0] else 1.0
        yrange = ylim[1] - ylim[0] if ylim[1] != ylim[0] else 1.0

        dx = (self._scatter_x - event.xdata) / xrange
        dy = (self._scatter_y - event.ydata) / yrange
        dist = np.sqrt(dx * dx + dy * dy)
        idx  = int(np.argmin(dist))

        # Only show tooltip if within 3% of axis range
        if dist[idx] > 0.03:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                self._hover_idx = -1
                if self._scatter_highlight is not None:
                    self._scatter_highlight.set_offsets(np.empty((0, 2)))
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)
        if idx == self._hover_idx:
            return

        self._hover_idx = idx
        px = self._scatter_x[idx]
        py = self._scatter_y[idx]

        loc     = self._scatter_locs[idx]
        date    = self._scatter_dates[idx]
        dur     = self._scatter_durs[idx]
        sp_list = self._scatter_species[idx] if idx < len(self._scatter_species) else []
        n       = int(py)
        limit   = self._tooltip_species_limit(anchor_data_xy=(px, py))
        tip     = f"{date}  ·  {n} species\n{int(dur)} min  ·  {loc}"
        for name in sp_list[:limit]:
            tip += f"\n  {name}"
        if len(sp_list) > limit:
            tip += f"\n  (+{len(sp_list) - limit} more)"
        n_lines = 2 + min(len(sp_list), limit) + (1 if len(sp_list) > limit else 0)

        self._hover_annot.xy = (px, py)
        self._hover_annot.set_text(tip)
        self._position_tooltip(event, n_lines, (px, py))
        self._hover_annot.set_visible(True)
        if self._scatter_highlight is not None:
            self._scatter_highlight.set_offsets([[px, py]])
        self._canvas.draw_idle()

    def _on_scatter_click(self, event):
        if event.inaxes is not self._ax or event.xdata is None or event.ydata is None:
            return
        if len(self._scatter_x) == 0:
            return

        xlim = self._ax.get_xlim()
        ylim = self._ax.get_ylim()
        xrange = xlim[1] - xlim[0] if xlim[1] != xlim[0] else 1.0
        yrange = ylim[1] - ylim[0] if ylim[1] != ylim[0] else 1.0

        dx = (self._scatter_x - event.xdata) / xrange
        dy = (self._scatter_y - event.ydata) / yrange
        dist = np.sqrt(dx * dx + dy * dy)
        idx  = int(np.argmin(dist))

        if dist[idx] > 0.03:
            return

        new_filter = copy.deepcopy(self.filter)
        new_filter.setChecklistID(self._scatter_ids[idx])
        self._spawn_species_list(new_filter)

    def _update_named_scatter_hover(self, event):
        if self._hover_annot is None or len(self._named_scatter_x) == 0:
            return
        if event.inaxes is not self._ax or event.xdata is None or event.ydata is None:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                self._hover_idx = -1
                if self._named_scatter_highlight is not None:
                    self._named_scatter_highlight.set_offsets(np.empty((0, 2)))
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        xlim   = self._ax.get_xlim()
        ylim   = self._ax.get_ylim()
        xrange = xlim[1] - xlim[0] if xlim[1] != xlim[0] else 1.0
        yrange = ylim[1] - ylim[0] if ylim[1] != ylim[0] else 1.0

        dx   = (self._named_scatter_x - event.xdata) / xrange
        dy   = (self._named_scatter_y - event.ydata) / yrange
        dist = np.sqrt(dx * dx + dy * dy)
        idx  = int(np.argmin(dist))

        if dist[idx] > 0.03:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                self._hover_idx = -1
                if self._named_scatter_highlight is not None:
                    self._named_scatter_highlight.set_offsets(np.empty((0, 2)))
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)
        if idx == self._hover_idx:
            return

        self._hover_idx = idx
        px = float(self._named_scatter_x[idx])
        py = float(self._named_scatter_y[idx])
        name = self._named_scatter_names[idx]

        if self._chart_type == "locationscatter":
            sp_list = self._named_scatter_species[idx] if idx < len(self._named_scatter_species) else []
            n_sp    = len(sp_list)
            limit   = self._tooltip_species_limit(anchor_data_xy=(px, py))
            tip     = f"{name}\n{int(py)} species  ·  {int(px)} checklists"
            for sp in sp_list[:limit]:
                tip += f"\n  {sp}"
            if n_sp > limit:
                tip += f"\n  (+{n_sp - limit} more)"
            n_lines = 2 + min(n_sp, limit) + (1 if n_sp > limit else 0)
        else:  # speciesscatter
            tip     = f"{name}\n{int(px)} locations  ·  {int(py)} individuals"
            n_lines = 2

        self._hover_annot.xy = (px, py)
        self._hover_annot.set_text(tip)
        self._position_tooltip(event, n_lines, (px, py))
        self._hover_annot.set_visible(True)
        if self._named_scatter_highlight is not None:
            self._named_scatter_highlight.set_offsets([[px, py]])
        self._canvas.draw_idle()

    def _on_named_scatter_click(self, event):
        if event.inaxes is not self._ax or event.xdata is None or event.ydata is None:
            return
        if len(self._named_scatter_x) == 0:
            return

        xlim   = self._ax.get_xlim()
        ylim   = self._ax.get_ylim()
        xrange = xlim[1] - xlim[0] if xlim[1] != xlim[0] else 1.0
        yrange = ylim[1] - ylim[0] if ylim[1] != ylim[0] else 1.0

        dx   = (self._named_scatter_x - event.xdata) / xrange
        dy   = (self._named_scatter_y - event.ydata) / yrange
        dist = np.sqrt(dx * dx + dy * dy)
        idx  = int(np.argmin(dist))

        if dist[idx] > 0.03:
            return

        name = self._named_scatter_names[idx]
        if self._chart_type == "locationscatter":
            self._spawn_location_window(name)
        else:  # speciesscatter
            self._spawn_individual_window(name)

    def _spawn_individual_window(self, species_name):
        import code_Individual
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        sub = code_Individual.Individual()
        sub.mdiParent = self.mdiParent
        sub.FillIndividual(species_name)
        self.mdiParent.mdiArea.addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self.mdiParent)
        sub.show()
        sub.scaleMe()
        QApplication.restoreOverrideCursor()

    def _spawn_location_window(self, location_name):
        import code_Location
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        sub = code_Location.Location()
        sub.mdiParent = self.mdiParent
        sub.FillLocation(location_name)
        self.mdiParent.mdiArea.addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self.mdiParent)
        sub.show()
        sub.scaleMe()
        QApplication.restoreOverrideCursor()

    def _update_accumulation_hover(self, event):
        if self._hover_annot is None:
            return
        if event.inaxes is not self._ax or event.xdata is None:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                if self._accumulation_highlight is not None:
                    self._accumulation_highlight.set_visible(False)
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        idx = int(round(event.xdata))
        if not (0 <= idx < len(self._labels)):
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                if self._accumulation_highlight is not None:
                    self._accumulation_highlight.set_visible(False)
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)
        if idx == self._hover_idx:
            return

        self._hover_idx = idx
        new   = self._new_counts[idx]
        rep   = self._repeat_counts[idx]
        total = new + rep
        sp_list = self._new_species[idx] if idx < len(self._new_species) else []

        limit = self._tooltip_species_limit(anchor_data_xy=(idx, total))
        tip = f"{self._labels[idx]}\nTotal: {total}  New: +{new}"
        for name in sp_list[:limit]:
            tip += f"\n  {name}"
        if new > limit:
            tip += f"\n  (+{new - limit} more)"
        n_lines = 2 + min(new, limit) + (1 if new > limit else 0)

        self._hover_annot.xy = (idx, total)
        self._hover_annot.set_text(tip)
        self._position_tooltip(event, n_lines, (idx, total))
        self._hover_annot.set_visible(True)
        if self._accumulation_highlight is not None:
            self._accumulation_highlight.set_xy((idx - 0.3, 0))
            self._accumulation_highlight.set_height(total)
            self._accumulation_highlight.set_visible(True)
        self._canvas.draw_idle()

    def _on_accumulation_click(self, event):
        if event.inaxes is not self._ax or event.xdata is None:
            return
        idx = int(round(event.xdata))
        if not (0 <= idx < len(self._labels)):
            return
        label = self._labels[idx]
        new_filter = copy.deepcopy(self.filter)
        new_filter.setStartDate(label + "-01-01")
        new_filter.setEndDate(label + "-12-31")
        self._spawn_species_list(new_filter)

    def _update_photo_accumulation_hover(self, event):
        if self._hover_annot is None:
            return
        if event.inaxes is not self._ax or event.xdata is None:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                if self._accumulation_highlight is not None:
                    self._accumulation_highlight.set_visible(False)
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        idx = int(round(event.xdata))
        if not (0 <= idx < len(self._labels)):
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                if self._accumulation_highlight is not None:
                    self._accumulation_highlight.set_visible(False)
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)
        if idx == self._hover_idx:
            return

        self._hover_idx = idx
        new   = self._new_counts[idx]
        rep   = self._repeat_counts[idx]
        total = new + rep
        sp_entries = self._new_species[idx] if idx < len(self._new_species) else []

        limit = self._tooltip_species_limit(anchor_data_xy=(idx, total))
        tip = f"{self._labels[idx]}\nTotal: {total}  New: +{new}"
        for name, date, _loc in sp_entries[:limit]:
            tip += f"\n  {name}  {date}"
        if new > limit:
            tip += f"\n  (+{new - limit} more)"
        n_lines = 2 + min(new, limit) + (1 if new > limit else 0)

        self._hover_annot.xy = (idx, total)
        self._hover_annot.set_text(tip)
        self._position_tooltip(event, n_lines, (idx, total))
        self._hover_annot.set_visible(True)
        if self._accumulation_highlight is not None:
            self._accumulation_highlight.set_xy((idx - 0.3, 0))
            self._accumulation_highlight.set_height(total)
            self._accumulation_highlight.set_visible(True)
        self._canvas.draw_idle()

    def _on_photo_accumulation_click(self, event):
        if event.inaxes is not self._ax or event.xdata is None:
            return
        idx = int(round(event.xdata))
        if not (0 <= idx < len(self._labels)):
            return
        year = self._labels[idx]
        new_filter = copy.deepcopy(self.filter)
        new_filter.setStartDate(year + "-01-01")
        new_filter.setEndDate(year + "-12-31")
        self._spawn_photos_window(new_filter)

    def _on_heatmap_click(self, event):
        if event.inaxes is not self._ax or event.xdata is None or event.ydata is None:
            return
        col = int(round(event.xdata))
        row = int(round(event.ydata))
        if not (0 <= col < 12 and 0 <= row < len(self._heatmap_years)):
            return
        if int(self._heatmap_grid[row, col]) == 0:
            return
        year     = self._heatmap_years[row]
        month    = col + 1
        last_day = calendar.monthrange(year, month)[1]
        new_filter = copy.deepcopy(self.filter)
        new_filter.setStartDate(f"{year}-{month:02d}-01")
        new_filter.setEndDate(f"{year}-{month:02d}-{last_day:02d}")
        self._spawn_species_list(new_filter)

    def _on_line_click(self, event):
        if event.inaxes is not self._ax or event.xdata is None:
            return
        idx = int(round(event.xdata))
        if not (0 <= idx < len(self._labels)):
            return
        new_filter = copy.deepcopy(self.filter)
        new_filter.setStartDate(self._labels[0])
        new_filter.setEndDate(self._labels[idx])
        if self._chart_type == "cumulativelocations":
            self._spawn_locations_list(new_filter)
        elif self._chart_type == "cumulativephotos":
            sp_list = (self._cumulative_new_species[idx]
                       if idx < len(self._cumulative_new_species) else [])
            if not sp_list:
                return
            date_str = self._labels[idx]
            gallery_filter = copy.deepcopy(self.filter)
            gallery_filter.setSpeciesList(list(sp_list))
            gallery_filter.setStartDate(date_str)
            gallery_filter.setEndDate(date_str)
            self._spawn_species_gallery(gallery_filter)
        else:  # cumulative, cumulativefamilies
            self._spawn_species_list(new_filter)

    def _spawn_species_list(self, filter):
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        sub = code_Lists.Lists()
        sub.mdiParent = self.mdiParent
        if sub.FillSpecies(filter) is True:
            self.mdiParent.mdiArea.addSubWindow(sub)
            self.mdiParent.PositionChildWindow(sub, self.mdiParent)
            sub.show()
            sub.scaleMe()
        else:
            self.mdiParent.CreateMessageNoResults()
            sub.close()
        QApplication.restoreOverrideCursor()

    def _spawn_locations_list(self, filter):
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        sub = code_Lists.Lists()
        sub.mdiParent = self.mdiParent
        if sub.FillLocations(filter) is True:
            self.mdiParent.mdiArea.addSubWindow(sub)
            self.mdiParent.PositionChildWindow(sub, self.mdiParent)
            sub.show()
            sub.scaleMe()
        else:
            self.mdiParent.CreateMessageNoResults()
            sub.close()
        QApplication.restoreOverrideCursor()

    def _spawn_species_gallery(self, filter):
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        sub = code_SpeciesGallery.SpeciesGallery()
        sub.mdiParent = self.mdiParent
        self.mdiParent.mdiArea.addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self.mdiParent)
        sub.show()
        if sub.FillGallery(filter) is False:
            self.mdiParent.CreateMessageNoResults()
            sub.close()
        QApplication.restoreOverrideCursor()

    def _spawn_photos_window(self, filter):
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        sub = code_Photos.Photos()
        sub.mdiParent = self.mdiParent
        self.mdiParent.mdiArea.addSubWindow(sub)
        self.mdiParent.PositionChildWindow(sub, self.mdiParent)
        sub.show()
        if sub.FillPhotos(filter) is False:
            self.mdiParent.CreateMessageNoResults()
            sub.close()
        QApplication.restoreOverrideCursor()

    # ------------------------------------------------------------------
    # Family Pie Chart
    # ------------------------------------------------------------------

    def _build_family_pie_data(self, sightings):
        """Return (families, counts, species_lists) sorted descending by count."""
        family_species = defaultdict(set)
        for s in sightings:
            fam = s.get("family", "") or "Unknown"
            family_species[fam].add(s["commonName"])
        ranked = sorted(family_species.items(), key=lambda x: len(x[1]), reverse=True)
        families      = [r[0] for r in ranked]
        counts        = [len(r[1]) for r in ranked]
        species_lists = [self._taxo_sort(r[1], sightings) for r in ranked]
        return families, counts, species_lists

    def _build_order_pie_data(self, sightings):
        """Return (orders, counts, species_lists) sorted descending by count."""
        order_species = defaultdict(set)
        for s in sightings:
            order = s.get("order", "") or "Unknown"
            order_species[order].add(s["commonName"])
        ranked = sorted(order_species.items(), key=lambda x: len(x[1]), reverse=True)
        orders        = [r[0] for r in ranked]
        counts        = [len(r[1]) for r in ranked]
        species_lists = [self._taxo_sort(r[1], sightings) for r in ranked]
        return orders, counts, species_lists

    @staticmethod
    def _parse_indiv_count(raw):
        """Convert a sighting count value to an integer ('X' treated as 1)."""
        if str(raw).strip().upper() == "X":
            return 1
        try:
            return max(0, int(raw))
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _taxo_sort(species_iterable, sightings):
        """Return a list of species sorted by taxonomic order.

        Order is determined by first occurrence in sightings, which mirrors
        the eBird CSV export order (= Clements taxonomic sequence).
        """
        index = {}
        for i, s in enumerate(sightings):
            name = s["commonName"]
            if name not in index:
                index[name] = i
        return sorted(species_iterable, key=lambda sp: index.get(sp, 999999))

    # Shared tooltip-sizing constants.
    # _TIP_LINE_PX: conservative per-line height in display pixels (covers
    #   fontsize-8 text at 100 dpi with line spacing; generous for Retina).
    # _TIP_PAD_PX:  total vertical bbox padding (top + bottom).
    # _TIP_MAX_FRAC: tooltip may occupy at most this fraction of figure/axes.
    # _TIP_GAP_PX:  gap in pixels between the cursor edge and the tooltip edge.
    # _TIP_FALLBACK_W: tooltip width estimate (px) used when renderer unavailable.
    _TIP_LINE_PX     = 22
    _TIP_PAD_PX      = 30
    _TIP_MAX_FRAC    = 0.80
    _TIP_GAP_PX      = 12
    _TIP_FALLBACK_W  = 280

    def _tooltip_species_limit(self, available_px=None, anchor_data_xy=None):
        """Return max species to show in a tooltip, scaled to available height.

        available_px    if supplied, use this as the height budget directly.
        anchor_data_xy  (x_data, y_data) of the hovered dot.  When provided,
                        the budget is the distance from the dot to the axes edge
                        in the direction the tooltip extends (below for top-half
                        dots, above for bottom-half), rather than the full axes
                        height.  This prevents the tooltip from overflowing.
                        Uses data-space fractions to avoid HiDPI pixel-scale issues.
        """
        if available_px is None:
            if anchor_data_xy is not None and self._ax is not None:
                ylim  = self._ax.get_ylim()
                anchor_y_data = float(anchor_data_xy[1])
                ax_h  = self._ax.get_window_extent().height or 400
                y_lo, y_hi = min(ylim), max(ylim)
                y_span = y_hi - y_lo
                y_inverted = ylim[0] > ylim[1]
                # Visual top half: large y for normal axis, small y for inverted axis.
                visual_top = (anchor_y_data >= (ylim[0] + ylim[1]) / 2) != y_inverted
                if y_span == 0:
                    frac = 0.5
                elif visual_top:
                    # Tooltip extends toward visual bottom — measure space below the bar.
                    y_visual_bottom = y_hi if y_inverted else y_lo
                    frac = abs(anchor_y_data - y_visual_bottom) / y_span
                else:
                    # Tooltip extends toward visual top — measure space above the bar.
                    y_visual_top = y_lo if y_inverted else y_hi
                    frac = abs(anchor_y_data - y_visual_top) / y_span
                available_px = frac * ax_h
            elif self._ax is not None:
                available_px = (self._ax.get_window_extent().height or 400) * self._TIP_MAX_FRAC
            elif self._fig is not None:
                available_px = (self._fig.get_window_extent().height or 400) * self._TIP_MAX_FRAC
            else:
                return 25
        usable_px = available_px - self._TIP_PAD_PX
        # Subtract 2: one for the header line, one for the potential "more" line
        return max(5, int(usable_px / self._TIP_LINE_PX) - 2)

    def _position_tooltip(self, event, n_lines, anchor_data_xy=None):
        """Set self._hover_annot position so it appears beside the cursor.

        Must be called *after* set_text() so the rendered dimensions are correct.

        anchor_data_xy  (x_data, y_data) for offset-point charts (bar,
                        cumulative, scatter, heatmap, FOY/LOY, strip).
                        Pass None for pie charts (figure-fraction mode).
        n_lines         estimated text-line count (used only for pie fallback).
        """
        # Actual rendered tooltip dimensions — measured from the live renderer.
        # This avoids any DPI / font-scaling mismatch between the limit
        # calculation and the height estimate.
        try:
            renderer  = self._canvas.get_renderer()
            ann_box   = self._hover_annot.get_window_extent(renderer)
            tip_w_px  = ann_box.width
            tip_h_px  = ann_box.height
        except Exception:
            tip_w_px  = self._TIP_FALLBACK_W
            tip_h_px  = (n_lines * self._TIP_LINE_PX + self._TIP_PAD_PX)

        # Guard: if the renderer returned an empty bbox (annotation not yet drawn),
        # fall back to the estimate so positioning is still meaningful.
        if tip_w_px < 1 or tip_h_px < 1:
            tip_w_px = self._TIP_FALLBACK_W
            tip_h_px = (n_lines * self._TIP_LINE_PX + self._TIP_PAD_PX)

        if anchor_data_xy is None:
            # ── PIE CHART: figure-fraction coords ───────────────────────
            fig_bbox   = self._fig.get_window_extent()
            fig_w      = fig_bbox.width  or 600
            fig_h      = fig_bbox.height or 400
            tip_h_frac = min(tip_h_px / fig_h, self._TIP_MAX_FRAC)
            tip_w_frac = min(tip_w_px / fig_w, 0.70)
            gap_frac   = self._TIP_GAP_PX / fig_w
            MARGIN     = 0.02

            fx = (event.x - fig_bbox.x0) / fig_w
            fy = (event.y - fig_bbox.y0) / fig_h

            right_of_center = event.x > fig_bbox.x0 + fig_bbox.width / 2
            if right_of_center:
                tx = fx - tip_w_frac - gap_frac
            else:
                tx = fx + gap_frac
            tx = max(0.0, min(tx, 1.0 - tip_w_frac))

            ty = fy + MARGIN
            ty = min(ty, 1.0 - MARGIN - tip_h_frac)
            ty = max(MARGIN, ty)

            self._hover_annot.set_position((tx, ty))

        else:
            # ── OFFSET-POINT charts ──────────────────────────────────────
            # Set ha/va to pin the correct corner of the tooltip to the dot,
            # based on which quadrant of the axes the dot sits in.
            #
            #   left  half → ha='left',  x_off = +gap  (tooltip extends right)
            #   right half → ha='right', x_off = -gap  (tooltip extends left)
            #   top    half → va='top',    y_off = 0    (top edge at dot, extends down)
            #   bottom half → va='bottom', y_off = 0    (bottom edge at dot, extends up)
            # Use data-space comparisons to determine quadrant — avoids any
            # HiDPI mismatch between transData (logical px) and get_window_extent
            # (may be physical px on Retina displays).
            xlim = self._ax.get_xlim()
            ylim = self._ax.get_ylim()
            ax, ay = float(anchor_data_xy[0]), float(anchor_data_xy[1])
            # XOR with axis-inverted flag so quadrant detection works for both
            # normal axes and inverted axes (e.g. YTD chart uses invert_yaxis()).
            left_half = (ax < (xlim[0] + xlim[1]) / 2) != (xlim[0] > xlim[1])
            top_half  = (ay >= (ylim[0] + ylim[1]) / 2) != (ylim[0] > ylim[1])

            gap_pts = self._TIP_GAP_PX * (72 / self._fig.dpi)

            if left_half:
                self._hover_annot.set_ha('left')
                x_off = gap_pts
            else:
                self._hover_annot.set_ha('right')
                x_off = -gap_pts

            if top_half:
                self._hover_annot.set_va('top')
            else:
                self._hover_annot.set_va('bottom')

            self._hover_annot.set_position((x_off, 0.0))

    def _build_location_checklist_pie_data(self, sightings):
        """Return (locations, counts, date_lists) sorted descending by checklist count.

        date_lists[i] is a sorted list of distinct checklist dates for locations[i].
        """
        loc_checklists = defaultdict(set)   # location → set of checklistIDs
        cl_dates       = {}                 # checklistID → date
        for s in sightings:
            loc_checklists[s["location"]].add(s["checklistID"])
            cl_dates[s["checklistID"]] = s["date"]
        ranked     = sorted(loc_checklists.items(), key=lambda x: len(x[1]), reverse=True)
        locations  = [r[0] for r in ranked]
        counts     = [len(r[1]) for r in ranked]
        date_lists = [sorted(set(cl_dates[cid] for cid in r[1])) for r in ranked]
        return locations, counts, date_lists

    def _build_family_indiv_pie_data(self, sightings):
        """Return (families, individual_totals, species_lists, species_tallies)
        by summed individual count."""
        family_total   = defaultdict(int)
        family_sp_cnt  = defaultdict(lambda: defaultdict(int))
        for s in sightings:
            fam = s.get("family", "") or "Unknown"
            cnt = self._parse_indiv_count(s.get("count", 0))
            family_total[fam]  += cnt
            family_sp_cnt[fam][s["commonName"]] += cnt
        # Drop groups with zero observed individuals
        ranked = sorted(
            ((fam, tot) for fam, tot in family_total.items() if tot > 0),
            key=lambda x: x[1], reverse=True)
        if not ranked:
            return [], [], [], []
        families = [r[0] for r in ranked]
        counts   = [r[1] for r in ranked]
        # Species sorted by individual count descending
        species_lists = [
            sorted(family_sp_cnt[fam], key=lambda sp: -family_sp_cnt[fam][sp])
            for fam in families
        ]
        species_tallies = [
            [family_sp_cnt[fam][sp] for sp in sp_list]
            for fam, sp_list in zip(families, species_lists)
        ]
        return families, counts, species_lists, species_tallies

    def _build_family_photo_pie_data(self, sightings):
        """Return (families, photo_totals, species_lists, species_tallies)
        by summed photo count, sorted descending."""
        family_total  = defaultdict(int)
        family_sp_cnt = defaultdict(lambda: defaultdict(int))
        for s in sightings:
            photos = s.get("photos", [])
            if not photos:
                continue
            fam = s.get("family", "") or "Unknown"
            n   = len(photos)
            family_total[fam]               += n
            family_sp_cnt[fam][s["commonName"]] += n
        ranked = sorted(
            ((fam, tot) for fam, tot in family_total.items() if tot > 0),
            key=lambda x: x[1], reverse=True)
        if not ranked:
            return [], [], [], []
        families = [r[0] for r in ranked]
        counts   = [r[1] for r in ranked]
        species_lists = [
            sorted(family_sp_cnt[fam], key=lambda sp: -family_sp_cnt[fam][sp])
            for fam in families
        ]
        species_tallies = [
            [family_sp_cnt[fam][sp] for sp in sp_list]
            for fam, sp_list in zip(families, species_lists)
        ]
        return families, counts, species_lists, species_tallies

    def _build_order_photo_pie_data(self, sightings):
        """Return (orders, photo_totals, species_lists, species_tallies)
        by summed photo count, sorted descending."""
        order_total  = defaultdict(int)
        order_sp_cnt = defaultdict(lambda: defaultdict(int))
        for s in sightings:
            photos = s.get("photos", [])
            if not photos:
                continue
            order = s.get("order", "") or "Unknown"
            n     = len(photos)
            order_total[order]               += n
            order_sp_cnt[order][s["commonName"]] += n
        ranked = sorted(
            ((ord_, tot) for ord_, tot in order_total.items() if tot > 0),
            key=lambda x: x[1], reverse=True)
        if not ranked:
            return [], [], [], []
        orders  = [r[0] for r in ranked]
        counts  = [r[1] for r in ranked]
        species_lists = [
            sorted(order_sp_cnt[ord_], key=lambda sp: -order_sp_cnt[ord_][sp])
            for ord_ in orders
        ]
        species_tallies = [
            [order_sp_cnt[ord_][sp] for sp in sp_list]
            for ord_, sp_list in zip(orders, species_lists)
        ]
        return orders, counts, species_lists, species_tallies

    def _build_order_indiv_pie_data(self, sightings):
        """Return (orders, individual_totals, species_lists, species_tallies)
        by summed individual count."""
        order_total  = defaultdict(int)
        order_sp_cnt = defaultdict(lambda: defaultdict(int))
        for s in sightings:
            order = s.get("order", "") or "Unknown"
            cnt   = self._parse_indiv_count(s.get("count", 0))
            order_total[order]  += cnt
            order_sp_cnt[order][s["commonName"]] += cnt
        ranked = sorted(
            ((ord_, tot) for ord_, tot in order_total.items() if tot > 0),
            key=lambda x: x[1], reverse=True)
        if not ranked:
            return [], [], [], []
        orders  = [r[0] for r in ranked]
        counts  = [r[1] for r in ranked]
        species_lists = [
            sorted(order_sp_cnt[ord_], key=lambda sp: -order_sp_cnt[ord_][sp])
            for ord_ in orders
        ]
        species_tallies = [
            [order_sp_cnt[ord_][sp] for sp in sp_list]
            for ord_, sp_list in zip(orders, species_lists)
        ]
        return orders, counts, species_lists, species_tallies

    def _draw_family_pie_chart(self, families, counts, species_lists,
                               label_suffix="species", species_tallies=None,
                               label_min_pct=0.005):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        self._pie_families        = families
        self._pie_species         = species_lists
        self._pie_species_tallies = species_tallies or []
        self._pie_counts          = list(counts)
        self._pie_label_suffix    = label_suffix
        self._pie_hover_idx       = -1

        fig = Figure(facecolor=_BG_COLOR)
        ax  = fig.add_subplot(111, facecolor=_BG_COLOR)

        # Build a colour cycle — blue/teal for standard charts, amber/gold for photo charts
        n = len(families)
        colors = []
        if self._bar_color == PHOTO_PRIMARY:
            for i in range(n):
                hue = (0.12 + i * 0.10 / max(n, 1)) % 1.0   # sweep golden yellow → yellow-green
                sat = 0.60 + 0.25 * (i % 2)
                val = 0.60 + 0.25 * ((i // 2) % 2)
                colors.append(colorsys.hsv_to_rgb(hue, sat, val))
        else:
            for i in range(n):
                hue = (0.58 + i * 0.37 / max(n, 1)) % 1.0   # sweep around blue/teal range
                sat = 0.55 + 0.3 * (i % 2)
                val = 0.55 + 0.25 * ((i // 2) % 2)
                colors.append(colorsys.hsv_to_rgb(hue, sat, val))

        total = sum(counts) or 1
        display_labels = [f if (c / total) >= label_min_pct else "" for f, c in zip(families, counts)]

        wedges, texts, autotexts = ax.pie(
            counts, labels=display_labels, colors=colors,
            autopct=lambda p: f"{p:.1f}%" if p >= 2 else "",
            pctdistance=0.75,
            wedgeprops=dict(linewidth=0.5, edgecolor=_BG_COLOR),
            textprops=dict(color=_TEXT_COLOR, fontsize=7))

        for at in autotexts:
            at.set_color(_TEXT_COLOR)
            at.set_fontsize(6)

        ax.set_aspect("equal")
        fig.tight_layout()

        canvas = FigureCanvasQTAgg(fig)
        layout = self.chartWidget.layout()
        if layout is None:
            layout = QVBoxLayout(self.chartWidget)
            layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(canvas)

        self._fig    = fig
        self._canvas = canvas
        self._ax     = ax
        self._pie_wedges = wedges

        self._hover_annot = ax.annotate(
            "", xy=(0.5, 0.5), xycoords="figure fraction",
            xytext=(0.5, 0.5), textcoords="figure fraction",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=self._bar_color, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5,
            annotation_clip=False)

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event', self._on_pie_click)

    def _on_pie_click(self, event):
        if event.button != 1 or not self._pie_wedges:
            return
        for i, wedge in enumerate(self._pie_wedges):
            if wedge.contains_point([event.x, event.y]):
                name = self._pie_families[i]
                if self._chart_type == "locationchecklistpie":
                    self._spawn_location_window(name)
                elif self._chart_type == "photopie":
                    new_filter = copy.deepcopy(self.filter)
                    if self.rdoPieFamily.isChecked():
                        new_filter.setFamily(name)
                    else:
                        new_filter.setOrder(name)
                    self._spawn_photos_window(new_filter)
                else:
                    new_filter = copy.deepcopy(self.filter)
                    if self.rdoPieFamily.isChecked():
                        new_filter.setFamily(name)
                    else:
                        new_filter.setOrder(name)
                    self._spawn_species_list(new_filter)
                return

    def _update_family_pie_hover(self, event):
        if self._hover_annot is None or not self._pie_wedges:
            return

        # Find which wedge (if any) the mouse is inside
        hit_idx = -1
        if event.inaxes is self._ax and event.xdata is not None:
            for i, wedge in enumerate(self._pie_wedges):
                if wedge.contains_point([event.x, event.y]):
                    hit_idx = i
                    break

        if hit_idx == -1:
            if self._pie_hover_idx != -1:
                # Restore previous wedge edge
                self._pie_wedges[self._pie_hover_idx].set_linewidth(0.5)
                self._pie_wedges[self._pie_hover_idx].set_edgecolor(_BG_COLOR)
                self._hover_annot.set_visible(False)
                self._pie_hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)

        if hit_idx == self._pie_hover_idx:
            return  # same wedge, no update needed

        # Restore old wedge highlight
        if self._pie_hover_idx != -1:
            self._pie_wedges[self._pie_hover_idx].set_linewidth(0.5)
            self._pie_wedges[self._pie_hover_idx].set_edgecolor(_BG_COLOR)

        # Highlight new wedge
        self._pie_hover_idx = hit_idx
        wedge = self._pie_wedges[hit_idx]
        wedge.set_linewidth(2.5)
        wedge.set_edgecolor(_TEXT_COLOR)

        # Build tooltip
        family  = self._pie_families[hit_idx]
        sp_list = self._pie_species[hit_idx]
        n       = (self._pie_counts[hit_idx]
                   if hit_idx < len(self._pie_counts) else len(sp_list))
        total_counts = sum(self._pie_counts) or 1
        pct = 100.0 * n / total_counts
        tip = f"{family}  ·  {n:,} {self._pie_label_suffix}  ({pct:.1f}%)"
        limit   = self._tooltip_species_limit()
        tallies = (self._pie_species_tallies[hit_idx]
                   if hit_idx < len(self._pie_species_tallies) else [])
        for i, name in enumerate(sp_list[:limit]):
            if tallies and i < len(tallies):
                tip += f"\n  {name}  ({tallies[i]:,})"
            else:
                tip += f"\n  {name}"
        if len(sp_list) > limit:
            tip += f"\n  (+{len(sp_list) - limit} more)"

        n_sp    = len(sp_list)
        n_lines = 1 + min(n_sp, limit) + (1 if n_sp > limit else 0)

        self._hover_annot.set_text(tip)
        self._position_tooltip(event, n_lines)   # pie: no anchor_data_xy
        self._hover_annot.set_visible(True)
        self._canvas.draw_idle()

    def _redraw_pie(self):
        """Rebuild species pie when the Family/Order radio changes."""
        sightings = self._filtered_sightings()
        if not sightings:
            return
        if self.rdoPieFamily.isChecked():
            labels, counts, species_lists = self._build_family_pie_data(sightings)
            title_kind = "Families"
        else:
            labels, counts, species_lists = self._build_order_pie_data(sightings)
            title_kind = "Orders"
        self._draw_family_pie_chart(labels, counts, species_lists,
                                    label_suffix="species")
        self.setWindowTitle(
            self.filter.buildWindowTitle(
                f"Pie Chart by Species – {title_kind}", self.mdiParent.db))

    def _redraw_photo_pie(self):
        """Rebuild photo-count pie when the Family/Order radio changes."""
        sightings = self._filtered_sightings()
        if not sightings:
            return
        if self.rdoPieFamily.isChecked():
            labels, counts, species_lists, species_tallies = self._build_family_photo_pie_data(sightings)
            title_kind = "Families"
        else:
            labels, counts, species_lists, species_tallies = self._build_order_photo_pie_data(sightings)
            title_kind = "Orders"
        self._draw_family_pie_chart(labels, counts, species_lists,
                                    label_suffix="photos",
                                    species_tallies=species_tallies)
        self.setWindowTitle(
            self.filter.buildWindowTitle(
                f"Families & Orders by Photos – {title_kind}", self.mdiParent.db))

    def _redraw_indiv_pie(self):
        """Rebuild individual-tally pie when the Family/Order radio changes."""
        sightings = self._filtered_sightings()
        if not sightings:
            return
        if self.rdoPieFamily.isChecked():
            labels, counts, species_lists, species_tallies = self._build_family_indiv_pie_data(sightings)
            title_kind = "Families"
        else:
            labels, counts, species_lists, species_tallies = self._build_order_indiv_pie_data(sightings)
            title_kind = "Orders"
        self._draw_family_pie_chart(labels, counts, species_lists,
                                    label_suffix="individuals",
                                    species_tallies=species_tallies)
        self.setWindowTitle(
            self.filter.buildWindowTitle(
                f"Pie Chart by Individual Tallies – {title_kind}", self.mdiParent.db))

    # ------------------------------------------------------------------
    # Public fill entry point (called by MainWindow)
    # ------------------------------------------------------------------

    def FillGraph(self, filter, chartType="bar"):
        self.filter = filter
        self._chart_type = chartType
        self._setup_colors()

        sightings = self._filtered_sightings()
        if not sightings:
            return False

        # ------------------------------------------------------------------
        # Cumulative species curve — no granularity controls needed
        # ------------------------------------------------------------------
        if chartType == "cumulative":
            self.frmGranularity.setVisible(False)
            labels, counts, new_species, y_label = self._build_cumulative_data(sightings)
            if not labels:
                return False
            self._draw_line_chart(labels, counts, new_species, y_label)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Species Growth Over Time", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "cumulativephotos":
            self.frmGranularity.setVisible(False)
            labels, counts, new_species, y_label, best_photo = self._build_cumulative_photos_data(sightings)
            if not labels:
                return False
            self._draw_line_chart(labels, counts, new_species, y_label)
            self._date_species_best = best_photo   # {date: {sp: path}}
            self._photo_thumb_cache = {}           # path -> b64 string, built on demand
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Photographed Species Growth Over Time", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "cumulativelocations":
            self.frmGranularity.setVisible(False)
            labels, counts, new_locations, y_label = self._build_cumulative_locations_data(sightings)
            if not labels:
                return False
            self._draw_line_chart(labels, counts, new_locations, y_label,
                                  new_items=new_locations)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Locations Growth Over Time", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "cumulativefamilies":
            self.frmGranularity.setVisible(False)
            labels, counts, new_families, y_label = self._build_cumulative_families_data(sightings)
            if not labels:
                return False
            self._draw_line_chart(labels, counts, new_families, y_label,
                                  new_items=new_families)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Families Growth Over Time", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "locations":
            self.frmGranularity.setVisible(False)
            locations, counts, life_counts, species_lists = self._build_top_locations_data(sightings)
            if not locations:
                return False
            self._draw_horizontal_bar_chart(locations, counts, life_counts, species_lists)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle(f"Top {len(locations)} Locations", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "ytdreport":
            self.frmGranularity.setVisible(False)
            years, ytd_counts, full_counts, ytd_recent_items, today = self._build_ytd_data(sightings)
            if not years:
                return False
            self._draw_ytd_chart(years, ytd_counts, full_counts, ytd_recent_items,
                                 "species", today)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Year to Date by Species", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "ytdlocations":
            self.frmGranularity.setVisible(False)
            years, ytd_counts, full_counts, ytd_recent_items, today = self._build_ytd_locations_data(sightings)
            if not years:
                return False
            self._draw_ytd_chart(years, ytd_counts, full_counts, ytd_recent_items,
                                 "locations", today)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Year to Date by Locations", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "ytdchecklists":
            self.frmGranularity.setVisible(False)
            years, ytd_counts, full_counts, ytd_recent_items, today = self._build_ytd_checklists_data(sightings)
            if not years:
                return False
            self._draw_ytd_chart(years, ytd_counts, full_counts, ytd_recent_items,
                                 "checklists", today)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Year to Date by Checklists", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "ytdphotos":
            self.frmGranularity.setVisible(False)
            years, ytd_counts, full_counts, ytd_recent_items, today = self._build_ytd_photos_data(sightings)
            if not years:
                return False
            self._draw_ytd_chart(years, ytd_counts, full_counts, ytd_recent_items,
                                 "photos", today)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Year to Date by Photographs", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "accumulation":
            self.frmGranularity.setVisible(False)
            labels, new_counts, repeat_counts, new_species = self._build_accumulation_data(sightings)
            if not labels:
                return False
            self._draw_stacked_bar_chart(labels, new_counts, repeat_counts, new_species)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("New Species Each Year", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "photoaccumulation":
            self.frmGranularity.setVisible(False)
            labels, new_counts, repeat_counts, new_species = self._build_photo_accumulation_data(sightings)
            if not labels:
                return False
            self._draw_stacked_bar_chart(labels, new_counts, repeat_counts, new_species,
                                         click_handler=self._on_photo_accumulation_click)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("New Species Photographed Each Year", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "heatmap":
            self.frmGranularity.setVisible(False)
            grid, years, species_grid = self._build_heatmap_data(sightings)
            if not len(years):
                return False
            self._draw_heatmap(grid, years, species_grid)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Monthly Activity", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "loy":
            self.frmGranularity.setVisible(False)
            doys, years, dates, loc_lists, species, colors = self._build_loy_data(sightings)
            if not doys:
                return False
            self._draw_loy_chart(doys, years, dates, loc_lists, species, colors)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Last of Year Seasonal Occurrence", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "foy":
            self.frmGranularity.setVisible(False)
            doys, years, dates, loc_lists, species, colors = self._build_foy_data(sightings)
            if not doys:
                return False
            self._draw_foy_chart(doys, years, dates, loc_lists, species, colors)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("First of Year Seasonal Occurrence", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "strip":
            self.frmGranularity.setVisible(False)
            doys, years, dates, loc_lists, species_lists, colors = self._build_strip_data(sightings)
            if not doys:
                return False
            self._draw_strip_chart(doys, years, dates, loc_lists, species_lists, colors)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Seasonal Occurrence", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "locationscatter":
            self.frmGranularity.setVisible(False)
            x, y, names, species_lists = self._build_location_scatter_data(sightings)
            if not names:
                return False
            self._draw_named_scatter(x, y, names,
                                     x_label="Checklists", y_label="Species",
                                     species_lists=species_lists)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Location Productivity", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "speciesscatter":
            self.frmGranularity.setVisible(False)
            x, y, names = self._build_species_scatter_data(sightings)
            if not names:
                return False
            self._draw_named_scatter(x, y, names,
                                     x_label="Locations", y_label="Individuals")
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Species Breadth", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "scatter":
            self.frmGranularity.setVisible(False)
            checklists = self.mdiParent.db.GetChecklists(filter)
            if not checklists:
                return False
            x, y, colors, ids, locs, dates, durs, species_lists, incidental_count = \
                self._build_scatter_data(checklists, sightings)
            if not x:
                return False
            self._draw_scatter_chart(x, y, colors, ids, locs, dates, durs,
                                     species_lists, incidental_count)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Outing Effort", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "locationchecklistpie":
            self.frmGranularity.setVisible(False)
            locations, counts, date_lists = self._build_location_checklist_pie_data(sightings)
            if not locations:
                return False
            self._draw_family_pie_chart(locations, counts, date_lists,
                                        label_suffix="checklists",
                                        label_min_pct=0.01)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Locations by Checklists", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "familypie":
            self.frmGranularity.setVisible(False)
            families, counts, species_lists = self._build_family_pie_data(sightings)
            if not families:
                return False
            # Show the Family/Order toggle row and default to Families
            self.frmPieMode.setVisible(True)
            self.rdoPieFamily.setChecked(True)
            # Connect radio buttons (guard against duplicate connections)
            self.rdoPieFamily.toggled.connect(
                lambda checked: self._redraw_pie() if checked else None)
            self.rdoPieOrder.toggled.connect(
                lambda checked: self._redraw_pie() if checked else None)
            self._draw_family_pie_chart(families, counts, species_lists,
                                        label_suffix="species")
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Pie Chart by Species – Families",
                                        self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "indivpie":
            self.frmGranularity.setVisible(False)
            families, counts, species_lists, species_tallies = self._build_family_indiv_pie_data(sightings)
            if not families:
                return False
            self.frmPieMode.setVisible(True)
            self.rdoPieFamily.setChecked(True)
            self.rdoPieFamily.toggled.connect(
                lambda checked: self._redraw_indiv_pie() if checked else None)
            self.rdoPieOrder.toggled.connect(
                lambda checked: self._redraw_indiv_pie() if checked else None)
            self._draw_family_pie_chart(families, counts, species_lists,
                                        label_suffix="individuals",
                                        species_tallies=species_tallies)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Pie Chart by Individual Tallies – Families",
                                        self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "photopie":
            self.frmGranularity.setVisible(False)
            families, counts, species_lists, species_tallies = self._build_family_photo_pie_data(sightings)
            if not families:
                return False
            self.frmPieMode.setVisible(True)
            self.rdoPieFamily.setChecked(True)
            self.rdoPieFamily.toggled.connect(
                lambda checked: self._redraw_photo_pie() if checked else None)
            self.rdoPieOrder.toggled.connect(
                lambda checked: self._redraw_photo_pie() if checked else None)
            self._draw_family_pie_chart(families, counts, species_lists,
                                        label_suffix="photos",
                                        species_tallies=species_tallies)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Families & Orders by Photos – Families",
                                        self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        # ------------------------------------------------------------------
        # Bar graph
        # ------------------------------------------------------------------

        # Work out the data dimensions to choose smart default and day-limit state
        years_set  = set(s["date"][0:4] for s in sightings)
        months_set = set(s["date"][5:7] for s in sightings)
        days_set   = set(s["date"]      for s in sightings)

        self._update_month_year_button_style()

        self._day_count     = len(days_set)
        self._too_many_days = self._day_count > _DAY_LIMIT
        self._update_day_button_style()

        # Choose the most informative default granularity:
        #   - multiple years  → Year view
        #   - one year only   → Month view
        #   - one month only  → Day view (always ≤ 31 days, so never blocked)
        if len(years_set) == 1:
            if len(months_set) == 1:
                default = "day"
            else:
                default = "month"
        else:
            default = "year"

        # Apply default without triggering redraws (signals blocked)
        self._current_granularity = default
        for btn in (self.rdoYear, self.rdoMonth, self.rdoMonthYear, self.rdoDay):
            btn.blockSignals(True)
        self.rdoYear.setChecked(default == "year")
        self.rdoMonth.setChecked(default == "month")
        self.rdoMonthYear.setChecked(default == "monthyear")
        self.rdoDay.setChecked(default == "day")
        for btn in (self.rdoYear, self.rdoMonth, self.rdoMonthYear, self.rdoDay):
            btn.blockSignals(False)

        # Draw initial chart
        if chartType == "totalchecklists":
            labels, counts, item_lists, y_label = self._build_checklist_count_data(sightings, default)
            item_label = "checklists"
            title = "Total Checklists"
        elif chartType == "totallocations":
            labels, counts, item_lists, y_label = self._build_location_count_data(sightings, default)
            item_label = "locations"
            title = "Total Locations"
        elif chartType == "totalphotos":
            labels, counts, item_lists, sp_tallies, y_label = self._build_photo_count_data(sightings, default)
            self._bar_species_tallies = sp_tallies
            item_label = "photos"
            title = "Total Photos"
        else:  # "bar"
            if default == "month":
                labels, counts, item_lists, y_label = self._build_month_data(sightings)
            elif default == "day":
                labels, counts, item_lists, y_label = self._build_day_data(sightings)
            else:
                labels, counts, item_lists, y_label = self._build_year_data(sightings)
            item_label = "species"
            title = "Total Species"

        if not labels:
            return False

        self._draw_chart(labels, counts, item_lists, y_label, item_label)

        self.mdiParent.SetChildDetailsLabels(self, filter)

        self.setWindowTitle(
            filter.buildWindowTitle(title, self.mdiParent.db))

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                       QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        return True
