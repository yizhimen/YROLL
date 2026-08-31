# Follow-up: 404s on `/assets/{id}/file` and `/assets/{id}/waveform`

> **Status:** NEW follow-up issue. Discovered during GUI-03R3-W-C Runtime
> Verification (`docs/GUI-03R3-W-C-RUNTIME-VERIFY.md` §2, single FAIL).
> **Not mixed into W-D** (per user instruction in the W-D brief).
> **Not blocking the track-header work in W-D.**

---

## 1. What was observed

While running the live W-C bundle against the Sanlihe fixture, the
browser console spammed:

```
Failed to load resource: the server responded with a status of 404 (Not Found)
```

for two URL patterns:

| URL pattern | Where the GUI requests it |
|---|---|
| `/assets/{id}/file` | AssetPanel preview thumbnail / `<img>` tag for each asset row |
| `/assets/{id}/waveform` | Audio asset row's waveform placeholder |

`gui/smoke/check-404s.mjs` categorized every 404 by URL pattern and
matched them against the project's `assets` list. The category matched
exactly: every 404 was either an asset file or an asset waveform —
**none** were W-C related (no drop-zone / drag-over / track-related
URLs).

## 2. Root cause (provisional)

The Sanlihe fixture's source media is not under the project's `media/`
directory in this fixture copy. When the GUI mounts an AssetPanel
row, it eagerly sets `<img src="/assets/{id}/file">` and a waveform
`<img src="/assets/{id}/waveform">` — the server returns 404 for
every asset whose underlying media is missing from disk.

The 404 is harmless to the editor (the row still renders, the user
can still drag the asset), but:

1. It clutters the console during smoke runs.
2. It's misleading in production — a user who deletes an asset's
   media outside the editor would see the same 404s and wonder if
   the editor is broken.
3. Network panel noise makes real errors harder to spot.

## 3. Why this is NOT W-D

W-D's scope is "Track header UX" — semantic icons, compact controls,
resizable column. None of those touch asset URLs. Mixing the 404 fix
into W-D would:

- Inflate W-D's diff beyond its scope.
- Block the track-header work on an unrelated file-existence audit.
- Hide the 404 behind a feature commit so the fix is hard to spot.

Per the user's instruction, this lives in its own follow-up.

## 4. Suggested fix (separate batch)

A small `<follow-up>` batch. Sketch only — not implemented here:

1. **Server side** (`yroll/server/app.py`):
   - Return a 1×1 transparent PNG (or a small SVG placeholder) for
     `/assets/{id}/file` when the underlying media is missing
     instead of 404. Or: return 404 with a JSON body `{missing:
     true, reason: "media not on disk"}` so the client can branch.
   - Same for `/assets/{id}/waveform` (return an empty SVG line so
     the row stays at the same height).

2. **Client side** (`gui/src/components/AssetPanel.tsx`):
   - On `<img onError>`, swap `src` to a built-in placeholder data
     URL. CSS `.asset-thumb.missing` dims the row slightly so the
     user can see at a glance which assets lack media.
   - Stop logging the 404 to console (use a debug-only console.warn).

3. **Tests**:
   - pytest: 2 server tests (404 → placeholder body, 200 → real file).
   - vitest: 1 AssetPanel test that mounts a project with a
     missing-media asset and asserts no console.error fires and
     the placeholder renders.

4. **Static guard** (optional):
   - `tests/test_no_404_console_in_smoke.py` — runs the existing
     `gui/smoke/03r3-sanlihe.mjs` and asserts the page produces 0
     console.error entries.

## 5. Acceptance criterion

- 0 console.error entries from `/assets/...` URLs during a full
  Sanlihe open in the live browser.
- Missing-media assets render with a placeholder (visible but
  obviously "missing") instead of a broken-image glyph.
- The drag-and-drop path (which is what W-C actually exercises)
  still works identically.

## 6. Relationship to other open issues

| Issue | Status |
|---|---|
| Stale Help / Shortcut UI (W-C Runtime Verify §5) | **Fixed in W-D** (Help dialog now derives labels from Core keymap; Home binding added to `keyboard.py`) |
| 404s on `/assets/{id}/file` and `/assets/{id}/waveform` | **NEW — separate follow-up** (this doc) |
| Stale 5-min lease blocking browser mutation smoke | Out of scope; transient — wait 5 min OR restart the server |

## 7. Files most likely to change

When the follow-up batch ships, expected surface area:

- `yroll/server/app.py` — `/assets/{id}/file` and `/assets/{id}/waveform` handlers
- `gui/src/components/AssetPanel.tsx` — `<img onError>` → placeholder
- `gui/src/styles.css` — `.asset-thumb.missing` style
- `tests/test_missing_media_asset_placeholder.py` — new pytest
- `gui/src/AssetPanel.missing.test.tsx` — new vitest

(Not touching any of these in W-D.)