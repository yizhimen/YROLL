"""P1 Slip / Roll / Slide mutation tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.commands import CommandError, CommandLayer
from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore


@pytest.fixture()
def core(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "slip-test")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=60.0),
    ))
    return core


def test_slip_shifts_source_keeps_timeline(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    c = cmd.add_clip("a1", 0.0, 5.0, timeline_start=10.0)
    orig_sr = c.source_range.model_dump()
    orig_tr = c.timeline_range.model_dump()

    op = cmd.slip_clip(c.clip_id, delta_seconds=2.0)

    assert op.type == "slip"
    # Source shifted by +2
    assert core.project.clips[c.clip_id].source_range.start == pytest.approx(2.0)
    assert core.project.clips[c.clip_id].source_range.end == pytest.approx(7.0)
    # Timeline unchanged
    assert core.project.clips[c.clip_id].timeline_range.start == orig_tr["start"]
    assert core.project.clips[c.clip_id].timeline_range.end == orig_tr["end"]
    # Op captures both
    assert op.before["source_range"] == orig_sr


def test_slip_negative_raises(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    c = cmd.add_clip("a1", 5.0, 15.0, timeline_start=0.0)
    with pytest.raises(CommandError):
        cmd.slip_clip(c.clip_id, delta_seconds=-10.0)  # would push src_start to -5


def test_roll_moves_boundary(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    c1 = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    c2 = cmd.add_clip("a1", 5.0, 10.0, timeline_start=5.0)

    op = cmd.roll_clip(c1.clip_id, c2.clip_id, delta_seconds=1.0)

    assert op.type == "roll"
    # c1 grows by 1s, c2 starts 1s later
    assert core.project.clips[c1.clip_id].timeline_range.end == pytest.approx(6.0)
    assert core.project.clips[c2.clip_id].timeline_range.start == pytest.approx(6.0)


def test_roll_requires_same_track(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    c1 = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    cmd.add_track(__import__('yroll.core.manifest',
                              fromlist=['TrackKind']).TrackKind.TEXT, "t1")
    c2 = cmd.add_clip("", 0.0, 5.0, timeline_start=0.0, track_id="t1")
    with pytest.raises(CommandError):
        cmd.roll_clip(c1.clip_id, c2.clip_id, delta_seconds=1.0)


def test_slide_shifts_clip_and_neighbor(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    left = cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)
    middle = cmd.add_clip("a1", 10.0, 15.0, timeline_start=10.0)
    cmd.add_clip("a1", 15.0, 20.0, timeline_start=15.0)

    op = cmd.slide_clip(middle.clip_id, left.clip_id, delta_seconds=2.0)

    assert op.type == "slide"
    # middle shifts +2
    assert core.project.clips[middle.clip_id].timeline_range.start == pytest.approx(12.0)
    assert core.project.clips[middle.clip_id].timeline_range.end == pytest.approx(17.0)
    # left shortens by 2
    assert core.project.clips[left.clip_id].timeline_range.end == pytest.approx(8.0)


def test_slip_undo_restores_source(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    c = cmd.add_clip("a1", 5.0, 15.0, timeline_start=0.0)
    orig_sr = c.source_range.model_dump()

    op = cmd.slip_clip(c.clip_id, delta_seconds=3.0)
    assert core.project.clips[c.clip_id].source_range.start == pytest.approx(8.0)

    core.revert(op.operation_id)
    assert core.project.clips[c.clip_id].source_range.start == pytest.approx(5.0)
    assert core.project.clips[c.clip_id].source_range.end == pytest.approx(15.0)
