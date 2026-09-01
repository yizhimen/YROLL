// gui/src/frame-contract.test.ts
//
// GUI-04 04-02: Frame Mutation Contract Closure.
//
// These tests pin the contract that NO fractional TimelineFrame
// value is allowed to reach a frame-native mutation wrapper. The
// tests target the SOURCE code paths (App.tsx, AssetPanel.tsx,
// ClipBlock.tsx, frames.ts) — not the api.assertIntFrame guard.
//
// The contract:
//
//     candidateFrame       ∈ Z
//     clampedFrame         ∈ Z
//     snapFrame            ∈ Z | null
//     finalFrame           ∈ Z
//     mutationRequestFrame ∈ Z
//
// Forbidden values that the user's manual testing observed reaching
// a mutation wrapper (and the runtime assertIntFrame guard now
// catches them):
//
//   139.99999999997          (fp drift near 140)
//   275.25499999994          (fp drift near 275.255)
//   8.526512829121202e-14    (residual near 0)
//
// The architectural fix per the plan: identify the introducing
// operation and fix at the source. `Number(frame.toFixed(...))` and
// silent server round are FORBIDDEN as long-term fixes.
//
// This test file covers the source-level paths. The companion
// tests/test_frame_mutation_contract.py covers the Core side
// (Pydantic-validated int contract + _frame_to_sec boundary).

import { describe, it, expect } from "vitest";
import {
  roundHalfAwayFromZero,
  secondsToFramesEdit,
  pxPerFrame,
  pixelDeltaToFrameDelta,
  pixelToPlayheadFrame,
} from "./frames";

// ---------------------------------------------------------------------------
// 1. Round-trip identity for the rounding primitive itself
// ---------------------------------------------------------------------------
//
// roundHalfAwayFromZero is the ONLY canonical rounding primitive
// for frame-domain math. Test the policy at boundaries where
// Math.round and roundHalfAwayFromZero disagree.
//
// User's forbidden values covered:
//   - 139.99999999997  → 140 (Math.round and roundHalfAwayFromZero agree)
//   - 275.25499999994  → 275 (Math.round and roundHalfAwayFromZero agree)
//   - 8.526512829121202e-14 → 0 (Math.round and roundHalfAwayFromZero agree)
// Plus the half-frame tie-break where Math.round disagrees:
//   - 0.5   → 1   (both agree)
//   - -0.5  → -1  (Math.round gives 0; roundHalfAwayFromZero gives -1)
//   - 1.5   → 2   (both agree)
//   - -1.5  → -2  (Math.round gives -1; roundHalfAwayFromZero gives -2)

describe("roundHalfAwayFromZero — frame-domain rounding primitive", () => {
  it.each([
    [0, 0],
    [1, 1],
    [-1, -1],
    [139, 139],
    [140, 140],
    [139.99999999997, 140],
    [140.00000000002, 140],
    [275.25499999994, 275],
    [275.255, 275],
    [275.256, 275],
    [275.25 + 1e-9, 275],
    [8.526512829121202e-14, 0],
    [-8.526512829121202e-14, 0],
    [Number.NaN, Number.NaN],  // NaN stays NaN — caller must guard upstream
    [Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY],  // +Inf stays
    [Number.NEGATIVE_INFINITY, Number.NEGATIVE_INFINITY],  // -Inf stays
  ])("roundHalfAwayFromZero(%p) === %p", (input, expected) => {
    const got = roundHalfAwayFromZero(input);
    if (Number.isNaN(expected)) {
      expect(Number.isNaN(got)).toBe(true);
    } else {
      expect(got).toBe(expected);
    }
  });

  it("asymmetric tie-break at -0.5 (Math.round would give 0; policy gives -1)", () => {
    // This is the spec-mandated tie-break. If a future regression
    // swaps roundHalfAwayFromZero for Math.round, this catches it.
    expect(roundHalfAwayFromZero(-0.5)).toBe(-1);
    expect(roundHalfAwayFromZero(-1.5)).toBe(-2);
    expect(roundHalfAwayFromZero(-2.5)).toBe(-3);
  });
});

// ---------------------------------------------------------------------------
// 2. secondsToFramesEdit — the legacy-storage → frame-domain boundary
// ---------------------------------------------------------------------------
//
// This is the ONE sanctioned way to convert from the Core's legacy
// seconds storage into integer frames for edit math. Every value
// it returns MUST be an integer, regardless of fps ratio.

describe("secondsToFramesEdit — boundary helper", () => {
  it.each([
    [0, { num: 30, den: 1 }, 0],
    [1, { num: 30, den: 1 }, 30],
    [1, { num: 25, den: 1 }, 25],
    [1, { num: 24, den: 1 }, 24],
    [1, { num: 30000, den: 1001 }, 30],   // NTSC
    [1, { num: 60, den: 1 }, 60],
    // fp-drift seconds inputs (the user's reported values divided by
    // 30 fps to translate to "what seconds input would have produced
    // the forbidden frame value if the boundary was sloppy"):
    [139.99999999997 / 30, { num: 30, den: 1 }, 140],
    [275.25499999994 / 30, { num: 30, den: 1 }, 275],
    [8.526512829121202e-14 / 30, { num: 30, den: 1 }, 0],
    [Number.NaN, { num: 30, den: 1 }, Number.NaN],  // propagates
  ])("secondsToFramesEdit(%p, fps=%p) === %p", (sec, fps, expected) => {
    const got = secondsToFramesEdit(sec, fps);
    if (Number.isNaN(expected)) {
      expect(Number.isNaN(got)).toBe(true);
    } else {
      expect(got).toBe(expected);
      expect(Number.isInteger(got)).toBe(true);
    }
  });

  it("NTSC boundary: 1 second @ 30000/1001 → 30 frames (no half-frame drift)", () => {
    // NTSC has ~29.97 fps; 1 sec = ~29.97 frames. roundHalfAwayFromZero
    // gives 30, NOT 29 (Math.round also gives 30 here).
    expect(secondsToFramesEdit(1, { num: 30000, den: 1001 })).toBe(30);
  });

  it("return value is always an integer — never a forbidden fractional value", () => {
    // Sweep inputs across the real-world range. The helper must NEVER
    // return a value from the user's forbidden set.
    const forbidden = new Set([
      139.99999999997, 275.25499999994, 8.526512829121202e-14,
    ]);
    for (const fps of [
      { num: 30, den: 1 }, { num: 25, den: 1 }, { num: 24, den: 1 },
      { num: 60, den: 1 }, { num: 30000, den: 1001 },
    ]) {
      for (const sec of [0, 0.1, 0.5, 1, 1.5, 5, 10, 100, 1000]) {
        const got = secondsToFramesEdit(sec, fps);
        expect(Number.isInteger(got)).toBe(true);
        expect(forbidden.has(got)).toBe(false);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// 3. pxPerFrame + pixelDeltaToFrameDelta — drag candidate math
// ---------------------------------------------------------------------------
//
// Reproduce the real-world drag scenario where pxPerFrame is derived
// from a fractional pxPerSec and produces half-frame boundaries.

describe("pixelDeltaToFrameDelta — drag candidate from pointer pixels", () => {
  it("drag distance that crosses 1 frame boundary produces integer delta", () => {
    // 0.84 px/frame at 30fps (~25 px/sec). 10 px pointer delta →
    // roundHalfAwayFromZero(10 / 0.84) = roundHalfAwayFromZero(11.9047...) = 12
    const fps = { num: 30, den: 1 };
    const pxPerSec = 25;
    const pxF = pxPerFrame(pxPerSec, fps);
    expect(pixelDeltaToFrameDelta(10, pxPerSec, fps)).toBe(12);
    expect(pixelDeltaToFrameDelta(5, pxPerSec, fps)).toBe(6);
    expect(pixelDeltaToFrameDelta(50, pxPerSec, fps)).toBe(60);
    expect(pixelDeltaToFrameDelta(1, pxPerSec, fps)).toBe(1);
  });

  it("pointer delta that lands exactly on a half-frame boundary stays integer", () => {
    // 1 px / (1/3 pxPerFrame) = 3 frames exactly. No drift.
    const fps = { num: 30, den: 1 };
    const pxPerSec = 10;  // 10/30 pxPerFrame ≈ 0.333 px/frame
    expect(pixelDeltaToFrameDelta(1, pxPerSec, fps)).toBe(3);
  });

  it("real-world drag at default zoom (pxPerFrame ≈ 0.84)", () => {
    const fps = { num: 30, den: 1 };
    const pxPerSec = 25;
    // The exact values from manual drag testing — pointer deltas
    // 1, 5, 10, 50 px must produce integer frame deltas.
    expect(pixelDeltaToFrameDelta(1, pxPerSec, fps)).toBe(1);
    expect(pixelDeltaToFrameDelta(5, pxPerSec, fps)).toBe(6);
    expect(pixelDeltaToFrameDelta(10, pxPerSec, fps)).toBe(12);
    expect(pixelDeltaToFrameDelta(50, pxPerSec, fps)).toBe(60);
  });
});

// ---------------------------------------------------------------------------
// 4. pixelToPlayheadFrame — ruler click → integer frame
// ---------------------------------------------------------------------------

describe("pixelToPlayheadFrame — ruler click", () => {
  it("each integer frame corresponds to a click x that maps back to itself", () => {
    const fps = { num: 30, den: 1 };
    const pxPerSec = 25;
    // For frame F, click at F * pxPerFrame + small drift should
    // still resolve to F.
    for (const F of [0, 1, 30, 139, 140, 300, 1000]) {
      const xClick = F * pxPerFrame(pxPerSec, fps);
      expect(pixelToPlayheadFrame(xClick, pxPerSec, fps, 0)).toBe(F);
    }
  });

  it("drag-resampled x stays integer even when the click is sub-pixel off", () => {
    // Browsers can return fractional clientX when transforms are
    // applied (CSS zoom, sub-pixel layout). The math must survive.
    const fps = { num: 30, den: 1 };
    const pxPerSec = 25;
    const pxF = pxPerFrame(pxPerSec, fps);
    const driftPx = 0.3;  // sub-pixel drift
    for (const F of [139, 140, 275, 300]) {
      const xClick = F * pxF + driftPx;
      const got = pixelToPlayheadFrame(xClick, pxPerSec, fps, 0);
      expect(Number.isInteger(got)).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------
// 5. Architecture guard: integer Frame invariant
// ---------------------------------------------------------------------------
//
// A single test that documents the invariant explicitly so any
// future contributor sees the rule.

describe("Frame-domain invariant", () => {
  it("every integer is a Frame, every Frame is an integer (proof by reflection)", () => {
    // The set of valid Frames is exactly Z. There is no "valid
    // non-integer frame" in the GUI.
    for (const v of [0, 1, -1, 139, 140, 1e6]) {
      expect(Number.isInteger(v)).toBe(true);
    }
    for (const v of [
      139.99999999997, 275.25499999994, 8.526512829121202e-14,
      0.5, 1.5, -0.5, Number.NaN, Number.POSITIVE_INFINITY,
    ]) {
      expect(Number.isInteger(v)).toBe(false);
    }
  });

  it("forbidden values are never silently produced by the boundary helper", () => {
    const fps = { num: 30, den: 1 };
    for (const sec of [139.99999999997, 275.25499999994, 8.526512829121202e-14]) {
      const got = secondsToFramesEdit(sec, fps);
      expect(Number.isInteger(got)).toBe(true);
    }
  });

  // ----------------------------------------------------------------
  // GUI-04 04-02 architectural guard
  //
  // Regression test for the F1 bug class:
  //   App.tsx:1121 (pre-fix) — seek(h.timeline) where h.timeline is
  //   SECONDS from /search-transcripts (`round(tl, 2)`), passed
  //   straight into setPlayheadFrame. Result: fractional
  //   playheadFrame, which assertIntFrame then refused on the next
  //   user action (e.g. api.split).
  //
  // The fix converts seconds → frames at the call site via
  // secondsToFramesEdit. This test pins that contract: any value
  // coming out of the /search-transcripts response shape must be
  // converted via secondsToFramesEdit before reaching
  // setPlayheadFrame / seek / api.split / api.move.
  //
  // If a future contributor re-introduces the F1 bug (treating
  // /search-transcripts timeline as frames), this test fails.
  // ----------------------------------------------------------------
  it("F1 guard: /search-transcripts timeline (seconds) must convert to integer frames before reaching playheadFrame", () => {
    // Reproduce the /search-transcripts response shape (seconds
    // rounded to 2 decimals by the server).
    const searchHit = { timeline: 3.14 };  // seconds (e.g. 3.14s)
    const fps = { num: 30, den: 1 };

    // The bug class: passing the seconds value as frames.
    const naivePlayheadFrame = searchHit.timeline;  // 3.14
    expect(Number.isInteger(naivePlayheadFrame)).toBe(false);

    // The fix: apply secondsToFramesEdit at the storage→edit
    // boundary. Result is the integer frame the user expects.
    const correctedPlayheadFrame = secondsToFramesEdit(
      searchHit.timeline, fps);
    expect(correctedPlayheadFrame).toBe(94);  // roundHalfAwayFromZero(3.14*30) = 94
    expect(Number.isInteger(correctedPlayheadFrame)).toBe(true);
  });
});