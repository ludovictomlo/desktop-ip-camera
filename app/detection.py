"""
Motion detection module.

Uses OpenCV background subtraction and contour analysis to detect
motion in the camera feed. When motion is detected, it signals
the recording manager to start/extend recording.

Supports:
- Detection zones (polygon masks) to limit where motion is detected
- Downscaled processing for lower CPU usage
"""

import cv2
import time
import logging
import numpy as np
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class MotionDetector:
    """
    Detects motion in video frames using background subtraction.

    Parameters
    ----------
    sensitivity : int
        Threshold for binary frame differencing (lower = more sensitive).
        Range: 1-100, default 25.
    min_area : int
        Minimum contour area (in pixels) to be considered motion.
        Filters out noise. Default 500.
    cooldown_seconds : float
        Time after last motion before "motion stopped" is fired.
    detection_scale : float
        Scale factor for processing (0.25-1.0). Lower = faster but coarser.
        Default 0.5 processes at half resolution.
    """

    def __init__(
        self,
        sensitivity: int = 25,
        min_area: int = 500,
        cooldown_seconds: float = 3.0,
        detection_scale: float = 0.5,
    ):
        self.sensitivity = sensitivity
        self.min_area = min_area
        self.cooldown_seconds = cooldown_seconds
        self._detection_scale = max(0.1, min(1.0, detection_scale))

        self._bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=self.sensitivity,
            detectShadows=True,
        )

        self._motion_active = False
        self._last_motion_time: float = 0
        self._enabled = True

        # Callbacks
        self._on_motion_start: Optional[Callable] = None
        self._on_motion_end: Optional[Callable] = None
        self._on_motion_frame: Optional[Callable] = None

        # Stats
        self._motion_regions: list = []

        # Cached morphological kernel (avoid recreating every frame)
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

        # Detection zones
        self._zones: list[dict] = []
        self._zone_mask_cache: Optional[np.ndarray] = None
        self._zone_mask_full_cache: Optional[np.ndarray] = None
        self._cached_frame_size: tuple = (0, 0)
        self._cached_full_size: tuple = (0, 0)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
        if not value and self._motion_active:
            self._motion_active = False
            if self._on_motion_end:
                self._on_motion_end()

    @property
    def motion_active(self) -> bool:
        return self._motion_active

    @property
    def motion_regions(self) -> list:
        """List of bounding rects (x, y, w, h) of detected motion."""
        return self._motion_regions

    def set_callbacks(
        self,
        on_motion_start: Optional[Callable] = None,
        on_motion_end: Optional[Callable] = None,
        on_motion_frame: Optional[Callable] = None,
    ):
        """Set motion event callbacks."""
        self._on_motion_start = on_motion_start
        self._on_motion_end = on_motion_end
        self._on_motion_frame = on_motion_frame

    def update_sensitivity(self, sensitivity: int):
        """Update detection sensitivity (recreates background subtractor)."""
        self.sensitivity = max(1, min(100, sensitivity))
        self._bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=self.sensitivity,
            detectShadows=True,
        )
        logger.info("Motion sensitivity updated to %d", self.sensitivity)

    def update_min_area(self, min_area: int):
        """Update minimum contour area."""
        self.min_area = max(10, min_area)

    def set_zones(self, zones: list[dict]):
        """
        Set detection zones.

        Each zone dict has:
            "points": list of [x, y] normalised (0-1) coordinates
            "enabled": bool
        """
        self._zones = zones
        # Invalidate cached masks so they are rebuilt on next frame
        self._zone_mask_cache = None
        self._zone_mask_full_cache = None
        self._cached_frame_size = (0, 0)
        self._cached_full_size = (0, 0)
        active = sum(1 for z in zones if z.get("enabled", True) and len(z.get("points", [])) >= 3)
        logger.info("Detection zones updated: %d total, %d active", len(zones), active)

    def _build_zone_mask(self, width: int, height: int) -> Optional[np.ndarray]:
        """Build a binary mask from the zone polygons at the given resolution."""
        active_zones = [
            z for z in self._zones
            if z.get("enabled", True) and len(z.get("points", [])) >= 3
        ]
        if not active_zones:
            return None

        mask = np.zeros((height, width), dtype=np.uint8)
        for zone in active_zones:
            pts = np.array(
                [(int(p[0] * width), int(p[1] * height)) for p in zone["points"]],
                dtype=np.int32,
            )
            cv2.fillPoly(mask, [pts], 255)

        return mask if np.any(mask) else None

    def _get_zone_mask(self, width: int, height: int) -> Optional[np.ndarray]:
        """Get (or build and cache) the zone mask for the detection-scaled frame."""
        if (width, height) != self._cached_frame_size:
            self._cached_frame_size = (width, height)
            self._zone_mask_cache = self._build_zone_mask(width, height)
        return self._zone_mask_cache

    def _get_zone_mask_full(self, width: int, height: int) -> Optional[np.ndarray]:
        """Get (or build and cache) the zone mask at full resolution (for overlay)."""
        if (width, height) != self._cached_full_size:
            self._cached_full_size = (width, height)
            self._zone_mask_full_cache = self._build_zone_mask(width, height)
        return self._zone_mask_full_cache

    def process_frame(self, frame: np.ndarray) -> bool:
        """
        Analyze a frame for motion.

        The frame is downscaled by ``detection_scale`` before processing
        to reduce CPU usage. Detected regions are mapped back to full
        resolution for overlay drawing.

        Returns True if motion is detected in this frame.
        """
        if not self._enabled:
            self._motion_regions = []
            return False

        now = time.time()
        h, w = frame.shape[:2]
        scale = self._detection_scale

        # Downscale for faster processing
        small_w, small_h = int(w * scale), int(h * scale)
        if scale < 1.0:
            small_frame = cv2.resize(
                frame, (small_w, small_h), interpolation=cv2.INTER_LINEAR
            )
        else:
            small_frame = frame

        # Apply background subtraction on small frame
        fg_mask = self._bg_subtractor.apply(small_frame)

        # Remove shadows (shadow pixels are marked as 127)
        _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

        # Morphological operations to remove noise (use cached kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, self._kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, self._kernel)
        fg_mask = cv2.dilate(fg_mask, self._kernel, iterations=2)

        # Apply zone mask (if any zones are defined)
        zone_mask = self._get_zone_mask(small_w, small_h)
        if zone_mask is not None:
            fg_mask = cv2.bitwise_and(fg_mask, zone_mask)

        # Find contours
        contours, _ = cv2.findContours(
            fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Filter by area (scaled to match downscaled frame)
        min_area_scaled = self.min_area * (scale * scale)
        inv_scale = 1.0 / scale
        motion_found = False
        self._motion_regions = []

        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= min_area_scaled:
                motion_found = True
                x, y, cw, ch = cv2.boundingRect(contour)
                # Scale bounding rect back to original resolution
                self._motion_regions.append((
                    int(x * inv_scale),
                    int(y * inv_scale),
                    int(cw * inv_scale),
                    int(ch * inv_scale),
                ))

        if motion_found:
            self._last_motion_time = now

            if not self._motion_active:
                self._motion_active = True
                logger.info("Motion detected!")
                if self._on_motion_start:
                    self._on_motion_start()

            if self._on_motion_frame:
                self._on_motion_frame(frame, self._motion_regions)

        elif self._motion_active:
            # Check cooldown
            elapsed = now - self._last_motion_time
            if elapsed >= self.cooldown_seconds:
                self._motion_active = False
                logger.info("Motion ended (%.1fs cooldown elapsed)", elapsed)
                if self._on_motion_end:
                    self._on_motion_end()

        return motion_found

    def draw_regions(self, frame: np.ndarray) -> np.ndarray:
        """Draw motion detection bounding boxes and zone overlays on a frame copy."""
        display = frame.copy()
        h, w = frame.shape[:2]

        # Draw zone overlays (semi-transparent fill + solid outline)
        active_zones = [
            z for z in self._zones
            if z.get("enabled", True) and len(z.get("points", [])) >= 3
        ]
        if active_zones:
            overlay = display.copy()
            for zone in active_zones:
                pts = np.array(
                    [(int(p[0] * w), int(p[1] * h)) for p in zone["points"]],
                    dtype=np.int32,
                )
                cv2.fillPoly(overlay, [pts], (0, 200, 255))
            cv2.addWeighted(overlay, 0.12, display, 0.88, 0, display)

            # Zone outlines
            for zone in active_zones:
                pts = np.array(
                    [(int(p[0] * w), int(p[1] * h)) for p in zone["points"]],
                    dtype=np.int32,
                )
                cv2.polylines(display, [pts], True, (0, 200, 255), 2)

        # Draw motion bounding boxes
        for x, y, cw, ch in self._motion_regions:
            cv2.rectangle(display, (x, y), (x + cw, y + ch), (0, 255, 0), 2)

        if self._motion_active:
            cv2.putText(
                display,
                "MOTION DETECTED",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 0, 255),
                2,
            )

        return display

    def reset(self):
        """Reset the background model."""
        self._bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=self.sensitivity,
            detectShadows=True,
        )
        self._motion_active = False
        self._motion_regions = []
        logger.info("Motion detector reset")
