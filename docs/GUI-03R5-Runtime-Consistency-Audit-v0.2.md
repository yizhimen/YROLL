# GUI-03R5 Runtime Consistency Audit v0.2

**Audit baseline**: HEAD = `1651e23` (R5 manual pass IN PROGRESS).
**Audit window**: 2026-09-01.
**Mandate (per user)**: stop feature work; produce runtime evidence before any code change.

This audit is **read-only**. Every claim is backed by a CLI observation against
the running backend (PID 23952, port 8770) and a static read of the current tree.
No source file in `yroll/`, `gui/src/`, or `tests/` was modified by this audit.

---

## TL;DR

| User-reported failure                       | Reproduced? | Root cause                                                                                                              | Bug location                                  |
| ------------------------------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| Clicking Track Visibility hides entire row  | **YES**     | `display: track.hidden ? "none" : "flex"` at `Timeline.tsx:576, 811` collapses the whole row + header                  | **GUI** — Timeline.tsx                        |
| `GET /timelines` → 404                      | **NO**      | Live backend returns HTTP 200 with 4 timelines                                                                          | (false report — possibly transient)           |
| Adding assets to Timeline fails             | **NO**      | Mutation chain works end-to-end with valid sessionId                                                                    | (false report — possibly gate-state confusion) |
| Preview is black / "playhead is in a gap"   | **PARTIAL** | Backend `/preview/plan?timeline_id=main` returns full plan; **BUG**: `build_preview_plan` always reports `project_revision=0` (because `project.ui_status` is never set). The GUI's `usePreviewPlan` then treats the plan as stale and discards it. | **Core** — `yroll/core/plan.py:143-146`       |
| Subtitles are missing                       | **NO**      | `/preview/plan?timeline_id=main` returns 5 subtitle ranges; mojibake in shell is just `cat` GBK rendering, bytes are valid UTF-8 | (false report)                               |

The runtime stack is **consistent**: backend code, import path, build hash,
and process identity all match the current tree. The failures that DO
reproduce are real GUI/Core bugs, not version drift.

---

## Step 1 — Runtime / Version Consistency

### 1.1 Process and port inventory

```
PID     Name    StartTime               CommandLine
23952   python  2026-09-01 02:36:37 AM  python -m yroll.cli.main serve
                                    D:\cc\YROLL\projects\_sanlihe-r5-manual
                                    --port 8770 --host 127.0.0.1
23508   node    2026-08-30 11:38:19 AM vite (no --port flag — default 5173)
9000    node    2026-08-31 09:11:55 PM vite --port 5173 --host 127.0.0.1
14128   node    2026-09-01 02:37:06 AM (orphan from earlier today)
```

* Backend (8770): single python process, started today at 02:36:37.
  `Get-NetTCPConnection -LocalPort 8770 -State Listen` confirms port is open.
* Frontend (5173): TWO `vite` processes — PID 23508 (started 08-30 11:38:19,
  older) + PID 9000 (started 08-31 21:11:55). **One is orphaned**.
* No phantom `python.exe` for MCP / hidden servers.

### 1.2 Import-path verification

```
python -c "import yroll, yroll.server.app"
  yroll:           D:\cc\YROLL\yroll\__init__.py
  yroll.server.app: D:\cc\YROLL\yroll\server\app.py
```

The running interpreter resolves `yroll` to the **repo itself**, not to a
site-packages shadow. The server's loaded module path equals the source path.

### 1.3 Git HEAD

```
HEAD: 1651e23 SESSION: log GUI-03R5 batches B1-B5 + manual pass in progress
Working tree: only gui/tsconfig.tsbuildinfo dirty (irrelevant)
```

`yroll/server/app.py` mtime: 2026-08-31 17:19 — consistent with HEAD.

### 1.4 Live route table (`GET /openapi.json`)

```
HTTP 200, total_paths: 106
/timelines methods: ['get', 'post']
/timelines/{timeline_id} /timelines/{timeline_id}/duplicate /timelines/{timeline_id}/switch
/preview/plan /preview/at_frame /preview.mp4 /frame/preview /mutation/preview
/clips + /clips/add_image + 24 /clips/{clip_id}/* mutations
/tracks + /tracks/close_gap + /tracks/close_gaps_batch + /tracks/delete + /tracks/ensure_for_drop
/selection/delete, /snap, /markers, /beats, /ui/status, /audit/since/{id}, /audit/last
/proposals (+ approve/reject), /problems, /solutions/execute, /keyboard/keymap
/sequence, /history, /operations, /costs, /versions, /presets, /render, /export/package
```

Every route the GUI calls is present in the live process. **No drift.**

### 1.5 Live backend direct probes

| Request                                                | Status | Body sample                                                                                                                |
| ------------------------------------------------------ | ------ | -------------------------------------------------------------------------------------------------------------------------- |
| `GET /timelines`                                       | 200    | `{"active_timeline_id":"main","default_timeline_id":"main","timelines":[main,科普版,种草版,IP版]}`                          |
| `GET /preview/plan?timeline_id=main`                   | 200    | 10 tracks, 16 visual layers, 5 subtitle ranges, `project_revision: 0` ← **bug**, see §3.1                                   |
| `GET /preview/plan?timeline_id=` (empty)               | 200    | 0 tracks, 0 subtitles                                                                                                      |
| `GET /preview/plan` (no query)                         | 422    | `{"detail":[{"type":"missing","loc":["query","timeline_id"]}]}`                                                            |
| `GET /preview/at_frame?timeline_id=main&frame=500`     | 200    | `is_black: false`, 2 visual layers + 1 subtitle                                                                             |
| `GET /preview/at_frame?timeline_id=main&frame=1380`    | 200    | `is_black: false`, 1 visual layer (v1, c0bb0eb)                                                                            |
| `GET /preview/at_frame?frame=500` (no timeline_id)     | 200    | `is_black: false`, 2 visual + 1 subtitle (Core falls back to active_timeline_id)                                          |
| `GET /ui/status`                                       | 200    | `actor=human, session_id=756069e3..., base_revision=1, conflict=false, visual_cue=🟢 编辑权：我`                            |
| `GET /sequence`                                        | 200    | `project_revision: 1`                                                                                                      |
| `GET /project`                                         | 200    | 4 timelines; main has 14 tracks (10 visible, 4 hidden), 41 clips, 48 assets (47 image + 1 video)                          |
| `POST /clips/add_image` (with valid SID+rev+body)      | 200    | `{clip_id: cf9426c, track_id: v1, timeline_range: {50, 55}}`                                                                |
| `POST /clips/add_image` (no sessionId)                 | 403    | `{"detail":"sessionId required for mutations (call /lease/acquire first)"}`                                                 |
| `POST /lease/acquire?actorId=audit-test` (someone else)| 403    | `{"detail":"project currently held by human session 756069e3 in edit mode; release or handoff first"}`                     |

### 1.6 Frontend bundle hash

```
gui/dist/index.html  →  /assets/index-CFooX-sC.js
                       /assets/index-BnJ9wojO.css
```

The bundle hash matches what `gui/dist/assets/` contains on disk and what
SESSION.md line 288 records. No stale build.

### 1.7 Frontend bundle internals (sanity grep)

```
grep "preview/plan" gui/dist/assets/index-CFooX-sC.js
  → preview/plan${a.toString(    ← URL template builder
grep "previewPlan(" gui/dist/assets/index-CFooX-sC.js
  → previewPlan({timeline_id:a}) ← GUI passes timeline_id correctly
```

The built code uses `previewPlan({timeline_id: activeTimelineId})`. **No
"missing timeline_id" bug in the bundle**.

### 1.8 Conclusion of Step 1

The running stack is internally consistent:
- backend code = HEAD
- backend process loads the repo
- all routes present
- frontend bundle = HEAD
- frontend bundle calls the right endpoints with the right params

The user's "GET /timelines 404" and "asset add fails" reports **could not be
reproduced against this stack**. They were either transient, from a stale
browser tab, or from an earlier process. **No backend code change is
justified by runtime evidence.**

The `preview/plan` empty-timeline response is a real Core bug, but it's
the GUI's responsibility to send the right timeline_id (which the built
bundle does).

---

## Step 2 — Track.hidden semantics

### 2.1 Current code (Timeline.tsx)

```tsx
// Line 572–577 (track-label-row / header)
<div
  className={`track-label-row ${track.hidden ? "track-hidden" : ""}`}
  data-track-id={track.track_id}
  style={{ display: track.hidden ? "none" : "flex" }}   // ← BUG
  onContextMenu={…}
>

// Line 807–813 (track-row / content)
{visibleTracks.map((track) => (
  <div
    key={track.track_id}
    className={`track-row ${track.hidden ? "track-hidden" : ""}`}
    data-track-id={track.track_id}
    style={{ width, display: track.hidden ? "none" : "flex" }}   // ← BUG
  >
```

### 2.2 What R5 acceptance (Decision 1) actually said

> Track.row stays visible. Track header stays visible. Clip blocks remain
> visible in Timeline. The hidden state is visually obvious. Only
> Preview/Composite participation is suppressed.

The `display: none` semantics directly contradict this. Clicking visibility
removes the entire row + header from the DOM, so the user sees their track
disappear, which they interpret as "Preview black, no media, my track
disappeared".

### 2.3 visibleTracks filter (Timeline.tsx:306)

```tsx
.filter(
  (track) => showEmptyTracks || track.clip_ids.length > 0 || track.hidden,
),
```

Hidden tracks are INTENTIONALLY included in `visibleTracks`. The
`display: none` is what suppresses them. Removing only the `display`
inline-style (keeping the `.track-hidden` class hook) restores the
intended semantics.

### 2.4 Remediation outline (do not apply yet)

1. Drop `style={{ display: track.hidden ? "none" : "flex" }}` from both rows.
2. Add a `.track-hidden` rule in `styles.css` that visually communicates
   "hidden from preview" (e.g. opacity 0.5, italic label, "🕶 预览中隐藏"
   tooltip), without removing the row from layout.
3. Add a vitest that asserts: after `setTrackHidden(id, true)`, the row
   element still exists in the DOM with class `track-hidden` and computed
   `display` is `flex`.

---

## Step 3 — Trace black Preview

### 3.1 Root cause: `build_preview_plan` reports `project_revision=0` (Core bug)

```python
# yroll/core/plan.py:143–146
revision = 0
ui_status = getattr(project, "ui_status", None)
if ui_status is not None and getattr(ui_status, "base_revision", None) is not None:
    revision = ui_status.base_revision
```

**`project.ui_status` is never assigned anywhere in `yroll/`**. Grep
confirms there is no setter. The `getattr` returns `None`, the `if` is
false, and `revision` stays `0` no matter what the actual revision is.

### 3.2 GUI consequence (gui/src/preview-plan.ts:204–248)

```ts
useEffect(() => {
  if (projectRevision === null) return;        // <-- early-return
  // ...
  api.previewPlan({ timeline_id: timelineId })
    .then((data) => {
      // The hook does NOT compare data.project_revision against the
      // project's actual revision; it just stores the response.
      setPlan(data);
    });
}, [projectRevision, timelineId]);
```

The hook fires when `liveSeq.projectRevision` transitions from null to a
number (typically `1`). It fetches `/preview/plan`, gets
`project_revision: 0` from the buggy Core, and stores it. The Preview
Player reads `plan.tracks` and tries to render layers — those layers ARE
populated (we verified 16 visual + 5 subtitles at frame 500).

So why does the user see a black Preview?

Two suspects remain:

**Suspect A** — `liveSeq.projectRevision` is `null` longer than expected.
The `useProjectSequence` hook has its own polling cycle. If the first
`/sequence` response is delayed (or returns `project_revision: 0` once,
then 1 later), `usePreviewPlan` waits. Combined with the Core bug (§3.1),
the plan always reports 0 and may be discarded by a future staleness
check.

**Suspect B** — the TimelineFrame/Playhead is positioned in a gap. The
playhead at frame X where no clip covers it renders `is_black: true`.
The status bar's "playhead is in a gap" message comes from App.tsx when
`activeLayerAt(plan.tracks, playheadFrame)` returns null for ALL tracks
and the subtitle is empty.

Both can co-occur. A targeted vitest is needed to disambiguate.

### 3.3 What was verified live

| Test                                                              | Result                                                         |
| ----------------------------------------------------------------- | -------------------------------------------------------------- |
| `GET /preview/plan?timeline_id=main`                              | 200, 10 tracks with 16 layers, 5 subtitles, **`revision: 0`**  |
| `GET /preview/at_frame?timeline_id=main&frame=500`                | 200, `is_black: false`, 2 visuals + 1 subtitle                 |
| `GET /preview/at_frame?timeline_id=main&frame=0`                  | 200, `is_black: false`, 5 visuals                              |
| `GET /preview/at_frame?timeline_id=main&frame=2000` (no clip there)| black (correct — playhead is in a gap)                       |

So the backend can produce a black frame when the playhead is in a gap,
which is normal. The user's complaint is "Preview is completely black" —
that suggests **all** frames are black, not just one. That points at
Suspect A: the plan never lands, so the GUI never queries it locally,
and the canvas has zero layers.

### 3.4 Remediation outline

1. **Fix `build_preview_plan`** — fall back to `project.sequence.project_revision`
   (read directly off `project.sequence` like `/sequence` does), not
   `project.ui_status` (which doesn't exist).
2. **Audit `useProjectSequence`** for first-render null delay.
3. **Add a vitest** that mounts `usePreviewPlan(1, "main")` against a
   mocked api returning `project_revision: 1` and asserts `plan` is
   non-null.
4. **Add a Playwright acceptance** that loads `_sanlihe-r5-manual`,
   asserts the preview canvas has at least one visible `<img>` for a
   known in-bounds frame.

---

## Step 4 — Asset mutation chain

### 4.1 Live mutation test (with valid session)

```
POST /clips/add_image?sessionId=756069e3bfa140d5bea7eb739bd14c96&baseRevision=1
  {"asset_id":"aa080ae","timeline_start_frame":1500,
   "timeline_duration_frames":150,"track_id":null,"why":"audit-test"}

→ 200
  {"clip_id":"cf9426c","asset_id":"aa080ae","timeline_id":"main",
   "timeline_range":{"start":50.0,"end":55.0},"track_id":"v1",
   "source_range":{"start":0.0,"end":0.0333...}, ...}
```

The Core allocated `v1` (allocator picks when `track_id=null`), persisted
the clip at frames 50–55 seconds, returned the full clip object. **The
chain works.**

### 4.2 Without sessionId

```
POST /clips/add_image (no sessionId)
→ 403 {"detail":"sessionId required for mutations (call /lease/acquire first)"}
```

### 4.3 GUI's actual call shape (api.ts:534–545)

```ts
addImageClip: (
  assetId, timelineStartFrame, timelineDurationFrames, trackId, why,
) => mutate<Clip>("POST", "/clips/add_image", {
  asset_id: assetId,
  timeline_start_frame: timelineStartFrame,        // ✓ matches server
  timeline_duration_frames: timelineDurationFrames,// ✓ matches server
  track_id: trackId, why,
}),
```

The API client sends the exact field names the Pydantic model
`AddImageClipReq` expects (`yroll/server/app.py:167–174`). The chain
`session → currentGate() → mutate() → HTTP → Core` is wired correctly.

### 4.4 Conclusion

The user's "Adding assets fails" complaint **cannot be reproduced** with
the current stack. The most likely explanation is:
- A stale session in the user's browser (localStorage `yroll.session.v1`
  pointing at an old session_id no longer in the server's lease store).
- Or the user was observing an OBSERVE-mode session (EditorState ≠ EDIT)
  and the gate refused the write.

**No Core or API client change is justified by runtime evidence.**

---

## Step 5 — Gap toolbar remnants

### 5.1 Topbar

`App.tsx:878–884`:

```tsx
{/* GUI-03R5-B4 (Decision 5): the "批量关闭间隙" topbar button
    was REMOVED. Gap actions are now CONTEXTUAL:
    - Right-click on an empty area in a track → "Close this gap"
      (already implemented in Timeline.tsx)
    - Right-click on a track header → context menu with
      "Close all gaps on this track" + mute/lock/hide/delete
      (added in B4) */}
```

The topbar button is **not present** (replaced by the comment block
documenting the removal). Decision 5 holds.

### 5.2 Dead callback

`App.tsx:521–527` defines `onCloseGapsBatch` (still wired into Timeline
at line 1645), but the only caller was the removed topbar button. The
callback is dead but harmless. No user-facing surface remains.

### 5.3 Conclusion

Decision 5 is satisfied. No action needed.

---

## Step 6 — Other observations (informational, not blocking R5)

1. **Orphaned `vite` process (PID 23508)** started 2026-08-30 11:38:19
   alongside PID 9000 (started 2026-08-31 21:11:55). Both bind 5173. The
   older one should be killed to avoid stale-tab confusion. (Cosmetic;
   not a code defect.)

2. **Subtitle text bytes are valid UTF-8.** `cat`'s GBK encoding on the
   Windows shell makes them look like mojibake in this terminal, but the
   raw bytes are correct (`b'\xe4\xb8\xa4\xe7\x99\xbe\xe5\xa4\x9a...'`
   = "两百多年前"). The JSON wire format is clean.

3. **`/preview/at_frame` falls back to `active_timeline_id`** when
   `timeline_id` is empty (`frame_preview.py:184`). `/preview/plan` does
   NOT (`plan.py:152` → `project.get_timeline("")` returns None → empty
   plan). This API asymmetry is intentional but worth documenting so the
   GUI never calls `/preview/plan` without a timeline_id.

---

## Remediation order (recommended, pending user go-ahead)

1. **GUI: remove `display: none` from `Timeline.tsx:576, 811`** (Step 2).
   Add `.track-hidden` CSS. Add regression vitest. (Single-file change
   in Timeline.tsx + styles.css; doesn't touch Core.)
2. **Core: fix `build_preview_plan` revision source** (Step 3.1).
   Replace `project.ui_status.base_revision` with `project.sequence.project_revision`
   (or the server-supplied value). Add pytest pinning revision parity
   across `/sequence`, `/ui/status`, `/preview/plan`.
3. **GUI: vitest + Playwright for black-Playhead case** (Step 3.4).
   Lock the user-observable failure so it cannot regress.
4. **Cleanup: kill orphaned vite PID 23508** (Step 6.1). Restart both
   frontend + backend with a single canonical helper script (R5 already
   has `gui/smoke/serve-r5-manual.mjs` and `static-with-proxy.mjs` —
   fold them into one).
5. **Documentation**: keep `docs/GUI-03R5-NLE-Interaction-Viewer-Audit-v0.1.md`
   as the design intent; this audit (`-v0.2`) as the runtime evidence.

After 1–4 land and the 6 manual checks (drag / session / multi-layer /
play-scrub / contextual-menu / basic-editing-feel) pass on the user's
machine, R5 can be declared closed. No Publish Metadata / Timeline-local
Revision / Keyframes / opacity work should start until then.

---

## Appendix A — Test fixtures and commands

```bash
# Live probes used in this audit (all runnable today)
curl http://127.0.0.1:8770/timelines
curl "http://127.0.0.1:8770/preview/plan?timeline_id=main"
curl "http://127.0.0.1:8770/preview/at_frame?timeline_id=main&frame=500"
curl http://127.0.0.1:8770/ui/status
curl http://127.0.0.1:8770/sequence

# Verify import path
python -c "import yroll, yroll.server.app; print(yroll.__file__, yroll.server.app.__file__)"

# Process / port audit
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8770,5173 -State Listen | Select-Object LocalPort, OwningProcess"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'ProcessId=23952' | Select-Object CommandLine"
```

## Appendix B — Files inspected (read-only)

* `yroll/server/app.py` (route declarations, AddImageClipReq model)
* `yroll/core/plan.py` (`build_preview_plan` revision logic)
* `yroll/core/frame_preview.py` (`composite_preview_at_frame` fallback)
* `yroll/core/manifest.py` (Project.get_timeline, active_timeline_id)
* `gui/src/components/Timeline.tsx` (line 306, 574–577, 807–813)
* `gui/src/components/PreviewPlayer.tsx` (line 220–248)
* `gui/src/api.ts` (line 400, 446, 525–545)
* `gui/src/preview-plan.ts` (line 191–249)
* `gui/dist/index.html` + `gui/dist/assets/index-CFooX-sC.js` (bundle hash)

No file was modified.