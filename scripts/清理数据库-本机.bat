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

"venv\Scripts\python.exe" -X utf8 -m databases.tools.clean
pause