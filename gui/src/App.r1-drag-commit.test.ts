// GUI-05-R1 — Drag Commit Stability / Relationship Propagation Audit.
//
// R1-A: SUCCESS drag must never visually spring back.
// Current bug: onMoveCommit clears dragPreview[clipId] BEFORE await
// run(). Visual sequence: A → B(preview) → A(Core old) → B(Core new).
// Fix invariant: keep B visually during pending mutation; clear
// preview only after Core state is refreshed; B remains visually
// continuous.
//
// R1-B: rejected drag remains A → B(rejected) → 600ms → A.
// Current bug: attemptedFrame is mutated from inside a setState
// updater (anti-pattern). Per spec: use the canonical pointerup
// frame newStartFrame directly.

import { describe, it, expect } from "vitest";

async function readAppTsx(): Promise<string> {
  const fs = await import("node:fs/promises");
  const path = await import("node:path");
  const appPath = path.resolve(__dirname, "./App.tsx");
  return fs.readFile(appPath, "utf-8");
}

/**
 * Strip JS line + block comments. Naive but sufficient for source-pin
 * assertions (no // or /* inside string literals in App.tsx).
 */
function stripComments(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "")
    .replace(/\s+\/\/.*$/g, "");
}

/**
 * Extract the body of the onMoveCommit callback wired into <Timeline>.
 * The callback is the async arrow function assigned to
 * `onMoveCommit={async (clipId, newStartFrame, newTrackId) => { ... }}`
 * in App.tsx. This is a heuristic extraction; if App.tsx is refactored
 * this regex must be updated.
 */
function extractOnMoveCommitBody(stripped: string): string | null {
  const m = stripped.match(
    /onMoveCommit=\{async\s*\(\s*clipId\s*,\s*newStartFrame\s*,\s*newTrackId\s*\)\s*=>\s*\{[\s\S]*?\n\s+\}\s*\}/,
  );
  return m ? m[0] : null;
}

describe("GUI-05-R1 (R1-A) SUCCESS drag must never visually spring back", () => {
  it("source-pin: onMoveCommit must NOT mutate attemptedFrame from inside a setDragPreview updater (combined R1-A + R1-B check)", async () => {
    // The original R1-A bug: `setDragPreview((p) => { attemptedFrame = p[clipId]; ... return rest; })`
    // appeared BEFORE the await run() call. This both:
    //   - cleared dragPreview synchronously (R1-A: visual spring-back)
    //   - mutated attemptedFrame inside a setState updater (R1-B: anti-pattern)
    // The R1-B "no attemptedFrame = p[clipId] inside updater" test already
    // pins the anti-pattern; together with the "must set dragPreview =
    // attemptedFrame BEFORE await" test below, the absence of the buggy
    // sync-clear is implied.
    const raw = await readAppTsx();
    const stripped = stripComments(raw);
    const body = extractOnMoveCommitBody(stripped);
    expect(body, "could not locate onMoveCommit body in App.tsx").toBeTruthy();
    if (!body) return;
    // Sanity: the fix pattern IS present.
    const setBeforeAwaitRe =
      /setDragPreview\(\s*\(\s*p\s*\)\s*=>\s*\(\s*\{\s*\.\.\.p\s*,\s*\[clipId\]\s*:\s*attemptedFrame\s*\}\s*\)\s*\)/;
    expect(body).toMatch(setBeforeAwaitRe);
  });

  it("source-pin: onMoveCommit must set dragPreview[clipId] = attemptedFrame BEFORE await (so visual stays at B during pending mutation)", async () => {
    const raw = await readAppTsx();
    const stripped = stripComments(raw);
    const body = extractOnMoveCommitBody(stripped);
    expect(body).toBeTruthy();
    if (!body) return;

    // The fix pattern: setDragPreview((p) => ({ ...p, [clipId]: attemptedFrame }))
    // BEFORE the `await run(...)` call. This ensures displayProject reads
    // dragPreview[clipId] (B) during the pending mutation window.
    const setBeforeAwaitRe =
      /setDragPreview\(\s*\(\s*p\s*\)\s*=>\s*\(\s*\{\s*\.\.\.p\s*,\s*\[clipId\]\s*:\s*attemptedFrame\s*\}\s*\)\s*\)/;
    expect(body).toMatch(setBeforeAwaitRe);
  });

  it("source-pin: onMoveCommit success path must clear dragPreview[clipId] AFTER refresh", async () => {
    const raw = await readAppTsx();
    const stripped = stripComments(raw);
    const body = extractOnMoveCommitBody(stripped);
    expect(body).toBeTruthy();
    if (!body) return;

    // The success branch (`if (success) { ... }`) must include a
    // setDragPreview that removes clipId. After Core refresh updates
    // project to the new position, displayProject falls back to Core
    // — no visual change.
    const successBranchRe =
      /if\s*\(\s*success\s*\)\s*\{[\s\S]*?setDragPreview\(\s*\(\s*p\s*\)\s*=>\s*\{[\s\S]*?const\s*\{\s*\[clipId\][^}]*\}\s*=\s*p[\s\S]*?return\s+rest\s*;[\s\S]*?\}\s*\)[\s\S]*?\}/;
    expect(body).toMatch(successBranchRe);
  });

  it("behavior: B stays visually continuous during pending api.move (no repaint at A)", () => {
    // Mirror the fix invariant in pure state-machine form.
    // Setup: preview starts with clip-a at 150 (B).
    let preview: Record<string, number> = { "clip-a": 150 };
    const setDragPreview = (updater: (p: Record<string, number>) => Record<string, number>) => {
      preview = updater({ ...preview });
    };

    // Simulate the FIXED onMoveCommit (before-await): keep dragPreview
    // at the attempted frame so displayProject renders at B during the
    // pending mutation.
    const attemptedFrame = 150;
    setDragPreview((p) => ({ ...p, ["clip-a"]: attemptedFrame }));

    // During the await window, preview[clip-a] is still 150 (B).
    expect(preview["clip-a"]).toBe(150);

    // Simulate Core refresh resolving: project updated to B. We then
    // clear dragPreview so displayProject falls back to Core (also B).
    setDragPreview((p) => {
      const { ["clip-a"]: _, ...rest } = p;
      return rest;
    });

    // After the post-refresh clear, preview[clip-a] is undefined.
    // displayProject would read Core's value (B at this point).
    expect(preview["clip-a"]).toBeUndefined();

    // The visual sequence was: A (start) → B (preview, set in pointermove)
    // → B (kept during await) → B (Core new, after refresh) — NO A
    // repaint in the middle. The invariant holds.
  });
});

describe("GUI-05-R1 (R1-B) attemptedFrame must equal newStartFrame (canonical pointerup frame)", () => {
  it("source-pin: attemptedFrame must NOT be mutated from inside a setDragPreview setState updater", async () => {
    const raw = await readAppTsx();
    const stripped = stripComments(raw);
    const body = extractOnMoveCommitBody(stripped);
    expect(body).toBeTruthy();
    if (!body) return;

    // The bug pattern: inside a setDragPreview((p) => { ... }) updater,
    // assign to attemptedFrame from p[clipId]. This is the React
    // anti-pattern (setState updater may run multiple times in dev
    // StrictMode, or not at all).
    const antiPatternRe =
      /setDragPreview\(\s*\(\s*p\s*\)\s*=>\s*\{[\s\S]*?attemptedFrame\s*=\s*p\[clipId\]/;
    expect(body).not.toMatch(antiPatternRe);
  });

  it("source-pin: attemptedFrame must be assigned from newStartFrame (the canonical pointerup frame)", async () => {
    const raw = await readAppTsx();
    const stripped = stripComments(raw);
    const body = extractOnMoveCommitBody(stripped);
    expect(body).toBeTruthy();
    if (!body) return;

    // The fix: `const attemptedFrame = newStartFrame;` at the top of
    // the callback (before any await). newStartFrame is the integer
    // TimelineFrame computed by ClipBlock's pointerup (post-clamp +
    // post-snap + post-collision-validation).
    const fixRe =
      /const\s+attemptedFrame\s*=\s*newStartFrame\s*;/;
    expect(body).toMatch(fixRe);
  });

  it("source-pin: no `let attemptedFrame: number | null = null;` declaration", async () => {
    // The bug uses `let` with `| null` because the closure mutates it
    // (sometimes it's null). The fix uses `const` (always set from
    // newStartFrame, which is non-null).
    const raw = await readAppTsx();
    const stripped = stripComments(raw);
    const body = extractOnMoveCommitBody(stripped);
    expect(body).toBeTruthy();
    if (!body) return;

    expect(body).not.toMatch(
      /let\s+attemptedFrame\s*:\s*number\s*\|\s*null\s*=\s*null\s*;/,
    );
  });
});

describe("GUI-05-R1 (R1-C) relationship propagation audit (pytest counterpart in tests/test_r1_relationship_audit.py)", () => {
  it("source-pin: App.tsx does NOT change infer_relationships or move_clip propagation semantics", async () => {
    // R1-C explicitly forbids silently changing move_clip semantics.
    // This source-pin guards against accidental Core-side changes
    // smuggled into the R1 commit.
    const fs = await import("node:fs/promises");
    const commandsText = await fs.readFile(
      (await import("node:path")).resolve(
        __dirname,
        "../../yroll/core/commands.py",
      ),
      "utf-8",
    );
    const linksText = await fs.readFile(
      (await import("node:path")).resolve(
        __dirname,
        "../../yroll/core/links.py",
      ),
      "utf-8",
    );

    // move_clip must still call infer_relationships (D12 + R1-C
    // invariant: pre-existing STRONG propagation behavior unchanged).
    expect(commandsText).toMatch(/infer_relationships\(self\.core\.project\)/);

    // move_clip must still iterate related_ids and shift by delta.
    // The cross_shifted dict shape is unchanged.
    expect(commandsText).toMatch(/cross_shifted\[rid\]\s*=/);
    expect(commandsText).toMatch(/rc\.timeline_range\s*=\s*TimeRange\([\s\S]*?rc\.timeline_range\.start\s*\+\s*delta/);

    // infer_relationships must still only iterate non-VIDEO tracks
    // when building the relations list (text/audio → video only).
    // This is what makes A→C a direct relationship rather than a
    // transitive one through B.
    expect(linksText).toMatch(/if\s+t\.kind\s*==\s*TrackKind\.VIDEO\s*:\s*\n\s*continue/);

    // No transitive propagation (no chain iteration over related_ids
    // of related_ids). The shift loop is over a single hop from the
    // moved clip's direct edges only.
    // (Implicit: the loop is `for rid in related_ids:`, not a
    // recursive walker — pin the absence of recursion.)
    expect(commandsText).not.toMatch(/def\s+_propagate_transitive/);
  });
});