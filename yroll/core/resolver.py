"""Asset Resolver：素材移动/改名后自动找回（纯代码，不需要 LLM）。

寻找顺序（蓝图 §护城河-Asset Intelligence）：
  1. 原路径
  2. 历史路径
  3. 同目录扫描
  4. 指定目录扫描
  5. 内容指纹匹配（MD5 → size+duration 近似）
卖点："你的工程永远不会丢素材。"
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from yroll.core.models import Asset


def _md5(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def resolve(asset: Asset, search_dirs: list[str | Path] | None = None) -> Path | None:
    """按指纹找回素材文件，找到则更新 asset.path。找不到返回 None。"""
    ident = asset.identity

    # 1. 原路径
    p = Path(asset.path)
    if p.exists() and _matches(p, ident):
        return p

    candidates: list[Path] = []
    # 2. 原目录 + 3. 用户指定目录（先做便宜的全盘候选收集，再按指纹精确匹配）
    dirs = [p.parent, *(Path(d) for d in (search_dirs or []))]
    for d in dirs:
        if not d.is_dir():
            continue
        for f in d.rglob("*"):
            if f.is_file() and f.suffix.lower() == p.suffix.lower():
                candidates.append(f)

    # 4. size 粗筛 → 5. MD5 精确
    for f in candidates:
        if f.stat().st_size == ident.size_bytes and _md5(f) == ident.md5:
            asset.path = str(f)
            return f
    return None


def _matches(path: Path, ident) -> bool:
    try:
        return path.stat().st_size == ident.size_bytes
    except OSError:
        return False
