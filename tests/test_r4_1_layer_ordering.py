"""GUI-03R4-R1: Multi-layer Preview correctness.

P0 invariant: visual layer_index values are GLOBALLY UNIQUE across
all visible (non-hidden) visual tracks. Tracks in the visual stack are
ordered by KIND_RANK (text/video/audio) and within kind by natural-
numeric suffix (v1 < v2 < v10).

5 acceptance scenarios from the audit:
  1. V1 only → V1
  2. V2 only → V2
  3. V1 + V2 → V2 over V1 (V2's layer_index > V1's layer_index)
  4. V1 + V2 + V3 → V3 > V2 > V1
  5. V2 hidden → V1's layers still appear
  6. upper clip ends while lower remains → lower immediately visible
"""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.frame_preview import (
    composite_preview_at_frame,
)
from yroll.core.manifest import (
    Actor,
    Sequence,
    Track,
    TrackKind,
)
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.plan import build_preview_plan, _count_visual_layers
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational


FPS_30 = Rational(30, 1)


def _new_image_project(tmp_path: Path, n: int = 4):
    """Build a project with N image assets (video-kind compatible).
    Returns (project_path, core). The plan supports images as visual
    layers — same code path as videos for layer_index."""
    project_root = tmp_path / "proj"
    project_root.mkdir()
    name = "r4-1-test"
    core = ProjectCore.create(project_root, name)
    core.project.sequence = Sequence(fps=FPS_30)
    core.project.sequence.sync_to_project(core.project)
    for i in range(n):
        core.project.assets.append(Asset(
            asset_id=f"img{i+1}",
            type=AssetType.IMAGE,
            path=f"/tmp/img{i+1}.png",
            identity=AssetIdentity(md5=("i" * 32) + str(i), size_bytes=1),
            source_fps=None, source_is_cfr=True,
        ))
    return project_root / name, core


def _add_track(layer: CommandLayer, kind: TrackKind, tid: str):
    """Add a track via add_track (creates even with no clips)."""
    return layer.add_track(kind, track_id=tid)


# ---------------------------------------------------------------------------
# Scenario 1: V1 only → V1
# ---------------------------------------------------------------------------

def test_v1_only_layer(tmp_path):
    project_dir, core = _new_image_project(tmp_path, n=1)
    layer = CommandLayer(core, who=Actor.HUMAN)
    _add_track(layer, TrackKind.VIDEO, "v1")
    layer.add_image_clip("img1", 0, 60)  # 0..2s
    plan = build_preview_plan(core.project, timeline_id="main")
    # plan.tracks contains v1 only; one layer
    assert len(plan.tracks) == 1
    assert len(plan.tracks[0]) == 1
    assert plan.tracks[0][0].track_id == "v1"
    assert plan.tracks[0][0].layer_index == 0


# ---------------------------------------------------------------------------
# Scenario 2: V2 only → V2
# ---------------------------------------------------------------------------

def test_v2_only_layer(tmp_path):
    project_dir, core = _new_image_project(tmp_path, n=1)
    layer = CommandLayer(core, who=Actor.HUMAN)
    _add_track(layer, TrackKind.VIDEO, "v2")
    layer.add_image_clip("img1", 0, 60)
    plan = build_preview_plan(core.project, timeline_id="main")
    assert len(plan.tracks) == 1
    assert plan.tracks[0][0].track_id == "v2"
    assert plan.tracks[0][0].layer_index == 0


# ---------------------------------------------------------------------------
# Scenario 3: V1 + V2 → V2 layer_index > V1 layer_index
# ---------------------------------------------------------------------------

def test_v2_above_v1_layer_index(tmp_path):
    """Two visual tracks. V1 has many clips (high per-track indices);
    V2 has fewer. V2's clip must have a higher layer_index than ALL
    of V1's clips so the V2 layer renders on top."""
    project_dir, core = _new_image_project(tmp_path, n=10)
    layer = CommandLayer(core, who=Actor.HUMAN)
    _add_track(layer, TrackKind.VIDEO, "v1")
    _add_track(layer, TrackKind.VIDEO, "v2")
    # V1: 5 clips, large per-track layer indices under the OLD code.
    for i in range(5):
        layer.add_image_clip(f"img{i+1}", i * 60, 30)
    # V2: 1 clip.
    layer.add_image_clip("img10", 0, 60)
    plan = build_preview_plan(core.project, timeline_id="main")
    # Find layer_indices for v1 and v2 clips.
    v1_layers = [l for layers in plan.tracks for l in layers if l.track_id == "v1"]
    v2_layers = [l for layers in plan.tracks for l in layers if l.track_id == "v2"]
    assert len(v1_layers) == 5
    assert len(v2_layers) == 1
    max_v1 = max(l.layer_index for l in v1_layers)
    v2_idx = v2_layers[0].layer_index
    assert v2_idx > max_v1, (
        f"V2 must render above V1; got v2.layer_index={v2_idx} "
        f"<= max(v1.layer_index)={max_v1}"
    )


# ---------------------------------------------------------------------------
# Scenario 4: V1 + V2 + V3 → V3 > V2 > V1 (all layer_index monotonic)
# ---------------------------------------------------------------------------

def test_v3_above_v2_above_v1(tmp_path):
    project_dir, core = _new_image_project(tmp_path, n=3)
    layer = CommandLayer(core, who=Actor.HUMAN)
    _add_track(layer, TrackKind.VIDEO, "v1")
    _add_track(layer, TrackKind.VIDEO, "v2")
    _add_track(layer, TrackKind.VIDEO, "v3")
    layer.add_image_clip("img1", 0, 30)  # V1
    layer.add_image_clip("img2", 0, 30)  # V2
    layer.add_image_clip("img3", 0, 30)  # V3
    plan = build_preview_plan(core.project, timeline_id="main")
    by_track = {tid: [l for layers in plan.tracks for l in layers if l.track_id == tid]
                for tid in ("v1", "v2", "v3")}
    assert len(by_track["v1"]) == 1
    assert len(by_track["v2"]) == 1
    assert len(by_track["v3"]) == 1
    v1_idx = by_track["v1"][0].layer_index
    v2_idx = by_track["v2"][0].layer_index
    v3_idx = by_track["v3"][0].layer_index
    assert v1_idx < v2_idx < v3_idx, (
        f"V1 < V2 < V3 invariant broken: v1={v1_idx}, v2={v2_idx}, v3={v3_idx}"
    )


def test_v10_above_v9_above_v2_natural_order(tmp_path):
    """v10 must sort ABOVE v9 (natural numeric suffix, NOT lexical —
    v10 > v2 lexicographically but v2 < v9 < v10 numerically)."""
    project_dir, core = _new_image_project(tmp_path, n=3)
    layer = CommandLayer(core, who=Actor.HUMAN)
    _add_track(layer, TrackKind.VIDEO, "v2")
    _add_track(layer, TrackKind.VIDEO, "v9")
    _add_track(layer, TrackKind.VIDEO, "v10")
    layer.add_image_clip("img1", 0, 30)
    layer.add_image_clip("img2", 0, 30)
    layer.add_image_clip("img3", 0, 30)
    plan = build_preview_plan(core.project, timeline_id="main")
    indices = {tid: next(l for layers in plan.tracks for l in layers if l.track_id == tid).layer_index
               for tid in ("v2", "v9", "v10")}
    assert indices["v2"] < indices["v9"] < indices["v10"], (
        f"Natural numeric ordering broken: {indices}"
    )


# ---------------------------------------------------------------------------
# Scenario 5: V2 hidden → V1's layers still appear (and V2's layers don't)
# ---------------------------------------------------------------------------

def test_hidden_track_excluded_from_plan(tmp_path):
    project_dir, core = _new_image_project(tmp_path, n=3)
    layer = CommandLayer(core, who=Actor.HUMAN)
    _add_track(layer, TrackKind.VIDEO, "v1")
    _add_track(layer, TrackKind.VIDEO, "v2")
    layer.add_image_clip("img1", 0, 30)   # V1
    layer.add_image_clip("img2", 0, 30)   # V2
    # Hide V2.
    layer.set_track_hidden("v2", True, why="audit")
    plan = build_preview_plan(core.project, timeline_id="main")
    all_layers = [l for layers in plan.tracks for l in layers]
    track_ids = {l.track_id for l in all_layers}
    assert "v1" in track_ids, f"V1 must remain in plan: {track_ids}"
    assert "v2" not in track_ids, f"V2 must be excluded: {track_ids}"


def test_hidden_track_excluded_from_composite_at_frame(tmp_path):
    """The /preview/at_frame endpoint also excludes hidden tracks."""
    project_dir, core = _new_image_project(tmp_path, n=3)
    layer = CommandLayer(core, who=Actor.HUMAN)
    _add_track(layer, TrackKind.VIDEO, "v1")
    _add_track(layer, TrackKind.VIDEO, "v2")
    layer.add_image_clip("img1", 0, 60)
    layer.add_image_clip("img2", 0, 60)
    layer.set_track_hidden("v2", True, why="audit")
    pv = composite_preview_at_frame(core.project, 30, FPS_30)
    track_ids = {l.track_id for l in pv.visual_layers}
    assert "v1" in track_ids
    assert "v2" not in track_ids


# ---------------------------------------------------------------------------
# Scenario 6: upper clip ends while lower remains → lower immediately visible
# ---------------------------------------------------------------------------

def test_upper_ends_lower_visible(tmp_path):
    """V1 has a clip [0, 60]; V2 has a clip [0, 30]. At frame 45
    (V1 still active, V2 ended) only V1 must appear in the composite."""
    project_dir, core = _new_image_project(tmp_path, n=2)
    layer = CommandLayer(core, who=Actor.HUMAN)
    _add_track(layer, TrackKind.VIDEO, "v1")
    _add_track(layer, TrackKind.VIDEO, "v2")
    layer.add_image_clip("img1", 0, 60)    # V1: 0..60
    layer.add_image_clip("img2", 0, 30)    # V2: 0..30
    # Frame 10: both active.
    pv10 = composite_preview_at_frame(core.project, 10, FPS_30)
    tracks10 = {l.track_id for l in pv10.visual_layers}
    assert "v1" in tracks10 and "v2" in tracks10, tracks10
    # Frame 45: V2 ended, only V1.
    pv45 = composite_preview_at_frame(core.project, 45, FPS_30)
    tracks45 = {l.track_id for l in pv45.visual_layers}
    assert "v1" in tracks45, f"V1 must still appear after V2 ends: {tracks45}"
    assert "v2" not in tracks45, f"V2 must NOT appear after its clip ends: {tracks45}"


def test_upper_ends_lower_visible_in_plan(tmp_path):
    """Same scenario but verified against the cached plan + activeLayerAt."""
    project_dir, core = _new_image_project(tmp_path, n=2)
    layer = CommandLayer(core, who=Actor.HUMAN)
    _add_track(layer, TrackKind.VIDEO, "v1")
    _add_track(layer, TrackKind.VIDEO, "v2")
    layer.add_image_clip("img1", 0, 60)
    layer.add_image_clip("img2", 0, 30)
    plan = build_preview_plan(core.project, timeline_id="main")
    by_track = {tid: [l for layers in plan.tracks for l in layers if l.track_id == tid]
                for tid in ("v1", "v2")}
    # At frame 45, only V1 should be in its half-open range.
    assert len(by_track["v1"]) == 1 and by_track["v1"][0].timeline_start_frame == 0
    # V2's layer starts at 0, ends at 30; at frame 45 V2 layer is OUT of range.
    assert by_track["v2"][0].timeline_end_frame == 30


# ---------------------------------------------------------------------------
# Regression: text/audio tracks are NOT in visual layer_index
# ---------------------------------------------------------------------------

def test_text_tracks_dont_consume_visual_layer_index(tmp_path):
    """Text/SUBTITLE tracks contribute to subtitle_texts_by_range, not
    to plan.tracks. Audio tracks contribute to plan.tracks but with
    per-track layer_index (no z-stack). Neither should affect visual
    stacking order."""
    project_dir, core = _new_image_project(tmp_path, n=2)
    layer = CommandLayer(core, who=Actor.HUMAN)
    _add_track(layer, TrackKind.VIDEO, "v1")
    _add_track(layer, TrackKind.SUBTITLE, "t1")
    _add_track(layer, TrackKind.AUDIO, "a1")
    # A subtitle clip with text.
    from yroll.core.manifest import TimeRange, Clip
    sub = Clip(
        clip_id="sub1", asset_id="", track_id="t1", timeline_id="main",
        source_range=TimeRange(start=0.0, end=2.0),
        timeline_range=TimeRange(start=0.0, end=2.0),
        context={"text": "hello"},
    )
    core.project.clips["sub1"] = sub
    core.project.timelines[0].tracks[1].clip_ids.append("sub1")
    layer.add_image_clip("img1", 0, 60)
    plan = build_preview_plan(core.project, timeline_id="main")
    # v1 contributes one visual layer with layer_index = 0.
    visual_layers = [l for layers in plan.tracks for l in layers
                     if l.track_id == "v1"]
    assert len(visual_layers) == 1
    assert visual_layers[0].layer_index == 0
    # Subtitle text is captured in subtitle_texts_by_range.
    assert any("hello" in text for _, text in plan.subtitle_texts_by_range)


# ---------------------------------------------------------------------------
# _count_visual_layers helper sanity
# ---------------------------------------------------------------------------

def test_count_visual_layers_skips_video_without_source_fps(tmp_path):
    """Video without source_fps is skipped from the plan (GUI-02.3
    invariant). _count_visual_layers must agree so the layer_index
    base accounts only for layers that will actually appear."""
    project_dir, core = _new_image_project(tmp_path, n=2)
    layer = CommandLayer(core, who=Actor.HUMAN)
    v1 = _add_track(layer, TrackKind.VIDEO, "v1")
    layer.add_image_clip("img1", 0, 30)
    layer.add_image_clip("img2", 30, 30)
    # The images have source_fps=None; the helper counts them as visual.
    n = _count_visual_layers(v1, core.project, FPS_30)
    assert n == 2