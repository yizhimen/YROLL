# Semantic Link Behavior Contract

**Status:** FROZEN as of GUI-05 (2026-09-02). Future changes require explicit user approval.

This document locks the **current** behavior of "Semantic Link" in YROLL so that future
edits do not silently change semantics. It also clarifies that the GUI's
"时间重叠提示" checkbox is **NOT** a Semantic Link feature; it is a separate
timeline-range overlap heuristic.

---

## 1. Data model

Defined in `yroll/core/manifest.py`.

```python
class RelationStrength(str, Enum):
    STRONG       = "strong"        # auto-sync on move / ripple_delete
    MEDIUM       = "medium"        # prompt before destructive op
    WEAK         = "weak"          # visible in inspector, never auto-affects
    INDEPENDENT  = "independent"   # explicitly tagged "never propagate"


class Relationship(BaseModel):
    """语义关系图：与 Timeline 并列存放。"""
    relation_id: str
    source: str                # clip_id
    target: str                # clip_id
    relation: RelationStrength
    kind: str                  # caption_of / voice_of / bgm_of / sfx_of / ...
    confidence: float = 1.0
    scope: Optional[dict[str, TimeRange]] = None
    reason: str = ""
```

Storage: `Project.relationships: list[Relationship]` (`manifest.py:386`).
The list lives **next to** `Project.timeline` — they are siblings, not nested.

---

## 2. Producer

`yroll/core/links.py::infer_relationships(project)` (lines 35–97).

Deterministic, offline-capable rules (no LLM):

| Condition | kind | relation |
|---|---|---|
| TEXT clip's range overlaps a VIDEO clip's range by >50% | `caption_of` | `STRONG` |
| AUDIO clip's range covers exactly one VIDEO clip | `voice_of` | `STRONG` |
| AUDIO clip's range spans multiple VIDEO clips | `bgm_of` | `INDEPENDENT` |

**Idempotent.** Each call clears prior auto-inferred relations (those whose `reason` contains
`"自动推断"`) and appends the fresh ones. Human/AI-tagged relations are preserved.

---

## 3. Consumers (commands that READ the graph and act on it)

### 3.1 `commands.py::move_clip` (lines 1606–1685)

- Calls `infer_relationships(self.core.project)` before moving.
- For each `STRONG` partner of the primary clip whose range overlaps the **old** primary
  range, shifts the partner by the same `delta`.
- Records `before.cross_shifted` and `after.cross_shifted_count` on the `Operation`.

### 3.2 `commands.py::ripple_delete_clip` (lines 1064–1117)

- Calls `infer_relationships(self.core.project)` first.
- After deleting the primary, also shifts every `STRONG` partner whose range overlaps the
  deleted interval by `-dur`. Same-track followers are also collapsed to remove the gap.

### 3.3 `links.py::impact_preview` (lines 100–131)

- Read-only projection: returns `{will_sync, will_prompt, untouched}` for `op=remove` or
  generic `op`.
- GUI uses this in `App.tsx:826-833` / `:1887-1892` to show "将会同步影响谁" before a delete.

---

## 4. Explicit NON-consumers

These operations DO NOT consult `project.relationships`. Pinning this list prevents
future code from silently introducing Semantic Link propagation in unexpected places.

| Operation | Reads relationships? |
|---|---|
| `commands.py::move_clip` (single-clip drag) | **YES** — propagates STRONG (above) |
| `commands.py::move_selection` (multi-clip drag) | **NO** (see §4.1) |
| `commands.py::ripple_delete_clip` | **YES** — propagates STRONG (above) |
| `commands.py::delete_clip` (non-ripple single delete) | **NO** |
| `commands.py::delete_selection` (non-ripple) | **NO** |
| `commands.py::split_clip` | **NO** |
| `commands.py::trim_clip_frame` | **NO** |
| `commands.py::set_speed` | **NO** |
| `commands.py::set_volume` | **NO** |
| `commands.py::add_clip` | **NO** |
| `commands.py::add_track` | **NO** |
| `commands.py::delete_track` | **NO** |
| `commands.py::set_track_hidden` | **NO** |
| `commands.py::set_track_muted` | **NO** |
| `commands.py::set_track_locked` | **NO** |

### 4.1 The `move_clip` vs `move_selection` asymmetry — **frozen**

This is **intentional** and **frozen**. The plan that introduces this asymmetry is part of
the plan that locked this contract.

| Path | STRONG propagation? |
|---|---|
| `api.move(clipId, frame)` → `move_clip` | **YES** — co-shifts STRONG partners |
| GUI multi-select drag → `api.moveSelection(...)` → `move_selection` | **NO** — moves only the selection |

Why: single-clip drag is the user saying "move this thing"; multi-select drag is the user
saying "move these selected things as a group". The semantics of "group" override the
inferred "link" semantics. Future work (Linked Clips / Group Editing — see §6) would
re-introduce this — but **only after a user-approved model decision**.

This asymmetry is pinned by `tests/test_semantic_link_contract.py`:
- `test_move_clip_propagates_strong` (05-D.1)
- `test_move_selection_does_not_propagate` (05-D.2)
- `test_move_clip_source_pin` (05-D.5)
- `test_move_selection_source_pin` (05-D.6)

---

## 5. GUI surface

**The GUI does NOT render or act on `project.relationships` for any editing workflow.**

Verified by audit (`docs/GUI-05-POST-FOUNDATION-AUDIT.md`) and source-pinned by
`tests/test_gui_relationship_naming.py`:

| GUI feature | Reads `project.relationships`? |
|---|---|
| Timeline clip rendering (`Timeline.tsx`) | NO |
| ClipBlock drag/move | NO |
| Preview render | NO |
| Inspector (`App.tsx:1645-1967`) | NO |
| Subtitle Inspector (inline) | NO |
| Multi-select drag | NO |
| Marquee select | NO |
| Track hide/mute/lock | NO |
| Delete confirmation | NO (uses `links.impact_preview` only — see §3.3) |
| **`highlightRel` checkbox (renamed "时间重叠提示")** | **NO** — see §5.1 |

### 5.1 The "时间重叠提示" checkbox — NOT Semantic Link

The checkbox at `App.tsx:1229-1231` is labeled `"高亮关联"` with title
`"高亮所有跨轨关联的 clip（Semantic Link）"` historically. **This is a misleading label.**

The actual computation (`Timeline.tsx:1051-1056`) is purely:

```ts
isRelated = highlightRel && selectedIds.size > 0
  && Array.from(selectedIds).some((selId) => {
    const sel = project.clips[selId];
    if (!sel || sel.track_id === clip.track_id) return false;
    return clip.timeline_range.start < sel.timeline_range.end &&
           sel.timeline_range.start < clip.timeline_range.end;
  });
```

That is: **timeline-range overlap between the rendered clip and any selected clip, on a
different track**. It does not consult `project.relationships` at all. It is a visual
hint, not a relationship-graph query.

**Renamed in GUI-05-D (D13):**

| Before | After |
|---|---|
| Title: `"高亮所有跨轨关联的 clip（Semantic Link）"` | Title: `"高亮时间重叠的 clip"` |
| Label: `"高亮关联"` | Label: `"高亮时间重叠"` |

The rename makes the feature honest. Internal identifiers (`highlightRel`, `isRelated`)
are kept — they are accurate enough; renaming them is out of scope.

---

## 6. Intentionality — what this is NOT

Semantic Link in YROLL is **a designed inference graph**, not:

- **A user-creatable binding.** There is no "link these two clips" UI action today.
  Inferring it is automatic; editing it requires editing JSON or using AI proposals.
- **A "group" semantic on `Selection`.** The `Selection` dataclass
  (`yroll/core/selection.py:14-86`) lists `Linked` as a future mode in a comment, but no
  code path uses it. Pinned by
  `tests/test_gui_relationship_naming.py::test_selection_linked_mode_unused` (source-pin).
- **A preview-time filter.** Preview reads `clip.context`, not `project.relationships`.
- **A published export.** Publish metadata (not yet implemented) would be a separate model.

**Linked Clips / Group Editing is explicitly out of scope** of GUI-05. The plan keeps this
in the "future" bucket. If a future phase introduces user-creatable links, it will:

1. Define a new `Relationship.kind` value for user-created entries.
2. Add a UI to create/edit/delete them.
3. Decide which commands (today's list in §4) consume them — likely a strict subset.
4. Update this contract document with the new behavior.
5. Update or remove the §4.1 asymmetry if it makes sense in the new model.

---

## 7. Future changes

Any change to the contract above — adding a new consumer, removing an existing consumer,
or changing the §4.1 asymmetry — **must** be:

1. Approved by the user explicitly (not inferred).
2. Documented here with the change rationale.
3. Pinned by an updated `tests/test_semantic_link_contract.py`.

If a developer wants to make Semantic Link "real" (user-creatable, group-aware), they
must file a new plan and follow the approval flow above. This document is the gate.