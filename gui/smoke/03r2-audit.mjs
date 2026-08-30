// GUI-03R2 audit (no code changes yet).
// Connect via CDP to running Chrome; reproduce 8 user failures with measurements.
import { chromium } from 'playwright';

const WS = process.argv[2] || 'ws://localhost:9222/devtools/page/729F14FDFD3CC102672CF5A06C';
const URL = 'http://localhost:5173/';

function log(...a) { console.log('[AUDIT]', ...a); }
function header(s) { console.log('\n=== ' + s + ' ==='); }

const browser = await chromium.connectOverCDP('http://localhost:9222');
const ctx = browser.contexts()[0];
let page;
for (const p of ctx.pages()) {
  if (p.url().includes('localhost:5173')) { page = p; break; }
}
if (!page) throw new Error('no YROLL tab');
log('connected to', page.url());

// Acquire EDIT lease so mutations don't 403
await page.evaluate(async () => {
  const r = await fetch('/lease/acquire?actor=audit&mode=edit&actorId=audit-03r2');
  const j = await r.json();
  window.__sid = j.sessionId;
  return j.sessionId;
});
log('lease sid', await page.evaluate(() => window.__sid));

// ---------- measurements: P0-A frame-0 alignment ----------
header('P0-A: frame-0 alignment (ruler / playhead / clip / track-content)');
const origin = await page.evaluate(() => {
  const ruler = document.querySelector('.ruler');
  const playhead = document.querySelector('.playhead-full');
  const trackContent = document.querySelector('.track-content');
  const trackRow = document.querySelector('.track-row');
  const timelineBody = document.querySelector('.timeline-body');
  const minimap = document.querySelector('.minimap');
  const r = (el) => {
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return { left: b.left, top: b.top, right: b.right, width: b.width, height: b.height,
             scrollLeft: el.scrollLeft ?? null };
  };
  const rulerTicks = Array.from(document.querySelectorAll('.ruler .tick')).slice(0,3).map((el)=>({
    text: el.textContent, left: el.getBoundingClientRect().left,
    styleLeft: el.style.left,
  }));
  const playheadStyle = playhead ? playhead.getAttribute('style') : null;
  // trackContent LEFT (the x where content actually starts in screen pixels)
  const firstClip = document.querySelector('.track-content .clip');
  const clipRect = firstClip ? firstClip.getBoundingClientRect() : null;
  return {
    ruler: r(ruler), playhead: r(playhead), trackContent: r(trackContent),
    trackRow: r(trackRow), timelineBody: r(timelineBody), minimap: r(minimap),
    rulerTicks, playheadStyle, firstClipRect: clipRect,
    LABEL_GUTTER_PX: 80,
    pxPerSec: 30, fpsNum: 30, fpsDen: 1,
  };
});
console.log(JSON.stringify(origin, null, 2));

// ---------- P0-B: asset drag (image and video) ----------
header('P0-B: try a simulated drag from AssetPanel → track-content');
// Find first image asset + first video asset
const draggables = await page.evaluate(() => {
  return Array.from(document.querySelectorAll('.asset-item[draggable]')).map((el) => {
    const asset = el.querySelector('.asset-name')?.textContent;
    const dragStart = el.ondragstart !== null && el.ondragstart !== undefined;
    return { asset, dragStartAttached: dragStart, classList: el.className };
  });
});
console.log('draggable asset count:', draggables.length, 'first:', draggables[0]);

// Use Playwright's drag API: pick the first video asset and the first track-content
const firstImage = await page.locator('.asset-item[draggable]').filter({ has: page.locator('.asset-meta') }).first();
const allAssets = await page.locator('.asset-item[draggable]').all();
log('total draggable assets:', allAssets.length);

// Drag from asset[0] (video) to track-content (use second-to-last track since v1 may be busy)
async function tryDrag(srcIdx, label) {
  if (allAssets.length <= srcIdx) {
    log(label, 'SKIP — not enough assets');
    return;
  }
  const target = await page.evaluate(() => {
    const contents = Array.from(document.querySelectorAll('.track-content'));
    if (!contents.length) return null;
    const b = contents[0].getBoundingClientRect();
    return { x: b.left + 200, y: b.top + b.height / 2, trackId: contents[0].dataset.trackContent };
  });
  if (!target) { log(label, 'no track-content'); return; }
  log(label, 'target=', target);
  // Use page.dragAndDrop via selectors
  try {
    await allAssets[srcIdx].dragTo(page.locator(`[data-track-content="${target.trackId}"]`), {
      sourcePosition: { x: 80, y: 10 }, targetPosition: { x: 200, y: 30 },
    });
    log(label, 'dragAndDrop dispatched');
  } catch (e) {
    log(label, 'DRAG ERROR:', e.message.slice(0, 200));
  }
}
await tryDrag(0, 'image drag (assumed asset 0)');
await page.waitForTimeout(800);
// Read project state
const after = await page.evaluate(async () => {
  const r = await fetch('/project');
  const p = await r.json();
  const tl = (p.timelines || []).find(t => t.timeline_id === p.active_timeline_id) || p.timelines[0];
  return {
    timelineId: tl.timeline_id, clipCount: Object.keys(p.clips).length,
    tracks: tl.tracks.map((t) => ({ id: t.track_id, kind: t.kind, n: t.clip_ids.length })),
  };
});
console.log('after-drag state:', JSON.stringify(after, null, 2));

// ---------- P0-C: pointer delta → frame delta (manual measurement) ----------
header('P0-C: pointer delta → frame delta (no actual move)');
const dragMath = await page.evaluate(() => {
  // Synthetic: simulate moving a clip by N px and capture candidate frame.
  const clip = document.querySelector('.clip');
  if (!clip) return { error: 'no clip' };
  const tlRect = document.querySelector('.track-content').getBoundingClientRect();
  const pxPerSec = 30; const fpsNum = 30, fpsDen = 1;
  const pxPerFrame = pxPerSec * fpsDen / fpsNum;
  // simulate pointer delta scenarios
  const scenarios = [];
  for (const px of [1, 2, 4, 8, 16, 32, 50, 80, 120]) {
    const deltaFrame = Math.round(px / pxPerFrame);
    scenarios.push({ px, pxPerFrame, deltaFrame, jumpFrames: deltaFrame });
  }
  return { scenarios, tlLeft: tlRect.left, clipLeft: clip.getBoundingClientRect().left };
});
console.log(JSON.stringify(dragMath, null, 2));

// ---------- P0-D: collision target track ----------
header('P0-D: same-track collision observation (use Playwright atomic move)');
// Add a clip via API directly (bypassing GUI bugs) and observe
const collisionProbe = await page.evaluate(async () => {
  // get v1 track and add two overlapping video clips
  const proj = await (await fetch('/project')).json();
  const tl = proj.timelines.find(t => t.timeline_id === 'main');
  const v1 = tl.tracks.find(t => t.track_id === 'v1');
  if (!v1 || !v1.clip_ids.length) return { error: 'v1 empty' };
  const firstClip = proj.clips[v1.clip_ids[0]];
  // try to move it overlapping onto v1 (this MUST be rejected by Core with 400)
  const sid = window.__sid;
  const rev = (await (await fetch('/operations')).json()).length;
  const dur = firstClip.timeline_range.end - firstClip.timeline_range.start;
  const r = await fetch('/clips', {
    method: 'POST',
    params: { sessionId: sid, baseRevision: rev, timeline_id: 'main' },
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      asset_id: firstClip.asset_id,
      source_start: 0, source_end: dur,
      timeline_start: firstClip.timeline_range.start + 0.1,  // overlap
      track_id: 'v1', trackId: 'v1',
    }),
  });
  return { status: r.status, body: await r.text() };
});
console.log('core overlap rejection:', JSON.stringify(collisionProbe));

// ---------- P0-E + P0-F: playback playhead + preview progress ----------
header('P0-E/F: playhead visibility + preview progress during playback');
const playbackProbe = await page.evaluate(async () => {
  // Record playhead element geometry vs track content
  const playhead = document.querySelector('.playhead-full');
  const trackContent = document.querySelector('.track-content');
  const minimap = document.querySelector('.minimap-playhead');
  const tb = document.querySelector('.timeline-body');
  const r = (el) => el ? { left: el.getBoundingClientRect().left, top: el.getBoundingClientRect().top,
                           width: el.getBoundingClientRect().width, style: el.getAttribute('style') } : null;
  return { playhead: r(playhead), trackContent: r(trackContent), minimap: r(minimap),
           tb: r(tb), playheadPresent: !!playhead };
});
console.log(JSON.stringify(playbackProbe, null, 2));

// ---------- P1-G: wheel zoom step ----------
header('P1-G: wheel zoom current step');
const wheelZoom = await page.evaluate(() => {
  const slider = document.querySelector('input[type=range][min="4"]');
  // Read current pxPerSec (the slider value)
  return slider ? { value: slider.value, min: slider.min, max: slider.max, step: slider.step } : null;
});
console.log(JSON.stringify(wheelZoom));

// Done
log('AUDIT DONE');
await browser.close();
