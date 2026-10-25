@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ========================================================
echo     Building Blinkit Stock Tracker Pro Standalone EXE
echo ========================================================
echo.

:: 1. Verify / Install PyInstaller
python -m pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [1/3] Installing PyInstaller...
    python -m pip install pyinstaller
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install PyInstaller.
        pause
        exit /b 1
    )
) else (
    echo [1/3] PyInstaller verified.
)

:: 2. Clean previous build artifacts
echo [2/3] Cleaning previous build folders...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

:: 3. Run PyInstaller
echo [3/3] Compiling standalone executable...
echo       (This may take 1-2 minutes, please wait...)

python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --onefile ^
    --name "Blinkit Stock Tracker" ^
    --collect-all customtkinter ^
    app.py

if %errorlevel% neq 0 (
    echo.
    echo ========================================================
    echo  [BUILD FAILED] An error occurred during compilation.
    echo ========================================================
    pause
    exit /b %errorlevel%
)

echo.
echo ========================================================
echo  [BUILD SUCCESSFUL] Standalone EXE created!
echo ========================================================
echo.
echo Your executable is located at:
echo  %~dp0dist\Blinkit Stock Tracker.exe
echo.
echo You can distribute this .exe directly or upload it to
echo your GitHub Releases page.
echo.
pause
