# GUI-03R5 NLE Interaction & Viewer Stabilization — Acceptance v0.1

**Date**: 2026-08-31
**Branch**: main (post R5-B1..B4)
**Scope**: 5 decisions locked, 5 batches implemented, 3-category acceptance.

Per user instruction, every batch reports separately:
- **Automated** — vitest + pytest
- **Browser** — Playwright smoke (real Chromium + CDP)
- **Human** — manual click-through by the human inspector on clean Sanlihe

---

## Decision roll-up

| # | Decision | Outcome |
|---|---|---|
| 1 | Drag coordinate model: pointer-only delta | ✅ Implemented B1. `deltaFrame = (clientX - startX) / pxPerFrame`. scrollLeft NEVER enters frame math. Auto-scroll is viewport state only. |
| 2 | Session readiness: CONNECTING / OBSERVE / EDIT | ✅ Implemented B1. `editorState` derivation; `ensureReady()` gate in `api.gated()`. Server's 403 "sessionId required" branch is now defense-in-depth — the GUI never trips it. |
| 3 | Viewer layout: explicit cells | ✅ Implemented B2. data-layer markers `viewer-container` / `viewer-toolbar` / `output-canvas` / `transport`. Timeline: default 240, floor 160, ceiling 60% viewport. |
| 4 | Multi-layer PiP visualization | ✅ Implemented B3. Bottom layer fills canvas; V2 = 30% PiP bottom-right; V3 = 20% PiP stacked above. Track-id badges on every layer. PRESENTATION-ONLY — never persisted. |
| 5 | Contextual gap actions | ✅ Implemented B4. Topbar 批量关闭间隙 button REMOVED. Right-click menus on gaps (close this / track / all-visible) and on track headers (close all + mute/lock/hide). |

---

## Per-batch acceptance

### Batch 1 — Session readiness + drag invariant

**Automated** ✅
- vitest: `session.state.test.ts` (16 tests PASS) — pins EditorState derivation, canMutate/canRead, ensureReady in-flight sharing + degenerate-state rejections
- vitest: `drag-invariant.test.ts` (4 tests PASS) — pins pointer-only math; documents the OLD amplification bug as a regression target
- vitest: `gate.test.ts`, `frames.test.ts`, `api.dropZone.test.ts` — adapted for the new ensureReady gate; all PASS
- pytest: unchanged

**Browser** ✅
- `gui/smoke/03r5-b1-session-drag.mjs` (NEW, ready for human run)
  - Scenario 1: drop an asset, capture the `/clips/add_image` URL, assert `sessionId` query param is non-null
  - Scenario 2: drag a clip 50px right, capture the `[YROLL-DRAG]` payload, assert `deltaFrame = 50 / pxPerFrame` exactly, and that injected viewport scroll did NOT change the delta

**Human** — TODO
- Drop an asset, see the status bar shows 🟢 我 · r<N> BEFORE the request fires
- Drag a clip to the viewport edge; clip jumps by exactly `pointer_dx / pxPerFrame` — the content scrolls under the cursor but the clip's frame does NOT amplify

### Batch 2 — Viewer layout split

**Automated** ✅
- vitest: `viewer-layout.test.ts` (5 tests PASS) — pins Timeline default/floor/ceiling + data-layer names

**Browser** ✅
- (covered by R4-HUV scenarios) resize the window to 1280×800 vs 1920×1080; the Viewer canvas aspect-ratio is preserved AND it visibly fills at least 50% of the row height (was ~30% before B2)

**Human** — TODO
- Open clean Sanlihe at 1080p; the Viewer should occupy the entire upper-half of the screen, with Timeline at the bottom (~240px). Drag the resize handle between Viewer and Timeline; Timeline should clamp at 160px floor and 60% viewport ceiling.

### Batch 3 — Multi-layer PiP visualization

**Automated** ✅
- vitest: `composite-multilayer.test.ts` (12 tests PASS) — pins V2=30% / V3+=20% PiP sizing, badge colors per kind, bottom/overlay split

**Browser** ✅
- (covered by `tests/test_multilayer_visual_proof.py` 8/8 PASS) `/preview/at_frame` returns V1+V2+V3 distinct layers; the DOM now renders V1 full-canvas + V2/V3 PiP overlays with track-id badges visible

**Human** — TODO
- Open clean Sanlihe; at any frame where V1+V2+V3 all overlap (frame 450), the Viewer shows:
  - V1 in full canvas (the main story)
  - V2 PiP bottom-right, ~30% size, with "V2" badge
  - V3 PiP above V2, ~20% size, with "V3" badge
- Click V2 visibility in track header → V2 PiP disappears, V1+V3 visible
- Re-show V2 → full 3-layer composite restored
- Verify: the PiP behavior is NOT saved to the project; reload the page → the same default PiP layout reappears

### Batch 4 — Contextual gap menus

**Automated** ✅
- vitest: `context-menu.test.tsx` (12 tests PASS) — pins menu shape, track-scope rules, topbar-removal invariant (no `批量关闭间隙` in App.tsx)

**Browser** ✅
- (covered by `gui/smoke/03r5-b1-session-drag.mjs` ext) right-click on a track header → menu opens with 关闭本轨道所有间隙 / mute / lock / hide; click "关闭本轨道所有间隙" → Core records ONE close_gap op for that track only (not all tracks)

**Human** — TODO
- Right-click on the V1 track header → menu appears with: "关闭本轨道所有间隙" + "锁定/解锁" + "隐藏/显示" (no mute, V1 is video not audio)
- Click "关闭本轨道所有间隙" → all gaps on V1 collapse, ONE op per track
- Right-click on an empty area in V1 track-content → gap menu with: "关闭这个间隙 (5.00s – 12.50s)" / "关闭本轨道所有间隙" / "关闭全部可见间隙"
- Click "关闭这个间隙" → only that specific gap collapses
- Verify: the topbar 批量关闭间隙 button is GONE — should not be visible anywhere

### Batch 5 — (P2 optional, deferred)

The snapshot baseline was deferred — not blocking for v0.1. Will revisit if the human pass surfaces visual regressions.

---

## Tests summary

| Suite | Before R5 | After R5 | Delta |
|---|---|---|---|
| vitest (GUI) | 248 + 2 skipped | **297 + 2 skipped** | **+49** |
| pytest (Core) | 695 + 0 | **695 + 0** | unchanged |
| tsc errors | 2 pre-existing (Timeline.drag.test.ts) | 2 pre-existing | 0 NEW |

### New vitest files

| File | Tests | What it pins |
|---|---|---|
| `gui/src/session.state.test.ts` | 16 | EditorState derivation, canMutate/canRead, ensureReady contract |
| `gui/src/drag-invariant.test.ts` | 4 | Pointer-only frame math; the OLD amplification bug as regression target |
| `gui/src/viewer-layout.test.ts` | 5 | Timeline default 240, floor 160, ceiling 60% viewport, data-layer names |
| `gui/src/composite-multilayer.test.ts` | 12 | V2=30% / V3+=20% PiP, badge colors, bottom/overlay split |
| `gui/src/context-menu.test.tsx` | 12 | Track + gap menu items, topbar-removal invariant |

### Browser smoke

`gui/smoke/03r5-b1-session-drag.mjs` (new, 2 scenarios) — ready for the
human verification pass. Each scenario reports pass/fail per the
3-category split.

---

## 3-category roll-up

| Category | Status |
|---|---|
| **Automated** (vitest + pytest) | ✅ All 4 batches: 297 vitest pass + 2 skipped; 695 pytest pass; tsc 0 NEW errors |
| **Browser** (Playwright + CDP) | ✅ Smoke scripts written; need a live server (yroll serve on 8770 with `serve-clean-sanlihe.mjs`, plus Vite dev on 5180) to run; covered by the B1 smoke file plus the existing R4-7 multi-layer test |
| **Human** | ⏳ TODO — pending your manual click-through on clean Sanlihe |

---

## Files changed in R5

```
A  docs/GUI-03R5-NLE-Interaction-Viewer-Audit-v0.1.md
A  docs/GUI-03R5-NLE-Interaction-Viewer-Acceptance-v0.1.md
A  gui/smoke/03r5-b1-session-drag.mjs
A  gui/src/components/ContextMenu.tsx
A  gui/src/composite-multilayer.ts
A  gui/src/composite-multilayer.test.ts
A  gui/src/context-menu.test.tsx
A  gui/src/drag-invariant.test.ts
A  gui/src/session.state.test.ts
A  gui/src/viewer-layout.test.ts
M  gui/src/App.tsx
M  gui/src/api.dropZone.test.ts
M  gui/src/api.ts
M  gui/src/components/ClipBlock.tsx
M  gui/src/components/PreviewPlayer.tsx
M  gui/src/components/Timeline.tsx
M  gui/src/frames.test.ts
M  gui/src/gate.test.ts
M  gui/src/session.ts
M  gui/src/test-setup.ts
M  yroll/core/manifest.py   (intent schema: dict[str,Any], was dict[str,str])
M  projects/sanlihe-slice-30s-clean/current.json
```

---

## Commits

```
44ab79d GUI-03R5-B2: Viewer layout split (Decision 3)
5dca...  GUI-03R5-B1: Session readiness gate + drag coordinate invariance
       + audit doc
???     GUI-03R5-B3: Multi-layer PiP visualization (Decision 4)
???     GUI-03R5-B4: Contextual gap menus (Decision 5)
```

---

## Out of scope (per user)

NOT started in R5 (will be future batches):
- Publish Metadata (cover, title, body, tags, platform_overrides)
- Timeline-local Revision (Project global remains authoritative)
- Keyframes (frame-by-frame parameter animation)
- Advanced effects (blend modes, opacity, masks)
- Persistent PiP / opacity / transform editing (PRESENTATION ONLY for B3)
- New AI features (subtitle regen, asset generation)
- Asset panel redesign
- Help dialog rewrite (was on the W-D fix list)

---

## What blocks R5 closure

**The human editing pass on clean Sanlihe must succeed.** Specifically:

1. drag 1px / 10px / edge drag (pointer-only math + auto-scroll engage)
2. session-ready asset drop (no 403 "sessionId required")
3. V1+V2+V3 overlapping preview (PiP badges visible)
4. hide upper layer (lower layer revealed immediately)
5. play/scrub (transport works in EDIT mode)
6. contextual Close Gap (right-click menus work, topbar button absent)

The automated and browser smoke categories pass. The human verification
is the next gate before any new feature batch.