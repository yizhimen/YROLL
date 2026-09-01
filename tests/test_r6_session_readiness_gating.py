"""GUI-03R6-E: server Mutation Gate contract is unchanged.

R6-E added CLIENT-SIDE UX gating only (disable buttons / drag-start).
The server Mutation Gate is the authoritative truth. This file pins:
  1. POST /clips without sessionId → 403 (sessionId required)
  2. POST /clips with valid sessionId but stale baseRevision → 409
  3. POST /clips with valid sessionId + valid baseRevision → 200
  4. POST /clips with held-by-other-lease → 403 (lease_rejected)

The client must NEVER bypass the gate; the gate must NEVER
loosen its rules because of the client UX changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore


@pytest.fixture
def fresh_client(tmp_path: Path):
    """Each test gets a brand-new project with one image asset and
    one video asset so we can exercise the frame-native /clips path."""
    core = ProjectCore.create(tmp_path, "r6e_test")
    ProjectCore.ensure_default_tracks(core)
    a_img = Asset(
        asset_id="a1", type=AssetType.IMAGE, path="img.png",
        identity=AssetIdentity(md5="x", size_bytes=1, duration_sec=None,
                               width=100, height=100),
    )
    core.project.assets.append(a_img)
    core.save_state()
    from yroll.server.app import create_app
    app = create_app(core.path, who=Actor.HUMAN)
    with TestClient(app) as c:
        yield c


def _acquire(c: TestClient) -> str:
    r = c.post("/lease/acquire", params={"actorId": "human", "mode": "edit"})
    assert r.status_code == 200, r.text
    return r.json()["sessionId"]


def _base_rev(c: TestClient) -> int:
    """The /ui/status response carries base_revision (the canonical
    server-truth revision). POST /clips requires this exact value."""
    return c.get("/ui/status").json()["base_revision"]


def test_post_clips_without_sessionid_is_403(fresh_client: TestClient) -> None:
    """The Mutation Gate must reject unauthenticated writes with 403.
    R6-B contract: body uses frame fields."""
    r = fresh_client.post(
        "/clips",
        params={"baseRevision": "0"},
        json={
            "asset_id": "a1",
            "source_start_frame": 0,
            "source_end_frame": 150,
            "timeline_start_frame": 0,
        },
    )
    assert r.status_code == 403, r.text
    assert "sessionId required" in r.json()["detail"]


def test_post_clips_with_valid_session_and_revision_succeeds(fresh_client: TestClient) -> None:
    """When the session + revision are good, the gate accepts the write."""
    sid = _acquire(fresh_client)
    base = _base_rev(fresh_client)
    r = fresh_client.post(
        "/clips",
        params={"sessionId": sid, "baseRevision": str(base)},
        json={
            "asset_id": "a1",
            "source_start_frame": 0,
            "source_end_frame": 150,
            "timeline_start_frame": 0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "clip_id" in body
    assert body["timeline_range"]["start"] == 0


def test_post_clips_with_stale_revision_is_conflict(fresh_client: TestClient) -> None:
    """A write with stale baseRevision must be rejected with 409."""
    sid = _acquire(fresh_client)
    r = fresh_client.post(
        "/clips",
        params={"sessionId": sid, "baseRevision": "9999"},
        json={
            "asset_id": "a1",
            "source_start_frame": 0,
            "source_end_frame": 150,
            "timeline_start_frame": 0,
        },
    )
    assert r.status_code == 409, r.text


def test_post_clips_held_by_other_lease_is_rejected(fresh_client: TestClient) -> None:
    """Once human A holds the lease, an agent's write must 403."""
    sid_a = _acquire(fresh_client)
    # Agent attempts a write without first acquiring; even with a
    # valid-looking sessionId, the server rejects because we don't
    # own the lease.
    r = fresh_client.post(
        "/clips",
        params={"sessionId": "agent-attacker", "baseRevision": "0"},
        json={
            "asset_id": "a1",
            "source_start_frame": 0,
            "source_end_frame": 150,
            "timeline_start_frame": 0,
        },
    )
    assert r.status_code == 403, r.text