# Design notes

This document explains *why* the demo is built the way it is, what its
failure modes are, and what I would change for a production camera stack.
The code itself is short (about 700 lines); this is the reasoning behind it.

## Goals

1. A stranger with a stock Windows or macOS machine runs one command and sees
   a live camera pipeline. No Docker, no conda, no "first install X".
2. The pipeline is shaped like a real camera stack: capture, compute, and
   display are separate processes with well-defined hand-offs, and every
   frame carries a timestamp so latency is *measured*, not guessed.
3. Every component is testable without hardware.

## Process layout

```
             +-----------+   FrameRing (shared memory, 4 slots)   +-----------+
  webcam --> |  camera   | ======================================> |  feature  |  Haar face detect,
             |  process  |   FrameHeader (id, t_capture) queue    |  process  |  checkerboard calib
             +-----------+ --------------------------------------> +-----------+
                   |                                                    |
                   |  FrameHeader queue           DetectionResult queue |
                   v                                                    v
             +---------------------------------------------------------------+
             |  ui process: newest frame + newest result, HUD, keys, stats    |
             +---------------------------------------------------------------+
                                        |  Command queue ('calibrate', 'reset')
                                        +--> feature process
```

**Why processes and not threads.** OpenCV releases the GIL inside most calls,
so threads would mostly work, but a process boundary makes the coupling
explicit: the only things that cross it are the ring, four small queues, and
one `Event`. It is also the shape you get in a real system where capture,
ISP/perception, and display live in different address spaces (or on
different SoCs), so the demo exercises the same discipline.

**Why `spawn` on every platform.** Windows only supports spawn; macOS has
defaulted to it since 3.8 because `fork` breaks Cocoa/AVFoundation. Forcing it
everywhere means one code path and one set of bugs.

## Frame transport

Frames go through `frames.FrameRing`: a fixed number of same-shaped slots in
one `multiprocessing.shared_memory` block, each with an 16-byte header
(`frame_id`, `t_capture`). The camera writes frame *k* into slot *k mod N* and
announces the id on two tiny bounded queues. Consumers copy the slot out.

The earlier version of this demo pickled every frame through a
`multiprocessing.Queue`, twice. That is a ~1 MB copy per consumer per frame,
serialised through a pipe. Latency was "removed" by draining queues, which is
treating the symptom. The ring costs one `memcpy` per consumer and has no
queueing behaviour at all.

**Overwrite race.** A slow reader can be lapped by the writer. The writer
marks a slot's id as `-1` before writing and sets the real id after; the
reader checks the id before *and* after its copy and returns `None` on any
mismatch. That is a seqlock without the sequence counter, and it is enough
because readers always want the newest frame anyway. Ring overwrites are
counted and printed in the session summary; on the machines I have tested
the count is zero, because the consumers are faster than 30 fps.

**Memory ordering.** Python does not expose acquire/release semantics.
Between the GIL, the interpreter's own locking, and x86/ARM ordering rules the
header write is observed after the pixel write in practice, but a production
implementation would use a proper sequence counter with atomics (or a
platform frame-buffer API). This is the biggest "demo-grade" corner I know of.

## Latency measurement

Every header carries `time.perf_counter()` taken immediately after
`VideoCapture.read()` returns. The UI records:

* **capture->display**: from that timestamp to just before `imshow`.
  Excludes sensor exposure, driver buffering, and the display's own scan-out,
  so this is *software* latency; end-to-end "glass to glass" needs an external
  reference such as a photodiode or a phone camera filming the screen.
* **capture->detection**: from capture to the detector publishing its result.
* **overlay staleness**: how many frames old the boxes on screen are.

`perf_counter` is system-wide on all three supported platforms (QPC on
Windows, `mach_absolute_time` on macOS, `CLOCK_MONOTONIC` on Linux), so values
taken in different processes are comparable.

## Display never waits for detection

The UI shows the newest camera frame and overlays the newest detection
result, colouring the boxes amber when they are more than two frames old.
Detection can run at any rate, or find nothing, without stalling video.
(The first version of this demo displayed the detector's *output* image, and
returned `None` when no face was found, so the video froze whenever you left
the frame.)

## Camera selection

`camera.probe_cameras` opens indices 0..4, discards any that do not deliver
frames, and measures mean absolute difference between two frames 0.2 s apart.
Sensor noise alone gives ~1 grey level on a real camera; a virtual camera
returning a static image gives 0. The source with the most motion wins. If
nothing qualifies the demo runs on a generated scene so the pipeline is still
demonstrable on a machine with no webcam (and in CI).

## Calibration

`calibration.CheckerboardCalibrator` collects checkerboard views while the
board moves (mean corner displacement > 20 px since the last accepted view),
refines corners to sub-pixel, and calls `cv2.calibrateCamera`. The result
(camera matrix, five distortion coefficients, RMS reprojection error, image
size) is saved to `calibration.json` and the UI can toggle live undistortion.

The test-suite renders checkerboards from *known* intrinsics with
`cv2.projectPoints`, runs the calibrator on the rendered images, and asserts
that focal length and principal point are recovered within 3 px and RMS
reprojection is under 0.15 px. That proves the maths and the plumbing without
a printed board or a camera.

## Environment bootstrap

`core.py` creates `.venv_ken/` inside the project, installs the pinned
requirements into it once (a hash of `requirements.txt` is stamped into the
venv so re-launches are instant and work offline), and re-executes `main.py`
under that interpreter with an environment flag so the child knows not to
bootstrap again. Nothing outside the folder is modified.

The previous version ran `pip-review --auto` against the visitor's global
Python on Windows, which upgrades every package they own. That is exactly the
kind of side effect a "just run it" demo must never have.

## Known limitations

* Haar cascades are 2001-era technology: frontal faces only, sensitive to
  lighting. They are here because they ship inside `opencv-python` and need
  no model download. A modern replacement would be a small ONNX detector
  (e.g. YuNet, also shipped with OpenCV) run through `cv2.FaceDetectorYN`.
* `imshow` is a debugging window, not a UI toolkit. Window sizing, DPI
  scaling and menus are all absent by design.
* No frame-rate control: the camera process runs as fast as the driver
  delivers, which is what you want for latency but not for power.
* One writer only. Multiple cameras would need one ring each plus a
  synchroniser keyed on capture timestamps.

## What I would change for production

* Replace the ring's ad-hoc overwrite check with a real seqlock or, better,
  hand frames around as DMA-BUF / IOSurface handles and never copy pixels.
* Move detection to a model with a known latency budget and quantise it for
  the target NPU; report p99, not just p95.
* Timestamp at the sensor (V4L2 / AVFoundation give hardware timestamps) so
  driver buffering is inside the measurement, then close the loop with a
  glass-to-glass rig.
* Package as a signed app bundle / MSIX so the camera permission prompt is
  attributed to the demo rather than to Terminal.
