# Benchmarks and verification

Every claim in the README about speed or platform support should have a row
here, with the command that produced it. Numbers are *software* latency as
defined in `DESIGN.md`: from `VideoCapture.read()` returning to just before
`imshow`, so sensor exposure and display scan-out are not included.

## Verification matrix

Last full pass: 2026-09-03, working tree at the "showcase refresh" change.

| check | macOS 15, Apple Silicon, Python 3.10.6 | Windows 11, Python 3.14.3 |
|---|---|---|
| `python main.py` from a clean checkout creates `.venv_ken/` and installs deps | pass | pass |
| second launch skips the download | pass | pass |
| `pytest` (6 tests, no hardware) | pass | pass |
| headless pipeline on the synthetic source | pass | pass |
| real webcam with window | pass (FaceTime HD, 1280x720) | not run (no interactive desktop over SSH) |
| calibration against a printed board | not yet run | not yet run |

## Latency

| date | platform | source | display fps | detect fps | capture->display p50 / p95 | capture->detect p50 / p95 | overwrites |
|---|---|---|---|---|---|---|---|
| 2026-09-03 | macOS, Apple Silicon, py3.10, cv 4.14 | synthetic 640x480 | 30.2 | 29.2 | 0.4 / 0.5 ms | 5.5 / 6.3 ms | 0 |
| 2026-09-03 | Windows 11, py3.14, cv 4.14 | synthetic 640x480 | 30.5 | 21.1 | 0.6 / 0.8 ms | 3.9 / 4.8 ms | 0 |
| 2026-09-03 | macOS, Apple Silicon, py3.10, cv 4.14 | FaceTime HD 1280x720, dark room | 13.6 | 13.4 | 1.5 / 3.7 ms | 15.9 / 24.3 ms | 0 |

The webcam row is camera-bound: in low light the driver stretches exposure to
about 70 ms, so it delivers roughly 14 fps and the pipeline reports exactly
that. Under normal lighting the same camera delivers 30 fps at 720p.

## How to add a row

Run the demo with `--report` and it appends one JSON line per session:

```bash
python main.py --headless --duration 10 --source synthetic --report benchmarks.jsonl
```

```bash
python main.py --duration 30 --report benchmarks.jsonl
```

Each line carries the date, OS, CPU architecture, Python and OpenCV
versions, source description, frame rates, latency percentiles, ring
overwrite count, and the calibration RMS if one was solved during the
session. `benchmarks.jsonl` is git-ignored; copy the interesting rows into
the tables above with the command that produced them.

Tests:

```bash
python -m pytest -q
```
