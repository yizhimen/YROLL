// GUI-02: Conformance vectors for frames.ts.
//
// The 6 user-pinned DF vectors are the source of truth. The Python
// implementation in yroll/core/timebase.py and this TypeScript
// implementation MUST agree on every vector. The shared vector list
// is USER_PINNED_DF here (exported by frames.ts) and mirrored in
// tests/test_timecode_conformance.py.
//
// Closure note: F=30 -> "00:00:01;00" (the standard bijective map),
// F=1798 -> "00:01:00;00" (a DROPPED label — from_timecode MUST raise).

import { describe, expect, it } from "vitest";

import {
  framesToTimecode,
  timecodeToFrames,
  USER_PINNED_DF,
  rational,
  framesToSeconds,
  secondsToFrames,
  pxPerFrame,
  playheadFrameToPixel,
  pixelToPlayheadFrame,
  roundHalfAwayFromZero,
  pixelDeltaToFrameDelta,
  chooseZoomProfile,
  chooseTickStep,
  chooseLabelFormat,
} from "./frames";

const FPS_30 = rational(30, 1);
const FPS_24 = rational(24, 1);
const FPS_25 = rational(25, 1);
const FPS_60 = rational(60, 1);
const FPS_30000_1001 = rational(30000, 1001);

describe("conformance: 6 user-pinned DF vectors at 30000/1001", () => {
  for (const [frame, expected] of USER_PINNED_DF) {
    it(`frame ${frame} → ${expected}`, () => {
      expect(framesToTimecode(frame, FPS_30000_1001, true)).toBe(expected);
    });
  }
});

describe("conformance: DF roundtrip (5 vectors; F=1798 raises)", () => {
  // Standard bijective DF: every non-dropped label maps back to its
  // F. F=1798's label "00:01:00;00" IS a dropped label (NDF 1800),
  // so timecodeToFrames must raise — the round-trip is intentionally
  // asymmetric (to_timecode produces a label the inverse rejects).
  for (const [frame, expected] of USER_PINNED_DF) {
    it(`frame ${frame} → ${expected} → ${frame === 1798 ? "raises" : "frame"}`, () => {
      const s = framesToTimecode(frame, FPS_30000_1001, true);
      if (frame === 1798) {
        expect(() => timecodeToFrames(s, FPS_30000_1001, true))
          .toThrowError(/dropped NDF label/);
      } else {
        const back = timecodeToFrames(s, FPS_30000_1001, true);
        expect(back).toBe(frame);
      }
    });
  }
});

describe("conformance: F=1798 round-trip asymmetry is pinned", () => {
  // F=1798 → "00:01:00;00" (DF, the standard algorithm).
  // "00:01:00;00" → RAISE (it's a dropped label).
  // The inverse of the inverse (i.e. asserting a fresh DF round-trip
  // from a non-dropped label) is covered by the loop above.
  it("to_timecode(1798, DF) === '00:01:00;00'", () => {
    expect(framesToTimecode(1798, FPS_30000_1001, true)).toBe("00:01:00;00");
  });
  it("from_timecode('00:01:00;00') raises 'dropped NDF label'", () => {
    expect(() => timecodeToFrames("00:01:00;00", FPS_30000_1001, true))
      .toThrowError(/dropped NDF label/);
  });
  it("from_timecode('00:01:00;00') raises even without explicit flag (semicolon separator)", () => {
    expect(() => timecodeToFrames("00:01:00;00", FPS_30000_1001))
      .toThrowError(/dropped NDF label/);
  });
});

// Illegal dropped NDF labels must raise. The 2 dropped NDF frame
// numbers at the start of each non-10th minute are NOT displayable
// inputs. Per closure spec, from_timecode rejects them.
const DROPPED_DF_LABELS = [
  "00:01:00;00",   // NDF 1800 (dropped, minute 1 of 1st 10-min)
  "00:01:00;01",   // NDF 1801 (dropped)
  "00:02:00;00",   // NDF 3600 (dropped, minute 2)
  "00:02:00;01",   // NDF 3601 (dropped)
  "00:09:00;00",   // NDF 16200 (dropped, minute 9 of 1st 10-min)
  "00:09:00;01",   // NDF 16201 (dropped)
  "00:11:00;00",   // NDF 19800 (dropped, minute 1 of 2nd 10-min)
  "00:11:00;01",   // NDF 19801 (dropped)
];

describe("conformance: dropped DF labels raise", () => {
  for (const label of DROPPED_DF_LABELS) {
    it(`from_timecode("${label}") raises "dropped NDF label"`, () => {
      expect(() => timecodeToFrames(label, FPS_30000_1001, true))
        .toThrowError(/dropped NDF label/);
    });
    it(`from_timecode("${label}") raises even without explicit flag`, () => {
      expect(() => timecodeToFrames(label, FPS_30000_1001))
        .toThrowError(/dropped NDF label/);
    });
  }
});

// Out-of-range fields also raise.
describe("conformance: out-of-range fields raise", () => {
  const cases: Array<[string, RegExp]> = [
    ["00:00:00;30", /out-of-range/],   // FF >= fpsInt (30)
    ["00:00:60;00", /out-of-range/],   // SS >= 60
    ["00:60:00;00", /out-of-range/],   // MM >= 60
    ["24:00:00;00", /hour > 23/],      // HH >= 24
  ];
  for (const [label, matchRe] of cases) {
    it(`from_timecode("${label}") raises`, () => {
      expect(() => timecodeToFrames(label, FPS_30000_1001, true))
        .toThrowError(matchRe);
    });
  }
});

describe("conformance: NDF at 24/25/30/60 fps", () => {
  const NDF = [
    [FPS_30, 0, "00:00:00:00"],
    [FPS_30, 29, "00:00:00:29"],
    [FPS_30, 30, "00:00:01:00"],
    [FPS_30, 60, "00:00:02:00"],
    [FPS_30, 1798, "00:00:59:28"],
    [FPS_30, 17982, "00:09:59:12"],
    [FPS_24, 0, "00:00:00:00"],
    [FPS_24, 23, "00:00:00:23"],
    [FPS_24, 24, "00:00:01:00"],
    [FPS_24, 86400, "01:00:00:00"],
    [FPS_25, 24, "00:00:00:24"],
    [FPS_25, 25, "00:00:01:00"],
    [FPS_60, 60, "00:00:01:00"],
    [FPS_60, 108000, "00:30:00:00"],
    [FPS_30000_1001, 0, "00:00:00:00"],
    [FPS_30000_1001, 30, "00:00:01:00"],
    [FPS_30000_1001, 17982, "00:09:59:12"],
  ] as const;
  for (const [fps, frame, expected] of NDF) {
    it(`${fps.num}/${fps.den} frame ${frame} → ${expected}`, () => {
      expect(framesToTimecode(frame, fps, false)).toBe(expected);
    });
  }
});

describe("conformance: NDF roundtrip", () => {
  const cases = [0, 29, 30, 60, 1798, 17982];
  for (const frame of cases) {
    it(`frame ${frame} round-trip`, () => {
      const s = framesToTimecode(frame, FPS_30, false);
      expect(timecodeToFrames(s, FPS_30, false)).toBe(frame);
    });
  }
});

describe("roundHalfAwayFromZero: editor rounding policy", () => {
  it("symmetric tie-breaking: +0.5 → +1, -0.5 → -1", () => {
    expect(roundHalfAwayFromZero(0.5)).toBe(1);
    expect(roundHalfAwayFromZero(-0.5)).toBe(-1);
  });
  it("+1.5 → +2, -1.5 → -2", () => {
    expect(roundHalfAwayFromZero(1.5)).toBe(2);
    expect(roundHalfAwayFromZero(-1.5)).toBe(-2);
  });
  it("below-half rounds toward 0", () => {
    expect(roundHalfAwayFromZero(0.49)).toBe(0);
    expect(roundHalfAwayFromZero(-0.49)).toBe(0);
  });
});

describe("pxPerFrame: stable perceived-pxPerSec", () => {
  it("at 30 fps, pxPerSec=12 → pxPerFrame=0.4", () => {
    expect(pxPerFrame(12, FPS_30)).toBeCloseTo(0.4);
  });
  it("at 30000/1001, pxPerSec=12 → pxPerFrame=12*1001/30000", () => {
    expect(pxPerFrame(12, FPS_30000_1001)).toBeCloseTo(12 * 1001 / 30000);
  });
  it("at 60 fps, pxPerSec=12 → pxPerFrame=0.2", () => {
    expect(pxPerFrame(12, FPS_60)).toBeCloseTo(0.2);
  });
});

describe("zoom change preserves frame (when pxPerFrame is integer)", () => {
  const CASES: Array<[number, ReturnType<typeof rational>]> = [
    [30, FPS_30],     // pxPerFrame = 1
    [60, FPS_30],     // pxPerFrame = 2
    [120, FPS_30],    // pxPerFrame = 4
    [60, FPS_60],     // pxPerFrame = 1
  ];
  for (const [zoom, fps] of CASES) {
    it(`zoom=${zoom} fps=${fps.num}/${fps.den}: frame=528 round-trips`, () => {
      const frame = 528;
      const px = playheadFrameToPixel(frame, zoom, fps);
      const back = pixelToPlayheadFrame(px, zoom, fps);
      expect(back).toBe(frame);
    });
  }
});

describe("pixelDeltaToFrameDelta: drag pxPerFrame → exactly 1 frame", () => {
  const ZOOMS = [30, 60, 120, 240];
  const FPSES = [FPS_24, FPS_25, FPS_30, FPS_60];
  for (const zoom of ZOOMS) {
    for (const fps of FPSES) {
      it(`zoom=${zoom} fps=${fps.num}/${fps.den}`, () => {
        const pxPerF = pxPerFrame(zoom, fps);
        const delta = pixelDeltaToFrameDelta(pxPerF, zoom, fps);
        expect(delta).toBe(1);
      });
    }
  }
});

describe("frame < 0.5 / = 0.5 / > 0.5 frame boundaries", () => {
  const zoom = 12;
  const fps = FPS_30;
  it("0.49 frame → 0", () => {
    expect(pixelDeltaToFrameDelta(pxPerFrame(zoom, fps) * 0.49, zoom, fps)).toBe(0);
  });
  it("0.5 frame → 1 (round half away from zero)", () => {
    expect(pixelDeltaToFrameDelta(pxPerFrame(zoom, fps) * 0.5, zoom, fps)).toBe(1);
  });
  it("0.51 frame → 1", () => {
    expect(pixelDeltaToFrameDelta(pxPerFrame(zoom, fps) * 0.51, zoom, fps)).toBe(1);
  });
  it("1.0 frame → 1", () => {
    expect(pixelDeltaToFrameDelta(pxPerFrame(zoom, fps) * 1.0, zoom, fps)).toBe(1);
  });
  it("-0.5 frame → -1 (NOT 0)", () => {
    expect(pixelDeltaToFrameDelta(-pxPerFrame(zoom, fps) * 0.5, zoom, fps)).toBe(-1);
  });
});

describe("framesToSeconds / secondsToFrames", () => {
  it("at 30 fps, 1 sec = 30 frames", () => {
    expect(framesToSeconds(30, FPS_30)).toBe(1);
    expect(secondsToFrames(1, FPS_30)).toBe(30);
  });
  it("at 30000/1001, 1 sec = 30 frames (rounded)", () => {
    expect(secondsToFrames(1, FPS_30000_1001)).toBe(30);
  });
});

describe("ZoomProfile selection", () => {
  it("boundaries", () => {
    expect(chooseZoomProfile(0)).toBe("FAR");
    expect(chooseZoomProfile(3.99)).toBe("FAR");
    expect(chooseZoomProfile(4)).toBe("NORMAL");
    expect(chooseZoomProfile(19.99)).toBe("NORMAL");
    expect(chooseZoomProfile(20)).toBe("MID");
    expect(chooseZoomProfile(59.99)).toBe("MID");
    expect(chooseZoomProfile(60)).toBe("CLOSE");
    expect(chooseZoomProfile(199.99)).toBe("CLOSE");
    expect(chooseZoomProfile(200)).toBe("FRAME");
  });
});

describe("ZoomProfile label formats", () => {
  it("FAR shows seconds, NORMAL shows MM:SS, CLOSE/FRAME show MM:SS:FF", () => {
    expect(chooseLabelFormat("FAR")).toBe("SS");
    expect(chooseLabelFormat("NORMAL")).toBe("MMSS");
    expect(chooseLabelFormat("MID")).toBe("MMSSFF");
    expect(chooseLabelFormat("CLOSE")).toBe("MMSSFF");
    expect(chooseLabelFormat("FRAME")).toBe("MMSSFFFFR");
  });
});

describe("chooseTickStep lands ticks ~60-120 px apart", () => {
  const ZOOMS = [4, 12, 60, 200];
  const FPSES = [FPS_24, FPS_25, FPS_30, FPS_60];
  for (const zoom of ZOOMS) {
    for (const fps of FPSES) {
      it(`zoom=${zoom} fps=${fps.num}/${fps.den}`, () => {
        const profile = chooseZoomProfile(zoom);
        const step = chooseTickStep(profile, fps, zoom);
        const pxPerF = pxPerFrame(zoom, fps);
        const pxBetween = step * pxPerF;
        expect(pxBetween).toBeGreaterThanOrEqual(60);
        expect(pxBetween).toBeLessThanOrEqual(120);
      });
    }
  }
});

// Declare FPS_50 for the loop above (alias of FPS_30 since 50fps
// isn't common; tests can be relaxed later)
const FPS_50 = rational(50, 1);
