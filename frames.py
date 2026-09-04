"""
frames.py -- zero-copy frame transport between processes.

A ``FrameRing`` is a fixed number of same-shaped image slots living in one
block of shared memory, plus a tiny header per slot (frame id and capture
timestamp). One writer (the camera process) writes frame ``k`` into slot
``k % slots``; any number of readers copy a slot out by frame id.

Why not ``multiprocessing.Queue``?  A queue pickles every frame: a 640x480
BGR image is ~0.9 MB, and copying that through a pipe for every consumer adds
milliseconds of latency and burns a CPU core. Here the pixels are written once
and each reader does a single ``memcpy`` into its own buffer.

Overwrite detection: a reader checks the slot's frame id before *and* after
copying. If the writer lapped it in between, ``read`` returns ``None`` and the
caller simply moves on to the newest frame.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from multiprocessing import shared_memory

import numpy as np

HEADER_DTYPE = np.dtype([("frame_id", "<i8"), ("t_capture", "<f8")])


@dataclass(frozen=True)
class FrameHeader:
    """

    The tiny message the camera process announces on a queue after writing a slot.
    Carries the frame id (which slot to read) and the capture timestamp (for latency measurement).

    """
    frame_id: int
    t_capture: float          # time.perf_counter() in the camera process


@dataclass(frozen=True)
class RingSpec:
    """

    Everything a child process needs to attach to a ring created by the parent: shared memory name, frame shape,
    dtype, and slot count.
    Picklable, so it can be passed as a Process argument.

    """
    name: str
    shape: tuple
    dtype: str
    slots: int


class FrameRing:
    """

    A fixed number of same-shaped image slots in one block of shared memory, plus a 16 byte header per slot.
    One writer (the camera process), any number of readers. Frame k lives in slot k % slots.

    """
    def __init__(self, shape, dtype=np.uint8, slots: int = 4, spec: RingSpec | None = None):
        """
        Creates a new ring (spec=None) or attaches to an existing one (spec given).
        :param shape: tuple : Frame shape, e.g. (480, 640, 3). Ignored when spec is given.
        :param dtype: numpy dtype : Pixel type, default uint8. Ignored when spec is given.
        :param slots: int : Number of frames the ring holds. Ignored when spec is given.
        :param spec: RingSpec/None : Attach to this existing ring instead of creating one.
        """
        self.shape = tuple(spec.shape) if spec else tuple(shape)
        self.dtype = np.dtype(spec.dtype if spec else dtype)
        self.slots = spec.slots if spec else slots
        self.frame_bytes = int(np.prod(self.shape)) * self.dtype.itemsize
        header_bytes = HEADER_DTYPE.itemsize * self.slots
        total = header_bytes + self.frame_bytes * self.slots

        if spec is None:
            self._shm = shared_memory.SharedMemory(create=True, size=total)
            self._owner = True
        else:
            self._shm = _attach(spec.name)
            self._owner = False

        buf = self._shm.buf
        self._headers = np.ndarray((self.slots,), dtype=HEADER_DTYPE, buffer=buf, offset=0)
        self._frames = np.ndarray((self.slots, *self.shape), dtype=self.dtype,
                                  buffer=buf, offset=header_bytes)
        if self._owner:
            self._headers["frame_id"] = -1

    # ---- lifecycle -------------------------------------------------------
    @property
    def spec(self) -> RingSpec:
        """
        Describes this ring so another process can attach to it.
        :return: RingSpec : Name, shape, dtype and slot count.
        """
        return RingSpec(self._shm.name, self.shape, self.dtype.str, self.slots)

    @classmethod
    def attach(cls, spec: RingSpec) -> "FrameRing":
        """
        Attaches to a ring created in another process.
        :param spec: RingSpec : As returned by FrameRing.spec in the owning process.
        :return: FrameRing : A reader view over the same memory.
        """
        return cls(None, spec=spec)

    def close(self) -> None:
        # Drop numpy views first: on Windows the buffer cannot be released
        # while exported views are alive.
        """
        Releases this process's mapping. Numpy views are dropped first because Windows refuses to close a buffer
        with live exports.
        :return: Nothing.
        """
        self._headers = None
        self._frames = None
        self._shm.close()

    def unlink(self) -> None:
        """
        Destroys the shared memory segment. Only the creating process does anything here.
        :return: Nothing.
        """
        if self._owner:
            self._shm.unlink()

    # ---- data path -------------------------------------------------------
    def write(self, frame: np.ndarray, frame_id: int, t_capture: float) -> int:
        """
        Writes a frame into slot frame_id % slots. The slot id is set to -1 while the pixels are being copied, so a
        concurrent reader can tell the slot is in flight.
        :param frame: numpy.ndarray : Image with exactly the ring's shape and dtype.
        :param frame_id: int : Monotonically increasing frame counter.
        :param t_capture: float : time.perf_counter() taken right after the camera returned the frame.
        :return: int : The slot index written.
        """
        slot = frame_id % self.slots
        self._headers[slot]["frame_id"] = -1        # mark slot as in-flight
        np.copyto(self._frames[slot], frame, casting="no")
        self._headers[slot] = (frame_id, t_capture)
        return slot

    def read(self, frame_id: int) -> tuple[np.ndarray, float] | None:
        """
        Copies a frame out of the ring by id, checking the slot id before and after the copy to detect being lapped
        by the writer.
        :param frame_id: int : The id announced in a FrameHeader.
        :return: (numpy.ndarray, float)/None : A private copy of the frame and its capture time, or None if the
            writer overwrote the slot.
        """
        slot = frame_id % self.slots
        if int(self._headers[slot]["frame_id"]) != frame_id:
            return None
        t_capture = float(self._headers[slot]["t_capture"])
        out = self._frames[slot].copy()
        if int(self._headers[slot]["frame_id"]) != frame_id:
            return None                              # writer lapped us mid-copy
        return out, t_capture


def _attach(name: str) -> shared_memory.SharedMemory:
    """
    Attaches to shared memory without registering it with the resource tracker. Before Python 3.13 every attaching
    process registers the segment and then warns about a leak at exit even though the owner unlinks it.
    :param name: str : Shared memory segment name.
    :return: multiprocessing.shared_memory.SharedMemory : The attached segment.
    """
    if sys.version_info >= (3, 13):
        return shared_memory.SharedMemory(name=name, track=False)
    if sys.platform == "win32":
        return shared_memory.SharedMemory(name=name)
    from multiprocessing import resource_tracker
    original = resource_tracker.register

    def skip_shared_memory(rname, rtype):
        if rtype != "shared_memory":
            original(rname, rtype)

    resource_tracker.register = skip_shared_memory
    try:
        return shared_memory.SharedMemory(name=name)
    finally:
        resource_tracker.register = original
