"""Project Memory 存储：目录式工程 + JSON/SQLite。

Phase 0 用 JSON 单文件存 memory（够用即可），SQLite 留给检索密集阶段。
工程目录结构（目录式，不是单个大文件）：
    <project>/
    ├── memory.json        # ProjectMemory 序列化
    └── cache/keyframes/   # 关键帧
"""

from __future__ import annotations

import json
from pathlib import Path

from yroll.core.models import ProjectMemory


def project_dir(root: str | Path, name: str) -> Path:
    d = Path(root) / ".yroll" / name
    (d / "cache" / "keyframes").mkdir(parents=True, exist_ok=True)
    return d


def save(memory: ProjectMemory) -> Path:
    d = project_dir(memory.root, memory.name)
    p = d / "memory.json"
    p.write_text(
        json.dumps(memory.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return p


def load(root: str | Path, name: str) -> ProjectMemory:
    p = project_dir(root, name) / "memory.json"
    return ProjectMemory.model_validate(json.loads(p.read_text(encoding="utf-8")))
