"""YROLL MCP Server —— 把工程暴露给外部 Agent（Claude Code / Codex 等）。

协议：MCP over stdio（换行分隔的 JSON-RPC 2.0），零依赖手写。
只实现核心方法：initialize / ping / tools/list / tools/call。

铁律不破：外部 Agent 与人手、内置 AI 走同一个 CommandLayer，
每个 tools/call 都是一条带 who/why 的 Operation（工程黑匣子对外一样完整）。

启动：
    python -m yroll.server.mcp_server <工程目录>

Claude Code 接入示例（claude mcp add）：
    claude mcp add yroll -- python -m yroll.server.mcp_server D:/path/to/project
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from yroll.core.commands import CommandError, CommandLayer
from yroll.core.manifest import Actor, Region, TimeRange
from yroll.core.project import ProjectCore

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "yroll", "version": "0.1.0"}


def build_tools(cmd_getter: Callable[[], CommandLayer]) -> dict[str, dict]:
    """工具表：name → {schema, call}。call 返回可 JSON 化的结果。"""
    def cmd() -> CommandLayer:
        return cmd_getter()

    def t(description: str, props: dict, required: list[str],
          call: Callable[..., Any]) -> dict:
        return {
            "description": description,
            "inputSchema": {"type": "object", "properties": props, "required": required},
            "call": call,
        }

    s = {"type": "string"}
    n = {"type": "number"}
    return {
        "yroll_get_project": t(
            "获取工程当前状态（轨道/clip/素材/问题）",
            {}, [],
            lambda _a=None: cmd().core.project.model_dump()),
        "yroll_list_operations": t(
            "获取 Operation Log（工程黑匣子：谁、何时、改了什么、为什么）",
            {}, [],
            lambda _a=None: [op.model_dump() for op in cmd().core.operations()]),
        "yroll_trim": t(
            "裁剪 clip 的源区间", {"clip_id": s, "new_source_start": n, "new_source_end": n, "why": s},
            ["clip_id"],
            lambda a: cmd().trim_clip(a["clip_id"], a.get("new_source_start"),
                                      a.get("new_source_end"), why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_split": t(
            "在源时间点切开 clip", {"clip_id": s, "at_source_time": n, "why": s},
            ["clip_id", "at_source_time"],
            lambda a: [c.model_dump() for c in
                       cmd().split_clip(a["clip_id"], a["at_source_time"], why=a.get("why", "MCP 调用"))]),
        "yroll_move": t(
            "移动 clip 到时间轴新位置", {"clip_id": s, "new_timeline_start": n, "why": s},
            ["clip_id", "new_timeline_start"],
            lambda a: cmd().move_clip(a["clip_id"], a["new_timeline_start"], why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_set_speed": t(
            "设置 clip 速度倍率", {"clip_id": s, "speed": n, "why": s},
            ["clip_id", "speed"],
            lambda a: cmd().set_speed(a["clip_id"], a["speed"], why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_set_volume": t(
            "设置 clip 音量 0-2", {"clip_id": s, "volume": n, "why": s},
            ["clip_id", "volume"],
            lambda a: cmd().set_volume(a["clip_id"], a["volume"], why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_remove_clip": t(
            "删除 clip（高风险）", {"clip_id": s, "why": s},
            ["clip_id"],
            lambda a: cmd().remove_clip(a["clip_id"], why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_silence_remove": t(
            "去停顿/气口：检测静音段并重建 clip",
            {"clip_id": s, "noise_db": n, "min_duration": n, "why": s},
            ["clip_id"],
            lambda a: cmd().remove_silence(a["clip_id"], a.get("noise_db", -35.0),
                                           a.get("min_duration", 0.5), why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_denoise": t(
            "降噪（非破坏性调整图层，渲染时生效）", {"clip_id": s, "strength": n, "why": s},
            ["clip_id"],
            lambda a: cmd().denoise_clip(a["clip_id"], a.get("strength", 12.0), why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_delogo": t(
            "去水印/台标（region 归一化坐标 0-1，非破坏性）",
            {"clip_id": s, "region": {"type": "object"}, "why": s},
            ["clip_id", "region"],
            lambda a: cmd().delogo_clip(a["clip_id"], Region(**a["region"]),
                                        why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_analyze_loudness": t(
            "测量 clip 响度（mean/max dB），结果在返回的 Operation.after 里",
            {"clip_id": s, "why": s}, ["clip_id"],
            lambda a: cmd().analyze_loudness(a["clip_id"], why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_revert": t(
            "撤销一条 Operation", {"operation_id": s, "why": s}, ["operation_id"],
            lambda a: (cmd().core.revert(a["operation_id"], who="mcp", why=a.get("why", "MCP 撤销"))
                       or {"error": f"operation 不存在: {a['operation_id']}"})),
        "yroll_set_color": t(
            "画面色彩（brightness/contrast/saturation/temperature/sharpen 按需给）",
            {"clip_id": s, "params": {"type": "object"}, "why": s}, ["clip_id", "params"],
            lambda a: cmd().set_color(a["clip_id"], **a["params"], why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_set_flip": t(
            "镜像翻转", {"clip_id": s, "horizontal": {"type": "boolean"},
            "vertical": {"type": "boolean"}, "why": s}, ["clip_id"],
            lambda a: cmd().set_flip(a["clip_id"], a.get("horizontal", False),
                                     a.get("vertical", False), why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_set_opacity": t(
            "不透明度 0-1", {"clip_id": s, "opacity": n, "why": s}, ["clip_id", "opacity"],
            lambda a: cmd().set_opacity(a["clip_id"], a["opacity"], why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_set_crop": t(
            "画面裁剪（四边比例 0-0.45）",
            {"clip_id": s, "params": {"type": "object"}, "why": s}, ["clip_id", "params"],
            lambda a: cmd().set_crop(a["clip_id"], **a["params"], why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_set_transform2d": t(
            "主轨 2D 变换（scale/x/y/rotation/bg_blur，模糊背景填充）",
            {"clip_id": s, "params": {"type": "object"}, "why": s}, ["clip_id", "params"],
            lambda a: cmd().set_transform2d(a["clip_id"], **a["params"], why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_set_reverse": t(
            "倒放（60s 内 clip）", {"clip_id": s, "why": s}, ["clip_id"],
            lambda a: cmd().set_reverse(a["clip_id"], why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_replace_voice": t(
            "TTS 语音重配（text → 合成语音替换原声）",
            {"clip_id": s, "text": s, "voice_id": s, "why": s}, ["clip_id", "text"],
            lambda a: cmd().replace_clip_voice(a["clip_id"], a["text"],
                                               voice_id=a.get("voice_id"),
                                               why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_render": t(
            "渲染预览视频 preview.mp4", {}, [],
            lambda _a=None: _render(cmd())),
        "yroll_set_transform": t(
            "设置 PiP 位置/尺寸（x/y/scale 归一化）",
            {"clip_id": s, "transform": {"type": "object"}, "why": s},
            ["clip_id", "transform"],
            lambda a: cmd().set_transform(a["clip_id"], a["transform"], why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_set_fade": t(
            "淡入淡出（秒）", {"clip_id": s, "fade_in": n, "fade_out": n, "why": s},
            ["clip_id"],
            lambda a: cmd().set_fade(a["clip_id"], a.get("fade_in", 0.0),
                                     a.get("fade_out", 0.0), why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_set_dissolve": t(
            "与前一个 clip 叠化（type: fade/wipeleft/slideleft 等）",
            {"clip_id": s, "duration": n, "kind": s, "why": s}, ["clip_id"],
            lambda a: cmd().set_dissolve(a["clip_id"], a.get("duration", 0.5),
                                         a.get("kind", "fade"), why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_volume_range": t(
            "时间范围内调音量（不必先 Split）",
            {"clip_id": s, "volume": n, "start": n, "end": n, "why": s},
            ["clip_id", "volume", "start", "end"],
            lambda a: cmd().set_volume_range(
                a["clip_id"], a["volume"],
                TimeRange(start=a["start"], end=a["end"]),
                why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_add_subtitle": t(
            "加字幕", {"text": s, "start": n, "end": n, "why": s},
            ["text", "start", "end"],
            lambda a: cmd().add_subtitle(a["text"], a["start"], a["end"],
                                         why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_edit_subtitle": t(
            "改字幕文字", {"clip_id": s, "text": s, "why": s}, ["clip_id", "text"],
            lambda a: cmd().edit_subtitle(a["clip_id"], a["text"], why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_generate_subtitles": t(
            "从 ASR 转写自动生成整轨字幕", {"clip_id": s, "why": s}, [],
            lambda a: cmd().generate_subtitles(a.get("clip_id"), why=a.get("why", "MCP 调用")).model_dump()),
        "yroll_search_transcripts": t(
            "台词搜索定位（返回 clip_id + 时间轴时间）", {"q": s}, ["q"],
            lambda a: _search(cmd(), a["q"])),
    }


def _search(cmd: CommandLayer, q: str) -> dict:
    from yroll.core.transcripts import load_transcripts

    transcripts = load_transcripts(cmd.core.project)
    results = []
    for track in cmd.core.project.timeline.tracks:
        for cid in track.clip_ids:
            clip = cmd.core.project.clips.get(cid)
            if not clip:
                continue
            for seg in transcripts.get(clip.asset_id, []):
                if q in seg.get("text", ""):
                    s = max(seg["start"], clip.source_range.start)
                    if s >= clip.source_range.end:
                        continue
                    results.append({
                        "clip_id": cid,
                        "timeline": round(clip.timeline_range.start + (
                            s - clip.source_range.start) / clip.speed, 2),
                        "text": seg["text"],
                    })
    return {"results": sorted(results, key=lambda r: r["timeline"])[:50]}


def _render(cmd: CommandLayer) -> dict:
    from yroll.core.render import render_preview

    out = render_preview(cmd.core, cmd.core.path / "preview.mp4")
    return {"preview": str(out)}


class McpServer:
    """stdio JSON-RPC 循环。handle() 独立可测（无 IO）。"""

    def __init__(self, project_path: str | Path):
        self.core = ProjectCore.open(project_path)
        self.cmd = CommandLayer(self.core, who=Actor.AI)
        self.tools = build_tools(lambda: self.cmd)

    def handle(self, req: dict) -> dict | None:
        """处理一条 JSON-RPC 请求。通知（无 id）返回 None。"""
        method = req.get("method", "")
        rid = req.get("id")

        if method == "initialize":
            return self._ok(rid, {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": SERVER_INFO,
                "capabilities": {"tools": {}},
            })
        if method == "ping":
            return self._ok(rid, {})
        if method == "notifications/initialized" or rid is None:
            return None
        if method == "tools/list":
            return self._ok(rid, {"tools": [
                {"name": name, "description": t["description"],
                 "inputSchema": t["inputSchema"]}
                for name, t in self.tools.items()
            ]})
        if method == "tools/call":
            params = req.get("params") or {}
            name = params.get("name", "")
            tool = self.tools.get(name)
            if tool is None:
                return self._err(rid, -32602, f"未知工具: {name}")
            try:
                result = tool["call"](params.get("arguments") or {})
                self.core.save_state()
                return self._ok(rid, {
                    "content": [{"type": "text",
                                 "text": json.dumps(result, ensure_ascii=False, default=str)}],
                    "isError": False,
                })
            except (CommandError, KeyError, TypeError) as e:
                return self._ok(rid, {
                    "content": [{"type": "text", "text": str(e)}],
                    "isError": True,
                })
        return self._err(rid, -32601, f"未知方法: {method}")

    @staticmethod
    def _ok(rid: Any, result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    @staticmethod
    def _err(rid: Any, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}

    def serve_stdio(self, instream=None, outstream=None) -> None:
        """stdio 主循环：每行一条 JSON-RPC 消息（MCP stdio transport）。"""
        instream = instream or sys.stdin
        outstream = outstream or sys.stdout
        for line in instream:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                continue
            resp = self.handle(req)
            if resp is not None:
                outstream.write(json.dumps(resp, ensure_ascii=False) + "\n")
                outstream.flush()


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python -m yroll.server.mcp_server <工程目录>", file=sys.stderr)
        sys.exit(1)
    McpServer(sys.argv[1]).serve_stdio()


if __name__ == "__main__":
    main()
