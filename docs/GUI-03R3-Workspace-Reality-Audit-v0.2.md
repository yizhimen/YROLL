# GUI-03R3 Workspace Reality Audit v0.2

> **Status:** measurement + classification only. **No code yet.**
> **Baseline:** `bd088af` (post-GUI-03R3-2 Timeline Workspace Stabilization, 11/11 browser PASS).
> **Driver:** real Sanlihe browser usage + user-reported complaints after 03R3-2 landed.
> **Companion docs:** `GUI-03R3-2-AUDIT.md` (viewport geometry), `GUI-03R3-Timeline-Workspace-Spec-v0.1.md` (DRAFT spec).
> **Scope:** Timeline Workspace as one *interaction system*. Track header / scroll / drag / select / preview / gaps / keyboard / publish metadata — none in isolation.

---

## 0. TL;DR

03R3-1E and 03R3-2 correctly fix the frame-math and the worst workspace pitfalls (sticky chrome, frame safety, fit-content default, compact controls). The remaining user complaints fall into **three distinct buckets** that the previous audits did not classify:

| Bucket | What it is | Examples |
|---|---|---|
| **A. Real implementation gap** | The wire exists, the server endpoint exists, but the GUI doesn't connect to it — or connects it wrong. | `transportRef` is a dead ref (Space never plays); `Delete` key routes to `jumpBoundary` instead of `delete_selection`; `Timeline.publish_metadata` does not exist; no Close Gap operation; no marquee selection; track-header column is `width: 80px` with no resize handle. |
| **B. Spec'd-but-not-shipped** | The 03R3 v0.1 DRAFT spec already calls for the feature; it just hasn't been implemented because the spec was waiting on user approval. | Explicit-dimension Output Canvas (today: CSS `aspectRatio` magic); Timeline-level publish panel (Inspector only has 属性/历史 tabs); ResizeObserver-driven canvas; draggable preview-progress thumb; `Home` = center-on-playhead. |
| **C. UX-scale problem** | The pipeline works as designed; the user's complaint comes from a scale mismatch (22-min project seen at 30 px/sec, with 80px header). | "Tracks look too sparse" (correct at zoom 1, wrong at zoom 30); "clips disappear from view during drag" (geometry, not algorithm — already in 03R3-2 audit); "header column too narrow" (it's 80px and unresizable → spec gap, not a scale problem). |

The next batch must:
1. Fix the **A** bugs (they are small, safe, and high-visibility).
2. Implement the **B** items the user explicitly listed in their feedback (Output Canvas, Publishing panel, semantic track icons, resizable header).
3. NOT regress the frame-math fixes from 03R3-1E / 03R3-2.

---

## 1. Drag interaction pipeline

**Files:** `gui/src/components/ClipBlock.tsx`, `gui/src/components/Timeline.tsx`, `gui/src/App.tsx` (`onDragMove` / `dragGhost` / `onMoveCommit`).

**State machine** (already correct per 03R3-1E, do not touch):
1. `pointerdown` on a clip → `onSelect(clipId, false, ctrl)` → opens a window-level `move`/`up` pair.
2. `pointermove` → `deltaFrame = roundHalfAwayFromZero(pixelDelta / pxPerFrame)` → `clamp(candidate)` → emit `onDragMove(clipId, clamped, ghostSnap)`.
3. `up` → `preSnapFrame = lastPreviewFrame` → ONE local `snap()` (Core's `/snap` is wrong for short-source clips, per 03R3-1E finding) → clamp the snap target; if it would overlap → `[YROLL-SNAP-ABORTED]`. Cross-track re-clamp if `data-track-id` at pointer-up differs from source. Hard `[0, max(sibling.end)+lenFrames]` clamp on commit.

**What's correct.** Drag preview 1:1 with pointer. Ghost snap line is visual-only. Server-side `[0, project_max_frame]` rejection is the last-line defense. Atomic cross-track move (`api.move(clipId, frame, why, trackId)` in one call).

**What's not.**
- The GUI-side `[0, ...]` clamp uses `max(sibling.end) + lenFrames` as the upper bound, which is a sibling-aware estimate, not the true project max. The server clamps it again, but the GUI can land the visual at a frame that the server will then silently truncate. **Gap (A) — minor:** surface `Project.max_timeline_frame()` to the GUI (the helper already exists in `manifest.py:391`; just needs a `/project` field) and use it.
- No auto-scroll during drag. Already documented in `GUI-03R3-2-AUDIT.md §6`. **Bucket C** at default zoom (Fit-Content on load), **Bucket A** at any other zoom. Out of scope for this audit; tracked separately.
- The "drag feels uncontrollable" complaint is **Bucket C** in 99% of cases — at Fit Content, drag is 1:1 and the user has full visual feedback. The 1% (cross-track drop where pointer ends over a track that was just hidden mid-drag) is an edge case we can defer.

---

## 2. Selection pipeline

**Files:** `gui/src/App.tsx` (`selected`, `selectedSet`, `onSelect`), `gui/src/components/ClipBlock.tsx` (`onSelect(clipId, viaAiZone, ctrl)`), `gui/src/components/Timeline.tsx` (forwards).

**State.**
- `selected: string | null` — single-selection *head* (used for keyboard / inspector / clip-targeted ops).
- `selectedSet: Set<string>` — multi-selection backing (used by batch panel when `size > 1`).
- `onSelect(id, viaAiZone=false, ctrl?)`:
  - `viaAiZone=true` → opens Clip Workspace (Y-axis), single-selects.
  - `ctrl=true` → toggle membership in `selectedSet`.
  - else → replace `selectedSet` with `{id}`.

**What's correct.** Ctrl+click works. Ctrl+A selects all. Batch panel appears when `size > 1` with 统一音量 / 统一速度 / 全部删除.

**What's not.**
- **No marquee selection.** Spec calls for "marquee drag on empty timeline area = multi-select" — not implemented. The user feedback asks for it explicitly. **Gap (A).**
- **Multi-delete always leaves gaps.** `api.removeClip(id, "GUI 批量删除")` is called in a loop with `ripple` defaulting to `false` (App.tsx:1042). There is no batch UI for "delete all and close gaps" — the Ripple button on a single-clip Inspector does this, but multi-select only offers "全部删除" (leaves gaps). **Gap (A) — both the multi-ripple path AND a "close gaps" post-pass are missing.**
- `highlightRel` checkbox toggles "related" highlighting on clips that overlap in time with the selected clip — not a selection feature, but the visual state is gated on `selectedIds.size > 0`. Means Ctrl+A → all clips get a "related" outline (because each is related to all the others). Cosmetic. **Bucket C.**
- Keyboard Delete routes to `delete_selection` via the keymap lookup, but App.tsx:499 lumps `delete_selection` into the `_nudge_playhead_boundary` handler. **See §7 — this is a real bug.**

---

## 3. Track header / layout pipeline

**Files:** `gui/src/components/Timeline.tsx` (.timeline-headers, .track-label-row, TRACK_ROLE), `gui/src/styles.css` (.timeline-headers, .track-label-row, .track-icon-btn).

**Geometry.**
- `.timeline-headers` is fixed at `width: 80px` (styles.css:67). No resize handle. **Gap (A) — user asked for resizable.**
- `.track-label-row` is `height: 56px` (styles.css:77). Three sub-rows: title (kind badge + track_id), buttons (hover-reveal), label.
- TRACK_ROLE labels (Timeline.tsx:77): V1=主画面, V2/V3/V4=B-roll, A1=旁白, A2=音效, A3=环境音, T1/T2=字幕. Fallback per kind.

**Semantic order.** `KIND_RANK: text(0) > video/image(1) > audio(2)`, then numeric-suffix sort (v1 < v2 < v10). Confirmed correct and matches user spec.

**What's correct.** Subtitle → Video → Audio order. Numeric suffix. Empty tracks hidden by default. Compact icon-only mute/lock/hide on hover.

**What's not (per user feedback).**
- **Icons are emoji + text-heavy.** Current: `🔇 / 🔊`, `🔓 / 🔒`, `🚫 / 👁`. User wants **semantic compact icons** (T / ▶ / ♪) and **eye** for visible (not `🚫`). **Gap (A) — visual replacement.**
- **Mute hidden on text tracks** (Timeline.tsx:272). Spec calls for all-track visibility. **Gap (A) — small.**
- **Controls hover-reveal only.** User wants "reduced opacity so state is always apparent, more prominent on hover". **Gap (A) — CSS change.**
- **Header column not resizable.** **Gap (A) — needs a new ResizeHandle on the right edge of `.timeline-headers`** (the existing `ResizeHandle` component is vertical/horizontal only; need a new direction or repurpose).
- **TRACK_ROLE only hardcodes V1/V2/V3/V4, A1/A2/A3, T1/T2.** Any user-created track (`v5`, `a4`, `t3`) falls back to kind label. OK for v0.1.

---

## 4. Scrolling / sticky chrome geometry

**Files:** `gui/src/components/Timeline.tsx`, `gui/src/styles.css`.

**State.**
- `.timeline-content` is the only horizontal-scroll container. ScrollLeft measured in pixels; frames at x=0.
- `.minimap` (sticky top:0) + `.ruler` (sticky top:18) — both stay fixed during vertical scroll. **Correct (03R3-2 P0-2).**
- `.timeline-headers` `overflow-y: auto` with JS-mirrored `scrollTop` from `.timeline-content` (Timeline.tsx:158-160). **Correct (03R3-2 P0-3).**
- `contentWidth = pxPerF * 30 * 60 + 40` (Timeline.tsx:144) — assumed 30-min headroom. Always ≥ viewport width.

**Default zoom.** `pxPerSec = 30` initial; App.tsx:319 runs Fit Content on first project load (one-shot, 200ms after `project` arrives). Slider 1-120 px/sec. **Correct (03R3-2 P1-1).**

**What's not.**
- **No auto-scroll during drag.** Already classified in `GUI-03R3-2-AUDIT.md`. Bucket C at fit-content zoom; Bucket A at any other zoom. Out of scope here.
- **`contentWidth` headroom is fixed 30 min.** A user editing a 90-min project will see a scroll bar in the middle of their editing region but the visible content only spans the actual project. Cosmetic, **Bucket C.**

---

## 5. Preview / output-canvas pipeline

**Files:** `gui/src/components/PreviewPlayer.tsx`, `gui/src/styles.css`, `gui/src/App.tsx` (`aspect` state).

**Canvas box.** `frameStyle` uses **CSS `aspectRatio: "16/9"` + `maxWidth: 100%` + `maxHeight: 100%`** (PreviewPlayer.tsx:382-398). Outline `#ffd479 2px` is set (03R3-2 P1-4) so the user can see the canvas edge.

**What's correct.** Aspect switching visibly changes canvas size because aspectRatio + maxWidth/maxHeight does the right thing. The outline makes the boundary obvious. `objectFit: contain` on inner media. Composite stage and progress bar use the canvas / preview-stage as parent.

**What's not (per user feedback).**
- **CSS `aspectRatio` magic, not explicit width/height.** Spec calls for explicit `width` / `height` from a ResizeObserver on `.preview-stage`. The current implementation is responsive but does NOT visibly grow/shrink the canvas when the inspector pane changes width — only when aspect ratio changes. **Gap (B) — needs ResizeObserver + arithmetic on the inner-dimension rule.**
- **Aspect dropdown tooltips are bare** (`title={`${a.w}:${a.h}`}`). User wants platform hints ("横屏（YouTube/B站）", "竖屏（抖音/快手）", "方形（小红书/朋友圈）", "传统电视", "竖版传统"). **Gap (B) — tooltip strings.**
- **Preview progress bar is `pointer-events: none`.** Not draggable. Spec calls for draggable thumb + hover tooltip with frame number. **Gap (B).**
- **No playhead-in-canvas marker.** User wants the preview to "show playback position". Currently the only playhead indicator is the timeline ruler overlay. **Gap (B) — small.** A 1-px vertical line at the playhead frame's normalized x inside the canvas, color-matched to the timeline playhead.
- **L1 composite subtitle has `zIndex: 9999`**, putting it above all chrome. Correct for the *stage* but the PiP-drag-box and the region-mode overlay live at zIndex 5/6; a user trying to drag PiP while a subtitle is visible will have the subtitle intercept. **Gap (A) — small: cap subtitle zIndex to 100 inside the stage, or use pointer-events: none on the subtitle div (it already has `pointerEvents: "none"`, so this is OK actually — verified).** No fix needed.
- **No `pip-drag-box` zIndex conflict.** The PiP box has `z-index: 5` and is inside `.preview-pane`, above `.composite-stage`. Subtitle has `pointerEvents: none`. All good.

---

## 6. Gap / ripple / batch operations

**Files:** `gui/src/api.ts` (`removeClip`, `split`, `move`), `gui/src/App.tsx` (delete buttons + keydown), `yroll/core/commands.py:1214` (`delete_selection`).

**Server surface (already shipped).**
- `api.removeClip(id, why, ripple=false)` → `DELETE /clips/{id}?why=...&ripple=true|false` (api.ts:267-269). Both leaves-gap and ripple variants exist server-side.
- `api.split(clipId, atSource, why)` → `POST /clips/{id}/split`.
- Core `delete_selection(ripple=False|True)` exists in `commands.py:1214`. Single-clip or multi-clip aware.
- Core `split_clip_frame` exists.

**GUI surface.**
- Single-clip Inspector: "删除" button (App.tsx:1165) + "Ripple" button (App.tsx:1179).
  - "删除" → impact preview → confirm dialog (pendingDelete) → `api.removeClip(id, ..., ripple=false)`.
  - "Ripple" → `api.removeClip(id, "GUI Ripple 删除", true)`.
- Multi-select batch panel: "全部删除" button (App.tsx:1038) → loops `api.removeClip(id, "GUI 批量删除")` (always ripple=false).
- Help dialog (App.tsx:1515) lists `Delete` + `Shift+Delete` shortcuts, but see §7 for the routing bug.

**What's not (per user feedback).**
- **No Close Gap operation.** Spec calls for "Close Gap: close an existing empty range". Not implemented in api.ts, not in any button. **Gap (A) — needs `api.closeGap(timeline_id, track_id, start_frame, end_frame)`, a Core command, and a GUI entry point (right-click on empty track region? Or a "Close all gaps in selection" toolbar button?).**
- **No Batch Close Gaps.** **Gap (A) — `api.closeGapsBatch(timeline_id, track_id, ...)` + UI.**
- **Multi-select delete has no ripple option.** **Gap (A) — add a "Ripple Delete" button next to "全部删除".**
- **Snapshots for destructive batch.** Spec calls for preview / confirmation before destructive batch. **Gap (A) — pair Batch Close Gaps with a confirmation dialog showing "N gaps / M total frames will be closed".**

---

## 7. Playback keyboard controls

**Files:** `gui/src/App.tsx` (`useEffect` window keydown at line 426), `gui/src/keymap.ts` (Core keymap client), `yroll/core/keyboard.py` (Core keymap).

**What the Core keymap ships.**
- `Space`, `K` → `_toggle_play`.
- `J`, `L`, `ArrowLeft`, `ArrowRight` → `_nudge_playhead ±1 frame`.
- `Shift+J`, `Shift+L`, `Shift+ArrowLeft`, `Shift+ArrowRight` → `_nudge_playhead ±10 frames`.
- `I`, `O` → `_set_in_out`.
- `S` → `split_clip_at_frame`.
- `Delete`, `Shift+Delete` → `delete_selection(ripple=False|True)`.
- (Also `ArrowUp`/`ArrowDown` as `_nudge_playhead_boundary` is implied in App.tsx but not in the keymap table — minor inconsistency.)

**What the GUI does today.**

| Combo | GUI path | Result |
|---|---|---|
| `Space` | Direct branch (App.tsx:464) | `transportRef.current?.toggle?.()` — **but `transportRef.current` is never assigned** (App.tsx:358 only initializes the ref to `{toggle: undefined}`). **BUG.** |
| `K` | Falls through to keymap lookup, dispatches `_toggle_play` → no branch in App.tsx. **Silent no-op.** |
| `J`, `L`, arrows | Falls through, `binding.deltaFrames !== 0` → `seek(playheadFrame + deltaFrames)`. **Works.** |
| `Shift+J/L/arrows` | Same. **Works.** |
| `I`, `O` | Falls through, `_set_in_out` branch → `setInPoint` / `setOutPoint`. **Works.** |
| `S` | Falls through, `split_clip_at_frame` → `splitAtPlayhead()`. **Works.** |
| `Delete` | Falls through, `binding.name === "delete_selection"` matches the `_nudge_playhead_boundary` branch (App.tsx:499) → `jumpBoundary(1)`. **BUG.** |
| `Shift+Delete` | Same path. Same BUG. |
| `ArrowUp`/`ArrowDown` | Binding name `_nudge_playhead_boundary` (App.tsx:499) → `jumpBoundary(dir)`. **Works** — but this binding is NOT in the Core keymap (`yroll/core/keyboard.py:46-92`). Works only because the GUI synthesizes it. |
| `Ctrl+Z/Y` | Direct branch → undo / redo. **Works.** |
| `Ctrl+C/V/D/A` | Direct branch → clipboard ops / select-all. **Works.** |

**What's not.**
- **Spacebar cannot play/pause.** `transportRef` is dead. The PreviewPlayer owns its own `FrameClock`; the App's keydown handler has no handle into it. **Gap (A) — fix: lift `playing` state into App (or pass a `ref`-less callback prop down to PreviewPlayer and back up). 5-line change.**
- **Delete key does not delete.** `delete_selection` is matched by the wrong branch (it's grouped with `_nudge_playhead_boundary`, which has different params). **Gap (A) — fix: split the dispatch so `delete_selection` reads `params.ripple` and calls `api.removeClip(...)`. 10-line change.**
- **`ArrowUp/Down` binding is not in Core keymap** but works because GUI synthesizes it. Spec calls for it to be in Core. **Gap (B) — small.**
- **No binding for `Home` (Center-on-playhead).** Spec calls for it; not in keymap; not in GUI. **Gap (B).**

---

## 8. Publish metadata model

**Files:** `gui/src/App.tsx` (line 1590: `(project as any).publishing?.title`), `gui/src/components/ExportPanel.tsx` (consumes `initial.title/description/tags`), `yroll/core/manifest.py` (lines 318, 377 — `Publishing` class + `Project.publishing`).

**What exists.**
- `class Publishing` (manifest.py:318): `{video_versions, cover, title, description, tags, platform_copy, cost_report}`.
- `Project.publishing: Publishing = Field(default_factory=Publishing)` (manifest.py:377).
- `ExportPanel.initial` reads from `project.publishing.title / description / tags` (App.tsx:1590-1592).
- **No `Timeline.publish_metadata`** — the spec calls for it but it is **not in the model** (manifest.py:201-221 — `class Timeline` has no publish_metadata field).

**What's not.**
- **Timeline-level publish metadata does not exist.** Duplicate Timeline (03E-4) inherits `Project.publishing` and shares it across all timelines — wrong, per 03R3 §3.2. **Gap (A) — needs Core model + migration + GUI panel + MCP wiring. This is the 03R3-3 batch from the spec; user feedback explicitly asked for it.**
- **No GUI publishing-metadata panel.** Inspector tabs are 属性 / 历史 only (App.tsx:987-1000). No `发布` tab. No Cover picker. No Title / Body / Tags inputs. **Gap (A) — must be added before the user can actually edit per-Timeline metadata.**
- **ExportPanel reads `project.publishing`, not `timeline.publish_metadata`.** Once the Timeline field lands, this read site must change. **Gap (B) — coupled with the Core change.**
- **Cover asset picker / frame scrubber not implemented.** Spec v0.1 picks the clip's start frame; future = scrubber. **Gap (B) — defer scrubber.**

---

## 9. User-reported issues — classified

| # | Report | Verdict | Why |
|---|--------|---------|-----|
| 1 | Clip dragging still feels uncontrollable / clips disappear from view | **Bucket C** | Already audited in `GUI-03R3-2-AUDIT.md` — viewport geometry, not frame math. Mitigated by Fit Content on load. Auto-scroll during drag is a follow-up. |
| 2 | Tracks are visually too sparse | **Bucket C** | The track row is 56 px high with only an 18 px label area at zoom 1. Track-content fills the rest. Sparse = correct geometry at fit-content zoom. If the user is on a tight zoom (Fit Timeline leaves them zoomed-out), they see sparse because the content is. |
| 3 | Multi-select by drag (marquee) is missing | **Bucket A** | Not implemented. Selection pipeline has Ctrl+click + Ctrl+A; no marquee. Spec calls for it. |
| 4 | Ripple / Close Gap / Batch Close Gaps missing | **Bucket A** | Single-clip Ripple button works; Close Gap and Batch Close Gaps are not implemented at all (no API, no UI). Multi-delete always leaves gaps. |
| 5 | Track controls need semantic icons and persistent state indication | **Bucket A** | Today: emoji (🔇/🔊/🔒/🔓/🚫/👁), hover-reveal only. User wants semantic icons (T/▶/♪), eye for visible, persistent at reduced opacity. |
| 6 | Track header column is too narrow and should be resizable | **Bucket A** | Fixed at 80 px. No resize handle. Spec calls for resizable. |
| 7 | Track labels should use compact semantic icons (T / ▶ / ♪) | **Bucket A** | Today: text labels (主画面 / B-roll / 旁白 / 字幕 / etc.). User wants T/▶/♪ icons as the canonical kind label. |
| 8 | Track ordering Subtitle → Video → Audio should remain | **Already correct** | `KIND_RANK` enforces this. 03R3-2 P1-2. |
| 9 | Timeline ruler / header must remain fixed while track body scrolls | **Already correct** | 03R3-2 P0-2 + P0-3. Minimap + ruler sticky-top; headers vertical-sync via JS. |
| 10 | Need a dedicated publishing metadata area for Cover / Title / Body / Tags | **Bucket A** | `Timeline.publish_metadata` does not exist in the model. No Inspector tab. No Core command. |
| 11 | Preview needs to become a clearly bounded Output Canvas | **Bucket B (partially Bucket A)** | Outline is set (03R3-2 P1-4) — boundary is visible. But the canvas uses CSS `aspectRatio` magic, not explicit dimensions + ResizeObserver. The "clearly bounded" requirement is met at aspect-switching time but not at viewport-resize time. |
| 12 | Spacebar must play/pause | **Bucket A** | `transportRef.current` is never assigned. Spacebar is a no-op. |

---

## 10. Recommended implementation batches (NO code yet)

Each batch ends with: pytest clean, vitest clean, tsc clean, Sanlihe scenario subset green, commit + push. Each batch is small enough to ship in one session.

### Batch 03R3-W-A — Quick keyboard + selection wins (P0)
- Fix `transportRef` plumbing so Spacebar plays/pauses PreviewPlayer. (Lift `playing` to App, or pass `onTogglePlay` callback down.)
- Fix Delete-key dispatch — `delete_selection` is currently swallowed by the `_nudge_playhead_boundary` branch. Route it to `api.removeClip(clipId, "GUI Delete", ripple)` and `Shift+Delete` to `api.removeClip(..., true)`.
- Add `Home` key binding = center-on-playhead (scrollLeft = playheadFrame*pxPerF − clientWidth/2, clamped). Add it to Core keymap AND the GUI handler.
- Surface `Project.max_timeline_frame()` to the GUI and use it as the hard upper bound on `finalFrame` (replace the `max(sibling.end)+lenFrames` estimate).
- **Acceptance:** Spacebar plays/pauses, Delete removes (with impact preview), Shift+Delete ripples, Home centers.

### Batch 03R3-W-B — Track header semantic icons + resizable column (P0)
- Replace emoji icons with semantic icons in the header row:
  - Track kind: T (text) / ▶ (video) / ♪ (audio).
  - State icons: 🔊/🔇 (mute), 🔒/🔓 (lock), 👁 (visible — no longer 🚫).
- Show track kind icon + track_id by default; mute/lock/hide at 30% opacity by default; full opacity on hover / focus / state-active. State-active = `active` class (already in CSS) makes them fully opaque + brand color.
- Add `ResizeHandle` (or a new variant) on the right edge of `.timeline-headers`. Persist width in localStorage.
- Mute button visible on all tracks (drop the `track.kind !== "text"` guard in Timeline.tsx:272). Tooltip notes video-mute is informational-only.
- **Acceptance:** Compact icons readable at a glance; column resizable 80-300 px; state always apparent.

### Batch 03R3-W-C — Marquee multi-select on empty timeline area (P0)
- On `pointerdown` on `.track-content` (not on a `.clip`), enter marquee mode. Track `pointermove` to draw a translucent selection rectangle. On `pointerup`, compute the list of clips whose bounding box intersects the rectangle; replace or extend `selectedSet` based on `ctrl` modifier.
- The marquee rectangle is rendered inside `.tracks` (z-index above clip outlines, below playhead).
- Esc cancels; clicking inside the marquee without dragging deselects.
- **Acceptance:** Empty-track-area drag → multi-select. Ctrl+drag → add to selection. Esc → clear.

### Batch 03R3-W-D — Gap operations (Close Gap + Batch Close Gaps + multi-ripple) (P0)
- Core: implement `close_gap(timeline_id, track_id, start_frame, end_frame)` and `close_gaps_batch(timeline_id, track_ids, why)` commands. Server endpoints + GUI api.ts methods.
- GUI: add a "Close Gap" right-click context on empty track-area (or a `…` menu in the track header). Add "Batch Close Gaps" as a topbar button + Inspector batch-panel button (multi-select).
- Multi-select batch panel: add a "Ripple 删除" button next to "全部删除" (uses ripple=true on each).
- Confirmation dialog for Batch Close Gaps showing "N gaps / M total frames to close".
- **Acceptance:** Single Close Gap works. Batch Close Gaps runs across selected tracks. Multi-Ripple delete works.

### Batch 03R3-W-E — Timeline-level publish metadata + Inspector panel (P0)
- Core: add `Timeline.publish_metadata: TimelinePublishMetadata = TimelinePublishMetadata()` field. `TimelinePublishMetadata = {cover, title, body, tags, platform_overrides}`. Migration on read: existing projects get `Project.publishing` copied into each Timeline (one-time).
- Core command: `set_publish_metadata(timeline_id, field, value, why)`. Server endpoint `POST /timelines/{tid}/publish_metadata`.
- GUI: add a third Inspector tab `发布` next to `属性` / `历史`. Cover (asset picker + start-frame readout), Title (text), Body (textarea), Tags (comma-separated). Platform overrides (deferred to a follow-up batch — out of v0.1 scope).
- ExportPanel `initial` reads from `timeline.publish_metadata` (not `project.publishing`).
- MCP / Agent path: same gate, same command.
- **Acceptance:** Editing Cover/Title/Body/Tags in Inspector persists to that Timeline only. Duplicate Timeline now has independent metadata.

### Batch 03R3-W-F — Output Canvas explicit dimensions + ResizeObserver (P0)
- Replace `frameStyle`'s `aspectRatio + maxWidth/maxHeight` with explicit `width` / `height` computed by a `ResizeObserver` on `.preview-stage`. Inner-dimension rule: longest side = min(stageWidth, stageHeight × aspectRatio); other side = longestSide / aspectRatio.
- Add platform tooltips to the aspect dropdown (横屏 / 竖屏 / 方形 / 传统 / 竖版).
- Add a 1-px timeline-playhead marker inside the canvas: vertical line at `(playheadFrame / endFrame) × canvasWidth`, color-matched to the timeline `.playhead-overlay`. Hidden while the user is interacting with the canvas.
- **Acceptance:** Switching aspect visibly resizes the canvas; resizing the inspector pane visibly resizes the canvas; playhead position is visible inside the canvas.

### Batch 03R3-W-G — Draggable preview-progress thumb + hover tooltip (P1)
- Lift `.preview-progress` from `pointer-events: none` to `pointer-events: auto` on the thumb.
- Pointerdown on `.preview-progress-thumb`: track pointermove; compute `frame = (mouseX / barWidth) * endFrame`; call `onPlayhead`.
- Hover (no drag) on `.preview-progress` (not thumb): show a faint tooltip with the integer frame at pointer X.
- **Acceptance:** Drag the thumb → playhead scrubs. Hover → tooltip.

### Batch 03R3-W-H — Sanlihe acceptance run end-to-end (P0)
- Refresh `gui/smoke/03r3-sanlihe.mjs` (already 11/11) with the 03R3-W additions:
  - keyboard: Spacebar play/pause, Delete removes, Shift+Delete ripples, Home centers.
  - track header: column resize persists across reload.
  - marquee: empty-area drag multi-selects.
  - gap ops: Batch Close Gaps on a known gap closes it.
  - publish: Cover/Title save round-trips through `/timelines/{tid}/publish_metadata`.
  - preview canvas: ResizeObserver width tracks inspector width within ±2 px.
- **Acceptance:** N/N green. Update `SESSION.md` to record all 03R3-W batches shipped.

---

## 11. Spec invariants — preserved across all batches

- **1 px = 1 frame at default zoom** (03R3-1E math) — do not change.
- **`previewFrame == finalFrame`** on commit, unless `api.snap` returned non-null (03R3-1E).
- **No same-track overlap ever commits** (03R3-2 P0-1 + server-side `[0, max_timeline_frame]` clamp).
- **One authoritative snap per pointerup** (03R3-1E).
- **Frame-native edit chain** (TimelineFrame / ClipFrame / SourceFrame distinct).
- **No GUI TimeMap business math** (`* clip.speed` / `/ clip.speed` forbidden in ClipBlock).
- **`roundHalfAwayFromZero`** is the only edit-coordinate rounding primitive.
- **Drag preview follows pointer 1:1**; snap is visual-only during drag.

---

## 12. Out of scope (still pinned)

Per user instruction:
- Timeline-local Revision
- nested Timelines
- Keyframes
- advanced effects / transitions
- full `EditorSelection` redesign (we add marquee without rebuilding the model)
- new AI generation features
- cover-frame scrubbing (v0.1 picks clip's start frame)
- cursor-anchor reticle during wheel zoom
- crop fit-mode (`objectFit: cover`)
- per-clip "moment cards"
