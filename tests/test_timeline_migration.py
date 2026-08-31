"""GUI-03E-1 — Timeline schema / migration tests.

Required test surface (per GUI-03E-1 spec):
  1. v1 single-timeline project loads as one Timeline
  2. migration is idempotent (open+save+open+save produces identical state)
  3. save/reload preserves timeline ID and all timeline state
  4. active/default IDs survive save/reload
  5. active timeline always exists
  6. default timeline always exists
  7. project cannot persist zero timelines
  8. timeline rename does not change timeline_id
  9. derived_from uses stable timeline_id
 10. Timeline-local state is isolated between two timelines
 11. Shared Asset remains one shared reference after multiple timelines exist
 12. Existing legacy fixtures remain green

These tests ONLY touch manifest + ProjectCore + migration loader.
They do NOT exercise GUI, command layer (timeline_id), or preview.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from yroll.core.manifest import (
    Clip,
    Project,
    TimeRange,
    Timeline,
    Track,
    TrackKind,
)
from yroll.core.models import (
    Asset,
    AssetIdentity,
    AssetType,
)
from yroll.core.project import (
    ProjectCore,
    _migrate_raw_to_multi_timeline,
)


# --- helpers --------------------------------------------------------

def _make_legacy_raw(
    *,
    project_id: str = "p1",
    name: str = "legacy",
    timeline_id: str = "main",
    tracks: list | None = None,
    clips: dict | None = None,
) -> dict:
    """A pre-03E single-timeline project.json shape."""
    return {
        "manifest_version": "0.1",
        "project_id": project_id,
        "name": name,
        "fps_num": 30, "fps_den": 1, "width": 1920, "height": 1080,
        "sequence": {
            "fps": {"num": 30, "den": 1},
            "width": 1920,
            "height": 1080,
        },
        "timeline": {
            "timeline_id": timeline_id,
            "tracks": tracks or [],
        },
        "clips": clips or {},
    }


def _make_post_03e_raw(
    *,
    project_id: str = "p1",
    name: str = "post",
    timelines: list | None = None,
    active: str = "main",
    default: str = "main",
) -> dict:
    return {
        "manifest_version": "0.1",
        "schema_version": "0.2",
        "project_id": project_id,
        "name": name,
        "fps_num": 30, "fps_den": 1, "width": 1920, "height": 1080,
        "sequence": {
            "fps": {"num": 30, "den": 1},
            "width": 1920,
            "height": 1080,
        },
        "timelines": timelines or [{"timeline_id": "main", "name": "main",
                                     "tracks": []}],
        "active_timeline_id": active,
        "default_timeline_id": default,
    }


def _write_project(raw: dict, root: str) -> str:
    """Write a project.json into a fresh project directory under root.
    Returns the project directory path."""
    proj = Path(root) / "p"
    for d in ("operations", "versions", "media", "cache", "generated"):
        (proj / d).mkdir(parents=True, exist_ok=True)
    (proj / "current.json").write_text(json.dumps(raw, indent=2),
                                        encoding="utf-8")
    return str(proj)


# --- 1. v1 single-timeline loads as one Timeline -------------------

def test_legacy_single_timeline_loads_as_one_timeline(tmp_path):
    raw = _make_legacy_raw(
        tracks=[{"track_id": "v1", "kind": "video", "clip_ids": ["c1"]}],
        clips={"c1": {
            "clip_id": "c1", "asset_id": "a1",
            "source_range": {"start": 0, "end": 1},
            "timeline_range": {"start": 0, "end": 1},
        }},
    )
    proj_dir = _write_project(raw, str(tmp_path))
    core = ProjectCore.open(proj_dir)
    assert len(core.project.timelines) == 1
    assert core.project.timelines[0].timeline_id == "main"
    # Legacy field is gone (Pydantic default extra='ignore'); the
    # deprecated property still resolves correctly.
    assert core.project.timeline is core.project.timelines[0]
    assert core.project.active_timeline_id == "main"
    assert core.project.default_timeline_id == "main"
    assert core.project.schema_version == "0.2"


# --- 2. Migration is idempotent -------------------------------------

def test_migration_idempotent(tmp_path):
    raw = _make_legacy_raw(
        tracks=[{"track_id": "v1", "kind": "video", "clip_ids": []}],
    )
    once = _migrate_raw_to_multi_timeline(raw)
    twice = _migrate_raw_to_multi_timeline(once)
    assert once == twice
    assert len(twice["timelines"]) == 1
    assert twice["schema_version"] == "0.2"

    # Real open+save+open roundtrip must be stable.
    proj_dir = _write_project(raw, str(tmp_path))
    core = ProjectCore.open(proj_dir)
    core.save_state()
    core2 = ProjectCore.open(proj_dir)
    core2.save_state()
    raw_after = json.loads(Path(proj_dir, "current.json").read_text(encoding="utf-8"))
    assert len(raw_after["timelines"]) == 1
    assert raw_after["active_timeline_id"] == "main"
    assert raw_after["default_timeline_id"] == "main"


# --- 3. Save/reload preserves timeline ID + all timeline state ------

def test_save_reload_preserves_timeline_state(tmp_path):
    raw = _make_legacy_raw(
        timeline_id="main",
        tracks=[
            {"track_id": "v1", "kind": "video", "clip_ids": ["c1", "c2"]},
            {"track_id": "t1", "kind": "text", "clip_ids": ["c3"]},
        ],
        clips={
            "c1": {"clip_id": "c1", "asset_id": "a1",
                    "source_range": {"start": 0, "end": 2},
                    "timeline_range": {"start": 0, "end": 2}},
            "c2": {"clip_id": "c2", "asset_id": "a2",
                    "source_range": {"start": 0, "end": 3},
                    "timeline_range": {"start": 2, "end": 5}},
            "c3": {"clip_id": "c3", "asset_id": "a3",
                    "source_range": {"start": 0, "end": 1},
                    "timeline_range": {"start": 1, "end": 3}},
        },
    )
    proj_dir = _write_project(raw, str(tmp_path))
    core = ProjectCore.open(proj_dir)
    core.save_state()
    core2 = ProjectCore.open(proj_dir)
    tl = core2.project.timelines[0]
    assert tl.timeline_id == "main"
    track_ids = sorted(t.track_id for t in tl.tracks)
    assert track_ids == ["t1", "v1"]
    assert set(core2.project.clips) == {"c1", "c2", "c3"}


# --- 4. active/default IDs survive save/reload ----------------------

def test_active_default_ids_survive_save_reload(tmp_path):
    raw = _make_post_03e_raw(
        timelines=[
            {"timeline_id": "main", "name": "完整版", "tracks": []},
            {"timeline_id": "seed", "name": "种草版", "tracks": []},
        ],
        active="seed",
        default="main",
    )
    proj_dir = _write_project(raw, str(tmp_path))
    core = ProjectCore.open(proj_dir)
    core.save_state()
    raw_after = json.loads(Path(proj_dir, "current.json").read_text(encoding="utf-8"))
    assert raw_after["active_timeline_id"] == "seed"
    assert raw_after["default_timeline_id"] == "main"
    core2 = ProjectCore.open(proj_dir)
    assert core2.project.active_timeline_id == "seed"
    assert core2.project.default_timeline_id == "main"


# --- 5. Active timeline always exists -------------------------------

def test_active_timeline_always_exists(tmp_path):
    # Post-03E file with a stale active id; loader must repair.
    raw = _make_post_03e_raw(
        timelines=[{"timeline_id": "main", "name": "main", "tracks": []}],
        active="main",
        default="main",
    )
    proj_dir = _write_project(raw, str(tmp_path))
    core = ProjectCore.open(proj_dir)
    assert core.project.active_timeline is not None
    assert core.project.active_timeline.timeline_id == "main"

    # Even if we manually corrupt the active id, get_timeline should
    # fall back through default → first, and active_timeline property
    # must always resolve.
    core.project.active_timeline_id = "does_not_exist"
    assert core.project.active_timeline is not None
    assert core.project.active_timeline.timeline_id == "main"


# --- 6. Default timeline always exists ------------------------------

def test_default_timeline_always_exists(tmp_path):
    raw = _make_post_03e_raw(
        timelines=[{"timeline_id": "main", "name": "main", "tracks": []}],
    )
    proj_dir = _write_project(raw, str(tmp_path))
    core = ProjectCore.open(proj_dir)
    assert core.project.default_timeline is not None
    core.project.default_timeline_id = "missing"
    assert core.project.default_timeline is not None
    assert core.project.default_timeline.timeline_id == "main"


# --- 7. Cannot persist zero timelines -------------------------------

def test_cannot_persist_zero_timelines(tmp_path):
    core = ProjectCore.create(str(tmp_path), "p1")
    core.project.timelines = []
    with pytest.raises(ValueError, match="at least one Timeline"):
        core.save_state()


# --- 8. Rename does not change timeline_id --------------------------

def test_rename_does_not_change_timeline_id(tmp_path):
    core = ProjectCore.create(str(tmp_path), "p1")
    tl = core.project.active_timeline
    original_id = tl.timeline_id
    tl.name = "完整版"
    core.save_state()
    core2 = ProjectCore.open(str(Path(tmp_path) / "p1"))
    assert core2.project.timelines[0].timeline_id == original_id
    assert core2.project.timelines[0].name == "完整版"


# --- 9. derived_from uses stable timeline_id -----------------------

def test_derived_from_uses_stable_id():
    main = Timeline(timeline_id="main", name="完整版")
    seed = Timeline(timeline_id="seed", name="种草版",
                     derived_from="main")  # stable id, not name
    p = Project(
        project_id="p1", name="t",
        timelines=[main, seed],
        active_timeline_id="seed",
        default_timeline_id="main",
    )
    # Serialize and reload; derived_from must round-trip as the id.
    raw = p.model_dump()
    p2 = Project.model_validate(raw)
    assert p2.timelines[1].derived_from == "main"
    assert p2.timelines[1].name == "种草版"


# --- 10. Timeline-local state isolated between two timelines --------

def test_timeline_local_state_isolated(tmp_path):
    core = ProjectCore.create(str(tmp_path), "p1")
    # Manually add a second Timeline (03E-2 will introduce the command;
    # here we exercise the isolation contract directly).
    from yroll.core.manifest import Timeline, Track
    t1 = core.project.timelines[0]  # 'main'
    t1.tracks.append(Track(track_id="v1", kind=TrackKind.VIDEO))
    t2 = Timeline(timeline_id="seed", name="种草版",
                  tracks=[Track(track_id="v1", kind=TrackKind.VIDEO)])
    core.project.timelines.append(t2)
    core.project.active_timeline_id = "seed"
    core.project.default_timeline_id = "main"

    # Mutate seed's tracks — main must remain unchanged.
    seed_track_ids = [t.track_id for t in core.project.require_timeline("seed").tracks]
    main_track_ids = [t.track_id for t in core.project.require_timeline("main").tracks]
    assert seed_track_ids == ["v1"]
    assert main_track_ids == ["v1"]

    core.project.require_timeline("seed").tracks.append(
        Track(track_id="v2", kind=TrackKind.VIDEO))
    # W-B: empty tracks are auto-cleaned on load. Add clips to
    # main's v1 AND seed's v1 + v2 so they survive the migration.
    # The test still verifies Timeline-local state isolation: seed
    # has 2 tracks after the append, main has 1.
    core.project.clips["c-main-1"] = Clip(
        clip_id="c-main-1", asset_id="a-shared",
        source_range=TimeRange(start=0, end=1),
        timeline_range=TimeRange(start=0, end=1),
        track_id="v1", timeline_id="main",
    )
    core.project.clips["c-seed-1"] = Clip(
        clip_id="c-seed-1", asset_id="a-shared",
        source_range=TimeRange(start=0, end=1),
        timeline_range=TimeRange(start=0, end=1),
        track_id="v1", timeline_id="seed",
    )
    core.project.clips["c-seed-2"] = Clip(
        clip_id="c-seed-2", asset_id="a-shared",
        source_range=TimeRange(start=0, end=1),
        timeline_range=TimeRange(start=10, end=11),
        track_id="v2", timeline_id="seed",
    )
    core.project.require_timeline("main").tracks[0].clip_ids.append("c-main-1")
    core.project.require_timeline("seed").tracks[0].clip_ids.append("c-seed-1")
    core.project.require_timeline("seed").tracks[1].clip_ids.append("c-seed-2")
    core.save_state()
    core2 = ProjectCore.open(str(Path(tmp_path) / "p1"))
    main_after = core2.project.require_timeline("main")
    seed_after = core2.project.require_timeline("seed")
    assert len(main_after.tracks) == 1
    assert len(seed_after.tracks) == 2


# --- 11. Shared Asset remains one shared reference -----------------

def test_shared_asset_remains_one_reference(tmp_path):
    core = ProjectCore.create(str(tmp_path), "p1")
    asset = Asset(
        asset_id="a-shared",
        type=AssetType.IMAGE,
        path="media/a.png",
        identity=AssetIdentity(md5="deadbeef", size_bytes=1),
    )
    core.project.assets.append(asset)

    # Add a second Timeline referencing the same Asset.
    core.project.timelines.append(Timeline(timeline_id="seed",
                                              name="种草版", tracks=[]))
    core.save_state()

    core2 = ProjectCore.open(str(Path(tmp_path) / "p1"))
    assert len(core2.project.assets) == 1
    assert core2.project.assets[0].asset_id == "a-shared"
    # The Timeline count grew but assets stayed singleton.
    assert len(core2.project.timelines) == 2


# --- 12. Existing legacy fixtures remain green ----------------------

def test_existing_legacy_fixture_loads_clean(tmp_path):
    """A realistic pre-03E shape (with v1/v2/v3/a1/t1 pre-created tracks,
    as GUI-03C's `ensure_default_tracks` used to ship). After migration
    we should have exactly one Timeline.

    W-B: empty tracks are auto-cleaned on load (load-time migration).
    The pre-W-B test asserted all 8 tracks survived; under W-B they
    are removed because they have no clips. We now assert the
    load-time migration ran and left the Timeline with NO empty
    tracks (preserves the new invariant).
    """
    raw = _make_legacy_raw(
        timeline_id="main",
        tracks=[
            {"track_id": "v1", "kind": "video", "clip_ids": []},
            {"track_id": "v2", "kind": "video", "clip_ids": []},
            {"track_id": "v3", "kind": "video", "clip_ids": []},
            {"track_id": "a1", "kind": "audio", "clip_ids": []},
            {"track_id": "a2", "kind": "audio", "clip_ids": []},
            {"track_id": "a3", "kind": "audio", "clip_ids": []},
            {"track_id": "t1", "kind": "text", "clip_ids": []},
            {"track_id": "t2", "kind": "text", "clip_ids": []},
        ],
    )
    proj_dir = _write_project(raw, str(tmp_path))
    core = ProjectCore.open(proj_dir)
    assert len(core.project.timelines) == 1
    # W-B: empty tracks are auto-cleaned on load. Surviving tracks
    # have >= 1 clip; with the fixture's empty tracks, none survive.
    assert core.project.timelines[0].tracks == [], (
        "load-time migration must remove all empty tracks"
    )
    # Re-save must drop the legacy field and bump schema_version.
    core.save_state()
    raw_after = json.loads(Path(proj_dir, "current.json").read_text(encoding="utf-8"))
    assert "timeline" not in raw_after
    assert raw_after["schema_version"] == "0.2"


# --- Bonus: post-03E file with missing IDs gets repaired -----------

def test_post_03e_missing_ids_repaired(tmp_path):
    raw = _make_post_03e_raw(
        timelines=[{"timeline_id": "main", "name": "main", "tracks": []}],
        active="",  # intentionally bad
        default="",
    )
    proj_dir = _write_project(raw, str(tmp_path))
    core = ProjectCore.open(proj_dir)
    assert core.project.active_timeline_id == "main"
    assert core.project.default_timeline_id == "main"


# --- Bonus: bare constructor returns None for active_timeline -------

def test_bare_project_active_timeline_is_none():
    p = Project(project_id="p1", name="t1")
    assert p.timelines == []
    assert p.active_timeline is None
    assert p.timeline is None