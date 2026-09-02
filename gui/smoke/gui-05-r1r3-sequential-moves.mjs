// gui/smoke/gui-05-r1r3-sequential-moves.mjs
//
// GUI-05-R1-R3 — Sequential Same-Clip Move Consistency
//
// Human acceptance of GUI-05-R1-R2 found a NEW critical failure:
//   A → B (success)
//   B → C (rejection)
//   C → A   ← BUG: should be C(rejected) → B
//
// Expected on rejection:
//   B → C(rejected) → B
//
// This smoke performs sequential moves A→B, B→C, C→D, D→E on the SAME
// clip without page reload, and captures the FULL state chain at each
// step:
//
// === POINTERDOWN ===
//   - clipId
//   - trackId
//   - Core committed start frame at pointerdown (server /project)
//   - rendered/displayed start frame at pointerdown (el.style.left)
//   - project revision (operations length)
//   - drag origin frame stored by GUI (el.style.left = displayProject frame)
//   - relationship graph version (project.relationships length)
//
// === POINTERUP ===
//   - pointer target frame
//   - target track (hit-test result)
//   - attempted frame (committedFrame computed in ClipBlock)
//   - project revision sent as baseRevision (last /operations length)
//   - dragPreview frame (after pointermove)
//   - current rendered frame
//
// === MUTATION RESPONSE ===
//   - HTTP result (status code)
//   - server revision before mutation
//   - server revision after mutation
//   - final Core clip frame
//   - exact rejection reason if rejected
//
// === GUI RECONCILIATION ===
//   - frame before refresh (displayProject reads project + dragPreview)
//   - frame returned by refresh
//   - frame after clearing dragPreview (after 700ms)
//   - rejection origin frame (first-gesture origin A vs current committed B)
//   - final displayed frame
//
// Requires:
//   - python -m yroll.cli.main serve projects/_sanlihe-clean-work --port 8770
//   - frontend served on 5180
//   - chromium --remote-debugging-port=9222

import { chromium } from '../../gui/node_modules/playwright/index.mjs';

const FRONTEND = 'http://127.0.0.1:5180/';

const results = [];
function record(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log(`${ok ? '✓ PASS' : '✗ FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
}

async function resetClipToFrame(page, cid, sid, frame) {
  const ok = await page.evaluate(async ({ cid, sid, frame }) => {
    const opsBefore = (await fetch('/operations').then(r => r.json()).catch(() => [])).length;
    const proj = await fetch('/project').then(r => r.json());
    const fps = proj.fps_num || 30;
    const qs = new URLSearchParams({
      sessionId: sid,
      baseRevision: String(opsBefore),
    });
    const r = await fetch(`/clips/${cid}/move?${qs}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        new_timeline_start_frame: frame,
        why: 'gui-05-r1r3 smoke: reset',
      }),
    });
    return { status: r.status, body: await r.text() };
  }, { cid, sid, frame });
  if (ok.status !== 200) {
    console.log(`    reset to ${frame} returned ${ok.status}: ${ok.body}`);
  }
  await page.waitForTimeout(300);
}

async function clipRect(page, cid) {
  return await page.evaluate((c) => {
    const el = document.querySelector(`[data-clip-id="${c}"]`);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {
      x: r.left + r.width / 2,
      y: r.top + (r.height * 3) / 4,
    };
  }, cid);
}

async function getCoreState(page, cid) {
  return await page.evaluate(async (c) => {
    const p = await fetch('/project').then(r => r.json());
    const ops = await fetch('/operations').then(r => r.json()).catch(() => []);
    const clip = p.clips?.[c];
    return {
      start: clip?.timeline_range?.start ?? null,
      end: clip?.timeline_range?.end ?? null,
      track: clip?.track_id ?? null,
      revision: Array.isArray(ops) ? ops.length : 0,
      relationships: Array.isArray(p.relationships) ? p.relationships.length : 0,
      pxPerSec: p.fps_num || 30,  // approximation; pxPerSec isn't directly in /project
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

async function getUiSession(page) {
  return await page.evaluate(() => fetch('/ui/status').then(r => r.json()).catch(() => null));
}

/**
 * Perform a single drag gesture with full trace capture.
 * Returns a structured trace object that includes:
 *   pointerdown, pointerup, mutation, reconciliation.
 *
 * The trace drag is uses small dx to stay within a gap of ~3-5 seconds
 * (each move is ~10 frames at 30fps). We use a fixed dx of 50px
 * (≈ 5 frames at default zoom).
 */
async function performDragWithTrace(page, cid, sid, dragIdx, expectedTargetFrame) {
  const trace = {
    dragIdx,
    expectedTargetFrame,
    pointerdown: {},
    pointerup: {},
    mutation: {},
    reconciliation: {},
  };

  // ---- POINTERDOWN state ----
  const coreAtDown = await getCoreState(page, cid);
  const renderedAtDown = await getRenderedFrame(page, cid);
  trace.pointerdown = {
    clipId: cid,
    trackId: coreAtDown.track,
    coreCommittedStartFrame: Math.round((coreAtDown.start ?? 0) * 30),  // assume 30fps
    renderedStartFrame: renderedAtDown,
    projectRevision: coreAtDown.revision,
    relationshipsCount: coreAtDown.relationships,
    dragOriginStoredByGui: renderedAtDown,  // ClipBlock captures tlStartFrame at pointerdown
  };

  // Install per-frame style.left poller BEFORE pointerdown.
  await page.evaluate((c) => {
    const el = document.querySelector(`[data-clip-id="${c}"]`);
    if (!el) return;
    window.__yrollR3PollerSamples = [];
    window.__yrollR3PollerStart = performance.now();
    window.__yrollR3PollerStopped = false;
    const tick = () => {
      if (window.__yrollR3PollerStopped) return;
      window.__yrollR3PollerSamples.push({
        leftPx: el.style.left,
        ts: performance.now() - window.__yrollR3PollerStart,
      });
      window.__yrollR3PollerTimer = setTimeout(tick, 16);
    };
    window.__yrollR3PollerTimer = setTimeout(tick, 16);
  }, cid);

  // Snapshot baseRevision BEFORE drag (what the next mutation will send).
  const baseRevAtDragStart = await page.evaluate(() => fetch('/operations').then(r => r.json()).then(o => o.length));

  // Drag (50px right).
  const rect = await clipRect(page, cid);
  if (!rect) {
    trace.error = 'no clip rect';
    return trace;
  }

  await page.mouse.move(rect.x, rect.y);
  await page.mouse.down();
  await page.waitForTimeout(100);
  const dx = 50;
  const steps = 20;
  for (let i = 1; i <= steps; i++) {
    const t = i / steps;
    await page.mouse.move(rect.x + dx * t, rect.y, { steps: 1 });
    await page.waitForTimeout(15);
  }

  // Release pointer FIRST so the up() handler fires and logs dragUpLog.
  await page.mouse.up();
  // Brief wait for the up event to propagate.
  await page.waitForTimeout(50);

  // ---- POINTERUP state ----
  const dragUpLog = await page.evaluate(() => {
    const log = Array.isArray(window.__yrollDragLog) ? window.__yrollDragLog : [];
    for (let i = log.length - 1; i >= 0; i--) {
      if (log[i].kind === 'up') return log[i];
    }
    return null;
  });
  trace.pointerup = {
    attemptedFrame: dragUpLog?.committedFrame ?? null,
    originFrame: dragUpLog?.originFrame ?? null,
    targetTrackId: dragUpLog?.hitTrackId ?? null,
    committedTrackId: dragUpLog?.committedTrackId ?? null,
    willMutate: dragUpLog?.willMutate ?? null,
    pointerClientX: dragUpLog?.pointerClientX ?? null,
    pointerClientY: dragUpLog?.pointerClientY ?? null,
    siblingsAtPointerdown: dragUpLog?.siblingsAtPointerdown ?? null,
    hitTestStack: dragUpLog?.hitTestStack ?? null,
    baseRevisionSent: baseRevAtDragStart,
  };

  // ---- MUTATION RESPONSE ----
  // Wait for mutation to complete (success or rejection).
  await page.waitForTimeout(200);
  const coreAfterMutation = await getCoreState(page, cid);
  const mutationTrace = await page.evaluate(() => {
    const trace = Array.isArray(window.__yrollDragTrace) ? window.__yrollDragTrace : [];
    return trace.length > 0 ? trace[trace.length - 1] : null;
  });
  trace.mutation = {
    httpResult: mutationTrace?.mutationSucceeded === true ? '200' : (mutationTrace?.mutationSucceeded === false ? 'rejected' : 'unknown'),
    baseRevisionBefore: mutationTrace?.baseRevisionBefore ?? null,
    baseRevisionAfter: mutationTrace?.baseRevisionAfter ?? null,
    coreFrameAfter: Math.round((coreAfterMutation.start ?? 0) * 30),
    serverRevisionBefore: baseRevAtDragStart,
    serverRevisionAfter: coreAfterMutation.revision,
    rejectionReason: mutationTrace?.mutationError ?? null,
  };

  // ---- GUI RECONCILIATION ----
  // Wait for dragPreview to clear (600ms in rejection, immediate in success).
  await page.waitForTimeout(800);
  const finalRenderedFrame = await getRenderedFrame(page, cid);
  const finalCoreState = await getCoreState(page, cid);

  // Stop poller and get sample summary.
  await page.evaluate(() => {
    window.__yrollR3PollerStopped = true;
    if (window.__yrollR3PollerTimer) clearTimeout(window.__yrollR3PollerTimer);
  });
  const samples = await page.evaluate(() => window.__yrollR3PollerSamples || []);

  // Find the pointerup timestamp to split samples.
  const pointerUpTs = await page.evaluate(() => {
    const log = Array.isArray(window.__yrollDragLog) ? window.__yrollDragLog : [];
    for (let i = log.length - 1; i >= 0; i--) {
      if (log[i].kind === 'up') return log[i].ts;
    }
    return null;
  });
  const pointerUpTsRel = pointerUpTs != null
    ? (samples.find(s => s.ts >= pointerUpTs)?.ts ?? 0)
    : 0;
  const postUpSamples = samples.filter(s => s.ts >= pointerUpTsRel);
  const distinctPostUpValues = new Set(postUpSamples.map(s => s.leftPx));

  trace.reconciliation = {
    frameBeforeDragPreview: renderedAtDown,
    finalRenderedFrame,
    finalCoreStartFrame: Math.round((finalCoreState.start ?? 0) * 30),
    finalCoreRevision: finalCoreState.revision,
    finalRelationshipsCount: finalCoreState.relationships,
    sampleCount: samples.length,
    postUpSampleCount: postUpSamples.length,
    distinctPostUpLeftPxCount: distinctPostUpValues.size,
    distinctPostUpLeftPxValues: Array.from(distinctPostUpValues),
  };

  return trace;
}

async function setupFreshFixture(page, sid) {
  // Find an existing video clip, delete its siblings on v1, then position
  // the test clip at a known place (frame 0) and add an obstacle at
  // a known position that will cause the SECOND move to fail.
  // We need: clip at (0, 50), empty (50, 100), obstacle at (100, 200),
  // empty (200, ∞). Move sequence: (0,50) -> (50,100) -> (100,150) [FAIL].
  // After FAIL: clip should be at (50,100), NOT (0,50).

  return await page.evaluate(async (sid) => {
    const proj = await fetch('/project').then(r => r.json());
    const tl = proj.timelines?.[Object.keys(proj.timelines)[0]];
    if (!tl) return { error: 'no timeline' };
    const v = tl.tracks.find(t => t.kind === 'video' && !t.hidden);
    if (!v) return { error: 'no video track' };

    // We won't delete existing clips (too risky). Instead, we'll find
    // a clip with >100 frames of empty space AFTER it, reset it to frame 0,
    // and then move it sequentially.

    // Find the latest-positioned clip on v1 with enough room after it.
    const sorted = v.clip_ids
      .map(cid => proj.clips[cid])
      .filter(c => c)
      .sort((a, b) => a.timeline_range.start - b.timeline_range.start);
    // Pick the LAST clip (most space after it before any sibling).
    const last = sorted[sorted.length - 1];
    if (!last) return { error: 'no clip on v1' };
    return { clipId: last.clip_id, initialStart: last.timeline_range.start };
  }, sid);
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
  });
  // Initialize __yrollDragTrace array (App.tsx instrumentation only
  // pushes to it if it already exists).
  await page.evaluate(() => {
    window.__yrollDragTrace = [];
  });
  await page.reload({ waitUntil: 'networkidle', timeout: 30000 });
  await page.evaluate(() => {
    window.__yrollDragTrace = [];
  });
  await page.waitForSelector('.timeline-content', { timeout: 15000 });
  await page.waitForTimeout(2000);

  console.log('=== Setup: acquire lease + pick movable clip ===');
  const setup = await page.evaluate(async () => {
    const proj = await fetch('/project').then(r => r.json());
    const uiStatus = await fetch('/ui/status').then(r => r.json()).catch(() => null);
    let sessionId = uiStatus?.session_id;
    let baseRevision = -1;
    if (!sessionId) {
      const acq = await fetch('/lease/acquire?actor=human&mode=edit&baseRevision=-1&humanLabel=gui-05-r1r3')
        .then(r => r.json()).catch(() => ({}));
      sessionId = acq.sessionId;
      baseRevision = acq.baseRevision ?? -1;
    } else {
      const ops = await fetch('/operations').then(r => r.json()).catch(() => []);
      baseRevision = Array.isArray(ops) ? ops.length : -1;
    }
    // Pick first clip with >30s space (enough for 5 moves of ~5 frames each).
    const v = proj.timeline.tracks.find(t => t.kind === 'video' && !t.hidden);
    if (!v || !v.clip_ids?.length) return null;
    const sorted = v.clip_ids
      .map(cid => proj.clips[cid])
      .filter(c => c)
      .sort((a, b) => a.timeline_range.start - b.timeline_range.start);
    let chosen = null;
    for (const c of sorted) {
      const idx = sorted.indexOf(c);
      const next = sorted[idx + 1];
      const gap = next ? (next.timeline_range.start - c.timeline_range.end) : 60;
      if (gap > 30) {
        chosen = c;
        break;
      }
    }
    if (!chosen) chosen = sorted[0];
    return {
      sessionId,
      baseRevision,
      clipId: chosen.clip_id,
      initialStart: chosen.timeline_range.start,
      initialEnd: chosen.timeline_range.end,
    };
  });

  if (!setup) {
    record('Setup', false, 'no clip found');
    await browser.close();
    process.exit(1);
  }
  console.log(`  session=${setup.sessionId.slice(0, 8)}…`);
  console.log(`  cid=${setup.clipId}`);
  console.log(`  initial: [${setup.initialStart.toFixed(2)}s, ${setup.initialEnd.toFixed(2)}s]`);

  // Find an unobstructed area to drag into. We'll use the end of the
  // timeline (no obstacles after the last clip). The clip can be dragged
  // forward freely.
  const clipEndFrame = Math.round(setup.initialEnd * 30);
  console.log(`  clipEndFrame: ${clipEndFrame}f`);
  // Drag the clip forward 3 times: +50, +50, +50 frames. The third
  // attempt will FAIL because it pushes past project_max_frame (the
  // server safety bound). Each move is +50 frames (≈ 16-18 frames at
  // 30fps, ~9 px at default zoom).
  //
  // Actually, simpler: use larger gaps so moves don't get clamped.
  // We'll use +10 frames per move and the rejection will come from
  // the explicit bound check at /clips/{id}/move.
  //
  // To force a rejection deterministically: pick a target that's BEYOND
  // project_max_frame. The server rejects with 400.
  const maxFrameResp = await page.evaluate(async () => {
    const p = await fetch('/project').then(r => r.json());
    return p.max_timeline_frame ?? null;
  });
  console.log(`  max_timeline_frame: ${maxFrameResp}f`);

  // Reset clip to a known starting position (far enough from origin
  // that move targets don't get clamped by local clamp due to other
  // siblings at the target area).
  // We'll move to a position where the target frame is BEYOND the
  // project max — this deterministically fails.
  await resetClipToFrame(page, setup.clipId, setup.sessionId, 0);

  // Verify reset took effect.
  const postReset = await getCoreState(page, setup.clipId);
  console.log(`  post-reset core: [${postReset.start.toFixed(2)}s, ${postReset.end.toFixed(2)}s] rev=${postReset.revision}`);
  if (postReset.start !== 0) {
    console.log(`  ⚠️ Reset FAILED — clip still at ${postReset.start}s.`);
  }

  // Sequential moves with deterministic outcomes:
  // Move 1: 0 → 30 (success — empty space ahead)
  // Move 2: 30 → 60 (success — empty space ahead)
  // Move 3: 60 → maxFrame+200 (FAIL — exceeds project max)
  // Move 4: (after failure) should remain at 60 (current), NOT 0 (original)
  const targetFrames = [30, 60, (maxFrameResp ?? 600) + 200, 90];
  const traces = [];
  for (let i = 0; i < targetFrames.length; i++) {
    console.log('');
    console.log(`=== Sequential move #${i + 1}: A→${String.fromCharCode(66 + i)} (target frame ${targetFrames[i]}) ===`);
    const trace = await performDragWithTrace(page, setup.clipId, setup.sessionId, i + 1, targetFrames[i]);
    traces.push(trace);
    console.log(`  POINTERDOWN: core=${trace.pointerdown.coreCommittedStartFrame}f, rendered=${trace.pointerdown.renderedStartFrame}, revision=${trace.pointerdown.projectRevision}`);
    console.log(`  POINTERUP:   attempt=${trace.pointerup.attemptedFrame}f, baseRev=${trace.pointerup.baseRevisionSent}, willMutate=${trace.pointerup.willMutate}, hitTrack=${trace.pointerup.targetTrackId}`);
    console.log(`  MUTATION:    ${trace.mutation.httpResult}, baseRev ${trace.mutation.baseRevisionBefore}→${trace.mutation.baseRevisionAfter}, coreAfter=${trace.mutation.coreFrameAfter}f, reason=${trace.mutation.rejectionReason}`);
    console.log(`  RECONCIL:    rendered=${trace.reconciliation.finalRenderedFrame}, coreFinal=${trace.reconciliation.finalCoreStartFrame}f, distinctLeftPx=${trace.reconciliation.distinctPostUpLeftPxCount}`);
  }

  // ===========================================================
  // ANALYSIS — verify the state chain invariant
  // ===========================================================
  console.log('');
  console.log('=== State chain analysis ===');

  let lastAcceptedFrame = 0;  // Initially at A (frame 0)
  let invariantViolated = false;

  for (let i = 0; i < traces.length; i++) {
    const t = traces[i];
    const mutationOk = t.mutation.httpResult === '200';
    const finalFramePx = t.reconciliation.finalRenderedFrame;
    const finalCoreFrame = t.reconciliation.finalCoreStartFrame;

    console.log(`Move #${i + 1}: mutation=${mutationOk ? 'success' : 'rejected'}, `
      + `finalCore=${finalCoreFrame}f (expected ${targetFrames[i]}f), `
      + `finalRendered=${finalFramePx}`);

    if (mutationOk) {
      // Successful move: Core should be at target. Final rendered should
      // match Core. Last accepted frame should be target.
      if (finalCoreFrame !== targetFrames[i]) {
        console.log(`  ✗ FAIL: successful move landed at ${finalCoreFrame}f, expected ${targetFrames[i]}f`);
        invariantViolated = true;
      }
      lastAcceptedFrame = targetFrames[i];
    } else {
      // Rejected move: Core should remain at lastAcceptedFrame (NOT A).
      // Final rendered should match Core (after dragPreview clears).
      if (finalCoreFrame !== lastAcceptedFrame) {
        console.log(`  ✗ FAIL: rejected move left Core at ${finalCoreFrame}f, `
          + `expected ${lastAcceptedFrame}f (immediately previous committed). `
          + `Returning to OLDER position!`);
        invariantViolated = true;
      } else {
        console.log(`  ✓ PASS: rejected move preserved Core at ${lastAcceptedFrame}f`);
      }
    }
  }

  // Final state assertion: if last move rejected, final core = last accepted.
  const finalTrace = traces[traces.length - 1];
  const lastMutationOk = finalTrace.mutation.httpResult === '200';
  const expectedFinalCore = lastMutationOk ? targetFrames[targetFrames.length - 1] : lastAcceptedFrame;
  if (finalTrace.reconciliation.finalCoreStartFrame !== expectedFinalCore) {
    console.log(`✗ Final state: Core at ${finalTrace.reconciliation.finalCoreStartFrame}f, expected ${expectedFinalCore}f`);
    invariantViolated = true;
  }

  // ===========================================================
  // Output the full traces (for analysis)
  // ===========================================================
  console.log('');
  console.log('=== Full traces (JSON) ===');
  console.log(JSON.stringify(traces, null, 2));

  record(
    'R1-R3 state chain invariant (A→B→C→D→E never returns to older position)',
    !invariantViolated,
    `traces=${traces.length}, lastAcceptedFrame=${lastAcceptedFrame}, finalCore=${finalTrace.reconciliation.finalCoreStartFrame}f`,
  );

  await browser.close();

  const passed = results.filter(r => r.ok).length;
  const failed = results.filter(r => !r.ok).length;
  console.log('');
  console.log(`=== R1-R3 SUMMARY: ${passed}/${results.length} passed ===`);
  if (failed > 0) {
    console.log('FAILURES:');
    for (const r of results.filter(r => !r.ok)) {
      console.log(`  - ${r.name}: ${r.detail ?? ''}`);
    }
    process.exit(1);
  }
}

await main().catch((e) => {
  console.error('gui-05-r1r3 smoke crashed:', e);
  process.exit(2);
});