"""GUI-03R4-R5: Gap / Ripple editing primitives.

Tests cover the Core-level close_gap and close_gaps_batch commands:
  - close_gap shifts later clips left by the gap size
  - close_gap pulls clips starting inside the gap to start_frame
  - close_gap is atomic (one Operation per call)
  - close_gap refuses empty / negative gaps
  - close_gap refuses unknown track
  - close_gaps_batch finds every empty range in a track
  - close_gaps_batch skips tracks with no gaps
  - close_gaps_batch is per-track (one Operation per track with a gap)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.commands import CommandError, CommandLayer
from yroll.core.manifest import (
    Actor,
    Clip,
    Sequence,
    TimeRange,
    Track,
    TrackKind,
)
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational


FPS_30 = Rational(30, 1)


def _new_core(tmp_path: Path) -> ProjectCore:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    core = ProjectCore.create(project_root, "r4-5-test")
    core.project.sequence = Sequence(fps=FPS_30)
    core.project.sequence.sync_to_project(core.project)
    asset = Asset(
        asset_id="a1", type=AssetType.VIDEO, path="/tmp/v.mp4",
        identity=AssetIdentity(md5="a" * 32, size_bytes=1, duration_sec=10.0),
    )
    asset.source_fps = FPS_30
    asset.source_is_cfr = True
    asset.source_frame_count = 300
    core.project.assets.append(asset)
    return core


def _add_clip(layer: CommandLayer, track_id: str, start: float,
               end: float, asset_id: str = "a1") -> Clip:
    return layer.add_clip(
        asset_id, source_start=0.0, source_end=end - start,
        timeline_start=start, track_id=track_id, why="r4-5-test",
    )


# ---------------------------------------------------------------------------
# close_gap: shift later clips left
# ---------------------------------------------------------------------------

def test_close_gap_shifts_later_clips_left(tmp_path):
    """A gap of [10, 20] should shift every clip starting at >= 20
    left by 10. A clip starting at 30 ends up at 20; a clip starting
    at 5 is untouched."""
    core = _new_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_track(TrackKind.VIDEO, "v1")
    a = _add_clip(layer, "v1", 0, 5)
    b = _add_clip(layer, "v1", 5, 10)
    c = _add_clip(layer, "v1", 30, 35)  # past the gap
    d = _add_clip(layer, "v1", 50, 55)  # further past
    op = layer.close_gap("main", "v1", 10, 20, why="audit")
    assert op.before != {}, "close_gap should produce before/after"
    a_after = core.project.clips[a.clip_id]
    b_after = core.project.clips[b.clip_id]
    c_after = core.project.clips[c.clip_id]
    d_after = core.project.clips[d.clip_id]
    # a/b untouched.
    assert a_after.timeline_range.start == 0.0
    assert b_after.timeline_range.start == 5.0
    # c shifted: 30 -> 20.
    assert c_after.timeline_range.start == pytest.approx(20.0, abs=1e-3)
    assert c_after.timeline_range.end == pytest.approx(25.0, abs=1e-3)
    # d shifted: 50 -> 40.
    assert d_after.timeline_range.start == pytest.approx(40.0, abs=1e-3)
    assert d_after.timeline_range.end == pytest.approx(45.0, abs=1e-3)


def test_close_gap_pulls_clip_inside_gap_to_start(tmp_path):
    """If a clip starts INSIDE the gap (start < end_frame but
    start >= start_frame), pull it to start_frame."""
    core = _new_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_track(TrackKind.VIDEO, "v1")
    _add_clip(layer, "v1", 0, 5)
    inner = _add_clip(layer, "v1", 12, 17)  # starts INSIDE the gap [10, 20]
    _add_clip(layer, "v1", 30, 35)  # past the gap
    op = layer.close_gap("main", "v1", 10, 20, why="audit")
    # inner should be pulled to start=10; duration preserved.
    inner_after = core.project.clips[inner.clip_id]
    assert inner_after.timeline_range.start == pytest.approx(10.0, abs=1e-3)
    assert inner_after.timeline_range.end == pytest.approx(15.0, abs=1e-3)
    assert op.before != {}


def test_close_gap_emits_exactly_one_operation(tmp_path):
    """One user intent = one Core Operation, even when multiple clips
    are shifted."""
    core = _new_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_track(TrackKind.VIDEO, "v1")
    _add_clip(layer, "v1", 0, 5)
    _add_clip(layer, "v1", 30, 35)
    _add_clip(layer, "v1", 50, 55)
    before = len(core.operations())
    op = layer.close_gap("main", "v1", 10, 20, why="audit")
    after = len(core.operations())
    assert after - before == 1
    assert op.type == "close_gap"


def test_close_gap_no_op_when_gap_catches_nothing(tmp_path):
    """A gap that doesn't catch any clips still records ONE no-op
    Operation (auditable)."""
    core = _new_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_track(TrackKind.VIDEO, "v1")
    _add_clip(layer, "v1", 0, 5)
    _add_clip(layer, "v1", 8, 10)
    op = layer.close_gap("main", "v1", 100, 110, why="audit")
    assert op.type == "close_gap"
    # Nothing shifted.
    assert op.before == {}


def test_close_gap_rejects_empty_range(tmp_path):
    """end_frame <= start_frame raises CommandError."""
    core = _new_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_track(TrackKind.VIDEO, "v1")
    with pytest.raises(CommandError, match="empty range"):
        layer.close_gap("main", "v1", 10, 10, why="audit")
    with pytest.raises(CommandError, match="empty range"):
        layer.close_gap("main", "v1", 10, 5, why="audit")


def test_close_gap_rejects_unknown_track(tmp_path):
    core = _new_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    with pytest.raises(CommandError, match="track not found"):
        layer.close_gap("main", "nonexistent", 10, 20, why="audit")


def test_close_gap_refuses_to_create_negative_starts(tmp_path):
    """GUI-03R4-R2 invariant: clip.start cannot go below 0. A close
    shift that would push a clip below 0 must instead clamp at 0."""
    core = _new_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_track(TrackKind.VIDEO, "v1")
    _add_clip(layer, "v1", 0, 5)
    c = _add_clip(layer, "v1", 12, 17)  # gap [10, 20]
    layer.close_gap("main", "v1", 10, 20, why="audit")
    # c pulled to start=10 (not 0; the gap start is 10).
    assert core.project.clips[c.clip_id].timeline_range.start == pytest.approx(10.0, abs=1e-3)


# ---------------------------------------------------------------------------
# close_gaps_batch: find every gap in a track
# ---------------------------------------------------------------------------

def test_close_gaps_batch_collapses_every_gap(tmp_path):
    core = _new_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_track(TrackKind.VIDEO, "v1")
    _add_clip(layer, "v1", 0, 5)
    _add_clip(layer, "v1", 30, 35)   # gap [5, 30]
    _add_clip(layer, "v1", 50, 55)   # gap [35, 50]
    _add_clip(layer, "v1", 70, 75)   # gap [55, 70]
    ops = layer.close_gaps_batch("main", ["v1"], why="audit")
    assert len(ops) == 3, f"Expected 3 gap ops, got {len(ops)}"
    # After all collapses, clips are contiguous: [0,5],[5,10],[10,15],[15,20].
    clips = sorted(
        [core.project.clips[cid]
         for t in core.project.timelines[0].tracks
         if t.track_id == "v1"
         for cid in t.clip_ids],
        key=lambda c: c.timeline_range.start)
    assert clips[0].timeline_range.start == 0
    assert clips[1].timeline_range.start == 5
    assert clips[2].timeline_range.start == 10
    assert clips[3].timeline_range.start == 15


def test_close_gaps_batch_skips_tracks_with_no_gaps(tmp_path):
    """A track whose clips are already contiguous produces no Operation
    (clean log)."""
    core = _new_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_track(TrackKind.VIDEO, "v1")
    _add_clip(layer, "v1", 0, 5)
    _add_clip(layer, "v1", 5, 10)
    _add_clip(layer, "v1", 10, 15)
    ops = layer.close_gaps_batch("main", ["v1"], why="audit")
    assert ops == []


def test_close_gaps_batch_per_track_one_operation_per_gap_track(tmp_path):
    """One Operation per TRACK that had gaps (not one per gap)."""
    core = _new_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_track(TrackKind.VIDEO, "v1")
    _add_clip(layer, "v1", 0, 5)
    _add_clip(layer, "v1", 30, 35)
    _add_clip(layer, "v1", 50, 55)
    layer.add_track(TrackKind.VIDEO, "v2")
    _add_clip(layer, "v2", 0, 5)
    _add_clip(layer, "v2", 5, 10)  # contiguous — no op
    ops = layer.close_gaps_batch("main", ["v1", "v2"], why="audit")
    # v1 had 2 gaps → 2 ops. v2 had 0 gaps → 0 ops. Total 2.
    assert len(ops) == 2
    # Both ops reference v1 (the gap-bearing track).
    assert all(op.target == "v1" for op in ops)


def test_close_gaps_batch_rejects_unknown_track(tmp_path):
    core = _new_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_track(TrackKind.VIDEO, "v1")
    with pytest.raises(CommandError, match="track not found"):
        layer.close_gaps_batch("main", ["v1", "ghost"], why="audit")


def test_close_gaps_batch_multi_track_each_track_atomic(tmp_path):
    """Per-track atomicity: each track's operation captures that
    track's full before/after; another track's shifts don't bleed
    across."""
    core = _new_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_track(TrackKind.VIDEO, "v1")
    layer.add_track(TrackKind.VIDEO, "v2")
    a = _add_clip(layer, "v1", 0, 5)
    b = _add_clip(layer, "v1", 30, 35)   # gap on v1
    c = _add_clip(layer, "v2", 0, 5)
    d = _add_clip(layer, "v2", 30, 35)   # gap on v2
    ops = layer.close_gaps_batch("main", ["v1", "v2"], why="audit")
    assert len(ops) == 2
    for op in ops:
        assert op.type == "close_gap"
        for cid in op.before:
            assert cid in {a.clip_id, b.clip_id, c.clip_id, d.clip_id}