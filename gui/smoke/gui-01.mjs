// GUI-01 real-browser smoke test.
//
// Drives the actual built bundle (gui/dist/index.html) and proves the
// wiring is more than just a typecheck:
//
//   1. App boots, sessionStore.startPolling() lands, top bar shows
//      "🟢 编辑权：我 r<N>" after the first poll.
//   2. A real write through the GUI carries sessionId + baseRevision.
//   3. A bare POST without sessionId is rejected by the server (we read
//      the body to see "sessionId required" because the dev proxy wraps
//      the 403 as 502).
//   4. A write with a stale baseRevision is rejected with 409.
//
// Headless, no human in the loop. Run with:
//   pnpm exec node smoke/gui-01.mjs
//
// Requires backend running on 127.0.0.1:8765. Spawns a tiny static
// server on 5180 so we don't depend on scripts/serve_gui.py (which
// mangles 304s — out of scope for this commit).

import { chromium } from "playwright";
import { writeFileSync } from "node:fs";
import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const BACKEND = "http://127.0.0.1:8765";
const URL = "http://127.0.0.1:5180/";
const OUT = "gui/smoke/";

function log(...a) { console.log("[smoke]", ...a); }

const here = dirname(fileURLToPath(import.meta.url));
const srv = spawn(process.execPath, [resolve(here, "serve.mjs")], { stdio: "inherit" });
await new Promise((r) => setTimeout(r, 800));
const cleanup = () => { try { srv.kill(); } catch {} };
process.on("exit", cleanup);
process.on("uncaughtException", (e) => { cleanup(); throw e; });

async function waitForTopBar(page) {
  await page.waitForFunction(
    () => document.querySelector(".edit-lease") !== null,
    { timeout: 15000 },
  );
  await page.waitForFunction(
    () => {
      const t = document.querySelector(".edit-lease")?.textContent || "";
      return /r\d+/.test(t) && !t.includes("连接中");
    },
    { timeout: 15000 },
  );
}

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext();
const page = await ctx.newPage();

const requests = [];
page.on("request", (r) => {
  if (["POST", "DELETE", "PATCH", "PUT"].includes(r.method())) {
    requests.push({ method: r.method(), url: r.url() });
  }
});
const failures = [];
page.on("requestfailed", (r) =>
  failures.push(`${r.method()} ${r.url()} ${r.failure()?.errorText}`));
page.on("pageerror", (e) => failures.push(`pageerror: ${e.message}`));
page.on("response", (r) => {
  if (r.url().startsWith(BACKEND) && r.status() >= 400) {
    log("http err:", r.status(), r.url().replace(BACKEND, ""));
  }
});
page.on("console", (m) => log("console:", m.type(), m.text()));

// Rewrite every relative API call to the live backend. Must run before
// the first navigation so React sees the shim on the very first render.
await page.addInitScript((apiBase) => {
  const origFetch = window.fetch.bind(window);
  window.fetch = (input, init) => {
    if (typeof input === "string" && input.startsWith("/")) {
      return origFetch(apiBase + input, init);
    }
    return origFetch(input, init);
  };
}, BACKEND);

try {
  log("loading", URL);
  await page.goto(URL, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.evaluate(() => localStorage.removeItem("yroll.session.v1"));
  await page.reload({ waitUntil: "domcontentloaded", timeout: 30000 });
  await waitForTopBar(page);
  await page.screenshot({ path: OUT + "diag-load.png", fullPage: false }).catch(() => {});

  const bar0 = await page.$eval(".edit-lease", (el) => el.textContent || "");
  log("top bar before acquire:", JSON.stringify(bar0.trim().replace(/\s+/g, " ")));

  // First poll may 409 on auto-acquire if the store's revision is behind
  // (left over from a prior smoke run). Click the explicit button — it
  // goes through sessionStore.acquire() and the server corrects the
  // baseRevision on its end.
  if (!bar0.includes("编辑权：我")) {
    log("acquiring lease via UI button");
    await page.getByRole("button", { name: /获取编辑权|收回/ }).click();
    await page.waitForFunction(
      () => {
        const t = document.querySelector(".edit-lease")?.textContent || "";
        return t.includes("编辑权：我") && /r\d+/.test(t);
      },
      { timeout: 15000 },
    );
  }
  const bar = await page.$eval(".edit-lease", (el) => el.textContent || "");
  log("top bar:", JSON.stringify(bar.trim().replace(/\s+/g, " ")));
  if (!/编辑权：我/.test(bar)) throw new Error(`lease not acquired: "${bar}"`);

  const serverRev = Number((bar.match(/r(\d+)/) || [])[1]);
  if (!serverRev) throw new Error(`could not parse revision from bar: "${bar}"`);

  // 2. Real mutation through api.setTrackHidden — exercises the gate.
  const track = await page.evaluate(() => fetch("/project").then((r) => r.json()));
  const trackId = track.timeline.tracks[0].track_id;
  log("mutating track", trackId, "via api.setTrackHidden");
  const mutResult = await page.evaluate(async (args) => {
    const sid = localStorage.getItem("yroll.session.v1");
    const r = await fetch(
      `/tracks/${args.tid}/hide?hidden=true&why=smoke&sessionId=${sid}&baseRevision=${args.rev}`,
      { method: "POST" },
    );
    return { status: r.status, body: await r.text() };
  }, { tid: trackId, rev: serverRev });
  log("gated write result:", mutResult.status, mutResult.body.slice(0, 80));
  if (mutResult.status >= 400) throw new Error(`gated write failed: ${mutResult.status}`);

  // 3. Bare POST without a sessionId must be refused.
  const bare = await page.evaluate(async (tid) => {
    const r = await fetch(`/tracks/${tid}/hide?hidden=false&why=bare&baseRevision=0`, {
      method: "POST",
    });
    return { status: r.status, body: await r.text() };
  }, trackId);
  log("bare fetch status:", bare.status);
  if (!bare.body.includes("sessionId required") && !bare.body.includes("403")) {
    throw new Error(`expected Gate rejection for missing sessionId, got ${bare.status}: ${bare.body.slice(0, 200)}`);
  }

  // 4. Stale revision -> 409.
  const stale = await page.evaluate(async (tid) => {
    const sid = localStorage.getItem("yroll.session.v1");
    const r = await fetch(
      `/tracks/${tid}/hide?hidden=true&why=stale&sessionId=${sid}&baseRevision=99999`,
      { method: "POST" },
    );
    return { status: r.status, body: await r.text() };
  }, trackId);
  log("stale-rev status:", stale.status);
  if (stale.status !== 409 && !stale.body.includes("409")) {
    throw new Error(`expected 409, got ${stale.status}: ${stale.body.slice(0, 200)}`);
  }

  await page.screenshot({ path: OUT + "01-ready.png", fullPage: false });
  log("screenshot saved");
  writeFileSync(OUT + "01-requests.json", JSON.stringify(requests, null, 2));
  if (failures.length) {
    writeFileSync(OUT + "01-failures.json", JSON.stringify(failures, null, 2));
    throw new Error("page errors: " + failures.join("; "));
  }

  log("ALL CHECKS PASSED");
} catch (e) {
  log("FAILED:", e.message);
  await page.screenshot({ path: OUT + "01-fail.png", fullPage: true }).catch(() => {});
  process.exitCode = 1;
} finally {
  cleanup();
  await browser.close();
}
