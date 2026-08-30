// CDP smoke test: attach to running Chrome at 9222, open a new tab
// pointing to http://localhost:5173/, capture console + network
// errors and a screenshot.
//
// Requires: Chrome already running with --remote-debugging-port=9222.
import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const CDP_URL = "http://127.0.0.1:9222";
const TARGET_URL = "http://localhost:5173/";
const OUT_DIR = resolve("smoke-out");
mkdirSync(OUT_DIR, { recursive: true });

const browser = await chromium.connectOverCDP(CDP_URL);
console.log(`connected to ${CDP_URL}`);

// Use the first context (default user profile).
let context = browser.contexts()[0];
if (!context) {
  context = await browser.newContext();
}

const page = await context.newPage();
const consoleErrors = [];
const networkErrors = [];

page.on("console", (msg) => {
  if (msg.type() === "error") {
    consoleErrors.push({ text: msg.text(), location: msg.location() });
  }
});
page.on("pageerror", (err) => {
  consoleErrors.push({ text: "[pageerror] " + err.message });
});
page.on("response", (resp) => {
  if (resp.status() >= 400 && !resp.url().includes("favicon")) {
    networkErrors.push({ url: resp.url(), status: resp.status() });
  }
});
page.on("requestfailed", (req) => {
  networkErrors.push({
    url: req.url(),
    failure: req.failure()?.errorText,
  });
});

console.log(`navigating to ${TARGET_URL}`);
try {
  await page.goto(TARGET_URL, { waitUntil: "networkidle", timeout: 30000 });
} catch (e) {
  console.log("navigation error:", e.message);
}
await page.waitForTimeout(2500);  // let async fetches settle

const dom = await page.evaluate(() => {
  const root = document.querySelector(".app");
  const statusbar = document.querySelector(".statusbar");
  const switcher = document.querySelector(
    "[data-testid='timeline-switcher']",
  );
  const chips = Array.from(document.querySelectorAll(
    "[data-testid^='timeline-chip-']",
  )).map((el) => ({
    testid: el.getAttribute("data-testid"),
    active: el.getAttribute("data-active"),
    text: (el.textContent || "").trim().slice(0, 50),
  }));
  return {
    title: document.title,
    rootExists: !!root,
    rootChildren: root?.children.length ?? 0,
    statusbarText: statusbar?.textContent ?? null,
    switcherExists: !!switcher,
    chipCount: chips.length,
    chips,
    bodyTextLength: (document.body.textContent ?? "").length,
  };
});

const screenshotPath = resolve(OUT_DIR, "gui-5173-cdp.png");
await page.screenshot({ path: screenshotPath, fullPage: true });

const report = {
  target: TARGET_URL,
  dom,
  consoleErrors,
  networkErrors,
  screenshot: screenshotPath,
};
writeFileSync(resolve(OUT_DIR, "cdp-report.json"),
              JSON.stringify(report, null, 2));

console.log("\n===== REPORT =====");
console.log("DOM:", JSON.stringify(dom, null, 2));
console.log("\nconsole errors:", consoleErrors.length);
for (const e of consoleErrors.slice(0, 10)) console.log("  -", e.text);
console.log("\nnetwork errors:", networkErrors.length);
for (const e of networkErrors.slice(0, 10))
  console.log("  -", e.status || e.failure, e.url);
console.log("\nscreenshot:", screenshotPath);

await browser.close();
process.exit(consoleErrors.length || networkErrors.length ? 1 : 0);