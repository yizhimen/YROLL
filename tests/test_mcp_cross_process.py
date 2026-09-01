"""GUI-01.5: cross-process integration tests, A–G.

The contract under test: a running `yroll serve` is the sole owner of
ProjectCore + LeaseStore + Revision. The MCP server (in any process)
must route every project-state write through the HTTP API, carrying
sessionId + baseRevision. The scenarios below each exercise one
invariant the GUI-01.5 spec demands.

All tests use a real uvicorn-served YROLL backend in a thread (see
tests/_cross_process.py). TestClient is intentionally not used — it
constructs a SECOND ProjectCore against the same directory and a
SECOND LeaseStore, which is the exact bug this batch fixes.
"""
import pytest

from tests._cross_process import (
    backend, mcp_for, call_tool, content, seed_clip, http_post,
    http_get, refresh_revision, project_dump, operations_count,
    grant_edit_to,
)


# ---------------------------------------------------------------------------
# A. Human holds EDIT → MCP mutation must be refused
# ---------------------------------------------------------------------------

def test_human_holds_edit_blocks_mcp_commit(backend):
    """Scenario A: GUI/Human holds EDIT; MCP request to commit is
    refused by the Mutation Gate. The MCP tool surfaces the refusal
    as a structured isError response.

    The implementation choice: in non-EDIT mode the MCP routes
    mutations through /mutation/preview, not a hard 403. So the
    observable behaviour is: MCP gets a preview body, no operation
    is logged, and no project state changes.
    """
    url, _ = backend
    # Human acquires
    _, h = http_post(url, "/lease/acquire", {}, params={"actor": "human", "mode": "edit", "humanLabel": "User"})
    human_sid = h["sessionId"]
    clip_id = seed_clip(url, session_id=human_sid, base_revision=0)
    ops_before = operations_count(url)

    # MCP starts → observe (because human holds)
    mcp = mcp_for(url, actor_id="claude-A")
    mcp.start()
    assert mcp.state["mode"] == "observe", mcp.state
    assert mcp.state["owner"] == "human", mcp.state

    # MCP attempts a trim → routed to /mutation/preview, NOT committed
    refresh_revision(mcp)
    resp = call_tool(mcp, "yroll_trim", {"clip_id": clip_id, "new_source_start": 3.0})
    body = content(resp)
    assert body.get("preview") is True, body
    # No new operation was logged
    assert operations_count(url) == ops_before
    # Project state unchanged
    state = project_dump(url)
    assert state["clips"][clip_id]["source_range"]["start"] == 0.0
    mcp.shutdown(release=False)


# ---------------------------------------------------------------------------
# B. handoff Human→Agent → MCP can commit
# ---------------------------------------------------------------------------

def test_mcp_succeeds_after_handoff_human_to_agent(backend):
    """Scenario B: handoff transfers the lease; MCP's next mutation
    goes through the gate and lands in the operation log."""
    url, _ = backend
    _, h = http_post(url, "/lease/acquire", {}, params={"actor": "human", "mode": "edit", "humanLabel": "User"})
    human_sid = h["sessionId"]
    clip_id = seed_clip(url, session_id=human_sid, base_revision=0)
    ops_before = operations_count(url)

    mcp = mcp_for(url, actor_id="claude-B")
    mcp.start()
    assert mcp.state["mode"] == "observe"

    # Human hands off to the Agent's actor_id; parked session is promoted
    handoff = http_post(
        url, "/lease/handoff", {},
        params={"fromSessionId": human_sid, "toActor": "agent",
                "toMode": "edit", "toLabel": "Claude", "toActorId": "claude-B"})
    assert handoff[0] == 200, handoff

    # MCP re-ensures → mode=edit
    grant_edit_to(mcp)
    assert mcp.state["mode"] == "edit", mcp.state

    refresh_revision(mcp)
    resp = call_tool(mcp, "yroll_trim", {"clip_id": clip_id, "new_source_start_frame": 60, "new_source_end_frame": 300, "why": "B-test"})
    body = content(resp)
    assert not body.get("_isError"), body
    assert body["type"] == "trim"

    # Operation count bumped by 1
    assert operations_count(url) == ops_before + 1
    # State advanced
    state = project_dump(url)
    assert state["clips"][clip_id]["source_range"]["start"] == 2.0
    mcp.shutdown(release=False)


# ---------------------------------------------------------------------------
# C. Agent holds EDIT → GUI HTTP mutation with wrong sessionId is 403
# ---------------------------------------------------------------------------

def test_agent_holds_edit_blocks_gui_mutation(backend):
    """Scenario C: Agent holds the lease. A raw HTTP mutation from a
    third party (wrong sessionId) is refused by the Mutation Gate.
    """
    url, _ = backend
    mcp = mcp_for(url, actor_id="claude-C")
    mcp.start()
    assert mcp.state["mode"] == "edit"
    clip_id = seed_clip(url, session_id=mcp.state["sessionId"], base_revision=0)

    # A third party tries to mutate with a bogus sessionId
    status, body = http_post(
        url, f"/clips/{clip_id}/trim",
        {"new_source_start_frame":270,"new_source_end_frame":300,"why": "C-test"},
        params={"sessionId": "bogus", "baseRevision": 1})
    assert status == 403, (status, body)
    assert "lease rejected" in str(body)
    # State unchanged
    state = project_dump(url)
    assert state["clips"][clip_id]["source_range"]["start"] == 0.0
    mcp.shutdown(release=False)


# ---------------------------------------------------------------------------
# D. stale baseRevision on MCP path → 409, no silent overwrite
# ---------------------------------------------------------------------------

def test_stale_base_revision_returns_409_for_mcp_path(backend):
    """Scenario D: MCP submits against a stale revision; server
    refuses with 409; no operation is logged; no state change."""
    url, _ = backend
    mcp = mcp_for(url, actor_id="claude-D")
    mcp.start()
    sid = mcp.state["sessionId"]
    clip_id = seed_clip(url, session_id=sid, base_revision=0)
    ops_before = operations_count(url)

    # Bump revision legitimately (add another clip on a different
    # timeline slot to avoid V1 overlap detection).
    seed_clip(url, session_id=sid, base_revision=None, timeline_start_frame=600)
    assert operations_count(url) == ops_before + 1

    # Now try a trim with a STALE baseRevision
    status, body = http_post(
        url, f"/clips/{clip_id}/trim",
        {"new_source_start_frame":210,"new_source_end_frame":270,"why": "D-stale"},
        params={"sessionId": sid, "baseRevision": 0})
    assert status == 409, (status, body)
    assert "revision mismatch" in str(body)
    # Operation count unchanged
    assert operations_count(url) == ops_before + 1
    # State unchanged
    state = project_dump(url)
    assert state["clips"][clip_id]["source_range"]["start"] == 0.0
    mcp.shutdown(release=False)


# ---------------------------------------------------------------------------
# F. lease TTL elapsed → MCP re-acquire succeeds
# ---------------------------------------------------------------------------

def test_lease_expiry_then_recovery_via_mcp(backend):
    """Scenario F: the lease dies (simulate by releasing directly);
    the MCP re-runs /session/ensure and gets a fresh edit lease.
    """
    url, _ = backend
    mcp = mcp_for(url, actor_id="claude-F")
    mcp.start()
    sid1 = mcp.state["sessionId"]
    assert mcp.state["mode"] == "edit"

    # Server-side release; the MCP state still thinks it has the lease
    http_post(url, "/lease/release", params={"sessionId": sid1})

    # MCP re-ensures: should get a NEW sessionId, mode=edit
    grant_edit_to(mcp)
    assert mcp.state["mode"] == "edit"
    assert mcp.state["sessionId"] != sid1, "sessionId should rotate after re-ensure"
    mcp.shutdown(release=False)


# ---------------------------------------------------------------------------
# G. stale-revision attempt never produces a silent overwrite
# ---------------------------------------------------------------------------

def test_no_silent_overwrite_on_mcp_conflict(backend):
    """Scenario G: a stale-revision write attempt is refused and
    produces zero observable change — even if the call is repeated.
    This is the property the spec calls 'no silent overwrite'."""
    url, _ = backend
    mcp = mcp_for(url, actor_id="claude-G")
    mcp.start()
    sid = mcp.state["sessionId"]
    clip_id = seed_clip(url, session_id=sid, base_revision=0)
    ops_before = operations_count(url)
    # Bump revision so the MCP's base_revision=0 is now stale
    seed_clip(url, session_id=sid, base_revision=None, timeline_start_frame=600)

    # Try to trim with stale revision
    for i in range(3):
        status, body = http_post(
            url, f"/clips/{clip_id}/trim",
            {"new_source_start_frame":240,"new_source_end_frame":270,"why": f"G-{i}"},
            params={"sessionId": sid, "baseRevision": 0})
        assert status == 409, (i, status, body)
    # No new ops, no state change
    assert operations_count(url) == ops_before + 1
    state = project_dump(url)
    assert state["clips"][clip_id]["source_range"]["start"] == 0.0
    mcp.shutdown(release=False)
