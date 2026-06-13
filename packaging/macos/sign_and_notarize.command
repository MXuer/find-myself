#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

APP_NAME="Find Myself"
VERSION="0.2.0"
ARCH="arm64"
APP_PATH="$PROJECT_ROOT/desktop/tauri/src-tauri/target/release/bundle/macos/$APP_NAME.app"
DIST_DIR="$PROJECT_ROOT/dist"
SIGNED_APP_PATH="$DIST_DIR/$APP_NAME.app"
DMG_PATH="$DIST_DIR/${APP_NAME}_${VERSION}_${ARCH}.dmg"

SIGN_IDENTITY="${FIND_MYSELF_APPLE_SIGN_IDENTITY:-}"
NOTARY_PROFILE="${FIND_MYSELF_NOTARY_PROFILE:-}"

if [ -z "$SIGN_IDENTITY" ]; then
  echo "Missing FIND_MYSELF_APPLE_SIGN_IDENTITY"
  echo "Example: export FIND_MYSELF_APPLE_SIGN_IDENTITY='Developer ID Application: Your Name (TEAMID)'"
  exit 1
fi

if [ -z "$NOTARY_PROFILE" ]; then
  echo "Missing FIND_MYSELF_NOTARY_PROFILE"
  echo "Example: export FIND_MYSELF_NOTARY_PROFILE='find-myself-notary'"
  exit 1
fi

if [ ! -d "$APP_PATH" ]; then
  echo "Missing app bundle: $APP_PATH"
  echo "Build first with: env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY npm run tauri:build:dmg"
  exit 1
fi

mkdir -p "$DIST_DIR"
rm -rf "$SIGNED_APP_PATH"
cp -R "$APP_PATH" "$SIGNED_APP_PATH"

echo "Signing app with identity:"
echo "  $SIGN_IDENTITY"

codesign \
  --force \
  --deep \
  --options runtime \
  --timestamp \
  --sign "$SIGN_IDENTITY" \
  "$SIGNED_APP_PATH"

codesign --verify --deep --strict --verbose=2 "$SIGNED_APP_PATH"
spctl --assess --type open --verbose=4 "$SIGNED_APP_PATH" || true

echo "Rebuilding DMG from signed app..."
rm -f "$DMG_PATH"
TMP_STAGE="/tmp/find-myself-dmg-signed"
rm -rf "$TMP_STAGE"
mkdir -p "$TMP_STAGE"
cp -R "$SIGNED_APP_PATH" "$TMP_STAGE"
ln -s /Applications "$TMP_STAGE/Applications"

hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$TMP_STAGE" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo "Submitting DMG for notarization..."
xcrun notarytool submit "$DMG_PATH" \
  --keychain-profile "$NOTARY_PROFILE" \
  --wait

echo "Stapling notarization ticket..."
xcrun stapler staple "$SIGNED_APP_PATH"
xcrun stapler staple "$DMG_PATH"

echo "Final verification..."
codesign --verify --deep --strict --verbose=2 "$SIGNED_APP_PATH"
spctl --assess --type open --verbose=4 "$SIGNED_APP_PATH"
spctl --assess --type open --verbose=4 "$DMG_PATH"

echo
echo "Done:"
echo "  App: $SIGNED_APP_PATH"
echo "  DMG: $DMG_PATH"
