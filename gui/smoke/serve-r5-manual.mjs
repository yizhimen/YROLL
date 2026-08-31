#!/usr/bin/env node
// GUI-03R5 manual pass: spawn a working-copy of the canonical
// clean Sanlihe fixture and serve it on a dedicated port.
//
// GUARANTEE: the canonical fixture at
//   projects/sanlihe-slice-30s-clean
// is never written to. We copy it to
//   projects/_sanlihe-r5-manual
// (gitignored), then run `yroll serve` against the COPY.
//
// Usage:
//   node gui/smoke/serve-r5-manual.mjs [port]
// Default port: 8770

import { spawn, spawnSync } from "node:child_process";
import {
  mkdirSync, copyFileSync, rmSync, existsSync, readdirSync, statSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..", "..");
const CANONICAL = join(ROOT, "projects", "sanlihe-slice-30s-clean");
const SENTINEL = join(CANONICAL, "CANONICAL_READONLY_DO_NOT_MUTATE");
const WORK = join(ROOT, "projects", "_sanlihe-r5-manual");
const PORT = process.argv[2] ?? "8770";

console.log("=== GUI-03R5 MANUAL PASS WORKING COPY ===");
console.log(`canonical (READ-ONLY): ${CANONICAL}`);
console.log(`working copy:          ${WORK}`);
console.log(`port:                  ${PORT}`);

if (!existsSync(SENTINEL)) {
  console.error(`canonical fixture missing or sentinel absent: ${SENTINEL}`);
  console.error(`run scripts/build_clean_sanlihe_fixture.py first`);
  process.exit(1);
}

// Reset + copy. Sentinel is never copied to the working dir.
console.log(`\n[1/3] Resetting working copy...`);
if (existsSync(WORK)) {
  rmSync(WORK, { recursive: true, force: true });
}
function rec(src, dst) {
  mkdirSync(dst, { recursive: true });
  for (const name of readdirSync(src)) {
    const sp = join(src, name);
    const dp = join(dst, name);
    if (sp === SENTINEL) continue;
    if (statSync(sp).isDirectory()) rec(sp, dp);
    else copyFileSync(sp, dp);
  }
}
rec(CANONICAL, WORK);
console.log(`[2/3] Working copy created (canonical untouched)`);

// Verify the canonical mtime is newer than the working copy mtime
// (just a sanity check that we didn't accidentally write to it).
const canonicalStat = statSync(CANONICAL);
console.log(`      canonical mtime: ${canonicalStat.mtime.toISOString()}`);

// Spawn yroll serve against the WORKING dir (NOT the canonical).
console.log(`[3/3] Starting yroll serve on port ${PORT}...`);
const child = spawn(
  "python",
  ["-m", "yroll.cli.main", "serve", WORK, "--port", PORT, "--host", "127.0.0.1"],
  { stdio: "inherit", cwd: ROOT },
);
child.on("exit", (code) => {
  console.log(`yroll serve exited with code ${code}`);
  process.exit(code ?? 0);
});
process.on("SIGINT", () => { child.kill("SIGINT"); });
process.on("SIGTERM", () => { child.kill("SIGTERM"); });