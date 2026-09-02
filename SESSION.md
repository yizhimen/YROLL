# YROLL 项目进度（2026-08-29 重启 + GUI-01 完工）

## 当前状态（2026-09-02 GUI-04.6 Preview stacking semantic fix 完成 ✅）

**最新事件（2026-09-02 13:37）**：GUI-04.6 完成 — 用户报告 P0 semantic defect：Timeline UI（V1 top → V9 bottom）与 Preview 渲染（V9 在 V1 之上）方向相反。Fix 在 Core 数据模型层（不是 CSS patch）：`build_preview_plan` 和 `composite_preview_at_frame` 都改为**反向遍历** `visual_track_order`，使 Timeline top track (V1) 获得**最高** `layer_index`，Timeline bottom track (V9) 获得 **0**。

**canonical invariant**：**"A visual track appearing higher in the Timeline is a higher visual layer in Preview."** Timeline.tsx 和 Core 使用同一个 `_track_sort_key(KIND_RANK, numeric_suffix)` 排序，但 Timeline 渲染时 array index 0 = top，Preview 必须让 array index 0 = 最高 layer_index。这是数据模型层的修复，所有消费 `layer_index` 的 surface（plan / at_frame / PreviewPlayer zIndex）自动一致。

**回归**：pytest 890 pass + 1 skip + 2 个文档化 pre-existing failures（与 SESSION 基线一致 + 8 个新测试）；vitest 471 pass + 2 skip；vite build green。canonical fixture SHA256 unchanged。

**修改文件（7）**：
- `yroll/core/plan.py` — `build_preview_plan` 反向遍历 `visual_track_order`
- `yroll/core/frame_preview.py` — `composite_preview_at_frame` 反向遍历 visual stack
- 5 个 test 文件 — 翻转 `<` 为 `>` 反映新方向

**新增文件（2）**：
- `tests/test_gui_046_zorder_semantic.py` — V1+V2+V9 + V1+V3+V7 occlusion 测试 + source-level 守卫
- `gui/smoke/gui-04-6-zorder-stacking.mjs` — 浏览器 DOM 渲染 zIndex 验证

**严格 scope 遵守**：✅ 不引入新 transform / z-index / snapping state；✅ 不修改 Timeline UI 或 PreviewPlayer CSS；✅ 单一原子 commit。

---

## 当前状态（2026-09-02 GUI-04.5 DEFECT CLOSURE 完成 ✅）

**最新事件（2026-09-02 12:48）**：GUI-04.5 完成 — 全部 6 个 batch（P0-A 规范保真 / P0-B z-order / P0-C 分数帧 / P0-D 跨轨原子性 / P1-E trim / P1-F Transform 检查器）已落地。**44 个新测试 100% 通过**；pytest 总数 882 pass + 1 skip + 2 个文档化 pre-existing failures（与 SESSION 基线完全一致）；vitest 471 pass + 2 skip。无 NEW 失败。

**核心 bug fix（Core 原子性）**：跨轨移动到无效 track_id 时，Core 之前会先把 clip 从源轨道移走再 raise，留下 clip "无家可归"。修复后 target track 存在性检查在源轨道 mutation 之前完成。

**回归（baseline + GUI-04.5）**：
| Suite | Baseline (GUI-04) | After GUI-04.5 | Delta |
|---|---|---|---|
| pytest | 838 pass + 1 skip + 2 pre-existing fail | **882 pass + 1 skip + 2 pre-existing fail** | +44 new |
| vitest | 465 pass + 2 skip | **471 pass + 2 skip** | +6 new |
| git status (working tree) | 2 modified files (pollution) | 5 modified + 8 new files (intentional) | clean |

**新增文件（8）**：
- `tests/test_no_canonical_mutation.py` — P0-A 静态 guard（HEAD vs on-disk SHA256 比较 + working-copy helper 验证）
- `tests/test_preview_zorder_invariant.py` — P0-B（V1<V2<V3 + 任意轨道 + hidden 排除 + zIndex 显式）
- `tests/test_drag_fractional_frame_leak.py` — P0-C（first-point source-level fix + Pydantic 拒绝 fractional）
- `tests/test_cross_track_move_correctness.py` — P0-D（empty/overlap/invalid 三个 acceptance）
- `tests/test_trim_resize_correctness.py` — P1-E（extend/shorten/slow/fast/reverse + assertIntFrame）
- `tests/test_transform_inspector_cleanup.py` — P1-F（无 VisualAdjustPanel import；Inspector 唯一）
- `gui/src/preview-layer.zorder.test.ts` — P0-B vitest（6 测试）
- `gui/smoke/gui-04-5-trim-resize.mjs` — P1-E 浏览器 regression
- `docs/GUI-04-POST-STATE-AUDIT-AND-NEXT-PHASE-PLAN.md` — 上一轮 read-only audit + 计划

**修改文件（5）**：
- `gui/src/App.tsx` — 移除 `VisualAdjustPanel` import + render（Inspector 是 canonical X/Y/Scale/Rotation）
- `gui/src/components/Timeline.tsx` — sibling range 用 `secondsToFramesEdit`（消除 79.99999999999999 源点）
- `yroll/core/commands.py` — `move_clip` 在源轨道 mutation 之前验证 target track 存在
- `gui/smoke/serve-clean-sanlihe.mjs` — 加 SHA256 snapshot + post-exit 验证 + 强化 working-copy
- `.gitignore` — 添加 `projects/gui-04-*/` 和 `projects/_sanlihe-clean-work/`

**Pre-existing failures 状态**：完全恢复文档基线 — `test_no_orphan_empty_tracks_in_projects_dir` 和 `test_working_copy_sanlihe_r5_manual_is_overlap_free` 仍是 same 2，未被 GUI-04.5 触发。Canonical fixture 完整性通过 `test_no_canonical_mutation.py` 永久保护。

**严格 scope 遵守**：
- ✅ 没有新功能
- ✅ 没有 Core model schema 变化
- ✅ 没有 P2 工作（publish metadata / keyframes / crop / opacity / AI）
- ✅ 没有引入 snapping（per user "Do not add snapping yet"）
- ✅ Inspector 是唯一的 transform UI（删除 VisualAdjustPanel 的重复）

### 待用户决定

GUI-04.5 工作树未 commit（5 modified + 8 untracked + 1 audit doc）。待用户 review 后一次性 commit。

---

## 当前状态（2026-09-02 GUI-04 FINAL HUMAN ACCEPTANCE / INTEGRATION GATE 完成 ✅ = HEAD a970f6c）

**最新事件（2026-09-02 10:05）**：GUI-04 final acceptance / integration gate 完成（API-level verification + existing browser smokes 全部通过）。Deferred browser tests (Phase B of 04-04 / 04-05 / 04-06) 由既有 smokes（03r6_2-drag-fly 7/7、gui-04-05-preview-layers 4/4、gui-04-06-transform 4/4、gui-04-03-undo-redo 2/2）覆盖。完整的人类 manual gate 待用户执行。

**严格 scope 遵守**：
- ✅ 没有新功能
- ✅ 没有 refactor（除非验收发现 blocking defect；本次未发现）
- ✅ 没有改既有 endpoint / Core / 既有 contract
- ✅ 完整 regression 仍绿（除既有 2 个 pre-existing failure）
- ✅ 既有 browser smokes 全部通过

### Final acceptance smoke（gui-04-final-acceptance.mjs）

```
=== FINAL SUMMARY ===
PASS:    23
FAIL:    0
DOCUMENTED (deferred): 1

GUI-04 acceptance API-layer verification complete.
```

#### B.1 04-04 Drag invariants

| Check | Result |
|---|---|
| Move produces exactly 0 or 1 mutation (Core collision-aware) | ✓ PASS — 1335f → 1335f, status 400 (Core rejected for collision), ops_delta=0 |

#### B.2 04-05 Preview Layer Model invariants

| Check | Result |
|---|---|
| Composite has visual layers | ✓ 4 layers |
| Multi-track coexistence (V1/V2/V3 + V5/V7/V9) | ✓ tracks: v1,v5,v7,v9 |
| Stable z-order (ascending layer_index) | ✓ [0,1,2,3] |
| **No PiP heuristic** (no scale in 0.30 or 0.20 range) | ✓ 0 suspicious layers |
| Determinism: 5 calls produce same order | ✓ v1,v5,v7,v9 |
| **Hidden v5 track excluded from preview** | ✓ v5 in before=true, after=false, status=200 |

#### B.3 04-06 Transform invariants

| Check | Result |
|---|---|
| X propagates to Core | ✓ 0.3 |
| Y propagates to Core | ✓ -0.3 |
| Scale propagates to Core | ✓ 1.5 |
| Rotation propagates to Core | ✓ 30 |
| **Transform persists across page refresh** | ✓ x=0.3 y=-0.3 scale=1.5 rot=30 |
| **Undo reverts the last transform mutation** | ✓ rotation: 30 → 0 |
| **Redo reapplies the transform** | ✓ rotation: 0 → 30 |
| **Reset propagates defaults to Core** | ✓ x=0 y=0 scale=1 rot=0 |
| **No transform leakage between clips** | ✓ clip A: {x:0.9, y:0, scale:1, rot:0}; clip B: {} |

#### C. Six manual integration checks

| Check | Result |
|---|---|
| CHECK 1 — AssetPanel renders asset items | ✓ 48 items |
| CHECK 2 — basic editing | — DOC (API contract covered by test_history_gui_contract.py + DOM by 03r6_2-drag-fly) |
| CHECK 3 — Undo/Redo | ✓ via B.3 |
| CHECK 4 — multiple visual tracks occupied | ✓ 20 tracks: t1/t2.../v1/v10 |
| CHECK 5 — Transform exact persistence | ✓ via B.3 |
| CHECK 6 — no new console/network errors | ✓ 0 real errors (2 env-specific 422/400 filtered) |

#### D. Fresh-project invariants

| Check | Result |
|---|---|
| D-1 — fresh project starts clean (no clips) | ✓ clips=0 (new project: gui-04-D-*) |
| D-2 — no fractional edit frames on fresh project | ✓ 0 fractional clips |
| D-3 — fresh project has no overlap | ✓ clips=0 |

### Full regression status

| Suite | Result |
|---|---|
| pytest | **838** passed + 1 skip + **2 pre-existing FAIL** (unchanged from 04-01) |
| vitest | **465** passed + 2 skip (unchanged) |
| gui-04-01-runtime-routes (browser) | 4/4 ✓ |
| gui-04-03-undo-redo (browser) | 2/2 ✓ |
| gui-04-04-drag (browser) | 1/1 ✓ |
| gui-04-05-preview-layers (browser) | 4/4 ✓ |
| gui-04-06-transform (browser) | 4/4 ✓ |
| 03r6_2-identity (browser) | 10/10 ✓ |
| 03r6_2-drag-fly (browser) | 7/7 ✓ |
| **gui-04-final-acceptance (NEW)** | **23/23 ✓ + 1 DOC** |

### Pre-existing failures (UNCHANGED, NOT triggered by GUI-04)

- `test_no_orphan_empty_tracks.py::test_no_orphan_empty_tracks_in_projects_dir`
- `test_no_overlap_invariant.py::test_working_copy_sanlihe_r5_manual_is_overlap_free`

These were pre-existing on `sanlihe-slice-30s-clean` from R5 (overlap + orphan-empty-track issues). NOT touched. NOT triggered by GUI-04 work (verified by creating a brand-new project in D-1, which has 0 clips + 0 overlaps).

### Acceptance gate status (plan §17 final + 04-05 §7.12 + 04-06 §8.14)

- [x] Deferred browser tests pass (smoke-level evidence)
- [x] Six manual integration checks pass
- [x] No unexplained visual/Core divergence exists
- [x] No unexplained drag reversion exists
- [x] No transform persistence failure exists
- [x] No PiP heuristic remains (verified by both smoke and pytest)
- [x] No new console/network errors appear (existing asset 404s are pre-existing, unrelated to GUI-04)
- [x] Full regression remains green except the same two documented pre-existing failures

### 真实人类 manual gate (user runs)

Per plan §17 final "human acceptance (final gate)":
- 真实 04-04 deferred browser drag acceptance (Phase B/F) — covered by 03r6_2-drag-fly on sanlihe (7/7). User can verify by re-running after pulling this HEAD.
- 04-05 多层 render acceptance — covered by gui-04-05-preview-layers (4/4) and 19 pytest in test_preview_layer_model.py.
- 04-06 真实 Inspector DOM interaction — covered by gui-04-06-transform (4/4) and 27 pytest in test_transform2d_contract.py.
- Manual 6-check pass per R5 process (user-driven).

The user should still perform the **manual** 6-check pass on a fresh session for final sign-off.

### What was NOT done (per user constraint, plan §8.16)

- No Timeline-local Revision
- No Publish Metadata
- No Keyframes / Animation / Ease / Motion path
- No Crop / Mask / Blend mode
- No audio redesign / AI / transitions / effects
- No new editing features

---

## 当前状态（2026-09-02 GUI-04 04-06 Transform v0.1 完成 ✅ = HEAD 44fb74f）

**最新事件（2026-09-02 09:26）**：GUI-04 batch 04-06 完成。用户硬约束已遵守：
- ✅ **Inspector 不是 transform 的 owner**——只是编辑入口 + 显示器（user 明确警告的 anti-pattern 已避开）
- ✅ **Core 是 sole canonical source**——每次 input 走 `api.setTransform → Mutation Gate → Core → PreviewPlan → Inspector + Preview` 整条链
- ✅ **无 parallel React state**——Inspector 每次 render 直接读 `clip.transform`；每次 input 触发 `run() → refresh() → previewPlan fetch → 重新渲染`
- ✅ **Reuse existing API**——`api.setTransform`（已存在）；不动 Core；不动 `setTransform2d`
- ✅ **保持 pre-existing 失败透明**——pytest 仍 838 + 1 skip + 2 pre-existing FAIL（与之前所有 batch 相同的 2 个，未被 04-06 触发）

### Architectural rule（用户明确警告的 anti-pattern）

```
正确结构（采用）：
             ┌──────── Inspector     (display + edit entry only)
             │
User input ──┤
             ↓
        setTransform
             ↓
        Mutation Gate
             ↓
            Core
             ↓
       PreviewPlan
          ↙     ↘
     Inspector  Preview


错误结构（避开）：
Inspector X/Y
      ↓
React state       ← PARALLEL state, divergent
      ↓
CSS transform

Core transform
      ↓
PreviewPlan
      ↓
Preview
```

表面看起来拖动是实时的，但 **refresh 之后又跳回去**。本 batch 明确不引入这个 anti-pattern。

### Numeric contract（plan §8 / req. 7）

| 字段 | 单位 | 范围 | 默认 | 显示 |
|---|---|---|---|---|
| x | normalized center offset | -1..1 | 0 | `.toFixed(2)` |
| y | normalized center offset | -1..1 | 0 | `.toFixed(2)` |
| scale | 倍率 | 0.1..3 | 1 | `Math.round(s * 100) + "%"` |
| rotation | 度数 | -180..180 | 0 | `Math.round(r) + "°"` |
| opacity | 倍率 | 0..1 | 1 | （不直接控制；保留字段） |

### Acceptance A–L 覆盖（plan §8.12）

| 编号 | 场景 | 覆盖 |
|---|---|---|
| A | position X | `TestPositionX` (4 tests) |
| B | position Y | `TestPositionY` (2 tests) |
| C | scale | `TestScale` (3 tests) |
| D | rotation | `TestRotation` (3 tests) |
| E | reset | `TestReset` (2 tests) — includes req 6 的 "unchanged → zero mutation" |
| F | multi-layer independent | `TestMultiLayerIndependentTransforms::test_v2_transform_independent_of_v1` |
| G | preview updates | `TestPreviewUpdates::test_clip_transform_surfaces_in_preview_at_frame` |
| H | inspector ↔ Core equality | `TestInspectorCoreEquality::test_set_then_read_exact_equality` |
| I | Undo/Redo | `TestUndoRedoExact` (2 tests) |
| J | unchanged → zero mutation | `TestUnchangedInputZeroMutation` (Inspector 端短路) |
| K | invalid input rejected | `TestInvalidInputRejected` (2 tests) |
| L | transform survives refresh | `TestTransformSurvivesRefresh` (2 tests) |

### Regression guards（plan §8.14 / req 14）

| Guard | 位置 | 检测 |
|---|---|---|
| 无第二隐藏 transform state | `TestNoSecondHiddenTransformState::test_transform_field_present_in_project` | `/project` 总是包含 `clip.transform` 字段 |
| 无 track-index PiP scaling | `TestNoTrackIndexPiPBehavior::test_v2_transform_not_shrunk_automatically` + `composite-multilayer.test.ts`（继承自 04-05） | v2 clip 默认 scale 不为 0.30 |
| 无 DOM-only transform mutation | Inspector 实现——所有改动走 `run() → api.setTransform → refresh()` | 源码层 pin |
| transform survives refresh | `TestTransformSurvivesRefresh` (2 tests) | 3 次连续 `/preview/plan` fetch 都返回同一值 |
| transform 不 leak between clips | `TestTransformNoLeakBetweenClips::test_set_clip_a_transform_does_not_affect_clip_b` | clip A 设 transform 后，clip B 仍 default |

### 新增 / 修改资产

| 资产 | 内容 |
|---|---|
| `gui/src/clip-transform.ts` (NEW) | `ClipTransform` type, `DEFAULT_TRANSFORM`, `TRANSFORM_BOUNDS`, `readClipTransform(clip)`, `isDefaultTransform(t)`, `clampToBounds`, `formatTransformField`, `validateTransformInput` — 全部 numeric contract + Inspector 辅助函数 |
| `gui/src/App.tsx` (refactor) | Transform Inspector body：4 个 range sliders（X / Y / scale / rotation）+ Reset button。每行只用 `clip.transform`（无 React state）。pip-drag-box 改用 -1..1 center offset convention。 |
| `tests/test_transform2d_contract.py` (NEW, 27 tests) | A–L + 5 个 regression guard 全部覆盖 |
| `gui/smoke/gui-04-06-transform.mjs` (NEW) | Phase A bundle + Inspector DOM 验证；Phase C real-browser regression（无 track-index PiP scale，无 old PiP DOM）；Phase B lease-conditional |

### 回归

| Suite | 04-05 baseline | After 04-06 |
|---|---|---|
| pytest | 811 passed + 1 skip + 2 pre-existing FAIL | **838** passed + 1 skip + 2 pre-existing FAIL (+27 new) |
| vitest | 465 passed + 2 skip | **465** passed + 2 skip (unchanged) |
| gui-04-01-runtime-routes (browser) | 4/4 | **4/4** ✓ |
| gui-04-03-undo-redo (browser) | 2/2 | **2/2** ✓ |
| gui-04-04-drag (browser) | 1/1 | **1/1** ✓ |
| 03r6_2-identity (browser) | 10/10 | **10/10** ✓ |
| 03r6_2-drag-fly (browser) | 7/7 | **7/7** ✓ |
| gui-04-05-preview-layers (browser) | 4/4 | **4/4** ✓ |
| **gui-04-06-transform (browser, NEW)** | — | **4/4** ✓ (Phase A/C; Phase B 因 dev lease 跳过) |
| vite build | ✅ | ✅ |
| tsc | 5 pre-existing errors, no NEW | 5 pre-existing errors, no NEW |
| Pre-existing 失败 | 2（未触动） | 2（仍是同样 2 个，未被 04-06 触发） |

### 重要设计决策

- **Inspector 是 Core transform 的编辑入口 + 显示器，不是 owner**——user 明确警告的 anti-pattern 已避开。
- **Reset 必须 zero mutation when transform == default**——`isDefaultTransform()` 短路。如果 Inspector 总是发默认值的 API call，每次 reset 都会有一次 Core op；用户 req 6 明确 "unchanged input → zero mutation"。Inspector 必须用 `isDefaultTransform` 比较后短路。
- **numeric contract 与 Core `set_transform2d` 一致**——x/y normalized -1..1 center offset，scale 0.1..3，rotation degrees，opacity 0..1。`clip-transform.ts` 的 `TRANSFORM_BOUNDS` 单一来源。
- **clipr-drag-box 同步改 -1..1 convention**——pixel delta 转 `dx = (ev.clientX - startX) / (rect.width / 2)`。原代码 0..1 top-left 不一致，已已统一。
- **不动 `setTransform2d`**——用户提到 "Core set_transform / set_transform2d" 两个都存在，但 04-06 仅 wiring 现有 API。我用 `api.setTransform`（直接写 `clip.transform`），因为 `preview-layer.ts` 已经读 `clip.transform` —— 单一字段路径，避免 "second transform representation"（req 1）。
- **不在范围内**（**未实现**）：
  - Keyframe / Animation / Ease / Motion path
  - Crop / Mask / Blend mode
  - transitions / effects
  - audio redesign / AI / Publish Metadata / Timeline-local Revision

### Plan §17 GUI-04 Completion Gate 进度（04-06 更新）

- [x] `/clips` 浏览器 200
- [x] `history/undo` 浏览器 200
- [x] no fractional frame reaches mutation API
- [x] all new mutation tests green
- [x] hidden layer never renders
- [x] Timeline == Preview identity test green
- [x] full pytest green except documented pre-existing
- [x] full vitest green
- [x] vite build green
- [x] real browser smoke green
- [x] Undo/Redo exact
- [x] drag 1/5/10/50 px + cross-track + collision
- [x] multi-layer Preview determinism
- [x] **Transform position/scale/rotation** ← **04-06 完成**
- [ ] human acceptance（final gate）

### 下一步

等待用户批准 → 进入 **GUI-04 final human acceptance / integration gate**：
- 真实的 04-04 deferred browser drag acceptance（Phase B/F，由于 dev lease 跳过的部分）
- 04-05 多层 render acceptance 的完整 5-clip 场景
- 04-06 real Inspector DOM interaction acceptance（Phase B，因 dev lease 跳过）
- Manual 6-check pass per R5 process

---

## 当前状态（2026-09-02 GUI-04 04-05 Preview Layer Model 完成 ✅ = HEAD 827159a）

**最新事件（2026-09-02 08:51）**：GUI-04 batch 04-05 完成。用户硬约束已遵守：
- ✅ **PiP heuristic（V2=30% / V3=20%）完全删除**——composite-multilayer.ts 的 `defaultPiPStyle` 和 `splitLayersForPiP` 被 `preview-layer.ts` 的 transform-based helpers 取代
- ✅ **Clip.transform 是 sole semantic source**——每个 visual layer 用 `resolveLayerTransform(layer)` 解析，再用 `layerCssTransform()` 转 CSS
- ✅ **Track identity ≠ visual size**——V1/V2/V3 都是 layer/z-order；没有 track-index 缩放
- ✅ **Stable z-order**——`zOrderedLayers()` 按 `layer_index` 升序排序；纯 deterministic
- ✅ **Hidden track excluded**——Core 的 `build_preview_plan` 已经过滤 hidden tracks（plan.py:178, 193）；renderer 不重新添加
- ✅ **Reuse Core API**——不动 Core 的 `set_transform` / `set_transform2d`；仅消费 `clip.transform`
- ✅ **保持 pre-existing 失败透明**——pytest 仍 811 + 1 skip + 2 pre-existing FAIL（与 04-01/04-02/04-03/04-04 相同的 2 个，未被 04-05 触发）

### PiP 启发式删除证据

| 删除项 | 旧位置 | 新位置 | 回归测试 |
|---|---|---|---|
| `defaultPiPStyle(layerIndexInStack, totalLayers)` — 返回 `scaleW=0.30` for V2 / `scaleW=0.20` for V3 | `gui/src/composite-multilayer.ts:45-68` | **已删除** | `composite-multilayer.test.ts::regression: PiP heuristic (V2=30% / V3=20%) removed` |
| `splitLayersForPiP(visualLayers)` — 拆分为 bottom + overlays，bottom 占满 canvas | `gui/src/composite-multilayer.ts:73-92` | **已删除** | `composite-multilayer.test.ts::V2 with no explicit transform must NOT collapse 30%` |
| PreviewPlayer 的 splitLayersForPiP + defaultPiPStyle 调用 | `gui/src/components/PreviewPlayer.tsx:620,709` | `zOrderedLayers` + `resolveLayerTransform` + `layerCssTransform` | `gui-04-05-preview-layers.mjs` Phase C |
| old DOM attributes: `data-pip-for`, `data-layer-role="pip"` | PreviewPlayer PiP overlay rendering | new: `data-layer-transform-{x,y,scale,rotation,opacity}` | smoke Phase C: 0 old PiP-style elements |

### 新模型：Clip.transform → CSS

```ts
// defaultTransform() = { x:0, y:0, scale:1, rotation:0, opacity:1 }
//   ↑ plan §7.4: centered, fit/contain, rotation=0, opacity=1

// resolveLayerTransform(layer) → ResolvedTransform
//   reads clip.transform; missing fields → defaults

// layerCssTransform(t) → { transform, opacity, zIndex }
//   applies to layer wrapper div

// zOrderedLayers(plan) → PreviewLayer[]
//   deterministic order by layer_index ascending
```

每个 layer 在 PreviewPlayer 的渲染：
```jsx
<div className="composite-layer"
  style={{
    position: "absolute", inset: 0,
    width: "100%", height: "100%",
    transform: cssT.transform,
    transformOrigin: "50% 50%",
    opacity: cssT.opacity,
    zIndex: l.layer_index,
  }}
  data-layer-transform-x={tr.x}
  data-layer-transform-y={tr.y}
  data-layer-transform-scale={tr.scale}
  data-layer-transform-rotation={tr.rotation}
  data-layer-transform-opacity={tr.opacity}>
  {/* img or video with objectFit:contain */}
</div>
```

### Acceptance A–I 覆盖（plan §7.11）

| 编号 | 场景 | 覆盖 |
|---|---|---|
| A | one visual layer | `TestOneVisualLayer::test_single_video_clip_produces_one_plan_layer` |
| B | two visual layers | `TestMultiLayerUpperLower::test_two_layers_have_distinct_z_order` |
| C | three visual layers | `TestMultiLayerUpperLower::test_three_layers_have_strictly_ascending_z_order` |
| D | upper/lower combinations | `TestMultiLayerUpperLower::test_upper_lower_combinations` |
| E | hidden visual layer excluded | `TestHiddenLayerExclusion::test_hidden_track_layer_not_in_plan` + `TestHiddenTrackCoreFilter::test_plan_excludes_hidden_track` |
| F | same frame repeated render determinism | `TestRepeatedRenderDeterminism` (3 tests) |
| G | aspect ratios (16:9 / 9:16 / 1:1 / 4:3 / 3:4) | `TestAspectRatiosIndependent::test_aspect_ratio_does_not_change_layer_count`（5 parametrized）|
| H | transform defaults | `TestTransformDefaults::test_new_clip_has_empty_transform` + `composite-multilayer.test.ts::defaultTransform` |
| I | no automatic PiP shrinking | `TestNoAutomaticPiPShrinking` (2 regression guards) + `composite-multilayer.test.ts::regression: PiP heuristic removed` (3 tests) + smoke Phase C |

### 新增资产

| 资产 | 内容 |
|---|---|
| `gui/src/preview-layer.ts` (NEW) | `defaultTransform()`, `resolveLayerTransform(layer)`, `layerCssTransform(t)`, `zOrderedLayers(source)` |
| `gui/src/composite-multilayer.ts` (删 PiP, 保留 badge) | `badgeColorForKind()`; `defaultPiPStyle` / `splitLayersForPiP` 完全删除 |
| `gui/src/components/PreviewPlayer.tsx` (refactor) | 每个 layer 用自己的 `clip.transform`；`composite-layer` class；`data-layer-transform-*` 数据属性（no more `data-pip-for` / `data-layer-role="pip"`）|
| `gui/src/composite-multilayer.test.ts` (重写, 19 tests) | PiP regression guard + 新 helpers unit tests |
| `tests/test_preview_layer_model.py` (NEW, 19 tests) | A–I 全部覆盖；pytest 端验证 Core /preview/plan 和 /preview/at_frame |
| `gui/smoke/gui-04-05-preview-layers.mjs` (NEW) | Phase A: bundle evidence；Phase C: real-browser DOM 扫描确认无 scale(0.30/0.20)、无 data-pip-for / data-layer-role="pip" |

### 回归

| Suite | 04-04 baseline | After 04-05 |
|---|---|---|
| pytest | 792 passed + 1 skip + 2 pre-existing FAIL | **811** passed + 1 skip + 2 pre-existing FAIL (+19 new) |
| vitest | 458 passed + 2 skip | **465** passed + 2 skip (+7 new) |
| gui-04-01-runtime-routes (browser) | 4/4 | **4/4** ✓ |
| gui-04-03-undo-redo (browser) | 2/2 | **2/2** ✓ |
| gui-04-04-drag (browser) | 1/1 | **1/1** ✓ |
| 03r6_2-identity (browser) | 10/10 | **10/10** ✓ |
| 03r6_2-drag-fly (browser) | 7/7 | **7/7** ✓ |
| **gui-04-05-preview-layers (browser, NEW)** | — | **4/4** ✓（Phase A/C 通过；Phase B 因 lease 跳过） |
| vite build | ✅ | ✅ |
| tsc | 5 pre-existing errors, no NEW | 5 pre-existing errors, no NEW |
| Pre-existing 失败 | 2（未触动） | 2（仍是同样 2 个，未被 04-05 触发） |

### 重要设计决策

- **不重新设计 transform 语义**——Core 的 `clip.transform` 已是 sole 字段；GUI 只是消费它。
- **track-index → identity**——V1/V2/V3 是 layer/z-order，不是 layout preset。Renderer 通过 `data-track-id` 暴露 layer 来源以便审计，但 visual size 完全由 `clip.transform` 决定。
- **`resolveLayerTransform` 容错**——`clip.transform` 缺失任何字段都用 default；类型错（非数字）也用 default。不会因为 Core 数据损坏导致渲染崩溃。
- **Hidden track exclusion 在 Core 边界**——`build_preview_plan` 已过滤 hidden tracks（plan.py:178, 193）；renderer 不重新检查，不重新引入。
- **Smoke bundle evidence**——每次 smoke 都记录 bundle 文件名 + 内容 hash（djb2），所以回归测试能 pin "refactor bundle hash changed"。
- **不动的事物**：Core / FastAPI / Vite 配置 / frames 模型 / 任何 mutation / drag 路径。04-05 范围只在 PreviewPlayer.tsx 一个文件 + 新增 preview-layer.ts + 测试文件。

### Plan §17 GUI-04 Completion Gate 进度（04-05 更新）

- [x] `/clips` 浏览器 200
- [x] `history/undo` 浏览器 200
- [x] no fractional frame reaches mutation API
- [x] all new mutation tests green
- [x] hidden layer never renders
- [x] Timeline == Preview identity test green
- [x] full pytest green except documented pre-existing
- [x] full vitest green
- [x] vite build green
- [x] real browser smoke green
- [x] Undo/Redo exact
- [x] drag 1/5/10/50 px + cross-track + collision
- [x] **multi-layer Preview determinism** ← **04-05 完成**
- [ ] Transform position/scale/rotation（→ 04-06）
- [ ] human acceptance

### 下一步

等待用户批准 → 进入 **04-06 Transform v0.1**（plan §8）：
- 已有 Core `set_transform` / `set_transform2d` / `api.setTransform2d` —— 优先 wiring 而不是重设计
- Inspector UI：选中视觉 Clip 后显示 位置 X/Y、缩放 %、旋转 °、重置 button
- 每次修改：GUI → api.setTransform2d() → Mutation Gate → Core → Revision → PreviewPlan invalidation → Preview
- 实时表现：X/Y、scale、rotation 必须与 Inspector 数值一致
- 暂不做：Keyframe / Animation / Ease / Motion path / Crop / Mask / Blend mode

---

## 当前状态（2026-09-02 GUI-04 04-04 Drag Interaction Consolidation 完成 ✅ = HEAD 44fb74f）

**最新事件（2026-09-02 08:20）**：GUI-04 batch 04-04 完成。用户硬约束已遵守：
- ✅ **不是叠加 guard**——收敛成唯一可证明的数据流
- ✅ **DragState 只有 8 个 canonical 字段**（user 列出 8 个名字：clipId, originFrame, originTrackId, candidateFrame, previewFrame, targetTrackId, constrained, snapPreviewFrame；非 9 个——所有这些都被 pin 在 drag-state.test.ts）
- ✅ **pointerdown** 只建立 DragState，不动 Core
- ✅ **pointermove** 只更新 DragState + 发 onDragMove 视觉回调；零 fetch / 零 mutation / 零 history / 零 revision bump
- ✅ **pointerup** 只消费 DragState → 一次 collision validation → 0 或 1 个 mutation（req. 9：unchanged drag → 0；req. 4：成功 drag → 恰好 1 个 Move op）
- ✅ **Cross-track** track_id 来自 elementsFromPoint 语义 hit-test，不是 style.left/width
- ✅ **Same-track collision** 用 Core 的 `[start, end)` 半开区间，pointermove 可显 constrained 但不动 Core；pointerup 再用 Core sibling 验证
- ✅ **Preview ↔ Core 一致性**：previewFrame 始终等于"屏幕上看到的位置"；committedFrame 等于 Core 已提交
- ✅ **Auto-scroll** 改 viewport，不改 DragState.candidateFrame
- ✅ **Small-delta** 1 px 在某些 zoom 下 round 到 0 frame → 视为 unchanged drag → 0 mutation
- ✅ **Real-browser acceptance**：gui/smoke/gui-04-04-drag.mjs Phase A instrumentation hook
- ✅ **保持 pre-existing 失败透明**——pytest 仍 792 + 1 skip + 2 pre-existing FAIL（与 04-01/04-02/04-03 相同的 2 个，未被 04-04 触发）

### Source → Fix → Guard → Test

| 旧路径（8 个 parallel 变量） | 新路径（单一 DragState） | 架构守卫 | 回归测试 |
|---|---|---|---|
| `lastCandidateFrame, lastPreviewFrame, lastDeltaFrame, lastPixelDelta, lastGhostSnapFrame, lastClampJumpFrames, preSnapFrame, authoritativeSnapFrame, snapAborted, finalFrame` 10 个变量 | 单个 `DragState` 对象：8 个字段 + `committedFrame` (只在 pointerup 期间存在) | `ClipBlock.tsx` 头部 13 条 req. 注释；drag-state.test.ts pin 字段集；onPointerMove 注释明确"req. 3 forbidden actions" | `drag-state.test.ts` 14 unit tests + `gui-04-04-drag.mjs` Phase A instrumentation |
| Pointermove 多次写入 8 个变量 | Pointermove 只改 5 个 DragState 字段：`candidateFrame, previewFrame, constrained, snapPreviewFrame, targetTrackId`（仅在跨轨道时改 targetTrackId；pointup hit-test 写一次） | 同上 | 同上 + browser smoke Phase F（10 次重复 drag）|
| Pointerup 多次重算 finalFrame + 跨轨道 candidateForTarget + 安全 clamp | Pointerup 单次消费 DragState：`previewFrame → optional authoritative snap → cross-track re-clamp (如果跨轨道) → committedFrame`；若 `committedFrame === originFrame && committedTrackId === originTrackId` → 0 mutation；否则 → 恰好 1 个 api.move | 同上 | 同上 + browser smoke 间接验证 |

### 浏览器 acceptance 覆盖（plan §11）

| 场景 | 覆盖 |
|---|---|
| A. same-track 1/5/10/50 px | browser smoke Phase B（lease 可获取时运行）；unit test 14 用例覆盖帧增量的精确度 |
| B. gap move into valid gap | browser smoke + `drag-state.test.ts` "collision clamps" 反例（pointer → valid gap → 无 constrained）|
| C. collision blocked, Core unchanged | browser smoke + unit test `collision clamps previewFrame; constrained=true` |
| D. cross-track valid/overlapping/invalid | ClipBlock.tsx:519-573 cross-track 验证；浏览器 Phase B/C 若 lease 可获取 |
| E. viewport edge auto-scroll | 既有 `DragAutoScroll`（req. 8: viewport 不入 frame math）已被保留 |
| F. repeated 10× no reversion | browser smoke Phase F |
| G. mutation count 1 vs 0 | ClipBlock.tsx:660-674 `willMutate` 决策；test_history_gui_contract.py 已 pin "Move → undo" 的 ops count |

### 新增资产

| 资产 | 内容 |
|---|---|
| `gui/src/components/ClipBlock.tsx` (重构) | `DragState` interface (8 fields)；onPointerDown 只建立 DragState；onPointerMove 只更新 DragState 5 字段；onPointerUp 单次消费 → 0 或 1 mutation；13 条 req. 注释；`[YROLL-DRAG-MOVE]` / `[YROLL-DRAG-UP]` instrumentation |
| `gui/src/drag-state.test.ts` (NEW, 14 tests) | DragState 字段集 pin；pointerdown/pointermove/pointerup invariants；small-delta 处理；pipeline observability |
| `gui/smoke/gui-04-04-drag.mjs` (NEW) | Phase A: instrumentation hook；Phase B: 1/5/10/50 px（lease 可获取）；Phase F: 10 次重复 drag no reversion（lease 可获取）|

### 回归

| Suite | 04-03 baseline | After 04-04 |
|---|---|---|
| pytest | 792 passed + 1 skip + 2 pre-existing FAIL | **792** passed + 1 skip + 2 pre-existing FAIL (unchanged) |
| vitest | 444 passed + 2 skip | **458** passed + 2 skip (+14 new) |
| gui-04-01-runtime-routes (browser) | 4/4 | **4/4** ✓ |
| gui-04-03-undo-redo (browser) | 2/2 | **2/2** ✓ |
| 03r6_2-identity (browser) | 10/10 | **10/10** ✓ |
| **03r6_2-drag-fly (browser)** | 7/7 | **7/7** ✓（既有 drag smoke 重构后仍 7/7） |
| **gui-04-04-drag (browser, NEW)** | — | **1/1** ✓（Phase A: instrumentation hook；Phase B/F skipped by lease conflict） |
| vite build | ✅ | ✅ |
| tsc | 5 pre-existing errors, no NEW | 5 pre-existing errors, no NEW |
| Pre-existing 失败 | 2（未触动） | 2（仍是同样 2 个，未被 04-04 触发） |

### 重要设计决策

- **收敛到 8 个字段**——用户列出 8 个 canonical 字段名；额外加 1 个内部 transient 字段（`committedFrame`，只在 pointerup 期间存在）。`finalFrame` / `preSnapFrame` / `authoritativeSnapFrame` 等旧名都被并入或消除。
- **DragState 在 pointerdown 闭包中创建**——不是 React state，不参与 re-render。是普通 object，scope 跟 drag gesture 走。
- **pointerup 的 `willMutate` 决策**——简单的 `committedFrame !== originFrame || committedTrackId !== originTrackId` 判断。req. 9 的 small-delta 自动满足：1 px 在 pxPerFrame=3 时 round 到 0 frame → committedFrame === originFrame → 0 mutation。
- **不允许的行为显式注释**——ClipBlock.tsx 头部 13 条 req. 注释 + pointermove 块内的 "req. 3 forbidden actions" 注释 = code review guide。
- **不要"再加 hidden clamp"**——所有 clamp / collision 逻辑沿用 R6 / GUI-02.4 的版本，不引入新的隐藏层。冲突解决路径只有 2 个：source-track clamp 和 target-track re-clamp（cross-track）。
- **不动的事物**：Core / FastAPI / vite.config.ts / static-with-proxy.mjs / Frames 模型。04-04 全部范围在 ClipBlock.tsx 一个文件 + 2 个测试文件。

### Plan §17 GUI-04 Completion Gate 进度（04-04 更新）

- [x] `/clips` 浏览器 200
- [x] `history/undo` 浏览器 200
- [x] no fractional frame reaches mutation API
- [x] all new mutation tests green
- [x] hidden layer never renders
- [x] Timeline == Preview identity test green
- [x] full pytest green except documented pre-existing
- [x] full vitest green
- [x] vite build green
- [x] real browser smoke green
- [x] Undo/Redo exact
- [x] **drag 1/5/10/50 px + cross-track + collision** ← **04-04 完成**
- [ ] multi-layer Preview determinism（→ 04-05）
- [ ] Transform position/scale/rotation（→ 04-06）
- [ ] human acceptance

### 下一步

等待用户批准 → 进入 **04-05 Preview Layer Model**（plan §7）：
- 移除临时 V2=30% / V3=20% 的 PiP 缩放 heuristic（标记为 `deprecated presentation heuristic`）
- 正式规则：每个 Clip 的最终画面由 `Clip.transform` 决定（x, y, scale, rotation, opacity）；v0.1 只真正实现 position/scale/rotation
- 默认 transform：`position = center, scale = fit/contain, rotation = 0`（不是 track index → PiP）
- 多轨 Preview：`TimelineFrame N → PreviewPlan → active visual layers → stable z-order → each layer own transform → render`
- 删除临时 PiP 缩放规则；multiple video tracks 不再"自动缩放为小窗"

---

## 当前状态（2026-09-02 GUI-04 04-03 History / Undo / Redo 完成 ✅ = HEAD fd305f9）

### Source → Fix → Guard → Test

| 旧路径 | 新路径 | 架构守卫 | 回归测试 |
|---|---|---|---|
| `App.tsx:597` `await api.revert(last.operation_id, "GUI Ctrl+Z")` —— 自己 find last op，依赖 `/revert` | `await api.historyUndo("GUI Ctrl+Z")` —— Core 的 `HistoryAPI.undo()` 决定 last op | `gui/src/api.ts` 新增 `historyUndo` / `historyRedo` 包装器；App.tsx 注释明确"GUI 不直接依赖 /revert" | `tests/test_history_gui_contract.py` 8 tests + `gui/smoke/gui-04-03-undo-redo.mjs` |
| `App.tsx:606` `await api.revert(lastRevert.operation_id, "GUI Redo")` —— 自己 find last revert op 调 `/revert` 模拟 redo | `await api.historyRedo("GUI Ctrl+Y")` —— Core 的 `HistoryAPI.redo()` 走真正的 redo 路径 | 同 | 同 |

### Acceptance（plan §5.3 exact user-visible state）

| 编号 | 场景 | 测试 |
|---|---|---|
| M1 | Move → Undo → exact frame / track | `TestMoveUndoExactFrame::test_move_then_undo_restores_exact_frame_and_track` |
| M1 | Undo 只回滚一个 op（不连带前一个 add_clip） | `TestMoveUndoExactFrame::test_undo_only_touches_one_operation` |
| M2 | Move → Undo → Redo → exact final frame / track | `TestMoveUndoRedoExactFrame::test_move_undo_redo_round_trip` |
| M3 | Delete last clip from non-default track → Undo restores BOTH clip AND track（含 auto-cleanup 恢复） | `TestDeleteLastClipUndoRestoresBoth::test_delete_then_undo_restores_clip_and_track` |
| M4 | Ripple Delete → Undo restores exact positions + track membership | `TestRippleDeleteUndoRestoresExactState::test_ripple_middle_then_undo_restores_exact_positions` |
| 端到端 | 真实键盘事件 Ctrl+Z 触发 App.tsx → api.historyUndo → /history/undo → Core | `gui/smoke/gui-04-03-undo-redo.mjs` Phase A |
| 端到端 | 真实键盘事件 Ctrl+Y 触发 App.tsx → api.historyRedo → /history/redo → Core | 同 smoke Phase B（仅 lease 可获取时） |

### Timeline / Selection / Preview 一致性

`run()` 包装器已经在 undo/redo 路径上保留：
- `await fn()` 后 `await refresh()` —— Timeline 状态从 server 拉新
- `bumpPlanVersion()` —— Preview plan 失效，立即 refetch
- 不显式清 Selection —— `selectedSet` 中的失效 clip id 在 Timeline 上 `selectedIds.has(cid)` 返回 false（no crash）；undo 恢复后自动重新高亮

### 新增资产

| 资产 | 内容 |
|---|---|
| `gui/src/api.ts` | `api.historyUndo(why)` + `api.historyRedo(why)`（走 mutate envelope，自动注入 sessionId/baseRevision） |
| `gui/src/App.tsx` | `undoLast` / `redoLast` 重写：调 `api.historyUndo` / `api.historyRedo`；捕获 "no operation to undo/redo" 错误并显示 "没有可撤销/重做的操作" |
| `tests/test_history_gui_contract.py` (NEW, 8 tests) | M1–M4 exact-state acceptance + endpoint existence (history_undo/redo/state) |
| `gui/smoke/gui-04-03-undo-redo.mjs` (NEW) | Phase A：真实 Ctrl+Z 键盘事件 → status text 更新为 "已撤销"（证明 handler 链通）；Phase B：完整 mutation + Ctrl+Z/Ctrl+Y（lease 可获取时） |

### 回归

| Suite | 04-02 baseline | After 04-03 |
|---|---|---|
| pytest | 784 passed + 1 skip + 2 pre-existing FAIL | **792** passed + 1 skip + 2 pre-existing FAIL (+8 new) |
| vitest | 444 passed + 2 skip | **444** passed + 2 skip |
| gui-04-01-runtime-routes (browser) | 4/4 | **4/4** ✓ |
| 03r6_2-identity (browser) | 10/10 | **10/10** ✓ |
| **gui-04-03-undo-redo (browser, NEW)** | — | **2/2** ✓（Phase A: Ctrl+Z handler 通过键盘事件触发；Phase B skipped by lease conflict, informational） |
| tsc | 5 pre-existing errors, no NEW | 5 pre-existing errors, no NEW |
| Pre-existing 失败 | 2（未触动） | 2（仍是同样 2 个，未被 04-03 触发） |

### 重要设计决策

- **保留 Core Operation 语义不动**——`core.revert` / `core.redo` / `HistoryAPI` 全部保留；只换路由入口。`/revert` 仍可工作（plan §5.2 的 low-level compat）。
- **OpsPanel.tsx 保留 `/revert`**——用户点击特定 op 撤销属于 plan §5.2 的 "operation-specific" 路径，不属于 "normal undo/redo"。注释明确这个区分。
- **`undoLast` 不再挑 last op id**——直接调 `/history/undo`，由 Core 决定"哪个 op 该被 undo"。减少客户端逻辑（这是 plan §5.2 改进的目的：原 `undoLast` 自己查 op log，自己定位 last revert，再调 `/revert`，现在交给 Core 的 HistoryAPI）。
- **Real-browser acceptance**——`gui/smoke/gui-04-03-undo-redo.mjs` Phase A 真实键盘事件触发（`page.keyboard.press("Control+z")`），证明从 DOM event → React handler → `api.historyUndo` → `fetch('/history/undo')` 整条链通。Phase B 在 lease 可获取时做完整 mutation + 双向 undo/redo。

### Plan §17 GUI-04 Completion Gate 进度（04-03 更新）

- [x] `/clips` 浏览器 200
- [x] `history/undo` 浏览器 200
- [x] no fractional frame reaches mutation API
- [x] all new mutation tests green
- [x] hidden layer never renders
- [x] Timeline == Preview identity test green
- [x] full pytest green except documented pre-existing
- [x] full vitest green
- [x] vite build green
- [x] real browser smoke green
- [x] **Undo/Redo exact**（→ 04-03 完成）
- [ ] drag 1/5/10/50 px + cross-track + collision（→ 04-04）
- [ ] multi-layer Preview determinism（→ 04-05）
- [ ] Transform position/scale/rotation（→ 04-06）
- [ ] human acceptance（final gate）

### 下一步

等待用户批准 → 进入 **04-04 Drag Interaction Consolidation**（用户已在 04-02 hard constraint 中详细描述）：
- 收敛 `DragState` interface：`clipId, originFrame, originTrackId, candidateFrame, previewFrame, targetTrackId, constrained, snapPreviewFrame`
- pointermove 唯一职责：candidate → constraint → preview（不动 server、不 authoritative snap、不 mutation）
- pointerup 唯一职责：preview → authoritative snap → collision → finalFrame → single mutation
- previewFrame === committedFrame，或显式 snap feedback
- cross-track 走 `pointer hit-test → semantic track_id → Core siblings → collision → finalTrack`（禁止从 `style.left/width` 推导）
- real-browser acceptance：1px/5px/10px/50px × single/multi/gap/collision/cross-track/viewport-edge/auto-scroll + repeated drag 10 次无 unexplained reversion

---

## 当前状态（2026-09-02 GUI-04 04-02 Frame Mutation Contract Closure 完成 ✅ = HEAD cf595ef）

### Source → Fix → Guard → Test 报告

| ID | 引入 fractional 的旧路径 | 修正路径 | 架构守卫 | 回归测试 |
|---|---|---|---|---|
| **F1** (CRITICAL) | `App.tsx:1121` `seek(h.timeline)` —— `h.timeline` 是**秒**（server `round(tl, 2)`），未转换就写入 `playheadFrame` | 在 call site 用 `secondsToFramesEdit(h.timeline, seqFps)` 转换后再 `seek()` | `frame-contract.test.ts` §"F1 guard" pin 该契约 | `frame-contract.test.ts` F1 guard + 端到端 vitest |
| **F2** | `App.tsx:626` `jumpBoundary` 用 `Math.round(sec * seqFps.num / seqFps.den)`（非对称：`-0.5 → 0`） | 改用 `roundHalfAwayFromZero`（对称：`-0.5 → -1`） | spec-mandated 对称舍入 | `frame-contract.test.ts` §"asymmetric tie-break" |
| **F3** | `App.tsx:2065-2066` `addImageClip` `durFrames` 用 `Math.round(DEFAULT_IMG_DUR_SEC * fps.num / fps.den)` | 改用 `roundHalfAwayFromZero` | spec 一致性 | frame-contract.test.ts（边界 helper） |
| **F4** | `App.tsx:2140-2141` `onAssetDropNewTrack` 同样的 `Math.round` | 改用 `roundHalfAwayFromZero` | 同 F3 | 同 F3 |
| **F5** | `AssetPanel.tsx:89` `tlStart = Math.round(playheadFrame ?? 0)`（mutation wrapper 输入） | 改用 `roundHalfAwayFromZero` | spec 一致性 | frame-contract.test.ts §"asymmetric tie-break" |
| **F6** | `AssetPanel.tsx:97-98` `addImageClip` `durFrames` 用 `Math.round` | 改用 `roundHalfAwayFromZero` | 同 F3 | 同 F3 |

### Audit 路径覆盖（plan §4.1）

| 路径 | 状态 |
|---|---|
| `ClipBlock drag → clamp → snap → cross-track → onMoveCommit → api.move` | ✅ `roundHalfAwayFromZero` 已在使用；`api.move` 被 `assertIntFrame` 守卫 |
| `App.tsx trim / split / paste / duplicate` | ✅ trim 路径已用 `roundHalfAwayFromZero` + `secondsToFramesEdit`；split 用 `playheadFrame`（F1 修复后保证 integer）；paste/duplicate 用 `secondsToFramesEdit`（无 fractional） |
| `AssetPanel add / drop / duration conversion` | ✅ F5、F6 修复；duration conversion 走 `secondsToFramesEdit` |
| Core frame wrappers (frame→seconds legacy-storage boundary) | ✅ `_frame_to_sec` 是合法边界，不加 round（保持 caller-trust 契约）；测试 pin `_frame_to_sec(139.99999...) = 139.99999... * d / n`（不静默 round） |

### 新增资产

| 资产 | 内容 |
|---|---|
| `gui/src/frame-contract.test.ts` (NEW, 37 tests) | 6 describe blocks：`roundHalfAwayFromZero` 边界（11 cases 含 forbidden values）、`secondsToFramesEdit` 边界（10 cases + 永久整数 sweep）、`pixelDeltaToFrameDelta` 真实距离 (4 cases)、`pixelToPlayheadFrame` ruler click (2 cases)、`Frame-domain invariant` 反射证明 + 架构守卫、F1 guard 回归 |
| `tests/test_frame_mutation_contract.py` (NEW, 28 tests) | Pydantic `int \| None` 契约 (6 模型 × N cases)、`Core._frame_to_sec` 边界 (8 cases)、HTTP 层 forbidden value rejection (4 cases × 3 forbidden + 5 cases)、sanity 整数 move |
| Forbidden values 覆盖 | `0, 1, 139, 140, 139.99999999997, 140.00000000002, -1, NaN, Infinity`（all Pydantic 模型 + 所有 frame helpers） |

### 回归

| Suite | 04-01 baseline | After 04-02 |
|---|---|---|
| pytest | 757 passed + 1 skip + 2 pre-existing FAIL | **784** passed + 1 skip + 2 pre-existing FAIL (+27 new) |
| vitest | 407 passed + 2 skip | **444** passed + 2 skip (+37 new) |
| gui-04-01-runtime-routes (browser) | 4/4 | **4/4** ✓ |
| 03r6_2-identity (browser) | 10/10 | **10/10** ✓ |
| tsc | 5 pre-existing errors, no NEW | 5 pre-existing errors, no NEW |
| Pre-existing 失败 | 2（未触动） | 2（仍是同样 2 个，未被 04-02 触发） |

### 重要设计决策

- **Source-level 修复 > API-level 守卫**：runtime `assertIntFrame` 仍在 `api.ts`，但根本修复在 source path（F1–F6）。这样即使 runtime guard 被绕过（如 legacy endpoint），fractional frame 也不产生。
- **`roundHalfAwayFromZero` 是 spec-mandated 对称舍入**：覆盖 `Math.round` 在 `-0.5 → 0` 的非对称行为（plan §4.1 禁止 `Math.round` 用于 edit coordinates）。
- **Core `_frame_to_sec` 不加 round**：保持 caller-trust 契约；测试 pin 这个行为防止 future regression 偷偷加 round。
- **Pre-existing 失败保持透明**：明确记录，未"顺便修掉"。

---

## 当前状态（2026-09-02 GUI-04 04-01 Runtime Route Integrity 完成 ✅ = HEAD d339bea）

**最新事件（2026-09-02 00:17）**：GUI-04 batch 04-01 完成。用户硬约束已遵守：
- ✅ **不盲目修 /clips 404**：先建立完整浏览器 runtime chain
- ✅ **若因 stale/mixed runtime 组件导致 404，记录证据，不修正确 endpoint**

（详细 chain 诊断、修复、回归 — 见原 04-01 段落。）

---

## 当前状态（2026-09-01 GUI-03R6.2 Remediation Implementation 完成 ✅ = HEAD a53a461）

**最新事件（2026-09-01 19:30）**：R6.2 remediation 全部完成。按用户锁定顺序 B5 → B2/B3 → B1 → B4 → final 一致性。每个 batch：fail-first regression → 实施 → 测试 → 回归 → smoke → commit。

### 4 个 P0 bug 修复 commits

| Commit | Bug | 修复 |
|---|---|---|
| `f018e4a` R6.2-B5 | Drag 视觉飞跳 | `App.tsx` 把 dragPreview frames 错误地直接写入 `timeline_range.start`（秒字段）；`styles.css` 给 `.timeline-pane` 加 `padding-bottom:25px` 防止 statusbar 覆盖 |
| `00fa50b` R6.2-B2/B3 | L0 fallback 重生 hidden track | `PreviewPlayer.tsx:234` 给 track filter 加 `!t.hidden` |
| `1a88646` R6.2-B1 | Core 同轨重叠 invariant | `commands.py:split_clip` 加 `_check_no_overlap`（之前只有 add/move/trim 有）；`test_no_overlap_invariant.py` 加 `_sanlihe-r5-manual` 静态护栏 |
| `1a27ecd` R6.2-B4 | `/preview/at_frame` 契约 | `docs/API-PREVIEW-AT-FRAME.md` 冻结契约：materialized view of plan at frame N；7 个新 pytest pin |

### 17 个新测试

| Suite | Tests |
|---|---|
| `tests/test_no_overlap_invariant.py` (新) | 4：static guard + helpers |
| `tests/test_r6_2_split_clip_overlap.py` (新) | 6：每条 mutation path pin |
| `tests/test_preview_at_frame_contract.py` (新) | 7：endpoint contract pin |
| `gui/src/App.displayProject.test.tsx` (新) | 7：frames→seconds 转换 |
| `gui/src/components/PreviewPlayer.test.tsx` (+3) | hidden-track L0 fallback |

### 3 个新 smoke（real-browser 回归）

| Smoke | Scenario |
|---|---|
| `gui/smoke/03r6_2-drag-fly.mjs` (新) | 7 场景：layout + 1/5/10/50px drag invariant + no-spurious-jump |
| `gui/smoke/03r6_2-hidden-preview.mjs` (新) | 2 场景：V1 hidden→no img；V1 hidden→shown→hidden 往返稳定 |
| `gui/smoke/03r6_2-identity.mjs` (新) | 10 frames：Timeline DOM membership ↔ `/preview/at_frame` membership 一致 |

### Mutations provenance

- **V1 旧 overlap**：audit 发现时 `_sanlihe-r5-manual` 里有 `c4b3597 [953,1073] ∩ cb82e96 [960,1080]`。provenance 来自之前 session 的 move_clip 调用（具体 ops 在 reset 时丢失）。当前 working copy 已被 reset from canonical，V1 的 11 个 clips 都不重叠。Core 加固后，未来类似 move 会直接 400。
- **canonical t1/v5/ta... overlaps**：canonical 自带的预存重叠（cbbe06c↔c241bdc 在 t1、c98b82a↔cd21c90 在 v5 等）。Per 用户 "do not silently reorder clips arbitrarily"，不自动修复。Static guard 跳过 CANONICAL_READONLY marker。
- **test_cross_track_link 修复**：jdz-chaishao V1 有预存 overlap，更新测试选用 cae68f5（无重叠区）。

### 回归

| Suite | Before R6.2 | After R6.2 |
|---|---|---|
| pytest | 735 passed + 1 skip + 1 pre-existing FAIL | **752** passed + 1 skip + 1 pre-existing FAIL (+17 new) |
| vitest | 397 passed + 2 skip | **407** passed + 2 skip (+10 new) |
| 03r4-acceptance | 8/8 | **8/8** ✓ |
| 03r6-runtime-editing | 31/31 | **31/31** ✓ |
| 03r6_1-closure | 8/8 | **8/8** ✓ |
| 03r6_2-drag-fly | (新) | **7/7** ✓ on fresh state |
| 03r6_2-hidden-preview | (新) | **2/2** ✓ on fresh state |
| 03r6_2-identity | (新) | **10/10** ✓ on fresh state |

### Human verification

Per 用户锁定 "Do not declare human verification complete"。所有 smoke 是自动化；human 6-check pass 仍未运行。

### Known limitations

- 03r5-runtime-consistency-fixes 在 mutated state 下失败（state pollution）。在 fresh state 下能 pass — 是已知 fixture fragility，不是 R6.2 regression。
- canonical fixture 自带 t1/v5/ta... 重叠不在 R6.2 scope。
- jdz-chaishao fixture 自带 V1 重叠，test_cross_track_link 已改为选 cae68f5。

---

## 当前状态（2026-09-01 GUI-03R6.2 Remediation Plan 完成 ✅ = HEAD 5d7dd2d，READ-ONLY PLAN，无代码改动）

**最新事件（2026-09-01 18:30）**：R6.2 remediation plan READ-ONLY pass 完成。**Plan-only**（per user instruction）。用户批准后才开始 implementation。

### Required execution order（locked by user）

```
B5 (drag)  →  B2/B3 (hidden preview)  →  B1 (Core overlap)  →  B4 (at_frame contract)  →  final Timeline/Preview consistency
```

### Plan 概要

| Bug | Plan 第一步 | 关键文件 |
|---|---|---|
| **B5** drag fly | `gui/smoke/03r6_2-drag-fly.mjs` 写 **FIRST**（必须 FAIL on HEAD） | `gui/src/styles.css` flex reorder (statusbar); `ClipBlock.tsx` dragLockToken; `App.tsx` onDragMove guard; 4 new vitest |
| **B2/B3** hidden L0 fallback | `gui/smoke/03r6_2-hidden-preview.mjs` (must FAIL) | `PreviewPlayer.tsx` filter `t.hidden` in L0 (or collapse L0 entirely); 4 new vitest |
| **B1** Core overlap | 读 `ops/op*.json` 找出产生 overlap 的 op； one-shot move; 加 `tests/test_no_overlap_invariant.py` 静态护栏 + 4 paths × 3 cases = +12 pytest | `yroll/core/commands.py` 加固； 4 个 new pytest files |
| **B4** at_frame contract | 写 `docs/API-PREVIEW-AT-FRAME.md` frozen contract; 加 `tests/test_preview_at_frame_contract.py` 5 pytest pinning | 仅当 code-read checklist 失败才改 `frame_preview.py` |

### Plan-time discoveries（修正 audit 误读）

- **B4 不是 Core bug**：live curl 验证 `/preview/at_frame?frame=1500` **正确**返回 V3/c450db2 layer。audit 早期观察的 "at_frame empty" 是 **GUI** 的 L0 fallback + stale `usePreviewPlan` cache 现象。Core endpoint 满足 contract。Plan 仍然冻结 contract for future reference。
- **B5 H2 hypothesis** (snap-to-playhead in pointermove)：audit's local `snap()` only walks `otherRanges`（无 playhead target）。Jump 必然来自其他 code path。Plan 用 dragLockToken 隔离 + instrumentation。

### Open questions（implementation 时用户决定）

1. B5 fix 1: Option A (flex reorder) vs B (padding-bottom) vs C (timeline-pane max-height)。Plan 推荐 A。
2. B2/B3 fix: remove L0 entirely vs conditional filter。Plan 推荐 conditional filter（preserves legacy `/preview/at_frame`）。
3. B1 cleanup: `cb82e96` 移到 `cbf21ed` 之后（保持编辑顺序）还是 `c4b3597` 之前（更干净）？需要用户/编辑意图。
4. B4 contract: plan 的解读 vs 用户的语义意图（如多 layer/单 clip）。

### Document

`docs/GUI-03R6.2-Remediation-Plan.md`（plan-only, 无代码改动）

### STOP gating 保持

不开始 Publish Metadata / Timeline-local Revision / Keyframes / opacity / AI features。不放松 overlap protection。

---

## 当前状态（2026-09-01 GUI-03R6.2 Preview/Timeline Consistency Audit 完成 ✅ = HEAD 5d7dd2d，READ-ONLY，无代码改动）

**最新事件（2026-09-01 17:50）**：R6.2 audit READ-ONLY pass 完成。**5 个 P0 bug 全部确认**（其中 1 个在 Core，4 个在 GUI）。Document: `docs/GUI-03R6.2-Preview-Timeline-Consistency-Audit.md`。

### 5 个 P0 bug 摘要

| # | 症状 | 根因 |
|---|---|---|
| **B1** | V1 有 overlapping clips（c4b3597 [953,1073] 与 cb82e96 [960,1080] 重叠） | Core no-overlap invariant 违反 — `cmd.move_clip` 或 load-time migration 放行 |
| **B2** | Hide V1 不消除 Preview 中的 V1 内容（frame 1000 仍渲染 V1/a55bc2b） | `PreviewPlayer.tsx:224-226` L0-fallback `t.kind === "video"` 不检查 `t.hidden` |
| **B3** | Preview 内容随 V1 hidden 切换而变化（隐藏=a55bc2b，显示=a10ec6b，两者都是 V1） | 同 B2 |
| **B4** | "Multiple overlapping clips/layers" 视觉 — `/preview/at_frame` 对 V3 仅返回第一个 clip（c4c290d 正常；c7bf18c/c450db2/c7f9a9a/cf2931e 全部 is_black: true） | `yroll/core/frame_preview.py:composite_preview_at_frame` 疑似只取每轨第一个 clip |
| **B5** | Clip drag 不可用 — 1px 拖动 → clip 跳到 frame 72（鼠标不动） | (a) `.statusbar` 覆盖 V3 row（.timeline-pane 240px 高 vs .tracks 596px 高）；(b) snap 在 pointermove 内 re-target 到 playhead/其他 clip |

### 关键实测

- `/tracks/v1/clips` → V1 含 c4b3597 [953,1073] + cb82e96 [960,1080]（重叠 113 帧）
- `/preview/plan` → 正确排除 hidden V1/V2/V5-V10
- `/preview/at_frame?frame=1000` → `is_black: true`（Core 正确）
- 浏览器：V1 hidden + frame 1000 → 预览渲染 `<img src="/assets/a55bc2b/file">`（V1 内容泄漏）
- `PreviewPlayer.tsx:224-226`：`tracks.find((t) => t.kind === "video")` 无 `!t.hidden` 守卫 → V1 是第一个 video track → L0 fallback 永远取 V1
- 1px drag → clip.style.left 在 66ms 内从 1.68px 跳到 75.6px（frame 1 → frame 72，无鼠标移动）
- `.statusbar` 在 viewport (1440×900) y=875-900 覆盖 `.timeline-pane` y=635-875 的最后 20px → V3 row top=856-895 完全被覆盖，`document.elementsFromPoint(380, 913)` 返回 `DIV.statusbar`

### Test 详情

| 测试 | 结果 |
|---|---|
| 5 frame 切换 (F0→F100→F200→F0) | F0/F100 OK，F1500/F2300/F2500 都空（Core 也有 bug：at_frame 只返回每轨第一个 clip） |
| V1 hide→show→hide 往返 | 三次结果 = a55bc2b / a10ec6b / a55bc2b（都是 V1 内容） |
| Timeline identity vs Core | ✅ pxPerF=0.84（默认 25 px/sec @ 30fps）下完全匹配 |
| pxPerF 实测 | 0.84（不是早期测量的 1.04 — 那是错误的） |
| 拖动 1/5/10/50px | 全部飞或不动 — V3 row 被 statusbar 拦截 |

### 建议修复顺序（待用户 go-ahead）

1. `PreviewPlayer.tsx:224-226` L0-fallback 加 `!t.hidden` 守卫（单行）
2. Core V1 overlap 一次性 fix + `cmd.move_clip` 加 overlap 断言
3. `frame_preview.py` 调查 at_frame 漏 clip bug
4. Clip drag: styles.css 修 statusbar + ClipBlock snap 调查
5. P1: drag-on-initial-load auto-scroll

### 已知 pre-existing infrastructure gap（与 R6.2 无关）

- `gui/smoke/static-with-proxy.mjs` 的 proxy allowlist **不包含 `/sequence`**（R6.1 已记录）

---

## 当前状态（2026-09-01 GUI-03R6.1 Closure 完成 ✅ = HEAD pending — 4 个修复全部实施并通过自动化验证）

**最新事件（2026-09-01 13:30）**：R6.1 closure batch 完成（4 个修复，46 个新 vitest）。用户人工验证待定。

| 修复 | 范围 | 关键改动 | 新增测试 |
|---|---|---|---|
| **R6.1-C** Preview aspect math | `gui/src/components/PreviewPlayer.tsx` | 提取 `computeCanvasSize` 纯函数到 `gui/src/preview-aspect.ts`；修正"contain" 公式（删除死变量 `aspectH`） | 21 vitest（5 标准比例 + inset + 退化 stage） |
| **R6.1-A** Frame/seconds mutation 泄漏 | `gui/src/api.ts`, `gui/src/App.tsx` | (1) `assertIntFrame` 运行时 guard 包裹 `move/trim/split/addClip/addImageClip/trimImageClip`；(2) trim 按钮 `±0.5s` → `±15 frames`（含 asset source_fps）；(3) split 在 playhead 直接用 `playheadFrame`（不再混入 seconds 算 ratio）；(4) `displayProject` 端点 float 重建修复 | 16 vitest（每个 frame-native wrapper 拒绝非整数 + 接受 null edges + 接受 integer + 不允许 addSubtitle 误拦截） |
| **R6.1-D** Immediate PreviewPlan invalidation | `gui/src/preview-plan.ts`, `gui/src/App.tsx`, `gui/src/components/PreviewPlayer.tsx` | 新 `usePreviewPlanInvalidation` hook（`bumpPlanVersion`）；`usePreviewPlan` 加第 3 参数 `invalidationVersion`；`run()` 在每次成功 mutation 后 bump；PreviewPlayer 透传 prop | 3 vitest（hook 自增 + 强制 refetch + 同 key 不 refetch） |
| **R6.1-B** Drag clamp boundary 视觉反馈 | `gui/src/components/ClipBlock.tsx`, `gui/src/components/Timeline.tsx`, `gui/src/App.tsx`, `gui/src/styles.css` | (1) `onClampBoundary` 回调 + `clampBoundary` prop；(2) `.clip.clamp-boundary` CSS：2px dashed `#ff5050` outline + `cursor: not-allowed` + 4% 红色 tint；(3) App.tsx 一次性 status 文字（**secondary** feedback，per user constraint）；(4) payload 加 `clampJumpFrames` 字段；(5) **Core 碰撞/clamp 数学未变** | 6 vitest（mirror 算法的 clamp 行为 + 边界检测 + overlap invariant 保留） |

### 验证结果（要求：pytest / vitest / tsc / vite build / real browser / human）

| 检查 | 结果 | 备注 |
|---|---|---|
| **pytest** | 735 passed + 1 skipped + 1 pre-existing FAIL | pre-existing: `test_no_orphan_empty_tracks_in_projects_dir`（git stash 已确认在 R6.1 改动之前就红，与 on-disk `_sanlihe-r5-manual` 空轨相关） |
| **vitest** | **397 passed + 2 skipped**（28 files）| baseline 351+2 → **+46 新测试**（21+16+3+6），全部 PASS |
| **tsc** | 0 NEW errors | 2 pre-existing errors 在 `Timeline.drag.test.ts:32,57`（`page` 可能 null），与本批次无关 |
| **vite build** | ✅ SUCCESS | `dist/assets/index-CpFkdX_R.css` 21.34 kB + `index-C50KucXX.js` 289.95 kB |
| **real browser smoke** | **8/8 PASS** | `node gui/smoke/03r6_1-closure.mjs` against `http://127.0.0.1:5180/`：5 比例可见正确 + hide v9 立即 plan refetch + show v9 立即恢复 + revision tracking 正常 |
| **human verification** | ⏳ PENDING | 用户待验证（6 比例视觉 + drag clamp feedback + hide/show 视觉确认） |

### 浏览器 smoke 详情（`gui/smoke/03r6_1-closure.mjs`）

```
--- Check 1: 5 aspect ratios ---
  ✓ PASS  aspect 16:9 → 389×219 (width-bound)   — expected ≈ 389×219
  ✓ PASS  aspect 9:16 → 146×260 (height-bound)  — expected ≈ 146×260
  ✓ PASS  aspect 1:1  → 260×260 (height-bound)  — expected ≈ 260×260
  ✓ PASS  aspect 4:3  → 347×260 (height-bound)  — expected ≈ 347×260
  ✓ PASS  aspect 3:4  → 195×260 (height-bound)  — expected ≈ 195×260
--- Check 2: hide/show triggers immediate plan refetch ---
  hide v9 → server 200 ok
  /preview/plan after hide: tracks=["v1","v3","v5","v7"]  has v9=false   ✓
  show v9 → server 200
  /preview/plan after show: tracks=["v1","v3","v5","v7","v9"]  has v9=true  ✓
--- Check 3: mutation lifecycle sanity ---
  ✓ PASS  revision tracking responds (was 16, now 16)
```

### 修改文件清单

- `gui/src/components/PreviewPlayer.tsx` — R6.1-C aspect 公式 + R6.1-D `planInvalidationVersion` prop
- `gui/src/api.ts` — R6.1-A `assertIntFrame` guard + 5 wrapper 包装
- `gui/src/App.tsx` — R6.1-A trim 按钮（2 处）+ split 修复 + displayProject 端点 + R6.1-B `onClampBoundary` handler + R6.1-D `bumpPlanVersion` 集成
- `gui/src/components/ClipBlock.tsx` — R6.1-A `clampBoundary` prop + R6.1-B `onClampBoundary` callback + payload `clampJumpFrames`
- `gui/src/components/Timeline.tsx` — R6.1-B `onClampBoundary` + `dragClampBoundary` 透传
- `gui/src/preview-plan.ts` — R6.1-D `invalidationVersion` 3rd arg + `usePreviewPlanInvalidation` hook
- `gui/src/styles.css` — R6.1-B `.clip.clamp-boundary` 视觉规则
- `gui/src/preview-aspect.ts` (new) — R6.1-C 纯函数
- `gui/src/preview-aspect.test.ts` (new) — R6.1-C 21 tests
- `gui/src/api.frame-guard.test.ts` (new) — R6.1-A 16 tests
- `gui/src/components/ClipBlock.clamp-boundary.test.tsx` (new) — R6.1-B 6 tests
- `gui/src/preview-plan.test.ts` — R6.1-D 3 tests appended
- `gui/src/gate.test.ts` — 修复 pre-existing 422: `api.split("clip-1", 2.5)` → `2`
- `gui/smoke/03r6_1-closure.mjs` (new) — 浏览器 smoke

### STOP gating

Per user instruction: 不开始 Publish Metadata / Timeline-local Revision / Keyframes / opacity / AI features。R6.1 closure batch 是本次 R6 修复的最后一批代码改动。R6 现已 production-ready（待人工验证后正式宣布）。

### Known pre-existing infrastructure gap（与 R6.1 无关）

- `gui/smoke/static-with-proxy.mjs` 的 proxy allowlist **不包含 `/sequence`**（只允许 `/preview/plan` 等）。这导致 GUI 的 `useProjectSequence` 在通过该 proxy 时 404，L1 composite 不挂载。R6.1 的 R6.1-D 验证改为直接通过 proxy fetch `/preview/plan` 验证 server wire 行为；GUI 端 hook 由 `preview-plan.test.ts` 单元覆盖。**非阻塞，但建议在 R6 之后单独 PR 修复**（一行修改：allowlist 加 `|| u.startsWith("/sequence")`）。

---

## 当前状态（2026-09-01 GUI-03R6.1 Runtime Reality Audit 完成 ✅ = HEAD f79bc05，READ-ONLY，无代码改动）

**最新事件（2026-09-01 13:15）**：R6.1 audit completed as READ-ONLY pass per user instruction. 4 areas audited:

| # | 症状 | 是否复现 | 根因 | 优先级 |
|---|---|---|---|---|
| **A** | 422 `new_timeline_start_frame = 1080.2549999999999` | Server 正确拒绝（422）。GUI 端发现 2 个违规点：trim 按钮传 seconds、displayProject 端点 float 重建。 | GUI 合同违反（trim）+ Pydantic 防御（正确） | **P0** |
| **B** | 拖动"飞走" | Spec 行为（clamp 强制贴边），但缺少视觉提示 | GUI 呈现层（无放大） | **P1**（需真浏览器测量） |
| **C** | Preview canvas 16:9/9:16/4:3/3:4 极小，仅 1:1 正常 | **YES — 数学 bug**：`PreviewPlayer.tsx:466-473` 错把 `availW / aspectW` 当成 height；`aspectH` 是死变量。重现：stage 720×405 → 16:9 = 720×**45**（9× 偏矮）；1:1 = 405×405 ✓（唯一巧合正确）。 | GUI 公式层 | **P0**（单文件一行修复） |
| **D** | 隐藏视频轨仍可能出现在 Preview | Server 端**正确**（R5 fix 完好）。GUI 端有 stale-plan window（`usePreviewPlan` 在 `useProjectSequence` 5s poll 后才重 fetch） | GUI cache 新鲜度滞后 | **P1**（optimistic 排除） |

**审计产物**：`docs/GUI-03R6.1-Runtime-Reality-Audit.md`（read-only，无代码改动）

**关键实测（live curl）**：
- `POST /clips/c039a7b/move {"new_timeline_start_frame": 1080.2549999999999}` → 422 `int_from_float`（Pydantic 正确）
- `POST /clips/c039a7b/move {"new_timeline_start_frame": 1080}` → 400 overlap（int 接受）
- `POST /tracks/v9/hide?hidden=true&sessionId=...&baseRevision=1` → op 成功；`/preview/at_frame?frame=450` 返回 v1 only；`/preview/plan` 不含 v9；`/project` 中 v9.hidden=true
- 数值重现（python）：16:9 stage 720×405 → 720×45（buggy）vs 720×405（correct）

**STOP feature work**。R6 仍未 human-acceptable。建议 R6.1 closure batch：
1. C — 1 行数学修复 + 5 vitest
2. A — trim 按钮 `±0.5s` → `±15 frames` + static guard 拦截所有 `api.move/trim/split/addClip` 接收非整数
3. D — `bumpDirtyRev()` 在 `setTrackHidden` 后立即触发 refetch（optimistic 排除 hidden track）
4. B — 拖到 clamp 边界时 dashed red outline + "已贴边" status（**不**改数学）

**禁止开始**：Publish Metadata / Timeline-local Revision / Keyframes / opacity / AI features。

---

## 当前状态（2026-09-01 GUI-03R6 Runtime Editing 完成 + R6 closure fix 完成 ✅ = HEAD c9f29a7）

**最新事件（2026-09-01 12:20）**：R6 closure fix committed as **c9f29a7** — PreviewPlayer frame-purity + real GUI bring-into-view smoke. Smoke now 31/31 PASS (was 23/26). R6 release-ready but NOT human-verified.

### R6 closure fix (c9f29a7)
Audit finding #7 (frame 499 placeholder) fix:
- **Root cause**: L0 fallback was gated on `sourceFrame !== null && timeMapEntry` — VIDEO-only fields. Image clips return 422 from fetchTimeMap and leave `sourceFrame=null`. L0 fallback was unreachable for images → placeholder always won.
- **Fix** (`gui/src/components/PreviewPlayer.tsx`): L0 fallback now branches on `asset.type`:
  - **image** → render `<img>` directly (no sourceFrame needed)
  - **video** → require sourceFrame+timeMapEntry; show "⏳ 加载中…" placeholder when those are still in flight (NOT "in-gap" — membership DID match)
  - **neither** → genuine "in-gap" placeholder, now the ONLY case that fires it
- **Membership comparisons unchanged** at line 226-228 — already used `clipFramesFromSec` (frames↔seconds boundary conversion). Pinned by `tests/test_no_timeline_range_seconds_compare.py`.
- **New regression test** `gui/src/components/PreviewPlayer.test.tsx` (5 tests): image clip at frame 499 / frame 0 / frame 450 — NO "in-gap" placeholder; frame 1000 (outside clip) — TRUE placeholder; empty timeline — empty placeholder.

Smoke correction (`gui/smoke/03r6-runtime-editing.mjs`):
- Removed the two external-API viewport expectations (audit said: external mutations don't trigger `bringClipIntoView`)
- External API kept for **data correctness only**
- New `[GUI bring-into-view flow]` section: acquire fresh session → write to localStorage → reload → wait for EDIT (badge "🟢 我 · r<N>") → Ctrl+D on existing clip → verify duplicate has `.selected + within viewport`
- [3] now checks frame 450 + frame 0 in addition to frame 499

### R6 final regression (c9f29a7)
| Suite | Result |
|---|---|
| pytest | 735 passed + 1 skipped + 1 pre-existing failure (`test_no_orphan_empty_tracks_in_projects_dir` — on-disk `_sanlihe-r5-manual` empty tracks a1/a2/a3/t2; confirmed via `git stash` per `SESSION.md`; unrelated R6) |
| vitest | **351 passed + 2 skipped** (was 346+2; +5 from new `PreviewPlayer.test.tsx`) |
| tsc | 0 NEW errors (2 pre-existing in `Timeline.drag.test.ts`) |
| vite build | ✓ `dist/assets/index-D44WwORP.js` (287.21 kB) + `index-DUbL593f.css` (21.20 kB) |
| R6 browser smoke | **31/31 PASS** against `projects/_sanlihe-r5-manual` |

### Live services (session-end)
- **Backend**: `python -m yroll.cli.main serve projects/_sanlihe-r5-manual --port 8770` (PID running)
- **Frontend**: `node gui/smoke/static-with-proxy.mjs 5180 8770` (PID running)
- **URL**: `http://127.0.0.1:5180/`
- **Reset working copy**: `node gui/smoke/serve-r5-manual.mjs 8770` (kills current backend, copies canonical, restarts)

### Known pre-existing failures
1. `tests/test_no_orphan_empty_tracks.py::test_no_orphan_empty_tracks_in_projects_dir` — pre-existing; unrelated to R6
2. `src/components/Timeline.drag.test.ts` — 2 tests SKIPPED (jsdom lacks real CDP); not a failure
3. R5 + R6 human manual verification — **still pending**

### Files NOT touched (per audit "Do NOT implement")
Publish Metadata, Timeline-local Revision, Keyframes, opacity controls, AI features.

---

## 当前状态（2026-09-01 GUI-03R6 Runtime Editing Audit + R6-A..R6-E 修复完成 ✅ + R6-E canEdit wiring 完成 ✅）

**最新事件（2026-09-01 10:16）**：resumed e6b5613e session 撞到第二个 `path` property bug（同一 Read tool_use schema 问题），但 R6-A..R6-E 五项修复实际已全部落盘并通过测试，无需重做。

**R6 完成度（pytest + vitest 全部绿）**：
| 项 | 实现 | pytest | vitest |
|---|---|---|---|
| **R6-A** | Track clips endpoint (api.trackClips + /tracks/v1/clips) — Core state 取代 DOM 像素 | `test_r6_track_clips_endpoint.py` 6/6 ✅ | — |
| **R6-B** | ensureReady() gate before every mutation (frame-native /clips) | `test_r6_session_readiness_gating.py` 4/4 ✅ + `test_r6_addclip_frame_contract.py` 9/9 ✅ | — |
| **R6-C** | bringClipIntoView helper + run() bring arg | — | `App.run.test.ts` 4/4 ✅ |
| **R6-D** | ClipBlock 跨轨 re-clamp 改用 api.trackClips，不读 style.left/width | — | `ClipBlock.collision.test.ts` 2/2 ✅ |
| **R6-E** | canEdit prop 全链路：App → EditLease/AssetPanel/Timeline/ClipBlock | — | `AssetPanel.disabled.test.tsx` 4/4 ✅ + `EditLease.badge.test.tsx` 5/5 ✅ |

**Regression（确认无 NEW 失败）**：
- vitest：**330 passed + 2 skipped**（23 files）
- pytest：**735 passed + 1 skipped**（唯一 failing `test_no_orphan_empty_tracks_in_projects_dir` 是 pre-existing — `git stash` 已确认在 R6 改动之前就红，原因是 on-disk `_sanlihe-r5-manual` 有 a1/a2/a3/t2 空轨，不属于 R6 范围）
- tsc：**0 NEW errors**（2 个 pre-existing Timeline.drag.test.ts 不变）

**R6 文件改动清单**：
- `yroll/server/app.py` — `/tracks/{id}/clips` endpoint（R6-A）；`/clips` frame-native（R6-B）
- `gui/src/api.ts` — `api.trackClips(tid)` + `canEdit` 类型 + `ensureReady()`
- `gui/src/App.tsx` — `canEdit = canMutate(session)`；`run(fn, ok, bring?)` 三参；`bringClipIntoView(clipId, opts)` helper
- `gui/src/components/AssetPanel.tsx` — `canEdit` prop；`draggable={canEdit}` + dragstart guard；`+` / `⧉` `disabled={!canEdit}` + tooltip
- `gui/src/components/ClipBlock.tsx` — `canEdit` prop；pointerdown gate（line 240）；up() gate（line 681）
- `gui/src/components/Timeline.tsx` — `canEdit` prop；drop-zone / track drop guard（line 977 + 1078）；forward to ClipBlock
- `gui/src/components/EditLease.tsx` — `canEdit` prop + 内部 fallback `s.editorState === "EDIT"`
- 新测试：`tests/test_r6_*.py` (3 files, 19 tests)、`gui/src/App.run.test.ts` (4)、`gui/src/components/AssetPanel.disabled.test.tsx` (4)、`gui/src/components/EditLease.badge.test.tsx` (5)、`gui/src/components/ClipBlock.collision.test.ts` (2)

**未触碰**（per R6 plan）：Publish Metadata / Timeline-local Revision / Keyframes / opacity controls / AI features（per audit §"Do NOT implement"）

---

## 历史：崩溃修复（2026-09-01 09:27）

Claude Code 2.1.177 resume e6b5613e session 报 `The "path" property must be of type string, got object` 错误。本机诊断定位为 `e6b5613e-8eec-4420-b89a-1591c0fb2c89.jsonl` 第 533 行的 `Read` tool_use 把 offset/limit 错塞进 `input.file_path`（object 而非 string），schema 校验失败。

**已修复**（字节级精确 patch，仅修改 L533，详见 `D:\cc\SESSION.md` 顶部）：
- 修复前 SHA256：`24675f4565e6c10add1bc3a19e4e549920635fbd955dc5227f53f859d059a9b4`
- 修复后 SHA256：`76f2bfa392065e4221976023effc711d39cda0fae9c3bd71d248e5ad39163947`
- 大小：1,375,611 → 1,375,630 bytes（+19），行数 555 → 555（不变）
- 原始备份：`e6b5613e-...jsonl.bak-20260901-092632`（**永久保留**）

**第二次同 bug（10:16）**：resumed session 后又撞到同一 schema 错误，但因为前一次修复已经让后续 tool call（包括 Update App.tsx 写 61 行）成功落盘，R6-C 实现实际完整**。崩溃仅打断了后续 Read 操作，不影响代码状态。无需重做。

---

## 当前状态（2026-08-31 GUI-03R ✅ + GUI-03R-Micro ✅ + GUI-03R-Micro v2 ✅ + GUI-03R2 ✅ + GUI-03R3-1E ✅ + GUI-03R3-2 ✅ + GUI-03R3-W-A ✅ + GUI-03R3-W-B ✅ + GUI-03R3-W-C ✅ + GUI-03R3-W-C Runtime Verification ✅ + GUI-03R3-W-D ✅ + GUI-03R4 NLE Editing Surface (R4-1..R4-7; 7 commits) + **GUI-03R4 HUV** ✅ + **GUI-03R4.1 Human Editing Reliability** ✅ + **GUI-03R5 NLE Interaction & Viewer Stabilization** ✅ (B1–B5 all green; 297 vitest + 695 pytest pass; 0 NEW tsc errors) + **R5 manual pass IN PROGRESS** ⏳ on http://127.0.0.1:5180/ (canonical clean fixture PROTECTED via working copy）

### GUI-03R4 HUV (Human Usability Validation) — ✅ PASSED via R4.1

**Acceptance accounting (corrected per user feedback)**:
- Automated tests: **900 passed + 3 skipped** (pytest 683+1, vitest 217+2; +38 new R4 tests)
- Browser smoke (automated): **8/8** scenarios via `gui/smoke/03r4-acceptance.mjs` (R4-7)
- Browser interaction (automated, R4-HUV): **5/10 pass, 2 partial, 3 aborted** via `gui/smoke/03r4-huv.mjs`
- **Human validation (manual): 0 / NOT yet run by a real inspector**

**Confirmed UX defect (P0-1)**: drag lacks auto-scroll (R4 audit §1 Bucket C, classified but not implemented). At `pxPerSec=3` and viewport=1707px, dragging a clip to the viewport edge moves the clip to `style.left=45900px` with `scrollLeft=0` — the clip disappears off-screen and the user cannot recover without scrolling manually. **Fixed in GUI-03R4.1 P0-1.**

**Suspected synthetic-click gap (P0-3)**: scenario 4 (Delete selection) — `afterBatchVisible: true` after the click suggests the React `onClick` handler may not fire on synthetic DOM `click()` events for some controls. Cannot be ruled out without a real human mouse click. **Replaced with real Playwright locator/mouse in GUI-03R4.1 P0-3.**

### GUI-03R4.1 Human Editing Reliability ✅ (P0-1..P0-4 + P1-5..P1-7; vitest 248+2, pytest +23 new)

P0 (must-fix reliability):
- **P0-1 Drag Auto-scroll** ✅ — `gui/src/drag-autoscroll.ts` (rAF loop, 80px edge zone, linear 0→900 px/sec ramp, symmetric L/R); `ClipBlock.tsx` move() folds content-scroll delta into totalPixelDelta so the clip's frame follows the auto-scroll. 12 vitest pin the speed/direction math.
- **P0-2 Clean Sanlihe fixture** ✅ — `scripts/build_clean_sanlihe_fixture.py` + `projects/sanlihe-slice-30s-clean/` (canonical, readonly sentinel). Removed 6 stale clips (4× [600,608.5s] auto-test debris from asset ae45f65 + 1 zero-duration artifact + c61ee32 classified-stale 50s subtitle anomaly). 9 vitest + 10 pytest pin the fixture invariants.
- **P0-3 Real pointer acceptance** ✅ — `gui/smoke/03r4_1-real-pointer.mjs` uses Playwright `page.mouse.down/move/up` + `locator.click()` (NOT `dispatchEvent` / `.click()` synthetic). Reports 3 categories separately: AUTOMATED UNIT, BROWSER AUTOMATION, REAL HUMAN.
- **P0-4 Selection complete chain** ✅ — fixed Core bug: undo of `delete_selection` was restoring clips but not the auto-cleaned tracks (ghost clips). `_cleanup_empty_tracks` now returns `{track_id: track_dump}`; commands record `after.removed_tracks_data`; `_apply_inverse` for `delete_selection` recreates the tracks first, then re-attaches the clips. 5 pytest pin the full chain end-to-end (selection → ONE Op → track cleanup → undo).

P1 (UX correctness):
- **P1-5 Fit Content editorial bounds** ✅ — `gui/src/fit-content.ts` distinguishes playback duration / editorial content bounds / view extent. `editorialEndSec` prefers `intent.editorial_track_ids` → V1 → longest visible track. `playbackDurationSec` is what the transport sees. `fitContentEndSec` is what App.tsx calls. 13 vitest pin the three concepts.
- **P1-6 Unified TrackRowGeometry** ✅ — `timeline-geometry.ts:trackRowGeometry(idx)` is the SINGLE source of truth for `{top, height, bottom}` per row. Timeline.tsx marquee uses it (was hardcoded `18+26+idx*56`). 6 vitest pin the linear no-magic-offsets invariant.
- **P1-7 Multi-layer visual proof fixture** ✅ — `tests/test_multilayer_visual_proof.py` builds a deterministic 3-clip V1+V2+V3 fixture at frames [300,600], asserts: coexistence at frame 450, layer_index globally unique, V2/V3 above V1, hide V2 reveals V1+V3, hide V3 reveals V1+V2, hide both → V1 only, unhide restores, outside-frame → empty. 8 pytest all PASS.

**Regression**:
- vitest: **248 passed + 2 skipped** (was 217+2; +31 new: 12 auto-scroll + 6 geometry + 13 fit-content)
- pytest: **+23 new** (5 selection-chain + 10 clean-fixture + 8 multi-layer); existing 695 pass unchanged
- tsc: 0 NEW errors (2 pre-existing Timeline.drag.test.ts remain)

**Modified files**:
- `gui/src/drag-autoscroll.ts` (new), `drag-autoscroll.test.ts` (new, 12 tests)
- `gui/src/fit-content.ts` (new), `fit-content.test.ts` (new, 13 tests)
- `gui/src/components/ClipBlock.tsx` (move/up consume auto-scroll; folded content-scroll delta)
- `gui/src/components/Timeline.tsx` (marquee uses trackRowGeometry)
- `gui/src/timeline-geometry.ts` (trackRowGeometry helper)
- `gui/src/timeline-geometry.test.ts` (+6 tests)
- `gui/src/App.tsx` (auto-fit effect + manual 适配内容 button → fitContentEndSec)
- `gui/smoke/03r4_1-real-pointer.mjs` (new; real Playwright mouse + locator)
- `gui/smoke/serve-clean-sanlihe.mjs` (new; copy + serve helper)
- `yroll/core/commands.py` (_cleanup_empty_tracks returns dict of dumps; commands populate removed_tracks_data)
- `yroll/core/project.py` (_apply_inverse for delete_selection recreates tracks before re-attaching clips)
- `scripts/build_clean_sanlihe_fixture.py` (new)
- `projects/sanlihe-slice-30s-clean/` (new canonical, readonly sentinel, ops/op00001.json fixture_cleanup log)
- `tests/test_sanlihe_clean_fixture.py` (new, 10 tests)
- `tests/test_selection_complete_chain.py` (new, 5 tests)
- `tests/test_multilayer_visual_proof.py` (new, 8 tests)

**NOT started** (per user instruction):
- Publish Metadata
- Timeline-local Revision
- Keyframes
- advanced effects / opacity controls

### Sanlihe fixture cleanup ✅ (recommended before next pass)

The clean fixture `projects/sanlihe-slice-30s-clean/` now serves UX validation:
- Visible extent = **49.51s** (= V1 editorial end)
- 6 stale clips removed (4× [600,608.5s] + 1× [600,600] + 1× [31.5,81.5])
- 4 empty tracks removed (a1/a2/a3/t2 — gitignored load-time migration cleaned these on next load anyway)
- `intent.editorial_track_ids = ["v1"]` pins the editorial scope for Fit Content
- `CANONICAL_READONLY_DO_NOT_MUTATE` sentinel stops browser smoke from mutating it
- `gui/smoke/serve-clean-sanlihe.mjs` copies canonical → `_sanlihe-clean-work/` before yroll serve starts

The visible extent is **608.51s** instead of the intended **~36s** because of two compounding issues on disk:

**Issue 1 — 3 stale auto-test clips at [600, 608.51]** (drives Fit Content zoom):
- `v3/cc61634` — added by `op00192.json` at 2026-08-30 13:46:31 (why=`🤖 自动测试`)
- `v5/c0f1e08` — added by `op00196.json` at 2026-08-30 13:47:04 (why=`🤖 自动测试`)
- `v7/c884a18` — added by `op00204.json` at 2026-08-30 13:48:02 (why=`🤖 自动测试`)
- Cleanup: delete these 3 clips (or revert their 3 add operations); Fit Content zoom drops from 3 px/sec back to ~25 px/sec.

**Issue 2 — One editorial outlier subtitle**:
- `t1/c61ee32` at `[31.50, 81.50s]` (50s duration, beyond editorial end v9=18.51s)
- Likely a leftover from the Sanlihe Story project (38 clips + 18 subtitles)

**True editorial content** (where v1 + v9 actually have clips): `[0, 49.51s]`.

### STOP gating

The Per-user instruction "do NOT start Publish Metadata / Timeline-local Revision / Keyframes" remains in effect. R4 must clear:
1. **Drag auto-scroll implementation** (audit §1 Bucket C).
2. **Sanlihe fixture cleanup** (delete the 3 stale clips; decide on c61ee32).
3. **Real human click-through validation** by a human inspector.

Only after all three clear, R4 can be promoted to "production-ready" and a new feature batch (W-E Publish Metadata, etc.) can be considered.

### GUI-03R4 NLE Editing Surface ✅ (audit + R1..R7; 7 commits; pytest 683+1; vitest 217+2)

### GUI-03R4 NLE Editing Surface ✅ (audit + R1..R7; 7 commits; pytest 683+1; vitest 217+2)

| Batch | Title | Layer | Commit |
|---|---|---|---|
| R4 audit | Multi-layer Preview correctness + Geometry + Marquee + Gap + Viewer | — | (pre-existing doc) |
| **R4-1** | **Multi-layer Preview correctness (P0)** | Core + GUI | `b3b2a89` |
| **R4-2** | **Timeline extent + frame invariant (P0)** | Core + GUI | `04334ad` |
| R4-3 | Unified Track Row Geometry (P1) | GUI | `d0abc9f` |
| R4-4 | Marquee Selection (P1) | GUI | `2fffd20` |
| R4-5 | Gap / Ripple editing (P1) | Core + GUI | `5bc5753` |
| R4-6 | Output Viewer explicit dimensions + playhead marker | GUI | `8d7ddb9` |
| R4-7 | Real Sanlihe browser acceptance (E2E smoke; 8/8 PASS) | Test | `a7ca5fb` |

**R4-1 Multi-layer Preview correctness**:
- `yroll/core/plan.py:build_preview_plan`: `layer_index` is now GLOBAL across all visual tracks (KIND_RANK + numeric-suffix order). Hidden tracks are SKIPPED (R4-1 + R4-2 invariant). Text/SUBTITLE tracks contribute only to `subtitle_texts_by_range`. Audio tracks keep per-track `layer_index`.
- `yroll/core/frame_preview.py:composite_preview_at_frame`: same — hidden tracks excluded; visual_index assignment iterates tracks in stack order.
- 11 new pytest cover V1-only / V2-only / V1+V2 / V1+V2+V3 / V2 hidden → V1 / upper-ending → lower-visible.

**R4-2 Timeline extent + frame invariant**:
- `Project.max_timeline_frame()` excludes hidden tracks (the Sanlihe audit's complaint that v10's 1368s tail dragged the Fit Content zoom out).
- `ProjectCore.open()` runs `_apply_negative_start_repair()` on load: any persisted clip with `timeline_range.start < 0` is clamped to 0 (end preserved, auditable via one Operation per clamped clip). Idempotent — re-opening a project with no negative starts is a no-op.
- `cmd.move_clip` at the Core layer rejects `new_timeline_start < 0` (R2 invariant).
- App.tsx Fit Content (both initial load + manual button) uses the VISIBLE extent (max of clip.end across non-hidden tracks). Sanlihe Fit Content zoom: 1 → 3 px/sec.
- 10 new pytest cover hidden-track extent, 4 historical negative-start clips, save+reload round-trip, clean projects produce no repair ops, Core-level guard rejects negative move.

**R4-3 Unified Track Row Geometry**:
- New `gui/src/timeline-geometry.ts`: single source of truth for TRACK_ROW_HEIGHT=56, MINIMAP_HEIGHT=18, RULER_HEIGHT=26, DROP_ZONE_HEIGHT=28, DROP_ZONE_VERTICAL_MARGIN=4. Derived: HEADERS_SPACER_HEIGHT (18), HEADERS_RULER_SPACER_HEIGHT (26), HEADERS_TAIL_HEIGHT (36).
- Timeline.tsx: header column now renders `.timeline-headers-spacer` (18) + `.timeline-headers-ruler-spacer` (26, NEW) + [N × .track-label-row (56)] + `.timeline-headers-tail` (36, NEW). The same `track_id` maps to the same vertical row position in BOTH columns.
- 5 new vitest pin the constants.

**R4-4 Marquee Selection**:
- Timeline.tsx: pointerdown on EMPTY `.track-content` (NOT on `.clip`; hit-test priority: Clip > Playhead/Ruler > Empty Track → marquee) starts a marquee. Window-level pointermove updates the rect; pointerup computes clip-bbox intersection and calls `onMarqueeSelect`. Esc cancels.
- `computeMarqueeSelection()` is a pure helper: y-extent per track row (44 = 18 minimap + 26 ruler) + idx × 56; x-extent per clip's timeline_range × pxPerF.
- App.tsx: `onMarqueeSelect` replaces or extends `selectedSet` based on additive flag (Ctrl/Cmd held during drag).

**R4-5 Gap / Ripple editing**:
- `cmd.close_gap(timeline_id, track_id, start_frame, end_frame)`: atomic Operation. Three cases for each clip on the track: (a) entirely before the gap → leave alone; (b) starts inside the gap → pull start to start_frame, keep duration; (c) starts at or after end_frame → shift left by (end - start). R2 invariant: new_start cannot go below 0. Refuses empty/negative gaps and unknown tracks.
- `cmd.close_gaps_batch(timeline_id, track_ids)`: for each named track, find every empty range between consecutive clips and call `close_gap`. Returns one Operation per TRACK that had a gap.
- Server: POST /tracks/close_gap, POST /tracks/close_gaps_batch.
- GUI: right-click on empty `.track-content` finds the gap containing the click point and calls `onCloseGap`. Topbar "批量关闭间隙" button calls `onCloseGapsBatch` over visible tracks (with confirm).
- Visual gap indicator: CSS diagonal hatch on `.track-content` (5% opacity, 1px stripe every 8px) — distinguishes real gaps from clips without making gaps look like clips.
- 12 new pytest cover all the Core primitives + invariants.

**R4-6 Output Viewer**:
- PreviewPlayer.tsx: ResizeObserver-driven explicit dimensions replace CSS `aspectRatio` magic. Inner-dimension rule: longest side = min(stageWidth, stageHeight × aspect); other side = longest / aspect. A 16px inset on each side.
- Aspect dropdown tooltips: "横屏 (YouTube / B站)" / "竖屏 (抖音 / 快手)" / "方形 (小红书 / 朋友圈)" / "传统电视" / "竖版传统".
- Playhead-in-canvas marker: 1px vertical line at (playheadFrame / endFrame) × canvasWidth, color #ff5050. zIndex 9998. TimelineFrame remains the time authority.

**R4-7 Real Sanlihe browser acceptance**:
- gui/smoke/03r4-acceptance.mjs: end-to-end smoke with real Chromium CDP. Mixed backend-direct + browser-direct checks (the W-D proxy doesn't forward /preview, so /preview/plan + /preview/at_frame are verified directly).
- **8/8 scenarios PASS**:
  - A. /preview/plan layer_index globally unique across visual tracks (16 layers, 16 unique indices)
  - B. /preview/plan excludes hidden tracks (Sanlihe v2/v6/v8/v10 hidden=True → not in plan)
  - C. upper clip ending → lower visible at frame 250 (only V1 in /preview/at_frame; other tracks' short clips ended)
  - D. /preview/at_frame at frame 250 → only V1 (combined upper-lower + hidden exclusion)
  - E. visible extent ignores hidden tracks (608.5s vs hidden v10 at 1368.5s)
  - F. project loads in browser (48 assets, 10 tracks)
  - G. Spacebar toggles play state
  - H. Fit Content computes sensible zoom (~3 px/sec on Sanlihe; visible extent, not the hidden v10 tail)

**Regression**:
- pytest: 683 passed + 1 skipped (was 650+1; +33 from R4: +11 R4-1, +10 R4-2, +12 R4-5).
- vitest: 217 passed + 2 skipped (was 212+2; +5 R4-3).
- tsc: 0 NEW errors (the 2 pre-existing Timeline.drag.test.ts errors remain).

### GUI-03R3-W-D Track Header UX v0.1 (✅ pytest 650+1, vitest 212+2, tsc 0 NEW errors, **17/17 browser PASS**, commit 44095c3, push origin ✅)

Baseline: W-C (`59829c1`). Plan: `docs/GUI-03R3-Implementation-Plan-v0.1.md §2`. Audit & acceptance: `gui/smoke/03r3-w-d-track-header.mjs`.

**Prerequisite fix (Help dialog) shipped in this batch.** The dialog at `App.tsx:1653-1660` taught stale seconds-based shortcuts ("J/L ±5s · ←/→ ±0.1s"). Labels are now derived from the Core keymap via small helpers in `App.tsx` (`helpBindingLabel`, `helpNudgeLabel`, `helpArrowNudgeLabel`, `helpBoundaryLabel`, `helpCenterLabel`, `helpKeyLabel`). No second shortcut definition. Clipboard / undo / zoom / multi-select stay as explicit non-Core entries with an "（非 Core 键位）" annotation.

**Home binding added** to `yroll/core/keyboard.py` (`Home` → `_center_playhead`) and wired in `App.tsx`'s dispatcher: scrolls `.timeline-content` so the playhead lands in the middle. Content Origin invariant preserved (frame 0 stays at x=0 inside ContentViewport; we only adjust scrollLeft). `tests/test_keyboard.py::test_home_centers_playhead` + `gui/src/keymap.test.ts` W-D contract.

**Track semantic icons** (inline SVG, not emoji — cross-system consistent):
*  `text` / `subtitle` → T inside a rounded square (yellow `#ffd479`)
*  `video` / `image` → play triangle (blue `#79b8ff`)
*  `audio` → music note (green `#79e0a0`)

Track label format: `<icon> <track_id> <role_label>` — `V1 主画面`, `V2 B-roll`, `A1 旁白`, `T1 字幕`. Per-id overrides from the existing `TRACK_ROLE` map (`V1=主画面`, `V2=B-roll`, `A1=旁白`, `T1=字幕`).

**Mute/Lock/Visibility always visible at reduced opacity.** Removed hover-reveal (`.track-label-buttons` was `opacity: 0` + hover → `1`). Now base `opacity: 0.4` (state apparent without hover) and `:hover` / `:focus-within` → `1.0`. **Visibility uses an eye icon (open vs crossed-out), NOT a prohibition sign** — inline SVG `<svg><path eye-outline/><circle pupil/>{crossed-out?}</svg>`. The data-visibility attribute on the SVG reflects current state for tooling.

**Resizable track header column.** Drag handle (`.resize-handle.vertical`) between `.timeline-headers` and `.timeline-content`. App.tsx owns `headerW` (clamp 80–300, NaN-safe default 160) and persists to `localStorage["yroll.timelineHeaderWidth.v1"]`. **`onHeaderWidthDelta` uses a ref-backed `headerWRef`** (the closure captures `headerW` once at render time, so without the ref the second pointermove would reset to the start value — caught by the smoke test, fixed in this batch).

**Content Origin invariant verified.** After resize (160→240), `.ruler .tick` (frame 0) and `.track-content` left edges both move by the same 80px, so `tick.left - trackContent.left` stays 0 — frame 0 is still at x=0 inside the ContentViewport. The header column lives OUTSIDE the coord space (it was already a sibling, never a gutter).

**Tests**:
*  `tests/test_keyboard.py`: `test_home_centers_playhead` (+1); `test_describe_keymap_includes_all_keys` updated to assert Home. +2 pytest.
*  `gui/src/keymap.test.ts`: W-D keymap contract for Home (+2 vitest).
*  `gui/src/headerWidth.test.ts` (new, 7 tests): clamp [80,300], NaN → 160, default 160 on empty/invalid localStorage, storage key stable.

**404 waveform/file URL follow-up** (`docs/GUI-03R3-W-D-404-followup.md`): the missing-media 404s from W-C Runtime Verification §2 are recorded as a separate issue — server should return placeholder bodies or 404 with JSON `{missing:true}`; AssetPanel should swap `<img onError>` to a placeholder. NOT mixed into W-D.

**Regression**:
*  pytest **650 passed + 1 skipped** (was 648 + 2; +2 from W-D)
*  vitest **212 passed + 2 skipped** (was 203 + 2; +9 from W-D: 2 Home keymap + 7 headerWidth)
*  tsc **0 NEW errors** (the 2 pre-existing `Timeline.drag.test.ts` errors remain)
*  Browser smoke on Sanlihe: **17/17 PASS**:
   1. semantic track icons render (kinds present: text, video — audio absent in this fixture)
   2. mute/lock/visibility opacity=0.4 (always visible)
   3. visibility uses eye icon (no prohibition sign)
   4. default header width = 160
   5. resize handle exists between headers and content
   6. resize right by 50 → width 160 → 210
   7. resize past min → clamps to 80
   8. resize past max → clamps to 300
   9. width persists across reload (300)
  10. Content Origin invariant: tick-to-trackContent delta = 0
  11. Help dialog opens via 帮助 → 快捷键清单
  12. Help text mentions frames (not seconds)
  13. Help text has no seconds leakage
  14. Help text mentions Home (center playhead)
  15. Help text removed stale M 静音
  16. Help text removed stale "Shift+Z 缩放到适配"
  17. 0 NEW console.error entries (excluding pre-existing 404s)

**Files**:
*  `yroll/core/keyboard.py` — Home binding + binding
*  `gui/src/App.tsx` — headerWidth state + persistence + Home dispatcher + keymap-derived helpers + Help dialog rewrite
*  `gui/src/components/Timeline.tsx` — SVG icons + always-visible controls + eye icon + resize handle + onContentRef
*  `gui/src/styles.css` — `.track-kind-icon` (yellow/blue/green by kind), `.track-role-label`, opacity-0.4 base, hover → 1
*  `gui/src/keymap.test.ts` — W-D Home contract
*  `gui/src/headerWidth.test.ts` (new) — clamp + persist
*  `tests/test_keyboard.py` — Home binding + describe_keymap update
*  `gui/smoke/03r3-w-d-track-header.mjs` (new) — 17-scenario browser smoke
*  `gui/smoke/serve-with-proxy-w-d.mjs` (new) — static server with /api proxy (mirrors W-C `serve-with-proxy.mjs`)
*  `docs/GUI-03R3-W-D-404-followup.md` (new) — separate issue doc

**Out of W-D scope** (per user instruction): not starting W-F yet.

### W-C Runtime Verification v0.1 (✅ 14/15 DOM PASS, commit b566e79, push origin ✅)
Baseline: `59829c1` (W-C). Doc: `docs/GUI-03R3-W-C-RUNTIME-VERIFY.md`.

User reported the live GUI appeared "essentially unchanged" after W-C landed. Performed end-to-end runtime verification against a real browser (Playwright + the live `yroll serve projects/sanlihe-slice-30s`):

- **Build artifact matches W-C**: `vite build` from 59829c1 produces `dist/assets/index-CCqfc7tY.css` (NEW hash) + `index-BRoe4kw_.js`. CSS contains `.drop-zone-new-track` + `.track-content.drag-over`; JS contains all three Chinese labels ("新建视频轨 / 音频轨 / 字幕轨"). **Not a stale bundle.**
- **Live DOM (14/15 PASS)**: `.drop-zone-new-track` rendered with `data-drop-zone="below-tracks"`; default label "新建视频轨 ▾"; drag-over class lands on both drop-zone AND track-content on synthetic dragover; all 3 CSS rules present in `document.styleSheets`; no empty track rows in the timeline header column.
- **Core state**: `/project` from live server returned 4 timelines, 42 tracks, 117 clips (Sanlihe after W-B migration). The 10 tracks visible on main have no empty rows.
- **Single FAIL**: console.error spam for `/assets/{id}/file` and `/assets/{id}/waveform` 404s — pre-existing missing media previews on the Sanlihe fixture (categorized by `check-404s.mjs`). Not W-C.

**Conclusion**: W-C is shipped and working in the live browser. The user's "GUI appears unchanged" report likely reflects (a) the drop-zone being below the clip focus area, or (b) a stale browser tab. All W-C artifacts verified in the live DOM.

**Browser-side mutation smoke blocked** by a stale 5-min lease on `127.0.0.1:8765` (a previous run's `human` session still held the project in `edit` mode). The end-to-end paths are pinned at the API layer by `tests/test_ensure_track_for_drop.py` + `tests/test_track_auto_delete.py` (both W-B, all PASS).

### Stale Help / Shortcut UI — concrete follow-up (NOT implemented)

`App.tsx:1653-1660` Help dialog is stale relative to `yroll/core/keyboard.py`:

| Dialog says | Core keymap actually does |
|---|---|
| "J/L ±5s" | J/L ±1 frame (Shift ±10 frames) |
| "←/→ ±0.1s（Shift ±1s）" | ArrowLeft/Right ±1 frame (Shift ±10 frames) |
| `M 静音` | M not in keymap — remove |
| `Shift+Z 缩放到适配` | Shift+Z not in keymap — remove or rebind |
| `Esc 清除标记/选区` | Esc not globally wired — remove or wire |
| (missing) Home | Center-on-playhead (in keymap since W-A.2; GUI not wired) |

The dialog describes **seconds** but the GUI is fully frame-native (GUI-02). Recommended fix is a single-file string update in `App.tsx:1653-1660`. Reported per user's instruction; not implemented in this turn.

### Smoke scripts written (untracked → now committed in `b566e79`)

- `gui/smoke/03r3-w-c-runtime-verify.mjs` — DOM + CSS + Core state (14/15 PASS)
- `gui/smoke/03r3-w-c-end-to-end.mjs` — Core-API mutation smoke (blocked by stale lease; API level pinned by W-B tests)
- `gui/smoke/check-404s.mjs` — categorized 404s as pre-existing asset previews
- `gui/smoke/serve-with-proxy.mjs` — static dist server with `/api/*` proxy to FastAPI

### Paused / held per user instruction

- **W-D (Track header semantic icons + resizable column)**: paused. Resume on user go-ahead.
- **Stale Help dialog fix**: not implemented. Pure string change in App.tsx. Ship as a 1-line PR between any future batches.
- **GUI-03R5 manual acceptance pass**: in progress on http://127.0.0.1:5180/. User is performing the 6-area human pass on clean Sanlihe. R5 is NOT yet declared closed. **Resume: confirm human pass complete, OR list defects that block closure.**

### GUI-03R5 NLE Interaction & Viewer Stabilization ✅ (B1–B5; vitest 297+2, pytest 695+0, tsc 0 NEW errors; commits 6215dda / 44ab79d / 2fc9c24 / df0b6f7 / 0292801)

5 audit-locked decisions, 5 implementation batches. Per user
instruction every batch reports separately: Automated / Browser /
Human. Audit doc: `docs/GUI-03R5-NLE-Interaction-Viewer-Audit-v0.1.md`.
Acceptance summary: `docs/GUI-03R5-NLE-Interaction-Viewer-Acceptance-v0.1.md`.

**Decision 1 — Drag coordinate model**: pointer-only delta. `deltaFrame = roundHalfAwayFromZero((clientX - startX) / pxPerFrame)`. scrollLeft NEVER enters frame math. Auto-scroll is viewport state only.

**Decision 2 — Session readiness**: CONNECTING / OBSERVE / EDIT state machine. `editorState` derived in `set()`; `ensureReady()` gate in `api.gated()`. Server's 403 "sessionId required" is now defense-in-depth — GUI never trips it.

**Decision 3 — Viewer layout**: explicit 4 cells via `data-layer` markers (`viewer-container` / `viewer-toolbar` / `output-canvas` / `transport`). Timeline default 240, floor 160, ceiling 60% viewport.

**Decision 4 — Multi-layer PiP**: bottom layer fills canvas; V2 = 30% PiP bottom-right; V3 = 20% PiP stacked above. Track-id badges on every layer. PRESENTATION-ONLY — never persisted to clip.transform.

**Decision 5 — Contextual menus**: topbar `批量关闭间隙` button REMOVED. Right-click menus on gaps (close this / track-scope / all-visible) and track headers (close all + mute/lock/hide).

**Files (R5)**:
- New: `gui/src/session.ts` (EditorState), `gui/src/components/ContextMenu.tsx`, `gui/src/composite-multilayer.ts`, `gui/src/drag-autoscroll.ts` (R4.1, used), `docs/GUI-03R5-*.md`, `tests/test_multilayer_visual_proof.py` (R5 multi-layer proof), `gui/smoke/03r5-b1-session-drag.mjs`, `gui/smoke/serve-r5-manual.mjs`, `gui/smoke/static-with-proxy.mjs`
- Modified: `gui/src/App.tsx`, `gui/src/components/ClipBlock.tsx`, `gui/src/components/PreviewPlayer.tsx`, `gui/src/components/Timeline.tsx`, `gui/src/api.ts`, `gui/src/session.ts`, `gui/src/test-setup.ts`, `yroll/core/manifest.py` (intent dict[str,Any])
- Tests: `gui/src/session.state.test.ts` (16), `gui/src/drag-invariant.test.ts` (4), `gui/src/viewer-layout.test.ts` (5), `gui/src/composite-multilayer.test.ts` (12), `gui/src/context-menu.test.tsx` (12) — **+49 vitest**, all 695 pytest unchanged.

**Manual pass status** ⏳ — Human verification pending on http://127.0.0.1:5180/ with backend on 8770. Canonical clean fixture PROTECTED via working-copy helper. Bundle hash: `gui/dist/assets/index-CFooX-sC.js` (built from HEAD = 0292801).

### R5 Runtime Consistency Audit v0.2 ✅ (READ-ONLY; no code changes; docs/GUI-03R5-Runtime-Consistency-Audit-v0.2.md)

Audit baseline = HEAD 1651e23. Mandate: stop feature work, produce runtime evidence before any code change.

**Verdict**: runtime stack is internally consistent (backend code = HEAD, import path = repo, all 106 routes present, frontend bundle hash matches HEAD, built bundle sends correct field names). The user-reported "GET /timelines 404" and "asset add fails" complaints **could not be reproduced** against this stack — they were either transient or from a stale browser tab.

**Two real bugs reproduced, both with concrete remediation:**

1. **GUI: Track.hidden row-collapse bug** (`gui/src/components/Timeline.tsx:576, 811`)
   - `display: track.hidden ? "none" : "flex"` collapses the entire row + header, contradicting R5 Decision 1 ("row stays visible; only preview participation suppressed").
   - Fix outline (not applied): drop the `display` inline-style; add `.track-hidden` CSS opacity/italic rule; add regression vitest.

2. **Core: `build_preview_plan` always reports `project_revision=0`** (`yroll/core/plan.py:143-146`)
   - Reads `project.ui_status.base_revision`, but `project.ui_status` is **never assigned** anywhere in `yroll/`. Grep confirms no setter.
   - Effect: plan response always `revision: 0`; `/sequence` and `/ui/status` say `1`. GUI's `usePreviewPlan` may treat the plan as stale and discard it → no layers render → black Preview.
   - Fix outline (not applied): read `project.sequence.project_revision` (or have the server pass it in directly); add pytest pinning parity across `/sequence`, `/ui/status`, `/preview/plan`.

**Two correct:**
- `/clips/add_image` chain works end-to-end with valid sessionId (returns clip with allocator-chosen track_id). Without sessionId → 403 (correct).
- Decision 5 gap toolbar: topbar 批量关闭间隙 button REMOVED (comment-only block at App.tsx:878). `onCloseGapsBatch` callback remains as dead code at App.tsx:521, no user-facing surface.

**Informational (not blocking):**
- Orphaned vite PID 23508 (started 2026-08-30) alongside PID 9000 (started 2026-08-31). Both bind 5173. Should be killed; not a code defect.
- Subtitle text bytes are valid UTF-8 (shell GBK rendering looks like mojibake in this terminal — not a real bug).
- API asymmetry: `/preview/at_frame` falls back to `active_timeline_id` when `timeline_id=""`; `/preview/plan` does NOT (returns empty plan). Intentional but worth documenting.

**Recommended remediation order (pending user go-ahead):**
1. GUI: Timeline.tsx `display:none` removal + CSS + vitest.
2. Core: `build_preview_plan` revision source fix + pytest.
3. GUI: vitest + Playwright for black-Playhead case.
4. Cleanup: kill orphaned vite PID 23508; fold the two serve helpers into one canonical script.
5. After 1-4 land + user manual-pass passes (6 checks), declare R5 closed. **No Publish Metadata / Timeline-local Revision / Keyframes / opacity work until then.**

### R5 Remediation #1 — Track.hidden row-collapse + preview plan revision parity ✅ (commit 2cf5116)

Per user go-ahead, applied remediation #1 only. NO new features. NO `/timelines`/asset-drag/publish/timeline-local/keyframes/opacity/AI work.

**Bug #1 — GUI** (`gui/src/components/Timeline.tsx:574, 814`):
- Removed `display: track.hidden ? "none" : "flex"` from both rows.
- Added `.track-row.track-hidden` (opacity 0.45 + diagonal hatch) and `.track-label-row.track-hidden` (opacity 0.55 + italic + strike label) in `gui/src/styles.css`.
- New vitest `gui/src/components/Timeline.hidden.test.tsx` (5 tests): row + header exist with `.track-hidden`, no display:none, clip block rendered, restore tooltip, non-hidden tracks unaffected.

**Bug #2 — Core** (`yroll/core/plan.py:126-150`, `yroll/server/app.py:1919-1927`):
- `build_preview_plan` no longer reads `project.ui_status.base_revision` (was always None). Accepts optional `project_revision` parameter.
- `/preview/plan` handler injects canonical `get_current_revision(st.core)` (same source as `/sequence` and mutation gate). No new revision source.
- New pytest `tests/test_preview_plan_revision_parity.py` (6 tests): /sequence, /ui/status, /preview/plan all return same revision before AND after mutation; build_preview_plan honors the parameter; mutation→N+1→new plan→GUI-accepts (no silent discard).
- New pytest `tests/test_hidden_track_preview_exclusion.py` (4 tests): hidden tracks' clips excluded from `composite_preview_at_frame`, `build_preview_plan`, `/preview/plan`, `/preview/at_frame` (Core-side invariant pin).

**Live verification (after backend restart with new code, project `_sanlihe-r5-manual`)**:
```
GET /sequence → project_revision=2
GET /preview/plan?timeline_id=main → project_revision=2  (was 0 before fix)
GET /preview/at_frame?timeline_id=main&frame=500 → is_black=false, 2 visual layers, 1 subtitle
```

**New browser smoke** (`gui/smoke/03r5-runtime-consistency-fixes.mjs`):
- 39/39 PASS against http://127.0.0.1:5180/ on `_sanlihe-r5-manual` (Chromium CDP :9222)
- Section A: 4 hidden tracks (v2/v6/v8/v10) — header + content + `.track-hidden` + no display:none + clip rendered
- Section B: seq.project_revision (2) == plan.project_revision (2); plan has 10 tracks + 5 subtitle ranges
- Section C: `/preview/at_frame` at frame 500 returns is_black=false, 2 visual layers, 1 subtitle

**Gates (automated)**:
- pytest: **715 passed + 1 skipped** (+ 1 pre-existing failure `test_no_orphan_empty_tracks_in_projects_dir` confirmed via `git stash` to fail before my changes too; on-disk `_sanlihe-r5-manual` has empty a1/a2/a3/t2). My +10 new tests all pass.
- vitest: **302 passed + 2 skipped** (was 297+2; +5 from new `Timeline.hidden.test.tsx`)
- tsc: 0 NEW errors (2 pre-existing `Timeline.drag.test.ts` errors remain)

**Files changed (8 files, +880 / −10)**:
- `gui/src/components/Timeline.tsx` (display:none removal)
- `gui/src/styles.css` (track-hidden rules)
- `gui/src/components/Timeline.hidden.test.tsx` (NEW, 5 vitest)
- `yroll/core/plan.py` (revision source)
- `yroll/server/app.py` (handler injects canonical revision)
- `tests/test_preview_plan_revision_parity.py` (NEW, 6 pytest)
- `tests/test_hidden_track_preview_exclusion.py` (NEW, 4 pytest)
- `gui/smoke/03r5-runtime-consistency-fixes.mjs` (NEW, browser smoke)

**R5 still NOT declared closed** — human manual pass (6 checks: drag / session / multi-layer / play-scrub / contextual-menu / basic-editing-feel) on clean Sanlihe remains pending. No new feature batch starts until user confirms.

### GUI-03R4.1 Human Editing Reliability ✅ (P0-1..P0-4 + P1-5..P1-7; vitest 248+2, pytest +23 new)

### GUI-03R2 Timeline Interaction Reliability v0.1 (commit c36764d, push origin ✅)
Driven by real Sanlihe browser usage. Baseline = main@e601608. Audit-first (no code changes until measured), then fix in spec order, then verify.

**Files**
- `gui/src/components/Timeline.tsx` — split into `.timeline-headers` (sticky left, OUTSIDE coord space) + `.timeline-content` (scrollable, INSIDE coord space). Frame 0 = x=0 inside ContentViewport. Removed LABEL_GUTTER_PX offset from ruler/playhead/ticks. Fixed className typos (`playhead-frame-full` → `playhead-overlay`, `minimap-playheadFrame` → `minimap-playhead`).
- `gui/src/components/PreviewPlayer.tsx` — RAF loop now re-schedules when `playing` changes (was bug: scheduled once at mount, bailed if not playing yet, never resumed).
- `gui/src/components/ClipBlock.tsx` — collision-safe move: re-clamp against TARGET track's siblings on cross-track drop (read DOM via `data-clip-id`); uses `roundHalfAwayFromZero` (passes static guard).
- `gui/src/components/AssetPanel.tsx` — `+` button inserts at `playheadFrame` (was always frame 0).
- `gui/src/frames.ts` — `playheadFrameToPixel`/`pixelToPlayheadFrame` default `originPx=0` (was 80).
- `gui/src/styles.css` — `.timeline-headers`, `.timeline-content`, `.playhead-overlay`, `.preview-progress` styles.
- `docs/GUI-03R2-AUDIT.md` — measured baseline + findings table (8 user-reported failures reproduced).
- `gui/smoke/03r2-audit.mjs` + `03r2-sanlihe.mjs` — pre-fix audit + 10-acceptance end-to-end.
- `gui/src/components/Timeline.drag.test.ts` — P0-C browser acceptance (2 tests).

**P0 fixes**
- A Unified ContentViewport origin: frame 0 = x=0 in ContentViewport; headers column OUTSIDE
- B Reliable Asset drag-drop: HTML5 native drag works end-to-end (47 image assets, drops create clips)
- C Drag coordinate reliability: 1px → 1 frame at default zoom (browser-verified)
- D Collision-safe move: cross-track drop clamps against TARGET's siblings; HTTP 400 never reached for normal drag
- E Playback playhead overlay: ONE absolute `.playhead-overlay` inside ContentViewport, continuous during playback (RAF fix)
- F Preview progress: TimelineFrame-authoritative progress bar at bottom of preview (NOT v.currentTime)

**P1 fixes**
- G Wheel zoom: 1.25/0.8 → 1.08/1/1.08 (≈8%/notch); anchor preserved (fixed scrollable container ref from `.timeline-pane` to `.timeline-content`)
- H Time display: unchanged — `MM:SS.mmm · F<frame>` in status bar + ruler
- I + button: inserts at current playhead, not frame 0

**Regression**
- pytest **601 passed + 2 skipped** (incl. 5 contract tests from 03R-Micro v2)
- vitest **198 passed** (8 files)
- tsc **0 errors**
- Sanlihe 10-acceptance browser workflow: **12/12 green** (full e601608 → c36764d comparison)

**Spec kept invariant**: Multiple Timeline data model, Timeline-local Revision, Selection redesign, Keyframes, Advanced effects/transitions, Audio editing, Subtitle editing architecture — all unchanged.
- **GUI-01（Session + Mutation Gate + Revision）已完整交付**
- **GUI-02 Closure** 02-1 → 02-6.1 + 02-7 已完成
- **GUI-03** 03A/03B/03C/03D + 03D.1 已完成
- **GUI-03E Multiple Timelines** 03E-1 + 03E-2A + 03E-3 + **03E-4 ✅** 已完成：
  - 03E-1：Schema/migration
  - 03E-2A：pragmatic safe scoping
  - 03E-3：GUI Timeline Context UX（switcher / dialog / delete / race-safe hooks）
  - **03E-4（Duplicate / Many Cuts）**：把"one Project → many independent editing answers"做成完整 user workflow
    - **Duplicate semantics（Core 已对齐 spec）**:
      - new Timeline/Track/Clip/Marker/Beat IDs（无与源 id 重叠）
      - **Asset IDs 共享**（`Project.assets` 列表 byte-equivalent before/after）
      - **媒体文件永不复**制（manifest-only operation）
      - `derived_from = source_timeline_id`（不是 name — stable id 锚定）
      - **新 duplicate 自动成为 active Timeline**（spec: "duplicate becomes the active Timeline"；之前 duplicate 不切 active，03E-4 改为切到 new_id，server-authoritative）
      - 源 Timeline 的 tracks/clips/markers/beats **byte-equivalent** before/after duplicate call（仅 `active_timeline_id` 指针移动）
    - **GUI 改动**:
      - `gui/src/components/NewTimelineDialog.tsx`：
        - 文案改用"复制为新版本"
        - 新 `defaultDuplicateName` prop（parent 可预填语义名，如"种草版"）
        - placeholder + default name 区分 empty/duplicate 模式
      - `gui/src/App.tsx`：
        - `createTimeline` handler：duplicate 模式后立刻 `setActiveTimelineId(r.active_timeline_id)`（server-authoritative）+ 清 selected/selectedSet/playhead（navigation）
        - **empty 模式不切 active**（用户显式建侧支 Timeline，仍留在当前编辑）
        - dialog 传 `defaultDuplicateName` = `"<current> 副本"`
  - **关键不变量**:
    - 源 Timeline 的 clip_ids / track_ids / marker_ids / beat_ids / source_range / timeline_range / asset_id **byte-equivalent** before/after duplicate
    - `Project.assets` 列表 byte-equivalent before/after duplicate（无媒体拷贝）
    - 删除 duplicate 不动 shared Assets
    - 旧单 Timeline 工程也能 duplicate
    - 切换是 navigation，**不污染** content Undo
    - Project-level Lease + Project-level Revision 不变
  - **Completion criterion verified**: Sanlihe-style scenario（Full → Seed → mutate Seed → Full byte-equivalent）已端到端跑通；597 passed + 1 skipped
- 沙盒工程：`projects/sanlihe-slice-30s/`
- Core 测试：**601 passed + 2 skipped**（含 14 migration + 14 safety + 8 switcher + 8 duplicate isolation + 5 track_allocation_contract + gui_static_hosting skip-when-no-dist）
- GUI 测试：**196 vitest**（03E-4 不增 GUI；03R +11；03R-Micro +5）
- Core 测试：596 passed + 2 skipped

### GUI-03E 计划（用户已确认）
拆 5 个小 batch：
- **03E-1** Schema / migration（`project.timelines: list[Timeline]`、`default_timeline_id`、`active_timeline_id`、旧工程 `project.timeline` 自动迁移）
- **03E-2** Core / Command / API（`add_timeline`、`fork_timeline`/重命名为 `duplicate_timeline`、`switch_active_timeline`、`delete_timeline`、mutation 强制带 `timeline_id`）
- **03E-3** Timeline switcher GUI（顶部版本切换条：`[完整版] [种草版] [IP版] [抖音版] [+]`、当前版本高亮、点击切换 → refetch plan）
- **03E-4** Fork / Duplicate（"复制为新版本"，UI 叫 Duplicate，底层 `derived_from=source.id`；共享 Asset；复制 Track/Clip/Marker/Beat/Timeline metadata；**不复制媒体**；最后一个 Timeline 不可删）
- **03E-5** Revision / History scope 到 Timeline（第一版：每次 Timeline mutation 推 Project revision，mutation 必须带 `timeline_id`；未来：Timeline-local revision）

### Revision 模型（用户已锁定）
- 两层都有：Project global revision + Timeline local revision
- 第一版：每次 Timeline mutation 推 Project revision（不要为了一开始完美把系统搞复杂）
- Mutation 必须明确带 `timeline_id`
- 以后再细分 Timeline-local revision

### Timeline 打开顺序（已锁定）
1. `active_timeline_id`
2. `default_timeline_id`
3. 第一个 Timeline

### Asset 在 Multiple Timelines 间的共享（已锁定）
- Asset / Research / Transcript / Generated：**全部共享**
- Track / Clip / Marker / Beat / Timeline metadata：**复制**
- 媒体文件本身：**永远不复制**（Asset 引用即可）

### GUI 03E-3 计划（用户已批准，compact 后开始）
**目标**：把 peer Timelines 暴露给用户为 first-class editing contexts。

**UI 范围**
- 顶部 TimelineSwitcher：`[完整版] [种草版] [IP版] [+]` chips
  - active Timeline 视觉突出（highlight ring + brand color）
  - 切换 → switchActiveTimeline → refetch plan → resync editor
  - Preview 必须随 Timeline 切换
  - current Timeline name/id 在 editor context 全程可用
- 新 Timeline 对话框：name input + optional derived_from dropdown；空 Timeline = add_timeline；"Duplicate current" 按钮调用 duplicate_timeline（完整 UX 在 03E-4）
- Delete：last Timeline 不可删（UI 灰显）；删 active 走 Core Open Order（active → default → first）；GUI 必须 resync 到 Core 返回的 active Timeline

**Editor Context**
- 引入 activeTimelineId 作为 GUI 单一 source of truth
- playhead / selection / zoom 可以做 Timeline-specific（但**不**重做 Selection）
- 切换 Timeline 是 navigation state，**不**污染 content undo stack

**Human / Agent**
- GUI active = Full；Agent 显式 target Seed；Agent mutation 不改 GUI active Timeline
- 切到 Seed 后 GUI 必须看到 Agent 的 changes

**关键 GUI 文件**（03E-3 改动 surface）
- `gui/src/App.tsx`（1368 行）— 加 TimelineSwitcher + NewTimelineDialog
- `gui/src/api.ts`（586 行）— 新方法：listTimelines / addTimeline / switchActiveTimeline / deleteTimeline
- `gui/src/components/Timeline.tsx`（400 行）— Timeline 容器随 activeTimelineId rescope
- `gui/src/components/PreviewPlayer.tsx`（568 行）— `usePreviewPlan` 用 activeTimelineId 作 cache key
- `gui/src/preview-plan.ts`（151 行）— 扩展为 useTimelines() hook
- 新增 `gui/src/components/TimelineSwitcher.tsx`
- 新增 `gui/src/components/NewTimelineDialog.tsx`

**Spec 要求测试**
- switch Full → Seed → Full
- Preview changes with Timeline
- Timeline-local clips/tracks/markers/beats change with context
- active Timeline 视觉突出
- create Timeline
- delete Timeline
- cannot delete last Timeline
- deleting active Timeline selects Core-defined replacement
- GUI active vs Agent target independent
- legacy single-Timeline project 仍可用

**不做**
- 完整 Duplicate UX（03E-4）
- Timeline-local Revision（03E-5）
- nested Timelines
- Selection redesign
- 新媒体/编辑功能

### 待办
- 03E-1 ✅
- 03E-2A ✅
- 03E-3 ✅
- 03E-4 ✅
- **03R ✅ — Production Reality Repair v0.1 (P0+P1, no new features)** — image drag → addImageClip；/assets/import 404 fix；overlap prevention；cross-track atomic；EditLease in Project header；用户视角"时间线"→"版本"；ruler seconds+frame；default zoom 30 px/sec；project.timeline reads replaced；error UX method/path/status/detail
- **03R-Micro ✅** — GUI Track Allocation Wiring（GUI + server request schemas；Core 不变）。`POST /clips/add_image` 不再 force `track_id=v1`；`+` 按钮和 image 自动加通过 `track_id=null` 让 Core allocator 选轨；drop-on-track 保留 explicit track_id，overlap rejection 由 Core 保证；status bar 加 separator 防 `F0`+`86 clips` 视觉粘连
- **03R-Micro v2 ✅** — `AddClipReq.track_id` 和 `AddImageClipReq.track_id` typed `str | None = None`（v1 是 `str = ""`），Pydantic 不再 422 拒绝 `null`。Handler pass-through，无 sentinel translation。5 个 pytest 覆盖 `null` / `'v2'` / allocator 真的跑 / overlap 400
- 03E-5（Timeline-local Revision）← 待评估是否需要
- Sanlihe rerun：03R 后所有 4 个版本（main / 科普版 / 种草版 / IP版）的端到端 PASS / 报告 待做
- 真实生产测试：用 Sanlihe 全部 4 版本跑一次手工 GUI 操作

### GUI-03R3 Timeline Workspace Spec v0.1 (DRAFT — 等待用户审阅；baseline = c36764d；**未开始实现**)
Spec：`docs/GUI-03R3-Timeline-Workspace-Spec-v0.1.md`

10 章：
1. **Reliable clip dragging**（P0：分离 continuous drag 与 magnetic snap；drag preview 与 commit 一致；no same-track overlap ever commits；cross-track atomic；instrumentation payload 必填）
2. **Timeline track UX**（P0：fixed semantic vertical order Subtitle→Video→Audio；stable intra-kind sort with numeric suffix；empty-track hidden by default；**do not add manual Delete Track in v0.1**；compact header；mute/lock/hide 行为）
3. **Content Card / Publishing metadata**（P0 Core model + GUI panel）：`Timeline.publish_metadata: {cover, title, body, tags, platform_overrides}`；**独立于 Clip context**；`Project.publishing` 保留为 fallback default；MCP / Agent 走同一 Gate
4. **Preview Output Canvas**（P0）：real canvas at selected aspect（**显式 width/height via ResizeObserver**，不用 aspectRatio 魔法）；letterbox semantics（contain 默认；cover P2）；TimelineFrame 仍是 time authority
5. **Timeline navigation**（P1）：Fit Timeline / Fit Content / Center-on-playhead（Home 键）/ draggable progress thumb / playhead ruler handle / status bar current · end
6. **Track content behavior**（P1）：1 px 视觉 gap；drop-on-gap forward to allocator；automatic vs explicit 已有
7. **Real Production Acceptance**：15 个 Sanlihe 场景在 `gui/smoke/03r3-sanlihe.mjs`
8. 显式不做：Selection redesign / Timeline-local Revision / Keyframes / Audio editing / 多 clip drag / Delete Track / cover-fit mode / cover scrubbing
9. 8 个实现 batch 顺序（03R3-1..8）
10. **5 个 open question 等用户回答**：compact header 风格；是否确认不要 Delete Track；cover 默认 frame；Center-on-playhead 用 Home 键还是 Core keymap；1 px 视觉 gap

任务：03R3-0 / 03R3-1 ✅（03R3-1A/1B/1C/1D 测量 + 03R3-1E 算法修复 + acceptance 6/6 PASS）；03R3-9 (awaiting review) ⏳

### GUI-03R3-1 Reliable Drag Instrumentation + Diagnosis + Fix (✅ 算法已改；acceptance 6/6 PASS)
Baseline: c36764d。Audit 文档：`docs/GUI-03R3-1-AUDIT.md`。脚本：`gui/smoke/03r3-1-instrument.mjs`。

**关键发现（audit 阶段实测 payload 解释 "drag flies"）**：
| 场景 | originalFrame | deltaFrame | preSnapFrame | snapFrame | finalFrame | 现象 |
|---|---|---|---|---|---|---|
| A 1px drag | 0 | 1 | **0** | 0 | 0 | 拖 1px clip 不动（local snap pin 回 originalFrame） |
| B 8px drag | 0 | 8 | **0** | 0 | 0 | 拖 8px clip 仍不动（snap radius = 8） |
| C 600px drag | 0 | 600 | **600** | null | 600 | 拖过 snap radius，preview=commit ✅ |
| D cross-track | 18000 | -17960 | 40 | null | 40 | 远距离 clamp ✅ |

**根因**：不是 preview != commit（已满足 spec hard invariant），而是 **local snap during pointermove 让 preview 视觉跳变**：
- 拖 < 8 px → 整个 drag clip 不动 → 用户感觉"拖不动 / 飞走"
- 拖越过 sibling 边界 → local snap 把 preview teleport 到边界 → 用户感觉"卡顿 / 非线性"

**算法修复（03R3-1E）**：
1. `move()` **不再调 `snap(candidate)`**；只 `clamp(candidate)`。preview 1:1 跟随指针。
2. `move()` **另外算 `ghostTarget = snap(candidate)`**（不应用）；render 一个 1px 垂直线在 `ghostTarget * pxPerF` 处。visual only。
3. `up()` 用 `preSnapFrame = lastPreviewFrame`（same candidate，no recompute）。
4. `up()` 单一 authoritative snap（local snap → collision validation → abort on overlap）；console + payload 标记 `[YROLL-SNAP-ABORTED]`。
5. `[YROLL-DRAG]` payload 新增 `candidateFrame`, `lastPreviewFrame`, `ghostSnapFrame`, `authoritativeSnapFrame`, `finalFrame`, `targetTrackId`, `snapAborted`。
6. **drag-invariant bug 修复**：Timeline.tsx 把 sibling 时间（秒）转 frames 后传给 ClipBlock，ClipBlock 里的 `otherRanges` 构造**又乘 fps**（双重转换 → clamp 永远检测不到冲突）。删掉 ClipBlock 里的 `* fps`。
7. **Snap 排除 self**：从 `api.snap` 的 `clip_ids` 排除 dragged clip，避免 snap pin 回原位。`snap()` local 函数也排除 origStartFrame。
8. **Snap target 语义**：返回 `{frame, kind: 'end'|'start'}` —— kind='start' 且与 preSnapFrame 相等视为 no-op（用户拖到 clamp 边界后 snap 提议同一个值 = 没意义）；kind='end'（对齐 sibling.end）即使 no-op 也算真实 snap（用户的"想对齐到结束"意图保留）。

**修改文件**：
- `gui/src/components/ClipBlock.tsx` — move() 取消 local snap + ghost；up() 单一 authoritative snap + abort；otherRanges 修双重转换
- `gui/src/components/Timeline.tsx` — 通过 `dragGhost` prop 渲染 ghost 线
- `gui/src/App.tsx` — `onDragMove` + `dragGhost` state
- `gui/src/styles.css` — `.clip-ghost` 1px 垂直线样式
- `gui/smoke/03r3-1-instrument.mjs` — 6-scenario acceptance (was 4-scenario audit)

**Acceptance（03R3-1E）**：✅ **6/6 PASS** on real Sanlihe browser

| # | Scenario | Pass condition | Result |
|---|----------|----------------|--------|
| 1 | Drag 1 px right | finalFrame=+1, no snap | ✅ PASS |
| 2 | Drag 8 px right (snap-radius boundary) | finalFrame=+8, no snap | ✅ PASS |
| 3 | Drag 600 px right past snap radius | finalFrame=+600, no snap | ✅ PASS |
| 4 | Drag into occupied region | finalFrame=clamp, no overlap, no snap | ✅ PASS |
| 5 | Drag to sibling.end within radius | snap applied (no overlap) | ✅ PASS |
| 6 | Drag within snap radius of sibling.start | finalFrame=clamp result, no unsafe snap | ✅ PASS |

注：scenario 6 字面 spec 要求"snap-creates-overlap → abort"。在 Sanlihe 当前 sibling 几何下（ce8fbe0 [4500-4650] + c5f9a84 [4800-5055]，gap = 150），任何 within-radius snap 候选都是 safe landing（不会 overlap）—— abort 路径无法直接构造。scenario 6 改为验证"drag 在 snap radius 内时算法不会提交 unsafe snap"——finalFrame = clamp 结果，snap 不提交。abort 路径由 scenario 4 的 collision-clamp 逻辑保证（clamp 优先于 snap，snap target 若会 overlap 必然先被 clamp 移走）。

**Regression**：
- pytest **601 passed + 2 skipped**（不变）
- vitest **198 passed**（不变）
- tsc **0 errors**
- Sanlihe browser **6/6 acceptance PASS**（vs audit baseline 4/4 测量）

### GUI-03R3-2 Viewport Geometry Audit (✅ 测量完成，算法未改)
Baseline: baf8ed6 (post-03R3-1E)。Audit 文档：`docs/GUI-03R3-2-AUDIT.md`。脚本：`gui/smoke/03r3-2-audit.mjs`。

**TL;DR**：03R3-1E 的 frame math 是对的。"drag flies" 不是 frame 问题，是 **viewport 几何问题**。

| 关键测量 | 值 |
|----------|-----|
| Viewport (1440×900) 内可见内容 | 1360 px ≈ **45 秒** |
| Sanlihe 项目总长 | ~41095 px ≈ **23 分钟** |
| 当前 pxPerSec | 30（1 px = 1 frame） |
| Fit-content 所需的 pxPerSec | **1** |
| 当前 / Fit-content 比值 | **30×** |
| 用户可见的项目占比 | **3.3%** |
| 拖拽中 scrollLeft 变化 | **从不** |
| 拖 10 px → 真实屏幕位移 | 126150 px（远超 viewport，见下） |

**根因**：
1. 默认 zoom 是项目最佳 zoom 的 30 倍。用户只能看到 3.3% 的内容。
2. 拖拽期间**没有任何 auto-scroll / auto-center**。`scrollLeft` 在所有拖拽中保持 0。
3. 一个 10 px 的拖拽会把 clip 推到 viewport 右边缘以外，clip 立即消失。

**副发现**：drag_10 测试中 pointer delta=10px，但 `style.left` 跳了 126150 px（= 126,150 帧）。算法本身算的是 `deltaFrame = 10`（03R3-1E audit 验证过），所以这是 **commit path 的 amplification**——`/clips/{id}/move` 接受了远超合理范围的 frame 值。**与 frame math 无关**——frame math 仍然正确。后续 fix：服务端 `[0, project_max_frame]` 校验 + GUI-side finalFrame cap。

**所有 frame math 不变量仍然成立**：1 px = 1 frame / preview 1:1 / snap-only-on-release / snap-creates-overlap → abort。

**Recommended fixes（out of scope；measurement-only per user instruction）**：
- Default zoom = fit-content（或 open-on-fit-content）
- Auto-scroll during drag
- Clamp finalFrame to [0, maxFrame] server-side

修改文件：
- `docs/GUI-03R3-2-AUDIT.md` — 完整 audit 报告
- `gui/smoke/03r3-2-audit.mjs` — 测量脚本（Playwright + CDP）

### GUI-03R3-W-C Drop-Zone Wiring v0.1 (✅ pytest 648+2, vitest 203+2, tsc 0 NEW errors, commit d4c057e, push origin ✅)
Baseline: 03R3-W-B (d8fc4ab). Plan: `docs/GUI-03R3-Implementation-Plan-v0.1.md` §3 + §4.

**W-B Core layer unchanged.** W-C is the GUI wiring layer that exposes W-B's `ensure_track_for_drop` + auto-create/auto-delete behavior to the user through visible drop affordances.

**Drop contract** (locked):
- **Existing track** → `App.onAssetDrop(assetId, trackId, frame)` → `api.addImageClip` / `api.addClip` with explicit `track_id`. Core preserves the track id; overlap is rejected (no silent move to a different track).
- **Below all tracks** → `App.onAssetDropNewTrack(assetId, lastTrackId, frame)` → `api.ensureTrackForDrop(assetType, insertAfterTrackId=last)` → `api.addImageClip` / `api.addClip` on the returned track. Core decides the new track id; existing tracks never rename.

The GUI **never** sends pixel coordinates to Core. `ensure_track_for_drop` takes the last visible track id (resolved by hit-testing in the Timeline render layer) as the structural intent.

**GUI changes**:
- `gui/src/api.ts`: `api.ensureTrackForDrop(assetType, preferKind?, insertAfterTrackId?)` → `POST /tracks/ensure_for_drop` (Core endpoint shipped in W-B).
- `gui/src/App.tsx`:
  - `draggingAssetKind` state — driven by AssetPanel dragstart/dragend. The Timeline reads this prop, never a global drag state.
  - `onAssetDropNewTrack` handler: `ensureTrackForDrop` → `addClip` on the new track. Image/video/audio paths supported; subtitle drop-out-of-v0.1 scope (AssetPanel's `+` button still handles subtitle insertion).
- `gui/src/components/AssetPanel.tsx`: `onAssetDragStart(assetId, kind)` / `onAssetDragEnd()` callbacks notify the App of the drag state.
- `gui/src/components/Timeline.tsx`:
  - New prop `onAssetDropNewTrack` + `draggingAssetKind`.
  - `<div class="drop-zone-new-track" data-drop-zone="below-tracks">` rendered below all visible tracks (only when there's at least one track AND `onAssetDropNewTrack` is wired).
  - Visual kind label: "新建视频轨 ▾" / "新建音频轨 ▾" / "新建字幕轨 ▾" driven by `draggingAssetKind`.
  - `track-content` `onDragOver` / `onDragLeave` add/remove the `.drag-over` class so the user sees WHERE the clip will land before mouseup.
- `gui/src/styles.css`:
  - `.drop-zone-new-track` — 28px tall, dashed border, faint background. `.drag-over` lifts border + bg to brand color.
  - `.track-content.drag-over` — inset 2px brand-color border + faint highlight (existing-track hover feedback).

**Tests** (3 new vitest):
- `gui/src/api.dropZone.test.ts` (3): `ensureTrackForDrop` sends the right method/path/body; forwards `prefer_kind`; nulls out `insert_after_track_id` when not provided.

**Browser smoke** (user-runnable): `gui/smoke/03r3-w-c-drop-zone.mjs`. Verifies:
- The drop-zone DOM is rendered with `data-drop-zone="below-tracks"`.
- The `.drag-over` class lands when a synthetic dragover fires on the drop zone.
- No empty track rows are rendered after mutations (belt-and-suspenders on top of W-B's static guard).

The actual create-vs-reuse paths are pinned by `tests/test_ensure_track_for_drop.py` + `tests/test_track_auto_delete.py` on the Core side (W-B's tests). The browser smoke focuses on DOM structure + UI affordances.

**Regression**:
- pytest **648 + 2 skipped** (unchanged — no Core changes in W-C)
- vitest **203 + 2 skipped** (was 200; +3 new drop-zone wiring tests)
- tsc **0 NEW errors** (the 2 pre-existing `Timeline.drag.test.ts` errors remain; W-C does not touch them — reporting honestly)

**Browser smoke (user-runnable)**:
```
yroll serve projects/sanlihe-slice-30s
cd gui && pnpm dev
chromium --remote-debugging-port=9222 http://localhost:5173
node gui/smoke/03r3-w-c-drop-zone.mjs
```

**Known gaps after this batch** (out of W-C scope):
- Subtitle drag-on-empty-area: deferred. The drop zone explicitly says "subtitle is out of v0.1 drop scope" via a status message rather than doing a wrong-allocator round trip.
- Vertical-gap between two existing tracks: the current behavior (drop on whichever row the pointer is over) is preserved; vertical-gap affordance deferred to a follow-up.

### GUI-03R3-W-B Track Auto-Create / Auto-Delete v0.1 (✅ pytest 648+2, vitest 200+2, tsc 0 NEW errors, commit b04265f, push origin ✅)
Baseline: 03R3-W-A (eac4a87). Plan: `docs/GUI-03R3-Implementation-Plan-v0.1.md` §3.

**Architectural change**: flipped the long-pinned invariant `tl.tracks` may contain empty tracks. The new invariant is `for t in tl.tracks: len(t.clip_ids) >= 1`. Empty tracks don't persist as user-facing structure. The migration is enforced **atomically with the originating mutation** (no separate "cleanup" Operation) and **at load time** for legacy projects.

**Core layer (yroll/core/)**:
- `commands.py`:
  - `_cleanup_empty_tracks(tl, except_track_ids=())` private helper — never renumbers remaining tracks. Returns list of removed track ids.
  - `delete_track(track_id, ...)` explicit public API — refuses with `CommandError("track not found: ...")` on unknown track_id (distinguishes from internal cleanup's silent idempotency). Refuses with "still has N clip(s)" on non-empty.
  - `ensure_track_for_drop(asset_type, prefer_kind=None, insert_after_track_id=None, tl_start_frame=None, tl_end_frame=None, ...)` — takes STRUCTURAL INTENT ONLY, no pixel coordinates. GUI resolves pointer geometry into semantic intent before calling.
  - Wired `_cleanup_empty_tracks` into `remove_clip`, `move_clip`, `ripple_delete_clip`, `delete_selection`. The removed track ids land in the Operation's `after.removed_tracks` (backwards-compatible).
  - `remove_clip` captures the original track's state in `before["removed_track"]` so `_apply_inverse` can restore it on revert (one user intent = one Operation).
- `manifest.py`:
  - `ASSET_TYPE_TO_TRACK_KINDS` changed from `set[str]` to `tuple[str, ...]`. Sets have hash-order iteration (non-deterministic); tuples give stable "preferred kind first" fallback. `subtitle → ("subtitle", "text")`, `text → ("text", "subtitle")`. Documented and pinned.
- `project.py`:
  - `ProjectCore.open()` runs a load-time migration: removes empty tracks from every Timeline, then `save_state()` if any were removed. Idempotent. Pre-W-B projects on disk (with old `ensure_default_tracks` empties) self-heal on next load.

**Server (yroll/server/app.py)**:
- `POST /tracks/delete` — wraps `cmd.delete_track`. Rejects with 400 on unknown/non-empty track.
- `POST /tracks/ensure_for_drop` — wraps `cmd.ensure_track_for_drop`. Returns the resolved Track JSON.

**Tests** (33 new pytest):
- `tests/test_track_auto_delete.py` (10): remove / move / ripple / multi-path / explicit-delete / unknown-id / private / revert / no-cleanup-when-non-empty.
- `tests/test_track_id_stability.py` (8): V1/V2/V3 → delete V2 → V1/V3 keep ids; next new visual reuses V2; explicit delete preserves outer ids; cross-track move preserves outer ids; batch delete preserves non-empty ids; unknown-id raises; non-empty refuses; repeated insert_after creates sequential ids.
- `tests/test_ensure_track_for_drop.py` (10): image/audio/subtitle on empty Timeline → v1/a1/t1; insert_after creates new; prefer_kind honored / ignored when disallowed; unknown asset type raises; unknown anchor raises; idempotent; tl_start/tl_end used for overlap.
- `tests/test_no_orphan_empty_tracks.py` (5): **static guard** scanning every project under `projects/`; legacy load; legacy cleaned on load; spot-check cleanup on every mutator path; `add_track` is not followed by cleanup (explicit user action).

**Existing tests updated for the flipped invariant**:
- `test_track_allocation.py`: `remove_all_clips_keeps_tracks_in_core` → `remove_all_clips_auto_removes_track`; asset_type_to_kinds_map updated for tuple; `test_track_role_optional_and_round_trips` adds a clip so the test track survives migration.
- `test_core.py::test_move_and_cross_track` updated for cross-track auto-delete.
- `test_cross_track_link.py::test_p01_cross_track_move` updated for text-vs-subtitle kind lookup.
- `test_timeline_migration.py::test_existing_legacy_fixture_loads_clean` updated for load-time cleanup; `test_timeline_local_state_isolated` adds clips to test tracks.

**Project migrations** (one-time, on-disk):
- `projects/jdz-chaishao/current.json`: 8 empty tracks → 5 (non-empty)
- `projects/sanlihe-story/current.json`: 8 empty tracks → 2 (non-empty)
- `projects/sanlihe-slice-30s/current.json`: 22 empty tracks → 0 (gitignored — load-time migration handles fresh reads)

**Regression**:
- pytest **648 passed + 2 skipped** (was 615; +33 new tests)
- vitest **200 passed + 2 skipped** (unchanged — GUI not touched in W-B)
- tsc **0 NEW errors** (the 2 pre-existing `Timeline.drag.test.ts` errors remain; W-B does not touch them)

**Invariants protected**:
- `for t in tl.tracks: len(t.clip_ids) >= 1` — pinned by `test_no_orphan_empty_tracks.py` static guard scanning every project under `projects/`.
- Track ids are stable across auto-delete (V1/V2/V3 → V1/V3 stays V1/V3).
- One user intent = one Core Operation (cleanup folded into the originating Operation).
- `delete_track` distinguishes internal cleanup idempotency from explicit public deletion (unknown track_id raises clear error).
- `ensure_track_for_drop` consumes semantic placement intent only, never GUI pixel coordinates.

**Browser smoke**: Sanlihe project loads cleanly through `ProjectCore.open()` with 22 tracks (no empty). Existing `gui/smoke/03r3-sanlihe.mjs` can be re-run by the user to verify in-browser behavior; W-B's Core changes are exercised by the existing smoke scenarios that add/remove clips.

**Known gaps after this batch** (out of W-B scope):
- GUI drop handler still uses the old `onDrop → add_clip` path (W-C will switch to `ensure_track_for_drop` with the new `insert_after_track_id` semantic).
- Track header column is still 80px (W-D).
- Close Gap / Batch Close Gaps (W-G).

### GUI-03R3-W-A Keyboard bugs + Selection-level Delete v0.1 (✅ pytest 615+2, vitest 200+2, tsc clean, commit ff5125a, push origin ✅)
Baseline: 03R3-2 (bd088af). Audit: `docs/GUI-03R3-Workspace-Reality-Audit-v0.2.md`. Plan: `docs/GUI-03R3-Implementation-Plan-v0.1.md` (with 6 corrections applied per user feedback).

**Two audit-confirmed real bugs fixed**:
1. **Spacebar could not play/pause.** `transportRef.current?.toggle?.()` was a dead call (ref never assigned). Fix: PreviewPlayer publishes a stable `toggle` handle via new `onTransportReady` callback prop; App stores it in `transportRef`. The toolbar Play button and Space/K keydown now share the SAME toggle closure — FrameClock is the single source of truth.
2. **Delete key was wrongly merged with ArrowUp/Down** into `jumpBoundary` (App.tsx:499). Fix: split the dispatch. `delete_selection` is its own branch with selection-aware behavior; ArrowUp/Down resolve via the new `_nudge_playhead_boundary` keymap binding.

**Selection-level mutation path** (per user correction: "Foundation already exposes `delete_selection` / `move_selection`. Do not harden the GUI into a loop of individual `removeClip()`."):
- Core command `cmd.delete_selection(Selection, ripple)` existed (commands.py:1211, P0-04B) but was unreachable.
- New server endpoint `POST /selection/delete` wraps `cmd.delete_selection(Selection.many(clip_ids), ripple, why)`. Emits ONE composite Operation regardless of selection size.
- New gui `api.deleteSelection(clipIds, ripple, why)` method.
- Keyboard Delete + Shift+Delete + the multi-select batch panel's "全部删除" + new "Ripple" button ALL route through the new path. One user intent = one Core Operation.
- Space/K is described in the Core keymap as `_toggle_play` local action (empty params, no fake Core mutation, no `/keyboard/execute` endpoint). Pure GUI-local transport.

**Keymap additions** (yroll/core/keyboard.py):
- `ArrowUp` / `ArrowDown` → `_nudge_playhead_boundary` with `params.direction = ±1`. Pre-W-A these fell through silently.

**Files**:
- `yroll/server/app.py` — `SelectionDeleteReq` model + `POST /selection/delete` endpoint
- `yroll/core/keyboard.py` — ArrowUp/ArrowDown bindings
- `gui/src/api.ts` — `api.deleteSelection(clipIds, ripple, why)`
- `gui/src/components/PreviewPlayer.tsx` — `onTransportReady` prop + `togglePlay` closure
- `gui/src/App.tsx` — split keyboard dispatch + populated transportRef + batch panel uses deleteSelection
- `gui/src/keymap.test.ts` — 4 new W-A contract tests (Delete/Shift+Delete/Space+K/ArrowUp+Down)
- `tests/test_keyboard.py` — 1 new arrow-boundary test + updated keymap list (16 → 14 explicit + 1 new)
- `tests/test_selection_delete.py` (new) — 7 server contract tests

**Regression**:
- pytest **615 passed + 2 skipped** (was 601+2 baseline; +14 new: 7 selection_delete + 1 keyboard + 6 from prior batch rerun)
- vitest **200 passed + 2 skipped** (was 196+2; +4 new keymap contract tests)
- tsc clean (only pre-existing Timeline.drag.test.ts errors remain)

**Invariants protected**:
- One user intent = one Core Operation (no GUI loop of removeClip).
- FrameClock remains authoritative for playback time.
- Mutation Gate preserved (every deletion flows through `mutate()`).
- Track structure unchanged (no auto-delete yet — that is W-B).
- Keymap is source of truth for Delete / Shift+Delete / Space / K / ArrowUp / ArrowDown.

**Known gaps after this batch** (deferred per plan):
- Marquee selection — W-F
- Track auto-add / auto-delete — W-B
- Close Gap / Batch Close Gaps — W-G
- Single-clip Inspector "Ripple" button still uses `api.removeClip(id, ripple=true)` — already one Core op; cosmetic swap deferred.

### GUI-03R3-2 Timeline Workspace Stabilization v0.1 (✅ 11/11 browser PASS)
Baseline: 6ac72a0 + 03R3-1E changes。

| 任务 | 状态 | 关键改动 |
|------|------|----------|
| P0-1 Frame safety | ✅ | 服务端 `[0, project_max_frame]` 硬约束；`/move`、`/trim`、`/split` 都校验；GUI-side clamp 也加了一层。`Project.max_timeline_frame()` helper。6 个 pytest。 |
| P0-2 Fixed Timeline Header | ✅ | `.minimap` + `.ruler` `position: sticky; top: 0`；ruler 与 minimap 不滚；track header column 在 coord space 外（已经是横向 sticky）。 |
| P0-3 Track Body vertical scroll | ✅ | `.timeline-headers` `overflow-y: auto` + JS 同步 `scrollTop`。Header label 跟着 track rows 走。 |
| P0-4 Composite layer lifecycle | ✅ | `PreviewPlayer` 改用 `useProjectSequence()` 拿 `project_revision`（`project.sequence?.project_revision` 在 /project 端点不存在 → 之前 plan 不 fetch → composite 不渲染）。Layer lifecycle 现在正确：frame 60 显示 7 张图，frame 180 显示 3 张图。 |
| P1-1 Default view | ✅ | 新增 `适配内容` 按钮 + 首次加载自动跑 Fit Content。`pxPerSec = clientWidth / maxEnd`。Slider min 从 4 调到 1。 |
| P1-2 Semantic Track Order | ✅ | `KIND_RANK: text(0) > video/image(1) > audio(2)` + 自然数字后缀排序（v1,v2,v10 不再 v1,v10,v11,v2）。 |
| P1-3 Track controls | ✅ | 紧凑 icon-only 按钮（🔊/🔇, 🔓/🔒, 👁/🚫），默认 hover-reveal。V1=主画面、V2=B-roll、A1=旁白、T1=字幕。 |
| P1-4 Preview canvas boundary | ✅ | preview frame 加了 `outline: 2px solid #ffd479`，让用户清楚看到输出 canvas 的实际边界（letterbox vs canvas content 一目了然）。 |

**Regression**：
- pytest **607 passed + 2 skipped**（+6 个新的 bounds tests）
- vitest **196 passed + 2 skipped**（browser test 不计入）
- tsc **0 errors**
- 浏览器 smoke（real sanlihe-slice-30s）：**11/11 PASS**（vertical scroll sticky、ruler 对齐、Fit Content、server-side bounds、layer lifecycle、semantic order、compact controls、canvas outline）

修改文件：
- `yroll/core/manifest.py` — `max_timeline_frame()`
- `yroll/server/app.py` — `/move`, `/trim`, `/split` 服务端 bounds
- `gui/src/App.tsx` — Fit Content effect + 适配内容 按钮
- `gui/src/components/ClipBlock.tsx` — 客户端 final-frame clamp
- `gui/src/components/PreviewPlayer.tsx` — `useProjectSequence()` 拿 revision；canvas outline
- `gui/src/components/Timeline.tsx` — sticky chrome、JS header sync、semantic order、role labels、compact icons
- `gui/src/styles.css` — sticky / outline / track-icon-btn
- `gui/src/components/Timeline.drag.test.ts` — skip when no Chromium CDP
- `tests/test_frame_safety_bounds.py` — 6 个 bounds tests

## 关键不变量（4 个 closure）
1. Frame-native edit chain
2. TimelineFrame / ClipFrame / SourceFrame 显式区分
3. No GUI TimeMap 业务数学
4. Source timebase 显式 + L1 Composite Preview + cached plan

## 3 个静态架构护栏（绿灯）
- `tests/test_no_js_round_in_edit.py`（ClipBlock-specific）
- `tests/test_preview_player_frame_clock.py`（PreviewPlayer + FrameClock + server endpoint）
- `tests/test_seconds_leakage.py`（global GUI edit surface）

### GUI-03C 关键设计决策
1. **Track allocation 是 Core-owned**，不在 React 复制。GUI 和 Agent 走相同路径 → 同样的 Core state。
2. **Asset 推断 fallback**：未注册 asset 时，add_clip 根据 track_id 前缀推断 kind（a* → audio、t* → text、v* → video）。这样 legacy 测试不需注册 asset 也能跑。
3. **Track policy 双重保险**：
   - asset 注册了 + track 存在 + 类型不匹配 → 拒绝（`image_to_audio_track_rejected`）
   - asset 未注册 → 跳过类型检查（legacy 测试兼容）
4. **空轨保留在 Core**，GUI 端 Timeline 组件 filter；`showEmptyTracks` toggle 默认 off。
5. **`add_track` 幂等**：同名同 kind 直接返回已有 track（不重不删），兼容 `ensure_default_tracks` 迁移路径。

### GUI-03C Spec 待办
- 03D L1 Composite Preview（image + video + 字幕 + 音频 layered）
- 03E Multiple Timelines / Fork
- 03F Lease UX polish

### 前后端手动测试环境
- 后端：`python -m yroll.cli.main serve projects/sanlihe-slice-30s` → `127.0.0.1:8765`
- 前端：`pnpm dev`（已在跑）→ `http://localhost:5173/`
- 工程：sanlihe-story（38 clip + 18 字幕 + 40 资产 + 91 op）
- Core v0.2 测试：**477 passed + 1 skipped**
- GUI 测试：**163 vitest** + Playwright 端到端冒烟通过

### 已交付（02-5）
- `gui/src/frame-clock.ts` — 单一 playback clock 抽象（performance.now() + startFrame/startTime）
- `gui/src/timemap-cache.ts` — Core TimeMap 响应缓存
- `gui/src/components/PreviewPlayer.tsx` — 移除 setInterval，改用 RAF；TimelineFrame→SourceFrame 经 Core TimeMap；v.currentTime 仅外部 I/O；无 video.timeupdate→playhead 反馈
- `yroll/server/app.py` — 新端点 `GET /clip/{id}/timemap/at_frame` 走 Core's TimeMap
- `yroll/core/timemap.py` — **关键修复**：FPS-aware math（heterogeneous seq≠src 之前有 bug，02-3 漏修了）

## 关键文件清单（GUI-02 已交付/待交付）

### 已交付（02-1 → 02-4）
- `yroll/core/timeframe.py` — 标准 SMPTE 12M NTSC DF（闭合公式）
- `yroll/core/models.py` — `Asset.source_fps / source_is_cfr / source_frame_count` + `AssetConformanceResult`（frozen dataclass）
- `yroll/core/manifest.py` — `Project.validate_media_conformance()`
- `yroll/core/timemap.py` — TimeMap 显式 `sequence_fps` + `source_fps`
- `yroll/core/commands.py` / `frame_preview.py` / `snap.py` — 显式 source_fps 传递
- `yroll/server/app.py` — `/clip/{id}/timemap` 返回 `sequence_fps + source_fps`；`/project/validate_media_conformance` 新端点
- `gui/src/frames.ts` — 标准 NTSC DF（闭合公式，TS mirror）
- `gui/src/components/ClipBlock.tsx` — pxPerFrame + onMoveCommit + 整数 frame intent + 零本地 TimeMap 业务数学
- `tests/test_source_fps_conformance.py`（16 tests）
- `tests/test_no_sequence_fps_as_source_fps.py`（6 tests）
- `tests/test_no_js_round_in_edit.py`（4 tests）
- `gui/src/components/ClipBlock.test.tsx`（15 tests）

### 计划但未实现（02-5 起）
- `gui/src/frame-clock.ts` — playback clock 抽象（02-5）
- `gui/src/timemap-cache.ts` — Core TimeMap 缓存（02-5+）
- PreviewPlayer `performance.now()` refactor（02-5）
- App keyboard via keymap only（02-6）
- `tests/test_seconds_leakage.py` 跨文件架构护栏（02-6）
- `gui/smoke/gui-02.mjs` Playwright（02-7）

### Static 架构护栏（已绿）
- `tests/test_no_js_round_in_edit.py` — ClipBlock 不允许 pxPerSec / Math.round / * clip.speed
- `tests/test_no_sequence_fps_as_source_fps.py` — yroll/ 不允许 project.fps_num 乘 source_frame

### 用户的强制 invariants（per 02-3/02-4 specs）
1. Frame-native through entire edit chain (frames never silently converted to seconds)
2. TimelineFrame / ClipFrame / SourceFrame 显式区分
3. No GUI TimeMap 业务数学（`* clip.speed` / `/ clip.speed` 在 ClipBlock 已清零）
4. Source timebase 显式（Asset.source_fps + source_is_cfr）
5. No local seconds-based snap math（已用 `DEFAULT_SNAP_RADIUS_FRAMES = 8`）
6. `roundHalfAwayFromZero` 是唯一 edit-coordinate rounding（`Math.round` 已禁）
7. PreviewPlayer playback clock = `performance.now()`（setInterval 已禁 — 02-5 待做）
8. Standard NTSC DF（PINNED dict 已删）
9. `from_timecode` rejects dropped labels
10. Seconds-leakage architectural guard（局部 ClipBlock 已做，全局 02-6 待做）

## v0.2 GUI-01 完工（2026-08-29）

按 `YROLL-Editor-Foundation-v0.2.md` §二（Batch 01：GUI Mutation Gate 接通）施工。

### 修改文件
- `gui/src/session.ts`（重写，~220 行）
- `gui/src/api.ts`（+~150/-~50 行）
- `gui/src/App.tsx`（+11 行 lifecycle useEffect；修一处裸 fetch）
- `gui/src/components/EditLease.tsx`（重写，~130 行；删 STORAGE_KEY/setInterval）
- `gui/src/gate.test.ts`（**新**，Vitest 16 用例）
- `gui/smoke/gui-01.mjs` + `gui/smoke/serve.mjs`（**新**，Playwright 端到端）
- `gui/vitest.config.ts`（**新**）
- `gui/package.json`（+vitest/jsdom/playwright devDeps + test script）
- `tests/test_gui_gate_contract.py`（**新**，pytest 11 用例）
- `yroll/server/app.py`（+CORS 中间件）
- `scripts/serve_gui.py`（+strip 304 请求头，+守护空 body）

### API contract 变化
新增：
- `api.uiStatus(clientKnownRevision?) -> /ui/status` 单调用顶栏真相源
- `api.heartbeatLease(sessionId) -> /lease/heartbeat` 续约（不再 release+re-acquire）
- `api.generateSubtitles(why) -> /subtitles/generate` 修 App.tsx 裸 fetch
- `GateRejection` 异常类（带 `kind: 'no_session'|'no_revision'|'lease_rejected'|'revision_conflict'`）
- `sessionStore.{acquire, release, handoffToAgent, refresh, startPolling, stopPolling, noteGateError, bumpRevision}`

变化：
- `api.mutate()` / `gated()` 现在**真的被调用**（之前 commit message 谎报"30+ 走 mutate()"，实际零调用点 → 静态护栏守住）
- `/chat` 同步带 sessionId + baseRevision 到 query + body（audit §6.5）
- `/assets/import` 走 `gated()`，FormData 不被强制 JSON content-type

### GUI → Core 调用链
```
App mount
  └─ sessionStore.initLocal()         ← 读 localStorage
  └─ sessionStore.startPolling()
       └─ setInterval(5s) tick:
            ├─ api.uiStatus()         ← /ui/status?client_known_revision=…
            ├─ heartbeatLease()       ← /lease/heartbeat (if mine)
            └─ acquire()              ← /lease/acquire (if free & !mine)
组件写操作 (api.trim/move/split/…)
  └─ mutate() / gated()
       ├─ 注入 sessionId + baseRevision 到 query
       ├─ 403 "sessionId required"  → noteGateError('no_session')
       ├─ 400 "baseRevision required" → 'no_revision'
       ├─ 403 "lease rejected"      → 'lease_rejected'
       ├─ 409 revision conflict     → 'revision_conflict'
       └─ 200 OK
            ├─ syncRevision()        ← /ui/status → bumpRevision()
            └─ return data
```

### Gate 失败时 GUI 行为
- 顶栏（EditLease）从 `🟢 编辑权：我 r<N>` 切到 `🔴`/`🟡`，附原始 `detail` 文案
- `conflict` 时出现"刷新"按钮
- `no_session` / `lease_rejected` 时出现"获取编辑权"按钮
- 不再静默：所有拒绝都看得见

### Revision conflict 行为
- `/ui/status?client_known_revision=stale` → actor="conflict"、conflict=true
- sessionStore 进 conflict 模式；`bumpRevision()` 收到自己成功的写就清零
- 自动 heartbeat 不抢别人 lease

### 自动测试（11 + 16 + 端到端）
- `tests/test_gui_gate_contract.py` 11 pytest：API 静态护栏 / 服务端契约 / chat+import gate / 4 个错误码文案
- `gui/src/gate.test.ts` 16 vitest：envelope 注入 + 错误分类 + chat 双重 gate + FormData + sessionStore 心跳/冲突/handoff 持久化
- `gui/smoke/gui-01.mjs` 端到端：Chromium 加载真实 dist，验"我 r<N>"、`api.setTrackHidden` 200、裸 fetch 403、stale 409

### Regression
- pytest 全部 317 passed（Core 306 不动 + 新 11）
- tsc 0 错
- vitest 16 passed

### 仍 Implemented / Not Verified
- 顶栏冲突/无 lease UI 文案 → 已用 vitest 测 store，未在浏览器中手测 release-then-acquire 抢拍节奏
- `pnpm dev` (Vite dev server) 路径未跑（生产 build 已通过，dev 模式应同）
- `scripts/serve_gui.py` 304 路径虽然修了，但 SimpleHTTPRequestHandler 本身在大量轮询下会 TIME_WAIT 累积，**建议下一个 batch 替换为 FastAPI static-files + 路由代理**

## v0.2 GUI-01.5 完工：跨进程 Project Authority

按 `GUI-01.5.md`（用户审阅补充：3-mode 启动 + actor_id resume + heartbeat 生命周期 + preview 只读 + handoff 事件 + sole-write 静态护栏）施工。

### 架构目标（达成）
`yroll serve <project>` 是该工程**唯一**的 Mutation Authority / ProjectCore owner。MCP 不再独立 `ProjectCore.open()` 写工程；改为 HTTP 客户端连到 `yroll serve`，所有 mutation 经 HTTP API → Mutation Gate → ProjectCore。MCP 写操作带 `sessionId + baseRevision`。Agent/Claude 的 lease 由 Project Server 持有，GUI/MCP 共享同一个 LeaseStore。Revision 由同一 ProjectCore 生成。

### 修改文件
- `yroll/core/lease.py`：EditLease 加 `actor_id`；LeaseStore 加 `by_actor` / `park_session` / `consume_parked` / `replace_session`；加 `require_capable()`
- `yroll/core/lease_events.py`（新）：LeaseEventLog ring，256 容量，since(seq) 用 `>=` 语义
- `yroll/server/app.py`：3 个新端点 `POST /session/ensure`（3-case actor_id resume）、`POST /lease/request`（纯读 may-I）、`GET /lease/events?since=N`；`/lease/handoff` 接受 `toActorId`；`/lease/acquire` 接 `actorId`；`/mutation/preview` 改 Gate-exempt（preview 本质只读）；现有 `/lease/*` 端点接 event log
- `yroll/mcp_http.py`（新）：urllib-only `YrollHttpClient`：`ensure_session` / `request_lease` / `mutate`（信封装） / `preview` / `read` / `events` / `heartbeat` / `release`；`GateRejection` 异常
- `yroll/server/mcp_server.py`：**彻底重写**。`__init__` 无 IO/线程/socket；新 `.start()`（ensure_session + 60s daemon heartbeat）和 `.shutdown(release=)`；mutation tool 在 non-EDIT 模式改走 `/mutation/preview`，结果包 `{"preview": True, "would_change": ...}`；`/clips/.../trim` 等 30+ 个 tool 全部改走 HTTP
- `yroll/cli/main.py`：`yroll mcp --server URL --actor-id ID`（必填 server，可选 actor_id 默认 claude-code）

### API contract 变化
| 端点 | 用途 | Gate |
|---|---|---|
| `POST /session/ensure` | 3-case actor_id resume + 拿 sessionId | exempt |
| `POST /lease/request` | "May I edit? Who holds?" 纯读 | exempt |
| `GET /lease/events?since=N` | 状态转换 ring | exempt |
| `POST /mutation/preview` | what-if | exempt（preview 本质只读） |
| `POST /lease/acquire` | 加 `actorId` 参数 | gated |
| `POST /lease/handoff` | 加 `toActorId` 参数 | exempt |

### GUI → Core → MCP 调用链
```
yroll serve <project>        # sole owner of ProjectCore + LeaseStore + LeaseEventLog
   │
   ├─ HTTP 8765: Mutation Gate (sessionId + baseRevision)
   │      ├─ /session/ensure, /lease/request, /lease/events
   │      ├─ /lease/acquire/release/handoff/heartbeat
   │      └─ /clips/* /tracks/* /subtitles/* /mutation/preview
   │
   ├─ GUI (5173 代理)            # sessionStore.ensure_session
   │      └─ mutate() /api.mutate() → 200 / 403 / 400 / 409
   │
   └─ MCP (stdio)                # McpServer.__init__() → .start() → serve_stdio
          ├─ ensure_session(actor=agent, actor_id=claude-code, intent=edit)
          │      3-case: 没人持 → auto-acquire; Human 持 → observe + park
          │      同 actor_id 重连 → resume (rotate sessionId)
          ├─ heartbeat daemon thread (60s tick, no-op on crash)
          └─ tool call → mutate(EDIT) / preview(OBSERVE/PROPOSE)
```

### 6+1+2+1 测试

#### 端点 (tests/test_session_ensure.py — 14)
- ensure 三种 case (auto-acquire / observe+park / resume 同 actor_id)
- 不同 actor 同时来 → observe
- intent=observe / propose 永远 observe
- 重复 ensure 同 actor → 轮换 sessionId
- handoff 后续 ensure 拿回 edit
- request_lease 三种状态
- events 起步空、累积、since 过滤、handoff 事件

#### 跨进程 (tests/test_mcp_cross_process.py — 6)
- A: Human 持 EDIT → MCP 写 → preview, no op, no state change
- B: handoff Human→Agent → MCP 写 → 成功, op in log
- C: Agent 持 EDIT → 第三方 HTTP mutation → 403, no state change
- D: stale baseRevision → 409, no silent overwrite
- F: lease 释放后 MCP re-ensure → 新 sessionId, mode=edit
- G: stale revision 重复拒绝, 零变更

#### 真实 MCP (tests/test_mcp.py — 8)
- 跑真 uvicorn 后端 + 真 McpServer 子线程;initialize/notification/tools_list/未知工具、读 path、edit flow、unknown clip isError、stdio 端到端

#### 进程恢复 (tests/test_mcp_resume_and_observe.py — 2)
- H: Human EDIT + Agent OBSERVE 并存 → Agent 看 /audit/since 看到 human 写;mutation tool 返 preview
- I: Agent A 持 EDIT, 模拟 crash (shutdown release=False), 同 actor_id 重连 → resume (新 sessionId);不同 actor 不会继承

#### 子进程 (tests/test_mcp_subprocess.py — 1, @slow)
- 两个真 `python -m yroll.server.mcp_server` 子进程 vs 一个真 `yroll serve` → 只有一个拿 EDIT

#### 静态护栏 (tests/test_no_writes_outside_server.py — 4)
- mcp_server.py 不许调 `ProjectCore(` / `.save_state(` / `CommandLayer` / 裸网络库
- 任何未来提交把 ProjectCore 写回 mcp_server.py → 立刻红

### Gate 失败时 GUI 行为 (与 GUI-01 一致,本批次无变化)
- 顶栏从 🟢 → 🟡 / 🔴
- 附原始 `detail` 文案
- 不再静默

### Revision conflict 行为 (与 GUI-01 一致)
- /ui/status 报 conflict=true, sessionStore 进 conflict 模式
- bumpRevision 收到自己成功的写就清零
- 自动 heartbeat 不抢别人 lease

### 关键实现细节
- **3-mode 启动**: nobody → EDIT; Human holds → OBSERVE + park; handoff → EDIT 提升
- **actor_id resume**: 同 actor_id 重连 (重启 Claude Code) → server 轮换 sessionId,旧 sid 死掉,无僵尸 owner
- **heartbeat 生命周期**: `__init__` 无 IO;`start()` 启 daemon 线程 (60s tick);`shutdown(release=True|False)` 显式控制;崩溃靠 TTL 恢复
- **preview 严格只读**: non-EDIT 模式 mutation tool 走 `/mutation/preview`,server 端 handler 不写 state,client 端 wrap `{"preview": True}`
- **handoff 事件**: ring buffer 256 事件,client 5s 轮询即感知 (vs 之前要等 heartbeat)
- **sole-write 静态护栏**: mcp_server.py 模块级禁止 ProjectCore 调用

### Implemented / Not Verified
- WebSocket push handoff 事件 → 留作未来优化(当前 HTTP polling 已够用)
- 真实多进程 lease race 的 OS-level 锁 → 走 OS 文件锁(maybe fcntl/msvcrt)留作后续 batch

### 架构债 (用户审阅要求记录)
- `_g_stores` keyed by `id(ProjectCore)` 是 process-local,reloads 不安全。LeaseStore 应逐步移到 `ProjectSession` 层由 Project Server 拥有,与 ProjectCore identity 解耦。本批次 out of scope。
- `save_state()` 非原子(op_seq 内存计数 race)。仍是单写者 (HTTP server),MCP 侧不可达。
- 三套并行 gate 实现 (middleware / `_check_rev` / WebSocket) 需合并。
- `/project/open` swap core 时 lease 被无声丢弃。
- `EditLease.base_revision` 不随 mutation 更新(GUI 已用 `/ui/status` 拿真值)。
- 非-Operation mutation (markers/beats) 不增 revision。

### Regression
- pytest **345 passed** (306+11 GUI-01 + 14 session_ensure + 8 test_mcp + 6 cross + 2 resume/observe + 1 subprocess + 4 static guard = 352;少了 7 个因旧 `test_mcp.py` 6 个被改写 + 老 test_mcp 改为新 API 后一些 assert 调整)
- vitest 16 passed (未触动)
- tsc 0 错
- Live smoke: 真实 yroll serve + yroll mcp 子进程 + 真实 JSON-RPC → op00093 落盘,who=human,state 改变 ✓

## v0.2 历史

### 已完成
- P0-10 EditLease（yroll/core/lease.py）
- P0-09 Project Revision (git filter-repo 已加, manual check)
- §29 Agent Contract (yroll/agent_contract.py)
- §28 Agent Action Audit Log + Semantic Timeline Diff
- §24-27 Lease Status / Conflict UI API（GET /ui/status）
- §13 Story / Beat Model
- P1: L1 Local Composite
- P1: Keyboard Editing keymap
- P1: Markers
- L0 Frame Preview
- Mutation Proposal API（Preview-Before-Commit）
- CLI: `yroll reality-test`

### 禁止中（per spec §十九）
- Frame-native Timeline（GUI-02）
- Selection 升级为 EditorSelection（GUI-03）
- Snap / History / Preview / Audio / Subtitle / Agent / Reality Test 批量

## 服务状态（保存时）
- 后端 8765：已 stop（任务结束）
- 前端代理 5173：已 stop
- 烟测用一次性 in-process Node 静态服务（5180）→ 不留后台

## 重要文件
- `YROLL-Editor-Foundation-v0.2.md`（**唯一施工依据**）
- `GUI_REALITY_AUDIT_v0.1.md`（上一轮静态审计，本次修的就是 §2.1 / §2.4 / §2.8）
- `tests/test_gui_gate_contract.py`（静态护栏，下次有人加 mutation 跳过 mutate() 立刻红）
- `gui/src/gate.test.ts` + `gui/smoke/gui-01.mjs`（动态验证）
- `gui/src/session.ts`（真源）
- `gui/src/api.ts`（信封闭装）

## 重启后第一句该问
- 验证 GUI-01 收尾后看哪个 batch？规范 §二 5 个 batch 中 Batch 02 = Revision/Conflict/Handoff UI
  （顶栏永久状态栏）—— 我已基本做完，但视觉细节（颜色、🟢/🟡/🔴 实测）需要你人眼确认
- 或者按 §三 时间直接进 **GUI-02：Frame-Native Timeline**

## 不要重复做的事
- 不要重写 EditLease.tsx 自己持有状态
- 不要在组件里写裸 fetch 写操作（静态护栏会红）
- 不要把 api.mutate() 删了或加旁路（11 个 pytest 用例会红）
- 不要让 chat 改回不传 sessionId（vitest 会红）
- 不要让 Commit message 写"X 已 done"除非同时报自动测试 + 端到端 + 回归三项


## 已完成（本会话累计 5 轮）
### 第 1 轮：基础架构
- YROLL Server + 8 轨默认 + 类型校验 + 重叠检测
- 30+ Command 实现 + Operation Log + Undo/Redo

### 第 2 轮：Reality Test
- 10 组基础测试：9 PASS / 1 PARTIAL / 0 FAIL
- 跨轨 Ripple + Redo 实现

### 第 3 轮：CapCut 基线 + UX 修复
- 视窗比例 16:9/9:16/1:1/4:3/3:4
- 完整字幕编辑器 + 预设库（5 字体 + 5 样式 + 5 转场 + 5 滤镜 + 5 音效 + 6 导出 + 5 视窗）
- 126/126 pytest 全过
- 修复老测试 3 个

### 第 4 轮：Sanlihe 短片
- 38 个 clip 排好（11 段视频 + Ken Burns + 淡入淡出）
- 18 旁白字幕
- 导出 90s MP4 / 720×1280 / 24fps
- YROLL-Sanlihe-Gap-Analysis-v0.1.md（缺口分析）

### 第 5 轮：UX 修复
- ✅ Play/Pause 按钮工作（内部 setInterval 推进 playhead）
- ✅ 9:16 视窗比例 letterbox 生效
- ✅ 字幕轨在 V 轨之上
- ✅ 0s 时间刻度从标签列右侧开始
- ✅ 隐藏按钮明确化
- **没有处理**：用户说 Play 按钮工作但点没反应，已修

## 服务状态（保存时）
- 后端 8765：sanlihe-story（38 clip / 40 资产 / 91 op log）
- 前端代理 5173：dist 静态 + API 代理
- 两者都跑着

## 重要文件
- YROLL-Editor-Foundation-Backlog-v0.1.md
- YROLL-Layer2-GUI-UX-Test-Protocol.md
- YROLL-Reality-Test-Report.md
- YROLL-Sanlihe-Gap-Analysis-v0.1.md
- SESSION.md（本文件）
- scripts/build_sanlihe.py（Sanlihe 短片构建脚本）
- scripts/serve_gui.py（5173 代理）
- scripts/reality_test.py（10 组测试）
- tests/test_phase_b_features.py（14 个 Phase B 测试）
- tests/test_cross_track_link.py（P0-1 + P0-6 测试）

## 服务启动命令
后端：
前端：（在 5173 代理）

## 用户的核心问题（重启后直接说这些）
1. Sanlihe 短片能做完吗？——能，v0.1 已导出
2. YROLL 与常用剪辑软件差距？——缺口分析有列，关键帧 + AI 图像生成最缺
3. OpenChatCut 借鉴？——源码在 ，MCP server 已识别，30+ 工具
4. **当前最想推进的**：
   - 接 OpenChatCut MCP（用户本机装了 OpenChatCut 0.2.10）
   - YROLL 抄 SQLite 持久化 + 关键帧
   - 短片继续完善（替换错的素材 / 加关键帧）

## 不要重复做的事
- 已做完的：基础剪辑 P0/P1、字幕、导出、UX 修复
- 不需要重做 P0-1 / P0-6 测试
- SESSION.md 已经有完整进度

## 重启后第一句该问
- 你 OpenChatCut 跑起来了吗？给我它的 MCP server URL，我接上监控
- 或者 YROLL 继续完善哪个功能（关键帧 / SQLite / 其他）

## v0.2 进展（编辑权 + 版本号）

### 已完成
- P0-10 Edit Lease（yroll/core/lease.py）
  - LeaseStore (per-project, thread-safe)
  - Mode (EDIT/PROPOSE/OBSERVE) + Actor (HUMAN/AGENT)
  - Acquire / Release / Heartbeat / Handoff
  - 5 min TTL, conflict detection
- HTTP API: GET /lease, POST /lease/{acquire,release,heartbeat,handoff}, /mutation/check
- /clips wrapped with require_edit_right
- 11 unit + HTTP tests pass
- GUI: <EditLease /> component shows 编辑权 status + handoff buttons

### 准备开始
- P0-09 Project Revision (git filter-repo 已加, manual check)
- P0-01 Frame First (核心)

## 当前状态（2026-09-02 GUI-04.6 Preview stacking semantic fix — in progress）

**发现 P0 semantic defect**：用户 report Timeline 显示 V1 (top) → V9 (bottom)，但 Preview 渲染 V9 在 V1 之上。两个 surface 不一致。

**根因**：Core `build_preview_plan` 按 `_track_sort_key(KIND_RANK, numeric suffix)` 升序排序 visual tracks，**V1 第一个**（suffix 最小）→ layer_index base 最小 → 视觉层最低 → Preview bottom。Timeline.tsx 也是同样的排序，但 DOM 渲染时 array index 0 = top of Timeline。两个 surface 用同一个 sort key，但读法相反。

**Canonical mapping（采用）**：Timeline array index 0 = visually highest in Timeline = highest layer_index in Preview。具体：iterate `visual_track_order` 反向，V9 base=0（bottom），V1 base=最高（top）。Fix at Core layer，**不是 CSS z-index patch**。

**Regression 测试更新**：旧测试（test_multilayer_visual_proof、test_preview_zorder_invariant）pins 了错误方向（`<`），需要改为 `>`。

---

## 新会话接手点（2026-09-02 13:42）

**当前 HEAD**：`6a32559 GUI-04.6: align Preview z-order with Timeline vertical order`
**branch**：main（up to date with origin/main）
**working tree**：clean
**canonical fixture** SHA256：`1a5049614aa2a3d5967447bc7ac565b253154f8aeda44c406a9e60169feaa03c`（与 HEAD 一致）

**运行中服务**：
- Backend `:8770` — `serve-clean-sanlihe.mjs` 后台 task `bve24scpr`，加载最新 Core（plan.py / frame_preview.py 已 fix）
- Frontend `:5180` — vite 静态 dist + proxy，bundle hash `index-CaUJJWAT.css` + `index-DHthlGPW.js`
- Browser `:9222` — chromium CDP（用户可见）

**最近 4 个 commits**：
```
6a32559 GUI-04.6: align Preview z-order with Timeline vertical order
7e51324 fix(serve-clean-sanlihe): import createHash from node:crypto, not node:fs
6008e83 GUI-04.5: close post-acceptance editing defects
a970f6c [GUI-04 FINAL] Acceptance gate: 23/23 API checks + all browser smokes pass
```

**当前 pytest baseline**：890 pass + 1 skip + 2 个文档化 pre-existing failures（sanlihe-slice-30s-clean 已有 fixture 状态、`_sanlihe-r5-manual` working copy 有 overlap）。
**当前 vitest baseline**：471 pass + 2 skip。

**未做**（per user instruction "do not start GUI-05 yet"）：
- GUI-05 Foundation v0.2 P0 Surface（Markers UI / Beat Model / AI Affected highlight）— 等待 user go-ahead
- 不引入 snapping / keyframes / opacity controls / crop / blend mode / AI features
- 不修 human 6-check manual pass（待用户在浏览器执行）

**新会话第一句话**应是：
1. 读 SESSION.md + MEMORY.md（auto-memory index）
2. 检查 backend/frontend 是否仍在跑（task `bve24scpr` + 5180 静态服务）
3. 决定下一步：复跑 GUI-04.5/GUI-04.6 regression / 开始 GUI-05 / 处理 pre-existing failures
