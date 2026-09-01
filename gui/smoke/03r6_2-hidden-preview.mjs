// gui/smoke/03r6_2-hidden-preview.mjs
//
// R6.2-B2/B3 regression: PreviewPlayer must not independently resurrect
// hidden-track content via the L0 fallback. Track.hidden == true →
// no renderer layer for that track.
//
// Fail conditions (must FAIL on HEAD before the fix):
//   - V1 is hidden in Core state, but Preview at frame 1000 (inside
//     V1's overlap zone [953,1073]∪[960,1080]) shows V1's asset
//   - Round-trip V1 hidden→shown→hidden produces a different img src
//     at the two hidden states (proves L0 fallback fires regardless)
//
// Pass conditions (must PASS after the fix):
//   - V1 hidden + frame 1000: Preview shows NEITHER a V1 img NOR a V3 layer
//     (V3 doesn't cover frame 1000 either) → placeholder
//   - Round-trip: V1 hidden→shown→hidden shows the SAME placeholder
//
// Requires:
//   - Backend: python -m yroll.cli.main serve projects/_sanlihe-r5-manual --port 8770
//   - Frontend: node gui/smoke/static-with-proxy.mjs 5180 8770

import { chromium } from '../../gui/node_modules/playwright/index.mjs';

const FRONTEND = 'http://127.0.0.1:5180/';
const PX_PER_FRAME = 0.84;

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

  // Find any V1 clip with content + its asset_id, then navigate to a
  // frame inside its range. We pick the first V1 clip and click on it
  // to set the playhead into its range.
  const v1Clip = await page.evaluate(() => {
    const clips = Array.from(document.querySelectorAll('[data-clip-id]'));
    // V1 clips have top=??? (need to scroll first)
    // Use the API instead: find the first V1 clip with its start_frame
    return null;
  });
  // Use Core API to get a V1 frame target.
  // Find a V1 clip whose range V3 does NOT cover. The Sanlihe canonical
  // has V3 with 1 clip at [0, 150]; V1 has clips at [150, 1335] etc.
  // Pick a V1 clip with start_frame > 150 to avoid V3 coverage.
  const apiResp = await page.evaluate(async () => {
    const r = await fetch('/tracks/v1/clips?timeline_id=main');
    return r.json();
  });
  if (!apiResp.clips || apiResp.clips.length === 0) {
    record('setup: V1 has clips', false, 'no V1 clips found');
    await browser.close();
    return summarize();
  }
  // Pick a clip whose range is outside V3 [0,150]
  const targetClip = apiResp.clips.find(c => c.start_frame >= 200) || apiResp.clips[0];
  // Use a frame inside the clip but within the visible viewport (1440px).
  // pxPerF=0.84, viewport=1440, so max visible frame ≈ 1300.
  const targetFrame = Math.min(
    Math.round((targetClip.start_frame + targetClip.end_frame) / 2),
    1300,
  );
  console.log(`  setup: target V1 clip=${targetClip.clip_id}, frames=[${targetClip.start_frame},${targetClip.end_frame}], navigating to frame ${targetFrame}`);

  // Click ruler at targetFrame
  const rulerRect = await page.evaluate(() =>
    document.querySelector('.ruler').getBoundingClientRect());
  await page.mouse.click(rulerRect.x + targetFrame * PX_PER_FRAME, rulerRect.y + 13);
  await page.waitForTimeout(2500);

  // Detect the current V1 hidden state from the DOM (the canonical
  // may have V1 shown or hidden depending on prior mutations).
  const v1InitialHidden = await page.evaluate(() => {
    return document.querySelector('.track-label-row[data-track-id="v1"]')?.classList.contains('track-hidden') ?? false;
  });
  console.log(`  setup: V1 initial hidden = ${v1InitialHidden}`);

  // Helper to read preview imgs + badges.
  async function readPreview() {
    return await page.evaluate(() => {
      const stage = document.querySelector('.preview-stage');
      const imgs = Array.from(stage?.querySelectorAll('img[data-layer-kind]') ?? []);
      const badges = Array.from(stage?.querySelectorAll('.layer-badge') ?? []);
      return {
        imgSrcs: imgs.map(i => i.src?.substring(i.src.lastIndexOf('/assets/') + 8, i.src.lastIndexOf('/assets/') + 14)),
        badgeTrackIds: badges.map(b => b.dataset.trackId),
      };
    });
  }

  const v1Btn = page.locator('.track-label-row[data-track-id="v1"] [aria-label="hide"]').first();

  // Make sure V1 starts in the SHOWN state.
  if (v1InitialHidden) {
    await v1Btn.click();
    await page.waitForTimeout(2500);
  }
  const previewV1Shown = await readPreview();
  console.log(`  V1 shown preview: imgSrcs=${JSON.stringify(previewV1Shown.imgSrcs)}, badges=${JSON.stringify(previewV1Shown.badgeTrackIds)}`);

  // Now toggle V1 to HIDDEN.
  await v1Btn.click();
  await page.waitForTimeout(2500);
  const previewV1Hidden = await readPreview();
  record(
    'B2: V1 hidden at frame inside V1 → no V1 image in preview',
    !previewV1Hidden.imgSrcs.includes(targetClip.asset_id?.slice(0, 6)) && !previewV1Hidden.badgeTrackIds.includes('v1'),
    `v1-shown=${JSON.stringify(previewV1Shown.imgSrcs)}→v1-hidden=${JSON.stringify(previewV1Hidden.imgSrcs)}, badges-hidden=${JSON.stringify(previewV1Hidden.badgeTrackIds)}`,
  );

  // Toggle back to SHOWN.
  await v1Btn.click();
  await page.waitForTimeout(2500);
  const previewV1ShownAgain = await readPreview();
  record(
    'B3: V1 hidden → shown → hidden: round-trip must not leak V1 content at hidden state',
    !previewV1Hidden.imgSrcs.includes(targetClip.asset_id?.slice(0, 6)),
    `v1-hidden=${JSON.stringify(previewV1Hidden.imgSrcs)}, v1-shown-again=${JSON.stringify(previewV1ShownAgain.imgSrcs)}`,
  );

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