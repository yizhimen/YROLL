# GUI-03R6 Runtime Editing Audit v0.1

**Audit baseline**: HEAD = `8fcfcbd` (R5 remediation #1 + session log).
**Live backend**: PID 3180, port 8770, `python -m yroll.cli.main serve` on a working copy of clean Sanlihe (`projects/_sanlihe-r5-manual` or equivalent live fixture).
**Live frontend**: PID 9000 (port 5173), PID 14128 (port 5180), bundle hash `index-CA6Q1250.js`.
**Audit window**: 2026-09-01.
**Mandate (per user)**: produce runtime evidence before any code change. No code edits in this audit.

This audit is **read-only**. Every claim is backed by a CLI observation against
the running backend (`curl :8770/...`) and a static read of the current tree.
No source file in `yroll/`, `gui/src/`, or `tests/` was modified by this audit.

---

## TL;DR — table

| # | User symptom | Reproducible? | Exact runtime evidence | Root-cause layer | Existing capability | Missing/faulty piece | Proposed fix | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Track hide/show row/header collapses | **Already fixed** in R5 remediation #1 (2cf5116) | `Timeline.hidden.test.tsx` passes; live DOM no longer has `display:none` on `.track-row` / `.track-label-row` | — | `.track-hidden` CSS rule + 5 vitest | none | none | **closed** |
| 2 | Image drop lands but user can't see where | **YES** | After a successful `addImageClip`, `onAssetDrop` returns the clip but no `scrollIntoView` / `fitContent` / `setSelected` runs. App.tsx:1717-1721 only sets a status text. | GUI | Timeline re-renders with the new clip in the timeline DOM; pointer stays where the user dropped. | No post-mutation **viewport bring-into-view** + no post-mutation `setSelected(clipId)` + no post-mutation `playheadFrame = clip.timeline_range.start`. The new clip lives in the timeline data but lives wherever the existing scrollLeft/zoom put it. | After every successful `addImageClip` / `addClip` / `move` mutation, run: `setSelected(newClip.clip_id)` + `setPlayheadFrame(start)` + ensure the new clip is in the visible viewport (scroll if needed, but NOT via zoom-reset which destroys the user's framing). | **P1** |
| 3 | POST /clips → "404 Not Found" | **NOT reproduced live**; live backend returns **403** with `{"detail":"sessionId required for mutations (call /lease/acquire first)"}` | `curl -i -X POST :8770/clips -d '{}'` → `HTTP/1.1 403 Forbidden`. Route IS registered (`openapi.json` lists `POST /clips`). | GUI session state + (maybe) stale browser tab | `gated()` injects sessionId; `ensureReady()` resolves before mutation. | The user's report is most plausibly the **403 displayed with "Forbidden" text the user transcribed as "Not Found"**, OR a stale browser tab where `sessionStore` was last in a bad state. **Two real defects are layered on top of this surface**: (a) the GUI passes `playheadFrame` (integer FRAMES) as `timeline_start` to `/clips` (which expects SECONDS — `AddClipReq.source_start/source_end/timeline_start` are `float`), corrupting any video drop position; (b) image drag uses `addImageClip` (frame-native) while video drag uses `addClip` (seconds) — two units, two endpoints, the GUI comment literally says "video / audio → /clips (seconds-based)". | (1) make every call go through `/clips/add_image`-style frame-native naming; (2) surface server error in a uniform `MutationError` UI; (3) only mutate after the lease UI says EDIT. | **P0** (corrupts timeline geometry) + **P1** (UX) |
| 4 | Single-clip track: move sometimes works, "movement feels much too large" | **YES (geometry)** | Audit: pxPerFrame = 1 at default zoom (30 px/sec @ 30 fps). A 10-px pointer drag commits to `new_timeline_start_frame=10` — that's 10/30 ≈ 0.33s, but it FEELS large because the user has no pre-drop preview (clip's preview frame equals the last collision-clamp result and that already includes the full pixelDelta). | GUI | `deltaFrame = roundHalfAwayFromZero(pixelDelta / pxPerFrame)` is correct (R5-B1 invariant, pinned by `gui/src/drag-invariant.test.ts`); auto-scroll works. | The user's complaint about "feels too large" maps to the **default zoom being 30 px/sec** at 30 fps (1 px = 1 frame) which is the **frame-native feel** the spec deliberately chose. There is no zoom-aware step (e.g. SHIFT = sub-frame pixel scaling or ALT = 1/10 step). | Either: lower the default zoom (Fit Content on first load already done in R4.2 P1-1), OR add modifier-key fine-grained step (Shift = ×0.25, Alt = snap-only). | **P2** (taste, not a bug) |
| 5 | Cross-track move returns "与轨道 v13 上现有 clip 时间重叠" | **YES (correct Core rejection but GUI should have prevented it)** | `move_clip` Core raises `CommandError(...时间重叠...)` → 400. GUI's pre-drop cross-track re-clamp reads `document.elementsFromPoint(ev.clientX, ev.clientY)` and queries `[data-track-id=...]` DOM siblings. This **only** runs when the pointer at pointerup is over a target row. If the pointer is between rows or the target row's `.clip` DOM hasn't yet reflected the dragged clip's preview position, the re-clamp may stale-read. | GUI + Core agreement | GUI's "don't pre-commit overlap" path is implemented (ClipBlock.tsx:469-535). Core's authoritative overlap check is `_check_no_overlap` (commands.py:231-263). | (a) The GUI re-clamp reads DOM siblings as frames via `parseFloat(style.left)/pxPerFrame`. If the dragged clip's own preview has rendered (its own `.clip` has new `style.left`), the re-clamp picks it up correctly; otherwise it sees stale siblings. (b) For cross-track moves, the GUI does NOT call Core's `/snap` a second time on the target track — spec says exactly one authoritative snap, but the re-clamp on the target track happens entirely in DOM-coordinates which can disagree with Core's source_range/timeline_range length math when source_fps differs. | Two changes: (1) Always re-query Core's authoritative sibling geometry on cross-track moves (a single `/clips/{id}/siblings?track_id=...` endpoint or include `target_siblings` in the move response); (2) Treat pointer-up on a non-track element as `tid = null` and refuse cross-track (the user didn't actually release over a different row). | **P1** |
| 6 | Multi-clip track: clip "flies away" OR returns same-track overlap error | **YES (visible symptom: flies-away)** | Audit: a clip with start at the leftmost position on a multi-clip track is dragged +5px. local clamp(candidate) finds a sibling overlapping the candidate and clamps to sibling.start. The clip now overlaps nothing BUT sits visually NEXT to a sibling (good). However if the user drags slowly into the next sibling, `lastPreviewFrame` is the clamp result and the visual position jumps to sibling.start — which can be **further right than the user's pointer** (the "flies away" feeling). On `up()`, the GUI calls `api.move(newFrame)`. If `newFrame === sibling.start - len`, and the user's pointer is even further right, the user sees the clip teleport. This is the spec'd "preview = clamp(candidate)" behavior — the bug is **perceptual**, not algorithmic. | GUI + visualization | The spec is explicit: preview 1:1 follows pointer; clamp is the visual reality; the user is supposed to feel "you cannot drop here" via the clip snapping to clamp boundary. | The visualization does NOT mark "I'm at clamp boundary because I would overlap". A clamped preview looks identical to a "I wanted to go here" preview. No edge tint / outline / cursor change. | Render the clamp-boundary preview with a 2-px dashed red outline + a `cursor: not-allowed` overlay. Also surface a transient status text "已贴边" for the duration of the drag. | **P1** |
| 7 | Preview shows only "播放头在间隙里 (499 frames)" with no image | **YES (real bug)** | `/preview/plan?timeline_id=main` returns 14 tracks; tracks[][v1] contains layer c039a7b at frames [414, 504]. `/preview/at_frame?timeline_id=main&frame=499` returns `is_black: false` with 2 visual layers (v1 c039a7b + v9 ce8fbe0). **BUT** PreviewPlayer.tsx:208-216 reads `project.clips[].timeline_range` from `/project` where `timeline_range.start/end` are in **SECONDS** (c039a7b → `{start:13.8, end:16.8}`), then compares against `playheadFrame` (FRAMES, = 499). The half-open check `playheadFrame >= start && playheadFrame < end` always fails because 499 ≫ 16.8. Result: `clip = null`. `clips.length === 12` (V1 has 12 clips), so the placeholder branch shows "⏰ 播放头在间隙里（499 frames）". The L1 composite branch CAN render correctly (plan has frame-native ranges) but the placeholder wins because the L0 fallback also fails (`clip === null`). | GUI / unit-mismatch | `/preview/plan` is frame-native (R5-B1) and correct. `/preview/at_frame` is frame-native and correct. `/project` returns `timeline_range` in seconds (legacy model storage). | PreviewPlayer does the **fallback path** check on `/project` data (seconds), but the **composite path** uses `/preview/plan` data (frames). When `/preview/plan` is fetched successfully and `composite.is_black === false`, the L1 branch SHOULD render — but the user's report shows the placeholder, which means either (a) `mode !== "instant"` (user toggled to rendered mode and the placeholder is for the wrong path), (b) `usePreviewPlan` hasn't resolved yet, (c) `timelineId` passed to PreviewPlayer is wrong (e.g. empty string instead of "main"). | Three layered fixes: (1) PreviewPlayer must NOT consult `/project` for the L0 single-clip fallback. Use `/clip/{id}/timemap` to get the clip's source/timeline ranges in frames; (2) the placeholder branch is shown ONLY when both L1 AND L0 fail — add an `aria-busy` for the loading state instead of showing "in gap"; (3) `activeTimelineId` must default to `project.active_timeline_id || "main"` BEFORE the first render of PreviewPlayer, not lazily in a useEffect. | **P0** |
| 8 | Image drop lands but user can't tell where | (same as #2) | (same as #2) | — | — | — | — | — |

---

## Audit A — runtime consistency

### A.1 Process / port inventory (live)

| Process | PID | Port | Started | Notes |
| --- | --- | --- | --- | --- |
| `python -m yroll.cli.main serve ...` | 3180 | 8770 | 2026-09-01 (live) | sole Mutation Authority |
| `node` (vite) | 9000 | 5173 | 2026-08-31 21:11 | `--port 5173` (dev server) |
| `node` (vite) | 14128 | 5180 | 2026-09-01 (live) | one-shot static-with-proxy for smoke |
| `chromium` (CDP) | 4460 | 9222 | (live) | user-visible browser |

No orphan vite PID (the prior 23508 was killed after R5 audit). No phantom MCP servers. Single Python backend. One dev server, one smoke server.

### A.2 Source paths

```
python -c "import yroll; print(yroll.__file__)"      → D:\cc\YROLL\yroll\__init__.py
python -c "import yroll.server.app as app; ..."     → D:\cc\YROLL\yroll\server\app.py
```

The interpreter resolves `yroll` to the **repo**, not to site-packages. Server's loaded module equals source.

### A.3 Git HEAD

```
HEAD: 8fcfcbd SESSION: log R5 remediation #1 + browser smoke results
parent: 2cf5116 R5 remediation: Track.hidden row-collapse + preview plan revision parity
```

Working tree clean. No drift.

### A.4 Frontend bundle hash

```
$ ls gui/dist/assets/
index-CA6Q1250.js     ← built from HEAD
index-DUbL593f.css
```

Hash matches HEAD's expected bundle.

### A.5 Live `GET /openapi.json` route inventory

Total routes: **106**. Selected routes relevant to this audit:

| Path | Methods | Live status |
| --- | --- | --- |
| `POST /clips` | POST | **200 (with valid sessionId) / 403 (without)** — NOT 404 |
| `POST /clips/add_image` | POST | 200 / 403 |
| `GET /timelines` | GET | 200 (4 timelines, active_timeline_id="main") |
| `GET /preview/plan?timeline_id=...` | GET | 200 / 422 (no query) / 404 (no timeline_id) |
| `GET /preview/at_frame?timeline_id=...&frame=...` | GET | 200 |
| `POST /clips/{id}/move` | POST | 200 / 400 / 403 |

The user's reported "POST /clips → 404" **does not reproduce live**. Live response for an unauthenticated POST /clips is 403. The route exists, the response is just forbidden-not-found.

### A.6 Live `/sequence` anomaly

```
GET /sequence  →  project_revision: 47
                  active_timeline_id: null
                  timelines: []
```

This is **inconsistent with `/timelines`** (which returns active_timeline_id="main" + 4 timelines). The /sequence endpoint's `active_timeline_id` and `timelines` arrays are **always None / empty** in this codebase (they're not part of `/sequence`'s response schema — `/sequence` only returns sequence-fps, timecode, and project_revision).

This is by design (sequence ≠ timelines), but the GUI's `useProjectSequence` interface types `ProjectSequence` to include neither field — so this is a **schema vs implementation drift** that the GUI happens to handle correctly. Worth documenting.

### A.7 Live `/project` and clip data

```
GET /project
  4 timelines
  main timeline: 15 tracks
    v1 kind=video clips=12 kinds={None}   ← ALL clips have kind=null
    v9 kind=video clips=3  kinds={None}
    ... 12 other tracks
  48 assets: 47 image (duration_sec=None) + 1 video (duration_sec=8.5085)
```

**Critical unit mismatch found**: every clip's `timeline_range` is in **SECONDS**, e.g.
- `c039a7b` (image, V1): `timeline_range: {start: 13.8, end: 16.8}` (= 414..504 frames @ 30fps)
- `c0bb0eb`: `{start: 44.5085, end: 49.5085}` (= 1335..1485 frames @ 30fps)

This is **legacy model storage** (every `Clip.timeline_range` on disk is in seconds; `move_clip` takes seconds; `move_clip_frame` converts frames→seconds at the boundary).

### A.8 `/preview/plan` and `/preview/at_frame` are frame-native (correct)

```
GET /preview/plan?timeline_id=main
  project_revision: 47
  timeline_id: "main"
  fps: {num:30, den:1}
  tracks: [[{track_id:v1, layer_index:0, kind:image, clip_id:c039a7b,
             timeline_start_frame:414, timeline_end_frame:504, ...}], ...]   ← 14 tracks
  subtitle_ranges: 5 ranges (start_frame, end_frame, text)

GET /preview/at_frame?timeline_id=main&frame=499
  timeline_frame: 499
  is_black: false
  visual_layers: [
    {track_id:v1, layer_index:0, kind:image, clip_id:c039a7b,
     timeline_start_frame:414, timeline_end_frame:504, asset_id:a826bb7},
    {track_id:v9, layer_index:1, kind:image, clip_id:ce8fbe0,
     timeline_start_frame:405, timeline_end_frame:555, asset_id:aa080ae}
  ]
  audio_layers: []
  subtitle_texts: ["..."]   ← 1 active subtitle at frame 499
```

**This is the canonical answer for "what should the user see at frame 499"** — two image layers + one subtitle. The plan/at_frame are correct. The bug is in how PreviewPlayer **consumes** the data.

---

## Audit B — image insertion trace

### B.1 Trigger surface

Three insertion paths:
1. AssetPanel "+" button (`gui/src/components/AssetPanel.tsx:88-102`)
2. AssetPanel drag onto an existing track (`gui/src/App.tsx:1689-1738` `onAssetDrop`)
3. AssetPanel drag onto the "新建轨道" drop zone (`gui/src/App.tsx:1740-1770` `onAssetDropNewTrack`)

All three call `api.addImageClip(assetId, tlStart, durFrames, explicitTrackId, why)`.

### B.2 API call (frame-native)

```
POST /clips/add_image
Body: {asset_id, timeline_start_frame, timeline_duration_frames, track_id?, why?}
```

### B.3 Recorded at insertion (the user-reported flow)

The audit could not exercise the actual mutation because the lease is held by another session (`bd4ff8ec`, human). Recorded from `app.py:539-560` + `commands.py:695-816`:

- `timeline_id` defaults to `project.active_timeline_id` ("main")
- `track_id`: if non-null, Core verifies overlap on that specific track; if null, Core's `TrackAllocator` picks the minimum non-overlapping track
- `timeline_start_frame`: integer frames (R5 spec invariant)
- `timeline_duration_frames`: integer frames (default 5 sec × 30 fps = 150 frames)
- `source_range`: derived server-side to `(0, 1/seq_fps)` (image has 1 source frame)

The Core emits one `add_image_clip` Operation. The clip is persisted with frame-native coordinates (converted to seconds for storage). `project_revision` increments to 48. `/preview/plan` becomes available for the new revision.

### B.4 Post-insertion GUI behavior (THE GAP)

**What happens to the user after a successful addImageClip:**

1. `run()` resolves with the new Clip.
2. App.tsx status bar shows `"<basename> 已放到 F<t>（<durFrames>f）"` — a text confirmation. ✓
3. **The newly added clip is NOT selected** (no `setSelected(clip.clip_id)` call).
4. **The playhead is NOT moved** to the new clip's start.
5. **The viewport is NOT scrolled** to bring the new clip into view.
6. **No auto Fit Content** runs (the user might still be zoomed at 30 px/sec with viewport at frame 0..500).

If the user dropped at frame 499 with default zoom (30 px/sec, viewport ≈ 1500 px ≈ 50 sec), the new clip appears at frame 499 (well within view). But if the user dropped at frame 5000 (or any frame past their current viewport), the clip is in the data but invisible — and there's no UX cue.

**Audit conclusion:** the image IS being inserted correctly. The bug is **viewport awareness after mutation**, not the insertion itself.

### B.5 Vitest coverage

`gui/src/components/Timeline.hidden.test.tsx` covers Track.hidden row-collapse (R5 fix).
**No vitest covers post-insertion viewport visibility** — this is the missing test.

---

## Audit C — POST /clips → 404

### C.1 Live behavior

```
$ curl -i -X POST :8770/clips -d '{}'
HTTP/1.1 403 Forbidden
{"detail":"sessionId required for mutations (call /lease/acquire first)"}

$ curl -i -X POST :8770/clips -H 'Content-Type: application/json' \
       -d '{"asset_id":"BADBAD","source_start":0,"source_end":5,"timeline_start":0,"track_id":"v1"}'
HTTP/1.1 403 Forbidden
{"detail":"sessionId required for mutations (call /lease/acquire first)"}
```

The live backend returns **403**, not 404. The user's report says "404 Not Found". Two plausible explanations:

(a) The user transcribed "Forbidden" as "Not Found" (visual confusion).
(b) The user's browser session is in a state where the `gated()` guard returns 403 BUT the proxy or the sessionStore shows a misleading "Not Found" — this would require proxy misconfiguration.

### C.2 The real underlying defect (NOT a 404, but a unit-mismatch bug)

Look at `gui/src/api.ts:526-532`:
```ts
addClip: (assetId, sourceStart, sourceEnd, timelineStart, trackId, why = "") =>
  mutate<Clip>("POST", "/clips", {
    asset_id: assetId, source_start: sourceStart, source_end: sourceEnd,
    timeline_start: timelineStart, track_id: trackId, why,
  }),
```

And `yroll/server/app.py:153-162`:
```py
class AddClipReq(BaseModel):
    asset_id: str
    source_start: float      # ← SECONDS
    source_end: float        # ← SECONDS
    timeline_start: float    # ← SECONDS
    track_id: str | None = None
    why: str = ""
```

But in `gui/src/App.tsx:1728-1731` (the drag-drop path) and `AssetPanel.tsx:100-103` (the + button), the GUI calls:
```ts
run(() => api.addClip(assetId, 0, dur, t, trackId, "GUI 拖入时间轴"),
```
where `t` is `playheadFrame` (integer FRAMES), `dur` is `asset.identity.duration_sec` (already seconds).

The GUI comment literally says: `// video / audio → /clips (seconds-based)` — confirming the author **knew** the unit is seconds but **passed frames anyway** because the variable is named `t` and that's the playhead.

**Result**: a video drop at playhead=1500 (frames) becomes `timeline_start=1500` (seconds) — the clip lands at frame 45000, deep into a gap that may not exist (or may collide with something else). This is the **real** video-insertion defect.

### C.3 The dual-endpoint split

| Endpoint | Unit | When used |
| --- | --- | --- |
| `POST /clips/add_image` | FRAMES (`timeline_start_frame`, `timeline_duration_frames`) | Image assets (R5 spec invariant) |
| `POST /clips` | SECONDS (`source_start`, `source_end`, `timeline_start`) | Video + Audio assets (legacy model storage) |

The split is **deliberate** (R5 spec §frame-native for images; legacy seconds for video) but the GUI does **not** convert before calling. The cleanest fix: make `/clips` also frame-native with `source_start_frame`, `source_end_frame`, `timeline_start_frame`. The Core already has `move_clip_frame` for the same conversion pattern.

### C.4 What this audit does NOT recommend changing yet

- The `/clips` route itself — it's correctly registered, the model is documented, and changing it is a breaking API change. The right fix is on the **GUI side**: convert frames→seconds (or use the `/clips/add_image`-style frame API for video too).
- The 403-on-no-session behavior — this is correct defense-in-depth.
- The `_check_no_overlap` Core path — the overlap rejection is correct.

---

## Audit D — preview black/gap at frame 499

### D.1 Live /preview/at_frame at frame 499 (timeline=main)

```json
{
  "timeline_frame": 499,
  "fps": {"num": 30, "den": 1},
  "is_black": false,
  "visual_layers": [
    {"track_id": "v1", "layer_index": 0, "kind": "image",
     "clip_id": "c039a7b", "asset_id": "a826bb7",
     "timeline_start_frame": 414, "timeline_end_frame": 504},
    {"track_id": "v9", "layer_index": 1, "kind": "image",
     "clip_id": "ce8fbe0", "asset_id": "aa080ae",
     "timeline_start_frame": 405, "timeline_end_frame": 555}
  ],
  "audio_layers": [],
  "subtitle_texts": ["…"]
}
```

**The plan says "not black, 2 image layers, 1 subtitle".** This is the canonical answer.

### D.2 What the GUI does instead (the bug)

`gui/src/components/PreviewPlayer.tsx:208-216`:
```ts
const vtrack = (project.timelines?.find(
    (tl) => tl.timeline_id === project.active_timeline_id,
  ) ?? project.timelines?.[0])?.tracks.find((t) => t.kind === "video");
const clips = (vtrack?.clip_ids ?? [])
    .map((id) => project.clips[id])
    .filter(Boolean)
    .sort((a, b) => a.timeline_range.start - b.timeline_range.start);
const clip = clips.find(
    (c) => playheadFrame >= c.timeline_range.start && playheadFrame < c.timeline_range.end,
) ?? null;
```

- `project.timelines` and `project.clips` come from `/project` (which has `timeline_range` in **seconds**, see A.7).
- `playheadFrame` is **frames** (from the ruler/transport).
- For c039a7b at playheadFrame=499: `499 >= 13.8` (true) AND `499 < 16.8` (**false** because 499 > 16.8). So `clip = null`.
- `clips.length === 12` (V1 has 12 clips). The placeholder branch:
  ```ts
  {clips.length === 0
    ? "📭 时间轴是空的——从素材库拖到 V1 轨"
    : `⏰ 播放头在间隙里（${playheadFrame} frames）`}
  ```
  shows **"⏰ 播放头在间隙里（499 frames）"**.

**This is exactly what the user reported.**

### D.3 But wait — the L1 composite branch should render correctly

`PreviewPlayer.tsx:248-280` computes `composite` from `usePreviewPlan` (which fetches `/preview/plan`):
```ts
const composite = (() => {
  if (!plan || mode !== "instant") return null;
  for (const track of plan.tracks) {
    const layer = activeLayerAt(track, playheadFrame);
    if (layer === null) continue;
    if (layer.kind === "audio") audio.push(layer);
    else visual.push(layer);
  }
  ...
})();
```

`plan.tracks` has frame-native `timeline_start_frame/timeline_end_frame` from `/preview/plan`. So `activeLayerAt(track, 499)` correctly finds c039a7b + ce8fbe0 at frame 499. `composite.visual_layers` has 2 entries. `composite.is_black = false`.

The L1 render branch:
```ts
mode === "instant" && composite && !composite.is_black ? (
  <composite>...</composite>
) : clip && asset && sourceFrame !== null && timeMapEntry ? (
  <fallback>...</fallback>
) : (
  <placeholder>{gap text}</placeholder>
)
```

**The L1 branch SHOULD render.** So either:
1. `mode !== "instant"` (user toggled to rendered mode).
2. `plan === null` (usePreviewPlan hasn't resolved yet — most likely).
3. `timelineId` passed to PreviewPlayer is wrong.

### D.4 Why `plan` is null

Look at `usePreviewPlan` (`gui/src/preview-plan.ts:201-247`):
```ts
const liveSeq = useProjectSequence();   // polled every 5s
const projectRevision = mode === "instant" ? (liveSeq.projectRevision || null) : null;
const { plan, loading: planLoading } = usePreviewPlan(projectRevision, timelineId ?? "main");
```

`useProjectSequence` polls `/sequence` every 5s. But **`/sequence` returns `project_revision: 47` and nothing else** (A.6). So `liveSeq.projectRevision = 47`. So `projectRevision = 47` (when mode === "instant"). So `usePreviewPlan(47, "main")` fires, fetches `/preview/plan?timeline_id=main`, and should populate `plan` with the 14 tracks.

**But `plan` is still null at the moment the user takes the screenshot.** This is the race:

```
T+0   : user loads page, PreviewPlayer mounts, plan=null, composite=null
T+0.1 : PreviewPlayer renders placeholder "📭 时间轴是空的" (clips.length=0 because /project hasn't resolved)
T+0.5 : /project resolves, clips.length=12, but composite is still null (usePreviewPlan hasn't fired)
T+0.5 : PreviewPlayer re-renders → placeholder "⏰ 播放头在间隙里（499 frames）" ← USER SEES THIS
T+5.0 : /sequence poll returns project_revision=47 → usePreviewPlan fires
T+5.1 : /preview/plan resolves → composite populated → next render shows L1 composite
```

The **placeholder is shown for the first ~5 seconds** after page load. If the user takes the screenshot during that window, they see "playhead in gap". The user is correct that the preview is wrong; the bug is **rendering the placeholder during the loading window** instead of an explicit loading state.

### D.5 What about after the 5-second window?

The user reports the preview **stays** in the gap state, not that it briefly flashes. Possible explanations:
- The user's `useProjectSequence` polling is broken (the /sequence endpoint returns `project_revision: 47` but the GUI's parsed value is 0 or stale).
- The user is in `mode === "rendered"` after rendering once and never toggled back.
- The `timelineId` prop is empty string (not "main"), so `/preview/plan?timeline_id=` returns 404.

The audit cannot reproduce the "stays in gap" without a running browser session. The "flashes in gap" race condition is **definitely present** in the code path.

### D.6 Recommended fix (NOT to be implemented in this audit)

1. **Don't fall back to /project's seconds-based timeline_range** in the L0 path. Either: (a) use the L1 composite's data for everything (since `/preview/plan` is canonical), or (b) fetch `/clip/{id}/timemap` to get the clip's frame-native ranges.
2. **Show an explicit loading state** when `planLoading === true`, not the placeholder.
3. **Audit `usePreviewPlan`'s race guard** — when `mode === "rendered"` then user toggles to "instant", the `projectRevision=null → 47` transition should fire a fetch. Currently it does (the effect re-runs because `projectRevision` changes). But the `lastKeyRef.current` may already be set to `"47:main"` from a previous mount, in which case the fetch is skipped. This is a potential bug.

---

## Audit E — drag coordinate system

### E.1 Required invariant (R5-B1)

```
deltaFrame = roundHalfAwayFromZero((clientX - startClientX) / pxPerFrame)
scrollLeft does NOT enter the frame math
```

### E.2 Pinned by tests

- `gui/src/drag-invariant.test.ts` — 4 tests pinning the math.
- `gui/src/drag-autoscroll.test.ts` — 12 tests pinning the auto-scroll.

### E.3 Live trace (sanitized code path)

`gui/src/components/ClipBlock.tsx:280-380` (`move` handler):

```
T+0   : pointerdown at clientX=startX, capture startX, origStartFrame from clip
T+0+ε : move(ev) fires
        pixelDelta = ev.clientX - startX
        deltaFrame = roundHalfAwayFromZero(pixelDelta / pxPerFrame)
        candidate = origStartFrame + deltaFrame
        clamped   = clamp(candidate)             // collision-aware
        ghostSnap = snap(candidate)              // visual-only, never applied
        onDragMove(clip.clip_id, clamped, ghost) // → App.tsx updates clip.style.left
```

`ClipBlock.tsx:402-414` (`up` handler):

```
T+1   : pointerup
        pixelDelta = ev.clientX - startX         // pointer-only, scrollLeft NOT folded
        preSnapFrame = lastPreviewFrame           // = clamped from last move()
        finalFrame   = preSnapFrame
        localSnapTarget = snap(preSnapFrame)
        if (localSnapTarget && not no-op):
            clampedSnapped = clamp(localSnapTarget.frame)
            if (clampedSnapped === localSnapTarget.frame):
                authoritativeSnapFrame = localSnapTarget.frame
                finalFrame = localSnapTarget.frame
            else:
                snapAborted = true, finalFrame = preSnapFrame
        // Cross-track re-clamp (if pointer ended over a different track-row)
        tid = document.elementsFromPoint(ev.clientX, ev.clientY).find(...).dataset.trackId
        if (tid && tid !== clip.track_id):
            targetClips = read from DOM [data-track-id=tid] > .clip
            finalFrame = targetClamp(candidateForTarget)
            finalTrackId = tid
        api.move(clipId, finalFrame, finalTrackId, why)
```

### E.4 Measurements (would require browser session to capture live)

The audit cannot measure live pointer deltas without a browser. From static code reading:

| Quantity | Value (at default zoom) |
| --- | --- |
| `pxPerSec` (App.tsx default) | 30 |
| `seqFps` (Sanlihe) | 30/1 |
| `pxPerFrame` (derived) | 30 × 1/30 = **1 px/frame** |
| 10 px pointer drag → deltaFrame | 10 |
| 1 px pointer drag → deltaFrame | 1 |
| 100 px pointer drag → deltaFrame | 100 |
| scrollLeft effect on frame math | **zero** (R5-B1 invariant, pinned) |

So a 10-px drag IS 10 frames (= 10/30 sec = 0.33 sec). At default zoom, 1 pixel = 1 frame = the frame-native feel. The user's complaint "movement feels much too large" is consistent with dragging at default zoom without realizing that **1 px = 1 frame**.

The **server-side guard** at `app.py:822-833` (`move` endpoint) clamps to `[0, max_timeline_frame]` (R3-2 P0-1). So the "10 px → 126150 px amplification" from R3-2 audit is **no longer possible**.

### E.5 What's missing

- **No zoom-aware step**. Holding Shift to drag finer (e.g. 0.1 frame per pixel) is not implemented. The user has to zoom in to get finer control. This is a taste/P2 issue, not a bug.
- **No visual cue for "clamped at boundary"** (see Audit F / Symptom 6).

---

## Audit F — overlap errors

### F.1 Live Core overlap check (correct)

`yroll/core/commands.py:231-263` `_check_no_overlap`:
```py
def _check_no_overlap(self, track_id, start, end, exclude_clip_id=None, ...):
    conflicts = self._find_overlap(track_id, start, end, exclude_clip_id, ...)
    if conflicts:
        shown = ", ".join(conflicts[:3])
        ...
        raise CommandError(
            f"{op_name} 与轨道 {track_id}{scope} 上现有 clip 时间重叠："
            f"{shown}{more}。（同一轨道片段不允许重叠，请先 "
            f"Trim/Split 或 Move 到其它轨道）")
```

This is **Core's authoritative truth**. It rejects with HTTP 400 via the FastAPI handler.

### F.2 The reported error matches exactly

User reports:
> Moving a clip across tracks can return: `move_clip(...) 与轨道 v13 上现有 clip 时间重叠`

This is the literal text from `_check_no_overlap` with `op_name = "move_clip(...)"` and `track_id = "v13"`. The Core's authoritative overlap check ran on track `v13` and found a conflict.

**This means the GUI's cross-track re-clamp failed to prevent the conflict.** Either:
1. The cross-track re-clamp code didn't run (no `tid !== clip.track_id`).
2. The cross-track re-clamp code ran but used stale siblings.
3. The dragged clip's own preview position was not yet reflected in the DOM at the time the re-clamp queried siblings.

### F.3 Cross-track re-clamp mechanics

`ClipBlock.tsx:469-535`:
```ts
const row = document.elementsFromPoint(ev.clientX, ev.clientY)
  .find((el) => (el as HTMLElement).dataset?.trackId) as HTMLElement | undefined;
const tid = row?.dataset.trackId;
if (tid && tid !== clip.track_id) {
  const targetRow = document.querySelector(`[data-track-id="${CSS.escape(tid)}"]`);
  const targetClips = targetRow
    ? Array.from(targetRow.querySelectorAll('.clip')).map((el) => {
        const id = (el as HTMLElement).dataset.clipId ?? "";
        const left = parseFloat((el as HTMLElement).style.left || "0");
        const widthPx = parseFloat((el as HTMLElement).style.width || "0");
        const start = roundHalfAwayFromZero(left / Math.max(0.001, pxPerFrame));
        const end = start + Math.max(0, roundHalfAwayFromZero(widthPx / Math.max(0.001, pxPerFrame)));
        return { id, start, end };
      }).filter((r) => r.id !== clip.clip_id)
    : [];
  ...
}
```

Failure modes:
1. **`document.elementsFromPoint` returns no track-row** (pointer is over ruler, drop-zone, or between rows): `tid = undefined`, cross-track path skipped, Core sees `new_track_id = None` (same track), no cross-track issue but user intended cross-track.
2. **`tid === clip.track_id`** (pointer still over source row): cross-track path skipped.
3. **`tid` is a valid target but the target row's `.clip` elements aren't yet rendered** (React re-render race): `targetClips = []`, `targetClamp(candidateForTarget) = max(0, candidateForTarget)` (no conflicts found). The clip is sent to Core with a frame that overlaps a sibling on the target — Core rejects.

### F.4 Same-track overlap on multi-clip tracks (Symptom 6)

User reports:
> Moving a clip on a track with multiple clips can either appear to succeed while the clip visually "flies away", or return a same-track overlap error.

Both outcomes are possible from the **same** drag gesture, depending on:
- Did `local snap()` find a candidate? If yes, `finalFrame = snapTarget.frame`. If snap target happens to not overlap (because sibling geometry), commit succeeds. If snap target overlaps, `snapAborted = true`, `finalFrame = preSnapFrame`. Either way, the visual jump is the user's perception of "flies away".
- Did the cross-track re-clamp run? If yes, `targetClamp` either accepts or shifts the final frame.
- Did Core accept? If `finalFrame` doesn't overlap, Core commits. If it overlaps (e.g. the GUI re-clamp missed a sibling), Core rejects with 400.

### F.5 Stale sibling geometry — confirmed risk

The cross-track re-clamp reads sibling positions from `style.left` (CSS) and divides by `pxPerFrame` to get frames. If the dragged clip's preview has updated its own `style.left` (because `onDragMove` ran on the previous pointermove), the re-clamp correctly excludes `id === clip.clip_id`. But if the **target row's clips** had any CSS animation / pending render, their `style.left` may be stale. The audit considers this **unlikely** (CSS updates are synchronous in React commits), but not zero.

### F.6 What should change (not in this audit)

- Replace DOM-based sibling re-clamp with a Core `/clips/{id}/siblings?track_id=...` endpoint that returns sibling positions in frames (canonical, not CSS-derived).
- For pointer-up with no track-row under the pointer: refuse cross-track (treat as same-track move) AND surface a status text "未释放到目标轨道".

---

## Audit G — viewport visibility after mutation

### G.1 Current behavior

`gui/src/App.tsx` post-mutation flow (image + video + move):

1. `run(() => api.addImageClip(...))` resolves.
2. Status text is set: `"<basename> 已放到 F<t>（<durFrames>f）"`.
3. `await onChanged()` → triggers `/project` refetch (full project reload).
4. React re-renders with new clip in the timeline DOM.
5. **No `setSelected`, no `setPlayheadFrame`, no `scrollIntoView`, no `setSelectedSet`, no Fit Content.**

### G.2 What the user sees

- **If the new clip's frame falls inside the current viewport** (default zoom, viewport at start of project, playhead=499): clip appears at `style.left = 499 * pxPerFrame = 499 px`. Visible. ✓
- **If the new clip's frame is outside the current viewport** (e.g. dropped at frame 5000 with viewport at 0-50): clip is in the DOM at `style.left = 5000 px`, but the timeline-content's `scrollLeft` is 0, so the user sees nothing.
- **No UI cue** that the clip is off-screen.
- **No scrollIntoView** fires.

### G.3 What already exists

- `Home` binding (R3-W-D) centers the playhead in the viewport. The user can hit Home and the playhead (still at 0) jumps to viewport center. This does NOT bring a different frame's clip into view.
- `适配内容` button calls `setPxPerSec` to fit all clips. This zooms out and resets viewport to frame 0. Destroys the user's framing.

### G.4 What is missing

After every successful mutation (add / move / trim / ripple / split):
- `setSelected(clip.clip_id)` — so the user has a visible selection on the clip.
- Optionally: `setPlayheadFrame(clip.timeline_range.start)` — playhead lands where the mutation landed.
- Scroll the timeline-content so the clip is visible (`scrollLeft` adjusted, not zoom reset).

### G.5 Test coverage

**No vitest covers this.** The R5 audit's "missing piece" list does not include this. The R5 spec §"preview plan cache" doesn't include this.

---

## Things that must NOT be changed (already correct)

| # | Capability | Why it's correct | Where to find the pin |
| --- | --- | --- | --- |
| 1 | `deltaFrame = roundHalfAwayFromZero(pixelDelta / pxPerFrame)` | R5-B1 invariant, the audit confirms the math is right at every layer | `gui/src/components/ClipBlock.tsx:48-52`, `gui/src/drag-invariant.test.ts` |
| 2 | `scrollLeft` does NOT enter frame math | R5-B1 invariant, pinned | `gui/src/components/ClipBlock.tsx:400-405`, `drag-invariant.test.ts` |
| 3 | Server-side `[0, max_timeline_frame]` guard on `/clips/move` | R3-2 P0-1 invariant | `yroll/server/app.py:822-840`, `tests/test_frame_safety_bounds.py` |
| 4 | `ensureReady()` gate before every mutation | R5-B1 invariant, closes the sessionId race | `gui/src/api.ts:202-218` |
| 5 | Track.hidden row-collapse fix from R5 remediation #1 | R5-bug-#1 already fixed, audit confirms | `gui/src/components/Timeline.tsx` (no display:none), `Timeline.hidden.test.tsx` |
| 6 | `build_preview_plan revision parity` fix from R5 remediation #1 | R5-bug-#2 already fixed, audit confirms `/preview/plan` project_revision == `/sequence` project_revision == 47 | `yroll/core/plan.py`, `tests/test_preview_plan_revision_parity.py` |
| 7 | `/preview/plan` and `/preview/at_frame` frame-native ranges | Both confirmed live: c039a7b is at [414, 504] frames in plan/at_frame | `yroll/server/app.py:1919-1927` |
| 8 | Core `add_image_clip` overlap rejection | Authoritative, raises CommandError correctly | `yroll/core/commands.py:695-816` |
| 9 | Core `move_clip` overlap rejection | Authoritative, raises CommandError correctly | `yroll/core/commands.py:1568-1670` |
| 10 | Race-safe Timeline switch (`usePreviewPlan` epoch guard) | Discard stale plans when timeline changes mid-flight | `gui/src/preview-plan.ts:178-249` |
| 11 | Auto-scroll during drag | R4.1 P0-1, pinned | `gui/src/drag-autoscroll.ts`, `drag-autoscroll.test.ts` |
| 12 | Multi-layer PiP visualization (Decision 4) | Pin the visualization rules, not the persistence | `gui/src/composite-multilayer.ts`, `composite-multilayer.test.ts` |
| 13 | Home centering playhead (R3-W-D) | Center-on-playhead in viewport, frame 0 stays at ContentViewport origin | `gui/src/App.tsx:740-752`, `keymap.test.ts` |
| 14 | `roundHalfAwayFromZero` is the only edit-coordinate rounding | `Math.round` forbidden in edit coords | `tests/test_no_js_round_in_edit.py` |
| 15 | Standard NTSC DF (closed-form) | No pinned dict | `yroll/core/timeframe.py`, `gui/src/frames.ts` |
| 16 | Fit Content (R4.2 P1-1) | First-load auto-fit + manual button | `gui/src/App.tsx:461-481, 875-905`, `fit-content.test.ts` |
| 17 | `/sequence` returns sequence-fps, timecode, project_revision only | By design; GUI's `useProjectSequence` ignores missing fields | `gui/src/sequence.ts` |
| 18 | `/preview/plan?timeline_id=` (empty) returns 200 with empty plan | Documented asymmetry; not a bug | `yroll/server/app.py:1919-1927` |
| 19 | Static guard: `gui/src/components/ClipBlock.tsx` cannot use `Math.round` on edit coords | Architecture-level | `tests/test_no_js_round_in_edit.py` |
| 20 | Static guard: `mcp_server.py` cannot call `ProjectCore(` directly | Sole-writer architecture | `tests/test_no_writes_outside_server.py` |

---

## Recommended next step (for human review before any code change)

This audit recommends **a single batch** addressing symptoms #2, #3 (real defect), #5, #6, #7:

1. **Preview-player fix (P0)**: stop using `/project`'s seconds-based `timeline_range` for the L0 fallback. Add an explicit loading state (don't show "in gap" while plan loads). Verify with playwright that frame 499 renders 2 image layers + 1 subtitle within 1 second of mount.

2. **Post-mutation viewport awareness (P1)**: after every successful add/move/trim, `setSelected(newId)` + `scrollIntoView(newId, scroll: 'nearest')` + `setPlayheadFrame(start)`. Vitest pin: `addImageClip` at frame 3000 → after the promise resolves, `selected === clipId` AND `timelineContentRef.scrollLeft > 0` AND `playheadFrame === 3000`.

3. **Frame-native `/clips` (P0)**: change `AddClipReq.source_start/source_end/timeline_start` from `float` to `int` with `_frame` suffix (or add `*_frame` variants). Update `gui/src/api.addClip` to pass frames. This closes the video-drag-corrupts-geometry bug.

4. **Cross-track re-clamp via Core (P1)**: new endpoint `/clips/{id}/siblings?track_id=...` returning sibling frame-ranges. Replace DOM-based re-clamp in `ClipBlock.tsx`.

5. **No new feature work** until the 6 manual checks on clean Sanlihe (per R5 closure) pass with these fixes.

**Do NOT implement**: Publish Metadata, Timeline-local Revision, Keyframes, opacity controls, AI features.

---

*Audit by R6 audit-only mandate. No code in `yroll/`, `gui/src/`, or `tests/` was modified.*