"""画面/位置调整（CapCut 式）：像素级渲染验证。"""

import subprocess
from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.render import render_preview
from tests.test_render_multitrack import _pixel


def _halfvideo(path: Path) -> None:
    """左红右蓝的 2s 视频（验证翻转/裁剪的坐标变化）。"""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=red:s=160x240:d=2:r=30",
         "-f", "lavfi", "-i", "color=blue:s=160x240:d=2:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-filter_complex", "[0:v][1:v]hstack[v]",
         "-map", "[v]", "-map", "2:a", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(path)],
        check=True, capture_output=True)


@pytest.fixture
def proj(tmp_path: Path):
    _halfvideo(tmp_path / "half.mp4")
    core = ProjectCore.create(tmp_path, "va-demo")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path=str(tmp_path / "half.mp4"),
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
    ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    clip = cmd.add_clip("a1", 0.0, 2.0, timeline_start=0.0)
    return core, cmd, clip, tmp_path


def test_brightness_and_opacity(proj):
    core, cmd, clip, tmp_path = proj
    cmd.set_color(clip.clip_id, brightness=-0.3)
    out = render_preview(core, tmp_path / "o.mp4", width=320, fps=30)
    r_dark, _, _ = _pixel(out, 1.0, 80, 120)
    core.revert(cmd.core.operations()[-1].operation_id)
    cmd.set_opacity(clip.clip_id, 0.5)
    out2 = render_preview(core, tmp_path / "o2.mp4", width=320, fps=30)
    r_dim, _, _ = _pixel(out2, 1.0, 80, 120)
    r_orig, _, _ = _pixel(render_preview(core, tmp_path / "o3.mp4", width=320, fps=30), 1.0, 80, 120) if False else (None, None, None)
    assert r_dark < 200 and r_dim < 200  # 原红(~229)被压暗


def test_flip_horizontal(proj):
    core, cmd, clip, tmp_path = proj
    cmd.set_flip(clip.clip_id, horizontal=True)
    out = render_preview(core, tmp_path / "o.mp4", width=320, fps=30)
    # 原本左红右蓝 → 翻转后左蓝右红
    r_l, _, b_l = _pixel(out, 1.0, 40, 120)
    r_r, _, b_r = _pixel(out, 1.0, 280, 120)
    assert b_l > r_l, f"左侧应变蓝: {(r_l, _, b_l)}"
    assert r_r > b_r, f"右侧应变红: {(r_r, _, b_r)}"


def test_transform2d_scale_blur_bg(proj):
    core, cmd, clip, tmp_path = proj
    cmd.set_transform2d(clip.clip_id, scale=0.5, bg_blur=True)
    out = render_preview(core, tmp_path / "o.mp4", width=320, fps=30)
    # 中心偏左（fg 缩小后的左半）仍是红
    r_c, _, b_c = _pixel(out, 1.0, 100, 120)
    assert r_c > b_c, f"中心偏左应偏红: {(r_c, _, b_c)}"

    # 黑底变体：同工程撤销后换黑底，角落应变黑
    core.revert(cmd.core.operations()[-1].operation_id)
    cmd.set_transform2d(clip.clip_id, scale=0.5, bg_blur=False)
    out2 = render_preview(core, tmp_path / "o2.mp4", width=320, fps=30)
    r_e, g_e, b_e = _pixel(out2, 1.0, 5, 5)
    assert r_e < 40 and g_e < 40 and b_e < 40, f"黑底模式角落应黑: {(r_e, g_e, b_e)}"


def test_crop_zooms_back(proj):
    core, cmd, clip, tmp_path = proj
    # 裁掉左半的 45%（红区大部分）→ 蓝区占左
    cmd.set_crop(clip.clip_id, left=0.45)
    out = render_preview(core, tmp_path / "o.mp4", width=320, fps=30)
    _, _, b_l = _pixel(out, 1.0, 40, 120)
    assert b_l > 100, f"裁左后左侧应偏蓝: b={b_l}"


def test_reverse_adjustment(proj):
    core, cmd, clip, tmp_path = proj
    op = cmd.set_reverse(clip.clip_id)
    assert any(a["kind"] == "reverse" for a in
               core.project.clips[clip.clip_id].adjustments)
    out = render_preview(core, tmp_path / "o.mp4", width=320, fps=30)
    assert out.exists() and out.stat().st_size > 0  # reverse 链真实可渲染
