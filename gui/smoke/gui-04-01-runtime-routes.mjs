// gui/smoke/gui-04-01-runtime-routes.mjs
//
// GUI-04 batch 04-01: Runtime Route Integrity
//
// Hard constraint from user:
//   "Do NOT blindly 'fix' /clips 404. First establish the actual
//    browser runtime chain: GUI bundle → request URL → proxy → FastAPI
//    route → response. If the 404 is caused by mixed/stale runtime
//    components rather than current code, document it and do not modify
//    a correct endpoint just to make the smoke green."
//
// Chain (real-browser, through vite/static-with-proxy.mjs):
//   chromium (cdp 9222) → frontend (5180) → static-with-proxy.mjs
//                                       → backend FastAPI (8770)
//   We test the chain by exercising 3 routes from a real browser
//   page: POST /clips, POST /history/undo, POST /revert.
//
// Two phases (smoke handles a held lease gracefully):
//
//   Phase A — Route REACHABILITY (always runs; no lease required):
//     POST each endpoint with empty body and NO baseRevision.
//     The Mutation Gate MUST reject with a JSON 400/403 from
//     uvicorn. A bare "not found" string from python http.server
//     would mean the proxy did NOT forward the request to FastAPI
//     — that is the symptom we caught before the GUI-04 04-01 fix.
//
//   Phase B — Full mutation (only if the smoke can acquire a lease):
//     Acquire lease → POST /clips (frame-native) → 200 → POST
//     /history/undo → 200 → POST /revert → 200 → release lease.
//
//   Either phase succeeding proves the chain is intact.
//
// Usage:
//   chromium --remote-debugging-port=9222 &
//   python -m yroll.cli.main serve projects/_sanlihe-r5-manual --port 8770 &
//   node gui/smoke/static-with-proxy.mjs 5180 8770 &
//   node gui/smoke/gui-04-01-runtime-routes.mjs

import { chromium } from '../../gui/node_modules/playwright/index.mjs';

const FRONTEND = 'http://127.0.0.1:5180/';

const results = [];
function record(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log(`${ok ? '✓ PASS' : '✗ FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
}

function shortHash(s) {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return ('00000000' + (h >>> 0).toString(16)).slice(-8);
}

function isFastApiJson(body) {
  // The bare-python "not found" / "proxy error" bodies are plain
  // text. FastAPI error responses are always JSON {"detail": ...}.
  if (!body) return false;
  const t = body.trim();
  return t.startsWith('{') || t.startsWith('[');
}

async function main() {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
  const ctx = browser.contexts()[0] || await browser.newContext();
  const page = ctx.pages()[0] || await ctx.newPage();

  const badResponses = [];
  const endpointBodies = {};
  page.on('response', (r) => {
    if (r.status() >= 400) {
      const headers = r.headers();
      badResponses.push({
        status: r.status(),
        method: r.request().method(),
        url: r.url(),
        server: headers['server'] || '(none)',
      });
    }
  });
  page.on('response', async (r) => {
    const path = new URL(r.url()).pathname;
    if (['/clips', '/history/undo', '/revert', '/lease/acquire'].includes(path)
        && r.status() >= 400) {
      try { endpointBodies[path] = await r.text(); } catch {}
    }
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(FRONTEND, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForSelector('.timeline-content', { timeout: 15000 });
  await page.waitForTimeout(2000);

  // ---- Bundle SHA evidence ----
  const bundleInfo = await page.evaluate(() => {
    const scripts = Array.from(document.querySelectorAll('script[src]'));
    const main = scripts.map(s => s.getAttribute('src')).find(s => s && s.includes('index-'));
    return { mainScript: main || '(none)' };
  });
  let bundleBody = '';
  if (bundleInfo.mainScript && bundleInfo.mainScript !== '(none)') {
    try {
      bundleBody = await page.evaluate(async (url) => {
        const r = await fetch(url);
        return await r.text();
      }, bundleInfo.mainScript);
    } catch (e) {
      bundleBody = '(fetch failed: ' + e.message + ')';
    }
  }
  const bundleSha = bundleBody ? shortHash(bundleBody) : '(no bundle)';

  console.log('');
  console.log('=== Runtime chain evidence ===');
  console.log(`frontend bundle (vite-built JS the browser ran): ${bundleInfo.mainScript}`);
  console.log(`bundle content hash (32-bit djb2):              ${bundleSha}`);
  console.log(`backend port:                                   8770  (yroll serve, FastAPI + StaticFiles)`);
  console.log(`proxy layer:                                    static-with-proxy.mjs on 5180 → 8770`);
  console.log(`vite dev proxy (alt path):                      gui/vite.config.ts catch-all → 8765`);
  console.log('');

  // ---- Phase A: route REACHABILITY (no lease required) ----
  const phaseA = await page.evaluate(async () => {
    const out = { posts: [] };

    async function probe(label, url, init) {
      const r = await fetch(url, init);
      const t = await r.text();
      out.posts.push({
        label, url,
        status: r.status,
        server: r.headers.get('server') || '(none)',
        ct: r.headers.get('content-type') || '(none)',
        body: t.length > 400 ? t.slice(0, 400) + '…' : t,
      });
    }

    // Each of these is a POST without baseRevision. The Mutation
    // Gate MUST reject with a JSON 400/403 from FastAPI.
    await probe('A.POST /clips',          '/clips',
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    await probe('A.POST /history/undo',   '/history/undo',
      { method: 'POST' });
    await probe('A.POST /revert',         '/revert',
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });

    return out;
  });

  console.log('=== Phase A — route reachability ===');
  for (const p of phaseA.posts) {
    console.log(`${p.label.padEnd(22)} ${String(p.status).padEnd(4)} ${p.server.padEnd(8)} ${p.url}`);
    if (p.status >= 400) console.log(`  body: ${p.body}`);
  }

  for (const p of phaseA.posts) {
    const fastApi = (p.server || '').toLowerCase().includes('uvicorn')
                  && isFastApiJson(p.body);
    record(
      `${p.label} reaches FastAPI (not bare-python 404)`,
      fastApi,
      `status=${p.status} server="${p.server}" ct="${p.ct}"`,
    );
  }

  // ---- Phase B: full mutation (only if lease can be acquired) ----
  console.log('');
  console.log('=== Phase B — full mutation (lease required) ===');

  const phaseB = await page.evaluate(async () => {
    const out = { posts: [], leaseStatus: 'unknown' };

    // Try to acquire lease. If someone holds it, we can't probe
    // mutations — Phase A still proved the chain is intact.
    const acq = await fetch('/lease/acquire?actor=human&mode=edit&baseRevision=-1&humanLabel=gui-04-01-smoke',
      { method: 'POST' });
    const acqBody = await acq.text();
    if (acq.status !== 200) {
      out.leaseStatus = `acquire_${acq.status}`;
      out.acquireBody = acqBody;
      return out;
    }
    const acqJson = JSON.parse(acqBody);
    out.sessionId = acqJson.sessionId;
    out.baseRevision = acqJson.baseRevision;
    out.leaseStatus = 'acquired';

    // Find a video asset for addClip.
    const proj = await fetch('/project').then(r => r.json());
    const fps = proj.fps_num || 30;
    const asset = (proj.assets || []).find(a => a.type === 'video');
    if (!asset) {
      out.leaseStatus = 'no_video_asset';
      // Release the lease before returning.
      await fetch('/lease/release?sessionId=' + encodeURIComponent(out.sessionId), { method: 'POST' });
      return out;
    }
    const durSec = asset.identity?.duration_sec || 5;
    const durFrame = Math.round(durSec * fps);

    async function probe(label, url, init) {
      const r = await fetch(url, init);
      const t = await r.text();
      out.posts.push({
        label, url,
        status: r.status,
        server: r.headers.get('server') || '(none)',
        body: t.length > 400 ? t.slice(0, 400) + '…' : t,
      });
    }

    const sid = out.sessionId;
    const brev = out.baseRevision;

    // ---- B.POST /clips (frame-native, real mutation) ----
    await probe('B.POST /clips', `/clips?sessionId=${encodeURIComponent(sid)}&baseRevision=${brev}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          asset_id: asset.asset_id,
          source_start_frame: 0,
          source_end_frame: durFrame,
          timeline_start_frame: 0,
          track_id: null,
          why: 'gui-04-01 smoke probe',
        }) });

    // ---- B.POST /history/undo ----
    await probe('B.POST /history/undo', `/history/undo?sessionId=${encodeURIComponent(sid)}&baseRevision=${brev}&why=gui-04-01`,
      { method: 'POST' });

    // ---- B.POST /revert (low-level compat endpoint per plan §5.2) ----
    const ops = await fetch('/operations').then(r => r.json());
    const last = ops[ops.length - 1];
    if (last) {
      await probe('B.POST /revert', '/revert',
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ operation_id: last.operation_id, why: 'gui-04-01 smoke revert' }) });
    }

    // Release lease.
    await fetch('/lease/release?sessionId=' + encodeURIComponent(sid), { method: 'POST' });

    return out;
  });

  if (phaseB.leaseStatus === 'acquired') {
    for (const p of phaseB.posts) {
      console.log(`${p.label.padEnd(22)} ${String(p.status).padEnd(4)} ${p.server.padEnd(8)} ${p.url}`);
      if (p.status >= 400) console.log(`  body: ${p.body}`);
    }
    const findP = (label) => phaseB.posts.find(p => p.label === label);
    const clips = findP('B.POST /clips');
    const undo  = findP('B.POST /history/undo');
    const revert = findP('B.POST /revert');
    record('B.POST /clips → 200',         clips && clips.status === 200,
      clips ? `status=${clips.status}` : 'no /clips probe recorded');
    record('B.POST /history/undo → 200',  undo && undo.status === 200,
      undo ? `status=${undo.status}` : 'no /history/undo probe recorded');
    record('B.POST /revert → 200',        revert && revert.status === 200,
      revert ? `status=${revert.status}` : 'no /revert probe recorded');
  } else {
    console.log(`(skipped — lease status: ${phaseB.leaseStatus}${phaseB.acquireBody ? ' | ' + phaseB.acquireBody : ''})`);
    // Phase B is informational, not a hard fail. In a clean test
    // environment Phase A alone is sufficient to prove the chain.
    // We log it but do not increment the fail counter.
    console.log(`  (informational — Phase A already verified the chain)`);
  }

  // ---- No unrelated PROXY-FAIL ≥400 responses during probe ----
  // A "proxy-fail" 4xx is one that the proxy emitted itself (bare
  // "not found" / "proxy error" / "forbidden" text with no
  // `server: uvicorn` header). That means the request never reached
  // FastAPI — exactly the GUI-04 04-01 bug class. Legitimate FastAPI
  // 4xx (assets registered but file missing on disk, etc.) is fine
  // and shows `server: uvicorn`.
  const ourProbes = new Set(['/clips', '/history/undo', '/revert', '/lease/acquire']);
  const proxyFails = badResponses.filter(r => {
    const path = new URL(r.url).pathname;
    if (ourProbes.has(path)) return false;
    const server = (r.server || '').toLowerCase();
    return !server.includes('uvicorn');
  });
  record(
    'no proxy-fail ≥400 responses during probe',
    proxyFails.length === 0,
    proxyFails.length
      ? `${proxyFails.length} proxy-fail error(s); first: ${proxyFails[0].status} ${proxyFails[0].url}`
      : `0 proxy-fail errors. ${badResponses.length} error(s) total — all from FastAPI itself (server=uvicorn).`,
  );

  await browser.close();

  const fails = results.filter(r => !r.ok);
  console.log('');
  console.log(`=== SUMMARY: ${results.length - fails.length}/${results.length} passed ===`);
  if (fails.length) {
    console.log('FAILURES:');
    for (const f of fails) console.log(`  ${f.name} — ${f.detail}`);
    process.exit(1);
  }
}

await main();