# GUI-03 Production Usability Spec v0.1

**Status:** Draft (based on 2026-08-29 三里河垂直切片 36s production reality test)
**Sources:** `sanlihe-story` (90s 完整版) + `sanlihe-slice-30s` (36s 切片)
**Scope:** User-facing production usability only. Does NOT touch mutation gate, time model, keymap, or frame-clock (those are already shipped in Foundation v0.2 → GUI-02).

---

## 0. Reality Test — Pain Points Discovered

Walking the 36s slice end-to-end surfaced these user-visible frictions:

| # | Pain | Where it bites | Concrete example |
|---|---|---|---|
| **P1** | Empty default tracks clutter Timeline | `core.project.timeline.tracks` is auto-populated with v1/v2/v3/a1/a2/a3/t1/t2; the slice has content only in v1+t1, but the other 6 empty tracks still show | "Why is there v2 / a1 / a2 in my empty slice timeline?" |
| **P2** | Image clip duration is a kludge | `add_clip(image, 0.0, 5.0, ...)` + `set_speed(5.0/duration)` — image has no intrinsic source duration; speed=2.5 to get 2s timeline is semantically wrong | The slice has speed=1.67 on a 3s clip; the source has nothing to play at 1.67x speed; it just lies |
| **P3** | Preview shows nothing for image-only timelines | `PreviewPlayer` queries `vtrack.clip_ids`; image-only slice → empty preview | "I added 10 image clips but Preview says 时间轴是空的" |
| **P4** | One Project = one Timeline | Can't have 种草版 + 收割版 + 视频号版 in one project; each is a separate `ProjectCore` on disk | "I want to fork the slice into a 抖音版 and a 视频号版" |
| **P5** | Track header / content geometry contract is implicit | `LABEL_GUTTER_PX=80` shifts frame 0 to px=80; a 9th clip starts at frame 0 visible but a casual user might think "frame 0 = px 0" | Minor; documentation gap |
| **P6** | Lease UX is OK but verbose | `🟢 编辑权：我 r<N>` shows for a long time on slow boot | Minor; not blocking |
| **P7** | "ramp" source FPS missing for image assets | `Asset.source_fps = None` for images; TimeMap falls back to seq fps | Acceptable; image clips don't need TimeMap math |

**P1, P2, P3, P4 are blockers for the next real production test.** P5/P6/P7 are polish.

---

## 1. Timeline Gutter / Frame-0 Geometry

### Spec (CURRENTLY MET, must pin in code+docs)
- Track header (label column) lives in a left gutter `LABEL_GUTTER_PX = 80`.
- Timeline content area starts at `x = LABEL_GUTTER_PX`.
- Frame 0 is at content area `x = 0` (NOT container `x = 0`).
- The ruler's `paddingLeft = LABEL_GUTTER_PX` and `localX = e.clientX - rect.left - LABEL_GUTTER_PX` is the convention for hit-testing.
- Frame-0 tick is rendered at `content x = 0` (a vertical line + the label "0").

### What's missing
- No explicit "this is the gutter contract" doc in Timeline.tsx header.
- No visual indication that the gutter is not editable content.

### Acceptance Criteria
- Track header `<div>` and timeline content `<div>` are siblings, both inside a flex container. (Already true; verify.)
- Cursor over gutter shows `cursor: default`; cursor over content shows grab/drag.
- Frame-0 tick visible at content x=0, even when content is empty.

### Priority
**P1 — ship in GUI-03A (docs + cursor + frame-0 tick).** Already-correct geometry just needs to be made obvious.

---

## 2. Media Model: Image as First-Class Timeline Media

### Current state (kludgy)
- `add_clip(asset_id, src_start=0.0, src_end=5.0, timeline_start=10.0, ...)` → caller picks arbitrary source range (0..5s), then `set_speed(5.0/duration)` to fake a target timeline duration.
- For images this means: speed=2.5 to make a 2s clip from a 5s "source range" — semantically a lie (image has no duration).

### Spec (target model)

| Field | Meaning |
|---|---|
| `Asset.duration_sec` | Real media duration. Images: `None` (still). Videos: actual seconds. Audio: actual seconds. |
| `Clip.source_range` | For video/audio: `[in, out)` in seconds within the asset. For image: `[0, 0)` (empty; the image is one frame). |
| `Clip.speed` | For video/audio: 1.0 default. For image: locked to 1.0 (no time scaling). |
| `Clip.timeline_range` | The actual visible range on the timeline. For image: caller-specified, e.g. 3s. For video/audio: derived from source_range and speed. |

### Concrete Core changes
- New command: `add_image_clip(asset_id, timeline_start, timeline_duration, track_id='v1', why='')`
  - Source range is `[0, 0)` (image has no in/out — image is one frame).
  - Speed is locked at 1.0.
  - `timeline_range` = `(timeline_start, timeline_start + timeline_duration)`.
- `set_speed` rejects image assets with a clear error: "image clips cannot change speed; adjust timeline_duration instead".
- `Asset.source_fps` remains None for images (no time math needed); TimeMap math for image clips is a no-op (source frames = 0).

### GUI implications
- Image clip render: just paint the still for `timeline_duration` seconds with Ken Burns (scale/translate).
- Trim handle: drag right edge → adjust `timeline_duration`. The left edge is fixed (image has no source range to trim from).
- Speed control on an image clip: hidden (or grayed out with the explanation).

### Acceptance Criteria
- `add_image_clip(asset_id, ts=10, dur=3)` produces a clip with `timeline_range=(10,13)`, `source_range=(0,0)`, `speed=1.0`.
- The slice script can be rewritten as `add_image_clip(...)` per shot; no `set_speed` hack.
- Trimming an image clip extends/contracts its on-screen duration.
- A user cannot crash YROLL by trimming an image past zero (server rejects with 400).

### Priority
**P1 — ship in GUI-03B.**

---

## 3. Dynamic Track Allocation

### Current state (over-allocated)
- `ProjectCore.create()` pre-creates 8 tracks: v1, v2, v3, a1, a2, a3, t1, t2.
- Empty tracks still render in the Timeline UI.
- The slice script's `core.project.timeline.tracks = [...]` filter does NOT survive `core.save_state()` (the Project pydantic model's default_factory for tracks is reset on validation).

### Spec (target model)

#### Track creation policy (Core-side)
| Trigger | Action |
|---|---|
| First image / video asset added with `asset_type='video'` and `track_id='v1'` (or no track specified) | Allocate `v1` if not present |
| First audio asset | Allocate `a1` if not present |
| First subtitle text | Allocate `t1` if not present |
| PiP / overlay | Allocate `v2`, `v3` |
| Asset placed on `track_id='v9'` (user-chosen) | Allocate `v9` (named track; user owns the layout) |
| Track has zero clips AND no future placement references it | Hide from UI (Core keeps it for `track_ids` lookup but `Timeline.rendered_tracks()` filters empty tracks) |

#### Per-track policy
| Kind | Allowed asset types | Default |
|---|---|---|
| `video` | video, image | First video/image → `v1` |
| `audio` | audio | First audio → `a1` |
| `subtitle` (text) | text (subtitle kind only) | First subtitle → `t1` |
| `pip` (PiP overlay) | video, image | First PiP → `v2` (created on demand) |
| `screen_recording` | video, image | reserved for future |
| `voiceover` | audio | reserved |

#### Future semantic track role (for later — not GUI-03)
Each track carries a `role: Optional[TrackRole]` (e.g. "main", "b-roll", "voiceover", "sfx", "captions"). GUI-03 leaves the field as None; later batches populate it.

### Acceptance Criteria
- Empty `sanlihe-slice-30s` project shows ONLY v1 + t1 (no empty v2/v3/a1/a2/a3/t2 in the rendered timeline).
- Adding an image creates `v1` if absent.
- Adding an audio creates `a1` if absent.
- Removing all clips from a track leaves the track in `core.project.timeline.tracks` (so existing clips referencing it aren't broken) but hides it in the UI.
- Track-policy enforcement: `add_clip(image, ... track_id='a1')` → server rejects with 400 "track a1 (audio) rejects asset type image".

### Priority
**P1 — ship in GUI-03C.**

---

## 4. Preview: L1 Local Composite

### Current state (misleading)
- `PreviewPlayer` queries `vtrack = project.timeline.tracks.find(kind == 'video')`.
- For an image-only timeline (the slice), `vtrack` exists but has image clips, not videos.
- The Player shows "📭 时间轴是空的——从素材库拖到 V1 轨" or "⏰ 播放头在间隙里" depending on whether the playhead is on a clip.
- The user perceives this as "Preview broken"; reality is "Preview only handles video assets".

### Spec: distinguish Source Preview vs Timeline Composite Preview

#### Source Preview (per-clip, asset-backed)
- Shows the asset at the playhead's source frame (after TimeMap.source_from_timeline conversion).
- For images: paints the still (Ken Burns scale/translate over the on-screen duration).
- For video: plays the source media at the source frame's timestamp.
- This is what `/frame/preview` does today.

#### Timeline Composite Preview (the user's expectation)
- Renders ALL clips at the playhead, layered by track (v3 over v2 over v1; audio mixed; subtitles overlaid).
- Image clips: paint the still for the entire on-screen duration (Ken Burns if specified).
- Video clips: paint the source frame at the playhead's source timestamp.
- Audio clips: synchronized playback.
- Subtitles: text overlay at the bottom.
- Black gap: nothing on screen (the playhead is between clips).

#### L1 Local Composite (minimum useful)
For GUI-03, ship the **Timeline Composite Preview** at minimum:
- For each `track` containing a clip that covers the playhead:
  - If asset type is `image`: paint still to a `<canvas>` or `<img>` overlay, optionally with Ken Burns.
  - If asset type is `video`: paint `<video>` element at the source-seconds timestamp.
  - If asset type is `audio`: start `<audio>` synchronized.
- Subtitle: show the text overlay if playhead is within a subtitle clip.
- Play / pause / seek: as today (via FrameClock).
- Frame rate: image clips render at frame rate (refresh rate); video clips play at asset source rate; audio follows video.
- **NOT required**: real-time Resolve-grade compositing, GPU-accelerated blending, color grading, transitions, effects.

#### Why "minimum" not "fully featured"
The user said: "不要求本批次达到 Resolve 级实时渲染". L1 is good enough to verify the cut looks right and the audio doesn't clip. Heavy compositing comes later (GUI-04+ when Selection + multi-track blends are needed).

### Core changes
- `Project.frame_preview(playhead_frame)` returns a structured `CompositeFrame`:
  ```python
  {
    "timeline_frame": int,
    "playhead_in_gap": bool,
    "tracks": [
      {"track_id": "v1", "kind": "video", "asset_type": "image"|"video"|"audio",
       "clip_id": ..., "source_frame": int, "media_seconds": float, "asset_path": str,
       "transform": {"x", "y", "scale", "bg_blur"}},
      ... for v2, v3, a1, a2, a3, t1, t2 ...
    ],
    "subtitle": "text overlay if a subtitle clip covers the playhead",
  }
  ```
- The existing `frame_preview.resolve_frame()` API is upgraded to return this richer shape. `video_source_frame` becomes a per-track field.
- Image clips: `source_frame` is always 0 (image has no time); the GUI ignores it for rendering but the field is still present for symmetry.

### GUI changes
- `PreviewPlayer` renders `<img>` (for image assets) or `<video>` (for video assets) per track.
- Layering: track order (v3 above v2 above v1) → CSS z-index or stacked `<div>`s.
- Subtitles: bottom overlay.
- Audio: a single `<audio>` per audio track that's active; synchronized to the FrameClock.
- "Gap" → black screen + (if subtitle) the subtitle text.

### Acceptance Criteria
- For the slice (image-only, no video):
  - Playhead at frame 0 (0.0s) → shows oracle_feng_01.jpg with Ken Burns scale 1.08; no "时间轴是空的" message.
  - Playhead at frame 5 (5.0s) → shows painting_gaofenghan_hd.jpg.
  - Playhead at frame 35 (35.0s) → shows pottery_longshan_red.jpg.
  - Subtitles appear at the right time.
- For mixed timeline (some video, some image): video tracks play their `<video>`; image tracks paint their `<img>`; all layered correctly.
- Pressing Space → all tracks start/pause in sync.

### Priority
**P1 — ship in GUI-03D.**

---

## 5. Multiple Timelines / Sequences

### Current state (one project = one timeline)
- `Project.timeline: Timeline` (singular).
- `Timeline` owns `tracks: list[Track]`; tracks own clip ids; clips live in `Project.clips: dict[clip_id, Clip]`.
- To have a 种草版 and a 收割版, you `ProjectCore.create()` two projects on disk.

### Spec: Project holds a list of Timelines

#### Data model
```python
class Project:
    ...
    timelines: list[Timeline]  # replaces `timeline: Timeline`
    active_timeline_id: str   # the one currently being edited
    default_timeline_id: str  # the first timeline created with the project

class Timeline:
    timeline_id: str          # NEW: unique within Project
    name: str                 # NEW: human label "种草版 / 收割版"
    derived_from: Optional[str]  # NEW: timeline_id of the parent (for Fork)
    fps: Rational             # MOVED from Sequence (timeline-level fps)
    width: int
    height: int
    drop_frame: bool
    tracks: list[Track]
    # created_at, note, etc.
```

#### Backward compat
- `Project.timeline: Timeline` is deprecated but kept as a property that returns `timelines[active_timeline_id]`.
- `Sequence` stays as a project-level metadata (drop_frame for the OUTPUT render).
- Migration: on load, if `project.timelines` is empty but `project.timeline` exists, lift it into `timelines` and set `active_timeline_id = timeline_id`.

#### Fork
- New Core API: `cmd_fork_timeline(timeline_id, new_name, why='') → Timeline`
  - Creates a new Timeline with `derived_from = timeline_id`.
  - Copy all `Track`s (empty); copy all `Clip`s from the source timeline.
  - Re-link clip_ids in the new tracks.
- Used by: Human "save as 种草版 from 当前版".

#### List of use cases (initial)
- `default` — created with the project
- `种草版`
- `收割版`
- `IP版` (long-form, 90s+)
- `抖音版` (vertical 9:16, 30s)
- `视频号版` (vertical 9:16, 60s)
- `微信版` (1:1 or 4:3, 30s)
- ... user can add custom names

#### Future: derived_from / compare / diff
- `derived_from: Optional[str]` field already populated.
- `compare(timeline_a, timeline_b) → DiffResult` (later batch).
- "WolfCut README mentions multiple timelines per project" — reference for the model, not the implementation.

### Acceptance Criteria
- `project.timelines` returns a list with ≥1 entry (the default).
- `project.active_timeline_id` defaults to the first timeline.
- Fork creates a new timeline with `derived_from` set; all clips duplicated.
- Switching `active_timeline_id` in the GUI shows that timeline's tracks/clips (others preserved).
- The slice script (which currently writes to the default timeline) can write to a named timeline without losing the original.

### Priority
**P2 — ship in GUI-03E.** (Most important for the 种草/收割 multi-version workflow but data-model change is bigger.)

---

## 6. Connection / Lease UX

### Current state (acceptable but verbose)
- `sessionStore.startPolling()` starts on app mount.
- Top bar shows: "🟢 编辑权：我 r<N>" (after lease acquire) or "🔴 获取编辑权" (if polling hasn't succeeded).
- Manual button "获取编辑权" works if auto-acquire fails (revision conflict).

### Spec
- **Normal start:** auto-connect + auto-acquire should complete within ≤2s on localhost. The top bar shows "🟢 编辑权：我 r<N>" and DOES NOT obscure the editing UI.
- **Failure:** only show error toast / banner if connection or acquire fails. The polling should keep retrying silently in the background.
- **Top bar layout:** "🟢 编辑权：我 r<N>" should be a thin top strip (24-32px), not a card. Current width should fit in `<200px`.
- **Editing UX invariant:** while editing, the lease/connection status is visible but does NOT require user attention. The user can edit for hours without seeing an "edit locked" interruption.

### Acceptance Criteria
- App boot → ≤2s to "🟢 编辑权：我 r<N>".
- During normal editing, the top bar doesn't cover any editing surface.
- On disconnect, a small toast appears; the lease/connection state in the bar shows 🔴; polling retries silently.
- After reconnect, the bar goes 🟢 without user intervention.

### Priority
**P1 — minor polish in GUI-03F.**

---

## 7. Real Workflow (end-to-end)

This is the scenario the slice test exercises. Spec: it must WORK.

```
[Agent] build_sanlihe_slice.py
  └─> ProjectCore.create("sanlihe-slice-30s")
  └─> asset reuse from sanlihe-story
  └─> add_image_clip(...) × 10
  └─> add_subtitle(...) × 6
  └─> core.save_state()

[YROLL Server] python -m yroll.cli.main serve projects/sanlihe-slice-30s
  └─> serves /project, /ui/status, /frame/preview, /clips/{id}/trim, /clips/{id}/move, /clips/{id}/split, /snap, /keyboard/keymap

[Human] http://localhost:5173/
  └─> open editor → see slice loaded
  └─> drag clips to refine timing
  └─> trim edges to fix durations
  └─> Preview shows the result (image + subtitle + audio if any)
  └─> Fork to 抖音版 / 视频号版 → adjust fps + aspect ratio → save
  └─> Export → see if rendering pipeline can produce MP4
```

### Acceptance Criteria
- Agent script → Core write → Core read → GUI display: no manual intervention.
- Human can refine the cut without losing the Agent's coarse cut.
- Human can fork into multiple platform-specific versions in a single Project.

### Priority
**P0 — this is the test that the chain works.** All of GUI-03A-D are P0.

---

## 8. Priority Matrix

| Item | Priority | Core supported? | Core change? | GUI-only? | Batch |
|---|---|---|---|---|---|
| **1. Timeline gutter / frame-0 geometry** | P1 | Yes | None (clarify docs + visual tick) | Yes | GUI-03A |
| **2. Image as first-class media** | P1 | Mostly (add_clip accepts image; but duration model is kludgy) | YES — `add_image_clip` command; `set_speed` rejects image | API client update | GUI-03B |
| **3. Dynamic track allocation** | P1 | Partial (tracks pre-created) | YES — default factory removed; allocate on first use; hide empty | Render-side filter | GUI-03C |
| **4. L1 Composite Preview** | P1 | Partial (`frame_preview` for single asset) | YES — richer `CompositeFrame`; image-aware | PreviewPlayer renders images | GUI-03D |
| **5. Multiple Timelines / Fork** | P2 | No (Project.timeline: single) | YES — `timelines: list[Timeline]`; `active_timeline_id`; `cmd_fork_timeline` | GUI: timeline switcher | GUI-03E |
| **6. Lease UX** | P1 | Yes | None | Polish bar layout | GUI-03F |
| **7. Real workflow validation** | P0 | Yes | None (depends on 2-5) | None | Verified by slice test |

---

## 9. Core Capabilities (what already exists vs what needs to be added)

### Already in Core (Foundation v0.2 + GUI-02)
- ✅ `Project` pydantic model with `clips`, `assets`, `tracks`, `commands`, etc.
- ✅ `Sequence` (project-level output metadata).
- ✅ `Timeline` with `tracks: list[Track]`; `Track` with `kind`, `clip_ids`, `transform`, etc.
- ✅ `Asset` with `source_fps`, `source_is_cfr`, `duration_sec` (already on `AssetIdentity`).
- ✅ `Clip` with `source_range`, `timeline_range`, `speed`, `volume`, `transform` (Ken Burns), etc.
- ✅ `CommandLayer`: `add_clip`, `add_subtitle`, `set_speed`, `set_transform2d`, `set_fade`, `revert`, `redo`, `set_volume`, `mute`, `split_clip_frame`, `trim_clip_frame`, `move_clip_frame`.
- ✅ `frame_preview.resolve_frame(project, frame, fps) → FramePreview`.
- ✅ HTTP API: `/project`, `/clips/{id}/trim`, `/move`, `/split`, `/snap`, `/frame/preview`, `/ui/status`, `/keyboard/keymap`.

### Missing in Core (need to add for GUI-03)
- ❌ `add_image_clip(asset_id, timeline_start, duration, track_id, why)` — image-first-class duration.
- ❌ `set_speed` rejects image assets.
- ❌ `Project.timelines: list[Timeline]`, `active_timeline_id`, `default_timeline_id`.
- ❌ `cmd_fork_timeline(timeline_id, new_name, why)` — Fork.
- ❌ `cmd_rename_timeline(timeline_id, new_name, why)` — UI rename.
- ❌ `cmd_delete_timeline(timeline_id, why)` — UI delete (with safety: refuse if it's the last).
- ❌ `cmd_set_active_timeline(timeline_id)` — UI switch.
- ❌ Track creation policy: `cmd_ensure_track(kind, track_id=None)` — used by `add_clip` to lazily create.
- ❌ `frame_preview.resolve_frame` returns `tracks: list[TrackComposite]` for composite preview.
- ❌ `Timeline.derived_from: Optional[str]`.
- ❌ Track policy: `Track.accepts_asset_type(asset_type) -> bool` (centralizes the rules in commands.py line 248).

### GUI-only (no Core change)
- ✅ `LABEL_GUTTER_PX` doc.
- ✅ Frame-0 tick render.
- ✅ PreviewPlayer renders images + composite.
- ✅ Timeline switcher UI.
- ✅ Empty-track hide.
- ✅ Top-bar layout polish.

---

## 10. Batch Plan

| Batch | Items | Est. scope |
|---|---|---|
| **GUI-03A** Timeline gutter | (1) | Tiny — docs + 1 visual element |
| **GUI-03B** Image as first-class media | (2) | Small — 1 new command + API client + preview glue |
| **GUI-03C** Dynamic track allocation | (3) | Medium — Core track policy + render-side filter |
| **GUI-03D** L1 Composite Preview | (4) | Medium — richer FramePreview + PreviewPlayer renders images |
| **GUI-03E** Multiple Timelines + Fork | (5) | Larger — Project data model change + new commands + UI switcher |
| **GUI-03F** Lease UX | (6) | Tiny — top-bar polish |
| **GUI-03 (verify)** | (7) | Production test with the slice; iterate |

---

## 11. Don't-Do (out of scope for GUI-03)

- ❌ Real-time GPU compositing.
- ❌ Color grading / scopes.
- ❌ Multi-cam editing.
- ❌ Plugin / extension API.
- ❌ Cloud sync.
- ❌ AI-driven auto-edit (future batch).
- ❌ EditorSelection / multi-clip mutation (that's GUI-04, after GUI-03).
- ❌ Audio mixing (gain, pan) beyond current per-clip volume.

---

## 12. Open Questions (need user input before GUI-03E)

1. **Storage format**: when Project.timeline becomes Project.timelines (list), do we migrate existing `current.json` on disk, or version-bump?
2. **Fork semantics**: does Fork copy `asset` references (yes) or create separate Asset records per timeline? (Default: same Asset, separate Timeline.)
3. **Default timeline on project open**: open the most-recently-active timeline, or the default_timeline_id?
4. **Empty timeline deletion**: allow deleting the last remaining timeline? (Probably no; refuse with 400.)

---

## 13. Acceptance Test (after GUI-03 lands)

A real coarse-cut script:
```python
# scripts/build_sanlihe_3version.py
core = ProjectCore.create('sanlihe-3v')
# ... add assets, add_image_clip × 12, add_subtitle × 6 ...
cmd_fork_timeline(default, '抖音版', why='9:16 vertical')
cmd_fork_timeline(default, '视频号版', why='60s landscape')
# Now: 3 timelines in one project, sharing assets.
```

Human opens `http://localhost:5173/`, switches timelines, edits each:
- 抖音版: trims each clip to <2s (TikTok pacing).
- 视频号版: extends durations (longer-form pacing).
- IP版: keeps the 36s dramatic version.

Then:
- Preview shows images + subtitles + audio for each.
- Drag, trim, split all work.
- Undo / redo per timeline.
- Fork tree visible (derived_from chains).

If this works → GUI-03 closes. → GUI-04 (Selection + multi-clip mutation).

---

**End of GUI-03 Production Usability Spec v0.1**