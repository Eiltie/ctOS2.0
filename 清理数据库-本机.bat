@echo off
set PYTHONIOENCODING=gbk
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Cannot find venv\Scripts\python.exe
    echo Please create the venv first.
    pause
    exit /b 1
)

echo Local database (port 5432)
echo.
"venv\Scripts\python.exe" -m databases.clean_db
echo.
pause
