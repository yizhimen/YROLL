# YROLL 部署指南（无 Docker）

结论：**不需要 Docker**。YROLL 是单进程全栈应用——FastAPI 同时提供 API、WebSocket 和 GUI 静态文件。
依赖只有三样：Python ≥ 3.12、FFmpeg、构建好的前端。

## 架构

```
┌─────────────────────────────────────────────┐
│ uvicorn (单进程)                             │
│  ├── /project /clips ...  REST API          │
│  ├── /ws/chat             WebSocket (AI)    │
│  └── /                    gui/dist 静态文件  │
├─────────────────────────────────────────────┤
│ ffmpeg / ffprobe (子进程调用)                │
│ 工程目录 (文件即数据库，无外部 DB)           │
└─────────────────────────────────────────────┘
```

## 服务器部署（Linux）

```bash
# 1. 系统依赖（一次性）
sudo apt install -y ffmpeg python3.12 python3.12-venv

# 2. 代码 + Python 依赖
git clone <repo> /opt/yroll && cd /opt/yroll
python3.12 -m venv .venv
.venv/bin/pip install .          # pyproject.toml 声明全部依赖
                                 # 注：faster-whisper 含 ctranslate2（ASR 用），包较大

# 3. 前端构建（在本地或 CI 构建好传上来也行，gui/dist 是纯静态）
cd gui && pnpm install && pnpm build && cd ..

# 4. LLM 凭据
cp .env.example .env   # 填 YROLL_API_KEY / YROLL_BASE_URL / YROLL_TEXT_MODEL

# 5. 启动（工程目录作为参数，素材就在工程目录里）
.venv/bin/python -m yroll.cli.main serve /data/projects/my-project --host 0.0.0.0 --port 8765
```

浏览器访问 `http://服务器IP:8765` —— GUI、API、WS 同一个端口。

## 开机自启（systemd，可选）

```ini
# /etc/systemd/system/yroll.service
[Unit]
Description=YROLL AI Video Workstation
After=network.target

[Service]
WorkingDirectory=/opt/yroll
ExecStart=/opt/yroll/.venv/bin/python -m yroll.cli.main serve /data/projects/my-project --host 0.0.0.0 --port 8765
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now yroll
```

## Windows 服务器

一样：装 Python 3.12 + FFmpeg（`winget install ffmpeg`），建好 venv 和 gui/dist 后：

```powershell
.venv\Scripts\python -m yroll.cli.main serve D:\projects\my-project --host 0.0.0.0 --port 8765
```

## 外部 Agent 接入（可选）

MCP Server 是独立 stdio 进程，随调随起，不需要常驻：

```bash
claude mcp add yroll -- /opt/yroll/.venv/bin/python -m yroll.cli.main mcp /data/projects/my-project
```

## 为什么不用 Docker

| 考量 | 结论 |
|------|------|
| 依赖 | Python + FFmpeg 两个系统包，镜像纯属套娃 |
| 数据 | 工程目录是文件即数据库，直接放宿主机磁盘，挂载卷反而碍事 |
| 进程 | 单进程（MCP 按需 spawn），没有编排需求 |
| 调试 | 服务器上直接 `journalctl -u yroll` 看日志，比进容器方便 |

真要多实例（多个工程共用一台服务器）：每个工程一个 uvicorn 进程 + 不同端口即可，
或者外层套一个 nginx 按路径分流——但那是规模化之后的事，现在用不上。

## 反向代理 / HTTPS（可选，对外开放时）

单机自用不需要。要对外就 nginx/Caddy 终结 TLS 后反代到 8765，
注意 WS 需要 `Upgrade` 头透传（`/ws/chat`）。
