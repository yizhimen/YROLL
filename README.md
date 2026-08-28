# YROLL AI

> 泛来源素材与工程的人机共创视频生产平台——让一个人成为一支视频生产团队。

## 文档

- **`YROLL Editor Foundation v0.2.md`** — 唯一施工依据（架构状态 + P0 清单 + 目标形态）
- **`v0.2 Foundation Reality Audit → 精确补洞.md`** — 三轮审计的最终判断
- **`docs/manifest-v0.1.md`** — 内部统一对象模型规范

## 当前状态：Editor Foundation v0.2 — Core Complete ✅

**12/12 P0 + 5/5 P1 + 3 项 §29/§28/§13 完成。306 passed, 0 failed.**

完整状态见 `YROLL Editor Foundation v0.2.md` §37 P0 清单 + §38 P1 + §39 P2。

### 已实现的关键能力

#### P0 — Foundation (12/12)
| 层 | 能力 |
|---|---|
| P0-01 Frame Timebase | `Rational` / `FrameTime` / `FrameRange` 帧语义（24/25/30/29.97 fps） |
| P0-02 TimeMap | `TimeMap` 三层映射 source_frame ↔ clip_frame ↔ timeline_frame |
| P0-03 Selection | `Selection` 模型（single / multi / track / range）+ `move_selection` / `delete_selection` |
| P0-04 Mutation Engine | `CommandLayer` + `Operation` + Gate Middleware（46/46 endpoint enforced） |
| P0-04D Atomic Mutation | `replace_clip_voice` 一个用户意图 = 一个 Operation |
| P0-06 Snap Engine | `SnapEngine.snap()` 统一 snap（Clip/Subtitle/Word/Marker/Playhead） |
| P0-07 Mutation Preview | `POST /mutation/preview` 描述"操作将影响什么"，不 commit |
| P0-08 History API | `GET /history/state` + `POST /history/undo|redo`（外部统一接口） |
| P0-09 Revision | `Project Revision` + `check_project_revision()` |
| P0-10 Edit Lease / Handoff | `acquire` / `release` / `heartbeat` / `handoff` |
| P0-11 Gate 全覆盖 | `_MutationGateMiddleware` 强制 Lease+Revision on every non-GET mutation |
| P0-12 No Silent Overwrite | Mutation Gate + Chat Task gate（`task.run()` 也强制 Lease 检查） |

#### P1 — Pro Editing (5/5)
| 能力 | API |
|---|---|
| Slip / Roll / Slide | `cmd.slip_clip` / `cmd.roll_clip` / `cmd.slide_clip` |
| L0 Frame Preview | `GET /frame/preview?frame=N` |
| L1 Local Composite | `local_composite.resolve_composite_window()` + ffmpeg 指令 |
| Markers | `GET/POST/DELETE/PATCH /markers` |
| Keyboard Editing | `GET /keyboard/keymap` (J/K/L/I/O/Space/Delete/箭头) |

#### §28/§29/§13 — AI-native
| 能力 | 入口 |
|---|---|
| Agent Contract | `yroll.agent_contract.YrollAgent` |
| Mutation Proposal (Preview-Before-Commit) | `POST /proposals` + approve/reject |
| Semantic Timeline Diff | `yroll.core.diff.diff_projects()` / `diff_revisions()` |
| Story / Beat Model | `GET/POST/DELETE /beats` |
| Lease Status / Conflict UI | `GET /ui/status` (🟢我 / 🟡Claude / ⚪观察 / 🔴冲突) |
| Agent Action Audit | `GET /audit/since/{op_id}` / `/audit/last` |

### GUI 表现层（下一阶段）

文档 §11 明确指出 GUI 是 Foundation 收敛后的下一步。Core 已经支撑：
- 黄/灰状态条（"🟢 编辑权：我" / "🟡 编辑权：Claude"）
- AI affected 区域高亮（§26）
- Conflict dialog（§27）
- Keyboard 绑定（§34）
- Timeline diff 显示（§28）

## 使用

### 安装

```bash
uv venv && uv pip install -e . && uv pip install opencv-python-headless pytest
```

### 验证 Foundation v0.2

```bash
yroll reality-test
# → 14 passed (Test A-G: Frame/Basic Edit/Ripple/Split/Undo/Redo/Handoff/Conflict)
```

### Stage 0 理解管线（v0.1 仍可用）

```bash
yroll ingest <素材目录> --name <项目名> --goal "视频目标"
```

### v0.2 编辑内核 — 三种入口

```bash
# 1. HTTP server（GUI/外部 Agent 都通过它）
yroll serve <工程目录> --port 8765

# 2. MCP server（stdio，给外部 MCP Agent）
yroll mcp <工程目录>

# 3. Python API（直接集成）
python -c "from yroll.agent_contract import YrollAgent; ..."
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
# 306 passed, 0 failed
```

测试覆盖：
- **单元 (23+ 模块)**：Frame / TimeMap / Selection / Lease / Revision / Command / Timebase / Snap / Markers / Beat / Story
- **集成**：Mutation Gate（46/46 endpoint）、Atomic Mutation、Selection Mutation、Agent Contract、Audit
- **端到端**（v0.2 Reality Test）：Test A-G — Frame 帧率、Basic Edit、Ripple 传播、Split 关系、Undo/Redo、Human/Agent Handoff、Conflict 拦截

## 仓库历史文档

- `YROLL-Editor-Foundation-Backlog-v0.1` / Gap Analysis / Reality Test / 开发规划 等：保留为历史资料，**实现以 `YROLL Editor Foundation v0.2.md` 为唯一依据**。
- `v0.2 Foundation Reality Audit → 精确补洞.md`：三轮审计的最终判断。
