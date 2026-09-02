// GUI-04 04-05: Preview Layer Model — PiP heuristic REMOVED.
//
// The temporary V2=30% / V3=20% track-index-based PiP heuristic was
// removed in 04-05. Per plan §7:
//   - Clip.transform is the SOLE semantic source for visual
//     placement (x, y, scale, rotation, opacity).
//   - Track identity (V1/V2/V3) is layer/z-order, NOT layout preset.
//   - Each visual layer is rendered using its own transform; the
//     "bottom layer full canvas + others as 30%/20% PiP" rule no
//     longer applies.
//
// The new helpers live in ./preview-layer.ts:
//   - defaultTransform()
//   - resolveLayerTransform(layer)
//   - layerCssTransform(t)
//   - zOrderedLayers(plan)
//
// This file is kept as a placeholder for future multi-layer
// concerns (audio mixing, subtitle compositing) but exports no
// PiP helpers — they have been deleted.

/** Track-id badge colors per kind. Kept here as it's still used by
 *  PreviewPlayer for the visual layer badge. (Presentation only —
 *  does NOT affect layout.) */
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