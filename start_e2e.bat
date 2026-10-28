@echo off
title ATF - Playwright E2E Browser Tests
cd /d "%~dp0"

echo =========================================================
echo   ATF Playwright End-to-End Visual Browser Test Runner
echo =========================================================
echo.
echo Launching automated browser with visual playback...
echo (Watch the Chromium window open and run tests automatically)
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe
    echo Please run .\start.ps1 first to initialize the environment.
    pause
    exit /b 1
)

.\.venv\Scripts\python.exe -m pytest tests/e2e -v --headed --slowmo 700

echo.
echo =========================================================
echo   Tests completed. Press any key to close this window.
echo =========================================================
pause >nul
