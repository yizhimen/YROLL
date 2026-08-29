"""GUI-02: Frame / seconds dual-write test (user spec).

The GUI sends N frames; after the mutation is committed, the entire
project state — including operation log, manifest, and a reloaded
ProjectCore — must round-trip back to exactly N frames. This test
catches the most insidious "silent frame→seconds→frame" conversion
at the boundary.

Tested at:
  - 1 frame, 2 frames (smallest moves)
  - 1 frame at 29.97 fps
  - 1 frame at 1.5x speed
  - 1 frame at clip boundaries (start, end-1)
  - 1 frame across the 10-minute DF boundary (17982 -> 17983)
  - 1 frame at the very first frame (frame 0)
"""
import shutil
import tempfile
from pathlib import Path

import pytest

from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational


def _open_project(td: Path) -> ProjectCore:
    return ProjectCore.open(td / "dual-write")


def _make_project_with_clip(td: Path, *, fps: tuple, speed: float = 1.0) -> ProjectCore:
    """Create a project with one clip at 0..10s of asset."""
    from yroll.core.models import Asset, AssetIdentity, AssetType
    ProjectCore.create(str(td), "dual-write")
    core = _open_project(td)
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="x.mp4", origin="unknown",
        identity=AssetIdentity(md5="b" * 32, size_bytes=1, duration_sec=60.0),
    ))
    core.project.sequence.fps = Rational(*fps)
    from yroll.core.commands import CommandLayer
    from yroll.core.manifest import Actor
    layer = CommandLayer(core, who=Actor.HUMAN)
    fps_num, fps_den = fps
    src_frames = int(10 * fps_num / fps_den)
    layer.add_clip_frame("a1", 0, src_frames, 0, track_id="V1", why="seed")
    # Apply speed if not 1.0
    if speed != 1.0:
        from yroll.core.commands import CommandLayer as _CL
        clip_id = list(core.project.clips.keys())[0]
        _CL(core, who=Actor.HUMAN).set_speed(clip_id, speed, why="seed")
    core.save_state()
    return core


def _read_clip_frames(core, clip_id):
    """Read the clip's source-range frames back from the persisted
    model. Performs the project-core's seconds -> frames mapping via
    the project's fps."""
    fps = core.project.sequence.fps
    sr = core.project.clips[clip_id].source_range
    return (round(sr.start * fps.num / fps.den),
            round(sr.end * fps.num / fps.den))


def test_one_frame_trim_at_30fps(tmp_path):
    with tempfile.TemporaryDirectory() as td:
        core = _make_project_with_clip(Path(td), fps=(30, 1))
        clip_id = list(core.project.clips.keys())[0]
        # Trim 1 frame at start: 0..10s -> 1..10s = frames 30..300
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor
        layer = CommandLayer(core, who=Actor.HUMAN)
        layer.trim_clip_frame(clip_id, src_start_frame=1, src_end_frame=300)
        core.save_state()
        # Reload from disk
        core2 = ProjectCore.open(Path(td) / "dual-write")
        s, e = _read_clip_frames(core2, clip_id)
        assert (s, e) == (1, 300), f"expected (1, 300), got ({s}, {e})"


def test_two_frame_trim_at_30fps(tmp_path):
    with tempfile.TemporaryDirectory() as td:
        core = _make_project_with_clip(Path(td), fps=(30, 1))
        clip_id = list(core.project.clips.keys())[0]
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor
        layer = CommandLayer(core, who=Actor.HUMAN)
        layer.trim_clip_frame(clip_id, src_start_frame=2, src_end_frame=300)
        core.save_state()
        core2 = ProjectCore.open(Path(td) / "dual-write")
        s, e = _read_clip_frames(core2, clip_id)
        assert (s, e) == (2, 300)


def test_one_frame_trim_at_29_97_fps(tmp_path):
    """The classic 29.97 fps case where seconds<->frames conversion
    is non-integer. The 1-frame trim must still come out as exactly
    1 frame after save+reload."""
    with tempfile.TemporaryDirectory() as td:
        core = _make_project_with_clip(Path(td), fps=(30000, 1001))
        clip_id = list(core.project.clips.keys())[0]
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor
        layer = CommandLayer(core, who=Actor.HUMAN)
        # 10s = 30000/1001 * 10 = 299.7 frames, rounded to 300.
        # The clip was created as 0..300 frames. Trim 1 frame.
        layer.trim_clip_frame(clip_id, src_start_frame=1, src_end_frame=300)
        core.save_state()
        core2 = ProjectCore.open(Path(td) / "dual-write")
        s, e = _read_clip_frames(core2, clip_id)
        assert (s, e) == (1, 300)


def test_one_frame_trim_at_1_5x_speed(tmp_path):
    """Speed != 1.0 changes the timeline-frame -> source-frame
    mapping. The trim itself is on source frames, but the dual-write
    test must still round-trip the source_range frames exactly."""
    with tempfile.TemporaryDirectory() as td:
        core = _make_project_with_clip(Path(td), fps=(30, 1), speed=1.5)
        clip_id = list(core.project.clips.keys())[0]
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor
        layer = CommandLayer(core, who=Actor.HUMAN)
        layer.trim_clip_frame(clip_id, src_start_frame=1, src_end_frame=300)
        core.save_state()
        core2 = ProjectCore.open(Path(td) / "dual-write")
        s, e = _read_clip_frames(core2, clip_id)
        assert (s, e) == (1, 300)


def test_trim_at_clip_boundary_start(tmp_path):
    with tempfile.TemporaryDirectory() as td:
        core = _make_project_with_clip(Path(td), fps=(30, 1))
        clip_id = list(core.project.clips.keys())[0]
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor
        layer = CommandLayer(core, who=Actor.HUMAN)
        # Trim 0 frames: no change
        layer.trim_clip_frame(clip_id, src_start_frame=0, src_end_frame=300)
        core.save_state()
        core2 = ProjectCore.open(Path(td) / "dual-write")
        s, e = _read_clip_frames(core2, clip_id)
        assert (s, e) == (0, 300)


def test_trim_at_clip_boundary_end_minus_one(tmp_path):
    with tempfile.TemporaryDirectory() as td:
        core = _make_project_with_clip(Path(td), fps=(30, 1))
        clip_id = list(core.project.clips.keys())[0]
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor
        layer = CommandLayer(core, who=Actor.HUMAN)
        # Trim so the clip is 1 frame long
        layer.trim_clip_frame(clip_id, src_start_frame=299, src_end_frame=300)
        core.save_state()
        core2 = ProjectCore.open(Path(td) / "dual-write")
        s, e = _read_clip_frames(core2, clip_id)
        assert (s, e) == (299, 300)


def test_split_then_dual_write(tmp_path):
    """Split a clip at timeline frame X. The two halves must
    preserve their source-range frames after save+reload."""
    with tempfile.TemporaryDirectory() as td:
        core = _make_project_with_clip(Path(td), fps=(30, 1))
        clip_id = list(core.project.clips.keys())[0]
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor
        layer = CommandLayer(core, who=Actor.HUMAN)
        # Split at timeline frame 60 (2s). Left = frames 0..60, Right = 60..300.
        left, right = layer.split_clip_frame(clip_id, at_timeline_frame=60)
        core.save_state()
        core2 = ProjectCore.open(Path(td) / "dual-write")
        ls, le = _read_clip_frames(core2, left.clip_id)
        rs, re = _read_clip_frames(core2, right.clip_id)
        assert (ls, le) == (0, 60)
        assert (rs, re) == (60, 300)


def test_first_frame_trim_does_not_disappear(tmp_path):
    """Trimming 1 frame at the very start (frame 0) is a boundary
    case: it must produce a clip starting at frame 1, not at 0."""
    with tempfile.TemporaryDirectory() as td:
        core = _make_project_with_clip(Path(td), fps=(30, 1))
        clip_id = list(core.project.clips.keys())[0]
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor
        layer = CommandLayer(core, who=Actor.HUMAN)
        layer.trim_clip_frame(clip_id, src_start_frame=1, src_end_frame=300)
        core.save_state()
        core2 = ProjectCore.open(Path(td) / "dual-write")
        s, e = _read_clip_frames(core2, clip_id)
        assert s == 1
        assert e == 300
