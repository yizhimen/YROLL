"""Semantic Timeline Diff tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.diff import (
    ChangeKind, ClipChange, TimelineDiff, diff_projects,
)
from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational


FPS = Rational(30, 1)


@pytest.fixture()
def core(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "diff-test")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=60.0),
    ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)
    cmd.add_clip("a1", 10.0, 20.0, timeline_start=10.0)
    return core


def test_diff_detects_move():
    from copy import deepcopy
    core = ProjectCore.create(Path("/tmp"), "x")  # placeholder
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)
    before = deepcopy(core.project)
    # Move by +12 frames @ 30fps = +0.4s
    c = next(iter(core.project.clips.values()))
    cmd.move_clip(c.clip_id, new_timeline_start=0.4)
    after = deepcopy(core.project)
    diff = diff_projects(before, after, FPS,
                          from_revision=0, to_revision=2)
    moves = [c for c in diff.changes if c.kind == ChangeKind.MOVED]
    assert len(moves) == 1
    assert moves[0].delta_frames == 12  # 0.4s = 12 frames


def test_diff_detects_trim():
    from copy import deepcopy
    core = ProjectCore.create(Path("/tmp"), "y")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=60.0),
    ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)
    before = deepcopy(core.project)
    c = next(iter(core.project.clips.values()))
    cmd.trim_clip(c.clip_id, new_source_start=2.0)
    after = deepcopy(core.project)
    diff = diff_projects(before, after, FPS)
    trims = [c for c in diff.changes if c.kind == ChangeKind.TRIMMED]
    assert len(trims) == 1


def test_diff_detects_added_and_removed():
    from copy import deepcopy
    core = ProjectCore.create(Path("/tmp"), "z")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=60.0),
    ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    c1 = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    before = deepcopy(core.project)
    cmd.remove_clip(c1.clip_id)
    after = deepcopy(core.project)
    diff = diff_projects(before, after, FPS)
    assert any(c.kind == ChangeKind.REMOVED for c in diff.changes)


def test_diff_summary():
    diff = TimelineDiff(from_revision=0, to_revision=5)
    diff.changes.append(ClipChange("c1", "v1", ChangeKind.MOVED, "x"))
    diff.changes.append(ClipChange("c2", "v1", ChangeKind.MOVED, "x"))
    diff.changes.append(ClipChange("c3", "t1", ChangeKind.TRIMMED, "x"))
    diff.changes.append(ClipChange("c4", "a1", ChangeKind.ADDED, "x"))
    diff.changes.append(ClipChange("c5", "v1", ChangeKind.UNCHANGED, "x"))
    assert "2 added" not in diff.summary()
    assert "2 moved" in diff.summary()
    assert "1 trimmed" in diff.summary()
    assert "1 added" in diff.summary()


def test_diff_empty_projects():
    from yroll.core.manifest import Project
    p = Project(project_id="p1", name="empty")
    diff = diff_projects(p, p, FPS)
    assert diff.summary() == "no changes"
