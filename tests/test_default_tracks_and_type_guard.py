"""Phase A 回归测试：默认轨道结构 + 素材类型校验。

P0-7（轨道）/ P0-8（图片可上轨 + 类型校验）：防止回归。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from yroll.core.commands import CommandError, CommandLayer
from yroll.core.manifest import Actor, TrackKind
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore


def _make_core(tmp_path: Path, name: str = "t") -> ProjectCore:
    core = ProjectCore.create(tmp_path, name)
    # 测试工程补齐缺失轨道
    ProjectCore.ensure_default_tracks(core)
    return core


def test_default_tracks_present():
    """GUI-03C: NEW projects have NO pre-created default tracks.
    Tracks are allocated on demand by the Core allocator. The
    visible Timeline contains only tracks that are actually needed
    by the current project (after adding clips)."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        core = ProjectCore.create(Path(td), "new")
        # No pre-created tracks.
        assert core.project.timeline.tracks == [], (
            "GUI-03C: ProjectCore.create() must NOT pre-create "
            "v1/v2/v3/a1/a2/a3/t1/t2; tracks are allocated on demand."
        )
        # Add an image — exactly one track (v1) is created.
        core.project.assets.append(Asset(
            asset_id="img1", type=AssetType.IMAGE, path="x.jpg",
            identity=AssetIdentity(md5="x" * 32, size_bytes=1),
        ))
        layer = CommandLayer(core, who=Actor.HUMAN)
        layer.add_image_clip("img1", 0, 30)
        # Only v1 is now present.
        assert len(core.project.timeline.tracks) == 1
        assert core.project.timeline.tracks[0].track_id == "v1"
        # Adding an audio clip allocates a1 (a new track kind).
        core.project.assets.append(Asset(
            asset_id="aud1", type=AssetType.AUDIO, path="x.m4a",
            identity=AssetIdentity(md5="y" * 32, size_bytes=1, duration_sec=2.0),
        ))
        layer.add_clip("aud1", 0.0, 2.0, timeline_start=0.0)
        track_ids = sorted(t.track_id for t in core.project.timeline.tracks)
        assert track_ids == ["a1", "v1"]


def test_ensure_default_tracks_idempotent(tmp_path):
    """P0-7 (legacy compat): OLD projects that have only v1+t1
    still get the other 6 default tracks added on `ensure_default_tracks`
    call. This is a legacy migration path for pre-GUI-03C projects;
    new projects don't need it because they create tracks on demand."""
    # Hand-craft an old project with only v1 + t1.
    core = ProjectCore.create(tmp_path, "old")
    # New projects have no pre-created tracks; we add v1 + t1 manually
    # to simulate a pre-GUI-03C project state.
    from yroll.core.manifest import Track, TrackKind
    core.project.timeline.tracks = [
        Track(track_id="v1", kind=TrackKind.VIDEO),
        Track(track_id="t1", kind=TrackKind.TEXT),
    ]
    assert len(core.project.timeline.tracks) == 2
    ProjectCore.ensure_default_tracks(core)
    # The legacy migration fills in the missing tracks.
    assert len(core.project.timeline.tracks) == 8
    # Second call is idempotent.
    ProjectCore.ensure_default_tracks(core)
    assert len(core.project.timeline.tracks) == 8


def test_image_to_video_track_ok(tmp_path):
    """P0-8：图片上 V 轨允许（默认 5s），image → a2 拒绝。"""
    core = _make_core(tmp_path)
    core.project.assets.append(Asset(
        asset_id="img1", type=AssetType.IMAGE, path="x.jpg",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1),
    ))
    layer = CommandLayer(core, who=Actor.HUMAN)
    # 图片上 v1 应成功
    clip = layer.add_clip("img1", 0, 5, 0, track_id="v1", why="test img→v1")
    assert clip.track_id == "v1"
    assert clip.timeline_range.end == 5.0


def test_image_to_audio_track_rejected(tmp_path):
    """P0-8：图片不允许上 A 轨（必须 audio）。"""
    core = _make_core(tmp_path)
    core.project.assets.append(Asset(
        asset_id="img1", type=AssetType.IMAGE, path="x.jpg",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1),
    ))
    layer = CommandLayer(core, who=Actor.HUMAN)
    with pytest.raises(CommandError, match="audio.*rejects.*image"):
        layer.add_clip("img1", 0, 5, 0, track_id="a1", why="test img→a1 fail")


def test_audio_to_video_track_rejected(tmp_path):
    """P0-8：音频素材不允许上 V 轨。"""
    core = _make_core(tmp_path)
    core.project.assets.append(Asset(
        asset_id="aud1", type=AssetType.AUDIO, path="x.m4a",
        identity=AssetIdentity(md5="y" * 32, size_bytes=1, duration_sec=2.0),
    ))
    layer = CommandLayer(core, who=Actor.HUMAN)
    with pytest.raises(CommandError, match="video.*rejects.*audio"):
        layer.add_clip("aud1", 0, 2, 0, track_id="v1", why="test aud→v1 fail")


def test_audio_to_audio_track_ok(tmp_path):
    """P0-8：音频上 A 轨允许。"""
    core = _make_core(tmp_path)
    core.project.assets.append(Asset(
        asset_id="aud1", type=AssetType.AUDIO, path="x.m4a",
        identity=AssetIdentity(md5="y" * 32, size_bytes=1, duration_sec=2.0),
    ))
    layer = CommandLayer(core, who=Actor.HUMAN)
    clip = layer.add_clip("aud1", 0, 2, 0, track_id="a1", why="test aud→a1 OK")
    assert clip.track_id == "a1"


def test_video_to_video_track_ok(tmp_path):
    """P0-8：视频上 V 轨允许。"""
    core = _make_core(tmp_path)
    core.project.assets.append(Asset(
        asset_id="vid1", type=AssetType.VIDEO, path="x.mp4",
        identity=AssetIdentity(md5="z" * 32, size_bytes=1, duration_sec=3.0),
    ))
    layer = CommandLayer(core, who=Actor.HUMAN)
    clip = layer.add_clip("vid1", 0, 3, 0, track_id="v1", why="test vid→v1 OK")
    assert clip.track_id == "v1"
