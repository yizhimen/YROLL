"""YROLL Time Model (P0-01) - Frame First.

Internal canonical time is frames, not seconds.
Seconds are only for: UI display, ffmpeg arguments, human-friendly I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Union


@dataclass(frozen=True)
class Rational:
    """Exact rational number (numerator/denominator). Used for fps."""
    num: int
    den: int

    def __post_init__(self):
        if self.den == 0:
            raise ValueError("denominator cannot be 0")
        if self.den < 0:
            object.__setattr__(self, 'num', -self.num)
            object.__setattr__(self, 'den', -self.den)
        from math import gcd
        g = gcd(abs(self.num), abs(self.den))
        if g > 1:
            object.__setattr__(self, 'num', self.num // g)
            object.__setattr__(self, 'den', self.den // g)

    def as_float(self) -> float:
        return self.num / self.den

    def __str__(self):
        if self.den == 1:
            return f"{self.num}"
        return f"{self.num}/{self.den}"


@dataclass(frozen=True)
class FrameTime:
    """A single point in time, expressed in frames."""
    frame: int
    fps: Rational

    def to_seconds(self) -> float:
        return self.frame / self.fps.as_float()

    @classmethod
    def from_seconds(cls, sec: float, fps: Rational) -> 'FrameTime':
        return cls(frame=round(sec * fps.as_float()), fps=fps)

    def __str__(self):
        s = self.frame / self.fps.as_float()
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = s % 60
        ff = self.frame % self.fps.num
        return f"{h:02d}:{m:02d}:{sec:06.3f}[{ff:02d}]"


@dataclass(frozen=True)
class FrameRange:
    """Half-open frame range [start, end). All time is frames."""
    start_frame: int
    end_frame: int
    fps: Rational

    def __post_init__(self):
        if self.end_frame < self.start_frame:
            raise ValueError("end_frame must be >= start_frame")

    @property
    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame

    def to_seconds(self) -> tuple:
        return (self.start_frame / self.fps.as_float(),
                self.end_frame / self.fps.as_float())

    @classmethod
    def from_seconds(cls, start_sec: float, end_sec: float, fps: Rational) -> 'FrameRange':
        return cls(
            start_frame=round(start_sec * fps.as_float()),
            end_frame=round(end_sec * fps.as_float()),
            fps=fps
        )

    def contains(self, frame: int) -> bool:
        return self.start_frame <= frame < self.end_frame

    def overlaps(self, other: 'FrameRange') -> bool:
        return self.start_frame < other.end_frame and other.start_frame < self.end_frame

    def __str__(self):
        s = self.start_frame / self.fps.as_float()
        e = self.end_frame / self.fps.as_float()
        return f"[{s:.3f}s..{e:.3f}s) = {self.duration_frames} frames"


@dataclass
class Timebase:
    """Project canonical time base - fps + resolution."""
    fps: Rational = Rational(30, 1)
    width: int = 1920
    height: int = 1080

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 16/9

    def to_dict(self) -> dict:
        return {"fps": str(self.fps), "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, d: dict) -> 'Timebase':
        if not d:
            return cls()
        fps_str = d.get('fps', '30')
        if '/' in fps_str:
            n, den = fps_str.split('/')
            fps = Fraction(int(n), int(den)) if int(den) > 0 else Fraction(30, 1)
        else:
            fps = Fraction(int(float(fps_str)), 1) if float(fps_str) > 0 else Fraction(30, 1)
        return cls(fps=Rational(fps.numerator, fps.denominator),
                   width=int(d.get('width', 1920)),
                   height=int(d.get('height', 1080)))
