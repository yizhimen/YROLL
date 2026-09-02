#!/usr/bin/env node
// GUI-04.5 P0-A: serve a working COPY of the canonical clean fixture.
//
// The canonical fixture (projects/sanlihe-slice-30s-clean) carries a
// "CANONICAL_READONLY_DO_NOT_MUTATE" sentinel and is the source of
// truth for UX-validation scenarios. Browser smoke must NEVER write
// to it.
//
// This script:
//   1. Verifies the canonical sentinel exists (refuses to start if
//      someone has tampered with the protection).
//   2. Snapshots the canonical current.json SHA256 before doing
//      anything.
//   3. Copies the canonical into a per-run disposable working
//      directory (default: projects/_sanlihe-clean-work). The
//      sentinel is NOT copied.
//   4. Spawns `yroll serve` against the working copy.
//   5. On exit, verifies the canonical SHA256 is unchanged (defense-
//      in-depth even though the working copy is what yroll sees).
//
// Usage:
//   node gui/smoke/serve-clean-sanlihe.mjs [port]
//   PORT env var also honored.
//
// Defaults:
//   port = 8770
//
// Failure to maintain the canonical invariant is a hard error.

import { spawn } from 'node:child_process';
import {
  mkdirSync,
  copyFileSync,
  rmSync,
  existsSync,
  readdirSync,
  statSync,
  readFileSync,
} from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..', '..');
const CANONICAL = join(ROOT, 'projects', 'sanlihe-slice-30s-clean');
const CANONICAL_CURRENT = join(CANONICAL, 'current.json');
const SENTINEL = join(CANONICAL, 'CANONICAL_READONLY_DO_NOT_MUTATE');
const WORK = join(ROOT, 'projects', '_sanlihe-clean-work');
const PORT = process.argv[2] ?? process.env.PORT ?? '8770';

// ---- Safety: canonical snapshot BEFORE we do anything ----
function sha256OfFile(p) {
  return createHash('sha256')
    .update(readFileSync(p))
    .digest('hex');
}

function canonicalSnapshot() {
  return {
    sentinel: existsSync(SENTINEL),
    currentSha: existsSync(CANONICAL_CURRENT)
      ? sha256OfFile(CANONICAL_CURRENT)
      : null,
  };
}

console.log(`=== GUI-04.5 P0-A Clean Sanlihe Working Copy ===`);
console.log(`canonical: ${CANONICAL}`);
console.log(`working:   ${WORK}`);
console.log(`port:      ${PORT}`);

// Pre-flight 1: canonical + sentinel must exist.
if (!existsSync(CANONICAL)) {
  console.error(`canonical fixture missing: ${CANONICAL}`);
  process.exit(1);
}
if (!existsSync(SENTINEL)) {
  console.error(`canonical sentinel missing: ${SENTINEL}`);
  console.error(`run scripts/build_clean_sanlihe_fixture.py first`);
  process.exit(1);
}

// Pre-flight 2: snapshot the canonical so we can detect any mutation.
const before = canonicalSnapshot();
console.log(`canonical snapshot: sha256=${before.currentSha?.slice(0, 12)}...`);

// ---- Build the working copy ----
console.log(`\nResetting working dir: ${WORK}`);
if (existsSync(WORK)) {
  rmSync(WORK, { recursive: true, force: true });
}
mkdirSync(WORK, { recursive: true });

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

// ---- Spawn yroll serve against the working copy ----
const child = spawn(
  'python',
  ['-m', 'yroll.cli.main', 'serve', WORK, '--port', PORT],
  { stdio: 'inherit', cwd: ROOT },
);

// ---- Post-exit canonical invariant check ----
function verifyCanonicalInvariant() {
  const after = canonicalSnapshot();
  if (!after.sentinel) {
    console.error(`\n[FATAL] canonical sentinel was removed during run!`);
    process.exit(2);
  }
  if (after.currentSha !== before.currentSha) {
    console.error(
      `\n[FATAL] canonical current.json was mutated during run!\n` +
        `  before: ${before.currentSha}\n` +
        `  after:  ${after.currentSha}`,
    );
    process.exit(2);
  }
  console.log(`canonical invariant OK (sha256=${after.currentSha?.slice(0, 12)}...)`);
}

child.on('exit', (code) => {
  verifyCanonicalInvariant();
  console.log(`yroll serve exited with code ${code}`);
  process.exit(code ?? 0);
});
process.on('SIGINT', () => {
  child.kill('SIGINT');
  // give the child a moment to actually exit so verifyCanonicalInvariant runs
  setTimeout(() => verifyCanonicalInvariant(), 100);
});
process.on('SIGTERM', () => {
  child.kill('SIGTERM');
  setTimeout(() => verifyCanonicalInvariant(), 100);
});
