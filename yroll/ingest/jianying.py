"""剪映专业版草稿导入（蓝图 §4.1：AI Video Production Compatibility Layer）。

剪映草稿 = 目录 + draft_content.json（轨道/片段/素材引用）。
我们解析它的 tracks/materials，映射成 YROLL Manifest：
  - materials.videos → Asset（按路径登记，md5 指纹）
  - tracks[].segments → Clip（source_timerange → source_range，target_timerange → timeline_range）
  - speed → clip.speed

V0 支持：视频/音频轨、裁剪、变速。不支持的（特效/关键帧/转场）记 context.skipped。

用法：
    from yroll.ingest.jianying import import_jianying_draft
    stats = import_jianying_draft(cmd, "D:/.../草稿目录")
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from yroll.core.commands import CommandError, CommandLayer
from yroll.core.manifest import TrackKind
from yroll.core.models import Asset, AssetIdentity, AssetType

# 剪映时间单位是微秒
_US = 1_000_000


def _us(v) -> float:
    return (v or 0) / _US


def import_jianying_draft(cmd: CommandLayer, draft_dir: str | Path) -> dict:
    """导入剪映草稿到当前工程。返回统计信息。"""
    draft_dir = Path(draft_dir)
    draft_file = draft_dir / "draft_content.json"
    if not draft_file.exists():
        raise CommandError(f"不是剪映草稿目录（缺 draft_content.json）: {draft_dir}")

    draft = json.loads(draft_file.read_text(encoding="utf-8"))
    materials = draft.get("materials", {})
    videos = {m["id"]: m for m in materials.get("videos", [])}

    project = cmd.core.project
    stats = {"assets": 0, "clips": 0, "tracks": 0, "skipped": 0}

    def register_asset(mat: dict) -> Asset | None:
        path = mat.get("path", "")
        if not path or not Path(path).exists():
            stats["skipped"] += 1
            return None
        # 指纹去重（同素材复用）
        p = Path(path)
        md5 = hashlib.md5(p.read_bytes()).hexdigest()
        existing = next((a for a in project.assets
                         if a.identity.md5 == md5), None)
        if existing:
            return existing
        asset = Asset(
            asset_id=f"a{uuid.uuid4().hex[:6]}",
            type=AssetType.VIDEO if mat.get("type") == "video" else AssetType.AUDIO,
            path=str(p),
            identity=AssetIdentity(
                md5=md5, size_bytes=p.stat().st_size,
                duration_sec=_us(mat.get("duration")) or None,
                width=(mat.get("width") or None), height=(mat.get("height") or None)),
        )
        project.assets.append(asset)
        stats["assets"] += 1
        return asset

    for i, track in enumerate(draft.get("tracks", [])):
        ttype = track.get("type")
        kind = TrackKind.VIDEO if ttype == "video" else \
            TrackKind.AUDIO if ttype == "audio" else None
        if kind is None:
            stats["skipped"] += 1
            continue  # 文本/特效轨 V0 跳过
        tid = f"jy{i + 1}"
        cmd.add_track(kind, tid)
        stats["tracks"] += 1
        for seg in track.get("segments", []):
            mat = videos.get(seg.get("material_id"))
            if mat is None:
                stats["skipped"] += 1
                continue
            asset = register_asset(mat)
            if asset is None:
                continue
            src = seg.get("source_timerange", {})
            tgt = seg.get("target_timerange", {})
            src_start = _us(src.get("start"))
            src_end = src_start + _us(src.get("duration"))  # 剪映给的是 start+duration
            tl_start = _us(tgt.get("start"))
            # 幂等：相同 (asset, track, src_range, tl_start) 已存在则跳过
            already = next(
                (c for c in project.clips.values()
                 if c.track_id == tid and c.asset_id == asset.asset_id
                 and abs(c.source_range.start - src_start) < 1e-6
                 and abs(c.source_range.end - src_end) < 1e-6
                 and abs(c.timeline_range.start - tl_start) < 1e-6),
                None,
            )
            if already is not None:
                stats["skipped"] += 1
                continue
            clip = cmd.add_clip(
                asset.asset_id, src_start, src_end,
                timeline_start=tl_start, track_id=tid,
                why="剪映草稿导入")
            speed = (seg.get("speed") or {}).get("speed", 1.0)
            if speed and speed != 1.0:
                cmd.set_speed(clip.clip_id, float(speed), why="剪映草稿导入（变速）")
            stats["clips"] += 1

    cmd.core.save_state()
    return stats
