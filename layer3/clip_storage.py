import cv2
import os
import threading
import logging
import numpy as np
from datetime import datetime
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)


class ClipStorage:
    """
    Captures and saves video clips around alert events.

    Strategy — Ring Buffer:
        We keep the last N seconds of frames in memory (ring buffer).
        When an alert fires, we:
        1. Save the pre-alert frames (what happened before)
        2. Continue recording for post-alert seconds
        3. Write the complete clip to disk

    This ensures the clip shows WHAT LED TO the alert,
    not just what happened after.

    Also saves JPEG snapshots of individual alert frames.
    """

    def __init__(self, config: dict):
        cfg = config.get("storage", {})

        self.clips_dir     = cfg.get("clips_dir",     "data/clips")
        self.snapshots_dir = cfg.get("snapshots_dir", "data/snapshots")
        self.pre_seconds   = cfg.get("clip_pre_seconds",  5)
        self.post_seconds  = cfg.get("clip_post_seconds", 10)
        self.fps           = cfg.get("clip_fps",          15)
        self.enabled       = cfg.get("save_clips",       True)
        self.max_clips     = cfg.get("max_clips_stored", 500)
        self.jpeg_quality  = cfg.get("snapshot_quality",  85)

        os.makedirs(self.clips_dir,     exist_ok=True)
        os.makedirs(self.snapshots_dir, exist_ok=True)

        # Ring buffer: stores last pre_seconds * fps frames
        buffer_len        = int(self.pre_seconds * self.fps)
        self._ring_buffer : deque  = deque(maxlen=buffer_len)

        # Active clip recording state
        self._recording        = False
        self._post_frames_left = 0
        self._clip_frames      : list = []
        self._current_clip_path: Optional[str] = None
        self._clip_thread      : Optional[threading.Thread] = None

        self._frame_size = (1280, 720)  # updated on first frame

        logger.info(f"ClipStorage ready — clips: {self.clips_dir}")

    def update(self, frame: np.ndarray):
        """
        Add frame to ring buffer. Call every frame.
        Frame is only written to disk when save_clip() is called.
        """
        if not self.enabled:
            return

        h, w = frame.shape[:2]
        self._frame_size = (w, h)

        # Always feed ring buffer
        self._ring_buffer.append(frame.copy())

        # If actively recording post-alert frames
        if self._recording:
            self._clip_frames.append(frame.copy())
            self._post_frames_left -= 1

            if self._post_frames_left <= 0:
                self._recording = False
                # Write clip in background thread
                frames_to_write = list(self._clip_frames)
                path            = self._current_clip_path
                self._clip_frames = []
                self._clip_thread = threading.Thread(
                    target=self._write_clip,
                    args=(frames_to_write, path),
                    daemon=True
                )
                self._clip_thread.start()

    def save_clip(self, alert_type: str, camera_id: str = "cam_0") -> str:
        """
        Trigger clip save. Call when an alert fires.

        Returns:
            Path to the clip file being written.
        """
        if not self.enabled:
            return ""

        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_type = alert_type.replace(" ", "_").replace("/", "_")[:30]
        filename  = f"{camera_id}_{safe_type}_{ts}.avi"
        clip_path = os.path.join(self.clips_dir, filename)

        # Combine pre-buffer + start post-recording
        self._clip_frames      = list(self._ring_buffer)  # pre-alert frames
        self._recording        = True
        self._post_frames_left = int(self.post_seconds * self.fps)
        self._current_clip_path= clip_path

        logger.info(f"Clip recording started: {filename}")
        self._cleanup_old_clips()
        return clip_path

    def save_snapshot(self, frame: np.ndarray, alert_type: str,
                      camera_id: str = "cam_0") -> str:
        """
        Save a single JPEG frame snapshot of an alert moment.

        Returns:
            Path to the saved JPEG.
        """
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:20]
        safe_type = alert_type.replace(" ", "_").replace("/", "_")[:30]
        filename  = f"{camera_id}_{safe_type}_{ts}.jpg"
        path      = os.path.join(self.snapshots_dir, filename)

        encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
        cv2.imwrite(path, frame, encode_params)
        return path

    def _write_clip(self, frames: list, path: str):
        """Write frames to AVI file. Runs in background thread."""
        if not frames:
            return
        try:
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            writer = cv2.VideoWriter(path, fourcc, self.fps, self._frame_size)
            for f in frames:
                writer.write(f)
            writer.release()
            logger.info(f"Clip saved: {path} ({len(frames)} frames)")
        except Exception as e:
            logger.error(f"Failed to write clip {path}: {e}")

    def _cleanup_old_clips(self):
        """Delete oldest clips if over max_clips limit."""
        clips = sorted([
            os.path.join(self.clips_dir, f)
            for f in os.listdir(self.clips_dir)
            if f.endswith(".avi")
        ], key=os.path.getmtime)

        while len(clips) > self.max_clips:
            oldest = clips.pop(0)
            try:
                os.remove(oldest)
                logger.info(f"Old clip deleted: {oldest}")
            except OSError:
                pass

    def list_clips(self) -> list:
        """Return list of saved clip info dicts — for UI display."""
        clips = []
        for f in sorted(os.listdir(self.clips_dir), reverse=True):
            if f.endswith(".avi"):
                full_path = os.path.join(self.clips_dir, f)
                size_mb   = os.path.getsize(full_path) / (1024 * 1024)
                clips.append({
                    "filename" : f,
                    "path"     : full_path,
                    "size_mb"  : round(size_mb, 2),
                    "modified" : datetime.fromtimestamp(
                        os.path.getmtime(full_path)
                    ).strftime("%Y-%m-%d %H:%M")
                })
        return clips
