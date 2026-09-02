// gui/src/clip-transform.ts
//
// GUI-04 04-06: Transform v0.1 — numeric contract.
//
// Architectural rule (plan §8 / req. 7):
//   Inspector is NOT the owner of transform state. It is an edit
//   entry + viewer of Core's clip.transform. No parallel React
//   state; no direct DOM mutation as the source of truth.
//
// The Core endpoint we wire to: api.setTransform (POST
// /clips/{id}/transform), which calls Core's set_transform and
// writes directly to clip.transform. preview-layer.ts reads
// clip.transform, so the chain is end-to-end Core-authoritative:
//   Inspector input → api.setTransform → Mutation Gate → Core →
//   PreviewPlan invalidation → Inspector + Preview re-render.
//
// Numeric contract (matches Core's set_transform / set_transform2d
// intent, plan §8.2):
//
//   x       normalized -1..1, 0 = centered, ±1 = edge
//   y       normalized -1..1, 0 = centered, ±1 = edge
//   scale   0.1..3, 1 = no extra scaling (canvas-fit via objectFit)
//   rotation degrees, positive = clockwise (CSS convention)
//   opacity 0..1, 1 = fully opaque
//
// Defaults (plan §7.4):
//   {x: 0, y: 0, scale: 1, rotation: 0, opacity: 1}

import type { Clip } from "./api";

export type ClipTransform = {
  x: number;
  y: number;
  scale: number;
  rotation: number;
  opacity: number;
};

/** Default transform for a visual clip. */
export const DEFAULT_TRANSFORM: ClipTransform = {
  x: 0,
  y: 0,
  scale: 1,
  rotation: 0,
  opacity: 1,
};

/** Bounds (numeric contract). */
export const TRANSFORM_BOUNDS = {
  x: { min: -1, max: 1, step: 0.02 },
  y: { min: -1, max: 1, step: 0.02 },
  scale: { min: 0.1, max: 3, step: 0.05 },
  rotation: { min: -180, max: 180, step: 1 },
  opacity: { min: 0, max: 1, step: 0.05 },
};

/** Read the canonical transform of a clip. Missing fields fall
 *  back to defaults (per plan §7.4). Non-numeric values fall back
 *  to defaults (no silent corruption).
 *
 *  This is the SOLE source for Inspector / Preview rendering of
 *  a clip's transform. Returns a fresh object so callers cannot
 *  accidentally mutate Core data. */
export function readClipTransform(clip: Clip): ClipTransform {
  const t = (clip.transform && typeof clip.transform === "object")
    ? clip.transform
    : {};
  const num = (k: string, dflt: number): number => {
    const v = (t as Record<string, unknown>)[k];
    return typeof v === "number" && Number.isFinite(v) ? v : dflt;
  };
  return {
    x: num("x", DEFAULT_TRANSFORM.x),
    y: num("y", DEFAULT_TRANSFORM.y),
    scale: num("scale", DEFAULT_TRANSFORM.scale),
    rotation: num("rotation", DEFAULT_TRANSFORM.rotation),
    opacity: num("opacity", DEFAULT_TRANSFORM.opacity),
  };
}

/** True if `transform` equals `DEFAULT_TRANSFORM` field-by-field. */
export function isDefaultTransform(transform: ClipTransform): boolean {
  return transform.x === DEFAULT_TRANSFORM.x
      && transform.y === DEFAULT_TRANSFORM.y
      && transform.scale === DEFAULT_TRANSFORM.scale
      && transform.rotation === DEFAULT_TRANSFORM.rotation
      && transform.opacity === DEFAULT_TRANSFORM.opacity;
}

/** Clamp a value to its bounds. Used to sanitize user input
 *  before sending to Core (so out-of-range inputs fail in the
 *  UI rather than after a 422 round-trip). */
export function clampToBounds(
  field: keyof typeof TRANSFORM_BOUNDS,
  value: number,
): number {
  const b = TRANSFORM_BOUNDS[field];
  if (value < b.min) return b.min;
  if (value > b.max) return b.max;
  return value;
}

/** Format a transform field for Inspector display.
 *  - x, y: 2 decimals
 *  - scale: percentage (e.g. 1.0 → "100%", 0.5 → "50%")
 *  - rotation: degrees with ° (e.g. 30 → "30°")
 *  - opacity: percentage */
export function formatTransformField(
  field: keyof ClipTransform,
  value: number,
): string {
  switch (field) {
    case "scale":
      return `${Math.round(value * 100)}%`;
    case "rotation":
      return `${Math.round(value)}°`;
    case "opacity":
      return `${Math.round(value * 100)}%`;
    default:
      return value.toFixed(2);
  }
}

/** Validate raw user input against the numeric contract.
 *  Returns null if valid; otherwise returns a string error. */
export function validateTransformInput(
  field: keyof typeof TRANSFORM_BOUNDS,
  raw: string,
): { ok: true; value: number } | { ok: false; error: string } {
  const num = Number(raw);
  if (!Number.isFinite(num)) {
    return { ok: false, error: `${field} 必须是数字` };
  }
  const b = TRANSFORM_BOUNDS[field];
  if (num < b.min || num > b.max) {
    return {
      ok: false,
      error: `${field} 必须在 [${b.min}, ${b.max}] 范围内（输入 ${num}）`,
    };
  }
  return { ok: true, value: num };
}