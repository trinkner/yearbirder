# -*- mode: python ; coding: utf-8 -*-

import os, glob
from PyInstaller.utils.hooks import collect_data_files

# With Homebrew PyQt5, PyInstaller's binary analysis automatically collects
# the real QtWebEngineCore.framework (binary + resources + QtWebEngineProcess.app)
# into Contents/Frameworks/. No manual datas entries needed for WebEngine resources.

datas = [
    ("src/guide", "guide"),
    ("src/us-states.json", "."),
    ("src/us-counties-lower48.json", "."),
    ("src/world-countries.json", "."),
    ("src/ca-provinces.json", "."),
    ("src/in-states.json", "."),
    ("src/gb-counties.json", "."),
    ("src/eBird_BBLCodes.csv", "."),
    ("src/eBird_Taxonomy.csv", "."),
    ("src/ebird_api_ref_location_eBird_list_subnational1.csv", "."),
]

# White toolbar icons (loaded from filesystem at runtime)
for _f in glob.glob("src/icon_*_white.png"):
    datas.append((_f, "."))

# PyQt5 data files (plugins, translations, etc.)
datas += collect_data_files("PyQt5")

hiddenimports = [
    "PyQt5.QtWebEngineWidgets",
    "PyQt5.QtWebEngineCore",
    "PyQt5.QtWebEngine",
]

a = Analysis(
    ["src/yearbird.py"],
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
    name="Yearbird",
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
    name="Yearbird",
)

app = BUNDLE(
    coll,
    name="Yearbird.app",
    icon="icons/Yearbird.icns",
    bundle_identifier=None,
    codesign_identity=None,
    entitlements_file=None,
)
