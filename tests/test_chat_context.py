"""Chat 上下文注入转写文本的测试。"""

import json
from pathlib import Path

from yroll.core.commands import CommandLayer
from yroll.core.project import ProjectCore
from yroll.server.chat import _project_context


def _setup(tmp_path: Path) -> ProjectCore:
    core = ProjectCore.create(tmp_path, "ctx-demo")
    # 模拟源工程记忆（ingest 产物）
    mem_dir = tmp_path / "footage" / ".yroll" / "m1"
    mem_dir.mkdir(parents=True)
    (mem_dir / "memory.json").write_text(json.dumps({
        "transcripts": {
            "a1": [
                {"start": 0.0, "end": 3.0, "text": "大家好我是虎哥"},
                {"start": 3.5, "end": 8.0, "text": "今天看这个柴烧壶"},
            ]
        }
    }, ensure_ascii=False), encoding="utf-8")
    core.project.extensions["memory"] = {"root": str(tmp_path / "footage"), "name": "m1"}
    core.save_state()

    cmd = CommandLayer(core)
    cmd.add_clip("a1", 4.0, 6.0, timeline_start=0.0)  # 源 4-6s：只覆盖第二句
    return core


def test_context_includes_transcript(tmp_path: Path):
    core = _setup(tmp_path)
    ctx = _project_context(core.project)
    assert "说话内容" in ctx
    # 源 4-6s 只覆盖 3.5-8.0 那句；0-3s 那句不在范围内
    assert "今天看这个柴烧壶" in ctx
    assert "大家好" not in ctx


def test_context_without_memory_pointer(tmp_path: Path):
    core = ProjectCore.create(tmp_path, "no-mem")
    CommandLayer(core).add_clip("a1", 0.0, 5.0, timeline_start=0.0)
    ctx = _project_context(core.project)
    assert "说话内容" not in ctx  # 无记忆指针也能正常出上下文
