# YROLL AI

> 泛来源素材与工程的人机共创视频生产平台——让一个人成为一支视频生产团队。

## 文档

- **`YROLL Editor Foundation v0.2.md`** — 唯一施工依据（架构状态 + P0 清单 + 目标形态）
- **`v0.2 Foundation Reality Audit → 精确补洞.md`** — 三轮审计的最终判断
- **`docs/manifest-v0.1.md`** — 内部统一对象模型规范

## 当前状态：Editor Foundation v0.2 — Mutation Integrity Phase

Core / Commands / Server / MCP / GUI / Selection / Frame API / Lease /
Revision / Render + 二十多个测试模块 + 222 passing tests。

完整状态见 `YROLL Editor Foundation v0.2.md` §37 P0 清单（11/12 已完成）。

### 已实现的关键能力

| 层 | 能力 |
|---|---|
| P0-01 Frame Timebase | `Rational` / `FrameTime` / `FrameRange` 帧语义（24/25/30/29.97 fps） |
| P0-02 TimeMap | `TimeMap` 三层映射 source_frame ↔ clip_frame ↔ timeline_frame |
| P0-03 Selection | 单一 `Selection` 模型（single / multi / track / range） |
| P0-04 Mutation Engine | `CommandLayer` + `Operation` + `Selection`-aware `move_selection` / `delete_selection` |
| P0-04D Atomic Mutation | `replace_clip_voice` 一个用户意图 = 一个 Operation |
| P0-07 Mutation Preview | `POST /mutation/preview` 描述"操作将影响什么"，不 commit |
| P0-08 History API | `GET /history/state` + `POST /history/undo|redo`（外部统一接口） |
| P0-09 Revision | `Project Revision` + `check_project_revision()` |
| P0-10 Edit Lease / Handoff | `acquire` / `release` / `heartbeat` / `handoff` |
| P0-11 Gate 全覆盖 | `_MutationGateMiddleware` 强制 Lease+Revision on every non-GET mutation |
| P0-12 No Silent Overwrite | Mutation Gate + Chat Task gate（`task.run()` 也强制 Lease 检查） |

## 使用

### Stage 0 理解管线（仍可用，v0.1 spike）

素材 → AI 理解 → Project Memory：

```bash
uv venv && uv pip install -e . && uv pip install opencv-python-headless pytest

python -m yroll.cli.main ingest <素材目录> --name <项目名> --goal "视频目标"
```

### v0.2 编辑内核

```bash
# 启动 HTTP server（GUI/MCP/Agent 都通过它）
yroll serve <工程目录> --port 8765

# 或者：
python -m yroll.server.app serve <工程目录>
```

LLM 配置（BYOK，OpenAI 兼容 API）：

```bash
export YROLL_API_KEY=...
export YROLL_BASE_URL=https://...     # 可选
export YROLL_TEXT_MODEL=gpt-4o-mini   # Chat 任务
```

## 测试

```bash
python -m pytest tests/ -q
# 222 passed, 1 unrelated failure (pyscenedetect API drift)
```

测试覆盖：
- 单元：Frame / TimeMap / Selection / Lease / Revision / Command / Timebase
- 集成：Mutation Gate（46/46 endpoint）、Atomic Mutation、Selection Mutation
- 端到端（v0.2 Reality Test）：Test A-G — Frame 帧率、Basic Edit、Ripple 传播、Split 关系、Undo/Redo、Human/Agent Handoff、Conflict 拦截
