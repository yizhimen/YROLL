"""Problem→Solution Engine —— 产品灵魂（蓝图 §3.5/§3.7）。

Harness 接受的不是"生成视频"，而是 Problem：
    AnalyzeProblem → RecommendSolutions（带成本/风险，默认最低成本）→ Execute → 验证

V0 为规则版 Solution Matrix（产品知识库，版本化，后续喂给 Harness 做路由依据）。
L0 路由立即映射到 Command Layer 真实执行；L1+ 记录为 Pending（等 AI 能力接入）。

"不问 AI 能不能做，而问解决这个问题最低成本的方法是什么。"
"""

from __future__ import annotations

import uuid

from yroll.core.commands import CommandError, CommandLayer
from yroll.core.manifest import (
    Problem,
    ProblemCategory,
    ProblemSource,
    Project,
    Region,
    Solution,
    SolutionRoute,
    TimeRange,
)

# ---------- Problem-Solution Matrix v0.1（版本化产品知识库） ----------
# 每个 entry：category → 候选方案（route/tool/参数模板/成本估算/风险）
# 排序即推荐顺序（默认最低成本优先 = 列表第一个）
MATRIX: dict[ProblemCategory, list[dict]] = {
    ProblemCategory.TEMPORAL: [
        {"route": SolutionRoute.L0_TRANSFORM, "tool": "video.trim",
         "label": "裁掉这段", "cost": 0.0, "duration_ms": 50, "risk": "low"},
        {"route": SolutionRoute.L0_TRANSFORM, "tool": "video.speed",
         "label": "加速跳过", "cost": 0.0, "duration_ms": 50, "risk": "low",
         "params": {"speed": 1.5}},
        {"route": SolutionRoute.L1_LOCAL_AI, "tool": "audio.silence_remove",
         "label": "本地 AI 识别并删除停顿/气口", "cost": 0.0, "duration_ms": 30000, "risk": "medium"},
        {"route": SolutionRoute.L3_REGENERATE, "tool": "video.generate",
         "label": "重新生成该镜头", "cost": 1.20, "duration_ms": 120000, "risk": "high"},
    ],
    ProblemCategory.AUDIO: [
        {"route": SolutionRoute.L0_TRANSFORM, "tool": "audio.gain",
         "label": "调整音量", "cost": 0.0, "duration_ms": 50, "risk": "low"},
        {"route": SolutionRoute.L1_LOCAL_AI, "tool": "audio.denoise",
         "label": "本地降噪", "cost": 0.0, "duration_ms": 20000, "risk": "low"},
        {"route": SolutionRoute.L2_CLOUD_AI, "tool": "voice.clone_replace",
         "label": "语音克隆重配该句", "cost": 0.05, "duration_ms": 15000, "risk": "medium"},
    ],
    ProblemCategory.TEXT: [
        {"route": SolutionRoute.L0_TRANSFORM, "tool": "text.correct",
         "label": "直接改字幕文字", "cost": 0.0, "duration_ms": 50, "risk": "low"},
        {"route": SolutionRoute.L0_TRANSFORM, "tool": "subtitle.retime",
         "label": "重新对齐字幕时间", "cost": 0.0, "duration_ms": 100, "risk": "low"},
        {"route": SolutionRoute.L1_LOCAL_AI, "tool": "video.inpaint",
         "label": "局部重绘去除烧录字幕/水印", "cost": 0.0, "duration_ms": 40000, "risk": "medium"},
    ],
    ProblemCategory.VISUAL: [
        {"route": SolutionRoute.L0_TRANSFORM, "tool": "video.adjust",
         "label": "调亮度/对比度（带羽化）", "cost": 0.0, "duration_ms": 100, "risk": "low",
         "params": {"brightness": 0.1}},
        {"route": SolutionRoute.L1_LOCAL_AI, "tool": "video.stabilize",
         "label": "本地稳定/降噪/超分", "cost": 0.0, "duration_ms": 60000, "risk": "low"},
        {"route": SolutionRoute.L2_CLOUD_AI, "tool": "video.v2v",
         "label": "V2V 风格统一", "cost": 0.60, "duration_ms": 90000, "risk": "medium"},
    ],
    ProblemCategory.SPATIAL_OBJECT: [
        {"route": SolutionRoute.L0_TRANSFORM, "tool": "object.transform",
         "label": "直接变换（缩放/移动/旋转浮动层）", "cost": 0.0, "duration_ms": 100, "risk": "low"},
        {"route": SolutionRoute.L1_LOCAL_AI, "tool": "object.remove",
         "label": "本地 AI 去除对象（inpaint）", "cost": 0.0, "duration_ms": 40000, "risk": "medium"},
        {"route": SolutionRoute.L2_CLOUD_AI, "tool": "video.inpaint",
         "label": "云端重绘该区域", "cost": 0.18, "duration_ms": 40000, "risk": "medium"},
        {"route": SolutionRoute.L3_REGENERATE, "tool": "video.generate",
         "label": "重新生成该镜头", "cost": 1.20, "duration_ms": 120000, "risk": "high"},
    ],
    ProblemCategory.SEMANTIC: [
        {"route": SolutionRoute.L0_TRANSFORM, "tool": "timeline.reorder",
         "label": "调整顺序/节奏", "cost": 0.0, "duration_ms": 100, "risk": "low"},
        {"route": SolutionRoute.L3_REGENERATE, "tool": "video.generate",
         "label": "重新生成更贴主题的镜头", "cost": 1.20, "duration_ms": 120000, "risk": "high"},
    ],
    ProblemCategory.CONSISTENCY: [
        {"route": SolutionRoute.L0_TRANSFORM, "tool": "audio.normalize",
         "label": "统一响度/音量", "cost": 0.0, "duration_ms": 200, "risk": "low"},
        {"route": SolutionRoute.L1_LOCAL_AI, "tool": "video.color_match",
         "label": "本地色彩匹配", "cost": 0.0, "duration_ms": 30000, "risk": "low"},
        {"route": SolutionRoute.L2_CLOUD_AI, "tool": "video.v2v",
         "label": "V2V 统一风格", "cost": 0.60, "duration_ms": 90000, "risk": "medium"},
    ],
}


def _execute_generate(cmd: CommandLayer, solution: Solution,
                      problem: Problem, clip_id: str) -> dict:
    """L3 video.generate：云端生成新镜头 → generated/ 落盘 → 登记 Asset(origin=generated)
    → 作为新 clip 追加到问题 clip 之后（非破坏，人在时间轴上对比后自己决定替换与否）。"""
    import uuid

    from yroll.core.models import Asset, AssetIdentity, AssetOrigin, AssetType
    from yroll.tools.cloud_gen import generate_shot

    project = cmd.core.project
    clip = project.clips.get(clip_id)
    if clip is None:
        raise CommandError(f"clip 不存在: {clip_id}")

    prompt = solution.params.get("prompt") or (
        f"重新生成一个镜头，解决：{problem.description}")
    dest = cmd.core.path / "generated" / f"gen-{uuid.uuid4().hex[:8]}.mp4"
    dest.parent.mkdir(exist_ok=True)
    out = generate_shot(prompt, dest)

    asset = Asset(
        asset_id=f"a{uuid.uuid4().hex[:6]}",
        type=AssetType.VIDEO, origin=AssetOrigin.GENERATED,
        path=str(out),
        identity=AssetIdentity(
            md5=_md5(out), size_bytes=out.stat().st_size,
            duration_sec=clip.source_range.end - clip.source_range.start),
    )
    project.assets.append(asset)

    # 生成片段追加到问题 clip 之后（时长以问题 clip 源时长为准，渲染时自适配）
    dur = asset.identity.duration_sec or 6.0
    new_clip = cmd.add_clip(
        asset.asset_id, 0.0, dur,
        timeline_start=clip.timeline_range.end,
        track_id=clip.track_id,
        why=f"L3 生成镜头（问题[{problem.problem_id}]）：{problem.description}")
    cmd.core.save_state()

    solution.selected = True
    return {"status": "applied", "clip_id": new_clip.clip_id,
            "asset_id": asset.asset_id, "prompt": prompt,
            "solution": solution.model_dump()}


def _md5(path) -> str:
    import hashlib

    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def report_problem(project: Project, description: str, category: ProblemCategory,
                   target_clip: str | None = None,
                   time_range: TimeRange | None = None,
                   region: Region | None = None,
                   source: ProblemSource = ProblemSource.HUMAN) -> Problem:
    """登记一个 Problem（一级对象）。"""
    p = Problem(
        problem_id=f"p{uuid.uuid4().hex[:6]}",
        target_clip=target_clip,
        time_range=time_range,
        region=region,
        category=category,
        description=description,
        source=source,
    )
    project.problems.append(p)
    return p


def recommend(project: Project, problem: Problem) -> list[Solution]:
    """按 Matrix 给候选方案：默认最低成本优先（列表序即推荐序）。"""
    templates = MATRIX.get(problem.category, [])
    solutions = []
    for t in templates:
        s = Solution(
            solution_id=f"s{uuid.uuid4().hex[:6]}",
            problem_id=problem.problem_id,
            route=t["route"],
            tool=t["tool"],
            params=dict(t.get("params", {})),
            cost=t["cost"],
            duration_ms=t["duration_ms"],
            risk=t["risk"],
        )
        solutions.append(s)
    project.solutions.extend(solutions)
    return solutions


def execute(cmd: CommandLayer, solution: Solution, problem: Problem) -> dict:
    """执行选中的 Solution。

    L0：映射到 Command Layer 参数级操作。
    L1（已接入的本地确定性工具）：真实执行，如 audio.silence_remove。
    其余 L1+：返回 pending（接口预留，Harness 阶段接 Tool Registry）。
    """
    clip_id = problem.target_clip
    if clip_id is None:
        raise CommandError("该方案需要目标 clip")

    # L1 已接入的本地能力
    if solution.route == SolutionRoute.L1_LOCAL_AI and solution.tool == "audio.silence_remove":
        why = f"解决问题[{problem.problem_id}]：{problem.description}"
        op = cmd.remove_silence(clip_id, why=why)
        solution.selected = True
        return {"status": "applied", "operation_id": op.operation_id,
                "detail": op.after, "solution": solution.model_dump()}

    if solution.route == SolutionRoute.L1_LOCAL_AI and solution.tool == "audio.denoise":
        why = f"解决问题[{problem.problem_id}]：{problem.description}"
        op = cmd.denoise_clip(clip_id, why=why)
        solution.selected = True
        return {"status": "applied", "operation_id": op.operation_id,
                "solution": solution.model_dump()}

    if solution.route == SolutionRoute.L1_LOCAL_AI and solution.tool == "video.inpaint":
        # 局部去除（烧录字幕/水印）：走 delogo 调整图层，需要 region
        if problem.region is None:
            raise CommandError("局部重绘需要框选区域（region）")
        why = f"解决问题[{problem.problem_id}]：{problem.description}"
        op = cmd.delogo_clip(clip_id, problem.region, why=why)
        solution.selected = True
        return {"status": "applied", "operation_id": op.operation_id,
                "solution": solution.model_dump()}

    # L2 已接入的云端能力：TTS 语音重配（需要方案里带正确台词）
    if solution.route == SolutionRoute.L2_CLOUD_AI and solution.tool == "voice.clone_replace":
        text = solution.params.get("text")
        if not text:
            return {"status": "pending",
                    "message": "该方案需要正确台词文本（params.text），请在执行时提供",
                    "solution": solution.model_dump()}
        why = f"解决问题[{problem.problem_id}]：{problem.description}"
        op = cmd.replace_clip_voice(clip_id, text, why=why)
        solution.selected = True
        return {"status": "applied", "operation_id": op.operation_id,
                "solution": solution.model_dump()}

    # L3 已接入的云端生成：生成新镜头（非破坏——作为新 clip 跟在问题 clip 后面，人决定换不换）
    if solution.route == SolutionRoute.L3_REGENERATE and solution.tool == "video.generate":
        return _execute_generate(cmd, solution, problem, clip_id)

    if solution.route != SolutionRoute.L0_TRANSFORM:
        return {
            "status": "pending",
            "message": f"{solution.route} 能力将在 Tool Registry 阶段接入（接口已预留）",
            "solution": solution.model_dump(),
        }

    tool = solution.tool
    why = f"解决问题[{problem.problem_id}]：{problem.description}"
    if tool == "video.trim" and problem.time_range:
        # 裁掉问题时间段：在时间范围起点切分
        clip = cmd.core.project.clips[clip_id]
        sr = clip.source_range
        tr = problem.time_range
        # timeline 时间 → 源时间
        ratio = (tr.start - clip.timeline_range.start) / max(
            clip.timeline_range.end - clip.timeline_range.start, 1e-6)
        at = sr.start + (sr.end - sr.start) * ratio
        cmd.split_clip(clip_id, at, why=why)
        op = cmd.core.operations()[-1]
    elif tool == "video.speed":
        op = cmd.set_speed(clip_id, solution.params.get("speed", 1.5), why=why)
    elif tool == "audio.gain":
        op = cmd.set_volume(clip_id, solution.params.get("volume", 1.3), why=why)
    elif tool == "video.adjust":
        op = cmd.add_adjustment(clip_id, "color", solution.params,
                                time_range=problem.time_range,
                                region=problem.region, why=why)
    elif tool == "object.transform":
        op = cmd.add_adjustment(clip_id, "object_transform", solution.params,
                                time_range=problem.time_range,
                                region=problem.region, why=why)
    else:
        raise CommandError(f"L0 工具未实现: {tool}")

    solution.selected = True
    return {"status": "applied", "operation_id": op.operation_id,
            "solution": solution.model_dump()}
