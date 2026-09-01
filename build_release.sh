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

# ── Pre-flight checklist ──────────────────────────────────────────────────────
# Everything checked here has to be right BEFORE the build, because each item is
# baked into the artifact: the User Guide ships inside the .app and About
# Yearbirder is compiled from code_Web.py.  Discovering any of it afterwards
# means rebuilding, re-signing and re-notarizing from scratch — 20 minutes and
# two round-trips to Apple.  The steps that come after the build are printed at
# the end of a successful run.
#
# Anything that can be verified mechanically is verified rather than asked
# about; a yes/no prompt for something the script could check itself just trains
# you to type "y".  Only the two genuinely human judgements are prompted for.
VERSION=$(grep 'versionNumber = ' src/code_MainWindow.py | sed 's/.*"\(.*\)".*/\1/')
VERSION_DATE=$(grep 'versionDate = ' src/code_MainWindow.py | sed 's/.*"\(.*\)".*/\1/')

GUIDE_HTML="src/guide/guide_Yearbirder.html"
HISTORY_HTML="web/history.html"
ABOUT_SRC="src/code_Web.py"

preflight_problems=0
ok()   { echo "   ok   $1"; }
warn() { echo "   --   $1"; preflight_problems=$((preflight_problems + 1)); }

# Released versions live as tags on the remote.  The local tag list is NOT a
# reliable substitute: a release created with `gh release create` tags the
# remote only, so v2.13 was absent locally the day after it shipped.
#
# Filter to vN.N tags specifically: the repo also carries non-release tags such
# as "pyside6-stable", and an unfiltered list sorts one of those to the top and
# produces nonsense like 'v"pyside6-stable" was never demoted'.
RELEASED_TAGS=$(git ls-remote --tags origin 2>/dev/null \
                | awk -F/ '{print $NF}' | grep -v '\^{}' \
                | grep -E '^v[0-9]+\.[0-9]+$' || true)
if [ -z "$RELEASED_TAGS" ]; then
    echo "(could not reach the remote — falling back to local tags)"
    RELEASED_TAGS=$(git tag 2>/dev/null | grep -E '^v[0-9]+\.[0-9]+$' || true)
fi
PREV_VERSION=$(echo "$RELEASED_TAGS" | sed 's/^v//' | sort -V | tail -1)

echo ""
echo "=============================================================="
echo " Pre-flight checklist for v${VERSION}"
echo "=============================================================="
echo ""
echo " 1. Version number and date"
if echo "$RELEASED_TAGS" | grep -qx "v${VERSION}"; then
    warn "v${VERSION} is already released — bump versionNumber in src/code_MainWindow.py"
else
    ok "version ${VERSION} is not yet released"
fi
VD_EPOCH=$(date -j -f "%B %d, %Y" "$VERSION_DATE" +%s 2>/dev/null || true)
if [ -z "$VD_EPOCH" ]; then
    warn "versionDate \"${VERSION_DATE}\" is not in \"Month D, YYYY\" form"
else
    VD_AGE=$(( ( $(date +%s) - VD_EPOCH ) / 86400 ))
    if [ "$VD_AGE" -gt 14 ]; then
        warn "versionDate is ${VD_AGE} days old (${VERSION_DATE}) — left over from the last release?"
    else
        ok "versionDate ${VERSION_DATE} is current"
    fi
fi

echo ""
echo " 2. What's New on the website (${HISTORY_HTML})"
if grep -q "release-version\">v${VERSION}<" "$HISTORY_HTML" 2>/dev/null; then
    ok "an entry for v${VERSION} exists"
else
    warn "no v${VERSION} entry yet"
fi

echo ""
echo " 3. User Guide (${GUIDE_HTML}) — ships inside the .app"
GUIDE_HITS=$(grep -c "What's New in v${VERSION}" "$GUIDE_HTML" 2>/dev/null || true)
if [ "${GUIDE_HITS:-0}" -ge 2 ]; then
    ok "What's New heading and table-of-contents entry both name v${VERSION}"
elif [ "${GUIDE_HITS:-0}" -eq 1 ]; then
    warn "only one of the What's New heading / TOC entry says v${VERSION} — the other is stale"
else
    warn "no \"What's New in v${VERSION}\" section"
fi
if [ -n "$PREV_VERSION" ] && ! grep -q "Earlier changes in v${PREV_VERSION}" "$GUIDE_HTML"; then
    warn "v${PREV_VERSION} was never demoted to \"Earlier changes in v${PREV_VERSION}\""
fi

echo ""
echo " 4. Credits in About Yearbirder (${ABOUT_SRC})"
CREDITS_LINE=$(grep -n "The Chromium Authors" "$ABOUT_SRC" | head -1 | cut -d: -f1 || true)
echo "        third-party credits block starts near ${ABOUT_SRC}:${CREDITS_LINE:-?}"

echo ""
echo " 5. Working tree"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    warn "uncommitted changes — commit them so the build matches what you push"
    git status --short --untracked-files=no | sed 's/^/        /'
else
    ok "clean"
fi

echo ""
echo "--------------------------------------------------------------"
if [ "$preflight_problems" -gt 0 ]; then
    echo " ${preflight_problems} item(s) above need attention."
else
    echo " All mechanical checks passed."
fi
echo ""
echo " Confirm by eye — neither can be checked mechanically:"
echo "   * the User Guide documents every new feature in this release"
echo "   * About Yearbirder credits every library, map provider and data"
echo "     source, including anything added or swapped this cycle"
echo "--------------------------------------------------------------"
echo ""
read -p "Proceed with the build for v${VERSION}? (y/n): " PREFLIGHT_OK
if [[ "$PREFLIGHT_OK" != "y" && "$PREFLIGHT_OK" != "Y" ]]; then
    echo "Stopped. Nothing was built."
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

# codesign's --timestamp option calls out to Apple's timestamp authority over
# the network on every invocation. A transient failure there (seen in
# practice) used to kill the whole build with NO diagnostic, because
# routine "replacing existing signature" notices were piped to /dev/null at
# each call site — which silently swallowed the one failure that actually
# mattered too, along with set -e aborting mid-loop with nothing printed.
# codesign_retry() retries a transient failure a few times and only ever
# prints codesign's output if every attempt still fails, so a real failure
# is always visible and points at the exact file that failed.
codesign_retry() {
    local target="$1"; shift
    local attempt out
    for attempt in 1 2 3; do
        if out=$(codesign --force --timestamp "$@" --sign "$SIGN_ID" "$target" 2>&1); then
            return 0
        fi
        echo "  (codesign attempt $attempt/3 failed for $target, retrying...)"
        sleep 3
    done
    echo "ERROR: codesign failed 3/3 attempts on: $target"
    echo "$out"
    exit 1
}

# Signing a leaf/framework/app inside the bundle always wants hardened
# runtime + the shared entitlements; the DMG (step 10) does not, and calls
# codesign_retry directly instead.
sign_file() {
    codesign_retry "$1" --options runtime --entitlements "$ENTS"
}

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
# Remove leftover CMake build objects shipped inside the PySide6 wheel's QML
# plugin dirs (e.g. Qt/labs/assetdownloader/objects-RelWithDebInfo/*.o) — not
# runtime files, and an unsigned .o inside the bundle fails whole-bundle
# codesign ("code object is not signed at all").
find "$WORK_APP/Contents/Frameworks" -type d -name "objects-*" -exec rm -rf {} + 2>/dev/null || true
# PyInstaller mirrors QML/data files between Frameworks and Resources via
# symlinks, so removing the objects-* dirs above can leave a dangling
# Resources symlink pointing at a path that no longer exists. Prune those too.
find "$WORK_APP" -type l | while read -r link; do
    target=$(readlink "$link")
    dir=$(dirname "$link")
    [[ "$target" == /* ]] && resolved="$target" || resolved="$dir/$target"
    # `|| true`: this is the loop body's last command, so under set -e a
    # symlink that's simply fine (test is false, nothing to remove) must not
    # be allowed to end the loop iteration on a nonzero status.
    [ ! -e "$resolved" ] && rm -f "$link" || true
done
echo "Copy and cleanup done."

echo ""
echo "=== Step 3: Sign (leaves → frameworks → app) ==="

# 3a. All dylibs and .so extension modules
find "$WORK_APP" -type f \( -name "*.dylib" -o -name "*.so" \) | while read f; do
    sign_file "$f"
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
            sign_file "$f"
        fi
    done
done
echo "  3b: PySide6 plain executables signed"

# 3c. Python.framework: binary first, then the framework bundle
sign_file "$WORK_APP/Contents/Frameworks/Python.framework/Versions/3.14/Python"
sign_file "$WORK_APP/Contents/Frameworks/Python.framework"
echo "  3c: Python.framework signed"

# 3d. QtWebEngineCore: sign the binary and its nested QtWebEngineProcess.app before
# signing the whole framework (the nested app must be signed as a unit)
QTWE="$WORK_APP/Contents/Frameworks/PySide6/Qt/lib/QtWebEngineCore.framework"
sign_file "$QTWE/Versions/A/QtWebEngineCore"
sign_file "$QTWE/Versions/A/Helpers/QtWebEngineProcess.app"
echo "  3d: QtWebEngineCore binary and nested app signed"

# 3e. All Qt .framework bundles (sort by path length descending = deepest first)
find "$WORK_APP/Contents/Frameworks" -name "*.framework" \
    -not -path "*/Python.framework*" | \
    awk '{ print length, $0 }' | sort -rn | awk '{print $2}' | while read f; do
    sign_file "$f"
done
echo "  3e: Qt frameworks signed"

# 3f. Main app bundle (signs and seals everything including the main executable)
sign_file "$WORK_APP"
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
# Let macOS pick the mount point so the script works even if an older DMG is still mounted.
ATTACH_OUT=$(hdiutil attach "$WORK_RW_DMG" -readwrite -noverify)
echo "$ATTACH_OUT"
# Pick the entry that actually carries a mount point, preferring our own volume.
# NOT `tail -1 | cut -f3-`: when other disk images are attached, hdiutil lists
# their partitions too, and the last line can be a scheme/container row with no
# mount point at all — which silently yielded an EMPTY mount point and turned
# the cleanup lines below into operations on "/".
MOUNT_POINT=$(echo "$ATTACH_OUT" | sed -n "s|.*\(/Volumes/${DMG_NAME}.*\)$|\1|p" | tail -1)
if [ -z "$MOUNT_POINT" ]; then
    MOUNT_POINT=$(echo "$ATTACH_OUT" | sed -n 's|.*\(/Volumes/.*\)$|\1|p' | tail -1)
fi
if [ -z "$MOUNT_POINT" ] || [ ! -d "$MOUNT_POINT" ]; then
    echo "ERROR: could not determine the DMG mount point from hdiutil output."
    echo "Refusing to continue — the steps below would operate on '/'."
    exit 1
fi
DISK_DISPLAY=$(basename "$MOUNT_POINT")
echo "Mounted at: $MOUNT_POINT  (Finder name: $DISK_DISPLAY)"

sleep 5   # give Finder time to register the volume and render the app icon
# Hide .background on the mounted APFS volume (chflags on staging is not preserved)
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
# Remove .fseventsd created by macOS when mounting the APFS volume
rm -rf "${MOUNT_POINT}/.fseventsd"
sync
hdiutil detach "$MOUNT_POINT"   # detach by actual mount point, not hardcoded name
rm -rf "$DMG_STAGING"

hdiutil convert "$WORK_RW_DMG" -format UDZO -imagekey zlib-level=9 -o "$WORK_DMG"
rm "$WORK_RW_DMG"
echo "DMG created."

echo ""
echo "=== Step 10: Sign DMG ==="
codesign_retry "$WORK_DMG"
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
echo "=== Step 14: Update web/download.html ==="
DOWNLOAD_HTML="web/download.html"
OLD_VERSION=$(grep -o 'download/v[0-9][0-9]*\.[0-9][0-9]*/Yearbirder_v' "$DOWNLOAD_HTML" | grep -o '[0-9][0-9]*\.[0-9][0-9]*' | head -1)
RELEASE_MONTH_YEAR=$(echo "$VERSION_DATE" | awk '{print $1, $3}')
if [ -z "$OLD_VERSION" ]; then
    echo "WARNING: Could not detect old version in $DOWNLOAD_HTML — skipping."
else
    OLD_V="$OLD_VERSION" NEW_V="$VERSION" NEW_DATE="$RELEASE_MONTH_YEAR" \
    venv/bin/python3 - <<'PYEOF'
import os, re
html_path = "web/download.html"
old_v    = os.environ["OLD_V"]
new_v    = os.environ["NEW_V"]
new_date = os.environ["NEW_DATE"]
with open(html_path) as f:
    content = f.read()
content = content.replace(f"v{old_v}/Yearbirder_v{old_v}.dmg",  f"v{new_v}/Yearbirder_v{new_v}.dmg")
content = content.replace(f"Yearbirder_v{old_v}.dmg",           f"Yearbirder_v{new_v}.dmg")
content = content.replace(f"refs/tags/v{old_v}.zip",            f"refs/tags/v{new_v}.zip")
content = re.sub(
    rf'v{re.escape(old_v)} &nbsp;·&nbsp; \S+ \d+',
    f'v{new_v} &nbsp;·&nbsp; {new_date}',
    content
)
with open(html_path, "w") as f:
    f.write(content)
print(f"  {html_path}: v{old_v} → v{new_v}, date → {new_date}")
PYEOF
fi

echo ""
echo "=== All done! ==="
echo ""
echo "=============================================================="
echo " Remaining release steps for v${VERSION}"
echo "=============================================================="
echo ""
echo " 6. Test dist/Yearbirder_v${VERSION}.dmg yourself — install it and"
echo "    check About Yearbirder reports v${VERSION} (${VERSION_DATE})."
echo "    Any fix from here means re-running this script from the top."
echo ""
echo " 7. Commit and push a release/v${VERSION} branch."
echo "    NOTE: Step 14 above just edited web/download.html — include it."
echo "    Pushing release/** starts the Windows CI build."
echo ""
echo " 8. When CI finishes, download the Yearbirder-Windows-Setup artifact"
echo "    and test the installer on the Windows VM."
echo ""
echo " 9. Update README.md for v${VERSION} and commit to the branch."
echo ""
echo "10. Upload the new Yearbirder_Setup.exe to Cloudflare R2 — BEFORE the"
echo "    merge, not after."
echo "    https://dash.cloudflare.com -> R2 -> yearbirder-downloads -> Upload"
echo "    (replaces downloads.yearbirder.org/Yearbirder_Setup.exe)"
echo "    R2 serves one fixed URL, so the file and the page it is advertised"
echo "    on go stale independently.  Uploading first means the page still"
echo "    says v${PREV_VERSION:-previous} while the newer exe is already"
echo "    served; merging first means the page promises v${VERSION} and hands"
echo "    out the old build.  The first is untidy, the second ships the wrong"
echo "    app to anyone downloading in the gap."
echo ""
echo "11. Merge release/v${VERSION} to master (this takes the website live)."
echo ""
echo "12. Immediately create tag v${VERSION} and a GitHub release, attaching"
echo "    dist/Yearbirder_v${VERSION}.dmg."
echo "    web/download.html links to"
echo "    .../download/v${VERSION}/Yearbirder_v${VERSION}.dmg — that link 404s"
echo "    from the moment of merge until the release exists, so do not leave"
echo "    a gap between steps 11 and 12."
echo ""
echo "13. Sanity-check yearbirder.org: every page reachable, v${VERSION}"
echo "    everywhere, no stale v${PREV_VERSION:-previous} references, and both"
echo "    download links returning 200."
echo ""
