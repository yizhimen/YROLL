"""GUI-02: Project.sequence save/reload consistency.

The canonical accessor is `Project.sequence`. The flat
fps_num / fps_den / width / height fields are denormalized
storage. They MUST stay in sync with `sequence` across save/reload
cycles — otherwise a legacy v0.1 reader would see a different
timebase than the GUI.

These tests pin the sync contract.
"""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational, to_timecode


def _new_project(td: Path) -> ProjectCore:
    ProjectCore.create(str(td), "save-reload")
    return ProjectCore.open(td / "save-reload")


def test_default_sequence_after_create():
    with tempfile.TemporaryDirectory() as td:
        core = _new_project(Path(td))
        # Default sequence is 30 fps, SMPTE non-drop
        assert core.project.sequence.fps == Rational(30, 1)
        assert core.project.sequence.drop_frame is False
        assert core.project.sequence.timecode_format == "SMPTE"
        # Flat fields synced
        assert core.project.fps_num == 30
        assert core.project.fps_den == 1


def test_modify_sequence_syncs_flat_fields_on_save():
    """When Project.sequence changes, save_state() must update the
    flat denormalized fields too."""
    with tempfile.TemporaryDirectory() as td:
        core = _new_project(Path(td))
        core.project.sequence.fps = Rational(30000, 1001)
        core.project.sequence.drop_frame = True
        core.project.sequence.timecode_format = "DF"
        core.project.sequence.width = 3840
        core.project.sequence.height = 2160
        core.save_state()

        # Reload
        proj = ProjectCore.open(Path(td) / "save-reload").project
        assert proj.sequence.fps == Rational(30000, 1001)
        assert proj.sequence.drop_frame is True
        assert proj.sequence.timecode_format == "DF"
        # Flat fields match
        assert proj.fps_num == 30000
        assert proj.fps_den == 1001
        assert proj.width == 3840
        assert proj.height == 2160


def test_reload_from_legacy_v01_file_builds_sequence():
    """A v0.1 current.json without a `sequence` field must load
    correctly by building the Sequence from the flat fields."""
    with tempfile.TemporaryDirectory() as td:
        proj = Path(td) / "legacy"
        proj.mkdir()
        # Write a v0.1-style current.json (no `sequence` key)
        (proj / "current.json").write_text(json.dumps({
            "manifest_version": "0.1",
            "project_id": "legacy",
            "name": "legacy",
            "fps_num": 24000,
            "fps_den": 1001,
            "width": 1280,
            "height": 720,
            "assets": [],
            "timeline": {"timeline_id": "main", "tracks": []},
            "clips": {},
        }), encoding="utf-8")
        core = ProjectCore.open(proj)
        assert core.project.sequence.fps == Rational(24000, 1001)
        assert core.project.sequence.width == 1280
        assert core.project.sequence.height == 720
        # The flat fields are also there (denormalized)
        assert core.project.fps_num == 24000
        assert core.project.fps_den == 1001


def test_reload_saves_sequence_id():
    """Sequence.sequence_id is generated at construction and
    preserved across save/reload (so the GUI can track it)."""
    with tempfile.TemporaryDirectory() as td:
        core = _new_project(Path(td))
        sid1 = core.project.sequence.sequence_id
        assert sid1
        core.save_state()
        proj = ProjectCore.open(Path(td) / "save-reload").project
        assert proj.sequence.sequence_id == sid1


def test_reload_preserves_pinned_df_timecode_after_round_trip():
    """End-to-end: build a project with DF 30000/1001, save, reload,
    assert the timecode at frame 17982 is 00:10:00;00."""
    with tempfile.TemporaryDirectory() as td:
        core = _new_project(Path(td))
        core.project.sequence.fps = Rational(30000, 1001)
        core.project.sequence.drop_frame = True
        core.save_state()
        proj = ProjectCore.open(Path(td) / "save-reload").project
        assert to_timecode(17982, proj.sequence.fps, drop_frame=True) == "00:10:00;00"
        assert to_timecode(0, proj.sequence.fps, drop_frame=True) == "00:00:00;00"
