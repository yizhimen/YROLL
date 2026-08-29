Single Project Authority / Cross-process Session

解决：

MCP 不再独立持有 ProjectCore
GUI / MCP 共享同一 Core
Lease 真正跨操作者
Revision 真正有单一真相
Mutation Gate 对所有入口统一
MCP 也进入 sessionId + baseRevision
不允许 silent overwrite

这个完成后：

才进入 GUI-02 Frame-Native Timeline。

先不要做 GUI-02。

当前最新审计发现：EditLease 的 LeaseStore 是进程内状态（_g_stores keyed by id(ProjectCore)），而 mcp_server.py 会独立 ProjectCore.open() 并直接操作 CommandLayer；因此 GUI 与 MCP 跨进程并不共享 Lease / ProjectCore，当前 Lease 不能真正保护 GUI↔MCP。

实施 GUI-01.5 / Cross-process Project Authority：

保持 YROLL serve <project> 作为该工程唯一 Mutation Authority / ProjectCore owner。
MCP 不再独立 ProjectCore.open() 写工程；改为连接正在运行的 YROLL HTTP server，所有 mutation 经 HTTP API → Mutation Gate → ProjectCore。
MCP 的写操作统一携带 sessionId + baseRevision。
Agent/Claude 的 lease 由 Project Server 持有，GUI/MCP 共享同一个 LeaseStore。
Revision 必须由同一个 ProjectCore 生成；禁止客户端本地推断。
增加跨进程集成测试：
GUI/Human 持有 EDIT → MCP mutation 必须拒绝；
handoff Human→Agent 后 MCP mutation 成功；
Agent 持有 EDIT → GUI mutation 必须拒绝；
stale baseRevision → 409；
两个 MCP client 不能同时获得 EDIT；
lease expired 后可以恢复；
不允许 silent overwrite。
保留现有 GUI-01 的静态护栏和 Vitest/Playwright/pytest。
完成后运行完整 regression，并明确报告：
哪些入口经过 Mutation Gate；
GUI/MCP 是否共享同一 ProjectCore；
跨进程测试结果；
pytest / vitest / tsc / Playwright。

禁止同时修改 Frame Timeline、Selection、Preview、Audio、Subtitle。

目标：GUI-01.5 完成后，Human + Agent 才真正共享一个有 Lease、Revision、History 的 Project State。