#!/bin/bash
# rebuild_dmg.sh — Rebuild, sign, notarize, staple, and re-upload the DMG for the current version.
# Uses the already-signed dist/Yearbirder.app (skip PyInstaller + app notarization).
#
# Usage:  ./rebuild_dmg.sh

set -e

VERSION=$(grep 'versionNumber = ' src/code_MainWindow.py | sed 's/.*"\(.*\)".*/\1/')
echo "Rebuilding DMG for v${VERSION}"

APP_NAME="Yearbirder"
DMG_NAME="Yearbirder_v${VERSION}"
SIGN_ID="Developer ID Application: RICHARD L TRINKNER (SPC3RCL6VT)"
KEYCHAIN_PROFILE="yearbirder"
WORK_APP="/tmp/${APP_NAME}.app"
WORK_DMG="/tmp/${DMG_NAME}.dmg"
WORK_RW_DMG="/tmp/${DMG_NAME}_rw.dmg"
DMG_STAGING="/tmp/${DMG_NAME}_dmg_staging"

echo ""
echo "=== Step 1: Copy stapled app to /tmp ==="
rm -rf "$WORK_APP"
ditto "dist/${APP_NAME}.app" "$WORK_APP"
echo "Copied dist/${APP_NAME}.app → $WORK_APP"

echo ""
echo "=== Step 2: Create DMG ==="
rm -rf "$DMG_STAGING" && mkdir "$DMG_STAGING"
ditto "$WORK_APP" "$DMG_STAGING/${APP_NAME}.app"
ln -s /Applications "$DMG_STAGING/Applications"
mkdir "$DMG_STAGING/.background"
cp src/dmg_background.png "$DMG_STAGING/.background/dmg_background.png"

rm -f "$WORK_DMG" "$WORK_RW_DMG"
hdiutil create -volname "${DMG_NAME}" -srcfolder "$DMG_STAGING" -ov -format UDRW "$WORK_RW_DMG"

# Let macOS pick the mount point (avoids conflict if an older DMG is already mounted).
# The embedded volume name stays ${DMG_NAME}, so the background alias resolves correctly
# when users mount the finished DMG.
ATTACH_OUT=$(hdiutil attach "$WORK_RW_DMG" -readwrite -noverify)
echo "$ATTACH_OUT"
MOUNT_POINT=$(echo "$ATTACH_OUT" | tail -1 | cut -f3-)
DISK_DISPLAY=$(basename "$MOUNT_POINT")
echo "Mounted at: $MOUNT_POINT  (Finder name: $DISK_DISPLAY)"

sleep 5   # give Finder time to register the volume and render the app icon
chflags hidden "${MOUNT_POINT}/.background"
rm -f "${MOUNT_POINT}/.DS_Store"

osascript << APPLESCRIPT
tell application "Finder"
  tell disk "${DISK_DISPLAY}"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set the bounds of container window to {100, 100, 640, 528}
    set viewOptions to icon view options of container window
    set arrangement of viewOptions to not arranged
    set icon size of viewOptions to 100
    set background picture of viewOptions to file ".background:dmg_background.png"
    delay 5
    set position of item "${APP_NAME}.app" of container window to {135, 195}
    set position of item "Applications" of container window to {405, 195}
    try
      set position of item ".background" of container window to {900, 900}
    end try
    update without registering applications
    delay 5
    close
  end tell
end tell
APPLESCRIPT

rm -rf "${MOUNT_POINT}/.fseventsd"
sync
hdiutil detach "$MOUNT_POINT"   # detach by actual mount point, not hardcoded name
rm -rf "$DMG_STAGING"

hdiutil convert "$WORK_RW_DMG" -format UDZO -imagekey zlib-level=9 -o "$WORK_DMG"
rm "$WORK_RW_DMG"
echo "DMG created."

echo ""
echo "=== Step 3: Sign DMG ==="
codesign --force --sign "$SIGN_ID" --timestamp "$WORK_DMG"
codesign --verify --verbose "$WORK_DMG"
echo "DMG signed."

echo ""
echo "=== Step 4: Notarize DMG ==="
xcrun notarytool submit "$WORK_DMG" \
    --keychain-profile "$KEYCHAIN_PROFILE" \
    --wait

echo ""
echo "=== Step 5: Staple DMG ==="
xcrun stapler staple "$WORK_DMG"
spctl --assess --type open --context context:primary-signature --verbose "$WORK_DMG"

echo ""
echo "=== Step 6: Copy DMG to dist/ ==="
cp "$WORK_DMG" "dist/${DMG_NAME}.dmg"
echo "dist/${DMG_NAME}.dmg ready."

echo ""
echo "=== Step 7: Upload to GitHub release v${VERSION} ==="
gh release upload "v${VERSION}" "dist/${DMG_NAME}.dmg" --clobber
echo "Uploaded dist/${DMG_NAME}.dmg to GitHub release v${VERSION}."

echo ""
echo "=== All done! ==="
