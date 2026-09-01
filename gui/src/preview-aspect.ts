// R6.1-C: pure aspect-fit helper.
//
// Computes the canvas (width, height) that fits the requested aspect
// ratio inside the available stage, preserving the EXACT requested aspect
// ratio. The output is always ≤ the stage in both dimensions.
//
// Algorithm (standard "contain" / letterbox / pillarbox):
//   scaleW = availW / aspectW
//   scaleH = availH / aspectH
//   if scaleW <= scaleH: width-bound → canvasH = scaleW × aspectH
//   else:                 height-bound → canvasW = scaleH × aspectW
//
// The previous formula (PreviewPlayer.tsx:466-473, pre-R6.1-C) used
// `availW / aspectW` as the height — that was dimensionally wrong: it
// gave pixels/pixel, not pixels. 16:9 on a 720×405 stage produced
// 720×45 (a flat strip) instead of 720×405. The `aspectH` variable was
// declared but never used. This module fixes both defects.

export interface AspectSize {
  width: number;
  height: number;
}

export interface AspectFitInput {
  stageWidth: number;
  stageHeight: number;
  /** Output canvas inset (px each side). */
  inset?: number;
  aspect: string; // "W:H" e.g. "16:9"
}

export interface AspectFitResult {
  canvas: AspectSize;
  bound: "width" | "height";
  /** Effective aspect (canvas.width / canvas.height). Equals the
   *  requested aspect up to floating-point noise. */
  effectiveAspect: number;
}

/** Parse "W:H" aspect string into integers. Tolerates "16:9" and "1:1";
 *  falls back to 16:9 for unparseable input. */
export function parseAspect(aspect: string): { w: number; h: number } {
  const parts = aspect.split(":").map((s) => Number(s.trim()));
  const w = Number.isFinite(parts[0]) && parts[0] > 0 ? parts[0] : 16;
  const h = Number.isFinite(parts[1]) && parts[1] > 0 ? parts[1] : 9;
  return { w, h };
}

/** Pure aspect-fit computation. Always returns a rectangle that fits
 *  inside the available stage while preserving the requested aspect
 *  ratio to within floating-point precision. */
export function computeCanvasSize(input: AspectFitInput): AspectFitResult {
  const inset = input.inset ?? 0;
  const availW = Math.max(1, input.stageWidth - inset * 2);
  const availH = Math.max(1, input.stageHeight - inset * 2);
  const { w: aspectW, h: aspectH } = parseAspect(input.aspect);
  // The standard "contain" rule: pick the smaller of the two axis
  // scales so the rectangle fits in BOTH dimensions.
  const scaleW = availW / aspectW;
  const scaleH = availH / aspectH;
  if (scaleW <= scaleH) {
    // Width-bound: fill the available width, derive height.
    return {
      canvas: { width: availW, height: scaleW * aspectH },
      bound: "width",
      effectiveAspect: aspectW / aspectH,
    };
  } else {
    // Height-bound: fill the available height, derive width.
    return {
      canvas: { width: scaleH * aspectW, height: availH },
      bound: "height",
      effectiveAspect: aspectW / aspectH,
    };
  }
}
