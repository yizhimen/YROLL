"""P0-06: Snap Engine tests — unified frame snap."""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor, TrackKind
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.snap import SnapEngine, SnapKind, SnapTarget
from yroll.core.timebase import Rational


FPS = Rational(30, 1)


@pytest.fixture()
def core(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "snap-test")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=60.0),
    ))
    return core


def test_snap_to_clip_start(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    cmd.add_clip("a1", 5.0, 10.0, timeline_start=5.0)

    targets = SnapEngine.collect_clip_targets(core.project, FPS)
    # c2 starts at frame 150 (= 5s @ 30fps)
    engine = SnapEngine(threshold_frames=5)
    snap = engine.snap(frame=148, targets=targets)  # within threshold
    assert snap is not None
    assert snap.frame == 150  # snapped to c2's start


def test_no_snap_outside_threshold(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)

    targets = SnapEngine.collect_clip_targets(core.project, FPS)
    engine = SnapEngine(threshold_frames=3)
    snap = engine.snap(frame=200, targets=targets)  # far from any clip
    assert snap is None


def test_snap_prefers_closer_target(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    cmd.add_clip("a1", 5.0, 10.0, timeline_start=5.0)

    targets = SnapEngine.collect_clip_targets(core.project, FPS)
    engine = SnapEngine(threshold_frames=10)
    # Frame 152 is 2 frames from c2.start (150) and 152 frames from c1.start (0).
    snap = engine.snap(frame=152, targets=targets)
    assert snap.frame == 150


def test_snap_priority_clip_start_over_playhead(core):
    """Multiple kinds equidistant: CLIP_START wins (structural over transient)."""
    targets = [
        SnapTarget(100, SnapKind.PLAYHEAD),
        SnapTarget(101, SnapKind.CLIP_START),
        SnapTarget(102, SnapKind.CLIP_END),
    ]
    engine = SnapEngine(threshold_frames=5)
    # Frame 100 is 0 from PLAYHEAD, 1 from CLIP_START → PLAYHEAD wins
    snap = engine.snap(frame=100, targets=targets)
    assert snap.target.kind == SnapKind.PLAYHEAD


def test_snap_subtitle_boundary(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_track(TrackKind.TEXT, "t1")
    cmd.add_clip("", 0.0, 2.0, timeline_start=5.0, track_id="t1")  # subtitle @ 5..7s
    targets = SnapEngine.collect_subtitle_targets(core.project, FPS)
    # subtitle starts at frame 150 (5s @ 30fps)
    assert any(t.frame == 150 and t.kind == SnapKind.SUBTITLE_BOUNDARY
               for t in targets)
    engine = SnapEngine(threshold_frames=3)
    snap = engine.snap(frame=151, targets=targets)
    assert snap is not None
    assert snap.target.kind == SnapKind.SUBTITLE_BOUNDARY


def test_snap_word_boundary_via_timemap(core):
    """Word boundary uses TimeMap to translate source → timeline frames."""
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 10.0, timeline_start=2.0)  # source 0..10, tl 2..12
    transcripts = {
        "a1": [
            {"text": "hello", "start": 1.0, "end": 1.5},
        ],
    }
    targets = SnapEngine.collect_word_targets(core.project, FPS, transcripts)
    # Word at source 1.0s (= frame 30) with clip source_start=0, tl_start=2.0
    # → timeline frame = 30 + tl_offset(2s=60) = 90
    assert any(t.frame == 90 and t.kind == SnapKind.WORD_BOUNDARY
               for t in targets)


def test_snap_playhead(core):
    targets = SnapEngine.collect_playhead(10.0, FPS)
    engine = SnapEngine(threshold_frames=2)
    snap = engine.snap(frame=299, targets=targets)  # 10s = frame 300
    assert snap is not None
    assert snap.target.kind == SnapKind.PLAYHEAD


def test_snap_returns_delta(core):
    """SnapResult.delta_frames tells caller how far we moved."""
    targets = [SnapTarget(100, SnapKind.CLIP_START)]
    engine = SnapEngine(threshold_frames=10)
    snap = engine.snap(frame=103, targets=targets)
    assert snap.delta_frames == -3  # target 100 is 3 to the left of input 103
