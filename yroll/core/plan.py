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

GUI-03R4-R1: `layer_index` is assigned GLOBALLY across visual tracks
(in declared track order, hidden tracks skipped). Within a single
track, layers get sequential sub-indices. This guarantees V_k+1
renders strictly above V_k regardless of per-track clip counts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from yroll.core.manifest import Project, Track, TrackKind
from yroll.core.timebase import Rational
from yroll.core.timemap import TimeMap


# GUI-03R4-R1: KIND_RANK + numeric suffix sort. Used by
# `build_preview_plan` to assign globally-unique layer_index across
# visual tracks (V1 < V2 < ... < V10 in stacking order, regardless of
# the order they appear in tl.tracks). Note: images share VIDEO tracks
# per the asset_type → track_kinds policy; they participate in the
# same visual layer_index sequence.
_KIND_RANK: dict[str, int] = {
    TrackKind.TEXT.value: 0,
    TrackKind.SUBTITLE.value: 0,
    TrackKind.VIDEO.value: 1,
    TrackKind.AUDIO.value: 2,
}
_NUM_SUFFIX_RE = re.compile(r"(\d+)\s*$")


def _track_sort_key(track: Track) -> tuple[int, int, str]:
    """Stable visual-stack ordering: kind first (text/video/audio),
    then natural-numeric suffix of track_id, then lexical for tie-
    break. Same rule as Timeline.tsx (KIND_RANK + trackKey)."""
    kind_rank = _KIND_RANK.get(track.kind.value, 9)
    m = _NUM_SUFFIX_RE.search(track.track_id)
    n = int(m.group(1)) if m else 9999
    return (kind_rank, n, track.track_id)


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

    GUI-03R4-R1: `layer_index` is assigned GLOBALLY across all visual
    tracks (in KIND_RANK + numeric-suffix order). Hidden tracks are
    SKIPPED entirely (their layers never appear in the composite).
    Text/SUBTITLE tracks contribute only to `subtitle_texts_by_range`,
    not to `plan.tracks`. Audio tracks remain in `plan.tracks` with
    per-track `layer_index` (audio sync doesn't use z-index).
    """
    if fps is None:
        fps = project.sequence.fps
    revision = 0
    ui_status = getattr(project, "ui_status", None)
    if ui_status is not None and getattr(ui_status, "base_revision", None) is not None:
        revision = ui_status.base_revision
    plan = PreviewPlan(
        project_revision=revision,
        timeline_id=timeline_id,
        fps=fps,
    )
    timeline = project.get_timeline(timeline_id)
    if timeline is None:
        # Unknown timeline → empty plan.
        return plan

    # GUI-03R4-R1: pre-compute the layer_index BASE for each visual
    # track, in the visual-stack order (KIND_RANK + numeric suffix).
    # The base is the count of all visual layers contributed by tracks
    # that come EARLIER in the stack order. Within each track, layers
    # are sorted by timeline_start_frame and assigned sequential
    # sub-indices starting from the base. Hidden tracks are skipped
    # entirely — their layers never appear in the composite.
    visual_track_order = sorted(
        (t for t in timeline.tracks
         if not t.hidden
         and t.kind == TrackKind.VIDEO),
        key=_track_sort_key,
    )
    track_layer_base: dict[str, int] = {}
    running = 0
    for t in visual_track_order:
        n = _count_visual_layers(t, project, fps)
        track_layer_base[t.track_id] = running
        running += n

    # Phase 2: iterate ALL tracks (including text and audio) so text
    # layers still feed subtitle_texts_by_range and audio tracks stay
    # in plan.tracks for sync. Hidden tracks contribute nothing.
    for track in timeline.tracks:
        if track.hidden:
            # Hidden tracks are excluded from the composite entirely.
            continue
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
            layers.append(PreviewLayer(
                track_id=track.track_id,
                layer_index=0,  # re-stamped below per track
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
        # Sort layers by timeline_start_frame within the track.
        layers.sort(key=lambda l: l.timeline_start_frame)
        # Visual tracks: layer_index is globally unique (track base
        # + intra-track offset). Audio tracks: per-track indices
        # (audio doesn't stack visually).
        if track.kind == TrackKind.VIDEO:
            base = track_layer_base.get(track.track_id, 0)
            for i, l in enumerate(layers):
                l.layer_index = base + i
        else:
            for i, l in enumerate(layers):
                l.layer_index = i
        plan.tracks.append(layers)
    return plan


def _count_visual_layers(track: Track, project: Project,
                          fps: Rational) -> int:
    """Count how many layers `track` will contribute to the preview
    plan. Used to pre-compute `track_layer_base` so visual layer_index
    values are globally unique across all visual tracks (in visual-
    stack order)."""
    n = 0
    for cid in track.clip_ids:
        c = project.clips.get(cid)
        if c is None:
            continue
        asset = next((a for a in project.assets
                      if a.asset_id == c.asset_id), None)
        if asset is None:
            continue
        asset_type = asset.type.value
        if asset_type == "image":
            n += 1
        elif asset.source_fps is not None:
            # Video: source_fps must be set; otherwise the layer would
            # be skipped by Phase 2 (per GUI-02.3 invariant).
            n += 1
        # else: video without source_fps — Phase 2 skips it, so it
        # does not consume a layer_index slot.
    return n


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
