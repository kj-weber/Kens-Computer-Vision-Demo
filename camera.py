"""
camera.py -- finding, ranking, and opening frame sources.

``open_source("auto")`` probes the first few camera indices, keeps the ones
that actually deliver *changing* frames (a virtual camera that returns the
same image forever is not useful for a demo), and picks the one with the most
motion. If nothing usable is found it returns a ``SyntheticSource`` so the demo
still runs on a machine with no webcam.
"""
from __future__ import annotations

import math
import os
import sys
import time
from dataclasses import dataclass

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")   # must precede the cv2 import
import cv2
import numpy as np

MAX_PROBE_INDEX = 4
MAX_CONSECUTIVE_MISSES = 2   # camera indices are contiguous in practice; stop early to keep stderr quiet
LIVE_THRESHOLD = 0.3     # mean |diff| in 0..255 units; sensor noise alone is ~1
REQUEST_WIDTH, REQUEST_HEIGHT = 1280, 720   # most webcams deliver 30 fps at 720p but only ~15 fps at 1080p


@dataclass
class CameraInfo:
    """

    What the probe learned about one camera index: its frame shape and how much the picture changes over a fifth of
    a second.

    """
    index: int
    shape: tuple
    motion: float        # mean absolute frame difference over ~0.2 s


def _backend() -> int:
    # DirectShow opens far faster than Media Foundation on most Windows boxes.
    """
    Picks the VideoCapture backend per OS. DirectShow opens far faster than Media Foundation on most Windows boxes.
    :return: int : A cv2.CAP_* constant.
    """
    return cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY


def open_capture(index: int) -> cv2.VideoCapture:
    """
    Opens a camera by index with the OS appropriate backend.
    :param index: int : Camera index as understood by OpenCV.
    :return: cv2.VideoCapture : The capture object, possibly not opened.
    """
    cap = cv2.VideoCapture(index, _backend())
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, REQUEST_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, REQUEST_HEIGHT)
    return cap


def frame_motion(a: np.ndarray, b: np.ndarray) -> float:
    """
    Measures how different two frames are, channel aware and shape checked.
    :param a: cv_mat : The image taken at time t-1.
    :param b: cv_mat : The image taken at time t.
    :return: float : Mean absolute difference in 0..255 units, or NaN if the frames cannot be compared.
    """
    if a is None or b is None or a.shape != b.shape:
        return math.nan
    return float(np.mean(cv2.absdiff(a, b)))


def probe_cameras(max_index: int = MAX_PROBE_INDEX) -> list[CameraInfo]:
    """
    Robustly tries camera indices in turn and keeps those that deliver changing frames. Sensor noise alone gives
    about one grey level of motion on a real camera; a virtual camera returning a static image gives zero.
    :param max_index: int : Highest index to try, inclusive.
    :return: list : CameraInfo for every live camera found, possibly empty.
    """
    found = []
    misses = 0
    for index in range(max_index + 1):
        if misses >= MAX_CONSECUTIVE_MISSES:
            break
        cap = open_capture(index)
        try:
            if not cap.isOpened():
                misses += 1
                continue
            ok, first = cap.read()
            if not ok or first is None or first.size == 0:
                misses += 1
                continue
            misses = 0
            for _ in range(2):          # let auto-exposure settle
                cap.read()
            time.sleep(0.2)
            ok, second = cap.read()
            motion = frame_motion(first, second) if ok else math.nan
            if not math.isnan(motion) and motion > LIVE_THRESHOLD:
                found.append(CameraInfo(index, first.shape, motion))
        finally:
            cap.release()
    return found


def select_camera(cameras: list[CameraInfo]) -> CameraInfo | None:
    """
    Chooses the camera most likely to be looking at something interesting.
    :param cameras: list : CameraInfo entries from probe_cameras.
    :return: CameraInfo/None : The camera with the most motion, or None if the list is empty.
    """
    return max(cameras, key=lambda c: c.motion, default=None)


class SyntheticSource:
    """

    A generated moving scene with the same read()/release() API as cv2.VideoCapture, so the demo and the test-suite
    run on a machine with no webcam.

    """

    def __init__(self, width: int = 640, height: int = 480, fps: float = 30.0):
        """
        Creates the synthetic scene generator.
        :param width: int : Frame width in pixels.
        :param height: int : Frame height in pixels.
        :param fps: float : Frame rate to pace read() at.
        """
        self.width, self.height, self.fps = width, height, fps
        self._t0 = time.perf_counter()
        self._n = 0

    def isOpened(self) -> bool:  # noqa: N802 (VideoCapture naming)
        """
        Mirrors cv2.VideoCapture.isOpened.
        :return: bool : Always True.
        """
        return True

    def read(self):
        """
        Sleeps until the next frame is due, then draws a bouncing disc with a caption.
        :return: (bool, cv_mat) : (True, image), matching cv2.VideoCapture.read.
        """
        target = self._t0 + self._n / self.fps
        delay = target - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        self._n += 1
        img = np.full((self.height, self.width, 3), (40, 30, 30), np.uint8)
        phase = self._n / self.fps
        cx = int(self.width / 2 + 0.35 * self.width * math.sin(phase * 1.3))
        cy = int(self.height / 2 + 0.30 * self.height * math.cos(phase * 0.9))
        cv2.circle(img, (cx, cy), 60, (60, 200, 255), -1)
        cv2.putText(img, "No webcam found: synthetic source", (12, self.height - 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 230, 230), 1, cv2.LINE_AA)
        return True, img

    def release(self) -> None:
        """
        Mirrors cv2.VideoCapture.release. Nothing to free.
        :return: Nothing.
        """
        pass


class ImageSource:
    """

    Loops a still image as if it were a camera, with a one pixel wander so the liveness check and the latency
    numbers behave like a real source. Useful for a reliable detection demo with a photo of your own.

    """

    def __init__(self, path: str, fps: float = 30.0):
        """
        Loads the image once.
        :param path: str : Path to any image OpenCV can read.
        :param fps: float : Frame rate to pace read() at.
        """
        self.img = cv2.imread(path, cv2.IMREAD_COLOR)
        if self.img is None:
            raise FileNotFoundError(f"could not read image {path}")
        self.fps = fps
        self._t0 = time.perf_counter()
        self._n = 0

    def isOpened(self) -> bool:  # noqa: N802 (VideoCapture naming)
        """
        Mirrors cv2.VideoCapture.isOpened.
        :return: bool : Always True.
        """
        return True

    def read(self):
        """
        Sleeps until the next frame is due, then returns the image shifted by up to one pixel.
        :return: (bool, cv_mat) : (True, image), matching cv2.VideoCapture.read.
        """
        target = self._t0 + self._n / self.fps
        delay = target - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        self._n += 1
        dx, dy = (self._n % 2), ((self._n // 2) % 2)
        return True, np.roll(self.img, (dy, dx), axis=(0, 1))

    def release(self) -> None:
        """
        Mirrors cv2.VideoCapture.release. Nothing to free.
        :return: Nothing.
        """
        pass


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")


def open_source(spec: str):
    """
    Turns a command line source spec into something with read()/release().
    :param spec: str : 'auto' | 'synthetic' | a camera index such as '0' | a path to an image or video file.
    :return: (source, str) : The opened source and a human readable description of it.
    """
    if spec == "synthetic":
        return SyntheticSource(), "synthetic scene"
    if spec == "auto":
        cams = probe_cameras()
        chosen = select_camera(cams)
        if chosen is None:
            if sys.platform == "darwin":
                print("[CAMERA] No camera delivered frames. On macOS the camera permission belongs to "
                      "the app that launched Python (Terminal, PyCharm, VS Code ...): allow it under "
                      "System Settings > Privacy & Security > Camera, then re-run.", flush=True)
            return SyntheticSource(), "synthetic scene (no live camera found)"
        return open_capture(chosen.index), f"camera {chosen.index} {chosen.shape[1]}x{chosen.shape[0]}"
    if spec.isdigit():
        cap = open_capture(int(spec))
        return cap, f"camera {spec}"
    if spec.lower().endswith(IMAGE_EXTENSIONS):
        return ImageSource(spec), f"image file {spec}"
    cap = cv2.VideoCapture(spec)
    return cap, f"video file {spec}"
