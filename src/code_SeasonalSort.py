"""Seasonal (day-of-year) sorting for report tables that carry date columns.

A chronological sort answers "when did this happen"; a seasonal sort answers
"where in the year does this fall" — every Jan 1 record first, every Dec 31
record last, regardless of year.  It is the ordering you want for phenology:
when do I see this species, when am I out birding.

The order is offered by right-clicking a date column's header, so it costs no
screen space and one install() call covers a whole table.  The name matches the
Sighting Filter's existing "Seasonal Range" controls, which already express a
position in the year independent of year.

Sorting is driven by Qt's own sortItems: date cells are SeasonalDateItem, whose
__lt__ consults the table's "seasonalSort" property, so both orders come from
one item class and no report has to re-sort anything itself.

Why MM-DD and not an ordinal day number: ordinal day 60 is Feb 29 in a leap
year and Mar 1 otherwise, so an ordinal key silently interleaves late-February
and early-March records across years.  Comparing "MM-DD" avoids that entirely,
and because dates are already stored as "YYYY-MM-DD" the key is a substring —
no date parsing at all.  The year is appended so records sharing a day sub-sort
oldest-first instead of landing in arbitrary order.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QHeaderView, QMenu, QTableWidgetItem

# Dedicated item-data role for the sort key.  NOT Qt.UserRole: the report tables
# already store payloads there (the checklistID on Checklists rows, the species
# name on Species rows), and colliding with those would break row activation.
SEASONAL_KEY_ROLE = Qt.ItemDataRole.UserRole + 100

_SUFFIX = "  (seasonal)"

# Room for the sort arrow plus cell padding, matching the arrowAllowance
# code_Lists.scaleMe already uses when sizing its own sortable columns.
_ARROW_ALLOWANCE = 48


def seasonalKey(dateText):
    """"MM-DD-YYYY" from a "YYYY-MM-DD" or "YYYY-MM-DD HH:MM" string.

    Returns "" when the text is too short to carry a date, which sorts such
    cells together at one end rather than raising.
    """
    if not dateText or len(dateText) < 10:
        return ""
    return dateText[5:10] + "-" + dateText[0:4]


class SeasonalDateItem(QTableWidgetItem):
    """A date cell that can sort chronologically or seasonally.

    Which one applies is decided per-table at sort time via the "seasonalSort"
    property, so toggling the mode needs no rebuild of the rows.
    """

    def __lt__(self, other):
        """Compare seasonally or chronologically — never via super().

        MUST NOT call super().__lt__(): under PySide6 that does NOT reach the
        C++ QTableWidgetItem::operator<.  It re-enters
        QTableWidgetItemWrapper::operator<, which looks up the Python override
        and calls this method again — unbounded recursion that blows the C
        stack and segfaults the app mid-sort (crash 2026-08-29).  Both branches
        therefore compare in pure Python.

        Chronological compares the display text directly, which is correct
        because the dates are stored "YYYY-MM-DD" (and "YYYY-MM-DD HH:MM" on
        the Locations list): lexicographic order IS chronological order for
        that format, digit by digit.
        """
        table = self.tableWidget()
        if table is not None and bool(table.property("seasonalSort")):
            mine = self.data(SEASONAL_KEY_ROLE) or ""
            theirs = other.data(SEASONAL_KEY_ROLE) or ""
            if mine or theirs:
                return mine < theirs
        return self.text() < other.text()


def dateItem(dateText, displayText=None):
    """A date cell carrying both its display text and its seasonal sort key."""
    item = SeasonalDateItem()
    item.setData(Qt.DisplayRole,
                 dateText if displayText is None else displayText)
    item.setData(SEASONAL_KEY_ROLE, seasonalKey(dateText))
    return item


def install(table, dateColumns):
    """Offer seasonal sorting on `table`'s date columns via a header right-click.

    dateColumns are logical column indexes whose cells were built with
    dateItem().  Safe to call once per fill; re-installing simply resets the
    table to chronological order.
    """
    table.setProperty("seasonalSort", False)
    table.setProperty("seasonalColumns", list(dateColumns))
    # A refill re-sizes its own columns, so any widths saved by a previous
    # seasonal session are stale and must not be restored over them.
    table._seasonalSavedWidths = None

    header = table.horizontalHeader()
    if not header.property("seasonalMenuInstalled"):
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(
            lambda pos, t=table: _showMenu(t, pos))
        header.setProperty("seasonalMenuInstalled", True)
    _annotate(table, False)


def _showMenu(table, pos):
    header = table.horizontalHeader()
    column = header.logicalIndexAt(pos)
    if column not in (table.property("seasonalColumns") or []):
        return          # not a date column — nothing seasonal to offer

    seasonal = bool(table.property("seasonalSort"))
    menu = QMenu(table)
    actChrono = menu.addAction("Sort by date")
    actSeasonal = menu.addAction("Sort by day of year (seasonal)")
    for act, on in ((actChrono, not seasonal), (actSeasonal, seasonal)):
        act.setCheckable(True)
        act.setChecked(on)

    chosen = menu.exec(header.mapToGlobal(pos))
    if chosen is None:
        return
    apply(table, column, chosen is actSeasonal)


def apply(table, column, seasonal):
    """Sort `column` in the chosen order and label the date headers to match."""
    table.setProperty("seasonalSort", bool(seasonal))
    _annotate(table, bool(seasonal))

    header = table.horizontalHeader()
    order = header.sortIndicatorOrder()
    table.sortItems(column, order)
    header.setSortIndicator(column, order)
    header.setSortIndicatorShown(True)

    # Only after the indicator is shown: the size hint reserves room for the
    # arrow, so asking earlier would under-measure.
    _fitDateColumns(table, bool(seasonal))


def _fitDateColumns(table, seasonal):
    """Widen the date columns to fit the "(seasonal)" suffix, restore on exit.

    The suffix makes the header text longer than the column was sized for, and
    the sort arrow is laid out after the text — so without this the arrow is
    pushed into the text or clipped off the edge entirely.  Widths are only ever
    increased, never shrunk, so a column already wide enough is left alone; the
    originals are restored when seasonal mode is switched off.
    """
    header = table.horizontalHeader()
    columns = table.property("seasonalColumns") or []

    if seasonal:
        if getattr(table, "_seasonalSavedWidths", None) is None:
            table._seasonalSavedWidths = {c: table.columnWidth(c)
                                          for c in columns}
        for column in columns:
            # A stretched section sizes itself; forcing a width would fight it.
            if header.sectionResizeMode(column) != QHeaderView.ResizeMode.Interactive:
                continue
            item = table.horizontalHeaderItem(column)
            text = item.text() if item is not None else ""
            # Qt's own hint, and a direct measurement of the text plus room for
            # the arrow — the larger of the two.  The measurement is the same
            # "text + arrowAllowance" idiom scaleMe already uses for the
            # Checklists columns, and it covers the case where the hint
            # under-reports because the app stylesheet supplies the header font.
            metrics = QFontMetrics(item.font() if item is not None else header.font())
            measured = metrics.horizontalAdvance(text) + _ARROW_ALLOWANCE
            needed = max(header.sectionSizeHint(column), measured)
            if table.columnWidth(column) < needed:
                table.setColumnWidth(column, needed)
    else:
        for column, width in (getattr(table, "_seasonalSavedWidths", None) or {}).items():
            if header.sectionResizeMode(column) == QHeaderView.ResizeMode.Interactive:
                table.setColumnWidth(column, width)
        table._seasonalSavedWidths = None


def _annotate(table, seasonal):
    """Mark every date header while seasonal mode is on.

    Qt's arrow only says "ascending on this column", so with two possible
    orderings it cannot tell the user WHICH ordering they are looking at.  The
    suffix says it outright.  Every date column is marked, not just the sorted
    one, because the mode is table-wide: sorting any other date column next
    will also be seasonal.
    """
    for column in (table.property("seasonalColumns") or []):
        item = table.horizontalHeaderItem(column)
        if item is None:
            continue
        base = item.text().replace(_SUFFIX, "")
        item.setText(base + (_SUFFIX if seasonal else ""))
