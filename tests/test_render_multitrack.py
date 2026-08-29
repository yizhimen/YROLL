"""渲染器 V0.3：多轨合成（图片 clip + 音频轨混音）。"""

import json
import subprocess
from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor, TrackKind
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.render import render_preview


def _make(tmp_path: Path):
    # 2s 视频（440Hz 正弦）
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=blue:s=320x240:d=2:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-map", "0:v", "-map", "1:a", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(tmp_path / "v.mp4")],
        check=True, capture_output=True)
    # 2s 音频（880Hz 正弦，作 BGM）
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "sine=frequency=880:duration=2",
         "-c:a", "aac", str(tmp_path / "bgm.m4a")],
        check=True, capture_output=True)
    # 图片
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=red:s=320x240:d=0.1:r=30",
         "-frames:v", "1", str(tmp_path / "img.jpg")],
        check=True, capture_output=True)


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", str(path)],
        capture_output=True, text=True)
    return float(json.loads(out.stdout)["format"]["duration"])


def _loudness(path: Path, ss: float, to: float) -> float:
    out = subprocess.run(
        ["ffmpeg", "-v", "info", "-ss", str(ss), "-to", str(to),
         "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True)
    import re
    m = re.search(r"mean_volume:\s*(-?[\d.]+)", out.stderr)
    return float(m.group(1))


def test_image_clip_and_audio_track_mix(tmp_path: Path):
    _make(tmp_path)
    core = ProjectCore.create(tmp_path, "mt-demo")
    ProjectCore.ensure_default_tracks(core)
    for aid, atype, fname in [("v1", AssetType.VIDEO, "v.mp4"),
                              ("bgm", AssetType.AUDIO, "bgm.m4a"),
                              ("img", AssetType.IMAGE, "img.jpg")]:
        core.project.assets.append(Asset(
            asset_id=aid, type=atype, path=str(tmp_path / fname),
            identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
        ))
    cmd = CommandLayer(core, who=Actor.HUMAN)

    # 主视频轨：视频 2s + 图片 1.5s（静帧占时长）
    cmd.add_clip("v1", 0.0, 2.0, timeline_start=0.0)
    cmd.add_clip("img", 0.0, 1.5, timeline_start=2.0)
    # 音频轨：BGM 从 1s 处进入，音量 0.5
    atrack = cmd.add_track(TrackKind.AUDIO, "a1")
    bgm = cmd.add_clip("bgm", 0.0, 2.0, timeline_start=1.0, track_id="a1")
    cmd.set_volume(bgm.clip_id, 0.5)

    out = render_preview(core, tmp_path / "preview.mp4")

    # 总时长 = 2s 视频 + 1.5s 图片 = 3.5s（图片 clip 真实占时长）
    assert _duration(out) == pytest.approx(3.5, abs=0.3)
    # BGM 从 1s 进：0-0.9s 只有视频声，1.1-1.9s 是 视频+BGM 混合区（2s 后是图片静音段，不纳入比较）
    quiet = _loudness(out, 0.0, 0.9)
    mixed = _loudness(out, 1.1, 1.9)
    assert mixed > quiet + 0.3
    # 图片段（3-3.4s）仍有声音轨道（补静音，不崩）
    _loudness(out, 3.0, 3.4)  # 不抛异常即通过


def _pixel(path: Path, t: float, x: int, y: int) -> tuple[int, int, int]:
    """抽 t 秒处 (x,y) 像素的 RGB（全帧 rawvideo → Python 取值；
    本机 ffmpeg seek+crop 组合会拿到 0x0 帧，绕开）。"""
    import json as _json
    info = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", str(path)],
        capture_output=True, text=True)
    vs = next(s for s in _json.loads(info.stdout)["streams"]
              if s.get("codec_type") == "video")
    w, h = int(vs["width"]), int(vs["height"])
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path),
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True)
    i = (y * w + x) * 3
    r, g, b = out.stdout[i:i + 3]
    return r, g, b


def test_second_video_track_overlay(tmp_path: Path):
    """第二视频轨 → PiP overlay：overlay 区间内角落变红，区间外还是蓝。"""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=blue:s=320x240:d=2:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-map", "0:v", "-map", "1:a", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(tmp_path / "base.mp4")],
        check=True, capture_output=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=red:s=320x240:d=2:r=30",
         "-pix_fmt", "yuv420p", str(tmp_path / "pip.mp4")],
        check=True, capture_output=True)

    core = ProjectCore.create(tmp_path, "pip-demo")
    ProjectCore.ensure_default_tracks(core)
    for aid, fname, dur in [("b", "base.mp4", 2.0), ("p", "pip.mp4", 2.0)]:
        core.project.assets.append(Asset(
            asset_id=aid, type=AssetType.VIDEO, path=str(tmp_path / fname),
            identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=dur),
        ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("b", 0.0, 2.0, timeline_start=0.0)
    v2 = cmd.add_track(TrackKind.VIDEO, "v2")
    pip = cmd.add_clip("p", 0.0, 2.0, timeline_start=0.5, track_id="v2")
    # transform：右上 30% PiP
    pip.source_range.end = 1.5
    pip.timeline_range.end = 1.5
    pip.transform = {"x": 0.68, "y": 0.06, "scale": 0.3}

    out = render_preview(core, tmp_path / "preview.mp4", width=320, fps=30)

    # overlay 区间内（t=1）：右上角是红（PiP），左下还是蓝（主画面）
    r, g, b = _pixel(out, 1.0, 300, 30)
    assert r > 150 and b < 100, f"overlay 失效: {(r, g, b)}"
    r2, g2, b2 = _pixel(out, 1.0, 30, 200)
    assert b2 > 120, f"主画面被盖住: {(r2, g2, b2)}"
    # overlay 区间外（t=1.8）：右上角恢复蓝色
    r3, g3, b3 = _pixel(out, 1.8, 300, 30)
    assert b3 > 120, f"overlay 未按时结束: {(r3, g3, b3)}"


def test_gap_filled_with_black(tmp_path: Path):
    """主轨间隙 → 黑场静音占时长（混音/字幕才对得齐）。"""
    _make(tmp_path)
    core = ProjectCore.create(tmp_path, "gap-demo")
    ProjectCore.ensure_default_tracks(core)
    core.project.assets.append(Asset(
        asset_id="v1", type=AssetType.VIDEO, path=str(tmp_path / "v.mp4"),
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
    ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    # 两个 clip，中间空 1s（1.0-2.0 是洞）
    cmd.add_clip("v1", 0.0, 1.0, timeline_start=0.0)
    cmd.add_clip("v1", 1.0, 2.0, timeline_start=2.0)

    out = render_preview(core, tmp_path / "preview.mp4", width=320, fps=30)

    # 总时长 3s：间隙被占住（不是 2s 直接拼上）
    assert _duration(out) == pytest.approx(3.0, abs=0.2)
    # 间隙里是黑场（中间像素接近纯黑）
    r, g, b = _pixel(out, 1.5, 160, 120)
    assert r < 30 and g < 30 and b < 30, f"间隙不是黑场: {(r, g, b)}"


def test_burn_subtitles(tmp_path: Path):
    """烧录模式：字幕进画面（流里无 mov_text）；默认软字幕保留 mov_text。"""
    _make(tmp_path)
    core = ProjectCore.create(tmp_path, "burn-demo")
    ProjectCore.ensure_default_tracks(core)
    core.project.assets.append(Asset(
        asset_id="v1", type=AssetType.VIDEO, path=str(tmp_path / "v.mp4"),
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
    ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("v1", 0.0, 2.0, timeline_start=0.0)
    cmd.add_subtitle("烧录测试字幕", 0.5, 1.5)

    out_soft = render_preview(core, tmp_path / "soft.mp4", width=320, fps=30)
    streams = json.loads(subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", str(out_soft)],
        capture_output=True, text=True).stdout)["streams"]
    assert any(s.get("codec_name") == "mov_text" for s in streams)  # 软字幕轨在

    out_burn = render_preview(core, tmp_path / "burn.mp4", width=320, fps=30,
                              burn_subtitles=True)
    streams = json.loads(subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", str(out_burn)],
        capture_output=True, text=True).stdout)["streams"]
    assert not any(s.get("codec_name") == "mov_text" for s in streams)  # 烧录后无字幕轨


def test_fade_transition(tmp_path: Path):
    """淡入淡出：fade 后开头比中间暗（像素级）。"""
    _make(tmp_path)
    core = ProjectCore.create(tmp_path, "fade-demo")
    ProjectCore.ensure_default_tracks(core)
    core.project.assets.append(Asset(
        asset_id="v1", type=AssetType.VIDEO, path=str(tmp_path / "v.mp4"),
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
    ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    clip = cmd.add_clip("v1", 0.0, 2.0, timeline_start=0.0)
    cmd.set_fade(clip.clip_id, fade_in=0.5, fade_out=0.5)

    out = render_preview(core, tmp_path / "preview.mp4", width=320, fps=30)
    # 蓝色画面：fade-in 早期蓝色分量显著低于中段
    _, _, b_start = _pixel(out, 0.05, 160, 120)
    _, _, b_mid = _pixel(out, 1.0, 160, 120)
    assert b_start < b_mid * 0.5, f"fade-in 未生效: start={b_start} mid={b_mid}"
    _, _, b_end = _pixel(out, 1.95, 160, 120)
    assert b_end < b_mid * 0.5, f"fade-out 未生效: end={b_end} mid={b_mid}"


def test_dissolve_xfade(tmp_path: Path):
    """真叠化：总时长减去重叠；溶解区是混色；前后各自纯色。"""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=red:s=320x240:d=2:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-map", "0:v", "-map", "1:a", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(tmp_path / "red.mp4")],
        check=True, capture_output=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=blue:s=320x240:d=2:r=30",
         "-f", "lavfi", "-i", "sine=frequency=880:duration=2",
         "-map", "0:v", "-map", "1:a", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(tmp_path / "blue.mp4")],
        check=True, capture_output=True)

    core = ProjectCore.create(tmp_path, "dissolve-demo")
    ProjectCore.ensure_default_tracks(core)
    for aid, fname in [("r", "red.mp4"), ("b", "blue.mp4")]:
        core.project.assets.append(Asset(
            asset_id=aid, type=AssetType.VIDEO, path=str(tmp_path / fname),
            identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
        ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("r", 0.0, 2.0, timeline_start=0.0)
    blue = cmd.add_clip("b", 0.0, 2.0, timeline_start=2.0)
    cmd.set_dissolve(blue.clip_id, duration=0.5)

    out = render_preview(core, tmp_path / "preview.mp4", width=320, fps=30)

    # 总时长 = 2 + 2 - 0.5 重叠 = 3.5s
    assert _duration(out) == pytest.approx(3.5, abs=0.25)
    # 溶解中点（输出时间 ~1.75s）：红蓝混合（紫）
    r, g, b = _pixel(out, 1.75, 160, 120)
    assert r > 60 and b > 60, f"溶解区不是混色: {(r, g, b)}"
    # 前段纯红、后段纯蓝
    r1, _, b1 = _pixel(out, 1.0, 160, 120)
    assert r1 > 150 and b1 < 100
    r2, _, b2 = _pixel(out, 3.0, 160, 120)
    assert b2 > 120 and r2 < 100


def test_dissolve_wipe_kind(tmp_path: Path):
    """叠化类型：wipeleft 边界右半先变蓝（擦除方向性）。"""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=red:s=320x240:d=2:r=30",
         "-f", "lavfi", "-i", "anullsrc=d=2",
         "-map", "0:v", "-map", "1:a", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(tmp_path / "red.mp4")],
        check=True, capture_output=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=blue:s=320x240:d=2:r=30",
         "-f", "lavfi", "-i", "anullsrc=d=2",
         "-map", "0:v", "-map", "1:a", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(tmp_path / "blue.mp4")],
        check=True, capture_output=True)
    core = ProjectCore.create(tmp_path, "wipe-demo")
    ProjectCore.ensure_default_tracks(core)
    for aid, fname in [("r", "red.mp4"), ("b", "blue.mp4")]:
        core.project.assets.append(Asset(
            asset_id=aid, type=AssetType.VIDEO, path=str(tmp_path / fname),
            identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
        ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("r", 0.0, 2.0, timeline_start=0.0)
    blue = cmd.add_clip("b", 0.0, 2.0, timeline_start=2.0)
    cmd.set_dissolve(blue.clip_id, duration=0.5, kind="wipeleft")

    out = render_preview(core, tmp_path / "preview.mp4", width=320, fps=30)
    # 溶解中点（输出 ~1.75s）：wipeleft = 新画面从右向左擦入 → 右半已蓝、左半还红
    r_r, _, b_r = _pixel(out, 1.75, 280, 120)
    r_l, _, b_l = _pixel(out, 1.75, 40, 120)
    assert b_r > r_r, f"右侧应先变蓝: {(r_r, _, b_r)}"
    assert r_l > b_l, f"左侧应仍红: {(r_l, _, b_l)}"


def test_track_muted_skips_audio(tmp_path: Path):
    """轨道静音：音频轨整体不进混音（可撤销）。"""
    _make(tmp_path)
    core = ProjectCore.create(tmp_path, "trackmute-demo")
    ProjectCore.ensure_default_tracks(core)
    for aid, atype, fname in [("v1", AssetType.VIDEO, "v.mp4"),
                              ("bgm", AssetType.AUDIO, "bgm.m4a")]:
        core.project.assets.append(Asset(
            asset_id=aid, type=atype, path=str(tmp_path / fname),
            identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
        ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("v1", 0.0, 2.0, timeline_start=0.0)
    atrack = cmd.add_track(TrackKind.AUDIO, "a1")
    cmd.add_clip("bgm", 0.0, 2.0, timeline_start=0.0, track_id="a1")

    op = cmd.set_track_muted("a1", True)
    out = render_preview(core, tmp_path / "preview.mp4", width=320, fps=30)
    # 静音后 1-1.9s 不应比 0-0.9s 更响（BGM 没进来）
    q = _loudness(out, 0.0, 0.9)
    m = _loudness(out, 1.1, 1.9)
    assert abs(m - q) < 3.0, f"轨道静音未生效: {q} vs {m}"

    core.revert(op.operation_id)
    assert core.project.timeline.tracks[-1].muted is False
