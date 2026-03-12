"""
Motion detection module.

Uses OpenCV background subtraction and contour analysis to detect
motion in the camera feed. When motion is detected, it signals
the recording manager to start/extend recording.
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
    """

    def __init__(
        self,
        sensitivity: int = 25,
        min_area: int = 500,
        cooldown_seconds: float = 3.0,
    ):
        self.sensitivity = sensitivity
        self.min_area = min_area
        self.cooldown_seconds = cooldown_seconds

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

    def process_frame(self, frame: np.ndarray) -> bool:
        """
        Analyze a frame for motion.

        Returns True if motion is detected in this frame.
        """
        if not self._enabled:
            self._motion_regions = []
            return False

        now = time.time()

        # Apply background subtraction
        fg_mask = self._bg_subtractor.apply(frame)

        # Remove shadows (shadow pixels are marked as 127)
        _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

        # Morphological operations to remove noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
        fg_mask = cv2.dilate(fg_mask, kernel, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(
            fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Filter by area
        motion_found = False
        self._motion_regions = []

        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= self.min_area:
                motion_found = True
                x, y, w, h = cv2.boundingRect(contour)
                self._motion_regions.append((x, y, w, h))

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
        """Draw motion detection bounding boxes on a frame copy."""
        display = frame.copy()
        for x, y, w, h in self._motion_regions:
            cv2.rectangle(display, (x, y), (x + w, y + h), (0, 255, 0), 2)

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
