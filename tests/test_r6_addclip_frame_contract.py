"""GUI-03R6-B: frame-native POST /clips contract.

The /clips endpoint now requires integer-frame fields:
  - timeline_start_frame
  - source_start_frame
  - source_end_frame

Legacy seconds fields (source_start / source_end / timeline_start)
are explicitly REJECTED with 400 to prevent silent frame↔seconds
confusion at the request boundary. This is the same pattern that
MoveReq uses for /clips/{id}/move.

Tests:
  - accept frame fields, clip lands at the right frame
  - reject each legacy field
  - reject negative frames
  - reject source_end_frame <= source_start_frame
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
    """Project with one VIDEO asset so source_fps is meaningful."""
    core = ProjectCore.create(tmp_path, "r6b_test")
    ProjectCore.ensure_default_tracks(core)
    from yroll.core.timebase import Rational
    a = Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x", size_bytes=1, duration_sec=10.0,
                               width=1920, height=1080),
    )
    a.source_fps = Rational(30, 1)
    a.source_is_cfr = True
    core.project.assets.append(a)
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
    return c.get("/ui/status").json()["base_revision"]


def _post_frame(c: TestClient, **overrides) -> "pytest.TestClient":
    body = {
        "asset_id": "a1",
        "timeline_start_frame": 150,
        "source_start_frame": 0,
        "source_end_frame": 300,
    }
    body.update(overrides)
    sid = _acquire(c)
    base = _base_rev(c)
    return c.post(
        "/clips",
        params={"sessionId": sid, "baseRevision": str(base)},
        json=body,
    )


def test_accept_frame_fields_lands_at_exact_frame(fresh_client: TestClient) -> None:
    """A drop at frame 150 with 300-frame duration creates a clip at
    TimelineFrame [150, 450]. The Core persists seconds but the GUI
    round-trip via /preview/plan is frame-native."""
    r = _post_frame(fresh_client,
                    timeline_start_frame=150,
                    source_start_frame=0,
                    source_end_frame=300)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "clip_id" in body
    # Stored as seconds in legacy model: 150/30 = 5.0; 450/30 = 15.0
    assert abs(body["timeline_range"]["start"] - 5.0) < 1e-9
    assert abs(body["timeline_range"]["end"] - 15.0) < 1e-9


def test_drop_at_frame_N_lands_at_frame_N_not_N_seconds(fresh_client: TestClient) -> None:
    """The critical regression test for the user-reported bug: a video
    drop at frame 1500 must produce a clip at TimelineFrame 1500, NOT
    at TimelineFrame 1500*30=45000 (which would be 1500 seconds)."""
    r = _post_frame(fresh_client, timeline_start_frame=1500)
    assert r.status_code == 200, r.text
    body = r.json()
    start_sec = body["timeline_range"]["start"]
    # Frame 1500 @ 30fps = 50.0 sec. NOT 1500 sec.
    assert abs(start_sec - 50.0) < 1e-9, (
        f"Expected start_sec=50.0 (1500 frames @ 30fps), got {start_sec}. "
        "The server is treating timeline_start_frame as seconds.")


def test_legacy_source_start_is_rejected(fresh_client: TestClient) -> None:
    """The user-reported regression: passing source_start (seconds)
    must produce 400 'no longer accepted', not silently convert."""
    sid = _acquire(fresh_client)
    base = _base_rev(fresh_client)
    r = fresh_client.post(
        "/clips",
        params={"sessionId": sid, "baseRevision": str(base)},
        json={
            "asset_id": "a1",
            "source_start": 0.0,           # legacy
            "source_end_frame": 300,
            "timeline_start_frame": 150,
        },
    )
    assert r.status_code == 400, r.text
    assert "source_start" in r.json()["detail"]
    assert "no longer accepted" in r.json()["detail"]


def test_legacy_source_end_is_rejected(fresh_client: TestClient) -> None:
    sid = _acquire(fresh_client)
    base = _base_rev(fresh_client)
    r = fresh_client.post(
        "/clips",
        params={"sessionId": sid, "baseRevision": str(base)},
        json={
            "asset_id": "a1",
            "source_start_frame": 0,
            "source_end": 5.0,             # legacy
            "timeline_start_frame": 150,
        },
    )
    assert r.status_code == 400, r.text


def test_legacy_timeline_start_is_rejected(fresh_client: TestClient) -> None:
    sid = _acquire(fresh_client)
    base = _base_rev(fresh_client)
    r = fresh_client.post(
        "/clips",
        params={"sessionId": sid, "baseRevision": str(base)},
        json={
            "asset_id": "a1",
            "source_start_frame": 0,
            "source_end_frame": 300,
            "timeline_start": 5.0,         # legacy
        },
    )
    assert r.status_code == 400, r.text


def test_negative_timeline_start_frame_is_rejected(fresh_client: TestClient) -> None:
    r = _post_frame(fresh_client, timeline_start_frame=-1)
    assert r.status_code == 400, r.text


def test_zero_duration_source_is_rejected(fresh_client: TestClient) -> None:
    r = _post_frame(fresh_client,
                    source_start_frame=300, source_end_frame=300)
    assert r.status_code == 400, r.text


def test_inverted_source_range_is_rejected(fresh_client: TestClient) -> None:
    r = _post_frame(fresh_client,
                    source_start_frame=300, source_end_frame=100)
    assert r.status_code == 400, r.text


def test_explicit_track_id_is_honored(fresh_client: TestClient) -> None:
    """Drop on the explicit V1 track (Core's auto-allocator would
    otherwise pick the same track; we verify the explicit path)."""
    r = _post_frame(fresh_client, track_id="v1")
    assert r.status_code == 200, r.text
    assert r.json()["track_id"] == "v1"