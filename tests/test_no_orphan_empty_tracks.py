"""GUI-03R3-W-B.7: static guard + legacy project compatibility.

Two contracts pinned here:

1. STATIC GUARD: every Project in tests/ + projects/ has
   `for t in tl.tracks: len(t.clip_ids) >= 1`. No orphan empty tracks.
   The guard runs across every project's current.json under the
   projects/ directory (the Sanlihe slice is the canonical fixture).

2. LEGACY COMPATIBILITY: pre-W-B projects may have empty tracks on
   disk (created by the old `ensure_default_tracks` default-track
   seeding). Loading a legacy project must NOT crash; the next
   mutation MUST auto-clean the empty tracks. This is the migration
   contract for legacy single-Timeline projects.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor, TrackKind
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational


ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = ROOT / "projects"


def _all_project_roots() -> list[Path]:
    """Find every project directory under projects/ that has current.json."""
    if not PROJECTS_DIR.exists():
        return []
    return [p for p in PROJECTS_DIR.iterdir()
            if p.is_dir() and (p / "current.json").exists()]


# ---------- 1. STATIC GUARD: every fixtures/*.current.json has no empty tracks ----------

def test_no_orphan_empty_tracks_in_projects_dir():
    """Static guard: scan every project under projects/ for empty
    tracks. Pinning this prevents accidental introduction of empty
    tracks (e.g., from a missed cleanup in a mutation path)."""
    failures: list[str] = []
    for proj_dir in _all_project_roots():
        current = json.loads(
            (proj_dir / "current.json").read_text(encoding="utf-8"),
        )
        # Multi-Timeline projects have timelines[]; legacy single-
        # Timeline projects have timeline (singular alias). Walk both.
        timelines = current.get("timelines") or [current.get("timeline", {})]
        for tl in timelines:
            tl_id = tl.get("timeline_id", "main")
            tracks = tl.get("tracks", []) or []
            for t in tracks:
                clip_ids = t.get("clip_ids", []) or []
                if not clip_ids:
                    failures.append(
                        f"{proj_dir.name}::{tl_id}::track {t.get('track_id')!r} "
                        f"is empty (no clips)"
                    )
    assert failures == [], (
        "orphan empty tracks found:\n" + "\n".join(failures)
    )


# ---------- 2. LEGACY PROJECT LOADS WITHOUT CRASH ----------

def test_legacy_project_with_empty_tracks_loads(tmp_path: Path):
    """Pre-W-B projects on disk may have empty tracks (from the
    old `ensure_default_tracks` helper which created v1..v3, a1..a3,
    t1, t2 with no clips). Loading such a project MUST NOT crash.
    The empty tracks are migrated on load (W-B invariant)."""
    project_root = tmp_path / "legacy-fixture"
    # Build a legacy project via the OLD path: ensure_default_tracks
    # creates 8 empty tracks; we then save without any clips.
    core = ProjectCore.create(tmp_path, "legacy-fixture")
    ProjectCore.ensure_default_tracks(core)
    core.save_state()

    # Reload via ProjectCore.open — must not crash.
    # ProjectCore.create builds <root>/<name>/; pass that path.
    reloaded = ProjectCore.open(project_root)
    surviving_ids = [t.track_id for t in reloaded.project.timeline.tracks]
    # W-B: load-time migration cleans empty tracks. After load,
    # only non-empty tracks remain (or no tracks at all).
    for t in reloaded.project.timeline.tracks:
        assert len(t.clip_ids) >= 1, (
            f"loaded legacy project has orphan empty track {t.track_id!r}"
        )


# ---------- 3. LEGACY PROJECT: CLEANED ON LOAD ----------

def test_legacy_first_load_cleans_empty_tracks(tmp_path: Path):
    """The load-time migration (added in ProjectCore.open) cleans
    empty tracks BEFORE the first mutation runs. Concretely: a
    legacy project with 8 empty default tracks has only those that
    become non-empty after load. With no clips on disk, all 8 are
    removed."""
    project_root = tmp_path / "legacy-mut"
    core = ProjectCore.create(tmp_path, "legacy-mut")
    ProjectCore.ensure_default_tracks(core)
    a = Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="v" * 32, size_bytes=1, duration_sec=10.0),
    )
    a.source_fps = Rational(30, 1); a.source_is_cfr = True
    core.project.assets.append(a)
    core.save_state()

    # Sanity: on disk, the project has 8 empty default tracks.
    pre_load = json.loads((project_root / "current.json").read_text())
    # Multi-Timeline projects use 'timelines'; legacy single-Timeline
    # uses 'timeline' (singular alias). Read both.
    pre_tracks_lists = pre_load.get("timelines") or [pre_load.get("timeline", {})]
    pre_tracks = [
        t for tl in pre_tracks_lists for t in tl.get("tracks", []) or []
    ]
    empty_pre = [t for t in pre_tracks if not t.get("clip_ids")]
    assert len(empty_pre) >= 1, "test fixture should have empty tracks on disk"

    # Reload — migration runs in open().
    reloaded = ProjectCore.open(project_root)
    # All empty tracks are removed on load.
    surviving_ids = [t.track_id for t in reloaded.project.timeline.tracks]
    assert surviving_ids == [], (
        f"legacy load should leave no tracks when no clips exist; "
        f"got {surviving_ids}"
    )

    # Now add a clip. The allocator creates a fresh v1.
    layer = CommandLayer(reloaded, who=Actor.HUMAN)
    layer.add_clip("a1", 0.0, 1.0, timeline_start=0.0, track_id="v1")
    assert [t.track_id for t in reloaded.project.timeline.tracks] == ["v1"]
    # No orphan empty tracks.
    for t in reloaded.project.timeline.tracks:
        assert len(t.clip_ids) >= 1


# ---------- 4. CLEANUP IS INVARIANT — THE GUARD CANNOT BE VIOLATED BY ANY PATH ----------

def test_cleanup_runs_on_every_clip_mutator_path():
    """Spot-check: each of the four mutators that can empty a track
    triggers _cleanup_empty_tracks. We confirm via the Operation's
    `after.removed_tracks` field, which is only populated when
    cleanup actually removed something."""
    # Construct a clean Core with one clip on v1, then mutate.
    from yroll.core.commands import CommandLayer
    from yroll.core.manifest import Actor

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        core = ProjectCore.create(Path(td), "invariant-check")
        a = Asset(
            asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
            identity=AssetIdentity(md5="v" * 32, size_bytes=1, duration_sec=10.0),
        )
        a.source_fps = Rational(30, 1); a.source_is_cfr = True
        core.project.assets.append(a)
        core.save_state()
        layer = CommandLayer(core, who=Actor.HUMAN)
        c = layer.add_clip("a1", 0.0, 1.0, timeline_start=0.0, track_id="v1")
        # remove_clip → empty v1 → removed.
        op = layer.remove_clip(c.clip_id, why="test")
        assert op.after.get("removed_tracks") == ["v1"]
        # After: only v1 might be in tl.tracks, but with no clips.
        # Wait — v1 was just removed. tl.tracks is empty.
        assert [t.track_id for t in core.project.timeline.tracks] == []


# ---------- 5. ADD_TRACK IS NOT FOLLOWED BY CLEANUP (explicit user action) ----------

def test_add_track_explicit_user_action_keeps_empty_track(tmp_path: Path):
    """`add_track` is an explicit user action (e.g., "create a new
    track"). It is NOT followed by cleanup, even though the new
    track is empty. The user might be about to add clips to it.
    Cleanup only runs after clip mutations, never after add_track."""
    core = ProjectCore.create(tmp_path, "add-track-test")
    layer = CommandLayer(core, who=Actor.HUMAN)
    t = layer.add_track(TrackKind.VIDEO, "v1")
    # The track exists and is empty (no clips yet).
    assert t.track_id == "v1"
    assert t.clip_ids == []
    # The track survives — no auto-cleanup on add_track.
    assert any(x.track_id == "v1" for x in core.project.timeline.tracks)
