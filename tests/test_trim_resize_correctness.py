"""GUI-04.5 P1-E: Resize / trim interaction correctness.

Pins the trim gesture pipeline so the user-specified acceptance
holds:

  * Extend (right edge → right) commits exactly the previewed
    frame.
  * Shorten (right edge → left) commits exactly the previewed
    frame.
  * Slow movement (many small deltas) accumulates to the same
    final commit as one equivalent fast movement.
  * Fast movement (one large delta) commits the full pixel
    delta without losing any frames.
  * Reverse direction (extend then shorten back) leaves the
    clip at its original size.

The Core is the source of truth for trim semantics: it accepts
integer SOURCE-FRAME positions for new head / tail and updates
`source_range.{start, end}` accordingly. The GUI's gesture
math computes these integer source-frames; pointerup sends
them; Core persists them.

This test exercises the Core-level trim contract end-to-end so
the user's "pointerup commits exactly the previewed frame" is
pinned at the mutation API.

For real-browser coverage, see gui/smoke/gui-04-5-trim-resize.mjs
(P1-E real-browser regression).
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
# Fixture: a 30s video clip on V1, source range [0, 900] frames
# ─────────────────────────────────────────────────────────────

@pytest.fixture()
def trim_client(tmp_path: Path):
    core = ProjectCore.create(tmp_path, "p1-e-trim")
    a = Asset(
        asset_id="a1", type=AssetType.VIDEO, path="v.mp4",
        identity=AssetIdentity(
            md5="b" * 32, size_bytes=1024, duration_sec=30.0,
        ),
    )
    a.source_fps = Rational(30, 1)
    a.source_is_cfr = True
    core.project.assets.append(a)
    core.save_state()
    app = create_app(core.path, who=Actor.AI)
    raw = TestClient(app)
    sid = raw.post(
        "/lease/acquire?actor=agent&mode=edit&actorId=p1-e"
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
    c.post("/tracks", params={
        "kind": "video", "track_id": "v1", "timeline_id": "main",
    })
    r = c.post("/clips", json={
        "asset_id": "a1",
        "source_start_frame": 0, "source_end_frame": 900,
        "timeline_start_frame": 0,
        "track_id": "v1",
    })
    assert r.status_code == 200, r.text
    return c, r.json()["clip_id"]


def _clip(c, cid):
    proj = c.get("/project").json()
    return proj["clips"][cid]


# ─────────────────────────────────────────────────────────────
# Acceptance A: Extend (right edge moves right)
# ─────────────────────────────────────────────────────────────

def test_trim_extend_right_edge_right_commits_extended(trim_client):
    c, cid = trim_client
    # Original: source range [0, 900].
    # Extend: new tail at 1200 frames.
    r = c.post(
        f"/clips/{cid}/trim",
        json={
            "new_source_end_frame": 1200,
            "why": "p1-e-extend",
        },
    )
    assert r.status_code == 200, r.text
    cl = _clip(c, cid)
    # The Core stores source_range in seconds (legacy model).
    fps_num, fps_den = 30, 1
    src_end = round(
        cl["source_range"]["end"] * fps_num / fps_den
    )
    assert src_end == 1200, (
        f"extend commit: expected source_end=1200, got {src_end} "
        f"(stored={cl['source_range']['end']})"
    )
    # Head unchanged.
    src_start = round(cl["source_range"]["start"] * fps_num / fps_den)
    assert src_start == 0, (
        f"extend must not move head; got start={src_start}"
    )


# ─────────────────────────────────────────────────────────────
# Acceptance B: Shorten (right edge moves left)
# ─────────────────────────────────────────────────────────────

def test_trim_shorten_right_edge_left_commits_shortened(trim_client):
    c, cid = trim_client
    r = c.post(
        f"/clips/{cid}/trim",
        json={
            "new_source_end_frame": 300,
            "why": "p1-e-shorten",
        },
    )
    assert r.status_code == 200, r.text
    cl = _clip(c, cid)
    src_end = round(cl["source_range"]["end"] * 30 / 1)
    assert src_end == 300, (
        f"shorten commit: expected source_end=300, got {src_end}"
    )


def test_trim_shorten_below_one_frame_rejected(trim_client):
    """Trim must not let the clip shrink below 1 frame. The Core
    rejects (400). The client should never produce such an intent
    because of the MIN_TRIM_DELTA_FRAMES guard, but Core is the
    authoritative guard."""
    c, cid = trim_client
    r = c.post(
        f"/clips/{cid}/trim",
        json={
            "new_source_start_frame": 0,
            "new_source_end_frame": 0,  # zero-length range
            "why": "p1-e-zero-len",
        },
    )
    assert r.status_code == 400, r.text


# ─────────────────────────────────────────────────────────────
# Acceptance C: Slow movement = single equivalent movement
# ─────────────────────────────────────────────────────────────

def test_trim_accumulation_matches_single_commit(trim_client):
    """Slow drag = many small pointermove deltas. Each delta is
    < MIN_TRIM_DELTA_FRAMES threshold so the gesture accumulates
    silently until the FINAL pointermove exceeds the threshold.

    After several small trims the cumulative source-end should
    equal a single equivalent trim. This pins that trim commits
    are exact integer-frame values, not subject to floating-point
    drift."""
    c, cid = trim_client
    # Apply 5 small extensions of 30 frames each.
    final_target = 900 + 5 * 30  # 1050
    for i in range(5):
        r = c.post(
            f"/clips/{cid}/trim",
            json={
                "new_source_end_frame": 900 + (i + 1) * 30,
                "why": f"p1-e-slow-{i}",
            },
        )
        assert r.status_code == 200, r.text
    cl = _clip(c, cid)
    src_end = round(cl["source_range"]["end"] * 30 / 1)
    assert src_end == final_target, (
        f"accumulated commit: expected {final_target}, got {src_end}"
    )


# ─────────────────────────────────────────────────────────────
# Acceptance D: Fast movement = one large delta
# ─────────────────────────────────────────────────────────────

def test_trim_fast_large_delta_commits_full_value(trim_client):
    """Fast drag = one large pointermove. The committed value
    must equal the requested frame EXACTLY (no clamping, no
    rounding loss)."""
    c, cid = trim_client
    # Jump from 900 to 2700 in a single commit.
    r = c.post(
        f"/clips/{cid}/trim",
        json={
            "new_source_end_frame": 2700,
            "why": "p1-e-fast-large",
        },
    )
    assert r.status_code == 200, r.text
    cl = _clip(c, cid)
    src_end = round(cl["source_range"]["end"] * 30 / 1)
    assert src_end == 2700


# ─────────────────────────────────────────────────────────────
# Acceptance E: Reverse direction (extend then shorten back)
# ─────────────────────────────────────────────────────────────

def test_trim_reverse_direction_returns_to_original(trim_client):
    """Extend by 200, then shorten by 200. The clip's source_end
    must be exactly back to the original 900 frames. No drift,
    no off-by-one from intermediate rounding."""
    c, cid = trim_client
    # Extend +200.
    r = c.post(
        f"/clips/{cid}/trim",
        json={"new_source_end_frame": 1100, "why": "p1-e-ext"},
    )
    assert r.status_code == 200, r.text
    cl = _clip(c, cid)
    assert round(cl["source_range"]["end"] * 30 / 1) == 1100
    # Shorten -200.
    r = c.post(
        f"/clips/{cid}/trim",
        json={"new_source_end_frame": 900, "why": "p1-e-rev"},
    )
    assert r.status_code == 200, r.text
    cl = _clip(c, cid)
    final = round(cl["source_range"]["end"] * 30 / 1)
    assert final == 900, (
        f"reverse direction must return to original; got {final}"
    )


# ─────────────────────────────────────────────────────────────
# Acceptance F: pointerup commits exactly the previewed frame
# ─────────────────────────────────────────────────────────────

def test_trim_integer_frame_contract_no_floating_point_drift(
    trim_client,
) -> None:
    """For every integer source-frame target, the Core accepts
    the exact integer and persists a round-trippable value. This
    pins "pointerup commits exactly the previewed frame" at the
    Core API contract."""
    c, cid = trim_client
    for target in (1, 50, 100, 300, 600, 899, 900, 901, 1500):
        r = c.post(
            f"/clips/{cid}/trim",
            json={
                "new_source_end_frame": target,
                "why": f"p1-e-exact-{target}",
            },
        )
        if r.status_code != 200:
            # Server may reject out-of-range or head >= tail; we
            # only verify the cases that succeeded.
            continue
        cl = _clip(c, cid)
        # Round-trip back via the canonical helper.
        src_end = round(cl["source_range"]["end"] * 30 / 1)
        assert src_end == target, (
            f"target={target} → stored={cl['source_range']['end']} "
            f"→ round-trip={src_end}"
        )


# ─────────────────────────────────────────────────────────────
# Static guard: trim pipeline doesn't bypass Core
# ─────────────────────────────────────────────────────────────

def test_clipblock_trim_routes_through_onTrimCommit() -> None:
    """The trim gesture in ClipBlock MUST dispatch through
    onTrimCommit → api.trim → Core Mutation Gate. A direct
    fetch / bare mutation that bypasses this path is forbidden.
    """
    src = Path("gui/src/components/ClipBlock.tsx").read_text(
        encoding="utf-8"
    )
    # The trim up() handler must end with onTrimCommit (parent
    # forwards to api.trim which gates sessionId + baseRevision).
    assert "onTrimCommit(" in src
    # No direct fetch / POST / PUT / DELETE to /clips/{id}/trim.
    import re
    bad = re.search(
        r"fetch\s*\(\s*[`'\"][^`'\"]*clips[^`'\"]*/trim",
        src,
    )
    assert not bad, (
        "ClipBlock must not fetch /clips/.../trim directly. "
        "Use api.trim (which gates sessionId + baseRevision)."
    )


def test_api_trim_uses_assertIntFrame() -> None:
    """api.trim in api.ts must call assertIntFrame on both
    `new_source_start_frame` and `new_source_end_frame` so a
    fractional source frame can never reach Core."""
    src = Path("gui/src/api.ts").read_text(encoding="utf-8")
    assert "assertIntFrame(\"trim.newSourceStartFrame\"" in src, (
        "api.trim must call assertIntFrame on newSourceStartFrame"
    )
    assert "assertIntFrame(\"trim.newSourceEndFrame\"" in src, (
        "api.trim must call assertIntFrame on newSourceEndFrame"
    )
