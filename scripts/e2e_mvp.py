"""MVP 验证脚本（蓝图 §11 成功标准）：
真实案例「10 个手机视频 → 30 秒抖音视频」全流程计时，
对照组是"剪映+ChatGPT+可灵+人工切换"，快 5 倍则项目成立。

手动触发（真实素材+真实 LLM 调用，不进 CI）：
    .venv/Scripts/python scripts/e2e_mvp.py <素材目录> [--name mvp-demo]

输出各阶段耗时 + 总耗时，打印对照估算。
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("media_dir", help="素材目录（手机视频）")
    ap.add_argument("--name", default="mvp-demo")
    ap.add_argument("--goal", default="30 秒抖音产品视频")
    args = ap.parse_args()

    t0 = time.perf_counter()
    lap = t0

    def mark(stage: str) -> None:
        nonlocal lap
        now = time.perf_counter()
        print(f"[{now - lap:7.1f}s] {stage}")
        lap = now

    # 1. 理解管线（扫描/镜头/ASR/故事线）
    from yroll.cli.main import cmd_ingest

    cmd_ingest(argparse.Namespace(
        media_dir=args.media_dir, name=args.name, goal=args.goal,
        no_asr=False, whisper_model="small"))
    mark("理解管线（扫描/镜头/ASR）")

    # 2. AI 初剪（故事线 → Timeline）
    from yroll.cli.main import cmd_build_timeline

    proj_dir = Path(args.media_dir) / ".yroll" / args.name
    cmd_build_timeline(argparse.Namespace(project=str(proj_dir)))
    mark("AI 初剪 Timeline")

    # 3. 自动字幕
    from yroll.core.commands import CommandLayer
    from yroll.core.manifest import Actor
    from yroll.core.project import ProjectCore

    core = ProjectCore.open(proj_dir)
    cmd = CommandLayer(core, who=Actor.AI)
    try:
        op = cmd.generate_subtitles(why="MVP 验证")
        core.save_state()
        mark(f"自动字幕（{op.after['count']} 条）")
    except Exception as e:
        mark(f"自动字幕跳过（{e}）")

    # 4. 发布包导出
    from yroll.core.publish import export_package

    report = export_package(core, proj_dir / "export")
    mark("发布包导出（成片+封面+报告）")

    total = time.perf_counter() - t0
    manual_est = 30 * 60  # 人工+多工具切换的保守估计 30 分钟
    print("=" * 50)
    print(f"YROLL 总耗时：{total / 60:.1f} 分钟")
    print(f"人工对照估算：~{manual_est / 60:.0f} 分钟（剪映+ChatGPT+可灵+人工切换）")
    print(f"加速比：{manual_est / max(total, 1):.1f}x"
          f"（{'✅ 达成 5x 标准' if manual_est / max(total, 1) >= 5 else '❌ 未达 5x'}）")
    print(f"报告：{report['path']}")


if __name__ == "__main__":
    main()
