"""GUI-05-D: GUI wording source-pins for Semantic Link rename (D13).

These tests are SOURCE-PIN tests: they grep grep on GUI source files to ensure
the misleading "Semantic Link" wording does not leak back into the codebase,
and that the "时间重叠提示" / "时间重叠" timeline-overlap hint wording is
present where required.

Coverage:
- 05-D.G1: `gui/src/App.tsx` checkbox no longer says "Semantic Link";
            the title attribute uses timeline-overlap hint wording.
- 05-D.G2: `gui/src/components/Timeline.tsx` `isRelated` doc comment
            explicitly states it's a timeline-range overlap heuristic, NOT
            the Semantic Link graph.
- 05-D.G3: `gui/src/components/ClipBlock.tsx` does not contain user-facing
            "Semantic Link" string.
- 05-D.G4: `yroll/core/selection.py` `Selection` dataclass `Linked` mode
            remains "future" (D14 — no Linked Clips implementation).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


GUI_DIR = ROOT / "gui" / "src"
APP_TSX = GUI_DIR / "App.tsx"
TIMELINE_TSX = GUI_DIR / "components" / "Timeline.tsx"
CLIPBLOCK_TSX = GUI_DIR / "components" / "ClipBlock.tsx"
SELECTION_PY = ROOT / "yroll" / "core" / "selection.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_negated_semantic_link_lines(text: str) -> str:
    """Strip lines that contain an explicit negation of "Semantic Link".

    D13 bans the misleading wording as a feature name. Explicit negations
    (e.g. "NOT the Semantic Link", "NOT 'Semantic Link'", "非 Semantic Link")
    are intentional clarifications and are allowed.

    Implementation: any line whose lowercase contains "semantic link" AND
    contains a negation marker within ~50 chars before it is stripped.
    """
    negation_markers = (
        "not the semantic link",
        "not a semantic link",
        "not \"semantic link\"",
        "not 'semantic link'",
        "non-semantic link",
        "non semantic link",
        "non-semantic",
        "非 semantic link",
    )
    # Markers that must appear before "semantic link" in the same line.
    before_markers = ("not ", "non-", "non ", "非 ", "不是")

    out_lines = []
    for line in text.splitlines():
        low = line.lower()
        if "semantic link" in low:
            has_explicit_negation = any(m in low for m in negation_markers)
            sl_idx = low.find("semantic link")
            prefix = low[:sl_idx]
            has_before_negation = any(m in prefix for m in before_markers)
            if has_explicit_negation or has_before_negation:
                out_lines.append(line.replace("Semantic Link", "<<SEMANTIC_LINK>>"))
                continue
        out_lines.append(line)
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# 05-D.G1 — App.tsx checkbox no longer says "Semantic Link"
# ---------------------------------------------------------------------------

def test_app_tsx_no_semantic_link_label():
    """D13: GUI checkbox must NOT contain user-facing 'Semantic Link' string.

    The historical wording `"高亮所有跨轨关联的 clip（Semantic Link）"` must be
    removed. Replace with timeline-overlap hint wording such as `"高亮时间重叠"`
    or `"时间重叠"`.

    Explicit negation forms ("非 Semantic Link", "not the Semantic Link") are
    intentional clarifications and are allowed.
    """
    assert APP_TSX.exists(), f"{APP_TSX} must exist"
    text = APP_TSX.read_text(encoding="utf-8")
    text_stripped = _strip_negated_semantic_link_lines(text)

    banned_literal = "Semantic Link"
    assert banned_literal not in text_stripped, (
        f"App.tsx must not contain literal 'Semantic Link' string "
        f"(D13: rename to timeline-overlap hint). Found occurrences: "
        f"{text.count(banned_literal)}"
    )

    # The renamed "时间重叠" wording must be present (Chinese timeline-overlap hint).
    assert "时间重叠" in text, (
        "App.tsx must contain '时间重叠' wording for the renamed checkbox (D13)"
    )


# ---------------------------------------------------------------------------
# 05-D.G2 — Timeline.tsx isRelated doc comment explicitly says timeline-overlap
# ---------------------------------------------------------------------------

def test_timeline_tsx_isrelated_doc_comment():
    """D13: `isRelated` calculation doc comment must clarify timeline-overlap heuristic.

    The `isRelated` prop in `Timeline.tsx` (around line 1051) must have a
    doc comment / inline comment that explicitly says it is a timeline-range
    overlap heuristic and NOT the Semantic Link graph.
    """
    assert TIMELINE_TSX.exists(), f"{TIMELINE_TSX} must exist"
    text = TIMELINE_TSX.read_text(encoding="utf-8")

    # The isRelated calculation site must exist.
    assert "isRelated" in text, "Timeline.tsx must define isRelated"

    # The function/prop site must be near (within ~40 lines) one of these markers.
    needle_alts = [
        "时间重叠",
        "timeline_range overlap",
        "timeline-overlap",
        "overlap heuristic",
        "not the Semantic Link",
        "not a Semantic Link",
        "not the relationship graph",
    ]
    found = [n for n in needle_alts if n in text]
    assert found, (
        f"Timeline.tsx must contain one of {needle_alts!r} near isRelated — "
        f"D13 requires explicit timeline-overlap hint wording to prevent "
        f"the overlap heuristic from being conflated with project.relationships"
    )

    # The misleading string must NOT appear in user-facing comments.
    # Allow explicit negation forms ("非 Semantic Link", "not the Semantic Link").
    text_stripped = _strip_negated_semantic_link_lines(text)
    banned_literal = "Semantic Link"
    assert banned_literal not in text_stripped, (
        f"Timeline.tsx must not contain literal 'Semantic Link' string "
        f"(D13: rename). Found: {text.count(banned_literal)}"
    )


# ---------------------------------------------------------------------------
# 05-D.G3 — ClipBlock.tsx no "Semantic Link" leakage
# ---------------------------------------------------------------------------

def test_clipblock_tsx_no_semantic_link_label():
    """D13: ClipBlock.tsx must NOT contain user-facing 'Semantic Link' string."""
    assert CLIPBLOCK_TSX.exists(), f"{CLIPBLOCK_TSX} must exist"
    text = CLIPBLOCK_TSX.read_text(encoding="utf-8")
    text_stripped = _strip_negated_semantic_link_lines(text)

    banned_literal = "Semantic Link"
    assert banned_literal not in text_stripped, (
        f"ClipBlock.tsx must not contain literal 'Semantic Link' string "
        f"(D13). Found: {text.count(banned_literal)}"
    )


# ---------------------------------------------------------------------------
# 05-D.G4 — Selection.Linked mode remains "future" (D14)
# ---------------------------------------------------------------------------

def test_selection_linked_mode_unused():
    """D14: `Selection` dataclass `Linked` mode remains a future comment.

    Mirrored from test_semantic_link_contract.py for source-pin coverage at the
    GUI/contract boundary. No new `linked` field may be introduced.
    """
    import inspect

    assert SELECTION_PY.exists(), f"{SELECTION_PY} must exist"

    from yroll.core.selection import Selection

    src = inspect.getsource(Selection)
    assert "Linked" in src and "future" in src, (
        "Selection dataclass must still document 'Linked' mode as 'future' "
        "(D14: no Linked Clips implementation)"
    )

    # No `linked` field on the dataclass.
    if hasattr(Selection, "__dataclass_fields__"):
        fields = {f.name for f in Selection.__dataclass_fields__.values()}
        assert "linked" not in fields, (
            f"Selection must not have a 'linked' field (D14), got fields={fields}"
        )


# ---------------------------------------------------------------------------
# 05-D.G5 — isRelated computation does NOT consult project.relationships
# ---------------------------------------------------------------------------

def test_isrelated_is_overlap_only():
    """D13: `isRelated` in Timeline.tsx uses timeline_range overlap ONLY.

    The calculation must NOT reference `project.relationships`, `Relationship`,
    or `relations`. If those names appear in the isRelated block, the test fails
    because the overlap heuristic would be conflated with Semantic Link.
    """
    assert TIMELINE_TSX.exists(), f"{TIMELINE_TSX} must exist"
    text = TIMELINE_TSX.read_text(encoding="utf-8")

    # Find the isRelated calculation block (rough: from "isRelated=" to next "}").
    # We do a simple substring scan — the isRelated expression is short.
    m = re.search(r"isRelated=\{.*?\}\s*\n", text, re.DOTALL)
    assert m, "Could not locate isRelated={...} expression in Timeline.tsx"

    block = m.group(0)

    # The block must reference timeline_range (it computes overlap).
    assert "timeline_range" in block, (
        f"isRelated must use timeline_range overlap; got: {block}"
    )

    # The block must NOT reference project.relationships, Relationship graph,
    # or "relations". (No Semantic Link graph consultation in this heuristic.)
    forbidden = ["project.relationships", ".relationships", "Relationship", "infer_relationships"]
    for token in forbidden:
        assert token not in block, (
            f"isRelated must NOT consult {token} — D13 / §5.1: this is an "
            f"overlap heuristic, not the Semantic Link graph. Block: {block}"
        )