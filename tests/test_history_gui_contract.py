"""GUI-04 04-03: History / Undo / Redo contract for the GUI path.

GUI contract:
    Ctrl+Z → POST /history/undo
    Ctrl+Y → POST /history/redo

The GUI must NOT depend on /revert for normal undo/redo. /revert
is kept as an operation-specific low-level compatibility endpoint
(plan §5.2).

Acceptance (plan §5.3 — exact user-visible state, not just metadata):

  M1. Move → Undo → exact timeline frame / track
  M2. Move → Undo → Redo → exact final frame / track
  M3. Delete last clip from a track → Undo restores BOTH clip and track
  M4. Ripple Delete → Undo restores exact original clip positions
      AND track membership

This module pins those invariants at the HTTP boundary. The
companion browser smoke (gui/smoke/gui-04-03-undo-redo.mjs)
verifies the same invariants through real-browser keyboard events.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.server.app import _STATE, create_app
from tests.conftest import _AuthedClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def authed_client(tmp_path):
    """Mirrors test_server.py: TestClient with auto-attach sessionId
    + baseRevision; one video asset pre-seeded."""
    core = ProjectCore.create(tmp_path, "history-contract")
    ProjectCore.ensure_default_tracks(core)
    app = create_app(core.path, who=Actor.AI)
    st = _STATE["default"]
    if not any(a.asset_id == "a-history" for a in st.core.project.assets):
        st.core.project.assets.append(Asset(
            asset_id="a-history", type=AssetType.VIDEO, path="",
            identity=AssetIdentity(md5="1" * 32, size_bytes=0,
                                   duration_sec=10.0,
                                   width=1920, height=1080),
        ))
        st.core.save_state()
    app = create_app(core.path, who=Actor.AI)
    return _AuthedClient(TestClient(app))


@pytest.fixture()
def client(authed_client) -> TestClient:
    """Raw TestClient without auth (for route-existence checks)."""
    return authed_client._raw


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _frame_of(seconds: float, fps: int) -> int:
    """Convert a seconds value to integer frames at the given fps."""
    return round(seconds * fps)


def _find_track(proj, track_id: str):
    """Find a track by id in either legacy `timeline.tracks` or new
    `timelines[].tracks` shape. Returns None if not found."""
    for t in (proj.get("timeline", {}) or {}).get("tracks", []) or []:
        if t["track_id"] == track_id:
            return t
    for tl in proj.get("timelines", []) or []:
        for t in (tl.get("tracks", []) or []):
            if t["track_id"] == track_id:
                return t
    return None


# ---------------------------------------------------------------------------
# M1: Move → Undo → exact frame / track
# ---------------------------------------------------------------------------

class TestMoveUndoExactFrame:
    """The simplest undo path. User moves a clip from (frame 0,
    track v1) to (frame 100, track v1). Undo must restore (0, v1)
    exactly — no frame drift, no track change."""

    def test_move_then_undo_restores_exact_frame_and_track(self, authed_client):
        r = authed_client.post("/clips", json={
            "asset_id": "a-history",
            "source_start_frame": 0, "source_end_frame": 300,
            "timeline_start_frame": 0,
            "track_id": "v1",
            "why": "seed",
        })
        assert r.status_code == 200, r.text
        clip_id = r.json()["clip_id"]

        r = authed_client.post(f"/clips/{clip_id}/move", json={
            "new_timeline_start_frame": 100,
            "why": "move",
        })
        assert r.status_code == 200, r.text
        clip = authed_client.get("/project").json()["clips"][clip_id]
        assert _frame_of(clip["timeline_range"]["start"], 30) == 100
        assert clip["track_id"] == "v1"

        r = authed_client.post("/history/undo")
        assert r.status_code == 200, r.text
        clip = authed_client.get("/project").json()["clips"][clip_id]
        assert _frame_of(clip["timeline_range"]["start"], 30) == 0, (
            f"frame not restored: got {clip['timeline_range']['start']}"
        )
        assert clip["track_id"] == "v1", (
            f"track not restored: got {clip['track_id']}"
        )

    def test_undo_only_touches_one_operation(self, authed_client):
        """Undo of a Move must NOT also undo anything else (e.g. the
        preceding add_clip). Exactly one new revert: marker is added."""
        r = authed_client.post("/clips", json={
            "asset_id": "a-history",
            "source_start_frame": 0, "source_end_frame": 300,
            "timeline_start_frame": 0, "track_id": "v1",
            "why": "seed",
        })
        assert r.status_code == 200, r.text
        clip_id = r.json()["clip_id"]

        before_ops = authed_client.get("/operations").json()
        before_reverts = len([o for o in before_ops if o["type"].startswith("revert:")])

        r = authed_client.post(f"/clips/{clip_id}/move", json={
            "new_timeline_start_frame": 50, "why": "move",
        })
        assert r.status_code == 200

        r = authed_client.post("/history/undo")
        assert r.status_code == 200

        ops = authed_client.get("/operations").json()
        # Core records both seed and move as their respective types;
        # undo logs a single new revert: marker.
        assert any(o["type"] == "add_clip" for o in ops), "add_clip must remain"
        # Core records move ops as type "move" (see commands.py:1679).
        assert any(o["type"] == "move" for o in ops), (
            f"move op must remain after undo (got types: "
            f"{[o['type'] for o in ops]})"
        )
        revert_markers = [o for o in ops if o["type"].startswith("revert:")]
        assert len(revert_markers) == before_reverts + 1, (
            f"expected exactly one new revert marker, got ops: "
            f"{[o['type'] for o in ops]}"
        )


# ---------------------------------------------------------------------------
# M2: Move → Undo → Redo → exact final frame / track
# ---------------------------------------------------------------------------

class TestMoveUndoRedoExactFrame:
    """Round-trip: Move to 100, Undo → 0, Redo → 100."""

    def test_move_undo_redo_round_trip(self, authed_client):
        r = authed_client.post("/clips", json={
            "asset_id": "a-history",
            "source_start_frame": 0, "source_end_frame": 300,
            "timeline_start_frame": 0, "track_id": "v1",
            "why": "seed",
        })
        assert r.status_code == 200, r.text
        clip_id = r.json()["clip_id"]

        r = authed_client.post(f"/clips/{clip_id}/move", json={
            "new_timeline_start_frame": 100, "why": "move",
        })
        assert r.status_code == 200

        r = authed_client.post("/history/undo")
        assert r.status_code == 200
        clip = authed_client.get("/project").json()["clips"][clip_id]
        assert _frame_of(clip["timeline_range"]["start"], 30) == 0

        r = authed_client.post("/history/redo")
        assert r.status_code == 200, r.text
        clip = authed_client.get("/project").json()["clips"][clip_id]
        assert _frame_of(clip["timeline_range"]["start"], 30) == 100, (
            f"redo did not restore 100: got {clip['timeline_range']['start']}"
        )
        assert clip["track_id"] == "v1"


# ---------------------------------------------------------------------------
# M3: Delete last clip from a track → Undo restores BOTH clip AND track
# ---------------------------------------------------------------------------

class TestDeleteLastClipUndoRestoresBoth:
    """User scenario: a track has one clip, the user deletes it.
    The Core auto-cleans empty tracks; the user then undoes.
    Per plan §5.3, undo must restore BOTH the clip AND the track.

    NOTE: we use a non-default track (v99) so the auto-cleanup
    actually fires. Default tracks (v1, v2, v3) are NOT auto-cleaned
    when emptied — they survive as a user-visible artifact — which
    is also valid Core behavior, but doesn't exercise the cleanup +
    restore path."""

    def test_delete_then_undo_restores_clip_and_track(self, authed_client):
        # Create a fresh track so the cleanup path actually fires.
        # _AuthedClient only injects sessionId/baseRevision; pass
        # other query params via params=.
        r = authed_client.post(
            "/tracks",
            params={"kind": "video", "track_id": "v99"},
        )
        assert r.status_code == 200, r.text

        r = authed_client.post("/clips", json={
            "asset_id": "a-history",
            "source_start_frame": 0, "source_end_frame": 100,
            "timeline_start_frame": 0, "track_id": "v99",
            "why": "seed-only",
        })
        assert r.status_code == 200, r.text
        clip_id = r.json()["clip_id"]
        proj = authed_client.get("/project").json()
        v99 = _find_track(proj, "v99")
        assert v99 is not None, "test setup: v99 track must exist"
        assert clip_id in v99["clip_ids"], "test setup: v99 should hold the clip"

        r = authed_client.delete(f"/clips/{clip_id}")
        assert r.status_code == 200, r.text

        # After delete: v99 has been auto-cleaned (empty non-default
        # tracks disappear). The clip is also gone.
        proj = authed_client.get("/project").json()
        v99 = _find_track(proj, "v99")
        assert v99 is None, (
            f"v99 should be auto-cleaned after delete, but still present: {v99}"
        )
        assert clip_id not in proj["clips"], "clip should be gone after delete"

        # /history/undo must restore BOTH the track AND the clip.
        r = authed_client.post("/history/undo")
        assert r.status_code == 200, r.text

        proj = authed_client.get("/project").json()
        assert clip_id in proj["clips"], (
            f"clip {clip_id} not restored in clips dict after undo"
        )
        v99 = _find_track(proj, "v99")
        assert v99 is not None, "track v99 must be restored after undo"
        assert clip_id in v99["clip_ids"], (
            f"clip {clip_id} not restored in track v99.clip_ids after undo"
        )
        clip = proj["clips"][clip_id]
        assert _frame_of(clip["timeline_range"]["start"], 30) == 0


# ---------------------------------------------------------------------------
# M4: Ripple Delete → Undo restores exact positions + track membership
# ---------------------------------------------------------------------------

class TestRippleDeleteUndoRestoresExactState:
    """Ripple delete removes the clip AND shifts same-track neighbors
    left to close the gap. Undo must restore BOTH the removed clip
    AND the original positions of every other clip on the same track."""

    def _seed_three_clips_in_a_row(self, authed_client):
        ids = []
        for start in [0, 100, 200]:
            r = authed_client.post("/clips", json={
                "asset_id": "a-history",
                "source_start_frame": 0, "source_end_frame": 100,
                "timeline_start_frame": start,
                "track_id": "v1",
                "why": f"seed-{start}",
            })
            assert r.status_code == 200, r.text
            ids.append(r.json()["clip_id"])
        return ids

    def test_ripple_middle_then_undo_restores_exact_positions(self, authed_client):
        c0, c1, c2 = self._seed_three_clips_in_a_row(authed_client)

        proj = authed_client.get("/project").json()
        for cid, expected_start in [(c0, 0), (c1, 100), (c2, 200)]:
            clip = proj["clips"][cid]
            assert _frame_of(clip["timeline_range"]["start"], 30) == expected_start

        # /clips/{id}?ripple=true is the DELETE path.
        # Note: _AuthedClient only injects sessionId/baseRevision,
        # so other URL query params must be passed via params=.
        r = authed_client.delete(f"/clips/{c1}", params={"ripple": "true"})
        assert r.status_code == 200, r.text

        proj = authed_client.get("/project").json()
        assert c1 not in proj["clips"], "c1 should be gone after ripple"
        c2_clip = proj["clips"][c2]
        assert _frame_of(c2_clip["timeline_range"]["start"], 30) == 100, (
            f"after ripple, c2 should be at frame 100 (got "
            f"{c2_clip['timeline_range']['start']})"
        )

        r = authed_client.post("/history/undo")
        assert r.status_code == 200, r.text

        proj = authed_client.get("/project").json()
        assert c1 in proj["clips"], (
            f"ripple-undone clip {c1} not restored"
        )
        c0_clip = proj["clips"][c0]
        c1_clip = proj["clips"][c1]
        c2_clip = proj["clips"][c2]
        assert _frame_of(c0_clip["timeline_range"]["start"], 30) == 0
        assert _frame_of(c1_clip["timeline_range"]["start"], 30) == 100
        assert _frame_of(c2_clip["timeline_range"]["start"], 30) == 200, (
            f"c2 should be restored to frame 200 (got "
            f"{c2_clip['timeline_range']['start']})"
        )

        v1 = _find_track(proj, "v1")
        assert v1 is not None
        assert c0 in v1["clip_ids"]
        assert c1 in v1["clip_ids"]
        assert c2 in v1["clip_ids"]


# ---------------------------------------------------------------------------
# GUI contract: /history/undo is the GUI's path, /revert stays low-level
# ---------------------------------------------------------------------------

class TestGuiUsesHistoryNotRevert:
    """Pin the GUI contract: normal Ctrl+Z/Y uses /history/*.
    /revert remains as low-level compat (still works for any caller
    that wants operation-specific revert)."""

    def test_history_undo_endpoint_exists(self, client):
        r = client.post("/history/undo")
        # No lease → 403 (gate), but the route IS reachable.
        assert r.status_code in (200, 400, 403), r.text

    def test_history_redo_endpoint_exists(self, client):
        r = client.post("/history/redo")
        assert r.status_code in (200, 400, 403), r.text

    def test_history_state_endpoint_exists(self, client):
        # Gate-exempt GET.
        r = client.get("/history/state")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "can_undo" in body
        assert "can_redo" in body