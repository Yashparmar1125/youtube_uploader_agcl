@echo off
chcp 65001 > nul
title Pravachan YouTube Uploader

echo ========================================================
echo        PRAVACHAN AUTOMATED YOUTUBE UPLOADER
echo ========================================================
echo.

if not exist client_secret.json (
    echo [WARNING] 'client_secret.json' was not found!
    echo Please download your OAuth client credentials from Google Cloud Console
    echo and place 'client_secret.json' in this folder.
    echo See SETUP_GUIDE.md for step-by-step instructions.
    echo.
    pause
    exit /b 1
)

echo Select run mode:
echo   1. Run scan once (upload pending files and exit)
echo   2. Run continuous monitor (checks every 10 minutes)
echo   3. Dry-run test (simulates scan without uploading)
echo.
set /p choice="Enter choice [1-3] (Default: 1): "

if "%choice%"=="2" (
    echo Starting continuous monitor...
    python uploader.py --loop --interval 10
) else if "%choice%"=="3" (
    echo Running dry-run scan...
    python uploader.py --dry-run
    pause
) else (
    echo Running single scan and upload...
    python uploader.py --run-once
    pause
)
