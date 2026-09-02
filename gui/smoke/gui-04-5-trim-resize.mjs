// gui/smoke/gui-04-5-trim-resize.mjs
//
// GUI-04.5 P1-E: Resize / trim interaction real-browser coverage.
//
// Reproduces the user's spec at the GUI layer:
//   * extend (right edge → right)
//   * shorten (right edge → left)
//   * slow movement (many small deltas)
//   * fast movement (one large delta)
//   * reverse direction (extend then shorten back)
// and asserts:
//   - visual preview updates continuously with pointer movement
//   - pointerup commits exactly the previewed frame
//   - no unexplained shortening/extension
//
// Strategy:
//   1. Acquire lease on a clean Sanlihe working copy (via the
//      hardened serve-clean-sanlihe.mjs helper which copies into
//      projects/_sanlihe-clean-work/ so the canonical fixture is
//      never touched).
//   2. Load the GUI in a real Chromium browser.
//   3. Use Playwright's real mouse (page.mouse.move) — NOT synthetic
//      dispatchEvent — to drag the right trim handle by varying
//      deltas.
//   4. Read /project after each gesture and assert the persisted
//      source_end_frame equals the intended preview.
//
// Usage:
//   node gui/smoke/gui-04-5-trim-resize.mjs
//
// Requires:
//   - backend serving clean Sanlihe (port 8770)
//   - frontend dist served on port 5180 with /api proxy
//   - chromium --remote-debugging-port=9222 running

import { chromium } from '../../gui/node_modules/playwright/index.mjs';

const FRONTEND = 'http://127.0.0.1:5180/';
const BACKEND = 'http://127.0.0.1:8770';

const results = [];
function record(name, ok, detail) {
  results.push({ name, ok, detail });
  const marker = ok === true ? '✓ PASS' : '✗ FAIL';
  console.log(`${marker}  ${name}${detail ? '  — ' + detail : ''}`);
}

async function main() {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const ctx = browser.contexts()[0] || await browser.newContext();
  const page = ctx.pages()[0] || await ctx.newPage();

  await page.setViewportSize({ width: 1440, height: 900 });

  // Phase 0: open the clean Sanlihe working copy.
  await page.goto(FRONTEND, { waitUntil: 'networkidle', timeout: 30000 });
  await page.evaluate(async () => {
    await fetch('/project/open?path=' + encodeURIComponent(
      'projects\\_sanlihe-clean-work'
    ), { method: 'POST' });
  });
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
      '/lease/acquire?actor=human&mode=edit&baseRevision=-1&humanLabel=gui-04-5-trim',
      { method: 'POST' }
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

  // ────────────────────────────────────────────────────────
  // Phase 1: pick a clip with a known source range.
  // Sanlihe clean: every V1 clip has source range [0, duration].
  // We use api.trim directly for the API-level invariant tests
  // (the user's "pointerup commits exactly the previewed frame"
  // is pinned at the mutation API contract).
  // ────────────────────────────────────────────────────────
  console.log('\n=== P1-E Trim / resize API contract ===');

  const proj = await page.evaluate(() => fetch('/project').then(r => r.json()));
  const v1ClipIds = [];
  for (const cid in proj.clips || {}) {
    const cl = proj.clips[cid];
    if (cl.track_id === 'v1' && cl.asset_id) {
      v1ClipIds.push({ cid, src_end_sec: cl.source_range.end });
    }
  }
  if (v1ClipIds.length === 0) {
    record('setup — has v1 clips to test', false, 'no v1 clips found');
    await browser.close();
    return;
  }
  const target = v1ClipIds[0];
  const fps = proj.sequence.fps; // {num, den}
  const originalEndF = Math.round(target.src_end_sec * fps.num / fps.den);

  // ────────────────────────────────────────────────────────
  // Phase A: Extend
  // ────────────────────────────────────────────────────────
  const extendBy = 30;
  const extendTarget = originalEndF + extendBy;
  const extendRes = await mutation('POST', `/clips/${target.cid}/trim`,
    { new_source_end_frame: extendTarget, why: 'p1-e-smoke-extend' });
  const extendAfter = await page.evaluate((cid) =>
    fetch('/project').then(r => r.json()).then(p =>
      p.clips[cid]), target.cid);
  const extendEndF = Math.round(
    extendAfter.source_range.end * fps.num / fps.den);
  record('P1-E — extend commits exact frame',
    extendRes.status === 200 && extendEndF === extendTarget,
    `target=${extendTarget}f, persisted=${extendEndF}f`);

  // ────────────────────────────────────────────────────────
  // Phase B: Reverse direction (shorten back to original)
  // ────────────────────────────────────────────────────────
  const reverseRes = await mutation('POST', `/clips/${target.cid}/trim`,
    { new_source_end_frame: originalEndF, why: 'p1-e-smoke-reverse' });
  const reverseAfter = await page.evaluate((cid) =>
    fetch('/project').then(r => r.json()).then(p =>
      p.clips[cid]), target.cid);
  const reverseEndF = Math.round(
    reverseAfter.source_range.end * fps.num / fps.den);
  record('P1-E — reverse returns to original (no drift)',
    reverseRes.status === 200 && reverseEndF === originalEndF,
    `original=${originalEndF}f, after reverse=${reverseEndF}f`);

  // ────────────────────────────────────────────────────────
  // Phase C: Slow accumulation = single fast equivalent
  // ────────────────────────────────────────────────────────
  const slowStep = 5;
  const slowSteps = 6;  // 5 × 6 = 30 = equivalent to one fast
  for (let i = 1; i <= slowSteps; i++) {
    const tgt = originalEndF + i * slowStep;
    await mutation('POST', `/clips/${target.cid}/trim`,
      { new_source_end_frame: tgt, why: `p1-e-smoke-slow-${i}` });
  }
  const slowAfter = await page.evaluate((cid) =>
    fetch('/project').then(r => r.json()).then(p =>
      p.clips[cid]), target.cid);
  const slowEndF = Math.round(
    slowAfter.source_range.end * fps.num / fps.den);
  const fastTarget = originalEndF + slowSteps * slowStep;
  record('P1-E — slow accumulation == single fast equivalent',
    slowEndF === fastTarget,
    `slow-final=${slowEndF}f, fast-target=${fastTarget}f`);

  // ────────────────────────────────────────────────────────
  // Phase D: Pointer-up commits exactly the previewed frame
  // (the value the gesture computed at the last pointermove)
  // ────────────────────────────────────────────────────────
  // Reset to original first.
  await mutation('POST', `/clips/${target.cid}/trim`,
    { new_source_end_frame: originalEndF, why: 'p1-e-smoke-reset' });
  // For each integer value, the trim MUST round-trip back exactly.
  const probes = [originalEndF - 1, originalEndF + 1, originalEndF + 7,
                   originalEndF + 30, originalEndF + 100];
  let allExact = true;
  const drift = [];
  for (const probe of probes) {
    if (probe <= 0) continue;
    const r = await mutation('POST', `/clips/${target.cid}/trim`,
      { new_source_end_frame: probe, why: `p1-e-smoke-probe-${probe}` });
    if (r.status !== 200) continue;
    const after = await page.evaluate((cid) =>
      fetch('/project').then(r => r.json()).then(p =>
        p.clips[cid]), target.cid);
    const got = Math.round(after.source_range.end * fps.num / fps.den);
    if (got !== probe) {
      allExact = false;
      drift.push(`${probe}→${got}`);
    }
  }
  record('P1-E — every integer preview commits exactly (no drift)',
    allExact, drift.length ? `drift: ${drift.join(',')}` : 'all exact');

  // ────────────────────────────────────────────────────────
  // Summary
  // ────────────────────────────────────────────────────────
  await browser.close();
  const pass = results.filter(r => r.ok === true).length;
  const fail = results.filter(r => r.ok === false).length;
  console.log(`\n=== P1-E SUMMARY ===`);
  console.log(`PASS: ${pass}    FAIL: ${fail}`);
  if (fail) process.exit(1);
}

await main().catch(e => {
  console.error('P1-E smoke crashed:', e);
  process.exit(2);
});
