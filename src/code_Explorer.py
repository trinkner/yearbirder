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
    QMdiSubWindow, QMessageBox, QPushButton, QSizePolicy, QSlider,
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
        # encoding="utf-8" is REQUIRED, not tidiness: without it Python uses the
        # platform default, which is cp1252 on Windows.  This file is UTF-8, so
        # the accented region names came out mojibake there and only there —
        # "Auvergne-Rhone-Alpes" (with a circumflex) rendered as "RhA´ne".  macOS
        # defaults to UTF-8, which is why it looked correct in development.
        with open(path, "r", encoding="utf-8", errors="replace") as f:
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

# The region most recently chosen in any Explorer window: {"code","label","path"}
# or None.  The Explorer is constructed fresh on every open, so without this the
# selection would not survive even closing and reopening the window.  Seeded
# from preferences the first time an Explorer loads, so it also carries across
# app restarts; see Explorer._setRegion / Explorer.load.
_LAST_REGION = None

# The past-days slider value most recently set in any Explorer window, or None.
# Same two-tier arrangement as _LAST_REGION: session state here, seeded from
# preferences on the first Explorer of the run.
_LAST_BACK_DAYS = None

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
        # County code expand_to is waiting on: set when the target county's
        # list had to be fetched, cleared once the node exists and is selected.
        self._pendingCounty = None
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

        # A county targeted by expand_to could not be selected while its list
        # was still in flight; now that the nodes exist, finish the job.
        if self._pendingCounty:
            target = self._find_child_by_code(item, self._pendingCounty)
            if target is not None:
                self._pendingCounty = None
                self.tree.setCurrentItem(target)
                self.tree.scrollToItem(target)

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
        path.

        When the path names a county whose state has not had its county list
        fetched yet, this fires that fetch rather than stopping at the state.
        The fetch is asynchronous — the dialog still opens immediately, showing
        "Loading counties…" — so the county cannot be selected inline; it is
        recorded in _pendingCounty and selected by _on_counties_fetched when the
        list lands.  This matters most after the My County shortcut, which sets
        a region without ever opening the tree, so nothing is cached."""
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
                if level_key == "state" and path.get("county"):
                    # Remember the target before _ensure_loaded, so a cache hit
                    # (which fills synchronously) is handled by the loop below
                    # and a miss is handled once the fetch returns.
                    self._pendingCounty = path["county"]
                self._ensure_loaded(node)
                node.setExpanded(True)
            parent = node
        if deepest is not None:
            # If the county node already exists we reached it, so there is
            # nothing left pending.
            if deepest.data(0, _ROLE) is not None \
                    and deepest.data(0, _ROLE).get("code") == path.get("county"):
                self._pendingCounty = None
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
        self._backDays     = code_Web.EBIRD_BACK_DAYS_DEFAULT

        _load_state_data()
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(10)

        # Centered picker row with the current selection beneath it.  My County
        # keeps the default button styling so Select Region… stays the primary
        # action; the shortcut sits to its left, matching the Sighting Filter
        # where My County is likewise a plain button.
        self.myCountyBtn = QPushButton("My County")
        self.myCountyBtn.clicked.connect(self._applyMyCounty)

        self.selectRegionBtn = QPushButton("Select Region…")
        self.selectRegionBtn.clicked.connect(self._openRegionDialog)
        self.selectRegionBtn.setStyleSheet(
            f"QPushButton {{ background: {code_Stylesheet.CHART_PRIMARY};"
            " color: white; }"
            " QPushButton:hover { background: #7aaeff; }"
            " QPushButton:pressed { background: #3d74d6; }")

        pickerRow = QHBoxLayout()
        pickerRow.setSpacing(8)
        pickerRow.addStretch(1)
        pickerRow.addWidget(self.myCountyBtn)
        pickerRow.addWidget(self.selectRegionBtn)
        pickerRow.addStretch(1)
        root.addLayout(pickerRow)
        self.regionLabel = QLabel("No region selected")
        self.regionLabel.setWordWrap(True)
        self.regionLabel.setAlignment(Qt.AlignHCenter)
        region_font = self.regionLabel.font()
        region_font.setItalic(True)
        self.regionLabel.setFont(region_font)
        self.regionLabel.setStyleSheet("color: #888;")
        root.addWidget(self.regionLabel)

        # How far back the three community-sightings reports below ask eBird to
        # look.  The app stylesheet already draws QSlider in the thematic blue.
        root.addSpacing(6)
        self.backDaysLabel = QLabel()
        self.backDaysLabel.setAlignment(Qt.AlignHCenter)
        self.backDaysLabel.setStyleSheet(
            f"color: {code_Stylesheet.CHART_PRIMARY};")
        root.addWidget(self.backDaysLabel)

        self.backDaysSlider = QSlider(Qt.Horizontal)
        self.backDaysSlider.setRange(code_Web.EBIRD_BACK_DAYS_MIN,
                                     code_Web.EBIRD_BACK_DAYS_MAX)
        self.backDaysSlider.setValue(self._backDays)
        self.backDaysSlider.setSingleStep(1)
        self.backDaysSlider.setPageStep(1)
        # No tick marks: the app stylesheet styles the groove and handle, and a
        # styled QSlider doesn't draw them — the label above is the readout.
        self.backDaysSlider.setToolTip(
            "How many days of eBird history the Notable Community Sightings,\n"
            "All Community Sightings, and Notable Sightings Map reports cover.\n"
            "More days means a slower query and a longer report.")
        self.backDaysSlider.valueChanged.connect(self._onBackDaysChanged)
        root.addWidget(self.backDaysSlider)
        self._onBackDaysChanged(self._backDays)   # set the label's initial text

        root.addStretch()

        # Buttons.  The three community reports honour the slider above, so their
        # labels no longer name a fixed window.
        self.notableBtn = QPushButton("Notable Community Sightings")
        self.notableBtn.clicked.connect(self._runNotable)
        root.addWidget(self.notableBtn)

        self.allBtn = QPushButton("All Community Sightings")
        self.allBtn.clicked.connect(self._runAll)
        root.addWidget(self.allBtn)

        self.notableMapBtn = QPushButton("Notable Sightings Map")
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

        # _build_ui runs before mdiParent is assigned, so the county-aware
        # tooltip has to wait until here.  Wording mirrors the Sighting Filter's
        # My County button.
        county = self.mdiParent.db.myCounty
        self.myCountyBtn.setToolTip(
            "Set the region to My County (%s)" % county if county
            else "My County is not set yet — click to choose it in Preferences")

        # Restore the last region: from this session if an Explorer has already
        # set one, otherwise from preferences (first Explorer of the run).
        global _LAST_REGION
        if _LAST_REGION is None:
            stored = self.mdiParent.db.explorerRegion or {}
            if stored.get("code"):
                _LAST_REGION = {"code":  stored.get("code", ""),
                                "label": stored.get("label", "") or stored.get("code", ""),
                                "path":  stored.get("path") or {}}
        if _LAST_REGION and not self._regionCode:
            self._setRegion(_LAST_REGION["code"],
                            _LAST_REGION["label"],
                            _LAST_REGION["path"],
                            persist=False)

        # Same for the past-days slider.  Clamped to the slider's own range: a
        # hand-edited prefs file must not be able to push it out of bounds.
        global _LAST_BACK_DAYS
        if _LAST_BACK_DAYS is None:
            stored = self.mdiParent.db.explorerBackDays
            if stored:
                _LAST_BACK_DAYS = max(code_Web.EBIRD_BACK_DAYS_MIN,
                                      min(code_Web.EBIRD_BACK_DAYS_MAX, int(stored)))
        if _LAST_BACK_DAYS and _LAST_BACK_DAYS != self._backDays:
            # Block the signal so setValue does not re-enter the handler and
            # persist; update label and state explicitly instead.
            self.backDaysSlider.blockSignals(True)
            self.backDaysSlider.setValue(_LAST_BACK_DAYS)
            self.backDaysSlider.blockSignals(False)
            self._onBackDaysChanged(_LAST_BACK_DAYS, persist=False)

        if _COUNTRY_DATA is not None:
            return
        thread = _RegionFetch("/v2/ref/region/list/country/world", self._api_key)
        thread.done.connect(_store_countries)
        thread.finished.connect(thread.deleteLater)
        _track_fetch(thread)
        thread.start()

    def scaleMe(self):
        sf = self.mdiParent.scaleFactor
        self.resize(int(440 * sf), int(375 * sf))   # + the past-days slider row

    # ── Region picker ─────────────────────────────────────────────────────────

    def _setRegion(self, code, label, path, persist=True):
        """Adopt a region and show it beneath the picker.  Shared by the tree
        dialog, the My County shortcut, and session restore, so the three cannot
        drift apart.

        persist=False is used when restoring an already-stored region, so that
        reopening the window does not rewrite the preferences file with the
        value it just read."""
        global _LAST_REGION
        self._regionCode  = code
        self._regionLabel = label
        self._regionPath  = path
        _LAST_REGION = {"code": code, "label": label, "path": path}
        if persist:
            # The prefs file is a handful of lines, so rewriting it on each
            # change is cheaper than tracking dirty state, and it survives a
            # crash that an exit-time write would lose.
            db = self.mdiParent.db
            db.explorerRegion = dict(_LAST_REGION)
            db.writePreferences()
        self.regionLabel.setText(label)
        self.regionLabel.setStyleSheet(
            f"color: {code_Stylesheet.CHART_PRIMARY};")
        region_font = self.regionLabel.font()
        region_font.setItalic(False)
        self.regionLabel.setFont(region_font)

    def _openRegionDialog(self):
        dlg = RegionTreeDialog(self._api_key, self)
        if self._regionPath:
            dlg.expand_to(self._regionPath)
        if dlg.exec() and dlg.result:
            self._setRegion(dlg.result["code"],
                            dlg.result["label"],
                            dlg.result["path"])

    # ── My County shortcut ────────────────────────────────────────────────────

    def _myCountyRegion(self):
        """Resolve the configured My County to the Explorer's
        (code, label, path) triple, or None if it cannot be resolved.

        Preferences stores My County as a bare county NAME, while the Explorer
        needs an eBird subnational2 code.  For US counties that is derivable
        offline from the FIPS lookup — the same
        f"US-{abbr}-{fips[2:]}" construction Web._getEBirdRegionCode uses — so
        the common case costs no network round trip.  Outside the US there is no
        FIPS table, so we ask eBird for the state's subnational2 list and match
        by name."""
        db = self.mdiParent.db
        county = db.myCounty
        if not county:
            return None

        # The county name alone is ambiguous (many states have a "Boulder"),
        # so pull the country/state it belongs to from the user's own sightings.
        country_code = state_code = ""
        for entry in db.masterLocationList:
            if entry.get("county") == county:
                country_code = entry.get("countryCode", "")
                state_code   = entry.get("stateCode", "")
                break
        if not state_code:
            return None

        state_abbr   = state_code[3:] if len(state_code) > 3 else state_code
        country_name = db.GetCountryName(country_code) or country_code
        state_name   = db.GetStateName(state_code) or state_code

        code = ""
        if country_code == "US":
            for fips, s_abbr in db.countyCodeDict.get(county, []):
                if s_abbr == state_abbr:
                    code = f"US-{state_abbr}-{fips[2:]}"
                    break
        else:
            code = self._lookupCountyCode(state_code, county)

        if not code:
            return None
        label = f"{county}, {state_name}, {country_name}"
        path  = {"country": country_code, "state": state_code, "county": code}
        return code, label, path

    def _lookupCountyCode(self, state_code, county_name):
        """Non-US fallback: ask eBird for the state's subnational2 list and match
        by name.  Synchronous, but it runs only outside the US and only on an
        explicit button press."""
        url = f"https://api.ebird.org/v2/ref/region/list/subnational2/{state_code}"
        req = urllib.request.Request(url, headers={"X-eBirdApiToken": self._api_key})
        try:
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            with urllib.request.urlopen(req, timeout=20, context=_SSL_CTX) as resp:
                regions = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return ""
        finally:
            QApplication.restoreOverrideCursor()
        target = county_name.split(" (")[0].strip().lower()
        for r in regions:
            if r.get("name", "").strip().lower() == target:
                return r.get("code", "")
        return ""

    def _applyMyCounty(self):
        """Set the region to the county configured in Preferences → My
        Locations, or offer to go and configure it."""
        if not self.mdiParent.db.myCounty:
            self.mdiParent._promptSetMyLocation(
                "My County",
                "My County is the county you bird most often.")
            return

        resolved = self._myCountyRegion()
        if resolved is None:
            QMessageBox.information(
                self,
                "My County Not Found",
                f"Could not match “{self.mdiParent.db.myCounty}” to an eBird "
                "region.\n\nChoose the region with the Select Region… button "
                "instead.",
            )
            return
        self._setRegion(*resolved)

    # ── Past-days slider ──────────────────────────────────────────────────────

    def _onBackDaysChanged(self, days, persist=True):
        """Slider handler.  persist=False when restoring a stored value, so
        reopening the window does not rewrite prefs with what it just read.
        (valueChanged passes only `days`, so real drags always persist.)"""
        global _LAST_BACK_DAYS
        self._backDays = days
        self.backDaysLabel.setText(
            f"Past {days} day" + ("" if days == 1 else "s"))

        # _build_ui calls this once at construction to seed the label, while
        # mdiParent is still "".  That call must not touch the shared session
        # value: it would set _LAST_BACK_DAYS to the default before load() ran,
        # so load() would see a non-None value, skip reading preferences, and
        # find nothing to restore — the slider then reset to 3 on every open.
        if not self.mdiParent:
            return

        _LAST_BACK_DAYS = days
        if persist:
            db = self.mdiParent.db
            db.explorerBackDays = days
            db.writePreferences()

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
        # Read by the community-sightings builders (code_Web.ebirdBackDays); the
        # reports that don't take a date window simply ignore it.
        f.backDays = self._backDays
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

