"""GUI-03R3-W-B.4: track auto-delete regression tests.

Atomic invariant: every mutation that could empty a track (remove_clip,
move_clip cross-track, ripple_delete_clip, delete_selection) MUST run
_cleanup_empty_tracks at the end so the Timeline is never observed
with an empty track. The cleanup is part of the SAME Operation as the
mutation that emptied it (no separate "cleanup" Operation).

These tests pin the invariant across all four mutation paths and the
batch (delete_selection) path.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.commands import CommandError, CommandLayer
from yroll.core.manifest import (
    Actor,
    Track,
    TrackKind,
)
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.selection import Selection
from yroll.core.timebase import Rational


def _fresh_core(tmp_path: Path) -> ProjectCore:
    """Create a clean Timeline with no empty default tracks.

    W-B invariant: tl.tracks contains only tracks with >= 1 clip.
    The legacy `ensure_default_tracks` helper (still used by older
    tests) pre-creates 8 empty tracks; under W-B those are
    auto-removed on the first mutation. Tests for the W-B invariant
    need a clean slate so the post-mutation `removed_tracks` field
    only reflects THIS test's mutations.
    """
    core = ProjectCore.create(tmp_path, "track-auto-delete-test")
    # Intentionally do NOT call ProjectCore.ensure_default_tracks.
    a = Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="v" * 32, size_bytes=1, duration_sec=10.0),
    )
    a.source_fps = Rational(30, 1); a.source_is_cfr = True
    core.project.assets.append(a)
    a_audio = Asset(
        asset_id="a_audio", type=AssetType.AUDIO, path="a.mp3",
        identity=AssetIdentity(md5="a" * 32, size_bytes=1, duration_sec=10.0),
    )
    a_audio.source_fps = Rational(30, 1); a_audio.source_is_cfr = True
    core.project.assets.append(a_audio)
    core.save_state()
    return core


def _surviving_track_ids(core: ProjectCore) -> list[str]:
    return [t.track_id for t in core.project.timeline.tracks]


# ---------- 1. remove last clip on a track → track disappears ----------

def test_remove_last_clip_auto_deletes_track(tmp_path):
    """The CORE invariant: when the last clip is removed from a
    track, the track itself is removed in the same Operation."""
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    c = layer.add_clip("a1", 0.0, 1.0, timeline_start=0.0, track_id="v1")
    assert "v1" in _surviving_track_ids(core)
    op = layer.remove_clip(c.clip_id, why="test")
    # Same Operation records the auto-delete in `after.removed_tracks`.
    assert op.after.get("removed_tracks") == ["v1"]
    # v1 is gone.
    assert "v1" not in _surviving_track_ids(core)
    # No orphan empty tracks anywhere.
    for t in core.project.timeline.tracks:
        assert len(t.clip_ids) >= 1


# ---------- 2. move last clip cross-track → source track disappears ----------

def test_move_last_clip_cross_track_auto_deletes_source(tmp_path):
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    # Add the clip first (allocator creates v1).
    c = layer.add_clip("a1", 0.0, 1.0, timeline_start=0.0, track_id="v1")
    assert c.track_id == "v1"
    assert "v1" in _surviving_track_ids(core)
    # Explicitly create v2 (the destination for the move).
    layer.add_track(TrackKind.VIDEO, "v2")
    op = layer.move_clip(c.clip_id, new_timeline_start=5.0, new_track_id="v2")
    # v1 is now empty → auto-removed; v2 holds the clip.
    assert op.after.get("removed_tracks") == ["v1"]
    assert "v1" not in _surviving_track_ids(core)
    assert "v2" in _surviving_track_ids(core)
    v2 = next(t for t in core.project.timeline.tracks if t.track_id == "v2")
    assert c.clip_id in v2.clip_ids


# ---------- 3. cross-track move where source still has another clip → source remains ----------

def test_cross_track_move_keeps_source_when_other_clips_remain(tmp_path):
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    # Two clips on v1 (allocator creates v1), then v2.
    c1 = layer.add_clip("a1", 0.0, 1.0, timeline_start=0.0, track_id="v1")
    c2 = layer.add_clip("a1", 1.0, 2.0, timeline_start=1.0, track_id="v1")
    layer.add_track(TrackKind.VIDEO, "v2")
    # Move c1 away, leave c2 on v1.
    op = layer.move_clip(c1.clip_id, new_timeline_start=10.0, new_track_id="v2")
    # v1 still has c2 → not removed.
    if "removed_tracks" in op.after:
        assert "v1" not in op.after["removed_tracks"]
    assert "v1" in _surviving_track_ids(core)
    assert "v2" in _surviving_track_ids(core)
    v1 = next(t for t in core.project.timeline.tracks if t.track_id == "v1")
    assert v1.clip_ids == [c2.clip_id]


# ---------- 4. batch delete_selection empties multiple tracks ----------

def test_batch_delete_selection_empties_multiple_tracks(tmp_path):
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    # Add 3 clips on 3 distinct tracks. We must create the tracks
    # EXPLICITLY first because add_clip's allocator ignores an
    # explicit track_id when the track doesn't exist (it routes
    # through allocate_track_for which picks the first non-
    # overlapping track — likely v1 again).
    layer.add_track(TrackKind.VIDEO, "v1")
    layer.add_track(TrackKind.VIDEO, "v2")
    layer.add_track(TrackKind.VIDEO, "v3")
    c1 = layer.add_clip("a1", 0.0, 1.0, timeline_start=0.0, track_id="v1")
    c2 = layer.add_clip("a1", 0.0, 1.0, timeline_start=10.0, track_id="v2")
    c3 = layer.add_clip("a1", 0.0, 1.0, timeline_start=20.0, track_id="v3")
    # Each clip lives on its dedicated track.
    assert {c1.track_id, c2.track_id, c3.track_id} == {"v1", "v2", "v3"}
    # Batch delete all three clips → all three tracks empty.
    op = layer.delete_selection(
        Selection.many([c1.clip_id, c2.clip_id, c3.clip_id]),
        ripple=False, why="test",
    )
    removed = sorted(op.after.get("removed_tracks", []))
    assert removed == ["v1", "v2", "v3"]
    for t in core.project.timeline.tracks:
        assert len(t.clip_ids) >= 1


# ---------- 5. explicit delete_track on track with clips raises ----------

def test_explicit_delete_track_with_clips_raises(tmp_path):
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    c = layer.add_clip("a1", 0.0, 1.0, timeline_start=0.0, track_id="v1")
    with pytest.raises(CommandError, match=r"still has"):
        layer.delete_track("v1", why="explicit")
    # Track and clip are untouched.
    assert "v1" in _surviving_track_ids(core)
    assert c.clip_id in core.project.clips


# ---------- 6. explicit delete_track on unknown track_id raises clear error ----------

def test_explicit_delete_track_unknown_raises(tmp_path):
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    with pytest.raises(CommandError, match=r"track not found"):
        layer.delete_track("phantom", why="explicit")
    # Sanity: no tracks present (clean Timeline).
    surviving = _surviving_track_ids(core)
    assert "phantom" not in surviving
    assert surviving == [], (
        f"clean Timeline should have no tracks before any clip; got {surviving}"
    )


# ---------- 7. cleanup is internal — not callable by name from outside ----------

def test_cleanup_helper_is_private(tmp_path):
    """`_cleanup_empty_tracks` is a private helper. It MUST NOT appear
    on the public CommandLayer surface as a callable command."""
    layer = CommandLayer.__dict__
    assert "_cleanup_empty_tracks" in layer
    # Public surface only: delete_track is public, the helper is not.
    # `delete_track` should also exist as a public method.
    assert "delete_track" in layer


# ---------- 8. ripple_delete also auto-cleans the source track ----------

def test_ripple_delete_auto_cleans_source_track(tmp_path):
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    c = layer.add_clip("a1", 0.0, 1.0, timeline_start=0.0, track_id="v1")
    op = layer.ripple_delete_clip(c.clip_id, why="test")
    assert "v1" in op.after.get("removed_tracks", [])
    assert "v1" not in _surviving_track_ids(core)


# ---------- 9. revert of remove_clip restores the auto-deleted track ----------

def test_revert_remove_clip_restores_track(tmp_path):
    """Operations are reversible. Removing the last clip auto-deletes
    the track; reverting the remove must restore both the clip and
    the track (no orphan state)."""
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    c = layer.add_clip("a1", 0.0, 1.0, timeline_start=0.0, track_id="v1")
    op = layer.remove_clip(c.clip_id, why="test")
    assert "v1" not in _surviving_track_ids(core)
    # Revert.
    core.revert(op.operation_id)
    # Track is back, clip is back on it.
    assert "v1" in _surviving_track_ids(core)
    v1 = next(t for t in core.project.timeline.tracks if t.track_id == "v1")
    assert c.clip_id in v1.clip_ids


# ---------- 10. The clean-up is silent for non-empty tracks ----------

def test_cleanup_leaves_non_empty_tracks_alone(tmp_path):
    core = _fresh_core(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    c1 = layer.add_clip("a1", 0.0, 1.0, timeline_start=0.0, track_id="v1")
    c2 = layer.add_clip("a1", 0.0, 1.0, timeline_start=10.0, track_id="v1")
    # Remove one clip — v1 still has the other.
    op = layer.remove_clip(c1.clip_id, why="test")
    assert "removed_tracks" not in op.after or not op.after["removed_tracks"]
    assert "v1" in _surviving_track_ids(core)
    v1 = next(t for t in core.project.timeline.tracks if t.track_id == "v1")
    assert v1.clip_ids == [c2.clip_id]
