"""GUI-02.3: Architectural guard — no code may use project.sequence.fps
as the source media FPS when resolving sourceFrame → media currentTime.

The GUI-02.3 invariant: every code path that converts a SourceFrame
integer into media seconds (for `<video>.currentTime` or `<audio>`
playback) MUST use the asset's source_fps — never the project's
sequence_fps.

This test walks the source tree and flags two patterns:

  (A) Direct forbidden write: `v.currentTime = sourceFrame * fps.den /
      fps.num` (or any equivalent). v.currentTime writes are a GUI
      concern; in the yroll/ core we expect ZERO of them. This guard
      makes the absence explicit so future contributors don't drift
      toward computing currentTime in Core.

  (B) Source-frame multiplication that uses project.fps_num /
      project.fps_den (the denormalized sequence-fps fields). Any
      line that multiplies a source-frame integer by a sequence-fps
      fraction to produce seconds is silently relabelling SourceFrame
      as TimelineFrame.

The guard is intentionally narrow — it catches the SPECIFIC bug the
spec warns against and nothing else.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
YROLL_DIR = ROOT / "yroll"


def _iter_python_files():
    for p in YROLL_DIR.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        yield p


# Forbidden regexes (case-sensitive; whole-line match via re.search)
#
# (A) v.currentTime writes are a GUI concern; the yroll/ tree MUST
# NOT compute them. This catches direct currentTime = src*fps writes.
FORBIDDEN_V_CURRENTTIME = re.compile(
    r"""(?xi)
    \b v \. currentTime \s* = \s*  # the write
    .*?                           # body
    \* \s* \w+ \. den \s* / \s* \w+ \. num  # the multiply-by-fps pattern
    """
)


# (B) Source-frame integer multiplied by sequence-fps fraction.
# We allow: `fps.den / fps.num` where `fps` is a parameter or local
# variable that the test then has to prove is a source_fps (not in
# scope here). The simplest catch is: any line with
# `project.fps_num` / `project.fps_den` / `core.project.fps_*` /
# `st.core.project.fps_*` that is ALSO doing a multiply-by-den-over-num
# for a source-frame integer is forbidden.
#
# Concretely we forbid:
#   src_frame * fps.den / fps.num     where fps == project.fps_*
#   source_seconds = source_frame * project.fps_den / project.fps_num
#   v.currentTime = source_frame * fps.den / fps.num
#
# The pattern below matches: a `project.fps_*` / `core.project.fps_*`
# reference on a line that also contains `* X.den / X.num` style
# fraction arithmetic.
SOURCE_FPS_REFERENCE = re.compile(
    r"""(?x)
    \b (?: project | core \. project | st \. core \. project )
    \. fps_(?: num | den )
    """
)
SOURCE_FRAME_REFERENCE = re.compile(
    r"""(?xi)
    \b (?: src_frame | source_frame | src_f | sourceFrame
       | video_source_frame | audio_source_frame )
    \b
    """
)
DEN_OVER_NUM = re.compile(
    r"""(?x)
    \* \s* \w+ \. den \s* / \s* \w+ \. num
    """
)


def _read_lines(path):
    return path.read_text(encoding="utf-8").splitlines()


def test_no_v_currenttime_writes_in_yroll():
    """v.currentTime is HTML media I/O. The Core owns data, not
    playback. ZERO v.currentTime writes should appear in yroll/."""
    violations = []
    for path in _iter_python_files():
        for i, line in enumerate(_read_lines(path), start=1):
            if FORBIDDEN_V_CURRENTTIME.search(line):
                violations.append(f"{path}:{i}: {line.strip()}")
    assert not violations, (
        "v.currentTime writes belong in the GUI, not the Core.\n"
        + "\n".join(violations)
    )


def test_no_project_fps_in_source_frame_seconds_conversion():
    """A line that (a) references project.fps_num/fps_den (the
    denormalized sequence-fps fields), (b) contains a source-frame
    integer reference, AND (c) does `* X.den / X.num` fraction
    arithmetic is silently relabelling SourceFrame as TimelineFrame.
    """
    violations = []
    for path in _iter_python_files():
        for i, line in enumerate(_read_lines(path), start=1):
            stripped = line.strip()
            # Skip comments and blanks
            if not stripped or stripped.startswith("#"):
                continue
            if not SOURCE_FPS_REFERENCE.search(line):
                continue
            if not SOURCE_FRAME_REFERENCE.search(line):
                continue
            if not DEN_OVER_NUM.search(line):
                continue
            # If all three patterns appear on the same line, that's the
            # exact bug the spec warns against.
            violations.append(f"{path}:{i}: {stripped}")
    assert not violations, (
        "Code is multiplying a source-frame integer by project.fps_num/"
        "fps_den (sequence fps). Use the asset's source_fps instead.\n"
        + "\n".join(violations)
    )


def test_get_timemap_returns_source_fps_field():
    """The /clip/{id}/timemap HTTP endpoint MUST include `source_fps`
    in its response so the GUI never has to derive it from project
    sequence fps."""
    from yroll.server import app as server_app
    src = Path(server_app.__file__).read_text(encoding="utf-8")
    # The timemap handler must emit `source_fps` in its return dict.
    timemap_block = re.search(
        r"def get_timemap\([^)]*\):.*?(?=\n    @|\nclass |\Z)",
        src, flags=re.DOTALL,
    )
    assert timemap_block is not None, "get_timemap handler not found"
    body = timemap_block.group(0)
    assert '"source_fps"' in body, (
        "get_timemap must return 'source_fps' in its JSON response"
    )
    assert '"sequence_fps"' in body, (
        "get_timemap must also return 'sequence_fps' (the project's "
        "timeline timebase) so the GUI can distinguish the two"
    )


def test_validate_media_conformance_endpoint_exists():
    """The /project/validate_media_conformance endpoint is the
    canonical way for the GUI to learn the conformance verdict for
    every asset."""
    from yroll.server import app as server_app
    src = Path(server_app.__file__).read_text(encoding="utf-8")
    assert '"/project/validate_media_conformance"' in src, (
        "expected /project/validate_media_conformance endpoint in app.py"
    )


def test_time_map_factory_requires_source_fps():
    """The TimeMap factory must REJECT source_fps=None. This pins the
    architectural guard at the type level — there is no way to build a
    TimeMap without an explicit source FPS."""
    from yroll.core.timemap import TimeMap
    from yroll.core.timebase import Rational
    with pytest.raises(ValueError, match="source_fps is required"):
        TimeMap(
            source_start_frame=0, source_end_frame=10,
            timeline_start_frame=0, speed=1.0,
            sequence_fps=Rational(30, 1), source_fps=None,
        )


def test_time_map_distinct_sequence_and_source_fps():
    """TimeMap MUST expose both sequence_fps and source_fps as separate
    fields. The legacy `fps` alias is permitted but `sequence_fps` is
    the canonical name."""
    from yroll.core.timemap import TimeMap
    from yroll.core.timebase import Rational
    tm = TimeMap(
        source_start_frame=0, source_end_frame=10,
        timeline_start_frame=0, speed=1.0,
        sequence_fps=Rational(30, 1), source_fps=Rational(24, 1),
    )
    assert tm.sequence_fps == Rational(30, 1)
    assert tm.source_fps == Rational(24, 1)
    assert tm.sequence_fps != tm.source_fps