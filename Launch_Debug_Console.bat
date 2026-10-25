@echo off
cd /d "%~dp0"
echo ========================================================
echo  Launching Blinkit Stock Tracker Pro (Debug Console)
echo ========================================================
echo.
python app.py
if %errorlevel% neq 0 (
    echo.
    echo Application exited with code: %errorlevel%
)
pause
