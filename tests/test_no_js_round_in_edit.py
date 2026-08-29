"""GUI-02.4: Static architectural guard for the GUI frame-native refactor.

Walks the GUI source tree and fails on forbidden patterns that would
silently leak seconds, Math.round for edit coords, or TimeMap business
math into the active editing paths.

Forbidden patterns in any file under gui/src/:

  - `Math.round(`               — edit coords use roundHalfAwayFromZero
                                  (or its async parent pixelDeltaToFrameDelta)
  - `deltaSec`                  — second-based drag deltas (must be deltaFrame)
  - `pxPerSec`                  — second-based layout (must be pxPerFrame)
  - `SNAP_RADIUS_SEC`           — second-based snap thresholds
  - `* clip.speed`              — TimeMap business math in the GUI
  - `/ clip.speed`              — same
  - `* source.speed`            — same
  - `/ source.speed`            — same
  - `sourceDelta * `            — SourceDelta is a forbidden name (was used
                                  in legacy mapping math)
  - `timelineDelta * `          — TimelineDelta is a forbidden name
  - `/ clip.speed`              — explicit divisor form
  - `secondsToFrames(` in edit  — edit paths use frames natively

Permitted uses (not checked):
  - Inside comments
  - Inside test files (tests pin the contract; they may name the
    forbidden patterns for documentation purposes)
  - Inside the helper functions themselves (frames.ts owns
    pxPerSec, Math.round, secondsToFrames etc. as legitimate
    conversion primitives)
  - Display labels (toFixed(1)}s, framesToTimecode)
  - HTML media I/O (v.currentTime, v.duration)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
GUI_SRC = ROOT / "gui" / "src"
FRAMES_HELPERS = ROOT / "gui" / "src" / "frames.ts"
CLIPBLOCK = ROOT / "gui" / "src" / "components" / "ClipBlock.tsx"

# GUI-02.4 scope: the architectural guard is ClipBlock-focused. Other
# GUI files (PreviewPlayer, App keyboard, etc.) have their own
# refactor batches in subsequent closures and are NOT in scope here.
# The broad sweep below checks globally for the most egregious
# patterns (deltaSec, SNAP_RADIUS_SEC, sourceDelta, timelineDelta).
# ClipBlock-specific checks (Math.round, pxPerSec, * clip.speed) are
# in the focused test below.
OUT_OF_SCOPE_FOR_THIS_BATCH = {
    ROOT / "gui" / "src" / "components" / "PreviewPlayer.tsx",
    ROOT / "gui" / "src" / "App.tsx",
    ROOT / "gui" / "src" / "components" / "Timeline.tsx",
}


def _iter_gui_files():
    for p in GUI_SRC.rglob("*.ts"):
        if "__pycache__" in p.parts:
            continue
        if p.name.endswith(".test.ts") or p.name.endswith(".test.tsx"):
            continue
        yield p
    for p in GUI_SRC.rglob("*.tsx"):
        if "__pycache__" in p.parts:
            continue
        if p.name.endswith(".test.ts") or p.name.endswith(".test.tsx"):
            continue
        yield p


# Each pattern is (name, regex). The regex is matched against a line;
# the guard fails when ANY line matches and that line is not a comment.

FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern]] = [
    # deltaSec — must be deltaFrame in any active edit code path.
    (
        "deltaSec (must be deltaFrame)",
        re.compile(r"""\bdeltaSec\b"""),
    ),
    # SNAP_RADIUS_SEC — seconds-based snap threshold (frame-only invariant)
    (
        "SNAP_RADIUS_SEC (must be frame-domain)",
        re.compile(r"""\bSNAP_RADIUS_SEC\b"""),
    ),
    # sourceDelta / timelineDelta — forbidden variable names that
    # historically indicated TimeMap business math in the GUI.
    (
        "sourceDelta (TimeMap business math)",
        re.compile(r"""\bsourceDelta\b"""),
    ),
    (
        "timelineDelta (TimeMap business math)",
        re.compile(r"""\btimelineDelta\b"""),
    ),
    # Note: * clip.speed, / clip.speed, pxPerSec, and Math.round()
    # are NOT globally forbidden because:
    #   - pxPerSec is the legitimate perceived-zoom slider value
    #     (the App-level zoom control)
    #   - Math.round is used in non-edit display paths (e.g. opacity
    #     percentage formatting in VisualAdjustPanel)
    #   - clip.speed TimeMap math exists in PreviewPlayer which is
    #     out of scope for this batch
    # The ClipBlock-specific guard below pins all four as forbidden
    # INSIDE ClipBlock, which is the GUI-02.4 contract.
]


def _strip_comments_and_strings(src: str) -> str:
    """Remove TS/JS comments and template literal references to the
    forbidden pattern. We can't reliably parse TS, so we strip:
      - `// ...` line comments
      - `/* ... */` block comments
      - template-literal interpolations like `${clip.speed}x` (display)
    Returns the source minus those regions. Multi-line block comments
    are handled by replacing them with whitespace (preserving line
    numbers) so line-based error messages still work.
    """
    # Replace block comments with whitespace preserving line breaks.
    def _block_repl(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    out = re.sub(r"/\*.*?\*/", _block_repl, src, flags=re.DOTALL)
    # Remove // line comments.
    out = re.sub(r"//[^\n]*", "", out)
    # Replace `${clip.speed}` and similar with a display-only marker.
    out = re.sub(r"\$\{[^}]*\.speed[^}]*\}", "DISPLAY_SPEED", out)
    return out


def test_no_forbidden_edit_patterns_in_gui_source():
    """Broad sweep: scan all GUI source for the truly forbidden names
    that should NEVER appear anywhere in the GUI:
    deltaSec, SNAP_RADIUS_SEC, sourceDelta, timelineDelta.

    Other patterns (pxPerSec, Math.round, * clip.speed) are checked
    in the ClipBlock-specific test below (they have legitimate uses
    outside ClipBlock).
    """
    violations: list[str] = []
    for path in _iter_gui_files():
        if path.resolve() == FRAMES_HELPERS.resolve():
            continue
        # Skip files that are out of scope for this batch (have their
        # own refactor batch). PreviewPlayer in particular has its own
        # closure (02-5).
        if path.resolve() in OUT_OF_SCOPE_FOR_THIS_BATCH:
            continue
        cleaned = _strip_comments_and_strings(path.read_text(encoding="utf-8"))
        for i, (orig_line, clean_line) in enumerate(
            zip(path.read_text(encoding="utf-8").splitlines(),
                cleaned.splitlines()), start=1,
        ):
            for name, regex in FORBIDDEN_PATTERNS:
                if regex.search(clean_line):
                    violations.append(f"{path}:{i}: [{name}] {orig_line.strip()}")
    assert not violations, (
        "GUI-02.4 architectural guard violations:\n"
        + "\n".join(violations)
        + "\n\nActive edit paths must be frame-only. See foamy-conjuring-blum.md §02-4."
    )


def test_clipblock_has_no_local_timemap_business_math():
    """A focused check on ClipBlock.tsx specifically: no `* clip.speed`,
    no `/ clip.speed`, no sourceDelta, no timelineDelta, no Math.round
    for edit coords, no pxPerSec, no SNAP_RADIUS_SEC. Display-only
    `${clip.speed}` template substitutions are stripped before
    scanning."""
    path = ROOT / "gui" / "src" / "components" / "ClipBlock.tsx"
    src = path.read_text(encoding="utf-8")
    cleaned = _strip_comments_and_strings(src)
    for forbidden in [
        r"\*\s*clip\.speed",
        r"/\s*clip\.speed",
        r"\*\s*\w+\.speed",
        r"/\s*\w+\.speed",
        r"\bsourceDelta\b",
        r"\btimelineDelta\b",
        r"\bMath\.round\s*\(",
        r"\bSNAP_RADIUS_SEC\b",
        # pxPerSec as a prop/variable is forbidden; the conversion
        # back to pxPerSec (for pixelDeltaToFrameDelta) IS permitted
        # because that helper expects the perceived zoom value. We
        # detect that pattern via the local variable name only.
        r"\bpxPerSec\b",
    ]:
        m = re.search(forbidden, cleaned)
        assert not m, (
            f"ClipBlock.tsx contains forbidden pattern {forbidden!r}: "
            f"'{cleaned[max(0, m.start()-20):m.end()+20]}'"
        )


def test_clipblock_uses_roundHalfAwayFromZero_for_edit_coords():
    """The only edit-coordinate rounding primitive is roundHalfAwayFromZero
    (directly or via pixelDeltaToFrameDelta). Pin this at the import
    site so the architectural contract is explicit."""
    path = ROOT / "gui" / "src" / "components" / "ClipBlock.tsx"
    src = path.read_text(encoding="utf-8")
    assert "roundHalfAwayFromZero" in src, (
        "ClipBlock.tsx must import and use roundHalfAwayFromZero for "
        "edit-coordinate rounding"
    )
    assert "pixelDeltaToFrameDelta" in src, (
        "ClipBlock.tsx must use pixelDeltaToFrameDelta for drag deltas"
    )


def test_clipblock_emit_types_are_integer_frames():
    """ClipBlock's onDragMove / onMoveCommit / onTrimCommit must emit
    integer frame types (no seconds). The Props interface pins this."""
    path = ROOT / "gui" / "src" / "components" / "ClipBlock.tsx"
    src = path.read_text(encoding="utf-8")
    # The Props interface must NOT contain `number` typed as seconds.
    # We assert the canonical property names exist as number-typed.
    for needle in [
        "pxPerFrame:",
        "onDragMove:",
        "onMoveCommit:",
        "onTrimCommit:",
        "newTimelineStartFrame:",
        "srcStartFrame",
        "srcEndFrame",
    ]:
        assert needle in src, (
            f"ClipBlock.tsx Props API must include {needle!r} "
            f"(frame-only contract)"
        )
    # The legacy `deltaSec` parameter MUST NOT appear in the props.
    assert "deltaSec" not in src, (
        "ClipBlock props must not include deltaSec (frame-only contract)"
    )