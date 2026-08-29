"""Agent Contract (v0.2 §29) tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.selection import Selection
from yroll.agent_contract import YrollAgent


@pytest.fixture()
def core(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "agent-contract-test")
    ProjectCore.ensure_default_tracks(core)
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=30.0),
    ))
    return core


def test_get_project_state(core):
    agent = YrollAgent(core)
    state = agent.get_project_state()
    assert state["name"] == "agent-contract-test"
    assert "timeline" in state


def test_get_timeline(core):
    agent = YrollAgent(core)
    tl = agent.get_timeline()
    assert "tracks" in tl


def test_preview_move_does_not_mutate(core):
    from yroll.core.commands import CommandLayer
    from yroll.core.manifest import Actor
    cmd = CommandLayer(core, who=Actor.HUMAN)
    c = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)

    agent = YrollAgent(core)
    pv = agent.preview_mutation(
        Selection.single(c.clip_id), "move", {"delta_seconds": 2.0})
    assert pv["summary"]["n_primary"] == 1
    assert core.project.clips[c.clip_id].timeline_range.start == pytest.approx(0.0)


def test_commit_mutation_without_session_succeeds_in_legacy_mode(core):
    """No session_id: legacy mode (no gate, just commit). Useful for
    trusted internal scripts. The HTTP server enforces the gate; the
    Python API is intentionally permissive for non-HTTP callers.
    """
    from yroll.core.commands import CommandLayer
    from yroll.core.manifest import Actor
    cmd = CommandLayer(core, who=Actor.HUMAN)
    c = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)

    agent = YrollAgent(core)  # session_id=None
    res = agent.commit_mutation(Selection.single(c.clip_id), "move",
                                 {"delta_seconds": 1.0})
    assert res["type"] == "move_selection"


def test_commit_mutation_with_invalid_session_raises(core):
    """Setting a session_id without acquiring a lease → gate fails."""
    from yroll.core.commands import CommandLayer
    from yroll.core.manifest import Actor
    cmd = CommandLayer(core, who=Actor.HUMAN)
    c = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)

    agent = YrollAgent(core, session_id="bogus")
    with pytest.raises(Exception):
        agent.commit_mutation(Selection.single(c.clip_id), "move",
                              {"delta_seconds": 1.0})


def test_full_lease_to_commit_flow(core):
    from yroll.core.commands import CommandLayer
    from yroll.core.manifest import Actor
    cmd = CommandLayer(core, who=Actor.HUMAN)
    c = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)

    agent = YrollAgent(core)
    sid = agent.request_edit_lease(actor="human", human_label="User")
    assert sid
    lease = agent.get_lease_state()
    assert lease["alive"]
    assert lease["held_by"] == "human"

    res = agent.commit_mutation(Selection.single(c.clip_id), "move",
                                 {"delta_seconds": 2.0})
    assert res["type"] == "move_selection"
    assert core.project.clips[c.clip_id].timeline_range.start == pytest.approx(2.0)
    # base_revision auto-bumped to current (1 add_clip + 1 move_selection = 2)
    assert agent.base_revision == 2


def test_handoff_to_agent(core):
    from yroll.core.commands import CommandLayer
    from yroll.core.manifest import Actor
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)

    agent = YrollAgent(core)
    human_sid = agent.request_edit_lease(actor="human", human_label="User")
    agent_sid = agent.handoff(to_actor="agent", to_label="Claude")
    assert agent_sid != human_sid
    # Now agent holds the lease
    lease = agent.get_lease_state()
    assert lease["held_by"] == "agent"


def test_release_lease_clears_session(core):
    agent = YrollAgent(core)
    agent.request_edit_lease(actor="human")
    assert agent.session_id is not None
    agent.release_edit_lease()
    assert agent.session_id is None


def test_undo_redo_via_agent(core):
    from yroll.core.commands import CommandLayer
    from yroll.core.manifest import Actor
    cmd = CommandLayer(core, who=Actor.HUMAN)
    c = cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)

    agent = YrollAgent(core)
    agent.request_edit_lease(actor="human")
    # Use the agent's commit_mutation (with proper dispatch)
    sel = Selection.single(c.clip_id)
    agent.commit_mutation(sel, op="move", params={"delta_seconds": 1.0},
                           why="")
    # Now bump volume via cmd (bypassing agent to avoid lease drift)
    cmd.set_volume(c.clip_id, 0.5)
    # Sync agent's base_revision so undo gate passes
    agent.base_revision = 3  # add_clip + move_selection + set_volume
    assert core.project.clips[c.clip_id].volume == pytest.approx(0.5)

    agent.undo()
    assert core.project.clips[c.clip_id].volume == pytest.approx(1.0)

    agent.redo()
    assert core.project.clips[c.clip_id].volume == pytest.approx(0.5)
