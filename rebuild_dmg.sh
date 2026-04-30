#!/bin/bash
# rebuild_dmg.sh — Recreate DMG from already-built dist/Yearbirder.app
# Use this when only the DMG appearance needs updating (background, icon layout)
# without re-running PyInstaller or re-notarizing the app.
#
# Requires: dist/Yearbirder.app already signed, notarized, and stapled.

set -e

VERSION=$(grep 'versionNumber = ' src/code_MainWindow.py | sed 's/.*"\(.*\)".*/\1/')
APP_NAME="Yearbirder"
DMG_NAME="Yearbirder_v${VERSION}"
SIGN_ID="Developer ID Application: RICHARD L TRINKNER (SPC3RCL6VT)"
KEYCHAIN_PROFILE="yearbirder"

WORK_APP="/tmp/${APP_NAME}.app"
WORK_DMG="/tmp/${DMG_NAME}.dmg"
WORK_RW_DMG="/tmp/${DMG_NAME}_rw.dmg"
DMG_STAGING="/tmp/${DMG_NAME}_dmg_staging"

echo "Rebuilding DMG for v${VERSION} from dist/${APP_NAME}.app ..."

echo "=== Copy stapled app to /tmp ==="
rm -rf "$WORK_APP"
ditto "dist/${APP_NAME}.app" "$WORK_APP"

echo "=== Create DMG staging ==="
rm -rf "$DMG_STAGING" && mkdir "$DMG_STAGING"
ditto "$WORK_APP" "$DMG_STAGING/${APP_NAME}.app"
ln -s /Applications "$DMG_STAGING/Applications"
mkdir "$DMG_STAGING/.background"
cp src/dmg_background.png "$DMG_STAGING/.background/dmg_background.png"

rm -f "$WORK_DMG" "$WORK_RW_DMG"
hdiutil create -volname "${DMG_NAME}" -srcfolder "$DMG_STAGING" -ov -format UDRW "$WORK_RW_DMG"

echo "=== Configure Finder window ==="
MOUNT_POINT="/Volumes/${DMG_NAME}"
hdiutil attach "$WORK_RW_DMG" -mountpoint "$MOUNT_POINT"
sleep 2
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
rm -rf "${MOUNT_POINT}/.fseventsd"
sync
hdiutil detach "$MOUNT_POINT"
rm -rf "$DMG_STAGING"

echo "=== Convert to compressed read-only DMG ==="
hdiutil convert "$WORK_RW_DMG" -format UDZO -imagekey zlib-level=9 -o "$WORK_DMG"
rm "$WORK_RW_DMG"

echo "=== Sign DMG ==="
codesign --force --sign "$SIGN_ID" --timestamp "$WORK_DMG"
codesign --verify --verbose "$WORK_DMG"

echo "=== Notarize DMG ==="
xcrun notarytool submit "$WORK_DMG" \
    --keychain-profile "$KEYCHAIN_PROFILE" \
    --wait

echo "=== Staple DMG ==="
xcrun stapler staple "$WORK_DMG"
spctl --assess --type open --context context:primary-signature --verbose "$WORK_DMG"

echo "=== Copy to dist/ ==="
cp "$WORK_DMG" "dist/${DMG_NAME}.dmg"
echo ""
echo "Done — dist/${DMG_NAME}.dmg is ready."
