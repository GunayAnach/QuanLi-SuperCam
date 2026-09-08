# SUPERCAM Thermal Viewer (cross-platform)

Lightweight Python replacement for the vendor app. Shows the QuanLi/LangChi
"SuperCam" IR camera (PCBQDIRCam) as a **side-by-side dual stream**:
**LEFT = IR thermal**, **RIGHT = visible camera**. Works on Windows and macOS.

## Install

```sh
python -m pip install -r requirements.txt   # numpy, opencv-python, av (PyAV), Pillow
```

## Run

```sh
python run.py                 # uses remembered IP
python run.py 192.168.2.32    # or override
```

In the window: type the camera IP, press **Connect**. Settings (IP, IR palette
inferno/jet/gray, smooth upscale) are saved automatically and remembered on
next start.

- `%APPDATA%/SuperCamViewer/settings.json`  (Windows)
- `~/Library/Application Support/SuperCamViewer/settings.json`  (macOS)

## Protocol (verified against vendor captures)

- TCP **3001** control: 0x65/0x66/0x10066 negotiation, 0x78 CONFIG binding,
  login + keepalive. TCP **3000**: CLEANALARM + video streams.
- The client RAW-hunts: probe chan4 on fresh session ids with CONFIG `extra1=1`
  (codec selector -> RAW thermal), then binds chan2 `extra1=0` (-> H.264 VIS).
  CA channel byte `@0x24` = engine select (1 = IR, 0 = VIS). One probe per sid —
  re-configuring a sid wedges the camera (power-cycle to recover).
- IR frames: fixed 39448 B, `LAUNCHDIGITAL` + `RAW\0` header, 160x120 u16-LE
  12-bit samples. VIS: H.264 elementary stream, 1920x1080.
- Full story: `../../reverse_engineering_NOTES.md` (Addenda 6-7).

## Self-test (no GUI)

```sh
python -c "import supercam.camera as c; print('ok')"   # imports
python cam_selftest.py 192.168.2.32   # 8s headless dual-stream soak
```

## Packaging

Windows PowerShell:

```powershell
.\build_windows.ps1
```

macOS Terminal:

```sh
chmod +x build_macos.sh
./build_macos.sh
```

The Windows output is `dist-final-ui/SuperCam.exe`. Build the macOS app on macOS; PyAV,
OpenCV, Tk, and PyInstaller bundles are platform-specific and cannot be
cross-built reliably from Windows.

## Layout

```
run.py                 entrypoint
supercam/__init__.py
supercam/proto.py      byte-exact wire builders
supercam/camera.py     threaded dual-stream client
supercam/decoders.py   IR framer + PyAV H.264 decoder
supercam/render.py     palette + upscale + composite
supercam/gui.py        tkinter UI
supercam/settings.py   persisted JSON settings
```
