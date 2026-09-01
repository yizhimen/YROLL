"""MCP Server tests over the real HTTP backend (GUI-01.5).

The MCP server is a thin HTTP client of `yroll serve <project>`. These
tests use FastAPI's TestClient to host a real Project Server in-process,
point a real McpServer at it, and exercise the JSON-RPC surface.

Why TestClient and not a real port: the project asserts the contract
between McpServer and the Project Server. A real subprocess would add
flakiness (port collisions, race on startup) without proving anything
that TestClient does not. The cross-process authority is proved by
tests/test_mcp_cross_process.py and the @slow subprocess test.
"""
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.server.app import create_app
from yroll.server.mcp_server import McpServer


@pytest.fixture
def backend(tmp_path: Path):
    """Real YROLL HTTP server in a thread + scratch project with one asset.

    Returns (http_url, proj_path). All tests must use the same URL —
    TestClient would create a SECOND ProjectCore and a SECOND LeaseStore
    (the exact bug GUI-01.5 is solving).
    """
    from threading import Thread
    import time
    import uvicorn
    from yroll.server.app import create_app
    ProjectCore.create(str(tmp_path), "mcp-demo")
    proj = ProjectCore.open(tmp_path / "mcp-demo")
    proj.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="dummy.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=10.0),
    ))
    proj.save_state()
    app = create_app(str(proj.path))
    config = uvicorn.Config(app, host="127.0.0.1", port=0,
                             log_level="error", access_log=False)
    server = uvicorn.Server(config)
    t = Thread(target=server.run, daemon=True)
    t.start()
    url = None
    for _ in range(100):
        if server.started and server.servers:
            for s in server.servers:
                for sock in s.sockets:
                    port = sock.getsockname()[1]
                    url = f"http://127.0.0.1:{port}"
                    break
                if url:
                    break
            if url:
                break
        time.sleep(0.05)
    if not url:
        raise RuntimeError("uvicorn did not start in time")
    yield url, str(proj.path)
    server.should_exit = True
    t.join(timeout=2.0)


@pytest.fixture
def mcp(backend):
    """McpServer with .start() already called → agent holds EDIT."""
    url, _ = backend
    srv = McpServer(url, actor_id="claude-code-test")
    srv.start()
    yield srv
    srv.shutdown(release=True)


@pytest.fixture
def mcp_unstarted(backend):
    """McpServer without .start() — use when the test must drive
    ensure/handoff itself (e.g. scenario B from GUI-01.5)."""
    url, _ = backend
    srv = McpServer(url, actor_id="claude-code-test")
    yield srv
    srv.shutdown(release=True)


def _call(srv, name, args, rid=2):
    return srv.handle({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                       "params": {"name": name, "arguments": args}})


def _content(resp):
    assert resp["result"]["isError"] is False, resp
    return json.loads(resp["result"]["content"][0]["text"])


def test_initialize(mcp):
    resp = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05"}})
    assert resp["result"]["serverInfo"]["name"] == "yroll"
    assert "tools" in resp["result"]["capabilities"]


def test_notification_no_response(mcp):
    assert mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_list(mcp):
    resp = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert "yroll_trim" in names
    assert "yroll_analyze_loudness" in names
    assert "yroll_get_project" in names
    assert "yroll_search_transcripts" in names


def test_unknown_tool(mcp):
    resp = _call(mcp, "yroll_nope", {})
    assert "error" in resp


def test_yroll_get_project_reads_via_http(mcp):
    proj = _content(_call(mcp, "yroll_get_project", {}))
    assert proj["name"] == "mcp-demo"
    assert any(a["asset_id"] == "a1" for a in proj["assets"])


def test_yroll_trim_writes_via_http_and_logs_with_who_ai(mcp, backend):
    """End-to-end: an MCP-driven trim lands in the operation log and
    is visible via /operations (the GUI's truth source).

    The mcp fixture already called .start() which ran /session/ensure
    and got the agent EDIT lease (nobody else holds). So we just seed
    a clip via /clips and trim it via MCP.
    """
    from urllib import request as urlrequest, parse as urlparse
    import json as _json
    url, _proj = backend

    def http_post(path, body):
        data = _json.dumps(body).encode()
        req = urlrequest.Request(
            url + path, data=data, method="POST",
            headers={"Content-Type": "application/json"})
        with urlrequest.urlopen(req, timeout=5) as r:
            return r.status, _json.loads(r.read())

    # Seed: use the MCP's already-acquired session to add a clip.
    # R6-B: /clips is frame-native; use *_frame keys.
    sid = mcp.state["sessionId"]
    qs = urlparse.urlencode({"sessionId": sid, "baseRevision": 0})
    _, body = http_post(f"/clips?{qs}", {
        "asset_id": "a1",
        "source_start_frame": 0, "source_end_frame": 300,
        "timeline_start_frame": 0, "track_id": "V1", "why": "seed",
    })
    clip_id = body.get("clip", {}).get("clip_id") or body.get("clip_id")
    assert clip_id, f"no clip_id in add response: {body}"
    # The seed add_clip happened via raw HTTP, so McpServer's state
    # still carries the old base_revision. Refresh it before trimming.
    mcp.state["base_revision"] = mcp.client.ui_status().get(
        "base_revision", mcp.state["base_revision"])

    op = _content(_call(mcp, "yroll_trim",
                        {"clip_id": clip_id, "new_source_start_frame": 60,
                         "new_source_end_frame": 300,
                         "why": "MCP 跨进程测试"}))
    assert op["type"] == "trim"
    state = _content(_call(mcp, "yroll_get_project", {}))
    assert state["clips"][clip_id]["source_range"]["start"] == 2.0
    ops = _content(_call(mcp, "yroll_list_operations", {}))
    assert any(o["type"] == "trim" and o.get("why") == "MCP 跨进程测试"
               for o in ops)


def test_unknown_clip_returns_iserror(mcp):
    resp = _call(mcp, "yroll_trim", {"clip_id": "nope-clip",
                                       "new_source_start": 1.0})
    assert resp["result"]["isError"] is True
    text = resp["result"]["content"][0]["text"]
    # The HTTP server returns 400 "clip 不存在" for a missing clip —
    # the MCP client surfaces it as a non-gate error.
    assert "不存在" in text or "400" in text


def test_serve_stdio_roundtrip(mcp):
    """End-to-end: line-delimited JSON-RPC in → out."""
    lines = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping"}),
    ])
    out = io.StringIO()
    mcp.serve_stdio(instream=io.StringIO(lines), outstream=out)
    replies = [json.loads(l) for l in out.getvalue().strip().splitlines()]
    assert len(replies) == 3  # notification had no response
    assert replies[0]["result"]["serverInfo"]["name"] == "yroll"
    assert len(replies[1]["result"]["tools"]) >= 10
    assert replies[2]["result"] == {}
