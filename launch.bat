@echo off
:: Tapo Camera Viewer Launcher
:: Uses the local venv — no system Python required

set SCRIPT_DIR=%~dp0
set VENV_PYTHON=%SCRIPT_DIR%venv\Scripts\pythonw.exe
set MAIN=%SCRIPT_DIR%main.py

:: Check if venv exists
if not exist "%VENV_PYTHON%" (
    echo Setting up virtual environment...
    python -m venv "%SCRIPT_DIR%venv"
    if errorlevel 1 (
        echo ERROR: Could not create virtual environment. Make sure Python is installed.
        pause
        exit /b 1
    )
)

:: Check if packages are installed (PyQt6 as indicator)
"%VENV_PYTHON%" -c "import PyQt6" 2>nul
if errorlevel 1 (
    echo Installing required packages...
    "%SCRIPT_DIR%venv\Scripts\pip.exe" install -r "%SCRIPT_DIR%requirements.txt"
    if errorlevel 1 (
        echo ERROR: Failed to install packages.
        pause
        exit /b 1
    )
)

:: Launch the app (pythonw = no console window)
start "" "%VENV_PYTHON%" "%MAIN%"
