@echo off
title ATF - Playwright Browser Studio - Test Recorder
cd /d "%~dp0"

echo ====================================================================
echo   ATF Playwright Interactive Browser Studio
echo ====================================================================
echo.
echo [1/2] Checking backend server on http://127.0.0.1:8000...

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Please run start.bat first.
    pause
    exit /b 1
)

:: Test if backend is already responding
.\.venv\Scripts\python.exe scripts\wait_for_server.py http://127.0.0.1:8000/health 1 >nul 2>&1
if %errorlevel% neq 0 (
    echo Starting backend server in a background window...
    start "ATF Backend Server" /D "%~dp0" "%~dp0.venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000
    echo Waiting for backend server to become ready...
    .\.venv\Scripts\python.exe scripts\wait_for_server.py http://127.0.0.1:8000/health 15
    if %errorlevel% neq 0 (
        echo [ERROR] Backend server failed to start within 15 seconds.
        pause
        exit /b 1
    )
) else (
    echo [OK] Backend server is already running and ready!
)

echo.
echo [2/2] Launching Playwright Browser and Inspector...
echo   - Perform any actions on the dashboard (click demo, upload, switch tabs)
echo   - Playwright records your exact actions and generates test code live!
echo   - Recorded test will be saved to: tests\e2e\test_recorded.py
echo.

.\.venv\Scripts\playwright.exe codegen http://127.0.0.1:8000 --target python-pytest -o tests\e2e\test_recorded.py

echo.
echo ====================================================================
echo   Session ended.
if exist "tests\e2e\test_recorded.py" (
    echo   Your recorded test is saved in: tests\e2e\test_recorded.py
    echo   Run it anytime using: start_e2e.bat
)
echo ====================================================================
pause
