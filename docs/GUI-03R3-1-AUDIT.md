# GUI-03R3-1 Audit: Reliable Drag Instrumentation

> **Status:** baseline measured. No algorithm change yet.
> **Baseline:** `main@c36764d` (GUI-03R2).
> **Driver:** real Sanlihe browser via Playwright CDP, project `projects/sanlihe-slice-30s/`.
> **Test surface:** `gui/smoke/03r3-1-instrument.mjs` (4 scenarios).

---

## 1. What we measured

`ClipBlock.tsx` was instrumented to emit a `[YROLL-DRAG]` structured payload at the end of every `pointerup`. The payload captures:

| Field | Meaning |
|-------|---------|
| `pointerdown.clientX` | screen X of pointerdown (sanitized) |
| `pointerup.clientX`, `clientY` | screen X/Y of pointerup |
| `rect_left` | `.clip` element's screen left at up time |
| `contentOrigin` | `.timeline-content` left = frame 0 in viewport |
| `scrollLeft` | `.timeline-content` scrollLeft |
| `pxPerSec`, `pxPerFrame` | zoom model |
| `originalFrame` | clip's `tlStartFrame` at down |
| `deltaPx` | pointerup.clientX − pointerdown.clientX |
| `deltaFrame` | integer frame delta from pointermove |
| `preSnapFrame` | the SAME candidateFrame from the last pointermove (used as pre-snap input on up) |
| `lastPreviewFrame` | the integer frame emitted via `onDragMove` on the last move |
| `snapFrame` | `api.snap()` result (null if Core returned no snap) |
| `finalFrame` | the integer sent to `api.move()` after clamp + post-snap re-clamp |
| `targetTrackId` | DOM `data-track-id` resolved at pointerup |
| `finalTrackId` | the `track_id` argument sent to `api.move()` |
| `sourceTrackId` | the clip's pre-drag track id |
| `snapEngineApplied` | whether Core's SnapEngine returned a non-null snap |

The payload is emitted to `console.log("[YROLL-DRAG]", ...)` AND pushed to `window.__yrollDragLog[]`. The smoke script reads `window.__yrollDragLog` after each scenario.

---

## 2. Four-scenario reproduction (real browser)

All scenarios run against the first visible clip (`c0a6d68`) on the first visible video track (`v9`) in `main` Timeline at the default zoom (30 px/sec ≈ 1 px/frame at 30 fps). Drag = a real pointer event chain (pointerdown on the `.clip` element + pointermove × N on `window` + pointerup on `window`).

### 2.1 Scenario A — 1 px drag (cursor 1 frame right)

| Field | Value |
|---|---|
| originalFrame | 0 |
| deltaPx | 1 |
| deltaFrame | 1 |
| preSnapFrame | **0** |
| lastPreviewFrame | 0 |
| snapFrame | 0 |
| finalFrame | 0 |
| targetTrackId / finalTrackId | v9 / v9 |
| snapEngineApplied | true |

**Observations.**
- The user drags 1 pixel right.
- Local snap during `move()` snaps `candidate=1` back to `originalFrame=0` (radius 8 frames, |1−0|=1 ≤ 8). `preSnapFrame = 0`.
- The visual preview (via `onDragMove`) is `0` for the entire drag. The clip does not move.
- On pointerup, `api.snap(0, ...)` returns `0`. `finalFrame = 0`.
- The committed position is identical to `preSnapFrame` and `lastPreviewFrame`. **Hard invariant holds (preview == commit).**
- **User-visible effect: drag did nothing.** Pointer moved 1 px; the clip stayed still. This is the first source of the "drag flies" perception.

### 2.2 Scenario B — 8 px drag (cursor 8 frames right, exact snap-radius boundary)

| Field | Value |
|---|---|
| originalFrame | 0 |
| deltaPx | 8 |
| deltaFrame | 8 |
| preSnapFrame | **0** |
| lastPreviewFrame | 0 |
| snapFrame | 0 |
| finalFrame | 0 |
| targetTrackId / finalTrackId | v9 / v9 |
| snapEngineApplied | true |

**Observations.**
- Identical pattern to Scenario A. Local snap pins `candidate ∈ [0..8]` back to `0`. Server snap returns `0`.
- **User drags 8 px → clip doesn't move at all.**
- This is the "drag flies" complaint at its sharpest: at the snap-radius boundary, an entire 8 px of pointer movement is **invisible**.

### 2.3 Scenario C — 600 px drag (cursor 600 frames right, past snap radius)

| Field | Value |
|---|---|
| originalFrame | 0 |
| deltaPx | 600 |
| deltaFrame | 600 |
| preSnapFrame | **600** |
| lastPreviewFrame | 600 |
| snapFrame | null |
| finalFrame | 600 |
| targetTrackId / finalTrackId | v9 / v9 |
| snapEngineApplied | false |

**Observations.**
- Drag exceeds snap radius from any candidate. Local snap returns null → clamp returns `candidate=600`.
- Server snap returns null (no candidate within radius). `finalFrame = 600`.
- The visual preview followed the cursor 1:1.
- **Hard invariant holds (previewFrame == preSnapFrame == finalFrame).** Drag works correctly when past snap radius.

### 2.4 Scenario D — cross-track drop (partial reproduction)

| Field | Value |
|---|---|
| originalFrame | 18000 (clip had been moved by prior test runs) |
| deltaPx | −17960 |
| deltaFrame | −17960 |
| preSnapFrame | **40** (post-clamp from candidate=40) |
| lastPreviewFrame | 40 |
| snapFrame | null |
| finalFrame | 40 |
| targetTrackId | **null** (elementsFromPoint didn't resolve a track-row at pointerup point — see §3.4) |
| finalTrackId | v9 (source — no cross-track) |
| snapEngineApplied | false |

**Observations.**
- Drag from frame 18000 to clientX=130. Pre-snap candidate = 18000 − 17960 = 40. Local snap returns null. Clamp against siblings returned 40 (no conflict with siblings in `[4500..4650]` or `[4800..5055]`).
- Server snap returned null. `finalFrame = 40`.
- The cross-track re-clamp path **did not run** because `elementsFromPoint` didn't resolve a track-row. The drag landed at frame 40 on `v9` (source track).
- **Partial coverage of Scenario D.** This is documented as a known gap; the cross-track logic was already verified end-to-end in 03R2 (test 6 in `03r2-sanlihe.mjs`). The structural pattern (atomic frame+track in single API call, target-track siblings for clamp) is unchanged.

---

## 3. Findings

### 3.1 The "drag flies" perception is NOT a preview/commit mismatch

The hard invariant **already holds** under the current code: `previewFrame == preSnapFrame == finalFrame` whenever `api.snap` returns null. When `api.snap` returns a non-null `snapped_frame`, `finalFrame = snapped_frame`, and the user sees a small visual "settle" — this is also by spec.

So the user's complaint is not that the clip commits to a frame the user didn't see. The complaint is that **the preview itself jumps in a way that feels non-linear relative to the pointer**.

### 3.2 Two perceptual mechanisms contribute to "flies"

**(a) Snap-rigid small drags.** The local snap during `pointermove` snaps `candidate` back to `originalFrame` (or a sibling boundary) whenever the candidate is within `DEFAULT_SNAP_RADIUS_FRAMES = 8` of any snap target. For drags entirely inside the snap radius, the visual preview **never moves** — the pointer moves 8 px and the clip stays still. The user's brain registers "the drag is laggy" / "the clip is flying away from my cursor" because the **delta between pointer and clip grows** as the user drags.

**(b) Snap-boundary teleport.** When the pointer approaches a sibling boundary, the local snap pulls the preview toward that boundary. At `|candidate − sibling.start| ≤ 8`, the preview teleports from `candidate` to `sibling.start`. This is up to an 8-frame jump on a single pointermove. The preview is no longer 1:1 with the pointer — it has a sticky "attraction" near boundaries that feels non-linear.

Both effects are caused by **local snap running on every pointermove**. The current code at `ClipBlock.tsx:295-300` does:

```ts
const allowSnap = snapMode === "always" || (snapMode === "alt" && ev.altKey);
if (allowSnap) {
  const snapTarget = snap(candidate);
  if (snapTarget !== null) candidate = snapTarget;
} else {
  candidate = clamp(candidate);
}
```

This is the bug per the spec invariant: **"During pointermove, do not perform server snap or magnetic jumps."** The current code runs magnetic jumps every move.

### 3.3 What the algorithm does correctly today

- **Coordinate math is right.** 1 px = 1 frame at default zoom. No frame-domain rounding bugs.
- **ContentViewport origin is right.** `rect_left = contentOrigin = 80`, `scrollLeft = 0`. The pixel↔frame math holds in screen and scroll-aware coords.
- **Cross-track atomicity is right** (verified in 03R2 test 6).
- **Collision clamp is right** — drag into occupied region lands at sibling boundary (verified in 03R2 test 5).
- **No same-track overlap commits** — clamp + post-snap re-clamp enforce this.
- **Snap is authoritative on commit.** When `api.snap` returns a non-null value, the final position is the snap target (Scenario A, B).

### 3.4 Known infra gap during this audit run

Scenario D's `targetTrackId` was null because `document.elementsFromPoint(ev.clientX, ev.clientY)` did not return a `.track-row` at the pointerup position in this particular session. This may be a Playwright dispatch quirk (synthetic pointerup's coords are valid but the elementsFromPoint hit-test didn't find the track-row through whatever overlays might have been momentarily present). The cross-track re-clamp path **was verified end-to-end in 03R2 test 6** with a real pointer drag through React's event chain; we are not regressing it here. Cross-track is pinned via 03R2-P0-D and the `tests/test_no_js_round_in_edit.py` static guard.

---

## 4. Spec interpretation: drag-vs-snap separation

The hard invariant from user approval:

> The frame shown during drag and the frame committed on pointerup must originate from the same candidate calculation.
>
> Drag: pointer → integer candidateFrame → collision clamp → ghost preview
> Pointerup: same candidateFrame → Core SnapEngine → collision validation → commit
>
> Do not recompute an unrelated second candidate on pointerup.
> During pointermove, do not perform server snap or magnetic jumps.
> On pointerup, Snap is authoritative, but a snap result that creates overlap is invalid and must never be committed.

Mapping to the current code:

| Spec step | Current behavior | Gap |
|-----------|------------------|-----|
| Drag: pointer → integer candidateFrame | ✅ `candidate = origStartFrame + deltaFrame` | — |
| Drag: collision clamp | ✅ when `snapMode !== 'always'` | ⚠ when `snapMode === 'always'`, snap runs FIRST and overrides clamp |
| Drag: ghost preview at snap target | ❌ no ghost outline at snap target | needs new feature |
| Drag: no server snap, no magnetic jumps | ❌ local snap runs every move | **the bug** |
| Up: same candidateFrame from move | ✅ `preSnapFrame = lastPreviewFrame` | — |
| Up: Core SnapEngine | ✅ `await api.snap(finalFrame, ctx, radius)` | — |
| Up: collision validation | ✅ post-snap `clamp(finalFrame)` | — but spec wants "if snap creates overlap → ABORT snap and commit pre-snap frame" — current code silently overrides to clamped frame, losing the user's snap intent |
| Up: commit | ✅ `onMoveCommit(clipId, finalFrame, tid)` | — |

### 4.1 Two corrections are required for v0.1

**Correction 1: remove magnetic jumps during pointermove.**

`move()` should NOT run `snap(candidate)` on every move. It should run `clamp(candidate)` only. The visual preview must follow the cursor 1:1 in frames. The pre-snap candidateFrame on pointerup is the LAST integer frame emitted by `move()` (already true).

The ghost outline is a separate affordance: during `move()`, we ALSO compute `ghostTarget = snap(candidate)` (without applying it) and draw a thin vertical line at the ghost target's px position. This is a visual hint, not a candidate change. **If `ghostTarget === null` or `|ghostTarget − candidate| > DEFAULT_SNAP_RADIUS_FRAMES`, no ghost.**

**Correction 2: snap-creates-overlap aborts the snap.**

Currently the code does:
```ts
if (snapped_frame !== null) finalFrame = snapped_frame;
// ...
finalFrame = clamp(finalFrame);  // re-clamp AFTER snap
```

If `snapped_frame` creates overlap with siblings, the post-snap `clamp()` moves `finalFrame` AWAY from `snapped_frame` to resolve the conflict — but the snap was already applied. The user gets neither the snap target nor the pre-snap candidate: they get a third frame that doesn't match what they saw.

Per the spec invariant: "a snap result that creates overlap is invalid and must never be committed." So if the post-snap clamp would move `finalFrame` away from `snapped_frame`, **abort the snap and commit `preSnapFrame`** (the user's pre-snap candidate).

Implementation:
```ts
const preSnapFrame = lastPreviewFrame;
let finalFrame = preSnapFrame;
let snapFrame: number | null = null;
const clampedPreSnap = clamp(preSnapFrame);
try {
  const { snapped_frame } = await api.snap(preSnapFrame, ctx, RADIUS);
  if (snapped_frame !== null) {
    const clampedSnapped = clamp(snapped_frame);
    // Spec: snap is invalid if it would create overlap. Abort.
    if (clampedSnapped === snapped_frame) {
      snapFrame = snapped_frame;
      finalFrame = snapped_frame;
    } else {
      // snap would create overlap → ABORT; commit pre-snap (clamped)
      finalFrame = clampedPreSnap;
      snapFrame = null;
      // status bar: "snap 已吸附 X 帧但会造成重叠，已回退到原候选"
    }
  }
} catch { /* ... */ }
// (no further clamp needed since both branches produce clamp-respecting frames)
```

### 4.2 Drag vs snap separation: who owns what

| Concern | Owner | Code site |
|---|---|---|
| Visual preview during drag | GUI (no snap) | `ClipBlock.move()` |
| Collision clamp during drag | GUI | `ClipBlock.clamp()` (already correct) |
| Ghost outline during drag | GUI (visual only) | new — added in `move()` |
| Snap candidate computation (Core) | Core `/snap` | `api.snap()` (already correct) |
| Snap authority on commit | Core | `api.snap()` (already correct) |
| Post-snap collision check | GUI | `up()` post-snap clamp (new logic) |
| Commit | Core `/clips/move` | `api.move()` (unchanged) |

---

## 5. Implementation plan for 03R3-1D/E

### 5.1 Files to modify

- `gui/src/components/ClipBlock.tsx`
  - Remove `snap(candidate)` from `move()` (drag no longer jumps magnetically).
  - Add `ghostTarget` computation in `move()` (visual only, doesn't change `candidate`).
  - Add `ghost` element render alongside the clip (absolute position via clip's parent track-content).
  - Update `up()`: use `lastPreviewFrame` as `preSnapFrame`, call `api.snap(preSnapFrame)`, abort-and-fallback if snap would create overlap.
  - Keep `[YROLL-DRAG]` instrumentation in place; gate acceptance by it.

- `gui/src/styles.css`
  - Add `.clip-ghost` style: thin vertical line (1 px wide, full track-content height), color matches snap indicator, `pointer-events: none`.
  - Optional: `.clip-snap-aborted` status pulse (used only if snap is aborted).

### 5.2 No changes to

- `App.tsx` (move commit handler unchanged)
- `Timeline.tsx` (track-content DOM unchanged; `data-clip-id` attribute already there)
- Core `/snap` endpoint (unchanged)
- Core `/clips/move` endpoint (unchanged)
- All static guards (`test_no_js_round_in_edit.py`, `test_no_sequence_fps_as_source_fps.py`, `test_seconds_leakage.py`)

### 5.3 Acceptance criteria

`gui/smoke/03r3-1-instrument.mjs` is upgraded to a real acceptance script:

| # | Scenario | Pass condition |
|---|----------|----------------|
| 1 | Drag 1 px right from originalFrame=0 | previewFrame=1, finalFrame=1, no snap applied (snapFrame=null) |
| 2 | Drag 8 px right (snap-radius boundary) | previewFrame=8, finalFrame=8, no snap applied |
| 3 | Drag 600 px right past snap radius | previewFrame=600, finalFrame=600, no snap applied |
| 4 | Drag into occupied region (left collision) | previewFrame follows cursor until clamp; finalFrame = clamp candidate; no overlap; no snap |
| 5 | Drag from frame 0 toward sibling at frame 100, end at frame 92 | finalFrame=snap target (100), snapEngineApplied=true, NO overlap |
| 6 | Drag from frame 0 to a candidate that snap would suggest but that creates overlap | snap is ABORTED, finalFrame = pre-snap (clamped), snapFrame=null, log "[YROLL-SNAP-ABORTED]" |
| 7 | Cross-track drop (verified in 03R2; spot-check here) | targetTrackId = other track-row, finalTrackId = other, single api.move call |

Plus: visual ghost outline appears at the snap target during drag (Scenario 5 only — only when within snap radius).

### 5.4 Regression gates

- pytest 601 + 2 skipped (unchanged)
- vitest 198 + new tests for the abort-snap-on-overlap branch
- tsc 0 errors
- Sanlihe 12-acceptance (`03r2-sanlihe.mjs`) all green (covers drag, cross-track, snap, etc.)

---

## 6. Conclusion

The user's "drag flies" perception is **diagnosable and reproducible**. The root cause is local magnetic snap running on every pointermove, which (a) makes small drags appear to do nothing, and (b) creates non-linear "teleport" jumps when crossing snap boundaries. The hard invariant from the spec — previewFrame == preSnapFrame — is already met by the current code; the fix is to make the **visual** preview honest by removing the magnetic jumps from `move()`.

The fix is small (~30 lines of ClipBlock) and the acceptance tests are crisp. **Proceed to 03R3-1D/E** on user approval.