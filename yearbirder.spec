# -*- mode: python ; coding: utf-8 -*-

import os, glob
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# PySide6/WebEngine: PyInstaller's PySide6 hooks automatically collect
# QtWebEngineCore.framework (binary + resources + QtWebEngineProcess.app)
# into Contents/Frameworks/. No manual datas entries needed for WebEngine.

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

# PySide6 data files (plugins, translations, etc.)
datas += collect_data_files("PySide6")

# Matplotlib data files (font cache, style sheets, etc.)
datas += collect_data_files("matplotlib")

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
    [],
    exclude_binaries=True,
    name="Yearbirder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Yearbirder",
)

app = BUNDLE(
    coll,
    name="Yearbirder.app",
    icon="icons/Yearbirder.icns",
    bundle_identifier="com.trinkner.yearbirder",
    codesign_identity=None,
    entitlements_file=None,
)
