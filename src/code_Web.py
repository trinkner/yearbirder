from PySide6.QtCore import QLibraryInfo
import json
import os
import ssl
import sys

# SSL context that works inside a PyInstaller bundle on Windows.
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

from code_Stylesheet import CHART_PRIMARY, PHOTO_PRIMARY, RECORDINGS_PRIMARY

# import the GUI forms that we create with Qt Creator
import form_Web

# import the Qt components we'll use
# do this so later we won't have to clutter our code with references to parent Qt classes 

from PySide6.QtGui import (
    QCursor,
    QDesktopServices,
    QIcon,
    QPixmap
    )
    
from PySide6.QtCore import (
    Qt,
    QUrl,
    QFile,
    QTimer,
    Signal,
    Slot,
    QObject,
    QIODevice,
    QByteArray,
    QBuffer
    )

from PySide6.QtWebChannel import QWebChannel    
    
from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QMdiSubWindow
    )

from math import (
    floor
    )

from PySide6.QtWebEngineWidgets import (
    QWebEngineView,
    )
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineSettings,
    QWebEngineProfile,
    )

from collections import (
    defaultdict
    )

import base64


class MapBridge(QObject):
    """Qt/JavaScript bridge for the location map.

    Registered on the page's QWebChannel as 'bridge'.  When the user clicks a
    location dot, JavaScript calls locationClicked(name) which opens the
    Location child window for that location.
    """

    def __init__(self, web_window):
        super().__init__()
        self._web = web_window

    @Slot(str)
    def locationClicked(self, locationName):
        import code_Location
        sub = code_Location.Location()
        sub.mdiParent = self._web.mdiParent
        sub.FillLocation(locationName)
        self._web.mdiParent.mdiArea.addSubWindow(sub)
        self._web.mdiParent.PositionChildWindow(sub, self._web)
        sub.show()
        QApplication.processEvents()
        sub.scaleMe()


class CommunitySightingsMapBridge(QObject):
    """JS→Python bridge for community sightings maps.

    When the user clicks a location dot, opens an All Community Sightings
    tabular report for that specific eBird location (past 3 days).
    """

    def __init__(self, web_window):
        super().__init__()
        self._web = web_window

    @Slot(str, str)
    def locationClicked(self, loc_id, loc_name):
        import code_Filter
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QCursor

        # Resolve full geo hierarchy for this eBird location so the child
        # report can show Country / State / County badges correctly.
        api_key      = self._web.mdiParent.db.ebirdApiKey.strip()
        badge_country = None
        badge_state   = None
        badge_county  = None
        if api_key:
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            info = self._web._ebirdGet(f"/v2/ref/hotspot/info/{loc_id}", api_key)
            QApplication.restoreOverrideCursor()
            if isinstance(info, dict):
                badge_country = info.get("countryCode")       # e.g. "US"
                badge_state   = info.get("subnational1Code")  # e.g. "US-TX"
                badge_county  = info.get("subnational2Name")  # e.g. "Hidalgo"

        f = code_Filter.Filter()
        f.setLocationType("EBirdRegion")
        f.setLocationName(loc_id)
        f.regionLabel    = loc_name
        f._badgeCountry  = badge_country
        f._badgeState    = badge_state
        f._badgeCounty   = badge_county
        # Fallback if hotspot lookup fails (private locations not in hotspot API)
        f._badgeRegionId    = getattr(self._web, "_communityRegionId",    None)
        f._badgeRegionLabel = getattr(self._web, "_communityRegionLabel", None)

        main = self._web.mdiParent
        sub = Web()
        sub.mdiParent = main
        if sub.loadAllSightings(f) is True:
            main.mdiArea.addSubWindow(sub)
            main.PositionChildWindow(sub, self._web)
            sub.show()


class _ExternalLinkPage(QWebEnginePage):
    """QWebEnginePage that opens http/https links in the system browser.

    Used by the User Guide so that ebird.org links don't navigate inside the
    child window.
    """
    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class _FullScreenPage(QWebEnginePage):
    """QWebEnginePage that intercepts yearbirder://togglefullscreen navigation
    requests and routes them to the Web window's fullscreen toggle method."""

    def __init__(self, web_window, parent=None):
        super().__init__(parent)
        self._web = web_window

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme() == "yearbirder" and url.host() == "togglefullscreen":
            QTimer.singleShot(0, self._web._doToggleFullScreen)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class ChoroplethBridge(QObject):
    """Qt/JavaScript bridge for choropleth maps.

    Registered on the page's QWebChannel as 'bridge'.  When the user clicks a
    shaded region, JavaScript calls regionClicked(clickKey) which opens a
    species list (mode='species') or checklists list (mode='checklists')
    filtered to that region.
    """

    def __init__(self, web_window, location_type, mode='species'):
        super().__init__()
        self._web = web_window
        self._location_type = location_type  # "State", "County", or "Country"
        self._mode = mode

    @Slot(str)
    def regionClicked(self, clickKey):
        from copy import deepcopy
        import code_Lists

        newFilter = deepcopy(self._web.filter)
        newFilter.setLocationType(self._location_type)
        newFilter.setLocationName(clickKey)

        sub = code_Lists.Lists()
        sub.mdiParent = self._web.mdiParent

        if self._mode == 'checklists':
            filled = sub.FillChecklists(newFilter)
        else:
            filled = sub.FillSpecies(newFilter)

        if filled:
            self._web.mdiParent.mdiArea.addSubWindow(sub)
            self._web.mdiParent.PositionChildWindow(sub, self._web)
            sub.show()
            QApplication.processEvents()
            sub.scaleMe()


class AnimatedPhotosBridge(QObject):
    """JS→Python bridge for the Animated Sequence Map.

    When the user clicks a photo card, opens a Photos window filtered
    to that dot's location within the current map filter.
    """

    def __init__(self, web_window, locations):
        super().__init__()
        self._web       = web_window
        self._locations = locations   # one location name per photo, parallel to photos list

    @Slot(int)
    def photoClicked(self, idx):
        from copy import deepcopy
        import code_Photos

        if idx < 0 or idx >= len(self._locations):
            return

        new_filter = deepcopy(self._web.filter)
        new_filter.setLocationType("Location")
        new_filter.setLocationName(self._locations[idx])

        main = self._web.mdiParent
        if not main.db.GetSightingsWithPhotos(new_filter):
            return

        sub = code_Photos.Photos()
        sub.mdiParent = main
        main.mdiArea.addSubWindow(sub)
        main.PositionChildWindow(sub, self._web)
        sub.show()

        if sub.FillPhotos(new_filter) is False:
            sub.close()


class PhotosMapBridge(QObject):
    """JS→Python bridge for the Geolocated Photos map.

    Registered on the page's QWebChannel as 'bridge'.  When a marker is
    clicked, JavaScript calls photoClicked(idx) which opens an Enlargement
    window for that photo.  Only photos sharing the same lat/lon (i.e. the
    same spider-cluster pin) are passed to Enlargement so arrow-key navigation
    stays within that co-located group.
    """

    def __init__(self, web_window, photo_entries, markers):
        super().__init__()
        self._web     = web_window
        self._entries = photo_entries   # list of [photo_dict, sighting_dict]
        self._markers = markers         # parallel list of (lat, lon, name, date, location, uri)

    @Slot(int)
    def photoClicked(self, idx):
        import code_Enlargement

        if idx < 0 or idx >= len(self._entries):
            return

        main_window = self._web.mdiParent

        # Build a subset of entries that share the same lat/lon as the clicked
        # marker — these are the co-located photos in the same spider cluster.
        clicked_lat, clicked_lon = self._markers[idx][0], self._markers[idx][1]
        cluster_entries = []
        cluster_index   = 0
        for i, (lat, lon, *_) in enumerate(self._markers):
            if lat == clicked_lat and lon == clicked_lon:
                if i == idx:
                    cluster_index = len(cluster_entries)
                cluster_entries.append(self._entries[i])

        # Enlargement expects mdiParent to be a Photos-like object with:
        #   .mdiParent  → MainWindow
        #   .photoList  → [[photo_dict, sighting_dict], …]
        #   .filter     → filter object (used only for FillPhotos refresh)
        #   .FillPhotos(filter) → called after detach/delete
        # We satisfy this interface with a lightweight proxy.
        class _Proxy:
            def __init__(self):
                self.mdiParent = main_window
                self.photoList = cluster_entries
                self.filter    = None
            def FillPhotos(self, f):
                pass   # no Photos grid window to refresh from the map

        proxy = _Proxy()

        sub              = code_Enlargement.Enlargement()
        sub.mdiParent    = proxy
        sub.photoList    = proxy.photoList
        sub.currentIndex = cluster_index

        main_window.mdiArea.addSubWindow(sub)
        main_window.PositionChildWindow(sub, self._web)
        sub.show()
        sub.fillEnlargement()


class _AudioGalleryBridge(QObject):
    """JS→Python bridge for the Audio Species Gallery.

    Clicking a species row calls speciesClicked(species) which opens
    the audio browser filtered to that species.
    """

    def __init__(self, web_window, base_filter):
        super().__init__()
        self._web    = web_window
        self._filter = base_filter

    @Slot(str)
    def speciesClicked(self, species):
        import code_Recordings
        from copy import deepcopy
        new_filter = deepcopy(self._filter)
        new_filter.setSpeciesName(species)
        main = self._web.mdiParent
        if not main.db.GetSightingsWithRecordings(new_filter):
            return
        sub = code_Recordings.Recordings()
        sub.mdiParent = main
        main.mdiArea.addSubWindow(sub)
        main.PositionChildWindow(sub, self._web)
        sub.show()
        sub.FillRecordings(new_filter)


class _PhotoGalleryBridge(QObject):
    """JS→Python bridge for the Photo Species Gallery.

    Clicking a species row calls speciesClicked(species) which opens
    the photo browser filtered to that species.
    """

    def __init__(self, web_window, base_filter):
        super().__init__()
        self._web    = web_window
        self._filter = base_filter

    @Slot(str)
    def speciesClicked(self, species):
        import code_Photos
        from copy import deepcopy
        new_filter = deepcopy(self._filter)
        new_filter.setSpeciesName(species)
        main = self._web.mdiParent
        if not main.db.GetSightingsWithPhotos(new_filter):
            return
        sub = code_Photos.Photos()
        sub.mdiParent = main
        main.mdiArea.addSubWindow(sub)
        main.PositionChildWindow(sub, self._web)
        sub.show()
        sub.FillPhotos(new_filter)


class GeolocatedRecordingsBridge(QObject):
    """JS→Python bridge for the Geolocated Recordings map.

    Clicking a marker calls recordingClicked(idx) which opens the audio browser
    filtered to that sighting's location.
    """

    def __init__(self, web_window, locations):
        super().__init__()
        self._web       = web_window
        self._locations = locations   # one location name per audio sighting

    @Slot(int)
    def recordingClicked(self, idx):
        import code_Recordings
        from copy import deepcopy
        if idx < 0 or idx >= len(self._locations):
            return
        new_filter = deepcopy(self._web.filter)
        new_filter.setLocationType("Location")
        new_filter.setLocationName(self._locations[idx])
        main = self._web.mdiParent
        if not main.db.GetSightingsWithRecordings(new_filter):
            return
        sub = code_Recordings.Recordings()
        sub.mdiParent = main
        main.mdiArea.addSubWindow(sub)
        main.PositionChildWindow(sub, self._web)
        sub.show()
        sub.FillRecordings(new_filter)


class AnimatedRecordingsBridge(QObject):
    """JS→Python bridge for the Animated Recording Sequence Map.

    Clicking a dot calls recordingClicked(idx) which opens the audio browser
    filtered to that sighting's location.
    """

    def __init__(self, web_window, locations):
        super().__init__()
        self._web       = web_window
        self._locations = locations

    @Slot(int)
    def recordingClicked(self, idx):
        import code_Recordings
        from copy import deepcopy
        if idx < 0 or idx >= len(self._locations):
            return
        new_filter = deepcopy(self._web.filter)
        new_filter.setLocationType("Location")
        new_filter.setLocationName(self._locations[idx])
        main = self._web.mdiParent
        if not main.db.GetSightingsWithRecordings(new_filter):
            return
        sub = code_Recordings.Recordings()
        sub.mdiParent = main
        main.mdiArea.addSubWindow(sub)
        main.PositionChildWindow(sub, self._web)
        sub.show()
        sub.FillRecordings(new_filter)


class RegionalTaxonomyBridge(QObject):
    """JS→Python bridge for the Regional Taxonomy.

    When the user clicks a species name, JS calls speciesClicked(commonName)
    which opens the Individual window for that species.
    """

    def __init__(self, web_window):
        super().__init__()
        self._web = web_window

    @Slot(str)
    def speciesClicked(self, commonName):
        import code_Individual
        main = self._web.mdiParent
        if commonName not in main.db.speciesDict:
            return
        sub = code_Individual.Individual()
        sub.mdiParent = main
        sub.FillIndividual(commonName)
        main.mdiArea.addSubWindow(sub)
        main.PositionChildWindow(sub, self._web)
        sub.show()
        QApplication.processEvents()
        sub.scaleMe()


class NotableSightingsBridge(QObject):
    """JS→Python bridge for Notable Sightings — opens checklists, spawns maps, opens Individual."""

    def __init__(self, web_window, region_id=None, region_label=None,
                 back_days=3, api_key=None, species_obs=None, all_observations=None):
        super().__init__(web_window)
        self._web             = web_window
        self._region_id       = region_id
        self._region_label    = region_label
        self._back_days       = back_days
        self._api_key         = api_key
        self._species_obs     = species_obs or {}
        self._all_observations = all_observations or []

    @Slot(str)
    def openChecklist(self, sub_id):
        from PySide6.QtGui import QDesktopServices
        if sub_id:
            QDesktopServices.openUrl(QUrl(f"https://ebird.org/checklist/{sub_id}"))

    @Slot(str)
    def speciesClicked(self, common_name):
        import code_Individual
        main = self._web.mdiParent
        if common_name not in main.db.speciesDict:
            return
        sub = code_Individual.Individual()
        sub.mdiParent = main
        sub.FillIndividual(common_name)
        main.mdiArea.addSubWindow(sub)
        main.PositionChildWindow(sub, self._web)
        sub.show()
        QApplication.processEvents()
        sub.scaleMe()

    @Slot()
    def showNotableMap(self):
        mdi = self._web.mdiParent
        sub = Web()
        sub.mdiParent = mdi
        if sub.loadNotableMapFromObs(
            self._all_observations, self._web.filter,
            self._region_label, self._back_days,
        ):
            mdi.mdiArea.addSubWindow(sub)
            mdi.PositionChildWindow(sub, mdi)
            sub.show()

    @Slot(str, str, str)
    def showSpeciesMap(self, species_code, species_name, tag):
        if not self._region_id:
            return
        mdi = self._web.mdiParent
        sub = Web()
        sub.mdiParent = mdi
        obs_list = self._species_obs.get(species_name)
        if obs_list is not None:
            success = sub.loadSpeciesMapFromObs(
                obs_list, species_name, self._region_label, self._back_days, tag,
                region_id=self._region_id,
            )
        else:
            success = sub.loadSpeciesMap(
                self._region_id, self._region_label,
                species_code, species_name,
                self._api_key, self._back_days, tag,
            )
        if success:
            mdi.mdiArea.addSubWindow(sub)
            mdi.PositionChildWindow(sub, mdi)
            sub.show()


class AllSightingsBridge(QObject):
    """JS→Python bridge for All Community Sightings — spawns per-species location windows."""

    def __init__(self, web_window, region_id, region_label, back_days, api_key):
        super().__init__(web_window)
        self._web          = web_window
        self._region_id    = region_id
        self._region_label = region_label
        self._back_days    = back_days
        self._api_key      = api_key

    @Slot(str)
    def openChecklist(self, sub_id):
        from PySide6.QtGui import QDesktopServices
        if sub_id:
            QDesktopServices.openUrl(QUrl(f"https://ebird.org/checklist/{sub_id}"))

    @Slot(str)
    def speciesClicked(self, common_name):
        import code_Individual
        main = self._web.mdiParent
        if common_name not in main.db.speciesDict:
            return
        sub = code_Individual.Individual()
        sub.mdiParent = main
        sub.FillIndividual(common_name)
        main.mdiArea.addSubWindow(sub)
        main.PositionChildWindow(sub, self._web)
        sub.show()
        QApplication.processEvents()
        sub.scaleMe()

    @Slot(str, str)
    def showAllLocations(self, species_code, species_name):
        mdi = self._web.mdiParent
        sub = Web()
        sub.mdiParent = mdi
        if sub.loadSpeciesSightings(
            self._region_id, self._region_label,
            species_code, species_name,
            self._api_key, self._back_days,
        ):
            mdi.mdiArea.addSubWindow(sub)
            mdi.PositionChildWindow(sub, mdi)
            sub.show()

    @Slot(str, str, str)
    def showSpeciesMap(self, species_code, species_name, tag):
        mdi = self._web.mdiParent
        sub = Web()
        sub.mdiParent = mdi
        if sub.loadSpeciesMap(
            self._region_id, self._region_label,
            species_code, species_name,
            self._api_key, self._back_days, tag,
        ):
            mdi.mdiArea.addSubWindow(sub)
            mdi.PositionChildWindow(sub, mdi)
            sub.show()

    @Slot(str, str)
    def showRegionalTaxonomy(self, loc_id, loc_name):
        import code_Filter
        f = code_Filter.Filter()
        # Resolve L-code to the user's own location name so GetSightings can
        # filter seen/photographed to this specific location via locationDict.
        db = self._web.mdiParent.db
        loc_id_dict_inv = {v: k for k, v in db.locationIDDict.items()}
        user_loc_name = loc_id_dict_inv.get(loc_id)
        if user_loc_name:
            f.setLocationType("Location")
            f.setLocationName(user_loc_name)
        else:
            f.setLocationType("EBirdRegion")
            f.setLocationName(loc_id)
        f.regionLabel = loc_name
        mdi = self._web.mdiParent
        sub = Web()
        sub.mdiParent = mdi
        if sub.loadRegionalTaxonomy(f) is True:
            mdi.mdiArea.addSubWindow(sub)
            mdi.PositionChildWindow(sub, self._web)
            sub.show()

    @Slot(str, str, str)
    def showSingleLocationMap(self, loc_name, lat_str, lng_str):
        try:
            lat = float(lat_str)
            lng = float(lng_str)
        except (ValueError, TypeError):
            return
        mdi = self._web.mdiParent
        sub = Web()
        sub.mdiParent = mdi
        sub.loadLocationPointMap(loc_name, lat, lng)
        mdi.mdiArea.addSubWindow(sub)
        mdi.PositionChildWindow(sub, self._web)
        sub.show()


def satellite_toggle_js():
    """Return a <script> block adding Satellite/Map and Reset Zoom buttons to any Leaflet map."""
    return r"""<script>
(function() {
    function _findLeafletMap() {
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {
            try { var o = window[keys[i]]; if (o && o instanceof L.Map) return o; }
            catch(e) {}
        }
        return null;
    }
    function _initSatToggle() {
        var map = _findLeafletMap();
        if (!map) { setTimeout(_initSatToggle, 150); return; }

        // Capture the initial view once fitBounds/setView settles.
        var _initialCenter = null;
        var _initialZoom   = null;
        function _captureOnce() {
            if (_initialCenter) return;
            _initialCenter = map.getCenter();
            _initialZoom   = map.getZoom();
        }
        map.once('moveend', _captureOnce);
        setTimeout(_captureOnce, 500);

        var _satLayer = L.tileLayer(
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            {attribution: 'Tiles © Esri', maxZoom: 19}
        );
        var _streetLayer = null;
        map.eachLayer(function(lyr) { if (lyr._url) _streetLayer = lyr; });
        var _isSat = false;

        var _BtnStyle = (
            'background:#252730;color:#e2e4ec;border:1px solid #444657;' +
            'border-radius:5px;padding:4px 10px;font-size:12px;' +
            'cursor:pointer;font-family:inherit;box-shadow:0 1px 4px rgba(0,0,0,.4);'
        );

        var _MapCtrl = L.Control.extend({
            options: {position: 'topright'},
            onAdd: function(m) {
                var wrap = L.DomUtil.create('div');
                wrap.style.cssText = 'display:flex;gap:4px;';

                var satBtn = L.DomUtil.create('button', '', wrap);
                satBtn.textContent = 'Satellite';
                satBtn.style.cssText = _BtnStyle;
                satBtn.onmouseover = function() { satBtn.style.background = '#2e2f3d'; };
                satBtn.onmouseout  = function() { satBtn.style.background = '#252730'; };
                L.DomEvent.on(satBtn, 'click', function(e) {
                    L.DomEvent.stop(e);
                    if (_isSat) {
                        m.removeLayer(_satLayer);
                        if (_streetLayer) m.addLayer(_streetLayer);
                        satBtn.textContent = 'Satellite';
                        _isSat = false;
                    } else {
                        if (_streetLayer) m.removeLayer(_streetLayer);
                        m.addLayer(_satLayer);
                        satBtn.textContent = 'Map';
                        _isSat = true;
                    }
                });

                var resetBtn = L.DomUtil.create('button', '', wrap);
                resetBtn.textContent = 'Reset';
                resetBtn.style.cssText = _BtnStyle;
                resetBtn.onmouseover = function() { resetBtn.style.background = '#2e2f3d'; };
                resetBtn.onmouseout  = function() { resetBtn.style.background = '#252730'; };
                L.DomEvent.on(resetBtn, 'click', function(e) {
                    L.DomEvent.stop(e);
                    if (_initialCenter && _initialZoom !== null) {
                        m.setView(_initialCenter, _initialZoom);
                    }
                });

                var fsBtn = L.DomUtil.create('button', '', wrap);
                fsBtn.id = '_fs_toggle_btn';
                fsBtn.textContent = 'Full Screen';
                fsBtn.style.cssText = _BtnStyle;
                fsBtn.onmouseover = function() { fsBtn.style.background = '#2e2f3d'; };
                fsBtn.onmouseout  = function() { fsBtn.style.background = '#252730'; };
                L.DomEvent.on(fsBtn, 'click', function(e) {
                    L.DomEvent.stop(e);
                    window.location.href = 'yearbirder://togglefullscreen';
                });

                return wrap;
            }
        });
        new _MapCtrl().addTo(map);
    }
    _initSatToggle();
})();
</script>"""


class Web(QMdiSubWindow, form_Web.Ui_frmWeb):
    
    resized = Signal()

    def __init__(self):
        super(self.__class__, self).__init__()
        self.setupUi(self)
        self.setAttribute(Qt.WA_DeleteOnClose,True)
        self.mdiParent = ""
        self.setWindowIcon(QIcon(QPixmap(1,1)))
        self.contentType = "Web Page"
        self.resized.connect(self.resizeMe)
        self.webView = QWebEngineView(self)
        self.webView.setObjectName("webView")
        self._fsPage = _FullScreenPage(self, self.webView)
        self.webView.setPage(self._fsPage)
        self.webView.installEventFilter(self)
        self.webView.loadFinished.connect(self.LoadFinished)
        self.webView.loadProgress.connect(self.showLoadProgress)
        self.title = ""
        # Set once at creation so all choropleth temp-file pages can load
        # remote tile CDNs without a referer error on first load
        QWebEngineProfile.defaultProfile().settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )


    def resizeEvent(self, event):
        #routine to handle events on objects, like clicks, lost focus, gained forcus, etc.
        self.resized.emit()
        return super(self.__class__, self).resizeEvent(event)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if (obj is self.webView
                and event.type() == QEvent.Type.KeyPress
                and event.key() == Qt.Key_Escape
                and self.mdiParent
                and self.mdiParent.isFullScreen()):
            self._doToggleFullScreen()
            return True
        return super(self.__class__, self).eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.mdiParent and self.mdiParent.isFullScreen():
            self._doToggleFullScreen()
        else:
            super(self.__class__, self).keyPressEvent(event)
        
            
    def resizeMe(self):

        windowWidth =  self.frameGeometry().width()
        windowHeight = self.frameGeometry().height()
        self.scrollArea.setGeometry(5, 27, windowWidth -10 , windowHeight-35)
        self.webView.setGeometry(5, 27, windowWidth - 10, windowHeight-35)
        if self.contentType == "Map":
            self.webView.page().runJavaScript(
                "(function(){"
                "var k=Object.keys(window);"
                "for(var i=0;i<k.length;i++){"
                "try{var o=window[k[i]];if(o&&o instanceof L.Map){o.invalidateSize();return;}}"
                "catch(e){}}})()"
            )
   
   
    def html(self):

#         QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        if self.contentType in ("Notable Sightings", "All Community Sightings", "Species List"):
            return self._buildCommunityPdfHtml()

        # Build heading: type (H1) and filter details (H2).
        # When _buildFilterTitle was used, self.title is already "Type: filter details".
        # For maps/photos that set a plain self.title, use self.filter to build the description.
        title = getattr(self, 'title', '')
        filter_obj = getattr(self, 'filter', None)

        if ': ' in title:
            type_part, filter_part = title.split(': ', 1)
            heading = '<h1>' + type_part + '</h1><h2>' + filter_part + '</h2>'
        elif filter_obj is not None:
            full_title = filter_obj.buildWindowTitle(title, self.mdiParent.db)
            if ': ' in full_title:
                type_part, filter_part = full_title.split(': ', 1)
                heading = '<h1>' + type_part + '</h1><h2>' + filter_part + '</h2>'
            else:
                heading = '<h1>' + full_title + '</h1>'
        else:
            heading = '<h1>' + title + '</h1>' if title else ''

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

        myPixmap = self.webView.grab()
        myPixmap = myPixmap.scaledToWidth(600, Qt.SmoothTransformation)

        myByteArray = QByteArray()
        myBuffer = QBuffer(myByteArray)
        myBuffer.open(QIODevice.OpenModeFlag.WriteOnly)
        myPixmap.save(myBuffer, "PNG")

        encodedImage = base64.b64encode(myByteArray)

        html = html + ("""
        <img src="data:image/png;base64,
        """)

        html = html + str(encodedImage)[1:]

        html = html + ("""
            <font size>
            </body>
            </html>
            """)

#         QApplication.restoreOverrideCursor()

        return(html)


    def _buildCommunityPdfHtml(self):
        import html as _html
        data = getattr(self, "_pdf_data", None)
        if not data:
            return "<html><body><p>No data available.</p></body></html>"

        report_type = data["type"]

        if report_type == "Species List":
            return self._buildSpeciesListPdfHtml(data)

        # Notable Community Sightings / All Community Sightings
        region     = data["region"]
        date_range = data["date_range"]
        back_days  = data["back_days"]
        species    = data["species"]
        is_notable = (report_type == "Notable Community Sightings")

        TAG_LABELS = {
            "life": "Life", "country": "Country", "state": "State",
            "county": "County", "year": "Year",
        }
        TAG_COLORS = {
            "life": "#c0392b", "country": "#e07020", "state": "#2e7d32",
            "county": "#1a6ebd", "year": "#777",
        }

        rows = []
        for sp in species:
            com       = _html.escape(sp["com"])
            sci       = _html.escape(sp["sci"])
            tags      = sp["tags"]
            is_hybrid = sp["is_hybrid"]

            tags_html = ""
            for t in tags:
                color = TAG_COLORS.get(t, "#777")
                label = TAG_LABELS.get(t, t)
                tags_html += (
                    f'<span style="background:{color};color:#fff;font-size:0.7em;'
                    f'font-weight:bold;padding:1px 7px;border-radius:8px;'
                    f'margin-left:4px;white-space:nowrap;">{label}</span>'
                )

            com_style = "font-weight:bold;" + (" color:#777;" if is_hybrid else "")
            rows.append(
                f'<tr style="background:#f0f0f0;">'
                f'<td colspan="4" style="padding:5px 8px;border-top:2px solid #ccc;">'
                f'<span style="{com_style}">{com}</span>'
                f'<span style="font-style:italic;color:#555;font-size:0.87em;margin-left:8px;">{sci}</span>'
                f'{tags_html}'
                f'</td></tr>'
            )

            if is_notable:
                for obs in sp.get("obs", []):
                    rev_color = "#2e7d32" if obs["reviewed"] else "#c0392b"
                    rev_text  = "Confirmed" if obs["reviewed"] else "Unreviewed"
                    rows.append(
                        f'<tr>'
                        f'<td style="padding:3px 8px 3px 20px;color:#222;">{_html.escape(obs["loc"])}</td>'
                        f'<td style="padding:3px 8px;color:#444;white-space:nowrap;">{_html.escape(obs["dt"])}</td>'
                        f'<td style="padding:3px 8px;color:#444;text-align:right;">{_html.escape(obs["count"])}</td>'
                        f'<td style="padding:3px 8px;color:{rev_color};font-style:italic;font-size:0.88em;">{rev_text}</td>'
                        f'</tr>'
                    )
            else:
                n = sp.get("num_locations", 1)
                locs_note = f" ({n} locations)" if n > 1 else ""
                rows.append(
                    f'<tr>'
                    f'<td style="padding:3px 8px 3px 20px;color:#222;">'
                    f'{_html.escape(sp["loc"])}{_html.escape(locs_note)}</td>'
                    f'<td style="padding:3px 8px;color:#444;white-space:nowrap;">{_html.escape(sp["dt"])}</td>'
                    f'<td style="padding:3px 8px;color:#444;text-align:right;">{_html.escape(sp["count"])}</td>'
                    f'<td></td>'
                    f'</tr>'
                )

        rows_html = "\n".join(rows)

        total_species = data["total_species"]
        if is_notable:
            stats = f'{total_species} notable species &middot; {data["total_obs"]} reports'
            col4_header = "Status"
        else:
            stats = f'{total_species} species'
            col4_header = ""

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:"Times New Roman",Times,serif; color:#000; background:#fff; padding:0; }}
h1 {{ font-size:17pt; margin-bottom:3px; }}
h2 {{ font-size:12pt; font-weight:normal; margin-bottom:6px; }}
.meta {{ font-size:9pt; color:#555; margin-bottom:3px; }}
table {{ border-collapse:collapse; width:100%; font-size:10pt; margin-top:10px; }}
th {{ background:#ddd; padding:4px 8px; text-align:left; font-size:9pt;
      border-bottom:2px solid #aaa; white-space:nowrap; }}
th.right {{ text-align:right; }}
td {{ border-bottom:1px solid #e0e0e0; vertical-align:middle; }}
</style>
</head>
<body>
<h1>{_html.escape(report_type)}</h1>
<h2>{_html.escape(region)}</h2>
<div class="meta">{date_range} &nbsp;&middot;&nbsp; Past {back_days} days &nbsp;&middot;&nbsp; {stats}</div>
<div class="meta">Sightings data from eBird.org</div>
<table>
<thead>
<tr>
  <th>Location</th>
  <th>Date / Time</th>
  <th class="right">Count</th>
  <th>{col4_header}</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</body>
</html>"""


    def _buildSpeciesListPdfHtml(self, data):
        import html as _html

        region       = data["region"]
        subtitle     = data["subtitle"]
        total        = data["total"]
        seen_count   = data["seen_count"]
        unseen_count = data["unseen_count"]
        pct          = data["pct"]
        photos_open  = data["photos_open"]
        families     = data["families"]

        rows = []
        for fam in families:
            fam_com = _html.escape(fam["fam_com"])
            fam_sci = _html.escape(fam["fam_sci"])
            rows.append(
                f'<tr style="background:#e8e8e8;">'
                f'<td colspan="{4 if photos_open else 2}" '
                f'style="padding:6px 8px 3px;border-top:2px solid #bbb;">'
                f'<span style="font-weight:bold;font-size:0.85em;letter-spacing:0.05em;">'
                f'{fam_com.upper()}</span>'
                f'<span style="font-style:italic;color:#555;font-size:0.8em;margin-left:8px;">'
                f'{fam_sci}</span>'
                f'</td></tr>'
            )
            for sp in fam["entries"]:
                com  = _html.escape(sp["com"])
                sci  = _html.escape(sp["sci"])
                seen = sp["seen"]
                chk  = "&#10003;" if seen else ""
                chk_style = (
                    "background:#e07020;color:#fff;font-weight:bold;"
                    if seen else
                    "border:1px solid #aaa;"
                )
                name_style = "color:#555;" if seen else "font-weight:bold;"
                photo_cell = ""
                rec_cell = ""
                if photos_open:
                    photo_cell = (
                        f'<td style="padding:2px 6px;text-align:center;color:#e07020;">'
                        f'&#9679;</td>'
                        if sp["photo"] else
                        '<td></td>'
                    )
                    rec_cell = (
                        f'<td style="padding:2px 6px;text-align:center;color:#e07020;">'
                        f'&#9834;</td>'
                        if sp.get("rec") else
                        '<td></td>'
                    )
                rows.append(
                    f'<tr>'
                    f'<td style="padding:2px 8px;width:22px;text-align:center;">'
                    f'<span style="display:inline-block;width:16px;height:16px;'
                    f'border-radius:3px;font-size:11px;line-height:16px;'
                    f'text-align:center;{chk_style}">{chk}</span>'
                    f'</td>'
                    f'{photo_cell}'
                    f'{rec_cell}'
                    f'<td style="padding:2px 8px;{name_style}">{com}'
                    f'<span style="font-style:italic;color:#888;font-size:0.85em;'
                    f'margin-left:8px;">{sci}</span>'
                    f'</td>'
                    f'</tr>'
                )

        rows_html = "\n".join(rows)
        photo_note = (" &nbsp;&middot;&nbsp; &#9679; = photographed"
                      " &nbsp;&middot;&nbsp; &#9834; = recorded"
                      if photos_open else "")

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:"Times New Roman",Times,serif; color:#000; background:#fff; }}
h1 {{ font-size:17pt; margin-bottom:3px; }}
.meta {{ font-size:9pt; color:#555; margin-bottom:2px; }}
.stats {{ font-size:10pt; margin:6px 0 8px; }}
table {{ border-collapse:collapse; width:100%; font-size:10pt; }}
td {{ border-bottom:1px solid #e8e8e8; vertical-align:middle; }}
</style>
</head>
<body>
<h1>Species List: {_html.escape(region)}</h1>
<div class="meta">{_html.escape(subtitle)}</div>
<div class="meta">Species data from eBird.org</div>
<div class="stats">
  <strong>{seen_count}</strong> seen &nbsp;&middot;&nbsp;
  <strong>{unseen_count}</strong> not yet seen &nbsp;&middot;&nbsp;
  <strong>{total}</strong> total &nbsp;&middot;&nbsp;
  <strong>{pct}%</strong> complete{photo_note}
</div>
<table>
<tbody>
{rows_html}
</tbody>
</table>
</body>
</html>"""
        
       
    def scaleMe(self):
       
        fontSize = self.mdiParent.fontSize
        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setFontSize(QWebEngineSettings.FontSize.DefaultFontSize, floor(fontSize * 1.6))        
        
        scaleFactor = self.mdiParent.scaleFactor
        windowWidth =  int(800 * scaleFactor)
        windowHeight = int(580 * scaleFactor)       
        self.resize(windowWidth, windowHeight)


    def loadAboutYearbirder(self):
        
        self.title= "About Yearbirder"
        
        self.contentType = "About"
                    
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>About Yearbirder</title>
<style>
  body {{
    background-color: #1e1f26;
    color: #e2e4ec;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 14px;
    margin: 32px 40px;
    line-height: 1.6;
  }}
  h1 {{
    color: {CHART_PRIMARY};
    font-size: 2em;
    margin-bottom: 2px;
  }}
  .subtitle {{
    color: #8b8fa8;
    font-size: 0.95em;
    margin-top: 0;
    margin-bottom: 24px;
  }}
  .description {{
    font-size: 1em;
    margin-bottom: 28px;
  }}
  h2 {{
    color: {CHART_PRIMARY};
    font-size: 1.1em;
    border-bottom: 1px solid #3a3d4e;
    padding-bottom: 6px;
    margin-top: 28px;
  }}
  ul {{
    padding-left: 20px;
    margin: 10px 0;
  }}
  li {{
    margin-bottom: 8px;
    color: #c8cad8;
  }}
  li b {{
    color: #e2e4ec;
  }}
</style>
</head>
<body>
<h1>Yearbirder</h1>
"""
        html += f'<p class="subtitle">Version {self.mdiParent.versionNumber} &nbsp;&bull;&nbsp; {self.mdiParent.versionDate}</p>'
        html += """
<p class="description">
  Yearbirder is a desktop app to help birders analyze, visualize and map their personal eBird sightings and, optionally, their bird photography. Yearbirder is a free and open-source Python application.<br>
  Created by Richard Trinkner.
</p>

<p class="description">
  Found a bug or have a suggestion? Please report it on the
  <a href="https://github.com/trinkner/yearbirder/issues" style="color: #7aadff;">Yearbirder GitHub Issues page</a>.
</p>

<h2>Licenses</h2>
<ul>
  <li><b>Yearbirder</b> is licensed under the GNU General Public License, version 3.</li>
  <li><b>PySide6</b>, by The Qt Company, is used under the GNU Lesser General Public
      License (LGPL) version 3, which permits free non-commercial use.</li>
  <li><b>Matplotlib</b>, by the Matplotlib Development Team, is used under the
      Matplotlib License (a BSD-compatible license).</li>
  <li><b>NumPy</b>, by the NumPy Developers, is used under the BSD 3-Clause License.</li>
  <li><b>Folium</b>, by the Python Visualization team, is used under the MIT License.</li>
  <li><b>OpenLayers</b>, used for point and label map layers, is released under the
      2-Clause BSD License.</li>
  <li><b>Map base layers</b> are provided by OpenStreetMap contributors under the
      Open Database License (ODbL).</li>
  <li><b>piexif</b>, by hMatoba, is used under the MIT License.</li>
  <li><b>natsort</b>, by Seth M. Morton, is used under the MIT License.</li>
  <li><b>SoundFile</b>, by Bastian Bechtold, used to read audio recordings, is
      licensed under the BSD 3-Clause License. It bundles <b>libsndfile</b>, by
      Erik de Castro Lopo, used under the GNU Lesser General Public License (LGPL)
      version 2.1.</li>
  <li><b>python-soxr</b>, by Dofuuz, used for high-quality audio resampling, is
      licensed under the GNU Lesser General Public License (LGPL) version 2.1. It
      bundles <b>libsoxr</b>, by Rob Sykes.</li>
  <li><b>PyInstaller</b>, by the PyInstaller Development Team, is licensed under the
      GPL with a special exception that permits bundling of non-GPL applications.</li>
</ul>
</body>
</html>"""

        from PySide6.QtGui import QColor
        self._aboutExternalPage = _ExternalLinkPage(self.webView)
        self.webView.setPage(self._aboutExternalPage)
        self.webView.page().setBackgroundColor(QColor("#1e1f26"))
        self.webView.setHtml(html)

        self.setWindowTitle("About Yearbirder")

        return(True)


    def loadUserGuide(self):

        self.title = "User Guide"
        self.contentType = "User Guide"
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        guide_path = os.path.join(base_path, "guide", "guide_Yearbirder.html")
        self._guideExternalPage = _ExternalLinkPage(self.webView)
        self.webView.setPage(self._guideExternalPage)
        self.webView.load(QUrl.fromLocalFile(guide_path))
        self.resizeMe()
        self.scaleMe()
        self.setWindowTitle("User Guide")
        return True


    def LoadWebPage(self,  url):
#         QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        self.webView.load(QUrl(url))
        self.resizeMe()
        self.scaleMe()
        
    def LoadFinished(self):
#         QApplication.restoreOverrideCursor()
        return()

        
    def LoadLocationsMap(self, filter):

        import folium
        import json
        import tempfile

        self.title = "Location Map"
        self.contentType = "Map"
        self.filter = filter

        mapWidth  = self.frameGeometry().width()  - 10
        mapHeight = self.frameGeometry().height() - 35
        self.scrollArea.setGeometry(5, 27, mapWidth + 2, mapHeight + 2)
        self.webView.setGeometry(5, 27, mapWidth + 2, mapHeight + 2)

        locations = self.mdiParent.db.GetLocations(filter)
        if len(locations) == 0:
            return False

        coordinatesDict = defaultdict()
        for l in locations:
            coordinatesDict[l] = self.mdiParent.db.GetLocationCoordinates(l)

        # Build species per location from filtered sightings.
        # Use dict-as-ordered-set so insertion order (= eBird taxonomic order) is preserved.
        sightings = self.mdiParent.db.GetSightings(filter)
        location_species = defaultdict(dict)
        for s in sightings:
            location_species[s["location"]][s["commonName"]] = None
        species_counts = {loc: len(sp) for loc, sp in location_species.items()}

        location_map = folium.Map(tiles="CartoDB Voyager")

        # Build tooltip HTML for each location; stored in a JS dict for
        # the custom positioned tooltip (not folium.Tooltip, which can't be
        # told which side of the map to appear on).
        tip_data = {}
        points = []
        for name, coords in coordinatesDict.items():
            lat, lon = float(coords[0]), float(coords[1])
            points.append([lat, lon])
            n_species = species_counts.get(name, 0)
            radius = 8
            sp_sorted = list(location_species.get(name, {}).keys())
            sp_lines = "".join(f"<br>&nbsp;&nbsp;{sp}" for sp in sp_sorted[:25])
            if len(sp_sorted) > 25:
                sp_lines += f"<br>&nbsp;&nbsp;(+{len(sp_sorted) - 25} more)"
            tip_data[name] = f"<b>{name}</b><br>{n_species} species{sp_lines}"
            marker = folium.CircleMarker(
                location=[lat, lon],
                radius=radius,
                color="#000000",
                weight=1,
                fill=True,
                fill_color=CHART_PRIMARY,
                fill_opacity=0.85,
            )
            # Store the exact location name on the layer for click handling
            marker.options["locationName"] = name
            marker.add_to(location_map)

        tip_data_json = json.dumps(tip_data, ensure_ascii=False)

        lats = [p[0] for p in points]
        lons  = [p[1] for p in points]
        if len(points) == 1:
            pad = 0.001  # tiny non-degenerate box; max_zoom caps the result at ~street level
            location_map.fit_bounds(
                [[lats[0] - pad, lons[0] - pad], [lats[0] + pad, lons[0] + pad]],
                max_zoom=13,
            )
        else:
            location_map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], max_zoom=15)

        # --- QWebChannel: wire up Python ↔ JS bridge ---
        self._mapBridge = MapBridge(self)
        channel = QWebChannel(self.webView.page())
        channel.registerObject("bridge", self._mapBridge)
        self.webView.page().setWebChannel(channel)

        # Read qwebchannel.js from Qt resources
        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        # Find the Leaflet map variable name Folium assigned (e.g. "map_a1b2c3")
        import re
        html = location_map.get_root().render()
        map_var_match = re.search(r'var\s+(map_[a-zA-Z0-9_]+)\s*=\s*L\.map', html)
        map_var = map_var_match.group(1) if map_var_match else "map"

        # JS injected into the page: set up channel, click handlers, and a
        # custom positioned tooltip div that flips left/right based on which
        # half of the map the marker sits in.
        inject_js = f"""
<script>
{qwc_js}
document.addEventListener("DOMContentLoaded", function() {{

    // Custom tooltip div — styled to match the app's dark theme.
    var tipDiv = document.createElement('div');
    tipDiv.style.cssText = (
        'position:fixed; display:none; pointer-events:none; z-index:9999;' +
        'background:#252730; color:#e2e4ec; border:1px solid {CHART_PRIMARY};' +
        'border-radius:6px; padding:6px 10px; font-size:12px;' +
        'max-width:300px; line-height:1.5;'
    );
    document.body.appendChild(tipDiv);

    var tipData = {tip_data_json};

    new QWebChannel(qt.webChannelTransport, function(channel) {{
        window.bridge = channel.objects.bridge;
        {map_var}.eachLayer(function(layer) {{
            if (layer.options && layer.options.locationName) {{
                var name = layer.options.locationName;
                layer.on('click', function(e) {{
                    window.bridge.locationClicked(name);
                }});
                layer.on('mouseover', function(e) {{
                    layer.setStyle({{color: '#ff8800', weight: 2}});
                    var html = tipData[name];
                    if (!html) return;
                    tipDiv.innerHTML = html;
                    tipDiv.style.display = 'block';

                    // Marker position in map-container pixel coords.
                    var mapCont = {map_var}.getContainer();
                    var mapRect = mapCont.getBoundingClientRect();
                    var pt = {map_var}.latLngToContainerPoint(e.target.getLatLng());

                    var GAP   = 12;
                    var tipW  = tipDiv.offsetWidth;
                    var tipH  = tipDiv.offsetHeight;

                    // Flip left when marker is in the right half of the map.
                    var absX;
                    if (pt.x > mapRect.width / 2) {{
                        absX = mapRect.left + pt.x - tipW - GAP;
                    }} else {{
                        absX = mapRect.left + pt.x + GAP;
                    }}

                    // Centre vertically on the marker; clamp to viewport.
                    var absY = mapRect.top + pt.y - tipH / 2;
                    absY = Math.max(GAP, Math.min(absY, window.innerHeight - tipH - GAP));

                    tipDiv.style.left = absX + 'px';
                    tipDiv.style.top  = absY + 'px';
                }});
                layer.on('mouseout', function(e) {{
                    layer.setStyle({{color: '#000000', weight: 1}});
                    tipDiv.style.display = 'none';
                }});
            }}
        }});
    }});
}});
</script>
"""
        html = html.replace("</body>", inject_js + self._satellite_toggle_js() + "</body>")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))

        self._buildFilterTitle(filter, "Map", count=len(coordinatesDict))

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_map_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon)

        return True


    def _buildFilterTitle(self, filter, prefix, count=None, countUnit=""):
        """Build and set the MDI child window title from a filter and a content-type prefix.

        Delegates title construction to filter.buildWindowTitle(), then stores the
        result in self.title (used by showLoadProgress during page load) and applies
        it as the visible window title.
        """
        self.title = filter.buildWindowTitle(prefix, self.mdiParent.db, count=count, countUnit=countUnit)
        self.setWindowTitle(self.title)


    def _lerp_orange(self, value, max_value):
        """Return a hex color across a 3-stop yellow → orange → deep red gradient.

        Uses a square-root scale for good spread across skewed distributions.
        Blue stays at zero throughout to maintain full saturation at every shade.
        Stop 1 (t=0.0): #ffff6e (light yellow)
        Stop 2 (t=0.5): #ff6600 (vivid orange)
        Stop 3 (t=1.0): #880000 (deep dark red)
        """
        if value == 0 or max_value == 0:
            return '#e8e8e8'
        import math
        t = min(math.sqrt(value / max_value), 1.0)
        if t < 0.5:
            s = t * 2                          # 0 → 1 across first half
            r = 255
            g = int(255 + s * (102 - 255))     # 255 → 102
            b = int(110 * (1 - s))             # 110 →   0  (lightens yellow, fades out by orange)
        else:
            s = (t - 0.5) * 2                  # 0 → 1 across second half
            r = int(255 + s * (136 - 255))     # 255 → 136
            g = int(102 + s * (  0 - 102))     # 102 →   0
            b = 0
        return f'#{r:02x}{g:02x}{b:02x}'


    def _satellite_toggle_js(self):
        return satellite_toggle_js()


    def _doToggleFullScreen(self):
        from PySide6.QtGui import QShortcut, QKeySequence
        mainWindow = self.mdiParent
        if not mainWindow.isFullScreen():
            self.showMaximized()
            self.setWindowFlags(Qt.FramelessWindowHint)
            mainWindow.dckFilter.setVisible(False)
            mainWindow.dckMediaFilter.setVisible(False)
            mainWindow.menuBar.setVisible(False)
            mainWindow.toolBar.setVisible(False)
            mainWindow.statusBar.setVisible(False)
            mainWindow.showFullScreen()
            self._escShortcut = QShortcut(QKeySequence(Qt.Key_Escape), mainWindow)
            self._escShortcut.activated.connect(self._doToggleFullScreen)
            self.webView.page().runJavaScript(
                "var b=document.getElementById('_fs_toggle_btn');if(b)b.textContent='Exit Full Screen';"
            )
        else:
            if hasattr(self, '_escShortcut') and self._escShortcut:
                self._escShortcut.deleteLater()
                self._escShortcut = None
            mainWindow.dckFilter.setVisible(True)
            mainWindow.dckMediaFilter.setVisible(True)
            mainWindow.menuBar.setVisible(True)
            mainWindow.toolBar.setVisible(True)
            mainWindow.statusBar.setVisible(True)
            self.setWindowFlags(Qt.SubWindow)
            mainWindow.showMaximized()
            self.showNormal()
            self.webView.page().runJavaScript(
                "var b=document.getElementById('_fs_toggle_btn');if(b)b.textContent='Full Screen';"
            )
            QApplication.restoreOverrideCursor()


    def _setup_choropleth_channel(self, html, location_type, tip_data_json="{}", mode='species'):
        """Register a ChoroplethBridge on the page and inject click/tooltip JS.

        Each GeoJSON feature whose properties contain a non-empty 'clickKey'
        will open a species-list window (mode='species') or checklists window
        (mode='checklists') when clicked.  Features with a 'tipKey' property
        get a custom positioned tooltip that shows species or dates dynamically
        limited to the available viewport height.

        tip_data_json  JSON string mapping tipKey → {"hdr": header_html,
                       "sp": [items_in_order]}.  Pass "{}" for no tooltips.
        """
        import re

        self._choroplethBridge = ChoroplethBridge(self, location_type, mode=mode)
        channel = QWebChannel(self.webView.page())
        channel.registerObject("bridge", self._choroplethBridge)
        self.webView.page().setWebChannel(channel)

        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        map_var_match = re.search(r'var\s+(map_[a-zA-Z0-9_]+)\s*=\s*L\.map', html)
        map_var = map_var_match.group(1) if map_var_match else "map"

        inject_js = f"""
<script>
{qwc_js}
document.addEventListener("DOMContentLoaded", function() {{

    // Custom tooltip div — dark theme matching the app.
    var tipDiv = document.createElement('div');
    tipDiv.style.cssText = (
        'position:fixed; display:none; pointer-events:none; z-index:9999;' +
        'background:#252730; color:#e2e4ec; border:1px solid {CHART_PRIMARY};' +
        'border-radius:6px; padding:6px 10px; font-size:12px;' +
        'max-width:320px; line-height:1.5;'
    );
    document.body.appendChild(tipDiv);

    var tipData = {tip_data_json};
    var LINE_H  = 20;   // approximate pixels per species line

    function showTip(e, props) {{
        var entry = tipData[props.tipKey];
        if (!entry) return;

        // Dynamically limit species list to fit 80 % of viewport height.
        var maxLines = Math.max(3, Math.floor((window.innerHeight * 0.80 - 50) / LINE_H));
        var sp    = entry.sp || [];
        var shown = Math.min(sp.length, maxLines);
        var html  = entry.hdr;
        for (var i = 0; i < shown; i++) {{
            html += '<br>&nbsp;&nbsp;' + sp[i];
        }}
        if (sp.length > shown) {{
            html += '<br>&nbsp;&nbsp;(+' + (sp.length - shown) + ' more)';
        }}
        tipDiv.innerHTML = html;
        tipDiv.style.display = 'block';

        // Smart left/right positioning: flip when cursor is right of map centre.
        var mapCont = {map_var}.getContainer();
        var mapRect = mapCont.getBoundingClientRect();
        var cx = e.originalEvent.clientX;
        var cy = e.originalEvent.clientY;
        var GAP  = 12;
        var tipW = tipDiv.offsetWidth;
        var tipH = tipDiv.offsetHeight;

        var absX = (cx > mapRect.left + mapRect.width / 2)
            ? cx - tipW - GAP
            : cx + GAP;
        absX = Math.max(GAP, Math.min(absX, window.innerWidth - tipW - GAP));

        var absY = cy - tipH / 2;
        absY = Math.max(GAP, Math.min(absY, window.innerHeight - tipH - GAP));

        tipDiv.style.left = absX + 'px';
        tipDiv.style.top  = absY + 'px';
    }}

    new QWebChannel(qt.webChannelTransport, function(channel) {{
        window.bridge = channel.objects.bridge;
        {map_var}.eachLayer(function(layer) {{
            if (layer.eachLayer) {{
                layer.eachLayer(function(featureLayer) {{
                    if (featureLayer.feature && featureLayer.feature.properties) {{
                        var props = featureLayer.feature.properties;
                        if (props.tipKey) {{
                            featureLayer.on('mousemove', function(e) {{ showTip(e, props); }});
                            featureLayer.on('mouseout',  function()  {{ tipDiv.style.display = 'none'; }});
                        }}
                        if (props.clickKey) {{
                            featureLayer.getElement && featureLayer.getElement() &&
                                (featureLayer.getElement().style.cursor = 'pointer');
                            featureLayer.on('click', function() {{
                                window.bridge.regionClicked(props.clickKey);
                            }});
                        }}
                    }}
                }});
            }}
        }});
    }});
}});
</script>
"""
        return html.replace("</body>", inject_js + "</body>")


    def loadChoroplethUSStates(self, filter, mode='species'):

        from copy import deepcopy
        import folium
        import json

        self.filter = deepcopy(filter)

        minimalSightingList = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)
        cf = self.mdiParent.db.CompileFilter(filter)

        stateDict = defaultdict()
        for s in minimalSightingList:
            if s["country"] == "US":
                if self.mdiParent.db.TestSightingCompiled(s, cf):
                    key = s["state"][3:5]
                    if key not in stateDict:
                        stateDict[key] = []
                    stateDict[key].append(s)

        if len(stateDict) == 0:
            return False

        stateTotals = defaultdict()
        stateTipItems = {}
        largestTotal = 0
        if mode == 'checklists':
            self.title = "US States Choropleth – By Checklists"
            for state, sightings in stateDict.items():
                cl_dates = {}
                for s in sightings:
                    cl_dates[s["checklistID"]] = s["date"]
                dates_sorted = sorted(cl_dates.values(), reverse=True)
                stateTotals[state] = len(cl_dates)
                stateTipItems[state] = dates_sorted
                if stateTotals[state] > largestTotal:
                    largestTotal = stateTotals[state]
        else:
            self.title = "US States Choropleth"
            for state, sightings in stateDict.items():
                sp_ordered = {}
                for s in sightings:
                    commonName = s["commonName"]
                    if "/" not in commonName and "sp." not in commonName and " x " not in commonName:
                        sp_ordered[commonName] = None
                stateTotals[state] = len(sp_ordered)
                stateTipItems[state] = list(sp_ordered.keys())
                if stateTotals[state] > largestTotal:
                    largestTotal = stateTotals[state]

        geo_file = self.mdiParent.db.state_geo

        tip_data = {}
        for f in geo_file["features"]:
            sid = f["id"]
            n = stateTotals.get(sid, 0)
            f["properties"]["speciesTotal"] = n
            if n > 0:
                f["properties"]["clickKey"] = "US-" + sid
                f["properties"]["tipKey"]   = sid
                state_name = f["properties"].get("name", sid)
                if mode == 'checklists':
                    tip_data[sid] = {
                        "hdr": f"<b>{state_name}</b><br>{sid}  ·  {n} checklists",
                        "sp":  stateTipItems.get(sid, []),
                    }
                else:
                    tip_data[sid] = {
                        "hdr": f"<b>{state_name}</b><br>{sid}  ·  {n} species",
                        "sp":  stateTipItems.get(sid, []),
                    }
            else:
                stateTotals[sid] = 0
                f["properties"].pop("clickKey", None)
                f["properties"].pop("tipKey",   None)

        state_map = folium.Map(location=[39.5, -98.3], zoom_start=4, tiles="CartoDB Voyager")

        folium.GeoJson(
            geo_file,
            style_function=lambda feature: {
                'fillColor': self._lerp_orange(stateTotals[feature['id']], largestTotal),
                'color': 'black',
                'weight': .2,
                'fillOpacity': .8,
                },
            highlight_function=lambda feature: {
                'color': CHART_PRIMARY, 'weight': 2, 'fillOpacity': .95,
                },
            ).add_to(state_map)

        folium.LayerControl().add_to(state_map)

        import tempfile
        html = state_map.get_root().render()
        html = self._setup_choropleth_channel(html, "State", json.dumps(tip_data, ensure_ascii=False), mode=mode)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name
        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        count = sum(1 for v in stateTotals.values() if v > 0)
        self._buildFilterTitle(filter, self.title, count=count, countUnit="States")

        return True


    def loadChoroplethCanadaProvinces(self, filter, mode='species'):

        from copy import deepcopy
        import folium
        import json

        self.filter = deepcopy(filter)

        provDict = defaultdict()
        minimalSightingList = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)
        cf = self.mdiParent.db.CompileFilter(filter)

        for s in minimalSightingList:
            if s["country"] == "CA":
                if self.mdiParent.db.TestSightingCompiled(s, cf):
                    provCode = s["state"][3:5]
                    if provCode not in provDict:
                        provDict[provCode] = []
                    provDict[provCode].append(s)

        if len(provDict) == 0:
            return False

        provTotals = defaultdict()
        provTipItems = {}
        largestTotal = 0
        if mode == 'checklists':
            self.title = "Canada Provinces Choropleth – By Checklists"
            for prov, sightings in provDict.items():
                cl_dates = {}
                for s in sightings:
                    cl_dates[s["checklistID"]] = s["date"]
                dates_sorted = sorted(cl_dates.values(), reverse=True)
                provTotals[prov] = len(cl_dates)
                provTipItems[prov] = dates_sorted
                if provTotals[prov] > largestTotal:
                    largestTotal = provTotals[prov]
        else:
            self.title = "Canada Provinces Choropleth"
            for prov, sightings in provDict.items():
                sp_ordered = {}
                for s in sightings:
                    commonName = s["commonName"]
                    if "/" not in commonName and "sp." not in commonName and " x " not in commonName:
                        sp_ordered[commonName] = None
                provTotals[prov] = len(sp_ordered)
                provTipItems[prov] = list(sp_ordered.keys())
                if provTotals[prov] > largestTotal:
                    largestTotal = provTotals[prov]

        geo_file = self.mdiParent.db.ca_province_geo

        tip_data = {}
        for f in geo_file["features"]:
            pid = f["id"]
            n = provTotals.get(pid, 0)
            f["properties"]["speciesTotal"] = n
            if n > 0:
                f["properties"]["clickKey"] = "CA-" + pid
                f["properties"]["tipKey"]   = pid
                prov_name = f["properties"].get("name", pid)
                if mode == 'checklists':
                    tip_data[pid] = {
                        "hdr": f"<b>{prov_name}</b><br>{n} checklists",
                        "sp":  provTipItems.get(pid, []),
                    }
                else:
                    tip_data[pid] = {
                        "hdr": f"<b>{prov_name}</b><br>{n} species",
                        "sp":  provTipItems.get(pid, []),
                    }
            else:
                provTotals[pid] = 0
                f["properties"].pop("clickKey", None)
                f["properties"].pop("tipKey",   None)

        prov_map = folium.Map(location=[62, -96], zoom_start=3, tiles="CartoDB Voyager")

        folium.GeoJson(
            geo_file,
            style_function=lambda feature: {
                'fillColor': self._lerp_orange(provTotals[feature['id']], largestTotal),
                'color': 'black',
                'weight': .2,
                'fillOpacity': .8,
                },
            highlight_function=lambda feature: {
                'color': CHART_PRIMARY, 'weight': 2, 'fillOpacity': .95,
                },
            ).add_to(prov_map)

        folium.LayerControl().add_to(prov_map)

        import tempfile
        html = prov_map.get_root().render()
        html = self._setup_choropleth_channel(html, "State", json.dumps(tip_data, ensure_ascii=False), mode=mode)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name
        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        count = sum(1 for v in provTotals.values() if v > 0)
        self._buildFilterTitle(filter, self.title, count=count, countUnit="Provinces")

        return True

    def loadChoroplethIndiaStates(self, filter, mode='species'):

        from copy import deepcopy
        import folium
        import json

        self.filter = deepcopy(filter)

        stateDict = defaultdict()
        minimalSightingList = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)
        cf = self.mdiParent.db.CompileFilter(filter)

        for s in minimalSightingList:
            if s["country"] == "IN":
                if self.mdiParent.db.TestSightingCompiled(s, cf):
                    stateCode = s["state"]
                    if stateCode not in stateDict:
                        stateDict[stateCode] = []
                    stateDict[stateCode].append(s)

        if len(stateDict) == 0:
            return False

        stateTotals = defaultdict()
        stateTipItems = {}
        largestTotal = 0
        if mode == 'checklists':
            self.title = "India States Choropleth – By Checklists"
            for state, sightings in stateDict.items():
                cl_dates = {}
                for s in sightings:
                    cl_dates[s["checklistID"]] = s["date"]
                dates_sorted = sorted(cl_dates.values(), reverse=True)
                stateTotals[state] = len(cl_dates)
                stateTipItems[state] = dates_sorted
                if stateTotals[state] > largestTotal:
                    largestTotal = stateTotals[state]
        else:
            self.title = "India States Choropleth"
            for state, sightings in stateDict.items():
                sp_ordered = {}
                for s in sightings:
                    commonName = s["commonName"]
                    if "/" not in commonName and "sp." not in commonName and " x " not in commonName:
                        sp_ordered[commonName] = None
                stateTotals[state] = len(sp_ordered)
                stateTipItems[state] = list(sp_ordered.keys())
                if stateTotals[state] > largestTotal:
                    largestTotal = stateTotals[state]

        geo_file = self.mdiParent.db.in_state_geo

        tip_data = {}
        for f in geo_file["features"]:
            sid = f["id"]
            n = stateTotals.get(sid, 0)
            f["properties"]["speciesTotal"] = n
            if n > 0:
                f["properties"]["clickKey"] = sid
                f["properties"]["tipKey"]   = sid
                state_name = f["properties"].get("name", sid)
                if mode == 'checklists':
                    tip_data[sid] = {
                        "hdr": f"<b>{state_name}</b><br>{n} checklists",
                        "sp":  stateTipItems.get(sid, []),
                    }
                else:
                    tip_data[sid] = {
                        "hdr": f"<b>{state_name}</b><br>{n} species",
                        "sp":  stateTipItems.get(sid, []),
                    }
            else:
                stateTotals[sid] = 0
                f["properties"].pop("clickKey", None)
                f["properties"].pop("tipKey",   None)

        state_map = folium.Map(location=[22, 80], zoom_start=4, tiles="CartoDB Voyager")

        folium.GeoJson(
            geo_file,
            style_function=lambda feature: {
                'fillColor': self._lerp_orange(stateTotals[feature['id']], largestTotal),
                'color': 'black',
                'weight': .2,
                'fillOpacity': .8,
                },
            highlight_function=lambda feature: {
                'color': CHART_PRIMARY, 'weight': 2, 'fillOpacity': .95,
                },
            ).add_to(state_map)

        folium.LayerControl().add_to(state_map)

        import tempfile
        html = state_map.get_root().render()
        html = self._setup_choropleth_channel(html, "State", json.dumps(tip_data, ensure_ascii=False), mode=mode)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name
        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        count = sum(1 for v in stateTotals.values() if v > 0)
        self._buildFilterTitle(filter, self.title, count=count, countUnit="States")

        return True

    def loadChoroplethGBCounties(self, filter, mode='species'):

        from copy import deepcopy
        import folium
        import json

        self.filter = deepcopy(filter)

        countyDict = defaultdict()
        minimalSightingList = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)
        cf = self.mdiParent.db.CompileFilter(filter)

        for s in minimalSightingList:
            if s["country"] == "GB":
                if self.mdiParent.db.TestSightingCompiled(s, cf):
                    county = s.get("county", "")
                    if county != "":
                        countyName = county.split(" (")[0].strip()
                        if countyName not in countyDict:
                            countyDict[countyName] = []
                        countyDict[countyName].append(s)

        if len(countyDict) == 0:
            return False

        countyTotals = defaultdict()
        countyTipItems = {}
        largestTotal = 0
        if mode == 'checklists':
            self.title = "Great Britain Counties Choropleth – By Checklists"
            for county, sightings in countyDict.items():
                cl_dates = {}
                for s in sightings:
                    cl_dates[s["checklistID"]] = s["date"]
                dates_sorted = sorted(cl_dates.values(), reverse=True)
                countyTotals[county] = len(cl_dates)
                countyTipItems[county] = dates_sorted
                if countyTotals[county] > largestTotal:
                    largestTotal = countyTotals[county]
        else:
            self.title = "Great Britain Counties Choropleth"
            for county, sightings in countyDict.items():
                sp_ordered = {}
                for s in sightings:
                    commonName = s["commonName"]
                    if "/" not in commonName and "sp." not in commonName and " x " not in commonName:
                        sp_ordered[commonName] = None
                countyTotals[county] = len(sp_ordered)
                countyTipItems[county] = list(sp_ordered.keys())
                if countyTotals[county] > largestTotal:
                    largestTotal = countyTotals[county]

        geo_file = self.mdiParent.db.gb_county_geo

        tip_data = {}
        for f in geo_file["features"]:
            ename = f["properties"].get("ebird_name", f["properties"]["name"])
            n = countyTotals.get(ename, 0)
            f["properties"]["speciesTotal"] = n
            if n > 0:
                f["properties"]["clickKey"] = ename
                f["properties"]["tipKey"]   = ename
                if mode == 'checklists':
                    tip_data[ename] = {
                        "hdr": f"<b>{ename}</b><br>{n} checklists",
                        "sp":  countyTipItems.get(ename, []),
                    }
                else:
                    tip_data[ename] = {
                        "hdr": f"<b>{ename}</b><br>{n} species",
                        "sp":  countyTipItems.get(ename, []),
                    }
            else:
                countyTotals[ename] = 0
                f["properties"].pop("clickKey", None)
                f["properties"].pop("tipKey",   None)

        county_map = folium.Map(location=[54, -2], zoom_start=5, tiles="CartoDB Voyager")

        folium.GeoJson(
            geo_file,
            style_function=lambda feature: {
                'fillColor': self._lerp_orange(
                    countyTotals.get(feature['properties'].get('ebird_name', feature['properties']['name']), 0),
                    largestTotal),
                'color': 'black',
                'weight': .2,
                'fillOpacity': .8,
                },
            highlight_function=lambda feature: {
                'color': CHART_PRIMARY, 'weight': 2, 'fillOpacity': .95,
                },
            ).add_to(county_map)

        folium.LayerControl().add_to(county_map)

        import tempfile
        html = county_map.get_root().render()
        html = self._setup_choropleth_channel(html, "County", json.dumps(tip_data, ensure_ascii=False), mode=mode)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name
        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        count = sum(1 for v in countyTotals.values() if v > 0)
        self._buildFilterTitle(filter, self.title, count=count, countUnit="Counties")

        return True

    def loadChoroplethUSCounties(self, filter, mode='species'):

        from copy import deepcopy
        import folium
        import json

        self.filter = deepcopy(filter)

        countyDict = defaultdict()
        minimalSightingList = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)
        cf = self.mdiParent.db.CompileFilter(filter)

        for s in minimalSightingList:
            if s["country"] == "US" and s["state"] not in ["US-HI", "US-AK"]:
                if "countyCode" in s.keys():
                    if self.mdiParent.db.TestSightingCompiled(s, cf):
                        key = s["countyCode"]
                        if key not in countyDict:
                            countyDict[key] = []
                        countyDict[key].append(s)

        if len(countyDict) == 0:
            return False

        countyTotals = defaultdict()
        countyTipItems = {}
        largestTotal = 0
        if mode == 'checklists':
            self.title = "US Lower 48 Counties Choropleth – By Checklists"
            for county, sightings in countyDict.items():
                cl_dates = {}
                for s in sightings:
                    cl_dates[s["checklistID"]] = s["date"]
                dates_sorted = sorted(cl_dates.values(), reverse=True)
                countyTotals[county] = len(cl_dates)
                countyTipItems[county] = dates_sorted
                if countyTotals[county] > largestTotal:
                    largestTotal = countyTotals[county]
        else:
            self.title = "US Lower 48 Counties Choropleth"
            for county, sightings in countyDict.items():
                sp_ordered = {}
                for s in sightings:
                    commonName = s["commonName"]
                    if "/" not in commonName and "sp." not in commonName and " x " not in commonName:
                        sp_ordered[commonName] = None
                countyTotals[county] = len(sp_ordered)
                countyTipItems[county] = list(sp_ordered.keys())
                if countyTotals[county] > largestTotal:
                    largestTotal = countyTotals[county]

        # Load the shape of the zone (US counties)
        geo_file = self.mdiParent.db.county_geo

        tip_data = {}
        for f in geo_file["features"]:
            cid = f["id"]
            n = countyTotals.get(cid, 0)
            f["properties"]["speciesTotal"] = n
            if n > 0:
                county_name  = f["properties"].get("name", cid)
                state_abbrev = f["properties"].get("state", "")
                f["properties"]["clickKey"] = countyDict[cid][0]["county"]
                f["properties"]["tipKey"]   = cid
                if mode == 'checklists':
                    tip_data[cid] = {
                        "hdr": f"<b>{county_name}</b><br>{state_abbrev}  ·  {n} checklists",
                        "sp":  countyTipItems.get(cid, []),
                    }
                else:
                    tip_data[cid] = {
                        "hdr": f"<b>{county_name}</b><br>{state_abbrev}  ·  {n} species",
                        "sp":  countyTipItems.get(cid, []),
                    }
            else:
                countyTotals[cid] = 0
                f["properties"].pop("clickKey", None)
                f["properties"].pop("tipKey",   None)

        county_map = folium.Map(location=[39.5, -98.3], zoom_start=4, tiles="CartoDB Voyager")

        folium.GeoJson(
            geo_file,
            style_function=lambda feature: {
                'fillColor': self._lerp_orange(countyTotals[feature['id']], largestTotal),
                'color': 'black',
                'weight': 1,
                'fillOpacity': .8,
                'nan_fill_color': 'white'
                },
            highlight_function=lambda feature: {
                'color': CHART_PRIMARY, 'weight': 2, 'fillOpacity': .95,
                },
            ).add_to(county_map)

        folium.LayerControl().add_to(county_map)

        # Note: the county GeoJSON embeds ~1.2MB of data in a single JS line, which causes
        # QWebEngineView.setHtml() to silently produce a blank page when many counties have
        # non-zero counts (as in the no-filter case). Writing to a temp file and
        # loading via setUrl() bypasses this Qt internal content-handling limitation.
        import tempfile
        html = county_map.get_root().render()
        html = self._setup_choropleth_channel(html, "County", json.dumps(tip_data, ensure_ascii=False), mode=mode)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        count = sum(1 for v in countyTotals.values() if v > 0)
        self._buildFilterTitle(filter, self.title, count=count, countUnit="Counties")

        return True


    def loadChoroplethWorldCountries(self, filter, mode='species'):

        from copy import deepcopy
        import folium
        import json

        self.filter = deepcopy(filter)

        countryDict = defaultdict()
        minimalSightingList = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)
        cf = self.mdiParent.db.CompileFilter(filter)

        for s in minimalSightingList:
            if self.mdiParent.db.TestSightingCompiled(s, cf):
                key = s["country"]
                if key not in countryDict:
                    countryDict[key] = []
                countryDict[key].append(s)

        if len(countryDict) == 0:
            return False

        countryTotals = defaultdict()
        countryTipItems = {}
        largestTotal = 0
        if mode == 'checklists':
            self.title = "World Choropleth – By Checklists"
            for country, sightings in countryDict.items():
                cl_dates = {}
                for s in sightings:
                    cl_dates[s["checklistID"]] = s["date"]
                dates_sorted = sorted(cl_dates.values(), reverse=True)
                countryTotals[country] = len(cl_dates)
                countryTipItems[country] = dates_sorted
                if countryTotals[country] > largestTotal:
                    largestTotal = countryTotals[country]
        else:
            self.title = "World Choropleth"
            for country, sightings in countryDict.items():
                sp_ordered = {}
                for s in sightings:
                    commonName = s["commonName"]
                    if "/" not in commonName and "sp." not in commonName and " x " not in commonName:
                        sp_ordered[commonName] = None
                countryTotals[country] = len(sp_ordered)
                countryTipItems[country] = list(sp_ordered.keys())
                if countryTotals[country] > largestTotal:
                    largestTotal = countryTotals[country]

        geo_file = self.mdiParent.db.country_geo

        tip_data = {}
        for f in geo_file["features"]:
            cid = f["id"]
            n = countryTotals.get(cid, 0)
            f["properties"]["speciesTotal"] = n
            if n > 0:
                f["properties"]["clickKey"] = cid
                f["properties"]["tipKey"]   = cid
                country_name = f["properties"].get("name", cid)
                if mode == 'checklists':
                    tip_data[cid] = {
                        "hdr": f"<b>{country_name}</b><br>{n} checklists",
                        "sp":  countryTipItems.get(cid, []),
                    }
                else:
                    tip_data[cid] = {
                        "hdr": f"<b>{country_name}</b><br>{n} species",
                        "sp":  countryTipItems.get(cid, []),
                    }
            else:
                countryTotals[cid] = 0
                f["properties"].pop("clickKey", None)
                f["properties"].pop("tipKey",   None)

        choro_map = folium.Map(location=[1, 1], zoom_start=1, tiles="CartoDB Voyager")

        folium.GeoJson(
            geo_file,
            style_function=lambda feature: {
                'fillColor': self._lerp_orange(countryTotals[feature['id']], largestTotal),
                'color': 'black',
                'weight': 1,
                'fillOpacity': .8,
                'nan_fill_color': 'white'
                },
            highlight_function=lambda feature: {
                'color': CHART_PRIMARY, 'weight': 2, 'fillOpacity': .95,
                },
            ).add_to(choro_map)

        folium.LayerControl().add_to(choro_map)

        import tempfile
        html = choro_map.get_root().render()
        html = self._setup_choropleth_channel(html, "Country", json.dumps(tip_data, ensure_ascii=False), mode=mode)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name
        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        count = sum(1 for v in countryTotals.values() if v > 0)
        self._buildFilterTitle(filter, self.title, count=count, countUnit="Countries")

        return True


    def loadLifeListMap(self, filter):
        """Animate lifers appearing on the map in chronological order.

        Each dot = the location where that species was first recorded under the
        current filter.  Dots accumulate as the animation plays.  Color shifts
        from cream (earliest lifer) to deep orange (most recent).

        Uses injected JS rather than TimestampedGeoJson: markers are
        pre-created invisible and revealed one-by-one via setTimeout so that
        dots truly accumulate rather than being controlled by a look-back window.
        """
        from copy import deepcopy
        import folium
        import json
        import tempfile
        from pathlib import Path

        self.title = "Life List Map"
        self.filter = deepcopy(filter)

        # ── Collect lifers ───────────────────────────────────────────────
        # Step 1: species that appear in the filtered sightings
        minimal = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)
        cf = self.mdiParent.db.CompileFilter(filter)

        filtered_species = set()
        for s in minimal:
            if not self.mdiParent.db.TestSightingCompiled(s, cf):
                continue
            name = s.get("commonName", "")
            if "/" in name or "sp." in name or " x " in name:
                continue
            filtered_species.add(name)

        # Step 2 & 3: for each species find the first-ever sighting in the entire
        # database, then keep it only if that life sighting passes the full filter
        # (date range AND location).  This ensures life birds that happened outside
        # the filtered location or period are excluded.
        species_dict = self.mdiParent.db.speciesDict

        lifers = []
        for name in filtered_species:
            if name not in species_dict:
                continue
            first = min(species_dict[name], key=lambda s: (s.get("date", ""), s.get("time", "")))
            if not self.mdiParent.db.TestSightingCompiled(first, cf):
                continue
            try:
                lat = float(first["latitude"])
                lon = float(first["longitude"])
            except (ValueError, TypeError, KeyError):
                continue
            if lat == 0.0 and lon == 0.0:
                continue
            best_img = ""
            if self.mdiParent.db.photoDataFileOpenFlag:
                photos = first.get("photos", [])
                if photos:
                    best = max(photos, key=lambda p: int(p.get("rating", "0") or "0"))
                    fn = best.get("fileName", "")
                    if fn:
                        best_img = Path(fn).as_uri()
            lifers.append({
                "species":  name,
                "date":     first.get("date", ""),
                "location": first.get("location", ""),
                "lat":      lat,
                "lon":      lon,
                "img":      best_img,
            })

        if not lifers:
            return False

        lifers.sort(key=lambda x: x["date"])
        total = len(lifers)

        for i, lifer in enumerate(lifers):
            lifer["color"] = self._lerp_orange(i + 1, total)
            lifer["num"]   = i + 1

        # ── Build base Folium map (tiles only) ───────────────────────────
        lats = [l["lat"] for l in lifers]
        lons = [l["lon"] for l in lifers]

        life_map = folium.Map(
            location=[sum(lats) / total, sum(lons) / total],
            zoom_start=4,
            tiles="CartoDB Voyager",
        )
        life_map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], max_zoom=15)

        lifers_js  = json.dumps(lifers, ensure_ascii=False)

        html = life_map.get_root().render()

        # ── Inject custom animation ───────────────────────────────────────
        # We do NOT use window[mapVarName] because Folium may scope its var
        # differently across versions.  Instead we find the map object by
        # scanning window for the L.Map instance that owns the rendered
        # .leaflet-container div, retrying until Leaflet reports it ready.
        animation = f"""
<style>
#llm-bar {{
    position:absolute; bottom:28px; left:50%; transform:translateX(-50%);
    z-index:1000;
    background:rgba(255,255,255,0.93);
    border-radius:10px;
    box-shadow:0 2px 10px rgba(0,0,0,0.25);
    padding:7px 14px 8px;
    display:flex; flex-direction:column; align-items:stretch; gap:5px;
    font-family:sans-serif; font-size:13px;
    white-space:nowrap; user-select:none;
}}
#llm-controls {{
    display:flex; align-items:center; gap:10px;
}}
#llm-bar button {{
    background:none; border:none; cursor:pointer;
    font-size:17px; padding:0 2px; line-height:1;
}}
#llm-slider {{ width:200px; cursor:pointer; }}
#llm-speed  {{ width:65px;  cursor:pointer; vertical-align:middle; }}
#llm-info   {{ min-width:120px; color:#333; }}
#llm-lifer  {{
    text-align:center; font-size:12px; color:#444;
    min-height:15px; letter-spacing:0.01em;
}}
</style>
<div id="llm-bar">
  <div id="llm-controls">
    <button id="llm-restart" title="Restart">&#9198;</button>
    <button id="llm-play"    title="Play / Pause">&#9654;</button>
    <input  id="llm-slider"  type="range" min="0" max="{total}" value="0">
    <span   id="llm-info">0 / {total} lifers</span>
    <label  title="Animation speed" style="display:flex;align-items:center;gap:4px">
        Slower<input id="llm-speed" type="range" min="0" max="10" value="1">Faster
    </label>
  </div>
  <div id="llm-lifer"></div>
</div>
<script>
(function() {{
    var lifers  = {lifers_js};
    var mkrs    = [];
    var shown   = 0;
    var playing = false;
    var timer   = null;
    var tipDiv  = null;
    var map     = null;
    var DELAYS  = [3000, 2100, 1500, 1080, 770, 550, 390, 280, 200, 140, 100];

    function delayMs() {{
        return DELAYS[parseInt(document.getElementById('llm-speed').value)] || 550;
    }}

    function updateUI() {{
        var idx = Math.max(0, shown - 1);
        document.getElementById('llm-info').textContent = shown + ' / ' + lifers.length + ' lifers';
        document.getElementById('llm-slider').value = shown;
        var liferEl = document.getElementById('llm-lifer');
        if (shown > 0) {{
            var l = lifers[idx];
            liferEl.innerHTML = '<b>' + l.species + '</b> &nbsp;\u00b7&nbsp; ' + l.location + ' &nbsp;\u00b7&nbsp; ' + l.date;
        }} else {{
            liferEl.textContent = '';
        }}
    }}

    function buildTipHtml(lifer) {{
        if (lifer.img) {{
            return (
                '<div style="width:160px; background:#252730;' +
                'border:1px solid {CHART_PRIMARY}; border-radius:6px;' +
                'overflow:hidden; font-family:sans-serif; line-height:1.3;' +
                'box-shadow:0 3px 10px rgba(0,0,0,0.55);">' +
                '<img src="' + lifer.img + '" ' +
                'style="width:160px; height:110px; object-fit:cover; display:block;">' +
                '<div style="padding:4px 6px 5px;">' +
                '<div style="font-size:11px; font-weight:bold; color:#e2e4ec;' +
                'white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">' +
                lifer.species + ' (#' + lifer.num + ')</div>' +
                '<div style="font-size:10px; color:#8b8fa8;' +
                'white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">' +
                lifer.date + '</div>' +
                '<div style="font-size:10px; color:#8b8fa8;' +
                'white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">' +
                lifer.location + '</div>' +
                '</div></div>'
            );
        }}
        return (
            '<div style="background:#252730; color:#e2e4ec;' +
            'border:1px solid {CHART_PRIMARY}; border-radius:6px;' +
            'padding:6px 10px; font-size:12px; max-width:300px;' +
            'line-height:1.5; font-family:sans-serif;">' +
            '<b>' + lifer.species + '</b> (#' + lifer.num + ')' +
            '<br>' + lifer.date + ' · ' + lifer.location +
            '</div>'
        );
    }}

    function showAutoTip(lifer) {{
        if (!tipDiv || !map) return;
        tipDiv.innerHTML = buildTipHtml(lifer);
        tipDiv.style.display = 'block';
        var mapCont = map.getContainer();
        var mapRect = mapCont.getBoundingClientRect();
        var pt  = map.latLngToContainerPoint([lifer.lat, lifer.lon]);
        var GAP = 12;
        var tipW = tipDiv.offsetWidth;
        var tipH = tipDiv.offsetHeight;
        var absX = pt.x > mapRect.width / 2
            ? mapRect.left + pt.x - tipW - GAP
            : mapRect.left + pt.x + GAP;
        var absY = mapRect.top + pt.y - tipH / 2;
        absY = Math.max(GAP, Math.min(absY, window.innerHeight - tipH - GAP));
        tipDiv.style.left = absX + 'px';
        tipDiv.style.top  = absY + 'px';
    }}

    function showUpTo(n) {{
        if (n <= shown) return;
        // Revert the previous "newest" dot from red back to its orange
        if (shown > 0) {{
            mkrs[shown - 1].setStyle({{ fillColor: lifers[shown - 1].color }});
        }}
        // All intermediate new dots get their correct orange immediately
        for (var i = shown; i < n - 1 && i < lifers.length; i++) {{
            mkrs[i].setStyle({{ fillColor: lifers[i].color, fillOpacity:0.85, opacity:1 }});
        }}
        // The newest dot appears in bright red
        if (n <= lifers.length) {{
            mkrs[n - 1].setStyle({{ fillColor:'{CHART_PRIMARY}', fillOpacity:0.95, opacity:1 }});
        }}
        shown = Math.min(n, lifers.length);
        updateUI();
        if (shown > 0) showAutoTip(lifers[shown - 1]);
    }}

    function resetMarkers() {{
        mkrs.forEach(function(m) {{ m.setStyle({{ fillOpacity:0, opacity:0 }}); }});
        shown = 0;
        if (tipDiv) tipDiv.style.display = 'none';
        updateUI();
    }}

    function scheduleStep() {{
        timer = setTimeout(function() {{
            if (!playing) return;
            if (shown < lifers.length) {{ showUpTo(shown + 1); scheduleStep(); }}
            else pause();
        }}, delayMs());
    }}

    function play() {{
        if (shown >= lifers.length) resetMarkers();
        playing = true;
        document.getElementById('llm-play').innerHTML = '&#9646;&#9646;';
        scheduleStep();
    }}

    function pause() {{
        playing = false;
        clearTimeout(timer);
        document.getElementById('llm-play').innerHTML = '&#9654;';
    }}

    document.getElementById('llm-play').onclick    = function() {{ if (playing) pause(); else play(); }};
    document.getElementById('llm-restart').onclick = function() {{ pause(); resetMarkers(); }};
    document.getElementById('llm-slider').oninput  = function() {{ var target = parseInt(this.value); pause(); resetMarkers(); showUpTo(target); }};

    // ── Lock the control bar to its maximum width up front ──
    // Find the lifer with the longest combined text (char count ≈ rendered width proxy),
    // render it into #llm-lifer, force a layout read, then pin min-width.
    function fixBarWidth() {{
        var bar = document.getElementById('llm-bar');
        var liferEl = document.getElementById('llm-lifer');
        var best = lifers.reduce(function(b, l) {{
            var len = l.species.length + l.location.length + l.date.length;
            return len > b.len ? {{len: len, lifer: l}} : b;
        }}, {{len: 0, lifer: null}});
        if (best.lifer) {{
            var l = best.lifer;
            liferEl.innerHTML = '<b>' + l.species + '</b> &nbsp;\u00b7&nbsp; ' + l.location + ' &nbsp;\u00b7&nbsp; ' + l.date;
            bar.style.minWidth = bar.offsetWidth + 'px';
            liferEl.textContent = '';
        }}
    }}
    fixBarWidth();

    // ── Find the Leaflet map, retrying until it is fully initialised ──
    function findMap() {{
        // Folium names the JS var identically to the container div id.
        // Walking window for an L.Map is more version-proof than a hard name.
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {{
            try {{
                var obj = window[keys[i]];
                if (obj && obj instanceof L.Map) return obj;
            }} catch(e) {{}}
        }}
        return null;
    }}

    function init() {{
        map = findMap();
        if (!map) {{ setTimeout(init, 150); return; }}

        tipDiv = document.createElement('div');
        tipDiv.style.cssText = 'position:fixed; display:none; pointer-events:none; z-index:9999;';
        document.body.appendChild(tipDiv);

        lifers.forEach(function(lifer) {{
            var m = L.circleMarker([lifer.lat, lifer.lon], {{
                radius:7, fillColor:lifer.color, color:'#555',
                weight:0.8, fillOpacity:0, opacity:0
            }});
            m.on('mouseover', function(e) {{
                tipDiv.innerHTML = buildTipHtml(lifer);
                tipDiv.style.display = 'block';
                var mapCont = map.getContainer();
                var mapRect = mapCont.getBoundingClientRect();
                var pt = map.latLngToContainerPoint(e.target.getLatLng());
                var GAP = 12;
                var tipW = tipDiv.offsetWidth;
                var tipH = tipDiv.offsetHeight;
                var absX = pt.x > mapRect.width / 2
                    ? mapRect.left + pt.x - tipW - GAP
                    : mapRect.left + pt.x + GAP;
                var absY = mapRect.top + pt.y - tipH / 2;
                absY = Math.max(GAP, Math.min(absY, window.innerHeight - tipH - GAP));
                tipDiv.style.left = absX + 'px';
                tipDiv.style.top  = absY + 'px';
            }});
            m.on('mouseout', function() {{
                tipDiv.style.display = 'none';
            }});
            m.bindPopup(
                lifer.img
                    ? '<div style="font-family:sans-serif">' +
                      '<img src="' + lifer.img + '" style="width:200px;height:140px;' +
                      'object-fit:cover;display:block;border-radius:4px;margin-bottom:6px;">' +
                      '<b>' + lifer.species + '</b><br>' +
                      'Lifer #' + lifer.num + ' \u00b7 ' + lifer.date + '<br>' +
                      lifer.location + '</div>'
                    : '<div style="font-family:sans-serif">' +
                      '<b>' + lifer.species + '</b><br>' +
                      'Lifer #' + lifer.num + ' \u00b7 ' + lifer.date + '<br>' +
                      lifer.location + '</div>'
            );
            m.addTo(map);
            mkrs.push(m);
        }});

        setTimeout(play, 300);
    }}

    init();
}})();
</script>
"""
        html = html.replace("</body>", animation + self._satellite_toggle_js() + "\n</body>")

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        self._buildFilterTitle(filter, "Life List Map", count=total, countUnit="Lifers")

        return True


    def loadFirstSightingsMap(self, filter):
        """Animate first sightings of each species under the current filter.

        Identical in structure to loadLifeListMap but respects the full filter,
        so it can show county firsts, year firsts, etc. rather than life lifers.
        """
        from copy import deepcopy
        from pathlib import Path
        import folium
        import json
        import tempfile

        self.title = "Animated First Sightings"
        self.filter = deepcopy(filter)

        minimal = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)
        cf = self.mdiParent.db.CompileFilter(filter)
        minimal_sorted = sorted(minimal, key=lambda s: (s.get("date", ""), s.get("time", "")))

        seen     = set()
        species  = []
        for s in minimal_sorted:
            if not self.mdiParent.db.TestSightingCompiled(s, cf):
                continue
            name = s.get("commonName", "")
            if "/" in name or "sp." in name or " x " in name:
                continue
            if name in seen:
                continue
            try:
                lat = float(s["latitude"])
                lon = float(s["longitude"])
            except (ValueError, TypeError, KeyError):
                continue
            if lat == 0.0 and lon == 0.0:
                continue
            seen.add(name)
            best_img = ""
            if self.mdiParent.db.photoDataFileOpenFlag:
                photos = s.get("photos", [])
                if photos:
                    best = max(photos, key=lambda p: int(p.get("rating", "0") or "0"))
                    fn = best.get("fileName", "")
                    if fn:
                        best_img = Path(fn).as_uri()
            species.append({
                "species":  name,
                "date":     s.get("date", ""),
                "location": s.get("location", ""),
                "lat":      lat,
                "lon":      lon,
                "img":      best_img,
            })

        if not species:
            return False

        species.sort(key=lambda x: x["date"])
        total = len(species)

        for i, sp in enumerate(species):
            sp["color"] = self._lerp_orange(i + 1, total)
            sp["num"]   = i + 1

        lats = [sp["lat"] for sp in species]
        lons = [sp["lon"] for sp in species]

        fsm_map = folium.Map(
            location=[sum(lats) / total, sum(lons) / total],
            zoom_start=4,
            tiles="CartoDB Voyager",
        )
        fsm_map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], max_zoom=15)

        species_js = json.dumps(species, ensure_ascii=False)
        html = fsm_map.get_root().render()

        animation = f"""
<style>
#fsm-bar {{
    position:absolute; bottom:28px; left:50%; transform:translateX(-50%);
    z-index:1000;
    background:rgba(255,255,255,0.93);
    border-radius:10px;
    box-shadow:0 2px 10px rgba(0,0,0,0.25);
    padding:7px 14px 8px;
    display:flex; flex-direction:column; align-items:stretch; gap:5px;
    font-family:sans-serif; font-size:13px;
    white-space:nowrap; user-select:none;
}}
#fsm-controls {{
    display:flex; align-items:center; gap:10px;
}}
#fsm-bar button {{
    background:none; border:none; cursor:pointer;
    font-size:17px; padding:0 2px; line-height:1;
}}
#fsm-slider {{ width:200px; cursor:pointer; }}
#fsm-speed  {{ width:65px;  cursor:pointer; vertical-align:middle; }}
#fsm-info   {{ min-width:120px; color:#333; }}
#fsm-caption {{
    text-align:center; font-size:12px; color:#444;
    min-height:15px; letter-spacing:0.01em;
}}
</style>
<div id="fsm-bar">
  <div id="fsm-controls">
    <button id="fsm-restart" title="Restart">&#9198;</button>
    <button id="fsm-play"    title="Play / Pause">&#9654;</button>
    <input  id="fsm-slider"  type="range" min="0" max="{total}" value="0">
    <span   id="fsm-info">0 / {total} species</span>
    <label  title="Animation speed" style="display:flex;align-items:center;gap:4px">
        Slower<input id="fsm-speed" type="range" min="0" max="10" value="1">Faster
    </label>
  </div>
  <div id="fsm-caption"></div>
</div>
<script>
(function() {{
    var species = {species_js};
    var mkrs    = [];
    var shown   = 0;
    var playing = false;
    var timer   = null;
    var tipDiv  = null;
    var map     = null;
    var DELAYS  = [3000, 2100, 1500, 1080, 770, 550, 390, 280, 200, 140, 100];

    function delayMs() {{
        return DELAYS[parseInt(document.getElementById('fsm-speed').value)] || 550;
    }}

    function updateUI() {{
        var idx = Math.max(0, shown - 1);
        document.getElementById('fsm-info').textContent = shown + ' / ' + species.length + ' species';
        document.getElementById('fsm-slider').value = shown;
        var capEl = document.getElementById('fsm-caption');
        if (shown > 0) {{
            var s = species[idx];
            capEl.innerHTML = '<b>' + s.species + '</b> &nbsp;·&nbsp; ' + s.location + ' &nbsp;·&nbsp; ' + s.date;
        }} else {{
            capEl.textContent = '';
        }}
    }}

    function buildTipHtml(sp) {{
        if (sp.img) {{
            return (
                '<div style="width:160px; background:#252730;' +
                'border:1px solid {CHART_PRIMARY}; border-radius:6px;' +
                'overflow:hidden; font-family:sans-serif; line-height:1.3;' +
                'box-shadow:0 3px 10px rgba(0,0,0,0.55);">' +
                '<img src="' + sp.img + '" ' +
                'style="width:160px; height:110px; object-fit:cover; display:block;">' +
                '<div style="padding:4px 6px 5px;">' +
                '<div style="font-size:11px; font-weight:bold; color:#e2e4ec;' +
                'white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">' +
                sp.species + ' (#' + sp.num + ')</div>' +
                '<div style="font-size:10px; color:#8b8fa8;' +
                'white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">' +
                sp.date + '</div>' +
                '<div style="font-size:10px; color:#8b8fa8;' +
                'white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">' +
                sp.location + '</div>' +
                '</div></div>'
            );
        }}
        return (
            '<div style="background:#252730; color:#e2e4ec;' +
            'border:1px solid {CHART_PRIMARY}; border-radius:6px;' +
            'padding:6px 10px; font-size:12px; max-width:300px;' +
            'line-height:1.5; font-family:sans-serif;">' +
            '<b>' + sp.species + '</b> (#' + sp.num + ')' +
            '<br>' + sp.date + ' · ' + sp.location +
            '</div>'
        );
    }}

    function showAutoTip(sp) {{
        if (!tipDiv || !map) return;
        tipDiv.innerHTML = buildTipHtml(sp);
        tipDiv.style.display = 'block';
        var mapCont = map.getContainer();
        var mapRect = mapCont.getBoundingClientRect();
        var pt  = map.latLngToContainerPoint([sp.lat, sp.lon]);
        var GAP = 12;
        var tipW = tipDiv.offsetWidth;
        var tipH = tipDiv.offsetHeight;
        var absX = pt.x > mapRect.width / 2
            ? mapRect.left + pt.x - tipW - GAP
            : mapRect.left + pt.x + GAP;
        var absY = mapRect.top + pt.y - tipH / 2;
        absY = Math.max(GAP, Math.min(absY, window.innerHeight - tipH - GAP));
        tipDiv.style.left = absX + 'px';
        tipDiv.style.top  = absY + 'px';
    }}

    function showUpTo(n) {{
        if (n <= shown) return;
        if (shown > 0) {{
            mkrs[shown - 1].setStyle({{ fillColor: species[shown - 1].color }});
        }}
        for (var i = shown; i < n - 1 && i < species.length; i++) {{
            mkrs[i].setStyle({{ fillColor: species[i].color, fillOpacity:0.85, opacity:1 }});
        }}
        if (n <= species.length) {{
            mkrs[n - 1].setStyle({{ fillColor:'{CHART_PRIMARY}', fillOpacity:0.95, opacity:1 }});
        }}
        shown = Math.min(n, species.length);
        updateUI();
        if (shown > 0) showAutoTip(species[shown - 1]);
    }}

    function resetMarkers() {{
        mkrs.forEach(function(m) {{ m.setStyle({{ fillOpacity:0, opacity:0 }}); }});
        shown = 0;
        if (tipDiv) tipDiv.style.display = 'none';
        updateUI();
    }}

    function scheduleStep() {{
        timer = setTimeout(function() {{
            if (!playing) return;
            if (shown < species.length) {{ showUpTo(shown + 1); scheduleStep(); }}
            else pause();
        }}, delayMs());
    }}

    function play() {{
        if (shown >= species.length) resetMarkers();
        playing = true;
        document.getElementById('fsm-play').innerHTML = '&#9646;&#9646;';
        scheduleStep();
    }}

    function pause() {{
        playing = false;
        clearTimeout(timer);
        document.getElementById('fsm-play').innerHTML = '&#9654;';
    }}

    document.getElementById('fsm-play').onclick    = function() {{ if (playing) pause(); else play(); }};
    document.getElementById('fsm-restart').onclick = function() {{ pause(); resetMarkers(); }};
    document.getElementById('fsm-slider').oninput  = function() {{ var target = parseInt(this.value); pause(); resetMarkers(); showUpTo(target); }};

    function fixBarWidth() {{
        var bar = document.getElementById('fsm-bar');
        var capEl = document.getElementById('fsm-caption');
        var best = species.reduce(function(b, s) {{
            var len = s.species.length + s.location.length + s.date.length;
            return len > b.len ? {{len: len, sp: s}} : b;
        }}, {{len: 0, sp: null}});
        if (best.sp) {{
            var s = best.sp;
            capEl.innerHTML = '<b>' + s.species + '</b> &nbsp;·&nbsp; ' + s.location + ' &nbsp;·&nbsp; ' + s.date;
            bar.style.minWidth = bar.offsetWidth + 'px';
            capEl.textContent = '';
        }}
    }}
    fixBarWidth();

    function findMap() {{
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {{
            try {{
                var obj = window[keys[i]];
                if (obj && obj instanceof L.Map) return obj;
            }} catch(e) {{}}
        }}
        return null;
    }}

    function init() {{
        map = findMap();
        if (!map) {{ setTimeout(init, 150); return; }}

        tipDiv = document.createElement('div');
        tipDiv.style.cssText = 'position:fixed; display:none; pointer-events:none; z-index:9999;';
        document.body.appendChild(tipDiv);

        species.forEach(function(sp) {{
            var m = L.circleMarker([sp.lat, sp.lon], {{
                radius:7, fillColor:sp.color, color:'#555',
                weight:0.8, fillOpacity:0, opacity:0
            }});
            m.on('mouseover', function(e) {{
                tipDiv.innerHTML = buildTipHtml(sp);
                tipDiv.style.display = 'block';
                var mapCont = map.getContainer();
                var mapRect = mapCont.getBoundingClientRect();
                var pt = map.latLngToContainerPoint(e.target.getLatLng());
                var GAP = 12;
                var tipW = tipDiv.offsetWidth;
                var tipH = tipDiv.offsetHeight;
                var absX = pt.x > mapRect.width / 2
                    ? mapRect.left + pt.x - tipW - GAP
                    : mapRect.left + pt.x + GAP;
                var absY = mapRect.top + pt.y - tipH / 2;
                absY = Math.max(GAP, Math.min(absY, window.innerHeight - tipH - GAP));
                tipDiv.style.left = absX + 'px';
                tipDiv.style.top  = absY + 'px';
            }});
            m.on('mouseout', function() {{
                tipDiv.style.display = 'none';
            }});
            m.bindPopup(
                sp.img
                    ? '<div style="font-family:sans-serif">' +
                      '<img src="' + sp.img + '" style="width:200px;height:140px;' +
                      'object-fit:cover;display:block;border-radius:4px;margin-bottom:6px;">' +
                      '<b>' + sp.species + '</b><br>' +
                      'First sighting #' + sp.num + ' · ' + sp.date + '<br>' +
                      sp.location + '</div>'
                    : '<div style="font-family:sans-serif">' +
                      '<b>' + sp.species + '</b><br>' +
                      'First sighting #' + sp.num + ' · ' + sp.date + '<br>' +
                      sp.location + '</div>'
            );
            m.addTo(map);
            mkrs.push(m);
        }});

        setTimeout(play, 300);
    }}

    init();
}})();
</script>
"""
        html = html.replace("</body>", animation + self._satellite_toggle_js() + "\n</body>")

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        self._buildFilterTitle(filter, "Animated First Sightings", count=total, countUnit="Species")

        return True


    def loadGeolocatedPhotosMap(self, filter):

        from copy import deepcopy
        import folium
        from folium.plugins import MarkerCluster
        import tempfile
        from pathlib import Path
        import json

        self.title = "Geolocated Photos"
        self.filter = deepcopy(filter)

        photoSightings = self.mdiParent.db.GetSightingsWithPhotos(filter)

        # Collect one marker entry per photo that has valid coordinates.
        # photo_entries mirrors markers index-for-index and stores the raw
        # [photo_dict, sighting_dict] pairs needed by Enlargement.
        markers      = []
        photo_entries = []
        for s in photoSightings:
            try:
                lat = float(s["latitude"])
                lon = float(s["longitude"])
            except (ValueError, TypeError, KeyError):
                continue
            if lat == 0.0 and lon == 0.0:
                continue

            for p in s["photos"]:
                if not self.mdiParent.db.TestIndividualPhoto(p, filter):
                    continue

                file_path = p.get("fileName", "")
                if not file_path:
                    continue

                markers.append((lat, lon,
                                 s.get("commonName", "Unknown"),
                                 s.get("date", ""),
                                 s.get("location", ""),
                                 Path(file_path).as_uri()))
                photo_entries.append([p, s])

        if not markers:
            return False

        photo_js_data = json.dumps(
            [{"lat": m[0], "lon": m[1],
              "species": m[2], "date": m[3], "location": m[4], "img": m[5],
              "idx": i}
             for i, m in enumerate(markers)],
            ensure_ascii=False,
        )

        # Centre the map on the mean of all photo locations
        avg_lat = sum(m[0] for m in markers) / len(markers)
        avg_lon = sum(m[1] for m in markers) / len(markers)

        photo_map = folium.Map(
            location=[avg_lat, avg_lon],
            zoom_start=5,
            tiles="CartoDB Voyager",
        )

        # Add an empty MarkerCluster so Folium loads the markercluster JS
        # library; the actual markers are built entirely in injected JS below.
        MarkerCluster(options={
            "spiderfyOnMaxZoom": True,
            "spiderfyDistanceMultiplier": 2,
        }).add_to(photo_map)

        # Fit map to the bounds of all markers
        lats = [m[0] for m in markers]
        lons = [m[1] for m in markers]
        photo_map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], max_zoom=15)

        html = photo_map.get_root().render()

        # --- QWebChannel bridge for click-to-enlarge ---
        self._photosBridge = PhotosMapBridge(self, photo_entries, markers)
        channel = QWebChannel(self.webView.page())
        channel.registerObject("bridge", self._photosBridge)
        self.webView.page().setWebChannel(channel)

        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        # Inject custom JS: creates markers in a markerClusterGroup, wires up
        # an edge-aware photo tooltip (mousemove) and a click-to-enlarge handler.
        # The image container has a fixed size so the div is stable before the
        # image loads, keeping the positioning calculation correct.
        inject = f"""
<script>
{qwc_js}
(function() {{
    var photoData = {photo_js_data};

    var tipDiv = document.createElement('div');
    tipDiv.style.cssText = (
        'position:fixed; display:none; pointer-events:none; z-index:9999;' +
        'background:#252730; color:#e2e4ec; border:2px solid {PHOTO_PRIMARY};' +
        'border-radius:8px; padding:10px 12px; font-family:sans-serif;' +
        'box-shadow:0 4px 20px rgba(0,0,0,0.55);'
    );
    document.body.appendChild(tipDiv);

    function showTip(e, d) {{
        tipDiv.innerHTML = (
            '<b style="font-size:13px">' + d.species + '</b><br>' +
            '<span style="font-size:11px; color:#aaa">' +
                d.date + ' \u00b7 ' + d.location +
            '</span>' +
            '<div style="width:280px; height:190px; overflow:hidden;' +
                        'background:#1e1f26; border-radius:4px; margin-top:7px">' +
                '<img src="' + d.img + '" ' +
                     'style="width:100%; height:100%; object-fit:contain">' +
            '</div>'
        );
        tipDiv.style.display = 'block';

        var cx   = e.originalEvent.clientX;
        var cy   = e.originalEvent.clientY;
        var GAP  = 14;
        var tipW = tipDiv.offsetWidth;
        var tipH = tipDiv.offsetHeight;

        // Flip left when cursor is in the right half of the viewport.
        var absX = (cx > window.innerWidth / 2)
            ? cx - tipW - GAP
            : cx + GAP;
        absX = Math.max(GAP, Math.min(absX, window.innerWidth  - tipW - GAP));

        var absY = cy - tipH / 2;
        absY = Math.max(GAP, Math.min(absY, window.innerHeight - tipH - GAP));

        tipDiv.style.left = absX + 'px';
        tipDiv.style.top  = absY + 'px';
    }}

    function findMap() {{
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {{
            try {{
                var obj = window[keys[i]];
                if (obj && obj instanceof L.Map) return obj;
            }} catch(ignore) {{}}
        }}
        return null;
    }}

    // Set up the Qt bridge as soon as the channel transport is available.
    new QWebChannel(qt.webChannelTransport, function(channel) {{
        window.photoBridge = channel.objects.bridge;
    }});

    function init() {{
        var map = findMap();
        if (!map) {{ setTimeout(init, 150); return; }}

        var cluster = L.markerClusterGroup({{
            spiderfyOnMaxZoom: true,
            spiderfyDistanceMultiplier: 2,
        }});

        photoData.forEach(function(d) {{
            var marker = L.marker([d.lat, d.lon]);
            marker.on('mousemove', function(e) {{ showTip(e, d); }});
            marker.on('mouseout',  function()  {{ tipDiv.style.display = 'none'; }});
            marker.on('click', function() {{
                tipDiv.style.display = 'none';
                if (window.photoBridge) window.photoBridge.photoClicked(d.idx);
            }});
            cluster.addLayer(marker);
        }});

        map.addLayer(cluster);
    }}

    init();
}})();
</script>
"""
        html = html.replace("</body>", inject + self._satellite_toggle_js() + "\n</body>")

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        self._buildFilterTitle(filter, "Geolocated Photos", count=len(markers), countUnit="Photos")

        return True


    def loadAnimatedPhotoSequenceMap(self, filter):
        """Animate geolocated photos appearing on the map in chronological order.

        Each marker shows a thumbnail of the photo at its GPS location.
        Thumbnails accumulate as the animation plays.  The most recently revealed
        photo is highlighted with a blue border; previous photos keep a dark border.
        Clicking any thumbnail opens an Enlargement window for that photo.
        """
        from copy import deepcopy
        import folium
        import json
        import tempfile
        from pathlib import Path

        self.title = "Animated Sequence Map"
        self.filter = deepcopy(filter)

        # ── Collect geolocated photos sorted chronologically ─────────────
        photoSightings = self.mdiParent.db.GetSightingsWithPhotos(filter)

        entries  = []   # [photo_dict, sighting_dict] for Enlargement
        photos   = []   # map data dicts

        for s in sorted(photoSightings,
                        key=lambda x: (x.get("date", ""), x.get("time", ""))):
            try:
                lat = float(s["latitude"])
                lon = float(s["longitude"])
            except (ValueError, TypeError, KeyError):
                continue
            if lat == 0.0 and lon == 0.0:
                continue

            for p in s["photos"]:
                if not self.mdiParent.db.TestIndividualPhoto(p, filter):
                    continue
                file_path = p.get("fileName", "")
                if not file_path:
                    continue

                idx = len(entries)
                entries.append([p, s])
                photos.append({
                    "idx":      idx,
                    "lat":      lat,
                    "lon":      lon,
                    "img":      Path(file_path).as_uri(),
                    "species":  s.get("commonName", ""),
                    "date":     s.get("date", ""),
                    "location": s.get("location", ""),
                })

        if not photos:
            return False

        total      = len(photos)
        photos_js  = json.dumps(photos, ensure_ascii=False)

        # ── Base Folium map ───────────────────────────────────────────────
        lats = [p["lat"] for p in photos]
        lons = [p["lon"] for p in photos]

        photo_map = folium.Map(
            location=[sum(lats) / total, sum(lons) / total],
            zoom_start=4,
            tiles="CartoDB Voyager",
        )
        photo_map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], max_zoom=15)

        html = photo_map.get_root().render()

        # ── QWebChannel bridge (click → Photos window for that location) ──
        self._photosBridge = AnimatedPhotosBridge(
            self, [p["location"] for p in photos]
        )
        channel = QWebChannel(self.webView.page())
        channel.registerObject("bridge", self._photosBridge)
        self.webView.page().setWebChannel(channel)

        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        animation = f"""
<style>
#aps-bar {{
    position:absolute; bottom:28px; left:50%; transform:translateX(-50%);
    z-index:1000;
    background:rgba(255,255,255,0.93);
    border-radius:10px;
    box-shadow:0 2px 10px rgba(0,0,0,0.25);
    padding:7px 14px 8px;
    display:flex; flex-direction:column; align-items:stretch; gap:5px;
    font-family:sans-serif; font-size:13px;
    white-space:nowrap; user-select:none;
}}
#aps-controls {{
    display:flex; align-items:center; gap:10px;
}}
#aps-bar button {{
    background:none; border:none; cursor:pointer;
    font-size:17px; padding:0 2px; line-height:1;
}}
#aps-slider {{ width:200px; cursor:pointer; }}
#aps-speed  {{ width:65px;  cursor:pointer; vertical-align:middle; }}
#aps-info   {{ min-width:120px; color:#333; }}
#aps-caption {{
    text-align:center; font-size:12px; color:#444;
    min-height:15px; letter-spacing:0.01em;
}}
</style>
<div id="aps-bar">
  <div id="aps-controls">
    <button id="aps-restart" title="Restart">&#9198;</button>
    <button id="aps-play"    title="Play / Pause">&#9654;</button>
    <input  id="aps-slider"  type="range" min="0" max="{total}" value="0">
    <span   id="aps-info">0 / {total} photos</span>
    <label  title="Animation speed" style="display:flex;align-items:center;gap:4px">
        Slower<input id="aps-speed" type="range" min="0" max="10" value="4">Faster
    </label>
  </div>
  <div id="aps-caption"></div>
</div>
<script>
{qwc_js}
(function() {{
    var photos      = {photos_js};
    var thumbMarker = null;
    var map         = null;
    var dots        = [];
    var shown       = 0;
    var current     = -1;
    var playing     = false;
    var timer       = null;
    var DELAYS      = [5000, 3500, 2500, 1800, 1300, 950, 700, 500, 375, 300, 250];

    // Set up the Qt bridge for click → Photos window.
    new QWebChannel(qt.webChannelTransport, function(ch) {{
        window.photoBridge = ch.objects.bridge;
    }});

    function delayMs() {{
        return DELAYS[parseInt(document.getElementById('aps-speed').value)] || 150;
    }}

    function updateUI() {{
        var idx = Math.max(0, shown - 1);
        document.getElementById('aps-info').textContent = shown + ' / ' + photos.length + ' photos';
        document.getElementById('aps-slider').value = shown;
        var capEl = document.getElementById('aps-caption');
        if (shown > 0) {{
            var p = photos[idx];
            capEl.innerHTML = '<b>' + p.species + '</b> &nbsp;\u00b7&nbsp; ' + p.location + ' &nbsp;\u00b7&nbsp; ' + p.date;
        }} else {{
            capEl.textContent = '';
        }}
    }}

    function buildThumbHtml(p) {{
        return (
            '<div style="opacity:1; width:160px; display:flex; flex-direction:column;' +
                'align-items:center; cursor:pointer; transition:opacity 0.2s;">' +
                '<div style="width:160px; background:#252730;' +
                    'border:2px solid {PHOTO_PRIMARY}; border-radius:6px;' +
                    'overflow:hidden; box-shadow:0 3px 10px rgba(0,0,0,0.55);' +
                    'font-family:sans-serif; line-height:1.3;">' +
                    '<img src="' + p.img + '" ' +
                         'style="width:160px; height:110px; object-fit:cover; display:block;">' +
                    '<div style="padding:4px 6px 5px;">' +
                        '<div style="font-size:11px; font-weight:bold; color:#e2e4ec;' +
                             'white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">' + p.species + '</div>' +
                        '<div style="font-size:10px; color:#8b8fa8;' +
                             'white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">' + p.date + '</div>' +
                        '<div style="font-size:10px; color:#8b8fa8;' +
                             'white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">' + p.location + '</div>' +
                    '</div>' +
                '</div>' +
                '<div style="width:0; height:0;' +
                     'border-left:10px solid transparent;' +
                     'border-right:10px solid transparent;' +
                     'border-top:12px solid {PHOTO_PRIMARY};' +
                     'margin-top:-1px;"></div>' +
            '</div>'
        );
    }}

    function showAt(idx) {{
        current = idx;
        if (current >= 0 && current < photos.length) {{
            var p = photos[current];
            var icon = L.divIcon({{
                html: buildThumbHtml(p),
                iconSize:   [160, 176],
                iconAnchor: [80, 176],
                className:  ''
            }});
            if (thumbMarker === null) {{
                thumbMarker = L.marker([p.lat, p.lon], {{icon: icon}}).addTo(map);
                var mEl = thumbMarker.getElement();
                if (mEl) mEl.style.pointerEvents = 'none';
            }} else {{
                thumbMarker.setLatLng([p.lat, p.lon]);
                thumbMarker.setIcon(icon);
            }}
            dots[current].setStyle({{opacity: 1, fillOpacity: 0.9}});
            var dotEl = dots[current].getElement();
            if (dotEl) {{ dotEl.style.pointerEvents = 'auto'; dotEl.style.cursor = 'pointer'; }}
            shown = current + 1;
        }} else {{
            shown = 0;
        }}
        updateUI();
    }}

    function resetMarkers() {{
        if (thumbMarker !== null) {{
            thumbMarker.remove();
            thumbMarker = null;
        }}
        current = -1;
        shown = 0;
        for (var i = 0; i < dots.length; i++) {{
            dots[i].setStyle({{opacity: 0, fillOpacity: 0}});
            var dotEl = dots[i].getElement();
            if (dotEl) dotEl.style.pointerEvents = 'none';
        }}
        updateUI();
    }}

    function scheduleStep() {{
        timer = setTimeout(function() {{
            if (!playing) return;
            if (shown < photos.length) {{ showAt(shown); scheduleStep(); }}
            else pause();
        }}, delayMs());
    }}

    function play() {{
        if (shown >= photos.length) resetMarkers();
        playing = true;
        document.getElementById('aps-play').innerHTML = '&#9646;&#9646;';
        scheduleStep();
    }}

    function pause() {{
        playing = false;
        clearTimeout(timer);
        document.getElementById('aps-play').innerHTML = '&#9654;';
    }}

    document.getElementById('aps-play').onclick    = function() {{ if (playing) pause(); else play(); }};
    document.getElementById('aps-restart').onclick = function() {{ pause(); resetMarkers(); }};
    document.getElementById('aps-slider').oninput  = function() {{
        var target = parseInt(this.value);
        pause();
        if (target === 0) {{
            resetMarkers();
        }} else {{
            // Reveal dots that playback skipped over (forward scrub)
            for (var i = shown; i < target - 1; i++) {{
                dots[i].setStyle({{opacity: 1, fillOpacity: 0.9}});
                var el = dots[i].getElement();
                if (el) {{ el.style.pointerEvents = 'auto'; el.style.cursor = 'pointer'; }}
            }}
            // Hide dots beyond the new position (backward scrub)
            for (var i = target; i < shown; i++) {{
                dots[i].setStyle({{opacity: 0, fillOpacity: 0}});
                var el = dots[i].getElement();
                if (el) el.style.pointerEvents = 'none';
            }}
            showAt(target - 1);
        }}
    }};

    // Lock the control bar width to its maximum before animation starts.
    function fixBarWidth() {{
        var bar = document.getElementById('aps-bar');
        var capEl = document.getElementById('aps-caption');
        var best = photos.reduce(function(b, p) {{
            var len = p.species.length + p.location.length + p.date.length;
            return len > b.len ? {{len: len, p: p}} : b;
        }}, {{len: 0, p: null}});
        if (best.p) {{
            var p = best.p;
            capEl.innerHTML = '<b>' + p.species + '</b> &nbsp;\u00b7&nbsp; ' + p.location + ' &nbsp;\u00b7&nbsp; ' + p.date;
            bar.style.minWidth = bar.offsetWidth + 'px';
            capEl.textContent = '';
        }}
    }}
    fixBarWidth();

    function findMap() {{
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {{
            try {{
                var obj = window[keys[i]];
                if (obj && obj instanceof L.Map) return obj;
            }} catch(e) {{}}
        }}
        return null;
    }}

    function init() {{
        map = findMap();
        if (!map) {{ setTimeout(init, 150); return; }}

        photos.forEach(function(p) {{
            var dot = L.circleMarker([p.lat, p.lon], {{
                radius:      6,
                fillColor:   '{PHOTO_PRIMARY}',
                color:       '#ffffff',
                weight:      1.5,
                opacity:     0,
                fillOpacity: 0,
            }});
            dot.on('click', function() {{
                if (window.photoBridge) window.photoBridge.photoClicked(p.idx);
            }});
            dot.addTo(map);
            // Start non-interactive; showAt() enables pointer-events when the dot becomes visible.
            var dotEl = dot.getElement();
            if (dotEl) dotEl.style.pointerEvents = 'none';
            dots.push(dot);
        }});

        setTimeout(play, 300);
    }}

    init();
}})();
</script>
"""
        html = html.replace("</body>", animation + self._satellite_toggle_js() + "\n</body>")

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        self._buildFilterTitle(filter, "Animated Sequence Map", count=total, countUnit="Photos")

        return True


    def loadGeolocatedRecordingsMap(self, filter):
        from copy import deepcopy
        import folium
        from folium.plugins import MarkerCluster
        import tempfile
        import json

        self.title = "Geolocated Recordings"
        self.filter = deepcopy(filter)

        recordingSightings = self.mdiParent.db.GetSightingsWithRecordings(filter)

        markers  = []   # (lat, lon, species, date, location, idx)
        for s in recordingSightings:
            try:
                lat = float(s["latitude"])
                lon = float(s["longitude"])
            except (ValueError, TypeError, KeyError):
                continue
            if lat == 0.0 and lon == 0.0:
                continue
            markers.append((lat, lon,
                             s.get("commonName", "Unknown"),
                             s.get("date", ""),
                             s.get("location", ""),
                             len(markers)))

        if not markers:
            return False

        marker_js = json.dumps(
            [{"lat": m[0], "lon": m[1],
              "species": m[2], "date": m[3], "location": m[4],
              "idx": m[5]}
             for m in markers],
            ensure_ascii=False,
        )

        avg_lat = sum(m[0] for m in markers) / len(markers)
        avg_lon = sum(m[1] for m in markers) / len(markers)

        rec_map = folium.Map(location=[avg_lat, avg_lon], zoom_start=5,
                             tiles="CartoDB Voyager")
        MarkerCluster(options={"spiderfyOnMaxZoom": True,
                                "spiderfyDistanceMultiplier": 2}).add_to(rec_map)
        lats = [m[0] for m in markers]
        lons = [m[1] for m in markers]
        rec_map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], max_zoom=15)

        html = rec_map.get_root().render()

        self._recordingsBridge = GeolocatedRecordingsBridge(
            self, [m[4] for m in markers])
        channel = QWebChannel(self.webView.page())
        channel.registerObject("bridge", self._recordingsBridge)
        self.webView.page().setWebChannel(channel)

        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        inject = f"""
<script>
{qwc_js}
(function() {{
    var recData = {marker_js};

    var tipDiv = document.createElement('div');
    tipDiv.style.cssText = (
        'position:fixed; display:none; pointer-events:none; z-index:9999;' +
        'background:#252730; color:#e2e4ec; border:2px solid {RECORDINGS_PRIMARY};' +
        'border-radius:8px; padding:10px 12px; font-family:sans-serif;' +
        'box-shadow:0 4px 20px rgba(0,0,0,0.55);'
    );
    document.body.appendChild(tipDiv);

    function showTip(e, d) {{
        tipDiv.innerHTML = (
            '<b style="font-size:13px">' + d.species + '</b><br>' +
            '<span style="font-size:11px; color:#aaa">' +
                d.date + ' · ' + d.location +
            '</span>'
        );
        tipDiv.style.display = 'block';
        var cx = e.originalEvent.clientX, cy = e.originalEvent.clientY;
        var GAP = 14, tipW = tipDiv.offsetWidth, tipH = tipDiv.offsetHeight;
        var absX = (cx > window.innerWidth / 2) ? cx - tipW - GAP : cx + GAP;
        absX = Math.max(GAP, Math.min(absX, window.innerWidth - tipW - GAP));
        var absY = cy - tipH / 2;
        absY = Math.max(GAP, Math.min(absY, window.innerHeight - tipH - GAP));
        tipDiv.style.left = absX + 'px';
        tipDiv.style.top  = absY + 'px';
    }}

    function findMap() {{
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {{
            try {{ var obj = window[keys[i]]; if (obj && obj instanceof L.Map) return obj; }} catch(e) {{}}
        }}
        return null;
    }}

    new QWebChannel(qt.webChannelTransport, function(channel) {{
        window.recBridge = channel.objects.bridge;
    }});

    function init() {{
        var map = findMap();
        if (!map) {{ setTimeout(init, 150); return; }}
        var cluster = L.markerClusterGroup({{spiderfyOnMaxZoom: true, spiderfyDistanceMultiplier: 2}});
        recData.forEach(function(d) {{
            var marker = L.marker([d.lat, d.lon]);
            marker.on('mousemove', function(e) {{ showTip(e, d); }});
            marker.on('mouseout',  function()  {{ tipDiv.style.display = 'none'; }});
            marker.on('click', function() {{
                tipDiv.style.display = 'none';
                if (window.recBridge) window.recBridge.recordingClicked(d.idx);
            }});
            cluster.addLayer(marker);
        }});
        map.addLayer(cluster);
    }}
    init();
}})();
</script>
"""
        html = html.replace("</body>", inject + self._satellite_toggle_js() + "\n</body>")

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        self._buildFilterTitle(filter, "Geolocated Recordings",
                               count=len(markers), countUnit="Recordings")
        return True


    def loadAnimatedRecordingSequenceMap(self, filter):
        """Animate geolocated recordings appearing on the map in chronological order."""
        from copy import deepcopy
        import folium
        import json
        import tempfile

        self.title = "Animated Recording Sequence Map"
        self.filter = deepcopy(filter)

        recordingSightings = self.mdiParent.db.GetSightingsWithRecordings(filter)

        recordings = []
        for s in sorted(recordingSightings,
                        key=lambda x: (x.get("date", ""), x.get("time", ""))):
            try:
                lat = float(s["latitude"])
                lon = float(s["longitude"])
            except (ValueError, TypeError, KeyError):
                continue
            if lat == 0.0 and lon == 0.0:
                continue
            recordings.append({
                "idx":      len(recordings),
                "lat":      lat,
                "lon":      lon,
                "species":  s.get("commonName", ""),
                "date":     s.get("date", ""),
                "location": s.get("location", ""),
            })

        if not recordings:
            return False

        total       = len(recordings)
        recs_js     = json.dumps(recordings, ensure_ascii=False)

        lats = [r["lat"] for r in recordings]
        lons = [r["lon"] for r in recordings]

        rec_map = folium.Map(
            location=[sum(lats) / total, sum(lons) / total],
            zoom_start=4, tiles="CartoDB Voyager")
        rec_map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], max_zoom=15)

        html = rec_map.get_root().render()

        self._animatedRecBridge = AnimatedRecordingsBridge(
            self, [r["location"] for r in recordings])
        channel = QWebChannel(self.webView.page())
        channel.registerObject("bridge", self._animatedRecBridge)
        self.webView.page().setWebChannel(channel)

        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        animation = f"""
<style>
#ars-bar {{
    position:absolute; bottom:28px; left:50%; transform:translateX(-50%);
    z-index:1000; background:rgba(255,255,255,0.93);
    border-radius:10px; box-shadow:0 2px 10px rgba(0,0,0,0.25);
    padding:7px 14px 8px;
    display:flex; flex-direction:column; align-items:stretch; gap:5px;
    font-family:sans-serif; font-size:13px; white-space:nowrap; user-select:none;
}}
#ars-controls {{ display:flex; align-items:center; gap:10px; }}
#ars-bar button {{ background:none; border:none; cursor:pointer; font-size:17px; padding:0 2px; line-height:1; }}
#ars-slider {{ width:200px; cursor:pointer; }}
#ars-speed  {{ width:65px;  cursor:pointer; vertical-align:middle; }}
#ars-info   {{ min-width:140px; color:#333; }}
#ars-caption {{ text-align:center; font-size:12px; color:#444; min-height:15px; letter-spacing:0.01em; }}
</style>
<div id="ars-bar">
  <div id="ars-controls">
    <button id="ars-restart" title="Restart">&#9198;</button>
    <button id="ars-play"    title="Play / Pause">&#9654;</button>
    <input  id="ars-slider"  type="range" min="0" max="{total}" value="0">
    <span   id="ars-info">0 / {total} recordings</span>
    <label  title="Animation speed" style="display:flex;align-items:center;gap:4px">
        Slower<input id="ars-speed" type="range" min="0" max="10" value="4">Faster
    </label>
  </div>
  <div id="ars-caption"></div>
</div>
<script>
{qwc_js}
(function() {{
    var recs  = {recs_js};
    var map   = null;
    var dots  = [];
    var shown = 0;
    var current = -1;
    var playing = false;
    var timer   = null;
    var DELAYS  = [5000, 3500, 2500, 1800, 1300, 950, 700, 500, 375, 300, 250];

    new QWebChannel(qt.webChannelTransport, function(ch) {{
        window.recBridge = ch.objects.bridge;
    }});

    function delayMs() {{
        return DELAYS[parseInt(document.getElementById('ars-speed').value)] || 150;
    }}

    function updateUI() {{
        var idx = Math.max(0, shown - 1);
        document.getElementById('ars-info').textContent = shown + ' / ' + recs.length + ' recordings';
        document.getElementById('ars-slider').value = shown;
        var capEl = document.getElementById('ars-caption');
        if (shown > 0) {{
            var r = recs[idx];
            capEl.innerHTML = '<b>' + r.species + '</b> &nbsp;·&nbsp; ' + r.location + ' &nbsp;·&nbsp; ' + r.date;
        }} else {{ capEl.textContent = ''; }}
    }}

    function showAt(idx) {{
        current = idx;
        if (current >= 0 && current < recs.length) {{
            dots[current].setStyle({{opacity: 1, fillOpacity: 0.9}});
            var dotEl = dots[current].getElement();
            if (dotEl) {{ dotEl.style.pointerEvents = 'auto'; dotEl.style.cursor = 'pointer'; }}
            shown = current + 1;
        }} else {{ shown = 0; }}
        updateUI();
    }}

    function resetMarkers() {{
        current = -1; shown = 0;
        for (var i = 0; i < dots.length; i++) {{
            dots[i].setStyle({{opacity: 0, fillOpacity: 0}});
            var el = dots[i].getElement();
            if (el) el.style.pointerEvents = 'none';
        }}
        updateUI();
    }}

    function scheduleStep() {{
        timer = setTimeout(function() {{
            if (!playing) return;
            if (shown < recs.length) {{ showAt(shown); scheduleStep(); }}
            else pause();
        }}, delayMs());
    }}

    function play() {{
        if (shown >= recs.length) resetMarkers();
        playing = true;
        document.getElementById('ars-play').innerHTML = '&#9646;&#9646;';
        scheduleStep();
    }}

    function pause() {{
        playing = false; clearTimeout(timer);
        document.getElementById('ars-play').innerHTML = '&#9654;';
    }}

    document.getElementById('ars-play').onclick    = function() {{ if (playing) pause(); else play(); }};
    document.getElementById('ars-restart').onclick = function() {{ pause(); resetMarkers(); }};
    document.getElementById('ars-slider').oninput  = function() {{
        var target = parseInt(this.value);
        pause();
        if (target === 0) {{
            resetMarkers();
        }} else {{
            for (var i = shown; i < target - 1; i++) {{
                dots[i].setStyle({{opacity: 1, fillOpacity: 0.9}});
                var el = dots[i].getElement();
                if (el) {{ el.style.pointerEvents = 'auto'; el.style.cursor = 'pointer'; }}
            }}
            for (var i = target; i < shown; i++) {{
                dots[i].setStyle({{opacity: 0, fillOpacity: 0}});
                var el = dots[i].getElement();
                if (el) el.style.pointerEvents = 'none';
            }}
            showAt(target - 1);
        }}
    }};

    function fixBarWidth() {{
        var bar = document.getElementById('ars-bar');
        var capEl = document.getElementById('ars-caption');
        var best = recs.reduce(function(b, r) {{
            var len = r.species.length + r.location.length + r.date.length;
            return len > b.len ? {{len: len, r: r}} : b;
        }}, {{len: 0, r: null}});
        if (best.r) {{
            var r = best.r;
            capEl.innerHTML = '<b>' + r.species + '</b> &nbsp;·&nbsp; ' + r.location + ' &nbsp;·&nbsp; ' + r.date;
            bar.style.minWidth = bar.offsetWidth + 'px';
            capEl.textContent = '';
        }}
    }}
    fixBarWidth();

    function findMap() {{
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {{
            try {{ var obj = window[keys[i]]; if (obj && obj instanceof L.Map) return obj; }} catch(e) {{}}
        }}
        return null;
    }}

    function init() {{
        map = findMap();
        if (!map) {{ setTimeout(init, 150); return; }}
        recs.forEach(function(r) {{
            var dot = L.circleMarker([r.lat, r.lon], {{
                radius: 6, fillColor: '{RECORDINGS_PRIMARY}',
                color: '#ffffff', weight: 1.5, opacity: 0, fillOpacity: 0,
            }});
            dot.on('click', function() {{
                if (window.recBridge) window.recBridge.recordingClicked(r.idx);
            }});
            dot.addTo(map);
            var dotEl = dot.getElement();
            if (dotEl) dotEl.style.pointerEvents = 'none';
            dots.push(dot);
        }});
        setTimeout(play, 300);
    }}
    init();
}})();
</script>
"""
        html = html.replace("</body>", animation + self._satellite_toggle_js() + "\n</body>")

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        self._buildFilterTitle(filter, "Animated Recording Sequence Map",
                               count=total, countUnit="Recordings")
        return True


    def loadAudioSpeciesGallery(self, filter):
        """HTML table of species with recordings, in taxonomic order.

        Clicking a species row opens the audio browser filtered to that species.
        """
        from copy import deepcopy
        import json

        self.title = "Recordings by Species"
        self.filter = deepcopy(filter)

        recordingSightings = self.mdiParent.db.GetSightingsWithRecordings(filter)
        if not recordingSightings:
            return False

        # Count recordings per species, preserve taxonomic order
        species_order = []
        species_count = {}
        species_taxo  = {}
        for s in recordingSightings:
            sp = s["commonName"]
            n  = len(s.get("audio", []))
            if sp not in species_count:
                species_order.append(sp)
                species_count[sp] = 0
                species_taxo[sp]  = float(s.get("taxonomicOrder", 0))
            species_count[sp] += n

        species_order.sort(key=lambda sp: species_taxo[sp])

        # rank = 1-based taxonomic position; travels with the species so the
        # "#" column stays meaningful (and sortable back to taxonomic order)
        # regardless of the active sort.
        rows_data = [{"species": sp, "count": species_count[sp], "rank": i + 1}
                     for i, sp in enumerate(species_order)]
        rows_js = json.dumps(rows_data, ensure_ascii=False)

        channel = QWebChannel(self.webView.page())
        self.webView.page().setWebChannel(channel)

        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        total_recs    = sum(species_count.values())
        total_species = len(species_order)

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ margin:0; padding:0; background:#1e1f26; color:#e2e4ec;
          font-family:sans-serif; font-size:13px; }}
  #header {{ padding:10px 14px 8px; background:#252730;
             border-bottom:1px solid #333; display:flex; align-items:baseline; gap:16px; }}
  #header h2 {{ margin:0; font-size:15px; font-weight:600; }}
  #header .sub {{ font-size:12px; color:#8b8fa8; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ position:sticky; top:0; background:#252730; padding:6px 14px;
        text-align:left; font-size:11px; color:#8b8fa8; letter-spacing:0.05em;
        text-transform:uppercase; border-bottom:1px solid #333; }}
  tr.sp-row {{ cursor:pointer; }}
  tr.sp-row:hover td {{ background:#2e3040; }}
  td {{ padding:7px 14px; border-bottom:1px solid #2a2b35; }}
  td.num {{ text-align:right; color:{CHART_PRIMARY}; font-variant-numeric:tabular-nums; }}
  td.bar-cell {{ width:180px; padding-right:14px; }}
  .bar {{ height:10px; background:{RECORDINGS_PRIMARY}; border-radius:3px; min-width:2px; }}
  th.sortable {{ cursor:pointer; user-select:none; }}
  th.sortable:hover {{ color:#c3c6d4; }}
  th.num-h {{ text-align:right; }}
  th.prop-h {{ width:180px; }}
  th .arr {{ font-size:9px; margin-left:5px; color:{CHART_PRIMARY}; }}
</style>
</head><body>
<div id="header">
  <h2>Recordings by Species</h2>
  <span class="sub">{total_species} species &nbsp;·&nbsp; {total_recs} recordings</span>
</div>
<table>
  <thead><tr>
    <th class="sortable" data-key="rank">Tax<span class="arr"></span></th>
    <th class="sortable" data-key="species">Species<span class="arr"></span></th>
    <th class="sortable num-h" data-key="count">Recordings<span class="arr"></span></th>
    <th class="prop-h"></th>
  </tr></thead>
  <tbody id="tbody"></tbody>
</table>
<script>
{qwc_js}
new QWebChannel(qt.webChannelTransport, function(ch) {{
    window.galleryBridge = ch.objects.galleryBridge;
}});
var rows = {rows_js};
var maxCount = Math.max.apply(null, rows.map(function(r) {{ return r.count; }}));
var tbody = document.getElementById('tbody');
var sortKey = 'rank', sortDir = 1;   // 1 = ascending, -1 = descending

function render(data) {{
  tbody.innerHTML = '';
  data.forEach(function(r) {{
    var tr = document.createElement('tr');
    tr.className = 'sp-row';
    var pct = maxCount > 0 ? (r.count / maxCount * 170) : 0;
    tr.innerHTML = (
      '<td>' + r.rank + '</td>' +
      '<td>' + r.species + '</td>' +
      '<td class="num">' + r.count + '</td>' +
      '<td class="bar-cell"><div class="bar" style="width:' + Math.round(pct) + 'px"></div></td>'
    );
    tr.addEventListener('click', function() {{
      if (window.galleryBridge) window.galleryBridge.speciesClicked(r.species);
    }});
    tbody.appendChild(tr);
  }});
}}

function updateArrows() {{
  var ths = document.querySelectorAll('th.sortable');
  for (var i = 0; i < ths.length; i++) {{
    var span = ths[i].querySelector('.arr');
    span.textContent = (ths[i].getAttribute('data-key') === sortKey)
      ? (sortDir === 1 ? '▲' : '▼') : '';
  }}
}}

function applySort() {{
  var data = rows.slice();
  data.sort(function(a, b) {{
    if (sortKey === 'species') return a.species.localeCompare(b.species) * sortDir;
    return (a[sortKey] - b[sortKey]) * sortDir;
  }});
  render(data);
  updateArrows();
}}

var headers = document.querySelectorAll('th.sortable');
for (var h = 0; h < headers.length; h++) {{
  headers[h].addEventListener('click', function() {{
    var key = this.getAttribute('data-key');
    if (key === sortKey) {{
      sortDir = -sortDir;
    }} else {{
      sortKey = key;
      sortDir = (key === 'count') ? -1 : 1;   // numbers most-first by default
    }}
    applySort();
  }});
}}

applySort();
</script>
</body></html>"""

        self._galleryBridge = _AudioGalleryBridge(self, filter)
        channel.registerObject("galleryBridge", self._galleryBridge)

        # Paint the page's backing store in the theme colour so there is no
        # white flash before the HTML renders (matches the <body> background).
        from PySide6.QtGui import QColor
        self.webView.page().setBackgroundColor(QColor("#1e1f26"))
        self.webView.setHtml(html)
        self._buildFilterTitle(filter, "Recordings by Species",
                               count=total_species, countUnit="Species")
        return True


    def loadPhotoSpeciesGallery(self, filter):
        """HTML table of species with photos, in taxonomic order.

        Clicking a species row opens the photo browser filtered to that species.
        """
        from copy import deepcopy
        import json

        self.title = "Photos by Species"
        self.filter = deepcopy(filter)

        photoSightings = self.mdiParent.db.GetSightingsWithPhotos(filter)
        if not photoSightings:
            return False

        # Count photos per species (applying the per-photo filter so the counts
        # match the browser), preserving taxonomic order.
        species_order = []
        species_count = {}
        species_taxo  = {}
        for s in photoSightings:
            n = sum(1 for p in s.get("photos", [])
                    if self.mdiParent.db.TestIndividualPhoto(p, filter))
            if n == 0:
                continue
            sp = s["commonName"]
            if sp not in species_count:
                species_order.append(sp)
                species_count[sp] = 0
                species_taxo[sp]  = float(s.get("taxonomicOrder", 0))
            species_count[sp] += n

        if not species_order:
            return False

        species_order.sort(key=lambda sp: species_taxo[sp])

        # rank = 1-based taxonomic position; travels with the species so the
        # "Tax" column stays meaningful (and sortable back to taxonomic order)
        # regardless of the active sort.
        rows_data = [{"species": sp, "count": species_count[sp], "rank": i + 1}
                     for i, sp in enumerate(species_order)]
        rows_js = json.dumps(rows_data, ensure_ascii=False)

        channel = QWebChannel(self.webView.page())
        self.webView.page().setWebChannel(channel)

        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        total_photos  = sum(species_count.values())
        total_species = len(species_order)

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ margin:0; padding:0; background:#1e1f26; color:#e2e4ec;
          font-family:sans-serif; font-size:13px; }}
  #header {{ padding:10px 14px 8px; background:#252730;
             border-bottom:1px solid #333; display:flex; align-items:baseline; gap:16px; }}
  #header h2 {{ margin:0; font-size:15px; font-weight:600; }}
  #header .sub {{ font-size:12px; color:#8b8fa8; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ position:sticky; top:0; background:#252730; padding:6px 14px;
        text-align:left; font-size:11px; color:#8b8fa8; letter-spacing:0.05em;
        text-transform:uppercase; border-bottom:1px solid #333; }}
  tr.sp-row {{ cursor:pointer; }}
  tr.sp-row:hover td {{ background:#2e3040; }}
  td {{ padding:7px 14px; border-bottom:1px solid #2a2b35; }}
  td.num {{ text-align:right; color:{CHART_PRIMARY}; font-variant-numeric:tabular-nums; }}
  td.bar-cell {{ width:180px; padding-right:14px; }}
  .bar {{ height:10px; background:{PHOTO_PRIMARY}; border-radius:3px; min-width:2px; }}
  th.sortable {{ cursor:pointer; user-select:none; }}
  th.sortable:hover {{ color:#c3c6d4; }}
  th.num-h {{ text-align:right; }}
  th.prop-h {{ width:180px; }}
  th .arr {{ font-size:9px; margin-left:5px; color:{CHART_PRIMARY}; }}
</style>
</head><body>
<div id="header">
  <h2>Photos by Species</h2>
  <span class="sub">{total_species} species &nbsp;·&nbsp; {total_photos} photos</span>
</div>
<table>
  <thead><tr>
    <th class="sortable" data-key="rank">Tax<span class="arr"></span></th>
    <th class="sortable" data-key="species">Species<span class="arr"></span></th>
    <th class="sortable num-h" data-key="count">Photos<span class="arr"></span></th>
    <th class="prop-h"></th>
  </tr></thead>
  <tbody id="tbody"></tbody>
</table>
<script>
{qwc_js}
new QWebChannel(qt.webChannelTransport, function(ch) {{
    window.galleryBridge = ch.objects.galleryBridge;
}});
var rows = {rows_js};
var maxCount = Math.max.apply(null, rows.map(function(r) {{ return r.count; }}));
var tbody = document.getElementById('tbody');
var sortKey = 'rank', sortDir = 1;   // 1 = ascending, -1 = descending

function render(data) {{
  tbody.innerHTML = '';
  data.forEach(function(r) {{
    var tr = document.createElement('tr');
    tr.className = 'sp-row';
    var pct = maxCount > 0 ? (r.count / maxCount * 170) : 0;
    tr.innerHTML = (
      '<td>' + r.rank + '</td>' +
      '<td>' + r.species + '</td>' +
      '<td class="num">' + r.count + '</td>' +
      '<td class="bar-cell"><div class="bar" style="width:' + Math.round(pct) + 'px"></div></td>'
    );
    tr.addEventListener('click', function() {{
      if (window.galleryBridge) window.galleryBridge.speciesClicked(r.species);
    }});
    tbody.appendChild(tr);
  }});
}}

function updateArrows() {{
  var ths = document.querySelectorAll('th.sortable');
  for (var i = 0; i < ths.length; i++) {{
    var span = ths[i].querySelector('.arr');
    span.textContent = (ths[i].getAttribute('data-key') === sortKey)
      ? (sortDir === 1 ? '▲' : '▼') : '';
  }}
}}

function applySort() {{
  var data = rows.slice();
  data.sort(function(a, b) {{
    if (sortKey === 'species') return a.species.localeCompare(b.species) * sortDir;
    return (a[sortKey] - b[sortKey]) * sortDir;
  }});
  render(data);
  updateArrows();
}}

var headers = document.querySelectorAll('th.sortable');
for (var h = 0; h < headers.length; h++) {{
  headers[h].addEventListener('click', function() {{
    var key = this.getAttribute('data-key');
    if (key === sortKey) {{
      sortDir = -sortDir;
    }} else {{
      sortKey = key;
      sortDir = (key === 'count') ? -1 : 1;   // numbers most-first by default
    }}
    applySort();
  }});
}}

applySort();
</script>
</body></html>"""

        self._galleryBridge = _PhotoGalleryBridge(self, filter)
        channel.registerObject("galleryBridge", self._galleryBridge)

        # Paint the page's backing store in the theme colour so there is no
        # white flash before the HTML renders (matches the <body> background).
        from PySide6.QtGui import QColor
        self.webView.page().setBackgroundColor(QColor("#1e1f26"))
        self.webView.setHtml(html)
        self._buildFilterTitle(filter, "Photos by Species",
                               count=total_species, countUnit="Species")
        return True


    def loadEffortMap(self, filter, mode='time'):

        from copy import deepcopy
        import folium
        import math
        import tempfile

        title = "Effort Map by Time" if mode == 'time' else "Effort Map by Checklists"
        self.title = title
        self.filter = deepcopy(filter)

        checklists = self.mdiParent.db.GetChecklists(filter)
        if not checklists:
            return False

        # Aggregate duration (minutes), checklist count, and untimed count by location name.
        # GetChecklists returns [checklistID, state, county, location, date, time, speciesCount, duration]
        loc_minutes  = {}   # location -> total minutes
        loc_count    = {}   # location -> checklist count
        loc_untimed  = {}   # location -> untimed checklist count
        for row in checklists:
            location = row[3]
            duration = row[7]
            try:
                mins = int(duration) if duration not in (None, "") else 0
            except (ValueError, TypeError):
                mins = 0
            loc_minutes[location] = loc_minutes.get(location, 0) + mins
            loc_count[location]   = loc_count.get(location, 0) + 1
            if mins == 0:
                loc_untimed[location] = loc_untimed.get(location, 0) + 1

        # Resolve coordinates and drop locations with no valid GPS fix.
        points = []   # (lat, lon, location, total_minutes, checklist_count, untimed_count)
        for location, total_mins in loc_minutes.items():
            try:
                coords = self.mdiParent.db.GetLocationCoordinates(location)
                lat = float(coords[0])
                lon = float(coords[1])
            except (KeyError, IndexError, ValueError, TypeError):
                continue
            if lat == 0.0 and lon == 0.0:
                continue
            points.append((lat, lon, location, total_mins, loc_count[location], loc_untimed.get(location, 0)))

        if not points:
            return False

        # ── Radius scaling ──────────────────────────────────────────────────
        # Use sqrt so that area (∝ r²) is proportional to the chosen metric,
        # giving a perceptually honest comparison between locations.
        # p = (lat, lon, location, total_minutes, checklist_count, untimed_count)
        MIN_R, MAX_R = 6, 45
        if mode == 'time':
            MAX_METRIC = max(p[3] for p in points) or 1
            def radius_for(total_mins, count):
                return MIN_R + (MAX_R - MIN_R) * math.sqrt(total_mins / MAX_METRIC)
        else:
            MAX_METRIC = max(p[4] for p in points) or 1
            def radius_for(total_mins, count):
                return MIN_R + (MAX_R - MIN_R) * math.sqrt(count / MAX_METRIC)

        # ── Duration formatter ───────────────────────────────────────────────
        def fmt_duration(mins):
            if mins <= 0:
                return "no duration recorded"
            h, m = divmod(mins, 60)
            if h == 0:
                return f"{m}m"
            return f"{h}h {m}m" if m else f"{h}h"

        # Centre map on the mean of all points.
        avg_lat = sum(p[0] for p in points) / len(points)
        avg_lon = sum(p[1] for p in points) / len(points)

        effort_map = folium.Map(
            location=[avg_lat, avg_lon],
            zoom_start=5,
            tiles="CartoDB Voyager",
        )

        tip_data = {}
        for lat, lon, location, total_mins, count, untimed in points:
            r = radius_for(total_mins, count)
            untimed_line = (
                f"<br>Includes {untimed} untimed checklist{'s' if untimed != 1 else ''}"
                if 0 < untimed < count else ""
            )
            if mode == 'time':
                tip_data[location] = (
                    f"<b>{location}</b><br>"
                    f"{fmt_duration(total_mins)} &nbsp;·&nbsp; "
                    f"{count} checklist{'s' if count != 1 else ''}"
                    f"{untimed_line}"
                )
            else:
                tip_data[location] = (
                    f"<b>{location}</b><br>"
                    f"{count} checklist{'s' if count != 1 else ''} &nbsp;·&nbsp; "
                    f"{fmt_duration(total_mins)}"
                    f"{untimed_line}"
                )
            marker = folium.CircleMarker(
                location=[lat, lon],
                radius=r,
                color="#2a5fad",
                weight=1,
                fill=True,
                fill_color=CHART_PRIMARY,
                fill_opacity=0.65,
            )
            marker.options["locationName"] = location
            marker.add_to(effort_map)

        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        effort_map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], max_zoom=15)

        html = effort_map.get_root().render()

        import json as _json
        tip_data_json = _json.dumps(tip_data, ensure_ascii=False)

        self._mapBridge = MapBridge(self)
        channel = QWebChannel(self.webView.page())
        channel.registerObject("bridge", self._mapBridge)
        self.webView.page().setWebChannel(channel)

        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        inject_js = f"""
<script>
{qwc_js}
(function() {{
    var tipDiv = document.createElement('div');
    tipDiv.style.cssText = (
        'position:fixed; display:none; pointer-events:none; z-index:9999;' +
        'background:#252730; color:#e2e4ec; border:1px solid {CHART_PRIMARY};' +
        'border-radius:6px; padding:6px 10px; font-size:12px;' +
        'max-width:300px; line-height:1.5;'
    );
    document.body.appendChild(tipDiv);
    var tipData = {tip_data_json};
    function findMap() {{
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {{
            try {{ var o = window[keys[i]]; if (o && o instanceof L.Map) return o; }}
            catch(e) {{}}
        }}
        return null;
    }}
    function init() {{
        var map = findMap();
        if (!map) {{ setTimeout(init, 150); return; }}
        new QWebChannel(qt.webChannelTransport, function(channel) {{
            window.bridge = channel.objects.bridge;
            map.eachLayer(function(layer) {{
                if (!(layer instanceof L.CircleMarker)) return;
                var name      = layer.options.locationName;
                var origColor = layer.options.color;
                var origWeight = layer.options.weight;
                if (!name) return;
                layer.on('click', function() {{
                    window.bridge.locationClicked(name);
                }});
                layer.on('mouseover', function(e) {{
                    this.setStyle({{ color: '#ff8800', weight: 3 }});
                    var html = tipData[name];
                    if (!html) return;
                    tipDiv.innerHTML = html;
                    tipDiv.style.display = 'block';
                    var mapCont = map.getContainer();
                    var mapRect = mapCont.getBoundingClientRect();
                    var pt = map.latLngToContainerPoint(e.target.getLatLng());
                    var GAP = 12;
                    var tipW = tipDiv.offsetWidth;
                    var tipH = tipDiv.offsetHeight;
                    var absX = pt.x > mapRect.width / 2
                        ? mapRect.left + pt.x - tipW - GAP
                        : mapRect.left + pt.x + GAP;
                    var absY = mapRect.top + pt.y - tipH / 2;
                    absY = Math.max(GAP, Math.min(absY, window.innerHeight - tipH - GAP));
                    tipDiv.style.left = absX + 'px';
                    tipDiv.style.top  = absY + 'px';
                }});
                layer.on('mouseout', function() {{
                    this.setStyle({{ color: origColor, weight: origWeight }});
                    tipDiv.style.display = 'none';
                }});
            }});
        }});
    }}
    init();
}})();
</script>"""
        html = html.replace("</body>", inject_js + self._satellite_toggle_js() + "\n</body>")

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        self._buildFilterTitle(filter, title, count=len(points), countUnit="Locations")

        return True


    def _inject_circle_marker_bridge(self, html):
        """Set up MapBridge + QWebChannel and inject click/hover JS for CircleMarker maps.

        Wires locationClicked(name) on click and orange-outline highlight on hover
        for every CircleMarker whose options.locationName is set.  Returns modified HTML.
        """
        self._mapBridge = MapBridge(self)
        channel = QWebChannel(self.webView.page())
        channel.registerObject("bridge", self._mapBridge)
        self.webView.page().setWebChannel(channel)

        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        inject_js = f"""
<script>
{qwc_js}
(function() {{
    function findMap() {{
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {{
            try {{ var o = window[keys[i]]; if (o && o instanceof L.Map) return o; }}
            catch(e) {{}}
        }}
        return null;
    }}
    function init() {{
        var map = findMap();
        if (!map) {{ setTimeout(init, 150); return; }}
        new QWebChannel(qt.webChannelTransport, function(channel) {{
            window.bridge = channel.objects.bridge;
            map.eachLayer(function(layer) {{
                if (!(layer instanceof L.CircleMarker)) return;
                var name       = layer.options.locationName;
                var origColor  = layer.options.color;
                var origWeight = layer.options.weight;
                if (name) {{
                    layer.on('click', function() {{
                        window.bridge.locationClicked(name);
                    }});
                }}
                layer.on('mouseover', function() {{
                    this.setStyle({{ color: '#ff8800', weight: 3 }});
                }});
                layer.on('mouseout', function() {{
                    this.setStyle({{ color: origColor, weight: origWeight }});
                }});
            }});
        }});
    }}
    init();
}})();
</script>"""
        return html.replace("</body>", inject_js + self._satellite_toggle_js() + "\n</body>")


    def loadBubbleMap(self, filter, mode='species'):

        from copy import deepcopy
        import folium
        import math
        import tempfile

        title = "Species Total Map" if mode == 'species' else "Individuals Total Map"
        self.title = title
        self.filter = deepcopy(filter)

        sightings = self.mdiParent.db.GetSightings(filter)
        if not sightings:
            return False

        # Aggregate per location: species set, individual counts, and checklists with unknown counts
        loc_species     = defaultdict(dict)   # location -> {commonName: None}
        loc_individuals = defaultdict(int)    # location -> total tallied individuals
        loc_unknown_cl  = defaultdict(set)    # location -> set of checklistIDs with ≥1 "X" count

        for s in sightings:
            location = s.get("location", "")
            if not location:
                continue
            loc_species[location][s.get("commonName", "")] = None
            cnt = s.get("count", "X")
            try:
                loc_individuals[location] += int(cnt)
            except (ValueError, TypeError):
                # "X" (unknown count) — count as 1 and record the checklist ID
                loc_individuals[location] += 1
                cid = s.get("checklistID", "")
                if cid:
                    loc_unknown_cl[location].add(cid)

        if not loc_species:
            return False

        # Compute the metric for each location
        if mode == 'species':
            loc_metric = {
                loc: self.mdiParent.db.CountSpecies(list(sp.keys()))
                for loc, sp in loc_species.items()
            }
            metric_label = "species"
        else:
            # Use all locations that have any sightings; individuals defaults to 0 if all "X"
            loc_metric   = {loc: loc_individuals.get(loc, 0) for loc in loc_species}
            metric_label = "individuals"

        # Resolve coordinates; drop (0, 0) fixes
        points = []   # (lat, lon, location, metric)
        for location, metric in loc_metric.items():
            try:
                coords = self.mdiParent.db.GetLocationCoordinates(location)
                lat = float(coords[0])
                lon = float(coords[1])
            except (KeyError, IndexError, ValueError, TypeError):
                continue
            if lat == 0.0 and lon == 0.0:
                continue
            points.append((lat, lon, location, metric))

        if not points:
            return False

        # ── Radius scaling (sqrt so small values stay visible across wide ranges) ──
        MAX_METRIC = max(p[3] for p in points) or 1
        MIN_R, MAX_R = 3, 40

        def radius_for(metric):
            return MIN_R + (MAX_R - MIN_R) * math.sqrt(metric / MAX_METRIC)

        avg_lat = sum(p[0] for p in points) / len(points)
        avg_lon = sum(p[1] for p in points) / len(points)

        bubble_map = folium.Map(
            location=[avg_lat, avg_lon],
            zoom_start=5,
            tiles="CartoDB Voyager",
        )

        # Build tooltip data for both modes
        tip_data = {}
        for lat, lon, location, metric in points:
            if mode == 'species':
                sp_sorted = list(loc_species.get(location, {}).keys())
                sp_lines = "".join(f"<br>&nbsp;&nbsp;{sp}" for sp in sp_sorted[:25])
                if len(sp_sorted) > 25:
                    sp_lines += f"<br>&nbsp;&nbsp;(+{len(sp_sorted) - 25} more)"
                tip_data[location] = f"<b>{location}</b><br>{metric:,} species{sp_lines}"
            else:
                unknown_cl_count = len(loc_unknown_cl.get(location, set()))
                unknown_cl_line = (
                    f"<br>{unknown_cl_count} checklist{'s' if unknown_cl_count != 1 else ''}"
                    f" do not include a specific count for some species;"
                    f" these entries add 1 to the total."
                    if unknown_cl_count > 0 else ""
                )
                tip_data[location] = (
                    f"<b>{location}</b><br>{metric:,} {metric_label}{unknown_cl_line}"
                )

        import json
        tip_data_json = json.dumps(tip_data, ensure_ascii=False)

        for lat, lon, location, metric in points:
            marker = folium.CircleMarker(
                location=[lat, lon],
                radius=radius_for(metric),
                color="#2a5fad",
                weight=1,
                fill=True,
                fill_color=CHART_PRIMARY,
                fill_opacity=0.65,
            )
            marker.options["locationName"] = location
            marker.add_to(bubble_map)

        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        bubble_map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]], max_zoom=15)

        html = bubble_map.get_root().render()

        self._mapBridge = MapBridge(self)
        channel = QWebChannel(self.webView.page())
        channel.registerObject("bridge", self._mapBridge)
        self.webView.page().setWebChannel(channel)

        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        inject_js = f"""
<script>
{qwc_js}
(function() {{
    var tipDiv = document.createElement('div');
    tipDiv.style.cssText = (
        'position:fixed; display:none; pointer-events:none; z-index:9999;' +
        'background:#252730; color:#e2e4ec; border:1px solid {CHART_PRIMARY};' +
        'border-radius:6px; padding:6px 10px; font-size:12px;' +
        'max-width:300px; line-height:1.5;'
    );
    document.body.appendChild(tipDiv);
    var tipData = {tip_data_json};
    function findMap() {{
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {{
            try {{ var o = window[keys[i]]; if (o && o instanceof L.Map) return o; }}
            catch(e) {{}}
        }}
        return null;
    }}
    function init() {{
        var map = findMap();
        if (!map) {{ setTimeout(init, 150); return; }}
        new QWebChannel(qt.webChannelTransport, function(channel) {{
            window.bridge = channel.objects.bridge;
            map.eachLayer(function(layer) {{
                if (!(layer instanceof L.CircleMarker)) return;
                var name      = layer.options.locationName;
                var origColor = layer.options.color;
                var origWeight = layer.options.weight;
                if (!name) return;
                layer.on('click', function() {{
                    window.bridge.locationClicked(name);
                }});
                layer.on('mouseover', function(e) {{
                    this.setStyle({{ color: '#ff8800', weight: 3 }});
                    var html = tipData[name];
                    if (!html) return;
                    tipDiv.innerHTML = html;
                    tipDiv.style.display = 'block';
                    var mapCont = map.getContainer();
                    var mapRect = mapCont.getBoundingClientRect();
                    var pt = map.latLngToContainerPoint(e.target.getLatLng());
                    var GAP = 12;
                    var tipW = tipDiv.offsetWidth;
                    var tipH = tipDiv.offsetHeight;
                    var absX = pt.x > mapRect.width / 2
                        ? mapRect.left + pt.x - tipW - GAP
                        : mapRect.left + pt.x + GAP;
                    var absY = mapRect.top + pt.y - tipH / 2;
                    absY = Math.max(GAP, Math.min(absY, window.innerHeight - tipH - GAP));
                    tipDiv.style.left = absX + 'px';
                    tipDiv.style.top  = absY + 'px';
                }});
                layer.on('mouseout', function() {{
                    this.setStyle({{ color: origColor, weight: origWeight }});
                    tipDiv.style.display = 'none';
                }});
            }});
        }});
    }}
    init();
}})();
</script>"""
        html = html.replace("</body>", inject_js + self._satellite_toggle_js() + "\n</body>")

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        self._buildFilterTitle(filter, title, count=len(points), countUnit="Locations")

        return True


    def loadChoroplethWorldSubregion1(self, filter):

        return()


    def showLoadProgress(self, percent):

        if percent < 100:
            self.setWindowTitle(self.title + ": " + str(percent) + "%")
        else:
            self.setWindowTitle(self.title)


    def _ebirdGet(self, path, api_key):
        """HTTP GET to api.ebird.org; returns parsed JSON or None on error."""
        import urllib.request
        import urllib.error
        import json as _json
        url = "https://api.ebird.org" + path
        req = urllib.request.Request(url, headers={"X-eBirdApiToken": api_key})
        try:
            with urllib.request.urlopen(req, timeout=20, context=_SSL_CTX) as resp:
                return _json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None


    def _getEBirdRegionCode(self, filter):
        """Return (eBird_region_code, display_label) for the filter's location.

        Returns (None, None) if no geographic region can be determined.
        Location-type filters resolve to the county (or state as fallback).
        """
        locationType = filter.getLocationType()
        locationName = filter.getLocationName()
        db = self.mdiParent.db

        # Explorer-built filters carry the region code and display label directly.
        if locationType == "EBirdRegion":
            label = getattr(filter, "regionLabel", locationName) or locationName
            return locationName, label

        if locationType == "State":
            label = db.GetStateName(locationName) if locationName else locationName
            return locationName, label

        if locationType == "Country":
            label = db.GetCountryName(locationName) if locationName else locationName
            return locationName, label

        if locationType == "Location":
            # Return the eBird L-code directly; the spplist API accepts it and
            # gives the all-time species list for that specific location.
            loc_id = db.locationIDDict.get(locationName)
            if loc_id:
                return loc_id, locationName

        if locationType in ("County", "Location"):
            sightings = db.GetSightings(filter)
            if not sightings:
                return None, None
            state_code = sightings[0]["state"]          # "US-CO"
            state_abbr = state_code[3:] if len(state_code) > 3 else state_code
            county_raw = sightings[0]["county"].split(" (")[0]
            for fips, s_abbr in db.countyCodeDict.get(county_raw, []):
                if s_abbr == state_abbr:
                    code = f"US-{state_abbr}-{fips[2:]}"
                    return code, county_raw
            # Non-US: fall back to state
            return state_code, db.GetStateName(state_code)

        return None, None


    def _showRegionalTaxonomyError(self, message):
        """Render an error message inside the web view."""
        from PySide6.QtGui import QColor
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ background:#16171d; color:#e2e4ec;
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
       padding:40px; font-size:14px; }}
.err {{ color:#e07020; font-size:1.1em; margin-bottom:10px; font-weight:600; }}
</style></head>
<body><div class="err">Species List</div><p>{message}</p></body>
</html>"""
        self.webView.page().setBackgroundColor(QColor("#16171d"))
        self.webView.setHtml(html)
        self.resizeMe()
        self.scaleMe()
        self.title = "Species List"
        self.setWindowTitle("Species List")


    def _buildFilterDescription(self, filter):
        """Return a ' · '-separated string describing all active filter dimensions.

        Covers Standard and Photos filter fields, matching the logic in
        SetChildDetailsLabels in code_MainWindow.py.  Location is included so
        the subtitle clarifies which sightings drive the seen/unseen checkmarks.
        """
        db = self.mdiParent.db
        month_names = ["Jan","Feb","Mar","Apr","May","Jun",
                       "Jul","Aug","Sep","Oct","Nov","Dec"]
        parts = []

        # --- Location ---
        loc_type = filter.getLocationType()
        loc_name = filter.getLocationName()
        if loc_name:
            if loc_type == "Region":
                parts.append(db.GetRegionName(loc_name))
            elif loc_type == "Country":
                parts.append(db.GetCountryName(loc_name))
            elif loc_type == "State":
                parts.append(db.GetStateName(loc_name))
            else:
                parts.append(loc_name)

        # --- Taxonomy ---
        species = filter.getSpeciesName()
        family  = filter.getFamily()
        order   = filter.getOrder()
        search  = filter.getCommonNameSearch()
        if species:
            parts.append(species)
        elif family:
            parts.append(family)
        elif order:
            parts.append(order)
        if search:
            if "s:" in search and search.strip().lower().startswith("s:"):
                parts.append(f"Scientific name includes '{search.strip()[2:]}'")
            else:
                parts.append(f"Name includes '{search}'")

        # --- Date range ---
        sd, ed = filter.getStartDate(), filter.getEndDate()
        if sd:
            parts.append(sd if sd == ed else f"{sd} to {ed}")

        # --- Seasonal range ---
        sm, em = filter.getStartSeasonalMonth(), filter.getEndSeasonalMonth()
        if sm and em:
            sday = filter.getStartSeasonalDay()
            eday = filter.getEndSeasonalDay()
            parts.append(
                f"Season: {month_names[int(sm)-1]}-{sday} "
                f"to {month_names[int(em)-1]}-{eday}"
            )

        # --- Photo filter ---
        sp = filter.getSightingHasPhoto()
        sph = filter.getSpeciesHasPhoto()
        camera = filter.getCamera()
        lens   = filter.getLens()
        ss0, ss1 = filter.getStartShutterSpeed(), filter.getEndShutterSpeed()
        ap0, ap1 = filter.getStartAperture(),     filter.getEndAperture()
        fl0, fl1 = filter.getStartFocalLength(),  filter.getEndFocalLength()
        iso0, iso1 = filter.getStartIso(),        filter.getEndIso()
        r0, r1   = filter.getStartRating(),       filter.getEndRating()

        if sp == "Has photo":
            parts.append("Sightings with photos")
        elif sp == "No photo":
            parts.append("Sightings without photos")
        if sph == "Photographed":
            parts.append("Photographed species")
        elif sph == "Not photographed":
            parts.append("Unphotographed species")
        if camera:
            parts.append(camera)
        if lens:
            parts.append(lens)

        def _range_str(label, a, b):
            if a and b:
                return f"{label}: {a}" if a == b else f"{label}: {a}–{b}"
            if a:
                return f"{label}: from {a}"
            if b:
                return f"{label}: to {b}"
            return ""

        for s in [_range_str("Speed", ss0, ss1),
                  _range_str("Aperture", ap0, ap1),
                  _range_str("Focal length", fl0, fl1),
                  _range_str("ISO", iso0, iso1),
                  _range_str("Rating", r0, r1)]:
            if s:
                parts.append(s)

        return " · ".join(parts) if parts else "All species, locations, and dates"


    def loadRegionalTaxonomy(self, filter):
        """Fetch eBird regional taxonomy and display a seen/unseen species checklist."""
        import re
        import html as _html
        from copy import deepcopy
        from PySide6.QtGui import QColor, QCursor

        self.contentType = "Species List"
        self.filter = filter

        api_key = self.mdiParent.db.ebirdApiKey.strip()
        if not api_key:
            QMessageBox.warning(
                self.mdiParent,
                "eBird API Key Required",
                "No eBird API key is configured.\n\n"
                "Please add your key under Preferences.",
                QMessageBox.StandardButton.Ok,
            )
            return False

        region_code, region_label = self._getEBirdRegionCode(filter)
        # Prefer an explicit label on the filter (e.g. hotspot name) over the
        # county/state label that _getEBirdRegionCode derives from the location type.
        region_label = getattr(filter, "regionLabel", None) or region_label
        if not region_code:
            QMessageBox.warning(
                self.mdiParent,
                "Location Required",
                "The Regional Taxonomy requires a country, state, county, or location "
                "to be selected in the location filter.\n\n"
                "Please select a location and try again.",
                QMessageBox.StandardButton.Ok,
            )
            return False

        # Detect private vs. public location: the hotspot info endpoint returns
        # data for public hotspots and nothing for private L-codes.
        _is_private_loc = False
        if region_code.startswith("L") and region_code[1:].isdigit():
            _hs_info = self._ebirdGet(f"/v2/ref/hotspot/info/{region_code}", api_key)
            _is_private_loc = not isinstance(_hs_info, dict)

        # Strip photo- and recording-presence flags — the in-report buttons
        # handle those axes.  All other filter dimensions (camera, lens, date,
        # season, etc.) are kept.
        stripped_filter = deepcopy(filter)
        stripped_filter.setSightingHasPhoto("")
        stripped_filter.setSpeciesHasPhoto("")
        stripped_filter.setSpeciesHasRecording("")

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        try:
            species_codes = self._ebirdGet(f"/v2/product/spplist/{region_code}", api_key)
            if species_codes is None:
                QApplication.restoreOverrideCursor()
                self._showRegionalTaxonomyError(
                    f"Could not fetch species list for region '{region_code}'. "
                    "Check your API key."
                )
                return True

            taxonomy_entries = []
            batch_size = 500
            for i in range(0, len(species_codes), batch_size):
                codes_str = ",".join(species_codes[i:i + batch_size])
                batch = self._ebirdGet(
                    f"/v2/ref/taxonomy/ebird?fmt=json&species={codes_str}", api_key
                )
                if batch:
                    taxonomy_entries.extend(batch)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            self._showRegionalTaxonomyError(f"eBird API error: {exc}")
            return True

        QApplication.restoreOverrideCursor()

        # Keep only full species
        taxonomy_entries = [t for t in taxonomy_entries if t.get("category") == "species"]

        # Apply family / order / species filter
        filter_family  = stripped_filter.getFamily()
        filter_order   = stripped_filter.getOrder()
        filter_species = stripped_filter.getSpeciesName()

        def _base(name):
            return re.sub(r'\s*\([^)]*\)\s*$', '', name).strip()

        if filter_species:
            base = _base(filter_species)
            taxonomy_entries = [
                t for t in taxonomy_entries
                if t["comName"] == filter_species or t["comName"] == base
            ]
        elif filter_family:
            fam_sci = filter_family.split("(")[0].strip()
            taxonomy_entries = [
                t for t in taxonomy_entries if t.get("familySciName") == fam_sci
            ]
        elif filter_order:
            ord_name = filter_order.split("(")[0].strip()
            taxonomy_entries = [
                t for t in taxonomy_entries if t.get("order") == ord_name
            ]

        # GetSightings doesn't handle locationType="EBirdRegion", so remap it to
        # the equivalent native type before computing seen/photo/recording sets.
        # L-codes → "Location" (if the user has sightings there) or empty.
        # Country/state codes → "Country" / "State" (GetSightings handles both).
        # County codes (2 hyphens) → one region-info API call maps the code to
        # the eBird county name, which is also what the internal county keys use.
        _sf_lt = stripped_filter.getLocationType()
        _sf_ln = stripped_filter.getLocationName()
        _forced_empty = False
        if _sf_lt == "EBirdRegion":
            if _sf_ln.startswith("L") and _sf_ln[1:].isdigit():
                _db = self.mdiParent.db
                _inv = {v: k for k, v in _db.locationIDDict.items()}
                _resolved = _inv.get(_sf_ln)
                if _resolved and _resolved in _db.locationDict:
                    stripped_filter.setLocationType("Location")
                    stripped_filter.setLocationName(_resolved)
                else:
                    _forced_empty = True
            else:
                _hyphens = _sf_ln.count("-")
                _db = self.mdiParent.db
                if _hyphens == 0 and _sf_ln in _db.countryDict:
                    stripped_filter.setLocationType("Country")
                elif _hyphens == 1 and _sf_ln in _db.stateDict:
                    stripped_filter.setLocationType("State")
                elif _hyphens == 2:
                    # County code (e.g. US-CA-081).  Internal county keys are
                    # the plain eBird county name, or "Name (US-XX)" when the
                    # user has sightings in same-named counties in several
                    # states (see the parenthetical de-duplication in
                    # code_DataBase's file load).
                    _info = self._ebirdGet(f"/v2/ref/region/info/{_sf_ln}", api_key)
                    _cname = ""
                    if isinstance(_info, dict):
                        _cname = (_info.get("result") or "").split(",")[0].strip()
                    _state_code = "-".join(_sf_ln.split("-")[:2])
                    _qualified = f"{_cname} ({_state_code})"
                    if _cname and _cname in _db.countyDict:
                        stripped_filter.setLocationType("County")
                        stripped_filter.setLocationName(_cname)
                    elif _cname and _qualified in _db.countyDict:
                        stripped_filter.setLocationType("County")
                        stripped_filter.setLocationName(_qualified)
                    else:
                        # Lookup failed, or the user has no sightings there.
                        _forced_empty = True
                else:
                    # The user has no sightings in the selected country/state.
                    _forced_empty = True

        # Seen set: sightings passing the stripped filter
        sightings = [] if _forced_empty else self.mdiParent.db.GetSightings(stripped_filter)
        seen_set = set()
        for s in sightings:
            name = s["commonName"]
            seen_set.add(name)
            seen_set.add(_base(name))

        # Photo set: only when a media catalog is open
        photos_open = self.mdiParent.db.photoDataFileOpenFlag
        photo_set = set()
        if photos_open and not _forced_empty:
            photo_filter = deepcopy(stripped_filter)
            photo_filter.setSightingHasPhoto("Has photo")
            for s in self.mdiParent.db.GetSightings(photo_filter):
                if "photos" in s and s["photos"]:
                    name = s["commonName"]
                    photo_set.add(name)
                    photo_set.add(_base(name))

        # Recording set: mirrors the photo set exactly.  Built from the same
        # stripped_filter (already remapped/scoped above for every spawn path),
        # so a species only gets the microphone icon when the user recorded it
        # WITHIN this list's scope — e.g. recorded in Boulder County when the
        # list is for Boulder County, not merely recorded somewhere in their
        # lifetime.  The per-sighting audio check keeps the semantics
        # sighting-level (species-level fallbacks in the filter can't leak in).
        rec_set = set()
        if photos_open and not _forced_empty:
            rec_filter = deepcopy(stripped_filter)
            rec_filter.setSpeciesHasRecording("Recorded")
            for s in self.mdiParent.db.GetSightings(rec_filter):
                if s.get("audio"):
                    name = s["commonName"]
                    rec_set.add(name)
                    rec_set.add(_base(name))

        # Stats
        total        = len(taxonomy_entries)
        seen_count   = sum(1 for t in taxonomy_entries if t["comName"] in seen_set)
        unseen_count = total - seen_count
        pct          = round(seen_count * 100 / total) if total else 0

        # Group entries by family (preserving taxonomic order from API)
        families = []
        cur_fam_sci = None
        cur_fam_com = None
        cur_entries = []
        for t in taxonomy_entries:
            fam_sci = t.get("familySciName", "")
            fam_com = t.get("familyComName", "")
            if fam_sci != cur_fam_sci:
                if cur_entries:
                    families.append((cur_fam_sci, cur_fam_com, cur_entries))
                cur_fam_sci, cur_fam_com, cur_entries = fam_sci, fam_com, [t]
            else:
                cur_entries.append(t)
        if cur_entries:
            families.append((cur_fam_sci, cur_fam_com, cur_entries))

        # Build subtitle from stripped filter (photo-presence flags excluded)
        filter_desc = self._buildFilterDescription(stripped_filter)
        subtitle = f"Full species only · eBird taxonomy · {filter_desc}"

        self._pdf_data = {
            "type": "Species List",
            "region": region_label,
            "subtitle": subtitle,
            "total": total,
            "seen_count": seen_count,
            "unseen_count": unseen_count,
            "pct": pct,
            "photos_open": photos_open,
            "is_private_loc": _is_private_loc,
            "families": [
                {
                    "fam_sci": fam_sci,
                    "fam_com": fam_com,
                    "entries": [
                        {
                            "com": t["comName"],
                            "sci": t.get("sciName", ""),
                            "seen": t["comName"] in seen_set,
                            "photo": t["comName"] in photo_set,
                            "rec": t["comName"] in rec_set,
                        }
                        for t in entries
                    ]
                }
                for fam_sci, fam_com, entries in families
            ]
        }

        # Camera / microphone icons (photographed- and recorded-species
        # markers), embedded as data URIs — the report page can't fetch local
        # files, same as the map thumbnails.
        def _resource_b64(path):
            f = QFile(path)
            if not f.open(QIODevice.OpenModeFlag.ReadOnly):
                return ""
            data = base64.b64encode(bytes(f.readAll())).decode("ascii")
            f.close()
            return data

        cam_b64 = _resource_b64(":/icon_camera_yellow.png") if photos_open else ""
        mic_b64 = _resource_b64(":/icon_microphone_green.png") if photos_open else ""

        # Build species rows
        rows_html = ""
        for fam_sci, fam_com, entries in families:
            rows_html += (
                f'<div class="family-header">'
                f'<span class="fam-com">{_html.escape(fam_com).upper()}</span>'
                f'<span class="fam-sci">{_html.escape(fam_sci)}</span>'
                f'</div>\n'
            )
            for t in entries:
                com = t["comName"]
                sci = t.get("sciName", "")
                com_safe = _html.escape(com)
                sci_safe = _html.escape(sci)
                seen  = com in seen_set
                photo = com in photo_set
                rec   = com in rec_set
                row_cls  = "row seen" if seen else "row unseen"
                if photos_open:
                    row_cls += " photo-yes" if photo else " photo-no"
                    row_cls += " rec-yes" if rec else " rec-no"
                chk_html = ('<span class="check seen-check">&#10003;</span>'
                            if seen else
                            '<span class="check unseen-check"></span>')
                cam_html = ('<span class="cam-icon" title="Photographed"></span>'
                            if (photos_open and photo) else
                            '<span class="cam-absent"></span>' if photos_open else '')
                # The mic image itself lives ONCE in the page CSS (as
                # .mic-icon's background) — embedding the ~53KB data URI in
                # every recorded row pushed the page past setHtml()'s ~2MB
                # content limit, which silently renders a blank window (same
                # Qt limitation the choropleth maps hit; see loadCountyChoropleth).
                mic_html = ('<span class="mic-icon" title="Recorded"></span>'
                            if (photos_open and rec) else
                            '<span class="mic-absent"></span>' if photos_open else '')
                com_cls  = "com seen-name" if seen else "com unseen-name"
                rows_html += (
                    f'<div class="{row_cls}" data-species="{com_safe}">'
                    f'{chk_html}'
                    f'{cam_html}'
                    f'{mic_html}'
                    f'<span class="{com_cls}">{com_safe}</span>'
                    f'<span class="sci">{sci_safe}</span>'
                    f'</div>\n'
                )

        # Photo / recording filter buttons (only when catalog is open)
        photo_btns_html = ""
        if photos_open:
            photo_count = sum(1 for t in taxonomy_entries if t["comName"] in photo_set)
            no_photo_count = total - photo_count
            rec_count = sum(1 for t in taxonomy_entries if t["comName"] in rec_set)
            no_rec_count = total - rec_count
            photo_btns_html = f"""  <span class="filter-sep"></span>
  <button class="filter-btn photo-btn" onclick="setPhotoFilter('withphoto',this)">With Photo ({photo_count})</button>
  <button class="filter-btn photo-btn" onclick="setPhotoFilter('nophoto',this)">No Photo ({no_photo_count})</button>
  <span class="filter-sep"></span>
  <button class="filter-btn rec-btn" onclick="setRecFilter('withrec',this)">With Recording ({rec_count})</button>
  <button class="filter-btn rec-btn" onclick="setRecFilter('norec',this)">No Recording ({no_rec_count})</button>"""

        # Read Qt WebChannel JS
        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{
  background:#16171d; color:#e2e4ec;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:14px;
}}
.header {{ background:#1e1f26; padding:18px 28px 12px; border-bottom:1px solid #2a2b38; }}
.header h1 {{ font-size:1.45em; font-weight:700; margin-bottom:4px; }}
.header .subtitle {{ color:#8b8fa8; font-size:0.82em; }}
.header .attribution {{ color:#6b6f88; font-size:0.75em; margin-top:6px; }}
.header .attribution a {{ color:{CHART_PRIMARY}; text-decoration:none; }}
.header .attribution a:hover {{ text-decoration:underline; }}
.stats-bar {{
  background:#1a1b22; padding:14px 28px;
  display:flex; align-items:center; gap:24px;
  border-bottom:1px solid #2a2b38;
}}
.stat {{ min-width:55px; }}
.stat strong {{ font-size:1.9em; font-weight:700; display:block; }}
.stat span {{ font-size:0.72em; color:#8b8fa8; text-transform:uppercase; letter-spacing:.05em; }}
.progress-wrap {{ flex:1; height:10px; background:#2a2b38; border-radius:5px; overflow:hidden; margin:0 6px; }}
.progress-fill {{ height:100%; background:#e07020; border-radius:5px; width:{pct}%; }}
.pct {{ font-size:1.5em; font-weight:700; min-width:54px; text-align:right; }}
.pct small {{ font-size:.48em; color:#8b8fa8; text-transform:uppercase; display:block; }}
.filters {{
  padding:10px 28px; border-bottom:1px solid #2a2b38;
  background:#1e1f26; display:flex; align-items:center; gap:8px; flex-wrap:wrap;
}}
.filter-sep {{
  width:1px; height:20px; background:#3a3d4e; margin:0 4px;
}}
.filter-btn {{
  padding:5px 15px; border-radius:20px; cursor:pointer;
  font-size:0.83em; border:1px solid #3a3d4e;
  background:#252730; color:#e2e4ec;
}}
.filter-btn.active {{ background:#e07020; border-color:#e07020; color:#fff; font-weight:600; }}
.exotic-note {{
  padding:6px 28px; font-size:0.76em; color:#6b6f88;
  background:#1a1b22; border-bottom:1px solid #2a2b38;
}}
.species-list {{ padding:0 20px 40px 20px; }}
.family-header {{
  padding:14px 8px 3px 8px;
  border-bottom:1px solid #2a2b38; margin-bottom:1px;
}}
.fam-com {{ font-size:.8em; font-weight:700; color:{CHART_PRIMARY}; letter-spacing:.05em; }}
.fam-sci {{ font-size:.76em; color:#6b6f88; font-style:italic; margin-left:8px; }}
.row {{
  display:flex; align-items:center;
  padding:4px 8px; border-radius:4px; cursor:pointer;
}}
.row:hover {{ background:#252730; }}
.check {{
  width:20px; min-width:20px; height:20px;
  border-radius:3px; display:inline-flex;
  align-items:center; justify-content:center;
  margin-right:10px; font-size:12px; font-weight:bold;
}}
.seen-check {{ background:#e07020; color:#fff; }}
.unseen-check {{ border:2px solid #4a4d60; background:#1e1f26; }}
.com {{ }}
.seen-name {{ color:#8b8fa8; }}
.unseen-name {{ color:#e2e4ec; font-weight:600; }}
/* The camera and microphone icons render at the same 20px height as the
   orange .check box.  The artwork is padding-free with a transparent
   background, so each column's slot width comes from its icon's true aspect
   ratio (camera 480x416 → 23px, mic 332x512 → 13px); every slot in a column
   is that same width (absent included), keeping the columns and the species
   names aligned.  Each image is embedded ONCE here as a data URI (per-row
   embedding blew setHtml's ~2MB limit). */
.cam-icon {{
  width:23px; min-width:23px; height:20px;
  margin-right:10px;
  background-image:url("data:image/png;base64,{cam_b64}");
  background-repeat:no-repeat;
  background-position:center;
  background-size:auto 20px;
  display:inline-block;
}}
.cam-absent {{ width:23px; min-width:23px; margin-right:10px; display:inline-block; }}
.mic-icon {{
  width:13px; min-width:13px; height:20px;
  margin-right:10px;
  background-image:url("data:image/png;base64,{mic_b64}");
  background-repeat:no-repeat;
  background-position:center;
  background-size:auto 20px;
  display:inline-block;
}}
.mic-absent {{ width:13px; min-width:13px; margin-right:10px; display:inline-block; }}
.sci {{ color:#5a5d78; font-style:italic; font-size:.84em; margin-left:10px; }}
.hidden {{ display:none !important; }}
</style>
<script>{qwc_js}</script>
</head>
<body>
<div class="header">
  <h1>{region_label} Species List{"&nbsp;<span style='font-size:0.6em;font-weight:400;color:#8b8fa8;'>(Personal Location)</span>" if _is_private_loc else ""}</h1>
  <div class="subtitle">{subtitle}</div>
  <div class="attribution">Species data from <a href="https://ebird.org" target="_blank">eBird.org</a></div>
</div>
<div class="stats-bar">
  <div class="stat"><strong>{seen_count}</strong><span>Seen</span></div>
  <div class="stat"><strong>{unseen_count}</strong><span>Not Yet Seen</span></div>
  <div class="stat"><strong>{total}</strong><span>Total Species</span></div>
  <div class="progress-wrap"><div class="progress-fill"></div></div>
  <div class="pct">{pct}%<small>Complete</small></div>
</div>
<div class="filters">
  <button class="filter-btn seen-btn all-btn active" onclick="setSeenFilter('all',this)">All ({total})</button>
  <button class="filter-btn seen-btn" onclick="setSeenFilter('unseen',this)">Not Yet Seen ({unseen_count})</button>
  <button class="filter-btn seen-btn" onclick="setSeenFilter('seen',this)">Seen ({seen_count})</button>
{photo_btns_html}
</div>
<div class="exotic-note">&#9432;&nbsp; This checklist may include exotic or escaped species not yet removed from the eBird regional list.</div>
{"<div class='exotic-note'>&#9432;&nbsp; Personal location — this species list reflects your own sightings only.</div>" if _is_private_loc else ""}
<div class="species-list">{rows_html}</div>
<script>
var seenMode  = 'all';
var photoMode = 'all';
var recMode   = 'all';

function applyFilters() {{
  document.querySelectorAll('.row').forEach(function(row) {{
    var isSeen      = row.classList.contains('seen');
    var hasPhoto    = row.classList.contains('photo-yes');
    var hasRec      = row.classList.contains('rec-yes');
    var showBySeen  = seenMode  === 'all' ||
                      (seenMode  === 'seen'      &&  isSeen) ||
                      (seenMode  === 'unseen'    && !isSeen);
    var showByPhoto = photoMode === 'all' ||
                      (photoMode === 'withphoto' &&  hasPhoto) ||
                      (photoMode === 'nophoto'   && !hasPhoto);
    var showByRec   = recMode   === 'all' ||
                      (recMode   === 'withrec'   &&  hasRec) ||
                      (recMode   === 'norec'     && !hasRec);
    row.classList.toggle('hidden', !(showBySeen && showByPhoto && showByRec));
  }});
}}

function setSeenFilter(mode, btn) {{
  document.querySelectorAll('.seen-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  seenMode = mode;
  if (mode === 'all') {{
    // All resets the photo and recording axes too
    document.querySelectorAll('.photo-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.rec-btn').forEach(b => b.classList.remove('active'));
    photoMode = 'all';
    recMode   = 'all';
  }}
  applyFilters();
}}

function setPhotoFilter(mode, btn) {{
  document.querySelectorAll('.photo-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  // Deactivate the seen All button since we're no longer showing everything
  document.querySelectorAll('.all-btn').forEach(b => b.classList.remove('active'));
  photoMode = mode;
  applyFilters();
}}

function setRecFilter(mode, btn) {{
  document.querySelectorAll('.rec-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  // Deactivate the seen All button since we're no longer showing everything
  document.querySelectorAll('.all-btn').forEach(b => b.classList.remove('active'));
  recMode = mode;
  applyFilters();
}}

document.addEventListener("DOMContentLoaded", function() {{
  new QWebChannel(qt.webChannelTransport, function(channel) {{
    window.bridge = channel.objects.bridge;
    document.querySelectorAll('.row').forEach(function(row) {{
      row.addEventListener('click', function() {{
        var sp = row.getAttribute('data-species');
        if (sp && window.bridge) window.bridge.speciesClicked(sp);
      }});
    }});
  }});
}});
</script>
</body>
</html>"""

        self._regionalTaxonomyBridge = RegionalTaxonomyBridge(self)
        channel = QWebChannel(self.webView.page())
        channel.registerObject("bridge", self._regionalTaxonomyBridge)
        self.webView.page().setWebChannel(channel)

        self.webView.page().setBackgroundColor(QColor("#16171d"))
        self.webView.setHtml(html)
        self.resizeMe()
        self.scaleMe()

        title = f"Species List: {region_label}"
        self.title = title
        self.setWindowTitle(title)
        return True


    # ------------------------------------------------------------------
    # Notable Community Sightings
    # ------------------------------------------------------------------

    def _renderNotableError(self, message):
        from PySide6.QtGui import QColor
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ background:#16171d; color:#e2e4ec;
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
       padding:40px; font-size:14px; }}
.err {{ color:#e07020; font-size:1.1em; margin-bottom:10px; font-weight:600; }}
</style></head>
<body><div class="err">Notable Community Sightings</div><p>{message}</p></body>
</html>"""
        self.webView.page().setBackgroundColor(QColor("#16171d"))
        self.webView.setHtml(html)
        self.resizeMe()
        self.scaleMe()
        self.title = "Notable Sightings"
        self.setWindowTitle("Notable Sightings")


    def loadNotableSightings(self, filter):
        """Fetch eBird notable/rare community sightings for the most restrictive
        geography in the filter.  Date filter settings are ignored; always fetches
        the past 3 days from the eBird API."""
        import html as _html
        from datetime import datetime, timedelta
        from collections import defaultdict
        from PySide6.QtGui import QColor, QCursor

        BACK_DAYS = 3
        self.contentType = "Notable Sightings"
        self.filter = filter

        api_key = self.mdiParent.db.ebirdApiKey.strip()
        if not api_key:
            QMessageBox.warning(
                self.mdiParent,
                "eBird API Key Required",
                "No eBird API key is configured.\n\nPlease add your key under Preferences.",
                QMessageBox.StandardButton.Ok,
            )
            return False

        # For a specific location use its eBird location ID directly;
        # for all other geography types use the standard region-code endpoint.
        db = self.mdiParent.db
        loc_type = filter.getLocationType()
        loc_name = filter.getLocationName()

        if loc_type == "Location" and loc_name:
            loc_id = db.locationIDDict.get(loc_name, "")
            if loc_id:
                api_path    = (f"/v2/data/obs/{loc_id}/recent/notable"
                               f"?detail=full&back={BACK_DAYS}")
                region_label    = loc_name
                notable_region_id = loc_id
            else:
                # Location ID not available — fall back to county/state
                region_code, region_label = self._getEBirdRegionCode(filter)
                api_path = (f"/v2/data/obs/{region_code}/recent/notable"
                            f"?detail=full&back={BACK_DAYS}") if region_code else None
                notable_region_id = region_code
        else:
            region_code, region_label = self._getEBirdRegionCode(filter)
            api_path = (f"/v2/data/obs/{region_code}/recent/notable"
                        f"?detail=full&back={BACK_DAYS}") if region_code else None
            notable_region_id = region_code

        if not api_path:
            QMessageBox.warning(
                self.mdiParent,
                "Location Required",
                "Notable Community Sightings requires a country, state, county, "
                "or specific location to be selected in the location filter.\n\n"
                "Please select a location and try again.",
                QMessageBox.StandardButton.Ok,
            )
            return False

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        try:
            observations = self._ebirdGet(api_path, api_key)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            self._renderNotableError(f"eBird API error: {exc}")
            return True
        QApplication.restoreOverrideCursor()

        if observations is None:
            self._renderNotableError(
                f"Could not fetch notable sightings for '{region_label}'. "
                "Check your eBird API key and internet connection."
            )
            return True

        self._communityRegionId    = notable_region_id
        self._communityRegionLabel = region_label

        # Group observations by species
        species_obs         = defaultdict(list)
        species_sci         = {}
        species_code_map    = {}
        species_category    = {}
        species_taxon_order = {}
        for obs in observations:
            com = obs.get("comName", "").strip()
            if not com:
                continue
            species_obs[com].append(obs)
            if com not in species_sci:
                species_sci[com]      = obs.get("sciName", "")
                species_code_map[com] = obs.get("speciesCode", "")
                species_category[com] = obs.get("category", "")
                try:
                    species_taxon_order[com] = float(obs.get("taxonOrder", 0) or 0)
                except (ValueError, TypeError):
                    species_taxon_order[com] = 0.0

        # Sort species taxonomically using the taxonOrder field from the API response
        species_list = sorted(
            species_obs.keys(),
            key=lambda c: (species_taxon_order.get(c, 0.0), c),
        )

        total_species = len(species_list)
        total_obs     = len(observations)

        today      = datetime.now()

        # Build seen-species sets for badge determination.
        # We only populate state_set / county_set when the report geography
        # is specific enough to make those badges meaningful.
        current_year  = str(today.year)
        check_country = None   # 2-char country code e.g. "US"
        check_state   = None   # state code e.g. "US-CO"
        check_county  = None   # county name e.g. "Boulder"

        if loc_type == "Country":
            check_country = loc_name
        elif loc_type == "State":
            check_state = loc_name
            if "-" in loc_name:
                check_country = loc_name.split("-")[0]
        elif loc_type == "County":
            check_county = loc_name
            _county_s = db.countyDict.get(loc_name, [])
            if _county_s:
                check_country = _county_s[0]["country"]
                check_state   = _county_s[0]["state"]
            elif " (" in loc_name and loc_name.endswith(")"):
                check_state = loc_name[loc_name.rfind("(") + 1 : -1]
        elif loc_type == "Location":
            _loc_s = db.locationDict.get(loc_name, [])
            if _loc_s:
                check_country = _loc_s[0]["country"]
                check_state  = _loc_s[0]["state"]
                check_county = _loc_s[0]["county"]
        elif loc_type == "EBirdRegion":
            # L-codes (e.g. "L1234567") are specific eBird locations, not
            # hierarchical region codes — country/state/county can't be derived.
            _is_lcode = loc_name.startswith("L") and loc_name[1:].isdigit()
            if not _is_lcode:
                _dashes = loc_name.count("-")
                check_country = loc_name.split("-")[0]
                if _dashes >= 1:
                    check_state = loc_name if _dashes == 1 else loc_name.rsplit("-", 1)[0]
                if _dashes >= 2:
                    _lbl = region_label
                    for _sfx in (" County", " Parish", " Borough", " Municipality",
                                 " Census Area", " Municipio", " District"):
                        if _lbl.endswith(_sfx):
                            _lbl = _lbl[:-len(_sfx)].strip()
                            break
                    if _lbl:
                        check_county = _lbl

        def _base(name):
            return name[:name.index(" (")].strip() if " (" in name else name

        life_set    = set()
        country_set = set()
        state_set   = set()
        county_set  = set()
        year_set    = set()
        for _s in db.sightingList:
            _n = _s["commonName"]
            _b = _base(_n)
            life_set.add(_n);  life_set.add(_b)
            if check_country and _s["country"] == check_country: country_set.add(_n); country_set.add(_b)
            if check_state   and _s["state"]   == check_state:   state_set.add(_n);  state_set.add(_b)
            if check_county  and (_s["county"] == check_county or
                                  _s["county"].startswith(check_county + " (")):
                county_set.add(_n); county_set.add(_b)
            if _s["date"][:4] == current_year: year_set.add(_n); year_set.add(_b)
        start_date = today - timedelta(days=BACK_DAYS - 1)
        date_range = (
            f"{start_date.strftime('%b')} {start_date.day} – "
            f"{today.strftime('%b')} {today.day}, {today.year}"
        )

        def _fmt_dt(raw):
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    month = dt.strftime("%b")
                    if fmt == "%Y-%m-%d %H:%M":
                        hour = str(int(dt.strftime("%I")))
                        return f"{month} {dt.day}, {dt.year}  {hour}:{dt.strftime('%M')} {dt.strftime('%p')}"
                    return f"{month} {dt.day}, {dt.year}"
                except ValueError:
                    pass
            return raw

        # Build species-block HTML
        tag_counts = {"life": 0, "country": 0, "state": 0, "county": 0, "year": 0}
        rows_html = ""
        _pdf_species_list = []
        for com in species_list:
            obs_list = species_obs[com]
            sci      = species_sci.get(com, "")
            sp_code  = species_code_map.get(com, "")

            # Dedupe here so the badge count reflects unique sightings
            _seen_keys = set()
            _deduped = []
            for _o in obs_list:
                _key = (_o.get("locName", ""), _o.get("obsDt", ""), _o.get("userDisplayName", ""))
                if _key not in _seen_keys:
                    _seen_keys.add(_key)
                    _deduped.append(_o)
            obs_list = _deduped

            n        = len(obs_list)
            badge    = f"{n} report{'s' if n != 1 else ''}"

            is_hybrid = (species_category.get(com, "") == "hybrid") or (" x " in com)
            com_class = "com com-hybrid" if is_hybrid else "com"
            _lookup = _base(com)

            tags = []
            tags_html = ""
            if not is_hybrid:
                if _lookup not in life_set:
                    tags.append("life")
                    tags_html += '<span class="sp-tag tag-life">Life</span>'
                if check_country and _lookup not in country_set:
                    tags.append("country")
                    tags_html += '<span class="sp-tag tag-country">Country</span>'
                if check_state and _lookup not in state_set:
                    tags.append("state")
                    tags_html += '<span class="sp-tag tag-state">State</span>'
                if check_county and _lookup not in county_set:
                    tags.append("county")
                    tags_html += '<span class="sp-tag tag-county">County</span>'
                if _lookup not in year_set:
                    tags.append("year")
                    tags_html += '<span class="sp-tag tag-year">Year</span>'
            for _t in tags:
                tag_counts[_t] += 1
            data_tags = " ".join(tags)
            if tags_html:
                tags_html = f'<span class="sp-tags">{tags_html}</span>'

            sighting_rows = ""
            _pdf_obs = []
            for obs in obs_list:
                loc      = _html.escape(obs.get("locName", ""))
                dt_str   = _fmt_dt(obs.get("obsDt", ""))
                how_many = obs.get("howMany")
                count_str = str(how_many) if how_many else ""
                observer  = _html.escape(obs.get("userDisplayName", ""))
                sub_id    = _html.escape(obs.get("subId", ""))
                ebird_btn = (
                    f'<span class="ebird-link" onclick="openChecklist(\'{sub_id}\')">'
                    f'View &#8599;</span>'
                    if sub_id else ""
                )
                review_tag = (
                    '<em style="color:#2e7d32;margin-left:6px;">Confirmed</em>'
                    if obs.get("obsReviewed", False)
                    else '<em style="color:#c0392b;margin-left:6px;">Unreviewed</em>'
                )
                sighting_rows += (
                    f'<div class="sighting">'
                    f'<span class="loc">{loc}</span>'
                    f'<span class="dt">{dt_str}</span>'
                    f'<span class="count">{count_str}</span>'
                    f'{review_tag}'
                    f'{ebird_btn}'
                    f'</div>\n'
                )
                _pdf_obs.append({
                    "loc": obs.get("locName", ""),
                    "dt": dt_str,
                    "count": count_str,
                    "reviewed": obs.get("obsReviewed", False),
                })
            _pdf_species_list.append({
                "com": com,
                "sci": sci,
                "is_hybrid": is_hybrid,
                "tags": list(tags),
                "obs": _pdf_obs,
            })

            primary_tag = next(
                (t for t in ("life", "country", "state", "county", "year") if t in tags), ""
            )
            if sp_code:
                map_btn = (
                    f'<span class="map-locs-btn" '
                    f'data-code="{_html.escape(sp_code)}" data-name="{_html.escape(com)}" '
                    f'data-tag="{primary_tag}" '
                    f'onclick="event.stopPropagation(); handleMapLocs(this)">'
                    f'Map Locations</span>'
                )
            else:
                map_btn = ""

            com_onclick = (
                f' onclick="event.stopPropagation(); handleSpeciesClick({_html.escape(json.dumps(com))})"'
                if not is_hybrid else ""
            )
            rows_html += (
                f'<div class="sp-block" data-tags="{data_tags}">'
                f'<div class="sp-hdr" onclick="toggleBlock(this)">'
                f'<span class="toggle">+</span>'
                f'<span class="{com_class}"{com_onclick}>{_html.escape(com)}</span>'
                f'<span class="sci">{_html.escape(sci)}</span>'
                f'{tags_html}'
                f'<span class="row-actions">{map_btn}<span class="badge">{badge}</span></span>'
                f'</div>'
                f'<div class="sightings" style="display:none">{sighting_rows}</div>'
                f'</div>\n'
            )

        self._pdf_data = {
            "type": "Notable Community Sightings",
            "region": region_label,
            "date_range": date_range,
            "back_days": BACK_DAYS,
            "total_species": total_species,
            "total_obs": total_obs,
            "species": _pdf_species_list,
        }

        # Build filter bar (tag buttons left, Map All button right)
        _fb = [f'<button class="filter-btn f-all active" onclick="setTagFilter(\'all\',this)">All ({total_species})</button>']
        if tag_counts["life"]    > 0: _fb.append(f'<button class="filter-btn f-life"    onclick="setTagFilter(\'life\',this)">Life ({tag_counts["life"]})</button>')
        if check_country and tag_counts["country"] > 0: _fb.append(f'<button class="filter-btn f-country" onclick="setTagFilter(\'country\',this)">Country ({tag_counts["country"]})</button>')
        if check_state   and tag_counts["state"]   > 0: _fb.append(f'<button class="filter-btn f-state"   onclick="setTagFilter(\'state\',this)">State ({tag_counts["state"]})</button>')
        if check_county  and tag_counts["county"]  > 0: _fb.append(f'<button class="filter-btn f-county"  onclick="setTagFilter(\'county\',this)">County ({tag_counts["county"]})</button>')
        if tag_counts["year"]    > 0: _fb.append(f'<button class="filter-btn f-year"    onclick="setTagFilter(\'year\',this)">Year ({tag_counts["year"]})</button>')
        _map_btn = '<button class="map-all-btn" onclick="handleMapAll()">Map All</button>'
        if len(_fb) > 1:
            filter_bar_html = f'<div class="filters">{"".join(_fb)}{_map_btn}</div>'
        else:
            filter_bar_html = f'<div class="filters">{_map_btn}</div>'

        if not rows_html:
            rows_html = (
                '<div style="padding:40px;text-align:center;color:#8b8fa8;font-style:italic;">'
                f'No notable sightings reported in {_html.escape(region_label)} '
                f'in the past {BACK_DAYS} days.</div>'
            )

        # Read Qt WebChannel JS
        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{
  background:#16171d; color:#e2e4ec;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:14px;
}}
.header {{ background:#1e1f26; padding:18px 28px 12px; border-bottom:1px solid #2a2b38; }}
.header h1 {{ font-size:1.45em; font-weight:700; margin-bottom:4px; }}
.header h2 {{ font-size:1.45em; font-weight:700; margin-top:2px; }}
.header .sub {{ color:#8b8fa8; font-size:0.82em; margin-top:4px; }}
.header .attr {{ color:#6b6f88; font-size:0.75em; margin-top:6px; }}
.header .attr a {{ color:{CHART_PRIMARY}; text-decoration:none; }}
.header .attr a:hover {{ text-decoration:underline; }}
.stats-bar {{
  background:#1a1b22; padding:12px 28px;
  display:flex; align-items:center; gap:32px;
  border-bottom:1px solid #2a2b38;
}}
.stat strong {{ font-size:1.7em; font-weight:700; display:block; line-height:1.1; }}
.stat span {{ font-size:0.72em; color:#8b8fa8; text-transform:uppercase; letter-spacing:.05em; }}
.list {{ padding:16px 20px 40px; }}
.sp-block {{
  background:#1e1f26; border-radius:6px;
  margin-bottom:12px; border:1px solid #2a2b38; overflow:hidden;
}}
.sp-hdr {{
  display:flex; align-items:center; gap:12px;
  padding:9px 16px; background:#252730; border-bottom:1px solid #2a2b38;
  cursor:pointer; user-select:none;
}}
.sp-hdr:hover {{ background:#2d2e3a; }}
.toggle {{
  color:#8b8fa8; font-size:0.85em; min-width:14px;
  text-align:center; flex-shrink:0;
}}
.com {{ font-weight:700; color:{CHART_PRIMARY}; font-size:1.0em; cursor:pointer; }}
.com:hover {{ text-decoration:underline; }}
.com-hybrid {{ color:#8b8fa8; cursor:default; }}
.com-hybrid:hover {{ text-decoration:none; }}
.sci {{ font-size:0.82em; color:#6b6f88; font-style:italic; }}
.sp-tags {{ display:flex; gap:5px; flex-shrink:0; }}
.sp-tag {{
  font-size:0.68em; font-weight:700; padding:2px 9px;
  border-radius:10px; white-space:nowrap; letter-spacing:.03em;
}}
.tag-life    {{ background:#c0392b; color:#fff; }}
.tag-country {{ background:#e07020; color:#fff; }}
.tag-state   {{ background:#2e7d32; color:#fff; }}
.tag-county  {{ background:#4488EE; color:#fff; }}
.tag-year    {{ background:transparent; color:#d0d4e8; border:1px solid #6b6f88; }}
.row-actions {{
  margin-left:auto; display:flex; gap:8px; align-items:center; flex-shrink:0;
}}
.badge {{
  font-size:0.74em; color:#8b8fa8;
  background:#1e1f26; border:1px solid #3a3d4e;
  border-radius:10px; padding:2px 10px; white-space:nowrap;
}}
.map-locs-btn {{
  color:{CHART_PRIMARY}; font-size:0.8em; cursor:pointer;
  padding:2px 10px; border-radius:4px; border:1px solid {CHART_PRIMARY}88;
  white-space:nowrap; user-select:none;
}}
.map-locs-btn:hover {{ background:{CHART_PRIMARY}22; }}
.filters {{
  padding:10px 20px; border-bottom:1px solid #2a2b38;
  background:#1e1f26; display:flex; align-items:center; gap:8px; flex-wrap:wrap;
}}
.filter-btn {{
  padding:4px 14px; border-radius:20px; cursor:pointer;
  font-size:0.78em; font-weight:600; border:1px solid #3a3d4e;
  background:#252730; color:#e2e4ec;
}}
.filter-btn.active {{ border-color:#e07020; color:#fff; font-weight:700; }}
.filter-btn.f-all.active     {{ background:#e07020; }}
.filter-btn.f-life.active    {{ background:#c0392b; border-color:#c0392b; }}
.filter-btn.f-country.active {{ background:#e07020; border-color:#e07020; }}
.filter-btn.f-state.active   {{ background:#2e7d32; border-color:#2e7d32; }}
.filter-btn.f-county.active  {{ background:#4488EE; border-color:#4488EE; }}
.filter-btn.f-year.active    {{ background:transparent; color:#d0d4e8; border-color:#8b8fa8; }}
.map-all-btn {{
  margin-left:auto; padding:4px 14px; border-radius:20px; cursor:pointer;
  font-size:0.78em; font-weight:600;
  color:{CHART_PRIMARY}; border:1px solid {CHART_PRIMARY}88; background:#252730;
}}
.map-all-btn:hover {{ background:{CHART_PRIMARY}22; }}
.sp-block.hidden {{ display:none; }}
.sighting {{
  display:flex; align-items:center; gap:10px;
  padding:6px 16px; border-bottom:1px solid #2a2b38;
  font-size:0.87em;
}}
.sighting:last-child {{ border-bottom:none; }}
.loc {{ flex:1; color:#e2e4ec; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.dt {{ color:#8b8fa8; min-width:160px; white-space:nowrap; }}
.count {{ color:#8b8fa8; min-width:28px; text-align:right; font-size:0.85em; }}
.observer {{ color:#6b6f88; min-width:130px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:0.85em; }}
.ebird-link {{
  color:{CHART_PRIMARY}; font-size:0.8em; cursor:pointer;
  padding:2px 8px; border-radius:4px; border:1px solid #3a4a60;
  white-space:nowrap; user-select:none;
}}
.ebird-link:hover {{ background:{CHART_PRIMARY}22; }}
</style>
<script>{qwc_js}</script>
</head>
<body>
<div class="header">
  <h1>Notable Community Sightings</h1>
  <h2>{_html.escape(region_label)}</h2>
  <div class="sub">{date_range} &nbsp;&middot;&nbsp; Past {BACK_DAYS} days</div>
  <div class="attr">Sightings data from <a href="https://ebird.org" target="_blank">eBird.org</a></div>
</div>
<div class="stats-bar">
  <div class="stat"><strong>{total_species}</strong><span>Notable Species</span></div>
  <div class="stat"><strong>{total_obs}</strong><span>Reports</span></div>
</div>
{filter_bar_html}
<div class="list">{rows_html}</div>
<script>
var activeTag = 'all';
function applyTagFilter() {{
  document.querySelectorAll('.sp-block').forEach(function(b) {{
    var tags = b.getAttribute('data-tags') || '';
    b.classList.toggle('hidden', activeTag !== 'all' && tags.indexOf(activeTag) === -1);
  }});
}}
function setTagFilter(tag, btn) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  activeTag = tag;
  applyTagFilter();
}}
document.addEventListener("DOMContentLoaded", function() {{
  new QWebChannel(qt.webChannelTransport, function(channel) {{
    window.bridge = channel.objects.bridge;
  }});
}});
function openChecklist(subId) {{
  if (window.bridge) window.bridge.openChecklist(subId);
}}
function handleSpeciesClick(name) {{
  if (window.bridge) window.bridge.speciesClicked(name);
}}
function handleMapLocs(el) {{
  if (window.bridge) window.bridge.showSpeciesMap(
    el.getAttribute('data-code'),
    el.getAttribute('data-name'),
    el.getAttribute('data-tag') || ''
  );
}}
function handleMapAll() {{
  if (window.bridge) window.bridge.showNotableMap();
}}
function toggleBlock(hdr) {{
  var body = hdr.nextElementSibling;
  var btn  = hdr.querySelector('.toggle');
  if (body.style.display === 'none') {{
    body.style.display = '';
    btn.textContent = '−';
  }} else {{
    body.style.display = 'none';
    btn.textContent = '+';
  }}
}}
</script>
</body>
</html>"""

        _all_obs = [obs for obs_list in species_obs.values() for obs in obs_list]
        self._notableBridge = NotableSightingsBridge(
            self, notable_region_id, region_label, BACK_DAYS, api_key,
            species_obs=dict(species_obs),
            all_observations=_all_obs,
        )
        channel = QWebChannel(self.webView.page())
        channel.registerObject("bridge", self._notableBridge)
        self.webView.page().setWebChannel(channel)

        self.webView.page().setBackgroundColor(QColor("#16171d"))

        import tempfile, os as _os
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", encoding="utf-8", delete=False
        )
        tmp.write(html)
        tmp.close()
        self._notableTmpFile = tmp.name
        self.webView.load(QUrl.fromLocalFile(tmp.name))

        self.resizeMe()
        self.scaleMe()

        title = f"Notable Community Sightings: {region_label}"
        self.title = title
        self.setWindowTitle(title)
        return True


    # ------------------------------------------------------------------
    # All Community Sightings
    # ------------------------------------------------------------------

    def _renderAllError(self, message):
        from PySide6.QtGui import QColor
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ background:#16171d; color:#e2e4ec;
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
       padding:40px; font-size:14px; }}
.err {{ color:#e07020; font-size:1.1em; margin-bottom:10px; font-weight:600; }}
</style></head>
<body><div class="err">All Community Sightings</div><p>{message}</p></body>
</html>"""
        self.webView.page().setBackgroundColor(QColor("#16171d"))
        self.webView.setHtml(html)
        self.resizeMe()
        self.scaleMe()
        self.title = "All Community Sightings"
        self.setWindowTitle("All Community Sightings")


    def loadAllSightings(self, filter):
        """Fetch recent eBird community sightings (all species) for the filter geography.
        Shows the most recent observation per species; an 'All Locations' button spawns
        a child window with the full per-species location list."""
        import html as _html
        from datetime import datetime, timedelta
        from collections import defaultdict
        from PySide6.QtGui import QColor, QCursor

        BACK_DAYS = 3
        self.contentType = "All Community Sightings"
        self.filter = filter

        api_key = self.mdiParent.db.ebirdApiKey.strip()
        if not api_key:
            QMessageBox.warning(
                self.mdiParent,
                "eBird API Key Required",
                "No eBird API key is configured.\n\nPlease add your key under Preferences.",
                QMessageBox.StandardButton.Ok,
            )
            return False

        db = self.mdiParent.db
        loc_type = filter.getLocationType()
        loc_name = filter.getLocationName()

        if loc_type == "Location" and loc_name:
            region_id = db.locationIDDict.get(loc_name, "")
            if region_id:
                region_label = loc_name
            else:
                region_id, region_label = self._getEBirdRegionCode(filter)
        else:
            region_id, region_label = self._getEBirdRegionCode(filter)

        if not region_id:
            QMessageBox.warning(
                self.mdiParent,
                "Location Required",
                "All Community Sightings requires a country, state, county, or specific "
                "location to be selected in the location filter.\n\n"
                "Please select a location and try again.",
                QMessageBox.StandardButton.Ok,
            )
            return False

        # Persist region so child windows spawned from map dots can inherit badge context
        self._communityRegionId    = region_id
        self._communityRegionLabel = region_label

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        observations = self._ebirdGet(
            f"/v2/data/obs/{region_id}/recent?detail=full&back={BACK_DAYS}&includeProvisional=true",
            api_key,
        )
        QApplication.restoreOverrideCursor()

        if observations is None:
            self._renderAllError(
                f"Could not fetch sightings for '{region_label}'. "
                "Check your eBird API key and internet connection."
            )
            return True

        # Build local taxon order lookup — the /recent endpoint omits taxonOrder
        local_taxon_order = {}
        for _s in db.sightingList:
            _n = _s["commonName"]
            if _n not in local_taxon_order:
                try:
                    local_taxon_order[_n] = float(_s["taxonomicOrder"] or 0)
                except (ValueError, TypeError):
                    pass

        # Group by species; capture species code and taxon order
        species_obs         = defaultdict(list)
        species_sci         = {}
        species_code_map    = {}
        species_category    = {}
        species_taxon_order = {}
        for obs in observations:
            com = obs.get("comName", "").strip()
            if not com:
                continue
            species_obs[com].append(obs)
            if com not in species_sci:
                species_sci[com]      = obs.get("sciName", "")
                species_code_map[com] = obs.get("speciesCode", "")
                species_category[com] = obs.get("category", "")

        # For species not in the user's sighting list (life birds), use the full
        # eBird taxonomy reference stored on db to get correct taxon order.
        _full_taxon = getattr(db, "taxonOrderBySciName", {})
        for com, sci in species_sci.items():
            if com not in local_taxon_order and sci:
                order = _full_taxon.get(sci)
                if order:
                    local_taxon_order[com] = order

        for obs in observations:
            com = obs.get("comName", "").strip()
            if not com or com in species_taxon_order:
                continue
            try:
                api_order = float(obs.get("taxonOrder", 0) or 0)
                species_taxon_order[com] = api_order if api_order else local_taxon_order.get(com, float("inf"))
            except (ValueError, TypeError):
                species_taxon_order[com] = local_taxon_order.get(com, float("inf"))

        # Sort each species' observations most-recent-first; sort species taxonomically
        for com in species_obs:
            species_obs[com].sort(key=lambda o: o.get("obsDt", ""), reverse=True)
        species_list = sorted(
            species_obs.keys(),
            key=lambda c: (species_taxon_order.get(c, float("inf")), c),
        )

        total_species = len(species_list)

        today      = datetime.now()
        start_date = today - timedelta(days=BACK_DAYS - 1)
        date_range = (
            f"{start_date.strftime('%b')} {start_date.day} – "
            f"{today.strftime('%b')} {today.day}, {today.year}"
        )

        def _fmt_dt(raw):
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    month = dt.strftime("%b")
                    if fmt == "%Y-%m-%d %H:%M":
                        hour = str(int(dt.strftime("%I")))
                        return f"{month} {dt.day}, {dt.year}  {hour}:{dt.strftime('%M')} {dt.strftime('%p')}"
                    return f"{month} {dt.day}, {dt.year}"
                except ValueError:
                    pass
            return raw

        # Badge sets — same logic as Notable Sightings
        current_year   = str(today.year)
        _is_single_loc = (loc_type == "EBirdRegion"
                          and loc_name.startswith("L")
                          and loc_name[1:].isdigit())
        _single_lat = observations[0].get("lat") if (_is_single_loc and observations) else None
        _single_lng = observations[0].get("lng") if (_is_single_loc and observations) else None

        check_country = None
        check_state   = None
        check_county  = None
        if loc_type == "Country":
            check_country = loc_name
        elif loc_type == "State":
            check_state = loc_name
            if "-" in loc_name:
                check_country = loc_name.split("-")[0]
        elif loc_type == "County":
            check_county = loc_name
            _county_s = db.countyDict.get(loc_name, [])
            if _county_s:
                check_country = _county_s[0]["country"]
                check_state   = _county_s[0]["state"]
            elif " (" in loc_name and loc_name.endswith(")"):
                check_state = loc_name[loc_name.rfind("(") + 1 : -1]
        elif loc_type == "Location":
            _loc_s = db.locationDict.get(loc_name, [])
            if _loc_s:
                check_country = _loc_s[0]["country"]
                check_state  = _loc_s[0]["state"]
                check_county = _loc_s[0]["county"]
        elif loc_type == "EBirdRegion":
            if not _is_single_loc:
                # Hierarchical code — derive context directly from the code
                _dashes = loc_name.count("-")
                check_country = loc_name.split("-")[0]
                if _dashes >= 1:
                    check_state = loc_name if _dashes == 1 else loc_name.rsplit("-", 1)[0]
                if _dashes >= 2:
                    _lbl = region_label
                    for _sfx in (" County", " Parish", " Borough", " Municipality",
                                 " Census Area", " Municipio", " District"):
                        if _lbl.endswith(_sfx):
                            _lbl = _lbl[:-len(_sfx)].strip()
                            break
                    if _lbl:
                        check_county = _lbl
            elif getattr(filter, "_badgeCountry", None):
                # Spawned from map dot: hotspot API resolved full hierarchy
                check_country = filter._badgeCountry
                check_state   = getattr(filter, "_badgeState",  None)
                check_county  = getattr(filter, "_badgeCounty", None)
            else:
                # Private location — hotspot API unavailable; inherit parent region
                _badge_id  = getattr(filter, "_badgeRegionId",    None)
                _badge_lbl = getattr(filter, "_badgeRegionLabel", None)
                if _badge_id:
                    _dashes = _badge_id.count("-")
                    check_country = _badge_id.split("-")[0]
                    if _dashes >= 1:
                        check_state = _badge_id if _dashes == 1 else _badge_id.rsplit("-", 1)[0]
                    if _dashes >= 2:
                        _lbl = _badge_lbl or ""
                        for _sfx in (" County", " Parish", " Borough", " Municipality",
                                     " Census Area", " Municipio", " District"):
                            if _lbl.endswith(_sfx):
                                _lbl = _lbl[:-len(_sfx)].strip()
                                break
                        if _lbl:
                            check_county = _lbl

        def _base(name):
            return name[:name.index(" (")].strip() if " (" in name else name

        life_set    = set()
        country_set = set()
        state_set   = set()
        county_set  = set()
        year_set    = set()
        for _s in db.sightingList:
            _n = _s["commonName"]
            _b = _base(_n)
            life_set.add(_n);  life_set.add(_b)
            if check_country and _s["country"] == check_country: country_set.add(_n); country_set.add(_b)
            if check_state   and _s["state"]   == check_state:   state_set.add(_n);  state_set.add(_b)
            if check_county  and (_s["county"] == check_county or
                                  _s["county"].startswith(check_county + " (")):
                county_set.add(_n); county_set.add(_b)
            if _s["date"][:4] == current_year: year_set.add(_n); year_set.add(_b)

        # Build species-block HTML (one visible row per species, no collapse toggle)
        tag_counts = {"life": 0, "country": 0, "state": 0, "county": 0, "year": 0}
        rows_html = ""
        _pdf_species_list = []
        for com in species_list:
            obs_list    = species_obs[com]
            sci         = species_sci.get(com, "")
            sp_code     = species_code_map.get(com, "")
            most_recent = obs_list[0]

            is_hybrid = (species_category.get(com, "") == "hybrid") or (" x " in com)
            com_class = "com com-hybrid" if is_hybrid else "com"
            _lookup = _base(com)

            tags = []
            tags_html = ""
            if not is_hybrid:
                if _lookup not in life_set:
                    tags.append("life")
                    tags_html += '<span class="sp-tag tag-life">Life</span>'
                if check_country and _lookup not in country_set:
                    tags.append("country")
                    tags_html += '<span class="sp-tag tag-country">Country</span>'
                if check_state and _lookup not in state_set:
                    tags.append("state")
                    tags_html += '<span class="sp-tag tag-state">State</span>'
                if check_county and _lookup not in county_set:
                    tags.append("county")
                    tags_html += '<span class="sp-tag tag-county">County</span>'
                if _lookup not in year_set:
                    tags.append("year")
                    tags_html += '<span class="sp-tag tag-year">Year</span>'
            for _t in tags:
                tag_counts[_t] += 1
            data_tags = " ".join(tags)
            if tags_html:
                tags_html = f'<span class="sp-tags">{tags_html}</span>'

            _mr_count = str(most_recent.get("howMany")) if most_recent.get("howMany") else ""
            _pdf_species_list.append({
                "com": com,
                "sci": sci,
                "is_hybrid": is_hybrid,
                "tags": list(tags),
                "loc": most_recent.get("locName", ""),
                "dt": _fmt_dt(most_recent.get("obsDt", "")),
                "count": _mr_count,
                "num_locations": len(obs_list),
            })

            primary_tag = next(
                (t for t in ("life", "country", "state", "county", "year") if t in tags), ""
            )
            if sp_code:
                _esc_code = _html.escape(sp_code)
                _esc_com  = _html.escape(com)
                _map_locs = (
                    f'<span class="map-locs-btn" data-code="{_esc_code}" data-name="{_esc_com}" '
                    f'data-tag="{primary_tag}" '
                    f'onclick="handleMapLocs(this)">Map Locations</span>'
                    if not _is_single_loc else ""
                )
                row_actions = (
                    f'<span class="row-actions">'
                    f'{_map_locs}'
                    f'<span class="all-locs-btn" data-code="{_esc_code}" data-name="{_esc_com}" '
                    f'onclick="handleAllLocs(this)">All Locations &#8599;</span>'
                    f'</span>'
                )
            else:
                row_actions = ""

            loc       = _html.escape(most_recent.get("locName", ""))
            dt_str    = _fmt_dt(most_recent.get("obsDt", ""))
            how_many  = most_recent.get("howMany")
            count_str = str(how_many) if how_many else ""
            observer  = _html.escape(most_recent.get("userDisplayName", ""))
            sub_id    = _html.escape(most_recent.get("subId", ""))
            ebird_btn = (
                f'<span class="ebird-link" onclick="openChecklist(\'{sub_id}\')">'
                f'View &#8599;</span>'
                if sub_id else ""
            )
            sighting_row = (
                f'<div class="sighting">'
                f'<span class="loc">{loc}</span>'
                f'<span class="dt">{dt_str}</span>'
                f'<span class="count">{count_str}</span>'
                f'{ebird_btn}'
                f'</div>'
            )

            com_onclick = (
                f' onclick="handleSpeciesClick({_html.escape(json.dumps(com))})"'
                if not is_hybrid else ""
            )
            rows_html += (
                f'<div class="sp-block" data-tags="{data_tags}">'
                f'<div class="sp-hdr">'
                f'<span class="{com_class}"{com_onclick}>{_html.escape(com)}</span>'
                f'<span class="sci">{_html.escape(sci)}</span>'
                f'{tags_html}'
                f'{row_actions}'
                f'</div>'
                f'<div class="sightings">{sighting_row}</div>'
                f'</div>\n'
            )

        self._pdf_data = {
            "type": "All Community Sightings",
            "region": region_label,
            "date_range": date_range,
            "back_days": BACK_DAYS,
            "total_species": total_species,
            "species": _pdf_species_list,
        }

        # Build filter bar
        _fb = [f'<button class="filter-btn f-all active" onclick="setTagFilter(\'all\',this)">All ({total_species})</button>']
        if tag_counts["life"]    > 0: _fb.append(f'<button class="filter-btn f-life"    onclick="setTagFilter(\'life\',this)">Life ({tag_counts["life"]})</button>')
        if check_country and tag_counts["country"] > 0: _fb.append(f'<button class="filter-btn f-country" onclick="setTagFilter(\'country\',this)">Country ({tag_counts["country"]})</button>')
        if check_state   and tag_counts["state"]   > 0: _fb.append(f'<button class="filter-btn f-state"   onclick="setTagFilter(\'state\',this)">State ({tag_counts["state"]})</button>')
        if check_county  and tag_counts["county"]  > 0: _fb.append(f'<button class="filter-btn f-county"  onclick="setTagFilter(\'county\',this)">County ({tag_counts["county"]})</button>')
        if tag_counts["year"]    > 0: _fb.append(f'<button class="filter-btn f-year"    onclick="setTagFilter(\'year\',this)">Year ({tag_counts["year"]})</button>')
        filter_bar_html = f'<div class="filters">{"".join(_fb)}</div>' if len(_fb) > 1 else ""

        if not rows_html:
            rows_html = (
                '<div style="padding:40px;text-align:center;color:#8b8fa8;font-style:italic;">'
                f'No sightings reported in {_html.escape(region_label)} '
                f'in the past {BACK_DAYS} days.</div>'
            )

        if _is_single_loc:
            # When there are no observations, lat/lng are unavailable from the data;
            # query the hotspot info API as a fallback so the buttons always render.
            if _single_lat is None and api_key:
                _hs = self._ebirdGet(f"/v2/ref/hotspot/info/{loc_name}", api_key)
                if isinstance(_hs, dict):
                    _single_lat = _hs.get("latitude")
                    _single_lng = _hs.get("longitude")

            _esc_label = _html.escape(region_label)
            _esc_loc   = _html.escape(loc_name)
            _taxonomy_btn = (
                f'<span class="show-map-btn" '
                f'data-locid="{_esc_loc}" data-name="{_esc_label}" '
                f'onclick="handleShowChecklist(this)">All-time List</span>'
            )
            _map_btn = ""
            if _single_lat is not None and _single_lng is not None:
                _map_btn = (
                    f'<span class="show-map-btn" '
                    f'data-lat="{_single_lat}" data-lng="{_single_lng}" '
                    f'data-name="{_esc_label}" '
                    f'onclick="handleShowMap(this)">Map</span>'
                )
            _single_loc_buttons = (
                f'<div class="single-loc-actions">{_taxonomy_btn}{_map_btn}</div>'
            )
        else:
            _single_loc_buttons = ""

        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{
  background:#16171d; color:#e2e4ec;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:14px;
}}
.header {{ background:#1e1f26; padding:18px 28px 12px; border-bottom:1px solid #2a2b38; }}
.header h1 {{ font-size:1.45em; font-weight:700; margin-bottom:4px; }}
.header h2 {{ font-size:1.45em; font-weight:700; margin-top:2px; }}
.header .sub {{ color:#8b8fa8; font-size:0.82em; margin-top:4px; }}
.header .attr {{ color:#6b6f88; font-size:0.75em; margin-top:6px; }}
.header .attr a {{ color:{CHART_PRIMARY}; text-decoration:none; }}
.header .attr a:hover {{ text-decoration:underline; }}
.stats-bar {{
  background:#1a1b22; padding:12px 28px;
  display:flex; align-items:center; gap:32px;
  border-bottom:1px solid #2a2b38;
}}
.stat strong {{ font-size:1.7em; font-weight:700; display:block; line-height:1.1; }}
.stat span {{ font-size:0.72em; color:#8b8fa8; text-transform:uppercase; letter-spacing:.05em; }}
.list {{ padding:16px 20px 40px; }}
.sp-block {{
  background:#1e1f26; border-radius:6px;
  margin-bottom:12px; border:1px solid #2a2b38; overflow:hidden;
}}
.sp-hdr {{
  display:flex; align-items:center; gap:12px;
  padding:9px 16px; background:#252730; border-bottom:1px solid #2a2b38;
}}
.com {{ font-weight:700; color:{CHART_PRIMARY}; font-size:1.0em; cursor:pointer; }}
.com:hover {{ text-decoration:underline; }}
.com-hybrid {{ color:#8b8fa8; cursor:default; }}
.com-hybrid:hover {{ text-decoration:none; }}
.sci {{ font-size:0.82em; color:#6b6f88; font-style:italic; }}
.sp-tags {{ display:flex; gap:5px; flex-shrink:0; }}
.sp-tag {{
  font-size:0.68em; font-weight:700; padding:2px 9px;
  border-radius:10px; white-space:nowrap; letter-spacing:.03em;
}}
.tag-life    {{ background:#c0392b; color:#fff; }}
.tag-country {{ background:#e07020; color:#fff; }}
.tag-state   {{ background:#2e7d32; color:#fff; }}
.tag-county  {{ background:#4488EE; color:#fff; }}
.tag-year    {{ background:transparent; color:#d0d4e8; border:1px solid #6b6f88; }}
.badge {{
  margin-left:auto; font-size:0.74em; color:#8b8fa8;
  background:#1e1f26; border:1px solid #3a3d4e;
  border-radius:10px; padding:2px 10px; white-space:nowrap;
}}
.row-actions {{
  margin-left:auto; display:flex; gap:8px; align-items:center; flex-shrink:0;
}}
.all-locs-btn {{
  color:#e2e4ec; font-size:0.8em; cursor:pointer;
  padding:2px 10px; border-radius:4px; border:1px solid #6b6f88;
  white-space:nowrap; user-select:none;
}}
.all-locs-btn:hover {{ background:#2d3040; }}
.map-locs-btn {{
  color:{CHART_PRIMARY}; font-size:0.8em; cursor:pointer;
  padding:2px 10px; border-radius:4px; border:1px solid {CHART_PRIMARY}88;
  white-space:nowrap; user-select:none;
}}
.map-locs-btn:hover {{ background:{CHART_PRIMARY}22; }}
.single-loc-actions {{
  display:flex; flex-direction:column; gap:5px; margin-left:auto; flex-shrink:0;
}}
.show-map-btn {{
  color:{CHART_PRIMARY}; font-size:1.2em; cursor:pointer;
  padding:2px 10px; border-radius:4px; border:1px solid {CHART_PRIMARY}88;
  white-space:nowrap; user-select:none; text-align:center; display:block;
}}
.show-map-btn:hover {{ background:{CHART_PRIMARY}22; }}
.filters {{
  padding:10px 20px; border-bottom:1px solid #2a2b38;
  background:#1e1f26; display:flex; align-items:center; gap:8px; flex-wrap:wrap;
}}
.filter-btn {{
  padding:4px 14px; border-radius:20px; cursor:pointer;
  font-size:0.78em; font-weight:600; border:1px solid #3a3d4e;
  background:#252730; color:#e2e4ec;
}}
.filter-btn.active {{ border-color:#e07020; color:#fff; font-weight:700; }}
.filter-btn.f-all.active     {{ background:#e07020; }}
.filter-btn.f-life.active    {{ background:#c0392b; border-color:#c0392b; }}
.filter-btn.f-country.active {{ background:#e07020; border-color:#e07020; }}
.filter-btn.f-state.active   {{ background:#2e7d32; border-color:#2e7d32; }}
.filter-btn.f-county.active  {{ background:#4488EE; border-color:#4488EE; }}
.filter-btn.f-year.active    {{ background:transparent; color:#d0d4e8; border-color:#8b8fa8; }}
.sp-block.hidden {{ display:none; }}
.sighting {{
  display:flex; align-items:center; gap:10px;
  padding:6px 16px; border-bottom:1px solid #2a2b38;
  font-size:0.87em;
}}
.sighting:last-child {{ border-bottom:none; }}
.loc {{ flex:1; color:#e2e4ec; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.dt {{ color:#8b8fa8; min-width:160px; white-space:nowrap; }}
.count {{ color:#8b8fa8; min-width:28px; text-align:right; font-size:0.85em; }}
.observer {{ color:#6b6f88; min-width:130px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:0.85em; }}
.ebird-link {{
  color:{CHART_PRIMARY}; font-size:0.8em; cursor:pointer;
  padding:2px 8px; border-radius:4px; border:1px solid #3a4a60;
  white-space:nowrap; user-select:none;
}}
.ebird-link:hover {{ background:{CHART_PRIMARY}22; }}
</style>
<script>{qwc_js}</script>
</head>
<body>
<div class="header">
  <h1>All Community Sightings</h1>
  <h2>{_html.escape(region_label)}</h2>
  <div class="sub">{date_range} &nbsp;&middot;&nbsp; Past {BACK_DAYS} days</div>
  <div class="attr" style="display:flex;align-items:center;">
    <span>Sightings from <a href="https://ebird.org" target="_blank">eBird.org</a>. Some sightings may be provisional or exotic.<br>Most recent location for each species.</span>
    {_single_loc_buttons}
  </div>
</div>
<div class="stats-bar">
  <div class="stat"><strong>{total_species}</strong><span>Species</span></div>
</div>
{filter_bar_html}
<div class="list">{rows_html}</div>
<script>
var activeTag = 'all';
function applyTagFilter() {{
  document.querySelectorAll('.sp-block').forEach(function(b) {{
    var tags = b.getAttribute('data-tags') || '';
    b.classList.toggle('hidden', activeTag !== 'all' && tags.indexOf(activeTag) === -1);
  }});
}}
function setTagFilter(tag, btn) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  activeTag = tag;
  applyTagFilter();
}}
document.addEventListener("DOMContentLoaded", function() {{
  new QWebChannel(qt.webChannelTransport, function(channel) {{
    window.bridge = channel.objects.bridge;
  }});
}});
function openChecklist(subId) {{
  if (window.bridge) window.bridge.openChecklist(subId);
}}
function handleSpeciesClick(name) {{
  if (window.bridge) window.bridge.speciesClicked(name);
}}
function handleAllLocs(el) {{
  if (window.bridge) window.bridge.showAllLocations(
    el.getAttribute('data-code'),
    el.getAttribute('data-name')
  );
}}
function handleMapLocs(el) {{
  if (window.bridge) window.bridge.showSpeciesMap(
    el.getAttribute('data-code'),
    el.getAttribute('data-name'),
    el.getAttribute('data-tag') || ''
  );
}}
function handleShowMap(el) {{
  if (window.bridge) window.bridge.showSingleLocationMap(
    el.getAttribute('data-name'),
    el.getAttribute('data-lat'),
    el.getAttribute('data-lng')
  );
}}
function handleShowChecklist(el) {{
  if (window.bridge) window.bridge.showRegionalTaxonomy(
    el.getAttribute('data-locid'),
    el.getAttribute('data-name')
  );
}}
</script>
</body>
</html>"""

        self._allSightingsBridge = AllSightingsBridge(
            self, region_id, region_label, BACK_DAYS, api_key
        )
        channel = QWebChannel(self.webView.page())
        channel.registerObject("bridge", self._allSightingsBridge)
        self.webView.page().setWebChannel(channel)

        self.webView.page().setBackgroundColor(QColor("#16171d"))

        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", encoding="utf-8", delete=False
        )
        tmp.write(html)
        tmp.close()
        self._allSightingsTmpFile = tmp.name
        self.webView.load(QUrl.fromLocalFile(tmp.name))

        self.resizeMe()
        self.scaleMe()

        title = f"All Community Sightings: {region_label}"
        self.title = title
        self.setWindowTitle(title)
        return True


    def loadNotableMapFromObs(self, observations, filter, region_label, back_days):
        """Build the Notable Community Sightings map from pre-fetched observations.

        Skips the API call; uses lat/lng already present from the detail=full fetch.
        Colour priority per dot: orange (life) > blue (state) > yellow (county) > white.
        """
        import folium
        import html as _html2
        import json as _json
        import tempfile
        from copy import deepcopy
        from collections import defaultdict
        from datetime import datetime

        self.contentType = "Notable Map"
        self.filter = deepcopy(filter)

        if not observations:
            return False

        db = self.mdiParent.db

        loc_type = filter.getLocationType()
        loc_name = filter.getLocationName()

        check_country = None
        check_state   = None
        check_county  = None
        if loc_type == "Country":
            check_country = loc_name
        elif loc_type == "State":
            check_state = loc_name
            if "-" in loc_name:
                check_country = loc_name.split("-")[0]
        elif loc_type == "County":
            check_county = loc_name
            _county_s = db.countyDict.get(loc_name, [])
            if _county_s:
                check_country = _county_s[0]["country"]
                check_state   = _county_s[0]["state"]
            elif " (" in loc_name and loc_name.endswith(")"):
                check_state = loc_name[loc_name.rfind("(") + 1 : -1]
        elif loc_type == "Location":
            _loc_s = db.locationDict.get(loc_name, [])
            if _loc_s:
                check_country = _loc_s[0]["country"]
                check_state  = _loc_s[0]["state"]
                check_county = _loc_s[0]["county"]
        elif loc_type == "EBirdRegion":
            # L-codes (e.g. "L1234567") are specific eBird locations, not
            # hierarchical region codes — country/state/county can't be derived.
            _is_lcode = loc_name.startswith("L") and loc_name[1:].isdigit()
            if not _is_lcode:
                _dashes = loc_name.count("-")
                check_country = loc_name.split("-")[0]
                if _dashes >= 1:
                    check_state = loc_name if _dashes == 1 else loc_name.rsplit("-", 1)[0]
                if _dashes >= 2:
                    _lbl = region_label
                    for _sfx in (" County", " Parish", " Borough", " Municipality",
                                 " Census Area", " Municipio", " District"):
                        if _lbl.endswith(_sfx):
                            _lbl = _lbl[:-len(_sfx)].strip()
                            break
                    if _lbl:
                        check_county = _lbl

        def _base(name):
            return name[:name.index(" (")].strip() if " (" in name else name

        life_set    = set()
        country_set = set()
        state_set   = set()
        county_set  = set()
        for _s in db.sightingList:
            _n = _s["commonName"]
            _b = _base(_n)
            life_set.add(_n);  life_set.add(_b)
            if check_country and _s["country"] == check_country: country_set.add(_n); country_set.add(_b)
            if check_state   and _s["state"]   == check_state:   state_set.add(_n);  state_set.add(_b)
            if check_county  and (_s["county"] == check_county or
                                  _s["county"].startswith(check_county + " (")):
                county_set.add(_n); county_set.add(_b)

        loc_obs    = defaultdict(list)
        loc_coords = {}
        for obs in observations:
            loc = obs.get("locName", "").strip()
            if not loc:
                continue
            loc_obs[loc].append(obs)
            if loc not in loc_coords:
                try:
                    lat = float(obs.get("lat") or 0)
                    lng = float(obs.get("lng") or 0)
                    if lat != 0.0 or lng != 0.0:
                        loc_coords[loc] = (lat, lng, obs.get("locId", ""))
                except (ValueError, TypeError):
                    pass

        COLOR_LIFE    = "#c0392b"
        COLOR_COUNTRY = "#e07020"
        COLOR_STATE   = "#2e7d32"
        COLOR_COUNTY  = "#4488EE"
        COLOR_OTHER   = "#FFFFFF"

        points = []
        for loc, obs_list in loc_obs.items():
            if loc not in loc_coords:
                continue
            lat, lng, loc_id = loc_coords[loc]

            seen_sp = []
            for obs in obs_list:
                com = obs.get("comName", "").strip()
                if com and com not in seen_sp:
                    seen_sp.append(com)

            has_life = has_country = has_state = has_county = False
            for com in seen_sp:
                if " x " in com:
                    continue
                _lk = _base(com)
                if _lk not in life_set:
                    has_life = True
                    break
            if not has_life:
                for com in seen_sp:
                    if " x " in com:
                        continue
                    _lk = _base(com)
                    if check_country and _lk not in country_set:
                        has_country = True
                        break
            if not has_life and not has_country:
                for com in seen_sp:
                    if " x " in com:
                        continue
                    _lk = _base(com)
                    if check_state and _lk not in state_set:
                        has_state = True
                        break
            if not has_life and not has_country and not has_state:
                for com in seen_sp:
                    if " x " in com:
                        continue
                    _lk = _base(com)
                    if check_county and _lk not in county_set:
                        has_county = True
                        break

            if has_life:
                color = COLOR_LIFE
            elif has_country:
                color = COLOR_COUNTRY
            elif has_state:
                color = COLOR_STATE
            elif has_county:
                color = COLOR_COUNTY
            else:
                color = COLOR_OTHER

            points.append((lat, lng, loc, loc_id, color, seen_sp))

        if not points:
            return False

        avg_lat = sum(p[0] for p in points) / len(points)
        avg_lng = sum(p[1] for p in points) / len(points)

        notable_map = folium.Map(
            location=[avg_lat, avg_lng],
            zoom_start=7,
            tiles="CartoDB Voyager",
        )

        tip_data = {}
        for lat, lng, loc, loc_id, color, sp_list in points:
            sp_lines = ""
            for sp in sp_list[:25]:
                _lk = _base(sp)
                _esc = _html2.escape(sp)
                if " x " not in sp and _lk not in life_set:
                    sp_lines += (f'<br>&nbsp;&nbsp;<span style="color:{COLOR_LIFE}">'
                                 f'{_esc} (Life)</span>')
                elif " x " not in sp and check_country and _lk not in country_set:
                    sp_lines += (f'<br>&nbsp;&nbsp;<span style="color:{COLOR_COUNTRY}">'
                                 f'{_esc} (Country)</span>')
                elif " x " not in sp and check_state and _lk not in state_set:
                    sp_lines += (f'<br>&nbsp;&nbsp;<span style="color:{COLOR_STATE}">'
                                 f'{_esc} (State)</span>')
                elif " x " not in sp and check_county and _lk not in county_set:
                    sp_lines += (f'<br>&nbsp;&nbsp;<span style="color:{COLOR_COUNTY}">'
                                 f'{_esc} (County)</span>')
                else:
                    sp_lines += f"<br>&nbsp;&nbsp;{_esc}"
            if len(sp_list) > 25:
                sp_lines += f"<br>&nbsp;&nbsp;(+{len(sp_list) - 25} more)"
            tip_data[loc] = f"<b>{_html2.escape(loc)}</b>{sp_lines}"

        tip_data_json = _json.dumps(tip_data, ensure_ascii=False)

        for lat, lng, loc, loc_id, color, sp_list in points:
            marker = folium.CircleMarker(
                location=[lat, lng],
                radius=12,
                color="#555555",
                weight=1,
                fill=True,
                fill_color=color,
                fill_opacity=0.88,
            )
            marker.options["locationName"] = loc
            marker.options["locationId"]   = loc_id
            marker.add_to(notable_map)

        lats = [p[0] for p in points]
        lngs = [p[1] for p in points]
        notable_map.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]], max_zoom=15)

        html = notable_map.get_root().render()

        inject_js = f"""
<script>
(function() {{
    var tipDiv = document.createElement('div');
    tipDiv.style.cssText = (
        'position:fixed; display:none; pointer-events:none; z-index:9999;' +
        'background:#252730; color:#e2e4ec; border:1px solid #FF8C00;' +
        'border-radius:6px; padding:6px 10px; font-size:12px;' +
        'max-width:300px; line-height:1.5;'
    );
    document.body.appendChild(tipDiv);
    var tipData = {tip_data_json};
    function findMap() {{
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {{
            try {{ var o = window[keys[i]]; if (o && o instanceof L.Map) return o; }}
            catch(e) {{}}
        }}
        return null;
    }}
    function init() {{
        var map = findMap();
        if (!map) {{ setTimeout(init, 150); return; }}
        map.eachLayer(function(layer) {{
            if (!(layer instanceof L.CircleMarker)) return;
            var name      = layer.options.locationName;
            var origColor = layer.options.color;
            var origWeight = layer.options.weight;
            if (!name) return;
            layer.on('mouseover', function(e) {{
                this.setStyle({{ color: '#ffffff', weight: 2 }});
                var html = tipData[name];
                if (!html) return;
                tipDiv.innerHTML = html;
                tipDiv.style.display = 'block';
                var mapCont = map.getContainer();
                var mapRect = mapCont.getBoundingClientRect();
                var pt = map.latLngToContainerPoint(e.target.getLatLng());
                var GAP = 12;
                var tipW = tipDiv.offsetWidth;
                var tipH = tipDiv.offsetHeight;
                var absX = pt.x > mapRect.width / 2
                    ? mapRect.left + pt.x - tipW - GAP
                    : mapRect.left + pt.x + GAP;
                var absY = mapRect.top + pt.y - tipH / 2;
                absY = Math.max(GAP, Math.min(absY, window.innerHeight - tipH - GAP));
                tipDiv.style.left = absX + 'px';
                tipDiv.style.top  = absY + 'px';
            }});
            layer.on('mouseout', function() {{
                this.setStyle({{ color: origColor, weight: origWeight }});
                tipDiv.style.display = 'none';
            }});
        }});
    }}
    init();
}})();
</script>"""
        click_js = """
<script>
(function() {
    new QWebChannel(qt.webChannelTransport, function(channel) {
        window.csBridge = channel.objects.csBridge;
    });
    function initClick() {
        var map = null;
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {
            try { var o = window[keys[i]]; if (o && o instanceof L.Map) { map = o; break; } }
            catch(e) {}
        }
        if (!map) { setTimeout(initClick, 150); return; }
        map.eachLayer(function(layer) {
            if (!(layer instanceof L.CircleMarker)) return;
            var locId   = layer.options.locationId;
            var locName = layer.options.locationName;
            if (!locId) return;
            layer.on('click', function() {
                if (window.csBridge) window.csBridge.locationClicked(locId, locName);
            });
        });
    }
    initClick();
})();
</script>"""
        _qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        _qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        _qwc_block = "\n<script>" + bytes(_qwc_file.readAll()).decode("utf-8") + "</script>"
        _qwc_file.close()
        html = html.replace("</body>", inject_js + _qwc_block + click_js + self._satellite_toggle_js() + "\n</body>")

        self._csSightingsMapBridge = CommunitySightingsMapBridge(self)
        cs_channel = QWebChannel(self.webView.page())
        cs_channel.registerObject("csBridge", self._csSightingsMapBridge)
        self.webView.page().setWebChannel(cs_channel)

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))

        title = f"Notable Community Sightings Map: {region_label}"
        self.title = title
        self.setWindowTitle(title)
        self.resizeMe()
        self.scaleMe()
        return True


    def loadNotableMap(self, filter):
        """Fetch eBird notable sightings for the filter's region and show a colour-coded
        Folium map.  One dot per location; colour priority: orange (life bird) > blue
        (state bird) > yellow (county bird) > white (nothing new)."""
        import folium
        import json as _json
        import tempfile
        from copy import deepcopy
        from collections import defaultdict
        from datetime import datetime, timedelta
        from PySide6.QtGui import QCursor

        BACK_DAYS = 3
        self.contentType = "Notable Map"
        self.filter = deepcopy(filter)

        db = self.mdiParent.db
        api_key = db.ebirdApiKey.strip()
        if not api_key:
            QMessageBox.warning(
                self.mdiParent,
                "eBird API Key Required",
                "No eBird API key is configured.\n\nPlease add your key under Preferences.",
                QMessageBox.StandardButton.Ok,
            )
            return False

        loc_type = filter.getLocationType()
        loc_name = filter.getLocationName()

        if loc_type == "Location" and loc_name:
            loc_id = db.locationIDDict.get(loc_name, "")
            if loc_id:
                api_path     = f"/v2/data/obs/{loc_id}/recent/notable?detail=full&back={BACK_DAYS}"
                region_label = loc_name
            else:
                region_code, region_label = self._getEBirdRegionCode(filter)
                api_path = (f"/v2/data/obs/{region_code}/recent/notable"
                            f"?detail=full&back={BACK_DAYS}") if region_code else None
        else:
            region_code, region_label = self._getEBirdRegionCode(filter)
            api_path = (f"/v2/data/obs/{region_code}/recent/notable"
                        f"?detail=full&back={BACK_DAYS}") if region_code else None

        if not api_path:
            QMessageBox.warning(
                self.mdiParent,
                "Location Required",
                "Notable Community Sightings Map requires a country, state, county, "
                "or specific location to be selected in the location filter.\n\n"
                "Please select a location and try again.",
                QMessageBox.StandardButton.Ok,
            )
            return False

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        try:
            observations = self._ebirdGet(api_path, api_key)
        except Exception:
            QApplication.restoreOverrideCursor()
            return False
        QApplication.restoreOverrideCursor()

        if not observations:
            QMessageBox.information(
                self.mdiParent,
                "No Notable Sightings",
                f"No notable sightings found for '{region_label}' in the past {BACK_DAYS} days.",
                QMessageBox.StandardButton.Ok,
            )
            return False

        # Build badge sets — same logic as loadNotableSightings
        today         = datetime.now()
        current_year  = str(today.year)
        check_country = None
        check_state   = None
        check_county  = None

        if loc_type == "Country":
            check_country = loc_name
        elif loc_type == "State":
            check_state = loc_name
            if "-" in loc_name:
                check_country = loc_name.split("-")[0]
        elif loc_type == "County":
            check_county = loc_name
            _county_s = db.countyDict.get(loc_name, [])
            if _county_s:
                check_country = _county_s[0]["country"]
                check_state   = _county_s[0]["state"]
            elif " (" in loc_name and loc_name.endswith(")"):
                check_state = loc_name[loc_name.rfind("(") + 1 : -1]
        elif loc_type == "Location":
            _loc_s = db.locationDict.get(loc_name, [])
            if _loc_s:
                check_country = _loc_s[0]["country"]
                check_state  = _loc_s[0]["state"]
                check_county = _loc_s[0]["county"]
        elif loc_type == "EBirdRegion":
            # L-codes (e.g. "L1234567") are specific eBird locations, not
            # hierarchical region codes — country/state/county can't be derived.
            _is_lcode = loc_name.startswith("L") and loc_name[1:].isdigit()
            if not _is_lcode:
                _dashes = loc_name.count("-")
                check_country = loc_name.split("-")[0]
                if _dashes >= 1:
                    check_state = loc_name if _dashes == 1 else loc_name.rsplit("-", 1)[0]
                if _dashes >= 2:
                    _lbl = region_label
                    for _sfx in (" County", " Parish", " Borough", " Municipality",
                                 " Census Area", " Municipio", " District"):
                        if _lbl.endswith(_sfx):
                            _lbl = _lbl[:-len(_sfx)].strip()
                            break
                    if _lbl:
                        check_county = _lbl

        def _base(name):
            return name[:name.index(" (")].strip() if " (" in name else name

        life_set    = set()
        country_set = set()
        state_set   = set()
        county_set  = set()
        for _s in db.sightingList:
            _n = _s["commonName"]
            _b = _base(_n)
            life_set.add(_n);  life_set.add(_b)
            if check_country and _s["country"] == check_country: country_set.add(_n); country_set.add(_b)
            if check_state   and _s["state"]   == check_state:   state_set.add(_n);  state_set.add(_b)
            if check_county  and (_s["county"] == check_county or
                                  _s["county"].startswith(check_county + " (")):
                county_set.add(_n); county_set.add(_b)

        # Group by location name; collect coords and species list
        loc_obs    = defaultdict(list)
        loc_coords = {}
        for obs in observations:
            loc = obs.get("locName", "").strip()
            if not loc:
                continue
            loc_obs[loc].append(obs)
            if loc not in loc_coords:
                try:
                    lat = float(obs.get("lat", 0))
                    lng = float(obs.get("lng", 0))
                    if lat != 0.0 or lng != 0.0:
                        loc_coords[loc] = (lat, lng)
                except (ValueError, TypeError):
                    pass

        COLOR_LIFE    = "#c0392b"
        COLOR_COUNTRY = "#e07020"
        COLOR_STATE   = "#2e7d32"
        COLOR_COUNTY  = "#4488EE"
        COLOR_OTHER   = "#FFFFFF"

        points = []   # (lat, lng, loc_name, color, [species, …])
        for loc, obs_list in loc_obs.items():
            if loc not in loc_coords:
                continue
            lat, lng = loc_coords[loc]

            seen_sp = []
            for obs in obs_list:
                com = obs.get("comName", "").strip()
                if com and com not in seen_sp:
                    seen_sp.append(com)

            has_life = has_country = has_state = has_county = False
            for com in seen_sp:
                if " x " in com:
                    continue
                _lk = _base(com)
                if _lk not in life_set:
                    has_life = True
                    break
            if not has_life:
                for com in seen_sp:
                    if " x " in com:
                        continue
                    _lk = _base(com)
                    if check_country and _lk not in country_set:
                        has_country = True
                        break
            if not has_life and not has_country:
                for com in seen_sp:
                    if " x " in com:
                        continue
                    _lk = _base(com)
                    if check_state and _lk not in state_set:
                        has_state = True
                        break
            if not has_life and not has_country and not has_state:
                for com in seen_sp:
                    if " x " in com:
                        continue
                    _lk = _base(com)
                    if check_county and _lk not in county_set:
                        has_county = True
                        break

            if has_life:
                color = COLOR_LIFE
            elif has_country:
                color = COLOR_COUNTRY
            elif has_state:
                color = COLOR_STATE
            elif has_county:
                color = COLOR_COUNTY
            else:
                color = COLOR_OTHER

            points.append((lat, lng, loc, color, seen_sp))

        if not points:
            return False

        avg_lat = sum(p[0] for p in points) / len(points)
        avg_lng = sum(p[1] for p in points) / len(points)

        notable_map = folium.Map(
            location=[avg_lat, avg_lng],
            zoom_start=7,
            tiles="CartoDB Voyager",
        )

        import html as _html2
        tip_data = {}
        for lat, lng, loc, color, sp_list in points:
            sp_lines = ""
            for sp in sp_list[:25]:
                _lk = _base(sp)
                _esc = _html2.escape(sp)
                if " x " not in sp and _lk not in life_set:
                    sp_lines += (f'<br>&nbsp;&nbsp;<span style="color:{COLOR_LIFE}">'
                                 f'{_esc} (Life)</span>')
                elif " x " not in sp and check_country and _lk not in country_set:
                    sp_lines += (f'<br>&nbsp;&nbsp;<span style="color:{COLOR_COUNTRY}">'
                                 f'{_esc} (Country)</span>')
                elif " x " not in sp and check_state and _lk not in state_set:
                    sp_lines += (f'<br>&nbsp;&nbsp;<span style="color:{COLOR_STATE}">'
                                 f'{_esc} (State)</span>')
                elif " x " not in sp and check_county and _lk not in county_set:
                    sp_lines += (f'<br>&nbsp;&nbsp;<span style="color:{COLOR_COUNTY}">'
                                 f'{_esc} (County)</span>')
                else:
                    sp_lines += f"<br>&nbsp;&nbsp;{_esc}"
            if len(sp_list) > 25:
                sp_lines += f"<br>&nbsp;&nbsp;(+{len(sp_list) - 25} more)"
            tip_data[loc] = f"<b>{_html2.escape(loc)}</b>{sp_lines}"

        tip_data_json = _json.dumps(tip_data, ensure_ascii=False)

        for lat, lng, loc, color, sp_list in points:
            marker = folium.CircleMarker(
                location=[lat, lng],
                radius=12,
                color="#555555",
                weight=1,
                fill=True,
                fill_color=color,
                fill_opacity=0.88,
            )
            marker.options["locationName"] = loc
            marker.add_to(notable_map)

        lats = [p[0] for p in points]
        lngs = [p[1] for p in points]
        notable_map.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]], max_zoom=15)

        html = notable_map.get_root().render()

        inject_js = f"""
<script>
(function() {{
    var tipDiv = document.createElement('div');
    tipDiv.style.cssText = (
        'position:fixed; display:none; pointer-events:none; z-index:9999;' +
        'background:#252730; color:#e2e4ec; border:1px solid #FF8C00;' +
        'border-radius:6px; padding:6px 10px; font-size:12px;' +
        'max-width:300px; line-height:1.5;'
    );
    document.body.appendChild(tipDiv);
    var tipData = {tip_data_json};
    function findMap() {{
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {{
            try {{ var o = window[keys[i]]; if (o && o instanceof L.Map) return o; }}
            catch(e) {{}}
        }}
        return null;
    }}
    function init() {{
        var map = findMap();
        if (!map) {{ setTimeout(init, 150); return; }}
        map.eachLayer(function(layer) {{
            if (!(layer instanceof L.CircleMarker)) return;
            var name      = layer.options.locationName;
            var origColor = layer.options.color;
            var origWeight = layer.options.weight;
            if (!name) return;
            layer.on('mouseover', function(e) {{
                this.setStyle({{ color: '#ffffff', weight: 2 }});
                var html = tipData[name];
                if (!html) return;
                tipDiv.innerHTML = html;
                tipDiv.style.display = 'block';
                var mapCont = map.getContainer();
                var mapRect = mapCont.getBoundingClientRect();
                var pt = map.latLngToContainerPoint(e.target.getLatLng());
                var GAP = 12;
                var tipW = tipDiv.offsetWidth;
                var tipH = tipDiv.offsetHeight;
                var absX = pt.x > mapRect.width / 2
                    ? mapRect.left + pt.x - tipW - GAP
                    : mapRect.left + pt.x + GAP;
                var absY = mapRect.top + pt.y - tipH / 2;
                absY = Math.max(GAP, Math.min(absY, window.innerHeight - tipH - GAP));
                tipDiv.style.left = absX + 'px';
                tipDiv.style.top  = absY + 'px';
            }});
            layer.on('mouseout', function() {{
                this.setStyle({{ color: origColor, weight: origWeight }});
                tipDiv.style.display = 'none';
            }});
        }});
    }}
    init();
}})();
</script>"""
        html = html.replace("</body>", inject_js + self._satellite_toggle_js() + "\n</body>")

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))

        title = f"Notable Community Sightings Map: {region_label}"
        self.title = title
        self.setWindowTitle(title)
        self.resizeMe()
        self.scaleMe()
        return True


    def loadLocationPointMap(self, loc_name, lat, lng):
        """Show a single-dot folium map for a specific eBird location."""
        import folium
        import tempfile

        self.contentType = "Location Map"
        m = folium.Map(location=[lat, lng], zoom_start=14, tiles="CartoDB Voyager")
        folium.CircleMarker(
            location=[lat, lng],
            radius=15,
            color="#333333",
            weight=1,
            fill=True,
            fill_color=CHART_PRIMARY,
            fill_opacity=0.85,
            tooltip=loc_name,
        ).add_to(m)

        html = m.get_root().render()
        html = html.replace("</body>", self._satellite_toggle_js() + "</body>")
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", encoding="utf-8", delete=False
        )
        tmp.write(html)
        tmp.close()
        self._locationPointMapTmpFile = tmp.name
        self.webView.load(QUrl.fromLocalFile(tmp.name))
        self.setWindowTitle(f"Map: {loc_name}")
        self.resizeMe()
        return True


    def loadSpeciesSightings(self, region_id, region_label, species_code,
                             species_name, api_key, back_days):
        """Fetch all recent observations for one species in a region and display them."""
        import html as _html
        from datetime import datetime, timedelta
        from PySide6.QtGui import QColor, QCursor

        self.contentType = "Species Sightings"
        self._communityRegionId    = region_id
        self._communityRegionLabel = region_label

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        observations = self._ebirdGet(
            f"/v2/data/obs/{region_id}/recent/{species_code}"
            f"?detail=full&back={back_days}&includeProvisional=true",
            api_key,
        )
        QApplication.restoreOverrideCursor()

        def _fmt_dt(raw):
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    month = dt.strftime("%b")
                    if fmt == "%Y-%m-%d %H:%M":
                        hour = str(int(dt.strftime("%I")))
                        return f"{month} {dt.day}, {dt.year}  {hour}:{dt.strftime('%M')} {dt.strftime('%p')}"
                    return f"{month} {dt.day}, {dt.year}"
                except ValueError:
                    pass
            return raw

        if not observations:
            msg = (f"No recent {_html.escape(species_name)} sightings found "
                   f"in {_html.escape(region_label)} for the past {back_days} days.")
            obs_html = (
                f'<div style="padding:40px;text-align:center;'
                f'color:#8b8fa8;font-style:italic;">{msg}</div>'
            )
            sci_name = ""
        else:
            observations = sorted(observations, key=lambda o: o.get("obsDt", ""), reverse=True)
            sci_name = observations[0].get("sciName", "")
            obs_html = ""
            for obs in observations:
                loc       = _html.escape(obs.get("locName", ""))
                dt_str    = _fmt_dt(obs.get("obsDt", ""))
                how_many  = obs.get("howMany")
                count_str = str(how_many) if how_many else ""
                observer  = _html.escape(obs.get("userDisplayName", ""))
                sub_id    = _html.escape(obs.get("subId", ""))
                ebird_btn = (
                    f'<span class="ebird-link" onclick="openChecklist(\'{sub_id}\')">'
                    f'View &#8599;</span>'
                    if sub_id else ""
                )
                obs_html += (
                    f'<div class="sighting">'
                    f'<span class="loc">{loc}</span>'
                    f'<span class="dt">{dt_str}</span>'
                    f'<span class="count">{count_str}</span>'
                    f'{ebird_btn}'
                    f'</div>\n'
                )

        today      = datetime.now()
        start_date = today - timedelta(days=back_days - 1)
        date_range = (
            f"{start_date.strftime('%b')} {start_date.day} – "
            f"{today.strftime('%b')} {today.day}, {today.year}"
        )

        qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        qwc_js = bytes(qwc_file.readAll()).decode("utf-8")
        qwc_file.close()

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{
  background:#16171d; color:#e2e4ec;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:14px;
}}
.header {{ background:#1e1f26; padding:18px 28px 12px; border-bottom:1px solid #2a2b38; }}
.header h1 {{ font-size:1.45em; font-weight:700; margin-bottom:2px; }}
.header .sci {{ font-size:0.9em; color:#6b6f88; font-style:italic; margin-top:2px; }}
.header h2 {{ font-size:1.45em; font-weight:700; margin-top:6px; }}
.header .sub {{ color:#8b8fa8; font-size:0.82em; margin-top:4px; }}
.header .attr {{ color:#6b6f88; font-size:0.75em; margin-top:6px; }}
.header .attr a {{ color:{CHART_PRIMARY}; text-decoration:none; }}
.header .attr a:hover {{ text-decoration:underline; }}
.list {{ padding:16px 20px 40px; }}
.sighting {{
  display:flex; align-items:center; gap:10px;
  padding:8px 16px; border-bottom:1px solid #2a2b38;
  font-size:0.87em; background:#1e1f26;
  border-radius:4px; margin-bottom:4px;
}}
.sighting:last-child {{ margin-bottom:0; }}
.loc {{ flex:1; color:#e2e4ec; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.dt {{ color:#8b8fa8; min-width:160px; white-space:nowrap; }}
.count {{ color:#8b8fa8; min-width:28px; text-align:right; font-size:0.85em; }}
.observer {{ color:#6b6f88; min-width:130px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:0.85em; }}
.ebird-link {{
  color:{CHART_PRIMARY}; font-size:0.8em; cursor:pointer;
  padding:2px 8px; border-radius:4px; border:1px solid #3a4a60;
  white-space:nowrap; user-select:none;
}}
.ebird-link:hover {{ background:{CHART_PRIMARY}22; }}
</style>
<script>{qwc_js}</script>
</head>
<body>
<div class="header">
  <h1>{_html.escape(species_name)}</h1>
  <div class="sci">{_html.escape(sci_name)}</div>
  <h2>{_html.escape(region_label)}</h2>
  <div class="sub">{date_range} &nbsp;&middot;&nbsp; Past {back_days} days</div>
  <div class="attr">Sightings from <a href="https://ebird.org" target="_blank">eBird.org</a>. Some sightings may be provisional or exotic.</div>
</div>
<div class="list">{obs_html}</div>
<script>
document.addEventListener("DOMContentLoaded", function() {{
  new QWebChannel(qt.webChannelTransport, function(channel) {{
    window.bridge = channel.objects.bridge;
  }});
}});
function openChecklist(subId) {{
  if (window.bridge) window.bridge.openChecklist(subId);
}}
</script>
</body>
</html>"""

        self._speciesBridge = NotableSightingsBridge(self)
        channel = QWebChannel(self.webView.page())
        channel.registerObject("bridge", self._speciesBridge)
        self.webView.page().setWebChannel(channel)

        self.webView.page().setBackgroundColor(QColor("#16171d"))

        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", encoding="utf-8", delete=False
        )
        tmp.write(html)
        tmp.close()
        self._speciesTmpFile = tmp.name
        self.webView.load(QUrl.fromLocalFile(tmp.name))

        self.resizeMe()
        self.scaleMe()

        title = f"{species_name}: {region_label}"
        self.title = title
        self.setWindowTitle(title)
        return True


    def loadSpeciesMapFromObs(self, observations, species_name, region_label, back_days, tag="", region_id=""):
        """Build a location dot map from pre-fetched observations (no API call).

        Used by the Notable Sightings bridge, which already has lat/lng on every
        observation from the detail=full fetch.
        """
        import folium
        import html as _html
        import json as _json
        import tempfile
        from collections import defaultdict
        from datetime import datetime

        self.contentType = "Species Map"
        self._communityRegionId    = region_id
        self._communityRegionLabel = region_label

        if not observations:
            return False

        def _fmt_dt(raw):
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    month = dt.strftime("%b")
                    if fmt == "%Y-%m-%d %H:%M":
                        hour = str(int(dt.strftime("%I")))
                        return f"{month} {dt.day}, {dt.year}  {hour}:{dt.strftime('%M %p')}"
                    return f"{month} {dt.day}, {dt.year}"
                except ValueError:
                    pass
            return raw

        loc_obs    = defaultdict(list)
        loc_coords = {}
        for obs in observations:
            loc = obs.get("locName", "").strip()
            if not loc:
                continue
            loc_obs[loc].append(obs)
            if loc not in loc_coords:
                try:
                    lat = float(obs.get("lat") or 0)
                    lng = float(obs.get("lng") or 0)
                    if lat != 0.0 or lng != 0.0:
                        loc_coords[loc] = (lat, lng, obs.get("locId", ""))
                except (ValueError, TypeError):
                    pass

        points = []
        for loc, obs_list in loc_obs.items():
            if loc not in loc_coords:
                continue
            lat, lng, loc_id = loc_coords[loc]
            obs_list.sort(key=lambda o: o.get("obsDt", ""), reverse=True)
            seen_dt = set()
            dates   = []
            for obs in obs_list:
                dt_raw = obs.get("obsDt", "")
                if dt_raw and dt_raw not in seen_dt:
                    seen_dt.add(dt_raw)
                    dates.append(_fmt_dt(dt_raw))
            points.append((lat, lng, loc, loc_id, dates))

        if not points:
            return False

        avg_lat = sum(p[0] for p in points) / len(points)
        avg_lng = sum(p[1] for p in points) / len(points)

        sp_map = folium.Map(
            location=[avg_lat, avg_lng],
            zoom_start=7,
            tiles="CartoDB Voyager",
        )

        _BADGE_COLORS = {
            "life":    "#c0392b",
            "country": "#e07020",
            "state":   "#2e7d32",
            "county":  "#4488EE",
        }
        dot_color    = _BADGE_COLORS.get(tag, CHART_PRIMARY)
        badge_labels = {"life": "Life", "country": "Country", "state": "State", "county": "County"}
        badge_label  = badge_labels.get(tag, "")
        badge_html   = (f'<span style="color:{dot_color}; margin-left:6px;">({badge_label})</span>'
                        if badge_label else "")

        tip_data = {}
        for lat, lng, loc, loc_id, dates in points:
            dt_lines = "".join(f"<br>&nbsp;&nbsp;{d}" for d in dates[:15])
            if len(dates) > 15:
                dt_lines += f"<br>&nbsp;&nbsp;(+{len(dates) - 15} more)"
            tip_data[loc] = f"<b>{_html.escape(loc)}</b>{badge_html}{dt_lines}"

        tip_data_json = _json.dumps(tip_data, ensure_ascii=False)

        for lat, lng, loc, loc_id, dates in points:
            marker = folium.CircleMarker(
                location=[lat, lng],
                radius=12,
                color="#333333",
                weight=1,
                fill=True,
                fill_color=dot_color,
                fill_opacity=0.85,
            )
            marker.options["locationName"] = loc
            marker.options["locationId"]   = loc_id
            marker.add_to(sp_map)

        lats = [p[0] for p in points]
        lngs = [p[1] for p in points]
        sp_map.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]], max_zoom=15)

        html = sp_map.get_root().render()

        inject_js = f"""
<script>
(function() {{
    var tipDiv = document.createElement('div');
    tipDiv.style.cssText = (
        'position:fixed; display:none; pointer-events:none; z-index:9999;' +
        'background:#252730; color:#e2e4ec; border:1px solid {dot_color};' +
        'border-radius:6px; padding:6px 10px; font-size:12px;' +
        'max-width:320px; line-height:1.5;'
    );
    document.body.appendChild(tipDiv);
    var tipData = {tip_data_json};
    function findMap() {{
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {{
            try {{ var o = window[keys[i]]; if (o && o instanceof L.Map) return o; }}
            catch(e) {{}}
        }}
        return null;
    }}
    function init() {{
        var map = findMap();
        if (!map) {{ setTimeout(init, 150); return; }}
        map.eachLayer(function(layer) {{
            if (!(layer instanceof L.CircleMarker)) return;
            var name      = layer.options.locationName;
            var origColor = layer.options.color;
            var origWeight = layer.options.weight;
            if (!name) return;
            layer.on('mouseover', function(e) {{
                this.setStyle({{ color: '#ffffff', weight: 2 }});
                var html = tipData[name];
                if (!html) return;
                tipDiv.innerHTML = html;
                tipDiv.style.display = 'block';
                var mapCont = map.getContainer();
                var mapRect = mapCont.getBoundingClientRect();
                var pt = map.latLngToContainerPoint(e.target.getLatLng());
                var GAP = 12;
                var tipW = tipDiv.offsetWidth;
                var tipH = tipDiv.offsetHeight;
                var absX = pt.x > mapRect.width / 2
                    ? mapRect.left + pt.x - tipW - GAP
                    : mapRect.left + pt.x + GAP;
                var absY = mapRect.top + pt.y - tipH / 2;
                absY = Math.max(GAP, Math.min(absY, window.innerHeight - tipH - GAP));
                tipDiv.style.left = absX + 'px';
                tipDiv.style.top  = absY + 'px';
            }});
            layer.on('mouseout', function() {{
                this.setStyle({{ color: origColor, weight: origWeight }});
                tipDiv.style.display = 'none';
            }});
        }});
    }}
    init();
}})();
</script>"""
        click_js = """
<script>
(function() {
    new QWebChannel(qt.webChannelTransport, function(channel) {
        window.csBridge = channel.objects.csBridge;
    });
    function initClick() {
        var map = null;
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {
            try { var o = window[keys[i]]; if (o && o instanceof L.Map) { map = o; break; } }
            catch(e) {}
        }
        if (!map) { setTimeout(initClick, 150); return; }
        map.eachLayer(function(layer) {
            if (!(layer instanceof L.CircleMarker)) return;
            var locId   = layer.options.locationId;
            var locName = layer.options.locationName;
            if (!locId) return;
            layer.on('click', function() {
                if (window.csBridge) window.csBridge.locationClicked(locId, locName);
            });
        });
    }
    initClick();
})();
</script>"""
        _qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        _qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        _qwc_block = "\n<script>" + bytes(_qwc_file.readAll()).decode("utf-8") + "</script>"
        _qwc_file.close()
        html = html.replace("</body>", inject_js + _qwc_block + click_js + self._satellite_toggle_js() + "\n</body>")

        self._csSightingsMapBridge = CommunitySightingsMapBridge(self)
        cs_channel = QWebChannel(self.webView.page())
        cs_channel.registerObject("csBridge", self._csSightingsMapBridge)
        self.webView.page().setWebChannel(cs_channel)

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))

        title = f"Community Sightings ({back_days} days): {species_name}: {region_label}"
        self.title = title
        self.setWindowTitle(title)
        self.resizeMe()
        self.scaleMe()
        return True


    def loadHotspotMap(self, filter):
        """Fetch eBird hotspots for a county-level region and plot as a dot map
        sized by all-time species count.  Clicking a dot opens an All Community
        Sightings report for that location."""
        import math
        import csv as _csv
        import io
        import folium
        import json as _json
        import tempfile
        import urllib.request
        from PySide6.QtGui import QColor, QCursor

        self.contentType = "Hotspot Map"

        api_key = self.mdiParent.db.ebirdApiKey.strip()
        if not api_key:
            QMessageBox.warning(
                self.mdiParent, "eBird API Key Required",
                "No eBird API key is configured.\n\nPlease add your key under Preferences.",
                QMessageBox.StandardButton.Ok,
            )
            return False

        region_id, region_label = self._getEBirdRegionCode(filter)
        if not region_id:
            QMessageBox.warning(
                self.mdiParent, "County Required",
                "Hotspot Map requires a county or specific location to be "
                "selected in the filter.\n\nPlease select a county and try again.",
                QMessageBox.StandardButton.Ok,
            )
            return False

        # _getEBirdRegionCode falls back to state level for non-US counties because
        # countyCodeDict is US-only.  If the filter explicitly targets a county but we
        # only got a state code, look up the eBird subnational2 code via the API.
        if region_id.count("-") == 1 and filter.getLocationType() == "County":
            county_name = filter.getLocationName().split(" (")[0].strip()
            try:
                _url = f"https://api.ebird.org/v2/ref/region/list/subnational2/{region_id}"
                _req = urllib.request.Request(
                    _url, headers={"X-eBirdApiToken": api_key}
                )
                with urllib.request.urlopen(_req, timeout=20, context=_SSL_CTX) as _resp:
                    _counties = _json.loads(_resp.read().decode("utf-8"))
                for _c in _counties:
                    if _c.get("name", "").strip().lower() == county_name.lower():
                        region_id    = _c["code"]
                        region_label = _c["name"]
                        break
            except Exception:
                pass

        # Restrict to county-level (2 dashes) or location-derived codes
        if not region_id.startswith("L") and region_id.count("-") < 2:
            QMessageBox.warning(
                self.mdiParent, "County Required",
                "Hotspot Map is only available at the county level — "
                "a country or state would return too many hotspots to display "
                "usefully.\n\nPlease select a county in the filter and try again.",
                QMessageBox.StandardButton.Ok,
            )
            return False

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        url = f"https://api.ebird.org/v2/ref/hotspot/{region_id}"
        req = urllib.request.Request(url, headers={"X-eBirdApiToken": api_key})
        try:
            with urllib.request.urlopen(req, timeout=20, context=_SSL_CTX) as resp:
                raw_csv = resp.read().decode("utf-8")
        except Exception:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(
                self.mdiParent, "Network Error",
                f"Could not fetch hotspots for '{region_label}'.\n\n"
                "Check your internet connection and eBird API key.",
                QMessageBox.StandardButton.Ok,
            )
            return False
        QApplication.restoreOverrideCursor()

        # CSV: locId, countryCode, subnational1Code, subnational2Code,
        #      lat, lng, locName, lastObsDate, numSpecies, numChecklists
        points = []
        for row in _csv.reader(io.StringIO(raw_csv)):
            if len(row) < 10:
                continue
            try:
                loc_id   = row[0].strip()
                lat      = float(row[4])
                lng      = float(row[5])
                name     = row[6].strip()
                last_obs = row[7].strip()[:10]   # date only
                num_sp   = int(row[8])
                num_cl   = int(row[9])
            except (ValueError, IndexError):
                continue
            points.append((lat, lng, loc_id, name, last_obs, num_sp, num_cl))

        if not points:
            QMessageBox.information(
                self.mdiParent, "No Hotspots",
                f"No eBird hotspots found for '{region_label}'.",
                QMessageBox.StandardButton.Ok,
            )
            return False

        # Color shading: pale straw → orange → deep crimson, rank-normalised so the
        # full color range is always used regardless of the species-count distribution.
        C0 = (255, 253, 200)   # #fffdc8  pale straw yellow
        C1 = (255, 120,   0)   # #ff7800  orange
        C2 = (139,   0,  20)   # #8b0014  deep crimson

        unique_counts = sorted(set(p[5] for p in points))
        sp_rank = {sp: i for i, sp in enumerate(unique_counts)}
        max_rank = max(1, len(unique_counts) - 1)

        def species_color(sp):
            t = sp_rank.get(sp, 0) / max_rank   # 0 = lowest, 1 = highest
            if t <= 0.5:
                s = t * 2
                A, B = C0, C1
            else:
                s = (t - 0.5) * 2
                A, B = C1, C2
            r = int(A[0] + s * (B[0] - A[0]))
            g = int(A[1] + s * (B[1] - A[1]))
            b = int(A[2] + s * (B[2] - A[2]))
            return f"#{r:02x}{g:02x}{b:02x}"

        avg_lat = sum(p[0] for p in points) / len(points)
        avg_lng = sum(p[1] for p in points) / len(points)

        m = folium.Map(location=[avg_lat, avg_lng], zoom_start=10, tiles="CartoDB Voyager")

        # Tooltip data keyed by loc_id to avoid name collisions
        tip_data = {}
        for lat, lng, loc_id, name, last_obs, num_sp, num_cl in points:
            tip_data[loc_id] = (
                f"<b>{name}</b><br>"
                f"{num_sp:,} species &nbsp;&middot;&nbsp; {num_cl:,} checklists<br>"
                f"Last obs: {last_obs}"
            )
        tip_data_json = _json.dumps(tip_data, ensure_ascii=False)

        for lat, lng, loc_id, name, last_obs, num_sp, num_cl in points:
            fill = species_color(num_sp)
            marker = folium.CircleMarker(
                location=[lat, lng],
                radius=11,
                color="#ffffff",
                weight=1.5,
                fill=True,
                fill_color=fill,
                fill_opacity=0.85,
            )
            marker.options["locationName"] = name
            marker.options["locationId"]   = loc_id
            marker.add_to(m)

        lats = [p[0] for p in points]
        lngs = [p[1] for p in points]
        m.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]], max_zoom=15)

        html = m.get_root().render()

        inject_js = f"""
<script>
(function() {{
    var tipDiv = document.createElement('div');
    tipDiv.style.cssText = (
        'position:fixed; display:none; pointer-events:none; z-index:9999;' +
        'background:#252730; color:#e2e4ec; border:1px solid #8888bb;' +
        'border-radius:6px; padding:6px 10px; font-size:12px;' +
        'max-width:320px; line-height:1.5;'
    );
    document.body.appendChild(tipDiv);
    var tipData = {tip_data_json};
    function findMap() {{
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {{
            try {{ var o = window[keys[i]]; if (o && o instanceof L.Map) return o; }}
            catch(e) {{}}
        }}
        return null;
    }}
    function init() {{
        var map = findMap();
        if (!map) {{ setTimeout(init, 150); return; }}
        map.eachLayer(function(layer) {{
            if (!(layer instanceof L.CircleMarker)) return;
            var locId = layer.options.locationId;
            if (!locId) return;
            layer.on('mouseover', function(e) {{
                this.setStyle({{ color: '#ffcc00', weight: 2.5 }});
                var html = tipData[locId];
                if (!html) return;
                tipDiv.innerHTML = html;
                tipDiv.style.display = 'block';
                var mapCont = map.getContainer();
                var mapRect = mapCont.getBoundingClientRect();
                var pt = map.latLngToContainerPoint(e.target.getLatLng());
                var GAP = 12;
                var tipW = tipDiv.offsetWidth;
                var tipH = tipDiv.offsetHeight;
                var absX = pt.x > mapRect.width / 2
                    ? mapRect.left + pt.x - tipW - GAP
                    : mapRect.left + pt.x + GAP;
                var absY = mapRect.top + pt.y - tipH / 2;
                absY = Math.max(GAP, Math.min(absY, window.innerHeight - tipH - GAP));
                tipDiv.style.left = absX + 'px';
                tipDiv.style.top  = absY + 'px';
            }});
            layer.on('mouseout', function() {{
                this.setStyle({{ color: '#ffffff', weight: 1.5 }});
                tipDiv.style.display = 'none';
            }});
        }});
    }}
    init();
}})();
</script>"""

        click_js = """
<script>
(function() {
    new QWebChannel(qt.webChannelTransport, function(channel) {
        window.csBridge = channel.objects.csBridge;
    });
    function initClick() {
        var map = null;
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {
            try { var o = window[keys[i]]; if (o && o instanceof L.Map) { map = o; break; } }
            catch(e) {}
        }
        if (!map) { setTimeout(initClick, 150); return; }
        map.eachLayer(function(layer) {
            if (!(layer instanceof L.CircleMarker)) return;
            var locId   = layer.options.locationId;
            var locName = layer.options.locationName;
            if (!locId) return;
            layer.on('click', function() {
                if (window.csBridge) window.csBridge.locationClicked(locId, locName);
            });
        });
    }
    initClick();
})();
</script>"""

        _qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        _qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        _qwc_block = "\n<script>" + bytes(_qwc_file.readAll()).decode("utf-8") + "</script>"
        _qwc_file.close()
        html = html.replace("</body>", inject_js + _qwc_block + click_js + self._satellite_toggle_js() + "\n</body>")

        self._communityRegionId    = region_id
        self._communityRegionLabel = region_label
        self._csSightingsMapBridge = CommunitySightingsMapBridge(self)
        cs_channel = QWebChannel(self.webView.page())
        cs_channel.registerObject("csBridge", self._csSightingsMapBridge)
        self.webView.page().setWebChannel(cs_channel)

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        title = f"Hotspot Map: {region_label}"
        self.title = title
        self.setWindowTitle(title)
        self.resizeMe()
        self.scaleMe()
        return True


    def loadSpeciesMap(self, region_id, region_label, species_code,
                       species_name, api_key, back_days, tag=""):
        """Fetch recent observations for one species and show a location dot map.

        Dots are deduped by location name.  Tooltip shows the location name as a
        heading with each checklist date/time listed below it.
        """
        import folium
        import html as _html
        import json as _json
        import tempfile
        from collections import defaultdict
        from datetime import datetime

        self.contentType = "Species Map"
        self._communityRegionId    = region_id
        self._communityRegionLabel = region_label

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        observations = self._ebirdGet(
            f"/v2/data/obs/{region_id}/recent/{species_code}"
            f"?detail=full&back={back_days}&includeProvisional=true",
            api_key,
        )
        QApplication.restoreOverrideCursor()

        if not observations:
            return False

        def _fmt_dt(raw):
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    month = dt.strftime("%b")
                    if fmt == "%Y-%m-%d %H:%M":
                        hour = str(int(dt.strftime("%I")))
                        return f"{month} {dt.day}, {dt.year}  {hour}:{dt.strftime('%M %p')}"
                    return f"{month} {dt.day}, {dt.year}"
                except ValueError:
                    pass
            return raw

        # Group by location name; collect coords and observation datetimes
        loc_obs    = defaultdict(list)
        loc_coords = {}
        for obs in observations:
            loc = obs.get("locName", "").strip()
            if not loc:
                continue
            loc_obs[loc].append(obs)
            if loc not in loc_coords:
                try:
                    lat = float(obs.get("lat", 0))
                    lng = float(obs.get("lng", 0))
                    if lat != 0.0 or lng != 0.0:
                        loc_coords[loc] = (lat, lng, obs.get("locId", ""))
                except (ValueError, TypeError):
                    pass

        points = []   # (lat, lng, loc_name, [formatted_date, …])
        for loc, obs_list in loc_obs.items():
            if loc not in loc_coords:
                continue
            lat, lng, loc_id = loc_coords[loc]
            obs_list.sort(key=lambda o: o.get("obsDt", ""), reverse=True)
            seen_dt = set()
            dates   = []
            for obs in obs_list:
                dt_raw = obs.get("obsDt", "")
                if dt_raw and dt_raw not in seen_dt:
                    seen_dt.add(dt_raw)
                    dates.append(_fmt_dt(dt_raw))
            points.append((lat, lng, loc, loc_id, dates))

        if not points:
            return False

        avg_lat = sum(p[0] for p in points) / len(points)
        avg_lng = sum(p[1] for p in points) / len(points)

        sp_map = folium.Map(
            location=[avg_lat, avg_lng],
            zoom_start=7,
            tiles="CartoDB Voyager",
        )

        _BADGE_COLORS = {
            "life":    "#c0392b",
            "country": "#e07020",
            "state":   "#2e7d32",
            "county":  "#4488EE",
        }
        dot_color    = _BADGE_COLORS.get(tag, CHART_PRIMARY)
        badge_labels = {"life": "Life", "country": "Country", "state": "State", "county": "County"}
        badge_label  = badge_labels.get(tag, "")
        badge_html   = (f'<span style="color:{dot_color}; margin-left:6px;">({badge_label})</span>'
                        if badge_label else "")

        tip_data = {}
        for lat, lng, loc, loc_id, dates in points:
            dt_lines = "".join(f"<br>&nbsp;&nbsp;{d}" for d in dates[:15])
            if len(dates) > 15:
                dt_lines += f"<br>&nbsp;&nbsp;(+{len(dates) - 15} more)"
            tip_data[loc] = f"<b>{_html.escape(loc)}</b>{badge_html}{dt_lines}"

        tip_data_json = _json.dumps(tip_data, ensure_ascii=False)

        for lat, lng, loc, loc_id, dates in points:
            marker = folium.CircleMarker(
                location=[lat, lng],
                radius=12,
                color="#333333",
                weight=1,
                fill=True,
                fill_color=dot_color,
                fill_opacity=0.85,
            )
            marker.options["locationName"] = loc
            marker.options["locationId"]   = loc_id
            marker.add_to(sp_map)

        lats = [p[0] for p in points]
        lngs = [p[1] for p in points]
        sp_map.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]], max_zoom=15)

        html = sp_map.get_root().render()

        inject_js = f"""
<script>
(function() {{
    var tipDiv = document.createElement('div');
    tipDiv.style.cssText = (
        'position:fixed; display:none; pointer-events:none; z-index:9999;' +
        'background:#252730; color:#e2e4ec; border:1px solid {dot_color};' +
        'border-radius:6px; padding:6px 10px; font-size:12px;' +
        'max-width:320px; line-height:1.5;'
    );
    document.body.appendChild(tipDiv);
    var tipData = {tip_data_json};
    function findMap() {{
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {{
            try {{ var o = window[keys[i]]; if (o && o instanceof L.Map) return o; }}
            catch(e) {{}}
        }}
        return null;
    }}
    function init() {{
        var map = findMap();
        if (!map) {{ setTimeout(init, 150); return; }}
        map.eachLayer(function(layer) {{
            if (!(layer instanceof L.CircleMarker)) return;
            var name      = layer.options.locationName;
            var origColor = layer.options.color;
            var origWeight = layer.options.weight;
            if (!name) return;
            layer.on('mouseover', function(e) {{
                this.setStyle({{ color: '#ffffff', weight: 2 }});
                var html = tipData[name];
                if (!html) return;
                tipDiv.innerHTML = html;
                tipDiv.style.display = 'block';
                var mapCont = map.getContainer();
                var mapRect = mapCont.getBoundingClientRect();
                var pt = map.latLngToContainerPoint(e.target.getLatLng());
                var GAP = 12;
                var tipW = tipDiv.offsetWidth;
                var tipH = tipDiv.offsetHeight;
                var absX = pt.x > mapRect.width / 2
                    ? mapRect.left + pt.x - tipW - GAP
                    : mapRect.left + pt.x + GAP;
                var absY = mapRect.top + pt.y - tipH / 2;
                absY = Math.max(GAP, Math.min(absY, window.innerHeight - tipH - GAP));
                tipDiv.style.left = absX + 'px';
                tipDiv.style.top  = absY + 'px';
            }});
            layer.on('mouseout', function() {{
                this.setStyle({{ color: origColor, weight: origWeight }});
                tipDiv.style.display = 'none';
            }});
        }});
    }}
    init();
}})();
</script>"""
        click_js = """
<script>
(function() {
    new QWebChannel(qt.webChannelTransport, function(channel) {
        window.csBridge = channel.objects.csBridge;
    });
    function initClick() {
        var map = null;
        var keys = Object.keys(window);
        for (var i = 0; i < keys.length; i++) {
            try { var o = window[keys[i]]; if (o && o instanceof L.Map) { map = o; break; } }
            catch(e) {}
        }
        if (!map) { setTimeout(initClick, 150); return; }
        map.eachLayer(function(layer) {
            if (!(layer instanceof L.CircleMarker)) return;
            var locId   = layer.options.locationId;
            var locName = layer.options.locationName;
            if (!locId) return;
            layer.on('click', function() {
                if (window.csBridge) window.csBridge.locationClicked(locId, locName);
            });
        });
    }
    initClick();
})();
</script>"""
        _qwc_file = QFile(":/qtwebchannel/qwebchannel.js")
        _qwc_file.open(QIODevice.OpenModeFlag.ReadOnly)
        _qwc_block = "\n<script>" + bytes(_qwc_file.readAll()).decode("utf-8") + "</script>"
        _qwc_file.close()
        html = html.replace("</body>", inject_js + _qwc_block + click_js + self._satellite_toggle_js() + "\n</body>")

        self._csSightingsMapBridge = CommunitySightingsMapBridge(self)
        cs_channel = QWebChannel(self.webView.page())
        cs_channel.registerObject("csBridge", self._csSightingsMapBridge)
        self.webView.page().setWebChannel(cs_channel)

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))

        title = f"Community Sightings ({back_days} days): {species_name}: {region_label}"
        self.title = title
        self.setWindowTitle(title)
        self.resizeMe()
        self.scaleMe()
        return True

