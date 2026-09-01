"""GUI-03R6-A: Static architectural guard.

The audit found 6 places where the GUI compared playheadFrame (frames)
against c.timeline_range.start/end (seconds from /project). This guard
fails when such comparisons reappear in the edit-surface files.

The approved sanitizer: convert seconds → frames at the boundary
via `clipFramesFromSec(clip, fps)` from gui/src/frames.ts. The
helper uses `roundHalfAwayFromZero` (NOT Math.round) so the
rounding policy matches every other edit-coord operation.

Forbidden pattern in `EDIT_SURFACE` files:

    <frame-var>  (<|<=|>|>=|===|!==|==)  .timeline_range.(start|end)

where frame-var ∈ {playheadFrame, playhead, sourceFrame, nowFrame,
                   lastPreviewFrame, preSnapFrame}.

Permitted: `clipFramesFromSec(c, fps).startFrame` (helper result);
display-only `.timeline_range.start.toFixed(1)` (no comparison).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
GUI_SRC = ROOT / "gui" / "src"

EDIT_SURFACE = {
    GUI_SRC / "components" / "PreviewPlayer.tsx",
    GUI_SRC / "App.tsx",
    GUI_SRC / "components" / "ClipBlock.tsx",
}

# Frame-domain variables (LHS of the comparison). The RHS is the
# legacy-seconds timeline_range field. Any line matching both halves
# is a regression — must be converted via clipFramesFromSec first.
FRAME_VARS = (
    "playheadFrame", "playhead", "sourceFrame", "nowFrame",
    "lastPreviewFrame", "preSnapFrame", "authoritativeSnapFrame",
    "finalFrame", "candidateFrame", "lastCandidateFrame",
    "origStartFrame", "origEndFrame",
)
COMPARISON_OPS = r"(?:>=|<=|>|<|===|!==|==)"
RANGE_FIELD = r"\.timeline_range\.(?:start|end)"

# Build a regex that matches "<framevar> <op> <something> .timeline_range.(start|end)".
# We accept any non-newline content between the operator and the field
# (could be `c.timeline_range.start`, `selClip.timeline_range.end`, etc.).
PATTERN = re.compile(
    rf"\b(?:{'|'.join(FRAME_VARS)})\b\s*{COMPARISON_OPS}\s*[^.\n]*?{RANGE_FIELD}"
)


def _strip_comments_and_strings(src: str) -> str:
    """Remove TS comments and template-literal interpolations."""
    out = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)),
                 src, flags=re.DOTALL)
    out = re.sub(r"//[^\n]*", "", out)
    out = re.sub(r"\$\{[^}]*\.timeline_range\.[^}]*\}", "DISPLAY_TR", out)
    return out


def test_no_legacy_seconds_compare_in_edit_surface() -> None:
    violations: list[str] = []
    for path in EDIT_SURFACE:
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8")
        cleaned = _strip_comments_and_strings(raw)
        for i, (orig_line, clean_line) in enumerate(
            zip(raw.splitlines(), cleaned.splitlines()), start=1,
        ):
            if PATTERN.search(clean_line):
                violations.append(f"{path}:{i}: {orig_line.strip()}")
    assert not violations, (
        "GUI-03R6-A architectural guard violations (frame-var vs "
        "seconds timeline_range):\n" + "\n".join(violations)
        + "\n\nUse `clipFramesFromSec(clip, fps).startFrame / "
        ".endFrame` to cross the seconds↔frames boundary."
    )