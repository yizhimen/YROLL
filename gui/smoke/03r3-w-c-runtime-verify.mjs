// GUI-03R3-W-C runtime verification against a real browser.
//
// Verifies the W-C drop-zone artifacts (data-drop-zone="below-tracks",
// .drop-zone-new-track, .track-content.drag-over) are actually present
// in the rendered DOM of the running frontend, NOT just in unit tests.

import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const out = { checks: [], coreStates: [] };
const record = (name, ok, detail) => {
  out.checks.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}  ${detail || ''}`);
};

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

const errors = [];
page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
page.on('console', (m) => {
  if (m.type() === 'error') errors.push(`console.error: ${m.text()}`);
});

await page.goto('http://localhost:5180/', { waitUntil: 'networkidle', timeout: 20000 });
await page.waitForSelector('.timeline-content', { timeout: 10000 });
await page.waitForTimeout(2500);

// ---------- 1. Baseline DOM artifacts ----------

const dropZoneCount = await page.locator('.drop-zone-new-track').count();
record('drop-zone-new-track-rendered', dropZoneCount >= 1,
       `count=${dropZoneCount}`);

const dropZoneDataAttr = await page
  .locator('.drop-zone-new-track')
  .first()
  .getAttribute('data-drop-zone')
  .catch(() => '');
record('drop-zone-data-attr=below-tracks',
       dropZoneDataAttr === 'below-tracks',
       `got=${JSON.stringify(dropZoneDataAttr)}`);

const dropZoneLabel = await page
  .locator('.drop-zone-new-track .drop-zone-label')
  .first()
  .innerText()
  .catch(() => '');
record('drop-zone-default-label',
       /新建.*轨/.test(dropZoneLabel),
       `label=${JSON.stringify(dropZoneLabel)}`);

// Track-content elements exist (the per-track drop targets)
const trackContentCount = await page.locator('.track-content').count();
record('track-content-count', trackContentCount >= 1,
       `count=${trackContentCount}`);

// ---------- 2. CSS class hooks present in rendered stylesheet ----------

// We synthesize a dragover on the drop zone and confirm the
// .drag-over class lands (and the corresponding CSS rule changes
// computed style).
const dragOverApplied = await page.evaluate(() => {
  const dz = document.querySelector('.drop-zone-new-track');
  if (!dz) return { error: 'no drop zone' };
  const dt = new DataTransfer();
  dt.setData('text/yroll-asset', 'fake-id');
  dt.setData('text/plain', 'fake');
  const ev = new DragEvent('dragover', {
    bubbles: true, cancelable: true, dataTransfer: dt,
  });
  dz.dispatchEvent(ev);
  // Return immediately — classList is mutated synchronously by React.
  const cls = dz.className;
  return { className: cls, hasDragOver: cls.includes('drag-over') };
});
record('drop-zone-drag-over-class-applied',
       dragOverApplied.hasDragOver === true,
       `class=${JSON.stringify(dragOverApplied.className)}`);

// ---------- 3. Track-content drag-over (existing-track hover) ----------

const trackDragOver = await page.evaluate(() => {
  const tc = document.querySelector('.track-content');
  if (!tc) return { error: 'no track-content' };
  const dt = new DataTransfer();
  dt.setData('text/yroll-asset', 'fake-id');
  const ev = new DragEvent('dragover', {
    bubbles: true, cancelable: true, dataTransfer: dt,
  });
  tc.dispatchEvent(ev);
  return { className: tc.className, hasDragOver: tc.className.includes('drag-over') };
});
record('track-content-drag-over-class-applied',
       trackDragOver.hasDragOver === true,
       `class=${JSON.stringify(trackDragOver.className)}`);

// ---------- 4. No empty track rows rendered ----------

const trackLabels = await page.evaluate(() => {
  const rows = document.querySelectorAll('.timeline-headers .track-label-row');
  return Array.from(rows).map((r) => ({
    id: r.querySelector('.track-id')?.textContent || '',
    text: r.querySelector('.track-label-title')?.textContent || '',
  })).filter((r) => r.id);
});
record('no-empty-track-rows', trackLabels.length > 0,
       `count=${trackLabels.length}`);
const emptyIds = trackLabels.filter((r) => r.id === '' || r.text === '');
record('no-empty-track-rows-no-blanks', emptyIds.length === 0,
       `blanks=${emptyIds.length}`);

// ---------- 5. CSS rule actually present in document ----------

const cssHasRules = await page.evaluate(() => {
  const found = {
    dropZone: false,
    dropZoneDragOver: false,
    trackContentDragOver: false,
  };
  for (const sheet of Array.from(document.styleSheets)) {
    let rules;
    try { rules = sheet.cssRules; } catch { continue; }
    if (!rules) continue;
    for (const r of Array.from(rules)) {
      const sel = r.selectorText || '';
      if (sel.includes('.drop-zone-new-track') && !sel.includes('.drag-over')) found.dropZone = true;
      if (sel.includes('.drop-zone-new-track.drag-over')) found.dropZoneDragOver = true;
      if (sel.includes('.track-content.drag-over')) found.trackContentDragOver = true;
    }
  }
  return found;
});
record('css-rule-drop-zone', cssHasRules.dropZone === true,
       `dropZone=${cssHasRules.dropZone}`);
record('css-rule-drop-zone-drag-over', cssHasRules.dropZoneDragOver === true,
       `dropZoneDragOver=${cssHasRules.dropZoneDragOver}`);
record('css-rule-track-content-drag-over',
       cssHasRules.trackContentDragOver === true,
       `trackContentDragOver=${cssHasRules.trackContentDragOver}`);

// ---------- 6. Capture initial Core state (project snapshot) ----------

// Pull /project directly to see the on-disk Core state.
const apiProject = await page.evaluate(async () => {
  const r = await fetch('/project');
  if (!r.ok) return { error: `status ${r.status}` };
  return r.json();
});
const beforeState = {
  timeline_count: (apiProject?.timelines ?? []).length,
  total_tracks: (apiProject?.timelines ?? []).reduce(
    (n, tl) => n + (tl.tracks?.length ?? 0), 0),
  total_clips: Object.keys(apiProject?.clips ?? {}).length,
  per_timeline_tracks: (apiProject?.timelines ?? []).map(
    (tl) => ({ id: tl.timeline_id, tracks: tl.tracks?.length ?? 0 }),
  ),
};
out.coreStates.push({ when: 'before', state: beforeState });
record('core-state-fetched', !apiProject?.error,
       `tracks=${beforeState.total_tracks} clips=${beforeState.total_clips}`);

// ---------- 7. Render-side: built bundle metadata ----------

const bundleMeta = await page.evaluate(() => {
  const scripts = Array.from(document.querySelectorAll('script[src]'));
  const css = Array.from(document.querySelectorAll('link[rel=stylesheet]'));
  return {
    scripts: scripts.map((s) => s.src.split('/').pop()),
    css: css.map((c) => c.href.split('/').pop()),
  };
});
record('bundle-script-loaded', bundleMeta.scripts.length > 0,
       JSON.stringify(bundleMeta.scripts));
record('bundle-css-loaded', bundleMeta.css.length > 0,
       JSON.stringify(bundleMeta.css));

// ---------- 8. Page errors? ----------

record('no-page-errors', errors.length === 0,
       `errors=${JSON.stringify(errors).slice(0, 300)}`);

// ---------- Save report ----------

writeFileSync('/tmp/03r3-w-c-runtime-verify.json', JSON.stringify(out, null, 2));
const failed = out.checks.filter((c) => !c.ok);
console.log(`\n${out.checks.length - failed.length}/${out.checks.length} passed`);
console.log('Bundle:', JSON.stringify(bundleMeta));
console.log('Initial Core state:', JSON.stringify(beforeState));
if (failed.length > 0) process.exitCode = 1;

await browser.close();
