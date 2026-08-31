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
    "mutagen",
    "mutagen.wave",
    "mutagen.id3",
    # Audio decode: libsndfile via soundfile (+ its cffi binding).  The native
    # libsndfile shared library is bundled into _soundfile_data/ by hook-soundfile.
    "soundfile",
    "cffi",
    # Audio resampling: libsoxr via python-soxr (self-contained abi3 extension;
    # libsoxr is statically linked, so there is no separate shared lib to bundle).
    "soxr",
    "soxr.soxr_ext",
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
    excludes=["gi"],
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
    info_plist={
        # The download page has always said "macOS 13+", but the bundle declared
        # nothing, and the Mach-O header inherits minos 11.0 from the Python and
        # wheels it is built against — so macOS would happily launch it on
        # Big Sur or Monterey, which are untested.  Declaring the requirement
        # here makes macOS enforce what the page promises: an older system
        # refuses with a clear message instead of failing in some obscure way
        # later.  Raise BOTH this and the page together if the floor ever moves.
        "LSMinimumSystemVersion": "13.0",
    },
)
