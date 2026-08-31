// GUI-03R5 Batch 1 Browser Smoke.
//
// Connects to a running Chromium via CDP, opens the dev frontend, and
// verifies the GUI-03R5-B1 contracts:
//
//   1. Session readiness gate — connect, drop an asset, the request
//      MUST reach /clips/add_image WITH a non-null sessionId, OR
//      surface a status message (never 403 "sessionId required").
//   2. Drag math — drag a clip 50px right, the committed frame delta
//      MUST equal round(50/pxPerFrame), independent of any
//      ContentViewport scroll change.

import { setTimeout as sleep } from 'node:timers/promises';

const FRONTEND = process.env.FRONTEND ?? 'http://127.0.0.1:5180';
const BACKEND = process.env.BACKEND ?? 'http://127.0.0.1:8765';
const CDP = process.env.CDP ?? 'http://127.0.0.1:9222';

console.log('=== GUI-03R5-B1 Browser Smoke ===');
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

// === Scenario 1: Session readiness ===
//
// Wait for the lease badge to read "我 · r<N>" (we hold EDIT). Then
// drop an asset and assert the network call had a sessionId.
console.log('\n[1] Session readiness gate');

const badge = await page.locator('[data-testid="edit-lease-badge"]').first()
  .textContent({ timeout: 15000 }).catch(() => null);
check('EditLease badge appears within 15s', !!badge, badge ? `text="${badge.trim()}"` : 'no badge');

// Capture network calls to /clips/add_image during a drop.
let lastAddImageCall = null;
page.on('request', (req) => {
  if (req.url().includes('/clips/add_image')) {
    lastAddImageCall = req.url();
  }
});

// Try a real drop via Playwright on the first asset.
const asset = page.locator('.asset-item').first();
const assetBox = await asset.boundingBox();
const v1 = page.locator('[data-track-content="v1"]').first();
const v1Box = await v1.boundingBox();
if (assetBox && v1Box) {
  await page.mouse.move(assetBox.x + assetBox.width / 2, assetBox.y + assetBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(v1Box.x + 200, v1Box.y + v1Box.height / 2, { steps: 10 });
  await page.mouse.up();
  await sleep(2000);
} else {
  console.log('  (skipping drop — no asset/v1 bbox)');
}

if (lastAddImageCall) {
  const u = new URL(lastAddImageCall);
  const sid = u.searchParams.get('sessionId');
  const rev = u.searchParams.get('baseRevision');
  check('Drop request carries sessionId', !!sid && sid !== 'null',
    sid ? `sessionId=${sid.slice(0,8)}…, rev=${rev}` : 'MISSING sessionId');
} else {
  check('Drop fired /clips/add_image', false, 'no request captured — drag probably failed in jsdom-less CDP');
}

// === Scenario 2: Drag math (pointer-only, scroll-independent) ===
console.log('\n[2] Drag coordinate invariance');

const clip = page.locator('[data-track-content="v1"] .clip').first();
const cBox = await clip.boundingBox();
if (cBox) {
  // Reset scroll, then drag 50px right.
  await page.evaluate(() => {
    const c = document.querySelector('.timeline-content');
    if (c) c.scrollLeft = 0;
  });
  await sleep(300);
  const startX = cBox.x + 10;
  const y = cBox.y + cBox.height / 2;
  // Capture the move's payload via the [YROLL-DRAG] console log.
  let dragPayload = null;
  page.on('console', (msg) => {
    if (msg.text().startsWith('[YROLL-DRAG]') && !dragPayload) {
      try { dragPayload = JSON.parse(msg.text().slice('[YROLL-DRAG] '.length)); }
      catch { /* ignore */ }
    }
  });
  await page.mouse.move(startX, y);
  await page.mouse.down();
  await page.mouse.move(startX + 50, y, { steps: 10 });
  // Inject extra scroll via the ContentViewport directly. The
  // pointer-only invariant says this MUST NOT influence the frame
  // delta.
  await page.evaluate(() => {
    const c = document.querySelector('.timeline-content');
    if (c) c.scrollLeft = 300;
  });
  await page.mouse.up();
  await sleep(1500);
  if (dragPayload) {
    const expected = Math.round(50 / dragPayload.pxPerFrame);
    check('frame delta = pointer_delta / pxPerFrame',
      dragPayload.deltaFrame === expected,
      `deltaFrame=${dragPayload.deltaFrame} expected≈${expected} pxPerFrame=${dragPayload.pxPerFrame}`);
    check('viewport scroll did NOT amplify the frame delta',
      dragPayload.deltaFrame === dragPayload.lastPreviewFrame - dragPayload.originalFrame,
      'preview frame equals deltaFrame (no extra amplification)');
  } else {
    check('captured drag payload', false, 'no [YROLL-DRAG] console log');
  }
} else {
  check('found a draggable clip', false, 'no .clip in v1');
}

console.log(`\n${passed} passed, ${failed} failed`);
await browser.close();
process.exit(failed === 0 ? 0 : 1);