#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
ARCH="$(uname -m)"
OUT="${1:-release}"
mkdir -p "$OUT"
python3 -m PyInstaller --noconfirm packaging/app.spec
APP="dist/百家观测.app"
"$APP/Contents/MacOS/BaijiaObservatory" --smoke-test
codesign --force --deep --sign - "$APP"
pkgbuild --component "$APP" --install-location /Applications --identifier com.baijia.observatory --version 1.1.0 "$OUT/BaijiaObservatory-1.1.0-macOS-$ARCH.pkg"
if [[ "${CI:-}" == "true" ]]; then
    sudo installer -pkg "$OUT/BaijiaObservatory-1.1.0-macOS-$ARCH.pkg" -target /
    "/Applications/百家观测.app/Contents/MacOS/BaijiaObservatory" --smoke-test
    python3 - <<'PY'
import json
from pathlib import Path
report = Path.home() / 'Library/Application Support/BaijiaObservatory/smoke-test.json'
assert json.loads(report.read_text())['status'] == 'ok'
assert Path('/Applications/百家观测.app/Contents/Resources/studio/manual.pdf').is_file()
print('Installed application backend and bundled manual verified.')
PY
fi
