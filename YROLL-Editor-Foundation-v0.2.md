它以后就是：

Claude Code 唯一施工依据

旧文档全部 ARCHIVED。

而且这份文档不再只是架构说明，要同时成为：

Spec + Work Breakdown + Acceptance Criteria + Reality Test

一、第一原则：先修“协议接缝”，再修 UI

这次我建议严格按这个顺序：

Core v0.2
      ↓
GUI Adapter
      ↓
Timeline / Selection
      ↓
Preview
      ↓
Visual polish

不要一上来重做 Timeline UI。

因为当前最致命的问题不是 Timeline 看起来不好。

是：

GUI 还没有真正进入 Core v0.2 的世界。

二、Batch 01：GUI Mutation Gate 接通

这是第一批施工。

目标：

GUI 的任何写操作，都必须经过当前 Session + Base Revision + Mutation Gate。

1. 建立 GUI Session Store

不要再让 EditLease.tsx 自己持有一点状态，api.ts 再自己从 localStorage 猜。

应该有一个统一：

useProjectSession()

sessionId
owner
mode
revision
leaseStatus
conflict

例如：

{
  sessionId,
  owner: "human",
  mode: "edit",
  revision: 104,
  leaseExpiresAt,
  conflict: false
}
2. api.ts 统一 Mutation Envelope

以后：

api.trim(...)
api.move(...)
api.split(...)
api.remove(...)
api.volume(...)

不能再自己定义不同参数。

统一：

MutationRequest {
    session_id
    base_revision
    actor
    mutation
}

或者由 API client 自动注入：

api.mutate(...)

这样以后不会再发生：

增加一个新的 mutation，忘了传 Gate 参数。

3. Chat 也必须走同一条路

Chat Agent：

GUI Chat
 ↓
session
 ↓
current revision
 ↓
Agent
 ↓
proposal
 ↓
approval
 ↓
Mutation Engine

不能存在：

GUI mutation → Gate
Chat mutation → 老路径
三、Batch 02：Revision / Conflict / Handoff UI

这批是解决你刚刚提出的：

“像 Git 一样冻结、交接，而且一眼能看出来。”

我建议直接做成 YROLL 的一级 UI。

顶部永久状态栏

例如：

┌───────────────────────────────────────────────────────────┐
│ 🟢 编辑权：你    Revision 107        [交给 Claude ▾]    │
└───────────────────────────────────────────────────────────┘

当 Agent：

┌───────────────────────────────────────────────────────────┐
│ 🟡 Claude 正在编辑    Revision 108     [收回编辑权]      │
└───────────────────────────────────────────────────────────┘

冲突：

┌───────────────────────────────────────────────────────────┐
│ 🔴 工程已被其他会话修改  Revision 109                     │
│      [查看变化]   [刷新]                                  │
└───────────────────────────────────────────────────────────┘
Timeline 也同步表达

Agent 正在改：

00:00      00:20      00:40      01:00
───────────████████───────────────
             🟡 AI

你不能误以为：

“为什么这里拖不了？”

而是一眼知道：

“现在是 Claude 的编辑权。”

这点我赞成做成明显的灰度/黄色高亮。

四、Batch 03：Frame-Native Timeline

这是第二个最重要的大工程。

不能只是：

“把秒显示成 00:00:17:18。”

必须整个 Timeline 改成：

Frame-native
Canonical state
currentFrame
clip.startFrame
clip.endFrame
source.startFrame
source.endFrame

UI：

00:00:17:18

而不是：

17.6 sec
键盘

必须来自 Core：

J       -1 frame
L       +1 frame

←       -1 frame
→       +1 frame

Shift←  -10 frames
Shift→  +10 frames

而不是 App.tsx 自己写一套。

也就是说：

keyboard.describe_keymap() 不是“调用一下”。

GUI 的实际行为应该由这个 contract 驱动。

五、Batch 04：Selection Mutation

现在的：

selectedSet

不要废掉。

但是升级成真正的：

EditorSelection

支持：

Single
Multi
Range
Cross-track
Linked

然后：

moveSelection()
deleteSelection()
trimSelection()

都走 Core Mutation Engine。

禁止：

for clip_id in selected:
    move_clip(...)

这点必须写成硬性规则。

否则看似多选，实际上只是：

“批量调用单选接口。”

六、Batch 05：Unified Timeline Mutation

这一批把：

Move
Trim
Ripple Trim
Ripple Delete
Split
Insert
Overwrite

彻底统一。

尤其是：

Split

必须：

timeline frame
 ↓
TimeMap
 ↓
source frame
 ↓
split
 ↓
relationship rebind

而不是 GUI 自己算比例。

七、Split 后的 Relationship 必须成为强制测试

例如：

Video A
  ↕
Voice A
  ↕
Subtitle A

Split：

Video A1
Video A2

之后系统必须知道：

Voice A
→ covers A1 + A2

或者：

Voice A
→ A1
Voice B
→ A2

具体怎样由语义决定，但不能丢关系。

否则 Agent 后面一剪，整个工程会慢慢失去语义结构。

八、Batch 06：Snap Engine

现在已经有 Core Snap。

GUI 要完全删除自己的：

0.25 sec

这种 snap 逻辑。

统一：

SnapEngine

支持：

frame boundary
clip edge
playhead
marker
selection edge
subtitle boundary
word boundary

以后甚至：

“切点对齐台词最后一个字。”

自然就能接上。

九、Batch 07：History

GUI 统一：

history.undo()
history.redo()

然后：

GET /history/state

直接驱动：

Undo disabled
Redo disabled

而不是再：

找最后一个 revert operation。

十、Batch 08：Mutation Preview / Semantic Diff

Core 已经做出来。

GUI 必须开始消费：

/mutation/preview
/proposals
/ui/status
/audit
/diff

例如你拖一个镜头：

Commit 前

显示：

移动 Shot 07 +12 frames

影响：
Subtitle 07 +12
Voice 07 +12
SFX unchanged
BGM unchanged

你松手以后：

Commit。

然后：

Revision Diff
Revision 108 → 109

Shot 07     +12f
Subtitle 07 +12f
Voice 07    +12f

这才是 YROLL 的特色真正进入 GUI。

十一、Batch 09：Composite Preview

这个我们之前已经确定。

不是立刻追求 Resolve 级。

做三层：

L0

Frame preview。

L1

Local Composite。

L2

现有 Full Render。

十二、L1 要优先服务“编辑反馈”

比如：

你在 00:37 改：

古画的位置。

不要整条90秒 render。

只需要：

00:35 — 00:40

重新合成。

然后 Preview 立即变化。

这才会让 YROLL 真正“能剪”。

十三、Batch 10：Direct Manipulation

在 Preview 里面：

┌──────────────┐
│              │
│    IMAGE     │
│              │
└──────────────┘
↗   ↙

move
scale
rotate
crop

所有操作：

Mouse
 ↓
Mutation

而不是：

Mouse
 ↓
Local React state
 ↓
eventually patch backend
十四、Batch 11：Audio / Subtitle

现在 Core 的这些能力已经相当丰富。

GUI 要把它们变成真正的编辑体验。

Audio

波形：

────╱╲──╱╲───────

可以：

split
trim
fade
volume keyframe
duck
mute
solo
Subtitle

直接在 Timeline：

split
merge
move
trim
batch style

而不是全部跑 Inspector。

十五、Batch 12：Story / Beat / Marker

这一批现在可以做。

因为 Core 已经完成：

StoryBeat
Marker

GUI 至少应该先有：

      STORY BEAT
          ▼
─────────◆───────────────
        marker

然后未来：

Hook
Context
Discovery
Reveal
Conclusion

可以直接挂在 Timeline 上。

这个会让 YROLL 开始明显区别于普通 NLE。

十六、Batch 13：GUI Reality Test

这时候才重新跑：

YROLL GUI Reality Test v0.2

而且这次必须：

真的启动 GUI。

不是静态审计。

测试：

G001

导入10个视频。

G002

导入10张图片。

G003

拖图片进 Timeline。

G004

逐帧播放。

G005

Frame-accurate trim。

G006

多选三个 Clip。

G007

一起移动。

G008

Ripple Delete。

G009

Split + Relationship。

G010

Undo / Redo。

……

最终：

17-Step Real Edit Test

必须由真实 GUI 完成。

十七、然后加一个非常重要的指标
GUI Escape Rate

这个特别适合你。

你拿真实项目剪：

《他们拿着一幅假画，去寻找4000年前的人》

每当：

“这个我还是去剪映做。”

记录一次。

例如：

总编辑动作：82

YROLL完成：76
回剪映：6

Escape Rate = 7.3%

目标：

v0.2 GUI

< 30%

v0.3

< 15%

v0.4

< 5%

这会比：

“实现了多少功能”

真实得多。

十八、我会把 Claude Code 的施工顺序锁死

给它的不是：

“完善 GUI。”

而是：

Phase GUI-01
Session + Gate + Revision

Phase GUI-02
Frame + TimeModel

Phase GUI-03
Selection + Mutation

Phase GUI-04
Snap + History

Phase GUI-05
Preview

Phase GUI-06
Audio + Subtitle

Phase GUI-07
Agent / Diff / Handoff

Phase GUI-08
Reality Test

每个 Phase 必须：

Implementation
↓
Unit tests
↓
Integration tests
↓
GUI smoke test
↓
Reality benchmark
↓
Regression

否则下一批不能开始。

十九、还有一个非常重要的开发纪律

以后 Claude Code 不能说：

“Feature completed.”

除非同时报告：

Implementation:
✓

Core Test:
✓

API Test:
✓

GUI Test:
✓

Undo/Redo:
✓

Regression:
✓

Reality Task:
✓

否则只能叫：

Implemented / Not Verified

这一个纪律，可能就能解决你之前一半的痛苦。

因为：

“代码写出来了” ≠ “功能完成了”。

二十、YROLL 最终应该形成的几个“真相”

我现在会把它归纳成：

Truth 1

Project State

工程现在是什么样。

Truth 2

Frame Time

每个对象精确在哪一帧。

Truth 3

Relationship

东西之间为什么关联。

Truth 4

Mutation

刚才到底改变了什么。

Truth 5

Revision

现在属于哪个版本。

Truth 6

Ownership

现在谁拥有编辑权。

Truth 7

Preview

这个状态实际长什么样。

Truth 8

Provenance

这个变化是谁做的、为什么做。

然后：

Human 和 Agent 都只能通过同一套 Truth 工作。

这才是 YROLL。

二十一、所以现在到了一个非常明确的节点

你的配合暂时只有一件事。

把当前这份：

YROLL GUI Reality Audit v0.1

以及 Claude Code 刚刚报告的：

Foundation v0.2 306 passed

视为审计输入。

暂时不要再让 Claude Code自行发挥。

我建议你现在把下面这段直接交给 Claude Code：

停止新增功能。

当前 306 passed 仅证明 Core v0.2 自动测试通过，不得视为 GUI 合格。

请以仓库现有 YROLL GUI Reality Audit v0.1 和最终 YROLL-Editor-Foundation-v0.2.md 为施工依据。

第一阶段只实施 GUI-01: Session + Mutation Gate + Revision。

禁止同时修改 Frame / Timeline / Preview / Story / Agent UI。

完成后必须提供：

修改文件；
API contract 变化；
GUI → Core 调用链；
自动测试；
Gate 失败时 GUI 行为；
revision conflict 行为；
regression test；
明确列出“已实现但尚未 GUI 验证”的部分。

不得用“代码存在”作为完成条件。

然后只让它做 GUI-01。

做完，我们再进行第二批。

这样现在终于有机会从：

“Claude Code 不停补东西，我也不知道到底好了没有”

变成：

“一层一层验收，直到 YROLL 真正成为一个我愿意每天使用的剪辑器。”

而我认为，基于现在这份 Audit，第一批只修 Session/Gate/Revision 是最正确的决定。因为这是目前唯一一个会让“整个 GUI 编辑路径事实上被 Core 拒绝”的 P0 阻断问题；把它解决之后，后面的 Frame、Selection、Mutation、Preview 才有稳定的接口可以往上搭。