"""Shared helpers for the GUI-01.5 cross-process integration tests.

Provides:
  - backend() fixture: a real uvicorn-served YROLL server in a thread.
  - mcp_for(url, actor_id) builder: returns an McpServer (NOT started)
    that the test can drive through ensure / handoff / shutdown as the
    scenario demands.
  - seed_clip(): use the server's REST API to add a clip so MCP has
    something to mutate; refreshes McpServer's base_revision afterward.

Why a real uvicorn server: the cross-process claim is that GUI and MCP
share Lease + ProjectCore + Revision. TestClient creates a *second*
ProjectCore against the same directory and a *second* LeaseStore — the
exact bug GUI-01.5 is solving. A real HTTP server in a thread shares
everything because the LeaseStore is keyed by `id(core)` and there is
exactly one core in the served process.
"""
import json
import time
from pathlib import Path
from threading import Thread
from typing import Tuple

import pytest
import uvicorn

from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.server.app import create_app
from yroll.server.mcp_server import McpServer


@pytest.fixture
def backend(tmp_path: Path):
    """Yield (http_url, project_path) for a real YROLL server + scratch project."""
    ProjectCore.create(str(tmp_path), "xproc")
    proj = ProjectCore.open(tmp_path / "xproc")
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
    for _ in range(200):
        if server.started and server.servers:
            for s in server.servers:
                for sock in s.sockets:
                    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
                    break
                if url:
                    break
            if url:
                break
        time.sleep(0.05)
    if not url:
        raise RuntimeError("uvicorn did not bind in time")
    yield url, str(proj.path)
    server.should_exit = True
    t.join(timeout=2.0)


def mcp_for(url: str, actor_id: str = "claude-code-x") -> McpServer:
    return McpServer(url, actor_id=actor_id)


def call_tool(srv: McpServer, name: str, args: dict, rid: int = 2) -> dict:
    return srv.handle({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                       "params": {"name": name, "arguments": args}})


def content(resp: dict):
    if resp.get("result", {}).get("isError"):
        return {"_isError": True,
                "text": resp["result"]["content"][0]["text"]}
    return json.loads(resp["result"]["content"][0]["text"])


def seed_clip(url: str, *, session_id: str, base_revision: int = None,
              asset_id: str = "a1", timeline_start: float = 0.0,
              track_id: str = "V1", source_start: float = 0.0,
              source_end: float = 10.0, why: str = "seed") -> str:
    """Add a clip via /clips, return the clip_id.

    If `base_revision` is None, reads the live revision from /operations
    first (the safer default when the caller doesn't know how many ops
    have happened).
    """
    from urllib import request as urlrequest, parse as urlparse, error as urlerror
    if base_revision is None:
        with urlrequest.urlopen(url + "/operations", timeout=5) as r:
            base_revision = len(json.loads(r.read()))
    qs = urlparse.urlencode({"sessionId": session_id, "baseRevision": base_revision})
    data = json.dumps({
        "asset_id": asset_id, "source_start": source_start,
        "source_end": source_end, "timeline_start": timeline_start,
        "track_id": track_id, "why": why,
    }).encode()
    req = urlrequest.Request(url + f"/clips?{qs}", data=data, method="POST",
                              headers={"Content-Type": "application/json"})
    try:
        with urlrequest.urlopen(req, timeout=5) as r:
            body = json.loads(r.read())
    except urlerror.HTTPError as e:
        raise AssertionError(f"seed_clip failed: {e.code} {e.read()[:200]}")
    return body.get("clip", {}).get("clip_id") or body.get("clip_id")


def http_post(url: str, path: str, body: dict = None, params: dict = None):
    from urllib import request as urlrequest, parse as urlparse, error as urlerror
    full = url + path
    if params:
        full += "?" + urlparse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urlrequest.Request(full, data=data, method="POST",
                              headers={"Content-Type": "application/json"} if data else {})
    try:
        with urlrequest.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or "null")
    except urlerror.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(text)
        except Exception:
            return e.code, text


def http_get(url: str, path: str, params: dict = None):
    from urllib import request as urlrequest, parse as urlparse
    full = url + path
    if params:
        full += "?" + urlparse.urlencode(params)
    with urlrequest.urlopen(urlrequest.Request(full, method="GET"), timeout=5) as r:
        return r.status, json.loads(r.read())


def refresh_revision(srv: McpServer) -> int:
    st = srv.client.ui_status()
    srv.state["base_revision"] = st.get("base_revision", srv.state["base_revision"])
    return srv.state["base_revision"]


def project_dump(url: str) -> dict:
    from urllib import request as urlrequest
    with urlrequest.urlopen(url + "/project", timeout=5) as r:
        return json.loads(r.read())


def operations_count(url: str) -> int:
    from urllib import request as urlrequest
    with urlrequest.urlopen(url + "/operations", timeout=5) as r:
        return len(json.loads(r.read()))


def grant_edit_to(srv: McpServer) -> None:
    """Make sure the McpServer's current state has mode=edit.

    Most useful right after a handoff: the McpServer's state dict still
    carries its old mode (e.g. 'observe'). Re-run /session/ensure to
    promote it.
    """
    r = srv.client.ensure_session(
        actor="agent", actor_id=srv.actor_id, intent="edit",
        base_revision=srv.state["base_revision"])
    srv.state["sessionId"] = r.get("sessionId")
    srv.state["mode"] = r.get("mode", srv.state["mode"])
    srv.state["owner"] = r.get("owner", srv.state["owner"])
    srv.state["base_revision"] = r.get("revision", srv.state["base_revision"])
