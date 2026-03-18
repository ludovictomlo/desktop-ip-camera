@echo off
:: Build standalone TapoViewer.exe using PyInstaller
set SCRIPT_DIR=%~dp0
set VENV_PYTHON=%SCRIPT_DIR%venv\Scripts\python.exe

echo =============================================
echo  Tapo Viewer - Build Executable
echo =============================================

:: Ensure venv and packages exist
if not exist "%VENV_PYTHON%" (
    echo Creating virtual environment...
    python -m venv "%SCRIPT_DIR%venv"
)

"%VENV_PYTHON%" -c "import PyQt6" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    "%SCRIPT_DIR%venv\Scripts\pip.exe" install -r "%SCRIPT_DIR%requirements.txt"
)

"%VENV_PYTHON%" -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo Installing PyInstaller...
    "%SCRIPT_DIR%venv\Scripts\pip.exe" install pyinstaller
)

echo.
echo Building executable...
"%SCRIPT_DIR%venv\Scripts\pyinstaller.exe" "%SCRIPT_DIR%tapo_viewer.spec" --clean

if errorlevel 1 (
    echo.
    echo ERROR: Build failed.
    pause
    exit /b 1
)

echo.
echo =============================================
echo  Build complete!
echo  Output: dist\TapoViewer\TapoViewer.exe
echo =============================================
pause
