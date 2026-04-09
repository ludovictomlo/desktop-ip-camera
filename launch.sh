#!/usr/bin/env bash
# Tapo Camera Viewer Launcher
# Uses a local venv — no system Python required

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
MAIN="$SCRIPT_DIR/main.py"

# Check if venv exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Setting up virtual environment..."
    python3 -m venv "$SCRIPT_DIR/venv"
    if [ $? -ne 0 ]; then
        echo "ERROR: Could not create virtual environment. Make sure Python 3 is installed."
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

# Check if packages are installed (PyQt6 as indicator)
"$VENV_PYTHON" -c "import PyQt6" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installing required packages..."
    "$SCRIPT_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install packages."
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

# Launch the app
exec "$VENV_PYTHON" "$MAIN" "$@"
