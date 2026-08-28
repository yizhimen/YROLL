# YROLL 项目进度（2026-08-28 重启前完整快照）

## 服务状态（保存时）
- YROLL 后端 8765（PID 25868，sanlihe-story 工程）
- YROLL 前端代理 5173（PID 1724）
- OpenChatCut 桌面端 + MCP 5199（用户本机，已提供 URL）

## 当前工程
- 名称：sanlihe-story（《他们拿着一幅假画，去寻找4000年前的人》）
- 资产：40 张图（高凤翰画 / 陶鬶 / 考古证据 / 甲骨 / 学者 / 古籍 / 地图 / 莲花）
- Clip：38（11 段 + Ken Burns + 淡入淡出）
- 字幕：18 旁白
- Op log：91
- v0.1 导出：projects/sanlihe-story/export/（90s MP4 + SRT + 封面 + 元数据）

## 已完成（本会话 5 轮）
1. **基础架构**：YROLL Server + 8 轨 + 类型校验 + 重叠检测 + 30+ Command
2. **Reality Test**：10 组 9 PASS / 1 PARTIAL / 0 FAIL
3. **CapCut 基线**：视窗比例 + 完整字幕编辑器 + 预设库 + 跨轨 Ripple + Redo
4. **Sanlihe 短片**：v0.1 已导出
5. **UX 修复**：Play/Pause 按钮 + 9:16 letterbox + 字幕轨在最上 + 0s 从标签右侧

## 重要文件
- YROLL-Editor-Foundation-Backlog-v0.1.md（6 项 P0 冻结）
- YROLL-Layer2-GUI-UX-Test-Protocol.md（10 个 GUI 测试剧本）
- YROLL-Reality-Test-Report.md（10 组基础测试）
- YROLL-Sanlihe-Gap-Analysis-v0.1.md（缺口分析）
- scripts/build_sanlihe.py（Sanlihe 短片构建脚本）
- scripts/serve_gui.py（5173 代理）
- scripts/reality_test.py（10 组测试）
- tests/test_phase_b_features.py（14 个 Phase B 测试）

## 服务启动命令
```bash
# 后端
cd D:\cc\YROLL
.venv\Scripts\python.exe -m yroll.cli.main serve projects/sanlihe-story --host 127.0.0.1 --port 8765

# 前端代理（5173）
.venv\Scripts\python.exe scripts/serve_gui.py

# OpenChatCut MCP（用户本机）
http://127.0.0.1:5199/api/external-mcp/mcp
```

## 用户的核心问题
1. Sanlihe 短片能做完吗？—— 能，v0.1 已导出，可细剪
2. YROLL 与常用剪辑软件差距？—— 缺口分析有列
3. OpenChatCut 借鉴？—— 源码在 参考/OpenChatCut-main/
4. **新方向**（2026-08-28 用户决定）：
   - 我接 OpenChatCut MCP（监控 + 粗剪）
   - 用户在 OpenChatCut 里细剪
   - 资源两边都用

## YROLL 当前 P0/P1 能力
P0 ✅：导入 / 拖动 / Trim / Split / Delete / 音视频同步 / 渲染 / 导出
P1 ✅：Ripple / 多选 / 锁定 / 吸附 / 多轨 / 音量 / 淡入淡出 / 画面变换 / 裁剪 / 字幕 / 快捷键
P1 ⚠️：框选多选 / 帧级精度
P2 ❌：关键帧 / 速度曲线 / Shot Factory / AI 图像 / Editorial Transition / Proxy
P3 ❌：Slip/Slide / Compound / 高级关键帧

## 不要再做的事
- 已修的：Play 按钮 / 视窗比例 / 字幕轨顺序 / 时间轴起点
- 已修的：类型校验 / 重叠检测 / 跨轨 Ripple / Redo
- 已写的：4 个 Backlog/Report 文档
- 不要重做 P0-1/P0-6

## 重启后第一句该问
- 你 OpenChatCut MCP 连上后看到了什么工程列表？
- 这次 Sanlihe 粗剪想从 OpenChatCut 端做还是 YROLL 端做？
- 或者 YROLL 抄 SQLite / 关键帧 / UI 缩放？
