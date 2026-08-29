// GUI-02.4: ClipBlock is FRAME-ONLY.
//
// These tests pin the invariants from the closure spec:
//
//   - Drag emits integer TimelineFrame candidates via pixelDeltaToFrameDelta
//     + roundHalfAwayFromZero. No `* clip.speed`, no Math.round on edit
//     coords, no SNAP_RADIUS_SEC.
//   - Trim drag emits integer source-frame intent (no `* clip.speed`).
//   - The drag preview and the drag-end snap use the SAME final
//     candidate frame coordinate.
//   - Heterogeneous source FPS (sequence 30 + source 60) does not
//     cause ClipBlock to do local TimeMap business math.
//
// We exercise the drag math by invoking the pointermove handler
// indirectly via a synthetic PointerEvent on the rendered component.
// React Testing Library + jsdom provides the event plumbing.

import { describe, expect, it, vi } from "vitest";
import { fireEvent } from "@testing-library/react";
import { render } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { useState } from "react";

import ClipBlock from "./ClipBlock";
import type { Clip } from "../api";

// Mock the api module so ClipBlock's drag-end snap call doesn't hit
// the network. The mock returns the unsnapped frame unchanged so the
// drag-end handler's snap-or-pass-through logic is observable.
vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      snap: vi.fn(async (frame: number) => ({ snapped_frame: frame, target: null })),
    },
  };
});

const FPS_24 = { num: 24, den: 1 };
const FPS_30 = { num: 30, den: 1 };
const FPS_2997 = { num: 30000, den: 1001 };
const FPS_60 = { num: 60, den: 1 };

function makeClip(overrides: Partial<Clip> = {}): Clip {
  return {
    clip_id: "c1",
    asset_id: "a1",
    track_id: "v1",
    source_range: { start: 0, end: 10 },
    timeline_range: { start: 0, end: 10 },
    speed: 1.0,
    volume: 1.0,
    transform: {},
    adjustments: [],
    context: {},
    ...overrides,
  } as Clip;
}

interface Harness {
  /** Get the most recent dragMove callback argument. */
  lastDragFrame: () => number | null;
  /** Get the most recent dragMove commit (frame on pointerup). */
  lastCommitFrame: () => number | null;
  /** Get the most recent trim commit (srcStart, srcEnd) in source frames. */
  lastTrim: () => { srcStart: number | null; srcEnd: number | null } | null;
}

function makeHarness(
  clip: Clip,
  pxPerFrame: number,
  seqFps: { num: number; den: number } = FPS_30,
  sourceFps?: { num: number; den: number },
  snapMode: "always" | "alt" | "off" = "off",  // default off for test predictability
): { container: HTMLElement; harness: Harness } {
  const captured: {
    dragFrame: number | null;
    commitFrame: number | null;
    trim: { srcStart: number | null; srcEnd: number | null } | null;
  } = { dragFrame: null, commitFrame: null, trim: null };

  function Wrapper() {
    const [, force] = useState(0);
    return (
      <ClipBlock
        clip={clip}
        selected={true}
        pxPerFrame={pxPerFrame}
        seqFps={seqFps}
        sourceFps={sourceFps}
        siblings={[]}
        onSelect={() => force((x) => x + 1)}
        snapMode={snapMode}
        onDragMove={(_cid, frame) => {
          captured.dragFrame = frame;
          force((x) => x + 1);
        }}
        onMoveCommit={(_cid, frame) => {
          captured.commitFrame = frame;
          force((x) => x + 1);
        }}
        onTrimCommit={(_cid, srcStart, srcEnd) => {
          captured.trim = { srcStart, srcEnd };
          force((x) => x + 1);
        }}
      />
    );
  }

  const { container } = render(<Wrapper />);

  return {
    container,
    harness: {
      lastDragFrame: () => captured.dragFrame,
      lastCommitFrame: () => captured.commitFrame,
      lastTrim: () => captured.trim,
    },
  };
}

// ---------------------------------------------------------------------------
// Frame-only drag: integer TimelineFrame via pixelDeltaToFrameDelta
// ---------------------------------------------------------------------------

describe("ClipBlock drag: frame-only via pixelDeltaToFrameDelta", () => {
  it("pxPerFrame=0.4 (30fps at pxPerSec=12), 1 frame pixel delta", () => {
    // At 30fps, pxPerSec=12 → pxPerFrame = 12 * 1 / 30 = 0.4 px/frame.
    // snapMode="off" so we measure pure pixelDeltaToFrameDelta.
    const clip = makeClip({
      timeline_range: { start: 50, end: 60 },
    });
    const { container, harness } = makeHarness(clip, 0.4, FPS_30, undefined, "off");
    const root = container.querySelector(".clip") as HTMLElement;
    expect(root).toBeTruthy();
    fireEvent.pointerDown(root, { clientX: 100, clientY: 0 });
    window.dispatchEvent(new PointerEvent("pointermove", { clientX: 100.4, clientY: 0 }));
    expect(harness.lastDragFrame()).toBe(1501);
  });

  it("pxPerFrame=0.5 (24fps at pxPerSec=12), 1 frame pixel delta", () => {
    const clip = makeClip({
      timeline_range: { start: 50, end: 60 },  // 1200..1440 frames @ 24fps
    });
    const { container, harness } = makeHarness(clip, 0.5, FPS_24, undefined, "off");
    const root = container.querySelector(".clip") as HTMLElement;
    fireEvent.pointerDown(root, { clientX: 100, clientY: 0 });
    window.dispatchEvent(new PointerEvent("pointermove", { clientX: 100.5, clientY: 0 }));
    expect(harness.lastDragFrame()).toBe(1201);
  });

  it("pxPerFrame=0.2 (60fps at pxPerSec=12), 1 frame pixel delta", () => {
    const clip = makeClip({
      timeline_range: { start: 50, end: 60 },  // 3000..3600 frames @ 60fps
    });
    const { container, harness } = makeHarness(clip, 0.2, FPS_60, undefined, "off");
    const root = container.querySelector(".clip") as HTMLElement;
    fireEvent.pointerDown(root, { clientX: 100, clientY: 0 });
    window.dispatchEvent(new PointerEvent("pointermove", { clientX: 100.2, clientY: 0 }));
    expect(harness.lastDragFrame()).toBe(3001);
  });

  it("pxPerFrame at 30000/1001: 1 frame delta is ~0.0334 px", () => {
    const pxPerF = 12 * 1001 / 30000;
    const clip = makeClip({
      timeline_range: { start: 50, end: 60 },
    });
    const { container, harness } = makeHarness(clip, pxPerF, FPS_2997, undefined, "off");
    const root = container.querySelector(".clip") as HTMLElement;
    fireEvent.pointerDown(root, { clientX: 100, clientY: 0 });
    window.dispatchEvent(new PointerEvent("pointermove", { clientX: 100 + pxPerF, clientY: 0 }));
    expect(harness.lastDragFrame()).toBe(1500);
  });

  it("roundHalfAwayFromZero asymmetry: +1.5 → +2 (NOT Math.round's +2 here, but +1 for -1.5)", async () => {
    // snapMode="off" to isolate rounding.
    // Test the helper directly — that's where the asymmetry lives.
    // The ClipBlock uses pixelDeltaToFrameDelta which delegates to
    // roundHalfAwayFromZero, so testing the helper is sufficient to
    // pin the asymmetric tie-breaking behavior the spec requires.
    const { roundHalfAwayFromZero } = await import("../frames");
    expect(roundHalfAwayFromZero(1.5)).toBe(2);   // +0.5 → +1 above 0
    expect(roundHalfAwayFromZero(-1.5)).toBe(-2);  // -0.5 → -1 below 0 (NOT Math.round's 0/-1)
  });

  it("non-integer pixel deltas: 0.8px @ pxPerFrame=0.4 → 2 frames (roundHalfAwayFromZero(2)=2)", () => {
    // snapMode="off" prevents snap from catching the drag.
    // 0.8 px @ pxPerSec=12 (pxPerFrame=0.4) = exactly 2.0 frames.
    // This verifies the integer frame emitted for a non-tied drag,
    // which is what the spec's "drag preview == drag-end snap
    // target" invariant depends on. (We don't test the tie-breaking
    // asymmetry at the integration level because IEEE-754 makes
    // 1.5 unrepresentable; the helper unit test above pins that.)
    const clip = makeClip({
      timeline_range: { start: 50, end: 60 },
    });
    const { container, harness } = makeHarness(clip, 0.4, FPS_30, undefined, "off");
    const root = container.querySelector(".clip") as HTMLElement;
    fireEvent.pointerDown(root, { clientX: 100, clientY: 0 });
    window.dispatchEvent(new PointerEvent("pointermove", { clientX: 100.8, clientY: 0 }));
    expect(harness.lastDragFrame()).toBe(1502);
  });
});

// ---------------------------------------------------------------------------
// Snap consistency: drag preview == drag-end snap target
// ---------------------------------------------------------------------------

describe("ClipBlock: drag preview == drag-end snap target", () => {
  it("pointerup emits the same integer TimelineFrame as the last pointermove (with snap idempotent)", async () => {
    const clip = makeClip({
      timeline_range: { start: 0, end: 10 },
    });
    const { container, harness } = makeHarness(clip, 0.4, FPS_30);
    const root = container.querySelector(".clip") as HTMLElement;
    fireEvent.pointerDown(root, { clientX: 100, clientY: 0 });
    // Drag by +10 frames = 4 px (since pxPerFrame=0.4).
    window.dispatchEvent(new PointerEvent("pointermove", { clientX: 104, clientY: 0 }));
    const lastDrag = harness.lastDragFrame();
    expect(lastDrag).toBe(10);
    // Drag end: should emit onMoveCommit with the same coordinate
    // (the mock snap returns the frame unchanged).
    await new Promise((r) => setTimeout(r, 0));
    window.dispatchEvent(new PointerEvent("pointerup", { clientX: 104, clientY: 0 }));
    await new Promise((r) => setTimeout(r, 10));
    expect(harness.lastCommitFrame()).toBe(lastDrag);
  });
});

// ---------------------------------------------------------------------------
// Trim drag: integer source-frame deltas, no `* clip.speed`
// ---------------------------------------------------------------------------

describe("ClipBlock trim: integer source-frame deltas (no speed math)", () => {
  it("left edge drag by 1 source frame emits srcStartFrame+1", () => {
    const clip = makeClip({
      source_range: { start: 0, end: 10 },
      timeline_range: { start: 0, end: 10 },
    });
    // pxPerFrame=0.4 (timeline). Trim uses the same pxPerFrame but
    // maps pixel delta to source-frame delta via the asset's source
    // fps (which defaults to seq fps when sourceFps is undefined).
    const { container, harness } = makeHarness(clip, 0.4, FPS_30);
    const leftHandle = container.querySelector(".trim-handle.left") as HTMLElement;
    expect(leftHandle).toBeTruthy();
    fireEvent.pointerDown(leftHandle, { clientX: 100, clientY: 0 });
    // Drag by +0.4 px = +1 source-frame (when source_fps == seq_fps).
    window.dispatchEvent(new PointerEvent("pointermove", { clientX: 100.4, clientY: 0 }));
    // Commit on pointerup. Original srcStart = 0 sec * 30 = 0 frame.
    // +1 source frame → commit srcStart = 1.
    window.dispatchEvent(new PointerEvent("pointerup", { clientX: 100.4, clientY: 0 }));
    const trim = harness.lastTrim();
    expect(trim).toEqual({ srcStart: 1, srcEnd: null });
  });

  it("right edge drag by 1 source frame emits srcEndFrame+1", () => {
    const clip = makeClip({
      source_range: { start: 0, end: 10 },
      timeline_range: { start: 0, end: 10 },
    });
    const { container, harness } = makeHarness(clip, 0.4, FPS_30);
    const rightHandle = container.querySelector(".trim-handle.right") as HTMLElement;
    fireEvent.pointerDown(rightHandle, { clientX: 100, clientY: 0 });
    window.dispatchEvent(new PointerEvent("pointermove", { clientX: 100.4, clientY: 0 }));
    window.dispatchEvent(new PointerEvent("pointerup", { clientX: 100.4, clientY: 0 }));
    const trim = harness.lastTrim();
    expect(trim).toEqual({ srcStart: null, srcEnd: 301 });
  });

  it("trim below MIN_TRIM_DELTA_FRAMES is a no-op (no commit)", () => {
    const clip = makeClip({
      source_range: { start: 0, end: 10 },
      timeline_range: { start: 0, end: 10 },
    });
    const { container, harness } = makeHarness(clip, 0.4, FPS_30);
    const leftHandle = container.querySelector(".trim-handle.left") as HTMLElement;
    fireEvent.pointerDown(leftHandle, { clientX: 100, clientY: 0 });
    // Drag by less than 1 source-frame's worth of pixels (sub-pixel).
    window.dispatchEvent(new PointerEvent("pointermove", { clientX: 100.1, clientY: 0 }));
    window.dispatchEvent(new PointerEvent("pointerup", { clientX: 100.1, clientY: 0 }));
    // No commit should have been emitted.
    expect(harness.lastTrim()).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Heterogeneous source FPS: 30seq + 60src
// ---------------------------------------------------------------------------

describe("ClipBlock: heterogeneous 30seq + 60src", () => {
  it("drag far enough to escape snap (8 frame radius): 30seq + 60src → timeline frames only", () => {
    // Sequence is 30fps. Drag deltas are in timeline frame coordinates.
    // The source fps (60) affects only the trim drag and display
    // labels, never the timeline move delta. timeline_range.start in
    // seconds → 10s @ 30fps = 300 frames. Drag by 20 timeline-frames
    // (= 8px @ pxPerFrame=0.4) so we escape the snap radius.
    const clip = makeClip({
      timeline_range: { start: 10, end: 20 },  // 300..600 frames @ 30fps
    });
    const { container, harness } = makeHarness(clip, 0.4, FPS_30, FPS_60);
    const root = container.querySelector(".clip") as HTMLElement;
    fireEvent.pointerDown(root, { clientX: 100, clientY: 0 });
    // 20 timeline frames @ pxPerFrame=0.4 = 8 px drag
    window.dispatchEvent(new PointerEvent("pointermove", { clientX: 108, clientY: 0 }));
    expect(harness.lastDragFrame()).toBe(320);  // 300 + 20
  });

  it("left-edge trim drag with 60fps source: pxPerFrame=0.4 @ 30seq → pxPerFrame(source)=0.2", () => {
    // seq=30, src=60, pxPerFrame_timeline=0.4, pxPerSec=12.
    // pxPerFrame_source = pxPerSec / sourceFps = 12 / 60 = 0.2 px/src-frame.
    // So 0.2 px drag = 1 source-frame.
    const clip = makeClip({
      source_range: { start: 0, end: 10 },
      timeline_range: { start: 0, end: 10 },
    });
    const { container, harness } = makeHarness(clip, 0.4, FPS_30, FPS_60);
    const leftHandle = container.querySelector(".trim-handle.left") as HTMLElement;
    fireEvent.pointerDown(leftHandle, { clientX: 100, clientY: 0 });
    window.dispatchEvent(new PointerEvent("pointermove", { clientX: 100.2, clientY: 0 }));
    window.dispatchEvent(new PointerEvent("pointerup", { clientX: 100.2, clientY: 0 }));
    expect(harness.lastTrim()).toEqual({ srcStart: 1, srcEnd: null });
  });
});

// ---------------------------------------------------------------------------
// Source/sequence fps NEVER assumed equal in edit coords
// ---------------------------------------------------------------------------

describe("ClipBlock: source_fps and seq_fps are explicitly distinct", () => {
  it("renders without crash when sourceFps is undefined (degraded display)", () => {
    const clip = makeClip();
    const { container } = makeHarness(clip, 0.4, FPS_30, undefined);
    expect(container.querySelector(".clip")).toBeTruthy();
  });

  it("renders without crash when sourceFps === seqFps (conformant)", () => {
    const clip = makeClip();
    const { container } = makeHarness(clip, 0.4, FPS_30, FPS_30);
    expect(container.querySelector(".clip")).toBeTruthy();
  });

  it("renders without crash when sourceFps !== seqFps (heterogeneous)", () => {
    const clip = makeClip();
    const { container } = makeHarness(clip, 0.4, FPS_30, FPS_60);
    expect(container.querySelector(".clip")).toBeTruthy();
  });
});