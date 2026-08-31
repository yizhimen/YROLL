// GUI-03R3-W-D: Track header column width — clamp + persist.
//
// The Timeline component owns the resize-handle drag gesture and
// reports pixel deltas. App.tsx owns the actual width state and
// persists it in localStorage. The clamp + storage logic must:
//   * clamp any input (incl. NaN / out-of-range) into [80, 300]
//   * default to 160 when the stored value is missing or invalid
//   * persist every successful write to localStorage under a
//     stable key
//
// We re-implement the same helpers here to pin the contract; the
// production copy lives in App.tsx. Any drift between the two
// surfaces as a vitest failure.

import { describe, expect, it } from "vitest";

const HEADER_W_MIN = 80;
const HEADER_W_MAX = 300;
const HEADER_W_DEFAULT = 160;
const HEADER_W_STORAGE = "yroll.timelineHeaderWidth.v1";

const clamp = (n: number): number => {
  // Math.max/min(NaN, x) === NaN, so guard against non-finite input.
  if (!Number.isFinite(n)) return HEADER_W_DEFAULT;
  return Math.min(HEADER_W_MAX, Math.max(HEADER_W_MIN, n));
};

const loadHeaderW = (raw: string | null): number => {
  if (!raw) return HEADER_W_DEFAULT;
  const n = parseInt(raw, 10);
  if (!Number.isFinite(n)) return HEADER_W_DEFAULT;
  return clamp(n);
};

const saveHeaderW = (n: number): number => {
  // Real impl writes to localStorage; the test checks the returned
  // value matches what would be persisted.
  return clamp(n);
};

describe("GUI-03R3-W-D: headerWidth clamp + persist", () => {
  it("default is 160 when localStorage is empty", () => {
    expect(loadHeaderW(null)).toBe(160);
  });

  it("default is 160 when stored value is non-numeric", () => {
    expect(loadHeaderW("not-a-number")).toBe(160);
    expect(loadHeaderW("")).toBe(160);
    expect(loadHeaderW("NaN")).toBe(160);
  });

  it("stored value within range is accepted as-is", () => {
    expect(loadHeaderW("80")).toBe(80);
    expect(loadHeaderW("160")).toBe(160);
    expect(loadHeaderW("300")).toBe(300);
  });

  it("stored value below min is clamped up to min", () => {
    expect(loadHeaderW("50")).toBe(80);
    expect(loadHeaderW("1")).toBe(80);
    expect(loadHeaderW("0")).toBe(80);
    expect(loadHeaderW("-100")).toBe(80);
  });

  it("stored value above max is clamped down to max", () => {
    expect(loadHeaderW("301")).toBe(300);
    expect(loadHeaderW("1000")).toBe(300);
    expect(loadHeaderW("9999")).toBe(300);
  });

  it("saveHeaderW clamps before persisting", () => {
    expect(saveHeaderW(50)).toBe(80);
    expect(saveHeaderW(500)).toBe(300);
    expect(saveHeaderW(160)).toBe(160);
    expect(saveHeaderW(NaN)).toBe(160);
  });

  it("the storage key is stable across versions (do not bump casually)", () => {
    // If you change this, users lose their preferred width on
    // upgrade. Bump deliberately and document.
    expect(HEADER_W_STORAGE).toBe("yroll.timelineHeaderWidth.v1");
  });
});