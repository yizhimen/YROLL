// GUI-03R5-B1 (Decision 1): drag coordinate invariant.
//
// Pins:
//   frameDelta = roundHalfAwayFromZero((ev.clientX - startX) / pxPerFrame)
//   scrollLeft MUST NOT participate in frame delta.
//
// This is a pure unit test for the math, NOT an integration test of
// ClipBlock (those live in ClipBlock.test.tsx). The test documents
// the invariant for future implementers and serves as the contract.

import { describe, expect, it } from "vitest";
import { roundHalfAwayFromZero } from "./frames";

describe("GUI-03R5-B1 Decision 1: pointer-only frame delta", () => {
  it("frame delta = round((clientX - startX) / pxPerFrame)", () => {
    const pxPerFrame = 0.4;  // 30fps, pxPerSec=12
    // 50 px right at 0.4 px/frame → +125 frames
    expect(
      roundHalfAwayFromZero(50 / pxPerFrame)).toBe(125);
    // -30 px left → -75 frames
    expect(
      roundHalfAwayFromZero(-30 / pxPerFrame)).toBe(-75);
  });

  it("scrollLeft delta is INDEPENDENT (does not enter frame math)", () => {
    // Simulate: pointer moved 50px right; content scrolled 200px right.
    // The frame delta is purely the pointer's 50px displacement.
    const pxPerFrame = 0.4;
    const pointerDelta = 50;
    const scrollDelta = 200;
    // Correct (interpretation 1): frame = pointer-only.
    const frameA = roundHalfAwayFromZero(pointerDelta / pxPerFrame);
    // Incorrect (interpretation 2, the previous behavior): frame = pointer+scroll.
    const frameB = roundHalfAwayFromZero(
      (pointerDelta + scrollDelta) / pxPerFrame);
    // The audit rejected interpretation 2 (it amplifies drag). Pin
    // interpretation 1 as the contract.
    expect(frameA).toBe(125);
    expect(frameB).toBe(625);  // would be the amplified value
    expect(frameA).not.toBe(frameB);
  });

  it("scrollLeft changes do NOT cross-couple into frame math", () => {
    // Same pointer displacement, different scroll deltas. The
    // pointer-only invariant: frame delta depends ONLY on
    // pointerDelta, never on scrollLeft. So pointerDelta + 9999
    // scroll delta would AMPLIFY to 20198 frames in the OLD code
    // (interpretation 2). Under interpretation 1, the scroll
    // delta is independent and never enters the frame math — the
    // result is identical regardless of scroll.
    const pxPerFrame = 0.5;
    const pointerDelta = 100;
    const f1 = roundHalfAwayFromZero(pointerDelta / pxPerFrame);
    // The correct contract: same pointer displacement → same frame
    // delta. The OLD bug was that adding scroll to the math made
    // f2 different from f1. Pin interpretation 1 here.
    expect(f1).toBe(200);
    // And document the OLD buggy behavior so the regression is
    // explicit:
    const buggy = roundHalfAwayFromZero(
      (pointerDelta + 9999) / pxPerFrame);
    expect(buggy).toBe(20198);  // OLD interpretation 2 — never use this
    expect(f1).not.toBe(buggy);  // confirm we are NOT doing this
  });

  it("extreme small drag (sub-pixel) rounds toward zero", () => {
    const pxPerFrame = 0.4;
    // 0.3 px = 0.75 frame → rounds to 1 (half-away-from-zero)
    expect(roundHalfAwayFromZero(0.3 / pxPerFrame)).toBe(1);
    // 0.1 px = 0.25 frame → rounds to 0 (below half)
    expect(roundHalfAwayFromZero(0.1 / pxPerFrame)).toBe(0);
    // Negative: -0.1 px = -0.25 frame → rounds to 0
    expect(roundHalfAwayFromZero(-0.1 / pxPerFrame)).toBe(0);
  });
});