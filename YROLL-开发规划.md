# YROLL AI 开发规划与执行计划

> 基于《YROLL-产品蓝图-整理终稿.md》制定。2026-08-23。
> 总原则：**Intelligence Routing First（够用即可）/ AI-native 但非 AI-dependent / 人机共用同一 Command Layer / 先验证闭环，不堆功能。**

---

## 一、战略目标

验证上层命题：**"AI 能否成为视频生产问题解决系统的组织者，而不仅是 Timeline 的操作者。"**

MVP 成功标准（对话已冻结）：真实案例（柴烧茶器 39 照片+15 视频 → 30 秒小红书/抖音成品）比"剪映+ChatGPT+可灵+人工切换"散装工作流 **快 5 倍**，且全程不离开 YROLL。

验收三问：① AI 是否真理解视频项目？② AI 修改是否发生在同一 Timeline 上？③ 人是否可随时接管？

---

## 二、总体阶段规划

```
Phase 0  技术验证 Spike（纯 Python，无 GUI）—— 2 周
Phase 1  Project Core + Manifest（骨架）     —— 与 P0 部分并行，2 周
Phase 2  Timeline GUI + Command Layer         —— 3 周
Phase 3  Harness + AI Timeline Assistant      —— 3 周
Phase 4  Y 轴 Clip Workspace + Problem→Solution —— 3 周
Phase 5  Preview 框选 + 人机共编闭环           —— 2 周
───────── 以上 = V1 最小闭环（约 8-12 周，对照原对话"8周冲刺"的扩展版）
Phase 6  Generation Adapter（ComfyUI/云 API） —— 2 周
Phase 7  Export Package + Cost Report          —— 1 周
───────── 以上 = V1.5
后续     P1 增长能力（Adapter/BYOK/Publish）、P2 长期能力（成品反推等）
```

工程铁序（对话定案，防走偏）：**Project Memory → Agent Tool Runtime → Timeline → Chat → Version → Preview Selection → Export Report → Generation Adapter**。"很多人会反过来先做生成，这是最容易走偏的。"

---

## 三、Phase 0：技术验证 Spike（当前阶段）

**目标**：不用 GUI，纯 Python 跑通"素材 → AI 理解 → Project Memory"链路，验证理解质量与成本。

### 任务清单
- [ ] 0.1 项目脚手架：`yroll/` monorepo 目录结构、Python 环境（uv/venv）、依赖锁定
- [ ] 0.2 **Media Scanner**：ffprobe 扫描目录 → Asset 清单（时长/分辨率/编码/EXIF/MD5）→ `assets.json`
- [ ] 0.3 **Asset Identity**：文件指纹（MD5+size+duration）入库 SQLite
- [ ] 0.4 **Shot Detection**：PySceneDetect 镜头切分 → Shots 表
- [ ] 0.5 **Keyframe 抽取**：每 Shot 首/中/尾帧 → `cache/keyframes/`
- [ ] 0.6 **ASR**：faster-whisper 本地转写（词级时间戳）→ Transcript
- [ ] 0.7 **本地视觉初筛**（Stage 3）：CLIP/BLIP 或 Qwen-VL 对关键帧打标（可选，先留接口）
- [ ] 0.8 **LLM 导演分析**（Stage 4 接口）：关键帧描述+转写+用户目标 → Story/Scene 建议（OpenAI 兼容 API，BYOK）
- [ ] 0.9 输出 `project_memory`（SQLite + JSON 导出），打印成本报告（耗时/token/¥）

**验证素材**：`D:\cc\产品定位\景德镇柴烧窑变` + `E:\视频\7月视频\7.26灰片柴烧`（对话中用户指定的真实案例）。
**完成标准**：39 照片+15 视频 → 自动产出镜头清单、转写、语义标签、初步故事线建议；理解成本 < ¥5。

---

## 四、Phase 1：Project Core + Manifest v0.1

**目标**：定义并实现 YROLL Internal Model —— 一切系统的地基，第一天就要做对。

- [ ] 1.1 编写 `manifest-v0.1.schema.json`：Project/Asset/Clip/Timeline/Relationship/Operation/Version/Problem/Solution/Generation/Cost/AIContext/Publishing/extensions
- [ ] 1.2 Python 实现 `ProjectCore`：目录式工程（current.json + operations/ + versions/ + media/ + memory.db）
- [ ] 1.3 **Operation Log**：每个修改产生不可变 Operation 记录（who/when/target/before/after/why/tool/cost）
- [ ] 1.4 **Version**：Git 式版本树（只存 diff，不复制素材）；current + parent 指针
- [ ] 1.5 **Command Layer**：统一编辑指令 API 定义（trim/split/move/speed/volume/transform/edit_subtitle/replace_segment……），GUI 与 AI 共用
- [ ] 1.6 Asset Resolver（纯代码素材找回：原路径→指纹匹配→目录扫描）

## 五、Phase 2：Timeline GUI + Command Layer

- [ ] 2.1 Tauri + React + TS 桌面壳（Windows 优先）
- [ ] 2.2 Timeline 渲染：多轨（视频/音频/字幕），Clip 上下双层结构（上 1/3 AI Context 区 / 下 2/3 编辑区）
- [ ] 2.3 基础编辑走 Command Layer：Trim/Split/Move/Delete/Speed/Volume（无 AI 完整可用——离线底座验证）
- [ ] 2.4 时间范围选择（不必先 Split）：`applyColor(range)` / `changeVolume(range)` + 羽化参数
- [ ] 2.5 Preview 播放器（FFmpeg 渲染 / 后期 Remotion 评估）
- [ ] 2.6 双刻度导航 + 滚轮以鼠标为中心缩放

## 六、Phase 3：Harness + AI Timeline Assistant

- [ ] 3.1 **Codex Harness 深度研究**（对话末尾指定的下一步）：输出《Generic Agent Runtime 研究报告》，决定基座/自研边界
- [ ] 3.2 Generic Agent Runtime：Session/Context/Tool Registry/Permission/Log（能跑 agent loop 即可，保持克制）
- [ ] 3.3 Video Domain Layer：VideoToolContext（project_id/selection/playhead）、~20 个原子工具
- [ ] 3.4 Chat 面板 + 统一会话历史；AI 对话→Command Layer→Timeline 可见修改
- [ ] 3.5 权限三级 + Plan→Preview→Apply 流程
- [ ] 3.6 MCP Server 预留（Editor Core 暴露工具给外部 Claude Code/Codex）

## 七、Phase 4：Y 轴 Clip Workspace + Problem→Solution

- [ ] 4.1 Clip Workspace 五层 UI（Current/Origin/Intent/Generation Chain/Operations）
- [ ] 4.2 Problem 对象 + Problem→Solution Matrix v0.1（问题分类库 P0 先做：时间/音频/文字）
- [ ] 4.3 Solution Routing Engine：L0-L3 成本分级，方案带价格标签，默认推荐最低成本
- [ ] 4.4 Semantic Link 四级关系 + Impact Preview（"将删除视频2秒、同步缩短人声、重对齐2条字幕、BGM不受影响"）
- [ ] 4.5 Semantic Undo（"撤销 AI 刚才对 12-15 秒的修改"）

## 八、Phase 5：Preview 框选 + 闭环验证

- [ ] 5.1 Preview 矩形框选 + 多框编号（V1 不做对象追踪）
- [ ] 5.2 框选 + 时间范围 + 自然语言 → Problem（"1号框的茶具缩小三分之一"）
- [ ] 5.3 **V1 闭环验收**：柴烧茶器真实案例全流程走查，对比散装工作流计时

## 九、Phase 6-7：生成接入 + 导出（V1.5）

- [ ] 6.1 Generation Router + ComfyUI Adapter（用户自有服务器为第一 Provider）
- [ ] 6.2 重新生成替换 Clip / TTS 局部替换（真人语音克隆留接口）
- [ ] 6.3 局部重绘（mask+inpaint，LaMa/FLUX fill 图片级先行）
- [ ] 7.1 Export Package：视频+封面+标题/正文/标签 Markdown（小红书/抖音风格）
- [ ] 7.2 Cost Report：总成本/¥每分钟/节省人工估算
- [ ] 7.3 Timeline Health Check（导出前 lint）

## 十、明确不做（V1 红线）

完整特效库 / 大量模板 / 专业调色 / 短剧工业生成 / 全自动成片 / 多人协作 / 自研模型 / 剪映 6.x 逆向 / 成品视频反推（只留 Finished Media Indexing 接口）/ 对象级视频编辑（V2+）。

## 十一、风险与对策

| 风险 | 对策 |
|---|---|
| Harness 做不出来（用户自评最大风险） | Codex Harness 候选基座先行研究；Generic/Video 分层解耦，Generic 可换 |
| Context Management（最大技术风险） | Context Pyramid + Attention Manager 独立模块 + "AI 分析一次长期使用" |
| 剪辑功能欠债 | V1 剪辑能力只到 30% 也可接受，AI 理解和交互要 200%；但离线手动底座必须完整 |
| 工程文件体积 | 只存元数据 diff；三级缓存；项目关闭自动 Cleanup |
| 许可证 | 不 fork AGPL 项目；Codex Harness Apache-2.0 ✅；OTIO Apache-2.0 ✅ |

---

## 当前执行状态

- [x] 对话整理终稿（2026-08-23）
- [x] 开发规划制定（2026-08-23）
- [ ] Phase 0 进行中 → 见 SESSION.md
