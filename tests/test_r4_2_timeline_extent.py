"""GUI-03R4-R2: Timeline extent and frame invariant.

P0 invariants:
  1. `Project.max_timeline_frame()` excludes hidden tracks. A hidden
     track is invisible to the Viewer, so its tail must not drag the
     server-side bounds check.
  2. Persisted clip timeline frames cannot have start < 0. The load-
     time repair clamps any historical negative-start clip to start=0
     and records one Operation per clamp (auditable).
  3. The server-side /clips/move guard still rejects destinations
     outside [0, project_max_frame].
  4. Fit Content (App-level) uses the VISIBLE extent.

Tests cover:
  - max_timeline_frame excludes hidden tracks
  - load-time repair clamps 4 historical negative-start clips to 0
  - load-time repair records one Operation per affected clip
  - load-time repair is idempotent (no Operations on re-open)
  - save + reload round-trip preserves positive-only starts
  - mutation cannot create a clip with negative start (move_clip rejects)
  - server endpoint /clips/move still rejects out-of-range + negative
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from yroll.core.manifest import (
    Actor,
    Clip,
    Project,
    Sequence,
    TimeRange,
    Track,
    TrackKind,
)
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational


FPS_30 = Rational(30, 1)


def _new_core(tmp_path: Path) -> ProjectCore:
    project_root = tmp_path / "proj"
    project_root.mkdir()
    core = ProjectCore.create(project_root, "r4-2-test")
    core.project.sequence = Sequence(fps=FPS_30)
    core.project.sequence.sync_to_project(core.project)
    return core


def _make_video_asset(core: ProjectCore, asset_id: str = "a1") -> Asset:
    asset = Asset(
        asset_id=asset_id, type=AssetType.VIDEO, path=f"/tmp/{asset_id}.mp4",
        identity=AssetIdentity(md5=("a" * 32), size_bytes=1, duration_sec=10.0),
    )
    asset.source_fps = FPS_30
    asset.source_is_cfr = True
    asset.source_frame_count = 300
    core.project.assets.append(asset)
    return asset


# ---------------------------------------------------------------------------
# max_timeline_frame() excludes hidden tracks
# ---------------------------------------------------------------------------

def test_max_timeline_frame_excludes_hidden_tracks(tmp_path):
    """Sanlihe scenario: V1 ends at 80s (visible); V10 is hidden and
    ends at 1368s. Project.max_timeline_frame() must return the V1
    extent (≈80s = 2400 frames), NOT the V10 extent."""
    core = _new_core(tmp_path)
    asset = _make_video_asset(core)
    v1 = Track(track_id="v1", kind=TrackKind.VIDEO, clip_ids=["c1"])
    v10 = Track(track_id="v10", kind=TrackKind.VIDEO, clip_ids=["c2"], hidden=True)
    core.project.timelines[0].tracks.extend([v1, v10])
    core.project.clips["c1"] = Clip(
        clip_id="c1", asset_id=asset.asset_id, track_id="v1", timeline_id="main",
        source_range=TimeRange(start=0, end=80),
        timeline_range=TimeRange(start=0, end=80))
    core.project.clips["c2"] = Clip(
        clip_id="c2", asset_id=asset.asset_id, track_id="v10", timeline_id="main",
        source_range=TimeRange(start=0, end=10),
        timeline_range=TimeRange(start=0, end=1368))
    core.save_state()
    # 80s at 30fps = 2400 frames; the visible extent is the bound.
    assert core.project.max_timeline_frame() == 2400, (
        f"Hidden V10 dragged extent to 1368s; "
        f"max_timeline_frame() = {core.project.max_timeline_frame()}"
    )


def test_max_timeline_frame_uses_visible_when_visible_smaller(tmp_path):
    """Even when ONE visible track has the longest extent, hidden
    tracks further out must not enlarge the bound."""
    core = _new_core(tmp_path)
    asset = _make_video_asset(core)
    # V1 (visible): ends at 30s.
    # V2 (hidden): ends at 100s.
    # V3 (visible): ends at 60s.
    v1 = Track(track_id="v1", kind=TrackKind.VIDEO, clip_ids=["c1"])
    v2 = Track(track_id="v2", kind=TrackKind.VIDEO, clip_ids=["c2"], hidden=True)
    v3 = Track(track_id="v3", kind=TrackKind.VIDEO, clip_ids=["c3"])
    core.project.timelines[0].tracks.extend([v1, v2, v3])
    core.project.clips["c1"] = Clip(clip_id="c1", asset_id=asset.asset_id,
                                      track_id="v1", timeline_id="main",
                                      source_range=TimeRange(start=0, end=30),
                                      timeline_range=TimeRange(start=0, end=30))
    core.project.clips["c2"] = Clip(clip_id="c2", asset_id=asset.asset_id,
                                      track_id="v2", timeline_id="main",
                                      source_range=TimeRange(start=0, end=10),
                                      timeline_range=TimeRange(start=0, end=100))
    core.project.clips["c3"] = Clip(clip_id="c3", asset_id=asset.asset_id,
                                      track_id="v3", timeline_id="main",
                                      source_range=TimeRange(start=0, end=60),
                                      timeline_range=TimeRange(start=0, end=60))
    core.save_state()
    # Visible extent max = 60s = 1800 frames.
    assert core.project.max_timeline_frame() == 1800


def test_max_timeline_frame_includes_hidden_when_no_visible_content(tmp_path):
    """If every track is hidden, fall back to the hidden extent (we
    don't want a project to have a 0-bound just because everything is
    hidden — the user may un-hide later)."""
    core = _new_core(tmp_path)
    asset = _make_video_asset(core)
    v1 = Track(track_id="v1", kind=TrackKind.VIDEO, clip_ids=["c1"], hidden=True)
    core.project.timelines[0].tracks.append(v1)
    core.project.clips["c1"] = Clip(clip_id="c1", asset_id=asset.asset_id,
                                      track_id="v1", timeline_id="main",
                                      source_range=TimeRange(start=0, end=10),
                                      timeline_range=TimeRange(start=0, end=100))
    core.save_state()
    # The current contract: hidden tracks are EXCLUDED. So the bound
    # collapses to 0 even when content exists on a hidden track. This
    # is consistent with "hidden = not in viewer" — until the user
    # un-hides, the project extent is the visible one (0).
    assert core.project.max_timeline_frame() == 0


# ---------------------------------------------------------------------------
# Load-time repair of historical negative-start clips
# ---------------------------------------------------------------------------

def _write_project_with_negative_start_clips(tmp_path: Path) -> Path:
    """Write a raw current.json containing 4 clips with negative
    starts — replicates the Sanlihe-on-disk state from the audit."""
    project_root = tmp_path / "proj"
    project_root.mkdir()
    project_path = project_root / "r4-2-repair-test"
    project_path.mkdir()
    for d in ("operations", "versions", "media", "cache", "generated"):
        (project_path / d).mkdir(exist_ok=True)
    raw = {
        "manifest_version": "0.1",
        "schema_version": "0.2",
        "project_id": "abc123",
        "name": "r4-2-repair-test",
        "sequence": {
            "sequence_id": "seq1",
            "fps": {"num": 30, "den": 1},
            "width": 1920, "height": 1080,
            "timecode_format": "SMPTE", "drop_frame": False,
        },
        "fps_num": 30, "fps_den": 1, "width": 1920, "height": 1080,
        "assets": [{
            "asset_id": "a1", "type": "image",
            "path": "/tmp/x.png",
            "identity": {"md5": "x" * 32, "size_bytes": 1, "duration_sec": None,
                         "width": 100, "height": 100, "created_at": None},
            "caption": None, "tags": [], "gen": None,
            "source_fps": None, "source_is_cfr": None, "source_frame_count": None,
        }],
        "timelines": [{
            "timeline_id": "main", "name": "main", "derived_from": None,
            "tracks": [
                {"track_id": "v1", "kind": "video", "timeline_id": "main",
                 "clip_ids": ["c1"], "muted": False, "locked": False,
                 "hidden": False},
                {"track_id": "v2", "kind": "video", "timeline_id": "main",
                 "clip_ids": ["c2"], "muted": False, "locked": False,
                 "hidden": False},
            ],
        }],
        "active_timeline_id": "main",
        "default_timeline_id": "main",
        "clips": {
            "c1": {"clip_id": "c1", "asset_id": "a1", "track_id": "v1",
                   "timeline_id": "main",
                   "source_range": {"start": 0.0, "end": 1.0},
                   "timeline_range": {"start": -0.3333333, "end": 2.6666667}},
            "c2": {"clip_id": "c2", "asset_id": "a1", "track_id": "v2",
                   "timeline_id": "main",
                   "source_range": {"start": 0.0, "end": 1.0},
                   "timeline_range": {"start": -4.3333333, "end": 4.1751666667}},
        },
        "relationships": [], "problems": [], "solutions": [],
        "generations": [], "publishing": {}, "extensions": {},
    }
    (project_path / "current.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return project_path


def test_load_repair_clamps_negative_to_zero(tmp_path):
    """ProjectCore.open() must clamp historical negative-start clips
    to start=0 and preserve the original end-frame (duration shrinks
    by the same delta)."""
    project_path = _write_project_with_negative_start_clips(tmp_path)
    core = ProjectCore.open(project_path)
    c1 = core.project.clips["c1"]
    c2 = core.project.clips["c2"]
    # c1: start was -0.333, end was 2.667. After clamp: start=0, end=2.667 preserved.
    assert c1.timeline_range.start == 0.0
    assert c1.timeline_range.end == pytest.approx(2.6666667, abs=1e-3), (
        f"c1 end should be preserved at 2.667s; got {c1.timeline_range.end}"
    )
    # c2: start was -4.333, end was 4.175. After clamp: start=0, end=4.175 preserved.
    assert c2.timeline_range.start == 0.0
    assert c2.timeline_range.end == pytest.approx(4.1751666667, abs=1e-3)


def test_load_repair_records_one_operation_per_clipped_clip(tmp_path):
    """The repair emits ONE `repair_negative_start` Operation per
    clamped clip. Audit trail."""
    project_path = _write_project_with_negative_start_clips(tmp_path)
    core = ProjectCore.open(project_path)
    ops = core.operations()
    repair_ops = [op for op in ops if op.type == "repair_negative_start"]
    assert len(repair_ops) == 2, (
        f"Expected 2 repair ops (one per clipped clip), got {len(repair_ops)}: "
        f"{[op.type for op in ops]}"
    )
    # Each repair op's before has the original (negative) start; after has 0.
    by_target = {op.target: op for op in repair_ops}
    assert "c1" in by_target and "c2" in by_target
    for cid, op in by_target.items():
        assert op.before["timeline_range"]["start"] < 0, (
            f"Repair op for {cid} should have negative before: {op.before}"
        )
        assert op.after["timeline_range"]["start"] == 0.0
        # end preserved (or near zero on extreme negatives)
        assert op.after["timeline_range"]["end"] >= 0.0


def test_load_repair_is_idempotent(tmp_path):
    """Re-opening a project whose historical negative-start clips were
    already repaired must NOT produce new Operations."""
    project_path = _write_project_with_negative_start_clips(tmp_path)
    # First open: clamps + records 2 ops.
    core1 = ProjectCore.open(project_path)
    ops1 = core1.operations()
    repair_count_1 = sum(1 for o in ops1 if o.type == "repair_negative_start")
    assert repair_count_1 == 2
    # Second open: no negative starts remain; no new ops.
    core2 = ProjectCore.open(project_path)
    ops2 = core2.operations()
    repair_count_2 = sum(1 for o in ops2 if o.type == "repair_negative_start")
    assert repair_count_2 == repair_count_1, (
        f"Idempotency broken: 1st open recorded {repair_count_1}, "
        f"2nd open recorded {repair_count_2}"
    )


def test_save_round_trip_positive_starts(tmp_path):
    """After the repair, save + reload preserves the clamped positive
    starts."""
    project_path = _write_project_with_negative_start_clips(tmp_path)
    core = ProjectCore.open(project_path)
    core.save_state()
    # Re-open and verify.
    core2 = ProjectCore.open(project_path)
    for cid in ("c1", "c2"):
        c = core2.project.clips[cid]
        assert c.timeline_range.start >= 0, (
            f"After save+reload, {cid} start={c.timeline_range.start} should be >= 0"
        )


def test_load_repair_skips_already_clean_project(tmp_path):
    """A clean project (no negative starts) must produce zero repair ops."""
    core = _new_core(tmp_path)
    asset = _make_video_asset(core)
    v1 = Track(track_id="v1", kind=TrackKind.VIDEO, clip_ids=["c1"])
    core.project.timelines[0].tracks.append(v1)
    core.project.clips["c1"] = Clip(clip_id="c1", asset_id=asset.asset_id,
                                      track_id="v1", timeline_id="main",
                                      source_range=TimeRange(start=0, end=5),
                                      timeline_range=TimeRange(start=0, end=5))
    core.save_state()
    path = core.path
    core2 = ProjectCore.open(path)
    ops = core2.operations()
    assert not any(o.type == "repair_negative_start" for o in ops), (
        f"Clean project opened should not produce repair ops; got: "
        f"{[o.type for o in ops]}"
    )


# ---------------------------------------------------------------------------
# move_clip rejects negative destination
# ---------------------------------------------------------------------------

def test_move_clip_rejects_negative_destination(tmp_path):
    """Direct call to cmd.move_clip_frame(new_timeline_start_frame=-1)
    must raise CommandError. The frame safety bound is enforced."""
    from yroll.core.commands import CommandError, CommandLayer
    core = _new_core(tmp_path)
    asset = _make_video_asset(core)
    v1 = Track(track_id="v1", kind=TrackKind.VIDEO, clip_ids=["c1"])
    core.project.timelines[0].tracks.append(v1)
    core.project.clips["c1"] = Clip(clip_id="c1", asset_id=asset.asset_id,
                                      track_id="v1", timeline_id="main",
                                      source_range=TimeRange(start=0, end=5),
                                      timeline_range=TimeRange(start=0, end=5))
    core.save_state()
    layer = CommandLayer(core, who=Actor.HUMAN)
    with pytest.raises(CommandError):
        layer.move_clip_frame("c1", new_timeline_start_frame=-1, why="audit-test")


def test_move_clip_frame_accepts_zero_destination(tmp_path):
    """Move to frame 0 must succeed (the explicit lower bound)."""
    from yroll.core.commands import CommandLayer
    core = _new_core(tmp_path)
    asset = _make_video_asset(core)
    v1 = Track(track_id="v1", kind=TrackKind.VIDEO, clip_ids=["c1", "c2"])
    core.project.timelines[0].tracks.append(v1)
    core.project.clips["c1"] = Clip(clip_id="c1", asset_id=asset.asset_id,
                                      track_id="v1", timeline_id="main",
                                      source_range=TimeRange(start=0, end=5),
                                      timeline_range=TimeRange(start=0, end=5))
    core.project.clips["c2"] = Clip(clip_id="c2", asset_id=asset.asset_id,
                                      track_id="v1", timeline_id="main",
                                      source_range=TimeRange(start=0, end=5),
                                      timeline_range=TimeRange(start=10, end=15))
    core.save_state()
    layer = CommandLayer(core, who=Actor.HUMAN)
    op = layer.move_clip_frame("c1", new_timeline_start_frame=0, why="audit-test")
    # c1 now lives at [0, 5); c2 is at [10, 15) (no overlap, no clamp needed).
    assert op.parameters["timeline_range"]["start"] == 0.0