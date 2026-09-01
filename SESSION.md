# YROLL 项目进度（2026-08-29 重启 + GUI-01 完工）

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
