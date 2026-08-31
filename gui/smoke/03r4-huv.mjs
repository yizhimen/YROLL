// GUI-03R4 Human Usability Validation (HUV)
//
// 10 interaction scenarios the user requested for human validation:
//  1. drag clip and keep it visible
//  2. drag near viewport edge
//  3. marquee 3–5 clips
//  4. Delete selection
//  5. Ripple Delete
//  6. Close Gap
//  7. Space play/pause
//  8. Preview multi-layer
//  9. hidden upper layer reveals lower layer
// 10. Output Canvas aspect changes
//
// Each scenario reports a DOM state; the human inspector reads
// the printed state and judges.
//
// Usage: node gui/smoke/03r4-huv.mjs
// Prereqs: yroll serve on 8765, W-D proxy on 5180, chromium on 9222.

import { setTimeout as sleep } from 'node:timers/promises';

const FRONTEND = process.env.FRONTEND ?? 'http://127.0.0.1:5180';
const BACKEND = process.env.BACKEND ?? 'http://127.0.0.1:8765';
const CDP = process.env.CDP ?? 'http://127.0.0.1:9222';

console.log('=== GUI-03R4 HUMAN USABILITY VALIDATION ===');
console.log(`frontend=${FRONTEND}  backend=${BACKEND}  cdp=${CDP}\n`);

const WebSocket = (await import('ws')).default;
const newTab = await fetch(`${CDP}/json/new?${encodeURIComponent(FRONTEND)}`,
  { method: 'PUT' }).then((r) => r.json());
const cdp = new WebSocket(newTab.webSocketDebuggerUrl);
await new Promise((r, e) => { cdp.once('open', r); cdp.once('error', e); });
let nextId = 1;
const pending = new Map();
cdp.on('message', (m) => {
  const d = JSON.parse(m.toString());
  if (d.id && pending.has(d.id)) {
    const { resolve, reject } = pending.get(d.id);
    pending.delete(d.id);
    if (d.error) reject(new Error(JSON.stringify(d.error)));
    else resolve(d.result);
  }
});
function send(method, params = {}) {
  const id = nextId++;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    cdp.send(JSON.stringify({ id, method, params }));
  });
}
async function eval_(expr) {
  const r = await send('Runtime.evaluate', {
    expression: expr, returnByValue: true, awaitPromise: true,
  });
  if (r.result.exceptionDetails) {
    return { __error: JSON.stringify(r.result.exceptionDetails) };
  }
  return r.result.value;
}

await send('Page.enable');
await send('Runtime.enable');
await send('Page.navigate', { url: FRONTEND });
await sleep(8000);

async function snapshot(label) {
  const s = await eval_(`(() => ({
    url: location.href,
    title: document.title,
    assetCount: document.querySelectorAll('.asset-item').length,
    trackRowCount: document.querySelectorAll('.track-label-row').length,
    visibleTrackRows: Array.from(document.querySelectorAll('.track-label-row'))
      .filter(r => r.style.display !== 'none').length,
    trackIds: Array.from(document.querySelectorAll('.track-label-row'))
      .filter(r => r.style.display !== 'none')
      .map(r => r.querySelector('.track-id')?.textContent),
    clipCount: document.querySelectorAll('.clip').length,
    playheadStatus: document.querySelector('[data-testid=playhead-status]')?.textContent?.trim(),
    sliderValue: document.querySelector('input[type="range"][min="1"][max="120"]')?.value,
    compositeLayers: document.querySelectorAll('.composite-stage img, .composite-stage video').length,
    compositeZ: Array.from(document.querySelectorAll('.composite-stage img, .composite-stage video'))
      .map(el => el.style.zIndex),
    placeholder: document.querySelector('.placeholder')?.textContent?.trim(),
  }))()`);
  console.log(`\n--- ${label} ---`);
  console.log(JSON.stringify(s, null, 2));
  return s;
}

// === Baseline ===
await snapshot('0. BASELINE');

console.log('\n=== 1. drag clip and keep it visible ===');
const drag1 = await eval_(`(async () => {
  const v1Row = Array.from(document.querySelectorAll('.track-content[data-track-content]'))
    .find(el => el.dataset.trackContent === 'v1');
  if (!v1Row) return { error: 'no v1 row' };
  const clip = v1Row.querySelector('.clip');
  if (!clip) return { error: 'no clip in v1' };
  const beforeRect = clip.getBoundingClientRect();
  const startX = beforeRect.left + 10;
  const startY = beforeRect.top + beforeRect.height / 2;
  clip.dispatchEvent(new PointerEvent('pointerdown', {
    pointerId: 1, button: 0, bubbles: true, clientX: startX, clientY: startY,
  }));
  await new Promise(r => setTimeout(r, 30));
  window.dispatchEvent(new PointerEvent('pointermove', {
    pointerId: 1, bubbles: true, clientX: startX + 80, clientY: startY,
  }));
  await new Promise(r => setTimeout(r, 30));
  window.dispatchEvent(new PointerEvent('pointerup', {
    pointerId: 1, bubbles: true, clientX: startX + 80, clientY: startY,
  }));
  await new Promise(r => setTimeout(r, 1500));
  const clipAfter = v1Row.querySelector('.clip');
  return {
    beforeLeft: beforeRect.left.toFixed(1),
    afterRectLeft: clipAfter ? clipAfter.getBoundingClientRect().left.toFixed(1) : null,
    afterStyleLeft: clipAfter?.style?.left,
  };
})()`);
console.log(JSON.stringify(drag1, null, 2));
await snapshot('After drag');

console.log('\n=== 2. drag near viewport edge ===');
const drag2 = await eval_(`(async () => {
  const v1Row = Array.from(document.querySelectorAll('.track-content[data-track-content]'))
    .find(el => el.dataset.trackContent === 'v1');
  const clip = v1Row.querySelector('.clip');
  const rect = clip.getBoundingClientRect();
  const startX = rect.left + 10;
  const startY = rect.top + rect.height / 2;
  const endX = window.innerWidth - 5;
  clip.dispatchEvent(new PointerEvent('pointerdown', {
    pointerId: 1, button: 0, bubbles: true, clientX: startX, clientY: startY,
  }));
  for (let i = 0; i < 10; i++) {
    window.dispatchEvent(new PointerEvent('pointermove', {
      pointerId: 1, bubbles: true,
      clientX: startX + (endX - startX) * (i / 9), clientY: startY,
    }));
    await new Promise(r => setTimeout(r, 20));
  }
  window.dispatchEvent(new PointerEvent('pointerup', {
    pointerId: 1, bubbles: true, clientX: endX, clientY: startY,
  }));
  await new Promise(r => setTimeout(r, 1500));
  const clipAfter = v1Row.querySelector('.clip');
  return {
    vw: window.innerWidth,
    afterStyleLeft: clipAfter?.style?.left,
    afterRectLeft: clipAfter ? clipAfter.getBoundingClientRect().left.toFixed(1) : null,
    scrollLeft: document.querySelector('.timeline-content')?.scrollLeft,
  };
})()`);
console.log(JSON.stringify(drag2, null, 2));
await snapshot('After edge-drag');

console.log('\n=== 3. marquee 3-5 clips ===');
const marquee = await eval_(`(async () => {
  const v1Row = Array.from(document.querySelectorAll('.track-content[data-track-content]'))
    .find(el => el.dataset.trackContent === 'v1');
  const tcRect = v1Row.getBoundingClientRect();
  const clips = Array.from(v1Row.querySelectorAll('.clip'));
  if (clips.length < 5) return { error: 'v1 has <5 clips', count: clips.length };
  const rect0 = clips[0].getBoundingClientRect();
  const rect4 = clips[4].getBoundingClientRect();
  const startX = rect0.left - 10;
  const startY = tcRect.top + tcRect.height - 20;
  const endX = rect4.right + 10;
  const endY = tcRect.bottom - 5;
  v1Row.dispatchEvent(new PointerEvent('pointerdown', {
    pointerId: 1, button: 0, bubbles: true, clientX: startX, clientY: startY,
  }));
  for (let i = 1; i <= 10; i++) {
    const t = i / 10;
    window.dispatchEvent(new PointerEvent('pointermove', {
      pointerId: 1, bubbles: true,
      clientX: startX + (endX - startX) * t, clientY: startY + (endY - startY) * t,
    }));
    await new Promise(r => setTimeout(r, 20));
  }
  window.dispatchEvent(new PointerEvent('pointerup', {
    pointerId: 1, bubbles: true, clientX: endX, clientY: endY,
  }));
  await new Promise(r => setTimeout(r, 1000));
  const batchPanel = document.querySelector('.batch-panel');
  return {
    batchVisible: !!batchPanel,
    batchHeading: batchPanel?.querySelector('h3')?.textContent,
    rectCovered: [rect0.left.toFixed(1), rect4.right.toFixed(1)],
  };
})()`);
console.log(JSON.stringify(marquee, null, 2));
await snapshot('After marquee');

console.log('\n=== 4. Delete selection ===');
const delSel = await eval_(`(async () => {
  const batchPanel = document.querySelector('.batch-panel');
  if (!batchPanel) return { error: 'no batch panel (marquee failed?)' };
  const before = batchPanel.querySelector('h3')?.textContent;
  const buttons = Array.from(batchPanel.querySelectorAll('button'));
  const delBtn = buttons.find(b => b.textContent.includes('全部删除'));
  if (!delBtn) return { error: 'no 全部删除 button' };
  const origConfirm = window.confirm;
  window.confirm = () => true;
  delBtn.click();
  await new Promise(r => setTimeout(r, 1500));
  window.confirm = origConfirm;
  const batchAfter = document.querySelector('.batch-panel');
  return { before, afterBatchVisible: !!batchAfter };
})()`);
console.log(JSON.stringify(delSel, null, 2));
await snapshot('After Delete selection');

console.log('\n=== 5. Ripple Delete ===');
const ripple = await eval_(`(async () => {
  const clip = document.querySelector('.clip');
  if (!clip) return { error: 'no clip' };
  clip.dispatchEvent(new MouseEvent('click', { bubbles: true, ctrlKey: true }));
  await new Promise(r => setTimeout(r, 300));
  const inspector = document.querySelector('.inspector');
  const buttons = Array.from(inspector?.querySelectorAll('button') ?? []);
  const rippleBtn = buttons.find(b => b.textContent.includes('Ripple') && !b.textContent.includes('批量'));
  if (!rippleBtn) return { error: 'no Inspector Ripple button', available: buttons.map(b => b.textContent) };
  rippleBtn.click();
  await new Promise(r => setTimeout(r, 1500));
  return { ok: true };
})()`);
console.log(JSON.stringify(ripple, null, 2));
await snapshot('After Ripple Delete');

console.log('\n=== 6. Close Gap ===');
const closeGap = await eval_(`(async () => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const gapBtn = buttons.find(b => b.textContent.includes('批量关闭间隙'));
  if (!gapBtn) return { error: 'no 批量关闭间隙 button' };
  const origConfirm = window.confirm;
  window.confirm = () => true;
  gapBtn.click();
  await new Promise(r => setTimeout(r, 1500));
  window.confirm = origConfirm;
  return { ok: true };
})()`);
console.log(JSON.stringify(closeGap, null, 2));
await snapshot('After Close Gap');

console.log('\n=== 7. Space play/pause ===');
const space = await eval_(`(async () => {
  const playBtn = document.querySelector('.play-btn');
  const before = playBtn?.textContent?.trim();
  window.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }));
  await new Promise(r => setTimeout(r, 400));
  const after = playBtn?.textContent?.trim();
  return { before, after };
})()`);
console.log(JSON.stringify(space, null, 2));

console.log('\n=== 8. Preview multi-layer ===');
const pv0 = await fetch(`${BACKEND}/preview/at_frame?frame=0&timeline_id=main`).then(r => r.json());
console.log('frame 0 visual_layers tracks:',
  pv0.visual_layers.map(l => `${l.track_id}:z${l.layer_index}`).join(', '));
const pv200 = await fetch(`${BACKEND}/preview/at_frame?frame=200&timeline_id=main`).then(r => r.json());
console.log('frame 200 visual_layers tracks:',
  pv200.visual_layers.map(l => `${l.track_id}:z${l.layer_index}`).join(', '));
await snapshot('Multi-layer frame 0');

console.log('\n=== 9. hidden upper layer reveals lower layer ===');
const v3Before = pv0.visual_layers.some(l => l.track_id === 'v3');
const hideV3 = await eval_(`(async () => {
  const rows = Array.from(document.querySelectorAll('.track-label-row'))
    .filter(r => r.style.display !== 'none');
  const v3Row = rows.find(r => r.querySelector('.track-id')?.textContent === 'v3');
  if (!v3Row) return { error: 'no v3 row' };
  const buttons = v3Row.querySelectorAll('.track-icon-btn');
  if (buttons.length < 3) return { error: 'no buttons' };
  buttons[2].click();
  await new Promise(r => setTimeout(r, 1500));
  return { ok: true };
})()`);
console.log('hide action:', JSON.stringify(hideV3));
const pv0After = await fetch(`${BACKEND}/preview/at_frame?frame=0&timeline_id=main`).then(r => r.json());
const v3After = pv0After.visual_layers.some(l => l.track_id === 'v3');
console.log(`v3 in plan: before=${v3Before}, after=${v3After}`);
console.log('after visual_layers tracks:',
  pv0After.visual_layers.map(l => `${l.track_id}:z${l.layer_index}`).join(', '));

console.log('\n=== 10. Output Canvas aspect changes ===');
const aspect = await eval_(`(async () => {
  const out = {};
  for (const a of ['16:9', '9:16', '1:1', '4:3', '3:4']) {
    const btn = Array.from(document.querySelectorAll('.aspect-btn'))
      .find(b => b.textContent.trim() === a);
    if (!btn) { out[a] = 'no button'; continue; }
    btn.click();
    await new Promise(r => setTimeout(r, 300));
    const canvas = document.querySelector('.preview-pane div[style*="outline"]');
    out[a] = canvas ? {
      width: canvas.style.width,
      height: canvas.style.height,
    } : 'no canvas';
  }
  return out;
})()`);
console.log(JSON.stringify(aspect, null, 2));

await snapshot('FINAL');

console.log('\n=== DONE — human inspector: read each scenario\'s output ===');
process.exit(0);