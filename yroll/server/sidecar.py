"""桌面壳/部署用的极简入口：只含 serve 和 mcp，不碰 ingest 重依赖。

为什么单独存在：yroll.cli.main 顶层 import 了 faster-whisper（ASR），
PyInstaller 打包编辑后端时会把整个 ASR 栈拖进来（体积 + 打包脆弱）。
本入口模块图只有 fastapi/uvicorn/openai/pydantic —— 干净可 --onefile。

用法：
    yroll-backend serve <工程目录> [--host 127.0.0.1] [--port 8765]
    yroll-backend mcp <工程目录>
"""

from __future__ import annotations

import argparse
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(prog="yroll-backend")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="启动 YROLL Server（REST + WS + GUI 静态托管）")
    s.add_argument("project")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)

    m = sub.add_parser("mcp", help="启动 MCP Server（stdio）")
    m.add_argument("project")

    args = parser.parse_args()
    if args.cmd == "serve":
        from yroll.server.app import serve

        serve(args.project, host=args.host, port=args.port)
    else:
        from yroll.server.mcp_server import McpServer

        McpServer(args.project).serve_stdio()


if __name__ == "__main__":
    main()
