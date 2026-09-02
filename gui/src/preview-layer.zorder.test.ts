// gui/src/preview-layer.zorder.test.ts
//
// GUI-04.5 P0-B: Preview z-order semantics — vitest coverage for
// the actual TypeScript implementation (the pytest uses a Python
// mirror; here we test the real `zOrderedLayers` function).
//
// Invariant pinned (P0-B #1, #2, #3):
//   * upper Timeline track ⇒ higher visual layer ⇒ occludes lower
//   * Preview z-order derived from canonical track ordering
//   * no accidental DOM paint order reliance

import { describe, it, expect } from "vitest";
import { zOrderedLayers } from "./preview-layer";
import type { PreviewLayer } from "./preview-plan";

function layer(track_id: string, layer_index: number): PreviewLayer {
  return {
    track_id,
    layer_index,
    kind: "video",
    clip_id: `clip-${track_id}`,
    asset_id: `asset-${track_id}`,
    asset_type: "video",
    asset_path: `${track_id}.mp4`,
    timeline_start_frame: 0,
    timeline_end_frame: 100,
    source_start_frame: 0,
    source_end_frame: 100,
    source_fps: null,
    transform: {},
  };
}

describe("Preview z-order semantics (GUI-04.5 P0-B)", () => {
  it("sorts flat visual_layers by layer_index ascending (bottom first)", () => {
    const layers = [
      layer("v6", 5),
      layer("v3", 2),
      layer("v8", 7),
      layer("v1", 0),
      layer("v4", 3),
    ];
    const out = zOrderedLayers(layers);
    expect(out.map((l) => l.layer_index)).toEqual([0, 2, 3, 5, 7]);
    expect(out[0].track_id).toBe("v1"); // bottom
    expect(out[out.length - 1].track_id).toBe("v8"); // top
  });

  it("sorts nested `tracks` arrays in the same ascending order", () => {
    const tracks: PreviewLayer[][] = [
      [layer("v6", 5), layer("v7", 6)],
      [layer("v1", 0), layer("v2", 1)],
      [layer("v3", 2), layer("v4", 3), layer("v5", 4)],
    ];
    const out = zOrderedLayers({ tracks });
    expect(out.map((l) => l.layer_index)).toEqual([0, 1, 2, 3, 4, 5, 6]);
    expect(out[0].track_id).toBe("v1");
    expect(out[6].track_id).toBe("v7");
  });

  it("accepts composite.visual_layers shape", () => {
    const out = zOrderedLayers({
      visual_layers: [
        layer("v2", 1),
        layer("v3", 2),
        layer("v1", 0),
      ],
    });
    expect(out.map((l) => l.track_id)).toEqual(["v1", "v2", "v3"]);
  });

  it("uses stable sort: equal layer_index preserves concatenation order", () => {
    const layers = [
      layer("a", 2),
      layer("b", 2),
      layer("c", 1),
    ];
    const out = zOrderedLayers(layers);
    // c (1) first, then a (2) then b (2) in original order.
    expect(out.map((l) => l.track_id)).toEqual(["c", "a", "b"]);
  });

  it("upper track (higher numeric suffix) ⇒ higher layer_index ⇒ painted last", () => {
    // Mimics the Core plan: V1 base=0, V2 base=1, ..., V10 base=9.
    const layers: PreviewLayer[] = [];
    for (let n = 1; n <= 10; n++) {
      layers.push(layer(`v${n}`, n - 1));
    }
    const out = zOrderedLayers(layers);
    for (let n = 1; n < 10; n++) {
      const idxLower = out.findIndex((l) => l.track_id === `v${n}`);
      const idxUpper = out.findIndex((l) => l.track_id === `v${n + 1}`);
      expect(idxLower).toBeLessThan(idxUpper);
    }
  });

  it("does not mutate the input array", () => {
    const layers = [layer("v3", 2), layer("v1", 0), layer("v2", 1)];
    const snapshot = layers.map((l) => l.track_id);
    zOrderedLayers(layers);
    expect(layers.map((l) => l.track_id)).toEqual(snapshot);
  });
});
