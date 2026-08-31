// GUI-03R5-B3 (Decision 4): Multi-layer preview rendering.
//
// The audit found that all visual layers filled the canvas with
// objectFit:contain, z-stacked by layer_index. That made the topmost
// layer COMPLETELY COVER the lower layers — the user couldn't tell
// that V1+V2+V3 were all there. The PiP visualization in this file
// is PRESENTATION ONLY — it is NEVER persisted to clip.transform
// or any Core data structure. The eventual persistent model (Layer =
// media + transform + opacity + visibility + z-order) is unchanged.
//
// Rule (per Decision 4):
//   * The BOTTOMMOST layer (lowest layer_index) renders full canvas
//     (the "main" video).
//   * Each layer above the bottommost renders as a Picture-in-Picture
//     overlay. The DEFAULT scale (when clip.transform.scale is
//     undefined) is 30% for V2 and 20% for V3+. The PiP is anchored
//     to the bottom-right with 8% margin.
//   * Every layer shows a small track-id badge (top-left) so the
//     user knows what's in the composite at a glance.
//   * If clip.transform.scale IS defined (user explicitly set PiP),
//     the explicit value is respected — the default is only the
//     "first-time visualization" rule.

import type { PreviewLayer } from "./preview-plan";

export interface PiPStyle {
  /** Width as a percentage of the parent canvas (0..1). */
  scaleW: number;
  /** Height as a percentage of the parent canvas (0..1). */
  scaleH: number;
  /** Left offset as percentage of parent (0..1, top-left origin). */
  leftPct: number;
  /** Top offset as percentage of parent (0..1, top-left origin). */
  topPct: number;
}

/** GUI-03R5-B3: compute the PiP style for a layer based on its
 *  position in the stack. Bottom layer is always 100% × 100%.
 *  Each subsequent layer is a PiP overlay (default 30%, V3+ 20%),
 *  anchored bottom-right with 8% margin.
 *
 *  Returned style is the COMPUTED default. Callers MUST respect an
 *  explicit clip.transform.scale (if present) by overriding `scaleW`
 *  — this helper returns defaults only. */
export function defaultPiPStyle(
  layerIndexInStack: number,
  totalLayers: number,
): PiPStyle {
  if (layerIndexInStack === 0 || totalLayers <= 1) {
    // Bottom layer: full canvas.
    return { scaleW: 1, scaleH: 1, leftPct: 0, topPct: 0 };
  }
  // V2 = 30% wide; V3+ = 20% wide. PiP anchored bottom-right
  // with 8% margin. V2/V3 stack upward from bottom-right.
  const scaleW = layerIndexInStack === 1 ? 0.30 : 0.20;
  const scaleH = scaleW * (9 / 16);  // assume 16:9 PiP
  const rightMargin = 0.08;
  const bottomMargin = 0.08;
  // Stack upward: V2 at bottom-right; V3 just above it.
  const verticalStep = scaleH + 0.04;
  const baseTopPct = 1 - bottomMargin - scaleH - (layerIndexInStack - 1) * verticalStep;
  return {
    scaleW,
    scaleH,
    leftPct: 1 - rightMargin - scaleW,
    topPct: Math.max(0.04, baseTopPct),
  };
}

/** GUI-03R5-B3: split visual layers into [bottom] + [overlays].
 *  The bottom layer is rendered full-canvas. Overlays get PiP style.
 *  Returns them in z-stacked order (bottom first). */
export function splitLayersForPiP(
  visualLayers: PreviewLayer[],
): {
  bottom: PreviewLayer | null;
  overlays: Array<{ layer: PreviewLayer; style: PiPStyle }>;
} {
  if (visualLayers.length === 0) {
    return { bottom: null, overlays: [] };
  }
  // Sort by layer_index ascending so bottom is lowest z.
  const sorted = [...visualLayers].sort(
    (a, b) => a.layer_index - b.layer_index,
  );
  const bottom = sorted[0];
  const overlays = sorted.slice(1).map((layer, i) => ({
    layer,
    style: defaultPiPStyle(i + 1, sorted.length),
  }));
  return { bottom, overlays };
}

/** Track-id badge colors per kind. The badge is a small chip on the
 *  top-left of every visual layer (presentation-only). */
export function badgeColorForKind(kind: string): string {
  switch (kind) {
    case "video":   return "#79b8ff";  // blue
    case "image":   return "#79b8ff";  // blue (same family)
    case "audio":   return "#7ec97e";  // green
    case "text":    return "#ffd479";  // yellow
    case "subtitle":return "#ffd479";  // yellow
    default:        return "#888";
  }
}