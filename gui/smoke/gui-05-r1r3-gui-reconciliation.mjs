// gui/smoke/gui-05-r1r3-gui-reconciliation.mjs
//
// GUI-05-R1-R3 — Sequential Same-Clip Move: GUI reconciliation focus.
//
// R1-R3 Core-level tests (tests/test_r1r3_state_chain.py) confirm the
// Core's state chain invariant is correct: after a rejected move,
// Core remains at the IMMEDIATELY PREVIOUS committed position.
//
// But the user observes the GUI showing A (origin) after the second
// move's rejection. Since Core is correct, the bug MUST be in the
// GUI's reconciliation layer (dragPreview lifecycle / refresh).
//
// This smoke exercises the FULL GUI drag pipeline to reproduce the
// reported "A → B → C → A" sequence:
//
//   1. Clean v1 of all clips except one (delete via API)
//   2. Move the test clip to frame 0 via API
//   3. Reload the page (so GUI picks up clean state)
//   4. Drag 1: 0 → +30 frames (success)
//   5. Drag 2: 30 → +30 frames (success — should be 60)
//   6. Drag 3: 60 → MAX_FRAME+200 (rejected — server max_frame guard)
//   7. Observe GUI's rendered position after each drag
//
// Expected:
//   After Drag 1 (success): GUI = +30, Core = +30
//   After Drag 2 (success): GUI = +60, Core = +60
//   After Drag 3 (rejected): GUI = +60 (immediately previous), Core = +60
//
// BUG (user's observation): After Drag 3, GUI shows 0 (origin).

import { chromium } from '../../gui/node_modules/playwright/index.mjs';

const FRONTEND = 'http://127.0.0.1:5180/';

const results = [];
function record(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log(`${ok ? '✓ PASS' : '✗ FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
}

async function getCoreState(page, cid) {
  return await page.evaluate(async (c) => {
    const p = await fetch('/project').then(r => r.json());
    const ops = await fetch('/operations').then(r => r.json()).catch(() => []);
    const clip = p.clips?.[c];
    return {
      start: clip?.timeline_range?.start ?? null,
      end: clip?.timeline_range?.end ?? null,
      revision: Array.isArray(ops) ? ops.length : 0,
      fps: p.fps_num || 30,
    };
  }, cid);
}

async function getRenderedFrame(page, cid) {
  return await page.evaluate((c) => {
    const el = document.querySelector(`[data-clip-id="${c}"]`);
    if (!el) return null;
    return el.style.left;
  }, cid);
}

async function getPxPerFrame(page) {
  // pxPerFrame is NOT exposed via /project directly. Read from a clip's
  // current position vs its rendered pixel position.
  return await page.evaluate(async () => {
    const p = await fetch('/project').then(r => r.json());
    const c = Object.values(p.clips)[0];
    if (!c) return 1;
    const fps = p.fps_num || 30;
    const startFrame = Math.round(c.timeline_range.start * fps);
    const el = document.querySelector(`[data-clip-id="${c.clip_id}"]`);
    if (!el) return 1;
    const renderedPx = parseFloat(el.style.left);
    if (startFrame === 0) return 1;
    return renderedPx / startFrame;
  });
}

async function resetClip(page, cid, sid, frame) {
  await page.evaluate(async ({ cid, sid, frame }) => {
    const ops = (await fetch('/operations').then(r => r.json()).catch(() => [])).length;
    const proj = await fetch('/project').then(r => r.json());
    const fps = proj.fps_num || 30;
    const qs = new URLSearchParams({
      sessionId: sid,
      baseRevision: String(ops),
    });
    return fetch(`/clips/${cid}/move?${qs}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        new_timeline_start_frame: frame,
        why: 'r1r3 reset',
      }),
    });
  }, { cid, sid, frame });
  await page.waitForTimeout(300);
}

async function deleteClip(page, cid, sid) {
  await page.evaluate(async ({ cid, sid }) => {
    const ops = (await fetch('/operations').then(r => r.json()).catch(() => [])).length;
    const qs = new URLSearchParams({
      sessionId: sid,
      baseRevision: String(ops),
    });
    return fetch(`/clips/${cid}?${qs}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ why: 'r1r3 cleanup' }),
    });
  }, { cid, sid });
  await page.waitForTimeout(200);
}

async function performDrag(page, cid, dx) {
  const rect = await page.evaluate((c) => {
    const el = document.querySelector(`[data-clip-id="${c}"]`);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + (r.height * 3) / 4 };
  }, cid);
  if (!rect) return null;
  await page.mouse.move(rect.x, rect.y);
  await page.mouse.down();
  await page.waitForTimeout(80);
  const steps = 10;
  for (let i = 1; i <= steps; i++) {
    const t = i / steps;
    await page.mouse.move(rect.x + dx * t, rect.y, { steps: 1 });
    await page.waitForTimeout(15);
  }
  await page.mouse.up();
}

async function main() {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const ctx = browser.contexts()[0] || await browser.newContext();
  const page = ctx.pages()[0] || await ctx.newPage();

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(FRONTEND + '?cb=' + Date.now(), { waitUntil: 'networkidle', timeout: 30000 });
  await page.evaluate(async () => {
    if ('serviceWorker' in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map(r => r.unregister()));
    }
    if (window.caches) {
      const keys = await caches.keys();
      await Promise.all(keys.map(k => caches.delete(k)));
    }
    window.__yrollDragTrace = [];
  });
  await page.reload({ waitUntil: 'networkidle', timeout: 30000 });
  await page.evaluate(() => { window.__yrollDragTrace = []; });
  await page.waitForSelector('.timeline-content', { timeout: 15000 });
  await page.waitForTimeout(2000);

  // ---- Setup ----
  const setup = await page.evaluate(async () => {
    const proj = await fetch('/project').then(r => r.json());
    const ui = await fetch('/ui/status').then(r => r.json()).catch(() => null);
    const sid = ui?.session_id;
    const ops = await fetch('/operations').then(r => r.json()).catch(() => []);
    const br = Array.isArray(ops) ? ops.length : 0;
    const v = proj.timeline.tracks.find(t => t.kind === 'video' && !t.hidden);
    if (!v) return { error: 'no visible video track' };
    // Text track may have been deleted by prior smoke runs. Don't fail
    // if missing — just set to null and skip text cleanup.
    const t = proj.timeline.tracks.find(t => t.kind === 'text');
    return {
      sid, br,
      fps: proj.fps_num || 30,
      v1: v.track_id,
      v1Clips: v.clip_ids || [],
      t1: t?.track_id ?? null,
      t1Clips: t?.clip_ids || [],
    };
  });

  if (setup.error) {
    record('Setup', false, setup.error);
    await browser.close();
    process.exit(1);
  }

  // Clean up v1 (and t1 if present): delete all clips except keep the
  // first v1 clip for our test. Pick the first v1 clip as the test
  // target.
  const testCid = setup.v1Clips[0];
  if (!testCid) {
    record('Setup', false, 'no v1 clip');
    await browser.close();
    process.exit(1);
  }
  const otherV1 = setup.v1Clips.slice(1);
  const allT1 = setup.t1Clips;
  for (const cid of [...otherV1, ...allT1]) {
    await deleteClip(page, cid, setup.sid);
  }
  // Move test clip to frame 0
  await resetClip(page, testCid, setup.sid, 0);

  // Also add a SAME-TRACK sibling (D: video at [10s, 15s] = frames
// [300, 450]) so we can trigger a Core-level rejection (Case C)
// without depending on project_max bound. We add it via API.
  const siblingResp = await page.evaluate(async ({ sid, v1 }) => {
    const ops = (await fetch('/operations').then(r => r.json()).catch(() => [])).length;
    const qs = new URLSearchParams({
      sessionId: sid,
      baseRevision: String(ops),
    });
    return fetch(`/clips?${qs}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        asset_id: '',
        source_start_frame: 0,
        source_end_frame: 150,
        timeline_start_frame: 300,
        track_id: v1,
        why: 'r1r3 sibling',
      }),
    });
  }, { sid: setup.sid, v1: setup.v1 });
  console.log(`  sibling add: ${siblingResp.status}`);

  await page.waitForTimeout(500);
  await page.reload({ waitUntil: 'networkidle', timeout: 30000 });
  await page.evaluate(() => { window.__yrollDragTrace = []; });
  await page.waitForTimeout(2000);

  console.log(`=== Setup: test clip ${testCid} at frame 0 + sibling at frame 300 ===`);
  console.log(`  v1 cleaned of ${otherV1.length} other clips, t1 cleaned of ${allT1.length} clips`);

  // Get pixel-per-frame ratio for converting frames to drag distance.
  // Move test clip to frame 0 (ensure reset took effect).
  const core0 = await getCoreState(page, testCid);
  console.log(`  post-reset core: start=${core0.start}s, end=${core0.end}s, rev=${core0.revision}`);

  const pxPerFrame = await getPxPerFrame(page);
  console.log(`  pxPerFrame: ${pxPerFrame}`);

  // Determine max_frame from project (server's project_max_frame).
  // project.max_timeline_frame is not exposed via /project. Instead,
  // we'll use a forced-rejection by going far enough that the server
  // hits its internal bound. We can use any value beyond all existing
  // content extent. Project's effective max is the maximum of all
  // existing content's end. Test clip length is fps*60 = 1800 frames.
  // We pick a target that's beyond the project's existing max.
  const projectMax = await page.evaluate(async () => {
    const p = await fetch('/project').then(r => r.json());
    let max = 0;
    for (const c of Object.values(p.clips || {})) {
      if (c.timeline_range.end > max) max = c.timeline_range.end;
    }
    return max;
  });
  const rejectTargetFrame = Math.ceil(projectMax * (setup.fps || 30)) + 500;
  console.log(`  projectMax: ${projectMax}s, rejectTargetFrame: ${rejectTargetFrame}f`);

  // Drag 1: 0 → 30 frames. We use a generous dx to ensure the move
  // commits regardless of zoom. At max zoom (120 px/sec), 30 frames
  // = 30 * 4 = 120px. Use 120px to be safe.
  const drag1Frames = 30;
  const drag1Dx = 120;  // px (works at any zoom)
  console.log(`\n=== Drag 1: 0 → +${drag1Frames} frames (dx=${drag1Dx}px) ===`);
  const pre1 = { core: await getCoreState(page, testCid), rendered: await getRenderedFrame(page, testCid) };
  console.log(`  PRE: core=${pre1.core.start}s, rendered=${pre1.rendered}`);
  await performDrag(page, testCid, drag1Dx);
  await page.waitForTimeout(800);  // wait for refresh + dragPreview clear
  const post1 = { core: await getCoreState(page, testCid), rendered: await getRenderedFrame(page, testCid) };
  console.log(`  POST: core=${post1.core.start}s, rendered=${post1.rendered}`);
  const expected1 = drag1Frames / (setup.fps || 30);
  record(
    'Drag 1 (success): Core moves to target',
    Math.abs(post1.core.start - expected1) < 0.5,  // loose tolerance: local clamp may reduce
    `expected ~${expected1}s, got ${post1.core.start}s (any forward move is OK)`,
  );
  record(
    'Drag 1 (success): Core moved forward (not stuck at origin)',
    post1.core.start > pre1.core.start,
    `pre=${pre1.core.start}s, post=${post1.core.start}s`,
  );

  // Drag 2: from post1 position → +30 frames
  const drag2Frames = 30;
  const drag2Dx = 120;
  console.log(`\n=== Drag 2: post1 → +${drag2Frames} frames (dx=${drag2Dx}px) ===`);
  const pre2 = { core: await getCoreState(page, testCid), rendered: await getRenderedFrame(page, testCid) };
  console.log(`  PRE: core=${pre2.core.start}s, rendered=${pre2.rendered}`);
  await performDrag(page, testCid, drag2Dx);
  await page.waitForTimeout(800);
  const post2 = { core: await getCoreState(page, testCid), rendered: await getRenderedFrame(page, testCid) };
  console.log(`  POST: core=${post2.core.start}s, rendered=${post2.rendered}`);
  record(
    'Drag 2 (success): Core moved forward (relative to pre2)',
    post2.core.start > pre2.core.start,
    `pre=${pre2.core.start}s, post=${post2.core.start}s`,
  );
  // Pre2 was immediately previous committed position.
  const pre2Commited = pre2.core.start;

  // Drag 3: from post2 → drag far enough to collide with sibling D.
// The sibling is at frame 300 (= 10 seconds). Test clip A is currently
// at ~2s. To force collision: drag A to ~7s (frame 210). A's new range
// [210, 360]. Sibling D at [300, 450]. [210, 360) ∩ [300, 450) = [300, 360).
// COLLISION. Core rejects with Case C.
//
// Use a drag dx that's about (frame 300 - currentFrame) * pxPerFrame.
// Current frame after Drag 2: post2.core.start * fps (seconds → frames).
// At max zoom (120 px/sec), pxPerFrame = 4. 150 frames = 5s = 600px.
// We drag 600px to push it to ~7s.
  console.log(`\n=== Drag 3: post2 → drag into sibling (REJECTED by Case C) ===`);
  const pre3 = { core: await getCoreState(page, testCid), rendered: await getRenderedFrame(page, testCid) };
  console.log(`  PRE: core=${pre3.core.start}s, rendered=${pre3.rendered}`);
  const pre3Commited = pre3.core.start;
  // Drag 800px (way past sibling).
  await performDrag(page, testCid, 800);
  await page.waitForTimeout(800);
  const post3 = { core: await getCoreState(page, testCid), rendered: await getRenderedFrame(page, testCid) };
  console.log(`  POST: core=${post3.core.start}s, rendered=${post3.rendered}`);

  // Critical assertion: Core did NOT move (rejected, stays at immediately previous).
  record(
    'Drag 3 (rejected): Core did NOT advance beyond immediately previous position',
    Math.abs(post3.core.start - pre3Commited) < 0.1,
    `expected ${pre3Commited}s (immediately previous), got ${post3.core.start}s`,
  );

  // Critical assertion: rendered MUST NOT be at origin (frame 0).
  // If GUI shows origin (0), that's the A → B → C → A bug.
  const renderedPx = parseFloat(post3.rendered);
  const originPx = 0;  // frame 0 → 0 px
  record(
    'Drag 3 (rejected): GUI did NOT return to origin (A → B → C → A bug check)',
    Math.abs(renderedPx - originPx) > 1,
    `rendered=${post3.rendered}, origin would be 0px`,
  );

  // GUI rendered should match Core (after dragPreview clears).
  const fpsActual = setup.fps || 30;
  const expectedRenderedPx = pre3Commited * fpsActual * pxPerFrame;
  record(
    'Drag 3 (rejected): GUI rendered matches immediately previous Core position',
    Math.abs(renderedPx - expectedRenderedPx) < 5,
    `rendered=${renderedPx}, expected=${expectedRenderedPx}`,
  );

  await browser.close();

  const passed = results.filter(r => r.ok).length;
  const failed = results.filter(r => !r.ok).length;
  console.log('');
  console.log(`=== R1-R3 GUI RECONCILIATION SUMMARY: ${passed}/${results.length} passed ===`);
  if (failed > 0) {
    console.log('FAILURES:');
    for (const r of results.filter(r => !r.ok)) {
      console.log(`  - ${r.name}: ${r.detail ?? ''}`);
    }
    process.exit(1);
  }
}

await main().catch((e) => {
  console.error('gui-05-r1r3-gui-reconciliation smoke crashed:', e);
  process.exit(2);
});