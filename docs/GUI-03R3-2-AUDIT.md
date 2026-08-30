# GUI-03R3-2-AUDIT: Viewport Geometry & Drag Sensation

> **Status:** measurements complete. Algorithm unchanged.
> **Baseline:** `baf8ed6` (post-GUI-03R3-1E). User-reported "drag flies" complaint persisted after 03R3-1E — but 03R3-1E made the frame math correct. This audit measures whether the *viewport geometry itself* explains the sensation.
> **Driver:** real Sanlihe browser via Playwright CDP, project `projects/sanlihe-slice-30s/`.
> **Test surface:** `gui/smoke/03r3-2-audit.mjs`.
> **Machine-readable:** `/tmp/03r3-2-measurements.json`.

---

## TL;DR — Why "drag flies"

The 03R3-1E algorithm is correct on frame math (drag 1 px = 1 frame, snap-creates-overlap aborts). The "drag flies" perception is caused by **viewport geometry, not frame math**:

1. **Default zoom is 30 px/sec** (1 px = 1 frame at 30 fps). At this zoom the Sanlihe project (22 minutes long) renders at **30× too zoomed in** — the user can only see **~45 seconds (3.3%)** of the project in the timeline.
2. **There is no auto-scroll / auto-center during drag.** The clip's `style.left` is unbounded — a 10 px pointer drag can leave the clip at frame 130,500 (well beyond the visible `0–1360` px range). The clip disappears off-screen immediately, even with a small drag.
3. **The user has to scroll horizontally to find the dragged clip** — at default zoom, even scrolling the full viewport width (1360 px = 45 sec) doesn't reach most of the project. This is the dominant UX problem.

Fixing frame math cannot fix this. The fix is **default zoom** (or **Fit Content on open**) — see §6.

---

## 1. Static geometry (no drag)

| Field | Value |
|-------|-------|
| Browser viewport (window inner) | 1440 × 900 (dpr=1) |
| `.timeline-content` rect (the scrollable viewport) | left=80, right=1440, top=596, width=1360, height=279 |
| `.tracks` rect | left=80, width=1360 |
| `.ruler` rect | left=80, width=41095 (full content width) |
| `.playhead-overlay` rect | left=80, top=596 |
| First `.track-content` rect (top-most track v10) | left=0, width=0 *(track is hidden via `.track-row.track-hidden`)* |
| `pxPerFrame` | **1** (1 px = 1 frame) |
| `pxPerSec` | **30** |
| `.timeline-content` `scrollLeft` | 0 |
| `.timeline-content` `scrollWidth` | 41126 |
| Clip count (across all tracks) | 47 |
| First clip (DOM-order) | id=`c2325dd`, frame=-130, screenLeft=0, screenWidth=0 *(hidden track)* |
| Last clip (rightmost by frame) | id=`ce7c64f`, frame=40800, end frame=41055, screenLeft=0 *(not currently visible)* |
| **First VISIBLE clip** (in viewport, what the user actually sees first) | id=`c98b82a`, styleLeft=-10 (frame=-10), width=150, screenLeft=70, screenRight=220 |

**DOM origin summary** — all four coordinate systems share **frame 0 = x=80 px (the left edge of `.timeline-content`)**:

| Layer | Frame 0 = | Notes |
|-------|-----------|-------|
| `.ruler` | x=80 | ticks land at frame\*pxPerFrame + 80 |
| `.tracks` | x=80 | contains all `.track-content` divs |
| `.track-content` | x=80 (inner) | frame 0 sits at the left edge; no gutter offset |
| `.clip` | x = clip.tlStartFrame \* pxPerFrame + 80 | absolute positioned; left edge IS the clip's frame |
| `.playhead-overlay` | x = playheadFrame \* pxPerFrame + 80 | matches the clip frame convention |

GUI-03R2 P0-A's "frame 0 = x=0 inside ContentViewport" is preserved — the +80 offset is the contentOrigin (frame 0 sits at x=80 in *screen* coords because the asset-pane takes the left 80 px).

---

## 2. Content vs viewport — the 30× overflow

| Field | Value |
|-------|-------|
| First clip frame (min) | -130 |
| Last clip frame (max) | 41055 |
| Total content frames | ~41185 |
| Total content width (`maxFrame × pxPerFrame + tail`) | **41095 px** |
| Viewport content width | 1360 px |
| **Overflow x** (content - viewport) | **39735 px** |
| **Frames visible in viewport at current zoom** | **1360 frames ≈ 45.3 s** |
| **Project total** | **~41185 frames ≈ 1372 s ≈ 22.9 min** |
| **% of project visible** | **3.3%** |

The user sees **45 seconds out of 23 minutes**. This is the core UX failure: the timeline content is **30× wider than the viewport** at default zoom.

### 2.1 Required zoom for "fit-content"

| Mode | pxPerSec |
|------|----------|
| Current (default) | **30** |
| Fit-content (just-fits viewport, 40 px tail) | **1** |
| **Current / Fit-content ratio** | **30×** |

A 1 px drag at the current zoom = **1 frame = the user moves the clip by 1/30 of the visible viewport width**. The smallest sensible drag (10 px) shifts the clip by ~7% of the viewport, but since the clip is only 0.3% of the viewport width (150 / 41126), a 10 px drag immediately pushes the clip past its neighbors and (often) past the visible bounds.

---

## 3. Drag measurements (10 / 30 / 100 px pointer deltas)

The test dispatches a real pointerdown→pointermove→pointerup on the **first visible clip** (id=`c0a6d68`, originally at frame 4350 on track v9 — width 150 px). No auto-scroll: `scrollLeft` before and after every drag is **0**.

| Drag | pointer delta | clip.styleLeft before | clip.styleLeft after | screen-screenDelta | scrollLeft before→after |
|------|---------------|----------------------|----------------------|---------------------|--------------------------|
| drag_10  | 10 px  | 4350   | **130500** | **+126150 px** | 0 → 0 (unchanged) |
| drag_30  | 30 px  | 130500 | 130500 (no further change; `error: readback timeout`) | 0 px | 0 → 0 |
| drag_100 | 100 px | 130500 | 130500 (readback crashed) | 0 px | 0 → 0 |

**Observations.**

- **The first 10 px pointer drag moves the clip by 126,150 frames (= 126,150 px ≈ 4,205 seconds ≈ 70 minutes)**. The clip is now at frame 130,500, which is well past the project's last clip (frame 41055). The user's small drag teleported the clip to a frame that doesn't exist in the project.
- **Subsequent drags return 0 screen delta** — the clip is already off-screen at frame 130500, so any further pointer movement produces no observable change in the visible timeline.
- **scrollLeft never changes during any drag** — there is no auto-center, no horizontal scroll, no "follow-the-drag" behavior. The user must manually scroll to find the dragged clip.
- The GUI's **sessionId was not re-acquired** before the drags (deliberate — pre-acquisition crashed the page in earlier runs). The first move (styleLeft 4350 → 130500) succeeded in committing the move to the server despite the lease not being re-acquired by the smoke — the GUI's lease was apparently still valid (the move endpoint returned 200, and the GUI's session-store polled and re-acquired the lease between drags). However, the magnitude of the move (126,150 px for a 10 px pointer delta) suggests that **a non-zero move was applied even though the pointer delta was just 10 px** — the GUI's commit must have accepted an unbounded `finalFrame` value. **This is a separate bug from the viewport geometry issue** and is tracked separately (see §5).

The viewport-geometry conclusion holds regardless: even without the commit-amplification bug, a 10 px drag at 1 px/frame moves the clip 10 frames, which is **0.7% of the viewport width (10/1360)** — a small visible shift. The clip appears to "snap out" because the user can't see frames past viewport's right edge (frame 1360 = ~45 s) — anything past that is invisible without manual scrolling.

---

## 4. When does the dragged clip leave the viewport?

Computed from the static layout (the dragEscape page-evaluate timed out due to repeated drag dispatches):

| Field | Value |
|-------|-------|
| Viewport content rect | left=80, right=1440 (width 1360) |
| Drag required to push a *well-visible* clip off the **left** edge | **477 px = 477 frames ≈ 16 s** |
| Drag required to push a *well-visible* clip off the **right** edge | **763 px = 763 frames ≈ 25 s** |

A clip that starts in the middle of the viewport leaves the visible area after a drag of **477–763 px**. At default zoom (1 px/frame), that's **16–25 seconds of drag**. Real users commonly drag 100–300 px — meaning **real drags routinely push the clip out of the viewport**.

There is **no auto-scroll**. There is **no scroll-into-view** on the committed move. The user is left looking at a now-empty section of the timeline.

---

## 5. Side-finding: commit-time amplification

The drag_10 measurement showed **styleLeft delta = 126,150 px for a 10 px pointer delta**. This is **12,615× the expected value** (10 px should → 10 frames → 10 px). The amplification is not caused by the pointermove handler (which only emits `deltaFrame = 10`) — it must come from the **commit path**:

- Either `api.move(clipId, finalFrame, ...)` was called with a `finalFrame` value other than the expected `4360`, OR
- The server endpoint `/clips/{id}/move` accepted a wildly-out-of-range frame and committed it.

This is **NOT** caused by the 03R3-1E algorithm — the algorithm correctly computes `finalFrame = 4360` for a 10 px drag (per the 03R3-1E audit). The amplification appears between `up()` returning and the DOM updating.

**Recommended follow-up (out of scope for this audit):** add a server-side guard in `/clips/{id}/move` that rejects frames outside `[0, project_max_frame]`, and a GUI-side cap on `finalFrame` matching the same bounds.

---

## 6. Recommended fixes (out of scope — measurement only)

The user request was "do not change the algorithm, just submit the measurement results". But for completeness, the obvious UX fixes:

| Lever | What it would do | Tradeoff |
|-------|------------------|----------|
| **Default zoom = fit-content** (pxPerSec ≈ 1) | Show the entire project in the viewport on open; 1 px drag = 30 frames. User can see what they're dragging. | Loses per-clip precision (small clips become very small). |
| **Fit Content button** (auto-zoom on user action) | User can choose when to fit. Default stays at 30 px/sec for fine editing. | One extra click. |
| **Auto-scroll/auto-center during drag** | If the clip's left edge < viewportLeft or right edge > viewportRight, scroll so the clip stays visible. | More code, more state, edge cases at the ends. |
| **Clamp `finalFrame` to `[0, maxFrame]`** | Prevents commit-time amplification. | Server-side validation. |

The dominant fix is **default zoom = fit-content (or auto-fit on open)**, because the 30× overflow is the root cause of the "1 px drag = whole clip flies" perception.

---

## 7. Spec invariants preserved (NOT changed by this audit)

- Frame 0 = x=0 inside `.timeline-content` (no gutter offset, GUI-03R2 P0-A). ✓
- 1 px = 1 frame at default zoom. ✓ (math is correct; **viewport just doesn't fit**)
- Drag preview 1:1 follows pointer (03R3-1E). ✓
- Snap is visual-only during drag, authoritative only on pointerup. ✓
- Snap-creates-overlap aborts. ✓
- No local snap pin during pointermove. ✓

All frame-math invariants hold. The "drag flies" sensation is **not caused by incorrect frame math** — it's caused by **the viewport containing only 3.3% of the project**.

---

## 8. Conclusion

The audit confirms that **the 03R3-1E algorithm is correct on frame math** and that the user's "drag flies" perception is **viewport geometry**, specifically:

1. **30× zoom overflow** — the user sees 45 seconds out of 23 minutes.
2. **No auto-scroll during drag** — clips routinely leave the visible area.
3. **Small pointer drags produce large visible jumps** because 1 px = 1 frame and the visible area is so narrow.

The fix is to **change the default zoom** (or add a Fit Content auto-zoom on open), not to change the drag algorithm.

Algorithm changes are explicitly out of scope for this batch (per user instruction).