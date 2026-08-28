"""YROLL GUI 静态服务 + API 转发。

- 静态文件从 gui/dist 目录服务（HTML/CSS/JS）
- 其他请求（/project, /presets, /assets/*, /clips/* ...）转发到后端 8765
- 一个端口搞定，避免 CORS / 跨域问题
"""
from __future__ import annotations

import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib import request as urlrequest

ROOT = Path(__file__).resolve().parents[1] / "gui" / "dist"
BACKEND = "http://127.0.0.1:8765"
PORT = 5173


class ProxyHandler(SimpleHTTPRequestHandler):
    """GET 走静态文件，找不到时转发；POST/PUT/DELETE/PATCH 全部转发到后端。"""

    # 不让父类处理 GET，先自己决定
    def do_GET(self):
        # 根路径 / 自动解析为 index.html（避免目录列表）
        if self.path == "/" or self.path == "":
            self.path = "/index.html"
        # 先按静态文件路径找
        path = self.translate_path(self.path)
        if not __import__("os").path.exists(path):
            # 静态文件不存在 → 转发到后端（API 路径）
            self.proxy_to_backend()
            return
        super().do_GET()

    def do_POST(self):
        self.proxy_to_backend()

    def do_PUT(self):
        self.proxy_to_backend()

    def do_DELETE(self):
        self.proxy_to_backend()

    def do_PATCH(self):
        self.proxy_to_backend()

    def proxy_to_backend(self):
        url = f"{BACKEND}{self.path}"
        # 复制请求体
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(content_length) if content_length else b""
        # 转发请求头（去掉 hop-by-hop）
        fwd_headers = {
            k: v for k, v in self.headers.items()
            if k.lower() not in ("host", "content-length")
        }
        try:
            req = urlrequest.Request(url, data=body if body else None,
                                      method=self.command, headers=fwd_headers)
            with urlrequest.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                # 复制响应头（排除 hop-by-hop）
                for k, v in resp.headers.items():
                    if k.lower() in ("transfer-encoding", "connection", "content-length"):
                        continue
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.read())
        except Exception as e:
            self.send_error(502, f"Proxy error: {e}")

    def log_message(self, fmt, *args):
        # 简化日志
        sys.stderr.write(f"[serve] {self.address_string()} {fmt % args}\n")


def main():
    print(f"=== YROLL GUI 服务 ===")
    print(f"静态文件: {ROOT}")
    print(f"API 转发: {BACKEND}")
    print(f"访问:    http://localhost:{PORT}")
    httpd = HTTPServer(("0.0.0.0", PORT), ProxyHandler)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
