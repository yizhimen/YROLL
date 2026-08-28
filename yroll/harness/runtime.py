"""Generic Agent Runtime v0 —— Session/Task/Turn 循环（借鉴 Codex Harness 协议思想，Python 自研）。

来自 docs/44-codex-harness研究.md 的决策："抄协议，自研引擎"。

- Task：响应一次用户输入的完整执行（多轮 Turn）
- Turn：请求模型 → 解析动作 → 执行 → 观察结果回喂 → 下一 Turn
- Event：流式事件（task_started/turn/action_applied/task_finished...），
  V0 收集为列表返回，V1 走 WebSocket 推送（传输无关，同 Codex 设计）
- 审批：高风险动作（remove 等）走 approval_hook；无钩子时默认拒绝（安全默认）
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from openai import OpenAI

from yroll.core.commands import CommandError, CommandLayer

HIGH_RISK_OPS = {"remove"}  # 中高风险：删除/覆盖类动作必须审批

EventHandler = Callable[[dict], None]
ApprovalHook = Callable[[dict], bool]


class Task:
    """一次用户输入 → 多轮 Turn 直到模型不再给动作或达到上限。

    Mutation Gate (audit §6.5): when constructed with `session_id`, the Task
    enforces Edit Lease on every action applied. When `expected_base_revision`
    is also given, every action also checks that the project hasn't drifted
    beneath us. Without these, the Task falls back to legacy behavior (used
    for tests that don't go through the HTTP gate).
    """

    def __init__(self, cmd: CommandLayer, system: str,
                 max_turns: int = 4,
                 on_event: EventHandler | None = None,
                 approval_hook: ApprovalHook | None = None,
                 session_id: str | None = None,
                 expected_base_revision: int | None = None):
        self.cmd = cmd
        self.system = system
        self.max_turns = max_turns
        self.on_event = on_event or (lambda e: None)
        self.approval_hook = approval_hook
        self.session_id = session_id
        self.expected_base_revision = expected_base_revision
        self.events: list[dict] = []

    def _emit(self, type_: str, **data) -> None:
        e = {"type": type_, **data}
        self.events.append(e)
        self.on_event(e)

    def run(self, context: str, message: str) -> dict[str, Any]:
        self._emit("task_started")
        messages = [
            {"role": "system", "content": self.system},
            {"role": "user", "content": f"{context}\n\n【用户说】{message}"},
        ]
        reply, all_applied, all_errors, problems = "", [], [], []

        for turn in range(1, self.max_turns + 1):
            self._emit("turn_started", turn=turn)
            text = self._call_model(messages)
            reply, actions = _parse(text)
            self._emit("turn_finished", turn=turn, n_actions=len(actions))

            if not actions:
                break  # 模型没有再给动作 = 任务结束

            results = self._apply_batch(actions, all_applied, all_errors, problems)

            # 观察结果回喂，进入下一 Turn（"一个 Turn 的输出是下一个 Turn 的输入"）
            messages.append({"role": "assistant", "content": text})
            messages.append({
                "role": "user",
                "content": "【执行结果】\n" + "\n".join(results)
                + "\n\n如果任务已完成，输出 {\"reply\":\"总结\",\"actions\":[]}；"
                  "如果还需要继续操作，给出下一批 actions。",
            })

        self._emit("task_finished", turns=len([e for e in self.events
                                               if e["type"] == "turn_finished"]))
        return {
            "reply": reply,
            "applied": all_applied,
            "errors": all_errors,
            "problems_reported": problems,
            "events": self.events,
        }

    # ---------- Plan → Preview → Apply（蓝图 §3.5 权限三级） ----------

    def propose(self, context: str, message: str) -> dict[str, Any]:
        """Plan 阶段：只出计划（动作清单）不执行，给人审。"""
        self._emit("task_started")
        self._emit("turn_started", turn=1)
        text = self._call_model([
            {"role": "system", "content": self.system},
            {"role": "user", "content":
             f"{context}\n\n【用户说】{message}\n\n"
             "（计划模式：把要做的事一次性列进 actions，reply 里用一句话说明计划，"
             "不要分批、不要说'我先…'）"},
        ])
        reply, actions = _parse(text)
        self._emit("plan_drafted", n_actions=len(actions))
        return {"reply": reply, "actions": actions}

    def apply_actions(self, actions: list[dict]) -> dict[str, Any]:
        """Apply 阶段：执行人批准过的动作清单（高风险动作仍走审批钩子）。"""
        all_applied, all_errors, problems = [], [], []
        self._apply_batch(actions, all_applied, all_errors, problems)
        self._emit("task_finished", turns=1)
        return {
            "reply": "",
            "applied": all_applied,
            "errors": all_errors,
            "problems_reported": problems,
            "events": self.events,
        }

    def _apply_batch(self, actions: list[dict],
                     all_applied: list, all_errors: list,
                     problems: list) -> list[str]:
        """执行一批动作，结果逐条落日志/事件，返回人读的执行结果行。

        Mutation Gate (audit §6.5): when session_id is set, enforce Lease +
        Revision before executing any action. Returns an error row and skips
        the action if gate fails — Task does NOT abort, since one bad action
        shouldn't kill the whole batch.
        """
        if self.session_id:
            from yroll.core.lease import require_edit_right
            try:
                require_edit_right(self.cmd.core, self.session_id)
            except Exception as e:
                err = f"[gate] lease rejected: {e}"
                all_errors.append(err)
                self._emit("gate_rejected", reason="lease", error=str(e))
                return [err]
            if self.expected_base_revision is not None:
                from yroll.core.revision import check_project_revision
                try:
                    check_project_revision(self.cmd.core,
                                           self.expected_base_revision)
                except Exception as e:
                    err = f"[gate] revision conflict: {e}"
                    all_errors.append(err)
                    self._emit("gate_rejected", reason="revision", error=str(e))
                    return [err]
        results = []
        for a in actions:
            if a.get("op") in HIGH_RISK_OPS and not self._approve(a):
                all_errors.append({"action": a, "error": "未获批准"})
                results.append(f"动作 {a.get('op')} 被用户拒绝或未获批准")
                continue
            try:
                op = _execute(self.cmd, a)
                all_applied.append(op.operation_id)
                line = f"已执行 {a.get('op')} → {op.operation_id}"
                if op.type == "analyze_loudness":
                    # 分析类动作的价值在结果数据，必须回喂给模型（观察）
                    line += f"，结果：{json.dumps(op.after, ensure_ascii=False)}"
                results.append(line)
                self._emit("action_applied", op=a.get("op"), id=op.operation_id)
                if op.type == "report_problem":
                    prob = next((p for p in self.cmd.core.project.problems
                                 if p.problem_id == op.target), None)
                    if prob:
                        sols = [s for s in self.cmd.core.project.solutions
                                if s.problem_id == prob.problem_id]
                        problems.append({
                            "problem": prob.model_dump(),
                            "solutions": [s.model_dump() for s in sols],
                        })
            except (CommandError, KeyError, TypeError) as e:
                all_errors.append({"action": a, "error": str(e)})
                results.append(f"执行 {a.get('op')} 失败：{e}")
                self._emit("action_failed", op=a.get("op"), error=str(e))
        return results

    def _approve(self, action: dict) -> bool:
        if self.approval_hook is None:
            return False  # 安全默认：无审批通道时高风险动作拒绝
        return self.approval_hook(action)

    def _call_model(self, messages: list[dict]) -> str:
        resp = _client().chat.completions.create(
            model=os.environ.get("YROLL_TEXT_MODEL", "gpt-4o-mini"),
            messages=messages,
            max_tokens=2000,
        )
        return resp.choices[0].message.content or ""


def _client() -> OpenAI:
    return OpenAI(
        api_key=os.environ.get("YROLL_API_KEY", ""),
        base_url=os.environ.get("YROLL_BASE_URL", "https://api.openai.com/v1"),
    )


def _parse(text: str) -> tuple[str, list[dict]]:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return text, []
    try:
        data = json.loads(m.group())
        return data.get("reply", ""), data.get("actions", [])
    except json.JSONDecodeError:
        return text, []


def _execute(cmd: CommandLayer, a: dict) -> Any:
    """动作 → Command Layer（与 chat.py 同一映射； Harness 与单轮入口共用）。"""
    op = a["op"]
    why = a.get("why", "AI 任务")
    if op == "trim":
        return cmd.trim_clip(a["clip_id"], a.get("new_source_start"),
                             a.get("new_source_end"), why=why)
    if op == "split":
        cmd.split_clip(a["clip_id"], a["at_source_time"], why=why)
        return cmd.core.operations()[-1]
    if op == "move":
        return cmd.move_clip(a["clip_id"], a["new_timeline_start"], why=why)
    if op == "speed":
        return cmd.set_speed(a["clip_id"], a["speed"], why=why)
    if op == "volume":
        return cmd.set_volume(a["clip_id"], a["volume"], why=why)
    if op == "remove":
        return cmd.remove_clip(a["clip_id"], why=why)
    if op == "silence_remove":
        return cmd.remove_silence(a["clip_id"], why=why)
    if op == "denoise":
        return cmd.denoise_clip(a["clip_id"], a.get("strength", 12.0), why=why)
    if op == "fade":
        return cmd.set_fade(a["clip_id"], a.get("fade_in", 0.0),
                            a.get("fade_out", 0.0), why=why)
    if op == "dissolve":
        return cmd.set_dissolve(a["clip_id"], a.get("duration", 0.5), why=why)
    if op == "delogo":
        from yroll.core.manifest import Region
        return cmd.delogo_clip(a["clip_id"], Region(**a["region"]), why=why)
    if op == "subtitle_edit":
        return cmd.edit_subtitle(a["clip_id"], a["text"], why=why)
    if op == "add_subtitle":
        clip = cmd.add_subtitle(a["text"], a["start"], a["end"], why=why)
        return cmd.core.operations()[-1]
    if op == "generate_subtitles":
        return cmd.generate_subtitles(a.get("clip_id"), why=why)
    if op == "color":
        return cmd.set_color(a["clip_id"], **a.get("params", {}), why=why)
    if op == "flip":
        return cmd.set_flip(a["clip_id"], a.get("horizontal", False),
                            a.get("vertical", False), why=why)
    if op == "opacity":
        return cmd.set_opacity(a["clip_id"], a["opacity"], why=why)
    if op == "crop":
        return cmd.set_crop(a["clip_id"], **a.get("params", {}), why=why)
    if op == "reverse":
        return cmd.set_reverse(a["clip_id"], why=why)
    if op == "transform2d":
        return cmd.set_transform2d(a["clip_id"], **a.get("params", {}), why=why)
    if op == "voice_replace":
        return cmd.replace_clip_voice(a["clip_id"], a["text"],
                                      voice_id=a.get("voice_id"), why=why)
    if op == "revert":
        inv = cmd.core.revert(a["operation_id"], who="ai", why=why or "AI 语义撤销")
        if inv is None:
            raise CommandError(f"operation 不存在: {a['operation_id']}")
        return inv
    if op == "analyze_loudness":
        return cmd.analyze_loudness(a["clip_id"], why=why)
    if op == "problem":
        from yroll.core.manifest import ProblemCategory
        from yroll.core.problems import recommend, report_problem

        p = report_problem(
            cmd.core.project, a["description"],
            ProblemCategory(a.get("category", "temporal")),
            target_clip=a.get("clip_id"),
        )
        recommend(cmd.core.project, p)
        cmd.core.save_state()
        return cmd._record(
            "report_problem", p.problem_id, {},
            {"description": p.description, "category": p.category.value},
            why=a["description"], tool="ai.report_problem")
    raise CommandError(f"未知动作: {op}")
