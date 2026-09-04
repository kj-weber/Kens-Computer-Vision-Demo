"""End-to-end: three processes, shared-memory ring, synthetic camera, no window."""
from steady_core import Config, run_demo


def test_headless_pipeline_reports_latency():
    stats = run_demo(Config(source="synthetic", headless=True, duration=2.5))
    assert stats.frames_displayed > 30
    assert stats.frames_detected > 10
    assert stats.display_latency_ms and max(stats.display_latency_ms) < 500
    assert stats.detect_latency_ms and min(stats.detect_latency_ms) > 0
