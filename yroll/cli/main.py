"""yroll ingest 管线：素材目录 → Project Memory。

Stage 0 媒体扫描（ffprobe，成本 0）
Stage 1 镜头切分（PySceneDetect）
Stage 2 关键帧抽取（每 Shot 首/中/尾）
Stage 2.5 ASR 转写（faster-whisper 本地）
Stage 3.5 关键帧视觉描述（需 YROLL_VISION_MODEL，可选）
Stage 4 故事线建议（需 YROLL_TEXT_MODEL，可选）

用法：
    python -m yroll.cli.main ingest <素材目录> --name <项目名> [--goal "目标"]
                                 [--no-asr] [--whisper-model small]
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _load_dotenv() -> None:
    """加载项目根目录 .env（不覆盖已有环境变量）。"""
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_dotenv()

from yroll.core.models import AssetType, ProjectMemory
from yroll.core.store import project_dir, save
from yroll.ingest.asr import transcribe
from yroll.ingest.director import caption_keyframes, suggest_story
from yroll.ingest.scanner import has_audio_stream, scan_dir
from yroll.ingest.shots import detect_shots, extract_keyframes


def cmd_ingest(args: argparse.Namespace) -> None:
    root = Path(args.source).resolve()
    name = args.name or root.name
    memory = ProjectMemory(project_id=name, name=name, root=str(root))
    kf_dir = project_dir(root, name) / "cache" / "keyframes"

    print(f"== Stage 0: 扫描 {root}")
    t0 = time.time()
    memory.assets = scan_dir(root)
    n_video = sum(1 for a in memory.assets if a.type == AssetType.VIDEO)
    n_image = sum(1 for a in memory.assets if a.type == AssetType.IMAGE)
    print(f"   {len(memory.assets)} 个素材（视频 {n_video} / 图片 {n_image}），{time.time()-t0:.1f}s")

    print("== Stage 1+2: 镜头切分与关键帧")
    t0 = time.time()
    for asset in memory.assets:
        if asset.type != AssetType.VIDEO:
            continue
        shots = detect_shots(asset)
        for shot in shots:
            extract_keyframes(shot, asset.path, kf_dir)
        memory.shots.extend(shots)
        print(f"   {Path(asset.path).name}: {len(shots)} 镜头")
    print(f"   共 {len(memory.shots)} 个镜头，{time.time()-t0:.1f}s")

    if not args.no_asr:
        print(f"== Stage 2.5: ASR 转写（faster-whisper/{args.whisper_model}）")
        t0 = time.time()
        for asset in memory.assets:
            if asset.type not in (AssetType.VIDEO, AssetType.AUDIO):
                continue
            if not has_audio_stream(asset.path):
                print(f"   {Path(asset.path).name}: 无音轨，跳过")
                continue
            try:
                segs = transcribe(asset.path, model_size=args.whisper_model)
                if segs:
                    memory.transcripts[asset.asset_id] = segs
                    print(f"   {Path(asset.path).name}: {len(segs)} 段")
            except Exception as e:
                print(f"   {Path(asset.path).name}: 转写失败 {e}")
        print(f"   ASR 完成，{time.time()-t0:.1f}s")

    print("== Stage 3.5/4: LLM 理解（可选，需 API 配置）")
    cost1 = caption_keyframes(memory)
    print(f"   关键帧描述: {cost1}")
    if not args.no_story:
        cost2 = suggest_story(memory, goal=args.goal or "")
        print(f"   故事线建议: {cost2}")

    out = save(memory)
    total_tokens = sum(c.get("prompt_tokens", 0) + c.get("completion_tokens", 0) for c in memory.costs)
    print(f"\n✓ Project Memory 已保存: {out}")
    print(f"  素材 {len(memory.assets)} / 镜头 {len(memory.shots)} / "
          f"转写 {len(memory.transcripts)} 段资产 / 故事场景 {len(memory.story)}")
    print(f"  LLM token 消耗: {total_tokens}")


def cmd_story(args: argparse.Namespace) -> None:
    """基于已有 Project Memory 跑 Stage 3.5/4（不重新扫描素材）。"""
    from yroll.core.store import load

    memory = load(args.source, args.name)
    print(f"已加载项目 {memory.name}：素材 {len(memory.assets)} / 镜头 {len(memory.shots)}")

    if not args.no_caption:
        print("== Stage 3.5: 关键帧视觉描述")
        print("  ", caption_keyframes(memory, max_shots=args.max_shots))
    print("== Stage 4: 故事线建议")
    print("  ", suggest_story(memory, goal=args.goal or ""))
    save(memory)
    print(f"\n✓ 故事场景 {len(memory.story)} 个：")
    for i, s in enumerate(memory.story):
        print(f"  {i+1}. [{s.role or '-'}] {s.title}（{len(s.shot_ids)} 镜头）{s.narrative[:60]}")


def cmd_build_timeline(args: argparse.Namespace) -> None:
    """按 Stage 4 故事线，用 Command Layer 搭建 Timeline（全部操作落 Operation Log）。"""
    from yroll.core.commands import CommandLayer
    from yroll.core.manifest import Actor
    from yroll.core.project import ProjectCore
    from yroll.core.store import load

    memory = load(args.source, args.name)
    if not memory.story:
        raise SystemExit("该项目还没有故事线，请先运行: yroll story ...")

    project_path = Path(args.project) / (args.project_name or memory.name)
    if (project_path / "current.json").exists():
        core = ProjectCore.open(project_path)
    else:
        core = ProjectCore.create(args.project, args.project_name or memory.name,
                                  intent={"goal": args.goal or ""})
    core.project.assets = memory.assets  # 导入素材清单（含 Asset Identity 指纹）
    # 记忆指针：chat/理解上下文可从源头 Project Memory 取转写/镜头语义
    core.project.extensions["memory"] = {"root": str(root), "name": name}
    core.save_state()
    cmd = CommandLayer(core, who=Actor.AI)  # AI 初剪，与人操作走同一 Command API

    shots_by_id = {s.shot_id: s for s in memory.shots}
    cursor = 0.0
    placed = 0
    for scene in memory.story:
        for sid in scene.shot_ids:
            shot = shots_by_id.get(sid)
            if shot is None or shot.end - shot.start <= 0.05:
                continue
            cmd.add_clip(shot.asset_id, shot.start, shot.end,
                         timeline_start=cursor, track_id="v1",
                         why=f"[{scene.role}] {scene.title}")
            cursor += shot.end - shot.start
            placed += 1

    core.commit(note="AI 初剪：按故事线搭建 Timeline")
    print(f"✓ Timeline 已搭建: {project_path}")
    print(f"  场景 {len(memory.story)} / 上轨镜头 {placed} / 总时长 {cursor:.1f}s / "
          f"操作 {len(core.operations())} 条（全部可追溯）")


def cmd_render(args: argparse.Namespace) -> None:
    """按当前 Timeline 状态渲染预览视频。"""
    from yroll.core.project import ProjectCore
    from yroll.core.render import render_preview

    core = ProjectCore.open(args.project)
    out = render_preview(core, args.out or (Path(args.project) / "preview.mp4"))
    print(f"✓ 预览已渲染: {out}")


def cmd_reality_test(args: argparse.Namespace) -> None:
    """End-to-end reality test (v0.2 spec §36): Test A-G using real
    synthetic video files. Exits 0 on PASS, 1 on FAIL.
    """
    import tempfile
    import sys
    from pathlib import Path

    import pytest

    code = pytest.main([
        "tests/test_reality_v02.py",
        "-v", "--tb=short",
        "-x",  # stop on first failure
    ])
    sys.exit(0 if code == 0 else 1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="yroll")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reality-test",
                       help="端到端 Reality Test v0.2 (Test A-G)")
    r.set_defaults(func=cmd_reality_test)
    p = sub.add_parser("ingest", help="扫描并理解素材目录")
    p.add_argument("source")
    p.add_argument("--name")
    p.add_argument("--goal", default="")
    p.add_argument("--no-asr", action="store_true")
    p.add_argument("--no-story", action="store_true")
    p.add_argument("--whisper-model", default="small")
    p.set_defaults(func=cmd_ingest)

    s = sub.add_parser("story", help="基于已有项目记忆生成故事线（需 LLM 配置）")
    s.add_argument("source", help="素材根目录（含 .yroll/<name>/memory.json）")
    s.add_argument("--name", required=True)
    s.add_argument("--goal", default="")
    s.add_argument("--no-caption", action="store_true")
    s.add_argument("--max-shots", type=int, default=60)
    s.set_defaults(func=cmd_story)

    b = sub.add_parser("build-timeline", help="按故事线搭建 Timeline（AI 初剪）")
    b.add_argument("source", help="素材根目录（含 .yroll/<name>/memory.json）")
    b.add_argument("--name", required=True, help="记忆项目名")
    b.add_argument("--project", default="projects", help="工程输出根目录")
    b.add_argument("--project-name", default=None)
    b.add_argument("--goal", default="")
    b.set_defaults(func=cmd_build_timeline)

    r = sub.add_parser("render", help="按 Timeline 渲染预览视频")
    r.add_argument("project", help="工程目录（含 current.json）")
    r.add_argument("--out", default=None)
    r.set_defaults(func=cmd_render)

    v = sub.add_parser("serve", help="启动 YROLL Server（Command Layer over HTTP）")
    v.add_argument("project", help="工程目录（含 current.json）")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8765)
    v.set_defaults(func=lambda a: __import__("yroll.server.app", fromlist=["serve"]).serve(
        a.project, host=a.host, port=a.port))

    m = sub.add_parser("mcp", help="启动 MCP Server（stdio，供外部 Agent 接入）")
    m.add_argument("project", help="工程目录（含 current.json）")
    m.set_defaults(func=lambda a: __import__(
        "yroll.server.mcp_server", fromlist=["McpServer"]).McpServer(a.project).serve_stdio())

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
