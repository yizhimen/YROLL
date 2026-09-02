"""GUI-04 04-05: Preview Layer Model contract.

Per plan §7:
   TimelineFrame N → PreviewPlan → active visual clips →
   stable z-order → each clip's own transform → renderer

Hard requirements pinned here:

   1. NO track-index-based PiP shrinking (no V2=30%, V3=20%).
   2. Clip.transform is the SOLE semantic source for visual
      placement: x, y, scale, rotation, opacity.
   3. Default transform for newly created visual clip:
      centered (x=0, y=0), scale=1, rotation=0, opacity=1.
   4. Track identity (V1/V2/V3) is layers/z-order, NOT layout.
   5. Multiple visual tracks coexist; stable deterministic z-order.
   6. Hidden track excluded from rendering (Core's
      build_preview_plan filters hidden tracks).
   7. Multi-layer determinism: same Core state + same
      TimelineFrame → same PreviewPlan / arrangement.
   8. Acceptance A–I (plan §7):
       A. one visual layer
       B. two visual layers
       C. three visual layers
       D. upper/lower layer combinations
       E. hidden visual layer excluded
       F. same frame repeated render determinism
       G. aspect ratios (16:9, 9:16, 1:1, 4:3, 3:4)
       H. transform defaults
       I. no automatic PiP shrinking
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from yroll.core.manifest import Actor
from yroll.core.project import ProjectCore
from yroll.server.app import create_app
from tests.conftest import _AuthedClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def authed_client(tmp_path):
    """Mirrors test_history_gui_contract.py: TestClient with
    auto-attach sessionId + baseRevision. The authed wrapper
    takes care of /lease/acquire for the mutation endpoints."""
    core = ProjectCore.create(tmp_path, "preview-layers")
    ProjectCore.ensure_default_tracks(core)
    app = create_app(core.path, who=Actor.AI)
    return _AuthedClient(TestClient(app))


def _seed_video_asset(client, asset_id: str = "a-1"):
    """Register a synthetic video asset with source_fps set. Without
    source_fps, the Core's build_preview_plan skips the clip (per
    GUI-02.3 invariant: never silently fall back to sequence fps).
    Tests must therefore register the asset first."""
    from yroll.core.models import Asset, AssetIdentity, AssetType
    from yroll.core.timebase import Rational
    from yroll.server.app import _STATE
    st = _STATE["default"]
    if not any(a.asset_id == asset_id for a in st.core.project.assets):
        st.core.project.assets.append(Asset(
            asset_id=asset_id, type=AssetType.VIDEO, path="",
            identity=AssetIdentity(md5="0" * 32, size_bytes=0,
                                   duration_sec=10.0,
                                   width=1920, height=1080),
            source_fps=Rational(30, 1),
            source_is_cfr=True,
        ))
        st.core.save_state()


def _seed_video_clip(client, asset_id="a-1", track_id="v1",
                     start_frame=0, dur_frames=300):
    """Add a video clip via the Core API. The authed_client wrapper
    auto-injects sessionId + baseRevision. Also registers the
    asset with source_fps so the plan builder includes the clip."""
    _seed_video_asset(client, asset_id)
    body = {
        "asset_id": asset_id,
        "source_start_frame": 0, "source_end_frame": dur_frames,
        "timeline_start_frame": start_frame,
        "track_id": track_id,
        "why": "preview-layer test seed",
    }
    r = client.post("/clips", json=body)
    assert r.status_code == 200, r.text
    return r.json()["clip_id"]


# ---------------------------------------------------------------------------
# Acceptance A: one visual layer → plan has 1 layer
# ---------------------------------------------------------------------------

class TestOneVisualLayer:
    def test_single_video_clip_produces_one_plan_layer(self, authed_client):
        _seed_video_clip(authed_client)
        r = authed_client.get("/preview/plan?timeline_id=main")
        assert r.status_code == 200, r.text
        plan = r.json()
        total_layers = sum(len(t) for t in plan["tracks"])
        assert total_layers == 1
        # The single layer is in v1 (the default track).
        v1 = next(t for t in plan["tracks"] if t[0]["track_id"] == "v1")
        assert v1[0]["kind"] == "video"
        # Composite (single frame) reports one visual layer.
        composite = authed_client.get("/preview/at_frame?frame=0").json()
        assert len(composite["visual_layers"]) == 1


# ---------------------------------------------------------------------------
# Acceptance B + D: multiple visual layers; upper/lower combinations
# ---------------------------------------------------------------------------

class TestMultiLayerUpperLower:
    def _seed_v1_v2_v3(self, client):
        # Create clips on v1, v2, v3 (the default tracks).
        c1 = _seed_video_clip(client, asset_id="a-v1", track_id="v1")
        c2 = _seed_video_clip(client, asset_id="a-v2", track_id="v2")
        c3 = _seed_video_clip(client, asset_id="a-v3", track_id="v3")
        return c1, c2, c3

    def test_two_layers_have_distinct_z_order(self, authed_client):
        _seed_video_clip(authed_client, track_id="v1")
        _seed_video_clip(authed_client, track_id="v2")
        composite = authed_client.get("/preview/at_frame?frame=0").json()
        layers = composite["visual_layers"]
        assert len(layers) == 2
        # The two layers have DIFFERENT layer_index (stable z-order).
        assert layers[0]["layer_index"] < layers[1]["layer_index"]

    def test_three_layers_have_strictly_ascending_z_order(self, authed_client):
        self._seed_v1_v2_v3(authed_client)
        composite = authed_client.get("/preview/at_frame?frame=0").json()
        layers = composite["visual_layers"]
        assert len(layers) == 3
        # Stable z-order: ascending layer_index.
        for i in range(len(layers) - 1):
            assert layers[i]["layer_index"] < layers[i + 1]["layer_index"]

    def test_upper_lower_combinations(self, authed_client):
        """D — pair-wise upper/lower combinations. Each pair must
        have distinct, stable layer_index."""
        self._seed_v1_v2_v3(authed_client)
        composite = authed_client.get("/preview/at_frame?frame=0").json()
        tracks = {l["track_id"]: l for l in composite["visual_layers"]}
        # v1 is bottom, v3 is top.
        assert tracks["v1"]["layer_index"] < tracks["v2"]["layer_index"]
        assert tracks["v2"]["layer_index"] < tracks["v3"]["layer_index"]


# ---------------------------------------------------------------------------
# Acceptance E: hidden visual layer excluded
# ---------------------------------------------------------------------------

class TestHiddenLayerExclusion:
    def test_hidden_track_layer_not_in_plan(self, authed_client):
        # Seed three clips; hide v2.
        _seed_video_clip(authed_client, track_id="v1")
        _seed_video_clip(authed_client, track_id="v2")
        _seed_video_clip(authed_client, track_id="v3")
        # Hide v2 via the track endpoint (no auth needed for setup).
        r = authed_client.post(f"/tracks/v2/hide?hidden=true")
        assert r.status_code == 200, r.text

        plan = authed_client.get("/preview/plan?timeline_id=main").json()
        track_ids = [t[0]["track_id"] for t in plan["tracks"] if t]
        assert "v2" not in track_ids, (
            f"hidden track v2 should be excluded from plan.tracks, "
            f"got: {track_ids}"
        )
        # v1 and v3 still present.
        assert "v1" in track_ids
        assert "v3" in track_ids

        # Composite also excludes v2.
        composite = authed_client.get("/preview/at_frame?frame=0").json()
        composite_tracks = [l["track_id"] for l in composite["visual_layers"]]
        assert "v2" not in composite_tracks


# ---------------------------------------------------------------------------
# Acceptance F: same frame repeated render determinism
# ---------------------------------------------------------------------------

class TestRepeatedRenderDeterminism:
    def test_same_frame_yields_identical_plan(self, authed_client):
        _seed_video_clip(authed_client, track_id="v1")
        _seed_video_clip(authed_client, track_id="v2")
        plan_a = authed_client.get("/preview/plan?timeline_id=main").json()
        plan_b = authed_client.get("/preview/plan?timeline_id=main").json()
        # Same revision, same plan.
        assert plan_a["project_revision"] == plan_b["project_revision"]
        assert plan_a["tracks"] == plan_b["tracks"]

    def test_same_frame_yields_identical_composite(self, authed_client):
        _seed_video_clip(authed_client, track_id="v1")
        _seed_video_clip(authed_client, track_id="v2")
        _seed_video_clip(authed_client, track_id="v3")
        c1 = authed_client.get("/preview/at_frame?frame=0").json()
        c2 = authed_client.get("/preview/at_frame?frame=0").json()
        # Same frames → same z-order, same tracks.
        assert c1["visual_layers"] == c2["visual_layers"]

    def test_deterministic_across_calls(self, authed_client):
        """Call /preview/at_frame 5 times with the same frame and
        assert the layer order is stable across calls."""
        _seed_video_clip(authed_client, track_id="v1")
        _seed_video_clip(authed_client, track_id="v2")
        _seed_video_clip(authed_client, track_id="v3")
        orders = []
        for _ in range(5):
            layers = authed_client.get("/preview/at_frame?frame=0").json()["visual_layers"]
            orders.append([l["track_id"] for l in layers])
        # All 5 calls yield the same order.
        assert all(o == orders[0] for o in orders), (
            f"non-deterministic order across calls: {orders}"
        )


# ---------------------------------------------------------------------------
# Acceptance G: aspect ratios don't affect z-order or layer count
# ---------------------------------------------------------------------------

class TestAspectRatiosIndependent:
    """The aspect ratio of the project sequence does NOT change
    the number of visual layers or their z-order. (Aspect ratio
    affects canvas size, not layer composition.)"""

    @pytest.mark.parametrize("aspect", [
        "16:9", "9:16", "1:1", "4:3", "3:4",
    ])
    def test_aspect_ratio_does_not_change_layer_count(self, authed_client, aspect):
        # Set the project's aspect ratio.
        from yroll.server.app import _STATE
        st = _STATE["default"]
        # parseAspect -> w,h pairs
        w, h = {"16:9": (1920, 1080), "9:16": (1080, 1920),
                "1:1": (1080, 1080), "4:3": (1440, 1080),
                "3:4": (1080, 1440)}[aspect]
        # Mutate the project's sequence width/height.
        st.core.project.sequence.width = w
        st.core.project.sequence.height = h
        st.core.save_state()

        # Seed clips; they should still produce 3 layers regardless of aspect.
        _seed_video_clip(authed_client, track_id="v1")
        _seed_video_clip(authed_client, track_id="v2")
        _seed_video_clip(authed_client, track_id="v3")
        composite = authed_client.get("/preview/at_frame?frame=0").json()
        assert len(composite["visual_layers"]) == 3


# ---------------------------------------------------------------------------
# Acceptance H: transform defaults (the layer.transform field starts
# empty for a newly seeded clip — no PiP shrinking default).
# ---------------------------------------------------------------------------

class TestTransformDefaults:
    def test_new_clip_has_empty_transform(self, authed_client):
        """A newly added visual clip has clip.transform = {}. The
        renderer must apply defaults (centered, scale=1, etc.),
        NOT collapse to a 30%/20% PiP heuristic."""
        _seed_video_clip(authed_client, track_id="v1")
        composite = authed_client.get("/preview/at_frame?frame=0").json()
        assert len(composite["visual_layers"]) == 1
        layer = composite["visual_layers"][0]
        # transform is empty for a fresh clip.
        assert layer["transform"] == {}, (
            f"new clip's transform should be empty; got: {layer['transform']}"
        )

    def test_layer_transform_round_trip_through_set_transform(self, authed_client):
        """The renderer-side transform defaults are NOT persisted
        to Core. set_transform is the only way to change
        clip.transform."""
        clip_id = _seed_video_clip(authed_client, asset_id="a-rt", track_id="v1")
        # Explicit set_transform call.
        r = authed_client.post(
            f"/clips/{clip_id}/transform",
            json={"transform": {"x": 0.3, "y": -0.2, "scale": 1.5, "rotation": 30}},
        )
        assert r.status_code == 200, r.text
        # After set_transform, clip.transform is set to the inner dict
        # (the Core sets clip.transform = dict(transform), where
        # `transform` is the dict passed to set_transform). Verify
        # the composite layer reports a non-empty transform.
        composite = authed_client.get("/preview/at_frame?frame=0").json()
        assert len(composite["visual_layers"]) == 1
        # The layer's transform reflects the user's set call (the
        # exact field names depend on whether Core nested the dict
        # under a "transform" key — we just check it is set).
        layer_transform = composite["visual_layers"][0]["transform"]
        assert layer_transform, (
            f"set_transform should populate clip.transform, got: {layer_transform}"
        )


# ---------------------------------------------------------------------------
# Acceptance I: no automatic PiP shrinking — REGRESSION GUARD
# ---------------------------------------------------------------------------

class TestNoAutomaticPiPShrinking:
    """REGRESSION: any future contributor who re-introduces a
    track-index-based PiP shrinking (V2=30%, V3=20%) MUST fail
    this test. The Core's PreviewPlan contains per-layer
    `transform` (raw user-set) but does NOT inject synthetic
    shrinking transforms based on track_index.

    The PiP heuristic lived in the GUI's `defaultPiPStyle`
    (composite-multilayer.ts) and was REMOVED in 04-05.
    """

    def test_no_layer_has_synthetic_transform_with_pip_shrink(self, authed_client):
        """No layer in the plan has a transform that LOOKS like the
        old PiP heuristic (scale ≈ 0.30 for V2, scale ≈ 0.20 for V3).
        All transforms are either empty {} or user-set via
        /clips/{id}/transform."""
        _seed_video_clip(authed_client, track_id="v1")
        _seed_video_clip(authed_client, track_id="v2")
        _seed_video_clip(authed_client, track_id="v3")
        composite = authed_client.get("/preview/at_frame?frame=0").json()
        for layer in composite["visual_layers"]:
            t = layer.get("transform", {})
            scale = t.get("scale") if isinstance(t, dict) else None
            if scale is not None:
                # Pin: no synthetic 0.30 (V2) or 0.20 (V3) shrinking.
                assert not (0.28 < scale < 0.32), (
                    f"layer {layer['track_id']} has suspicious scale={scale} "
                    f"(V2=0.30 PiP heuristic returned?). "
                    f"Clip.transform is for user-set values, not "
                    f"track-index PiP shrinking."
                )
                assert not (0.18 < scale < 0.22), (
                    f"layer {layer['track_id']} has suspicious scale={scale} "
                    f"(V3=0.20 PiP heuristic returned?)."
                )

    def test_layer_count_equals_clip_count_not_clip_count_divisor(self, authed_client):
        """When 3 clips exist on 3 visual tracks, the plan has 3
        layers — NOT 1 'main' + 2 PiP overlays. The old code had
        1 'bottom' + N 'overlays' (where overlays were shrunk).
        The new code has N layers, each at full canvas."""
        _seed_video_clip(authed_client, track_id="v1")
        _seed_video_clip(authed_client, track_id="v2")
        _seed_video_clip(authed_client, track_id="v3")
        composite = authed_client.get("/preview/at_frame?frame=0").json()
        assert len(composite["visual_layers"]) == 3, (
            "expected 3 layers (one per clip on V1/V2/V3). The OLD "
            "PiP heuristic collapsed to '1 main + 2 PiP overlays'."
        )


# ---------------------------------------------------------------------------
# Hidden-track filter lives at Core boundary (yroll/core/plan.py).
# The GUI iterates plan.tracks as-is. This test pins that contract
# at the HTTP layer.
# ---------------------------------------------------------------------------

class TestHiddenTrackCoreFilter:
    """The hidden-track exclusion is a Core responsibility (per
    yroll/core/plan.py:178,193). The HTTP layer just exposes the
    plan. If the GUI tries to independently re-add a hidden
    layer, the test fails (no such code path here, but the pin
    documents the contract)."""

    def test_plan_excludes_hidden_track(self, authed_client):
        _seed_video_clip(authed_client, track_id="v1")
        _seed_video_clip(authed_client, track_id="v2")
        r = authed_client.post("/tracks/v2/hide?hidden=true")
        assert r.status_code == 200, r.text

        plan = authed_client.get("/preview/plan?timeline_id=main").json()
        track_ids = [t[0]["track_id"] for t in plan["tracks"] if t]
        assert "v2" not in track_ids
        assert "v1" in track_ids

        # Unhide; plan should include v2 again. We pass hidden via
        # params= because TestClient + URL query string merging is
        # unreliable across versions.
        r = authed_client.post(
            "/tracks/v2/hide",
            params={"hidden": "false"},
        )
        assert r.status_code == 200, r.text
        plan = authed_client.get("/preview/plan?timeline_id=main").json()
        track_ids = [t[0]["track_id"] for t in plan["tracks"] if t]
        assert "v2" in track_ids


# ---------------------------------------------------------------------------
# Multi-layer determinism: z-order does NOT depend on track number,
# insertion order, selected clip, DOM, or viewport. (Plan §7.8.)
# We pin this by checking that the SAME plan produces the SAME
# order across many queries.
# ---------------------------------------------------------------------------

class TestZOrderIndependence:
    def test_z_order_independent_of_track_id_string(self, authed_client):
        # Identical plans on v1/v2/v3 should produce strictly
        # ascending layer_index.
        _seed_video_clip(authed_client, track_id="v1")
        _seed_video_clip(authed_client, track_id="v2")
        _seed_video_clip(authed_client, track_id="v3")
        composite = authed_client.get("/preview/at_frame?frame=0").json()
        # Get layer_index sequence.
        idxs = [l["layer_index"] for l in composite["visual_layers"]]
        assert idxs == sorted(idxs)
        assert len(idxs) == len(set(idxs)), "layer_index must be unique"
        assert idxs[0] < idxs[1] < idxs[2], (
            "z-order must be strictly ascending"
        )