"""YROLL Time Mapping (P0-02 + GUI-02.3): source_frame ↔ clip_frame ↔ timeline_frame.

Three-frame-space mapping, the foundation for Frame-native editing:

  SourceFrame (in source_fps)
        │  (source_range)
        ▼
  ClipFrame (clip-local, also in source_fps)
        │  (timeline_position, speed, sequence_fps)
        ▼
  TimelineFrame (in sequence_fps)

GUI-02.3 invariant: source_fps and sequence_fps are EXPLICIT and
distinct. TimeMap NEVER assumes source_fps == sequence_fps. The
factory `TimeMap.for_clip` requires both; any code that wants to
build a TimeMap must declare both FPS values. The two spaces are
tagged on every returned FrameRange — `timeline_from_source_range`
returns a FrameRange tagged with `sequence_fps`,
`source_from_timeline_range` returns one tagged with `source_fps`.

Why this matters:
- Agent asks: "what timeline frame is source frame 1200 of asset A?"
- Old code recomputed (s - sr.start) / clip.speed inline, repeated
  in generate_subtitles, search-transcripts, ripple_delete, ...
- New code asks TimeMap once: `tm.timeline_from_source(1200)`.

All inputs/outputs are canonical frames (FrameTime / FrameRange).
The two FPS values are required, not assumed.
"""
from __future__ import annotations

from dataclasses import dataclass

from yroll.core.timebase import FrameRange, FrameTime, Rational


@dataclass(frozen=True)
class TimeMap:
    """Bidirectional mapping for one Clip instance.

    Mapping rules:
      clip_frame      = source_frame - source_start_frame          (source_fps)
      timeline_frame  = timeline_start_frame + clip_frame / speed  (sequence_fps)

    The mapping is a pure function of
      (source_range, timeline_range, speed, sequence_fps, source_fps).

    source_fps and sequence_fps are both REQUIRED; TimeMap never
    assumes equality. The factory `for_clip(clip, sequence_fps,
    source_fps)` accepts no silent fallback — pass `sequence_fps` as
    `source_fps` only when the asset is genuinely conformant (which is
    exactly what `Project.validate_media_conformance()` is for).

    The legacy `fps` attribute is kept as an alias for `sequence_fps`
    so existing snapshot tests don't break — but new code MUST name
    the two fields explicitly.
    """
    source_start_frame: int      # clip.source_range.start (frames, source_fps)
    source_end_frame: int        # clip.source_range.end   (frames, source_fps)
    timeline_start_frame: int    # clip.timeline_range.start (frames, sequence_fps)
    speed: float                 # 1.0 = normal; 2.0 = 2x; 0.5 = half
    sequence_fps: Rational       # project's timeline timebase
    source_fps: Rational         # asset's source timebase (NEVER assumed equal)

    def __post_init__(self):
        if self.source_fps is None:
            raise ValueError(
                "TimeMap.source_fps is required; frame-native editing "
                "never assumes source_fps == sequence_fps"
            )
        if self.sequence_fps is None:
            raise ValueError("TimeMap.sequence_fps is required")
        if self.speed <= 0:
            raise ValueError(f"speed must be > 0, got {self.speed}")
        if self.source_end_frame < self.source_start_frame:
            raise ValueError("source_end_frame < source_start_frame")

    @property
    def fps(self) -> Rational:
        """Legacy alias: returns `sequence_fps`. New code must name the
        two FPS fields explicitly to avoid the assumption."""
        return self.sequence_fps

    # ---------- Source ↔ Clip Local (both in source_fps) ----------

    @property
    def source_range(self) -> FrameRange:
        """Source-frame FrameRange tagged with source_fps."""
        return FrameRange(self.source_start_frame, self.source_end_frame, self.source_fps)

    @property
    def timeline_range(self) -> FrameRange:
        """Timeline-frame FrameRange tagged with sequence_fps.
        Half-open: [timeline_start_frame, timeline_start_frame + clip_duration_in_tl_frames).
        FPS-aware: clip_duration (source frames) is converted to timeline
        frames via the same formula as timeline_from_clip."""
        clip_duration = self.source_end_frame - self.source_start_frame
        # Same formula as timeline_from_clip (relative offset from
        # timeline_start, no offset to add here):
        num = clip_duration * self.sequence_fps.num * self.source_fps.den
        den = self.speed * self.source_fps.num * self.sequence_fps.den
        tl_duration = round(num / den)
        return FrameRange(
            self.timeline_start_frame,
            self.timeline_start_frame + tl_duration,
            self.sequence_fps,
        )

    def clip_from_source(self, source_frame: int) -> int:
        """Source frame → clip-local frame. Out-of-range clamps to boundary.
        Both source_frame and the result are integers in source_fps."""
        if source_frame < self.source_start_frame:
            return 0
        sf = min(source_frame, self.source_end_frame - 1)
        return sf - self.source_start_frame

    def source_from_clip(self, clip_frame: int) -> int:
        """Clip-local frame → source frame. Both integers in source_fps."""
        if clip_frame < 0:
            return self.source_start_frame
        return self.source_start_frame + clip_frame

    # ---------- Clip Local ↔ Timeline (sequence_fps) ----------
    #
    # The FPS-aware conversion. speed=N means the clip plays at Nx:
    # 1 second of source becomes N seconds of timeline (for N>1).
    # Equivalently:
    #   clip_seconds      = clip_frame / source_fps
    #   timeline_seconds  = clip_seconds / speed   (speed=2 → half)
    #   timeline_frames   = timeline_seconds * sequence_fps
    #                     = clip_frame * sequence_fps / (speed * source_fps)
    #
    # For the conformant case (sequence_fps == source_fps), this
    # collapses to the legacy `clip_frame / speed` formula. For
    # heterogeneous FPS (e.g. seq=30, src=60, speed=1), the factor
    # is 0.5 — 1 timeline frame corresponds to 2 source frames.
    #
    # The closed-form rational math avoids float drift:
    #   timeline_frames_offset =
    #       clip_frame * seq_fps.num * src_fps.den
    #     / (speed * src_fps.num * seq_fps.den)

    def timeline_from_clip(self, clip_frame: int) -> int:
        """Clip-local frame → timeline frame (FPS-aware).

        Both FPS values come from the TimeMap construction; the
        caller has no way to override them per-call (and shouldn't —
        mixing FPS would silently relabel TimelineFrame integers as
        SourceFrame integers).
        """
        if clip_frame < 0:
            return self.timeline_start_frame
        num = clip_frame * self.sequence_fps.num * self.source_fps.den
        den = self.speed * self.source_fps.num * self.sequence_fps.den
        return self.timeline_start_frame + round(num / den)

    def clip_from_timeline(self, timeline_frame: int) -> int:
        """Timeline frame → clip-local frame. FPS-aware.

        Inverse of timeline_from_clip. Result is integer in source_fps.
        """
        if timeline_frame < self.timeline_start_frame:
            return 0
        num = (timeline_frame - self.timeline_start_frame) * self.speed * self.source_fps.num * self.sequence_fps.den
        den = self.sequence_fps.num * self.source_fps.den
        return round(num / den)

    # ---------- Source ↔ Timeline (the user-facing mapping) ----------

    def timeline_from_source(self, source_frame: int) -> int:
        """SourceFrame (in source_fps) → TimelineFrame (in sequence_fps)."""
        return self.timeline_from_clip(self.clip_from_source(source_frame))

    def source_from_timeline(self, timeline_frame: int) -> int:
        """TimelineFrame (in sequence_fps) → SourceFrame (in source_fps)."""
        return self.source_from_clip(self.clip_from_timeline(timeline_frame))

    # ---------- FrameRange helpers (used for ASR/字幕 mapping) ----------

    def timeline_from_source_range(self, src: FrameRange) -> FrameRange:
        """Map a source-frame FrameRange to its timeline-frame FrameRange.
        The output FrameRange is tagged with `sequence_fps`.

        Preserves half-open semantics: end_frame stays exclusive
        (start + duration). For speed mapping: timeline duration =
        source duration / speed, rounded.

        Note: when source_fps != sequence_fps, this is a best-effort
        integer mapping. Sub-frame accuracy is impossible; the boundary
        frames are rounded to nearest. Use Project.validate_media_
        conformance() to assert conformant assets if exact round-trip
        matters.
        """
        src_duration = src.duration_frames
        tl_duration = round(src_duration / self.speed)
        return FrameRange(
            start_frame=self.timeline_from_source(src.start_frame),
            end_frame=self.timeline_from_source(src.start_frame) + tl_duration,
            fps=self.sequence_fps,        # tagged with timeline timebase
        )

    def source_from_timeline_range(self, tl: FrameRange) -> FrameRange:
        """Map a timeline-frame FrameRange to its source-frame FrameRange.
        The output FrameRange is tagged with `source_fps`.

        Preserves half-open semantics.
        """
        tl_duration = tl.duration_frames
        src_duration = round(tl_duration * self.speed)
        return FrameRange(
            start_frame=self.source_from_timeline(tl.start_frame),
            end_frame=self.source_from_timeline(tl.start_frame) + src_duration,
            fps=self.source_fps,          # tagged with source timebase — NOT sequence!
        )

    # ---------- Factory ----------

    @classmethod
    def for_clip(
        cls, clip, sequence_fps: Rational, source_fps: Rational,
    ) -> "TimeMap":
        """Build TimeMap from a Clip model.

        Both `sequence_fps` (the project's timeline timebase) and
        `source_fps` (the asset's source timebase) are REQUIRED. There
        is no silent fallback — heterogeneous FPS is the norm, not
        the exception, and pretending source_fps == sequence_fps would
        silently relabel SourceFrame integers as TimelineFrame integers.

        Caller should:
          1. Look up the asset by `clip.asset_id`
          2. Read `asset.source_fps_rational` (raises if asset has no
             source timebase set — caller must run ffprobe first)
          3. Pass both fps values here
        """
        if source_fps is None:
            raise ValueError(
                "TimeMap.for_clip: source_fps is required; "
                "pass asset.source_fps_rational. Frame-native editing "
                "never assumes source_fps == sequence_fps"
            )
        sr = clip.source_range
        tr = clip.timeline_range
        return cls(
            source_start_frame=FrameTime.from_seconds(sr.start, source_fps).frame,
            source_end_frame=FrameTime.from_seconds(sr.end, source_fps).frame,
            timeline_start_frame=FrameTime.from_seconds(tr.start, sequence_fps).frame,
            speed=clip.speed,
            sequence_fps=sequence_fps,
            source_fps=source_fps,
        )