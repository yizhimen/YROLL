"""剪映草稿导入测试。"""

import json
import subprocess
from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.project import ProjectCore
from yroll.ingest.jianying import import_jianying_draft

_US = 1_000_000


@pytest.fixture
def draft(tmp_path: Path):
    # 造素材
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=red:s=320x240:d=4:r=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
         "-map", "0:v", "-map", "1:a", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(tmp_path / "m1.mp4")],
        check=True, capture_output=True)
    d = tmp_path / "draft"
    d.mkdir()
    content = {
        "materials": {
            "videos": [
                {"id": "mat1", "type": "video", "path": str(tmp_path / "m1.mp4"),
                 "duration": 4 * _US, "width": 320, "height": 240},
            ]
        },
        "tracks": [
            {"type": "video", "segments": [
                {"material_id": "mat1",
                 "source_timerange": {"start": 1 * _US, "duration": 2 * _US},
                 "target_timerange": {"start": 0, "duration": 2 * _US}},
                {"material_id": "mat1",
                 "source_timerange": {"start": 0, "duration": 1 * _US},
                 "target_timerange": {"start": 2 * _US, "duration": 1 * _US},
                 "speed": {"speed": 2.0}},
            ]},
            {"type": "text", "segments": []},  # 不支持轨 → skipped
        ],
    }
    (d / "draft_content.json").write_text(
        json.dumps(content, ensure_ascii=False), encoding="utf-8")
    return d, tmp_path


def test_import_jianying(draft):
    d, tmp_path = draft
    core = ProjectCore.create(tmp_path, "jy-demo")
    ProjectCore.ensure_default_tracks(core)
    cmd = CommandLayer(core)

    stats = import_jianying_draft(cmd, d)
    assert stats["tracks"] == 1
    assert stats["clips"] == 2
    assert stats["assets"] == 1
    assert stats["skipped"] == 1  # text 轨

    track = next(t for t in core.project.timeline.tracks if t.track_id == "jy1")
    c1 = core.project.clips[track.clip_ids[0]]
    assert c1.source_range.start == pytest.approx(1.0)
    assert c1.source_range.end == pytest.approx(3.0)
    assert c1.timeline_range.start == 0.0
    c2 = core.project.clips[track.clip_ids[1]]
    assert c2.speed == 2.0
    assert c2.timeline_range.start == pytest.approx(2.0)

    # 重复导入：素材指纹去重不重复登记
    stats2 = import_jianying_draft(cmd, d)
    assert stats2["assets"] == 0
    assert len(core.project.assets) == 1


def test_import_jianying_not_draft(tmp_path: Path):
    from yroll.core.commands import CommandError

    core = ProjectCore.create(tmp_path, "jy-bad")
    ProjectCore.ensure_default_tracks(core)
    with pytest.raises(CommandError, match="draft_content"):
        import_jianying_draft(CommandLayer(core), tmp_path)
