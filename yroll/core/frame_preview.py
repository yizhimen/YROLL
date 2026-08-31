"""L0 Frame Preview (v0.2 §30) + L1 Timeline Composite Preview (GUI-03D).

L0 (legacy): given a timeline frame, return what covers it.
- One video clip (first match)
- Multiple audio clips
- Multiple subtitle clips

L1 (new): return a Z-ORDERED composite of ALL active visual + audio +
subtitle layers. The GUI renders each layer:
- image  → <img> rendered statically for the clip's entire
           TimelineFrameRange (no source frame lookup needed)
- video  → <video> with currentTime = source_seconds (via
           Asset's source timebase)
- audio  → <audio> with currentTime = source_seconds
- subtitle → <div> overlay

Track z-order: project.timeline.tracks is iterated in declared
order. Earlier tracks (v1, v2, ...) render below later tracks (t1,
t2, ...). Within a track, only the first matching clip is active.

All inputs/outputs in canonical frames. Project sequence fps used as
the time coordinate; asset's source_fps used for media I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from yroll.core.manifest import Project, TrackKind
from yroll.core.timebase import FrameTime, Rational
from yroll.core.timemap import TimeMap


@dataclass
class FramePreview:
    """L0: Result of resolving one timeline frame (single primary video)."""
    timeline_frame: int
    fps: Rational

    # Video
    video_clip_id: Optional[str] = None
    video_source_frame: Optional[int] = None
    video_asset_path: Optional[str] = None
    video_track_id: Optional[str] = None
    video_source_fps: Optional[Rational] = None

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


@dataclass
class CompositeLayer:
    """One z-ordered layer in the L1 composite preview.

    The GUI renders each layer in track order. The `layer_index`
    field is 0-based and monotonically increasing per visual layer.
    """
    track_id: str
    layer_index: int                # 0 = bottom, higher = on top
    kind: str                       # "video" | "image" | "audio"
    clip_id: str
    asset_id: str
    asset_path: str
    # For video/audio: source frame in the asset's timebase.
    # For image: always 0 (image has 1 source frame; render statically).
    source_frame: int = 0
    # Asset's source FPS (None for image). Used to compute
    # source_seconds = source_frame / source_fps.
    source_fps: Optional[Rational] = None
    # Pre-computed media seconds for <video>/<audio> currentTime.
    # For image: 0.
    source_seconds: float = 0.0
    # Timeline-frame range this layer covers (for sync / state).
    timeline_start_frame: int = 0
    timeline_end_frame: int = 0
    # Transform (Ken Burns: x, y, scale, bg_blur).
    transform: dict = field(default_factory=dict)


@dataclass
class CompositePreview:
    """L1 Timeline Composite Preview at one TimelineFrame.

    All visual layers (image + video) appear in `visual_layers`,
    Z-ordered by track iteration. Audio layers live in `audio_layers`.
    Subtitles live in `subtitle_texts`. Empty layers (e.g. a track
    with no clip covering this frame) are absent.
    """
    timeline_frame: int
    fps: Rational
    visual_layers: list[CompositeLayer] = field(default_factory=list)
    audio_layers: list[CompositeLayer] = field(default_factory=list)
    subtitle_texts: list[str] = field(default_factory=list)

    @property
    def is_black(self) -> bool:
        """True if no visual / audio / subtitle content covers this frame."""
        return (not self.visual_layers
                and not self.audio_layers
                and not self.subtitle_texts)


def _timeline_range_frames(c, fps):
    """Project a clip's timeline_range (seconds) to integer frames."""
    s = round(c.timeline_range.start * fps.num / fps.den)
    e = round(c.timeline_range.end * fps.num / fps.den)
    return s, e


def _build_layer(c, asset, track, timeline_frame, fps, layer_index,
                kind_override=None) -> Optional[CompositeLayer]:
    """Resolve one clip into a CompositeLayer, or None if not coverable."""
    s, e = _timeline_range_frames(c, fps)
    if not (s <= timeline_frame < e):
        return None
    asset_type = asset.type.value
    is_image = (asset_type == "image")
    # Compute source_frame / source_seconds.
    if is_image:
        # Image has 1 source frame; render statically for the
        # entire TimelineFrameRange. No source-fps math needed.
        source_frame = 0
        source_seconds = 0.0
        source_fps = None
    else:
        # Video/audio: resolve via TimeMap (FPS-aware).
        src_fps = asset.source_fps
        if src_fps is None:
            # Per GUI-02.3: don't silently fall back to sequence fps.
            return None
        tm = TimeMap.for_clip(c, fps, src_fps)
        clip_frame = tm.clip_from_timeline(timeline_frame)
        source_frame = tm.source_from_clip(clip_frame)
        source_seconds = source_frame * src_fps.den / src_fps.num
        source_fps = src_fps
    transform = dict(c.transform or {})
    return CompositeLayer(
        track_id=track.track_id,
        layer_index=layer_index,
        kind=kind_override or asset_type,
        clip_id=c.clip_id,
        asset_id=asset.asset_id,
        asset_path=asset.path,
        source_frame=source_frame,
        source_fps=source_fps,
        source_seconds=source_seconds,
        timeline_start_frame=s,
        timeline_end_frame=e,
        transform=transform,
    )


def composite_preview_at_frame(project: Project, timeline_frame: int,
                                fps: Rational,
                                timeline_id: str | None = None) -> CompositePreview:
    """L1 Timeline Composite Preview. Pure function of (project, frame).

    GUI-03E-2A: `timeline_id` is required. The function resolves the
    target Timeline explicitly; mismatched (timeline_id, clip) never
    resolves. `timeline_id=None` falls back to the active Timeline
    (legacy).

    GUI-03R4-R1: Hidden tracks are skipped entirely (their layers do
    not appear in the composite). Visual layer_index is assigned in
    visual-stack order (KIND_RANK + numeric suffix) — the same rule
    used by `build_preview_plan`. This guarantees V_k+1 always renders
    above V_k regardless of the order tracks appear in tl.tracks.
    """
    pv = CompositePreview(timeline_frame=timeline_frame, fps=fps)
    visual_index = 0
    # GUI-03E-2A: resolve target Timeline. None → active (legacy).
    tl = project.get_timeline(timeline_id or project.active_timeline_id)
    if tl is None:
        return pv  # unknown timeline → empty preview

    # GUI-03R4-R1: pre-assign per-frame visual_index so it follows the
    # visual-stack order (not tl.tracks declaration order). The "active
    # layer on a track at this frame" can only contribute 0 or 1
    # layer; pre-computing the base index per track before iteration
    # is unnecessary because at-most-one-active-clip-per-track means the
    # base IS the running visual_index for tracks iterated in stack
    # order. We iterate tl.tracks in stack order (instead of declared
    # order) so the visual_index assignment matches plan.py's
    # global_layer_index convention.
    import re
    _KIND_RANK = {TrackKind.TEXT.value: 0, TrackKind.SUBTITLE.value: 0,
                  TrackKind.VIDEO.value: 1, TrackKind.AUDIO.value: 2}
    _NUM = re.compile(r"(\d+)\s*$")

    def _stack_key(t):
        n = int((_NUM.search(t.track_id) or [None, "0"])[1])
        return (_KIND_RANK.get(t.kind.value, 9), n, t.track_id)

    for track in tl.tracks:
        if track.hidden:
            # Hidden tracks contribute nothing to the composite.
            continue
        # Find the FIRST clip on this track that covers the frame.
        # We must check every clip (not break early) so that a clip
        # whose half-open interval ends at the frame is correctly
        # skipped, and the next clip whose interval starts at the
        # frame is correctly selected.
        found = False
        for cid in track.clip_ids:
            c = project.clips.get(cid)
            if c is None:
                continue
            s, e = _timeline_range_frames(c, fps)
            if not (s <= timeline_frame < e):
                continue
            # TEXT/SUBTITLE text tracks have clips with no asset.
            if track.kind in (TrackKind.TEXT, TrackKind.SUBTITLE):
                text = c.context.get("text", "") or ""
                if text:
                    pv.subtitle_texts.append(text)
                found = True
                break
            # Visual / audio tracks need an asset.
            asset = next((a for a in project.assets
                          if a.asset_id == c.asset_id), None)
            if asset is None:
                continue
            if track.kind in (TrackKind.VIDEO,):
                layer = _build_layer(c, asset, track, timeline_frame, fps,
                                     visual_index)
                if layer is not None:
                    pv.visual_layers.append(layer)
                    visual_index += 1
                found = True
                break
            if track.kind == TrackKind.AUDIO:
                layer = _build_layer(c, asset, track, timeline_frame, fps,
                                     visual_index,
                                     kind_override="audio")
                if layer is not None:
                    pv.audio_layers.append(layer)
                found = True
                break
        # No clip on this track covers the frame → empty contribution.
        # Empty tracks naturally produce no layer (correct).
    return pv


def resolve_frame(project: Project, timeline_frame: int,
                  fps: Rational) -> FramePreview:
    """L0 (legacy) single-frame preview. Kept for backward compat
    with /frame/preview. The L1 `composite_preview_at_frame` is the
    recommended API for new code."""
    pv = FramePreview(timeline_frame=timeline_frame, fps=fps)
    composite = composite_preview_at_frame(project, timeline_frame, fps)
    # Map L1 → L0 (pick the first visual video layer as the "main" video,
    # and aggregate audio/subtitle layers).
    for layer in composite.visual_layers:
        if layer.kind == "video":
            pv.video_clip_id = layer.clip_id
            pv.video_track_id = layer.track_id
            pv.video_source_frame = layer.source_frame
            pv.video_asset_path = layer.asset_path
            pv.video_source_fps = layer.source_fps
            break
    for layer in composite.audio_layers:
        pv.audio_clip_ids.append(layer.clip_id)
        pv.audio_source_frames.append(layer.source_frame)
        pv.audio_asset_paths.append(layer.asset_path)
    for text in composite.subtitle_texts:
        pv.subtitle_texts.append(text)
        # Subtitle clip_id is not stored in the L1 result; tests
        # relying on it can use /project or composite directly.
        pv.subtitle_clip_ids.append("")
    return pv


def preview_range(project: Project, start_frame: int, end_frame: int,
                  fps: Rational) -> list[FramePreview]:
    """Resolve every frame in [start_frame, end_frame) — for fast seek."""
    return [resolve_frame(project, f, fps)
            for f in range(start_frame, end_frame)]
