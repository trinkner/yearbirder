"""The street basemap used by every folium map in the app.

One place, because 23 call sites across code_Web, code_BigReport and
code_Location build maps and the provider has now changed under us once.

Why Esri and not CARTO: the maps used CARTO's Voyager basemap through folium's
`tiles="CartoDB Voyager"` shorthand.  In August 2026 CARTO began requiring an
API key and started stamping "API KEY REQUIRED / carto.com/basemaps/apikey"
across every tile served without one — the tiles still return HTTP 200 with
real imagery, so nothing errors, the maps simply come back watermarked.

Esri is the natural replacement: the satellite layer in code_Web already uses
Esri's World Imagery and is unaffected, so this keeps the app on one tile
provider instead of two.  OpenStreetMap's own tile servers were the other
candidate, but their usage policy explicitly discourages distributed desktop
applications, which is exactly what Yearbirder is.

An API key was deliberately NOT obtained: a key shipped inside a desktop app is
trivially extractable and would put every user's traffic on one quota.

NOTE the path order — Esri serves {z}/{y}/{x}, not the {z}/{x}/{y} most tile
servers use.  Swapping them silently yields a map of the wrong place.
"""

import folium

TILE_URL = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Street_Map/MapServer/tile/{z}/{y}/{x}")
TILE_ATTR = "Tiles © Esri"
TILE_NAME = "Street Map"


def streetTiles():
    """A fresh basemap layer for one folium.Map(tiles=...).

    Returns a NEW TileLayer every call, never a shared constant: a folium
    MacroElement remembers the map it was added to, so reusing one instance
    across maps corrupts the second map's layer tree.

    Named rather than passed as a bare URL string because the six choropleth
    maps add a LayerControl, and folium derives an unnamed layer's label from
    the URL — which would list the whole tile URL in the control.
    """
    return folium.TileLayer(TILE_URL, attr=TILE_ATTR, name=TILE_NAME)
