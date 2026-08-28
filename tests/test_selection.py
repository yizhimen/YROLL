"""P0-03 Selection tests."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from yroll.core.selection import Selection
from yroll.core.timebase import FrameRange, Rational, Timebase


def test_selection_empty():
    s = Selection()
    assert s.is_empty()
    assert not bool(s)
    assert s.describe() == "empty"


def test_selection_single():
    s = Selection.single("c1")
    assert not s.is_empty()
    assert s.contains_clip("c1")
    assert not s.contains_clip("c2")
    assert "1 clip" in s.describe()


def test_selection_many():
    s = Selection.many(["c1", "c2", "c3"])
    assert len(s.clip_ids) == 3
    assert s.contains_clip("c1")
    assert s.contains_clip("c3")


def test_selection_track():
    s = Selection.track_only("v1")
    assert s.contains_track("v1")
    assert not s.contains_clip("anything")


def test_selection_range():
    fps = Rational(30, 1)
    r = FrameRange(0, 90, fps)
    s = Selection.range_only(r)
    assert s.range == r
    # intersects a clip in v1 from 50-100 -> True
    assert s.intersects("v1", 50, 100)
    # intersects at 0-30 -> True
    assert s.intersects("a1", 0, 30)
    # intersects at 200-300 (out of range) -> False
    assert not s.intersects("a1", 200, 300)


def test_selection_from_clip_or_id_str():
    s1 = Selection.from_clip_or_id("c1")
    assert isinstance(s1, Selection) and s1.clip_ids == ["c1"]
    s2 = Selection.from_clip_or_id(["c1", "c2", "c3"])
    assert s2.clip_ids == ["c1", "c2", "c3"]
    s3 = Selection.from_clip_or_id(Selection.single("c1"))
    assert s3 is s3  # identity


def test_selection_combined():
    """Multi-clip + range + track - the realistic editing selection."""
    fps = Rational(30, 1)
    s = Selection(
        clip_ids=["c1", "c2"],
        track_ids=["v1"],
        range=FrameRange(0, 90, fps),
    )
    desc = s.describe()
    assert "2 clip" in desc
    assert "1 track" in desc
    assert "range=" in desc


def test_selection_intersects_with_combined():
    """Selection has both clip_ids AND range: intersects if either matches."""
    fps = Rational(30, 1)
    # clip_ids only - matches only via range
    s = Selection(clip_ids=["c1"], range=FrameRange(0, 30, fps))
    assert s.intersects("any", 10, 20) is True
    assert s.intersects("any", 100, 200) is False
    # track_ids only - matches via track
    s2 = Selection(track_ids=["v1"], range=FrameRange(0, 30, fps))
    assert s2.intersects("v1", 1000, 2000) is True
    assert s2.intersects("v2", 100, 200) is False
    # combined - matches via either
    s3 = Selection(clip_ids=["c1"], track_ids=["v1"], range=FrameRange(0, 30, fps))
    assert s3.intersects("v1", 100, 200) is True
    assert s3.intersects("any", 0, 60) is True
    assert s3.intersects("x", 100, 200) is False


def test_selection_iterable():
    """Can iterate over all selected clip IDs."""
    s = Selection.many(["c1", "c2", "c3"])
    ids = [c for c in s.clip_ids]
    assert ids == ["c1", "c2", "c3"]
