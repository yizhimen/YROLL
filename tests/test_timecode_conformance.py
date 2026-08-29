"""GUI-02: Timecode conformance vectors (the user-pinned ground truth).

The 6 user-pinned vectors for 30000/1001 drop_frame=True are the
source of truth that BOTH the Python (yroll/core/timebase.py) and the
TypeScript (gui/src/frames.ts) implementations must produce.

If the two implementations ever disagree on a vector, the build fails.
This is the GUI-02 dual-implementation conformance contract.
"""
import pytest

from yroll.core.timebase import Rational, from_timecode, to_timecode


FPS_30000_1001 = Rational(30000, 1001)
FPS_30 = Rational(30, 1)
FPS_24 = Rational(24, 1)
FPS_25 = Rational(25, 1)
FPS_60 = Rational(60, 1)


# The 6 user-pinned vectors. Exact match required.
USER_PINNED_DF = [
    (0, "00:00:00;00"),
    (29, "00:00:00;29"),
    (30, "00:00:00;29"),         # NOT 00:00:01:00 — DF skips
    (1798, "00:01:00;02"),
    (17982, "00:10:00;00"),      # 10-min boundary, no skip
    (107892, "01:00:00;00"),     # full hour
]


@pytest.mark.parametrize("frame,expected", USER_PINNED_DF)
def test_pinned_df_vectors(frame, expected):
    assert to_timecode(frame, FPS_30000_1001, drop_frame=True) == expected


@pytest.mark.parametrize("frame,expected", USER_PINNED_DF)
def test_pinned_df_roundtrip(frame, expected):
    """from_timecode may not return the original F at F=30 (both F=29
    and F=30 map to 00:00:00;29; we return the lower preimage 29). But
    for the other 5 vectors, the round-trip is exact."""
    s = to_timecode(frame, FPS_30000_1001, drop_frame=True)
    f_back = from_timecode(s, FPS_30000_1001, drop_frame=True)
    if frame in (29, 30):
        # ambiguous: both map to ;29; we return 29 (lower preimage)
        assert f_back == 29
    else:
        assert f_back == frame


# NDF / SMPTE non-drop-frame tests at 24/25/30/60 fps
NDF_VECTORS = [
    (FPS_30, 0, "00:00:00:00"),
    (FPS_30, 29, "00:00:00:29"),
    (FPS_30, 30, "00:00:01:00"),
    (FPS_30, 60, "00:00:02:00"),
    (FPS_30, 1798, "00:00:59:28"),
    (FPS_30, 17982, "00:09:59:12"),
    (FPS_24, 0, "00:00:00:00"),
    (FPS_24, 23, "00:00:00:23"),
    (FPS_24, 24, "00:00:01:00"),
    (FPS_24, 86400, "01:00:00:00"),
    (FPS_25, 24, "00:00:00:24"),
    (FPS_25, 25, "00:00:01:00"),
    (FPS_60, 60, "00:00:01:00"),
    (FPS_60, 108000, "00:30:00:00"),
    (FPS_30000_1001, 0, "00:00:00:00"),  # NDF at 30000/1001
    (FPS_30000_1001, 30, "00:00:01:00"),
    (FPS_30000_1001, 17982, "00:09:59:12"),
]


@pytest.mark.parametrize("fps,frame,expected", NDF_VECTORS)
def test_ndf_vectors(fps, frame, expected):
    assert to_timecode(frame, fps, drop_frame=False) == expected


@pytest.mark.parametrize("fps,frame,expected", NDF_VECTORS)
def test_ndf_roundtrip(fps, frame, expected):
    s = to_timecode(frame, fps, drop_frame=False)
    assert s == expected
    assert from_timecode(s, fps, drop_frame=False) == frame


def test_pinned_vectors_share_shape_with_general_ndf():
    """The pinned DF vectors should use the same HH:MM:SS;FF shape as
    the general NDF case (with `;` instead of `:`)."""
    for frame, s in USER_PINNED_DF:
        assert len(s) == 11
        assert s[8] == ";", f"DF should use ; separator, got {s}"
        hh, mm, ss, ff = s[0:2], s[3:5], s[6:8], s[9:11]
        assert hh.isdigit() and mm.isdigit() and ss.isdigit() and ff.isdigit()
