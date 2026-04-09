"""
Recording manager module.

Handles writing video segments when motion is detected.
Each recording gets a timestamped filename and is stored
in the configured output folder.
"""

import cv2
import os
import time
import threading
import logging
from datetime import datetime
from typing import Optional
from collections import deque

logger = logging.getLogger(__name__)


class RecordingManager:
    """
    Manages video recording triggered by motion detection.

    Features:
    - Pre-record buffer: keeps last N seconds of frames so the
      recording starts slightly before motion was detected.
    - Post-record: continues recording for N seconds after motion ends.
    - Segments recordings into files of configurable max duration.
    """

    def __init__(
        self,
        output_folder: str = "recordings",
        fps: float = 15.0,
        segment_duration: int = 60,
        pre_record_seconds: float = 5.0,
        post_record_seconds: float = 10.0,
        video_format: str = "mp4",
        frame_width: int = 1920,
        frame_height: int = 1080,
    ):
        self.output_folder = os.path.abspath(output_folder)
        self.fps = fps
        self.segment_duration = segment_duration
        self.pre_record_seconds = pre_record_seconds
        self.post_record_seconds = post_record_seconds
        self.video_format = video_format
        self.frame_width = frame_width
        self.frame_height = frame_height

        # Pre-record circular buffer
        buffer_size = int(self.fps * self.pre_record_seconds)
        self._pre_buffer: deque = deque(maxlen=max(buffer_size, 1))

        # Recording state
        self._recording = False
        self._writer: Optional[cv2.VideoWriter] = None
        self._current_file: Optional[str] = None
        self._segment_start: float = 0
        self._segment_frame_count: int = 0
        self._post_record_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

        # Stats
        self.total_recordings: int = 0
        self.current_recording_duration: float = 0

        # Accumulated zone labels for current recording session
        self._zone_labels: set[str] = set()

        # Ensure output folder exists
        os.makedirs(self.output_folder, exist_ok=True)

    @property
    def recording(self) -> bool:
        return self._recording

    @property
    def current_file(self) -> Optional[str]:
        return self._current_file

    def feed_frame(self, frame):
        """
        Feed a frame to the recording manager.
        If recording, writes to file. Otherwise, stores in pre-buffer.
        """
        if frame is None:
            return

        with self._lock:
            if self._recording:
                self._write_frame(frame)
            else:
                self._pre_buffer.append(frame.copy())

    def start_recording(self, zone_label: str = ""):
        """Start recording (called when motion is detected).

        Parameters
        ----------
        zone_label : str
            Optional label derived from triggered zone names.
            Zone names are accumulated across the recording session
            and all included in the final filename.
        """
        with self._lock:
            # Cancel any pending post-record stop
            if self._post_record_timer:
                self._post_record_timer.cancel()
                self._post_record_timer = None

            # Parse comma-separated zone names and add to the set
            if zone_label:
                for name in zone_label.split(', '):
                    name = name.strip()
                    if name:
                        self._zone_labels.add(name)

            if self._recording:
                # Already recording, check if we need a new segment
                elapsed = time.time() - self._segment_start
                if elapsed >= self.segment_duration:
                    self._finalize_segment()
                    self._start_new_segment()
                return

            logger.info("Starting recording...")
            self._start_new_segment()

            # Write pre-buffer frames
            pre_frames = list(self._pre_buffer)
            for f in pre_frames:
                self._write_frame(f)
            self._pre_buffer.clear()

            self._recording = True
            self.total_recordings += 1

    def stop_recording(self):
        """
        Signal that motion has ended.
        Continues recording for post_record_seconds then stops.
        """
        with self._lock:
            if not self._recording:
                return

            if self._post_record_timer:
                self._post_record_timer.cancel()

            self._post_record_timer = threading.Timer(
                self.post_record_seconds, self._do_stop_recording
            )
            self._post_record_timer.daemon = True
            self._post_record_timer.start()
            logger.info(
                "Motion ended, recording for %.1fs more...",
                self.post_record_seconds,
            )

    def force_stop(self):
        """Immediately stop recording."""
        with self._lock:
            if self._post_record_timer:
                self._post_record_timer.cancel()
                self._post_record_timer = None
            self._do_stop_internal()

    def _do_stop_recording(self):
        """Called after post-record timer expires."""
        with self._lock:
            self._do_stop_internal()

    def _do_stop_internal(self):
        """Internal stop without lock."""
        if self._writer:
            self._finalize_segment()
        self._recording = False
        self._current_file = None
        self._zone_labels.clear()
        logger.info("Recording stopped")

    def _start_new_segment(self):
        """Create a new video file for recording.

        Initially creates a temporary name; the final name with all
        accumulated zone labels is applied when the segment is finalized.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Use a temporary name; zone labels may still be accumulating
        filename = f"motion_{timestamp}.{self.video_format}"
        filepath = os.path.join(self.output_folder, filename)

        # Choose codec based on format
        if self.video_format == "mp4":
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        elif self.video_format == "avi":
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
        else:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")

        self._writer = cv2.VideoWriter(
            filepath, fourcc, self.fps, (self.frame_width, self.frame_height)
        )

        if not self._writer.isOpened():
            logger.error("Failed to create video writer for %s", filepath)
            self._writer = None
            return

        self._current_file = filepath
        self._segment_start = time.time()
        self._segment_frame_count = 0
        logger.info("New recording segment: %s", filename)

    def _write_frame(self, frame):
        """Write a single frame to the current segment."""
        if self._writer is None:
            return

        # Resize if needed
        h, w = frame.shape[:2]
        if w != self.frame_width or h != self.frame_height:
            frame = cv2.resize(frame, (self.frame_width, self.frame_height))

        self._writer.write(frame)
        self._segment_frame_count += 1
        self.current_recording_duration = time.time() - self._segment_start

        # Check segment duration
        if self.current_recording_duration >= self.segment_duration:
            self._finalize_segment()
            self._start_new_segment()

    def _finalize_segment(self):
        """Close the current video segment and rename with accumulated zone labels."""
        if self._writer:
            self._writer.release()
            self._writer = None

            old_path = self._current_file
            new_path = old_path

            # Rename to include zone labels now that we know all of them
            if self._zone_labels and old_path and os.path.exists(old_path):
                folder = os.path.dirname(old_path)
                base = os.path.splitext(os.path.basename(old_path))[0]
                ext = os.path.splitext(old_path)[1]
                sorted_labels = sorted(self._zone_labels)
                safe_label = self._sanitise_filename(', '.join(sorted_labels))
                new_name = f"{base}_{safe_label}{ext}"
                new_path = os.path.join(folder, new_name)
                try:
                    os.rename(old_path, new_path)
                    self._current_file = new_path
                    logger.info("Segment renamed to: %s", new_name)
                except OSError as e:
                    logger.warning("Could not rename segment: %s", e)

            logger.info(
                "Segment finalized: %s (%d frames, %.1fs)",
                self._current_file,
                self._segment_frame_count,
                self.current_recording_duration,
            )

    def update_resolution(self, width: int, height: int):
        """Update the recording resolution (call before recording starts)."""
        self.frame_width = width
        self.frame_height = height
        logger.info("Recording resolution set to %dx%d", width, height)

    def shutdown(self):
        """Clean shutdown of the recording manager."""
        self.force_stop()
        logger.info("Recording manager shut down")

    @staticmethod
    def _sanitise_filename(label: str) -> str:
        """Convert a zone label to a safe filename fragment."""
        import re
        # Replace spaces/special chars with underscores, strip leading/trailing
        safe = re.sub(r'[^\w\-]+', '_', label).strip('_')
        return safe[:60] if safe else "zone"
