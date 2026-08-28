# YROLL AI 产品蓝图（对话整理终稿）

> 来源：`chatgpt-conversation-6a815662-1787490203014-整理版.md`（210 条消息，2026-08-16 ~ 2026-08-23）
> 整理原则：只保留最终成立的结论；被后面否定/取代的内容集中收录在文末附录；重复论点只保留最完整的一次表述。

---

# 第一部分：产品定义

## 1.1 一句话定义

> **YROLL AI：一个泛来源素材与工程的人机共创视频生产平台——让一个人成为一支视频生产团队。**

- Y = Y 轴理解轴 / Why（为什么这么剪）；ROLL = roll camera / 持续滚动生产。
- 不是 AI Video Editor，不是 AI Video Generator，而是 **AI-native Video Production Environment（AI 原生视频生产环境）**；编辑器只是其中一个执行层。
- 卡位：**所有视频生产方式（拍摄/AI 生成/旧工程/外部 AI 工具产物）最终汇聚成可发布成品之前的统一工作环境**（Final Production Layer）。

## 1.2 最高判断标准（所有功能取舍的唯一标尺）

**最方便、最快、最低成本、最符合人的意愿地产出可发布成品。**

判断任何功能该不该做，只问一句："它有没有直接帮助用户更方便、更快、更省钱、更符合意愿地完成一个可发布的视频？"

- 产品价值四词：**快**（减少等待反复）/ **省**（人工、AI 费用、资源、沟通）/ **准**（时间定位、空间框选、直接操作、精确表达）/ **顺**（AI、人、素材、生成、剪辑、审核在一个工作空间连续流动）。
- 成功标志："以后你无论从哪里生产素材，最后都不用离开 YROLL。"

## 1.3 产品哲学（不可违背）

1. **AI-native，但不是 AI-dependent**：AI 宕机/断网/没额度时，Timeline、手动编辑、本地工具、已有 Project Memory 全部照常。"AI 是外挂驾驶系统，但方向盘、刹车、发动机都属于车本身。"
2. **Intelligence Routing First（够用即可，保持克制）**：不是 AI First——能纯代码解决不上模型，能本地解决不上云，能便宜解决不用贵的。"AI 时代最大的风险不是能力不足，而是能力太多导致系统失控。"
3. **素材平权（Source Agnostic）**：不关心素材是拍的还是生成的、照片还是视频，只关心最终效果与问题解决。"AI 时代，照片想成为视频，也只应该是一键的事。"
4. **人决定方向，AI 负责实现**："人负责确定想去哪、必要时转动方向盘调整方向，没必要理解方向盘助力、传动轴和发动机的工作细节。" 与自动成片软件的根本区别：自动成片是"AI 觉得这样比较好"，YROLL 是"人决定方向，AI 把方向变成结果"。
5. **不为花架子付费**：不做虚假展开动画、不堆模板素材库、不为差异化而差异化。"AI 时代找到最合适的 3 个方案，胜过 10 万个模板。"
6. **问题驱动，而非功能驱动**：Feature Backlog 不是"AI 抠图/AI 扩图"功能列表，而是 Problem #001 声音太小、#002 字幕错字……每个问题下挂现有办法/默认办法/备用办法/成本/UI/工具/模型。用户不会说"调用 video inpainting"，用户说"这个杯子太大"。

## 1.4 核心创新：X/Y 双轴模型

- **X 轴 = 时间线 = 成品空间**：审核、修改、整合、输出成品；相当于剪映的功能，人可完全手动操作。
- **Y 轴 = 语义/逻辑空间 = Clip Workspace**："这个结果为什么是这样，以及还能怎么变"；相当于把可灵/Runway/ComfyUI 等生成与局部修改平台全部集成进来，终结"抽卡生成→下载→导入剪映"的割裂流程。
- 金句："X 轴保存'影片是什么'，Y 轴保存'为什么是这样，以及还能怎么变'。""X 轴是答案，Y 轴是过程。"
- 五角色闭环：
  ```
  X：最终成片是什么？  Y：怎么得到这个结果？
  Semantic Layer：发生了什么？  AI：下一步该做什么？  Human：这样好不好？
  ```

## 1.5 五层角色 / 三大核心

三大核心：**Project Intelligence**（为什么做/给谁/表达什么）、**Human-AI Co-editing**（AI 做 80% 人修 20%）、**Production Memory**（一次项目经验变成下一次能力）。

核心循环：
```
理解项目 → 理解素材 → 理解目标 → 制定方案 → 生成/剪辑 → 人审核 → AI修改 → 沉淀经验 → 下次更聪明
```

---

# 第二部分：架构

## 2.1 总架构（定格版）

```
任何来源（手机/相机/剪映/PR/DaVinci/AI平台/ComfyUI/Claude Code/KrillinAI/Shotcraft）
   ↓ Import / Normalize（Adapter + OTIO/IR + Evidence Fusion，代码优先）
   ↓ Recover / Understand（R0-R5，置信度透明）
YROLL Manifest v0.1（内部统一对象模型）
   ↓
X Timeline + Y Clip Workspace（同一 Project Model，两端不同呈现）
   ↓ Unified Editing Command Layer（人/手机手势/AI 都走同一 Command API）
   ↓ Generic Agent Runtime（Codex Harness 为候选基座）+ Video Domain Layer（自持）
   ↓ Problem → Solution Routing（L0 简单→L1 本地→L2 高级 AI→L3 重生成）
Human ←→ AI 连续驾驶（Manual/Assist/Co-pilot/Auto，Current Project Truth）
   ↓
Final Production Package（Video+Cover+Title+Copy+Tags+平台版本+成本报告）
```

## 2.2 七层架构

```
7. HUMAN EXPERIENCE LAYER   GUI/Timeline/Preview/AI/Support
6. PROJECT INTELLIGENCE     Narrative/Semantic/Memory/Review
5. AI HARNESS               Agent/Context/Tools/Skills/Tasks
4. AI SERVICE & COST        BYOK/Official/Router/Credits
3. VIDEO DOMAIN RUNTIME     Editing/Understanding/Generation
2. PROJECT CORE / MEDIA     Project/Timeline/Asset/Render
1. PLATFORM                 OS/GPU/FFmpeg/Storage/Network
```

## 2.3 架构铁律

1. **AI 不是底盘**：Core Editing Runtime 必须完全独立运行，AI Runtime 不能成为 Project Core 的依赖。连接方式必须 `Human → Core API` 且 `AI → Core API`，而不是 `Human → AI → Core`。
2. **人和 AI 调用同一个 Project API**：GUI、手机手势、内置 Agent、外部 Claude Code/Codex（经 MCP）全部走同一个 Unified Editing Command Layer（trim_clip()/move_clip()/change_volume()/edit_subtitle()/transform_object()/replace_segment()……）。Undo/Version/Log/Cost/跨端/MCP 因此自然统一。
3. **Every mutation must have provenance**：每次修改进 Operation Log（谁/何时/对什么/原来什么/变成什么/为什么/工具/模型/参数/成本/是否人审核），取代 Undo/Redo，支持语义化撤销（"把 AI 刚才对 12~15 秒做的修改全部撤掉""回到昨天下午的版本但保留字幕修改"）。
4. **AI Context 永远动态选择**，不把整个工程塞给模型。
5. **人永远可中断、修改、接管**；AI 写操作走 Plan → Preview → Approve → Apply。
6. **Timeline 是 X 主坐标，Y 不允许吞掉 X**。
7. **离线时核心编辑能力完整可用**。

## 2.4 AI Harness 双层结构（系统灵魂，最大技术风险点）

```
        AI Harness
   Generic Agent Runtime   （不懂视频：Session/Context/Tool Router/Permission/Log/成本）
            |
   Video Agent Runtime     （视频领域：Video Context/Timeline/Scene/Asset/Problem/Generation）
            |
   Editor / Generation Tools
            |
        Project Core
```

- 原则："Generic Harness 不懂视频；Video Runtime 不需要重新发明 Agent。"
- **Generic Agent Runtime 候选基座：OpenAI Codex Harness**（2026-08-19 开源，Apache-2.0；官方分工思想与 YROLL 一致：应用管 UI/上下文/工具/审批，Harness 管 agent loop/工具调用/状态/审批）。不换皮、不让"代码思维"污染 Video Domain。
- 三要素论："Harness 提供能力，Object Model 提供世界，Skills 提供经验，三者缺一不可。"
- 工具原子化：不做 edit_video() 大工具，做 get_clip_info/split_clip/move_clip/change_parameter 等约 20 个原子工具，AI 负责组合。
- Agent 工作循环：`Observe → Understand → Plan → Execute → Verify → Update Memory`。
- 权限三级：低风险直接执行（改字幕/音量/亮度）→ 中风险询问（删镜头/换素材）→ 高风险必须确认（重构剧情/大量生成）。
- 关键子模块：Context Manager / Attention Manager（必须独立）/ Tool Registry（动态加载，按问题只开放相关工具）/ Skill Manager / Permission / Review-Approval / Operation History / Cost Manager / Model Router / Evaluator。
- Skill 化架构：软件本体很小，高级能力做成按需加载的 Skill（婚礼/茶产品/小红书/电商……）。Skill = Prompt + Workflow + Tools 组合 + 判断规则。
- 最大技术风险：**Context Management**（"AI 什么时候应该知道什么"）。
- 用户已用 Claude Code 实证：通用 Harness + 领域 Skills 即可理解视频世界，缺的是 GUI、实时交互、人机共改同一工程。

## 2.5 Project Memory（核心资产，护城河之首）

"Project Memory 不是一个附属功能，而是 AI Harness 能否真正成为视频领域 Agent 的基础。""核心资产不是模型，而是 Project Memory。""AI Harness 决定 AI 能不能行动，Project Memory 决定 AI 能不能长期合作。"

```
Project
├── Media / Timeline / Shots（镜头+语义+embedding）
├── Entities（Characters / Objects / Locations，含 Scope 分层 Global→Brand→Project→Sequence→Shot）
├── Story（AI 建议、人确认）
├── References / AI Memory（风格/禁忌/偏好）
├── Generation History / Decision Logs
```

- **经济模型**："AI 分析一次，长期使用。"第一次 100 个视频深度理解花 ¥5，之后"找茶壶/缩短第三段"≈¥0。Project Memory 把一次性的昂贵理解变成长期便宜的查询。
- **Creative Memory / Project DNA**：项目结束时 AI 主动总结"哪些值得留下"（节奏/色调/人物/调性/钩子/配乐/字幕），与用户确认后沉淀；项目间人物资产隔离，方法可进 Studio Style Memory。"不是记住这个人，而是记住这个方法。"
- 存储：SQLite + 向量库（sqlite-vss/Chroma/LanceDB），目录式工程（project.json/memory.db/timeline.json/decisions.json/assets/cache/generated），不是单个巨大文件。

## 2.6 多阶段视频理解 Pipeline（成本控制核心）

不是"每秒抽帧发大模型"：
- Stage 0 本地媒体扫描（ffprobe，成本 0）
- Stage 1 镜头切分（PySceneDetect/TransNetV2，CV 算法）
- Stage 2 关键帧抽取（每 Shot 首/中/尾 3-10 帧）
- Stage 3 本地视觉模型初筛（CLIP/YOLO/SAM/Whisper/OCR……生成 caption/objects/embedding）
- Stage 4 高级 LLM 理解（只预设接口，前期不用；后期做成 Skill 插件升级）

剪辑后不重新分析：`Original Semantic Timeline → Timeline Transform → Current Semantic Timeline`（增量映射）。手机端同理三级：本机确定性/轻量 AI → 服务器本地模型 → 云端大模型（按问题升级，非默认）。

## 2.7 YROLL Manifest v0.1（内部统一对象模型，第一天就要做）

Project 包含：Assets / Timeline / Clips / Audio / Text / Objects / Relationships / Operations / Versions / AI Context / Generation / Problems / Solutions / Publishing / extensions。

- **Asset**：一切来源统一为 Asset，来源只是 Origin 属性。
- **Clip**：时间轴上的使用实例（asset_id + source_range + timeline_range + current_state + context + relationships + versions）；同一 Asset 可被多个 Clip 复用。
- **Timeline 只记录最终作品结构；Semantic Relationship 是 Project 下并列的 Relationship Graph**（两者分开）。
- **Relationship**：`{source, target, relation:strong/medium/weak/independent, confidence, scope}`。
- **Operation**：一切有意义修改都是 Operation。
- **Problem / Solution 是一级数据对象**：Solution 带 route(L0-L3)/tool/cost/duration——"Problem→Solution→Tool 真正变成了数据"。
- **Generation**：provider/model/prompt/references/workflow/cost/duration。
- **Version 不复制项目/素材**，只存元数据 diff（Git 式）：`current.json + operations/ + versions/ + media/`。
- **Publishing**：视频版本/封面/标题/正文/标签/平台——"完整的上传前成品包"进入数据模型。
- **extensions 机制**：`extensions:{jianying:{}, premiere:{}, comfyui:{}}`——"YROLL Core 不被任何旧软件绑架，永远不要为了导入旧工程污染 Core。"

## 2.8 视频 = 语义关系网络（Semantic Link）

"剪映的问题本质不是缺按钮，而是它仍把视频看成轨道集合；下一代系统应该把视频看成一个语义网络。"

- Semantic Link 四级：**Strong**（自动同步）/ **Medium**（提示用户）/ **Weak**（默认不动）/ **Independent**（绝不自动修改）。字幕分型（Speech Caption/Title/Annotation/Decoration）、音频分型（Voice 强 / Ambient 中 / BGM 弱 / SFX 中~强）。
- **Impact Preview**：修改前告诉用户将发生什么——"即将修改：✓视频删3秒 ✓人声同步裁剪 ✓字幕重对齐2条 ◇倒茶音效建议删除 ×BGM不受影响 [应用全部][调整方案][查看详细影响]"。
- "YROLL 真正需要智能的地方，不是每次帮用户生成什么，而是判断一个操作会影响谁、应该连带改变什么、什么应该保持不变。"
- 视觉规范：默认不显示全部关系线；选中 Clip 显示关系胶囊（🔗人声 🔗字幕 ◇音效 ○BGM），点击展开连线；线型粗细为主、颜色为辅；轨道始终存在，非工作轨窄化、工作轨加宽。
- **离线照常工作**："AI 负责建立理解，普通系统负责执行已确定的关系"（AI 分析一次，长期使用）。

## 2.9 Capability Manager / Router / Harness 三层分离

- **Capability Manager** 回答"能不能做"（纯确定性，断网也能跑）
- **Router** 回答"用哪种方法做"（成本/速度/质量路由）
- **Harness** 回答"用户想解决什么问题、怎么组织复杂任务"

降级顺序：Cloud AI → Local AI → Deterministic Tool → Manual。"Harness 可以死机，YROLL 依然能剪视频。"

## 2.10 Tool Registry

Tool ≠ UI 功能。统一规格：`tool_id/category/level/offline/input/estimated_time/estimated_cost/risk/reversible/preview/affects`。四层分开：**Problem → Capability → Tool → Provider**（如 video.inpaint 可有本地 ComfyUI/云 API 多个 Provider，Router 决定）。

首批工具族：video.trim/split/move/speed/transform；selection.target（统一时间+空间+羽化作用范围）；audio.gain/normalize/denoise/ducking/replace_segment；voice.clone_context/generate_segment；text.correct、subtitle.retime/resegment；object.segment/track/transform/remove/replace；image.generate/edit、video.generate/inpaint/extend（这些是"可插拔执行器"，不是 YROLL 核心产品）。

"Tool 是怎么做，Skill 是什么时候做、怎么判断、注意什么。"

---

# 第三部分：核心交互设计

## 3.1 Timeline Clip 上下双层模型（用户确立）

```
Clip Container
┌────────────────────────┐
│   AI Context Layer     │  ← 上 1/3：点击=打开 Clip Workspace；
│                        │     按住横向拖动=框选本 clip 的时间段，跳出 Y 轴
├────────────────────────┤
│   Edit Layer           │  ← 下 2/3：点击=选中 clip；点击后拖动=移动 clip；
│                        │     Trim/Split/Speed/Volume/Opacity/Crop/Color/Subtitle
└────────────────────────┘
```
"普通操作保持传统剪辑习惯，AI 操作自然向上展开。AI 永远在那里，但默认不打扰。" 80% 日常修改留在 Timeline，20% 复杂修改进入 Workspace。

## 3.2 Clip Workspace（Y 轴五层）

```
1. Current State   当前预览 + 版本号
2. Origin          原始来源（文件、拍摄时间、设备）
3. Creative Intent 为什么存在（Purpose/Emotion/Style/Hook）
4. Generation Chain 生成链（Prompt→模型→参数→Image→Video→Edit）
5. Operations      操作历史（Git 式版本树）+ AI Actions（改 prompt 重生成/局部重绘/回滚/分叉/替换）
```

Y 轴三态：Collapsed / Context / Workspace。UI 由 Problem Matrix 推导生成——"问题驱动 UI，而不是功能驱动 UI"。

## 3.3 三维选择模型（Semantic Selection）

**Temporal Selection × Spatial Selection × Semantic Selection**：框时间 + Preview 画面框选空间区域（矩形框、多框、自动编号：[1]茶壶 [2]手）+ 语义定位对象（"右边那个人的左手"）。统一为 Selection Object：
```
Selection { timelineRange, spatialRegion, semanticTarget, trackIds, assetIds }
```
"用户不是操作素材，而是指出自己想解决的问题。"——"1 号框里的茶具太大，缩小三分之一。"

## 3.4 Direct Manipulation + AI Execution（Intent First Editing）

```
框选 → 生成临时浮动图层 → 人直接移动/缩放/旋转（实时预览，纯合成无需生成）
     → 确认后 AI 理解空间意图 → 生成 mask/prompt → 局部重绘/补背景/融合 → 新版本替换
```
"不是告诉 AI 怎么做，而是告诉 AI 你想看到什么。" V1 做交互框架记录意图，V2 加对象识别自动 mask（SAM2），V3 真正对象级编辑。

## 3.5 Problem → Solution 闭环（产品灵魂）

Harness 接受的不是"生成视频"，而是 **Problem**：
```
AnalyzeProblem → FindCause → RecommendSolutions（带成本/时间/风险标注，默认推荐最低成本）
→ Execute → Preview 验证 → 写入 Y 轴历史
```
- Problem 三来源：Human Feedback（最高价值）、AI Review（发布前审核）、数据反馈。
- 方案示例："A 直接裁切 ￥0 / B 本地 AI 去除 ￥0·15秒 / C 云端重绘 ￥0.18·40秒 / D 重新生成镜头 ￥1.20·2分钟，推荐 A"——"它知道什么时候没必要用 AI。"
- 核心按钮是 **Solve / Ask AI**，不是 Generate。"Generation 是 Tool，Problem Solving 是 Product。"

## 3.6 修改成本分级（Intelligence Routing）

```
L0 参数调整（scale -30%）         成本 0
L1 局部编辑（mask + inpaint）     低
L2 重新生成（image/video model）  高
L3 重新设计镜头                    最高
```
所有局部修改默认带 `Mask → Feather → Blend → Temporal Consistency`（自动羽化，时间范围自动外扩）。

## 3.7 问题分类库 v0.1（按痛点排序，用户修正版）

```
A. Temporal   时间问题（P0：长度/节奏/停顿气口/衔接）
B. Audio      音频问题（P0：局部音量/降噪/跨 Clip 人声统一/音画一致）
C. Text       文本问题（P0：错字/同步/断句/遮挡/水印/文画一致）
D. Visual     画面问题（P1：光影/色彩统一/清晰度/抖动）
E. Spatial/Object 空间对象问题（P1交互/P2执行：位置/方向/尺寸/外观/增删替换，
              人与商品统一为 Object——处理逻辑接近）
F. Semantic   语义问题（内容相关/信息密度/卖点表达）
G. Consistency 一致性问题（跨 clip 与跨 timeline 的视觉/音频/文案/品牌）
H. Asset/Origin 素材来源（前世今生可追溯）
故事/情绪归入 Project 层（P3，柔性，后做）。
```

## 3.8 人机协作协议

- 四种驾驶模式：**Manual / Assist / Co-pilot（默认）/ Auto**，自动化程度与成本意愿独立（Automation Level × Resource Preference × Quality/Time），随时切换、随时接管。AI 从新的 Current State 接着做（Current Project Truth），不会因人改了一下就重新生成整条视频。
- AI 修改三阶段：Plan → Preview（左右对比/虚线版本）→ Apply（类比 Git：diff → review → merge）。
- Decision Log 为一级对象；Semantic Undo；AI 修改必须带 Scope（默认最小范围）。
- 时间线导航：双刻度（上层精细/下层大尺度）+ 滚轮以鼠标位置为中心缩放（Google Maps 式）+ 鼠标距离非线性速度 + 语义跳转（"跳到虎哥第一次拿壶"），不需要辅助键。
- UI 分层显示：Normal → Explain → Developer；"默认隐藏复杂性，复杂性按需展开"。Context Panel 做成半透明黑色浮层，不破坏布局。统一会话框可查看全部沟通历史。
- 用户只面对一个 **AI Director**；多 Agent 是隐形能力模块，不暴露成"员工"。
- Support Agent（客服，免费不耗 Credits，只读产品知识库，与用户内容默认隔离）与 Director Agent（改项目，消耗 Credits）分离。

## 3.9 Timeline 级智能

Audio Master Layer（统一音量/响度/音色）、Text Layer Intelligence（跨 clip 字幕合并/断句/查错）、**Timeline Health Check**（导出前 lint：字幕错字/音量/黑帧/人声突降/水印/穿帮/开头 3 秒/时长合规）、Release Report（发布前 AI 审核：内容/视觉/节奏）。

---

# 第四部分：导入与兼容

## 4.1 定位：AI Video Production Compatibility Layer

不是万能格式转换器，是"AI 视频生产兼容层"：**不追求"打开"别家工程，而是解析、抽象、投射成 YROLL 对象；无法还原的识别、重建或降级。**

ADR：External Project Recovery——
```
Convert ↓ Rebuild ↓ Flatten ↓ Ignore（而不是 Open or Fail）
```

Recovery Level R0-R5：R0 直接原生解析 / R1 标准交换格式转换 / R2 证据融合恢复 / R3 AI 辅助重建 / R4 只恢复可用媒体 / R5 无法恢复。兼容度不用百分比宣传，用分维度 **Project Recovery Report**（"视频100%/字幕96%/特效41%/AI可重建18项"）。

## 4.2 关键决策

- **OTIO = Timeline Interchange Layer（交换中间层），不是内部模型**（OTIO 不管 Prompt/Problem/Solution/Cost）。
- **剪映**：最重要的迁移入口，但只是普通 Migration Adapter。未加密老草稿（≤5.9，pyJianYingDraft 已验证）可做第一批实验；6.0+ 加密草稿不碰解密，走外围证据 + 用户导出（User-assisted migration）。"不要一开始花两个月逆向剪映 6.x。"
- **只导入不导出剪映工程**（用户明确否定回流）。
- PR/DaVinci/FCP 走 OTIO/FCPXML/AAF/EDL；不追求 100% 还原（Adobe 自己都做不到）。
- **Evidence Fusion**：素材本身（Hash/EXIF）→ 草稿外围伴随文件 → 用户旁证 → OCR/ASR/CV 反推 → 用户导出公开格式；不同证据带可靠度标注。
- **import-normalization.skill**：Detect→Parse→Normalize→Recover→Interpret→Map→Validate；前 90% 是确定性代码，必要时 AI 才介入。
- "没有上下文也可以进来"——裸 MP4 直接可用，绝不设格式门槛。
- 外部 AI 工具（KrillinAI/video-shotcraft 等）= 外部能力提供者，**我们接着处理它们的产物，不是替换它们**。前期主动兼容别人，生态起来后别人自然输出 YROLL Manifest。"标准是做出来的，用的人多了就是标准。"

## 4.3 成品反推（降级为长期能力）

用户基于实操经验降温："去成品字幕最难、模型大、效果不满意，不要早期死磕。"轻量版保留为 **Finished Media Indexing**（镜头切分/缩略图/ASR/基础字幕/场景标签/可搜索索引），不承诺去烧录字幕；数据模型预留 RecoveredAsset/RecoveredClip + confidence 字段。

**核心能力 vs 增长能力**：核心 = 新素材+新项目+人机共创+问题解决+成品输出；增长 = 旧工程导入/成品恢复/外部适配。"先把新房子盖好，再考虑怎么把老家具搬进来。"

---

# 第五部分：跨端架构

**One Core, Multiple Interaction Surfaces / "一个 YROLL，两个驾驶舱"**：

```
                    YROLL Core（共享 Project/Manifest/Command Layer/Harness/Version/Cost）
        ┌────────────────┴────────────────┐
   Desktop（工作站）                   Mobile（移动驾驶舱）
   Editor First·精确操控·大屏鼠键      Intent First·AI 协作更重·触控+语音
   PC：AI 主要代替手                   Mobile：AI 主要代替技术门槛
```

- 共享的不是云同步，而是 **Same Project Model / Project Truth**；X/Y 数据模型不变，像素布局可变。
- Mobile 原则：不硬塞专业面板；屏幕只显示当前最需要决策的两三个方案（Solution 卡片）；竖屏 Y 轴天然更长可能是优势；语音用系统输入法语音转文字，价值在"语音+当前选区+框选上下文"融合。
- Mobile Harness：Lightweight Client + Agent Gateway；本地做确定性编辑，视觉理解上服务器，生成上 Provider。
- **Local First + 离线降级**：断网→Local Core→Manual/Basic AI；离线可建 Pending AI Task，联网自动执行；服务器永不成为单点故障。
- 跨端四件套（第一天就要考虑）：**Project Manifest + Understanding Cache + Capability Manager + Solution Router**。

---

# 第六部分：商业模式

```
┌──────────────────────────────┐
│        免费核心编辑器        │（Timeline/手动剪辑/多轨/字幕/本地素材/离线/已有AI资产）
└──────────────┬───────────────┘
               ↓ 可选
┌──────────────────────────────┐
│          AI Services         │
└──────────────┬───────────────┘
        ┌──────┴──────┐
        ↓             ↓
     官方套餐       BYOK（不扣平台额度）
```

- **基础剪辑永久免费**（类剪映）；AI 能力按统一 **AI Credits** 收费（用户只看到一个额度，内部细分 LLM/VLM/Image/Video/Audio）；额度包：3天/7天/30天/年。
- **BYOK 不扣额度**；Provider Priority：用户 API 有该能力→走用户 API，没有→官方。两者不互相污染。官方提供默认 LLM/视频 API，用户只付一份费用。
- 硬承诺：**"用户永远不能因为 AI 额度耗尽而失去自己的项目。"**
- **Cost-aware Problem Solving**：AI 是"成本敏感的问题解决器"，方案带价格标签，先选最便宜方案。用户可设"最快/最佳质量/成本最低/平衡"策略；问法："省 1 分钟人工，你最多愿意多花多少 AI 成本？"
- **Cost Visibility 三级**：默认不显示 / 工程完成后汇总（AI 成本明细+节省人工）/ 专业实时；可设提醒阈值。导出 **AI Cost Report**（"本项目 AI 成本 ¥3.82，节省人工 2.5 小时，¥1.52/分钟"）——本身可做社媒营销素材。
- AI Cost Report + Export Package 让用户"感慨甚至感激，想晒一晒"。

---

# 第七部分：导出与发布

**导出不是导出视频，而是 Final Production Package**：
```
Final Production Package
├── Video（多平台 variants：抖音版/小红书版/视频号版——一个 Master Timeline + 多个 Output Profile，只是 diff JSON）
├── Cover（自动选帧+AI 生成）
├── Title / Description / Tags（按平台输出 Markdown，一键复制）
├── Project record
└── Cost / Time report
```

---

# 第八部分：用户与市场

- 目标用户不是"创作者"而是"**视频生产者**"：所有需要持续生产视频但没有专业影视团队的人。
  - Tier 1 高频短视频运营团队（连锁餐饮/茶品牌/教培/门店/工厂/医美）、Tier 2 个人职业创作者、Tier 3 小型内容工作室（婚礼定位"活动视频快速生产"，**排除婚纱摄影**——调色美颜竞争不过）、Tier 4 电商团队。
  - 排除：普通家庭用户（频率太低）、专业影视公司、AI 短剧批量生成团队。
- **MVP 按能力切，不按行业切**；默认工作流为"视频项目助手"。
- 种子用户 100 人：20 影响力 + 60 高频 + 20 专业；找粉丝多的人送积分/VIP 换反馈宣传。
- 三大使用场景：A 从零创作（Script→Shot→生成，轻量内置，不与短剧平台竞争）/ B 素材→成片（旅游/婚礼批量素材自动成片，可能是 MVP 级场景）/ C 已有成片→AI 辅助完善（70→95 分循环，最能体现 Co-editing）。
- 真正的竞争对象是"剪映+Claude+ComfyUI+各 AI 平台+人脑"的**散装工作流**，核心痛点是上下文不断丢失。
- 护城河五层（"离开很可惜，而非离不开"，不做数据锁死）：① Video Project Memory ② Human-AI Co-editing Experience ③ Asset Intelligence（Asset Identity：MD5/时长/内容特征，素材移动后自动找回——"你的工程永远不会丢素材"）④ Workflow Memory ⑤ Domain Skills。**最终精炼：问题解决知识 + Project Memory + Harness + 人机共创工作流**——不是靠更多模型/特效/模板。
- 防大厂：不防复制功能，建立"不容易复制的东西"——细分工作流理解、明确人群切入、项目记忆迁移成本。

---

# 第九部分：竞品终局判断

| | OpenCut | OpenChatCut | YROLL |
|---|---|---|---|
| 核心定位 | 开放式剪辑器基础设施 | Agent-native AI 剪辑器 | **AI-native 视频生产环境** |
| AI 角色 | 编辑器的 AI 扩展 | Agent 直接参与剪辑 | **生产流程的主要组织者** |
| 人机关系 | 人+AI 编辑 | AI+人共同编辑 | **自动驾驶↔人工接管连续体** |
| Y 轴 | 无 | 有但非核心模型 | **Clip Workspace/Problem-Solution 空间** |
| Problem→Solution | 非核心 | 有雏形 | **产品一级对象** |
| 成本路由 | 非核心 | 非核心 | **核心机制** |
| 输出 | 编辑器导出 | 编辑器导出 | **Final Production Package** |
| Mobile | 一等公民 | 桌面为主 | **Intent-first 驾驶舱** |

- 差异本质：底层结构必然相似（Media→Timeline→EditorCore→Agent→Tools），正确说法是"**OpenChatCut 已实现 AI-native Editor；YROLL 要把 AI-native Editor 升级成 AI-native Production Environment**"。
- 策略："不要做比 OpenChatCut 功能更多的软件，而要做比它更完整的视频生产闭环。"不造花架子差异化；如果 OpenChatCut 未来也做了 Y 轴，没有关系。
- 研究分工：OpenCut 学 Editor Core/跨端/Plugin/Headless/API；OpenChatCut 学 Agent Runtime/MCP/Skills/协同编辑；**YROLL 的 Project Model/Harness/Problem-Solution/Y 轴/Semantic Graph 必须自持**；Editor Core 长期可外采，但必须服从 YROLL Internal Model 和 Command Layer。
- 技术参照总表：
  - **OpenChatCut**（AGPL⚠️）：EditorCore 铁律、Agent Tool 体系、MCP、Proposal→Review→Apply。深度拆代码，但**不 Fork 做商业产品**（AGPL 禁止闭源分发，SaaS 触发第 13 条）。
  - **OpenCode**（MIT✅）/ Claude Code：Generic Agent Runtime 思想（Attention/Context/Tool Registry/Permission/Compaction）。Copy Architecture, not Code。
  - **Codex Harness**（Apache-2.0✅）：Generic Runtime 候选基座。
  - **Velorn**：ComfyUI Bridge/底层骨架参考；其"编辑器+AI Tab+ComfyUI Tab"是外挂式 AI，不照搬；明确不 fork。
  - **Remotion**：渲染/Preview 引擎（商业条款需核查）；FFmpeg：底层执行层。
  - **ComfyUI**（GPLv3⚠️）：Generation Provider 之一，Adapter 模式接入，用户永不可见节点。
  - **Mr.Director**："先理解再行动"验证；其"timeline-free 是倒反天罡→转 Remotion"的教训引为佐证。
  - **Preview/OnSolo/Anijam**：Production Model（Project→Story→Scene→Shot+Characters/Props）借鉴；"一个人就是一个剧组"理念佐证。
  - **剪映**：106 条真实痛点=问题来源库（顶级诉求是稳定性+专业编辑精度），不逐条复制成功能；不复制其模板/素材生态。
  - 许可证优先级：① permissive 底层 ② 商业授权 ③ clean-room 重实现 ④ 才考虑 AGPL+SaaS。

---

# 第十部分：AI-native 的八条可验证标准

1. AI 和人操作同一个项目状态
2. AI 能从当前状态继续工作（不每次重新理解整个视频）
3. 人工操作能成为 AI 的上下文
4. AI 操作能反向成为人的操作对象
5. 所有复杂 AI 操作有最低成本路径（Simple→Local→Advanced AI→Regenerate）
6. AI 不在线，项目仍然存在并可编辑
7. AI 不是外挂聊天框，而是 Project Runtime 的一部分
8. 用户可用视觉直接表达意图（时间选择+框选+移动+缩放+旋转+语言）

客户最终应感受到：
> "我不是在教 AI 怎么剪；我只是告诉它我想得到什么、哪里不满意，AI 自己处理；我觉得不对时，我可以像普通剪辑一样直接动手；AI 再继续接着我的修改往下做。"

---

# 第十一部分：开发优先级（最终排序）

```
P0（核心闭环）：① Internal Model ② Manifest v0.1 ③ Import/Normalize ④ Timeline
   ⑤ Clip Workspace/Y轴 ⑥ Problem→Solution Matrix ⑦ Semantic Link
   ⑧ Solution Routing ⑨ Harness ⑩ Preview框选 ⑪ 基础媒体处理 ⑫ AI能力接入
P1（增长能力）：⑬ 外部AI产物 Adapter ⑭ JianYing/OTIO/FCPXML 工程导入
   ⑮ Cost/BYOK/Provider 管理 ⑯ Publish Package
P2（长期能力）：⑰ 复杂工程恢复 ⑱ 成品视频反向恢复（先只做 Finished Media Indexing）
   ⑲ 对象分层 ⑳ 高级视频重建
```

- 技术栈定案：**Tauri + React + TypeScript 前端；Python + FastAPI 后端；SQLite + 向量库；FFmpeg + OTIO；OpenAI Compatible API（GPT/Gemini/Qwen/DeepSeek/本地模型）；ComfyUI Adapter 接生成（用户已有服务器）**。
- 工程优先级（"很多人会反过来先做生成，这是最容易走偏的"）：Project Memory → Agent Tool Runtime → Timeline → Chat → Version → Preview Selection → Export Report → Generation Adapter。
- MVP 验证三问：① AI 是否真理解视频项目 ② AI 修改是否发生在同一 Timeline ③ 人是否可随时接管。成功标准：真实案例（茶产品 10 个手机视频→30 秒抖音视频）比"剪映+ChatGPT+可灵+人工切换"**快 5 倍**则项目成立。
- Demo 场景：柴烧茶器（39 照片+15 视频，真实素材）/ 手机旅游视频（200 照片+30 视频→Vlog）。
- V1 必做：Clip Context、Preview 框选、时间范围选择、传统参数修改、AI 对话定位问题、重新生成替换 Clip、版本记录。V1.5：局部重绘、去水印、去对象、字幕智能修改、音频修复。V2+：视频元素分层、对象级编辑、动作修改、人物一致性。
- V1 不做：完整特效库、大量模板、专业调色、短剧工业生产、全自动生成、多人协作、自研模型。

---

# 附录：被否定/被取代的内容全记录

> 这些内容在对话中出现过但已被明确否决，**不应再进入设计或开发**。

## 产品定位类
1. 自由画布工作流作为主形态（"ComfyUI 换皮"）→ X/Y 双轴
2. "ComfyUI+剪映缝合" → Human-AI Co-editing Workstation
3. "AI 视频编辑器/AI Video Generator"命名 → YROLL AI 生产环境
4. "YROLL 是剪映之前/之后的 AI 生产层" → 必须完全替代剪映，"如果还要用剪映就是失败"
5. "做一个更好的剪映/Premiere 替代" → 第一个真正 AI-native 的视频生产环境
6. 做 AI 短剧生成器/海量模板/花字/字体库路线 → 明确不碰
7. 为差异化造花架子（硬推 Y 轴对标）→ Y 轴因解决真实问题而存在
8. 候选名 VideoOS/CreatorOS/StoryOS/一人影厂/灵剪/影匠等 → 定 YROLL AI

## 技术路线类
9. timeline-free 的 ffmpeg 路线 → Remotion/OTIO+WebGPU timeline
10. 从零自研完整编辑器 / 直接 Fork OpenChatCut 商业化（AGPL 风险）/ fork Velorn → 学架构不复制实现，核心自持
11. OTIO 当内部 Project Model → 仅作交换中间层
12. 两层架构 → 三层 → 七层
13. LangChain/LangGraph/CrewAI 作 Runtime → 借鉴 Claude Code/Codex Harness 模式
14. 从零自造 Harness → 先深度研究 Codex Harness 作候选基座（不换皮）
15. 每秒抽帧发大模型 / 把整个项目塞给 LLM → 多阶段本地初筛 + 动态 Context
16. 保存各版本视频文件 / 单个巨大工程文件 → Git 式元数据 diff + 目录式工程
17. 传统 Ctrl+Z / Undo-Redo → Operation Log + Semantic Undo + Git 式版本树
18. 生成完即结束 / "一次生成尽量完美" → 低成本迭代审核闭环（生成只是工具）
19. 整段视频上传云端 → 本地优先 + 只上传必要局部片段
20. 自造手机语音系统 → 系统输入法语音转文字
21. 手机硬塞专业面板 / "PC版+手机低配版" → 一核两舱、Intent Interface

## 交互类
22. AI 放在独立 Generate Tab / 显眼的 Generate 按钮 / 用户挑模型挑 Workflow → Solve/Ask AI，AI 自决技术方案
23. AI 是右侧聊天框 → Context-aware 嵌入式助手 + 多入口
24. Clip 左右分区 → 上下分区（左右会被误读为时间关系）
25. Y 轴 = 历史记录/Generation Graph → Clip Workspace
26. Y 轴展开动画 → 永久取消（虚假面子工程）
27. 右侧固定 Context Panel → 半透明黑色浮层
28. 多 Agent 当"员工"暴露给用户 → 只面对一个 AI Director
29. "绑定/不绑定"轨道锁定按钮 → Semantic Link 四级关系
30. 面向用户的版本树 → 只有一个 Current + 后台 History
31. Shift 辅助键双速导航 → 鼠标距离非线性速度 + 滚轮缩放
32. 传统 Media Pool → 项目制资产（Character/Prop/Shot）

## 商业与边界类
33. 卖软件授权/订阅 → 基础剪辑永久免费 + AI Credits + BYOK
34. 每次 AI 操作都显示成本 → 阈值提醒 + 工程汇总
35. 问"人工时间值多少钱" → "省 1 分钟愿意多花多少钱"
36. 只选一个行业垂直 → 按能力切不按行业切；排除婚纱摄影
37. 数据锁死当护城河 → "离开很可惜而非离不开"
38. YROLL 导出剪映工程 → 只导入不导出
39. 逆向剪映 6.x 加密草稿 → 不做，走外围证据+用户导出
40. "支持 95% 剪映工程"式宣传 → 分维度 Recovery Report
41. "制定 AI 视频行业标准" → 内部 Manifest，"标准是做出来的"
42. 要求外部工具适配 YROLL → YROLL 主动兼容外部产物
43. 成品视频反推作前期核心/首个卖点 → 降级为长期兜底（Finished Media Indexing）
44. 故事理解/情绪/导演 Agent 等高级能力前期投入 → 推后，先把高频刚性问题做实
45. 客服 Agent 读用户项目内容 → 默认隔离，只读产品知识库
46. 追求 100% 打开 PR/达芬奇工程 → Recover/投射/降级（"格式兼容就是一句空话"）
