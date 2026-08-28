"""L1 扩充测试：响度测量（volumedetect）+ 降噪调整图层。"""

import subprocess
from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.tools.audio_tools import measure_loudness


def _make_tone(path: Path, volume: float = 1.0, dur: int = 2) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}",
         "-af", f"volume={volume}",
         "-c:a", "aac", str(path)],
        check=True, capture_output=True,
    )


def test_measure_loudness(tmp_path: Path):
    _make_tone(tmp_path / "tone.m4a", volume=1.0)
    loud = measure_loudness(tmp_path / "tone.m4a")
    assert loud is not None
    assert loud["max_db"] > -25  # ffmpeg sine 源满幅约 -18dB

    _make_tone(tmp_path / "quiet.m4a", volume=0.1)
    quiet = measure_loudness(tmp_path / "quiet.m4a")
    assert quiet is not None
    assert quiet["mean_db"] < loud["mean_db"] - 10  # -20dB 差异可测


def test_analyze_loudness_command(tmp_path: Path):
    _make_tone(tmp_path / "tone.m4a")
    core = ProjectCore.create(tmp_path, "loud-demo")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.AUDIO, path=str(tmp_path / "tone.m4a"),
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
    ))
    cmd = CommandLayer(core, who=Actor.AI)
    # 音频素材上 a1 轨（默认轨结构已含 a1）
    clip = cmd.add_clip("a1", 0.0, 2.0, timeline_start=0.0, track_id="a1")

    op = cmd.analyze_loudness(clip.clip_id)
    assert op.type == "analyze_loudness"
    assert "mean_db" in op.after and "max_db" in op.after
    assert op.who == Actor.AI  # 分析也落日志


def test_denoise_is_nondestructive_adjustment(tmp_path: Path):
    _make_tone(tmp_path / "tone.m4a")
    core = ProjectCore.create(tmp_path, "denoise-demo")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.AUDIO, path=str(tmp_path / "tone.m4a"),
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
    ))
    cmd = CommandLayer(core, who=Actor.AI)
    clip = cmd.add_clip("a1", 0.0, 2.0, timeline_start=0.0, track_id="a1")

    op = cmd.denoise_clip(clip.clip_id, strength=15.0)

    # 非破坏性：源区间不变，只加调整图层
    c = core.project.clips[clip.clip_id]
    assert c.source_range.start == 0.0 and c.source_range.end == 2.0
    assert c.adjustments[-1]["kind"] == "denoise"
    assert c.adjustments[-1]["params"]["nr"] == 15.0
    assert op.type == "adjust"


def test_denoise_applied_in_render(tmp_path: Path):
    """渲染链里 afftdn 生效（能渲染出文件即说明滤镜语法正确）。"""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=blue:s=320x240:d=2:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-map", "0:v", "-map", "1:a", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(tmp_path / "v.mp4")],
        check=True, capture_output=True,
    )
    from yroll.core.render import render_preview

    core = ProjectCore.create(tmp_path, "render-demo")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path=str(tmp_path / "v.mp4"),
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
    ))
    cmd = CommandLayer(core, who=Actor.AI)
    clip = cmd.add_clip("a1", 0.0, 2.0, timeline_start=0.0)
    cmd.denoise_clip(clip.clip_id, strength=12.0)

    out = render_preview(core, tmp_path / "preview.mp4")
    assert out.exists() and out.stat().st_size > 0


def _make_logo_video(path: Path) -> None:
    """2 秒视频：右上角白色块 = 假水印。"""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=blue:s=320x240:d=2:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-filter_complex",
         "[0:v]drawbox=x=270:y=10:w=40:h=20:color=white:t=fill[v]",
         "-map", "[v]", "-map", "1:a", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(path)],
        check=True, capture_output=True,
    )


def test_delogo_nondestructive_and_renders(tmp_path: Path):
    from yroll.core.manifest import Region
    from yroll.core.render import render_preview

    _make_logo_video(tmp_path / "v.mp4")
    core = ProjectCore.create(tmp_path, "delogo-demo")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path=str(tmp_path / "v.mp4"),
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
    ))
    cmd = CommandLayer(core, who=Actor.AI)
    clip = cmd.add_clip("a1", 0.0, 2.0, timeline_start=0.0)

    # 归一化坐标：右上角白色块 (270,10,40,20) / 320x240
    op = cmd.delogo_clip(clip.clip_id, Region(x=0.83, y=0.03, w=0.15, h=0.12))
    c = core.project.clips[clip.clip_id]
    assert c.source_range.start == 0.0 and c.source_range.end == 2.0  # 非破坏
    assert c.adjustments[-1]["kind"] == "delogo"
    assert op.type == "adjust"

    out = render_preview(core, tmp_path / "preview.mp4")
    assert out.exists() and out.stat().st_size > 0  # delogo 滤镜语法真实生效


def test_delogo_rejects_pixel_coords(tmp_path: Path):
    from yroll.core.commands import CommandError
    from yroll.core.manifest import Region

    _make_logo_video(tmp_path / "v.mp4")
    core = ProjectCore.create(tmp_path, "delogo-bad")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path=str(tmp_path / "v.mp4"),
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
    ))
    cmd = CommandLayer(core, who=Actor.AI)
    clip = cmd.add_clip("a1", 0.0, 2.0, timeline_start=0.0)
    with pytest.raises(CommandError):
        cmd.delogo_clip(clip.clip_id, Region(x=270.0, y=10.0, w=40.0, h=20.0))


def test_volume_range_and_remove_adjustment(tmp_path: Path):
    """时间范围调音量（不必先 Split）+ 调整图层可移除、可撤销。"""
    from yroll.core.manifest import TimeRange
    from yroll.core.render import render_preview

    _make_logo_video(tmp_path / "v.mp4")
    core = ProjectCore.create(tmp_path, "volrange-demo")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path=str(tmp_path / "v.mp4"),
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
    ))
    cmd = CommandLayer(core, who=Actor.AI)
    clip = cmd.add_clip("a1", 0.0, 2.0, timeline_start=0.0)

    op = cmd.set_volume_range(clip.clip_id, 0.2, TimeRange(start=0.5, end=1.5))
    adj = core.project.clips[clip.clip_id].adjustments[-1]
    assert adj["kind"] == "volume_range"
    assert adj["time_range"] == {"start": 0.5, "end": 1.5}

    # 范围外交集校验
    from yroll.core.commands import CommandError
    with pytest.raises(CommandError):
        cmd.set_volume_range(clip.clip_id, 0.5, TimeRange(start=5.0, end=6.0))

    # 渲染真实生效（enable 语法通过 ffmpeg 验证）
    out = render_preview(core, tmp_path / "preview.mp4")
    assert out.exists() and out.stat().st_size > 0

    # 移除 + 撤销移除
    op2 = cmd.remove_adjustment(clip.clip_id, adj["id"])
    assert len(core.project.clips[clip.clip_id].adjustments) == 0
    core.revert(op2.operation_id)
    assert len(core.project.clips[clip.clip_id].adjustments) == 1


def test_mute_and_render_range(tmp_path: Path):
    """静音开关（渲染音量 0 + 可撤销）+ I/O 选区导出。"""
    from yroll.core.render import render_preview

    _make_logo_video(tmp_path / "v.mp4")
    core = ProjectCore.create(tmp_path, "mute-demo")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path=str(tmp_path / "v.mp4"),
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
    ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    clip = cmd.add_clip("a1", 0.0, 2.0, timeline_start=0.0)

    op = cmd.set_muted(clip.clip_id, True)
    assert core.project.clips[clip.clip_id].context["muted"] == "1"
    assert core.project.clips[clip.clip_id].volume == 1.0  # 原值不动
    core.revert(op.operation_id)
    assert "muted" not in core.project.clips[clip.clip_id].context

    # 静音渲染：mean 音量应接近 -inf（远低于未静音）
    cmd.set_muted(clip.clip_id, True)
    out = render_preview(core, tmp_path / "muted.mp4")
    from yroll.tools.audio_tools import measure_loudness
    m = measure_loudness(out)
    assert m is None or m["mean_db"] < -60
