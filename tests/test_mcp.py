"""MCP Server 测试：握手 / tools/list / tools/call 全链路（不经 stdio，直接 handle）。"""

import json
from pathlib import Path

import pytest

from yroll.core.manifest import Actor
from yroll.core.models import Asset, AssetIdentity, AssetType
from yroll.core.project import ProjectCore
from yroll.server.mcp_server import McpServer


@pytest.fixture
def server(tmp_path: Path):
    core = ProjectCore.create(tmp_path, "mcp-demo")
    core.project.assets.append(Asset(
        asset_id="a1", type=AssetType.VIDEO, path="dummy.mp4",
        identity=AssetIdentity(md5="x" * 32, size_bytes=1, duration_sec=10.0),
    ))
    core.save_state()
    return McpServer(core.path)


def _call(srv, name, args, rid=2):
    return srv.handle({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                       "params": {"name": name, "arguments": args}})


def _content(resp):
    assert resp["result"]["isError"] is False, resp
    return json.loads(resp["result"]["content"][0]["text"])


def test_initialize(server):
    resp = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2024-11-05"}})
    assert resp["result"]["serverInfo"]["name"] == "yroll"
    assert "tools" in resp["result"]["capabilities"]


def test_notification_no_response(server):
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_list(server):
    resp = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert "yroll_trim" in names
    assert "yroll_analyze_loudness" in names
    assert "yroll_get_project" in names


def test_unknown_tool(server):
    resp = _call(server, "yroll_nope", {})
    assert "error" in resp


def test_tools_call_edit_flow(server):
    # 先加 clip（走 REST 之外的另一条路：直接 CommandLayer 准备数据）
    from yroll.core.commands import CommandLayer

    clip = CommandLayer(server.core).add_clip("a1", 0.0, 10.0, timeline_start=0.0)

    # 外部 Agent 通过 MCP 裁剪
    op = _content(_call(server, "yroll_trim",
                        {"clip_id": clip.clip_id, "new_source_start": 2.0, "why": "MCP 测试"}))
    assert op["type"] == "trim"
    assert op["who"] == "ai"  # 外部 Agent 也是 ai，落日志

    # 工程状态已持久化（MCP 调用后自动 save_state）
    core2 = ProjectCore.open(server.core.path)
    assert core2.project.clips[clip.clip_id].source_range.start == 2.0

    # Operation Log 对外可见
    ops = _content(_call(server, "yroll_list_operations", {}))
    assert any(o["type"] == "trim" and o.get("why") == "MCP 测试" for o in ops)


def test_command_error_returned_as_iserror(server):
    resp = _call(server, "yroll_trim", {"clip_id": "不存在", "new_source_start": 1.0})
    assert resp["result"]["isError"] is True
    assert "clip 不存在" in resp["result"]["content"][0]["text"]


def test_serve_stdio_roundtrip(server, tmp_path: Path):
    """端到端：行分隔 JSON-RPC 进 → 出行。"""
    import io

    lines = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping"}),
    ])
    out = io.StringIO()
    server.serve_stdio(instream=io.StringIO(lines), outstream=out)
    replies = [json.loads(l) for l in out.getvalue().strip().splitlines()]
    assert len(replies) == 3  # 通知无响应
    assert replies[0]["result"]["serverInfo"]["name"] == "yroll"
    assert len(replies[1]["result"]["tools"]) >= 10
    assert replies[2]["result"] == {}
