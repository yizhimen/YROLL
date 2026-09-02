"""GUI-05-D: Semantic Link contract — frozen behavior + regression guards.

This test file pins the Semantic Link contract documented in
`docs/SEMANTIC-LINK-BEHAVIOR.md`. Any change to the contract MUST update both
the doc and this test file together.

Coverage (D12 freeze + regression guards):
- 05-D.1: `move_clip` propagates STRONG relations (cross_shifted in Operation.after)
- 05-D.2: `move_selection` does NOT propagate STRONG relations (D12 frozen asymmetry)
- 05-D.3: `move_clip` with no STRONG relations → no cross_shifted
- 05-D.4: `infer_relationships` is idempotent (regression pin)
- 05-D.5: `move_clip` source-pinned to call `infer_relationships`
- 05-D.6: `move_selection` source-pinned to NOT call `infer_relationships`
- 05-D.9: `docs/SEMANTIC-LINK-BEHAVIOR.md` exists with all 7 required sections
          (D12, D14 explicitly stated; D13 rename documented)
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_link_test_project(tmp_path: Path):
    """Create a fresh project with: 1 video clip + 1 subtitle clip aligned in time.

    After `infer_relationships`, the subtitle has a `STRONG caption_of` link
    to the video. The two clips share a single overlap so the STRONG inference
    rule fires deterministically (text covers >50% of video range).
    """
    from yroll.core.commands import CommandLayer
    from yroll.core.manifest import Actor, TrackKind
    from yroll.core.project import ProjectCore

    proj = tmp_path / "link-contract"
    if proj.exists():
        shutil.rmtree(proj)
    core = ProjectCore.create(proj, "link-contract")
    cmd = CommandLayer(core, who=Actor.HUMAN)

    v = cmd.add_clip("asset-v", 0.0, 10.0, timeline_start=0.0, track_id="v1")
    cmd.add_track(TrackKind.TEXT, "t1")
    sub = cmd.add_clip("", 0.0, 9.0, timeline_start=1.0, track_id="t1")
    sub.context["text"] = "test subtitle"

    return core, cmd, v, sub


def _make_no_link_project(tmp_path: Path):
    """A project with one video clip but NO subtitle/audio companion.

    After `infer_relationships`, `project.relationships` is empty.
    """
    from yroll.core.commands import CommandLayer
    from yroll.core.manifest import Actor
    from yroll.core.project import ProjectCore

    proj = tmp_path / "no-link-contract"
    if proj.exists():
        shutil.rmtree(proj)
    core = ProjectCore.create(proj, "no-link-contract")
    cmd = CommandLayer(core, who=Actor.HUMAN)

    v = cmd.add_clip("asset-v", 0.0, 10.0, timeline_start=0.0, track_id="v1")

    return core, cmd, v


# ---------------------------------------------------------------------------
# 05-D.1 — move_clip propagates STRONG (cross_shifted in Operation.after)
# ---------------------------------------------------------------------------

def test_move_clip_propagates_strong(tmp_path: Path):
    """D12 — single-clip `move_clip` co-shifts STRONG partners.

    After `infer_relationships`, the subtitle has STRONG caption_of → video.
    `move_clip` shifts the video by +0.5s; the subtitle must shift by +0.5s.
    The Operation.after must carry `cross_shifted_count == 1`.
    """
    from yroll.core.links import infer_relationships

    core, cmd, v, sub = _make_link_test_project(tmp_path)
    core.save_state()
    infer_relationships(core.project)

    # Sanity: STRONG link must have been inferred.
    strong = [r for r in core.project.relationships
              if r.relation.value == "strong"]
    assert len(strong) >= 1, "fixture setup failed: no STRONG relation inferred"

    sub_start_before = sub.timeline_range.start
    v_start_before = v.timeline_range.start
    delta = 0.5

    op = cmd.move_clip(v.clip_id, new_timeline_start=v_start_before + delta,
                       why="contract test: move_clip propagates")

    sub_after = core.project.clips[sub.clip_id]
    assert abs(sub_after.timeline_range.start - (sub_start_before + delta)) < 1e-6, (
        f"subtitle must shift by +{delta}s, "
        f"got start={sub_after.timeline_range.start} expected={sub_start_before + delta}"
    )

    # Operation must record the propagation in after.cross_shifted_count.
    assert op.after.get("cross_shifted_count", 0) >= 1, (
        f"op.after.cross_shifted_count must be >=1, got {op.after.get('cross_shifted_count')}"
    )


# ---------------------------------------------------------------------------
# 05-D.2 — move_selection does NOT propagate STRONG (D12 frozen asymmetry)
# ---------------------------------------------------------------------------

def test_move_selection_does_not_propagate(tmp_path: Path):
    """D12 — multi-clip `move_selection` does NOT co-shift.

    Same fixture: STRONG caption_of → video is inferred. Selecting both clips
    via `Selection` and calling `move_selection(Selection.many([v, sub]), delta=+0.5s)`
    must move both by +0.5s, but must NOT introduce any cross-shifted logic
    beyond the per-clip translation. The Operation.after must NOT carry a
    `cross_shifted_count` key (no STRONG propagation in the move_selection path).
    """
    from yroll.core.links import infer_relationships
    from yroll.core.selection import Selection

    core, cmd, v, sub = _make_link_test_project(tmp_path)
    core.save_state()
    infer_relationships(core.project)

    # Sanity: STRONG link inferred (otherwise the test is inconclusive).
    assert any(r for r in core.project.relationships if r.relation.value == "strong"), \
        "fixture setup failed: no STRONG relation inferred"

    sub_start_before = sub.timeline_range.start
    v_start_before = v.timeline_range.start
    delta = 0.5

    op = cmd.move_selection(Selection.many([v.clip_id, sub.clip_id]),
                             delta_seconds=delta,
                             why="contract test: move_selection does not propagate")

    # Both clips moved by delta (the move itself works).
    assert abs(core.project.clips[v.clip_id].timeline_range.start
               - (v_start_before + delta)) < 1e-6
    assert abs(core.project.clips[sub.clip_id].timeline_range.start
               - (sub_start_before + delta)) < 1e-6

    # Frozen asymmetry: move_selection must NOT carry cross_shifted_count.
    # (move_clip path carries it; move_selection path does not.)
    assert "cross_shifted_count" not in (op.after or {}), (
        f"move_selection must NOT carry cross_shifted_count, "
        f"got op.after={op.after!r}"
    )


# ---------------------------------------------------------------------------
# 05-D.3 — move_clip with no STRONG relations → no cross_shifted
# ---------------------------------------------------------------------------

def test_move_clip_no_relations_no_shift(tmp_path: Path):
    """When there are no STRONG relations, `move_clip` produces no cross_shifted."""
    core, cmd, v = _make_no_link_project(tmp_path)
    core.save_state()
    # No `infer_relationships` call → no relationships.
    assert len(core.project.relationships) == 0

    op = cmd.move_clip(v.clip_id, new_timeline_start=5.0,
                       why="contract test: no relations")

    assert op.after.get("cross_shifted_count", 0) == 0, (
        f"no-relations move must not carry cross_shifted_count, "
        f"got op.after={op.after!r}"
    )


# ---------------------------------------------------------------------------
# 05-D.4 — infer_relationships idempotency (existing behavior pinned)
# ---------------------------------------------------------------------------

def test_infer_relationships_idempotent(tmp_path: Path):
    """Re-running `infer_relationships` does not accumulate stale entries."""
    from yroll.core.links import infer_relationships

    core, *_ = _make_link_test_project(tmp_path)
    n1 = len(infer_relationships(core.project))
    n2 = len(infer_relationships(core.project))
    assert n1 == n2 == len(core.project.relationships), (
        f"idempotency broken: n1={n1} n2={n2} stored={len(core.project.relationships)}"
    )


# ---------------------------------------------------------------------------
# 05-D.5 — move_clip source-pin: calls infer_relationships
# ---------------------------------------------------------------------------

def test_move_clip_source_pin(tmp_path: Path):
    """Source-pin: `commands.py::move_clip` body must call `infer_relationships`.

    We do this by reading the source of the function and asserting the
    `infer_relationships(self.core.project)` call is present. This is a
    source-level guard against accidental removal of the propagation.
    """
    import inspect

    from yroll.core.commands import CommandLayer

    src = inspect.getsource(CommandLayer.move_clip)
    assert "infer_relationships" in src, (
        "move_clip body must call infer_relationships — "
        "STRONG propagation depends on this"
    )
    assert "self.core.project" in src, (
        "move_clip must pass self.core.project to infer_relationships"
    )


# ---------------------------------------------------------------------------
# 05-D.6 — move_selection source-pin: does NOT call infer_relationships
# ---------------------------------------------------------------------------

def test_move_selection_source_pin(tmp_path: Path):
    """Source-pin: `commands.py::move_selection` body must NOT call `infer_relationships`.

    This is the D12 frozen asymmetry: `move_selection` overrides link inference
    semantics with explicit "user selected these clips as a group" semantics.
    """
    import inspect

    from yroll.core.commands import CommandLayer

    src = inspect.getsource(CommandLayer.move_selection)
    assert "infer_relationships" not in src, (
        "move_selection body must NOT call infer_relationships — "
        "D12 frozen asymmetry: multi-select overrides link propagation"
    )


# ---------------------------------------------------------------------------
# 05-D.7 — impact_preview partitions by RelationStrength
# ---------------------------------------------------------------------------

def test_impact_preview_partitions_by_strength(tmp_path: Path):
    """`impact_preview` partitions relations into will_sync / will_prompt / untouched."""
    from yroll.core.links import impact_preview, infer_relationships

    core, cmd, v, sub = _make_link_test_project(tmp_path)
    core.save_state()
    infer_relationships(core.project)

    impact = impact_preview(core.project, v.clip_id, "remove")
    # caption_of/STRONG partner (subtitle) must land in will_sync.
    assert any(d["clip_id"] == sub.clip_id for d in impact["will_sync"]), (
        f"subtitle (STRONG caption_of) must be in will_sync, got {impact}"
    )
    # Subtitle must NOT be in untouched.
    assert all(d["clip_id"] != sub.clip_id for d in impact["untouched"]), (
        f"STRONG subtitle must not be in untouched, got {impact['untouched']}"
    )


# ---------------------------------------------------------------------------
# 05-D.8 — Selection Linked mode remains "future" (D14 — no Linked Clips impl)
# ---------------------------------------------------------------------------

def test_selection_linked_mode_unused(tmp_path: Path):
    """D14: `yroll/core/selection.py` `Linked` mode remains a future comment.

    Source-pin: the docstring of `Selection` still says "future", and no code
    path uses a `linked` attribute (only `clip_ids`, `track_ids`, `range`).
    """
    import inspect

    from yroll.core.selection import Selection

    src = inspect.getsource(Selection)
    assert "Linked" in src and "future" in src, (
        "Selection dataclass must still document 'Linked' mode as 'future' "
        "(D14: no Linked Clips implementation)"
    )
    # The dataclass must NOT introduce a `linked` field.
    fields = {f.name for f in Selection.__dataclass_fields__.values()} \
        if hasattr(Selection, "__dataclass_fields__") else set()
    assert "linked" not in fields, (
        f"Selection must not have a 'linked' field (D14), got fields={fields}"
    )


# ---------------------------------------------------------------------------
# 05-D.9 — docs/SEMANTIC-LINK-BEHAVIOR.md exists with all 7 required sections
# ---------------------------------------------------------------------------

def test_docs_semantic_link_behavior_exists():
    """The contract doc must exist and contain all 7 required sections.

    Required sections (per plan §05-D + amendments D12, D13, D14):
      1. Data model
      2. Producer
      3. Consumers (commands that READ the graph and act on it)
      4. Explicit non-consumers (D12 frozen asymmetry)
      5. GUI surface (D13 renamed checkbox)
      6. Intentionality — what this is NOT (D14 Linked Clips)
      7. Future changes
    """
    doc_path = ROOT / "docs" / "SEMANTIC-LINK-BEHAVIOR.md"
    assert doc_path.exists(), f"{doc_path} must exist (05-D deliverable)"

    text = doc_path.read_text(encoding="utf-8")

    required = [
        "## 1. Data model",
        "## 2. Producer",
        "## 3. Consumers",
        "## 4. Explicit NON-consumers",
        "## 5. GUI surface",
        "## 6. Intentionality",
        "## 7. Future changes",
    ]
    for section in required:
        assert section in text, (
            f"doc must contain {section!r} (07 section contract)"
        )

    # D12: move_clip / move_selection asymmetry must be in the doc.
    assert "move_clip" in text and "move_selection" in text, \
        "doc must mention both move_clip and move_selection"

    # D13: renamed "时间重叠提示" wording must be in the doc.
    assert "时间重叠提示" in text, \
        "doc must document the renamed '时间重叠提示' wording (D13)"

    # D14: Linked Clips / Group Editing explicitly out of scope.
    assert "Linked Clips" in text, \
        "doc must mention Linked Clips as out of scope (D14)"


# ---------------------------------------------------------------------------
# Cleanup helper for tmp projects (run after each test if used directly)
# ---------------------------------------------------------------------------

def teardown_module(module):
    """Clean up any leftover test projects."""
    for name in ("link-contract", "no-link-contract"):
        p = ROOT / "tests" / f"_{name}_tmp"
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)