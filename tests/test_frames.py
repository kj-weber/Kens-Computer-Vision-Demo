import numpy as np

from frames import FrameRing


def test_ring_roundtrip_and_overwrite_detection():
    ring = FrameRing((8, 6, 3), slots=3)
    try:
        reader = FrameRing.attach(ring.spec)
        try:
            frames = [np.full((8, 6, 3), i, np.uint8) for i in range(5)]
            for i, f in enumerate(frames):
                ring.write(f, i, 100.0 + i)
            # Slots hold ids 3, 4, 2 -> id 1 was lapped and must be rejected.
            assert reader.read(1) is None
            got, t = reader.read(4)
            assert t == 104.0 and np.array_equal(got, frames[4])
            got, _ = reader.read(2)
            assert np.array_equal(got, frames[2])
            got[:] = 0                                   # reader owns a copy
            assert np.array_equal(reader.read(2)[0], frames[2])
        finally:
            reader.close()
    finally:
        ring.close()
        ring.unlink()
