from PySide6.QtCore import QLibraryInfo
import os
import sys

# import the GUI forms that we create with Qt Creator
import form_Web
import code_MapHtml

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
    Signal,
    QIODevice,
    QByteArray,
    QBuffer
    )    
    
from PySide6.QtWidgets import (
#     QApplication,
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
  <li><b>Map base layers</b> are retrieved from OpenStreetMap contributors.</li>
  <li><b>Choropleth maps</b> are generated using Folium, which is released under the
      MIT License.</li>
  <li><b>OpenLayers</b>, used for point and label map layers, is released under the
      2-Clause BSD License.</li>
  <li><b>PyInstaller</b>, by the PyInstaller Development Team, is licensed under the
      GPL General Public License.</li>
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
        
        self.title= "Location Map"
        
        coordinatesDict = defaultdict()
        mapWidth =  self.frameGeometry().width() -10
        mapHeight = self.frameGeometry().height() -35
        self.scrollArea.setGeometry(5, 27, mapWidth + 2, mapHeight + 2)
        self.webView.setGeometry(5, 27, mapWidth + 2, mapHeight + 2)        
        self.contentType = "Map"
        self.filter = filter
        
        locations = self.mdiParent.db.GetLocations(filter)
        
        if len(locations) == 0:
            return(False)
        
        for l in locations:
            coordinates = self.mdiParent.db.GetLocationCoordinates(l)
            coordinatesDict[l] = coordinates

        thisMap = code_MapHtml.MapHtml()
        thisMap.mapHeight = mapHeight
        thisMap.mapWidth = mapWidth
        thisMap.coordinatesDict = coordinatesDict
        
        html = thisMap.html()
        
        self.webView.setHtml(html)

        self._buildFilterTitle(filter, "Map", count=len(coordinatesDict.keys()))

        icon = QIcon()
        icon.addPixmap(QPixmap(":/icon_map_white.png"), QIcon.Normal, QIcon.Off)
        self.setWindowIcon(icon) 
                
        return(True)


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


    def loadChoroplethUSStates(self, filter):

        from copy import deepcopy
        import folium

        self.title= "US States Choropleth"
        
        self.filter = deepcopy(filter)
        
        # find states in filtered sightings
        stateDict = defaultdict()
        
        minimalSightingList = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)
        
        for s in minimalSightingList:

            # Only count US sightings since we're only showing the US choropleth
            if s["country"] == "US":

                # Consider only full species, not slash or spuh or hybrid entries
                commonName = s["commonName"]
                if "/" not in commonName and "sp." not in commonName and " x " not in commonName:

                    if self.mdiParent.db.TestSighting(s, filter):

                        if s["state"][3:5] not in stateDict.keys():
                            stateDict[s["state"][3:5]] = [s]
                        else:
                            stateDict[s["state"][3:5]].append(s)
                                 
        # check if no sightings were found. Return false if none found. Abort and display message.
        if len(stateDict) == 0:
            return(False)

        stateTotals = defaultdict()
        largestTotal = 0
        for state in stateDict.keys():
            stateSpecies = set()
            for s in stateDict[state]:
                stateSpecies.add(s["commonName"])
            stateTotals[state] = len(stateSpecies)
            if len(stateSpecies) > largestTotal:
                largestTotal = len(stateSpecies)

        # Load the shape of the zone (US counties)
        geo_file = self.mdiParent.db.state_geo
                
        #add the state values to the geojson so we can access them for tooltips
        for f in geo_file["features"]:
            if f["id"] in stateTotals.keys(): 
                f["properties"]["speciesTotal"] = stateTotals[f["id"]]
            else:
                f["properties"]["speciesTotal"] = 0
                stateTotals[f["id"]] = 0
                    
        # Initialize the folium map
        state_map = folium.Map(location=[39.5, -98.3], zoom_start=4, tiles="CartoDB Positron")

        # Configure the chloropleth layer and add to map
        folium.GeoJson(
            geo_file,
            style_function=lambda feature: {
                'fillColor': self._lerp_orange(stateTotals[feature['id']], largestTotal),
                'color': 'black',
                'weight': .2,
                'fillOpacity': .8,
                },
            tooltip=folium.features.GeoJsonTooltip(
                fields=['name', 'speciesTotal'],
                aliases=["State", "Species"]
                )
            ).add_to(state_map)
        
        # make the layer control box visible
        folium.LayerControl().add_to(state_map)
                 
        # get the html string from the map
        import tempfile
        html = state_map.get_root().render()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name
        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        self._buildFilterTitle(filter, "US States Choropleth", count=len(stateDict), countUnit="States")

        return(True)


    def loadChoroplethCanadaProvinces(self, filter):

        from copy import deepcopy
        import folium

        self.title = "Canada Provinces Choropleth"

        self.filter = deepcopy(filter)

        # find provinces in filtered sightings
        provDict = defaultdict()

        minimalSightingList = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)

        for s in minimalSightingList:

            # Only count Canadian sightings since we're only showing the Canada choropleth
            if s["country"] == "CA":

                # Consider only full species, not slash or spuh or hybrid entries
                commonName = s["commonName"]
                if "/" not in commonName and "sp." not in commonName and " x " not in commonName:

                    if self.mdiParent.db.TestSighting(s, filter):

                        provCode = s["state"][3:5]  # e.g. "ON" from "CA-ON"
                        if provCode not in provDict.keys():
                            provDict[provCode] = [s]
                        else:
                            provDict[provCode].append(s)

        # check if no sightings were found. Return false if none found. Abort and display message.
        if len(provDict) == 0:
            return(False)

        provTotals = defaultdict()
        largestTotal = 0
        for prov in provDict.keys():
            provSpecies = set()
            for s in provDict[prov]:
                provSpecies.add(s["commonName"])
            provTotals[prov] = len(provSpecies)
            if len(provSpecies) > largestTotal:
                largestTotal = len(provSpecies)

        # Load the Canada provinces GeoJSON
        geo_file = self.mdiParent.db.ca_province_geo

        # add species totals to geojson features for tooltips
        for f in geo_file["features"]:
            if f["id"] in provTotals.keys():
                f["properties"]["speciesTotal"] = provTotals[f["id"]]
            else:
                f["properties"]["speciesTotal"] = 0
                provTotals[f["id"]] = 0

        # Initialize the folium map centered on Canada
        prov_map = folium.Map(location=[62, -96], zoom_start=3, tiles="CartoDB Positron")

        # Configure the choropleth layer and add to map
        folium.GeoJson(
            geo_file,
            style_function=lambda feature: {
                'fillColor': self._lerp_orange(provTotals[feature['id']], largestTotal),
                'color': 'black',
                'weight': .2,
                'fillOpacity': .8,
                },
            tooltip=folium.features.GeoJsonTooltip(
                fields=['name', 'speciesTotal'],
                aliases=["Province", "Species"]
                )
            ).add_to(prov_map)

        folium.LayerControl().add_to(prov_map)

        import tempfile
        html = prov_map.get_root().render()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name
        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        self._buildFilterTitle(filter, "Canada Provinces Choropleth", count=len(provDict), countUnit="Provinces")

        return(True)

    def loadChoroplethIndiaStates(self, filter):

        from copy import deepcopy
        import folium

        self.title = "India States Choropleth"

        self.filter = deepcopy(filter)

        # find states in filtered sightings
        stateDict = defaultdict()

        minimalSightingList = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)

        for s in minimalSightingList:

            # Only count Indian sightings since we're only showing the India choropleth
            if s["country"] == "IN":

                # Consider only full species, not slash or spuh or hybrid entries
                commonName = s["commonName"]
                if "/" not in commonName and "sp." not in commonName and " x " not in commonName:

                    if self.mdiParent.db.TestSighting(s, filter):

                        stateCode = s["state"]  # already full code e.g. "IN-MH"
                        if stateCode not in stateDict.keys():
                            stateDict[stateCode] = [s]
                        else:
                            stateDict[stateCode].append(s)

        if len(stateDict) == 0:
            return(False)

        stateTotals = defaultdict()
        largestTotal = 0
        for state in stateDict.keys():
            stateSpecies = set()
            for s in stateDict[state]:
                stateSpecies.add(s["commonName"])
            stateTotals[state] = len(stateSpecies)
            if len(stateSpecies) > largestTotal:
                largestTotal = len(stateSpecies)

        geo_file = self.mdiParent.db.in_state_geo

        for f in geo_file["features"]:
            if f["id"] in stateTotals.keys():
                f["properties"]["speciesTotal"] = stateTotals[f["id"]]
            else:
                f["properties"]["speciesTotal"] = 0
                stateTotals[f["id"]] = 0

        state_map = folium.Map(location=[22, 80], zoom_start=4, tiles="CartoDB Positron")

        folium.GeoJson(
            geo_file,
            style_function=lambda feature: {
                'fillColor': self._lerp_orange(stateTotals[feature['id']], largestTotal),
                'color': 'black',
                'weight': .2,
                'fillOpacity': .8,
                },
            tooltip=folium.features.GeoJsonTooltip(
                fields=['name', 'speciesTotal'],
                aliases=["State", "Species"]
                )
            ).add_to(state_map)

        folium.LayerControl().add_to(state_map)

        import tempfile
        html = state_map.get_root().render()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name
        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        self._buildFilterTitle(filter, "India States Choropleth", count=len(stateDict), countUnit="States")

        return(True)

    def loadChoroplethGBCounties(self, filter):

        from copy import deepcopy
        import folium

        self.title = "Great Britain Counties Choropleth"

        self.filter = deepcopy(filter)

        countyDict = defaultdict()

        minimalSightingList = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)

        for s in minimalSightingList:

            # Only count GB sightings
            if s["country"] == "GB":

                commonName = s["commonName"]
                if "/" not in commonName and "sp." not in commonName and " x " not in commonName:

                    if self.mdiParent.db.TestSighting(s, filter):

                        # eBird county field for GB is like "Yorkshire" — look up its code
                        county = s.get("county", "")
                        if county != "":
                            # Strip the "(GB-ENG)" suffix that eBird appends to county names
                            countyName = county.split(" (")[0].strip()
                            if countyName not in countyDict.keys():
                                countyDict[countyName] = [s]
                            else:
                                countyDict[countyName].append(s)

        if len(countyDict) == 0:
            return(False)

        # Build species totals keyed by eBird county name
        countyTotals = defaultdict()
        largestTotal = 0
        for county in countyDict.keys():
            species = set()
            for s in countyDict[county]:
                species.add(s["commonName"])
            countyTotals[county] = len(species)
            if len(species) > largestTotal:
                largestTotal = len(species)

        geo_file = self.mdiParent.db.gb_county_geo

        # Match GeoJSON features by ebird_name property (set during GeoJSON build)
        for f in geo_file["features"]:
            ename = f["properties"].get("ebird_name", f["properties"]["name"])
            if ename in countyTotals.keys():
                f["properties"]["speciesTotal"] = countyTotals[ename]
            else:
                f["properties"]["speciesTotal"] = 0
                countyTotals[ename] = 0

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
            tooltip=folium.features.GeoJsonTooltip(
                fields=['ebird_name', 'speciesTotal'],
                aliases=["County", "Species"]
                )
            ).add_to(county_map)

        folium.LayerControl().add_to(county_map)

        import tempfile
        html = county_map.get_root().render()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name
        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        self._buildFilterTitle(filter, "Great Britain Counties Choropleth", count=len(countyDict), countUnit="Counties")

        return(True)

    def loadChoroplethUSCounties(self, filter):

        from copy import deepcopy
        import folium

        self.title= "US Lower 48 Counties Choropleth"
        
        self.filter = deepcopy(filter)
        
        # find states in filtered sightings
        countyDict = defaultdict()
        
        minimalSightingList = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)
        
        for s in minimalSightingList:
            
            # only count US sightings since we're only showing the US choropleth
            if s["country"] == "US" and s["state"] not in ["US-HI", "US-AK"]:
                
                #only use sightings that have a county code assigned to them
                # some US sightings won't have them, such as if a checklist is for 
                # an entire state, not localized down to a location or county
                if "countyCode" in s.keys():
                            
                    # Consider only full species, not slash or spuh or hybrid entries
                    commonName = s["commonName"]
                    if "/" not in commonName and "sp." not in commonName and " x " not in commonName:
                        
                        if self.mdiParent.db.TestSighting(s, filter):
        
                            if s["countyCode"] not in countyDict.keys():
                                countyDict[s["countyCode"]] = [s]
                            else:
                                countyDict[s["countyCode"]].append(s)                
                                     
        # check if no sightings were found. Return false if none found. Abort and display message.
        if len(countyDict) == 0:
            return(False)

        countyTotals = defaultdict()
        largestTotal = 0
        for county in countyDict.keys():
            countySpecies = set()
            for s in countyDict[county]:
                countySpecies.add(s["commonName"])
            countyTotals[county] = len(countySpecies)
            if len(countySpecies) > largestTotal:
                largestTotal = len(countySpecies)

        # Load the shape of the zone (US counties)
        geo_file = self.mdiParent.db.county_geo
                        
        #add the county values to the geojson so we can access them for tooltips
        for f in geo_file["features"]:
            if f["id"] in countyTotals.keys(): 
                f["properties"]["speciesTotal"] = countyTotals[f["id"]]
            else:
                f["properties"]["speciesTotal"] = 0
                countyTotals[f["id"]] = 0
                    
        # Initialize the folium map
        county_map = folium.Map(location=[39.5, -98.3], zoom_start=4, tiles="CartoDB Positron")

        # Configure the chloropleth layer and add to map
        folium.GeoJson(
            geo_file,
            style_function=lambda feature: {
                'fillColor': self._lerp_orange(countyTotals[feature['id']], largestTotal),
                'color': 'black',
                'weight': 1,
                'fillOpacity': .8,
                'nan_fill_color': 'white'
                },
            tooltip=folium.features.GeoJsonTooltip(
                fields=['name', 'state', 'speciesTotal'],
                aliases=["County", "State", "Species"]
                )
            ).add_to(county_map)
        
        # make the layer control box visible
        folium.LayerControl().add_to(county_map)
                 
        # get the html string from the map
        # Note: the county GeoJSON embeds ~1.2MB of data in a single JS line, which causes
        # QWebEngineView.setHtml() to silently produce a blank page when many counties have
        # non-zero species counts (as in the no-filter case). Writing to a temp file and
        # loading via setUrl() bypasses this Qt internal content-handling limitation.
        import tempfile
        html = county_map.get_root().render()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name

        # Allow the local file page to load Leaflet and other CDN resources
        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        self._buildFilterTitle(filter, "US Lower 48 Counties Choropleth", count=len(countyDict), countUnit="Counties")

        return(True)


    def loadChoroplethWorldCountries(self, filter):

        from copy import deepcopy
        import folium

        self.title= "World Choropleth"
        
        self.filter = deepcopy(filter)
        
        # find states in filtered sightings
        countryDict = defaultdict()
        
        minimalSightingList = self.mdiParent.db.GetMinimalFilteredSightingsList(filter)
        
        for s in minimalSightingList:
            
            # Consider only full species, not slash or spuh or hybrid entries
            commonName = s["commonName"]
            if "/" not in commonName and "sp." not in commonName and " x " not in commonName:
                
                if self.mdiParent.db.TestSighting(s, filter):
                
                    if s["country"] not in countryDict.keys():
                        countryDict[s["country"]] = [s]
                    else:
                        countryDict[s["country"]].append(s)                
                                 
        # check if no sightings were found. Return false if none found. Abort and display message.
        if len(countryDict) == 0:
            return(False)

        countryTotals = defaultdict()
        largestTotal = 0
        for country in countryDict.keys():
            countrySpecies = set()
            for s in countryDict[country]:
                countrySpecies.add(s["commonName"])
            countryTotals[country] = len(countrySpecies)
            if len(countrySpecies) > largestTotal:
                largestTotal = len(countrySpecies)

        # Load the shape of the zone (US counties)
        geo_file = self.mdiParent.db.country_geo
                
        #add the country values to the geojson so we can access them for tooltips
        for f in geo_file["features"]:
            if f["id"] in countryTotals.keys(): 
                f["properties"]["speciesTotal"] = countryTotals[f["id"]]
            else:
                f["properties"]["speciesTotal"] = 0
                countryTotals[f["id"]] = 0
                    
        # Initialize the folium map
        choro_map = folium.Map(location=[1, 1], zoom_start=1, tiles="CartoDB Positron")

        # Configure the chloropleth layer and add to map
        folium.GeoJson(
            geo_file,
            style_function=lambda feature: {
                'fillColor': self._lerp_orange(countryTotals[feature['id']], largestTotal),
                'color': 'black',
                'weight': 1,
                'fillOpacity': .8,
                'nan_fill_color': 'white'
                },
            tooltip=folium.features.GeoJsonTooltip(
                fields=['name', 'speciesTotal'],
                aliases=["Country", "Species"]
                )
            ).add_to(choro_map)
        
        # make the layer control box visible
        folium.LayerControl().add_to(choro_map)
                 
        # get the html string from the map
        import tempfile
        html = choro_map.get_root().render()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(html)
            tmp_path = f.name
        settings = QWebEngineProfile.defaultProfile().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.webView.setUrl(QUrl.fromLocalFile(tmp_path))
        self._buildFilterTitle(filter, "World Choropleth", count=len(countryDict), countUnit="Countries")

        return(True)


    def loadChoroplethWorldSubregion1(self, filter):

        return()


    def showLoadProgress(self, percent):
        
        if percent < 100:
            self.setWindowTitle(self.title + ": " + str(percent) + "%")
        else:
            self.setWindowTitle(self.title)

