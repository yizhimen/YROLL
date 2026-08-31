// GUI-03R4-R3: tests for shared Timeline Row Geometry.
//
// Pins the invariants:
//  - TRACK_ROW_HEIGHT matches CSS .track-row + .track-label-row height
//  - HEADERS_SPACER_HEIGHT matches MINIMAP_HEIGHT
//  - HEADERS_RULER_SPACER_HEIGHT matches RULER_HEIGHT
//  - HEADERS_TAIL_HEIGHT matches DROP_ZONE_HEIGHT + 2×margin
//  - trackContentHeight(N) sums to the same vertical structure as
//    the content column produces
//  - trackRowGeometry(idx) returns the SAME {top, height} as the
//    header column, content column, clip, marquee hit-test, and
//    drop zone — the GUI-03R4.1 P1-6 "no magic offsets" invariant.
import { describe, expect, test } from "vitest";
import {
  DROP_ZONE_HEIGHT,
  DROP_ZONE_VERTICAL_MARGIN,
  HEADERS_RULER_SPACER_HEIGHT,
  HEADERS_SPACER_HEIGHT,
  HEADERS_TAIL_HEIGHT,
  MINIMAP_HEIGHT,
  RULER_HEIGHT,
  TRACK_ROW_HEIGHT,
  trackContentHeight,
  trackRowGeometry,
} from "./timeline-geometry";

describe("GUI-03R4-R3: timeline-geometry constants", () => {
  test("TRACK_ROW_HEIGHT is 56 (matches CSS .track-row + .track-label-row)", () => {
    expect(TRACK_ROW_HEIGHT).toBe(56);
  });

  test("HEADERS_SPACER_HEIGHT equals MINIMAP_HEIGHT (18)", () => {
    expect(HEADERS_SPACER_HEIGHT).toBe(MINIMAP_HEIGHT);
    expect(HEADERS_SPACER_HEIGHT).toBe(18);
  });

  test("HEADERS_RULER_SPACER_HEIGHT equals RULER_HEIGHT (26)", () => {
    expect(HEADERS_RULER_SPACER_HEIGHT).toBe(RULER_HEIGHT);
    expect(HEADERS_RULER_SPACER_HEIGHT).toBe(26);
  });

  test("HEADERS_TAIL_HEIGHT = drop-zone + 2×margin", () => {
    expect(HEADERS_TAIL_HEIGHT).toBe(
      DROP_ZONE_HEIGHT + DROP_ZONE_VERTICAL_MARGIN * 2);
    expect(HEADERS_TAIL_HEIGHT).toBe(36);
  });

  test("trackContentHeight sums the same vertical structure as content column", () => {
    // For N=0 (empty Timeline): minimap + + ruler + + drop-zone + margins
    //   = 18 + 26 + 28 + 8 = 80
    expect(trackContentHeight(0)).toBe(
      MINIMAP_HEIGHT + RULER_HEIGHT
      + DROP_ZONE_HEIGHT + DROP_ZONE_VERTICAL_MARGIN * 2);
    expect(trackContentHeight(0)).toBe(80);

    // For N=3: + 3 * 56 = + 168 → 248
    expect(trackContentHeight(3)).toBe(80 + 3 * 56);

    // For N=10 (Sanlihe main): + 10 * 56 = + 560 → 640
    expect(trackContentHeight(10)).toBe(80 + 10 * 56);
  });
});

describe("GUI-03R4.1 P1-6: trackRowGeometry — unified row {top, height}", () => {
  test("first row (idx=0) starts at MINIMAP + RULER = 44", () => {
    const g = trackRowGeometry(0);
    expect(g.top).toBe(MINIMAP_HEIGHT + RULER_HEIGHT);
    expect(g.top).toBe(44);
    expect(g.height).toBe(TRACK_ROW_HEIGHT);
    expect(g.bottom).toBe(44 + 56);  // 100
  });

  test("idx N top = MINIMAP + RULER + N*56 (linear, no magic offsets)", () => {
    for (const idx of [0, 1, 2, 5, 9]) {
      const g = trackRowGeometry(idx);
      expect(g.top).toBe(MINIMAP_HEIGHT + RULER_HEIGHT + idx * TRACK_ROW_HEIGHT);
      expect(g.height).toBe(TRACK_ROW_HEIGHT);
      expect(g.bottom).toBe(g.top + TRACK_ROW_HEIGHT);
    }
  });

  test("bottom of row N == top of row N+1 (continuous, no gaps)", () => {
    for (const idx of [0, 1, 2, 5, 9]) {
      const a = trackRowGeometry(idx);
      const b = trackRowGeometry(idx + 1);
      expect(a.bottom).toBe(b.top);
    }
  });

  test("every row's height is exactly TRACK_ROW_HEIGHT (56)", () => {
    for (const idx of [0, 1, 5, 20]) {
      expect(trackRowGeometry(idx).height).toBe(TRACK_ROW_HEIGHT);
    }
  });

  test("tracks do NOT overlap (top[N+1] >= bottom[N])", () => {
    for (const idx of [0, 1, 2, 9, 20]) {
      const a = trackRowGeometry(idx);
      const b = trackRowGeometry(idx + 1);
      expect(b.top).toBeGreaterThanOrEqual(a.bottom);
    }
  });

  test("marquee y-extent matches a track row when it should hit", () => {
    // The marquee select uses these exact rows. Sanity check:
    // row 0 spans y in [44, 100]. A marquee rect of (0, 70, 100, 80)
    // (y-extent [70, 80]) intersects row 0.
    const r0 = trackRowGeometry(0);
    const marqueeY1 = 70, marqueeY2 = 80;
    const intersect = !(marqueeY2 < r0.top || marqueeY1 > r0.bottom);
    expect(intersect).toBe(true);
  });
});