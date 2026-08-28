"""Publish Package + Cost 聚合测试。"""

import json
import subprocess
from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.publish import export_package


@pytest.fixture
def proj(tmp_path: Path):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=blue:s=320x240:d=2:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-map", "0:v", "-map", "1:a", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(tmp_path / "v.mp4")],
        check=True, capture_output=True)
    core = ProjectCore.create(tmp_path, "pub-demo")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path=str(tmp_path / "v.mp4"),
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=2.0),
    ))
    return core


def test_export_package(proj, tmp_path: Path):
    cmd = CommandLayer(proj, who=Actor.AI)
    clip = cmd.add_clip("a1", 0.0, 2.0, timeline_start=0.0)
    cmd.set_volume(clip.clip_id, 0.8)
    proj.commit("导出前存档")

    out = tmp_path / "pkg"
    report = export_package(proj, out, width=320)

    # 三件套齐全
    assert (out / "video.mp4").exists() and (out / "video.mp4").stat().st_size > 0
    assert (out / "cover.jpg").exists() and (out / "cover.jpg").stat().st_size > 100
    r = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert r["project"] == "pub-demo"
    assert r["history"]["operations"] >= 2
    assert r["history"]["versions"] == 1
    assert r["history"]["by_who"]["ai"] >= 1
    assert r["spec"]["duration_sec"] == pytest.approx(2.0, abs=0.2)
    assert r["content"]["clips"] == 1


def test_costs_endpoint(proj):
    from fastapi.testclient import TestClient

    from yroll.core.commands import CommandLayer
    from yroll.server.app import create_app

    cmd = CommandLayer(proj, who=Actor.AI)
    clip = cmd.add_clip("a1", 0.0, 2.0, timeline_start=0.0)
    # 造一条带成本的 op
    cmd._record("voice_replace", clip.clip_id, {}, {"text": "x"},
                cost=0.05, tool="voice.clone_replace")

    client = TestClient(create_app(proj.path))
    r = client.get("/costs").json()
    assert r["total"] == pytest.approx(0.05, abs=0.001)
    assert r["by_tool"]["voice.clone_replace"]["cost"] == pytest.approx(0.05, abs=0.001)
    assert r["by_who"]["ai"] == pytest.approx(0.05, abs=0.001)
