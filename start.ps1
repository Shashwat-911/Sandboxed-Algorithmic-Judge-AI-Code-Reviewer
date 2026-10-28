$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
}
& .venv/Scripts/python.exe -c "import importlib.util,sys; sys.exit(not all(importlib.util.find_spec(m) for m in ['fastapi','uvicorn','multipart','httpx','docker','reportlab','playwright']))"
if ($LASTEXITCODE -ne 0) {
    & .venv/Scripts/python.exe -m pip install -r requirements-demo.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
& .venv/Scripts/python.exe -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw 'Playwright Chromium installation failed.' }
Write-Host 'ATF dashboard: http://127.0.0.1:8000 (Ctrl+C to stop)'
& .venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
