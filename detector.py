"""
Frame classification: given a BGR frame (numpy array from OpenCV), decide
whether it's 'ok' or 'black'. Kept separate from capture so it can be unit
tested with synthetic frames, and reused identically for both RTSP live
polling and recorded-file backtesting.
"""

import cv2
import numpy as np

from config import BRIGHTNESS_THRESHOLD, STD_DEV_THRESHOLD


def classify_frame(frame: np.ndarray) -> dict:
    """
    Returns {"status": "ok" | "black", "mean_brightness": float, "std_dev": float}
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean, std = cv2.meanStdDev(gray)
    mean = float(mean[0][0])
    std = float(std[0][0])
    
    is_black = mean < BRIGHTNESS_THRESHOLD and std < STD_DEV_THRESHOLD
    print(f"mean: {mean}, std: {std} -> {'black' if is_black else 'ok'}")
    return {
        "status": "black" if is_black else "ok",
        "mean_brightness": round(mean, 2),
        "std_dev": round(std, 2),
    }
