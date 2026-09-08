$ErrorActionPreference = 'Stop'
python -m pip install -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m PyInstaller --clean --noconfirm --workpath build-final-ui --distpath dist-final-ui SuperCam.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Windows build: dist-final-ui\SuperCam.exe"
