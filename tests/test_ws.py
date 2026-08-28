"""WebSocket 流式 chat 测试。"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yroll.core.commands import CommandLayer
from yroll.core.project import ProjectCore
from yroll.harness import runtime
from yroll.server.app import create_app
from tests.test_harness import FakeClient


def test_ws_chat_streams_events(tmp_path: Path, monkeypatch):
    core = ProjectCore.create(tmp_path, "ws-demo")
    cmd = CommandLayer(core)
    clip = cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)

    fake = FakeClient([
        json.dumps({"reply": "", "actions": [
            {"op": "volume", "clip_id": clip.clip_id, "volume": 0.5}]}),
        json.dumps({"reply": "音量已调低", "actions": []}),
    ])
    monkeypatch.setattr(runtime, "_client", lambda: fake)

    client = TestClient(create_app(core.path))
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"message": "音量调低", "selected_clip": None, "playhead": 0})
        events = []
        while True:
            e = ws.receive_json()
            events.append(e)
            if e["type"] == "done":
                break

    types = [e["type"] for e in events]
    assert types[0] == "task_started"
    assert "turn_started" in types
    assert "action_applied" in types
    assert types[-1] == "done"
    result = events[-1]["result"]
    assert result["reply"] == "音量已调低"
    assert len(result["applied"]) == 1
    # server 从磁盘重开工程（与测试内 core 非同对象），从持久化状态验证
    reopened = ProjectCore.open(core.path)
    assert reopened.project.clips[clip.clip_id].volume == 0.5


def test_ws_plan_mode(tmp_path: Path, monkeypatch):
    """Plan→Preview→Apply：propose 不执行；人确认后才落工程。"""
    core = ProjectCore.create(tmp_path, "plan-demo")
    cmd = CommandLayer(core)
    clip = cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)

    fake = FakeClient([
        json.dumps({"reply": "我打算把音量降到 0.5", "actions": [
            {"op": "volume", "clip_id": clip.clip_id, "volume": 0.5}]}),
    ])
    monkeypatch.setattr(runtime, "_client", lambda: fake)

    client = TestClient(create_app(core.path))
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"message": "音量调低", "plan": True})
        events = []
        plan = None
        while True:
            e = ws.receive_json()
            events.append(e)
            if e["type"] == "plan_proposed":
                plan = e
                break
        assert plan is not None
        assert plan["actions"][0]["op"] == "volume"
        # Plan 阶段未执行
        assert ProjectCore.open(core.path).project.clips[clip.clip_id].volume == 1.0

        # 人点「应用全部」→ Apply 阶段执行
        ws.send_json({"type": "plan_response", "apply": True})
        while True:
            e = ws.receive_json()
            events.append(e)
            if e["type"] == "done":
                break

    types = [e["type"] for e in events]
    assert "action_applied" in types
    assert len(events[-1]["result"]["applied"]) == 1
    assert ProjectCore.open(core.path).project.clips[clip.clip_id].volume == 0.5


def test_ws_plan_discard(tmp_path: Path, monkeypatch):
    """计划被放弃 → 不落任何修改。"""
    core = ProjectCore.create(tmp_path, "plan-discard")
    cmd = CommandLayer(core)
    clip = cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)

    fake = FakeClient([
        json.dumps({"reply": "计划", "actions": [
            {"op": "volume", "clip_id": clip.clip_id, "volume": 0.1}]}),
    ])
    monkeypatch.setattr(runtime, "_client", lambda: fake)

    client = TestClient(create_app(core.path))
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"message": "音量调低", "plan": True})
        while True:
            e = ws.receive_json()
            if e["type"] == "plan_proposed":
                break
        ws.send_json({"type": "plan_response", "apply": False})
        while True:
            e = ws.receive_json()
            if e["type"] == "done":
                break
        assert "已放弃" in e["result"]["reply"]
    assert ProjectCore.open(core.path).project.clips[clip.clip_id].volume == 1.0
