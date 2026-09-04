"""
steady_core.py -- the OS-independent camera pipeline.

Three processes, one shared-memory frame ring, and a few tiny queues:

    camera  --frames--> [FrameRing] <--copy-- feature (face detect, calibration)
      |                                  |
      +--FrameHeader--> ui  <--DetectionResult (boxes, corners, timings)--+
                        |
                        +--Command ('calibrate', 'reset')--> feature

* The camera process never waits on anyone: it writes the newest frame into
  the ring and announces its id. Announcements are dropped, not queued, when a
  consumer falls behind (``Queue(maxsize=...)`` + ``put_nowait``).
* The UI always displays the *newest camera frame* and overlays the *newest
  detection result*, so display rate is decoupled from detector rate and the
  video never freezes when detection is slow or finds nothing.
* Every frame carries its capture timestamp, so the UI can measure and report
  capture-to-display and capture-to-detection latency instead of guessing.

Timestamps use ``time.perf_counter()``, which is a system-wide clock on all
three supported platforms (QueryPerformanceCounter on Windows,
mach_absolute_time on macOS, CLOCK_MONOTONIC on Linux), so values taken in
different processes are directly comparable.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import platform
import queue
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
import cv2
import numpy as np

from calibration import CalibrationResult, CheckerboardCalibrator
from camera import open_source
from face_detector import FaceDetector
from frames import FrameHeader, FrameRing, RingSpec

WINDOW_NAME = "Kenneth's Computer Vision Demo"
CALIBRATION_FILE = Path(__file__).resolve().parent / "calibration.json"
RING_SLOTS = 4
QUEUE_DEPTH = 4


# --------------------------------------------------------------------------
# Configuration and messages
# --------------------------------------------------------------------------
@dataclass
class Config:
    """

    Everything the demo can be told from the command line, bundled so it can be handed to each process in one argument.

    """
    source: str = "auto"
    headless: bool = False
    duration: float | None = None          # seconds, None = until 'q'
    pattern_cols: int = 9
    pattern_rows: int = 6
    square_size_m: float = 0.025
    calibration_views: int = 15
    detect_width: int = 320
    report: str | None = None              # append a JSON line with the session summary here


@dataclass(frozen=True)
class DetectionResult:
    """

    The message the feature process sends to the UI for each frame it processed: face boxes, optional checkerboard
    corners, calibration progress, and timestamps for latency measurement. The solved calibration rides along
    exactly once.

    """
    frame_id: int
    t_capture: float
    t_done: float
    faces: list
    corners: np.ndarray | None = None
    calib_views: int = 0
    calib_active: bool = False
    calibration: CalibrationResult | None = None   # sent once when solved


@dataclass
class Stats:
    """

    Counters and latency samples gathered by the UI process and handed back to the parent at exit for the session
    summary.

    """
    source: str = ""
    frames_displayed: int = 0
    frames_detected: int = 0
    frames_dropped_by_ring: int = 0
    display_latency_ms: list = field(default_factory=list)   # capture -> just before imshow
    detect_latency_ms: list = field(default_factory=list)    # capture -> detection done
    result_age_frames: list = field(default_factory=list)    # how stale the boxes on screen were
    wall_seconds: float = 0.0
    calibration: CalibrationResult | None = None


def parse_args(argv) -> Config:
    """
    Parses the command line into a Config.
    :param argv: list : Arguments after the script name.
    :return: Config : The demo configuration.
    """
    p = argparse.ArgumentParser(description="Kenneth's live camera pipeline demo")
    p.add_argument("--source", default="auto",
                   help="'auto' (default), 'synthetic', a camera index, or a path to an image or video file")
    p.add_argument("--headless", action="store_true", help="no window; useful for tests and CI")
    p.add_argument("--duration", type=float, default=None, help="stop after N seconds")
    p.add_argument("--pattern", default="9x6", help="checkerboard inner corners, e.g. 9x6")
    p.add_argument("--square-size", type=float, default=0.025, help="checkerboard square size in metres")
    p.add_argument("--calibration-views", type=int, default=15)
    p.add_argument("--report", default=None, metavar="FILE",
                   help="append this session's summary as one JSON line to FILE (see BENCHMARKS.md)")
    a = p.parse_args(argv)
    cols, rows = (int(v) for v in a.pattern.lower().split("x"))
    return Config(source=a.source, headless=a.headless, duration=a.duration,
                  pattern_cols=cols, pattern_rows=rows, square_size_m=a.square_size,
                  calibration_views=a.calibration_views, report=a.report)


def _latest(q: mp.Queue, timeout: float):
    """
    A function which waits for one item and then drains the queue, so the caller always gets the newest value and
    never processes a backlog.
    :param q: multiprocessing.Queue : Any queue.
    :param timeout: float : Seconds to wait for the first item.
    :return: any/None : The newest item, or None if nothing arrived in time.
    """
    try:
        item = q.get(timeout=timeout)
    except queue.Empty:
        return None
    while True:
        try:
            item = q.get_nowait()
        except queue.Empty:
            return item


def _offer(q: mp.Queue, item) -> bool:
    """
    A non-blocking put which drops the item if the consumer is behind, so a slow process can never stall a fast one.
    :param q: multiprocessing.Queue : A bounded queue.
    :param item: any : The item to enqueue.
    :return: bool : True if enqueued, False if dropped.
    """
    try:
        q.put_nowait(item)
        return True
    except queue.Full:
        return False


# --------------------------------------------------------------------------
# Processes
# --------------------------------------------------------------------------
def camera_process(cfg: Config, ring_spec: RingSpec, announce_queues, stop: mp.Event):
    """
    The process which continuously reads the selected source and publishes every frame through the ring. It never
    waits on a consumer.
    :param cfg: Config : Demo configuration, used for the source spec.
    :param ring_spec: RingSpec : The ring to write into.
    :param announce_queues: list : One bounded queue per consumer to announce FrameHeaders on.
    :param stop: multiprocessing.Event : Set by anyone to end the demo.
    :return: Nothing. All I/O is handled by the ring and queues.
    """
    source, _desc = open_source(cfg.source)
    ring = FrameRing.attach(ring_spec)
    frame_id = 0
    try:
        while not stop.is_set():
            ok, frame = source.read()
            t_capture = time.perf_counter()
            if not ok or frame is None or frame.shape != ring.shape:
                if cfg.source not in ("auto", "synthetic") and not cfg.source.isdigit():
                    break                                  # video file ended
                time.sleep(0.005)
                continue
            ring.write(frame, frame_id, t_capture)
            header = FrameHeader(frame_id, t_capture)
            for q in announce_queues:
                _offer(q, header)
            frame_id += 1
    finally:
        source.release()
        ring.close()
        stop.set()


def feature_process(cfg: Config, ring_spec: RingSpec, frames_in: mp.Queue,
                    results_out: mp.Queue, commands_in: mp.Queue, stop: mp.Event):
    """
    The process which computes the entire feature logic: face detection on every frame it can get, and checkerboard
    collection plus calibration when the UI asks for it.
    :param cfg: Config : Demo configuration (detector width, board geometry).
    :param ring_spec: RingSpec : The ring to read frames from.
    :param frames_in: multiprocessing.Queue : FrameHeaders from the camera process.
    :param results_out: multiprocessing.Queue : DetectionResults to the UI process.
    :param commands_in: multiprocessing.Queue : 'calibrate' / 'reset' strings from the UI process.
    :param stop: multiprocessing.Event : Set by anyone to end the demo.
    :return: Nothing. All I/O is handled by the ring and queues.
    """
    ring = FrameRing.attach(ring_spec)
    detector = FaceDetector(detect_width=cfg.detect_width)
    calibrator = CheckerboardCalibrator((cfg.pattern_cols, cfg.pattern_rows),
                                        cfg.square_size_m, cfg.calibration_views)
    calib_active = False
    dropped = 0
    try:
        while not stop.is_set():
            while True:                                   # apply pending UI commands
                try:
                    cmd = commands_in.get_nowait()
                except queue.Empty:
                    break
                if cmd == "calibrate":
                    calib_active = not calib_active
                    if calib_active:
                        calibrator.reset()
                elif cmd == "reset":
                    calib_active = False
                    calibrator.reset()

            header = _latest(frames_in, timeout=0.2)
            if header is None:
                continue
            got = ring.read(header.frame_id)
            if got is None:
                dropped += 1
                continue
            frame, t_capture = got

            faces = detector.detect(frame)
            corners = None
            calibration = None
            if calib_active:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                corners = calibrator.find_corners(gray)
                if corners is not None:
                    calibrator.maybe_add_view(corners)
                if calibrator.complete:
                    h, w = gray.shape
                    calibration = calibrator.calibrate((w, h))
                    calibration.save(CALIBRATION_FILE)
                    calib_active = False

            result = DetectionResult(header.frame_id, t_capture, time.perf_counter(), faces,
                                     corners, calibrator.n_views, calib_active, calibration)
            _offer(results_out, result)
    finally:
        ring.close()
        _offer(results_out, ("dropped", dropped))


def ui_process(cfg: Config, ring_spec: RingSpec, frames_in: mp.Queue, results_in: mp.Queue,
               commands_out: mp.Queue, stats_out: mp.Queue, stop: mp.Event, source_desc: str):
    """
    The process which handles all UI logic: shows the newest camera frame with the newest detection overlaid, draws
    the HUD, handles keys, and records latency statistics.
    :param cfg: Config : Demo configuration.
    :param ring_spec: RingSpec : The ring to read frames from.
    :param frames_in: multiprocessing.Queue : FrameHeaders from the camera process.
    :param results_in: multiprocessing.Queue : DetectionResults from the feature process.
    :param commands_out: multiprocessing.Queue : Commands to the feature process.
    :param stats_out: multiprocessing.Queue : Where the final Stats object is placed for the parent.
    :param stop: multiprocessing.Event : Set by anyone to end the demo.
    :param source_desc: str : Human readable name of the source, for the summary.
    :return: Nothing. All I/O is handled by the ring and queues.
    """
    ring = FrameRing.attach(ring_spec)
    stats = Stats(source=source_desc)
    calibration = CalibrationResult.load(CALIBRATION_FILE) if CALIBRATION_FILE.exists() else None
    undistort = False
    maps = calibration.undistort_maps() if calibration else None
    last_result: DetectionResult | None = None
    t_start = time.perf_counter()
    disp_fps = det_fps = 0.0
    last_disp_t = last_det_id = None

    if not cfg.headless:
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)

    try:
        while not stop.is_set():
            if cfg.duration is not None and time.perf_counter() - t_start >= cfg.duration:
                break
            header = _latest(frames_in, timeout=0.5)
            if header is None:
                continue
            got = ring.read(header.frame_id)
            if got is None:
                stats.frames_dropped_by_ring += 1
                continue
            frame, t_capture = got

            # Newest detection result, if any arrived.
            while True:
                try:
                    item = results_in.get_nowait()
                except queue.Empty:
                    break
                if isinstance(item, DetectionResult):
                    last_result = item
                    stats.frames_detected += 1
                    stats.detect_latency_ms.append((item.t_done - item.t_capture) * 1000)
                    if item.calibration is not None:
                        calibration = item.calibration
                        maps = calibration.undistort_maps()
                        stats.calibration = calibration
                        print(f"[CALIBRATION] solved from {calibration.n_views} views: "
                              f"RMS reprojection error {calibration.rms_reprojection_px:.3f} px, "
                              f"saved to {CALIBRATION_FILE.name}", flush=True)
                elif isinstance(item, tuple) and item[0] == "dropped":
                    stats.frames_dropped_by_ring += item[1]

            if undistort and maps is not None:
                frame = cv2.remap(frame, maps[0], maps[1], cv2.INTER_LINEAR)

            now = time.perf_counter()
            disp_fps = _ema(disp_fps, 1.0 / (now - last_disp_t)) if last_disp_t else 0.0
            last_disp_t = now
            if last_result is not None and last_result.frame_id != last_det_id:
                if last_det_id is not None:
                    det_fps = _ema(det_fps, 1.0 / max(1e-6, (now - last_det_t)))
                last_det_t, last_det_id = now, last_result.frame_id

            _draw_overlay(frame, header, last_result, calibration, undistort, disp_fps, det_fps,
                          cfg, now - t_capture)
            stats.frames_displayed += 1
            stats.display_latency_ms.append((now - t_capture) * 1000)
            if last_result is not None:
                stats.result_age_frames.append(header.frame_id - last_result.frame_id)

            if cfg.headless:
                continue
            cv2.imshow(WINDOW_NAME, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:
                break
            if key == ord("c"):
                _offer(commands_out, "calibrate")
            if key == ord("r"):
                _offer(commands_out, "reset")
                calibration, maps, undistort = None, None, False
            if key == ord("u") and maps is not None:
                undistort = not undistort
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        stats.wall_seconds = time.perf_counter() - t_start
        stop.set()
        if not cfg.headless:
            cv2.destroyAllWindows()
        ring.close()
        stats_out.put(stats)


def _ema(prev: float, sample: float, alpha: float = 0.1) -> float:
    """
    Exponential moving average used to smooth the on-screen frame rates.
    :param prev: float : Previous average, 0.0 means uninitialised.
    :param sample: float : New sample.
    :param alpha: float : Smoothing factor, higher follows the sample faster.
    :return: float : Updated average.
    """
    return sample if prev == 0.0 else prev + alpha * (sample - prev)


def _draw_overlay(frame, header, result, calibration, undistort, disp_fps, det_fps, cfg, disp_latency_s):
    """
    Draws face boxes (green when fresh, amber when stale), checkerboard corners, and the HUD text onto the frame in
    place.
    :param frame: cv_mat : The frame about to be displayed.
    :param header: FrameHeader : Header of that frame.
    :param result: DetectionResult/None : Newest detection result.
    :param calibration: CalibrationResult/None : Current calibration, if any.
    :param undistort: bool : Whether undistortion is switched on.
    :param disp_fps: float : Smoothed display rate.
    :param det_fps: float : Smoothed detection rate.
    :param cfg: Config : Demo configuration, for the board geometry.
    :param disp_latency_s: float : Capture to display latency of this frame in seconds.
    :return: Nothing, the frame is modified in place.
    """
    if result is not None:
        age = header.frame_id - result.frame_id
        color = (0, 255, 0) if age <= 2 else (0, 200, 255)      # green fresh, amber stale
        FaceDetector.draw(frame, result.faces, color)
        if result.corners is not None:
            cv2.drawChessboardCorners(frame, (cfg.pattern_cols, cfg.pattern_rows), result.corners, True)

    lines = [f"display {disp_fps:5.1f} fps   capture->display {disp_latency_s * 1000:5.1f} ms"]
    if result is not None:
        lines.append(f"detect  {det_fps:5.1f} fps   capture->detect  "
                     f"{(result.t_done - result.t_capture) * 1000:5.1f} ms   faces {len(result.faces)}")
        if result.calib_active:
            lines.append(f"CALIBRATING: show the {cfg.pattern_cols}x{cfg.pattern_rows} checkerboard, "
                         f"views {result.calib_views}/{cfg.calibration_views}")
    if calibration is not None:
        K = calibration.K
        lines.append(f"calibrated: fx {K[0, 0]:.0f} fy {K[1, 1]:.0f}  RMS {calibration.rms_reprojection_px:.2f} px"
                     f"   undistort {'ON' if undistort else 'off'}")
    lines.append("keys: q quit   c calibrate   u undistort   r reset")
    y = 22
    for text in lines:
        cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        y += 22


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def _probe_shape(cfg: Config) -> tuple[tuple, str]:
    """
    Opens the source once in the parent to learn the frame shape the ring must be sized for.
    :param cfg: Config : Demo configuration, used for the source spec.
    :return: (tuple, str) : Frame shape and a human readable source description.
    """
    source, desc = open_source(cfg.source)
    try:
        for _ in range(10):
            ok, frame = source.read()
            if ok and frame is not None and frame.size:
                return frame.shape, desc
    finally:
        source.release()
    raise RuntimeError(f"source '{cfg.source}' produced no frames")


def run_demo(cfg: Config) -> Stats:
    """
    Creates the ring and queues, spins off the three processes, waits for the UI to finish, and prints the session
    summary.
    :param cfg: Config : Demo configuration.
    :return: Stats : The session statistics, also useful for tests.
    """
    print(f"[DEMO] probing source '{cfg.source}' ...", flush=True)
    shape, desc = _probe_shape(cfg)
    print(f"[DEMO] using {desc}, frame shape {shape}", flush=True)

    ctx = mp.get_context("spawn")            # identical behaviour on Windows, macOS, Linux
    ring = FrameRing(shape, slots=RING_SLOTS)
    stop = ctx.Event()
    cam_to_feature = ctx.Queue(QUEUE_DEPTH)
    cam_to_ui = ctx.Queue(QUEUE_DEPTH)
    feature_to_ui = ctx.Queue(QUEUE_DEPTH * 4)
    ui_to_feature = ctx.Queue(QUEUE_DEPTH)
    stats_q = ctx.Queue(1)

    procs = [
        ctx.Process(name="camera", target=camera_process,
                    args=(cfg, ring.spec, [cam_to_feature, cam_to_ui], stop)),
        ctx.Process(name="feature", target=feature_process,
                    args=(cfg, ring.spec, cam_to_feature, feature_to_ui, ui_to_feature, stop)),
        ctx.Process(name="ui", target=ui_process,
                    args=(cfg, ring.spec, cam_to_ui, feature_to_ui, ui_to_feature, stats_q, stop, desc)),
    ]
    stats = Stats(source=desc)
    try:
        for p in procs:
            p.start()
        while not stop.is_set():
            stop.wait(0.25)
            if not all(p.is_alive() for p in procs):
                stop.set()
        try:
            stats = stats_q.get(timeout=5)
        except queue.Empty:
            print("[DEMO] WARNING: UI process exited without reporting statistics", flush=True)
    except KeyboardInterrupt:
        stop.set()
    finally:
        for p in procs:
            p.join(timeout=3)
            if p.is_alive():
                p.terminate()
        ring.close()
        ring.unlink()
    print_summary(stats)
    if cfg.report:
        append_report(stats, Path(cfg.report))
    return stats


def summary_record(s: Stats) -> dict:
    """
    Flattens a Stats object plus the machine description into one JSON friendly dict, the unit of BENCHMARKS.md.
    :param s: Stats : Statistics returned by the UI process.
    :return: dict : Platform, versions, source, rates and latency percentiles.
    """
    def pct(values, q):
        return round(float(np.percentile(values, q)), 2) if values else None

    return {
        "date": time.strftime("%Y-%m-%d"),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "opencv": cv2.__version__,
        "source": s.source,
        "wall_s": round(s.wall_seconds, 1),
        "display_fps": round(s.frames_displayed / max(s.wall_seconds, 1e-6), 1),
        "detect_fps": round(s.frames_detected / max(s.wall_seconds, 1e-6), 1),
        "ring_overwrites": s.frames_dropped_by_ring,
        "capture_to_display_ms_p50": pct(s.display_latency_ms, 50),
        "capture_to_display_ms_p95": pct(s.display_latency_ms, 95),
        "capture_to_detect_ms_p50": pct(s.detect_latency_ms, 50),
        "capture_to_detect_ms_p95": pct(s.detect_latency_ms, 95),
        "calibration_rms_px": round(s.calibration.rms_reprojection_px, 3) if s.calibration else None,
    }


def append_report(s: Stats, path: Path) -> None:
    """
    Appends one JSON line describing this session, so runs on different machines can be compared over time.
    :param s: Stats : Statistics returned by the UI process.
    :param path: Path : File to append to, created if missing.
    :return: Nothing.
    """
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary_record(s)) + "\n")
    print(f"[DEMO] session summary appended to {path}", flush=True)


def print_summary(s: Stats) -> None:
    """
    Prints the end of session table of frame counts and latency percentiles.
    :param s: Stats : Statistics returned by the UI process.
    :return: Nothing.
    """
    def pct(values, q):
        return float(np.percentile(values, q)) if values else float("nan")

    print("\n[DEMO] ---- session summary ----")
    print(f"  source              : {s.source}")
    print(f"  wall time           : {s.wall_seconds:6.1f} s")
    print(f"  frames displayed    : {s.frames_displayed:6d}  ({s.frames_displayed / max(s.wall_seconds, 1e-6):.1f} fps)")
    print(f"  frames detected     : {s.frames_detected:6d}  ({s.frames_detected / max(s.wall_seconds, 1e-6):.1f} fps)")
    print(f"  ring overwrites     : {s.frames_dropped_by_ring:6d}")
    print(f"  capture->display    : median {pct(s.display_latency_ms, 50):5.1f} ms   p95 {pct(s.display_latency_ms, 95):5.1f} ms")
    print(f"  capture->detection  : median {pct(s.detect_latency_ms, 50):5.1f} ms   p95 {pct(s.detect_latency_ms, 95):5.1f} ms")
    print(f"  overlay staleness   : median {pct(s.result_age_frames, 50):.0f} frames  p95 {pct(s.result_age_frames, 95):.0f} frames")
    if s.calibration is not None:
        print(f"  calibration         : RMS {s.calibration.rms_reprojection_px:.3f} px from {s.calibration.n_views} views")
    print("[DEMO] Thank you for checking out the demo.\n")
