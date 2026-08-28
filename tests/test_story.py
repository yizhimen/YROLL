"""Story / Beat Model tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor, TrackKind
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.story import (
    STANDARD_BEAT_KINDS, add_beat, beat_at_frame, beats_overlapping,
    list_beats, remove_beat, suggest_beat_boundaries,
)
from yroll.core.timebase import Rational


FPS = Rational(30, 1)


@pytest.fixture()
def core(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "story-test")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=60.0),
    ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)
    cmd.add_clip("a1", 10.0, 20.0, timeline_start=10.0)
    return core


def test_add_and_list_beat(core):
    b = add_beat(core.project, "Setup", "setup",
                  start_frame=0, end_frame=300)
    assert b.beat_id
    assert b.label == "Setup"
    beats = list_beats(core.project)
    assert len(beats) == 1


def test_beats_sorted_by_start_frame(core):
    add_beat(core.project, "Climax", "climax", 600, 900)
    add_beat(core.project, "Setup", "setup", 0, 300)
    add_beat(core.project, "Resolution", "resolution", 900, 1200)
    beats = list_beats(core.project)
    assert [b.label for b in beats] == ["Setup", "Climax", "Resolution"]


def test_remove_beat(core):
    b = add_beat(core.project, "X", "custom", 0, 100)
    assert remove_beat(core.project, b.beat_id) is True
    assert list_beats(core.project) == []


def test_beat_at_frame(core):
    add_beat(core.project, "Setup", "setup", 0, 300)
    add_beat(core.project, "Climax", "climax", 600, 900)
    assert beat_at_frame(core.project, 150).label == "Setup"
    assert beat_at_frame(core.project, 700).label == "Climax"
    assert beat_at_frame(core.project, 500) is None  # gap


def test_beats_overlapping(core):
    add_beat(core.project, "A", "setup", 0, 300)
    add_beat(core.project, "B", "rising_action", 200, 500)
    add_beat(core.project, "C", "climax", 600, 900)
    overlaps = beats_overlapping(core.project, 250, 350)
    assert {b.label for b in overlaps} == {"A", "B"}


def test_invalid_beat_range_raises(core):
    with pytest.raises(ValueError):
        add_beat(core.project, "Bad", "custom", 500, 100)


def test_beat_persists_after_save_reload(tmp_path):
    core = ProjectCore.create(tmp_path, "persist")
    add_beat(core.project, "Setup", "setup", 0, 300)
    core.save_state()
    reloaded = ProjectCore.open(tmp_path / "persist")
    beats = list_beats(reloaded.project)
    assert len(beats) == 1
    assert beats[0].label == "Setup"


def test_suggest_beat_boundaries_detects_gaps():
    """Two clips with a 3s gap should produce one suggestion."""
    core = ProjectCore.create(Path("/tmp"), "suggest-test")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=60.0),
    ))
    cmd = CommandLayer(core, who=Actor.HUMAN)
    cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)
    cmd.add_clip("a1", 10.0, 20.0, timeline_start=13.0)  # 3s gap
    suggestions = suggest_beat_boundaries(core.project, FPS)
    assert len(suggestions) == 1
    # Gap is frame 300..390 (10s to 13s)
    assert suggestions[0].start_frame == 300
    assert suggestions[0].end_frame == 390


def test_standard_beat_kinds_complete():
    expected = {"setup", "inciting_incident", "rising_action", "midpoint",
                "climax", "falling_action", "resolution", "denouement"}
    assert expected.issubset(set(STANDARD_BEAT_KINDS))
