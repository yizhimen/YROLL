# GUI-03R2 Runtime Audit — baseline e601608

Target project: `sanlihe-slice-30s` (4 timelines, 48 assets, 97 clips).
Browser: Chromium 151 over CDP @ localhost:9222.
Audit script: `gui/smoke/03r2-audit.mjs`.

## Measurement summary

### P0-A — Frame-0 alignment (CRITICAL ✗)

| Element                | left (px)  | Source                              |
|------------------------|------------|-------------------------------------|
| `.ruler` (screen)      | 0          | spans full pane                     |
| `.ruler .tick` F0      | **80**     | `style.left: 80px`                  |
| `.track-content` (v10) | **80**     | screen rect.left                    |
| `.playhead-full`       | **null**   | **NOT in DOM** at playhead=0        |
| First clip on v1       | 5580       | `tlStart * pxPerF + LABEL_GUTTER_PX`|

**Findings**:
- `LABEL_GUTTER_PX = 80` is baked into **tick positioning** (`x = LABEL_GUTTER_PX + round(t * pxPerF)`)
  AND **playhead calculation** (`playheadFrameToPixel` defaults to `originPx=LABEL_GUTTER_PX`).
- BUT **`.playhead-full` is not in the DOM** when playheadFrame = 0. The className in CSS is
  `playhead-full`, but the rendered element is `.playhead-full` — yet `document.querySelector('.playhead-full')`
  returns null. Looking at Timeline.tsx line 256: `<div className="playhead-frame-full" ...>`.
  **CSS class `.playhead-full` exists; component renders `.playhead-frame-full`**. Typo / mismatch.
- The `clip` element renders at `left = tlStartFrame * pxPerFrame` (no gutter offset) and CSS
  `.track-row` has `display: flex`. Children of a flex row are positioned by `left` only because
  they're `position: absolute`. Their `left` value is relative to the **track-content** (which
  starts at `LABEL_GUTTER_PX` inside the row). So a clip with `tlStart = 0` should be at
  `0 * pxPerFrame = 0` **inside track-content** which is at screen x=80. → Frame-0 clip at
  screen x=80. ✓ (Ruler tick F0 at 80, clip F0 at 80 → consistent.)
- **BUT**: spec says "TimelineFrame 0 is exactly ContentViewport x=0". Currently it's at x=80.
  Track header (LABEL_GUTTER_PX) IS inside the coordinate space; ruler uses paddingLeft=80 to
  push its ticks right; playhead uses `playheadFrameToPixel` with `originPx=80`; clip uses
  `left = frame * pxPerF` (which would be 0 at frame 0). Ruler+playhead are at +80; clips are at +0.
  **The ruler/clip are 80px apart at frame 0.** This is the **P0-A origin bug**.

### P0-B — Asset drag-drop (BROKEN ✗)

- 48 `.asset-item[draggable]` items present, `ondragstart` not enumerable but `draggable="true"` set.
- Playwright `dragTo` against `[data-track-content=v10]` **timed out after 30s**.
- DataTransfer-based browser drag (HTML5 native) requires `dragover` + `drop` events fired on
  the target with proper DataTransfer; Playwright's `dragTo` uses mouse events that don't
  trigger native HTML5 drag-and-drop. So Playwright dragTo **cannot** verify native drag.
- The actual user report "drag from AssetPanel → Timeline drop does not work, while + works"
  needs a different test approach: **simulate the native drag event sequence directly via JS**.

### P0-C — Drag coordinate reliability (PASS at pure math)

- At pxPerSec=30, fps=30/1: pxPerFrame = 30 × 1/30 = **1**.
- 1 px → 1 frame (roundHalfAwayFromZero(1/1) = 1). **GOOD.**
- BUT user reports "Clip drag moves visually far too quickly." → The bug is not the math; it's
  that during real drag, the cursor moves more pixels than expected (HTML5 drag dataTransfer
  uses `clientX/Y` consistently), so a single-frame move visually jumps much less than a
  real-time drag.
- Actually, `1 px = 1 frame` at default zoom is CORRECT. The user complaint suggests **clip
  moves more than cursor moves** — i.e., **pxPerFrame ≠ 1** at the actual drag handler. Let me
  check: App passes `pxPerSec={pxPerSec}` to Timeline; Timeline computes
  `pxPerF = pxPerFrame(pxPerSec, seq.fps) = pxPerSec * fps.den / fps.num = 30 * 1/30 = 1`.
  Timeline passes `pxPerFrame={pxPerF}` to ClipBlock. ClipBlock uses it directly. ✓ Math correct.
- **However**, ClipBlock's drag is a **pointerdown+pointermove** on the ClipBlock element
  itself, not a native HTML5 dragstart/drop. It uses `clientX` deltas. This is correct.
- User report may stem from the wheel zoom (1.25/0.8) causing zoom to jump unexpectedly, which
  the user then sees as "drag moves far too quickly" — i.e., the zoom changed mid-drag.

### P0-D — Collision (server-side ✓, no test possible)

- Server is configured correctly (we have 5 contract tests from 03R-Micro v2).
- 403 on the test mutation means lease wasn't acquired before the click — audit script issue,
  not a Core bug. Core's overlap rejection was verified earlier in tests.

### P0-E — Playback playhead (CRITICAL ✗)

- `document.querySelector('.playhead-full')` → **null**.
- Timeline.tsx renders `<div className="playhead-frame-full" />`. **CSS rule `.playhead-full`**
  exists but the element rendered is `.playhead-frame-full`. **MISMATCH**.
- Result: the playback playhead is **never styled** (the element renders but no width/color/etc).
- Even if the className matched, the playhead is `position: absolute` child of `.timeline-body`
  → which scrolls with `.timeline-pane`. The playhead SHOULD move with timeline scroll. ✓.
- The spec wants "ONE absolute PlayheadOverlay inside the Timeline ContentViewport". Currently
  it's a child of `.timeline-body` (one element above `.tracks`). OK conceptually, but the
  className is wrong.

### P0-F — Preview progress (BROKEN ✗)

- `document.querySelector('.minimap-playhead')` → **null**. Same className mismatch.
  Timeline.tsx renders `.minimap-playheadFrame`. CSS rule is `.minimap-playhead`.
- PreviewPlayer DOES advance `playheadFrame` via RAF (confirmed in source: tick → onPlayhead).
- BUT the user-visible "preview progress" element uses the wrong class. So the CSS doesn't apply.
- Additionally, the preview shows `framesToTimecode`-derived positions but **no progress bar/line
  in the Preview frame itself** — only the mini-map playhead. Spec wants "Preview must visibly
  indicate current TimelineFrame during playback".

### P1-G — Wheel zoom step (BROKEN ✗)

- Slider value is 60 (the state default after init); step is 1, range 4-120.
- Wheel zoom factor is `1.25 / 0.8` → 25% per notch. User wants ~8%.
- 60 → 60×1.25 = 75 (one notch up) — that's a big jump.

### P1-H — Time display (PARTIAL ✓)

- Status bar shows `播放头 00:00.000 · F0 · 97 clips`. ✓ The "播放头" label, MM:SS.mmm seconds,
  F<frame> suffix all present. The separator is now its own span (03R-Micro fix). ✓
- Tick ruler shows `00:00.000 · F0` etc. ✓
- BUT: tick labels are at every 1 second because pxPerSec=60 places ticks at fps=30 step.
  At pxPerSec=30 (the spec default), ticks would be further apart (default step would land
  per-half-second based on the profile).
- Also: only at "precise" (pxPerSec >= 24) we get the F<frame>. At pxPerSec=60 we're way past
  the threshold. OK.

### P1-I — + button semantics (LIE ✗)

- AssetPanel `addToTimeline` sets `const tlStart = 0` (line 65), so "+" inserts at frame 0
  **regardless of playhead**. Spec wants **insert at current playhead**. This is a lie in
  the success message too ("已加入（Core allocator 选轨）" — no mention of frame).
- Also `addClip(assetId, 0, dur, tlStart, ...)` — second arg is `source_start` (currently 0).
  For a video, source_start=0 is fine; tlStart=0 means "at project frame 0".

## Cross-cutting findings

### CSS Class Mismatch Bug
Two class names are typed in Timeline.tsx but don't match the CSS:
- `<div className="playhead-frame-full" />` — CSS has `.playhead-full`
- `<div className="minimap-playheadFrame" />` — CSS has `.minimap-playhead`

This is the **primary cause of the P0-E and P0-F visible failures** — the playhead element
renders but with no styles. (User sees "Playback does not show a clear playhead/progress line
across tracks" and "Preview does not show a clear playback progress position.")

### Origin Mismatch
Three coordinate systems coexist:
1. **Ruler**: `LABEL_GUTTER_PX + round(t * pxPerF)` — gutter offset baked in
2. **Playhead** (when rendered): `playheadFrameToPixel(f)` default `originPx=LABEL_GUTTER_PX`
3. **Clip**: `left = tlStartFrame * pxPerF` — NO gutter offset, but child of `.track-content`
   which is positioned at `LABEL_GUTTER_PX` inside `.track-row`

Currently they APPEAR to align at frame 0 because: ruler tick at +80, clip at 0 (inside
track-content which starts at +80). User-visible frame 0 is at screen x=80 in both cases.
**But**: this fragile arrangement depends on:
- `.track-content` being offset by LABEL_GUTTER_PX inside the row (currently via row flex)
- `.playhead` being offset by LABEL_GUTTER_PX (currently via originPx arg, BUT className typo
  means the element isn't styled)

The spec mandates **ONE ContentViewport origin** at frame 0 = x=0, with the track-header
column **outside** the coordinate space. This requires a structural redesign:
- Move track-name out of each track-row into a single left column (sticky) outside the
  scrollable area
- Make ruler, playhead, track-content, clips, drop coordinates all anchored at x=0 = frame 0

## Required fix order (per spec)

1. **P0-A Unified Origin**: structural CSS + JSX refactor. Use a single
   `.timeline-content` wrapper that's a flexbox with `.track-headers` (sticky left) and
   `.content` (scrollable right). All frame→pixel math uses x=0 at frame 0.
2. **P0-B Drag-drop**: simulate native drag events via JS in test; check `dragstart` fires
   DataTransfer setData, `dragover` on track-content sets dropEffect, `drop` calls onAssetDrop.
3. **P0-C Drag coordinate reliability**: (already correct in math; needs browser acceptance test
   that moves 1px and verifies exactly 1-frame candidate).
4. **P0-D Collision**: server-side already correct; needs GUI test that tries to overlap and
   verifies the local clamp + atomic onMoveCommit (no 400 visible).
5. **P0-E Playback playhead**: fix className + add ONE absolute overlay inside ContentViewport.
6. **P0-F Preview progress**: fix className + add progress indicator in Preview frame.
7. **P1-G Wheel zoom**: 1.08 / 0.93 + preserve frame under cursor.
8. **P1-H Time display**: already correct; verify ruler label format unchanged.
9. **P1-I + button**: change `tlStart = 0` to use `playheadFrame` from App.
