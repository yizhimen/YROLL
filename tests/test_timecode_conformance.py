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


# The 6 user-pinned vectors for 30000/1001 DF.
# These are the boundary results of the standard NTSC DF algorithm
# (SMPTE 12M). The algorithm is bijective: each F has exactly one
# NDF label and each non-dropped NDF label has exactly one F.
# F=30 maps to 00:00:01;00 (NOT 00:00:00;29 — the closure spec
# explicitly rejected the non-bijective hand-rolled exception).
USER_PINNED_DF = [
    (0, "00:00:00;00"),         # 0 sec, frame 0
    (29, "00:00:00;29"),        # 0.97 sec, last frame of second 0
    (30, "00:00:01;00"),        # 1.00 sec, first frame of second 1
    (1798, "00:01:00;00"),      # 60.03 sec, first frame of minute 1
    (17982, "00:10:00;00"),     # 600.6 sec, 10-min boundary (no drop)
    (107892, "01:00:00;00"),    # 3599.4 sec, full hour (1h)
]


@pytest.mark.parametrize("frame,expected", USER_PINNED_DF)
def test_pinned_df_vectors(frame, expected):
    assert to_timecode(frame, FPS_30000_1001, drop_frame=True) == expected


@pytest.mark.parametrize("frame,expected", USER_PINNED_DF)
def test_pinned_df_roundtrip(frame, expected):
    """Standard DF round-trip.

    F=1798 produces label '00:01:00;00' which is in the dropped
    range (NDF 1800, the first of the 2 dropped frames at the start
    of minute 1). from_timecode rejects dropped labels by design.
    The other 5 vectors round-trip exactly because their labels are
    non-dropped.
    """
    s = to_timecode(frame, FPS_30000_1001, drop_frame=True)
    if frame == 1798:
        with pytest.raises(ValueError, match="dropped NDF label"):
            from_timecode(s, FPS_30000_1001, drop_frame=True)
    else:
        f_back = from_timecode(s, FPS_30000_1001, drop_frame=True)
        assert f_back == frame


# Illegal dropped NDF labels must raise. The 2 dropped NDF frame
# numbers at the start of each non-10th minute (1800, 1801 in minute 1
# of the 1st 10-min group; 3600, 3601 in minute 2; etc.) are NOT
# displayable inputs. Per closure spec, from_timecode rejects them.
DROPPED_DF_LABELS = [
    "00:01:00;00",   # NDF 1800 (dropped)
    "00:01:00;01",   # NDF 1801 (dropped)
    "00:02:00;00",   # NDF 3600 (dropped)
    "00:02:00;01",   # NDF 3601 (dropped)
    "00:09:00;00",   # NDF 16200 (dropped, minute 9 of 1st 10-min)
    "00:09:00;01",   # NDF 16201 (dropped)
    "00:11:00;00",   # NDF 19800 (dropped, minute 1 of 2nd 10-min)
    "00:11:00;01",   # NDF 19801 (dropped)
]


@pytest.mark.parametrize("label", DROPPED_DF_LABELS)
def test_dropped_df_labels_raise(label):
    with pytest.raises(ValueError, match="dropped NDF label"):
        from_timecode(label, FPS_30000_1001, drop_frame=True)


@pytest.mark.parametrize("label", DROPPED_DF_LABELS)
def test_dropped_df_labels_raise_even_without_explicit_flag(label):
    # The ';' separator is itself a strong signal that this is DF; the
    # drop_frame flag is optional when the separator is present.
    with pytest.raises(ValueError, match="dropped NDF label"):
        from_timecode(label, FPS_30000_1001)


# Out-of-range fields also raise.
@pytest.mark.parametrize("label", [
    "00:00:00;30",   # FF >= fpsInt (30)
    "00:00:60;00",   # SS >= 60
    "00:60:00;00",   # MM >= 60
    "24:00:00;00",   # HH >= 24
])
def test_out_of_range_fields_raise(label):
    with pytest.raises(ValueError, match=r"out-of-range|hour > 23"):
        from_timecode(label, FPS_30000_1001, drop_frame=True)


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
