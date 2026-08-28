"""Generic Agent Runtime（Task/Turn 循环）测试——用假 LLM 驱动，不依赖真实 API。"""

import json
from pathlib import Path

import pytest

from yroll.core.commands import CommandLayer
from yroll.core.manifest import Actor
from yroll.core.project import ProjectCore
from yroll.harness import runtime
from yroll.harness.runtime import Task


class FakeMessage:
    def __init__(self, content: str):
        msg = type("M", (), {"content": content})()
        self.choices = [type("C0", (), {"message": msg})()]
        self.usage = None


class FakeClient:
    """按队列返回预设回复。"""

    def __init__(self, replies: list[str]):
        self.replies = replies
        self.chat = type("C", (), {"completions": self})()

    def create(self, **_kw):
        return FakeMessage(self.replies.pop(0))


@pytest.fixture()
def setup(tmp_path: Path, monkeypatch):
    core = ProjectCore.create(tmp_path, "task-demo")
    cmd = CommandLayer(core, who=Actor.AI)
    clip = cmd.add_clip("a1", 0.0, 10.0, timeline_start=0.0)

    def use_fake(replies: list[str]):
        fake = FakeClient(replies)
        monkeypatch.setattr(runtime, "_client", lambda: fake)

    return core, cmd, clip, use_fake


def test_multi_turn_task(setup, monkeypatch):
    core, cmd, clip, use_fake = setup
    use_fake([
        # Turn 1：给两个动作
        json.dumps({"reply": "", "actions": [
            {"op": "volume", "clip_id": clip.clip_id, "volume": 0.5},
            {"op": "speed", "clip_id": clip.clip_id, "speed": 2.0},
        ]}),
        # Turn 2：观察结果后总结，无动作 → 结束
        json.dumps({"reply": "音量已降到一半并加速到 2x", "actions": []}),
    ])
    task = Task(CommandLayer(core, who=Actor.AI), "system")
    result = task.run("【当前工程】...", "调小音量再加速")

    assert len(result["applied"]) == 2
    assert result["reply"] == "音量已降到一半并加速到 2x"
    # 事件流完整
    types = [e["type"] for e in result["events"]]
    assert types[0] == "task_started" and types[-1] == "task_finished"
    assert types.count("turn_started") == 2


def test_high_risk_requires_approval(setup, monkeypatch):
    core, cmd, clip, use_fake = setup
    use_fake([
        json.dumps({"reply": "", "actions": [{"op": "remove", "clip_id": clip.clip_id}]}),
        json.dumps({"reply": "删除未获批准", "actions": []}),
    ])
    # 无审批钩子 → 默认拒绝（安全默认）
    task = Task(CommandLayer(core, who=Actor.AI), "system")
    result = task.run("...", "删掉它")
    assert not result["applied"]
    assert result["errors"][0]["error"] == "未获批准"
    assert clip.clip_id in core.project.clips  # 没被删

    # 有审批钩子且批准 → 执行
    use_fake([
        json.dumps({"reply": "", "actions": [{"op": "remove", "clip_id": clip.clip_id}]}),
        json.dumps({"reply": "已删除", "actions": []}),
    ])
    task2 = Task(CommandLayer(core, who=Actor.AI), "system",
                 approval_hook=lambda a: True)
    result2 = task2.run("...", "删掉它")
    assert result2["applied"]
    assert clip.clip_id not in core.project.clips


def test_max_turns_cap(setup, monkeypatch):
    core, cmd, clip, use_fake = setup
    use_fake([
        json.dumps({"reply": "", "actions": [{"op": "volume", "clip_id": clip.clip_id, "volume": 1.0}]}),
    ] * 10)
    task = Task(CommandLayer(core, who=Actor.AI), "system", max_turns=3)
    result = task.run("...", "反复调音量")
    turns = len([e for e in result["events"] if e["type"] == "turn_finished"])
    assert turns == 3  # 死循环防护
