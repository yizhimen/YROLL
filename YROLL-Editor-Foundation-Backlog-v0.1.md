# YROLL Editor Foundation Backlog v0.1

> 状态：v0.1 冻结
> 来源：YROLL_Editor_Foundation_Gap_Analysis v0.1 §22-23 Reality Test 实测 + 补充 2 修订
> 验收标准：每项 P0 必须通过对应的 Reality Test 验证（Test B/F/E/G/I 全部从 PARTIAL 升到 PASS 才算完成）

---

## 0. 当前状态定性

| 层级 | 判断 | 说明 |
|------|------|------|
| Project Model | � | core/manifest.py + models.py 完整 |
| Manifest | 🟢 | 17 域 + Operation + Version 闭环 |
| **Command Layer** | **🟢** | 30+ Command 全部跑通（Layer 1 实测） |
| Render 基础能力 | 🟢 | 30s 成片 + 50 素材实测 OK |
| Harness 基础 | 🟢 | runtime.py + skills.py |
| Operation / History | � | 18 类语义撤销实测精确 |
| AI 接力 Current State | 🟢 | Test J：人改 0.7 + AI 改 speed 完整保留 |
| **基础 Timeline UI** | **🟡** | 组件存在，鼠标手感未实测 |
| **多轨语义联动** | **🔴** | ripple/move 不联动字幕/音频（Test B/F） |
| **字幕/音频跟随** | **🔴** | 剪掉 1.8s 后字幕不动（Test E） |
| **Preview 直接操控** | **🟡** | 命令 OK，拖拽框未实测（Test C） |
| **Timeline 精细交互** | **🟡** | Snapping / Zoom / Scrubbing 缺 |
| ASR / Transcript 稳定性 | 🟠 | Test E 出现 'Project' has no attribute 'transcripts' / tuple index out of range |
| **大素材性能** | **�** | 50 素材 65s，100/500 未实测（Test I） |
| 完整 NLE 基础体验 | 🟠 | Layer 2 GUI UX 完全缺 |

**结论**：脑（Manifest / Link / Harness / Current State / AI Continuity）已成形；手（Timeline / Trim / Move / Render / Transform / Audio / Subtitle）需补强。

---

## 1. P0 冻结项（必须先做，关系用户会不会回剪映）

### P0-1：跨轨 Ripple / Move（语义联动）
**对应 Reality Test**：B / F（当前 PARTIAL → 目标 PASS）
**现状**：`links.py` 已有 `RelationStrength` 模型（STRONG/MEDIUM/WEAK/INDEPENDENT），但 ripple_delete_clip / move_clip 未读 links，只收同轨。
**实现**：
- 在 `core/models.py` 增加 `Relationship { source_clip_id, target_clip_id, kind, strength, time_range }` 模型
- 在 `commands.py` 的 `ripple_delete_clip` 与 `move_clip` 里读所有 `Relationship`，按 `strength == STRONG` 联动 shift
- 默认规则：
  - Video↔Voice Strong
  - Video↔Subtitle Strong
  - Video↔SFX Medium（提示）
  - Video↔BGM Independent（不动）
**验收**：Test B 字幕起点确实被前移；Test F move 主轨后字幕/Voice 同步前移。

### P0-2：Subtitle / Voice / Video Strong Link 实际联动
**对应 Reality Test**：E（PARTIAL → PASS）
**现状**：generate_subtitles 落字幕 clip 时未自动建 Relationship。
**实现**：
- `generate_subtitles` 在创建每个字幕 clip 时，写入 `Relationship(target_clip_id=video_clip_id, strength=STRONG)`
- ripple/move 时根据 Relationship 自动 shift 字幕起点
**验收**：Test E 中 ripple 主轨后字幕自动前移。

### P0-3：真实 GUI Timeline 基础操作（Layer 2 测试）
**对应 Reality Test**：A / I（验证 GUI 而非仅 CLI）
**现状**：CLI/Command 全过，但 Tauri GUI 的鼠标手感未实测。
**实现**：
- 启动 `pnpm tauri dev` 真实运行
- 测试：拖 Clip、拉 Trim Handle、Split、Ripple Delete、多选、Shift/吸附、Timeline Zoom、Playhead、Track height、Scroll、Undo/Redo
- 重点：是不是"像剪辑软件"
**验收**：Layer 2 报告里所有基础操作标"顺手"，无"想回剪映"评语。

### P0-4：Preview Transform Box 直接操控
**对应 Reality Test**：C（PASS 但仅命令行层）
**现状**：`set_transform2d()` 命令 OK，但 Preview 框选/拖拽/旋转/实时预览未实测。
**实现**：
- React `PreviewPlayer.tsx` 加 Transform Box overlay
- 鼠标：选中 Clip → Preview 出 8 个 handle + 1 个旋转手柄
- 拖拽：缩放、移动、旋转
- 松手：调 `set_transform2d()` + 实时重渲染
- Undo 一键还原
**验收**：完整 7 步闭环顺畅，无卡顿，无错位。

### P0-5：完整 Trim / Split / Ripple 真实交互（GUI 层）
**对应 Reality Test**：A（Trim 端点实际未变化）
**现状**：CLI trim 命令存在，但 GUI Trim Handle 拉动手感未实测；Split/Ripple Delete 按钮/快捷键未确认。
**实现**：
- Timeline.tsx 加 Trim Handle（左/右各一个）+ hover 高亮
- S 键 split（已有快捷键但未实测）
- Shift+Del = Ripple Delete（缺）
- 帧级精确（不是秒级粗调）
**验收**：完整 Trim→Split→Ripple 链条在 GUI 1 分钟内完成。

### P0-6：Undo + Redo
**对应 Reality Test**：G（Undo PASS 但 Redo 未测）
**现状**：`core.revert()` 已实现，Undo 精确。Redo 没有。
**实现**：
- `core.redo()`：找到最近的 `revert:X` op，调用相同的 `_apply_inverse`（已是 Redo 语义）
- GUI：Ctrl+Z / Ctrl+Y 快捷键
**验收**：Test G 升级版：人改→AI 改→人改→Undo 3 次→Redo 3 次，最终状态 = 第三次人改。

---

## 2. P1（基础稳定后补）

7. Subtitle / Transcript 稳定性（修 Project.transcripts / tuple index 报错）
8. 音频轨编辑（音量/淡入淡出/波形）
9. BGM 独立时间关系（不随视频剪辑 move）
10. Track Selection / Lock / Mute / Solo
11. Snapping（吸附）
12. Timeline Zoom / Scrubbing（鼠标位置居中）
13. Proxy / Preview Cache
14. Autosave / Crash Recovery
15. Replace Asset

---

## 3. P2（增强）

16. Keyframe（位置/缩放/旋转/不透明度）
17. Transition（叠化/淡入淡出已 OK；wipe/slide/circlecrop 待补）
18. Mask（圆形/矩形/钢笔）
19. 基础效果（亮度/对比度/饱和度/色温/锐化已 OK；模糊/锐化高级参数）
20. 完整 Audio Mix（多轨混音 / BGM Ducking）
21. 多平台序列（不同发布平台自动适配）

---

## 4. 暂时冻结（不要扩）

- 成品反推（Final → Project Memory）
- 复杂对象分层（角色/道具/场景对象模型）
- 复杂 Story Layer（剧本→分镜→生成完整闭环）
- 大规模旧工程兼容（Premiere / Final Cut / DaVinci 反向工程）
- 高级 AI 导演（多 Agent 协同）
- 模板生态
- 社区

---

## 5. 验收总表

| ID | 项 | Layer 1 (Command) | Layer 2 (GUI UX) | 状态 |
|----|----|-------------------|------------------|------|
| P0-1 | 跨轨 Ripple/Move | Test B/F → PASS | "字幕自动跟着走" | � 待做 |
| P0-2 | Subtitle Strong Link | Test E → PASS | "剪完字幕自动对齐" | 🔴 待做 |
| P0-3 | GUI 基础操作 | — | Layer 2 全过 | 🔴 待做 |
| P0-4 | Preview Transform | Test C 已 PASS | "框选→拖→缩放→旋转→预览" | 🟡 部分 |
| P0-5 | Trim/Split/Ripple 交互 | Test A 已 PASS | "拖 Trim Handle" | 🟡 部分 |
| P0-6 | Undo + Redo | Test G 已 PASS (Undo) | "Ctrl+Z/Y 闭环" | 🟡 部分 |

**完成定义**：6 项 P0 全部 🟢 才算 Phase A 完结，可进入 Phase B（AI Co-editing）。

---

## 6. 30 分钟真实任务测试（Layer 2 增强版）

**场景**：5 个手机视频 + 10 张照片 + 1 段口播 + 1 段 BGM + 1 份商品资料 → 30~45 秒产品短视频

**流程**：
1. 不开 AI，纯手动完成基础版本（记录步骤数）
2. AI 修改 3 次
3. 人工修改 3 次
4. AI 继续
5. 导出

**记录字段**：
- 花了多少步骤
- 哪一步卡
- 哪一步想回剪映
- 哪一步操作不自然
- 哪一步需要 AI
- 哪一步 AI 反而添麻烦

**判定**：30 分钟内完成，且 0 次"想回剪映"，才算通过。
