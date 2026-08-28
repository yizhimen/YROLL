# YROLL 项目进度（2026-08-28 重启前完整快照）

## 当前状态
- YROLL 后端跑在 8765（PID 25868，最后工程 sanlihe-story）
- 前端代理在 5173（PID 1724）
- 工程：sanlihe-story（38 clip + 18 字幕 + 40 资产 + 91 op）
- v0.1 短片已导出：

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
