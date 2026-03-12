"""
Storage manager module.

Monitors the recordings folder and enforces the maximum storage limit.
When the total size exceeds the threshold, the oldest recordings are
deleted to make space — implementing the "loop recording" behavior.
"""

import os
import time
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class StorageManager:
    """
    Manages recording storage with automatic cleanup.

    Periodically checks the total size of recordings and deletes
    the oldest files when the max storage limit is exceeded.
    """

    def __init__(
        self,
        recordings_folder: str = "recordings",
        max_storage_mb: float = 5000,
        check_interval_seconds: float = 30,
    ):
        self.recordings_folder = os.path.abspath(recordings_folder)
        self.max_storage_mb = max_storage_mb
        self.max_storage_bytes = max_storage_mb * 1024 * 1024
        self.check_interval = check_interval_seconds

        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Stats
        self.current_usage_mb: float = 0
        self.files_count: int = 0
        self.files_deleted: int = 0

        os.makedirs(self.recordings_folder, exist_ok=True)

    @property
    def usage_percent(self) -> float:
        if self.max_storage_mb <= 0:
            return 0
        return (self.current_usage_mb / self.max_storage_mb) * 100

    def start(self):
        """Start the storage monitor in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info(
            "Storage manager started (max: %.0f MB, folder: %s)",
            self.max_storage_mb,
            self.recordings_folder,
        )

    def stop(self):
        """Stop the storage monitor."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
        logger.info("Storage manager stopped")

    def check_and_cleanup(self):
        """
        Check storage usage and delete oldest files if over limit.
        Can be called manually or runs automatically via the monitor.
        """
        files = self._get_recording_files()
        total_size = sum(f["size"] for f in files)
        self.current_usage_mb = total_size / (1024 * 1024)
        self.files_count = len(files)

        if total_size <= self.max_storage_bytes:
            return

        # Sort by modification time (oldest first)
        files.sort(key=lambda f: f["mtime"])

        logger.info(
            "Storage limit exceeded: %.1f MB / %.1f MB (%d files)",
            self.current_usage_mb,
            self.max_storage_mb,
            self.files_count,
        )

        # Delete oldest files until we're under the limit
        while total_size > self.max_storage_bytes and files:
            oldest = files.pop(0)
            try:
                os.remove(oldest["path"])
                total_size -= oldest["size"]
                self.files_deleted += 1
                logger.info(
                    "Deleted old recording: %s (%.1f MB)",
                    os.path.basename(oldest["path"]),
                    oldest["size"] / (1024 * 1024),
                )
            except OSError as e:
                logger.error("Failed to delete %s: %s", oldest["path"], e)

        self.current_usage_mb = total_size / (1024 * 1024)
        self.files_count = len(files)

    def get_recordings(self) -> list[dict]:
        """
        Get list of all recordings with metadata.
        Returns list of dicts with: path, filename, size, size_mb, mtime, datetime.
        """
        from datetime import datetime

        files = self._get_recording_files()
        files.sort(key=lambda f: f["mtime"], reverse=True)

        result = []
        for f in files:
            result.append(
                {
                    "path": f["path"],
                    "filename": os.path.basename(f["path"]),
                    "size": f["size"],
                    "size_mb": f["size"] / (1024 * 1024),
                    "mtime": f["mtime"],
                    "datetime": datetime.fromtimestamp(f["mtime"]).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                }
            )
        return result

    def _get_recording_files(self) -> list[dict]:
        """Get all video files in the recordings folder."""
        video_extensions = {".mp4", ".avi", ".mkv", ".mov"}
        files = []

        if not os.path.exists(self.recordings_folder):
            return files

        for entry in os.scandir(self.recordings_folder):
            if entry.is_file():
                ext = os.path.splitext(entry.name)[1].lower()
                if ext in video_extensions:
                    stat = entry.stat()
                    files.append(
                        {
                            "path": entry.path,
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                        }
                    )
        return files

    def _monitor_loop(self):
        """Background loop that periodically checks storage."""
        while self._running:
            try:
                self.check_and_cleanup()
            except Exception as e:
                logger.error("Storage check error: %s", e)

            # Sleep in small intervals for responsive shutdown
            for _ in range(int(self.check_interval)):
                if not self._running:
                    break
                time.sleep(1)

    def update_max_storage(self, max_mb: float):
        """Update the maximum storage limit."""
        self.max_storage_mb = max_mb
        self.max_storage_bytes = max_mb * 1024 * 1024
        logger.info("Max storage updated to %.0f MB", max_mb)
        # Immediately check if we need to clean up
        self.check_and_cleanup()
