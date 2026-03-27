import copy
import calendar
import datetime

import numpy as np

import form_Graphs
import code_Lists

from collections import defaultdict
from math import floor
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

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
    "Winter": "#7ab8d4",   # Dec–Feb  steel blue
    "Spring": "#5cd68a",   # Mar–May  green
    "Summer": "#f5c842",   # Jun–Aug  golden
    "Fall":   "#e8783a",   # Sep–Nov  orange
}


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
        self._new_counts    = []
        self._repeat_counts = []
        self._life_counts   = []
        self._scatter_x    = np.array([])
        self._scatter_y    = np.array([])
        self._scatter_ids  = []
        self._scatter_locs = []
        self._scatter_dates = []
        self._scatter_durs = []
        self._strip_doys   = np.array([])
        self._strip_years  = np.array([])
        self._strip_dates  = []
        self._strip_locs   = []
        self._chart_type = "bar"
        self._hover_annot = None
        self._hover_idx   = -1
        self._heatmap_years = []
        self._heatmap_grid  = None
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

        labels, counts, y_label = self._get_current_data()
        self._draw_chart(labels, counts, y_label)

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
        return labels, counts, "Species per Year"

    def _build_month_data(self, sightings):
        bucket = defaultdict(set)
        for s in sightings:
            bucket[s["date"][5:7]].add(s["commonName"])
        month_nums = sorted(bucket.keys())
        labels = [_MONTH_NAMES[int(m) - 1] for m in month_nums]
        counts = [len(bucket[m]) for m in month_nums]
        return labels, counts, "Species per Month"

    def _build_month_year_data(self, sightings):
        """One bar per YYYY-MM, sorted chronologically, labelled 'Jan-2020' etc."""
        bucket = defaultdict(set)
        for s in sightings:
            bucket[s["date"][0:7]].add(s["commonName"])   # key = "YYYY-MM"
        keys   = sorted(bucket.keys())
        labels = [_MONTH_NAMES[int(k[5:7]) - 1] + "-" + k[0:4] for k in keys]
        counts = [len(bucket[k]) for k in keys]
        return labels, counts, "Species per Month"

    def _build_day_data(self, sightings):
        bucket = defaultdict(set)
        for s in sightings:
            bucket[s["date"]].add(s["commonName"])
        labels = sorted(bucket.keys())
        counts = [len(bucket[k]) for k in labels]
        return labels, counts, "Species per Day"

    def _build_cumulative_data(self, sightings):
        daily = defaultdict(set)
        for s in sightings:
            daily[s["date"]].add(s["commonName"])
        dates = sorted(daily.keys())
        seen = set()
        counts = []
        for d in dates:
            seen |= daily[d]
            counts.append(len(seen))
        return dates, counts, "Cumulative Species"

    def _build_heatmap_data(self, sightings):
        """Return (grid, years) where grid[year_idx][month_idx] = species count."""
        bucket = defaultdict(set)
        for s in sightings:
            key = (int(s["date"][0:4]), int(s["date"][5:7]))
            bucket[key].add(s["commonName"])
        years = sorted(set(k[0] for k in bucket), reverse=True)
        grid  = np.zeros((len(years), 12), dtype=int)
        for i, year in enumerate(years):
            for j in range(12):
                grid[i, j] = len(bucket.get((year, j + 1), set()))
        return grid, years

    def _build_accumulation_data(self, sightings):
        """Return (years, new_counts, repeat_counts) for stacked accumulation chart."""
        by_year = defaultdict(set)
        for s in sightings:
            by_year[s["date"][0:4]].add(s["commonName"])
        years = sorted(by_year.keys())
        seen_before = set()
        new_counts    = []
        repeat_counts = []
        for year in years:
            year_species = by_year[year]
            new_counts.append(len(year_species - seen_before))
            repeat_counts.append(len(year_species & seen_before))
            seen_before |= year_species
        return years, new_counts, repeat_counts

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

        x, y, colors, ids, locs, dates, durs = [], [], [], [], [], [], []
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
            filtered_count = len(checklist_species.get(c[0], set()))
            if filtered_count == 0:
                continue
            month = int(c[4][5:7])
            if month in (12, 1, 2):
                season = "Winter"
            elif month in (3, 4, 5):
                season = "Spring"
            elif month in (6, 7, 8):
                season = "Summer"
            else:
                season = "Fall"
            x.append(dur)
            y.append(filtered_count)
            colors.append(_SEASON_COLORS[season])
            ids.append(c[0])
            locs.append(c[3])
            dates.append(c[4])
            durs.append(dur)
        return x, y, colors, ids, locs, dates, durs, incidental_count

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

            if month in (12, 1, 2):
                season = "Winter"
            elif month in (3, 4, 5):
                season = "Spring"
            elif month in (6, 7, 8):
                season = "Summer"
            else:
                season = "Fall"

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

        ax.scatter(doys, years, c=colors, s=20, alpha=0.75, zorder=2, linewidths=0)

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
            for s, lbl in (("Winter", "Dec–Feb"), ("Spring", "Mar–May"),
                           ("Summer", "Jun–Aug"), ("Fall",   "Sep–Nov"))
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

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event', self._on_strip_click)

    def _draw_scatter_chart(self, x, y, colors, ids, locs, dates, durs,
                            incidental_count):
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

        fig = Figure(facecolor=_BG_COLOR)
        ax  = fig.add_subplot(111, facecolor=_AXES_COLOR)

        ax.scatter(x, y, c=colors, alpha=0.5, s=18, zorder=2, linewidths=0)

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
            for s, lbl in (("Winter", "Dec–Feb"), ("Spring", "Mar–May"),
                           ("Summer", "Jun–Aug"), ("Fall",   "Sep–Nov"))
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

    def _draw_chart(self, labels, counts, y_label):
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

        canvas.mpl_connect('button_press_event', self._on_bar_click)
        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)

    def _draw_line_chart(self, labels, counts, y_label):
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
        self._hover_idx = -1

        self._hover_annot = ax.annotate(
            "", xy=(0, 0),
            xytext=(12, 12), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc=_AXES_COLOR,
                      ec=_BAR_COLOR, lw=1),
            color=_TEXT_COLOR, fontsize=8,
            visible=False, zorder=5)

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event', self._on_line_click)

    def _draw_heatmap(self, grid, years):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        self._heatmap_years = years
        self._heatmap_grid  = grid

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

        # Annotate cells with species count when the grid is small enough to read
        if len(years) <= 15:
            for i in range(len(years)):
                for j in range(12):
                    val = int(grid[i, j])
                    if val > 0:
                        ax.text(j, i, str(val), ha='center', va='center',
                                color=_TEXT_COLOR, fontsize=7)

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

        canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        canvas.mpl_connect('button_press_event', self._on_heatmap_click)

    def _draw_stacked_bar_chart(self, labels, new_counts, repeat_counts):
        if self._canvas is not None:
            self._canvas.setParent(None)
            self._canvas = None
            self._fig = None

        self._new_counts    = new_counts
        self._repeat_counts = repeat_counts

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
        else:
            # Bar chart: pointer cursor over bars
            if (event.inaxes is self._ax and event.xdata is not None
                    and 0 <= int(round(event.xdata)) < len(self._labels)):
                self._canvas.setCursor(Qt.PointingHandCursor)
            else:
                self._canvas.setCursor(Qt.ArrowCursor)

    def _update_hover_annotation(self, event):
        if self._hover_annot is None:
            return
        if event.inaxes is not self._ax or event.xdata is None:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        idx = int(round(event.xdata))
        if not (0 <= idx < len(self._labels)):
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)

        if idx == self._hover_idx:
            return  # already showing this point — no redraw needed

        self._hover_idx = idx
        x, y = idx, self._counts[idx]

        ax_xlim = self._ax.get_xlim()
        ax_ylim = self._ax.get_ylim()
        x_off = -80 if x > (ax_xlim[1] - ax_xlim[0]) * 0.75 + ax_xlim[0] else 12
        y_off = -40 if y > (ax_ylim[1] - ax_ylim[0]) * 0.75 + ax_ylim[0] else 12
        self._hover_annot.set_position((x_off, y_off))

        self._hover_annot.xy = (x, y)
        self._hover_annot.set_text(f"{self._labels[idx]}\n{y} species")
        self._hover_annot.set_visible(True)
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

    def _update_heatmap_hover(self, event):
        if self._hover_annot is None:
            return
        if (event.inaxes is not self._ax or event.xdata is None
                or event.ydata is None):
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        col = int(round(event.xdata))   # month index 0-11
        row = int(round(event.ydata))   # year index
        if not (0 <= col < 12 and 0 <= row < len(self._heatmap_years)):
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
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

        x_off = -90 if col >= 9 else 12
        y_off = -40 if row < len(self._heatmap_years) * 0.25 else 12
        self._hover_annot.set_position((x_off, y_off))

        self._hover_annot.xy = (col, row)
        if species > 0:
            self._hover_annot.set_text(f"{label}\n{species} species")
            self._canvas.setCursor(Qt.PointingHandCursor)
        else:
            self._hover_annot.set_text(f"{label}\nNo data")
            self._canvas.setCursor(Qt.ArrowCursor)
        self._hover_annot.set_visible(True)
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

        ax_xlim = self._ax.get_xlim()
        ax_ylim = self._ax.get_ylim()
        x_off = -130 if count > (ax_xlim[1] - ax_xlim[0]) * 0.75 + ax_xlim[0] else 12
        y_off = -40  if idx  > (ax_ylim[1] - ax_ylim[0]) * 0.75 + ax_ylim[0] else 12
        self._hover_annot.set_position((x_off, y_off))

        life  = self._life_counts[idx] if self._life_counts else 0
        tip   = f"{self._labels[idx]}\n{count} species"
        if life:
            tip += f"  ·  {life} life birds"
        self._hover_annot.xy = (count, idx)
        self._hover_annot.set_text(tip)
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
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)
        if idx == self._hover_idx:
            return

        self._hover_idx = idx
        px = float(self._strip_doys[idx])
        py = float(self._strip_years[idx])

        x_off = -140 if event.xdata > xlim[0] + xrange * 0.75 else 12
        y_off = -40  if event.ydata > ylim[0] + yrange * 0.75 else 12
        self._hover_annot.set_position((x_off, y_off))

        date = self._strip_dates[idx]
        locs = self._strip_locs[idx]
        loc_text = locs[0] if len(locs) == 1 else f"{locs[0]} + {len(locs)-1} more"
        tip = f"{date}\n{loc_text}"
        self._hover_annot.xy = (px, py)
        self._hover_annot.set_text(tip)
        self._hover_annot.set_visible(True)
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

    def _update_scatter_hover(self, event):
        if self._hover_annot is None or len(self._scatter_x) == 0:
            return
        if event.inaxes is not self._ax or event.xdata is None or event.ydata is None:
            if self._hover_annot.get_visible():
                self._hover_annot.set_visible(False)
                self._hover_idx = -1
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
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        self._canvas.setCursor(Qt.PointingHandCursor)
        if idx == self._hover_idx:
            return

        self._hover_idx = idx
        px = self._scatter_x[idx]
        py = self._scatter_y[idx]

        x_off = -130 if event.xdata > xlim[0] + xrange * 0.75 else 12
        y_off = -40  if event.ydata > ylim[0] + yrange * 0.75 else 12
        self._hover_annot.set_position((x_off, y_off))

        loc  = self._scatter_locs[idx]
        date = self._scatter_dates[idx]
        dur  = self._scatter_durs[idx]
        tip  = f"{date}  ·  {int(py)} species\n{int(dur)} min  ·  {loc}"
        self._hover_annot.xy = (px, py)
        self._hover_annot.set_text(tip)
        self._hover_annot.set_visible(True)
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
                self._hover_idx = -1
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.ArrowCursor)
            return

        idx = int(round(event.xdata))
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
        new   = self._new_counts[idx]
        rep   = self._repeat_counts[idx]
        total = new + rep

        ax_xlim = self._ax.get_xlim()
        ax_ylim = self._ax.get_ylim()
        x_off = -110 if idx   > (ax_xlim[1] - ax_xlim[0]) * 0.75 + ax_xlim[0] else 12
        y_off = -40  if total > (ax_ylim[1] - ax_ylim[0]) * 0.75 + ax_ylim[0] else 12
        self._hover_annot.set_position((x_off, y_off))

        self._hover_annot.xy = (idx, total)
        self._hover_annot.set_text(
            f"{self._labels[idx]}\nTotal: {total}  New: +{new}")
        self._hover_annot.set_visible(True)
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
            labels, counts, y_label = self._build_cumulative_data(sightings)
            if not labels:
                return False
            self._draw_line_chart(labels, counts, y_label)
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
            labels, new_counts, repeat_counts = self._build_accumulation_data(sightings)
            if not labels:
                return False
            self._draw_stacked_bar_chart(labels, new_counts, repeat_counts)
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
            grid, years = self._build_heatmap_data(sightings)
            if not len(years):
                return False
            self._draw_heatmap(grid, years)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Species Heatmap", self.mdiParent.db))
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
            x, y, colors, ids, locs, dates, durs, incidental_count = \
                self._build_scatter_data(checklists, sightings)
            if not x:
                return False
            self._draw_scatter_chart(x, y, colors, ids, locs, dates, durs,
                                     incidental_count)
            self.mdiParent.SetChildDetailsLabels(self, filter)
            self.setWindowTitle(
                filter.buildWindowTitle("Checklist Scatter", self.mdiParent.db))
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
            labels, counts, y_label = self._build_month_data(sightings)
        elif default == "day":
            labels, counts, y_label = self._build_day_data(sightings)
        else:
            labels, counts, y_label = self._build_year_data(sightings)

        if not labels:
            return False

        self._draw_chart(labels, counts, y_label)

        self.mdiParent.SetChildDetailsLabels(self, filter)

        self.setWindowTitle(
            filter.buildWindowTitle("Bar Graph", self.mdiParent.db))

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_bird_white.png"),
                       QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        return True
