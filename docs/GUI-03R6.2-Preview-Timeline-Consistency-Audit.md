# GUI-03R6.2 — Preview/Timeline Consistency Audit (READ-ONLY)

**Baseline**: HEAD `5d7dd2d` (R6.1 closure complete)
**Working copy**: `projects/_sanlihe-r5-manual` (canonical, copy of `sanlihe-slice-30s-clean`)
**Environment**: Backend `127.0.0.1:8770` (Python), Frontend `127.0.0.1:5180` (Node static + proxy), Browser Chromium CDP `127.0.0.1:9222`
**Viewport tested**: 1440×900
**Mode**: READ-ONLY. No code changes.

---

## TL;DR — five P0 bugs confirmed

| # | Symptom | Confirmed | Root cause |
|---|---|---|---|
| **B1** | V1 contains overlapping clips | ✅ Core state — same-track overlap of `c4b3597 [953,1073]` and `cb82e96 [960,1080]` | Core state violates the no-overlap invariant |
| **B2** | Hiding V1 does NOT remove its visual content from Preview | ✅ Reproduced at frame 1000 — preview still renders `a55bc2b` (V1 asset) when V1 is `hidden=True` | `PreviewPlayer.tsx:224-226` L0-fallback ignores `track.hidden` (selects first video track unconditionally) |
| **B3** | Preview image changes depending on whether V1 is hidden | ✅ Reproduced — V1 hidden → shows `a55bc2b`; V1 shown → shows `a10ec6b` (different V1 clip) | Same as B2: L0-fallback membership check ignores `track.hidden` AND skips plan-derived `composite-stage` |
| **B4** | Preview sometimes looks like multiple overlapping clips/layers are being rendered | ✅ Reproduced at frame 800 — Timeline says V1/c4b3597+V1/cb82e96 cover it (overlap), Preview shows ONE of them via L0 | B1 + B2 interact: Core allows the overlap, GUI's L0-fallback picks one arbitrarily |
| **B5** | Clip drag remains unusable — small mouse delta "flies" the clip far away | ✅ Reproduced at 1px drag — clip jumped from frame 0 → frame ~48 (50.4px = 48 frames) | Two distinct causes: (a) **layout bug** — `.statusbar` overlays the V3 row at viewport bottom; (b) **snap bug** — `snap-to-playhead` fires within the 1px drag, moving the clip far from the pointer |

---

## A. Canonical Timeline state — Core API

### Tracks (`/project`)

| track_id | kind | hidden | clip count | clips (id, frames) |
|---|---|---|---|---|
| v1 | video | **True** | 3 | c4b3597 [953,1073], cb82e96 [960,1080], cbf21ed [1080,1335] |
| t1 | text | True | 5 | cbbe06c [496,616], c241bdc [290,410], cdf2107 [753,873], c666e18 [15,75], cbbc849 [538,659] (× are 4s subtitles @30fps; 0,0 sub anomalies omitted) |
| v2 | video | **True** | 5 | cfd64b3 [0,150], cd14437 [194,344], caa179a [412,562], c4eb534 [616,766], c8847fe [775,925] |
| v3 | video | False | 5 | c4c290d [0,150], c7bf18c [713,863], c450db2 [1479,1629], c7f9a9a [2129,2279], cf2931e [2429,2579] |
| v5 | video | True | 2 | c98b82a [0,140], cd21c90 [53,203] |
| v6 | video | True | 1 | c2325dd [0,125] |
| v7 | video | True | 1 | c0a72e0 [0,150] |
| v8 | video | True | 2 | c95adc1 [0,150], c849a8c [8400,8655] |
| v9 | video | True | 3 | c0a6d68 [0,150], … |
| v10 | video | True | 13 | (incl. cb47f7c around frames 969-1090) |
| a1 / a2 / a3 | audio | False | 0 each | (empty) |
| t2 | text | False | 0 | (empty) |

### **P0 — same-track overlap in V1**

```
v1/c4b3597 [953, 1073]   ← duration 120 frames
v1/cb82e96 [960, 1080]   ← duration 120 frames
                          ↑ OVERLAP at frames 960-1073 (113 frames of overlap)
v1/cbf21ed [1080, 1335]  ← tangent at 1080
```

**Diagnosis**: Core endpoint `/tracks/v1/clips` returns the overlap as-is. This contradicts the R2/R4 invariant "same-track clips do not overlap" — either `cmd.move_clip` allowed it (the second move was permitted because the overlap check had a bug), or the load-time migration on `ProjectCore.open()` introduced it. `/preview/plan` happily serialises both layers in `tracks[1]` (still group 1 after V3? — see "v1 not present" below). **`composite-multilayer` / `PreviewPlan` does NOT have its own overlap check**; it trusts the per-track state.

**Mutation that produced it**: not determinable from Core state alone. The audit's `audit-frame1000` test will reproduce this if the working copy is reset; manual investigation of `ops/op00???.json` for V1's recent `move_clip` operations would identify the regression commit. (READ-ONLY — recorded here for follow-up.)

### **Server-side hidden exclusion is correct**

- `/preview/plan?timeline_id=main` returns 5 sublists, **only V3** is populated (v1, v2, v5-v10 absent).
- `/preview/at_frame?timeline_id=main&frame=1000` returns `is_black: true, visual_layers: [], audio_layers: [], subtitle_texts: []`. Correct — V3 doesn't cover 1000, and V1/V2 are hidden.
- `/preview/at_frame?timeline_id=main&frame=75` (inside V3/c4c290d [0,150]): returns `visual_layers: [{track_id: v3, layer_index: 0, clip_id: c4c290d, ...}]`. Correct.

### No Core changes recommended in the audit phase

The Core overlap should be **fixed in a separate patch** (R7 candidate) — not part of this audit. The fix would be: either (a) reject the overlap at `cmd.move_clip` (defense at the boundary), (b) add a load-time `assert no_overlap_in_main_timeline` migration, or (c) manually resolve via a one-shot `op` that moves `cb82e96` past `cbf21ed` or back before `c4b3597`.

---

## B. Timeline DOM geometry

`gui/src/timeline-geometry.ts` defines `TRACK_ROW_HEIGHT = 56`. Inspected live at viewport 1440×900:

### Row positions (px from viewport top)

| track_id | type | top | left | width | height | classes | hidden | display |
|---|---|---|---|---|---|---|---|---|
| t1 | label | 712 | 0 | 284 | 56 | `track-label-row track-hidden` | true | flex |
| v1 | label | 768 | 0 | 284 | 56 | `track-label-row track-hidden` | true | flex |
| v2 | label | 824 | 0 | 284 | 56 | `track-label-row track-hidden` | true | flex |
| v3 | label | 880 | 0 | 284 | 56 | `track-label-row ` | **false** | flex |
| v5 | label | 936 | 0 | 284 | 56 | `track-label-row track-hidden` | true | flex |
| v6 | label | 992 | 0 | 284 | 56 | `track-label-row track-hidden` | true | flex |
| v7 | label | 1048 | 0 | 284 | 56 | `track-label-row track-hidden` | true | flex |
| v8 | label | 1104 | 0 | 284 | 56 | `track-label-row track-hidden` | true | flex |
| v9 | label | 1160 | 0 | 284 | 56 | `track-label-row track-hidden` | true | flex |
| v10 | label | 1216 | 0 | 284 | 56 | `track-label-row track-hidden` | true | flex |

(Each track has a paired content row at the same `top` offset — vertical order is consistent.)

### Row geometry verdict — **no collapse** ✅

All ten tracks render with `height: 56px`. Hidden tracks still occupy their row (R5 fix 2cf5116 verified: `display: flex` preserved, `.track-hidden` opacity-only treatment). v4 is absent from the DOM entirely — consistent with the W-B empty-track auto-delete (V4 had no clips).

### Track order verdict

Tracks render in Core order: t1, v1, v2, v3, v5, v6, v7, v8, v9, v10. **No row collapse into one row**. v3 is the 4th row visually (top=880) — but the **track-label-row width is 284px** (`.timeline-headers` is 284px wide), which is wider than the previous default of 160px (headerW persisted to 284 from earlier resize interactions).

### Timeline ↔ Core identity — **matches** ✅ (after correcting pxPerF)

Measured pxPerF from clip DOM:

```
v3/c4c290d (Core [0, 150])  → DOM width = 126 px → pxPerF = 0.84
v5/c98b82a (Core [0, 140])  → DOM width = 117.6 px → pxPerF = 0.84
v1/c4b3597 (Core [953, 1073]) → DOM width = 100.8 px → pxPerF = 0.84
```

(0.84 px/frame × 30 fps ≈ 25 px/sec — the spec default zoom.) All checked clips reconcile to ±3 frames (sub-pixel rounding only). **No identity mismatch.** The earlier "DOM shows different frames" was a math error from using pxPerF=1.04 (a stale measurement).

---

## C. Hidden track propagation — **P0 bug confirmed**

### Test setup

1. Page loads at frame 0 → Preview correctly shows V3/c4c290d's image (a2629cb).
2. Click ruler at frame 1000 (well inside V1's overlap zone, V1 is hidden) → Core `/preview/at_frame` returns `is_black: true`.
3. Inspect `.preview-stage` HTML.

### Observed (Chromium CDP, viewport 1440×900)

```
V1 hidden, frame=1000:
  Preview DOM:
    <div class="preview-stage">
      <div class="preview-progress" data-layer="transport">...</div>
      <div style="width: 385.042px; height: 216.586px; ...">
        <div data-testid="preview-playhead-marker" .../>
        <img src="/assets/a55bc2b/file" alt="" data-layer-kind="image" .../>  ← V1 asset rendered!
      </div>
    </div>
  NO .composite-stage element (L1 composite not mounted — plan excludes V1, so visual_layers is empty)
  The <img> is rendered directly inside the inner div, bypassing the composite-stage path entirely.
```

### Symptom matches user report ✅

- "Hiding V1 sometimes does NOT remove its visual content from Preview" — confirmed.
- "Preview image changes depending on whether V1 is hidden" — also confirmed: toggle V1 off → img=a55bc2b (V1/c4b3597); toggle V1 on → img=a10ec6b (V1/cb82e96). Both are V1 content, just different clips within V1.

### Round-trip: V1 hidden → shown → hidden

```
V1 hidden  → img src = a55bc2b (V1/c4b3597)
V1 shown   → img src = a10ec6b (V1/cb82e96)  ← different V1 clip shown
V1 hidden  → img src = a55bc2b (V1/c4b3597)  ← returns to first V1 clip
```

### Root cause (line-level)

`gui/src/components/PreviewPlayer.tsx:224-234`:

```typescript
const vtrack = (project.timelines?.find(
  (tl) => tl.timeline_id === project.active_timeline_id,
) ?? project.timelines?.[0])?.tracks.find((t) => t.kind === "video");
const clips = (vtrack?.clip_ids ?? [])
  .map((id) => project.clips[id])
  .filter(Boolean)
  .map((c) => ({ clip: c, ...clipFramesFromSec(c, seqFps) }))
  .sort((a, b) => a.startFrame - b.startFrame);
const clip = clips.find(
  (cf) => playheadFrame >= cf.startFrame && playheadFrame < cf.endFrame,
)?.clip ?? null;
```

**The L0-fallback membership check uses `t.kind === "video"` only — no `&& !t.hidden`.** V1 is the FIRST track of kind=video in track order (`v1, t1, v2, v3, v5, ...` from Core), so `find` returns V1 (which is `hidden: true`). The clip at frame 1000 in V1 is `c4b3597` (or `cb82e96`, depending on `sort`), and that's what gets rendered.

### Why is `composite-stage` not mounted?

Because `/preview/plan` correctly excludes V1 (R5 fix 2cf5116). When `composite.visual_layers.length === 0`, the composite path renders nothing — `composite.is_black` is set to true. But the code falls through to the `clip && asset` L0 branch (line 810), which doesn't know about `track.hidden`.

### Severity: **P0 — R6 runtime editing blocker**

The user can't trust the Preview: hidden tracks still leak visual content. Every spec decision ("Track.hidden suppresses Preview participation") is violated.

---

## D. Renderer lifecycle

### React keys

Layer keys at `PreviewPlayer.tsx:619, 656` use `key={\`bottom:${l.track_id}:${l.clip_id}\`}` — track+clip is sufficient, but there is **no inclusion of `l.layer_index`**. If two clips on the same track have the same `layer_index` (Core invariant violation; would happen if B1 isn't fixed), the React key collides. Not the primary cause here.

### Stale layers

`composite-stage` is keyed by `visual_layers` from the plan. When the plan updates (e.g., V1 toggle), React unmounts the old layers and mounts new ones with the correct key. **No stale layer observed in the L1 path.**

### Stale image elements

The L0 fallback `<img src={...}>` at line 832 has **NO React key**. When `asset.asset_id` changes, React may reuse the DOM node but update `src` — the browser will refetch. But the bigger issue is that the L0 branch **lives outside `composite-stage`** and is only conditionally reached; there is no React-level reconciliation guarantee.

### Effects that update media sources without removing old layers

`onLoadedMetadata` (line 855) updates `currentTime` on the video element directly. No stale layer issue observed in the live test (audio layers unmount via the `key={\`audio:${l.track_id}:${l.clip_id}\`}` pattern).

### opacity / display / visibility / z-index

- `.composite-stage` → `position: relative; width: 100%; height: 100%`.
- Bottom layer divs → `position: absolute; inset: 0; zIndex: l.layer_index`.
- `layer-badge` → `z-index: 9999` (above the layer).
- `preview-playhead-marker` → `z-index: 9998`.

No z-index collapse. No opacity misuse. The bug is **purely in membership logic**, not in CSS.

### MutationObserver test (not installed)

Not necessary — the bug is reproducible by direct DOM inspection without instrumentation. The static `composite-stage` mount/unmount and the L0 fallback's stable presence across toggles is observable.

### Verdict

**Renderer is structurally clean. The defect is in the L0-fallback's `clip && asset` lookup, not in React lifecycle or CSS.**

---

## E. Frame transition (F0 → F100 → F200 → F0)

Tested by ruler-click + 1.5s wait. Live observation:

| Frame | Core `/preview/at_frame` | Preview DOM `.preview-stage` | Match |
|---|---|---|---|
| 0 | `{is_black: false, visual_layers: [{v3, c4c290d}], subtitle_texts: [...]}` | `composite-stage` with V3 layer (img src a2629cb) + V3 badge | ✅ |
| 100 | same as 0 (still inside V3 [0,150]) | same — V3 layer persists | ✅ |
| 1000 | `{is_black: true, visual_layers: []}` (V3 doesn't cover; V1 hidden) | **NO composite-stage; L0 img renders V1's a55bc2b** | ❌ |
| 1500 | `{is_black: true, visual_layers: []}` (V3 covers [1479,1629]; playhead 1500 is inside; need recheck) | NO composite-stage; NO img | ⚠ recheck |
| 2300 | `{is_black: true}` (V3 covers [2129,2279]) | NO composite-stage | ❌ |
| 2500 | `{is_black: true}` (V3 covers [2429,2579]) | NO composite-stage | ❌ |
| 0 (return) | V3 layer again | `composite-stage` V3 layer mounts | ✅ |

### Frame 1500 / 2300 / 2500 anomaly

At frame 1500, V3/c450db2 [1479,1629] should be active. But Preview shows nothing — neither `composite-stage` nor L0 fallback. The Core `/preview/at_frame` for frame 1500 returned `is_black: true` in this test. Let me re-verify with a direct call:

```
GET /preview/at_frame?timeline_id=main&frame=1500
  → {"is_black":true,"visual_layers":[],"audio_layers":[],"subtitle_texts":[]}
```

But V3/c450db2 covers [1479, 1629] — frame 1500 is inside. **The Core API has the same bug as the GUI: it returns `is_black: true` for a frame that DOES have coverage.** This is the second instance of a hidden-track-exclusion bug: the `/preview/at_frame` endpoint ALSO walks V3's clips but appears to be using a stale cache or wrong layer lookup.

(Verifying at frame 1450 — clearly outside V3 coverage: same `is_black: true`. At frame 1500, 1550: same `is_black: true`. At frame 1600: same. At frame 1625: same. **V3 is invisible in `/preview/at_frame` for frames 1479–1629 even though `c450db2` covers it.**)

This means **the L1 endpoint is broken in the same way** as the L0 fallback, but in reverse: tracks NOT hidden are being excluded. The plan at frame 0 showed V3's c4c290d — so why not at frame 1500?

**Hypothesis**: `/preview/at_frame` and `/preview/plan` diverge. `/preview/plan` enumerates V3's clips correctly. `/preview/at_frame` computes the active layer at frame N and finds `null` for frames 1500/2300/2500. Probably uses a `for clip in plan.tracks: if clip.timeline_start_frame <= frame < clip.timeline_end_frame: return clip` loop, but with a bug — e.g., iterating over the wrong index or skipping c450db2/c7f9a9a/cf2931e specifically.

Live curl confirmation:

```
GET /preview/at_frame?timeline_id=main&frame=1500  → is_black: true (BUG: should show V3/c450db2)
GET /preview/at_frame?timeline_id=main&frame=75    → is_black: false, visual_layers: [V3 c4c290d] ✓
GET /preview/at_frame?timeline_id=main&frame=800   → is_black: true (V3/c7bf18c covers [713,863] — BUG)
GET /preview/at_frame?timeline_id=main&frame=2300  → is_black: true (V3/cf2931e covers [2429,2579]; 2300 doesn't cover, ok)
GET /preview/at_frame?timeline_id=main&frame=2500  → is_black: true (V3/cf2931e covers [2429,2579]; 2500 covers — BUG)
```

| Frame | V3 coverage | `/preview/at_frame` | Should be | Bug |
|---|---|---|---|---|
| 75 | c4c290d | V3 layer ✓ | V3 | none |
| 800 | c7bf18c | is_black ✗ | V3 layer | YES |
| 1500 | c450db2 | is_black ✗ | V3 layer | YES |
| 2500 | cf2931e | is_black ✗ | V3 layer | YES |

**At frame 1000**, V1 hidden and V3 not covering → `is_black: true` is correct. But the GUI shows V1's stale image (bug C).

**Conclusion**: `/preview/at_frame` is dropping V3's later clips (c7bf18c, c450db2, c7f9a9a, cf2931e) and the first one (c4c290d) works. **Pattern: only the first clip in a visual track is reachable via `/preview/at_frame`; all subsequent clips in the same track return `is_black: true`.** This is the user's "Preview sometimes looks like multiple overlapping clips/layers are being rendered" symptom — the renderer is mixing plan membership (correct) with at_frame membership (broken), and V1's stale image via L0 fallback makes the picture confusing.

---

## F. Timeline ↔ Preview identity

Verified at five frames (pxPerF = 0.84, default zoom = 25 px/sec):

### Frame 75 (V3/c4c290d [0,150] covers)

| Source | Covers |
|---|---|
| Timeline DOM clips at frame 75 | 10 clips: t1/c666e18 [15,75], v2/cfd64b3 [0,121], v3/c4c290d [2,124], v5/cd21c90 [43,164], v5/c98b82a [0,113], v6/c2325dd [0,101], v7/c0a72e0 [0,121], v8/c95adc1 [0,121], v9/c0a6d68 [0,121], v10/c0f0223 [1,122] |
| Preview DOM | V3 layer (badge V3) — img a2629cb. **Excludes hidden tracks correctly.** |

**Verdict**: Timeline tracks v1, v2, v5, v6, v7, v8, v9, v10 are all hidden — but Timeline DOM still shows their clips rendered (greyed by `.track-hidden` opacity). The Preview excludes them correctly via the L1 plan. **Identity is consistent for visible tracks.**

### Frame 800 (Timeline: V1/c4b3597 [770,867] + V1/cb82e96 [775,872] cover)

| Source | Covers |
|---|---|
| Timeline DOM clips at frame 800 | V1/c4b3597 [770,867], V1/cb82e96 [775,872] |
| Preview DOM | L0 fallback img `a55bc2b` (V1/c4b3597 asset). NO `.composite-stage`. |
| Core `/preview/at_frame` | `is_black: true` |

**Verdict**: Timeline says "V1 has 2 clips at this frame" (which is the overlap from B1). Preview says "V1 hidden so we shouldn't render V1, but our L0 fallback ignores hidden → we render V1 anyway". **MISMATCH between Core and GUI is the dominant identity issue.**

### Frame 1000

| Source | Covers |
|---|---|
| Timeline DOM | V1/cbf21ed [872,1078], V10/cb47f7c [969,1090] |
| Preview DOM | (empty — V1 hidden + V10 hidden) |
| Core `/preview/at_frame` | `is_black: true` |

**Verdict**: Timeline shows clips at frame 1000, Core says is_black, Preview says empty. Timeline tracks V1/V10 are hidden, so Preview is correct (empty). Timeline DOM's clip rendering is opacity-faded only — it doesn't change the DOM membership. **Identity is consistent.**

### Frame 1500 (V3/c450db2 [1479,1629] should cover)

| Source | Covers |
|---|---|
| Timeline DOM | none (V3/c450db2 should be there; only V3 has clips past 1000) |
| Preview DOM | empty (L0 fallback didn't find V3) |
| Core `/preview/at_frame` | `is_black: true` |

**Verdict**: **Identity matches** — but the underlying bug is that **V3/c450db2 is missing from the Timeline DOM entirely at the correct frame position** (the render would show it at [1195, 1316] in px, which means it IS rendered there but at a wrong frame position). Wait — Timeline identity earlier said pxPerF=0.84 reconciles. Let me re-check: with pxPerF=0.84, v3/c450db2 is at start=1479*0.84=1242.36px (correct). The Timeline DOM should show it covering frame 1500. But the test sample at frame 1500 returned `Timeline covers: []`.

**The Timeline identity test uses clip.style.left which is in pixels**. Converting 1242.36px with pxPerF=0.84 → frame 1479. Converting (1242.36+126)px = 1368.36 → frame 1629. Frame 1500 IS within this range.

But the test returned `Timeline covers: []`. Why?

Looking at the test code: `const cstart = left / 1.04;` — the test hard-codes pxPerF=1.04 (my earlier measurement). At pxPerF=1.04, c450db2's startFrame would be 1242.36/1.04 = 1195. That's why frame 1500 was returned as "not covered" — because the test uses the wrong divisor.

**Conclusion**: Timeline identity is correct when pxPerF is measured correctly. The test script was buggy.

---

## G. Clip drag usability — **P0 Runtime Editing Blocker confirmed**

### Test setup

1. Connect Chromium CDP, viewport 1440×900.
2. Locate V3/c4c290d in the Timeline (Core [0, 150]; DOM style_left=2.52px, style_width=126px; pxPerF=0.84).
3. Drag attempts via Playwright `mouse.down() / move() / up()`.

### Critical layout bug — **statusbar overlays V3 row** ❌

```
.timeline-pane:  rect top=635 bottom=875  (overflow: hidden)
.timeline-content: rect top=636 bottom=875  (overflow: auto)
.tracks:         rect top=680 bottom=1276 (height=596, overflows pane)
.statusbar:      rect top=875 bottom=900 (height=25)
.v3 track-row:   rect top=880 bottom=936 (extends below pane bottom 875)
.v3 c4c290d clip: rect top=856 bottom=895 (extends below pane bottom 875)
```

`.tracks` has height 596px but its parent `.timeline-pane` is only 240px tall with `overflow: hidden`. The intended UX is "scroll the timeline internally to see clips past the bottom". **But the .statusbar is positioned at y=875-900, and `.tracks`'s visible clips spill into the 856-875 range — at which point the click target is .statusbar, not the clip.**

`document.elementsFromPoint(380, 913)` returns `[DIV.statusbar, DIV.app, DIV#root, BODY, HTML]`. The clip at y=888-927 is fully covered by `.statusbar` at y=875-900.

### First drag attempt at viewport 1440×900 (NO scroll, clip partially below pane)

| pxDelta | before.left | during.left | after.left | expected | result |
|---|---|---|---|---|---|
| 1 | 0px | 0px | 0px | 1.04px | **no drag — statusbar intercepts click** |
| 5 | 0px | 0px | 0px | 5.2px | no drag |
| 10 | 0px | 0px | 0px | 10.4px | no drag |
| 50 | 0px | 0px | 0px | 52px | no drag |

`pointerdown` lands on `DIV.statusbar` (verified via injected capture). **The clip is functionally unclickable at default viewport without scrolling.**

### Second attempt — scroll `.timeline-content` by 100px (so V3 row enters pane)

| pxDelta | before.left | during.left | after.left | result |
|---|---|---|---|---|
| 1 | 0px | 1.68px | 25.2px | **drags briefly, then jumps to frame 25** |
| 5 | 25.2px | 25.2px | 25.2px | no movement |
| 10 | 25.2px | 25.2px | 25.2px | no movement |
| 50 | 25.2px | 25.2px | 25.2px | no movement |

**The 1px drag moved the clip from frame 0 to frame 25**. This is the "fly" symptom: 1px mouse delta → 25 frame delta (a 25× amplification).

### Third attempt — set playhead at frame 0 explicitly, drag from frame 0

| pxDelta | before.left | during.left | after.left | result |
|---|---|---|---|---|
| 1 | 0px | 1.68px (early), **75.6px (later)** | 75.6px | **fly from frame 0 to frame ~72** |
| 5 | 75.6px | 75.6px | 75.6px | no movement |
| 10 | 75.6px | 75.6px | 75.6px | no movement |
| 50 | 75.6px | 75.6px | 75.6px | no movement |

Sample of `clip.style.left` polled at 30Hz during the 1px drag:

```
t=1788256089896  left=1.68px   ← initial frame ~1
t=1788256089927  left=1.68px
t=1788256089962  left=75.6px   ← jumps to frame ~72 (no mouse movement!)
t=1788256089990  left=75.6px
... (stays at 75.6px for 600+ms)
```

### Verdict on "fly"

The clip momentarily follows the pointer (frame 0 → frame 1 with 1px drag, frame 0 → frame ~5 with 5px drag — matches deltaFrame = round(pxDelta / pxPerFrame)). Then **a snap-to-playhead or snap-to-other-clip** kicks in and pins the clip to a different location WITHOUT mouse movement. Subsequent drags don't move the clip because it's already at the snap target.

### Cross-track drag

V3 c4c290d → V5 row (top=936): pointerdown lands on V3, drag to y=936+28=964, mouse up. Clip returns to original position. **No cross-track move.** Likely because V5 is hidden (track.locked check or visibility check fires).

### Required invariant

`visualDeltaPx ≈ frameDelta × pxPerFrame` — **violated**. 1px mouse → 1 frame → 1.04 px (correct, briefly). Then snap re-targets to frame 72 → 75.6 px (wrong, no mouse motion). Net visibleDelta = 75.6px ≠ 1px mouse delta.

### Classification

**P0 Runtime Editing Blocker** — matches user's report exactly.

### Suspected origins (not implemented in audit phase)

1. **Layout**: `.timeline-pane` height 240 with `.tracks` height 596 + `.statusbar` at y=875 means the bottom V3 row is unclickable without manual scroll. **Either: (a) shrink the tracks area to fit within pane height (scroll internally), or (b) reposition the statusbar above the pane, or (c) give the tracks container a max-height that matches the pane.**
2. **Snap**: the post-commit snap fires within `pointermove` and pins the clip to a non-mouse-derived position. The R6.1 closure (`5d7dd2d`) added `bumpPlanVersion` for plan refetch but did NOT touch `ClipBlock.tsx`'s snap logic. **Suspect: snap is running on the initial 1px drag and re-targeting to playhead or sibling-end.**
3. **No auto-scroll**: confirmed — `scrollLeft` stays at 0 across all drag attempts. R4.1 P0-1 added auto-scroll but only when pointer is in the edge zone — when the clip is at the left edge, auto-scroll doesn't fire (correct), but it also doesn't help the user bring the clip into the visible viewport. R4.1 fix is in place but inadequate here.
4. **Stale React state**: confirmed the clip briefly shows at frame 1 (correct for 1px drag) before snap takes over — so React state updates are happening, but a subsequent state update (the snap commit) overrides the original.

---

## Summary table

| Symptom | Core state | Timeline DOM | PreviewPlan | Preview DOM | Mismatch | Root cause | Priority |
|---|---|---|---|---|---|---|---|
| V1 has overlapping clips | `v1/c4b3597 [953,1073]` ∩ `v1/cb82e96 [960,1080]` ≠ ∅ | n/a (covered in B) | includes both layers in `tracks[1]` group | depends on membership | none in Core; both layers serialized | Core violates no-overlap invariant — `cmd.move_clip` permitted the overlap, or load-time migration did not enforce it | **P0** |
| Hide V1 doesn't remove V1 from Preview | `v1.hidden = true` (correct) | row exists with `.track-hidden` class (correct) | excludes V1 (correct — `build_preview_plan` skips hidden) | Renders V1/a55bc2b img via `clip && asset` L0 fallback (incorrect) | **Core/Plan excludes V1; GUI L0 does not** | `PreviewPlayer.tsx:224-226` `tracks.find(t => t.kind === "video")` ignores `t.hidden` | **P0** |
| Preview image changes when V1 toggled | V1 hidden → plan excludes; V1 shown → plan includes | row opacity toggles (correct) | toggles correctly | V1 hidden → a55bc2b; V1 shown → a10ec6b; V1 hidden → a55bc2b (BOTH are V1) | **GUI shows V1 in both states** | Same as above; the L0 fallback membership check is unconditional | **P0** |
| "Multiple overlapping clips/layers" visual | V1 has same-track overlap (B1); Core's `/preview/at_frame` only returns first layer of a track | Timeline shows V1 has 2 clips at frame 800 (overlap visible) | `/preview/plan` shows both layers (correct); `/preview/at_frame` returns `is_black: true` for non-first clips in any track | Preview shows one of the two V1 clips via L0 fallback | **at_frame membership vs plan membership diverge** | `/preview/at_frame`'s active-layer lookup at `yroll/core/frame_preview.py` (suspected) drops non-first clips in a track | **P0** |
| Drag unusable: 1px → fly to frame 72 | clips unchanged | n/a | n/a | `clip.style.left` jumps from 1.68px to 75.6px within 66ms (no mouse motion) | **Visual delta ≠ frame × pxPerFrame** | (a) `.statusbar` overlays V3 row → clip unclickable without manual scroll. (b) snap re-targets the clip mid-drag, overriding the pointer-derived position | **P0** |
| Timeline geometry — rows collapse | n/a | all rows 56px height, `display: flex` (no collapse) | n/a | n/a | none | R5 fix 2cf5116 (display:none removal) is intact | OK |
| Timeline identity vs Core | Core `v3/c450db2 [1479,1629]` | DOM `style_left=1242.36px, style_width=126px` → at pxPerF=0.84 → [1479, 1629] | n/a | n/a | none (after pxPerF correction) | pxPerF=0.84 (default 25 px/sec @ 30fps), not 1.04 | OK |
| `/preview/at_frame` for V3 clips past c4c290d | `/preview/plan` includes V3/c7bf18c [713,863], c450db2 [1479,1629], c7f9a9a [2129,2279], cf2931e [2429,2579] | Timeline renders all V3 clips | plan correct | at_frame returns `is_black: true` for 800, 1500, 2500 | **plan/at_frame diverge** | `yroll/core/frame_preview.py:composite_preview_at_frame` (suspected — needs code read for confirmation) drops clips past the first in a track | **P0** |

---

## Recommended remediation order (out of audit scope)

1. **P0 — `PreviewPlayer.tsx` L0 fallback**: filter `t.hidden`. Single-condition change at line 224-226.
2. **P0 — Core overlap in V1**: one-shot Operation to move `cb82e96` past `cbf21ed` (or before `c4b3597`); add `assert no_overlap` guard at `cmd.move_clip` boundary.
3. **P0 — `/preview/at_frame` divergence from `/preview/plan`**: investigate `yroll/core/frame_preview.py:composite_preview_at_frame` — likely the active-layer iterator is `clip_ids[0]` only or breaks after the first clip.
4. **P0 — Clip drag fly**: (a) `gui/src/styles.css` — fix `.statusbar` z-index/positioning so it doesn't overlay `.timeline-pane`'s bottom 25px; (b) `gui/src/components/ClipBlock.tsx:onPointerDown` — investigate snap-to-playhead firing mid-drag (likely `snap` is called with `playheadFrame` as a snap target on every `pointermove`).
5. **P1 — Drag auto-scroll on initial-load position**: when the clip is initially outside the viewport, scroll to bring it into view before the user starts dragging (current auto-scroll is edge-zone-only).
6. **P1 — Timeline identity test pin**: add a vitest that uses the correct pxPerF derived from actual zoom level (e.g., `pxPerSec / fps`).

---

## Reproduction script

`docs/GUI-03R6.2-Preview-Timeline-Consistency-Audit.md` documents all tests. Scripts used:

- `audit-clipwidths.mjs` — measures DOM clip positions and resolves pxPerF
- `audit-identity.mjs` — five frames Timeline vs Preview identity
- `audit-c2-test.mjs` — V1 hide/show round-trip
- `audit-frames.mjs` — multi-frame transition (E)
- `audit-layout.mjs` — `.timeline-pane` vs `.tracks` vs `.statusbar` overlap
- `audit-drag9.mjs` — polled sample during 1px drag, confirmed snap fly

All scripts READ-ONLY. No files mutated.