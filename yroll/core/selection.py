"""YROLL Selection (P0-03) - unified selection object.

Selection is a first-class citizen: every mutation should accept it
instead of just clip_id. P0-11 (one mutation path) depends on this.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from yroll.core.timebase import FrameRange, Timebase


@dataclass
class Selection:
    """A unified selection: clip_ids + tracks + (optional) frame range.

    Patterned after Premiere/CapCut + OpenCut, but minimal.

    Modes:
    - Single clip: clip_ids=['c1']
    - Multi clip: clip_ids=['c1','c2','c3']
    - Range only: range=FrameRange (no specific clips, e.g., "all in 0:00:05-0:00:10")
    - Track only: track_ids=['v1','v2'] (all clips in those tracks)
    - Linked: future (e.g., voice + subtitle auto-link)
    """
    clip_ids: list[str] = field(default_factory=list)
    track_ids: list[str] = field(default_factory=list)
    range: Optional[FrameRange] = None

    def is_empty(self) -> bool:
        return not (self.clip_ids or self.track_ids or self.range)

    def __bool__(self) -> bool:
        return not self.is_empty()

    def contains_clip(self, clip_id: str) -> bool:
        return clip_id in self.clip_ids

    def contains_track(self, track_id: str) -> bool:
        return track_id in self.track_ids

    def intersects(self, track_id: str, start_frame: int, end_frame: int) -> bool:
        """True if selection affects this track's frame range."""
        if track_id in self.track_ids:
            return True
        if self.range and not (end_frame < self.range.start_frame or start_frame >= self.range.end_frame):
            return True
        return False

    def describe(self) -> str:
        parts = []
        if self.clip_ids:
            parts.append(f"{len(self.clip_ids)} clip(s)")
        if self.track_ids:
            parts.append(f"{len(self.track_ids)} track(s)")
        if self.range:
            parts.append(f"range={self.range}")
        return ", ".join(parts) if parts else "empty"

    @classmethod
    def single(cls, clip_id: str) -> 'Selection':
        return cls(clip_ids=[clip_id])

    @classmethod
    def many(cls, clip_ids: list[str]) -> 'Selection':
        return cls(clip_ids=list(clip_ids))

    @classmethod
    def track_only(cls, track_id: str) -> 'Selection':
        return cls(track_ids=[track_id])

    @classmethod
    def range_only(cls, frame_range: FrameRange) -> 'Selection':
        return cls(range=frame_range)

    @classmethod
    def from_clip_or_id(cls, thing) -> 'Selection':
        """Convenience: accept either a clip_id str or a Selection object."""
        if isinstance(thing, Selection):
            return thing
        if isinstance(thing, str):
            return cls(clip_ids=[thing])
        if isinstance(thing, (list, tuple)) and all(isinstance(x, str) for x in thing):
            return cls(clip_ids=list(thing))
        raise TypeError(f"cannot make Selection from {type(thing)}")
