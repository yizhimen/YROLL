"""P0-08 History API tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.history import HistoryAPI
from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore


@pytest.fixture()
def core(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "history-test")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=10.0),
    ))
    return core


def test_history_state_initial(core):
    h = HistoryAPI(core)
    s = h.state()
    assert s.can_undo is False
    assert s.can_redo is False
    assert s.last_operation_id is None


def test_undo_restores_state(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    last_op = core.operations()[-1]
    h = HistoryAPI(core)

    s = h.state()
    assert s.can_undo is True
    assert s.last_operation_id == last_op.operation_id

    # Mutate, then undo
    c = next(iter(core.project.clips.values()))
    cmd.set_volume(c.clip_id, 0.5)
    h.undo()
    assert core.project.clips[c.clip_id].volume == pytest.approx(1.0)


def test_redo_re_applies_state(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    c = next(iter(core.project.clips.values()))
    cmd.set_volume(c.clip_id, 0.5)
    h = HistoryAPI(core)
    h.undo()
    assert core.project.clips[c.clip_id].volume == pytest.approx(1.0)

    h.redo()
    assert core.project.clips[c.clip_id].volume == pytest.approx(0.5)


def test_history_returns_full_log(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    h = HistoryAPI(core)
    log = h.history()
    assert len(log) == 1
    assert log[0]["type"] == "add_clip"


def test_history_state_after_undo(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    h = HistoryAPI(core)
    h.undo()
    s = h.state()
    # Last op is now a revert:* marker, so can_redo should be True
    assert s.can_redo is True
