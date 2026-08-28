# YROLL GUI Reality Audit v0.1

> 本文为静态审计（未实际启动 GUI）。本机为 Windows Server headless 环境，
> 无法运行 React/Tauri GUI 做端到端 Reality Test。
> 本审计**只回答 GUI 是否真用 Core + 哪些操作实际可达**，不修代码。

---

## 0. 一句话结论

**YROLL Core v0.2 已经完整（306 passed），但 GUI 是相对独立的"传统编辑器"层，
并未真正接入 v0.2 Core 的大部分新增能力。** 这是文档 §7 的典型风险：

```
             Core v0.2  ✅
                ▲
                │
          MCP / Agent
                │
                │
GUI ────────────┘   ← 自己的旧逻辑
   ↓
- 用 seconds 而非 frames
- 不走 mutation gate
- 不消费 history/state/undo API
- 不显示 beat/marker/lease status UI
- 不用 Keyboard Editing keymap
```

修这一层所需工作 ≈ 重新设计 GUI，否则 YROLL 仍然"功能很多但实际是旧剪辑器"。

---

## 1. 文件清单（GUI 总规模：3927 行 TypeScript/React）

| 文件 | 行数 | 职责 |
|---|---|---|
| App.tsx | 1311 | 顶层编排 + 几乎所有键盘快捷键 + 大半 mutation 调用 |
| api.ts | 296 | HTTP 客户端 |
| Timeline.tsx | 288 | 时间线渲染 |
| PreviewPlayer.tsx | 271 | 预览窗 |
| ClipBlock.tsx | 265 | 单个 clip 块渲染 |
| ChatPanel.tsx | 240 | Chat Agent 面板 |
| ClipWorkspace.tsx | 237 | clip 工作区（Problem/Solution/History） |
| VisualAdjustPanel.tsx | 147 | 视觉调整面板 |
| SubtitleEditor.tsx | 182 | 字幕编辑 |
| ExportPanel.tsx | 145 | 导出 |
| AssetPanel.tsx | 133 | 素材面板 |
| EditLease.tsx | 126 | **仅这个文件**消费 Lease |
| OpsPanel.tsx | 79 | 操作历史 |
| ResizeHandle.tsx | 66 | 分界线拖动 |
| MenuBar.tsx | 141 | 菜单 |

---

## 2. 关键发现

### 2.1 🔴 Mutation Gate 完全未走

所有 mutation 直接 `POST /clips/{id}/trim` / `/move` / `/split` / `/speed` / `/volume` 等，
**未带 sessionId/baseRevision**。

证据：`gui/src/api.ts` 里所有 mutation 函数签名都没有 `sessionId` / `baseRevision` 参数。
仅 `acquireLease` / `releaseLease` / `handoffLease` 用了 lease（仅 `/lease/*` 豁免）。

**后果**：GUI 端可以绕过 Core 的 Lease + Revision 守卫。
但因为 Core `_MutationGateMiddleware` 是全局的（`_STATE["default"]`），
Core 端会拒。所以 GUI 操作会**全部 403/400**，但 GUI 没有传所以默默失败。

这是文档 §6.1 的真实回归：Core 修了，GUI 没接。

---

### 2.2 🔴 Timeline 是纯 seconds 编辑器（§11 §III 关键判断）

证据：`gui/src/components/Timeline.tsx:43,53,80,83,90,156,159,167,168` 全部以
`pxPerSec` 计算位置：
```
const width = duration * pxPerSec + 40;
const left = 110 + playhead * pxPerSec;
const anchorTime = mouseX / pxPerSec;
```

而 ClipBlock.tsx:54-55,66 用 `tlStart * pxPerSec` / `tlEnd * pxPerSec` 渲染。
显示的文字也是 `clip.source_range.start.toFixed(1)`（秒）。

**文档 §11 III** 的判断 **完全成立**——Timeline 还是"秒编辑器"：
- ❌ 没有 00:00:00:00 时间码
- ❌ 最后两位 Frame 显示
- ❌ ← → 是 0.1s 而非 1 frame
- ❌ Shift+← 是 1s 而非 10 frames
- ❌ SnapEngine 完全没接（Core 已有 P0-06，GUI 0%）

### 2.3 🔴 键盘快捷键以 seconds 为单位（§34）

App.tsx:212-227：
- J = -5 秒（文档要求 -1 frame）
- L = +5 秒（文档要求 +1 frame）
- ArrowLeft/Right = ±0.1 秒（文档要求 ±1 frame）
- Shift+Arrow = ±1 秒（文档要求 ±10 frames）

而且没用 Core 的 `keyboard.describe_keymap()`——纯散落在 onKey handler 里。

### 2.4 🟡 EditLease 组件实现了但连接不完整

EditLease.tsx 实现了 UI 状态条 + handoff + release + take-back，
但**EditLease 没有把 sessionId 传给其它 mutation 调用**。

而且 Effect 的 polling (line 41-52) 每 5 秒会重复 `releaseLease` 然后 `acquireLease`，
逻辑看起来试图保持 lease alive，但有 race condition（line 43-50 在 lease 是自己时 release）。

### 2.5 🔴 Story/Beat/Marker 完全未在 GUI 出现

Core 已有：
- `POST /beats` / `GET /beats` / 完整 StoryBeat 模型
- `POST /markers` / `GET /markers`

GUI 没消费：搜索 `gui/src/**/*.tsx` + `gui/src/*.ts` 全无 marker/beat 调用。

### 2.6 🔴 Preview/Impact/Diff/Audit 完全未在 GUI 出现

Core 已有：
- `POST /mutation/preview` (P0-07)
- `POST /proposals` + approve/reject (Preview-Before-Commit)
- `GET /ui/status` (Lease status + conflict detection)
- `GET /audit/since/{id}` / `/audit/last`
- `yroll.core.diff.diff_projects` / `diff_revisions`

GUI 没消费这些 endpoint。
唯一消费 `/impact` 的是 ClipWorkspace.tsx（Pending Delete 弹窗），
但只查 `op=remove` 的影响——不消费 `preview_mutation` 的 selection+op+params 全套。

### 2.7 🔴 History API 未消费

Core 已有：
- `GET /history/state` (can_undo, can_redo)
- `POST /history/undo` / `/history/redo`
- `POST /revert` (旧的 op-id 形式)

GUI 操作历史：
- App.tsx 应该有 undoLast/redoLast——但是用 `api.revert(operationId)` 旧形式
- OpsPanel.tsx 显示 ops 列表（只读）

未见消费 `/history/state` —— 没法直接禁用 Undo 按钮当 `can_undo=false`。

### 2.8 🔴 Chat Agent 不传 sessionId

ChatPanel.tsx:109 调用 `api.chat(text, selectedClip, playhead)`。
但 api.ts:109 的 chat 函数签名没传 sessionId/baseRevision。
所以 Chat 路径走 Chat Agent Gate 时也会被 Core 拒（因为没 sessionId）。

—— 这条 Core 端 Gate 工作，但** GUI 用户根本无法让 Chat Agent 工作**。

### 2.9 🔴 Frame Native UI 元素全无

没有：
- 帧级时间码显示（00:00:00:00）
- 帧级 zoom
- 帧级 snap
- 帧级 trim 把手（仅 seconds-based 拖动）
- 帧级 ripple 反馈
- 帧级 in/out 点（虽然 state 有 inPoint/outPoint，但只是 seconds 数值）

### 2.10 🟡 Selection 模型未真正接 P0-03B

App.tsx 有 `selectedSet`（multi），但 mutation 路径仍以单 clip 为主：
- `api.trim(clipId, ...)` 接单 clip
- `api.removeClip(clipId, ripple)`
- 没有 `moveSelection` / `deleteSelection` 调用

测试 GUI 操作时：
- 选多 clip → 按 Delete 实际只删一个？
- 或根本不允许多选删除？

文档 §4 P0-04B 明确要求："**不能退化成 `for clip_id: move_clip(...)`**"——看 api.ts 是单 clip 形式。

---

## 3. 缺失的传统剪辑操作

文档 §36 列了 Reality Test 必须能完成 17 步：

| 操作 | Core | GUI | 人类可达？ |
|---|---|---|---|
| 打开工程 | ✅ | ✅ MenuBar | ✅ |
| 导入素材 | ✅ `/assets/import` | ✅ AssetPanel | ✅ |
| 浏览素材 | ✅ | ✅ AssetPanel | ✅ |
| 拖入时间线 | ✅ `/clips` | ✅ AssetPanel → Timeline | ✅ |
| 播放 | ✅ | ✅ PreviewPlayer | ✅ |
| 暂停 | ✅ | ✅ | ✅ |
| 逐帧 | ✅ Core | 🔴 (J/L=5s, 不是 1 frame) | ❌ |
| 定位 | ✅ | 🟡 (search-transcripts 但只能搜到后跳) | 🟡 |
| 选中 | ✅ | ✅ | ✅ |
| 移动 | ✅ | ✅ (拖动) | ✅ |
| Trim | ✅ `/trim` | ✅ ClipBlock handle | ✅ |
| Split | ✅ `/split` | ✅ | ✅ |
| 删除 | ✅ | ✅ Delete 键 | ✅ |
| Ripple Delete | ✅ `/clips/{id}?ripple=true` | 🟡 (有 flag，但 UI 不明示 ripple) | 🟡 |
| Undo | ✅ `/revert` | ✅ Ctrl+Z | ✅ |
| Redo | ✅ `/revert` | ✅ Ctrl+Shift+Z | ✅ |
| 加字幕 | ✅ | ✅ | ✅ |
| 调音频 | ✅ `/volume` | ✅ | ✅ |
| B-roll | ✅ `/clips` | 🟡 (拖动 asset 到轨道，但无 PiP 视觉) | 🟡 |
| 转场 | ✅ | ❌ | ❌（仅在菜单，未 wire） |
| 预览 | ✅ `/render` | ✅ | ✅ |
| 导出 | ✅ `/export/package` | ✅ ExportPanel | ✅ |

---

## 4. GUI 现状 vs 文档 §7 目标架构

文档目标：
```
                  GUI
                   │
                   ▼
             Selection
                   │
                   ▼
             Mutation API
                   │
                   ▼
            Mutation Engine
                   │
       ┌───────────┼───────────┐
       ▼           ▼           ▼
   Timeline     History     Revision
       │
       ▼
  Relationship
       │
       ▼
    Renderer
```

GUI 实际：
```
GUI ──→ HTTP API（部分 endpoint）
        ↓
    CommandLayer（直接走，绕过 Gate）
        ↓
    ProjectCore（save_state）
```

**GUI 没经过 Mutation Engine 的 Selection 层**（api.ts 的 mutation 是按
single clip_id 而非 Selection 对象）。
**GUI 没消费 Revision / Lease（除 EditLease.tsx 自身）**。
**GUI 完全不消费 History API**。

---

## 5. 真实可执行操作（人工可达）

| 操作 | 状态 |
|---|---|
| 导入 mp4 | ✅ AssetPanel 拖入 |
| 看波形 | ✅ AssetPanel |
| 加到时间线 | ✅ 拖到 Timeline |
| 拖动 clip 移动 | ✅ 拖 |
| Trim handle | ✅ 左右 handle |
| Split (Ctrl+D?) | ✅ Ctrl+D 复制；split 是别的 |
| Delete | ✅ Delete 键 |
| Ctrl+Z/Y | ✅ Undo/Redo |
| 加字幕 | ✅ SubtitleEditor |
| 配音 | ✅ TTS voice-replace |
| 调音量 | ✅ VisualAdjustPanel |
| 关键帧拖动 | ❌ 没有 |
| PiP Transform | ✅ VisualAdjustPanel |
| 转场 fade/dissolve | ❌ 仅有菜单，未 wire |
| Markers | ❌ 无 UI |
| Story Beats | ❌ 无 UI |
| Mutation Preview | ❌ 无 UI（点删除才有 impact 弹窗） |
| AI Affected 高亮 | ❌ 无 |
| Conflict Dialog | ❌ 无（GET /ui/status 已实现） |
| 逐帧 ← → | ❌ (0.1s 而非 1 frame) |
| Snap 吸附 | 🟡 snapMode state 但没消费 SnapEngine |
| Search transcripts | ✅ MenuBar 搜索框 |

---

## 6. 结论与建议

按文档 §11 "GUI 表现层（下一阶段，不是现在）" —— 本审计确认了核心问题：

**Core v0.2 完整，GUI 落后一整个 v0.2 时代。**

最严重的 5 件事：
1. 🔴 Mutation Gate 在 GUI 端完全没接（API 调用不带 sessionId）
2. 🔴 Timeline 是 seconds 编辑器（无 frame 概念）
3. 🔴 键盘快捷键以 seconds 为单位（无 frame 概念）
4. 🔴 Selection 模型未真正走 multi-clip mutation
5. 🔴 Chat Agent 不传 sessionId，GUI 用户实际不能用 Agent

修复优先级（按文档 §3 P0-04A "先不要碰 Frame，先修 Gate"）：
1. 让 `api.ts` 每个 mutation 函数自动注入 sessionId + baseRevision（来自 EditLease.tsx 的 localStorage）
2. 让 ChatPanel 调用 `/chat` 时也传 sessionId
3. 接入 Core 的 `keyboard.describe_keymap()`（不再散落 onKey）
4. Timeline 引入 frame 显示（00:00:17:18 时间码）
5. 接入 `/ui/status` 让 GUI 知道 conflict 状态
6. 接入 `/history/state` 禁用按钮

按文档 §11：这些是 **GUI Milestone GUI-01 / GUI-02 / GUI-03** 的工作。
按文档 §8 末："**先不要修。**"——本文档先产出 audit，等用户决定优先级。
