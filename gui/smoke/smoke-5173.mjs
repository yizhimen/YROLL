// Smoke test: open http://localhost:5173/ via Playwright Chromium,
// capture console errors + network failures + a screenshot.
//
// Usage: node smoke-5173.mjs
//   expects Vite dev server on http://localhost:5173/
//   expects YROLL backend on http://127.0.0.1:8765/
import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const OUT_DIR = resolve("smoke-out");
mkdirSync(OUT_DIR, { recursive: true });

const URL = "http://localhost:5173/";

const browser = await chromium.launch({
  headless: true,
  args: ["--no-sandbox", "--disable-gpu"],
});
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
});
const page = await ctx.newPage();

const consoleErrors = [];
const consoleWarns = [];
const networkErrors = [];

page.on("console", (msg) => {
  if (msg.type() === "error") {
    consoleErrors.push({ text: msg.text(), location: msg.location() });
  } else if (msg.type() === "warning") {
    consoleWarns.push(msg.text());
  }
});

page.on("pageerror", (err) => {
  consoleErrors.push({ text: "[pageerror] " + err.message, location: {} });
});

page.on("requestfailed", (req) => {
  networkErrors.push({
    url: req.url(),
    method: req.method(),
    failure: req.failure()?.errorText,
  });
});

page.on("response", (resp) => {
  const status = resp.status();
  if (status >= 400 && !resp.url().includes("favicon")) {
    networkErrors.push({
      url: resp.url(),
      status,
      statusText: resp.statusText(),
    });
  }
});

console.log(`Navigating to ${URL} ...`);
try {
  await page.goto(URL, { waitUntil: "networkidle", timeout: 30000 });
} catch (e) {
  console.log("navigation error:", e.message);
}

await page.waitForTimeout(2000);  // let any async fetches settle

// Probe DOM: is the App rendered?
const dom = await page.evaluate(() => {
  const root = document.querySelector(".app");
  const statusbar = document.querySelector(".statusbar");
  const timelineSwitcher = document.querySelector(
    "[data-testid='timeline-switcher']",
  );
  const menuBar = document.querySelector(".menubar, [class*='MenuBar']");
  return {
    rootExists: !!root,
    rootChildrenCount: root?.children.length ?? 0,
    statusbarText: statusbar?.textContent ?? null,
    timelineSwitcherExists: !!timelineSwitcher,
    menuBarExists: !!menuBar,
    titleText: document.title,
    bodyTextLength: document.body.textContent?.length ?? 0,
    bodyTextPreview: (document.body.textContent ?? "").slice(0, 200),
  };
});

const screenshotPath = resolve(OUT_DIR, "gui-5173.png");
await page.screenshot({ path: screenshotPath, fullPage: true });

const report = {
  url: URL,
  dom,
  consoleErrors,
  consoleWarns: consoleWarns.slice(0, 10),
  networkErrors,
  screenshot: screenshotPath,
};

writeFileSync(
  resolve(OUT_DIR, "report.json"),
  JSON.stringify(report, null, 2),
);

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