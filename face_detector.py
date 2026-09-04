"""
face_detector.py -- Haar-cascade face detection, sized for a live pipeline.

Detection runs on a downscaled copy (``detect_width`` px wide) and the boxes
are scaled back to full resolution. On a 640x480 frame that is roughly a 4x
speed-up for no visible loss with a webcam-distance face.
"""
from __future__ import annotations

import cv2
import numpy as np

Box = tuple[int, int, int, int]        # x, y, w, h in full-resolution pixels


def default_cascade_path() -> str:
    """
    Locates the frontal face cascade that ships inside opencv-python, so nothing has to be vendored or downloaded.
    :return: str : Absolute path to haarcascade_frontalface_default.xml.
    """
    return cv2.data.haarcascades + "haarcascade_frontalface_default.xml"


class FaceDetector:
    """

    A class containing the logic related to face detection. Detection runs on a downscaled copy and the boxes are
    scaled back to full resolution, roughly a 4x speed-up on a 640x480 frame for no visible loss at webcam
    distance.

    """
    def __init__(self, cascade_path: str | None = None, detect_width: int = 320,
                 min_size: tuple[int, int] = (24, 24)):
        """
        Loads the Haar cascade.
        :param cascade_path: str/None : Path to a cascade XML, or None for the one bundled with OpenCV.
        :param detect_width: int : Frames wider than this are downscaled to it before detection.
        :param min_size: (int, int) : Smallest face to look for, in downscaled pixels.
        """
        self.cascade = cv2.CascadeClassifier(cascade_path or default_cascade_path())
        if self.cascade.empty():
            raise RuntimeError("could not load Haar cascade")
        self.detect_width = detect_width
        self.min_size = min_size

    def detect(self, img_bgr: np.ndarray) -> list[Box]:
        """
        A function which accepts an image and returns a bounding box for each face found within it.
        :param img_bgr: cv_mat : Input image, BGR.
        :return: list : One (x, y, w, h) tuple per face in full resolution pixels; empty list when none.
        """
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        scale = 1.0
        if gray.shape[1] > self.detect_width:
            scale = gray.shape[1] / self.detect_width
            gray = cv2.resize(gray, (self.detect_width, int(round(gray.shape[0] / scale))),
                              interpolation=cv2.INTER_AREA)
        gray = cv2.equalizeHist(gray)
        found = self.cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4,
                                              minSize=self.min_size)
        if len(found) == 0:
            return []
        return [tuple(int(round(v * scale)) for v in box) for box in found]

    @staticmethod
    def draw(img: np.ndarray, faces: list[Box], color=(0, 255, 0), thickness: int = 2) -> np.ndarray:
        """
        A function which draws a bounding box on each face, in place. Always returns the image, even when there are
        no faces.
        :param img: cv_mat : The image to draw on.
        :param faces: list : Boxes from detect().
        :param color: (int, int, int) : BGR rectangle colour.
        :param thickness: int : Rectangle line thickness in pixels.
        :return: cv_mat : The same image object, now with bounding boxes.
        """
        for (x, y, w, h) in faces:
            cv2.rectangle(img, (x, y), (x + w, y + h), color, thickness)
        return img

    @staticmethod
    def crops(gray: np.ndarray, faces: list[Box]) -> list[np.ndarray]:
        """
        A function which cuts the grayscale pixels inside each bounding box out as a sub-image. Rows are y, columns
        are x.
        :param gray: cv_mat : Grayscale image the boxes refer to.
        :param faces: list : Boxes from detect().
        :return: list : One cv_mat per face.
        """
        return [gray[y:y + h, x:x + w] for (x, y, w, h) in faces]
