"""Audit §6.5: Chat Agent is a second unprotected mutation path.

Without gate, Human holds Edit Lease → Agent Chat task.apply_actions()
or task.run() can still modify the project via CommandLayer.

Fix: Task now accepts session_id + expected_base_revision. Server chat
endpoints forward them. Without valid gate, the Task refuses to apply
any action and emits gate_rejected event.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.lease import (
    Actor as LeaseActor, LeaseMode, get_lease_store,
)
from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore


@pytest.fixture()
def core_with_clip(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "chat-gate-test")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=10.0),
    ))
    # Pre-populate one clip so we can mutate its volume.
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    return core


def _volume_action(clip_id: str, vol: float = 0.7) -> dict:
    return {"op": "volume", "clip_id": clip_id,
            "volume": vol, "why": "test"}


def test_chat_task_legacy_no_session_id_allows(core_with_clip):
    """No session_id: legacy behavior preserved (back-compat for non-HTTP callers)."""
    from yroll.harness.runtime import Task
    core = core_with_clip
    clip_id = next(iter(core.project.clips))
    cmd = CommandLayer(core, who=Actor.AI)
    task = Task(cmd, system="x", session_id=None)
    task.apply_actions([_volume_action(clip_id)])
    assert core.project.clips[clip_id].volume == pytest.approx(0.7)


def test_chat_task_rejects_when_lease_held_by_other_actor(core_with_clip):
    """Human holds the lease. AI Chat with a different session_id → rejected."""
    from yroll.harness.runtime import Task
    core = core_with_clip
    clip_id = next(iter(core.project.clips))
    get_lease_store(core).acquire(
        core.project.project_id, LeaseActor.HUMAN, LeaseMode.EDIT, 0, "User")

    cmd = CommandLayer(core, who=Actor.AI)
    task = Task(cmd, system="x",
                session_id="ai_fake_session_id",
                expected_base_revision=0)
    task.apply_actions([_volume_action(clip_id)])
    # AI's fake session_id is not the human's; lease rejected → volume unchanged
    assert core.project.clips[clip_id].volume == pytest.approx(1.0)


def test_chat_task_rejects_on_stale_revision(core_with_clip):
    """AI holds lease but baseRevision is stale → rejected."""
    from yroll.harness.runtime import Task
    core = core_with_clip
    clip_id = next(iter(core.project.clips))
    # Bump server revision via another mutation
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.set_volume(clip_id, 0.3)
    cur_rev = len(core.operations())  # = 2 (add_clip + volume)

    ls = get_lease_store(core).acquire(
        core.project.project_id, LeaseActor.AGENT, LeaseMode.EDIT, 0, "Claude")
    ai_sid = ls.session_id

    cmd2 = CommandLayer(core, who=Actor.AI)
    # AI tries with baseRevision=0 (stale; current is cur_rev)
    task = Task(cmd2, system="x",
                session_id=ai_sid,
                expected_base_revision=0)
    task.apply_actions([_volume_action(clip_id, vol=0.9)])
    # AI's stale-rev action rejected; volume still at 0.3 from prior set
    assert core.project.clips[clip_id].volume == pytest.approx(0.3)


def test_chat_task_accepts_valid_lease_and_revision(core_with_clip):
    """AI holds lease + correct revision → action applies."""
    from yroll.harness.runtime import Task
    core = core_with_clip
    clip_id = next(iter(core.project.clips))
    cur_rev = len(core.operations())  # = 1 (just add_clip)

    ls = get_lease_store(core).acquire(
        core.project.project_id, LeaseActor.AGENT, LeaseMode.EDIT,
        cur_rev, "Claude")
    ai_sid = ls.session_id

    cmd = CommandLayer(core, who=Actor.AI)
    task = Task(cmd, system="x",
                session_id=ai_sid,
                expected_base_revision=cur_rev)
    task.apply_actions([_volume_action(clip_id, vol=0.5)])
    assert core.project.clips[clip_id].volume == pytest.approx(0.5)


def test_chat_endpoint_accepts_sessionid_in_payload():
    """HTTP /chat payload model accepts sessionId + baseRevision."""
    from yroll.server.app import ChatReq
    req = ChatReq(message="hi", sessionId="abc", baseRevision=5)
    assert req.sessionId == "abc"
    assert req.baseRevision == 5
