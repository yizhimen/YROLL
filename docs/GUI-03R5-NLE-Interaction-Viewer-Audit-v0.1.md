# GUI-03R5 NLE Interaction & Viewer Stabilization Audit v0.1

**Date**: 2026-08-31
**Branch**: main @ f07df9a (post GUI-03R4.1)
**Scope**: Audit-only. **No code changes.**
**Spec**: user-reported issues from R5 batch start; trace findings + 3–5 batch plan.

---

## Executive summary

GUI-03R4 shipped the NLE Editing Surface (R4-1..R4-7). GUI-03R4.1 added
human reliability (auto-scroll, clean fixture, selection chain, fit-content,
unified geometry, multi-layer proof). R5 finds that **the user's
end-to-end editing loop is still leaky** in 4 places — race window on
mutation, drag coordinate amplification, Viewer too small, and contextual
editing buttons misplaced — even though every individual commit "passes its
own tests". The pattern: pieces are correct in isolation; the assembly is
not yet an NLE.

The 5-batch plan at the end of this document fixes the assembly.

---

## A. Session readiness

### A.1 Trace

```
App mount (App.tsx:1077)
└─ <div className="app"> renders
   └─ useEffect (App.tsx:435-439)
      ├─ sessionStore.initLocal()              ← sync: read sessionId from localStorage (or null)
      └─ sessionStore.startPolling()
         └─ void tick()                         ← fires immediately
            ├─ await sessionStore.refresh()      ← HTTP /ui/status (mine? owner?)
            └─ if (!mine && (!alive || owner==="free"))
                 └─ await sessionStore.acquire() ← HTTP /lease/acquire (mints sessionId)

[meanwhile, AssetPanel mounts, Timeline mounts, ClipBlocks mount]
[user drops an image → AssetPanel.onAssetDrop → App.onAssetDrop → api.addImageClip]
└─ api.addImageClip → mutate("POST", "/clips", body)
   └─ gated(path, init)
      ├─ currentGate() → { sessionId: null, baseRevision: 0 }   ← if pre-acquire
      ├─ URL.searchParams.set("baseRevision", "0")
      └─ fetch(...)
         └─ Server: 403 "sessionId required for mutations"
```

### A.2 Race window (measured)

- `initLocal()` is sync — returns immediately with `sessionId = localStorage.getItem("yroll.session.v1") ?? null`.
- `startPolling()` schedules `tick()` immediately. The first tick does
  `refresh()` (~30-80ms one-way HTTP) then `acquire()` (~30-80ms more).
- During that ~60–160ms window, `sessionStore.get().sessionId` is `null`
  for a fresh tab, or stale for a reloaded tab.
- `currentGate()` (session.ts:269) reads the singleton directly:
  ```ts
  const s = sessionStore.get();
  return { sessionId: s.sessionId, baseRevision: s.revision };
  ```
- `gated()` (api.ts:200-204) sets `baseRevision` even if `sessionId` is null:
  ```ts
  if (sessionId) url.searchParams.set("sessionId", sessionId);
  url.searchParams.set("baseRevision", String(baseRevision));
  ```
  → server gets `?baseRevision=0` with no `sessionId` → middleware `_MutationGateMiddleware`
  raises 403 "sessionId required for mutations".

### A.3 User-reported symptom

> "Dropping image/video can reach GateRejection: sessionId required for mutations."

This is exactly the A.2 race: a user who clicks fast enough (or whose
network is slow) lands a `POST /clips/add_image` before `acquire()` resolves.

### A.4 No UI gate

```bash
grep -nE "sessionStore.loaded|sessionStore.gateError|disabled" gui/src/App.tsx
# → no matches
```

The AssetPanel drop handler (App.tsx:1699), Timeline drop-zone (App.tsx:1718),
ClipBlock drag (ClipBlock.tsx:226), batch panel buttons (App.tsx:1322,1337)
all fire mutations WITHOUT consulting `sessionStore.loaded && mine`.

### A.5 Per-component checks

There is currently **one** gate-style guard: `EditLease.tsx` shows a topbar
badge when `gateError != null`, but the badge is reactive (post-hoc)
not blocking (proactive). The user can still click through.

### A.6 Root cause

The session is "always available" — `currentGate()` returns `sessionId: null`
without raising. Two reasonable fixes:

| Option | Description | Trade-off |
|---|---|---|
| **A. EditorReady gate** | `await sessionStore.ensureReady()` before ANY mutation. Components opt-in via a `useMutationReady()` hook that returns `{ ready: boolean, reason?: string }`. The session lifecycle promotes `ready` once `mine && alive && !conflict`. | Cleaner, fewer surfaces. Components must explicitly check `ready`. |
| **B. Auto-acquire on mount** | `useEffect` awaits `sessionStore.acquire()` synchronously. Anything else waits. | Same outcome; couples component mount to a network roundtrip. |

**Recommendation: A.** Single source of truth, explicit guard.

---

## B. Drag session

### B.1 Trace

```
pointerdown on .clip (ClipBlock.tsx:226)
├─ capture startX = ev.clientX        ← viewport-space, ONCE
├─ capture origStartFrame              ← TimelineFrame at drag origin
├─ capture startScrollLeft             ← contentEl.scrollLeft at drag origin
└─ new DragAutoScroll(dragContentEl)
   └─ rAF tick (drag-autoscroll.ts:43) reads lastPointerClientX, mutates contentEl.scrollLeft

pointermove (ClipBlock.tsx:347)
├─ autoScroll.updatePointer(ev.clientX)
├─ pixelDelta    = ev.clientX - startX                            ← viewport-space displacement
├─ currentScroll = contentEl.scrollLeft
├─ scrollDelta   = currentScroll - startScrollLeft                ← content-space scroll delta
├─ totalPixelDelta = pixelDelta + scrollDelta                      ← additive
├─ deltaFrame    = pxPerFrameToFrameDelta(totalPixelDelta, pxPerFrame)
├─ candidate     = origStartFrame + deltaFrame
├─ clamped       = clamp(candidate)                                ← collision-clamp
└─ onDragMove(clip.clip_id, clamped, ghost)

pointerup (ClipBlock.tsx:397)
├─ autoScroll.dispose()
├─ finalScrollDelta = contentEl.scrollLeft - startScrollLeft       ← SAME formula, read after dispose
├─ totalPixelDelta  = (ev.clientX - startX) + finalScrollDelta
├─ deltaFrame       = pxPerFrameToFrameDelta(totalPixelDelta, pxPerFrame)
├─ preSnapFrame     = lastPreviewFrame                              ← authoritative
├─ finalFrame       = preSnapFrame [+ local snap, target re-clamp, max-clamp]
└─ onMoveCommit(clip.clip_id, finalFrame, targetTrackId)
```

### B.2 Invariant check

The user's spec:

> frameDelta = f(pointer displacement from drag origin)
> while viewport scrolling is independent state.

The current implementation computes:

```
deltaFrame = (ev.clientX - startX + contentEl.scrollLeft - startScrollLeft) / pxPerFrame
```

That is, **the pointer displacement and the scroll delta are BOTH folded
into the frame delta**. The result is that the clip's frame tracks the
pointer's position in **content space**, not in viewport space. So:

- Drag right 100px on screen, no scroll → frame advances +100/pxPerF
- Drag right 100px on screen, auto-scroll moves content right 200px → frame advances +300/pxPerF
  → clip's screen position = (origFrame + 300/pxPerF) × pxPerF − scrollLeft
                            = (origFrame × pxPerF) + 300 − (startScrollLeft + 200)
                            = (original screen position) + 100 − 200 = −100
  → the clip is rendered 100px to the LEFT of where the pointer was at
    pointerdown, NOT under the pointer.

That's NOT what the user wants. The user expects the clip to stay under
the pointer during auto-scroll.

### B.3 Two interpretations of the spec

| Interpretation | Math | UX |
|---|---|---|
| **(1) Frame = pointer-only** | `frame = orig + (clientX - startX) / pxPerF` | Clip stays under pointer **if no scroll**. Once scroll kicks in, the clip moves off the pointer (clip's screen position stays still while content scrolls under it). |
| **(2) Frame = pointer + scroll** (current) | `frame = orig + (clientX - startX + contentEl.scrollLeft - startScrollLeft) / pxPerF` | Clip tracks the pointer's content-space position. Clip's screen position moves opposite to scroll direction. |

For an NLE drag, **interpretation (1) is correct**. The clip should stay
visually anchored to the pointer. Scrolling the viewport should NOT
make the clip's frame jump.

The current implementation (interpretation 2) is a hybrid that was a
reasonable guess during P0-1 ("fold content-scroll delta so the clip
frame follows the auto-scroll") but breaks the spec invariant.

### B.4 The fix

```ts
// CORRECT (interpretation 1):
const deltaFrame = pxPerFrameToFrameDelta(pixelDelta, pxPerFrame);
// viewport scroll is independent; the visual rendering pipeline
// (clip.style.left = origFrame * pxPerF - contentEl.scrollLeft) handles
// the screen position automatically — no need to bake scroll into frame.

const up = (ev) => {
  const finalFrame = lastPreviewFrame;  // preSnapFrame, same formula
  // NO scrollDelta added at commit.
};
```

This makes `frameDelta = (ev.clientX - startX) / pxPerF` regardless of
viewport scroll. The clip's screen position is `frame × pxPerF − scrollLeft`;
if the pointer hasn't moved and scroll grew by Δ, the clip's screen
position moves left by Δ — exactly what the user sees and expects.

### B.5 Why this also fixes "clip can disappear"

> "Clip dragging is still visually uncontrollable; clip can disappear
>  even after auto-scroll work."

The current code in `move()` emits `lastPreviewFrame = clamped` to App,
which renders the clip at `clamped * pxPerF`. The clip's screen position
is then `clamped * pxPerF − scrollLeft`. If the user dragged 100px and
the content scrolled 200px, the clip's frame moves +300 (interpretation 2),
which renders as `clamped * pxPerF − (startScrollLeft + 200)`. The clip
is visibly LEFT of where the pointer is — and the user can't see it
because they dragged to the right of the original clip position.

Adopting interpretation 1 makes the clip's frame track the pointer
faithfully and the clip stays anchored under the cursor.

### B.6 B-aux: pixelDelta-to-frameDelta rounding

`pxPerFrameToFrameDelta` (ClipBlock.tsx:47):
```ts
function pxPerFrameToFrameDelta(pixelDelta: number, pxPerFrame: number) {
  return roundHalfAwayFromZero(pixelDelta / pxPerFrame);
}
```

`roundHalfAwayFromZero` is the canonical rounding primitive (GUI-02.4
invariant: Math.round forbidden for edit coords). This part is correct.

### B.7 B-aux: max-frame clamp

```ts
// ClipBlock.tsx:599-607
let maxBoundary = 0;
for (const r of otherRanges) {
  if (r.end > maxBoundary) maxBoundary = r.end;
}
maxBoundary += lenFrames;
if (finalFrame < 0) finalFrame = 0;
if (finalFrame > maxBoundary) finalFrame = maxBoundary;
```

This is a **GUI-side clamp using sibling-end max + len**. It is
defensive (server-side `/move` has its own [0, project_max_frame] guard)
but it caps the drag at the rightmost sibling's end, NOT at the project's
true max frame. Result: a clip dragged into empty territory past every
sibling gets clamped to `max(sibling.end) + len`. That's still correct
behavior — the user can't push it further than "everything else fits" —
but the clamp value `maxBoundary` is silently never updated when the
project grows. The cap doesn't read `Project.max_timeline_frame()`. This
is a separate minor issue; not blocking.

### B.8 Root cause

**The drag-time math folds scroll delta into the frame delta**. The spec
wants pointer-only. The fix is a one-line change to `move()` and `up()`.

---

## C. Viewer layout

### C.1 Trace

```
.app (CSS .app, styles.css:11)
  display: flex; flex-direction: column; height: 100vh;
└─ .topbar (fixed ~40px)
└─ .main (styles.css:20)
   flex: 1; display: flex; min-height: 0;
   ├─ .asset-pane           (flex-shrink: 0; width: assetW)
   ├─ <ResizeHandle>
   ├─ .preview-pane         (flex: 1 1 0; styles.css:22)
   │  display: flex; flex-direction: column;
   │  align-items: center; justify-content: center; background: #000;
   │  overflow: hidden;
   │  └─ <PreviewPlayer>
   │     └─ .preview-stage  (PreviewPlayer.tsx:484)
   │        flex: 1; display: flex; align-items: center; justify-content: center;
   │        width: 100%; height: 100%;
   │        └─ <div style={frameStyle} className="frame">
   │           explicit width × height from ResizeObserver (PreviewPlayer.tsx:441-454)
   │           ├─ .composite-stage (relative; 100% × 100%)
   │           │  └─ <img> / <video> per visual_layer
   │           └─ <div className="composite-subtitle">
   └─ .inspector (width: 260-500px)
└─ <ResizeHandle direction="horizontal">
   └─ <Timeline>  height={timelineH} (default 280, clamp 150-700)
```

### C.2 What takes the space

| Layer | Width | Height |
|---|---|---|
| Topbar | 100% | ~40px |
| Asset pane | assetW (default ~200px) | full row |
| Inspector | inspectorW (260-500px) | full row |
| **Preview pane** | rest of row | **rest of row** |
| Timeline | 100% | 280px (default) |

The preview-pane competes for height against the timeline. With default
`timelineH = 280`, topbar = 40, viewport = 900px:
- main row height = 900 - 40 - 280 = 580px
- preview canvas = min(availW × 16/9, availH) — usually height-bound to ~400px

That's not "NLE-sized". Real NLEs (Premiere, DaVinci) dedicate 50–70% of
vertical space to the viewer.

### C.3 Why ResizeObserver + explicit dimensions aren't enough

The R4-6 ResizeObserver + explicit dimensions (PreviewPlayer.tsx:411-424)
correctly size the canvas inside the stage. The canvas IS the right size
for its container. The container itself is small.

The user's report — "Preview/Viewer is visually far too small; 1:1
becomes large in a way that still does not resemble an NLE Viewer" —
is about the **container**, not the canvas.

### C.4 "1:1 becomes large in a way that does not resemble an NLE Viewer"

At `1:1` aspect (square) on a 16:9 display, the canvas is
`min(availW, availH)` per side. A 1920×1080 layout with preview 1460×400px:
- 16:9 canvas → 400×225px (height-bound, correct)
- 1:1 canvas → 400×400px (still height-bound)
- 9:16 canvas → min(1460, 400×9/16=225) → 225×400px (width-bound)

The 1:1 case shows a 400×400 black square — not "large" — and the rest
of the canvas region stays black, breaking visual continuity. Real NLEs
fill the viewport.

### C.5 Layer definitions (per spec)

The user explicitly named 4 layers:
- **Viewer container** — top-level layout cell containing everything output-related
- **Output Canvas** — the actual rendered frames at the chosen aspect
- **Transport** — play/pause/scrub bar
- **Timeline** — the time ruler + tracks

Currently these are entangled:
- The preview-pane contains Viewer + Canvas + Transport (Transport is
  `.preview-progress` inside `.preview-pane`).
- Timeline is a sibling of the preview-pane, sharing vertical space.
- Asset pane and Inspector are also siblings of the preview-pane.

### C.6 Root cause

**The 4 layers (Viewer / Output Canvas / Transport / Timeline) are not
independent layout cells**. They share flex containers and the Timeline
"steals" vertical space from the Viewer via the horizontal resize handle.
The Viewer also contains the Canvas, Transport, and zoom/aspect chrome
in a single column, with no separation between them.

---

## D. Multi-layer preview Viewer

### D.1 Trace

```
PreviewPlayer mounts → usePreviewPlan(timelineId) polls /preview/plan → plan.layers
FrameClock ticks → currentFrame(clock) → playheadFrame
composite = activeLayerAt(plan, playheadFrame)   // preview-plan.ts
└─ visual_layers: [PreviewLayer, ...]
└─ audio_layers, subtitle_texts
└─ is_black: boolean

<composite-stage> render:
  .filter((l) => l.kind === "image").map(<img absolute inset:0 width:100% height:100% zIndex:layer_index>)
  .filter((l) => l.kind === "video").map(<video absolute inset:0 width:100% height:100% zIndex:layer_index>)
```

### D.2 What works

- `/preview/at_frame` returns the right visual_layers (proven by
  `tests/test_multilayer_visual_proof.py`: 8/8 pass).
- layer_index is globally unique (R4-1 invariant).
- Hidden tracks are excluded (R4-1 invariant).

### D.3 What doesn't work — V2 covers V1 completely

All visual layers use:
```css
position: absolute; inset: 0; width: 100%; height: 100%;
objectFit: contain; zIndex: layer_index;
```

Every layer fills the entire output canvas. The topmost layer (highest
layer_index) sits on top. Lower layers are OBSCURED — they render
beneath the top layer but the top layer is opaque, so the user sees
ONLY the top layer.

For Sanlihe's editorial story this is fine — V1 carries the main
video, V2 carries occasional B-roll that REPLACES V1. The "V1 + V2 + V3
coexist and render simultaneously" requirement (P1-7) means the
test confirms they all exist in `/preview/at_frame`, but the rendered
DOM shows ONLY the top one.

### D.4 The user complaint

> "Multiple visual tracks still do not produce a reliably understandable
>  multi-layer Viewer result."

In an NLE:
- Premiere / DaVinci: lower layers are partially visible through
  upper layers via opacity or scale. The user can SEE that V1 and V2
  are both there even when V2 is on top.
- CapCut: V2 is shown as a PiP overlay, smaller and offset.
- After Effects: blend modes.

YROLL today: V2 completely covers V1. There's no way for the user to
verify "yes, V1 is still underneath" without checking /project.

### D.5 Verifying actual rendering

Per the user's spec, /preview/plan alone is not proof. I would verify
actual rendering with a Playwright + CDP test:
- Load a deterministic V1+V2+V3 fixture
- Confirm the DOM has 3 `<video>` / `<img>` elements at the same z-stack
- Confirm opacity/scale indicators reveal the lower layers

### D.6 Root cause

**The composite-stage treats all visual layers as full-canvas overlays
without any affordance for "lower layers must be visible to the user"**.
The fix is a multi-layer visualization rule:

| Approach | Behavior | Trade-off |
|---|---|---|
| **(a) Tint indicator** | Each layer gets a small track-id badge in its corner (e.g., "V1", "V2"). Layers still cover but the user sees them. | Cheap, no behavior change. Doesn't address "feel". |
| **(b) PiP upper layers** | Top layer (highest layer_index) rendered smaller (e.g., 30% scale) and offset (bottom-right). Lower layers fill the canvas. | Real NLE feel; needs per-layer transform. |
| **(c) Cycle on click** | Click the Viewer to step through: V1 only → V1+V2 → V1+V2+V3 → V2+V3 → V3 only → all. | Cheap; loses the "composite" sense. |
| **(d) Blend alpha** | Each upper layer is multiplied by α (e.g., 70% for V2, 50% for V3). | Visually immediate; editorial decision. |

**Recommendation: (b) PiP for upper layers, plus (a) track-id badges**.
Both are addressable from a single rule in `composite-stage` style +
visible label overlay. Editorial intent for "cover" can override via
`clip.transform.scale === 1.0` (existing transform field).

---

## E. Contextual editing inventory

### E.1 Top-level buttons in `.topbar` (App.tsx)

| Button | Line | Action | Verdict |
|---|---|---|---|
| 缩放 slider | 873 | Set pxPerSec | ✅ KEEP (global viewport) |
| **批量关闭间隙** | 871 | Close gaps on all visible tracks | 🚚 MOVE → context menu on track header |
| 适配内容 | 882 | Fit Content zoom | ✅ KEEP (global viewport) |
| 渲染预览 | 898 | Start render job | ✅ KEEP (global action) |
| 烧录字幕 | 921 | Toggle burn-in | ✅ KEEP (export option) |
| 存版本 | 934 | Commit version | ✅ KEEP (global action) |

### E.2 Right-click context (already implemented)

- `Timeline.tsx:711`: right-click on empty track-content → "Close Gap here" via
  `onContextMenu` handler that finds the gap containing the click point.
  ✅ Already contextual (per-gap).

### E.3 Inspector single-clip (App.tsx:1356+)

| Button | Action | Verdict |
|---|---|---|
| 删除 (line ~1459) | `api.removeClip` | ✅ KEEP (contextual to selected clip) |
| Ripple (line ~1486) | `api.removeClip(clip_id, why, true)` | ✅ KEEP (contextual) |
| 在播放头切分 (line 1443) | `api.split` | ✅ KEEP |
| M/L/H (trim) | `api.trim` | ✅ KEEP |

### E.4 Batch panel (App.tsx:1293)

| Button | Action | Verdict |
|---|---|---|
| 全部删除 (1322) | `api.deleteSelection` (preserve gap) | ✅ KEEP (contextual to selection) |
| Ripple (1337) | `api.deleteSelection(ripple=true)` | ✅ KEEP |
| 取消多选 (1350) | Clear selection | ✅ KEEP |

### E.5 What's wrong with "批量关闭间隙"

The button at App.tsx:871-881:
```tsx
<button title="批量关闭当前可见轨道的所有间隙（每条轨道一个 Operation）"
  onClick={() => {
    const ids = (activeTl?.tracks ?? []).filter((t) => !t.hidden).map((t) => t.track_id);
    onCloseGapsBatch(ids);
  }}>
  批量关闭间隙
</button>
```

It works on **all visible tracks** — a global action. In an NLE:
- Per-track gap tools belong on the track header (right-click).
- "Close all gaps in project" might belong in a Tools menu, not topbar.

Per user spec: "Batch Close Gaps is currently surfaced as a top-level
button; this should become contextual/right-click gap tooling."

### E.6 Proposed mapping

| Action | Where it lives today | Where it should live |
|---|---|---|
| Close Gap (single, this gap) | right-click on track empty area | ✅ already correct |
| **Close All Gaps (this track)** | topbar button (global) | **right-click on track header** |
| **Close All Gaps (all tracks)** | topbar button (global) | **Track dropdown menu** or **Tools menu** |
| Ripple Delete (selection) | batch panel + Inspector | ✅ already contextual |
| **Ripple Delete (single clip)** | Inspector | ✅ already contextual |
| **Track cleanup** | implicit (W-B auto-cleanup on last clip removal) | (no UI needed) |

### E.7 Root cause

**The topbar carries a per-track editing action as a global button**.
The fix is small:
1. Remove the `批量关闭间隙` topbar button.
2. Add a right-click context menu on `.track-label-row` with: "Close all gaps in this track" + existing mute/lock/hide actions consolidated.
3. (Optional) Add a Track menu in topbar with "Close all gaps in all tracks" as a less-prominent option.

---

## Findings → 3-batch implementation plan

Each batch is a single PR. The plan preserves the existing invariants
(R4-1 layer_index unique, R4-2 hidden-track extent, R4-3 unified geometry,
R4-5 close gap chain, R4-7 multi-layer coexistence test) and adds
behavior without changing data model.

### Batch 1 — Session readiness + drag invariant (P0)

**Goal**: Close the two mutation-blocking bugs (A + B).

**Files**:
- `gui/src/session.ts` — add `ensureReady(): Promise<void>` that resolves once `loaded && mine && alive && !conflict`. Add `ready: boolean` to `ProjectSession`.
- `gui/src/App.tsx` — `useEffect` on mount calls `await sessionStore.ensureReady()`. Show "准备编辑器…" overlay until ready.
- `gui/src/api.ts` — `mutate()` and `gated()` await `sessionStore.ensureReady()` before issuing the request. If the user clicks something during the wait, the call queues (or surfaces a "session not ready" status).
- `gui/src/components/ClipBlock.tsx` — drag `move()` and `up()` revert to pointer-only frame math (interpretation 1). `startScrollLeft` is no longer used in frame math; it's used only by the visual rendering pipeline.
- `gui/src/components/AssetPanel.tsx`, `gui/src/components/Timeline.tsx`, `gui/src/App.tsx` — drop handlers check `sessionStore.ready` and bail with a status message otherwise.
- `gui/src/EditLease.tsx` — already shows gateError, extend to show "准备中…" when `!ready`.

**Tests**:
- New `gui/src/session.test.ts`: `ensureReady` resolves once `refresh` + `acquire` complete.
- New `gui/src/components/ClipBlock.test.tsx` case: drag with mocked scroll change. Assert frame = pointer-only delta.
- New `gui/smoke/03r5-session-drag.mjs`: Playwright + CDP — drop an image before `acquire` resolves, assert it either queues or surfaces a "准备中" status, not a 403.

**Out of scope**: server-side gate changes; new Mutation Gate branches.

### Batch 2 — Viewer layout split (P0)

**Goal**: Make the Viewer feel like an NLE Viewer.

**Files**:
- `gui/src/App.tsx` — split `.app` into:
  ```
  .topbar
  .viewer-region  ← flex: 1; display: column
    ├─ .viewer-toolbar  ← play/pause/scrub + aspect + zoom (existing chrome)
    ├─ <Viewer>          ← flex: 1; the actual canvas region
    └─ <Transport>       ← progress bar (separated from Viewer)
  .timeline-region  ← Timeline + resize handle (already separated)
  .panels           ← asset + inspector row (already exists)
  ```
  Move the Timeline resize handle from `.preview-pane` boundary to `.timeline-region` boundary.
- `gui/src/components/PreviewPlayer.tsx` — drop the `width: 100%; height: 100%` defaults on `.preview-stage`; let the parent control height.
- `gui/src/styles.css` — `.viewer-region { flex: 1; min-height: 0; display: flex; }`, `.viewer-toolbar { height: 32px; flex-shrink: 0; }`, `.preview-pane { flex: 1; min-height: 0; }`.
- `gui/src/components/PreviewPlayer.tsx` — the transport progress bar at `.preview-progress` moves to its own component if needed; or stays inline but gets a fixed height row in `.viewer-region`.

**Tests**:
- New vitest: `ViewerLayout.test.tsx` mounts the App shell, asserts `.viewer-region`, `.viewer-toolbar`, `<Transport>`, `<Viewer>` are siblings of `.timeline-region` (not nested inside it).
- Browser smoke (Playwright): resize the window to 1280×800 vs 1920×1080; assert the viewer canvas aspect-ratio is preserved AND it visibly fills at least 50% of the row height.

**Out of scope**: feature changes to Viewer (overlay controls, fullscreen toggle). Multi-layer indicators (batch 3).

### Batch 3 — Multi-layer Viewer indicators + PiP (P1)

**Goal**: User can SEE that V1+V2+V3 are all there, even when one covers the other.

**Files**:
- `gui/src/components/PreviewPlayer.tsx` — `<composite-stage>` rule:
  - For each visual_layer with `layer_index < max_layer_index`: render at full size with a small track-id badge (e.g., top-left "V1") and a 1px outline in a per-track color.
  - For the topmost layer: render at full size by default; if `clip.transform.scale === undefined`, apply PiP defaults (30% scale, bottom-right, 8% margin). Track-id badge optional for top.
- `gui/src/components/PreviewPlayer.tsx` — the badge component is a tiny inline `<div style={{position:'absolute', top:6, left:6, padding:'2px 6px', background:'rgba(0,0,0,0.6)', color:'#fff', fontSize:11, borderRadius:3}}>{layer.track_id.toUpperCase()}</div>`.
- `gui/src/styles.css` — per-track badge colors (V=yellow, A=green, T=blue).
- `gui/src/preview-plan.ts` — extend `PreviewLayer` with optional `transform` passthrough (already on `clip.transform`).

**Tests**:
- Update `tests/test_multilayer_visual_proof.py` (currently asserts `/preview/at_frame` payload): add browser-level assertion via Playwright that 3 `<video>`/`<img>` elements render with 3 distinct track-id badges visible.
- New `gui/src/components/PreviewPlayer.test.tsx`: render with a fake composite; assert the topmost layer has `style.transform` containing scale (PiP) and at least one badge is visible.

**Out of scope**: blend modes, opacity controls, drag-to-resize PiP (already partially implemented as `pip-drag-box`).

### Batch 4 — Contextual editing toolbar (P1)

**Goal**: Move "Batch Close Gaps" off the topbar; add right-click on track header.

**Files**:
- `gui/src/App.tsx` — REMOVE the `批量关闭间隙` topbar button (line 871-881).
- `gui/src/components/Timeline.tsx` — add `onContextMenu` to `.track-label-row` (the header):
  ```tsx
  e.preventDefault();
  showTrackContextMenu(track.track_id, e.clientX, e.clientY);
  ```
  New `showTrackContextMenu(trackId, x, y)` state: render a positioned menu with:
  - "关闭本轨道所有间隙"
  - "隐藏/显示轨道"
  - "锁定/解锁轨道"
  - (audio only) "静音/取消静音"
  - "删除空轨道"
- `gui/src/App.tsx` — wire the menu items to existing `onCloseGapsBatch`, `onTrackHide`, `onTrackLock`, `onTrackMute` callbacks (already exist).
- `gui/src/styles.css` — `.track-context-menu` positioned absolute, dark background, 1px border, hover highlight.

**Tests**:
- New vitest: `Timeline.context-menu.test.tsx` — render Timeline, simulate right-click on a track-label-row, assert the menu appears with the expected items. Click "关闭本轨道所有间隙", assert `onCloseGapsBatch([track.track_id])` was called with ONE id (not all tracks).
- New browser smoke: Playwright right-click on v1 track header → menu → click → verify Core recorded ONE `close_gap` op for v1 only.

**Out of scope**: a "Close all gaps in project" option (could be a Tools menu in batch 5+).

### Batch 5 — Optional: snapshot test of the layered Viewer (P2)

**Goal**: Lock the multi-layer rendering as a visual baseline.

**Files**:
- New `gui/src/components/__snapshots__/PreviewPlayer.multilayer.test.tsx.snap`
- New `gui/src/components/PreviewPlayer.multilayer.test.tsx` — renders with a 3-layer fake composite; jest/vitest snapshot of the DOM.

**Out of scope**: pixel-perfect image diffs (would require Playwright + image comparison, too heavy for v0.1).

---

## Estimated impact

| Batch | Files changed | New tests | Risk | Out-of-scope reaffirmation |
|---|---|---|---|---|
| 1. Session + Drag | ~6 | ~6 | Medium (mutate() awaits; drag math change) | No Publish Metadata, Keyframes, Timeline-local Revision |
| 2. Viewer split | ~4 | ~3 | Low (CSS + component split) | No new Viewer features |
| 3. Multi-layer indicators | ~3 | ~3 | Low (CSS + render rule) | No opacity controls, no blend modes |
| 4. Contextual toolbar | ~4 | ~3 | Low (UI move, no behavior change) | No new editing actions |
| 5. Snapshot baseline | ~2 | ~1 | Very low | n/a |

**Total**: ~19 files, ~16 new tests. 5 batches × ~1 PR each.

---

## What we explicitly are NOT doing in R5

Per user instruction, the following are deferred:

- Publish Metadata (cover, title, body, tags, platform_overrides)
- Timeline-local Revision (Project global remains authoritative)
- Keyframes (frame-by-frame parameter animation)
- Advanced effects (blend modes, opacity, masks)
- New AI features (subtitles regeneration, asset generation)
- Asset panel redesign
- Track header resize handle changes
- Help dialog rewrite (already on the W-D fix list)

These all belong in R6+ once R5's stabilization lands.

---

## Open questions for the user

1. **Multi-layer visualization rule** — Batch 3 proposes PiP + badges.
   Acceptable, or do you want blend modes / cycle-on-click / something
   else?
2. **Drag-time pointer-only** — Batch 1 changes interpretation 2 →
   interpretation 1. Confirm that's the intended UX (clip stays under
   pointer, content scrolls under it during auto-scroll).
3. **"Close all gaps in all tracks"** — Batch 4 only puts the per-track
   action in the context menu. The "all tracks" action gets dropped.
   Acceptable, or do you want a Tools menu entry?
4. **Default timelineH** — currently 280px. After Batch 2 the Viewer is
   bigger, but if the user has a small monitor the Timeline may feel
   cramped. Should the default drop to 200, or stay 280?

End of audit v0.1.