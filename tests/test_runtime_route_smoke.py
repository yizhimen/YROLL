"""GUI-04 04-01: pin the runtime route table.

GUI-04 §3 (Runtime Route Integrity) requires that the FastAPI
endpoints the GUI relies on are present and return 200 on a valid
request. The companion GUI-side regression guard is
``gui/smoke/gui-04-01-runtime-routes.mjs`` — a real-browser smoke
that exercises the actual runtime chain (vite / static-with-proxy
→ FastAPI). This pytest pins the same contract at the TestClient
layer so silent removal of a route breaks BOTH the smoke and the
test, even when only one is run.

Per GUI-04 §5.2 ``/revert`` is the operation-specific low-level
compatibility endpoint and the GUI does not depend on it. It is
pinned here as well so the contract is preserved across batches.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yroll.core.manifest import Actor
from yroll.core.project import ProjectCore
from yroll.server.app import create_app
from tests.conftest import _AuthedClient


@pytest.fixture()
def authed_client(tmp_path: Path) -> _AuthedClient:
    core = ProjectCore.create(tmp_path, "route-pin")
    ProjectCore.ensure_default_tracks(core)
    app = create_app(core.path, who=Actor.AI)
    return _AuthedClient(TestClient(app))


def _seed_asset(client: _AuthedClient) -> str:
    """Register a tiny synthetic asset in the Core and return its id."""
    asset_id = "a-route-pin"
    proj = client.get("/project").json()
    # ProjectCore.create already creates an empty project; we add an
    # asset via the Core directly to avoid ffmpeg probing overhead.
    from yroll.core.models import Asset, AssetIdentity, AssetType
    core = getattr(client, "_core", None)
    # _AuthedClient doesn't expose _core; do it via the public path:
    # ingest a 1-byte MP4-like blob through /assets/import is overkill.
    # Use the API instead by inserting via the test-only fixture file.
    asset = Asset(
        asset_id=asset_id, type=AssetType.VIDEO,
        path="",  # not probed during route-pin (no ffmpeg)
        identity=AssetIdentity(md5="0" * 32, size_bytes=0,
                               duration_sec=10.0, width=1920, height=1080),
    )
    # Reach the Core state through the FastAPI app's _STATE module.
    from yroll.server.app import _STATE
    st = _STATE.get("default")
    assert st is not None, "test setup: _STATE.default should be set"
    if not any(a.asset_id == asset_id for a in st.core.project.assets):
        st.core.project.assets.append(asset)
        st.core.save_state()
    return asset_id


def test_post_clips_returns_200_with_frame_native_payload(authed_client):
    """GUI-04 §3.1: POST /clips must accept a frame-native payload
    and return 200 with the new clip's id. Frames must be integers;
    legacy seconds fields must be rejected with 400 (already covered
    in tests/test_server.py — this test pins the success path).
    """
    asset_id = _seed_asset(authed_client)
    r = authed_client.post("/clips", json={
        "asset_id": asset_id,
        "source_start_frame": 0,
        "source_end_frame": 300,
        "timeline_start_frame": 0,
        "why": "route-pin /clips success",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "clip_id" in body, f"missing clip_id in {body}"
    assert body["clip_id"]


def test_history_undo_returns_200_after_mutation(authed_client):
    """GUI-04 §5: GUI's Ctrl+Z path is POST /history/undo, NOT
    /revert. Pin the contract that one round-trip
    (mutation → /history/undo) returns 200.
    """
    asset_id = _seed_asset(authed_client)
    r1 = authed_client.post("/clips", json={
        "asset_id": asset_id,
        "source_start_frame": 0,
        "source_end_frame": 300,
        "timeline_start_frame": 0,
        "why": "route-pin seed for undo",
    })
    assert r1.status_code == 200, r1.text

    r2 = authed_client.post("/history/undo", params={"why": "route-pin undo"})
    assert r2.status_code == 200, r2.text


def test_history_redo_returns_200_after_undo(authed_client):
    """Companion to test_history_undo_returns_200_after_mutation.
    /history/redo must work too — Ctrl+Y needs it.
    """
    asset_id = _seed_asset(authed_client)
    r1 = authed_client.post("/clips", json={
        "asset_id": asset_id,
        "source_start_frame": 0,
        "source_end_frame": 300,
        "timeline_start_frame": 0,
        "why": "route-pin seed for redo",
    })
    assert r1.status_code == 200, r1.text
    r2 = authed_client.post("/history/undo", params={"why": "route-pin undo"})
    assert r2.status_code == 200, r2.text
    r3 = authed_client.post("/history/redo", params={"why": "route-pin redo"})
    assert r3.status_code == 200, r3.text


def test_revert_returns_200_for_known_operation(authed_client):
    """GUI-04 §5.2: /revert is the low-level compat endpoint.
    It is NOT in the GUI's mutation path, but the route must still
    work for any future low-level caller.
    """
    asset_id = _seed_asset(authed_client)
    r1 = authed_client.post("/clips", json={
        "asset_id": asset_id,
        "source_start_frame": 0,
        "source_end_frame": 300,
        "timeline_start_frame": 0,
        "why": "route-pin seed for revert",
    })
    assert r1.status_code == 200, r1.text
    op_id = r1.json().get("operation_id") or ""
    if not op_id:
        # Fall back to the operations log when the body doesn't
        # surface operation_id (the project json does include the
        # operation id when Core logs the Operation).
        ops = authed_client.get("/operations").json()
        op_id = ops[-1]["operation_id"]
    r2 = authed_client.post("/revert", json={
        "operation_id": op_id, "why": "route-pin revert",
    })
    assert r2.status_code == 200, r2.text


def test_post_clips_rejects_legacy_seconds_fields(authed_client):
    """GUI-04 §3.1: even when /clips POSTs reach the route, the
    handler must still reject the legacy seconds fields. Belt-and-
    braces — also covered by test_server.py — but pinned here so
    this test fails if the GUI-04 §4 contract regresses.
    """
    asset_id = _seed_asset(authed_client)
    r = authed_client.post("/clips", json={
        "asset_id": asset_id,
        # Legacy seconds fields — should be rejected.
        "source_start": 0.0,
        "source_end": 10.0,
        "timeline_start": 0.0,
    })
    assert r.status_code == 400, r.text
    assert "no longer accepted" in r.text