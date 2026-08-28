# YROLL Editor Foundation Layer 2 — GUI UX Reality Test Protocol

> 目的：补 Layer 1（Command 代码层）的盲点，验证真实鼠标/键盘操作体验
>
> 来源：YROLL补充2 §"Layer 2: Editor UX Reality Test"
>
> 与 Layer 1 区别：Claude Code 不能跑这层（headless 无 GUI），必须由真人在 Tauri 桌面里按剧本操作

---

## 0. 启动方式

⚠️ **必须用 dev 模式，不能用安装 exe**：
- 安装 exe 是 08-24 23:41 打包的，不包含今天的跨轨 Ripple/Move 和 Redo 改动
- 用 exe 等于测老代码，无法验证 P0-1 / P0-6

### 0.1 启动 dev 模式

打开 **两个**终端：

**终端 A（后端 Server）**：
```bash
cd D:\cc\YROLL
.venv\Scripts\python.exe -m yroll.cli.main serve projects\jdz-chaishao --host 127.0.0.1 --port 8765
```
应该看到：`Uvicorn running on http://127.0.0.1:8765`

**终端 B（Tauri 桌面）**：
```bash
cd D:\cc\YROLL\gui
pnpm install        # 第一次需要，之后可跳
pnpm tauri dev      # 第一次会编译 ~2-3 分钟
```

启动后会自动弹出一个 Tauri 桌面窗口，连后端 8765。

### 0.2 验证连上了

在 Tauri 窗口里：
- 左上应该看到 `jdz-chaishao` 工程已加载
- 素材面板应该列出 10 张图 + 5 段视频
- Timeline 应该有 8 个视频 clip + 2 个字幕 clip

如果看不到：检查终端 A 的 Server 日志有没有报错；检查浏览器能否访问 `http://127.0.0.1:8765`。

### 0.3 什么时候才需要重建 exe

只有当：
- Layer 2 全部跑完且 P0 标记完成
- 想给非开发者用户用
- 想发布版本

重建命令（耗时长，10-20 分钟）：
```bash
cd D:\cc\YROLL\gui
CARGO_BUILD_JOBS=2 pnpm tauri build
```
产物：`gui/src-tauri/target/release/bundle/nsis/YROLL AI_0.1.0_x64-setup.exe`

---

## 替代方案：用浏览器（更省事，推荐先试）

如果 `pnpm tauri dev` 起不来或太慢（首次编译要 2-3 分钟），**Layer 2 大部分剧本可以用纯浏览器跑**：

**终端 A 不变**（后端 Server）。

**终端 C（Vite dev server，秒启）**：
```bash
cd D:\cc\YROLL\gui
pnpm install
pnpm dev    # vite，不是 tauri dev
```
Vite 启动后会输出类似 `http://localhost:5173`。

**浏览器**打开：
- 优先 `http://localhost:5173`（Vite，有热重载，连 8765 后端）
- 或 `http://127.0.0.1:8765`（直接走后端静态托管，但没热重载）

可以测：
- ✅ 剧本 2/3/5/6/7/8/10
- ❌ 剧本 4（Preview Transform Box 在 Tauri 里才有原生 overlay）
- ❌ 剧本 1 部分（依赖 Tauri 原生组件）

**取舍**：浏览器跑能验证 80% 的交互，省去 Tauri 编译 20 分钟；剩余 20% 的"像剪辑软件"的体验再上 Tauri 测。

### 调试技巧

- 浏览器 DevTools（F12）→ Network → 看 API 请求有没有 404
- 后端日志会显示每次 API 调用：`INFO: 127.0.0.1:xxxx - "POST /api/xxx HTTP/1.1" 200 OK`
- 如果 API 调不通：检查 `gui/src/api.ts` 里的 base URL 默认是不是 `http://127.0.0.1:8765`

### API 快速验证（不进 GUI）

```bash
# 查看后端 OpenAPI 文档
curl http://127.0.0.1:8765/docs

# 列素材
curl http://127.0.0.1:8765/api/assets
```

---

## 1. 测试矩阵（10 个剧本）

每个剧本**记录**：
- ✅/❌ 操作是否成功
- ⏱ 实际花费秒数（粗略）
- 😤 任何"想回剪映"的瞬间
- 📝 改进建议

### 剧本 1：30 秒视频端到端
**素材**：用 `jdz-chaishao`（10 张柴烧茶器照片 + 5 段手机视频）

**任务**：
1. 打开 jdz-chaishao 工程
2. 在 Preview 看一段视频
3. 拖到 Timeline 主轨
4. 拖动 Clip 改位置（鼠标）
5. 拖 Trim Handle 改入点出点（精确到帧）
6. S 键 split
7. Shift+Del = Ripple Delete
8. 加字幕 / 加 BGM
9. 调音量、淡入淡出
10. 导出

**重点**：每一步的鼠标手感，是不是"像剪辑软件"

### 剧本 2：跨轨联动（验证 P0-1）
**任务**：
1. 手动建一个字幕 clip 与主轨某段重叠
2. Move 主轨 clip 看字幕是否跟
3. Ripple Delete 主轨某段看字幕是否跟

**重点**：用户**不**知道 STRONG link 这件事，他只希望"字幕自动跟着"

### 剧本 3：Undo / Redo（验证 P0-6）
**任务**：
1. Ctrl+Z 多次
2. Ctrl+Y 多次
3. 混合：人改 → AI 改 → 人改 → Undo×3 → Redo×3

**重点**：撤销栈在 GUI 里的可视化，撤销一步后是否能继续撤销，撤销按钮禁用时机

### 剧本 4：Preview Transform Box（验证 P0-4）
**任务**：
1. 选中一个 clip
2. Preview 出现 Transform Box（8 个 handle + 1 个旋转手柄）
3. 拖角缩放
4. 拖边缩放
5. 拖旋转手柄
6. 松手看效果
7. 撤销

**重点**：手柄大小是否够大（手机/小屏友好），是否实时预览，旋转中心是否准确

### 剧本 5：Trim/Split/Ripple（验证 P0-5）
**任务**：
1. 拖 Trim Handle（左右各一个）
2. S 键 split
3. Shift+Del Ripple Delete
4. 多选批量 trim

**重点**：Trim Handle 拉动的精确度（帧 vs 秒），Ripple 后相邻 clip 是否自动收拢

### 剧本 6：Snapping / Zoom / Scrubbing
**任务**：
1. 拖 Clip 靠近另一个 clip，看磁吸
2. Ctrl+滚轮缩放 Timeline
3. 拖 Playhead 跳转
4. J/K/L 反向/暂停/正向播放

**重点**：Snapping 强度（不会抢控制权），缩放以鼠标位置为中心

### 剧本 7：Track 操作
**任务**：
1. 加 / 删 / 静音 / 锁定 / Solo 轨道
2. 拖动调整 track height
3. PiP 拖到第二条视频轨

**重点**：轨道操作是否即时响应

### 剧本 8：字幕体验（验证 P1-2）
**任务**：
1. 自动字幕生成
2. 改一个词的字
3. 拖字幕 clip 改时间
4. 删一段主轨后字幕是否自动重排

**重点**：字幕与主轨的对齐是否真的"自然"

### 剧本 9：50 素材压力（验证 P1-4 Proxy）
**任务**：导入 50 段视频，做一个 5 分钟的工程

**重点**：
- Timeline 滚动是否卡顿
- Render 进度条是否流畅
- 内存占用（任务管理器）

### 剧本 10：断网 + 30 分钟任务（验证 30 分钟任务）
**任务**：断网状态下，用 jdz-chaishao 素材完成一条 30 秒视频

**重点**：
- AI 不能用时，是否能继续完成视频（H 已验证后端可以）
- 用户多久会想回剪映

---

## 2. 记录模板

每个剧本完成后填写：

```
剧本 X：[名字]
日期：YYYY-MM-DD HH:MM
操作员：[你的名字]

总耗时：XX 分 XX 秒
回剪映次数：X 次（关键节点）

✅ 通过的步骤：
- 
- 

😤 想回剪映的瞬间：
- [时间点] [操作] [原因]
- 

💡 改进建议：
- 
- 

🎬 整体评价（1-5 星）：
```

---

## 3. 验收标准

| 剧本 | 最低标准 | 期望 |
|------|---------|------|
| 1 | 30 分钟内完成 | 15 分钟 |
| 2 | 字幕联动 80% | 100% |
| 3 | Undo/Redo 闭环 | 可视化撤销栈 |
| 4 | Transform 顺畅 | 无延迟 |
| 5 | Trim 帧级精确 | 帧级 |
| 6 | Snapping 不抢控 | 不抢控 |
| 7 | 轨道操作 < 100ms | < 50ms |
| 8 | 字幕对齐自然 | 自然 |
| 9 | 50 素材不卡 | 流畅 |
| 10 | 断网可用 | 完全可用 |

---

## 4. 当前 Layer 1 → Layer 2 状态

| P0 项 | Layer 1 状态 | Layer 2 状态 |
|-------|--------------|--------------|
| P0-1 跨轨 Ripple/Move | ✅ PASS（测试通过） | ❓ 待 GUI 实测 |
| P0-6 Undo/Redo | ✅ PASS（测试通过） | ❓ 待 GUI 实测 |
| P0-3 GUI 基础操作 | ❌ 无 | ❓ 待 GUI 实测 |
| P0-4 Preview Transform | ❌ 无 | ❓ 待 GUI 实测 |
| P0-5 Trim/Split/Ripple GUI | ❌ 无 | ❓ 待 GUI 实测 |
| P0-2 Subtitle Strong Link | ✅ 命令层 | ❓ 待 GUI 实测 |

**结论**：Phase A 后端骨架 ✅ 已可，下一步**只**做 GUI 实测。

---

## 5. 数据收集建议

把每次测试填的记录贴到 `tests/layer2-reports/` 目录，按日期命名：
- `tests/layer2-reports/2026-08-26-script-1.md`
- `tests/layer2-reports/2026-08-26-script-2.md`
- ...

每个剧本完成后，把"回剪映次数"和"整体评价"汇总成一张表：

```
| 剧本 | 回剪映次数 | 评价 | 关键问题 |
|------|------------|------|---------|
| 1    | 0          | 4    | Trim 精度 |
| 2    | 1          | 3    | 字幕偶尔不跟 |
| ...  | ...        | ...  | ... |
```

当所有剧本的"回剪映次数"加总 < 3 时，Phase A 才算真正完成。
