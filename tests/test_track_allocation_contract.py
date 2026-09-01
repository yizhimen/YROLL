"""GUI-03R-Micro v2: regression tests for the request contract of
/clips and /clips/add_image.

Background
----------
The runtime proof was:

  POST /clips/add_image → 422
  {"detail":[{"loc":["body","track_id"],"msg":"Input should be a valid string","input":null}]}

Root cause: AddClipReq.track_id and AddImageClipReq.track_id were
typed `str = ""`. When the GUI (correctly per 03R-Micro v1) sent
`track_id: null` to invoke Core's automatic TrackAllocator, Pydantic
rejected the body as 422 ("Input should be a valid string").

Fix: both fields are now `str | None = None`.

This file pins the contract — the schema accepts `null`, the handler
passes the value through to Core without sentinel translation, an
explicit string target still works, and Core's normal overlap
rejection (400) is preserved.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational
from yroll.server.app import create_app


# ---------- helpers ----------

@pytest.fixture()
def authed_client(tmp_path: Path):
    """Plain TestClient + a small wrapper that auto-attaches
    sessionId + the LIVE baseRevision read from /operations right
    before every mutation. Pre-populates the project with one VIDEO
    asset (a1) and one IMAGE asset (a-img) plus the default v1
    track.
    """
    core = ProjectCore.create(tmp_path, "alloc-test")
    ProjectCore.ensure_default_tracks(core)
    a_v = Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v1.mp4",
        identity=AssetIdentity(md5="v" * 32, size_bytes=1, duration_sec=10.0),
    )
    a_v.source_fps = Rational(30, 1)
    a_v.source_is_cfr = True
    core.project.assets.append(a_v)
    a_img = Asset(
        asset_id="a-img", type=AssetType.IMAGE, path="img.png",
        identity=AssetIdentity(md5="i" * 32, size_bytes=1, duration_sec=None),
    )
    core.project.assets.append(a_img)
    # Save state to disk so create_app's ProjectCore.open picks up
    # our appended assets when it re-reads current.json.
    core.save_state()
    app = create_app(core.path, who=Actor.AI)
    raw = TestClient(app)
    r = raw.post("/lease/acquire?actor=agent&mode=edit&actorId=alloc-test")
    sid = r.json()["sessionId"]

    class _Call:
        def get(self, url):
            return raw.get(url)
        def post(self, url, json=None):
            rev = len(raw.get("/operations").json())
            return raw.post(url, params={
                "sessionId": sid, "baseRevision": str(rev),
            }, json=json or {})

    return _Call()


# ---------- 1. /clips/add_image accepts track_id=null ----------

def test_add_image_accepts_track_id_null(authed_client):
    """The GUI sends track_id=null to invoke Core's automatic
    TrackAllocator. The server MUST accept it (no 422) and Core
    must allocate a non-overlapping track."""
    r = authed_client.post("/clips/add_image", json={
        "asset_id": "a-img",
        "timeline_start_frame": 0,
        "timeline_duration_frames": 30,
        "track_id": None,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("track_id"), f"allocator returned no track: {body}"
    clip_id = body["clip_id"]
    assert clip_id.startswith("c")
    proj_tracks = authed_client.get("/project").json()
    chosen = next(
        (t for t in proj_tracks["timelines"][0]["tracks"]
         if clip_id in t["clip_ids"]),
        None,
    )
    assert chosen is not None, "no track owns the new image clip"


# ---------- 2. /clips accepts track_id=null ----------

def test_add_clip_accepts_track_id_null(authed_client):
    """Video path: same automatic-placement contract."""
    r = authed_client.post("/clips", json={
        "asset_id": "a1",
        "source_start_frame": 0,
        "source_end_frame": 150,
        "timeline_start_frame": 0,
        "track_id": None,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("track_id")
    proj_tracks = authed_client.get("/project").json()
    chosen = next(
        (t for t in proj_tracks["timelines"][0]["tracks"]
         if body["clip_id"] in t["clip_ids"]),
        None,
    )
    assert chosen is not None


# ---------- 3. track_id="v2" still works (explicit string) ----------

def test_explicit_string_track_id_still_works(authed_client):
    """The explicit-target path must remain honored."""
    r = authed_client.post("/clips/add_image", json={
        "asset_id": "a-img",
        "timeline_start_frame": 0,
        "timeline_duration_frames": 30,
        "track_id": "v2",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("track_id") == "v2"


# ---------- 4. null automatic placement actually invokes Core allocator ----------

def test_null_allocator_picks_non_overlapping_track(authed_client):
    """Fill v1 explicitly; then add another video clip with
    track_id=null. The allocator must NOT pick v1 (overlap)."""
    r1 = authed_client.post("/clips", json={
        "asset_id": "a1",
        "source_start_frame": 0, "source_end_frame": 150,
        "timeline_start_frame": 0,
        "track_id": "v1",
    })
    assert r1.status_code == 200
    r2 = authed_client.post("/clips", json={
        "asset_id": "a1",
        "source_start_frame": 0, "source_end_frame": 150,
        "timeline_start_frame": 0,
        "track_id": None,
    })
    assert r2.status_code == 200, r2.text
    chosen = r2.json()["track_id"]
    assert chosen != "v1", (
        f"allocator collided on v1 (occupied): {r2.text}")


# ---------- 5. explicit-target overlap still returns Core's normal 400 ----------

def test_explicit_overlap_returns_400(authed_client):
    """Same-track overlap on an explicit track_id MUST be rejected
    with Core's 400."""
    r1 = authed_client.post("/clips", json={
        "asset_id": "a1",
        "source_start_frame": 0, "source_end_frame": 150,
        "timeline_start_frame": 0,
        "track_id": "v1",
    })
    assert r1.status_code == 200
    r2 = authed_client.post("/clips", json={
        "asset_id": "a1",
        "source_start_frame": 0, "source_end_frame": 90,
        "timeline_start_frame": 60,
        "track_id": "v1",
    })
    assert r2.status_code == 400, (
        f"expected 400 for overlap, got {r2.status_code}: {r2.text}")
    assert "重叠" in r2.text or "overlap" in r2.text.lower()