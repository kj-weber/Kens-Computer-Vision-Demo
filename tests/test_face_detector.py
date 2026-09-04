import numpy as np

from face_detector import FaceDetector


def test_no_faces_still_returns_image():
    """Regression: the old draw() returned None with zero faces, freezing the UI."""
    det = FaceDetector()
    blank = np.zeros((480, 640, 3), np.uint8)
    faces = det.detect(blank)
    assert faces == []
    out = FaceDetector.draw(blank, faces)
    assert out is blank


def test_crops_use_row_major_indexing():
    gray = np.arange(100 * 200, dtype=np.uint8).reshape(100, 200)
    (crop,) = FaceDetector.crops(gray, [(150, 10, 40, 20)])   # x=150 y=10 w=40 h=20
    assert crop.shape == (20, 40)
    assert np.array_equal(crop, gray[10:30, 150:190])
