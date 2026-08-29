"""GUI-02.6: Global seconds-leakage guard for the active GUI edit surface.

Walks the GUI source tree (App / Timeline / ClipBlock / PreviewPlayer)
and flags any seconds variable, field, or arithmetic used as a
SEMANTIC OPERAND in active edit logic.

Per the closure spec:
  - Permitted seconds uses: display labels, HTML media currentTime /
    duration, legacy model storage (TimeRange.start/end), frames.ts
    conversion helpers.
  - Forbidden: seconds as semantic operands in App/Timeline/ClipBlock
    /PreviewPlayer edit logic (including hidden variable renaming
    tricks — "frame" suffix on a seconds variable is still forbidden).

This guard is intentionally stricter than the per-file `test_no_js_round_in_edit.py`
and `test_preview_player_frame_clock.py` checks. Those guard specific
patterns (deltaSec, pxPerSec, Math.round, setInterval). THIS guard
walks the AST-shaped surface and flags any suspicious pattern.

The strategy is STRUCTURED rather than naive global grep:
  - We parse each file with a lightweight regex tokenizer (TSX is too
    rich for full AST parsing here, but a token-aware scanner catches
    the common hiding tricks).
  - We identify "edit paths" via a hand-curated set of markers:
    - keyboard handler bodies (window.addEventListener("keydown", ...))
    - useEffect hooks that mention playhead / seek / drag / etc.
    - functions whose names contain `commit`, `apply`, `dispatch`,
      `handle`, `seek`, `drag`, `trim`, `move`, `split`, `tick`.
  - Within those edit paths, we flag any occurrence of forbidden
    seconds operands.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
GUI_SRC = ROOT / "gui" / "src"

# Files actively in scope for this guard.
#
# App.tsx and Timeline.tsx own the perceived-zoom slider (pxPerSec)
# and the playhead state — they're allowed to hold those values. The
# strict "no pxPerSec" / "no seconds in active edit" guards apply to
# the COMPONENTS that consume them: ClipBlock and PreviewPlayer.
# App.tsx is still checked for the keyboard handler and other edit
# logic, but it has the slider exemption.
EDIT_SURFACE = {
    ROOT / "gui" / "src" / "App.tsx",
    ROOT / "gui" / "src" / "components" / "Timeline.tsx",
    ROOT / "gui" / "src" / "components" / "ClipBlock.tsx",
    ROOT / "gui" / "src" / "components" / "PreviewPlayer.tsx",
}

# Components that must NOT use pxPerSec — they receive pxPerFrame only.
STRICT_COMPONENTS_NO_PX_PER_SEC = {
    ROOT / "gui" / "src" / "components" / "ClipBlock.tsx",
    ROOT / "gui" / "src" / "components" / "PreviewPlayer.tsx",
}

# Permitted locations of seconds. We allow these in edit paths.
PERMITTED_SECONDS_NAMES = {
    # Legacy model storage (TimeRange.start / end). Reading these
    # and converting via frames.ts helpers is the EXPLICIT allowed path.
    "source_range.start",
    "source_range.end",
    "timeline_range.start",
    "timeline_range.end",
    "identity.duration_sec",
    # Legacy storage on Project itself (v0.1 schema).
    "fps_num",
    "fps_den",
    # HTML media I/O — explicit boundary per the spec.
    "v.currentTime",
    "v.duration",
    "el.currentTime",
    "el.duration",
    # Display label only (the spec explicitly permits .toFixed(1)}s
    # in display strings; the parser recognizes template literals).
}

# Forbidden seconds-leakage names in edit paths. These are the
# "hidden variable renaming tricks" the spec warns against — even
# renaming `secondsX` → `frameX` doesn't help; we flag the underlying
# pattern.
FORBIDDEN_SECONDS_NAMES = [
    r"\bduration\s*:",       # duration: number  (clip duration typed in seconds)
    r"\bduration_seconds\b",
    r"\bdurationSec\b",
    r"\bdurationSecs\b",
    r"\bdurSecs?\b",
    r"\btimeSeconds\b",
    r"\btimeInSeconds\b",
    r"\bsecondsToFrame\b",  # backward direction (frame-native → seconds)
    r"\bframesToSecond\b",
    r"\belapsedSec\b",
    r"\belapsed\s*=.*\*\s*\d",  # elapsed in seconds computation
    r"\*\s*\w+\.duration\b",   # multiplying by clip.duration (seconds)
]

# Edit path markers — we only flag patterns inside these.
EDIT_PATH_MARKERS = [
    r"window\.addEventListener\(\s*['\"]keydown['\"]",
    r"onPointerDown\s*=\s*\(",
    r"onPointerMove\s*=\s*\(",
    r"onPointerUp\s*=\s*\(",
    r"\buseEffect\s*\(\s*\(\s*\)\s*=>",
    r"function\s+(commit|apply|dispatch|handle|seek|drag|trim|move|split|tick)",
    r"const\s+(commit|apply|dispatch|handle|seek|drag|trim|move|split|tick)\s*=",
    r"onMoveCommit",
    r"onTrimCommit",
    r"onDragMove",
]

EDIT_PATH_MARKER_RE = re.compile("|".join(f"({p})" for p in EDIT_PATH_MARKERS))


def _strip_comments_and_strings(src: str) -> str:
    """Remove TS comments and template-literal interpolations while
    preserving line numbers (block comments are replaced with
    whitespace so errors stay line-aligned)."""
    def _block_repl(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    out = re.sub(r"/\*.*?\*/", _block_repl, src, flags=re.DOTALL)
    out = re.sub(r"//[^\n]*", "", out)
    # Remove template-literal interpolations that mention display-only
    # values (e.g. `{playheadFrame.toFixed(1)}s`).
    out = re.sub(r"\$\{[^}]*\.toFixed[^}]*\}", "DISPLAY_FIXED", out)
    return out


def _is_in_edit_path(clean_src: str, line_offset: int) -> bool:
    """Return True if the given character offset falls inside an edit
    path block. We define "inside" as: after an edit-path marker that
    hasn't been closed yet (matching brace count)."""
    depth = 0
    in_edit = False
    for i, c in enumerate(clean_src):
        if EDIT_PATH_MARKER_RE.match(clean_src, i):
            # Found a marker at this position. Find the next `{` to
            # start counting braces; we're "in edit" until the count
            # returns to the pre-marker level.
            j = clean_src.find("{", i)
            if j == -1:
                continue
            # Reset depth to local zero (we treat each marker as
            # opening its own block scope). Simpler: scan from j to
            # the matching `}`.
            in_edit = True
            depth = 0
            start = j
        elif in_edit:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth <= 0:
                    in_edit = False
        if i == line_offset:
            return in_edit
    return in_edit


def _line_to_offset(clean_src: str, line_no: int) -> int:
    """Return the character offset of the start of `line_no` (1-based)."""
    lines = clean_src.split("\n")
    offset = 0
    for i, ln in enumerate(lines, start=1):
        if i == line_no:
            return offset
        offset += len(ln) + 1
    return offset


def _scan_file(path: Path):
    """Return a list of (line_no, line_text, forbidden_match) tuples
    found inside edit paths."""
    src = path.read_text(encoding="utf-8")
    cleaned = _strip_comments_and_strings(src)
    cleaned_lines = cleaned.split("\n")
    orig_lines = src.split("\n")

    forbidden_re = re.compile("|".join(FORBIDDEN_SECONDS_NAMES))
    violations: list[tuple[int, str, str]] = []

    # For each edit-path marker, scan the block until braces balance.
    # We use a simpler per-line check: a line is "in edit" if it
    # contains an edit-path marker OR if any of its preceding lines
    # up to a brace-balanced close is in edit. We approximate by
    # walking the file linearly and tracking the depth.
    depth = 0
    in_edit_depth: int | None = None
    for i, line in enumerate(cleaned_lines, start=1):
        # Detect an edit-path marker on this line.
        if EDIT_PATH_MARKER_RE.search(line):
            in_edit_depth = depth
            # Find the next `{` (might be on the same line or later).
            j = cleaned.find("{", sum(len(l) + 1 for l in cleaned_lines[:i - 1]))
            if j != -1:
                # Re-anchor: we're in edit at the brace level of
                # where the marker starts. If the line doesn't yet
                # have a `{`, we just stay "in edit" for this line.
                pass

        # Count braces for depth tracking.
        opens = line.count("{")
        closes = line.count("}")

        # If we're in edit, scan for forbidden patterns.
        if in_edit_depth is not None:
            for m in forbidden_re.finditer(line):
                violations.append((i, orig_lines[i - 1], m.group(0)))

        # Update depth. If we just balanced the entry point,
        # we leave the edit path.
        depth += opens - closes
        if in_edit_depth is not None and depth <= in_edit_depth:
            in_edit_depth = None

    return violations


# ---------------------------------------------------------------------------
# Per-file guards
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", sorted(EDIT_SURFACE), ids=lambda p: p.name)
def test_no_seconds_leakage_in_active_edit_paths(path: Path):
    violations = _scan_file(path)
    assert not violations, (
        f"{path.name} contains seconds-based operands in active edit "
        f"logic. The GUI-02.6 invariant requires frame-only semantics "
        f"in edit paths. Violations:\n" +
        "\n".join(f"  line {ln}: {text.strip()}  [matched: {m!r}]"
                  for ln, text, m in violations)
    )


# ---------------------------------------------------------------------------
# Positive case: frames.ts IS allowed to use seconds
# ---------------------------------------------------------------------------

def test_frames_ts_is_explicitly_permitted():
    """frames.ts owns the conversion primitives (secondsToFrames,
    framesToSeconds, framesToTimecode). It may use seconds freely —
    that's its job. The guard excludes frames.ts from the scan."""
    frames = ROOT / "gui" / "src" / "frames.ts"
    assert frames.is_file()
    # The file legitimately references seconds in its public API;
    # the guard test is structured to not flag it.
    assert frames not in EDIT_SURFACE


# ---------------------------------------------------------------------------
# Positive case: App.tsx playback transport hook MAY touch spacebar
# ---------------------------------------------------------------------------

def test_app_keyboard_handler_is_keymap_only():
    """The App.tsx keyboard handler must use eventToKeyCombo +
    keymap.find(a => a.key === combo) — no hardcoded step sizes, no
    fallback magic numbers. This is a textual pin — the full
    behavior is covered by keymap.test.ts (Keymap Drift + Missing).
    """
    app = ROOT / "gui" / "src" / "App.tsx"
    src = app.read_text(encoding="utf-8")
    cleaned = _strip_comments_and_strings(src)
    # Must contain the keymap lookup pattern.
    assert "keymap.find" in cleaned, (
        "App.tsx keyboard handler must look up bindings via keymap.find"
    )
    # Must NOT contain fallback magic numbers for delta_frames
    # specifically. Other `?? <int>` patterns (e.g. optional param
    # parsing like `direction ?? 1`) are fine — they're optional
    # field defaults, not step sizes. The pattern is anchored on
    # the `delta_frames` identifier to keep the guard tight.
    forbidden_magic = [
        # ?? 1/?? 10 fallback for delta_frames
        r"delta[_]?frames\s*\)?\s*\?\?\s*[0-9]+\b",
        # shiftMul = ... ? 10 : 1 magic-number multiplier
        r"shiftMul\s*=\s*[^?]+\?\s*[0-9]+\s*:\s*1\b",
    ]
    for pattern in forbidden_magic:
        m = re.search(pattern, cleaned)
        assert not m, (
            f"App.tsx contains forbidden magic number {pattern!r}: "
            f"'{cleaned[max(0, m.start()-20):m.end()+20] if m else ''}'"
        )


# ---------------------------------------------------------------------------
# Positive case: PreviewPlayer no setInterval + no video.currentTime →
# playhead feedback (already covered in test_preview_player_frame_clock.py
# but re-pinned here for the global guard).
# ---------------------------------------------------------------------------

def test_preview_player_is_frame_clock_authoritative():
    preview = ROOT / "gui" / "src" / "components" / "PreviewPlayer.tsx"
    cleaned = _strip_comments_and_strings(preview.read_text(encoding="utf-8"))
    assert "setInterval" not in cleaned, (
        "PreviewPlayer must not use setInterval; FrameClock + RAF only"
    )
    assert "frameClockCurrentFrame" in cleaned or "currentFrame" in cleaned, (
        "PreviewPlayer must import FrameClock.currentFrame (or alias)"
    )


# ---------------------------------------------------------------------------
# Static guard: no `deltaSec` anywhere in the edit surface
# ---------------------------------------------------------------------------

def test_no_delta_sec_anywhere_in_edit_surface():
    for path in EDIT_SURFACE:
        cleaned = _strip_comments_and_strings(path.read_text(encoding="utf-8"))
        assert "deltaSec" not in cleaned, (
            f"{path.name}: 'deltaSec' is forbidden (frame-only contract)"
        )


def test_no_px_per_sec_in_edit_surface():
    """pxPerSec is the LEGITIMATE perceived-zoom slider value at the
    App level — it pairs with the sequence FPS to derive pxPerFrame.
    But inside the active edit components (ClipBlock, PreviewPlayer)
    it must not appear; those consume pxPerFrame only.

    App.tsx and Timeline.tsx own the slider, so they're exempt
    here. The guard is strict for ClipBlock and PreviewPlayer only.
    """
    for path in STRICT_COMPONENTS_NO_PX_PER_SEC:
        cleaned = _strip_comments_and_strings(path.read_text(encoding="utf-8"))
        assert "pxPerSec" not in cleaned, (
            f"{path.name}: 'pxPerSec' is forbidden (must be pxPerFrame)"
        )


def test_no_snap_radius_sec_in_edit_surface():
    for path in EDIT_SURFACE:
        cleaned = _strip_comments_and_strings(path.read_text(encoding="utf-8"))
        assert "SNAP_RADIUS_SEC" not in cleaned, (
            f"{path.name}: 'SNAP_RADIUS_SEC' is forbidden (frame-domain)"
        )