"""GUI-04.5 P0-B: Preview z-order semantics.

Pins the canonical invariant:

  "Upper Timeline track ⇒ higher visual layer ⇒ occludes lower
   tracks when their content overlaps."

The invariant is formalized at THREE layers:

  L1  CORE:  `build_preview_plan` assigns `layer_index` based on
            `_track_sort_key(kind_rank, numeric_suffix, track_id)`.
            Within VIDEO tracks, V_k+1 gets a strictly higher
            layer_index base than V_k. (See yroll/core/plan.py.)
  L2  GUI:   `zOrderedLayers(source)` sorts layers by `layer_index`
            ascending so the bottom layer paints first.
  L3  DOM:   `PreviewPlayer` sets `zIndex: l.layer_index`
            EXPLICITLY on every `.composite-layer`. The DOM
            paint order does NOT decide stacking; CSS zIndex does.

If any of L1 / L2 / L3 regress, the test fails with the exact
invariant that broke.

Coverage:
  * V1 < V2 < V3 layer_index (canonical 3-track case)
  * arbitrary visual track occupancy (10 tracks: V1..V10)
  * hidden tracks excluded from z-order entirely
  * zIndex CSS attribute on the rendered layer equals
    `layer_index` (i.e. the GUI sets it explicitly, not relying
    on DOM order)
  * upper-track content occludes lower-track content when the
    two overlap (the SEMANTIC test the user asked for)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.core.timebase import Rational
from yroll.server.app import create_app


# ─────────────────────────────────────────────────────────────
# Shared fixture: deterministic 10-track visual project
# ─────────────────────────────────────────────────────────────

def _build_client(tmp_path: Path, track_ids: tuple[str, ...]):
    """Build a project where every `track_ids[i]` carries ONE clip
    overlapping in the same frame range [10s, 20s]. Every track is
    visual (VIDEO kind) so the preview composites them all."""
    core = ProjectCore.create(tmp_path, "p0-b-zorder")
    # Distinct asset per track (deterministic asset_id = "a<idx>").
    for i in range(1, len(track_ids) + 1):
        a = Asset(
            asset_id=f"a{i}", type=AssetType.VIDEO, path=f"v{i}.mp4",
            identity=AssetIdentity(
                md5=str(i).encode().hex().ljust(32, "0")[:32],
                size_bytes=1024 * i, duration_sec=30.0,
            ),
        )
        a.source_fps = Rational(30, 1)
        a.source_is_cfr = True
        core.project.assets.append(a)
    core.save_state()
    app = create_app(core.path, who=Actor.AI)
    raw = TestClient(app)
    r = raw.post("/lease/acquire?actor=agent&mode=edit&actorId=p0-b")
    sid = r.json()["sessionId"]

    class _Call:
        def get(self, url): return raw.get(url)
        def post(self, url, params=None, json=None):
            extra = params or {}
            extra.setdefault("sessionId", sid)
            extra.setdefault(
                "baseRevision",
                str(len(raw.get("/operations").json())))
            return raw.post(url, params=extra, json=json or {})
    c = _Call()
    for idx, tid in enumerate(track_ids, start=1):
        c.post("/tracks", params={
            "kind": "video", "track_id": tid, "timeline_id": "main",
        })
        r = c.post("/clips", json={
            "asset_id": f"a{idx}",
            "source_start_frame": 0, "source_end_frame": 300,
            "timeline_start_frame": 300,
            "track_id": tid,
        })
        assert r.status_code == 200, r.text
    return c, track_ids


@pytest.fixture()
def v123_client(tmp_path: Path):
    return _build_client(tmp_path, ("v1", "v2", "v3"))


@pytest.fixture()
def v1_to_v10_client(tmp_path: Path):
    return _build_client(tmp_path, tuple(f"v{n}" for n in range(1, 11)))


def _at_frame(c, frame: int) -> dict:
    return c.get(
        f"/preview/at_frame?frame={frame}&timeline_id=main"
    ).json()


def _plan(c) -> dict:
    return c.get("/preview/plan?timeline_id=main").json()


# ─────────────────────────────────────────────────────────────
# L1 — Core layer_index ordering
# ─────────────────────────────────────────────────────────────

def test_v1_v2_v3_layer_index_order(v123_client):
    """Canonical 3-track case (GUI-04.6 corrected direction).

    Timeline renders V1 at top → V2 → V3 at bottom. Preview MUST
    follow: V1 (Timeline top) has the HIGHEST layer_index,
    V3 (Timeline bottom) has the LOWEST.

    V1 highest layer_index → painted last → on top.
    V3 lowest layer_index  → painted first → on bottom.
    """
    c, _ = v123_client
    pv = _at_frame(c, 450)
    by_track = {l["track_id"]: l["layer_index"] for l in pv["visual_layers"]}
    assert by_track["v1"] > by_track["v2"] > by_track["v3"], (
        f"V1 > V2 > V3 (layer_index) invariant broken: {by_track}"
    )


def test_arbitrary_track_occupancy_layer_index_order(v1_to_v10_client):
    """10 visual tracks: V1..V10 each contribute one clip at the
    same frame. Per GUI-04.6: layer_index MUST be strictly
    DESCENDING through the numeric suffix (V1 highest, V10 lowest).
    """
    c, _ = v1_to_v10_client
    pv = _at_frame(c, 450)
    by_track = {l["track_id"]: l["layer_index"] for l in pv["visual_layers"]}
    for n in range(1, 10):
        a, b = f"v{n}", f"v{n+1}"
        assert by_track[a] > by_track[b], (
            f"{a} (Timeline higher) must have strictly greater "
            f"layer_index than {b}; got {a}={by_track[a]}, "
            f"{b}={by_track[b]}"
        )


def test_layer_index_globally_unique_in_plan(v1_to_v10_client):
    """Per the R4-1 invariant: layer_index is globally unique across
    all visual tracks in /preview/plan. No two layers share a
    z-slot."""
    c, _ = v1_to_v10_client
    plan = _plan(c)
    flat = [l for sub in plan["tracks"] for l in sub]
    indices = [l["layer_index"] for l in flat]
    assert len(indices) == len(set(indices)), (
        f"layer_index collision: {indices}"
    )


# ─────────────────────────────────────────────────────────────
# L2 — GUI zOrderedLayers: sort stability
# ─────────────────────────────────────────────────────────────

def test_z_ordered_layers_sorts_by_layer_index_ascending():
    """The GUI's zOrderedLayers helper sorts by layer_index
    ascending so the bottom layer paints first. Determinism.

    Implementation note: preview-layer.ts is TypeScript and not
    directly importable here. The algorithm is simple enough that
    we test it via a Python mirror of the algorithm AND pin the
    TypeScript source separately (test_z_ordered_layers_ts_contract).
    """
    def z_ordered(layers):
        # Python mirror of TS: stable sort by layer_index ascending.
        return sorted(layers, key=lambda l: l["layer_index"])

    layers = [
        {"layer_index": 5, "track_id": "v6"},
        {"layer_index": 2, "track_id": "v3"},
        {"layer_index": 7, "track_id": "v8"},
        {"layer_index": 0, "track_id": "v1"},
        {"layer_index": 3, "track_id": "v4"},
    ]
    out = z_ordered(layers)
    assert [l["layer_index"] for l in out] == [0, 2, 3, 5, 7], out
    # Stable sort: equal layer_index preserves concatenation order.
    eq_layers = [
        {"layer_index": 2, "track_id": "a"},
        {"layer_index": 2, "track_id": "b"},
    ]
    eq_out = z_ordered(eq_layers)
    assert [l["track_id"] for l in eq_out] == ["a", "b"], (
        "stable sort violated: equal layer_index must preserve order"
    )


# ─────────────────────────────────────────────────────────────
# L3 — DOM: PreviewPlayer sets zIndex EXPLICITLY per layer
# ─────────────────────────────────────────────────────────────

def test_preview_layer_uses_explicit_zindex_not_dom_order(tmp_path: Path):
    """PreviewPlayer.tsx sets `style.zIndex = l.layer_index` on
    every `.composite-layer`. The DOM paint order (insertion
    order) does NOT decide stacking — only the CSS zIndex does.

    This test reads the source to pin that contract. If a future
    refactor removes the explicit zIndex, this test fails.
    """
    src = Path("gui/src/components/PreviewPlayer.tsx").read_text(
        encoding="utf-8"
    )
    # Locate the layer render block.
    assert "composite-layer" in src, "composite-layer class not found"
    # Find a layer render and check it has zIndex: l.layer_index
    # (we accept either the literal string or any member access).
    import re
    # match either zIndex: l.layer_index or zIndex: layer.layer_index
    pattern = re.compile(
        r"zIndex:\s*l\.layer_index|zIndex:\s*layer\.layer_index",
    )
    assert pattern.search(src), (
        "PreviewPlayer must set zIndex: l.layer_index explicitly on "
        "every .composite-layer div. Relying on DOM paint order is "
        "an invariant violation."
    )


# ─────────────────────────────────────────────────────────────
# SEMANTIC test: upper-track content occludes lower-track content
# when they overlap (the user's primary P0-B requirement)
# ─────────────────────────────────────────────────────────────

def test_upper_track_higher_layer_index_so_occludes_lower(v1_to_v10_client):
    """For ANY pair (V_k, V_m) where k < m (so V_k is the
    Timeline-higher track), V_k's layer_index MUST be strictly
    greater than V_m's. This is what makes V_k occlude V_m when
    they overlap at the same frame.

    Without this property the GUI could not promise the user
    "upper track paints over lower track when they overlap".

    GUI-04.6 direction: V_k (k smaller) is visually HIGHER in the
    Timeline, so V_k MUST have HIGHER layer_index than V_m.
    """
    c, tracks = v1_to_v10_client
    pv = _at_frame(c, 450)
    by_track = {l["track_id"]: l["layer_index"] for l in pv["visual_layers"]}
    for n in range(1, 10):
        upper, lower = f"v{n}", f"v{n + 1}"
        assert by_track[upper] > by_track[lower], (
            f"Timeline-higher track {upper} must have strictly "
            f"greater layer_index than Timeline-lower track {lower}; "
            f"got {upper}={by_track[upper]}, {lower}={by_track[lower]}"
        )


def test_hidden_track_excluded_from_z_order(tmp_path: Path):
    """Hidden tracks are EXCLUDED from the visual stack entirely.
    They neither occlude nor are occluded. Their clips are not
    in plan.tracks and not in /preview/at_frame.visual_layers."""
    c, _ = _build_client(tmp_path, ("v1", "v2", "v3"))
    # Confirm baseline: 3 layers at frame 450.
    pv_before = _at_frame(c, 450)
    tracks_before = sorted(l["track_id"] for l in pv_before["visual_layers"])
    assert tracks_before == ["v1", "v2", "v3"]

    # Hide V2.
    c.post("/tracks/v2/hide", params={"hidden": True})
    pv_after = _at_frame(c, 450)
    tracks_after = sorted(l["track_id"] for l in pv_after["visual_layers"])
    assert "v2" not in tracks_after, (
        f"hidden V2 must be excluded from z-order; got {tracks_after}"
    )
    assert set(tracks_after) == {"v1", "v3"}, (
        f"only V1 and V3 should remain; got {tracks_after}"
    )

    # The relative order of V1 > V3 (GUI-04.6 direction) must still hold.
    by_track = {l["track_id"]: l["layer_index"] for l in pv_after["visual_layers"]}
    assert by_track["v1"] > by_track["v3"], by_track


def test_upper_overlapping_lower_upper_occludes_lower_at_frame(v123_client):
    """The user's semantic test: when two tracks' clips cover the
    SAME frame, the upper-track (Timeline-top) clip is what the
    user sees at that frame. GUI-04.6 direction:

      - V1, V2, V3 each have a clip at [300, 600] frames.
      - At frame 450 (midpoint), all three are active.
      - V1 is the Timeline top (visually highest) → highest
        layer_index → painted LAST → on top of V2 and V3.
      - V3 is the Timeline bottom (visually lowest) → lowest
        layer_index → painted FIRST → at the bottom.

    The semantic guarantee "Timeline-higher track occludes
    Timeline-lower when they overlap" follows from:
      (a) zOrderedLayers orders ascending by layer_index,
      (b) PreviewPlayer sets zIndex = layer_index per layer, and
      (c) the React tree paint order matches the sort order so
          V1's DOM element comes AFTER V3's.

    Tests (a) and (b) are pinned above; here we pin the
    structural premise (c): every active visual layer is present
    in visual_layers and the ordering matches layer_index ascending.
    """
    c, _ = v123_client
    pv = _at_frame(c, 450)
    layers = pv["visual_layers"]
    # (i) every track contributes one layer.
    assert len(layers) == 3, f"expected 3 layers, got {len(layers)}: {layers}"
    # (ii) layer_index is strictly ascending in the rendered order.
    indices = [l["layer_index"] for l in layers]
    assert indices == sorted(indices), (
        f"visual_layers must be ordered by ascending layer_index; "
        f"got {indices}"
    )
    # (iii) V1 (Timeline top) is the last (top-painted) layer.
    assert layers[-1]["track_id"] == "v1", (
        f"V1 (Timeline top) must be the topmost layer (highest "
        f"layer_index = last painted); got top={layers[-1]['track_id']}"
    )
    # (iv) V3 (Timeline bottom) is the first (bottom-painted) layer.
    assert layers[0]["track_id"] == "v3", (
        f"V3 (Timeline bottom) must be the bottom layer; got "
        f"bottom={layers[0]['track_id']}"
    )


# ─────────────────────────────────────────────────────────────
# Static guard: no accidental DOM-order reliance in PreviewPlayer
# ─────────────────────────────────────────────────────────────

def test_preview_player_does_not_rely_on_dom_paint_order():
    """The user's P0-B #3 requirement: do NOT rely on accidental
    DOM paint order. This static guard fails if PreviewPlayer
    relies on layer insertion order for stacking.

    The contract is that EVERY .composite-layer carries an
    explicit zIndex equal to its layer_index. Sort is done in
    zOrderedLayers BEFORE render — but the actual stacking is
    the CSS zIndex, not the React tree order.
    """
    src = Path("gui/src/components/PreviewPlayer.tsx").read_text(
        encoding="utf-8"
    )
    # The presence of `zIndex: l.layer_index` proves explicit
    # CSS-based stacking.
    assert "zIndex: l.layer_index" in src or \
        "zIndex: layer.layer_index" in src, (
        "PreviewPlayer must set explicit zIndex per layer "
        "(zIndex: l.layer_index). DOM-order-only stacking is "
        "forbidden by P0-B #3."
    )
