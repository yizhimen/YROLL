"""Lease Status / Conflict UI tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.lease import (
    Actor as LeaseActor, LeaseMode, get_lease_store,
)
from yroll.core.lease_status import lease_status
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore


@pytest.fixture()
def core(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "lease-status-test")
    ProjectCore.ensure_default_tracks(core)
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=10.0),
    ))
    return core


def test_initial_status_is_free(core):
    s = lease_status(core)
    assert s["actor"] == "free"
    assert s["alive"] is False
    assert s["conflict"] is False
    assert s["visual_cue"]["color"] == "white"


def test_human_holding_edit(core):
    get_lease_store(core).acquire(
        core.project.project_id,
        LeaseActor.HUMAN, LeaseMode.EDIT, 0, "Alice")
    s = lease_status(core)
    assert s["actor"] == "human"
    assert s["human_label"] == "Alice"
    assert s["alive"] is True
    assert s["visual_cue"]["color"] == "green"
    assert "我" in s["visual_cue"]["text"]


def test_agent_holding_edit(core):
    get_lease_store(core).acquire(
        core.project.project_id,
        LeaseActor.AGENT, LeaseMode.EDIT, 0, "Claude")
    s = lease_status(core)
    assert s["actor"] == "agent"
    assert s["agent_label"] == "Claude"
    assert s["visual_cue"]["color"] == "yellow"
    assert "Claude" in s["visual_cue"]["text"]


def test_observe_mode(core):
    get_lease_store(core).acquire(
        core.project.project_id,
        LeaseActor.HUMAN, LeaseMode.OBSERVE, 0, "Watcher")
    s = lease_status(core)
    assert s["actor"] == "observe"
    assert s["visual_cue"]["color"] == "gray"


def test_conflict_when_client_revision_stale(core):
    """GUI knew rev=0; server is now rev=3 → CONFLICT."""
    from yroll.core.commands import CommandLayer
    from yroll.core.manifest import Actor
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)  # rev=1
    cmd.set_volume(list(core.project.clips.values())[0].clip_id, 0.5)  # rev=2
    s = lease_status(core, client_known_revision=0)
    assert s["actor"] == "conflict"
    assert s["conflict"] is True
    assert s["visual_cue"]["color"] == "red"
    assert s["base_revision"] == 2


def test_no_conflict_when_client_in_sync(core):
    from yroll.core.commands import CommandLayer
    from yroll.core.manifest import Actor
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    s = lease_status(core, client_known_revision=1)
    assert s["conflict"] is False
    assert s["actor"] != "conflict"
