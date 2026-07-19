import csv
import json
import ssl
import urllib.request
import urllib.error

# Build an SSL context that works inside a PyInstaller bundle on Windows.
# certifi ships its own CA bundle; fall back to the default context on platforms
# where certifi is unavailable (the default context uses the OS trust store).
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

import code_Filter
import code_DataBase
import code_Stylesheet
import code_Web

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel,
    QMdiSubWindow, QMessageBox, QPushButton, QSizePolicy,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)


# ── Background thread for eBird region list fetches ───────────────────────────

class _RegionFetch(QThread):
    """Fetches /v2/ref/region/list/{regionType}/{parentCode} in a background
    thread.  Emits (ok, regions): ok is False only on a network/API failure, so
    callers can tell "no subregions" ([] with ok=True) from "check your key"."""
    done = Signal(bool, list)

    def __init__(self, path, api_key):
        super().__init__()
        self._path    = path
        self._api_key = api_key

    def run(self):
        url = "https://api.ebird.org" + self._path
        req = urllib.request.Request(url, headers={"X-eBirdApiToken": self._api_key})
        try:
            with urllib.request.urlopen(req, timeout=20, context=_SSL_CTX) as resp:
                self.done.emit(True, json.loads(resp.read().decode("utf-8")))
        except Exception:
            self.done.emit(False, [])


# ── Subnational-1 CSV loader (cached at module level) ─────────────────────────

_STATE_DATA = None   # dict: country_code → sorted list of (state_name, state_code)

def _load_state_data():
    global _STATE_DATA
    if _STATE_DATA is not None:
        return
    path = code_DataBase.resource_path("ebird_api_ref_location_eBird_list_subnational1.csv")
    data = {}
    try:
        with open(path, "r", errors="replace") as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            for row in reader:
                if len(row) < 3:
                    continue
                country_code, state_code, state_name = row[0].strip(), row[1].strip(), row[2].strip()
                if not state_code or state_code.endswith("-"):
                    # Entry with no subnational1 divisions — skip
                    continue
                data.setdefault(country_code, []).append((state_name, state_code))
    except Exception:
        pass
    for code in data:
        data[code].sort()
    _STATE_DATA = data


# ── Module-level region caches (survive across dialog opens) ──────────────────

_COUNTRY_DATA = None   # sorted list of (name, code), US/Canada pinned first
_COUNTY_DATA  = {}     # state_code → sorted list of (name, code)

# Strong refs to in-flight fetch threads.  Owner objects (dialog/window) can be
# garbage-collected while a request is outstanding — e.g. the picker is closed
# mid-fetch — and without a surviving reference the QThread's C++ object is
# destroyed while its thread runs, which aborts the process.
_ACTIVE_FETCHES = set()

def _track_fetch(thread):
    _ACTIVE_FETCHES.add(thread)
    thread.finished.connect(lambda t=thread: _ACTIVE_FETCHES.discard(t))


def _country_sort_key(name):
    # Alphabetical, with United States and Canada pinned to the top.
    if name == "United States":
        return "  " + name
    if name == "Canada":
        return " " + name
    return name


# ── Region tree-picker dialog ─────────────────────────────────────────────────

_LEVEL_COUNTRY = 0
_LEVEL_STATE   = 1
_LEVEL_COUNTY  = 2

_LEVEL_CAPTION = {_LEVEL_COUNTRY: "country",
                  _LEVEL_STATE:   "state/province",
                  _LEVEL_COUNTY:  "county"}

_ROLE = Qt.ItemDataRole.UserRole


class RegionTreeDialog(QDialog):
    """Lazy drill-down picker: Country → State/Province → County.

    Any level is a valid final answer, so navigation and selection use
    different gestures: a single click highlights a node (expanding it if it
    has children), the bottom button — whose caption tracks the highlight,
    e.g. 'Use Ohio (state/province)' — confirms it, and double-click is a
    shortcut for the same confirm.  Mirrors ChecklistTreeDialog's dummy-child
    lazy pattern, but the county level is fetched from the eBird API on a
    background thread, so expansion shows a transient 'Loading…' child.

    After exec(), `result` is None (cancelled) or a dict with:
      code   — eBird region code of the chosen node ("US", "US-OH", "US-OH-041")
      label  — breadcrumb, deepest first ("Delaware, Ohio, United States")
      path   — {"country": code, "state": code or "", "county": code or ""}
    """

    def __init__(self, api_key, parent=None):
        super().__init__(parent)
        self._api_key  = api_key
        self.result    = None
        self._fetching = set()   # items with an in-flight county fetch
        self._closed   = False
        self.finished.connect(self._markClosed)

        self.setWindowTitle("Select a region")
        self.resize(460, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(16)
        self.tree.setExpandsOnDoubleClick(False)   # double-click confirms instead
        self.tree.itemExpanded.connect(self._on_expanded)
        self.tree.itemClicked.connect(self._on_clicked)
        self.tree.itemDoubleClicked.connect(self._on_double_clicked)
        self.tree.currentItemChanged.connect(self._on_current_changed)
        layout.addWidget(self.tree)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btnCancel = QPushButton("Cancel")
        self.btnCancel.clicked.connect(self.reject)
        buttons.addWidget(self.btnCancel)
        self.btnSelect = QPushButton("Select a region")
        self.btnSelect.setEnabled(False)
        self.btnSelect.clicked.connect(self._accept_current)
        buttons.addWidget(self.btnSelect)
        layout.addLayout(buttons)

        self._populate_countries()

    # ── node helpers ─────────────────────────────────────────────────────────

    def _make_node(self, parent, name, level, code, expandable):
        item = QTreeWidgetItem(parent, [name])
        item.setData(0, _ROLE, {"level": level, "code": code,
                                "name": name, "loaded": False})
        if expandable:
            # Dummy child gives the node an expander arrow until it's loaded.
            QTreeWidgetItem(item, ["…"])
        return item

    def _make_placeholder(self, parent, text):
        item = QTreeWidgetItem(parent, [text])
        item.setFlags(Qt.ItemFlag.NoItemFlags)   # grayed, unselectable
        return item

    def _populate_countries(self):
        if _COUNTRY_DATA is not None:
            self._fill_countries()
            return
        self._make_placeholder(self.tree.invisibleRootItem(), "Loading countries…")
        thread = _RegionFetch("/v2/ref/region/list/country/world", self._api_key)
        thread.done.connect(self._on_countries_fetched)
        thread.finished.connect(thread.deleteLater)
        _track_fetch(thread)
        thread.start()

    def _on_countries_fetched(self, ok, regions):
        if self._closed:
            return
        _store_countries(ok, regions)
        self.tree.clear()
        if _COUNTRY_DATA is None:
            self._make_placeholder(self.tree.invisibleRootItem(),
                                   "(could not load — check API key)")
            return
        self._fill_countries()

    def _fill_countries(self):
        root = self.tree.invisibleRootItem()
        for name, code in _COUNTRY_DATA:
            has_states = bool((_STATE_DATA or {}).get(code))
            self._make_node(root, name, _LEVEL_COUNTRY, code, has_states)

    # ── lazy loading ─────────────────────────────────────────────────────────

    def _ensure_loaded(self, item):
        """Populate the node's children.  States come from the bundled CSV
        (synchronous); counties come from the eBird API (asynchronous — a
        'Loading…' child shows until the fetch lands)."""
        data = item.data(0, _ROLE)
        if data is None or data.get("loaded"):
            return

        if data["level"] == _LEVEL_COUNTRY:
            item.takeChildren()
            for name, code in (_STATE_DATA or {}).get(data["code"], []):
                self._make_node(item, name, _LEVEL_STATE, code, True)
            data["loaded"] = True
            item.setData(0, _ROLE, data)
            return

        if data["level"] == _LEVEL_STATE:
            cached = _COUNTY_DATA.get(data["code"])
            if cached is not None:
                self._fill_counties(item, cached)
                return
            if item in self._fetching:
                return
            self._fetching.add(item)
            item.takeChildren()
            self._make_placeholder(item, "Loading counties…")
            thread = _RegionFetch(
                f"/v2/ref/region/list/subnational2/{data['code']}",
                self._api_key,
            )
            thread.done.connect(
                lambda ok, regions, it=item: self._on_counties_fetched(it, ok, regions))
            thread.finished.connect(thread.deleteLater)
            _track_fetch(thread)
            thread.start()

    def _on_counties_fetched(self, item, ok, regions):
        if self._closed:
            return
        self._fetching.discard(item)
        if not ok:
            # Leave the node unloaded so collapsing and re-expanding retries.
            item.takeChildren()
            self._make_placeholder(item, "(could not load counties — check connection)")
            return
        counties = sorted((r.get("name", r["code"]), r["code"]) for r in regions)
        _COUNTY_DATA[item.data(0, _ROLE)["code"]] = counties
        self._fill_counties(item, counties)

    def _fill_counties(self, item, counties):
        item.takeChildren()
        data = item.data(0, _ROLE)
        for name, code in counties:
            self._make_node(item, name, _LEVEL_COUNTY, code, False)
        data["loaded"] = True
        item.setData(0, _ROLE, data)

    # ── signals ──────────────────────────────────────────────────────────────

    def _markClosed(self, *args):
        self._closed = True

    def _on_expanded(self, item):
        self._ensure_loaded(item)

    def _on_clicked(self, item, _col):
        # Navigation: a plain click also drills in (never collapses — that
        # stays on the expander arrow), so users who click a country expecting
        # to "open" it are not stranded.
        data = item.data(0, _ROLE)
        if data is not None and data["level"] != _LEVEL_COUNTY:
            self._ensure_loaded(item)
            item.setExpanded(True)

    def _on_double_clicked(self, item, _col):
        if item.data(0, _ROLE) is not None:
            self.tree.setCurrentItem(item)
            self._accept_current()

    def _on_current_changed(self, current, _previous):
        data = current.data(0, _ROLE) if current is not None else None
        if data is None:
            self.btnSelect.setText("Select a region")
            self.btnSelect.setEnabled(False)
            return
        self.btnSelect.setText(
            f"Use {data['name']} ({_LEVEL_CAPTION[data['level']]})")
        self.btnSelect.setEnabled(True)

    # ── selection ────────────────────────────────────────────────────────────

    def _accept_current(self):
        item = self.tree.currentItem()
        data = item.data(0, _ROLE) if item is not None else None
        if data is None:
            return
        names, path = [], {"country": "", "state": "", "county": ""}
        node = item
        while node is not None:
            d = node.data(0, _ROLE)
            if d is None:
                break
            names.append(d["name"])
            path[{_LEVEL_COUNTRY: "country",
                  _LEVEL_STATE:   "state",
                  _LEVEL_COUNTY:  "county"}[d["level"]]] = d["code"]
            node = node.parent()
        self.result = {"code": data["code"],
                       "label": ", ".join(names),
                       "path": path}
        self.accept()

    # ── pre-expansion to the previous selection ──────────────────────────────

    def _find_child_by_code(self, parent, code):
        for i in range(parent.childCount()):
            child = parent.child(i)
            d = child.data(0, _ROLE)
            if d is not None and d["code"] == code:
                return child
        return None

    def expand_to(self, path):
        """Re-expand to a previous selection's {country, state, county} code
        path.  Descends only as far as synchronously-available data allows —
        an uncached county list is not fetched here."""
        if not path or not path.get("country"):
            return
        parent = self.tree.invisibleRootItem()
        deepest = None
        for level_key in ("country", "state", "county"):
            code = path.get(level_key)
            if not code:
                break
            node = self._find_child_by_code(parent, code)
            if node is None:
                break
            deepest = node
            if level_key != "county":
                data = node.data(0, _ROLE)
                if level_key == "state" and not data.get("loaded") \
                        and _COUNTY_DATA.get(data["code"]) is None:
                    break   # counties not cached — don't fire a fetch here
                self._ensure_loaded(node)
                node.setExpanded(True)
            parent = node
        if deepest is not None:
            self.tree.setCurrentItem(deepest)
            self.tree.scrollToItem(deepest)


def _store_countries(ok, regions):
    """Cache the world country list (module level, shared by every dialog)."""
    global _COUNTRY_DATA
    if not ok or not regions:
        return
    pairs = [(r.get("name", r["code"]), r["code"]) for r in regions]
    pairs.sort(key=lambda p: _country_sort_key(p[0]))
    _COUNTRY_DATA = pairs


# ── Explorer window ───────────────────────────────────────────────────────────

class Explorer(QMdiSubWindow):

    def __init__(self):
        super().__init__()
        self.mdiParent  = ""
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle("Community Sightings Explorer")

        self._api_key      = ""
        self._regionCode   = None
        self._regionLabel  = None
        self._regionPath   = None   # {"country","state","county"} codes

        _load_state_data()
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(10)

        # Centered picker button with the current selection beneath it
        self.selectRegionBtn = QPushButton("Select Region…")
        self.selectRegionBtn.clicked.connect(self._openRegionDialog)
        self.selectRegionBtn.setStyleSheet(
            f"QPushButton {{ background: {code_Stylesheet.CHART_PRIMARY};"
            " color: white; }"
            " QPushButton:hover { background: #7aaeff; }"
            " QPushButton:pressed { background: #3d74d6; }")
        root.addWidget(self.selectRegionBtn, 0, Qt.AlignHCenter)
        self.regionLabel = QLabel("No region selected")
        self.regionLabel.setWordWrap(True)
        self.regionLabel.setAlignment(Qt.AlignHCenter)
        region_font = self.regionLabel.font()
        region_font.setItalic(True)
        self.regionLabel.setFont(region_font)
        self.regionLabel.setStyleSheet("color: #888;")
        root.addWidget(self.regionLabel)

        root.addStretch()

        # Buttons
        self.notableBtn = QPushButton("Notable Community Sightings (Past 3 days)")
        self.notableBtn.clicked.connect(self._runNotable)
        root.addWidget(self.notableBtn)

        self.allBtn = QPushButton("All Community Sightings (Past 3 days)")
        self.allBtn.clicked.connect(self._runAll)
        root.addWidget(self.allBtn)

        self.notableMapBtn = QPushButton("Notable Sightings Map (Past 3 days)")
        self.notableMapBtn.clicked.connect(self._runNotableMap)
        root.addWidget(self.notableMapBtn)

        self.hotspotBtn = QPushButton("Hotspot Map")
        self.hotspotBtn.clicked.connect(self._runHotspotMap)
        root.addWidget(self.hotspotBtn)

        self.speciesListBtn = QPushButton("Species List")
        self.speciesListBtn.clicked.connect(self._runSpeciesList)
        root.addWidget(self.speciesListBtn)

    # ── Initialisation (called after mdiParent is set) ────────────────────────

    def load(self):
        """Warm the module-level country cache so the picker opens instantly."""
        self._api_key = self.mdiParent.db.ebirdApiKey.strip()
        if _COUNTRY_DATA is not None:
            return
        thread = _RegionFetch("/v2/ref/region/list/country/world", self._api_key)
        thread.done.connect(_store_countries)
        thread.finished.connect(thread.deleteLater)
        _track_fetch(thread)
        thread.start()

    def scaleMe(self):
        sf = self.mdiParent.scaleFactor
        self.resize(int(440 * sf), int(315 * sf))

    # ── Region picker ─────────────────────────────────────────────────────────

    def _openRegionDialog(self):
        dlg = RegionTreeDialog(self._api_key, self)
        if self._regionPath:
            dlg.expand_to(self._regionPath)
        if dlg.exec() and dlg.result:
            self._regionCode  = dlg.result["code"]
            self._regionLabel = dlg.result["label"]
            self._regionPath  = dlg.result["path"]
            self.regionLabel.setText(self._regionLabel)
            self.regionLabel.setStyleSheet(
                f"color: {code_Stylesheet.CHART_PRIMARY};")
            region_font = self.regionLabel.font()
            region_font.setItalic(False)
            self.regionLabel.setFont(region_font)

    # ── Filter construction ───────────────────────────────────────────────────

    def _build_filter(self):
        """Return a (filter, region_code, region_label) triple from the current
        selection, or (None, None, None) — after alerting — if no region is
        selected.  Every report button funnels through here, so the alert
        lives in one place."""
        if not self._regionCode:
            QMessageBox.information(
                self,
                "Select a Region",
                "Please choose a region with the Select Region… button\n"
                "before running a report.",
            )
            return None, None, None
        f = code_Filter.Filter()
        f.setLocationType("EBirdRegion")
        f.setLocationName(self._regionCode)
        f.regionLabel = self._regionLabel
        return f, self._regionCode, self._regionLabel

    # ── Report launchers ──────────────────────────────────────────────────────

    def _runNotable(self):
        f, code, label = self._build_filter()
        if not f:
            return
        sub = code_Web.Web()
        sub.mdiParent = self.mdiParent
        if sub.loadNotableSightings(f) is True:
            self.mdiParent.mdiArea.addSubWindow(sub)
            self.mdiParent.PositionChildWindow(sub, self)
            sub.show()

    def _runAll(self):
        f, code, label = self._build_filter()
        if not f:
            return
        sub = code_Web.Web()
        sub.mdiParent = self.mdiParent
        if sub.loadAllSightings(f) is True:
            self.mdiParent.mdiArea.addSubWindow(sub)
            self.mdiParent.PositionChildWindow(sub, self)
            sub.show()

    def _runNotableMap(self):
        f, code, label = self._build_filter()
        if not f:
            return
        sub = code_Web.Web()
        sub.mdiParent = self.mdiParent
        if sub.loadNotableMap(f) is True:
            self.mdiParent.mdiArea.addSubWindow(sub)
            self.mdiParent.PositionChildWindow(sub, self)
            sub.show()

    def _runHotspotMap(self):
        f, code, label = self._build_filter()
        if not f:
            return
        sub = code_Web.Web()
        sub.mdiParent = self.mdiParent
        if sub.loadHotspotMap(f) is True:
            self.mdiParent.mdiArea.addSubWindow(sub)
            self.mdiParent.PositionChildWindow(sub, self)
            sub.show()

    def _runSpeciesList(self):
        f, code, label = self._build_filter()
        if not f:
            return
        sub = code_Web.Web()
        sub.mdiParent = self.mdiParent
        if sub.loadRegionalTaxonomy(f) is True:
            self.mdiParent.mdiArea.addSubWindow(sub)
            self.mdiParent.PositionChildWindow(sub, self)
            sub.show()

