import copy
import calendar
import colorsys
import datetime

import numpy as np

import form_Graphs
import code_Lists

from collections import defaultdict
from math import floor
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch, Rectangle

from PySide6.QtGui import QCursor, QFont, QIcon, QPixmap
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QMdiSubWindow, QVBoxLayout, QMessageBox

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

# App colour palette (matches code_Stylesheet.py)
_BAR_COLOR    = "#4f8ef7"
_REPEAT_COLOR = "#3a5c8a"   # muted blue for "seen before" stacked segment
_BG_COLOR     = "#1e1f26"
_AXES_COLOR   = "#252730"
_TEXT_COLOR   = "#e2e4ec"
_GRID_COLOR   = "#2e3040"
_GREY_COLOR   = "#5a5e73"   # disabled-looking text

_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_DAY_LIMIT   = 100
_TOP_N_LOCS  = 20

_SEASON_COLORS = {
    "Winter": "#7ab8d4",   # Dec 20–Mar 19  steel blue
    "Spring": "#5cd68a",   # Mar 20–Jun 19  green
    "Summer": "#f5c842",   # Jun 20–Sep 19  golden
    "Fall":   "#e8783a",   # Sep 20–Dec 19  orange
}


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
        self._cumulative_highlight   = None
        self._new_counts    = []
        self._repeat_counts = []
        self._new_species   = []
        self._accumulation_highlight = None
        self._life_counts   = []
        self._scatter_x    = np.array([])
        self._scatter_y    = np.array([])
        self._scatter_ids  = []
        self._scatter_locs = []
        self._scatter_dates = []
        self._scatter_durs = []
        self._scatter_species = []
        self._scatter_highlight = None
        self._strip_doys   = np.array([])
        self._strip_years  = np.array([])
        self._strip_dates  = []
        self._strip_locs   = []
        self._strip_highlight = None
        self._foy_doys      = np.array([])
        self._foy_years     = np.array([])
        self._foy_dates     = []
        self._foy_species   = []
        self._foy_highlight = None
        self._loy_doys      = np.array([])
        self._loy_years     = np.array([])
        self._loy_dates     = []
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
        self._bar_species   = []
        self._bar_highlight = None
        self._heatmap_years = []
        self._heatmap_grid         = None
        self._heatmap_species_grid = None
        self._heatmap_highlight    = None
        self._too_many_days = False
        self._day_count = 0
        self._too_many_month_years = False
        self._month_year_count = 0
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
        if self.rdoMonthYear.isChecked() and self._too_many_month_years:
            for btn in (self.rdoYear, self.rdoMonth, self.rdoMonthYear, self.rdoDay):
                btn.blockSignals(True)
            if self._current_granularity == "month":
                self.rdoMonth.setChecked(True)
            else:
                self.rdoYear.setChecked(True)
            for btn in (self.rdoYear, self.rdoMonth, self.rdoMonthYear, self.rdoDay):
                btn.blockSignals(False)
            QMessageBox.information(
                self,
                "Too Many Month-Years",
                f"The current filter returned {self._month_year_count} month-year "
                f"combinations, which is more than the {_DAY_LIMIT}-bar limit for "
                "By Month-Year view.\n\n"
                "Narrow your date filter and try again.")
            return

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
                f"which is more than the {_DAY_LIMIT}-day limit for By Day view.\n\n"
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

        labels, counts, species_lists, y_label = self._get_current_data()
        self._draw_chart(labels, counts, species_lists, y_label)

    # ------------------------------------------------------------------
    # Day-button visual state
    # ------------------------------------------------------------------

    def _update_month_year_button_style(self):
        if self._too_many_month_years:
            self.rdoMonthYear.setStyleSheet(
                f"QRadioButton {{ color: {_GREY_COLOR}; }}")
        else:
            self.rdoMonthYear.setStyleSheet("")

    def _update_day_button_style(self):
        if self._too_many_days:
            self.rdoDay.setStyleSheet(
                f"QRadioButton {{ color: {_GREY_COLOR}; }}")
        else:
            self.rdoDay.setStyleSheet("")

    # ------------------------------------------------------------------
    # Data builders
    # ------------------------------------------------------------------

    def _filtered_sightings(self):
        """Minimal filtered list, excluding slash / spuh / hybrid entries."""
        minimal = self.mdiParent.db.GetMinimalFilteredSightingsList(self.filter)
        result = []
        for s in minimal:
            name = s["commonName"]
            if "/" in name or "sp." in name or " x " in name:
                continue
            if self.mdiParent.db.TestSighting(s, self.filter):
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

    def _build_cumulative_data(self, sightings):
        daily = defaultdict(set)
        for s in sightings:
            daily[s["date"]].add(s["commonName"])
        dates = sorted(daily.keys())
        seen = set()
        counts = []
        new_species = []
        for d in dates:
            new_sp = self._taxo_sort(daily[d] - seen, sightings)
            seen |= daily[d]
            counts.append(len(seen))
            new_species.append(new_sp)
        return dates, counts, new_species, "Cumulative Species"

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

        return locations, counts, life_counts

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

    def _build_strip_data(self, sightings):
        """One dot per unique date the species was seen.

        Returns (doys, years, dates, loc_lists, colors) sorted chronologically.
        loc_lists[i] is a sorted list of locations where the species was seen
        on dates[i].
        """
        date_locs = defaultdict(set)
        for s in sightings:
            date_locs[s["date"]].add(s["location"])

        doys, years, dates_out, loc_lists, colors = [], [], [], [], []

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
            colors.append(_SEASON_COLORS[season])

        return doys, years, dates_out, loc_lists, colors

    def _draw_strip_chart(self, doys, years, dates, loc_lists, colors):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        self._strip_doys  = np.array(doys,  dtype=float)
        self._strip_years = np.array(years, dtype=float)
        self._strip_dates = dates
        self._strip_locs  = loc_lists

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
        legend = ax.legend(handles=legend_handles, loc="upper right",
                           facecolor=_AXES_COLOR, edgecolor=_GRID_COLOR, fontsize=8)
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
        self._hover_idx = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=_BAR_COLOR, lw=1),
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

        Returns (doys, years, dates, species_lists, colors) where
        species_lists[i] is a sorted list of species names sharing that dot.
        """
        # (species, year) → earliest date string
        foy = {}
        for s in sightings:
            key = (s["commonName"], s["date"][0:4])
            if key not in foy or s["date"] < foy[key]:
                foy[key] = s["date"]

        # Aggregate: date → list of species (date string already encodes year)
        date_species = defaultdict(list)
        for (species, _year_str), date in foy.items():
            date_species[date].append(species)

        doys, years, dates_out, species_lists, colors = [], [], [], [], []
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
            species_lists.append(self._taxo_sort(sp_list, sightings))
            colors.append(_SEASON_COLORS[season])

        return doys, years, dates_out, species_lists, colors

    def _draw_foy_chart(self, doys, years, dates, species, colors):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        self._foy_doys    = np.array(doys,  dtype=float)
        self._foy_years   = np.array(years, dtype=float)
        self._foy_dates   = dates
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
        legend = ax.legend(handles=legend_handles, loc="upper right",
                           facecolor=_AXES_COLOR, edgecolor=_GRID_COLOR, fontsize=8)
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
        self._hover_idx = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=_BAR_COLOR, lw=1),
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

        Returns (doys, years, dates, species_lists, colors).
        """
        # (species, year) → latest date string
        loy = {}
        for s in sightings:
            key = (s["commonName"], s["date"][0:4])
            if key not in loy or s["date"] > loy[key]:
                loy[key] = s["date"]

        # Aggregate: date → list of species
        date_species = defaultdict(list)
        for (species, _year_str), date in loy.items():
            date_species[date].append(species)

        doys, years, dates_out, species_lists, colors = [], [], [], [], []
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
            species_lists.append(self._taxo_sort(sp_list, sightings))
            colors.append(_SEASON_COLORS[season])

        return doys, years, dates_out, species_lists, colors

    def _draw_loy_chart(self, doys, years, dates, species, colors):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        self._loy_doys    = np.array(doys,  dtype=float)
        self._loy_years   = np.array(years, dtype=float)
        self._loy_dates   = dates
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
        legend = ax.legend(handles=legend_handles, loc="upper right",
                           facecolor=_AXES_COLOR, edgecolor=_GRID_COLOR, fontsize=8)
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
        self._hover_idx = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=_BAR_COLOR, lw=1),
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
        legend = ax.legend(handles=legend_handles, loc="upper left",
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
                      ec=_BAR_COLOR, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5)

        self._scatter_highlight = ax.scatter(
            [], [], s=55, zorder=4,
            facecolors='none', edgecolors=_TEXT_COLOR, linewidths=1.5)

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event', self._on_scatter_click)

    def _get_current_data(self):
        sightings = self._filtered_sightings()
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

    def _draw_chart(self, labels, counts, species_lists, y_label):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        fig = Figure(facecolor=_BG_COLOR)
        ax  = fig.add_subplot(111, facecolor=_AXES_COLOR)

        x_pos = range(len(labels))
        bars = ax.bar(x_pos, counts, color=_BAR_COLOR, width=0.6, zorder=2)

        many = len(labels) > 10
        ax.bar_label(bars, padding=3, color=_TEXT_COLOR,
                     fontsize=7 if many else 9)

        ax.set_xticks(list(x_pos))
        if many:
            ax.set_xticklabels(labels, rotation=45, ha="right",
                               color=_TEXT_COLOR, fontsize=7)
        else:
            ax.set_xticklabels(labels, color=_TEXT_COLOR, fontsize=9)

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
        self._counts = counts
        self._bar_species = species_lists
        self._hover_idx   = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=_BAR_COLOR, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5)

        bar_rect = Rectangle((0, 0), 0.6, 1,
                              linewidth=1.5, edgecolor=_TEXT_COLOR,
                              facecolor='none', visible=False, zorder=4)
        ax.add_patch(bar_rect)
        self._bar_highlight = bar_rect

        canvas.mpl_connect('button_press_event', self._on_bar_click)
        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)

    def _draw_line_chart(self, labels, counts, new_species, y_label):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        fig = Figure(facecolor=_BG_COLOR)
        ax  = fig.add_subplot(111, facecolor=_AXES_COLOR)

        x_pos = list(range(len(labels)))
        ax.plot(x_pos, counts, color=_BAR_COLOR, linewidth=1.5, zorder=2)
        ax.fill_between(x_pos, counts, alpha=0.15, color=_BAR_COLOR, zorder=1)

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
        self._hover_idx = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=_BAR_COLOR, lw=1),
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
            'yearbird_heat', ['#a0c4ff', _BAR_COLOR, '#1e4a8a', '#1a2a45'])
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
                      ec=_BAR_COLOR, lw=1),
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

    def _draw_stacked_bar_chart(self, labels, new_counts, repeat_counts, new_species):
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
        ax.bar(x_pos, repeat_counts, color=_REPEAT_COLOR, width=0.6,
               label="Seen Before", zorder=2)
        ax.bar(x_pos, new_counts, bottom=repeat_counts, color=_BAR_COLOR,
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
                      ec=_BAR_COLOR, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5)

        # White outline that tracks the hovered bar
        bar_rect = Rectangle((0, 0), 0.6, 1,
                              linewidth=1.5, edgecolor=_TEXT_COLOR,
                              facecolor='none', visible=False, zorder=4)
        ax.add_patch(bar_rect)
        self._accumulation_highlight = bar_rect

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event', self._on_accumulation_click)

    def _draw_horizontal_bar_chart(self, locations, counts, life_counts):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        self._life_counts = life_counts
        non_life_counts   = [t - l for t, l in zip(counts, life_counts)]

        fig = Figure(facecolor=_BG_COLOR)
        ax  = fig.add_subplot(111, facecolor=_AXES_COLOR)

        y_pos = list(range(len(locations)))

        # Non-life-bird segment (left portion)
        ax.barh(y_pos, non_life_counts, color=_REPEAT_COLOR, height=0.6,
                label="Previously seen", zorder=2)

        # Life-bird segment (right portion, bright blue)
        life_bars = ax.barh(y_pos, life_counts, left=non_life_counts,
                            color=_BAR_COLOR, height=0.6,
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
                      ec=_BAR_COLOR, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5)

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event', self._on_location_click)

    # ------------------------------------------------------------------
    # Bar click → spawn species list
    # ------------------------------------------------------------------

    # Max days per month for seasonal filter (use 29 for Feb to cover leap years)
    _MONTH_DAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    def _on_mouse_move(self, event):
        if self._chart_type == "cumulative":
            self._update_hover_annotation(event)
        elif self._chart_type == "heatmap":
            self._update_heatmap_hover(event)
        elif self._chart_type == "accumulation":
            self._update_accumulation_hover(event)
        elif self._chart_type == "locations":
            self._update_location_hover(event)
        elif self._chart_type == "scatter":
            self._update_scatter_hover(event)
        elif self._chart_type == "strip":
            self._update_strip_hover(event)
        elif self._chart_type == "foy":
            self._update_foy_hover(event)
        elif self._chart_type == "loy":
            self._update_loy_hover(event)
        elif self._chart_type in ("familypie", "indivpie"):
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
        limit = self._tooltip_species_limit()

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
        limit   = self._tooltip_species_limit()

        tip = f"{self._labels[idx]}: {count} species"
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

        limit = self._tooltip_species_limit()
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

        self._hover_annot.xy = (count, idx)
        self._hover_annot.set_text(tip)
        self._position_tooltip(event, 2, (count, idx))
        self._hover_annot.set_visible(True)
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

        date = self._strip_dates[idx]
        locs = self._strip_locs[idx]
        loc_text = locs[0] if len(locs) == 1 else f"{locs[0]} + {len(locs)-1} more"
        tip = f"{date}\n{loc_text}"

        self._hover_annot.xy = (px, py)
        self._hover_annot.set_text(tip)
        self._position_tooltip(event, 2, (px, py))
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
        sp_list  = self._foy_species[idx]
        n        = len(sp_list)
        limit    = self._tooltip_species_limit()
        tip      = f"{date}  ·  {n} FOY species"
        for name in sp_list[:limit]:
            tip += f"\n  {name}"
        if n > limit:
            tip += f"\n  (+{n - limit} more)"
        n_lines = 1 + min(n, limit) + (1 if n > limit else 0)

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
        sp_list  = self._loy_species[idx]
        n        = len(sp_list)
        limit    = self._tooltip_species_limit()
        tip      = f"{date}  ·  {n} LOY species"
        for name in sp_list[:limit]:
            tip += f"\n  {name}"
        if n > limit:
            tip += f"\n  (+{n - limit} more)"
        n_lines = 1 + min(n, limit) + (1 if n > limit else 0)

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
        limit   = self._tooltip_species_limit()
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

        limit = self._tooltip_species_limit()
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

    def _tooltip_species_limit(self):
        """Return max species to show in a tooltip, scaled to available height.

        For charts that use offset-point annotations (bar, line, scatter etc.)
        the relevant constraint is the *axes* height, which excludes tick labels,
        axis titles and figure margins.  For the pie chart (figure-fraction
        annotations) the figure height is used as a fallback.
        Shares _TIP_LINE_PX/_TIP_PAD_PX/_TIP_MAX_FRAC with the positioning code
        so the limit and the height estimate are always consistent.
        """
        if self._ax is not None:
            h = self._ax.get_window_extent().height or 400
        elif self._fig is not None:
            h = self._fig.get_window_extent().height or 400
        else:
            return 25
        usable_px = h * self._TIP_MAX_FRAC - self._TIP_PAD_PX
        # Subtract 2: one for the header line, one for the potential "more" line
        return max(5, int(usable_px / self._TIP_LINE_PX) - 2)

    def _position_tooltip(self, event, n_lines, anchor_data_xy=None):
        """Set self._hover_annot position so it appears beside the cursor.

        Must be called *after* set_text() so the rendered width is correct.

        anchor_data_xy  (x_data, y_data) for offset-point charts (bar,
                        cumulative, scatter, heatmap, FOY/LOY, strip).
                        Pass None for pie charts (figure-fraction mode).
        n_lines         estimated text-line count for height calculation.
        """
        # Actual rendered tooltip width — measured from the live renderer so
        # long family/species names are handled correctly.
        try:
            tip_w_px = self._hover_annot.get_window_extent(
                self._canvas.get_renderer()).width
        except Exception:
            tip_w_px = self._TIP_FALLBACK_W

        # Left/right decision: place tooltip on the opposite side of centre.
        fig_bbox        = self._fig.get_window_extent()
        right_of_center = event.x > fig_bbox.x0 + fig_bbox.width / 2

        tip_height_pts = n_lines * 11 + 20

        if anchor_data_xy is None:
            # ── PIE CHART: figure-fraction coords ───────────────────────
            fig_w      = fig_bbox.width  or 600
            fig_h      = fig_bbox.height or 400
            tip_h_frac = min(
                (n_lines * self._TIP_LINE_PX + self._TIP_PAD_PX) / fig_h,
                self._TIP_MAX_FRAC)
            tip_w_frac = min(tip_w_px / fig_w, 0.70)
            gap_frac   = self._TIP_GAP_PX / fig_w
            MARGIN     = 0.02

            fx = (event.x - fig_bbox.x0) / fig_w
            fy = (event.y - fig_bbox.y0) / fig_h

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
            tip_height_px = tip_height_pts * (self._fig.dpi / 72)
            ax_bbox       = self._ax.get_window_extent()

            # Anchor in display pixels; clamp y to axes bounds (guards against
            # bars/points that extend above the y-axis view limit).
            anchor_px   = self._ax.transData.transform(anchor_data_xy)
            anchor_x_px = float(anchor_px[0])
            anchor_y_px = float(np.clip(anchor_px[1], ax_bbox.y0, ax_bbox.y1))

            # x: place tooltip left or right of the cursor, not the anchor.
            gap_px = self._TIP_GAP_PX
            if right_of_center:
                x_off_px = event.x - anchor_x_px - tip_w_px - gap_px
            else:
                x_off_px = event.x - anchor_x_px + gap_px
            x_off = x_off_px * (72 / self._fig.dpi)

            # y: vertically centre the tooltip in the axes.
            ax_center_px = (ax_bbox.y0 + ax_bbox.y1) / 2
            y_off = (ax_center_px - anchor_y_px - tip_height_px / 2) * (72 / self._fig.dpi)

            self._hover_annot.set_position((x_off, y_off))

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
                               label_suffix="species", species_tallies=None):
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

        # Build a colour cycle that steps through the app's blue palette
        n = len(families)
        colors = []
        for i in range(n):
            hue = (0.58 + i * 0.37 / max(n, 1)) % 1.0   # sweep around blue/teal range
            sat = 0.55 + 0.3 * (i % 2)
            val = 0.55 + 0.25 * ((i // 2) % 2)
            colors.append(colorsys.hsv_to_rgb(hue, sat, val))

        total = sum(counts) or 1
        display_labels = [f if (c / total) >= 0.005 else "" for f, c in zip(families, counts)]

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
                      ec=_BAR_COLOR, lw=1),
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
                new_filter = copy.deepcopy(self.filter)
                name = self._pie_families[i]
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
                filter.buildWindowTitle("Cumulative Species Curve", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "locations":
            self.frmGranularity.setVisible(False)
            locations, counts, life_counts = self._build_top_locations_data(sightings)
            if not locations:
                return False
            self._draw_horizontal_bar_chart(locations, counts, life_counts)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle(f"Top {len(locations)} Locations", self.mdiParent.db))
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
                filter.buildWindowTitle("Species Accumulation", self.mdiParent.db))
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
                filter.buildWindowTitle("Species Heatmap", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "loy":
            self.frmGranularity.setVisible(False)
            doys, years, dates, species, colors = self._build_loy_data(sightings)
            if not doys:
                return False
            self._draw_loy_chart(doys, years, dates, species, colors)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Last of Year Phenology", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "foy":
            self.frmGranularity.setVisible(False)
            doys, years, dates, species, colors = self._build_foy_data(sightings)
            if not doys:
                return False
            self._draw_foy_chart(doys, years, dates, species, colors)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("First of Year Phenology", self.mdiParent.db))
            icon = QIcon()
            icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                           QIcon.Normal, QIcon.Off)
            self.setWindowIcon(icon)
            return True

        if chartType == "strip":
            self.frmGranularity.setVisible(False)
            doys, years, dates, loc_lists, colors = self._build_strip_data(sightings)
            if not doys:
                return False
            self._draw_strip_chart(doys, years, dates, loc_lists, colors)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Phenology", self.mdiParent.db))
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
                filter.buildWindowTitle("Checklist Scatter", self.mdiParent.db))
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

        # ------------------------------------------------------------------
        # Bar graph
        # ------------------------------------------------------------------

        # Work out the data dimensions to choose smart default and day-limit state
        years_set  = set(s["date"][0:4] for s in sightings)
        months_set = set(s["date"][5:7] for s in sightings)
        days_set   = set(s["date"]      for s in sightings)

        month_years_set          = set(s["date"][0:7] for s in sightings)
        self._month_year_count   = len(month_years_set)
        self._too_many_month_years = self._month_year_count > _DAY_LIMIT
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
        if default == "month":
            labels, counts, species_lists, y_label = self._build_month_data(sightings)
        elif default == "day":
            labels, counts, species_lists, y_label = self._build_day_data(sightings)
        else:
            labels, counts, species_lists, y_label = self._build_year_data(sightings)

        if not labels:
            return False

        self._draw_chart(labels, counts, species_lists, y_label)

        self.mdiParent.SetChildDetailsLabels(self, filter)

        self.setWindowTitle(
            filter.buildWindowTitle("Bar Graph", self.mdiParent.db))

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                       QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        return True
