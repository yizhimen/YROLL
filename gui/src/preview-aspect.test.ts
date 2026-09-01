// R6.1-C: regression tests for the aspect-fit formula. The pre-R6.1
// formula at PreviewPlayer.tsx:466-473 produced 720×45 for 16:9 on a
// 720×405 stage (a flat strip, 9× too short). These tests pin the
// corrected behavior: the output canvas MUST fit inside the stage in
// both dimensions and MUST preserve the requested aspect ratio to
// within 0.5% tolerance.

import { describe, it, expect } from "vitest";
import { computeCanvasSize, parseAspect } from "./preview-aspect";

const STAGE = { stageWidth: 720, stageHeight: 405, inset: 0 };

describe("parseAspect", () => {
  it("parses '16:9' → {w:16, h:9}", () => {
    expect(parseAspect("16:9")).toEqual({ w: 16, h: 9 });
  });
  it("parses '1:1' → {w:1, h:1}", () => {
    expect(parseAspect("1:1")).toEqual({ w: 1, h: 1 });
  });
  it("falls back to 16:9 for garbage input", () => {
    expect(parseAspect("garbage")).toEqual({ w: 16, h: 9 });
    expect(parseAspect("")).toEqual({ w: 16, h: 9 });
  });
});

describe("computeCanvasSize — 5 standard aspects on a 720x405 stage", () => {
  const cases: Array<{
    aspect: string;
    expectedW: number;
    expectedH: number;
    bound: "width" | "height";
  }> = [
    { aspect: "16:9", expectedW: 720, expectedH: 405, bound: "width" },
    { aspect: "9:16", expectedW: 228, expectedH: 405, bound: "height" },
    { aspect: "1:1",  expectedW: 405, expectedH: 405, bound: "height" },
    { aspect: "4:3",  expectedW: 540, expectedH: 405, bound: "height" },
    { aspect: "3:4",  expectedW: 304, expectedH: 405, bound: "height" },
  ];

  for (const c of cases) {
    it(`${c.aspect} → ${c.expectedW}×${c.expectedH} (${c.bound}-bound)`, () => {
      const r = computeCanvasSize({ ...STAGE, aspect: c.aspect });
      // Allow 1px tolerance for rounding from the 1px / 30, 405 / 9,
      // 405 / 16, etc. computations.
      expect(r.canvas.width).toBeCloseTo(c.expectedW, -1);
      expect(r.canvas.height).toBeCloseTo(c.expectedH, -1);
      expect(r.bound).toBe(c.bound);
    });
  }

  for (const c of cases) {
    it(`${c.aspect}: effective aspect within 0.5% of requested`, () => {
      const r = computeCanvasSize({ ...STAGE, aspect: c.aspect });
      const [aw, ah] = c.aspect.split(":").map(Number);
      const requested = aw / ah;
      const actual = r.canvas.width / r.canvas.height;
      expect(Math.abs(actual - requested) / requested).toBeLessThan(0.005);
    });
  }

  for (const c of cases) {
    it(`${c.aspect}: canvas fits inside stage on both axes`, () => {
      const r = computeCanvasSize({ ...STAGE, aspect: c.aspect });
      expect(r.canvas.width).toBeLessThanOrEqual(STAGE.stageWidth);
      expect(r.canvas.height).toBeLessThanOrEqual(STAGE.stageHeight);
    });
  }
});

describe("computeCanvasSize — inset respected", () => {
  it("16:9 with 16px inset on 752x437 → canvas 720x405", () => {
    const r = computeCanvasSize({
      stageWidth: 752, stageHeight: 437, inset: 16, aspect: "16:9",
    });
    expect(r.canvas.width).toBeCloseTo(720, -1);
    expect(r.canvas.height).toBeCloseTo(405, -1);
  });
});

describe("computeCanvasSize — degenerate stage (very small)", () => {
  it("1:1 on a 10x10 stage → canvas 10x10 (no division by zero)", () => {
    const r = computeCanvasSize({ stageWidth: 10, stageHeight: 10, aspect: "1:1" });
    expect(r.canvas.width).toBe(10);
    expect(r.canvas.height).toBe(10);
  });
  it("16:9 on a 1x1000 stage → width-bound tiny canvas", () => {
    const r = computeCanvasSize({ stageWidth: 1, stageHeight: 1000, aspect: "16:9" });
    expect(r.canvas.width).toBe(1);
    expect(r.canvas.height).toBeCloseTo(1 / 16 * 9, 5);
  });
});
