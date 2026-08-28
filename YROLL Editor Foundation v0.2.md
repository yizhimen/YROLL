Status：Proposed Canonical Implementation Specification
用途：YROLL 后续 Core / GUI / HTTP / MCP / Agent 开发的唯一施工依据

本文档覆盖本次代码审计后确定的编辑器基础架构。

仓库中此前的 Foundation、Gap Analysis、Reality Test、开发规划等文档保留为历史资料；实现时以本文档为唯一技术施工依据。

YROLL 当前仓库已经公开，并且实际已经包含 GUI、Core、Server、MCP、Render、Project Memory 等多个层次；但 README 仍将项目描述为 Phase 0 Spike，因此本规范同时承担“架构状态收敛”的作用。

0. 核心目标

YROLL 不是：

一个“可以用 AI 帮忙剪视频”的传统剪辑器。

YROLL 的目标是：

一个 Human + Agent 可以共同操作、理解、修改、回退和验证的视频时间轴。

因此 YROLL 的基础模型必须同时服务三个主体：

Human
  │
  ├── GUI
  │
  └── Keyboard / Mouse

Agent
  │
  ├── MCP
  └── API

Core
  │
  └── Canonical Project State

所有修改最终必须进入同一个：

Canonical Mutation Layer

1. 五条不可违反的原则
P1. Frame First

帧是编辑时间的 canonical representation。

秒不是编辑单位。

秒只是：

UI 显示
外部媒体接口
FFmpeg 参数
人类友好的时间表示
P2. One Mutation Path

GUI、MCP、Agent、HTTP 不允许各自实现编辑逻辑。

全部：

Intent
 ↓
Mutation Engine
 ↓
Operation
 ↓
Project State
P3. Preview Before Commit

凡是可能影响多个对象的操作，都必须能够：

Preview
 ↓
Impact
 ↓
Commit
P4. Project State Has Ownership

一个工程可以被多个进程读取。

但：

同一时刻只能有一个 Mutation Authority。

其他进程可以：

Read
Observe
Propose
Preview

但没有写权限。

P5. Every Mutation Is Reversible

每次 mutation 必须产生：

Operation

并能够：

undo()
redo()
2. Canonical Time Model
2.1 Sequence Time

Project 必须拥有：

SequenceTimebase
├── fps_num
├── fps_den
├── width
├── height
└── timebase

例如：

24 fps
25 fps
30000/1001 fps
60 fps

禁止默认假定：

30fps
3. FrameTime

核心对象：

FrameTime {
    frame: int
    timebase: Rational
}

例如：

frame = 1832
fps = 30

就是：

61.0667 sec

但内部编辑对象永远是：

FrameTime(1832)

而不是：

61.0667
4. FrameRange

统一：

FrameRange {
    start_frame: int
    end_frame: int
}

约定：

[start, end)

例如：

[100, 200)

表示：

100 ... 199

这样可以避免大量 off-by-one 错误。

5. Time Mapping

YROLL 不能只解决：

seconds → frames

而必须解决四层时间：

Source
  ↓
Clip Local
  ↓
Timeline
  ↓
Output

即：

Source Frame
      ↕
Clip Local Frame
      ↕
Timeline Frame
      ↕
Output Frame

必须统一处理：

trim
speed
reverse
slip
retime
transition
output rendering

任何 GUI 层不得自己计算这些关系。

6. Selection Model

Selection 必须成为一等公民。

至少支持：

Single Clip
Multi Clip
Range
Track Range
Linked Selection

例如：

Selection {
    clips: [...]
    tracks: [...]
    range: FrameRange?
}

所有 mutation 都应接受 Selection，而不是只接受：

clip_id
7. Mutation Engine

这是 YROLL v0.2 的核心。

统一流程：

Intent
  ↓
Resolve Selection
  ↓
Resolve Frame Range
  ↓
Resolve Relationships
  ↓
Calculate Impact
  ↓
Validate
  ↓
Preview
  ↓
Commit
  ↓
Record Operation
  ↓
Notify
8. Mutation 类型

最低要求：

MOVE
TRIM
SPLIT
DELETE
RIPPLE_DELETE
INSERT
OVERWRITE

随后：

SLIP
ROLL
SLIDE
9. Move

Agent：

move_selection(
    selection,
    delta_frames
)

而不是：

move_clip(
    clip_id,
    new_timeline_start_seconds
)
10. Trim

Trim 必须支持：

trim_start
trim_end

并计算：

source change
timeline change
relationship impact

Trim 不得成为当前这种“只改变自己”的孤岛。

11. Split

Split：

split_at_frame(
    clip_id,
    timeline_frame
)

Core 负责：

timeline → source mapping

GUI 不允许自己通过秒数比例计算 source position。

Split 后必须重新处理 Relationship。

12. Relationship Model

当前 YROLL 已经有 Relationship 的雏形，这是应该保留并强化的部分。

关系至少包括：

STRONG
MEDIUM
WEAK
INDEPENDENT

但最终结构应该支持：

Relationship {
    source
    target
    kind
    strength
    confidence
    time_scope
    semantic_scope
}

时间重叠只是 heuristic。

不能把：

overlap

等同于：

semantic ownership。

13. Relationship Propagation

任何 mutation 都必须计算：

Primary Impact
Secondary Impact

例如：

Delete Shot 07

可能：

Shot 07          → remove
Subtitle 07      → shift
Voice 07         → shift
SFX 07           → shift
BGM              → untouched
Story Beat 03    → affected
14. Mutation Preview

这是 YROLL 的重要特色。

例如用户拖动：

Shot 07

GUI 不应该只显示：

Shot 07 移动了。

而应该显示：

Shot 07       +12 frames
Subtitle 07   +12 frames
Voice 07      +12 frames
SFX           unchanged

即：

用户看到的是“操作将产生什么”，而不是操作本身。
15. Snap Engine

Snap 必须只有一个。

禁止：

ClipBlock Snap
App Snap
Core Snap

各自计算。

统一：

SnapEngine

支持：

Clip Start
Clip End
Playhead
Selection Edge
Marker
Subtitle Boundary
Word Boundary
Beat

以后可以：

“让画面切点对齐一句话最后一个字。”

即：

ASR Word Boundary
        ↓
Frame
        ↓
SnapEngine
        ↓
Mutation
16. GUI 不得拥有编辑真相

GUI 可以拥有：

drag state
hover state
selection visual
preview visual

但不能拥有：

timeline mutation logic
source mapping
relationship propagation
snap algorithm
history semantics

GUI：

负责表达。

Core：

负责决定。

17. History API

外部统一：

history.undo()
history.redo()

GUI / MCP / Agent 都不能自己操作 Operation Log。

内部实现可以继续使用现有 Operation / Revert 机制。

以后再逐步升级为真正的 history cursor。

18. Project Session / Edit Lease

这是你刚刚提出、我认为必须加入 P0 的部分。

18.1 为什么需要它

当前架构允许：

GUI
 ↓
ProjectCore A

MCP
 ↓
ProjectCore B

两个进程可能同时：

read
modify
save

于是可能产生：

A reads revision 10
B reads revision 10

A → revision 11
B → revision 11

最终：

A 的修改可能被 B 覆盖。

19. Edit Lease

工程状态增加：

ProjectSession
├── session_id
├── project_id
├── actor
├── mode
├── acquired_at
├── last_heartbeat
└── base_revision

Actor：

HUMAN
AGENT

Mode：

EDIT
OBSERVE
PROPOSE
20. 三种状态
EDIT

拥有修改权。

例如：

HUMAN — Editing

其他 Agent：

READ / PROPOSE
OBSERVE

只能读取：

Timeline
Assets
Operations
Impact

不能 Commit。

PROPOSE

Agent 可以：

Analyze
Plan
Preview

但不能直接写入。

21. Git-like Revision

每次 Commit：

revision 104

变成：

revision 105

Mutation 必须声明：

base_revision

例如：

Agent:
base_revision = 105

current_revision = 106

则：

拒绝直接提交。

必须：

refresh
↓
re-evaluate
↓
preview again
↓
commit

这比单纯 file lock 安全得多。

22. Handoff

这是 YROLL 最关键的人机协作功能之一。

例如你现在编辑：

HUMAN
EDIT

然后准备让 Claude：

“你接着帮我改。”

点击：

Handoff to Agent

状态：

HUMAN
 ↓
FREEZE
 ↓
AGENT EDIT

GUI 显示：

🔶 AI 正在编辑此工程

你仍然可以：

看
播放
浏览素材

但是不能修改。

23. Agent 完成以后

Agent：

HANDOFF_BACK

变成：

AGENT
 ↓
FREEZE
 ↓
HUMAN EDIT

GUI：

🟢 编辑权已交还给你

24. 视觉状态必须非常明显

这个我完全赞成你的判断。

不能只在设置里写：

Session locked.

用户根本不会注意。

应该在 Timeline 顶部持续显示：

Human

🟢 你正在编辑

Agent

🟡 Claude 正在编辑

Observe

⚪ 只读观察

Conflict

🔴 工程已发生变化，请刷新

25. Timeline 视觉提示

当 Agent 编辑时：

整个 Timeline 可以轻微：

灰度 / 降低饱和度

顶部出现：

🟡 CLAUDE 正在编辑

同时：

鼠标拖动、Trim、Split 等写操作禁用。

不要把整个 UI 做成“软件坏了”的感觉。

应该是：

明确告诉用户：现在轮到谁。

26. 更进一步：显示“修改区域”

如果 Agent 正在修改：

00:17 — 00:24

Timeline 可以：

┌─────────────────────────────┐
│        🟡 AI WORKING        │
├──────────┬──────────────────┤
│          │████████           │
│          │  AI affected     │
└──────────┴──────────────────┘

用户一眼就知道：

Claude 到底在碰哪里。

27. Conflict 状态

如果工程 revision 已变化：

🔴 Project changed externally

不能让用户继续无意识编辑。

按钮：

[Review Changes]
[Reload]
[Keep My Session]

Agent 同样如此。

28. 这其实比 Git 更适合视频

Git：

file
 ↓
diff
 ↓
merge

视频工程：

timeline
 ↓
operation
 ↓
affected clips
 ↓
affected time range

因此 YROLL 应该做：

Semantic Timeline Diff

例如：

Revision 105 → 106

Shot 07
  moved +12 frames

Subtitle 07
  moved +12 frames

Voice 07
  unchanged

Shot 08
  trimmed -18 frames

未来甚至可以：

“看看 Claude 刚才改了什么。”

直接在 Timeline 上显示。

这会非常强。

29. Agent Contract

MCP 最终不应该暴露大量：

yroll_move_clip(seconds)
yroll_split_clip(source_time)

而应该逐步升级为：

get_project_state()
get_selection()
get_timeline()
get_impact()
preview_mutation()
commit_mutation()
undo()
redo()
request_edit_lease()
release_edit_lease()
handoff()

然后 mutation：

move
trim
split
delete
ripple_delete
insert
overwrite

全部统一走 Mutation Engine。

30. Preview Pyramid

现有 Renderer 不推倒。

定义三层：

L0 — Frame Preview

用于：

seek
trim
frame stepping
precise inspection
L1 — Local Composite

只渲染：

playhead ± N frames

支持：

video
image
PiP
subtitle
transform
audio
SFX

用于：

真正剪辑时的即时检查。

L2 — Full Render

使用现有 FFmpeg Renderer。

用途：

最终检查 / 导出。

31. Renderer 原则

现有 Render 能力：

Video
Image
Audio
BGM
Subtitle
PiP
Transform
Crop
Opacity
Fade
Reverse
Speed
Transition

应当：

保留，不重写。

需要做的是让它服从：

Project Timebase
Time Mapping

而不是自己维护另一套时间。

32. Render Time

禁止：

render(fps=30)

成为项目级默认。

应该：

project.sequence.timebase

统一决定。

33. Local Render

当前：

render full project
 ↓
cut start/end

可以继续作为 L2。

但未来 L1 必须做到：

affected frame range
 ↓
local composite
 ↓
cache

而不是整个项目重新渲染。

34. Keyboard Editing

真正可用版本必须支持：

J
K
L

I
O

←
→

Shift + ←
Shift + →

Space

S
Delete
Shift + Delete

并且全部基于 Frame。

35. 编辑器完成标准

不是：

API 能调用。

不是：

Claude Code 能改 JSON。

而是：

一个普通用户可以不用 Claude Code，单靠 YROLL 完成一次真实短视频粗剪 + 精剪。

至少应该能够：

导入
 ↓
拖入
 ↓
移动
 ↓
Trim
 ↓
Split
 ↓
删除
 ↓
Ripple
 ↓
字幕
 ↓
音频
 ↓
PiP
 ↓
转场
 ↓
Undo
 ↓
Redo
 ↓
Preview
 ↓
Export
36. Reality Test v0.2

必须建立真实操作测试，而不是只测 Python API。

Test A — Frame
24fps
25fps
30fps
59.94fps
Test B — Basic Editing
Move
Trim
Split
Delete
Test C — Ripple
Video
Subtitle
Voice
SFX
BGM

验证：

哪些跟随、哪些不跟随。

Test D — Split Relationship
Video
Voice
Subtitle

Split 后：

Relationship 是否正确分裂。

Test E — Undo / Redo

每一种 mutation：

Action
→ Undo
→ Redo
Test F — Human / Agent
Human Edit
 ↓
Freeze
 ↓
Agent Edit
 ↓
Handoff
 ↓
Human
Test G — Conflict
A revision 10
B revision 10

A → 11
B → commit

Expected:
CONFLICT

绝不能 silent overwrite。

37. P0 最终清单

现在我把所有审计结果压成这一份：

P0-01

Canonical Frame Timebase

P0-02

Time Mapping

P0-03

Unified Selection

P0-04

Mutation Engine

P0-05

Relationship Propagation

P0-06

Snap Engine

P0-07

Mutation Preview / Impact

P0-08

History API

P0-09

Project Revision

P0-10

Edit Lease / Handoff

P0-11

GUI / API / MCP 全部接入同一 Mutation Path

P0-12

禁止 Silent Overwrite

38. P1

完成 P0 后：

Slip
Roll
Slide
Keyboard
Markers
L0 Frame Preview
L1 Local Composite
Multi-selection
39. P2

然后才进入真正的 AI-native：

Timeline Understanding
Story / Beat Model
Semantic Relationships
Agent Plan
Mutation Proposal
Automatic Impact Analysis
Agent Evaluation
Automatic Iteration
40. 最终 YROLL 的真正形态

我认为到这里，YROLL 的核心已经非常清楚了：

                 HUMAN
                   │
                   │
                 GUI
                   │
                   ▼
             ┌─────────────┐
             │   SESSION   │
             │   / LEASE   │
             └──────┬──────┘
                    │
             ┌──────▼──────┐
             │   PROJECT   │
             │   REVISION  │
             └──────┬──────┘
                    │
        ┌───────────▼───────────┐
        │   CANONICAL TIMELINE  │
        │                       │
        │      FRAME MODEL      │
        │      TIME MAPPING     │
        └───────────┬───────────┘
                    │
             ┌──────▼──────┐
             │  SELECTION  │
             └──────┬──────┘
                    │
             ┌──────▼──────┐
             │ RELATIONSHIP│
             └──────┬──────┘
                    │
             ┌──────▼──────┐
             │  MUTATION   │
             │   ENGINE    │
             └──────┬──────┘
                    │
             ┌──────▼──────┐
             │   IMPACT    │
             │   PREVIEW   │
             └──────┬──────┘
                    │
             ┌──────▼──────┐
             │  OPERATION  │
             │     LOG     │
             └──────┬──────┘
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
       PREVIEW              RENDER
       L0/L1                 L2

而 Agent 从另一边进入：

                  CLAUDE / AGENT
                        │
                       MCP
                        │
                        ▼
                 Project Session
                        │
                 PROPOSE / EDIT
                        │
                        ▼
                 Mutation Engine

最终 Human 和 Agent 并不是两套编辑器。

而是：

两个操作者，共享一个有版本、有关系、有时间语义、有可回退历史的编辑内核。

41. 这也解决了我们最初遇到的 OpenChatCut 问题

OpenChatCut 那种：

GUI
 ↓
持有 session

MCP
 ↓
想接管

最后变成：

GUI 开着不能 MCP，MCP 开着 GUI 又不能动。

YROLL 不应该复制这个模式。

YROLL 应该是：

GUI ───────┐
           │
MCP ───────┼──→ Project Session
           │
Agent ─────┘
              │
       Edit Lease
              │
       Current Owner
              │
       Revision Guard

这样：

GUI 可以开着。

Claude 也可以开着。

但同一时刻谁拥有“编辑权”是明确的。

而且用户一眼就看得到。

42. 最后一个我认为非常重要的产品细节

我建议不要把它叫：

Lock

因为用户会觉得：

“软件怎么又锁了？”

应该叫：

编辑权

界面上直接显示：

🟢 编辑权：我

或者：

🟡 编辑权：Claude

点击：

交给 Claude

或者：

收回编辑权

这会比：

Session / Lock / Mutex / Lease

这种工程术语友好很多。

底层当然叫：

EditLease

但产品层叫：

编辑权