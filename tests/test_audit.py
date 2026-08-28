"""Agent Action Audit tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.audit import audit_batch, audit_since
from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore


@pytest.fixture()
def core(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "audit-test")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=30.0),
    ))
    return core


def test_empty_batch(core):
    a = audit_batch(core, [], previewed=True)
    assert a["operations"] == 0
    assert a["previewed"] is True


def test_single_move_audit(core):
    cmd = CommandLayer(core, who=Actor.AI)
    c = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    last_known = core.operations()[-1].operation_id
    op = cmd.move_clip(c.clip_id, new_timeline_start=2.0)
    a = audit_batch(core, [op])
    assert a["operations"] == 1
    assert "move" in a["by_kind"]
    assert a["affected_frame_range"] == [2.0, 7.0]  # tl start..end after move
    assert a["previewed"] is False


def test_audit_since_collects_all_new_ops(core):
    cmd = CommandLayer(core, who=Actor.AI)
    c1 = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    last_known = core.operations()[-1].operation_id
    cmd.move_clip(c1.clip_id, new_timeline_start=2.0)
    cmd.set_volume(c1.clip_id, 0.5)
    a = audit_since(core, since_operation_id=last_known, previewed=True)
    # 2 ops since add_clip
    assert a["operations"] == 2
    assert "move" in a["by_kind"]
    assert "volume" in a["by_kind"]
    assert a["previewed"] is True


def test_audit_summary_format(core):
    cmd = CommandLayer(core, who=Actor.AI)
    c = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    op = cmd.move_clip(c.clip_id, new_timeline_start=2.0)
    a = audit_batch(core, [op])
    # summary should mention the op kind
    assert "move" in a["summary"]


def test_audit_since_no_new_ops(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    c = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    last_known = core.operations()[-1].operation_id
    a = audit_since(core, since_operation_id=last_known)
    assert a["operations"] == 0
