// gui/src/preview-layer.ts
//
// GUI-04 04-05: Preview Layer Model.
//
// REMOVED: the temporary V2=30% / V3=20% PiP heuristic
// (composite-multilayer.ts's defaultPiPStyle / splitLayersForPiP).
// The "bottom layer full canvas, others 30% or 20% in the
// bottom-right corner" was a presentation-only artifact and is no
// longer the rule.
//
// NEW RULE (plan §7):
//   TimelineFrame N
//     → PreviewPlan
//       → active visual clips (per plan.tracks, hidden excluded)
//         → stable z-order (by layer_index, deterministic)
//           → each clip's own Clip.transform drives placement
//             → renderer applies transform.
//
// Default transform for a newly created visual clip (plan §7.4):
//   x = 0 (centered)
//   y = 0 (centered)
//   scale = 1 (no extra scaling; canvas-fit via objectFit:contain)
//   rotation = 0
//   opacity = 1
//
// Track identity (V1/V2/V3) is layer/z-order, NOT layout preset.
// The renderer MUST NOT base visual size on track index.

import type { PreviewLayer } from "./preview-plan";

/** Resolved integer/float transform values used by the renderer.
 *  All fields are present (defaults applied) so the renderer does
 *  not need to handle undefined branches. */
export interface ResolvedTransform {
  /** Normalized horizontal center offset, -1..1. 0 = centered.
   *  ±1 = layer edge at canvas edge. */
  x: number;
  /** Normalized vertical center offset, -1..1. 0 = centered. */
  y: number;
  /** Multiplier 0.1..3. 1 = no scaling (canvas-fit via CSS). */
  scale: number;
  /** Rotation in degrees. 0 = no rotation. */
  rotation: number;
  /** Opacity 0..1. 1 = fully opaque. */
  opacity: number;
}

/** Default transform for any layer with no user-set fields. */
export function defaultTransform(): ResolvedTransform {
  return { x: 0, y: 0, scale: 1, rotation: 0, opacity: 1 };
}

/** Read a layer's transform from clip.transform, applying defaults
 *  for any field not present. clip.transform is a Record<string,
 *  unknown> (raw JSON from Core). Unknown fields are ignored.
 *
 *  This is the SOLE consumer of clip.transform for visual placement.
 *  Per plan §7.3, Clip.transform is the sole semantic source. */
export function resolveLayerTransform(
  layer: Pick<PreviewLayer, "transform">,
): ResolvedTransform {
  const t = (layer.transform && typeof layer.transform === "object")
    ? (layer.transform as Record<string, unknown>)
    : {};
  const d = defaultTransform();
  const num = (k: string): number | undefined => {
    const v = t[k];
    return typeof v === "number" && Number.isFinite(v) ? v : undefined;
  };
  return {
    x: num("x") ?? d.x,
    y: num("y") ?? d.y,
    scale: num("scale") ?? d.scale,
    rotation: num("rotation") ?? d.rotation,
    opacity: num("opacity") ?? d.opacity,
  };
}

/** Convert a ResolvedTransform into the CSS positioning + transform
 *  applied to the layer's wrapping div.
 *
 *  x and y are normalized -1..1 center offsets. translate(x*50%, y*50%)
 *  places the layer's CENTER at x*50% / y*50% offset from canvas
 *  center. (50% is relative to the layer's own size, which equals
 *  canvas size after objectFit:contain.)
 *
 *  scale is applied around the layer's own center (default
 *  transform-origin: 50% 50%).
 *
 *  rotation is applied around the same center.
 *
 *  opacity is applied as a separate CSS property (not part of
 *  transform) so the CSS engine applies it correctly without
 *  affecting the transform stack. */
export function layerCssTransform(t: ResolvedTransform): {
  transform: string;
  opacity: number;
  zIndex: number;
} {
  return {
    transform: `translate(${t.x * 50}%, ${t.y * 50}%) scale(${t.scale}) rotate(${t.rotation}deg)`,
    opacity: t.opacity,
    // zIndex is set separately by the renderer using layer_index;
    // we don't put it here so the caller can compose freely.
    zIndex: 0,
  };
}

/** Stable z-ordered list of all visual layers in the plan.
 *
 *  plan.tracks is ordered by track iteration order (Core returns
 *  tracks in declared order, with hidden tracks filtered).
 *  Within each track, layers are sorted by timeline_start_frame
 *  and assigned sequential layer_index values starting from a
 *  per-track base (see yroll/core/plan.py:170-187).
 *
 *  We sort the concatenated list by layer_index ascending so the
 *  bottom (lowest z) is first. This is the DETERMINISTIC order
 *  the renderer iterates to stack layers.
 *
 *  Accepts both shapes:
 *    - `previewPlan.tracks` is `PreviewLayer[][]` (nested per-track)
 *    - `composite.visual_layers` is `PreviewLayer[]` (already flat,
 *      already ordered by Core's `build_preview_plan`)
 *  Both yield the same z-ordered output.
 *
 *  Determinism property (req. 8): same Core state + same
 *  TimelineFrame produces the same output order regardless of:
 *    - track number (NOT used)
 *    - clip insertion order (handled by layer_index assignment)
 *    - currently selected clip (NOT used)
 *    - DOM position (NOT used)
 *    - viewport quirks (NOT used)
 */
export function zOrderedLayers(
  source:
    | { tracks: PreviewLayer[][] }
    | { visual_layers: PreviewLayer[] }
    | PreviewLayer[],
): PreviewLayer[] {
  // Accept nested (`tracks` is per-track), flat (`visual_layers`
  // is already-flat from composite), or a bare array.
  let flat: PreviewLayer[];
  if (Array.isArray(source)) {
    flat = source;
  } else if ("visual_layers" in source) {
    flat = source.visual_layers;
  } else {
    flat = [];
    for (const t of source.tracks) {
      for (const l of t) flat.push(l);
    }
  }
  // Sort by layer_index ascending (bottom = lowest = first).
  // Stable sort so equal layer_index preserves the concatenation order.
  return [...flat].sort((a, b) => a.layer_index - b.layer_index);
}