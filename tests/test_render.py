"""渲染器测试：合成素材 → Command Layer 建 Timeline → FFmpeg 渲染。"""

import subprocess
from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.render import render_preview


def _make_video(path: Path, color: str, seconds: float) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", f"color={color}:s=320x240:d={seconds}:r=30",
         "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )


def _register_asset(core: ProjectCore, path: Path) -> Asset:
    asset = Asset(
        asset_id=path.stem,
        type=AssetType.VIDEO,
        path=str(path),
        identity=AssetIdentity(md5="x" * 32, size_bytes=path.stat().st_size,
                               duration_sec=2.0, width=320, height=240),
    )
    core.project.assets.append(asset)
    return asset


def test_render_preview(tmp_path: Path):
    _make_video(tmp_path / "red.mp4", "red", 2)
    _make_video(tmp_path / "blue.mp4", "blue", 2)

    core = ProjectCore.create(tmp_path, "render-demo")
    cmd = CommandLayer(core, who=Actor.AI)
    a1 = _register_asset(core, tmp_path / "red.mp4")
    a2 = _register_asset(core, tmp_path / "blue.mp4")

    c1 = cmd.add_clip(a1.asset_id, 0.0, 2.0, timeline_start=0.0)
    cmd.add_clip(a2.asset_id, 0.5, 2.0, timeline_start=2.0)  # 裁前 0.5s
    cmd.set_speed(c1.clip_id, 2.0)  # 2s → 1s

    # 字幕轨道（text clip 不需要素材文件）
    from yroll.core.manifest import TrackKind

    cmd.add_track(TrackKind.TEXT, "t1")
    sub = cmd.add_clip("", 0.0, 2.5, timeline_start=0.0, track_id="t1")
    sub.context["text"] = "柴烧窑变 · 每一只都独一无二"

    out = render_preview(core, tmp_path / "out.mp4", width=320)
    assert out.exists() and out.stat().st_size > 0

    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", str(out)],
        capture_output=True, text=True,
    )
    import json

    data = json.loads(probe.stdout)
    duration = float(data["format"]["duration"])
    # 1s(2x) + 1s 间隙黑场（1.0-2.0 的洞现在被占住）+ 1.5s
    assert duration == pytest.approx(3.5, abs=0.3)
    codecs = [s["codec_type"] for s in data["streams"]]
    assert "video" in codecs
    assert "audio" in codecs  # 无音轨素材自动补静音
    assert "subtitle" in codecs  # 字幕软封装
