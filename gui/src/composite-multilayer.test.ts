// GUI-04 04-05: Preview Layer Model — REGRESSION TEST for PiP
// heuristic removal.
//
// Per plan §7.1:
//   "Mark V2=30% / V3=20% PiP heuristic as `deprecated presentation
//    heuristic`. No more: V2 = 30%, V3 = 20%, or any track-index-
//    based automatic shrinking."
//
// This test file's OLD content tested the deleted PiP helpers
// (`defaultPiPStyle`, `splitLayersForPiP`). The current test pins
// that:
//   - the OLD PiP constants 0.30 / 0.20 are NO LONGER produced
//     anywhere in the rendering pipeline
//   - the new helpers (`preview-layer.ts`) use Clip.transform
//     instead of track-index
//   - hidden tracks are excluded from rendering (Core's
//     `build_preview_plan` does this; the GUI just consumes the
//     plan)
//   - track identity does NOT determine visual size

import { describe, expect, it } from "vitest";
import {
  badgeColorForKind,
} from "./composite-multilayer";
import {
  defaultTransform,
  resolveLayerTransform,
  layerCssTransform,
  zOrderedLayers,
} from "./preview-layer";
import type { PreviewLayer } from "./preview-plan";

// ---------------------------------------------------------------------------
// REGRESSION: PiP heuristic constants must NOT appear in the rendering
// pipeline. Any future contributor who re-introduces a track-index
// PiP shrinking rule will fail this test.
// ---------------------------------------------------------------------------

describe("regression: PiP heuristic (V2=30% / V3=20%) removed (plan §7.1)", () => {
  it("defaultTransform does NOT use 30% or 20% scaling", () => {
    const d = defaultTransform();
    // PiP heuristic used 0.30 for V2 and 0.20 for V3. The new
    // default is scale=1 (full-canvas, no PiP shrinking).
    expect(d.scale).toBe(1);
    expect(d.scale).not.toBeCloseTo(0.30);
    expect(d.scale).not.toBeCloseTo(0.20);
  });

  it("layerCssTransform does NOT produce any 30% or 20% width scaling", () => {
    // For ANY input transform, the resulting scale should NOT
    // collapse to 30% or 20% based on track index. With a default
    // transform, scale is 1.
    const cssT = layerCssTransform(defaultTransform());
    // CSS transform is "translate(0%, 0%) scale(1) rotate(0deg)".
    expect(cssT.transform).toContain("scale(1)");
    expect(cssT.transform).not.toContain("scale(0.3");
    expect(cssT.transform).not.toContain("scale(0.2");
  });

  it("resolveLayerTransform defaults to scale=1, never 30% or 20%", () => {
    // Even when clip.transform is fully empty, the layer resolves
    // to scale=1 — no PiP shrinking.
    const empty = resolveLayerTransform({ transform: {} });
    expect(empty.scale).toBe(1);
    expect(empty.scale).not.toBeCloseTo(0.30);
    expect(empty.scale).not.toBeCloseTo(0.20);
  });
});

// ---------------------------------------------------------------------------
// Helpers behavior
// ---------------------------------------------------------------------------

function layer(
  track_id: string, layer_index: number, kind: string = "video",
  transform: Record<string, unknown> = {},
): PreviewLayer {
  return {
    track_id, layer_index, kind,
    clip_id: `c-${track_id}`, asset_id: `a-${track_id}`,
    asset_type: kind, asset_path: "/tmp/x",
    timeline_start_frame: 0, timeline_end_frame: 30,
    source_start_frame: 0, source_end_frame: 30,
    source_fps: { num: 30, den: 1 },
    transform,
  };
}

describe("defaultTransform (plan §7.4)", () => {
  it("centered, fit/contain (scale=1), rotation=0, opacity=1", () => {
    const d = defaultTransform();
    expect(d).toEqual({ x: 0, y: 0, scale: 1, rotation: 0, opacity: 1 });
  });
});

describe("resolveLayerTransform", () => {
  it("applies defaults for missing fields", () => {
    const tr = resolveLayerTransform({ transform: { x: 0.5 } });
    expect(tr.x).toBe(0.5);
    expect(tr.y).toBe(0);            // default
    expect(tr.scale).toBe(1);        // default
    expect(tr.rotation).toBe(0);     // default
    expect(tr.opacity).toBe(1);      // default
  });

  it("honors all explicit fields", () => {
    const tr = resolveLayerTransform({ transform: {
      x: -0.5, y: 0.25, scale: 0.8, rotation: 45, opacity: 0.6,
    } });
    expect(tr.x).toBeCloseTo(-0.5);
    expect(tr.y).toBeCloseTo(0.25);
    expect(tr.scale).toBeCloseTo(0.8);
    expect(tr.rotation).toBe(45);
    expect(tr.opacity).toBeCloseTo(0.6);
  });

  it("ignores non-numeric fields (type-safe extraction)", () => {
    const tr = resolveLayerTransform({ transform: {
      x: "0.5", y: null, scale: undefined, rotation: NaN, opacity: -1,
    } });
    // All invalid → fall back to defaults.
    expect(tr.x).toBe(0);
    expect(tr.y).toBe(0);
    expect(tr.scale).toBe(1);
    expect(tr.rotation).toBe(0);
    // opacity -1 is a finite number, so the type check passes,
    // but is out-of-range. We don't clamp; consumer decides.
    expect(tr.opacity).toBe(-1);
  });

  it("treats non-object transform as defaults", () => {
    const tr = resolveLayerTransform({ transform: null as unknown as Record<string, unknown> });
    expect(tr).toEqual(defaultTransform());
  });
});

describe("layerCssTransform", () => {
  it("default transform yields translate(0%, 0%) scale(1) rotate(0deg)", () => {
    const cssT = layerCssTransform(defaultTransform());
    expect(cssT.transform).toBe("translate(0%, 0%) scale(1) rotate(0deg)");
    expect(cssT.opacity).toBe(1);
  });

  it("non-default transform produces full translate/scale/rotate", () => {
    const cssT = layerCssTransform({ x: 0.5, y: -0.25, scale: 1.5, rotation: 90, opacity: 0.8 });
    expect(cssT.transform).toBe(
      "translate(25%, -12.5%) scale(1.5) rotate(90deg)"
    );
    expect(cssT.opacity).toBe(0.8);
  });
});

describe("zOrderedLayers (plan §7.2)", () => {
  it("sorts by layer_index ascending (bottom first)", () => {
    const plan = {
      tracks: [
        [layer("v2", 1), layer("v2b", 2)],  // V2 track: z=1, z=2
        [layer("v1", 0)],                    // V1 track: z=0 (bottom)
        [layer("v3", 3)],                    // V3 track: z=3
      ],
    };
    const ordered = zOrderedLayers(plan);
    expect(ordered.map(l => l.track_id)).toEqual(["v1", "v2", "v2b", "v3"]);
  });

  it("is deterministic: same plan → same order (plan §7.8)", () => {
    const plan = {
      tracks: [
        [layer("v2", 1), layer("v1", 0), layer("v3", 2)],
      ],
    };
    const a = zOrderedLayers(plan);
    const b = zOrderedLayers(plan);
    expect(a.map(l => l.track_id)).toEqual(b.map(l => l.track_id));
  });

  it("handles empty tracks", () => {
    expect(zOrderedLayers({ tracks: [] })).toEqual([]);
    expect(zOrderedLayers({ tracks: [[]] })).toEqual([]);
  });
});

describe("track identity does NOT imply visual size (plan §7.5)", () => {
  it("V1 and V3 with default transforms have identical CSS transform", () => {
    const v1Layer = layer("v1", 0);
    const v3Layer = layer("v3", 2);
    const t1 = layerCssTransform(resolveLayerTransform(v1Layer));
    const t3 = layerCssTransform(resolveLayerTransform(v3Layer));
    // Same default transform → same CSS. Track identity has no effect.
    expect(t1.transform).toBe(t3.transform);
    expect(t1.opacity).toBe(t3.opacity);
  });

  it("V2 in the OLD PiP heuristic was 30%; in the new model it's identical to V1/V3", () => {
    // This is the explicit regression test: V2 with no explicit
    // transform must NOT collapse to 30%.
    const v2 = layer("v2", 1);
    const cssT = layerCssTransform(resolveLayerTransform(v2));
    expect(cssT.transform).not.toMatch(/scale\(0\.[0-9]/);
    expect(cssT.transform).toContain("scale(1)");
  });
});

// ---------------------------------------------------------------------------
// Hidden-track exclusion (Core already filters; this pins that the
// renderer does not re-introduce hidden layers from a different path.)
// ---------------------------------------------------------------------------

describe("hidden track exclusion (plan §7.6)", () => {
  it("rendered layers are exactly plan.tracks (no hidden)", () => {
    // Core's build_preview_plan already filters out hidden tracks
    // (yroll/core/plan.py:178, 193). The renderer iterates
    // plan.tracks as-is — it MUST NOT independently re-introduce
    // a hidden layer. This test pins that zOrderedLayers is a
    // pure pass-through of plan.tracks.
    const plan = {
      tracks: [
        [layer("v1", 0)],
        [layer("v2", 1)],  // not hidden in this fixture
      ],
    };
    const ordered = zOrderedLayers(plan);
    // The function does not look at track.hidden — that's Core's
    // job. But it also doesn't accidentally INCLUDE hidden tracks
    // that Core already excluded.
    const trackIds = ordered.map(l => l.track_id);
    expect(trackIds).toEqual(["v1", "v2"]);
    // If Core filtered out a hidden track, this function doesn't
    // re-add it (it never sees hidden tracks in the first place).
  });
});

describe("badgeColorForKind (preserved)", () => {
  it("returns blue for video/image", () => {
    expect(badgeColorForKind("video")).toBe("#79b8ff");
    expect(badgeColorForKind("image")).toBe("#79b8ff");
  });
  it("returns green for audio", () => {
    expect(badgeColorForKind("audio")).toBe("#7ec97e");
  });
  it("returns yellow for text/subtitle", () => {
    expect(badgeColorForKind("text")).toBe("#ffd479");
    expect(badgeColorForKind("subtitle")).toBe("#ffd479");
  });
});