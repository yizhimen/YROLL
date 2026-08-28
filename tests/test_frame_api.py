"""P0-01 Frame-based API tests."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore


def test_frame_api_add_clip_30fps(tmp_path):
    core = ProjectCore.create(tmp_path, "frame30")
    core.project.assets.append(Asset(
        asset_id="fa", type=AssetType.VIDEO, path="x.mp4", origin="unknown",
        identity=AssetIdentity(md5="a" * 32, size_bytes=1, duration_sec=5.0)))
    core.save_state()
    layer = CommandLayer(core, who=Actor.HUMAN)
    # 30 fps: 2 seconds = 60 frames
    c = layer.add_clip_frame("fa", 0, 60, 0, track_id="v1", why="test")
    assert c.timeline_range.start == 0.0
    assert c.timeline_range.end == pytest.approx(2.0, abs=0.01)
    # move by 60 frames = 2 seconds
    layer.move_clip_frame(c.clip_id, 60, why="test")
    assert c.timeline_range.start == pytest.approx(2.0, abs=0.01)
    # trim to frames 30-90 (50-150 frames = 2-3 sec)
    layer.trim_clip_frame(c.clip_id, src_start_frame=30, src_end_frame=90, why="test")
    assert c.timeline_range.start == pytest.approx(3.0, abs=0.01)
    assert c.timeline_range.end == pytest.approx(5.0, abs=0.01)


def test_frame_api_add_clip_24fps(tmp_path):
    core = ProjectCore.create(tmp_path, "frame24")
    core.project.assets.append(Asset(
        asset_id="fa", type=AssetType.VIDEO, path="x.mp4", origin="unknown",
        identity=AssetIdentity(md5="b" * 32, size_bytes=1, duration_sec=5.0)))
    core.project.fps_num = 24
    core.project.fps_den = 1
    core.save_state()
    layer = CommandLayer(core, who=Actor.HUMAN)
    # 24 fps: 2 seconds = 48 frames
    c = layer.add_clip_frame("fa", 0, 48, 0, track_id="v1", why="test")
    assert c.timeline_range.start == 0.0
    assert c.timeline_range.end == pytest.approx(2.0, abs=0.01)


def test_frame_api_2997_ntsc(tmp_path):
    """29.97 fps NTSC: 1 second = 30000/1001 frames ≈ 30 frames"""
    core = ProjectCore.create(tmp_path, "ntsc")
    core.project.assets.append(Asset(
        asset_id="fa", type=AssetType.VIDEO, path="x.mp4", origin="unknown",
        identity=AssetIdentity(md5="c" * 32, size_bytes=1, duration_sec=5.0)))
    core.project.fps_num = 30000
    core.project.fps_den = 1001
    core.save_state()
    layer = CommandLayer(core, who=Actor.HUMAN)
    # 1 second = 30 frames
    c = layer.add_clip_frame("fa", 0, 30, 0, track_id="v1", why="test")
    assert c.timeline_range.start == 0.0
    assert c.timeline_range.end == pytest.approx(1.0, abs=0.01)


def test_frame_api_round_trip(tmp_path):
    """frame -> sec -> frame should be lossless for integer multiples"""
    core = ProjectCore.create(tmp_path, "roundtrip")
    core.save_state()
    layer = CommandLayer(core, who=Actor.HUMAN)
    # 30 fps: 150 frames = 5 sec; 5 sec back = 150 frames
    sec = layer._frame_to_sec(150)
    assert sec == 5.0
    frm = layer._sec_to_frame(5.0)
    assert frm == 150
