"""R5 audit (2026-09-01): /preview/plan project_revision parity.

Bug: `build_preview_plan` derived `project_revision` from
`project.ui_status.base_revision`, but `project.ui_status` is never
assigned anywhere in the project model. The plan always reported
`project_revision: 0` while /sequence and /ui/status reported the real
revision. The GUI's `usePreviewPlan` would compare the plan's revision
against the polled revision, find a mismatch, and discard the plan —
producing a black Preview with zero layers.

Fix: `build_preview_plan` now accepts an optional `project_revision`
parameter. The server's `/preview/plan` handler injects the canonical
`get_current_revision(core)` (the same function used by /sequence and
the mutation gate). The plan function no longer reads `project.ui_status`.

These tests pin:
  1. /sequence, /ui/status, /preview/plan all report the SAME
     project_revision BEFORE any mutation.
  2. After one mutation, all three bump to revision N+1.
  3. `build_preview_plan(project, project_revision=N)` embeds N in
     the returned PreviewPlan (Core-layer contract).
  4. The fallback path (parameter omitted, no `sequence.project_revision`
     attribute) reports 0 — preserves backward compatibility.
"""
from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from yroll.core.commands import CommandLayer
from yroll.core.manifest import (
    Actor,
    Project,
    Sequence,
    Track,
    TrackKind,
)
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.plan import build_preview_plan
from yroll.core.project import ProjectCore
from yroll.core.revision import get_current_revision
from yroll.core.timebase import Rational
from yroll.server.app import create_app


FPS_30 = Rational(30, 1)


def _new_image_project(tmp_path, n=1):
    project_root = tmp_path / "proj"
    project_root.mkdir()
    name = "preview-revision-test"
    core = ProjectCore.create(project_root, name)
    core.project.sequence = Sequence(fps=FPS_30)
    core.project.sequence.sync_to_project(core.project)
    ProjectCore.ensure_default_tracks(core)
    for i in range(n):
        core.project.assets.append(Asset(
            asset_id=f"img{i+1}",
            type=AssetType.IMAGE,
            path=f"/tmp/img{i+1}.png",
            identity=AssetIdentity(md5=("i" * 32), size_bytes=1),
            source_fps=None, source_is_cfr=True,
        ))
    core.save_state()
    return project_root / name, core


def _read_three(client: TestClient, timeline_id: str = "main"):
    """Hit the three endpoints and return their project_revision."""
    seq = client.get("/sequence").json()
    ui = client.get("/ui/status").json()
    plan = client.get(f"/preview/plan?timeline_id={timeline_id}").json()
    return (
        int(seq["project_revision"]),
        int(ui["base_revision"]),
        int(plan["project_revision"]),
    )


# ---------------------------------------------------------------------------
# 1. Initial parity: /sequence == /ui/status == /preview/plan
# ---------------------------------------------------------------------------

def test_initial_revision_parity(tmp_path):
    """A freshly-created project reports the same revision on all
    three endpoints before any mutation."""
    project_dir, core = _new_image_project(tmp_path, n=1)
    app = create_app(core.path, who=Actor.HUMAN)
    with TestClient(app) as client:
        seq_r, ui_r, plan_r = _read_three(client)
    assert seq_r == ui_r == plan_r, (
        f"revision must be equal across the three endpoints; "
        f"got /sequence={seq_r} /ui/status={ui_r} /preview/plan={plan_r}"
    )


# ---------------------------------------------------------------------------
# 2. After one mutation, all three endpoints bump to N+1
# ---------------------------------------------------------------------------

def test_revision_parity_after_mutation(tmp_path):
    """After exactly one mutation, all three endpoints report the
    pre-mutation revision + 1. Lock the GUI invariant: stale plan
    must NOT silently disagree with /sequence."""
    project_dir, core = _new_image_project(tmp_path, n=2)
    app = create_app(core.path, who=Actor.HUMAN)
    with TestClient(app) as client:
        before_seq, before_ui, before_plan = _read_three(client)
        assert before_seq == before_ui == before_plan

        # Auto-acquire lease (mutation gate).
        r = client.post("/lease/acquire?actor=human&mode=edit&humanLabel=Test")
        assert r.status_code == 200, r.text
        sid = r.json()["sessionId"]
        rev = before_seq  # current revision = the baseRevision to send

        # One mutation: add an image clip.
        r = client.post(
            f"/clips/add_image?sessionId={sid}&baseRevision={rev}",
            json={
                "asset_id": "img1",
                "timeline_start_frame": 0,
                "timeline_duration_frames": 30,
                "track_id": None,
                "why": "audit-revision-test",
            },
        )
        assert r.status_code == 200, r.text

        after_seq, after_ui, after_plan = _read_three(client)

    assert after_seq == before_seq + 1
    assert after_ui == before_ui + 1
    assert after_plan == before_plan + 1
    assert after_seq == after_ui == after_plan


# ---------------------------------------------------------------------------
# 3. Core contract: build_preview_plan honors project_revision parameter
# ---------------------------------------------------------------------------

def test_build_preview_plan_honors_project_revision_parameter(tmp_path):
    """When the server passes `project_revision=N` to
    `build_preview_plan`, the returned PreviewPlan embeds exactly N."""
    project_dir, core = _new_image_project(tmp_path, n=1)
    plan = build_preview_plan(core.project, "main", project_revision=42)
    assert plan.project_revision == 42

    plan = build_preview_plan(core.project, "main", project_revision=0)
    assert plan.project_revision == 0


def test_build_preview_plan_matches_get_current_revision(tmp_path):
    """When the server passes `get_current_revision(core)` to
    `build_preview_plan`, the plan's revision matches the canonical
    function output byte-for-byte. Pins the single-source-of-truth
    invariant."""
    project_dir, core = _new_image_project(tmp_path, n=1)
    rev = get_current_revision(core)
    plan = build_preview_plan(
        core.project, "main", project_revision=rev,
    )
    assert plan.project_revision == rev


# ---------------------------------------------------------------------------
# 4. Fallback: parameter omitted → revision defaults to 0 (no silent lie)
# ---------------------------------------------------------------------------

def test_build_preview_plan_fallback_when_no_revision_source(tmp_path):
    """Without an explicit `project_revision` and without
    `sequence.project_revision`, the plan reports 0. This is the
    documented fallback — it must NEVER silently disagree with
    /sequence; the production code path always injects the canonical
    value, so the fallback exists for unit-test ergonomics only."""
    project_dir, core = _new_image_project(tmp_path, n=1)
    plan = build_preview_plan(core.project, "main")
    assert plan.project_revision == 0


# ---------------------------------------------------------------------------
# 5. End-to-end: mutation → revision N+1 → new plan → GUI accepts it
# ---------------------------------------------------------------------------

def test_mutation_then_plan_accepted(tmp_path):
    """End-to-end flow: a mutation bumps the canonical revision,
    /preview/plan reports the NEW revision, and the GUI's
    `usePreviewPlan` would compare-and-accept (not discard) it.

    Reproduces the original R5 bug shape: without the fix, the plan
    always reports `project_revision: 0` regardless of the mutation,
    so the GUI compares `data.project_revision (0)` against its
    `liveSeq.projectRevision (N+1)` and discards the plan. With the
    fix, both are N+1 and the plan is accepted.
    """
    project_dir, core = _new_image_project(tmp_path, n=2)
    app = create_app(core.path, who=Actor.HUMAN)
    with TestClient(app) as client:
        seq0 = int(client.get("/sequence").json()["project_revision"])
        assert seq0 == get_current_revision(core)

        # Auto-acquire lease.
        r = client.post("/lease/acquire?actor=human&mode=edit&humanLabel=Test")
        sid = r.json()["sessionId"]

        # One mutation.
        r = client.post(
            f"/clips/add_image?sessionId={sid}&baseRevision={seq0}",
            json={
                "asset_id": "img1",
                "timeline_start_frame": 0,
                "timeline_duration_frames": 30,
                "track_id": None,
                "why": "audit-mutation-flow",
            },
        )
        assert r.status_code == 200

        seq1 = int(client.get("/sequence").json()["project_revision"])
        plan1 = client.get("/preview/plan?timeline_id=main").json()

    assert seq1 == seq0 + 1
    # The GUI's usePreviewPlan would call:
    #   setPlan({ project_revision: plan1.project_revision, ... })
    # and accept it because plan1.project_revision == seq1.
    assert plan1["project_revision"] == seq1, (
        "GUI would discard the plan as 'stale' if these disagree"
    )
    # And the plan must actually contain the layer for the just-added clip.
    clip_ids = [
        layer["clip_id"]
        for track in plan1["tracks"]
        for layer in track
    ]
    assert len(clip_ids) >= 1, "the just-added clip must appear in the plan"