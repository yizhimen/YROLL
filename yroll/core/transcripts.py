"""Project Memory 转写读取（单一出处）。

蓝图："AI 分析一次，长期使用"——转写在 ingest 阶段入 memory.json，
chat 上下文、自动字幕生成共用这一个读取入口。
"""

from __future__ import annotations

import json
from pathlib import Path

from yroll.core.manifest import Project


def load_transcripts(project: Project) -> dict[str, list[dict]]:
    """从源 Project Memory 取转写（extensions.memory 指针）。
    返回 {asset_id: [{"start": float, "end": float, "text": str}, ...]}。"""
    ptr = project.extensions.get("memory") if project.extensions else None
    if not ptr:
        return {}
    try:
        mem_file = Path(ptr["root"]) / ".yroll" / ptr["name"] / "memory.json"
        data = json.loads(mem_file.read_text(encoding="utf-8"))
        return data.get("transcripts", {})
    except Exception:
        return {}
