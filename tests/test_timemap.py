"""P0-02 TimeMap: source_frame ↔ clip_frame ↔ timeline_frame mapping tests."""
from __future__ import annotations

from fractions import Fraction

from yroll.core.manifest import Clip, TimeRange
from yroll.core.timebase import FrameRange, FrameTime, Rational
from yroll.core.timemap import TimeMap


FPS_30 = Rational(30, 1)
FPS_24 = Rational(24, 1)
FPS_2997 = Rational(30000, 1001)


def _make_clip(sr=TimeRange(start=0.0, end=10.0),
               tr=TimeRange(start=5.0, end=15.0),
               speed=1.0) -> Clip:
    return Clip(
        clip_id="c1", asset_id="a1",
        source_range=sr, timeline_range=tr, speed=speed,
    )


# ---------- Source ↔ Clip Local ----------

def test_clip_from_source_normal():
    tm = TimeMap.for_clip(_make_clip(), FPS_30)
    assert tm.clip_from_source(0) == 0
    assert tm.clip_from_source(150) == 150   # mid-clip
    assert tm.clip_from_source(299) == 299   # last frame


def test_clip_from_source_clamps():
    tm = TimeMap.for_clip(_make_clip(), FPS_30)
    assert tm.clip_from_source(-5) == 0     # below start → 0
    assert tm.clip_from_source(999) == 299  # past end → clamped to last


def test_source_from_clip():
    tm = TimeMap.for_clip(_make_clip(), FPS_30)
    assert tm.source_from_clip(0) == 0
    assert tm.source_from_clip(150) == 150
    assert tm.source_from_clip(-5) == 0     # negative clamps


# ---------- Clip Local ↔ Timeline ----------

def test_timeline_from_clip_normal():
    # timeline_start=5.0s @ 30fps = 150 frames, no speed change
    tm = TimeMap.for_clip(_make_clip(), FPS_30)
    assert tm.timeline_from_clip(0) == 150
    assert tm.timeline_from_clip(150) == 300


def test_timeline_from_clip_speed_2x():
    # 300 source frames @ 2x = 150 timeline frames (so 300 clip-frames map to 150 tl-frames)
    tm = TimeMap.for_clip(_make_clip(speed=2.0), FPS_30)
    assert tm.timeline_from_clip(0) == 150
    assert tm.timeline_from_clip(150) == 225  # 150 clip / 2 = 75 + 150 tl = 225


def test_clip_from_timeline_roundtrip():
    tm = TimeMap.for_clip(_make_clip(), FPS_30)
    for cf in (0, 50, 100, 200, 299):
        tl = tm.timeline_from_clip(cf)
        assert tm.clip_from_timeline(tl) == cf, f"roundtrip failed at clip={cf}"


# ---------- Source ↔ Timeline (the Agent-facing mapping) ----------

def test_timeline_from_source_matches_inline_calc():
    """The Agent asks: 'source frame X is at what timeline frame?'
    Must match the old inline calculation (s - sr.start) / speed + tr.start.
    """
    clip = _make_clip(sr=TimeRange(start=2.0, end=8.0),
                      tr=TimeRange(start=10.0, end=16.0),
                      speed=1.5)
    tm = TimeMap.for_clip(clip, FPS_30)
    # source frame 60 (= 2.0s, first valid frame) → timeline frame 300 (= 10.0s)
    assert tm.timeline_from_source(60) == 300
    # mid: 150 source (= 5.0s, clip-local=90) → tl = 10 + 90/1.5 = 70.0s wait...
    # Actually: 90 clip-frames @ 1.5x = 60 timeline-frames past start.
    # timeline = 300 + 60 = 360 (= 12.0s on timeline)
    assert tm.timeline_from_source(150) == 360


def test_source_from_timeline_roundtrip():
    tm = TimeMap.for_clip(_make_clip(speed=2.0), FPS_30)
    # roundtrip across speed-affected timeline (2x): use valid interior frames
    for sf in (0, 60, 150, 200, 250):
        tl = tm.timeline_from_source(sf)
        assert tm.source_from_timeline(tl) == sf


# ---------- FrameRange mapping (used by ASR/subtitle mapping) ----------

def test_source_range_to_timeline_range():
    """ASR word source frames 60..90 → timeline frame range."""
    tm = TimeMap.for_clip(_make_clip(sr=TimeRange(start=2.0, end=8.0),
                                     tr=TimeRange(start=10.0, end=16.0),
                                     speed=1.0), FPS_30)
    # Half-open: source [60, 90) = 30 frames @ 1.0x = 30 timeline frames
    # Timeline starts at 300 (source frame 60), so end = 300 + 30 = 330
    src = FrameRange(60, 90, FPS_30)
    tl = tm.timeline_from_source_range(src)
    assert tl.start_frame == 300
    assert tl.end_frame == 330
    assert tl.duration_frames == 30


def test_speed_clip_keeps_half_open():
    """Speed change must preserve half-open semantics on FrameRange."""
    tm = TimeMap.for_clip(_make_clip(sr=TimeRange(start=0.0, end=10.0),
                                     tr=TimeRange(start=0.0, end=20.0),
                                     speed=0.5), FPS_30)
    # FrameRange(0, 300) half-open [0, 300) = 300 frames
    # At 0.5x speed: 300 source frames span 600 timeline frames (2x duration)
    # Mapped range: half-open [0, 600) = 600 frames → end_frame=600
    src = FrameRange(0, 300, FPS_30)
    tl = tm.timeline_from_source_range(src)
    assert tl.start_frame == 0
    assert tl.end_frame == 600
    assert tl.duration_frames == 600


# ---------- Different FPS ----------

def test_24fps_mapping():
    """Frame mapping must respect project fps, not assume 30."""
    tm = TimeMap.for_clip(_make_clip(sr=TimeRange(start=0.0, end=10.0),
                                     tr=TimeRange(start=0.0, end=10.0),
                                     speed=1.0), FPS_24)
    # 239 source frames (= last valid frame in [0, 240)) → 239 timeline
    assert tm.timeline_from_source(239) == 239
    assert tm.timeline_from_clip(239) == 239


def test_2997fps_mapping():
    """23.976 fps (30000/1001) — common NTSC framerate."""
    tm = TimeMap.for_clip(_make_clip(sr=TimeRange(start=0.0, end=10.0),
                                     tr=TimeRange(start=0.0, end=10.0),
                                     speed=1.0), FPS_2997)
    # 299 source frames (= last valid frame) → 299 timeline
    assert tm.timeline_from_source(299) == 299


# ---------- Invalid args ----------

def test_invalid_speed_raises():
    import pytest
    with pytest.raises(ValueError):
        TimeMap(source_start_frame=0, source_end_frame=100,
                timeline_start_frame=0, speed=0, fps=FPS_30)
    with pytest.raises(ValueError):
        TimeMap(source_start_frame=0, source_end_frame=100,
                timeline_start_frame=0, speed=-1, fps=FPS_30)


def test_invalid_source_range_raises():
    import pytest
    with pytest.raises(ValueError):
        TimeMap(source_start_frame=100, source_end_frame=50,
                timeline_start_frame=0, speed=1.0, fps=FPS_30)


# ---------- Snapshot: this is the ASR/subtitle test case from the audit doc ----------

def test_audit_subtitle_case():
    """The audit doc's specific example:
    ASR word at source timestamp 0.733s, speed 1.0, source 0..60s,
    clip placed at timeline 0..60s. Find timeline frame.
    """
    tm = TimeMap.for_clip(
        _make_clip(sr=TimeRange(start=0.0, end=60.0),
                   tr=TimeRange(start=0.0, end=60.0),
                   speed=1.0),
        FPS_30,
    )
    # 0.733s @ 30fps = 22 frames (rounded)
    assert tm.timeline_from_source(22) == 22
