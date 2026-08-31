// GUI-03R5-B3: Multi-layer PiP rendering tests.

import { describe, expect, it } from "vitest";
import {
  defaultPiPStyle, splitLayersForPiP, badgeColorForKind,
} from "./composite-multilayer";
import type { PreviewLayer } from "./preview-plan";

function layer(
  track_id: string, layer_index: number, kind: string = "video",
): PreviewLayer {
  return {
    track_id, layer_index, kind,
    clip_id: `c-${track_id}`, asset_id: `a-${track_id}`,
    asset_type: kind, asset_path: "/tmp/x",
    timeline_start_frame: 0, timeline_end_frame: 30,
    source_start_frame: 0, source_end_frame: 30,
    source_fps: { num: 30, den: 1 },
    transform: {},
  };
}

describe("defaultPiPStyle", () => {
  it("bottom layer is 100% × 100%", () => {
    const s = defaultPiPStyle(0, 3);
    expect(s.scaleW).toBe(1);
    expect(s.scaleH).toBe(1);
    expect(s.leftPct).toBe(0);
    expect(s.topPct).toBe(0);
  });

  it("V2 (layer index 1) is 30% wide PiP, anchored bottom-right", () => {
    const s = defaultPiPStyle(1, 3);
    expect(s.scaleW).toBeCloseTo(0.30);
    expect(s.scaleH).toBeCloseTo(0.30 * 9 / 16);
    // Anchored bottom-right with 8% margin.
    expect(s.leftPct).toBeCloseTo(1 - 0.08 - 0.30);
    // topPct should be positive (within viewport).
    expect(s.topPct).toBeGreaterThan(0);
    expect(s.topPct).toBeLessThan(1);
  });

  it("V3 (layer index 2) is 20% wide PiP", () => {
    const s = defaultPiPStyle(2, 3);
    expect(s.scaleW).toBeCloseTo(0.20);
  });

  it("single layer is always full-canvas regardless of index", () => {
    const s = defaultPiPStyle(0, 1);
    expect(s.scaleW).toBe(1);
  });
});

describe("splitLayersForPiP", () => {
  it("3 layers: bottom + 2 overlays", () => {
    const layers = [layer("v1", 0), layer("v2", 1), layer("v3", 2)];
    const { bottom, overlays } = splitLayersForPiP(layers);
    expect(bottom?.track_id).toBe("v1");
    expect(overlays).toHaveLength(2);
    expect(overlays[0].layer.track_id).toBe("v2");
    expect(overlays[0].style.scaleW).toBeCloseTo(0.30);
    expect(overlays[1].layer.track_id).toBe("v3");
    expect(overlays[1].style.scaleW).toBeCloseTo(0.20);
  });

  it("sorts by layer_index even if input is unordered", () => {
    const layers = [layer("v2", 5), layer("v1", 0), layer("v3", 9)];
    const { bottom, overlays } = splitLayersForPiP(layers);
    expect(bottom?.track_id).toBe("v1");
    expect(overlays.map((o) => o.layer.track_id)).toEqual(["v2", "v3"]);
  });

  it("empty input: bottom=null, overlays=[]", () => {
    const { bottom, overlays } = splitLayersForPiP([]);
    expect(bottom).toBeNull();
    expect(overlays).toEqual([]);
  });

  it("single layer: bottom = that layer, overlays = []", () => {
    const { bottom, overlays } = splitLayersForPiP([layer("v1", 0)]);
    expect(bottom?.track_id).toBe("v1");
    expect(overlays).toEqual([]);
  });
});

describe("badgeColorForKind", () => {
  it("video/image → blue", () => {
    expect(badgeColorForKind("video")).toBe("#79b8ff");
    expect(badgeColorForKind("image")).toBe("#79b8ff");
  });
  it("audio → green", () => {
    expect(badgeColorForKind("audio")).toBe("#7ec97e");
  });
  it("text/subtitle → yellow", () => {
    expect(badgeColorForKind("text")).toBe("#ffd479");
    expect(badgeColorForKind("subtitle")).toBe("#ffd479");
  });
  it("unknown → gray", () => {
    expect(badgeColorForKind("xyz")).toBe("#888");
  });
});