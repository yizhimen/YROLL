"""L0 Frame Preview tests."""
from __future__ import annotations

from pathlib import Path

from yroll.core.commands import CommandLayer
from yroll.core.frame_preview import resolve_frame
from yroll.core.manifest import Actor, TrackKind
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational


FPS_30 = Rational(30, 1)


def _build(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "frame-preview-test")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="/tmp/v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=60.0),
    ))
    core.project.assets.append(Asset(
        asset_id="a2", type=AssetType.AUDIO, path="/tmp/v.mp3",
        identity=AssetIdentity(md5="y" * 32, size_bytes=1, duration_sec=60.0),
    ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)         # video 0..10s
    cmd.add_track(TrackKind.AUDIO, "a1")
    cmd.add_clip("a2", 0.0, 10.0, timeline_start=0.0,
                 track_id="a1")                                 # audio 0..10s
    cmd.add_track(TrackKind.TEXT, "t1")
    cmd.add_clip("", 0.0, 3.0, timeline_start=2.0, track_id="t1")  # sub 2..5s
    cmd.core.project.clips[list(cmd.core.project.clips)[-1]].context["text"] = "hello world"
    core.save_state()
    return core


def test_resolve_inside_video(tmp_path):
    core = _build(tmp_path)
    pv = resolve_frame(core.project, timeline_frame=60, fps=FPS_30)  # 2s
    assert pv.video_clip_id is not None
    assert pv.video_source_frame == 60  # at 2s timeline, source 2s @ 30fps = frame 60
    assert pv.video_asset_path == "/tmp/v.mp4"
    # Audio present
    assert len(pv.audio_clip_ids) == 1
    # Subtitle present (2..5s = frame 60..150, frame 60 is start)
    assert "hello world" in pv.subtitle_texts


def test_resolve_outside_video_is_black(tmp_path):
    core = _build(tmp_path)
    pv = resolve_frame(core.project, timeline_frame=1500, fps=FPS_30)  # 50s, no clip
    assert pv.is_black()


def test_resolve_in_subtitle_only(tmp_path):
    core = _build(tmp_path)
    pv = resolve_frame(core.project, timeline_frame=200, fps=FPS_30)  # ~6.6s
    # Video ends at 10s = frame 300, so still in video
    # Subtitle ends at 5s = frame 150, so frame 200 has NO subtitle
    assert pv.video_clip_id is not None
    assert pv.subtitle_texts == []


def test_resolve_respects_speed(tmp_path):
    """2x speed clip: 30 timeline frames = 60 source frames."""
    core = ProjectCore.create(tmp_path, "speed-test")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="/tmp/v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=60.0),
    ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)
    cmd.set_speed(list(cmd.core.project.clips.values())[0].clip_id, 2.0)

    pv = resolve_frame(core.project, timeline_frame=60, fps=FPS_30)  # 2s timeline
    # speed=2: source = clip_local * 2 = 60 timeline_frame - 0 (start) = 60 clip-frames
    # source = 60 * 2 = 120
    assert pv.video_source_frame == 120


def test_resolve_frame_half_open(tmp_path):
    """Frame exactly at clip.end should NOT cover (half-open)."""
    core = _build(tmp_path)
    # clip ends at frame 300 (10s). Frame 300 should be black on video track.
    pv = resolve_frame(core.project, timeline_frame=300, fps=FPS_30)
    assert pv.video_clip_id is None
