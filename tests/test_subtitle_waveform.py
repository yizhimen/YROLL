"""字幕轨编辑 + 波形/缩略图 测试。"""

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.server.app import create_app


@pytest.fixture
def proj(tmp_path: Path):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=green:s=320x240:d=2:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-map", "0:v", "-map", "1:a", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(tmp_path / "v.mp4")],
        check=True, capture_output=True)
    core = ProjectCore.create(tmp_path, "sub-demo")
    ProjectCore.ensure_default_tracks(core)
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path=str(tmp_path / "v.mp4"),
        identity=AssetIdentity(md5="y" * 32, size_bytes=1, duration_sec=2.0),
    ))
    core.save_state()
    return core


def test_add_and_edit_subtitle(proj):
    cmd = CommandLayer(proj, who=Actor.HUMAN)
    clip = cmd.add_subtitle("你好世界", 1.0, 3.0)
    assert clip.asset_id == ""
    assert clip.context["text"] == "你好世界"
    track = next(t for t in proj.project.timeline.tracks
                 if clip.clip_id in t.clip_ids)
    assert track.kind.value == "text"  # 自动建 text 轨

    op = cmd.edit_subtitle(clip.clip_id, "改后的字幕")
    assert op.type == "subtitle_edit"
    assert proj.project.clips[clip.clip_id].context["text"] == "改后的字幕"

    # 撤销改字 → 撤销加字幕（add_clip 现在也可撤销）
    proj.revert(op.operation_id)
    assert proj.project.clips[clip.clip_id].context["text"] == "你好世界"
    add_op = next(o for o in proj.operations()
                  if o.type == "add_clip" and o.target == clip.clip_id)
    proj.revert(add_op.operation_id)
    assert clip.clip_id not in proj.project.clips


def test_subtitle_rest_api(proj):
    from tests.conftest import _AuthedClient
    client = _AuthedClient(TestClient(create_app(proj.path)))
    r = client.post("/subtitles", params={"text": "接口字幕", "start": 0, "end": 1.5})
    assert r.status_code == 200
    clip_id = r.json()["clip_id"]
    r2 = client.post(f"/clips/{clip_id}/subtitle", params={"text": "改了"})
    assert r2.status_code == 200
    proj2 = ProjectCore.open(proj.path)
    assert proj2.project.clips[clip_id].context["text"] == "改了"


def test_waveform_api(proj):
    client = TestClient(create_app(proj.path))
    r = client.get("/assets/a1/waveform?points=50")
    assert r.status_code == 200
    peaks = r.json()["peaks"]
    assert 30 <= len(peaks) <= 60
    assert max(peaks) == pytest.approx(1.0, abs=0.01)  # 归一化
    # 缓存生效（第二次直接读 cache）
    assert (proj.path / "cache").glob("wave-*.json")
    r2 = client.get("/assets/a1/waveform?points=50")
    assert r2.json() == r.json()


def test_thumbnail_api(proj):
    client = TestClient(create_app(proj.path))
    r = client.get("/assets/a1/thumbnail?t=0.5")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert len(r.content) > 100  # 纯色画面 JPEG 很小但有效


def test_asset_file_range(proj):
    """即时预览的素材流：Range 请求 → 206 + Content-Range。"""
    client = TestClient(create_app(proj.path))
    r = client.get("/assets/a1/file", headers={"Range": "bytes=0-1023"})
    assert r.status_code == 206
    assert r.headers["content-range"].startswith("bytes 0-1023/")
    assert len(r.content) == 1024
    # 无 Range → 200 全量
    r2 = client.get("/assets/a1/file")
    assert r2.status_code == 200
    assert len(r2.content) > 1024


def test_subtitle_style_and_burn(proj, tmp_path: Path):
    """字幕样式：可设/可撤销；烧录真实生效（drawtext 带样式）。"""
    cmd = CommandLayer(proj, who=Actor.HUMAN)
    proj.project.clips  # noqa
    v = cmd.add_clip("a1", 0.0, 2.0, timeline_start=0.0)
    sub = cmd.add_subtitle("样式字幕", 0.5, 1.5)

    op = cmd.set_subtitle_style(sub.clip_id, {"size": 56, "position": "top"})
    assert proj.project.clips[sub.clip_id].context["style"]["size"] == 56
    proj.revert(op.operation_id)
    assert proj.project.clips[sub.clip_id].context["style"] == {}

    cmd.set_subtitle_style(sub.clip_id, {"size": 24, "color": "yellow"})
    from yroll.core.render import render_preview
    out = render_preview(proj, tmp_path / "burn.mp4", width=320, fps=30,
                         burn_subtitles=True)
    assert out.exists() and out.stat().st_size > 0


def test_generate_subtitles_from_transcript(proj, tmp_path: Path):
    """从转写自动生成字幕：源区间映射、幂等、可撤销。"""
    import json as _json

    # 伪造 ingest 的 Project Memory（extensions.memory 指针 + memory.json）
    mem_root = tmp_path / "memroot"
    mem_dir = mem_root / ".yroll" / "mem1"
    mem_dir.mkdir(parents=True)
    (mem_dir / "memory.json").write_text(_json.dumps({
        "transcripts": {
            "a1": [
                {"start": 0.2, "end": 1.0, "text": "第一句话"},
                {"start": 1.2, "end": 1.9, "text": "第二句话"},
                {"start": 5.0, "end": 6.0, "text": "区间外"},
            ]
        }
    }), encoding="utf-8")
    proj.project.extensions = {"memory": {"root": str(mem_root), "name": "mem1"}}

    cmd = CommandLayer(proj, who=Actor.AI)
    clip = cmd.add_clip("a1", 0.0, 2.0, timeline_start=1.0)  # 时间轴 1.0 起

    op = cmd.generate_subtitles()
    assert op.after["count"] == 2  # 区间外的不算

    text_track = next(t for t in proj.project.timeline.tracks
                      if t.kind.value == "text")
    subs = sorted((proj.project.clips[cid] for cid in text_track.clip_ids),
                  key=lambda c: c.timeline_range.start)
    assert subs[0].context["text"] == "第一句话"
    # 源 0.2 → 时间轴 1.0 + 0.2 = 1.2
    assert subs[0].timeline_range.start == pytest.approx(1.2, abs=0.01)
    assert subs[1].context["text"] == "第二句话"

    # 幂等：再跑一遍不重复生成
    op2 = cmd.generate_subtitles()
    assert op2.after["count"] == 0


def test_search_transcripts(proj, tmp_path: Path):
    """台词搜索：命中 → clip_id + 时间轴时间；区间外不命中。"""
    import json as _json

    mem_root = tmp_path / "memroot"
    mem_dir = mem_root / ".yroll" / "mem1"
    mem_dir.mkdir(parents=True)
    (mem_dir / "memory.json").write_text(_json.dumps({
        "transcripts": {
            "a1": [
                {"start": 0.5, "end": 1.0, "text": "景德镇柴烧窑变"},
                {"start": 5.0, "end": 6.0, "text": "区间外的柴烧"},
            ]
        }
    }), encoding="utf-8")
    proj.project.extensions = {"memory": {"root": str(mem_root), "name": "mem1"}}
    proj.save_state()

    cmd = CommandLayer(proj)
    cmd.add_clip("a1", 0.0, 2.0, timeline_start=10.0)

    client = TestClient(create_app(proj.path))
    r = client.get("/search-transcripts", params={"q": "柴烧"})
    hits = r.json()["results"]
    assert len(hits) == 1  # 区间外的不命中
    assert hits[0]["timeline"] == pytest.approx(10.5, abs=0.01)
    assert "景德镇" in hits[0]["text"]
