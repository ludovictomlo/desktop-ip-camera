"""
TP-Link Tapo C220 Camera Viewer & Recorder

A desktop application for viewing the live RTSP feed from a Tapo C220
camera, with motion-triggered loop recording and automatic storage management.

Usage:
    python main.py
"""

import sys
import os
import logging
from datetime import datetime

# Set up logging before anything else
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging():
    """Configure logging to console and file."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root_logger.addHandler(console)

    # File handler
    log_dir = os.path.dirname(__file__)
    log_file = os.path.join(log_dir, "app.log")
    try:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        root_logger.addHandler(file_handler)
    except Exception:
        pass  # Don't fail if we can't write log file


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Tapo C220 Camera Viewer & Recorder")
    logger.info("Starting at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 60)

    # Import after logging setup
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont
    from app.config import load_config
    from app.gui import MainWindow

    # Load configuration
    config = load_config()
    logger.info("Configuration loaded")

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Tapo C220 Viewer")
    app.setStyle("Fusion")

    # Apply dark theme
    app.setStyleSheet(DARK_THEME)

    # Create and show main window
    window = MainWindow(config)
    window.show()

    logger.info("Application ready")
    sys.exit(app.exec())


DARK_THEME = """
    QMainWindow {
        background-color: #1e1e2e;
    }
    QWidget {
        background-color: #1e1e2e;
        color: #cdd6f4;
        font-size: 12px;
    }
    QGroupBox {
        font-weight: bold;
        border: 1px solid #45475a;
        border-radius: 6px;
        margin-top: 8px;
        padding-top: 16px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 6px;
        color: #89b4fa;
    }
    QPushButton {
        background-color: #313244;
        border: 1px solid #45475a;
        border-radius: 6px;
        padding: 6px 14px;
        color: #cdd6f4;
    }
    QPushButton:hover {
        background-color: #45475a;
        border-color: #89b4fa;
    }
    QPushButton:pressed {
        background-color: #585b70;
    }
    QPushButton:checked {
        background-color: #cc3333;
        color: white;
    }
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
        background-color: #313244;
        border: 1px solid #45475a;
        border-radius: 4px;
        padding: 4px 8px;
        color: #cdd6f4;
    }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
        border-color: #89b4fa;
    }
    QSlider::groove:horizontal {
        height: 6px;
        background: #45475a;
        border-radius: 3px;
    }
    QSlider::handle:horizontal {
        background: #89b4fa;
        width: 16px;
        height: 16px;
        margin: -5px 0;
        border-radius: 8px;
    }
    QTabWidget::pane {
        border: 1px solid #45475a;
        border-radius: 6px;
    }
    QTabBar::tab {
        background: #313244;
        border: 1px solid #45475a;
        border-bottom: none;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        padding: 6px 16px;
        color: #a6adc8;
    }
    QTabBar::tab:selected {
        background: #1e1e2e;
        color: #89b4fa;
    }
    QTableWidget {
        background-color: #181825;
        border: 1px solid #45475a;
        border-radius: 4px;
        gridline-color: #313244;
    }
    QTableWidget::item {
        padding: 4px;
    }
    QTableWidget::item:selected {
        background-color: #45475a;
    }
    QHeaderView::section {
        background-color: #313244;
        border: 1px solid #45475a;
        padding: 4px;
        font-weight: bold;
    }
    QProgressBar {
        background-color: #313244;
        border: 1px solid #45475a;
        border-radius: 4px;
        text-align: center;
        color: #cdd6f4;
    }
    QProgressBar::chunk {
        background-color: #44bb44;
        border-radius: 3px;
    }
    QStatusBar {
        background-color: #181825;
        border-top: 1px solid #313244;
    }
    QMessageBox {
        background-color: #1e1e2e;
    }
    QScrollBar:vertical {
        background: #181825;
        width: 10px;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical {
        background: #45475a;
        border-radius: 5px;
        min-height: 20px;
    }
"""

if __name__ == "__main__":
    main()
