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

// ============================================================================
// GUI-03R Production Reality Repair v0.1 — acceptance tests
// ============================================================================
//
// 10 required items from the 03R spec; mapped one-to-one below.
import {
  frameRulerLabel,
  frameToRulerSeconds,
} from "./frames";
import { api } from "./api";

// -------- 8. ruler exposes seconds + frame (millisecond trailing field) ----
describe("GUI-03R: ruler format", () => {
  const FPS_30 = rational(30, 1);
  const FPS_24 = rational(24, 1);

  it("frameToRulerSeconds(372 @ 30fps) === 00:12.400", () => {
    expect(frameToRulerSeconds(372, FPS_30)).toBe("00:12.400");
  });

  it("trailing .mmm is milliseconds, NOT a frame field", () => {
    // 1 frame @ 30fps = 33.33ms → "00:00.033"
    expect(frameToRulerSeconds(1, FPS_30)).toBe("00:00.033");
  });

  it("frame 0 displays as 00:00.000", () => {
    expect(frameToRulerSeconds(0, FPS_30)).toBe("00:00.000");
  });

  it("rounds to ms at 24fps (1 frame = 41.666ms)", () => {
    expect(frameToRulerSeconds(1, FPS_24)).toBe("00:00.042");
  });

  it("frameRulerLabel: F<frame> companion for precise zoom", () => {
    expect(frameRulerLabel(372)).toBe("F372");
    expect(frameRulerLabel(0)).toBe("F0");
  });
});

// -------- 3. 1-frame drag visually controllable at default zoom ----------
// Spec: "1 px/frame at 30fps is the desired starting feel".
describe("GUI-03R: default zoom is 1 px/frame at 30 fps", () => {
  it("pxPerFrame(30, 30/1) === 1", () => {
    expect(pxPerFrame(30, rational(30, 1))).toBeCloseTo(1, 6);
  });
  it("1-frame drag is at least 0.5 px wide (visually controllable)", () => {
    expect(pxPerFrame(30, rational(30, 1))).toBeGreaterThanOrEqual(0.5);
  });
});

// Helper: stub fetch with a dispatch table so the post-mutate
// syncRevision fetch (which hits /ui/status) doesn't overwrite the
// captured URL we actually want to assert.
function makeFetchStub(
  handlers: Record<string, (init?: RequestInit) => Response>,
): { fetch: typeof fetch; calls: Array<{ url: string; method: string; init?: RequestInit }> } {
  const calls: Array<{ url: string; method: string; init?: RequestInit }> = [];
  const stub = (async (url: string, init?: RequestInit) => {
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push({ url, method, init });
    for (const [prefix, h] of Object.entries(handlers)) {
      if (url.includes(prefix)) return h(init);
    }
    // Default: 200 OK with empty body
    return new Response("{}", {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  return { fetch: stub, calls };
}

// -------- 1. image drag routes to addImageClip with frame duration -------
describe("GUI-03R: api.addImageClip", () => {
  it("POSTs /clips/add_image with frame-native payload", async () => {
    const orig = globalThis.fetch;
    const { fetch: stub, calls } = makeFetchStub({
      "/clips/add_image": () => new Response(
        JSON.stringify({ clip_id: "c-new" }),
        { status: 200,
          headers: { "Content-Type": "application/json" } },
      ),
    });
    globalThis.fetch = stub;
    try {
      const r = await api.addImageClip("a-img", 100, 150, "v1", "drag");
      expect(r.clip_id).toBe("c-new");
      const targetCall = calls.find(
        (c) => c.url.includes("/clips/add_image"),
      );
      expect(targetCall, "missing /clips/add_image call").toBeDefined();
      expect(targetCall!.method).toBe("POST");
      const body = JSON.parse(targetCall!.init?.body as string);
      expect(body).toEqual({
        asset_id: "a-img",
        timeline_start_frame: 100,
        timeline_duration_frames: 150,
        track_id: "v1",
        why: "drag",
      });
      // Confirm: no set_speed in the request (03R spec).
      expect(body).not.toHaveProperty("speed");
    } finally {
      globalThis.fetch = orig;
    }
  });
});

// -------- 2. video import path is /assets/import (formerly 404) ----------
describe("GUI-03R: api.importAsset posts to /assets/import", () => {
  it("URL is /assets/import, method is POST", async () => {
    const orig = globalThis.fetch;
    const { fetch: stub, calls } = makeFetchStub({
      "/assets/import": () => new Response(
        JSON.stringify({
          asset: { asset_id: "a1" }, clip: null, deduped: false,
        }),
        { status: 200,
          headers: { "Content-Type": "application/json" } },
      ),
    });
    globalThis.fetch = stub;
    try {
      const file = new File(["x"], "v.mp4", { type: "video/mp4" });
      const r = await api.importAsset(file);
      expect(r.asset.asset_id).toBe("a1");
      const targetCall = calls.find(
        (c) => c.url.includes("/assets/import"),
      );
      expect(targetCall, "missing /assets/import call").toBeDefined();
      expect(targetCall!.method).toBe("POST");
    } finally {
      globalThis.fetch = orig;
    }
  });
});

// -------- 03R-K error UX includes method/path/status/detail ----------
describe("GUI-03R: error messages include METHOD /path /status /detail", () => {
  it("req() surfaces DELETE /clips/... 404 with method+path+status+detail", async () => {
    const orig = globalThis.fetch;
    const { fetch: stub } = makeFetchStub({
      "/clips/c-bad": () => new Response(
        '{"detail":"no such clip"}',
        { status: 404, statusText: "Not Found",
          headers: { "Content-Type": "application/json" } },
      ),
    });
    globalThis.fetch = stub;
    try {
      let caught = "";
      try {
        await api.removeClip("c-bad");
      } catch (e: any) {
        caught = e.message;
      }
      expect(caught).toMatch(/^DELETE \/clips\/c-bad\?why= → 404 Not Found/);
      expect(caught).toContain("no such clip");
    } finally {
      globalThis.fetch = orig;
    }
  });
});

// ============================================================================
// GUI-03R-Micro: Track Allocation Wiring (GUI side only — Core unchanged)
// ============================================================================
//
// The GUI's automatic-placement path ("+" button, drag without explicit
// target) MUST NOT force v1 / a1. It must pass track_id=null so Core's
// Track Allocation Policy picks the minimum non-overlapping track.
//
// These tests pin the contract the GUI now follows:
//   1. addImageClip / addClip accept trackId=null and serialize
//      track_id: null in the request body (the server side maps
//      null/empty to Core's None which lets the allocator run).
//   2. The explicit-target path still passes track_id (drop on V1).
//   3. An overlap on an explicit target is left for Core to reject
//      (the GUI does not pre-compute a "free" frame).

describe("GUI-03R-Micro: addImageClip auto-placement", () => {
  it("passes track_id=null (server → Core allocator) when no explicit track", async () => {
    const orig = globalThis.fetch;
    const { fetch: stub, calls } = makeFetchStub({
      "/clips/add_image": () => new Response(
        JSON.stringify({ clip_id: "c-img" }),
        { status: 200,
          headers: { "Content-Type": "application/json" } },
      ),
    });
    globalThis.fetch = stub;
    try {
      await api.addImageClip("a-img", 0, 150, null, "auto");
      const targetCall = calls.find(
        (c) => c.url.includes("/clips/add_image"),
      );
      expect(targetCall).toBeDefined();
      const body = JSON.parse(targetCall!.init?.body as string);
      // GUI must NOT force "v1" — Core's allocator picks the track.
      expect(body.track_id).toBeNull();
      // Frame-native coordinates preserved (no seconds-as-duration
      // hack, no set_speed).
      expect(body.timeline_start_frame).toBe(0);
      expect(body.timeline_duration_frames).toBe(150);
      expect(body).not.toHaveProperty("speed");
    } finally {
      globalThis.fetch = orig;
    }
  });

  it("explicit drop passes the user's track_id through", async () => {
    const orig = globalThis.fetch;
    const { fetch: stub, calls } = makeFetchStub({
      "/clips/add_image": () => new Response(
        JSON.stringify({ clip_id: "c-img" }),
        { status: 200,
          headers: { "Content-Type": "application/json" } },
      ),
    });
    globalThis.fetch = stub;
    try {
      await api.addImageClip("a-img", 100, 150, "v2", "drop");
      const targetCall = calls.find(
        (c) => c.url.includes("/clips/add_image"),
      );
      const body = JSON.parse(targetCall!.init?.body as string);
      expect(body.track_id).toBe("v2");
    } finally {
      globalThis.fetch = orig;
    }
  });
});

describe("GUI-03R-Micro: addClip auto-placement (video/audio)", () => {
  it("passes track_id=null when no explicit track was chosen", async () => {
    const orig = globalThis.fetch;
    const { fetch: stub, calls } = makeFetchStub({
      "/clips": () => new Response(
        JSON.stringify({ clip_id: "c-v" }),
        { status: 200,
          headers: { "Content-Type": "application/json" } },
      ),
    });
    globalThis.fetch = stub;
    try {
      await api.addClip("a-v", 0, 10, 0, null, "auto");
      const targetCall = calls.find((c) => /\/clips(\?|$)/.test(c.url));
      expect(targetCall).toBeDefined();
      const body = JSON.parse(targetCall!.init?.body as string);
      expect(body.track_id).toBeNull();
      expect(body.timeline_start).toBe(0);
    } finally {
      globalThis.fetch = orig;
    }
  });

  it("explicit drop passes the user's track_id through", async () => {
    const orig = globalThis.fetch;
    const { fetch: stub, calls } = makeFetchStub({
      "/clips": () => new Response(
        JSON.stringify({ clip_id: "c-v" }),
        { status: 200,
          headers: { "Content-Type": "application/json" } },
      ),
    });
    globalThis.fetch = stub;
    try {
      await api.addClip("a-v", 0, 10, 5, "a1", "drop");
      const targetCall = calls.find((c) => /\/clips(\?|$)/.test(c.url));
      const body = JSON.parse(targetCall!.init?.body as string);
      expect(body.track_id).toBe("a1");
      expect(body.timeline_start).toBe(5);
    } finally {
      globalThis.fetch = orig;
    }
  });
});

describe("GUI-03R-Micro: explicit-drop overlap is left to Core", () => {
  it("does NOT pre-compute a free frame; passes the drop frame verbatim", async () => {
    // The GUI used to run a local findFree() that shifted the drop
    // frame past occupied ranges. 03R-Micro removes that — Core
    // enforces overlap. The drop frame MUST be passed verbatim
    // even if it would conflict; Core will then reject.
    const orig = globalThis.fetch;
    const { fetch: stub, calls } = makeFetchStub({
      "/clips": () => new Response(
        JSON.stringify({ detail: "track a1 时间重叠" }),
        { status: 400, statusText: "Bad Request",
          headers: { "Content-Type": "application/json" } },
      ),
    });
    globalThis.fetch = stub;
    try {
      let caught = "";
      try {
        // Drop frame = 5s; v1 already has a clip covering [0,10]
        // so this should conflict.
        await api.addClip("a-v", 0, 3, 5, "a1", "drop");
      const targetCall = calls.find((c) => /\/clips(\?|$)/.test(c.url));
      } catch (e: any) {
        caught = e.message;
      }
      // Server returned 400; req() threw — and the GUI error UX
      // (03R-K) surfaces method+path+status+detail.
      expect(caught).toMatch(/^POST \/clips/);
      expect(caught).toContain("400");
      expect(caught).toContain("时间重叠");
      const targetCall = calls.find((c) => /\/clips(\?|$)/.test(c.url));
      const body = JSON.parse(targetCall!.init?.body as string);
      // The drop frame 5 was passed verbatim — no local mutation.
      expect(body.timeline_start).toBe(5);
    } finally {
      globalThis.fetch = orig;
    }
  });
});
