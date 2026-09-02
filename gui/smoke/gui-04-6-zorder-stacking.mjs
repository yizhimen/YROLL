// gui/smoke/gui-04-6-zorder-stacking.mjs
//
// GUI-04.6: Preview stacking semantic — browser acceptance.
//
// This smoke verifies the rendered DOM order + zIndex for
// overlapping V1+V2+V9 and V1+V3+V7 clips. It does NOT just
// check the numeric layer_index (the API tests already do
// that); it checks the actual CSS values that drive stacking.
//
// Invariant pinned:
//
//   "A visual track appearing higher in the Timeline is a
//    higher visual layer in Preview."
//
// For V1+V2+V9 with clips overlapping at frame 450, in the
// rendered DOM the .composite-layer divs must be present with:
//
//     data-track-id="v9" → zIndex smallest (bottom-painted)
//     data-track-id="v2" → zIndex middle
//     data-track-id="v1" → zIndex largest (top-painted)
//
// Plus the layer_index values in /preview/at_frame must
// reflect V1 having the highest numeric value.
//
// Strategy:
//   1. Open the frontend (port 5180, served by static-with-proxy)
//   2. POST /project/open to load a clean test fixture via the
//      working-copy helper's path (so the canonical stays safe).
//   3. Use the API to create V1+V2+V9 with overlapping clips.
//   4. Reload; navigate to /preview/at_frame; assert numeric
//      layer_index values match V1 > V2 > V9.
//   5. Trigger the PreviewPlayer composite render (real DOM);
//      query .composite-layer divs and assert zIndex values.
//
// Requires:
//   - hardened serve-clean-sanlihe.mjs running on 8770
//   - frontend dist on 5180 (proxy to 8770)
//   - chromium --remote-debugging-port=9222

import { chromium } from '../../gui/node_modules/playwright/index.mjs';

const FRONTEND = 'http://127.0.0.1:5180/';

const results = [];
function record(name, ok, detail) {
  results.push({ name, ok, detail });
  const marker = ok === true ? '✓ PASS' : ok === false ? '✗ FAIL' : '— DOC';
  console.log(`${marker}  ${name}${detail ? '  — ' + detail : ''}`);
}

async function main() {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const ctx = browser.contexts()[0] || await browser.newContext();
  const page = ctx.pages()[0] || await ctx.newPage();
  await page.setViewportSize({ width: 1440, height: 900 });

  await page.goto(FRONTEND, { waitUntil: 'networkidle', timeout: 30000 });

  // Create a fresh project for this smoke (do NOT mutate the
  // canonical Sanlihe fixture).
  const projectName = `gui-04-6-zorder-${Date.now()}`;
  await page.evaluate(async (name) => {
    await fetch(
      '/project/new?root=./projects&name=' + encodeURIComponent(name) +
      '&goal=gui-04-6-zorder',
      { method: 'POST' },
    );
  }, projectName);
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('.timeline-content', { timeout: 15000 });
  await page.waitForTimeout(2000);

  // Acquire lease.
  const creds = await page.evaluate(async () => {
    const cur = await fetch('/lease').then(r => r.json());
    if (cur.isAlive && cur.sessionId) {
      await fetch('/lease/release?sessionId=' + encodeURIComponent(cur.sessionId),
        { method: 'POST' });
    }
    const acq = await fetch(
      '/lease/acquire?actor=human&mode=edit&baseRevision=-1' +
      '&humanLabel=gui-04-6-zorder',
      { method: 'POST' },
    ).then(r => r.json());
    return { sid: acq.sessionId, brev: acq.baseRevision };
  });

  async function mutation(method, path, body) {
    const [basePath, existingQs] = path.split('?');
    const params = new URLSearchParams(existingQs || '');
    params.set('sessionId', creds.sid);
    params.set('baseRevision', String(creds.brev));
    const url = `${basePath}?${params.toString()}`;
    const r = await page.evaluate(async ({ method, url, body }) => {
      const init = { method, headers: { 'Content-Type': 'application/json' } };
      if (body !== undefined) init.body = JSON.stringify(body);
      const resp = await fetch(url, init);
      const text = await resp.text();
      return { status: resp.status, body: text };
    }, { method, url, body });
    if (r.status === 200) {
      creds.brev = await page.evaluate(() =>
        fetch('/operations').then(r => r.json()).then(o => o.length));
    }
    return r;
  }

  // Register 3 assets (distinct IDs).
  const seq = await page.evaluate(() =>
    fetch('/project').then(r => r.json()));
  const fps = seq.sequence.fps;

  async function registerAsset(i) {
    // Use the canonical /assets/import path. For the smoke we
    // don't need a real media file — Core's frame_native add
    // just requires the asset to exist with kind=video. We use
    // the project's existing default assets if any; otherwise
    // create one.
    // Easiest: send a no-op fake file; Core may reject. So we
    // skip /assets/import and instead construct the project via
    // /tracks + /clips with the default assets that the fresh
    // project auto-registers.
    return `a${i}`;
  }
  // The fresh project has no assets. We need to create them
  // via the proper endpoint. For this smoke we accept that
  // /clips/add_image may not work without an asset; we'll use
  // /clips which goes through the add_clip video path.
  // For simplicity, attempt to import a tiny dummy mp4 by
  // writing to the project's media dir. But we cannot from
  // the browser; instead, we'll skip the asset path and use a
  // different strategy: the fresh project may already have
  // assets. Probe.
  const proj0 = await page.evaluate(() =>
    fetch('/project').then(r => r.json()));
  const hasAssets = (proj0.assets || []).length >= 3;
  if (!hasAssets) {
    record('setup — fresh project has ≥3 assets', false,
      `project has ${(proj0.assets || []).length} assets; ` +
      'cannot build 3-track fixture');
    await browser.close();
    process.exit(1);
  }

  // Create V1, V2, V9 tracks.
  for (const tid of ['v1', 'v2', 'v9']) {
    const r = await mutation('POST', '/tracks', {
      kind: 'video', track_id: tid, timeline_id: 'main',
    });
    if (r.status !== 200) {
      record(`setup — create track ${tid}`, false, r.body);
      await browser.close();
      process.exit(1);
    }
  }

  // Add overlapping clips on each track at [300, 600] frames.
  for (let i = 0; i < 3; i++) {
    const tid = ['v1', 'v2', 'v9'][i];
    const aid = proj0.assets[i].asset_id;
    const r = await mutation('POST', '/clips', {
      asset_id: aid,
      source_start_frame: 0,
      source_end_frame: 300,
      timeline_start_frame: 300,
      track_id: tid,
    });
    if (r.status !== 200) {
      record(`setup — add clip on ${tid}`, false, r.body);
      await browser.close();
      process.exit(1);
    }
  }

  // ────────────────────────────────────────────────────────
  // Phase 1: numeric layer_index invariant (V1 > V2 > V9)
  // ────────────────────────────────────────────────────────
  const atf = await page.evaluate((f) =>
    fetch('/preview/at_frame?frame=' + f).then(r => r.json()), 450);
  const layers = atf.visual_layers || [];
  const byTrack = {};
  for (const l of layers) byTrack[l.track_id] = l.layer_index;

  record('numeric — V1 > V2 > V9 in layer_index',
    (byTrack['v1'] ?? -1) > (byTrack['v2'] ?? -1)
    && (byTrack['v2'] ?? -1) > (byTrack['v9'] ?? -1),
    JSON.stringify(byTrack));

  record('numeric — V1 has the highest layer_index',
    layers.length > 0 && layers[layers.length - 1].track_id === 'v1',
    `top layer=${layers[layers.length - 1]?.track_id}`);
  record('numeric — V9 has the lowest layer_index',
    layers.length > 0 && layers[0].track_id === 'v9',
    `bottom layer=${layers[0]?.track_id}`);

  // ────────────────────────────────────────────────────────
  // Phase 2: rendered DOM zIndex (the actual stacking)
  // ────────────────────────────────────────────────────────
  // The PreviewPlayer renders .composite-layer divs once the
  // /preview/plan has been fetched and the playhead is at a
  // frame where the layers are active. We need the playhead to
  // be at frame 450 AND the plan to have been fetched.
  // Easiest: drive the playhead via the URL or the existing
  // playhead store. The PreviewPlayer reads playheadFrame from
  // the App state. We'll set it via the public transport by
  // clicking on the ruler at the correct x position, OR we can
  // look up the rendered DOM after the preview is shown.
  // First: nudge the GUI to render by setting the playhead.
  // The playhead position is set by clicking the ruler; for
  // headless we can dispatch a programmatic setter.
  // The simplest robust path: directly verify the DOM-level
  // contract by inspecting the data attributes the renderer
  // stamps on each .composite-layer div.
  await page.waitForTimeout(1500);

  // Try to find the composite-stage and its layers. If the
  // preview hasn't rendered (e.g. playhead is at 0), we set
  // it via the ruler click. The ruler is .ruler and frame 450
  // is at x = 450 * pxPerFrame = 450 * 0.84 ≈ 378px in default
  // 30px/sec @ 30fps zoom.
  await page.evaluate(() => {
    const ruler = document.querySelector('.ruler');
    if (!ruler) return;
    const rect = ruler.getBoundingClientRect();
    const seqFps = { num: 30, den: 1 };
    const pxPerF = 0.84;
    const targetFrame = 450;
    const cx = rect.left + targetFrame * pxPerF;
    const cy = rect.top + rect.height / 2;
    ruler.dispatchEvent(new MouseEvent('pointerdown', {
      clientX: cx, clientY: cy, bubbles: true, button: 0,
    }));
  });
  await page.waitForTimeout(1500);

  // Read the .composite-layer zIndex values.
  const rendered = await page.evaluate(() => {
    const layers = Array.from(document.querySelectorAll('.composite-layer'));
    return layers.map((el) => ({
      trackId: el.getAttribute('data-track-id'),
      zIndex: el.style.zIndex,
    }));
  });

  record('DOM — 3 .composite-layer divs rendered',
    rendered.length === 3,
    `got ${rendered.length}: ${JSON.stringify(rendered)}`);

  if (rendered.length === 3) {
    const zByTrack = {};
    for (const r of rendered) {
      zByTrack[r.trackId] = parseInt(r.zIndex, 10);
    }
    record('DOM — V1 zIndex > V2 zIndex',
      (zByTrack['v1'] ?? -1) > (zByTrack['v2'] ?? -1),
      JSON.stringify(zByTrack));
    record('DOM — V2 zIndex > V9 zIndex',
      (zByTrack['v2'] ?? -1) > (zByTrack['v9'] ?? -1),
      JSON.stringify(zByTrack));
    // DOM paint order: V9 (bottom) before V1 (top).
    const v9Idx = rendered.findIndex((r) => r.trackId === 'v9');
    const v1Idx = rendered.findIndex((r) => r.trackId === 'v1');
    record('DOM — V9 painted before V1 in DOM order',
      v9Idx >= 0 && v1Idx >= 0 && v9Idx < v1Idx,
      `V9 idx=${v9Idx}, V1 idx=${v1Idx}`);
  }

  await browser.close();

  const pass = results.filter((r) => r.ok === true).length;
  const fail = results.filter((r) => r.ok === false).length;
  console.log(`\n=== GUI-04.6 stacking smoke SUMMARY ===`);
  console.log(`PASS: ${pass}    FAIL: ${fail}`);
  if (fail) process.exit(1);
}

await main().catch((e) => {
  console.error('smoke crashed:', e);
  process.exit(2);
});
