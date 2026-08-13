#!/usr/bin/env python3
"""Build the macOS app icon (Yearbirder.icns) from the square source artwork.

macOS does NOT round or inset an app icon for you: whatever the .icns contains
is drawn as-is in the Dock and the Cmd-Tab switcher.  Yearbirder_Icon_1024.png
is a full-bleed square (correct for Windows, where taskbar icons fill their
canvas), so using it directly made Yearbirder appear larger and squarer than
every system app beside it.

Apple's macOS icon grid puts the icon body in an 824x824 rounded square centred
on a 1024x1024 canvas — a 100px margin on every side.  Measuring the alpha of
/System/Applications/Mail.app's icon confirms exactly that, so rather than
approximating the "squircle" corner with a rounded rectangle, this script lifts
the anti-aliased mask straight off a system icon.  The result is pixel-identical
in size and corner shape to the apps Yearbirder sits next to.

Usage:  venv/bin/python3 icons/make_macos_icon.py
Writes: icons/Yearbirder_Icon_macOS_1024.png  (tracked, the .icns source)
        icons/Yearbirder.icns                 (gitignored build artifact)

The Windows .ico and MSIX assets are generated from Yearbirder_Icon_1024.png by
the CI workflow and are deliberately left full-bleed.
"""

import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_ART = os.path.join(HERE, "Yearbirder_Icon_1024.png")
MACOS_PNG  = os.path.join(HERE, "Yearbirder_Icon_macOS_1024.png")
# Embedded in the Qt resource bundle (src/icons.qrc) and set as the application
# icon on macOS, which is what the Dock and the Cmd-Tab switcher show when the
# app runs from source — there is no .app bundle then, so the .icns below is
# never consulted.  512px covers the largest Dock/switcher size at 2x; the 1024
# original would add three-quarters of a megabyte to icons_rc.py for nothing.
MACOS_RES_PNG = os.path.join(HERE, "Yearbirder_Icon_macOS_512.png")
RES_SIZE      = 512
ICNS       = os.path.join(HERE, "Yearbirder.icns")

# Any system app whose icon is a plain rounded square works as the mask donor.
MASK_DONORS = [
    "/System/Applications/Mail.app/Contents/Resources/ApplicationIcon.icns",
    "/System/Applications/Notes.app/Contents/Resources/AppIcon.icns",
]

CANVAS = 1024
BODY   = 824          # Apple's macOS icon grid: 824x824 body, 100px margins
MARGIN = (CANVAS - BODY) // 2

# The sizes an .icns needs; (filename, pixel size).
ICONSET = [
    ("icon_16x16.png", 16),      ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),      ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),   ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),   ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),   ("icon_512x512@2x.png", 1024),
]


def system_squircle_mask():
    """The anti-aliased 824x824 rounded-square mask macOS system icons use."""
    donor = next((p for p in MASK_DONORS if os.path.exists(p)), None)
    if donor is None:
        raise SystemExit("No system icon found to take the corner mask from.")
    with tempfile.TemporaryDirectory() as td:
        png = os.path.join(td, "donor.png")
        subprocess.run(
            ["sips", "-s", "format", "png",
             "--resampleHeightWidth", str(CANVAS), str(CANVAS), donor, "--out", png],
            check=True, capture_output=True)
        alpha = Image.open(png).convert("RGBA").getchannel("A")
    # Crop away the soft drop shadow outside the body; what remains is the
    # squircle itself, anti-aliased at its edge.
    mask = alpha.crop((MARGIN, MARGIN, MARGIN + BODY, MARGIN + BODY))
    body = mask.point(lambda v: 255 if v >= 128 else 0).getbbox()
    if body != (0, 0, BODY, BODY):
        raise SystemExit(f"Unexpected donor geometry: body bbox {body}")
    return mask, os.path.basename(donor)


def main():
    mask, donor = system_squircle_mask()
    art = Image.open(SOURCE_ART).convert("RGBA").resize((BODY, BODY), Image.LANCZOS)
    art.putalpha(mask)

    icon = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    icon.paste(art, (MARGIN, MARGIN), art)
    icon.save(MACOS_PNG)
    print(f"wrote {MACOS_PNG}  (body {BODY}x{BODY}, mask from {donor})")

    icon.resize((RES_SIZE, RES_SIZE), Image.LANCZOS).save(MACOS_RES_PNG, optimize=True)
    print(f"wrote {MACOS_RES_PNG}  ({os.path.getsize(MACOS_RES_PNG) / 1024:.0f} KB, "
          f"for src/icons.qrc — re-run pyside6-rcc after this)")

    with tempfile.TemporaryDirectory() as td:
        iconset = os.path.join(td, "Yearbirder.iconset")
        os.makedirs(iconset)
        for name, size in ICONSET:
            icon.resize((size, size), Image.LANCZOS).save(os.path.join(iconset, name))
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", ICNS], check=True)
    print(f"wrote {ICNS}  ({os.path.getsize(ICNS) / 1024:.0f} KB)")


if __name__ == "__main__":
    if sys.platform != "darwin":
        raise SystemExit("macOS only (uses sips and iconutil).")
    main()
