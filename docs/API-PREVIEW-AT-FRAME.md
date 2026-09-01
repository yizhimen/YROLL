# API Contract: `/preview/at_frame`

**Status**: Frozen as of R6.2-B4. Any change to the wire format or
semantics requires updating this document AND adding the same version
constant to the response.

**Endpoint**: `GET /preview/at_frame?timeline_id=<id>&frame=<int>`

**Source of truth**: `yroll/core/frame_preview.py:composite_preview_at_frame`

---

## Contract (frozen)

### Request

| parameter  | type   | required | description |
|------------|--------|----------|-------------|
| `timeline_id` | string | optional | Target Timeline id. Empty/missing falls back to `active_timeline_id` (legacy). |
| `frame`       | int    | required | TimelineFrame in sequence-fps coordinates. Must be ≥ 0. |

### Response (200 OK)

```json
{
  "timeline_frame": 1500,
  "fps": {"num": 30, "den": 1},
  "is_black": true,
  "visual_layers": [],
  "audio_layers": [],
  "subtitle_texts": []
}
```

| field           | type            | description |
|-----------------|-----------------|-------------|
| `timeline_frame`| int             | Echo of the requested frame (sanity-check for client cache key). |
| `fps`           | {num, den}      | Sequence fps used to compute frame<->source conversion. |
| `is_black`      | bool            | `true` iff `visual_layers` + `audio_layers` + `subtitle_texts` are all empty. |
| `visual_layers` | CompositeLayer[]| One entry per active visual clip on a visible track at this frame (z-ordered). |
| `audio_layers`  | CompositeLayer[]| One entry per active audio clip. |
| `subtitle_texts`| string[]        | Active subtitle text snippets at this frame. |

`CompositeLayer` (each entry in `visual_layers` / `audio_layers`):

```json
{
  "track_id": "v1",
  "layer_index": 0,
  "kind": "image",
  "clip_id": "c4c290d",
  "asset_id": "a2629cb",
  "asset_path": "projects/sanlihe/.../img.jpg",
  "source_frame": 0,
  "source_seconds": 0.0,
  "source_fps": null,
  "timeline_start_frame": 0,
  "timeline_end_frame": 150,
  "transform": {}
}
```

---

## Semantic rules

### Membership (R6.2-B4 contract)

A clip is "active at frame F" iff `timeline_start_frame <= F <
timeline_end_frame` (half-open interval). Frames are in sequence-fps
coordinates.

### Hidden tracks (R5 fix, preserved)

A track with `hidden == true` contributes ZERO layers and ZERO
subtitles to the response, regardless of clip membership at F.

### z-order (R4-1)

`layer_index` in `visual_layers` follows the global stack order
(`KIND_RANK + numeric-suffix sort` of non-hidden visual tracks).
The bottom layer fills the canvas; overlays stack on top. The
`layer_index` values in the at_frame response MUST match the same
values used in `/preview/plan` for the corresponding clips.

### Relationship to `/preview/plan`

`/preview/at_frame` is the **materialized view of `/preview/plan`
at frame F**. Concretely:

- For every `Layer` `L` in `at_frame(T, F).visual_layers`, there
  exists a `PreviewLayer` `P` in `plan(T).tracks[*]` such that
  `P.clip_id == L.clip_id` and `P.timeline_start_frame <= F <
  P.timeline_end_frame`.
- The reverse is NOT true (plan has every layer for the timeline;
  at_frame has only the active one at F).
- `at_frame`'s `layer_index` matches the plan's `layer_index` for
  the same layer.
- `at_frame.is_black == true` iff plan has no active layer at F
  (after hidden exclusion).

### Cacheability

`/preview/at_frame` is a **non-cached** pure function of
`(project, frame, timeline_id)`. The server NEVER caches it. Clients
MAY cache by frame+timeline_id+revision client-side.

### Stability across revisions

`/preview/at_frame` always reflects the project's CURRENT state,
regardless of `project_revision`. The response does NOT embed
`project_revision` (use `/ui/status` for that).

### Failure modes

| scenario            | response |
|---------------------|----------|
| Unknown timeline_id | 200 with empty `visual_layers` / `audio_layers` (no error) |
| frame < 0           | 200 with `is_black: true` |
| timeline_id missing | 200 using `active_timeline_id` (legacy) |
| Server exception    | 500 (no special handling — propagates) |

---

## Versioning

This is **v1** of the contract. Any breaking change to field names,
semantics, or hidden-track behavior requires:
1. Bumping this version.
2. Adding `api_version` field to the response.
3. Updating GUI's `composite_preview_at_frame` consumer.
4. Documenting the migration in this file.

---

## Reference: Core implementation

The endpoint handler is at `yroll/server/app.py:preview_at_frame`
(around line 2044). It delegates to
`yroll.core.frame_preview.composite_preview_at_frame`.

The implementation iterates the timeline's tracks in
**stack order** (KIND_RANK + numeric suffix), skipping hidden tracks,
and collects the first matching clip per track (using the same
`_find_overlap`-style membership check that `build_preview_plan`
uses). This guarantees the `/preview/at_frame` and `/preview/plan`
membership sets are consistent.

**Do not implement an independent layer-selection algorithm in
`/preview/at_frame`.** The R6.2-B4 fix consolidates the
implementation onto the same Core resolution path
(`build_preview_plan` + a thin `activeLayerAt` per-track lookup),
so the two endpoints share membership logic by construction.