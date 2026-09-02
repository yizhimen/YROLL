# GUI-04 Post-State Audit & Next-Phase Plan (READ-ONLY)

**Baseline:** HEAD `a970f6c` ([GUI-04 FINAL] Acceptance gate 23/23 + all browser smokes).
**Date:** 2026-09-02.
**Mandate:** read-only audit of post-GUI-04 state; bounded proposal for next phase. NO code changes in this pass.

---

## 0. One-line verdict

GUI-04 closes the **GUI-04 batch closure gate** (runtime-route integrity + frame contract + Undo/Redo exact + DragState consolidation + Preview-layer model + Inspector transform) and is fully tested at API + vitest + browser-smoke levels. The next-phase work has **two distinct shapes** and the user must pick:

- **(A) Cleanup & fix the two real defects that GUI-04 surfaced but did not address** — 1–2 sessions, mechanical, high ROI.
- **(B) Begin GUI-05**, the first batch where the user spec explicitly allows new capability.

These are not mutually exclusive, but they are different *kinds* of work and should be sequenced deliberately.

---

## 1. Repository state (snapshot)

| Item | Value | Notes |
|---|---|---|
| HEAD | `a970f6c` | GUI-04 FINAL acceptance |
| Branch | `main` | clean except 2 local pollution entries (see §2) |
| pytest | 835 pass + 1 skip + **5 fail** | was 838 pass + 1 skip + 2 pre-existing per SESSION §0 — **regression of 3 fixtures** |
| vitest | 465 pass + 2 skip | matches SESSION |
| `tsc` | 5 pre-existing errors in `Timeline.drag.test.ts` | unchanged |
| Backend live | `:8770` (clean Sanlihe, r275) | session human EDIT |
| Frontend live | `:5180` (vite dist + proxy) | last built from `827159a` per SESSION |
| Working tree | 2 modified files (not committed) | both are pollution, see §2 |

### 1.1 Local pollution (must NOT be committed)

```
M gui/src/drag-state.test.ts         ← LF/CRLF churn only (no semantic change)
M projects/sanlihe-slice-30s-clean/current.json   ← CANONICAL fixture MUTATED in place
```

The clean-fixture pollution is **the most important finding in this audit.** A working-copy helper (`serve-clean-sanlihe.mjs`) exists and the fixture carries a `CANONICAL_READONLY_DO_NOT_MUTATE` sentinel, but **at least one GUI-04 smoke wrote to the canonical path** (ca0eee0/c3ace4d moved from v1 → v9; c98b82a moved to v5; V3 hidden flipped true). This is exactly the regression class the sentinel was supposed to prevent. See §3.A.

---

## 2. GUI-01 → GUI-04 architectural evolution (what actually shipped)

### 2.1 Per-batch summary (cumulative regression at point of ship)

| Phase | What it locked | pytest | vitest | Browser smoke | Key invariant introduced |
|---|---|---|---|---|---|
| **GUI-01** | Mutation Gate wiring (sessionId + baseRevision injected on every mutation) | 317 | 16 | gui-01.mjs | `api.mutate()` is the only mutation surface; bare `fetch` for writes is forbidden by static guard |
| **GUI-01.5** | Cross-process authority: MCP becomes HTTP client of `yroll serve` | 345 | 16 | (in-process) | `mcp_server.py` cannot import `ProjectCore` (static guard); sole-write authority is `yroll serve` |
| **GUI-02** | Frame-native Timeline (P0-01..P0-08 P0 foundation) | 477 | 163 | gui-02.mjs | `roundHalfAwayFromZero` is the only edit-coordinate rounding; `pxPerFrame` instead of `pxPerSec` |
| **GUI-03 (A–E)** | Image-first media + dynamic track allocation + L1 composite + Multi-Timeline + Fork + Lease polish | 596→601 | 196→217 | 03r3-sanlihe | Image source_range = `(0, 1/seq_fps)`; tracks are derived (no orphans); `derived_from` lineage |
| **GUI-03R4 (R1–R7)** | NLE Editing Surface: multi-layer preview, frame invariant, marquee select, gap/ripple, output viewer | 683 | 217 | 03r4-acceptance (8/8) | Layer index globally unique; negative-start repair on load; hidden-track exclusion in `/preview/plan` |
| **GUI-03R4.1** | Human Editing Reliability: auto-scroll, clean fixture, real pointer, selection chain, fit content | 695 | 248 | 03r4_1-real-pointer | Editorial content vs playback duration are distinct concepts |
| **GUI-03R5 (B1–B5)** | Session readiness + drag invariance + viewer layout + multi-layer PiP + contextual menus | 695 | 297 | 03r5-b1-session-drag | EditorState state machine (CONNECTING/OBSERVE/EDIT); preview = clamp(candidate) is the spec'd perceptual behavior |
| **R5 remediations** | Track.hidden row-collapse + preview-plan revision parity | 715 | 302 | 03r5-runtime-consistency-fixes (39/39) | `build_preview_plan` revision parity with `/sequence`; `.track-hidden` CSS instead of `display:none` |
| **R6 / R6.1** | Runtime editing + canEdit gate + 4 reality fixes (aspect math, frame leak, plan invalidation, clamp feedback) | 735→752 | 351→397 | 03r6_1-closure (8/8) | `bumpPlanVersion` invalidates preview immediately; clamp boundary gets dashed-red visual |
| **R6.2** (B1–B5) | Drag fly + hidden preview + Core overlap + at_frame contract + identity smoke | 752→769 | 397→407 | 03r6_2-drag-fly/hidden-preview/identity (19/19) | Same-track overlap invariant on every mutation path; hidden tracks filtered in L0 fallback; `/preview/at_frame` materialized-view contract frozen |
| **GUI-04 (01–06 + FINAL)** | Runtime routes + frame mutation contract closure + Undo/Redo exact + DragState consolidation + Preview-layer model (no PiP heuristic) + Inspector transform reads from Core | **838 + 2 fail** | **465 + 2 skip** | **gui-04-{01,03,04,05,06}** + **gui-04-final-acceptance (23/23)** | No fractional frame reaches mutation API; single DragState (8 canonical fields); `clip.transform` is sole source; `Inspector` is display-only (no parallel state) |

The evolution traces a clear pattern: **the user repeatedly tightened the invariant contract before allowing any feature growth.** Each phase:
1. Produced an audit/measurement artifact
2. Fixed the smallest possible defect
3. Added a static guard so the defect cannot reappear
4. Did not start the next category of feature work

This pattern is what made GUI-04 shippable. Do not abandon it for GUI-05.

---

## 3. Genuinely complete vs merely tested

### 3.1 Genuinely complete (works end-to-end + covered)

| Capability | Layer | Evidence |
|---|---|---|
| Frame-native edit chain (frames as canonical coordinate) | Core + GUI | `test_no_js_round_in_edit.py`, `test_no_sequence_fps_as_source_fps.py`, `frame-contract.test.ts` (37), `test_frame_mutation_contract.py` (28) |
| Mutation Gate (sessionId + baseRevision on every write) | GUI + Core + MCP | `test_gui_gate_contract.py` (11), `gate.test.ts` (16), `test_no_writes_outside_server.py` (4), `gui-01.mjs` |
| Drag coordinate invariance (1 px = 1 frame @ default zoom; no scrollLeft in math) | GUI | `drag-invariant.test.ts` (4), `drag-autoscroll.test.ts` (12), 03R3-1E acceptance (6/6) |
| DragState single source (8 canonical fields, no parallel variables) | GUI | `drag-state.test.ts` (14), `gui-04-04-drag.mjs` (1/1) |
| Hidden-track exclusion at all boundaries | Core + GUI | `test_hidden_track_preview_exclusion.py` (4), `composite-multilayer.test.ts`, gui-04-05-preview-layers (4/4) |
| Same-track overlap invariant on every mutation path | Core | `test_no_overlap_invariant.py`, `test_r6_2_split_clip_overlap.py` (6), Core patch in `commands.py` |
| Undo/Redo exact (one intent = one Operation, frame-exact restoration) | Core + GUI | `test_history_gui_contract.py` (8), `gui-04-03-undo-redo.mjs` (2/2) |
| Preview layer identity (no PiP heuristic; `clip.transform` sole source) | GUI | `preview-layer.ts`, `test_preview_layer_model.py` (19), gui-04-05-preview-layers (4/4) |
| Inspector Transform (no parallel React state) | GUI | `test_transform2d_contract.py` (27), gui-04-06-transform (4/4) |
| Preview/plan revision parity (plan matches /sequence) | Core + Server | `test_preview_plan_revision_parity.py` (6) |
| Timeline ↔ Preview identity | Core + GUI | 03r6_2-identity (10/10) |
| PreviewPlan invalidation on every mutation | GUI | `bumpPlanVersion` in `App.run()` |
| `roundHalfAwayFromZero` is the only edit-coordinate rounding | GUI | `frame-contract.test.ts`, static guard tests |
| Asset 404 fallback (placeholder when source missing) | GUI | per R6 closure fix `PreviewPlayer.test.tsx` (5) |
| Track auto-delete invariant (`for t in tl.tracks: len(clip_ids) >= 1`) | Core | `test_no_orphan_empty_tracks.py` static guard |

### 3.2 Tested but NOT production-verified

These passed every automated gate (pytest + vitest + browser smoke) but were **not exercised by the human 6-check pass** the spec requires:

| Capability | Why not human-verified |
|---|---|
| Cross-track drag with collision rejection (1/5/10/50 px on multi-clip tracks) | Phase B/F of `gui-04-04-drag.mjs` skipped because dev lease held `_sanlihe-r5-manual`. Covered indirectly by `03r6_2-drag-fly` (7/7) on the same fixture. |
| Full 5-clip multi-layer Preview at non-trivial playhead positions | Phase C of `gui-04-05-preview-layers.mjs` runs real-browser DOM scan. Manual 5-clip with arbitrary overlap geometry not done by user. |
| Inspector Transform: full round-trip in real DOM (X → Y → scale → rotation → reset → Undo → Redo) | Phase A of `gui-04-06-transform.mjs` covers; Phase B lease-conditional skipped. Real-DOM Roundtrip was covered by `test_transform2d_contract.py::TestTransformSurvivesRefresh` and Phase C real-browser regression. |
| Lease handoff Human ↔ Agent (real cross-process flow) | `tests/test_mcp_cross_process.py` covers it at the protocol level; the GUI's "hand off to Claude" button has not been clicked in a real session in this audit window. |
| Human 6-check pass on clean Sanlihe | **Not done in this session.** The manual pass from R5 is the gate the user must run. |

### 3.3 Known defects NOT fixed (out of GUI-04 scope)

These were visible in the R6/R6.1/R6.2 audits and were explicitly deferred because GUI-04 was scoped to closure, not feature work:

| # | Defect | Source | Why not fixed | Where to address |
|---|---|---|---|---|
| 1 | `/clips` (video) endpoint is still SECONDS-based; GUI passes frames | R6 audit §C | Spec split is deliberate (frame-native images; legacy seconds for video). Right fix is on GUI side (convert or make `/clips` frame-native). | GUI-05 candidate (single-endpoint frame-native path) |
| 2 | L0 fallback branch fires "in gap" placeholder during 5s loading window before `/preview/plan` resolves | R6 audit §D | Loading state was shown as "in gap" — fixed in R6 closure for image but not for video frames. | GUI-05 candidate (explicit loading state) |
| 3 | Missing-media asset 404s produce no user-visible placeholder (silent broken `<img>`) | W-C runtime verify §2 | Server returns 404 with empty body; client doesn't swap to placeholder. Tracked in `GUI-03R3-W-D-404-followup.md` and explicitly deferred. | GUI-05 candidate (small, 1-2 files) |
| 4 | Stale Help dialog text in `App.tsx:1653-1660` ("J/L ±5s", "Shift+Z 缩放到适配", etc.) | W-D §2 | String-only fix. Reported and not shipped. | One-line PR between any future batch (also called out in SESSION) |
| 5 | Pre-existing failures: 2 documented + 3 NEW (sanlihe-clean-fixture drift + gui-04-final-test empty tracks) | See §4.A | Different root causes; one is regression from GUI-04 smoke | **Cleanup batch first** (Option A below) |

---

## 4. Remaining foundational gaps

### 4.A TEST HYGIENE — three regressions that didn't exist 24 hours ago

Running `pytest tests/ -q` right now shows **5 failures**, not the 2 documented in SESSION.md:

| Test | State | Root cause | Severity |
|---|---|---|---|
| `test_no_orphan_empty_tracks_in_projects_dir` | Pre-existing + **NEW polluter** | The GUI-04 final-acceptance smoke created `projects/gui-04-final-test/` and added it to the projects/ scan; the working copy has v2/v3/a1/a2/a3/t1/t2 default tracks with no clips (smoke didn't add content to them). Also `sanlihe-slice-30s/` has 4 empty tracks from the old fixture. | Real regression in test scope |
| `test_working_copy_sanlihe_r5_manual_is_overlap_free` | Pre-existing | `_sanlihe-r5-manual` has 5 NEW overlaps in `t1` (c241bdc↔cbbe06c, c241bdc↔cdf2107, c666e18↔cbbe06c, c666e18↔cdf2107, cbbe06c↔cdf2107). Caused by `cdf2107` being added with `start=19.87, end=49.0` during smoke. | Pre-existing |
| `test_t1_subtitle_durations_are_editorial` | **NEW** | `cdf2107` was added to t1 in the clean fixture, ending at 49s instead of editorial scope. | Caused by canonical fixture pollution |
| `test_v1_editorial_extent_is_49_51s` | **NEW** | V1 extent is now 40s not 49.51s — V1 clips were reordered. | Same |
| `test_visible_extent_matches_v1_editorial` | **NEW** | Visible max 49s but V1 end 40s. | Same |

The canonical clean fixture (`projects/sanlihe-slice-30s-clean/current.json`) carries `CANONICAL_READONLY_DO_NOT_MUTATE` but **was mutated in place** during the GUI-04 acceptance smoke. This breaks the trust boundary the rest of the project relies on:

```
git diff --stat projects/sanlihe-slice-30s-clean/current.json
 1 file changed, 672 insertions(+), 216 deletions(-)
```

This is the single most important finding. It indicates the working-copy helper was bypassed (or never invoked) during the FINAL acceptance run.

### 4.B FOUNDATION GAPS — items in spec, not yet GUI

These are listed in `YROLL Editor Foundation v0.2.md` §37 (P0) + §38 (P1) + §39 (P2) and `GUI-03-Production-Usability-Spec-v0.1.md` but have **no GUI surface yet**:

| Spec ref | Capability | Core | GUI | Spec priority |
|---|---|---|---|---|
| §13 / §28 | Story/Beat Model UI + AI affected region highlight | ✅ `yroll.core.beat` + `GET/POST/DELETE /beats` | ❌ No UI surface | P0 per spec |
| §15 / §26 | SnapEngine UI consumption (Core already does internal snap; GUI relies on local snap during pointermove only — the user's "snap target kind=end" path is not surfaced) | ✅ SnapEngine | ⚠️ Partial: 04-04 dragged-preview shows ghost target via 1px line; user can't see "snap to playhead / marker / word / beat" | P0 per spec |
| §17 / §26 | Marker UI (markers exist in Core + `/markers` endpoints; not in GUI) | ✅ Markers + endpoints | ❌ | P0 per spec |
| §29 | Agent Contract surface (MCP tools + agent audit log) | ✅ endpoints + diff | ❌ No GUI panel | P1 per spec |
| §39 P2 | Publish Metadata + Cover picker (`Timeline.publish_metadata`) | ❌ Not in Core | ❌ | P2 per spec |
| §39 P2 | Timeline-local Revision (Project-level only today) | ❌ Not in Core | ❌ | P2 per spec |
| §39 P2 | Keyframes / Animation / Ease / Motion path | ❌ Not in Core | ❌ | P2 per spec |
| §39 P2 | Crop / Mask / Blend mode | ⚠️ endpoints exist | ❌ | P2 per spec |

### 4.C ARCHITECTURE DEBT (non-blocking, but accumulates)

Carried from the v0.2 history; each is documented in SESSION but never resolved:

1. **`/project/open` swap silently drops the lease** — GUI must re-acquire after a project open; no warning to the user.
2. **`save_state()` is non-atomic** — `op_seq` race exists in-memory. Only safe because `yroll serve` is the sole writer.
3. **`_g_stores` keyed by `id(ProjectCore)`** — process-local; reload loses lease/audit/revision context. Plan called for LeaseStore to migrate to `ProjectSession` layer.
4. **`EditLease.base_revision` is not updated on mutation** — GUI must poll `/ui/status` to stay current (which it does every 5s). Works but wasteful.
5. **Missing-media 404 returns empty body** — see §3.3 #3.
6. **`static-with-proxy.mjs` proxy allowlist does not include `/sequence`** — `useProjectSequence` is bypassed via the proxy; GUI falls back to other endpoints. Documented in R6.1 audit. One-line fix deferred.

---

## 5. Proposed next phase — bounded options

The user said "propose the next development phase as a bounded plan" and "do not invent new features merely because they are possible." That rules out greenfield feature work. The two options below are what the post-state evidence actually justifies.

### Option A — `GUI-04.5` Cleanup & Defect Closure (RECOMMENDED first)

**Mandate:** close every defect GUI-04 surfaced but did not address, plus the test hygiene regressions. No new capability.

**Bounded scope (4 mechanical batches, ~1–2 sessions):**

| Batch | Title | Files touched | Acceptance |
|---|---|---|---|
| **04.5-A** | Canonical fixture protection (rebuild clean Sanlihe + restore working-copy helper + tighten `serve-clean-sanlihe.mjs`) | `scripts/build_clean_sanlihe_fixture.py`, `gui/smoke/serve-clean-sanlihe.mjs`, new `tests/test_no_canonical_mutation.py` static guard that asserts clean fixtures match HEAD's committed copy | All 3 NEW sanlihe-clean failures pass; static guard green |
| **04.5-B** | Pre-existing 2 failures (`_sanlihe-r5-manual` overlap + orphan tracks) — pick a remediation strategy and ship | One of: (a) delete the offending subtitle, (b) reset working copy from canonical, (c) accept pre-existing and rename tests to `_known_failures` | Either 0 fail or 2 documented pre-existing |
| **04.5-C** | Asset 404 placeholder + Help-dialog keymap text fix (the two trivial, long-deferred polish items) | `PreviewPlayer.tsx`, `App.tsx:1653-1660` (string), maybe `static-with-proxy.mjs` allowlist | New vitest for asset-onError placeholder; smoke or visual verify for Help dialog |
| **04.5-D** | Stale working-tree cleanup (drop `gui-04-final-test/` scratch project + `gui-04-D-*` scratch projects; add `.gitignore` entry for `projects/gui-04-*` scratch) | `.gitignore`, optionally `scripts/clean-gui-04-scratch.ps1` | `git status` clean again |

**Why this batch first:**
- 04.5-A closes a **real trust boundary violation** (canonical mutated in place).
- 04.5-B brings the regression count back to the documented 2.
- 04.5-C is the smallest possible UX delta that produces visible user value.
- 04.5-D restores `git status` to clean.
- After 04.5 lands, "pytest green except documented pre-existing" is **literally true** again, which is the invariant GUI-04 Final Acceptance claimed to have established.

**Out of scope for 04.5:**
- No new endpoints
- No Core model changes
- No new feature work
- No undoing of any GUI-04 batch

**Stop condition:** regression is back to ≤2 documented pre-existing failures; canonical fixture protection has a static guard; `git status` is clean.

---

### Option B — `GUI-05` Foundation v0.2 P0 Surface (only after Option A completes)

**Mandate:** bring the first Foundation P0 capabilities that have Core but no GUI into user-visible form. Stay strictly inside spec §37 P0 (no P1, no P2).

**Three candidate sub-batches, each independently shippable:**

#### B.1 — Markers UI (§17 / §26)
Core has it; GUI does not.
- Visual: a thin track-header row above V1 showing marker triangles with labels.
- Add: `m` key drops a marker at playhead; right-click marker → delete or rename.
- Reads `/markers`; writes via `/markers` (which Core already gates).
- Pin: smoke covers marker add → Core state → marker renders → delete → marker gone.

#### B.2 — Beat Model UI (§13)
Core has `GET/POST/DELETE /beats` + `suggest_beat_boundaries`.
- "Suggest beats" button → Core suggests → user accepts/edits.
- Visual: a second row in the header (under markers) showing beat boundaries as labeled vertical bars.
- Read: `GET /beats`. Write: `POST /beats` with `(timeline_frame, label)`.

#### B.3 — AI Affected Region Highlight (§26)
Core returns `ai_affected: [{start_frame, end_frame}]` in `/ui/status` (currently empty).
- Whenever the human receives the lease back from the Agent, show a yellow tint strip on the Timeline at the affected range, for 30 seconds or until any human action.
- The Core side already populates `ai_affected` per the docs (§26); the GUI just has to render it.

**None of B.1/B.2/B.3 touch Core.** Each is a single-file GUI change + a static guard + a smoke. Estimated combined: 2–3 sessions.

**Stop condition for GUI-05 B-cycle:** all three P0 capabilities have a real DOM affordance, a Core wire, a vitest, a smoke, and no regression.

**Out of scope for GUI-05 B-cycle:**
- Publish Metadata (P2; would require Core model change)
- Timeline-local Revision (P2)
- Keyframes / Crop / Mask / Blend (P2)
- Anything that changes Core behavior

---

## 6. What this plan explicitly does NOT do

Per the user's "preserve all established invariants unless a concrete defect requires changing them":

- Does NOT touch `roundHalfAwayFromZero`, `assertIntFrame`, `drag-state.test.ts` 8-field shape, `clip.transform` sole-source rule, `bumpPlanVersion` invalidation, `clipInspector` no-parallel-state rule.
- Does NOT remove the `CANONICAL_READONLY_DO_NOT_MUTATE` sentinel — it strengthens the helper that enforces it.
- Does NOT introduce any new Core mutation, endpoint, or pydantic field.
- Does NOT begin P2 work (publish metadata, keyframes, AI features).
- Does NOT weaken overlap protection, frame purity, or any other static guard.

---

## 7. Decision points for the user (please pick before implementation)

1. **Sequence:** do you want Option A (04.5 cleanup) before Option B (GUI-05 features), or skip A and start B directly?
2. **For 04.5-B** (the two pre-existing failures): is the resolution (a) delete offending subtitle, (b) reset working copy from canonical, or (c) accept and rename to `_known_failures`?
3. **For GUI-05 B-cycle ordering:** B.1 markers → B.2 beats → B.3 AI-affected, or a different order?
4. **Scope cap:** keep GUI-05 to B.1+B.2 only (true Foundation P0 UI) and defer B.3 to a later batch?

Once you answer these, the implementation plan can be tightened to a single canonical document and shipped as one phase per the established pattern (audit → batch → regression → commit → SESSION update).
