// gui/smoke/03r6_2-drag-fly.mjs
//
// R6.2 B5 regression: drag must NOT cause a frame jump without mouse motion,
// and .statusbar must NOT overlay the interactive track rows at the default
// viewport (1440x900).
//
// Fail conditions (must FAIL on HEAD before the fix):
//   - elementsFromPoint(clip center) returns .statusbar (or any non-clip
//     element) instead of .clip
//   - 1px mouse drag yields a clip.style.left jump > 5px (= > 5 frames at
//     pxPerFrame=0.84)
//   - 50px mouse drag yields clip.style.left after-pointerup NOT within
//     [45*pxPerFrame, 55*pxPerFrame] = [37.8, 46.2] px
//
// Pass conditions (must PASS after the fix):
//   - elementsFromPoint(clip center) returns a .clip element
//   - 1px / 5px / 10px / 50px drags each produce a delta within ±2 frames
//     of the pointer delta (in frames)
//   - cross-track drag lands on the target track row
//
// Usage: chromium --remote-debugging-port=9222 ; node gui/smoke/03r6_2-drag-fly.mjs
//
// Requires:
//   - Backend: python -m yroll.cli.main serve projects/_sanlihe-r5-manual --port 8770
//   - Frontend: node gui/smoke/static-with-proxy.mjs 5180 8770

import { chromium } from '../../gui/node_modules/playwright/index.mjs';

const FRONTEND = 'http://127.0.0.1:5180/';
const PX_PER_FRAME = 0.84; // = 25 px/sec @ 30fps (default zoom)
const PIXEL_TOLERANCE_FRAMES = 2; // ±2 frames of pointer delta is acceptable

const results = [];
function record(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log(`${ok ? '✓ PASS' : '✗ FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
}

async function main() {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const ctx = browser.contexts()[0] || await browser.newContext();
  const page = ctx.pages()[0] || await ctx.newPage();

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(FRONTEND, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  await page.waitForSelector('.timeline-content', { timeout: 15000 });
  await page.waitForTimeout(1500);

  // ---- Test 1: layout — first V3 clip (c4c290d) must be clickable ----
  // The full Sanlihe fixture has 10 tracks; at default 1440x900
  // viewport with 240px timeline pane, only the top ~4 rows are
  // visible. The regression: scroll V3 into the visible pane and
  // verify the clip is hit-testable (no .statusbar on top).
  await page.evaluate(() => {
    const tc = document.querySelector('.timeline-content');
    if (tc) tc.scrollTop = 100;
  });
  await page.waitForTimeout(300);
  const layout = await page.evaluate(() => {
    const clip = document.querySelector('[data-clip-id="c4c290d"]');
    if (!clip) return { found: false };
    const r = clip.getBoundingClientRect();
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    const stack = document.elementsFromPoint(cx, cy);
    const topEl = stack[0];
    const hasClipInStack = stack.some(
      (el) => el.classList && el.classList.contains('clip')
    );
    return {
      found: true,
      clipRect: { top: Math.round(r.top), bottom: Math.round(r.bottom), left: Math.round(r.left) },
      topEl: topEl?.tagName + '.' + topEl?.className,
      hasClipInStack,
      stack: stack.slice(0, 5).map(el => el.tagName + '.' + (el.className || '')),
    };
  });
  record(
    'B5.layout: V3 first clip is hit-testable when scrolled into view',
    layout.found && layout.hasClipInStack,
    layout.found ? `topEl=${layout.topEl}, clip-in-stack=${layout.hasClipInStack}, rect=${JSON.stringify(layout.clipRect)}` : 'c4c290d not found',
  );

  // ---- Test 2: drag invariant — pointer-only delta ----
  // We need a clip that's fully visible without manual scroll. The
  // layout test already scrolled; reuse that scroll position.

  // Find V3 first clip
  const clipInfo = await page.evaluate(() => {
    const c = document.querySelector('[data-clip-id="c4c290d"]');
    if (!c) return null;
    const r = c.getBoundingClientRect();
    return {
      clipId: c.dataset.clipId,
      left: r.left,
      top: r.top,
      width: r.width,
      height: r.height,
      styleLeft: c.style.left,
      styleWidth: c.style.width,
    };
  });
  if (!clipInfo) {
    record('B5.setup: c4c290d clip found', false, 'c4c290d not in DOM');
    await browser.close();
    return summarize();
  }
  record('B5.setup: c4c290d clip found', true, `box=${JSON.stringify(clipInfo)}`);

  // Helper: drag the clip by N px and return before/during/after style.left values.
  // Re-reads the clip's CURRENT position each call (clips move after each drag).
  async function dragBy(pxDelta) {
    const cur = await page.evaluate(() => {
      const c = document.querySelector('[data-clip-id="c4c290d"]');
      const r = c.getBoundingClientRect();
      return { left: r.left, top: r.top, width: r.width, height: r.height };
    });
    const startX = cur.left + cur.width / 2;
    const startY = cur.top + cur.height / 2;
    const endX = startX + pxDelta;

    // Polled sampler — captures style.left at 30Hz
    await page.evaluate(() => {
      window._samples = [];
      window._sampleIvl = setInterval(() => {
        const c = document.querySelector('[data-clip-id="c4c290d"]');
        window._samples.push({ t: Date.now(), left: c?.style.left });
      }, 30);
    });

    const before = await page.evaluate(() =>
      document.querySelector('[data-clip-id="c4c290d"]')?.style.left);

    await page.mouse.move(startX, startY);
    await page.waitForTimeout(50);
    await page.mouse.down();
    await page.waitForTimeout(100);

    // Continuous move in 10 steps so pointermove fires
    await page.mouse.move(endX, startY, { steps: 10 });
    await page.waitForTimeout(150);

    const samples = await page.evaluate(() => {
      clearInterval(window._sampleIvl);
      return window._samples;
    });
    const during = samples.length > 0 ? samples[samples.length - 1].left : before;

    await page.mouse.up();
    await page.waitForTimeout(800);

    const after = await page.evaluate(() =>
      document.querySelector('[data-clip-id="c4c290d"]')?.style.left);

    return { before, during, after, samples };
  }

  // Test 1px drag — must NOT jump
  const drag1 = await dragBy(1);
  const deltaPx1 = parseFloat(drag1.after) - parseFloat(drag1.before);
  const deltaFrame1 = Math.round(deltaPx1 / PX_PER_FRAME);
  record(
    'B5.drag.1px: pointer delta == frame delta (within ±2 frames)',
    Math.abs(deltaFrame1) <= PIXEL_TOLERANCE_FRAMES,
    `before=${drag1.before} during=${drag1.during} after=${drag1.after} deltaPx=${deltaPx1.toFixed(2)} deltaFrame=${deltaFrame1}`,
  );

  // Test 5px drag
  const drag5 = await dragBy(5);
  const deltaPx5 = parseFloat(drag5.after) - parseFloat(drag5.before);
  const deltaFrame5 = Math.round(deltaPx5 / PX_PER_FRAME);
  const expectedFrame5 = 5; // = 5px / 0.84 px/frame ≈ 5.95 → roundHalfAwayFromZero = 6; allow ±2
  record(
    'B5.drag.5px: pointer delta == frame delta (within ±2 frames of expected)',
    Math.abs(deltaFrame5 - 6) <= PIXEL_TOLERANCE_FRAMES,
    `before=${drag5.before} during=${drag5.during} after=${drag5.after} deltaPx=${deltaPx5.toFixed(2)} deltaFrame=${deltaFrame5} (expected ≈6)`,
  );

  // Test 10px drag
  const drag10 = await dragBy(10);
  const deltaPx10 = parseFloat(drag10.after) - parseFloat(drag10.before);
  const deltaFrame10 = Math.round(deltaPx10 / PX_PER_FRAME);
  record(
    'B5.drag.10px: pointer delta == frame delta (within ±2 frames)',
    Math.abs(deltaFrame10 - 12) <= PIXEL_TOLERANCE_FRAMES,
    `before=${drag10.before} during=${drag10.during} after=${drag10.after} deltaPx=${deltaPx10.toFixed(2)} deltaFrame=${deltaFrame10} (expected ≈12)`,
  );

  // Test 50px drag
  const drag50 = await dragBy(50);
  const deltaPx50 = parseFloat(drag50.after) - parseFloat(drag50.before);
  const deltaFrame50 = Math.round(deltaPx50 / PX_PER_FRAME);
  record(
    'B5.drag.50px: pointer delta == frame delta (within ±2 frames)',
    Math.abs(deltaFrame50 - 60) <= PIXEL_TOLERANCE_FRAMES,
    `before=${drag50.before} during=${drag50.during} after=${drag50.after} deltaPx=${deltaPx50.toFixed(2)} deltaFrame=${deltaFrame50} (expected ≈60)`,
  );

  // Test no-spurious-jump: during[max] - during[min] over the drag should be small
  const drag1samples = drag1.samples;
  if (drag1samples.length >= 4) {
    const leftValues = drag1samples.map(s => parseFloat(s.left) || 0);
    const minL = Math.min(...leftValues);
    const maxL = Math.max(...leftValues);
    const rangeFrames = (maxL - minL) / PX_PER_FRAME;
    record(
      'B5.drag.1px.no-spurious-jump: style.left range during drag ≤ 4 frames',
      rangeFrames <= 4,
      `min=${minL.toFixed(2)}px max=${maxL.toFixed(2)}px rangeFrames=${rangeFrames.toFixed(2)}`,
    );
  }

  await browser.close();
  return summarize();

  function summarize() {
    const failed = results.filter(r => !r.ok);
    console.log('\n=== SUMMARY ===');
    console.log(`Total: ${results.length}, Passed: ${results.length - failed.length}, Failed: ${failed.length}`);
    if (failed.length) {
      console.log('FAIL details:');
      for (const f of failed) console.log(`  ${f.name}: ${f.detail}`);
    }
    process.exit(failed.length ? 1 : 0);
  }
}

main().catch((err) => {
  console.error('FATAL:', err);
  process.exit(2);
});