"""L0 Frame Preview (v0.2 §30): single-frame accurate preview data.

Given a timeline frame, return everything needed to render it accurately:
- Which video clip (if any) covers this frame and its source frame
- Which audio clip covers this frame and the playback offset
- Which subtitle (text track) clips are visible at this frame
- A pre-fetched asset URL for the video source (asset.path) — actual
  rendering is the GUI's job; we just resolve the data.

All inputs/outputs in canonical frames. Project-level fps used.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from yroll.core.manifest import Project, TrackKind
from yroll.core.timebase import FrameTime, Rational
from yroll.core.timemap import TimeMap


@dataclass
class FramePreview:
    """Result of resolving one timeline frame."""
    timeline_frame: int
    fps: Rational

    # Video
    video_clip_id: Optional[str] = None
    video_source_frame: Optional[int] = None
    video_asset_path: Optional[str] = None
    video_track_id: Optional[str] = None

    # Audio
    audio_clip_ids: list[str] = field(default_factory=list)
    audio_source_frames: list[int] = field(default_factory=list)
    audio_asset_paths: list[str] = field(default_factory=list)

    # Subtitles
    subtitle_clip_ids: list[str] = field(default_factory=list)
    subtitle_texts: list[str] = field(default_factory=list)

    def is_black(self) -> bool:
        """True if no clip covers this frame."""
        return (self.video_clip_id is None
                and not self.audio_clip_ids
                and not self.subtitle_clip_ids)


def resolve_frame(project: Project, timeline_frame: int,
                  fps: Rational) -> FramePreview:
    """Resolve what covers a single timeline frame."""
    pv = FramePreview(timeline_frame=timeline_frame, fps=fps)

    for track in project.timeline.tracks:
        if track.kind == TrackKind.VIDEO:
            for cid in track.clip_ids:
                c = project.clips.get(cid)
                if c is None:
                    continue
                # Clip is half-open [start, end) in seconds.
                tl_s_f = FrameTime.from_seconds(c.timeline_range.start, fps).frame
                tl_e_f = FrameTime.from_seconds(c.timeline_range.end, fps).frame
                if tl_s_f <= timeline_frame < tl_e_f:
                    pv.video_clip_id = cid
                    pv.video_track_id = track.track_id
                    tm = TimeMap.for_clip(c, fps)
                    # Convert timeline_frame → clip-local → source
                    clip_frame = tm.clip_from_timeline(timeline_frame)
                    pv.video_source_frame = tm.source_from_clip(clip_frame)
                    asset = next((a for a in project.assets
                                  if a.asset_id == c.asset_id), None)
                    pv.video_asset_path = asset.path if asset else None
                    break  # one video wins on each track; first match
        elif track.kind == TrackKind.AUDIO:
            for cid in track.clip_ids:
                c = project.clips.get(cid)
                if c is None:
                    continue
                tl_s_f = FrameTime.from_seconds(c.timeline_range.start, fps).frame
                tl_e_f = FrameTime.from_seconds(c.timeline_range.end, fps).frame
                if tl_s_f <= timeline_frame < tl_e_f:
                    tm = TimeMap.for_clip(c, fps)
                    clip_frame = tm.clip_from_timeline(timeline_frame)
                    src_frame = tm.source_from_clip(clip_frame)
                    pv.audio_clip_ids.append(cid)
                    pv.audio_source_frames.append(src_frame)
                    asset = next((a for a in project.assets
                                  if a.asset_id == c.asset_id), None)
                    pv.audio_asset_paths.append(asset.path if asset else "")
        elif track.kind == TrackKind.TEXT:
            for cid in track.clip_ids:
                c = project.clips.get(cid)
                if c is None:
                    continue
                tl_s_f = FrameTime.from_seconds(c.timeline_range.start, fps).frame
                tl_e_f = FrameTime.from_seconds(c.timeline_range.end, fps).frame
                if tl_s_f <= timeline_frame < tl_e_f:
                    pv.subtitle_clip_ids.append(cid)
                    pv.subtitle_texts.append(
                        c.context.get("text", "") or "")
    return pv


def preview_range(project: Project, start_frame: int, end_frame: int,
                  fps: Rational) -> list[FramePreview]:
    """Resolve every frame in [start_frame, end_frame) — for fast seek."""
    return [resolve_frame(project, f, fps)
            for f in range(start_frame, end_frame)]
