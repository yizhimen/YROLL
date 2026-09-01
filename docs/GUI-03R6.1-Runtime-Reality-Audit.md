# GUI-03R6.1 Runtime Reality Audit v0.1

**Audit baseline**: HEAD = `f79bc05` (R6 closure fix c9f29a7 + SESSION log; no code change in f79bc05).
**Live backend**: `python -m yroll.cli.main serve projects/_sanlihe-r5-manual` on port 8770.
**Live frontend**: vite dev on port 5173 (per session log; no static-with-proxy on 5180 at audit time).
**Audit window**: 2026-09-01 (post-c9f29a7).
**Mandate (per user)**: produce runtime evidence before any code change. **No code edits in this audit.**

This audit is **read-only**. Every claim is backed by a CLI observation against
the running backend (`curl :8770/...`), a static read of the current tree, or
a deterministic numerical reproduction of the suspect formula. No source
file in `yroll/`, `gui/src/`, or `tests/` was modified by this audit.

---

## TL;DR — table

| # | User symptom | Reproducible? | Exact runtime evidence | Root-cause layer | Existing capability | Missing/faulty piece | Proposed fix | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | Real mutation produced 422 `new_timeline_start_frame = 1080.2549999999999` | **Partial** — server's Pydantic model **does** reject fractional frames with 422 (confirmed live). The exact 1080.255 value traces to a seconds→frame multiply without rounding in the **GUI** code path. | Live: `POST /clips/c039a7b/move` with `{"new_timeline_start_frame": 1080.2549999999999}` → 422 `int_from_float`; with `1080` → 400 overlap. GUI source `gui/src/App.tsx:1217-1218, 1598-1601` sends `clip.source_range.start + 0.5` (SECONDS) to `api.trim` (FRAMES contract); also `displayProject` override at `gui/src/App.tsx:985-995` produces `end = int + float` (visual only). | GUI contract violation (TRIM) + Core Pydantic `int` enforcement (correct) | `MoveReq.new_timeline_start_frame: int` (Pydantic v2) rejects fractions with 422 + clear error; `add_clip_frame` and `trim_image_clip_frame` are frame-native. | The TRIM inspector buttons at `App.tsx:1217,1218,1598,1601` pass `clip.source_range.{start,end} ± 0.5` (seconds) directly to `api.trim` which expects frames → 422. Display project override (line 985-995) builds `timeline_range: { start: int, end: int + float }` (subtle contract violation even if the value isn't sent). | (1) Convert `±0.5s` to `±15 frames` at the call site (`Math.round(0.5 * fps)`); (2) drop the `displayProject` end-rebuild — keep `end: clip.timeline_range.end` (or compute `end: int + (clip.timeline_range.end - clip.timeline_range.start)` cast to number after the float is sanity-rounded); (3) **add a vitest** that fails the build if any `api.move`/`api.trim`/`api.split`/`api.addClip` call is passed a non-integer value. | **P0** |
| B | Drag "flies away" — clip teleports beyond pointer | **YES — spec-level perception bug, not amplification** | Static: `ClipBlock.up()` math is correct (`finalFrame ∈ Z`); pixel delta = N → frame delta = N (pxPerFrame=1 at default zoom 30 px/sec @ 30fps). The "fly" maps to `clamp(candidate)` teleporting to `sibling.start - len` (or `sibling.end`) when the candidate is inside an existing clip — the spec calls this a "clean landing" but the user reads it as "the clip teleported past my pointer". | GUI presentation | `deltaFrame = roundHalfAwayFromZero(pixelDelta/pxPerFrame)` pinned by `drag-invariant.test.ts`; `scrollLeft` does NOT enter frame math (R3-2 P0-B). Auto-scroll works (`drag-autoscroll.test.ts`). | (a) No visual indicator that the preview landed on a clamp boundary (not the user's intended drop point). The preview is identical regardless of "user wanted here" vs "clamp forced here". (b) `lastPreviewFrame` in payload is the clamped value — when the user nudges a few pixels into a sibling, the clamp jumps to `sibling.start - len` which can be 30+ frames away from the pointer. | (1) On clamp boundary (tryStart ≠ clamped), render the dragged clip with a 2px dashed red outline + show a transient status "已贴边" (snapped to boundary) for the duration of the drag; (2) instrument `payload.clampJumpFrames = abs(tryStart - clamped)` so the audit can see when clamp is doing the work. **No change to math or commit path.** | **P1** |
| C | Preview canvas is "extremely small"; 16:9/9:16/4:3/3:4 wrong, only 1:1 looks normal | **YES — math bug in `PreviewPlayer.tsx:466-473`** | Static: `if (availW / aspectW <= availH) { canvasW = availW; canvasH = availW / aspectW; }` — the height formula uses `availW / aspectW` instead of `availW * aspectH / aspectW`. Numerical reproduction at stage=720×405: 16:9 → 720×**45** (flat strip, **9× too short**); 9:16 → 720×80; 4:3 → 720×180; 3:4 → 720×240; 1:1 → 405×405 ✓. The user's "only 1:1 looks normal" matches perfectly — for 1:1, the buggy `availW/aspectW` (720/1 = 720) correctly fails the `<= availH` test and the height-bound branch sets `canvasH = availH = 405`, which happens to be right. | GUI formula (presentation) | ResizeObserver-driven `stageSize` is correct; inset is correct. | Aspect-fit formula is dimensionally wrong. The `aspectH` declared in line 458 is **never used** (dead variable). The correct formula: `scaleW = availW/aspectW; scaleH = availH/aspectH; if scaleW <= scaleH: width-bound (canvasW=availW, canvasH=scaleW*aspectH) else: height-bound (canvasH=availH, canvasW=scaleH*aspectW)`. | (1) Fix the formula at `gui/src/components/PreviewPlayer.tsx:466-473` (one-line math change); (2) remove the dead `aspectH` variable — actually use it; (3) add a vitest that asserts the 5 standard aspects produce the expected canvas size given a fixed stageSize. **Add to R6.1 batch (single-file change).** | **P0** |
| D | Hidden visual Track may still appear in Preview | **Partial — server is correct; GUI has a stale-plan window** | Live: hide v9 → `/preview/at_frame?timeline_id=main&frame=450` returns `is_black=false, visual_layers=[v1 only]` (v9 absent). `/preview/plan?timeline_id=main` does not include v9 in the tracks list. **Server side is correct.** GUI side: `usePreviewPlan` is keyed by `(projectRevision, timelineId)` and only refetches when the revision changes. `useProjectSequence` polls `/sequence` every ~5s. So between the hide action and the next sequence poll, the GUI keeps the OLD plan and may still show v9 in the L1 composite. | GUI cache invalidation lag | `Timeline.hidden.test.tsx` pins "row exists + no display:none"; R5 remediation #1 fixes the Timeline row. Server's `build_preview_plan` excludes hidden tracks (pinned by `test_hidden_track_preview_exclusion.py`). | The `usePreviewPlan` cache has no optimistic-exclusion path. After `setTrackHidden(v9, true)` succeeds, the L1 composite can show v9's clip for up to one `/sequence` poll cycle. The user can also re-trigger a refetch by playing/pausing (the `liveSeq.projectRevision` updates). | (1) Bump the local plan cache key on a successful `setTrackHidden` mutation (e.g. add a "dirty" ref the plan hook reads); (2) alternatively, the `usePreviewPlan` hook subscribes to a `hiddenTrackIds` set passed by App — the hook filters the cached plan locally until the server refetch returns. **Defense in depth: don't trust the cache to be fresh.** | **P1** |

---

## Audit A — Frame integer integrity

### A.1 Server-side boundary: confirmed correct

Live Pydantic v2 enforcement:

```
$ curl -i -X POST :8770/clips/c039a7b/move?sessionId=...&baseRevision=1 \
       -H 'Content-Type: application/json' \
       -d '{"new_timeline_start_frame": 1080.2549999999999, "why": "audit"}'
HTTP/1.1 422 Unprocessable Entity
{"detail":[{"type":"int_from_float","loc":["body","new_timeline_start_frame"],
"msg":"Input should be a valid integer, got a number with a fractional part",
"input":1080.2549999999999}]}

$ curl -i -X POST :8770/clips/c039a7b/move?sessionId=...&baseRevision=1 \
       -d '{"new_timeline_start_frame": 1080, "why": "audit"}'
HTTP/1.1 400 Bad Request
{"detail":"move_clip(c039a7b) 与轨道 v1 上现有 clip 时间重叠：cbf21ed。..."}
```

The **server is doing its job**. `MoveReq.new_timeline_start_frame: int` in
`yroll/server/app.py:83` is a Pydantic v2 `int` field. Pydantic v2 enforces
"no fractional part" and returns `int_from_float` with the **exact JSON value
the client sent** echoed back in `input`. This matches the user's report
verbatim: the 422 they saw is Pydantic rejecting the float, not a Core math bug.

### A.2 The 1080.2549999999999 trace (IEEE 754 + missing round)

The value `1080.2549999999999` is the canonical IEEE 754 double representation
of `1080.255` (= `36.0085 * 30` in JavaScript at 30 fps). The number arises
wherever a `clip.timeline_range.start` (which is in **seconds** in the legacy
model storage) is multiplied by `seqFps.num / seqFps.den` **without rounding**.

**Smoking gun #1 — Inspector trim buttons** (`gui/src/App.tsx:1217-1218`):
```ts
onTrimHead={() => clip && run(() => api.trim(clip.clip_id,
  clip.source_range.start + 0.5), "头部裁掉 0.5s")}
onTrimTail={() => clip && run(() => api.trim(clip.clip_id, undefined,
  clip.source_range.end - 0.5), "尾部裁掉 0.5s")}
```
The same pattern appears in the inspector body at lines 1598 and 1601.

`clip.source_range.start` and `clip.source_range.end` are in **seconds**.
`api.trim(clipId, newSourceStartFrame, newSourceEndFrame, why)` is declared
in `api.ts:274-279` to take **integer source frames**. The implementation:
```ts
trim: (clipId, newSourceStartFrame, newSourceEndFrame, why = "") =>
  mutate("POST", `/clips/${clipId}/trim`, {
    new_source_start_frame: newSourceStartFrame ?? null,
    new_source_end_frame: newSourceEndFrame ?? null,
    why,
  }),
```
`new_source_start_frame` flows into `TrimReq.new_source_start_frame: int | None`
in `yroll/server/app.py:77`. Pydantic v2 returns 422 with `input: 0.5` (or
whatever the actual computed value is).

This is a **TRIM contract violation**, not a MOVE violation — but it shares
the **same bug class** as the user's reported 422 on `new_timeline_start_frame`.
A real inspector button click produces 422 with the exact same shape.

**Smoking gun #2 — Display project override** (`gui/src/App.tsx:985-995`):
```ts
const displayProject: Project = {
  ...project,
  clips: Object.fromEntries(
    Object.entries(project.clips).map(([id, c]) => {
      const s = dragPreview[id];
      if (s === undefined) return [id, c];
      const len = c.timeline_range.end - c.timeline_range.start;
      return [id, { ...c, timeline_range: { start: s, end: s + len } }];
    })
  ),
};
```
`dragPreview[id]` is an integer (set from `onDragMove` which receives integer
`newStartFrame` from `ClipBlock.move()`). But `len = c.timeline_range.end - c.timeline_range.start`
is a **float** (seconds). So `end = integer + float = float`. The display project
**violates the same `start, end: number` invariant that the server uses for
strict `int` types** — a downstream component reading `displayProject.clips[id].timeline_range.end`
may convert back to frames via `* fps` and produce a non-integer.

This is currently a **visual-only** side effect (it doesn't reach the move
endpoint directly), but it's a contract violation that future code can leak
into a real mutation.

### A.3 The move path itself — math is correct (R3-1E invariant intact)

Static trace of `ClipBlock.onPointerDown` → `move()` → `up()`:

| Stage | Code location | Operation | Type at output |
|---|---|---|---|
| pointerdown | `ClipBlock.tsx:248-250` | `startX, origStartFrame, lenFrames` | `startX: number, origStartFrame: Z, lenFrames: Z` |
| `move(ev)` (per pointermove) | `ClipBlock.tsx:365-392` | `pixelDelta = ev.clientX - startX; deltaFrame = pxPerFrameToFrameDelta(pixelDelta, pxPerFrame); candidate = origStartFrame + deltaFrame; clamped = clamp(candidate); ghostSnap = snap(candidate)` | `deltaFrame: Z, candidate: Z, clamped: Z, ghostSnap: Z | null` |
| `up(ev)` | `ClipBlock.tsx:413-667` | `preSnapFrame = lastPreviewFrame; finalFrame = preSnapFrame; localSnapTarget = snap(preSnapFrame); clampedSnapped = clamp(localSnapTarget.frame); finalFrame = clampedSnapped === localSnapTarget.frame ? localSnapTarget.frame : preSnapFrame;` then cross-track re-clamp via `targetClamp(candidateForTarget)`. | `preSnapFrame: Z, finalFrame: Z` after the entire chain (all clamp/snap are integer-only via `roundHalfAwayFromZero` and integer math). |
| `onMoveCommit` | `ClipBlock.tsx:666` | `onMoveCommit(clip.clip_id, finalFrame, tid)` | `finalFrame: Z` flows verbatim to App. |
| `api.move` | `App.tsx:1880,1884` | `run(() => api.move(clipId, newStartFrame, ...))` | `newStartFrame: Z` flows verbatim to body. |

**Conclusion**: the move path is integer-clean as long as `finalFrame` from
`ClipBlock.up()` is the only source. The `displayProject` and the inspector
trim buttons are the only known **non-move** code paths that can leak floats.

### A.4 Required invariant — what the audit locks in

For every drag, the following must hold:
```
candidateFrame ∈ Z          ← from pxPerFrameToFrameDelta (roundHalfAwayFromZero)
clampedFrame ∈ Z            ← clamp() does integer math
snapFrame ∈ Z ∪ null        ← snap() returns integers or null
finalFrame ∈ Z              ← finalFrame = clamped or clampedSnapped or targetClamped
HTTP new_timeline_start_frame ∈ Z   ← api.move body
```

`pxPerFrameToFrameDelta` (`gui/src/frames.ts:158-163` and the local
`ClipBlock.tsx:48-52`) uses `roundHalfAwayFromZero(pixelDelta / pxPerFrame)`
which is guaranteed to return an integer. All other stages chain through this
or through integer arithmetic on integer inputs. **The invariant holds for
the move path.**

### A.5 Regression that reproduces 1080.2549999999999

Add a vitest that **fails the build** if any `api.move`/`api.trim`/`api.split`/
`api.addClip`/`api.addImageClip` call is passed a non-integer value. Suggested
test (not implemented in this audit):

```ts
// gui/src/frames-contract.test.ts (new)
describe("frame integer contract — mutations only accept integers", () => {
  it("rejects non-integer api.move argument", async () => {
    const err = await api.move("c1", 1080.2549999999999, "test").catch(e => e);
    expect(String(err)).toMatch(/integer/);
  });
  it("rejects non-integer api.trim argument (inspector bug class)", async () => {
    const err = await api.trim("c1", 0.5, undefined, "test").catch(e => e);
    expect(String(err)).toMatch(/integer/);
  });
  it("accepts integer api.move", async () => {
    // expect 400 (overlap) or 200, never 422
    const err = await api.move("c1", 1080, "test").catch(e => e);
    expect(String(err)).not.toMatch(/int_from_float/);
  });
});
```

A separate **static guard** (regression test on the source) is the strongest
defense: parse every call site and check that the second arg of `api.move`,
second/third of `api.trim`, second of `api.split`, third/fourth of `api.addClip`,
second/third of `api.addImageClip` is either an integer literal, an identifier
whose name matches `/Frame|frame/`, or a `Math.round`/`roundHalfAwayFromZero`
call. **NOT IMPLEMENTED — out of scope for read-only audit.**

---

## Audit B — Drag visual amplification

### B.1 Required invariant (R3-1E, R5-B1)

```
deltaFrame = roundHalfAwayFromZero(pixelDelta / pxPerFrame)
scrollLeft does NOT enter the frame math
clamp(candidate) returns integer in [0, max(sibling.end) + len]
snap() returns integer in {r.end, r.start - len} ∪ {null}
```

These are pinned by:
- `gui/src/drag-invariant.test.ts` (4 tests)
- `gui/src/drag-autoscroll.test.ts` (12 tests)
- `tests/test_no_js_round_in_edit.py` (architecture guard, forbids `Math.round`)

### B.2 The math IS correct at every layer (no amplification)

Static trace of `ClipBlock.move()` (`gui/src/components/ClipBlock.tsx:365-392`):

```ts
const move = (ev: PointerEvent) => {
  const pixelDelta = ev.clientX - startX;            // 1
  const deltaFrame = pxPerFrameToFrameDelta(pixelDelta, pxPerFrame);  // 2
  const candidate = origStartFrame + deltaFrame;     // 3
  const clamped = clamp(candidate);                  // 4
  const ghostSnap = allowSnap ? snap(candidate) : null;  // 5
  ...
  onDragMove(clip.clip_id, clamped, ghost);          // 6
};
```

1. `pixelDelta` — pure pointer displacement (no scrollLeft, no ContentViewport origin)
2. `deltaFrame` — `roundHalfAwayFromZero(pixelDelta / pxPerFrame)` (integer)
3. `candidate` — integer + integer = integer
4. `clamped` — integer math on integer inputs (integer)
5. `ghostSnap` — visual only, never applied to the preview
6. `onDragMove(clip_id, clamped, ghost)` — clamped is integer

There is **no amplification** at any stage. A 10-px pointer drag produces a
10-frame intent at default zoom (`pxPerFrame = 1` at 30 px/sec × 30 fps).
The "10 px → 126,150 px amplification" the R3-2 audit found was a **previous**
bug (commit c9f29a7 / c36764d fixed it via server-side `[0, max_timeline_frame]`
guard + GUI-side clamp; pinned by `tests/test_frame_safety_bounds.py`).

### B.3 What IS the "fly" then?

The "flies away" perception has three contributing factors, in order of
likelihood based on the static trace:

**(1) Clamp teleports the visual to a sibling boundary.**
When the user drags a clip into an existing sibling's range, `clamp()`
returns `sibling.start - len` (or `sibling.end` for leftward drag) — the
preview jumps from the pointer's frame to a frame that may be **30+ frames
away from the pointer**. The math is correct; the visual is jarring because
the preview is identical whether the user intended the drop point or the
clamp forced it. There is no visual indicator (red outline, "已贴边"
status, `cursor: not-allowed` overlay).

**(2) `lastPreviewFrame` in the payload is the clamped value, not the
pointer-raw value.** This is correct per spec ("preview 1:1 follows pointer,
but clamp is the visual reality"), but the audit payload doesn't expose
`tryStart` vs `clamped` separately, so we cannot tell from the log whether
clamp did the work.

**(3) Default zoom 30 px/sec (1 px = 1 frame at 30 fps) makes every pixel
feel like a "real" frame.** This is the frame-native feel the spec
deliberately chose. A 10-px drag = 10 frames = 0.33 sec. Users used to
seconds-based editors (where 1 px = 1 sec) perceive the same drag as 10 sec
of content. P2 (taste).

### B.4 Required instrumentation (not yet measured live)

The audit cannot run a real browser to measure the drag end-to-end. The
smoke server is running on 8770, but the static-with-proxy on 5180 is not
in this session (only vite dev on 5173). A measurement script needs to:

1. Open Chromium with CDP, navigate to `http://127.0.0.1:5173/`.
2. Acquire the lease, accept the "我" editor mode.
3. Pick a real clip (e.g. `c039a7b` on v1 at frame 412).
4. Use `page.mouse.down/move/up` to drag +600 px and read `window.__yrollDragLog[-1]`.
5. Compare `startX, clientX, deltaPx, pxPerFrame, rawDeltaFrame, roundedDeltaFrame,
   origStartFrame, candidateFrame, clampedFrame, snapFrame, finalFrame,
   scrollLeft, renderedLeft`.

Add the following fields to the payload (currently absent, see
`gui/src/components/ClipBlock.tsx:573-616`):
```ts
payload = {
  ...,
  tryStart,                  // raw pointer-derived (pre-clamp) — currently `candidateFrame`
  clampJumpFrames: Math.abs(tryStart - clamped),  // how far the clamp jumped
  onClampBoundary: tryStart !== clamped,           // is this a clamp-forced visual?
  finalFrame_visualPx: clamped * pxPerFrame,        // px in ContentViewport coord space
  scrollLeft: contentEl?.scrollLeft ?? 0,
  renderedLeft: dragStartRect?.left ?? null,
};
```

**Do not change drag behavior until this measurement is complete.** No code
edit is performed in this audit.

### B.5 Proposed fix outline (NOT implemented)

1. When `clampJumpFrames > 0`, render the dragged clip with a 2px dashed red
   outline (`#ff5050` matches the playhead color) + transient status text
   "已贴边（避免与 XXX 重叠）".
2. Add `cursor: not-allowed` to the dragged clip when `onClampBoundary=true`.
3. Extend the `[YROLL-DRAG]` payload with the three new fields.
4. Add a vitest pinning `clampJumpFrames` for the multi-clip-track case.

This is **presentation only**. The math and commit path are untouched.

---

## Audit C — Preview canvas geometry

### C.1 The formula at `gui/src/components/PreviewPlayer.tsx:466-473`

```ts
if (availW / aspectW <= availH) {
  // Width-bound: width = availW, height = availW / aspectW.
  canvasW = availW;
  canvasH = availW / aspectW;          // ← BUG: should be availW * aspectH / aspectW
} else {
  canvasH = availH;
  canvasW = availH * aspectW;          // ← ALSO BUG: should be availH * aspectW / aspectH
}
```

The user's reported "Preview canvas is still extremely small. 16:9 / 9:16 /
3:4 / 4:3 canvas geometry is wrong; only 1:1 appears normal" maps **exactly**
to this formula. The bug is the missing `aspectH` in the height-bound branch
and the wrong divisor in the width-bound branch.

`aspectH` is declared at line 458 (`const aspectH = aspectParts[1] || 9;`) but
**never used** in the canvas dimension computation. It's a dead variable.

### C.2 Numerical reproduction (stage = 720 × 405, inset = 16)

| Aspect | Buggy canvas | Correct canvas | User-visible result |
|--------|--------------|----------------|---------------------|
| 16:9 | 720 × **45** (flat strip) | 720 × 405 (fills stage) | "极小" — height 9× too short |
| 9:16 | 720 × 80 (very wide) | 227.8 × 405 (tall portrait) | way too wide; portrait aspect lost |
| 1:1 | 405 × 405 | 405 × 405 | **works** — only because aspectW=1 and the height-bound branch's `availH * 1` is correct |
| 4:3 | 720 × 180 (very flat) | 540 × 405 (slight letterbox) | height 2.25× too short |
| 3:4 | 720 × 240 (wide) | 303.8 × 405 (tall portrait) | wrong aspect entirely |

The 1:1 case is the **only** aspect where the buggy formula happens to be
right (because `availW / aspectW = availW`, fails the `<= availH` test for
the typical stage, and the height-bound branch's `availH * aspectW = availH`
is correct when `aspectW = 1`). **The user's "只有 1:1 看起来正常" is a
diagnostic of the formula, not a coincidence.**

### C.3 Container vs canvas vs formula — separation of concerns

- **Container (`.preview-pane`, `.preview-stage`)**: ResizeObserver-driven
  `stageSize` is correct. `gui/src/components/PreviewPlayer.tsx:430-443`.
- **Inset** (16px each side, line 460-462): correct.
- **Canvas (`frameStyle`)**: WRONG. The dimensions are derived from the
  buggy formula above.

**The container is large enough** (it accommodates the full available space).
**The canvas itself is small** because the formula divides by the wrong
quantity. The fix is a one-line math change, not a CSS or container change.

### C.4 What about the actual DOM measurement?

Without a running static-with-proxy (only vite dev on 5173 is live; the
audit didn't open a browser to measure), the DOM rect of
`.preview-stage` cannot be captured in this audit window. The math
reproduction is sufficient to prove the formula is wrong.

### C.5 Required regression (not implemented in this audit)

Add a vitest that pins the formula:

```ts
// gui/src/components/PreviewPlayer.test.tsx (extend existing)
import { computeCanvasSize } from "./PreviewPlayer"; // extract pure helper

it("16:9 fit at stage 720x405 → canvas 720x405", () => {
  expect(computeCanvasSize(720, 405, 16, 9)).toEqual({ w: 720, h: 405 });
});
it("9:16 fit at stage 720x405 → canvas 228x405", () => {
  expect(computeCanvasSize(720, 405, 9, 16)).toEqual({ w: 228, h: 405 });
});
it("1:1 fit at stage 720x405 → canvas 405x405", () => {
  expect(computeCanvasSize(720, 405, 1, 1)).toEqual({ w: 405, h: 405 });
});
it("4:3 fit at stage 720x405 → canvas 540x405", () => {
  expect(computeCanvasSize(720, 405, 4, 3)).toEqual({ w: 540, h: 405 });
});
it("3:4 fit at stage 720x405 → canvas 304x405", () => {
  expect(computeCanvasSize(720, 405, 3, 4)).toEqual({ w: 304, h: 405 });
});
```

The pure helper is not yet extracted; the test would force the refactor.

### C.6 Proposed fix (one-line math change, NOT implemented)

```ts
// CORRECT formula (preview-plan.ts-style scale-min)
const scaleW = availW / aspectW;
const scaleH = availH / aspectH;
if (scaleW <= scaleH) {
  canvasW = availW;
  canvasH = scaleW * aspectH;
} else {
  canvasH = availH;
  canvasW = scaleH * aspectW;
}
```

This is **GUI only** (presentation). No server, no contract, no Core data
shape change. **Single-file change.** P0 because the user is currently
seeing a flat strip where a proper 16:9 canvas should be.

---

## Audit D — Hidden visual layer

### D.1 Server side: confirmed correct (R5 remediation #1 holding)

Live test (with lease + baseRevision):
```
$ curl -X POST ':8770/tracks/v9/hide?hidden=true&sessionId=...&baseRevision=1'
{"operation_id":"op00002",...,"before":{"hidden":false},"after":{"hidden":true},...}

$ curl -s ':8770/preview/at_frame?timeline_id=main&frame=450' | jq
{
  "timeline_frame": 450,
  "is_black": false,
  "visual_layers": [
    {"track_id":"v1","layer_index":0,"kind":"image","clip_id":"c039a7b",...}
  ],
  "audio_layers": [],
  "subtitle_texts": [...]
}
# v9 (and its clip ce8fbe0) is absent from visual_layers

$ curl -s ':8770/preview/plan?timeline_id=main' | jq
# tracks[] does NOT include v9 (or any hidden track)

$ curl -s ':8770/project' | jq '.timelines[0].tracks[] | select(.track_id=="v9")'
{"track_id":"v9","kind":"video","hidden":true,...}
# raw project still includes v9 (it stays in data; just hidden)

$ curl -X POST ':8770/tracks/v9/hide?hidden=false&...'  # restore
```

Server invariants are intact:
- `build_preview_plan` excludes hidden tracks (pinned by
  `tests/test_hidden_track_preview_exclusion.py`).
- `composite_preview_at_frame` excludes hidden tracks (same test).
- `/preview/plan` and `/preview/at_frame` agree.
- The `Project` still includes the hidden track (it's in the data, just
  not in the preview plan).

### D.2 GUI side: stale-plan window during refetch

`usePreviewPlan` (`gui/src/preview-plan.ts:191-249`) is keyed by
`(projectRevision, timelineId)`. The plan is only refetched when one of
those changes. `projectRevision` comes from `useProjectSequence` which
polls `/sequence` every ~5s.

**Failure mode**: the user hides v9. The Core mutation succeeds and bumps
`base_revision` from 1 to 2. But the GUI's local `projectRevision` (from
`useProjectSequence`) is still 1 for up to one poll cycle. During this
window, the cached plan still includes v9, and the L1 composite still
shows v9's clip.

**Observed in SESSION.md**: "R5 manual pass IN PROGRESS" — manual
validation on `_sanlihe-r5-manual` is pending. The user may have hit
exactly this stale-plan window.

### D.3 Timeline row visibility: confirmed correct (R5 fix holding)

`gui/src/components/Timeline.tsx` no longer has `display: track.hidden ? "none" : "flex"`
on the rows (R5 remediation #1, commit 2cf5116). The hidden track renders
with `.track-hidden` CSS class (opacity + diagonal hatch). The `.track-label-row`
is also visible (italic, strike label). Pinned by
`gui/src/components/Timeline.hidden.test.tsx` (5 tests).

So: hidden track → row + header both exist (correct, R5 fix intact).
The only remaining issue is the **stale L1 composite** in PreviewPlayer.

### D.4 What is the right fix?

Two options, in order of complexity:

**Option 1 (quick)**: bump a local "dirty" revision on every successful
mutation. The `usePreviewPlan` hook subscribes to the dirty revision and
refetches the plan immediately instead of waiting for the next sequence
poll. This adds 5-10 lines to `usePreviewPlan` and a `bumpDirtyRev()` call
in App.tsx for every `run()` callback.

**Option 2 (clean)**: App.tsx maintains a `hiddenTrackIds: Set<string>`
mirroring the project. The `usePreviewPlan` hook accepts a
`{ excludedTrackIds: Set<string> }` filter and applies it locally to the
cached plan until the next refetch. The plan is then optimistic-consistent
with the user's intent.

Either fix is **read-then-write** to the same `usePreviewPlan` module. The
Core side is unchanged.

### D.5 Required regression (not implemented)

Add an end-to-end test that:
1. Loads the project.
2. Captures the rendered L1 composite (DOM) at frame 450 → expects v1+v9 (current state).
3. Calls `setTrackHidden(v9, true)` via `api`.
4. Within 1 second (no waiting for poll), the L1 composite shows only v1.
5. Unhide v9 → both visible again.

Currently no test exercises this. The static guard tests for the
**server**-side exclusion are in place; the **GUI**-side freshness is not
pinned.

---

## Things that must NOT change in this audit (already correct)

| # | Capability | Why it's correct | Where to find the pin |
| --- | --- | --- | --- |
| 1 | Move path: `finalFrame ∈ Z` | R3-1E invariant, traced in this audit §A.3 | `gui/src/components/ClipBlock.tsx:413-667`, `drag-invariant.test.ts` |
| 2 | `scrollLeft` does NOT enter frame math | R5-B1 invariant, pinned | `ClipBlock.tsx:376-391`, `drag-invariant.test.ts` |
| 3 | Server-side `[0, max_timeline_frame]` guard on `/clips/move` | R3-2 P0-1 invariant | `yroll/server/app.py:918-921`, `tests/test_frame_safety_bounds.py` |
| 4 | `MoveReq.new_timeline_start_frame: int` rejects fractional | Pydantic v2 enforcement (this audit §A.1) | `yroll/server/app.py:83` |
| 5 | `AddClipReq` rejects legacy seconds fields with clear 400 | GUI-03R6 closure | `yroll/server/app.py:540-560` |
| 6 | `ensureReady()` gate before every mutation | R5-B1 invariant | `gui/src/api.ts:202-218` |
| 7 | Track.hidden row-collapse fix from R5 remediation #1 | R5-bug-#1 already fixed | `gui/src/components/Timeline.tsx` (no display:none), `Timeline.hidden.test.tsx` |
| 8 | `build_preview_plan revision parity` fix from R5 remediation #1 | R5-bug-#2 already fixed | `yroll/core/plan.py:126-150`, `tests/test_preview_plan_revision_parity.py` |
| 9 | `/preview/plan` and `/preview/at_frame` frame-native ranges | Both confirmed live: c039a7b is at [412, 502] frames in plan/at_frame | `yroll/server/app.py:1919-1927` |
| 10 | Core `add_image_clip` overlap rejection | Authoritative, raises CommandError correctly | `yroll/core/commands.py` |
| 11 | Core `move_clip` overlap rejection | Authoritative, raises CommandError correctly | `yroll/core/commands.py:1575-1670` |
| 12 | Hidden track exclusion in `build_preview_plan` + `composite_preview_at_frame` | R5-bug-#2 fix, this audit §D.1 confirms | `yroll/core/plan.py`, `tests/test_hidden_track_preview_exclusion.py` |
| 13 | Auto-scroll during drag | R4.1 P0-1, pinned | `gui/src/drag-autoscroll.ts`, `drag-autoscroll.test.ts` |
| 14 | Multi-layer PiP visualization (Decision 4) | Pin the visualization rules, not the persistence | `gui/src/composite-multilayer.ts`, `composite-multilayer.test.ts` |
| 15 | Home centering playhead (R3-W-D) | Center-on-playhead in viewport, frame 0 stays at ContentViewport origin | `gui/src/App.tsx:740-752`, `keymap.test.ts` |
| 16 | `roundHalfAwayFromZero` is the only edit-coordinate rounding | `Math.round` forbidden in edit coords | `tests/test_no_js_round_in_edit.py` |
| 17 | Standard NTSC DF (closed-form) | No pinned dict | `yroll/core/timeframe.py`, `gui/src/frames.ts` |
| 18 | Fit Content (R4.2 P1-1) | First-load auto-fit + manual button | `gui/src/App.tsx:461-481, 875-905`, `fit-content.test.ts` |
| 19 | Static guard: `gui/src/components/ClipBlock.tsx` cannot use `Math.round` on edit coords | Architecture-level | `tests/test_no_js_round_in_edit.py` |
| 20 | Static guard: `mcp_server.py` cannot call `ProjectCore(` directly | Sole-writer architecture | `tests/test_no_writes_outside_server.py` |

---

## Recommended next step (for human review before any code change)

This audit recommends **a single R6.1 closure batch** addressing:

1. **C — Preview canvas geometry (P0)**: one-line fix in
   `gui/src/components/PreviewPlayer.tsx:466-473` + add 5 vitest cases
   pinning the 5 standard aspects. Single-file change. Unblocks the user's
   most visible defect.

2. **A — Inspector trim buttons (P0)**: convert `±0.5s` to `±15 frames`
   at the call site (`App.tsx:1217-1218, 1598-1601`). The `displayProject`
   `end: s + len` rebuild can be left as-is (it's visual-only) but a static
   guard preventing `api.trim` with float would close the entire bug class.

3. **D — Stale L1 composite after hide (P1)**: add a `bumpDirtyRev()` after
   every `setTrackHidden` mutation; `usePreviewPlan` refetches immediately.
   Defense in depth: don't trust the cache to be fresh.

4. **B — Clamp-boundary presentation (P1)**: render dragged clip with
   dashed red outline when `tryStart !== clamped`. **No change to math or
   commit path.** Measurement still required (no live browser in this audit
   window).

**Do NOT implement**: Publish Metadata, Timeline-local Revision, Keyframes,
opacity controls, AI features.

---

*Audit by R6.1 audit-only mandate. No code in `yroll/`, `gui/src/`, or
`tests/` was modified.*
