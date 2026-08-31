#!/usr/bin/env node
// GUI-03R4.1 P0-2 helper: serve a working COPY of the canonical
// clean fixture.
//
// The canonical fixture (projects/sanlihe-slice-30s-clean) carries
// a "CANONICAL_READONLY_DO_NOT_MUTATE" sentinel — browser smoke
// must NEVER write to it. This script copies the canonical into a
// per-run working directory, removes the sentinel from the copy,
// and runs `yroll serve` against the copy.
//
// Usage:
//   node gui/smoke/serve-clean-sanlihe.mjs [port]
//
// Defaults:
//   port = 8770  (separate from the dirty fixture's 8765)
//
// The yroll serve process keeps its lease / mutates freely; the
// canonical copy is untouched.

import { spawn, spawnSync } from 'node:child_process';
import { mkdirSync, copyFileSync, rmSync, existsSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..', '..');
const CANONICAL = join(ROOT, 'projects', 'sanlihe-slice-30s-clean');
const SENTINEL = join(CANONICAL, 'CANONICAL_READONLY_DO_NOT_MUTATE');
const WORK = join(ROOT, 'projects', '_sanlihe-clean-work');
const PORT = process.argv[2] ?? '8770';

console.log(`=== GUI-03R4.1 P0-2 Clean Sanlihe Working Copy ===`);
console.log(`canonical: ${CANONICAL}`);
console.log(`working:   ${WORK}`);
console.log(`port:      ${PORT}`);

// Verify canonical exists and has the readonly sentinel.
if (!existsSync(SENTINEL)) {
  console.error(`canonical fixture missing or missing sentinel: ${SENTINEL}`);
  console.error(`run scripts/build_clean_sanlihe_fixture.py first`);
  process.exit(1);
}

// Reset the working directory. Always overwrite — the canonical
// stays untouched.
console.log(`\nResetting working dir: ${WORK}`);
if (existsSync(WORK)) {
  rmSync(WORK, { recursive: true, force: true });
}
mkdirSync(WORK, { recursive: true });

// Mirror canonical into working dir, EXCLUDING the sentinel.
function copyDir(src, dst) {
  mkdirSync(dst, { recursive: true });
  for (const name of readdirSync(src)) {
    const sp = join(src, name);
    const dp = join(dst, name);
    if (sp === SENTINEL) continue;
    const st = require('node:fs').statSync(sp);
    if (st.isDirectory()) copyDir(sp, dp);
    else copyFileSync(sp, dp);
  }
}
// Use a minimal recursive copy (no extra deps).
import { statSync } from 'node:fs';
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
console.log(`working copy created`);

// Spawn yroll serve against the working dir. The child runs in
// foreground; Ctrl+C will tear it down.
const child = spawn(
  'python',
  ['-m', 'yroll.cli.main', 'serve', WORK, '--port', PORT],
  { stdio: 'inherit', cwd: ROOT },
);
child.on('exit', (code) => {
  console.log(`yroll serve exited with code ${code}`);
  process.exit(code ?? 0);
});
process.on('SIGINT', () => { child.kill('SIGINT'); });
process.on('SIGTERM', () => { child.kill('SIGTERM'); });