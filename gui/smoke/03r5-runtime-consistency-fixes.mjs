#!/usr/bin/env node
// R5 audit (2026-09-01) — runtime-consistency fixes browser smoke.
//
// Two regressions pinned by this script:
//
//   A. Hidden Track UI semantics
//      - .track-row[data-track-id="<hidden>"] exists in the DOM
//      - .track-label-row[data-track-id="<hidden>"] exists
//      - both have .track-hidden class
//      - neither row has inline `display: none`
//      - the row's clip block (.clip[data-clip-id="…"]) is rendered
//
//   B. Preview Plan revision parity (Core fix)
//      - GET /sequence project_revision == GET /preview/plan project_revision
//      - GET /preview/at_frame?frame=N returns is_black=false + visual_layers>0
//        for a known in-bounds frame (proves the plan lands in the GUI;
//        before the fix, plan was always 0 → usePreviewPlan discarded it →
//        black Preview with zero layers).
//
// Connects to a running Chromium via CDP. The R5 working-copy server
// (gui/smoke/serve-r5-manual.mjs) must be running on BACKEND; the
// static-with-proxy frontend must be running on FRONTEND.
//
// Usage:
//   chromium --remote-debugging-port=9222
//   node gui/smoke/serve-r5-manual.mjs 8770 &   # if not already running
//   cd gui && node gui/smoke/static-with-proxy.mjs 5180 &
//   node gui/smoke/03r5-runtime-consistency-fixes.mjs

import { setTimeout as sleep } from 'node:timers/promises';

const FRONTEND = process.env.FRONTEND ?? 'http://127.0.0.1:5180';
const BACKEND = process.env.BACKEND ?? 'http://127.0.0.1:8770';
const CDP = process.env.CDP ?? 'http://127.0.0.1:9222';

console.log('=== R5 runtime-consistency fixes browser smoke ===');
console.log(`frontend=${FRONTEND}  backend=${BACKEND}  cdp=${CDP}\n`);

const { chromium } = await import('playwright');

const browser = await chromium.connectOverCDP(CDP);
const context = browser.contexts()[0] ?? await browser.newContext();
const page = context.pages()[0] ?? await context.newPage();

let passed = 0, failed = 0;
function check(label, ok, detail = '') {
  const tag = ok ? '✓ PASS' : '✗ FAIL';
  if (ok) passed++; else failed++;
  console.log(`  [${tag}] ${label}${detail ? '  ' + detail : ''}`);
}

await page.goto(FRONTEND, { waitUntil: 'domcontentloaded' });
await sleep(8000);

// === Section A: Hidden Track UI semantics ===
console.log('\n[A] Hidden Track UI semantics');

// Pick a hidden track by hitting the backend directly from the browser
// (avoids relying on which track the GUI chose as activeTimelineId).
const projectState = await page.evaluate(async (BASE) => {
  const r = await fetch(`${BASE}/project`);
  const d = await r.json();
  return d;
}, BACKEND);

const main = (projectState.timelines || []).find(t => t.timeline_id === 'main');
check('project has a "main" timeline', !!main, main ? `tracks=${main.tracks.length}` : 'no main');

const hiddenTracks = (main?.tracks || []).filter(t => t.hidden && t.clip_ids.length > 0);
check('project has at least one non-empty hidden track', hiddenTracks.length > 0,
  hiddenTracks.map(t => `${t.track_id}(${t.clip_ids.length})`).join(', '));

// Wait for the Timeline to actually render the active timeline's tracks.
await page.waitForSelector('.track-row', { timeout: 15000 }).catch(() => {});
await sleep(1500);

for (const t of hiddenTracks) {
  const result = await page.evaluate((trackId) => {
    const header = document.querySelector(`.track-label-row[data-track-id="${trackId}"]`);
    const row = document.querySelector(`.track-row[data-track-id="${trackId}"]`);
    return {
      headerExists: !!header,
      headerHasHiddenClass: header?.classList.contains('track-hidden'),
      headerStyle: header?.getAttribute('style') || '',
      rowExists: !!row,
      rowHasHiddenClass: row?.classList.contains('track-hidden'),
      rowStyle: row?.getAttribute('style') || '',
      clipInHiddenRow: !!row?.querySelector('.clip'),
    };
  }, t.track_id);
  check(`[${t.track_id}] header row exists`, result.headerExists);
  check(`[${t.track_id}] header has .track-hidden class`, result.headerHasHiddenClass);
  check(`[${t.track_id}] header has NO display:none`, !/display\s*:\s*none/.test(result.headerStyle),
    `style="${result.headerStyle}"`);
  check(`[${t.track_id}] content row exists`, result.rowExists);
  check(`[${t.track_id}] content row has .track-hidden class`, result.rowHasHiddenClass);
  check(`[${t.track_id}] content row has NO display:none`, !/display\s*:\s*none/.test(result.rowStyle),
    `style="${result.rowStyle}"`);
  check(`[${t.track_id}] clip block inside hidden row is rendered`,
    result.clipInHiddenRow);
}

// === Section B: Preview Plan revision parity ===
console.log('\n[B] Preview Plan revision parity (Core fix)');

const revisionParity = await page.evaluate(async (BASE) => {
  const [seqR, planR] = await Promise.all([
    fetch(`${BASE}/sequence`).then(r => r.json()),
    fetch(`${BASE}/preview/plan?timeline_id=main`).then(r => r.json()),
  ]);
  return {
    seqRev: seqR.project_revision,
    planRev: planR.project_revision,
    planTracks: (planR.tracks || []).length,
    planSubtitles: (planR.subtitle_ranges || []).length,
  };
}, BACKEND);

check('/sequence returns 200 + project_revision',
  typeof revisionParity.seqRev === 'number',
  `seq.project_revision=${revisionParity.seqRev}`);
check('/preview/plan returns 200 + project_revision',
  typeof revisionParity.planRev === 'number',
  `plan.project_revision=${revisionParity.planRev}`);
check('seq.project_revision == plan.project_revision',
  revisionParity.seqRev === revisionParity.planRev,
  `${revisionParity.seqRev} vs ${revisionParity.planRev}`);
check('/preview/plan has non-empty track list',
  revisionParity.planTracks > 0,
  `tracks=${revisionParity.planTracks}`);
check('/preview/plan has subtitle_ranges',
  revisionParity.planSubtitles > 0,
  `subtitles=${revisionParity.planSubtitles}`);

// === Section C: at_frame yields visible layers at a known in-bounds frame ===
console.log('\n[C] /preview/at_frame at a known in-bounds frame');

const atFrameResult = await page.evaluate(async (BASE) => {
  const r = await fetch(`${BASE}/preview/at_frame?timeline_id=main&frame=500`);
  const d = await r.json();
  return {
    status: r.status,
    is_black: d.is_black,
    visual_layers: (d.visual_layers || []).length,
    subtitle_texts: (d.subtitle_texts || []).length,
    first_track: d.visual_layers?.[0]?.track_id,
  };
}, BACKEND);

check('/preview/at_frame returns 200', atFrameResult.status === 200,
  `status=${atFrameResult.status}`);
check('at_frame is_black=false at frame 500', atFrameResult.is_black === false,
  `is_black=${atFrameResult.is_black}`);
check('at_frame has >=2 visual layers (v1+v3)', atFrameResult.visual_layers >= 2,
  `visual_layers=${atFrameResult.visual_layers} (first=${atFrameResult.first_track})`);
check('at_frame has subtitle at frame 500', atFrameResult.subtitle_texts >= 1,
  `subtitle_texts=${atFrameResult.subtitle_texts}`);

console.log(`\n=== Result: ${passed} passed, ${failed} failed ===`);
process.exit(failed === 0 ? 0 : 1);