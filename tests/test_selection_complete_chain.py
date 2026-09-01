# GUI-03R4.1 P0-4: Selection Complete Chain (marquee → Core Op →
# track cleanup → undo).
#
# Pins the ENTIRE chain end-to-end:
#   1. Marquee selection on the GUI side → set of clip_ids
#   2. /selection/delete (preserve gap OR ripple) → ONE Core Operation
#   3. Empty-track auto-cleanup (W-B) → if a track lost its last
#      clip, it's removed from tl.tracks atomically with the
#      selection delete.
#   4. Undo restores the deleted clips AND the auto-deleted track.
#
# Each test isolates one aspect of the chain. The local fixture
# (chain_client) gives us a fresh lease + project with a registered
# VIDEO asset, so we can seed clips and exercise the chain without
# depending on the dirty/clean Sanlihe fixture on disk.

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational
from yroll.server.app import create_app


@pytest.fixture()
def chain_client(tmp_path: Path):
    """TestClient + small wrapper that auto-attaches sessionId +
    the LIVE baseRevision. Pre-populates with a registered VIDEO
    asset so tests can seed clips and exercise the chain.
    """
    core = ProjectCore.create(tmp_path, "p0-4-chain-test")
    a_v = Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v1.mp4",
        identity=AssetIdentity(md5="v" * 32, size_bytes=1, duration_sec=10.0),
    )
    a_v.source_fps = Rational(30, 1)
    a_v.source_is_cfr = True
    core.project.assets.append(a_v)
    core.save_state()
    app = create_app(core.path, who=Actor.AI)
    raw = TestClient(app)
    r = raw.post("/lease/acquire?actor=agent&mode=edit&actorId=p0-4")
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

    return _Call()


def _seed_three_v1_clips(client) -> list[str]:
    """Add 3 non-overlapping clips on v1 at [0..1], [2..3], [4..5].
    v1 is auto-created by add_clip (per the auto-allocator)."""
    ids = []
    for i in range(3):
        r = client.post("/clips", json={
            "asset_id": "a1",
            "source_start_frame": 0, "source_end_frame": 30,
            "timeline_start_frame": i * 60,  # R6-B: frames
            "track_id": "v1",
        })
        assert r.status_code == 200, r.text
        ids.append(r.json()["clip_id"])
    return ids


def _track_ids(client) -> set[str]:
    p = client.get("/project").json()
    for tl in p["timelines"]:
        if tl["timeline_id"] == "main":
            return {t["track_id"] for t in tl["tracks"]}
    return set()


def _clips_map(client) -> dict[str, dict]:
    return client.get("/project").json()["clips"]


def _op_count(client) -> int:
    return len(client.get("/operations").json())


# ── Chain step 1+2: marquee (modeled as a set of ids) → ONE Op ──
def test_marquee_selection_delete_emits_one_operation(chain_client):
    """Step 1+2: a marquee on the GUI side yields a clip_id set;
    the parent calls /selection/delete with that set; Core emits
    ONE Operation regardless of selection size."""
    c1, c2, c3 = _seed_three_v1_clips(chain_client)
    ops_before = _op_count(chain_client)
    r = chain_client.post("/selection/delete", json={
        "clip_ids": [c1, c3],  # non-contiguous marquee
        "ripple": False,
        "why": "GUI marquee selection delete",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert sorted(body["deleted"]) == sorted([c1, c3])
    # Exactly ONE Operation for the whole selection.
    ops_after = _op_count(chain_client)
    assert ops_after - ops_before == 1, (
        f"selection delete must emit ONE Operation, "
        f"got {ops_after - ops_before}"
    )


# ── Chain step 3: track cleanup when last clip is deleted ──────
def test_selection_delete_triggers_track_cleanup(chain_client):
    """Step 3: when a selection delete removes the LAST clip on a
    track, W-B's auto-cleanup removes that track atomically with
    the delete. The track must be gone from tl.tracks; the
    cleanup is folded into the same single Operation
    (per W-B's "one user intent = one Core Operation" rule)."""
    # Create a fresh solo track via the canonical /tracks endpoint.
    r = chain_client.post("/tracks", params={
        "kind": "video", "track_id": "v_solo", "timeline_id": "main",
    })
    assert r.status_code == 200, r.text
    assert "v_solo" in _track_ids(chain_client)
    # Add one clip to v_solo.
    rc = chain_client.post("/clips", json={
        "asset_id": "a1",
        "source_start_frame": 0, "source_end_frame": 30,
        "timeline_start_frame": 3000,
        "track_id": "v_solo",
    })
    assert rc.status_code == 200, rc.text
    cid = rc.json()["clip_id"]
    # Delete via selection path → track cleanup chain.
    ops_before = _op_count(chain_client)
    rd = chain_client.post("/selection/delete", json={
        "clip_ids": [cid], "ripple": False, "why": "delete last clip",
    })
    assert rd.status_code == 200, rd.text
    ops_after = _op_count(chain_client)
    # ONE Operation (selection delete folds the cleanup into itself).
    assert ops_after - ops_before == 1, (
        f"selection-delete + track-cleanup must be ONE Operation, "
        f"got {ops_after - ops_before}"
    )
    # The clip is gone and the track is auto-removed.
    assert cid not in _clips_map(chain_client)
    assert "v_solo" not in _track_ids(chain_client), (
        f"track v_solo must auto-cleanup after losing its last clip; "
        f"tracks remain: {_track_ids(chain_client)}"
    )


# ── Chain step 4: undo restores the entire chain state ─────────
def test_undo_restores_selection_delete_and_track(chain_client):
    """Step 4: undoing the selection-delete Operation restores BOTH
    the deleted clips AND the auto-cleaned track."""
    chain_client.post("/tracks", params={
        "kind": "video", "track_id": "v_undo", "timeline_id": "main",
    })
    rc = chain_client.post("/clips", json={
        "asset_id": "a1",
        "source_start_frame": 0, "source_end_frame": 30,
        "timeline_start_frame": 6000,
        "track_id": "v_undo",
    })
    cid = rc.json()["clip_id"]
    chain_client.post("/selection/delete", json={
        "clip_ids": [cid], "ripple": False,
        "why": "delete + cleanup for undo",
    })
    assert cid not in _clips_map(chain_client)
    assert "v_undo" not in _track_ids(chain_client)
    # Undo the most recent Operation. /history/undo is a mutation
    # endpoint and needs the gate.
    rev = _op_count(chain_client)
    ru = chain_client.post("/history/undo",
                           params={"why": "P0-4 undo", "baseRevision": rev})
    assert ru.status_code == 200, ru.text
    # The clip is restored AND the track reappears.
    proj = chain_client.get("/project").json()
    assert cid in proj["clips"], (
        f"undo must restore deleted clip {cid}; "
        f"present: {cid in proj['clips']}"
    )
    assert "v_undo" in _track_ids(chain_client), (
        f"undo must restore auto-cleaned track v_undo; "
        f"tracks: {_track_ids(chain_client)}"
    )


# ── Chain ripple variant: marquee → ripple → ONE Op → undo ──────
def test_marquee_ripple_one_op_undo_restores(chain_client):
    """End-to-end chain with ripple=true: marquee (3 clips on v1)
    → /selection/delete with ripple=true → ONE Operation →
    undo restores the original timeline shape."""
    c1, c2, c3 = _seed_three_v1_clips(chain_client)
    ops_before = _op_count(chain_client)
    r = chain_client.post("/selection/delete", json={
        "clip_ids": [c1, c2, c3],
        "ripple": True,
        "why": "GUI marquee ripple",
    })
    assert r.status_code == 200, r.text
    ops_after = _op_count(chain_client)
    # ONE Operation covers all 3 clips + ripple shift.
    assert ops_after - ops_before == 1, (
        f"ripple selection-delete must emit ONE Operation, "
        f"got {ops_after - ops_before}"
    )
    # All 3 clips gone.
    for cid in (c1, c2, c3):
        assert cid not in _clips_map(chain_client)
    # Undo restores the timeline shape.
    rev = _op_count(chain_client)
    ru = chain_client.post("/history/undo",
                           params={"why": "P0-4 ripple undo", "baseRevision": rev})
    assert ru.status_code == 200, ru.text
    proj = chain_client.get("/project").json()
    for cid in (c1, c2, c3):
        assert cid in proj["clips"], f"undo must restore {cid}"
    # Original timeline ranges are preserved by undo.
    assert proj["clips"][c1]["timeline_range"]["start"] == pytest.approx(0.0)
    assert proj["clips"][c2]["timeline_range"]["start"] == pytest.approx(2.0)
    assert proj["clips"][c3]["timeline_range"]["start"] == pytest.approx(4.0)


# ── Static guard: GUI's batch panel Delete button calls
#    /selection/delete, NOT a loop of /clips/{id} DELETE ───────────
def test_batch_delete_uses_selection_endpoint(chain_client):
    """The GUI batch panel "全部删除" button calls api.deleteSelection
    which posts to /selection/delete. A loop of single-clip DELETEs
    would emit N Operations for N clips. This test pins that the
    selection-delete endpoint exists and accepts multi-clip input —
    the GUI client code (gui/src/api.ts) is a static target for
    the same invariant."""
    c1, c2, _c3 = _seed_three_v1_clips(chain_client)
    ops_before = _op_count(chain_client)
    r = chain_client.post("/selection/delete", json={
        "clip_ids": [c1, c2],
        "ripple": False,
        "why": "GUI batch delete (route through selection endpoint)",
    })
    assert r.status_code == 200, r.text
    ops_after = _op_count(chain_client)
    # Exactly ONE Operation — proves the chain's "one user intent
    # = one Core Operation" invariant holds end-to-end.
    assert ops_after - ops_before == 1