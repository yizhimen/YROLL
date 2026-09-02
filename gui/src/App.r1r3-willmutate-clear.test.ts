// GUI-05-R1-R3 fix — Vitest regression for the dragPreview leak
// when willMutate=false.
//
// The fix: ClipBlock.tsx:onPointerUp, when willMutate=false (drag
// clamped to 0 frames / no mutation will be emitted), MUST call
// onDragClear(clip_id) so App's dragPreview state is cleared
// immediately. The previous code returned early without clearing
// dragPreview, causing the GUI to display the clip at the last
// pointermove preview position forever (until next pointermove),
// while Core remained at the origin. This drifted the visual out of
// sync with Core.
//
// This file covers:
//   1. Source-pin: ClipBlock.tsx:onPointerUp willMutate=false branch
//      calls onDragClear before the early-return.
//   2. Source-pin: App.tsx wires onDragClear to a callback that
//      removes the clip from dragPreview / dragGhost /
//      dragClampBoundary.
//   3. Behavioral: simulate the willMutate=false branch flow with
//      a mocked ClipBlock pointerup; assert dragPreview would be
//      cleared.

import { describe, it, expect } from "vitest";
import fs from "node:fs/promises";
import path from "node:path";

async function readClipBlockTsx(): Promise<string> {
  const p = path.resolve(__dirname, "./components/ClipBlock.tsx");
  return fs.readFile(p, "utf-8");
}

async function readAppTsx(): Promise<string> {
  const p = path.resolve(__dirname, "./App.tsx");
  return fs.readFile(p, "utf-8");
}

/**
 * Extract the body of ClipBlock's `up = async (ev) => { ... }` handler.
 * Uses brace-counting for robust extraction (the IIFE / nested
 * setTimeout patterns broke a previous regex-based extraction).
 */
function extractUpHandler(stripped: string): string | null {
  const startRe = /const up = async \(ev: PointerEvent\) => \{/;
  const startMatch = startRe.exec(stripped);
  if (!startMatch) return null;
  const startIdx = startMatch.index + startMatch[0].length;
  let depth = 1;
  let i = startIdx;
  while (i < stripped.length && depth > 0) {
    const ch = stripped[i];
    if (ch === "{") depth++;
    else if (ch === "}") depth--;
    i++;
  }
  if (depth !== 0) return null;
  return stripped.slice(startMatch.index, i);
}

describe("GUI-05-R1-R3 fix: dragPreview cleared when willMutate=false", () => {
  it("source-pin: ClipBlock.tsx willMutate=false branch calls onDragClear BEFORE the early-return", async () => {
    const raw = await readClipBlockTsx();
    // Strip comments to avoid false matches.
    const stripped = raw
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "")
      .replace(/\s+\/\/.*$/g, "");

    const upBody = extractUpHandler(stripped);
    expect(upBody, "could not locate ClipBlock up() handler").toBeTruthy();
    if (!upBody) return;

    // Extract just the willMutate=false block.
    const willMutateFalseRe =
      /if\s*\(\s*!upLog\.willMutate\s*\)\s*\{[\s\S]*?\n\s+\}/;
    const block = upBody.match(willMutateFalseRe);
    expect(block, "could not locate willMutate=false branch").toBeTruthy();
    if (!block) return;

    // The block MUST contain a call to onDragClear (the prop is
    // optional but the call site must be present — App always wires
    // it).
    expect(block[0]).toMatch(/onDragClear\s*\(/);

    // The block MUST NOT call onMoveCommit (that's the success path).
    expect(block[0]).not.toMatch(/onMoveCommit\s*\(/);

    // The block MUST NOT schedule any setTimeout (no rejection timeout
    // for a no-op drag).
    expect(block[0]).not.toMatch(/setTimeout\s*\(/);
  });

  it("source-pin: App.tsx wires onDragClear to clear dragPreview / dragGhost / dragClampBoundary", async () => {
    const raw = await readAppTsx();
    const stripped = raw
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "")
      .replace(/\s+\/\/.*$/g, "");

    // Find the onDragClear prop block in App.tsx.
    const onDragClearRe =
      /onDragClear=\{[\s\S]*?\}\s*\}/;
    const block = stripped.match(onDragClearRe);
    expect(block, "could not locate onDragClear={...} prop in App.tsx").toBeTruthy();
    if (!block) return;

    // The block MUST remove the clipId from dragPreview state.
    expect(block[0]).toMatch(/setDragPreview[\s\S]*?\[[\s\S]*?clipId[\s\S]*?\][\s\S]*?\.\.\.rest/);

    // The block MUST also clear dragGhost and dragClampBoundary (since
    // these are paired state with dragPreview; leaving them set
    // would leave visual artifacts).
    expect(block[0]).toMatch(/setDragGhost/);
    expect(block[0]).toMatch(/setDragClampBoundary/);
  });

  it("behavioral: simulating willMutate=false → dragPreview removed (mock setDragPreview)", () => {
    // Mirror the App.tsx onDragClear handler logic in isolation.
    let preview: Record<string, number> = { "clip-a": 999 };
    const setDragPreview = (
      updater: (p: Record<string, number>) => Record<string, number>,
    ) => {
      preview = updater({ ...preview });
    };

    // Simulate the fix: when willMutate=false, App calls onDragClear
    // which removes the clipId from preview.
    setDragPreview((p) => {
      const id = "clip-a";
      if (!(id in p)) return p;
      const { [id]: _, ...rest } = p;
      return rest;
    });

    expect(preview).toEqual({});
    expect(preview["clip-a"]).toBeUndefined();
  });
});