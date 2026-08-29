"""GUI-03D.1: L1 Preview Plan — cached snapshot of all clip ranges.

The GUI caches a `PreviewPlan` keyed by `(project_revision, timeline_id)`.
During playback, the FrameClock drives the current TimelineFrame; the
plan is queried LOCALLY to find the active layer on each track. The
asset's source timebase (already cached per-layer) is used to compute
the media currentTime. NO HTTP per frame.

The plan is invalidated by ANY Core mutation that bumps the project
revision (the plan endpoint embeds the revision; the GUI compares it
against /ui/status). A single-frame seek does NOT re-fetch the plan
(it's still valid for the same revision); the active layer resolves
locally via the cached plan.

The plan endpoint is orthogonal to the existing
`composite_preview_at_frame` endpoint:
  * /preview/at_frame   — single-frame resolution, canonical Core API
  * /preview/plan       — full structural snapshot for caching
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from yroll.core.manifest import Project, Track, TrackKind
from yroll.core.timebase import Rational
from yroll.core.timemap import TimeMap


@dataclass
class PreviewLayer:
    """One clip's structural data for the L1 preview plan.

    `source_start_frame` and `source_end_frame` are the SourceFrame
    integers that correspond to the clip's `timeline_start_frame`
    and `timeline_end_frame`. They are precomputed by Core (via
    TimeMap) so the GUI can interpolate locally without per-frame
    HTTP.

    For image clips: source_start_frame == source_end_frame == 0
    and source_fps is None. The image renders statically for the
    full TimelineFrameRange.

    For video/audio clips: source_fps is the asset's source FPS.
    The GUI computes source_seconds = source_frame / source_fps
    when writing the HTMLMediaElement.currentTime.
    """
    track_id: str
    layer_index: int              # z-order (0 = bottom, higher = on top)
    kind: str                     # "video" | "image" | "audio"
    clip_id: str
    asset_id: str
    asset_type: str
    asset_path: str
    # TimelineFrame range this layer covers (half-open).
    timeline_start_frame: int
    timeline_end_frame: int
    # SourceFrame range corresponding to the timeline range.
    # For image: 0..1. For video/audio: mapped via TimeMap.
    source_start_frame: int = 0
    source_end_frame: int = 0
    # Asset's source FPS (None for image). GUI uses to compute
    # source_seconds for HTML media currentTime.
    source_fps: Optional[Rational] = None
    # Ken Burns / transform.
    transform: dict = field(default_factory=dict)


@dataclass
class PreviewPlan:
    """Snapshot of (project_revision, timeline_id) at one moment.

    The plan is keyed by (project_revision, timeline_id). Any Core
    mutation that bumps the revision invalidates the cached plan.
    """
    project_revision: int
    timeline_id: str
    fps: Rational
    # Per-track lists of PreviewLayer, sorted by timeline_start_frame.
    # The order of the list IS the z-order: index 0 = bottom, last = top.
    tracks: list[list[PreviewLayer]] = field(default_factory=list)
    # Active subtitle strings keyed by [timeline_start_frame, timeline_end_frame).
    # The GUI picks the most recent active subtitle for rendering.
    subtitle_texts_by_range: list[tuple[tuple[int, int], str]] = field(
        default_factory=list,
    )


def _timeline_range_frames(c, fps):
    s = round(c.timeline_range.start * fps.num / fps.den)
    e = round(c.timeline_range.end * fps.num / fps.den)
    return s, e


def build_preview_plan(project: Project, timeline_id: str = "main",
                       fps: Optional[Rational] = None) -> PreviewPlan:
    """Build a PreviewPlan for the project's current state.

    The plan embeds `project.sequence.project_revision` (or 0) so
    the GUI can detect staleness against /ui/status without re-fetching
    the whole project.
    """
    if fps is None:
        fps = project.sequence.fps
    # ProjectRevision lives on the Project's ui_status or the
    # /ui/status endpoint. The plan embeds the current revision so
    # the GUI can detect staleness.
    revision = 0
    ui_status = getattr(project, "ui_status", None)
    if ui_status is not None and getattr(ui_status, "base_revision", None) is not None:
        revision = ui_status.base_revision
    # Fall back: read the /project endpoint's sequence.project_revision
    # via Project.model_dump if available. Project doesn't have a
    # project_revision field directly; the HTTP layer tracks it on
    # /ui/status. For the plan, the revision is informational — the
    # GUI checks /ui/status separately for invalidation.
    plan = PreviewPlan(
        project_revision=revision,
        timeline_id=timeline_id,
        fps=fps,
    )
    # Find the target timeline. ProjectCore has exactly one
    # `timeline`; for multi-timeline support (GUI-03E), iterate.
    timeline = project.timeline
    layer_index = 0
    for track in timeline.tracks:
        layers: list[PreviewLayer] = []
        for cid in track.clip_ids:
            c = project.clips.get(cid)
            if c is None:
                continue
            asset = next((a for a in project.assets
                          if a.asset_id == c.asset_id), None)
            tl_s, tl_e = _timeline_range_frames(c, fps)
            if asset is None:
                # Subtitle/text clip: no asset; record as subtitle range.
                if track.kind in (TrackKind.TEXT, TrackKind.SUBTITLE):
                    text = c.context.get("text", "") or ""
                    if text:
                        plan.subtitle_texts_by_range.append(
                            ((tl_s, tl_e), text)
                        )
                continue
            asset_type = asset.type.value
            is_image = (asset_type == "image")
            if is_image:
                # Image: 1 source frame (whole clip is 1 frame's worth).
                # We use [0, 1) so the GUI's source_frame math works
                # (timeline_frame=tl_s → source_frame=0).
                src_s, src_e = 0, 1
                src_fps = None
            else:
                # Video / audio: TimeMap for FPS-aware conversion.
                src_fps = asset.source_fps
                if src_fps is None:
                    # Skip — per GUI-02.3 invariant, never silently
                    # fall back to sequence fps.
                    continue
                tm = TimeMap.for_clip(c, fps, src_fps)
                src_s = tm.source_from_timeline(tl_s)
                src_e = tm.source_from_timeline(tl_e - 1) + 1
                # Use the full half-open range via the source's
                # first/last frames. tm.source_from_timeline is
                # monotonic; we round to integer source frames.
            layers.append(PreviewLayer(
                track_id=track.track_id,
                layer_index=0,  # set below
                kind=asset_type,
                clip_id=cid,
                asset_id=asset.asset_id,
                asset_type=asset_type,
                asset_path=asset.path,
                timeline_start_frame=tl_s,
                timeline_end_frame=tl_e,
                source_start_frame=src_s,
                source_end_frame=src_e,
                source_fps=src_fps,
                transform=dict(c.transform or {}),
            ))
        # Sort layers by timeline_start_frame; assign layer_index.
        layers.sort(key=lambda l: l.timeline_start_frame)
        for i, l in enumerate(layers):
            l.layer_index = i
        # Only add non-empty tracks to the plan (saves the GUI from
        # iterating empty tracks). But preserve the track ORDER for
        # z-order semantics — empty tracks just have [].
        plan.tracks.append(layers)
    return plan


def active_layer_at(track_layers: list[PreviewLayer],
                    timeline_frame: int) -> Optional[PreviewLayer]:
    """Return the active layer on a track at the given TimelineFrame.

    The track's layers are assumed sorted by timeline_start_frame.
    We walk from the end (most-recently-added layers first) so a
    later clip whose half-open range starts at `timeline_frame`
    correctly wins over an earlier clip whose range ends at
    `timeline_frame` (half-open).
    """
    for layer in reversed(track_layers):
        if layer.timeline_start_frame <= timeline_frame < layer.timeline_end_frame:
            return layer
    return None


def source_frame_at(layer: PreviewLayer,
                    timeline_frame: int) -> int:
    """Compute the SourceFrame integer at `timeline_frame` for one layer.

    For image: always 0 (image has 1 source frame; rendered statically).
    For video/audio: linear interpolation of source_start..end
    across timeline_start..end. Both endpoints and the timeline_frame
    are integers; the result is rounded to the nearest integer.
    """
    if layer.kind == "image":
        return 0
    tl_range = layer.timeline_end_frame - layer.timeline_start_frame
    if tl_range <= 0:
        return layer.source_start_frame
    src_range = layer.source_end_frame - layer.source_start_frame
    return layer.source_start_frame + round(
        (timeline_frame - layer.timeline_start_frame) * src_range / tl_range
    )
