"""GUI-03D: L1 Timeline Composite Preview tests.

The 7 spec scenarios for the sanlihe-slice-30s benchmark:
  1. pure-image timeline visibly previews
  2. image duration follows TimelineFrameRange
  3. video previews correctly
  4. image + video overlap composites correctly
  5. track ordering is deterministic
  6. subtitles appear at their frame ranges
  7. empty tracks do not affect the result

Plus the HTTP endpoint round-trip and the Core API.
"""
from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from yroll.core.commands import CommandLayer
from yroll.core.frame_preview import (
    CompositePreview,
    composite_preview_at_frame,
    resolve_frame,
)
from yroll.core.manifest import (
    Actor,
    Project,
    Sequence,
    TimeRange,
    Track,
    TrackKind,
)
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational
from yroll.server.app import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FPS_30 = Rational(30, 1)


def _new_image_project(tmp_path, n=3):
    """Build a project with N image assets. Returns (project_path, core)
    where project_path is the directory `create_app` should open
    (ProjectCore.create writes to <root>/<name>, so the on-disk
    project lives at <tmp_path>/<name>)."""
    project_root = tmp_path / "proj"
    project_root.mkdir()
    name = "image-preview-test"
    core = ProjectCore.create(project_root, name)
    core.project.sequence = Sequence(fps=FPS_30)
    core.project.sequence.sync_to_project(core.project)
    for i in range(n):
        core.project.assets.append(Asset(
            asset_id=f"img{i+1}",
            type=AssetType.IMAGE,
            path=f"/tmp/img{i+1}.png",
            identity=AssetIdentity(md5=("i" * 32), size_bytes=1),
            source_fps=None, source_is_cfr=True,
        ))
    core.save_state()
    return project_root / name, core


def _add_video_project(tmp_path):
    project_root = tmp_path / "proj"
    project_root.mkdir()
    name = "video-preview-test"
    core = ProjectCore.create(project_root, name)
    core.project.sequence = Sequence(fps=FPS_30)
    core.project.sequence.sync_to_project(core.project)
    core.project.assets.append(Asset(
        asset_id="vid1", type=AssetType.VIDEO, path="/tmp/v.mp4",
        identity=AssetIdentity(md5=("v" * 32), size_bytes=1, duration_sec=10.0),
        source_fps=FPS_30, source_is_cfr=True, source_frame_count=300,
    ))
    core.save_state()
    return project_root / name, core


# ---------------------------------------------------------------------------
# 1. pure-image timeline visibly previews
# ---------------------------------------------------------------------------

def test_pure_image_timeline(tmp_path):
    """All-image timeline (no videos). composite_preview_at_frame
    returns one image visual layer per active clip. No audio, no
    subtitle. is_black is False when an image is active."""
    project_dir, core = _new_image_project(tmp_path, n=3)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_image_clip("img1", 0, 30)    # 0..1s
    layer.add_image_clip("img2", 30, 30)   # 1..2s
    layer.add_image_clip("img3", 60, 30)   # 2..3s
    # Sample the middle of each clip.
    pv1 = composite_preview_at_frame(core.project, 15, FPS_30)
    pv2 = composite_preview_at_frame(core.project, 45, FPS_30)
    pv3 = composite_preview_at_frame(core.project, 75, FPS_30)
    # Each returns exactly one image visual layer.
    assert len(pv1.visual_layers) == 1
    assert pv1.visual_layers[0].kind == "image"
    assert pv1.visual_layers[0].asset_id == "img1"
    assert pv1.visual_layers[0].source_frame == 0
    assert pv1.visual_layers[0].source_seconds == 0.0
    assert pv2.visual_layers[0].asset_id == "img2"
    assert pv3.visual_layers[0].asset_id == "img3"
    # No audio, no subtitle, not black.
    assert pv1.audio_layers == []
    assert pv1.subtitle_texts == []
    assert pv1.is_black is False


# ---------------------------------------------------------------------------
# 2. image duration follows TimelineFrameRange
# ---------------------------------------------------------------------------

def test_image_duration_follows_timeline_frame_range(tmp_path):
    """Each image clip's timeline_start_frame / timeline_end_frame in
    the composite layer matches the add_image_clip arguments."""
    project_dir, core = _new_image_project(tmp_path, n=2)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_image_clip("img1", 0, 30)       # 0..30 frames
    layer.add_image_clip("img2", 30, 60)      # 30..90 frames
    pv_0 = composite_preview_at_frame(core.project, 0, FPS_30)
    pv_29 = composite_preview_at_frame(core.project, 29, FPS_30)
    pv_30 = composite_preview_at_frame(core.project, 30, FPS_30)
    pv_89 = composite_preview_at_frame(core.project, 89, FPS_30)
    pv_90 = composite_preview_at_frame(core.project, 90, FPS_30)  # gap
    assert pv_0.visual_layers[0].timeline_start_frame == 0
    assert pv_0.visual_layers[0].timeline_end_frame == 30
    assert pv_29.visual_layers[0].timeline_end_frame == 30
    assert pv_30.visual_layers[0].timeline_start_frame == 30
    assert pv_30.visual_layers[0].timeline_end_frame == 90
    assert pv_89.visual_layers[0].timeline_end_frame == 90
    # Frame 90 is a gap → is_black.
    assert pv_90.is_black is True
    assert pv_90.visual_layers == []


# ---------------------------------------------------------------------------
# 3. video previews correctly
# ---------------------------------------------------------------------------

def test_video_preview(tmp_path):
    """A single video clip on the timeline. composite returns one
    video layer with source_frame = timeline_frame (conformant
    seq=src=30)."""
    project_dir, core = _add_video_project(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_clip("vid1", 0.0, 5.0, timeline_start=0.0)  # 0..5s
    pv = composite_preview_at_frame(core.project, 60, FPS_30)  # 2s
    assert len(pv.visual_layers) == 1
    assert pv.visual_layers[0].kind == "video"
    assert pv.visual_layers[0].asset_id == "vid1"
    # source_frame = timeline_frame (no speed change, conformant fps).
    assert pv.visual_layers[0].source_frame == 60
    # source_seconds = 60 / 30 = 2.0
    assert abs(pv.visual_layers[0].source_seconds - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# 4. image + video overlap composites correctly
# ---------------------------------------------------------------------------

def test_image_video_overlap_composites(tmp_path):
    """An image clip on V1 and a video clip on V2 both covering the
    same timeline frame. Both are returned in the composite, in
    track-declaration order (V1 before V2). The visual_layers are
    z-ordered: V1 (lower layer_index) → V2 (higher)."""
    project_dir, core = _new_image_project(tmp_path, n=1)
    core.project.assets.append(Asset(
        asset_id="vid1", type=AssetType.VIDEO, path="/tmp/v.mp4",
        identity=AssetIdentity(md5=("v" * 32), size_bytes=1, duration_sec=10.0),
        source_fps=FPS_30, source_is_cfr=True, source_frame_count=300,
    ))
    core.save_state()
    layer = CommandLayer(core, who=Actor.HUMAN)
    # Image on V1 (created first), video on V2 (created second).
    layer.add_image_clip("img1", 0, 90)              # 0..3s on V1
    layer.add_clip("vid1", 0.0, 3.0, timeline_start=0.0)  # 0..3s on V2
    pv = composite_preview_at_frame(core.project, 60, FPS_30)  # 2s
    # Both layers present.
    assert len(pv.visual_layers) == 2
    # Z-order: V1 (image) is lower, V2 (video) is higher.
    img_layer = next(l for l in pv.visual_layers if l.kind == "image")
    vid_layer = next(l for l in pv.visual_layers if l.kind == "video")
    assert img_layer.track_id == "v1"
    assert vid_layer.track_id == "v2"
    assert img_layer.layer_index < vid_layer.layer_index


# ---------------------------------------------------------------------------
# 5. track ordering is deterministic
# ---------------------------------------------------------------------------

def test_track_ordering_deterministic(tmp_path):
    """When the same set of clips exists on multiple tracks, the
    composite returns them in `project.timeline.tracks` order, NOT
    in some other order (clip_id, asset_id, etc.)."""
    project_dir, core = _new_image_project(tmp_path, n=2)
    layer = CommandLayer(core, who=Actor.HUMAN)
    # Add to V1, then V2 (created on demand by the allocator).
    layer.add_image_clip("img1", 0, 30)
    layer.add_image_clip("img2", 0, 30)  # overlaps img1 on V1; goes to V2
    pv = composite_preview_at_frame(core.project, 15, FPS_30)
    track_ids = [l.track_id for l in pv.visual_layers]
    # V1 was created first; V2 second; composite reflects creation order.
    assert track_ids == ["v1", "v2"]
    # Run composite twice — same result.
    pv2 = composite_preview_at_frame(core.project, 15, FPS_30)
    assert [l.track_id for l in pv2.visual_layers] == ["v1", "v2"]


# ---------------------------------------------------------------------------
# 6. subtitles appear at their frame ranges
# ---------------------------------------------------------------------------

def test_subtitles_in_composite(tmp_path):
    """A subtitle text clip on a text track. Its text is in
    composite.subtitle_texts when the playhead is in range, and
    absent when outside."""
    project_dir, core = _new_image_project(tmp_path, n=1)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_image_clip("img1", 0, 180)  # 0..6s
    sub = layer.add_subtitle("hello world", 1.0, 2.0, track_id="t1")
    # Frame 30 (1s) — in subtitle range.
    pv_in = composite_preview_at_frame(core.project, 30, FPS_30)
    assert "hello world" in pv_in.subtitle_texts
    # Frame 0 — before subtitle.
    pv_before = composite_preview_at_frame(core.project, 0, FPS_30)
    assert pv_before.subtitle_texts == []
    # Frame 60 (2s) — at subtitle end (half-open [1s, 2s) excludes 2s).
    pv_at_end = composite_preview_at_frame(core.project, 60, FPS_30)
    assert pv_at_end.subtitle_texts == []
    # Frame 90 (3s) — after subtitle.
    pv_after = composite_preview_at_frame(core.project, 90, FPS_30)
    assert pv_after.subtitle_texts == []


# ---------------------------------------------------------------------------
# 7. empty tracks do not affect the result
# ---------------------------------------------------------------------------

def test_empty_tracks_no_effect(tmp_path):
    """An empty track in the project does not appear in the
    composite. The visual_layers reflect only tracks with content."""
    project_dir, core = _new_image_project(tmp_path, n=1)
    layer = CommandLayer(core, who=Actor.HUMAN)
    # Add the image FIRST so it goes on v1 (the auto-named track).
    # Then add empty tracks v9/a9 — the allocator does NOT re-place
    # the image on them because the image's track_id is locked.
    layer.add_image_clip("img1", 0, 30)  # auto → v1
    # Manually create empty tracks.
    layer.add_track(TrackKind.VIDEO, "v9")
    layer.add_track(TrackKind.AUDIO, "a9")
    pv = composite_preview_at_frame(core.project, 15, FPS_30)
    # v9 and a9 are empty → no layers for them.
    track_ids = [l.track_id for l in pv.visual_layers]
    assert "v9" not in track_ids
    audio_track_ids = [l.track_id for l in pv.audio_layers]
    assert "a9" not in audio_track_ids


# ---------------------------------------------------------------------------
# HTTP endpoint: /preview/at_frame
# ---------------------------------------------------------------------------

def test_http_preview_at_frame_pure_image(tmp_path):
    """HTTP endpoint returns the composite JSON for the pure-image
    slice (sanlihe-slice-30s benchmark shape)."""
    project_dir, core = _new_image_project(tmp_path, n=3)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_image_clip("img1", 0, 30)
    layer.add_image_clip("img2", 30, 30)
    layer.add_subtitle("subtitle text", 0.5, 1.5, track_id="t1")
    core.save_state()
    app = create_app(project_dir, who=Actor.HUMAN)
    client = TestClient(app)
    # Sample at frame 15 (0.5s — image1 + subtitle).
    r = client.get("/preview/at_frame?frame=15")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["timeline_frame"] == 15
    assert data["is_black"] is False
    assert len(data["visual_layers"]) == 1
    layer_dict = data["visual_layers"][0]
    assert layer_dict["kind"] == "image"
    assert layer_dict["asset_id"] == "img1"
    assert layer_dict["source_frame"] == 0
    assert data["subtitle_texts"] == ["subtitle text"]
    # The fps field carries the project sequence fps.
    assert data["fps"] == {"num": 30, "den": 1}


def test_http_preview_at_frame_is_black_on_gap(tmp_path):
    project_dir, core = _new_image_project(tmp_path, n=1)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_image_clip("img1", 0, 30)  # 0..1s
    core.save_state()
    app = create_app(project_dir, who=Actor.HUMAN)
    client = TestClient(app)
    # Frame 60 is past the image (1s).
    r = client.get("/preview/at_frame?frame=60")
    assert r.status_code == 200
    data = r.json()
    assert data["is_black"] is True
    assert data["visual_layers"] == []
    assert data["audio_layers"] == []


# ---------------------------------------------------------------------------
# Backward compat: resolve_frame still works
# ---------------------------------------------------------------------------

def test_legacy_resolve_frame_still_works(tmp_path):
    """The legacy /frame/preview endpoint and resolve_frame function
    continue to work after GUI-03D's refactor. resolve_frame now
    delegates to composite_preview_at_frame."""
    project_dir, core = _add_video_project(tmp_path)
    layer = CommandLayer(core, who=Actor.HUMAN)
    layer.add_clip("vid1", 0.0, 5.0, timeline_start=0.0)
    core.save_state()
    app = create_app(project_dir, who=Actor.HUMAN)
    client = TestClient(app)
    r = client.get("/frame/preview?frame=60")
    assert r.status_code == 200
    data = r.json()
    # The legacy endpoint picks the first video layer as the "main" video.
    assert data["video"]["clip_id"] is not None
    assert data["video"]["source_frame"] == 60