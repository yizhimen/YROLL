// GUI-03R6-D: ClipBlock cross-track re-clamp reads sibling geometry
// from api.trackClips (Core state), NOT from DOM style.left / width.
//
// Architectural invariant: collision math (the half-open membership
// check used by the target-track re-clamp) is computed against
// frame-native intervals returned by Core. CSS pixels (style.left /
// style.width) are reserved for rendering only.

import { describe, expect, it, vi } from "vitest";

// We don't render the full ClipBlock (it pulls in Timeline, project
// state, drag autoscroll, etc.). Instead we verify the static text
// invariant: the file does NOT contain parseFloat(style.left) or
// parseFloat(style.width) for collision math. The DOM is allowed
// only for hit-testing (document.elementsFromPoint) and for the
// audit payload's geometry readout (these reads do not enter the
// collision decision).

import { readFileSync } from "fs";
import { resolve } from "path";

const CLIPBLOCK = resolve(
  __dirname, "..", "..", "src", "components", "ClipBlock.tsx",
);

describe("R6-D: ClipBlock does NOT derive collision geometry from CSS pixels", () => {
  it("never parses style.left to compute sibling frame ranges", () => {
    let raw = readFileSync(CLIPBLOCK, "utf-8");
    // Strip comments so the test doesn't flag historical mentions
    // in `//` lines.
    raw = raw.replace(/\/\*[\s\S]*?\*\//g, "");
    raw = raw.replace(/\/\/.*$/gm, "");
    // The previous implementation parsed style.left and style.width
    // to derive sibling intervals. After R6-D, the only DOM
    // geometry reads are for the audit payload (which is for
    // debugging) and for hit-testing (elementsFromPoint). Neither
    // enters the half-open collision check.
    expect(raw).not.toMatch(/parseFloat\([^)]*style\.left/);
    expect(raw).not.toMatch(/parseFloat\([^)]*style\.width/);
  });

  it("uses api.trackClips for canonical sibling intervals", () => {
    const raw = readFileSync(CLIPBLOCK, "utf-8");
    // The cross-track re-clamp must call api.trackClips(tid) and
    // consume the returned .start_frame / .end_frame fields.
    expect(raw).toMatch(/api\.trackClips/);
    expect(raw).toMatch(/start_frame/);
    expect(raw).toMatch(/end_frame/);
  });
});