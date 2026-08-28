# 44. Generic Agent Runtime × OpenAI Codex Harness 深度研究

> 2026-08-24。对应蓝图：Generic Agent Runtime 候选基座研究（对话末尾指定的下一步议题）。
> 仓库：`openai/codex`，Apache-2.0 ✅（商业闭源可用），核心在 `codex-rs/`（Rust）。

## 一、Codex Harness 的核心抽象（协议 v1）

```
UI ──Submission(Op)──▶ Codex 引擎（本地线程/进程）
UI ◂──Event───────────  （流式，传输无关：线程/IPC/stdio/TCP/gRPC 均可）

Session：当前配置与状态（model/sandbox/approval policy）
Task：  响应一次用户输入的执行；同一时刻最多一个；可被中断/等待审批
Turn：  Task 内一次迭代——请求模型 → 收 SSE 流 → 执行命令/补丁 → 必要时暂停等审批
        "一个 Turn 的输出是下一个 Turn 的输入"
```

关键机制：
- **response_id**：Session 保存，随 `TurnComplete` 返回——线程可恢复、可分叉（= 我们的 Version/Branch）
- **审批异步化**：`ExecApprovalRequest` / `Op::ExecApproval`——长任务中途暂停等人点头（= 我们的 Plan→Preview→Apply）
- **中断是一等公民**：`Op::Interrupt`（= 我们的 "Autonomous but Interruptible"）
- **逐轮上下文**：UserTurn 携带 cwd/model/sandbox/approval（= 我们的 VideoToolContext：project/selection/playhead）

## 二、模块地图（codex-rs，与我们架构的对应）

| Codex 模块 | 职责 | YROLL 对应 | 借鉴度 |
|---|---|---|---|
| `core` | agent loop（Session/Task/Turn） | Generic Agent Runtime | ★★★★★ 思想 |
| `protocol` | Submission/Event 枚举，传输无关 | Server↔GUI 事件协议 | ★★★★★ 直接可抄 |
| `skills` | skill 加载/解析/frontmatter/隐式触发/提及 | Skill Manager（茶视频/婚礼/电商包） | ★★★★★ |
| `tools` | 工具注册与执行 | Tool Registry（Problem→Capability→Tool→Provider） | ★★★★ |
| `mcp-server` | 把自己暴露成 MCP | YROLL MCP Server（外部 Claude Code/Codex 接管） | ★★★★ |
| `execpolicy`/`sandboxing` | 执行策略与沙箱 | Permission 三级 + Capability Manager | ★★★★ |
| `rollout`/`history` | 会话持久化/回放 | Operation Log + 会话历史 | ★★★★ |
| `model-provider` | 多 provider 抽象 | Model Router（BYOK/官方额度） | ★★★ |
| `memories` | 记忆 | Project Memory（我们的更深：视频语义层） | ★★★ |
| `tui`/`app-server` | 终端/应用外壳 | GUI（我们自研 X/Y 界面） | ★ 不借鉴 |

## 三、关键结论

### 1. 不嵌入、不换皮、不重造——"抄协议，自研引擎"

- Codex 引擎是 Rust + 深度绑代码任务（apply_patch/shell），直接嵌入会让"代码思维污染 Video Domain"（蓝图铁律）。
- 但其 **Session/Task/Turn + Submission/Event 协议 + 审批/中断模型** 是干净通用的——这就是"Generic Harness 不懂业务"的现成范本。
- 决策：**YROLL Generic Agent Runtime 用 Python 自研**（与现有 FastAPI/Command Layer 同栈），协议层照搬 Codex 的 Op/Event 模型。

### 2. YROLL Runtime 已有雏形，缺的是"协议化"

我们已有：Command Layer（工具执行）/ Operation Log（rollout）/ Problem→Solution（领域路由）/ chat（单轮 LLM 调用）。
缺的（本研究后要建的）：
- **Session/Task/Turn 循环**：当前 chat 是单轮；要升级为多轮 agent loop（模型→动作→观察→再模型）
- **事件流**：GUI 现在轮询刷新；要升级为 Event 推送（WebSocket）——"AI 正在分析/正在执行 op0009/等待你确认"
- **审批协议**：删除/批量/正式生成走 ApprovalRequest，GUI 弹确认（Impact Preview 已是一半）
- **Skill 加载器**：SKILL.md 格式（frontmatter + 指令 + 工具依赖），按需加载（借鉴 codex-rs/skills 的 loading/selection 分层）

### 3. MCP 双向

- 后期 YROLL Server 暴露 MCP Server（参考 codex-rs/mcp-server），外部 Claude Code/Codex 可调 `yroll.*` 工具——"AI 在哪里操作不重要，结果都回到同一个世界"。
- Codex 本身也可作为 YROLL 的"开发者模式"入口（L3 权限：AI 改 Skill/装 Tool）。

### 4. 许可证

Apache-2.0，可自由借鉴/引用/商用。无 AGPL 风险（对比 OpenChatCut）。

## 四、行动清单（Phase 3 落地）

- [ ] `yroll/harness/` 实现 Session/Task/Turn 循环（Python，asyncio）
- [ ] Event 协议：WebSocket 推送 agent 状态到 GUI（替换轮询）
- [ ] 审批协议：高风险操作 → ApprovalRequest → GUI 确认 → 继续
- [ ] Skill 加载器 v0：skills/ 目录 + SKILL.md frontmatter + 按需注入 system prompt
- [ ] chat 从单轮升级为 Task（多轮 tool-use loop，观察结果回喂）
- [ ] （P1）MCP Server 暴露 yroll 工具集
