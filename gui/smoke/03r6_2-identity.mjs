// gui/smoke/03r6_2-identity.mjs
//
// R6.2 final consistency: at 10 frames, verify that the set of TRACKS
// visible in the Timeline DOM matches the set of TRACKS in
// /preview/at_frame's visual_layers.
//
// We check at track level (not clip level) because:
//   - Half-open interval membership says only one clip can be active
//     per track at any frame, but the API and Timeline may pick
//     different clips when the same track has multiple clips covering
//     the same frame (a pre-existing overlap in the canonical fixture).
//   - Track-level membership is the user-visible question: does the
//     preview show all the visible tracks?
//
// Hidden tracks are excluded everywhere per R5/R6.2-B2/B3 invariants.
// Text/audio tracks are excluded from the visual-layer comparison
// (subtitles go to subtitle_texts, not visual_layers).

import { chromium } from '../../gui/node_modules/playwright/index.mjs';

const FRONTEND = 'http://127.0.0.1:5180/';

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
  await page.waitForTimeout(2000);

  // Derive pxPerFrame from c4c290d's DOM width (we know it's 150 frames
  // wide from Core). Robust to any ruler tick granularity.
  const PX_PER_FRAME = await page.evaluate(() => {
    const c = document.querySelector('[data-clip-id="c4c290d"]');
    if (c) {
      const w = parseFloat(c.style.width);
      if (w > 0) return w / 150;
    }
    return 0.84;
  });
  console.log(`  setup: pxPerFrame derived from c4c290d width = ${PX_PER_FRAME.toFixed(4)}`);

  const frames = [0, 50, 100, 200, 400, 800, 1500, 2200, 3000, 5000];
  const rulerRect = await page.evaluate(() =>
    document.querySelector('.ruler').getBoundingClientRect());

  for (const F of frames) {
    await page.mouse.click(rulerRect.x + F * PX_PER_FRAME, rulerRect.y + 13);
    await page.waitForTimeout(1500);

    // 1. Read Timeline DOM's visible (non-hidden, non-text/audio) tracks
    //    that have a RENDERABLE clip covering F. We pre-load the
    //    Core's asset → source_fps map so we can exclude clips whose
    //    assets lack source_fps (Core's GUI-02.3 invariant skips
    //    those from preview/at_frame).
    const timelineTracks = await page.evaluate(async ({ targetFrame, pxPerF }) => {
      // Pre-fetch the Core project once for asset metadata.
      const proj = await fetch('/project').then(r => r.json());
      const fps = proj.fps_num || 30;
      const clipSrcFps = {};
      for (const [cid, c] of Object.entries(proj.clips || {})) {
        const a = (proj.assets || []).find(x => x.asset_id === c.asset_id);
        clipSrcFps[cid] = a?.source_fps ?? null;
      }
      // Helper: convert clip's timeline_range (seconds) to frames
      const toFrames = (sec) => Math.round(sec * fps);
      const clips = Array.from(document.querySelectorAll('[data-clip-id]'));
      const tracksWithCover = new Set();
      for (const c of clips) {
        const cid = c.dataset.clipId;
        const left = parseFloat(c.style.left) || 0;
        const width = parseFloat(c.style.width) || 0;
        const cstart = left / pxPerF;
        const cend = (left + width) / pxPerF;
        if (targetFrame >= cstart && targetFrame < cend) {
          const trackRow = c.closest('.track-row');
          const trackId = trackRow?.dataset.trackId || '';
          if (trackRow?.classList.contains('track-hidden')) continue;
          if (!trackId.startsWith('v')) continue;
          // Exclude clips whose asset is a video without source_fps
          // (Core's GUI-02.3 invariant). Image assets are fine even
          // without source_fps.
          if (clipSrcFps[cid] === null) {
            // Source fps may be null for images OR for videos-without-fps.
            // We need to know the asset type.
            // If we have the project's asset list cached, we can
            // check; otherwise treat unknown source_fps as
            // potentially-renderable (be conservative).
            const asset = (proj.assets || []).find(
              a => a.asset_id === (proj.clips[cid]?.asset_id));
            if (asset?.type === 'video') continue;  // video without fps
          }
          tracksWithCover.add(trackId);
        }
      }
      return [...tracksWithCover];
    }, { targetFrame: F, pxPerF: PX_PER_FRAME });

    // 2. Read API visual_layers' track_ids for this frame
    const atFrame = await page.evaluate(async (targetFrame) => {
      const r = await fetch(`/preview/at_frame?timeline_id=main&frame=${targetFrame}`);
      return r.json();
    }, F);
    const apiTracks = new Set(atFrame.visual_layers.map(l => l.track_id));

    // 3. Compare: every Timeline-visible track should appear in API visual_layers
    const timelineSet = new Set(timelineTracks);
    const onlyInTimeline = timelineTracks.filter(t => !apiTracks.has(t));

    if (onlyInTimeline.length > 0) {
      record(
        `F=${F}: timeline shows visual track(s) not in /preview/at_frame (BUG)`,
        false,
        `only-in-timeline=${JSON.stringify(onlyInTimeline)}, api-tracks=${[...apiTracks]}, is_black=${atFrame.is_black}`,
      );
    } else {
      record(
        `F=${F}: timeline visible tracks ⊆ /preview/at_frame visual_layers`,
        true,
        `timeline=${timelineTracks}, api=${[...apiTracks]}, is_black=${atFrame.is_black}`,
      );
    }
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