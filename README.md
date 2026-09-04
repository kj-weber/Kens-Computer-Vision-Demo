# Kenneth's Computer Vision Demo

A live camera pipeline you can run on a stock Windows or macOS machine with
one command. It exists to show, in a few hundred lines you can read in an
afternoon, how I think about camera software: process boundaries, zero-copy
frame transport, measured latency, and a calibration step that is tested
against ground truth.

**About me.** I am a mechatronics engineer who spent five-plus years at
General Motors writing Python and C++ that extracted information from the
rear-view camera and fused it with other vehicle sensors, and I have been at
Apple since 2023. This repository is a sandbox, not a product: the point is
the pipeline shape and the engineering discipline around it, not the face
detector.

> **Privacy.** This software opens your webcam. The video never leaves your
> machine: nothing is saved, uploaded, or broadcast. The whole data path is in
> `steady_core.py` and `frames.py` if you want to check.

## Run it

```bash
git clone https://github.com/kj-weber/Kens-Computer-Vision-Demo.git
cd Kens-Computer-Vision-Demo
python main.py
```

That is the entire setup. `main.py` creates a private virtual environment
inside the folder, installs the two pinned dependencies (NumPy, OpenCV) into
it on the first run, and launches the demo under it. Nothing outside the
folder is touched; delete `.venv_ken/` to uninstall. Repeat launches skip the
download and work offline.

Requirements: Python 3.9 or newer from python.org (or the Microsoft Store).
Tested on macOS (Apple Silicon, Python 3.10) and Windows 11 (Python 3.14).

* **macOS:** the camera permission belongs to whatever launched Python
  (Terminal, PyCharm, VS Code). Click *Allow* when asked, or enable it under
  *System Settings > Privacy & Security > Camera* and re-run.
* **No webcam, or a dark room?** The demo detects a missing camera and runs on
  a generated scene, so the pipeline and the numbers still work. For a
  reliable face-detection demo anywhere, loop a photo of your own through the
  full pipeline: `python main.py --source path/to/photo.jpg`.

Keys while running:

| key | action |
|---|---|
| `q` / `Esc` | quit and print the session summary |
| `c` | start collecting checkerboard views for calibration |
| `u` | toggle live undistortion once calibrated |
| `r` | discard the calibration |

## What you are looking at

Three processes and one shared-memory frame ring:

```
webcam -> camera process ==[FrameRing]==> feature process (face detection, calibration)
              |                                  |
              +------ frame headers -----> ui process <--- detection results
```

* The camera process never waits on anyone. It writes each frame into a
  4-slot shared-memory ring and announces the frame id; slow consumers get
  lapped, not queued.
* The UI always shows the **newest camera frame** with the **newest detection
  result** drawn over it, so display rate is decoupled from detector rate and
  the video never freezes.
* Every frame carries its capture timestamp, so the HUD and the end-of-session
  summary report real latency numbers rather than a frame rate.

Session summaries from the machines above. The first two columns use the
640x480 synthetic source; the third is the built-in FaceTime camera at
1280x720 in a dark room, where the driver drops to about 14 fps because of
long exposures, which the pipeline correctly reports rather than hides:

| | macOS, synthetic | Windows 11, synthetic | macOS, webcam 720p |
|---|---|---|---|
| display rate | 30.2 fps | 30.4 fps | 13.6 fps (camera-bound) |
| capture to display (median / p95) | 0.4 / 0.5 ms | 0.5 / 0.8 ms | 1.5 / 3.7 ms |
| capture to detection (median / p95) | 5.5 / 6.3 ms | 4.0 / 4.8 ms | 15.9 / 24.3 ms |
| ring overwrites | 0 | 0 | 0 |

`DESIGN.md` explains the choices, the failure modes, and what I would change
for a production camera stack. `BENCHMARKS.md` holds the per-platform
verification matrix and every measured number with the command that produced
it; run with `--report benchmarks.jsonl` to add your own machine.

## Calibration

Print the standard OpenCV 9x6 checkerboard
(<https://github.com/opencv/opencv/blob/4.x/doc/pattern.png>), press `c`,
and move the board around the frame at a few angles. After 15 distinct views
the demo solves for the camera matrix and distortion coefficients, prints the
RMS reprojection error, saves `calibration.json`, and lets you toggle
undistortion with `u`. Under 0.5 px is a good webcam calibration.

The calibrator is verified in the test-suite against synthetic boards
rendered from known intrinsics: focal length and principal point are recovered
within 3 px and reprojection error is under 0.15 px.

Other board sizes: `python main.py --pattern 7x5 --square-size 0.03`.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

Six tests, no hardware needed: the shared-memory ring including the
overwrite race, the detector's no-face path, image-indexing order, the
calibrator against ground truth, and the full three-process pipeline running
headless on the synthetic source.

## Layout

| file | role |
|---|---|
| `main.py` | the only entry point |
| `core.py` | zero-configuration environment bootstrap (venv + pinned deps) |
| `steady_core.py` | the OS-independent pipeline: three processes and the HUD |
| `frames.py` | shared-memory frame ring with overwrite detection |
| `camera.py` | camera probing, liveness ranking, synthetic fallback |
| `face_detector.py` | Haar-cascade detection on a downscaled frame |
| `calibration.py` | checkerboard intrinsic calibration and undistortion |
| `tests/` | pytest suite |

## Writing

The accompanying series starts with
[Writing a Python Desktop Demo, Part 1](https://medium.com/@kenneth.weber1/writing-a-python-desktop-demo-computer-vision-part-1-intro-00d2f5692ee1).

## License

MIT, see `LICENSE`.
