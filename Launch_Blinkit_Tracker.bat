@echo off
setlocal
cd /d "%~dp0"

:: Try running silently with pyw or pythonw
where pyw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pyw app.py
    exit /b
)

where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw app.py
    exit /b
)

:: Fallback to standard python
python app.py
if %errorlevel% neq 0 (
    echo.
    echo Application failed to start.
    pause
)
