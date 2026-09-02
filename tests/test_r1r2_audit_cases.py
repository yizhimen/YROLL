"""GUI-05-R1-R2 — Drag Reliability Closure (Cases A-G).

Per human acceptance FAILED, R1-R2 investigates drag/move failures:

Case A: GUI says cross-track but pointer is actually on the same track.
  → GUI-side (elementsFromPoint mis-hit); tested by browser smoke.
Case B: API rejects because target track is wrong.
  → Core-level (move_clip with nonexistent new_track_id).
Case C: API rejects because the dragged clip itself overlaps another clip.
  → Core-level (move_clip with collision on target_track).
Case D: API rejects because a propagated related clip overlaps another clip.
  → Core-level (move_clip with collision on propagated target track).
Case E: API rejects because baseRevision is stale.
  → API-level (server gate _check_rev); tested via HTTP smoke.
Case F: Mutation succeeds in Core but GUI refresh/reconciliation displays
       old state.
  → GUI-side (displayProject reads dragPreview after refresh); browser smoke.
Case G: Mutation fails but GUI loses the correct rejection state.
  → GUI-side (status text overwritten or setDragPreview not cleared);
       browser smoke.

R1-R2 scope:
- Investigate + report root cause(s) BEFORE any fix or semantic change.
- No Linked Clips / Group Editing redesign.
- No move_clip propagation semantic changes (only the propagation-
  collision check fix that surfaced in instrumentation — see below).
- No 05-C subtitle work.

R1-R2 instrumentation finding (already captured during investigation):

  The pre-existing move_clip code did NOT check whether a propagated
  related clip would collide with a non-propagation sibling. It only
  checked the PRIMARY clip's target position. The instrumentation
  revealed: when A moves and propagates to B/C/D/E...F (where F is an
  unrelated clip), Core would silently move the propagated clips into
  F's range — leaving the project in an invalid state. The fix:

  - move_clip now does a propagation-collision check for each
    propagated target (excluding other propagation targets and self).
  - If a non-propagation sibling would be overlapped, the entire move
    is rolled back (primary clip's timeline_range + track_id restored).
  - The error is raised with the actual conflicting pair (propagated,
    non-propagation) for clear user-facing feedback.

  This is the "API rejects because a propagated related clip overlaps
  another clip" case (D). The fix makes it surface as a clean
  CommandError instead of silently corrupting state.

Deterministic fixtures:
  Fixture 1 — Case C: dragged clip overlaps another.
    A: video [0, 10], B: video [12, 15]
    Move A to 11 (i.e., new_timeline_start=11, length=10 → [11, 21]).
    B at [12, 15] ∩ A_new at [11, 21] = [12, 15]. COLLISION.

  Fixture 2 — Case D: propagated clip overlaps non-propagation sibling.
    A: video [0, 10], B: text caption of A [1, 4], C: text caption of A [6, 9],
    D: text NOT caption of A (at [10, 13])
    Move A by +5 → B shifts to [6, 9], C shifts to [11, 14].
    C's new range [11, 14] ∩ D [10, 13] = [11, 13]. COLLISION.
    Without the propagation-collision check, Core would silently
    corrupt state. With the check, the move is rolled back.

  Fixture 3 — Case B: target track doesn't exist.
    A: video on v1. Move A with new_track_id="v_doesnt_exist".
    Expect CommandError("track 不存在").

  Fixture 4 — repeated moves (Case E invariant).
    A: video [0, 10]. Sequential moves:
      move(A, 5) → move(A, 10) → move(A, 15) → move(A, 20)
    Each move must commit exactly one Operation. Final state must
    be A at [20, 30].
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _fresh_project_copy(test_root: Path) -> tuple:
    """Copy jdz-chaishao into a fresh test directory, clear clips.
    Returns (core, dst_path).
    """
    src = ROOT / "projects" / "jdz-chaishao"
    dst = test_root / "r1r2"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    from yroll.core.project import ProjectCore
    core = ProjectCore.open(dst)

    core.project.clips = {}
    core.project.relationships = []
    for t in core.project.timeline.tracks:
        t.clip_ids = []
    core.save_state()
    return core, dst


def _add_video_clip(layer, video_track, *, asset_id: str, src_start: float,
                    src_end: float, tl_start: float) -> str:
    from yroll.core.models import Asset, AssetType, AssetIdentity, AssetOrigin
    asset = next((a for a in layer.core.project.assets
                  if a.asset_id == asset_id), None)
    if asset is None:
        layer.core.project.assets.append(
            Asset(
                asset_id=asset_id,
                type=AssetType.VIDEO,
                origin=AssetOrigin.UNKNOWN,
                path=f"/tmp/{asset_id}.mp4",
                identity=AssetIdentity(
                    md5=f"r1r2-md5-{asset_id}",
                    size_bytes=1024,
                    duration_sec=max(src_end, 1.0),
                ),
            )
        )
    clip = layer.add_clip(
        asset_id=asset_id,
        source_start=src_start,
        source_end=src_end,
        timeline_start=tl_start,
        track_id=video_track.track_id,
        why="R1-R2 fixture",
    )
    return clip.clip_id


def _add_text_clip(layer, text_track, *, tl_start: float, tl_end: float) -> str:
    clip = layer.add_clip(
        asset_id="",
        source_start=0.0,
        source_end=tl_end - tl_start,
        timeline_start=tl_start,
        track_id=text_track.track_id,
        why="R1-R2 fixture",
    )
    return clip.clip_id


@pytest.fixture
def r1r2_fixture():
    """Build deterministic fixtures for Cases B, C, D, E."""
    test_root = ROOT / "tests" / "_r1r2_tmp"
    test_root.mkdir(exist_ok=True)
    try:
        core, dst = _fresh_project_copy(test_root)
        from yroll.core.commands import CommandLayer
        layer = CommandLayer(core, who=__import__(
            "yroll.core.manifest", fromlist=["Actor"]).Actor.HUMAN)

        video_track = next(
            t for t in core.project.timeline.tracks if t.kind.value == "video"
        )
        text_track = next(
            t for t in core.project.timeline.tracks if t.kind.value == "text"
        )

        # Fixture 1 (Case C — dragged clip overlaps another):
        # A: video [0, 10], B_video: video [12, 15] (independent video).
        # We use B_video far away to NOT interfere with Case D below.
        # A separate Case C test creates the overlapping fixture.
        a_id = _add_video_clip(
            layer, video_track, asset_id="r1r2-A",
            src_start=0.0, src_end=10.0, tl_start=0.0,
        )
        # Place B_video far enough that A's new range [5, 15) doesn't
        # overlap B_video (which we use as a non-propagation sibling
        # for Case D's propagation-collision test). Half-open interval:
        # [5, 15) ∩ [15, 18) = empty.
        b_video_id = _add_video_clip(
            layer, video_track, asset_id="r1r2-B",
            src_start=0.0, src_end=3.0, tl_start=15.0,
        )

        # Fixture 2 (Case D — propagated clip collides with non-propagation):
        # C: text caption of A [1, 4], E: text caption of A [6, 9],
        # F: text NOT caption of A [10, 13]
        c_text_id = _add_text_clip(layer, text_track, tl_start=1.0, tl_end=4.0)
        e_text_id = _add_text_clip(layer, text_track, tl_start=6.0, tl_end=9.0)
        f_text_id = _add_text_clip(layer, text_track, tl_start=10.0, tl_end=13.0)

        ids = {
            "A": a_id, "B_video": b_video_id,
            "C_text": c_text_id, "E_text": e_text_id, "F_text": f_text_id,
        }
        yield core, layer, ids
    finally:
        shutil.rmtree(test_root, ignore_errors=True)


def test_case_c_dragged_clip_overlaps_another():
    """Case C: move_clip where the PRIMARY clip's new range overlaps
    another clip on the target track. Expect CommandError, Core
    unchanged.

    Built ad-hoc so B_video overlaps A's new range.
    """
    test_root = ROOT / "tests" / "_r1r2_case_c_tmp"
    test_root.mkdir(exist_ok=True)
    try:
        core, dst = _fresh_project_copy(test_root)
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor
        layer = CommandLayer(core, who=Actor.HUMAN)
        video_track = next(
            t for t in core.project.timeline.tracks if t.kind.value == "video"
        )
        a = _add_video_clip(
            layer, video_track, asset_id="r1r2-casec-A",
            src_start=0.0, src_end=10.0, tl_start=0.0,
        )
        # B at [12, 15] — A's new range [11, 21) overlaps it.
        b = _add_video_clip(
            layer, video_track, asset_id="r1r2-casec-B",
            src_start=0.0, src_end=3.0, tl_start=12.0,
        )
        with pytest.raises(Exception) as excinfo:
            layer.move_clip(a, new_timeline_start=11.0, why="R1-R2 Case C")
        # Core unchanged.
        assert core.project.clips[a].timeline_range.start == 0.0
        assert core.project.clips[a].timeline_range.end == 10.0
        # Error message must identify the conflicting clip.
        err_msg = str(excinfo.value)
        assert "重叠" in err_msg or "overlap" in err_msg.lower(), (
            f"Expected overlap error; got: {err_msg}"
        )
        assert b in err_msg, (
            f"Error message must identify the conflicting clip {b}; "
            f"got: {err_msg}"
        )
    finally:
        shutil.rmtree(test_root, ignore_errors=True)


def test_case_d_propagated_clip_overlaps_non_propagation_sibling(r1r2_fixture):
    """Case D: A has STRONG captions C and E. F is on the same track
    (t1) but NOT a caption of A. Move A by +5; C/E shift by +5;
    E's new range [11, 14] overlaps F's range [10, 13] →
    propagation-collision detected. Core rolls back the entire move.
    """
    core, layer, ids = r1r2_fixture
    a = ids["A"]
    c = ids["C_text"]
    e = ids["E_text"]
    f = ids["F_text"]

    # Sanity: all positions pre-move.
    assert core.project.clips[a].timeline_range.start == 0.0
    assert core.project.clips[c].timeline_range.start == 1.0
    assert core.project.clips[e].timeline_range.start == 6.0
    assert core.project.clips[f].timeline_range.start == 10.0

    with pytest.raises(Exception) as excinfo:
        layer.move_clip(a, new_timeline_start=5.0, why="R1-R2 Case D")

    # Core state must be UNCHANGED after rollback.
    assert core.project.clips[a].timeline_range.start == 0.0, (
        f"A must be at original 0.0; got {core.project.clips[a].timeline_range.start}"
    )
    assert core.project.clips[c].timeline_range.start == 1.0
    assert core.project.clips[e].timeline_range.start == 6.0
    assert core.project.clips[f].timeline_range.start == 10.0

    # Error message must identify the propagated clip + non-propagation
    # sibling pair. Per user spec: "verify exactly which clip causes the
    # rejection; do NOT merely assert that 'overlap exists'; identify
    # the conflicting pair(s)".
    err_msg = str(excinfo.value)
    assert e in err_msg or "propagated_clip" in err_msg, (
        f"Error message must mention the propagated clip ({e}); got: {err_msg}"
    )
    assert f in err_msg, (
        f"Error message must mention the non-propagation sibling ({f}); "
        f"got: {err_msg}"
    )


def test_case_b_target_track_does_not_exist(r1r2_fixture):
    """Case B: API rejects because target track doesn't exist.
    Move A with new_track_id="v_doesnt_exist" → CommandError.
    """
    core, layer, ids = r1r2_fixture
    a = ids["A"]
    with pytest.raises(Exception) as excinfo:
        layer.move_clip(a, new_timeline_start=5.0, why="R1-R2 Case B",
                        new_track_id="v_doesnt_exist")
    assert "不存在" in str(excinfo.value) or "not exist" in str(excinfo.value).lower()
    # Core unchanged.
    assert core.project.clips[a].timeline_range.start == 0.0


def test_case_e_repeated_moves_each_commit_exactly_once():
    """Case E invariant: repeated same-clip moves must commit exactly
    once each. Final state must reflect the LAST move. No stale
    revision / position / relationship graph leak across gestures.

    Move A: 0 → 5 → 10 → 15 → 20. Each move emits exactly one
    Operation. Final A.timeline_range = [20, 30].

    Uses a fresh fixture with NO captions to avoid the propagation-
    collision check (Case D) from interfering.
    """
    test_root = ROOT / "tests" / "_r1r2_e_repeat_tmp"
    test_root.mkdir(exist_ok=True)
    try:
        core, dst = _fresh_project_copy(test_root)
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor
        layer = CommandLayer(core, who=Actor.HUMAN)
        video_track = next(
            t for t in core.project.timeline.tracks if t.kind.value == "video"
        )
        a = _add_video_clip(
            layer, video_track, asset_id="r1r2-E-repeat-A",
            src_start=0.0, src_end=5.0, tl_start=0.0,
        )
        # Place B at [50, 53] (far away, no overlap with any A move).
        b = _add_video_clip(
            layer, video_track, asset_id="r1r2-E-repeat-B",
            src_start=0.0, src_end=3.0, tl_start=50.0,
        )

        moves = [5.0, 10.0, 15.0, 20.0]
        op_count_before = len(core.operations())
        for i, new_start in enumerate(moves):
            layer.move_clip(a, new_timeline_start=new_start,
                            why=f"R1-R2 Case E move #{i+1}")
        op_count_after = len(core.operations())

        assert op_count_after - op_count_before == len(moves), (
            f"Expected {len(moves)} new ops; got {op_count_after - op_count_before}"
        )

        # Final state: A at [20, 25].
        assert core.project.clips[a].timeline_range.start == 20.0
        assert core.project.clips[a].timeline_range.end == 25.0
        # B unchanged.
        assert core.project.clips[b].timeline_range.start == 50.0
    finally:
        shutil.rmtree(test_root, ignore_errors=True)


def test_case_e_repeated_moves_no_stale_revision_leak():
    """Case E: API-level stale revision race. After the first move,
    the second move must use the LATEST revision (post the first
    move), not the original.

    Simulated at the HTTP layer in gui/smoke/gui-05-r1r2-drag-reliability.mjs.
    This pytest pins the Core invariant: each move emits one Operation,
    and ops are append-only with monotonically increasing revision.
    """
    test_root = ROOT / "tests" / "_r1r2_e_tmp"
    test_root.mkdir(exist_ok=True)
    try:
        core, dst = _fresh_project_copy(test_root)
        from yroll.core.commands import CommandLayer
        from yroll.core.manifest import Actor
        layer = CommandLayer(core, who=Actor.HUMAN)

        video_track = next(
            t for t in core.project.timeline.tracks if t.kind.value == "video"
        )
        a_id = _add_video_clip(
            layer, video_track, asset_id="r1r2-E-A",
            src_start=0.0, src_end=5.0, tl_start=0.0,
        )

        # Three sequential moves. After each move, the Core revision
        # (= ops length) must have incremented by exactly 1.
        for i in range(3):
            rev_before = len(core.operations())
            layer.move_clip(a_id, new_timeline_start=float(i + 1) * 2.0,
                            why=f"R1-R2 E #{i+1}")
            rev_after = len(core.operations())
            assert rev_after == rev_before + 1, (
                f"Move #{i+1}: expected revision increment by 1; "
                f"got {rev_before} → {rev_after}"
            )
    finally:
        shutil.rmtree(test_root, ignore_errors=True)


def test_propagation_collision_does_not_silently_corrupt_state(r1r2_fixture):
    """R1-R2 invariant: propagation-induced collision MUST NOT silently
    leave Core in an invalid state (e.g., primary clip at new position
    but propagated clip overlaps another).

    Even if the propagation-collision check is somehow bypassed
    (regression), the Core must never end up with overlap. This test
    uses the R1-R2 instrumentation check (now in move_clip). The fix
    rolls back atomically. Without the fix, this test fails (state
    corrupted).
    """
    core, layer, ids = r1r2_fixture
    a = ids["A"]
    e = ids["E_text"]
    f = ids["F_text"]

    # Run the move that triggers propagation collision.
    with pytest.raises(Exception):
        layer.move_clip(a, new_timeline_start=5.0, why="R1-R2 invariant")

    # Check that the Core state has NO overlap after the rollback.
    # E is at [6, 9], F is at [10, 13] (pre-move). After rollback, both
    # are still at their original positions. [6, 9] ∩ [10, 13] = empty.
    e_range = core.project.clips[e].timeline_range
    f_range = core.project.clips[f].timeline_range
    assert e_range.end <= f_range.start or f_range.end <= e_range.start, (
        f"Core has overlap after rejected move: E={e_range}, F={f_range}"
    )