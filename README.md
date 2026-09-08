# SuperCam Thermal Viewer

Cross-platform dual-stream viewer for QuanLi/LangChi SuperCam thermal cameras.
It displays the 160x120 infrared stream alongside the 1920x1080 visible stream,
with calibrated fusion, thermal palettes, hotspot search, temperature cutoffs,
zoom/pan, and persistent camera settings.

![SUPERCAM IR-main interface](docs/images/Screenshot%202026-09-08%20151322.png)

![SUPERCAM VIS-main interface](docs/images/Screenshot%202026-09-08%20151312.png)

## Why This Exists

The supplied PCBTool is useful for validating the camera, but it is a Windows-only
vendor application with limited diagnostics and no practical cross-platform workflow.
SUPERCAM keeps the same live IR/VIS data path while exposing the calibration, fusion,
hotspot, temperature-range, zoom, and pan controls needed for board troubleshooting.
It is intended to complement PCBTool, not replace the vendor SDK or claim ownership of
the camera protocol.

## Features

- IR and VIS live streams from the camera over the native TCP protocol.
- VIS/IR fusion with factory X/Y/zoom/rotation calibration.
- Correct forward and inverse calibration in both VIS-main and IR-main modes.
- Thermal palette, smoothing, adaptive temperature range, and Lo/Hi cutoffs.
- Hotspot search with view-only pan/zoom and reset.
- Windows executable and macOS app packaging.

## Windows Use

The standalone executable is:

```text
tools/supercam_viewer/dist-release-0.1.0/SuperCam.exe
```

It does not require Python, NumPy, OpenCV, PyAV, or the vendor SDK to be
installed. The one-file executable contains the application and its assets.
Windows and the camera network connection are the only runtime requirements.

The first launch may be checked by Windows Defender or the firewall because the
viewer connects to the camera over the local network. Settings are stored in
`%APPDATA%/SuperCamViewer/`.

## Build From Source

Install Python 3.12 or newer and run the viewer directly:

```powershell
python -m pip install -r tools/supercam_viewer/requirements.txt
python tools/supercam_viewer/run.py 192.168.2.32
```

Build Windows:

```powershell
cd tools/supercam_viewer
.\build_windows.ps1
```

Build macOS on macOS:

```sh
cd tools/supercam_viewer
chmod +x build_macos.sh
./build_macos.sh
```

The macOS build creates `dist/SuperCam.app` and
`dist/SuperCam-macOS.zip`. PyAV, OpenCV, Tk, and PyInstaller must be built on
the target operating system; macOS cannot be reliably cross-built on Windows.

## Project Layout

```text
tools/supercam_viewer/       Application source and packaging files
reverse_engineering/         Protocol research, captures, probes, and logs
QuanLi/                      Original vendor files and reference configuration
docs/                        Session and research notes
```

## Protocol Notes

The viewer uses TCP 3001 for control and TCP 3000 for the camera streams. IR
frames are raw 160x120 12-bit samples and the visible stream is H.264 at
1920x1080. Additional protocol findings are documented in
`reverse_engineering/README.md` and the scripts and captures in that directory.

## Reverse Engineering Summary

The camera uses a proprietary TCP/UDP protocol rather than RTSP, ONVIF, or ordinary
HTTP. Research identified UDP discovery on ports 10001/10002, control and stream
connections on TCP 3000/3001, H.264 visible frames at 1920x1080, and radiometric IR
frames at 160x120. The viewer reproduces the live stream path without bundling the
vendor DLLs. The full notes preserve packet layouts, source/session IDs, stream
negotiation, and the remaining device-specific limitations.

## License

No open-source license has been selected yet. Add the intended license before
publishing the repository publicly. Vendor software, DLLs, captures, and
reference files may have separate ownership or redistribution restrictions.
