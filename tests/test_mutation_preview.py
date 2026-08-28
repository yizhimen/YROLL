"""P0-07: Mutation Preview / Impact — describe what an operation WOULD do."""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.links import infer_relationships, preview_mutation
from yroll.core.manifest import Actor, TrackKind
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.selection import Selection


@pytest.fixture()
def core(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "preview-test")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=60.0),
    ))
    return core


def test_preview_move_describes_to_state(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    c = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)

    pv = preview_mutation(core.project, Selection.single(c.clip_id),
                          op="move", params={"delta_seconds": 2.5})
    assert pv["summary"]["n_primary"] == 1
    p = pv["primary"][0]
    assert p["clip_id"] == c.clip_id
    # "from" is current state, "to" predicts after move
    assert p["from"]["timeline_range"]["start"] == pytest.approx(0.0)
    assert p["to"]["timeline_range"]["start"] == pytest.approx(2.5)
    # State was NOT mutated
    assert core.project.clips[c.clip_id].timeline_range.start == pytest.approx(0.0)


def test_preview_delete_lists_secondary_propagation(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    v = cmd.add_clip("a1", 0.0, 30.0, timeline_start=0.0)
    cmd.add_track(TrackKind.TEXT, "t1")
    sub = cmd.add_clip("", 0.0, 30.0, timeline_start=0.0, track_id="t1")
    sub.context["text"] = "与 v 关联的字幕"
    core.save_state()
    infer_relationships(core.project)

    pv = preview_mutation(core.project, Selection.single(v.clip_id),
                          op="ripple_delete")
    # Primary: the video clip
    assert pv["summary"]["n_primary"] == 1
    # Secondary: the subtitle should appear as strong_link_propagate
    assert pv["summary"]["n_secondary"] >= 1
    assert any(s["clip_id"] == sub.clip_id for s in pv["secondary"])


def test_preview_multi_clip(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    c1 = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    c2 = cmd.add_clip("a1", 5.0, 10.0, timeline_start=5.0)

    pv = preview_mutation(core.project, Selection.many([c1.clip_id, c2.clip_id]),
                          op="move", params={"delta_seconds": -1.0})
    assert pv["summary"]["n_primary"] == 2


def test_preview_track_only_selection(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    cmd.add_clip("a1", 5.0, 10.0, timeline_start=5.0)

    pv = preview_mutation(core.project,
                          Selection(track_ids=["v1"]),
                          op="delete")
    assert pv["summary"]["n_primary"] == 2


def test_preview_does_not_mutate(core):
    cmd = CommandLayer(core, who=Actor.HUMAN)
    c = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    ops_before = len(core.operations())
    preview_mutation(core.project, Selection.single(c.clip_id),
                     op="delete")
    # No new operations
    assert len(core.operations()) == ops_before
    assert c.clip_id in core.project.clips
