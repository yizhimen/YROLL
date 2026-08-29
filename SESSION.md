# YROLL 项目进度（2026-08-29 重启 + GUI-01 完工）

## 当前状态
- **GUI-01（Session + Mutation Gate + Revision）已完整交付**（详见下"v0.2 GUI-01"）
- **GUI-02 Closure 02-1（Core 标准 NTSC DF）+ 02-2（TS mirror）+ 02-3（Source Timebase & Conformance）+ 02-4（ClipBlock Frame-Native Refactor）已完成**
- 工程：sanlihe-story（38 clip + 18 字幕 + 40 资产 + 91 op）
- Core v0.2 测试：466 passed + 1 skipped
- GUI 测试：140 vitest + Playwright 端到端冒烟通过

## v0.2 GUI-01 完工（2026-08-29）

按 `YROLL-Editor-Foundation-v0.2.md` §二（Batch 01：GUI Mutation Gate 接通）施工。

### 修改文件
- `gui/src/session.ts`（重写，~220 行）
- `gui/src/api.ts`（+~150/-~50 行）
- `gui/src/App.tsx`（+11 行 lifecycle useEffect；修一处裸 fetch）
- `gui/src/components/EditLease.tsx`（重写，~130 行；删 STORAGE_KEY/setInterval）
- `gui/src/gate.test.ts`（**新**，Vitest 16 用例）
- `gui/smoke/gui-01.mjs` + `gui/smoke/serve.mjs`（**新**，Playwright 端到端）
- `gui/vitest.config.ts`（**新**）
- `gui/package.json`（+vitest/jsdom/playwright devDeps + test script）
- `tests/test_gui_gate_contract.py`（**新**，pytest 11 用例）
- `yroll/server/app.py`（+CORS 中间件）
- `scripts/serve_gui.py`（+strip 304 请求头，+守护空 body）

### API contract 变化
新增：
- `api.uiStatus(clientKnownRevision?) -> /ui/status` 单调用顶栏真相源
- `api.heartbeatLease(sessionId) -> /lease/heartbeat` 续约（不再 release+re-acquire）
- `api.generateSubtitles(why) -> /subtitles/generate` 修 App.tsx 裸 fetch
- `GateRejection` 异常类（带 `kind: 'no_session'|'no_revision'|'lease_rejected'|'revision_conflict'`）
- `sessionStore.{acquire, release, handoffToAgent, refresh, startPolling, stopPolling, noteGateError, bumpRevision}`

变化：
- `api.mutate()` / `gated()` 现在**真的被调用**（之前 commit message 谎报"30+ 走 mutate()"，实际零调用点 → 静态护栏守住）
- `/chat` 同步带 sessionId + baseRevision 到 query + body（audit §6.5）
- `/assets/import` 走 `gated()`，FormData 不被强制 JSON content-type

### GUI → Core 调用链
```
App mount
  └─ sessionStore.initLocal()         ← 读 localStorage
  └─ sessionStore.startPolling()
       └─ setInterval(5s) tick:
            ├─ api.uiStatus()         ← /ui/status?client_known_revision=…
            ├─ heartbeatLease()       ← /lease/heartbeat (if mine)
            └─ acquire()              ← /lease/acquire (if free & !mine)
组件写操作 (api.trim/move/split/…)
  └─ mutate() / gated()
       ├─ 注入 sessionId + baseRevision 到 query
       ├─ 403 "sessionId required"  → noteGateError('no_session')
       ├─ 400 "baseRevision required" → 'no_revision'
       ├─ 403 "lease rejected"      → 'lease_rejected'
       ├─ 409 revision conflict     → 'revision_conflict'
       └─ 200 OK
            ├─ syncRevision()        ← /ui/status → bumpRevision()
            └─ return data
```

### Gate 失败时 GUI 行为
- 顶栏（EditLease）从 `🟢 编辑权：我 r<N>` 切到 `🔴`/`🟡`，附原始 `detail` 文案
- `conflict` 时出现"刷新"按钮
- `no_session` / `lease_rejected` 时出现"获取编辑权"按钮
- 不再静默：所有拒绝都看得见

### Revision conflict 行为
- `/ui/status?client_known_revision=stale` → actor="conflict"、conflict=true
- sessionStore 进 conflict 模式；`bumpRevision()` 收到自己成功的写就清零
- 自动 heartbeat 不抢别人 lease

### 自动测试（11 + 16 + 端到端）
- `tests/test_gui_gate_contract.py` 11 pytest：API 静态护栏 / 服务端契约 / chat+import gate / 4 个错误码文案
- `gui/src/gate.test.ts` 16 vitest：envelope 注入 + 错误分类 + chat 双重 gate + FormData + sessionStore 心跳/冲突/handoff 持久化
- `gui/smoke/gui-01.mjs` 端到端：Chromium 加载真实 dist，验"我 r<N>"、`api.setTrackHidden` 200、裸 fetch 403、stale 409

### Regression
- pytest 全部 317 passed（Core 306 不动 + 新 11）
- tsc 0 错
- vitest 16 passed

### 仍 Implemented / Not Verified
- 顶栏冲突/无 lease UI 文案 → 已用 vitest 测 store，未在浏览器中手测 release-then-acquire 抢拍节奏
- `pnpm dev` (Vite dev server) 路径未跑（生产 build 已通过，dev 模式应同）
- `scripts/serve_gui.py` 304 路径虽然修了，但 SimpleHTTPRequestHandler 本身在大量轮询下会 TIME_WAIT 累积，**建议下一个 batch 替换为 FastAPI static-files + 路由代理**

## v0.2 GUI-01.5 完工：跨进程 Project Authority

按 `GUI-01.5.md`（用户审阅补充：3-mode 启动 + actor_id resume + heartbeat 生命周期 + preview 只读 + handoff 事件 + sole-write 静态护栏）施工。

### 架构目标（达成）
`yroll serve <project>` 是该工程**唯一**的 Mutation Authority / ProjectCore owner。MCP 不再独立 `ProjectCore.open()` 写工程；改为 HTTP 客户端连到 `yroll serve`，所有 mutation 经 HTTP API → Mutation Gate → ProjectCore。MCP 写操作带 `sessionId + baseRevision`。Agent/Claude 的 lease 由 Project Server 持有，GUI/MCP 共享同一个 LeaseStore。Revision 由同一 ProjectCore 生成。

### 修改文件
- `yroll/core/lease.py`：EditLease 加 `actor_id`；LeaseStore 加 `by_actor` / `park_session` / `consume_parked` / `replace_session`；加 `require_capable()`
- `yroll/core/lease_events.py`（新）：LeaseEventLog ring，256 容量，since(seq) 用 `>=` 语义
- `yroll/server/app.py`：3 个新端点 `POST /session/ensure`（3-case actor_id resume）、`POST /lease/request`（纯读 may-I）、`GET /lease/events?since=N`；`/lease/handoff` 接受 `toActorId`；`/lease/acquire` 接 `actorId`；`/mutation/preview` 改 Gate-exempt（preview 本质只读）；现有 `/lease/*` 端点接 event log
- `yroll/mcp_http.py`（新）：urllib-only `YrollHttpClient`：`ensure_session` / `request_lease` / `mutate`（信封装） / `preview` / `read` / `events` / `heartbeat` / `release`；`GateRejection` 异常
- `yroll/server/mcp_server.py`：**彻底重写**。`__init__` 无 IO/线程/socket；新 `.start()`（ensure_session + 60s daemon heartbeat）和 `.shutdown(release=)`；mutation tool 在 non-EDIT 模式改走 `/mutation/preview`，结果包 `{"preview": True, "would_change": ...}`；`/clips/.../trim` 等 30+ 个 tool 全部改走 HTTP
- `yroll/cli/main.py`：`yroll mcp --server URL --actor-id ID`（必填 server，可选 actor_id 默认 claude-code）

### API contract 变化
| 端点 | 用途 | Gate |
|---|---|---|
| `POST /session/ensure` | 3-case actor_id resume + 拿 sessionId | exempt |
| `POST /lease/request` | "May I edit? Who holds?" 纯读 | exempt |
| `GET /lease/events?since=N` | 状态转换 ring | exempt |
| `POST /mutation/preview` | what-if | exempt（preview 本质只读） |
| `POST /lease/acquire` | 加 `actorId` 参数 | gated |
| `POST /lease/handoff` | 加 `toActorId` 参数 | exempt |

### GUI → Core → MCP 调用链
```
yroll serve <project>        # sole owner of ProjectCore + LeaseStore + LeaseEventLog
   │
   ├─ HTTP 8765: Mutation Gate (sessionId + baseRevision)
   │      ├─ /session/ensure, /lease/request, /lease/events
   │      ├─ /lease/acquire/release/handoff/heartbeat
   │      └─ /clips/* /tracks/* /subtitles/* /mutation/preview
   │
   ├─ GUI (5173 代理)            # sessionStore.ensure_session
   │      └─ mutate() /api.mutate() → 200 / 403 / 400 / 409
   │
   └─ MCP (stdio)                # McpServer.__init__() → .start() → serve_stdio
          ├─ ensure_session(actor=agent, actor_id=claude-code, intent=edit)
          │      3-case: 没人持 → auto-acquire; Human 持 → observe + park
          │      同 actor_id 重连 → resume (rotate sessionId)
          ├─ heartbeat daemon thread (60s tick, no-op on crash)
          └─ tool call → mutate(EDIT) / preview(OBSERVE/PROPOSE)
```

### 6+1+2+1 测试

#### 端点 (tests/test_session_ensure.py — 14)
- ensure 三种 case (auto-acquire / observe+park / resume 同 actor_id)
- 不同 actor 同时来 → observe
- intent=observe / propose 永远 observe
- 重复 ensure 同 actor → 轮换 sessionId
- handoff 后续 ensure 拿回 edit
- request_lease 三种状态
- events 起步空、累积、since 过滤、handoff 事件

#### 跨进程 (tests/test_mcp_cross_process.py — 6)
- A: Human 持 EDIT → MCP 写 → preview, no op, no state change
- B: handoff Human→Agent → MCP 写 → 成功, op in log
- C: Agent 持 EDIT → 第三方 HTTP mutation → 403, no state change
- D: stale baseRevision → 409, no silent overwrite
- F: lease 释放后 MCP re-ensure → 新 sessionId, mode=edit
- G: stale revision 重复拒绝, 零变更

#### 真实 MCP (tests/test_mcp.py — 8)
- 跑真 uvicorn 后端 + 真 McpServer 子线程;initialize/notification/tools_list/未知工具、读 path、edit flow、unknown clip isError、stdio 端到端

#### 进程恢复 (tests/test_mcp_resume_and_observe.py — 2)
- H: Human EDIT + Agent OBSERVE 并存 → Agent 看 /audit/since 看到 human 写;mutation tool 返 preview
- I: Agent A 持 EDIT, 模拟 crash (shutdown release=False), 同 actor_id 重连 → resume (新 sessionId);不同 actor 不会继承

#### 子进程 (tests/test_mcp_subprocess.py — 1, @slow)
- 两个真 `python -m yroll.server.mcp_server` 子进程 vs 一个真 `yroll serve` → 只有一个拿 EDIT

#### 静态护栏 (tests/test_no_writes_outside_server.py — 4)
- mcp_server.py 不许调 `ProjectCore(` / `.save_state(` / `CommandLayer` / 裸网络库
- 任何未来提交把 ProjectCore 写回 mcp_server.py → 立刻红

### Gate 失败时 GUI 行为 (与 GUI-01 一致,本批次无变化)
- 顶栏从 🟢 → 🟡 / 🔴
- 附原始 `detail` 文案
- 不再静默

### Revision conflict 行为 (与 GUI-01 一致)
- /ui/status 报 conflict=true, sessionStore 进 conflict 模式
- bumpRevision 收到自己成功的写就清零
- 自动 heartbeat 不抢别人 lease

### 关键实现细节
- **3-mode 启动**: nobody → EDIT; Human holds → OBSERVE + park; handoff → EDIT 提升
- **actor_id resume**: 同 actor_id 重连 (重启 Claude Code) → server 轮换 sessionId,旧 sid 死掉,无僵尸 owner
- **heartbeat 生命周期**: `__init__` 无 IO;`start()` 启 daemon 线程 (60s tick);`shutdown(release=True|False)` 显式控制;崩溃靠 TTL 恢复
- **preview 严格只读**: non-EDIT 模式 mutation tool 走 `/mutation/preview`,server 端 handler 不写 state,client 端 wrap `{"preview": True}`
- **handoff 事件**: ring buffer 256 事件,client 5s 轮询即感知 (vs 之前要等 heartbeat)
- **sole-write 静态护栏**: mcp_server.py 模块级禁止 ProjectCore 调用

### Implemented / Not Verified
- WebSocket push handoff 事件 → 留作未来优化(当前 HTTP polling 已够用)
- 真实多进程 lease race 的 OS-level 锁 → 走 OS 文件锁(maybe fcntl/msvcrt)留作后续 batch

### 架构债 (用户审阅要求记录)
- `_g_stores` keyed by `id(ProjectCore)` 是 process-local,reloads 不安全。LeaseStore 应逐步移到 `ProjectSession` 层由 Project Server 拥有,与 ProjectCore identity 解耦。本批次 out of scope。
- `save_state()` 非原子(op_seq 内存计数 race)。仍是单写者 (HTTP server),MCP 侧不可达。
- 三套并行 gate 实现 (middleware / `_check_rev` / WebSocket) 需合并。
- `/project/open` swap core 时 lease 被无声丢弃。
- `EditLease.base_revision` 不随 mutation 更新(GUI 已用 `/ui/status` 拿真值)。
- 非-Operation mutation (markers/beats) 不增 revision。

### Regression
- pytest **345 passed** (306+11 GUI-01 + 14 session_ensure + 8 test_mcp + 6 cross + 2 resume/observe + 1 subprocess + 4 static guard = 352;少了 7 个因旧 `test_mcp.py` 6 个被改写 + 老 test_mcp 改为新 API 后一些 assert 调整)
- vitest 16 passed (未触动)
- tsc 0 错
- Live smoke: 真实 yroll serve + yroll mcp 子进程 + 真实 JSON-RPC → op00093 落盘,who=human,state 改变 ✓

## v0.2 历史

### 已完成
- P0-10 EditLease（yroll/core/lease.py）
- P0-09 Project Revision (git filter-repo 已加, manual check)
- §29 Agent Contract (yroll/agent_contract.py)
- §28 Agent Action Audit Log + Semantic Timeline Diff
- §24-27 Lease Status / Conflict UI API（GET /ui/status）
- §13 Story / Beat Model
- P1: L1 Local Composite
- P1: Keyboard Editing keymap
- P1: Markers
- L0 Frame Preview
- Mutation Proposal API（Preview-Before-Commit）
- CLI: `yroll reality-test`

### 禁止中（per spec §十九）
- Frame-native Timeline（GUI-02）
- Selection 升级为 EditorSelection（GUI-03）
- Snap / History / Preview / Audio / Subtitle / Agent / Reality Test 批量

## 服务状态（保存时）
- 后端 8765：已 stop（任务结束）
- 前端代理 5173：已 stop
- 烟测用一次性 in-process Node 静态服务（5180）→ 不留后台

## 重要文件
- `YROLL-Editor-Foundation-v0.2.md`（**唯一施工依据**）
- `GUI_REALITY_AUDIT_v0.1.md`（上一轮静态审计，本次修的就是 §2.1 / §2.4 / §2.8）
- `tests/test_gui_gate_contract.py`（静态护栏，下次有人加 mutation 跳过 mutate() 立刻红）
- `gui/src/gate.test.ts` + `gui/smoke/gui-01.mjs`（动态验证）
- `gui/src/session.ts`（真源）
- `gui/src/api.ts`（信封闭装）

## 重启后第一句该问
- 验证 GUI-01 收尾后看哪个 batch？规范 §二 5 个 batch 中 Batch 02 = Revision/Conflict/Handoff UI
  （顶栏永久状态栏）—— 我已基本做完，但视觉细节（颜色、🟢/🟡/🔴 实测）需要你人眼确认
- 或者按 §三 时间直接进 **GUI-02：Frame-Native Timeline**

## 不要重复做的事
- 不要重写 EditLease.tsx 自己持有状态
- 不要在组件里写裸 fetch 写操作（静态护栏会红）
- 不要把 api.mutate() 删了或加旁路（11 个 pytest 用例会红）
- 不要让 chat 改回不传 sessionId（vitest 会红）
- 不要让 Commit message 写"X 已 done"除非同时报自动测试 + 端到端 + 回归三项


## 已完成（本会话累计 5 轮）
### 第 1 轮：基础架构
- YROLL Server + 8 轨默认 + 类型校验 + 重叠检测
- 30+ Command 实现 + Operation Log + Undo/Redo

### 第 2 轮：Reality Test
- 10 组基础测试：9 PASS / 1 PARTIAL / 0 FAIL
- 跨轨 Ripple + Redo 实现

### 第 3 轮：CapCut 基线 + UX 修复
- 视窗比例 16:9/9:16/1:1/4:3/3:4
- 完整字幕编辑器 + 预设库（5 字体 + 5 样式 + 5 转场 + 5 滤镜 + 5 音效 + 6 导出 + 5 视窗）
- 126/126 pytest 全过
- 修复老测试 3 个

### 第 4 轮：Sanlihe 短片
- 38 个 clip 排好（11 段视频 + Ken Burns + 淡入淡出）
- 18 旁白字幕
- 导出 90s MP4 / 720×1280 / 24fps
- YROLL-Sanlihe-Gap-Analysis-v0.1.md（缺口分析）

### 第 5 轮：UX 修复
- ✅ Play/Pause 按钮工作（内部 setInterval 推进 playhead）
- ✅ 9:16 视窗比例 letterbox 生效
- ✅ 字幕轨在 V 轨之上
- ✅ 0s 时间刻度从标签列右侧开始
- ✅ 隐藏按钮明确化
- **没有处理**：用户说 Play 按钮工作但点没反应，已修

## 服务状态（保存时）
- 后端 8765：sanlihe-story（38 clip / 40 资产 / 91 op log）
- 前端代理 5173：dist 静态 + API 代理
- 两者都跑着

## 重要文件
- YROLL-Editor-Foundation-Backlog-v0.1.md
- YROLL-Layer2-GUI-UX-Test-Protocol.md
- YROLL-Reality-Test-Report.md
- YROLL-Sanlihe-Gap-Analysis-v0.1.md
- SESSION.md（本文件）
- scripts/build_sanlihe.py（Sanlihe 短片构建脚本）
- scripts/serve_gui.py（5173 代理）
- scripts/reality_test.py（10 组测试）
- tests/test_phase_b_features.py（14 个 Phase B 测试）
- tests/test_cross_track_link.py（P0-1 + P0-6 测试）

## 服务启动命令
后端：
前端：（在 5173 代理）

## 用户的核心问题（重启后直接说这些）
1. Sanlihe 短片能做完吗？——能，v0.1 已导出
2. YROLL 与常用剪辑软件差距？——缺口分析有列，关键帧 + AI 图像生成最缺
3. OpenChatCut 借鉴？——源码在 ，MCP server 已识别，30+ 工具
4. **当前最想推进的**：
   - 接 OpenChatCut MCP（用户本机装了 OpenChatCut 0.2.10）
   - YROLL 抄 SQLite 持久化 + 关键帧
   - 短片继续完善（替换错的素材 / 加关键帧）

## 不要重复做的事
- 已做完的：基础剪辑 P0/P1、字幕、导出、UX 修复
- 不需要重做 P0-1 / P0-6 测试
- SESSION.md 已经有完整进度

## 重启后第一句该问
- 你 OpenChatCut 跑起来了吗？给我它的 MCP server URL，我接上监控
- 或者 YROLL 继续完善哪个功能（关键帧 / SQLite / 其他）

## v0.2 进展（编辑权 + 版本号）

### 已完成
- P0-10 Edit Lease（yroll/core/lease.py）
  - LeaseStore (per-project, thread-safe)
  - Mode (EDIT/PROPOSE/OBSERVE) + Actor (HUMAN/AGENT)
  - Acquire / Release / Heartbeat / Handoff
  - 5 min TTL, conflict detection
- HTTP API: GET /lease, POST /lease/{acquire,release,heartbeat,handoff}, /mutation/check
- /clips wrapped with require_edit_right
- 11 unit + HTTP tests pass
- GUI: <EditLease /> component shows 编辑权 status + handoff buttons

### 准备开始
- P0-09 Project Revision (git filter-repo 已加, manual check)
- P0-01 Frame First (核心)
