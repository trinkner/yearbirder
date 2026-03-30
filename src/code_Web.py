from PySide6.QtCore import QLibraryInfo
import os
import sys

# import the GUI forms that we create with Qt Creator
import form_Web

# import the Qt components we'll use
# do this so later we won't have to clutter our code with references to parent Qt classes 

from PySide6.QtGui import (
    QCursor,
    QIcon,
    QPixmap
    )
    
from PySide6.QtCore import (
    Qt,
    QUrl,
    QFile,
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
    QMdiSubWindow
    )

from math import (
    floor
    )

from PySide6.QtWebEngineWidgets import (
    QWebEngineView,
    )
from PySide6.QtWebEngineCore import (
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
        
            
    def resizeMe(self):

        windowWidth =  self.frameGeometry().width()
        windowHeight = self.frameGeometry().height()
        self.scrollArea.setGeometry(5, 27, windowWidth -10 , windowHeight-35)
        self.webView.setGeometry(5, 27, windowWidth - 10, windowHeight-35)
        if self.contentType == "Map":
            self.webView.adjustSize()
            self.LoadLocationsMap(self.filter)
   
   
    def html(self):
    
#         QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        html = """
            <!DOCTYPE html>
            <html>
            <head>
            </head>
            <body>
            """
        
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
        
       
    def scaleMe(self):
       
        fontSize = self.mdiParent.fontSize
        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setFontSize(QWebEngineSettings.FontSize.DefaultFontSize, floor(fontSize * 1.6))        
        
        scaleFactor = self.mdiParent.scaleFactor
        windowWidth =  int(800 * scaleFactor)
        windowHeight = int(580 * scaleFactor)       
        self.resize(windowWidth, windowHeight)


    def loadAboutYearbird(self):
        
        self.title= "About Yearbird"
        
        self.contentType = "About"
                    
        html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>About Yearbird</title>
<style>
  body {
    background-color: #1e1f26;
    color: #e2e4ec;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 14px;
    margin: 32px 40px;
    line-height: 1.6;
  }
  h1 {
    color: #4f8ef7;
    font-size: 2em;
    margin-bottom: 2px;
  }
  .subtitle {
    color: #8b8fa8;
    font-size: 0.95em;
    margin-top: 0;
    margin-bottom: 24px;
  }
  .description {
    font-size: 1em;
    margin-bottom: 28px;
  }
  h2 {
    color: #4f8ef7;
    font-size: 1.1em;
    border-bottom: 1px solid #3a3d4e;
    padding-bottom: 6px;
    margin-top: 28px;
  }
  ul {
    padding-left: 20px;
    margin: 10px 0;
  }
  li {
    margin-bottom: 8px;
    color: #c8cad8;
  }
  li b {
    color: #e2e4ec;
  }
</style>
</head>
<body>
<h1>Yearbird</h1>
"""
        html += f'<p class="subtitle">Version {self.mdiParent.versionNumber} &nbsp;&bull;&nbsp; {self.mdiParent.versionDate}</p>'
        html += """
<p class="description">
  Yearbird is a free, open-source application for analyzing personal eBird sightings.<br>
  Created by Richard Trinkner.
</p>

<h2>Licenses</h2>
<ul>
  <li><b>Yearbird</b> is licensed under the GNU General Public License, version 3.</li>
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
  <li><b>PyInstaller</b>, by the PyInstaller Development Team, is licensed under the
      GPL with a special exception that permits bundling of non-GPL applications.</li>
</ul>
</body>
</html>"""

        self.webView.setHtml(html)
                
        self.setWindowTitle("About Yearbird")

        return(True)


    def loadUserGuide(self):

        self.title = "User Guide"
        self.contentType = "User Guide"
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        guide_path = os.path.join(base_path, "guide", "guide_Yearbird.html")
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
        max_count = max(species_counts.values()) if species_counts else 1

        location_map = folium.Map(tiles="CartoDB Positron")

        # Build tooltip HTML for each location; stored in a JS dict for
        # the custom positioned tooltip (not folium.Tooltip, which can't be
        # told which side of the map to appear on).
        tip_data = {}
        points = []
        for name, coords in coordinatesDict.items():
            lat, lon = float(coords[0]), float(coords[1])
            points.append([lat, lon])
            n_species = species_counts.get(name, 0)
            radius = 4 + (n_species / max_count) * 14
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
                fill_color="#4f8ef7",
                fill_opacity=0.85,
            )
            # Store the exact location name on the layer for click handling
            marker.options["locationName"] = name
            marker.add_to(location_map)

        tip_data_json = json.dumps(tip_data, ensure_ascii=False)

        if len(points) == 1:
            location_map.location = points[0]
            location_map.zoom_start = 13
        else:
            lats = [p[0] for p in points]
            lons  = [p[1] for p in points]
            location_map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

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
        'background:#252730; color:#e2e4ec; border:1px solid #4f8ef7;' +
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
        html = html.replace("</body>", inject_js + "</body>")

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
        """Return a hex color interpolated from cream to orange based on value/max_value."""
        if value == 0 or max_value == 0:
            return '#f0f0f0'
        t = min(value / (max_value * 0.75), 1.0)
        r = 255
        g = int(240 + t * (119 - 240))
        b = int(227 + t * (0 - 227))
        return f'#{r:02x}{g:02x}{b:02x}'


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
        'background:#252730; color:#e2e4ec; border:1px solid #4f8ef7;' +
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

        stateDict = defaultdict()
        for s in minimalSightingList:
            if s["country"] == "US":
                if self.mdiParent.db.TestSighting(s, filter):
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

        state_map = folium.Map(location=[39.5, -98.3], zoom_start=4, tiles="CartoDB Positron")

        folium.GeoJson(
            geo_file,
            style_function=lambda feature: {
                'fillColor': self._lerp_orange(stateTotals[feature['id']], largestTotal),
                'color': 'black',
                'weight': .2,
                'fillOpacity': .8,
                },
            highlight_function=lambda feature: {
                'color': '#4f8ef7', 'weight': 2, 'fillOpacity': .95,
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

        for s in minimalSightingList:
            if s["country"] == "CA":
                if self.mdiParent.db.TestSighting(s, filter):
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

        prov_map = folium.Map(location=[62, -96], zoom_start=3, tiles="CartoDB Positron")

        folium.GeoJson(
            geo_file,
            style_function=lambda feature: {
                'fillColor': self._lerp_orange(provTotals[feature['id']], largestTotal),
                'color': 'black',
                'weight': .2,
                'fillOpacity': .8,
                },
            highlight_function=lambda feature: {
                'color': '#4f8ef7', 'weight': 2, 'fillOpacity': .95,
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

        for s in minimalSightingList:
            if s["country"] == "IN":
                if self.mdiParent.db.TestSighting(s, filter):
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

        state_map = folium.Map(location=[22, 80], zoom_start=4, tiles="CartoDB Positron")

        folium.GeoJson(
            geo_file,
            style_function=lambda feature: {
                'fillColor': self._lerp_orange(stateTotals[feature['id']], largestTotal),
                'color': 'black',
                'weight': .2,
                'fillOpacity': .8,
                },
            highlight_function=lambda feature: {
                'color': '#4f8ef7', 'weight': 2, 'fillOpacity': .95,
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

        for s in minimalSightingList:
            if s["country"] == "GB":
                if self.mdiParent.db.TestSighting(s, filter):
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

        county_map = folium.Map(location=[54, -2], zoom_start=5, tiles="CartoDB Positron")

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
                'color': '#4f8ef7', 'weight': 2, 'fillOpacity': .95,
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

        for s in minimalSightingList:
            if s["country"] == "US" and s["state"] not in ["US-HI", "US-AK"]:
                if "countyCode" in s.keys():
                    if self.mdiParent.db.TestSighting(s, filter):
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

        county_map = folium.Map(location=[39.5, -98.3], zoom_start=4, tiles="CartoDB Positron")

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
                'color': '#4f8ef7', 'weight': 2, 'fillOpacity': .95,
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

        for s in minimalSightingList:
            if self.mdiParent.db.TestSighting(s, filter):
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

        choro_map = folium.Map(location=[1, 1], zoom_start=1, tiles="CartoDB Positron")

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
                'color': '#4f8ef7', 'weight': 2, 'fillOpacity': .95,
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

        self.title = "Life List Map"
        self.filter = deepcopy(filter)

        # ── Collect lifers: first qualifying sighting of each species ──────
        minimal = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)
        minimal_sorted = sorted(minimal, key=lambda s: (s.get("date", ""), s.get("time", "")))

        seen   = set()
        lifers = []
        for s in minimal_sorted:
            if not self.mdiParent.db.TestSighting(s, filter):
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
            lifers.append({
                "species":  name,
                "date":     s.get("date", ""),
                "location": s.get("location", ""),
                "lat":      lat,
                "lon":      lon,
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
            tiles="CartoDB Positron",
        )
        life_map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

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
        &#x1F422;<input id="llm-speed" type="range" min="0" max="10" value="1">&#x1F407;
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
    var DELAYS  = [1350, 900, 600, 380, 240, 150, 95, 60, 35, 20, 10];

    function delayMs() {{
        return DELAYS[parseInt(document.getElementById('llm-speed').value)] || 150;
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
            mkrs[n - 1].setStyle({{ fillColor:'#4f8ef7', fillOpacity:0.95, opacity:1 }});
        }}
        shown = Math.min(n, lifers.length);
        updateUI();
    }}

    function resetMarkers() {{
        mkrs.forEach(function(m) {{ m.setStyle({{ fillOpacity:0, opacity:0 }}); }});
        shown = 0;
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
        var map = findMap();
        if (!map) {{ setTimeout(init, 150); return; }}

        lifers.forEach(function(lifer) {{
            var m = L.circleMarker([lifer.lat, lifer.lon], {{
                radius:7, fillColor:lifer.color, color:'#555',
                weight:0.8, fillOpacity:0, opacity:0
            }});
            m.bindTooltip(lifer.species + ' (#' + lifer.num + ')<br>' + lifer.date + '<br>' + lifer.location, {{sticky: false}});
            m.bindPopup(
                '<div style="font-family:sans-serif">' +
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
        html = html.replace("</body>", animation + "\n</body>")

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        self._buildFilterTitle(filter, "Life List Map", count=total, countUnit="Lifers")

        return True


    def loadGeolocatedPhotosMap(self, filter):

        from copy import deepcopy
        import folium
        from folium.plugins import MarkerCluster
        import tempfile
        from pathlib import Path

        self.title = "Geolocated Photos"
        self.filter = deepcopy(filter)

        photoSightings = self.mdiParent.db.GetSightingsWithPhotos(filter)

        # Collect one marker entry per photo that has valid coordinates
        markers = []
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

                species   = s.get("commonName", "Unknown")
                date      = s.get("date", "")
                location  = s.get("location", "")
                img_uri   = Path(file_path).as_uri()

                popup_html = (
                    f'<div style="font-family:sans-serif;width:270px">'
                    f'<b>{species}</b><br>'
                    f'{date}&nbsp;&nbsp;{location}<br>'
                    f'<img src="{img_uri}" '
                    f'style="max-width:260px;max-height:220px;margin-top:5px;'
                    f'border-radius:4px;">'
                    f'</div>'
                )
                markers.append((lat, lon, popup_html, species))

        if not markers:
            return False

        # --- Sunflower-spiral jitter for co-located markers ---
        # Photos sharing the exact same GPS point get a tiny offset arranged in
        # a Fibonacci spiral so they separate naturally on zoom-in.
        # Radius (degrees) = BASE * sqrt(n): ~2 m for n=2, ~45 m for n=700.
        import math
        from collections import defaultdict

        coord_groups = defaultdict(list)
        for i, m in enumerate(markers):
            coord_groups[(m[0], m[1])].append(i)

        GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))  # ~137.508°
        BASE_RADIUS  = 0.000015                            # degrees per √-marker

        for (lat, lon), indices in coord_groups.items():
            n = len(indices)
            if n <= 1:
                continue
            cos_lat = math.cos(math.radians(lat)) or 0.001
            radius  = BASE_RADIUS * math.sqrt(n)
            for k, idx in enumerate(indices):
                r     = radius * math.sqrt((k + 0.5) / n)
                theta = k * GOLDEN_ANGLE
                dlat  = r * math.cos(theta)
                dlon  = r * math.sin(theta) / cos_lat
                old   = markers[idx]
                markers[idx] = (lat + dlat, lon + dlon, old[2], old[3])

        # Centre the map on the mean of all photo locations
        avg_lat = sum(m[0] for m in markers) / len(markers)
        avg_lon = sum(m[1] for m in markers) / len(markers)

        photo_map = folium.Map(
            location=[avg_lat, avg_lon],
            zoom_start=5,
            tiles="CartoDB Positron",
        )

        cluster = MarkerCluster(
            options={
                "spiderfyOnMaxZoom": True,
                "spiderfyDistanceMultiplier": 2,
                "disableClusteringAtZoom": 18,
            }
        ).add_to(photo_map)

        for lat, lon, popup_html, species in markers:
            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(popup_html, max_width=280),
                tooltip=species,
            ).add_to(cluster)

        # Fit map to the bounds of all markers
        lats = [m[0] for m in markers]
        lons = [m[1] for m in markers]
        photo_map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

        html = photo_map.get_root().render()

        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        self._buildFilterTitle(filter, "Geolocated Photos", count=len(markers), countUnit="Photos")

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
        MIN_R, MAX_R = 4, 30
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
            tiles="CartoDB Positron",
        )

        for lat, lon, location, total_mins, count, untimed in points:
            r = radius_for(total_mins, count)
            untimed_line = (
                f"<br>Includes {untimed} untimed checklist{'s' if untimed != 1 else ''}"
                if 0 < untimed < count else ""
            )
            if mode == 'time':
                tooltip_text = (
                    f"{location}<br>"
                    f"{fmt_duration(total_mins)} &nbsp;·&nbsp; "
                    f"{count} checklist{'s' if count != 1 else ''}"
                    f"{untimed_line}"
                )
            else:
                tooltip_text = (
                    f"{location}<br>"
                    f"{count} checklist{'s' if count != 1 else ''} &nbsp;·&nbsp; "
                    f"{fmt_duration(total_mins)}"
                    f"{untimed_line}"
                )
            popup_html = (
                f'<div style="font-family:sans-serif;min-width:160px">'
                f'<b>{location}</b><br>'
                f'Total time: {fmt_duration(total_mins)}<br>'
                f'Checklists: {count}'
                f'</div>'
            )
            marker = folium.CircleMarker(
                location=[lat, lon],
                radius=r,
                color="#2a5fad",
                weight=1,
                fill=True,
                fill_color="#4f8ef7",
                fill_opacity=0.65,
                tooltip=folium.Tooltip(tooltip_text),
                popup=folium.Popup(popup_html, max_width=260),
            )
            marker.options["locationName"] = location
            marker.add_to(effort_map)

        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        effort_map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

        html = effort_map.get_root().render()
        html = self._inject_circle_marker_bridge(html)

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
        return html.replace("</body>", inject_js + "\n</body>")


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

        # ── Radius scaling (sqrt so area ∝ metric) ──────────────────────────
        MAX_METRIC = max(p[3] for p in points) or 1
        MIN_R, MAX_R = 4, 30

        def radius_for(metric):
            return MIN_R + (MAX_R - MIN_R) * math.sqrt(metric / MAX_METRIC)

        avg_lat = sum(p[0] for p in points) / len(points)
        avg_lon = sum(p[1] for p in points) / len(points)

        bubble_map = folium.Map(
            location=[avg_lat, avg_lon],
            zoom_start=5,
            tiles="CartoDB Positron",
        )

        for lat, lon, location, metric in points:
            unknown_cl_count = len(loc_unknown_cl.get(location, set()))
            unknown_cl_line = (
                f"<br>{unknown_cl_count} checklist{'s' if unknown_cl_count != 1 else ''}"
                f" do not include specific count for some species;"
                f" these entries add 1 to the total."
                if mode == 'individuals' and unknown_cl_count > 0 else ""
            )
            tooltip_text = f"{location}<br>{metric:,} {metric_label}{unknown_cl_line}"
            popup_html = (
                f'<div style="font-family:sans-serif;min-width:160px">'
                f'<b>{location}</b><br>'
                f'{metric_label.capitalize()}: {metric:,}'
                f'</div>'
            )
            marker = folium.CircleMarker(
                location=[lat, lon],
                radius=radius_for(metric),
                color="#2a5fad",
                weight=1,
                fill=True,
                fill_color="#4f8ef7",
                fill_opacity=0.65,
                tooltip=folium.Tooltip(tooltip_text),
                popup=folium.Popup(popup_html, max_width=260),
            )
            marker.options["locationName"] = location
            marker.add_to(bubble_map)

        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        bubble_map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

        html = bubble_map.get_root().render()
        html = self._inject_circle_marker_bridge(html)

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

