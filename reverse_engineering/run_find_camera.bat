@echo off
REM Find QuanLi/LangChi SuperCam thermal camera and test TCP/3000.
REM Run from native Windows (double-click). NOT from WSL.
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
    python find_camera.py --scan
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        py find_camera.py --scan
    ) else (
        echo Python not found. Install python from https://www.python.org/downloads/
        pause
    )
)
pause
