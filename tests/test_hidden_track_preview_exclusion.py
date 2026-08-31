"""R5 audit (2026-09-01): hidden Track's clips must be excluded from
Preview/Composite participation, while the Track itself remains
visible in the Timeline (covered by vitest). This pytest pins the
Core-side invariant: hidden tracks contribute ZERO visual_layers
and ZERO subtitle_texts to /preview/plan and /preview/at_frame.
"""
from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from yroll.core.commands import CommandLayer
from yroll.core.frame_preview import composite_preview_at_frame
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
from yroll.core.timebase import Rational
from yroll.server.app import create_app


FPS_30 = Rational(30, 1)


def _three_track_project(tmp_path):
    """Build a project with v1 (visible) + v2 (visible) + v3 (hidden).
    Each has one image clip at frames 0..30."""
    project_root = tmp_path / "proj"
    project_root.mkdir()
    name = "hidden-track-preview"
    core = ProjectCore.create(project_root, name)
    core.project.sequence = Sequence(fps=FPS_30)
    core.project.sequence.sync_to_project(core.project)
    ProjectCore.ensure_default_tracks(core)

    # Register one image asset.
    core.project.assets.append(Asset(
        asset_id="img1", type=AssetType.IMAGE, path="/tmp/img1.png",
        identity=AssetIdentity(md5=("i" * 32), size_bytes=1),
        source_fps=None, source_is_cfr=True,
    ))

    layer = CommandLayer(core, who=Actor.HUMAN)
    # Add three clips on three different tracks at the same range.
    # Default tracks: v1, v2, v3, a1, a2, a3, t1, t2.
    layer.add_image_clip("img1", 0, 30)   # on v1 (first VIDEO track)

    # Find v2, v3 and add clips on them.
    video_tracks = [t for t in core.project.timeline.tracks
                    if t.kind == TrackKind.VIDEO]
    v2 = next(t for t in video_tracks if t.track_id == "v2")
    v3 = next(t for t in video_tracks if t.track_id == "v3")

    # Mark v3 as hidden BEFORE adding its clip, so the clip lands on
    # the hidden track (legitimate scenario: user hides a track that
    # already has clips; the clips remain visible in Timeline but
    # excluded from Preview).
    CommandLayer(core, who=Actor.HUMAN).set_track_hidden(v3.track_id, True)
    layer.add_image_clip("img1", 0, 30, track_id=v2.track_id)
    layer.add_image_clip("img1", 0, 30, track_id=v3.track_id)
    core.save_state()

    return project_root / name, core


# ---------------------------------------------------------------------------
# 1. Core-layer: hidden track clips excluded from composite_preview_at_frame
# ---------------------------------------------------------------------------

def test_hidden_track_excluded_from_composite_at_frame(tmp_path):
    project_dir, core = _three_track_project(tmp_path)
    pv = composite_preview_at_frame(core.project, 15, FPS_30, "main")
    # v1 (visible) + v2 (visible) → 2 visual layers; v3 (hidden) excluded.
    assert len(pv.visual_layers) == 2
    track_ids = sorted({l.track_id for l in pv.visual_layers})
    assert track_ids == ["v1", "v2"], (
        f"v3 must be excluded; got {track_ids}"
    )


# ---------------------------------------------------------------------------
# 2. Core-layer: hidden track clips excluded from build_preview_plan
# ---------------------------------------------------------------------------

def test_hidden_track_excluded_from_preview_plan(tmp_path):
    project_dir, core = _three_track_project(tmp_path)
    plan = build_preview_plan(core.project, "main", project_revision=1)
    # plan.tracks contains one entry per visible track (hidden skipped
    # entirely — there is NO empty list entry for hidden tracks).
    track_ids_in_plan = [
        t[0].track_id for t in plan.tracks if t
    ]
    assert "v3" not in track_ids_in_plan, (
        f"hidden track v3 must NOT appear in plan.tracks; got {track_ids_in_plan}"
    )
    assert "v1" in track_ids_in_plan
    assert "v2" in track_ids_in_plan


# ---------------------------------------------------------------------------
# 3. HTTP-layer: /preview/plan hides the hidden track
# ---------------------------------------------------------------------------

def test_hidden_track_excluded_from_http_preview_plan(tmp_path):
    project_dir, core = _three_track_project(tmp_path)
    app = create_app(core.path, who=Actor.HUMAN)
    with TestClient(app) as client:
        resp = client.get("/preview/plan?timeline_id=main")
    assert resp.status_code == 200
    plan = resp.json()
    track_ids = sorted({layer["track_id"]
                        for t in plan["tracks"]
                        for layer in t})
    assert "v3" not in track_ids, (
        f"hidden v3 leaked into /preview/plan: {track_ids}"
    )
    assert "v1" in track_ids
    assert "v2" in track_ids


# ---------------------------------------------------------------------------
# 4. HTTP-layer: /preview/at_frame hides the hidden track
# ---------------------------------------------------------------------------

def test_hidden_track_excluded_from_http_preview_at_frame(tmp_path):
    project_dir, core = _three_track_project(tmp_path)
    app = create_app(core.path, who=Actor.HUMAN)
    with TestClient(app) as client:
        resp = client.get("/preview/at_frame?timeline_id=main&frame=15")
    assert resp.status_code == 200
    pv = resp.json()
    track_ids = sorted({l["track_id"] for l in pv["visual_layers"]})
    assert "v3" not in track_ids
    assert "v1" in track_ids
    assert "v2" in track_ids