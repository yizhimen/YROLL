"""Stage 4：LLM 导演分析（接口层）。

原则（蓝图）：前期主要靠 Stage 0-3 本地理解；Stage 4 只在需要时调用，
且只带"关键帧描述 + 转写 + 用户目标"，不发整个视频。
BYOK：OpenAI 兼容 API（GPT/Gemini/Qwen/DeepSeek/本地模型均可）。

环境变量：
    YROLL_API_KEY      — API key
    YROLL_BASE_URL     — OpenAI 兼容端点（默认 https://api.openai.com/v1）
    YROLL_TEXT_MODEL   — 文本模型名（默认 gpt-4o-mini）
    YROLL_VISION_MODEL — 视觉模型名（可选，配了才做关键帧理解）
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path

from openai import OpenAI

from yroll.core.models import ProjectMemory, SceneSuggestion


def _client() -> OpenAI:
    return OpenAI(
        api_key=os.environ.get("YROLL_API_KEY", "ollama"),
        base_url=os.environ.get("YROLL_BASE_URL", "https://api.openai.com/v1"),
    )


def _b64(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


def caption_keyframes(memory: ProjectMemory, max_shots: int = 60) -> dict:
    """用视觉模型给关键帧写描述（写入 shot.caption）。返回成本记录。"""
    model = os.environ.get("YROLL_VISION_MODEL")
    if not model:
        return {"skipped": "YROLL_VISION_MODEL 未配置，跳过 Stage 3.5 视觉理解"}
    client = _client()
    t0 = time.time()
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    for shot in memory.shots[:max_shots]:
        if not shot.keyframes:
            continue
        content = [
            {"type": "text", "text": "这是同一视频镜头的首/中/尾帧。用一句中文描述这个镜头的画面内容、主体、场景。只输出描述本身。"},
            *[
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64(k)}"}}
                for k in shot.keyframes[:3]
            ],
        ]
        resp = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": content}], max_tokens=150
        )
        shot.caption = (resp.choices[0].message.content or "").strip()
        if resp.usage:
            usage["prompt_tokens"] += resp.usage.prompt_tokens
            usage["completion_tokens"] += resp.usage.completion_tokens
    cost = {
        "stage": "vision_caption", "model": model,
        "duration_sec": round(time.time() - t0, 1), **usage,
    }
    memory.costs.append(cost)
    return cost


def suggest_story(memory: ProjectMemory, goal: str = "") -> dict:
    """基于镜头描述+转写，让 LLM 产出故事线/场景建议。"""
    model = os.environ.get("YROLL_TEXT_MODEL", "gpt-4o-mini")
    client = _client()

    shots_brief = "\n".join(
        f"- [{s.shot_id}] {s.start:.1f}-{s.end:.1f}s (asset {s.asset_id}): {s.caption or '(无描述)'}"
        for s in memory.shots
    )
    transcripts_brief = "\n".join(
        f"- [asset {aid}] " + " ".join(seg.text for seg in segs)[:300]
        for aid, segs in memory.transcripts.items()
    )

    prompt = f"""你是一个视频剪辑导演。下面是一个视频项目的素材理解结果。

用户目标：{goal or "（未指定，请按通用宣传/种草视频理解）"}

镜头清单：
{shots_brief or "（无）"}

语音转写：
{transcripts_brief or "（无）"}

请给出剪辑方案，用 JSON 数组输出，每个元素：
{{"title": "场景名", "shot_ids": ["..."], "narrative": "这一段讲什么", "role": "hook|body|climax|ending"}}
按成片顺序排列。只输出 JSON。"""

    t0 = time.time()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    text = resp.choices[0].message.content or "{}"

    import json
    import re

    m = re.search(r"\[.*\]", text, re.S)
    scenes = []
    if m:
        try:
            scenes = [SceneSuggestion(**s) for s in json.loads(m.group())]
        except Exception:
            pass
    memory.story = scenes

    cost = {
        "stage": "story_suggest", "model": model,
        "duration_sec": round(time.time() - t0, 1),
        "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
        "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
    }
    memory.costs.append(cost)
    return cost
