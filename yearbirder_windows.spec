# -*- mode: python ; coding: utf-8 -*-
# Windows build spec — no BUNDLE section (macOS-only).
# Generated icon: icons/Yearbirder.ico (created from PNG in CI workflow).

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ("src/guide", "guide"),
    ("src/us-states.json", "."),
    ("src/us-counties-lower48.json", "."),
    ("src/world-countries.json", "."),
    ("src/ca-provinces.json", "."),
    ("src/in-states.json", "."),
    ("src/gb-counties.json", "."),
    ("src/eBird_BBLCodes.csv", "."),
    ("src/eBird_Taxonomy_2025.csv", "."),
    ("src/ebird_api_ref_location_eBird_list_subnational1.csv", "."),
]

datas += collect_data_files("PySide6")
datas += collect_data_files("matplotlib")
datas += collect_data_files("folium")
datas += collect_data_files("branca")

hiddenimports = [
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebChannel",
    "matplotlib.backends.backend_qtagg",
    "matplotlib",
]

a = Analysis(
    ["src/yearbirder.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    exclude_binaries=False,
    name="Yearbirder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="icons/Yearbirder.ico",
)
