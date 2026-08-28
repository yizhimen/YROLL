"""Publish Package（蓝图 §7 导出与发布 / 工程优先级 Export Report）。

一次导出 = 完整发布包：
  1. 成片 video.mp4（走完整渲染管线，可选烧字幕）
  2. 封面 cover.jpg（首 clip 首帧）
  3. 字幕 subtitles.srt（始终输出；烧录与软字幕互不影响）
  4. 元数据 metadata.json（标题/描述/标签/平台）
  5. 导出报告 report.json（工程快照：版本/操作统计/成本/路由分布/参数）

导出报告是这个产品的信任状：这个片子的每一次修改都有账可查。
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from yroll.core.project import ProjectCore
from yroll.core.render import render_preview


def _write_srt_for_export(core: ProjectCore, out_path: Path) -> int:
    """写 SRT 字幕文件（即使不烧录也输出，供平台上传用）。"""
    text_clips = [c for tid in core.project.timeline.tracks
                  if tid.kind.value == "text"
                  for cid in tid.clip_ids
                  if (c := core.project.clips.get(cid)) and c.context.get("text", "").strip()]
    text_clips.sort(key=lambda c: c.timeline_range.start)
    if not text_clips:
        out_path.write_text("", encoding="utf-8")
        return 0

    def fmt(t: float) -> str:
        ms = int(round(t * 1000))
        h, ms = divmod(ms, 3_600_000)
        m, ms = divmod(ms, 60_000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, c in enumerate(text_clips, 1):
        s = c.timeline_range.start
        e = c.timeline_range.end
        text = c.context["text"].replace("\n", " ")
        lines.append(f"{i}\n{fmt(s)} --> {fmt(e)}\n{text}\n")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return len(text_clips)


def export_package(core: ProjectCore, out_dir: str | Path,
                   width: int = 1080, fps: int = 30,
                   burn_subtitles: bool = False,
                   title: str = "", description: str = "",
                   tags: list[str] | None = None,
                   platform: str = "",
                   cover_offset_sec: float = 0.5,
                   on_step=None) -> dict:
    """导出发布包到 out_dir。返回 report 内容。

    新增参数（v0.2）：
      - title / description / tags：平台发布元数据
      - platform：发布平台（douyin/xiaohongshu/...）
      - cover_offset_sec：封面从哪个时间点取（默认 0.5s）
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tags = tags or []

    # 0. 把元数据写入 Project.publishing（让历史可追溯）
    core.project.publishing.title = title or core.project.publishing.title
    core.project.publishing.description = (
        description or core.project.publishing.description)
    if tags:
        core.project.publishing.tags = tags
    if platform:
        core.project.publishing.platform_copy[platform] = description or title

    # 1. 成片
    video = render_preview(core, out_dir / "video.mp4", width=width, fps=fps,
                           burn_subtitles=burn_subtitles, on_step=on_step)

    # 2. 封面帧（视频首帧，可指定偏移）
    cover = out_dir / "cover.jpg"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{cover_offset_sec:.3f}",
         "-i", str(video), "-frames:v", "1", "-q:v", "3", str(cover)],
        check=True, capture_output=True)

    # 3. 字幕 SRT（始终输出；不烧录也能给平台上传）
    srt_count = _write_srt_for_export(core, out_dir / "subtitles.srt")

    # 4. 元数据 metadata.json
    metadata = {
        "title": title,
        "description": description,
        "tags": tags,
        "platform": platform,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    core.save_state()

    # 5. 导出报告
    ops = core.operations()
    versions = core.versions()
    by_who: dict[str, int] = {}
    by_tool: dict[str, int] = {}
    cost_total = 0.0
    for o in ops:
        who = o.who.value if hasattr(o.who, "value") else str(o.who)
        by_who[who] = by_who.get(who, 0) + 1
        tool = o.tool or o.type
        by_tool[tool] = by_tool.get(tool, 0) + 1
        cost_total += o.cost or 0.0

    n_clips = len(core.project.clips)
    duration = max((c.timeline_range.end
                    for c in core.project.clips.values()), default=0.0)
    report = {
        "project": core.project.name,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "files": {
            "video": "video.mp4",
            "cover": "cover.jpg",
            "subtitles": "subtitles.srt" if srt_count else None,
            "metadata": "metadata.json",
            "report": "report.json",
        },
        "spec": {
            "width": width, "fps": fps,
            "burn_subtitles": burn_subtitles,
            "duration_sec": round(duration, 2),
            "platform": platform,
        },
        "publishing": {
            "title": title,
            "description": description,
            "tags": tags,
            "subtitle_count": srt_count,
        },
        "content": {
            "clips": n_clips,
            "tracks": len(core.project.timeline.tracks),
            "assets": len(core.project.assets),
            "generated_assets": sum(
                1 for a in core.project.assets
                if getattr(a.origin, "value", a.origin) == "generated"),
        },
        "history": {
            "operations": len(ops),
            "versions": len(versions),
            "by_who": by_who,
            "by_tool": by_tool,
        },
        "cost": {
            "total": round(cost_total, 2),
            "currency": "CNY",
            "note": "L0/L1 免费；L2/L3 按 Solution 标价累计",
        },
    }
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["path"] = str(out_dir)
    return report
