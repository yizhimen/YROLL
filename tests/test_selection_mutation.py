"""P0-04B: Selection → Mutation integration tests.

move_selection / delete_selection are the front door for GUI/MCP/Agent.
They handle single/multi/cross-track/range Selection uniformly and emit
ONE atomic composite Operation regardless of how many clips are touched.
"""
from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.selection import Selection
from yroll.core.timebase import FrameRange, Rational


FPS_30 = Rational(30, 1)


@pytest.fixture()
def core(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "sel-mut-test")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=60.0),
    ))
    return core


def test_move_selection_single_clip(core):
    cmd = CommandLayer(core)
    c1 = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    c2 = cmd.add_clip("a1", 5.0, 10.0, timeline_start=5.0)
    pre_ops = len(core.operations())

    op = cmd.move_selection(Selection.single(c1.clip_id), delta_seconds=2.0)

    assert op.type == "move_selection"
    # ONE atomic composite op — no per-clip sub-ops
    assert len(core.operations()) == pre_ops + 1
    # c1 moved by +2s; c2 unchanged
    assert core.project.clips[c1.clip_id].timeline_range.start == pytest.approx(2.0)
    assert core.project.clips[c2.clip_id].timeline_range.start == pytest.approx(5.0)


def test_move_selection_multi_clip(core):
    """Multi-clip selection: both move by same delta in ONE op."""
    cmd = CommandLayer(core)
    c1 = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    c2 = cmd.add_clip("a1", 5.0, 10.0, timeline_start=5.0)
    c3 = cmd.add_clip("a1", 10.0, 15.0, timeline_start=10.0)
    pre_ops = len(core.operations())

    op = cmd.move_selection(Selection.many([c1.clip_id, c3.clip_id]),
                             delta_seconds=1.5)

    assert op.type == "move_selection"
    assert len(core.operations()) == pre_ops + 1
    assert core.project.clips[c1.clip_id].timeline_range.start == pytest.approx(1.5)
    assert core.project.clips[c2.clip_id].timeline_range.start == pytest.approx(5.0)
    assert core.project.clips[c3.clip_id].timeline_range.start == pytest.approx(11.5)


def test_move_selection_accepts_clip_id_str(core):
    """Convenience: Selection.from_clip_or_id('c1') works."""
    cmd = CommandLayer(core)
    c1 = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)

    # Pass a plain string instead of Selection object
    op = cmd.move_selection(c1.clip_id, delta_seconds=1.0)
    assert op.type == "move_selection"
    assert core.project.clips[c1.clip_id].timeline_range.start == pytest.approx(1.0)


def test_delete_selection_single_no_ripple(core):
    cmd = CommandLayer(core)
    c1 = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    c2 = cmd.add_clip("a1", 5.0, 10.0, timeline_start=5.0)
    pre_ops = len(core.operations())

    op = cmd.delete_selection(Selection.single(c1.clip_id))

    assert op.type == "delete_selection"
    assert len(core.operations()) == pre_ops + 1
    assert c1.clip_id not in core.project.clips
    # c2 unchanged (no ripple)
    assert core.project.clips[c2.clip_id].timeline_range.start == pytest.approx(5.0)


def test_delete_selection_with_ripple_shifts_followers(core):
    """Ripple delete: removes clip + collapses followers by deleted duration."""
    cmd = CommandLayer(core)
    c1 = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    c2 = cmd.add_clip("a1", 5.0, 10.0, timeline_start=5.0)
    c3 = cmd.add_clip("a1", 10.0, 15.0, timeline_start=10.0)

    cmd.delete_selection(Selection.single(c1.clip_id), ripple=True)

    assert c1.clip_id not in core.project.clips
    # c2 and c3 shifted left by 5s
    assert core.project.clips[c2.clip_id].timeline_range.start == pytest.approx(0.0)
    assert core.project.clips[c3.clip_id].timeline_range.start == pytest.approx(5.0)


def test_selection_mutation_atomic_undo(core):
    """Undo move_selection restores all clips in ONE step."""
    cmd = CommandLayer(core)
    c1 = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    c2 = cmd.add_clip("a1", 5.0, 10.0, timeline_start=5.0)
    c1_orig = c1.timeline_range.start
    c2_orig = c2.timeline_range.start

    op = cmd.move_selection(
        Selection.many([c1.clip_id, c2.clip_id]),
        delta_seconds=3.0,
    )

    assert c1.timeline_range.start == pytest.approx(c1_orig + 3.0)
    assert c2.timeline_range.start == pytest.approx(c2_orig + 3.0)

    # Atomic undo: ONE revert restores everything
    core.revert(op.operation_id)
    assert c1.timeline_range.start == pytest.approx(c1_orig)
    assert c2.timeline_range.start == pytest.approx(c2_orig)


def test_empty_selection_raises(core):
    cmd = CommandLayer(core)
    with pytest.raises(Exception):  # CommandError
        cmd.move_selection(Selection(), delta_seconds=1.0)
    with pytest.raises(Exception):
        cmd.delete_selection(Selection())
