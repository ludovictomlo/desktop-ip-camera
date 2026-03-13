"""
Main GUI application for TP-Link Tapo C220 Camera Viewer & Recorder.

Features:
- Live camera feed with motion detection overlay
- Start/stop detection and recording controls
- Settings panel for camera, detection, and storage configuration
- Recordings list with playback
- Storage usage indicator
"""

import sys
import os
import cv2
import logging
import subprocess
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QGroupBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QSlider,
    QComboBox,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QSplitter,
    QStatusBar,
    QProgressBar,
    QMessageBox,
    QTabWidget,
    QFrame,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QIcon, QAction

from app.camera import CameraStream, CameraConfig
from app.detection import MotionDetector
from app.recorder import RecordingManager
from app.storage import StorageManager
from app.config import load_config, save_config
from app.video_widget import ZoomableVideoWidget
from app.zone_dialog import ZoneEditorDialog

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""

    # Signal emitted from background threads to update UI
    motion_started = pyqtSignal(list)   # list of triggered zone names
    motion_ended = pyqtSignal()

    def __init__(self, config: dict):
        super().__init__()
        self.config = config

        self.setWindowTitle("Tapo C220 - Camera Viewer & Recorder")
        self.setMinimumSize(1100, 700)

        # Initialize components
        self._init_camera()
        self._init_detector()
        self._init_recorder()
        self._init_storage()

        # Build UI
        self._build_ui()

        # Timers
        self._frame_timer = QTimer()
        self._frame_timer.timeout.connect(self._update_frame)

        self._stats_timer = QTimer()
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start(2000)

        # Connect signals
        self.motion_started.connect(self._on_motion_started_ui)
        self.motion_ended.connect(self._on_motion_ended_ui)

        # State
        self._show_detection_overlay = True
        self._is_connected = False
        self._frame_counter = 0  # For skipping detection frames

    # ── Initialization ──────────────────────────────────────────────

    def _init_camera(self):
        cam_cfg = self.config["camera"]
        self._cam_config = CameraConfig(
            ip=cam_cfg["ip"],
            username=cam_cfg["username"],
            password=cam_cfg["password"],
            rtsp_port=cam_cfg["rtsp_port"],
            stream_path=cam_cfg["stream_path"],
        )
        self._camera = CameraStream(self._cam_config)

    def _init_detector(self):
        det_cfg = self.config["detection"]
        self._detector = MotionDetector(
            sensitivity=det_cfg["sensitivity"],
            min_area=det_cfg["min_area"],
            cooldown_seconds=det_cfg["cooldown_seconds"],
            detection_scale=0.5,
        )
        self._detector.enabled = det_cfg["enabled"]
        self._detector.set_callbacks(
            on_motion_start=self._on_motion_start,
            on_motion_end=self._on_motion_end,
        )
        # Load saved detection zones
        zones = det_cfg.get("zones", [])
        if zones:
            self._detector.set_zones(zones)

    def _init_recorder(self):
        rec_cfg = self.config["recording"]
        self._recorder = RecordingManager(
            output_folder=rec_cfg["output_folder"],
            fps=rec_cfg["fps"],
            segment_duration=rec_cfg["segment_duration_seconds"],
            pre_record_seconds=rec_cfg["pre_record_seconds"],
            post_record_seconds=rec_cfg["post_record_seconds"],
            video_format=rec_cfg["video_format"],
        )

    def _init_storage(self):
        rec_cfg = self.config["recording"]
        self._storage = StorageManager(
            recordings_folder=rec_cfg["output_folder"],
            max_storage_mb=rec_cfg["max_storage_mb"],
        )

    # ── Motion callbacks (called from background thread) ────────────

    def _on_motion_start(self, zone_names: list[str]):
        zone_label = ', '.join(zone_names) if zone_names else ''
        self._recorder.start_recording(zone_label=zone_label)
        self.motion_started.emit(zone_names)

    def _on_motion_end(self):
        self._recorder.stop_recording()
        self.motion_ended.emit()

    def _on_motion_started_ui(self, zone_names: list[str]):
        if zone_names:
            label = ', '.join(zone_names)
            self._status_motion.setText(f"  ● MOTION: {label}")
        else:
            self._status_motion.setText("  ● MOTION")
        self._status_motion.setStyleSheet(
            "color: #ff4444; font-weight: bold; font-size: 13px;"
        )

    def _on_motion_ended_ui(self):
        self._status_motion.setText("  ○ No Motion")
        self._status_motion.setStyleSheet("color: #888; font-size: 13px;")
        # Refresh recordings list
        self._refresh_recordings()

    # ── UI Construction ─────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # LEFT: Live feed + controls
        left_panel = QVBoxLayout()

        # Camera feed (zoomable)
        self._video_widget = ZoomableVideoWidget()
        left_panel.addWidget(self._video_widget, stretch=1)

        # Controls row
        controls = QHBoxLayout()

        self._btn_connect = QPushButton("Connect")
        self._btn_connect.setMinimumHeight(36)
        self._btn_connect.clicked.connect(self._toggle_connection)
        controls.addWidget(self._btn_connect)

        self._btn_detection = QPushButton("Detection: ON")
        self._btn_detection.setMinimumHeight(36)
        self._btn_detection.clicked.connect(self._toggle_detection)
        controls.addWidget(self._btn_detection)

        self._btn_overlay = QPushButton("Overlay: ON")
        self._btn_overlay.setMinimumHeight(36)
        self._btn_overlay.clicked.connect(self._toggle_overlay)
        controls.addWidget(self._btn_overlay)

        self._btn_snapshot = QPushButton("Snapshot")
        self._btn_snapshot.setMinimumHeight(36)
        self._btn_snapshot.clicked.connect(self._take_snapshot)
        controls.addWidget(self._btn_snapshot)

        self._btn_manual_record = QPushButton("Manual Record")
        self._btn_manual_record.setMinimumHeight(36)
        self._btn_manual_record.setCheckable(True)
        self._btn_manual_record.clicked.connect(self._toggle_manual_record)
        controls.addWidget(self._btn_manual_record)

        left_panel.addLayout(controls)
        main_layout.addLayout(left_panel, stretch=3)

        # RIGHT: Tabs for Settings / Recordings / Detection Zones
        right_panel = QTabWidget()
        right_panel.setMinimumWidth(340)
        right_panel.setMaximumWidth(420)

        right_panel.addTab(self._build_settings_tab(), "Settings")
        right_panel.addTab(self._build_recordings_tab(), "Recordings")
        right_panel.addTab(self._build_zones_tab(), "Zones")

        main_layout.addWidget(right_panel, stretch=1)

        # Status bar
        self._build_status_bar()

    def _build_settings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)

        # ── Camera settings ──
        cam_group = QGroupBox("Camera Connection")
        cam_form = QFormLayout()

        self._input_ip = QLineEdit(self.config["camera"]["ip"])
        self._input_ip.setPlaceholderText("192.168.1.100")
        cam_form.addRow("IP Address:", self._input_ip)

        self._input_port = QSpinBox()
        self._input_port.setRange(1, 65535)
        self._input_port.setValue(self.config["camera"]["rtsp_port"])
        cam_form.addRow("RTSP Port:", self._input_port)

        self._input_user = QLineEdit(self.config["camera"]["username"])
        cam_form.addRow("Username:", self._input_user)

        self._input_pass = QLineEdit(self.config["camera"]["password"])
        self._input_pass.setEchoMode(QLineEdit.EchoMode.Password)
        cam_form.addRow("Password:", self._input_pass)

        self._input_stream = QComboBox()
        self._input_stream.addItems(["/stream1", "/stream2"])
        idx = self._input_stream.findText(self.config["camera"]["stream_path"])
        if idx >= 0:
            self._input_stream.setCurrentIndex(idx)
        cam_form.addRow("Stream:", self._input_stream)

        cam_group.setLayout(cam_form)
        layout.addWidget(cam_group)

        # ── Detection settings ──
        det_group = QGroupBox("Motion Detection")
        det_form = QFormLayout()

        self._input_sensitivity = QSlider(Qt.Orientation.Horizontal)
        self._input_sensitivity.setRange(1, 100)
        self._input_sensitivity.setValue(self.config["detection"]["sensitivity"])
        self._lbl_sensitivity = QLabel(str(self.config["detection"]["sensitivity"]))
        self._input_sensitivity.valueChanged.connect(
            lambda v: self._lbl_sensitivity.setText(str(v))
        )
        sens_row = QHBoxLayout()
        sens_row.addWidget(self._input_sensitivity)
        sens_row.addWidget(self._lbl_sensitivity)
        det_form.addRow("Sensitivity:", sens_row)

        self._input_min_area = QSpinBox()
        self._input_min_area.setRange(10, 50000)
        self._input_min_area.setValue(self.config["detection"]["min_area"])
        det_form.addRow("Min Area (px):", self._input_min_area)

        self._input_cooldown = QDoubleSpinBox()
        self._input_cooldown.setRange(0.5, 60)
        self._input_cooldown.setValue(self.config["detection"]["cooldown_seconds"])
        self._input_cooldown.setSuffix(" s")
        det_form.addRow("Cooldown:", self._input_cooldown)

        det_group.setLayout(det_form)
        layout.addWidget(det_group)

        # ── Recording / Storage settings ──
        rec_group = QGroupBox("Recording & Storage")
        rec_form = QFormLayout()

        self._input_folder = QLineEdit(self.config["recording"]["output_folder"])
        btn_browse = QPushButton("...")
        btn_browse.setMaximumWidth(30)
        btn_browse.clicked.connect(self._browse_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self._input_folder)
        folder_row.addWidget(btn_browse)
        rec_form.addRow("Folder:", folder_row)

        self._input_max_storage = QSpinBox()
        self._input_max_storage.setRange(1, 1000000)
        self._input_max_storage.setSingleStep(500)
        self._input_max_storage.setValue(int(self.config["recording"]["max_storage_mb"]))
        self._input_max_storage.setSuffix(" MB")
        rec_form.addRow("Max Storage:", self._input_max_storage)

        self._input_segment = QSpinBox()
        self._input_segment.setRange(10, 3600)
        self._input_segment.setValue(self.config["recording"]["segment_duration_seconds"])
        self._input_segment.setSuffix(" s")
        rec_form.addRow("Segment Duration:", self._input_segment)

        self._input_pre_rec = QDoubleSpinBox()
        self._input_pre_rec.setRange(0, 30)
        self._input_pre_rec.setValue(self.config["recording"]["pre_record_seconds"])
        self._input_pre_rec.setSuffix(" s")
        rec_form.addRow("Pre-record:", self._input_pre_rec)

        self._input_post_rec = QDoubleSpinBox()
        self._input_post_rec.setRange(0, 60)
        self._input_post_rec.setValue(self.config["recording"]["post_record_seconds"])
        self._input_post_rec.setSuffix(" s")
        rec_form.addRow("Post-record:", self._input_post_rec)

        self._input_fps = QSpinBox()
        self._input_fps.setRange(1, 60)
        self._input_fps.setValue(self.config["recording"]["fps"])
        rec_form.addRow("FPS:", self._input_fps)

        rec_group.setLayout(rec_form)
        layout.addWidget(rec_group)

        # Apply / Save buttons
        btn_row = QHBoxLayout()
        btn_apply = QPushButton("Apply Settings")
        btn_apply.clicked.connect(self._apply_settings)
        btn_row.addWidget(btn_apply)

        btn_save = QPushButton("Save to File")
        btn_save.clicked.connect(self._save_settings)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)
        layout.addStretch()

        return tab

    def _build_recordings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)

        # Storage usage bar
        storage_row = QHBoxLayout()
        self._storage_bar = QProgressBar()
        self._storage_bar.setRange(0, 100)
        self._storage_bar.setTextVisible(True)
        storage_row.addWidget(QLabel("Storage:"))
        storage_row.addWidget(self._storage_bar)
        layout.addLayout(storage_row)

        self._storage_label = QLabel("0 MB / 0 MB (0 files)")
        self._storage_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._storage_label)

        # Recordings table
        self._rec_table = QTableWidget()
        self._rec_table.setColumnCount(3)
        self._rec_table.setHorizontalHeaderLabels(["Filename", "Size", "Date"])
        self._rec_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._rec_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._rec_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._rec_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._rec_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._rec_table.doubleClicked.connect(self._play_recording)
        layout.addWidget(self._rec_table)

        # Buttons
        btn_row = QHBoxLayout()

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._refresh_recordings)
        btn_row.addWidget(btn_refresh)

        btn_play = QPushButton("Play")
        btn_play.clicked.connect(self._play_recording)
        btn_row.addWidget(btn_play)

        btn_open_folder = QPushButton("Open Folder")
        btn_open_folder.clicked.connect(self._open_recordings_folder)
        btn_row.addWidget(btn_open_folder)

        btn_delete = QPushButton("Delete")
        btn_delete.clicked.connect(self._delete_recording)
        btn_row.addWidget(btn_delete)

        layout.addLayout(btn_row)

        return tab

    def _build_zones_tab(self) -> QWidget:
        """Build the Detection Zones tab with info and dialog launcher."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)

        # Zone info
        self._zone_info_label = QLabel("")
        self._zone_info_label.setStyleSheet("color: #cdd6f4; font-size: 11px;")
        self._zone_info_label.setWordWrap(True)
        layout.addWidget(self._zone_info_label)
        self._update_zone_info()

        # Open editor dialog button
        btn_open_editor = QPushButton("Open Zone Editor")
        btn_open_editor.setMinimumHeight(40)
        btn_open_editor.setToolTip(
            "Open a large popup window for drawing and editing detection zones"
        )
        btn_open_editor.clicked.connect(self._open_zone_editor_dialog)
        layout.addWidget(btn_open_editor)

        # Apply / Save buttons
        zone_btn_row = QHBoxLayout()
        btn_apply_zones = QPushButton("Apply Zones")
        btn_apply_zones.clicked.connect(self._zone_apply)
        zone_btn_row.addWidget(btn_apply_zones)

        btn_save_zones = QPushButton("Save Zones")
        btn_save_zones.clicked.connect(self._zone_save)
        zone_btn_row.addWidget(btn_save_zones)

        layout.addLayout(zone_btn_row)
        layout.addStretch()

        return tab

    # ── Zone editor actions ─────────────────────────────────────────

    def _open_zone_editor_dialog(self):
        """Open the zone editor in a large popup dialog."""
        frame = self._camera.get_frame()
        current_zones = self.config["detection"].get("zones", [])

        dialog = ZoneEditorDialog(
            parent=self, frame=frame, zones=current_zones,
        )
        if dialog.exec() == ZoneEditorDialog.DialogCode.Accepted:
            zones = dialog.get_zones()
            self.config["detection"]["zones"] = zones
            self._detector.set_zones(zones)
            self._update_zone_info()
            self.statusBar().showMessage(
                f"Zones updated ({len(zones)} zones)", 3000
            )

    def _update_zone_info(self):
        zones = self.config["detection"].get("zones", [])
        if not zones:
            self._zone_info_label.setText(
                "No detection zones defined.\n"
                "Full frame will be monitored for motion.\n\n"
                "Click 'Open Zone Editor' to draw polygon zones\n"
                "on a camera snapshot."
            )
        else:
            parts = []
            for i, z in enumerate(zones):
                status = "ON" if z.get("enabled", True) else "OFF"
                parts.append(f"  {i+1}. {z.get('name', f'Zone {i+1}')} ({status})")
            active = sum(1 for z in zones if z.get("enabled", True))
            self._zone_info_label.setText(
                f"{len(zones)} zone(s) defined, {active} active:\n" +
                "\n".join(parts) +
                "\n\nClick 'Open Zone Editor' to modify."
            )

    def _zone_apply(self):
        """Apply current zones to the motion detector."""
        zones = self.config["detection"].get("zones", [])
        self._detector.set_zones(zones)
        self.statusBar().showMessage(
            f"Detection zones applied ({len(zones)} zones)", 3000
        )

    def _zone_save(self):
        """Save current zones to config.json."""
        save_config(self.config)
        self.statusBar().showMessage("Detection zones saved to config.json!", 3000)

    def _build_status_bar(self):
        status = self.statusBar()

        self._status_connection = QLabel("Disconnected")
        self._status_connection.setStyleSheet("color: #888; font-size: 12px;")
        status.addWidget(self._status_connection)

        self._status_motion = QLabel("  ○ No Motion")
        self._status_motion.setStyleSheet("color: #888; font-size: 13px;")
        status.addWidget(self._status_motion)

        self._status_recording = QLabel("")
        self._status_recording.setStyleSheet("color: #888; font-size: 12px;")
        status.addPermanentWidget(self._status_recording)

    # ── Actions ─────────────────────────────────────────────────────

    def _toggle_connection(self):
        if self._is_connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        # Update camera config from UI
        self._cam_config = CameraConfig(
            ip=self._input_ip.text().strip(),
            username=self._input_user.text().strip(),
            password=self._input_pass.text(),
            rtsp_port=self._input_port.value(),
            stream_path=self._input_stream.currentText(),
        )
        self._camera = CameraStream(self._cam_config)
        self._camera.start()

        # Poll for connection with retries instead of a single fixed delay
        self._btn_connect.setText("Connecting...")
        self._btn_connect.setEnabled(False)
        self._connect_attempts = 0
        self._connect_max_attempts = 15  # check once per second for 15s
        self._connect_poll_timer = QTimer()
        self._connect_poll_timer.timeout.connect(self._check_connection)
        self._connect_poll_timer.start(1000)

    def _check_connection(self):
        self._connect_attempts += 1

        if self._camera.connected:
            # Success — stop polling and finalize
            self._connect_poll_timer.stop()
            self._btn_connect.setEnabled(True)
            self._is_connected = True
            self._btn_connect.setText("Disconnect")
            self._status_connection.setText(
                f"Connected: {self._cam_config.ip}"
            )
            self._status_connection.setStyleSheet(
                "color: #44bb44; font-size: 12px;"
            )

            # Update recorder resolution
            w, h = self._camera.frame_width, self._camera.frame_height
            if w > 0 and h > 0:
                self._recorder.update_resolution(w, h)

            # Start frame timer (~30 FPS UI update)
            self._frame_timer.start(66)  # ~15 FPS for lower CPU usage

            # Start storage manager
            self._storage.start()
            self._refresh_recordings()
            return

        # Still waiting — update status with attempt count
        remaining = self._connect_max_attempts - self._connect_attempts
        self._status_connection.setText(
            f"Connecting to {self._cam_config.ip}... ({remaining}s)"
        )
        self._status_connection.setStyleSheet(
            "color: #ffaa00; font-size: 12px;"
        )

        if self._connect_attempts >= self._connect_max_attempts:
            # Timed out — give up
            self._connect_poll_timer.stop()
            self._btn_connect.setEnabled(True)
            self._btn_connect.setText("Connect")
            self._status_connection.setText("Connection failed")
            self._status_connection.setStyleSheet(
                "color: #ff4444; font-size: 12px;"
            )
            QMessageBox.warning(
                self,
                "Connection Failed",
                f"Could not connect to camera at {self._cam_config.display_url}\n\n"
                "Please check:\n"
                "• Camera IP address\n"
                "• Username and password (Tapo account credentials)\n"
                "• Camera is powered on and on the same network\n"
                "• RTSP is enabled on the camera",
            )
            self._camera.stop()

    def _disconnect(self):
        if hasattr(self, '_connect_poll_timer') and self._connect_poll_timer.isActive():
            self._connect_poll_timer.stop()
        self._frame_timer.stop()
        self._recorder.shutdown()
        self._camera.stop()
        self._storage.stop()

        self._is_connected = False
        self._btn_connect.setText("Connect")
        self._status_connection.setText("Disconnected")
        self._status_connection.setStyleSheet("color: #888; font-size: 12px;")

        self._video_widget.clear()
        self._video_widget.set_placeholder("Disconnected. Click 'Connect' to start.")

    def _toggle_detection(self):
        self._detector.enabled = not self._detector.enabled
        if self._detector.enabled:
            self._btn_detection.setText("Detection: ON")
        else:
            self._btn_detection.setText("Detection: OFF")

    def _toggle_overlay(self):
        self._show_detection_overlay = not self._show_detection_overlay
        if self._show_detection_overlay:
            self._btn_overlay.setText("Overlay: ON")
        else:
            self._btn_overlay.setText("Overlay: OFF")

    def _take_snapshot(self):
        frame = self._camera.get_frame()
        if frame is None:
            return
        folder = self._input_folder.text().strip() or "recordings"
        os.makedirs(folder, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(folder, f"snapshot_{ts}.jpg")
        cv2.imwrite(path, frame)
        logger.info("Snapshot saved: %s", path)
        self.statusBar().showMessage(f"Snapshot saved: {path}", 3000)

    def _toggle_manual_record(self):
        if self._btn_manual_record.isChecked():
            self._btn_manual_record.setText("Stop Recording")
            self._btn_manual_record.setStyleSheet("background-color: #cc3333; color: white;")
            self._recorder.start_recording()
        else:
            self._btn_manual_record.setText("Manual Record")
            self._btn_manual_record.setStyleSheet("")
            self._recorder.force_stop()
            self._refresh_recordings()

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Recordings Folder"
        )
        if folder:
            self._input_folder.setText(folder)

    def _apply_settings(self):
        """Apply current UI settings to the running components and sync config."""
        # Detection
        self._detector.update_sensitivity(self._input_sensitivity.value())
        self._detector.update_min_area(self._input_min_area.value())
        self._detector.cooldown_seconds = self._input_cooldown.value()

        # Storage
        self._storage.update_max_storage(self._input_max_storage.value())

        # Recording
        self._recorder.output_folder = os.path.abspath(
            self._input_folder.text().strip() or "recordings"
        )
        self._recorder.fps = self._input_fps.value()
        self._recorder.segment_duration = self._input_segment.value()
        self._recorder.pre_record_seconds = self._input_pre_rec.value()
        self._recorder.post_record_seconds = self._input_post_rec.value()

        # Update storage folder
        self._storage.recordings_folder = self._recorder.output_folder
        os.makedirs(self._recorder.output_folder, exist_ok=True)

        # Sync all values back to self.config so save_settings is always current
        self.config["camera"]["ip"] = self._input_ip.text().strip()
        self.config["camera"]["rtsp_port"] = self._input_port.value()
        self.config["camera"]["username"] = self._input_user.text().strip()
        self.config["camera"]["password"] = self._input_pass.text()
        self.config["camera"]["stream_path"] = self._input_stream.currentText()
        self.config["detection"]["sensitivity"] = self._input_sensitivity.value()
        self.config["detection"]["min_area"] = self._input_min_area.value()
        self.config["detection"]["cooldown_seconds"] = self._input_cooldown.value()
        self.config["detection"]["enabled"] = self._detector.enabled
        self.config["recording"]["output_folder"] = self._input_folder.text().strip()
        self.config["recording"]["max_storage_mb"] = self._input_max_storage.value()
        self.config["recording"]["segment_duration_seconds"] = self._input_segment.value()
        self.config["recording"]["pre_record_seconds"] = self._input_pre_rec.value()
        self.config["recording"]["post_record_seconds"] = self._input_post_rec.value()
        self.config["recording"]["fps"] = self._input_fps.value()

        self.statusBar().showMessage("Settings applied!", 3000)
        logger.info("Settings applied")

    def _save_settings(self):
        """Save current UI settings to config.json."""
        # Apply first so self.config is in sync with UI
        self._apply_settings()
        save_config(self.config)
        self.statusBar().showMessage("Settings saved to config.json!", 3000)

    def _refresh_recordings(self):
        """Refresh the recordings table."""
        recordings = self._storage.get_recordings()
        self._rec_table.setRowCount(len(recordings))

        for i, rec in enumerate(recordings):
            self._rec_table.setItem(i, 0, QTableWidgetItem(rec["filename"]))
            self._rec_table.setItem(
                i, 1, QTableWidgetItem(f"{rec['size_mb']:.1f} MB")
            )
            self._rec_table.setItem(i, 2, QTableWidgetItem(rec["datetime"]))

    def _play_recording(self):
        """Open the selected recording in the default media player."""
        row = self._rec_table.currentRow()
        if row < 0:
            return
        filename = self._rec_table.item(row, 0).text()
        filepath = os.path.join(
            self._storage.recordings_folder, filename
        )
        if os.path.exists(filepath):
            # Open with default OS player
            if sys.platform == "win32":
                os.startfile(filepath)
            elif sys.platform == "darwin":
                subprocess.run(["open", filepath])
            else:
                subprocess.run(["xdg-open", filepath])

    def _open_recordings_folder(self):
        """Open the recordings folder in the file explorer."""
        folder = self._storage.recordings_folder
        if os.path.exists(folder):
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.run(["open", folder])
            else:
                subprocess.run(["xdg-open", folder])

    def _delete_recording(self):
        """Delete the selected recording."""
        row = self._rec_table.currentRow()
        if row < 0:
            return
        filename = self._rec_table.item(row, 0).text()
        filepath = os.path.join(
            self._storage.recordings_folder, filename
        )
        reply = QMessageBox.question(
            self,
            "Delete Recording",
            f"Delete {filename}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                os.remove(filepath)
                self._refresh_recordings()
                self.statusBar().showMessage(f"Deleted {filename}", 3000)
            except OSError as e:
                QMessageBox.warning(self, "Error", f"Could not delete: {e}")

    # ── Frame update loop ───────────────────────────────────────────

    def _update_frame(self):
        """Called by timer to grab latest frame and update the UI."""
        frame = self._camera.get_frame()
        if frame is None:
            return

        self._frame_counter += 1

        # Run detection every other frame to save CPU
        if self._frame_counter % 2 == 0:
            self._detector.process_frame(frame)

        # Feed to recorder (pre-buffer or active recording)
        self._recorder.feed_frame(frame)

        # Prepare display frame
        if self._show_detection_overlay and self._detector.enabled:
            display = self._detector.draw_regions(frame)
        else:
            display = frame

        # Add recording indicator
        if self._recorder.recording:
            cv2.circle(display, (30, 30), 12, (0, 0, 255), -1)
            cv2.putText(
                display, "REC", (50, 38),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2,
            )

        # Convert to QPixmap and display
        self._display_frame(display)

    def _display_frame(self, frame):
        """Send the frame to the zoomable video widget."""
        self._video_widget.set_frame(frame)

    def _update_stats(self):
        """Update status bar statistics."""
        # Storage
        self._storage_bar.setValue(int(self._storage.usage_percent))
        self._storage_label.setText(
            f"{self._storage.current_usage_mb:.1f} MB / "
            f"{self._storage.max_storage_mb:.0f} MB "
            f"({self._storage.files_count} files)"
        )

        # Color the bar based on usage
        pct = self._storage.usage_percent
        if pct > 90:
            self._storage_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: #ff4444; }"
            )
        elif pct > 70:
            self._storage_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: #ffaa00; }"
            )
        else:
            self._storage_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: #44bb44; }"
            )

        # Recording status
        if self._recorder.recording:
            self._status_recording.setText(
                f"Recording: {self._recorder.current_recording_duration:.0f}s"
            )
        else:
            self._status_recording.setText("")

    # ── Cleanup ─────────────────────────────────────────────────────

    def closeEvent(self, event):
        """Clean up on window close."""
        if hasattr(self, '_connect_poll_timer') and self._connect_poll_timer.isActive():
            self._connect_poll_timer.stop()
        self._frame_timer.stop()
        self._stats_timer.stop()
        self._recorder.shutdown()
        self._camera.stop()
        self._storage.stop()
        event.accept()
