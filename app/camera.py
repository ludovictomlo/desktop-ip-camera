"""
Camera connection module for TP-Link Tapo C220.

Connects to the camera via RTSP and provides frames for live view
and recording. The Tapo C220 supports RTSP at:
  rtsp://<user>:<pass>@<ip>:<port>/stream1  (high quality)
  rtsp://<user>:<pass>@<ip>:<port>/stream2  (low quality)
"""

import cv2
import threading
import time
import logging
from typing import Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    ip: str
    username: str
    password: str
    rtsp_port: int = 554
    stream_path: str = "/stream1"

    @property
    def rtsp_url(self) -> str:
        return (
            f"rtsp://{self.username}:{self.password}"
            f"@{self.ip}:{self.rtsp_port}{self.stream_path}"
        )

    @property
    def display_url(self) -> str:
        """RTSP URL with password masked for logging."""
        return (
            f"rtsp://{self.username}:****"
            f"@{self.ip}:{self.rtsp_port}{self.stream_path}"
        )


class CameraStream:
    """
    Manages RTSP connection to the Tapo C220 camera.

    Runs a background thread that continuously reads frames.
    Consumers can grab the latest frame at any time.
    """

    def __init__(self, config: CameraConfig):
        self.config = config
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame = None
        self._frame_lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._fps: float = 0.0
        self._frame_count: int = 0
        self._connected = False
        self._on_frame_callbacks: list[Callable] = []
        self._reconnect_delay = 5  # seconds

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def frame_width(self) -> int:
        if self._cap and self._cap.isOpened():
            return int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        return 0

    @property
    def frame_height(self) -> int:
        if self._cap and self._cap.isOpened():
            return int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return 0

    def on_frame(self, callback: Callable):
        """Register a callback that receives each new frame."""
        self._on_frame_callbacks.append(callback)

    def remove_on_frame(self, callback: Callable):
        """Remove a previously registered frame callback."""
        if callback in self._on_frame_callbacks:
            self._on_frame_callbacks.remove(callback)

    def start(self):
        """Start the camera stream in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._thread.start()
        logger.info("Camera stream started for %s", self.config.display_url)

    def stop(self):
        """Stop the camera stream."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self._release()
        logger.info("Camera stream stopped")

    def get_frame(self):
        """Get the latest frame (numpy array) or None."""
        with self._frame_lock:
            return self._frame.copy() if self._frame is not None else None

    def _connect(self) -> bool:
        """Attempt to connect to the RTSP stream."""
        self._release()
        logger.info("Connecting to camera at %s ...", self.config.display_url)

        self._cap = cv2.VideoCapture(self.config.rtsp_url, cv2.CAP_FFMPEG)

        # Set buffer size to minimize latency
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if self._cap.isOpened():
            ret, frame = self._cap.read()
            if ret and frame is not None:
                self._connected = True
                logger.info(
                    "Connected! Resolution: %dx%d",
                    self.frame_width,
                    self.frame_height,
                )
                return True

        self._connected = False
        logger.warning("Failed to connect to camera")
        return False

    def _release(self):
        """Release the video capture."""
        if self._cap:
            self._cap.release()
            self._cap = None
        self._connected = False

    def _stream_loop(self):
        """Main loop that reads frames from the camera."""
        while self._running:
            # Connect / reconnect
            if not self._connected:
                if not self._connect():
                    logger.info(
                        "Retrying connection in %ds...", self._reconnect_delay
                    )
                    time.sleep(self._reconnect_delay)
                    continue

            # Read frame
            try:
                ret, frame = self._cap.read()
            except Exception as e:
                logger.error("Error reading frame: %s", e)
                self._connected = False
                continue

            if not ret or frame is None:
                logger.warning("Lost connection to camera")
                self._connected = False
                continue

            # Update the latest frame
            with self._frame_lock:
                self._frame = frame

            # FPS calculation
            self._frame_count += 1

            # Notify callbacks
            for cb in self._on_frame_callbacks:
                try:
                    cb(frame)
                except Exception as e:
                    logger.error("Frame callback error: %s", e)

        self._release()
