import sys

# PyInstaller build description for Windows and macOS.
from PyInstaller.utils.hooks import collect_all


av_datas, av_binaries, av_hidden = collect_all('av')
cv_datas, cv_binaries, cv_hidden = collect_all('cv2')

hiddenimports = av_hidden + cv_hidden

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=av_binaries + cv_binaries,
    datas=av_datas + cv_datas + [('supercam/assets', 'assets')],
    hiddenimports=hiddenimports,
    excludes=['matplotlib', 'PyQt5', 'PySide6'],
    noarchive=False,
)

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SuperCam',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='supercam/assets/icon.ico' if sys.platform == 'win32' else None,
)

if sys.platform == 'darwin':
    app = BUNDLE(exe, name='SuperCam.app', icon='supercam/assets/icon.icns',
                 bundle_identifier='com.supercam.viewer')
