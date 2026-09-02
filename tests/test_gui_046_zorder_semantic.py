"""GUI-04.6-C: Preview stacking semantic — explicit occlusion
tests at V1+V2+V9 and V1+V3+V7.

The user's spec is precise:
  - V1, V2, V9 each carry a clip that overlaps the SAME
    TimelineFrame range. At the overlapping frame:
      * V1 must be visually on top of V2.
      * V2 must be visually on top of V9.
  - V1, V3, V7 (non-contiguous) carry overlapping clips.
    The same invariant must hold: V1 on top of V3 on top of V7.

These are SEMANTIC tests: the structure (layer_index ordering)
combined with the renderer's explicit zIndex must produce the
right visual occlusion. We do not assert CSS values here (the
explicit-zIndex contract is pinned in
test_preview_zorder_invariant.py); we assert the LAYER_INDEX
ordering and the visual_layers array order (which the
renderer uses as the React tree paint order, paired with
zIndex = layer_index).
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


def _build_client_with_tracks(tmp_path: Path, track_ids: tuple[str, ...]):
    """Build a project where every `track_ids[i]` carries ONE
    clip overlapping in the SAME frame range [10s, 20s].
    Distinct asset per track so Core won't refuse on identity."""
    core = ProjectCore.create(tmp_path, f"p0-6-{'-'.join(track_ids)}")
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
    sid = raw.post(
        "/lease/acquire?actor=agent&mode=edit&actorId=p0-6"
    ).json()["sessionId"]

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
    return c


def _at_frame(c, frame: int) -> dict:
    return c.get(
        f"/preview/at_frame?frame={frame}&timeline_id=main"
    ).json()


# ─────────────────────────────────────────────────────────────
# V1+V2+V9 (contiguous) — overlap at the same TimelineFrame
# ─────────────────────────────────────────────────────────────

def test_V1_V2_V9_overlap_V1_above_V2(tmp_path: Path) -> None:
    """Three visual tracks (V1, V2, V9) each carry one clip at
    [300, 600] frames. At frame 450 all three are active.

    Timeline renders V1 top → V2 → ... → V9 bottom. Preview
    MUST follow: V1 layer_index highest → painted last → on
    top of V2.
    """
    c = _build_client_with_tracks(tmp_path, ("v1", "v2", "v9"))
    pv = _at_frame(c, 450)
    layers = pv["visual_layers"]
    assert len(layers) == 3, f"expected 3 layers, got {len(layers)}: {layers}"
    by_track = {l["track_id"]: l["layer_index"] for l in layers}
    # V1 (Timeline top) > V2 (Timeline middle) in layer_index.
    assert by_track["v1"] > by_track["v2"], (
        f"V1 must have higher layer_index than V2; got {by_track}"
    )
    # The paint order in visual_layers is ascending by layer_index,
    # so V2 must paint BEFORE V1 (V2 below V1 in the React tree).
    idx_v2 = next(i for i, l in enumerate(layers) if l["track_id"] == "v2")
    idx_v1 = next(i for i, l in enumerate(layers) if l["track_id"] == "v1")
    assert idx_v2 < idx_v1, (
        f"V2 must paint before V1 (lower layer_index); got "
        f"V2 idx={idx_v2}, V1 idx={idx_v1}"
    )


def test_V1_V2_V9_overlap_V2_above_V9(tmp_path: Path) -> None:
    """V2 (Timeline middle) above V9 (Timeline bottom) in Preview."""
    c = _build_client_with_tracks(tmp_path, ("v1", "v2", "v9"))
    pv = _at_frame(c, 450)
    layers = pv["visual_layers"]
    by_track = {l["track_id"]: l["layer_index"] for l in layers}
    assert by_track["v2"] > by_track["v9"], (
        f"V2 must have higher layer_index than V9; got {by_track}"
    )
    idx_v9 = next(i for i, l in enumerate(layers) if l["track_id"] == "v9")
    idx_v2 = next(i for i, l in enumerate(layers) if l["track_id"] == "v2")
    assert idx_v9 < idx_v2, (
        f"V9 must paint before V2; got V9 idx={idx_v9}, V2 idx={idx_v2}"
    )


def test_V1_V2_V9_overlap_full_invariant(tmp_path: Path) -> None:
    """Full invariant: V1 > V2 > V9 in layer_index; V9 paints
    first, V1 paints last. Single test that pins the whole
    occlusion chain for the user's primary case."""
    c = _build_client_with_tracks(tmp_path, ("v1", "v2", "v9"))
    pv = _at_frame(c, 450)
    layers = pv["visual_layers"]
    by_track = {l["track_id"]: l["layer_index"] for l in layers}
    assert by_track["v1"] > by_track["v2"] > by_track["v9"], (
        f"V1 > V2 > V9 invariant broken: {by_track}"
    )
    # visual_layers is sorted ascending by layer_index; the
    # first entry is the bottom-most layer, the last is top-most.
    assert layers[0]["track_id"] == "v9", (
        f"V9 must be the bottom-painted layer; got {layers[0]['track_id']}"
    )
    assert layers[-1]["track_id"] == "v1", (
        f"V1 must be the top-painted layer; got {layers[-1]['track_id']}"
    )


# ─────────────────────────────────────────────────────────────
# V1+V3+V7 (non-contiguous) — overlap at the same TimelineFrame
# ─────────────────────────────────────────────────────────────

def test_V1_V3_V7_noncontiguous_same_invariant(tmp_path: Path) -> None:
    """Non-contiguous tracks V1, V3, V7. The user's spec says
    the same invariant must hold: V1 on top, V7 at the bottom.

    The non-contiguous case is critical because it tests the
    `numeric_suffix` part of `_track_sort_key` — V3 sits
    between V2 (not present) and V4 (not present). The sort
    still produces V1 first, V3 second, V7 third; the REVERSE
    layer_index assignment then gives V1 highest.
    """
    c = _build_client_with_tracks(tmp_path, ("v1", "v3", "v7"))
    pv = _at_frame(c, 450)
    layers = pv["visual_layers"]
    by_track = {l["track_id"]: l["layer_index"] for l in layers}
    assert by_track["v1"] > by_track["v3"] > by_track["v7"], (
        f"V1 > V3 > V7 invariant broken: {by_track}"
    )
    # Paint order: V7 first, V1 last.
    assert layers[0]["track_id"] == "v7", (
        f"V7 (Timeline bottom) must be the bottom-painted layer; "
        f"got {layers[0]['track_id']}"
    )
    assert layers[-1]["track_id"] == "v1", (
        f"V1 (Timeline top) must be the top-painted layer; "
        f"got {layers[-1]['track_id']}"
    )


def test_V1_V3_V7_invariant_via_plan_endpoints(tmp_path: Path) -> None:
    """Cross-check: the same invariant must hold via
    /preview/plan (the cached plan) AND /preview/at_frame (the
    per-frame composite). They MUST agree so the GUI can use
    either endpoint consistently."""
    c = _build_client_with_tracks(tmp_path, ("v1", "v3", "v7"))
    plan = c.get("/preview/plan?timeline_id=main").json()
    flat_plan = [l for sub in plan["tracks"] for l in sub]
    by_plan = {l["track_id"]: l["layer_index"] for l in flat_plan}
    atf = _at_frame(c, 450)
    by_atf = {l["track_id"]: l["layer_index"] for l in atf["visual_layers"]}
    for tid in ("v1", "v3", "v7"):
        assert by_plan[tid] == by_atf[tid], (
            f"{tid}: plan says {by_plan[tid]} but at_frame says "
            f"{by_atf[tid]}; endpoints disagree"
        )


# ─────────────────────────────────────────────────────────────
# Pin the source-level invariant (no CSS z-index patch)
# ─────────────────────────────────────────────────────────────

def test_build_preview_plan_iterates_visual_track_order_in_reverse() -> None:
    """GUI-04.6 source fix: build_preview_plan MUST iterate
    visual_track_order in REVERSE so V1 gets the highest
    layer_index base. A CSS-only patch would not appear here."""
    src = Path("yroll/core/plan.py").read_text(encoding="utf-8")
    # Locate the for-loop that assigns track_layer_base.
    import re
    # Find the loop header.
    match = re.search(
        r"for\s+t\s+in\s+reversed\s*\(\s*visual_track_order\s*\)\s*:",
        src,
    )
    assert match, (
        "build_preview_plan MUST iterate visual_track_order in "
        "REVERSE so the Timeline-top track gets the highest "
        "layer_index. The fix is at the data model layer, not "
        "in CSS."
    )


def test_composite_preview_at_frame_uses_reversed_visual_stack() -> None:
    """GUI-04.6 source fix: composite_preview_at_frame (which
    serves /preview/at_frame) MUST also iterate the visual
    stack in REVERSE so the per-frame layer_index matches the
    cached plan from /preview/plan."""
    src = Path("yroll/core/frame_preview.py").read_text(encoding="utf-8")
    import re
    match = re.search(
        r"for\s+track\s+in\s+reversed\s*\(\s*visual_stack\s*\)\s*:",
        src,
    )
    assert match, (
        "composite_preview_at_frame MUST iterate the visual "
        "stack in REVERSE so its per-frame layer_index matches "
        "/preview/plan."
    )


def test_previewlayer_zindex_matches_layer_index() -> None:
    """The renderer MUST consume layer_index via explicit zIndex
    (not rely on DOM paint order). Pin the contract."""
    src = Path("gui/src/components/PreviewPlayer.tsx").read_text(
        encoding="utf-8"
    )
    import re
    pattern = re.compile(
        r"zIndex:\s*l\.layer_index|zIndex:\s*layer\.layer_index",
    )
    assert pattern.search(src), (
        "PreviewPlayer must set zIndex: l.layer_index explicitly"
    )
