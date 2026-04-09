"""
Detection Zone Editor widget.

Interactive widget for drawing and editing polygon detection zones
on a camera snapshot. Zones define areas where motion detection is active.
"""

import cv2
import numpy as np
import logging

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import (
    QImage,
    QPixmap,
    QPainter,
    QColor,
    QPen,
    QBrush,
    QPolygonF,
)

logger = logging.getLogger(__name__)


class ZoneEditorWidget(QWidget):
    """
    Interactive widget for drawing and editing detection zones.

    Zones are stored as normalized (0-1) polygons so they are
    resolution-independent. Left-click to add points, right-click
    or double-click to finish the polygon. Click an existing zone
    to select it, then delete with the Delete key or button.
    """

    zones_changed = pyqtSignal(list)

    # Zone overlay colors (BGR-ish for consistency, but used as RGB here)
    ZONE_COLORS = [
        (0, 200, 255),
        (0, 255, 128),
        (255, 100, 100),
        (200, 100, 255),
        (100, 255, 255),
        (255, 200, 100),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 180)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._pixmap: QPixmap | None = None
        self._zones: list[dict] = []
        self._current_points: list[list[float]] = []
        self._drawing = False
        self._selected_zone = -1
        self._hover_pos = None

        self.setStyleSheet("background-color: #1a1a2e; border-radius: 4px;")

    # ── Public API ──────────────────────────────────────────────────

    @property
    def drawing(self) -> bool:
        return self._drawing

    @property
    def selected_zone(self) -> int:
        return self._selected_zone

    def set_image_from_frame(self, frame):
        """Set the background image from an OpenCV BGR frame."""
        if frame is None:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        q_img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self._pixmap = QPixmap.fromImage(q_img)
        self.update()

    def set_zones(self, zones: list[dict]):
        """Load zones from config (list of zone dicts)."""
        self._zones = []
        for z in zones:
            self._zones.append({
                "name": z.get("name", f"Zone {len(self._zones) + 1}"),
                "points": [list(p) for p in z.get("points", [])],
                "enabled": z.get("enabled", True),
            })
        self._selected_zone = -1
        self.update()

    def get_zones(self) -> list[dict]:
        """Return current zones as serialisable list of dicts."""
        return [
            {"name": z["name"], "points": z["points"], "enabled": z["enabled"]}
            for z in self._zones
        ]

    def start_drawing(self):
        """Enter drawing mode for a new zone."""
        self._drawing = True
        self._current_points = []
        self._selected_zone = -1
        self._hover_pos = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def cancel_drawing(self):
        """Cancel the current drawing operation."""
        self._drawing = False
        self._current_points = []
        self._hover_pos = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def finish_zone(self):
        """Finish the current polygon and store it as a zone."""
        if len(self._current_points) >= 3:
            zone = {
                "name": f"Zone {len(self._zones) + 1}",
                "points": self._current_points[:],
                "enabled": True,
            }
            self._zones.append(zone)
            self.zones_changed.emit(self._zones)
            logger.info(
                "Zone added: %s (%d points)", zone["name"], len(zone["points"])
            )
        self._drawing = False
        self._current_points = []
        self._hover_pos = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def delete_selected(self) -> bool:
        """Delete the currently selected zone. Returns True if a zone was removed."""
        if 0 <= self._selected_zone < len(self._zones):
            removed = self._zones.pop(self._selected_zone)
            self._selected_zone = -1
            self.zones_changed.emit(self._zones)
            logger.info("Zone deleted: %s", removed["name"])
            self.update()
            return True
        return False

    def clear_all(self):
        """Remove all zones."""
        self._zones.clear()
        self._selected_zone = -1
        self._drawing = False
        self._current_points = []
        self.zones_changed.emit(self._zones)
        self.update()

    def toggle_selected(self):
        """Toggle enabled state of the selected zone."""
        if 0 <= self._selected_zone < len(self._zones):
            z = self._zones[self._selected_zone]
            z["enabled"] = not z["enabled"]
            self.zones_changed.emit(self._zones)
            self.update()

    # ── Coordinate helpers ──────────────────────────────────────────

    def _image_rect(self) -> QRectF:
        """Rectangle where the image is drawn (centred, aspect-preserving)."""
        if self._pixmap is None:
            return QRectF(0, 0, self.width(), self.height())
        pw, ph = self._pixmap.width(), self._pixmap.height()
        ww, wh = self.width(), self.height()
        scale = min(ww / pw, wh / ph)
        dw, dh = pw * scale, ph * scale
        dx, dy = (ww - dw) / 2, (wh - dh) / 2
        return QRectF(dx, dy, dw, dh)

    def _widget_to_norm(self, pos) -> list[float]:
        """Widget pixel → normalised (0-1) image coordinate."""
        rect = self._image_rect()
        x = (pos.x() - rect.x()) / rect.width()
        y = (pos.y() - rect.y()) / rect.height()
        return [max(0.0, min(1.0, x)), max(0.0, min(1.0, y))]

    def _norm_to_widget(self, nx: float, ny: float) -> QPointF:
        """Normalised (0-1) → widget pixel coordinate."""
        rect = self._image_rect()
        return QPointF(rect.x() + nx * rect.width(), rect.y() + ny * rect.height())

    # ── Painting ────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background image
        if self._pixmap:
            rect = self._image_rect()
            painter.drawPixmap(rect.toRect(), self._pixmap)
        else:
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "No camera frame.\nConnect and click 'Grab Frame'.",
            )

        # Existing zones
        for i, zone in enumerate(self._zones):
            self._paint_zone(painter, zone, i)

        # Current polygon being drawn
        if self._drawing and self._current_points:
            self._paint_current_polygon(painter)

        painter.end()

    def _paint_zone(self, painter: QPainter, zone: dict, index: int):
        points = zone["points"]
        if len(points) < 3:
            return

        r, g, b = self.ZONE_COLORS[index % len(self.ZONE_COLORS)]
        selected = index == self._selected_zone
        enabled = zone.get("enabled", True)

        alpha_fill = 50 if enabled else 20
        alpha_line = 200 if enabled else 80

        poly = QPolygonF([self._norm_to_widget(p[0], p[1]) for p in points])

        painter.setBrush(QBrush(QColor(r, g, b, alpha_fill)))
        if selected:
            painter.setPen(QPen(QColor(255, 255, 255, 240), 3))
        else:
            painter.setPen(QPen(QColor(r, g, b, alpha_line), 2))

        painter.drawPolygon(poly)

        # Corner dots for selected zone
        if selected:
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.setPen(Qt.PenStyle.NoPen)
            for p in points:
                painter.drawEllipse(self._norm_to_widget(p[0], p[1]), 5, 5)

        # Zone label at centroid
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        lpt = self._norm_to_widget(cx, cy)

        painter.setPen(QColor(255, 255, 255, 220))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)

        label = zone.get("name", f"Zone {index + 1}")
        if not enabled:
            label += " (off)"
        painter.drawText(
            int(lpt.x()) - 80, int(lpt.y()) - 10, 160, 20,
            Qt.AlignmentFlag.AlignCenter, label,
        )

    def _paint_current_polygon(self, painter: QPainter):
        pts = [self._norm_to_widget(p[0], p[1]) for p in self._current_points]

        # Ghost line to cursor
        if self._hover_pos is not None:
            pts.append(QPointF(self._hover_pos.x(), self._hover_pos.y()))

        painter.setPen(QPen(QColor(255, 255, 0, 200), 2, Qt.PenStyle.DashLine))
        painter.setBrush(QBrush(QColor(255, 255, 0, 30)))

        if len(pts) >= 3:
            painter.drawPolygon(QPolygonF(pts))
        elif len(pts) == 2:
            painter.drawLine(pts[0], pts[1])

        # Vertex dots
        painter.setBrush(QBrush(QColor(255, 255, 0)))
        painter.setPen(Qt.PenStyle.NoPen)
        for p in self._current_points:
            painter.drawEllipse(self._norm_to_widget(p[0], p[1]), 5, 5)

        # Hint text
        remaining = 3 - len(self._current_points)
        painter.setPen(QColor(255, 255, 0))
        if remaining > 0:
            painter.drawText(
                10, self.height() - 10,
                f"Click to add points ({remaining} more needed). "
                "Right-click or double-click to finish.",
            )
        else:
            painter.drawText(
                10, self.height() - 10,
                "Click to add more points. Right-click or double-click to finish.",
            )

    # ── Mouse / Keyboard events ─────────────────────────────────────

    def mousePressEvent(self, event):
        if self._pixmap is None:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            if self._drawing:
                norm = self._widget_to_norm(event.pos())
                self._current_points.append(norm)
                self.update()
            else:
                norm = self._widget_to_norm(event.pos())
                self._try_select(norm[0], norm[1])

        elif event.button() == Qt.MouseButton.RightButton:
            if self._drawing and len(self._current_points) >= 3:
                self.finish_zone()

    def mouseDoubleClickEvent(self, event):
        if self._drawing and event.button() == Qt.MouseButton.LeftButton:
            if len(self._current_points) >= 3:
                self.finish_zone()

    def mouseMoveEvent(self, event):
        if self._drawing:
            self._hover_pos = event.pos()
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self._drawing:
                self.cancel_drawing()
        elif event.key() == Qt.Key.Key_Delete:
            self.delete_selected()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._drawing and len(self._current_points) >= 3:
                self.finish_zone()

    # ── Selection helper ────────────────────────────────────────────

    def _try_select(self, nx: float, ny: float):
        """Select the top-most zone containing (nx, ny)."""
        for i in range(len(self._zones) - 1, -1, -1):
            points = self._zones[i]["points"]
            if len(points) >= 3 and self._point_in_polygon(nx, ny, points):
                self._selected_zone = i
                self.update()
                return
        self._selected_zone = -1
        self.update()

    @staticmethod
    def _point_in_polygon(x: float, y: float, polygon: list) -> bool:
        """Ray-casting point-in-polygon test."""
        n = len(polygon)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            if ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / (yj - yi) + xi
            ):
                inside = not inside
            j = i
        return inside
