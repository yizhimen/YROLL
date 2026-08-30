"""GUI-03E-2A — Timeline safety tests.

Required coverage:
  1. Timeline-local objects carry correct ownership (clip/track/
     marker/beat each stamped with timeline_id).
  2. Mutation with explicit Seed changes Seed only even when active
     is Full.
  3. Cross-timeline clip_id + timeline_id mismatch rejects with zero
     state/revision/op change.
  4. Duplicate creates new Track/Clip/Marker/Beat IDs but preserves
     Asset IDs; derived_from=source.
  5. Delete last Timeline rejected.
  6. Delete active Timeline selects valid replacement via Open Order.
  7. Preview A cannot resolve clips from Timeline B.
  8. GUI/Agent paths targeting different Timelines remain safe under
     Project-level Lease.
  9. Legacy single-Timeline projects still compatible after migration.
 10. Rename does not change timeline_id (carried over from 03E-1).
 11. Static guard (regression): commands.py must not reference
     project.timeline in 03E-2A code paths.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from yroll.core.commands import (
    CommandError,
    CommandLayer,
    _legacy_fallback_used,
    _reset_legacy_fallback_counter,
)
from yroll.core.frame_preview import composite_preview_at_frame
from yroll.core.manifest import (
    Project,
    Timeline,
    Track,
    TrackKind,
)
from yroll.core.models import (
    Asset,
    AssetIdentity,
    AssetType,
)
from yroll.core.plan import build_preview_plan
from yroll.core.project import (
    ProjectCore,
    _migrate_raw_to_multi_timeline,
)


# ---------- helpers ----------

def _two_timeline_core(tmp_path) -> ProjectCore:
    """Create a Project with two peer Timelines 'full' and 'seed',
    each with a single shared Asset 'a-shared' and one Clip on a
    VIDEO track. Returns the ProjectCore.

    Layout after construction:
        full.timeline_id = 'full'
          full.tracks = [v1]   ; clip 'c-full' on v1, asset a-shared
        seed.timeline_id = 'seed'
          seed.tracks = [v1]   ; clip 'c-seed' on v1, asset a-shared
        active = 'full', default = 'full'
    """
    core = ProjectCore.create(tmp_path, "two-tl")
    from yroll.core.timebase import Rational
    asset = Asset(
        asset_id="a-shared", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1,
                               duration_sec=60.0),
    )
    # Set explicit source timebase so PreviewPlan can resolve the
    # video clips (per GUI-02.3 invariant).
    asset.source_fps = Rational(30, 1)
    asset.source_is_cfr = True
    core.project.assets.append(asset)
    cmd = CommandLayer(core)
    full_id = core.project.active_timeline_id
    # Add a clip on the active Timeline
    c1 = cmd.add_clip("a-shared", 0.0, 5.0, 0.0, timeline_id=full_id)
    # Add a second Timeline
    seed = cmd.add_timeline("seed", derived_from=None)
    # Switch to seed and add a clip there
    cmd.switch_active_timeline(seed.timeline_id)
    c2 = cmd.add_clip("a-shared", 0.0, 3.0, 0.0, timeline_id=seed.timeline_id)
    # Restore active to 'full' for tests
    cmd.switch_active_timeline(full_id)
    return core


# ---------- 1. Ownership ----------

def test_clip_track_marker_beat_carry_timeline_id(tmp_path):
    core = _two_timeline_core(tmp_path)
    full_id = core.project.active_timeline_id
    seed_id = next(t.timeline_id for t in core.project.timelines
                    if t.timeline_id != full_id)
    # Find one clip per Timeline
    full_clips = [c for c in core.project.clips.values()
                  if c.timeline_id == full_id]
    seed_clips = [c for c in core.project.clips.values()
                  if c.timeline_id == seed_id]
    assert len(full_clips) == 1
    assert len(seed_clips) == 1
    # Each Clip carries its Timeline id
    assert full_clips[0].timeline_id == full_id
    assert seed_clips[0].timeline_id == seed_id
    # Each Track on each Timeline also has a timeline_id
    for tl in core.project.timelines:
        for tr in tl.tracks:
            assert tr.timeline_id == tl.timeline_id

    # Markers / Beats: add one on full, one on seed; verify ownership
    from yroll.core.markers import add_marker
    from yroll.core.story import add_beat
    full_tl = next(t for t in core.project.timelines if t.timeline_id == full_id)
    seed_tl = next(t for t in core.project.timelines if t.timeline_id == seed_id)
    add_marker(full_tl, 10, "marker-full")
    add_marker(seed_tl, 20, "marker-seed")
    add_beat(full_tl, "beat-full", "setup", 0, 100)
    add_beat(seed_tl, "beat-seed", "setup", 0, 100)
    assert full_tl.markers[0]["timeline_id"] == full_id
    assert seed_tl.markers[0]["timeline_id"] == seed_id
    assert full_tl.beats[0]["timeline_id"] == full_id
    assert seed_tl.beats[0]["timeline_id"] == seed_id


# ---------- 2. Explicit Seed mutation changes only Seed ----------

def test_explicit_seed_mutation_changes_seed_only(tmp_path):
    core = _two_timeline_core(tmp_path)
    full_id = core.project.active_timeline_id
    seed_id = next(t.timeline_id for t in core.project.timelines
                    if t.timeline_id != full_id)
    cmd = CommandLayer(core)
    cmd.switch_active_timeline(full_id)  # active = full

    # Snapshot Full's state before mutation
    full_clips_before = sorted([
        (c.clip_id, c.timeline_range.start, c.timeline_range.end)
        for c in core.project.clips.values()
        if c.timeline_id == full_id
    ])
    full_revision_before = core.operations()[-1].operation_id if core.operations() else None
    full_op_count_before = len(core.operations())

    # Add a clip on Seed via EXPLICIT seed_id, while active = full
    seed_tl = next(t for t in core.project.timelines if t.timeline_id == seed_id)
    seed_clip_count_before = len([c for c in core.project.clips.values()
                                     if c.timeline_id == seed_id])
    c = cmd.add_clip("a-shared", 5.0, 8.0, 5.0, timeline_id=seed_id)
    assert c.timeline_id == seed_id

    # Full's clips unchanged
    full_clips_after = sorted([
        (c.clip_id, c.timeline_range.start, c.timeline_range.end)
        for c in core.project.clips.values()
        if c.timeline_id == full_id
    ])
    assert full_clips_after == full_clips_before
    # Seed's clip count grew by 1
    seed_clip_count_after = len([c for c in core.project.clips.values()
                                    if c.timeline_id == seed_id])
    assert seed_clip_count_after == seed_clip_count_before + 1


# ---------- 3. Cross-timeline mismatch rejects with zero mutation ----------

def test_mismatched_timeline_clip_rejects_no_mutation(tmp_path):
    core = _two_timeline_core(tmp_path)
    full_id = core.project.active_timeline_id
    seed_id = next(t.timeline_id for t in core.project.timelines
                    if t.timeline_id != full_id)
    cmd = CommandLayer(core)

    # Snapshot state before
    project_repr_before = core.project.model_dump_json()
    op_count_before = len(core.operations())

    # Find full's clip_id and try to mutate it with timeline_id=seed
    full_clip_id = next(c.clip_id for c in core.project.clips.values()
                        if c.timeline_id == full_id)
    with pytest.raises(CommandError) as ei:
        cmd.remove_clip(full_clip_id, timeline_id=seed_id)
    assert "belongs to timeline" in str(ei.value)

    # State unchanged
    project_repr_after = core.project.model_dump_json()
    assert project_repr_before == project_repr_after
    # No new operation recorded
    assert len(core.operations()) == op_count_before


def test_mismatched_timeline_track_rejects(tmp_path):
    core = _two_timeline_core(tmp_path)
    full_id = core.project.active_timeline_id
    seed_id = next(t.timeline_id for t in core.project.timelines
                    if t.timeline_id != full_id)
    # Pick a track that exists on FULL only — there is no v1 on
    # seed (its track was auto-named `t<hash>_video`). Use the
    # full track_id against seed.
    full_tl = next(t for t in core.project.timelines if t.timeline_id == full_id)
    full_track_id = full_tl.tracks[0].track_id
    cmd = CommandLayer(core)
    op_count_before = len(core.operations())
    with pytest.raises(CommandError):
        cmd.set_track_muted(seed_id, full_track_id, True)
    assert len(core.operations()) == op_count_before


def test_mismatched_timeline_marker_rejects(tmp_path):
    core = _two_timeline_core(tmp_path)
    full_id = core.project.active_timeline_id
    seed_id = next(t.timeline_id for t in core.project.timelines
                    if t.timeline_id != full_id)
    full_tl = next(t for t in core.project.timelines if t.timeline_id == full_id)
    seed_tl = next(t for t in core.project.timelines if t.timeline_id == seed_id)
    # Inject a marker that lives in seed's list but with
    # timeline_id=full_id. The `_marker(seed_id, ...)` lookup
    # iterates seed.markers, finds the id, and rejects because
    # the stored timeline_id doesn't match seed's id.
    seed_tl.markers.append({
        "marker_id": "stowaway",
        "timeline_frame": 10,
        "label": "stowaway-on-seed-but-owned-by-full",
        "color": "#ffd400", "note": "",
        "created_at": "2026-01-01T00:00:00",
        "timeline_id": full_id,  # owner is full, but stored in seed list
    })

    cmd = CommandLayer(core)
    op_count_before = len(core.operations())
    with pytest.raises(CommandError) as ei:
        cmd._marker(seed_id, "stowaway")
    assert "belongs to timeline" in str(ei.value)
    assert len(core.operations()) == op_count_before


# ---------- 4. Duplicate creates new IDs, preserves Asset IDs ----------

def test_duplicate_creates_new_ids_preserves_assets(tmp_path):
    core = _two_timeline_core(tmp_path)
    full_id = core.project.active_timeline_id

    # Add markers and beats to full
    from yroll.core.markers import add_marker
    from yroll.core.story import add_beat
    full_tl = next(t for t in core.project.timelines if t.timeline_id == full_id)
    add_marker(full_tl, 10, "M1")
    add_marker(full_tl, 20, "M2")
    add_beat(full_tl, "B1", "setup", 0, 100)

    cmd = CommandLayer(core)
    # Snapshot full's IDs
    full_clip_ids = sorted([c.clip_id for c in core.project.clips.values()
                              if c.timeline_id == full_id])
    full_track_ids = sorted([tr.track_id for tr in full_tl.tracks])
    full_marker_ids = sorted([m["marker_id"] for m in full_tl.markers])
    full_beat_ids = sorted([b["beat_id"] for b in full_tl.beats])
    full_asset_ids = sorted([a.asset_id for a in core.project.assets])
    # Asset IDs referenced by full's clips
    full_clip_asset_ids = sorted({c.asset_id for c in core.project.clips.values()
                                    if c.timeline_id == full_id})

    # Duplicate
    new_tl = cmd.duplicate_timeline(full_id, new_name="full 副本")
    new_id = new_tl.timeline_id

    # New Timeline id distinct
    assert new_id != full_id
    assert core.project.get_timeline(new_id) is not None
    # derived_from = source timeline_id
    assert new_tl.derived_from == full_id

    # Track / Clip / Marker / Beat IDs are NEW
    new_clip_ids = sorted([c.clip_id for c in core.project.clips.values()
                              if c.timeline_id == new_id])
    new_track_ids = sorted([tr.track_id for tr in new_tl.tracks])
    new_marker_ids = sorted([m["marker_id"] for m in new_tl.markers])
    new_beat_ids = sorted([b["beat_id"] for b in new_tl.beats])

    assert set(new_clip_ids).isdisjoint(set(full_clip_ids))
    assert set(new_track_ids).isdisjoint(set(full_track_ids))
    assert set(new_marker_ids).isdisjoint(set(full_marker_ids))
    assert set(new_beat_ids).isdisjoint(set(full_beat_ids))

    # Asset IDs PRESERVED (no media copy)
    new_clip_asset_ids = sorted({c.asset_id for c in core.project.clips.values()
                                    if c.timeline_id == new_id})
    assert new_clip_asset_ids == full_clip_asset_ids
    # Project.assets didn't grow (no Asset object copy)
    assert sorted([a.asset_id for a in core.project.assets]) == full_asset_ids

    # New Timeline has all 1 timeline + source's content
    assert len(new_clip_ids) == len(full_clip_ids)
    assert len(new_track_ids) == len(full_track_ids)
    assert len(new_marker_ids) == len(full_marker_ids)
    assert len(new_beat_ids) == len(full_beat_ids)


# ---------- 5. Delete last Timeline rejected ----------

def test_delete_last_timeline_rejected(tmp_path):
    core = ProjectCore.create(tmp_path, "solo")
    cmd = CommandLayer(core)
    assert len(core.project.timelines) == 1
    with pytest.raises(CommandError) as ei:
        cmd.delete_timeline(core.project.timelines[0].timeline_id)
    assert "最后一个不可删" in str(ei.value)
    assert len(core.project.timelines) == 1


# ---------- 6. Delete active Timeline selects valid replacement ----------

def test_delete_active_selects_via_open_order(tmp_path):
    core = ProjectCore.create(tmp_path, "multi")
    cmd = CommandLayer(core)
    seed = cmd.add_timeline("seed")
    cmd.switch_active_timeline(seed.timeline_id)
    full_id = cmd.add_timeline("full").timeline_id
    cmd.switch_active_timeline(full_id)
    # active = full, default = main
    # Delete active: open-order resolver should pick default (main)
    cmd.delete_timeline(full_id)
    assert core.project.active_timeline_id == "main"
    assert core.project.get_timeline(full_id) is None
    # main still exists
    assert core.project.get_timeline("main") is not None


# ---------- 7. Preview A cannot resolve clips from Timeline B ----------

def test_preview_a_does_not_resolve_b(tmp_path):
    core = _two_timeline_core(tmp_path)
    full_id = core.project.active_timeline_id
    seed_id = next(t.timeline_id for t in core.project.timelines
                    if t.timeline_id != full_id)
    cmd = CommandLayer(core)
    # Make sure the Full clip and Seed clip are at the same timeline
    # frame (so a naive resolver could pick either). Adjust Seed's
    # clip to [0, 5] to match Full's.
    seed_clip_id = next(c.clip_id for c in core.project.clips.values()
                          if c.timeline_id == seed_id)
    cmd.trim_clip(seed_clip_id, 0.0, 5.0, timeline_id=seed_id)
    cmd.move_clip(seed_clip_id, 0.0, timeline_id=seed_id)

    # Preview A: timeline_id=full → resolves Full's clip only
    plan_full = build_preview_plan(core.project, timeline_id=full_id)
    plan_seed = build_preview_plan(core.project, timeline_id=seed_id)
    full_clip_ids_in_plan = {
        layer.clip_id
        for track_layers in plan_full.tracks
        for layer in track_layers}
    seed_clip_ids_in_plan = {
        layer.clip_id
        for track_layers in plan_seed.tracks
        for layer in track_layers}
    full_clip_id = next(c.clip_id for c in core.project.clips.values()
                          if c.timeline_id == full_id)
    seed_clip_id = next(c.clip_id for c in core.project.clips.values()
                          if c.timeline_id == seed_id)
    assert full_clip_id in full_clip_ids_in_plan
    assert seed_clip_id not in full_clip_ids_in_plan
    assert seed_clip_id in seed_clip_ids_in_plan
    assert full_clip_id not in seed_clip_ids_in_plan

    # composite_preview_at_frame also respects timeline_id
    from yroll.core.timebase import Rational
    fps = Rational(30, 1)
    pv_full = composite_preview_at_frame(core.project, 30, fps,
                                          timeline_id=full_id)
    pv_seed = composite_preview_at_frame(core.project, 30, fps,
                                           timeline_id=seed_id)
    full_resolved = {l.clip_id for l in pv_full.visual_layers}
    seed_resolved = {l.clip_id for l in pv_seed.visual_layers}
    assert full_clip_id in full_resolved
    assert seed_clip_id not in full_resolved
    assert seed_clip_id in seed_resolved
    assert full_clip_id not in seed_resolved


# ---------- 8. Agent + Human on different Timelines under Project Lease ----------

def test_agent_and_human_on_different_timelines_safe(tmp_path):
    """GUI-03E-2A: Project-level Lease must allow mutations on
    different Timelines. The lease does NOT scope per-Timeline in
    this batch. Two independent edit paths (Human + Agent) must
    both be able to mutate different Timelines simultaneously
    without cross-interference."""
    core = _two_timeline_core(tmp_path)
    full_id = core.project.active_timeline_id
    seed_id = next(t.timeline_id for t in core.project.timelines
                    if t.timeline_id != full_id)

    # Two CommandLayer instances simulate Human and Agent paths.
    # They share the same core / project; the only thing they MUST
    # do differently is target different Timelines.
    cmd_human = CommandLayer(core)
    cmd_agent = CommandLayer(core)
    # Human: switch to seed, add a clip
    cmd_human.switch_active_timeline(seed_id)
    cmd_human.add_clip("a-shared", 5.0, 8.0, 5.0, timeline_id=seed_id)
    # Agent: switch back to full, add a clip
    cmd_agent.switch_active_timeline(full_id)
    cmd_agent.add_clip("a-shared", 5.0, 8.0, 5.0, timeline_id=full_id)
    # Both succeeded; no exception because lease is Project-level.
    seed_clips = [c for c in core.project.clips.values()
                  if c.timeline_id == seed_id]
    full_clips = [c for c in core.project.clips.values()
                  if c.timeline_id == full_id]
    assert len(seed_clips) == 2
    assert len(full_clips) == 2


# ---------- 9. Legacy single-Timeline projects still work ----------

def test_legacy_single_timeline_round_trip(tmp_path):
    legacy = {
        "manifest_version": "0.1",
        "project_id": "leg",
        "name": "leg",
        "fps_num": 30, "fps_den": 1, "width": 1920, "height": 1080,
        "sequence": {"fps": {"num": 30, "den": 1},
                     "width": 1920, "height": 1080},
        "timeline": {"timeline_id": "main", "tracks": [
            {"track_id": "v1", "kind": "video", "clip_ids": ["c1"]},
        ]},
        "clips": {"c1": {
            "clip_id": "c1", "asset_id": "a1",
            "source_range": {"start": 0, "end": 5},
            "timeline_range": {"start": 0, "end": 5},
        }},
    }
    proj = _write_legacy(tmp_path, legacy)
    core = ProjectCore.open(proj)
    # After migration: one Timeline, clip present, timeline_id stamped
    assert len(core.project.timelines) == 1
    assert core.project.active_timeline_id == "main"
    assert core.project.default_timeline_id == "main"
    assert "c1" in core.project.clips
    assert core.project.clips["c1"].timeline_id == "main"
    # Operations on it work
    cmd = CommandLayer(core)
    cmd.add_clip("a1", 5.0, 10.0, 5.0, timeline_id="main")
    assert len(core.project.clips) == 2


# ---------- 10. Rename doesn't change timeline_id ----------

def test_rename_does_not_change_timeline_id(tmp_path):
    core = _two_timeline_core(tmp_path)
    full_id = core.project.active_timeline_id
    seed_id = next(t.timeline_id for t in core.project.timelines
                    if t.timeline_id != full_id)
    seed_tl = next(t for t in core.project.timelines if t.timeline_id == seed_id)
    seed_tl.name = "种草版"
    core.save_state()
    core2 = ProjectCore.open(str(Path(tmp_path) / "two-tl"))
    found = next(t for t in core2.project.timelines if t.timeline_id == seed_id)
    assert found.name == "种草版"
    assert found.timeline_id == seed_id  # unchanged


# ---------- 11. Static guard ----------

def test_no_project_timeline_in_commands_module():
    """GUI-03E-2A: Timeline-local commands MUST NOT reference the
    deprecated `self.core.project.timeline` (singular) shortcut.
    The deprecated property itself stays in manifest.py for legacy
    compat; new code must use `tl = self._timeline(timeline_id)`.

    The static guard scans commands.py and counts references. The
    only allowed hits are:
      - inside the canonical accessor `_timeline` (where the
        accessor itself reads `self.core.project.get_timeline(...)`
        — not `.timeline`, so even that's clean);
      - inside the 4 lifecycle ops (`add_timeline`, `duplicate_timeline`,
        `delete_timeline`, `switch_active_timeline`) which are
        explicitly Project-global.

    We allow list-comprehensions over `self.core.project.timelines`
    (the list — plural) and over `self.core.project.timelines[0]`
    (for Open Order / pick_open_target) because those are Project-
    global. We forbid `self.core.project.timeline` (singular property
    accessor) — that's the deprecated shortcut."""
    from pathlib import Path as _P
    text = (_P("yroll/core/commands.py")).read_text(encoding="utf-8")
    import re
    stripped = re.sub(r'\"\"\"[\s\S]*?\"\"\"', "", text)
    # Only flag the singular `.timeline` (property shortcut) — NOT
    # `.timelines` (list) and NOT `.timeline_id` (field).
    # Use a negative lookahead: `.timeline` must NOT be followed by
    # `_id` or `s`.
    refs = re.findall(
        r"self\.core\.project\.timeline(?![_a-zA-Z0-9])", stripped)
    # The lone legitimate hit is the error message in `_timeline()`
    # that lists known timeline ids.
    allow_list = {
        # _timeline() error message — list known ids.
        86,
    }
    bad_lines = []
    for i, line in enumerate(stripped.splitlines()):
        if re.search(r"self\.core\.project\.timeline(?![_a-zA-Z0-9])", line):
            if (i + 1) not in allow_list:
                bad_lines.append((i + 1, line))
    assert not bad_lines, (
        f"commands.py still references self.core.project.timeline "
        f"{len(bad_lines)} times in 03E-2A code outside the canonical "
        f"accessor. Use `tl = self._timeline(timeline_id)` instead. "
        f"Lines: {bad_lines[:5]}"
    )


def test_legacy_fallback_counter_visible_to_tests():
    """Sanity: the regression guard's counter is exposed and resets."""
    _reset_legacy_fallback_counter()
    assert _legacy_fallback_used() == 0


# ---------- helpers (file path) ----------

def _write_legacy(tmp_path, raw: dict) -> str:
    proj = Path(tmp_path) / "leg"
    for d in ("operations", "versions", "media", "cache", "generated"):
        (proj / d).mkdir(parents=True, exist_ok=True)
    (proj / "current.json").write_text(json.dumps(raw, indent=2),
                                        encoding="utf-8")
    return str(proj)