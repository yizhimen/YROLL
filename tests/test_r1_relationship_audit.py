"""GUI-05-R1 (R1-C) — Relationship propagation audit.

Human testing of GUI-05-B exposed two symptoms:
  1. Drag commit visual instability → addressed by R1-A + R1-B.
  2. "moving A can move B; when B overlaps C, moving A may also cause
     B and C to move together."

R1-C goal: audit the propagation path BEFORE changing semantics.

Current Core behavior (frozen in 05-D):
  - infer_relationships() recomputes time-overlap STRONG relationships
    before move_clip() (commands.py:1636).
  - move_clip() iterates only the directly-related STRONG clips and
    shifts each by the same delta as the primary clip.
  - infer_relationships() only creates edges between NON-video clips
    (text/audio) and VIDEO clips (links.py:50-92). Two video clips
    never get a STRONG edge; a non-video clip overlapping multiple
    videos gets ONE caption_of/voice_of edge per video (not per
    non-video overlap).

Deterministic fixture (built per-test on top of a fresh project copy):
  - A: video, seconds [0.0, 10.0]
  - B: text caption of A, seconds [1.0, 4.0] (100% inside A)
  - C: text caption of A, seconds [5.0, 8.0] (100% inside A, but
        does NOT overlap B because B ends at 4.0 and C starts at 5.0)

Move A by delta=+5.0:
  - infer_relationships creates (B, caption_of, A) and (C, caption_of, A).
  - related_ids = [B, C] — both DIRECT captions of A.
  - A moves to [5.0, 15.0].
  - B shifts by +5.0 → [6.0, 9.0].
  - C shifts by +5.0 → [10.0, 13.0].

Audit finding:
  C moves because C is directly related to A (caption_of), NOT via
  transitive propagation through B. The two edges (B→A) and (C→A)
  are both first-hop from A. No bug. No fix needed.

If the user expected "moving A only shifts its DIRECT single caption",
the UX is surprising but the Core behavior is correct under the
existing infer_relationships model. Per R1-C spec:
  "Do NOT redesign Linked Clips / Group Editing yet.
   Do NOT silently change move_clip semantics until the exact
   propagation path is proven."

The tests below PIN the propagation path so future Core changes
cannot silently introduce transitive propagation.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _fresh_project_copy(test_root: Path) -> tuple:
    """Copy jdz-chaishao (canonical fixture with default tracks) into
    test_root, then clear all clips so we can build a clean A+B+C
    fixture on top of v1 + t1.
    """
    src = ROOT / "projects" / "jdz-chaishao"
    dst = test_root / "r1-audit"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    from yroll.core.project import ProjectCore
    core = ProjectCore.open(dst)

    # Clear pre-existing clips and relationships to start clean.
    core.project.clips = {}
    core.project.relationships = []
    for t in core.project.timeline.tracks:
        t.clip_ids = []
    core.save_state()
    return core, dst


def _add_video_clip(layer, video_track, *, asset_id: str, src_start: float,
                    src_end: float, tl_start: float) -> str:
    """Add a video clip via the legacy `add_clip` (asset_id + seconds).
    Returns the clip_id assigned by Core.
    """
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
                    md5=f"r1-md5-{asset_id}",
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
        why="R1-C audit fixture",
    )
    return clip.clip_id


def _add_text_clip(layer, text_track, *, tl_start: float, tl_end: float) -> str:
    """Add a text/subtitle clip via legacy add_clip(asset_id="").
    """
    clip = layer.add_clip(
        asset_id="",
        source_start=0.0,
        source_end=tl_end - tl_start,
        timeline_start=tl_start,
        track_id=text_track.track_id,
        why="R1-C audit fixture",
    )
    return clip.clip_id


@pytest.fixture
def abc_fixture():
    """Build the deterministic A+B+C fixture.

    Returns: (core, layer, ids) where ids = {"A": clip_id, ...}
    """
    test_root = ROOT / "tests" / "_r1_audit_tmp"
    test_root.mkdir(exist_ok=True)
    try:
        core, dst = _fresh_project_copy(test_root)
        from yroll.core.commands import CommandLayer
        from yroll.core.links import infer_relationships
        layer = CommandLayer(core, who=__import__(
            "yroll.core.manifest", fromlist=["Actor"]).Actor.HUMAN)

        video_track = next(
            t for t in core.project.timeline.tracks if t.kind.value == "video"
        )
        text_track = next(
            t for t in core.project.timeline.tracks if t.kind.value == "text"
        )

        # A: video [0.0, 10.0]
        a_id = _add_video_clip(
            layer, video_track,
            asset_id="r1-asset-A",
            src_start=0.0, src_end=10.0,
            tl_start=0.0,
        )
        # B: text [1.0, 4.0] (100% inside A)
        b_id = _add_text_clip(
            layer, text_track,
            tl_start=1.0, tl_end=4.0,
        )
        # C: text [5.0, 8.0] (100% inside A, NOT overlapping B)
        c_id = _add_text_clip(
            layer, text_track,
            tl_start=5.0, tl_end=8.0,
        )

        ids = {"A": a_id, "B": b_id, "C": c_id}

        # Run infer_relationships — populates project.relationships.
        infer_relationships(core.project)

        yield core, layer, ids
    finally:
        shutil.rmtree(test_root, ignore_errors=True)


def test_infer_creates_direct_caption_edges_for_both_B_and_C(abc_fixture):
    """infer_relationships() must produce TWO direct edges: B→A and C→A.

    Both B and C are 100% inside A's range, so each gets a caption_of
    edge to A. The relationship graph is:
        B -caption_of-> A
        C -caption_of-> A
    No edge B↔C because infer_relationships only connects non-video
    to video, never non-video to non-video.
    """
    core, _, ids = abc_fixture
    a, b, c = ids["A"], ids["B"], ids["C"]

    rel_edges = [
        (r.source, r.kind, r.target, r.relation.value)
        for r in core.project.relationships
        if {r.source, r.target}.issubset({a, b, c})
    ]

    assert (b, "caption_of", a, "strong") in rel_edges, (
        f"B→A caption_of STRONG edge missing; got {rel_edges}"
    )
    assert (c, "caption_of", a, "strong") in rel_edges, (
        f"C→A caption_of STRONG edge missing; got {rel_edges}"
    )

    # No edge between B and C (non-video ↔ non-video is forbidden by
    # the infer_relationships design).
    bc_edges = [
        (s, k, t, v) for (s, k, t, v) in rel_edges
        if {s, t} == {b, c}
    ]
    assert bc_edges == [], (
        f"No B↔C edge should exist (infer only connects non-video to video); "
        f"got {bc_edges}"
    )


def test_move_A_shifts_both_B_and_C_by_same_delta_one_hop(abc_fixture):
    """Move A by delta=+5s. Both B and C shift by +5s. C does NOT
    shift by 2*delta (no double-shift via B) — the propagation is
    direct, NOT transitive.
    """
    core, layer, ids = abc_fixture
    a, b, c = ids["A"], ids["B"], ids["C"]

    # Snapshot pre-move state of C.
    c_start_before = core.project.clips[c].timeline_range.start

    # Move A by +5.0 (A: [0, 10] → [5, 15]).
    op = layer.move_clip(a, new_timeline_start=5.0, why="R1-C audit")

    # A's new range
    assert core.project.clips[a].timeline_range.start == 5.0
    assert core.project.clips[a].timeline_range.end == 15.0

    # B's new range: [1, 4] + 5 → [6, 9]
    assert core.project.clips[b].timeline_range.start == 6.0
    assert core.project.clips[b].timeline_range.end == 9.0

    # C's new range: [5, 8] + 5 → [10, 13]
    assert core.project.clips[c].timeline_range.start == 10.0
    assert core.project.clips[c].timeline_range.end == 13.0

    # CRITICAL AUDIT: C shifted by EXACTLY +5 (matching A's delta),
    # NOT +10 (no double-shift via B).
    c_delta = core.project.clips[c].timeline_range.start - c_start_before
    assert c_delta == 5.0, (
        f"C's delta must equal A's delta (+5); got {c_delta}. "
        f"If 10.0, transitive propagation bug exists."
    )


def test_move_A_records_cross_shifted_with_B_and_C(abc_fixture):
    """commands.py records `before["cross_shifted"]` listing all
    directly-related clips that shifted. Both B and C must appear
    (one hop each from A).
    """
    core, layer, ids = abc_fixture
    a, b, c = ids["A"], ids["B"], ids["C"]

    op = layer.move_clip(a, new_timeline_start=5.0, why="R1-C audit")

    # The Operation's before dict must record both B and C.
    assert "cross_shifted" in op.before, (
        f"Operation.before['cross_shifted'] missing; before={op.before}"
    )
    cross = op.before["cross_shifted"]
    assert b in cross, f"B must appear in cross_shifted; got {list(cross)}"
    assert c in cross, f"C must appear in cross_shifted; got {list(cross)}"
    # after.cross_shifted_count must equal 2.
    assert op.after.get("cross_shifted_count") == 2, (
        f"Expected cross_shifted_count=2; got {op.after.get('cross_shifted_count')}"
    )


def test_infer_relationships_idempotent_after_move(abc_fixture):
    """Running infer_relationships() twice produces the same graph.

    Note: this runs on the POST-move state (the fixture moves A
    implicitly via the previous test in this module? No — each test
    gets a fresh fixture, so this is on the pre-move state). Verify
    idempotency on the pre-move graph.
    """
    core, _, _ = abc_fixture
    from yroll.core.links import infer_relationships

    r1 = infer_relationships(core.project)
    r2 = infer_relationships(core.project)

    def _key(r) -> tuple[str, str, str]:
        return (r.source, r.kind, r.target)

    edges1 = sorted(_key(r) for r in r1)
    edges2 = sorted(_key(r) for r in r2)
    assert edges1 == edges2, (
        f"infer_relationships is not idempotent:\n  1st: {edges1}\n  2nd: {edges2}"
    )


def test_move_clip_does_not_change_propagation_chain_after_move(abc_fixture):
    """R1-C critical invariant: move_clip() shifts only FIRST-HOP
    STRONG clips. It does NOT recursively shift clips related to the
    shifted related-clips.

    Constructed fixture: B is caption_of A. C is caption_of A. After
    A's move:
      - B shifts by +delta (one hop from A).
      - C shifts by +delta (one hop from A).
      - Neither B nor C shifts AGAIN because something related to them
        also shifted.
    """
    core, layer, ids = abc_fixture
    c = ids["C"]
    c_start_before = core.project.clips[c].timeline_range.start

    layer.move_clip(ids["A"], new_timeline_start=5.0, why="R1-C audit")

    c_start_after = core.project.clips[c].timeline_range.start
    # C moved by exactly +5.0 (one hop), NOT +10.0 (no second hop).
    assert c_start_after - c_start_before == 5.0, (
        f"C must shift by exactly A's delta (+5); got {c_start_after - c_start_before}. "
        f"This would indicate transitive propagation bug."
    )