# Reusable lazy-loading checklist/species picker.
#
# A single QTreeWidget drills down Year -> Month -> Date -> Location -> Time ->
# Species.  Each level is fetched from the database only when its parent is
# expanded (a dummy child marks a node as expandable until then), so the tree
# stays cheap even with thousands of checklists.  Picking a species leaf records
# the full (date, location, time, species) tuple and closes the dialog.

import code_Filter

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
)
from PySide6.QtCore import Qt


# Tree depth levels
_LEVEL_YEAR     = 0
_LEVEL_MONTH    = 1
_LEVEL_DATE     = 2
_LEVEL_LOCATION = 3
_LEVEL_TIME     = 4
_LEVEL_SPECIES  = 5

# 1-indexed so MONTHS[int("06")] == "June"
_MONTHS = ["", "January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]

_ROLE = Qt.ItemDataRole.UserRole


class ChecklistTreeDialog(QDialog):
    """Modal-ish picker.  After exec(), `result` is None (cancelled) or a dict
    with keys date / location / time / species."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.result = None

        self.setWindowTitle("Select species from a checklist")
        self.resize(460, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(16)
        self.tree.itemExpanded.connect(self._on_expanded)
        self.tree.itemClicked.connect(self._on_clicked)
        layout.addWidget(self.tree)

        self._populate_years()

    # ── node helpers ─────────────────────────────────────────────────────────

    def _make_node(self, parent, text, level, ctx):
        item = QTreeWidgetItem(parent, [text])
        item.setData(0, _ROLE, {"level": level, "ctx": ctx, "loaded": False})
        if level != _LEVEL_SPECIES:
            # Dummy child gives the node an expander arrow until it's loaded.
            QTreeWidgetItem(item, ["…"])
        return item

    def _populate_years(self):
        dates = self.db.GetDates(code_Filter.Filter())
        years = sorted({d[0:4] for d in dates if len(d) >= 4}, reverse=True)
        for y in years:
            self._make_node(self.tree.invisibleRootItem(), y, _LEVEL_YEAR, {"year": y})

    def _fetch_children(self, level, ctx):
        """Return a list of (display_text, child_ctx) for the node's children."""
        db = self.db
        if level == _LEVEL_YEAR:
            year = ctx["year"]
            f = code_Filter.Filter()
            f.setStartDate(year + "-01-01")
            f.setEndDate(year + "-12-31")
            months = sorted({d[5:7] for d in db.GetDates(f) if len(d) >= 7})
            return [(_MONTHS[int(m)], {**ctx, "month": m}) for m in months]

        if level == _LEVEL_MONTH:
            year, month = ctx["year"], ctx["month"]
            f = code_Filter.Filter()
            f.setStartDate(f"{year}-{month}-01")
            f.setEndDate(f"{year}-{month}-31")
            dates = sorted({d for d in db.GetDates(f) if d[0:7] == f"{year}-{month}"})
            return [(d, {**ctx, "date": d}) for d in dates]

        if level == _LEVEL_DATE:
            f = code_Filter.Filter()
            f.setStartDate(ctx["date"])
            f.setEndDate(ctx["date"])
            return [(loc, {**ctx, "location": loc}) for loc in db.GetLocations(f)]

        if level == _LEVEL_LOCATION:
            f = code_Filter.Filter()
            f.setStartDate(ctx["date"])
            f.setEndDate(ctx["date"])
            f.setLocationName(ctx["location"])
            f.setLocationType("Location")
            return [(t, {**ctx, "time": t}) for t in db.GetStartTimes(f)]

        if level == _LEVEL_TIME:
            f = code_Filter.Filter()
            f.setStartDate(ctx["date"])
            f.setEndDate(ctx["date"])
            f.setLocationName(ctx["location"])
            f.setLocationType("Location")
            f.setTime(ctx["time"])
            return [(sp, {**ctx, "species": sp}) for sp in db.GetSpecies(f)]

        return []

    def _ensure_loaded(self, item):
        data = item.data(0, _ROLE)
        if data.get("loaded"):
            return data
        item.takeChildren()  # drop the dummy placeholder
        for text, child_ctx in self._fetch_children(data["level"], data["ctx"]):
            self._make_node(item, text, data["level"] + 1, child_ctx)
        data["loaded"] = True
        item.setData(0, _ROLE, data)
        return data

    # ── signals ──────────────────────────────────────────────────────────────

    def _on_expanded(self, item):
        self._ensure_loaded(item)

    def _on_clicked(self, item, _col):
        data = item.data(0, _ROLE)
        if data and data["level"] == _LEVEL_SPECIES:
            ctx = data["ctx"]
            self.result = {
                "date":     ctx["date"],
                "location": ctx["location"],
                "time":     ctx["time"],
                "species":  ctx["species"],
            }
            self.accept()

    # ── pre-expansion to an existing assignment ──────────────────────────────

    def _find_child(self, parent, text):
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.text(0) == text:
                return child
        return None

    def expand_to(self, date="", location="", time="", species=""):
        """Expand and select as deep as the supplied (possibly partial) match
        allows.  Stops gracefully at the first level whose value is missing or
        not present in the tree."""
        if not date or len(date) < 7:
            return
        steps = [
            (self.tree.invisibleRootItem(), date[0:4]),
            (None, _MONTHS[int(date[5:7])]),
            (None, date),
            (None, location),
            (None, time),
            (None, species),
        ]
        parent = self.tree.invisibleRootItem()
        deepest = None
        for idx, (_unused, text) in enumerate(steps):
            if not text:
                break
            node = self._find_child(parent, text)
            if node is None:
                break
            deepest = node
            if idx < len(steps) - 1:
                self._ensure_loaded(node)
                node.setExpanded(True)
            parent = node
        if deepest is not None:
            self.tree.setCurrentItem(deepest)
            self.tree.scrollToItem(deepest)
