"""Skill 加载器 v0（借鉴 codex-rs/skills：loading / selection 分层）。

Skill = 目录 + SKILL.md（frontmatter: name/description/tools，正文是领域经验）。
原则（蓝图）："Skill 是什么时候做、怎么判断、注意什么；Tool 是怎么做。"
软件本体很小，能力插件化；按需加载——不把全部 Skill 塞给 LLM。

V0 选择策略：关键词匹配（够用即可）。V1 升级 embedding/LLM 路由。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"


@dataclass
class Skill:
    name: str
    description: str
    body: str
    tools: list[str] = field(default_factory=list)
    path: str = ""


_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    meta: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, m.group(2)


def load_skills(skills_dir: str | Path | None = None) -> list[Skill]:
    """加载目录下所有 skills（每个子目录一个 SKILL.md）。"""
    d = Path(skills_dir) if skills_dir else _DEFAULT_SKILLS_DIR
    if not d.is_dir():
        return []
    skills = []
    for sub in sorted(d.iterdir()):
        f = sub / "SKILL.md"
        if not f.exists():
            continue
        meta, body = _parse_frontmatter(f.read_text(encoding="utf-8"))
        skills.append(Skill(
            name=meta.get("name", sub.name),
            description=meta.get("description", ""),
            body=body.strip(),
            tools=[t.strip() for t in meta.get("tools", "").split(",") if t.strip()],
            path=str(sub),
        ))
    return skills


def select_skills(message: str, skills: list[Skill], max_skills: int = 2) -> list[Skill]:
    """按需选择：消息的二字元（bigram）与 Skill 名称/描述的重叠度排序。

    中文没有空格分词，直接子串匹配整词太脆（"停顿太多" 匹配不到 "停顿多"），
    用 bigram 重叠对中文鲁棒，V0 够用。V1 升级 embedding/LLM 路由。
    """
    shingles = {message[i:i + 2] for i in range(len(message) - 1)}

    def score(s: Skill) -> int:
        text = s.name + " " + s.description
        return sum(1 for g in shingles if g in text)

    ranked = sorted(skills, key=score, reverse=True)
    return [s for s in ranked[:max_skills] if score(s) > 0]


def select_skills_llm(message: str, skills: list[Skill],
                      client=None, model: str | None = None,
                      max_skills: int = 2) -> list[Skill]:
    """V1 路由：LLM 按语义选 Skill（"什么时候做"是判断题，正好是 LLM 的强项）。

    任何失败（无 client/网络/解析异常）都降级到 bigram——路由层永远不该拖死主流程。
    """
    if not skills or client is None:
        return select_skills(message, skills, max_skills)
    try:
        import os

        catalog = "\n".join(f"- {s.name}: {s.description}" for s in skills)
        resp = client.chat.completions.create(
            model=model or os.environ.get("YROLL_TEXT_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content":
                 "你是技能路由器。从下列技能中选出与用户意图相关的（0 到 "
                 f"{max_skills} 个），只输出 JSON：{{\"skills\":[\"name1\",...]}}，"
                 "无关就空数组。\n" + catalog},
                {"role": "user", "content": message},
            ],
            max_tokens=200,
        )
        text = resp.choices[0].message.content or ""
        m = re.search(r"\{.*\}", text, re.S)
        names = json.loads(m.group()).get("skills", []) if m else []
        picked = [s for s in skills if s.name in names][:max_skills]
        return picked if picked else select_skills(message, skills, max_skills)
    except Exception:
        return select_skills(message, skills, max_skills)


def inject_prompt(base_system: str, skills: list[Skill]) -> str:
    """把选中 Skill 的正文拼进 system prompt。"""
    if not skills:
        return base_system
    parts = [base_system, "\n【已加载的领域经验（Skills）】"]
    for s in skills:
        parts.append(f"## {s.name}\n{s.body}")
    return "\n".join(parts)
