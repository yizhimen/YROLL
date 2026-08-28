"""Mutation Proposal (v0.2 §3 P3 + §29 Agent Plan) tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.proposals import ProposalStore, get_proposal_store
from yroll.core.project import ProjectCore
from yroll.core.selection import Selection


@pytest.fixture()
def core(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "proposals-test")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=60.0),
    ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)
    cmd.add_clip("a1", 10.0, 20.0, timeline_start=10.0)
    return core


def test_propose_returns_preview(core):
    store = ProposalStore()
    p = store.propose(core.project, Selection(clip_ids=[next(iter(core.project.clips))]),
                      op="move", params={"delta_seconds": 2.0},
                      reason="test")
    assert p.proposal_id
    assert p.preview["summary"]["n_primary"] == 1
    # State was NOT mutated
    clip_id = next(iter(core.project.clips))
    assert core.project.clips[clip_id].timeline_range.start == pytest.approx(0.0)


def test_approve_then_consume(core):
    store = ProposalStore()
    p = store.propose(core.project, Selection(clip_ids=[next(iter(core.project.clips))]),
                      op="move", params={"delta_seconds": 2.0})
    assert store.approve(p.proposal_id, approved_by="human") is True
    consumed = store.consume(p.proposal_id)
    assert consumed is not None
    assert consumed.approved_by == "human"


def test_reject_blocks_approval(core):
    store = ProposalStore()
    p = store.propose(core.project, Selection(clip_ids=[next(iter(core.project.clips))]),
                      op="move", params={"delta_seconds": 2.0})
    assert store.reject(p.proposal_id) is True
    assert store.approve(p.proposal_id) is False


def test_approve_then_reject_blocked(core):
    store = ProposalStore()
    p = store.propose(core.project, Selection(clip_ids=[next(iter(core.project.clips))]),
                      op="move", params={"delta_seconds": 2.0})
    store.approve(p.proposal_id)
    assert store.reject(p.proposal_id) is False


def test_expired_proposal_removed(core):
    store = ProposalStore(ttl_seconds=0)  # immediate expiry
    p = store.propose(core.project, Selection(clip_ids=[next(iter(core.project.clips))]),
                      op="move", params={"delta_seconds": 2.0})
    # Manually expire: try approve; should fail
    assert store.approve(p.proposal_id) is False


def test_list_pending(core):
    store = ProposalStore()
    sel = Selection(clip_ids=[next(iter(core.project.clips))])
    store.propose(core.project, sel, op="move", params={"delta_seconds": 1.0})
    store.propose(core.project, sel, op="delete", params={})
    pending = store.list_pending()
    assert len(pending) == 2


def test_get_proposal_store_singleton(core):
    s1 = get_proposal_store(core)
    s2 = get_proposal_store(core)
    assert s1 is s2
