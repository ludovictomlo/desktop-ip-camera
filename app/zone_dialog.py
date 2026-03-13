"""
Detection Zone Editor dialog.

A resizable popup dialog for comfortable zone editing.
Opens large (80% of screen) so users can draw polygons easily.
"""

import logging

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QMessageBox,
    QInputDialog,
    QSizePolicy,
)
from PyQt6.QtCore import Qt

from app.zone_editor import ZoneEditorWidget

logger = logging.getLogger(__name__)


class ZoneEditorDialog(QDialog):
    """
    Popup dialog for editing detection zones on a large canvas.

    The dialog opens at 80% of screen size and is freely resizable,
    giving much more room to draw and edit polygons than the sidebar.
    """

    def __init__(self, parent=None, frame=None, zones: list | None = None):
        super().__init__(parent)
        self.setWindowTitle("Detection Zone Editor")
        self.setMinimumSize(800, 500)

        # Size to 80% of available screen
        if parent and parent.screen():
            geom = parent.screen().availableGeometry()
        else:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            geom = screen.availableGeometry() if screen else None

        if geom:
            w = int(geom.width() * 0.8)
            h = int(geom.height() * 0.8)
            self.resize(w, h)
            self.move(
                geom.x() + (geom.width() - w) // 2,
                geom.y() + (geom.height() - h) // 2,
            )

        self._result_zones: list[dict] = []

        self._build_ui(frame, zones)

    # ── Public ──────────────────────────────────────────────────────

    def get_zones(self) -> list[dict]:
        """Return the zones as configured when the dialog was accepted."""
        return self._result_zones

    # ── UI ──────────────────────────────────────────────────────────

    def _build_ui(self, frame, zones):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Zone editor canvas (fill most of the dialog)
        self._editor = ZoneEditorWidget()
        self._editor.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        if frame is not None:
            self._editor.set_image_from_frame(frame)
        if zones:
            self._editor.set_zones(zones)
        self._editor.zones_changed.connect(self._on_zones_changed)
        layout.addWidget(self._editor, stretch=1)

        # ── Toolbar row 1: drawing ──
        row1 = QHBoxLayout()

        self._btn_add = QPushButton("Add Zone")
        self._btn_add.setToolTip("Start drawing a new detection zone polygon")
        self._btn_add.clicked.connect(self._start_drawing)
        row1.addWidget(self._btn_add)

        self._btn_finish = QPushButton("Finish Drawing")
        self._btn_finish.setToolTip("Close the current polygon (need >= 3 points)")
        self._btn_finish.clicked.connect(self._finish_drawing)
        self._btn_finish.setEnabled(False)
        row1.addWidget(self._btn_finish)

        self._btn_cancel_draw = QPushButton("Cancel Drawing")
        self._btn_cancel_draw.setToolTip("Discard the polygon in progress")
        self._btn_cancel_draw.clicked.connect(self._cancel_drawing)
        self._btn_cancel_draw.setEnabled(False)
        row1.addWidget(self._btn_cancel_draw)

        row1.addStretch()
        layout.addLayout(row1)

        # ── Toolbar row 2: selection actions ──
        row2 = QHBoxLayout()

        self._btn_rename = QPushButton("Rename")
        self._btn_rename.setToolTip("Rename the selected zone")
        self._btn_rename.clicked.connect(self._rename_zone)
        row2.addWidget(self._btn_rename)

        self._btn_toggle = QPushButton("Toggle On/Off")
        self._btn_toggle.setToolTip("Enable or disable the selected zone")
        self._btn_toggle.clicked.connect(self._toggle_zone)
        row2.addWidget(self._btn_toggle)

        self._btn_delete = QPushButton("Delete Zone")
        self._btn_delete.setToolTip("Delete the selected zone")
        self._btn_delete.clicked.connect(self._delete_zone)
        row2.addWidget(self._btn_delete)

        self._btn_clear = QPushButton("Clear All")
        self._btn_clear.setToolTip("Remove all zones")
        self._btn_clear.clicked.connect(self._clear_zones)
        row2.addWidget(self._btn_clear)

        row2.addStretch()
        layout.addLayout(row2)

        # ── Info label ──
        self._info = QLabel("")
        self._info.setStyleSheet("color: #888; font-size: 11px;")
        self._info.setWordWrap(True)
        layout.addWidget(self._info)
        self._update_info()

        # ── OK / Cancel ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setMinimumWidth(100)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_ok = QPushButton("Apply && Close")
        btn_ok.setMinimumWidth(140)
        btn_ok.setStyleSheet(
            "background-color: #44bb44; color: #111; font-weight: bold;"
        )
        btn_ok.clicked.connect(self._accept)
        btn_row.addWidget(btn_ok)

        layout.addLayout(btn_row)

    # ── Drawing actions ─────────────────────────────────────────────

    def _start_drawing(self):
        # Ask for a name first
        name, ok = QInputDialog.getText(
            self, "Zone Name", "Enter a name for the new zone:",
            text=f"Zone {len(self._editor.get_zones()) + 1}",
        )
        if not ok or not name.strip():
            return

        self._pending_zone_name = name.strip()
        self._editor.start_drawing()
        self._btn_add.setEnabled(False)
        self._btn_finish.setEnabled(True)
        self._btn_cancel_draw.setEnabled(True)

    def _finish_drawing(self):
        self._editor.finish_zone()
        # Update the name of the last-added zone
        zones = self._editor.get_zones()
        if zones and hasattr(self, "_pending_zone_name"):
            zones[-1]["name"] = self._pending_zone_name
            self._editor.set_zones(zones)
            del self._pending_zone_name
        self._btn_add.setEnabled(True)
        self._btn_finish.setEnabled(False)
        self._btn_cancel_draw.setEnabled(False)

    def _cancel_drawing(self):
        self._editor.cancel_drawing()
        self._btn_add.setEnabled(True)
        self._btn_finish.setEnabled(False)
        self._btn_cancel_draw.setEnabled(False)

    # ── Zone management ─────────────────────────────────────────────

    def _rename_zone(self):
        idx = self._editor.selected_zone
        if idx < 0:
            QMessageBox.information(self, "No Selection", "Click a zone to select it first.")
            return
        zones = self._editor.get_zones()
        old_name = zones[idx].get("name", f"Zone {idx + 1}")
        name, ok = QInputDialog.getText(
            self, "Rename Zone", "New name:", text=old_name,
        )
        if ok and name.strip():
            zones[idx]["name"] = name.strip()
            self._editor.set_zones(zones)
            # Re-select the same zone
            self._editor._selected_zone = idx
            self._editor.update()

    def _toggle_zone(self):
        self._editor.toggle_selected()
        self._update_info()

    def _delete_zone(self):
        if self._editor.selected_zone < 0:
            QMessageBox.information(self, "No Selection", "Click a zone to select it first.")
            return
        self._editor.delete_selected()
        self._update_info()

    def _clear_zones(self):
        reply = QMessageBox.question(
            self, "Clear Zones", "Remove all detection zones?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._editor.clear_all()
            self._update_info()

    # ── Info & signals ──────────────────────────────────────────────

    def _on_zones_changed(self, zones):
        self._btn_add.setEnabled(True)
        self._btn_finish.setEnabled(False)
        self._btn_cancel_draw.setEnabled(False)
        self._update_info()

    def _update_info(self):
        zones = self._editor.get_zones()
        if not zones:
            self._info.setText(
                "No zones defined — full frame will be monitored.\n"
                "Click 'Add Zone', enter a name, then click on the image to "
                "draw polygon points. Right-click or double-click to close the polygon."
            )
        else:
            parts = []
            for i, z in enumerate(zones):
                status = "ON" if z.get("enabled", True) else "OFF"
                parts.append(f"  {i+1}. {z['name']} ({status})")
            self._info.setText(
                f"{len(zones)} zone(s):\n" + "\n".join(parts) +
                "\nClick a zone to select → Rename / Toggle / Delete."
            )

    def _accept(self):
        self._result_zones = self._editor.get_zones()
        self.accept()
