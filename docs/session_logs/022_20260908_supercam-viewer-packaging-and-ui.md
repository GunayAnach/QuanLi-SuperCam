# SuperCam Viewer Packaging and UI Session

Session identifier preserved from the former root `session.md`:

```text
opencode -s ses_f97758fafffePy2s24hvBq1naz
```

## Work Completed

- Implemented the cross-platform SuperCam dual-stream viewer with IR/VIS fusion.
- Added calibrated VIS/IR alignment, shared 4:3 reference geometry, crop zoom,
  hotspot search, zoom/pan, temperature controls, and persistent settings.
- Added responsive banner placement, transparent branding assets, Windows ICO,
  macOS ICNS, title-bar icon, and packaged asset handling.
- Added keyboard shortcuts, shortcut help dialog, IT-Solve credits, mouse-wheel
  zoom, mouse drag panning, and rotating footer hints.
- Added PyInstaller packaging for Windows and macOS build instructions.
- Organized research artifacts under `reverse_engineering/` and retained only
  the application under `tools/supercam_viewer/`.
- Added root GitHub README and `.gitignore`.

## Current Build

The latest Windows one-file executable is:

```text
tools/supercam_viewer/dist-footer/SuperCam.exe
```

The executable was smoke-tested after packaging. A native macOS build still
needs to be run on macOS.

## Repository

https://github.com/GunayAnach/QuanLi-SuperCam
