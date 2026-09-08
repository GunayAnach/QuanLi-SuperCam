#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install -r requirements.txt pyinstaller
python3 -m PyInstaller --clean --noconfirm SuperCam.spec
ditto -c -k --sequesterRsrc --keepParent dist/SuperCam.app dist/SuperCam-macOS.zip
echo "macOS app: dist/SuperCam.app"
echo "macOS archive: dist/SuperCam-macOS.zip"
