"""
calibration.py -- online intrinsic calibration from a printed checkerboard.

Show the demo a checkerboard (default: 9x6 inner corners, the standard OpenCV
pattern at https://github.com/opencv/opencv/blob/4.x/doc/pattern.png). The
calibrator collects views automatically whenever the board has moved enough
since the last accepted view, then solves for the camera matrix and
distortion coefficients and reports the RMS reprojection error in pixels.

Anything under ~0.5 px is a good webcam calibration; 1 px or more usually
means a warped print, motion blur, or too few tilted views.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

SUBPIX_CRITERIA = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)


@dataclass
class CalibrationResult:
    """

    The output of a calibration run: camera matrix, distortion coefficients, RMS reprojection error, image size and
    view count. JSON serialisable.

    """
    camera_matrix: list          # 3x3
    dist_coeffs: list            # k1 k2 p1 p2 k3
    rms_reprojection_px: float
    image_size: tuple            # (width, height)
    n_views: int

    @property
    def K(self) -> np.ndarray:
        """
        :return: numpy.ndarray : The 3x3 camera matrix as float64.
        """
        return np.asarray(self.camera_matrix, dtype=np.float64)

    @property
    def dist(self) -> np.ndarray:
        """
        :return: numpy.ndarray : The distortion coefficients (k1, k2, p1, p2, k3) as float64.
        """
        return np.asarray(self.dist_coeffs, dtype=np.float64)

    def save(self, path: Path) -> None:
        """
        Writes the result as JSON.
        :param path: Path : Destination file.
        :return: Nothing.
        """
        Path(path).write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: Path) -> "CalibrationResult":
        """
        Reads a result written by save().
        :param path: Path : Source file.
        :return: CalibrationResult : The loaded result.
        """
        d = json.loads(Path(path).read_text())
        d["image_size"] = tuple(d["image_size"])
        return cls(**d)

    def undistort_maps(self):
        """
        Pre-computes the remap tables for live undistortion at this result's image size.
        :return: (cv_mat, cv_mat) : map1, map2 for cv2.remap.
        """
        w, h = self.image_size
        new_K, _ = cv2.getOptimalNewCameraMatrix(self.K, self.dist, (w, h), alpha=0)
        return cv2.initUndistortRectifyMap(self.K, self.dist, None, new_K, (w, h), cv2.CV_16SC2)


class CheckerboardCalibrator:
    """

    Collects checkerboard views while the board moves, then solves for the intrinsics with cv2.calibrateCamera.
    Object points are laid out on the z=0 plane in metres.

    """
    def __init__(self, pattern_size=(9, 6), square_size_m: float = 0.025,
                 target_views: int = 15, min_motion_px: float = 20.0):
        """
        Prepares the object point grid for the board.
        :param pattern_size: (int, int) : Inner corners per row and per column, e.g. (9, 6).
        :param square_size_m: float : Side length of one square in metres.
        :param target_views: int : How many accepted views before calibrate() is allowed.
        :param min_motion_px: float : Mean corner displacement required since the last accepted view.
        """
        self.pattern_size = tuple(pattern_size)
        self.square_size_m = square_size_m
        self.target_views = target_views
        self.min_motion_px = min_motion_px
        cols, rows = self.pattern_size
        objp = np.zeros((cols * rows, 3), np.float32)
        objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * square_size_m
        self._objp = objp
        self.reset()

    def reset(self) -> None:
        """
        Discards every collected view.
        :return: Nothing.
        """
        self.object_points: list[np.ndarray] = []
        self.image_points: list[np.ndarray] = []
        self._last_accepted: np.ndarray | None = None

    @property
    def n_views(self) -> int:
        """
        :return: int : Number of views accepted so far.
        """
        return len(self.image_points)

    @property
    def complete(self) -> bool:
        """
        :return: bool : True once target_views have been accepted.
        """
        return self.n_views >= self.target_views

    def find_corners(self, gray: np.ndarray) -> np.ndarray | None:
        """
        Searches one grayscale frame for the board and refines the corners to sub-pixel accuracy.
        :param gray: cv_mat : Grayscale image.
        :return: numpy.ndarray/None : Corners of shape (N, 1, 2), or None if the board is not visible.
        """
        flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_FAST_CHECK
        ok, corners = cv2.findChessboardCorners(gray, self.pattern_size, flags=flags)
        if not ok:
            return None
        return cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), SUBPIX_CRITERIA)

    def maybe_add_view(self, corners: np.ndarray) -> bool:
        """
        Accepts a view only if the board has moved enough since the last accepted one, so fifteen near-identical
        frames cannot masquerade as fifteen views.
        :param corners: numpy.ndarray/None : Output of find_corners.
        :return: bool : True if the view was accepted.
        """
        if corners is None or self.complete:
            return False
        if self._last_accepted is not None:
            moved = float(np.mean(np.linalg.norm(corners - self._last_accepted, axis=2)))
            if moved < self.min_motion_px:
                return False
        self.object_points.append(self._objp.copy())
        self.image_points.append(corners)
        self._last_accepted = corners
        return True

    def calibrate(self, image_size: tuple[int, int]) -> CalibrationResult:
        """
        Solves for the intrinsics from the collected views.
        :param image_size: (int, int) : (width, height) of the frames the corners came from.
        :return: CalibrationResult : Camera matrix, distortion, RMS reprojection error.
        """
        rms, K, dist, _rvecs, _tvecs = cv2.calibrateCamera(
            self.object_points, self.image_points, tuple(image_size), None, None)
        return CalibrationResult(
            camera_matrix=K.tolist(),
            dist_coeffs=dist.ravel().tolist(),
            rms_reprojection_px=float(rms),
            image_size=tuple(int(v) for v in image_size),
            n_views=self.n_views,
        )


def render_synthetic_board(K: np.ndarray, dist: np.ndarray, rvec, tvec, image_size,
                           pattern_size=(9, 6), square_size_m=0.025):
    """
    Draws a checkerboard as seen by a camera with known intrinsics, so the test-suite can prove the calibrator
    recovers K and dist from images alone. (cols+1) x (rows+1) squares give cols x rows inner corners, on a white
    page.
    :param K: numpy.ndarray : 3x3 camera matrix.
    :param dist: numpy.ndarray : Distortion coefficients.
    :param rvec: numpy.ndarray : Board rotation (Rodrigues) in the camera frame.
    :param tvec: numpy.ndarray : Board translation in metres in the camera frame.
    :param image_size: (int, int) : (width, height) of the rendered image.
    :param pattern_size: (int, int) : Inner corners per row and per column.
    :param square_size_m: float : Side length of one square in metres.
    :return: cv_mat : Grayscale rendered image.
    """
    w, h = image_size
    cols, rows = pattern_size
    img = np.full((h, w), 255, np.uint8)
    # (cols+1) x (rows+1) squares give cols x rows inner corners; white page around.
    for r in range(-1, rows):
        for c in range(-1, cols):
            if (r + c) % 2:
                continue
            quad = np.array([[c, r, 0], [c + 1, r, 0], [c + 1, r + 1, 0], [c, r + 1, 0]],
                            np.float32) * square_size_m
            pts, _ = cv2.projectPoints(quad, rvec, tvec, K, dist)
            cv2.fillConvexPoly(img, np.round(pts.reshape(-1, 2) * 16).astype(np.int32), 0,
                               lineType=cv2.LINE_AA, shift=4)
    return img
