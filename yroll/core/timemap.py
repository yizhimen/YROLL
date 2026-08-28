"""YROLL Time Mapping (P0-02): source_frame ↔ clip_frame ↔ timeline_frame.

Three-frame-space mapping, the foundation for Frame-native editing:

  Source Asset Frame
        │  (source_range)
        ▼
  Clip Local Frame
        │  (timeline_position, speed, trim offsets)
        ▼
  Timeline Frame

A TimeMap is built once per Clip and cached. After trim/move/speed changes,
the TimeMap must be rebuilt (call .for_clip(clip, fps)).

Why this matters:
- Agent asks: "what timeline frame is source frame 1200 of asset A?"
- Old code recomputes (s - sr.start) / clip.speed inline, repeated in
  generate_subtitles, search-transcripts, ripple_delete, filler_remove...
- New code asks TimeMap once: `tm.timeline_from_source(1200)` → FrameTime.

All inputs/outputs in canonical frames (FrameTime / FrameRange).
"""
from __future__ import annotations

from dataclasses import dataclass

from yroll.core.timebase import FrameRange, FrameTime, Rational


@dataclass(frozen=True)
class TimeMap:
    """Bidirectional mapping for one Clip instance.

    Mapping rules:
      clip_frame = source_frame - source_start_frame
      timeline_frame = timeline_start_frame + clip_frame / speed
        (with speed handled as integer ratio when possible, otherwise float)

    This is a pure function of (source_range, timeline_range, speed).
    """
    source_start_frame: int      # clip.source_range.start (frames)
    source_end_frame: int        # clip.source_range.end (frames)
    timeline_start_frame: int    # clip.timeline_range.start (frames)
    speed: float                 # 1.0 = normal; 2.0 = 2x; 0.5 = half
    fps: Rational

    def __post_init__(self):
        if self.speed <= 0:
            raise ValueError(f"speed must be > 0, got {self.speed}")
        if self.source_end_frame < self.source_start_frame:
            raise ValueError("source_end_frame < source_start_frame")

    # ---------- Source ↔ Clip Local ----------

    @property
    def source_range(self) -> FrameRange:
        return FrameRange(self.source_start_frame, self.source_end_frame, self.fps)

    def clip_from_source(self, source_frame: int) -> int:
        """Source frame → clip-local frame. Out-of-range clamps to boundary."""
        if source_frame < self.source_start_frame:
            return 0
        sf = min(source_frame, self.source_end_frame - 1)
        return sf - self.source_start_frame

    def source_from_clip(self, clip_frame: int) -> int:
        """Clip-local frame → source frame."""
        if clip_frame < 0:
            return self.source_start_frame
        return self.source_start_frame + clip_frame

    # ---------- Clip Local ↔ Timeline ----------

    def timeline_from_clip(self, clip_frame: int) -> int:
        """Clip-local frame → timeline frame (accounting for speed)."""
        if clip_frame < 0:
            return self.timeline_start_frame
        # Use round() so 60 frames @ 2x = 30 timeline frames (exact).
        return round(self.timeline_start_frame + clip_frame / self.speed)

    def clip_from_timeline(self, timeline_frame: int) -> int:
        """Timeline frame → clip-local frame."""
        if timeline_frame < self.timeline_start_frame:
            return 0
        return round((timeline_frame - self.timeline_start_frame) * self.speed)

    # ---------- Source ↔ Timeline (the user-facing mapping) ----------

    def timeline_from_source(self, source_frame: int) -> int:
        """The mapping Agent asks for: source frame → timeline frame."""
        return self.timeline_from_clip(self.clip_from_source(source_frame))

    def source_from_timeline(self, timeline_frame: int) -> int:
        """Timeline frame → source frame."""
        return self.source_from_clip(self.clip_from_timeline(timeline_frame))

    # ---------- FrameRange helpers (used for ASR/字幕 mapping) ----------

    def timeline_from_source_range(self, src: FrameRange) -> FrameRange:
        """Map a source-frame FrameRange to its timeline-frame FrameRange.
        Preserves half-open semantics: end_frame stays exclusive (start + duration).
        For speed mapping: timeline duration = source duration / speed, rounded.
        """
        src_duration = src.duration_frames
        tl_duration = round(src_duration / self.speed)
        return FrameRange(
            start_frame=self.timeline_from_source(src.start_frame),
            end_frame=self.timeline_from_source(src.start_frame) + tl_duration,
            fps=self.fps,
        )

    def source_from_timeline_range(self, tl: FrameRange) -> FrameRange:
        """Map a timeline-frame FrameRange to its source-frame FrameRange.
        Preserves half-open semantics.
        """
        tl_duration = tl.duration_frames
        src_duration = round(tl_duration * self.speed)
        return FrameRange(
            start_frame=self.source_from_timeline(tl.start_frame),
            end_frame=self.source_from_timeline(tl.start_frame) + src_duration,
            fps=self.fps,
        )

    # ---------- Factory ----------

    @classmethod
    def for_clip(cls, clip, fps: Rational) -> "TimeMap":
        """Build TimeMap from a Clip model + project fps.

        Reads seconds from the clip and converts to frames via FrameTime.
        """
        sr = clip.source_range
        tr = clip.timeline_range
        return cls(
            source_start_frame=FrameTime.from_seconds(sr.start, fps).frame,
            source_end_frame=FrameTime.from_seconds(sr.end, fps).frame,
            timeline_start_frame=FrameTime.from_seconds(tr.start, fps).frame,
            speed=clip.speed,
            fps=fps,
        )
