// GUI-02.5: FrameClock unit tests.
//
// The clock is a PURE function of (state, now). Tests inject `now`
// directly so they don't depend on performance.now() — this also
// makes the tests deterministic across machines.

import { describe, expect, it } from "vitest";
import {
  type Fps,
  type FrameClock,
  createFrameClock,
  currentFrame,
  play,
  pause,
  seek,
  togglePlay,
} from "./frame-clock";

const FPS_30: Fps = { num: 30, den: 1 };
const FPS_2997: Fps = { num: 30000, den: 1001 };

// ---------------------------------------------------------------------------
// createFrameClock
// ---------------------------------------------------------------------------

describe("createFrameClock", () => {
  it("starts paused at startFrame with rate=0", () => {
    const c = createFrameClock({ startFrame: 0, fps: FPS_30, endFrame: 300, now: 1000 });
    expect(c.playing).toBe(false);
    expect(c.rate).toBe(0);
    expect(c.startFrame).toBe(0);
    expect(c.startTimeMs).toBe(1000);
    expect(c.endFrame).toBe(300);
  });

  it("rounds startFrame / endFrame to integers", () => {
    const c = createFrameClock({
      startFrame: 10.4, endFrame: 299.6, fps: FPS_30, now: 0,
    });
    expect(c.startFrame).toBe(10);
    expect(c.endFrame).toBe(300);
  });

  it("rejects negative startFrame / endFrame", () => {
    expect(() => createFrameClock({ startFrame: -1, fps: FPS_30, endFrame: 100 }))
      .toThrow();
    expect(() => createFrameClock({ startFrame: 0, fps: FPS_30, endFrame: -1 }))
      .toThrow();
  });
});

// ---------------------------------------------------------------------------
// currentFrame — pure function of (state, now)
// ---------------------------------------------------------------------------

describe("currentFrame (30 fps)", () => {
  it("paused: always returns startFrame regardless of now", () => {
    const c = createFrameClock({ startFrame: 50, fps: FPS_30, endFrame: 1000, now: 0 });
    expect(currentFrame(c, 0)).toBe(50);
    expect(currentFrame(c, 1_000_000)).toBe(50);
  });

  it("playing: 1 second elapsed = 30 frames", () => {
    const c = createFrameClock({ startFrame: 0, fps: FPS_30, endFrame: 1000, now: 0 });
    play(c, 1000);  // anchor at frame 0, wall-clock now=1000ms
    expect(currentFrame(c, 2000)).toBe(30);
  });

  it("playing: 500ms elapsed = 15 frames", () => {
    const c = createFrameClock({ startFrame: 0, fps: FPS_30, endFrame: 1000, now: 0 });
    play(c, 0);
    expect(currentFrame(c, 500)).toBe(15);
  });

  it("playing: negative direction (rate=-1) if set explicitly", () => {
    const c = createFrameClock({ startFrame: 100, fps: FPS_30, endFrame: 1000, now: 0 });
    play(c, 0);
    c.rate = -1;
    expect(currentFrame(c, 1000)).toBe(70);  // 100 - 30 = 70
    expect(currentFrame(c, 2000)).toBe(40);
  });

  it("clamps to endFrame when playback passes the end", () => {
    const c = createFrameClock({ startFrame: 990, fps: FPS_30, endFrame: 1000, now: 0 });
    play(c, 0);
    expect(currentFrame(c, 0)).toBe(990);
    expect(currentFrame(c, 500)).toBe(1000);   // 990 + 15 = 1005, clamped to 1000
    expect(currentFrame(c, 100_000)).toBe(1000);
  });

  it("clamps to 0 in reverse playback", () => {
    const c = createFrameClock({ startFrame: 5, fps: FPS_30, endFrame: 1000, now: 0 });
    play(c, 0);
    c.rate = -1;
    // 1s of reverse playback from frame 5 → 5-30 = -25, clamped to 0.
    expect(currentFrame(c, 1000)).toBe(0);
    // Wall-clock advances monotonically in practice; the negative-time
    // case is degenerate. We only verify the clamp at the positive
    // boundary.
  });
});

// ---------------------------------------------------------------------------
// 29.97 DF — fractional fps arithmetic
// ---------------------------------------------------------------------------

describe("currentFrame (29.97 DF)", () => {
  it("1000ms elapsed = 29.97 frames (rounded)", () => {
    const c = createFrameClock({
      startFrame: 0, fps: FPS_2997, endFrame: 100000, now: 0,
    });
    play(c, 0);
    expect(currentFrame(c, 1000)).toBe(30);  // 29.97 rounds to 30
  });

  it("33.367ms elapsed = 1 frame at 29.97", () => {
    // 1/29.97 ≈ 33.3667 ms/frame
    const c = createFrameClock({
      startFrame: 0, fps: FPS_2997, endFrame: 100000, now: 0,
    });
    play(c, 0);
    expect(currentFrame(c, 33.3667)).toBe(1);
  });

  it("60 frames elapsed = ~2.003 seconds wall-clock", () => {
    const c = createFrameClock({
      startFrame: 0, fps: FPS_2997, endFrame: 100000, now: 0,
    });
    play(c, 0);
    // 60 frames at 29.97 = 60 / 29.97 sec ≈ 2.00200 sec
    expect(currentFrame(c, 2002)).toBe(60);
  });
});

// ---------------------------------------------------------------------------
// play / pause / seek — re-anchor at current frame
// ---------------------------------------------------------------------------

describe("play / pause / seek", () => {
  it("play() re-anchors startFrame at the current frame", () => {
    const c = createFrameClock({ startFrame: 0, fps: FPS_30, endFrame: 1000, now: 0 });
    play(c, 0);
    // Advance 500ms = 15 frames
    expect(currentFrame(c, 500)).toBe(15);
    // Pause + re-play at the same wall-clock — frame is preserved
    pause(c, 500);
    expect(c.startFrame).toBe(15);
    expect(c.playing).toBe(false);
    play(c, 500);
    expect(c.startFrame).toBe(15);
    expect(c.playing).toBe(true);
  });

  it("seek() snaps to integer frame and re-anchors startTimeMs", () => {
    const c = createFrameClock({ startFrame: 0, fps: FPS_30, endFrame: 1000, now: 0 });
    const r = seek(c, 240, 1000);
    expect(r).toBe(240);
    expect(c.startFrame).toBe(240);
    expect(c.startTimeMs).toBe(1000);
  });

  it("seek() clamps below 0 to 0", () => {
    const c = createFrameClock({ startFrame: 50, fps: FPS_30, endFrame: 1000, now: 0 });
    expect(seek(c, -10, 0)).toBe(0);
    expect(c.startFrame).toBe(0);
  });

  it("seek() clamps above endFrame to endFrame", () => {
    const c = createFrameClock({ startFrame: 0, fps: FPS_30, endFrame: 1000, now: 0 });
    expect(seek(c, 5000, 0)).toBe(1000);
    expect(c.startFrame).toBe(1000);
  });

  it("seek() rounds non-integer frames via roundHalfAwayFromZero", () => {
    const c = createFrameClock({ startFrame: 0, fps: FPS_30, endFrame: 1000, now: 0 });
    // 10.5 → 11 (round half away from zero)
    expect(seek(c, 10.5, 0)).toBe(11);
    // -10.5 → -10 (would clamp to 0)
    expect(seek(c, -10.5, 0)).toBe(0);
  });

  it("togglePlay returns the new playing state", () => {
    const c = createFrameClock({ startFrame: 0, fps: FPS_30, endFrame: 1000, now: 0 });
    expect(togglePlay(c, 0)).toBe(true);
    expect(c.playing).toBe(true);
    expect(togglePlay(c, 100)).toBe(false);
    expect(c.playing).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Heterogeneous 30seq + 60src — the clock itself is timeline-domain,
// so this is really just verifying the fps conversion is correct.
// ---------------------------------------------------------------------------

describe("heterogeneous FPS (timeline only)", () => {
  it("30fps timeline advances 30 per second regardless of source fps", () => {
    const c = createFrameClock({
      startFrame: 0, fps: FPS_30, endFrame: 30000, now: 0,
    });
    play(c, 0);
    // The clock itself is timeline-domain — the source fps is a
    // separate concern resolved via Core's TimeMap, not the clock.
    expect(currentFrame(c, 1000)).toBe(30);
    expect(currentFrame(c, 60_000)).toBe(1800);
  });

  it("60fps timeline advances 60 per second", () => {
    const c = createFrameClock({
      startFrame: 0, fps: { num: 60, den: 1 }, endFrame: 60000, now: 0,
    });
    play(c, 0);
    expect(currentFrame(c, 1000)).toBe(60);
    expect(currentFrame(c, 500)).toBe(30);
  });
});

// ---------------------------------------------------------------------------
// Pause/resume continuity — wall-clock is monotonic but the clock must
// NOT drift across pause/resume cycles.
// ---------------------------------------------------------------------------

describe("pause/resume continuity", () => {
  it("play→pause→play preserves the frame at pause time", () => {
    const c = createFrameClock({ startFrame: 0, fps: FPS_30, endFrame: 1000, now: 0 });
    play(c, 0);
    expect(currentFrame(c, 1000)).toBe(30);
    pause(c, 1000);
    expect(currentFrame(c, 5000)).toBe(30);  // paused, frame preserved
    play(c, 5000);
    expect(currentFrame(c, 6000)).toBe(60);  // resumed, 30 frames later
  });

  it("seek while playing continues playback from the new frame", () => {
    const c = createFrameClock({ startFrame: 0, fps: FPS_30, endFrame: 1000, now: 0 });
    play(c, 0);
    expect(currentFrame(c, 1000)).toBe(30);
    seek(c, 500, 1500);  // seek to 500 at t=1500 (frame still moves)
    // After seek: startFrame=500, startTime=1500, playing=true.
    // At t=2000: elapsed=500ms, delta=15, frame = 500+15 = 515.
    expect(currentFrame(c, 2000)).toBe(515);
    // At t=2500: elapsed=1000ms, delta=30, frame = 500+30 = 530.
    expect(currentFrame(c, 2500)).toBe(530);
  });
});

// ---------------------------------------------------------------------------
// End-of-timeline clamping — the clock stops at endFrame; the caller
// must explicitly pause() to stop the RAF loop in PreviewPlayer.
// ---------------------------------------------------------------------------

describe("end-of-timeline clamping", () => {
  it("playing past endFrame freezes at endFrame", () => {
    const c = createFrameClock({ startFrame: 990, fps: FPS_30, endFrame: 1000, now: 0 });
    play(c, 0);
    // 1000ms later we'd be at 1020, but clamped to 1000
    expect(currentFrame(c, 1000)).toBe(1000);
    expect(currentFrame(c, 100_000_000)).toBe(1000);
  });
});