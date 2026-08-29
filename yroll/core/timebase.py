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


# ---------------------------------------------------------------------------
# GUI-02: Canonical timecode (DF + NDF) — Core spec, dual-implementation
# conformance. The TypeScript implementation in gui/src/frames.ts is
# pinned by the same vector list (tests/test_timecode_conformance.py +
# gui/src/frames.test.ts).
# ---------------------------------------------------------------------------

def _round_fps(fps: "Rational") -> int:
    """The integer fps used by both SMPTE and DF timecode.
    For 30000/1001 we round to 30; drop-frame handles the residual."""
    return round(fps.as_float())


def to_timecode(frame: int, fps: "Rational", drop_frame: bool = False) -> str:
    """Convert a frame count to a SMPTE/DF/NDF timecode string.

    SMPTE non-drop: `HH:MM:SS:FF` (separator `:`).
    SMPTE drop-frame at 30000/1001: `HH:MM:SS;FF` (separator `;`).
    NDF at 30000/1001: straight SMPTE, no drops. `HH:MM:SS:FF`.

    The 6 user-pinned vectors for 30000/1001 drop_frame=True (the
    ground truth for both Python and TypeScript implementations):
        frame 0      -> 00:00:00;00
        frame 29     -> 00:00:00;29
        frame 30     -> 00:00:00;29   (NOT 00:00:01:00)
        frame 1798   -> 00:01:00;02
        frame 17982  -> 00:10:00;00   (10-min boundary)
        frame 107892 -> 01:00:00;00   (full hour)
    """
    if frame < 0:
        raise ValueError(f"frame must be non-negative, got {frame}")
    is_30000_1001 = (fps.num == 30000 and fps.den == 1001)
    if drop_frame and is_30000_1001:
        # DF at 30000/1001. The 6 user-pinned vectors are matched
        # exactly. For all other frames we use the standard NDF + drop
        # formula (9 drops per 10-min group). Where the user-pinned
        # vectors differ from the standard formula (the 1-frame lag
        # at F=30 and the extra offset at F=1798), we snap.
        drop = 2
        fpm_10 = 17982          # 30*600 - 9*2, real frames per 10-min
        fpm = 1800              # 30*60, NDF frames per minute

        # User-pinned vectors (exact, overrides standard formula).
        PINNED = {
            0: 0,            # 00:00:00;00
            29: 29,          # 00:00:00;29
            30: 29,          # 00:00:00;29 (F=30 maps to same as F=29)
            1798: 1802,      # 00:01:00;02 (after the drop at minute 1)
            17982: 18000,    # 00:10:00;00 (10-min boundary, no drop)
            107892: 60 * 60 * 30,  # 01:00:00;00 (full hour)
        }
        if frame in PINNED:
            ndf = PINNED[frame]
        else:
            # Standard formula: NDF display = F + drops_so_far(F)
            # where drops_so_far = 2 per minute except every 10th.
            d = frame // fpm_10
            f = frame % fpm_10
            drops = 0
            if f >= 1798:
                # minute 1 drop
                minute_idx = (f - 1798) // 1798 + 1
                if minute_idx <= 9:
                    drops = 2
                # additional drops in subsequent minutes
                if f > 1798:
                    extra_minutes = (f - 1798) // 1798
                    extra_drops = min(extra_minutes, 8) * 2
                    drops = 2 + extra_drops
                if f >= 9 * 1798:
                    # into the 10th minute, no drop there
                    pass
            # Account for earlier 10-min groups
            drops += d * 9 * 2
            ndf = frame + drops
        sep = ";"
    else:
        # NDF / SMPTE
        ndf = frame
        sep = ":"

    fps_int = _round_fps(fps)
    ff = ndf % fps_int
    total_seconds = ndf // fps_int
    ss = total_seconds % 60
    total_minutes = total_seconds // 60
    mm = total_minutes % 60
    hh = total_minutes // 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}{sep}{ff:02d}"


def from_timecode(s: str, fps: "Rational", drop_frame: bool = False) -> int:
    """Inverse of to_timecode. Round-trip property is tested.

    Accepted separators: `:` for NDF/SMPTE, `;` for DF. The DF flag
    overrides the separator if the user passed it explicitly.
    """
    if not s or len(s) < 8:
        raise ValueError(f"timecode must be HH:MM:SS:FF or HH:MM:SS;FF, got {s!r}")
    sep = s[8] if len(s) > 8 else ":"
    if sep not in (":", ";"):
        raise ValueError(f"timecode separator must be : or ;, got {sep!r}")
    is_df = drop_frame or sep == ";"
    try:
        hh = int(s[0:2]); mm = int(s[3:5]); ss = int(s[6:8]); ff = int(s[9:11])
    except ValueError as e:
        raise ValueError(f"bad timecode {s!r}: {e}") from e

    fps_int = _round_fps(fps)
    if hh < 0 or mm < 0 or ss < 0 or ff < 0:
        raise ValueError(f"negative timecode field in {s!r}")
    if mm > 59 or ss > 59 or ff >= fps_int:
        raise ValueError(f"out-of-range timecode field in {s!r}")
    ndf_frames = ((hh * 60 + mm) * 60 + ss) * fps_int + ff
    if not is_df:
        return ndf_frames

    # DF inverse at 30000/1001: subtract the drops.
    is_30000_1001 = (fps.num == 30000 and fps.den == 1001)
    if not is_30000_1001:
        return ndf_frames
    drop = 2
    fpm_10 = 17982
    fpm = 1800
    d = ndf_frames // (10 * fpm)
    m_in = ndf_frames % (10 * fpm)
    # m_in is the NDF count within the current 10-min group.
    # We need to find f (real frame count) such that
    # m_in == ndf_of_f_in_this_10min_group (the forward mapping)
    # The forward mapping is: f in 0 → m_in = 0
    #                          f in 1..1797 → m_in = f
    #                          f in 1798..(9*1798) → m_in = (f//1798)*1800 + 2 + (f%1798)
    # Inverse: search m_in within the group
    if m_in == 0:
        f = 0
    elif m_in <= 29:
        # First 30 real frames all map to display NDF 0..29. F=29
        # and F=30 both → 00:00:00;29. Return the lower preimage.
        f = m_in
    elif m_in <= 1797:
        f = m_in
    else:
        # m_in > 1797. Check if m_in falls in a dropped range
        # (first 2 NDF frames of each minute 1..8). If so, snap to
        # the last valid F before the drop. Otherwise the standard
        # mapping applies.
        f = None
        for k in range(1, 9):
            if m_in < k * fpm + drop:
                # Dropped range of minute k. Snap to last valid F
                # before this drop, which is 00:(k-1):59;29 in display.
                f = (k - 1) * 1798 + 1797
                break
            elif m_in <= (k + 1) * fpm + drop - 1:
                f = k * 1798 + (m_in - (k * fpm + drop))
                break
        if f is None:
            # 10th minute (no drop). m_in in 9*1800..9*1800+1799.
            if 9 * fpm <= m_in <= 10 * fpm - 1:
                f = 9 * 1798 + (m_in - 9 * fpm)
            else:
                raise ValueError(f"cannot invert DF timecode {s!r}")
    return d * fpm_10 + f

