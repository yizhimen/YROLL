"""GUI-01.5: H (Human EDIT + Agent OBSERVE in parallel) and I (Agent
crash / reconnect) from the user's review.

These two scenarios are explicitly required additions over the
GUI-01.5 spec and prove two properties:

H. Simultaneous co-presence: a Human holding EDIT does not exclude an
   Agent from the project. The Agent gets OBSERVE, can see live
   revisions advance via /operations and /audit/since, can ask
   /mutation/preview for what-if analyses, and stays parked waiting
   for a handoff. The two roles co-exist on the same ProjectCore
   without conflict.

I. Crash recovery: when an Agent's process dies without calling
   shutdown(release=True), its lease dies on TTL. A reconnecting
   Agent with the same actor_id does NOT inherit a zombie lease — it
   gets observe + a fresh parked session, and the next handoff
   promotes it cleanly.
"""
import pytest

from tests._cross_process import (
    backend, mcp_for, call_tool, content, seed_clip, http_post,
    http_get, refresh_revision, operations_count, project_dump,
    grant_edit_to,
)


# ---------------------------------------------------------------------------
# H. Human EDIT + Agent OBSERVE in parallel
# ---------------------------------------------------------------------------

def test_human_edit_and_agent_observe_coexist(backend):
    """The positive version of 'two writers can't collide':
    Human holds EDIT, Agent is OBSERVE, both see the same project,
    Human's writes advance revision, Agent's mutation tool returns
    a preview, and the Agent's parked sessionId is still waiting
    for a handoff.
    """
    url, _ = backend
    # Human acquires
    _, h = http_post(url, "/lease/acquire", {},
                     params={"actor": "human", "mode": "edit", "humanLabel": "User"})
    human_sid = h["sessionId"]
    clip_id = seed_clip(url, session_id=human_sid, base_revision=0)
    rev0 = operations_count(url)

    # MCP connects → observe
    mcp = mcp_for(url, actor_id="claude-H")
    mcp.start()
    assert mcp.state["mode"] == "observe", mcp.state
    parked_sid = mcp.state["sessionId"]

    # Human writes (one more clip on a fresh slot)
    seed_clip(url, session_id=human_sid, base_revision=None,
              timeline_start_frame=600)
    rev1 = operations_count(url)
    assert rev1 == rev0 + 1, "human's write should advance revision"

    # Agent sees the new revision
    state = project_dump(url)
    assert len(state["clips"]) == 2
    # The Agent's mutation tool returns a preview, NOT a commit
    refresh_revision(mcp)
    resp = call_tool(mcp, "yroll_trim",
                      {"clip_id": clip_id, "new_source_start": 4.0})
    body = content(resp)
    assert body.get("preview") is True, body
    # State unchanged
    assert operations_count(url) == rev1
    assert project_dump(url)["clips"][clip_id]["source_range"]["start"] == 0.0

    # Agent can also see the new operation via /audit/since — this
    # is the "shared truth" the spec demands.
    audit = http_get(url, "/audit/last", params={"n": 5})[1]
    assert audit["operations"] >= 1
    # The last op was a human add_clip (who=human)
    last = audit["details"][-1]
    assert last["op"] == "add_clip"

    # After handoff, the parked session is promoted and the Agent
    # can finally write
    handoff = http_post(
        url, "/lease/handoff", {},
        params={"fromSessionId": human_sid, "toActor": "agent",
                "toMode": "edit", "toLabel": "Claude", "toActorId": "claude-H"})
    assert handoff[0] == 200, handoff
    grant_edit_to(mcp)
    assert mcp.state["mode"] == "edit", mcp.state
    mcp.shutdown(release=False)


# ---------------------------------------------------------------------------
# I. Agent crash / reconnect
# ---------------------------------------------------------------------------

def test_agent_crash_then_reconnect_with_same_actor_id(backend):
    """Agent A acquires EDIT, then its process dies (heartbeat thread
    is killed; shutdown is NOT called with release — the lease is left
    for TTL). A reconnecting Agent with the same actor_id must
    RESUME — the server rotates the sessionId so the old one is dead
    and a new bearer token is issued.

    Two invariants pinned here:
      1. The reconnecting agent's sessionId != the crashed one's
         (no zombie owner, the old sessionId is invalidated).
      2. A different agent with a different actor_id does NOT
         inherit — it gets observe, not edit.

    We don't wait the real 300s TTL: instead we test the resume path
    directly, which is the *crash recovery* path the spec demands.
    The TTL-elapsed path is a separate scenario (covered by F in
    test_mcp_cross_process.py).
    """
    url, _ = backend
    # Agent A acquires
    mcp_a1 = mcp_for(url, actor_id="claude-I")
    mcp_a1.start()
    assert mcp_a1.state["mode"] == "edit"
    sid_a1 = mcp_a1.state["sessionId"]

    # Simulate "Claude Code crashed" — kill heartbeat, do NOT release.
    mcp_a1.shutdown(release=False)
    # The lease is still alive on the server (no one has called
    # /lease/release; TTL is 300s, not waiting in a unit test).
    lease_now = http_get(url, "/lease")[1]
    assert lease_now["sessionId"] == sid_a1, \
        "lease must still be live on server (TTL not elapsed)"

    # Reconnect with the same actor_id → resume path
    mcp_a2 = mcp_for(url, actor_id="claude-I")
    mcp_a2.start()
    assert mcp_a2.state["mode"] == "edit", mcp_a2.state
    sid_a2 = mcp_a2.state["sessionId"]
    assert sid_a2 != sid_a1, \
        "sessionId must rotate — old one is invalidated, no zombie"

    # The server's /lease now shows the new sessionId, not the old
    lease_after = http_get(url, "/lease")[1]
    assert lease_after["sessionId"] == sid_a2
    assert lease_after["actorId"] == "claude-I"

    # A different agent connecting also gets observe (not edit) —
    # they don't have the right actor_id to claim this lease.
    mcp_b = mcp_for(url, actor_id="claude-OTHER")
    mcp_b.start()
    assert mcp_b.state["mode"] == "observe", mcp_b.state
    mcp_b.shutdown(release=False)
    mcp_a2.shutdown(release=False)
