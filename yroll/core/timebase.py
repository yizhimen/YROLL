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
        # Standard NTSC DF (SMPTE 12M) — Wikipedia reference algorithm.
        # drops_so_far(F) = 2 per minute, except the 10th minute of
        # every 10-min group. 9 drops × 2 = 18 per 10-min group. The
        # result is a bijective F→NDF mapping (every NDF label has
        # exactly one preimage F), which is what the GUI consumes.
        drops = _df_drops_so_far(frame)
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


def _df_drops_so_far(F: int, drop: int = 2, fpm: int = 1798,
                     fpm_10: int = 17982) -> int:
    """Standard NTSC DF: number of NDF frame numbers skipped before
    real frame F. The closed-form formula
        drops(F) = 2 * (F // fpm) - 2 * (F // fpm_10)
    counts minutes 1..8 within every 10-min group (each contributing
    2 drops) and subtracts the 2 drops per 10-min boundary that
    the minute-counting would otherwise over-count.
    """
    if F < 0:
        raise ValueError(f"frame must be non-negative, got {F}")
    return 2 * (F // fpm) - 2 * (F // fpm_10)


def _is_dropped_ndf_at_29_97(ndf: int) -> bool:
    """Returns True if ndf is a dropped frame number at 30000/1001
    DF. The standard NTSC DF drops 2 NDF frame numbers at the start
    of every minute except every tenth: 1800*m and 1800*m+1 for
    minute m in 1..9 within each 10-min group. So the dropped range
    within a 10-min group is [1800, 16202)."""
    if ndf < 0:
        return False
    ndf_d = ndf % 18000            # NDF within the 10-min group (10*1800)
    return 1800 <= ndf_d < 16202


def from_timecode(s: str, fps: "Rational", drop_frame: bool = False) -> int:
    """Inverse of to_timecode. Round-trip property is exact for both
    NDF and DF (bijective).

    Accepted separators: `:` for NDF/SMPTE, `;` for DF. The DF flag
    overrides the separator if the user passed it explicitly.

    For DF at 30000/1001: illegal dropped labels
    (00:01:00;00, 00:01:00;01, etc.) raise `ValueError`. Out-of-
    range fields (FF ≥ fps, SS/MM/HH ≥ 60/24) also raise.
    """
    if not s or len(s) < 11:
        raise ValueError(f"timecode must be HH:MM:SS:FF or HH:MM:SS;FF, got {s!r}")
    sep = s[8]
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
    if hh > 23:
        raise ValueError(f"hour > 23 in {s!r}")
    if mm > 59 or ss > 59 or ff >= fps_int:
        raise ValueError(f"out-of-range timecode field in {s!r}")
    ndf_frames = ((hh * 60 + mm) * 60 + ss) * fps_int + ff
    if not is_df:
        return ndf_frames

    # DF inverse at 30000/1001: reject illegal dropped labels, then
    # invert the standard NDF → F mapping.
    is_30000_1001 = (fps.num == 30000 and fps.den == 1001)
    if not is_30000_1001:
        return ndf_frames
    if _is_dropped_ndf_at_29_97(ndf_frames):
        raise ValueError(
            f"{s!r} is a dropped NDF label at 29.97 DF; "
            f"the standard algorithm does not display it. "
            f"Use the next non-dropped label."
        )
    fpm_10 = 17982
    fpm = 1800
    drop = 2
    d = ndf_frames // (10 * fpm)
    m_in = ndf_frames % (10 * fpm)
    # Inverse of drops_so_far. For each NDF within the 10-min group,
    # find the real F such that drops_so_far(d*17982 + F) + (d*17982+F)
    # = ndf. We invert in closed form below.
    if m_in < fpm:                                # minute 0 of the 10-min group
        f = m_in
    else:
        # Minutes 1..8: m_in >= fpm (= 1800).
        # For m_in = 1800 + 0 (dropped) we already rejected above.
        # For m_in in [1802, 3600): F = m_in - drop (one drop applied).
        # For m_in in [3602, 5400): F = m_in - 2*drop, etc.
        # minute index in 10-min group (0..8, NOT 9):
        minute_in_10 = (m_in - fpm) // fpm          # 0..7
        # Within the minute:
        ndf_in_minute = m_in - fpm - minute_in_10 * fpm  # 0..1797
        # In the first 2 NDF frame numbers of each minute the 2
        # drops are applied (we already rejected those).
        f = minute_in_10 * fpm + (minute_in_10 + 1) * drop + ndf_in_minute - 0
        # Wait: m_in = 1800 + 2 + (minute_in_10)*1800 + ndf_in_minute
        #       = (minute_in_10 + 1) * 1800 + 2 + ndf_in_minute
        #       = (minute_in_10 + 1) * fpm + drop + ndf_in_minute
        # But f = (minute_in_10 + 1) * 1798 + ndf_in_minute
        # And drops_so_far(f) = 18*d + drop*(minute_in_10 + 1) (since
        # m_in_minute_in_10 < 9 because m_in < 9*fpm and minute_in_10
        # < 9).
        # So f + drops = minute_in_10*1798 + ndf_in_minute +
        # 18*d + drop*(minute_in_10+1)
        # For this to equal m_in = 1800 + minute_in_10*1800 + ndf_in_minute,
        # we need: minute_in_10*1798 + ndf_in_minute + drop*(minute_in_10+1)
        # = 1800 + minute_in_10*1800 + ndf_in_minute
        # → minute_in_10*(1798+drop) + drop = 1800 + minute_in_10*1800
        # → minute_in_10*1800 = 1800 + minute_in_10*1800 ✓
        # So f = (minute_in_10 + 1) * 1798 + ndf_in_minute.
        # For minute_in_10 = 0: f = 1798 + ndf_in_minute. For ndf_in_minute=0: f=1798, displays 00:01:00;02 ✓.
        # General: f = (minute_in_10 + 1) * fpm_real + ndf_in_minute,
        # where fpm_real = fpm - drop = 1798.
        # minute_in_10 ranges 0..7 (since m_in < 9*fpm here). Wait,
        # the 10th minute (m_in in [9*1800, 10*1800)) has no drop and
        # m_in_in_10th = 9. We need to handle it separately.
        if m_in >= 9 * fpm:
            # 10th minute: no drop.
            # m_in in [9*1800, 10*1800).
            # f = 9 * 1798 + (m_in - 9*1800)
            f = 9 * (fpm - drop) + (m_in - 9 * fpm)
        else:
            # Minutes 1..8: f = (minute_in_10 + 1) * (fpm - drop) + ndf_in_minute
            f = (minute_in_10 + 1) * (fpm - drop) + ndf_in_minute
    return d * fpm_10 + f

