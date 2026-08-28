"""去停顿/气口测试：合成"有声-静音-有声"的音频 → 检测 → 自动裁剪重建。"""

import subprocess
from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor, TimeRange
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.tools.audio_tools import complement_ranges, detect_silences


def _make_talk_video(path: Path) -> None:
    """4 秒视频：0-1s 有声，1-2.5s 静音，2.5-4s 有声。"""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=blue:s=320x240:d=4:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-f", "lavfi", "-i", "anullsrc=d=1.5",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5",
         "-filter_complex", "[1:a][2:a][3:a]concat=n=3:v=0:a=1[a]",
         "-map", "0:v", "-map", "[a]", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(path)],
        check=True, capture_output=True,
    )


def test_detect_silences(tmp_path: Path):
    _make_talk_video(tmp_path / "talk.mp4")
    silences = detect_silences(tmp_path / "talk.mp4", noise_db=-35, min_duration=0.4)
    assert len(silences) == 1
    assert silences[0].start == pytest.approx(1.0, abs=0.2)
    assert silences[0].end == pytest.approx(2.5, abs=0.2)


def test_complement_ranges_padding():
    whole = TimeRange(start=0.0, end=4.0)
    keeps = complement_ranges(whole, [TimeRange(start=1.0, end=2.5)])
    assert len(keeps) == 2
    assert keeps[0].end == pytest.approx(1.08)  # padding 保护尾音
    assert keeps[1].start == pytest.approx(2.42)


def test_remove_silence_rebuilds_clip(tmp_path: Path):
    _make_talk_video(tmp_path / "talk.mp4")
    core = ProjectCore.create(tmp_path, "sil-demo")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path=str(tmp_path / "talk.mp4"),
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=4.0),
    ))
    cmd = CommandLayer(core, who=Actor.AI)
    clip = cmd.add_clip("a1", 0.0, 4.0, timeline_start=0.0)

    op = cmd.remove_silence(clip.clip_id, min_duration=0.4)

    # 一个 clip 重建成两个，静音段被删除，时间轴收缩
    assert len(op.after["new_clips"]) == 1
    assert op.after["removed_seconds"] == pytest.approx(1.34, abs=0.3)
    track = core.project.timeline.tracks[0]
    assert len(track.clip_ids) == 2
    second = core.project.clips[op.after["new_clips"][0]]
    assert second.source_range.start == pytest.approx(2.42, abs=0.1)
    # 原 clip 收缩到第一段
    assert clip.timeline_range.end == pytest.approx(1.08, abs=0.1)


def test_remove_silence_noop_when_quiet_free(tmp_path: Path):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=red:s=320x240:d=2:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
         str(tmp_path / "loud.mp4")],
        check=True, capture_output=True,
    )
    core = ProjectCore.create(tmp_path, "noop-demo")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path=str(tmp_path / "loud.mp4"),
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
    ))
    cmd = CommandLayer(core)
    clip = cmd.add_clip("a1", 0.0, 2.0, timeline_start=0.0)
    op = cmd.remove_silence(clip.clip_id, min_duration=0.4)
    assert op.after["removed"] == []
    assert len(core.project.timeline.tracks[0].clip_ids) == 1  # 不乱切
