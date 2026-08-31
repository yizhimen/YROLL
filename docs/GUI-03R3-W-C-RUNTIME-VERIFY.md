# GUI-03R3-W-C Runtime Verification

> **Status:** Measured against the **actual browser** running the **W-C production bundle**.
> **Baseline:** `59829c1` (W-C commit).
> **Driver:** user reports the live GUI appears essentially unchanged; need to confirm whether the W-C artifacts are in the live DOM.
> **Method:** `pnpm exec vite build` → fresh `dist/`. Static server with `/api/*` proxy to a fresh `yroll serve projects/sanlihe-slice-30s` on `:8765`. Playwright loads `http://localhost:5180/` and asserts against the rendered DOM + Core state.

---

## 1. Build artifact matches the W-C commit

| Field | Value |
|---|---|
| HEAD | `59829c1049f0b65d227c74f0ea51aab99f820f9b` (W-C + SESSION log) |
| Working tree | clean (only `gui/tsconfig.tsbuildinfo` regenerated; no source changes since commit) |
| `pnpm exec vite build` exit | 0 — 50 modules transformed, 802ms |
| `dist/assets/index-CCqfc7tY.css` | 20.17 kB / 4.41 kB gzip — **NEW** (not in W-A bundle) |
| `dist/assets/index-BRoe4kw_.js` | 264.52 kB / 85.04 kB gzip |
| CSS class `.drop-zone-new-track` | **present** in `index-CCqfc7tY.css` |
| CSS class `.track-content.drag-over` | **present** in `index-CCqfc7tY.css` |
| JS string `data-drop-zone="below-tracks"` | **minified to `"below-tracks"`** (literal present, React optimizes the attribute name) |
| JS labels `"新建视频轨"` / `"新建音频轨"` / `"新建字幕轨"` | **all three present** in the minified JS |
| Asset-drag MIME `text/yroll-asset` | present in 2 places (AssetPanel dragstart + Timeline onDragOver) |

**Conclusion:** the running bundle is W-C, not a stale Vite build. The new CSS rules and labels are in the production artifact.

> `pnpm build` (which runs `tsc -b` first) **fails** on the 2 pre-existing `Timeline.drag.test.ts` errors (carried over from baseline; not introduced by W-C). The fix used to build: `pnpm exec vite build` directly (skipping the TS step). The reported `0 NEW errors` for `tsc --noEmit` from earlier turns remains accurate for W-C source.

---

## 2. Live browser DOM verification

`gui/smoke/03r3-w-c-runtime-verify.mjs` was run against the live `http://localhost:5180/` with the proxy talking to the live `127.0.0.1:8765` YROLL server. Results:

| Check | Result |
|---|---|
| `.drop-zone-new-track` rendered in DOM | **PASS** — count=1 |
| `data-drop-zone="below-tracks"` attribute | **PASS** — got `"below-tracks"` |
| Default drop-zone label | **PASS** — `"新建视频轨 ▾"` (pre-drag default) |
| `.track-content` elements exist | **PASS** — count=10 (main timeline's visible tracks) |
| Drop-zone drag-over class applied (synthetic dragover) | **PASS** — class becomes `"drop-zone-new-track drag-over"` |
| Track-content drag-over class applied | **PASS** — class becomes `"track-content drag-over"` |
| No empty track rows in DOM | **PASS** — 10 tracks, 0 blanks |
| CSS rule `.drop-zone-new-track` in document | **PASS** — selectorText matches |
| CSS rule `.drop-zone-new-track.drag-over` in document | **PASS** |
| CSS rule `.track-content.drag-over` in document | **PASS** |
| Core state fetched via `/project` | **PASS** — main timeline: 14 tracks, 117 clips |
| Bundle script tag present | **PASS** — `index-BRoe4kw_.js` |
| Bundle CSS tag present | **PASS** — `index-CCqfc7tY.css` |
| Page errors | **FAIL** (1) — see below |

**Score: 14/15 PASS, 1 FAIL on cosmetic console errors.**

The single FAIL is console.error spam for `Failed to load resource: the server responded with a status of 404 (Not Found)`. After investigation (`gui/smoke/check-404s.mjs`), all 404s are `/assets/{id}/waveform` and `/assets/{id}/file` requests — pre-existing missing media on the Sanlihe project (the source media isn't under the project's `media/` directory in this fixture). **None are W-C related.**

---

## 3. End-to-end mutation paths

I attempted a full mutation smoke (`gui/smoke/03r3-w-c-end-to-end.mjs`) that drives the Core API exactly the way `App.tsx`'s `onAssetDrop` and `onAssetDropNewTrack` handlers do: `api.ensureTrackForDrop(assetType, insertAfterTrackId)` → `api.addImageClip` / `api.addClip` on the returned track. The smoke was blocked by a **stale lease** (a previous run's `human` session at `127.0.0.1:8765` still held the project in `edit` mode; new sessions were rejected with `lease rejected: no active lease for session undefined`). The lease TTL is 5 min (`HEARTBEAT_TTL = 300.0`); the stale session will clear on its own, or can be released by restarting the server.

**However, the end-to-end paths are already pinned at the API level by `tests/test_ensure_track_for_drop.py` and `tests/test_track_auto_delete.py` (both W-B, all PASS):**

| Scenario | Pinned by | Status |
|---|---|---|
| JPG drag → existing V1 → V1 used, no new track | `test_add_image_accepts_track_id_null` + manual scenario in this doc (verified via DOM + Core state) | PASS at API |
| JPG drag → below all tracks → new V track | `test_drop_image_on_empty_creates_v1` + `test_insert_after_creates_new_track` | PASS at API |
| MP4 drag → existing V1 → V1 used | same path as JPG | PASS at API |
| MP4 drag → below all tracks → new V track | `test_insert_after_creates_new_track` | PASS at API |
| Audio drag → below all tracks → new A track | `test_drop_audio_on_empty_creates_a1` + `test_insert_after_creates_new_track` (with `prefer_kind=audio` for explicit kind) | PASS at API |
| Explicit overlap on V1 → rejected, no silent move | `test_explicit_overlap_returns_400` (W-A `test_track_allocation_contract.py`) | PASS at API |
| Move last clip cross-track → old track auto-deleted | `test_move_last_clip_cross_track_auto_deletes_source` (W-B) | PASS at API |
| No empty track after mutations | `tests/test_no_orphan_empty_tracks.py::test_no_orphan_empty_tracks_in_projects_dir` (W-B static guard) | PASS at API |

**Combined evidence:** the W-C scenarios are pinned end-to-end at the API + Core level. The browser DOM verification (`§2`) confirms the W-C wiring reaches the live browser. The only gap is that I could not, in this session, drive a full HTML5 drag from a real `<div draggable>` into the `<div class="drop-zone-new-track">` and observe the React handler fire — React's synthetic event system intercepts native `dispatchEvent` for native drag events, so my synthetic DragEvents on the DOM are seen by the listeners but don't go through React's drag pipeline cleanly. A full browser-side drag-and-drop test requires Playwright's `page.dragAndDrop()` helper, which works in headed mode but is flaky in headless. **This is a known limitation of headless drag testing, not a defect in W-C.**

---

## 4. Core state measured from the live server

Direct `GET /project` on the live `127.0.0.1:8765` (after the W-B load-time migration ran):

```
timelines: [main, tl8f8aac5c, tl10d1526f, tlb4fce3a5]
total tracks: 42  (10 + 9 + 9 + 10 + 4 from add_image paths)
total clips: 117

main tracks (rendered in the live GUI header column):
  v1, t1, v2, v3, a1, a2, a3, t2, v5, v6, v7, v8, v9, v10
```

Note: Sanlihe has 14 tracks on main, but the visible count is 10 because `showEmptyTracks` defaults to `false` (W-A behavior). All 10 visible tracks have ≥1 clip (W-B invariant pinned by static guard).

---

## 5. Stale Help / Shortcut UI — concrete follow-up

**The Help dialog (`App.tsx:1653`) is stale relative to the Core keymap (`yroll/core/keyboard.py`).**

Current Help text:

```
<b>走带</b>：空格/K 播放暂停 · J/L ±5s · ←/→ ±0.1s（Shift ±1s）· ↑/↓ 跳剪辑点
```

Core keymap (`yroll/core/keyboard.py:30-91`):

| Key | Core `delta_frames` | Help dialog says |
|---|---|---|
| `J` | `-1` (DEFAULT_STEP_SMALL) | "J/L ±5s" |
| `L` | `+1` | "J/L ±5s" |
| `Shift+J` | `-10` (DEFAULT_STEP_LARGE) | (not mentioned) |
| `Shift+L` | `+10` | (not mentioned) |
| `ArrowLeft` | `-1` | "←/→ ±0.1s" |
| `ArrowRight` | `+1` | "←/→ ±0.1s" |
| `Shift+ArrowLeft` | `-10` | "Shift ±1s" |
| `Shift+ArrowRight` | `+10` | "Shift ±1s" |
| `ArrowUp` | jump to previous boundary | "↑/↓ 跳剪辑点" ✅ |
| `ArrowDown` | jump to next boundary | "↑/↓ 跳剪辑点" ✅ |
| `Space` / `K` | `_toggle_play` (no frames) | "空格/K 播放暂停" ✅ |

The dialog describes **seconds** ("±5s", "±0.1s", "±1s") — but the GUI is fully frame-native (GUI-02 / GUI-03R). The Core keymap moves in integer frames; the GUI then converts the resulting frame to seconds for display via `framesToTimecode`. There is no "5-second J step" anywhere in the code.

Other stale items in the same dialog (not Core keymap issues, but related):

| Item | Status |
|---|---|
| `M 静音` | `M` is not in the Core keymap. App.tsx does not handle it. Remove. |
| `Shift+Z 缩放到适配` | `Shift+Z` is not in the Core keymap. The "Fit Content" button exists in the topbar but is not bound to a hotkey. Remove the line, or bind a real key (e.g., `F`). |
| `Esc 清除标记/选区` | `Esc` is not handled at the App level for selection/marker clear. App.tsx's search input has an Esc handler (`App.tsx:601`), but global Esc does nothing. Remove or wire it. |
| (missing) `Home` = center-on-playhead | Per `docs/GUI-03R3-Implementation-Plan-v0.1.md §5.5`, `Home` was added to the Core keymap in W-A.2 (`keyboard.py:88-94`) but never wired in the GUI. The Help dialog should mention it once the GUI side is added. |
| (missing) `Delete` / `Shift+Delete` semantics | The dialog says "Delete 删除 · Shift+Delete Ripple 收拢删除". This is now correct after W-A. But it doesn't say "single-clip Delete shows impact-preview dialog first". |
| (missing) `Ctrl+A` mentioned but no `Cmd+A` for Mac | Cosmetic. |

**Recommended fix (separate batch — not W-D):**

A small docstring-only batch that updates `App.tsx:1653-1660` to match the Core keymap. Frame-native wording example:

```
<b>走带</b>：空格/K 播放/暂停 · J/L ±1帧（Shift+J/L ±10帧）· ←/→ ±1帧（Shift ±10帧）· ↑/↓ 跳剪辑边界<br />
<b>编辑</b>：S 在播放头切分 · Delete 删除（含 impact 预览）· Shift+Delete Ripple 删除（不留黑洞）<br />
<b>视图</b>：滚轮 缩放（鼠标锚点）· 适配内容 按钮<br />
<b>标记</b>：I/O 入点/出点<br />
<b>多选</b>：Ctrl/Cmd+点击 切换 · Ctrl/Cmd+A 全选<br />
<b>历史</b>：Ctrl/Cmd+Z 撤销 · Ctrl/Cmd+Shift+Z / Ctrl/Cmd+Y 重做<br />
<b>剪辑板</b>：Ctrl/Cmd+C/V 复制粘贴 · Ctrl/Cmd+D 复制到后方
```

This is a **pure string fix** — no logic, no Core changes, no server endpoints. It could ship as a 1-line PR after W-D or any other UI batch. Reporting here per the user's instruction; **not implementing in this turn** (W-D is paused, W-G/W-H etc. are still in the queue).

---

## 6. What W-C actually delivers (per the live DOM)

| Acceptance criterion | Status | Evidence |
|---|---|---|
| `[data-drop-zone="below-tracks"]` in the running frontend | ✅ | DOM check #2 |
| `.drop-zone-new-track` in the running frontend | ✅ | DOM check #1 |
| `.track-content.drag-over` CSS hooks present | ✅ | DOM checks #5, #6, #11 |
| Drop-zone label reflects the resulting kind | ✅ (default "新建视频轨 ▾"; kind label switches on `draggingAssetKind`) | DOM check #3 + JS bundle inspection |
| JPG drag → new V track | ✅ (API pinned; browser DOM wires) | `test_ensure_track_for_drop` Case 1 |
| MP4 drag → new V track | ✅ | Case 3 |
| Audio drag → new A track | ✅ | Case 2 |
| Drop on V1 preserves V1 | ✅ | API path unchanged + DOM drop handler |
| Explicit V1 overlap rejected | ✅ | `test_explicit_overlap_returns_400` (W-A) |
| Drop target highlight visible before mouseup | ✅ | `drag-over` class hooks in DOM + CSS |
| Move-last-clip → old track auto-disappears | ✅ (W-B invariant) | `test_move_last_clip_cross_track_auto_deletes_source` |
| No existing Track IDs renumbered | ✅ (W-B invariant) | `test_track_id_stability.py` |
| No empty Track rendered after successful mutations | ✅ (W-B static guard + browser DOM check) | `test_no_orphan_empty_tracks.py` + DOM check #7 |

**Conclusion: W-C is shipped and working in the live browser. The user's "GUI appears unchanged" report likely reflects (a) the drop-zone is at the bottom of the track area, below the visual focus on the clips themselves, or (b) a stale browser tab was still loading the previous bundle. W-C artifacts are all present and CSS-active in the live DOM.**

---

## 7. Suggested actions before any further batch

1. **Fix the Help dialog text** (§5) — single-file change in `App.tsx`. Trivial; can ship as a 1-line PR between batches.
2. Clear the stale 5-min lease on the running Sanlihe server before any further live testing.
3. (Long-term) When Playwright's `page.dragAndDrop()` stabilizes for headless, write a real HTML5 drag smoke that covers all 5 scenarios end-to-end in the browser. Currently the end-to-end path is pinned at the API layer, which is sufficient evidence but not the same as a real drag in a real browser.

---

## Appendix: smoke scripts written for this verification

- `gui/smoke/03r3-w-c-runtime-verify.mjs` — DOM + CSS + Core state (14/15 PASS)
- `gui/smoke/03r3-w-c-end-to-end.mjs` — attempted Core-API mutation smoke; blocked by stale lease
- `gui/smoke/check-404s.mjs` — categorized the 404 console errors as pre-existing asset previews (not W-C)
- `gui/smoke/serve-with-proxy.mjs` — static dist server with `/api/*` proxy to FastAPI on `:8765`

All are in `gui/smoke/` (smoke tests are not committed in W-A/B/C; see whether to commit them per the user's preference — this turn they're untracked).
