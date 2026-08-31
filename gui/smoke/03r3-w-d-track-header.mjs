// GUI-03R3-W-D: Track Header UX smoke verification.
//
// Drives the live browser at http://localhost:5180/ against the live
// yroll serve backend on :8765, with projects/sanlihe-slice-30s as
// the data source. Asserts:
//
//   1. semantic track icons render (T=text, V=video, A=audio SVG)
//   2. mute/lock/visibility are always visible at reduced opacity
//      (state apparent without hover)
//   3. track header column is resizable via a drag handle
//   4. resize persists across reload (localStorage round-trip)
//   5. Content Origin invariant: resizing the header column does NOT
//      shift the ruler / .track-content coordinate space. frame 0
//      stays at x=0 inside .timeline-content.
//
// Run:
//   yroll serve projects/sanlihe-slice-30s   # port 8765
//   node gui/smoke/serve-with-proxy-w-d.mjs # port 5180
//   node gui/smoke/03r3-w-d-track-header.mjs

import { chromium } from 'playwright';

const URL = process.env.URL ?? 'http://localhost:5180/';
const results = [];
let exitCode = 0;
const record = (name, ok, detail = '') => {
  results.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'} · ${name}${detail ? ' — ' + detail : ''}`);
  if (!ok) exitCode = 1;
};

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
});

try {
  const page = await ctx.newPage();
  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (e) => consoleErrors.push(`pageerror: ${e.message}`));

  // --- Navigate -----------------------------------------------------------
  await page.goto(URL, { waitUntil: 'networkidle', timeout: 20000 });
  // The Timeline is the last thing to mount. Wait for .timeline-headers.
  await page.waitForSelector('.timeline-headers', { timeout: 10000 });
  await page.waitForTimeout(800);  // settle resize + Core keymap fetch

  // --- 1. semantic track icons ------------------------------------------
  // The fixture may not have all three kinds (Sanlihe main has only
  // video + text — audio tracks were cleaned up by W-B). Verify
  // whatever kinds ARE present render with the right SVG icon.
  const kindIcons = await page.$$eval('.track-kind-icon', (els) =>
    els.map((e) => ({
      kind: e.querySelector('svg')?.getAttribute('data-track-kind-icon'),
      klass: e.className,
    })),
  );
  const presentKinds = new Set(kindIcons.map((i) => i.kind).filter(Boolean));
  const textOk = !presentKinds.has('text') || kindIcons.some(
    (i) => i.kind === 'text' && /kind-text|kind-subtitle/.test(i.klass));
  const videoOk = !presentKinds.has('video') || kindIcons.some(
    (i) => i.kind === 'video' && /kind-video|kind-image/.test(i.klass));
  const audioOk = !presentKinds.has('audio') || kindIcons.some(
    (i) => i.kind === 'audio' && /kind-audio/.test(i.klass));
  record('semantic track icons render (kinds present: ' +
    Array.from(presentKinds).sort().join(',') + ')',
    textOk && videoOk && audioOk,
    `present=${Array.from(presentKinds).sort().join(',')} text=${textOk} video=${videoOk} audio=${audioOk} (total=${kindIcons.length})`);

  // --- 2. mute/lock/visibility always visible (opacity > 0) --------------
  // Find a NON-text track row so mute button is present (text tracks
  // intentionally omit mute per the spec).
  const buttonRow = await page.evaluate(() => {
    const rows = Array.from(document.querySelectorAll('.track-label-row'));
    for (const row of rows) {
      if (row.style.display === 'none') continue;
      const buttons = row.querySelector('.track-label-buttons');
      if (!buttons) continue;
      const hasMute = !!row.querySelector('button[aria-label="mute"]');
      const hasLock = !!row.querySelector('button[aria-label="lock"]');
      const hasHide = !!row.querySelector('button[aria-label="hide"]');
      if (hasMute && hasLock && hasHide) {
        const cs = getComputedStyle(buttons);
        return { opacity: cs.opacity, hasMute, hasLock, hasHide,
                 trackId: row.getAttribute('data-track-id') };
      }
    }
    return null;
  });
  record('mute/lock/visibility always visible (opacity > 0)',
    !!buttonRow && Number(buttonRow.opacity) > 0 &&
      buttonRow.hasMute && buttonRow.hasLock && buttonRow.hasHide,
    buttonRow ? `opacity=${buttonRow.opacity} track=${buttonRow.trackId} mute=${buttonRow.hasMute} lock=${buttonRow.hasLock} hide=${buttonRow.hasHide}` : 'no row with all 3 buttons');

  // --- 2b. visibility uses eye icon (not prohibition sign) --------------
  const visSvg = await page.evaluate(() => {
    const btn = document.querySelector('.track-label-row button[aria-label="hide"]');
    if (!btn) return null;
    return {
      hasSvg: !!btn.querySelector('svg'),
      hasProhibit: btn.textContent?.includes('🚫') ?? false,
      dataVisibility: btn.querySelector('svg')?.getAttribute('data-visibility'),
    };
  });
  record('visibility uses eye icon (no prohibition sign)',
    !!visSvg && visSvg.hasSvg && !visSvg.hasProhibit,
    visSvg ? `hasSvg=${visSvg.hasSvg} prohibit=${visSvg.hasProhibit} data-visibility=${visSvg.dataVisibility}` : 'no button');

  // --- 3. track header column resizable ----------------------------------
  // The width must be controllable via a drag handle, and clamped to [80, 300].
  const initial = await page.$eval('.timeline-headers', (el) =>
    parseInt(getComputedStyle(el).width, 10));
  record('default header width = 160px', initial === 160, `got ${initial}`);

  // Find the resize handle (vertical) inside .timeline-pane. The Timeline
  // emits exactly one .resize-handle.vertical between .timeline-headers
  // and .timeline-content.
  const handleBox = await page.evaluate(() => {
    const h = document.querySelector('.timeline-pane > .resize-handle.vertical');
    if (!h) return null;
    const r = h.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  });
  if (!handleBox) {
    record('resize handle exists between headers and content', false, 'no .resize-handle.vertical in .timeline-pane');
  } else {
    record('resize handle exists between headers and content', true, `center=${handleBox.x.toFixed(1)},${handleBox.y.toFixed(1)}`);

    // Drag right by 50px → width should grow by ~50.
    await page.mouse.move(handleBox.x, handleBox.y);
    await page.mouse.down();
    await page.mouse.move(handleBox.x + 50, handleBox.y, { steps: 6 });
    await page.mouse.up();
    await page.waitForTimeout(150);
    const afterGrow = await page.$eval('.timeline-headers', (el) =>
      parseInt(getComputedStyle(el).width, 10));
    record('resize right → header grows (160 → ~210)',
      afterGrow >= 200 && afterGrow <= 220,
      `got ${afterGrow}`);

    // Drag left past the min → width should clamp at 80.
    const handleBox2 = await page.evaluate(() => {
      const h = document.querySelector('.timeline-pane > .resize-handle.vertical');
      const r = h.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    });
    await page.mouse.move(handleBox2.x, handleBox2.y);
    await page.mouse.down();
    await page.mouse.move(handleBox2.x - 300, handleBox2.y, { steps: 12 });
    await page.mouse.up();
    await page.waitForTimeout(150);
    const afterClampMin = await page.$eval('.timeline-headers', (el) =>
      parseInt(getComputedStyle(el).width, 10));
    record('resize past min → clamps to 80',
      afterClampMin === 80, `got ${afterClampMin}`);

    // Drag right past the max → width should clamp at 300.
    const handleBox3 = await page.evaluate(() => {
      const h = document.querySelector('.timeline-pane > .resize-handle.vertical');
      const r = h.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    });
    await page.mouse.move(handleBox3.x, handleBox3.y);
    await page.mouse.down();
    await page.mouse.move(handleBox3.x + 400, handleBox3.y, { steps: 12 });
    await page.mouse.up();
    await page.waitForTimeout(150);
    const afterClampMax = await page.$eval('.timeline-headers', (el) =>
      parseInt(getComputedStyle(el).width, 10));
    record('resize past max → clamps to 300',
      afterClampMax === 300, `got ${afterClampMax}`);
  }

  // --- 4. width persists across reload -----------------------------------
  // After the last clamp, width = 300. Reload and check.
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('.timeline-headers', { timeout: 10000 });
  await page.waitForTimeout(800);
  const afterReload = await page.$eval('.timeline-headers', (el) =>
    parseInt(getComputedStyle(el).width, 10));
  record('width persists across reload (300)',
    afterReload === 300, `got ${afterReload}`);

  // Reset to a mid value for the alignment check.
  await page.evaluate(() => {
    try { localStorage.setItem('yroll.timelineHeaderWidth.v1', '160'); } catch {}
  });
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('.timeline-headers', { timeout: 10000 });
  await page.waitForTimeout(500);

  // --- 5. Content Origin invariant --------------------------------------
  // Resizing the header MUST NOT shift frame 0 INSIDE the
  // ContentViewport. The .timeline-headers column is a flexbox
  // SIBLING of .timeline-content, so its left edge moves by the
  // resize delta — that's expected. What must NOT change is
  //   tickLeft  −  trackContentLeft  ==  0
  // (the tick at frame 0 sits exactly at the left edge of the
  // ContentViewport, regardless of header column width).
  const originBefore = await page.evaluate(() => {
    const tick = document.querySelector('.ruler .tick');
    const tc = document.querySelector('.track-content');
    if (!tick || !tc) return null;
    const tr = tick.getBoundingClientRect();
    const tcr = tc.getBoundingClientRect();
    return { tickLeft: tr.left, trackContentLeft: tcr.left,
             delta: tr.left - tcr.left };
  });
  // Resize to 240.
  const handleBox4 = await page.evaluate(() => {
    const h = document.querySelector('.timeline-pane > .resize-handle.vertical');
    const r = h.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  });
  await page.mouse.move(handleBox4.x, handleBox4.y);
  await page.mouse.down();
  await page.mouse.move(handleBox4.x + 80, handleBox4.y, { steps: 6 });
  await page.mouse.up();
  await page.waitForTimeout(200);
  const originAfter = await page.evaluate(() => {
    const tick = document.querySelector('.ruler .tick');
    const tc = document.querySelector('.track-content');
    if (!tick || !tc) return null;
    const tr = tick.getBoundingClientRect();
    const tcr = tc.getBoundingClientRect();
    return { tickLeft: tr.left, trackContentLeft: tcr.left,
             delta: tr.left - tcr.left };
  });
  // Content Origin invariant: tickLeft - trackContentLeft must stay 0
  // (both move together when the header column resizes; the diff
  // stays 0 because frame 0 sits at x=0 inside the ContentViewport).
  const ok = originBefore && originAfter &&
    Math.abs(originBefore.delta) < 1 &&
    Math.abs(originAfter.delta) < 1;
  record('Content Origin invariant: tick-to-trackContent delta = 0',
    ok,
    `before Δ=${originBefore?.delta.toFixed(2)} after Δ=${originAfter?.delta.toFixed(2)} ` +
    `(tickLeft ${originBefore?.tickLeft.toFixed(1)}→${originAfter?.tickLeft.toFixed(1)}, ` +
    `tcLeft ${originBefore?.trackContentLeft.toFixed(1)}→${originAfter?.trackContentLeft.toFixed(1)})`);

  // --- 6. Help dialog derives from Core keymap (not seconds) -----------
  // Open via the 帮助 menu (MenuBar) → "快捷键清单".
  await page.evaluate(() => { try { localStorage.removeItem('yroll.timelineHeaderWidth.v1'); } catch {} });
  const helpMenuOpened = await page.evaluate(() => {
    const menus = Array.from(document.querySelectorAll('.menubar .menu'));
    for (const menu of menus) {
      const name = menu.querySelector('.menu-name')?.textContent?.trim();
      if (name === '帮助') {
        menu.querySelector('.menu-name').click();
        return true;
      }
    }
    return false;
  });
  if (!helpMenuOpened) {
    record('Help menu (帮助) opens', false, 'no menu found');
  } else {
    await page.waitForTimeout(150);
    const helpItemClicked = await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll('.menu-item'));
      const target = items.find((i) => i.textContent?.includes('快捷键清单'));
      if (!target) return false;
      target.click();
      return true;
    });
    record('Help dialog opens via 帮助 → 快捷键清单', helpItemClicked);
    if (helpItemClicked) {
      await page.waitForTimeout(300);
      const helpText = await page.evaluate(() => {
        const body = document.querySelector('.workspace .ws-body');
        return body?.textContent ?? '';
      });
      const hasFrame = helpText.includes('frame');
      const noSecondsLeak = !helpText.match(/[±]5s|[±]0\.1s|[±]1s/);
      const hasHome = helpText.toLowerCase().includes('home') ||
                      helpText.includes('播放头居中') ||
                      helpText.includes('center playhead');
      const noMute = !/M\s*静音/.test(helpText);
      // The new dialog says "Shift+J/L ±10 frames" — that's intentional
      // (not stale). Only flag the OLD wording "Shift+Z 缩放到适配".
      const noShiftZ = !/Shift\+?Z\s*缩放/.test(helpText);
      record('Help text mentions frames (not seconds)', hasFrame, helpText.slice(0, 80));
      record('Help text has no seconds leakage', noSecondsLeak, '');
      record('Help text mentions Home (center playhead)', hasHome, '');
      record('Help text removed stale M 静音', noMute, '');
      record('Help text removed stale "Shift+Z 缩放到适配"', noShiftZ,
        `found: ${helpText.match(/Shift\+?Z[^A-Za-z]*\S+/)?.join(', ') ?? 'none'}`);
      // Close the dialog.
      await page.keyboard.press('Escape').catch(() => {});
    }
  }

  // --- 7. no critical console errors -------------------------------------
  // Filter out the pre-existing /assets/{id}/file and /assets/{id}/waveform
  // 404 noise (separate follow-up; see docs/GUI-03R3-W-D-404-followup.md).
  const real = consoleErrors.filter(
    (e) => !e.includes('/assets/') && !e.includes('Failed to load resource'),
  );
  record('no NEW console.error entries (excluding pre-existing 404s)',
    real.length === 0, `count=${real.length} sample=${real[0]?.slice(0, 60) ?? ''}`);

} finally {
  await browser.close();
}

// --- summary --------------------------------------------------------------
const passed = results.filter((r) => r.ok).length;
const failed = results.filter((r) => !r.ok).length;
console.log(`\nW-D smoke: ${passed} PASS / ${failed} FAIL`);
process.exit(exitCode);