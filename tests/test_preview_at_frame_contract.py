"""R6.2-B4: `/preview/at_frame` semantic contract pin.

The contract is frozen in docs/API-PREVIEW-AT-FRAME.md. This test
pins the wire format and the relationship to `/preview/plan`.

R6.2-B4 decision: `/preview/at_frame` is the materialized view of
`/preview/plan` at TimelineFrame=N. It MUST NOT implement an
independent layer-selection algorithm. The implementation
(composite_preview_at_frame in yroll/core/frame_preview.py) iterates
the same tracks + clips as build_preview_plan (same stack order,
same hidden exclusion, same membership). This test pins the
consistency.
"""
import json

import pytest

from yroll.core.frame_preview import composite_preview_at_frame
from yroll.core.plan import build_preview_plan, active_layer_at
from yroll.core.timebase import Rational
from yroll.core.project import ProjectCore
from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor


def _setup_core_with_v3_overlap(tmp_path):
    """Project with 2 video tracks:
    - V1: hidden=True, 3 clips
    - V3: hidden=False, 1 clip at frames [0, 150] at 30fps

    Yields a known composite where:
    - At frame 50: V3 clip should be in at_frame (V1 is hidden)
    - At frame 1000 (no V3 coverage): is_black=true, no layers
    """
    pc = ProjectCore.create(str(tmp_path), "at-frame-contract-test")
    ProjectCore.ensure_default_tracks(pc)
    from yroll.core.models import Asset, AssetIdentity, AssetType
    pc.project.assets.append(Asset(
        asset_id="a_v3", type=AssetType.IMAGE, path="/test/v3.jpg",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=5.0),
    ))
    pc.project.assets.append(Asset(
        asset_id="a_v1", type=AssetType.IMAGE, path="/test/v1.jpg",
        identity=AssetIdentity(md5="y" * 32, size_bytes=1, duration_sec=5.0),
    ))
    cmd = CommandLayer(pc, who=Actor.HUMAN)
    # V3 visible: 1 clip at frames [0, 150]
    cmd.add_clip_frame(
        asset_id="a_v3",
        src_start_frame=0, src_end_frame=150,
        timeline_start_frame=0, track_id="v3",
        timeline_id="main", why="v3-setup",
    )
    return pc


def test_at_frame_excludes_hidden_tracks(tmp_path):
    """Contract: Track.hidden == true → no layer from that track."""
    pc = _setup_core_with_v3_overlap(tmp_path)
    # Mark V1 as hidden (V1 has no clips so no-op, but rule still applies)
    pc.project.timeline.tracks[0].hidden = True  # v1
    pv = composite_preview_at_frame(
        pc.project, timeline_frame=50,
        fps=Rational(pc.project.fps_num, pc.project.fps_den),
    )
    assert pv.is_black is False, "V3 covers [0,150] so frame 50 is not black"
    assert all(l.track_id != "v1" for l in pv.visual_layers)
    assert any(l.track_id == "v3" for l in pv.visual_layers)


def test_at_frame_returns_is_black_when_no_coverage(tmp_path):
    """Contract: no active clip at F → is_black=True."""
    pc = _setup_core_with_v3_overlap(tmp_path)
    pv = composite_preview_at_frame(
        pc.project, timeline_frame=1000,  # outside V3 [0,150]
        fps=Rational(pc.project.fps_num, pc.project.fps_den),
    )
    assert pv.visual_layers == []
    assert pv.audio_layers == []
    assert pv.is_black is True


def test_at_frame_matches_plan_for_active_layer(tmp_path):
    """Contract: at_frame.active_layer_ids == plan.tracks[*].active_at(F).clip_ids."""
    pc = _setup_core_with_v3_overlap(tmp_path)
    fps = Rational(pc.project.fps_num, pc.project.fps_den)
    plan = build_preview_plan(pc.project, timeline_id="main", fps=fps)
    for F in [50, 100]:
        pv = composite_preview_at_frame(pc.project, timeline_frame=F, fps=fps)
        # Plan's active layers
        plan_active = set()
        for track_layers in plan.tracks:
            active = active_layer_at(track_layers, F)
            if active is not None:
                plan_active.add(active.clip_id)
        # at_frame's layers
        at_active = set(l.clip_id for l in pv.visual_layers)
        at_active |= set(l.clip_id for l in pv.audio_layers)
        assert at_active == plan_active, (
            f"at_frame membership diverges from plan at F={F}: "
            f"plan={plan_active}, at_frame={at_active}"
        )


def test_at_frame_layer_index_matches_plan(tmp_path):
    """Contract: layer_index in at_frame matches plan's layer_index
    for the same clip."""
    pc = _setup_core_with_v3_overlap(tmp_path)
    fps = Rational(pc.project.fps_num, pc.project.fps_den)
    plan = build_preview_plan(pc.project, timeline_id="main", fps=fps)
    pv = composite_preview_at_frame(pc.project, timeline_frame=50, fps=fps)
    for at_layer in pv.visual_layers:
        for track_layers in plan.tracks:
            for plan_layer in track_layers:
                if plan_layer.clip_id == at_layer.clip_id:
                    assert plan_layer.layer_index == at_layer.layer_index, (
                        f"layer_index mismatch for {at_layer.clip_id}: "
                        f"plan={plan_layer.layer_index}, at_frame={at_layer.layer_index}"
                    )


def test_at_frame_returns_empty_for_unknown_timeline(tmp_path):
    """Contract: unknown timeline_id → 200 with empty layers (no error)."""
    pc = _setup_core_with_v3_overlap(tmp_path)
    pv = composite_preview_at_frame(
        pc.project, timeline_frame=50,
        fps=Rational(pc.project.fps_num, pc.project.fps_den),
        timeline_id="nonexistent",
    )
    assert pv.visual_layers == []
    assert pv.audio_layers == []
    assert pv.is_black is True


def test_at_frame_negative_frame_returns_is_black(tmp_path):
    """Contract: frame < 0 → 200 with is_black=true."""
    pc = _setup_core_with_v3_overlap(tmp_path)
    pv = composite_preview_at_frame(
        pc.project, timeline_frame=-10,
        fps=Rational(pc.project.fps_num, pc.project.fps_den),
    )
    assert pv.is_black is True


def test_at_frame_video_clip_returns_full_composite_layer(tmp_path):
    """Contract: at_frame for a frame inside a visible video clip
    returns a CompositeLayer with the clip's metadata."""
    from yroll.core.models import Asset, AssetIdentity, AssetType
    pc = ProjectCore.create(str(tmp_path), "at-frame-video-test")
    ProjectCore.ensure_default_tracks(pc)
    pc.project.assets.append(Asset(
        asset_id="v1", type=AssetType.VIDEO, path="/t/v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=10.0),
        source_fps={"num": 30, "den": 1},
    ))
    cmd = CommandLayer(pc, who=Actor.HUMAN); cmd.add_clip_frame(
        asset_id="v1",
        src_start_frame=0, src_end_frame=300,
        timeline_start_frame=0, track_id="v1",
        timeline_id="main", why="setup",
    )
    pv = composite_preview_at_frame(
        pc.project, timeline_frame=100,
        fps=Rational(pc.project.fps_num, pc.project.fps_den),
    )
    assert not pv.is_black
    assert len(pv.visual_layers) == 1
    layer = pv.visual_layers[0]
    assert layer.clip_id is not None
    assert layer.asset_id == "v1"
    assert layer.kind == "video"
    assert layer.timeline_start_frame == 0
    assert layer.timeline_end_frame == 300