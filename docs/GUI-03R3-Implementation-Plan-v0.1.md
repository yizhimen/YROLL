# GUI-03R3 Implementation Plan v0.1

> **Status:** plan only. **No code yet.**
> **Baseline:** `bd088af` (post-GUI-03R3-2 Timeline Workspace Stabilization, 11/11 browser PASS).
> **Source audits:** `docs/GUI-03R3-Workspace-Reality-Audit-v0.2.md`, `docs/GUI-03R3-Timeline-Workspace-Spec-v0.1.md`.
> **Driver:** the audit identified (a) two real keyboard bugs, (b) a Core model gap for `Timeline.publish_metadata`, and (c) missing Track auto-add/auto-delete semantics.
> **Scope:** batches 03R3-W-A through 03R3-W-G, plus a NEW batch 03R3-W-T (Track auto-add / auto-delete, the most architecturally significant item).

---

## 0. Architectural decisions (locked before any batch ships)

These decisions resolve the design tensions surfaced by the audit and the user's feedback. They are pinned here so each batch can be reviewed against them.

### 0.1 Workspace is one interaction system, not isolated patches

The user said "Treat Timeline Workspace as an interaction system". Concretely:
- Track header / drag / selection / preview / publish / gaps are coupled at the user level. Changing one in isolation can shift the meaning of another.
- We batch changes so each batch delivers a *coherent* UX delta, not a single bug fix.
- We never ship a UI change without the Core mutation that gives it teeth.

### 0.2 Core owns the structural rules; UI owns the affordances

The user's feedback on auto-Track says: "请把它作为 GUI-03R3 的 Workspace behavior/invariant 设计，而不是临时 workaround。重要设计原则：Track 是由 Timeline 中实际存在的 Clip 集合推导出来的工作区结构，而不是要求用户预先维护的一组空容器。"

Concretely:
- `add_clip`, `add_image_clip`, `add_subtitle`, `move_clip`, `remove_clip`, `ripple_delete_clip`, `delete_selection`, `move_selection` ALL take an explicit `track_id` option. When the caller passes `None`, Core's allocator (`allocate_track_for`) picks a compatible non-overlapping track OR creates a new one of the right kind.
- **Core never consumes GUI pixel coordinates.** The Core layer exposes *structural* intents only (`asset_type`, `prefer_kind`, `tl_start`, `tl_end`, `timeline_id`). The GUI is responsible for resolving pointer geometry (x, y, hit-test against rendered track rows) into semantic intent: `target_track_id | create_new_track | insert_after_track_id | kind`. Once the GUI has produced that intent, Core resolves the actual track (existing or freshly created) without ever seeing DOM pixels. Concretely: the W-C drop handler will call something like `ensure_track_for_drop(asset_type, prefer_kind=kind, insert_after_track_id=resolved_track_id_or_null, timeline_id)` where `insert_after_track_id=null` means "create a new track at the end of the kind bucket". **No `drop_y_position` parameter ever crosses the boundary.**
- `remove_empty_tracks(timeline_id, except_track_ids=[])` becomes the cleanup pass that runs after any clip removal, move, ripple, or batch operation. It is **NOT** a public mutation that emits its own operation; it is folded into the same atomic command (see §0.3).

### 0.2.1 Track identity is stable across auto-add/auto-delete

Track IDs are structural references. Auto-delete MUST never renumber the remaining tracks:

- After V1/V2/V3 exists, deleting the last clip on V2 leaves V1 and V3 as **V1 and V3** — their IDs do not change.
- A future newly-allocated visual track uses the lowest unused id in the kind bucket (so V4 is the next created track after V2 is gone — V2's id remains "available" for future re-use, but V1/V3 are never touched).
- Cross-track moves, batch ops, undo/redo, and Duplicate Timeline all depend on stable track ids to keep Clip → Track references valid.
- **No Core mutation renames an existing Track.** Only `_next_track_id_for_kind` may allocate a brand-new id; it never reassigns one.

### 0.3 Atomicity rules

Every mutation that could affect Track structure MUST be one atomic Core command — and multi-clip mutations must reach Core as a single Operation, never as a GUI loop:
- "remove clip" → if its track becomes empty, also remove the track → ONE `remove_clip` Operation whose `after` includes `removed_tracks: [track_ids]`.
- "move clip across tracks" → if its old track becomes empty, also remove the old track → ONE `move_clip` Operation whose `after` includes `removed_tracks`.
- "ripple delete" → same.
- "delete N clips" (whether preserve-gap or ripple) → ONE `delete_selection(Selection, ripple=...)` Operation. The GUI MUST NOT loop `removeClip`. The Core command already exists (`commands.py:1211`) and emits one composite `_apply_record("delete_selection", ...)` regardless of selection size.
- "move N clips" → ONE `move_selection(Selection, delta_seconds, new_track_id?)` Operation. The Core command already exists (`commands.py:1137`).
- "batch close gaps" / "batch delete" → one Operation per track, batched inside Core.

The GUI never sees the intermediate "empty track" state. The state the user sees is always canonical: empty tracks don't exist.

The Core enforces this by a single helper `_cleanup_empty_tracks(tl, except_track_ids)` called at the end of `remove_clip`, `move_clip`, `ripple_delete_clip`, `delete_selection`, and `move_selection`. **It is forbidden to ship a Core mutation that leaves a track empty.** A static guard (`tests/test_no_orphan_empty_tracks.py`) asserts this invariant on every TestClient mutation.

### 0.3.1 GUI does not loop Core mutations for multi-clip actions

Per the user correction: "Foundation already exposes `delete_selection` / `move_selection`. Do not harden the GUI into a loop of individual `removeClip()` operations for multi-selection. Provide a selection-level mutation path, preserving one user intent = one Operation where feasible."

For W-A:
- A new server endpoint `POST /selection/delete` wraps `cmd.delete_selection(Selection.many(ids), ripple, why)` so the GUI can reach it.
- The keyboard Delete key, the keyboard Shift+Delete, the multi-select "全部删除" button, and the multi-select "Ripple 删除" button ALL route through `api.deleteSelection(clipIds, ripple, why)`.
- The single-clip Inspector buttons (delete / Ripple) stay on the existing `api.removeClip(...)` paths because the impact-preview UX (`pendingDelete`) and the single-clip Ripple UX already operate as ONE Core Operation each. They are not part of the multi-clip loop problem.

For W-G (gap operations), Close Gap uses a per-track Operation and Batch Close Gaps emits one Operation per track. Close Gap is distinct from Ripple Delete — they have different intents (delete-clip-with-shift vs. close-an-empty-range).

### 0.4 Pinned vs derived tracks

Today the model has no "pinned track" concept. Per user feedback: "除非 Core 明确存在 reserved/pinned tracks，否则..." — since no pinned tracks exist, ALL tracks are derived from clip presence.

If we ever add `Track.pinned: bool = False` (deferred — out of v0.1), the cleanup pass would skip pinned tracks. For now, the invariant is: "every track has ≥1 clip".

### 0.5 Track identity is stable across auto-add/auto-delete

- New tracks are named via the existing `_next_track_id_for_kind` allocator (lowest unused `<prefix><n>`).
- When an auto-deleted track's id is reused later, that is OK — Clip objects reference tracks by id, and at the moment a track is empty there are no clips referencing it. Re-creation cannot dangle references.
- Existing operations on Track identity (cross-track drag, mute/lock/hide, track selection, batch ops) all operate by id. Stable id is the only identity contract.
- The GUI renders tracks in the existing `KIND_RANK` order (Subtitle → Video → Audio). After auto-delete, the remaining tracks keep their kind bucket; after auto-add, the new track lands at the end of its kind bucket (lowest unused n in that bucket). Visual order is stable.

### 0.6 Publishing model split — locked decision

The Core `Project.publishing` and the future `Timeline.publish_metadata` are **separate concepts** with **different scopes**:

| Field | Lives on | Edited by | Inherits on Duplicate Timeline |
|---|---|---|---|
| `Project.publishing` | `Project` | Export package consumer; legacy fallback default | Not inherited (project-level) |
| `Timeline.publish_metadata` | `Timeline` | Inspector "发布" tab; per-Timeline copy of user-entered cover/title/body/tags/platform_overrides | **Independent** (each Timeline owns its own) |

Migration: existing `Project.publishing` becomes the **fallback default** for any new Timeline on first read. After the migration, any save to `Timeline.publish_metadata` is independent of `Project.publishing`.

**Cover MUST be a typed `CoverRef`, not an arbitrary dict.** Per the user correction: "do not leave cover as an unconstrained arbitrary dict if a minimal typed `CoverRef` can express the current semantics. At minimum distinguish asset identity + timeline frame/source."

Concretely (locked shape, used by W-E1):

```python
class CoverRef(BaseModel):
    """A typed reference to a Timeline cover image. Either an
    asset-derived cover (a still image from a clip) or an external
    URL. The CoverRef is owned by the Timeline (per-version cover).
    """
    source_kind: Literal["asset_clip", "external_url"]
    # For source_kind == "asset_clip":
    clip_id: Optional[str] = None           # which clip is the cover from
    timeline_frame: Optional[int] = None    # integer TimelineFrame within the clip
    # For source_kind == "external_url":
    external_url: Optional[str] = None
    # future: x/y/scale/transform for cover composition
```

W-E1 adds `Timeline.publish_metadata.cover: CoverRef | None` (default `None`). Migration: existing `Project.publishing.cover = {}` is read as "no cover" (empty CoverRef). The Inspector Cover picker uses `clip_id + timeline_frame` for asset-derived covers and `external_url` for uploads.

### 0.7 Existing invariants — preserved

These are unchanged from 03R3-1E / 03R3-2 and are pinned in the audit §11. Every batch must not regress them:
- 1 px = 1 frame at default zoom; preview 1:1 with pointer.
- One authoritative snap per pointerup; snap-creates-overlap → abort.
- No same-track overlap ever commits; `[0, max_timeline_frame]` server clamp.
- Frame-native edit chain (TimelineFrame / ClipFrame / SourceFrame distinct).
- No GUI TimeMap business math; `roundHalfAwayFromZero` is the only edit-coordinate rounding primitive.
- Every mutation is gated (sessionId + baseRevision); Mutation Gate contract is pinned.

---

## 1. Implementation batches (in order)

Each batch ends with: `pytest` clean, `vitest` clean, `tsc` clean, Sanlihe scenario subset green, `commit + push` + `SESSION.md` updated.

| Batch | Title | Layer | Touches | Why this order |
|---|---|---|---|---|
| **W-A** | Keyboard bugs (Spacebar + Delete) | GUI + tiny Core keymap tweak | `App.tsx`, `PreviewPlayer.tsx`, `keyboard.py`, vitest | Smallest possible change; fixes real bugs the audit confirmed. Closes the user-reported "Spacebar must play/pause" complaint. |
| **W-B** | Track auto-create / auto-delete | Core + thin API | `commands.py`, `manifest.py` (no field add), `app.py`, pytest | Architectural foundation: makes Timeline canonical-state clean before any UI affordance assumes it. |
| **W-C** | Track auto-create visual feedback in drag/drop | GUI | `Timeline.tsx`, `ClipBlock.tsx`, `App.tsx`, vitest | Uses W-B. Shows the user "这里会创建新轨道" before the drop commits. |
| **W-D** | Track semantic icons + resizable header column | GUI | `Timeline.tsx`, `styles.css`, `App.tsx`, vitest | Independent of W-B/W-C. The header is the user's primary interaction surface with tracks. |
| **W-E** | Timeline-level publish metadata model + Inspector panel | Core + GUI | `manifest.py` (field add), `commands.py`, `app.py`, `api.ts`, `App.tsx`, pytest + vitest | Independent of W-B/W-C/W-D. Closes the audit §8 gap. Largest single batch — split into W-E1 (Core + migration + tests) and W-E2 (GUI panel). |
| **W-F** | Marquee multi-select on empty timeline area | GUI | `Timeline.tsx`, `App.tsx`, vitest | Independent. Closes the audit §2 gap. |
| **W-G** | Gap operations: Close Gap / Batch Close Gaps / multi-Ripple | Core + GUI | `commands.py`, `app.py`, `api.ts`, `App.tsx`, pytest + vitest | Independent. Closes the audit §6 gap. Larger batch — split into W-G1 (Core + tests) and W-G2 (GUI). |
| **W-H** | Output Canvas explicit dimensions + ResizeObserver + playhead-in-canvas | GUI | `PreviewPlayer.tsx`, `styles.css`, vitest | Independent. Closes the audit §5 gap. |
| **W-I** | Draggable preview-progress thumb + hover tooltip | GUI | `PreviewPlayer.tsx`, `styles.css`, vitest | Independent. Closes the audit §5 P1 gap. |
| **W-J** | Sanlihe acceptance run end-to-end (consolidated smoke) | Test | `gui/smoke/03r3-sanlihe.mjs`, browser | Refresh the smoke to cover W-A through W-I. |

Batches ship one at a time. Each batch is reviewed against §0 invariants before merge.

---

## 2. Batch 03R3-W-A — Keyboard bugs (Spacebar + Delete) + selection-level mutation path

**Scope.** Fix the two real bugs the audit identified. Add the `delete_selection` server endpoint so the GUI can reach the existing Core `commands.delete_selection` command (no GUI loop). Add regression tests so the bugs cannot return.

### 2.1 Files

| File | Change | Why |
|---|---|---|
| `yroll/server/app.py` | Add `POST /selection/delete` endpoint. Body: `{clip_ids: list[str], ripple: bool, why: str, timeline_id?: str}`. Wraps `cmd.delete_selection(Selection.many(clip_ids), ripple, why, timeline_id)`. Returns `{deleted: list[str], ripple: bool}`. | The Core command exists (`commands.py:1211`) but is unreachable. The endpoint is the only Core change in W-A. |
| `gui/src/api.ts` | Add `deleteSelection(clipIds: string[], ripple: boolean, why: string, timelineId?: string)` → `POST /selection/delete`. | GUI client for the new endpoint. |
| `App.tsx` | Lift `playing` state. Pass `playing` + `onTogglePlay` props to `<PreviewPlayer>`. Wire `Spacebar` (and `K` via keymap) to `onTogglePlay()` directly. Remove the dead `transportRef` ref. | `transportRef.current?.toggle?.()` is a dead call because the ref is never assigned (App.tsx:358). |
| `App.tsx` | Split the keyboard dispatch at the `delete_selection` branch (was wrongly merged with `_nudge_playhead_boundary`): `delete_selection` is its own branch; it reads `binding.params.ripple` and dispatches based on selection size (see §2.1.1 below). | The audit confirmed `delete_selection` and `_nudge_playhead_boundary` are wrongly merged. |
| `App.tsx` (batch panel) | The existing "全部删除" button loops `for (const id of selectedSet) await api.removeClip(...)`. Replace with one call: `await api.deleteSelection([...selectedSet], ripple=false)`. Add a new "Ripple 删除" button next to it that calls `api.deleteSelection([...selectedSet], ripple=true)`. | Per the user correction: GUI MUST NOT loop Core mutations for multi-selection. One user intent = one Core Operation. |
| `PreviewPlayer.tsx` | Accept `playing: boolean` and `onTogglePlay: () => void` as props. Toolbar Play/Pause label uses them. The internal FrameClock is **still** the source of truth for the RAF loop, currentFrame, audio sync, and the `onPlayhead` emit; the props just expose `playing` and the toggle handler to the parent so Spacebar can reach it. | Don't break the existing FrameClock architecture. |
| `keyboard.py` | Add `_nudge_playhead_boundary` binding for ArrowUp/ArrowDown with `params.direction = -1 / +1`. | Currently ArrowUp/Down falls through silently. The keymap should describe them. |
| `gui/src/keyboard.test.ts` | Add tests: (a) Spacebar binding has `mutation_op="_toggle_play"` (local action, no Core op); (b) Delete has `mutation_op="delete_selection"` and `params.ripple=false`; (c) Shift+Delete has `params.ripple=true`; (d) ArrowUp/Down resolve to `_nudge_playhead_boundary`. | Pin the contract. |
| `gui/src/components/App.keyboard.test.tsx` (new) | Vitest test that simulates `keydown` events for Space, K, Delete, Shift+Delete (multi + single), ArrowUp, ArrowDown. Asserts: `onTogglePlay` is called for Space; `api.deleteSelection` (NOT `api.removeClip`) is called with the full id list and the correct ripple flag for Delete + Shift+Delete. Asserts the existing wrong merge is gone (ArrowUp/Down no longer routes to delete). | Pin the GUI behavior. |
| `gui/src/components/App.batch.test.tsx` (new) | Vitest test that asserts the batch panel "全部删除" calls `api.deleteSelection` once with all ids (NOT a loop of removeClip). | Pin the multi-clip batch path. |
| `tests/test_selection_delete.py` (new) | Pytest: single-clip, multi-clip, ripple vs preserve-gap, empty selection raises. Each scenario asserts ONE Operation recorded. | Pin the server contract. |

#### 2.1.1 Keyboard Delete dispatch rules (locked)

| Selection | Delete | Shift+Delete |
|---|---|---|
| `selectedSet.size === 0`, no `clip` | no-op | no-op |
| `selectedSet.size === 1` (or `selected` non-null, `selectedSet` empty) | existing pendingDelete impact-preview flow (one Core op, with impact UX) | `api.deleteSelection([clip.clip_id], ripple=true)` |
| `selectedSet.size > 1` | `window.confirm("Delete ${N} clips?")` → `api.deleteSelection([...selectedSet], ripple=false)` | `window.confirm("Ripple-delete ${N} clips?")` → `api.deleteSelection([...selectedSet], ripple=true)` |

Single-clip Delete keeps the existing impact-preview UX — that's already one Core Operation per user intent and is not part of the loop problem.

#### 2.1.2 Space/K is GUI-local, not a fake Core mutation

Per the user correction: "Space/K playback is a GUI-local transport action. Keymap should describe it as a local action (toggle_play / transport), not as a fake Core mutation. No `/keyboard/execute`."

The Core keymap already names these `_toggle_play` with empty params — there is no Core `cmd.toggle_play` and we will not create one. The GUI's keydown handler recognises the local-action semantics and routes to the lifted `onTogglePlay` callback. We do NOT add a `/keyboard/execute` endpoint.

### 2.2 Invariants protected

- FrameClock remains authoritative for playback time (PreviewPlayer still owns the RAF loop, currentFrame, audio sync).
- One user intent = one Core Operation, even for multi-clip actions.
- Mutation Gate is preserved (every deletion flows through `mutate()` → sessionId + baseRevision).
- Track structure unchanged by this batch (no auto-delete yet — that is W-B).
- Keymap is the source of truth for Delete / Shift+Delete semantics.

### 2.3 Known gaps after this batch

- ArrowUp/Down binding is added to the keymap, but the GUI's `jumpBoundary` math is unchanged (visually: playhead still jumps to the next/prev clip boundary). **No visual change.**
- Single-clip Inspector "Ripple" button stays on `api.removeClip(id, ..., true)` — it already routes to one Core Operation, so swapping to `deleteSelection([id], true)` would be cosmetic, not behavioral. Left for a follow-up.
- Marquee selection still not implemented (deferred to W-F).
- Track auto-add/auto-delete not implemented (deferred to W-B).

### 2.4 Acceptance

| Check | Pass condition |
|---|---|
| `pytest tests/test_selection_delete.py` | All new tests pass; single-op-per-call invariant pinned. |
| `pytest` | Full suite still passes (601 + 2 skipped, plus new). |
| `vitest run gui/src/keyboard.test.ts` | All new + existing tests pass. |
| `vitest run gui/src/components/App.keyboard.test.tsx` | New file passes; Spacebar + Delete + Shift+Delete + ArrowUp/Down behaviors are pinned. |
| `vitest run gui/src/components/App.batch.test.tsx` | New file passes; multi-delete uses deleteSelection, not a loop. |
| `tsc` | Clean. |
| Sanlihe smoke (existing) | 11/11 still green. |
| Manual | Open Sanlihe, press Space → playback toggles. Select clip, press Delete → impact dialog. Press Shift+Delete → ripple. Select 3 clips, press Shift+Delete → confirm dialog → all 3 removed + ripple. Press ArrowUp/Down → playhead jumps to boundary. |

---

## 3. Batch 03R3-W-B — Track auto-create / auto-delete (Core layer)

**Scope.** Add Core-level support for:
- `ensure_track_for_drop(asset_type, drop_x=None, drop_y=None, prefer_kind=None, timeline_id)` — for future UI integration in W-C. Today's UI calls `add_clip` / `add_image_clip` with `track_id=None`, which already invokes `allocate_track_for`. **W-B1** adds a thin wrapper that ALSO accepts (x, y) and (drop position below existing tracks) and creates tracks as needed. **The UI in W-C will use this.**
- Auto-cleanup: after `remove_clip`, `move_clip`, `ripple_delete_clip`, run `_cleanup_empty_tracks(tl)` and record the cleanup in the same Operation.
- `delete_track` (Core command): explicit remove. Not used by the UI today, but exists for tests + future Delete-Track button. Idempotent: removing a non-existent track is a no-op (vs error).

### 3.1 Files

| File | Change |
|---|---|
| `yroll/core/manifest.py` | No field add. Add a comment on `class Track` documenting the "no empty tracks" + "ids are stable across auto-delete" invariants. |
| `yroll/core/commands.py` | Add `delete_track(track_id, timeline_id)` — Core command. Add `ensure_track_for_drop(asset_type_value, prefer_kind=None, insert_after_track_id=None, timeline_id=None)` — accepts **structural intent only**, no GUI pixels. Add `_cleanup_empty_tracks(tl, except_track_ids=[])` private helper. Wire cleanup into the `after` of `remove_clip`, `move_clip`, `ripple_delete_clip`, `delete_selection`, `move_selection`. |
| `yroll/server/app.py` | Add `POST /tracks/delete` endpoint that calls `cmd.delete_track`. Add `POST /tracks/ensure_for_drop` endpoint that calls `cmd.ensure_track_for_drop`. |
| `tests/test_track_auto_delete.py` (new) | 12+ tests covering: (1) `remove_clip` removes empty track; (2) `move_clip` to another track removes empty source; (3) `ripple_delete_clip` removes empty track; (4) `delete_track` removes empty track; (5) `delete_track` on non-empty track raises; (6) `delete_track` on unknown id is a no-op (not error); (7) `_cleanup_empty_tracks` is called after a multi-step delete; (8) batch delete of last clips from 3 tracks removes all 3; (9) clip cross-track move doesn't remove track if other clips remain; (10) `ensure_track_for_drop` creates kind-correct track when no tracks exist; (11) `ensure_track_for_drop` creates vN for a video drop on empty Timeline; (12) `ensure_track_for_drop` is idempotent. |
| `tests/test_no_orphan_empty_tracks.py` (new, static guard) | A test that loads `projects/sanlihe-slice-30s/` (or a generated fixture) and asserts `for t in tl.tracks: len(t.clip_ids) >= 1`. Acts as a global invariant guard. |
| `tests/test_track_id_stability.py` (new) | Asserts: V1/V2/V3 → delete last clip on V2 → remaining tracks are V1 and V3 (NOT V1 and V2). Cross-track move that empties V2 leaves V1/V3. After V2 disappears, next new visual track allocates V2 again (lowest unused), but V1/V3 never rename. |

### 3.2 Design — auto-delete semantics

```
remove_clip(clip_id, ...):
    before = clip + track membership
    track.remove(clip_id)
    del project.clips[clip_id]
    removed_tracks = _cleanup_empty_tracks(tl)
    after = clip_gone + removed_tracks
    record("remove_clip", clip_id, before, after, ...)

move_clip(clip_id, new_frame, new_track_id, ...):
    before = clip + track membership
    ... existing move logic ...
    removed_tracks = _cleanup_empty_tracks(tl)
    after = new position + removed_tracks
    record("move", clip_id, before, after, ...)

delete_selection(selection, ripple, ...):
    ... existing per-clip removal logic ...
    if ripple:
        ... existing per-track shift logic ...
    removed_tracks = _cleanup_empty_tracks(tl)
    after = {deleted + ripple_shifts + removed_tracks}
    record("delete_selection", ..., after, ...)
```

`_cleanup_empty_tracks(tl, except_track_ids=[])` returns the list of removed track ids and removes them from `tl.tracks`. Returns `[]` if nothing changed.

**`_cleanup_empty_tracks` never renames a remaining track.** It only removes entries whose `clip_ids` is empty. The surviving tracks keep their existing ids. A future `_next_track_id_for_kind` allocation may reuse the freed id (lowest-unused wins), but that is a NEW track creation, not a rename.

### 3.3 Design — ensure_track_for_drop semantics (Core layer)

```
ensure_track_for_drop(
    asset_type_value: str,
    prefer_kind: TrackKind | None = None,
    insert_after_track_id: str | None = None,
    timeline_id: str | None = None,
) -> Track:
    """Resolve or create a track for a drop.

    No pixel coordinates are accepted. The caller (GUI) has already
    resolved the pointer geometry into semantic intent:
      - target_track_id (drop on existing track)        → pass nothing
      - create_new_track (drop in gap)                  → pass insert_after_track_id
      - kind (asset type drives kind when not specified)

    Returns a Track that the caller can place the new Clip on.
    """
    tl = _timeline(timeline_id)
    allowed_kinds = ASSET_TYPE_TO_TRACK_KINDS.get(asset_type_value)
    if not allowed_kinds:
        raise CommandError(...)
    if insert_after_track_id is not None:
        # Explicit "create new track after this one". Honors kind
        # policy: new track's kind is in allowed_kinds.
        anchor = next((t for t in tl.tracks if t.track_id == insert_after_track_id), None)
        kind_enum = prefer_kind or (
            TrackKind(anchor.kind.value) if anchor and anchor.kind.value in allowed_kinds
            else TrackKind(list(allowed_kinds)[0]))
        return self.add_track(kind_enum, timeline_id=timeline_id)
    # Default: existing allocator (find non-overlapping or create).
    return self.allocate_track_for(asset_type_value, tl_start=0, tl_end=0,
                                  prefer_track_id=None, timeline_id=timeline_id)
```

The Core wrapper takes only structural intent. The GUI is responsible for hit-testing the rendered track rows and producing the right combo of `target_track_id | insert_after_track_id | kind`. **No `drop_y_position`, `drop_x_position`, `clientX`, `clientY`, or any DOM-derived value ever crosses this boundary.**

### 3.4 Invariants protected

- Every `tl.tracks` entry has `len(clip_ids) >= 1`. Pinned by static guard.
- **Track ids are stable across auto-delete.** V1/V2/V3 → V2 becomes empty and is removed → remaining ids are still V1 and V3. Re-allocated ids (e.g., V2 again later) are NEW track creations, not renames. Pinned by `tests/test_track_id_stability.py`.
- Track order in `tl.tracks` is the order of creation (existing behavior); GUI applies `KIND_RANK` for display.
- No new Operation type introduced — `remove_clip`, `move`, `ripple_delete`, `delete_selection` "after" payloads gain a `removed_tracks: list[str]` field. Backwards-compatible (callers ignoring the field still work).
- `delete_track` is idempotent (no-op on unknown id); empty tracks can't have unknown ids because the invariant prevents them, but the no-op protects against double-cleanup races.
- Core never sees GUI pixel coordinates; the structural intent API surface is closed under "what a Core owner would write".

### 3.5 Known gaps after this batch

- GUI doesn't yet call `ensure_track_for_drop` from the drop handler — that's W-C.
- Batch operation across multiple tracks (e.g., delete all clips on 3 tracks → remove 3 tracks) reaches Core via one `delete_selection(Selection.many(...), ripple=...)` call (per §0.3.1) — NOT a GUI loop. The cleanup happens inside Core once.
- Drop ONTO a vertical gap between two existing tracks is not yet distinguished; for v0.1 the drop targets whichever track the pointer is over (existing behavior). **Defer to W-C.1 follow-up.**

### 3.6 Acceptance

| Check | Pass condition |
|---|---|
| `pytest tests/test_track_auto_delete.py` | All 12+ tests pass. |
| `pytest tests/test_track_id_stability.py` | All id-stability tests pass. |
| `pytest tests/test_no_orphan_empty_tracks.py` | Static guard passes on Sanlihe. |
| `pytest` | All existing tests still pass (601 + 2 skipped, plus new). |
| `vitest` | No GUI changes in this batch; unchanged. |
| `tsc` | Clean. |
| Manual | Open a project; remove all clips from V1 → V1 disappears. Move last clip from V1 to V2 → V1 disappears. Confirm V2 is now V1/V2 (NOT V1/V2-renamed-from-V2). Drop an image with the new endpoint onto a Timeline with V1+V2 → a new V3 is created at the end. |

---

## 4. Batch 03R3-W-C — Drop visual feedback + integrate `ensure_track_for_drop`

**Scope.** Connect the GUI drop handler to the new Core capability, and add the visual "这里会创建新轨道" affordance.

### 4.1 Files

| File | Change |
|---|---|
| `gui/src/components/Timeline.tsx` | `track-content` `onDragOver` resolves the y-position against the rendered track rows. If the pointer y is below the last track-row, set a `data-drop-zone="below-tracks"` on the next-to-last row, which renders a 2px dashed line at the bottom edge as the drop preview. |
| `gui/src/App.tsx` | `onAssetDrop` switches to a new path: compute the resolved track id (existing drop on track → explicit; drop below all tracks → `api.ensureTrackForDrop(asset_type, prefer_kind=...)` then `api.addImageClip(...)` on that track). The drop preview shows "新轨道" badge inside the dashed line. |
| `gui/src/api.ts` | `ensureTrackForDrop(assetType, preferKind)` → `POST /tracks/ensure_for_drop`. |
| `gui/src/styles.css` | `.drop-zone-below` — 2px dashed line at the bottom of the last track-row; `.drop-zone-badge` — small label "新轨道 ▶". |
| `gui/src/components/Timeline.drop.test.ts` (new) | Vitest test for the drop-zone visual preview logic (DOM-level). |

### 4.2 Invariants protected

- Existing drop-on-existing-track path is unchanged (uses explicit `track_id`, Core's allocator validates overlap).
- New drop-below-tracks path uses `ensureTrackForDrop` which is idempotent and respects kind ordering.

### 4.3 Known gaps after this batch

- Drag-and-drop onto a vertical gap BETWEEN two existing tracks (e.g., between V1 and V2) is not yet distinguished — the drop currently goes to whichever row the pointer is over. **Defer to W-C.1 or a follow-up batch.**
- Marquee selection still not implemented (W-F).

### 4.4 Acceptance

| Check | Pass condition |
|---|---|
| `vitest run gui/src/components/Timeline.drop.test.ts` | New tests pass. |
| `pytest` | New `test_ensure_track_for_drop.py` (or extension to `test_track_auto_delete.py`) covers the API path. |
| Manual | Drag asset onto Sanlihe empty area below the last track → dashed line + "新轨道" badge → drop creates V3 with the clip on it. |

---

## 5. Batch 03R3-W-D — Track semantic icons + resizable header column

**Scope.** Per audit §3 + user feedback. Independent of W-B/W-C.

### 5.1 Files

| File | Change |
|---|---|
| `gui/src/components/Timeline.tsx` | Replace `TRACK_ROLE` text labels with semantic icons (T / ▶ / ♪). Replace emoji state buttons with compact icons. Drop the `track.kind !== "text"` guard on mute (show mute on all tracks). |
| `gui/src/styles.css` | Track kind icon: monospace 14px colored chip. State icons: thin SVGs or Unicode glyphs. Hover-reveal at 30% default opacity; full opacity on `:hover`/`:focus-within`/`.active`. |
| `gui/src/App.tsx` | Track header column width becomes `headerW` state, initialized from `localStorage["yroll.headerWidth"]` (default 96px). Wire a `<ResizeHandle>` variant on the right edge of `.timeline-headers`. Save to localStorage on drag. |
| `gui/src/components/Timeline.test.tsx` (new) | Vitest snapshot test for header layout at multiple widths. |

### 5.2 Invariants protected

- Track kind icon does not change the `track.kind` value — purely visual.
- Resizing the header does NOT change the timeline-content's coord space origin (still `frame 0 = x=0` inside `.timeline-content`). The header column is OUTSIDE coord space (per 03R2 P0-A).

### 5.3 Acceptance

- Visual inspection: header shows T/▶/♪ + id, mute/lock/hide at 30% opacity, full opacity on hover.
- Header column is drag-resizable 80-300 px; width persists across reload.
- Existing Sanlihe smoke still 11/11 (no functional change).

---

## 6. Batch 03R3-W-E — Timeline-level publish metadata + Inspector panel

**Scope.** Two sub-batches:
- **W-E1**: Core model + migration + tests. Adds `Timeline.publish_metadata`. Duplicate Timeline becomes truly independent. Export panel reads from Timeline.
- **W-E2**: Inspector "发布" tab with Cover / Title / Body / Tags inputs.

### 6.1 W-E1 — Core changes

| File | Change |
|---|---|
| `yroll/core/manifest.py` | Add `class TimelinePublishMetadata(BaseModel)`: `cover: dict[str, Any] = {}`, `title: str = ""`, `body: str = ""`, `tags: list[str] = []`, `platform_overrides: dict[str, dict[str, str]] = {}`. Add `Timeline.publish_metadata: TimelinePublishMetadata = TimelinePublishMetadata()`. |
| `yroll/core/commands.py` | New `set_publish_metadata(timeline_id, field, value, why)` command. Single-field granularity = single revision bump per save. `duplicate_timeline` carries forward `publish_metadata` (deep copy) — duplicate has independent metadata from the source. |
| `yroll/server/app.py` | `POST /timelines/{tid}/publish_metadata` → `cmd.set_publish_metadata(tid, field, value, why)`. Body validation: `field` in `{"cover", "title", "body", "tags", "platform_overrides"}`. |
| Migration on read (Core side) | Existing projects without `Timeline.publish_metadata` get `TimelinePublishMetadata()` on load. The legacy `Project.publishing` stays as the fallback default — when a Timeline's `publish_metadata.title == ""`, the Export panel falls back to `project.publishing.title`. |
| `tests/test_publish_metadata.py` (new) | 8+ tests: (1) Timeline default is empty; (2) `set_publish_metadata(title)` updates one Timeline; (3) Other Timelines unchanged; (4) Duplicate Timeline gets a DEEP-COPY of source's publish_metadata; (5) Editing duplicate's title does NOT affect source; (6) Migration: legacy project without `publish_metadata` field loads with empty defaults; (7) Setter rejects unknown field names; (8) Setter per-field granularity = one revision bump per call. |
| `tests/test_duplicate_timeline.py` | Update existing test to assert `publish_metadata` independence. |

### 6.2 W-E2 — GUI changes

| File | Change |
|---|---|
| `gui/src/api.ts` | `setPublishMetadata(timelineId, field, value, why)` → `POST /timelines/{tid}/publish_metadata`. |
| `gui/src/api.ts` | Update `Project` type to include `Timeline.publish_metadata` field. |
| `gui/src/App.tsx` | Inspector tabs: add `发布` next to `属性` / `历史`. When clicked, render a panel with Cover (asset picker + start-frame readout), Title (text), Body (textarea), Tags (comma-separated). On save → `api.setPublishMetadata(...)` then `refresh()`. |
| `gui/src/components/ExportPanel.tsx` | Read `timeline.publish_metadata` instead of `project.publishing` (fallback to `project.publishing` when Timeline field is empty). |
| `gui/src/components/Inspector.publish.test.tsx` (new) | Vitest test: tab switch, edit title, save, verify api call. |

### 6.3 Invariants protected

- `Project.publishing` continues to exist as the legacy / fallback layer.
- The MCP / Agent path uses the same Core command, so Agent edits go through the same gate.
- Duplicate Timeline stays atomic — `publish_metadata` is part of the duplicate payload, not a post-step.

### 6.4 Known gaps after this batch

- Platform overrides UI not implemented (data model supports it; UI deferred).
- Cover frame scrubbing not implemented (v0.1 picks clip's start frame).
- Auto-generation of cover (e.g., "pick middle frame") not implemented.

### 6.5 Acceptance

- pytest + vitest clean.
- Manual: Inspector → 发布 tab → edit Title → save → Export panel shows the new title. Duplicate Timeline → edit duplicate's title → source unchanged.

---

## 7. Batch 03R3-W-F — Marquee multi-select on empty timeline area

**Scope.** Per audit §2 + user feedback.

### 7.1 Files

| File | Change |
|---|---|
| `gui/src/components/Timeline.tsx` | `track-content` `onPointerDown` distinguishes: target is `.clip` → existing selection+drag. Target is empty track area → enter marquee mode. Draw a translucent rectangle following pointermove. On `pointerup`, compute the set of clips whose bbox intersects the rectangle; replace or extend `selectedSet` based on `ctrl` modifier. Esc cancels. |
| `gui/src/styles.css` | `.marquee-rect` — 1px dashed brand-color border, faint background. |
| `gui/src/components/Timeline.marquee.test.tsx` (new) | Vitest test: pointerdown on empty area → move → up → `selectedSet` updated. Ctrl held → additive. Esc → cleared. |

### 7.2 Invariants protected

- Existing click / Ctrl+click / Ctrl+A selection paths unchanged.
- Marquee rect z-index above clip outlines, below playhead.

### 7.3 Acceptance

- Manual: drag on empty track area → translucent rect → multi-select. Ctrl+drag → add to selection. Esc → clear.

---

## 8. Batch 03R3-W-G — Gap operations (Close Gap / Batch Close Gaps / multi-Ripple)

**Scope.** Per audit §6 + user feedback.

### 8.1 W-G1 — Core

| File | Change |
|---|---|
| `yroll/core/commands.py` | `close_gap(timeline_id, track_id, start_frame, end_frame)`: shift all clips on the track with `timeline_range.start >= end_frame` LEFT by `(end_frame - start_frame)`. Atomic; emits one Operation. `close_gaps_batch(timeline_id, track_ids, why)`: for each track, find all empty ranges between clips, close them. Returns one Operation per track. **Multi-Ripple stays as one Core `delete_selection(..., ripple=true)` Operation, NOT a GUI loop of `removeClip`.** |
| `yroll/server/app.py` | `POST /tracks/{track_id}/close_gap` and `POST /tracks/close_gaps_batch`. |
| `tests/test_gap_operations.py` (new) | 6+ tests covering each variant + empty Project case. |

### 8.2 W-G2 — GUI

| File | Change |
|---|---|
| `gui/src/api.ts` | `closeGap(trackId, startFrame, endFrame)`, `closeGapsBatch(trackIds)`. |
| `gui/src/App.tsx` | Multi-select batch panel: add "Ripple 删除" button next to "全部删除" — calls `api.deleteSelection([...selectedSet], ripple=true)` (already wired in W-A.3, no change here beyond the button). Add "Batch Close Gaps" button (only enabled if `selectedSet.size >= 1`). Confirm dialog for Batch Close Gaps showing "N gaps / M frames to close". |
| `gui/src/components/Timeline.tsx` | Right-click context menu on empty track area: "Close gaps here" (computes the empty range at click point, calls close_gap). |
| `gui/src/components/Timeline.gapops.test.tsx` (new) | Vitest test: confirm dialog copy, multi-ripple call. |

### 8.3 Invariants protected

- Close Gap is atomic per-track; Batch is per-track with a single Operation per track.
- Multi-Ripple is **one Core `delete_selection(..., ripple=true)` Operation**, NOT a GUI loop. This was locked in W-A.3 (the multi-select batch panel's "Ripple 删除" already routes through `api.deleteSelection`).
- Close Gap is distinct from Ripple Delete: Close Gap closes an empty range (no clip removed); Ripple Delete removes a clip and shifts later clips left to close the gap it would leave. They share the "shift left" primitive but have different user intents.
- Auto-cleanup of empty tracks after Close Gap runs through the same `_cleanup_empty_tracks` helper as W-B (defer if Close Gap cannot produce empty tracks; verify in tests).

### 8.4 Known gaps after this batch

- Close Gap across multiple selected tracks in one UI call: deferred (W-G.1 follow-up).
- Undo/Redo of Close Gap already works (uses the standard Operation revert path).

---

## 9. Batch 03R3-W-H — Output Canvas explicit dimensions + ResizeObserver

**Scope.** Per audit §5 + user feedback.

### 9.1 Files

| File | Change |
|---|---|
| `gui/src/components/PreviewPlayer.tsx` | Replace `frameStyle`'s `aspectRatio + maxWidth/maxHeight` with explicit `width`/`height` from a `ResizeObserver` on `.preview-stage`. Inner-dimension rule: longest side = min(stageWidth, stageHeight × aspectRatio); other side = longestSide / aspectRatio. Recompute on `aspect` change or stage resize. |
| `gui/src/components/PreviewPlayer.tsx` | Add aspect dropdown tooltips: "横屏（YouTube / B站）", "竖屏（抖音 / 快手）", "方形（小红书 / 朋友圈）", "传统电视", "竖版传统". |
| `gui/src/components/PreviewPlayer.tsx` | Playhead-in-canvas marker: 1px vertical line at `(playheadFrame / endFrame) × canvasWidth`, color `#ff5050`, hidden when `mode === "instant"` and user is dragging a clip elsewhere (defer — for v0.1 just always show). |
| `gui/src/components/PreviewPlayer.canvas.test.tsx` (new) | Vitest test: ResizeObserver fires → canvas width tracks within ±2px. Aspect switch updates canvas dims. |

### 9.2 Invariants protected

- TimelineFrame remains the time authority; aspect switch does NOT change `playheadFrame` or `clockRef.current.startFrame`.
- Composite layer iteration is `playheadFrame`-driven.

### 9.3 Acceptance

- Manual: switch aspect → canvas visibly resizes. Resize inspector pane → canvas resizes. Playhead marker visible inside canvas.

---

## 10. Batch 03R3-W-I — Draggable preview-progress thumb + hover tooltip

**Scope.** Per audit §5 P1.

### 10.1 Files

| File | Change |
|---|---|
| `gui/src/components/PreviewPlayer.tsx` | `.preview-progress` thumb: `pointer-events: auto` on the thumb, drag-to-seek. Bar (not thumb): hover tooltip with frame number. |
| `gui/src/styles.css` | `.preview-progress` bar: `pointer-events: auto` for hover; thumb inherits. Tooltip: small `<div>` with frame count, fade in/out. |
| `gui/src/components/PreviewPlayer.progress.test.tsx` (new) | Vitest test: pointerdown on thumb → drag → `onPlayhead` called with correct frame. |

### 10.2 Acceptance

- Manual: drag thumb → playhead scrubs. Hover bar → tooltip with frame.

---

## 11. Batch 03R3-W-J — Sanlihe acceptance consolidation

**Scope.** Refresh `gui/smoke/03r3-sanlihe.mjs` (currently 11/11) to cover W-A through W-I:

| New scenario | Asserts |
|---|---|
| `spacebar_playback_toggles` | Press Space → playhead advances; press Space again → stops. |
| `delete_key_removes_with_impact` | Select clip → press Delete → impact dialog → confirm → clip gone. |
| `shift_delete_ripples` | Select clip → press Shift+Delete → trail ripples left. |
| `arrow_keys_jump_boundary` | Press ArrowUp/Down → playhead jumps to next/prev clip boundary. |
| `drop_below_tracks_creates_v3` | Drag asset onto Sanlihe's empty area below last track → V3 created with clip. |
| `column_resize_persists` | Resize track header column → reload page → width preserved. |
| `marquee_multi_select` | Drag empty area → multi-select clips. |
| `multi_ripple_delete` | Select 3 clips → multi-Ripple → 3 trails ripple. |
| `batch_close_gaps` | Project with 2 gaps → Batch Close Gaps → gaps closed. |
| `publish_title_roundtrip` | Inspector 发布 tab → edit title → save → reload → title persists. |
| `canvas_resize_tracks_inspector` | Resize inspector pane → canvas width tracks within ±2px. |
| `progress_thumb_scrubs` | Drag thumb → playhead scrubs to corresponding frame. |

Acceptance: 12/12 PASS. Update SESSION.md with all W-A through W-J deliveries.

---

## 12. Test strategy per layer

| Layer | Test runner | Coverage pattern |
|---|---|---|
| Core (commands, manifest, model) | `pytest tests/` | Pure logic tests; no HTTP. Use `CommandLayer(core, who=Actor.HUMAN)` directly. |
| Server (FastAPI endpoints) | `pytest tests/` | `TestClient` + lease fixture. Pinned by `test_track_allocation_contract.py` and new `test_*_contract.py` files. |
| GUI logic (helpers, hooks, factories) | `vitest` | Per-file `*.test.ts` adjacent to source. `App.keyboard.test.tsx` is new and mounts a minimal App wrapper. |
| GUI components (DOM behavior) | `vitest` + `@testing-library/react` where helpful | `Timeline.drop.test.tsx`, `Timeline.marquee.test.tsx`, `Inspector.publish.test.tsx`, etc. |
| Browser smoke (real Sanlihe) | `node gui/smoke/03r3-sanlihe.mjs` via Playwright | Consolidated in W-J. |
| Static guards | `pytest tests/test_no_*.py` | `test_no_orphan_empty_tracks.py` (new), existing `test_no_js_round_in_edit.py`, `test_no_writes_outside_server.py`. |

---

## 13. Risk + rollback

- **W-B** is the highest-risk batch (Core mutation semantics). Mitigation: 12+ pytest tests, static guard, manual verification on Sanlihe before merge. Rollback: revert the single commit; no Project on-disk schema change because no field is added.
- **W-E1** adds a Core field. Migration on read handles old projects gracefully. Rollback: a downward migration in `commands.py` would drop the field on save — not needed for v0.1 because old readers just ignore the new field.
- **W-A** is purely GUI + 3 lines of keymap. Rollback: revert the commit.

No batch changes the on-disk JSON shape in a backwards-incompatible way.

---

## 14. Out of scope (still pinned)

Per audit + user instruction:
- Timeline-local Revision (03E-5, paused)
- nested Timelines
- Keyframes / Animation model
- advanced effects / transitions
- full `EditorSelection` redesign (marquee adds to Set, doesn't rebuild)
- new AI generation features
- cover frame scrubbing (v0.1 picks clip's start frame)
- cursor-anchor reticle during wheel zoom
- crop fit-mode (`objectFit: cover`)
- per-clip "moment cards"
- Track pinning (`pinned: bool` on Track) — deferred until a real use case emerges
- Drop ONTO vertical gap between two existing tracks (currently drops on the upper track) — deferred to W-C.1 follow-up
