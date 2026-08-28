# YROLL Editor Foundation Gap Analysis v0.1

> 目的：建立 YROLL 基础剪辑能力的统一检查框架。
>
> 本文不是“剪映功能复制清单”，也不是最终 Backlog。
> 它首先回答：**不用 AI，YROLL 能不能独立、顺手、可靠地完成一条普通视频；如果不能，具体弱在哪里。**
>
> 当前版本：v0.1  
> 基于：2026-08-25 当前 YROLL 项目结构快照  
> 后续：由本地 Claude Code 在真实 GUI / 真实素材上补充实测证据，再合并为 `YROLL Editor Foundation Backlog v0.1`。

---

## 1. 评估原则

### 1.1 第一性问题

> **用户能不能不离开 YROLL，完成一条正常的基础视频，并且不会因为基础编辑能力太弱而回到剪映？**

### 1.2 不以“功能数量”评价

不统计“有多少按钮”，而评价：

- 能否完成任务
- 操作路径是否自然
- 是否精确
- 是否稳定
- 是否可撤销
- 是否符合视频剪辑的基本心智模型
- 是否能在没有 AI 的情况下继续工作
- AI 是否是在基础编辑能力之上提供增量价值

### 1.3 “够用即可”原则

基础编辑不追求一开始达到 Premiere / DaVinci 的专业深度。

但必须达到：

> **普通创作者不会因为基础剪辑能力不足而必须回剪映。**

### 1.4 AI 不应替代基础 Editor Core

AI 可以：

- 建议
- 自动执行
- 解释
- 批量处理
- 解决复杂问题

但基础动作必须有确定性的人工路径。

### 1.5 评估必须以真实任务为中心

一个功能即使代码中存在，也不意味着“已够用”。

例如：存在 `Timeline.tsx` 只能证明有 Timeline 组件，不能证明拖拽、Trim、Ripple、Snapping 等体验已经成熟。

---

# 2. 状态定义

| 状态 | 定义 | 处理原则 |
|---|---|---|
| ✅ A 已够用 | 真实任务稳定完成，体验已达到当前目标 | 暂不投入 |
| 🟡 B 可用但弱 | 能完成，但明显慢、笨、容易误操作 | 高优先级优化候选 |
| 🟠 C 有骨架未成型 | 数据/组件/接口存在，但端到端体验未成立 | 补齐垂直链路 |
| 🔴 D 缺失 | 基础任务无法完成 | 基础能力优先补 |
| ⚪ E 暂不需要 | 对当前目标不是必要能力 | 不进入 MVP |
| ❓ U 待实测 | 代码存在，但没有真实操作证据 | Claude Code 实测 |

另设一个独立维度：

### AI 依赖程度

| 标记 | 含义 |
|---|---|
| L0 | 完全确定性/本地，无 AI 依赖 |
| L1 | 可选本地 AI |
| L2 | 需要服务器/远程 AI 才能显著提升 |

原则：**基础编辑尽量 L0 可完成。**

---

# 3. 总体能力地图

```text
Editor Foundation
│
├── A. Project / Media Ingestion
├── B. Asset Management
├── C. Timeline Fundamentals
├── D. Clip Editing
├── E. Multi-track / Relations
├── F. Preview / Selection
├── G. Audio Editing
├── H. Subtitle / Text
├── I. Transform / Visual Basics
├── J. Speed / Timing
├── K. Effects / Transitions
├── L. Keyframe / Animation
├── M. Undo / Redo / History
├── N. Project Reliability
├── O. Render / Export
├── P. Performance / Large Projects
└── Q. Human-AI Command Boundary
```

---

# 4. A. Project / Media Ingestion

## A1. 导入单个视频

目标：MP4 / MOV 等常见视频能稳定进入项目。

检查：
- 拖入
- 文件选择器
- Metadata
- 缩略图
- 时长
- FPS
- 分辨率
- 音频是否存在

## A2. 批量导入多个文件

## A3. 拖入整个文件夹

## A4. 图片 / 视频 / 音频混合导入

## A5. 导入失败的可解释提示

## A6. 重复素材识别

## A7. 素材缺失 / Offline Media 状态

## A8. 外部盘 / 路径变化后的恢复

### 现有架构证据
当前已有 `ingest/scanner.py`、`ingest/jianying.py`、`ingest/asr.py` 等导入相关模块，并已有 `resolver.py`，说明导入与素材恢复已有结构基础。fileciteturn0file0L46-L56

### Claude Code 实测任务
> 新建项目 → 拖入 10 个视频 + 10 张图片 + 2 个音频 → 检查是否全部正确入库、排序、预览、拖入 Timeline。

---

# 5. B. Asset Management

## B1. 素材库缩略图
## B2. 视频快速预览
## B3. 搜索 / 筛选
## B4. 素材标记 Favorite / Reject
## B5. 素材文件路径显示
## B6. 素材重新定位 / Relink
## B7. 素材 MD5 / Identity
## B8. 原素材与代理素材关系

### 当前结构证据
项目数据目录已有 `media/`、`cache/`、缩略图与波形缓存，以及 `resolver.py` 和 `store.py`，说明 Asset Identity / Cache / Resolver 的基础已经存在。fileciteturn0file0L104-L129

### 必须实测
> 素材移动到另一个文件夹 → 重开项目 → YROLL 是否能找到并自动重新关联。

---

# 6. C. Timeline Fundamentals

这是当前最重要的类别之一。

## C1. Timeline 横向滚动
## C2. Timeline 缩放
## C3. Playhead 拖动
## C4. 精确到帧的定位
## C5. Clip 拖动
## C6. Clip 左右 Trim
## C7. Split / Blade
## C8. Delete
## C9. Ripple Delete
## C10. Gap / 空洞处理
## C11. Snapping
## C12. 多选
## C13. Copy / Paste
## C14. Duplicate
## C15. Clip 边界视觉反馈
## C16. Track 高度调整
## C17. Track 锁定 / 隐藏

### 强制判断
如果 C1～C11 有明显问题，优先级高于绝大多数高级 AI 功能。

### Claude Code 实测任务
> 10 个 Clip 连续排列 → 删除第 4 个 Clip 的中间 2.0 秒 → 后续内容准确左移 → 关联字幕 / 音频不产生错误 → Undo → Redo。

---

# 7. D. Clip Editing

## D1. Select
## D2. Move
## D3. Trim
## D4. Split
## D5. Ripple Delete
## D6. Replace Asset
## D7. Delete
## D8. Duplicate
## D9. Freeze Frame
## D10. Compound / Group / Nest（后期）

### 关键判断
普通编辑区与 AI Context 区是否已经符合我们之前确定的双区域设计。

### YROLL 特别要求
- 普通编辑区域的操作应该与普通 NLE 一样自然。
- 点击 AI Context 区才进入 Clip Workspace。
- 普通拖动 Clip 应该仍然表示 Move，而不是触发 AI。

---

# 8. E. Multi-track / Media Relations

## E1. 多视频轨
## E2. 多音频轨
## E3. 字幕轨
## E4. SFX 轨
## E5. BGM 轨
## E6. Track Lock
## E7. Track Hide
## E8. Track Height
## E9. Clip Linking
## E10. Semantic Link 显示
## E11. Ripple 后相关对象同步

### 重点
不要把 Semantic Link 与传统“Link/Unlink”混为一谈。

需要验证：

```text
Video
 ↕ Strong
Voice
 ↕ Strong
Subtitle
 ↕ Medium
SFX
 ↕ Weak
BGM
```

在实际编辑时是否真的能做到：

> 改必要的，不改不必要的。

### UI 实测
- 默认轨道全部存在
- 当前工作的轨道变宽/突出
- 关联线不满屏乱飞
- 选中对象后才显示必要关系

---

# 9. F. Preview / Spatial Editing

这是 YROLL 的重点能力，也是 V1 不应遗漏的能力。

## F1. 稳定播放
## F2. 暂停 / 播放 / 帧步进
## F3. 时间选择
## F4. Preview 空间框选
## F5. 多框选
## F6. 框编号
## F7. Move
## F8. Scale
## F9. Rotation
## F10. Bounding Box
## F11. Spatial Feather
## F12. Temporal Feather
## F13. Before / After
## F14. 左右 / 上下对比

### 强制原则
Preview 框选不是“高级功能”，而是 YROLL AI-native 局部编辑的基础交互，应在 V1 验证。

### Claude Code 实测任务
> 选择 Clip 的 2.1–4.3 秒 → Preview 框选茶壶 → 拖动 / 缩放 / 旋转 → 调整羽化 → Preview Before/After → 应用。

---

# 10. G. Audio Editing

## G1. 音量
## G2. 局部音量
## G3. Fade In / Out
## G4. Gain
## G5. Waveform
## G6. Mute
## G7. Audio Split
## G8. Audio Move
## G9. 音视频分离
## G10. 音频跟随 Clip
## G11. 局部羽化
## G12. 基础降噪
## G13. Loudness Normalization
## G14. BGM Ducking
## G15. 外部音频导入

### 重点验收
> 只把某一句口播的 1～2 秒调大，不能破坏前后声音。

### 当前结构证据
已有 `audio_tools.py`，并已有 `loudness-balance`、`noise-reduction`、`silence-cleanup` 等 Skills，说明音频高级层已经开始建设。fileciteturn0file0L63-L67 fileciteturn0file0L93-L101

下一步重点应从“再增加 Skill”转向：**这些能力能否在 Timeline 上自然操作。**

---

# 11. H. Subtitle / Text Foundation

## H1. 手动新增字幕
## H2. 修改字幕文字
## H3. 删除字幕
## H4. 字幕移动
## H5. 字幕时长调整
## H6. 字幕样式
## H7. 字幕轨
## H8. 自动字幕
## H9. Word-level timestamp
## H10. Subtitle ↔ Voice Link
## H11. 字幕随剪辑自动重映射
## H12. 字幕遮挡检测
## H13. 批量统一样式

### 强制场景
> 剪掉 1.8 秒口播后，逐字字幕是否自动正确移动？

> 改一个词后，字幕宽度变化会不会破坏版式？

当前已有 `transcripts.py`、`asr.py` 以及字幕/波形测试文件，说明基础设施已有一定覆盖，但真实 GUI 体验必须单独验证。fileciteturn0file0L43-L56 fileciteturn0file0L160-L164

---

# 12. I. Transform / Visual Basics

## I1. Position
## I2. Scale
## I3. Rotation
## I4. Crop
## I5. Opacity
## I6. Fit
## I7. Fill
## I8. Mirror / Flip
## I9. Basic Brightness
## I10. Basic Contrast
## I11. Saturation
## I12. Local Adjustment

### YROLL重点
普通变换必须 L0 可完成；AI 只是进一步理解“用户想把它怎么变”。

已有 `VisualAdjustPanel.tsx`，同时有 `test_visual_adjust.py`，说明该方向已有实现，但需要真实体验验证。fileciteturn0file0L77-L85 fileciteturn0file0L162-L164

---

# 13. J. Speed / Timing

## J1. Speed up
## J2. Slow down
## J3. Constant speed
## J4. Speed curve（后期）
## J5. Reverse
## J6. Freeze
## J7. Frame interpolation（后期）
## J8. Time remapping 对字幕/音频的影响

### 重点
基础变速首先要稳定；高级速度曲线不是第一优先级。

---

# 14. K. Effects / Transitions

第一阶段只要求“够用”，不要建设剪映式海量库。

## K1. Basic Transition
## K2. Cross Dissolve
## K3. Fade
## K4. Basic Blur
## K5. Crop / Mask
## K6. Simple Overlay
## K7. Text Overlay

### 暂不优先
- 海量特效
- 模板商城
- 大型花字库
- 复杂 3D 转场
- 海量滤镜

原则：**AI / Skill 可以在需要时生成或推荐，而不是靠库存竞争。**

---

# 15. L. Keyframe / Animation

## L1. Position keyframe
## L2. Scale keyframe
## L3. Rotation keyframe
## L4. Opacity keyframe
## L5. Easing
## L6. Keyframe editing

### 判断
基础关键帧属于正常编辑器的能力，但第一阶段只需覆盖最常用的 Transform 参数。

不要一开始追求 AE 级表达式系统。

---

# 16. M. Undo / Redo / History

## M1. Undo
## M2. Redo
## M3. 多步 Undo
## M4. Operation Log
## M5. 当前状态
## M6. 回滚
## M7. AI Operation 可回滚
## M8. 人工 Operation 可回滚

### 当前证据
项目示例已经存在 `operations/op00001~op00066.json` 和 `versions/v1.json`，说明操作与版本持久化已经存在基础结构。fileciteturn0file0L124-L129

### 核心测试
> AI 改了一次 → 人手动改一次 → AI 再改一次 → Undo 一次 → 是否只撤回最后一步？

---

# 17. N. Project Reliability

## N1. Autosave
## N2. Crash recovery
## N3. Asset relink
## N4. Cache cleanup
## N5. Temporary file cleanup
## N6. Proxy / optimized media
## N7. Project reopen
## N8. Missing asset diagnosis
## N9. External drive path recovery
## N10. Version migration

这是用户信任的底座。

> **视频软件最不能接受的是：能做，但做完打不开。**

---

# 18. O. Render / Export

## O1. Preview Render
## O2. Final Render
## O3. Common codecs
## O4. Resolution
## O5. FPS
## O6. Audio sync
## O7. Export preset
## O8. Progress
## O9. Failure diagnosis
## O10. Cancel / Resume（后期）
## O11. Export package
## O12. Cover / Title / Copy / Tags

### 当前架构证据
已有 `render.py`、`publish.py`，并已有 `test_render.py`、`test_render_multitrack.py`、`test_publish_cost.py`，说明 Render / Publishing / Cost 已有结构基础。fileciteturn0file0L39-L45 fileciteturn0file0L154-L158

---

# 19. P. Performance / Large Projects

## P1. 10 clips
## P2. 50 clips
## P3. 200 clips
## P4. 500 clips
## P5. 4K素材
## P6. Long video
## P7. Playback stability
## P8. Timeline responsiveness
## P9. Memory growth
## P10. Cache growth
## P11. GPU usage
## P12. Proxy mode

### 核心原则
不要在“实验项目”里判断性能。

必须做：

> 真实用户级素材压力测试。

至少准备：

- 30 个手机视频
- 100 个视频
- 500 个视频
- 4K素材
- 图片 + 视频混合

---

# 20. Q. Human-AI Command Boundary

这部分不是传统编辑能力，但决定 YROLL AI-native 架构是否成立。

## Q1. 所有基本编辑是否都有 Command

例如：

```text
trim_clip()
split_clip()
move_clip()
delete_clip()
ripple_delete()
change_volume()
edit_caption()
move_caption()
transform_clip()
replace_asset()
```

## Q2. 鼠标操作与 AI 操作是否调用同一 Command

## Q3. MCP 是否调用同一 Command

## Q4. 手机未来是否能够调用同一 Command

## Q5. Command 是否有统一 Undo / Redo

## Q6. AI 操作是否成为普通 Operation

## Q7. 操作是否写入 Project History

这是 YROLL 与普通“聊天式AI剪辑”的结构性基础。

---

# 21. 当前代码结构的初步判断

基于当前项目快照，只做“存在性判断”，不代表体验已经可用。

| 区域 | 当前证据 | 初步状态 |
|---|---|---|
| Core Project | `project.py` / `models.py` / `store.py` | 🟠 |
| Commands | `commands.py` | 🟠 |
| Manifest | `manifest.py` | 🟠 |
| Semantic Links | `links.py` | 🟠 |
| Problems | `problems.py` | 🟠 |
| Render | `render.py` | 🟠 |
| Publishing | `publish.py` | 🟠 |
| Asset Resolver | `resolver.py` | 🟠 |
| Timeline UI | `Timeline.tsx` | ❓ |
| Clip UI | `ClipBlock.tsx` | ❓ |
| Clip Workspace | `ClipWorkspace.tsx` | ❓ |
| Preview | `PreviewPlayer.tsx` | ❓ |
| Visual Adjust | `VisualAdjustPanel.tsx` | ❓ |
| Audio | `audio_tools.py` | 🟠 |
| ASR | `asr.py` | 🟠 |
| Jianying import | `jianying.py` | 🟠 |
| Harness | `runtime.py` | 🟠 |
| Skills | 4 个 Audio/Watermark Skills | 🟠 |
| MCP | `mcp_server.py` | 🟠 |
| Operations | 66 个示例操作日志 | 🟠 |
| Versions | `v1.json` | 🟠 |
| Tests | 18 个测试文件 | 🟠 |

### 关键结论

**目前不能凭目录判断“基础剪辑能力已经够用”。**

真正需要 Claude Code 做的是：把所有 `❓` 和 `🟠` 变成实际任务证据。

---

# 22. Claude Code Reality Test Protocol

Claude Code 不应该只扫描代码，而应该启动 YROLL 并真实操作。

## Test Group A：30 秒简单视频

> 3 个手机视频 + 1 张照片 → 30 秒视频 → 导出。

验证：
- 导入
- Timeline
- Move
- Trim
- Split
- Delete
- Preview
- Export

## Test Group B：删除中间片段

> 删除第 2 个 Clip 中间 2 秒。

验证：
- Ripple
- 后续 Clip
- Voice
- Subtitle
- BGM

## Test Group C：普通视觉调整

> 将一个 Clip 缩小 30%，右移，旋转 10°。

## Test Group D：局部音频

> 只把 1～3 秒人声提高 4dB，并做羽化。

## Test Group E：字幕

> 自动生成字幕 → 修改一个词 → 调整时间 → 删除中间 2 秒 → 检查字幕是否仍正确。

## Test Group F：多轨

> Video + Voice + SFX + BGM + Subtitle 同时存在，移动/删除 Clip。

## Test Group G：Undo / Redo

> 人工修改 → AI修改 → 人工修改 → 连续 Undo / Redo。

## Test Group H：断AI

> 关闭网络 / 禁用 AI provider，完成一条简单视频。

## Test Group I：大项目

> 50 / 100 / 500 个素材项目，观察卡顿、内存、缓存、Timeline操作。

## Test Group J：AI接管

> 用户先手动完成部分剪辑 → AI继续修改同一个项目 → AI是否真正理解当前状态，而不是重新从原始状态开始。

---

# 23. Claude Code 输出格式

每一个测试都必须返回：

```text
Test ID:
Task:
Result: PASS / PARTIAL / FAIL

Actual steps:
1.
2.
3.

Observed problems:
- 
- 

Severity:
P0 / P1 / P2 / P3

Evidence:
- screenshot/path
- log
- test result

Recommended fix:

Would user return to Jianying because of this?
YES / NO / MAYBE
```

特别增加最后一问：

> **“如果我是普通用户，我会不会因为这个问题回剪映？”**

这是最重要的产品判断之一。

---

# 24. 最终 Backlog 的排序规则

Claude Code 实测回来后，不按“实现难度”直接排序，而按照：

```text
Priority Score
=
User Frequency
×
Pain Severity
×
Core Workflow Impact
×
Return-to-CapCut Risk
×
Implementation Feasibility
```

再考虑：

- AI dependency
- offline availability
- cost
- performance
- technical debt

## P0
不解决就影响“基础剪辑能不能用”。

## P1
明显影响效率，但有临时办法。

## P2
体验增强。

## P3
以后再做。

---

# 25. 最终输出：YROLL Editor Foundation Backlog v0.1

Claude Code 完成 Reality Test 后，把每项写成：

```text
ID:
Capability:
Current State:
Evidence:
User Task:
Observed Gap:
Severity:
Frequency:
AI Dependency:
Offline:
Implementation Difficulty:
User Time Saved:
CapCut Return Risk:
Recommended Solution:
Dependencies:
V1 / Later:
```

最后只保留真正进入开发的项目。

---

# 26. 本轮最重要的开发纪律

> **Gap Analysis 不是为了证明 YROLL 缺很多功能。**
>
> **而是为了找出：最少补哪些基础能力，YROLL就能够让用户真正完成一条普通视频。**

然后再把 AI-native 能力叠加上去。

最终路线应当是：

```text
Editor Foundation
        ↓
一个普通人可以独立完成视频
        ↓
AI介入普通操作
        ↓
Problem → Solution
        ↓
Human / AI Continuous Handoff
        ↓
自动化程度逐渐提高
```

---

# 27. 与现有 YROLL 架构的关系

这份 Gap Analysis 不要求推翻现有：

- Manifest
- Harness
- Skills
- Semantic Links
- Problems
- MCP
- Clip Workspace
- Y轴

它只是增加一个基础层：

```text
                    YROLL
                      │
             AI Production Layer
                      │
       Harness / Skills / Routing
                      │
       Y Workspace / Problem Solution
                      │
            Editor Foundation
                      │
        Timeline / Media / Audio / Text
                      │
         Preview / Render / Project
```

**Editor Foundation 是地基，不是新的产品方向。**

---

## 下一步

先由 Claude Code 按第 22～23 节跑真实测试；不要让它只读代码给意见。

之后把它的结果追加进本文，形成：

`YROLL Editor Foundation Gap Analysis v0.2`

再从中筛选真正进入：

`YROLL Editor Foundation Backlog v0.1`
