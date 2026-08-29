有两个很小的文档/工程清理项，我建议在 GUI-02 前顺手做掉，但不要因此阻塞 GUI-02：

README 当前的 MCP 使用示例仍然写成 yroll mcp <工程目录>，而实际新接口已经是 yroll mcp --server URL --actor-id ID。
Foundation 文档里出现了一些历史文档与新文档并存、甚至同名不同路径的情况。现在既然已经约定“唯一施工依据”，GUI-02 开始前应该把 YROLL Editor Foundation v0.2.md 明确标成唯一 canonical spec，其余全部明确 ARCHIVED。仓库当前确实仍有多份旧 Foundation/Gap/Reality 文档。

除此之外，我建议不再碰 GUI-01.5。

现在正式进入 GUI-02：Frame-Native Timeline

这一批我建议我们非常严格：

不是“给 Timeline 增加帧显示”。

而是把 Timeline 从 seconds-first 改成 frame-first。

Foundation v0.2 已经明确规定：FrameTime 是 canonical representation，秒只是显示/外部接口；GUI 不得自行做 time mapping。

GUI-02 的真正目标

做到这一点：

          Project FPS / Timebase
                    │
                    ▼
             Canonical Frames
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
      GUI        Command       Agent
        │           │           │
        └───────────┼───────────┘
                    ▼
               SAME FRAME

也就是说：

你看到的是：

00:00:17:18

你按一次右键：

frame + 1

Claude 说：

+12 frames

Core、GUI、MCP 全都在说同一件事。

GUI-02 我建议拆成 8 个小阶段
02-A：Sequence Timebase UI

先把 Project 的：

fps_num
fps_den
width
height
timebase

真正变成 GUI 的基础状态。

不要：

const FPS = 30

这种。

必须：

project.sequence.timebase

成为唯一来源。

支持至少：

24
25
30
30000/1001
60

而 Foundation 当前已经支持这些帧率类型。

02-B：Playhead Frame Model

当前：

playhead: number

以后应该逻辑上变成：

playheadFrame: int

UI：

00:00:17:18
Frame 528

还可以显示：

528 / 30fps
02-C：Timeline Layout 改成 Frame → Pixel

这是非常重要的一次底层 GUI 改动。

现在是：

seconds × pxPerSec = pixel

改成：

frame × pxPerFrame = pixel

也就是：

Frame
  ↓
Timeline Layout
  ↓
Pixel

Foundation 已经明确要求 Frame 成为 canonical editing representation。

02-D：Frame Ruler

时间尺不能只显示：

00
05
10
15
20

而应该根据缩放级别动态显示。

例如远景：

00:00     00:05     00:10

放大以后：

00:10:00
00:10:15
00:11:00
...

再放大：

00:10:00:00
00:10:00:05
00:10:00:10
...

最终：

用户可以放大到“帧级切点”。

不是要求任何时候都显示每一帧。

而是：

缩放级别决定尺的显示密度。

02-E：Frame Step

这个必须严格。

键盘：
←       -1 frame
→       +1 frame

Shift←  -10 frames
Shift→  +10 frames
J/K/L

遵循 Core keymap。

而不是 App.tsx 再自己定义。

Foundation 明确要求键盘绑定来自 Core contract。

02-F：Frame-accurate Trim / Split / Move

这是最关键的实际编辑能力。

Trim

拖边缘：

frame 528
→
529
→
530

绝不能：

17.5
17.6
17.7
Split

Playhead 在：

Frame 1038

按 Split：

Clip A
[0, 1038)

Clip B
[1038, end)

Core 负责：

timeline frame
↓
TimeMap
↓
source frame

GUI 不计算 source position。Foundation 已明确规定这一点。

02-G：Snap Engine 接入 GUI

这一批必须把现有 GUI 自己的 Snap 删除/收敛。

只有：

SnapEngine

可以决定吸附。

目标包括：

Clip Start
Clip End
Playhead
Selection Edge
Marker
Subtitle Boundary
Word Boundary
Beat

Foundation 已经定义了完整目标集合。

GUI 只问：

snap(frame, context)

然后渲染结果。

02-H：Frame Debug / Inspector

我强烈建议这一批加入一个非常小但非常有用的 Debug UI：

选中一个 Clip：

Timeline Start
00:00:17:18

Frame
528

Source Start
1042

Source End
1214

FPS
30

Duration
172 frames

这样你一眼就可以验证：

GUI 显示的东西到底是不是 Core 正在使用的东西。

这对开发阶段特别重要。

GUI-02 有一个非常重要的禁区
不要同时做：
Multi Selection 重构
Ripple Trim
Slip/Roll/Slide GUI
Composite Preview
Audio waveform 编辑
Subtitle Timeline
Story Beat UI
AI UI

这些全部等下一批。

原因很简单：

Frame Model 是坐标系。

先把坐标系统一。

再往上挂东西。

我甚至建议 GUI-02 按这个顺序施工
02-A
Timebase

 ↓

02-B
Playhead Frame

 ↓

02-C
Frame → Pixel Layout

 ↓

02-D
Frame Ruler

 ↓

02-E
Keyboard Frame Step

 ↓

02-F
Frame Trim / Split / Move

 ↓

02-G
SnapEngine

 ↓

02-H
Frame Inspector

每一步都测试。

这次的验收标准也改变

不能再只：

tsc 0 errors

而必须至少有这些 GUI Reality Tests：

FGUI-01

24fps：

→

移动恰好 1 frame。

FGUI-02

30fps 同样测试。

FGUI-03

29.97fps。

FGUI-04

50/60fps。

FGUI-05

Frame Trim：

只裁 1 frame。

FGUI-06

Frame Split：

在精确 frame 分割。

FGUI-07

Frame Snap：

Clip 边缘吸到 Playhead。

FGUI-08

Keyboard：

← / → / Shift+← / Shift+→。

FGUI-09

GUI Frame 与 Core Frame 一致。

FGUI-10

Undo / Redo。

最重要的测试：不同 FPS

比如：

30fps
00:00:10:00

之后：

00:00:10:01

差 1 frame。

25fps

同样：

00:00:10:00
→
00:00:10:01

但秒数变化不同。

29.97fps

尤其要验证：

不能偷偷转换成 30fps。

还有一个我希望这次 Claude Code 特别注意的地方

现在 Core 已经拥有：

FrameTime
FrameRange
TimeMap
Keyboard
Snap

所以：

GUI-02 的目标不是再造这些东西。

而是：

把这些 Core capability 消费起来。

这应该成为本批的架构护栏：

GUI
❌ 自己算 frame
❌ 自己算 source time
❌ 自己实现 snap
❌ 自己实现 keymap

GUI
✅ consume Core
✅ render Core result
✅ send Intent

Foundation 的原则正是：

GUI 负责表达，Core 负责决定。

给 Claude Code 的施工指令

我建议你现在直接把下面这一段交给它：

GUI-02 — Frame-Native Timeline

GUI-01.5 已验收。现在进入 GUI-02。

唯一施工依据：YROLL Editor Foundation v0.2.md。

目标：把当前 GUI 从 seconds-first Timeline 改成 frame-native Timeline。FrameTime / FrameRange / TimeMap / Keyboard / SnapEngine 全部复用现有 Core 能力，禁止在 GUI 重写这些逻辑。

Scope
Sequence Timebase 从 Project/Server canonical state 注入 GUI；禁止硬编码 30fps。
Playhead 内部 canonical state 改为 frame。
Timeline layout 改为 frame → pixel；seconds 只用于显示/兼容。
Timeline ruler 支持根据 zoom 动态显示 time/frame 信息，放大后达到 frame-level inspection。
主时间码支持 HH:MM:SS:FF。
Frame step：
←/→ = ±1 frame
Shift+←/→ = ±10 frames
J/K/L 等按 Core /keyboard/keymap contract 执行。
Trim / Split / Move GUI 操作全部以 frame 为语义单位。
Split 时 GUI 不得自行进行 timeline→source 时间换算；必须调用 Core TimeMap。
Snap 所有 GUI 路径统一使用 Core SnapEngine，删除/旁路现有 App/ClipBlock seconds-based snap。
增加一个开发期 Frame Inspector，显示当前 playhead、clip timeline range、source range、FPS、duration frames。
Strictly out of scope

不修改 Selection Model、Mutation Engine、Slip/Roll/Slide、Composite Preview、Audio、Subtitle、Story/Beat、AI UI。

这些已有 Core 能力只允许在必要处调用，不进行功能扩张。

Hard invariants
Frame 是 GUI 编辑 canonical coordinate。
GUI 不得 seconds * pxPerSec 作为 canonical timeline layout。
GUI 不得自己做 source/timeline mapping。
GUI 不得自己实现 Snap。
GUI 不得自己维护另一套 keyboard semantics。
不允许出现 silent fallback 到 30fps。
Tests first

增加 GUI tests covering 24/25/30/30000/1001/60 fps，以及 ±1/±10 frame keyboard、1-frame trim、frame split、frame snap、Undo/Redo、GUI/Core frame agreement。

Completion criteria

必须报告：

修改文件
新增/修改 API contract
seconds-based paths removed or downgraded to display-only
Core capabilities consumed
vitest
tsc
pytest regression
GUI smoke
frame-specific test results
明确列出 implemented but not human-verified 项

不要以“时间码显示成 HH:MM:SS:FF”作为完成标准。

完成标准是：GUI 的实际剪辑操作以 Frame 为 canonical coordinate，并且 Core/GUI/Agent 对同一切点得到完全一致的 frame result。