"""GUI-02.3: heterogeneous-source-FPS conformance.

The GUI-02.3 invariant: YROLL can state explicitly whether every
asset is frame-editable, what its source timebase is, and how a
TimelineFrame maps to its SourceFrame without assuming equal FPS.

These tests pin that invariant at the model layer. The architectural
guard (`tests/test_no_sequence_fps_as_source_fps.py`) prevents the
server-side source→media code path from silently substituting the
sequence FPS for the source FPS.
"""
from __future__ import annotations

import pytest

from yroll.core.manifest import Project, Sequence
from yroll.core.models import (
    Asset,
    AssetConformanceResult,
    AssetIdentity,
    AssetType,
)
from yroll.core.timebase import Rational


# ---------------------------------------------------------------------------
# Conformance result taxonomy
# ---------------------------------------------------------------------------

def _make_project_with_assets(assets, seq_fps=Rational(30, 1)):
    p = Project(project_id="p1", name="t", sequence=Sequence(fps=seq_fps))
    p.assets = assets
    return p


def _asset(aid, src_fps=None, cfr=None, fc=None):
    return Asset(
        asset_id=aid,
        type=AssetType.VIDEO,
        path=f"/tmp/{aid}.mp4",
        identity=AssetIdentity(md5=aid, size_bytes=1),
        source_fps=src_fps,
        source_is_cfr=cfr,
        source_frame_count=fc,
    )


def test_no_assets_returns_empty():
    p = _make_project_with_assets([])
    assert p.validate_media_conformance() == []
    assert p.frame_editable_asset_ids() == []
    assert p.unsupported_asset_ids() == []


def test_conformant_cfr_at_seq_fps_is_editable():
    """seq=30, src=30, CFR → frame_editable."""
    p = _make_project_with_assets([
        _asset("a", src_fps=Rational(30, 1), cfr=True, fc=900),
    ])
    [r] = p.validate_media_conformance()
    assert r.status == "frame_editable"
    assert r.is_frame_editable
    assert r.sequence_fps == Rational(30, 1)
    assert r.source_fps == Rational(30, 1)
    assert r.source_is_cfr is True
    assert r.recommended_action is None
    assert "CFR at sequence FPS" in r.reason


def test_fps_mismatch_is_needs_conform():
    """seq=30, src=24, CFR → needs_conform (heterogeneous)."""
    p = _make_project_with_assets([
        _asset("a", src_fps=Rational(24, 1), cfr=True, fc=720),
    ])
    [r] = p.validate_media_conformance()
    assert r.status == "needs_conform"
    assert not r.is_frame_editable
    assert r.source_fps == Rational(24, 1)
    assert "24/1" in r.reason and "30/1" in r.reason
    assert r.recommended_action is not None


def test_vfr_is_needs_conform():
    """seq=30, src=24, VFR → needs_conform (VFR editing out of scope)."""
    p = _make_project_with_assets([
        _asset("a", src_fps=Rational(24, 1), cfr=False, fc=720),
    ])
    [r] = p.validate_media_conformance()
    assert r.status == "needs_conform"
    assert r.source_is_cfr is False
    assert "VFR" in r.reason
    assert "CFR" in r.recommended_action


def test_no_source_fps_is_unsupported():
    """No source FPS → unsupported (resolve via ffprobe first)."""
    p = _make_project_with_assets([
        _asset("a"),
    ])
    [r] = p.validate_media_conformance()
    assert r.status == "unsupported"
    assert r.is_unsupported
    assert r.source_fps is None
    assert "ffprobe" in (r.recommended_action or "")


def test_unknown_cfr_with_known_fps_is_needs_conform():
    """source_fps set but source_is_cfr unknown → needs_conform (conservative)."""
    p = _make_project_with_assets([
        _asset("a", src_fps=Rational(25, 1), cfr=None, fc=750),
    ])
    [r] = p.validate_media_conformance()
    # 25 != 30 → mismatch wins
    assert r.status == "needs_conform"


def test_mixed_project_lists_editable_and_unsupported():
    """One conformant + one mismatched + one VFR + one unknown source."""
    p = _make_project_with_assets([
        _asset("a1", src_fps=Rational(30, 1), cfr=True),    # editable
        _asset("a2", src_fps=Rational(24, 1), cfr=True),    # needs_conform
        _asset("a3", src_fps=Rational(60, 1), cfr=False),   # needs_conform (VFR)
        _asset("a4"),                                        # unsupported
    ])
    results = p.validate_media_conformance()
    by_id = {r.asset_id: r for r in results}
    assert by_id["a1"].is_frame_editable
    assert by_id["a2"].needs_conform
    assert by_id["a3"].needs_conform
    assert by_id["a4"].is_unsupported
    assert p.frame_editable_asset_ids() == ["a1"]
    assert set(p.unsupported_asset_ids()) == {"a2", "a3", "a4"}


def test_override_sequence_fps_reclassifies():
    """Pass a candidate sequence_fps to preview what would change."""
    p = _make_project_with_assets([
        _asset("a", src_fps=Rational(60, 1), cfr=True),
    ])
    # Default seq=30 → mismatched
    [r] = p.validate_media_conformance()
    assert r.status == "needs_conform"
    # Override seq=60 → matches → editable
    [r] = p.validate_media_conformance(sequence_fps=Rational(60, 1))
    assert r.status == "frame_editable"


def test_30000_1001_conformance():
    """29.97 DF conformant asset is editable at 29.97 sequence."""
    seq = Rational(30000, 1001)
    p = _make_project_with_assets(
        [_asset("a", src_fps=Rational(30000, 1001), cfr=True, fc=90000)],
        seq_fps=seq,
    )
    [r] = p.validate_media_conformance()
    assert r.status == "frame_editable"
    assert r.sequence_fps == seq
    assert r.source_fps == seq


def test_24fps_into_30fps_sequence():
    """24fps source + 30fps sequence = heterogeneous → needs_conform."""
    p = _make_project_with_assets(
        [_asset("a", src_fps=Rational(24, 1), cfr=True, fc=240)],
        seq_fps=Rational(30, 1),
    )
    [r] = p.validate_media_conformance()
    assert r.status == "needs_conform"
    assert not r.is_frame_editable


def test_conformance_result_is_immutable():
    """AssetConformanceResult is frozen — the conformance verdict cannot
    be mutated after the check."""
    r = AssetConformanceResult(
        asset_id="a", status="frame_editable", reason="ok",
        sequence_fps=Rational(30, 1), source_fps=Rational(30, 1),
        source_is_cfr=True, recommended_action=None,
    )
    with pytest.raises(Exception):
        r.status = "needs_conform"  # type: ignore[misc]


def test_source_fps_rational_raises_when_unset():
    """The strict accessor MUST raise; never silently fall back to
    sequence fps."""
    a = _asset("a")  # no source_fps
    with pytest.raises(ValueError, match="no source FPS set"):
        _ = a.source_fps_rational


def test_source_fps_rational_returns_value_when_set():
    a = _asset("a", src_fps=Rational(24, 1))
    assert a.source_fps_rational == Rational(24, 1)


def test_is_vfr_property():
    a_vfr = _asset("a", src_fps=Rational(24, 1), cfr=False)
    a_cfr = _asset("b", src_fps=Rational(30, 1), cfr=True)
    a_unk = _asset("c", src_fps=Rational(60, 1))
    a_none = _asset("d")
    assert a_vfr.is_vfr is True
    assert a_cfr.is_vfr is False
    assert a_unk.is_vfr is False
    assert a_none.is_vfr is False


def test_source_timebase_known():
    a_full = _asset("a", src_fps=Rational(30, 1), cfr=True)
    a_partial = _asset("b", src_fps=Rational(30, 1), cfr=None)
    a_none = _asset("c")
    assert a_full.source_timebase_known is True
    assert a_partial.source_timebase_known is False
    assert a_none.source_timebase_known is False


def test_conformance_status_string_taxonomy():
    """The 3 statuses are exactly frame_editable / needs_conform /
    unsupported — no permanent FPS-only naming."""
    # This test pins the taxonomy so future contributors don't
    # rename the check to e.g. "fps_only_check" and lose the VFR /
    # codec / resolution dimension.
    statuses = {r.status for r in _make_project_with_assets([
        _asset("a1", src_fps=Rational(30, 1), cfr=True),
        _asset("a2", src_fps=Rational(24, 1), cfr=True),
        _asset("a3"),
    ]).validate_media_conformance()}
    assert statuses == {"frame_editable", "needs_conform", "unsupported"}