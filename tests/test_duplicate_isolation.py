"""GUI-03E-4 — Duplicate / Many Cuts isolation tests.

Required coverage (per 03E-4 spec):
  1. duplicate produces new Timeline ID.
  2. new Track/Clip/Marker/Beat IDs (no id collision with source).
  3. same Asset IDs (shared, not duplicated).
  4. no media copies (Project.assets list is byte-equivalent
     before/after — asset entries themselves are untouched).
  5. correct derived_from = source_timeline_id.
  6. duplicate becomes the active Timeline (server-authoritative).
  7. edit duplicate leaves source byte/state-equivalent
     (track_ids, clip_ids, marker_ids, beat_ids of source untouched;
     source clips' timeline_id / source_range / timeline_range /
     asset_id unchanged).
  8. delete duplicate preserves shared Assets (Project.assets still
     contains every asset the duplicate referenced).
  9. legacy single-Timeline project can duplicate its Timeline.
 10. Sanlihe-style: Full → Seed → mutate Seed → Full unchanged.
"""

from __future__ import annotations

import copy
import tempfile

import pytest

from yroll.core.commands import CommandError, CommandLayer
from yroll.core.manifest import TrackKind
from yroll.core.markers import add_marker
from yroll.core.models import (
    Asset, AssetIdentity, AssetType,
)
from yroll.core.project import ProjectCore
from yroll.core.story import add_beat
from yroll.core.timebase import Rational


# ---------- helpers ----------

def _build_two_clip_core(tmp_path, name: str = "dup") -> ProjectCore:
    """Full cut with 2 clips, 1 marker, 1 beat, on default tracks."""
    core = ProjectCore.create(tmp_path, name)
    asset = Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v1.mp4",
        identity=AssetIdentity(md5="a" * 32, size_bytes=1, duration_sec=60.0),
    )
    asset.source_fps = Rational(30, 1)
    asset.source_is_cfr = True
    core.project.assets.append(asset)
    asset2 = Asset(
        asset_id="a2", type=AssetType.VIDEO, path="v2.mp4",
        identity=AssetIdentity(md5="b" * 32, size_bytes=1, duration_sec=60.0),
    )
    asset2.source_fps = Rational(30, 1)
    asset2.source_is_cfr = True
    core.project.assets.append(asset2)
    cmd = CommandLayer(core)
    tl_id = core.project.active_timeline_id
    full_tl = next(t for t in core.project.timelines if t.timeline_id == tl_id)
    c1 = cmd.add_clip("a1", 0.0, 5.0, 0.0, timeline_id=tl_id)
    c2 = cmd.add_clip("a2", 5.0, 10.0, 5.0, timeline_id=tl_id)
    add_marker(full_tl, 12, "first-cut")
    add_beat(full_tl, "intro", "setup", 0, 60)
    return core


def _state_snapshot(core: ProjectCore) -> dict:
    """Return a content-addressable snapshot of the Project's
    Timeline-local state. We compare snapshots across an edit on a
    different Timeline to verify the source is untouched.

    Includes: tracks, clips, markers, beats per Timeline, and the
    shared Project.assets list (key + md5 + size). It does NOT
    include active_timeline_id (that pointer is allowed to move)."""
    snap = {
        "timelines": {},
        "clips": {},
        "assets": [
            {"asset_id": a.asset_id, "md5": a.identity.md5,
             "size": a.identity.size_bytes, "path": a.path}
            for a in core.project.assets
        ],
    }
    for tl in core.project.timelines:
        snap["timelines"][tl.timeline_id] = {
            "name": tl.name,
            "derived_from": tl.derived_from,
            "track_ids": [t.track_id for t in tl.tracks],
            "marker_ids": [m.get("marker_id") for m in (tl.markers or [])],
            "beat_ids": [b.get("beat_id") for b in (tl.beats or [])],
        }
    for cid, clip in core.project.clips.items():
        snap["clips"][cid] = {
            "asset_id": clip.asset_id,
            "track_id": clip.track_id,
            "timeline_id": clip.timeline_id,
            "source_range": (clip.source_range.start, clip.source_range.end),
            "timeline_range": (clip.timeline_range.start,
                               clip.timeline_range.end),
        }
    return snap


# ---------- 1-4: duplicate creates new IDs, preserves assets ----

def test_duplicate_produces_new_ids(tmp_path):
    core = _build_two_clip_core(tmp_path)
    full_id = core.project.active_timeline_id
    cmd = CommandLayer(core)

    full_snap = _state_snapshot(core)
    dup = cmd.duplicate_timeline(full_id, new_name="种草版")
    dup_snap = _state_snapshot(core)

    # 1. new Timeline ID
    assert dup.timeline_id != full_id
    assert dup.timeline_id in [t.timeline_id for t in core.project.timelines]

    # 2. new Track/Clip/Marker/Beat IDs (no overlap with source)
    full_tl = next(t for t in core.project.timelines
                   if t.timeline_id == full_id)
    full_track_ids = {t.track_id for t in full_tl.tracks}
    full_clip_ids = {c.clip_id for c in core.project.clips.values()
                     if c.timeline_id == full_id}
    full_marker_ids = {m.get("marker_id") for m in full_tl.markers}
    full_beat_ids = {b.get("beat_id") for b in full_tl.beats}

    dup_track_ids = {t.track_id for t in dup.tracks}
    dup_clip_ids = {c.clip_id for c in core.project.clips.values()
                    if c.timeline_id == dup.timeline_id}
    dup_marker_ids = {m.get("marker_id") for m in dup.markers}
    dup_beat_ids = {b.get("beat_id") for b in dup.beats}

    assert dup_track_ids.isdisjoint(full_track_ids)
    assert dup_clip_ids.isdisjoint(full_clip_ids)
    assert dup_marker_ids.isdisjoint(full_marker_ids)
    assert dup_beat_ids.isdisjoint(full_beat_ids)


def test_duplicate_preserves_asset_ids(tmp_path):
    core = _build_two_clip_core(tmp_path)
    full_id = core.project.active_timeline_id
    cmd = CommandLayer(core)

    dup = cmd.duplicate_timeline(full_id)
    src_assets = sorted(c.asset_id for c in core.project.clips.values()
                        if c.timeline_id == full_id)
    dup_assets = sorted(c.asset_id for c in core.project.clips.values()
                        if c.timeline_id == dup.timeline_id)
    assert src_assets == dup_assets
    # 4. no media copies
    before_assets = {a.asset_id: a.identity.md5 for a in core.project.assets}
    cmd.duplicate_timeline(full_id)  # do it again — assets still intact
    after_assets = {a.asset_id: a.identity.md5 for a in core.project.assets}
    assert before_assets == after_assets


def test_duplicate_derived_from_is_source_timeline_id(tmp_path):
    core = _build_two_clip_core(tmp_path)
    full_id = core.project.active_timeline_id
    cmd = CommandLayer(core)
    dup = cmd.duplicate_timeline(full_id, new_name="harvest")
    assert dup.derived_from == full_id
    assert dup.name == "harvest"


# ---------- 5-6: active becomes the duplicate ----

def test_duplicate_becomes_active(tmp_path):
    core = _build_two_clip_core(tmp_path)
    full_id = core.project.active_timeline_id
    cmd = CommandLayer(core)
    dup = cmd.duplicate_timeline(full_id)
    assert core.project.active_timeline_id == dup.timeline_id


# ---------- 7: edit duplicate leaves source byte-equivalent ----

def test_edit_duplicate_leaves_source_byte_equivalent(tmp_path):
    core = _build_two_clip_core(tmp_path)
    full_id = core.project.active_timeline_id
    cmd = CommandLayer(core)
    dup = cmd.duplicate_timeline(full_id)

    full_snap_before = _state_snapshot(core)

    # Now mutate the duplicate heavily: remove a clip, add a new one,
    # tweak another, add a marker. None of this may touch the source
    # Timeline's clip_ids/track_ids/marker_ids/beat_ids.
    dup_tl = next(t for t in core.project.timelines
                  if t.timeline_id == dup.timeline_id)
    dup_clips = [c for c in core.project.clips.values()
                 if c.timeline_id == dup.timeline_id]
    # Remove one clip from duplicate
    cmd.remove_clip(dup_clips[0].clip_id, timeline_id=dup.timeline_id)
    # Move another within duplicate's track
    cmd.move_clip_frame(
        dup_clips[1].clip_id, new_timeline_start_frame=20,
        timeline_id=dup.timeline_id)
    # Add a marker to duplicate
    add_marker(dup_tl, 30, "new-version")

    full_snap_after = _state_snapshot(core)
    # Source Timeline section must be byte-equivalent
    assert full_snap_before["timelines"][full_id] == \
        full_snap_after["timelines"][full_id]
    src_clip_ids = {cid for cid, info in full_snap_before["clips"].items()
                    if info["timeline_id"] == full_id}
    for cid in src_clip_ids:
        assert full_snap_before["clips"][cid] == \
            full_snap_after["clips"][cid], \
            f"source clip {cid} mutated by duplicate edit"


# ---------- 8: delete duplicate preserves shared Assets ----

def test_delete_duplicate_preserves_shared_assets(tmp_path):
    core = _build_two_clip_core(tmp_path)
    full_id = core.project.active_timeline_id
    cmd = CommandLayer(core)
    dup = cmd.duplicate_timeline(full_id)

    asset_ids_before = sorted(a.asset_id for a in core.project.assets)
    cmd.delete_timeline(dup.timeline_id)
    asset_ids_after = sorted(a.asset_id for a in core.project.assets)
    assert asset_ids_before == asset_ids_after, \
        "deleting the duplicate must not touch Project.assets"
    # Source is intact
    assert full_id in [t.timeline_id for t in core.project.timelines]


# ---------- 9: legacy single-Timeline project can duplicate ----

def test_legacy_single_timeline_can_duplicate(tmp_path):
    """A fresh ProjectCore with one Timeline must still be able to
    produce a duplicate."""
    core = ProjectCore.create(tmp_path, "solo")
    asset = Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v1.mp4",
        identity=AssetIdentity(md5="c" * 32, size_bytes=1, duration_sec=60.0),
    )
    asset.source_fps = Rational(30, 1)
    asset.source_is_cfr = True
    core.project.assets.append(asset)
    cmd = CommandLayer(core)
    cmd.add_clip("a1", 0.0, 5.0, 0.0)

    only_id = core.project.active_timeline_id
    dup = cmd.duplicate_timeline(only_id, new_name="alternate")
    assert dup.timeline_id != only_id
    assert dup.derived_from == only_id
    assert core.project.active_timeline_id == dup.timeline_id
    # Original Timeline untouched
    src_tl = next(t for t in core.project.timelines
                  if t.timeline_id == only_id)
    assert len(src_tl.tracks) >= 1
    assert any(c.timeline_id == only_id
               for c in core.project.clips.values())


# ---------- 10: Sanlihe-style: Full → Seed → mutate → Full unchanged ----

def test_sanlihe_style_full_seed_full_unchanged(tmp_path):
    """Completion criterion smoke test:
    take the current full cut, duplicate to a new version, mutate
    the new version freely, return to the source; source state
    must be byte-equivalent."""
    core = _build_two_clip_core(tmp_path, name="sanlihe-dup")
    full_id = core.project.active_timeline_id
    cmd = CommandLayer(core)
    full_snap = _state_snapshot(core)

    # Duplicate (becomes the new active Timeline)
    seed = cmd.duplicate_timeline(full_id, new_name="种草版")
    assert core.project.active_timeline_id == seed.timeline_id

    # Mutate Seed heavily
    seed_clips = [c for c in core.project.clips.values()
                  if c.timeline_id == seed.timeline_id]
    # Remove all Seed clips and add a fresh one
    for sc in seed_clips:
        cmd.remove_clip(sc.clip_id, timeline_id=seed.timeline_id)
    cmd.add_clip("a1", 0.0, 12.0, 0.0, timeline_id=seed.timeline_id)
    seed_tl = next(t for t in core.project.timelines
                   if t.timeline_id == seed.timeline_id)
    add_marker(seed_tl, 0, "seed-anchor")
    add_beat(seed_tl, "seed-only", "setup", 0, 30)

    # Switch back to Full
    cmd.switch_active_timeline(full_id)
    assert core.project.active_timeline_id == full_id

    # Source state must be byte-equivalent to pre-duplicate snapshot
    full_snap_after = _state_snapshot(core)
    assert full_snap["timelines"][full_id] == \
        full_snap_after["timelines"][full_id]
    src_clip_ids = {cid for cid, info in full_snap["clips"].items()
                    if info["timeline_id"] == full_id}
    for cid in src_clip_ids:
        assert full_snap["clips"][cid] == \
            full_snap_after["clips"][cid]

    # Shared assets unchanged
    assert full_snap["assets"] == full_snap_after["assets"]

    # Seed Timeline mutated independently (it's still around, but
    # with different content)
    seed_clips_after = [c for c in core.project.clips.values()
                        if c.timeline_id == seed.timeline_id]
    assert len(seed_clips_after) == 1  # the fresh one we added
    seed_clips_src_count = sum(1 for c in full_snap["clips"].values()
                               if c["timeline_id"] == full_id)
    assert len(seed_clips_after) != seed_clips_src_count