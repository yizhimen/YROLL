"""YROLL MCP Server —— thin HTTP client of a running YROLL Project Server.

GUI-01.5: this module is no longer a ProjectCore owner. It opens an
HTTP client to `yroll serve <project>` and routes every project-state
write through the Mutation Gate, carrying `sessionId` and
`baseRevision` like the GUI does.

Lifecycle (per user review — no IO in __init__):

    McpServer(server_url, actor_id="claude-code")
        │
        ├── no IO, no threads, no sockets
        │
        .start()
        │   ensure_session(intent=edit)      # one-shot
        │   spawn daemon heartbeat thread    # 60s tick
        │
        .serve_stdio()                       # blocks on JSON-RPC loop
        │
        .shutdown(release=True|False)        # explicit
            stop heartbeat
            if release: release_lease()      # clean exit
            else: leave for TTL              # abnormal exit

Crash → heartbeat dies → TTL expiry → next peer re-acquires. The single
source of lease recovery is the server's TTL, not "release on exit".

启动（用户 / 集成方）：
    python -m yroll.server.mcp_server --server http://127.0.0.1:8765 \
        [--actor-id claude-code]

Claude Code 接入：
    claude mcp add yroll -- python -m yroll.server.mcp_server \\
        --server http://127.0.0.1:8765 --actor-id claude-code
"""

from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from yroll.mcp_http import YrollHttpClient, GateRejection

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "yroll", "version": "0.2.0"}


# ---------------------------------------------------------------------------
# Tool table
#
# Per GUI-01.5, every tool body routes through self.client (the HTTP
# client). Mutation tools in non-EDIT mode call /mutation/preview and
# tag the result with `preview: true` so the Agent can distinguish "I
# would change X" from "I changed X".
#
# The tool name ↔ HTTP path mapping is the canonical table from
# yroll-01.5 spec; do not invent new paths without checking the server.
# ---------------------------------------------------------------------------

def build_tools(server: "McpServer") -> dict[str, dict]:
    cli = server.client
    state = server.state  # holds sessionId, base_revision, mode, owner

    def read_tool(name: str, description: str, props: dict, required: list[str]):
        return {
            "description": description,
            "inputSchema": {"type": "object", "properties": props, "required": required},
            "_kind": "read",
            "_name": name,
        }

    def mutate_tool(name: str, description: str, path_template: str,
                     props: dict, required: list[str],
                     body_builder: Optional[Callable[[dict], dict]] = None):
        return {
            "description": description,
            "inputSchema": {"type": "object", "properties": props, "required": required},
            "_kind": "mutate",
            "_name": name,
            "_path_template": path_template,
            "_body_builder": body_builder,
        }

    s = {"type": "string"}
    n = {"type": "number"}
    b = {"type": "boolean"}
    o = {"type": "object"}

    def arg_get(a, key, default=None):
        return a.get(key, default)

    def call_mutation(tool_def, a):
        path = tool_def["_path_template"].format(**a)
        body = tool_def["_body_builder"](a) if tool_def["_body_builder"] else a
        sid = state["sessionId"]
        rev = state["base_revision"]
        if state["mode"] == "edit":
            return cli.mutate("POST", path, body=body,
                              session_id=sid, base_revision=rev)
        # OBSERVE / PROPOSE → preview, not commit
        preview_body = {
            "sessionId": sid, "baseRevision": rev,
            "selection": {"clip_ids": [a["clip_id"]]} if "clip_id" in a else {},
            "op": _path_to_op(path), "params": body,
        }
        result = cli.preview(preview_body, session_id=sid, base_revision=rev)
        return {"preview": True, "would_change": result}

    def call_mutation_no_clip(tool_def, a):
        path = tool_def["_path_template"].format(**a)
        body = tool_def["_body_builder"](a) if tool_def["_body_builder"] else a
        sid = state["sessionId"]
        rev = state["base_revision"]
        if state["mode"] == "edit":
            return cli.mutate("POST", path, body=body,
                              session_id=sid, base_revision=rev)
        preview_body = {
            "sessionId": sid, "baseRevision": rev,
            "selection": {},
            "op": _path_to_op(path), "params": body,
        }
        result = cli.preview(preview_body, session_id=sid, base_revision=rev)
        return {"preview": True, "would_change": result}

    def call_read(tool_def, _a):
        return cli.read(tool_def["_path_template"])

    def t_mut(name, desc, path, props, req, builder=None):
        td = mutate_tool(name, desc, path, props, req, builder)
        td["call"] = (lambda td: (lambda a: call_mutation_no_clip(td, a)))(td)
        # Re-bind if it has clip_id in the path template
        if "{clip_id}" in path:
            td["call"] = (lambda td: (lambda a: call_mutation(td, a)))(td)
        return td

    def t_read(name, desc, path):
        td = read_tool(name, desc, {}, [])
        td["_path_template"] = path
        td["call"] = (lambda td: (lambda a: call_read(td, a)))(td)
        return td

    tools = {
        "yroll_get_project": t_read("yroll_get_project",
            "获取工程当前状态（轨道/clip/素材/问题）", "/project"),
        "yroll_list_operations": t_read("yroll_list_operations",
            "获取 Operation Log", "/operations"),
        "yroll_trim": t_mut("yroll_trim", "裁剪 clip 的源区间",
            "/clips/{clip_id}/trim",
            {"clip_id": s, "new_source_start": n, "new_source_end": n, "why": s},
            ["clip_id"]),
        "yroll_split": t_mut("yroll_split", "在源时间点切开 clip",
            "/clips/{clip_id}/split",
            {"clip_id": s, "at_source_time": n, "why": s},
            ["clip_id", "at_source_time"]),
        "yroll_move": t_mut("yroll_move", "移动 clip 到时间轴新位置",
            "/clips/{clip_id}/move",
            {"clip_id": s, "new_timeline_start": n, "new_track_id": s, "why": s},
            ["clip_id", "new_timeline_start"]),
        "yroll_set_speed": t_mut("yroll_set_speed", "设置 clip 速度倍率",
            "/clips/{clip_id}/speed",
            {"clip_id": s, "speed": n, "why": s}, ["clip_id", "speed"]),
        "yroll_set_volume": t_mut("yroll_set_volume", "设置 clip 音量 0-2",
            "/clips/{clip_id}/volume",
            {"clip_id": s, "volume": n, "why": s}, ["clip_id", "volume"]),
        "yroll_remove_clip": t_mut("yroll_remove_clip", "删除 clip（高风险）",
            "/clips/{clip_id}",
            {"clip_id": s, "ripple": b, "why": s}, ["clip_id"]),
        "yroll_silence_remove": t_mut("yroll_silence_remove",
            "去停顿/气口：检测静音段并重建 clip",
            "/clips/{clip_id}/silence-remove",
            {"clip_id": s, "noise_db": n, "min_duration": n, "why": s},
            ["clip_id"]),
        "yroll_denoise": t_mut("yroll_denoise",
            "降噪（非破坏性调整图层，渲染时生效）",
            "/clips/{clip_id}/denoise",
            {"clip_id": s, "strength": n, "why": s}, ["clip_id"]),
        "yroll_delogo": t_mut("yroll_delogo",
            "去水印/台标（region 归一化坐标 0-1，非破坏性）",
            "/clips/{clip_id}/delogo",
            {"clip_id": s, "region": o, "why": s}, ["clip_id", "region"]),
        "yroll_analyze_loudness": t_mut("yroll_analyze_loudness",
            "测量 clip 响度（mean/max dB）",
            "/clips/{clip_id}/loudness",
            {"clip_id": s, "why": s}, ["clip_id"]),
        "yroll_revert": t_mut("yroll_revert", "撤销一条 Operation",
            "/revert",
            {"operation_id": s, "why": s}, ["operation_id"]),
        "yroll_set_color": t_mut("yroll_set_color", "画面色彩",
            "/clips/{clip_id}/color",
            {"clip_id": s, "params": o, "why": s}, ["clip_id", "params"]),
        "yroll_set_flip": t_mut("yroll_set_flip", "镜像翻转",
            "/clips/{clip_id}/flip",
            {"clip_id": s, "horizontal": b, "vertical": b, "why": s},
            ["clip_id"]),
        "yroll_set_opacity": t_mut("yroll_set_opacity", "不透明度 0-1",
            "/clips/{clip_id}/opacity",
            {"clip_id": s, "opacity": n, "why": s}, ["clip_id", "opacity"]),
        "yroll_set_crop": t_mut("yroll_set_crop", "画面裁剪",
            "/clips/{clip_id}/crop",
            {"clip_id": s, "params": o, "why": s}, ["clip_id", "params"]),
        "yroll_set_transform2d": t_mut("yroll_set_transform2d",
            "主轨 2D 变换", "/clips/{clip_id}/transform2d",
            {"clip_id": s, "params": o, "why": s}, ["clip_id", "params"]),
        "yroll_set_reverse": t_mut("yroll_set_reverse", "倒放（60s 内 clip）",
            "/clips/{clip_id}/reverse",
            {"clip_id": s, "why": s}, ["clip_id"]),
        "yroll_replace_voice": t_mut("yroll_replace_voice",
            "TTS 语音重配（text → 合成语音替换原声）",
            "/clips/{clip_id}/voice-replace",
            {"clip_id": s, "text": s, "voice_id": s, "why": s},
            ["clip_id", "text"]),
        "yroll_render": t_mut("yroll_render", "渲染预览视频 preview.mp4",
            "/render", {}, []),
        "yroll_set_transform": t_mut("yroll_set_transform",
            "设置 PiP 位置/尺寸（x/y/scale 归一化）",
            "/clips/{clip_id}/transform",
            {"clip_id": s, "transform": o, "why": s}, ["clip_id", "transform"]),
        "yroll_set_fade": t_mut("yroll_set_fade", "淡入淡出（秒）",
            "/clips/{clip_id}/fade",
            {"clip_id": s, "fade_in": n, "fade_out": n, "why": s}, ["clip_id"]),
        "yroll_set_dissolve": t_mut("yroll_set_dissolve", "与前一个 clip 叠化",
            "/clips/{clip_id}/dissolve",
            {"clip_id": s, "duration": n, "kind": s, "why": s}, ["clip_id"]),
        "yroll_volume_range": t_mut("yroll_volume_range",
            "时间范围内调音量", "/clips/{clip_id}/volume-range",
            {"clip_id": s, "volume": n, "start": n, "end": n, "why": s},
            ["clip_id", "volume", "start", "end"]),
        "yroll_add_subtitle": t_mut("yroll_add_subtitle", "加字幕",
            "/subtitles", {"text": s, "start": n, "end": n, "why": s},
            ["text", "start", "end"]),
        "yroll_edit_subtitle": t_mut("yroll_edit_subtitle", "改字幕文字",
            "/clips/{clip_id}/subtitle",
            {"clip_id": s, "text": s, "why": s}, ["clip_id", "text"]),
        "yroll_generate_subtitles": t_mut("yroll_generate_subtitles",
            "从 ASR 转写自动生成整轨字幕",
            "/subtitles/generate", {"clip_id": s, "why": s}, []),
        "yroll_search_transcripts": t_read("yroll_search_transcripts",
            "台词搜索定位（返回 clip_id + 时间轴时间）", "/search-transcripts"),
    }
    # Wire up search_transcripts query param
    tools["yroll_search_transcripts"]["call"] = lambda a: cli.read(
        f"/search-transcripts?q={a.get('q', '')}")

    # resolve_voice needs clip_id, so its call must use call_mutation
    tools["yroll_replace_voice"]["call"] = lambda a: call_mutation(
        tools["yroll_replace_voice"], a)
    # add_subtitle has no clip_id; use the no-clip variant
    tools["yroll_add_subtitle"]["call"] = lambda a: call_mutation_no_clip(
        tools["yroll_add_subtitle"], a)
    tools["yroll_generate_subtitles"]["call"] = lambda a: call_mutation_no_clip(
        tools["yroll_generate_subtitles"], a)
    tools["yroll_revert"]["call"] = lambda a: call_mutation_no_clip(
        tools["yroll_revert"], a)
    tools["yroll_render"]["call"] = lambda a: call_mutation_no_clip(
        tools["yroll_render"], a)
    tools["yroll_search_transcripts"]["call"] = lambda a: cli.read(
        f"/search-transcripts?q={a.get('q', '')}")

    return tools


# Map a mutation HTTP path to a /mutation/preview `op` value.
# /mutation/preview takes {op, params, selection}; `op` is a high-level
# verb (move / delete / ripple_delete / set_volume / etc). The Core
# layer has its own mapping; for now we pass a reasonable op name and
# let the server translate.
def _path_to_op(path: str) -> str:
    # /clips/{id}/trim, /clips/{id}/split, /clips/{id}/move, ...
    if "/trim" in path: return "trim"
    if "/split" in path: return "split"
    if "/move" in path: return "move"
    if "/speed" in path: return "set_speed"
    if "/volume-range" in path: return "set_volume_range"
    if "/volume" in path: return "set_volume"
    if "/mute" in path: return "set_muted"
    if path.rstrip("/").count("/") == 2 and path.endswith("") is False:
        if path.startswith("/clips/"): return "delete"
    if "/revert" in path: return "revert"
    if "/render" in path: return "render"
    if "/subtitle" in path: return "edit_subtitle"
    if "/subtitles" in path: return "add_subtitle"
    if "/denoise" in path: return "denoise"
    if "/delogo" in path: return "delogo"
    if "/silence-remove" in path: return "silence_remove"
    if "/color" in path: return "set_color"
    if "/flip" in path: return "set_flip"
    if "/opacity" in path: return "set_opacity"
    if "/crop" in path: return "set_crop"
    if "/transform" in path: return "set_transform"
    if "/transform2d" in path: return "set_transform2d"
    if "/reverse" in path: return "set_reverse"
    if "/voice-replace" in path: return "replace_voice"
    if "/fade" in path: return "set_fade"
    if "/dissolve" in path: return "set_dissolve"
    return "unknown"


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class McpServer:
    """stdio JSON-RPC loop. Lifecycle: construct → .start() → serve_stdio
    → .shutdown(release)."""

    def __init__(self, server_url: str, actor_id: str = "claude-code",
                  heartbeat_sec: float = 60.0):
        # No IO, no threads, no sockets in __init__.
        self.server_url = server_url
        self.actor_id = actor_id
        self.heartbeat_sec = heartbeat_sec
        self.client = YrollHttpClient(server_url)
        self.state: dict = {
            "sessionId": None,
            "mode": "observe",
            "owner": "free",
            "base_revision": 0,
        }
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop: Optional[threading.Event] = None
        self._tools: Optional[dict] = None

    def start(self) -> None:
        """Establish session with the Project Server, start heartbeat.

        Idempotent: calling twice is a no-op.
        """
        if self._heartbeat_thread is not None:
            return
        self._tools = build_tools(self)

        # One-shot ensure_session. We pass the current revision as
        # base_revision so the server knows the requester's view of
        # the world; the response carries the live revision back.
        try:
            self._ui = self.client.ui_status()
            base_rev = self._ui.get("base_revision", 0)
        except Exception:
            base_rev = 0

        result = self.client.ensure_session(
            actor="agent", actor_id=self.actor_id,
            intent="edit", base_revision=base_rev,
        )
        self.state["sessionId"] = result.get("sessionId")
        self.state["mode"] = result.get("mode", "observe")
        self.state["owner"] = result.get("owner", "free")
        self.state["base_revision"] = result.get("revision", base_rev)

        # Start heartbeat daemon
        self._heartbeat_stop = threading.Event()
        sid_provider = lambda: self.state["sessionId"]  # noqa: E731
        def heartbeat_main():
            while not self._heartbeat_stop.is_set():
                sid = sid_provider()
                if sid:
                    try:
                        self.client.heartbeat_lease(sid)
                    except Exception:
                        pass
                # Sleep in 1s slices for responsive shutdown
                for _ in range(int(self.heartbeat_sec)):
                    if self._heartbeat_stop.is_set():
                        return
                    time.sleep(1)
        self._heartbeat_thread = threading.Thread(
            target=heartbeat_main, daemon=True, name="mcp-heartbeat")
        self._heartbeat_thread.start()

    def shutdown(self, release: bool = True) -> None:
        """Stop heartbeat, optionally release the lease.

        If `release=False`, the lease is left for the server's TTL to
        expire. Use False for crash paths so the peer can re-acquire
        quickly; use True for clean KeyboardInterrupt exits.
        """
        if self._heartbeat_stop is not None:
            self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=2.0)
            self._heartbeat_thread = None
        self._heartbeat_stop = None
        if release and self.state.get("sessionId"):
            try:
                self.client.release_lease(self.state["sessionId"])
            except Exception:
                pass
        self.state["sessionId"] = None

    # ---- JSON-RPC dispatch ----

    def handle(self, req: dict) -> dict | None:
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
                {"name": t["_name"], "description": t["description"],
                 "inputSchema": t["inputSchema"]}
                for t in (self._tools or {}).values()
            ]})
        if method == "tools/call":
            params = req.get("params") or {}
            name = params.get("name", "")
            arguments = params.get("arguments") or {}
            tool = (self._tools or {}).get(name)
            if tool is None:
                return self._err(rid, -32602, f"未知工具: {name}")
            try:
                result = tool["call"](arguments)
                # After a successful mutation, refresh revision from
                # the server so the next mutation rides the right base.
                if tool["_kind"] == "mutate" and isinstance(result, dict) \
                        and not result.get("preview") \
                        and self.state["mode"] == "edit":
                    try:
                        st = self.client.ui_status(self.state["base_revision"])
                        self.state["base_revision"] = st.get(
                            "base_revision", self.state["base_revision"])
                    except Exception:
                        pass
                return self._ok(rid, {
                    "content": [{"type": "text",
                                 "text": json.dumps(result, ensure_ascii=False,
                                                     default=str)}],
                    "isError": False,
                })
            except GateRejection as e:
                return self._ok(rid, {
                    "content": [{"type": "text",
                                 "text": json.dumps(
                                     {"gate": e.kind, "status": e.status,
                                      "detail": e.detail},
                                     ensure_ascii=False)}],
                    "isError": True,
                })
            except Exception as e:
                return self._ok(rid, {
                    "content": [{"type": "text", "text": str(e)}],
                    "isError": True,
                })
        return self._err(rid, -32601, f"未知方法: {method}")

    @staticmethod
    def _ok(rid, result):
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    @staticmethod
    def _err(rid, code, message):
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}

    def serve_stdio(self, instream=None, outstream=None) -> None:
        instream = instream or sys.stdin
        outstream = outstream or sys.stdout
        try:
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
        finally:
            self.shutdown(release=False)


    def _cli_run(self) -> None:
        """Lifecycle used by the `yroll mcp` CLI entry point.

        Construct → .start() → serve_stdio → .shutdown(release=True)
        on KeyboardInterrupt. Crash paths leave the lease for TTL.
        """
        self.start()
        try:
            self.serve_stdio()
        except KeyboardInterrupt:
            self.shutdown(release=True)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(
        description="YROLL MCP server (HTTP client of yroll serve)")
    ap.add_argument("--server", required=True,
                    help="URL of running YROLL server, e.g. http://127.0.0.1:8765")
    ap.add_argument("--actor-id", default="claude-code",
                    help="Stable identity for /session/ensure resume (default: claude-code)")
    args = ap.parse_args()
    McpServer(args.server, actor_id=args.actor_id)._cli_run()
