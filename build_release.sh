#!/bin/bash
# build_release.sh — Build, sign, notarize, and staple Yearbird.app and Yearbird.dmg
#
# Prerequisites:
#   - Developer ID certificate in Keychain
#   - notarytool credentials stored: xcrun notarytool store-credentials "yearbird"
#   - PySide6 and PyInstaller installed under /opt/homebrew/bin/python3 (NOT the project venv)
#
# Usage:  ./build_release.sh

set -e  # exit on any error

SIGN_ID="Developer ID Application: RICHARD L TRINKNER (SPC3RCL6VT)"
ENTS="entitlements.plist"
KEYCHAIN_PROFILE="yearbird"
WORK_APP="/tmp/Yearbird.app"
WORK_ZIP="/tmp/Yearbird.zip"
WORK_DMG="/tmp/Yearbird.dmg"
WORK_RW_DMG="/tmp/Yearbird_rw.dmg"
DMG_STAGING="/tmp/Yearbird_dmg_staging"

echo "=== Step 1: PyInstaller build ==="
/opt/homebrew/bin/python3 -m PyInstaller Yearbird.spec --noconfirm
echo "Build complete."

echo ""
echo "=== Step 2: Copy to /tmp (preserving symlinks) and clean ==="
rm -rf "$WORK_APP"
# ditto preserves macOS symlinks (cp -r does not)
ditto dist/Yearbird.app "$WORK_APP"
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
# Use maxdepth 1 + file-type check — avoids path-filter bugs with find inside Yearbird.app
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
    "$WORK_APP/Contents/Frameworks/Python.framework/Versions/3.12/Python"
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
codesign --display --verbose=4 "$WORK_APP/Contents/MacOS/Yearbird" 2>&1 | grep "flags=.*runtime" || {
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
cd /tmp && ditto -c -k --keepParent Yearbird.app Yearbird.zip
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
ditto "$WORK_APP" dist/Yearbird.app
echo "dist/Yearbird.app is ready."

echo ""
echo "=== Step 9: Create DMG ==="
# Build a staging folder with the app and an Applications symlink.
# Use ditto (not cp -r) so the app's internal symlinks are preserved.
rm -rf "$DMG_STAGING" && mkdir "$DMG_STAGING"
ditto "$WORK_APP" "$DMG_STAGING/Yearbird.app"
ln -s /Applications "$DMG_STAGING/Applications"

rm -f "$WORK_DMG" "$WORK_RW_DMG"
hdiutil create -volname "Yearbird" -srcfolder "$DMG_STAGING" -ov -format UDRW "$WORK_RW_DMG"
hdiutil convert "$WORK_RW_DMG" -format UDZO -imagekey zlib-level=9 -o "$WORK_DMG"
rm "$WORK_RW_DMG" && rm -rf "$DMG_STAGING"
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
cp "$WORK_DMG" dist/Yearbird.dmg
echo "dist/Yearbird.dmg is ready for distribution."

echo ""
echo "=== All done! ==="
