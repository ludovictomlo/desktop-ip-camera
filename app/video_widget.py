"""
Zoomable video display widget.

Provides a live camera feed view with mouse-wheel zoom
anchored at the cursor position and click-drag panning.
"""

import cv2
import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor


class ZoomableVideoWidget(QWidget):
    """
    Widget that displays a video frame with:
    - Scroll-wheel zoom anchored at the mouse cursor
    - Click-drag panning when zoomed in
    - Double-click to reset zoom

    Zoom and pan are purely for the UI display; the actual frame
    fed to the recorder and detector is unaffected.
    """

    MIN_ZOOM = 1.0
    MAX_ZOOM = 10.0
    ZOOM_STEP = 1.15  # 15% per scroll tick

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 360)
        self.setMouseTracking(True)
        self.setStyleSheet(
            "background-color: #1a1a2e; border-radius: 8px;"
        )

        self._pixmap: QPixmap | None = None
        self._placeholder_text = "Camera feed will appear here.\nClick 'Connect' to start."

        # Zoom / pan state (in normalised 0-1 image coords)
        self._zoom: float = 1.0
        # Centre of the visible viewport in normalised coords
        self._view_cx: float = 0.5
        self._view_cy: float = 0.5

        # Drag state
        self._dragging = False
        self._drag_start_pos = QPointF()
        self._drag_start_cx: float = 0.0
        self._drag_start_cy: float = 0.0

    # ── Public ──────────────────────────────────────────────────────

    @property
    def zoom_level(self) -> float:
        return self._zoom

    def set_placeholder(self, text: str):
        self._placeholder_text = text
        if self._pixmap is None:
            self.update()

    def set_frame(self, frame):
        """Update the displayed frame (OpenCV BGR numpy array)."""
        if frame is None:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bpl = ch * w
        q_img = QImage(rgb.data, w, h, bpl, QImage.Format.Format_RGB888)
        self._pixmap = QPixmap.fromImage(q_img)
        self.update()

    def clear(self):
        self._pixmap = None
        self.reset_zoom()
        self.update()

    def reset_zoom(self):
        self._zoom = 1.0
        self._view_cx = 0.5
        self._view_cy = 0.5
        self.update()

    # ── Painting ────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        if self._pixmap is None:
            painter.setPen(QColor(170, 170, 170))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                self._placeholder_text,
            )
            painter.end()
            return

        ww, wh = self.width(), self.height()
        pw, ph = self._pixmap.width(), self._pixmap.height()

        # The visible portion of the image in normalised coords
        view_w = 1.0 / self._zoom
        view_h = 1.0 / self._zoom

        # Clamp the view centre so we don't go out of bounds
        half_w = view_w / 2.0
        half_h = view_h / 2.0
        cx = max(half_w, min(1.0 - half_w, self._view_cx))
        cy = max(half_h, min(1.0 - half_h, self._view_cy))
        self._view_cx, self._view_cy = cx, cy

        # Source rect in pixel coords
        src_x = (cx - half_w) * pw
        src_y = (cy - half_h) * ph
        src_w = view_w * pw
        src_h = view_h * ph

        src_rect = QRectF(src_x, src_y, src_w, src_h)

        # Destination: fit into widget preserving aspect ratio
        src_aspect = src_w / max(src_h, 1)
        dst_aspect = ww / max(wh, 1)

        if src_aspect > dst_aspect:
            # Source wider → letterbox top/bottom
            dst_w = ww
            dst_h = ww / src_aspect
        else:
            dst_h = wh
            dst_w = wh * src_aspect

        dst_x = (ww - dst_w) / 2
        dst_y = (wh - dst_h) / 2
        dst_rect = QRectF(dst_x, dst_y, dst_w, dst_h)

        painter.drawPixmap(dst_rect, self._pixmap, src_rect)

        # Zoom indicator when zoomed in
        if self._zoom > 1.05:
            painter.setPen(QColor(255, 255, 255, 160))
            font = painter.font()
            font.setPointSize(9)
            painter.setFont(font)
            painter.drawText(
                int(dst_x) + 8, int(dst_y) + 16,
                f"{self._zoom:.1f}x",
            )

        painter.end()

    # ── Wheel zoom ──────────────────────────────────────────────────

    def wheelEvent(self, event):
        if self._pixmap is None:
            return

        # Mouse position in widget coords → normalised image coords
        norm = self._widget_to_norm(event.position())
        if norm is None:
            return

        mx, my = norm

        old_zoom = self._zoom
        delta = event.angleDelta().y()
        if delta > 0:
            new_zoom = min(self._zoom * self.ZOOM_STEP, self.MAX_ZOOM)
        else:
            new_zoom = max(self._zoom / self.ZOOM_STEP, self.MIN_ZOOM)

        if new_zoom == old_zoom:
            return

        # Adjust view centre so the point under the cursor stays fixed.
        # Before zoom: norm coords of mouse = view_cx + (widget_rel) * (1/old_zoom)
        # We want the same image point to remain under the cursor after zoom.
        # new_cx = mx - (mx - old_cx) * (old_zoom / new_zoom)
        ratio = old_zoom / new_zoom
        self._view_cx = mx - (mx - self._view_cx) * ratio
        self._view_cy = my - (my - self._view_cy) * ratio

        self._zoom = new_zoom

        # If zoomed back to 1x, reset to centre
        if self._zoom <= 1.01:
            self._zoom = 1.0
            self._view_cx = 0.5
            self._view_cy = 0.5

        self.update()

    # ── Drag to pan ─────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._zoom > 1.01:
            self._dragging = True
            self._drag_start_pos = event.position()
            self._drag_start_cx = self._view_cx
            self._drag_start_cy = self._view_cy
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._dragging:
            dx = event.position().x() - self._drag_start_pos.x()
            dy = event.position().y() - self._drag_start_pos.y()

            # Convert pixel drag to normalised offset
            # The visible portion spans (1/zoom) in norm coords
            # and occupies ~widget_size pixels
            ww, wh = self.width(), self.height()
            self._view_cx = self._drag_start_cx - (dx / ww) * (1.0 / self._zoom)
            self._view_cy = self._drag_start_cy - (dy / wh) * (1.0 / self._zoom)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            if self._zoom > 1.01:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_zoom()
            self.setCursor(Qt.CursorShape.ArrowCursor)

    # ── Helpers ─────────────────────────────────────────────────────

    def _image_display_rect(self) -> QRectF | None:
        """Return the destination rect where the image is currently drawn."""
        if self._pixmap is None:
            return None

        pw, ph = self._pixmap.width(), self._pixmap.height()
        view_w = pw / self._zoom
        view_h = ph / self._zoom

        ww, wh = self.width(), self.height()
        src_aspect = view_w / max(view_h, 1)
        dst_aspect = ww / max(wh, 1)

        if src_aspect > dst_aspect:
            dst_w = ww
            dst_h = ww / src_aspect
        else:
            dst_h = wh
            dst_w = wh * src_aspect

        dst_x = (ww - dst_w) / 2
        dst_y = (wh - dst_h) / 2
        return QRectF(dst_x, dst_y, dst_w, dst_h)

    def _widget_to_norm(self, pos) -> tuple[float, float] | None:
        """Convert widget pixel position to normalised (0-1) image coordinates."""
        rect = self._image_display_rect()
        if rect is None:
            return None

        # Position relative to the displayed image rect (0-1 within visible region)
        rel_x = (pos.x() - rect.x()) / max(rect.width(), 1)
        rel_y = (pos.y() - rect.y()) / max(rect.height(), 1)

        # Visible region in norm coords
        view_w = 1.0 / self._zoom
        view_h = 1.0 / self._zoom
        half_w = view_w / 2.0
        half_h = view_h / 2.0
        cx = max(half_w, min(1.0 - half_w, self._view_cx))
        cy = max(half_h, min(1.0 - half_h, self._view_cy))

        nx = (cx - half_w) + rel_x * view_w
        ny = (cy - half_h) + rel_y * view_h
        return (nx, ny)
