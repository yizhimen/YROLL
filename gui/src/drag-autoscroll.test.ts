// GUI-03R4.1 P0-1: Tests for DragAutoScroll.
//
// Pure-unit tests for the computeSpeedAndDir() helper — no DOM, no
// rAF. The rAF tick is a thin loop wrapper around computeSpeedAndDir
// and is covered by the browser smoke (auto-scroll behavior is only
// observable in a real browser).

import { describe, it, expect } from "vitest";
import {
  DragAutoScroll,
  EDGE_ZONE_PX,
  MAX_SPEED_PX_PER_SEC,
  MIN_EFFECTIVE_SPEED_PX_PER_SEC,
} from "./drag-autoscroll";

class FakeContent {
  rect = { left: 0, right: 1000, top: 0, bottom: 600 };
  scrollWidth = 5000;
  scrollLeft = 0;
  getBoundingClientRect() { return this.rect as DOMRect; }
}

describe("DragAutoScroll.computeSpeedAndDir", () => {
  it("returns speed=0 dir=0 when pointer is in the middle of the viewport", () => {
    const c = new FakeContent();
    const a = new DragAutoScroll(c as unknown as HTMLElement);
    const { dir, speed } = a.computeSpeedAndDir(500);  // center of [0..1000]
    expect(dir).toBe(0);
    expect(speed).toBe(0);
    a.dispose();
  });

  it("engages RIGHT scroll when pointer is in the right edge zone", () => {
    const c = new FakeContent();
    const a = new DragAutoScroll(c as unknown as HTMLElement);
    // Right edge = 1000, EDGE_ZONE_PX=80, so zone is [920, 1000].
    // At x=1000 (touching the edge): t=0 → speed=MAX.
    const r0 = a.computeSpeedAndDir(1000);
    expect(r0.dir).toBe(1);
    expect(r0.speed).toBeCloseTo(MAX_SPEED_PX_PER_SEC, 0);
    // At x=920 (zone boundary): t=1 → speed=0.
    const r1 = a.computeSpeedAndDir(920);
    expect(r1.dir).toBe(1);
    expect(r1.speed).toBe(0);
    a.dispose();
  });

  it("engages LEFT scroll when pointer is in the left edge zone", () => {
    const c = new FakeContent();
    const a = new DragAutoScroll(c as unknown as HTMLElement);
    // Left zone is [0, 80].
    const l0 = a.computeSpeedAndDir(0);
    expect(l0.dir).toBe(-1);
    expect(l0.speed).toBeCloseTo(MAX_SPEED_PX_PER_SEC, 0);
    const l1 = a.computeSpeedAndDir(80);
    expect(l1.dir).toBe(-1);
    expect(l1.speed).toBe(0);
    a.dispose();
  });

  it("speed scales linearly across the zone", () => {
    const c = new FakeContent();
    const a = new DragAutoScroll(c as unknown as HTMLElement);
    // 5 sample points in the right zone [920, 1000].
    const samples = [920, 940, 960, 980, 1000];
    const speeds = samples.map((x) => a.computeSpeedAndDir(x).speed);
    // Monotonically increasing.
    for (let i = 1; i < speeds.length; i++) {
      expect(speeds[i]).toBeGreaterThanOrEqual(speeds[i - 1]);
    }
    // First and last match the boundary conditions.
    expect(speeds[0]).toBeCloseTo(0, 0);
    expect(speeds[speeds.length - 1]).toBeCloseTo(MAX_SPEED_PX_PER_SEC, 0);
    // Midpoint is roughly half MAX (linear ramp).
    const mid = a.computeSpeedAndDir(960).speed;
    expect(mid).toBeGreaterThan(MIN_EFFECTIVE_SPEED_PX_PER_SEC);
    expect(mid).toBeLessThan(MAX_SPEED_PX_PER_SEC);
    expect(mid).toBeCloseTo(MAX_SPEED_PX_PER_SEC / 2, -1);
    a.dispose();
  });

  it("returns speed=0 when pointer is OUTSIDE the ContentViewport rect horizontally", () => {
    const c = new FakeContent();
    const a = new DragAutoScroll(c as unknown as HTMLElement);
    expect(a.computeSpeedAndDir(-50).speed).toBe(0);
    expect(a.computeSpeedAndDir(1500).speed).toBe(0);
    a.dispose();
  });

  it("returns speed=0 for non-finite clientX (defensive)", () => {
    const c = new FakeContent();
    const a = new DragAutoScroll(c as unknown as HTMLElement);
    expect(a.computeSpeedAndDir(NaN).speed).toBe(0);
    expect(a.computeSpeedAndDir(Infinity).speed).toBe(0);
    a.dispose();
  });

  it("returns speed=0 when contentEl is null (defensive)", () => {
    const a = new DragAutoScroll(null);
    const { dir, speed } = a.computeSpeedAndDir(500);
    expect(dir).toBe(0);
    expect(speed).toBe(0);
    a.dispose();
  });

  it("is symmetric: left zone at 40px == right zone at (right-40px)", () => {
    const c = new FakeContent();
    const a = new DragAutoScroll(c as unknown as HTMLElement);
    const l = a.computeSpeedAndDir(40);                // 40px from left edge
    const r = a.computeSpeedAndDir(1000 - 40);         // 40px from right edge
    expect(l.dir).toBe(-1);
    expect(r.dir).toBe(1);
    expect(l.speed).toBeCloseTo(r.speed, 5);
    a.dispose();
  });

  it("EDGE_ZONE_PX is 80 (locked value)", () => {
    expect(EDGE_ZONE_PX).toBe(80);
  });

  it("MAX_SPEED_PX_PER_SEC is positive (locked value)", () => {
    expect(MAX_SPEED_PX_PER_SEC).toBeGreaterThan(0);
  });
});

describe("DragAutoScroll.dispose", () => {
  it("is idempotent", () => {
    const c = new FakeContent();
    const a = new DragAutoScroll(c as unknown as HTMLElement);
    a.dispose();
    a.dispose();
    a.dispose();
    // No-op. We just assert no throw.
    expect(true).toBe(true);
  });

  it("subsequent computeSpeedAndDir returns 0 (no contentEl)", () => {
    const c = new FakeContent();
    const a = new DragAutoScroll(c as unknown as HTMLElement);
    a.dispose();
    expect(a.computeSpeedAndDir(500).speed).toBe(0);
  });
});