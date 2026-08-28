# YROLL 项目目录结构

> 生成时间：2026-08-25
> 根目录：`D:\cc\YROLL`
> 说明：已忽略 `.venv/`、`.pytest_cache/`、`__pycache__/`、`dist/`、`build/`、`node_modules/`、`target/`、`.cargo/`、`.fingerprint/`、`.next/`、`.agents/`、`.github/`、`.vscode/`、`.moon/` 等构建/缓存目录。

## 根目录

```
YROLL/
├── .claude/                          # Claude 会话调度持久化
│   ├── scheduled_tasks.json
│   └── scheduled_tasks.lock
├── README.md
├── SESSION.md                        # 会话摘要/恢复上下文
├── pyproject.toml
├── yroll-backend.spec                # PyInstaller 后端打包规格
├── install-cpp-workload.bat          # 安装 MSVC C++ 工作负荷
├── 安装C++工作负荷.bat               # 同上（中文文件名）
├── vs_BuildTools.exe                 # Visual Studio Build Tools 安装器
│
├── # —— 顶层文档 ——
├── YROLL-产品蓝图-整理终稿.md
├── YROLL-开发规划.md
├── YROLL产品蓝图补充.md
├── chatgpt-conversation-6a815662-1787490203014.md
├── chatgpt-conversation-6a815662-1787490203014-整理版.md
│
├── # —— 核心代码 ——
├── yroll/                            # 主包（Python 后端）
│   ├── __init__.py
│   ├── cli/                          # 命令行入口
│   │   ├── __init__.py
│   │   └── main.py
│   ├── core/                         # 领域核心
│   │   ├── __init__.py
│   │   ├── commands.py
│   │   ├── links.py
│   │   ├── manifest.py
│   │   ├── models.py
│   │   ├── problems.py
│   │   ├── project.py
│   │   ├── publish.py
│   │   ├── render.py
│   │   ├── resolver.py
│   │   ├── store.py
│   │   └── transcripts.py
│   ├── harness/                      # Agent Harness 运行时
│   │   ├── __init__.py
│   │   ├── runtime.py
│   │   └── skills.py
│   ├── ingest/                       # 素材导入与解析
│   │   ├── __init__.py
│   │   ├── asr.py                    # 语音识别（faster-whisper）
│   │   ├── director.py
│   │   ├── jianying.py               # 剪映工程解析
│   │   ├── scanner.py
│   │   └── shots.py
│   ├── server/                       # 本地 API / MCP 服务
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── chat.py
│   │   ├── mcp_server.py
│   │   └── sidecar.py
│   └── tools/                        # 原子工具集
│       ├── __init__.py
│       ├── audio_tools.py            # 音频降噪/响度平衡/静音/去水印
│       ├── cloud_gen.py              # 云端生图/生视频
│       └── tts.py                    # TTS
│
├── # —— 桌面 GUI（Tauri + React）——
├── gui/
│   ├── src/                          # 前端（React + TS）
│   │   ├── App.tsx
│   │   ├── api.ts
│   │   ├── main.tsx
│   │   ├── styles.css
│   │   └── components/
│   │       ├── AssetPanel.tsx
│   │       ├── ChatPanel.tsx
│   │       ├── ClipBlock.tsx
│   │       ├── ClipWorkspace.tsx
│   │       ├── MenuBar.tsx
│   │       ├── OpsPanel.tsx
│   │       ├── PreviewPlayer.tsx
│   │       ├── Timeline.tsx
│   │       └── VisualAdjustPanel.tsx
│   └── src-tauri/                    # Tauri 桌面壳
│       ├── src/
│       │   └── main.rs
│       ├── gen/
│       │   └── schemas/
│       └── icons/                    # Android / iOS 多分辨率图标
│
├── # —— Skills ——
├── skills/
│   ├── loudness-balance/
│   │   └── SKILL.md
│   ├── noise-reduction/
│   │   └── SKILL.md
│   ├── silence-cleanup/
│   │   └── SKILL.md
│   └── watermark-removal/
│       └── SKILL.md
│
├── # —— 项目数据 ——
├── projects/
│   └── jdz-chaishao/                 # 示例项目：煎蛋·柴少
│       ├── current.json
│       ├── preview.mp4
│       ├── cache/                    # 缩略图与波形缓存
│       │   ├── thumb-38f193dc399c-0.1.jpg
│       │   ├── thumb-4487ace89ecf-0.1.jpg
│       │   ├── thumb-4487ace89ecf-3.5.jpg
│       │   ├── thumb-86f7057f4a8b-0.1.jpg
│       │   ├── thumb-a4abb813c2b2-0.5.jpg
│       │   ├── thumb-ab0d7ea0ca45-0.1.jpg
│       │   ├── thumb-c57b98b9040c-0.5.jpg
│       │   ├── wave-38f193dc399c-300.json
│       │   ├── wave-4487ace89ecf-300.json
│       │   ├── wave-86f7057f4a8b-300.json
│       │   ├── wave-a4abb813c2b2-30.json
│       │   └── wave-a4abb813c2b2-300.json
│       ├── generated/                # 生成产物（占位）
│       ├── media/                    # 原始素材（占位）
│       ├── operations/               # 操作日志（op00001~op00066.json）
│       │   ├── op00001.json
│       │   ├── ...
│       │   └── op00066.json
│       └── versions/
│           └── v1.json
│
├── # —— 模型权重 ——
├── models/
│   └── faster-whisper-small/         # faster-whisper small 模型
│       ├── config.json
│       ├── model.bin
│       ├── tokenizer.json
│       └── vocabulary.txt
│
├── # —— 辅助脚本与配置 ——
├── scripts/
│   └── e2e_mvp.py                    # MVP 端到端验证脚本
├── packaging/
│   └── sidecar_entry.py              # PyInstaller sidecar 入口
├── tests/                            # 单元/集成测试
│   ├── __init__.py
│   ├── test_audio_l1.py
│   ├── test_chat_context.py
│   ├── test_core.py
│   ├── test_harness.py
│   ├── test_ingest.py
│   ├── test_jianying.py
│   ├── test_links.py
│   ├── test_mcp.py
│   ├── test_phase6.py
│   ├── test_problems.py
│   ├── test_publish_cost.py
│   ├── test_render.py
│   ├── test_render_multitrack.py
│   ├── test_server.py
│   ├── test_silence.py
│   ├── test_skills.py
│   ├── test_subtitle_waveform.py
│   ├── test_visual_adjust.py
│   └── test_ws.py
│
├── docs/                             # 项目文档
│   ├── 44-codex-harness研究.md
│   ├── 45-最终目标对齐与实施计划.md
│   ├── deployment.md
│   └── manifest-v0.1.md
│
├── extract/                          # 长文档切片（用于检索/RAG）
│   ├── part1.md
│   ├── part2.md
│   ├── part3.md
│   ├── part4.md
│   ├── part5.md
│   ├── part6.md
│   └── part7.md
│
├── # —— 参考项目（克隆源码，供对比/借鉴）——
└── 参考/
    ├── OpenChatCut-0.2.3-x64.exe                 # OpenChatCut 安装包
    ├── Velorn-0.3.27-windows-installer-x64.exe   # Velorn 安装包
    │
    ├── OpenChatCut-main/                         # OpenChatCut 源码参考
    │   ├── assets/
    │   │   ├── agent/
    │   │   ├── audio/
    │   │   ├── branding/
    │   │   ├── fonts/
    │   │   │   ├── douyin-meihaoti/
    │   │   │   ├── huxiaobo-nanshenti/
    │   │   │   ├── huxiaobo-saobaoti/
    │   │   │   ├── huxiaobo-zhenshuaiti/
    │   │   │   ├── noto-sans-sc/
    │   │   │   │   └── files/
    │   │   │   ├── pangmen-zhengdao-biaotiti/
    │   │   │   ├── pangmen-zhengdao-qingsongti/
    │   │   │   ├── qingsong-shouxieti-san-p/
    │   │   │   ├── qingsong-shouxieti-yi/
    │   │   │   └── smiley-sans/
    │   │   ├── library-previews/
    │   │   ├── luts/
    │   │   ├── media/
    │   │   ├── model-capabilities/
    │   │   ├── plugins/
    │   │   ├── readme-pic/
    │   │   ├── sound-effects/
    │   │   ├── templates/
    │   │   ├── thumbnails/
    │   │   ├── vendor-icons/
    │   │   └── voice-samples/
    │   ├── config/
    │   ├── desktop/
    │   ├── public/
    │   │   ├── fonts/
    │   │   └── models/
    │   │       └── silero-vad/
    │   ├── remotion/
    │   ├── scripts/
    │   ├── server/
    │   │   ├── agent-runs/
    │   │   ├── codex/
    │   │   ├── external-agent/
    │   │   ├── plugins/
    │   │   └── storage/
    │   ├── shared/
    │   │   └── model-packs/
    │   ├── skills/
    │   │   └── openchatcut/
    │   │       ├── agents/
    │   │       ├── assets/
    │   │       └── references/
    │   └── src/
    │       ├── agent/
    │       │   ├── codex/
    │       │   ├── progress/
    │       │   ├── settings/
    │       │   ├── skills/
    │       │   │   ├── ai-cinematic-short-film/
    │       │   │   │   └── references/
    │       │   │   ├── asset-import/
    │       │   │   ├── create-motion-graphics/
    │       │   │   │   └── references/
    │       │   │   ├── explainer-video/
    │       │   │   │   └── references/
    │       │   │   ├── export/
    │       │   │   ├── image-gen/
    │       │   │   │   └── references/
    │       │   │   ├── known-errors/
    │       │   │   ├── long-video-to-shorts/
    │       │   │   │   └── references/
    │       │   │   ├── motion-graphic-placement/
    │       │   │   ├── multi-clips-to-reels/
    │       │   │   │   └── references/
    │       │   │   ├── music/
    │       │   │   │   └── references/
    │       │   │   ├── music-intelligence/
    │       │   │   ├── news-rough-cut/
    │       │   │   │   └── references/
    │       │   │   ├── openchatcut-plugin-basics/
    │       │   │   ├── product-ad-video-script/
    │       │   │   │   └── references/
    │       │   │   ├── product-help/
    │       │   │   │   └── references/
    │       │   │   ├── shader-gen/
    │       │   │   │   ├── examples/
    │       │   │   │   └── references/
    │       │   │   ├── skill-creator/
    │       │   │   ├── storyboard-shot-breakdown/
    │       │   │   ├── talking-head-guide/
    │       │   │   ├── transcription/
    │       │   │   ├── verification/
    │       │   │   ├── video-gen/
    │       │   │   │   └── references/
    │       │   │   ├── video-thumbnail-generator/
    │       │   │   ├── voice/
    │       │   │   │   └── references/
    │       │   │   └── widget-forms/
    │       │   └── tools/
    │       │       └── schemas/
    │       ├── app/
    │       ├── audio/
    │       │   └── intelligence/
    │       ├── captions/
    │       ├── color/
    │       ├── components/
    │       │   ├── chat/
    │       │   ├── dashboard/
    │       │   ├── inspector/
    │       │   ├── preview/
    │       │   ├── settings/
    │       │   └── timeline/
    │       ├── editor/
    │       ├── export/
    │       ├── fonts/
    │       ├── generate/
    │       ├── geometry/
    │       ├── gl/
    │       │   ├── fx/
    │       │   └── shaders/
    │       ├── hooks/
    │       ├── i18n/
    │       │   └── dict/
    │       │       ├── en/
    │       │       ├── it/
    │       │       ├── ru/
    │       │       └── zh/
    │       ├── library/
    │       ├── media/
    │       │   └── semantic-search/
    │       ├── multicam/
    │       ├── persist/
    │       │   └── migrations/
    │       │       └── fixtures/
    │       ├── plugins/
    │       ├── reframe/
    │       ├── review/
    │       ├── scene-detection/
    │       ├── script/
    │       ├── shortcuts/
    │       ├── tracking/
    │       ├── transcript/
    │       └── ui/
    │
    └── OpenCut-main/                             # OpenCut 源码参考
        ├── apps/
        │   ├── api/
        │   │   └── src/
        │   ├── desktop/
        │   │   ├── src/
        │   │   │   ├── components/
        │   │   │   └── panels/
        │   │   └── ...（略）
        │   └── web/
        │       ├── public/
        │       ├── src/
        │       │   ├── components/
        │       │   │   └── ui/
        │       │   ├── hooks/
        │       │   ├── lib/
        │       │   └── routes/
        │       └── ...
        ├── brand/
        │   └── marks/
        ├── changelog/
        └── （参考目录树，详见源码）
```

## 简要总览

| 路径 | 用途 |
|------|------|
| `yroll/` | Python 后端核心（CLI / Core / Harness / Ingest / Server / Tools） |
| `gui/` | Tauri + React 桌面 GUI 前端 |
| `skills/` | Agent Skills（音频四件套） |
| `projects/` | 用户项目数据（当前为 `jdz-chaishao` 示例） |
| `models/` | faster-whisper 模型权重 |
| `tests/` | 后端测试套件 |
| `docs/` | 项目文档 |
| `extract/` | 长文档切片 |
| `scripts/` / `packaging/` | 端到端测试与打包脚本 |
| `参考/` | OpenChatCut / OpenCut 参考源码与安装包 |

## 关键文件清单

### 顶层文档
- `README.md`
- `SESSION.md`
- `YROLL-产品蓝图-整理终稿.md`
- `YROLL-开发规划.md`
- `YROLL产品蓝图补充.md`
- `chatgpt-conversation-...md`（对话原始与整理版）

### 后端入口
- `yroll/cli/main.py` — CLI 入口
- `yroll/server/app.py` — FastAPI 应用
- `yroll/server/mcp_server.py` — MCP 服务
- `yroll/harness/runtime.py` — Agent Harness 运行时
- `yroll/harness/skills.py` — Skill 加载
- `yroll/ingest/jianying.py` — 剪映导入
- `yroll/ingest/asr.py` — 语音识别

### GUI
- `gui/src/App.tsx` — React 根组件
- `gui/src/components/*` — 9 个面板组件（Asset / Chat / Clip / MenuBar / Ops / Preview / Timeline / VisualAdjust / ClipWorkspace）
- `gui/src-tauri/src/main.rs` — Tauri 主进程

### Skills（SKILL.md）
- `skills/loudness-balance/`
- `skills/noise-reduction/`
- `skills/silence-cleanup/`
- `skills/watermark-removal/`

### 测试（pytest）
- 18 个 `test_*.py`，覆盖 audio / chat / core / harness / ingest / jianying / links / mcp / phase6 / problems / publish / render / server / silence / skills / subtitle / visual_adjust / ws。

### 模型
- `models/faster-whisper-small/` — faster-whisper small（ASR）
