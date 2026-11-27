@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Python environment not found. Follow the first-run setup in README.md.
    pause
    exit /b 1
)

if not exist ".env" (
    echo .env is missing. Copy .env.example to .env and add your API key first.
    pause
    exit /b 1
)

if not exist "data\olist.db" (
    echo data\olist.db is missing. Follow the Olist data setup in README.md first.
    pause
    exit /b 1
)

powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 1 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    start "" "http://127.0.0.1:8000/"
    exit /b 0
)

start "" powershell -NoProfile -WindowStyle Hidden -Command "$url='http://127.0.0.1:8000/health'; for($i=0; $i -lt 30; $i++){try{Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 1 | Out-Null; Start-Process 'http://127.0.0.1:8000/'; exit}catch{Start-Sleep -Seconds 1}}"
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload
pause
