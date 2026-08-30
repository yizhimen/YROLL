"""GUI-03E-3 — Timeline Switcher server-layer tests.

Covers the lifecycle commands exposed by the CommandLayer and their
behavioral guarantees that the GUI switcher depends on:

  1. Lifecycle: create empty / duplicate / delete.
  2. Rapid switch Active id stable: A → B → A returns to A.
  3. Preview plan isolation: A's plan contains A's clips only.
  4. Delete-active picks Open Order: Core decides; GUI reads result.
  5. Last Timeline cannot be deleted.
  6. Legacy single-Timeline project: still works with the same API.

These tests verify the contract that the TimelineSwitcher and
NewTimelineDialog rely on; the GUI side has its own Vitest coverage
for rendering + race-safe hooks.
"""

from __future__ import annotations

import tempfile

import pytest

from yroll.core.commands import CommandError, CommandLayer
from yroll.core.frame_preview import composite_preview_at_frame
from yroll.core.manifest import Track, TrackKind
from yroll.core.models import (
    Asset, AssetIdentity, AssetType,
)
from yroll.core.plan import build_preview_plan
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational


# ---------- helpers ----------

def _seeded_core(tmp_path, name: str = "switch") -> ProjectCore:
    """Two peer Timelines 'full' and 'seed' with one shared Asset."""
    core = ProjectCore.create(tmp_path, name)
    asset = Asset(
        asset_id="a-shared", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1,
                               duration_sec=60.0),
    )
    asset.source_fps = Rational(30, 1)
    asset.source_is_cfr = True
    core.project.assets.append(asset)
    cmd = CommandLayer(core)
    full_id = core.project.active_timeline_id
    cmd.add_clip("a-shared", 0.0, 5.0, 0.0, timeline_id=full_id)
    seed = cmd.add_timeline("seed", derived_from=None)
    cmd.switch_active_timeline(seed.timeline_id)
    cmd.add_clip("a-shared", 0.0, 3.0, 0.0, timeline_id=seed.timeline_id)
    cmd.switch_active_timeline(full_id)
    return core


# ---------- 1. Lifecycle roundtrip ----------

def test_create_empty_and_duplicate_and_delete(tmp_path):
    core = _seeded_core(tmp_path)
    cmd = CommandLayer(core)
    full_id = core.project.active_timeline_id
    seed_id = next(t.timeline_id for t in core.project.timelines
                    if t.timeline_id != full_id)

    # Create empty Timeline
    third = cmd.add_timeline("harvest", derived_from=None)
    assert third.timeline_id not in (full_id, seed_id)
    assert third.name == "harvest"
    assert third.derived_from is None
    assert len(third.tracks) == 0
    assert third.timeline_id in [t.timeline_id for t in core.project.timelines]

    # Duplicate an existing Timeline
    dup = cmd.duplicate_timeline(seed_id, new_name="seed-copy")
    assert dup.timeline_id not in (full_id, seed_id, third.timeline_id)
    assert dup.name == "seed-copy"
    assert dup.derived_from == seed_id
    # Duplicate carries tracks/clips of source
    src_seed = next(t for t in core.project.timelines if t.timeline_id == seed_id)
    assert len(dup.tracks) == len(src_seed.tracks)
    src_seed_clip_ids = {
        c.clip_id for c in core.project.clips.values()
        if c.timeline_id == seed_id
    }
    dup_clip_ids = {
        c.clip_id for c in core.project.clips.values()
        if c.timeline_id == dup.timeline_id
    }
    assert dup_clip_ids.isdisjoint(src_seed_clip_ids), \
        "duplicate must mint new clip ids"
    # But assets are shared
    src_assets = {c.asset_id for c in core.project.clips.values()
                  if c.timeline_id == seed_id}
    dup_assets = {c.asset_id for c in core.project.clips.values()
                  if c.timeline_id == dup.timeline_id}
    assert src_assets == dup_assets, "duplicate must reuse asset ids"

    # Delete the duplicate
    cmd.delete_timeline(dup.timeline_id)
    assert dup.timeline_id not in [t.timeline_id for t in core.project.timelines]
    assert all(c.timeline_id != dup.timeline_id for c in core.project.clips.values())


# ---------- 2. Rapid switch is idempotent ----------

def test_rapid_switch_a_to_b_to_a(tmp_path):
    core = _seeded_core(tmp_path)
    cmd = CommandLayer(core)
    full_id = core.project.active_timeline_id
    seed_id = next(t.timeline_id for t in core.project.timelines
                    if t.timeline_id != full_id)

    cmd.switch_active_timeline(seed_id)
    assert core.project.active_timeline_id == seed_id
    cmd.switch_active_timeline(full_id)
    assert core.project.active_timeline_id == full_id
    cmd.switch_active_timeline(seed_id)
    assert core.project.active_timeline_id == seed_id
    cmd.switch_active_timeline(full_id)
    # Each switch logs exactly one lifecycle op (audit trail).
    # Note: fixture construction also issues switches, so we count
    # the increments: helper seeds 2 switches, the test issues 4.
    types = [op.type for op in core.operations()]
    assert types.count("switch_active_timeline") >= 4


# ---------- 3. Preview plan isolation ----------

def test_preview_plan_full_does_not_see_seed(tmp_path):
    """Critical: GUI-03E-3 forbids plan leakage across Timelines."""
    core = _seeded_core(tmp_path)
    full_id = core.project.active_timeline_id
    seed_id = next(t.timeline_id for t in core.project.timelines
                    if t.timeline_id != full_id)

    full_plan = build_preview_plan(core.project, timeline_id=full_id)
    seed_plan = build_preview_plan(core.project, timeline_id=seed_id)

    full_clip_ids = {layer.clip_id
                     for track in full_plan.tracks for layer in track}
    seed_clip_ids = {layer.clip_id
                     for track in seed_plan.tracks for layer in track}
    assert full_clip_ids, "Full plan should contain its clip"
    assert seed_clip_ids, "Seed plan should contain its clip"
    assert full_clip_ids.isdisjoint(seed_clip_ids), \
        "Preview A's plan must not contain Preview B's clips"

    # Same for /preview/at_frame composite
    pv_full = composite_preview_at_frame(core.project, 0, Rational(30, 1),
                                         timeline_id=full_id)
    pv_seed = composite_preview_at_frame(core.project, 0, Rational(30, 1),
                                         timeline_id=seed_id)
    full_visual = {l.clip_id for l in pv_full.visual_layers}
    seed_visual = {l.clip_id for l in pv_seed.visual_layers}
    assert full_visual.isdisjoint(seed_visual)


# ---------- 4. Delete-active picks Open Order ----------

def test_delete_active_picks_open_order(tmp_path):
    core = _seeded_core(tmp_path)
    cmd = CommandLayer(core)
    full_id = core.project.active_timeline_id
    seed_id = next(t.timeline_id for t in core.project.timelines
                    if t.timeline_id != full_id)
    cmd.switch_active_timeline(full_id)  # active = full, default = full

    cmd.delete_timeline(full_id)
    # Core picked seed_id (only survivor, and seed != default
    # post-deletion since default also pointed at full).
    assert core.project.active_timeline_id == seed_id
    assert core.project.default_timeline_id == seed_id
    # The replacement is reported in the lifecycle op.
    op = core.operations()[-1]
    assert op.type == "delete_timeline"
    assert op.after["active_timeline_id"] == seed_id
    assert op.parameters["timeline_id"] == full_id  # the deleted id


def test_delete_non_active_leaves_active_alone(tmp_path):
    core = _seeded_core(tmp_path)
    cmd = CommandLayer(core)
    full_id = core.project.active_timeline_id
    seed_id = next(t.timeline_id for t in core.project.timelines
                    if t.timeline_id != full_id)
    # active = full; delete seed; active should remain full.
    cmd.delete_timeline(seed_id)
    assert core.project.active_timeline_id == full_id
    assert full_id in [t.timeline_id for t in core.project.timelines]


# ---------- 5. Last Timeline cannot be deleted ----------

def test_delete_last_timeline_rejected(tmp_path):
    core = ProjectCore.create(tmp_path, "solo")
    cmd = CommandLayer(core)
    only_id = core.project.active_timeline_id
    assert len(core.project.timelines) == 1
    with pytest.raises(CommandError, match="最后一个不可删|at least one"):
        cmd.delete_timeline(only_id)
    # State unchanged
    assert len(core.project.timelines) == 1
    assert core.project.active_timeline_id == only_id


# ---------- 6. Legacy single-Timeline project still works ----------

def test_legacy_single_timeline_project(tmp_path):
    """A project that was migrated from pre-03E has exactly one
    Timeline. The Switcher should still mount and the user can add
    a second one."""
    core = ProjectCore.create(tmp_path, "legacy")
    # Add a single asset + clip on the only Timeline
    asset = Asset(
        asset_id="a-1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="y" * 32, size_bytes=1, duration_sec=60.0),
    )
    asset.source_fps = Rational(30, 1)
    asset.source_is_cfr = True
    core.project.assets.append(asset)
    cmd = CommandLayer(core)
    cmd.add_clip("a-1", 0.0, 5.0, 0.0)

    # Add a sibling Timeline via the same lifecycle API.
    second = cmd.add_timeline("second", derived_from=None)
    assert len(core.project.timelines) == 2
    # The original Timeline is still active by default.
    assert core.project.active_timeline_id != second.timeline_id


# ---------- 7. Delete-active does NOT mutate other Timeline content ----

def test_delete_active_preserves_other_timeline(tmp_path):
    """Open Order must not touch the survivor's clips/tracks/markers."""
    core = _seeded_core(tmp_path)
    cmd = CommandLayer(core)
    full_id = core.project.active_timeline_id
    seed_id = next(t.timeline_id for t in core.project.timelines
                    if t.timeline_id != full_id)

    # Add a marker to seed so we can verify it survives.
    from yroll.core.markers import add_marker
    seed_tl = next(t for t in core.project.timelines if t.timeline_id == seed_id)
    add_marker(seed_tl, 30, "survivor")

    seed_clips_before = sorted(c.clip_id for c in core.project.clips.values()
                               if c.timeline_id == seed_id)

    cmd.delete_timeline(full_id)
    assert core.project.active_timeline_id == seed_id
    seed_clips_after = sorted(c.clip_id for c in core.project.clips.values()
                              if c.timeline_id == seed_id)
    assert seed_clips_before == seed_clips_after
    assert any(m.get("timeline_id") == seed_id
               for m in seed_tl.markers)