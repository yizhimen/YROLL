// Identify the 404 sources to confirm they're not W-C regressions.
import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext();
const page = await ctx.newPage();

const fails = [];
page.on('response', (r) => {
  if (r.status() >= 400) fails.push({ status: r.status(), url: r.url() });
});

await page.goto('http://localhost:5180/', { waitUntil: 'networkidle', timeout: 20000 });
await page.waitForTimeout(2500);

console.log(`Total failed responses: ${fails.length}`);
const byUrl = {};
for (const f of fails) {
  const path = new URL(f.url).pathname;
  byUrl[path] = (byUrl[path] || 0) + 1;
}
for (const [p, n] of Object.entries(byUrl)) {
  console.log(`  ${n}× ${p}`);
}
const nonWc = fails.filter((f) => !/drop-zone|track-content|asset|asset/i.test(f.url));
console.log(`Non-asset-related 404s: ${nonWc.length}`);
for (const f of nonWc.slice(0, 5)) console.log(`  ${f.status} ${f.url}`);

await browser.close();
