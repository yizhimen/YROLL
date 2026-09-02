# GUI-03R4.1 P1-7: Multi-layer visual proof.
#
# Pins the 3-layer coexistence invariant from the spec:
#   "V1 + V2 + V3 can coexist and render simultaneously with
#    V2/V3 over V1."
#   "Hidden upper layer must immediately reveal lower layer."
#
# The fixture builds a deterministic project with three visual tracks
# (V1 + V2 + V3) where each track carries a clip in the SAME frame
# range [10, 20] so the preview must composite them all at once.
# The pytest then exercises /preview/plan and /preview/at_frame to
# prove:
#
#   1. All three layers appear at frame 15 (V1 + V2 + V3 coexist).
#   2. V2/V3 sit ABOVE V1 in the composite (higher layer_index).
#   3. Hidden V2 → /preview/at_frame shows only V1 + V3.
#   4. Hidden V3 → /preview/at_frame shows only V1 + V2.
#   5. Hidden both → only V1.
#   6. Each visual layer has a UNIQUE layer_index (the R4-1 invariant).

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yroll.core.manifest import (
    Actor,
)
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational
from yroll.server.app import create_app


@pytest.fixture()
def ml_client(tmp_path: Path):
    """Project with V1 + V2 + V3 visual tracks; each carries ONE
    clip at [10s, 20s]. The clips all OVERLAP in the frame range so
    the preview must composite them simultaneously."""
    core = ProjectCore.create(tmp_path, "p1-7-multilayer")
    # Three video assets (one per track — distinct identities).
    for i in range(1, 4):
        a = Asset(
            asset_id=f"a{i}", type=AssetType.VIDEO, path=f"v{i}.mp4",
            identity=AssetIdentity(
                md5=str(i).encode().hex().ljust(32, "0")[:32],
                size_bytes=1024 * i, duration_sec=30.0,
            ),
        )
        a.source_fps = Rational(30, 1)
        a.source_is_cfr = True
        core.project.assets.append(a)
    core.save_state()
    app = create_app(core.path, who=Actor.AI)
    raw = TestClient(app)
    r = raw.post("/lease/acquire?actor=agent&mode=edit&actorId=p1-7")
    sid = r.json()["sessionId"]

    class _Call:
        def get(self, url):
            return raw.get(url)
        def post(self, url, params=None, json=None):
            extra = params or {}
            extra.setdefault("sessionId", sid)
            extra.setdefault("baseRevision",
                             str(len(raw.get("/operations").json())))
            return raw.post(url, params=extra, json=json or {})

    c = _Call()
    # Create three visual tracks V1/V2/V3 via HTTP — goes through
    # the Mutation Gate so each creation is auditable.
    for vid in ("v1", "v2", "v3"):
        r = c.post("/tracks", params={
            "kind": "video", "track_id": vid, "timeline_id": "main",
        })
        assert r.status_code == 200, r.text
    # Seed one clip per track at [10s, 20s] using /clips.
    for aid, tid in [("a1", "v1"), ("a2", "v2"), ("a3", "v3")]:
        r = c.post("/clips", json={
            "asset_id": aid,
            "source_start_frame": 0, "source_end_frame": 300,
            "timeline_start_frame": 300,
            "track_id": tid,
        })
        assert r.status_code == 200, r.text
    # Sanity: V1/V2/V3 all present with their clips.
    proj = c.get("/project").json()
    track_ids = {t["track_id"] for t in proj["timelines"][0]["tracks"]}
    assert {"v1", "v2", "v3"} <= track_ids
    clip_track_ids = {cl["track_id"] for cl in proj["clips"].values()}
    assert {"v1", "v2", "v3"} <= clip_track_ids
    return c


def _at_frame(client, frame: int) -> dict:
    # The endpoint takes FRAMES (project sequence fps), not seconds.
    # The clips span seconds [10, 20]; at 30fps that's frames
    # [300, 600]. The "midpoint" frame is 450.
    return client.get(
        f"/preview/at_frame?frame={frame}&timeline_id=main"
    ).json()


def _plan(client) -> dict:
    return client.get("/preview/plan?timeline_id=main").json()


# ── Step 1: 3-layer coexistence ──────────────────────────────────
def test_v1_v2_v3_coexist_at_frame_15(ml_client):
    """At frame 450 (midpoint of clip range [300, 600] at 30fps),
    all three clips are active. The preview must return 3
    visual_layers, one per track."""
    pv = _at_frame(ml_client, 450)
    tracks = [l["track_id"] for l in pv["visual_layers"]]
    assert sorted(tracks) == ["v1", "v2", "v3"], (
        f"3-layer coexistence broken at frame 450: {tracks}"
    )


# ── Step 2: V1 sits ABOVE V2/V3 (Timeline-higher = Preview-top) ────
def test_v1_above_v2_v3_in_z_order(ml_client):
    """GUI-04.6 direction: V1 (Timeline top) has the HIGHEST
    layer_index; V3 (Timeline bottom) has the LOWEST. The
    composite stacks V1 on top, V3 on bottom — matching the
    Timeline's vertical order exactly.

    Invariant: a visual track appearing higher in the Timeline
    is a higher visual layer in Preview.
    """
    pv = _at_frame(ml_client, 450)
    by_track = {l["track_id"]: l["layer_index"] for l in pv["visual_layers"]}
    assert by_track["v1"] > by_track["v2"] > by_track["v3"], (
        f"layer_index order must be v1 > v2 > v3 (Timeline top = "
        f"Preview top); got {by_track}"
    )


# ── Step 3: layer_index globally unique ──────────────────────────
def test_layer_index_globally_unique_in_plan(ml_client):
    """R4-1 invariant: layer_index is globally unique across all
    visual tracks in /preview/plan."""
    plan = _plan(ml_client)
    layers = plan["tracks"]
    flat = [l for sub in layers for l in sub]
    indices = [l["layer_index"] for l in flat]
    assert len(indices) == len(set(indices)), (
        f"layer_index collision: {indices}"
    )


# ── Step 4: hidden V2 reveals V1+V3 ──────────────────────────────
def test_hidden_v2_reveals_v1_and_v3(ml_client):
    """Hiding V2 must immediately drop V2 from the composite while
    keeping V1 and V3 — the lower layer is revealed."""
    ml_client.post("/tracks/v2/hide", params={"hidden": True})
    pv = _at_frame(ml_client, 450)
    tracks = sorted(l["track_id"] for l in pv["visual_layers"])
    assert "v2" not in tracks, (
        f"hidden V2 still in composite: {tracks}"
    )
    assert "v1" in tracks and "v3" in tracks, (
        f"hiding V2 must keep V1 and V3 visible; got {tracks}"
    )


# ── Step 5: hidden V3 reveals V1+V2 ──────────────────────────────
def test_hidden_v3_reveals_v1_and_v2(ml_client):
    """Hiding V3 must drop V3 and keep V1 + V2."""
    ml_client.post("/tracks/v3/hide", params={"hidden": True})
    pv = _at_frame(ml_client, 450)
    tracks = sorted(l["track_id"] for l in pv["visual_layers"])
    assert "v3" not in tracks, (
        f"hidden V3 still in composite: {tracks}"
    )
    assert "v1" in tracks and "v2" in tracks, (
        f"hiding V3 must keep V1 and V2 visible; got {tracks}"
    )


# ── Step 6: hidden both → only V1 ────────────────────────────────
def test_hidden_v2_and_v3_reveals_v1_only(ml_client):
    """Hiding BOTH V2 and V3 leaves only V1 in the composite. This
    is the 'hidden upper layer immediately reveals lower layer'
    invariant — the lower layer is now the topmost visible layer."""
    ml_client.post("/tracks/v2/hide", params={"hidden": True})
    ml_client.post("/tracks/v3/hide", params={"hidden": True})
    pv = _at_frame(ml_client, 450)
    tracks = [l["track_id"] for l in pv["visual_layers"]]
    assert tracks == ["v1"], (
        f"with V2+V3 hidden, only V1 should be visible; got {tracks}"
    )


# ── Step 7: re-show restores all three ───────────────────────────
def test_unhide_restores_3_layer_composite(ml_client):
    """After hiding V2 and V3, unhiding them must restore the full
    3-layer composite at frame 450."""
    ml_client.post("/tracks/v2/hide", params={"hidden": True})
    ml_client.post("/tracks/v3/hide", params={"hidden": True})
    ml_client.post("/tracks/v2/hide", params={"hidden": False})
    ml_client.post("/tracks/v3/hide", params={"hidden": False})
    pv = _at_frame(ml_client, 450)
    tracks = sorted(l["track_id"] for l in pv["visual_layers"])
    assert tracks == ["v1", "v2", "v3"], (
        f"unhide should restore all 3; got {tracks}"
    )


# ── Step 8: frame outside overlap → no layers ────────────────────
def test_frame_outside_overlap_has_no_layers(ml_client):
    """At frame 150 (before any clip starts at 300) and frame 750
    (after all clips end at 600), the composite must be empty."""
    assert _at_frame(ml_client, 150)["visual_layers"] == []
    assert _at_frame(ml_client, 750)["visual_layers"] == []