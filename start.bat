@echo off
title ATF - Backend and Web Dashboard
cd /d "%~dp0"

echo ========================================================
echo   Starting ATF Backend Server and Launching Dashboard
echo ========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe.
    pause
    exit /b 1
)

echo [1/2] Waiting for backend to start, then opening browser...
start "" /D "%~dp0" cmd /c ".\.venv\Scripts\python.exe scripts\wait_for_server.py http://127.0.0.1:8000/health 20 && start http://127.0.0.1:8000"

echo [2/2] Starting uvicorn backend server...
echo (Press Ctrl+C to stop the server)
echo.

.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
