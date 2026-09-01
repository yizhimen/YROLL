// GUI-03R6-C follow-up: bringClipIntoView post-refresh, pre-render.
//
// Background: the original `bringClipIntoView` wrapper looked up the
// new clip from the React `project` closure:
//
//     const c = project?.clips[clipId];
//     if (!c) return;          // ← silent no-op for fresh adds
//
// `refresh()` schedules `setProject(fresh)` and the wrapper was
// invoked immediately after — before React re-rendered. The closure's
// `project` still reflected the PRE-mutation state, so for
// `addImageClip` / `addClip` / paste / duplicate the new clip was
// absent and the bring silently no-op'd.
//
// The fix splits the helper into:
//   - `computeBringPlan` (pure, this file's subject)
//   - a thin React wrapper in App.tsx that consumes the plan
//
// The pure planner accepts the canonical frame range via
// `BringOpts.rangeFrames` (supplied by the call site from the
// mutation response or the move intent) and NEVER reads from a
// project closure. The DOM measurements are passed in as data, not
// captured from a closure. This makes the regression testable
// without rendering React.

import { describe, expect, it } from "vitest";
import {
  computeBringPlan,
  type BringMeasurements,
  type BringOpts,
} from "./bring-clip";

// Lightweight DOM-mock factory. Returns plain objects matching the
// BringMeasurements shape — no real jsdom layout (jsdom does not
// implement getBoundingClientRect with viewport math anyway).
function makeMeasurements(
  overrides: Partial<BringMeasurements> = {},
): BringMeasurements {
  const baseContentRect = {
    left: 0, right: 1000, top: 0, bottom: 600,
    width: 1000, height: 600, x: 0, y: 0,
  };
  return {
    pxPerSec: 30,
    seqFps: { num: 30, den: 1 },
    contentEl: {
      clientWidth: 1000,
      getBoundingClientRect: () => baseContentRect,
    },
    clipEl: null,
    ...overrides,
  };
}

describe("R6-C: computeBringPlan pure planner", () => {
  it("selects the clip on every successful plan (visual cue)", () => {
    const plan = computeBringPlan(
      { clipId: "c_new", rangeFrames: { startFrame: 500, endFrame: 650 } },
      makeMeasurements(),
    );
    expect(plan.selectClipId).toBe("c_new");
  });

  it("seek:false by default — no playhead jump", () => {
    const plan = computeBringPlan(
      { clipId: "c1", rangeFrames: { startFrame: 500, endFrame: 650 } },
      makeMeasurements(),
    );
    expect(plan.setPlayheadFrame).toBeNull();
  });

  it("seek:true + rangeFrames → playhead lands at the canonical start", () => {
    const plan = computeBringPlan(
      {
        clipId: "c1",
        rangeFrames: { startFrame: 500, endFrame: 650 },
        seek: true,
      },
      makeMeasurements(),
    );
    expect(plan.setPlayheadFrame).toBe(500);
  });

  it("seek:true WITHOUT rangeFrames → playhead stays put (no synthetic frame)", () => {
    // The helper refuses to invent a frame from nothing. This is the
    // move-without-intent case: should not happen in current code,
    // but the planner must NOT silently seek to frame 0.
    const plan = computeBringPlan(
      { clipId: "c1", seek: true },
      makeMeasurements(),
    );
    expect(plan.setPlayheadFrame).toBeNull();
  });

  it("scroll:'never' → no scrollLeft even with offscreen clip", () => {
    const plan = computeBringPlan(
      {
        clipId: "c1",
        rangeFrames: { startFrame: 9000, endFrame: 9200 },
        scroll: "never",
      },
      makeMeasurements(),
    );
    expect(plan.scrollLeft).toBeNull();
  });

  it("centers the canonical frame in the viewport (pxPerSec × fps math)", () => {
    // pxPerF = pxPerSec × (fps.den / fps.num) = 30 × (1/30) = 1 px/frame
    // target = startFrame * pxPerF - clientWidth/2 = 500 * 1 - 500 = 0
    const plan = computeBringPlan(
      {
        clipId: "c1",
        rangeFrames: { startFrame: 500, endFrame: 650 },
      },
      makeMeasurements({ pxPerSec: 30, seqFps: { num: 30, den: 1 } }),
    );
    expect(plan.scrollLeft).toBe(0);
  });

  it("clamps negative scrollLeft to 0 (frame 0 stays at ContentViewport origin)", () => {
    // startFrame=100 → 100*1 - 500 = -400 → clamped to 0
    const plan = computeBringPlan(
      {
        clipId: "c1",
        rangeFrames: { startFrame: 100, endFrame: 250 },
      },
      makeMeasurements(),
    );
    expect(plan.scrollLeft).toBe(0);
  });

  it("frame-native at heterogeneous fps: 60fps source → pxPerF < 1", () => {
    // pxPerF = 30 × (1/60) = 0.5
    // target = 240 * 0.5 - 500 = 120 - 500 = -380 → clamped to 0
    const plan = computeBringPlan(
      {
        clipId: "c1",
        rangeFrames: { startFrame: 240, endFrame: 360 },
      },
      makeMeasurements({ pxPerSec: 30, seqFps: { num: 60, den: 1 } }),
    );
    expect(plan.scrollLeft).toBe(0);

    // And at 60fps: frame 1200 → 1200*0.5 - 500 = 100
    const plan2 = computeBringPlan(
      {
        clipId: "c1",
        rangeFrames: { startFrame: 1200, endFrame: 1320 },
      },
      makeMeasurements({ pxPerSec: 30, seqFps: { num: 60, den: 1 } }),
    );
    expect(plan2.scrollLeft).toBe(100);
  });

  it("returns scrollLeft:null when contentEl is missing (no scroll possible)", () => {
    const plan = computeBringPlan(
      {
        clipId: "c1",
        rangeFrames: { startFrame: 500, endFrame: 650 },
      },
      makeMeasurements({ contentEl: null }),
    );
    expect(plan.scrollLeft).toBeNull();
  });
});

describe("R6-C follow-up: post-refresh, pre-render regression", () => {
  it("REGRESSION: add clip → refresh schedules React state update → bring still receives the new clip → selected + visible", () => {
    // Simulate the EXACT state at the moment bringClipIntoView runs
    // in App.tsx, AFTER `await fn()` + `await refresh()` succeeded:
    //   1. setProject(fresh) was invoked inside refresh, scheduling a
    //      React state update. The next render has NOT happened yet.
    //   2. The new clip exists on the server (returned by addImageClip).
    //   3. The new clip's DOM element does NOT exist yet (React
    //      render pending).
    //   4. The mutation response carries the canonical frame range
    //      (the call site extracted it via secondsToFramesEdit).
    //
    // The old wrapper would have looked up `project.clips[clipId]`
    // from the closure, found nothing, and silently no-op'd.
    //
    // The new planner MUST:
    //   - select the clip
    //   - compute scrollLeft from rangeFrames (not from a missing
    //     DOM element)
    //   - honor seek:true if requested
    //   - NOT depend on any external "project" lookup

    const opts: BringOpts = {
      clipId: "c_new",
      // Canonical data from the addImageClip mutation response.
      rangeFrames: { startFrame: 500, endFrame: 650 },
      seek: true,
    };
    const measurements: BringMeasurements = makeMeasurements({
      pxPerSec: 30,
      seqFps: { num: 30, den: 1 },
      contentEl: {
        clientWidth: 1000,
        getBoundingClientRect: () => ({
          left: 0, right: 1000, top: 0, bottom: 600,
          width: 1000, height: 600, x: 0, y: 0,
        }),
      },
      clipEl: null,  // post-refresh, pre-render: clip not in DOM
    });

    const plan = computeBringPlan(opts, measurements);

    // Selection: the new clip is selected.
    expect(plan.selectClipId).toBe("c_new");

    // Seek: explicit seek:true honors the canonical frame.
    expect(plan.setPlayheadFrame).toBe(500);

    // Visibility: scrollLeft is computed from rangeFrames, NOT
    // from a missing DOM element. This is the load-bearing
    // assertion — the old code returned null here because
    // clipEl was null and the helper short-circuited.
    expect(plan.scrollLeft).not.toBeNull();
    // pxPerF=1, target = 500*1 - 500 = 0
    expect(plan.scrollLeft).toBe(0);
  });

  it("REGRESSION: same scenario with seek:false (non-seek ops like volume/speed)", () => {
    const plan = computeBringPlan(
      {
        clipId: "c_existing",
        rangeFrames: { startFrame: 1200, endFrame: 1500 },
        // seek defaults to false
      },
      makeMeasurements({ clipEl: null }),
    );
    expect(plan.selectClipId).toBe("c_existing");
    expect(plan.setPlayheadFrame).toBeNull();  // no jump
    // Still scrollable from the canonical range
    expect(plan.scrollLeft).not.toBeNull();
    expect(plan.scrollLeft).toBe(1200 * 1 - 500);  // = 700
  });

  it("REGRESSION: post-refresh case with clipEl=null + no rangeFrames → scrollLeft:null (caller forgot to pass data)", () => {
    // Edge case: a caller invokes bringClipIntoView without
    // rangeFrames. The planner cannot compute a scroll target
    // without a frame, so it leaves scrollLeft null. Selection
    // still happens. This is the safest behavior — never invent
    // a scroll target from nothing.
    const plan = computeBringPlan(
      { clipId: "c_mystery" },  // no rangeFrames
      makeMeasurements({ clipEl: null }),
    );
    expect(plan.selectClipId).toBe("c_mystery");
    expect(plan.scrollLeft).toBeNull();
    expect(plan.setPlayheadFrame).toBeNull();
  });
});

describe("R6-C follow-up: rendered-element branch (post-render, scroll detection)", () => {
  it("scroll:'if-offscreen' + clip fully inside viewport → no scroll", () => {
    // clipRect spans 100..500 inside contentRect 0..1000 → not offscreen
    const plan = computeBringPlan(
      {
        clipId: "c1",
        rangeFrames: { startFrame: 200, endFrame: 350 },
      },
      makeMeasurements({
        clipEl: {
          getBoundingClientRect: () => ({
            left: 100, right: 500, top: 0, bottom: 30,
            width: 400, height: 30, x: 100, y: 0,
          }),
        },
      }),
    );
    expect(plan.scrollLeft).toBeNull();
  });

  it("scroll:'if-offscreen' + clip extends past right edge → scroll", () => {
    // clipRect 800..1200, contentRect 0..1000 → right edge past
    const plan = computeBringPlan(
      {
        clipId: "c1",
        rangeFrames: { startFrame: 800, endFrame: 1200 },
      },
      makeMeasurements({
        clipEl: {
          getBoundingClientRect: () => ({
            left: 800, right: 1200, top: 0, bottom: 30,
            width: 400, height: 30, x: 800, y: 0,
          }),
        },
      }),
    );
    // target = 800 * 1 - 500 = 300
    expect(plan.scrollLeft).toBe(300);
  });

  it("scroll:'if-offscreen' + clip extends before left edge → scroll", () => {
    // clipRect -200..100, contentRect 0..1000 → left edge before
    const plan = computeBringPlan(
      {
        clipId: "c1",
        rangeFrames: { startFrame: 0, endFrame: 100 },
      },
      makeMeasurements({
        clipEl: {
          getBoundingClientRect: () => ({
            left: -200, right: 100, top: 0, bottom: 30,
            width: 300, height: 30, x: -200, y: 0,
          }),
        },
      }),
    );
    // target = 0 * 1 - 500 = -500 → clamped to 0
    expect(plan.scrollLeft).toBe(0);
  });

  it("scroll:'always' + clip in viewport → still scroll", () => {
    const plan = computeBringPlan(
      {
        clipId: "c1",
        rangeFrames: { startFrame: 200, endFrame: 350 },
        scroll: "always",
      },
      makeMeasurements({
        clipEl: {
          getBoundingClientRect: () => ({
            left: 100, right: 500, top: 0, bottom: 30,
            width: 400, height: 30, x: 100, y: 0,
          }),
        },
      }),
    );
    // target = 200 * 1 - 500 = -300 → clamped to 0
    expect(plan.scrollLeft).toBe(0);
  });
});