"""Prove the calibrator recovers known intrinsics from rendered checkerboards."""
import cv2
import numpy as np

from calibration import CalibrationResult, CheckerboardCalibrator, render_synthetic_board

IMAGE_SIZE = (640, 480)
K_TRUE = np.array([[600.0, 0, 320.0], [0, 600.0, 240.0], [0, 0, 1]])
DIST_TRUE = np.array([-0.25, 0.08, 0.001, -0.0005, 0.0])


def _poses(n=15, seed=3, margin=12):
    """Random board poses whose every corner lands inside the image."""
    rng = np.random.default_rng(seed)
    cal = CheckerboardCalibrator((9, 6), 0.025)
    w, h = IMAGE_SIZE
    produced = 0
    while produced < n:
        rvec = rng.uniform(-0.45, 0.45, 3)
        tvec = np.array([rng.uniform(-0.12, 0.0), rng.uniform(-0.09, 0.0), rng.uniform(0.35, 0.55)])
        pts, _ = cv2.projectPoints(cal._objp, rvec, tvec, K_TRUE, DIST_TRUE)
        x, y = pts[:, 0, 0], pts[:, 0, 1]
        if x.min() > margin and x.max() < w - margin and y.min() > margin and y.max() < h - margin:
            produced += 1
            yield rvec, tvec


def test_calibrator_recovers_intrinsics(tmp_path):
    cal = CheckerboardCalibrator((9, 6), 0.025, target_views=15, min_motion_px=5)
    for rvec, tvec in _poses():
        img = render_synthetic_board(K_TRUE, DIST_TRUE, rvec, tvec, IMAGE_SIZE)
        corners = cal.find_corners(img)
        assert corners is not None, "board not found in synthetic view"
        cal.maybe_add_view(corners)
    assert cal.complete
    result = cal.calibrate(IMAGE_SIZE)

    assert result.rms_reprojection_px < 0.15
    K = result.K
    assert abs(K[0, 0] - 600) < 3 and abs(K[1, 1] - 600) < 3
    assert abs(K[0, 2] - 320) < 3 and abs(K[1, 2] - 240) < 3
    assert abs(result.dist[0] - DIST_TRUE[0]) < 0.01

    path = tmp_path / "cal.json"
    result.save(path)
    loaded = CalibrationResult.load(path)
    assert loaded.n_views == 15 and loaded.image_size == IMAGE_SIZE
    maps = loaded.undistort_maps()
    assert maps[0].shape[:2] == (480, 640)


def test_rejects_views_that_have_not_moved():
    cal = CheckerboardCalibrator((9, 6), 0.025, target_views=5, min_motion_px=20)
    rvec, tvec = next(_poses())
    img = render_synthetic_board(K_TRUE, DIST_TRUE, rvec, tvec, IMAGE_SIZE)
    corners = cal.find_corners(img)
    assert cal.maybe_add_view(corners) is True
    assert cal.maybe_add_view(corners) is False
    assert cal.n_views == 1
