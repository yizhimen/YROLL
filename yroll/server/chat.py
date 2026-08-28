"""AI 聊天编辑：用户意图 → LLM → 结构化动作 → Command Layer 执行。

MVP 决策：不用 tool-calling API（各家兼容性参差），
让 LLM 输出 JSON {"reply": ..., "actions": [...]}，服务端解析并执行。
actions 里的每个动作都走 CommandLayer —— 与人手操作同一套 API、同一个 Operation Log。

权限（蓝图 §2.4）：低风险操作（trim/speed/volume）直接执行；
删除/批量等中高风险动作，MVP 先也执行但 why 字段记录 AI 意图，
正式版接 Plan→Preview→Apply 协议。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from yroll.core.commands import CommandError, CommandLayer
from yroll.core.manifest import Actor, Project
from yroll.harness.skills import (
    inject_prompt,
    load_skills,
    select_skills,
    select_skills_llm,
)

_skills_cache: list | None = None


def build_system(message: str) -> str:
    """按需组装 system prompt：基础协议 + 选中的领域 Skill（按需加载，不全量塞入）。
    路由策略由 YROLL_SKILL_ROUTER 控制：llm（默认，语义路由）/ bigram（关键词兜底）。"""
    global _skills_cache
    if _skills_cache is None:
        _skills_cache = load_skills()
    if os.environ.get("YROLL_SKILL_ROUTER", "llm") == "llm" \
            and os.environ.get("YROLL_API_KEY"):
        picked = select_skills_llm(message, _skills_cache, client=_client())
    else:
        picked = select_skills(message, _skills_cache)
    return inject_prompt(SYSTEM, picked)

SYSTEM = """你是 YROLL AI 视频工作站的剪辑助手。你和人操作同一个视频工程。
你可以执行以下动作（每个动作都会真实修改工程并留下日志）：

- trim: {"op":"trim","clip_id":"...","new_source_start":秒,"new_source_end":秒}
- split: {"op":"split","clip_id":"...","at_source_time":秒}
- move: {"op":"move","clip_id":"...","new_timeline_start":秒}
- speed: {"op":"speed","clip_id":"...","speed":倍率}
- volume: {"op":"volume","clip_id":"...","volume":0-2}
- remove: {"op":"remove","clip_id":"..."}
- silence_remove: {"op":"silence_remove","clip_id":"..."}（去停顿/气口）
- denoise: {"op":"denoise","clip_id":"...","strength":12}（降噪，非破坏性）
- delogo: {"op":"delogo","clip_id":"...","region":{"x":0,"y":0,"w":0.2,"h":0.1}}（去水印，region 是归一化坐标 0-1，非破坏性）
- fade: {"op":"fade","clip_id":"...","fade_in":0.5,"fade_out":0.5}（淡入淡出转场，非破坏性）
- dissolve: {"op":"dissolve","clip_id":"...","duration":0.5}（与前一个 clip 叠化溶解，作用在后一个 clip 上）
- subtitle_edit: {"op":"subtitle_edit","clip_id":"...","text":"新字幕文字"}（改字幕，clip 必须是字幕轨上的）
- add_subtitle: {"op":"add_subtitle","text":"字幕内容","start":秒,"end":秒}（在时间轴加字幕）
- generate_subtitles: {"op":"generate_subtitles"}（从转写自动生成整轨字幕；也可带 clip_id 只对单个 clip）
- voice_replace: {"op":"voice_replace","clip_id":"...","text":"正确的台词"}（TTS 重配这句，原声静音）
- color: {"op":"color","clip_id":"...","params":{"brightness":-0.1,"contrast":1.1,"saturation":1.2,"temperature":5500,"sharpen":0.5}}（画面色彩，参数按需给）
- flip: {"op":"flip","clip_id":"...","horizontal":true}（镜像）
- opacity: {"op":"opacity","clip_id":"...","opacity":0.8}
- crop: {"op":"crop","clip_id":"...","params":{"left":0.1,"top":0,"right":0.1,"bottom":0}}（画面裁剪，四边比例）
- reverse: {"op":"reverse","clip_id":"..."}（倒放）
- transform2d: {"op":"transform2d","clip_id":"...","params":{"scale":0.8,"x":0.1,"y":0,"rotation":0}}（缩放/移动/旋转，模糊背景填充）
- revert: {"op":"revert","operation_id":"op00014"}（撤销一条操作，operation_id 从【最近操作】里选）
- analyze_loudness: {"op":"analyze_loudness","clip_id":"..."}（测量响度，结果会在下一轮返回给你）
- problem: {"op":"problem","clip_id":"...","category":"temporal|audio|text|visual|spatial_object|semantic|consistency","description":"问题描述"}

规则：
1. 只输出 JSON：{"reply":"给人看的回复（中文、简洁）","actions":[...]}
2. 不确定就不做动作，actions 为空数组，在 reply 里向人确认
3. 时间单位都是秒；clip_id 必须从工程上下文里选，不要编造
4. 源时间(source)和时间轴时间(timeline)不同：trim/split 用源时间
5. 当用户说的是"这里有问题/哪里不对/这个不好"等【问题类】意图（而不是明确的修改指令）时，
   用 problem 动作登记问题，系统会自动给出带成本的候选方案，让用户在 Clip Workspace 里选；
   只有用户明确说"直接改/帮我改好"时才直接执行修改动作"""


def _load_transcripts(project: Project) -> dict[str, list[dict]]:
    """从源 Project Memory 取转写（extensions.memory 指针）。
    蓝图：'AI 分析一次，长期使用'——不在 chat 时重新转写。"""
    from yroll.core.transcripts import load_transcripts

    return load_transcripts(project)


def _project_context(project: Project, ops: list | None = None) -> str:
    transcripts = _load_transcripts(project)
    lines = ["【当前工程】"]
    for t in project.timeline.tracks:
        lines.append(f"轨道 {t.track_id}（{t.kind}）：")
        for cid in t.clip_ids:
            c = project.clips.get(cid)
            if not c:
                continue
            label = c.context.get("text") or c.context.get("why") or ""
            line = (
                f"  {cid} | 素材 {c.asset_id} | 源 {c.source_range.start:.1f}-{c.source_range.end:.1f}s"
                f" | 时间轴 {c.timeline_range.start:.1f}-{c.timeline_range.end:.1f}s"
                f" | 速度 {c.speed}x 音量 {c.volume} {label}"
            )
            # 注入该 clip 源区间内的转写文本（AI 看得见"这段在说什么"）
            segs = transcripts.get(c.asset_id, [])
            said = " ".join(
                s["text"] for s in segs
                if s["end"] > c.source_range.start and s["start"] < c.source_range.end
            ).strip()
            if said:
                line += f"\n    说话内容：{said[:120]}"
            lines.append(line)
    # 最近操作（Semantic Undo 的依据：AI 看得见"刚才做了什么"才能撤销）
    if ops:
        lines.append("【最近操作】（可撤销，用 revert 动作）")
        for o in ops[-8:]:
            who = "AI" if o.who == Actor.AI else "人"
            why = f"（{o.why[:30]}）" if o.why else ""
            lines.append(f"  {o.operation_id} | {who} | {o.type} → {o.target} {why}")
    return "\n".join(lines)


def _client() -> OpenAI:
    return OpenAI(
        api_key=os.environ.get("YROLL_API_KEY", ""),
        base_url=os.environ.get("YROLL_BASE_URL", "https://api.openai.com/v1"),
    )


def chat_edit(cmd: CommandLayer, message: str,
              selected_clip: str | None = None, playhead: float | None = None) -> dict[str, Any]:
    """一轮对话编辑。返回 {reply, actions, applied, errors}。"""
    project = cmd.core.project
    ctx = _project_context(project)
    if selected_clip and selected_clip in project.clips:
        ctx += f"\n【用户当前选中】{selected_clip}"
    if playhead is not None:
        ctx += f"\n【播放头位置】{playhead:.1f}s（时间轴时间）"

    resp = _client().chat.completions.create(
        model=os.environ.get("YROLL_TEXT_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"{ctx}\n\n【用户说】{message}"},
        ],
        max_tokens=2000,
    )
    text = resp.choices[0].message.content or ""
    # 去掉 reasoning 模型的 <think> 段，提取 JSON
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    m = re.search(r"\{.*\}", text, re.S)
    reply, actions = "", []
    if m:
        try:
            data = json.loads(m.group())
            reply, actions = data.get("reply", ""), data.get("actions", [])
        except json.JSONDecodeError:
            reply = text
    else:
        reply = text

    applied, errors, problems_reported = [], [], []
    for a in actions:
        try:
            op = _execute(cmd, a)
            applied.append(op)
            if getattr(op, "type", "") == "report_problem":
                prob = next((p for p in cmd.core.project.problems
                             if p.problem_id == op.target), None)
                if prob:
                    sols = [s for s in cmd.core.project.solutions
                            if s.problem_id == prob.problem_id]
                    problems_reported.append({
                        "problem": prob.model_dump(),
                        "solutions": [s.model_dump() for s in sols],
                    })
        except (CommandError, KeyError, TypeError) as e:
            errors.append({"action": a, "error": str(e)})

    return {
        "reply": reply,
        "actions": actions,
        "applied": [op.operation_id for op in applied],
        "errors": errors,
        "problems_reported": problems_reported,
    }


def _execute(cmd: CommandLayer, a: dict) -> Any:
    """把 LLM 的动作翻译成 Command Layer 调用（who=ai，why 记录原始意图）。"""
    op = a["op"]
    why = a.get("why", "AI 对话编辑")
    if op == "trim":
        return cmd.trim_clip(a["clip_id"], a.get("new_source_start"),
                             a.get("new_source_end"), why=why)
    if op == "split":
        left, _ = cmd.split_clip(a["clip_id"], a["at_source_time"], why=why)
        return cmd.core.operations()[-1]
    if op == "move":
        return cmd.move_clip(a["clip_id"], a["new_timeline_start"], why=why)
    if op == "speed":
        return cmd.set_speed(a["clip_id"], a["speed"], why=why)
    if op == "volume":
        return cmd.set_volume(a["clip_id"], a["volume"], why=why)
    if op == "remove":
        return cmd.remove_clip(a["clip_id"], why=why)
    if op == "problem":
        # 问题类意图：登记 Problem + 推荐方案（不直接动手，人做最终判断）
        from yroll.core.manifest import ProblemCategory
        from yroll.core.problems import recommend, report_problem

        p = report_problem(
            cmd.core.project, a["description"],
            ProblemCategory(a.get("category", "temporal")),
            target_clip=a.get("clip_id"),
        )
        sols = recommend(cmd.core.project, p)
        cmd.core.save_state()
        # 记录为一条 Operation（问题登记也是工程事件）
        return cmd._record(
            "report_problem", p.problem_id, {},
            {"description": p.description, "category": p.category.value,
             "solutions": [s.solution_id for s in sols]},
            why=a["description"], tool="ai.report_problem")
    raise CommandError(f"未知动作: {op}")
