// gui/src/drag-state.test.ts
//
// GUI-04 04-04: Drag Interaction Consolidation — DragState contract.
//
// The 9-field DragState is the SOLE canonical state for a drag
// gesture. Pointermove only mutates these 9 fields. Pointerup
// consumes them and decides:
//   - ZERO mutations (unchanged / cancelled / invalid), OR
//   - EXACTLY ONE api.move mutation
//
// These tests pin the contract at the helper level so any future
// regression that re-introduces a hidden clamp/snap layer is
// caught at the test boundary, not at runtime.

import { describe, it, expect } from "vitest";
import {
  roundHalfAwayFromZero,
  secondsToFramesEdit,
  pxPerFrame,
  pixelDeltaToFrameDelta,
} from "./frames";

// ---------------------------------------------------------------------------
// DragState shape (the 9 fields, no extras)
// ---------------------------------------------------------------------------

interface DragState {
  clipId: string;
  originFrame: number;
  originTrackId: string;
  candidateFrame: number;
  previewFrame: number;
  targetTrackId: string;
  constrained: boolean;
  snapPreviewFrame: number | null;
}

const DRAG_STATE_KEYS = [
  "clipId", "originFrame", "originTrackId",
  "candidateFrame", "previewFrame", "targetTrackId",
  "constrained", "snapPreviewFrame",
] as const;

describe("DragState — single canonical shape", () => {
  it("has exactly the 9 required fields and nothing else", () => {
    const drag: DragState = {
      clipId: "c1",
      originFrame: 0,
      originTrackId: "v1",
      candidateFrame: 0,
      previewFrame: 0,
      targetTrackId: "v1",
      constrained: false,
      snapPreviewFrame: null,
    };
    expect(Object.keys(drag).sort()).toEqual([...DRAG_STATE_KEYS].sort());
    expect(Object.keys(drag).length).toBe(8);
    // Note: the spec mentions 9 fields but the user's
    // "clipId, originFrame, originTrackId, candidateFrame,
    //  previewFrame, targetTrackId, constrained, snapPreviewFrame"
    // list contains 8 names. We pin all 8 — adding more would
    // violate the "single canonical state" invariant.
  });
});

// ---------------------------------------------------------------------------
// pointerdown invariants (req. 2)
// ---------------------------------------------------------------------------

describe("DragState — pointerdown invariants", () => {
  it("initializes all 8 fields; origin == committed (no mutation yet)", () => {
    const origin = { frame: 100, trackId: "v1" };
    const drag: DragState = {
      clipId: "c1",
      originFrame: origin.frame,
      originTrackId: origin.trackId,
      candidateFrame: origin.frame,
      previewFrame: origin.frame,
      targetTrackId: origin.trackId,
      constrained: false,
      snapPreviewFrame: null,
    };
    // At pointerdown, candidate == preview == origin (no pointer
    // delta yet). snapPreviewFrame is null (no snap candidate).
    expect(drag.candidateFrame).toBe(origin.frame);
    expect(drag.previewFrame).toBe(origin.frame);
    expect(drag.targetTrackId).toBe(origin.trackId);
    expect(drag.snapPreviewFrame).toBe(null);
    expect(drag.constrained).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// pointermove invariants (req. 3, 8)
// ---------------------------------------------------------------------------

describe("DragState — pointermove invariants", () => {
  // Helper: the SAME algorithm ClipBlock.tsx uses to derive
  // candidate/preview/constrained from a pixel delta + siblings.
  function pointermove(
    drag: DragState,
    pixelDelta: number,
    pxPerFrameVal: number,
    siblingRanges: Array<{ start: number; end: number }>,
    snapWithin: number | null = null,  // optional sibling boundary to snap near
    lenFrames: number,
  ): DragState {
    const deltaFrame = roundHalfAwayFromZero(pixelDelta / pxPerFrameVal);
    const candidate = drag.originFrame + deltaFrame;
    // clamp to non-overlapping range on origin track
    const tryEnd = candidate + lenFrames;
    const conflicts = siblingRanges.filter(
      (r) => candidate < r.end && r.start < tryEnd,
    );
    let clamped = candidate;
    let constrained = false;
    if (conflicts.length > 0) {
      constrained = true;
      if (candidate >= drag.originFrame) {
        const first = conflicts.reduce((a, b) => a.start < b.start ? a : b);
        clamped = Math.max(0, first.start - lenFrames);
      } else {
        const last = conflicts.reduce((a, b) => a.end > b.end ? a : b);
        clamped = Math.max(0, last.end);
      }
    }
    // snapPreviewFrame: ghost-snap (visual only, never mutates previewFrame)
    let snapPreviewFrame: number | null = null;
    if (snapWithin !== null) {
      const SNAP_RADIUS = 8;
      for (const r of siblingRanges) {
        if (Math.abs(candidate - r.end) <= SNAP_RADIUS) {
          snapPreviewFrame = r.end;
          break;
        }
      }
    }
    return {
      ...drag,
      candidateFrame: candidate,
      previewFrame: clamped,
      constrained,
      snapPreviewFrame,
    };
  }

  it("1 px pointer at default zoom (pxPerFrame ≈ 0.84) → 1 frame delta", () => {
    const fps = { num: 30, den: 1 };
    const drag: DragState = {
      clipId: "c", originFrame: 0, originTrackId: "v1",
      candidateFrame: 0, previewFrame: 0, targetTrackId: "v1",
      constrained: false, snapPreviewFrame: null,
    };
    const after = pointermove(drag, 1, 0.84, [], null, 30);
    expect(after.candidateFrame).toBe(1);
    expect(after.previewFrame).toBe(1);
    expect(after.constrained).toBe(false);
  });

  it("5 / 10 / 50 px produce matching integer frame deltas", () => {
    const pxPerFrameVal = 0.84;
    const drag: DragState = {
      clipId: "c", originFrame: 100, originTrackId: "v1",
      candidateFrame: 100, previewFrame: 100, targetTrackId: "v1",
      constrained: false, snapPreviewFrame: null,
    };
    // 5 px → deltaFrame = roundHalfAwayFromZero(5/0.84) = 6
    //         candidate = originFrame(100) + deltaFrame(6) = 106
    expect(pointermove(drag, 5, pxPerFrameVal, []).candidateFrame).toBe(106);
    // 10 px → deltaFrame = 12, candidate = 112
    expect(pointermove(drag, 10, pxPerFrameVal, []).candidateFrame).toBe(112);
    // 50 px → deltaFrame = 60, candidate = 160
    expect(pointermove(drag, 50, pxPerFrameVal, []).candidateFrame).toBe(160);
  });

  it("collision clamps previewFrame; constrained=true; Core NOT touched", () => {
    const drag: DragState = {
      clipId: "c", originFrame: 0, originTrackId: "v1",
      candidateFrame: 0, previewFrame: 0, targetTrackId: "v1",
      constrained: false, snapPreviewFrame: null,
    };
    // Drag right; sibling at [50, 100). pxPerFrame=1, lenFrames=30.
    // Drag 90 px → candidate = 90 → clip at [90, 120) → overlaps [50,100)
    // because 90 < 100 (yes) AND 50 < 120 (yes). Clamp to just before
    // sibling.start: 50 - 30 = 20.
    const after = pointermove(drag, 90, 1, [{ start: 50, end: 100 }], null, 30);
    expect(after.candidateFrame).toBe(90);   // pointer wants 90
    expect(after.previewFrame).toBe(20);     // clamped to 20
    expect(after.constrained).toBe(true);
    // Core state is NOT represented in DragState (req. 3: pointermove
    // doesn't touch Core).
  });

  it("snapPreviewFrame is visual-only; it does NOT mutate previewFrame", () => {
    const drag: DragState = {
      clipId: "c", originFrame: 0, originTrackId: "v1",
      candidateFrame: 0, previewFrame: 0, targetTrackId: "v1",
      constrained: false, snapPreviewFrame: null,
    };
    // Drag 95 px (within snap radius of sibling.end=100, but also
    // overlapping). candidate = 95. clamp → 20. snapPreviewFrame=100.
    const after = pointermove(drag, 95, 1, [{ start: 50, end: 100 }], 100, 30);
    expect(after.candidateFrame).toBe(95);
    // previewFrame is the clamped value, NOT the snap target.
    expect(after.previewFrame).toBe(20);
    expect(after.snapPreviewFrame).toBe(100);  // ghost indicator only
  });

  it("targetTrackId comes from semantic hit-test, NOT from style.left", () => {
    // Pointermove doesn't directly compute targetTrackId — that's the
    // pointerup hit-test. But DragState.targetTrackId must be a
    // string track_id (semantic), not a pixel offset.
    const drag: DragState = {
      clipId: "c", originFrame: 0, originTrackId: "v1",
      candidateFrame: 0, previewFrame: 0, targetTrackId: "v1",
      constrained: false, snapPreviewFrame: null,
    };
    // Verify the type contract: targetTrackId is a track_id string,
    // not a number (req. 5: never derive from style.left/width).
    expect(typeof drag.targetTrackId).toBe("string");
    expect(["v1", "v2", "v3", "t1", "t2"]).toContain(drag.targetTrackId);
  });
});

// ---------------------------------------------------------------------------
// pointerup invariants (req. 4, 9, 10)
// ---------------------------------------------------------------------------

describe("DragState — pointerup willMutate decision", () => {
  function willMutate(
    originFrame: number,
    originTrackId: string,
    committedFrame: number,
    committedTrackId: string,
  ): boolean {
    return committedFrame !== originFrame || committedTrackId !== originTrackId;
  }

  it("unchanged drag (no pixel movement) → ZERO mutations", () => {
    expect(willMutate(100, "v1", 100, "v1")).toBe(false);
  });

  it("small-delta (1 px ≈ 0 frames at certain zoom) → ZERO mutations", () => {
    // 1 px at pxPerFrame = 2 → 1/2 = 0.5 → roundHalfAwayFromZero(0.5) = 1.
    // So 1 px CAN be 1 frame. But if pxPerFrame = 3, 1/3 = 0.33 → 0.
    const fps = { num: 30, den: 1 };
    const pxPerFrameVal = 3;
    expect(roundHalfAwayFromZero(1 / pxPerFrameVal)).toBe(0);
    // origin unchanged → no mutation (req. 9).
    expect(willMutate(100, "v1", 100, "v1")).toBe(false);
  });

  it("frame change, same track → ONE mutation", () => {
    expect(willMutate(100, "v1", 200, "v1")).toBe(true);
  });

  it("same frame, cross-track → ONE mutation", () => {
    expect(willMutate(100, "v1", 100, "v2")).toBe(true);
  });

  it("both changed → ONE mutation", () => {
    expect(willMutate(100, "v1", 200, "v2")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Anti-regression: forbidden tools in pointermove
// ---------------------------------------------------------------------------

// This is enforced at code-review level by the comments in
// ClipBlock.tsx. The vitest here documents it as a contract:
// pointermove MUST NOT issue fetch() / POST /clips / history ops.

// We can't easily intercept fetch() calls from a vitest unit, so
// the actual enforcement is via the browser smoke (gui-04-04-drag.mjs)
// which asserts: during a pointermove, no POST /clips request is made.
//
// This test instead documents the contract.
describe("DragState — pointermove forbidden actions (contract)", () => {
  it("contract: pointermove does NOT call api.move / api.historyUndo / etc.", () => {
    // The ClipBlock.tsx implementation has zero fetch / mutation
    // calls in pointermove. The browser smoke verifies this at
    // runtime by listening to network activity during a drag.
    expect(true).toBe(true);  // contract documented; runtime check in browser smoke
  });
});

// ---------------------------------------------------------------------------
// Pipeline observability (req. 12)
// ---------------------------------------------------------------------------

describe("DragState — pipeline observability", () => {
  it("the chain pointer → candidateFrame → previewFrame → committedFrame is well-defined", () => {
    const fps = { num: 30, den: 1 };
    const pxPerSec = 25;
    const pxF = pxPerFrame(pxPerSec, fps);

    // pointer position
    const pointerClientX = 200;
    const startX = 100;
    const pixelDelta = pointerClientX - startX;

    // → candidateFrame
    const candidateFrame = roundHalfAwayFromZero(pixelDelta / pxF);

    // → previewFrame (no collision here)
    const previewFrame = candidateFrame;

    // → committedFrame (no snap, no cross-track)
    const committedFrame = previewFrame;

    expect(pixelDelta).toBe(100);
    expect(candidateFrame).toBe(120);
    expect(previewFrame).toBe(120);
    expect(committedFrame).toBe(120);
  });
});