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
    """P0-7：新建工程必须有 V1/V2/V3 + A1/A2/A3 + T1/T2 共 8 条默认轨。"""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        core = ProjectCore.create(Path(td), "new")
        kinds = [(t.track_id, t.kind) for t in core.project.timeline.tracks]
        expected = [
            ("v1", TrackKind.VIDEO), ("v2", TrackKind.VIDEO), ("v3", TrackKind.VIDEO),
            ("a1", TrackKind.AUDIO), ("a2", TrackKind.AUDIO), ("a3", TrackKind.AUDIO),
            ("t1", TrackKind.TEXT), ("t2", TrackKind.TEXT),
        ]
        for e in expected:
            assert e in kinds, f"缺少默认轨 {e[0]} ({e[1].value})"


def test_ensure_default_tracks_idempotent(tmp_path):
    """P0-7：老工程 open 时自动补齐缺失轨道；已有轨道不重不删。"""
    # 手工建一个只有 v1 + t1 的工程（模拟老 jdz-chaishao）
    core = ProjectCore.create(tmp_path, "old")
    core.project.timeline.tracks = [
        next(t for t in core.project.timeline.tracks if t.track_id == "v1"),
        next(t for t in core.project.timeline.tracks if t.track_id == "t1"),
    ]
    assert len(core.project.timeline.tracks) == 2
    ProjectCore.ensure_default_tracks(core)
    assert len(core.project.timeline.tracks) == 8
    # 第二次调用幂等
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
