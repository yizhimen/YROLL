"""P0-02 TimeMap: source_frame ↔ clip_frame ↔ timeline_frame mapping tests.
GUI-02.3: heterogeneous-FPS aware — TimeMap.for_clip requires BOTH
sequence_fps and source_fps; tests use the conformant case
(sequence == source) for back-compat with v0.2 fixtures.
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from yroll.core.manifest import Clip, TimeRange
from yroll.core.timebase import FrameRange, FrameTime, Rational
from yroll.core.timemap import TimeMap


FPS_30 = Rational(30, 1)
FPS_24 = Rational(24, 1)
FPS_60 = Rational(60, 1)
FPS_2997 = Rational(30000, 1001)


def _make_clip(sr=TimeRange(start=0.0, end=10.0),
               tr=TimeRange(start=5.0, end=15.0),
               speed=1.0) -> Clip:
    return Clip(
        clip_id="c1", asset_id="a1",
        source_range=sr, timeline_range=tr, speed=speed,
    )


def _tm(clip, sequence_fps=FPS_30, source_fps=None):
    """TimeMap helper: defaults source_fps to sequence_fps (conformant)."""
    return TimeMap.for_clip(clip, sequence_fps, source_fps or sequence_fps)


# ---------- Source ↔ Clip Local ----------

def test_clip_from_source_normal():
    tm = _tm(_make_clip())
    assert tm.clip_from_source(0) == 0
    assert tm.clip_from_source(150) == 150   # mid-clip
    assert tm.clip_from_source(299) == 299   # last frame


def test_clip_from_source_clamps():
    tm = _tm(_make_clip())
    assert tm.clip_from_source(-5) == 0     # below start → 0
    assert tm.clip_from_source(999) == 299  # past end → clamped to last


def test_source_from_clip():
    tm = _tm(_make_clip())
    assert tm.source_from_clip(0) == 0
    assert tm.source_from_clip(150) == 150
    assert tm.source_from_clip(-5) == 0     # negative clamps


# ---------- Clip Local ↔ Timeline ----------

def test_timeline_from_clip_normal():
    # timeline_start=5.0s @ 30fps = 150 frames, no speed change
    tm = _tm(_make_clip())
    assert tm.timeline_from_clip(0) == 150
    assert tm.timeline_from_clip(150) == 300


def test_timeline_from_clip_speed_2x():
    # 300 source frames @ 2x = 150 timeline frames (so 300 clip-frames map to 150 tl-frames)
    tm = _tm(_make_clip(speed=2.0))
    assert tm.timeline_from_clip(0) == 150
    assert tm.timeline_from_clip(150) == 225  # 150 clip / 2 = 75 + 150 tl = 225


def test_clip_from_timeline_roundtrip():
    tm = _tm(_make_clip())
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
    tm = _tm(clip)
    # source frame 60 (= 2.0s, first valid frame) → timeline frame 300 (= 10.0s)
    assert tm.timeline_from_source(60) == 300
    # mid: 150 source (= 5.0s, clip-local=90) → tl = 10 + 90/1.5 = 70.0s wait...
    # Actually: 90 clip-frames @ 1.5x = 60 timeline-frames past start.
    # timeline = 300 + 60 = 360 (= 12.0s on timeline)
    assert tm.timeline_from_source(150) == 360


def test_source_from_timeline_roundtrip():
    tm = _tm(_make_clip(speed=2.0))
    # roundtrip across speed-affected timeline (2x): use valid interior frames
    for sf in (0, 60, 150, 200, 250):
        tl = tm.timeline_from_source(sf)
        assert tm.source_from_timeline(tl) == sf


# ---------- FrameRange mapping (used by ASR/subtitle mapping) ----------

def test_source_range_to_timeline_range():
    """ASR word source frames 60..90 → timeline frame range."""
    tm = _tm(_make_clip(sr=TimeRange(start=2.0, end=8.0),
                        tr=TimeRange(start=10.0, end=16.0),
                        speed=1.0))
    # Half-open: source [60, 90) = 30 frames @ 1.0x = 30 timeline frames
    # Timeline starts at 300 (source frame 60), so end = 300 + 30 = 330
    src = FrameRange(60, 90, FPS_30)
    tl = tm.timeline_from_source_range(src)
    assert tl.start_frame == 300
    assert tl.end_frame == 330
    assert tl.duration_frames == 30


def test_speed_clip_keeps_half_open():
    """Speed change must preserve half-open semantics on FrameRange."""
    tm = _tm(_make_clip(sr=TimeRange(start=0.0, end=10.0),
                        tr=TimeRange(start=0.0, end=20.0),
                        speed=0.5))
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
    tm = _tm(_make_clip(sr=TimeRange(start=0.0, end=10.0),
                        tr=TimeRange(start=0.0, end=10.0),
                        speed=1.0),
             sequence_fps=FPS_24, source_fps=FPS_24)
    # 239 source frames (= last valid frame in [0, 240)) → 239 timeline
    assert tm.timeline_from_source(239) == 239
    assert tm.timeline_from_clip(239) == 239


def test_2997fps_mapping():
    """23.976 fps (30000/1001) — common NTSC framerate."""
    tm = _tm(_make_clip(sr=TimeRange(start=0.0, end=10.0),
                        tr=TimeRange(start=0.0, end=10.0),
                        speed=1.0),
             sequence_fps=FPS_2997, source_fps=FPS_2997)
    # 299 source frames (= last valid frame) → 299 timeline
    assert tm.timeline_from_source(299) == 299


# ---------- GUI-02.3: heterogeneous FPS ----------

def test_heterogeneous_24src_30seq_basic_mapping():
    """seq=30, src=24, speed=1.0, source 0..10s = 240 src frames.
    Timeline start = 0s = 0 tl frames. So source frame 0 → tl 0
    and source frame 240 (last valid) → tl 240 (NOT 300 — we do NOT
    multiply by 1.25 to convert; the frame count is the count, not
    the time-domain value).
    """
    tm = _tm(
        _make_clip(sr=TimeRange(start=0.0, end=10.0),
                   tr=TimeRange(start=0.0, end=10.0),
                   speed=1.0),
        sequence_fps=FPS_30, source_fps=FPS_24,
    )
    assert tm.source_fps == FPS_24
    assert tm.sequence_fps == FPS_30
    # 240 source frames @ speed=1.0 → 240 timeline frames (NOT 300).
    # Per the GUI-02.3 invariant, source frames and timeline frames
    # are two distinct integer sequences; the mapping preserves the
    # frame count, the time-domain mapping is done via the asset's
    # source_fps when computing seconds for media I/O.
    assert tm.timeline_from_source(0) == 0
    assert tm.timeline_from_source(240 - 1) == 239
    # Roundtrip exact for integer-aligned frames
    assert tm.source_from_timeline(tm.timeline_from_source(120)) == 120


def test_heterogeneous_60src_30seq_speed_2x():
    """seq=30, src=60, speed=2.0.
    Source range: 0..10s = 600 src frames.
    Clip-local frame count = 600.
    At 2x speed: timeline duration = 600 / 2 = 300 tl frames.
    """
    tm = _tm(
        _make_clip(sr=TimeRange(start=0.0, end=10.0),
                   tr=TimeRange(start=0.0, end=5.0),
                   speed=2.0),
        sequence_fps=FPS_30, source_fps=FPS_60,
    )
    assert tm.source_fps == FPS_60
    assert tm.sequence_fps == FPS_30
    assert tm.source_from_clip(0) == 0
    assert tm.timeline_from_clip(0) == 0
    # 600 source frames / 2x → 300 timeline frames (integer boundary).
    # source_from_clip(599) = 599; clip_from_timeline uses round() which
    # is banker's rounding (half-to-even), so round(599/2.0)=round(299.5)=300.
    assert tm.timeline_from_source(599) == 300
    # Even source frames map to timeline frames exactly:
    assert tm.timeline_from_source(0) == 0
    assert tm.timeline_from_source(600) == 300  # clipped to source_end_frame-1 == 599 first
    # The full clip duration in timeline is 300 frames
    assert tm.timeline_range.duration_frames == 300


def test_heterogeneous_24src_30seq_speed_0_5():
    """seq=30, src=24, speed=0.5 (slow motion).
    Source range: 0..10s = 240 src frames.
    At 0.5x: 240 / 0.5 = 480 tl frames.
    """
    tm = _tm(
        _make_clip(sr=TimeRange(start=0.0, end=10.0),
                   tr=TimeRange(start=0.0, end=20.0),
                   speed=0.5),
        sequence_fps=FPS_30, source_fps=FPS_24,
    )
    assert tm.timeline_from_source(0) == 0
    # 240 source frames at 0.5x speed → 480 timeline frames
    assert tm.timeline_from_source(239) == 478  # 239 / 0.5 = 478


def test_heterogeneous_range_output_tagged_with_correct_fps():
    """timeline_from_source_range returns FrameRange tagged sequence_fps.
    source_from_timeline_range returns FrameRange tagged source_fps.
    This is the GUI-02.3 invariant: never relabel a source FrameRange
    as a timeline FrameRange (or vice versa).
    """
    tm = _tm(
        _make_clip(sr=TimeRange(start=0.0, end=10.0),
                   tr=TimeRange(start=0.0, end=10.0),
                   speed=1.0),
        sequence_fps=FPS_30, source_fps=FPS_24,
    )
    src = FrameRange(0, 100, FPS_24)
    tl = tm.timeline_from_source_range(src)
    assert tl.fps == FPS_30       # tagged with sequence fps
    assert tl.start_frame == 0
    assert tl.end_frame == 100     # 100 frames at 1.0x

    tl_in = FrameRange(0, 100, FPS_30)
    src_out = tm.source_from_timeline_range(tl_in)
    assert src_out.fps == FPS_24   # tagged with source fps
    assert src_out.start_frame == 0
    assert src_out.end_frame == 100


def test_heterogeneous_speed_1_5_monotonic():
    """seq=30, src=24, speed=1.5: mapping must be monotonic in both
    directions for the valid clip range."""
    tm = _tm(
        _make_clip(sr=TimeRange(start=0.0, end=10.0),
                   tr=TimeRange(start=0.0, end=6.667),
                   speed=1.5),
        sequence_fps=FPS_30, source_fps=FPS_24,
    )
    last = -1
    for sf in range(0, 240):
        tl = tm.timeline_from_source(sf)
        assert tl >= last, f"non-monotonic at sf={sf}: tl={tl} < last={last}"
        last = tl
    # And inverse
    last = -1
    for tl in range(0, 161):
        sf = tm.source_from_timeline(tl)
        assert sf >= last, f"non-monotonic at tl={tl}: sf={sf} < last={last}"
        last = sf


def test_heterogeneous_speed_2x_roundtrip_exact():
    """seq=30, src=24, speed=2.0:
    For frames that align, timeline_from_source then source_from_timeline
    is exact (modulo the speed-induced integer division)."""
    tm = _tm(
        _make_clip(sr=TimeRange(start=0.0, end=10.0),
                   tr=TimeRange(start=0.0, end=5.0),
                   speed=2.0),
        sequence_fps=FPS_30, source_fps=FPS_24,
    )
    # Even source frames roundtrip exactly through timeline_from_source
    # + source_from_timeline because tl=sf/2 and source_from_timeline(tl)=tl*2.
    for sf in (0, 2, 4, 10, 100, 200):
        tl = tm.timeline_from_source(sf)
        back = tm.source_from_timeline(tl)
        assert back == sf, f"sf={sf} → tl={tl} → back={back}"


def test_for_clip_requires_source_fps():
    """for_clip must reject source_fps=None. This is the hard guard
    that prevents silent source==sequence assumption."""
    with pytest.raises(ValueError, match="source_fps is required"):
        TimeMap.for_clip(_make_clip(), FPS_30, None)


def test_for_clip_with_explicit_source_fps_works():
    tm = TimeMap.for_clip(_make_clip(), FPS_30, FPS_24)
    assert tm.sequence_fps == FPS_30
    assert tm.source_fps == FPS_24


def test_legacy_fps_alias_is_sequence_fps():
    """The legacy `fps` attribute returns sequence_fps. New code must
    not use it; this test pins the alias contract for back-compat."""
    tm = TimeMap.for_clip(_make_clip(), FPS_30, FPS_24)
    assert tm.fps == tm.sequence_fps == FPS_30


# ---------- Invalid args ----------

def test_invalid_speed_raises():
    with pytest.raises(ValueError):
        TimeMap(source_start_frame=0, source_end_frame=100,
                timeline_start_frame=0, speed=0,
                sequence_fps=FPS_30, source_fps=FPS_30)
    with pytest.raises(ValueError):
        TimeMap(source_start_frame=0, source_end_frame=100,
                timeline_start_frame=0, speed=-1,
                sequence_fps=FPS_30, source_fps=FPS_30)


def test_invalid_source_range_raises():
    with pytest.raises(ValueError):
        TimeMap(source_start_frame=100, source_end_frame=50,
                timeline_start_frame=0, speed=1.0,
                sequence_fps=FPS_30, source_fps=FPS_30)


def test_missing_source_fps_raises():
    with pytest.raises(ValueError, match="source_fps is required"):
        TimeMap(source_start_frame=0, source_end_frame=100,
                timeline_start_frame=0, speed=1.0,
                sequence_fps=FPS_30, source_fps=None)


# ---------- Snapshot: this is the ASR/subtitle test case from the audit doc ----------

def test_audit_subtitle_case():
    """The audit doc's specific example:
    ASR word at source timestamp 0.733s, speed 1.0, source 0..60s,
    clip placed at timeline 0..60s. Find timeline frame.
    """
    tm = _tm(_make_clip(sr=TimeRange(start=0.0, end=60.0),
                        tr=TimeRange(start=0.0, end=60.0),
                        speed=1.0))
    # 0.733s @ 30fps = 22 frames (rounded)
    assert tm.timeline_from_source(22) == 22