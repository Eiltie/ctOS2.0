@echo off
setlocal
set PYTHONIOENCODING=utf-8
chcp 65001 >nul
cd /d "%~dp0.."

if not exist "venv\Scripts\python.exe" (
    echo [x] venv\Scripts\python.exe not found. Run: python -m venv venv
    pause
    exit /b 1
)

powershell -NoProfile -Command "if (-not (Test-NetConnection -ComputerName 127.0.0.1 -Port 5433 -InformationLevel Quiet -WarningAction SilentlyContinue)) { exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo [x] Cannot reach 127.0.0.1:5433 - Docker database is not running.
    echo     Start it: docker compose --env-file config\.env up -d
    pause
    exit /b 1
)

"venv\Scripts\python.exe" -X utf8 -m databases.tools.clean --docker
pause