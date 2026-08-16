"""
Source-agnostic frame grabber. Same interface whether you point it at a
live RTSP stream or a recorded video file -- this is what lets you run the
exact same detector logic in two modes:

  - live monitoring : poll an RTSP URL every POLL_INTERVAL_SEC
  - backtest / audit : walk through an already-recorded file (or folder of
                        files exported from the NVR) and classify every
                        sampled frame, so you can retroactively find how
                        much of yesterday a channel was black, or validate
                        the detector against footage you already know is bad.
"""

import time
import cv2

from config import RTSP_OPEN_TIMEOUT_MS, RTSP_READ_RETRIES


def is_rtsp(source: str) -> bool:
    return source.strip().lower().startswith("rtsp://")


def grab_single_frame(source: str):
    """
    Open `source` (RTSP URL or file path), grab one frame, release.
    Returns (frame or None, error or None).
    Used for live polling -- one short-lived connection per check keeps
    the monitor resilient (a hung stream can't wedge the whole process).
    """
    cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
    if is_rtsp(source):
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, RTSP_OPEN_TIMEOUT_MS)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, RTSP_OPEN_TIMEOUT_MS)

    if not cap.isOpened():
        cap.release()
        return None, "connection_failed"

    frame = None
    err = None
    for attempt in range(RTSP_READ_RETRIES + 1):
        ok, frame = cap.read()
        if ok and frame is not None:
            err = None
            break
        err = "read_failed"
        time.sleep(0.3)

    cap.release()
    return (frame, None) if err is None else (None, err)


def iter_file_frames(path: str, sample_every_sec: float = 5.0):
    """
    Generator for backtest mode: walks a recorded video file, yielding
    (timestamp_offset_sec, frame) sampled every `sample_every_sec` seconds
    instead of every single frame (a 5-min clip at 25fps is 7500 frames --
    no need to classify all of them).
    """
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_interval = max(1, int(fps * sample_every_sec))

    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % frame_interval == 0:
            yield frame_idx / fps, frame
        frame_idx += 1

    cap.release()
