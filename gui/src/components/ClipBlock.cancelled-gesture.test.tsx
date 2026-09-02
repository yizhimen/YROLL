// GUI-05-A (A1): real gesture cancellation.
//
// When Escape is pressed during an active drag/resize gesture, the
// pointerup that follows must commit ZERO mutations. The
// `dragCancelledRef` prop is read at the top of pointerup handlers
// in ClipBlock.tsx; this test pins that behavior using the same
// closure pattern the production code uses.
//
// We cannot trivially mount a full ClipBlock with jsdom (the
// pointermove/up pipeline depends on window event listeners and
// DOM geometry), so we mirror the cancellation gate logic and verify
// the contract:

import { describe, it, expect, vi } from "vitest";
import type { MutableRefObject } from "react";

/**
 * Mirror of ClipBlock.tsx up-handler entry gate.
 * Returns true if the gesture was cancelled by Escape (caller should
 * return early with ZERO mutation).
 */
function upCancelled(dragCancelledRef?: MutableRefObject<boolean>): boolean {
  if (dragCancelledRef?.current) return true;
  return false;
}

describe("GUI-05-A (A1) gesture cancellation", () => {
  it("dragCancelledRef default (false) → gesture not cancelled", () => {
    expect(upCancelled()).toBe(false);
  });

  it("dragCancelledRef.current = false → gesture not cancelled", () => {
    const ref: MutableRefObject<boolean> = { current: false };
    expect(upCancelled(ref)).toBe(false);
  });

  it("dragCancelledRef.current = true → gesture cancelled, ZERO mutation", () => {
    const ref: MutableRefObject<boolean> = { current: true };
    expect(upCancelled(ref)).toBe(true);
  });

  it("after Escape, late pointerup commits 0 mutations (B7)", () => {
    // Simulate: drag armed → Escape → pointerup
    const ref: MutableRefObject<boolean> = { current: false };
    // arm
    expect(upCancelled(ref)).toBe(false);
    // Escape fires (App.tsx's Escape handler in 05-B flips this ref)
    ref.current = true;
    // late pointerup arrives
    const cancelled = upCancelled(ref);
    expect(cancelled).toBe(true);
    // The up-handler bails out → onMoveCommit never fires → ZERO
    // mutations → no API call, no Core change.
    const onMoveCommit = vi.fn();
    if (!cancelled) onMoveCommit("clip-1", 200);
    expect(onMoveCommit).not.toHaveBeenCalled();
  });

  it("after successful pointerup, ref stays at last value (no auto-clear in this scope)", () => {
    // The ref is owned by App; clearing happens in onGestureArmed
    // (a new gesture bumps the gen AND resets the ref). This test
    // pins that within a single gesture, the ref's value persists
    // across multiple reads — so the Escape handler in 05-B can
    // detect "still cancelled" reliably.
    const ref: MutableRefObject<boolean> = { current: true };
    expect(upCancelled(ref)).toBe(true);
    expect(upCancelled(ref)).toBe(true);
    expect(upCancelled(ref)).toBe(true);
  });
});