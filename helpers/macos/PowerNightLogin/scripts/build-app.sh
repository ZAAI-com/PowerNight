#!/usr/bin/env bash
# Build "PowerNight Login.app" for local testing (ad-hoc signed, not notarized).
# Usage: scripts/build-app.sh [--universal]
set -euo pipefail
cd "$(dirname "$0")/.."

ARCH_FLAGS=()
if [[ "${1:-}" == "--universal" ]]; then
  ARCH_FLAGS=(--arch arm64 --arch x86_64)
fi

swift build -c release --product PowerNightLogin "${ARCH_FLAGS[@]+"${ARCH_FLAGS[@]}"}"
BIN_DIR="$(swift build -c release --show-bin-path "${ARCH_FLAGS[@]+"${ARCH_FLAGS[@]}"}")"

APP="build/PowerNight Login.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN_DIR/PowerNightLogin" "$APP/Contents/MacOS/PowerNightLogin"
cp Resources/Info.plist "$APP/Contents/Info.plist"
plutil -lint "$APP/Contents/Info.plist" >/dev/null

# Ad-hoc signature for local use only; distribution needs Developer ID
# signing and notarization
codesign --force --sign - "$APP"

# Register the powernight-login:// link handler with Launch Services
LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
if [[ -x "$LSREGISTER" ]]; then
  "$LSREGISTER" -f "$APP"
fi

echo "Built $(pwd)/$APP"
echo "Move it to /Applications (optional) and open it once with right-click > Open."
