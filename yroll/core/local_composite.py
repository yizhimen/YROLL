"""YROLL L1 Local Composite (v0.2 §30, §33): render a small window around playhead.

L1 differs from L2 (full render):
- L2: render the whole timeline. Used for export / final check.
- L1: render only ±N frames around the playhead. Used during editing
  for instant feedback without redoing the whole project.

This module provides:
- resolve_composite_window(project, playhead_frame, half_window, fps)
  → returns per-frame source info needed for ffmpeg invocation.
- build_ffmpeg_concat_cmd(window, output_path, width, fps)
  → builds an ffmpeg command that pulls the right segment from each
  source asset, applies the per-clip speed mapping, and concatenates
  into one preview mp4.

The actual ffmpeg invocation is the caller's job (we don't shell out
from this module — kept pure so it's testable without ffmpeg).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from yroll.core.frame_preview import resolve_frame
from yroll.core.manifest import Project, TrackKind
from yroll.core.timebase import FrameTime, Rational
from yroll.core.timemap import TimeMap


@dataclass
class CompositeFrame:
    """One timeline frame in the local composite window."""
    timeline_frame: int
    video_clip_id: Optional[str] = None
    video_source_frame: Optional[int] = None
    video_asset_path: Optional[str] = None
    subtitle_texts: list[str] = field(default_factory=list)


@dataclass
class CompositeWindow:
    """All data needed to render ±half_window frames around playhead."""
    start_frame: int
    end_frame: int           # half-open [start, end)
    fps: Rational
    frames: list[CompositeFrame]
    output_path: Path

    def duration_seconds(self) -> float:
        return (self.end_frame - self.start_frame) / self.fps.as_float()


def resolve_composite_window(project: Project, playhead_frame: int,
                              half_window: int, fps: Rational,
                              output_path: Path) -> CompositeWindow:
    """Resolve all frames in [playhead - half_window, playhead + half_window).

    Pure: no rendering, just metadata. The GUI/CLI then runs ffmpeg.
    """
    start = max(0, playhead_frame - half_window)
    end = playhead_frame + half_window + 1
    frames: list[CompositeFrame] = []
    for f in range(start, end):
        pv = resolve_frame(project, f, fps)
        cf = CompositeFrame(
            timeline_frame=f,
            video_clip_id=pv.video_clip_id,
            video_source_frame=pv.video_source_frame,
            video_asset_path=pv.video_asset_path,
            subtitle_texts=list(pv.subtitle_texts),
        )
        frames.append(cf)
    return CompositeWindow(start_frame=start, end_frame=end,
                           fps=fps, frames=frames, output_path=output_path)


def build_ffmpeg_segment_cmds(window: CompositeWindow) -> list[list[str]]:
    """For each frame in the window, return an ffmpeg command list that
    extracts exactly that one source frame. The caller then concats.

    Output frames are named frame_NNNN.png in a temp dir; the caller is
    responsible for the temp dir.

    Returns one command per frame that has a video source.
    """
    cmds: list[list[str]] = []
    for cf in window.frames:
        if cf.video_source_frame is None or cf.video_asset_path is None:
            continue
        out = f"{window.output_path}_frame_{cf.timeline_frame:08d}.png"
        # -ss before -i: fast seek (keyframe-aware)
        # -frames:v 1: grab exactly one frame
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{cf.video_source_frame / window.fps.as_float():.6f}",
            "-i", cf.video_asset_path,
            "-frames:v", "1",
            out,
        ]
        cmds.append(cmd)
    return cmds
