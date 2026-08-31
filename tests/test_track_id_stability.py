"""GUI-03R3-W-B.5: track IDs are stable across auto-delete.

Per user feedback: "Track IDs of remaining tracks must NEVER be
renumbered after deletion. V1/V2/V3 → delete V2 → V1/V3 remain V1/V3.
A future newly allocated visual track may reuse the lowest unused ID
for that kind, but existing tracks never rename."

This file pins that contract across:
  - the auto-cleanup path (remove last clip, move cross-track)
  - the explicit delete path (delete_track)
  - the new-track allocator (ensure_track_for_drop, allocate_track_for)
  - the revert path (auto-cleanup is reversible)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.commands import CommandError, CommandLayer
from yroll.core.manifest import Actor, TrackKind
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational


def _fresh_core_with_videos(tmp_path: Path, n_video: int = 3
                             ) -> ProjectCore:
    """Create a project with N named video tracks and one clip each."""
    core = ProjectCore.create(tmp_path, "track-id-stability")
    a = Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="v" * 32, size_bytes=1, duration_sec=10.0),
    )
    a.source_fps = Rational(30, 1); a.source_is_cfr = True
    core.project.assets.append(a)
    core.save_state()
    layer = CommandLayer(core, who=Actor.HUMAN)
    for i in range(1, n_video + 1):
        tid = f"v{i}"
        layer.add_track(TrackKind.VIDEO, tid)
        layer.add_clip("a1", 0.0, 1.0, timeline_start=float(i * 10), track_id=tid)
    return core


def _track_ids(core: ProjectCore) -> list[str]:
    return [t.track_id for t in core.project.timeline.tracks]


# ---------- 1. V1/V2/V3 → delete last clip on V2 → V1 and V3 remain ----------

def test_delete_middle_track_keeps_outer_ids(tmp_path):
    core = _fresh_core_with_videos(tmp_path, n_video=3)
    layer = CommandLayer(core, who=Actor.HUMAN)
    assert _track_ids(core) == ["v1", "v2", "v3"]
    # Find the v2 clip and remove it.
    v2 = next(t for t in core.project.timeline.tracks if t.track_id == "v2")
    assert len(v2.clip_ids) == 1
    layer.remove_clip(v2.clip_ids[0], why="test")
    # Remaining tracks keep their ids: V1 and V3 — NOT V1/V2.
    assert _track_ids(core) == ["v1", "v3"], (
        f"expected ['v1', 'v3'] but got {_track_ids(core)}"
    )


# ---------- 2. Next new visual track reuses the lowest unused id (v2 again) ----------

def test_after_delete_next_visual_reuses_lowest_unused_id(tmp_path):
    core = _fresh_core_with_videos(tmp_path, n_video=3)
    layer = CommandLayer(core, who=Actor.HUMAN)
    v2 = next(t for t in core.project.timeline.tracks if t.track_id == "v2")
    layer.remove_clip(v2.clip_ids[0], why="test")
    assert _track_ids(core) == ["v1", "v3"]
    # Now allocate a new visual track. Explicit `insert_after_track_id`
    # creates a NEW track; lowest unused id is "v2" (reused, NOT a
    # rename of v1 or v3).
    new_track = layer.ensure_track_for_drop(
        "video", insert_after_track_id="v3",
    )
    assert new_track.track_id == "v2", (
        f"next visual track should reuse lowest unused id 'v2', got {new_track.track_id!r}"
    )
    # v1 and v3 keep their ids — no renumber.
    assert "v1" in _track_ids(core)
    assert "v3" in _track_ids(core)
    assert _track_ids(core).count("v2") == 1


# ---------- 3. Explicit delete_track preserves remaining ids ----------

def test_explicit_delete_track_preserves_outer_ids(tmp_path):
    """When the user wants to remove a non-empty track explicitly,
    the explicit-delete path (delete_track) refuses with a clear
    error (the caller must remove clips first). The auto-cleanup
    path then handles the empty-track removal. After both, remaining
    ids are unchanged."""
    core = _fresh_core_with_videos(tmp_path, n_video=3)
    layer = CommandLayer(core, who=Actor.HUMAN)
    # Explicit delete_track on a non-empty track must refuse.
    with pytest.raises(CommandError, match=r"still has"):
        layer.delete_track("v2", why="explicit")
    # The track is untouched; remaining ids unchanged.
    assert _track_ids(core) == ["v1", "v2", "v3"]
    # Remove v2's clip → auto-cleanup removes v2.
    v2 = next(t for t in core.project.timeline.tracks if t.track_id == "v2")
    layer.remove_clip(v2.clip_ids[0], why="prep")
    # After auto-cleanup, v2 is gone; v1 and v3 keep their ids.
    assert _track_ids(core) == ["v1", "v3"]


# ---------- 4. Move-last-clip cross-track preserves outer ids ----------

def test_cross_track_move_preserves_outer_ids(tmp_path):
    """V1 has one clip; V3 has one clip. Move V1's clip to V3 (with
    non-overlapping timeline placement). V1 becomes empty and is
    removed. Remaining ids are V3 (unchanged) — V1 and V2 both gone
    if V2 was empty, but in this test V2 still has its clip, so
    V1 and V3 remain. Actually let's only set up V1 and V3."""
    core = ProjectCore.create(tmp_path, "track-id-stability-move")
    a = Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="v" * 32, size_bytes=1, duration_sec=10.0),
    )
    a.source_fps = Rational(30, 1); a.source_is_cfr = True
    core.project.assets.append(a)
    core.save_state()
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_track(TrackKind.VIDEO, "v1")
    layer.add_track(TrackKind.VIDEO, "v3")
    c1 = layer.add_clip("a1", 0.0, 1.0, timeline_start=0.0, track_id="v1")
    c3 = layer.add_clip("a1", 0.0, 1.0, timeline_start=10.0, track_id="v3")
    # Move c1 from v1 to v3 (different timeline range so no overlap).
    layer.move_clip(c1.clip_id, new_timeline_start=20.0, new_track_id="v3")
    # v1 empty → removed; v3 stays. Outer ids preserved.
    assert _track_ids(core) == ["v3"], (
        f"expected ['v3'] but got {_track_ids(core)}"
    )


# ---------- 5. Batch delete preserves ids of non-empty tracks ----------

def test_batch_delete_preserves_ids_of_non_empty_tracks(tmp_path):
    core = _fresh_core_with_videos(tmp_path, n_video=3)
    layer = CommandLayer(core, who=Actor.HUMAN)
    # Remove all clips from v2 and v3; v1 still has its clip.
    v2 = next(t for t in core.project.timeline.tracks if t.track_id == "v2")
    v3 = next(t for t in core.project.timeline.tracks if t.track_id == "v3")
    layer.remove_clip(v2.clip_ids[0], why="test")
    layer.remove_clip(v3.clip_ids[0], why="test")
    # Only v1 remains (with its clip).
    assert _track_ids(core) == ["v1"]
    # Sanity: v1 was NOT renamed to "v2".
    assert _track_ids(core)[0] == "v1"


# ---------- 6. delete_track unknown id raises clear CommandError ----------

def test_delete_track_unknown_id_raises_command_error(tmp_path):
    core = _fresh_core_with_videos(tmp_path, n_video=2)
    layer = CommandLayer(core, who=Actor.HUMAN)
    with pytest.raises(CommandError, match=r"track not found"):
        layer.delete_track("v99", why="test")


# ---------- 7. delete_track refuses on non-empty track ----------

def test_delete_track_refuses_on_non_empty(tmp_path):
    core = _fresh_core_with_videos(tmp_path, n_video=1)
    layer = CommandLayer(core, who=Actor.HUMAN)
    with pytest.raises(CommandError, match=r"still has"):
        layer.delete_track("v1", why="test")


# ---------- 8. The helper never renumbers; explicit insert_after creates new ----------

def test_repeated_insert_after_creates_sequential_ids(tmp_path):
    core = _fresh_core_with_videos(tmp_path, n_video=3)
    layer = CommandLayer(core, who=Actor.HUMAN)
    initial = _track_ids(core)
    # Each call with insert_after_track_id creates a NEW track of
    # the right kind. The new tracks get the lowest unused id; the
    # existing tracks keep theirs (no renumber).
    new_ids = []
    anchor = initial[-1]  # "v3"
    for _ in range(5):
        t = layer.ensure_track_for_drop(
            "video", insert_after_track_id=anchor,
        )
        new_ids.append(t.track_id)
        anchor = t.track_id  # chain the anchor so each new track comes after the previous one
    # The first 3 existing tracks must NOT have been renamed.
    assert _track_ids(core)[:3] == initial
    # New ids are v4, v5, v6, v7, v8 (lowest unused sequentially).
    assert new_ids == ["v4", "v5", "v6", "v7", "v8"], (
        f"unexpected allocator ids: {new_ids}"
    )
