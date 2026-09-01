# GUI-03R6.2 — Remediation Plan (READ-ONLY)

**Baseline**: HEAD `5d7dd2d` (R6.1 closure complete). Audit: `docs/GUI-03R6.2-Preview-Timeline-Consistency-Audit.md`.
**Mandate**: Plan only. NO code changes in this pass. Per-bug regression scripts may be written because they are additive tests, not behavior changes.

---

## Required execution order (locked by user)

```
B5 (drag)  →  B2/B3 (hidden preview)  →  B1 (Core overlap)  →  B4 (at_frame contract)  →  final Timeline/Preview consistency
```

The order is justified:
- **B5 first** because clip drag is a P0 runtime editing blocker; without it, users cannot recover from any of the other defects.
- **B2/B3 second** because the L0 fallback must respect `track.hidden` before we can trust any visual-layer debugging we do for B1/B4.
- **B1 third** because Core state must be single-overlap-free before we measure at_frame semantics.
- **B4 fourth** because the at_frame/plan divergence can only be characterized once B1/B2/B3 are in.
- **Final Timeline/Preview consistency** as the wrap-up regression battery.

---

## Hard constraints (apply to every batch)

- Do **NOT** loosen overlap protection anywhere.
- Do **NOT** add new features.
- Do **NOT** start Publish Metadata / Timeline-local Revision / Keyframes / opacity / AI features.
- Every batch ships:
  1. A failing real-browser regression that reproduces the bug **before** any code change.
  2. The minimum-diff fix.
  3. New vitest / pytest pinning the fix.
  4. A passing real-browser regression confirming the fix.
  5. A `git commit` per batch with `[R6.2-<bug>] ` prefix.
- No batch may regress another bug's regression test.

---

## B5 — Drag remediation (P0 Runtime Editing Blocker)

### B5.0 Reproduction (must come first)

**File**: `gui/smoke/03r6_2-drag-fly.mjs` (NEW)

The script is the **first** thing we write. It must FAIL on HEAD before any code change.

```js
// Pseudocode — full script in implementation pass
const clip = await page.locator('[data-clip-id="c4c290d"]').first();
// scroll .timeline-content so V3 row is visible
await page.evaluate(() => document.querySelector('.timeline-content').scrollTop = 100);
// hook polled sampler
window.__samples = [];
window.__sampleIvl = setInterval(() => {
  const c = document.querySelector('[data-clip-id="c4c290d"]');
  window.__samples.push({ t: Date.now(), left: c?.style.left });
}, 30);
// drag from clip center, 1px to the right
await page.mouse.move(startX, startY);
await page.mouse.down();
await page.mouse.move(startX + 1, startY, { steps: 1 });
await page.waitForTimeout(200);
await page.mouse.up();
// assert: clip.style.left at pointerdown ≈ 0px; at pointerup must be ≤ pxPerFrame*1.5
const samples = await page.evaluate(() => window.__samples);
const first = samples[0]?.left, last = samples[samples.length - 1]?.left;
const deltaPx = parseFloat(last) - parseFloat(first);
assert(deltaPx < 5, `drag delta ${deltaPx}px exceeds 5px threshold for 1px mouse delta`);
```

Also reproduce **layout bug** separately:

```js
// assert: at viewport 1440×900, elementsFromPoint(clipCenter) returns .clip, not .statusbar
const topEl = await page.evaluate(() => {
  const c = document.querySelector('[data-clip-id="c4c290d"]');
  const r = c.getBoundingClientRect();
  return document.elementsFromPoint(r.left + r.width/2, r.top + r.height/2)[0]?.className;
});
assert(topEl.includes('clip'), `expected .clip at clip center, got ${topEl}`);
```

**Acceptance**: Both assertions FAIL on HEAD. After the fix batch, both PASS.

### B5.1 Root-cause hypotheses

The audit confirmed three independent failures converging into the "fly" symptom:

| # | Hypothesis | Confirm by |
|---|---|---|
| H1 | `.statusbar` overlays the V3 track row at viewport ≤ ~900px tall | Already confirmed (audit B5) |
| H2 | Snap-to-playhead fires on `pointermove`, pinning the clip to playheadFrame even though `snap()` only walks `otherRanges` | Add a `console.log` in `move()` printing `lastPreviewFrame`, `lastCandidateFrame`, `lastGhostSnapFrame` on every pointermove; observe whether `lastPreviewFrame` jumps |
| H3 | `useEffect` or auto-scroll callback is re-emitting `onDragMove(clipId, frame, ghost)` with a stale frame from a previous pointerdown | Same instrumentation; check if multiple `move()` calls happen per pointermove |

Suspected dominant cause is **H2 + H1** working together: the user can't even initiate a drag because H1 intercepts the click; when they manage to drag (after manual scroll), H2 snaps the clip to playhead within one or two pointermoves.

### B5.2 Minimum-diff fixes

**Fix 1 — statusbar layout**

In `gui/src/styles.css` and/or `gui/src/App.tsx`:

Option A (preferred): move `.statusbar` above `.timeline-pane` in the flex order so it never overlaps the timeline region.

Option B: pin `.statusbar` with `position: absolute; bottom: 0; left: 0; right: 0` and add `padding-bottom: 25px` to `.timeline-pane` so the track area is never under it.

Option C: shrink `.timeline-pane` max-height to `calc(100vh - topbar - statusbar - some-margin)` so its `overflow: hidden` actually hides the spilled tracks.

The plan recommends **Option A** because:
- It is a layout-only change (no clipping behavior).
- It does not require `resize` listeners.
- It keeps `.tracks`'s scroll behavior unchanged.

```css
/* Plan-only — do not edit */
.app { display: flex; flex-direction: column; }
.timeline-pane { flex: 1 1 auto; min-height: 160px; max-height: 60vh; overflow: hidden; }
.statusbar { flex: 0 0 auto; }
```

**Fix 2 — snap does not modify preview during drag**

In `gui/src/components/ClipBlock.tsx`, the local `snap()` (line 317) only walks `otherRanges`. Verify by reading that **playhead is NOT a target of the local snap** (it shouldn't be). If confirmed:

- The actual jump comes from a different code path. The most likely candidates are:
  - The `onClampBoundary` callback firing on first `move()` call, which sets `dragClampBoundary` state in App, which re-renders, which... possibly re-emits a stale `onDragMove`?
  - A second effect (perhaps `useProjectSequence` or `usePreviewPlan` revalidation) that re-runs the drag state and clamps against new playhead position.

The fix is to **lock `lastPreviewFrame` to the actual pointer-derived candidate** and **never let any other state mutation override `clip.style.left`** while a drag is in progress. Implementation:

```typescript
// Plan-only
// In onPointerDown, after creating lastPreviewFrame:
const dragLockToken = Symbol("drag-in-progress");
clip.dataset.dragLockToken = dragLockToken.toString();
const move = (ev) => { ...onDragMove(clip.clip_id, clamped, ghost); /* no other state mutation */ };
const up = async (ev) => {
  ...
  delete clip.dataset.dragLockToken;
};
```

Add a guard in `App.onDragMove`:

```typescript
// Plan-only — in App.tsx
const onDragMove = useCallback((clipId, frame, ghost) => {
  if (clipsBeingDragged.has(clipId)) return; // no-op if a drag is active
  setDragGhost(...);
  setDragClampBoundary(...);
}, [...]);
```

**Fix 3 — auto-scroll remains viewport-only**

`DragAutoScroll` (R4.1 P0-1) is correct: it scrolls `.timeline-content`, not the clip's frame. No change needed; just verify with the regression script.

**Fix 4 — rendered position must match candidateFrame × pxPerFrame**

After the drag's first `pointermove`, the clip's `style.left` must equal `lastPreviewFrame * pxPerFrame`. Add a vitest that:
1. Renders a ClipBlock with `pxPerFrame=1.04, origStartFrame=0`.
2. Fires a synthetic `pointermove` with `clientX = startX + 1`.
3. Asserts `clip.style.left ≈ 1.04px` (within 0.5px tolerance for subpixel rounding).

### B5.3 Files touched (expected)

| File | Change |
|---|---|
| `gui/smoke/03r6_2-drag-fly.mjs` (NEW) | Reproduction script for H1 + H2 |
| `gui/src/styles.css` | `.app` flex column order; `.timeline-pane` height constraint |
| `gui/src/components/ClipBlock.tsx` | dragLockToken guard; instrumentation comments |
| `gui/src/App.tsx` | `onDragMove` no-op when clip drag-locked |
| `gui/src/components/ClipBlock.drag.test.tsx` (NEW or extend existing) | 4 new vitest pinning the pointer-only invariant |
| `gui/smoke/03r6_2-drag-fly.mjs` | Run against fix; assert PASS |

### B5.4 Verification

- pytest: unchanged from baseline
- vitest: +4 (drag invariant pins)
- real-browser smoke (03r6_2-drag-fly.mjs): 1→72 jump NOT reproduced; elementsFromPoint returns .clip
- 1px / 5px / 10px / 50px drags each produce a delta within ±5% of `pxDelta × pxPerFrame`
- Cross-track drag: clip moves to target track row, no mid-drag snap
- Near viewport edge: auto-scroll engages, frame delta still pointer-only

---

## B2/B3 — Hidden PreviewPlayer L0 fallback (P0)

### B2/B3.0 Reproduction

**File**: `gui/smoke/03r6_2-hidden-preview.mjs` (NEW)

```js
// Pseudocode
await page.goto('http://127.0.0.1:5180/');
await page.waitForSelector('.preview-stage');

// Confirm V1 is hidden in Core state (via /tracks/v1/clips + /preview/plan)
// Click ruler at frame 1000 (inside V1's overlap zone)
await page.mouse.click(rulerX + 1000 * pxPerF, rulerY + 13);
await page.waitForTimeout(2000);

// Capture preview DOM
const previewImg = await page.evaluate(() => {
  const img = document.querySelector('.preview-stage img[data-layer-kind]');
  return img ? { src: img.src, kind: img.dataset.layerKind } : null;
});
const badgeText = await page.evaluate(() => {
  const b = document.querySelector('.layer-badge');
  return b?.dataset?.trackId;
});

// Assert: NO image, NO badge (since V1 hidden and no V3 coverage at 1000)
assert(previewImg === null, `V1 hidden but preview shows img ${previewImg?.src}`);
assert(badgeText === undefined, `V1 hidden but preview shows V1 badge ${badgeText}`);
```

**Acceptance**: FAILS on HEAD (preview shows V1/a55bc2b). After fix, PASSES.

### B2/B3.1 Root cause (already located by audit)

`gui/src/components/PreviewPlayer.tsx:224-237` selects the first video track without filtering on `t.hidden`. The L0 fallback's `clip && asset` branch then renders the first matching clip from V1 (the first video track in Core order), regardless of whether V1 is hidden.

The L1 plan-based composite (`composite-stage` at line 595-609) is correct — it derives from `/preview/plan` which already excludes hidden tracks. The bug is that the **L0 fallback fires whenever `composite.is_black` is true** (or composite is null), without checking whether the membership came from a hidden-track exclusion or a genuine "no clip at this frame".

### B2/B3.2 Minimum-diff fix

**Strategy**: Make PreviewPlan the single source of truth. The L0 path should:
1. **Only** fire if `mode === "instant" && composite === null` (plan not loaded yet).
2. **Never** fire if `composite && composite.is_black` (Core says no visual layer — even if L0 finds something locally).

Concretely:

```typescript
// Plan-only — in PreviewPlayer.tsx around line 595
} : mode === "instant" && composite && !composite.is_black ? (
  // L1 composite path — UNCHANGED
  <div className="composite-stage">...</div>
) : (
  // L0 single-clip fallback — only used for legacy /preview/at_frame
  // consumption where a single-clip is acceptable. This path is only
  // reached when the L1 plan is unavailable (loading/error) AND a
  // single clip was historically returned by /preview/at_frame.
  //
  // CRITICAL: this path must NOT resurrect a hidden-track clip just
  // because the local clip list has it. Filter on track.hidden here
  // too, mirroring the L1 contract.
  (() => {
    const vtrack = ...;
    if (vtrack?.hidden) return <div className="placeholder">⏰ 播放头在间隙里（{playheadFrame} frames）</div>;
    const clips = ...; // existing logic
    ...
  })()
) ? (
```

The key invariant: **every code path that produces a visual layer must filter `t.hidden`**. The audit's invariant must be checked in **both** branches, not just one.

**Alternative simpler fix**: collapse the L0 fallback entirely. If `composite` is null or `is_black`, render the placeholder. The L0 fallback was added in early GUI-03D for legacy `/preview/at_frame` consumption; with the L1 plan always available via `usePreviewPlan`, the L0 path can become a strict "loading" state.

The plan recommends the **alternative simpler fix** if `usePreviewPlan` is reliable (no stale-cache window that lasts more than 1s). If it isn't, the conditional fix is the fallback.

### B2/B3.3 Files touched

| File | Change |
|---|---|
| `gui/smoke/03r6_2-hidden-preview.mjs` (NEW) | Reproduction script |
| `gui/src/components/PreviewPlayer.tsx` | Filter `t.hidden` in L0 fallback, or remove L0 fallback entirely |
| `gui/src/components/PreviewPlayer.test.tsx` (extend) | 4 new vitest: hidden track → no L0 layer; ended clip → no L0 layer; hidden + ended → placeholder; visible V1 → renders correctly |

### B2/B3.4 Verification

- vitest: +4
- real-browser smoke: 03r6_2-hidden-preview.mjs passes (V1 hidden → preview shows placeholder, NOT a55bc2b)
- Round-trip: V1 hidden→shown→hidden does not produce different img src

---

## B1 — Core overlap invariant (P0)

### B1.0 Reproduction (the audit-level snapshot)

The overlap exists **on HEAD** in `projects/_sanlihe-r5-manual/current.json`:
- `v1/c4b3597` [953, 1073]
- `v1/cb82e96` [960, 1080]

This is **NOT** a runtime bug we can repro with a script (it's persistent state). The audit identified it via Core API. The fix is two-pronged: (a) clean the current file, (b) prevent recurrence.

### B1.1 Mutation provenance (audit task)

**Required first step**: read `projects/_sanlihe-r5-manual/operations/op*.json` to find the `move_clip` op that produced the overlap. Likely candidates:
- The op that moved `cb82e96` into `[960, 1080]` (which overlapped existing `c4b3597` [953, 1073]).
- A `move_clip` that allowed the overlap because the Core check ran against the wrong siblings (e.g., compared against `cbf21ed` only, not `c4b3597`).

**Investigation checklist**:
1. List all `move_clip` operations that targeted `cb82e96` or `c4b3597`.
2. For each, replay the op in a test environment and observe the response. If Core returned 200 OK with the resulting overlap, that's the regression commit.
3. Identify whether `cmd.move_clip`'s overlap check uses `clip_ids` of the **target** track correctly, or if it has a stale snapshot bug.

The mutation provenance MUST be documented in the implementation commit message (per user requirement: "Do not merely repair the current project file").

### B1.2 Current-state cleanup

**One-shot Core op**: `cmd.move_clip(cb82e96, timeline_id=main, new_timeline_start_frame=1080)` (push past `cbf21ed` start). This is safe — Core's overlap check accepts this because `cbf21ed` starts at 1080 (tangent, not overlap). After the move, the order on V1 becomes:

```
v1/c4b3597 [953, 1073]
v1/cbf21ed [1080, 1335]   ← was third
v1/cb82e96 [1080, ?]      ← moved here, then adjust end_frame to match duration
```

Or move `cb82e96` to before `c4b3597`:

```
v1/cb82e96 [new_start, new_start + 120]
v1/c4b3597 [953, 1073]
v1/cbf21ed [1080, 1335]
```

Either fix is acceptable; the chosen one is whichever doesn't overlap any other clip and respects the user's editorial intent (if known).

### B1.3 Prevention: Core overlap invariant at every mutation path

For each Core mutation path, audit and add a regression test:

| Path | Current behavior | Required regression test |
|---|---|---|
| `cmd.add_clip` | Overlap check at add | Already exists; add a 2nd-order case: add same start_frame as existing clip |
| `cmd.move_clip` | Overlap check at move | Add case: move to overlap a non-adjacent sibling |
| `cmd.trim_clip` | Overlap check at trim-end | Add case: trim-end to overlap a sibling's start |
| `cmd.split_clip` | Split creates two halves; each must not overlap siblings | Add case: split at a frame inside a sibling's range |
| `cmd.ripple_delete` | Delete + shift; no new overlap possible | Already covered |
| `cmd.duplicate_clip` (03E-4) | Duplicate lands at end of track; must not overlap | Add case: duplicate when there's no gap |
| `cmd.add_track` (ensure_track_for_drop) | Track allocator respects timeline extent | Already covered; add: ensure no overlap on insert |
| `cmd.cross_track_move` | Old track's other clips unaffected; new track's siblings respected | Add case: cross-track move that overlaps an existing clip on target |

For each, the test:
1. Set up a fixture with a known non-overlapping arrangement.
2. Invoke the mutation with parameters designed to overlap.
3. Assert: Core returns 400 (or equivalent CommandError) AND no Operation is appended to the log.
4. Bonus: assert the invariant "`for c1, c2 in same_track.clips: not (c1.start < c2.end and c2.start < c1.end)`" holds after the failed mutation.

### B1.4 Files touched

| File | Change |
|---|---|
| `yroll/core/commands.py` (or wherever move/add/trim/split/duplicate live) | Tighten overlap check + new regression tests |
| `tests/test_no_overlap_invariant.py` (NEW) | Static guard: scan every project under `projects/` for same-track overlap; CI fails on detection |
| `tests/test_move_clip_overlap.py` (extend) | Add 3 cases: non-adjacent sibling overlap; trim-into-sibling; split-inside-sibling |
| `tests/test_duplicate_clip_overlap.py` (NEW) | 03E-4 cross-track isolation; overlap on duplicate |
| `tests/test_split_clip_overlap.py` (NEW) | split at sibling-start frame |
| `tests/test_trim_clip_overlap.py` (NEW) | trim-end to overlap sibling |
| `scripts/fix-v1-overlap.py` (NEW, ONE-SHOT) | Apply the one-shot move to `_sanlihe-r5-manual/current.json`; emits an Operation entry |

### B1.5 Verification

- pytest: +12 (3 per path × 4 paths: move/trim/split/duplicate + 1 invariant guard)
- vitest: unchanged
- Real fixture: `python -c "from yroll.core.plan import ...; assert no_overlap(_sanlihe_r5_manual)"` PASSES
- `git log` shows the one-shot fix commit with documented provenance

---

## B4 — `/preview/at_frame` semantic contract (P0)

### B4.0 State of the endpoint (verified live during plan-writing)

The Core endpoint `/preview/at_frame?timeline_id=main&frame=N` correctly returns the expected layer for **every** frame tested (0, 75, 800, 1500, 2200, 2500). The audit's earlier "B4 finding" was a misread — it was observing the **GUI's** L0 fallback firing instead of the L1 plan, not a Core bug.

**Refined B4 finding**: the GUI mixes L1 plan membership (correct, excludes hidden) with L0 fallback membership (incorrect, includes hidden). Once B2/B3 is fixed, the GUI should derive exclusively from L1, and the at_frame endpoint's correctness will surface in the GUI.

However, **the audit still demands a documented semantic contract** for `/preview/at_frame` before any change to that endpoint. We commit to documenting the contract now.

### B4.1 Documented semantic contract (frozen)

```
GET /preview/at_frame?timeline_id=<id>&frame=<int>
```

**Returns a CompositePreview** describing **all active layers** at the given frame on the given Timeline.
- A layer is "active at frame F" iff its clip's `[timeline_start_frame, timeline_end_frame)` half-open interval contains F.
- For visual tracks (kind=video), an image asset yields one layer; a video asset yields one layer.
- For audio tracks (kind=audio), each active audio clip yields one layer.
- For text/subtitle tracks (kind=text/subtitle), each active text clip appends to `subtitle_texts`.
- Hidden tracks (`track.hidden == true`) contribute NO layers and NO subtitles.
- `is_black == true` iff `visual_layers` is empty AND `audio_layers` is empty AND `subtitle_texts` is empty.

**Relationship to `/preview/plan`**: `/preview/at_frame` is a **subquery** of `/preview/plan`. At any frame F on Timeline T:
- For every layer `L` in `at_frame(T, F).visual_layers`, there exists exactly one `PreviewLayer` in `plan(T).tracks[*]` whose `clip_id == L.clip_id` and `timeline_start_frame <= F < timeline_end_frame`. The reverse is not true (plan has all layers; at_frame has only the active one).
- `at_frame`'s `layer_index` matches the plan's `layer_index` for the same layer (consistent with `build_preview_plan`'s global layer_index assignment).

**Cacheability**: `/preview/at_frame` is **NOT cached** — it's a pure function of `(project, frame, timeline_id)`. Clients may cache the response client-side per frame, but the server never caches.

**Stability across revisions**: `/preview/at_frame` reflects the project's CURRENT state, regardless of `project_revision`. It does NOT embed `project_revision` in the response.

### B4.2 Implementation review

Read `yroll/core/frame_preview.py:composite_preview_at_frame` and `yroll/core/plan.py:build_preview_plan` to confirm:

1. Hidden tracks are excluded (R5 fix already in).
2. `layer_index` assignment in `composite_preview_at_frame` matches `build_preview_plan` (audit says yes — global stack order, KIND_RANK + numeric suffix).
3. There is no scenario where `at_frame` returns more or fewer layers than `plan` says should be active at the given frame.

**Code-read checklist**:
- [ ] `composite_preview_at_frame` skips `track.hidden` (already verified at line 207-209)
- [ ] `composite_preview_at_frame` iterates clips in `track.clip_ids` order, returns the FIRST whose range covers the frame
- [ ] `composite_preview_at_frame`'s `visual_index` is incremented per returned visual layer, NOT per scanned clip
- [ ] `build_preview_plan`'s layer_index assignment uses the same stack-order iteration (KIND_RANK + numeric suffix)
- [ ] `_timeline_range_frames(c, fps)` rounds consistently across both functions

If any item fails, **fix the function before this batch ships**.

### B4.3 Test pin

Add `tests/test_preview_at_frame_contract.py` (NEW):

```python
def test_at_frame_excludes_hidden_tracks():
    """V1 hidden, frame=1000: visual_layers=[], is_black=True."""
    pv = composite_preview_at_frame(project, 1000, fps)
    assert pv.visual_layers == []
    assert pv.is_black

def test_at_frame_matches_plan_for_active_layer():
    """at_frame at frame F returns the same clip_ids as plan.tracks[*].activeLayerAt(F)."""
    plan = build_preview_plan(project)
    for F in [75, 800, 1500, 2200, 2500]:
        pv = composite_preview_at_frame(project, F, fps)
        plan_active = [l.clip_id for track in plan.tracks for l in track if l.timeline_start_frame <= F < l.timeline_end_frame]
        at_active = [l.clip_id for l in pv.visual_layers]
        assert sorted(plan_active) == sorted(at_active)

def test_at_frame_layer_index_matches_plan():
    """layer_index for each layer matches plan's index for the same clip."""
    ...

def test_at_frame_subtitles_match_plan():
    """subtitle_texts at F match plan.subtitle_texts_by_range active at F."""
    ...
```

### B4.4 Files touched

| File | Change |
|---|---|
| `docs/API-PREVIEW-AT-FRAME.md` (NEW) | Frozen semantic contract |
| `tests/test_preview_at_frame_contract.py` (NEW) | 5 pytest pinning the contract |
| `yroll/core/frame_preview.py` | ONLY if checklist items 1-5 reveal a defect; otherwise untouched |

### B4.5 Verification

- pytest: +5
- Real curl: `/preview/at_frame?frame=1000` returns `is_black: true` with V1 hidden (already passes)
- Real curl: `/preview/at_frame?frame=1500` returns V3/c450db2 (already passes — confirmed in audit)
- No code change to the endpoint if the contract is already met

---

## Final Timeline/Preview consistency batch

After B1, B2/B3, B4, B5 all land, run a combined regression battery:

1. **Full Sanlihe end-to-end**: `gui/smoke/03r4-acceptance.mjs` (8 scenarios, all pass on baseline) — must still pass.
2. **R6 closure smoke**: `gui/smoke/03r6-runtime-editing.mjs` (31 scenarios) — must still pass.
3. **R6.1 closure smoke**: `gui/smoke/03r6_1-closure.mjs` (8 scenarios) — must still pass.
4. **R6.2 new smokes**:
   - `03r6_2-drag-fly.mjs` (B5)
   - `03r6_2-hidden-preview.mjs` (B2/B3)
   - `03r6_2-core-overlap.mjs` (B1 — verifies fixture has no overlap + new mutation paths reject)
   - `03r6_2-at-frame-contract.mjs` (B4 — at_frame matches plan)
5. **Final Timeline vs Preview identity**: at 10 frames, assert Timeline DOM clips covering F == preview DOM rendered layer clip_ids (excluding hidden).

---

## Open questions for the implementation pass (require user input)

These can be answered during implementation, NOT now:

1. **B5 fix 1 (statusbar)**: Option A (flex reorder) vs Option B (padding-bottom) vs Option C (timeline-pane max-height). Plan recommends A; user may prefer C if they want to keep the pane flexible.
2. **B5 fix 2 (snap)**: Whether to remove the L0 fallback entirely or filter it. Recommendation: keep + filter (preserves legacy `/preview/at_frame` consumption path).
3. **B1 cleanup**: Move `cb82e96` before `c4b3597` (cleaner ordering) or after `cbf21ed` (preserves editorial order — V1 had c4b3597 then cb82e96 then cbf21ed, which suggests chronological order). Need to consult user/editor intent.
4. **B4 endpoint**: Frozen contract above is the plan's best interpretation. If the user has different semantics in mind (e.g., "only one resolved clip per frame, not multiple"), we adjust before implementation.

---

## Files NOT touched in this plan (out of scope per user)

- Publish Metadata
- Timeline-local Revision
- Keyframes
- Opacity / advanced transitions
- AI features
- Selection redesign
- Cross-process MCP / lease semantics
- Anything in `dist/` (regenerated by `pnpm build`)
- Anything in `node_modules/`

---

## Per-batch commit template

```
[R6.2-<bug>] <one-line summary>

Bug: <audit citation>
Fix: <what changed>
Tests: <pytest/vitest counts>
Smoke: <real-browser .mjs filename + pass count>
Regression: <which existing smokes still pass>
```

Each batch ships independently with a `git push` to origin. After all four batches land and the final consistency batch passes, R6.2 is closed and R7 (or whatever the next feature batch is) may begin — but only after user approval.

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| B5 fix 1 (statusbar layout) breaks Fit Content zoom logic | Low | Medium | Smoke `03r4-acceptance.mjs` scenario H must still pass |
| B2/B3 fix removes too much — Preview never renders for projects without L1 plan | Low | High | Keep L0 fallback as conditional branch; do not collapse entirely |
| B1 mutation provenance is unclear (op log doesn't tell us) | Medium | Low | Document the absence of provenance in commit; fix prevention regardless |
| B4 contract change conflicts with already-deployed MCP tools | Low | Medium | MCP tools don't use `/preview/at_frame` directly (verified) |
| Real-browser regression is flaky (timing-dependent) | Medium | Medium | Use polled samplers with deterministic wait; multiple trials; report variance |