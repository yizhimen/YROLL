// GUI-03R4-R3: tests for shared Timeline Row Geometry.
//
// Pins the invariants:
//  - TRACK_ROW_HEIGHT matches CSS .track-row + .track-label-row height
//  - HEADERS_SPACER_HEIGHT matches MINIMAP_HEIGHT
//  - HEADERS_RULER_SPACER_HEIGHT matches RULER_HEIGHT
//  - HEADERS_TAIL_HEIGHT matches DROP_ZONE_HEIGHT + 2×margin
//  - trackContentHeight(N) sums to the same vertical structure as
//    the content column produces
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