"""Marker (P1 §38) tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor
from yroll.core.markers import (
    legacy_add_marker as add_marker,
    legacy_list_markers as list_markers,
    legacy_remove_marker as remove_marker,
    legacy_update_marker as update_marker,
)
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore


@pytest.fixture()
def core(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "markers-test")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=60.0),
    ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 30.0, timeline_start=0.0)
    return core


def test_add_and_list_marker(core):
    m = add_marker(core.project, timeline_frame=120, label="Beat 1")
    assert m.marker_id
    assert m.label == "Beat 1"
    markers = list_markers(core.project)
    assert len(markers) == 1
    assert markers[0].timeline_frame == 120


def test_markers_sorted_by_frame(core):
    add_marker(core.project, timeline_frame=300, label="C")
    add_marker(core.project, timeline_frame=60, label="A")
    add_marker(core.project, timeline_frame=150, label="B")
    ms = list_markers(core.project)
    assert [m.label for m in ms] == ["A", "B", "C"]


def test_remove_marker(core):
    m = add_marker(core.project, timeline_frame=100, label="X")
    assert remove_marker(core.project, m.marker_id) is True
    assert list_markers(core.project) == []
    # Removing again returns False
    assert remove_marker(core.project, m.marker_id) is False


def test_update_marker(core):
    m = add_marker(core.project, timeline_frame=100, label="orig")
    updated = update_marker(core.project, m.marker_id,
                             label="new", color="#ff0000")
    assert updated.label == "new"
    assert updated.color == "#ff0000"


def test_marker_persists_after_save_reload(tmp_path):
    core = ProjectCore.create(tmp_path, "persist")
    add_marker(core.project, timeline_frame=1832, label="key frame")
    core.save_state()
    reloaded = ProjectCore.open(tmp_path / "persist")
    markers = list_markers(reloaded.project)
    assert len(markers) == 1
    assert markers[0].label == "key frame"
    assert markers[0].timeline_frame == 1832


def test_markers_compatible_with_snap_engine(core):
    """SnapEngine.collect_* helpers can use marker frames."""
    from yroll.core.snap import SnapEngine, SnapKind
    from yroll.core.timebase import Rational
    fps = Rational(30, 1)
    add_marker(core.project, timeline_frame=1832, label="key")
    add_marker(core.project, timeline_frame=200, label="other")

    # Build SnapTarget list manually from markers (mirrors collect_* pattern)
    from yroll.core.snap import SnapTarget
    targets = [SnapTarget(m.timeline_frame, SnapKind.MARKER, label=m.label)
               for m in list_markers(core.project)]
    snap = SnapEngine(threshold_frames=3).snap(frame=1831, targets=targets)
    assert snap is not None
    assert snap.target.kind == SnapKind.MARKER
    assert snap.target.label == "key"
