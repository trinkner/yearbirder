#!/bin/bash
# build_release.sh — Build, sign, notarize, and staple Yearbirder_vX.XX.app and .dmg
#
# Prerequisites:
#   - Developer ID certificate in Keychain
#   - notarytool credentials stored: xcrun notarytool store-credentials "yearbirder"
#   - PySide6 and PyInstaller installed in the project venv (python.org Python 3.14)
#
# Usage:  ./build_release.sh

set -e  # exit on any error

# ── Version check ─────────────────────────────────────────────────────────────
VERSION=$(grep 'versionNumber = ' src/code_MainWindow.py | sed 's/.*"\(.*\)".*/\1/')
VERSION_DATE=$(grep 'versionDate = ' src/code_MainWindow.py | sed 's/.*"\(.*\)".*/\1/')
echo ""
echo "Current version in code_MainWindow.py: ${VERSION}  (${VERSION_DATE})"
echo ""
read -p "Have you updated the version number? (y/n): " VERSION_CONFIRMED
if [[ "$VERSION_CONFIRMED" != "y" && "$VERSION_CONFIRMED" != "Y" ]]; then
    echo "Please update versionNumber and versionDate in src/code_MainWindow.py, then re-run."
    exit 1
fi

APP_NAME="Yearbirder"
DMG_NAME="Yearbirder_v${VERSION}"
echo "Building ${DMG_NAME}"

SIGN_ID="Developer ID Application: RICHARD L TRINKNER (SPC3RCL6VT)"
ENTS="entitlements.plist"
KEYCHAIN_PROFILE="yearbirder"
WORK_APP="/tmp/${APP_NAME}.app"
WORK_ZIP="/tmp/${APP_NAME}.zip"
WORK_DMG="/tmp/${DMG_NAME}.dmg"
WORK_RW_DMG="/tmp/${DMG_NAME}_rw.dmg"
DMG_STAGING="/tmp/${DMG_NAME}_dmg_staging"

echo "=== Step 1: PyInstaller build ==="
venv/bin/python3 -m PyInstaller Yearbirder.spec --noconfirm
echo "Build complete."

echo ""
echo "=== Step 2: Copy to /tmp (preserving symlinks) and clean ==="
rm -rf "$WORK_APP"
# ditto preserves macOS symlinks (cp -r does not)
ditto dist/Yearbirder.app "$WORK_APP"
# Remove Dropbox extended attributes that break codesign
xattr -cr "$WORK_APP"
# Remove .dist-info dirs — not code objects, cause codesign to choke
find "$WORK_APP/Contents/Frameworks" -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true
# Remove Qt developer tool apps (Linguist, Designer, Assistant) — not needed at runtime.
# These have a split-bundle structure (circular symlinks between Frameworks and Resources)
# that codesign cannot handle, and they break notarization if left unsigned.
for appname in Linguist Designer Assistant; do
    rm -rf "$WORK_APP/Contents/Frameworks/PySide6/${appname}.app"
    rm -rf "$WORK_APP/Contents/Frameworks/PySide6/${appname}__dot__app"
    rm -rf "$WORK_APP/Contents/Resources/PySide6/${appname}.app"
done
echo "Copy and cleanup done."

echo ""
echo "=== Step 3: Sign (leaves → frameworks → app) ==="

# 3a. All dylibs and .so extension modules
find "$WORK_APP" -type f \( -name "*.dylib" -o -name "*.so" \) | while read f; do
    codesign --force --options runtime --timestamp \
        --entitlements "$ENTS" --sign "$SIGN_ID" "$f" 2>/dev/null
done
echo "  3a: dylibs and .so files signed"

# 3b. Plain Mach-O executables in PySide6 flat dir and Qt/libexec
# (balsam, lupdate, lrelease, balsamui, qmlformat, qsb, svgtoqml, qmllint, qmlls, rcc, etc.)
# Use maxdepth 1 + file-type check — avoids path-filter bugs with find inside Yearbirder.app
for dir in \
    "$WORK_APP/Contents/Frameworks/PySide6" \
    "$WORK_APP/Contents/Frameworks/PySide6/Qt/libexec"; do
    find "$dir" -maxdepth 1 -type f | while read f; do
        if file "$f" | grep -q "Mach-O"; then
            codesign --force --options runtime --timestamp \
                --entitlements "$ENTS" --sign "$SIGN_ID" "$f" 2>/dev/null
        fi
    done
done
echo "  3b: PySide6 plain executables signed"

# 3c. Python.framework: binary first, then the framework bundle
codesign --force --options runtime --timestamp \
    --entitlements "$ENTS" --sign "$SIGN_ID" \
    "$WORK_APP/Contents/Frameworks/Python.framework/Versions/3.14/Python"
codesign --force --options runtime --timestamp \
    --entitlements "$ENTS" --sign "$SIGN_ID" \
    "$WORK_APP/Contents/Frameworks/Python.framework"
echo "  3c: Python.framework signed"

# 3d. QtWebEngineCore: sign the binary and its nested QtWebEngineProcess.app before
# signing the whole framework (the nested app must be signed as a unit)
QTWE="$WORK_APP/Contents/Frameworks/PySide6/Qt/lib/QtWebEngineCore.framework"
codesign --force --options runtime --timestamp \
    --entitlements "$ENTS" --sign "$SIGN_ID" \
    "$QTWE/Versions/A/QtWebEngineCore" 2>/dev/null
codesign --force --options runtime --timestamp \
    --entitlements "$ENTS" --sign "$SIGN_ID" \
    "$QTWE/Versions/A/Helpers/QtWebEngineProcess.app" 2>/dev/null
echo "  3d: QtWebEngineCore binary and nested app signed"

# 3e. All Qt .framework bundles (sort by path length descending = deepest first)
find "$WORK_APP/Contents/Frameworks" -name "*.framework" \
    -not -path "*/Python.framework*" | \
    awk '{ print length, $0 }' | sort -rn | awk '{print $2}' | while read f; do
    codesign --force --options runtime --timestamp \
        --entitlements "$ENTS" --sign "$SIGN_ID" "$f" 2>/dev/null
done
echo "  3e: Qt frameworks signed"

# 3f. Main app bundle (signs and seals everything including the main executable)
codesign --force --options runtime --timestamp \
    --entitlements "$ENTS" --sign "$SIGN_ID" "$WORK_APP"
echo "  3f: main app bundle signed"

echo ""
echo "=== Step 4: Verify signature ==="
codesign --verify --verbose "$WORK_APP"
# Confirm hardened runtime flag is set
codesign --display --verbose=4 "$WORK_APP/Contents/MacOS/Yearbirder" 2>&1 | grep "flags=.*runtime" || {
    echo "ERROR: Hardened runtime flag not set!"; exit 1
}
# Confirm no broken symlinks (would cause spctl to reject even after notarization)
broken=$(find "$WORK_APP" -type l | while read link; do
    target=$(readlink "$link")
    dir=$(dirname "$link")
    [[ "$target" == /* ]] && resolved="$target" || resolved="$dir/$target"
    [ ! -e "$resolved" ] && echo "$link -> $target"
done) || true
if [ -n "$broken" ]; then
    echo "ERROR: Broken symlinks found:"; echo "$broken"; exit 1
fi
echo "Signature OK (hardened runtime confirmed, no broken symlinks)"

echo ""
echo "=== Step 5: Notarize ==="
rm -f "$WORK_ZIP"
cd /tmp && ditto -c -k --keepParent "${APP_NAME}.app" "${APP_NAME}.zip"
cd - > /dev/null
xcrun notarytool submit "$WORK_ZIP" \
    --keychain-profile "$KEYCHAIN_PROFILE" \
    --wait

echo ""
echo "=== Step 6: Staple ==="
xcrun stapler staple "$WORK_APP"

echo ""
echo "=== Step 7: Gatekeeper check ==="
spctl --assess --type exec --verbose "$WORK_APP"

echo ""
echo "=== Step 8: Copy stapled app back to dist/ ==="
rm -rf "dist/${APP_NAME}.app"
ditto "$WORK_APP" "dist/${APP_NAME}.app"
echo "dist/${APP_NAME}.app is ready."

echo ""
echo "=== Step 9: Create DMG ==="
# Build a staging folder: app, Applications symlink, and hidden background image folder.
rm -rf "$DMG_STAGING" && mkdir "$DMG_STAGING"
ditto "$WORK_APP" "$DMG_STAGING/${APP_NAME}.app"
ln -s /Applications "$DMG_STAGING/Applications"
mkdir "$DMG_STAGING/.background"
cp src/dmg_background.png "$DMG_STAGING/.background/dmg_background.png"

rm -f "$WORK_DMG" "$WORK_RW_DMG"
hdiutil create -volname "${DMG_NAME}" -srcfolder "$DMG_STAGING" -ov -format UDRW "$WORK_RW_DMG"

# Mount and configure Finder window (background, icon positions, window size)
MOUNT_POINT="/Volumes/${DMG_NAME}"
hdiutil attach "$WORK_RW_DMG" -mountpoint "$MOUNT_POINT"
sleep 2
# Hide .background on the mounted APFS volume (chflags on staging is not preserved)
chflags hidden "${MOUNT_POINT}/.background"
rm -f "${MOUNT_POINT}/.DS_Store"
osascript << APPLESCRIPT
tell application "Finder"
  tell disk "${DMG_NAME}"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set the bounds of container window to {100, 100, 640, 528}
    set viewOptions to icon view options of container window
    set arrangement of viewOptions to not arranged
    set icon size of viewOptions to 100
    set background picture of viewOptions to file ".background:dmg_background.png"
    delay 3
    set position of item "${APP_NAME}.app" of container window to {135, 195}
    set position of item "Applications" of container window to {405, 195}
    try
      set position of item ".background" of container window to {900, 900}
    end try
    update without registering applications
    delay 3
    close
  end tell
end tell
APPLESCRIPT
# Remove .fseventsd created by macOS when mounting the APFS volume
rm -rf "${MOUNT_POINT}/.fseventsd"
sync
hdiutil detach "$MOUNT_POINT"
rm -rf "$DMG_STAGING"

hdiutil convert "$WORK_RW_DMG" -format UDZO -imagekey zlib-level=9 -o "$WORK_DMG"
rm "$WORK_RW_DMG"
echo "DMG created."

echo ""
echo "=== Step 10: Sign DMG ==="
codesign --force --sign "$SIGN_ID" --timestamp "$WORK_DMG"
codesign --verify --verbose "$WORK_DMG"
echo "DMG signed."

echo ""
echo "=== Step 11: Notarize DMG ==="
xcrun notarytool submit "$WORK_DMG" \
    --keychain-profile "$KEYCHAIN_PROFILE" \
    --wait

echo ""
echo "=== Step 12: Staple DMG ==="
xcrun stapler staple "$WORK_DMG"
spctl --assess --type open --context context:primary-signature --verbose "$WORK_DMG"

echo ""
echo "=== Step 13: Copy DMG to dist/ ==="
cp "$WORK_DMG" "dist/${DMG_NAME}.dmg"
echo "dist/${DMG_NAME}.dmg is ready for distribution."

echo ""
echo "=== All done! ==="
