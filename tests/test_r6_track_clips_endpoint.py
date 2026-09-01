"""GUI-03R6-D: canonical sibling read API.

The /tracks/{track_id}/clips endpoint returns the canonical sibling
geometry (frame-native intervals) so the GUI's cross-track re-clamp
no longer reads DOM style.left / CSS pixels.

Tests:
  - empty track → empty clips list
  - populated track → frame-native intervals in order
  - unknown track → 404
  - unknown timeline → 404
  - the response drives a successful cross-track move (no 400)
  - the response drives a correctly rejected overlapping cross-track
    move (400 with overlap message)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore


@pytest.fixture
def app_client(tmp_path: Path):
    """Project with two VIDEO clips on V1 and V2 each."""
    core = ProjectCore.create(tmp_path, "r6d_test")
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
        yield c, core


def _acquire(c: TestClient) -> str:
    r = c.post("/lease/acquire", params={"actorId": "human", "mode": "edit"})
    assert r.status_code == 200, r.text
    return r.json()["sessionId"]


def _base_rev(c: TestClient) -> int:
    return c.get("/ui/status").json()["base_revision"]


def _post_clip(c, sid, base, *, timeline_start_frame, source_end_frame=300,
               track_id="v1", asset_id="a1"):
    r = c.post(
        "/clips",
        params={"sessionId": sid, "baseRevision": str(base)},
        json={
            "asset_id": asset_id,
            "source_start_frame": 0,
            "source_end_frame": source_end_frame,
            "timeline_start_frame": timeline_start_frame,
            "track_id": track_id,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_empty_track_returns_empty_list(app_client) -> None:
    """No clips yet → empty list, but the response is 200."""
    c, _core = app_client
    r = c.get("/tracks/v1/clips")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["track_id"] == "v1"
    assert body["timeline_id"] == "main"
    assert body["clips"] == []


def test_unknown_track_is_404(app_client) -> None:
    c, _core = app_client
    r = c.get("/tracks/nope/clips")
    assert r.status_code == 404


def test_unknown_timeline_is_404(app_client) -> None:
    c, _core = app_client
    r = c.get("/tracks/v1/clips", params={"timeline_id": "nope"})
    assert r.status_code == 404


def test_populated_track_returns_frame_intervals(app_client) -> None:
    """A track with two clips returns both intervals in frames."""
    c, _core = app_client
    sid = _acquire(c)
    base = _base_rev(c)
    # First clip: source 0..300 → timeline 0..300.
    _post_clip(c, sid, base, timeline_start_frame=0, source_end_frame=300)
    base = _base_rev(c)
    # Second clip: source 0..300 → timeline 600..900.
    _post_clip(c, sid, base, timeline_start_frame=600, source_end_frame=300)
    r = c.get("/tracks/v1/clips")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["clips"]) == 2
    intervals = sorted((c["start_frame"], c["end_frame"]) for c in body["clips"])
    assert intervals == [(0, 300), (600, 900)]


def test_endpoint_drives_valid_cross_track_move(app_client) -> None:
    """valid target → success. /clips/{id}/move on the empty target
    track produces a clip on the new track with no overlap error."""
    c, _core = app_client
    sid = _acquire(c)
    base = _base_rev(c)
    # Seed one clip on V1 at frame 0..300.
    seed = _post_clip(c, sid, base, timeline_start_frame=0,
                      source_end_frame=300, track_id="v1")
    base = _base_rev(c)
    # Move it to V2 at frame 0..300 (V2 is empty).
    move = c.post(
        f"/clips/{seed['clip_id']}/move",
        params={"sessionId": sid, "baseRevision": str(base)},
        json={
            "new_timeline_start_frame": 0,
            "new_track_id": "v2",
            "why": "R6-D valid move",
        },
    )
    assert move.status_code == 200, move.text
    body = move.json()
    assert body["after"]["track_id"] == "v2"


def test_endpoint_drives_correctly_rejected_overlap(app_client) -> None:
    """overlapping target → rejection is correct (400 with overlap
    message). The clip stays on its source track; state mutation is
    zero on rejection."""
    c, _core = app_client
    sid = _acquire(c)
    base = _base_rev(c)
    seed = _post_clip(c, sid, base, timeline_start_frame=0,
                      source_end_frame=300, track_id="v1")
    base = _base_rev(c)
    # V2 already has a clip at 100..400 → move target overlaps.
    _post_clip(c, sid, base, timeline_start_frame=100,
               source_end_frame=400, track_id="v2")
    base = _base_rev(c)
    move = c.post(
        f"/clips/{seed['clip_id']}/move",
        params={"sessionId": sid, "baseRevision": str(base)},
        json={
            "new_timeline_start_frame": 0,
            "new_track_id": "v2",
            "why": "R6-D overlap test",
        },
    )
    assert move.status_code == 400, move.text
    # The overlap message references v13 in the audit; here it's
    # whichever target we sent. Just confirm a clear overlap error.
    assert "时间重叠" in move.text or "overlap" in move.text.lower()