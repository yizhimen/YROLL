"""P0-01 Frame First tests."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fractions import Fraction

from yroll.core.timebase import Rational, FrameTime, FrameRange, Timebase


def test_rational_basic():
    r = Rational(30, 1)
    assert r.as_float() == 30.0
    assert str(r) == "30"

    r2 = Rational(30000, 1001)  # 29.97 NTSC
    assert r2.as_float() == 30000 / 1001
    assert r2.num == 30000 and r2.den == 1001


def test_rational_reduction():
    r = Rational(60, 2)
    assert r.num == 30 and r.den == 1

    r2 = Rational(25, 100)
    assert r2.num == 1 and r2.den == 4


def test_rational_normalize_negative_den():
    r = Rational(1, -2)
    assert r.num == -1
    assert r.den == 2


def test_frame_time_from_seconds():
    fps = Rational(30, 1)
    assert FrameTime.from_seconds(1.0, fps).frame == 30
    assert FrameTime.from_seconds(2.5, fps).frame == 75
    assert FrameTime.from_seconds(0.0, fps).frame == 0


def test_frame_time_to_seconds():
    fps = Rational(24, 1)
    t = FrameTime(frame=24, fps=fps)
    assert t.to_seconds() == 1.0
    t2 = FrameTime(frame=144, fps=fps)
    assert t2.to_seconds() == 6.0


def test_frame_time_different_fps():
    # 60 fps
    fps60 = Rational(60, 1)
    t = FrameTime.from_seconds(1.0, fps60)
    assert t.frame == 60
    # 24 fps
    fps24 = Rational(24, 1)
    t24 = FrameTime.from_seconds(1.0, fps24)
    assert t24.frame == 24
    # NTSC 29.97
    ntsc = Rational(30000, 1001)
    tntsc = FrameTime.from_seconds(1.0, ntsc)
    assert tntsc.frame == 30  # round(1.0 * 30000/1001) = round(29.97) = 30


def test_frame_range_basic():
    fps = Rational(30, 1)
    r = FrameRange(start_frame=0, end_frame=90, fps=fps)
    assert r.duration_frames == 90
    assert r.to_seconds() == (0.0, 3.0)


def test_frame_range_contains():
    fps = Rational(30, 1)
    r = FrameRange(start_frame=10, end_frame=20, fps=fps)
    assert r.contains(10)  # start included
    assert r.contains(19)  # end-1 included
    assert not r.contains(20)  # end excluded (half-open)
    assert not r.contains(5)
    assert not r.contains(25)


def test_frame_range_overlaps():
    fps = Rational(30, 1)
    a = FrameRange(0, 10, fps)
    b = FrameRange(10, 20, fps)  # touching, not overlap (half-open)
    c = FrameRange(5, 15, fps)   # overlap with a (touching and overlap)
    d = FrameRange(11, 25, fps)  # overlap with c
    assert not a.overlaps(b)
    assert a.overlaps(c)
    assert c.overlaps(d)
    assert not a.overlaps(d)  # a and d are 0-10 and 11-25, no overlap


def test_frame_range_from_seconds():
    fps = Rational(30, 1)
    r = FrameRange.from_seconds(0.5, 3.5, fps)
    assert r.start_frame == 15
    assert r.end_frame == 105
    assert r.duration_frames == 90


def test_timebase_defaults():
    tb = Timebase()
    assert tb.fps.as_float() == 30.0
    assert tb.width == 1920
    assert tb.height == 1080
    assert abs(tb.aspect - 16/9) < 0.01


def test_timebase_dict_roundtrip():
    tb = Timebase(fps=Rational(25, 1), width=1920, height=1080)
    d = tb.to_dict()
    tb2 = Timebase.from_dict(d)
    assert tb2.fps.as_float() == 25.0
    assert tb2.width == 1920
    assert tb2.height == 1080


def test_timebase_ntsc():
    tb = Timebase(fps=Rational(30000, 1001), width=1920, height=1080)
    d = tb.to_dict()
    tb2 = Timebase.from_dict(d)
    assert abs(tb2.fps.as_float() - 29.97) < 0.01


def test_frame_time_str_30fps():
    """Display format like 00:00:01.000[00] for human readability."""
    fps = Rational(30, 1)
    t = FrameTime(frame=30, fps=fps)  # 1 second
    s = str(t)
    assert "01" in s  # hours:minutes:seconds.fff[ff]
