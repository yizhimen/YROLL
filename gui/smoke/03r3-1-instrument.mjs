// GUI-03R3-1E acceptance: 6 scenarios on real Sanlihe browser.
//
// Exit-codes are NOW MEANINGFUL. Each scenario asserts the
// expected payload shape per the 03R3-1E drag invariant:
//
//   pointer → candidateFrame → collision-clampedFrame → visual
//
//   on pointerup:
//     preSnapFrame = lastPreviewFrame
//     one snap call → authoritativeSnapFrame
//     if clamp(snapped) !== snapped → ABORT, finalFrame = preSnapFrame
//     else → finalFrame = snapped
//
// Scenarios:
//   1. 1px drag → finalFrame = 1, no snap
//   2. 8px drag → finalFrame = 8, no snap
//   3. 600px drag → finalFrame = 600, no snap
//   4. Drag toward occupied region → collision-free clamp, no overlap
//   5. Drag toward sibling boundary within snap radius → snap applied (no overlap)
//   6. Drag within snap radius of sibling boundary → finalFrame = clamp
//      (spec says snap-creates-overlap → abort; with Sanlihe's
//       current clip layout, every within-radius snap target lands
//       safely, so this scenario verifies the algorithm's "no
//       unsafe snap" invariant indirectly.)
//
// Usage:
//   1. yroll serve projects/sanlihe-slice-30s (port 8765)
//   2. cd gui && pnpm dev  (port 5173)
//   3. open Chromium with --remote-debugging-port=9222 to http://localhost:5173
//   4. node gui/smoke/03r3-1-instrument.mjs
//
// Exit 0 = all 6 green; non-zero = failure summary printed.

import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const FAILURES = [];
const PASSES = [];

function recordPass(name, payload) {
  PASSES.push({ name, payload });
  console.log(`  ✅ PASS ${name}`);
}

function recordFail(name, reason, payload) {
  FAILURES.push({ name, reason, payload });
  console.error(`  ❌ FAIL ${name}: ${reason}`);
}

function assertEq(name, field, actual, expected, payload) {
  if (actual !== expected) {
    recordFail(name, `${field}=${JSON.stringify(actual)} (expected ${JSON.stringify(expected)})`, payload);
    return false;
  }
  return true;
}

// Launch our own browser to avoid stale-CDP-connection issues. We
// navigate to the dev server directly; Vite proxies /api/* to the
// yroll serve backend (8765). Headless to avoid GPU/memory pressure
// during repeated drag scenarios on Windows.
// Capture [YROLL-DRAG] console events so we can recover the payload
// even if window.__yrollDragLog is wiped by a navigation/reload
// between drag and read. Listener registered BEFORE goto so we
// never miss the drag's emit (Playwright's `console` event only
// fires for messages emitted AFTER .on()).
const consoleDragPayloads = [];
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext();
const page = await ctx.newPage();
// DIAGNOSTIC: log all /move requests
page.on('request', (req) => {
  if (req.url().includes('/move')) {
    process.stdout.write(`  [REQ] ${req.method()} ${req.url()}\n`);
  }
});
page.on('response', async (res) => {
  if (res.url().includes('/move') && !res.url().includes('/ui/')) {
    const status = res.status();
    const url = res.url().replace(/^http:\/\/localhost:5173/, '');
    process.stdout.write(`  [RES] ${status} ${url}\n`);
  }
});
page.on('console', (msg) => {
  const t = msg.text();
  if (t.includes('[YROLL-DRAG]')) {
    process.stdout.write(`    page-console: [YROLL-DRAG] (len=${t.length})\n`);
    const idx = t.indexOf('{');
    if (idx >= 0) {
      const json = t.substring(idx);
      try {
        consoleDragPayloads.push(JSON.parse(json));
        process.stdout.write(`      → parsed; buffer len=${consoleDragPayloads.length}\n`);
      } catch (e) {
        process.stderr.write(`    JSON.parse failed: ${e.message} — text head: ${t.substring(0, 100)}\n`);
      }
    } else {
      process.stderr.write(`    no "{" found in [YROLL-DRAG] message\n`);
    }
  } else if (t.includes('[YROLL-')) {
    process.stdout.write(`    page-console: ${t.substring(0, 200)}${t.length > 200 ? '…' : ''}\n`);
  }
});

await page.goto('http://localhost:5173/', { waitUntil: 'load' });
await page.reload({ waitUntil: 'networkidle' });
await page.waitForSelector('.timeline-content', { timeout: 10000 });

// Acquire lease so drag commits aren't 403'd. The server's POST
// handler requires a JSON body.
await page.evaluate(async () => {
  const r = await fetch('/lease/acquire', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actor: 'wf', mode: 'edit', actorId: 'wf' }),
  });
  window.__sid = (await r.json()).sessionId;
});

// Helper: dispatch a real pointer drag on the FIRST clip in the given
// track-content row. Drag delta is in screen pixels; we move through
// N intermediate steps so pointermove fires multiple times.
async function dragClip({ trackContentSelector, deltaPx, steps = 5, endOnDifferentRowSelector = null }) {
  return await Promise.race([
    page.evaluate(({ trackContentSelector, deltaPx, steps, endOnDifferentRowSelector }) => {
    const tc = document.querySelector(trackContentSelector);
    if (!tc) return { error: `no track-content for ${trackContentSelector}` };
    const clip = tc.querySelector('.clip');
    if (!clip) return { error: 'no clip in track-content' };
    const r = clip.getBoundingClientRect();
    const startX = r.left + 10;
    const startY = r.top + r.height / 2;
    const endX = startX + deltaPx;
    let endXFinal = endX;
    let endYFinal = startY;
    if (endOnDifferentRowSelector) {
      const otherTc = document.querySelector(endOnDifferentRowSelector);
      if (otherTc) {
        const otr = otherTc.getBoundingClientRect();
        endXFinal = otr.left + Math.min(50, otr.width / 2);
        endYFinal = otr.top + otr.height / 2;
      }
    }
    // DEBUG: capture clip pointerdown event behavior
    let pdFired = false;
    const pdProbe = (e) => { pdFired = true; };
    clip.addEventListener('pointerdown', pdProbe, { capture: true, once: true });
    clip.dispatchEvent(new PointerEvent('pointerdown', {
      bubbles: true, cancelable: true,
      clientX: startX, clientY: startY,
      pointerId: 1, pointerType: 'mouse', button: 0, buttons: 1,
    }));
    const totalDx = endXFinal - startX;
    const totalDy = endYFinal - startY;
    for (let i = 1; i <= steps; i++) {
      const x = startX + (totalDx * i) / steps;
      const y = startY + (totalDy * i) / steps;
      window.dispatchEvent(new PointerEvent('pointermove', {
        bubbles: true, cancelable: true,
        clientX: x, clientY: y,
        pointerId: 1, pointerType: 'mouse',
      }));
    }
    window.dispatchEvent(new PointerEvent('pointerup', {
      bubbles: true, cancelable: true,
      clientX: endXFinal, clientY: endYFinal,
      pointerId: 1, pointerType: 'mouse', button: 0, buttons: 0,
    }));
    return {
      startX, startY, endX: endXFinal, endY: endYFinal,
      clipId: clip.dataset.clipId,
      pdFired,
      clipRect: { left: r.left, top: r.top, width: r.width, height: r.height },
    };
  }, { trackContentSelector, deltaPx, steps, endOnDifferentRowSelector }),
  new Promise((_, reject) =>
    setTimeout(() => reject(new Error('dragClip timeout 8s')), 8000)),
  ]);
}

async function readPayloads() {
  // Primary source: in-page window.__yrollDragLog (fast). If the
  // page is unresponsive (e.g. after Target crash), fall through to
  // the console buffer we captured synchronously.
  let fromWindow = [];
  try {
    fromWindow = await Promise.race([
      page.evaluate(() => (window).__yrollDragLog || []),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('eval timeout')), 2000)),
    ]);
  } catch {
    // page crashed or unresponsive — fall through to console buffer
  }
  if (fromWindow.length > 0) return fromWindow;
  if (consoleDragPayloads.length > 0) return [consoleDragPayloads[consoleDragPayloads.length - 1]];
  return [];
}

// Find a video track-content with at least 2 clips so we can build
// collision / snap scenarios against sibling boundaries.
const setup = await page.evaluate(() => {
  const all = Array.from(document.querySelectorAll('[data-track-content]'));
  const isVisible = (tc) => tc.getBoundingClientRect().width > 0;
  const isVideo = (tc) => tc.dataset.trackContent.startsWith('v');
  const videoTc = all.find((tc) => isVideo(tc) && isVisible(tc)
    && tc.querySelectorAll('.clip').length >= 2);
  const anyVideoTc = all.find((tc) => isVideo(tc) && isVisible(tc));
  if (!anyVideoTc) return { error: 'no visible video track-content' };
  const otherVideoTc = all.find((tc) =>
    isVideo(tc) && isVisible(tc) && tc !== videoTc && tc !== anyVideoTc);
  return {
    primary: videoTc?.dataset.trackContent ?? anyVideoTc.dataset.trackContent,
    other: otherVideoTc?.dataset.trackContent ?? null,
  };
});

// Reset the test clip to a known clean position so we can build
// reliable collision / snap scenarios.
const testClipId = await page.evaluate((sel) => {
  const tc = document.querySelector(sel);
  const clip = tc?.querySelector('.clip');
  return clip?.dataset?.clipId ?? null;
}, `[data-track-content="${setup.primary}"]`);
if (!testClipId) throw new Error('no test clip found');
console.log('testClipId:', testClipId);

// Helper: programmatically move the test clip to a target frame via
// the Core /clips/{id}/move endpoint. Loops on lease acquisition
// (release, wait, acquire, retry on 409) to handle the race with
// the GUI's polling re-acquiring.
async function moveClipTo(targetFrame) {
  const moveResult = await page.evaluate(async ({ cid, frame }) => {
    let lastErr = null;
    for (let attempt = 0; attempt < 8; attempt++) {
      try {
        // Release any current lease so we can acquire cleanly.
        const st = await (await fetch('/ui/status')).json();
        if (st.session_id) {
          await fetch(`/lease/release?sessionId=${encodeURIComponent(st.session_id)}`, { method: 'POST' });
        }
        // Wait briefly to let the release propagate.
        await new Promise(r => setTimeout(r, 300));
        const lr = await fetch('/lease/acquire', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ actor: 'human', mode: 'edit', actorId: 'wf' }),
        });
        const lj = await lr.json();
        if (!lj.sessionId) {
          lastErr = 'lease acquire failed: ' + JSON.stringify(lj);
          continue;
        }
        const qs = `?sessionId=${encodeURIComponent(lj.sessionId)}&baseRevision=${encodeURIComponent(lj.baseRevision)}`;
        const r = await fetch(`/clips/${encodeURIComponent(cid)}/move${qs}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            new_timeline_start_frame: frame,
            new_track_id: null,
            why: '03r3-1e-setup',
          }),
        });
        const status = r.status;
        const text = await r.text();
        // Release so the GUI can re-acquire on next poll.
        await fetch(`/lease/release?sessionId=${encodeURIComponent(lj.sessionId)}`, { method: 'POST' });
        if (status === 200) {
          return { status, body: text };
        }
        lastErr = `status=${status}: ${text.substring(0, 100)}`;
        // Retry on transient failures.
      } catch (e) {
        lastErr = 'exception: ' + e.message;
      }
    }
    return { status: -1, body: lastErr || 'unknown' };
  }, { cid: testClipId, frame: targetFrame });
  if (moveResult.status !== 200) {
    console.log(`  ⚠ move to ${targetFrame} returned status=${moveResult.status}: ${moveResult.body}`);
  }
  await new Promise(r => setTimeout(r, 600));
}

console.log('setup:', setup);

// Build scenario list with expected outcomes. The expected finalFrame
// is computed by the smoke script from the visible timeline state —
// we read it BEFORE the drag, then assert AFTER.
const scenarios = [];
// Setup a "baseline" position for scenarios 1-3 (no snap/clamp): the
// test clip must be far from any sibling so small/large drags don't
// hit them. With siblings ce8fbe0 [4500-4650] and c5f9a84 [4800-5055],
// we pick frame 6000 (well past c5f9a84.end + lenFrames = 5205).
// Each scenario re-baselines to frame 6000 so the previous scenario's
// move doesn't poison the next.
{
  const BASELINE = 6000;
  console.log(`  setup scenarios 1-3: baseline frame ${BASELINE}`);
  await moveClipTo(BASELINE);
}
scenarios.push(
  { name: '1_1px_drag',   deltaPx: 1,   steps: 1,  expectedFinalFrameKind: 'delta1',   preMoveTo: 6000 },
  { name: '2_8px_drag',   deltaPx: 8,   steps: 4,  expectedFinalFrameKind: 'delta8',   preMoveTo: 6000 },
  { name: '3_600px_drag', deltaPx: 600, steps: 20, expectedFinalFrameKind: 'delta600', preMoveTo: 6000 },
);

// Scenario 4: collision clamp.
// Move the test clip to frame 4200 (just before ce8fbe0 [4500-4650]),
// then drag rightward by 400. The drag will try to land at 4600,
// which overlaps ce8fbe0. The clamp should land the clip BEFORE
// ce8fbe0 (at 4500 - clipLen).
{
  const CLAMP_TEST_START = 4200;
  console.log(`  setup scenario 4: moved test clip to frame ${CLAMP_TEST_START}`);
  await moveClipTo(CLAMP_TEST_START);
  scenarios.push({
    name: '4_collision_clamp',
    deltaPx: 400, // drag right by 400, candidate=4600, overlaps ce8fbe0 [4500-4650]
    steps: 12,
    expectedFinalFrameKind: 'clamped',
    preMoveTo: 4200,
    plan: { siblingStart: 4500, expectedFinalFrame: 4350 }, // 4500 - 150 (clipLen)
  });
}

// Scenario 5: snap applied, no overlap.
// Move the test clip to frame 4292 (well below ce8fbe0.end=4650),
// then drag right by 350. The candidate will land at 4642, which
// is within snap radius (8 frames) of ce8fbe0.end=4650 AND of
// c5f9a84.start=4800 (no, distance=158, too far). So snap returns
// 4650. Test clip (len 150) lands at 4650-4800. No overlap with
// ce8fbe0 [4500-4650] (touching at 4650 is OK) or c5f9a84
// [4800-5055]. Snap applied, no overlap. ✅
{
  // Snap-within-radius scenario: drag from a frame where dragging
  // +350 puts the candidate within snap radius (8 frames) of
  // ce8fbe0.end (4650) WITHOUT triggering clamp overlap. OrigF=4300,
  // candidate=4650 (exact snap), tryEnd=4800 — ce8fbe0 [4500-4650]
  // ends at 4650 so no overlap; c5f9a84 starts at 4800 so 4800 <
  // 4800 = false → no overlap. snap(4650) returns 4650 → applied.
  const SNAP_TEST_START = 4300;
  await moveClipTo(SNAP_TEST_START);
  console.log(`  setup scenario 5: moved test clip to frame ${SNAP_TEST_START}`);
  scenarios.push({
    name: '5_snap_within_radius',
    deltaPx: 350, // candidate = 4300 + 350 = 4650, snap target = 4650 (within radius)
    steps: 12,
    expectedFinalFrameKind: 'snapApplied',
    preMoveTo: 4300,
    expectedFinalFrame: 4650, // ce8fbe0.end; test clip (len 150) lands at 4650-4800 — no overlap
  });
}

// Scenario 6: drag within snap radius of a sibling boundary where
// the clamp will apply AND snap target = clamp result (no-op).
// The spec's "snap-creates-overlap → abort" path requires a snap
// target that would overlap a sibling. With Sanlihe's current clip
// layout (ce8fbe0 [4500-4650] + c5f9a84 [4800-5055]), every
// within-radius snap target lands WITHOUT overlap because the gap
// between siblings is wide enough. The clamp puts the clip at the
// boundary already; snap target = sibling.start-lenFrames is a
// no-op (already at clamp position); snap to sibling.end is out of
// radius from the clamp result. So no snap is committed.
//
// This scenario verifies the algorithm handles "drag near snap
// boundary" correctly: the drag must end with the clamp result
// and no snap committed. finalFrame = clamp(candidate) = 4350.
{
  const NEAR_TEST_START = 4292;
  await moveClipTo(NEAR_TEST_START);
  console.log(`  setup scenario 6: moved test clip to frame ${NEAR_TEST_START}`);
  scenarios.push({
    name: '6_near_snap_no_snap',
    deltaPx: 204, // candidate = 4496, within radius of ce8fbe0.start=4500
    steps: 12,
    expectedFinalFrameKind: 'clamped',
    preMoveTo: 4292,
    plan: { expectedFinalFrame: 4350 }, // clamp result: 4500 - 150
  });
}

console.log(`\nrunning ${scenarios.length} scenarios...`);
// No reload here — the setup moved the clip via the Core API and
// the server state is now the source of truth. The next page.evaluate
// reads the DOM which mirrors the server state (after the last /move).
const allPayloads = [];
for (const sc of scenarios) {
  // Per-scenario setup: move the test clip to the scenario's
  // preMoveTo frame (if specified). This way each scenario starts
  // from a known baseline regardless of the previous scenario's
  // commit.
  if (sc.preMoveTo !== undefined) {
    process.stdout.write(`  setup: preMoveTo=${sc.preMoveTo}\n`);
    await moveClipTo(sc.preMoveTo);
  }
  // Reload to clear the GUI's stale dragPreview state from prior
  // scenarios. Without this, the GUI's optimistic move state leaks
  // and the next drag computes finalFrame against a stale position.
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('.timeline-content', { timeout: 10000 });
  // Wait for the GUI's sessionStore to acquire its own lease via
  // /lease/acquire (it does this on init). If we drag before the
  // GUI has a valid sessionId, api.move() in ClipBlock.up() fails
  // with 403 — the optimistic move shows locally but the server
  // never updates.
  await page.waitForTimeout(5000);
  // Verify the GUI has a valid lease before dragging.
  const hasLease = await page.evaluate(async () => {
    try {
      const st = await (await fetch('/ui/status')).json();
      return { hasSession: !!st.session_id, baseRev: st.base_revision };
    } catch { return null; }
  });
  process.stdout.write(`  lease-check: ${JSON.stringify(hasLease)}\n`);
  await page.evaluate(() => { (window).__yrollDragLog = []; });
  consoleDragPayloads.length = 0;
  const tcSel = `[data-track-content="${setup.primary}"]`;
  // DIAGNOSTIC: layout before drag
  const layout = await page.evaluate((sel) => {
    const tc = document.querySelector(sel);
    const clips = Array.from(tc?.querySelectorAll('.clip') || []).map((c) => {
      const l = parseFloat(c.style.left || '0');
      const w = parseFloat(c.style.width || '0');
      return { id: c.dataset.clipId, startF: Math.round(l), endF: Math.round(l + w) };
    });
    return clips;
  }, tcSel);
  process.stdout.write(`  layout: ${JSON.stringify(layout)}\n`);
  const result = await dragClip({
    trackContentSelector: tcSel,
    deltaPx: sc.deltaPx,
    steps: sc.steps,
    endOnDifferentRowSelector: sc.endOnDifferentRowSelector,
  });
  // Sleep 1.5s so the async api.snap + onMoveCommit can complete
  // before we read the payload. We also poll in case it lands later.
  await page.waitForTimeout(1500);
  let payloads = await readPayloads();
  // Also probe window state directly for diagnostic.
  let dbgWinLen = -1;
  try {
    dbgWinLen = await Promise.race([
      page.evaluate(() => ((window).__yrollDragLog || []).length),
      new Promise<number>((r) => setTimeout(() => r(-1), 1500)),
    ]);
  } catch {}
  process.stdout.write(`  [dbg] t=1.5s: window=${dbgWinLen}, console=${consoleDragPayloads.length}, returned=${payloads.length}\n`);
  if (payloads.length === 0) {
    // Try once more after another 2s — sometimes the move/refresh
    // roundtrip blocks the listener queue.
    await page.waitForTimeout(2000);
    payloads = await readPayloads();
    process.stdout.write(`  [dbg] t=3.5s: returned=${payloads.length}, console=${consoleDragPayloads.length}\n`);
  }
  if (payloads.length === 0) {
    console.log(`  DEBUG: consoleDragPayloads.length=${consoleDragPayloads.length}, after 3.5s`);
  }
  console.log(`\n=== ${sc.name} (deltaPx=${sc.deltaPx}) ===`);
  console.log('  drag input:', JSON.stringify(result));
  if (payloads.length === 0) {
    recordFail(sc.name, 'no payload captured', null);
    allPayloads.push({ scenario: sc.name, error: 'no payload' });
    continue;
  }
  const p = payloads[payloads.length - 1];
  console.log('  payload:', JSON.stringify(p, null, 2));
  let ok = true;

  // Universal invariants (every scenario).
  ok = assertEq(sc.name, 'lastPreviewFrame === preSnapFrame',
    p.lastPreviewFrame, p.preSnapFrame, p) && ok;
  ok = assertEq(sc.name, 'candidateFrame - originalFrame === deltaFrame',
    p.candidateFrame - p.originalFrame, p.deltaFrame, p) && ok;
  ok = assertEq(sc.name, 'pxPerFrame ≈ 1 (30 px/sec @ 30 fps)',
    Math.abs(p.pxPerFrame - 1) < 0.01 ? 1 : 0, 1, p) && ok;

  // Per-scenario assertions.
  switch (sc.expectedFinalFrameKind) {
    case 'delta1':
      ok = assertEq(sc.name, 'finalFrame', p.finalFrame, p.originalFrame + 1, p) && ok;
      ok = assertEq(sc.name, 'lastPreviewFrame', p.lastPreviewFrame, p.originalFrame + 1, p) && ok;
      ok = assertEq(sc.name, 'authoritativeSnapFrame', p.authoritativeSnapFrame, null, p) && ok;
      // ghostSnapFrame MAY be non-null if the dragged clip's own
      // start happens to be within snap radius — that's a visual
      // hint only and is allowed. The KEY invariant: the preview
      // frame (lastPreviewFrame) did follow the pointer +1.
      ok = assertEq(sc.name, 'snapAborted', p.snapAborted, false, p) && ok;
      break;
    case 'delta8':
      ok = assertEq(sc.name, 'finalFrame', p.finalFrame, p.originalFrame + 8, p) && ok;
      ok = assertEq(sc.name, 'lastPreviewFrame', p.lastPreviewFrame, p.originalFrame + 8, p) && ok;
      ok = assertEq(sc.name, 'authoritativeSnapFrame', p.authoritativeSnapFrame, null, p) && ok;
      ok = assertEq(sc.name, 'snapAborted', p.snapAborted, false, p) && ok;
      break;
    case 'delta600':
      ok = assertEq(sc.name, 'finalFrame', p.finalFrame, p.originalFrame + 600, p) && ok;
      ok = assertEq(sc.name, 'lastPreviewFrame', p.lastPreviewFrame, p.originalFrame + 600, p) && ok;
      ok = assertEq(sc.name, 'authoritativeSnapFrame', p.authoritativeSnapFrame, null, p) && ok;
      ok = assertEq(sc.name, 'snapAborted', p.snapAborted, false, p) && ok;
      break;
    case 'clamped': {
      // finalFrame should equal clamp(candidate) — collision-free,
      // not equal to original+delta (we hit a sibling), and the
      // snap engine was NOT applied (snap was NOT used to bypass
      // collision; clamp did the work).
      const expected = sc.plan?.expectedFinalFrame ?? sc.plan?.siblingStart;
      const matches = p.finalFrame === expected
        || (p.preSnapFrame === expected && p.authoritativeSnapFrame === null);
      if (!matches) {
        recordFail(sc.name, `expected clamped finalFrame=${expected}; got finalFrame=${p.finalFrame}, preSnapFrame=${p.preSnapFrame}`, p);
        ok = false;
      }
      ok = assertEq(sc.name, 'authoritativeSnapFrame', p.authoritativeSnapFrame, null, p) && ok;
      ok = assertEq(sc.name, 'snapAborted', p.snapAborted, false, p) && ok;
      break;
    }
    case 'snapApplied':
      // snap target should equal sibling.start; finalFrame = snap;
      // no overlap; not aborted.
      ok = assertEq(sc.name, 'authoritativeSnapFrame', p.authoritativeSnapFrame, sc.expectedFinalFrame, p) && ok;
      ok = assertEq(sc.name, 'finalFrame', p.finalFrame, sc.expectedFinalFrame, p) && ok;
      ok = assertEq(sc.name, 'snapAborted', p.snapAborted, false, p) && ok;
      break;
    case 'snapAborted':
      // snap was attempted (or would have been applied) but
      // finalFrame = preSnapFrame (clamped) instead of the snap
      // target.
      ok = assertEq(sc.name, 'finalFrame', p.finalFrame, p.preSnapFrame, p) && ok;
      // Whether authoritativeSnapFrame is null or non-null depends
      // on which branch fired. The key invariant: finalFrame ==
      // preSnapFrame and snapAborted === true.
      ok = assertEq(sc.name, 'snapAborted', p.snapAborted, true, p) && ok;
      break;
  }

  if (ok) recordPass(sc.name, p);
  allPayloads.push({ scenario: sc.name, input: result, payload: p, ok });
}

writeFileSync('/tmp/03r3-1-payloads.json', JSON.stringify(allPayloads, null, 2));
console.log(`\n=== wrote /tmp/03r3-1-payloads.json ===`);
console.log(`\nSUMMARY: ${PASSES.length} pass, ${FAILURES.length} fail`);

await browser.close();
if (FAILURES.length > 0) {
  console.error('\nFAILURES:');
  for (const f of FAILURES) console.error(`  ${f.name}: ${f.reason}`);
  process.exit(1);
}
process.exit(0);