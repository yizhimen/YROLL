"""L1 Local Composite tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.local_composite import (
    build_ffmpeg_segment_cmds, resolve_composite_window,
)
from yroll.core.manifest import Actor, TrackKind
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational


FPS = Rational(30, 1)


def _build(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "l1-test")
    # GUI-02.3: assets declare their source timebase so frame_preview
    # can resolve source frames without falling back to sequence fps.
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="/tmp/v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=60.0),
        source_fps=FPS, source_is_cfr=True, source_frame_count=1800,
    ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)  # video 0..10s
    cmd.add_track(TrackKind.TEXT, "t1")
    cmd.add_clip("", 0.0, 3.0, timeline_start=4.0, track_id="t1")
    cmd.core.project.clips[list(cmd.core.project.clips)[-1]].context["text"] = "sub"
    core.save_state()
    return core


def test_window_resolves_frames_around_playhead(tmp_path):
    core = _build(tmp_path)
    out = tmp_path / "preview.png"
    win = resolve_composite_window(core.project, playhead_frame=200,
                                    half_window=5, fps=FPS,
                                    output_path=out)
    # start = 195, end = 206 (exclusive)
    assert win.start_frame == 195
    assert win.end_frame == 206
    assert len(win.frames) == 11
    # 200 is at ~6.67s: video 0..10s = frame 0..300, so all frames have video
    for cf in win.frames:
        assert cf.video_clip_id is not None
        assert cf.video_source_frame is not None


def test_window_subtitle_appears_at_correct_frames(tmp_path):
    core = _build(tmp_path)
    out = tmp_path / "preview.png"
    # subtitle is at timeline 4..7s = frame 120..210
    win = resolve_composite_window(core.project, playhead_frame=180,
                                    half_window=10, fps=FPS,
                                    output_path=out)
    # frame 170 → subtitle appears
    assert any("sub" in cf.subtitle_texts for cf in win.frames if cf.timeline_frame == 170)
    # frame 220 → after subtitle end
    assert all(not cf.subtitle_texts for cf in win.frames if cf.timeline_frame == 220)


def test_window_clamped_at_zero(tmp_path):
    core = _build(tmp_path)
    out = tmp_path / "preview.png"
    win = resolve_composite_window(core.project, playhead_frame=3,
                                    half_window=20, fps=FPS,
                                    output_path=out)
    assert win.start_frame == 0  # clamped


def test_window_duration(tmp_path):
    core = _build(tmp_path)
    out = tmp_path / "preview.png"
    win = resolve_composite_window(core.project, playhead_frame=300,
                                    half_window=30, fps=FPS,
                                    output_path=out)
    # 61 frames @ 30fps = ~2.033s
    assert win.duration_seconds() == pytest.approx(2.033, abs=0.01)


def test_ffmpeg_segment_cmds_have_video_source(tmp_path):
    core = _build(tmp_path)
    out = tmp_path / "preview.png"
    win = resolve_composite_window(core.project, playhead_frame=200,
                                    half_window=2, fps=FPS,
                                    output_path=out)
    cmds = build_ffmpeg_segment_cmds(win)
    # Each command should reference the asset and seek by source frame time
    assert len(cmds) >= 1
    for cmd in cmds:
        assert cmd[0] == "ffmpeg"
        assert "/tmp/v.mp4" in cmd
        assert "-frames:v" in cmd
        assert "1" in cmd
