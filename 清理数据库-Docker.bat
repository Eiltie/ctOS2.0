@echo off
set PYTHONIOENCODING=gbk
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Cannot find venv\Scripts\python.exe
    echo Please create the venv first.
    pause
    exit /b 1
)

echo Docker database (port 5433, used by 8080)
echo.
"venv\Scripts\python.exe" -m databases.clean_db --docker
echo.
pause
